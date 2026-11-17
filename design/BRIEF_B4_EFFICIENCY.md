# Brief B4: make desktop-mcp + the hub agent faster and cheaper (fewer model turns, fewer tokens)

Owner's goal for every tool: fastest and fewest tokens. Score each change by **model turns per task** and **tool-result tokens per task**, not by elegance.

You can only read and edit files; you cannot run commands. The PM runs the tests and the benchmark (tests/field/bench.py, plus real tasks tonight) and will send numbers back.

## Evidence (real run, owner's phone task "mở zalo và xem tin nhắn từ marry pham", 17/11 19:00)
It took 3 min 9 s and 30+ tool calls:
- windows_list x3
- launch_app("zalo") failed: not on PATH. This is now fixed by Start Menu resolution.
- launch_app returned `{"ok":true,"windows":[]}` twice, each followed by a 20–25 s `wait_for` timeout.
- File Explorer was opened 3 times to hunt for the shortcut and the windows were left open.
- inspect_compact x6, including "Read 163 controls" on Zalo.
- One click by real input.

Also read:
- desktop-mcp/BENCH.md: Calculator is about 714 tokens in 4 calls.
- desktop-mcp/FIELD_REPORT.md
- The tool definitions cost about 1,550 tokens per session. That is fine; focus on per-turn results and turn count.

## Do (desktop-mcp, `src/turbo_desktop/`)
1. **launch_app returns a first snapshot.** Add `returnSnapshot: bool = True`, plus `snapshotQuery` / `snapshotMaxChars` (default 1500). When a new window appears, include the compact interactive snapshot of that window in the same reply, as `inspect_compact` would return it. That removes the launch → inspect round trip.
   - When `windows` is empty after the wait, keep watching for up to `wait` seconds for a new top-level window of the launched process **or** of the resolved app name. Apps like Zalo start through a launcher process.
   - Return `{"ok": true, "pending": true, "hint": ...}` instead of an empty list, so the model does not need its own `wait_for`.
2. **act and batch_actions:** make sure `returnSnapshot` exists, returns only the changed part (delta), and is documented as the default way to see the result. If a delta mechanism already exists, wire it in rather than duplicating it.
3. **windows_list compact output.**
   - Default to a short line format: `w3 Calculator [CalculatorApp] *focused`. Drop hwnd and pid unless `verbose=true`.
   - Skip tool-irrelevant windows by default (`hidden=false`): cloaked or zero-size windows, the shell tray, and the glow/banner windows desktop-mcp itself draws.
   - Keep the denied and secret markers.
4. **inspect_compact on big windows.**
   - When an interactive snapshot exceeds maxChars, summarise repeated siblings, for example "ListItem ×120 (first 8 shown; use query= to filter)", instead of cutting mid-list.
   - Keep refs stable so `onlyChanged` keeps working.
5. **wait_for:** default timeout 8 s, not 20–25 s. Report what it did see when it times out (window titles of the process) so the model can act without another windows_list.
6. **Tool docstrings:** lead with the cheapest correct pattern.
   - Example for launch_app: "launch_app returns the window snapshot; then one batch_actions with returnSnapshot".
   - Keep the total tool-definition size about the same or smaller.
7. **Tests:** add unit tests for every behaviour above in `desktop-mcp/tests/`, following the existing patterns and fixtures. Never touch windows the test did not launch. Update `tests/field/bench.py` so it reports calls, chars and tokens for: Calculator (12.5+7)*3, the WinForms fixture form, and launch + snapshot of the editor fixture.

## Do (hub, `hub/turbo_hub/runners.py`)
8. Extend `OPERATOR_PROMPT` with 3 short efficiency rules, about 60 words total:
   - launch_app already returns the window: do not inspect again;
   - chain steps in one batch_actions with returnSnapshot;
   - use `query=` on large windows and do not call windows_list when you already know the window id.
9. In `ClaudeRunner`, pass the environment variable `ENABLE_TOOL_SEARCH=false` to the claude process, so the MCP tools are loaded up front instead of costing a ToolSearch turn. Merge it with the existing env, and only when the user has not set it. Add a test that the spawned command env contains it.

## Do not
- Do not weaken the hard floor: secret-window deny zone, password values never returned, STOP, audit, input lock and glow.
- Do not change the hub's signing or session code, the android/ folder, or design/.
- Do not read .env files.

## Final answer
List the changed files, the tests added, and the expected effect per item: turns saved and tokens saved, as estimates labelled as such. Note anything unfinished. Under 300 words.
