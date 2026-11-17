# Brief: round 2 of the 18/11 audit fixes

You can only read and edit files; you cannot run commands. The PM runs the tests. Do not read .env files.
Read `design/AUDIT_DEM_18-11.md` rows 14 and 29, `CODEBASE.md` and `agent.md` first.

## Part A (backend, hub only): row 14
`_extract_app` in `hub/turbo_hub/manager.py` misses most apps after B4. Make `topApps` in `/report` count the app for:
- `launch_app` results (window title / `matched`), remembering `window id -> app name` per task;
- `act`, `inspect_compact`, `batch_actions` calls that only give a window id (`w3`) or a ref (`w3:e5`), using that per-task map;
- `batch_actions` steps (each step may carry `window` or `ref`).
The tool result text arrives in the `tool_result` event (see how `summaries.py` unwraps it); keep the map on the `Task` object. Add tests in `hub/tests/test_report.py` with a FakeRunner script (see existing tests there).

## Part B (Android tests): row 29
Add Compose UI tests in `android/app/src/androidTest/java/dev/turbodesktop/remote/UiTest.kt` following the existing tests in that file, for: the approvals card of a Claude Code request (chip "Claude Code", the command detail text, no countdown), the full-screen player opening and the `zoomableScreen` tag being present, and the Báo cáo tab showing its tabs. Use the same setup helpers the existing tests use; if a test needs state, set the `Graph` flows directly as existing tests do. Do not change production code except adding `testTag`s if a node cannot be found otherwise.

Final answer: changed files and tests, under 150 words.
