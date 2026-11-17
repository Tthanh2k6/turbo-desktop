"""One short, human line per tool result for the phone's live view (raw JSON-in-JSON is unreadable on a small screen).

`summary_parts` returns a language-neutral (key, args) so the phone can localise it from string resources;
`summarize` renders the same thing in English for logs, the CLI and as the fallback text sent with the event.
"""
from __future__ import annotations

import json
import re

_VERBS_EN = {"click": "Clicked", "invoke": "Invoked", "type": "Typed into", "set_value": "Set", "select": "Selected",
             "toggle": "Toggled", "expand": "Expanded", "focus": "Focused", "scroll": "Scrolled", "press_keys": "Pressed keys in"}


def _unwrap(text: str):
    """FastMCP wraps results as {"result": "<json or text>"}; return (parsed_json_or_None, plain_text)."""
    plain = text
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and isinstance(obj.get("result"), str):
            plain = obj["result"]
            try:
                return json.loads(plain), plain
            except ValueError:
                return None, plain
        return obj, text
    except ValueError:
        return None, plain


def _excerpt(plain: str, lines: int = 2, width: int = 80) -> str:
    flat = re.sub(r"\s+", " ", plain).strip()
    out = [flat[i:i + width] for i in range(0, min(len(flat), lines * width), width)]
    return "\n".join(out) + ("…" if len(flat) > lines * width else "")


def summary_parts(tool: str | None, inp: dict | None, text: str) -> tuple[str, list]:
    """Keys: opened(title,id) acted(action,label,via) read_controls(n) read_window ran_steps(n,ok) screenshot
    listed_windows(n) read_state waited wait_timeout failed(error) text(excerpt)."""
    name = (tool or "").split("__")[-1]
    inp = inp or {}
    data, plain = _unwrap(text or "")
    d = data if isinstance(data, dict) else {}
    if d and d.get("ok") is False and d.get("error"):
        return "failed", [_excerpt(str(d["error"]))]
    if name == "launch_app" and d.get("windows"):
        w = d["windows"][0]
        return "opened", [w.get("title", "?"), w.get("id", "?")]
    if name == "act" and d:
        return "acted", [str(inp.get("action", "click")), str(inp.get("name") or inp.get("ref") or "control"), str(d.get("via") or "pattern")]
    if name == "inspect_compact":
        n = len(re.findall(r"^\[w\d+:e\d+\]", plain, re.M))
        return ("read_controls", [n]) if n else ("read_window", [])
    if name == "batch_actions" and isinstance(d.get("steps"), list):
        steps = d["steps"]
        return "ran_steps", [len(steps), sum(1 for s in steps if s.get("ok"))]
    if name == "screenshot":
        return "screenshot", []
    if name == "windows_list" and isinstance(d.get("windows"), list):
        return "listed_windows", [len(d["windows"])]
    if name == "system_state":
        return "read_state", []
    if name == "wait_for":
        return ("waited", []) if d.get("ok", True) else ("wait_timeout", [])
    return "text", [_excerpt(plain)]


def render_en(key: str, args: list) -> str:
    if key == "opened":
        return f"Opened {args[0]} ({args[1]})"
    if key == "acted":
        via = {"pattern": "UIA", "input": "real input"}.get(args[2], args[2])
        return f"{_VERBS_EN.get(args[0], 'Acted on')} '{args[1]}' via {via}"
    if key == "read_controls":
        return f"Read {args[0]} controls"
    if key == "read_window":
        return "Read the window"
    if key == "ran_steps":
        return f"Ran {args[0]} steps ({args[1]} ok)"
    if key == "screenshot":
        return "Took a screenshot"
    if key == "listed_windows":
        return f"Listed {args[0]} windows"
    if key == "read_state":
        return "Read PC state"
    if key == "waited":
        return "Waited"
    if key == "wait_timeout":
        return "Wait timed out"
    if key == "failed":
        return "Failed: " + args[0]
    return args[0] if args else ""


def summarize(tool: str | None, inp: dict | None, text: str) -> str:
    return render_en(*summary_parts(tool, inp, text))
