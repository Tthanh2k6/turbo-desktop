import asyncio
import json
from pathlib import Path
import time

import pytest

from conftest import Env
from turbo_hub import classifier
from turbo_hub.devclient import DevClient as DevClientCls
from turbo_hub.runners import FakeRunner as FR2
from turbo_hub.runners import ClaudeRunner, build_claude_command, map_stream_json, user_frame


def _start(env, d, text="please send the mail"):
    r = d.request("POST", "/tasks", {"text": text})
    assert r.status_code == 200, r.text
    return r.json()["taskId"]


def _approval(env, d):
    ev = env.wait_event(d, lambda e: e["type"] == "approval_request")
    return ev["approval_id"], ev


def test_approval_allow(env):
    d = env.session_client()
    _start(env, d)
    aid, ev = _approval(env, d)
    assert ev["control"] == "Send" and ev["window"] == "Mail - Compose" and ev["crop_png_b64"]
    pend = d.request("GET", "/approvals").json()
    assert pend[0]["approvalId"] == aid and pend[0]["crop_png_b64"]
    assert d.request("POST", f"/approvals/{aid}", {"decision": "allow"}, strong=True).status_code == 200
    env.wait_event(d, lambda e: e["type"] == "task_finished")
    assert [c["control"] for c in env.runner.executed if c["control"]] == ["Send"] and not env.runner.denied
    assert d.request("POST", f"/approvals/{aid}", {"decision": "deny"}, strong=True).status_code == 409


def test_approval_deny(env):
    d = env.session_client()
    _start(env, d)
    aid, _ = _approval(env, d)
    assert d.request("POST", f"/approvals/{aid}", {"decision": "deny"}, strong=True).status_code == 200
    env.wait_event(d, lambda e: e["type"] == "task_finished")
    assert env.runner.denied and not [c for c in env.runner.executed if c["control"] == "Send"]


def test_approval_needs_biometric_signature(env):
    d = env.session_client()
    _start(env, d)
    aid, _ = _approval(env, d)
    assert d.request("POST", f"/approvals/{aid}", {"decision": "allow"}, strong=False).status_code == 401
    assert d.request("GET", "/approvals").json()  # still pending


def test_approval_timeout_denies(tmp_path):
    with Env(tmp_path, approval_timeout=0.4) as env:
        d = env.session_client()
        _start(env, d)
        env.wait_event(d, lambda e: e["type"] == "approval_resolved" and e["decision"] == "timeout")
        env.wait_event(d, lambda e: e["type"] == "task_finished")
        assert env.runner.denied and not [c for c in env.runner.executed if c["control"] == "Send"]
        kinds = [(e["kind"], e["data"].get("decision")) for e in env.hub.audit.read(50)]
        assert ("approval_resolved", "timeout") in kinds


def test_stop_kills_runner_and_blocks_new_tasks(env):
    d = env.session_client()
    _start(env, d, "hang forever")
    env.wait_event(d, lambda e: e["type"] == "text")
    assert d.request("POST", "/stop", {}).status_code == 200
    ev = env.wait_event(d, lambda e: e["type"] == "task_finished")
    assert ev["status"] == "stopped" and env.runner.killed
    assert d.request("POST", "/tasks", {"text": "again"}).status_code == 423
    assert d.request("POST", "/resume", {}).status_code == 200
    env.runner.killed = False
    assert d.request("POST", "/tasks", {"text": "again"}).status_code == 200


def test_stop_during_pending_approval_denies_it(env):
    d = env.session_client()
    _start(env, d)
    _approval(env, d)
    d.request("POST", "/stop", {})
    env.wait_event(d, lambda e: e["type"] == "approval_resolved" and e["decision"] == "stop")
    assert not [c for c in env.runner.executed if c["control"] == "Send"]


def test_one_task_at_a_time(env):
    d = env.session_client()
    _start(env, d, "hang")
    assert d.request("POST", "/tasks", {"text": "second"}).status_code == 409


def test_pc_locked_refuses_and_battery_warns(tmp_path):
    state = {"locked": True}

    async def provider():
        return state

    with Env(tmp_path, system_state=provider) as env:
        d = env.session_client()
        r = d.request("POST", "/tasks", {"text": "hello"})
        assert r.status_code == 423 and r.json()["error"] == "pc_locked"
        state.update(locked=False, on_battery=True, battery_percent=15)
        _start(env, d, "hello")
        w = env.wait_event(d, lambda e: e["type"] == "warning")
        assert "15%" in w["text"]


def test_usage_per_task_session_day(env):
    d = env.session_client()
    _start(env, d, "hello")
    ev = env.wait_event(d, lambda e: e["type"] == "task_finished")
    assert ev["usage"]["input"] == 1000 and ev["usage"]["cost_usd"] == 0.01
    assert ev["session_usage"]["tasks"] == 1 and ev["day_usage"]["output"] == 200
    st = d.request("GET", "/status").json()
    assert st["usage"]["session"]["input"] == 1000 and st["usage"]["today"]["tasks"] == 1
    assert (env.settings.data_dir / "usage.json").exists()


def test_events_signed_and_poll_since(env):
    d = env.session_client()
    _start(env, d, "hello")
    env.wait_event(d, lambda e: e["type"] == "task_finished")
    all_ev = d.request("GET", "/events/poll?since=0").json()
    last = all_ev[-1]["seq"]
    assert d.request("GET", f"/events/poll?since={last}").json() == []


# ------------------------------------------------------------ classifier interface
def test_classifier_stub():
    f = classifier.stub_approval_required
    assert f({"tool": "mcp__desktop__act", "input": {"action": "click", "name": "Send"}})
    assert f({"tool": "mcp__desktop__act", "input": {"action": "click"}, "control": "Xoá tất cả"})
    assert not f({"tool": "mcp__desktop__act", "input": {"action": "type", "text": "hi"}, "control": "Body"})
    assert not f({"tool": "mcp__desktop__inspect_compact", "input": {}})
    assert not f({"tool": "Read", "input": {"file_path": "x"}})
    assert f({"tool": "mcp__desktop__act", "input": {"action": "click"}, "process": "powershell.exe"})


def test_classifier_failure_fails_closed(tmp_path):
    def boom(event):
        raise RuntimeError("x")

    with Env(tmp_path) as env:
        env.hub.manager.approval_required = boom
        d = env.session_client()
        _start(env, d, "hello")
        env.wait_event(d, lambda e: e["type"] == "approval_request")


# ------------------------------------------------------------ claude stream-json framing (no real claude)
class FakeStdin:
    def __init__(self, proc):
        self.proc, self.written = proc, []

    def write(self, data):
        self.written.append(data)
        self.proc.on_write(json.loads(data))

    async def drain(self):
        pass


class FakeStdout:
    def __init__(self):
        self.q = asyncio.Queue()

    async def readline(self):
        return await self.q.get()


class FakeProc:
    def __init__(self, replies_per_msg):
        self.stdout, self.returncode, self.pid = FakeStdout(), None, 4242
        self.stdin = FakeStdin(self)
        self.replies = list(replies_per_msg)

    def on_write(self, frame):
        for obj in self.replies.pop(0):
            self.stdout.q.put_nowait((json.dumps(obj) + "\n").encode() if obj else b"")


RESULT = {"type": "result", "result": "done!", "is_error": False, "total_cost_usd": 0.5,
          "usage": {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 100}}
ASSISTANT = {"type": "assistant", "message": {"content": [
    {"type": "text", "text": "hi"}, {"type": "tool_use", "id": "u1", "name": "mcp__desktop__act", "input": {"a": 1}}]}}
TOOL_RESULT = {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "u1", "content": "fine"}]}}


def test_map_stream_json():
    evs = map_stream_json(ASSISTANT)
    assert [e["type"] for e in evs] == ["text", "tool_call_seen"] and evs[1]["tool"] == "mcp__desktop__act"
    assert map_stream_json(TOOL_RESULT)[0]["summary"] == "fine"
    fin = map_stream_json(RESULT)[0]
    assert fin["type"] == "final" and fin["usage"] == {"input": 10, "output": 5, "cache_read": 100,
                                                       "cache_create": 0, "cost_usd": 0.5}


def test_claude_command_and_frame():
    cmd = build_claude_command("C:/x/claude.exe", "cfg.json")
    assert "--input-format" in cmd and cmd[cmd.index("--input-format") + 1] == "stream-json"
    assert "-p" in cmd and "--permission-prompt-tool" in cmd and "mcp__turbohub__approve" in cmd
    assert json.loads(user_frame("héllo"))["message"] == {"role": "user", "content": "héllo"}


def test_claude_runner_reuses_process_and_restarts_after_crash():
    async def go():
        procs = []

        async def spawn(cmd):
            p = FakeProc([[ASSISTANT, TOOL_RESULT, RESULT], [RESULT], [None]] if not procs else [[RESULT]])
            procs.append(p)
            return p

        r = ClaudeRunner("http://127.0.0.1:1", "tok", claude_path="claude", spawn=spawn)
        seen = []

        async def emit(ev):
            seen.append(ev)

        async def gate(call):
            return True

        assert await r.run("t1", "first", emit, gate) == "done"
        assert await r.run("t2", "second", emit, gate) == "done"
        assert r.spawn_count == 1 and len(procs[0].stdin.written) == 2        # same process, two frames
        assert [e["type"] for e in seen[:3]] == ["text", "tool_result", "final"]   # tool_call comes from the gate only
        assert await r.run("t3", "crash", emit, gate) == "failed"             # EOF mid-task
        procs[0].returncode = 1
        assert await r.run("t4", "after", emit, gate) == "done"
        assert r.spawn_count == 2                                             # restarted
        # kill drops the process so the next task starts fresh
        r.proc = None
    asyncio.run(go())


def test_internal_approve_requires_token_and_runs_gate(env):
    d = env.session_client()
    hdr = {"X-Task-Token": env.settings.internal_token}
    assert env.http.post("/internal/approve", json={"tool_name": "x"}).status_code == 403
    assert env.http.post("/internal/approve", json={"tool_name": "x"}, headers=hdr).status_code == 409  # no task
    _start(env, d, "hang")
    r = env.http.post("/internal/approve", json={"tool_name": "Read", "input": {"p": 1}}, headers=hdr)
    assert r.json()["behavior"] == "allow"


def test_runner_survives_a_screenshot_sized_line():
    """Field bug: asyncio's 64 KB line limit crashed the runner on a screenshot result."""
    import sys
    from turbo_hub.runners import _spawn_real

    async def go():
        p = await _spawn_real([sys.executable, "-c", "print('x' * 300000)"])
        line = await p.stdout.readline()
        await p.wait()
        return len(line)
    assert asyncio.run(go()) > 300000


def test_desktop_mcp_bridge_files(tmp_path):
    """Contract with desktop-mcp/security.py: approver.alive, <id>.req.json -> phone -> <id>.decision, STOP file."""
    import json as _json
    from turbo_hub.runners import FakeRunner as FR
    state = tmp_path / "state"
    from fastapi.testclient import TestClient
    from turbo_hub.app import Settings, create_app
    class Clk:
        t = __import__("time").time()
        def __call__(self): return self.t
    clk = Clk()
    runner = FR([{"type": "sleep", "s": 30}])
    s = Settings(data_dir=tmp_path / "hub3", runner_factory=lambda: runner, clock=clk, approval_timeout=3,
                 loopback_hosts=("127.0.0.1", "testclient"), approval_engine="desktop-mcp", desktop_state_dir=state)
    app = create_app(s)
    with TestClient(app) as http:
        hub = app.state.hub
        info = http.post("/admin/pairing", headers={"X-Admin-Token": hub.store.admin_token}).json()
        d = DevClientCls(http, hub_pub=info["hubKey"], clock=clk)
        assert d.pair(info["code"]).status_code == 200
        assert d.start_session(hub.store.totp_secret).status_code == 200
        d.request("POST", "/tasks", {"text": "hello"})
        (state / "approvals").mkdir(parents=True, exist_ok=True)
        (state / "approvals" / "ab12.req.json").write_text(_json.dumps(
            {"id": "ab12", "window": "Mail", "control": "Send", "action": "click", "reason": "send", "rule": "send-button"}))
        import time as _t
        aid = None
        end = _t.time() + 5
        while _t.time() < end and not aid:
            d.request("GET", "/status")     # phone activity keeps the approver "alive"
            for e in d.request("GET", "/events/poll?since=0").json():
                if e["type"] == "approval_request":
                    aid = e["approval_id"]
                    assert e["control"] == "Send" and e["window"] == "Mail"
            _t.sleep(0.1)
        assert aid and (state / "approver.alive").exists()
        assert d.request("POST", f"/approvals/{aid}", {"decision": "allow"}, strong=True).status_code == 200
        end = _t.time() + 5
        while _t.time() < end and not (state / "approvals" / "ab12.decision").exists():
            _t.sleep(0.05)
        assert (state / "approvals" / "ab12.decision").read_text() == "allow"
        d.request("POST", "/stop", {})
        assert (state / "STOP").exists()
        d.request("POST", "/resume", {})
        assert not (state / "STOP").exists()


def test_bridge_ignores_requests_left_by_a_previous_run(tmp_path):
    from fastapi.testclient import TestClient
    from turbo_hub.app import Settings, create_app
    state = tmp_path / "state"
    (state / "approvals").mkdir(parents=True)
    (state / "approvals" / "old1.req.json").write_text(json.dumps({"id": "old1", "control": "Send"}))
    clk = lambda: __import__("time").time()  # noqa: E731
    app = create_app(Settings(data_dir=tmp_path / "h", clock=clk, approval_engine="desktop-mcp", desktop_state_dir=state,
                              loopback_hosts=("127.0.0.1", "testclient")))
    with TestClient(app) as http:
        hub = app.state.hub
        import time as _t
        _t.sleep(0.8)
        assert not [e for e in hub.manager.events if e["type"] == "approval_request"]
        assert (state / "approvals" / "stale" / "old1.req.json").exists()
        assert not (state / "approvals" / "old1.decision").exists()


def test_reaper_kills_leftover_agent_only_if_same_image(tmp_path):
    import subprocess, sys, time as _t
    from turbo_hub import reaper
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    f = tmp_path / "agent.pid"
    reaper.record(f, p.pid)
    assert json.loads(f.read_text())["image"].lower().startswith("python")
    f.write_text(json.dumps({"pid": p.pid, "image": "claude.exe"}))        # same pid, different program: leave it
    assert reaper.reap(f) is False and p.poll() is None
    reaper.record(f, p.pid)
    assert reaper.reap(f) is True
    _t.sleep(1)
    assert p.poll() is not None
    assert reaper.reap(tmp_path / "missing.pid") is False


def test_agent_dies_when_the_hub_process_is_killed(tmp_path):
    """Field bug: a hard-killed hub left claude (and its MCP servers) driving the desktop."""
    import subprocess, sys, time as _t
    code = ("import subprocess,sys,time;from turbo_hub import reaper;"
            "c=subprocess.Popen([sys.executable,'-c','import time;time.sleep(120)']);"
            "assert reaper.bind_to_hub_lifetime(c.pid);print(c.pid,flush=True);time.sleep(120)")
    hub = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True,
                           cwd=str(Path(__file__).resolve().parents[1]))
    child = int(hub.stdout.readline())
    from turbo_hub import reaper
    assert reaper.image_of(child)
    hub.kill()
    hub.wait()
    _t.sleep(1.5)
    assert reaper.image_of(child) is None


def test_input_lock_indicator_and_takeover_relay(tmp_path):
    """desktop-mcp writes input_lock.json / indicator.json; the hub relays them, 'take over' releases and pauses."""
    from fastapi.testclient import TestClient
    from turbo_hub.app import Settings, create_app
    import time as _t
    state = tmp_path / "state"
    runner = FR2([{"type": "sleep", "s": 30}])
    clk = lambda: _t.time()  # noqa: E731
    app = create_app(Settings(data_dir=tmp_path / "h", clock=clk, runner_factory=lambda: runner, approval_engine="desktop-mcp",
                              desktop_state_dir=state, loopback_hosts=("127.0.0.1", "testclient")))
    with TestClient(app) as http:
        hub = app.state.hub
        info = http.post("/admin/pairing", headers={"X-Admin-Token": hub.store.admin_token}).json()
        d = DevClientCls(http, hub_pub=info["hubKey"], clock=clk)
        assert d.pair(info["code"]).status_code == 200
        assert d.start_session(hub.store.totp_secret).status_code == 200

        def types():
            return [(e["type"], e.get("state") or e.get("locked")) for e in d.request("GET", "/events/poll?since=0").json()]

        def wait_for(item):
            end = _t.time() + 5
            while _t.time() < end:
                if item in types():
                    return
                _t.sleep(0.1)
            raise AssertionError(f"{item} not in {types()}")

        (state / "indicator.json").write_text(json.dumps({"state": "acting"}))
        wait_for(("indicator", "acting"))
        (state / "input_lock.json").write_text(json.dumps({"locked": True, "mode": "real_input", "since": 1}))
        wait_for(("input_lock", True))
        wait_for(("indicator", "input_locked"))
        assert d.request("GET", "/status").json()["indicator"] == "input_locked"
        # take over: RELEASE file for the MCP, run paused until resume
        assert d.request("POST", "/takeover", {}).status_code == 200
        assert (state / "RELEASE").exists() and hub.manager.paused
        res = {}

        async def go():
            res["allowed"] = await asyncio.wait_for(hub.manager.gate("t1", {"tool": "mcp__desktop__act"}), 0.5)
        try:
            asyncio.run(go())
        except asyncio.TimeoutError:
            res["blocked"] = True                       # a paused run does not get its next tool call
        assert res.get("blocked")
        d.request("POST", "/resume", {})
        assert not (state / "RELEASE").exists() and not hub.manager.paused


def test_tool_result_summaries():
    from turbo_hub.summaries import summarize
    launch = json.dumps({"result": json.dumps({"ok": True, "windows": [{"id": "w3", "title": "Calculator"}]})})
    assert summarize("mcp__desktop__launch_app", {}, launch) == "Opened Calculator (w3)"
    act = json.dumps({"result": json.dumps({"ok": True, "via": "pattern"})})
    assert summarize("mcp__desktop__act", {"action": "click", "name": "Equals"}, act) == "Clicked 'Equals' via UIA"
    tree = json.dumps({"result": "window w3\n[w3:e1] <Button> \"1\"\n[w3:e2] <Button> \"2\"\n"})
    assert summarize("mcp__desktop__inspect_compact", {}, tree) == "Read 2 controls"
    err = json.dumps({"result": json.dumps({"ok": False, "error": "owner is using the PC"})})
    assert summarize("mcp__desktop__act", {}, err).startswith("Failed: owner is using")
    long_text = "word " * 100
    out = summarize("some_other_tool", {}, long_text)
    assert out.count("\n") <= 1 and len(out) <= 165 and out.endswith("…")
    batch = json.dumps({"result": json.dumps({"ok": True, "steps": [{"ok": True}, {"ok": True}]})})
    assert summarize("mcp__desktop__batch_actions", {}, batch) == "Ran 2 steps (2 ok)"


def test_live_usage_is_deduplicated_and_indicator_is_derived(tmp_path):
    script = [{"type": "tool_call", "tool": "mcp__desktop__inspect_compact", "input": {}, "window": "Calculator", "control": None, "action": "inspect"},
              {"type": "raw", "event": {"type": "usage_delta", "mid": "m1", "usage": {"input": 10, "output": 3}}},
              {"type": "raw", "event": {"type": "usage_delta", "mid": "m1", "usage": {"input": 10, "output": 5}}},   # same message again
              {"type": "raw", "event": {"type": "usage_delta", "mid": "m2", "usage": {"input": 20, "output": 7}}},
              {"type": "sleep", "s": 0.3}]
    with Env(tmp_path, runner_script=script) as env:
        env.hub.manager.engine = "desktop-mcp"
        d = env.session_client()
        d.request("POST", "/tasks", {"text": "x"})
        ev = env.wait_event(d, lambda e: e["type"] == "task_finished")
        usages = [e["usage"] for e in d.request("GET", "/events/poll?since=0").json() if e["type"] == "usage"]
        assert usages[-1] == {"input": 30, "output": 12, "cache_read": 0, "cache_create": 0}   # not 10+10+20 / 3+5+7
        states = [e["state"] for e in d.request("GET", "/events/poll?since=0").json() if e["type"] == "indicator"]
        assert states == ["acting", "idle"]          # derived from the tool call, back to idle at the end


def test_no_script_or_test_launches_the_owners_editor():
    """Field rule: never launch or target windows the run did not open (the owner's editor windows hold real files)."""
    word = "note" + "pad"
    root = Path(__file__).resolve().parents[1]
    for f in list((root / "scripts").glob("*.py")) + list((root / "tests").glob("*.py")):
        for line in f.read_text("utf-8").splitlines():
            if word in line.lower():
                raise AssertionError(f"{f.name} mentions it: {line.strip()[:80]}")


def test_default_fake_runner_factory_runs_the_demo_script(tmp_path):
    """Field bug: `serve --runner fake` failed with "'Task' object is not iterable" (factory got the Task as its script)."""
    from fastapi.testclient import TestClient
    from turbo_hub.app import Settings, create_app
    import time as _t
    clk = lambda: _t.time()  # noqa: E731
    app = create_app(Settings(data_dir=tmp_path / "h", clock=clk, loopback_hosts=("127.0.0.1", "testclient")))  # default FakeRunner class
    with TestClient(app) as http:
        hub = app.state.hub
        tok = {"X-Admin-Token": hub.store.admin_token}
        assert http.post("/admin/tasks", json={"text": "demo: x"}, headers=tok).status_code == 200
        end = _t.time() + 8
        while _t.time() < end and not any(e["type"] == "tool_call" for e in hub.manager.events):
            _t.sleep(0.1)
        types = [e["type"] for e in hub.manager.events]
        assert "tool_call" in types and not any(e.get("text", "").startswith("runner error") for e in hub.manager.events)


def test_summary_parts_are_language_neutral():
    from turbo_hub.summaries import summary_parts
    act = json.dumps({"result": json.dumps({"ok": True, "via": "input"})})
    assert summary_parts("mcp__desktop__act", {"action": "type", "name": "Name"}, act) == ("acted", ["type", "Name", "input"])
    tree = json.dumps({"result": "[w1:e1] a" + chr(10) + "[w1:e2] b"})
    assert summary_parts("mcp__desktop__inspect_compact", {}, tree) == ("read_controls", [2])
    assert summary_parts("x", {}, "plain words")[0] == "text"


def test_lock_wrapper_child_is_not_blocked_by_its_parent(tmp_path, monkeypatch):
    """Field bug: `with_lock.py -- pytest` deadlocked because conftest asked for the lock its own parent held."""
    import subprocess, sys
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    lock = tmp_path / "t.lock"
    code = "import sys;sys.path.insert(0,r'%s');import with_lock;with_lock.acquire(wait_seconds=3,poll=0.2);print('child ok')" % scripts
    env = {**__import__("os").environ, "TURBO_TEST_LOCK": str(lock)}
    r = subprocess.run([sys.executable, str(scripts / "with_lock.py"), "--", sys.executable, "-c", code], env=env,
                       capture_output=True, text=True, timeout=60)
    assert "child ok" in r.stdout, r.stdout + r.stderr


def test_claude_command_operator_prompt_and_model():
    from turbo_hub.runners import OPERATOR_PROMPT
    cmd = build_claude_command("claude", "cfg.json")
    assert cmd[cmd.index("--append-system-prompt") + 1] == OPERATOR_PROMPT
    assert "--model" not in cmd
    cmd = build_claude_command("claude", "cfg.json", system_prompt="be brief", model="sonnet")
    assert cmd[cmd.index("--append-system-prompt") + 1] == "be brief" and cmd[cmd.index("--model") + 1] == "sonnet"
    assert "--append-system-prompt" not in build_claude_command("claude", "cfg.json", system_prompt="")
    custom = build_claude_command("claude", "cfg.json", ["a", "{mcp_config}"], system_prompt="x", model="m")
    assert custom == ["a", "cfg.json"]   # a custom template only gets what it asks for via placeholders
