"""Subprocess E2E tests for the state-dir bridge (indicator.json, input_lock.json, RELEASE, _ignored_sig)."""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from turbo_desktop import border as bd, inputlock as il, security as sec
from turbo_desktop.engine import Desktop

from conftest import FIX, ROOT


def _read_json(path: Path):
    if not path.exists():
        return None
    for _ in range(5):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            time.sleep(0.02)
    return None


def _wait_for_json(path: Path, pred, timeout: float = 2.0):
    t0 = time.monotonic()
    last = None
    while time.monotonic() - t0 < timeout:
        last = _read_json(path)
        if last is not None and pred(last):
            return last, time.monotonic() - t0
        time.sleep(0.04)
    raise AssertionError(f"timed out after {timeout}s waiting on {path.name}; last={last!r}")


async def _wait_for_json_async(path: Path, pred, timeout: float = 2.0):
    t0 = time.monotonic()
    last = None
    while time.monotonic() - t0 < timeout:
        last = _read_json(path)
        if last is not None and pred(last):
            return last, time.monotonic() - t0
        await asyncio.sleep(0.04)
    raise AssertionError(f"timed out after {timeout}s waiting on {path.name}; last={last!r}")


def _text(res):
    return "".join(c.text for c in res.content if getattr(c, "text", None))


def test_state_bridge_e2e_over_stdio(tmp_path):
    """Spawn `python -m turbo_desktop` over stdio MCP with TURBO_DESKTOP_STATE_DIR and TURBO_DESKTOP_NO_INDICATOR=1.
    Proves: startup writes idle/unlocked -> task_active.json acquires lock + input_locked -> RELEASE clears lock
    and indicator within <1s and ignores same task_active.json -> pattern actions (launch, act, batch,
    window_control) update indicator.json to 'acting' then return to 'idle'."""
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    ind_path = state_dir / "indicator.json"
    lock_path = state_dir / "input_lock.json"
    task_path = state_dir / "task_active.json"
    rel_path = state_dir / "RELEASE"

    async def scenario():
        env = {
            **os.environ,
            "PYTHONPATH": str(ROOT / "src"),
            "PYTHONUTF8": "1",
            "TURBO_DESKTOP_STATE_DIR": str(state_dir),
            "TURBO_DESKTOP_AUDIT": str(state_dir / "audit.jsonl"),
            "TURBO_DESKTOP_NO_INDICATOR": "1",
            "TURBO_DESKTOP_NO_INPUT": "1",
            "TURBO_DESKTOP_PRESET": "easy",
            "TURBO_DESKTOP_REQUIRE_CLEAN": "1",
            "TURBO_DESKTOP_CONFIG": str(state_dir / "no-such-config.toml"),
        }
        params = StdioServerParameters(command=sys.executable,
                                       args=["-m", "turbo_desktop"], env=env)
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as session:
                await session.initialize()

                # 1. Server starts StateBridge immediately -> idle / unlocked
                await _wait_for_json_async(ind_path, lambda d: d == {"state": "idle"}, timeout=2.0)
                await _wait_for_json_async(lock_path, lambda d: d.get("locked") is False, timeout=2.0)

                # 2. task_active.json -> input_lock.json + indicator.json (< 1s)
                now = time.time()
                sec.atomic_write_json(task_path, {
                    "task": "e2e-task-1",
                    "since": now,
                    "heartbeat": now,
                    "source": "phone",
                    "max_minutes": 15,
                })
                lock_data, dt_lock = await _wait_for_json_async(
                    lock_path, lambda d: d.get("locked") is True and d.get("mode") == "whole_task", timeout=1.0
                )
                ind_data, dt_ind = await _wait_for_json_async(
                    ind_path, lambda d: d.get("state") == "input_locked", timeout=1.0
                )
                assert dt_lock < 1.0 and dt_ind < 1.0
                assert lock_data["reason"] == "remote_task"
                assert ind_data == {"state": "input_locked"}

                # 3. RELEASE clears lock and indicator within < 1s, deletes RELEASE, and ignores same task_active.json
                rel_path.write_text("takeover", encoding="utf-8")
                t_rel = time.monotonic()
                rel_lock, _ = await _wait_for_json_async(
                    lock_path, lambda d: d.get("locked") is False and d.get("reason") == "release", timeout=1.0
                )
                rel_ind, _ = await _wait_for_json_async(
                    ind_path, lambda d: d.get("state") == "idle", timeout=1.0
                )
                assert (time.monotonic() - t_rel) < 1.0
                assert not rel_path.exists()
                assert rel_lock["locked"] is False and rel_lock["reason"] == "release"
                assert rel_ind == {"state": "idle"}

                # Even with task_active.json still present, the same signature stays ignored across bridge ticks
                await asyncio.sleep(0.45)
                assert _read_json(lock_path)["locked"] is False
                assert _read_json(ind_path) == {"state": "idle"}
                task_path.unlink()
                await asyncio.sleep(0.25)

                # 4. Pattern actions update indicator.json -> acting -> idle even with TURBO_DESKTOP_NO_INDICATOR=1
                launched = json.loads(_text(await session.call_tool("launch_app", {
                    "target": str(FIX / "turbo_fixture.exe"), "wait": 8.0,
                })))
                assert launched["ok"] is True and launched["windows"]
                wid = launched["windows"][0]["id"]
                assert _read_json(ind_path) == {"state": "acting"}

                try:
                    # Wait for linger -> idle
                    await _wait_for_json_async(ind_path, lambda d: d == {"state": "idle"}, timeout=4.5)

                    # Pattern act -> acting -> idle
                    res_act = json.loads(_text(await session.call_tool("act", {
                        "window": wid, "action": "click", "name": "Count 0",
                    })))
                    assert res_act["ok"] is True and res_act["via"] == "pattern"
                    assert _read_json(ind_path) == {"state": "acting"}
                    await _wait_for_json_async(ind_path, lambda d: d == {"state": "idle"}, timeout=4.5)

                    # Pattern batch_actions -> acting
                    res_batch = json.loads(_text(await session.call_tool("batch_actions", {
                        "window": wid, "steps": [{"action": "click", "name": "Count 1"}],
                    })))
                    assert res_batch["ok"] is True
                    assert _read_json(ind_path) == {"state": "acting"}

                    # window_control -> acting -> idle
                    res_wc = json.loads(_text(await session.call_tool("window_control", {
                        "window": wid, "action": "minimize",
                    })))
                    assert res_wc["ok"] is True
                    assert _read_json(ind_path) == {"state": "acting"}
                    await _wait_for_json_async(ind_path, lambda d: d == {"state": "idle"}, timeout=4.5)
                finally:
                    await session.call_tool("window_control", {"window": wid, "action": "close"})

    asyncio.run(scenario())


def test_engine_checks_release_before_steps_and_updates_bridge(tmp_path, monkeypatch, launch_app):
    """Even if StateBridge background thread is not running, engine.py checks RELEASE before steps,
    deletes RELEASE, releases InputLock, calls hide_now(), ignores task_active.json, and updates files."""
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("TURBO_DESKTOP_STATE_DIR", str(state_dir))
    monkeypatch.setenv("TURBO_DESKTOP_NO_INDICATOR", "1")

    dt = Desktop(audit=sec.AuditLog(state_dir / "audit.jsonl"))
    dt.bridge.stop()  # isolate engine.py's synchronous check_release() from the background thread
    try:
        d = launch_app("turbo_fixture.exe")
        wid = dt.find_window(d["title"])["id"]
        now = time.time()
        sec.atomic_write_json(state_dir / "task_active.json", {
            "task": "sync-t1", "since": now, "heartbeat": now, "source": "phone",
        })
        dt.bridge.tick()
        assert dt.lock.locked is True
        assert _read_json(state_dir / "indicator.json") == {"state": "input_locked"}
        assert _read_json(state_dir / "input_lock.json")["locked"] is True

        # Create RELEASE right before a batch step (e.g. wait_for then click)
        rel = state_dir / "RELEASE"
        rel.write_text("takeover", encoding="utf-8")
        # Spy on hide_now
        hides = []
        orig_hide = dt.indicator.hide_now
        monkeypatch.setattr(dt.indicator, "hide_now", lambda: (hides.append(True), orig_hide())[1])

        res = dt.batch([
            {"op": "wait_for", "text": "Count 0", "timeout": 5},
            {"action": "click", "name": "Count 0"},
        ], window=wid)
        assert res["ok"] is True, res
        assert not rel.exists()
        assert hides
        assert dt.lock.locked is False
        assert _read_json(state_dir / "input_lock.json")["locked"] is False
        assert _read_json(state_dir / "input_lock.json")["reason"] == "release"
        assert dt.bridge._ignored_sig == ("sync-t1", now)

        # Next bridge tick keeps it unlocked for the same task_active.json
        dt.bridge.tick()
        assert dt.lock.locked is False
        assert _read_json(state_dir / "input_lock.json")["locked"] is False

        # If RELEASE exists right before wait_for (no activity afterwards), indicator goes straight to idle
        rel.write_text("takeover", encoding="utf-8")
        dt.indicator.activity()
        assert _read_json(state_dir / "indicator.json") == {"state": "acting"}
        dt.wait_for(window=wid, text="Count 1", timeout=5)
        assert not rel.exists()
        assert _read_json(state_dir / "indicator.json") == {"state": "idle"}
        assert _read_json(state_dir / "input_lock.json") == {
            "locked": False, "mode": "whole_task", "since": None, "reason": "release"
        }
    finally:
        dt.close_launched()


def test_input_lock_writes_bridge_files_for_real_input_and_whole_task_modes(tmp_path, monkeypatch):
    """InputLock.acquire/release writes input_lock.json atomically in both real_input and whole_task modes."""
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    ind = bd.Indicator(disabled_by_env=True, state_dir=state_dir)
    lock = il.InputLock(banner_class="TurboDesktopBannerBridgeT", linger_ms=100, state_dir=state_dir, indicator=ind)
    # Stub Win32 hook installation so this runs safely even while the owner is active at the PC
    monkeypatch.setattr(lock, "_ensure_thread", lambda: True)
    monkeypatch.setattr(il.u32, "PostMessageW", lambda hwnd, msg, wp, lp: (
        (setattr(lock, "locked", True), lock._ready.set()) if msg == il.WM_ACQUIRE
        else ((setattr(lock, "locked", False), setattr(lock, "since", None), lock._write_bridge(), lock._done.set()) if msg == il.WM_RELEASE else None)
    ))
    lock.ctrl_hwnd = 1
    lock._thread_up.set()

    # 1. real_input mode
    lock.acquire(max_seconds=30, whole_task=False, reason="real_input")
    d1 = _read_json(state_dir / "input_lock.json")
    assert d1["locked"] is True and d1["mode"] == "real_input" and d1["reason"] == "real_input"
    assert _read_json(state_dir / "indicator.json") == {"state": "input_locked"}
    lock.end_one()
    d2 = _read_json(state_dir / "input_lock.json")
    assert d2["locked"] is False and d2["mode"] == "real_input" and d2["reason"] == "done" and d2["since"] is None

    # 2. whole_task mode
    lock.acquire(max_seconds=45, whole_task=True, reason="whole_task")
    d3 = _read_json(state_dir / "input_lock.json")
    assert d3["locked"] is True and d3["mode"] == "whole_task" and d3["reason"] == "whole_task"
    lock.end_one()
    assert lock.locked is True  # whole_task lingers after end_one()
    lock.release("idle-linger")
    d4 = _read_json(state_dir / "input_lock.json")
    assert d4["locked"] is False and d4["mode"] == "whole_task" and d4["reason"] == "idle-linger"
    assert _read_json(state_dir / "indicator.json") == {"state": "idle"}
