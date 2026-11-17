# turbo-desktop working guide

## 1. Workflow

Read `DESIGN.md`, `design/LIVE_V3.md`, this guide, the relevant `CODEBASE.md` sections, then the affected source files before editing.

## 2. File routing

- MCP tools, UIA snapshots, action execution, Start Menu and UWP launch, OCR fallback: `desktop-mcp/src/turbo_desktop/server.py`, `desktop-mcp/src/turbo_desktop/engine.py`, `desktop-mcp/src/turbo_desktop/winsys.py`.
- Desktop safety rules, presets, secret-window floor, local and file approvals, hash-chained audit: `desktop-mcp/rules/default_rules.toml`, `desktop-mcp/src/turbo_desktop/rules.py`, `desktop-mcp/src/turbo_desktop/security.py`.
- Physical input lock, escape hatches (`Ctrl+Alt+Shift+K`, `Esc` x3), screen-edge glow, state-dir watcher: `desktop-mcp/src/turbo_desktop/inputlock.py`, `desktop-mcp/src/turbo_desktop/border.py`.
- Hub HTTP routes, request and response signing, TOTP, DPAPI secret store, audit log: `hub/turbo_hub/app.py`, `hub/turbo_hub/crypto.py`, `hub/turbo_hub/totp.py`, `hub/turbo_hub/store.py`, `hub/turbo_hub/dpapi.py`, `hub/turbo_hub/audit.py`.
- Task lifecycle, agent runners, MCP permission shim, `desktop-state/` bridge, usage and reports, screen capture and redaction: `hub/turbo_hub/manager.py`, `hub/turbo_hub/runners.py`, `hub/turbo_hub/approval_mcp.py`, `hub/turbo_hub/bridge.py`, `hub/turbo_hub/screen.py`, `hub/turbo_hub/summaries.py`, `hub/turbo_hub/reaper.py`, `hub/turbo_hub/sysstate.py`.
- Claude Code permission hook and `/cc/permission*` endpoints: `hub/scripts/cc_permission_hook.py`, `hub/turbo_hub/cc_permission.py`, `hub/turbo_hub/cc_hook_install.py`.
- Hub CLI, presets, default configuration, and autostart: `hub/turbo_hub/__main__.py`, `hub/turbo_hub/config.py`, `hub/turbo_hub/defaults.toml`, `hub/scripts/start_hub_hidden.vbs`.
- Android wire protocol, Keystore keys, HTTP and SSE client, state graph, foreground service, notifications: `android/app/src/main/java/dev/turbodesktop/remote/Protocol.kt`, `Keys.kt`, `Totp.kt`, `HubClient.kt`, `Graph.kt`, `Platform.kt`, `MainActivity.kt`.
- Android Compose screens, theme, and zoomable screen player: `android/app/src/main/java/dev/turbodesktop/remote/Ui.kt`, `ScreensSetup.kt`, `ScreensMain.kt`, `Zoom.kt`, `Components.kt`, `Theme.kt`.
- Wake-on-LAN relay: `relay/wol_relay.py`, `relay/tests/test_relay.py`.
- Automated tests, fixtures, and field runners: `hub/tests/*.py`, `hub/scripts/*.py`, `desktop-mcp/tests/*.py`, `desktop-mcp/tests/field/*.py`, `desktop-mcp/tests/fixtures/*.cs`, `android/app/src/test/java/dev/turbodesktop/remote/*.kt`, `android/app/src/androidTest/java/dev/turbodesktop/remote/UiTest.kt`.

## 3. Guardrails

- Preserve the hard floor across every preset: emergency `STOP` (`STOP` file, phone button, `Ctrl+Alt+Shift+K`), append-only hash-chained audit logs, signed non-local requests (`ECDSA P-256`, 60 s timestamp window, nonce replay check, never bind `0.0.0.0`), local-only pairing and admin endpoints (refuse proxy and tunnel headers), secret-window deny zone (hidden in `windows_list`, refused by all tools, blacked out in `/screen.jpg`), password fields never read or typed (except via `$secret:NAME`), screen-edge glow and banner always shown while input is locked or real input is sent, and owner-approval dialogs (`Claude Code cần duyệt`, `Claude Code needs approval`, `Credential Dialog Xaml Host`) blocked as a deny zone.
- Tests and field scripts must never touch, focus, type into, or close windows they did not launch themselves, and must never launch session-restore apps (such as the owner's Notepad) without a clean launch path (`TURBO_DESKTOP_REQUIRE_CLEAN=1`).
- Never connect to Chrome debugging ports `9222` or `9224`.
- Never run test suites or field scripts in parallel; every run must acquire the shared lock `%TEMP%\turbo-desktop-test.lock`.
- Do not change signing, canonical strings, TOTP, or session code (`hub/turbo_hub/crypto.py`, `hub/turbo_hub/totp.py`, `hub/turbo_hub/app.py`, `Protocol.kt`, `HubClient.kt`) without updating and running tests on both sides and regenerating shared vectors (`hub/scripts/gen_vectors.py`).
- Do not read, log, or commit `.env` files or real credentials.

## 4. Documentation sync

Update `CODEBASE.md` sections 2 to 7 and append to section 9 for any change to routes, data flow, file contracts, tools, events, configuration, or verification checks. Update `agent.md` when file routing, guardrails, or verification commands change.

## 5. Verification

- Hub and relay tests: `hub\.venv\Scripts\python.exe hub\scripts\with_lock.py -- hub\.venv\Scripts\python.exe -m pytest hub\tests -q` and `hub\.venv\Scripts\python.exe -m pytest relay\tests -q`.
- `desktop-mcp` tests (default `TURBO_DESKTOP_NO_INPUT=1`; set `$env:TURBO_DESKTOP_REAL_INPUT="1"` only when the PC is idle to run real-input tests, and rebuild C# fixtures with `powershell -File desktop-mcp\tests\fixtures\build.ps1` if `.cs` files change): `desktop-mcp\.venv\Scripts\python.exe -m pytest desktop-mcp\tests -q`.
- Android unit tests and release APK (`JAVA_HOME` set to JDK 17): `cd android && .\gradlew.bat :app:testDebugUnitTest :app:assembleRelease`.
- Emulator and benchmark scripts: `hub\.venv\Scripts\python.exe hub\scripts\emulator_shots.py`, `hub\.venv\Scripts\python.exe hub\scripts\emulator_shots_v3.py`, `hub\.venv\Scripts\python.exe hub\scripts\emulator_run.py`, and `desktop-mcp\.venv\Scripts\python.exe desktop-mcp\tests\field\bench.py`.
