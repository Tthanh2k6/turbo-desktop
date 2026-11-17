import json

from fastapi.testclient import TestClient

from conftest import Env
from turbo_hub.app import Settings, create_app
from turbo_hub.devclient import DevClient
from turbo_hub.manager import _today


def test_report_empty(env):
    d = env.session_client()
    r = d.request("GET", "/report?days=7")
    assert r.status_code == 200
    body = r.json()
    assert len(body["days"]) == 7
    dates = [x["date"] for x in body["days"]]
    assert dates == sorted(dates)
    assert dates[-1] == _today(env.clock())
    for day in body["days"]:
        assert day == {"date": day["date"], "done": 0, "failed": 0, "stopped": 0, "seconds": 0}
    assert body["totals"] == {
        "done": 0,
        "failed": 0,
        "stopped": 0,
        "seconds": 0,
        "tokensIn": 0,
        "tokensOut": 0,
        "costUsd": 0.0,
    }
    assert body["topApps"] == []

    r1 = d.request("GET", "/report?days=1").json()
    assert len(r1["days"]) == 1 and r1["days"][0]["date"] == _today(env.clock())
    r30 = d.request("GET", "/report?days=30").json()
    assert len(r30["days"]) == 30 and r30["days"][-1]["date"] == _today(env.clock())


def test_report_two_tasks_on_two_days_and_persistence(tmp_path):
    with Env(tmp_path) as env:
        d = env.session_client()
        day1_str = _today(env.clock())

        # Task 1 on day 1: runs for 40s, approved -> done
        r = d.request("POST", "/tasks", {"text": "first day task"})
        assert r.status_code == 200
        ev = env.wait_event(d, lambda e: e["type"] == "approval_request")
        env.clock.t += 40
        assert d.request("POST", f"/approvals/{ev['approval_id']}", {"decision": "allow"}, strong=True).status_code == 200
        env.wait_event(d, lambda e: e["type"] == "task_finished")

        # Advance 1 day for Task 2: runs for 25s, stopped -> stopped
        env.clock.t += 86400
        day2_str = _today(env.clock())
        assert d.start_session(env.hub.store.totp_secret).status_code == 200   # a day later the session has expired
        assert d.request("POST", "/tasks", {"text": "hang on day two"}).status_code == 200
        env.wait_event(d, lambda e: e["type"] == "text" and e.get("text") == "working...")
        env.clock.t += 25
        assert d.request("POST", "/stop", {}).status_code == 200
        env.wait_event(d, lambda e: e["type"] == "task_finished" and e["status"] == "stopped")

        rep7 = d.request("GET", "/report?days=7").json()
        assert len(rep7["days"]) == 7
        assert [x["date"] for x in rep7["days"]] == sorted(x["date"] for x in rep7["days"])
        for zero_day in rep7["days"][:5]:
            assert zero_day["done"] == 0 and zero_day["failed"] == 0 and zero_day["stopped"] == 0 and zero_day["seconds"] == 0
        assert rep7["days"][-2] == {"date": day1_str, "done": 1, "failed": 0, "stopped": 0, "seconds": 40}
        assert rep7["days"][-1] == {"date": day2_str, "done": 0, "failed": 0, "stopped": 1, "seconds": 25}
        assert rep7["totals"] == {
            "done": 1,
            "failed": 0,
            "stopped": 1,
            "seconds": 65,
            "tokensIn": 1000,
            "tokensOut": 200,
            "costUsd": 0.01,
        }

        rep1 = d.request("GET", "/report?days=1").json()
        assert rep1["days"] == [{"date": day2_str, "done": 0, "failed": 0, "stopped": 1, "seconds": 25}]
        assert rep1["totals"] == {
            "done": 0,
            "failed": 0,
            "stopped": 1,
            "seconds": 25,
            "tokensIn": 0,
            "tokensOut": 0,
            "costUsd": 0.0,
        }

        # Prepend a 95-day-old entry to tasks.jsonl and restart the hub to verify persistence and 90-day cap
        tasks_file = env.settings.data_dir / "tasks.jsonl"
        assert tasks_file.exists()
        old_line = json.dumps({
            "id": "told95",
            "start": env.clock() - 95 * 86400,
            "end": env.clock() - 95 * 86400 + 10,
            "status": "done",
            "usage": {"input": 999, "output": 999, "cost_usd": 1.0},
            "apps": ["AncientApp"],
        })
        existing = tasks_file.read_text("utf-8")
        tasks_file.write_text(old_line + "\n" + existing, "utf-8")
        data_dir, clock = env.settings.data_dir, env.clock

    clock.t += 5
    app2 = create_app(Settings(data_dir=data_dir, clock=clock, loopback_hosts=("127.0.0.1", "testclient")))
    with TestClient(app2) as http2:
        hub2 = app2.state.hub
        d.http = http2
        assert d.start_session(hub2.store.totp_secret, step_offset=1).status_code == 200
        rep_after = d.request("GET", "/report?days=7").json()
        assert rep_after["totals"] == rep7["totals"]
        assert rep_after["days"][-2]["seconds"] == 40 and rep_after["days"][-1]["seconds"] == 25
        kept_ids = [json.loads(line)["id"] for line in tasks_file.read_text("utf-8").splitlines() if line.strip()]
        assert "told95" not in kept_ids and len(kept_ids) == 2


def test_report_top_apps_ordering_and_redaction(tmp_path):
    script = [
        {"type": "tool_call", "tool": "mcp__desktop__launch_app", "input": {"target": "Zalo"}},
        {"type": "tool_call", "tool": "mcp__desktop__inspect_compact", "input": {"window": "Marry Pham - Zalo"}},
        {"type": "tool_call", "tool": "mcp__desktop__act", "input": {"action": "type", "name": "ChatInput", "text": "top-secret-msg"},
         "window": "Chat - Marry Pham - Zalo", "control": "ChatInput", "action": "type"},
        {"type": "tool_call", "tool": "mcp__desktop__act", "input": {"action": "click", "name": "Sticker"},
         "window": "Zalo", "control": "Sticker", "action": "click"},
        {"type": "tool_call", "tool": "mcp__desktop__inspect_compact", "input": {"window": "Q4 Budget - Excel"}},
        {"type": "tool_call", "tool": "mcp__desktop__act", "input": {"action": "click", "name": "CellA1"},
         "window": "Sheet1 - Q4 Budget - Excel", "control": "CellA1", "action": "click"},
        {"type": "tool_call", "tool": "mcp__desktop__act", "input": {"action": "type", "text": "42000"},
         "window": "Q4 Budget - Excel", "control": "CellA1", "action": "type"},
        {"type": "tool_call", "tool": "mcp__desktop__inspect_compact", "input": {"window": "Docs - Chrome"}, "app": "Chrome"},
        {"type": "tool_call", "tool": "mcp__desktop__act", "input": {"action": "click", "name": "Tab"},
         "window": "Search - Chrome", "control": "Tab", "action": "click"},
        {"type": "tool_call", "tool": "mcp__desktop__act", "input": {"action": "click", "name": "Play"},
         "window": "Song - Player", "process": "Spotify.exe", "control": "Play", "action": "click"},
        {"type": "tool_call", "tool": "mcp__desktop__inspect_compact", "input": {"window": "Playlist"}, "process": "Spotify.exe"},
        {"type": "tool_call", "tool": "mcp__desktop__launch_app", "input": {"target": "Calculator"}},
        {"type": "tool_call", "tool": "mcp__desktop__launch_app", "input": {"target": "Paint"}},
        {"type": "final", "text": "All done.", "usage": {"input": 500, "output": 120, "cost_usd": 0.005}},
    ]
    with Env(tmp_path, runner_script=script) as env:
        env.hub.manager.engine = "desktop-mcp"
        d = env.session_client()
        assert d.request("POST", "/tasks", {"text": "multi app"}).status_code == 200
        env.wait_event(d, lambda e: e["type"] == "task_finished")

        rep = d.request("GET", "/report?days=7").json()
        top = rep["topApps"]
        assert len(top) == 5  # capped at 5 even though 6 apps were used
        assert top[0] == {"name": "Zalo", "count": 4}
        assert top[1] == {"name": "Excel", "count": 3}
        assert top[2] == {"name": "Chrome", "count": 2}
        assert top[3] == {"name": "Spotify", "count": 2}
        assert top[4]["count"] == 1 and top[4]["name"] in ("Calculator", "Paint")

        raw_tasks = (env.settings.data_dir / "tasks.jsonl").read_text("utf-8")
        assert "top-secret-msg" not in raw_tasks
        assert "42000" not in raw_tasks
        assert "ChatInput" not in raw_tasks
        assert "CellA1" not in raw_tasks


def test_report_days_param_validation(env):
    d = env.session_client()
    for valid in ("1", "7", "30"):
        r = d.request("GET", f"/report?days={valid}")
        assert r.status_code == 200, f"days={valid} failed: {r.text}"
        assert len(r.json()["days"]) == int(valid)
    for invalid in ("0", "2", "5", "14", "90", "-1", "abc", ""):
        r = d.request("GET", f"/report?days={invalid}")
        assert r.status_code == 400, f"days={invalid} should return 400, got {r.status_code}"


def test_report_requires_session(env):
    unpaired = DevClient(env.http, clock=env.clock)
    assert unpaired.request("GET", "/report").status_code == 401
    assert unpaired.request("GET", "/report?days=7").status_code == 401

    paired_no_session = env.paired_client()
    assert paired_no_session.request("GET", "/report").status_code == 401
    assert paired_no_session.request("GET", "/report?days=7").status_code == 401

    with_session = env.session_client()
    r = with_session.request("GET", "/report?days=7")
    assert r.status_code == 200


def test_history_survives_restart(tmp_path):
    with Env(tmp_path) as env:
        d = env.session_client()
        assert d.request("POST", "/tasks", {"text": "first day task"}).status_code == 200
        ev = env.wait_event(d, lambda e: e["type"] == "approval_request")
        assert d.request("POST", f"/approvals/{ev['approval_id']}", {"decision": "allow"}, strong=True).status_code == 200
        env.wait_event(d, lambda e: e["type"] == "task_finished")
        env.hub.manager.tasks.clear()   # what a hub restart loses
        hist = d.request("GET", "/tasks").json()
        assert hist and hist[0]["text"] == "first day task" and hist[0]["status"] == "done"
        st = d.request("GET", "/status").json()
        assert isinstance(st.get("pcName"), str)
