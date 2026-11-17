"""Claude Code permission prompts, approved from the phone or on the PC.

A Claude Code PermissionRequest hook (hub/scripts/cc_permission_hook.py) posts the prompt here. The hub shows it on
the phone as a normal approval (push notification included) and the hook shows a small dialog on the PC. Whichever
side answers first wins; the other side closes. There is no decision timeout: a request only goes away when someone
answers it or when the hook that asked is gone (the owner answered in Claude Code itself, pressed Esc, or the
session ended). The hook proves it is still waiting by long-polling; when it stops polling for `stale_seconds`, the
request is withdrawn and the phone card closes.
"""
from __future__ import annotations

import asyncio
import json
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePath

DETAIL_MAX = 1500


def _clip(s: str, n: int) -> str:
    s = s if isinstance(s, str) else json.dumps(s, ensure_ascii=False)
    return s if len(s) <= n else s[: n - 1] + "…"


def describe(payload: dict) -> dict:
    """What the phone and the PC dialog show: action key, short control line, longer detail."""
    tool = str(payload.get("tool_name") or "?")
    inp = payload.get("tool_input") or {}
    if not isinstance(inp, dict):
        inp = {"input": inp}
    action, control, detail = "use_tool", tool, ""
    if tool in ("Bash", "PowerShell"):
        cmd = str(inp.get("command") or "")
        action, control = "run_command", _clip(cmd.strip().splitlines()[0] if cmd.strip() else "", 120)
        detail = cmd
        if inp.get("description"):
            detail = f"{inp['description']}\n\n{cmd}"
    elif tool in ("Edit", "MultiEdit", "Write", "NotebookEdit"):
        path = str(inp.get("file_path") or inp.get("notebook_path") or "")
        action, control = "edit_file", PurePath(path).name or path
        if tool == "Write":
            detail = f"{path}\n\n{inp.get('content') or ''}"
        elif tool == "Edit":
            detail = f"{path}\n\n- {inp.get('old_string') or ''}\n+ {inp.get('new_string') or ''}"
        else:
            detail = f"{path}\n\n{json.dumps(inp, ensure_ascii=False)}"
    elif tool in ("WebFetch", "WebSearch"):
        action = "web"
        control = str(inp.get("url") or inp.get("query") or tool)
        detail = json.dumps(inp, ensure_ascii=False)
    else:
        detail = json.dumps(inp, ensure_ascii=False, indent=1)
    cwd = str(payload.get("cwd") or "")
    project = PurePath(cwd).name if cwd else ""
    return {"tool": tool, "action": action, "control": _clip(control or tool, 120),
            "window": f"Claude Code · {project}" if project else "Claude Code",
            "detail": _clip(detail, DETAIL_MAX), "cwd": cwd}


@dataclass
class CCRequest:
    id: str
    pc_key: str
    info: dict
    created: float
    last_seen: float
    pollers: int = 0
    by: str | None = None
    decision: str | None = None   # allow | deny | stop | withdrawn
    done: asyncio.Event = field(default_factory=asyncio.Event)


class CCPermissions:
    def __init__(self, manager, audit, *, stale_seconds: float = 20.0, monotonic=time.monotonic):
        self.m, self.audit, self.stale, self.mono = manager, audit, stale_seconds, monotonic
        self.reqs: dict[str, CCRequest] = {}

    # ---------------------------------------------------------------- create / decide
    async def create(self, payload: dict) -> CCRequest:
        info = describe(payload)
        ap = await self.m.add_external_approval(
            {"tool": info["tool"], "window": info["window"], "control": info["control"], "action": info["action"],
             "detail": info["detail"], "source": "claude_code"})
        now = self.mono()
        r = CCRequest(ap.id, secrets.token_urlsafe(18), info, now, now)
        self.reqs[r.id] = r
        self.audit.append("cc_permission_requested", {"approval": r.id, "tool": info["tool"], "control": info["control"],
                                                      "cwd": info["cwd"], "session": str(payload.get("session_id") or "")[:12]})
        asyncio.create_task(self._watch(r, ap))
        return r

    async def _watch(self, r: CCRequest, ap) -> None:
        decision = await ap.future
        r.decision = r.decision or decision
        r.by = r.by or ("pc" if decision == "withdrawn" else "phone")
        self.audit.append("cc_permission_resolved", {"approval": r.id, "decision": r.decision, "by": r.by})
        await self.m.emit({"type": "approval_resolved", "approval_id": r.id, "decision": r.decision, "by": r.by})
        r.done.set()

    def decide_pc(self, rid: str, key: str, decision: str) -> str:
        r = self.reqs.get(rid)
        if r is None:
            return "unknown"
        if not secrets.compare_digest(key, r.pc_key):
            return "forbidden"
        if decision not in ("allow", "deny", "withdrawn"):
            raise ValueError("decision must be allow, deny or withdrawn")
        ap = self.m.approvals.get(rid)
        if ap is None or ap.decision is not None:
            return "already"
        r.by = "pc"
        r.decision = decision
        self.m._decide(ap, decision)
        return "ok"

    # ---------------------------------------------------------------- long-poll from the hook
    async def wait(self, rid: str, key: str, timeout: float) -> dict | None:
        r = self.reqs.get(rid)
        if r is None or not secrets.compare_digest(key, r.pc_key):
            return None
        r.pollers += 1
        r.last_seen = self.mono()
        try:
            try:
                await asyncio.wait_for(r.done.wait(), timeout)
            except asyncio.TimeoutError:
                pass
        finally:
            r.pollers -= 1
            r.last_seen = self.mono()
        return {"decision": r.decision, "by": r.by}

    def reap(self) -> list[str]:
        """Withdraw requests whose hook stopped polling (answered in Claude Code, Esc, session closed)."""
        gone = []
        now = self.mono()
        for rid, r in list(self.reqs.items()):
            if r.done.is_set():
                if now - r.last_seen > 300:
                    self.reqs.pop(rid, None)
                continue
            if r.pollers == 0 and now - r.last_seen > self.stale:
                ap = self.m.approvals.get(rid)
                if ap is not None and ap.decision is None:
                    r.decision, r.by = "withdrawn", "claude-code"
                    self.m._decide(ap, "withdrawn")
                    gone.append(rid)
        return gone

    async def run(self) -> None:
        while True:
            await asyncio.sleep(min(2.0, self.stale / 2))
            self.reap()


def load_or_create_token(data_dir: Path) -> str:
    """Narrow local token for the hook only (it cannot pair, read events or approve phone tasks)."""
    from . import dpapi
    p = Path(data_dir) / "cc_hook_token.dpapi"
    if p.exists():
        return dpapi.unprotect(p.read_bytes()).decode()
    tok = secrets.token_urlsafe(32)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_bytes(dpapi.protect(tok.encode()))
    tmp.replace(p)
    return tok
