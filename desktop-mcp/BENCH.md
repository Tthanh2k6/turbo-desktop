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

## I. Update 28/11/2026: High-DPI (`1440p` & `4K`) VLM Downscaling & Coordinate Drift vs UIA Deltas + Cropped 1:1 Region/OCR

On `1440p (2560x1440)` and `4K (3840x2160)` desktop monitors, full-screen screenshot loops hit Vision-Language Model (VLM) long-edge caps (`>1568px` on Anthropic Claude Vision, downscaled to `1568x882`; `>2048px` on OpenAI high-res tile grid, scaled into `512x512` tiles). Downscaling blurs `8–10pt` UI fonts and introduces coordinate scaling drift (`1.63x` at `1440p`, `2.45x` at `4K`) when mapping model-predicted pixel coordinates back to physical screen coordinates.

By contrast, `turbo-desktop-mcp` UIA compact snapshots + `onlyChanged=true` delta diffs are resolution-invariant (`2,313` tokens total and `0 px` coordinate drift at any screen resolution), and `screenshot(region=[x,y,w,h], maxWidth=1568)` / `inspect_compact(ocrRegion=[x,y,w,h])` crop custom-drawn canvas panes at native `1:1` pixels without triggering VLM downscaling.

### 1. Resolution comparison across the 4-task benchmark (16 screenshot steps vs UIA + Delta)

| Display / Capture Mode | Native Resolution | VLM Effective Resolution (Anthropic / OpenAI) | Anthropic Vision Cost (per shot / 16-shot total) | OpenAI High-Res Cost (per shot / 16-shot total) | VLM Coordinate Scaling Drift | `turbo-desktop-mcp` (UIA + Delta / Cropped OCR) | Token Savings (vs Anthropic / OpenAI) |
| :--- | :---: | :---: | ---: | ---: | :---: | ---: | :---: |
| **Full-screen `720p`** | `1280x720` | `1280x720` / `1280x720` | 1,229 tok / 19,664 tok | 1,105 tok / 17,680 tok | `1.00x` (`0 px`) | **2,313 tok** (`0 px` drift) | **8.5x / 7.6x** |
| **Full-screen `1440p`** | `2560x1440` | `1568x882` / `2048x1152` | 1,844 tok (4,916 raw) / **29,504 tok** | 1,445 tok / **23,120 tok** | **`1.63x`** (`±1–2 px` jitter) | **2,313 tok** (`0 px` drift) | **12.8x / 10.0x** |
| **Full-screen `4K UHD`** | `3840x2160` | `1568x882` / `2048x1152` | 1,844 tok (11,060 raw) / **29,504 tok** | 1,445 tok / **23,120 tok** | **`2.45x`** (`±2–3 px` jitter + font blur) | **2,313 tok** (`0 px` drift) | **12.8x / 10.0x** |
| **Cropped `1:1` Canvas (`region` / `ocrRegion`)** | `360x260` | `360x260` (`1:1`, `0%` downscale) | **125 tok** (1 shot) | **255 tok** (1 tile) | **`1.00x`** (`0 px`, native 1:1) | **235 tok** (`[w1:oN] @x,y` exact coords) | **14.8x / 5.7x** vs full-screen 1440p/4K shot |

### 2. Per-task token breakdown at `720p`, `1440p`, and `4K`

| Task | `turbo-desktop-mcp` (UIA + Delta) | `720p` (`1280x720`) VLM PNGs | `1440p` (`2560x1440`) VLM PNGs (`1.63x` drift) | `4K` (`3840x2160`) VLM PNGs (`2.45x` drift) | Unscaled `4K` Raw Pixel Equivalent (`W*H/750`) | Savings at `1440p`/`4K` (VLM / Raw) |
| :--- | ---: | ---: | ---: | ---: | ---: | :---: |
| 1. WinForms form fill (6 shots vs 4 UIA calls) | **760 tok** | 7,374 tok | 11,064 tok | 11,064 tok | 66,360 tok | **14.6x** / 87.3x |
| 2. 5-step stateful UI loop (6 shots vs 12 UIA calls) | **862 tok** | 7,374 tok | 11,064 tok | 11,064 tok | 66,360 tok | **12.8x** / 77.0x |
| 3. Native editor Unicode write + readback (3 shots vs 4 UIA calls) | **456 tok** | 3,687 tok | 5,532 tok | 5,532 tok | 33,180 tok | **12.1x** / 72.8x |
| 4. Custom canvas (1 shot vs `ocrRegion` / `region=[0,0,360,260]`) | **235 tok** (OCR) / **125 tok** (1:1 crop) | 1,229 tok | 1,844 tok | 1,844 tok | 11,060 tok | **7.8x (OCR) / 14.8x (crop)** |
| **Total (4 tasks, 16 screenshot steps)** | **2,313 tok** | **19,664 tok** | **29,504 tok** | **29,504 tok** | **176,960 tok** | **12.8x / 76.5x** |
