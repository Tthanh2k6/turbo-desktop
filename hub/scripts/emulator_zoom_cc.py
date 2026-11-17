"""Emulator check for 18/11 features, FAKE agent + synthetic demo frame (no real desktop pixels, no desktop input):
  1. a Claude Code permission prompt (POST /cc/permission) shows as a card with the command, no countdown;
  2. full-screen screen view: double-tap zooms, the app then asks the hub for a sharp crop (state shows crop=...),
     double-tap again resets.
Output: design/emulator/v4/*.png.   hub\\.venv\\Scripts\\python hub\\scripts\\emulator_zoom_cc.py
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
from turbo_hub.cc_permission import load_or_create_token  # noqa: E402
from turbo_hub.store import SecretStore  # noqa: E402

PORT = 8764
BASE = f"http://127.0.0.1:{PORT}"
DATA = F.WORK / "shotsdata_v4"


def state_line() -> str:
    E.hook("state")
    for line in reversed(E.dbg_log(2)):
        if "state online" in line:
            return line
    return ""


def main():
    F.WORK.mkdir(parents=True, exist_ok=True)
    if DATA.exists():
        import shutil
        shutil.rmtree(DATA, ignore_errors=True)
    cfg = F.WORK / "turbo-desktop-shots-v4.toml"
    cfg.write_text('preset = "easy"\n[server]\nconnections = ["local"]\n[auth]\ntotp = true\n[approval]\nengine = "hub"\n'
                   '[screen_view]\nmax_fps = 5\n', "utf-8")
    env = {**os.environ, "TURBO_HUB_DATA": str(DATA), "TURBO_DESKTOP_CONFIG": str(cfg), "PYTHONIOENCODING": "utf-8"}
    hub = subprocess.Popen([sys.executable, "-m", "turbo_hub", "serve", "--port", str(PORT), "--runner", "fake",
                            "--public-url", f"http://10.0.2.2:{PORT}"], cwd=ROOT / "hub", env=env,
                           stdout=open(F.WORK / "hub_shots_v4.out", "a"), stderr=subprocess.STDOUT)
    results = {}
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
        E.adb("shell", "cmd", "locale", "set-app-locales", E.PKG, "--locales", "vi")
        E.adb("shell", "svc", "power", "stayon", "true")   # the screen must not lock between steps
        E.adb("shell", "settings", "put", "secure", "immersive_mode_confirmations", "confirmed")  # no "Viewing full screen" card
        E.adb("shell", "input", "keyevent", "224"); time.sleep(1)
        E.adb("shell", "input", "swipe", "540", "1800", "540", "400"); time.sleep(1)
        E.adb("shell", "input", "text", E.PIN); E.adb("shell", "input", "keyevent", "66"); time.sleep(2)
        E.restart_app()
        info = httpx.post(BASE + "/admin/pairing", headers=tok).json()
        info.pop("otpauth", None); info.pop("needs", None)
        info["url"] = f"http://10.0.2.2:{PORT}"
        info["urls"] = [{"name": "local", "url": f"http://10.0.2.2:{PORT}"}]
        text = "turbo-pair:" + base64.urlsafe_b64encode(json.dumps(info, separators=(",", ":")).encode()).decode()
        E.hook("pair", text=text); E.enter_pin()
        for _ in range(15):
            if any("pair=" in l for l in E.dbg_log(2)):
                break
        time.sleep(3)
        E.adb("shell", "input", "tap", "540", "2168"); time.sleep(2)      # "Tôi đã thêm xong" on the 2FA screen
        E.hook("session", totp=totp.code_at(store.totp_secret, int(time.time() // 30))); E.enter_pin()
        time.sleep(5)
        E.hook("onboard"); time.sleep(1); E.restart_app()      # paired + session kept in prefs: main screen now
        E.adb("shell", "input", "tap", "540", "2168"); time.sleep(3)   # "Tôi đã thêm xong" if the 2FA step shows again

        # 1. Claude Code permission prompt
        cc = {"X-CC-Token": load_or_create_token(DATA)}
        payload = {"tool_name": "Bash", "cwd": "D:\\Project\\demo-app", "session_id": "emu",
                   "tool_input": {"command": "git push origin main", "description": "Push the release branch"}}
        req = httpx.post(BASE + "/cc/permission", json=payload, headers=cc).json()
        time.sleep(3)
        E.hook("tab", name="APPROVALS"); time.sleep(3); E.shot("v4/01-cc-approval")
        results["cc_pending"] = "pending=1" in state_line()
        E.adb("shell", "cmd", "statusbar", "expand-notifications"); time.sleep(2); E.shot("v4/02-cc-notification")
        E.adb("shell", "cmd", "statusbar", "collapse"); time.sleep(1)
        # the PC dialog answers first: the phone card must close by itself
        r = httpx.post(BASE + f"/cc/permission/{req['id']}", json={"decision": "allow"},
                       headers={**cc, "X-CC-Key": req["key"]}).json()
        time.sleep(4)
        results["pc_answer"] = r
        results["cc_closed"] = "pending=0" in state_line()
        E.shot("v4/03-cc-closed-after-pc-answer")

        # 2. full-screen player + zoom
        E.hook("tab", name="TASKS"); time.sleep(3); E.shot("v4/04-viec")
        E.hook("fullscreen"); time.sleep(4); E.shot("v4/05-fullscreen")
        E.adb("shell", "wm", "size")
        # double-tap the middle of the (landscape) player
        E.adb("shell", "input tap 1200 540 & sleep 0.08; input tap 1200 540")
        time.sleep(4); E.shot("v4/06-zoomed")
        s1 = state_line(); results["zoom_state"] = s1
        results["crop_after_double_tap"] = "crop=null" not in s1 and "crop=" in s1
        E.adb("shell", "input tap 1200 540 & sleep 0.08; input tap 1200 540")
        time.sleep(3); E.shot("v4/07-reset")
        s2 = state_line(); results["reset_state"] = s2
        results["crop_cleared"] = "crop=null" in s2
    finally:
        hub.kill()
        print(json.dumps(results, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
