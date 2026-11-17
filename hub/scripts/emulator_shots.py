"""Emulator screenshots of every screen with a FAKE agent: no real desktop is touched, so no test lock is needed.
Real hub process, real phone protocol, biometric prompt answered with the emulator PIN; only the agent is scripted
(FakeRunner demo script). English set goes to design/emulator/, Vietnamese to design/emulator/vi/.
    hub\\.venv\\Scripts\\python hub\\scripts\\emulator_shots.py
"""
import base64
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "hub"))
sys.path.insert(0, str(ROOT / "hub" / "scripts"))
import emulator_run as E  # noqa: E402
import field_run as F  # noqa: E402
from turbo_hub import totp  # noqa: E402
from turbo_hub.store import SecretStore  # noqa: E402

PORT = 8762
BASE = f"http://127.0.0.1:{PORT}"
DATA = F.WORK / "shotsdata"


def main():
    F.WORK.mkdir(parents=True, exist_ok=True)
    cfg = F.WORK / "turbo-desktop-shots.toml"
    cfg.write_text('preset = "strict"\n[server]\nconnections = ["local"]\n[cloudflare]\nrequire_access = false\n[approval]\nengine = "hub"\n', "utf-8")
    env = {**os.environ, "TURBO_HUB_DATA": str(DATA), "TURBO_DESKTOP_CONFIG": str(cfg)}
    hub = subprocess.Popen([sys.executable, "-m", "turbo_hub", "serve", "--port", str(PORT), "--runner", "fake"], cwd=ROOT / "hub",
                           env=env, stdout=open(F.WORK / "hub_shots.out", "a"), stderr=subprocess.STDOUT)
    try:
        for _ in range(60):
            try:
                httpx.get(BASE + "/admin/status", timeout=1)
                break
            except httpx.HTTPError:
                time.sleep(0.25)
        store = SecretStore(DATA)
        E.F.log("install:", E.adb("install", "-r", str(E.APK)))
        E.adb("shell", "pm", "clear", E.PKG)
        E.adb("shell", "pm", "grant", E.PKG, "android.permission.POST_NOTIFICATIONS")
        E.adb("shell", "pm", "grant", E.PKG, "android.permission.CAMERA")
        E.adb("shell", "cmd", "locale", "set-app-locales", E.PKG, "--locales", "en-US")
        E.adb("shell", "input", "keyevent", "224"); time.sleep(1)
        E.adb("shell", "input", "swipe", "540", "1800", "540", "400"); time.sleep(1)
        E.adb("shell", "input", "text", E.PIN); E.adb("shell", "input", "keyevent", "66"); time.sleep(2)

        E.restart_app(); E.shot("01-welcome")
        E.hook("onboard"); E.restart_app(); E.shot("02-pairing")
        info = httpx.post(BASE + "/admin/pairing", headers={"X-Admin-Token": store.admin_token}).json()
        info.pop("otpauth", None); info.pop("needs", None)
        info["url"] = f"http://10.0.2.2:{PORT}"
        info["urls"] = [{"name": "local", "url": f"http://10.0.2.2:{PORT}"}]
        text = "turbo-pair:" + base64.urlsafe_b64encode(json.dumps(info, separators=(",", ":")).encode()).decode()
        E.hook("pair", text=text); E.enter_pin()
        for _ in range(15):
            if any("pair=" in l for l in E.dbg_log(2)):
                break
        E.restart_app(); E.shot("03-open-session")
        E.hook("session", totp=totp.code_at(store.totp_secret, int(time.time() // 30))); E.enter_pin()
        time.sleep(4); E.shot("04-tasks")

        E.hook("task", text="demo: open Calculator and compute (12.5 + 7) * 3")
        E.hook("tab", name="LIVE")
        time.sleep(3); E.shot("05-live-acting")
        (DATA / "desktop-state").mkdir(parents=True, exist_ok=True)
        (DATA / "desktop-state" / "input_lock.json").write_text(json.dumps({"locked": True, "mode": "real_input", "since": time.time()}))
        time.sleep(2); E.shot("10-live-input-locked")
        (DATA / "desktop-state" / "input_lock.json").write_text(json.dumps({"locked": False}))
        for _ in range(30):
            if "pending=1" in E.state():
                break
            time.sleep(1)
        E.hook("tab", name="APPROVALS"); time.sleep(2); E.shot("06-approval")
        E.hook("decide", decision="deny"); E.enter_pin(); time.sleep(5)
        E.hook("tab", name="LIVE"); time.sleep(2); E.shot("05b-live-finished")
        E.hook("tab", name="SETTINGS"); time.sleep(3); E.shot("07-settings")
        E.hook("tab", name="AUDIT"); time.sleep(3); E.shot("08-audit")
        E.hook("task", text="demo: second run to stop")
        time.sleep(4)
        E.hook("stop"); time.sleep(2)
        E.hook("tab", name="LIVE"); time.sleep(2); E.shot("09b-live-stopped")
        E.hook("tab", name="TASKS"); time.sleep(2); E.shot("09-stop-state")
        E.hook("resume"); time.sleep(1)

        E.adb("shell", "cmd", "locale", "set-app-locales", E.PKG, "--locales", "vi")
        E.restart_app()
        for tab, nm in (("TASKS", "04-tasks"), ("LIVE", "05-live"), ("APPROVALS", "06-approvals"), ("AUDIT", "08-audit"), ("SETTINGS", "07-settings")):
            E.hook("tab", name=tab); time.sleep(2); E.shot("vi/" + nm)
        E.adb("shell", "cmd", "locale", "set-app-locales", E.PKG, "--locales", "en-US")
    finally:
        hub.kill()


if __name__ == "__main__":
    main()
