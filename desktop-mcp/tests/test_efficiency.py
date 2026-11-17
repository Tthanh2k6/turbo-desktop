"""Unit and integration tests for Brief B4 efficiency improvements.
Only windows launched by the tests themselves (or mocked windows) are touched."""
import inspect
import json

import pytest

from conftest import FIX
from turbo_desktop import engine, server, winsys
from turbo_desktop.engine import ToolError


class FakeCtrl:
    def __init__(self, role: str, name: str = "", aid: str = "", children=None, rid=None, value=None):
        self.ControlTypeName = f"{role}Control"
        self.Name = name
        self.AutomationId = aid
        self._children = list(children or [])
        self._rid = rid
        self.IsEnabled = True
        self.IsOffscreen = False
        self._value = value

    def GetChildren(self):
        return self._children

    def GetRuntimeId(self):
        return self._rid

    def GetPropertyValue(self, _pid):
        return False

    def GetPattern(self, _pid):
        return None


def test_launch_app_returns_first_snapshot_and_supports_delta(desktop):
    r = desktop.launch(str(FIX / "turbo_editor.exe"), "--title B4Editor", wait=8)
    try:
        assert r["ok"] is True and r["windows"]
        w = r["windows"][0]["id"]
        assert "snapshot" in r
        assert "<<<SCREEN_CONTENT" in r["snapshot"] and "Text editor" in r["snapshot"]
        assert len(r["snapshot"]) <= 1800  # default snapshotMaxChars=1500 + wrapper

        # Subsequent act with returnSnapshot=True returns ONLY the changed control (delta)
        act_res = desktop.act(w, "set_value", name="Text editor", text="hello b4", return_snapshot=True)
        assert act_res["ok"] is True and "snapshot" in act_res
        assert '~[' in act_res["snapshot"] and 'hello b4' in act_res["snapshot"]
        assert "-- delta:" in act_res["snapshot"]
    finally:
        desktop.close_launched()


def test_launch_app_snapshot_query_and_disable_flag(monkeypatch, desktop):
    win = {"id": "w1", "hwnd": 5151, "title": "FakeApp", "process": "fakeapp", "pid": 111, "focused": True}
    calls = []

    class DummyPopen:
        pid = 111

        def __init__(self, *a, **k):
            pass

    state = [[]]

    def fake_wl(*a, **k):
        res = list(state[0])
        state[0] = [dict(win)]
        return res

    def fake_inspect(window, mode="interactive", query=None, only_changed=False, max_chars=6000, **kw):
        calls.append((window, mode, query, max_chars))
        return f"SNAP({window},{query},{max_chars})"

    monkeypatch.setattr(engine.subprocess, "Popen", DummyPopen)
    monkeypatch.setattr(desktop, "windows_list", fake_wl)
    monkeypatch.setattr(desktop, "inspect", fake_inspect)

    state[0] = []
    r1 = desktop.launch("fakeapp.exe", wait=0.05, snapshot_query="Send", snapshot_max_chars=900)
    assert r1["snapshot"] == "SNAP(w1,Send,900)"
    assert calls[-1] == ("w1", "interactive", "Send", 900)

    state[0] = []
    r2 = desktop.launch("fakeapp.exe", wait=0.05, return_snapshot=False)
    assert "snapshot" not in r2


def test_launch_app_watches_for_launcher_child_and_returns_pending_hint(monkeypatch, desktop):
    """Apps like Zalo start through a launcher process: when windows is empty after the initial wait,
    launch keeps watching for a top-level window of the launched process or resolved app name."""
    shortcuts = [FIX / "Zalo.lnk"]
    monkeypatch.setattr(
        engine,
        "resolve_launch_target",
        lambda target: {"how": "start-menu", "matched": "Zalo", "shortcut": str(shortcuts[0]), "path": str(shortcuts[0])},
    )
    monkeypatch.setattr(engine.os, "startfile", lambda p: None, raising=False)

    # Poll 1-2 (first wait): empty or unrelated window. Poll 3+ (second watch): Zalo window appears under a new PID.
    unrelated = {"id": "w2", "hwnd": 2002, "title": "Background Helper", "process": "helper", "pid": 50, "focused": False}
    zalo_win = {"id": "w3", "hwnd": 3003, "title": "Zalo", "process": "Zalo", "pid": 999, "focused": True}
    seq = [
        [],             # before_list
        [],             # first wait poll 1 -> empty
        [unrelated],    # second watch poll 1 -> unrelated process ignored
        [unrelated, zalo_win],  # second watch poll 2 -> Zalo matched by resolved app name
        [unrelated, zalo_win],
    ]
    idx = [0]

    def fake_wl(*a, **k):
        i = min(idx[0], len(seq) - 1)
        idx[0] += 1
        return [dict(x) for x in seq[i]]

    monkeypatch.setattr(desktop, "windows_list", fake_wl)
    out = desktop.launch("zalo", wait=0.2)
    assert out["ok"] is True
    assert [w["id"] for w in out["windows"]] == ["w3"]
    assert "snapshot" in out and '"Zalo" (Zalo pid 999)' in out["snapshot"]  # fake hwnd: the engine numbers it itself
    assert "pending" not in out

    # When no window appears at all, launch returns {"ok": True, "pending": True, "hint": ...}
    monkeypatch.setattr(desktop, "windows_list", lambda *a, **k: [])
    pending_out = desktop.launch("zalo", wait=0.05)
    assert pending_out["ok"] is True
    assert pending_out["pending"] is True
    assert "hint" in pending_out and "wait_for" in pending_out["hint"]
    assert pending_out["windows"] == []


def test_act_and_batch_actions_return_delta_snapshot(launch_app, desktop):
    d = launch_app("turbo_fixture.exe")
    w = d["id"]
    first = desktop.inspect(w)
    assert '<Button> "Count 0"' in first and '<Button> "Submit"' in first

    # Single act with returnSnapshot=True returns only the delta
    r_act = desktop.act(w, "click", name="Count 0", returnSnapshot=True)
    assert r_act["ok"] is True and "snapshot" in r_act
    assert "Count 1" in r_act["snapshot"] and "-- delta:" in r_act["snapshot"]
    assert "Submit" not in r_act["snapshot"]

    # batch_actions with returnSnapshot=True returns only the delta since the previous snapshot
    r_batch = desktop.batch(
        [
            {"action": "set_value", "name": "Full name", "text": "B4 User"},
            {"action": "click", "name": "Count 1"},
        ],
        window=w,
        returnSnapshot=True,
    )
    assert r_batch["ok"] is True and "snapshot" in r_batch
    assert "B4 User" in r_batch["snapshot"] and "Count 2" in r_batch["snapshot"]
    assert "Submit" not in r_batch["snapshot"]


def test_windows_list_compact_format_filters_irrelevant_and_keeps_markers(monkeypatch, desktop):
    raw_windows = [
        {"hwnd": 10, "title": "Calculator", "pid": 100, "class": "ApplicationFrameWindow", "width": 400, "height": 500},
        {"hwnd": 20, "title": "Cloaked UWP", "pid": 101, "class": "ApplicationFrameWindow", "cloaked": True},
        {"hwnd": 30, "title": "Zero Sized", "pid": 102, "class": "Dummy", "width": 0, "height": 0},
        {"hwnd": 40, "title": "Tray", "pid": 103, "class": "Shell_TrayWnd"},
        {"hwnd": 50, "title": "turbo-desktop glow", "pid": 104, "class": "TurboDesktopGlow"},
        {"hwnd": 60, "title": "turbo-desktop", "pid": 104, "class": "TurboDesktopBanner"},
        {"hwnd": 70, "title": ".env - Notepad", "pid": 105, "class": "Notepad"},
        {"hwnd": 80, "title": "Windows Security", "pid": 106, "class": " ApplicationFrameWindow"},
    ]
    procs = {
        100: ("CalculatorApp", False),
        101: ("CloakedApp", False),
        102: ("ZeroApp", False),
        103: ("explorer", False),
        104: ("python", False),
        105: ("notepad", False),
        106: ("SecurityHealthUI", False),
    }
    monkeypatch.setattr(winsys, "enum_top_windows", lambda hidden=False: list(raw_windows))
    monkeypatch.setattr(winsys, "process_info", lambda pid: procs[pid])
    monkeypatch.setattr(engine.win32gui, "GetForegroundWindow", lambda: 10)

    compact = desktop.format_windows_list(verbose=False, hidden=False)
    lines = compact.splitlines()
    # Only Calculator, secret window, and denied window remain; cloaked, zero-size, tray, glow and banner are skipped
    assert len(lines) == 3
    assert lines[0] == "w1 Calculator [CalculatorApp] *focused"
    assert "pid=" not in compact and "hwnd=" not in compact
    assert "[hidden: secret window]" in lines[1] and "[secret]" in lines[1] and "[denied: secret-window]" in lines[1]
    assert ".env" not in compact
    assert "Windows Security [SecurityHealthUI]" in lines[2] and "[denied:" in lines[2]

    # verbose=True includes pid and hwnd
    verbose_out = desktop.format_windows_list(verbose=True, hidden=False)
    assert "pid=100 hwnd=10 *focused" in verbose_out

    # hidden=True includes cloaked, zero-size, tray, and glow/banner windows
    hidden_out = desktop.format_windows_list(verbose=False, hidden=True)
    assert "Cloaked UWP" in hidden_out and "Zero Sized" in hidden_out and "turbo-desktop glow" in hidden_out


def test_inspect_compact_summarises_repeated_siblings_and_keeps_refs_stable(monkeypatch, desktop):
    win = {"id": "w1", "hwnd": 9191, "title": "Zalo", "process": "Zalo", "pid": 77, "focused": True}
    monkeypatch.setattr(desktop, "windows_list", lambda *a, **k: [dict(win)])

    items = [FakeCtrl("ListItem", f"Contact {i}", rid=(10, i)) for i in range(1, 121)]
    search_box = FakeCtrl("Edit", "Search", rid=(1, 1))
    list_ctrl = FakeCtrl("List", "Conversations", children=items, rid=(1, 2))
    send_btn = FakeCtrl("Button", "Send message", rid=(1, 3))
    root = FakeCtrl("Window", "Zalo", children=[search_box, list_ctrl, send_btn], rid=(1, 0))
    monkeypatch.setattr(desktop, "_ctrl_for", lambda d: root)

    snap = desktop.inspect("w1", max_chars=1500)
    assert "ListItem ×120 (first 8 shown; use query= to filter)" in snap
    assert '"Contact 1"' in snap and '"Contact 8"' in snap
    assert '"Contact 9"' not in snap and '"Contact 120"' not in snap
    # Controls after the long sibling list are still preserved instead of cut mid-list
    assert '[w1:e122] <Button> "Send message"' in snap

    # Query filters the full list with the exact same stable ref
    q_snap = desktop.inspect("w1", query="Contact 50")
    assert '[w1:e51] <ListItem> "Contact 50"' in q_snap

    # onlyChanged works across all 122 elements with stable refs
    no_change = desktop.inspect("w1", only_changed=True)
    assert "0 new, 0 changed, 0 removed, 122 unchanged" in no_change

    items[49].Name = "Contact 50 (1 unread)"
    delta = desktop.inspect("w1", only_changed=True)
    assert '~[w1:e51] <ListItem> "Contact 50 (1 unread)"' in delta
    assert "0 new, 1 changed, 0 removed, 121 unchanged" in delta


def test_wait_for_default_timeout_and_reports_seen_windows(launch_app, desktop):
    assert inspect.signature(desktop.wait_for).parameters["timeout"].default == 8.0
    assert inspect.signature(server.wait_for).parameters["timeout"].default == 8.0

    d = launch_app("turbo_fixture.exe")
    with pytest.raises(ToolError) as exc_info:
        desktop.wait_for(window=d["id"], text="NoSuchControlText", timeout=0.3)
    msg = str(exc_info.value)
    assert "timeout" in msg and "TurboFixture" in msg
    assert "TurboFixture" in exc_info.value.extra.get("saw", [])
    assert any(w["id"] == d["id"] and w["title"] == "TurboFixture" for w in exc_info.value.extra.get("windows", []))


def test_tool_docstrings_lead_with_cheapest_pattern():
    assert server.launch_app.__doc__.startswith(
        "launch_app returns the window snapshot; then one batch_actions with returnSnapshot"
    )
    assert "returnSnapshot=true" in server.act.__doc__
    assert "returnSnapshot=true" in server.batch_actions.__doc__
    total_chars = sum(len(getattr(fn, "__doc__", "") or "") for fn in (
        server.windows_list, server.inspect_compact, server.act, server.batch_actions,
        server.launch_app, server.wait_for, server.window_control, server.screenshot, server.system_state,
    ))
    assert total_chars < 1600


def test_batch_success_lists_only_notable_steps(launch_app, desktop):
    d = launch_app("turbo_fixture.exe")
    w = d["id"]
    desktop.inspect(w)
    r = desktop.batch([
        {"action": "set_value", "name": "Full name", "text": "Bo"},
        {"action": "click", "name": "Count 0"},
        {"op": "inspect", "query": "Count", "only_changed": False},
    ], window=w)
    assert r["ok"] is True and r["ran"] == 3
    ids = [s["i"] for s in r["steps"]]   # set_value reports the field state; the plain click is dropped
    assert 1 not in ids and ids[-1] == 2 and "Count 1" in r["steps"][-1]["snapshot"]
    bad = desktop.batch([{"action": "click", "name": "No such button"}], window=w)
    assert bad["ok"] is False and bad["failedAt"] == 0 and "ran" not in bad and len(bad["steps"]) == 1


def test_caption_buttons_hidden_unless_queried():
    class C:
        def __init__(self, n):
            self.Name = n
    f = engine._is_caption_button
    assert f(C("Close Calculator"), "calculator", "") is True
    assert f(C("Minimize"), "calculator", "") is True
    assert f(C("Close Calculator"), "calculator", "close") is False
    assert f(C("Close tab"), "calculator", "") is False
    assert f(C("Submit"), "calculator", "") is False
