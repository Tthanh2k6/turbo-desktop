"""Regression for field bug 1: tools called through the real MCP stdio server (worker thread) must work.
Direct engine calls passed while every inspect through MCP failed with a blank 'Error executing tool'."""
import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from conftest import ROOT, _state

EXPECTED = {"windows_list", "inspect_compact", "act", "batch_actions", "launch_app", "wait_for", "window_control",
            "screenshot", "system_state"}


def _text(res):
    return "".join(c.text for c in res.content if getattr(c, "text", None))


async def _session_run(fn):
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONUTF8": "1"}
    params = StdioServerParameters(command=sys.executable, args=["-m", "turbo_desktop"], env=env)
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            return await fn(s)


def test_tools_list_and_full_loop_over_stdio(launch_app):
    d = launch_app("turbo_fixture.exe")

    async def go(s):
        tools = {t.name for t in (await s.list_tools()).tools}
        assert EXPECTED <= tools
        snap = _text(await s.call_tool("inspect_compact", {"window": "TurboFixture"}))
        assert '<Button> "Submit"' in snap
        r = json.loads(_text(await s.call_tool("act", {"window": "TurboFixture", "name": "Full name",
                                                       "action": "set_value", "text": "Via MCP"})))
        assert r["ok"] and r["via"] == "pattern"
        b = json.loads(_text(await s.call_tool("batch_actions", {
            "window": "TurboFixture", "steps": [{"action": "click", "name": "Count 0"}], "returnSnapshot": True})))
        assert b["ok"] and "Count 1" in b["snapshot"]
        st = json.loads(_text(await s.call_tool("system_state", {})))
        assert "idleSeconds" in st
        bad = json.loads(_text(await s.call_tool("act", {"window": "TurboFixture", "name": "Password", "action": "type", "text": "x"})))
        assert bad["ok"] is False and bad["denied"] is True and bad["rule"] == "password-field"
        shot = await s.call_tool("screenshot", {"window": "TurboFixture"})
        assert any(getattr(c, "type", "") == "image" for c in shot.content)

    asyncio.run(_session_run(go))
