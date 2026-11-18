"""Claude Code permission prompts through the hub: phone or PC answers, first one wins, no timeout."""
import importlib.util
import json
import threading
import time
from pathlib import Path

from conftest import Env

from turbo_hub import cc_hook_install
from turbo_hub.cc_permission import describe

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "cc_permission_hook.py"
spec = importlib.util.spec_from_file_location("cc_permission_hook", SCRIPT)
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)

BASH = {"hook_event_name": "PermissionRequest", "session_id": "abc123", "cwd": "D:\\Project\\demo-app",
        "tool_name": "Bash", "tool_input": {"command": "git push origin main", "description": "Push to GitHub"}}


def cc_headers(env, key=""):
    from turbo_hub.cc_permission import load_or_create_token
    return {"X-CC-Token": load_or_create_token(env.settings.data_dir), "X-CC-Key": key}


def create(env, payload=BASH):
    r = env.http.post("/cc/permission", content=json.dumps(payload), headers=cc_headers(env))
    assert r.status_code == 200, r.text
    return r.json()


def poll(env, c, wait=0.05):
    r = env.http.get(f"/cc/permission/{c['id']}?wait={wait}", headers=cc_headers(env, c["key"]))
    assert r.status_code == 200, r.text
    return r.json()


def test_describe_shows_the_command_file_or_input():
    d = describe(BASH)
    assert d["action"] == "run_command" and d["control"] == "git push origin main"
    assert d["window"] == "Claude Code · demo-app" and "Push to GitHub" in d["detail"]
    e = describe({"tool_name": "Edit", "tool_input": {"file_path": "C:/x/app.py", "old_string": "a", "new_string": "b"}})
    assert e["action"] == "edit_file" and e["control"] == "app.py" and "- a" in e["detail"] and "+ b" in e["detail"]
    m = describe({"tool_name": "mcp__github__create_issue", "tool_input": {"title": "t" * 3000}})
    assert m["action"] == "use_tool" and len(m["detail"]) <= 1500


def test_phone_answers_and_the_pc_side_learns_it(tmp_path):
    with Env(tmp_path) as env:
        d = env.session_client()
        c = create(env)
        ev = env.wait_event(d, lambda e: e["type"] == "approval_request" and e.get("source") == "claude_code")
        assert ev["approval_id"] == c["id"] and ev["expires_at"] == 0 and ev["control"] == "git push origin main"
        listed = d.request("GET", "/approvals").json()
        assert listed[0]["source"] == "claude_code" and "git push" in listed[0]["detail"]
        assert poll(env, c)["decision"] is None                  # still waiting
        got = {}
        t = threading.Thread(target=lambda: got.update(poll(env, c, wait=5)))
        t.start()
        time.sleep(0.2)
        assert d.request("POST", f"/approvals/{c['id']}", {"decision": "allow"}, strong=True).status_code == 200
        t.join(5)
        assert got == {"decision": "allow", "by": "phone"}
        res = env.wait_event(d, lambda e: e["type"] == "approval_resolved" and e["approval_id"] == c["id"])
        assert res["decision"] == "allow" and res["by"] == "phone"
        # the PC dialog clicking a moment later gets the phone's answer, not its own
        r = env.http.post(f"/cc/permission/{c['id']}", content=json.dumps({"decision": "deny"}),
                          headers=cc_headers(env, c["key"])).json()
        assert r == {"result": "already", "decision": "allow", "by": "phone"}


def test_pc_answers_and_the_phone_card_closes(tmp_path):
    with Env(tmp_path) as env:
        d = env.session_client()
        c = create(env)
        r = env.http.post(f"/cc/permission/{c['id']}", content=json.dumps({"decision": "deny"}),
                          headers=cc_headers(env, c["key"]))
        assert r.json()["result"] == "ok"
        res = env.wait_event(d, lambda e: e["type"] == "approval_resolved" and e["approval_id"] == c["id"])
        assert res["decision"] == "deny" and res["by"] == "pc"
        assert d.request("GET", "/approvals").json() == []
        assert d.request("POST", f"/approvals/{c['id']}", {"decision": "allow"}, strong=True).status_code == 409
        assert poll(env, c) == {"decision": "deny", "by": "pc"}


def test_no_timeout_while_the_hook_is_waiting(tmp_path):
    with Env(tmp_path) as env:       # task approvals time out after 1.5 s here; these must not
        d = env.session_client()
        c = create(env)
        env.clock.t += 7 * 24 * 3600
        for _ in range(3):
            assert poll(env, c, wait=0.6)["decision"] is None
        d = env.session_client()      # the old phone session expired with the clock jump
        assert [a["approvalId"] for a in d.request("GET", "/approvals").json()] == [c["id"]]


def test_withdrawn_when_the_hook_is_gone(tmp_path):
    with Env(tmp_path) as env:
        d = env.session_client()
        env.hub.cc.stale = 0.3       # the hook was killed (answered in Claude Code, Esc) and stopped polling
        c = create(env)
        res = env.wait_event(d, lambda e: e["type"] == "approval_resolved" and e["approval_id"] == c["id"], timeout=5)
        assert res["decision"] == "withdrawn"
        assert d.request("GET", "/approvals").json() == []


def test_stop_denies_waiting_prompts(tmp_path):
    with Env(tmp_path) as env:
        d = env.session_client()
        c = create(env)
        assert d.request("POST", "/stop", {}).status_code == 200
        assert poll(env, c)["decision"] == "stop"
        assert hook.output("stop", "phone").count("deny") == 1
        r = create(env)                                         # while STOP is on, new prompts are denied at once
        assert r["decision"] == "deny" and "id" not in r


def test_local_token_required(tmp_path):
    with Env(tmp_path) as env:
        assert env.http.post("/cc/permission", content="{}", headers={"X-CC-Token": "nope"}).status_code == 403
        h = {**cc_headers(env), "X-Forwarded-For": "1.2.3.4"}
        assert env.http.post("/cc/permission", content="{}", headers=h).status_code == 403
        c = create(env)
        assert env.http.get(f"/cc/permission/{c['id']}?wait=0", headers=cc_headers(env, "wrong")).status_code == 404
        r = env.http.post(f"/cc/permission/{c['id']}", content=json.dumps({"decision": "allow"}),
                          headers=cc_headers(env, "wrong"))
        assert r.status_code == 403


class HubViaTestClient:
    """The hook's Http, routed to the in-process app."""

    def __init__(self, env):
        self.env = env

    def call(self, method, path, body=None, key="", timeout=5.0):
        r = self.env.http.request(method, path, content=json.dumps(body) if body is not None else None,
                                  headers=cc_headers(self.env, key))
        if r.status_code >= 400:
            raise hook.urllib.error.HTTPError(path, r.status_code, r.text, None, None)
        return r.json()


def test_hook_pc_dialog_click_wins(tmp_path):
    with Env(tmp_path) as env:
        d = env.session_client()
        seen = {}

        class FakeDialog:
            def __init__(self, info, on_choice):
                seen["info"] = info
                self.on_choice = on_choice

            def loop(self, done):
                time.sleep(0.2)
                self.on_choice("allow")
                done.wait(5)

        decision, by = hook.run(BASH, HubViaTestClient(env), dialog_factory=FakeDialog, poll_wait=0.5)
        assert (decision, by) == ("allow", "pc") and "git push" in seen["info"]["detail"]
        out = json.loads(hook.output(decision, by))
        assert out["hookSpecificOutput"] == {"hookEventName": "PermissionRequest", "decision": {"behavior": "allow"}}
        env.wait_event(d, lambda e: e["type"] == "approval_resolved" and e.get("by") == "pc")


def test_hook_phone_answer_closes_the_dialog(tmp_path):
    with Env(tmp_path) as env:
        d = env.session_client()
        closed = {}

        class FakeDialog:
            def __init__(self, info, on_choice):
                pass

            def loop(self, done):
                closed["by_phone"] = done.wait(10)

        def phone():
            ev = env.wait_event(d, lambda e: e["type"] == "approval_request")
            d.request("POST", f"/approvals/{ev['approval_id']}", {"decision": "deny"}, strong=True)

        threading.Thread(target=phone).start()
        decision, by = hook.run(BASH, HubViaTestClient(env), dialog_factory=FakeDialog, poll_wait=0.5)
        assert (decision, by) == ("deny", "phone") and closed["by_phone"] is True
        out = json.loads(hook.output(decision, by))["hookSpecificOutput"]["decision"]
        assert out["behavior"] == "deny" and "phone" in out["message"]


def test_hook_falls_back_when_hub_is_down_or_withdrawn():
    class Down:
        def call(self, *a, **k):
            raise hook.urllib.error.URLError("refused")
    assert hook.run(BASH, Down(), dialog_factory=None) == (None, None)
    assert hook.output(None) == "" and hook.output("withdrawn") == ""


def test_install_keeps_other_settings(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"model": "opus", "hooks": {"PermissionRequest": [
        {"matcher": "Bash", "hooks": [{"type": "command", "command": "other.sh"}]}],
        "Stop": [{"hooks": [{"type": "command", "command": "x"}]}]}}), "utf-8")
    cc_hook_install.install(p)
    cc_hook_install.install(p)                                   # idempotent
    data = json.loads(p.read_text("utf-8"))
    ours = [h for g in data["hooks"]["PermissionRequest"] for h in g["hooks"] if "cc_permission_hook.py" in h["command"]]
    assert len(ours) == 1 and ours[0]["timeout"] >= 24 * 3600
    assert data["model"] == "opus" and data["hooks"]["Stop"] and cc_hook_install.installed(p)
    cc_hook_install.uninstall(p)
    data = json.loads(p.read_text("utf-8"))
    assert data["hooks"]["PermissionRequest"] == [{"matcher": "Bash", "hooks": [{"type": "command", "command": "other.sh"}]}]
    assert not cc_hook_install.installed(p) and list(tmp_path.glob("settings.json.bak-*"))


def test_parent_watch_helper():
    import os
    import subprocess
    import sys
    assert hook._alive(os.getpid()) is True
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    assert hook._alive(p.pid) is False


def test_hub_agent_is_skipped_so_its_own_approval_tool_decides(monkeypatch, capsys):
    """Field bug 18/11: every ordinary desktop call of a phone task opened the PC dialog and stole the focus."""
    from turbo_hub.runners import build_claude_env
    env = build_claude_env({})
    assert env["TURBO_HUB_AGENT"] == "1"
    assert hook.is_hub_agent(env) and not hook.is_hub_agent({})

    import io
    called = []
    monkeypatch.setattr(hook, "run", lambda *a, **k: called.append(1) or ("allow", "pc"))
    monkeypatch.setattr(hook, "load_token", lambda: "tok")
    monkeypatch.setenv("TURBO_HUB_AGENT", "1")
    monkeypatch.setattr(hook.sys, "stdin", io.TextIOWrapper(io.BytesIO(json.dumps(BASH).encode())))
    assert hook.main() == 0
    assert capsys.readouterr().out == "" and called == []   # no dialog, no hub request, no decision printed

    monkeypatch.delenv("TURBO_HUB_AGENT")
    monkeypatch.setattr(hook.sys, "stdin", io.TextIOWrapper(io.BytesIO(json.dumps(BASH).encode())))
    assert hook.main() == 0
    assert called == [1] and '"behavior": "allow"' in capsys.readouterr().out
