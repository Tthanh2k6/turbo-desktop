"""Unit and integration tests for turbo-desktop-mcp v0.2.0 P0 upgrades:
- settleMs (0 default, 100-1000 ms) on act and batch_actions
- per-window UIA timeout (TURBO_DESKTOP_WINDOW_TIMEOUT, default 4.0s) and [desktop.apps] exclude_processes
- CLI turbo-desktop-mcp --install (--dry-run, --client claude-desktop|claude-code|cursor|windsurf|all, MS Store Claude_*)
- v0.2.0 version metadata consistency
"""
from __future__ import annotations

import inspect
import json
import time
import tomllib
from pathlib import Path

import pytest

import turbo_desktop
from turbo_desktop import engine, rules, security as sec, server, winsys
from turbo_desktop.engine import Desktop, ToolError, normalize_settle_ms, window_timeout


# ---------------------------------------------------------------- 1. settleMs

def test_normalize_settle_ms_bounds():
    assert normalize_settle_ms(None) == 0
    assert normalize_settle_ms(0) == 0
    assert normalize_settle_ms(-50) == 0
    assert normalize_settle_ms(False) == 0
    assert normalize_settle_ms(50) == 100
    assert normalize_settle_ms(100) == 100
    assert normalize_settle_ms(250) == 250
    assert normalize_settle_ms(1000) == 1000
    assert normalize_settle_ms(2500) == 1000
    with pytest.raises(ToolError, match="invalid settleMs"):
        normalize_settle_ms("not-a-number")


def test_settle_uia_waits_for_tree_to_stop_changing(tmp_path, monkeypatch):
    sleeps: list[float] = []
    dt = Desktop(audit=sec.AuditLog(tmp_path / "audit.jsonl"), sleep_fn=sleeps.append)
    fake_win = {"id": "w1", "hwnd": 101, "title": "FakeApp", "process": "fakeapp", "pid": 999}

    # settleMs=0 does nothing
    assert dt._settle_uia(fake_win, 0) == 0
    assert sleeps == []

    # Static tree: waits exactly target settleMs (200ms = 4 x 50ms steps)
    probes = [("win", ("btn1",))]
    monkeypatch.setattr(dt, "_tree_probe", lambda d: probes[0])
    settled = dt._settle_uia(fake_win, 200)
    assert settled == 200
    assert len(sleeps) == 4

    # Mutating tree: changes on poll 1 and poll 2, then stabilizes for 200ms -> 2x50ms + 4x50ms = 300ms total
    sleeps.clear()
    seq = iter([
        ("win", ("v0",)),  # initial probe
        ("win", ("v1",)),  # poll 1: changed -> reset quiet_s
        ("win", ("v2",)),  # poll 2: changed -> reset quiet_s
        ("win", ("v2",)),  # poll 3: quiet 50ms
        ("win", ("v2",)),  # poll 4: quiet 100ms
        ("win", ("v2",)),  # poll 5: quiet 150ms
        ("win", ("v2",)),  # poll 6: quiet 200ms -> done
    ])
    monkeypatch.setattr(dt, "_tree_probe", lambda d: next(seq))
    settled_mut = dt._settle_uia(fake_win, 200)
    assert settled_mut == 300
    assert len(sleeps) == 6

    # Perpetually mutating tree: capped at 2x settleMs (400ms for settleMs=200)
    sleeps.clear()
    counter = {"n": 0}

    def always_changing(d):
        counter["n"] += 1
        return ("win", (counter["n"],))

    monkeypatch.setattr(dt, "_tree_probe", always_changing)
    settled_cap = dt._settle_uia(fake_win, 200)
    assert settled_cap == 400


def test_act_and_batch_settle_ms_on_fixture(launch_app, desktop):
    d = launch_app("turbo_fixture.exe")
    w = d["id"]
    desktop.inspect(w)

    r1 = desktop.act(w, "click", name="Count 0", settleMs=120, returnSnapshot=True)
    assert r1["ok"] is True
    assert r1["settledMs"] >= 120
    assert "Count 1" in r1["snapshot"]

    r2 = desktop.batch(
        [{"action": "click", "name": "Count 1"}],
        window=w,
        settleMs=150,
        returnSnapshot=True,
    )
    assert r2["ok"] is True
    assert r2["settledMs"] >= 150
    assert "Count 2" in r2["snapshot"]


def test_mcp_tool_signatures_include_settle_ms():
    assert "settleMs" in inspect.signature(server.act).parameters
    assert "settleMs" in inspect.signature(server.batch_actions).parameters
    assert inspect.signature(server.act).parameters["settleMs"].default == 0
    assert inspect.signature(server.batch_actions).parameters["settleMs"].default == 0


# ---------------------------------------------------------------- 2. exclude_processes & TURBO_DESKTOP_WINDOW_TIMEOUT

def test_exclude_processes_in_config_and_env(tmp_path, monkeypatch):
    cfg = tmp_path / "turbo-desktop.toml"
    cfg.write_text(
        '[desktop]\n'
        'preset = "easy"\n'
        '[desktop.apps]\n'
        'exclude_processes = ["Code.exe", "Cursor", "slack.exe"]\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("TURBO_DESKTOP_CONFIG", str(cfg))
    monkeypatch.delenv("TURBO_DESKTOP_EXCLUDE_PROCESSES", raising=False)
    rs = rules.load_ruleset(config_path=cfg)
    assert {"code", "cursor", "slack"} <= rs.exclude_processes
    assert rules.is_excluded_process("Code.exe", rs) is True
    assert rules.is_excluded_process("code", rs) is True
    assert rules.is_excluded_process("vscode", rs) is True
    assert rules.is_excluded_process("Cursor.exe", rs) is True
    assert rules.is_excluded_process("notepad", rs) is False

    monkeypatch.setenv("TURBO_DESKTOP_EXCLUDE_PROCESSES", " Spotify.exe , Discord ")
    assert rules.is_excluded_process("spotify", rs) is True
    assert rules.is_excluded_process("discord.exe", rs) is True


def test_windows_list_and_inspect_skip_excluded_processes(tmp_path, monkeypatch):
    cfg = tmp_path / "turbo-desktop.toml"
    cfg.write_text(
        '[desktop.apps]\n'
        'exclude_processes = ["Code.exe", "cursor"]\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("TURBO_DESKTOP_CONFIG", str(cfg))

    dt = Desktop(audit=sec.AuditLog(tmp_path / "audit.jsonl"))
    fake_raw = [
        {"hwnd": 1001, "title": "project - Visual Studio Code", "pid": 111, "class": "Chrome_WidgetWin_1"},
        {"hwnd": 1002, "title": "Cursor IDE", "pid": 222, "class": "Chrome_WidgetWin_1"},
        {"hwnd": 1003, "title": "Untitled - Notepad", "pid": 333, "class": "Notepad"},
    ]
    pid_map = {111: ("Code", False), 222: ("Cursor", False), 333: ("notepad", False)}
    monkeypatch.setattr(winsys, "enum_top_windows", lambda hidden=False: list(fake_raw))
    monkeypatch.setattr(winsys, "process_info", lambda pid: pid_map[pid])

    wl = dt.windows_list()
    assert [w["process"] for w in wl] == ["notepad"]
    formatted = dt.format_windows_list()
    assert "Notepad" in formatted
    assert "Visual Studio Code" not in formatted
    assert "Cursor" not in formatted

    with pytest.raises(ToolError) as exc_info:
        dt._guard_window({"id": "w9", "hwnd": 1001, "title": "VS Code", "process": "Code", "pid": 111}, "inspect")
    assert exc_info.value.extra.get("excluded") is True


def test_window_timeout_env_and_inspect_timeout(tmp_path, monkeypatch):
    monkeypatch.delenv("TURBO_DESKTOP_WINDOW_TIMEOUT", raising=False)
    assert window_timeout() == 4.0
    monkeypatch.setenv("TURBO_DESKTOP_WINDOW_TIMEOUT", "0.15")
    assert window_timeout() == pytest.approx(0.15)
    monkeypatch.setenv("TURBO_DESKTOP_WINDOW_TIMEOUT", "invalid")
    assert window_timeout() == 4.0

    # Simulate a hung window whose UIA root walk exceeds TURBO_DESKTOP_WINDOW_TIMEOUT with 0 elements
    monkeypatch.setenv("TURBO_DESKTOP_WINDOW_TIMEOUT", "0.1")
    dt = Desktop(audit=sec.AuditLog(tmp_path / "audit.jsonl"))
    fake_win = {"id": "w1", "hwnd": 5555, "title": "HungElectron", "process": "electronapp", "pid": 555}
    monkeypatch.setattr(dt, "find_window", lambda spec: fake_win)

    class HungRoot:
        def GetChildren(self):
            time.sleep(0.25)
            return []

    monkeypatch.setattr(dt, "_ctrl_for", lambda d: HungRoot())
    with pytest.raises(ToolError) as exc_info:
        dt.inspect("w1")
    assert exc_info.value.extra.get("hung") is True
    assert exc_info.value.extra.get("timeout") == pytest.approx(0.1)


def test_server_per_window_timeout_abandons_stuck_worker(monkeypatch):
    monkeypatch.delenv("TURBO_DESKTOP_CALL_TIMEOUT", raising=False)
    monkeypatch.setenv("TURBO_DESKTOP_WINDOW_TIMEOUT", "0.2")
    t0 = time.time()
    out = json.loads(server._guard(lambda: time.sleep(2.0), per_window=True))
    assert out["ok"] is False and out["hung"] is True and (time.time() - t0) < 1.5
    assert server._guard(lambda: "recovered", per_window=True) == "recovered"


# ---------------------------------------------------------------- 3. CLI --install & --dry-run

def test_install_dry_run_all_clients_including_ms_store_claude(tmp_path, monkeypatch):
    home = tmp_path / "home"
    appdata = tmp_path / "appdata"
    localappdata = tmp_path / "localappdata"
    ms_pkg = localappdata / "Packages" / "Claude_pzs8sxrjxfjjc"
    ms_pkg.mkdir(parents=True)
    home.mkdir()
    appdata.mkdir()

    env = {"APPDATA": str(appdata), "LOCALAPPDATA": str(localappdata), "TURBO_DESKTOP_LANG": "en"}
    res = server.install_mcp_config(client="all", dry_run=True, env=env, home=home)
    assert res["ok"] is True
    assert res["dry_run"] is True
    clients = [(t["client"], t["variant"]) for t in res["targets"]]
    assert ("claude-desktop", "standard") in clients
    assert ("claude-desktop", "ms-store") in clients
    assert ("claude-code", "standard") in clients
    assert ("cursor", "standard") in clients
    assert ("windsurf", "standard") in clients

    # Verify dry-run wrote zero files on disk
    for t in res["targets"]:
        assert t["written"] is False
        assert not Path(t["path"]).exists()
        assert t["config"]["mcpServers"]["turbo-desktop"]["command"] == "uvx"
        assert t["config"]["mcpServers"]["turbo-desktop"]["args"] == ["turbo-desktop-mcp"]


def test_install_writes_atomically_and_creates_backup(tmp_path):
    home = tmp_path / "home"
    appdata = tmp_path / "appdata"
    localappdata = tmp_path / "localappdata"
    std_claude = appdata / "Claude" / "claude_desktop_config.json"
    std_claude.parent.mkdir(parents=True)
    std_claude.write_text(
        json.dumps({"globalShortcut": "Ctrl+Space", "mcpServers": {"existing-server": {"command": "node"}}}),
        encoding="utf-8",
    )
    ms_pkg = localappdata / "Packages" / "Claude_msstore123"
    ms_pkg.mkdir(parents=True)

    env = {"APPDATA": str(appdata), "LOCALAPPDATA": str(localappdata)}
    res = server.install_mcp_config(client="claude-desktop", dry_run=False, env=env, home=home)
    assert res["ok"] is True and res["dry_run"] is False
    assert len(res["targets"]) == 2

    # Standard config preserved existing keys and created .bak
    written_std = json.loads(std_claude.read_text(encoding="utf-8"))
    assert written_std["globalShortcut"] == "Ctrl+Space"
    assert "existing-server" in written_std["mcpServers"]
    assert written_std["mcpServers"]["turbo-desktop"]["command"] == "uvx"
    bak_file = std_claude.with_suffix(".json.bak")
    assert bak_file.is_file()

    # MS Store virtualized path was also created and written
    ms_cfg = ms_pkg / "LocalCache" / "Roaming" / "Claude" / "claude_desktop_config.json"
    assert ms_cfg.is_file()
    written_ms = json.loads(ms_cfg.read_text(encoding="utf-8"))
    assert written_ms["mcpServers"]["turbo-desktop"]["args"] == ["turbo-desktop-mcp"]


def test_cli_main_install_dry_run_stdout(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))

    rc = server.main(["--install", "--dry-run", "--client", "cursor"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["dry_run"] is True
    assert out["client"] == "cursor"
    assert len(out["targets"]) == 1
    assert out["targets"][0]["path"].endswith(str(Path(".cursor") / "mcp.json"))


# ---------------------------------------------------------------- 4. Version 0.2.0 metadata

def test_version_020_consistency():
    assert turbo_desktop.__version__ == "0.2.0"
    desktop_root = Path(__file__).resolve().parents[1]
    repo_root = desktop_root.parent
    pyproj = tomllib.loads((desktop_root / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproj["project"]["version"] == "0.2.0"
    srv_json = json.loads((repo_root / "server.json").read_text(encoding="utf-8"))
    assert srv_json["version"] == "0.2.0"
    assert srv_json["packages"][0]["version"] == "0.2.0"
