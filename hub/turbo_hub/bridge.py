"""Hub side of desktop-mcp's file contract (see desktop-mcp/src/turbo_desktop/security.py):

  <state>/approver.alive         touched every few seconds while a phone (or the local CLI) is connected
  <state>/approvals/<id>.req.json   written by the MCP when its own rules say "ask"; we show it to the owner
  <state>/approvals/<id>.decision   we write "allow" or "deny"
  <state>/STOP                   created on STOP, removed on resume: blocks every action inside the MCP

The MCP classifies actions itself (it knows control names; the hub only sees tool names and element refs), so with
approval.engine = "desktop-mcp" (default) the hub does not second-guess desktop tools and just relays the question.
"""
from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path


class DesktopBridge:
    def __init__(self, manager, state_dir: Path, clock, activity=lambda: 0.0, alive_seconds: float = 12.0):
        self.m, self.dir, self.clock, self.activity, self.alive_seconds = manager, state_dir, clock, activity, alive_seconds
        (self.dir / "approvals").mkdir(parents=True, exist_ok=True)
        # Field bug: requests left by a previous run (MCP killed, hub restarted) showed up as phantom approvals.
        stale = self.dir / "approvals" / "stale"
        for old in (self.dir / "approvals").glob("*.req.json"):
            stale.mkdir(exist_ok=True)
            old.replace(stale / old.name)
        self.handled: set[str] = set()
        self.task: asyncio.Task | None = None
        self.m.on_stop = self.set_stop
        self.m.on_takeover = self.set_release
        self.set_stop(manager.stopped)

    def set_stop(self, stopped: bool) -> None:
        f = self.dir / "STOP"
        if stopped:
            f.write_text("stop", "utf-8")
        elif f.exists():
            f.unlink()

    def set_release(self, active: bool) -> None:
        f = self.dir / "RELEASE"
        if active:
            f.write_text("takeover", "utf-8")
        elif f.exists():
            f.unlink()

    def read_lock(self) -> dict:
        """<state>/input_lock.json is written by desktop-mcp: {"locked": bool, "mode": ..., "since": epoch, "reason": ...}"""
        try:
            d = json.loads((self.dir / "input_lock.json").read_text("utf-8"))
            return {"locked": bool(d.get("locked")), "mode": d.get("mode"), "since": d.get("since"),
                    "max_seconds": d.get("max_seconds"), "reason": d.get("reason")}
        except (OSError, ValueError):
            return {"locked": False}

    def read_indicator(self, lock: dict) -> str:
        """<state>/indicator.json is written by desktop-mcp: {"state": "idle" | "acting" | "input_locked"}.
        If the MCP only writes input_lock.json, a locked input implies input_locked; a running task implies acting."""
        if lock.get("locked"):
            return "input_locked"
        try:
            st = json.loads((self.dir / "indicator.json").read_text("utf-8")).get("state", "idle")
            return st if st in ("idle", "acting", "input_locked") else "idle"
        except (OSError, ValueError):
            return None   # no file: the hub derives acting/idle from tool calls

    def touch_alive(self) -> None:
        if self.clock() - self.activity() < self.alive_seconds:
            (self.dir / "approver.alive").write_text(str(self.clock()), "utf-8")

    def summary_to_call(self, req: dict) -> dict:
        crop = None
        thumb = req.get("thumb")
        for cand in (thumb if isinstance(thumb, list) else [thumb]):
            try:
                if cand and Path(str(cand)).is_file():
                    crop = base64.b64encode(Path(str(cand)).read_bytes()).decode()
                    break
            except OSError:
                pass
        return {"tool": "desktop-mcp", "window": req.get("window"), "control": req.get("control"),
                "action": req.get("action"), "reason": req.get("reason"), "rule": req.get("rule"), "crop_png_b64": crop}

    async def handle(self, path: Path) -> None:
        req = json.loads(path.read_text("utf-8"))
        task = self.m.running_task()
        tid = task.id if task else "none"
        if self.m.stopped:
            decision = "deny"
        else:
            async def emit(ev):
                await self.m.emit({**ev, "task_id": tid})
            ap = await self.m._ask(tid, self.summary_to_call(req), emit)
            decision = "allow" if ap.decision == "allow" else "deny"
        (self.dir / "approvals" / f"{req['id']}.decision").write_text(decision, "utf-8")

    async def run(self) -> None:
        while True:
            self.touch_alive()
            lock = self.read_lock()
            await self.m.set_input_lock(lock)
            ind = self.read_indicator(lock)
            self.m.indicator_external = (self.dir / "indicator.json").exists()
            if ind is not None:
                await self.m.set_indicator(ind)
            for p in sorted((self.dir / "approvals").glob("*.req.json")):
                if p.name not in self.handled:
                    self.handled.add(p.name)
                    asyncio.create_task(self.handle(p))
            await asyncio.sleep(0.25)
