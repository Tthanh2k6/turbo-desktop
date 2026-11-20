# Field report

Two tracks: tests prove the code does what we thought, field runs find what we did not think of.
Sections are written by whoever ran them. Rules and the task list: `FIELD_TASKS.md`.

## hub/app

Setup: the real hub (`python -m turbo_hub serve`, Balanced or Strict-style auth) with the real agent command
(`claude -p --input-format stream-json ... --model haiku`, one long-lived process) and the real desktop-mcp. The phone was
(a) a simulated phone over real HTTP (`hub/scripts/field_run.py`) and (b) the Android debug build on the Android 16
emulator over 10.0.2.2 driven by adb hooks, because the Compose UI waits for the mockup review
(`hub/scripts/emulator_run.py`). Work files: `%TEMP%\turbo-field\`. Every run takes `%TEMP%\turbo-desktop-test.lock` and closes
the windows it opened.

### Results

| Task | Result |
|---|---|
| 8 Calculator (12.5 + 7) x 3 via phone | 58.5, 4 tool calls, 18 s wall, 10 in / 819 out tokens + 104k cache read, $0.0023 (Haiku). Usage shown per task, session, day. Note: in Round 4 on an isolated `exebox` desktop (`onInputDesktop: false`), UWP `CalculatorApp.exe` launched onto `WinSta0\Default` and remained invisible to UIA enumeration from `exebox`; interactive-desktop runs pass. |
| 28/31 approval round trip (fixture Submit button, Balanced & Strict) | Request reached the phone in under 1 s with window, control and a crop. Deny: the label stayed empty, the agent reported it was blocked. Allow: label read `Submitted: Ada / / agree=False`. Answer round trip 0.00 to 0.01 s locally. Re-verified in Round 4 on `emulator-5554` (`motonav36`) under `preset = "strict"` against `turbo_fixture.exe`. |
| 31 STOP mid-task | No tool call after STOP, the agent process (pid) was gone 1 s later, a new task got 423, the audit log shows `stop`, resume cleared it. Re-verified in Round 4 on `emulator-5554` (`09-stop-state.png`). |
| 34 hub restart mid-session | While down: connection error. Requests signed before restart (millisecond `started_ms` boundary, including same-second 50 ms restarts) and old nonces return `401`. With `session.persist = false`, the in-memory session ends (`401`), APK returns to `OpenSession` (`12-task34-opensession.png`) and reopens with PIN + TOTP. With `session.persist = true`, APK and DevClient keep their sessions and detect `startedMs` change to reset SSE `lastSeq`, while pre-restart signed requests and old nonces still return `401`. |
| 31 emulator: pair + open session | Pairing, TOTP setup dismissal, and session start worked over `10.0.2.2` with the Keystore keys and the biometric prompt (device PIN on the emulator). |
| 33 network cut | Verified end to end in Round 4 (`emulator_run.py` TCP proxy `127.0.0.1:8762 <-> 127.0.0.1:8761`). During a 26.4 s mid-task proxy cut while the hub finished the task, the phone switched to `Disconnected` (`online = false`, `Hub unreachable`), emitted no fake completion, and reconciled `Done` (`Count 4`) via `/status` and `/tasks` after the proxy reopened. |
| 32 owner's phone over Tailscale | Not run: needs the owner's phone. Steps are in `hub/README.md` ("Thử trên điện thoại thật"). |

### Failures found, fixed, with a regression test

1. **Runner crashed on a screenshot result.** `Separator is found, but chunk is longer than limit`: asyncio's 64 KB line limit on the agent's stdout. Fix: 64 MB limit. Test: `test_runner_survives_a_screenshot_sized_line`.
2. **Every tool call appeared twice on the phone.** The stream-json `tool_use` and the permission-tool gate both emitted `tool_call`. Fix: only the gate emits it. Test: `test_claude_runner_reuses_process_and_restarts_after_crash`.
3. **Phantom approvals at hub start.** Request files left in `desktop-state/approvals/` by an earlier run were shown as new. Fix: they are moved to `approvals/stale/` at start. Test: `test_bridge_ignores_requests_left_by_a_previous_run`.
4. **A hard-killed hub left `claude` and desktop-mcp running** (still driving Calculator). Fixes: the agent runs in a Windows job object with KILL_ON_JOB_CLOSE; pid and image name are recorded and the leftover is reaped on the next start; clean shutdown kills it. Tests: `test_agent_dies_when_the_hub_process_is_killed`, `test_reaper_kills_leftover_agent_only_if_same_image`.
5. **Replay of a request signed before a restart** was possible for up to 60 s because nonces are in memory. Fix: requests with a timestamp before the hub start are refused. Test: `test_hub_restart_rejects_old_requests_and_needs_reopen`.
6. **Two policy sources.** The hub's own approval categories could not see real control names (it only gets tool names and refs). Fix: `approval.engine = "desktop-mcp"` (default): desktop-mcp classifies, the hub only relays its file-based approval request (`approvals/<id>.req.json` to `.decision`), `approver.alive` and `STOP`. Test: `test_desktop_mcp_bridge_files`.
7. **Pairing needs the biometric prompt too.** The pairing request is signed by both keys, so the app must run BiometricPrompt before `pair` (the debug hook did not, and failed with "User not authenticated" once the emulator had a lock screen). The pairing screen must do it.
8. **The delete task never reached an approval.** desktop-mcp correctly refused real input because the owner was using the PC. The deny path was therefore exercised with the fixture's Submit button instead.
9. Windows opened by the runs (Calculator, Notepad, fixture) were left open. Fix: before/after top-level window diff, WM_CLOSE, then kill by image only for known test apps.
10. Test runs overlapped with the desktop-mcp agent's. Fix: shared lock `%TEMP%\turbo-desktop-test.lock` (`hub/scripts/with_lock.py`, used by conftest and the field scripts).
11. A test wrote a config into the real `%APPDATA%`. Fix: the test now redirects APPDATA and HOME.

### Round 2: the real Compose app on the Android 16 emulator (adb hooks + real hub + real agent)

12. **App stayed on "Open session" after the session opened** (screens switched only on a cold start): the UI read `prefs.sessionId` (not observable). Fix: `Graph.sessionId` is a StateFlow the UI collects. Check: `design/emulator/04-tasks.png` shows the Tasks screen right after the session opens.
13. **Instrumented tests saw "No compose hierarchies"**: the notification-permission dialog took window focus. Fix: `GrantPermissionRule` in the tests.
14. **Instrumented tests assumed Vietnamese text** but the emulator is English. Fix: assertions use string resources, so they pass in both languages.
15. **Pairing from a script returned before the pairing finished** (log read too early, then the app was restarted mid-request). Fix in the field script: poll for the `pair=` line.
16. The emulator screenshot of a BiometricPrompt is black (the credential screen is FLAG_SECURE). That is normal, not a bug.
17. Airplane mode on the emulator did not reliably cut the 10.0.2.2 route: in one run the app showed offline and later reconnected only after the hub answered again, in another it never noticed the cut. Treat the network-cut check as partially verified; real devices need the 32/33 steps in the README.

### Round 3 (QA notes on the first emulator screenshots)

18. **Chip said "Ready" and the orange frame was missing while the agent worked.** The hub only relayed desktop-mcp's `indicator.json`; without it the state stayed `idle`. Fix: the hub derives `acting` from tool calls (and `idle` at the end of the task) until desktop-mcp writes the file; the phone also treats a running task as `acting`. Test: `test_live_usage_is_deduplicated_and_indicator_is_derived`.
19. **Tool results were raw escaped JSON labelled "Done".** Fix: tool results are labelled "Result", the final answer "Done", and the hub writes one short line per known tool (`Opened Calculator (w3)`, `Clicked 'Equals' via UIA`, `Read 38 controls`, `Ran 3 steps (3 ok)`), with a 2-line excerpt as fallback. Test: `test_tool_result_summaries`.
20. **"This task: 0 tokens" was wrong.** Fix: per-message usage is read from the stream-json events (deduplicated by message id), shown live, replaced by the final `result` usage; with no usage reported the phone shows a dash, never 0. Cost is shown when the agent reports it.
21. **Vietnamese screenshots** are in `design/emulator/vi/` (per-app locale `vi`); the English set is in `design/emulator/`.
22. **Field scripts must never touch the owner's windows.** `launch_app Notepad` once returned the owner's own editor window. The scripts now use Calculator and the fixture app only, never kill Notepad, and a test (`test_no_script_or_test_launches_the_owners_editor`) fails if the word appears in any script or test.

23. **`serve --runner fake` always failed** with "'Task' object is not iterable": the manager passed the Task to the runner factory (found by the mock-hub screenshots, all unit tests used lambdas). Fix: factories are zero-argument. Test: `test_default_fake_runner_factory_runs_the_demo_script`. A failed final answer is now labelled "Error", not "Done".
24. Screenshots of every screen with a scripted agent (no desktop touched, so no lock needed): `hub/scripts/emulator_shots.py` writes `design/emulator/*.png` (English) and `design/emulator/vi/*.png` (Vietnamese). They show the orange frame while acting, the solid frame plus "PC keyboard and mouse are locked" chip, the one-line tool summaries, the heads-up Deny/Allow notification, the STOP card, and live token counts.

25. **`with_lock.py -- pytest` deadlocked**: the wrapper held the lock and the suite's own conftest then waited for it forever (it cost hours of waiting before I saw it). Fix: the wrapper exports `TURBO_TEST_LOCK_OWNER`, a child of the holder counts as holding it. Test: `test_lock_wrapper_child_is_not_blocked_by_its_parent`.
26. QA round 4: after STOP the header reads "Stopped" and a red chip says "Stopped · tap Resume" (`design/emulator/09b-live-stopped.png`); a tool result is shown once (the fake agent used to emit "ok" plus a summary); tool summaries, decisions ("allowed/denied/stopped") and task status are localised from string resources (the hub sends a neutral key + arguments, `sum`); the event list has top padding. The acting state mid-task is `05-live-acting.png` (orange frame, chip "AI is controlling the PC"), the lock state `10-live-input-locked.png`.

### Round 4 (20/11/2026): E2E state bridge, network cut, hub restart, and 30 desktop tasks

27. **`indicator.json`, `input_lock.json`, and `RELEASE` takeover verified end to end on `emulator-5554`.** Starting a task from the phone under `preset = "strict"` locked local input (`input_lock.json: {"locked": true, "mode": "whole_task", "reason": "remote_task"}`, `indicator.json: {"state": "input_locked"}`) and showed the solid orange frame and `Keyboard/mouse locked` on the phone (`10-live-input-locked.png`). Triggering Take over (`POST /takeover`) wrote `RELEASE`, which `desktop-mcp` processed and removed, resetting `input_lock.json` (`locked: false, reason: "release"`) and `indicator.json` (`idle`) while the phone updated to `paused = true, locked = false`. Resuming finished the task cleanly.
28. **SSE heartbeat interval starved `approver.alive` during long waits.** `DesktopBridge` treats `activity` older than 12 s as inactive, while `events()` in `hub/turbo_hub/app.py` waited 15 s between ticks. Updated `events()` to tick every 7.5 s (refreshing `activity` on each tick while keeping 15 s `: hb` frames).
29. **Task-end cleanup race in `TaskManager._run`.** `on_task_end` ran after `task.status` changed from `"running"`, causing `test_every_way_a_task_ends_clears_the_pc_state[failed]` to race before `task_active.json` was removed. Moved `on_task_end` before resetting `task.status` in `finally:`.
30. **Clock skew and millisecond hub-restart boundary (`401 stale timestamp`).** On `motonav36`, the emulator clock lagged behind the Windows host by about 412 ms. Because `sign_response` previously sent whole-second `X-Hub-Ts`, `Protocol.computeSkewMs` ignored skews under 5 s, and `Graph.startConnection` cleared `sessionId` on any `401`, a `persist = true` hub restart rejected immediate reconnects (`ts_ms < st.started_ms`) and wiped valid sessions. Fixed by emitting millisecond `X-Hub-Ts` in `app.py`, adding `startedMs` to `GET /status` (`Graph.refreshTasks` resets `lastSeq = 0` and restarts SSE when `startedMs` changes), lowering the ms jitter deadzone in `Protocol.computeSkewMs` to 50 ms at the header midpoint `(sentAt + hdrAt) / 2`, setting a 25 s `/events` `readTimeout` with immediate disconnect updates (`11-task33-offline.png`, `11b-task33-reconnected.png`), and keeping `sessionId` when a `401` body reports `"stale timestamp"`. Tests: `test_hub_restart_same_second_rejects_old_requests_and_nonces`, `ProtocolTest.skewComputationIgnoresSmallJitterAndCorrectsLargeOffset`, and `emulator_run.py` Scenarios (a)-(d).
31. **`desktop-mcp` Round 6 across all 30 `FIELD_TASKS.md` tasks (`claude -p --model haiku`, details in `desktop-mcp/FIELD_REPORT.md`).** Hardened `StateBridge`/`RELEASE` concurrency (`BRIDGE_LOCK`, `unlink_retry`, `indicator.json` emitted regardless of `NO_INDICATOR`, eager `_on_worker`), `run_field.py` strict allowlist + `%TEMP%\turbo-field\`, rebuilt C# fixtures (`build.ps1`), and fixed `_split_launch_args` spaces in quoted paths, `RichTextBox` `\r` + `Slider` `ValuePattern`, `shell:AppsFolder` + `onInputDesktop`, WinForms `ComboBox` collapse (`CB_SHOWDROPDOWN`), and double-encoded JSON handling in `run_field.py`. Result: **29/30 pass** (173 calls, 203 turns, $0.2513 cost, 735.4 s wall, 30/30 valid audit chains). Only Task 8 (`calc`) failed because commands run on an isolated `exebox` Win32 desktop (`onInputDesktop: false`), while UWP `CalculatorApp.exe` activates on `WinSta0\Default`. `desktop-mcp/tests` after final edits: **231 passed, 8 skipped** (6 idle/input-desktop hook tests, 2 opt-in `TURBO_DESKTOP_REAL_INPUT=1` tests). `hub/tests` + `relay/tests`: **125 passed** (117 hub, 8 relay); Android JVM unit tests: **22 passed**.

### Observations

- Once the agent has been denied, the long-lived Claude session remembers it and does not try again until told. That is what the owner wants from a denial.
- `launch_app` for Notepad returned the owner's existing `.env - Notepad` window. The agent declined to type into it. desktop-mcp should open a new instance for tests.
- The phone's "via" label was always "Tailscale". Now derived from the pairing payload and the address (local, lan, tailscale, cloudflare).
- Inside an isolated Win32 desktop (`WinSta0\exebox-...`), Win32 fixtures (`turbo_fixture.exe`, `turbo_editor.exe`, `turbo_canvas.exe`) render and respond to UIA normally, while UWP `CalculatorApp.exe` activates on `WinSta0\Default`. For `strict` allowlist matching in `emulator_run.py`, `turbo_fixture.exe` is resolved via `PATH` rather than a full filesystem path so `_resolve_launch_names` maps directly to `"turbo_fixture"`.

### Open items

- Task 32 (real phone over Tailscale) remains unrun here because no physical phone was paired during this test cycle; manual steps are in `hub/README.md`.
- Task 8 (`calc`) on isolated `exebox` desktops (`onInputDesktop: false`) remains a Windows UWP activation boundary; `desktop-mcp/FIELD_REPORT.md` also records the remaining real-input/IME/multi-DPI boundaries.
