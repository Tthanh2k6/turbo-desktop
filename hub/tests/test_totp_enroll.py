import json

from conftest import Env
from turbo_hub import totp
from turbo_hub.devclient import DevClient

PROXY = {"X-Forwarded-For": "1.2.3.4"}


def admin_totp(env, rotate=None, **hdr):
    h = {"X-Admin-Token": env.hub.store.admin_token, **hdr}
    return env.http.post("/admin/totp", json=({"rotate": rotate} if rotate is not None else {}), headers=h)


def pair(env):
    info = env.new_pairing()
    d = DevClient(env.http, hub_pub=info["hubKey"], clock=env.clock)
    r = d.pair(info["code"])
    assert r.status_code == 200, r.text
    return d, r.json()


def test_pair_reply_has_needs_and_enroll_flag(env):
    _, j = pair(env)
    assert j["needs"] == {"totp": True, "biometric": True} and j["totpEnroll"] is True


def test_pair_without_totp_does_not_open_window(tmp_path):
    with Env(tmp_path) as env:
        env.settings.totp_required = False
        env.settings.biometric_required = False
        d, j = pair(env)
        assert j["needs"] == {"totp": False, "biometric": False} and j["totpEnroll"] is False
        assert d.request("GET", "/totp/enroll", strong=True).status_code == 403
        assert admin_totp(env).status_code == 409


def test_enroll_works_once_then_closed(env):
    d, _ = pair(env)
    r = d.request("GET", "/totp/enroll", strong=True)
    assert r.status_code == 200
    j = r.json()
    assert j["otpauth"] == totp.otpauth_uri(env.hub.store.totp_secret)
    assert j["secret"] == totp.b32(env.hub.store.totp_secret) and "=" not in j["secret"]
    assert (j["issuer"], j["account"], j["digits"], j["period"]) == ("turbo-desktop", "pc", 6, 30)
    r2 = d.request("GET", "/totp/enroll", strong=True)
    assert r2.status_code == 403 and r2.json() == {"detail": "enrollment closed"}


def test_enroll_requires_both_keys(env):
    d, _ = pair(env)
    assert d.request("GET", "/totp/enroll", strong=False).status_code == 401
    # the failed attempt must not have burned the window
    assert d.request("GET", "/totp/enroll", strong=True).status_code == 200


def test_enroll_window_expires(env):
    d, _ = pair(env)
    env.clock.t += env.settings.pair_code_ttl + 1
    r = d.request("GET", "/totp/enroll", strong=True)
    assert r.status_code == 403 and r.json()["detail"] == "enrollment closed"


def test_enroll_refused_through_proxy_and_keeps_window(env):
    d, _ = pair(env)
    r = d.request("GET", "/totp/enroll", strong=True, **{})
    assert r.status_code == 200  # sanity: local works
    d2, _ = pair(env)
    body = b""
    h = d2._headers("GET", "/totp/enroll", body, strong=True)
    r = env.http.get("/totp/enroll", headers={**h, **PROXY})
    assert r.status_code == 403 and "local only" in r.json()["detail"]
    assert d2.request("GET", "/totp/enroll", strong=True).status_code == 200


def test_secret_never_in_audit_log(env):
    d, _ = pair(env)
    d.request("GET", "/totp/enroll", strong=True)
    admin_totp(env, rotate=True)
    log = (env.settings.data_dir / "audit.jsonl").read_text("utf-8")
    assert totp.b32(env.hub.store.totp_secret) not in log and env.hub.store.totp_secret.hex() not in log
    assert "totp_enroll_fetched" in log and "totp_rotated" in log and "totp_enroll_opened" in log


def test_admin_totp_opens_window_and_rotate_invalidates_old_code(env):
    d, _ = pair(env)
    assert d.request("GET", "/totp/enroll", strong=True).status_code == 200   # window used up
    old = env.hub.store.totp_secret
    r = admin_totp(env, rotate=False)
    assert r.status_code == 200 and env.hub.store.totp_secret == old
    assert r.json()["expiresIn"] == int(env.settings.pair_code_ttl)
    r = admin_totp(env, rotate=True)
    j = r.json()
    new = env.hub.store.totp_secret
    assert new != old and j["secret"] == totp.b32(new) and j["otpauth"] == totp.otpauth_uri(new)
    assert env.hub.store.totp_last_step == 0
    assert d.start_session(code=totp.code_at(old, int(env.clock() // 30))).status_code == 401
    assert d.start_session(new).status_code == 200
    # persisted
    from turbo_hub.store import SecretStore
    assert SecretStore(env.settings.data_dir).totp_secret == new
    # the window opened by rotate allows exactly one fetch
    assert d.request("GET", "/totp/enroll", strong=True).json()["secret"] == totp.b32(new)
    assert d.request("GET", "/totp/enroll", strong=True).status_code == 403


def test_admin_totp_refuses_non_local(env):
    h = {"X-Admin-Token": env.hub.store.admin_token}
    assert env.http.post("/admin/totp", json={}, headers={**h, **PROXY}).status_code == 403
    assert env.http.post("/admin/totp", json={}, headers={"X-Admin-Token": "nope"}).status_code == 403
    assert env.http.post("/admin/totp", json={}).status_code == 403
    env.settings.loopback_hosts = ("127.0.0.1",)
    assert env.http.post("/admin/totp", json={}, headers=h).status_code == 403
    assert env.hub.totp_window_exp == 0.0


def test_policy_without_session(env):
    d, _ = pair(env)
    assert d.session is None
    r = d.request("GET", "/policy")
    assert r.status_code == 200
    j = r.json()
    assert j["needs"] == {"totp": True, "biometric": True} and "preset" in j and "sessionHours" in j
    assert DevClient(env.http, clock=env.clock).request("GET", "/policy").status_code == 401
