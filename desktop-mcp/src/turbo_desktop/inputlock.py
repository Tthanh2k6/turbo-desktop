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
import os
import threading
import time
from contextlib import contextmanager
from ctypes import wintypes
from pathlib import Path

from . import security as sec

BANNER_TEXT = "AI đang điều khiển máy · bàn phím/chuột tạm khoá · Esc ×3 để lấy lại · Ctrl+Alt+Shift+K để dừng"
REMOTE_BANNER_TEXT = "AI đang làm việc theo lệnh từ điện thoại · Esc ×3 để lấy lại · Ctrl+Alt+Shift+K để dừng"
SCREEN_VIEW_TEXT = "Điện thoại đang xem màn hình"
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


WM_ACQUIRE = WM_APP + 2
WM_SCREEN_VIEW = WM_APP + 3
HWND_MESSAGE = wintypes.HWND(-3)


REAL_INPUT_LINGER = 8.0
WHOLE_TASK_LINGER = 45.0


def linger_for_mode(whole_task: bool) -> float:
    return WHOLE_TASK_LINGER if whole_task else REAL_INPUT_LINGER


class InputLock:
    """One lock object per process, served by ONE persistent thread (hooks, banner and timers all live on it).
    acquire()/release() are idempotent; hold() is a nesting-safe context manager.

    Field bug 16: an earlier version started a new thread per acquire. A second acquire inside the 2.5 s end-notice
    of the first freed the first thread's callbacks while its window was still alive: the process crashed ("Connection
    closed"). One thread for the life of the process removes the overlap."""

    def __init__(self, banner_class=BANNER_CLASS, linger_ms=2500, state_dir=None, indicator=None, whole_task: bool = False):
        self._cv = threading.Condition()
        self._thread: threading.Thread | None = None
        self._thread_up = threading.Event()
        self._ready = threading.Event()
        self._done = threading.Event()
        self._done.set()
        self.locked = False
        self.taken_over = False
        self.stopped = False
        self.reason = ""
        self.mode = "whole_task" if whole_task else "real_input"
        self.since: float | None = None
        self.remote_task = False
        self.screen_view = False
        self.banner_hwnd = 0
        self.ctrl_hwnd = 0
        self.policy = Policy()
        self.max_seconds = 60.0
        self.whole_task = bool(whole_task)
        self.linger = linger_for_mode(self.whole_task)
        self.last_touch = time.monotonic()
        self.linger_ms = linger_ms
        self.banner_class = banner_class
        self._text = BANNER_TEXT
        self._depth = 0
        self._hooks: list = []
        self._procs: list = []  # ctypes callbacks live as long as the lock object
        self._state_dir = state_dir
        self.indicator = indicator
        atexit.register(self.release, "exit")

    def set_mode(self, whole_task: bool):
        self.whole_task = bool(whole_task)
        self.mode = "whole_task" if self.whole_task else "real_input"
        self.linger = linger_for_mode(self.whole_task)

    # ------------------------------------------------------------ bridge helpers

    def _write_bridge(self):
        d = sec.bridge_dir(self._state_dir)
        if d is None:
            return
        reason = self.reason or ("remote_task" if (self.locked and self.remote_task) else ("real_input" if self.locked else "done"))
        sec.atomic_write_json(d / "input_lock.json", {
            "locked": bool(self.locked),
            "mode": self.mode,
            "since": self.since if self.locked else None,
            "reason": reason,
        })
        if self.indicator is not None:
            self.indicator.state.set_locked(bool(self.locked))
            ind_state = self.indicator.state.bridge_state()
            self.indicator._last_bridge = ind_state
        else:
            ind_state = "input_locked" if self.locked else "idle"
        sec.atomic_write_json(d / "indicator.json", {"state": ind_state})

    def _ensure_thread(self) -> bool:
        with self._cv:
            if self._thread is None or not self._thread.is_alive():
                self._thread_up.clear()
                self._thread = threading.Thread(target=self._run, daemon=True, name="inputlock")
                self._thread.start()
        return self._thread_up.wait(5)

    # ------------------------------------------------------------ public API

    def acquire(self, max_seconds=60, whole_task=False, remote_task=False, banner_text=None, reason="") -> bool:
        with self._cv:
            if remote_task:
                self.remote_task = True
            else:
                self._depth += 1
            self.last_touch = time.monotonic()
            if self.locked:
                if remote_task or whole_task:
                    self.set_mode(True)
                if remote_task:
                    self.max_seconds = max(5.0, float(max_seconds))
                    self._text = banner_text or REMOTE_BANNER_TEXT
                    if reason:
                        self.reason = reason
                    if self.ctrl_hwnd:
                        u32.SetTimer(self.ctrl_hwnd, T_MAX, int(min(self.max_seconds + 2.0, 86400) * 1000), None)
                    if self.banner_hwnd:
                        u32.InvalidateRect(self.banner_hwnd, None, True)
                    self._write_bridge()
                return True
            self.max_seconds = max(5.0, float(max_seconds)) if remote_task else clamp_seconds(max_seconds)
            self.set_mode(bool(whole_task or remote_task))
            self.taken_over = self.stopped = False
            self.reason = reason
            self.since = round(time.time(), 3)
            self.policy = Policy()
            self._text = banner_text or (REMOTE_BANNER_TEXT if remote_task else BANNER_TEXT)
            self._ready.clear()
            self._done.clear()
            if self._thread is None or not self._thread.is_alive():
                self._thread_up.clear()
                self._thread = threading.Thread(target=self._run, daemon=True, name="inputlock")
                self._thread.start()
        if not self._thread_up.wait(5):
            if not remote_task:
                self._depth = max(0, self._depth - 1)
            else:
                self.remote_task = False
            raise RuntimeError("input lock thread did not start")
        u32.PostMessageW(self.ctrl_hwnd, WM_ACQUIRE, 0, 0)
        if not self._ready.wait(5) or not self.locked:
            if not remote_task:
                self._depth = max(0, self._depth - 1)
            else:
                self.remote_task = False
            raise RuntimeError("could not install the input hooks")
        self._write_bridge()
        return True

    def release_remote_task(self, reason="task-ended") -> dict:
        with self._cv:
            self.remote_task = False
            still_real = self._depth > 0
        if still_real and self.locked:
            self.set_mode(False)
            self.reason = ""
            self._text = BANNER_TEXT
            if self.banner_hwnd:
                u32.InvalidateRect(self.banner_hwnd, None, True)
            self._write_bridge()
            return self.info()
        return self.release(reason)

    def release(self, reason="done") -> dict:
        with self._cv:
            self._depth = 0
            self.remote_task = False
        if self.locked:
            self.reason = self.reason or reason
            if self.ctrl_hwnd:
                u32.PostMessageW(self.ctrl_hwnd, WM_RELEASE, 0, 0)
                if self._thread is not threading.current_thread():
                    self._done.wait(4)  # hooks removed; the end notice may linger a little longer on its own
            else:
                self.locked = False
                self.since = None
                self._write_bridge()
        return self.info()

    def end_one(self) -> dict:
        """Leave one hold(); in real_input mode this releases, in whole_task mode only at linger/max."""
        with self._cv:
            self._depth = max(0, self._depth - 1)
            last = self._depth == 0
        if last and not self.whole_task and not self.remote_task:
            return self.release("done")
        return self.info()

    def set_screen_view(self, active: bool, start_thread: bool = True):
        """Show or hide the small 'Điện thoại đang xem màn hình' banner without locking input."""
        self.screen_view = bool(active)
        if self.screen_view:
            if not self.locked:
                self._text = SCREEN_VIEW_TEXT
                if start_thread and self._ensure_thread() and self.ctrl_hwnd:
                    u32.PostMessageW(self.ctrl_hwnd, WM_SCREEN_VIEW, 1, 0)
        else:
            if not self.locked and self._text == SCREEN_VIEW_TEXT:
                self._text = BANNER_TEXT
                if self.ctrl_hwnd:
                    u32.PostMessageW(self.ctrl_hwnd, WM_SCREEN_VIEW, 0, 0)

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

    # ------------------------------------------------------------ the one thread

    def _escape(self, action):
        if action == "stop":
            try:
                (Path(self._state_dir) if self._state_dir else sec.state_dir()).joinpath("STOP").write_text(
                    "hotkey Ctrl+Alt+Shift+K seen by the input hook", encoding="utf-8")
            except OSError:
                pass
            self.stopped = True
            self.reason = "stop-hotkey"
        elif action == "takeover":
            self.taken_over = True
            self.reason = "owner-esc-x3"
            d = sec.bridge_dir(self._state_dir)
            if d is not None:
                sec.atomic_write_json(d / "owner_took_over.json", {"at": round(time.time(), 3)})
        self.remote_task = False
        self._depth = 0
        self._begin_release()

    def _destroy_banner(self):
        if self.banner_hwnd:
            u32.KillTimer(self.ctrl_hwnd, T_END)
            u32.DestroyWindow(self.banner_hwnd)
            self.banner_hwnd = 0

    def _create_banner_window(self, hinst, width_cap=1000, height=38) -> int:
        sw = u32.GetSystemMetrics(0)
        width = min(width_cap, sw)
        hwnd = u32.CreateWindowExW(WS_EX_TOPMOST | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW,
                                   self.banner_class, "turbo-desktop", WS_POPUP, (sw - width) // 2, 0, width, height,
                                   None, None, hinst, None)
        if hwnd:
            self.banner_hwnd = hwnd
            u32.SetLayeredWindowAttributes(hwnd, 0, 235, LWA_ALPHA)
            u32.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE
            u32.SetWindowPos(hwnd, wintypes.HWND(-1), 0, 0, 0, 0, 0x13)  # topmost, no move/size/activate
        return hwnd

    def _begin_release(self):
        """On the thread: unhook, show the end notice, schedule its destruction."""
        if not self.locked:
            self._write_bridge()
            return
        self.locked = False
        self.remote_task = False
        self.since = None
        if self.ctrl_hwnd:
            for h in self._hooks:
                u32.UnhookWindowsHookEx(h)
            self._hooks = []
            u32.KillTimer(self.ctrl_hwnd, T_MAX)
            u32.KillTimer(self.ctrl_hwnd, T_LINGER)
            self._text = END_TEXT
            if self.banner_hwnd:
                u32.InvalidateRect(self.banner_hwnd, None, True)
                u32.SetTimer(self.ctrl_hwnd, T_END, self.linger_ms, None)
        self._write_bridge()
        if self.indicator is not None and (self.taken_over or self.stopped):
            self.indicator.hide_now()
        self._done.set()

    def _do_acquire(self, hinst):
        """On the thread: banner window (replacing any lingering end notice), hooks, timers."""
        self._destroy_banner()
        if not self._create_banner_window(hinst, width_cap=1000, height=38):
            self._ready.set()
            self._done.set()
            return
        h1 = u32.SetWindowsHookExW(13, self._kb_p, hinst, 0)
        h2 = u32.SetWindowsHookExW(14, self._ms_p, hinst, 0)
        self._hooks = [h for h in (h1, h2) if h]
        if len(self._hooks) < 2:  # without both hooks there is no lock; never pretend
            for h in self._hooks:
                u32.UnhookWindowsHookEx(h)
            self._hooks = []
            self._destroy_banner()
            self._ready.set()
            self._done.set()
            return
        self.locked = True
        t_ms = int(min(self.max_seconds + (2.0 if self.remote_task else 0.0), 86400) * 1000)
        u32.SetTimer(self.ctrl_hwnd, T_MAX, t_ms, None)
        u32.SetTimer(self.ctrl_hwnd, T_LINGER, 1000, None)
        self._ready.set()

    def _do_screen_view(self, hinst):
        if self.locked:
            return
        if self.screen_view:
            self._text = SCREEN_VIEW_TEXT
            u32.KillTimer(self.ctrl_hwnd, T_END)
            if not self.banner_hwnd:
                self._create_banner_window(hinst, width_cap=420, height=34)
            else:
                u32.InvalidateRect(self.banner_hwnd, None, True)
        else:
            self._destroy_banner()

    def _run(self):
        hinst = k32.GetModuleHandleW(None)

        def wndproc(hwnd, msg, wp, lp):
            if msg == WM_PAINT and hwnd == self.banner_hwnd:
                ps = PAINTSTRUCT()
                hdc = u32.BeginPaint(hwnd, ctypes.byref(ps))
                rc = wintypes.RECT()
                u32.GetClientRect(hwnd, ctypes.byref(rc))
                color = 0x00202080 if self.locked else (0x00604020 if self._text == SCREEN_VIEW_TEXT else 0x00406020)
                brush = g32.CreateSolidBrush(color)
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
            if hwnd == self.ctrl_hwnd:
                if msg == WM_ACQUIRE:
                    self._do_acquire(hinst)
                    return 0
                if msg == WM_RELEASE:
                    self._begin_release()
                    return 0
                if msg == WM_SCREEN_VIEW:
                    self._do_screen_view(hinst)
                    return 0
                if msg == WM_TIMER:
                    if wp == T_MAX:
                        self.reason = self.reason or ("max-minutes" if self.remote_task else "max-seconds")
                        self._begin_release()
                    elif wp == T_LINGER:
                        if self.whole_task and not self.remote_task and time.monotonic() - self.last_touch > self.linger and self._depth == 0:
                            self.reason = self.reason or "idle-linger"
                            self._begin_release()
                    elif wp == T_END:
                        if self.screen_view and not self.locked:
                            self._do_screen_view(hinst)
                        else:
                            self._destroy_banner()
                    return 0
            return u32.DefWindowProcW(hwnd, msg, wp, lp)

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

        self._wp = WNDPROC(wndproc)
        self._kb_p, self._ms_p = HOOKPROC(kb), HOOKPROC(ms)
        self._procs = [self._wp, self._kb_p, self._ms_p]   # referenced for the whole life of the object
        wc = WNDCLASSW()
        wc.lpfnWndProc = self._wp
        wc.hInstance = hinst
        wc.lpszClassName = self.banner_class
        u32.RegisterClassW(ctypes.byref(wc))
        self.ctrl_hwnd = u32.CreateWindowExW(0, self.banner_class, "turbo-desktop-ctrl", 0, 0, 0, 0, 0, HWND_MESSAGE, None, hinst, None)
        self._thread_up.set()
        msg = wintypes.MSG()
        while u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            u32.TranslateMessage(ctypes.byref(msg))
            u32.DispatchMessageW(ctypes.byref(msg))


# ---------------------------------------------------------------- state-dir bridge & whole-task watcher

_DEFAULT_BRIDGE: "StateBridge | None" = None


class StateBridge:
    """Watches TURBO_DESKTOP_STATE_DIR once per second (on a companion thread, never installing a second hook thread)
    and synchronises input_lock.json, indicator.json, RELEASE, task_active.json, owner_took_over.json and screen_view.json.
    Lock and indicator objects can be mocked or injected in unit tests."""

    def __init__(self, lock=None, indicator=None, state_dir: Path | str | None = None,
                 now=time.time, period: float = 1.0, allow_windows: bool = True):
        self.lock = lock
        self.indicator = indicator
        self.state_dir = Path(state_dir) if state_dir is not None else None
        self.now = now
        self.period = period
        self.allow_windows = allow_windows
        self.task_locked = False
        self.screen_view_active = False
        self.banner_text = ""
        self._task_id = None
        self._task_since: float | None = None
        self._ignored_sig = None
        self._last_lock_snapshot = None
        self._last_ind_state = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def active_dir(self) -> Path | None:
        return sec.bridge_dir(self.state_dir)

    def _lock_enabled(self) -> bool:
        return os.environ.get("TURBO_DESKTOP_INPUT_LOCK", "1") != "0"

    def _real_input_holding(self) -> bool:
        if self.lock is None:
            return False
        if getattr(self.lock, "_depth", 0) > 0 or getattr(self.lock, "real_input_active", False):
            return True
        if getattr(self.lock, "locked", False) and not self.task_locked and not getattr(self.lock, "remote_task", False):
            return True
        return False

    def _set_ind_locked(self, v: bool):
        if self.indicator is None:
            return
        if hasattr(self.indicator, "locked"):
            self.indicator.locked(v)
        elif hasattr(self.indicator, "set_locked"):
            self.indicator.set_locked(v)
        elif hasattr(self.indicator, "state"):
            self.indicator.state.set_locked(v)

    def _set_ind_real(self, v: bool):
        if self.indicator is None:
            return
        if hasattr(self.indicator, "real_input"):
            self.indicator.real_input(v)
        elif hasattr(self.indicator, "set_real_input"):
            self.indicator.set_real_input(v)
        elif hasattr(self.indicator, "state"):
            self.indicator.state.set_real_input(v)

    def _do_acquire_task(self, max_seconds: float, since: float):
        self.banner_text = REMOTE_BANNER_TEXT
        if not self._lock_enabled():
            self._set_ind_real(True)
            return
        self._set_ind_locked(True)
        if self.lock is None:
            return
        if not isinstance(self.lock, InputLock) or self.allow_windows:
            try:
                self.lock.acquire(max_seconds=max_seconds, whole_task=True, remote_task=True,
                                  banner_text=REMOTE_BANNER_TEXT, reason="remote_task")
            except TypeError:
                try:
                    self.lock.acquire(max_seconds, True)
                except TypeError:
                    self.lock.acquire()
        for k, v in (("locked", True), ("whole_task", True), ("remote_task", True), ("mode", "whole_task"),
                     ("since", since), ("reason", "remote_task"), ("_text", REMOTE_BANNER_TEXT), ("max_seconds", max_seconds)):
            try:
                setattr(self.lock, k, v)
            except Exception:
                pass

    def _do_release(self, reason: str, respect_real_input: bool = False):
        if respect_real_input and self._real_input_holding():
            self.task_locked = False
            if self.lock is not None:
                if hasattr(self.lock, "release_remote_task") and (not isinstance(self.lock, InputLock) or self.allow_windows):
                    self.lock.release_remote_task(reason)
                for k, v in (("remote_task", False), ("whole_task", False), ("mode", "real_input"),
                             ("reason", "real_input"), ("_text", BANNER_TEXT)):
                    try:
                        setattr(self.lock, k, v)
                    except Exception:
                        pass
            self.banner_text = BANNER_TEXT
            self.sync_files(force=True)
            return
        self.task_locked = False
        self._task_id = None
        self._task_since = None
        self._set_ind_locked(False)
        self._set_ind_real(False)
        if self.lock is not None:
            if not isinstance(self.lock, InputLock) or self.allow_windows or getattr(self.lock, "ctrl_hwnd", 0):
                if respect_real_input and hasattr(self.lock, "release_remote_task"):
                    self.lock.release_remote_task(reason)
                elif hasattr(self.lock, "release"):
                    try:
                        self.lock.release(reason)
                    except TypeError:
                        self.lock.release()
            for k, v in (("locked", False), ("remote_task", False), ("since", None), ("reason", reason)):
                try:
                    setattr(self.lock, k, v)
                except Exception:
                    pass
            if self.screen_view_active:
                if hasattr(self.lock, "set_screen_view"):
                    self.lock.set_screen_view(True, start_thread=self.allow_windows)
                else:
                    try:
                        self.lock._text = SCREEN_VIEW_TEXT
                    except Exception:
                        pass
        self.banner_text = SCREEN_VIEW_TEXT if self.screen_view_active else ""
        self.sync_files(force=True, reason_override=reason)

    def takeover(self):
        """Esc x3 while held: release lock and write <state>/owner_took_over.json = {"at": epoch}."""
        d = self.active_dir()
        at = round(float(self.now()), 3)
        if d is not None:
            tf = d / "task_active.json"
            if tf.exists():
                self._ignored_sig = self._sig(sec.read_json_safe(tf))
            sec.atomic_write_json(d / "owner_took_over.json", {"at": at})
        if self.lock is not None:
            try:
                self.lock.taken_over = True
            except Exception:
                pass
        if self.indicator is not None and hasattr(self.indicator, "hide_now"):
            self.indicator.hide_now()
        self._do_release("owner-esc-x3", respect_real_input=False)

    @staticmethod
    def _sig(data: dict | None):
        if not isinstance(data, dict):
            return None
        if data.get("task") is not None or data.get("since") is not None:
            return (data.get("task"), data.get("since"))
        return ("anon", data.get("heartbeat"))

    def _compute_indicator_state(self, locked: bool) -> str:
        if locked:
            return "input_locked"
        if self.task_locked and not self._lock_enabled():
            return "acting"
        if self.indicator is not None:
            st_obj = getattr(self.indicator, "state", self.indicator)
            if hasattr(st_obj, "bridge_state"):
                return st_obj.bridge_state()
            if getattr(st_obj, "real_active", False) or getattr(st_obj, "acting", False):
                return "acting"
        if getattr(self.lock, "real_input_active", False):
            return "acting"
        return "idle"

    def sync_files(self, force: bool = False, reason_override: str | None = None):
        d = self.active_dir()
        if d is None:
            return
        locked = bool(getattr(self.lock, "locked", False)) if self.lock is not None else (self.task_locked and self._lock_enabled())
        mode = getattr(self.lock, "mode", None) or ("whole_task" if (self.task_locked or getattr(self.lock, "whole_task", False)) else "real_input")
        since = (getattr(self.lock, "since", None) or self._task_since or round(float(self.now()), 3)) if locked else None
        reason = reason_override or getattr(self.lock, "reason", "") or ("remote_task" if self.task_locked else ("real_input" if locked else "done"))
        snap = (locked, mode, since, reason)
        if force or snap != self._last_lock_snapshot or not (d / "input_lock.json").exists():
            self._last_lock_snapshot = snap
            sec.atomic_write_json(d / "input_lock.json", {
                "locked": locked,
                "mode": mode,
                "since": since,
                "reason": reason,
            })
        ind_state = self._compute_indicator_state(locked)
        ind_last = getattr(self.indicator, "_last_bridge", self._last_ind_state) if self.indicator is not None else self._last_ind_state
        if force or ind_state != self._last_ind_state or ind_state != ind_last or not (d / "indicator.json").exists():
            self._last_ind_state = ind_state
            if self.indicator is not None:
                try:
                    self.indicator._last_bridge = ind_state
                except Exception:
                    pass
            sec.atomic_write_json(d / "indicator.json", {"state": ind_state})

    def tick(self):
        d = self.active_dir()
        if d is None:
            return
        now = float(self.now())

        # 1. Honour <state>/RELEASE immediately and delete the file
        rel = d / "RELEASE"
        if rel.exists():
            try:
                rel.unlink()
            except OSError:
                pass
            tf = d / "task_active.json"
            if tf.exists():
                self._ignored_sig = self._sig(sec.read_json_safe(tf))
            self._do_release("release", respect_real_input=False)
            return

        # 2. Check if the lock itself recorded a physical Esc x3 takeover
        if self.lock is not None and getattr(self.lock, "taken_over", False):
            self.lock.taken_over = False
            self.takeover()
            return

        # 3. Check <state>/task_active.json
        tf = d / "task_active.json"
        data = sec.read_json_safe(tf) if tf.exists() else None
        if data is None:
            self._ignored_sig = None
            if self.task_locked or getattr(self.lock, "remote_task", False):
                self._do_release("task-ended", respect_real_input=True)
        else:
            sig = self._sig(data)
            if self._ignored_sig is not None and sig != self._ignored_sig:
                self._ignored_sig = None
            hb_raw = data.get("heartbeat")
            try:
                hb = float(hb_raw) if hb_raw is not None else None
            except (TypeError, ValueError):
                hb = None
            stale = hb is None or (now - hb) >= 15.0
            try:
                max_minutes = float(data.get("max_minutes", 15))
            except (TypeError, ValueError):
                max_minutes = 15.0
            task_id = data.get("task", "")
            try:
                since_val = float(data["since"]) if "since" in data and data["since"] is not None else (
                    self._task_since if (self.task_locked and task_id == self._task_id and self._task_since is not None) else now
                )
            except (TypeError, ValueError):
                since_val = self._task_since or now
            exceeded = (now - since_val) >= (max_minutes * 60.0)

            if stale:
                if self.task_locked or getattr(self.lock, "remote_task", False):
                    self._do_release("stale-heartbeat", respect_real_input=True)
            elif exceeded:
                if self.task_locked or getattr(self.lock, "remote_task", False):
                    self._do_release("max-minutes", respect_real_input=True)
            elif self._ignored_sig is None:
                need_acq = not self.task_locked or (self._lock_enabled() and self.lock is not None and not getattr(self.lock, "locked", False))
                self.task_locked = True
                self._task_id = task_id
                self._task_since = since_val
                if need_acq:
                    self._do_acquire_task(max_seconds=max_minutes * 60.0, since=since_val)
                else:
                    self._set_ind_locked(True)

        # 4. Check <state>/screen_view.json
        svf = d / "screen_view.json"
        sv = sec.read_json_safe(svf) if svf.exists() else None
        viewing = False
        if isinstance(sv, dict) and "until" in sv:
            try:
                viewing = float(sv["until"]) > now
            except (TypeError, ValueError):
                viewing = False
        if viewing != self.screen_view_active:
            self.screen_view_active = viewing
            if self.lock is not None and hasattr(self.lock, "set_screen_view"):
                self.lock.set_screen_view(viewing, start_thread=self.allow_windows)
            elif self.lock is not None and not getattr(self.lock, "locked", False):
                try:
                    self.lock._text = SCREEN_VIEW_TEXT if viewing else BANNER_TEXT
                except Exception:
                    pass
            if not self.task_locked and not getattr(self.lock, "locked", False):
                self.banner_text = SCREEN_VIEW_TEXT if viewing else ""

        # 5. Keep bridge files in sync
        self.sync_files()

    def start(self):
        global _DEFAULT_BRIDGE
        if self.state_dir is None and _DEFAULT_BRIDGE is not None and _DEFAULT_BRIDGE is not self:
            _DEFAULT_BRIDGE.stop()
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        if self.state_dir is None:
            _DEFAULT_BRIDGE = self
        self._thread = threading.Thread(target=self._loop, daemon=True, name="state-bridge")
        self._thread.start()

    def stop(self):
        self._stop.set()
        t = self._thread
        if t and t is not threading.current_thread() and t.is_alive():
            t.join(2)

    def _loop(self):
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                pass
            self._stop.wait(self.period)
