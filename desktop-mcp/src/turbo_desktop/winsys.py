"""Low-level Windows helpers: processes, integrity, idle time, session state, screenshots, OCR."""
from __future__ import annotations

import asyncio
import ctypes
import io
import os
import threading
import time
from ctypes import wintypes

import win32api
import win32con
import win32gui
import win32process

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
u32 = ctypes.WinDLL("user32", use_last_error=True)
adv = ctypes.WinDLL("advapi32", use_last_error=True)
dwm = ctypes.WinDLL("dwmapi")
sh32 = ctypes.WinDLL("shell32", use_last_error=True)

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TOKEN_QUERY = 0x0008

k32.OpenProcess.restype = wintypes.HANDLE
k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
k32.QueryFullProcessImageNameW.restype = wintypes.BOOL
k32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
k32.CloseHandle.restype = wintypes.BOOL
k32.CloseHandle.argtypes = [wintypes.HANDLE]
k32.GetTickCount.restype = wintypes.DWORD
k32.GetTickCount.argtypes = []
k32.GetCurrentThreadId.restype = wintypes.DWORD
k32.GetCurrentThreadId.argtypes = []
adv.OpenProcessToken.restype = wintypes.BOOL
adv.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
adv.GetTokenInformation.restype = wintypes.BOOL
adv.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
sh32.IsUserAnAdmin.restype = wintypes.BOOL
sh32.IsUserAnAdmin.argtypes = []
u32.OpenInputDesktop.restype = wintypes.HANDLE
u32.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
u32.GetThreadDesktop.restype = wintypes.HANDLE
u32.GetThreadDesktop.argtypes = [wintypes.DWORD]
u32.GetUserObjectInformationW.restype = wintypes.BOOL
u32.GetUserObjectInformationW.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
u32.CloseDesktop.restype = wintypes.BOOL
u32.CloseDesktop.argtypes = [wintypes.HANDLE]
u32.PrintWindow.restype = wintypes.BOOL
u32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
dwm.DwmGetWindowAttribute.restype = ctypes.c_long
dwm.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]


def process_info(pid: int) -> tuple[str, bool | None]:
    """(exe name without .exe, elevated?). elevated is True when we cannot even open the process
    (access denied = higher integrity), None if unknown."""
    h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        err = ctypes.get_last_error()
        return "?", (True if err == 5 else None)
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        name = "?"
        if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            name = os.path.basename(buf.value)
            name = name[:-4] if name.lower().endswith(".exe") else name
        elevated = None
        tok = wintypes.HANDLE()
        if adv.OpenProcessToken(h, TOKEN_QUERY, ctypes.byref(tok)):
            try:
                val = wintypes.DWORD()
                ret = wintypes.DWORD()
                if adv.GetTokenInformation(tok, 20, ctypes.byref(val), ctypes.sizeof(val), ctypes.byref(ret)):  # TokenElevation
                    elevated = bool(val.value)
            finally:
                k32.CloseHandle(tok)
        return name, elevated
    finally:
        k32.CloseHandle(h)


def we_are_admin() -> bool:
    try:
        return bool(sh32.IsUserAnAdmin())
    except Exception:
        return False


def is_elevated_above_us(pid: int) -> bool:
    if we_are_admin():
        return False
    _, el = process_info(pid)
    return bool(el)


# ---------------------------------------------------------------- idle / session / power

class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


u32.GetLastInputInfo.restype = wintypes.BOOL
u32.GetLastInputInfo.argtypes = [ctypes.POINTER(LASTINPUTINFO)]


def idle_seconds() -> float:
    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(lii)
    u32.GetLastInputInfo(ctypes.byref(lii))
    return ((k32.GetTickCount() - lii.dwTime) & 0xFFFFFFFF) / 1000.0


class SYSTEM_POWER_STATUS(ctypes.Structure):
    _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte), ("BatteryLifePercent", ctypes.c_ubyte),
                ("SystemStatusFlag", ctypes.c_ubyte), ("BatteryLifeTime", wintypes.DWORD), ("BatteryFullLifeTime", wintypes.DWORD)]


k32.GetSystemPowerStatus.restype = wintypes.BOOL
k32.GetSystemPowerStatus.argtypes = [ctypes.POINTER(SYSTEM_POWER_STATUS)]


def _process_names() -> set[str]:
    names = set()
    try:
        for pid in win32process.EnumProcesses():
            n, _ = process_info(pid)
            names.add(n.lower())
    except Exception:
        pass
    return names


def _desktop_name(hdesk) -> str:
    if not hdesk:
        return ""
    buf = ctypes.create_unicode_buffer(256)
    need = wintypes.DWORD()
    if u32.GetUserObjectInformationW(hdesk, 2, buf, ctypes.sizeof(buf), ctypes.byref(need)):
        return buf.value
    return ""


def on_input_desktop() -> bool:
    """True when the calling thread runs on the active input desktop (False in isolated non-input desktops)."""
    h_thread = u32.GetThreadDesktop(k32.GetCurrentThreadId())
    h_input = u32.OpenInputDesktop(0, False, 0x0100)
    if not h_input:
        return False
    try:
        t_name = _desktop_name(h_thread)
        i_name = _desktop_name(h_input)
        return bool(t_name and i_name and t_name.lower() == i_name.lower())
    finally:
        u32.CloseDesktop(h_input)


def secure_desktop_active() -> bool:
    """True when the input desktop is not the user's (UAC prompt or lock screen)."""
    h = u32.OpenInputDesktop(0, False, 0x0100)  # DESKTOP_SWITCHDESKTOP
    if not h:
        return True
    u32.CloseDesktop(h)
    return False


def system_state() -> dict:
    names = _process_names()
    secure = secure_desktop_active()
    ps = SYSTEM_POWER_STATUS()
    k32.GetSystemPowerStatus(ctypes.byref(ps))
    on_battery = {0: True, 1: False}.get(ps.ACLineStatus)
    return {
        "secureDesktopActive": secure,  # UAC prompt or lock screen is in front: no automation possible
        "uacPrompt": secure and "consent" in names,
        "sessionLocked": secure and "logonui" in names,
        "displayOff": None,  # Windows exposes this only via power notifications; unknown without a listener
        "idleSeconds": round(idle_seconds(), 1),
        "onBattery": on_battery,
        "batteryPercent": None if ps.BatteryLifePercent == 255 else ps.BatteryLifePercent,
        "weAreAdmin": we_are_admin(),
        "onInputDesktop": on_input_desktop(),
        "ready": not secure,
    }


# ---------------------------------------------------------------- windows

def is_cloaked(hwnd) -> bool:
    v = wintypes.DWORD()
    try:
        dwm.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(v), ctypes.sizeof(v))
    except Exception:
        return False
    return bool(v.value)


def real_pid_for_window(hwnd) -> int:
    """For UWP frames (ApplicationFrameHost) return the pid of the hosted CoreWindow."""
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    name, _ = process_info(pid)
    if name.lower() != "applicationframehost":
        return pid
    found = []

    def cb(ch, _):
        try:
            if win32gui.GetClassName(ch) == "Windows.UI.Core.CoreWindow":
                _, p = win32process.GetWindowThreadProcessId(ch)
                if p != pid:
                    found.append(p)
        except Exception:
            pass
        return True

    try:
        win32gui.EnumChildWindows(hwnd, cb, None)
    except Exception:
        pass
    return found[0] if found else pid


def enum_top_windows(hidden: bool = False) -> list[dict]:
    out = []

    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return True
        title = win32gui.GetWindowText(hwnd)
        if not title:
            return True
        cls = win32gui.GetClassName(hwnd)
        cloaked = is_cloaked(hwnd)
        ex = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        rect = None
        try:
            if not win32gui.IsIconic(hwnd):
                rect = win32gui.GetWindowRect(hwnd)
        except Exception:
            rect = None
        item = {"hwnd": hwnd, "title": title, "class": cls, "cloaked": cloaked}
        if rect is not None:
            item["rect"] = rect
            item["width"] = rect[2] - rect[0]
            item["height"] = rect[3] - rect[1]
        if not hidden:
            if ex & win32con.WS_EX_TOOLWINDOW and not ex & win32con.WS_EX_APPWINDOW:
                return True
            if is_irrelevant_window(item):
                return True
        pid = real_pid_for_window(hwnd)
        out.append({"hwnd": hwnd, "title": title, "pid": pid, "class": cls})
        return True

    win32gui.EnumWindows(cb, None)
    return out


IRRELEVANT_CLASSES = {"Shell_TrayWnd", "Shell_SecondaryTrayWnd", "NotifyIconOverflowWindow", "Progman", "WorkerW"}
OWN_CLASS_PREFIXES = ("TurboDesktopGlow", "TurboDesktopBanner")
OWN_TITLES = {"turbo-desktop glow", "turbo-desktop-ctrl"}


def is_irrelevant_window(t: dict, own_hwnds=()) -> bool:
    """True for tool-irrelevant windows: cloaked, zero-size, shell tray, and desktop-mcp's own glow/banner windows."""
    hwnd = t.get("hwnd")
    if hwnd and hwnd in own_hwnds:
        return True
    title = (t.get("title") or "").strip()
    cls = (t.get("class") or "").strip()
    if not title or title == "Program Manager":
        return True
    if cls in IRRELEVANT_CLASSES:
        return True
    if cls.startswith(OWN_CLASS_PREFIXES) or title in OWN_TITLES:
        return True
    if title == "turbo-desktop" and cls.startswith("TurboDesktop"):
        return True
    if t.get("cloaked"):
        return True
    if ("width" in t or "height" in t) and (t.get("width", 1) <= 0 or t.get("height", 1) <= 0):
        return True
    rect = t.get("rect")
    if rect is not None and len(rect) == 4 and ((rect[2] - rect[0]) <= 0 or (rect[3] - rect[1]) <= 0):
        return True
    return False


# ---------------------------------------------------------------- screenshots

def capture_window(hwnd):
    """PIL image of the window via PrintWindow (works when partly covered); falls back to screen grab."""
    from PIL import Image, ImageGrab
    import win32ui

    l, t, r, b = win32gui.GetWindowRect(hwnd)
    w, h = max(r - l, 1), max(b - t, 1)
    hdc = src = mem = bmp = None
    try:
        hdc = win32gui.GetWindowDC(hwnd)
        src = win32ui.CreateDCFromHandle(hdc)
        mem = src.CreateCompatibleDC()
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(src, w, h)
        mem.SelectObject(bmp)
        ok = u32.PrintWindow(hwnd, mem.GetSafeHdc(), 2)
        info = bmp.GetInfo()
        bits = bmp.GetBitmapBits(True)
        img = Image.frombuffer("RGB", (info["bmWidth"], info["bmHeight"]), bits, "raw", "BGRX", 0, 1)
        if ok:
            return img, (l, t)
    except Exception:
        pass
    finally:
        if mem is not None:
            try:
                mem.DeleteDC()
            except Exception:
                pass
        if src is not None:
            try:
                src.DeleteDC()
            except Exception:
                pass
        if hdc is not None:
            try:
                win32gui.ReleaseDC(hwnd, hdc)
            except Exception:
                pass
        if bmp is not None:
            try:
                handle = bmp.GetHandle()
                if handle:
                    win32gui.DeleteObject(handle)
            except Exception:
                pass
    return ImageGrab.grab(bbox=(l, t, r, b), all_screens=True), (l, t)


# ---------------------------------------------------------------- OCR (Windows.Media.Ocr, local)

_ocr_lock = threading.Lock()


async def _ocr_async(png: bytes):
    from winrt.windows.graphics.imaging import BitmapDecoder
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.storage.streams import DataWriter, InMemoryRandomAccessStream

    stream = InMemoryRandomAccessStream()
    dw = DataWriter(stream)
    dw.write_bytes(png)
    await dw.store_async()
    await dw.flush_async()
    stream.seek(0)
    decoder = await BitmapDecoder.create_async(stream)
    bitmap = await decoder.get_software_bitmap_async()
    engine = OcrEngine.try_create_from_user_profile_languages()
    if engine is None:
        raise RuntimeError("no OCR language pack installed")
    res = await engine.recognize_async(bitmap)
    lines = []
    for ln in res.lines:
        rects = [w.bounding_rect for w in ln.words]
        if not rects:
            continue
        x1 = min(r.x for r in rects); y1 = min(r.y for r in rects)
        x2 = max(r.x + r.width for r in rects); y2 = max(r.y + r.height for r in rects)
        lines.append({"text": ln.text, "x": int(x1), "y": int(y1), "w": int(x2 - x1), "h": int(y2 - y1)})
    return lines


def ocr_image(img) -> list[dict]:
    """Return [{text,x,y,w,h}] in image pixel coords. Raises RuntimeError if OCR unavailable."""
    buf = io.BytesIO()
    img.save(buf, "PNG")
    try:
        with _ocr_lock:
            return asyncio.run(_ocr_async(buf.getvalue()))
    except ImportError as e:
        raise RuntimeError(f"winrt OCR packages missing: {e}")
