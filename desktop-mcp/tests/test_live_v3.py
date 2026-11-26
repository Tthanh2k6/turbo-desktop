import json
from pathlib import Path

from turbo_desktop import border as bd, engine, inputlock as il, security as sec


class FakeClock:
    def __init__(self, t: float = 1000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t


class FakeLock:
    def __init__(self):
        self.locked = False
        self.whole_task = False
        self.remote_task = False
        self.mode = "real_input"
        self.since = None
        self.reason = ""
        self.max_seconds = 60.0
        self.taken_over = False
        self._text = il.BANNER_TEXT
        self._depth = 0
        self.screen_view = False
        self.acquires = []
        self.releases = []

    def acquire(self, max_seconds=60, whole_task=False, remote_task=False, banner_text=None, reason=""):
        self.acquires.append({
            "max_seconds": max_seconds,
            "whole_task": whole_task,
            "remote_task": remote_task,
            "banner_text": banner_text,
            "reason": reason,
        })
        self.locked = True
        self.whole_task = bool(whole_task or remote_task)
        self.remote_task = bool(remote_task)
        self.mode = "whole_task" if self.whole_task else "real_input"
        self.max_seconds = float(max_seconds)
        self.reason = reason
        self._text = banner_text or (il.REMOTE_BANNER_TEXT if remote_task else il.BANNER_TEXT)
        return True

    def release_remote_task(self, reason="task-ended"):
        self.remote_task = False
        if self._depth > 0 and self.locked:
            self.whole_task = False
            self.mode = "real_input"
            self.reason = "real_input"
            self._text = il.BANNER_TEXT
            return {"locked": True, "reason": self.reason}
        return self.release(reason)

    def release(self, reason="done"):
        self.releases.append(reason)
        self.locked = False
        self.whole_task = False
        self.remote_task = False
        self.since = None
        self.reason = reason
        self._depth = 0
        return {"locked": False, "reason": reason}

    def set_screen_view(self, active: bool, start_thread: bool = True):
        self.screen_view = bool(active)
        if active and not self.locked:
            self._text = il.SCREEN_VIEW_TEXT
        elif not active and not self.locked and self._text == il.SCREEN_VIEW_TEXT:
            self._text = il.BANNER_TEXT


# ---------------------------------------------------------------- 1. State-dir bridge files

def test_bridge_noop_when_env_unset(tmp_path, monkeypatch):
    monkeypatch.delenv("TURBO_DESKTOP_STATE_DIR", raising=False)
    assert sec.bridge_dir() is None
    ind = bd.Indicator(disabled_by_env=True)
    ind.activity()
    lock = FakeLock()
    bridge = il.StateBridge(lock=lock, indicator=ind, state_dir=None, allow_windows=False)
    bridge.tick()
    assert list(tmp_path.iterdir()) == []


def test_atomic_write_and_indicator_bridge_states(tmp_path):
    clock = FakeClock(500.0)
    ind = bd.Indicator(disabled_by_env=True, state_dir=tmp_path)
    ind.state.now = clock
    lock = FakeLock()
    bridge = il.StateBridge(lock=lock, indicator=ind, state_dir=tmp_path, now=clock, allow_windows=False)

    bridge.tick()
    assert json.loads((tmp_path / "indicator.json").read_text("utf-8")) == {"state": "idle"}
    assert json.loads((tmp_path / "input_lock.json").read_text("utf-8"))["locked"] is False
    assert list(tmp_path.glob("*.tmp")) == []

    # Acting via pattern activity
    ind.activity()
    assert json.loads((tmp_path / "indicator.json").read_text("utf-8")) == {"state": "acting"}

    # Linger expires after 3s -> back to idle on next tick
    clock.t += 4.0
    bridge.tick()
    assert json.loads((tmp_path / "indicator.json").read_text("utf-8")) == {"state": "idle"}

    # Real input without lock -> acting; with lock -> input_locked
    ind.real_input(True)
    assert json.loads((tmp_path / "indicator.json").read_text("utf-8")) == {"state": "acting"}
    lock.acquire(max_seconds=30, whole_task=False, reason="real_input")
    lock.since = clock.t
    ind.locked(True)
    bridge.tick()
    assert json.loads((tmp_path / "indicator.json").read_text("utf-8")) == {"state": "input_locked"}
    il_data = json.loads((tmp_path / "input_lock.json").read_text("utf-8"))
    assert il_data == {"locked": True, "mode": "real_input", "since": 504.0, "reason": "real_input"}


# ---------------------------------------------------------------- 2. Whole-task lock, staleness, max_minutes, RELEASE, takeover

def test_whole_task_lock_lifecycle_and_staleness(tmp_path):
    clock = FakeClock(1000.0)
    ind = bd.Indicator(disabled_by_env=True, state_dir=tmp_path)
    ind.state.now = clock
    lock = FakeLock()
    bridge = il.StateBridge(lock=lock, indicator=ind, state_dir=tmp_path, now=clock, allow_windows=False)

    sec.atomic_write_json(tmp_path / "task_active.json", {
        "task": "t-1",
        "since": 1000.0,
        "heartbeat": 1000.0,
        "source": "phone",
    })
    bridge.tick()
    assert lock.locked is True
    assert lock.mode == "whole_task"
    assert lock._text == il.REMOTE_BANNER_TEXT
    assert ind.state.level() == "locked"
    assert json.loads((tmp_path / "indicator.json").read_text("utf-8")) == {"state": "input_locked"}
    assert json.loads((tmp_path / "input_lock.json").read_text("utf-8")) == {
        "locked": True,
        "mode": "whole_task",
        "since": 1000.0,
        "reason": "remote_task",
    }

    # The 60s max_seconds cap does NOT apply to whole-task lock: at +120s with fresh heartbeat it stays locked
    clock.t = 1120.0
    sec.atomic_write_json(tmp_path / "task_active.json", {
        "task": "t-1",
        "since": 1000.0,
        "heartbeat": 1110.0,
        "source": "phone",
    })
    bridge.tick()
    assert lock.locked is True and len(lock.acquires) == 1

    # Heartbeat >= 15s old -> stale -> release
    clock.t = 1125.0  # 1125 - 1110 == 15.0s
    bridge.tick()
    assert lock.locked is False
    il_data = json.loads((tmp_path / "input_lock.json").read_text("utf-8"))
    assert il_data["locked"] is False and il_data["reason"] == "stale-heartbeat"
    assert json.loads((tmp_path / "indicator.json").read_text("utf-8")) == {"state": "idle"}


def test_whole_task_lock_respects_active_real_input_on_missing_or_stale(tmp_path):
    clock = FakeClock(2000.0)
    ind = bd.Indicator(disabled_by_env=True, state_dir=tmp_path)
    ind.state.now = clock
    lock = FakeLock()
    bridge = il.StateBridge(lock=lock, indicator=ind, state_dir=tmp_path, now=clock, allow_windows=False)

    sec.atomic_write_json(tmp_path / "task_active.json", {
        "task": "t-2",
        "since": 2000.0,
        "heartbeat": 2000.0,
        "source": "phone",
    })
    bridge.tick()
    assert lock.locked is True and lock.remote_task is True

    # Simulate a real-input action currently holding the lock when task_active.json disappears
    lock._depth = 1
    (tmp_path / "task_active.json").unlink()
    bridge.tick()
    assert lock.locked is True
    assert lock.remote_task is False
    assert lock.mode == "real_input"
    assert lock._text == il.BANNER_TEXT
    assert json.loads((tmp_path / "input_lock.json").read_text("utf-8"))["locked"] is True

    # Once the real-input action finishes, releasing updates the bridge file
    lock._depth = 0
    lock.release("done")
    bridge.tick()
    assert json.loads((tmp_path / "input_lock.json").read_text("utf-8"))["locked"] is False


def test_whole_task_max_minutes_cap(tmp_path):
    clock = FakeClock(3000.0)
    ind = bd.Indicator(disabled_by_env=True, state_dir=tmp_path)
    ind.state.now = clock
    lock = FakeLock()
    bridge = il.StateBridge(lock=lock, indicator=ind, state_dir=tmp_path, now=clock, allow_windows=False)

    sec.atomic_write_json(tmp_path / "task_active.json", {
        "task": "t-cap",
        "since": 3000.0,
        "heartbeat": 3000.0,
        "max_minutes": 10,
    })
    bridge.tick()
    assert lock.locked is True and lock.max_seconds == 600.0

    # At 9 min 59 s with fresh heartbeat -> still locked
    clock.t = 3599.0
    sec.atomic_write_json(tmp_path / "task_active.json", {
        "task": "t-cap",
        "since": 3000.0,
        "heartbeat": 3598.0,
        "max_minutes": 10,
    })
    bridge.tick()
    assert lock.locked is True

    # At 10 min (600 s) -> released with reason max-minutes even though heartbeat is fresh
    clock.t = 3600.0
    sec.atomic_write_json(tmp_path / "task_active.json", {
        "task": "t-cap",
        "since": 3000.0,
        "heartbeat": 3599.0,
        "max_minutes": 10,
    })
    bridge.tick()
    assert lock.locked is False
    il_data = json.loads((tmp_path / "input_lock.json").read_text("utf-8"))
    assert il_data["locked"] is False and il_data["reason"] == "max-minutes"


def test_release_file_and_owner_takeover(tmp_path):
    clock = FakeClock(4000.0)
    ind = bd.Indicator(disabled_by_env=True, state_dir=tmp_path)
    ind.state.now = clock
    lock = FakeLock()
    bridge = il.StateBridge(lock=lock, indicator=ind, state_dir=tmp_path, now=clock, allow_windows=False)

    sec.atomic_write_json(tmp_path / "task_active.json", {
        "task": "t-rel",
        "since": 4000.0,
        "heartbeat": 4000.0,
    })
    bridge.tick()
    assert lock.locked is True

    # Honour <state>/RELEASE: release immediately and delete the file
    rel = tmp_path / "RELEASE"
    rel.write_text("takeover", encoding="utf-8")
    bridge.tick()
    assert not rel.exists()
    assert lock.locked is False
    assert json.loads((tmp_path / "input_lock.json").read_text("utf-8"))["reason"] == "release"

    # New task starts -> locks again; Esc x3 takeover writes owner_took_over.json = {"at": epoch}
    clock.t = 4010.0
    sec.atomic_write_json(tmp_path / "task_active.json", {
        "task": "t-esc",
        "since": 4010.0,
        "heartbeat": 4010.0,
    })
    bridge.tick()
    assert lock.locked is True

    clock.t = 4012.5
    lock.taken_over = True
    bridge.tick()
    assert lock.locked is False
    took = json.loads((tmp_path / "owner_took_over.json").read_text("utf-8"))
    assert took == {"at": 4012.5}
    assert json.loads((tmp_path / "input_lock.json").read_text("utf-8"))["reason"] == "owner-esc-x3"


def test_whole_task_with_input_lock_disabled_reports_acting(tmp_path, monkeypatch):
    monkeypatch.setenv("TURBO_DESKTOP_INPUT_LOCK", "0")
    clock = FakeClock(5000.0)
    ind = bd.Indicator(disabled_by_env=True, state_dir=tmp_path)
    ind.state.now = clock
    lock = FakeLock()
    bridge = il.StateBridge(lock=lock, indicator=ind, state_dir=tmp_path, now=clock, allow_windows=False)

    sec.atomic_write_json(tmp_path / "task_active.json", {
        "task": "t-nolock",
        "since": 5000.0,
        "heartbeat": 5000.0,
    })
    bridge.tick()
    assert lock.locked is False
    assert json.loads((tmp_path / "input_lock.json").read_text("utf-8"))["locked"] is False
    assert json.loads((tmp_path / "indicator.json").read_text("utf-8")) == {"state": "acting"}


# ---------------------------------------------------------------- 3. Screen-view banner

def test_screen_view_banner_without_lock(tmp_path):
    clock = FakeClock(6000.0)
    lock = FakeLock()
    bridge = il.StateBridge(lock=lock, state_dir=tmp_path, now=clock, allow_windows=False)

    sec.atomic_write_json(tmp_path / "screen_view.json", {"until": 6005.0})
    bridge.tick()
    assert bridge.screen_view_active is True
    assert lock.screen_view is True
    assert lock.locked is False
    assert lock._text == il.SCREEN_VIEW_TEXT == "Phone is viewing the screen"
    assert bridge.banner_text == "Phone is viewing the screen"

    # Once `until` is in the past, the banner is hidden
    clock.t = 6006.0
    bridge.tick()
    assert bridge.screen_view_active is False
    assert lock.screen_view is False
    assert bridge.banner_text == ""


# ---------------------------------------------------------------- 4. launch_app Start Menu & AppsFolder matcher

def test_match_start_menu_exact_prefix_and_vietnamese_diacritics():
    fake_shortcuts = [
        Path(r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Zalo\Zalo Updater.lnk"),
        Path(r"C:\Users\Owner\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Zalo.lnk"),
        Path(r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Cốc Cốc\Trình duyệt Cốc Cốc.lnk"),
        Path(r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Cốc Cốc\Cốc Cốc.lnk"),
        Path(r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Accessories\Bản đồ.lnk"),
        Path(r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Accessories\Điện thoại.lnk"),
        Path(r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Notes.txt"),
    ]
    # Exact match beats prefix match ("Zalo.lnk" over "Zalo Updater.lnk")
    assert engine.match_start_menu("zalo", fake_shortcuts).name == "Zalo.lnk"
    assert engine.match_start_menu("ZALO", fake_shortcuts).name == "Zalo.lnk"
    assert engine.match_start_menu("zalo up", fake_shortcuts).name == "Zalo Updater.lnk"

    # Vietnamese diacritics (including đ/Đ) are insensitive both ways
    assert engine.match_start_menu("coc coc", fake_shortcuts).name == "Cốc Cốc.lnk"
    assert engine.match_start_menu("cốc", fake_shortcuts).name == "Cốc Cốc.lnk"
    assert engine.match_start_menu("trinh duyet", fake_shortcuts).name == "Trình duyệt Cốc Cốc.lnk"
    assert engine.match_start_menu("ban do", fake_shortcuts).name == "Bản đồ.lnk"
    assert engine.match_start_menu("dien thoai", fake_shortcuts).name == "Điện thoại.lnk"
    assert engine.match_start_menu("ĐIỆN", fake_shortcuts).name == "Điện thoại.lnk"

    # Non-.lnk files are ignored
    assert engine.match_start_menu("notes", fake_shortcuts) is None
    assert engine.match_start_menu("nonexistent", fake_shortcuts) is None


def test_parse_and_match_start_apps_and_10min_cache():
    table_raw = """
Name                      AppID
----                      -----
Calculator                Microsoft.WindowsCalculator_8wekyb3d8bbwe!App
Đồng hồ báo thức          Microsoft.WindowsAlarms_8wekyb3d8bbwe!App
Zalo UWP                  ZaloGroup.Zalo_12345!App
"""
    apps = engine.parse_start_apps(table_raw)
    assert len(apps) == 3
    assert engine.match_start_apps("dong ho", apps) == {
        "name": "Đồng hồ báo thức",
        "app_id": "Microsoft.WindowsAlarms_8wekyb3d8bbwe!App",
    }
    assert engine.match_start_apps("calc", apps)["name"] == "Calculator"

    json_raw = json.dumps([{"Name": "Photos", "AppID": "Microsoft.Windows.Photos_8wekyb3d8bbwe!App"}])
    assert engine.parse_start_apps(json_raw) == [{"name": "Photos", "app_id": "Microsoft.Windows.Photos_8wekyb3d8bbwe!App"}]

    # 10-minute cache test
    clock = FakeClock(100.0)
    calls = [0]

    def fake_runner():
        calls[0] += 1
        return table_raw

    res1 = engine.list_start_apps(now=clock, runner=fake_runner, ttl=600.0, force_refresh=True)
    clock.t += 300.0  # 5 min later: still cached
    res2 = engine.list_start_apps(now=clock, runner=fake_runner, ttl=600.0)
    assert calls[0] == 1 and res1 == res2

    clock.t += 301.0  # > 10 min: refreshed
    engine.list_start_apps(now=clock, runner=fake_runner, ttl=600.0)
    assert calls[0] == 2


def test_resolve_launch_target_order_and_launch_startfile(monkeypatch, desktop):
    shortcuts = [Path(r"C:\Users\Owner\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Zalo.lnk")]
    uwp_apps = [{"name": "UniKey UWP", "app_id": "UniKey.App!Main"}]

    # 1. PATH wins when present
    r_path = engine.resolve_launch_target(
        "notepad",
        which_fn=lambda x: r"C:\Windows\System32\notepad.exe",
        app_paths_fn=lambda x: None,
        shortcuts=shortcuts,
        start_apps=uwp_apps,
    )
    assert r_path["how"] == "path" and r_path["matched"] == "notepad.exe"

    # 2. Start Menu .lnk when not on PATH / App Paths
    r_sm = engine.resolve_launch_target(
        "zalo",
        which_fn=lambda x: None,
        app_paths_fn=lambda x: None,
        shortcuts=shortcuts,
        start_apps=uwp_apps,
    )
    assert r_sm == {
        "how": "start-menu",
        "matched": "Zalo",
        "shortcut": str(shortcuts[0]),
        "path": str(shortcuts[0]),
    }

    # 3. UWP shell:AppsFolder when not in Start Menu
    r_uwp = engine.resolve_launch_target(
        "unikey",
        which_fn=lambda x: None,
        app_paths_fn=lambda x: None,
        shortcuts=shortcuts,
        start_apps=uwp_apps,
    )
    assert r_uwp == {
        "how": "appsfolder",
        "matched": "UniKey UWP",
        "appId": "UniKey.App!Main",
        "path": r"shell:AppsFolder\UniKey.App!Main",
    }

    # 4. Desktop.launch uses os.startfile for Start Menu / AppsFolder and never returns a pre-existing window
    started = []
    monkeypatch.setattr(engine.os, "startfile", lambda p: started.append(p), raising=False)
    monkeypatch.setattr(engine, "resolve_launch_target", lambda target: r_sm)
    existing = {"id": "w5", "hwnd": 9999, "title": "Zalo", "process": "zalo", "pid": 42, "focused": True}
    monkeypatch.setattr(desktop, "windows_list", lambda *a, **k: [dict(existing)])

    out = desktop.launch("zalo", wait=0.3)
    assert started == [str(shortcuts[0])]
    assert out["ok"] is True
    assert out["how"] == "start-menu" and out["matched"] == "Zalo"
    assert out["reused_existing_window"] is True and out["windows"] == []


# ---------------------------------------------------------------- field bug 18/11: still "working" after the task ended

def _task_file(d, t, hb):
    sec.atomic_write_json(d / "task_active.json", {"task": "t-9", "since": t, "heartbeat": hb, "source": "phone"})


def test_task_ends_during_real_input_then_everything_is_released(tmp_path):
    clock = FakeClock(1000.0)
    ind = bd.Indicator(disabled_by_env=True, state_dir=tmp_path)
    ind.state.now = clock
    lock = FakeLock()
    bridge = il.StateBridge(lock=lock, indicator=ind, state_dir=tmp_path, now=clock, allow_windows=False)
    _task_file(tmp_path, 1000.0, 1000.0)
    bridge.tick()
    assert lock.locked and ind.state.locked

    # a real-input action is in flight when the hub deletes task_active.json
    lock._depth = 1
    ind.real_input(True)
    (tmp_path / "task_active.json").unlink()
    clock.t += 1
    bridge.tick()
    assert lock.locked and lock.mode == "real_input"      # the running click keeps its short lock
    assert ind.state.locked is False                      # the whole-task frame is handed over

    # the action ends but its release is missed (the race seen in the field): the next tick cleans up
    lock._depth = 0
    ind.real_input(False)
    clock.t += 1
    bridge.tick()
    assert lock.locked is False
    assert json.loads((tmp_path / "input_lock.json").read_text("utf-8"))["locked"] is False
    assert json.loads((tmp_path / "indicator.json").read_text("utf-8")) == {"state": "acting"}   # short afterglow only
    assert bridge.banner_text == ""
    clock.t += 4
    bridge.tick()
    assert json.loads((tmp_path / "indicator.json").read_text("utf-8")) == {"state": "idle"}


def test_frame_left_locked_without_a_lock_is_cleared(tmp_path):
    clock = FakeClock(1000.0)
    ind = bd.Indicator(disabled_by_env=True, state_dir=tmp_path)
    ind.state.now = clock
    lock = FakeLock()
    bridge = il.StateBridge(lock=lock, indicator=ind, state_dir=tmp_path, now=clock, allow_windows=False)
    ind.locked(True)            # orange frame says "locked", but nothing holds the input and no task runs
    bridge.tick()
    assert ind.state.locked is False
    assert json.loads((tmp_path / "indicator.json").read_text("utf-8")) == {"state": "idle"}


def test_unreadable_task_file_mid_replace_does_not_end_the_task(tmp_path):
    clock = FakeClock(1000.0)
    ind = bd.Indicator(disabled_by_env=True, state_dir=tmp_path)
    ind.state.now = clock
    lock = FakeLock()
    bridge = il.StateBridge(lock=lock, indicator=ind, state_dir=tmp_path, now=clock, allow_windows=False)
    _task_file(tmp_path, 1000.0, 1000.0)
    bridge.tick()
    assert lock.locked
    (tmp_path / "task_active.json").write_text("{", "utf-8")   # half-written / sharing violation
    clock.t += 1
    bridge.tick()
    assert lock.locked and lock.releases == []
    _task_file(tmp_path, 1000.0, clock.t)
    bridge.tick()
    assert lock.locked and lock.releases == []
    (tmp_path / "task_active.json").unlink()
    bridge.tick()
    assert lock.locked is False and lock.releases


def test_local_whole_task_linger_is_left_alone(tmp_path):
    clock = FakeClock(1000.0)
    lock = FakeLock()
    bridge = il.StateBridge(lock=lock, indicator=None, state_dir=tmp_path, now=clock, allow_windows=False)
    lock.acquire(max_seconds=30, whole_task=True, reason="whole_task")   # Strict preset, local run: lingers on purpose
    bridge.tick()
    assert lock.locked and lock.releases == []
