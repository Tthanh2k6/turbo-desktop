import ctypes
import time

import pytest
from ctypes import wintypes

from turbo_desktop import border as bd, rules, security as sec
from turbo_desktop.engine import Desktop


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


# ---------------------------------------------------------------- pure state machine

def test_state_off_until_first_activity_then_linger_3s():
    c = Clock()
    s = bd.GlowState(now=c)
    assert s.level() == "off"
    s.activity()
    assert s.level() == "acting"
    c.t += 2.9
    assert s.level() == "acting"
    c.t += 0.2
    assert s.level() == "off"           # 3 s after the last action
    s.activity()
    assert s.level() == "acting"


def test_locked_level_wins_and_ignores_border_false():
    c = Clock()
    s = bd.GlowState(now=c, enabled=False)
    s.activity()
    assert s.level() == "off"           # pattern-only with border=false: hidden
    s.set_real_input(True)
    assert s.level() == "locked"        # hard floor
    s.set_real_input(False)
    s.set_locked(True)
    assert s.level() == "locked"
    c.t += 60
    assert s.level() == "locked"        # stays while the lock is held
    s.set_locked(False)
    assert s.level() == "off"


def test_stop_or_takeover_hides_now_until_next_activity():
    c = Clock()
    s = bd.GlowState(now=c)
    s.set_locked(True)
    s.hide_now()
    assert s.level() == "off"
    c.t += 1
    assert s.level() == "off"
    s.activity()
    assert s.level() == "acting"


def test_pure_helpers():
    assert bd.parse_color("#E0461D") == (0xE0, 0x46, 0x1D) and bd.parse_color("nonsense") == (0xE0, 0x46, 0x1D)
    vals = [bd.pulse_factor(t / 20) for t in range(60)]
    assert 0.59 <= min(vals) and max(vals) <= 1.0 and max(vals) - min(vals) > 0.3
    assert bd.pulse_factor(0.37, steady=True) == 1.0     # reduce-motion: steady
    assert bd.edge_alpha(0, "acting") == 255 and bd.edge_alpha(5, "acting") == 255 and bd.edge_alpha(60, "acting") == 0
    assert 0 < bd.edge_alpha(10, "acting") < 255
    assert bd.edge_alpha(7, "locked") == 255 and bd.edge_alpha(7, "acting") < 255   # locked frame is thicker


def test_frame_bitmap_has_frame_and_empty_center():
    w, h = 120, 90
    data = bd.build_frame_bytes(w, h, (0xE0, 0x46, 0x1D), "acting")
    assert len(data) == w * h * 4

    def pixel(x, y):
        o = (y * w + x) * 4
        return tuple(data[o:o + 4])   # B, G, R, A (premultiplied)

    assert pixel(60, 2) == (0x1D, 0x46, 0xE0, 255)       # frame is solid orange
    assert pixel(2, 45)[3] == 255 and pixel(w - 3, 45)[3] == 255 and pixel(60, h - 3)[3] == 255
    assert pixel(60, 45) == (0, 0, 0, 0)                  # center fully transparent


def test_indicator_config_and_defaults():
    d = rules._read_toml(rules.DEFAULT_RULES_FILE)
    for preset in ("easy", "balanced", "strict"):
        assert rules.build_ruleset(d, None, preset).indicator == {"border": True, "color": "#E0461D"}
    r = rules.build_ruleset(d, {"desktop": {"indicator": {"border": False, "color": "#00FF00"}}}, "easy")
    assert r.indicator == {"border": False, "color": "#00FF00"}


# ---------------------------------------------------------------- engine wiring (no window is drawn)

def test_only_acting_calls_trigger_the_glow(launch_app, desktop):
    d = launch_app("turbo_fixture.exe")
    assert desktop.indicator.state.level() == "off"
    desktop.windows_list()
    desktop.inspect(d["id"])
    desktop.screenshot(d["id"])
    assert desktop.indicator.state.level() == "off"          # read-only calls never glow
    desktop.act(d["id"], "click", name="Count 0")
    assert desktop.indicator.state.level() == "acting"
    desktop.indicator.state.last_activity = None
    desktop.batch([{"action": "click", "name": "Count 1"}], window=d["id"])
    assert desktop.indicator.state.level() == "acting"
    desktop.indicator.state.last_activity = None
    desktop.window_control(d["id"], "minimize")
    assert desktop.indicator.state.level() == "acting"


def test_stop_hides_the_glow(launch_app, desktop):
    d = launch_app("turbo_fixture.exe")
    desktop.act(d["id"], "click", name="Count 0")
    (sec.state_dir() / "STOP").write_text("x")
    with pytest.raises(Exception):
        desktop.act(d["id"], "click", name="Count 0")
    assert desktop.indicator.state.level() == "off"


# ---------------------------------------------------------------- live windows

def style(hwnd):
    return ctypes.windll.user32.GetWindowLongW(wintypes.HWND(hwnd), -20) & 0xFFFFFFFF


def count_windows(cls):
    n = [0]

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _):
        buf = ctypes.create_unicode_buffer(64)
        ctypes.windll.user32.GetClassNameW(h, buf, 64)
        if buf.value == cls:
            n[0] += 1
        return True

    ctypes.windll.user32.EnumWindows(cb, 0)
    return n[0]


def wait_until(fn, secs=4.0):
    end = time.time() + secs
    while time.time() < end:
        if fn():
            return True
        time.sleep(0.1)
    return fn()


def test_windows_on_every_monitor_click_through_no_focus_and_destroyed():
    c = bd.GlowState()
    g = bd.Glow(c, window_class="TurboDesktopGlowT1", tick_ms=40)
    fg_before = ctypes.windll.user32.GetForegroundWindow()
    c.set_locked(True)      # solid frame: deterministic pixels
    g.start()
    try:
        assert wait_until(lambda: len(g.hwnds) == len(bd.monitors()) and g.visible_level == "locked")
        assert count_windows("TurboDesktopGlowT1") == len(bd.monitors()) >= 1
        for h in g.hwnds:
            ex = style(h)
            for flag in (bd.WS_EX_TOPMOST, bd.WS_EX_LAYERED, bd.WS_EX_TRANSPARENT, bd.WS_EX_NOACTIVATE, bd.WS_EX_TOOLWINDOW):
                assert ex & flag, hex(flag)
        time.sleep(0.5)
        fg_after = ctypes.windll.user32.GetForegroundWindow()
        assert fg_after not in g.hwnds                                   # never takes the focus (the owner may switch windows)
        assert fg_after == fg_before or fg_after != 0
        # field check: the frame pixels really are on screen at the edges (primary monitor)
        from PIL import ImageGrab
        x, y, w, h = bd.monitors()[0]
        try:
            img = ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True).convert("RGB")
        except OSError:
            from turbo_desktop import winsys
            img, _ = winsys.capture_window(g.hwnds[0])
            img = img.convert("RGB")
        hits = 0
        for px in ((w // 2, 2), (w // 2, h - 3), (2, h // 2), (w - 3, h // 2)):
            r, gg, b = img.getpixel(px)
            hits += abs(r - 0xE0) < 12 and abs(gg - 0x46) < 12 and abs(b - 0x1D) < 12
        # at least 3 of 4 edges: a full-screen app of the owner may cover one edge of the real screen
        assert hits >= 3, hits
        assert img.getpixel((w // 2, h // 2)) != (0xE0, 0x46, 0x1D)
        img.save(str(sec.state_dir() / "glow_screenshot.png"))
    finally:
        c.set_locked(False)
    assert wait_until(lambda: count_windows("TurboDesktopGlowT1") == 0)
    g.close()


def test_stop_file_removes_windows_quickly():
    c = bd.GlowState()
    g = bd.Glow(c, window_class="TurboDesktopGlowT2")
    c.set_locked(True)
    g.start()
    try:
        assert wait_until(lambda: g.visible_level == "locked")
        (sec.state_dir() / "STOP").write_text("x")
        assert wait_until(lambda: count_windows("TurboDesktopGlowT2") == 0, 2.0)
    finally:
        g.close()


def test_close_removes_windows_even_while_showing():
    c = bd.GlowState()
    g = bd.Glow(c, window_class="TurboDesktopGlowT3")
    c.set_locked(True)
    g.start()
    assert wait_until(lambda: g.visible_level == "locked")
    g.close()
    assert count_windows("TurboDesktopGlowT3") == 0
