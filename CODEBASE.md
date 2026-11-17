# turbo-desktop codebase

## 1. Purpose

`turbo-desktop` has three parts: `desktop-mcp` (`desktop-mcp/`) is a Python stdio MCP server that drives Windows desktop apps through UI Automation (UIA) snapshots and patterns with idle-gated real input and Windows OCR fallbacks; `hub` (`hub/`) is the FastAPI server on the PC that the phone talks to; and `Turbo Remote` (`android/`) is the Kotlin and Jetpack Compose Android app (`minSdk 29`) for sending tasks, watching the PC screen and step log, answering approvals, triggering emergency STOP, and viewing reports and the audit log. `relay/wol_relay.py` is an optional stdlib-only Wake-on-LAN HTTP server for an always-on LAN device. Design notes and owner decisions live in `DESIGN.md` and `design/LIVE_V3.md`.

## 2. Architecture and data flow

During local pairing (`python -m turbo_hub pair` -> `POST /pair`), the phone generates two non-exportable EC P-256 keypairs in Android Keystore (`Keys.kt`): a plain key (`turbo_device_key`) for all requests and a biometric-gated key (`turbo_auth_key`, unlocked for 30 s per `BiometricPrompt`) for pairing, TOTP enrollment, opening sessions, and answering approvals. The phone pins the hub's EC P-256 public key from the QR payload. Every phone request carries `X-Device`, `X-Ts`, `X-Nonce`, and `X-Sig` (`ECDSA-SHA256` over `METHOD\nPATH?QUERY\nSHA256(body)\nTS\nNONCE`), plus `X-Auth-Sig` on `strong` routes and `X-Session` on `in_session` routes. The hub checks a 60 s clock window, rejects timestamps earlier than the current hub process start (`st.started`), tracks nonces in memory for 180 s, and signs every response (`X-Hub-Ts`, `X-Hub-Sig` over `RESP\nSTATUS\nPATH?QUERY\nSHA256(body)\nTS\nNONCE`) and every SSE frame (`EVT\n<json_payload>`) on `GET /events`. `GET /screen.jpg` captures the primary monitor with `mss`, blacks out visible windows whose titles match secret patterns before JPEG encoding, optionally crops to a zoomed region (`rx,ry,rw,rh` in thousandths), and returns the signed image with `X-Redacted`.

`TaskManager` (`hub/turbo_hub/manager.py`) runs one task at a time. In the default `claude-stream-json` mode, `ClaudeRunner` (`hub/turbo_hub/runners.py`) keeps one long-lived `claude -p --input-format stream-json --output-format stream-json` process alive across tasks, bound to a Windows job object (`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` in `reaper.py`) with its PID and image name recorded in `agent.pid`. `ClaudeRunner` writes a temporary MCP config that loads `desktop-mcp` (passing `TURBO_DESKTOP_CONFIG`, `TURBO_DESKTOP_PRESET`, and `TURBO_DESKTOP_STATE_DIR`) and registers `hub/turbo_hub/approval_mcp.py` (`mcp__turbohub__approve`) as `--permission-prompt-tool`. Before each tool call, `approval_mcp.py` calls loopback `POST /internal/approve` (`X-Task-Token`), which runs `TaskManager.gate`. With `approval.engine = "desktop-mcp"` (default), `desktop-mcp` classifies desktop actions using real UIA control metadata and asks through the state directory; the hub's own classifier (`config.py` / `classifier.py`) gates non-desktop tools or all tools when `approval.engine = "hub"`.

When `TURBO_DESKTOP_STATE_DIR` is set (`<hub_data_dir>/desktop-state` under the hub, or `desktop-mcp/tmp/state` standalone), `DesktopBridge` (`hub/turbo_hub/bridge.py`) and `StateBridge` (`desktop-mcp/src/turbo_desktop/inputlock.py`) synchronize through files in that directory (JSON files are written atomically via temp file and `os.replace`):
- `approver.alive`: touched by `DesktopBridge` every 0.1 s while phone or local admin activity is under 12 s old; `desktop-mcp` routes `ask` decisions to file approvals when this file is under 15 s old, and falls back to a local Windows `MessageBoxW` otherwise.
- `approvals/<id>.req.json` and `approvals/<id>.decision`: `desktop-mcp` writes `<id>.req.json` (with action metadata and optional control crop path) and polls for `<id>.decision`. On startup, `DesktopBridge` moves leftover `.req.json` files into `approvals/stale/`, emits `approval_request` for new files, and writes `allow` or `deny` to `<id>.decision`.
- `STOP`: created by the hub on `/stop` or `/admin/stop` and by `desktop-mcp` when the low-level input hook sees `Ctrl+Alt+Shift+K`; removed on resume. While present, `desktop-mcp` refuses all tool calls, cancels `wait_for`, releases the input lock, and hides the edge glow.
- `RELEASE`: written by the hub when the owner takes over; `StateBridge` deletes `RELEASE` and releases the input lock on its next 1 s tick.
- `task_active.json`: `{"task": id, "since": epoch, "heartbeat": epoch, "source": "phone", "max_minutes": 15}`, written by `DesktopBridge` for phone tasks when `remote_task = "whole_task"`, refreshed every 5 s, and deleted on task end, `STOP`, or takeover. `StateBridge` checks it every 1 s and holds the whole-task input lock, solid edge glow, and remote banner while `heartbeat` is under 15 s old and elapsed time is under `max_minutes`.
- `indicator.json`: `{"state": "idle" | "acting" | "input_locked"}`, written by `desktop-mcp` and read by `DesktopBridge` to update phone status and frame state.
- `input_lock.json`: `{"locked": bool, "mode": "real_input" | "whole_task", "since": epoch|null, "reason": str}`, written by `desktop-mcp` and read by `DesktopBridge`.
- `screen_view.json`: `{"until": epoch}`, written by the hub on each `GET /screen.jpg` (`now + 5` s); `StateBridge` displays the non-locking `"Điện thoại đang xem màn hình"` banner while `until` is in the future.
- `owner_took_over.json`: `{"at": epoch}`, written by `desktop-mcp` when the owner presses `Esc` 3 times within 1.5 s during an input lock; `DesktopBridge` unlinks it, clears `task_active.json`, and pauses the task (`TaskManager.takeover`).

For Claude Code permission prompts, `python -m turbo_hub cc-hook install` adds `hub/scripts/cc_permission_hook.py` to `hooks.PermissionRequest` in `~/.claude/settings.json`. The script reads the prompt JSON from stdin, decrypts `<hub_data_dir>/cc_hook_token.dpapi`, and calls loopback `POST /cc/permission` (`X-CC-Token`). `CCPermissions` (`hub/turbo_hub/cc_permission.py`) creates a non-expiring approval (`expires_at = 0`, `source = "claude_code"`) and pushes it to the phone, while the hook opens a topmost mouse-only Tkinter dialog on the PC and long-polls `GET /cc/permission/{rid}` with `X-CC-Key`. Whichever side answers first (`POST /approvals/{id}` on the phone or `POST /cc/permission/{rid}` from the PC dialog) wins and closes the other. If the parent Claude Code process exits or the hook stops polling for `stale_seconds` (20 s), `CCPermissions.reap` withdraws the request and closes the phone card.

## 3. Files and routes

### desktop-mcp (`desktop-mcp/`)

| Path | Responsibility |
| --- | --- |
| `src/turbo_desktop/server.py` | MCP stdio server, dedicated single-thread COM worker queue, 40 s call timeout with worker abandonment, tool registrations |
| `src/turbo_desktop/engine.py` | `Desktop` engine: window enumeration and matching, compact snapshots and deltas, sibling summarization, UIA pattern actions, idle-gated real input, Start Menu and UWP app launch, `wait_for`, window controls, redacted screenshots, Windows OCR fallback |
| `src/turbo_desktop/rules.py` | Loads `rules/default_rules.toml`, merges user `turbo-desktop.toml` and preset (`easy`, `balanced`, `strict`), evaluates `allow`, `ask`, or `deny` |
| `src/turbo_desktop/security.py` | Hard-floor checks (secret windows, password fields, owner-approval dialogs, `STOP`), `<<<SCREEN_CONTENT>>>` boundary wrapping, hash-chained `AuditLog`, file and local `MessageBoxW` approvals |
| `src/turbo_desktop/inputlock.py` | Single-thread `WH_KEYBOARD_LL` and `WH_MOUSE_LL` physical input lock, top banner window, `Ctrl+Alt+Shift+K` and `Esc` x3 escape hatches, `StateBridge` 1 s watcher for `TURBO_DESKTOP_STATE_DIR` |
| `src/turbo_desktop/border.py` | Per-monitor click-through layered orange edge glow (`Glow`, `GlowState`, `Indicator`) with pulse, locked solid mode, and `indicator.json` writer |
| `src/turbo_desktop/winsys.py` | Win32, DWM, and WinRT helpers: process name and elevation, idle timer, secure desktop and UAC check, battery status, `PrintWindow` capture, `Windows.Media.Ocr` |
| `rules/default_rules.toml` | Shipped allowlist, session-restore app list, input-lock and indicator defaults, and `[[rules]]` definitions per preset |
| `tests/*.py`, `tests/field/*.py`, `tests/fixtures/*` | Pytest unit and integration suites, shared machine lock (`locking.py`), WinForms and custom-draw C# fixtures (`build.ps1`), `bench.py`, `run_field.py`, `e2e_glow.py` |

### hub (`hub/`) and relay (`relay/`)

| Path | Responsibility |
| --- | --- |
| `turbo_hub/__main__.py` | CLI entry point: `setup`, `serve`, `run`, `pair`, `totp`, `devices`, `revoke`, `stop`, `resume`, `verify-audit`, `cc-hook` |
| `turbo_hub/app.py` | FastAPI application, request and response signing, nonce and strike lockout guards, sessions, and all HTTP routes |
| `turbo_hub/manager.py` | `TaskManager`: single-task execution, event bus, approval futures, `STOP`, takeover, resume, live and daily token usage, `tasks.jsonl` history, and `/report` aggregation |
| `turbo_hub/runners.py` | `ClaudeRunner` (long-lived `claude` stream-json process with `OPERATOR_PROMPT`), `GenericRunner` (`oneshot` CLI), `FakeRunner` (tests and demos) |
| `turbo_hub/approval_mcp.py` | Minimal stdio MCP server (`mcp__turbohub__approve`) forwarding Claude permission checks to `POST /internal/approve` |
| `turbo_hub/bridge.py` | `DesktopBridge`: syncs `approver.alive`, `approvals/*.req.json` to `.decision`, `STOP`, `RELEASE`, `task_active.json`, `owner_took_over.json`, `input_lock.json`, and `indicator.json` |
| `turbo_hub/cc_permission.py` | `CCPermissions`: formats Claude Code tool prompts, manages non-expiring external approvals, long-polling, and stale-hook withdrawal |
| `turbo_hub/cc_hook_install.py` | Installs, removes, checks, or prints the `PermissionRequest` hook entry in `~/.claude/settings.json` with timestamped backups |
| `turbo_hub/screen.py` | Primary-monitor capture (`mss`), secret-window black-out redaction, zoom crop box calculation, JPEG encoding, synthetic `demo_frame` |
| `turbo_hub/config.py`, `defaults.toml` | Config file lookup, preset merging (`easy`, `balanced`, `strict`), hub-side fallback classifier, first-run config writer |
| `turbo_hub/crypto.py`, `totp.py`, `store.py`, `dpapi.py` | Canonical wire strings, ECDSA P-256 sign and verify, RFC 6238 TOTP, DPAPI-encrypted `SecretStore` (`hub_key`, `admin_token`, `devices`, `totp`) |
| `turbo_hub/audit.py`, `reaper.py`, `sysstate.py`, `summaries.py`, `classifier.py`, `devclient.py` | Hash-chained `AuditLog`, Windows job object and `agent.pid` reaper, stdio `system_state` caller, localized tool-result summary keys, fallback classifier, simulated phone `DevClient` |
| `scripts/*.py`, `scripts/*.ps1`, `scripts/*.vbs` | `cc_permission_hook.py`, `start_hub_hidden.vbs`, `with_lock.py`, `field_run.py`, `emulator_run.py`, `emulator_shots.py`, `emulator_shots_v3.py`, `gen_vectors.py`, `smoke_real.ps1` |
| `tests/*.py` | Pytest suites for security, sessions, TOTP enrollment, tasks, screen redaction and crops, reports, config, Android test vectors, and Claude Code permissions |
| `../relay/wol_relay.py`, `../relay/tests/test_relay.py` | Stdlib-only signed Wake-on-LAN HTTP relay (`POST /pair`, `POST /wake`, `GET /hello`) with pure-Python P-256 verification and unit tests |

### Turbo Remote (`android/`)

| Path | Responsibility |
| --- | --- |
| `app/build.gradle.kts` | Android application config (`namespace = "dev.turbodesktop.remote"`, `minSdk 29`, `targetSdk 35`, `compileSdk 36`, JDK 17, Compose, R8 and resource shrinking on `arm64-v8a` release) |
| `app/src/main/java/dev/turbodesktop/remote/MainActivity.kt` | Activity host, notification Allow/Deny biometric dispatch, debug-only `dbg_action` intent hooks for emulator automation |
| `app/src/main/java/dev/turbodesktop/remote/Ui.kt` | Root `App` state router (Welcome -> Pair -> TotpSetup -> OpenSession -> Main) and `Main` scaffold with edge glow modifier |
| `app/src/main/java/dev/turbodesktop/remote/ScreensSetup.kt` | Onboarding and auth screens: `Welcome`, CameraX and ML Kit `QrScanner`, `PairScreen`, `TotpSetupScreen`, `OpenSession` |
| `app/src/main/java/dev/turbodesktop/remote/ScreensMain.kt` | Main tabs and overlays: `WorkTab` (`Việc`), `InlineScreenPlayer`, `FullScreenPlayerOverlay`, `StopCard`, `ApprovalsTab` (`Duyệt`), `ReportTab` (`Báo cáo`: overview and `AuditLogSection`), `SettingsTab` (`Cài đặt`), `CfLogin` |
| `app/src/main/java/dev/turbodesktop/remote/Zoom.kt` | `ScreenQuality` (`eco`, `sharp`, `max`), `ZoomMath` region, fit, and clamp calculations, and `ZoomableScreen` composable with delayed sharp crop fetching |
| `app/src/main/java/dev/turbodesktop/remote/Components.kt`, `Theme.kt` | Shared Compose controls (`PresenceHeader`, `TurboNavBar`, `OtpSixBoxInput`, buttons, rows) and dark theme tokens (`BeVietnamPro`, `JetBrainsMono`) |
| `app/src/main/java/dev/turbodesktop/remote/Graph.kt` | Process-wide state (`MutableStateFlow`s), event stream handler, screen-frame decoding on `Dispatchers.Default`, task, approval, report, and wake actions |
| `app/src/main/java/dev/turbodesktop/remote/HubClient.kt` | `Prefs`, `HubClient` (multi-transport failover, request signing, response and SSE signature verification, binary `/screen.jpg` fetch), `RelayClient` |
| `app/src/main/java/dev/turbodesktop/remote/Protocol.kt`, `Keys.kt`, `Totp.kt` | Canonical strings, ECDSA P-256 verification, QR payload and JSON parsers (`HubJson`), `KeystoreSigner`, RFC 6238 TOTP helper |
| `app/src/main/java/dev/turbodesktop/remote/Platform.kt` | `TurboApp`, `Biometric` prompt wrapper, `Notifier` channels and alerts, `HubService` foreground service, `BootReceiver`, Xiaomi and HyperOS `BatteryGuide`, `AppLang` |
| `app/src/test/.../*.kt`, `app/src/androidTest/.../UiTest.kt` | JVM unit tests (`ProtocolTest.kt`, `ZoomMathTest.kt`) and emulator Compose UI tests (`UiTest.kt`) |

### Hub HTTP routes

| Method and path | Auth | Purpose |
| --- | --- | --- |
| `POST /pair` | Local only (no proxy headers), active 6-digit pairing code, signed by new `pub` (`X-Sig`) and `authPub` (`X-Auth-Sig` if biometric required) | Registers a phone device, burns the one-time code, opens the 5 min TOTP enrollment window when TOTP is enabled |
| `GET /hello` | `signed` (`X-Device`, `X-Ts`, `X-Nonce`, `X-Sig`; no session) | Signed liveness check used during Wake-on-LAN polling and transport selection |
| `GET /policy` | `signed` (no session) | Returns active preset, `pcName`, `needs` (`totp`, `biometric`), `sessionHours`, `screenView`, and `lockRemoteTask` |
| `GET /totp/enroll` | Local only (no proxy headers) + `strong` (`signed` + `X-Auth-Sig` when biometric required; no session) | One-shot fetch of the `otpauth://` URI and base32 TOTP secret while the enrollment window is open |
| `POST /session/start` | `strong` (`signed` + `X-Auth-Sig` when biometric required) + unused 6-digit `totp` in body when `totp_required` | Opens a session (`2 h` or `12 h`) and returns `sessionId`, `expiresAt`, and `stopped` |
| `POST /unpair` | `in_session` (`signed` + valid `X-Session`) | Revokes the calling device and drops its sessions |
| `GET /status` | `in_session` | Returns `stopped`, `running` task ID, `pcName`, `paused`, `policy`, `screenView`, `lockRemoteTask`, `inputLock`, `indicator`, `usage`, `pendingApprovals`, `now` |
| `GET /screen.jpg` | `in_session` | Captures primary monitor (`w`, `q`, `rx`, `ry`, `rw`, `rh`), blacks out secret windows, writes `screen_view.json`, returns signed JPEG with `X-Redacted` |
| `POST /tasks` | `in_session` | Starts a task (`1..4000` chars); returns `409` if a task is already running, `423` if stopped or PC locked |
| `GET /tasks` | `in_session` | Returns up to 50 recent tasks from memory and `tasks.jsonl` |
| `GET /events/poll` | `in_session` | Returns up to 500 events with `seq > since` |
| `GET /events` | `in_session` | Streams hub-signed SSE events (`data: {"p":...,"sig":...}`) from `since` with 15 s heartbeats |
| `GET /approvals` | `in_session` | Lists pending approvals (`approvalId`, `taskId`, `tool`, `window`, `control`, `action`, `crop_png_b64`, `detail`, `source`, `expiresAt`) |
| `POST /approvals/{approval_id}` | `in_session` + `strong` (`X-Auth-Sig` when biometric required) | Resolves a pending approval with `{"decision": "allow" | "deny"}`; returns `409` if already decided |
| `POST /stop` | `in_session` | Activates emergency STOP, kills the agent process, denies pending approvals, writes `STOP` |
| `POST /takeover` | `in_session` | Writes `RELEASE`, clears `task_active.json`, and pauses the running task |
| `POST /resume` | `in_session` | Clears `STOP` and pause state |
| `GET /audit` | `in_session` | Verifies the hash chain and returns `chainOk`, `chainInfo`, and the last `limit` (`1..200`) audit entries |
| `GET /report` | `in_session` | Aggregates task counts, work seconds, token totals, USD cost, and top 5 apps for `days` in `1`, `7`, or `30` |
| `POST /internal/approve` | Loopback only (no proxy headers) + `X-Task-Token` | Internal gate called by `approval_mcp.py` before Claude executes a tool |
| `POST /cc/permission` | Loopback only (no proxy headers) + `X-CC-Token` | Creates a non-expiring Claude Code permission request from `cc_permission_hook.py` |
| `GET /cc/permission/{rid}` | Loopback only (no proxy headers) + `X-CC-Token` + `X-CC-Key` | Long-polls (`wait` up to 30 s) for a decision on a Claude Code permission request |
| `POST /cc/permission/{rid}` | Loopback only (no proxy headers) + `X-CC-Token` + `X-CC-Key` | Records a PC-side decision (`allow`, `deny`, or `withdrawn`) for a Claude Code permission request |
| `POST /admin/totp` | Loopback only (no proxy headers) + `X-Admin-Token` | Opens the 5 min TOTP enrollment window (and rotates the secret if `{"rotate": true}`) |
| `POST /admin/pairing` | Loopback only (no proxy headers) + `X-Admin-Token` | Creates a 6-digit pairing code and QR payload |
| `GET /admin/devices` | Loopback only (no proxy headers) + `X-Admin-Token` | Lists paired devices |
| `DELETE /admin/devices/{device_id}` | Loopback only (no proxy headers) + `X-Admin-Token` | Revokes a paired device and drops its active sessions |
| `POST /admin/tasks` | Loopback only (no proxy headers) + `X-Admin-Token` | Starts a local admin task (`source = "local"`) |
| `GET /admin/events` | Loopback only (no proxy headers) + `X-Admin-Token` | Polls up to 500 events with `seq > since` and refreshes `approver.alive` activity |
| `POST /admin/approvals/{approval_id}` | Loopback only (no proxy headers) + `X-Admin-Token` | Resolves a pending approval from the local CLI |
| `POST /admin/stop` | Loopback only (no proxy headers) + `X-Admin-Token` | Triggers emergency STOP from the PC CLI |
| `POST /admin/resume` | Loopback only (no proxy headers) + `X-Admin-Token` | Clears STOP and pause from the PC CLI |
| `GET /admin/status` | Loopback only (no proxy headers) + `X-Admin-Token` | Returns `stopped`, `devices`, `audit_ok`, `audit`, `running`, `agent_pid`, and `paused` |

## 4. Interfaces

### desktop-mcp tools
- `windows_list(verbose=False, hidden=False)`: Lists top-level windows as compact lines (`w3 Calculator [CalculatorApp] *focused`), keeping `[secret]`, `[denied: ...]`, and `[elevated]` flags and hiding cloaked, zero-size, tray, and overlay windows unless `hidden=True`.
- `inspect_compact(window, mode="interactive", query=None, onlyChanged=False, maxChars=6000)`: Returns a wrapped snapshot (`[w1:e12] <Button> "Save"`) or delta (`*` new, `~` changed, `-` removed), collapsing sibling runs above 8 items and falling back to Windows OCR (`[w1:o3]`, `treeEmpty: true`) when the UIA tree is empty.
- `act(window=None, ref=None, name=None, role=None, action="click", text=None, value=None, keys=None, direction=None, amount=1, returnSnapshot=False)`: Performs `click`, `invoke`, `type`, `set_value`, `select`, `toggle`, `expand`, `focus`, `read`, `scroll`, `press_keys`, or `send_text` by ref or name, preferring UIA patterns (`via: "pattern"`) before idle-gated real input (`via: "input"`), with optional delta snapshot.
- `batch_actions(steps, window=None, returnSnapshot=False)`: Runs a sequence of `act`, `wait_for`, or `inspect` steps in one call and stops on the first error; on success returns `ran=N` and only steps with output, plus an optional delta snapshot.
- `launch_app(target, args="", wait=8.0, returnExisting=False, returnSnapshot=True, snapshotQuery=None, snapshotMaxChars=1500)`: Launches an executable or alias, Registry App Path, Start Menu `.lnk` (case- and Vietnamese-diacritic-insensitive), or UWP `shell:AppsFolder` app with `SW_SHOWNOACTIVATE`, returning new windows and the initial snapshot (or `pending: true` with a hint).
- `wait_for(window=None, text=None, gone=False, title=None, timeout=8.0)`: Polls up to `timeout` seconds for a window title or control substring to appear or disappear (`gone=True`), checking `STOP` on every poll and returning seen window titles on timeout.
- `window_control(window, action)`: Sends `close`, `minimize`, `maximize`, `restore`, or `activate` to the target window.
- `screenshot(window)`: Returns a PNG of a single window (scaled to at most 1280 px wide) with `IsPassword` edit controls blacked out.
- `system_state()`: Returns `secureDesktopActive`, `uacPrompt`, `sessionLocked`, `displayOff`, `idleSeconds`, `onBattery`, `batteryPercent`, `weAreAdmin`, and `ready`.

### Event types sent to the phone
Every event emitted by `TaskManager.emit` over `/events` (SSE) and `/events/poll` includes `seq` (monotonic integer) and `ts` (epoch seconds):
- `task_started`: `{task_id, text}` when a task begins.
- `warning`: `{task_id, text}` for low battery (<20%) or display-off warnings at task start.
- `text`: `{task_id, text}` for assistant text blocks or `GenericRunner` output lines.
- `tool_call`: `{task_id, tool, window, control, action}` emitted once per tool call when gated.
- `tool_result`: `{task_id, tool, tool_use_id?, ok, summary, sum: {k, a}}` carrying a language-neutral summary key and arguments (`opened`, `acted`, `read_controls`, `read_window`, `ran_steps`, `screenshot`, `listed_windows`, `read_state`, `waited`, `wait_timeout`, `failed`, `text`) and an English fallback string.
- `usage`: `{task_id, usage: {input, output, cache_read, cache_create}}` live deduplicated token counts during a run.
- `final`: `{task_id, text, ok, usage?}` with the task's final answer or runner error.
- `task_finished`: `{task_id, status, usage, session_usage, day_usage}` (`status` is `done`, `failed`, or `stopped`).
- `approval_request`: `{approval_id, task_id?, tool, window, control, action, crop_png_b64, expires_at, detail?, source?}` (`expires_at: 0` and `source: "claude_code"` for Claude Code prompts).
- `approval_resolved`: `{approval_id, task_id?, decision, by?}` (`decision` is `allow`, `deny`, `timeout`, `stop`, or `withdrawn`).
- `stopped`: emitted when emergency STOP is activated.
- `taken_over`: `{reason?}` emitted when the owner takes over (`pc-owner`, phone `/takeover`, or `max_task_minutes`) and the task pauses.
- `resumed`: emitted when STOP or pause is cleared.
- `input_lock`: `{locked, mode?, since?, max_seconds?, reason?}` relayed from `input_lock.json`.
- `indicator`: `{state: "idle" | "acting" | "input_locked"}` relayed from `indicator.json` or derived from tool calls.
- `hub_alert`: `{what, device?}` emitted when an unpaired device is rejected or a source is locked out for 15 minutes.
- `paired`: `{device, name}` emitted when a device completes `/pair`.
- `device_revoked`: `{device}` emitted when `/admin/devices/{device_id}` revokes a device.

## 5. Behaviour and invariants

The hard floor is enforced in code across every preset (`easy`, `balanced`, `strict`) and cannot be disabled by configuration:
- `STOP`: Pressing `Ctrl+Alt+Shift+K` while the input hook is active, calling `POST /stop` from the phone, or running `python -m turbo_hub stop` writes `<state>/STOP`, kills the running agent process tree, resolves pending approvals as `stop`, cancels `wait_for`, releases the input lock, hides the edge glow, and blocks new tasks (`423`) and tool calls until resumed.
- Hash-chained audit: Both the hub (`<hub_data_dir>/audit.jsonl`) and `desktop-mcp` (`<state_dir>/audit.jsonl` or `TURBO_DESKTOP_AUDIT`) record every action, approval, rejection, lockout, and state change in an append-only JSONL file where each line includes `prev` and `hash` (`SHA-256` over `prev` + canonical JSON body).
- Signed non-local requests: `bind_sockets` refuses `0.0.0.0` and `::`. Every non-admin request requires a valid ECDSA P-256 signature from a paired device, a timestamp within 60 s of hub time and not earlier than `st.started`, and an unused nonce. Bodies over 64 KB are rejected (`413`), and 5 authentication failures from one source within 10 minutes lock out that source for 15 minutes (`429`).
- Local-only pairing: `/pair`, `/totp/enroll`, `/admin/*`, `/internal/approve`, and `/cc/permission*` reject any request carrying proxy or tunnel headers (`Cf-Connecting-Ip`, `Cf-Ray`, `X-Forwarded-For`, `Cf-Access-Jwt-Assertion`). Pairing requires a 6-digit code created on the PC (5 min TTL, burned after 5 attempts).
- Secret-window deny zone: Windows whose title matches `SECRET_TITLE_PATTERNS` (`.env`, `secret(s)`, `credentials`, `.pem`, `.key`, `id_rsa`, `.kdbx`, `token`, `password`, `mật khẩu`, `api[_-]?key`, plus user additions in `[desktop.secrets] patterns`) or whose process is in `SECRET_PROCESSES` (`bitwarden`, `keepass`, `keepassxc`, `1password`, `lastpass`, `dashlane`, `nordpass`, `roboform`, `enpass`, `protonpass`) are listed as `"[hidden: secret window]"` in `windows_list`, refused on all `inspect_compact`, `act`, `read`, `screenshot`, and OCR calls with `{"denied": "secret-window", "rule": "secret-window"}` without repeating the title, and blacked out (enumerated both before and after screen grab) in `GET /screen.jpg`.
- Passwords never reach the model: Controls with `IsPasswordProperty == true` appear as `[password:protected]` with no value in snapshots, refuse `read`, `type`, `set_value`, and `click`, and are blacked out in `screenshot`. Secrets can only be typed via `$secret:NAME` resolved inside `desktop-mcp` from `~/.turbo-desktop-secrets.json` (or `TURBO_DESKTOP_SECRETS`). All screen text returned by `desktop-mcp` is wrapped in `<<<SCREEN_CONTENT ...>>>` boundary markers with spoofed markers stripped.
- Glow while locked or sending real input: Even when `[indicator] border = false`, `border.py` and `inputlock.py` always show the solid bright edge frame and top banner while the physical keyboard and mouse are locked or real input is being sent.
- Owner-approval dialogs are a deny zone: Windows with class `"Credential Dialog Xaml Host"` or titles in `OWNER_APPROVAL_TITLES` (`"claude code cần duyệt"`, `"claude code needs approval"`) are denied in `security.py` (`deny zone [owner-approval]`) so an agent cannot click Allow on its own permission prompt.

Phone tasks default to `[input_lock] remote_task = "whole_task"` in all presets. From `task_started` to `task_finished`, the hub maintains `task_active.json` (5 s heartbeat) and `desktop-mcp` locks physical keyboard and mouse input (passing `LLKHF_INJECTED` and `LLMHF_INJECTED` events) and displays the solid glow and remote banner, up to `max_task_minutes = 15` (and per-action `max_seconds` clamped to `5..300` for `real_input`). Pressing `Esc` 3 times within 1.5 s or tapping Take Over on the phone releases the lock immediately and pauses the task until resumed. `TaskManager` runs one task at a time, rejecting `POST /tasks` with `409 {"detail": "busy", "running": id}` while a task is running, and the Android composer disables Send while a request is in flight or a task is running. Permission requests created via `/cc/permission` set `expires_at = 0` and wait without a timeout until answered on the phone or PC dialog, stopped via STOP, or withdrawn when the hook stops polling for 20 s.

## 6. Configuration

Both `hub` and `desktop-mcp` resolve `turbo-desktop.toml` in the same order: `$TURBO_DESKTOP_CONFIG`, `./turbo-desktop.toml`, `%APPDATA%\turbo-desktop\turbo-desktop.toml` (written by `python -m turbo_hub setup`), and `~/turbo-desktop.toml`. Settings merge `hub/turbo_hub/defaults.toml` -> `[presets.<name>]` -> user `turbo-desktop.toml` (and `desktop-mcp/rules/default_rules.toml` + `[desktop]` overrides in `desktop-mcp`).

| Setting | `easy` (default) | `balanced` | `strict` |
| --- | --- | --- | --- |
| `server.connections` | `["local"]` (`+ "lan"` if setup with phone) | `["local", "lan", "tailscale"]` | `["tailscale", "cloudflare", "local"]` |
| `session.hours` | `12` | `2` | `2` |
| `auth.totp` / `auth.biometric` | `false` / `false` | `true` / `false` | `true` / `true` |
| `cloudflare.require_access` | `false` | `false` | `true` |
| `input_lock.mode` (local `run`) | `"real_input"` | `"real_input"` | `"whole_task"` |
| `input_lock.remote_task` (phone) | `"whole_task"` (15 min cap) | `"whole_task"` (15 min cap) | `"whole_task"` (15 min cap) |
| `screen_view.enabled` | `true` | `true` | `false` |
| Approval rules (`ask`) | permanent delete, payment, uninstall, Windows Settings > Accounts/Privacy | `easy` + Send/Delete/Install/Publish/Sign out, shells/regedit/Task Manager, Enter in chat/compose, session-restore apps | `balanced` + OK/Yes in delete/payment dialogs, unnamed buttons or Enter in multiline boxes of unknown apps, launching unknown apps (uses clean launch for Notepad/VS Code) |
| Deny zones (`deny`) | hard floor + password managers, UAC/lock screen, Windows Security | same as `easy` | `balanced` + banking window titles |

The hub data directory is `%LOCALAPPDATA%\turbo-desktop-hub` (or `$TURBO_HUB_DATA`), storing DPAPI-encrypted `hub_key.dpapi`, `admin_token.dpapi`, `devices.dpapi`, `totp.dpapi`, `cc_hook_token.dpapi`, optional `sessions.dpapi`, `audit.jsonl`, `tasks.jsonl` (90-day retention), `usage.json`, `agent.pid`, `thumbs/`, and `desktop-state/`. The default port is `8750` (`[server] port = 8750`, overridable via `--port`). `hub/scripts/start_hub_hidden.vbs` launches `hub\.venv\Scripts\python.exe -u -m turbo_hub serve` in a hidden window (`sh.Run ..., 0, False`) and redirects output to `%LOCALAPPDATA%\turbo-desktop-hub\serve.log` when linked from `shell:startup`. `python -m turbo_hub cc-hook install` backs up `~/.claude/settings.json` and installs `hub/scripts/cc_permission_hook.py` under `hooks.PermissionRequest` (`uninstall`, `status`, and `print` are also supported).

## 7. Verification

All pytest suites and field scripts acquire the shared machine lock `%TEMP%\turbo-desktop-test.lock` (`hub/scripts/with_lock.py` and `desktop-mcp/tests/locking.py`) so two runs never touch the desktop or `desktop-mcp` at the same time.

Hub and relay unit and integration tests:
```powershell
hub\.venv\Scripts\python.exe hub\scripts\with_lock.py -- hub\.venv\Scripts\python.exe -m pytest hub\tests -q
hub\.venv\Scripts\python.exe -m pytest relay\tests -q
hub\.venv\Scripts\python.exe hub\scripts\gen_vectors.py
```

`desktop-mcp` tests run with `TURBO_DESKTOP_NO_INPUT=1` by default (UIA patterns only, isolated temp state). Set `TURBO_DESKTOP_REAL_INPUT=1` to include real mouse and keyboard tests (`@pytest.mark.realinput`; live hook tests skip unless the PC has been idle for at least 20 s). Rebuild the C# fixtures (`turbo_fixture.exe`, `turbo_editor.exe`, `turbo_canvas.exe`) if `.cs` files change:
```powershell
desktop-mcp\.venv\Scripts\python.exe -m pytest desktop-mcp\tests -q
$env:TURBO_DESKTOP_REAL_INPUT = "1"; desktop-mcp\.venv\Scripts\python.exe -m pytest desktop-mcp\tests -q
powershell -File desktop-mcp\tests\fixtures\build.ps1
```

Android unit tests and release APK build require `JAVA_HOME` set to JDK 17 (`.\gradlew.bat :app:connectedDebugAndroidTest` runs Compose UI tests on a connected Android 16 emulator):
```powershell
cd android
.\gradlew.bat :app:testDebugUnitTest :app:assembleRelease
```

Emulator, field, and benchmark scripts:
```powershell
hub\.venv\Scripts\python.exe hub\scripts\emulator_shots.py
hub\.venv\Scripts\python.exe hub\scripts\emulator_shots_v3.py
hub\.venv\Scripts\python.exe hub\scripts\emulator_run.py
hub\.venv\Scripts\python.exe hub\scripts\field_run.py [calc|deny|stop|restart|orphan|all]
desktop-mcp\.venv\Scripts\python.exe desktop-mcp\tests\field\bench.py
```

## 8. Operational limitations

Calling UIA `Invoke` on a WinForms `ToolStripMenuItem` that opens a modal dialog (field task 21) blocks inside the app's modal loop; `act` returns after 2.5 s with `pending: true` and marks the process `blocked: true` for subsequent UIA calls until the dialog closes via `window_control close` or window-level `press_keys {Esc}`. Use keyboard accelerators (`Ctrl+S`) for menu items that open modal dialogs. A UIA call into a hung app times out after 40 s (`TURBO_DESKTOP_CALL_TIMEOUT`) and starts a fresh COM worker thread.

Transient right-click, `Shift+F10`, or `{Apps}` context menus in Windows 11 Explorer (field task 22) sit outside the window's UIA tree and did not appear in `windows_list` or screenshots. Windows 11 Notepad, Edge, Chrome, VS Code, Word, and Excel reopen previous tabs or documents on launch, exposing their text to the agent; `easy` returns a warning, `balanced` asks for approval, and `strict` asks and uses a clean launch only for Notepad (new temp file) and VS Code (`--new-window` on a temp folder). Windows owned by elevated processes (`elevated: true, actionable: false`), UAC prompts, and the lock screen cannot be driven by a non-admin process due to UIPI and the Windows secure desktop. Windows with empty UIA trees fall back to slower Windows OCR (`treeEmpty: true`, click-only `[w1:oN]` refs, no control values), and unfiltered snapshots of large trees such as a 200-file Explorer folder (~2,300 tokens) or a Save As dialog (~1,500 tokens) require `query=` or `maxChars`.

`GET /screen.jpg` blacks out windows whose titles match `secret_title_patterns`, but all other visible screen pixels are streamed (~40 KB per frame at 960 px q60, ~2.4 MB/min at 1 fps). Windows DPAPI (`CurrentUser`) stops file copying to another machine or user, not malware running as the same Windows user. The hash chain in `audit.jsonl` detects edits, deletions, and reordering, but cannot detect truncating lines from the end of the file without an external anchor. Real-phone pairing over Tailscale (task 32), multi-monitor or 150% DPI real-input clicks (task 26), and active Vietnamese IME transformation on injected keys (task 18) were not completed on the test PC; emulator airplane mode did not reliably cut the `10.0.2.2` route (task 33). `oneshot` CLI agents without a permission hook cannot be gated per tool call by the hub. Wake-on-LAN requires wired Ethernet, BIOS and NIC support, and an always-on LAN device running `relay/wol_relay.py`.

## 9. Change log

- 2026-11-17: Built v0 prototype of `desktop-mcp` (UIA engine, rules/presets, hash-chained audit, input lock, edge glow), `hub` (ECDSA P-256 pairing, TOTP sessions, SSE events, Claude stream-json runner, WOL relay), and `Turbo Remote` Android client (`DESIGN.md`).
- 2026-11-17: Completed automated and field test rounds across `desktop-mcp`, `hub`, and the Android 16 emulator; added dedicated COM worker thread, modal-dialog timeout guard, persistent input-lock thread, secret-window hard floor, shared `%TEMP%\turbo-desktop-test.lock`, and Windows job-object agent reaper (`FIELD_REPORT.md`, `desktop-mcp/FIELD_REPORT.md`, `desktop-mcp/BENCH.md`).
- 2026-11-17: Shipped Live v3 after real-phone feedback: whole-task lock and glow via `task_active.json`, single-task concurrency (`409` busy), Start Menu `.lnk` and `shell:AppsFolder` resolution in `launch_app`, redacted `GET /screen.jpg` live player, merged `Việc` and `Báo cáo` tabs, and Android release R8 and Compose performance fixes (`design/LIVE_V3.md`, `android/PERF.md`).
- 2026-11-18: Added Claude Code remote and PC permission approvals (`cc_permission_hook.py` and `/cc/permission*` with no timeout and owner-approval deny zone), pinch-to-zoom with native-pixel sharp crops on `/screen.jpg`, and B4 `desktop-mcp` token efficiency improvements (`launch_app` initial snapshot, compact `batch_actions` and `windows_list`, sibling group summarization, 8 s `wait_for` with seen-window hints) (`desktop-mcp/BENCH.md`).
