# Turbo Desktop

Turbo Desktop lets an AI coding agent operate Windows 10/11 desktop applications through Windows UI Automation (UIA) rather than screenshot loops, while giving the PC owner live supervision, cryptographic per-action approvals, and an emergency kill switch from an Android phone.

The repository contains four components that work together or standalone:

| Directory | Component | Description |
| --- | --- | --- |
| `desktop-mcp/` | Standalone MCP server (Python 3.12+) | Exposes 9 UIA + Windows OCR tools (`windows_list`, `inspect_compact`, `act`, `batch_actions`, `launch_app`, `wait_for`, `window_control`, `screenshot`, `system_state`). Works on its own in Claude Code, Claude Desktop, Cursor, or any stdio MCP client. Full guide: [`desktop-mcp/README.md`](desktop-mcp/README.md). |
| `hub/` | Control hub (Python FastAPI) | Runs on the PC (`127.0.0.1`, LAN, or Tailscale; never `0.0.0.0`), manages headless agent runs (`claude -p --output-format stream-json` or pluggable CLI commands), enforces ECDSA P-256 request/event signing and RFC 6238 TOTP sessions, relays dangerous-action approvals and redacted live screen frames (`/screen.jpg`), and hooks Claude Code's `PermissionRequest` prompt. Full guide (Vietnamese): [`hub/README.md`](hub/README.md). |
| `android/` | Turbo Remote (`dev.turbodesktop.remote`) | Kotlin + Jetpack Compose Android client (`minSdk 29`). Pairs via local QR code using non-exportable Android Keystore EC P-256 keys (plain + biometric-gated), dispatches tasks, answers approval prompts with cropped control previews, views redacted desktop frames with native-pixel pinch-to-zoom, inspects the audit log, and triggers emergency `STOP`. |
| `relay/` | Wake-on-LAN relay (Python stdlib) | Lightweight signed HTTP listener for an always-on LAN device (such as a Raspberry Pi or rooted tablet) to send magic packets when the PC is powered off over Ethernet. |

## How UIA automation saves tokens and avoids focus fights

1. `windows_list` enumerates top-level windows (`w1`, `w2`, ...) while hiding secret windows and flagging elevated processes (`elevated: true, actionable: false`).
2. `inspect_compact` walks the UIA tree on a dedicated COM thread and formats one line per actionable control (`[w1:e12] <Button> "Save"`), summarizing repeated sibling rows and supporting `onlyChanged: true` diffs (`*` added, `~` changed, `-` removed). Custom-drawn windows with an empty UIA tree automatically fall back to Windows OCR (`treeEmpty: true`, `[w1:oN]` click refs).
3. `act` and `batch_actions` invoke UIA patterns (`Invoke`, `Value`, `SelectionItem`, `Toggle`, `ExpandCollapse`, `Scroll`) first so the physical mouse cursor and window focus stay untouched (`via: "pattern"`). When an app requires simulated mouse or keyboard input (`via: "input"`), `desktop-mcp` waits until the owner has been idle for 5 seconds, pauses physical input with low-level hooks for that step (or the whole remote task), lights an orange border around every monitor, and restores focus afterwards.
4. All screen-derived text is wrapped in `<<<SCREEN_CONTENT ...>>>` boundaries so text inside untrusted documents or windows is marked as data.

## Security floor (active in every preset)

Turbo Desktop ships three presets (`easy`, `balanced`, `strict`, configured in `turbo-desktop.toml`), all sharing a non-configurable floor:

- Immediate `STOP` and owner takeover: `Ctrl+Alt+Shift+K` on the PC or the red `STOP` button in the Android app kills the agent job object and blocks every tool call until resumed. Pressing `Esc` three times within 1.5 s releases the physical input lock immediately (`owner_took_over: true`).
- Secret-window and password floor: UIA `IsPassword` fields are never read or typed (except via `$secret:NAME` local placeholders). Windows matching secret title patterns (`.env`, `credentials`, `.pem`, `.kdbx`, `password`, `api key`, password managers) and owner-approval dialogs (`Claude Code needs approval`, `Credential Dialog Xaml Host`) are denied across `inspect_compact`, `act`, `screenshot`, and OCR, and blacked out in `GET /screen.jpg`.
- Signed remote protocol: non-localhost requests require an ECDSA P-256 signature over `METHOD\nPATH?QUERY\nSHA256(body)\nTS\nNONCE` within a 60 s window, replay-checked nonces, and an active session (with single-use TOTP + biometric signature in `balanced`/`strict`). Hub responses and SSE events are signed by the hub's pinned P-256 key so the phone rejects spoofed endpoints. Pairing and admin routes reject proxy and tunnel headers.
- Hash-chained audit logs: both `desktop-mcp` and `hub` record every tool call, rule match, and approval decision in append-only JSONL chained with SHA-256 (`python -m turbo_hub verify-audit`).

## Quick start

### 1. Standalone MCP server (`desktop-mcp` only)

```powershell
cd desktop-mcp
python -m venv .venv
.venv\Scripts\python -m pip install -e .
claude mcp add turbo-desktop -e PYTHONPATH="$PWD\src" -e PYTHONUTF8=1 -- "$PWD\.venv\Scripts\python.exe" -m turbo_desktop
```

### 2. Full remote hub + phone pairing

```powershell
cd hub
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m turbo_hub setup
.venv\Scripts\python -m turbo_hub serve
```

In a second terminal, pair the Android app (`android\app\build\outputs\apk\release\app-release.apk`):

```powershell
hub\.venv\Scripts\python.exe -m turbo_hub pair
```

## Verification and test results

Tests use isolated C# WinForms/WPF fixture apps (`desktop-mcp/tests/fixtures/*.cs`), acquire a shared `%TEMP%\turbo-desktop-test.lock` so suites never collide, and default to `TURBO_DESKTOP_NO_INPUT=1` so your mouse, keyboard, and open windows are never touched during test runs:

```powershell
# 1. desktop-mcp unit and fixture integration suite (237 tests)
desktop-mcp\.venv\Scripts\python.exe -m pytest desktop-mcp\tests -q

# 2. hub and Wake-on-LAN relay suite (125 tests)
hub\.venv\Scripts\python.exe -m pytest hub\tests -q
hub\.venv\Scripts\python.exe -m pytest relay\tests -q

# 3. Android JVM unit tests and release APK (22 tests; requires JDK 17)
cd android
.\gradlew.bat :app:testDebugUnitTest :app:assembleRelease
```

Field validation (`FIELD_REPORT.md` and `desktop-mcp/FIELD_REPORT.md`, 20 Nov 2026): 29/30 desktop field tasks passed (UWP `CalculatorApp.exe` inside `exebox` desktop isolation is the single known skip), alongside full Android 16 emulator E2E verification of pairing, TOTP session start, strict approval allow/deny, `STOP`, `Esc` x3 takeover, TCP-proxy network drop reconciliation, and hub restart recovery.

## Known limits

- Elevated windows (`elevated: true`), UAC prompts, and the Windows lock screen cannot be driven from a non-admin process due to Windows UIPI and the secure desktop.
- Calling UIA `Invoke` on a WinForms `ToolStripMenuItem` that opens a modal dialog blocks inside the target app's modal loop; `act` returns after 2.5 s with `pending: true` and marks the process `blocked: true` until the modal closes. Prefer keyboard shortcuts such as `Ctrl+S` for menu items that open modal dialogs.
- Windows DPAPI (`CurrentUser`) protects stored hub keys against file copying to another machine, not against malware running under the same Windows user account.
- Wake-on-LAN requires wired Ethernet, BIOS/NIC magic-packet support, and an always-on device on the same LAN running `relay/wol_relay.py`.
