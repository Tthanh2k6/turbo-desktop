"""Field bugs 8 and 10: a menu item that opens a modal dialog, and a UIA call that blocks forever.
(The root cause of the 'dialog never appears' report was the fixture, which lacked [STAThread]; the blocking is real.)"""
import json
import time

import pytest

from turbo_desktop import server
from turbo_desktop.engine import ToolError


def wait_until(fn, secs=6.0):
    end = time.time() + secs
    while time.time() < end:
        r = fn()
        if r:
            return r
        time.sleep(0.2)
    return fn()


def test_invoke_that_opens_a_modal_dialog_does_not_hang(launch_app, desktop):
    d = launch_app("turbo_editor.exe")
    w = d["id"]
    desktop.act(w, "click", name="File")
    time.sleep(0.4)
    t0 = time.time()
    r = desktop.act(w, "click", name="Save As...")
    assert r["ok"] and r.get("pending") is True and time.time() - t0 < 6
    # the dialog is a separate window and is listed
    dlg = wait_until(lambda: [x for x in desktop.windows_list() if x["pid"] == d["pid"] and x["title"] == "Save As"])
    assert dlg, "Save As dialog not listed"
    # UIA into the blocked app answers at once with the reason instead of hanging
    t0 = time.time()
    with pytest.raises(ToolError) as e:
        desktop.inspect(w)
    assert e.value.extra.get("blocked") and time.time() - t0 < 2
    # window_control close uses a window message (not UIA) and closes the dialog
    desktop.window_control(dlg[0]["id"], "close")
    assert wait_until(lambda: not [x for x in desktop.windows_list() if x["title"] == "Save As" and x["pid"] == d["pid"]])
    assert wait_until(lambda: "Text editor" in _try_inspect(desktop, w))


def _try_inspect(desktop, w):
    try:
        return desktop.inspect(w)
    except ToolError:
        return ""


def test_server_call_timeout_abandons_the_stuck_worker(monkeypatch):
    monkeypatch.setenv("TURBO_DESKTOP_CALL_TIMEOUT", "1")
    t0 = time.time()
    out = json.loads(server._guard(lambda: time.sleep(4)))
    assert out["ok"] is False and out["hung"] is True and time.time() - t0 < 3
    # a fresh worker serves the next call immediately
    assert server._guard(lambda: "fine") == "fine"
