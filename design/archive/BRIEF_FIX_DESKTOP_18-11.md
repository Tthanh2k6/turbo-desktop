# Brief: desktop-mcp fixes from the 18/11 audit (backend)

You can only read and edit files; you cannot run commands. The PM runs the tests and sends failures back. Do not read .env files. Only edit `desktop-mcp/`.

Read first: `design/AUDIT_DEM_18-11.md` (rows referenced below), then each file before editing. Add unit tests in `desktop-mcp/tests/` for every behaviour change. Tests must never touch windows they did not launch and must pass with `TURBO_DESKTOP_NO_INPUT=1` (no real mouse/keyboard); use monkeypatch/fakes like `tests/test_efficiency.py` and `tests/test_security.py`.

## Fix
1. Row 3 (security): in `Desktop.launch`, resolve the target first (`resolve_launch_target`), then classify with the resolved executable stem AND the matched display name, so "Bitwarden", "Windows PowerShell", "Registry Editor" or a session-restore app launched by Start Menu name hit the same deny/ask/session_restore rules as their exe. For a `.lnk`, use the shortcut's target exe if `resolve_launch_target` exposes it (read that function); otherwise match the display name against the rule's process list after folding (lowercase, no spaces). Test with a fake resolver: "Bitwarden" → denied; "Windows PowerShell" → ask/deny per the shells rule.
2. Row 5 (security): extract the password-field black-out used by `Desktop.screenshot` into one helper and call it in `_ocr_window` and `_thumb` before OCR/saving. In `server.py`, wrap `screenshot` in `_guard` like the other tools. Do not add new parameters to tool signatures (token budget). Test the helper with a fake image and fake rects.
3. Row 6 (security): add `PROMPT_TITLE.lower()` to `OWNER_APPROVAL_TITLES`; check `OWNER_APPROVAL_TITLES` in `classify_action` too (deny, rule `owner-approval`); pass `class_name=d.get("class")` from `Desktop.act`. Test.
4. Row 15: `rules.build_ruleset` falls back to top-level keys (`preset`, `input_lock`, `indicator`, `apps`) when `[desktop]` exists but lacks them. Test with a toml that has both `preset = "strict"` at top level and a `[desktop.secrets]` table.
5. Row 21: in local `whole_task` input-lock mode, keep the lock across model think time: raise the idle linger to 45 s for `whole_task` (keep 8 s for `real_input`). The hard cap `max_seconds` still applies. Test the chosen linger per mode.
6. Row 22: `_is_caption_button` hides a bare "Minimize"/"Maximize"/"Restore", but a bare "Close" only when its AutomationId is "Close" (read `ctrl.AutomationId` safely); "Close <window title>" stays hidden. Update `tests/test_efficiency.py::test_caption_buttons_hidden_unless_queried`.
7. Row 23: `Desktop.act` with neither `window` nor `ref` raises `ToolError("need window= or a ref like w1:e12")`; `_parse_ref` accepts "[w1:e12]". Test.
8. Row 24: `winsys.capture_window` frees GDI objects in `finally`.
9. Row 20 (desktop part): explicit `argtypes`/`restype` for `OpenInputDesktop`/`CloseDesktop` and other raw ctypes Win32 calls in `winsys.py` and `tests/locking.py` if present.

## Do not
Do not weaken the hard floor: secret-window deny zone, password values never returned, STOP, audit, input lock and glow, owner-approval deny zone. Do not change tool names or add tool parameters.

## Final answer
Changed files, tests added, anything not done and why. Under 250 words.
