"""Paste text into whatever field has focus, through the clipboard, and give the clipboard back.

1. Snapshot every format the clipboard holds now.
2. Put the text there with *delayed rendering*: we only announce CF_UNICODETEXT, and Windows asks us
   for the bytes (WM_RENDERFORMAT) the moment some program actually reads it. That is the signal that
   the paste landed.
3. Mark it as private, so it stays out of the Win+V history and the cloud clipboard.
4. Send Ctrl+V.
5. Read seen: wait a moment, then restore the snapshot, unless the user copied something meanwhile.
   No read within the timeout: the focused thing did not take a paste (no text field, an elevated
   window...). The text is then left on the clipboard so the user can paste it by hand.
"""
import ctypes
import struct
import threading
import time
from ctypes import wintypes as w

from hotkey import OWN_INPUT_TAG
from win32 import (CF_BITMAP, CF_DSPBITMAP, CF_DSPENHMETAFILE, CF_DSPMETAFILEPICT, CF_ENHMETAFILE,
                   CF_METAFILEPICT, CF_OWNERDISPLAY, CF_PALETTE, CF_UNICODETEXT, GMEM_MOVEABLE, HWND_MESSAGE,
                   VK_CONTROL, VK_V, WM_APP, WM_CLOSE, WM_DESTROY, WM_RENDERALLFORMATS, WM_RENDERFORMAT,
                   WM_TIMER, WNDPROC, kernel32, key_input, register_window_class, run_message_loop,
                   send_inputs, user32)

user32.GetClipboardFormatNameW.restype = ctypes.c_int
user32.GetClipboardFormatNameW.argtypes = [w.UINT, w.LPWSTR, ctypes.c_int]

WM_APP_PASTE = WM_APP + 10
TIMER_READ, TIMER_RESTORE = 1, 2

# Handles that are not plain memory (GDI objects, owner-drawn) cannot be copied byte by byte.
# Windows re-synthesizes CF_BITMAP from CF_DIB, so images still come back.
_NOT_MEMORY = {CF_BITMAP, CF_METAFILEPICT, CF_PALETTE, CF_ENHMETAFILE, CF_OWNERDISPLAY, CF_DSPBITMAP,
               CF_DSPMETAFILEPICT, CF_DSPENHMETAFILE}
# OLE bookkeeping points at a live COM object of the program that copied; replaying it would lie.
_SKIP_NAMES = {"Ole Private Data", "DataObject"}

PRIVATE_FORMATS = ("ExcludeClipboardContentFromMonitorProcessing", "CanIncludeInClipboardHistory",
                   "CanUploadToCloudClipboard")


def format_name(fmt):
    buf = ctypes.create_unicode_buffer(256)
    return buf.value if user32.GetClipboardFormatNameW(fmt, buf, 256) else ""


def open_clipboard(hwnd, attempts=25):
    for _ in range(attempts):  # another program may be holding it for a moment
        if user32.OpenClipboard(hwnd):
            return True
        time.sleep(0.02)
    return False


def global_from_bytes(data):
    h = kernel32.GlobalAlloc(GMEM_MOVEABLE, max(len(data), 1))
    if not h:
        raise MemoryError("GlobalAlloc")
    p = kernel32.GlobalLock(h)
    ctypes.memmove(p, data, len(data))
    kernel32.GlobalUnlock(h)
    return h


def set_bytes(fmt, data):
    h = global_from_bytes(data)
    if not user32.SetClipboardData(fmt, h):
        kernel32.GlobalFree(h)
        return False
    return True


def text_bytes(text):
    return text.encode("utf-16-le") + b"\x00\x00"


def read_formats():
    """Must be called with the clipboard open. Returns [(fmt, bytes)] for every copyable format."""
    out = []
    fmt = user32.EnumClipboardFormats(0)
    while fmt:
        if fmt not in _NOT_MEMORY and not (0x200 <= fmt <= 0x3FF) and format_name(fmt) not in _SKIP_NAMES:
            h = user32.GetClipboardData(fmt)
            if h:
                p = kernel32.GlobalLock(h)
                if p:
                    try:
                        out.append((fmt, ctypes.string_at(p, kernel32.GlobalSize(h))))
                    finally:
                        kernel32.GlobalUnlock(h)
        fmt = user32.EnumClipboardFormats(fmt)
    return out


class PasteResult:
    def __init__(self):
        self.read = False       # the target program asked for the text
        self.restored = False   # the previous clipboard came back
        self.kept = False       # the text was left on the clipboard (paste not confirmed)
        self.error = None
        self.read_after = None  # seconds from Ctrl+V to the read

    def __repr__(self):
        return f"PasteResult(read={self.read}, restored={self.restored}, kept={self.kept}, error={self.error})"


class ClipboardPaster:
    def __init__(self, read_timeout=1.5, restore_delay=0.6):
        self.read_timeout = read_timeout
        self.restore_delay = restore_delay
        self.hwnd = None
        self._proc = WNDPROC(self._wndproc)
        self._ready = threading.Event()
        self._lock = threading.Lock()
        self._job = None
        self._text = ""
        self._private = []

    # --- public, any thread ---------------------------------------------------------------------
    def start(self):
        self._thread = threading.Thread(target=self._run, name="clipboard", daemon=True)
        self._thread.start()
        self._ready.wait(5)

    def stop(self):
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
            self._thread.join(3)

    def paste(self, text, send_keys=True):
        with self._lock:  # one paste at a time
            job = {"text": text, "send": send_keys, "result": PasteResult(), "done": threading.Event()}
            self._job = job
            user32.PostMessageW(self.hwnd, WM_APP_PASTE, 0, 0)
            if not job["done"].wait(self.read_timeout + self.restore_delay + 5):
                job["result"].error = "timeout"
            return job["result"]

    # --- clipboard thread -----------------------------------------------------------------------
    def _run(self):
        cls = f"DitadoClipboard{id(self)}"
        hinst = register_window_class(cls, self._proc)
        self.hwnd = user32.CreateWindowExW(0, cls, "Ditado clipboard", 0, 0, 0, 0, 0, HWND_MESSAGE, None, hinst, None)
        self._private = [user32.RegisterClipboardFormatW(n) for n in PRIVATE_FORMATS]
        self._ready.set()
        run_message_loop()

    def _finish(self):
        job, self._job = self._job, None
        if job:
            job["done"].set()

    def _begin(self):
        job = self._job
        if job is None:
            return
        res = job["result"]
        if not open_clipboard(self.hwnd):
            res.error = "clipboard ocupado"
            return self._finish()
        try:
            job["snapshot"] = read_formats()
            self._text = job["text"]
            user32.EmptyClipboard()
            user32.SetClipboardData(CF_UNICODETEXT, None)  # delayed: rendered on first read
            self._mark_private()
        finally:
            user32.CloseClipboard()
        job["sent_at"] = time.perf_counter()
        if job["send"]:
            send_inputs([key_input(VK_CONTROL, scan=0x1D, extra=OWN_INPUT_TAG),
                         key_input(VK_V, scan=0x2F, extra=OWN_INPUT_TAG),
                         key_input(VK_V, up=True, scan=0x2F, extra=OWN_INPUT_TAG),
                         key_input(VK_CONTROL, up=True, scan=0x1D, extra=OWN_INPUT_TAG)])
        user32.SetTimer(self.hwnd, TIMER_READ, int(self.read_timeout * 1000), None)

    def _mark_private(self):
        exclude, history, cloud = self._private
        set_bytes(exclude, struct.pack("<I", 0))
        set_bytes(history, struct.pack("<I", 0))
        set_bytes(cloud, struct.pack("<I", 0))

    def _render(self):
        """WM_RENDERFORMAT: someone is reading our text right now."""
        set_bytes(CF_UNICODETEXT, text_bytes(self._text))
        job = self._job
        if job and not job["result"].read:
            job["result"].read = True
            job["result"].read_after = time.perf_counter() - job.get("sent_at", time.perf_counter())
            user32.KillTimer(self.hwnd, TIMER_READ)
            user32.SetTimer(self.hwnd, TIMER_RESTORE, int(self.restore_delay * 1000), None)

    def _read_timed_out(self):
        user32.KillTimer(self.hwnd, TIMER_READ)
        job = self._job
        if job is None:
            return
        # Nobody took the paste. Leave the text there, rendered, so a manual Ctrl+V works.
        if open_clipboard(self.hwnd):
            try:
                if user32.GetClipboardOwner() == self.hwnd:
                    set_bytes(CF_UNICODETEXT, text_bytes(self._text))
                    job["result"].kept = True
            finally:
                user32.CloseClipboard()
        self._finish()

    def _restore(self):
        user32.KillTimer(self.hwnd, TIMER_RESTORE)
        job = self._job
        if job is None:
            return
        if user32.GetClipboardOwner() != self.hwnd:
            return self._finish()  # the user copied something new meanwhile: theirs wins
        if open_clipboard(self.hwnd):
            try:
                user32.EmptyClipboard()
                snapshot = job.get("snapshot") or []
                for fmt, data in snapshot:
                    set_bytes(fmt, data)
                if snapshot:
                    # It is already in the history once; do not add it a second time.
                    present = {f for f, _ in snapshot}
                    if self._private[0] not in present:
                        set_bytes(self._private[0], struct.pack("<I", 0))
                job["result"].restored = True
            finally:
                user32.CloseClipboard()
        self._finish()

    def _wndproc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_APP_PASTE:
                self._begin()
                return 0
            if msg == WM_RENDERFORMAT:
                if wparam == CF_UNICODETEXT:
                    self._render()
                return 0
            if msg == WM_RENDERALLFORMATS:
                if open_clipboard(hwnd, attempts=5):
                    try:
                        if user32.GetClipboardOwner() == hwnd:
                            set_bytes(CF_UNICODETEXT, text_bytes(self._text))
                    finally:
                        user32.CloseClipboard()
                return 0
            if msg == WM_TIMER:
                if wparam == TIMER_READ:
                    self._read_timed_out()
                elif wparam == TIMER_RESTORE:
                    self._restore()
                return 0
            if msg == WM_CLOSE:
                user32.DestroyWindow(hwnd)
                return 0
            if msg == WM_DESTROY:
                self._finish()
                user32.PostQuitMessage(0)
                return 0
        except Exception as e:  # never let an exception cross the Win32 boundary
            if self._job:
                self._job["result"].error = repr(e)
                self._finish()
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)
