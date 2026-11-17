import ctypes
import time

import pytest
from ctypes import wintypes

from turbo_desktop import inputlock as il, rules, security as sec, winsys

K = il.VK_K


def phys(vk, down=True):
    return dict(vk=vk, down=down, flags=0)


# ---------------------------------------------------------------- pure logic with fake flags

def test_physical_keys_and_mouse_are_swallowed_injected_pass():
    p = il.Policy()
    assert p.key(0x41, True, 0) == (True, None)
    assert p.key(0x41, True, il.LLKHF_INJECTED) == (False, None)
    assert p.mouse(0) is True
    assert p.mouse(il.LLMHF_INJECTED) is False
    assert p.physical_events == 2 and p.injected_events == 2


def test_stop_hotkey_needs_all_three_modifiers_and_physical_k():
    p = il.Policy()
    assert p.key(0xA2, True, 0)[1] is None            # left ctrl
    assert p.key(0xA4, True, 0)[1] is None            # left alt
    assert p.key(K, True, 0)[1] is None               # no shift yet
    p.key(K, False, 0)
    assert p.key(0xA0, True, 0)[1] is None            # left shift
    assert p.key(K, True, 0) == (True, "stop")
    # injected modifiers never count
    q = il.Policy()
    for vk in (0x11, 0x12, 0x10):
        q.key(vk, True, il.LLKHF_INJECTED)
    assert q.key(K, True, 0)[1] is None


def test_esc_x3_within_window_is_takeover():
    t = [0.0]
    p = il.Policy(now=lambda: t[0])
    for i in range(2):
        assert p.key(il.VK_ESCAPE, True, 0) == (True, None)
        p.key(il.VK_ESCAPE, False, 0)
        t[0] += 0.4
    assert p.key(il.VK_ESCAPE, True, 0) == (True, "takeover")


def test_esc_too_slow_or_held_down_is_not_takeover():
    t = [0.0]
    p = il.Policy(now=lambda: t[0])
    for i in range(3):
        assert p.key(il.VK_ESCAPE, True, 0)[1] is None
        p.key(il.VK_ESCAPE, False, 0)
        t[0] += 1.0   # 3 presses over 2 s: outside the 1.5 s window
    q = il.Policy(now=lambda: t[0])
    for i in range(10):                       # auto-repeat while held counts once
        r = q.key(il.VK_ESCAPE, True, 0)
    assert r[1] is None
    z = il.Policy(now=lambda: t[0])
    for i in range(3):                        # injected Esc never counts
        assert z.key(il.VK_ESCAPE, True, il.LLKHF_INJECTED) == (False, None)


def test_max_seconds_is_clamped():
    assert il.clamp_seconds(1) == 5 and il.clamp_seconds(9999) == 300 and il.clamp_seconds("x") == 60 and il.clamp_seconds(45) == 45


def test_mode_per_preset_and_user_override():
    d = rules._read_toml(rules.DEFAULT_RULES_FILE)
    assert rules.build_ruleset(d, None, "easy").input_lock["mode"] == "real_input"
    assert rules.build_ruleset(d, None, "balanced").input_lock["mode"] == "real_input"
    assert rules.build_ruleset(d, None, "strict").input_lock["mode"] == "whole_task"
    assert rules.build_ruleset(d, None, "easy").input_lock["max_seconds"] == 60
    user = {"desktop": {"input_lock": {"mode": "off", "max_seconds": 1000}}}
    r = rules.build_ruleset(d, user, "strict").input_lock
    assert r == {"mode": "off", "max_seconds": 300}
    assert rules.build_ruleset(d, {"desktop": {"input_lock": {"mode": "bogus"}}}, "strict").input_lock["mode"] == "whole_task"


# ---------------------------------------------------------------- live hook tests (owner must be away)

needs_idle = pytest.mark.usefixtures("owner_away")   # evaluated when the test runs, not at collection


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", ctypes.c_byte * 24), ("padding", ctypes.c_byte * 32)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


def send_f24():
    """Inject F24 down/up with SendInput (harmless key). Injected events must pass the hook."""
    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.c_size_t)]

    class IN(ctypes.Structure):
        class U(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]
        _anonymous_ = ("u",)
        _fields_ = [("type", wintypes.DWORD), ("u", U)]

    arr = (IN * 2)(IN(1, IN.U(ki=KEYBDINPUT(0x87, 0, 0, 0, 0))), IN(1, IN.U(ki=KEYBDINPUT(0x87, 0, 2, 0, 0))))
    ctypes.windll.user32.SendInput(2, ctypes.byref(arr), ctypes.sizeof(IN))


def banner_visible(cls):
    h = ctypes.windll.user32.FindWindowW(cls, None)
    return bool(h) and bool(ctypes.windll.user32.IsWindowVisible(h)), h


@needs_idle
def test_hook_lifecycle_banner_and_injected_pass():
    lock = il.InputLock(banner_class="TurboDesktopBannerT1", linger_ms=400)
    assert not banner_visible("TurboDesktopBannerT1")[0]
    lock.acquire(10)
    try:
        assert lock.locked and banner_visible("TurboDesktopBannerT1")[0]
        # banner is click-through, topmost and does not take focus
        ex = ctypes.windll.user32.GetWindowLongW(wintypes.HWND(lock.banner_hwnd), -20)
        for flag in (il.WS_EX_TOPMOST, il.WS_EX_LAYERED, il.WS_EX_TRANSPARENT, il.WS_EX_NOACTIVATE):
            assert ex & flag
        send_f24()
        time.sleep(0.3)
        assert lock.policy.injected_events >= 2 and lock.policy.physical_events == 0
    finally:
        info = lock.release("test")
    assert not info["locked"] and not info["owner_took_over"]
    time.sleep(1.0)
    assert not banner_visible("TurboDesktopBannerT1")[0]       # end notice gone, window destroyed


@needs_idle
def test_max_seconds_auto_release():
    lock = il.InputLock(banner_class="TurboDesktopBannerT2", linger_ms=200)
    lock.max_seconds = 5
    lock.acquire(0)   # clamped to 5 s
    t0 = time.time()
    while lock.locked and time.time() - t0 < 9:
        time.sleep(0.2)
    assert not lock.locked and lock.reason == "max-seconds" and 4 < time.time() - t0 < 8


@needs_idle
def test_stop_hotkey_and_takeover_release_through_escape_path():
    lock = il.InputLock(banner_class="TurboDesktopBannerT3", linger_ms=200)
    lock.acquire(10)
    lock._escape("stop")        # what the hook calls when it sees Ctrl+Alt+Shift+K
    time.sleep(0.5)
    assert not lock.locked and lock.stopped and (sec.state_dir() / "STOP").exists()
    (sec.state_dir() / "STOP").unlink()
    lock2 = il.InputLock(banner_class="TurboDesktopBannerT4", linger_ms=200)
    lock2.acquire(10)
    lock2._escape("takeover")
    time.sleep(0.5)
    assert not lock2.locked and lock2.taken_over and lock2.reason == "owner-esc-x3"


@needs_idle
def test_real_input_reports_owner_took_over(monkeypatch):
    from turbo_desktop.engine import Desktop, ToolError
    monkeypatch.setenv("TURBO_DESKTOP_NO_INPUT", "0")
    monkeypatch.setenv("TURBO_DESKTOP_IDLE_SECONDS", "1")
    d = Desktop()
    d.lock = il.InputLock(banner_class="TurboDesktopBannerT5", linger_ms=200)
    with pytest.raises(ToolError) as e:
        d.real_input(lambda: d.lock._escape("takeover"))
    assert e.value.extra["owner_took_over"] is True
    assert not d.lock.locked


@needs_idle
def test_hard_kill_takes_hooks_banner_and_glow_with_it():
    """A killed process leaves no hook and no window behind (Windows removes both with the process)."""
    import subprocess
    import sys
    code = (
        "import sys,time; sys.path.insert(0, r'%s'); "
        "from turbo_desktop import inputlock as il, border as bd; "
        "l = il.InputLock(banner_class='TurboDesktopBannerKill'); l.acquire(30); "
        "s = bd.GlowState(); s.set_locked(True); g = bd.Glow(s, window_class='TurboDesktopGlowKill'); g.start(); "
        "print('up', flush=True); time.sleep(60)" % str((__import__('pathlib').Path(il.__file__).resolve().parents[1]))
    )
    p = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
    try:
        assert p.stdout.readline().strip() == "up"
        time.sleep(0.8)
        assert banner_visible("TurboDesktopBannerKill")[0]
        p.kill()
        p.wait(5)
        time.sleep(0.8)
        assert not banner_visible("TurboDesktopBannerKill")[0]
        h = ctypes.windll.user32.FindWindowW("TurboDesktopGlowKill", None)
        assert not h
        # input flows again: an injected+physical-agnostic probe, our own hook is gone so SendInput F24 works untouched
        send_f24()
    finally:
        if p.poll() is None:
            p.kill()


@needs_idle
def test_rapid_reacquire_inside_the_end_notice_does_not_crash():
    """Field bug 16: a second acquire inside the 2.5 s end notice of the first crashed the whole server
    (callbacks of the first lock thread were freed while its window was alive). Run in a subprocess to see a crash."""
    import subprocess
    import sys
    from pathlib import Path
    src = str(Path(il.__file__).resolve().parents[1])
    code = (
        "import sys,time; sys.path.insert(0, r'%s'); from turbo_desktop import inputlock as il; "
        "l = il.InputLock(banner_class='TurboDesktopBannerRapid', linger_ms=2500); "
        "[ (l.acquire(10), time.sleep(0.15), l.end_one(), time.sleep(0.25)) for _ in range(8) ]; "
        "time.sleep(3.5); print('ok', l.locked, l.banner_hwnd, flush=True)" % src)
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (r.returncode, r.stderr[-300:])
    assert r.stdout.strip() == "ok False 0"
