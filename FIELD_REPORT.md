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
| 8 Calculator (12.5 + 7) x 3 via phone | 58.5, 4 tool calls, 18 s wall, 10 in / 819 out tokens + 104k cache read, $0.0023 (Haiku). Usage shown per task, session, day. |
| 28/31 approval round trip (fixture Submit button, Balanced) | Request reached the phone in under 1 s with window, control and a crop. Deny: the label stayed empty, the agent reported it was blocked. Allow: label read `Submitted: Ada / / agree=False`. Answer round trip 0.00 to 0.01 s locally. |
| 31 STOP mid-task | No tool call after STOP, the agent process (pid) was gone 1 s later, a new task got 423, the audit log shows `stop`, resume cleared it. |
| 34 hub restart mid-session | While down: connection error. A request signed before the restart is rejected (401). The in-memory session is gone (401), the phone reopens with biometric + TOTP, the paired device survives (DPAPI file). With `session.persist = true` the session survives. |
| 31 emulator: pair + open session | Pairing and session start worked over 10.0.2.2 with the Keystore keys and the biometric prompt (device PIN on the emulator). |
| 33 network cut | See "open items". |
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

### Observations

- Once the agent has been denied, the long-lived Claude session remembers it and does not try again until told. That is what the owner wants from a denial.
- `launch_app` for Notepad returned the owner's existing `.env - Notepad` window. The agent declined to type into it. desktop-mcp should open a new instance for tests.
- The phone's "via" label was always "Tailscale". Now derived from the pairing payload and the address (local, lan, tailscale, cloudflare).

### Open items

- Network cut on the emulator and the full emulator task run could not be completed in this session's time; the hub side is covered above and the app side reconnects with backoff (code in `Graph.startConnection`) but has not been watched on a device.
- The orange border, input lock and take-over states are relayed by the hub and the app (`indicator.json`, `input_lock.json`, `RELEASE` in the state folder). desktop-mcp has to write the first two and honour `RELEASE`. Not verified end to end yet.
