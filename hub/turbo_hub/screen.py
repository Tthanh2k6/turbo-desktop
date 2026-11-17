"""Primary-monitor capture and secret-window redaction for GET /screen.jpg."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import io
import re
from typing import Callable, Sequence

from PIL import Image

DWMWA_EXTENDED_FRAME_BOUNDS = 9

# Exact secret-title patterns from desktop-mcp/src/turbo_desktop/security.py
SECRET_TITLE_PATTERNS = [
    r"\.env(\.|\b)", r"secrets?", r"credentials", r"\.pem\b", r"\.key\b", r"id_rsa", r"\.kdbx", r"token",
    r"password", r"mật khẩu", r"api[_-]?key",
]


def is_secret_title(title: str | None, patterns: Sequence[str] = SECRET_TITLE_PATTERNS) -> bool:
    if not title:
        return False
    for pat in patterns:
        try:
            if re.search(pat, title, re.I):
                return True
        except re.error:
            continue
    return False


def _window_rect(hwnd: int, user32, dwmapi) -> tuple[int, int, int, int] | None:
    rect = wintypes.RECT()
    if dwmapi is not None:
        try:
            hr = dwmapi.DwmGetWindowAttribute(
                wintypes.HWND(hwnd),
                wintypes.DWORD(DWMWA_EXTENDED_FRAME_BOUNDS),
                ctypes.byref(rect),
                ctypes.sizeof(rect),
            )
            if hr == 0 and rect.right > rect.left and rect.bottom > rect.top:
                return int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)
        except Exception:
            pass
    if user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect)):
        if rect.right > rect.left and rect.bottom > rect.top:
            return int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)
    return None


def enum_windows() -> list[dict]:
    """Enumerate visible top-level windows via ctypes: [{"title": str, "rect": (left, top, right, bottom)}]."""
    if not hasattr(ctypes, "windll"):
        return []
    user32 = ctypes.windll.user32
    dwmapi = getattr(ctypes.windll, "dwmapi", None)
    out: list[dict] = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        if not title:
            return True
        r = _window_rect(hwnd, user32, dwmapi)
        if r is not None:
            out.append({"title": title, "rect": r})
        return True

    user32.EnumWindows(WNDENUMPROC(_cb), 0)
    return out


def grab_primary() -> tuple[Image.Image, tuple[int, int, int, int]]:
    """Capture the primary monitor with mss and return (RGB PIL.Image, (left, top, right, bottom))."""
    import mss
    with mss.mss() as sct:
        mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
        shot = sct.grab(mon)
        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        left, top = int(mon.get("left", 0)), int(mon.get("top", 0))
        return img, (left, top, left + img.width, top + img.height)


def _unpack_window(w) -> tuple[str, tuple[int, int, int, int]]:
    if isinstance(w, dict):
        rect = w.get("rect") or (w["left"], w["top"], w["right"], w["bottom"])
        return str(w.get("title") or ""), (int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3]))
    if isinstance(w, (tuple, list)):
        if len(w) == 2:
            r = w[1]
            return str(w[0] or ""), (int(r[0]), int(r[1]), int(r[2]), int(r[3]))
        if len(w) >= 5:
            return str(w[0] or ""), (int(w[1]), int(w[2]), int(w[3]), int(w[4]))
    return str(getattr(w, "title", "") or ""), tuple(int(x) for x in getattr(w, "rect"))  # type: ignore[return-value]


def redact_image(
    img: Image.Image | bytes,
    windows: Sequence,
    patterns: Sequence[str] = SECRET_TITLE_PATTERNS,
    monitor_rect: tuple[int, int, int, int] | None = None,
) -> tuple[Image.Image, int]:
    """Black out every window whose title matches `patterns`. Returns (redacted_image, count)."""
    if isinstance(img, (bytes, bytearray)):
        out = Image.open(io.BytesIO(img)).convert("RGB")
    else:
        out = img.convert("RGB") if img.mode != "RGB" else img.copy()
    ml, mt, _mr, _mb = monitor_rect or (0, 0, out.width, out.height)
    redacted = 0
    for w in windows:
        title, (l, t, r, b) = _unpack_window(w)
        if not is_secret_title(title, patterns):
            continue
        x0 = max(0, min(out.width, l - ml))
        y0 = max(0, min(out.height, t - mt))
        x1 = max(0, min(out.width, r - ml))
        y1 = max(0, min(out.height, b - mt))
        if x1 > x0 and y1 > y0:
            out.paste((0, 0, 0), (x0, y0, x1, y1))
            redacted += 1
    return out, redacted


def capture_screen_jpeg(
    *,
    max_width: int = 960,
    quality: int = 60,
    patterns: Sequence[str] = SECRET_TITLE_PATTERNS,
    grabber: Callable | Image.Image | None = None,
    window_enumerator: Callable | Sequence | None = None,
    region: tuple[int, int, int, int] | None = None,
) -> tuple[bytes, int]:
    """Capture primary monitor, black out secret windows before encoding, optionally crop to `region`
    (x, y, w, h in thousandths of the screen, for the phone's zoomed view), scale to <= max_width, encode JPEG.
    A crop is never upscaled, so a zoomed view gets the PC's own pixels."""
    def _windows():
        return enum_windows() if window_enumerator is None else (
            window_enumerator() if callable(window_enumerator) else list(window_enumerator))
    before = _windows()   # enumerate before AND after the grab: a secret window that opens or moves in between
    raw = grab_primary() if grabber is None else (grabber() if callable(grabber) else grabber)
    if isinstance(raw, tuple) and len(raw) == 2:
        img, mon_rect = raw
    else:
        img = raw
        mon_rect = None
    windows, seen = [], set()   # is still blacked out (union of both lists, duplicates dropped)
    for w in list(before) + list(_windows()):
        key = _unpack_window(w)
        if key not in seen:
            seen.add(key); windows.append(w)
    img, redacted = redact_image(img, windows, patterns, mon_rect)
    if region is not None:
        box = crop_box(region, img.width, img.height)
        if box is not None:
            img = img.crop(box)
    w = max(1, min(int(max_width), MAX_WIDTH))
    q = max(30, min(int(quality), MAX_QUALITY))
    if img.width > w:
        h = max(1, int(round(img.height * w / img.width)))
        img = img.resize((w, h), Image.Resampling.BILINEAR)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=q, subsampling=0)
    return buf.getvalue(), redacted


MAX_WIDTH = 1920     # full frames: the phone picks 960 / 1600 / 1920 ("Tiết kiệm" / "Nét" / "Rất nét")
MAX_QUALITY = 85


def crop_box(region: tuple[int, int, int, int], width: int, height: int) -> tuple[int, int, int, int] | None:
    """(x, y, w, h) in thousandths -> pixel box clamped to the image, at least 16 px each way. None = whole image."""
    x, y, rw, rh = (max(0, min(1000, int(v))) for v in region)
    if rw <= 0 or rh <= 0 or (x == 0 and y == 0 and rw >= 1000 and rh >= 1000):
        return None
    x0 = x * width // 1000
    y0 = y * height // 1000
    x1 = min(width, max(x0 + 16, (x + rw) * width // 1000))
    y1 = min(height, max(y0 + 16, (y + rh) * height // 1000))
    x0, y0 = max(0, min(x0, x1 - 16)), max(0, min(y0, y1 - 16))
    return x0, y0, x1, y1


def demo_frame() -> tuple[Image.Image, tuple[int, int, int, int]]:
    """Synthetic 1600x900 desktop for the fake runner (emulator demos): a calculator-like window, no real pixels."""
    from PIL import ImageDraw
    img = Image.new("RGB", (1600, 900), (32, 40, 58))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 860, 1600, 900), fill=(20, 22, 28))                     # taskbar
    d.rounded_rectangle((520, 140, 1080, 780), 14, fill=(243, 243, 243))   # app window
    d.rectangle((520, 140, 1080, 180), fill=(230, 230, 230))
    d.text((540, 152), "Calculator", fill=(40, 40, 40))
    d.text((1000, 230), "58.5", fill=(20, 20, 20))
    for r in range(5):
        for c in range(4):
            x, y = 545 + c * 130, 330 + r * 85
            d.rounded_rectangle((x, y, x + 115, y + 70), 8, fill=(250, 250, 250) if r else (225, 225, 225))
    return img, (0, 0, 1600, 900)
