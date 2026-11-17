"""Task manager: runs one agent task at a time, streams events, gates dangerous actions behind owner approval."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import secrets
import time
from dataclasses import dataclass, field
from typing import Callable

from . import classifier as classifier_mod
from .audit import AuditLog
from .runners import AgentRunner, RunnerFactory


@dataclass
class Approval:
    id: str
    task_id: str
    event: dict
    expires_at: float
    future: asyncio.Future
    decision: str | None = None  # allow | deny | timeout | stop


@dataclass
class Task:
    id: str
    text: str
    status: str = "running"  # running | done | failed | stopped
    started_at: float = 0.0
    finished_at: float | None = None
    token: str = field(default_factory=lambda: secrets.token_urlsafe(24))
    usage: dict = field(default_factory=lambda: _blank_usage())
    live: dict = field(default_factory=dict)   # message id -> usage seen so far (deduplicated)


class TaskManager:
    def __init__(self, audit: AuditLog, runner_factory: RunnerFactory, *, approval_timeout: float = 120.0,
                 clock: Callable[[], float], approval_required: Callable[[dict], bool] | None = None,
                 thumbs_dir=None, system_state=None, usage_path=None,
                 engine: str = "hub"):
        self.engine = engine
        self.on_stop = lambda stopped: None
        self.on_takeover = lambda active: None   # bridge hook: RELEASE file for the desktop MCP
        self.paused = False
        self._resume_evt = asyncio.Event()
        self._resume_evt.set()
        self.input_lock: dict = {"locked": False}
        self.indicator_external = False   # True once desktop-mcp writes indicator.json: then it decides
        self.indicator = "idle"      # idle | acting | input_locked (from desktop-mcp via the bridge)
        self.audit = audit
        self.runner_factory = runner_factory
        self.approval_timeout = approval_timeout
        self.clock = clock
        self.approval_required = approval_required or classifier_mod.approval_required
        self.thumbs_dir = thumbs_dir
        self.system_state = system_state      # async () -> dict | None  (desktop-mcp system_state)
        self.usage_path = usage_path
        self.session_usage = _blank_usage()
        self.daily_usage: dict[str, dict] = {}
        if usage_path and usage_path.exists():
            try:
                self.daily_usage = json.loads(usage_path.read_text("utf-8"))
            except ValueError:
                pass
        self.tasks: dict[str, Task] = {}
        self.events: list[dict] = []
        self.approvals: dict[str, Approval] = {}
        self.stopped = False
        self._subs: set[asyncio.Queue] = set()
        self._runner: AgentRunner | None = None
        self._asyncio_task: asyncio.Task | None = None
        self._seq = 0

    # ------------------------------------------------------------ events
    async def emit(self, ev: dict) -> dict:
        self._seq += 1
        ev = {"seq": self._seq, "ts": round(self.clock(), 3), **ev}
        self.events.append(ev)
        if len(self.events) > 5000:
            del self.events[:1000]
        for q in list(self._subs):
            q.put_nowait(ev)
        return ev

    def events_since(self, since: int) -> list[dict]:
        return [e for e in self.events if e["seq"] > since]

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    # ------------------------------------------------------------ tasks
    @property
    def agent_pid(self):
        return getattr(self._runner, "pid", None)

    def running_task(self) -> Task | None:
        return next((t for t in self.tasks.values() if t.status == "running"), None)

    async def start_task(self, text: str, device_id: str) -> Task:
        if self.stopped:
            raise RuntimeError("stopped")
        if self.running_task():
            raise ValueError("a task is already running")
        warnings = await self._check_pc()
        task = Task(id="t" + secrets.token_hex(4), text=text, started_at=self.clock())
        self.tasks[task.id] = task
        self.audit.append("task_start", {"task": task.id, "device": device_id, "text": text[:500]})
        await self.emit({"type": "task_started", "task_id": task.id, "text": text})
        for w in warnings:
            await self.emit({"type": "warning", "task_id": task.id, "text": w})
        self._runner = self.runner_factory()   # zero-arg factory; passing the Task broke `serve --runner fake` (field bug)
        self._asyncio_task = asyncio.create_task(self._run(task, self._runner))
        return task

    async def _run(self, task: Task, runner: AgentRunner) -> None:
        async def emit(ev: dict) -> None:
            ev = {**ev, "task_id": task.id}
            if ev["type"] == "usage_delta":
                task.live[ev["mid"]] = ev["usage"]
                total = {k: sum(u.get(k, 0) for u in task.live.values()) for k in ("input", "output", "cache_read", "cache_create")}
                await self.emit({"type": "usage", "task_id": task.id, "usage": total})
                return
            await self.emit(ev)
            if ev["type"] == "final" and ev.get("usage"):
                self.record_usage(task, ev["usage"])
            if ev["type"] in ("tool_result", "final"):
                self.audit.append(ev["type"], {"task": task.id, "tool": ev.get("tool"), "ok": ev.get("ok"),
                                               "summary": str(ev.get("summary") or ev.get("text") or "")[:200]})

        async def gate(call: dict) -> bool:
            return await self.gate(task.id, call, emit)

        status = "failed"
        try:
            status = await runner.run(task.id, task.text, emit, gate)
        except asyncio.CancelledError:
            status = "stopped"
        except Exception as exc:  # runner crashed
            await emit({"type": "final", "text": f"runner error: {exc}", "ok": False})
        finally:
            if task.status == "running":
                task.status = "stopped" if self.stopped else status
            task.finished_at = self.clock()
            self.audit.append("task_end", {"task": task.id, "status": task.status})
            if not self.indicator_external and not self.input_lock.get("locked"):
                await self.set_indicator("idle")
            await self.emit({"type": "task_finished", "task_id": task.id, "status": task.status,
                             "usage": task.usage, "session_usage": self.session_usage,
                             "day_usage": self.daily_usage.get(_today(self.clock()), _blank_usage())})

    async def _check_pc(self) -> list[str]:
        """Refuse when the PC is locked; warn on low battery. Unknown state (no provider/failure) never blocks."""
        if self.system_state is None:
            return []
        try:
            st = await asyncio.wait_for(self.system_state(), 10) or {}
        except Exception:
            return ["Could not read PC state (system_state unavailable)."]
        if st.get("locked"):
            raise PcLocked("The PC is locked. Unlock it first, then send the task again.")
        warns = []
        if st.get("on_battery") and st.get("battery_percent") is not None and st["battery_percent"] < 20:
            warns.append(f"PC is on battery at {st['battery_percent']}%.")
        if st.get("display_off"):
            warns.append("PC display is off.")
        return warns

    def record_usage(self, task: Task, usage: dict) -> None:
        day = self.daily_usage.setdefault(_today(self.clock()), _blank_usage())
        for bucket in (task.usage, self.session_usage, day):
            for k in ("input", "output", "cache_read", "cache_create"):
                bucket[k] += int(usage.get(k, 0))
            bucket["cost_usd"] = round(bucket["cost_usd"] + float(usage.get("cost_usd", 0.0)), 6)
            bucket["tasks"] += 1
        if self.usage_path:
            self.usage_path.write_text(json.dumps(self.daily_usage), "utf-8")

    # ------------------------------------------------------------ gate + approvals
    async def gate(self, task_id: str, call: dict, emit=None) -> bool:
        emit = emit or (lambda ev: self.emit({**ev, "task_id": task_id}))
        if self.paused and not self.stopped:      # owner took over: hold the agent until the phone resumes
            await self._resume_evt.wait()
        if self.stopped:
            self.audit.append("action_blocked", {"task": task_id, "tool": call.get("tool"), "why": "stopped"})
            return False
        await emit({"type": "tool_call", "tool": call.get("tool"), "window": call.get("window"),
                    "control": call.get("control"), "action": call.get("action")})
        if not self.input_lock.get("locked") and not self.indicator_external:
            await self.set_indicator("acting")      # derived from tool calls when desktop-mcp writes no indicator.json
        if self.engine == "desktop-mcp" and str(call.get("tool", "")).startswith("mcp__desktop"):
            needs = False   # desktop-mcp classifies with real control names and asks through the bridge itself
        else:
            needs = classifier_mod_safe(self.approval_required, call)
        if not needs:
            self.audit.append("action", {"task": task_id, "tool": call.get("tool"), "window": call.get("window"),
                                         "control": call.get("control"), "action": call.get("action"),
                                         "approval": None})
            return True
        approval = await self._ask(task_id, call, emit)
        return approval.decision == "allow"

    async def _ask(self, task_id: str, call: dict, emit) -> Approval:
        aid = "a" + secrets.token_hex(4)
        crop = call.get("crop_png_b64")
        crop_hash = None
        if crop:
            raw = base64.b64decode(crop)
            crop_hash = hashlib.sha256(raw).hexdigest()
            if self.thumbs_dir:
                (self.thumbs_dir / f"{aid}.png").write_bytes(raw)
        ap = Approval(aid, task_id, call, self.clock() + self.approval_timeout,
                      asyncio.get_running_loop().create_future())
        self.approvals[aid] = ap
        self.audit.append("approval_requested", {"approval": aid, "task": task_id, "tool": call.get("tool"),
                                                 "window": call.get("window"), "control": call.get("control"),
                                                 "action": call.get("action"), "crop_sha256": crop_hash})
        await emit({"type": "approval_request", "approval_id": aid, "tool": call.get("tool"),
                    "window": call.get("window"), "control": call.get("control"), "action": call.get("action"),
                    "crop_png_b64": crop, "expires_at": ap.expires_at})
        try:
            await asyncio.wait_for(asyncio.shield(ap.future), self.approval_timeout)
        except asyncio.TimeoutError:
            self._decide(ap, "timeout")
        except asyncio.CancelledError:   # STOP cancelled the task while the owner was still deciding
            self._decide(ap, "stop")
            self.audit.append("approval_resolved", {"approval": aid, "decision": "stop", "tool": call.get("tool")})
            await emit({"type": "approval_resolved", "approval_id": aid, "decision": "stop"})
            raise
        decision = ap.decision or "deny"
        self.audit.append("approval_resolved", {"approval": aid, "decision": decision, "tool": call.get("tool"),
                                                "control": call.get("control")})
        await emit({"type": "approval_resolved", "approval_id": aid, "decision": decision})
        return ap

    def _decide(self, ap: Approval, decision: str) -> bool:
        if ap.decision is not None:
            return False
        ap.decision = decision
        if not ap.future.done():
            ap.future.set_result(decision)
        return True

    def pending_approvals(self) -> list[Approval]:
        return [a for a in self.approvals.values() if a.decision is None]

    def resolve(self, approval_id: str, decision: str) -> str:
        """Returns 'ok', 'unknown' or 'already'."""
        ap = self.approvals.get(approval_id)
        if ap is None:
            return "unknown"
        if decision not in ("allow", "deny"):
            raise ValueError("decision must be allow or deny")
        return "ok" if self._decide(ap, decision) else "already"

    # ------------------------------------------------------------ STOP
    async def stop(self, device_id: str) -> None:
        self.stopped = True
        self._resume_evt.set()
        self.on_stop(True)
        self.audit.append("stop", {"device": device_id})
        for ap in self.pending_approvals():
            self._decide(ap, "stop")
        if self._runner:
            await self._runner.kill()
        t = self._asyncio_task
        if t and not t.done():
            t.cancel()
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        await self.emit({"type": "stopped"})

    async def takeover(self, device_id: str) -> None:
        """'Take over': release the input lock now and pause the run (the next tool call waits until resume)."""
        self.paused = True
        self._resume_evt.clear()
        self.on_takeover(True)
        self.audit.append("takeover", {"device": device_id})
        await self.emit({"type": "taken_over"})

    async def set_input_lock(self, state: dict) -> None:
        if state != self.input_lock:
            self.input_lock = state
            self.audit.append("input_lock", {k: state.get(k) for k in ("locked", "mode", "reason")})
            await self.emit({"type": "input_lock", **state})

    async def set_indicator(self, state: str) -> None:
        if state not in ("idle", "acting", "input_locked"):
            state = "idle"
        if state != self.indicator:
            self.indicator = state
            await self.emit({"type": "indicator", "state": state})

    async def resume(self, device_id: str) -> None:
        if self.paused:
            self.paused = False
            self._resume_evt.set()
            self.on_takeover(False)
        self.stopped = False
        self.on_stop(False)
        self.audit.append("resume", {"device": device_id})
        await self.emit({"type": "resumed"})


class PcLocked(Exception):
    pass


def _blank_usage() -> dict:
    return {"input": 0, "output": 0, "cache_read": 0, "cache_create": 0, "cost_usd": 0.0, "tasks": 0}


def _today(ts: float) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(ts))


def classifier_mod_safe(fn: Callable[[dict], bool], call: dict) -> bool:
    try:
        return bool(fn(call))
    except Exception:
        return True  # fail closed


def _takes_task(factory) -> bool:
    import inspect
    try:
        return len(inspect.signature(factory).parameters) >= 1
    except (TypeError, ValueError):
        return False
