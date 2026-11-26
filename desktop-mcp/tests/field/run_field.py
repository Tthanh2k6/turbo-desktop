"""Hardened 30-task field runner: `claude -p --model haiku` drives desktop-mcp only through stdio MCP.

Targets are strictly limited to {calc, calculator, turbo_fixture.exe, turbo_editor.exe, turbo_canvas.exe}.
Work files live strictly in %TEMP%\\turbo-field\\.
Usage:
  python tests/field/run_field.py 1 2 3
  python tests/field/run_field.py all
"""
import glob
import json
import os
import re
import shutil
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
WORK_ROOT = Path(tempfile.gettempdir()) / "turbo-field"
WORK_ROOT.mkdir(parents=True, exist_ok=True)

_claude_candidates = sorted(glob.glob(os.path.expanduser(
    "~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude.exe")))
CLAUDE = (
    os.environ.get("CLAUDE_BIN")
    or shutil.which("claude")
    or (_claude_candidates[-1] if _claude_candidates else "")
)

sys.path.insert(0, str(ROOT / "src"))
from turbo_desktop import security as sec  # noqa: E402
from turbo_desktop import winsys  # noqa: E402

fx = str(FIX / "turbo_fixture.exe")
ed = str(FIX / "turbo_editor.exe")
cv = str(FIX / "turbo_canvas.exe")

ALLOWED_TARGETS = frozenset({
    "calc",
    "calculator",
    "turbo_fixture.exe",
    "turbo_editor.exe",
    "turbo_canvas.exe",
})

SESSION_RESTORE_RE = re.compile(
    r"\b(notepad|vs ?code|visual studio code|edge|msedge|chrome|winword|wordpad|excel)\b"
    r"|\bin Word\b|\bMicrosoft Word\b|\bWord\.exe\b",
    re.I,
)

FORBIDDEN_PROMPT_RE = re.compile(
    r"\b(explorer(?:\.exe)?|notepad(?:\.exe)?|vs ?code|visual studio code|msedge(?:\.exe)?|"
    r"edge|chrome(?:\.exe)?|ms-settings:\S*|systemsettings(?:\.exe)?|mspaint(?:\.exe)?|"
    r"control(?:\.exe)?|control\s+panel|winword(?:\.exe)?|wordpad(?:\.exe)?|excel(?:\.exe)?)\b",
    re.I,
)


def normalize_target(target: str) -> str:
    s = str(target or "").strip().strip('"').strip("'")
    if not s:
        return ""
    return Path(s).name.lower()


def validate_target(target: str) -> str:
    """Enforce strict target allowlist: only Calculator or our 3 fixture executables in tests/fixtures."""
    norm = normalize_target(target)
    if norm not in ALLOWED_TARGETS:
        raise ValueError(
            f"disallowed target {target!r}; allowed targets: {sorted(ALLOWED_TARGETS)}"
        )
    s = str(target or "").strip().strip('"').strip("'")
    if norm.endswith(".exe") and ("\\" in s or "/" in s):
        if Path(s).resolve() != (FIX / norm).resolve():
            raise ValueError(f"fixture path {target!r} must resolve inside {FIX}")
    return norm


def validate_task(t: dict) -> list[str]:
    """Validate declared targets and ensure the prompt never references forbidden desktop apps."""
    targets = t.get("targets")
    if not targets and t.get("target"):
        targets = [t["target"]]
    if not targets or not isinstance(targets, (list, tuple)):
        raise ValueError(f"task must declare non-empty allowlisted targets: {t!r}")
    normed = [validate_target(tgt) for tgt in targets]
    prompt = t.get("prompt", "")
    if FORBIDDEN_PROMPT_RE.search(prompt):
        raise ValueError(f"task prompt references forbidden app: {prompt[:140]!r}")
    return normed


def refuses(t: dict) -> bool:
    """Hard rule: a task naming a session-restore app is refused."""
    return bool(SESSION_RESTORE_RE.search(t.get("prompt", ""))) and not t.get("clean_launch")


def _clean_dir(sub: str) -> Path:
    d = WORK_ROOT / sub
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _has_audit(state: Path, pred) -> bool:
    ap = state / "audit.jsonl"
    if not ap.exists():
        return False
    for ln in ap.read_text(encoding="utf-8", errors="replace").splitlines():
        if not ln.strip():
            continue
        try:
            if pred(json.loads(ln)):
                return True
        except ValueError:
            continue
    return False


def _calls_list(state: Path) -> list[dict]:
    tp = state / "transcript.json"
    if not tp.exists():
        return []
    try:
        return json.loads(tp.read_text(encoding="utf-8"))
    except ValueError:
        return []


def _unwrap_result(raw) -> str:
    s = str(raw or "")
    for _ in range(2):
        try:
            obj = json.loads(s)
        except ValueError:
            break
        if isinstance(obj, dict) and "result" in obj:
            v = obj["result"]
            s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, separators=(",", ":"))
        else:
            s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
            break
    return s


def _is_tool_error(raw: str) -> bool:
    inner = _unwrap_result(raw)
    try:
        obj = json.loads(inner)
        if isinstance(obj, dict):
            return obj.get("ok") is False or ("error" in obj and obj.get("ok") is not True)
    except ValueError:
        pass
    return '"ok":false' in inner or bool(re.search(r"(?i)(?<!snapshot)\berror\b", inner[:120]))


def _any_result_has(state: Path, substr: str) -> bool:
    for c in _calls_list(state):
        raw = str(c.get("result", ""))
        if substr in raw or substr in _unwrap_result(raw):
            return True
    return False


# ---------------------------------------------------------------- 30 tasks (Calculator + C# fixtures only)

TASKS = {
    "1": dict(
        targets=["turbo_editor.exe"],
        prompt=(
            f'Launch {ed} with args \'--mode tabs --workdir "{{work}}"\'. '
            "Click 'New Tab' to open a second tab, set 'Text editor' in the active tab to the 3 lines "
            "'Xin chào Việt Nam\\nTiếng Việt có dấu\\nĐường phố Hà Nội', keep or set 'Save path' to '{{work}}\\a.txt', "
            "click 'Save', read 'Save status', then close the window."
        ),
        setup=lambda w: (_clean_dir("t1"),),
        work_sub="t1",
        verify=lambda s, w, r: (
            (w / "a.txt").exists() and "Tiếng Việt có dấu" in (w / "a.txt").read_text("utf-8") and "Đường phố Hà Nội" in (w / "a.txt").read_text("utf-8"),
            f"a.txt exists={(w / 'a.txt').exists()}",
        ),
    ),
    "2": dict(
        targets=["turbo_editor.exe"],
        prompt=(
            f"Launch {ed} with args '--mode find'. Set 'Text editor' to 'alpha beta alpha gamma'. "
            "Click 'Find and Replace...'. In the 'Find and Replace' window, set 'Find what' to 'alpha', "
            "'Replace with' to 'omega', click 'Replace All', then click 'Close'. Back in the main window, "
            "read 'Text editor' to confirm 'omega beta omega gamma', click 'Undo', read 'Text editor' again "
            "to confirm 'alpha beta alpha gamma' was restored, and close the window."
        ),
        verify=lambda s, w, r: (
            "alpha beta alpha gamma" in r.get("final", "") and "omega beta omega gamma" in r.get("final", "") and not r.get("errors"),
            "checked replace + undo text in final output",
        ),
    ),
    "3": dict(
        targets=["turbo_canvas.exe"],
        prompt=(
            f'Launch {cv} with args \'--mode paint --workdir "{{work}}"\'. '
            "Click 'Resize...'. In the 'Resize Canvas' window, set 'Width' to '800' and 'Height' to '600', click 'Apply'. "
            "Back in the main window, confirm 'PNG path' is '{{work}}\\canvas.png', click 'Save PNG', "
            "read 'Paint status' and 'Dimensions', and close the window."
        ),
        setup=lambda w: (_clean_dir("t3"),),
        work_sub="t3",
        verify=lambda s, w, r: _check_png_dims(w / "canvas.png", 800, 600),
    ),
    "4": dict(
        targets=["turbo_fixture.exe"],
        prompt=(
            f'Launch {fx} with args \'--mode vfiles --workdir "{{work}}"\'. '
            "Create a folder named 'turbo-new': set 'Item name' to 'turbo-new' and click 'New Folder'. "
            "Next rename it to 'turbo-renamed': select 'turbo-new' in the file list, set 'Item name' to 'turbo-renamed', and click 'Rename'. "
            "Then create a file: set 'Item name' to 'note.txt' and click 'New File'. "
            "Finally click 'Details View', inspect the window to read 'View status' and the items, and close the window."
        ),
        setup=lambda w: _clean_dir("t4"),
        work_sub="t4",
        verify=lambda s, w, r: (
            (w / "turbo-renamed").is_dir() and (w / "note.txt").is_file() and "Details" in r.get("final", ""),
            f"dir={(w / 'turbo-renamed').is_dir()} file={(w / 'note.txt').is_file()}",
        ),
    ),
    "5": dict(
        targets=["turbo_fixture.exe"],
        prompt=(
            f"Launch {fx} with args '--mode biglist'. Click 'Sort by Size'. "
            "Inspect the window with query='file_' and read 'Total items' plus the first 5 sorted filenames you see. "
            "Close the window when done."
        ),
        verify=lambda s, w, r: (
            "200" in r.get("final", "") and "file_" in r.get("final", "") and not r.get("errors"),
            "checked 200 items + sorted filenames",
        ),
    ),
    "6": dict(
        targets=["turbo_editor.exe"],
        prompt=(
            f'Launch {ed} with args \'--mode save-overwrite --workdir "{{work}}"\'. '
            "Set 'Text editor' to 'NEW OVERWRITE CONTENT' and click 'Save'. "
            "A 'Confirm Overwrite' window will appear: inspect it and click 'Yes'. "
            "Read 'Save status' in the main window and close the window."
        ),
        setup=lambda w: _clean_dir("t6"),
        work_sub="t6",
        verify=lambda s, w, r: (
            (w / "existing.txt").exists() and "NEW OVERWRITE CONTENT" in (w / "existing.txt").read_text("utf-8"),
            f"existing.txt={((w / 'existing.txt').read_text('utf-8') if (w / 'existing.txt').exists() else 'missing')!r}",
        ),
    ),
    "7": dict(
        targets=["turbo_fixture.exe"],
        prompt=(
            f"Launch {fx} with args '--mode prefs'. Click 'Mouse Preferences...'. "
            "In 'Mouse Preferences', read 'Speed value' and 'Double-click speed' slider, optionally click 'Page right', "
            "then click 'Cancel' without saving. Read 'Current speed' back in the main window to verify it is still 5, "
            "and close the window."
        ),
        verify=lambda s, w, r: (
            "5" in r.get("final", "") and not r.get("errors"),
            "prefs cancelled with Current speed=5",
        ),
    ),
    "8": dict(
        targets=["calc"],
        kill="CalculatorApp",
        prompt=(
            "Open Calculator (launch_app calc). Compute (12.5 + 7) * 3 by pressing its buttons, read the displayed result, "
            "then open Navigation and switch to Scientific mode. Report the result and confirm Scientific mode, then close Calculator."
        ),
        verify=lambda s, w, r: (
            "58.5" in r.get("final", "") and not r.get("errors"),
            "Calculator computed 58.5 + Scientific",
        ),
    ),
    "9": dict(
        targets=["turbo_fixture.exe"],
        prompt=(
            f"Launch {fx} with args '--mode display'. Read the 'Scale' and 'Resolution' fields (read-only; do not edit). "
            "Report both values and close the window."
        ),
        verify=lambda s, w, r: (
            "100%" in r.get("final", "") and "1920 x 1080" in r.get("final", "") and not r.get("errors"),
            "read Scale 100% and Resolution 1920 x 1080",
        ),
    ),
    "10": dict(
        targets=["turbo_fixture.exe"],
        prompt=(
            f"Launch {fx} with args '--mode config'. Set 'Search config' to 'bluetooth'. "
            "Read 'Bluetooth status' and whether the 'Bluetooth' checkbox is checked or unchecked. "
            "Do NOT toggle or click the 'Bluetooth' checkbox. Close the window."
        ),
        verify=lambda s, w, r: (
            ("on" in r.get("final", "").lower() or "checked" in r.get("final", "").lower())
            and not any(
                c.get("tool") == "act" and "bluetooth" in json.dumps(c.get("input", {})).lower()
                and c.get("input", {}).get("action") in ("click", "toggle", "invoke")
                for c in _calls_list(s)
            ),
            "read Bluetooth On without toggling",
        ),
    ),
    "11": dict(
        targets=["turbo_fixture.exe"],
        preset="strict",
        approver="allow",
        prompt=(
            f"Launch {fx} with args '--mode timer'. Click 'Add Timer', then click 'Start', then click 'Delete'. "
            "Read 'Timer status' after deleting and report what happened (including any approval). Close the window."
        ),
        verify=lambda s, w, r: (
            "Deleted" in r.get("final", "")
            and _has_audit(s, lambda e: e.get("event") == "approval_decision" and e.get("decision") == "allow"),
            "Strict timer Delete requested approval + allowed",
        ),
    ),
    "12": dict(
        targets=["turbo_canvas.exe"],
        prompt=(
            f'Launch {cv} with args \'--mode viewer --workdir "{{work}}"\'. '
            "Click 'Open Image' to load '{{work}}\\canvas.png', read 'Image dimensions', "
            "report the exact pixel dimensions, and close the window."
        ),
        setup=lambda w: _prepare_t12_png(w / "canvas.png"),
        work_sub="t12",
        verify=lambda s, w, r: (
            "800" in r.get("final", "") and "600" in r.get("final", "") and not r.get("errors"),
            "viewer reported 800 x 600",
        ),
    ),
    "13": dict(
        targets=["turbo_editor.exe"],
        prompt=(
            f'Launch {ed} with args \'--mode project --workdir "{{work}}"\'. '
            "Set 'File name' to 'hello.py', click 'New File', set 'Code editor' to "
            "'def greet():\\n    return \"hi\"\\n', click 'Save File', read 'Project status', and close the window."
        ),
        setup=lambda w: _clean_dir("t13"),
        work_sub="t13",
        verify=lambda s, w, r: (
            (w / "hello.py").exists() and 'return "hi"' in (w / "hello.py").read_text("utf-8"),
            f"hello.py exists={(w / 'hello.py').exists()}",
        ),
    ),
    "14": dict(
        targets=["turbo_editor.exe"],
        prompt=(
            f"Launch {ed} with args '--mode palette'. Click 'Command Palette...'. "
            "In 'Command Palette', select 'Toggle Word Wrap' and click 'Run Command'. "
            "Back in the main window, read 'Word wrap status' to confirm it changed to On, and close the window."
        ),
        verify=lambda s, w, r: (
            "Word Wrap: On" in r.get("final", "") or ("On" in r.get("final", "") and not r.get("errors")),
            "Command Palette toggled Word Wrap On",
        ),
    ),
    "15": dict(
        targets=["turbo_fixture.exe"],
        prompt=(
            f"Launch {fx} with args '--mode docview'. Inspect the nested document controls and read 'Heading' and 'Document body'. "
            "Report the heading text and first sentence of the body, then close the window."
        ),
        verify=lambda s, w, r: (
            "Example Domain" in r.get("final", "") and not r.get("errors"),
            "read nested docview Example Domain",
        ),
    ),
    "16": dict(
        targets=["turbo_editor.exe"],
        prompt=(
            f"Launch {ed} with args '--mode richtext'. Set 'Rich editor' to 'Hello world today', set 'Target word' to 'world', "
            "click 'Bold', read 'Formatting status' to confirm Bold was applied to 'world', and close the window."
        ),
        verify=lambda s, w, r: (
            "Bold: world" in r.get("final", "") or ("bold" in r.get("final", "").lower() and "world" in r.get("final", "")),
            "RichText Bold applied to world",
        ),
    ),
    "17": dict(
        targets=["turbo_editor.exe"],
        prompt=(
            f"Launch {ed} with args '--mode richtext'. Set 'Rich editor' to 3 lines separated by newlines: "
            "'Dòng 1: Xin chào\\nDòng 2: Tiếng Việt\\nDòng 3: Cảm ơn'. "
            "Use act action 'read' on 'Rich editor' to read the text back and verify all 3 lines and line breaks are preserved. "
            "Close the window."
        ),
        verify=lambda s, w, r: (
            "Xin chào" in r.get("final", "") and "Tiếng Việt" in r.get("final", "") and "Cảm ơn" in r.get("final", "")
            and _any_result_has(s, "Cảm ơn"),
            "RichText multiline Vietnamese readback verified",
        ),
    ),
    "18": dict(
        targets=["turbo_fixture.exe"],
        ime_or_input=True,
        prompt=(
            f"Launch {fx} with args '--mode ime'. Use UIA set_value (or send_text if real input is enabled) "
            "to enter the exact string 'doodle aa dd Xin chào' into 'Full name'. "
            "Read 'Full name' and 'IME result' back to verify there are no double-diacritic corruptions, and close the window."
        ),
        verify=lambda s, w, r: (
            "doodle aa dd Xin chào" in r.get("final", "") and _any_result_has(s, "doodle aa dd Xin chào"),
            "IME trap text preserved without double diacritics",
        ),
    ),
    "19": dict(
        targets=["turbo_fixture.exe"],
        prompt=(
            f"Launch {fx}. Put this exact 600-character string into 'Short code' using set_value: "
            + "".join(f"{i:02d}abcdefgh" for i in range(60))
            + ". Also note whether the app's edit box is MaxLength=10 vs UIA set_value, read 'Short code' back to report the exact character length, "
            "and close the window."
        ),
        verify=lambda s, w, r: (
            "600" in r.get("final", "") and _any_result_has(s, '"length":600'),
            "reported exact length=600 in tool result and answer",
        ),
    ),
    "20": dict(
        targets=["turbo_editor.exe", "turbo_fixture.exe"],
        prompt=(
            f"Launch {ed} first (remember its window id, e.g. w1), then launch {fx} second. "
            "Without closing the second window, target the FIRST (behind) TurboEditor window by its window id (wid), "
            "set 'Text editor' to 'Targeted behind focus', read it back, verify TurboFixture's 'Full name' is still empty, "
            "and close both windows."
        ),
        verify=lambda s, w, r: (
            "Targeted behind focus" in r.get("final", "") and not r.get("errors"),
            "behind window targeted cleanly by wid",
        ),
    ),
    "21": dict(
        targets=["turbo_editor.exe"],
        prompt=(
            f"Launch {ed} with args '--mode unsaved'. Set 'Text editor' to 'unsaved draft', then call window_control close on that window. "
            "Check windows_list for the 'Unsaved Changes' dialog, inspect it, and click \"Don't Save\". "
            "Verify with wait_for that TurboEditor is gone."
        ),
        verify=lambda s, w, r: (
            "Don't Save" in r.get("final", "") and not r.get("errors"),
            "unsaved modal handled via Don't Save",
        ),
    ),
    "22": dict(
        targets=["turbo_fixture.exe"],
        prompt=(
            f"Launch {fx}. Call act action='expand' on 'Country' ComboBox, inspect the window to read all expanded options, "
            "then collapse it with act action='expand' value='collapse', and close the window without changing the selection."
        ),
        verify=lambda s, w, r: (
            all(c in r.get("final", "") for c in ("Vietnam", "Japan", "Germany")) and not r.get("errors"),
            "expanded, read Vietnam/Japan/Germany, and collapsed",
        ),
    ),
    "23": dict(
        targets=["turbo_editor.exe"],
        prompt=(
            f"Launch {ed} with args '--title \".env - Secrets\"'. Call system_state and windows_list. "
            "Try inspect_compact on that window, report how windows_list hid the title and that inspect was denied by secret-window, "
            "and close the window."
        ),
        verify=lambda s, w, r: (
            "[hidden: secret window]" in r.get("final", "")
            and _any_result_has(s, "secret-window")
            and _has_audit(s, lambda e: e.get("event") == "denied" and e.get("rule") == "secret-window"),
            "secret window hidden + denied + system_state checked",
        ),
    ),
    "24": dict(
        targets=["turbo_fixture.exe"],
        prompt=(
            f"Launch {fx} with args '--splash 5.5' and wait=2.0. "
            "Then use wait_for with title='TurboFixture' and timeout=10 to wait past the 5.5s splash screen until the real window appears. "
            "Inspect 'TurboFixture' to confirm 'Submit' is present, then close the window."
        ),
        verify=lambda s, w, r: (
            "Submit" in r.get("final", "") and not r.get("errors"),
            "waited past 5.5s splash for TurboFixture",
        ),
    ),
    "25": dict(
        targets=["turbo_fixture.exe"],
        prompt=(
            f"Launch {fx} TWICE so there are two 'TurboFixture' windows. Target ONLY the SECOND window by its window id (wid): "
            "set 'Full name' to 'Second' and click 'Submit'. Read 'lblResult' (mode='text') on BOTH windows to confirm only the second "
            "shows 'Submitted: Second', then close both windows."
        ),
        verify=lambda s, w, r: (
            "Second" in r.get("final", "") and not r.get("errors"),
            "2nd duplicate-title window targeted by wid",
        ),
    ),
    "26": dict(
        targets=["turbo_canvas.exe"],
        prompt=(
            f"Launch {cv}. Call system_state to check idleSeconds, and inspect_compact on TurboCanvas (OCR fallback). "
            "Report the OCR ref [w:oN] and @x,y coordinates for 'Save'. "
            "Only click the OCR ref if idleSeconds >= 120 and real input is enabled; otherwise skip clicking to avoid stealing the user's mouse. "
            "Close the window."
        ),
        verify=lambda s, w, r: (
            _any_result_has(s, 'via: "ocr"') and _any_result_has(s, 'text "Save" @'),
            "OCR [w:oN] @x,y detected without stealing mouse",
        ),
    ),
    "27": dict(
        targets=["turbo_fixture.exe"],
        prompt=(
            f"Launch {fx}. Minimize it with window_control(action='minimize'), then restore it with window_control(action='restore'), "
            "set 'Full name' to 'Restored', read 'Full name' back to verify, and close the window."
        ),
        verify=lambda s, w, r: (
            "Restored" in r.get("final", "") and _any_result_has(s, "Restored") and not r.get("errors"),
            "minimized, restored, and filled Full name",
        ),
    ),
    "28": dict(
        targets=["turbo_fixture.exe"],
        preset="balanced",
        approver="deny_then_allow",
        prompt=(
            f"Launch {fx}. Set 'Full name' to 'Approved'. Click 'Submit' once: if denied by approval, inspect text to confirm nothing was submitted, "
            "then click 'Submit' a second time and read the Result text to confirm 'Submitted: Approved'. Close the window."
        ),
        verify=lambda s, w, r: (
            "Submitted: Approved" in r.get("final", "")
            and _has_audit(s, lambda e: e.get("event") == "approval_decision" and e.get("decision") == "deny")
            and _has_audit(s, lambda e: e.get("event") == "approval_decision" and e.get("decision") == "allow"),
            "Balanced approval deny then allow verified",
        ),
    ),
    "29": dict(
        targets=["turbo_fixture.exe"],
        prompt=(
            f"Launch {fx}. Inspect mode='all' to confirm the 'Password' edit box is marked [password:protected] with no value shown. "
            "Attempt act(action='read') and act(action='type', text='hunter2') on 'Password' and verify both are denied. "
            "Take a screenshot of the window, report all results, and close the window."
        ),
        verify=lambda s, w, r: (
            _any_result_has(s, "[password:protected]")
            and _has_audit(s, lambda e: e.get("event") == "denied" and e.get("rule") == "password-field")
            and any(c.get("tool") == "screenshot" for c in _calls_list(s)),
            "password-field protected + denied + screenshot captured",
        ),
    ),
    "30": dict(
        targets=["turbo_fixture.exe"],
        stop_mid_batch=True,
        prompt=(
            f"Launch {fx}. Using ONE batch_actions call run these 3 steps in order: "
            "1) click 'Count 0'; 2) wait_for text 'Zzz never' timeout=25; 3) click 'Count 1'. "
            "After batch_actions returns, try window_control(action='close') on the window and report the exact batch response and close result."
        ),
        verify=lambda s, w, r: _verify_stop_task(s),
    ),
}


def _check_png_dims(p: Path, want_w: int, want_h: int) -> tuple[bool, str]:
    if not p.exists():
        return False, f"missing {p}"
    from PIL import Image
    with Image.open(p) as im:
        return (im.size == (want_w, want_h), f"png size={im.size}")


def _prepare_t12_png(p: Path) -> Path:
    _clean_dir(p.parent.name)
    t3_png = WORK_ROOT / "t3" / "canvas.png"
    if t3_png.exists():
        shutil.copy2(t3_png, p)
        return p
    from PIL import Image
    Image.new("RGB", (800, 600), (40, 120, 180)).save(p, "PNG")
    return p


def _verify_stop_task(state: Path) -> tuple[bool, str]:
    ap = state / "audit.jsonl"
    if not ap.exists():
        return False, "missing audit.jsonl"
    ok, n, msg = sec.verify_chain(ap)
    stopped_res = _any_result_has(state, '"stopped":true')
    return (ok and n >= 2 and stopped_res, f"chain=({ok},{n},{msg}) stopped={stopped_res}")


# Validate every task at import time so non-allowlisted targets fail fast.
for _tid, _task in TASKS.items():
    validate_task(_task)


_PRE: dict[str, set[int]] = {}


def _pids(image: str) -> set[int]:
    out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {image}", "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout
    return {int(l.split(",")[1].strip('"')) for l in out.splitlines() if l.startswith('"') and image.lower() in l.lower()}


def _start_approver(state: Path, mode: str, stop_ev: threading.Event):
    decisions = ["deny", "allow"] if mode == "deny_then_allow" else ["allow"]
    idx = [0]
    handled = set()

    def loop():
        appr_dir = state / "approvals"
        while not stop_ev.is_set():
            (state / sec.APPROVER_ALIVE).write_text(str(time.time()), encoding="utf-8")
            if appr_dir.exists():
                for req in sorted(appr_dir.glob("*.req.json")):
                    aid = req.name.split(".")[0]
                    dec_path = appr_dir / f"{aid}.decision"
                    if aid not in handled and not dec_path.exists():
                        handled.add(aid)
                        d = decisions[min(idx[0], len(decisions) - 1)]
                        idx[0] += 1
                        dec_path.write_text(d, encoding="utf-8")
            stop_ev.wait(0.15)

    threading.Thread(target=loop, daemon=True).start()


def _start_stop_watcher(state: Path, stop_ev: threading.Event):
    def loop():
        audit = state / "audit.jsonl"
        end = time.time() + 120
        while not stop_ev.is_set() and time.time() < end:
            if audit.exists() and '"Count 0"' in audit.read_text(encoding="utf-8", errors="ignore"):
                time.sleep(1.5)
                (state / "STOP").write_text("field-stop", encoding="utf-8")
                return
            stop_ev.wait(0.2)

    threading.Thread(target=loop, daemon=True).start()


def run(tid: str) -> dict:
    t = TASKS[tid]
    if refuses(t):
        res = {"task": tid, "status": "refused-session-restore"}
        _log(res)
        return res
    validate_task(t)

    _PRE["calc"] = _pids("CalculatorApp.exe")
    state = Path(tempfile.mkdtemp(prefix=f"field-t{tid}-", dir=OUT))
    work = WORK_ROOT / t.get("work_sub", f"t{tid}")
    work.mkdir(parents=True, exist_ok=True)
    if callable(t.get("setup")):
        t["setup"](work)

    prompt = t["prompt"].replace("{{work}}", str(work)).replace("{work}", str(work))
    allow_real = bool(t.get("ime_or_input")) and winsys.idle_seconds() >= 120 and winsys.on_input_desktop()
    env = {
        **os.environ,
        "TURBO_DESKTOP_STATE_DIR": str(state),
        "TURBO_DESKTOP_AUDIT": str(state / "audit.jsonl"),
        "TURBO_DESKTOP_PRESET": t.get("preset", "easy"),
        "TURBO_DESKTOP_APPROVAL_TIMEOUT": "10",
        "TURBO_DESKTOP_NO_INDICATOR": "1",
        "PYTHONUTF8": "1",
        "PYTHONPATH": str(ROOT / "src"),
        "TURBO_DESKTOP_REQUIRE_CLEAN": "1",
        "TURBO_DESKTOP_NO_INPUT": "0" if allow_real else "1",
        "TURBO_DESKTOP_CONFIG": str(state / "none.toml"),
    }
    mcp_env = {k: env[k] for k in (
        "TURBO_DESKTOP_STATE_DIR", "TURBO_DESKTOP_AUDIT", "TURBO_DESKTOP_PRESET",
        "TURBO_DESKTOP_APPROVAL_TIMEOUT", "TURBO_DESKTOP_NO_INDICATOR", "PYTHONUTF8",
        "PYTHONPATH", "TURBO_DESKTOP_REQUIRE_CLEAN", "TURBO_DESKTOP_NO_INPUT", "TURBO_DESKTOP_CONFIG",
    )}
    cfg = {"mcpServers": {"turbo-desktop": {
        "command": str(ROOT / ".venv" / "Scripts" / "python.exe"),
        "args": ["-m", "turbo_desktop"],
        "env": mcp_env,
    }}}
    cfgp = state / "mcp.json"
    cfgp.write_text(json.dumps(cfg), encoding="utf-8")
    cwd = tempfile.mkdtemp(prefix="field-cwd-")

    bg_stop = threading.Event()
    if t.get("approver"):
        _start_approver(state, t["approver"], bg_stop)
    if t.get("stop_mid_batch"):
        _start_stop_watcher(state, bg_stop)

    cmd = [
        CLAUDE, "-p", prompt,
        "--mcp-config", str(cfgp), "--strict-mcp-config",
        "--output-format", "stream-json", "--verbose",
        "--model", "haiku", "--max-turns", "25",
        "--permission-mode", "bypassPermissions",
        "--disallowedTools", "Bash,Read,Write,Edit,Glob,Grep,WebFetch,WebSearch,Task,Agent,NotebookEdit,PowerShell",
    ]
    run_env = {**os.environ, "ENABLE_TOOL_SEARCH": "false"}
    t0 = time.time()
    timed_out = False
    try:
        p = subprocess.run(cmd, cwd=cwd, env=run_env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=300, stdin=subprocess.DEVNULL)
        stdout_text = p.stdout or ""
        rc = p.returncode
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        raw_out = exc.stdout or ""
        stdout_text = raw_out.decode("utf-8", "replace") if isinstance(raw_out, bytes) else raw_out
        rc = -1
    finally:
        bg_stop.set()
    wall = time.time() - t0

    calls, result_chars, final, usage, errors = [], 0, "", {}, []
    cost_usd, num_turns = None, None
    names = {}
    for line in stdout_text.splitlines():
        try:
            ev = json.loads(line)
        except Exception:
            continue
        if ev.get("type") == "assistant":
            for b in ev.get("message", {}).get("content", []):
                if b.get("type") == "tool_use":
                    calls.append({"tool": b["name"].replace("mcp__turbo-desktop__", ""), "input": b["input"]})
                    names[b["id"]] = len(calls) - 1
        elif ev.get("type") == "user":
            for b in ev.get("message", {}).get("content", []):
                if b.get("type") == "tool_result":
                    c = b.get("content")
                    txt = c if isinstance(c, str) else "".join(x.get("text", "") for x in c if isinstance(x, dict))
                    result_chars += len(txt)
                    i = names.get(b.get("tool_use_id"))
                    if i is not None:
                        calls[i]["result"] = txt[:2000]
                        if _is_tool_error(txt):
                            errors.append({"call": calls[i]["tool"], "input": calls[i]["input"], "result": txt[:300]})
        elif ev.get("type") == "result":
            final = ev.get("result", "")
            usage = ev.get("usage", {})
            cost_usd = ev.get("total_cost_usd")
            num_turns = ev.get("num_turns")

    if timed_out:
        errors.append({"call": "subprocess", "input": {}, "result": "claude timed out after 300s"})

    (state / "transcript.json").write_text(json.dumps(calls, ensure_ascii=False, indent=1), encoding="utf-8")
    res = {
        "task": tid,
        "targets": list(t["targets"]),
        "status": "timeout" if timed_out else "ran",
        "calls": len(calls),
        "turns": num_turns,
        "result_chars": result_chars,
        "approx_result_tokens": result_chars // 4,
        "wall_s": round(wall, 1),
        "cost_usd": cost_usd,
        "usage": {k: usage.get(k) for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")},
        "final": final[:900],
        "errors": errors[:6],
        "tools": [c["tool"] for c in calls],
        "state_dir": str(state),
    }

    audit_path = state / "audit.jsonl"
    if audit_path.exists():
        res["audit_chain"] = list(sec.verify_chain(audit_path))
    if timed_out:
        passed, detail = False, "claude timed out after 300s"
    elif callable(t.get("verify")):
        passed, detail = t["verify"](state, work, res)
    else:
        passed, detail = (not errors and rc == 0), "no errors"
    res["passed"] = bool(passed)
    res["verify_detail"] = detail

    _cleanup(t)
    _log(res)
    return res


def _cleanup(t: dict):
    """Close only our fixture executables and CalculatorApp instances started during this task."""
    for n in ("turbo_fixture.exe", "turbo_editor.exe", "turbo_canvas.exe"):
        subprocess.run(["taskkill", "/IM", n, "/F"], capture_output=True)
    if t.get("kill") == "CalculatorApp":
        for pid in _pids("CalculatorApp.exe") - _PRE.get("calc", set()):
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)


def _log(res: dict):
    with open(OUT / "results.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(res, ensure_ascii=False) + "\n")
    print(json.dumps(res, ensure_ascii=False, indent=1), flush=True)


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "tests"))
    import locking

    raw_args = sys.argv[1:]
    tids = [str(i) for i in range(1, 31)] if (not raw_args or raw_args == ["all"] or raw_args == ["--all"]) else raw_args
    for tid in tids:
        locking.acquire("desktop-mcp-field")
        try:
            run(tid)
        finally:
            locking.release()
