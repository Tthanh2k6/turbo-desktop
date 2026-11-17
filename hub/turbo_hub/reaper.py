"""Never leave an agent process behind when the hub dies (field bug: killing the hub orphaned `claude` and its MCP servers).

While the hub runs it records the agent's pid and image name in agent.pid. On the next start (and on clean shutdown) a
process with that pid AND the same image name is killed together with its children.
"""
from __future__ import annotations

import csv
import io
import json
import subprocess
from pathlib import Path


def image_of(pid: int) -> str | None:
    try:
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], capture_output=True,
                             text=True, timeout=10).stdout
        rows = list(csv.reader(io.StringIO(out)))
        return rows[0][0] if rows and len(rows[0]) > 1 and rows[0][1] == str(pid) else None
    except (OSError, subprocess.SubprocessError):
        return None


def record(pid_file: Path, pid: int | None) -> None:
    if pid is None:
        if pid_file.exists():
            pid_file.write_text("{}", "utf-8")
        return
    pid_file.write_text(json.dumps({"pid": pid, "image": image_of(pid)}), "utf-8")


def reap(pid_file: Path) -> bool:
    """Kill the recorded agent (with children) if it is still the same program. Returns True if something was killed."""
    try:
        data = json.loads(pid_file.read_text("utf-8"))
    except (OSError, ValueError):
        return False
    pid, image = data.get("pid"), data.get("image")
    if not pid or not image or image_of(pid) != image:
        return False
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    pid_file.write_text("{}", "utf-8")
    return True


# ---- Windows job object: the agent dies with the hub even if the hub is killed (no chance to clean up)
_job = None


def bind_to_hub_lifetime(pid: int) -> bool:
    """Put the process in a job object with KILL_ON_JOB_CLOSE. The handle closes when the hub process ends."""
    global _job
    import sys
    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.OpenProcess.restype = wintypes.HANDLE

    class BASIC(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

    class IOC(ctypes.Structure):
        _fields_ = [(n, ctypes.c_uint64) for n in ("a", "b", "c", "d", "e", "f")]

    class EXT(ctypes.Structure):
        _fields_ = [("Basic", BASIC), ("Io", IOC), ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    if _job is None:
        _job = k32.CreateJobObjectW(None, None)
        info = EXT()
        info.Basic.LimitFlags = 0x2000   # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not k32.SetInformationJobObject(_job, 9, ctypes.byref(info), ctypes.sizeof(info)):
            return False
    h = k32.OpenProcess(0x0100 | 0x0001, False, pid)   # PROCESS_SET_QUOTA | PROCESS_TERMINATE
    if not h:
        return False
    try:
        return bool(k32.AssignProcessToJobObject(_job, h))
    finally:
        k32.CloseHandle(h)
