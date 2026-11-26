# Brief: audit turbo-desktop, night of 18/11

You can only read files and write one file. Do not run commands. Do not read .env files.

## Goal
Make a prioritised list of missing features, bugs and improvements for turbo-desktop, with evidence. The PM will then assign the fixes.

## Read
- `DESIGN.md`, `FIELD_REPORT.md`, `FIELD_TASKS.md`
- `design/LIVE_V3.md`, `design/BRIEF_B1_HUB.md`, `design/BRIEF_B2_DESKTOP.md`, `design/BRIEF_B3_REPORT.md`, `design/BRIEF_B4_EFFICIENCY.md`, `design/BRIEF_IMPLEMENT_V3.md`
- `android/PERF.md`, `desktop-mcp/BENCH.md`, the README files
- Source: `hub/turbo_hub/*.py`, `hub/scripts/*.py`, `desktop-mcp/src/turbo_desktop/*.py`, `desktop-mcp/rules/default_rules.toml`, `android/app/src/main/java/dev/turbodesktop/remote/*.kt`, `android/app/build.gradle.kts`, `android/app/src/main/AndroidManifest.xml`
- Tests: `hub/tests/`, `desktop-mcp/tests/`, `android/app/src/test/`, `android/app/src/androidTest/`

## What to look for
1. Things a brief or design doc promised that the code does not do, or does differently. Quote the brief line and point at the code.
2. Bugs: wrong logic, unhandled errors, race conditions, resource leaks, Windows-specific issues, places where a failure is silently swallowed.
3. Security: anything that weakens the hard floor (STOP, hash-chained audit, signed non-local requests, local-only pairing, secret-window deny zone, passwords never reach the model, glow while locked or sending real input, owner-approval dialogs never answered by the AI).
4. Missing tests for important behaviour.
5. App UX gaps: strings that show raw keys, screens without empty/error states, accessibility.
6. Docs that are out of date with the code.

## Output
Write `design/AUDIT_DEM_18-11.md`, in English, plain markdown:

```
# Audit 18/11 (Gemini)

| # | Priority (P1 must fix / P2 should / P3 nice) | Area (hub / desktop-mcp / android / docs) | Kind (bug / missing / security / test / docs / ux) | What is wrong | Evidence (file:line, brief quote ≤15 words) | Suggested fix (1–2 sentences) | Effort (S <1h, M 1–3h, L >3h) | Owner (backend / frontend) |
```

Then a short section "Not sure" for items you could not confirm from the code.

Rules: only report what you can point to in a file. Do not invent line numbers; if unsure, give the function name. No code changes. At most 40 rows, most important first. Final answer: one line with the row count.
