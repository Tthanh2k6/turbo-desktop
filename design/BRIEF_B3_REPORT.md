# Brief B3: hub report endpoint (Python)

Read design/LIVE_V3.md, especially section F, then hub/turbo_hub/{app.py,manager.py,audit.py,store.py} and hub/tests (style, conftest). You can only read and edit files; you cannot run commands. The PM runs the tests.

Add `GET /report?days=1|7|30` (dependency `in_session`, signed reply like the other endpoints). It returns:
```
{"days": [{"date": "2026-11-17", "done": 3, "failed": 0, "stopped": 1, "seconds": 412}, ...],   // one per day, oldest first, zero days included
 "totals": {"done", "failed", "stopped", "seconds", "tokensIn", "tokensOut", "costUsd"},
 "topApps": [{"name": "Zalo", "count": 5}, ...]}                                            // max 5
```

Data sources:
- Task records the manager already keeps: start, end, status and usage. If they are not persisted across restarts, persist a small `tasks.jsonl` in the data dir with one line per finished task: `{id, start, end, status, usage, apps}`. Cap it at 90 days.
- `apps` comes from the task's `mcp__desktop__launch_app` tool calls and the window titles in `act` and `inspect_compact` calls. Use the process or app name when available, otherwise the last segment of the title after " - ". Never store typed text or tool inputs other than the app name.

Tests: empty report; two tasks on two days; topApps ordering; `days` param validation (anything else returns 400); requires a session.

Do not touch android/, desktop-mcp/, design/, or the signing and pairing code. Final answer: changed files, tests, anything unfinished. Under 150 words.
