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

See `BENCH.md` and `FIELD_REPORT.md`. In short: custom-drawn controls only get OCR (slow, no values); programs started elevated cannot be driven; apps that restore a previous session on launch (Windows 11 Notepad) will show you your old tabs, so do not launch them on a PC with private tabs open; UIA Invoke on an item that opens a modal dialog can raise a COM error even though it worked.
