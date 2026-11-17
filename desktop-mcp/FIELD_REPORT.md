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

## Fourth round (17/11 evening): real-input tasks with the owner away, and the secrets zone

Real-input tasks ran whenever the owner was idle for 2 minutes and the machine lock was free.

| Task | Result |
| :--- | :--- |
| 21k Ctrl+S on the editor fixture (rerun after `[STAThread]`) | **pass**: Save As dialog listed, controls read (file name, type, Save/Cancel, folder tree), cancelled with Esc, app closed |
| 20 Ctrl+S after another window took the focus | **pass**: the result carried `focus: "the window was not in front (front was '...'); brought it to the front first"`, dialog opened |
| cv OCR click on the custom-drawn canvas | **pass**: window read via screenshot + OCR (`treeEmpty`), click on the "Save" OCR ref changed the title to "TurboCanvas clicked" |
| 18 real typing with UniKey running | **pass, with a caveat**: `send_text "doodle aa dd"` read back exactly; no double diacritics appeared. UniKeyNT was running but its Telex state is unknown (or it ignores injected key events), so the IME-transformation case is not proven either way. The read-back check would have reported a mismatch |
| 30L STOP during a batch with real input and the input lock | `skipped-busy` |
| 4 and 22 Explorer create/rename and context menu | `skipped-busy` |

New findings:

11. **`{{Esc}}` crashed `press_keys` with a raw `TypeError: ord() expected a character` (tasks 20, 21k).** My prompt used template-style double braces and the model sent them as written. Fix: double braces are read as single (`{{Esc}}` = `{Esc}`, noted in the result) and any other bad key syntax returns a clear `invalid keys` error. Regression: `test_normalize_keys_accepts_double_braces`. The runner prompts had the same typo and were corrected.
12. **Task 20: the tool brought the right window to the front silently, so the model could not tell.** The result now says when the window was not in front and what was. Verified in the field run above.
13. **The field runner held the shared lock while it waited for the owner to leave, and the hub agent's back-to-back runs starved it in return.** Now the runner waits for the owner first without any lock, then takes the lock for one task at a time (`run_field.py` main loop). The starvation from the other side is not solved by the lock alone: polling every 10 to 30 s loses to a process that re-takes it at once. A fair queue (a `.waiting` file) would fix it; not built.
14. **Secrets deny zone (hard floor, in code, every preset).** After the hub run at 12:27 returned the owner's `.env - Notepad` window to an agent: titles matching `.env`, `secret(s)`, `credentials`, `.pem`, `.key`, `id_rsa`, `.kdbx`, `token`, `password`, `mật khẩu`, `api key`, and password-manager apps are listed as "[hidden: secret window]" and every inspect/screenshot/OCR/read/act returns `{denied: "secret-window", rule: "secret-window"}` with no contents and no title in the message. Users can add patterns, not remove built-ins. While writing its test I found the first version leaked the matched pattern in `windows_list`; fixed. Tests: `tests/test_secrets.py` (27, including a fixture window titled `.env - Notepad`, through the MCP functions, and all three presets). Known false positives: any title containing "token" or "password", by design.
15. **`launch_app` could hand back a window that already existed.** Now only windows that did not exist before the call are returned. If the app answered with an existing window (single-instance apps) the result says `reused_existing_window: true` with no ref unless `returnExisting=true`. Tests with a faked launch.

My own mistake during the secrets work: an early draft of a test called `inspect` with an id from a different Desktop object and read one owner window (read-only, nothing printed or stored) before I changed it to `process:turbo_editor`.

## Final counts

- **Field tasks 1 to 30:** 15 run, 14 pass, 1 fail (task 21 via menu `Invoke`: a real UIA limit, now reported at once instead of hanging, with a documented workaround). Not run because the lock or the owner was in the way: 30L, 4, 22, task 6, and `e2e_glow.py` (the `claude -p` real-input end-to-end with edge screenshots; the script is ready and skips itself unless the owner has been idle for 2 minutes). Not run for other reasons: 26 (one monitor at 100%), 1, 2, 3, 7, 9 to 16, 23, 24 as written (Notepad without a clean launch, the owner's Settings window, apps not installed, an elevated prompt).
- **Automated tests:** last full run 116 passed, 6 skipped (the skips are live hook tests that need the owner away and the opt-in real-input tests); `tests/test_secrets.py` 27 passed in a separate run afterwards; `test_modal.py` passed inside the full run. **The three consecutive full runs for the stress check were not done**: each full run takes about 4 to 6 minutes of the shared lock and the hub agent kept it. Across the runs that did complete I saw no flaky failure apart from the ones already fixed (owner keystrokes, foreground checks).
- To finish: with the lock free and the owner away, run `python tests/field/run_field.py 30L 4 22`, `python tests/field/e2e_glow.py`, then `python -m pytest` three times.

## Fifth round (17/11, 16:30 to 17:10): the remaining real-input tasks, the end-to-end run and the stress check

All of these ran with the machine lock taken per run and released afterwards; the owner was at the PC on and off, so each real-input run waited for 2 minutes of idle first.

| Item | Result |
| :--- | :--- |
| `e2e_glow.py`: `claude -p` (haiku) types a 5-step real-input task into the editor fixture | **pass**: the model's read-back was `one`, `two`, `three`; the edge glow was seen during the run and was gone 5 s after; the lock banner was seen during the run and was gone after. Edge strips (top strip with banner, top strip, left strip; not full-desktop shots) are in `field-shots/`. The sampler also flagged "physical input" on every sample, but that is our own injected typing resetting Windows' idle timer, so it proves nothing about the owner |
| 30L: STOP while a real-input batch runs | **pass** (second attempt): step 0 real input `ok` (audit: lock on 0.14 s, off, 4 injected events passed, 0 physical swallowed), step 1 `wait_for` cancelled with `emergency stop active: wait cancelled`, batch stopped, `window_control close` then refused (STOP blocks everything). The first attempt was invalid: STOP fired on a wall-clock timer before the batch started and the model passed an invented `real` field; both fixed (STOP now fires 2.5 s after the lock first appears in the audit log; a bad step field returns `bad step arguments ... Valid fields`) |
| 4: Explorer new window on `%TEMP%\turbo-field\explorer-a`, create a folder, rename it | **pass** on disk (`turbo-renamed` exists next to `readme.txt`), after two failed attempts that found real problems, below |
| 22: Explorer context menu | **fail, open limit**: `Shift+F10`, `Apps` and `Ctrl+Space` were sent, but the menu never appeared in the UIA tree, in `windows_list` or in a screenshot (the Win11 Explorer menu is a transient popup window outside the app window's tree). Not solved; documented |
| 6 (Save As with type-a-path and overwrite confirmation) | not run: the dialog opens (task 21k) but the type-a-path and overwrite steps were not written as a task |
| Stress check: three consecutive full runs under the lock | **3 of 3 green: 155 passed, 8 skipped each, no failures, no flaky test** (the 8 skips: 6 live input-hook tests because the owner was at the PC, 2 real-input opt-ins). One more run after the last code changes was queued behind the hub agent's lock (see the end) |

Findings:

16. **The whole MCP server crashed ("Connection closed") when two real-input actions came within 2.5 s (task 4, `windows_list` after the fourth action).** Cause: the input lock started a new thread per acquire; a second acquire inside the first lock's end-notice linger replaced the callback references that the first thread's still-open banner window used, so Windows called freed memory. It never showed before because the end-to-end run's actions were seconds apart. Fix: one persistent thread for the life of the process serves every acquire and release (hooks, banner and timers). Regression test: `test_rapid_reacquire_inside_the_end_notice_does_not_crash` (8 acquire/release cycles 0.4 s apart in a subprocess, must exit 0 and end unlocked), which I ran by hand because the owner was at the PC and it is a live test.
17. **Models write key chords in their own syntax** (`Ctrl+Shift+N`, `Enter`, `F2`) and `press_keys` typed them as literal text into Explorer. `Ctrl+Shift+N` is now translated to `{Ctrl}{Shift}n`, `Enter` to `{Enter}`, `F2` to `{F2}`, `{{Esc}}` to `{Esc}`; plain text is untouched. Tests: `test_normalize_keys_models_syntax` (12 cases).
18. **`send_text` / `type` with only a window answered "need ref or name"**, so a model could not type into Explorer's inline rename box (not an addressable control). `send_text` with no target now types into the window with the keyboard (window brought to the front, owner-idle and lock rules apply). A COM error from an element that refuses a pattern call now says to use `send_text`. Test: `test_send_text_without_target_types_into_the_window`.
19. **Runner:** a pytest run (`test_session_restore`) appended `refused-session-restore` lines for a fake task to the real `results.jsonl`; harmless, noted.

## Final counts

- **Field tasks 1 to 30 (distinct tasks run):** 17 run (8, 24, 19, 29, 25, 28, 30, 27, 17, 21, 5, 21k, 20, cv, 18, 30L, 4), **15 pass, 1 fail (21, menu `Invoke` opens a modal: a UIA limit, now reported at once), plus 22 failed** (Explorer context menu): so 15 pass, 2 fail among those 17. Not run: 6 (type-a-path and overwrite confirmation not written), 26 (one monitor at 100%), 1, 2, 3, 7, 9 to 16, 23, 24 as written, for the reasons given in the first report (Notepad without a clean launch, the owner's Settings window, apps not installed, an elevated prompt).
- **Real-input end-to-end through MCP with edge screenshots:** pass.
- **Automated tests:** 3 consecutive full runs, each 155 passed, 8 skipped, 0 failed. Skips: 6 live hook tests (they run only when the owner has been idle 20 s; two of them, the rapid re-acquire and the hard-kill test, were verified by hand), 2 opt-in real-input tests.

Addendum (17:15): the fourth full run, after the last code changes (persistent lock thread, key chords, window-level `send_text`), finished green: **156 passed, 8 skipped, 0 failed** (it spent 13 of its 13 minutes waiting for the shared lock). Across the four full runs of this round: 155, 155, 155, 156 passed, no failures, no flaky test. The flag file `%TEMP%	urbo-desktop-desk-done.flag` has been written.
