"""Field run 31/33: the Android app (debug build, adb hooks, no UI yet) on the Android 16 emulator against a REAL hub.
Strict-style auth (biometric key + TOTP) with the real agent on Calculator and the fixture app. Needs the emulator
running (emulator -avd motonav36) and the debug APK built. Uses the shared test lock and closes windows it opened.
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
import field_run as F  # noqa: E402
import with_lock  # noqa: E402
from turbo_hub import totp  # noqa: E402
from turbo_hub.store import SecretStore  # noqa: E402

ADB = ["D:/dev/sdk/android/platform-tools/adb.exe", "-s", os.environ.get("EMU", "emulator-5554")]
APK = ROOT / "android/app/build/outputs/apk/debug/app-debug.apk"
PKG = "dev.turbodesktop.remote"
PIN = "1234"


def adb(*a, check=False):
    r = subprocess.run([*ADB, *a], capture_output=True, text=True, timeout=60)
    return r.stdout.strip()


def sh_quote(v: str) -> str:
    return "'" + str(v).replace("'", "'\''") + "'"


def hook(action, **extra):
    """One adb shell string so spaces, parentheses and * in task text survive the device shell."""
    cmd = f"am start -n {PKG}/.MainActivity --es dbg_action {sh_quote(action)}"
    for k, v in extra.items():
        cmd += f" --es {k} {sh_quote(v)}"
    if action != "state":
        adb("logcat", "-c")
    adb("shell", cmd)


def dbg_log(wait=3.0):
    time.sleep(wait)
    return adb("logcat", "-d", "-s", "TurboDbg:I").splitlines()[-3:]


def conn_log(n=14):
    return adb("logcat", "-d", "-s", "TurboConn:*").splitlines()[-n:]


def enter_pin():
    """BiometricPrompt falls back to the device credential on an emulator without fingerprints."""
    time.sleep(4.0)
    adb("shell", "input", "text", PIN)
    adb("shell", "input", "keyevent", "66")


SHOTS = ROOT / "design" / "emulator"


def shot(name):
    target = SHOTS / f"{name}.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    time.sleep(1.2)
    r = subprocess.run([*ADB, "exec-out", "screencap", "-p"], capture_output=True, timeout=60)
    target.write_bytes(r.stdout)
    F.log("screenshot", name, len(r.stdout))


def restart_app():
    adb("shell", "am", "force-stop", PKG)
    adb("shell", "monkey", "-p", PKG, "-c", "android.intent.category.LAUNCHER", "1")
    time.sleep(12)


def state():
    hook("state")
    lines = dbg_log(2)
    return lines[-1] if lines else ""


def main():
    with_lock.acquire(log=F.log)
    before = F.top_windows()
    hub = F.Hub()
    try:
        # strict-style: biometric + TOTP, local connection, real claude (haiku), desktop-mcp
        F.write_config()
        cfg = F.WORK / "turbo-desktop.toml"
        cfg.write_text(cfg.read_text().replace('preset = "balanced"', 'preset = "strict"').replace(
            '[server]\nconnections = ["local"]', '[server]\nconnections = ["local"]\n[cloudflare]\nrequire_access = false'), "utf-8")
        hub.start()
        store = SecretStore(F.DATA)
        F.log("install apk:", adb("install", "-r", str(APK)))
        F.log("set pin:", adb("shell", "locksettings", "set-pin", PIN))
        adb("shell", "pm", "clear", PKG)          # clean prefs + Keystore entries: a fresh install
        adb("shell", "pm", "grant", PKG, "android.permission.POST_NOTIFICATIONS")   # after clear, or a dialog steals focus
        adb("shell", "input", "keyevent", "224")  # wake
        time.sleep(1)
        adb("shell", "input", "swipe", "540", "1800", "540", "400")
        time.sleep(1)
        adb("shell", "input", "text", PIN)
        adb("shell", "input", "keyevent", "66")   # unlock if the PIN from the previous run is active
        time.sleep(2)

        info = httpx.post(F.BASE + "/admin/pairing", headers={"X-Admin-Token": store.admin_token}).json()
        info.pop("otpauth", None); info.pop("needs", None)
        info["url"] = "http://10.0.2.2:%d" % F.PORT
        text = "turbo-pair:" + base64.urlsafe_b64encode(json.dumps(info, separators=(",", ":")).encode()).decode()
        adb("shell", "pm", "grant", PKG, "android.permission.CAMERA")
        restart_app()
        shot("01-welcome")
        hook("onboard")
        restart_app()
        shot("02-pairing")
        hook("pair", text=text)
        enter_pin()          # pairing signs with the biometric-gated key as well (proof of possession)
        for _ in range(15):
            lines = dbg_log(2)
            if any("pair=" in l for l in lines):
                break
        F.log("PAIR ->", lines)
        F.log("hub.out tail:", Path(F.WORK / "hub.out").read_text(errors="replace")[-300:].replace(chr(10), " | "))

        restart_app()
        shot("03-open-session")
        hook("session", totp=totp.code_at(store.totp_secret, int(time.time() // 30)))
        enter_pin()
        time.sleep(2)
        shot("04-tasks")
        F.log("SESSION ->", dbg_log(4))
        F.log("STATE ->", state())

        if "net" in sys.argv[1:]:
            F.log("--- network recovery only")
            adb("shell", "cmd", "connectivity", "airplane-mode", "enable")
            time.sleep(20)
            F.log("OFFLINE:", state()[-200:])
            adb("shell", "cmd", "connectivity", "airplane-mode", "disable")
            t0 = time.time()
            while time.time() - t0 < 120:
                if "online=true" in state():
                    F.log("back online after %.0f s" % (time.time() - t0))
                    F.log("conn log: " + " | ".join(l[:200] for l in conn_log()))
                    break
                time.sleep(3)
            else:
                F.log("STILL OFFLINE after 120 s:", state()[-250:])
            F.log("conn log: " + " | ".join(l[:200] for l in conn_log()))
            return
        F.log("--- task: calculator")
        hook("task", text="Open the Windows Calculator app and compute (12.5 + 7) * 3 using its buttons. "
                          "Tell me the number shown in the result display. Use only the desktop tools.")
        F.log("TASK ->", dbg_log(3))
        hook("tab", name="LIVE")
        time.sleep(6)
        shot("05-live-acting")
        t0 = time.time()
        last = ""
        while time.time() - t0 < 120:
            s = state()
            if s != last:
                F.log("STATE ->", s)
                last = s
            if "Kết thúc" in s or "Finished" in s:
                break
            time.sleep(3)

        F.log("--- approval from the phone: fixture Submit")
        fixture = ROOT / "desktop-mcp" / "tests" / "fixtures" / "turbo_fixture.exe"
        hook("task", text=f"Launch {fixture}. In its window type Ada in the Full name field, then click the Submit button "
                          "and tell me what the result label says. Use only the desktop tools.")
        t0 = time.time()
        while time.time() - t0 < 90:
            s = state()
            if "pending=1" in s:
                F.log("phone sees pending approval:", s)
                hook("tab", name="APPROVALS")
                shot("06-approval")
                hook("decide", decision="deny")
                enter_pin()
                F.log("DECIDE deny ->", dbg_log(4))
                break
            time.sleep(2)
        t0 = time.time()
        while time.time() - t0 < 60 and not any(w in state() for w in ("Kết thúc", "Finished")):
            time.sleep(3)
        F.log("after approval flow:", state())

        F.log("--- STOP from the phone during a task")
        hook("task", text="Open Calculator and press the digit buttons 1 to 9 one at a time, reading the display after each press, and repeat the whole sequence five times. Use only the desktop tools.")
        time.sleep(12)
        hook("stop")
        F.log("STOP ->", dbg_log(3), "|", state())
        shot("09-stop-state")
        hook("resume")
        F.log("RESUME ->", dbg_log(3))
        hook("tab", name="SETTINGS")
        shot("07-settings")
        hook("tab", name="AUDIT")
        time.sleep(2)
        shot("08-audit")

        F.log("--- network loss mid-task")
        hook("task", text="Open Calculator and press the digit buttons 1 to 9 one at a time. Use only the desktop tools.")
        time.sleep(8)
        adb("shell", "svc", "wifi", "disable"); adb("shell", "svc", "data", "disable")
        adb("shell", "cmd", "connectivity", "airplane-mode", "enable")
        time.sleep(12)
        F.log("OFFLINE state:", state())
        adb("shell", "cmd", "connectivity", "airplane-mode", "disable")
        adb("shell", "svc", "wifi", "enable"); adb("shell", "svc", "data", "enable")
        time.sleep(15)
        F.log("ONLINE again:", state())

        F.log("--- Vietnamese UI (per-app locale): the owner's default language")
        adb("shell", "cmd", "locale", "set-app-locales", PKG, "--locales", "vi")
        restart_app()
        for tab, nm in (("TASKS", "04-tasks"), ("LIVE", "05-live"), ("APPROVALS", "06-approvals"), ("AUDIT", "08-audit"), ("SETTINGS", "07-settings")):
            hook("tab", name=tab)
            time.sleep(2)
            shot("vi/" + nm)
        adb("shell", "cmd", "locale", "set-app-locales", PKG, "--locales", "en-US")
    finally:
        hub.kill()
        F.close_new_windows(before)
        with_lock.release()


if __name__ == "__main__":
    main()
