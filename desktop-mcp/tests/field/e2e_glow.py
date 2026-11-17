"""Real-input end to end through MCP: `claude -p` (haiku) drives the editor fixture with a 5-step real-input task while this
script watches the screen edge. Checks: the glow appears during the run and is gone afterwards; the input-lock banner
appears and is gone; real keystrokes arrived (file text). Saves edge strips (not full screenshots) to field-shots/.

Run only when the owner is away (idle >= 120 s). Takes the shared machine lock.
"""
import ctypes
import glob
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
import locking  # noqa: E402
from turbo_desktop import winsys  # noqa: E402

SHOTS = ROOT / "field-shots"
SHOTS.mkdir(exist_ok=True)
ed = str(ROOT / "tests" / "fixtures" / "turbo_editor.exe")
CLAUDE = sorted(glob.glob(os.path.expanduser("~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude.exe")))[-1]
u32 = ctypes.windll.user32

PROMPT = (f"Open the app at {ed} with launch_app args '--accept-keys'. Then do these 5 steps with REAL keyboard typing: "
          "1) act action send_text on the control named 'Text editor' with text 'one'; 2) press_keys '{Enter}' on that control; "
          "3) send_text 'two'; 4) press_keys '{Enter}'; 5) send_text 'three'. Then read the control's text and report it exactly, "
          "and close the app window.")


def win_exists(cls):
    return bool(u32.FindWindowW(cls, None))


def edge_orange(img):
    w, h = img.size
    hits = 0
    for px in ((w // 2, 2), (w // 2, h - 3), (2, h // 2), (w - 3, h // 2)):
        r, g, b = img.getpixel(px)[:3]
        hits += abs(r - 0xE0) < 14 and abs(g - 0x46) < 14 and abs(b - 0x1D) < 14
    return hits >= 2


def main():
    from PIL import ImageGrab
    end_wait = time.time() + float(os.environ.get('FIELD_WAIT_IDLE', '0'))
    while winsys.idle_seconds() < 120 and time.time() < end_wait:
        time.sleep(5)
    if winsys.idle_seconds() < 120:
        print(json.dumps({"status": "skipped-busy", "idle": round(winsys.idle_seconds())}))
        return 2
    locking.acquire("desktop-mcp-e2e")   # taken only after the idle wait above, so the hub agent can use the lock meanwhile
    state = tempfile.mkdtemp(prefix="e2e-state-")
    env = {"TURBO_DESKTOP_STATE_DIR": state, "TURBO_DESKTOP_PRESET": "easy", "TURBO_DESKTOP_NO_INPUT": "0",
           "TURBO_DESKTOP_IDLE_SECONDS": "5", "TURBO_DESKTOP_REQUIRE_CLEAN": "1", "PYTHONUTF8": "1",
           "PYTHONPATH": str(ROOT / "src"), "TURBO_DESKTOP_CONFIG": str(Path(state) / "none.toml")}
    cfg = Path(state) / "mcp.json"
    cfg.write_text(json.dumps({"mcpServers": {"turbo-desktop": {"command": str(ROOT / ".venv" / "Scripts" / "python.exe"),
                                                                "args": ["-m", "turbo_desktop"], "env": env}}}), encoding="utf-8")
    samples, stop = [], threading.Event()
    saved = {"glow": False, "banner": False}

    def watch():
        t0 = time.time()
        while not stop.is_set():
            img = ImageGrab.grab(all_screens=True).convert("RGB")
            glow, banner = edge_orange(img), win_exists("TurboDesktopBanner")
            samples.append((round(time.time() - t0, 1), glow, banner, winsys.idle_seconds() < 1.0))
            if glow and not saved["glow"]:
                saved["glow"] = True
                w, h = img.size
                strip = img.crop((0, 0, w, 60))   # edge strips only: never a full-desktop screenshot
                strip.save(SHOTS / "edge_top_glow_on.png")
                img.crop((0, 0, 60, h)).resize((60, h // 4)).save(SHOTS / "edge_left_glow_on.png")
            if banner and not saved["banner"]:
                saved["banner"] = True
                img.crop((0, 0, img.size[0], 60)).save(SHOTS / "edge_top_banner_on.png")
            time.sleep(0.4)

    th = threading.Thread(target=watch, daemon=True)
    th.start()
    t0 = time.time()
    try:
        p = subprocess.run([CLAUDE, "-p", PROMPT, "--mcp-config", str(cfg), "--strict-mcp-config", "--model", "haiku",
                            "--max-turns", "25", "--permission-mode", "bypassPermissions", "--output-format", "json",
                            "--disallowedTools", "Bash,Read,Write,Edit,Glob,Grep,WebFetch,WebSearch,Task,Agent,NotebookEdit,PowerShell"],
                           cwd=tempfile.mkdtemp(prefix="e2e-cwd-"), capture_output=True, text=True, encoding="utf-8",
                           timeout=300, stdin=subprocess.DEVNULL)
        run_secs = time.time() - t0
        time.sleep(6)   # glow lingers 3 s after the last action, the lock is already gone
    finally:
        stop.set()
        th.join(3)
        for n in ("turbo_editor.exe",):
            subprocess.run(["taskkill", "/IM", n, "/F"], capture_output=True)
        locking.release()
    try:
        result = json.loads(p.stdout).get("result", "")
    except Exception:
        result = p.stdout[-400:]
    during = [s for s in samples if s[0] <= run_secs]
    after = [s for s in samples if s[0] > run_secs + 5]
    owner_back = any(s[3] for s in samples)
    out = {"status": "ran", "run_secs": round(run_secs, 1), "samples": len(samples),
           "glow_seen_during": any(s[1] for s in during), "banner_seen_during": any(s[2] for s in during),
           "glow_after_5s": any(s[1] for s in after), "banner_after": any(s[2] for s in after),
           "physical_input_seen": owner_back, "agent_result": result[:300]}
    (SHOTS / "e2e_result.json").write_text(json.dumps({**out, "timeline": samples[::3]}, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
