# desktop-mcp: measurements (17/11/2026)

Tokens are counted with tiktoken `cl100k_base` for the scripted runs (`tests/field/bench.py`) and estimated as chars/4 for the field runs. Only windows the run launched itself were touched.

## A. Scripted (no model in the loop): what the tools return

| Task | Tool calls | Response chars | ~Tokens | Wall | Success |
| :--- | ---: | ---: | ---: | ---: | :--- |
| Form fill in the WinForms fixture (inspect + one batch: 3 fields, select, submit, delta) | 2 | 1,069 | 384 | 2.1 s | yes |
| Calculator (12.5 + 7) x 3 (launch, inspect, one batch of 10 clicks, read display) | 4 | 1,992 | 714 | 1.9 s | yes (58.5) |

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
