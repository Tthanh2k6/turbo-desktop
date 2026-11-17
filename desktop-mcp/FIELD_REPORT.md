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
