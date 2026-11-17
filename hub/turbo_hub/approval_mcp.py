"""Minimal stdio MCP server used as claude's --permission-prompt-tool (tool name: mcp__turbohub__approve).

Claude calls approve({tool_name, input, tool_use_id}); we forward to the hub (loopback, per-task token),
which runs the classifier and, if needed, waits for the phone. No third-party dependencies.
"""
import json
import os
import sys
import urllib.request

HUB = os.environ.get("TURBO_HUB_URL", "http://127.0.0.1:8750")
TOKEN = os.environ.get("TURBO_TASK_TOKEN", "")

TOOL = {
    "name": "approve",
    "description": "Ask the hub whether a tool call may run.",
    "inputSchema": {"type": "object", "properties": {"tool_name": {"type": "string"}, "input": {"type": "object"},
                                                     "tool_use_id": {"type": "string"}},
                    "required": ["tool_name", "input"]},
}


def ask_hub(args: dict) -> dict:
    req = urllib.request.Request(HUB + "/internal/approve", data=json.dumps(args).encode(),
                                 headers={"Content-Type": "application/json", "X-Task-Token": TOKEN})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.load(r)
    except Exception as exc:  # fail closed
        return {"behavior": "deny", "message": f"hub unreachable: {exc}"}


def handle(msg: dict) -> dict | None:
    mid, method = msg.get("id"), msg.get("method")
    if method == "initialize":
        result = {"protocolVersion": msg.get("params", {}).get("protocolVersion", "2024-11-05"),
                  "capabilities": {"tools": {}}, "serverInfo": {"name": "turbohub", "version": "0.1"}}
    elif method == "tools/list":
        result = {"tools": [TOOL]}
    elif method == "tools/call":
        decision = ask_hub(msg["params"].get("arguments", {}))
        result = {"content": [{"type": "text", "text": json.dumps(decision)}]}
    elif mid is None:
        return None  # notification
    else:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "method not found"}}
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def main() -> None:
    for line in sys.stdin:
        if not line.strip():
            continue
        out = handle(json.loads(line))
        if out is not None:
            sys.stdout.write(json.dumps(out) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
