# Brief: write CODEBASE.md and agent.md for turbo-desktop

You can only read files and write two files. Do not run commands. Do not read .env files.

Follow the format of `D:\Project\1-dang-ban\whop-sheet-sync\CODEBASE.md` and `D:\Project\1-dang-ban\whop-sheet-sync\agent.md` (read both first). Read `C:\Users\TRUNG THANH\.claude\skills\humanizer\SKILL.md` and `C:\Users\TRUNG THANH\.claude\skills\stop-slop\SKILL.md` and write plainly.

## Read the code
`DESIGN.md`, `design/LIVE_V3.md`, `hub/turbo_hub/*.py`, `hub/scripts/*.py`, `desktop-mcp/src/turbo_desktop/*.py`, `desktop-mcp/rules/default_rules.toml`, `android/app/src/main/java/dev/turbodesktop/remote/*.kt`, `android/app/build.gradle.kts`, the test folders, `android/PERF.md`, `desktop-mcp/BENCH.md`.

## Write `CODEBASE.md` (repo root), sections
1. Purpose (3 parts: desktop-mcp drives Windows apps through UI Automation; hub is the PC server the phone talks to; Turbo Remote is the Android app).
2. Architecture and data flow: phone → hub (signed requests, sessions, events SSE, approvals, screen view), hub → agent (claude stream-json runner with desktop-mcp), desktop-mcp ↔ hub file contract (state dir: approver.alive, approvals/, STOP, task_active.json, indicator.json, input_lock.json, screen_view.json, owner_took_over.json), Claude Code permission hook (`hub/scripts/cc_permission_hook.py` → `/cc/permission`).
3. Files and routes: a table per part (path → responsibility). List every hub HTTP route with its auth (session, strong, admin local, cc token local).
4. Interfaces: tool list of desktop-mcp with one line each; event types sent to the phone.
5. Behaviour and invariants: the hard floor (STOP, hash-chained audit, signed non-local requests, local-only pairing, secret-window deny zone, passwords never reach the model, glow while locked or sending real input, owner-approval dialogs are a deny zone), whole-task lock, one task at a time, no-timeout Claude Code approvals.
6. Configuration: `%APPDATA%\turbo-desktop\turbo-desktop.toml`, presets easy/balanced/strict, hub data dir `%LOCALAPPDATA%\turbo-desktop-hub`, port 8750, autostart `hub/scripts/start_hub_hidden.vbs`, `python -m turbo_hub cc-hook install`.
7. Verification: exact test commands for hub (pytest), desktop-mcp (pytest with TURBO_DESKTOP_NO_INPUT=1 default, real input only with TURBO_DESKTOP_REAL_INPUT=1, shared lock %TEMP%\turbo-desktop-test.lock), Android (`gradlew :app:testDebugUnitTest :app:assembleRelease`, JAVA_HOME = JDK 17), emulator scripts in `hub/scripts/emulator_*.py`, bench `desktop-mcp/tests/field/bench.py`.
8. Operational limitations (from FIELD_REPORT.md, PERF.md and the code).
9. Change log: one line per dated milestone you can see in the docs (most recent: 18/11 Claude Code remote approvals, zoom + sharp crops for screen view, B4 efficiency).

## Write `agent.md` (repo root), sections
1. Workflow (read DESIGN.md, this guide, the CODEBASE.md sections, then the code).
2. File routing (which files for which change).
3. Guardrails: the hard floor above; tests never touch windows they did not launch; never connect to Chrome ports 9222/9224; never run the suites in parallel; do not change signing/session code without tests; do not read .env.
4. Documentation sync: update CODEBASE.md sections 2–7 and append to section 9 for any change to routes, data flow, config or checks; update agent.md when routing, guardrails or commands change.
5. Verification commands.

Only state what the code shows. Unsure: say "check" rather than guess. Final answer: one line.
