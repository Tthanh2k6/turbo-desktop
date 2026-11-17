import asyncio
import sys
from pathlib import Path

import pytest

from conftest import Env
from turbo_hub import config as C
from turbo_hub.__main__ import build_settings, main
from turbo_hub.devclient import DevClient
from turbo_hub.runners import GenericRunner, fill_command, line_to_event, build_claude_command


def ev(label=None, window=None, process=None, action="click", keys=None):
    inp = {"action": action}
    if keys:
        inp["keys"] = keys
    return {"tool": "mcp__desktop__act", "input": inp, "control": label, "window": window, "process": process,
            "action": action}


def test_default_is_easy_local_only():
    cfg = C.load_config(None)
    assert cfg["preset"] == "easy" and cfg["server"]["connections"] == ["local"]
    assert cfg["session"]["hours"] == 12 and not cfg["auth"]["totp"] and not cfg["auth"]["biometric"]
    assert cfg["approval"]["enabled"] == ["permanent_delete", "payment", "uninstall", "windows_security"]
    assert cfg["deny_zones"]["password_managers"] is False
    assert cfg["input_lock"]["remote_task"] == "whole_task" and cfg["input_lock"]["max_task_minutes"] == 15
    assert cfg["screen_view"] == {"enabled": True, "max_fps": 2}
    assert r"\.env(\.|\b)" in cfg["privacy"]["secret_title_patterns"] and "mật khẩu" in cfg["privacy"]["secret_title_patterns"]


def test_presets_balanced_and_strict():
    b = C.load_config(None, "balanced")
    assert b["session"]["hours"] == 2 and b["auth"]["totp"] and not b["auth"]["biometric"]
    assert b["server"]["connections"] == ["local", "lan", "tailscale"] and b["deny_zones"]["banking"]
    assert b["input_lock"]["remote_task"] == "whole_task" and b["input_lock"]["max_task_minutes"] == 15
    assert b["screen_view"] == {"enabled": True, "max_fps": 2}
    s = C.load_config(None, "strict")
    assert s["auth"]["biometric"] and s["cloudflare"]["require_access"] and "cloudflare" in s["server"]["connections"]
    assert "task_manager" in s["approval"]["enabled"] and s["deny_zones"]["windows_security_app"]
    assert s["input_lock"]["remote_task"] == "whole_task" and s["input_lock"]["max_task_minutes"] == 15
    assert s["screen_view"] == {"enabled": False, "max_fps": 2}
    with pytest.raises(ValueError):
        C.load_config(None, "nope")


def test_user_file_overrides_single_items(tmp_path):
    f = tmp_path / "turbo-desktop.toml"
    f.write_text('preset = "balanced"\n[session]\nhours = 5\n[approval]\nenabled = ["send"]\n'
                 '[approval.category.send]\ncontrols = ["\\\\bdispatch\\\\b"]\n', "utf-8")
    cfg = C.load_config(f)
    assert cfg["session"]["hours"] == 5 and cfg["auth"]["totp"] is True            # preset kept, one item changed
    assert C.approval_required(cfg, ev("Dispatch"))
    assert not C.approval_required(cfg, ev("Send"))                                 # category words replaced by user
    assert not C.approval_required(cfg, ev("Delete"))                               # 'delete' category disabled


def test_approval_rules_per_preset():
    easy, bal, strict = (C.load_config(None, p) for p in C.PRESETS)
    assert C.approval_required(easy, ev("Xóa vĩnh viễn")) and C.approval_required(easy, ev("Thanh toán"))
    assert C.approval_required(easy, ev("Uninstall"))
    assert C.approval_required(easy, ev(window="Windows Security"))
    assert not C.approval_required(easy, ev("Send")) and not C.approval_required(easy, ev("Delete"))
    assert C.approval_required(bal, ev("Send")) and C.approval_required(bal, ev("Gửi"))
    assert C.approval_required(bal, ev("Delete")) and C.approval_required(bal, ev("Install"))
    assert C.approval_required(bal, ev("x", process="powershell.exe"))
    assert not C.approval_required(bal, ev("Save")) and not C.approval_required(bal, ev("Sender name"))
    assert not C.approval_required(bal, ev("OK", window="Delete file"))             # confirm_dialog only in strict
    assert C.approval_required(strict, ev("OK", window="Delete file"))
    assert not C.approval_required(strict, ev("OK", window="Calculator"))
    assert C.approval_required(strict, ev(action="press_keys", keys="Enter", window="Zalo - chat"))
    assert not C.approval_required(strict, ev(action="press_keys", keys="Enter", window="Calculator"))
    assert C.approval_required(strict, ev(process="Taskmgr"))
    assert not C.approval_required(strict, {"tool": "Read", "input": {}})            # not a desktop tool
    assert not C.approval_required(strict, ev("Delete", action="inspect"))           # reads never ask


def test_classifier_fails_closed():
    cfg = C.load_config(None)
    cfg["approval"]["category"]["payment"]["controls"] = ["("]                       # broken regex
    assert C.make_classifier(cfg)(ev("anything")) is True


def test_setup_writes_file_and_loads_back(tmp_path, monkeypatch):
    monkeypatch.setenv("TURBO_HUB_DATA", str(tmp_path))
    monkeypatch.delenv("TURBO_DESKTOP_CONFIG", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))      # never touch the real %APPDATA%
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.chdir(tmp_path)
    main(["setup", "--preset", "balanced"])
    written = tmp_path / "appdata" / "turbo-desktop" / "turbo-desktop.toml"
    assert C.load_config(written)["preset"] == "balanced"


def test_settings_from_config_and_easy_flow_without_phone_factors(tmp_path):
    cfg = C.load_config(None, "easy")
    s = build_settings(cfg, tmp_path / "hub", "fake", None, 8750, None)
    assert not s.totp_required and not s.biometric_required and s.session_ttl == 12 * 3600
    s.loopback_hosts = ("127.0.0.1", "testclient")
    from fastapi.testclient import TestClient
    from turbo_hub.app import create_app
    app = create_app(s)
    with TestClient(app) as http:
        hub = app.state.hub
        info = http.post("/admin/pairing", headers={"X-Admin-Token": hub.store.admin_token}).json()
        assert info["otpauth"] is None and info["needs"] == {"totp": False, "biometric": False}
        d = DevClient(http, hub_pub=info["hubKey"])
        # no biometric key at all, no TOTP
        import json
        from turbo_hub import crypto
        body = json.dumps({"code": info["code"], "name": "p", "pub": d.pub}, separators=(",", ":")).encode()
        h = d._headers("POST", "/pair", body, device=False)
        assert http.post("/pair", content=body, headers=h).status_code == 200
        r = d.request("POST", "/session/start", {})
        assert r.status_code == 200 and r.json()["expiresAt"] - d.clock() < 12 * 3600 + 5
        d.session = r.json()["sessionId"]
        assert d.request("GET", "/status").status_code == 200


def test_local_admin_task_without_phone(tmp_path):
    with Env(tmp_path) as env:
        tok = {"X-Admin-Token": env.hub.store.admin_token}
        r = env.http.post("/admin/tasks", json={"text": "hello"}, headers=tok)
        assert r.status_code == 200
        import time
        end = time.time() + 5
        aid = None
        while time.time() < end and not aid:
            for e in env.http.get("/admin/events?since=0", headers=tok).json():
                if e["type"] == "approval_request":
                    aid = e["approval_id"]
            time.sleep(0.05)
        assert aid
        assert env.http.post(f"/admin/approvals/{aid}", json={"decision": "allow"}, headers=tok).json()["result"] == "ok"
        assert env.http.post("/admin/tasks", json={"text": "x"}).status_code == 403   # token required


def test_proxy_requests_need_cloudflare_enabled_and_access(tmp_path):
    with Env(tmp_path) as env:
        env.settings.connections = ("local",)
        d = env.paired_client()
        h = d._headers("GET", "/hello", b"")
        h["Cf-Connecting-Ip"] = "1.2.3.4"
        assert env.http.get("/hello", headers=h).status_code == 403
        env.settings.connections = ("local", "cloudflare")
        env.settings.require_access_header = True
        h = d._headers("GET", "/hello", b"")
        h["Cf-Connecting-Ip"] = "1.2.3.4"
        assert env.http.get("/hello", headers=h).status_code == 403
        h = d._headers("GET", "/hello", b"")
        h.update({"Cf-Connecting-Ip": "1.2.3.4", "Cf-Access-Jwt-Assertion": "x"})
        assert env.http.get("/hello", headers=h).status_code == 200


# ------------------------------------------------------------ pluggable agent command
def test_command_templates():
    assert fill_command(["codex", "exec", "{task}"], task="do it") == ["codex", "exec", "do it"]
    cmd = build_claude_command("claude", "cfg.json", ["myagent", "--cfg", "{mcp_config}", "--tool", "{approval_tool}"])
    assert cmd == ["myagent", "--cfg", "cfg.json", "--tool", "mcp__turbohub__approve"]
    assert C.default_agent_command("claude-stream-json", "C:/c.exe")[0] == "C:/c.exe"


def test_line_parsers():
    assert line_to_event("hello\n", "text") == {"type": "text", "text": "hello"}
    assert line_to_event('{"message": "hi", "x": 1}', "jsonl") == {"type": "text", "text": "hi"}
    assert line_to_event("not json", "jsonl")["text"] == "not json"
    assert line_to_event("  \n", "text") is None


def test_generic_runner_runs_any_cli():
    async def go():
        out = []

        async def emit(e):
            out.append(e)

        async def gate(c):
            return True

        r = GenericRunner([sys.executable, "-c", "import sys; print('step 1'); print('answer: ' + sys.argv[1])", "{task}"])
        assert await r.run("t", "42", emit, gate) == "done"
        assert [e["text"] for e in out] == ["step 1", "answer: 42", "answer: 42"] and out[-1]["type"] == "final"
        bad = GenericRunner([sys.executable, "-c", "raise SystemExit(3)"])
        assert await bad.run("t", "x", emit, gate) == "failed"
        assert await GenericRunner(["no-such-binary-xyz"]).run("t", "x", emit, gate) == "failed"
    asyncio.run(go())


def test_config_lookup_order(tmp_path, monkeypatch):
    appdata, home, cwd = tmp_path / "appdata", tmp_path / "home", tmp_path / "cwd"
    for d in (appdata / "turbo-desktop", home, cwd):
        d.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.chdir(cwd)
    monkeypatch.delenv("TURBO_DESKTOP_CONFIG", raising=False)
    assert C.user_config_path(tmp_path) == appdata / "turbo-desktop" / "turbo-desktop.toml"      # nothing exists: default
    (home / "turbo-desktop.toml").write_text("")
    assert C.user_config_path(tmp_path) == home / "turbo-desktop.toml"
    (appdata / "turbo-desktop" / "turbo-desktop.toml").write_text("")
    assert C.user_config_path(tmp_path) == appdata / "turbo-desktop" / "turbo-desktop.toml"
    (cwd / "turbo-desktop.toml").write_text("")
    assert C.user_config_path(tmp_path) == cwd / "turbo-desktop.toml"
    monkeypatch.setenv("TURBO_DESKTOP_CONFIG", str(tmp_path / "x.toml"))
    assert C.user_config_path(tmp_path) == tmp_path / "x.toml"


def test_agent_env_carries_config_and_preset(tmp_path, monkeypatch):
    import json
    from turbo_hub.__main__ import agent_env
    from turbo_hub.runners import ClaudeRunner
    cfgfile = tmp_path / "my.toml"
    cfgfile.write_text('preset = "balanced"\n')
    monkeypatch.setenv("TURBO_DESKTOP_CONFIG", str(cfgfile))
    cfg = C.load_config(C.user_config_path(tmp_path))
    env = agent_env(cfg, tmp_path)
    assert env["TURBO_DESKTOP_CONFIG"] == str(cfgfile) and env["TURBO_DESKTOP_PRESET"] == "balanced"
    mcp = tmp_path / "mcp.json"
    mcp.write_text(json.dumps({"mcpServers": {"desktop": {"command": "x", "env": {"KEEP": "1"}}}}))
    r = ClaudeRunner("http://127.0.0.1:1", "t", str(mcp), claude_path="claude", server_env=env)
    written = json.loads(Path(r.write_mcp_config()).read_text())["mcpServers"]["desktop"]["env"]
    assert written["TURBO_DESKTOP_CONFIG"] == str(cfgfile) and written["TURBO_DESKTOP_PRESET"] == "balanced"
    assert written["KEEP"] == "1"
    # and the system_state call gets the same env
    s = build_settings(cfg, tmp_path / "hub", "agent", None, 8750, str(mcp))
    assert s.system_state is not None


def test_setup_with_phone_adds_lan(tmp_path, monkeypatch):
    monkeypatch.setenv("TURBO_HUB_DATA", str(tmp_path))
    monkeypatch.setenv("TURBO_DESKTOP_CONFIG", str(tmp_path / "t.toml"))
    main(["setup", "--preset", "easy", "--phone"])
    assert C.load_config(tmp_path / "t.toml")["server"]["connections"] == ["local", "lan"]
    main(["setup", "--preset", "easy", "--no-phone"])
    assert C.load_config(tmp_path / "t.toml")["server"]["connections"] == ["local"]
