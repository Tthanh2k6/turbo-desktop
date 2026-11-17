import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import with_lock  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _shared_test_lock():
    """Never run at the same time as the desktop-mcp suite or a field run (shared %TEMP%\\turbo-desktop-test.lock)."""
    with_lock.acquire()
    yield
    with_lock.release()

from fastapi.testclient import TestClient

from turbo_hub.app import Settings, create_app
from turbo_hub.devclient import DevClient
from turbo_hub.runners import FakeRunner


class Clock:
    def __init__(self):
        self.t = time.time()

    def __call__(self):
        return self.t


class Env:
    def __init__(self, tmp_path, runner_script=None, approval_timeout=1.5, system_state=None):
        self.clock = Clock()
        self.runner = FakeRunner(runner_script)
        self.settings = Settings(data_dir=tmp_path / "hub", runner_factory=lambda: self.runner,
                                 approval_timeout=approval_timeout, clock=self.clock,
                                 loopback_hosts=("127.0.0.1", "testclient"), system_state=system_state)
        self.app = create_app(self.settings)
        self.hub = self.app.state.hub
        self.http = TestClient(self.app)

    def admin(self, method, path):
        return self.http.request(method, path, headers={"X-Admin-Token": self.hub.store.admin_token})

    def new_pairing(self):
        r = self.admin("POST", "/admin/pairing")
        assert r.status_code == 200, r.text
        return r.json()

    def paired_client(self) -> DevClient:
        info = self.new_pairing()
        d = DevClient(self.http, hub_pub=info["hubKey"], clock=self.clock)
        r = d.pair(info["code"])
        assert r.status_code == 200, r.text
        return d

    def session_client(self) -> DevClient:
        d = self.paired_client()
        r = d.start_session(self.hub.store.totp_secret)
        assert r.status_code == 200, r.text
        return d

    def wait_event(self, d: DevClient, pred, timeout=5.0):
        end = time.time() + timeout
        while time.time() < end:
            evs = d.request("GET", "/events/poll?since=0").json()
            for e in evs:
                if pred(e):
                    return e
            time.sleep(0.03)
        raise AssertionError("event not seen; got " + str([e["type"] for e in evs]))


@pytest.fixture
def env(tmp_path):
    with Env(tmp_path) as e:
        yield e


class _Ctx(Env):
    def __enter__(self):
        self.http.__enter__()
        return self

    def __exit__(self, *a):
        self.http.__exit__(*a)


Env = _Ctx  # noqa: E305  (context-manager wrapper so the app loop starts/stops cleanly)
