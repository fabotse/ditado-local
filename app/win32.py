"""Win32 bindings via ctypes, with explicit argtypes so 64-bit handles are never truncated."""
import ctypes
from ctypes import wintypes as w

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

ULONG_PTR = ctypes.c_size_t
LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, w.WPARAM, w.LPARAM)
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, w.HWND, w.UINT, w.WPARAM, w.LPARAM)

# --- constants -------------------------------------------------------------------------------
WH_KEYBOARD_LL = 13
HC_ACTION = 0
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0100, 0x0101, 0x0104, 0x0105
WM_QUIT, WM_DESTROY, WM_CLOSE, WM_PAINT, WM_TIMER = 0x0012, 0x0002, 0x0010, 0x000F, 0x0113
WM_RENDERFORMAT, WM_RENDERALLFORMATS, WM_DESTROYCLIPBOARD = 0x0305, 0x0306, 0x0307
WM_APP = 0x8000
LLKHF_EXTENDED, LLKHF_INJECTED, LLKHF_UP = 0x01, 0x10, 0x80

VK_SHIFT, VK_CONTROL, VK_MENU = 0x10, 0x11, 0x12
VK_LSHIFT, VK_RSHIFT, VK_LCONTROL, VK_RCONTROL, VK_LMENU, VK_RMENU = 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5
VK_LWIN, VK_RWIN = 0x5B, 0x5C
VK_V = 0x56
VK_MASK = 0xE8  # "unassigned" virtual key: does nothing in any app, used only to break an Alt-alone press

INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP, KEYEVENTF_UNICODE, KEYEVENTF_SCANCODE = 0x1, 0x2, 0x4, 0x8

CF_TEXT, CF_BITMAP, CF_METAFILEPICT, CF_PALETTE, CF_UNICODETEXT, CF_ENHMETAFILE = 1, 2, 3, 9, 13, 14
CF_OWNERDISPLAY, CF_DSPBITMAP, CF_DSPMETAFILEPICT, CF_DSPENHMETAFILE = 0x80, 0x82, 0x83, 0x8E
GMEM_MOVEABLE = 0x0002

WS_POPUP = 0x80000000
WS_EX_TOPMOST, WS_EX_TOOLWINDOW, WS_EX_TRANSPARENT = 0x8, 0x80, 0x20
WS_EX_LAYERED, WS_EX_NOACTIVATE = 0x80000, 0x08000000
SW_HIDE, SW_SHOWNOACTIVATE = 0, 4
HWND_MESSAGE = w.HWND(-3)
HWND_TOPMOST = w.HWND(-1)
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_SHOWWINDOW = 0x1, 0x2, 0x10, 0x40
LWA_ALPHA = 0x2
GWL_EXSTYLE = -20
ERROR_ALREADY_EXISTS = 183


# --- structures ------------------------------------------------------------------------------
class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", w.DWORD), ("scanCode", w.DWORD), ("flags", w.DWORD),
                ("time", w.DWORD), ("dwExtraInfo", ULONG_PTR)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", w.LONG), ("dy", w.LONG), ("mouseData", w.DWORD), ("dwFlags", w.DWORD),
                ("time", w.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", w.WORD), ("wScan", w.WORD), ("dwFlags", w.DWORD), ("time", w.DWORD),
                ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", w.DWORD), ("wParamL", w.WORD), ("wParamH", w.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", w.DWORD), ("u", _INPUTUNION)]


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [("cbSize", w.UINT), ("style", w.UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int), ("hInstance", w.HINSTANCE),
                ("hIcon", w.HICON), ("hCursor", w.HANDLE), ("hbrBackground", w.HBRUSH),
                ("lpszMenuName", w.LPCWSTR), ("lpszClassName", w.LPCWSTR), ("hIconSm", w.HICON)]


class PAINTSTRUCT(ctypes.Structure):
    _fields_ = [("hdc", w.HDC), ("fErase", w.BOOL), ("rcPaint", w.RECT), ("fRestore", w.BOOL),
                ("fIncUpdate", w.BOOL), ("rgbReserved", ctypes.c_byte * 32)]


def _sig(fn, res, *args):
    fn.restype = res
    fn.argtypes = list(args)


# --- user32 ----------------------------------------------------------------------------------
_sig(user32.SetWindowsHookExW, w.HHOOK, ctypes.c_int, HOOKPROC, w.HINSTANCE, w.DWORD)
_sig(user32.UnhookWindowsHookEx, w.BOOL, w.HHOOK)
_sig(user32.CallNextHookEx, LRESULT, w.HHOOK, ctypes.c_int, w.WPARAM, w.LPARAM)
_sig(user32.GetMessageW, w.BOOL, ctypes.POINTER(w.MSG), w.HWND, w.UINT, w.UINT)
_sig(user32.PeekMessageW, w.BOOL, ctypes.POINTER(w.MSG), w.HWND, w.UINT, w.UINT, w.UINT)
_sig(user32.TranslateMessage, w.BOOL, ctypes.POINTER(w.MSG))
_sig(user32.DispatchMessageW, LRESULT, ctypes.POINTER(w.MSG))
_sig(user32.PostThreadMessageW, w.BOOL, w.DWORD, w.UINT, w.WPARAM, w.LPARAM)
_sig(user32.PostMessageW, w.BOOL, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
_sig(user32.SendMessageW, LRESULT, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
_sig(user32.PostQuitMessage, None, ctypes.c_int)
_sig(user32.DefWindowProcW, LRESULT, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
_sig(user32.RegisterClassExW, w.ATOM, ctypes.POINTER(WNDCLASSEXW))
_sig(user32.UnregisterClassW, w.BOOL, w.LPCWSTR, w.HINSTANCE)
_sig(user32.CreateWindowExW, w.HWND, w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD, ctypes.c_int, ctypes.c_int,
     ctypes.c_int, ctypes.c_int, w.HWND, w.HMENU, w.HINSTANCE, w.LPVOID)
_sig(user32.DestroyWindow, w.BOOL, w.HWND)
_sig(user32.ShowWindow, w.BOOL, w.HWND, ctypes.c_int)
_sig(user32.SetWindowPos, w.BOOL, w.HWND, w.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, w.UINT)
_sig(user32.IsWindowVisible, w.BOOL, w.HWND)
_sig(user32.InvalidateRect, w.BOOL, w.HWND, ctypes.c_void_p, w.BOOL)
_sig(user32.BeginPaint, w.HDC, w.HWND, ctypes.POINTER(PAINTSTRUCT))
_sig(user32.EndPaint, w.BOOL, w.HWND, ctypes.POINTER(PAINTSTRUCT))
_sig(user32.FillRect, ctypes.c_int, w.HDC, ctypes.POINTER(w.RECT), w.HBRUSH)
_sig(user32.DrawTextW, ctypes.c_int, w.HDC, w.LPCWSTR, ctypes.c_int, ctypes.POINTER(w.RECT), w.UINT)
_sig(user32.SetLayeredWindowAttributes, w.BOOL, w.HWND, w.COLORREF, w.BYTE, w.DWORD)
_sig(user32.SetWindowRgn, ctypes.c_int, w.HWND, w.HRGN, w.BOOL)
_sig(user32.GetWindowLongPtrW, ctypes.c_ssize_t, w.HWND, ctypes.c_int)
_sig(user32.SetTimer, ctypes.c_size_t, w.HWND, ctypes.c_size_t, w.UINT, ctypes.c_void_p)
_sig(user32.KillTimer, w.BOOL, w.HWND, ctypes.c_size_t)
_sig(user32.SystemParametersInfoW, w.BOOL, w.UINT, w.UINT, ctypes.c_void_p, w.UINT)
_sig(user32.GetDpiForSystem, w.UINT)
_sig(user32.SetProcessDpiAwarenessContext, w.BOOL, w.HANDLE)
_sig(user32.SendInput, w.UINT, w.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
_sig(user32.GetAsyncKeyState, w.SHORT, ctypes.c_int)
_sig(user32.GetForegroundWindow, w.HWND)
_sig(user32.OpenClipboard, w.BOOL, w.HWND)
_sig(user32.CloseClipboard, w.BOOL)
_sig(user32.EmptyClipboard, w.BOOL)
_sig(user32.GetClipboardData, w.HANDLE, w.UINT)
_sig(user32.SetClipboardData, w.HANDLE, w.UINT, w.HANDLE)
_sig(user32.EnumClipboardFormats, w.UINT, w.UINT)
_sig(user32.RegisterClipboardFormatW, w.UINT, w.LPCWSTR)
_sig(user32.GetClipboardOwner, w.HWND)
_sig(user32.GetClipboardSequenceNumber, w.DWORD)

# --- gdi32 -----------------------------------------------------------------------------------
_sig(gdi32.CreateSolidBrush, w.HBRUSH, w.COLORREF)
_sig(gdi32.DeleteObject, w.BOOL, w.HGDIOBJ)
_sig(gdi32.SelectObject, w.HGDIOBJ, w.HDC, w.HGDIOBJ)
_sig(gdi32.SetBkMode, ctypes.c_int, w.HDC, ctypes.c_int)
_sig(gdi32.SetTextColor, w.COLORREF, w.HDC, w.COLORREF)
_sig(gdi32.Ellipse, w.BOOL, w.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int)
_sig(gdi32.CreateRoundRectRgn, w.HRGN, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int)
_sig(gdi32.CreateFontW, w.HFONT, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, w.DWORD,
     w.DWORD, w.DWORD, w.DWORD, w.DWORD, w.DWORD, w.DWORD, w.DWORD, w.LPCWSTR)
_sig(gdi32.GetStockObject, w.HGDIOBJ, ctypes.c_int)

# --- kernel32 --------------------------------------------------------------------------------
_sig(kernel32.GetModuleHandleW, w.HMODULE, w.LPCWSTR)
_sig(kernel32.GetCurrentThreadId, w.DWORD)
_sig(kernel32.GlobalAlloc, w.HGLOBAL, w.UINT, ctypes.c_size_t)
_sig(kernel32.GlobalLock, w.LPVOID, w.HGLOBAL)
_sig(kernel32.GlobalUnlock, w.BOOL, w.HGLOBAL)
_sig(kernel32.GlobalSize, ctypes.c_size_t, w.HGLOBAL)
_sig(kernel32.GlobalFree, w.HGLOBAL, w.HGLOBAL)
_sig(kernel32.CreateMutexW, w.HANDLE, w.LPVOID, w.BOOL, w.LPCWSTR)
_sig(kernel32.CloseHandle, w.BOOL, w.HANDLE)


def rgb(r, g, b):
    return r | (g << 8) | (b << 16)


def key_input(vk, up=False, scan=0, extended=False, extra=0):
    inp = INPUT(type=INPUT_KEYBOARD)
    flags = (KEYEVENTF_KEYUP if up else 0) | (KEYEVENTF_EXTENDEDKEY if extended else 0)
    inp.ki = KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=extra)
    return inp


def send_inputs(inputs):
    arr = (INPUT * len(inputs))(*inputs)
    return user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))


def key_is_down(vk):
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def run_message_loop():
    msg = w.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))


def register_window_class(name, wndproc):
    hinst = kernel32.GetModuleHandleW(None)
    wc = WNDCLASSEXW()
    wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
    wc.lpfnWndProc = wndproc
    wc.hInstance = hinst
    wc.lpszClassName = name
    user32.RegisterClassExW(ctypes.byref(wc))  # re-registering an existing class just fails, harmless
    return hinst
