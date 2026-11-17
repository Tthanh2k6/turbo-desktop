# turbo-desktop: design (v0 prototype, 17/11/2026)

Goal: let an AI agent drive Windows desktop apps as fast and cheaply as turbo-browser-mcp drives web pages, and let the owner command, approve and watch it from an Android phone.

## Components

1. `desktop-mcp/` (Python 3.14, MCP stdio server): Windows UI Automation (UIA) instead of screenshots.
   - `windows_list` (top-level windows: handle, title, process, pid, focused).
   - `inspect_compact(window, mode=interactive|all, query?, onlyChanged?)`: compact tree of actionable controls with stable refs `[w1:e12] <Button> "Save"`, values for edits/combos/checkboxes, `[disabled]`, `[offscreen]`; after the first call `onlyChanged` returns only new/changed/removed elements (`*` marks new).
   - `act(ref|name+role, action=click|invoke|type|set_value|select|toggle|expand|focus|scroll|press_keys)`: prefer UIA patterns (Invoke, Value, SelectionItem, Toggle, ExpandCollapse, Scroll) so no real mouse/keyboard is needed; fall back to real input only when a pattern is missing, and say so in the result (`via: "pattern" | "input"`).
   - `batch_actions(steps[], returnSnapshot?)`: several steps in one call, stop on first error.
   - `launch_app(path|name)`, `wait_for(window title / element text / gone)`.
   - `screenshot(window, region?)` + OCR fallback only when the UIA tree is empty (custom-drawn controls); report `treeEmpty: true` so the agent knows.
   - Results are small JSON/text, no screenshots unless asked. Measure tokens per task.
2. `hub/` (Python, FastAPI on the PC): receives commands from the paired phone, runs the agent, streams progress, asks for approvals.
   - Binds to 127.0.0.1 and the PC's Tailscale IP (100.x) only. Never 0.0.0.0.
   - Runs a task with Claude Code headless: `claude -p "<task>" --mcp-config <desktop-mcp + turbo-browser> --output-format stream-json` (claude.exe lives in the VS Code extension folder `~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/` or similar; find it, do not assume PATH).
   - Streams events (tool calls, results, final answer) to the phone over SSE/WebSocket.
3. `android/` (Kotlin + Jetpack Compose, minSdk 29): the owner's remote control. It is NOT controlled by the AI.
   - Pair with the PC, send a task (text), watch the live log, approve or deny dangerous actions, see history and the audit log, emergency STOP button.

## Security model (owner decisions 17/11)

- Identity first: pairing proves the commander is the owner.
  - PC hub shows a QR (hub URL on Tailscale, hub public key, one-time 6-digit code, expires in 5 min).
  - Phone scans, creates its own keypair in Android Keystore (EC P-256, non-exportable), sends its public key + the code. Hub stores the phone key; PC shows "paired: <device name>".
  - Every request from the phone is signed (method, path, body hash, timestamp, nonce); hub rejects bad signatures, old timestamps (>60 s) and replayed nonces. Responses/events are signed by the hub key, phone verifies (no fake hub).
  - Sessions: after a valid signed `session/start`, a short-lived session (2 h). Unpaired devices: rejected and logged, PC shows an alert.
  - Unpair / revoke a phone from the PC (`python -m turbo_hub revoke <id>`) or from the phone itself.
- Per-action approval (owner: "duyệt theo hành động cũng được"): dangerous actions pause and push an approval request to the phone with the target window, control name and a cropped screenshot of the control; Allow / Deny; times out to Deny after 2 min.
  - Dangerous = clicking/pressing controls named like Send, Gửi, Delete, Xoá, Pay, Thanh toán, Buy, Install, Uninstall, Format, Shut down, Sign out, Submit, Post, Publish, Confirm/OK inside a dialog titled delete/remove/payment; typing Enter in a chat/email compose; any action in Windows Settings > Accounts/Privacy & security, Registry Editor, PowerShell/Terminal/cmd windows, Task Manager end task.
  - Ordinary actions (read, inspect, type into normal fields, scroll, open apps on the allowlist) are not asked.
- Always on, not configurable off:
  - Deny zones: password fields (UIA IsPassword: never read, never type; secrets only via `$secret:NAME` from a local file like turbo), Bitwarden/password managers, banking apps, UAC/secure desktop, Windows Security app.
  - Visible indicator while the agent acts: an orange glow on every screen edge plus a banner while input is locked (there is no tray icon).
  - Emergency stop: global hotkey Ctrl+Alt+Shift+K on the PC and STOP on the phone; kills the running agent process and blocks new actions until resumed from the phone.
  - Audit log: append-only JSONL, each line hash-chained to the previous (sha256), every action with window, control, action, result, approval id; thumbnails before/after for dangerous actions. Viewable on the phone.
  - Screen text is data, not instructions: wrap page/control text in content boundary markers like turbo.
- Key storage on PC: hub private key and paired-device list encrypted with Windows DPAPI (CurrentUser). Honest limit: malware running as the same Windows user can still use DPAPI; this only stops copying the file to another machine.

## Community direction (owner, 17/11 afternoon)

Audience: many users, from beginners to IT pros. The owner's strict setup becomes one preset.
- Config-driven: one commented `turbo-desktop.toml` plus a shipped `defaults.toml`, with rules in data files. Code stays plain, with no deep frameworks.
- Presets are picked in a first-run wizard, and every item can be switched individually afterwards:
  - **Easy (default):** local only, pairing optional, 12 h session, no TOTP, approval only for permanent delete, payment, uninstall and Windows security settings, deny zone = password fields.
  - **Balanced:** LAN or Tailscale, 2 h, TOTP on reopen, approval for send, delete, pay, install and terminal, deny zones add password managers and banking.
  - **Strict (owner):** biometric + TOTP, 2 h, full list, all deny zones, Cloudflare Access when tunnelled.
- Hard floor in every preset:
  - STOP;
  - audit log;
  - password values never reach the model;
  - non-localhost requests only from a paired device with a valid signature;
  - pairing only locally.
- Pluggable agent command (Claude Code default; Codex, Gemini CLI or a local model via a template) and connection list (`local`, `lan`, `tailscale`, `cloudflare`).
- desktop-mcp works standalone in any MCP client. With no phone, approvals fall back to a local Windows prompt.
- i18n vi/en. Android UI: SVG mockups in `design/mockups/` are reviewed before Compose code.
- The "always on" items in the security model above apply to Strict. Lower presets keep only the hard floor plus what the preset lists.

## hub + android v0: what was built (17/11)

- Wire format (hub `crypto.py`, Android `Protocol.kt`, shared test vectors): ECDSA P-256 over `METHOD
PATH?QUERY
SHA256(body)
TS
NONCE`; replies and SSE events signed by the hub key pinned at pairing; 60 s window; in-memory nonces plus "nothing signed before hub start".
- Two phone keys: a plain Keystore key for ordinary requests and a biometric-gated one (30 s window) for pairing, opening a session and answering approvals. Biometric is a preset option (Strict).
- Session = signed `session/start` + TOTP (Google Authenticator, RFC 6238, no reuse) when the preset says so; 2 h or 12 h; reopened from anywhere without a QR. Pairing only locally.
- Lockout (5 failures / 10 min, 15 min), 64 KB body limit, no unauthenticated endpoint except local pairing; tunnel headers are refused for pairing and admin.
- Approvals: desktop-mcp classifies and asks via files in `desktop-state/`, the hub relays to the phone; hub categories are the fallback (`approval.engine`). STOP file, RELEASE (take over), `input_lock.json` and `indicator.json` are the hub/desktop-mcp contract.
- One long-lived agent process (stream-json in/out), in a job object so it dies with the hub; pluggable command template.
- Wake-on-LAN relay in `relay/` (stdlib only, own pairing list). Config: `hub/turbo_hub/defaults.toml` + presets.
- Android UI (Compose, v3 design in `design/LIVE_V3.md`) is built: Việc, Duyệt, Báo cáo, Cài đặt, full-screen screen view with zoom.

## Out of scope for v0

Remote control of a different PC, iOS, controlling the phone itself, multi-user.

## Success measures

- desktop-mcp: 5 real tasks (Notepad write+save to a temp file, Explorer create folder + rename, Settings read display scale, Calculator compute, a small WinForms/WPF test app form fill) — tokens per task, tool calls, wall time, success, compared with screenshot-based computer use on the same tasks (estimate screenshot token cost per step if a real computer-use run is not available, and say it is an estimate).
- hub + android: pairing works on the Android 16 emulator over 10.0.2.2 (emulator) and is designed for Tailscale; signed requests verified; replay rejected; approval round-trip under 2 s locally; STOP kills a running task.
