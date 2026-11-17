# Field run: real tasks on real apps

There are two separate tracks:
1. **Tests** prove the code does what we think.
2. **Field runs** find what we did not think of.

With turbo-browser-mcp, most real bugs only showed up on live sites. Examples: a Lexical editor rejected fill, a 500-character limit made submit fail silently, a popover closed on blur, a stale page after a tab change, a modal hid the target, and the agent closed the last tab. This file is the desktop equivalent.

## Rules

- An agent drives the tools exactly as a user's AI would: through MCP (`claude -p` with only desktop-mcp loaded). It does not read the source and does not call engine functions directly.
- It only touches windows the run opened itself. If a task needs a dialog from an existing app, it opens a new instance.
- Work files live in `%TEMP%\turbo-field\`. The run never touches the owner's documents, accounts, chats or browsers.
- Real mouse and keyboard input runs only when the idle check says the owner has been away for 2 min or more. Otherwise those tasks are skipped and marked `skipped-busy`.
- Each task logs:
  - the task;
  - tool calls (count, tokens in/out where available, wall time);
  - success yes/no;
  - the first wrong thing seen (wrong element, silent no-op, wrong value, hang, crash);
  - and whether the tool's own result told the truth.
- Every failure becomes a numbered item in `FIELD_REPORT.md` with the exact call and result. It then gets a fix plus a regression test on a fixture app where possible. Rerun the failed task after the fix.

## 30 tasks (different kinds on purpose)

Win32 / classic:
1. Notepad: new tab, type 3 lines with Vietnamese diacritics, save as `%TEMP%\turbo-field\a.txt`, verify the file bytes. Notepad on Windows 11 is WinUI with tabs, and its launcher pid is not the window pid.
2. Notepad: Find & Replace a word, then undo.
3. Paint: new canvas, resize it to 800x600 through the dialog, then save as PNG.
4. Explorer (new window): create a folder, rename it, create a file, and switch to Details view.
5. Explorer: sort by size, then read the first 5 names from a virtualized list with 200 files the run created.
6. Common file dialog: Notepad Save As. Navigate by typing a path, then handle the overwrite confirmation.
7. Control Panel > Mouse: read the double-click speed and cancel without changing it.

UWP / WinUI:
8. Calculator: compute (12.5 + 7) × 3, read the result, and switch to Scientific mode.
9. Settings > System > Display: read the scale and resolution. Read only.
10. Settings: search "bluetooth" and read whether it is on. Do not toggle it.
11. Clock app: create a 1-minute timer, start it, then delete it. Delete has to ask under the Strict preset.
12. Snipping Tool or Photos: open an image the run created and read its dimensions.

Electron / Chromium (UIA is often weak here):
13. VS Code (new window, a temp folder): create a file, type code, save.
14. VS Code: open the command palette, run "Toggle Word Wrap", and verify.
15. Edge (new InPrivate window): open example.com and read the heading through UIA. The point is to see the limits.

Office-like / rich text:
16. WordPad replacement or Word if installed: bold a word.
17. A rich edit in the fixture app: select text with the keyboard and apply formatting.

Keyboard and input traps:
18. Type into a field while UniKey/EVKey (Vietnamese IME) is on. Detect it and avoid double diacritics.
19. Type a 600-character string into a field with a max length. The result must say it was truncated, not report success.
20. Press Ctrl+S on a window that lost focus to another one between calls. The tool must notice the focus change.

Dialogs, modals, popups:
21. App shows a modal (Notepad: close an unsaved file). Pick "Don't save". The modal must be found first.
22. A tooltip or flyout menu that closes when focus moves. Use a context menu in Explorer.
23. A UAC prompt (e.g. open Task Scheduler as admin). The tool must detect the secure desktop and stop. It must never try to click it.

Multi-window, DPI, timing:
24. App launch takes over 5 s (cold VS Code). `wait_for` must not time out early or return the splash screen.
25. Two Notepad windows with the same title. Act on the right one by handle.
26. A window on a second monitor or at 150% DPI. Clicks land in the right place (real input fallback).
27. A minimized window: restore it before acting, or say that it cannot.

Safety behaviour (must hold in the field, not only in tests):
28. Ask the agent to "delete the folder from task 4". Under Easy it asks locally (MessageBox). Under Strict it asks on the phone. Deny must leave the folder in place.
29. A password field (Windows Credential dialog, or the fixture login): reading returns no value, and typing is refused.
30. Press STOP (hotkey) during a long batch. Nothing runs after the hotkey, and the audit log shows the stop.

## Hub and phone field run (after the app builds)

31. Pair the Android emulator over 10.0.2.2, send task 8, watch it live, approve task 28, press STOP.
32. On the owner's real phone over Tailscale, when the owner is available: pair once, then reopen the session with TOTP.
33. Kill the network mid-task. The app must show a disconnect and must not show a fake success. On reconnect it shows the true state.
34. Restart the hub mid-session. Old nonces must be rejected, and the session either persists or needs a reopen, as the config says.
