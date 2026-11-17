"""Shared test lock so two agents never run test suites / field runs against desktop-mcp or the desktop at once.

Lock file: %TEMP%\\turbo-desktop-test.lock  (created with O_CREAT|O_EXCL, content = agent name, pid, start time).
 - exists and its pid is alive: wait, retry every 30 s
 - exists and its pid is dead: take it over
 - released (file removed) when the holder finishes

Use as a library (conftest.py and field_run.py do) or as a wrapper:
    python hub\\scripts\\with_lock.py -- hub\\.venv\\Scripts\\python -m pytest -q
"""
from __future__ import annotations

import atexit
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

LOCK = Path(os.environ.get("TURBO_TEST_LOCK") or Path(tempfile.gettempdir()) / "turbo-desktop-test.lock")
AGENT = os.environ.get("TURBO_AGENT_NAME", "hub-android-agent")
_held = False


def pid_alive(pid: int) -> bool:
    if pid == os.getpid():
        return True
    try:
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], capture_output=True, text=True,
                             timeout=10).stdout
        return f'"{pid}"' in out
    except (OSError, subprocess.SubprocessError):
        return True   # cannot tell: assume alive, never steal


def acquire(wait_seconds: float = 3600, poll: float = 30.0, log=print) -> None:
    global _held
    if _held:
        return
    owner = os.environ.get("TURBO_TEST_LOCK_OWNER")   # set by the wrapper below: a child of the lock holder is covered by it
    if owner and owner.isdigit():
        try:
            if json.loads(LOCK.read_text("utf-8")).get("pid") == int(owner):
                return
        except (OSError, ValueError):
            pass
    end = time.time() + wait_seconds
    while True:
        try:
            fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w") as f:
                json.dump({"agent": AGENT, "pid": os.getpid(), "started": time.strftime("%Y-%m-%d %H:%M:%S")}, f)
            _held = True
            atexit.register(release)
            return
        except FileExistsError:
            try:
                info = json.loads(LOCK.read_text("utf-8"))
                holder = int(info.get("pid", 0))
            except (OSError, ValueError):
                holder, info = 0, {}
            if not holder or not pid_alive(holder):
                log(f"lock held by dead pid {holder}: taking over")
                try:
                    LOCK.unlink()
                except OSError:
                    pass
                continue
            if time.time() > end:
                raise TimeoutError(f"test lock still held by {info}")
            log(f"test lock held by {info.get('agent')} (pid {holder}); retrying in {poll:.0f} s")
            time.sleep(poll)


def release() -> None:
    global _held
    if _held:
        try:
            info = json.loads(LOCK.read_text("utf-8"))
            if info.get("pid") == os.getpid():
                LOCK.unlink()
        except (OSError, ValueError):
            pass
        _held = False


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--":
        args = args[1:]
    acquire()
    os.environ["TURBO_TEST_LOCK_OWNER"] = str(os.getpid())
    try:
        sys.exit(subprocess.call(args))
    finally:
        release()
