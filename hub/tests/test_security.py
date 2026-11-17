import json
import time

import pytest

from conftest import Env
from turbo_hub import crypto, totp
from turbo_hub.devclient import DevClient


# ------------------------------------------------------------ pairing
def test_pairing_happy_path(env):
    info = env.new_pairing()
    assert info["url"].startswith("http") and len(info["code"]) == 6 and info["otpauth"].startswith("otpauth://totp/")
    d = DevClient(env.http, hub_pub=info["hubKey"], clock=env.clock)
    r = d.pair(info["code"])
    assert r.status_code == 200
    assert r.json()["deviceId"] == d.device_id and r.json()["hubPub"] == info["hubKey"]
    assert crypto.verify(crypto.pub_from_b64(info["hubKey"]),
                         crypto.canonical_response(200, "/pair", r.content, r.headers["x-hub-ts"], r.request.headers["x-nonce"]),
                         r.headers["x-hub-sig"])
    assert [x["id"] for x in env.admin("GET", "/admin/devices").json()] == [d.device_id]
    # the code is one-time
    assert DevClient(env.http, clock=env.clock).pair(info["code"]).status_code == 403


def test_pairing_wrong_code_and_burn(env):
    info = env.new_pairing()
    d = DevClient(env.http, clock=env.clock)
    assert d.pair("000000" if info["code"] != "000000" else "111111").status_code == 403
    # 5 attempts burn the real code
    for _ in range(4):
        d.pair("999999")
    assert d.pair("999999").status_code in (403, 429)   # 5th/6th strike: code burned and source locked
    env.clock.t += 901                                  # lockout over, the burned code still fails
    assert d.pair(info["code"]).status_code == 403
    assert env.admin("GET", "/admin/devices").json() == []


def test_pairing_expired_code(env):
    info = env.new_pairing()
    env.clock.t += 301
    assert DevClient(env.http, clock=env.clock).pair(info["code"]).status_code == 403


def test_pairing_disabled_unless_started_at_pc(env):
    assert DevClient(env.http, clock=env.clock).pair("123456").status_code == 403


def test_pairing_and_admin_refused_through_tunnel(env):
    info = env.new_pairing()
    d = DevClient(env.http, clock=env.clock)
    body = {"code": info["code"], "name": "x", "pub": d.pub, "authPub": d.auth_pub}
    raw = json.dumps(body, separators=(",", ":")).encode()
    h = d._headers("POST", "/pair", raw, strong=True, device=False)
    h["Cf-Connecting-Ip"] = "203.0.113.9"
    assert env.http.post("/pair", content=raw, headers=h).status_code == 403
    r = env.http.post("/admin/pairing", headers={"X-Admin-Token": env.hub.store.admin_token, "Cf-Ray": "abc"})
    assert r.status_code == 403
    assert env.http.post("/admin/pairing").status_code == 403  # no token


# ------------------------------------------------------------ signed requests
def test_unpaired_device_rejected_and_alerted(env):
    paired = env.session_client()
    stranger = DevClient(env.http, clock=env.clock)
    r = stranger.request("GET", "/hello")
    assert r.status_code == 401
    ev = env.wait_event(paired, lambda e: e["type"] == "hub_alert")
    assert "unpaired" in ev["what"]
    kinds = [e["data"].get("why") for e in env.hub.audit.read(20) if e["kind"] == "rejected"]
    assert "unknown device" in kinds


def test_bad_signature(env):
    d = env.session_client()
    body = b'{"text":"hello"}'
    h = d._headers("POST", "/tasks", body)
    assert env.http.post("/tasks", content=b'{"text":"EVIL"}', headers=h).status_code == 401  # body tampered
    other = DevClient(env.http, clock=env.clock)
    other.device_id = d.device_id  # impersonation with another key
    assert other.request("GET", "/hello").status_code == 401


def test_old_timestamp_and_future(env):
    d = env.paired_client()
    env.clock.t += 100      # hub has been up for a while
    assert d.request("GET", "/hello", ts=int(env.clock()) - 61).status_code == 401
    assert d.request("GET", "/hello", ts=int(env.clock()) + 61).status_code == 401
    assert d.request("GET", "/hello", ts=int(env.clock()) - 30).status_code == 200


def test_nonce_replay(env):
    d = env.paired_client()
    assert d.request("GET", "/hello", nonce="n-fixed-1").status_code == 200
    assert d.request("GET", "/hello", nonce="n-fixed-1").status_code == 401


def test_response_signature_detects_fake_hub(env):
    d = env.paired_client()
    d.hub_pub = crypto.pub_to_b64(crypto.generate_key().public_key())  # pretend we pinned another hub
    with pytest.raises(AssertionError):
        d.request("GET", "/hello")


def test_body_size_limit(env):
    d = env.session_client()
    r = d.request("POST", "/tasks", {"text": "x" * 70000})
    assert r.status_code == 413


# ------------------------------------------------------------ sessions, biometric key, TOTP
def test_session_needs_biometric_signature_and_totp(env):
    d = env.paired_client()
    secret = env.hub.store.totp_secret
    code = totp.code_at(secret, int(env.clock() // 30))
    assert d.request("POST", "/session/start", {"totp": code}, strong=False).status_code == 401  # no X-Auth-Sig
    assert d.request("POST", "/session/start", {"totp": "000000"}, strong=True).status_code == 401
    r = d.start_session(secret)
    assert r.status_code == 200 and r.json()["expiresAt"] == int(env.clock()) + 7200
    # no session -> no tasks
    d2 = env.paired_client()
    assert d2.request("GET", "/tasks").status_code == 401


def test_totp_functions():
    secret = bytes.fromhex("3132333435363738393031323334353637383930")  # RFC 6238 test secret
    assert totp.code_at(secret, 59 // 30) == "287082"            # RFC 6238 vector for T=59 (last 6 digits)
    now = 1_000_000.0
    step = int(now // 30)
    c = totp.code_at(secret, step)
    assert totp.verify(secret, c, now, 0) == step
    assert totp.verify(secret, c, now, step) is None              # reuse of the same step
    assert totp.verify(secret, totp.code_at(secret, step - 1), now, 0) == step - 1   # +-1 window
    assert totp.verify(secret, totp.code_at(secret, step + 1), now, 0) == step + 1
    assert totp.verify(secret, totp.code_at(secret, step - 2), now, 0) is None
    assert totp.verify(secret, totp.code_at(secret, step + 2), now, 0) is None
    for t, want in ((1111111109, "081804"), (1111111111, "050471"), (1234567890, "005924"), (2000000000, "279037")):
        assert totp.code_at(secret, t // 30) == want                # RFC 6238 SHA1 vectors (6-digit tail)
    assert totp.verify(secret, "12345", now, 0) is None and totp.verify(secret, "abcdef", now, 0) is None
    assert totp.otpauth_uri(secret).startswith("otpauth://totp/turbo-desktop:pc?secret=")


def test_totp_code_cannot_be_reused_for_second_session(env):
    d = env.paired_client()
    secret = env.hub.store.totp_secret
    code = totp.code_at(secret, int(env.clock() // 30))
    assert d.start_session(code=code).status_code == 200
    assert d.start_session(code=code).status_code == 401
    assert d.start_session(secret, step_offset=1).status_code == 200  # next step still fine


def test_session_expires_after_2h(env):
    d = env.session_client()
    assert d.request("GET", "/status").status_code == 200
    env.clock.t += 7201
    assert d.request("GET", "/status").status_code == 401


def test_lockout_after_5_bad_signatures(env):
    d = env.paired_client()
    for _ in range(5):
        h = d._headers("GET", "/hello", b"")
        h["X-Sig"] = "AAAA"
        env.http.get("/hello", headers=h)
    assert d.request("GET", "/hello").status_code == 429    # even a valid request from the same source
    assert any(e["kind"] == "lockout" for e in env.hub.audit.read(50))
    env.clock.t += 901
    assert d.request("GET", "/hello").status_code == 200


def test_lockout_after_5_wrong_totp(env):
    d = env.paired_client()
    for _ in range(5):
        d.request("POST", "/session/start", {"totp": "000000"}, strong=True)
    assert d.request("GET", "/hello").status_code == 429


def test_dpapi_and_secret_files_not_plaintext(env):
    from turbo_hub import dpapi
    assert dpapi.unprotect(dpapi.protect(b"secret")) == b"secret"
    env.paired_client()
    blob = (env.settings.data_dir / "devices.dpapi").read_bytes()
    assert b"pub" not in blob and b"test-phone" not in blob
    assert b"PRIVATE" not in (env.settings.data_dir / "hub_key.dpapi").read_bytes()
    # reload keeps the same hub key and TOTP secret
    from turbo_hub.store import SecretStore
    again = SecretStore(env.settings.data_dir)
    assert again.hub_pub_b64 == env.hub.store.hub_pub_b64 and again.totp_secret == env.hub.store.totp_secret
    assert len(again.list_devices()) == 1


# ------------------------------------------------------------ audit chain
def test_audit_chain_detects_tampering(env):
    d = env.session_client()
    d.request("POST", "/tasks", {"text": "hi"})
    env.wait_event(d, lambda e: e["type"] == "task_finished" or e["type"] == "approval_request")
    ok = d.request("GET", "/audit").json()
    assert ok["chainOk"] and len(ok["entries"]) > 3
    path = env.settings.data_dir / "audit.jsonl"
    lines = path.read_text("utf-8").splitlines()
    assert env.hub.audit.verify()[0]
    # edit a line
    tampered = lines.copy()
    tampered[2] = tampered[2].replace('"kind":"', '"kind":"x', 1)
    path.write_text("\n".join(tampered) + "\n", "utf-8")
    assert not env.hub.audit.verify()[0]
    assert d.request("GET", "/audit").json()["chainOk"] is False
    # remove a middle line
    path.write_text("\n".join(lines[:2] + lines[3:]) + "\n", "utf-8")
    assert not env.hub.audit.verify()[0]
    # restore
    path.write_text("\n".join(lines) + "\n", "utf-8")
    assert env.hub.audit.verify()[0]


def test_session_expiry_then_reopen_with_new_totp(env):
    d = env.session_client()
    env.clock.t += 7201
    assert d.request("GET", "/status").status_code == 401
    code_now = totp.code_at(env.hub.store.totp_secret, int(env.clock() // 30))
    assert d.start_session(code=code_now).status_code == 200            # no QR, no PC access: biometric + TOTP only
    assert d.request("GET", "/status").status_code == 200


def test_hub_restart_rejects_old_requests_and_needs_reopen(tmp_path):
    from fastapi.testclient import TestClient
    from turbo_hub.app import create_app
    with Env(tmp_path) as env:
        d = env.session_client()
        old = d._headers("GET", "/status", b"")           # a signed request captured before the restart
        data_dir, clock = env.settings.data_dir, env.clock
    env.clock.t += 5
    from turbo_hub.app import Settings
    s2 = Settings(data_dir=data_dir, clock=clock, loopback_hosts=("127.0.0.1", "testclient"))
    with TestClient(create_app(s2)) as http:
        assert http.get("/status", headers=old).status_code == 401            # replay after restart refused
        d.http = http
        assert d.request("GET", "/status").status_code == 401                # in-memory session gone: reopen
        secret = create_app.__globals__["SecretStore"](data_dir).totp_secret
        assert d.start_session(secret, step_offset=1).status_code == 200   # same step as before is refused (no reuse)
        assert d.request("GET", "/status").status_code == 200                # device pairing survived (DPAPI file)


def test_hub_restart_keeps_session_when_persist_is_on(tmp_path):
    from fastapi.testclient import TestClient
    from turbo_hub.app import Settings, create_app
    clock = lambda: 1_800_000_000.0  # noqa: E731
    mk = lambda: Settings(data_dir=tmp_path / "h", clock=clock, persist_sessions=True,  # noqa: E731
                          loopback_hosts=("127.0.0.1", "testclient"))
    app = create_app(mk())
    with TestClient(app) as http:
        hub = app.state.hub
        info = http.post("/admin/pairing", headers={"X-Admin-Token": hub.store.admin_token}).json()
        d = DevClient(http, hub_pub=info["hubKey"], clock=clock)
        assert d.pair(info["code"]).status_code == 200
        assert d.start_session(hub.store.totp_secret).status_code == 200
    with TestClient(create_app(mk())) as http2:
        d.http = http2
        assert d.request("GET", "/status").status_code == 200
