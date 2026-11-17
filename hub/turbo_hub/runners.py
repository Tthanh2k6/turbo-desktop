"""Agent runners. The hub only talks to the AgentRunner protocol, so tests use FakeRunner and never start claude."""
from __future__ import annotations

import asyncio
import glob
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Awaitable, Callable, Protocol

from .summaries import render_en, summary_parts

EmitFn = Callable[[dict], Awaitable[None]]
GateFn = Callable[[dict], Awaitable[bool]]  # True = allowed (after any approval)

# 1x1 transparent PNG, stand-in for the control crop in tests
TINY_PNG_B64 = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


class AgentRunner(Protocol):
    async def run(self, task_id: str, text: str, emit: EmitFn, gate: GateFn) -> str:
        """Run the task. Return 'done' or 'failed'. Must call gate() for every tool call before 'executing' it."""

    async def kill(self) -> None: ...


RunnerFactory = Callable[[], AgentRunner]


class FakeRunner:
    """Scripted runner for tests and emulator demos. Never touches the desktop or claude."""

    def __init__(self, script: list[dict] | None = None, step_delay: float = 0.02):
        self.script = script
        self.step_delay = step_delay
        self.killed = False
        self.executed: list[dict] = []   # tool calls that were allowed and "ran"
        self.denied: list[dict] = []
        self._task: asyncio.Task | None = None

    def demo_script(self) -> list[dict]:
        """Slow, realistic stream for screenshots and demos (no desktop is touched)."""
        def call(tool, key, args, summary, work=0.0, control=None, action=None):
            return {"type": "tool_call", "tool": tool, "input": {}, "window": "Calculator", "control": control, "action": action,
                    "work": work, "summary": summary, "sum": {"k": key, "a": args}}
        return [
            {"type": "text", "text": "Plan: open Calculator, enter 12.5 + 7, then multiply by 3."},
            call("mcp__desktop__launch_app", "opened", ["Calculator", "w3"], "Opened Calculator (w3)", work=4.0),
            {"type": "raw", "event": {"type": "usage_delta", "mid": "m1", "usage": {"input": 1800, "output": 120}}},
            call("mcp__desktop__inspect_compact", "read_controls", [38], "Read 38 controls", work=0.5),
            call("mcp__desktop__act", "acted", ["click", "Equals", "pattern"], "Clicked 'Equals' via UIA", work=2.0, control="Equals", action="click"),
            {"type": "raw", "event": {"type": "usage_delta", "mid": "m2", "usage": {"input": 900, "output": 260}}},
            {"type": "tool_call", "tool": "mcp__desktop__act", "input": {"action": "click", "name": "Send"}, "window": "Mail - Compose",
             "control": "Send", "action": "click", "crop_png_b64": TINY_PNG_B64, "summary": "Clicked 'Send' via UIA",
             "sum": {"k": "acted", "a": ["click", "Send", "pattern"]}},
            {"type": "final", "text": "The display shows 58.5.", "usage": {"input": 2700, "output": 380, "cost_usd": 0.0041}},
        ]

    def default_script(self, text: str) -> list[dict]:
        if text.startswith("demo"):
            return self.demo_script()
        if "hang" in text:
            return [{"type": "text", "text": "working..."}, {"type": "sleep", "s": 60}]
        return [
            {"type": "text", "text": f"Plan: {text}"},
            {"type": "tool_call", "tool": "mcp__desktop__inspect_compact",
             "input": {"window": "Calculator"}, "window": "Calculator", "control": None, "action": "inspect"},
            {"type": "tool_call", "tool": "mcp__desktop__act",
             "input": {"action": "click", "name": "Send"}, "window": "Mail - Compose",
             "control": "Send", "action": "click", "crop_png_b64": TINY_PNG_B64},
            {"type": "final", "text": "Finished the scripted task.",
             "usage": {"input": 1000, "output": 200, "cost_usd": 0.01}},
        ]

    async def run(self, task_id: str, text: str, emit: EmitFn, gate: GateFn) -> str:
        self._task = asyncio.current_task()
        try:
            for step in self.script if self.script is not None else self.default_script(text):
                await asyncio.sleep(self.step_delay)
                if self.killed:
                    return "failed"
                kind = step["type"]
                if kind == "sleep":
                    await asyncio.sleep(step["s"])
                elif kind == "text":
                    await emit({"type": "text", "text": step["text"]})
                elif kind == "raw":
                    await emit(step["event"])
                elif kind == "final":
                    await emit({"type": "final", "text": step["text"], "ok": True, "usage": step.get("usage")})
                elif kind == "tool_call":
                    call = {k: v for k, v in step.items() if k != "type"}
                    if await gate(call):
                        self.executed.append(call)
                        await asyncio.sleep(step.get("work", 0))   # the tool is "running": lets screenshots catch the acting state
                        res = {"type": "tool_result", "tool": call["tool"], "ok": True, "summary": step.get("summary", "ok")}
                        if "sum" in step:
                            res["sum"] = step["sum"]
                        await emit(res)
                    else:
                        self.denied.append(call)
                        await emit({"type": "tool_result", "tool": call["tool"], "ok": False,
                                    "summary": "denied by owner"})
            return "done"
        except asyncio.CancelledError:
            return "failed"

    async def kill(self) -> None:
        self.killed = True
        if self._task and not self._task.done():
            self._task.cancel()


# ---------------------------------------------------------------- real claude headless

def find_claude() -> str | None:
    home = Path(os.environ.get("USERPROFILE") or Path.home())
    pats = [str(home / ".vscode" / "extensions" / "anthropic.claude-code-*" / "resources" / "native-binary" / "claude.exe"),
            str(home / ".vscode" / "extensions" / "anthropic.claude-code-*" / "**" / "claude.exe")]
    found: list[str] = []
    for p in pats:
        found += glob.glob(p, recursive=True)
    return sorted(found)[-1] if found else None


def map_stream_json(obj: dict) -> list[dict]:
    """Translate one claude stream-json line into hub events (tool_call/tool_result/text/final)."""
    out: list[dict] = []
    t = obj.get("type")
    if t == "assistant":
        msg = obj.get("message") or {}
        mu = msg.get("usage")
        if mu and msg.get("id"):
            out.append({"type": "usage_delta", "mid": msg["id"], "usage": {
                "input": int(mu.get("input_tokens", 0)), "output": int(mu.get("output_tokens", 0)),
                "cache_read": int(mu.get("cache_read_input_tokens", 0)), "cache_create": int(mu.get("cache_creation_input_tokens", 0))}})
        for block in (obj.get("message") or {}).get("content", []) or []:
            if block.get("type") == "text" and block.get("text"):
                out.append({"type": "text", "text": block["text"]})
            elif block.get("type") == "tool_use":
                out.append({"type": "tool_call_seen", "tool": block.get("name"), "input": block.get("input", {}),
                            "tool_use_id": block.get("id")})
    elif t == "user":
        for block in (obj.get("message") or {}).get("content", []) or []:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                content = block.get("content")
                if isinstance(content, list):
                    content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
                out.append({"type": "tool_result", "tool_use_id": block.get("tool_use_id"),
                            "ok": not block.get("is_error", False), "summary": str(content or "")[:300],
                            "full": str(content or "")[:30000]})
    elif t == "result":
        u = obj.get("usage") or {}
        usage = {"input": int(u.get("input_tokens", 0)), "output": int(u.get("output_tokens", 0)),
                 "cache_read": int(u.get("cache_read_input_tokens", 0)),
                 "cache_create": int(u.get("cache_creation_input_tokens", 0))}
        if obj.get("total_cost_usd") is not None:
            usage["cost_usd"] = float(obj["total_cost_usd"])
        out.append({"type": "final", "text": str(obj.get("result", "")), "ok": not obj.get("is_error", False),
                    "usage": usage})
    return out


APPROVAL_TOOL = "mcp__turbohub__approve"


def fill_command(template: list[str], **values: str) -> list[str]:
    out = []
    for part in template:
        for k, v in values.items():
            part = part.replace("{" + k + "}", v)
        out.append(part)
    return out


def build_claude_command(claude: str, mcp_config_path: str, template: list[str] | None = None) -> list[str]:
    """One long-lived process per session: follow-up tasks are extra user messages on stdin (no cold start)."""
    tpl = template or [claude, "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
                       "--mcp-config", "{mcp_config}", "--strict-mcp-config", "--tools", "",
                       "--permission-prompt-tool", "{approval_tool}"]
    return fill_command(tpl, mcp_config=mcp_config_path, approval_tool=APPROVAL_TOOL)


def user_frame(text: str) -> bytes:
    return (json.dumps({"type": "user", "message": {"role": "user", "content": text}}) + "\n").encode()


async def _spawn_real(cmd: list[str]):
    # screenshots arrive as one huge JSON line: the default 64 KB line limit made the runner crash (field bug)
    return await asyncio.create_subprocess_exec(*cmd, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                                                stderr=asyncio.subprocess.DEVNULL, limit=64 * 1024 * 1024)


class ClaudeRunner:
    """Keeps ONE `claude -p --input-format stream-json` process alive across tasks and restarts it if it died.
    Every tool use is routed through the hub via the turbohub MCP shim (approval_mcp.py) used as
    --permission-prompt-tool, so the classifier and the phone decide before execution.
    `spawn` is injectable so the framing is unit-tested with a fake process; the real claude is NOT started by
    the automated tests (it would spend the owner's quota): see scripts/smoke_real.ps1."""

    def __init__(self, hub_url: str, internal_token: str, extra_mcp_config: str | None = None,
                 claude_path: str | None = None, spawn=None, command: list[str] | None = None,
                 server_env: dict | None = None):
        self.server_env = server_env or {}
        self.command = command or None
        self.hub_url, self.internal_token = hub_url, internal_token
        self.extra_mcp_config = extra_mcp_config
        self.claude_path = claude_path or find_claude()
        self.spawn = spawn or _spawn_real
        self.proc = None
        self._calls: dict = {}
        self.spawn_count = 0

    def write_mcp_config(self) -> str:
        servers: dict = {}
        if self.extra_mcp_config and Path(self.extra_mcp_config).exists():
            servers.update(json.loads(Path(self.extra_mcp_config).read_text("utf-8")).get("mcpServers", {}))
        if "desktop" in servers:   # tell desktop-mcp where the hub bridge lives and which preset to apply
            servers["desktop"] = {**servers["desktop"], "env": {**servers["desktop"].get("env", {}), **self.server_env}}
        shim = str(Path(__file__).with_name("approval_mcp.py"))
        servers["turbohub"] = {"command": sys.executable, "args": [shim],
                               "env": {"TURBO_HUB_URL": self.hub_url, "TURBO_TASK_TOKEN": self.internal_token}}
        fd, path = tempfile.mkstemp(prefix="turbo-hub-mcp-", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"mcpServers": servers}, f)
        return path

    async def _ensure(self):
        if self.proc is None or self.proc.returncode is not None:
            self.proc = await self.spawn(build_claude_command(self.claude_path or "claude", self.write_mcp_config(), self.command))
            self.spawn_count += 1
            if getattr(self.proc, "pid", None) and self.spawn is _spawn_real:
                from . import reaper
                reaper.bind_to_hub_lifetime(self.proc.pid)   # agent dies with the hub, even on a hard kill
        return self.proc

    async def run(self, task_id: str, text: str, emit: EmitFn, gate: GateFn) -> str:
        if not self.claude_path and self.spawn is _spawn_real:
            await emit({"type": "final", "text": "claude.exe not found", "ok": False})
            return "failed"
        proc = await self._ensure()
        proc.stdin.write(user_frame(text))
        await proc.stdin.drain()
        while True:
            raw = await proc.stdout.readline()
            if not raw:  # process died mid-task: next task gets a fresh one
                self.proc = None
                await emit({"type": "final", "text": "agent process ended unexpectedly", "ok": False})
                return "failed"
            try:
                obj = json.loads(raw)
            except ValueError:
                continue
            for ev in map_stream_json(obj):
                if ev["type"] == "tool_call_seen":
                    self._calls[ev.get("tool_use_id")] = (ev.get("tool"), ev.get("input") or {})
                    continue   # the permission tool (gate) emits the one tool_call event; do not show it twice
                if ev["type"] == "tool_result":
                    tool, inp = self._calls.pop(ev.get("tool_use_id"), (None, {}))
                    ev["tool"] = tool
                    key, args = summary_parts(tool, inp, ev.pop("full", ev.get("summary", "")))
                    ev["summary"] = render_en(key, args)
                    ev["sum"] = {"k": key, "a": args}
                await emit(ev)
                if ev["type"] == "final":
                    return "done" if ev.get("ok", True) else "failed"

    @property
    def pid(self):
        return getattr(self.proc, "pid", None)

    async def kill(self) -> None:
        proc, self.proc = self.proc, None
        if proc is not None and proc.returncode is None:
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)


def line_to_event(line: str, parser: str) -> dict | None:
    line = line.rstrip("\r\n")
    if not line.strip():
        return None
    if parser == "jsonl":
        try:
            obj = json.loads(line)
        except ValueError:
            return {"type": "text", "text": line}
        for k in ("text", "message", "content", "result", "delta"):
            if isinstance(obj, dict) and isinstance(obj.get(k), str):
                return {"type": "text", "text": obj[k]}
        return {"type": "text", "text": line[:500]}
    return {"type": "text", "text": line}


class GenericRunner:
    """Any CLI agent (Codex, Gemini CLI, a local model...): one process per task, stdout lines become events.
    The hub cannot gate tool calls of a CLI that has no permission hook; STOP and the audit log still apply."""

    def __init__(self, command: list[str], parser: str = "text"):
        self.command, self.parser = command, parser
        self.proc = None

    async def run(self, task_id: str, text: str, emit: EmitFn, gate: GateFn) -> str:
        cmd = fill_command(self.command, task=text)
        try:
            self.proc = await asyncio.create_subprocess_exec(
                *cmd, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT, limit=64 * 1024 * 1024)
        except OSError as exc:
            await emit({"type": "final", "text": f"cannot start agent: {exc}", "ok": False})
            return "failed"
        from . import reaper
        reaper.bind_to_hub_lifetime(self.proc.pid)
        last = ""
        async for raw in self.proc.stdout:
            ev = line_to_event(raw.decode("utf-8", "replace"), self.parser)
            if ev:
                last = ev["text"]
                await emit(ev)
        rc = await self.proc.wait()
        await emit({"type": "final", "text": last if rc == 0 else f"agent exited with code {rc}", "ok": rc == 0})
        return "done" if rc == 0 else "failed"

    async def kill(self) -> None:
        if self.proc and self.proc.returncode is None:
            subprocess.run(["taskkill", "/PID", str(self.proc.pid), "/T", "/F"], capture_output=True)
