"""Full Android 16 emulator E2E verification on motonav36 against a REAL hub and REAL desktop-mcp.

Covers:
  a) E2E indicator.json + input_lock.json + RELEASE takeover + resume
  b) Task 31: QR + PIN + TOTP + Calculator (12.5+7)*3 + fixture Submit deny/allow + STOP
  c) Task 33: Deterministic network cut via local TCP proxy (127.0.0.1:8762 <-> 127.0.0.1:8761)
  d) Task 34: Hub restart mid-session (pre-restart replay 401, old nonce 401, persist=false reopen, persist=true kept)

Only launches Calculator and turbo_fixture.exe. Acquires %TEMP%\\turbo-desktop-test.lock.
"""
import base64
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "hub"))
sys.path.insert(0, str(ROOT / "hub" / "scripts"))
import field_run as F  # noqa: E402
import with_lock  # noqa: E402
from turbo_hub import totp  # noqa: E402
from turbo_hub.devclient import DevClient  # noqa: E402
from turbo_hub.runners import find_claude  # noqa: E402
from turbo_hub.store import SecretStore  # noqa: E402

ADB = ["D:/dev/sdk/android/platform-tools/adb.exe", "-s", os.environ.get("EMU", "emulator-5554")]
APK = ROOT / "android/app/build/outputs/apk/debug/app-debug.apk"
PKG = "dev.turbodesktop.remote"
PIN = "1234"
PROXY_PORT = 8762
SHOTS = ROOT / "design" / "emulator"


def adb(*a, check=False):
    r = subprocess.run([*ADB, *a], capture_output=True, text=True, timeout=60)
    out = r.stdout.strip()
    if check and r.returncode != 0:
        raise RuntimeError(f"adb {a} failed ({r.returncode}): {r.stderr.strip() or out}")
    return out


def sh_quote(v: str) -> str:
    return "'" + str(v).replace("'", "'\\''") + "'"


def hook(action, **extra):
    """One adb shell string so spaces, parentheses and * in task text survive the device shell."""
    cmd = f"am start -n {PKG}/.MainActivity --es dbg_action {sh_quote(action)}"
    for k, v in extra.items():
        cmd += f" --es {k} {sh_quote(v)}"
    if action != "state":
        adb("logcat", "-c")
    adb("shell", cmd)


def dbg_log(wait=2.5):
    time.sleep(wait)
    return adb("logcat", "-d", "-s", "TurboDbg:I").splitlines()[-5:]


def conn_log(n=16):
    return adb("logcat", "-d", "-s", "TurboConn:*").splitlines()[-n:]


def enter_pin():
    """BiometricPrompt falls back to the device credential on an emulator without fingerprints."""
    time.sleep(3.5)
    adb("shell", "input", "text", PIN)
    adb("shell", "input", "keyevent", "66")


def dismiss_totp_setup():
    """Waits for the post-pairing 2FA setup screen (after restart), captures it, and taps \"I've added it\"."""
    t0 = time.time()
    pin_sent = False
    while time.time() - t0 < 20:
        xml_txt = adb("shell", "uiautomator dump /sdcard/ui.xml >/dev/null && cat /sdcard/ui.xml")
        if "<hierarchy" in xml_txt:
            try:
                root = ET.fromstring(xml_txt[xml_txt.index("<hierarchy") :])
                texts = [n.attrib.get("text", "") for n in root.iter("node") if n.attrib.get("text")]
                for node in root.iter("node"):
                    txt = node.attrib.get("text", "")
                    if txt in ("I've added it", "Tôi đã thêm"):
                        nums = [int(x) for x in re.findall(r"\d+", node.attrib.get("bounds", ""))]
                        if len(nums) == 4:
                            shot("02b-totp-setup")
                            cx, cy = (nums[0] + nums[2]) // 2, (nums[1] + nums[3]) // 2
                            adb("shell", "input", "tap", str(cx), str(cy))
                            time.sleep(1.5)
                            return
                if not pin_sent and any("PIN" in t or "Confirm" in t or "Xác nhận" in t for t in texts):
                    pin_sent = True
                    adb("shell", "input", "text", PIN)
                    adb("shell", "input", "keyevent", "66")
            except ET.ParseError:
                pass
        elif not pin_sent and time.time() - t0 > 3.5:
            pin_sent = True
            adb("shell", "input", "text", PIN)
            adb("shell", "input", "keyevent", "66")
        time.sleep(1.0)
    raise AssertionError("Timed out waiting for TotpSetupScreen 'I've added it' button")


def shot(name):
    target = SHOTS / f"{name}.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    time.sleep(1.0)
    r = subprocess.run([*ADB, "exec-out", "screencap", "-p"], capture_output=True, timeout=60)
    target.write_bytes(r.stdout)
    F.log("screenshot", name, len(r.stdout))


def restart_app():
    adb("shell", "am", "force-stop", PKG)
    adb("shell", "monkey", "-p", PKG, "-c", "android.intent.category.LAUNCHER", "1")
    time.sleep(10)


def state():
    hook("state")
    lines = dbg_log(1.8)
    for ln in reversed(lines):
        if "state " in ln:
            return ln
    return lines[-1] if lines else ""


def wait_state(pred, timeout=60.0, poll=1.5, desc="condition"):
    t0 = time.time()
    last = ""
    while time.time() - t0 < timeout:
        s = state()
        if s != last:
            F.log("STATE ->", s)
            last = s
        if s and pred(s):
            return s
        time.sleep(poll)
    raise AssertionError(f"Timeout waiting for {desc} after {timeout}s; last state: {last!r}")


class TcpProxy:
    """Lightweight TCP proxy (127.0.0.1:8762 <-> 127.0.0.1:8761) supporting deterministic socket cuts."""

    def __init__(self, listen_port: int = PROXY_PORT, target_host: str = "127.0.0.1", target_port: int = F.PORT):
        self.listen_port = listen_port
        self.target_host = target_host
        self.target_port = target_port
        self._lock = threading.Lock()
        self._active: list[tuple[socket.socket, socket.socket]] = []
        self._srv: socket.socket | None = None
        self._stop = False
        self._accepting = False
        self._thread: threading.Thread | None = None
        self.captured_requests: list[bytes] = []
        self.seen_heads: list[bytes] = []

    def start(self):
        self._stop = False
        self.reopen()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def reopen(self):
        with self._lock:
            if self._srv is None:
                srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                srv.bind(("127.0.0.1", self.listen_port))
                srv.listen(64)
                srv.settimeout(0.25)
                self._srv = srv
            self._accepting = True

    def cut(self):
        with self._lock:
            self._accepting = False
            srv, self._srv = self._srv, None
            pairs = list(self._active)
            self._active.clear()
        if srv:
            try:
                srv.close()
            except OSError:
                pass
        for c, u in pairs:
            for s in (c, u):
                try:
                    s.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                try:
                    s.close()
                except OSError:
                    pass

    def stop(self):
        self._stop = True
        self.cut()
        if self._thread and self._thread.is_alive():
            self._thread.join(2)

    def _loop(self):
        while not self._stop:
            with self._lock:
                srv = self._srv if self._accepting else None
            if srv is None:
                time.sleep(0.1)
                continue
            try:
                cli, _ = srv.accept()
            except socket.timeout:
                continue
            except OSError:
                time.sleep(0.05)
                continue
            try:
                up = socket.create_connection((self.target_host, self.target_port), timeout=5.0)
                up.settimeout(None)
                cli.settimeout(None)
            except OSError:
                cli.close()
                continue
            pair = (cli, up)
            with self._lock:
                if not self._accepting:
                    cli.close()
                    up.close()
                    continue
                self._active.append(pair)
            threading.Thread(target=self._pump, args=(cli, up, pair, True), daemon=True).start()
            threading.Thread(target=self._pump, args=(up, cli, pair, False), daemon=True).start()

    def _pump(self, src: socket.socket, dst: socket.socket, pair: tuple[socket.socket, socket.socket], client_to_hub: bool):
        buf = b""
        skip = 0
        try:
            while True:
                data = src.recv(65536)
                if not data:
                    break
                if client_to_hub:
                    chunk = data
                    if skip > 0:
                        take = min(skip, len(chunk))
                        chunk = chunk[take:]
                        skip -= take
                    if chunk:
                        buf += chunk
                        while True:
                            idx = buf.find(b"\r\n\r\n")
                            if idx == -1:
                                if len(buf) > 32768:
                                    buf = b""
                                break
                            req = buf[: idx + 4]
                            rest = buf[idx + 4 :]
                            clen = 0
                            for ln in req.split(b"\r\n")[1:]:
                                if ln.lower().startswith(b"content-length:"):
                                    try:
                                        clen = int(ln.split(b":", 1)[1].strip())
                                    except ValueError:
                                        clen = 0
                                    break
                            head = req.split(b"\r\n", 1)[0]
                            with self._lock:
                                self.seen_heads.append(head)
                                if (
                                    req.startswith(b"GET /status ")
                                    or req.startswith(b"GET /tasks ")
                                    or req.startswith(b"GET /report")
                                    or req.startswith(b"GET /audit")
                                ) and b"x-sig:" in req.lower():
                                    self.captured_requests.append(req)
                            if len(rest) >= clen:
                                buf = rest[clen:]
                                skip = 0
                            else:
                                buf = b""
                                skip = clen - len(rest)
                                break
                dst.sendall(data)
        except OSError:
            pass
        finally:
            with self._lock:
                if pair in self._active:
                    self._active.remove(pair)
            for s in pair:
                try:
                    s.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                try:
                    s.close()
                except OSError:
                    pass


def replay_raw_http(raw_req: bytes) -> int:
    """Sends captured raw HTTP request bytes straight to the real hub and returns the HTTP status code."""
    lines = raw_req.split(b"\r\n")
    filtered = [lines[0]]
    for ln in lines[1:]:
        if ln.lower().startswith(b"connection:"):
            continue
        if ln == b"":
            continue
        filtered.append(ln)
    filtered.append(b"Connection: close")
    payload = b"\r\n".join(filtered) + b"\r\n\r\n"
    with socket.create_connection(("127.0.0.1", F.PORT), timeout=5.0) as s:
        s.sendall(payload)
        resp = s.recv(4096)
    first_line = resp.split(b"\r\n", 1)[0].decode("ascii", errors="replace")
    parts = first_line.split()
    return int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 0


def write_emu_config(persist: bool = False) -> Path:
    F.WORK.mkdir(parents=True, exist_ok=True)
    mcp = F.WORK / "mcp.json"
    py = ROOT / "desktop-mcp" / ".venv" / "Scripts" / "python.exe"
    mcp.write_text(json.dumps({"mcpServers": {"desktop": {
        "command": str(py), "args": ["-m", "turbo_desktop"],
        "env": {"PYTHONPATH": str(ROOT / "desktop-mcp" / "src")}}}}), "utf-8")
    cfg = F.WORK / "turbo-desktop.toml"
    claude = find_claude().replace("\\", "/")
    cmd = [claude, "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
           "--model", "haiku", "--mcp-config", "{mcp_config}", "--strict-mcp-config", "--tools", "",
           "--permission-prompt-tool", "{approval_tool}", "--append-system-prompt", "{system_prompt}"]
    persist_str = "true" if persist else "false"
    cfg.write_text(
        f'preset = "strict"\n'
        f'[server]\nconnections = ["local"]\n'
        f'[session]\npersist = {persist_str}\n'
        f'[cloudflare]\nrequire_access = false\n'
        f'[agent]\nmcp_config = "{str(mcp).replace(chr(92), "/")}"\ncommand = {json.dumps(cmd)}\n',
        "utf-8",
    )
    return cfg


class EmuHub:
    def __init__(self):
        self.proc = None

    def start(self, persist: bool = False):
        if self.proc is not None:
            self.kill()
        cfg = write_emu_config(persist=persist)
        fixtures_dir = str(ROOT / "desktop-mcp" / "tests" / "fixtures")
        env = {
            **os.environ,
            "PATH": fixtures_dir + os.pathsep + os.environ.get("PATH", ""),
            "TURBO_HUB_DATA": str(F.DATA),
            "TURBO_DESKTOP_CONFIG": str(cfg),
            "TURBO_DESKTOP_CALL_TIMEOUT": "90",
            "PYTHONIOENCODING": "utf-8",
        }
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "turbo_hub", "serve", "--port", str(F.PORT), "--public-url", f"http://10.0.2.2:{PROXY_PORT}"],
            cwd=ROOT / "hub", env=env, stdout=open(F.WORK / "hub.out", "a"), stderr=subprocess.STDOUT,
        )
        for _ in range(60):
            try:
                httpx.get(F.BASE + "/admin/status", timeout=1)
                return
            except httpx.HTTPError:
                time.sleep(0.25)
        raise RuntimeError("hub did not start")

    def kill(self):
        if self.proc is not None:
            self.proc.kill()
            self.proc.wait()
            self.proc = None


def fresh_totp_code() -> str:
    while True:
        st = SecretStore(F.DATA)
        cur = int(time.time() // 30)
        target = max(cur, st.totp_last_step + 1)
        if target <= cur + 1:
            return totp.code_at(st.totp_secret, target)
        time.sleep(1.0)


def admin_status(store: SecretStore) -> dict:
    return httpx.get(F.BASE + "/admin/status", headers={"X-Admin-Token": store.admin_token}, timeout=5).json()


def wait_hub_task_idle(store: SecretStore, timeout: float = 120.0) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = admin_status(store)
        if not st.get("running"):
            return st
        time.sleep(1.0)
    raise AssertionError("hub task still running after timeout")


def read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None


def main():
    with_lock.acquire(poll=2.0, log=F.log)
    before = F.top_windows()
    shutil.rmtree(F.DATA, ignore_errors=True)
    hub = EmuHub()
    proxy = TcpProxy()
    try:
        proxy.start()
        hub.start(persist=False)
        store = SecretStore(F.DATA)
        state_dir = F.DATA / "desktop-state"

        F.log("wait-for-device:", adb("wait-for-device", check=True))
        F.log("install apk:", adb("install", "-r", str(APK), check=True))
        F.log("set pin:", adb("shell", "locksettings", "set-pin", PIN))
        adb("shell", "pm", "clear", PKG)
        adb("shell", "pm", "grant", PKG, "android.permission.POST_NOTIFICATIONS")
        adb("shell", "pm", "grant", PKG, "android.permission.CAMERA")
        adb("shell", "cmd", "locale", "set-app-locales", PKG, "--locales", "en-US")
        adb("shell", "input", "keyevent", "224")
        time.sleep(0.8)
        adb("shell", "input", "swipe", "540", "1800", "540", "400")
        time.sleep(0.8)
        adb("shell", "input", "text", PIN)
        adb("shell", "input", "keyevent", "66")
        time.sleep(1.5)

        # ---- Task 31: Pair QR + PIN + TOTP
        info = httpx.post(F.BASE + "/admin/pairing", headers={"X-Admin-Token": store.admin_token}).json()
        info.pop("otpauth", None)
        info.pop("needs", None)
        info["url"] = f"http://10.0.2.2:{PROXY_PORT}"
        info["urls"] = [{"name": "local", "url": f"http://10.0.2.2:{PROXY_PORT}"}]
        pair_text = "turbo-pair:" + base64.urlsafe_b64encode(json.dumps(info, separators=(",", ":")).encode()).decode()

        restart_app()
        shot("01-welcome")
        hook("onboard")
        time.sleep(2.0)
        restart_app()
        shot("02-pairing")
        hook("pair", text=pair_text)
        enter_pin()
        for _ in range(15):
            lines = dbg_log(2)
            if any("pair=true" in ln for ln in lines):
                break
        else:
            raise AssertionError(f"pairing failed: {lines}")
        F.log("PAIR ->", lines)

        # Pair a companion DevClient for raw pre-restart / nonce verification in Task 34
        info_dc = httpx.post(F.BASE + "/admin/pairing", headers={"X-Admin-Token": store.admin_token}).json()
        dc = DevClient(httpx.Client(base_url=F.BASE, timeout=20), hub_pub=info_dc["hubKey"])
        assert dc.pair(info_dc["code"]).status_code == 200
        assert dc.start_session(code=fresh_totp_code()).status_code == 200

        restart_app()
        dismiss_totp_setup()
        shot("03-open-session")
        hook("session", totp=fresh_totp_code())
        enter_pin()
        s = wait_state(lambda x: "session=true" in x and "online=true" in x, timeout=30, desc="open session online")
        shot("04-tasks")
        F.log("SESSION OPEN ->", s)

        fixture = "turbo_fixture.exe"

        # ---- Scenario (a): E2E indicator.json + input_lock.json + RELEASE takeover
        F.log("=== Scenario (a): E2E indicator.json + input_lock.json + RELEASE takeover ===")
        hook("task", text=f"Launch {fixture}. Click the 'Count 0' button 5 times one click per call (do not batch), reading its label after each click. Use only the desktop tools.")
        t0 = time.time()
        seen_lock = seen_ind = seen_phone = False
        while time.time() - t0 < 75:
            lock_j = read_json(state_dir / "input_lock.json")
            ind_j = read_json(state_dir / "indicator.json")
            ps = state()
            if lock_j and lock_j.get("locked") is True:
                seen_lock = True
            if ind_j and ind_j.get("state") == "input_locked":
                seen_ind = True
            if "locked=true" in ps and ("indicator=input_locked" in ps or "indicator=acting" in ps):
                seen_phone = True
            if seen_lock and seen_ind and seen_phone:
                F.log("LOCKED OBSERVED:", "input_lock.json=", lock_j, "indicator.json=", ind_j, "phone=", ps)
                break
            time.sleep(1.0)
        assert seen_lock and seen_ind and seen_phone, f"Failed to observe full lock state: lock={seen_lock} ind={seen_ind} phone={seen_phone}"
        shot("10-live-input-locked")

        hook("takeover")
        t0 = time.time()
        released_ok = False
        while time.time() - t0 < 20:
            rel_exists = (state_dir / "RELEASE").exists()
            lock_j = read_json(state_dir / "input_lock.json")
            ind_j = read_json(state_dir / "indicator.json")
            ps = state()
            if (
                not rel_exists
                and lock_j is not None
                and lock_j.get("locked") is False
                and ind_j is not None
                and ind_j.get("state") == "idle"
                and "paused=true" in ps
                and "locked=false" in ps
            ):
                F.log("RELEASED OBSERVED:", "input_lock.json=", lock_j, "indicator.json=", ind_j, "phone=", ps)
                released_ok = True
                break
            time.sleep(0.8)
        assert released_ok, f"RELEASE takeover did not clear cleanly: release_exists={(state_dir / 'RELEASE').exists()} lock={read_json(state_dir / 'input_lock.json')} ind={read_json(state_dir / 'indicator.json')} phone={state()}"

        hook("resume")
        wait_state(lambda x: "paused=false" in x, timeout=20, desc="resume after takeover")
        wait_hub_task_idle(store, timeout=90)
        wait_state(lambda x: "taskRunning=false" in x, timeout=20, desc="task finished after resume")
        subprocess.run(["taskkill", "/IM", "turbo_fixture.exe", "/F"], capture_output=True)
        F.log("Scenario (a) PASS")

        # ---- Scenario (b): Task 31 (Fixture multi-step + Fixture Submit deny/allow + STOP)
        F.log("=== Scenario (b): Task 31 Fixture multi-step ===")
        hook("task", text=f"Launch {fixture}. Set 'Full name' to 'Linh', click the 'Count 0' button twice, then read 'Count 2' and 'Full name' and tell me both values. Use only the desktop tools.")
        hook("tab", name="LIVE")
        time.sleep(4)
        shot("05-live-acting")
        wait_hub_task_idle(store, timeout=120)
        s = wait_state(lambda x: "taskRunning=false" in x and "topTask=done" in x, timeout=25, desc="fixture multi-step task done")
        hist = dc.request("GET", "/tasks").json()
        F.log("MULTI-STEP FIXTURE ->", hist[0] if hist else None, "| phone=", s)
        assert hist and ("Count 2" in (hist[0].get("answer") or "") or "Linh" in (hist[0].get("answer") or "")), f"Unexpected answer: {hist[:1]}"

        F.log("=== Scenario (b): Task 31 Fixture Submit deny then allow ===")
        hook("task", text=f"Use the open turbo_fixture window (or launch {fixture}). Type Ada in the Full name field, then click the Submit button and tell me what the result label says. Use only the desktop tools.")
        wait_state(lambda x: "pending=1" in x, timeout=90, poll=1.5, desc="fixture Submit approval (deny)")
        hook("tab", name="APPROVALS")
        shot("06-approval")
        hook("decide", decision="deny")
        enter_pin()
        F.log("DECIDE deny ->", dbg_log(3))
        wait_hub_task_idle(store, timeout=60)
        wait_state(lambda x: "taskRunning=false" in x, timeout=20, desc="fixture deny task finish")

        hook("task", text=f"The owner changed their mind and will approve Submit now. In the open turbo_fixture window (or launch {fixture} if closed), ensure Ada is in the Full name field, click the Submit button and tell me exactly what the result label says. Use only the desktop tools.")
        wait_state(lambda x: "pending=1" in x, timeout=90, poll=1.5, desc="fixture Submit approval (allow)")
        hook("decide", decision="allow")
        enter_pin()
        F.log("DECIDE allow ->", dbg_log(3))
        wait_hub_task_idle(store, timeout=60)
        wait_state(lambda x: "taskRunning=false" in x, timeout=20, desc="fixture allow task finish")
        hist_allow = dc.request("GET", "/tasks").json()
        F.log("FIXTURE ALLOW ->", hist_allow[0] if hist_allow else None)
        assert hist_allow and "Ada" in (hist_allow[0].get("answer") or ""), f"Expected Ada submission in answer, got {hist_allow[:1]}"

        F.log("=== Scenario (b): Task 31 STOP + Resume ===")
        hook("tab", name="TASKS")
        hook("task", text=f"Use the open turbo_fixture window (or launch {fixture}). Click the Count button 10 times one click per call (do not batch), reading the label after each click. Use only the desktop tools.")
        wait_state(lambda x: "taskRunning=true" in x, timeout=30, poll=1.0, desc="long fixture task running for STOP")
        time.sleep(3)
        hook("stop")
        s = wait_state(lambda x: "stopped=true" in x and "taskRunning=false" in x, timeout=20, poll=1.0, desc="stopped state")
        ast = admin_status(store)
        assert ast["stopped"] is True and ast["running"] is False, f"Hub not stopped: {ast}"
        shot("09-stop-state")
        hook("resume")
        wait_state(lambda x: "stopped=false" in x, timeout=15, poll=1.0, desc="resumed state")
        subprocess.run(["taskkill", "/IM", "turbo_fixture.exe", "/F"], capture_output=True)
        F.log("Scenario (b) PASS")

        # ---- Scenario (c): Task 33 (Deterministic Network Cut via TCP Proxy)
        F.log("=== Scenario (c): Task 33 Deterministic Network Cut via TCP Proxy ===")
        hook("task", text=f"Launch {fixture}. Click the 'Count 0' button 4 times one click per call (do not batch), then tell me the final Count button text. Use only the desktop tools.")
        wait_state(lambda x: "taskRunning=true" in x and "online=true" in x, timeout=30, poll=1.0, desc="task running before net cut")
        time.sleep(2.0)

        t_cut = time.time()
        proxy.cut()
        F.log("PROXY CUT at t=%.1f" % t_cut)
        saw_offline = False
        saw_fake_finish = False
        hub_done_while_offline = False
        while True:
            elapsed = time.time() - t_cut
            ps = state()
            st_hub = admin_status(store)
            if not st_hub["running"]:
                hub_done_while_offline = True
            if "online=false" in ps:
                saw_offline = True
            if "taskRunning=false" in ps or "last=Finished" in ps or "last=Kết thúc" in ps:
                saw_fake_finish = True
            F.log("OFFLINE_POLL t=+%.1fs hub_running=%s phone=%s" % (elapsed, st_hub["running"], ps))
            if elapsed >= 15.5 and hub_done_while_offline:
                break
            if elapsed > 75.0:
                raise AssertionError("Hub did not finish Calculator task during 75s proxy cut")
            time.sleep(2.5)
        assert saw_offline, "APK never set online=false during proxy cut!"
        assert not saw_fake_finish, "APK emitted fake completion while offline!"
        shot("11-task33-offline")

        proxy.reopen()
        t_reopen = time.time()
        F.log("PROXY REOPENED at +%.1fs" % (t_reopen - t_cut))
        s = wait_state(lambda x: "online=true" in x and "taskRunning=false" in x and "topTask=done" in x,
                       timeout=45, poll=1.5, desc="reconnect and task reconciliation")
        hist_c = dc.request("GET", "/tasks").json()
        F.log("RECONCILED in %.1fs -> %s | task=%s" % (time.time() - t_reopen, s, hist_c[0] if hist_c else None))
        assert hist_c and hist_c[0].get("status") == "done", f"Expected reconciled task done, got {hist_c[:1]}"
        F.log("conn log ->", " | ".join(conn_log()))
        shot("11b-task33-reconnected")
        subprocess.run(["taskkill", "/IM", "turbo_fixture.exe", "/F"], capture_output=True)
        F.log("Scenario (c) PASS")

        # ---- Scenario (d): Task 34 (Hub Restart Mid-Session)
        def capture_apk_signed(label: str) -> bytes:
            with proxy._lock:
                proxy.captured_requests.clear()
                proxy.seen_heads.clear()
            hook("tab", name="REPORT")
            t0 = time.time()
            tried_audit = False
            tried_resume = False
            while time.time() - t0 < 15:
                with proxy._lock:
                    if proxy.captured_requests:
                        return proxy.captured_requests[-1]
                el = time.time() - t0
                if el > 3.5 and not tried_audit:
                    tried_audit = True
                    hook("tab", name="AUDIT")
                elif el > 7.5 and not tried_resume:
                    tried_resume = True
                    hook("resume")
                time.sleep(0.4)
            with proxy._lock:
                heads = list(proxy.seen_heads)
            raise AssertionError(f"Did not capture an APK signed request ({label}); seen_heads={heads!r}")

        F.log("=== Scenario (d): Task 34 Hub Restart Mid-Session ===")
        apk_raw_req = capture_apk_signed("persist=false")
        hook("tab", name="TASKS")

        dc_pre_unused = dc._headers("GET", "/status", b"")
        dc_used_once = dc._headers("GET", "/status", b"")
        assert httpx.get(F.BASE + "/status", headers=dc_used_once).status_code == 200
        assert httpx.get(F.BASE + "/status", headers=dc_used_once).status_code == 401

        # (d1) Restart with persist=false
        hub.kill()
        hub.start(persist=False)
        code_apk = replay_raw_http(apk_raw_req)
        code_dc_pre = httpx.get(F.BASE + "/status", headers=dc_pre_unused).status_code
        F.log("RESTART persist=false replays -> apk=%d dc_pre=%d" % (code_apk, code_dc_pre))
        assert code_apk == 401 and code_dc_pre == 401

        # Wait for APK to observe 401 and return to OpenSession, then reopen with PIN + TOTP
        s = wait_state(lambda x: "session=false" in x, timeout=35, poll=1.5, desc="APK returned to OpenSession on 401")
        shot("12-task34-opensession")
        hook("session", totp=fresh_totp_code())
        enter_pin()
        s = wait_state(lambda x: "session=true" in x and "online=true" in x, timeout=30, poll=1.5, desc="APK session reopened")
        F.log("REOPENED persist=false ->", s)
        code_dc_sess = dc.request("GET", "/status").status_code
        F.log("persist=false old DevClient session ->", code_dc_sess)
        assert code_dc_sess == 401

        # (d2) Restart with persist=true
        hub.kill()
        hub.start(persist=True)
        # Establish persistent sessions for both APK and DevClient
        wait_state(lambda x: "session=false" in x, timeout=35, poll=1.5, desc="APK opens fresh session on persist=true hub")
        hook("session", totp=fresh_totp_code())
        enter_pin()
        wait_state(lambda x: "session=true" in x and "online=true" in x, timeout=30, poll=1.5, desc="APK online on persist=true hub")
        assert dc.start_session(code=fresh_totp_code()).status_code == 200

        apk_raw_p = capture_apk_signed("persist=true")
        dc_pre_p = dc._headers("GET", "/status", b"")
        dc_nonce_p = dc._headers("GET", "/status", b"")
        assert httpx.get(F.BASE + "/status", headers=dc_nonce_p).status_code == 200

        hub.kill()
        hub.start(persist=True)
        c1 = replay_raw_http(apk_raw_p)
        c2 = httpx.get(F.BASE + "/status", headers=dc_pre_p).status_code
        c3 = httpx.get(F.BASE + "/status", headers=dc_nonce_p).status_code
        c4 = dc.request("GET", "/status").status_code
        F.log("RESTART persist=true -> apk_replay=%d dc_pre=%d dc_old_nonce=%d dc_fresh=%d" % (c1, c2, c3, c4))
        assert c1 == 401 and c2 == 401 and c3 == 401 and c4 == 200

        hook("tab", name="TASKS")
        time.sleep(4)
        s = wait_state(lambda x: "session=true" in x and "online=true" in x, timeout=35, poll=1.5, desc="APK keeps session across persist=true restart")
        F.log("APK KEPT SESSION persist=true ->", s)
        hook("task", text=f"Launch {fixture}. Click the 'Count 0' button once, then tell me its updated label. Use only the desktop tools.")
        wait_hub_task_idle(store, timeout=90)
        wait_state(lambda x: "taskRunning=false" in x and "topTask=done" in x, timeout=20, desc="task works after persist=true restart")
        subprocess.run(["taskkill", "/IM", "turbo_fixture.exe", "/F"], capture_output=True)
        F.log("Scenario (d) PASS")

        # UI sanity screenshots (English & Vietnamese)
        hook("tab", name="SETTINGS"); time.sleep(1.5); shot("07-settings")
        hook("tab", name="AUDIT"); time.sleep(1.5); shot("08-audit")
        F.log("ALL SCENARIOS PASSED")
    finally:
        proxy.stop()
        hub.kill()
        F.close_new_windows(before)
        with_lock.release()


if __name__ == "__main__":
    main()
