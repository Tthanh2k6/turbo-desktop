"""v3 screenshots (Vietnamese) on the Android 16 emulator with a FAKE agent and the synthetic demo frame for /screen.jpg:
no real desktop pixels and no desktop input. Output: design/emulator/v3/*.png.
    hub\\.venv\\Scripts\\python hub\\scripts\\emulator_shots_v3.py
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

PORT = 8763
BASE = f"http://127.0.0.1:{PORT}"
DATA = F.WORK / "shotsdata_v3"


def code(store):
    return totp.code_at(store.totp_secret, int(time.time() // 30))


def main():
    F.WORK.mkdir(parents=True, exist_ok=True)
    if DATA.exists():
        import shutil
        shutil.rmtree(DATA, ignore_errors=True)
    cfg = F.WORK / "turbo-desktop-shots-v3.toml"
    cfg.write_text('preset = "easy"\n[server]\nconnections = ["local"]\n[auth]\ntotp = true\n[approval]\nengine = "hub"\n', "utf-8")
    env = {**os.environ, "TURBO_HUB_DATA": str(DATA), "TURBO_DESKTOP_CONFIG": str(cfg), "PYTHONIOENCODING": "utf-8"}
    hub = subprocess.Popen([sys.executable, "-m", "turbo_hub", "serve", "--port", str(PORT), "--runner", "fake",
                            "--public-url", f"http://10.0.2.2:{PORT}"], cwd=ROOT / "hub", env=env,
                           stdout=open(F.WORK / "hub_shots_v3.out", "a"), stderr=subprocess.STDOUT)
    try:
        for _ in range(60):
            try:
                httpx.get(BASE + "/admin/status", timeout=1)
                break
            except httpx.HTTPError:
                time.sleep(0.25)
        store = SecretStore(DATA)
        tok = {"X-Admin-Token": store.admin_token}
        E.F.log("install:", E.adb("install", "-r", str(E.APK)))
        E.adb("shell", "pm", "clear", E.PKG)
        E.adb("shell", "pm", "grant", E.PKG, "android.permission.POST_NOTIFICATIONS")
        E.adb("shell", "pm", "grant", E.PKG, "android.permission.CAMERA")
        E.adb("shell", "cmd", "locale", "set-app-locales", E.PKG, "--locales", "vi")
        E.adb("shell", "input", "keyevent", "224"); time.sleep(1)
        E.adb("shell", "input", "swipe", "540", "1800", "540", "400"); time.sleep(1)
        E.adb("shell", "input", "text", E.PIN); E.adb("shell", "input", "keyevent", "66"); time.sleep(2)

        E.restart_app(); E.shot("v3/01-welcome")
        E.hook("onboard"); E.restart_app(); E.shot("v3/02-pairing")
        info = httpx.post(BASE + "/admin/pairing", headers=tok).json()
        info.pop("otpauth", None); info.pop("needs", None)
        info["url"] = f"http://10.0.2.2:{PORT}"
        info["urls"] = [{"name": "local", "url": f"http://10.0.2.2:{PORT}"}]
        text = "turbo-pair:" + base64.urlsafe_b64encode(json.dumps(info, separators=(",", ":")).encode()).decode()
        E.hook("pair", text=text); E.enter_pin()
        for _ in range(15):
            if any("pair=" in l for l in E.dbg_log(2)):
                break
        time.sleep(3); E.shot("v3/03-after-pair")          # 2FA setup screen expected (needs.totp)
        E.adb("shell", "input", "tap", "540", "2256"); time.sleep(2)   # "Tôi đã thêm xong"
        E.shot("v3/04-open-session")
        E.hook("session", totp=code(store)); E.enter_pin()
        time.sleep(5); E.shot("v3/05-viec-idle")

        E.hook("task", text="demo: open Calculator and compute (12.5 + 7) * 3")
        time.sleep(4); E.shot("v3/06-viec-running")
        st = DATA / "desktop-state"; st.mkdir(parents=True, exist_ok=True)
        (st / "input_lock.json").write_text(json.dumps({"locked": True, "mode": "whole_task", "since": time.time()}))
        time.sleep(3); E.shot("v3/07-viec-locked")
        (st / "input_lock.json").write_text(json.dumps({"locked": False}))
        for _ in range(30):
            if "pending=1" in E.state():
                break
            time.sleep(1)
        E.hook("tab", name="APPROVALS"); time.sleep(2); E.shot("v3/08-approval")
        E.hook("decide", decision="allow"); E.enter_pin(); time.sleep(8)
        E.hook("tab", name="TASKS"); time.sleep(3); E.shot("v3/09-viec-done")
        E.adb("shell", "input", "swipe", "540", "1700", "540", "500"); time.sleep(1.5); E.shot("v3/09b-viec-done-scrolled")
        E.hook("tab", name="REPORT"); time.sleep(3); E.shot("v3/10-bao-cao")
        E.hook("tab", name="SETTINGS"); time.sleep(3); E.shot("v3/11-cai-dat")
        E.adb("shell", "input", "swipe", "540", "1700", "540", "500"); time.sleep(1.5); E.shot("v3/11b-cai-dat-scrolled")
        E.hook("task", text="demo: second run to stop"); time.sleep(4)
        E.hook("stop"); time.sleep(2)
        E.hook("tab", name="TASKS"); time.sleep(2); E.shot("v3/12-stopped")
        E.hook("resume"); time.sleep(1)
    finally:
        hub.kill()


if __name__ == "__main__":
    main()
