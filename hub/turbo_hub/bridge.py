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
    def __init__(self, manager, state_dir: Path, clock, activity=lambda: 0.0, alive_seconds: float = 12.0,
                 remote_task="whole_task", max_task_minutes=15):
        self.m, self.dir, self.clock, self.activity, self.alive_seconds = manager, state_dir, clock, activity, alive_seconds
        self.remote_task = remote_task
        self.max_task_minutes = max_task_minutes
        self._last_hb: float = 0.0
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
        self.m.on_task_start = self.on_task_start
        self.m.on_task_end = self.on_task_end
        self.set_stop(manager.stopped)

    def _remote_mode(self) -> str:
        return str(self.remote_task() if callable(self.remote_task) else self.remote_task)

    def _max_minutes(self) -> int:
        return int(self.max_task_minutes() if callable(self.max_task_minutes) else self.max_task_minutes)

    def write_task_active(self, task) -> None:
        if getattr(task, "source", "phone") != "phone" or self._remote_mode() != "whole_task":
            return
        now = self.clock()
        self._last_hb = now
        self.dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "task": task.id,
            "since": task.started_at,
            "heartbeat": now,
            "source": "phone",
            "max_minutes": self._max_minutes(),
        }
        tmp = self.dir / "task_active.json.tmp"
        tmp.write_text(json.dumps(payload), "utf-8")
        tmp.replace(self.dir / "task_active.json")

    def clear_task_active(self) -> None:
        for name in ("task_active.json", "task_active.json.tmp"):
            f = self.dir / name
            try:
                if f.exists():
                    f.unlink()
            except OSError:
                pass

    def on_task_start(self, task) -> None:
        self.write_task_active(task)

    def on_task_end(self, _task) -> None:
        self.clear_task_active()

    def set_stop(self, stopped: bool) -> None:
        f = self.dir / "STOP"
        if stopped:
            f.write_text("stop", "utf-8")
            self.clear_task_active()
        elif f.exists():
            f.unlink()

    def set_release(self, active: bool) -> None:
        f = self.dir / "RELEASE"
        if active:
            f.write_text("takeover", "utf-8")
            self.clear_task_active()
        else:
            if f.exists():
                f.unlink()
            if (t := self.m.running_task()) and not self.m.stopped:
                self.write_task_active(t)

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

    async def step(self) -> None:
        self.touch_alive()
        took_over = self.dir / "owner_took_over.json"
        if took_over.exists():
            try:
                took_over.unlink()
            except OSError:
                pass
            self.clear_task_active()
            await self.m.takeover("pc-owner")
        task = self.m.running_task()
        if task and getattr(task, "source", "phone") == "phone" and not self.m.paused and not self.m.stopped:
            if self._remote_mode() == "whole_task":
                now = self.clock()
                max_m = self._max_minutes()
                if max_m > 0 and now - task.started_at >= max_m * 60:
                    self.clear_task_active()
                    await self.m.takeover("max_task_minutes", reason="max_task_minutes")
                elif now - self._last_hb >= 5.0:
                    self.write_task_active(task)
            else:
                self.clear_task_active()
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

    async def run(self) -> None:
        while True:
            await self.step()
            await asyncio.sleep(0.1)
