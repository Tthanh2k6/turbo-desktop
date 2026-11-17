"""Input lock for real (non-UIA) input: swallow the owner's physical keyboard/mouse while the AI types or clicks,
so the owner cannot knock the action off course. No admin rights: low-level hooks (WH_KEYBOARD_LL / WH_MOUSE_LL)
on one dedicated thread with a message loop. Injected events (our own SendInput) pass through.

Hard floor (code, not configurable, not switchable off in rules):
  - Ctrl+Alt+Shift+K seen by the hook: STOP file + release.
  - Esc pressed 3 times within 1.5 s: release, `owner_took_over`.
  - A maximum lock time per acquire (default 60 s, clamped to 5..300): auto release.
  - Always released on exit / in `finally`. A banner is shown for as long as the lock is held.
  - Ctrl+Alt+Del cannot be blocked by any user-mode program (Windows guarantees it).
  - A hard kill of the process removes the hooks and every window with it (they belong to the process); see
    test_hard_kill_takes_hooks_banner_and_glow_with_it.
"""
from __future__ import annotations

import atexit
import ctypes
import threading
import time
from contextlib import contextmanager
from ctypes import wintypes

from . import security as sec

BANNER_TEXT = "AI đang điều khiển máy · bàn phím/chuột tạm khoá · Esc ×3 để lấy lại · Ctrl+Alt+Shift+K để dừng"
END_TEXT = "Đã trả lại bàn phím và chuột cho bạn"
BANNER_CLASS = "TurboDesktopBanner"

LLKHF_INJECTED = 0x10
LLMHF_INJECTED = 0x01
VK_ESCAPE, VK_K = 0x1B, 0x4B
CTRL = {0x11, 0xA2, 0xA3}
ALT = {0x12, 0xA4, 0xA5}
SHIFT = {0x10, 0xA0, 0xA1}


# ---------------------------------------------------------------- pure logic (unit-tested with fake flags)

class Policy:
    """Decides, for each low-level event, whether to swallow it and whether it triggers an escape hatch."""

    def __init__(self, now=time.monotonic, esc_presses=3, esc_window=1.5):
        self.now = now
        self.esc_presses = esc_presses
        self.esc_window = esc_window
        self.mods = {"ctrl": False, "alt": False, "shift": False}
        self.esc_times: list[float] = []
        self.esc_down = False
        self.physical_events = 0
        self.injected_events = 0

    def key(self, vk: int, down: bool, flags: int) -> tuple[bool, str | None]:
        """-> (swallow, action) with action None | 'stop' | 'takeover'."""
        if flags & LLKHF_INJECTED:
            self.injected_events += 1
            return False, None
        self.physical_events += 1
        for name, group in (("ctrl", CTRL), ("alt", ALT), ("shift", SHIFT)):
            if vk in group:
                self.mods[name] = down
        if down and vk == VK_K and all(self.mods.values()):
            return True, "stop"
        if vk == VK_ESCAPE:
            if down and not self.esc_down:
                t = self.now()
                self.esc_times = [x for x in self.esc_times if t - x <= self.esc_window] + [t]
                if len(self.esc_times) >= self.esc_presses:
                    self.esc_times.clear()
                    self.esc_down = True
                    return True, "takeover"
            self.esc_down = down
        return True, None

    def mouse(self, flags: int) -> bool:
        """-> swallow?"""
        if flags & LLMHF_INJECTED:
            self.injected_events += 1
            return False
        self.physical_events += 1
        return True


def clamp_seconds(v) -> float:
    try:
        return max(5.0, min(300.0, float(v)))
    except (TypeError, ValueError):
        return 60.0


# ---------------------------------------------------------------- windows plumbing

u32 = ctypes.WinDLL("user32", use_last_error=True)
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
g32 = ctypes.WinDLL("gdi32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("pt", wintypes.POINT), ("mouseData", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HANDLE),
                ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH), ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR)]


class PAINTSTRUCT(ctypes.Structure):
    _fields_ = [("hdc", wintypes.HDC), ("fErase", wintypes.BOOL), ("rcPaint", wintypes.RECT), ("fRestore", wintypes.BOOL),
                ("fIncUpdate", wintypes.BOOL), ("rgbReserved", ctypes.c_byte * 32)]


u32.SetWindowsHookExW.restype = wintypes.HHOOK
u32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
u32.CallNextHookEx.restype = LRESULT
u32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
u32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
u32.DefWindowProcW.restype = LRESULT
u32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
u32.CreateWindowExW.restype = wintypes.HWND
u32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
u32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
u32.SetTimer.argtypes = [wintypes.HWND, ctypes.c_size_t, wintypes.UINT, ctypes.c_void_p]
u32.KillTimer.argtypes = [wintypes.HWND, ctypes.c_size_t]
u32.BeginPaint.argtypes = [wintypes.HWND, ctypes.POINTER(PAINTSTRUCT)]
u32.EndPaint.argtypes = [wintypes.HWND, ctypes.POINTER(PAINTSTRUCT)]
u32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
u32.FillRect.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.HBRUSH]
u32.DrawTextW.argtypes = [wintypes.HDC, wintypes.LPCWSTR, ctypes.c_int, ctypes.POINTER(wintypes.RECT), wintypes.UINT]
u32.InvalidateRect.argtypes = [wintypes.HWND, ctypes.c_void_p, wintypes.BOOL]
u32.DestroyWindow.argtypes = [wintypes.HWND]
u32.SetLayeredWindowAttributes.argtypes = [wintypes.HWND, wintypes.COLORREF, ctypes.c_ubyte, wintypes.DWORD]
u32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
g32.CreateSolidBrush.restype = wintypes.HBRUSH
g32.CreateFontW.restype = wintypes.HANDLE
g32.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
g32.SetTextColor.argtypes = [wintypes.HDC, wintypes.COLORREF]
g32.SetBkMode.argtypes = [wintypes.HDC, ctypes.c_int]
g32.DeleteObject.argtypes = [wintypes.HANDLE]
k32.GetModuleHandleW.restype = wintypes.HMODULE
u32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
u32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
u32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
u32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
u32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
u32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]

WM_PAINT, WM_TIMER, WM_DESTROY, WM_APP = 0x000F, 0x0113, 0x0002, 0x8000
WM_RELEASE = WM_APP + 1
WS_POPUP, WS_VISIBLE = 0x80000000, 0x10000000
WS_EX_TOPMOST, WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW = 0x8, 0x80000, 0x20, 0x8000000, 0x80
LWA_ALPHA = 2
T_MAX, T_END, T_LINGER = 1, 2, 3


class InputLock:
    """One lock object per process. acquire()/release() are idempotent; hold() is a nesting-safe context manager."""

    def __init__(self, banner_class=BANNER_CLASS, linger_ms=2500):
        self._cv = threading.Condition()
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._done = threading.Event()
        self._done.set()
        self.locked = False
        self.taken_over = False
        self.stopped = False
        self.reason = ""
        self.banner_hwnd = 0
        self.policy = Policy()
        self.max_seconds = 60.0
        self.whole_task = False
        self.linger = 8.0
        self.last_touch = time.monotonic()
        self.linger_ms = linger_ms
        self.banner_class = banner_class
        self._text = BANNER_TEXT
        self._depth = 0
        self._hooks: list = []
        self._procs: list = []  # keep ctypes callbacks alive
        atexit.register(self.release, "exit")

    # ------------------------------------------------------------ public API

    def acquire(self, max_seconds=60, whole_task=False) -> bool:
        with self._cv:
            self._depth += 1
            self.last_touch = time.monotonic()
            if self.locked:
                return True
            self.max_seconds = clamp_seconds(max_seconds)
            self.whole_task = whole_task
            self.taken_over = self.stopped = False
            self.reason = ""
            self.policy = Policy()
            self._text = BANNER_TEXT
            self._ready.clear()
            self._done.clear()
            self._thread = threading.Thread(target=self._run, daemon=True, name="inputlock")
            self._thread.start()
        if not self._ready.wait(5) or not self.locked:
            self._depth = max(0, self._depth - 1)
            raise RuntimeError("could not install the input hooks")
        return True

    def release(self, reason="done") -> dict:
        with self._cv:
            self._depth = 0
        if self.locked and self.banner_hwnd:
            self.reason = self.reason or reason
            u32.PostMessageW(self.banner_hwnd, WM_RELEASE, 0, 0)
        t = self._thread
        if t and t is not threading.current_thread():
            self._done.wait(4)  # hooks removed; the end notice may linger a little longer on its own
        return self.info()

    def end_one(self) -> dict:
        """Leave one hold(); in real_input mode this releases, in whole_task mode only at linger/max."""
        with self._cv:
            self._depth = max(0, self._depth - 1)
            last = self._depth == 0
        if last and not self.whole_task:
            return self.release("done")
        return self.info()

    def touch(self):
        self.last_touch = time.monotonic()

    def info(self) -> dict:
        return {"locked": self.locked, "owner_took_over": self.taken_over, "stopped": self.stopped,
                "reason": self.reason, "physical_events_swallowed": self.policy.physical_events,
                "injected_events_passed": self.policy.injected_events}

    @contextmanager
    def hold(self, max_seconds=60, whole_task=False):
        self.acquire(max_seconds, whole_task)
        try:
            yield self
        finally:
            self.end_one()

    # ------------------------------------------------------------ hook thread

    def _escape(self, action):
        if action == "stop":
            try:
                (sec.state_dir() / "STOP").write_text("hotkey Ctrl+Alt+Shift+K seen by the input hook", encoding="utf-8")
            except OSError:
                pass
            self.stopped = True
            self.reason = "stop-hotkey"
        elif action == "takeover":
            self.taken_over = True
            self.reason = "owner-esc-x3"
        self._begin_release()

    def _begin_release(self):
        """Runs on the hook thread: unhook, show the end notice, schedule destruction."""
        if not self.locked:
            return
        self.locked = False
        for h in self._hooks:
            u32.UnhookWindowsHookEx(h)
        self._hooks = []
        u32.KillTimer(self.banner_hwnd, T_MAX)
        u32.KillTimer(self.banner_hwnd, T_LINGER)
        self._text = END_TEXT
        u32.InvalidateRect(self.banner_hwnd, None, True)
        u32.SetTimer(self.banner_hwnd, T_END, self.linger_ms, None)
        self._done.set()

    def _run(self):
        hinst = k32.GetModuleHandleW(None)

        def wndproc(hwnd, msg, wp, lp):
            if msg == WM_PAINT:
                ps = PAINTSTRUCT()
                hdc = u32.BeginPaint(hwnd, ctypes.byref(ps))
                rc = wintypes.RECT()
                u32.GetClientRect(hwnd, ctypes.byref(rc))
                brush = g32.CreateSolidBrush(0x00202080 if self.locked else 0x00406020)  # BGR: dark red / dark green
                u32.FillRect(hdc, ctypes.byref(rc), brush)
                g32.DeleteObject(brush)
                font = g32.CreateFontW(-18, 0, 0, 0, 600, 0, 0, 0, 1, 0, 0, 4, 0, "Segoe UI")
                old = g32.SelectObject(hdc, font)
                g32.SetBkMode(hdc, 1)
                g32.SetTextColor(hdc, 0x00FFFFFF)
                u32.DrawTextW(hdc, self._text, -1, ctypes.byref(rc), 0x25)  # center, vcenter, singleline
                g32.SelectObject(hdc, old)
                g32.DeleteObject(font)
                u32.EndPaint(hwnd, ctypes.byref(ps))
                return 0
            if msg == WM_RELEASE:
                self._begin_release()
                return 0
            if msg == WM_TIMER:
                if wp == T_MAX:
                    self.reason = self.reason or "max-seconds"
                    self._begin_release()
                elif wp == T_LINGER:
                    if self.whole_task and time.monotonic() - self.last_touch > self.linger and self._depth == 0:
                        self.reason = self.reason or "idle-linger"
                        self._begin_release()
                elif wp == T_END:
                    u32.KillTimer(hwnd, T_END)
                    u32.DestroyWindow(hwnd)
                return 0
            if msg == WM_DESTROY:
                u32.PostQuitMessage(0)
                return 0
            return u32.DefWindowProcW(hwnd, msg, wp, lp)

        wp_ref = WNDPROC(wndproc)
        wc = WNDCLASSW()
        wc.lpfnWndProc = wp_ref
        wc.hInstance = hinst
        wc.lpszClassName = self.banner_class
        u32.RegisterClassW(ctypes.byref(wc))  # re-registering after a previous run is harmless (fails with 1410)
        sw = u32.GetSystemMetrics(0)
        width = min(1000, sw)
        hwnd = u32.CreateWindowExW(WS_EX_TOPMOST | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW,
                                   self.banner_class, "turbo-desktop", WS_POPUP, (sw - width) // 2, 0, width, 38,
                                   None, None, hinst, None)
        if not hwnd:
            self._ready.set()
            self._done.set()
            return
        self.banner_hwnd = hwnd
        u32.SetLayeredWindowAttributes(hwnd, 0, 235, LWA_ALPHA)
        u32.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE
        u32.SetWindowPos(hwnd, wintypes.HWND(-1), 0, 0, 0, 0, 0x13)  # topmost, no move/size/activate

        def kb(nCode, wParam, lParam):
            if nCode >= 0 and self.locked:
                k = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                down = wParam in (0x100, 0x104)
                swallow, action = self.policy.key(k.vkCode, down, k.flags)
                if action:
                    self._escape(action)
                if swallow:
                    return 1
            return u32.CallNextHookEx(None, nCode, wParam, lParam)

        def ms(nCode, wParam, lParam):
            if nCode >= 0 and self.locked:
                m = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                if self.policy.mouse(m.flags):
                    return 1
            return u32.CallNextHookEx(None, nCode, wParam, lParam)

        kb_p, ms_p = HOOKPROC(kb), HOOKPROC(ms)
        self._procs = [wp_ref, kb_p, ms_p]
        h1 = u32.SetWindowsHookExW(13, kb_p, hinst, 0)
        h2 = u32.SetWindowsHookExW(14, ms_p, hinst, 0)
        self._hooks = [h for h in (h1, h2) if h]
        if len(self._hooks) < 2:  # without both hooks there is no lock; never pretend
            for h in self._hooks:
                u32.UnhookWindowsHookEx(h)
            self._hooks = []
            u32.DestroyWindow(hwnd)
            self._ready.set()
            self._done.set()
            return
        self.locked = True
        u32.SetTimer(hwnd, T_MAX, int(self.max_seconds * 1000), None)
        u32.SetTimer(hwnd, T_LINGER, 1000, None)
        self._ready.set()
        msg = wintypes.MSG()
        while u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            u32.TranslateMessage(ctypes.byref(msg))
            u32.DispatchMessageW(ctypes.byref(msg))
        self.banner_hwnd = 0
        self.locked = False
        self._done.set()
        u32.UnregisterClassW(self.banner_class, hinst)
