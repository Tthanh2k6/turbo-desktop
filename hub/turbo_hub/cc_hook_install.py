"""Add or remove the Claude Code PermissionRequest hook in a Claude Code settings file (default ~/.claude/settings.json).

Only our own entry is touched; every other setting and hook is kept. A backup is written next to the file first.
"""
from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

MARK = "cc_permission_hook.py"
TIMEOUT_SECONDS = 7 * 24 * 3600   # "no timeout": the hook waits for the owner; Claude Code needs a number


def hook_command() -> str:
    hub = Path(__file__).resolve().parents[1]
    py = Path(sys.executable)
    if py.parent.name.lower() != "scripts":   # not running from the venv: use the hub venv
        py = hub / ".venv" / "Scripts" / "python.exe"
    script = hub / "scripts" / MARK
    return f'"{py.as_posix()}" "{script.as_posix()}"'


def default_settings_path() -> Path:
    return Path.home() / ".claude" / "settings.json"


def _load(p: Path) -> dict:
    if not p.exists():
        return {}
    txt = p.read_text("utf-8").strip()
    return json.loads(txt) if txt else {}


def _save(p: Path, data: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        shutil.copy2(p, p.with_name(p.name + f".bak-{time.strftime('%Y%m%d-%H%M%S')}"))
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", "utf-8")
    tmp.replace(p)


def _strip(groups: list) -> list:
    out = []
    for g in groups:
        hooks = [h for h in (g.get("hooks") or []) if MARK not in str(h.get("command", ""))]
        if hooks:
            out.append({**g, "hooks": hooks})
    return out


def install(p: Path | None = None) -> Path:
    p = p or default_settings_path()
    data = _load(p)
    hooks = data.setdefault("hooks", {})
    groups = _strip(hooks.get("PermissionRequest") or [])
    groups.append({"matcher": "*", "hooks": [{"type": "command", "command": hook_command(),
                                              "timeout": TIMEOUT_SECONDS}]})
    hooks["PermissionRequest"] = groups
    _save(p, data)
    return p


def uninstall(p: Path | None = None) -> Path:
    p = p or default_settings_path()
    data = _load(p)
    hooks = data.get("hooks") or {}
    groups = _strip(hooks.get("PermissionRequest") or [])
    if groups:
        hooks["PermissionRequest"] = groups
    else:
        hooks.pop("PermissionRequest", None)
    if not hooks:
        data.pop("hooks", None)
    _save(p, data)
    return p


def installed(p: Path | None = None) -> bool:
    data = _load(p or default_settings_path())
    return any(MARK in str(h.get("command", "")) for g in (data.get("hooks") or {}).get("PermissionRequest") or []
               for h in g.get("hooks") or [])
