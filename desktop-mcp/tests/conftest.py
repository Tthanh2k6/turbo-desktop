import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
FIX = ROOT / "tests" / "fixtures"

# Isolated state for every test run: never touch the real audit log, never use real input by default.
_state = tempfile.mkdtemp(prefix="turbo-desktop-test-")
os.environ["TURBO_DESKTOP_STATE_DIR"] = _state
os.environ["TURBO_DESKTOP_AUDIT"] = str(Path(_state) / "audit.jsonl")
os.environ["TURBO_DESKTOP_NO_INPUT"] = "0" if os.environ.get("TURBO_DESKTOP_REAL_INPUT") == "1" else "1"
os.environ["TURBO_DESKTOP_PRESET"] = "easy"
os.environ["TURBO_DESKTOP_REQUIRE_CLEAN"] = "1"  # hard rule: our tests never launch a session-restore app without a clean path
os.environ["TURBO_DESKTOP_NO_INDICATOR"] = "1"  # Desktop objects in tests do not draw the glow; test_border.py draws it explicitly
os.environ.pop("TURBO_DESKTOP_CONFIG", None)
os.environ["TURBO_DESKTOP_CONFIG"] = str(Path(_state) / "no-such-config.toml")  # ignore any user config

REAL_INPUT = os.environ.get("TURBO_DESKTOP_REAL_INPUT") == "1"


@pytest.fixture(scope="session", autouse=True)
def machine_lock():
    """One UI test run at a time on this PC (shared with the hub agent)."""
    import locking
    locking.acquire("desktop-mcp-pytest", poll=int(os.environ.get("TURBO_LOCK_POLL", "30")))
    yield
    locking.release()


@pytest.fixture(autouse=True)
def clean_state():
    stop = Path(_state) / "STOP"
    if stop.exists():
        stop.unlink()
    alive = Path(_state) / "approver.alive"
    if alive.exists():
        alive.unlink()
    os.environ["TURBO_DESKTOP_PRESET"] = "easy"
    os.environ.pop("TURBO_DESKTOP_APPROVAL", None)
    yield
    for f in (stop, alive):
        if f.exists():
            f.unlink()


@pytest.fixture
def desktop():
    from turbo_desktop.engine import Desktop
    from turbo_desktop.security import AuditLog
    dt = Desktop(audit=AuditLog(Path(_state) / f"a{time.time_ns()}.jsonl"))
    yield dt
    dt.close_launched()  # teardown: close what launch() started, even after a failure


@pytest.fixture
def launch_app(desktop):
    """Launch one of our own fixture exes; always closed afterwards (only processes we started)."""
    procs = []

    def _launch(name, *args):
        exe = FIX / name
        before = {d["hwnd"] for d in desktop.windows_list()}
        from turbo_desktop.engine import no_activate_startupinfo
        p = subprocess.Popen([str(exe), *args], startupinfo=no_activate_startupinfo())
        procs.append(p)
        end = time.time() + 10
        while time.time() < end:
            time.sleep(0.2)
            new = [d for d in desktop.windows_list() if d["hwnd"] not in before and d["pid"] == p.pid]
            if new:
                time.sleep(0.3)
                return new[0]
        raise RuntimeError(f"{name} window did not appear")

    yield _launch
    for p in procs:
        try:
            p.kill()
        except Exception:
            pass
