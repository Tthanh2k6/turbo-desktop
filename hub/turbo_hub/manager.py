"""Task manager: runs one agent task at a time, streams events, gates dangerous actions behind owner approval."""
from __future__ import annotations

import asyncio
import base64
import datetime
import hashlib
import json
from pathlib import Path
import re
import secrets
import time
from dataclasses import dataclass, field
from typing import Callable

from . import classifier as classifier_mod
from .audit import AuditLog
from .runners import AgentRunner, RunnerFactory

TASK_RETENTION_DAYS = 90


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
    source: str = "phone"
    token: str = field(default_factory=lambda: secrets.token_urlsafe(24))
    usage: dict = field(default_factory=lambda: _blank_usage())
    live: dict = field(default_factory=dict)   # message id -> usage seen so far (deduplicated)
    apps: list[str] = field(default_factory=list)


class TaskManager:
    def __init__(self, audit: AuditLog, runner_factory: RunnerFactory, *, approval_timeout: float = 120.0,
                 clock: Callable[[], float], approval_required: Callable[[dict], bool] | None = None,
                 thumbs_dir=None, system_state=None, usage_path=None, tasks_path=None,
                 engine: str = "hub"):
        self.engine = engine
        self.on_stop = lambda stopped: None
        self.on_takeover = lambda active: None   # bridge hook: RELEASE file for the desktop MCP
        self.on_task_start = lambda task: None
        self.on_task_end = lambda task: None
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
        self.tasks_path: Path | None = (
            Path(tasks_path) if tasks_path else (Path(usage_path).with_name("tasks.jsonl") if usage_path else None)
        )
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
        self._read_tasks_file()

    # ------------------------------------------------------------ events
    async def emit(self, ev: dict) -> dict:
        ev = dict(ev)
        ev.pop("_gated", None)
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
        source = "local" if device_id == "local-admin" else "phone"
        task = Task(id="t" + secrets.token_hex(4), text=text, started_at=self.clock(), source=source)
        self.tasks[task.id] = task
        try:
            warnings = await self._check_pc()
        except BaseException:
            self.tasks.pop(task.id, None)
            raise
        self.on_task_start(task)
        self.audit.append("task_start", {"task": task.id, "device": device_id, "text": text[:500]})
        await self.emit({"type": "task_started", "task_id": task.id, "text": text})
        for w in warnings:
            await self.emit({"type": "warning", "task_id": task.id, "text": w})
        self._runner = self.runner_factory()   # zero-arg factory; passing the Task broke `serve --runner fake` (field bug)
        self._asyncio_task = asyncio.create_task(self._run(task, self._runner))
        return task

    async def _run(self, task: Task, runner: AgentRunner) -> None:
        async def emit(ev: dict) -> None:
            ev = dict(ev)
            gated = ev.pop("_gated", False)
            ev = {**ev, "task_id": task.id}
            if not gated and ev["type"] == "tool_call":
                if app := _extract_app(ev):
                    task.apps.append(app)
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
            self.on_task_end(task)   # release the PC lock first: the report record must never delay or block it
            try:
                self._record_finished_task(task)
            except Exception as exc:  # noqa: BLE001  reporting is best effort
                import sys
                print(f"tasks.jsonl record failed: {exc!r}", file=sys.stderr)
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

    def _read_tasks_file(self) -> list[dict]:
        if not self.tasks_path or not self.tasks_path.exists():
            return []
        cutoff = self.clock() - TASK_RETENTION_DAYS * 86400
        kept: list[dict] = []
        dropped = False
        for line in self.tasks_path.read_text("utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            ts = float(rec.get("end") or rec.get("start") or 0.0)
            if ts >= cutoff:
                kept.append(rec)
            else:
                dropped = True
        if dropped:
            self._write_tasks_file(kept)
        return kept

    def _write_tasks_file(self, records: list[dict]) -> None:
        if not self.tasks_path:
            return
        self.tasks_path.parent.mkdir(parents=True, exist_ok=True)
        content = "".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in records)
        self.tasks_path.write_text(content, "utf-8")

    def _record_finished_task(self, task: Task) -> None:
        if not self.tasks_path:
            return
        records = self._read_tasks_file()
        rec = {
            "id": task.id,
            "text": task.text[:500],
            "start": round(task.started_at, 3),
            "end": round(task.finished_at if task.finished_at is not None else self.clock(), 3),
            "status": task.status,
            "usage": dict(task.usage),
            "apps": list(task.apps),
        }
        records = [r for r in records if r.get("id") != task.id] + [rec]
        cutoff = self.clock() - TASK_RETENTION_DAYS * 86400
        records = [r for r in records if float(r.get("end") or r.get("start") or 0.0) >= cutoff]
        self._write_tasks_file(records)

    def history(self, limit: int = 50) -> list[dict]:
        """Recent tasks for the phone: the ones in memory plus finished ones from tasks.jsonl (survives a hub restart)."""
        out = {t.id: {"id": t.id, "text": t.text, "status": t.status, "startedAt": int(t.started_at),
                      "finishedAt": int(t.finished_at) if t.finished_at else None} for t in self.tasks.values()}
        for r in self._read_tasks_file():
            rid = r.get("id")
            if isinstance(rid, str) and rid and rid not in out and r.get("text"):
                out[rid] = {"id": rid, "text": r["text"], "status": r.get("status", "done"),
                            "startedAt": int(float(r.get("start") or 0)),
                            "finishedAt": int(float(r["end"])) if r.get("end") else None}
        return sorted(out.values(), key=lambda x: -x["startedAt"])[:limit]

    def report(self, days: int = 7) -> dict:
        now = self.clock()
        today_date = datetime.date.fromtimestamp(now)
        day_dates = [(today_date - datetime.timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]
        by_date = {d: {"date": d, "done": 0, "failed": 0, "stopped": 0, "seconds": 0} for d in day_dates}
        file_records = self._read_tasks_file()
        by_id: dict[str, dict] = {}
        extra: list[dict] = []
        for r in file_records:
            rid = r.get("id")
            if isinstance(rid, str) and rid:
                by_id[rid] = r
            else:
                extra.append(r)
        for t in self.tasks.values():
            if t.status != "running" and t.finished_at is not None:
                by_id[t.id] = {
                    "id": t.id,
                    "start": t.started_at,
                    "end": t.finished_at,
                    "status": t.status,
                    "usage": t.usage,
                    "apps": t.apps,
                }
        records = list(by_id.values()) + extra
        tokens_in = 0
        tokens_out = 0
        cost_usd = 0.0
        app_counts: dict[str, int] = {}
        app_names: dict[str, str] = {}
        for r in records:
            start = float(r.get("start") or 0.0)
            end = float(r.get("end") if r.get("end") is not None else start)
            d = _today(start or end)
            if d not in by_date:
                continue
            status = str(r.get("status") or "")
            if status in ("done", "failed", "stopped"):
                by_date[d][status] += 1
            by_date[d]["seconds"] += int(round(max(0.0, end - start)))
            u = r.get("usage") if isinstance(r.get("usage"), dict) else {}
            tokens_in += int(u.get("input", u.get("tokensIn", 0)))
            tokens_out += int(u.get("output", u.get("tokensOut", 0)))
            cost_usd = round(cost_usd + float(u.get("cost_usd", u.get("costUsd", 0.0))), 6)
            for raw_app in r.get("apps") or []:
                if isinstance(raw_app, str) and (a := _clean_app_name(raw_app)):
                    k = a.lower()
                    app_counts[k] = app_counts.get(k, 0) + 1
                    if k not in app_names or (app_names[k].islower() and not a.islower()):
                        app_names[k] = a
        days_list = [by_date[d] for d in day_dates]
        totals = {
            "done": sum(x["done"] for x in days_list),
            "failed": sum(x["failed"] for x in days_list),
            "stopped": sum(x["stopped"] for x in days_list),
            "seconds": sum(x["seconds"] for x in days_list),
            "tokensIn": tokens_in,
            "tokensOut": tokens_out,
            "costUsd": cost_usd,
        }
        top_apps = [
            {"name": app_names[k], "count": c}
            for k, c in sorted(app_counts.items(), key=lambda x: (-x[1], x[0]))[:5]
        ]
        return {"days": days_list, "totals": totals, "topApps": top_apps}

    # ------------------------------------------------------------ gate + approvals
    async def gate(self, task_id: str, call: dict, emit=None) -> bool:
        emit = emit or (lambda ev: self.emit({**ev, "task_id": task_id}))
        if self.paused and not self.stopped:      # owner took over: hold the agent until the phone resumes
            await self._resume_evt.wait()
        if self.stopped:
            self.audit.append("action_blocked", {"task": task_id, "tool": call.get("tool"), "why": "stopped"})
            return False
        if (t := self.tasks.get(task_id)) and (app := _extract_app(call)):
            t.apps.append(app)
        await emit({"type": "tool_call", "tool": call.get("tool"), "window": call.get("window"),
                    "control": call.get("control"), "action": call.get("action"), "_gated": True})
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

    async def add_external_approval(self, ev: dict) -> Approval:
        """An approval that belongs to no hub task (a Claude Code permission prompt). It never expires; the caller
        awaits `ap.future` and announces the result."""
        aid = "c" + secrets.token_hex(4)
        ap = Approval(aid, "", dict(ev), 0.0, asyncio.get_running_loop().create_future())
        self.approvals[aid] = ap
        await self.emit({"type": "approval_request", "approval_id": aid, "tool": ev.get("tool"),
                         "window": ev.get("window"), "control": ev.get("control"), "action": ev.get("action"),
                         "detail": ev.get("detail"), "source": ev.get("source"), "crop_png_b64": None,
                         "expires_at": 0})
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

    async def takeover(self, device_id: str, reason: str | None = None) -> None:
        """'Take over': release the input lock now and pause the run (the next tool call waits until resume)."""
        self.paused = True
        self._resume_evt.clear()
        self.on_takeover(True)
        self.audit.append("takeover", {"device": device_id, **({"reason": reason} if reason else {})})
        await self.emit({"type": "taken_over", **({"reason": reason} if reason else {})})

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


def _clean_app_name(raw: str) -> str:
    s = raw.strip()
    if not s:
        return ""
    if s.lower().startswith("process:"):
        s = s[8:].strip()
    if "\\" in s or "/" in s:
        s = s.replace("/", "\\").rsplit("\\", 1)[-1].strip()
    if s.lower().endswith(".exe"):
        s = s[:-4].strip()
    return s


def _extract_app(call: dict) -> str | None:
    tool = str(call.get("tool") or "")
    short = tool.split("__")[-1]
    if short not in ("launch_app", "act", "inspect_compact"):
        return None
    inp = call.get("input") if isinstance(call.get("input"), dict) else {}
    for cand in (call.get("process"), call.get("app"), inp.get("process"), inp.get("app")):
        if isinstance(cand, str) and (cleaned := _clean_app_name(cand)):
            return cleaned
    if short == "launch_app":
        sum_args = (call.get("sum") or {}).get("a") if isinstance(call.get("sum"), dict) else None
        sum_title = sum_args[0] if isinstance(sum_args, list) and sum_args else None
        for cand in (inp.get("target"), inp.get("name"), call.get("target"), sum_title):
            if isinstance(cand, str) and (cleaned := _clean_app_name(cand)):
                return cleaned
    win = call.get("window") if isinstance(call.get("window"), str) else inp.get("window")
    if not isinstance(win, str) or not win.strip():
        return None
    w = win.strip()
    if re.fullmatch(r"w\d+", w, re.I):
        return None
    if w.lower().startswith("process:"):
        return _clean_app_name(w) or None
    seg = w.rsplit(" - ", 1)[-1].strip()
    return _clean_app_name(seg) or None


def _takes_task(factory) -> bool:
    import inspect
    try:
        return len(inspect.signature(factory).parameters) >= 1
    except (TypeError, ValueError):
        return False
