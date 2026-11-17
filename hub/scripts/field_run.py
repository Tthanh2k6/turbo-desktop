"""Field run for hub + phone protocol with the REAL hub and the REAL agent command (claude headless + desktop-mcp).
Uses the simulated phone (DevClient) over real HTTP. Spends the owner's Claude quota (cheap model, trivial tasks).

    hub\\.venv\\Scripts\\python hub\\scripts\\field_run.py [calc|deny|stop|restart|all]
Work files live in %TEMP%\\turbo-field\\ ; the owner's real hub data is never touched.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
HUB = ROOT / "hub"
sys.path.insert(0, str(HUB))
from turbo_hub import totp  # noqa: E402
from turbo_hub.devclient import DevClient  # noqa: E402
from turbo_hub.runners import find_claude  # noqa: E402
from turbo_hub.store import SecretStore  # noqa: E402

WORK = Path(os.environ["TEMP"]) / "turbo-field"
DATA = WORK / "hubdata"
PORT = 8761
BASE = f"http://127.0.0.1:{PORT}"
LOG = WORK / "field_run.log"


# ---- clean up: record top-level windows before, close what the run opened (also on failure)
import ctypes  # noqa: E402
from ctypes import wintypes  # noqa: E402

KILLABLE = {"calculatorapp.exe", "turbo_fixture.exe", "turbo_editor.exe", "turbo_canvas.exe"}


def top_windows() -> dict:
    u = ctypes.windll.user32
    out = {}

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        if u.IsWindowVisible(hwnd):
            n = u.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                u.GetWindowTextW(hwnd, buf, n + 1)
                pid = wintypes.DWORD()
                u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                out[hwnd] = (buf.value, pid.value)
        return True

    u.EnumWindows(cb, 0)
    return out


def close_new_windows(before: dict) -> None:
    from turbo_hub import reaper
    now = top_windows()
    new = {h: v for h, v in now.items() if h not in before}
    for h, (title, pid) in new.items():
        log("cleanup: closing", hex(h), repr(title), "pid", pid)
        ctypes.windll.user32.PostMessageW(h, 0x0010, 0, 0)   # WM_CLOSE
    time.sleep(1.5)
    still = top_windows()
    for h, (title, pid) in new.items():
        if h in still and (reaper.image_of(pid) or "").lower() in KILLABLE:
            log("cleanup: still open, killing", reaper.image_of(pid), pid)
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)


def log(*a):
    line = time.strftime("%H:%M:%S ") + " ".join(str(x) for x in a)
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def write_config() -> Path:
    WORK.mkdir(parents=True, exist_ok=True)
    mcp = WORK / "mcp.json"
    py = ROOT / "desktop-mcp" / ".venv" / "Scripts" / "python.exe"
    mcp.write_text(json.dumps({"mcpServers": {"desktop": {
        "command": str(py), "args": ["-m", "turbo_desktop"],
        "env": {"PYTHONPATH": str(ROOT / "desktop-mcp" / "src")}}}}), "utf-8")
    cfg = WORK / "turbo-desktop.toml"
    claude = find_claude().replace("\\", "/")
    cmd = [claude, "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
           "--model", "haiku", "--mcp-config", "{mcp_config}", "--strict-mcp-config", "--tools", "",
           "--permission-prompt-tool", "{approval_tool}"]
    cfg.write_text(f'preset = "balanced"\n[server]\nconnections = ["local"]\n[agent]\n'
                   f'mcp_config = "{str(mcp).replace(chr(92), "/")}"\ncommand = {json.dumps(cmd)}\n', "utf-8")
    return cfg


class Hub:
    def __init__(self):
        self.proc = None

    def start(self):
        env = {**os.environ, "TURBO_HUB_DATA": str(DATA), "TURBO_DESKTOP_CONFIG": str(write_config())}
        self.proc = subprocess.Popen([sys.executable, "-m", "turbo_hub", "serve", "--port", str(PORT)], cwd=HUB, env=env,
                                     stdout=open(WORK / "hub.out", "a"), stderr=subprocess.STDOUT)
        for _ in range(60):
            try:
                httpx.get(BASE + "/admin/status", timeout=1)
                return
            except httpx.HTTPError:
                time.sleep(0.25)
        raise RuntimeError("hub did not start")

    def kill(self):
        self.proc.kill()
        self.proc.wait()


def phone(first: bool, existing: DevClient | None = None) -> DevClient:
    store = SecretStore(DATA)
    http = httpx.Client(base_url=BASE, timeout=30)
    if existing:
        existing.http = http
        return existing
    info = httpx.post(BASE + "/admin/pairing", headers={"X-Admin-Token": store.admin_token}).json()
    d = DevClient(http, hub_pub=info["hubKey"])
    assert d.pair(info["code"]).status_code == 200
    return d


def open_session(d: DevClient):
    secret = SecretStore(DATA).totp_secret
    for off in (0, 1, 2):     # a code from the current step may have been used already
        r = d.start_session(secret, step_offset=off - 0)
        if r.status_code == 200:
            return r
        time.sleep(0.2)
    raise RuntimeError("cannot open session")


def last_seq(d: DevClient) -> int:
    evs = d.request("GET", "/events/poll?since=0").json()
    return evs[-1]["seq"] if evs else 0


def watch(d: DevClient, task_id=None, timeout=240, on_event=None, since=None):
    """Poll events until task_finished. Returns (events, last_seq). Starts after the events that already exist."""
    since = last_seq(d) if since is None else since
    seen, end = [], time.time() + timeout
    while time.time() < end:
        r = d.request("GET", f"/events/poll?since={since}")
        if r.status_code != 200:
            log("poll status", r.status_code, r.text[:100])
            time.sleep(1)
            continue
        for e in r.json():
            since = e["seq"]
            seen.append(e)
            log("EV", e["type"], (e.get("text") or e.get("tool") or e.get("summary") or e.get("decision") or "")[:110],
                e.get("control") or "")
            if on_event:
                on_event(e)
            if e["type"] == "task_finished":
                return seen, since
        time.sleep(0.4)
    log("TIMEOUT waiting for task_finished")
    return seen, since


def scenario_calc(d: DevClient):
    log("=== calc: (12.5 + 7) * 3 in Calculator")
    t0 = time.time()
    mark = last_seq(d)
    r = d.request("POST", "/tasks", {"text": "Open the Windows Calculator app and compute (12.5 + 7) * 3 using its buttons. "
                                             "Tell me the number shown in the result display. Use only the desktop tools."})
    log("POST /tasks", r.status_code, r.text[:200])
    evs, _ = watch(d, since=mark)
    fin = next((e for e in evs if e["type"] == "final"), {})
    done = next((e for e in evs if e["type"] == "task_finished"), {})
    log("RESULT calc: seconds=%.1f tool_calls=%d final=%r usage=%s" % (
        time.time() - t0, sum(e["type"] == "tool_call" for e in evs), fin.get("text", "")[:120], done.get("usage")))
    return evs


def scenario_deny(d: DevClient):
    """Fixture app with a Submit button (asks under Balanced). First Deny, then Allow."""
    fixture = ROOT / "desktop-mcp" / "tests" / "fixtures" / "turbo_fixture.exe"
    for decision in ("deny", "allow"):
        log(f"=== approval round trip: owner answers {decision.upper()} on the fixture's Submit button")
        answered = []

        def on_event(e, decision=decision):
            if e["type"] == "approval_request":
                t = time.time()
                r = d.request("POST", f"/approvals/{e['approval_id']}", {"decision": decision}, strong=True)
                answered.append(time.time() - t)
                log("ANSWER", decision, r.status_code, "%.2fs" % answered[-1], "control=", e.get("control"),
                    "window=", e.get("window"), "has_crop=", bool(e.get("crop_png_b64")))

        mark = last_seq(d)
        extra = "" if decision == "deny" else "The owner has changed their mind and will approve this time, so do click Submit again. "
        d.request("POST", "/tasks", {"text": f"{extra}Launch {fixture}. In its window type Ada in the Full name field, then click "
                                             "the Submit button and tell me exactly what the result label says afterwards "
                                             "(it may be empty). Use only the desktop tools."})
        evs, _ = watch(d, on_event=on_event, since=mark)
        fin = next((e for e in evs if e["type"] == "final"), {})
        log("RESULT %s: approvals=%d final=%r" % (decision, len(answered), fin.get("text", "")[:200]))
        subprocess.run(["taskkill", "/IM", "turbo_fixture.exe", "/F"], capture_output=True)


def scenario_stop(d: DevClient):
    log("=== stop: press STOP while the agent works")
    d.request("POST", "/tasks", {"text": "Open Calculator and press the digit buttons 1 to 9 one at a time, reading the display after each press, and repeat the whole sequence five times. "
                                         "Use only the desktop tools."})
    t0, since = time.time(), 0
    while time.time() - t0 < 12:
        for e in d.request("GET", f"/events/poll?since={since}").json():
            since = e["seq"]
            log("EV", e["type"], (e.get("tool") or e.get("text") or "")[:80])
        time.sleep(0.5)
    store = SecretStore(DATA)
    pid = httpx.get(BASE + "/admin/status", headers={"X-Admin-Token": store.admin_token}).json().get("agent_pid")
    r = d.request("POST", "/stop", {})
    log("STOP", r.status_code, "agent pid was", pid)
    evs, _ = watch(d, timeout=20, since=since)
    n_after = sum(e["type"] == "tool_call" for e in evs if e["type"] != "task_finished")
    time.sleep(1)
    alive = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True).stdout
    log("RESULT stop: tool_calls_after_stop=%d agent_pid_still_running=%s" % (n_after, str(pid) in alive))
    r = d.request("POST", "/tasks", {"text": "hello"})
    log("new task while stopped ->", r.status_code)
    d.request("POST", "/resume", {})
    log("audit:", [e["kind"] for e in d.request("GET", "/audit?limit=10").json()["entries"]])


def scenario_restart(hub: Hub, d: DevClient):
    log("=== restart: kill the hub mid-session")
    old = d._headers("GET", "/status", b"")
    hub.kill()
    time.sleep(1)
    try:
        d.request("GET", "/status")
    except httpx.HTTPError as e:
        log("while hub is down the client sees:", type(e).__name__)
    hub.start()
    d = phone(False, d)
    r = httpx.get(BASE + "/status", headers=old)
    log("replay of a pre-restart signed request ->", r.status_code)
    r = d.request("GET", "/status")
    log("old session after restart ->", r.status_code, "(401 = must reopen, as configured: persist=false)")
    open_session(d)
    log("session reopened ->", d.request("GET", "/status").status_code)
    return d


def scenario_orphan(hub: Hub, d: DevClient):
    log("=== orphan: hard-kill the hub while the agent is mid-task")
    d.request("POST", "/tasks", {"text": "Open Calculator and press the digit buttons 1 to 9 one at a time, reading the display "
                                         "after each press. Use only the desktop tools."})
    time.sleep(10)
    store = SecretStore(DATA)
    pid = httpx.get(BASE + "/admin/status", headers={"X-Admin-Token": store.admin_token}).json().get("agent_pid")
    hub.kill()
    time.sleep(1.5)
    alive = lambda: str(pid) in subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True).stdout  # noqa: E731
    log("agent pid", pid, "alive after hub was killed:", alive())
    hub.start()
    time.sleep(2)
    log("agent alive after hub restart (should be reaped):", alive())


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    sys.path.insert(0, str(HUB / "scripts"))
    import with_lock
    with_lock.acquire(log=log)          # never overlap with the desktop-mcp agent's suites
    before = top_windows()
    hub = Hub()
    hub.start()
    try:
        d = phone(True)
        open_session(d)
        if which in ("calc", "all"):
            scenario_calc(d)
        if which in ("deny", "all"):
            scenario_deny(d)
        if which in ("stop", "all"):
            scenario_stop(d)
        if which == "orphan":
            scenario_orphan(hub, d)
        if which in ("restart", "all"):
            scenario_restart(hub, d)
    finally:
        hub.kill()
        close_new_windows(before)
        with_lock.release()
