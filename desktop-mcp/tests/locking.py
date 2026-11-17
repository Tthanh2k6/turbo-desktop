"""Shared machine-wide lock so two agents never run UI tests / field runs at the same time.
Lock file: %TEMP%\\turbo-desktop-test.lock (os.open O_CREAT|O_EXCL). Holder info: agent name, pid, start time."""
import ctypes
import json
import os
import tempfile
import time

LOCK = os.path.join(tempfile.gettempdir(), "turbo-desktop-test.lock")


def pid_alive(pid: int) -> bool:
    h = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))
    if not h:
        return False
    code = ctypes.c_ulong()
    ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
    ctypes.windll.kernel32.CloseHandle(h)
    return code.value == 259  # STILL_ACTIVE


def acquire(agent="desktop-mcp", poll=30, owner_pid=None, log=print):
    pid = owner_pid or os.getpid()
    while True:
        try:
            fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, json.dumps({"agent": agent, "pid": pid, "started": time.strftime("%Y-%m-%d %H:%M:%S")}).encode())
            os.close(fd)
            return
        except FileExistsError:
            try:
                with open(LOCK, encoding="utf-8") as f:
                    info = json.load(f)
                holder = info.get("pid")
            except Exception:
                info, holder = {}, None
            if holder and holder == pid:
                return
            if not holder or not pid_alive(holder):
                try:
                    os.remove(LOCK)  # stale: take over
                except OSError:
                    pass
                continue
            log(f"[lock] held by {info.get('agent')} pid {holder} since {info.get('started')}; retry in {poll}s")
            time.sleep(poll)


def release():
    try:
        with open(LOCK, encoding="utf-8") as f:
            info = json.load(f)
        if info.get("pid") == os.getpid():
            os.remove(LOCK)
    except Exception:
        pass
