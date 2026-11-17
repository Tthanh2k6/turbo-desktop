"""Field runner: an AI (claude -p) drives desktop-mcp only through MCP, like a user's AI would.

The inner agent gets NO file/shell tools and runs in an empty temp dir, so it cannot read the source.
Usage: python tests/field/run_field.py <task-id> [<task-id> ...]   (results appended to tmp/field/results.jsonl)
"""
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
    "4": dict(prompt="Open a NEW File Explorer window on the folder {tmp} (launch_app explorer with args). Report the window title and the names of the first 5 items "
                     "in the file list. Do not change anything. Close that Explorer window at the end.", explorer=True),
}


def run(tid):
    t = TASKS[tid]
    if t.get("needs_input"):
        import turbo_desktop.winsys as ws
        if ws.idle_seconds() < 120:
            res = {"task": tid, "status": "skipped-busy", "idle": round(ws.idle_seconds())}
            _log(res)
            return res
    _PRE["calc"] = _pids("CalculatorApp.exe")
    state = tempfile.mkdtemp(prefix="field-state-", dir=OUT)
    work = OUT / "work"
    work.mkdir(exist_ok=True)
    prompt = t["prompt"].replace("{tmp}", str(work))
    env = {
        "TURBO_DESKTOP_STATE_DIR": state, "TURBO_DESKTOP_PRESET": t.get("preset", "easy"),
        "TURBO_DESKTOP_APPROVAL_TIMEOUT": "6", "PYTHONUTF8": "1", "PYTHONPATH": str(ROOT / "src"),
        "TURBO_DESKTOP_NO_INPUT": "0" if t.get("needs_input") else "1",
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
    locking.acquire("desktop-mcp-field")
    try:
        for tid in sys.argv[1:]:
            run(tid)
    finally:
        locking.release()
