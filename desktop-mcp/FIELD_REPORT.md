# Field report: desktop-mcp driven by a model through MCP (17/11/2026)

Method: `tests/field/run_field.py` starts `claude -p` (Sonnet) with only desktop-mcp in `--mcp-config`, no file or shell tools, empty working directory, so the agent cannot read the source. Each task is run on windows the run launched itself. Real-input tasks need the owner to be idle for 2 minutes. Runs hold the shared machine lock `%TEMP%\turbo-desktop-test.lock`.

## Counts (honest)

FIELD_TASKS.md lists 30 desktop tasks (31 to 34 belong to the hub and phone run). Of the 30:

- **Run: 12** (some with a changed target, noted below). **Pass: 11. Fail (open): 1** (task 21).
- **Tasks run on the fixtures, not on the app named in the task:** 17 (editor fixture instead of a rich edit), 19, 25, 27, 28, 29, 30. Task 28 was run under the Balanced preset on the Submit button (no real delete target), so it tests the ask/deny path, not deleting a folder.
- **Not run: 18.** Reasons:
  - Notepad (1, 2, 6, 21 as written, 25 as written): Windows 11 Notepad restores the owner's previous tabs on launch. A first attempt opened a window with the owner's own tabs (contents of private files were visible to the tool). I closed it at once, all tabs were unmodified, and I stopped using Notepad. This is a finding, see item 6.
  - Settings (9, 10): the owner's Settings window is open; launching `ms-settings:` would navigate it.
  - Apps not installed or not safe to start here (3 Paint, 11 Clock, 12 Photos, 13 and 14 and 24 as written VS Code, 15 Edge, 16 Word/WordPad, 7 Control Panel).
  - 4 and 5 and 22 (Explorer create/rename/context menu): not attempted for lack of time.
  - 23 (UAC): would need an elevated prompt on the owner's screen. Covered by unit tests of the deny rules and `system_state` only.
  - 20 and 26 (real input, focus change, DPI) and the OCR click test: `skipped-busy`, the owner was using the PC (idle under 2 min). The OCR text detection itself is tested without input; the OCR click test exists but only runs with `TURBO_DESKTOP_REAL_INPUT=1`.
  - 18 (Vietnamese IME double diacritics): UniKey/EVKey not running; `send_text` has a read-back check but the IME case is untested.

## Failures found and what happened

1. **Every UIA call through MCP failed with a blank "Error executing tool" (task 8).** The tools ran in the MCP server's worker thread, where COM was not initialised. Direct engine calls worked, so unit tests missed it. The tool result gave no cause. Fix: all UIA work now runs on one dedicated COM thread; unexpected exceptions are returned as JSON with the exception type. Regression: `tests/test_mcp_stdio.py` (full loop over a real stdio MCP session). Rerun of task 8: pass.
2. **600 characters in a MaxLength=10 box (task 19).** The tool set the value via UIA (`WM_SETTEXT` ignores MaxLength), result said ok with no length, so the model had to count 600 characters by hand and got it wrong twice. The tool did not lie, but it gave no way to verify. Fix: results carry `length`; `read` returns `length`. A new action `send_text` types through the real keyboard and compares read-back, failing with `truncated: true` when the field cut the text. Regression: `test_long_value_reports_length`, and the opt-in `test_real_typing_truncation_is_reported_truthfully`. Note: a human could not type 600 characters in that box; UIA can. This stays a decision for the caller.
3. **The approval box stayed on the owner's screen after a timeout (task 28).** With no phone connected the Windows Yes/No box timed out to Deny but remained open. Fix: after the timeout the box is closed with IDNO (a Yes/No box ignores WM_CLOSE). Regression: `test_local_prompt_timeout_closes_the_box`.
4. **STOP during a long `wait_for` was ignored (task 30).** My first version of the task finished before STOP existed, so it proved nothing; the second version waits. The wait kept polling until its own timeout. Fix: `wait_for` checks STOP every poll. Regression: `test_stop_during_wait_for_cancels_it`. Rerun: batch returned `emergency stop active: wait cancelled` after about 9 s instead of 25.
5. **Line breaks were shown as spaces (task 17).** The value in a result looked like one line. The model noticed from the character count. Fix: line breaks now show as `\n`.
6. **Windows 11 Notepad launches with the owner's old tabs.** Not a code bug, a hazard: any AI with this tool sees them. Noted in the README limits. A Strict-preset user may want a rule that asks before launching Notepad.
7. **Tests flaked because the owner typed into the fixture windows.** New windows take keyboard focus and the owner's keystrokes landed in them ("sau", "l?" in a text box). Fix: fixtures swallow real key messages unless started with `--accept-keys`, and `launch_app` starts apps with `SW_SHOWNOACTIVATE`. Three full runs in a row were green afterwards.
8. **OPEN: menu item that opens a modal dialog (task 21).** In a WinForms `ToolStripMenuItem`, UIA `Invoke` on "Save As..." never returns and the dialog never appears (also with LegacyIAccessible `DoDefaultAction`). `act` now returns after 2.5 s with `pending: true` and a warning instead of hanging, but the task cannot be completed through patterns. The documented workaround is a keyboard accelerator through `press_keys` (real input, owner must be idle). Not verified in the field because that needs real input.

## Cleanup, locking, config (coordination fixes at 12:30)

- Shared lock `%TEMP%\turbo-desktop-test.lock` is taken by pytest (session fixture) and by the field runner, with stale-pid takeover. Test: `tests/test_locking.py`.
- `Desktop.close_launched()` closes by window handle everything `launch_app` started (also UWP apps whose pid differs); used in the test teardown and at server exit. The field runner removes only CalculatorApp instances that did not exist before the run.
- Calculator windows and "Untitled - Notepad" seen on the owner's screen at 12:21 to 12:29: I cannot tell which Calculators were mine (my runs ended before 12:20 and killed the Calculators they started), and I never started the Untitled Notepad. I did not close anything I could not identify.
- Config lookup order is now shared with the hub: `TURBO_DESKTOP_CONFIG`, `.\turbo-desktop.toml`, `%APPDATA%\turbo-desktop\turbo-desktop.toml`, `~\turbo-desktop.toml`. Test: `test_config_lookup_order`.

## What the pass rate looks like

First pass: 8 pass, 3 fail (tasks 8, 19 as unverifiable, 30 as unproven), then 1 more fail (21). After fixes: 11 of 12 run tasks pass; the last one is an open limit. The curve stopped moving because the remaining tasks need real input or apps I could not safely start, not because the tools got everything right.

## Second round (17/11, after the session-restore rule, input lock and edge glow)

The owner was at the PC during this round (idle 3 to 90 s, never the 2 minutes the real-input tasks need), so most real-input tasks could not run. The runner now waits up to 5 minutes for the idle check, then marks the task `skipped-busy`.

| Task | Result |
| :--- | :--- |
| 5 Explorer, 200 files in a new window on `%TEMP%\turbo-field\big` | pass: first 5 names and the total (200) read correctly, 4 calls, but about 2,300 tokens of result (the list is long; `query=` or `maxChars` would cut it) |
| 21k Editor fixture, Ctrl+S to open Save As | FAIL, 2 findings below |
| 20 (focus change before Ctrl+S), cv (OCR click), 18 (UniKey/Telex typing), 30L (STOP with the input lock), 4 (Explorer create + rename), 22 (Explorer context menu) | `skipped-busy` (owner active) |
| 26 (second monitor / 150% DPI) | not testable: one monitor at 100% |
| 4 and 22 and 20 and 18 as written | prompts and fixtures are ready (`tests/field/run_field.py`); they run as soon as the PC is idle for 2 minutes |

New failures:

9. **`act(press_keys)` with only a window answered "need ref or name" (task 21k).** Keyboard shortcuts such as Ctrl+S belong to the window, not to a control. Fix: with no ref or name the keys go to the window itself. Regression: `test_press_keys_without_target_goes_to_the_window`.
10. **OPEN: after Ctrl+S the Save As dialog never showed up in `windows_list`, and every UIA call on the editor failed with a COMError** (the app is inside its modal loop). The tool returned `internal: true` with the raw COM code; it told the truth but gave no hint. Probable cause: the common dialog is a separate top-level window that the enumeration did not return, or it is cloaked while opening. Not reproduced yet because it needs real input and the owner was present. Next step: enumerate by process id including hidden/cloaked windows after a modal opens, and turn a COMError on a blocked window into "window is busy in a modal dialog".

Also from the owner's list this round: shared lock respected (the hub agent held it for long stretches; my runs waited), the field runner now refuses prompts that start a session-restore app, and the tool results for real input carry `owner_took_over` and `stopped`.

Counts after this round: **14 tasks run, 12 pass, 2 fail (21, 21k)**, 7 more `skipped-busy`, 1 not testable (26).

## Third round (17/11 afternoon): the Save As investigation, and what could not run

The owner left the PC (idle reached 700 s), but the machine-wide lock `%TEMP%\turbo-desktop-test.lock` was held for more than 17 minutes by pid 31232, which is the main session's long-lived `turbo-browser-mcp` node server, not a short task. A lock owned by a process that never exits cannot go stale, so I waited and did not break it (taking it would have let my focus changes land in the middle of the Chrome post it protects). That blocked every step that needs the screen: the remaining real-input field tasks, the `claude -p` end-to-end with edge screenshots, and the three stress runs. Their scripts are ready and have not been run: `tests/field/run_field.py 20 cv 18 30L 4 22` and `tests/field/e2e_glow.py` (writes edge strips to `field-shots/`).

What I did finish (all outside the lock, no real input, and the orphan `turbo_editor.exe` I found was mine and was closed):

- **Leftovers from the killed processes:** none. No glow window, no banner window and no hook outlived the killed `dlg.py` processes (checked with EnumWindows; the hooks are per process and Windows removes them with it). Documented in the inputlock docstring, and `test_hard_kill_takes_hooks_banner_and_glow_with_it` covers it (live test, skipped unless the owner is away; not yet run).
- **Item 10 (Save As dialog missing, COM errors): cause found.** Two causes:
  1. My editor fixture had no `[STAThread]` on `Main`, so `SaveFileDialog` never opened and the app hung in its handler. With the fixture fixed, the dialog appears and is listed by `windows_list` ("Save As"). That part was a fixture bug, not a tool bug.
  2. A real limit that the fixed fixture exposed: while an `Invoke` is pending (its handler opened a modal dialog), every UIA call into that app blocks until the dialog closes, including `ControlFromHandle` on the dialog itself. Fix: after a pending Invoke the app is marked blocked; `inspect`/`act`/`wait_for` on any window of that process now fail at once with `blocked: true` and the reason. `window_control close` (a window message, not UIA) and window-level `press_keys` still work, so the dialog can be closed. The MCP server also puts a timeout (`TURBO_DESKTOP_CALL_TIMEOUT`, 40 s) on every UIA call, abandons the stuck worker thread and starts a new one (`hung: true`), so one hung app can no longer freeze the whole server. Regression tests: `tests/test_modal.py`. The first run of these (17 passed, 1 failed on `window_control` being blocked too) led to the `uia=False` exemption; the corrected tests were queued behind the lock and have not completed.
- Fixtures now carry `[STAThread]`; rebuild with `tests/fixtures/build.ps1`.

## Final counts (honest)

Field tasks against FIELD_TASKS.md 1 to 30:

- **Run: 14. Passed: 12. Failed: 2** (21 via menu Invoke: a real UIA limit, now reported instead of hanging; 21k via Ctrl+S: failed only because of the fixture's missing STAThread, expected to pass now, not rerun).
- **Not run because the machine lock was held by the main session:** 20, OCR click (cv), 18, 30 with the lock (30L), 4, 22, 6.
- **Not run for other reasons:** 26 (one monitor, 100% DPI); 1, 2, 3, 6 (as written), 7, 9 to 16, 23, 24 (as written) because they would need Notepad without a clean launch, the owner's open Settings window, apps not installed, or an elevated prompt.
- **Automated tests:** last full run before the third round: 116 passed, 2 skipped. New tests since then (`test_modal.py`, hard-kill) are not part of a completed run. The three consecutive full runs the stress check asks for were not done. No flaky test was observed in the three full runs I did complete earlier (each 84 to 116 passed), but that is not the requested stress check.
