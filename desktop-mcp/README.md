# desktop-mcp

An MCP server that lets an AI drive Windows desktop apps through UI Automation (UIA), not screenshots. It works on its own: no hub and no phone are needed. Add it to Claude Code or Claude Desktop and go.

Tools: `windows_list`, `inspect_compact`, `act`, `batch_actions`, `launch_app`, `wait_for`, `window_control`, `screenshot`, `system_state`.

## Install

Needs Windows 10/11 and Python 3.12 or newer.

```powershell
cd desktop-mcp
python -m venv .venv
.venv\Scripts\python -m pip install mcp uiautomation pywin32 pillow winrt-runtime winrt-Windows.Media.Ocr winrt-Windows.Graphics.Imaging winrt-Windows.Storage.Streams winrt-Windows.Globalization winrt-Windows.Foundation winrt-Windows.Foundation.Collections
```

The server command is `python -m turbo_desktop` with `PYTHONPATH` pointing at `desktop-mcp\src` (or `pip install -e .`).

### Claude Code

```powershell
claude mcp add turbo-desktop -e PYTHONPATH=D:\path\to\desktop-mcp\src -e PYTHONUTF8=1 -- D:\path\to\desktop-mcp\.venv\Scripts\python.exe -m turbo_desktop
```

### Claude Desktop

Edit `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "turbo-desktop": {
      "command": "D:\\path\\to\\desktop-mcp\\.venv\\Scripts\\python.exe",
      "args": ["-m", "turbo_desktop"],
      "env": { "PYTHONPATH": "D:\\path\\to\\desktop-mcp\\src", "PYTHONUTF8": "1" }
    }
  }
}
```

### Any other MCP client

Run `python -m turbo_desktop` as a stdio server with the two environment variables above.

## How the AI uses it

1. `windows_list` to see windows (`w1`, `w2`, ...). `launch_app` starts one.
2. `inspect_compact(window)` returns one line per control: `[w1:e12] <Button> "Save"`, with values (`= "text"`) and states (`[checked]`, `[disabled]`). Refs stay stable between calls. After the first call, `onlyChanged=true` returns only new (`*`), changed (`~`) and removed (`-`) elements.
3. `act(ref=..., action=...)`: `click`, `invoke`, `type` (append), `set_value` (replace), `select`, `toggle`, `expand`, `focus`, `read`, `scroll`, `press_keys`, `send_text` (real typing, checked by read-back). UIA patterns are used first (`via: "pattern"`). Real mouse/keyboard input (`via: "input"`) is only a fallback and waits until you stop touching the PC.
4. `batch_actions(steps, returnSnapshot)` runs several steps in one call and stops at the first error.
5. If a window has no accessible tree (custom-drawn apps, games), `inspect_compact` reports `treeEmpty: true` and returns lines found by Windows OCR, such as `[w1:o3] text "Save" @412,230`. Clicking an OCR ref uses real input.

Everything read from a screen is wrapped in `<<<SCREEN_CONTENT ...>>>` markers: it is data, never instructions.

## Safety

Each action is allowed, asked about, or denied by rules (below). When the answer is "ask":

- With the phone app connected, the request goes to the phone.
- Otherwise a Windows box pops up with Yes/No. No answer in 2 minutes means No.

Always on, in code, not configurable: password-field values are never returned or typed, the STOP file (created by the hub's hotkey) blocks everything, and every action goes into an append-only, hash-chained audit log (`tmp/state/audit.jsonl`, or `TURBO_DESKTOP_AUDIT`).

Other behaviour:

- Real input is held back while you are using the mouse or keyboard (waits up to 10 s for 5 s of idle, then fails with "owner is using the PC"). It restores your previous foreground window and cursor afterwards.
- Windows of elevated programs are shown with `elevated: true, actionable: false` and are never acted on (Windows blocks it anyway).
- `system_state` reports a UAC prompt or lock screen (`secureDesktopActive`), idle seconds and battery.

## Input lock (real input only)

When the AI has to use the real keyboard or mouse (no UIA pattern available, OCR clicks, `press_keys`, `send_text`), your physical keyboard and mouse are paused for the length of that action, so you cannot knock it off course. No admin rights are needed: it uses low-level keyboard/mouse hooks and lets the AI's own injected input through. A banner at the top of the screen says so for as long as the lock is held ("AI đang điều khiển máy · bàn phím/chuột tạm khoá · Esc ×3 để lấy lại · Ctrl+Alt+Shift+K để dừng"), and a green notice shows when you get control back (there is no tray balloon: the banner itself is the notice). UIA-pattern actions never lock.

Ways out, always on, not configurable:

- **Ctrl+Alt+Shift+K**: STOP (creates the STOP file, releases the lock, blocks every further action).
- **Esc three times within 1.5 s**: you take over. The lock is released and the tool result says `owner_took_over: true`; the run pauses because the idle check now sees you.
- **Time limit**: the lock releases by itself after `max_seconds` (default 60, between 5 and 300).
- It is released in a `finally` and when the server exits.
- **Ctrl+Alt+Del cannot be blocked** by any program that is not a driver; it still works, and from there you can sign out or end the task.

Settings in `turbo-desktop.toml`:

```toml
[desktop.input_lock]
mode = "real_input"     # "off", "real_input" (lock per action), "whole_task" (stay locked between actions)
max_seconds = 60
```

Easy and Balanced default to `real_input`, Strict to `whole_task`. The banner cannot be switched off while the lock is held.

## Screen-edge glow

While the AI acts, the edges of every monitor glow orange, like Claude in Chrome does inside the browser, so you know to take your hands off the keyboard. It starts at the first `act`, `batch_actions`, `launch_app` or `window_control` call (pattern or real input), pulses gently, and fades out 3 s after the last action. Read-only calls (`windows_list`, `inspect_compact`, `screenshot`, `system_state`) never show it.

| AI acting | Input locked (frame is solid and brighter, text banner on top) |
| :--- | :--- |
| ![glow while acting](docs/glow_acting.png) | ![glow while input is locked](docs/glow_locked.png) |

(Illustrations drawn from the same frame bitmap the tool uses, on a plain background.)

It is one click-through, no-focus, no-taskbar-entry window per monitor, drawn per pixel with UpdateLayeredWindow, per-monitor DPI aware, and its topmost state is re-asserted every second so it survives the taskbar moving and most full-screen apps (a true exclusive-full-screen game can still cover it). With Windows "reduce motion" the frame is steady instead of pulsing; in high-contrast mode it turns yellow. It disappears on STOP, on Esc x3, on exit and if the process dies.

```toml
[desktop.indicator]
border = true            # false hides it for pattern-only actions; it still shows while input is locked or real input is sent
color = "#E0461D"
```


## Secret windows (always on)

A window whose title or document name looks like a secret (`.env`, `secret(s)`, `credentials`, `.pem`, `.key`, `id_rsa`, `.kdbx`, `token`, `password`, `mật khẩu`, `api key`) and any password-manager app is a deny zone in every preset. `windows_list` still lists it, but with the title "[hidden: secret window]". `inspect_compact`, `screenshot`, OCR, `read` and every `act` on it return `{"denied": "secret-window", "rule": "secret-window"}` with no contents, and the message never repeats the title. You can add your own patterns (`[desktop.secrets] patterns = ["payroll"]`), but the built-in ones cannot be removed or switched off.

`launch_app` returns only windows that did not exist before the call. If an app answers with a window that was already open (Windows 11 Notepad and Explorer do this), the result says `reused_existing_window: true` and gives no ref for it, unless you pass `returnExisting=true`.

## Editing the rules

The rules are data: `rules/default_rules.toml` (read the comments at its top). Each rule has an `id`, a `level` (`allow`, `ask`, `deny`) and matchers (process, window title, control name in Vietnamese and English, role, action, ...). The first match wins. A refusal or question always names the rule: `{"rule": "payment", ...}`.

Presets, chosen with `preset = "easy" | "balanced" | "strict"`:

| Preset | Asks before | Denies |
| :--- | :--- | :--- |
| easy (default) | permanent delete, payment, uninstall, Windows Settings accounts/privacy | password fields, password managers, UAC, Windows Security |
| balanced | the above, plus Send/Gửi/Delete/Xoá/Submit/Publish/Sign out/Install, shells, regedit, Task Manager, Enter in chat/mail | same |
| strict | the above, plus OK in a delete dialog, icon-only buttons and Enter in multi-line boxes of apps not on the allowlist, launching unknown apps | the above, plus banking apps |

Put your changes in `turbo-desktop.toml` (next to the repo, in your home folder, or the path in `TURBO_DESKTOP_CONFIG`). The preset can also be set with `TURBO_DESKTOP_PRESET`.

```toml
[desktop]
preset = "balanced"

# your own rule: checked before the defaults
[[desktop.rules]]
id = "ask-before-saving-invoices"
level = "ask"
process = ["excel"]
name = "^(save|lưu)$"
why = "Invoices are saved by me."

# change or switch off a default rule
[desktop.overrides.commit-buttons]
level = "allow"          # or: disabled = true

[desktop.apps]
allowlist = ["myerp"]     # apps the "unknown app" rules leave alone
```

Hub and scripts can call `turbo_desktop.security.classify(window, control, action)`; it returns `{"dangerous", "level", "rule", "reason"}`.

## Tests

```powershell
.venv\Scripts\python -m pytest            # unit + integration on the fixture apps in tests/fixtures
$env:TURBO_DESKTOP_REAL_INPUT = "1"; .venv\Scripts\python -m pytest   # also the tests that use the real mouse/keyboard
```

Tests only touch windows they start themselves (`tests/fixtures/*.exe`, built from the `.cs` files with `build.ps1`).

## Known limits

See `BENCH.md` and `FIELD_REPORT.md`. In short: custom-drawn controls only get OCR (slow, no values); programs started elevated cannot be driven; apps that reopen your previous files on launch (Windows 11 Notepad, Edge, Chrome, VS Code, Word, Excel; list in `[apps.session_restore]`) make those contents visible to the AI: Easy warns, Balanced asks, Strict asks and uses a clean launch for Notepad (new temp file) and VS Code (`--new-window` on a temp folder); UIA `Invoke` on a menu item that opens a modal dialog returns `pending: true` and then every UI Automation call into that app blocks until the dialog is closed; the tool reports `blocked: true` at once and the dialog can be closed with `window_control close` or `press_keys {Esc}` on it (prefer the menu's keyboard accelerator, e.g. Ctrl+S, over `Invoke` for such items). A UIA call into a hung app times out after 40 s (`TURBO_DESKTOP_CALL_TIMEOUT`) and the server carries on with a fresh worker thread.
