"""Dangerous-action interface.

The real classifier lives in desktop-mcp (another agent builds it). The hub only needs one function:

    approval_required(event: dict) -> bool

`event` is one MCP tool call seen in Claude Code's stream-json output (or handed to the permission
prompt tool). Keys the hub looks at:
    tool     full tool name, e.g. "mcp__desktop__act"
    input    the tool arguments (dict)
    window   optional, window title the MCP resolved for the target
    control  optional, control name/label the MCP resolved
    action   optional, e.g. "click", "invoke", "type", "press_keys"
    process  optional, owning process name

To connect the real classifier later, set TURBO_CLASSIFIER="package.module:function" and the hub
will import that function instead of the stub below. It must never raise; if it does, the hub fails
closed (approval required).
"""
from __future__ import annotations

import importlib
import os
import re
from typing import Callable

Classifier = Callable[[dict], bool]

_DANGEROUS_WORDS = re.compile(
    r"\b(send|g[uư]i|gửi|delete|xo[aá]|xoá|pay|thanh to[aá]n|buy|install|uninstall|format|shut ?down|"
    r"sign ?out|submit|post|publish|confirm)\b", re.I)
_DANGEROUS_PROCS = re.compile(r"^(powershell|pwsh|cmd|windowsterminal|wt|regedit|taskmgr|conhost)(\.exe)?$", re.I)
_ACTING = {"click", "invoke", "press_keys", "toggle", "select", "set_value", "type"}


def stub_approval_required(event: dict) -> bool:
    """Conservative placeholder: keyword match on the control name plus a few fixed process rules."""
    tool = str(event.get("tool", ""))
    if not tool.startswith("mcp__desktop") and "desktop" not in tool:
        return False  # not a desktop action (reads, other MCPs)
    inp = event.get("input") or {}
    action = str(event.get("action") or inp.get("action") or "")
    if action and action not in _ACTING:
        return False
    if _DANGEROUS_PROCS.match(str(event.get("process") or "")):
        return True
    label = " ".join(str(x) for x in (event.get("control"), inp.get("name"), inp.get("ref_name"),
                                      inp.get("text") if action == "click" else "") if x)
    if _DANGEROUS_WORDS.search(label):
        return True
    keys = str(inp.get("keys", "")).lower()
    return action == "press_keys" and keys in {"enter", "{enter}", "return"} and \
        bool(re.search(r"mail|chat|messenger|zalo|compose", str(event.get("window") or ""), re.I))


def load_classifier() -> Classifier:
    spec = os.environ.get("TURBO_CLASSIFIER", "").strip()
    fn: Classifier = stub_approval_required
    if spec:
        mod, _, name = spec.partition(":")
        fn = getattr(importlib.import_module(mod), name or "approval_required")

    def safe(event: dict) -> bool:
        try:
            return bool(fn(event))
        except Exception:
            return True  # fail closed

    return safe


approval_required: Classifier = load_classifier()
