"""Field runner: an AI (claude -p) drives desktop-mcp only through MCP, like a user's AI would.

The inner agent gets NO file/shell tools and runs in an empty temp dir, so it cannot read the source.
Usage: python tests/field/run_field.py <task-id> [<task-id> ...]   (results appended to tmp/field/results.jsonl)
"""
import glob
import re
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "tests" / "fixtures"
OUT = ROOT / "tmp" / "field"
OUT.mkdir(parents=True, exist_ok=True)
CLAUDE = sorted(glob.glob(os.path.expanduser(
    "~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude.exe")))[-1]
sys.path.insert(0, str(ROOT / "src"))

fx = str(FIX / "turbo_fixture.exe")
ed = str(FIX / "turbo_editor.exe")
cv = str(FIX / "turbo_canvas.exe")

# id -> dict(prompt, preset, needs_input, timeout, stop_after (seconds, creates STOP), note)
TASKS = {
    "8": dict(prompt="Open Calculator (launch_app calc). Compute (12.5 + 7) * 3 by pressing its buttons, then tell me the displayed result. "
                     "Report only the number. Close the Calculator window when done.", kill="CalculatorApp"),
    "19": dict(prompt=f"Open the app at {fx}. Put the 600-character string made of the letter x repeated 600 times into the field named 'Short code'. "
                      "Then tell me honestly how many characters the field actually holds and whether it accepted all of them. Close the app window at the end."),
    "29": dict(prompt=f"Open the app at {fx}. Read the value of the Password field and type the text hunter2 into it. "
                      "Report exactly what the tools told you for each attempt. Close the app window at the end."),
    "25": dict(prompt=f"Open the app at {fx} TWICE (two windows with the same title). In the SECOND window only, set Full name to 'Second' and click Submit; "
                      "then read the Result label of BOTH windows and report which window shows what. Close both windows at the end."),
    "28": dict(prompt=f"Open the app at {fx}. Set Full name to 'Keep' and then click the Submit button. Report whether the click was done or refused and why. "
                      "Then read the Result label. Close the app window at the end.", preset="balanced"),
    "30": dict(prompt=f"Open the app at {fx}. Using ONE batch_actions call run these steps in order: click 'Count 0'; wait_for the text 'Zzz never' in that window with timeout 25; "
                      "click 'Count 1'. Report exactly what the batch call returned, how long it seemed to take, and the button name afterwards. Close the app window at the end.",
               note="runner creates the STOP file 9 s into the run"),
    "27": dict(prompt=f"Open the app at {fx}. Minimize it with window_control, then set Full name to 'Minimized' and report whether it worked and how you got there. "
                      "Close the app window at the end."),
    "24": dict(prompt="Open Calculator with launch_app and wait until its window is really ready (use wait_for). Then say what you see: the list of button names "
                      "in one line. Close the Calculator window at the end.", kill="CalculatorApp"),
    "17": dict(prompt=f"Open the app at {ed}. Type 3 lines of Vietnamese text (with diacritics, e.g. 'Xin chào', 'Tiếng Việt có dấu', 'Cảm ơn bạn') into its text editor, "
                      "then read the text back and report it exactly. Close the app window at the end."),
    "cv": dict(prompt=f"Open the app at {cv}. It is a custom-drawn window. Find out what is on it and report. If there is a Save button, click it, and report the window "
                      "title afterwards. Close the window at the end.", needs_input=True),
    "21": dict(prompt=f"Open the app at {ed}. Use its File menu to choose 'Save As...'. A Save dialog should appear: report its title and the names of its main controls. "
                      "Then cancel the dialog and close the app.", kill="turbo_editor"),
    "20": dict(prompt=f"Open the editor app at {ed} with launch_app args '--accept-keys'. Then open the app at {fx} (this one takes the keyboard focus). "
                      "Now, with the editor window as your target, press Ctrl+S (press_keys with '{Ctrl}s'). A 'Save As' dialog should appear from the editor. "
                      "Report: did the tool notice that the editor was not in front, and did the dialog open? Cancel the dialog with press_keys '{Esc}' and close both apps.",
               needs_input=True),
    "21k": dict(prompt=f"Open the app at {ed} with launch_app args '--accept-keys'. Set its text to 'hello'. Press Ctrl+S with press_keys ('{{Ctrl}}s') to open its Save As dialog. "
                       "Report the dialog's title and the names of its main controls, then cancel it with press_keys '{Esc}' and close the app.", needs_input=True),
    "18": dict(prompt=f"Open the app at {fx} with launch_app args '--accept-keys'. Use act action send_text to type the text 'doodle aa dd' into the field 'Full name' "
                      "(real keyboard typing). Report exactly what the tool said and what the field holds afterwards. Do not try to work around anything, just report. Close the app.",
               needs_input=True, note="UniKeyNT is running on this PC; Telex turns oo/aa/dd into diacritics"),
    "4": dict(prompt="Open a NEW File Explorer window on the folder {tmp}\\explorer-a with launch_app (target explorer, args that folder). Create a new folder named 'turbo-new' in it "
                     "(press_keys Ctrl+Shift+N, then type the name with send_text, then Enter), then rename it to 'turbo-renamed' (select it, F2). Report the names of the items in the window at the end. "
                     "Close that Explorer window.", needs_input=True, setup="explorer-a"),
    "5": dict(prompt="Open a NEW File Explorer window on the folder {tmp}\\big with launch_app (target explorer, args that folder). It holds 200 files. Read the names of the first 5 items "
                     "you can see and say how many items the window reports in total, if it shows that. Do not change anything. Close that Explorer window.",
              setup="big"),
    "22": dict(prompt="Open a NEW File Explorer window on the folder {tmp}\\explorer-a with launch_app (target explorer, args that folder). Open the context menu of the empty area "
                      "(press_keys '{Apps}' or shift+F10 after focusing the file list) and report the first 8 menu entries. Then close the menu with press_keys '{Esc}' and close the Explorer window. "
                      "Do not click any menu entry.", needs_input=True, setup="explorer-a"),
    "30L": dict(prompt=f"Open the app at {fx} with launch_app args '--accept-keys'. Using ONE batch_actions call run in order: act press_keys '{{Tab}}' on the window (real input); "
                       "wait_for the text 'Zzz never' with timeout 25; act press_keys '{Tab}'. Report exactly what the batch returned. Close the app.",
                needs_input=True, note="STOP file is created 14 s into the run; input lock must be released"),
    "4o": dict(prompt="Open a NEW File Explorer window on the folder {tmp} (launch_app explorer with args). Report the window title and the names of the first 5 items "
                     "in the file list. Do not change anything. Close that Explorer window at the end.", explorer=True),
}


SESSION_RESTORE_RE = re.compile(r"\b(notepad|vs ?code|visual studio code|edge|chrome|word|winword|excel)\b", re.I)


def refuses(t):
    """Hard rule: a field task that starts a session-restore app (it would reopen the owner's tabs/files) is refused.
    The server also runs with TURBO_DESKTOP_REQUIRE_CLEAN=1, so launch_app refuses these apps without a clean path."""
    return bool(SESSION_RESTORE_RE.search(t.get("prompt", ""))) and not t.get("clean_launch")


def _setup(name):
    """Create the work folders the explorer tasks need (inside %TEMP%\\turbo-field only)."""
    root = Path(tempfile.gettempdir()) / "turbo-field"
    if name == "explorer-a":
        (root / "explorer-a").mkdir(parents=True, exist_ok=True)
        (root / "explorer-a" / "readme.txt").write_text("field run", encoding="utf-8")
    elif name == "big":
        d = root / "big"
        d.mkdir(parents=True, exist_ok=True)
        for i in range(200):
            (d / f"file_{i:03d}.txt").write_text(str(i), encoding="utf-8")
    return str(root)


def _owner_away(wait=True, need=120.0):
    """True when the owner has been idle for `need` seconds; waits up to FIELD_WAIT_IDLE seconds (without any lock held)."""
    import turbo_desktop.winsys as ws
    end = time.time() + (float(os.environ.get("FIELD_WAIT_IDLE", "300")) if wait else 0)
    while ws.idle_seconds() < need and time.time() < end:
        time.sleep(5)
    return ws.idle_seconds() >= need


def run(tid):
    t = TASKS[tid]
    if refuses(t):
        res = {"task": tid, "status": "refused-session-restore"}
        _log(res)
        return res
    if t.get("needs_input") and not _owner_away(wait=False, need=20.0):  # main loop already waited for 120 s
        import turbo_desktop.winsys as ws
        res = {"task": tid, "status": "skipped-busy", "idle": round(ws.idle_seconds())}
        _log(res)
        return res
    state = tempfile.mkdtemp(prefix="field-state-", dir=OUT)
    work = OUT / "work"
    work.mkdir(exist_ok=True)
    root = _setup(t["setup"]) if t.get("setup") else str(work)
    prompt = t["prompt"].replace("{tmp}", root)
    env = {
        "TURBO_DESKTOP_STATE_DIR": state, "TURBO_DESKTOP_PRESET": t.get("preset", "easy"),
        "TURBO_DESKTOP_APPROVAL_TIMEOUT": "6", "PYTHONUTF8": "1", "PYTHONPATH": str(ROOT / "src"),
        "TURBO_DESKTOP_REQUIRE_CLEAN": "1", "TURBO_DESKTOP_NO_INPUT": "0" if t.get("needs_input") else "1",
        "TURBO_DESKTOP_CONFIG": str(Path(state) / "none.toml"),
    }
    cfg = {"mcpServers": {"turbo-desktop": {"command": str(ROOT / ".venv" / "Scripts" / "python.exe"),
                                            "args": ["-m", "turbo_desktop"], "env": env}}}
    cfgp = Path(state) / "mcp.json"
    cfgp.write_text(json.dumps(cfg), encoding="utf-8")
    cwd = tempfile.mkdtemp(prefix="field-cwd-")
    cmd = [CLAUDE, "-p", prompt, "--mcp-config", str(cfgp), "--strict-mcp-config", "--output-format", "stream-json",
           "--verbose", "--model", "sonnet", "--max-turns", "30", "--permission-mode", "bypassPermissions",
           "--disallowedTools", "Bash,Read,Write,Edit,Glob,Grep,WebFetch,WebSearch,Task,Agent,NotebookEdit,PowerShell"]
    t0 = time.time()
    if tid == "30":  # emergency stop while the batch runs
        threading.Timer(14, lambda: (Path(state) / "STOP").write_text("field")).start()
    if tid == "30L":  # STOP 2.5 s after the first real-input lock appears in the audit log (not on a wall-clock guess)
        def _stop_after_lock():
            audit = Path(state) / "audit.jsonl"
            end = time.time() + 120
            while time.time() < end:
                if audit.exists() and '"input_lock"' in audit.read_text(encoding="utf-8", errors="ignore"):
                    time.sleep(2.5)
                    (Path(state) / "STOP").write_text("field")
                    return
                time.sleep(0.3)
        threading.Thread(target=_stop_after_lock, daemon=True).start()
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", timeout=420, stdin=subprocess.DEVNULL)
    wall = time.time() - t0
    calls, result_chars, final, usage, errors = [], 0, "", {}, []
    names = {}
    for line in p.stdout.splitlines():
        try:
            ev = json.loads(line)
        except Exception:
            continue
        if ev.get("type") == "assistant":
            for b in ev["message"].get("content", []):
                if b.get("type") == "tool_use":
                    calls.append({"tool": b["name"].replace("mcp__turbo-desktop__", ""), "input": b["input"]})
                    names[b["id"]] = len(calls) - 1
        elif ev.get("type") == "user":
            for b in ev["message"].get("content", []):
                if b.get("type") == "tool_result":
                    c = b.get("content")
                    txt = c if isinstance(c, str) else "".join(x.get("text", "") for x in c if isinstance(x, dict))
                    result_chars += len(txt)
                    i = names.get(b.get("tool_use_id"))
                    if i is not None:
                        calls[i]["result"] = txt[:600]
                        if '"ok":false' in txt or "error" in txt[:80].lower():
                            errors.append({"call": calls[i]["tool"], "input": calls[i]["input"], "result": txt[:300]})
        elif ev.get("type") == "result":
            final = ev.get("result", "")
            usage = ev.get("usage", {})
    res = {"task": tid, "status": "ran", "calls": len(calls), "result_chars": result_chars, "approx_result_tokens": result_chars // 4,
           "wall_s": round(wall, 1), "final": final[:700], "usage": {k: usage.get(k) for k in ("input_tokens", "output_tokens", "cache_read_input_tokens")},
           "errors": errors[:6], "tools": [c["tool"] for c in calls]}
    _log(res)
    (Path(state) / "transcript.json").write_text(json.dumps(calls, ensure_ascii=False, indent=1), encoding="utf-8")
    _cleanup(t)
    return res


_PRE = {}


def _pids(image):
    out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {image}", "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout
    return {int(l.split(",")[1].strip('"')) for l in out.splitlines() if l.startswith('"') and image.lower() in l.lower()}


def _cleanup(t):
    """Close anything the run left behind: only our fixture exes and Calculator started by the run."""
    for n in ("turbo_fixture.exe", "turbo_editor.exe", "turbo_canvas.exe"):
        subprocess.run(["taskkill", "/IM", n, "/F"], capture_output=True)
    # Calculator: only instances that did not exist before this run (we hold the machine lock)
    if t.get("kill") == "CalculatorApp":
        for pid in _pids("CalculatorApp.exe") - _PRE.get("calc", set()):
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)


def _log(res):
    with open(OUT / "results.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(res, ensure_ascii=False) + "\n")
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "tests"))
    import locking
    for tid in sys.argv[1:]:
        if TASKS.get(tid, {}).get("needs_input"):
            _owner_away(wait=True)          # wait for the owner to be away first, without holding the shared lock
        locking.acquire("desktop-mcp-field")   # hold the machine lock for this one task only
        try:
            run(tid)
        finally:
            locking.release()
