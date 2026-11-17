import json
import os

import locking


def test_lock_exclusive_and_stale_takeover(monkeypatch, tmp_path):
    monkeypatch.setattr(locking, "LOCK", str(tmp_path / "x.lock"))
    locking.acquire("a", poll=0, owner_pid=os.getpid())
    with open(locking.LOCK) as f:
        info = json.load(f)
    assert info["agent"] == "a" and info["pid"] == os.getpid()
    locking.release()
    assert not os.path.exists(locking.LOCK)
    # stale lock (dead pid) is taken over
    with open(locking.LOCK, "w") as f:
        json.dump({"agent": "dead", "pid": 999999, "started": "x"}, f)
    locking.acquire("b", poll=0)
    with open(locking.LOCK) as f:
        assert json.load(f)["agent"] == "b"
    locking.release()


def test_win32_ctypes_signatures_declared():
    from ctypes import wintypes
    from turbo_desktop import winsys

    assert winsys.u32.OpenInputDesktop.restype == wintypes.HANDLE
    assert winsys.u32.OpenInputDesktop.argtypes == [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    assert winsys.u32.CloseDesktop.restype == wintypes.BOOL
    assert winsys.u32.CloseDesktop.argtypes == [wintypes.HANDLE]
    assert winsys.k32.OpenProcess.restype == wintypes.HANDLE
    assert winsys.k32.CloseHandle.argtypes == [wintypes.HANDLE]
    assert locking.k32.OpenProcess.restype == wintypes.HANDLE
    assert locking.k32.GetExitCodeProcess.argtypes[0] == wintypes.HANDLE
    assert locking.k32.CloseHandle.argtypes == [wintypes.HANDLE]
