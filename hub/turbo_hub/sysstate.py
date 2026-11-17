"""Reads PC state (locked, display off, idle, on battery) by calling desktop-mcp's `system_state` tool over stdio MCP.

Returns None from the provider when no desktop MCP is configured, so tests and the fake runner are not blocked.
Not exercised against the real desktop-mcp here (another agent is adding the tool); the JSON-RPC exchange is
unit-tested with a stub server script.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path


async def call_mcp_tool(command: str, args: list[str], env: dict | None, tool: str, arguments: dict | None = None,
                        timeout: float = 15) -> dict | None:
    proc = await asyncio.create_subprocess_exec(
        command, *args, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL, env={**os.environ, **(env or {})})

    async def rpc(mid: int | None, method: str, params: dict) -> dict | None:
        msg = {"jsonrpc": "2.0", "method": method, "params": params}
        if mid is not None:
            msg["id"] = mid
        proc.stdin.write((json.dumps(msg) + "\n").encode())
        await proc.stdin.drain()
        if mid is None:
            return None
        while True:
            line = await proc.stdout.readline()
            if not line:
                return None
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if obj.get("id") == mid:
                return obj

    async def go() -> dict | None:
        await rpc(1, "initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                                    "clientInfo": {"name": "turbo-hub", "version": "0.1"}})
        await rpc(None, "notifications/initialized", {})
        res = await rpc(2, "tools/call", {"name": tool, "arguments": arguments or {}})
        if not res or "result" not in res:
            return None
        for c in res["result"].get("content", []):
            if c.get("type") == "text":
                try:
                    return json.loads(c["text"])
                except ValueError:
                    return None
        return res["result"].get("structuredContent")

    try:
        return await asyncio.wait_for(go(), timeout)
    finally:
        if proc.returncode is None:
            proc.kill()


def mcp_system_state(mcp_config_path: str | None, extra_env: dict | None = None):
    """Build the async provider from an MCP config that has a server named 'desktop'."""
    if not mcp_config_path or not Path(mcp_config_path).exists():
        return None
    srv = json.loads(Path(mcp_config_path).read_text("utf-8")).get("mcpServers", {}).get("desktop")
    if not srv:
        return None

    async def provider() -> dict | None:
        return await call_mcp_tool(srv["command"], srv.get("args", []), {**(srv.get("env") or {}), **(extra_env or {})}, "system_state")

    return provider
