# Brief: hub fixes from the 18/11 audit (backend)

You can only read and edit files; you cannot run commands. The PM runs the tests and sends failures back. Do not read .env files. Do not touch `android/`, `desktop-mcp/`, `design/`.

Read first: `design/AUDIT_DEM_18-11.md` (rows referenced below), then each file before editing. Match the existing style. Add or update tests in `hub/tests/` for every behaviour change (look at `hub/tests/conftest.py` and existing tests for the `Env` fixture pattern).

## Fix
1. Row 1: `TaskManager._check_pc` must read the real keys from desktop-mcp `system_state` (`sessionLocked`, `secureDesktopActive`, `onBattery`, `batteryPercent`, `displayOff`) and keep accepting the old snake_case keys. A locked PC or a UAC/secure desktop refuses the task as today's `locked` does. Test both key styles.
2. Row 7: `TaskManager.gate` (or the `/internal/approve` route) fills `window`, `control` (`name`, else `ref`) and `action` from `call["input"]` when they are missing at the top level, so the audit and the live `tool_call` events are not null. Test it.
3. Row 11: `summaries.py` handles the plain-text `windows_list` result (count non-empty lines that look like window lines) and returns `listed_windows`. Row 30 (hub part only): use `inp.get("window") or ""` instead of the word "control"; a `launch_app` result with `pending: true` and no windows becomes a short "Waiting for <matched>" style summary (add a key, e.g. `launch_pending`, with an English render and keep the Vietnamese render pattern used in the file). Tests in `hub/tests/test_tasks.py` style.
4. Row 13: when a task ends without a `final` event (STOP, failure), record the usage already seen in `task.live`; include `cache_read` and `cache_create` in `report()` totals as separate fields (do not change existing field meanings). Test.
5. Row 18: `revoke()` also calls `save_sessions()`; the `/events` stream stops yielding events once its session is gone (check before each yield, not only on the 15 s heartbeat). Test revoke + persist.
6. Row 19: `source(request)` trusts `Cf-Connecting-Ip` only when the TCP peer is a loopback host and `"cloudflare"` is in `settings.connections`; never attribute lockout strikes to a loopback address from a proxied request. Test.
7. Row 25: the generated MCP config file is written to a fixed path under the hub data dir (or unlinked on kill); `taskkill`/`tasklist` calls made from async code run via `asyncio.to_thread`.
8. Row 20 (hub part): explicit `argtypes`/`restype` for the Win32 calls in `hub/turbo_hub/reaper.py` and `hub/scripts/cc_permission_hook.py`.
9. Row 4: `screen.py` redaction also blacks out windows whose title is an owner-approval dialog (`claude code cần duyệt`, `claude code needs approval`, `turbo-desktop: approve action?`, case-insensitive exact title) and windows owned by a password-manager process (`bitwarden`, `keepass`, `keepassxc`, `1password`, `lastpass`, `dashlane`, `nordpass`, `roboform`, `enpass`, `protonpass`). Get the process name in `enum_windows()` via `GetWindowThreadProcessId` + `QueryFullProcessImageNameW` (ctypes, with argtypes). Keep the window dict shape backward compatible (`title`, `rect`, add `process`). Extend `test_screen.py`.
10. Row 26 (hub part): `TaskManager.history()` returns the final answer text (`answer`, ≤2000 chars) for tasks it knows, including after a restart: store it in `tasks.jsonl` next to `text`.

## Do not
- Do not change pairing, signing, session or TOTP logic beyond item 5.
- Do not weaken the hard floor (STOP, hash-chained audit, signed non-local requests, local-only pairing, secret redaction, owner-approval prompts).

## Final answer
Changed files, tests added, anything you could not do and why. Under 250 words.
