"""Screen-edge glow while the AI controls the PC (like Claude in Chrome does in the browser).

Two levels:
  acting : AI is doing something (pattern or real input), until `linger` seconds after the last action. Pulses gently.
  locked : the input lock is held (or real input is being sent). Solid and brighter; the lock's text banner is on top.

One borderless, click-through, no-focus, no-taskbar layered window per monitor, drawn with UpdateLayeredWindow
(per-pixel alpha). Runs in its own thread with its own message loop. Hard floor: it cannot be switched off while
the input is locked or real input is being sent; with pattern-only actions `[indicator] border = false` hides it.
"""
from __future__ import annotations

import atexit
import ctypes
import threading
import time
from ctypes import wintypes

from . import security as sec

GLOW_CLASS = "TurboDesktopGlow"
DEFAULT_COLOR = "#E0461D"


# ---------------------------------------------------------------- pure state machine (fake clock in tests)

class GlowState:
    def __init__(self, now=time.monotonic, linger=3.0, enabled=True):
        self.now = now
        self.linger = linger
        self.enabled = enabled          # [indicator] border; ignored while locked / real input is sent
        self.last_activity = None
        self.locked = False
        self.real_active = False
        self.suppressed = False         # STOP or owner takeover: off until the next activity

    def activity(self):
        self.last_activity = self.now()
        self.suppressed = False

    def set_locked(self, v: bool):
        self.locked = v
        if v:
            self.suppressed = False

    def set_real_input(self, v: bool):
        self.real_active = v
        if v:
            self.activity()

    def hide_now(self):
        """STOP / owner takeover: disappear immediately, stay off until the next action."""
        self.suppressed = True
        self.locked = False
        self.real_active = False
        self.last_activity = None

    def level(self) -> str:
        if self.suppressed:
            return "off"
        if self.locked or self.real_active:
            return "locked"           # hard floor: shown whatever `enabled` says
        if not self.enabled:
            return "off"
        if self.last_activity is not None and self.now() - self.last_activity <= self.linger:
            return "acting"
        return "off"

    def bridge_state(self) -> str:
        if self.suppressed:
            return "idle"
        if self.locked:
            return "input_locked"
        if self.real_active:
            return "acting"
        if self.last_activity is not None and self.now() - self.last_activity <= self.linger:
            return "acting"
        return "idle"


def parse_color(s: str | None) -> tuple[int, int, int]:
    try:
        s = (s or DEFAULT_COLOR).lstrip("#")
        return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    except Exception:
        return 0xE0, 0x46, 0x1D


def pulse_factor(t: float, period=1.5, lo=0.6, hi=1.0, steady=False) -> float:
    """0.6..1.0 sine pulse; steady (reduce-motion) gives the bright end."""
    if steady:
        return hi
    import math
    return lo + (hi - lo) * (0.5 + 0.5 * math.sin(2 * math.pi * t / period))


def edge_alpha(d: int, level: str) -> int:
    """Alpha (0..255) of a pixel d px from the nearest screen edge: solid frame then a soft inner fade."""
    thick, fade, peak = (8, 18, 0.85) if level == "locked" else (6, 14, 0.55)
    if d < thick:
        return 255
    if d < thick + fade:
        k = 1 - (d - thick) / fade
        return int(255 * peak * k * k)
    return 0


def build_frame_bytes(w: int, h: int, rgb: tuple, level: str) -> bytes:
    """Premultiplied BGRA bitmap (top-down) of the frame. Pure python, built row by row."""
    r, g, b = rgb
    band = (8 + 18) if level == "locked" else (6 + 14)

    def px(a):
        return bytes((b * a // 255, g * a // 255, r * a // 255, a))

    cache = {}

    def pxc(a):
        if a not in cache:
            cache[a] = px(a)
        return cache[a]

    rows = []
    clear = b"\x00\x00\x00\x00"
    mid = None
    for y in range(h):
        dy = min(y, h - 1 - y)
        if dy < band:
            rows.append(b"".join(pxc(edge_alpha(min(dy, x, w - 1 - x), level)) for x in range(w)))
        else:
            if mid is None:
                left = b"".join(pxc(edge_alpha(x, level)) for x in range(band))
                right = b"".join(pxc(edge_alpha(x, level)) for x in range(band - 1, -1, -1))
                mid = left + clear * (w - 2 * band) + right
            rows.append(mid)
    return b"".join(rows)


# ---------------------------------------------------------------- windows plumbing

u32 = ctypes.WinDLL("user32", use_last_error=True)
g32 = ctypes.WinDLL("gdi32", use_last_error=True)
k32 = ctypes.WinDLL("kernel32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
WS_POPUP = 0x80000000
WS_EX_TOPMOST, WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW = 0x8, 0x80000, 0x20, 0x8000000, 0x80
ULW_ALPHA = 2
HWND_TOPMOST = wintypes.HWND(-1)
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_SHOWWINDOW = 1, 2, 0x10, 0x40


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HANDLE),
                ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH), ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte), ("SourceConstantAlpha", ctypes.c_ubyte),
                ("AlphaFormat", ctypes.c_ubyte)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


u32.DefWindowProcW.restype = LRESULT
u32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
u32.CreateWindowExW.restype = wintypes.HWND
u32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
u32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
u32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
u32.DestroyWindow.argtypes = [wintypes.HWND]
u32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
u32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
u32.GetDC.restype = wintypes.HDC
u32.GetDC.argtypes = [wintypes.HWND]
u32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
u32.UpdateLayeredWindow.argtypes = [wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT), ctypes.POINTER(wintypes.SIZE),
                                    wintypes.HDC, ctypes.POINTER(wintypes.POINT), wintypes.COLORREF,
                                    ctypes.POINTER(BLENDFUNCTION), wintypes.DWORD]
u32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
u32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
u32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
u32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
g32.CreateCompatibleDC.restype = wintypes.HDC
g32.CreateCompatibleDC.argtypes = [wintypes.HDC]
g32.CreateDIBSection.restype = wintypes.HBITMAP
g32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.POINTER(BITMAPINFOHEADER), wintypes.UINT, ctypes.POINTER(ctypes.c_void_p),
                                 wintypes.HANDLE, wintypes.DWORD]
g32.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
g32.SelectObject.restype = wintypes.HANDLE
g32.DeleteObject.argtypes = [wintypes.HANDLE]
g32.DeleteDC.argtypes = [wintypes.HDC]
k32.GetModuleHandleW.restype = wintypes.HMODULE


def set_per_monitor_dpi_aware():
    """Physical pixel coordinates on every monitor (needed so the frame matches each monitor's real edge)."""
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # PER_MONITOR_AWARE_V2
    except Exception:
        pass


def monitors() -> list[tuple[int, int, int, int]]:
    import win32api
    out = []
    for _h, _dc, (l, t, r, b) in win32api.EnumDisplayMonitors(None, None):
        out.append((l, t, r - l, b - t))
    return out


def reduce_motion() -> bool:
    on = ctypes.c_int(1)
    if u32.SystemParametersInfoW(0x1042, 0, ctypes.byref(on), 0):  # SPI_GETCLIENTAREAANIMATION
        return on.value == 0
    return False


def high_contrast() -> bool:
    class HC(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwFlags", wintypes.DWORD), ("lpszDefaultScheme", wintypes.LPWSTR)]
    hc = HC(ctypes.sizeof(HC), 0, None)
    u32.SystemParametersInfoW(0x42, ctypes.sizeof(hc), ctypes.byref(hc), 0)  # SPI_GETHIGHCONTRAST
    return bool(hc.dwFlags & 1)


class _MonitorWindow:
    def __init__(self, hwnd, rect):
        self.hwnd, self.rect = hwnd, rect
        self.level = None
        self.hbmp = None
        self.memdc = None
        self.bits = None


class Glow:
    """The renderer thread. Poll `state` (a GlowState) every tick; create/destroy one window per monitor."""

    def __init__(self, state: GlowState | None = None, color=DEFAULT_COLOR, window_class=GLOW_CLASS, tick_ms=40):
        self.state = state or GlowState()
        self.rgb = parse_color(color)
        self.window_class = window_class
        self.tick = tick_ms / 1000.0
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.windows: list[_MonitorWindow] = []
        self.hwnds: list[int] = []
        self.steady = False
        self.visible_level = "off"
        self._lock = threading.Lock()
        self._wp = WNDPROC(lambda h, m, w, l: u32.DefWindowProcW(h, m, w, l))
        atexit.register(self.close)

    # ------------------------------------------------------------ control

    def start(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, daemon=True, name="glow")
            self._thread.start()

    def close(self):
        self._stop.set()
        t = self._thread
        if t and t is not threading.current_thread() and t.is_alive():
            t.join(3)

    # ------------------------------------------------------------ thread

    def _create_windows(self):
        hinst = k32.GetModuleHandleW(None)
        wc = WNDCLASSW()
        wc.lpfnWndProc = self._wp
        wc.hInstance = hinst
        wc.lpszClassName = self.window_class
        u32.RegisterClassW(ctypes.byref(wc))
        for (x, y, w, h) in monitors():
            hwnd = u32.CreateWindowExW(WS_EX_TOPMOST | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW,
                                       self.window_class, "turbo-desktop glow", WS_POPUP, x, y, w, h, None, None, hinst, None)
            if hwnd:
                self.windows.append(_MonitorWindow(hwnd, (x, y, w, h)))
        self.hwnds = [m.hwnd for m in self.windows]

    def _paint(self, m: _MonitorWindow, level: str, alpha_factor: float):
        x, y, w, h = m.rect
        if m.level != level:
            for obj in (m.hbmp,):
                if obj:
                    g32.DeleteObject(obj)
            if m.memdc:
                g32.DeleteDC(m.memdc)
            screen = u32.GetDC(None)
            m.memdc = g32.CreateCompatibleDC(screen)
            bi = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
            ptr = ctypes.c_void_p()
            m.hbmp = g32.CreateDIBSection(screen, ctypes.byref(bi), 0, ctypes.byref(ptr), None, 0)
            u32.ReleaseDC(None, screen)
            g32.SelectObject(m.memdc, m.hbmp)
            ctypes.memmove(ptr, build_frame_bytes(w, h, self.rgb if not high_contrast() else (255, 255, 0), level), w * h * 4)
            m.level = level
        blend = BLENDFUNCTION(0, 0, max(1, min(255, int(255 * alpha_factor))), 1)  # AC_SRC_OVER, AC_SRC_ALPHA
        pt_dst, size, pt_src = wintypes.POINT(x, y), wintypes.SIZE(w, h), wintypes.POINT(0, 0)
        screen = u32.GetDC(None)
        u32.UpdateLayeredWindow(m.hwnd, screen, ctypes.byref(pt_dst), ctypes.byref(size), m.memdc, ctypes.byref(pt_src), 0,
                                ctypes.byref(blend), ULW_ALPHA)
        u32.ReleaseDC(None, screen)

    def _destroy_windows(self):
        for m in self.windows:
            u32.DestroyWindow(m.hwnd)
            if m.hbmp:
                g32.DeleteObject(m.hbmp)
            if m.memdc:
                g32.DeleteDC(m.memdc)
        if self.windows:
            u32.UnregisterClassW(self.window_class, k32.GetModuleHandleW(None))
        self.windows, self.hwnds = [], []

    def _pump(self):
        msg = wintypes.MSG()
        while u32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            u32.TranslateMessage(ctypes.byref(msg))
            u32.DispatchMessageW(ctypes.byref(msg))

    def _run(self):
        set_per_monitor_dpi_aware()
        t0 = time.monotonic()
        last_top = 0.0
        try:
            while not self._stop.is_set():
                if sec.stop_requested():
                    self.state.hide_now()
                level = self.state.level()
                if level != "off" and not self.windows:
                    self.steady = reduce_motion()
                    self._create_windows()
                if level == "off" and self.windows:
                    self._destroy_windows()
                if level != "off" and self.windows:
                    f = 1.0 if (level == "locked" or self.steady) else pulse_factor(time.monotonic() - t0, steady=self.steady)
                    for m in self.windows:
                        self._paint(m, level, f)
                    now = time.monotonic()
                    if now - last_top > 1.0:           # re-assert topmost (full-screen apps, taskbar changes)
                        for m in self.windows:
                            u32.SetWindowPos(m.hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_SHOWWINDOW)
                        last_top = now
                self.visible_level = level if self.windows else "off"
                self._pump()
                time.sleep(self.tick)
        finally:
            self._destroy_windows()
            self.visible_level = "off"


class Indicator:
    """What the engine calls. Lazily starts the renderer; every call is cheap and never raises."""

    def __init__(self, enabled=True, color=DEFAULT_COLOR, linger=3.0, disabled_by_env=False, state_dir=None):
        self.state = GlowState(linger=linger, enabled=enabled)
        self.glow = Glow(self.state, color)
        self.disabled = disabled_by_env
        self._state_dir = state_dir
        self._last_bridge = None

    def configure(self, border: bool, color: str | None):
        self.state.enabled = bool(border)
        if color:
            self.glow.rgb = parse_color(color)

    def write_bridge(self):
        d = sec.bridge_dir(self._state_dir)
        if d is None:
            return
        st = self.state.bridge_state()
        if st != self._last_bridge or not (d / "indicator.json").exists():
            self._last_bridge = st
            sec.atomic_write_json(d / "indicator.json", {"state": st})

    def _go(self):
        self.write_bridge()
        if not self.disabled:
            try:
                self.glow.start()
            except Exception:
                pass

    def activity(self):
        self.state.activity()
        self._go()

    def real_input(self, on: bool):
        self.state.set_real_input(on)
        self._go()

    def locked(self, on: bool):
        self.state.set_locked(on)
        self._go()

    def hide_now(self):
        self.state.hide_now()
        self.write_bridge()
