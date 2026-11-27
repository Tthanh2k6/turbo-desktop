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


# ---------------------------------------------------------------- 5. Cropped screenshot (region, maxWidth), ocrRegion & 1440p/4K benchmark

def test_mcp_tool_signatures_include_region_max_width_and_ocr_region():
    shot_params = inspect.signature(server.screenshot).parameters
    assert "region" in shot_params and shot_params["region"].default is None
    assert "maxWidth" in shot_params and shot_params["maxWidth"].default == 1280

    insp_params = inspect.signature(server.inspect_compact).parameters
    assert "ocrRegion" in insp_params and insp_params["ocrRegion"].default is None


def test_screenshot_region_crop_and_max_width_downscaling(tmp_path, monkeypatch):
    import io
    from PIL import Image

    dt = Desktop(audit=sec.AuditLog(tmp_path / "audit.jsonl"))
    fake_win = {"id": "w1", "hwnd": 4242, "title": "HiDpiCanvas", "process": "canvasapp", "pid": 424}
    monkeypatch.setattr(dt, "find_window", lambda spec: fake_win)
    monkeypatch.setattr(dt, "_guard_window", lambda d, act, uia=True: None)
    monkeypatch.setattr(dt, "_blackout_passwords", lambda img, d=None, ox=0, oy=0, rects=None: img)

    # Simulate a 2560x1440 (1440p) window capture
    monkeypatch.setattr(winsys, "capture_window", lambda hwnd: (Image.new("RGB", (2560, 1440), (30, 60, 90)), (100, 50)))

    # 1. Default maxWidth=1280 downscales full 2560x1440 window to 1280x720
    png_default = dt.screenshot("w1")
    img_default = Image.open(io.BytesIO(png_default))
    assert img_default.size == (1280, 720)

    # 2. Custom maxWidth=1920 downscales 2560x1440 to 1920x1080; maxWidth=3840 preserves full 1:1 2560x1440
    img_1920 = Image.open(io.BytesIO(dt.screenshot("w1", maxWidth=1920)))
    assert img_1920.size == (1920, 1080)
    img_native = Image.open(io.BytesIO(dt.screenshot("w1", max_width=3840)))
    assert img_native.size == (2560, 1440)

    # 3. 1:1 region crop [200, 150, 360, 260] stays exact 360x260 without downscaling
    img_crop = Image.open(io.BytesIO(dt.screenshot("w1", region=[200, 150, 360, 260])))
    assert img_crop.size == (360, 260)

    # 4. Region crop wider than maxWidth is downscaled proportionally
    img_crop_scaled = Image.open(io.BytesIO(dt.screenshot("w1", region=[0, 0, 1600, 800], maxWidth=800)))
    assert img_crop_scaled.size == (800, 400)

    # 5. Partially overflowing region clamps cleanly to window bounds (2560 - 2400 = 160, 1440 - 1300 = 140)
    img_clamped = Image.open(io.BytesIO(dt.screenshot("w1", region=[2400, 1300, 500, 500])))
    assert img_clamped.size == (160, 140)
    img_neg_clamped = Image.open(io.BytesIO(dt.screenshot("w1", region=[-40, -20, 140, 120])))
    assert img_neg_clamped.size == (100, 100)


def test_screenshot_and_ocr_region_invalid_bounds_raise_tool_error(tmp_path, monkeypatch):
    from PIL import Image

    dt = Desktop(audit=sec.AuditLog(tmp_path / "audit.jsonl"))
    fake_win = {"id": "w1", "hwnd": 4242, "title": "HiDpiCanvas", "process": "canvasapp", "pid": 424}
    monkeypatch.setattr(dt, "find_window", lambda spec: fake_win)
    monkeypatch.setattr(dt, "_guard_window", lambda d, act, uia=True: None)
    monkeypatch.setattr(dt, "_blackout_passwords", lambda img, d=None, ox=0, oy=0, rects=None: img)
    monkeypatch.setattr(dt, "_ctrl_for", lambda d: None)
    monkeypatch.setattr(winsys, "capture_window", lambda hwnd: (Image.new("RGB", (600, 400)), (0, 0)))

    # Invalid region dimensions (w <= 0 or h <= 0) or malformed lists
    for bad_region in ([0, 0, 0, 100], [10, 10, 100, 0], [0, 0, -50, 100], [0, 0, 100, -10], [1, 2, 3], "bad", [True, 0, 10, 10]):
        with pytest.raises(ToolError, match="invalid region"):
            dt.screenshot("w1", region=bad_region)
        with pytest.raises(ToolError, match="invalid ocrRegion"):
            dt.inspect("w1", ocrRegion=bad_region)

    # Region completely outside window bounds (600x400)
    for out_of_bounds in ([700, 100, 50, 50], [100, 500, 50, 50], [-100, 0, 50, 50], [0, -100, 50, 50]):
        with pytest.raises(ToolError, match="outside window bounds"):
            dt.screenshot("w1", region=out_of_bounds)
        with pytest.raises(ToolError, match="outside window bounds"):
            dt.inspect("w1", ocrRegion=out_of_bounds)

    # Invalid maxWidth (<= 0 or non-numeric/bool)
    for bad_mw in (0, -1280, "wide", False):
        with pytest.raises(ToolError, match="invalid maxWidth"):
            dt.screenshot("w1", maxWidth=bad_mw)


def test_inspect_ocr_region_crops_and_offsets_screen_coordinates(tmp_path, monkeypatch):
    from PIL import Image

    dt = Desktop(audit=sec.AuditLog(tmp_path / "audit.jsonl"))
    fake_win = {"id": "w1", "hwnd": 7777, "title": "Canvas4K", "process": "canvas4k", "pid": 777}
    monkeypatch.setattr(dt, "find_window", lambda spec: fake_win)
    monkeypatch.setattr(dt, "_guard_window", lambda d, act, uia=True: None)
    monkeypatch.setattr(dt, "_blackout_passwords", lambda img, d=None, ox=0, oy=0, rects=None: img)
    monkeypatch.setattr(dt, "_ctrl_for", lambda d: None)

    captured_sizes: list[tuple[int, int]] = []
    # Window is at screen origin (100, 200) with size 2560x1440
    monkeypatch.setattr(winsys, "capture_window", lambda hwnd: (Image.new("RGB", (2560, 1440)), (100, 200)))

    def fake_ocr(img):
        captured_sizes.append(img.size)
        return [{"text": "Canvas Save", "x": 10, "y": 20, "w": 80, "h": 30}]

    monkeypatch.setattr(winsys, "ocr_image", fake_ocr)

    snap = dt.inspect("w1", ocrRegion=[300, 400, 360, 260])
    assert captured_sizes == [(360, 260)]
    # Screen center x = 100 (win ox) + 300 (region x) + 10 + 80//2 = 450
    # Screen center y = 200 (win oy) + 400 (region y) + 20 + 30//2 = 635
    assert '[w1:o1] text "Canvas Save" @450,635' in snap
    assert 'via: "ocr"' in snap
    w_obj = dt._win(7777)
    assert w_obj.ocr[1] == (450, 635, "Canvas Save")


def test_1440p_and_4k_benchmark_resolution_comparison():
    from field import bench_uia_vs_screenshot as bench

    a1440 = bench.anthropic_vlm_downscale(2560, 1440)
    assert a1440["effective_dims"] == "1568x882"
    assert a1440["vlm_tokens"] == 1844
    assert a1440["raw_tokens"] == 4916
    assert a1440["coord_scale_drift"] == 1.63

    a4k = bench.anthropic_vlm_downscale(3840, 2160)
    assert a4k["effective_dims"] == "1568x882"
    assert a4k["vlm_tokens"] == 1844
    assert a4k["raw_tokens"] == 11060
    assert a4k["coord_scale_drift"] == 2.45

    table = bench.compute_resolution_comparison(total_uia_tokens=2313, total_shots=16)
    by_res = {r["resolution"]: r for r in table}
    assert by_res["1440p (2560x1440)"]["anthropic_total_tok"] == 29504
    assert by_res["1440p (2560x1440)"]["token_savings_vs_anthropic"] == 12.8
    assert by_res["4K (3840x2160)"]["anthropic_total_tok"] == 29504
    assert by_res["4K (3840x2160)"]["vlm_coord_scale_drift"] == 2.45
    assert by_res["4K (3840x2160)"]["uia_coord_drift_px"] == 0
    assert by_res["Cropped 1:1 Canvas Region (360x260)"]["vlm_coord_scale_drift"] == 1.0
    assert by_res["Cropped 1:1 Canvas Region (360x260)"]["anthropic_tok_per_shot"] == 125

