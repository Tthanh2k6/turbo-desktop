"""One short, human line per tool result for the phone's live view (raw JSON-in-JSON is unreadable on a small screen)."""
from __future__ import annotations

import json
import re

_VERBS = {"click": "Clicked", "invoke": "Invoked", "type": "Typed into", "set_value": "Set", "select": "Selected",
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


def summarize(tool: str | None, inp: dict | None, text: str) -> str:
    name = (tool or "").split("__")[-1]
    inp = inp or {}
    data, plain = _unwrap(text or "")
    d = data if isinstance(data, dict) else {}
    if d and d.get("ok") is False and d.get("error"):
        return _excerpt("Failed: " + str(d["error"]))
    if name == "launch_app" and d.get("windows"):
        w = d["windows"][0]
        return f"Opened {w.get('title', '?')} ({w.get('id', '?')})"
    if name == "act" and d:
        verb = _VERBS.get(str(inp.get("action", "click")), "Acted on")
        label = inp.get("name") or inp.get("ref") or "control"
        via = {"pattern": "UIA", "input": "real input"}.get(str(d.get("via")), d.get("via") or "UIA")
        return f"{verb} '{label}' via {via}"
    if name == "inspect_compact":
        n = len(re.findall(r"^\[w\d+:e\d+\]", plain, re.M))
        return f"Read {n} controls" if n else "Read the window"
    if name == "batch_actions" and isinstance(d.get("steps"), list):
        steps = d["steps"]
        return f"Ran {len(steps)} steps ({sum(1 for s in steps if s.get('ok'))} ok)"
    if name == "screenshot":
        return "Took a screenshot"
    if name == "windows_list" and isinstance(d.get("windows"), list):
        return f"Listed {len(d['windows'])} windows"
    if name == "system_state":
        return "Read PC state"
    if name == "wait_for":
        return "Waited" if d.get("ok", True) else "Wait timed out"
    return _excerpt(plain)
