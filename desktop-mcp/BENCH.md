# desktop-mcp: measurements (17/11/2026)

Tokens are counted with tiktoken `cl100k_base` for the scripted runs (`tests/field/bench.py`) and estimated as chars/4 for the field runs. Only windows the run launched itself were touched.

## A. Scripted (no model in the loop): what the tools return

| Task | Tool calls | Response chars | ~Tokens | Wall | Success |
| :--- | ---: | ---: | ---: | ---: | :--- |
| (17/11) Form fill in the WinForms fixture (inspect + one batch: 3 fields, select, submit, delta) | 2 | 1,069 | 384 | 2.1 s | yes |
| (17/11) Calculator (12.5 + 7) x 3 (launch, inspect, one batch of 10 clicks, read display) | 4 | 1,992 | 714 | 1.9 s | yes (58.5) |
| (18/11, B4) Form fill, same steps; successful batch lists only steps with output | 2 | 1,043 | 377 | 2.0 s | yes |
| (18/11, B4) Calculator: launch returns the button snapshot, one batch of 10 clicks + read display | 2 | 1,737 | 621 | 1.8 s | yes (58.5) |
| (18/11, B4) Launch + snapshot of the editor fixture | 1 | 514 | 170 | 0.9 s | yes |

B4 changes behind the new rows: launch_app returns the first snapshot (no separate inspect), keeps watching for a launcher's real window and returns `pending` with a hint instead of an empty list; a successful batch returns `ran=N` and only the steps that carry output; Minimize/Maximize/Close buttons that WinUI apps draw outside a title bar are hidden unless the query asks for them (window_control does those); windows_list is one short line per window; wait_for defaults to 8 s and reports what it saw. Calculator went from 4 calls / 714 tokens to 2 calls / 621 tokens.

## B. Field runs: a real model (Claude Sonnet through `claude -p`, only desktop-mcp loaded) driving the tools

| Task | Tool calls (incl. 1 ToolSearch) | Tool-result tokens (est.) | Wall | Result |
| :--- | ---: | ---: | ---: | :--- |
| Calculator (12.5 + 7) x 3 | 6 | ~640 | 19 s | pass, answered 58.5 |
| Calculator: wait until ready, list buttons | 6 | ~420 | 19 s | pass |
| Fixture: 600-char value in a MaxLength=10 box | 8 to 17 | ~800 to 950 | 38 to 63 s | pass with a note (see report) |
| Fixture: password read and type | 6 | ~270 | 21 s | pass, both refused |
| Fixture: two windows, same title | 10 | ~530 | 20 s | pass, correct window used |
| Fixture: Submit under the Balanced preset, denied | 7 | ~320 | 103 s* | pass, click not done |
| Fixture: STOP during a batch with a wait | 5 | ~240 | 22 s | pass after fix |
| Fixture: minimized window | 8 | ~340 | 41 s | pass |
| Editor fixture: 3 Vietnamese lines | 7 | ~300 | 21 s | pass |
| Editor fixture: File > Save As dialog | 9 | ~640 | 110 s (timed out) | FAIL (open issue) |

\* includes the 6 s approval timeout and model latency, not tool time.

Model token usage (input/output) is in `tmp/field/results.jsonl`; wall time is dominated by model turns, not by the tools (the scripted runs show the tool side is about 1 s per task).

## C. Screenshot-based computer use, same tasks: ESTIMATE, not measured

No real computer-use run was available here, so this is arithmetic:

- One full-window screenshot at about 1280x720 costs roughly 1,200 to 1,600 input tokens (Anthropic's image-token formula, width x height / 750).
- A screenshot agent takes one screenshot per action. Calculator (12.5 + 7) x 3 needs 10 button presses plus one read: about 11 to 12 steps, so about 14,000 to 19,000 image tokens, before the model's own reasoning.
- The form-fill task: 6 to 8 steps, so about 8,000 to 12,000 tokens.

Against that, desktop-mcp returned about 700 (Calculator) and 400 (form) tokens of tool results in the scripted runs, and 240 to 950 in the field runs. That is a 10x to 30x difference in tool-result tokens. The comparison is rough: the screenshot agent also needs no setup and works on apps with no accessible tree, where desktop-mcp falls back to slower OCR.

## D. Not measured

Tasks that could not be run safely or at all on this PC are listed in `FIELD_REPORT.md` (Notepad restores the owner's open tabs, Settings would navigate the owner's open window, no Office/WordPad/Edge InPrivate/UAC trigger without touching the owner's session, real-input tasks skipped because the owner was active).

## E. Update 17/11 afternoon

- Explorer window with 200 files (field task 5): 4 tool calls, about 2,300 tokens of tool results, 16 s, correct. The listing is long because the list is not virtualised in Explorer's UIA tree; `query=` or `maxChars` cuts it. This is the largest single result measured.
- Real-input steps now add the lock (hook install about 20 ms) and the glow; not measured end to end because the end-to-end run (`tests/field/e2e_glow.py`) could not take the machine lock.
- The numbers in sections A to C did not change.

## F. Update 17/11 evening

Real-input field runs (Sonnet through `claude -p`):

| Task | Tool calls (incl. ToolSearch) | Tool-result tokens (est.) | Wall | Result |
| :--- | ---: | ---: | ---: | :--- |
| Ctrl+S on the editor, read the Save As dialog | 11 to 14 | ~1,500 to 1,660 | 32 to 44 s | pass |
| Ctrl+S after another window took focus | 10 | ~520 | 24 s | pass, focus change reported |
| OCR read and click on a custom-drawn window | 8 | ~340 | 25 s | pass |
| Real typing with UniKey running | 5 | ~120 | 22 s | pass |

The Save As dialog is the largest result (about 1,500 tokens) because a common file dialog exposes a full folder tree; `query=` or `maxChars` would cut it. The end-to-end run with edge screenshots and the three suite repeats are not measured (see FIELD_REPORT.md).

## G. Update 17/11 late

- `claude -p` (haiku) real-input end to end, 5 steps typed into the editor fixture: 28.9 s wall, glow and banner shown during, gone within 5 s after.
- Explorer: create a folder and rename it (task 4, the successful run): 17 tool calls, about 2,290 tokens of tool results, 38 s. The failed first attempts cost 12 calls for nothing; the cause was the key syntax and the missing window-level typing (findings 17 and 18).
- STOP during a real-input batch: 4 calls, about 145 tokens, 19 s.
- The input lock itself: lock on to off for one `press_keys` took 0.14 to 0.3 s in the audit log.

## H. Update 26/11/2026: Head-to-head measured benchmark (UIA Deltas vs Screenshot PNGs)

Reproducible script: `desktop-mcp/tests/field/bench_uia_vs_screenshot.py` (Windows 11, `turbo-desktop-mcp v0.1.0`, `TURBO_DESKTOP_NO_INPUT=1`, `TURBO_DESKTOP_APPROVAL=allow`). UIA text tokens are measured with `tiktoken` `o200k_base`; screenshot baselines capture actual PNGs via `Desktop.screenshot()` on the same windows and compute both exact window-crop vision tokens (`W * H / 750`) and standard `1280x720` desktop-capture vision tokens (`1,229` tokens/shot).

| Task | `turbo-desktop-mcp` (UIA + Delta) | Window-crop PNGs (exact dims) | Full `1280x720` PNGs | Token ratio (vs crop / vs 720p) | Payload bytes (UIA vs PNG) | Pass |
| :--- | ---: | ---: | ---: | ---: | ---: | :--- |
| 1. WinForms form fill (3 fields + Submit + verify) | 760 tok (4 calls) | 1,548 tok (6 shots, 460x420) | 7,374 tok | 2.0x / 9.7x | 2.1 KB vs 55.2 KB | yes |
| 2. 5-step stateful UI loop (click + delta diff) | 862 tok (12 calls) | 1,548 tok (6 shots, 460x420) | 7,374 tok | 1.8x / 8.6x | 2.5 KB vs 40.5 KB | yes |
| 3. Native editor multi-line Unicode write + readback | 456 tok (4 calls) | 1,092 tok (3 shots, 620x440) | 3,687 tok | 2.4x / 8.1x | 1.3 KB vs 17.4 KB | yes |
| 4. Custom-drawn canvas (no UIA tree, WinRT OCR fallback) | 235 tok (2 calls) | 125 tok (1 shot, 360x260) | 1,229 tok | 0.5x / 5.2x | 0.7 KB vs 3.4 KB | yes |
| **Total (4 tasks)** | **2,313 tok** | **4,313 tok** | **19,664 tok** | **1.9x / 8.5x** | **6.5 KB vs 116.4 KB (17.8x)** | **4/4** |

Notes:
- On standard WinForms controls (tasks 1 to 3), UIA compact snapshots plus delta diffs use 1.8x to 2.4x fewer tokens than tightly cropped small fixture windows (`460x420` to `620x440`), and 8.1x to 9.7x fewer tokens than `1280x720` full-desktop captures.
- On Task 4 (`360x260` custom-drawn canvas with an empty UIA tree), a tightly cropped PNG costs fewer tokens (125) than the WinRT OCR text output (235), though OCR returns clickable `@x,y` coordinates without requiring vision input.
