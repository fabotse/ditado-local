"""Hold-to-talk on the right Alt (AltGr), through a low-level keyboard hook that never swallows a key.

On a Portuguese layout the right Alt is AltGr, which Windows delivers as a synthetic Left Ctrl plus
Right Alt. AltGr is also how you type @, EUR, [ ] { } on that layout, so the hotkey cannot steal it:

- the hook only observes; every event goes on to CallNextHookEx untouched;
- pressing right Alt alone and holding it is a dictation;
- if any other key is pressed while it is held (AltGr+2 = @), or a modifier was already held when it
  went down, that press is a key combo: the recording is thrown away and the key works as always;
- a quick tap (under MIN_HOLD) is ignored too.
"""
import ctypes
import queue
import threading
import time

from win32 import (HC_ACTION, HOOKPROC, KBDLLHOOKSTRUCT, LLKHF_INJECTED, LLKHF_UP, VK_CONTROL, VK_LCONTROL,
                   VK_LMENU, VK_LSHIFT, VK_LWIN, VK_MENU, VK_RCONTROL, VK_RMENU, VK_RSHIFT, VK_RWIN, VK_SHIFT,
                   WH_KEYBOARD_LL, WM_QUIT, kernel32, key_is_down, run_message_loop, user32)

# Marks input this app injects itself (the menu mask and Ctrl+V), so the hook can ignore it.
OWN_INPUT_TAG = 0x44544C31  # "DTL1"

MIN_HOLD = 0.25  # seconds; shorter presses are treated as an accidental tap

# Modifiers that, if already held when right Alt goes down, make it a combo (e.g. Shift+AltGr).
_COMBO_MODIFIERS = (VK_SHIFT, VK_LSHIFT, VK_RSHIFT, VK_LMENU, VK_RCONTROL, VK_LWIN, VK_RWIN)
# The Ctrl that AltGr synthesizes (and Ctrl in general) never cancels: it arrives with every AltGr press.
_IGNORED = (VK_CONTROL, VK_LCONTROL, VK_RCONTROL, VK_MENU)

IDLE, HELD, COMBO = "idle", "held", "combo"


class HoldDetector:
    """Pure state machine: feed key events, get back 'start' / 'release' / 'cancel'."""

    def __init__(self, hotkey_vk=VK_RMENU, min_hold=MIN_HOLD, modifier_is_down=None):
        self.hotkey_vk = hotkey_vk
        self.min_hold = min_hold
        self.modifier_is_down = modifier_is_down or (lambda vk: False)
        self.state = IDLE
        self.pressed_at = 0.0

    def feed(self, vk, down, t, own_input=False):
        if own_input:
            return None
        if vk == self.hotkey_vk:
            if down:
                if self.state != IDLE:
                    return None  # autorepeat
                self.pressed_at = t
                if any(self.modifier_is_down(m) for m in _COMBO_MODIFIERS):
                    self.state = COMBO
                    return None
                self.state = HELD
                return "start"
            state, self.state = self.state, IDLE
            if state == HELD:
                return "release" if t - self.pressed_at >= self.min_hold else "cancel"
            return None
        if down and self.state == HELD and vk not in _IGNORED:
            self.state = COMBO
            return "cancel"
        return None


class KeyboardHook:
    """Runs WH_KEYBOARD_LL on its own thread and turns key events into HoldDetector events.

    The callback does the minimum (a state update and a queue put) and always passes the event on.
    """

    def __init__(self, on_event, observer=None, min_hold=MIN_HOLD):
        self.on_event = on_event
        self.observer = observer  # optional: observer(vk, down, flags, extra, perf_counter) for tests
        self.detector = HoldDetector(min_hold=min_hold, modifier_is_down=key_is_down)
        self._proc = HOOKPROC(self._callback)
        self._thread = None
        self._thread_id = 0
        self._ready = threading.Event()
        self._hook = None
        self._events = queue.SimpleQueue()

    def _callback(self, code, wparam, lparam):
        if code == HC_ACTION:
            try:
                k = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                now = time.perf_counter()
                down = not (k.flags & LLKHF_UP)
                own = bool(k.flags & LLKHF_INJECTED) and k.dwExtraInfo == OWN_INPUT_TAG
                if self.observer:
                    self.observer(k.vkCode, down, k.flags, k.dwExtraInfo, now)
                ev = self.detector.feed(k.vkCode, down, now, own_input=own)
                if ev:
                    self._events.put((ev, now))
            except Exception:  # a hook must never raise back into Windows
                pass
        return user32.CallNextHookEx(None, code, wparam, lparam)

    def _run(self):
        self._thread_id = kernel32.GetCurrentThreadId()
        self._hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, kernel32.GetModuleHandleW(None), 0)
        self._ready.set()
        if not self._hook:
            return
        run_message_loop()
        user32.UnhookWindowsHookEx(self._hook)
        self._hook = None

    def _dispatch(self):
        while True:
            item = self._events.get()
            if item is None:
                return
            self.on_event(*item)

    def start(self):
        self._dispatcher = threading.Thread(target=self._dispatch, name="hotkey-dispatch", daemon=True)
        self._dispatcher.start()
        self._thread = threading.Thread(target=self._run, name="keyboard-hook", daemon=True)
        self._thread.start()
        self._ready.wait(5)
        if not self._hook:
            raise OSError(f"SetWindowsHookExW falhou (erro {ctypes.get_last_error()})")

    def stop(self):
        if self._thread and self._thread.is_alive():
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            self._thread.join(3)
        self._events.put(None)

    @property
    def installed(self):
        return bool(self._hook)
