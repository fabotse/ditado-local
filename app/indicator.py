"""A small pill at the bottom of the screen: red while recording, amber while transcribing.

It never takes focus (WS_EX_NOACTIVATE, shown with SW_SHOWNOACTIVATE) and lets the mouse pass
through it (WS_EX_TRANSPARENT), so the field you are dictating into keeps the cursor.
"""
import ctypes
import threading
from ctypes import wintypes as w

from win32 import (HWND_TOPMOST, LWA_ALPHA, PAINTSTRUCT, SW_HIDE, SW_SHOWNOACTIVATE, SWP_NOACTIVATE,
                   SWP_SHOWWINDOW, WM_APP, WM_CLOSE, WM_DESTROY, WM_PAINT, WM_TIMER, WNDPROC, WS_EX_LAYERED,
                   WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW, WS_EX_TOPMOST, WS_EX_TRANSPARENT, WS_POPUP, gdi32,
                   register_window_class, rgb, run_message_loop, user32)

WM_APP_STATE = WM_APP + 20
TIMER_ANIM, TIMER_HIDE = 1, 2
SPI_GETWORKAREA = 0x0030
DT_SINGLELINE_VCENTER_LEFT = 0x20 | 0x4 | 0x0
TRANSPARENT_BK = 1

HIDDEN, RECORDING, BUSY, MESSAGE = "hidden", "recording", "busy", "message"
_COLORS = {RECORDING: rgb(232, 64, 64), BUSY: rgb(240, 176, 48), MESSAGE: rgb(120, 170, 255)}
_LABELS = {RECORDING: "Gravando", BUSY: "Transcrevendo"}


class Indicator:
    def __init__(self, level_source=None):
        self.level_source = level_source or (lambda: 0.0)
        self.state = HIDDEN
        self.message = ""
        self.hwnd = None
        self._proc = WNDPROC(self._wndproc)
        self._ready = threading.Event()
        self._peak = 0.0

    def start(self):
        self._thread = threading.Thread(target=self._run, name="indicator", daemon=True)
        self._thread.start()
        self._ready.wait(5)

    def stop(self):
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
            self._thread.join(3)

    def set(self, state, message="", seconds=2.5):
        """Thread-safe. MESSAGE hides itself after `seconds`."""
        self.state, self.message, self._message_seconds = state, message, seconds
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_APP_STATE, 0, 0)

    # --- UI thread ------------------------------------------------------------------------------
    def _run(self):
        try:
            user32.SetProcessDpiAwarenessContext(w.HANDLE(-4))  # per-monitor v2, crisp text
        except Exception:
            pass
        scale = user32.GetDpiForSystem() / 96.0
        self.width, self.height = int(250 * scale), int(44 * scale)
        self.scale = scale
        cls = f"DitadoIndicator{id(self)}"
        hinst = register_window_class(cls, self._proc)
        ex = WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TRANSPARENT | WS_EX_LAYERED
        work = w.RECT()
        user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(work), 0)
        x = work.left + (work.right - work.left - self.width) // 2
        y = work.bottom - self.height - int(24 * scale)
        self.hwnd = user32.CreateWindowExW(ex, cls, "Ditado", WS_POPUP, x, y, self.width, self.height,
                                           None, None, hinst, None)
        user32.SetLayeredWindowAttributes(self.hwnd, 0, 235, LWA_ALPHA)
        rgn = gdi32.CreateRoundRectRgn(0, 0, self.width + 1, self.height + 1, self.height, self.height)
        user32.SetWindowRgn(self.hwnd, rgn, True)
        self._font = gdi32.CreateFontW(-int(16 * scale), 0, 0, 0, 600, 0, 0, 0, 0, 0, 0, 5, 0, "Segoe UI")
        self._bg = gdi32.CreateSolidBrush(rgb(28, 28, 32))
        self._bar_bg = gdi32.CreateSolidBrush(rgb(60, 60, 68))
        self._ready.set()
        run_message_loop()

    def _apply_state(self):
        user32.KillTimer(self.hwnd, TIMER_HIDE)
        if self.state == HIDDEN:
            user32.KillTimer(self.hwnd, TIMER_ANIM)
            user32.ShowWindow(self.hwnd, SW_HIDE)
            return
        user32.SetWindowPos(self.hwnd, HWND_TOPMOST, 0, 0, 0, 0, 0x1 | 0x2 | SWP_NOACTIVATE | SWP_SHOWWINDOW)
        user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
        if self.state == RECORDING:
            user32.SetTimer(self.hwnd, TIMER_ANIM, 50, None)
        else:
            user32.KillTimer(self.hwnd, TIMER_ANIM)
        if self.state == MESSAGE:
            user32.SetTimer(self.hwnd, TIMER_HIDE, int(self._message_seconds * 1000), None)
        user32.InvalidateRect(self.hwnd, None, True)

    def _paint(self):
        ps = PAINTSTRUCT()
        hdc = user32.BeginPaint(self.hwnd, ctypes.byref(ps))
        s = self.scale
        rect = w.RECT(0, 0, self.width, self.height)
        user32.FillRect(hdc, ctypes.byref(rect), self._bg)
        color = _COLORS.get(self.state, rgb(200, 200, 200))
        dot = gdi32.CreateSolidBrush(color)
        old_brush = gdi32.SelectObject(hdc, dot)
        old_pen = gdi32.SelectObject(hdc, gdi32.GetStockObject(8))  # NULL_PEN
        cy, r = self.height // 2, int(6 * s)
        gdi32.Ellipse(hdc, int(18 * s) - r, cy - r, int(18 * s) + r, cy + r)
        gdi32.SelectObject(hdc, old_pen)
        gdi32.SelectObject(hdc, old_brush)
        gdi32.DeleteObject(dot)
        old_font = gdi32.SelectObject(hdc, self._font)
        gdi32.SetBkMode(hdc, TRANSPARENT_BK)
        gdi32.SetTextColor(hdc, rgb(240, 240, 240))
        label = self.message if self.state == MESSAGE else _LABELS.get(self.state, "")
        text_right = self.width - int(16 * s) if self.state != RECORDING else self.width - int(86 * s)
        trect = w.RECT(int(34 * s), 0, text_right, self.height)
        user32.DrawTextW(hdc, label, -1, ctypes.byref(trect), DT_SINGLELINE_VCENTER_LEFT | 0x8000)  # end ellipsis
        gdi32.SelectObject(hdc, old_font)
        if self.state == RECORDING:  # live microphone level
            level = min(1.0, self.level_source() * 8)
            self._peak = max(level, self._peak * 0.85)
            x0, x1 = self.width - int(76 * s), self.width - int(18 * s)
            bar = w.RECT(x0, cy - int(3 * s), x1, cy + int(3 * s))
            user32.FillRect(hdc, ctypes.byref(bar), self._bar_bg)
            bar.right = x0 + int((x1 - x0) * self._peak)
            fill = gdi32.CreateSolidBrush(color)
            user32.FillRect(hdc, ctypes.byref(bar), fill)
            gdi32.DeleteObject(fill)
        user32.EndPaint(self.hwnd, ctypes.byref(ps))

    def _wndproc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_APP_STATE:
                self._apply_state()
                return 0
            if msg == WM_PAINT:
                self._paint()
                return 0
            if msg == WM_TIMER:
                if wparam == TIMER_ANIM:
                    user32.InvalidateRect(hwnd, None, False)
                elif wparam == TIMER_HIDE:
                    self.state = HIDDEN
                    self._apply_state()
                return 0
            if msg == WM_CLOSE:
                user32.DestroyWindow(hwnd)
                return 0
            if msg == WM_DESTROY:
                user32.PostQuitMessage(0)
                return 0
        except Exception:
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)
