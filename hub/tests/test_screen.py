import io
import json

from PIL import Image

from conftest import Env
from turbo_hub import config as C, screen
from turbo_hub.__main__ import build_settings
from turbo_hub.app import create_app
from turbo_hub.devclient import DevClient


def _fake_frame(w=400, h=300, color=(220, 180, 140)):
    return Image.new("RGB", (w, h), color), (0, 0, w, h)


def test_screen_redaction_blacks_out_right_rectangle(tmp_path):
    windows = [
        {"title": "Calculator", "rect": (10, 10, 90, 90)},
        {"title": "Code - .env.production", "rect": (100, 40, 240, 160)},
        {"title": "Quản lý Mật Khẩu", "rect": (260, 180, 380, 280)},
    ]
    img, count = screen.redact_image(_fake_frame()[0], windows)
    assert count == 2
    assert img.getpixel((50, 50)) == (220, 180, 140)
    assert img.getpixel((170, 100)) == (0, 0, 0)
    assert img.getpixel((320, 230)) == (0, 0, 0)

    with Env(tmp_path) as env:
        state = tmp_path / "state"
        env.settings.desktop_state_dir = state
        env.settings.screen_grabber = lambda: _fake_frame(1200, 600)
        env.settings.window_enumerator = lambda: [
            {"title": "Calculator", "rect": (0, 0, 200, 200)},
            {"title": "prod credentials", "rect": (300, 150, 900, 450)},
        ]
        d = env.session_client()
        r = d.request("GET", "/screen.jpg?w=600&q=75")
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/jpeg"
        assert r.headers["x-redacted"] == "1"
        out = Image.open(io.BytesIO(r.content))
        assert out.size == (600, 300)
        # (300..900, 150..450) scaled by 0.5 is (150..450, 75..225)
        assert out.getpixel((300, 150)) == (0, 0, 0)
        assert out.getpixel((50, 50))[0] > 180
        sv_file = state / "screen_view.json"
        assert sv_file.exists() and json.loads(sv_file.read_text("utf-8")) == {"until": env.clock() + 5}


def test_screen_rate_limit_and_audit_throttling(tmp_path):
    with Env(tmp_path) as env:
        env.settings.screen_grabber = _fake_frame
        env.settings.window_enumerator = lambda: []
        d = env.session_client()
        assert d.request("GET", "/screen.jpg").status_code == 200
        # Faster than 2 fps (< 0.5 s) -> 429
        env.clock.t += 0.2
        assert d.request("GET", "/screen.jpg").status_code == 429
        # After 0.5 s -> 200, still within 60 s so audit is not duplicated
        env.clock.t += 0.4
        assert d.request("GET", "/screen.jpg").status_code == 200
        audits = [e for e in env.hub.audit.read(50) if e["kind"] == "screen_view"]
        assert len(audits) == 1
        # After 60 s -> audited again
        env.clock.t += 60.0
        assert d.request("GET", "/screen.jpg").status_code == 200
        audits = [e for e in env.hub.audit.read(50) if e["kind"] == "screen_view"]
        assert len(audits) == 2


def test_screen_off_in_strict_and_exposed_in_policy_and_status(tmp_path):
    from fastapi.testclient import TestClient
    cfg = C.load_config(None, "strict")
    s = build_settings(cfg, tmp_path / "hub", "fake", None, 8750, None)
    s.loopback_hosts = ("127.0.0.1", "testclient")
    s.screen_grabber = _fake_frame
    s.window_enumerator = lambda: []
    app = create_app(s)
    with TestClient(app) as http:
        hub = app.state.hub
        info = http.post("/admin/pairing", headers={"X-Admin-Token": hub.store.admin_token}).json()
        d = DevClient(http, hub_pub=info["hubKey"])
        assert d.pair(info["code"]).status_code == 200
        pol = d.request("GET", "/policy").json()
        assert pol["screenView"] == {"enabled": False, "maxFps": 5}
        assert pol["lockRemoteTask"] == "whole_task"
        assert d.start_session(hub.store.totp_secret).status_code == 200
        st = d.request("GET", "/status").json()
        assert st["screenView"] == {"enabled": False, "maxFps": 5}
        assert st["lockRemoteTask"] == "whole_task"
        r = d.request("GET", "/screen.jpg")
        assert r.status_code == 403 and "screen view is off" in r.text


def test_screen_requires_session(env):
    env.settings.screen_grabber = _fake_frame
    env.settings.window_enumerator = lambda: []
    unpaired = DevClient(env.http, clock=env.clock)
    assert unpaired.request("GET", "/screen.jpg").status_code == 401
    paired_no_session = env.paired_client()
    assert paired_no_session.request("GET", "/screen.jpg").status_code == 401
    with_session = env.session_client()
    assert with_session.request("GET", "/screen.jpg").status_code == 200
