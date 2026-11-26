# Brief: Turbo Remote (Android) fixes from the 18/11 audit (frontend)

You can only read and edit files; you cannot run commands. The PM builds, runs the tests and the emulator, and sends failures back. Only edit `android/`. Do not read .env files.

Before editing, read and apply these skills, and name the ones you used in your final answer:
- `C:\Users\TRUNG THANH\.claude\skills\frontend-design\SKILL.md`
- `C:\Users\TRUNG THANH\.claude\skills\web-design-guidelines\SKILL.md`
- `D:\Project\thu-thach-1tr\07_cong-cu\design-skills\ui-ux-pro-max-skill\.claude\skills\ui-ux-pro-max\SKILL.md`

Then read `design/AUDIT_DEM_18-11.md` and `design/LIVE_V3.md`, and the Kotlin files you change. Keep the existing theme tokens (`LocalTurboColors`, `TurboType`, `TurboRadii`, `TurboSpacing`), Vietnamese + English strings in both `res/values*/strings*.xml` (escape apostrophes as `\'`), and performance rules from `android/PERF.md` (no always-running animations, read animated values in draw).

## Fix
1. Row 9: `CfLogin` WebView: set `webViewClient = WebViewClient()` and `settings.domStorageEnabled = true`; show a proper empty state (icon + one sentence + where to set the URL) when no Cloudflare URL is configured.
2. Row 16: Audit screen: readable lines for `cc_permission_requested` ("Claude Code xin chạy: <control>") and `cc_permission_resolved` ("<decision> bởi <phone|PC|Claude Code>"), include both in the approvals filter; map `whole_task`/`real_input` to the existing human strings.
3. Row 27: while `Graph.paused` is true, the header shows a paused state (warn colour dot, "Đã tạm dừng: bạn đang dùng máy") and the edge glow/indicator is idle.
4. Row 28: Settings relay field gets its own hint string; show success/error after relay pairing; adding a hub URL without a scheme prefixes `http://` instead of crashing (validate in the Settings action and guard `HubClient.build` against `IllegalArgumentException`).
5. Row 17: on the Welcome screen add one short line under the preset list: the PC's own preset (set during `turbo_hub setup`) wins after pairing. Do not change pairing protocol.
6. Row 30 (app part): in `Graph.kt` treat `via` values `input` and `ocr` as real input in the step labels.
7. Row 26 (app part): history items may now carry `answer` from `GET /tasks`; parse it and show it when the owner taps a past task, falling back to the current message if absent.
8. Approvals card: for `fromClaudeCode` approvals add a small "Claude Code" label chip at the top of the card (use existing chip styling) so it is clear the request is not from the PC agent.

## Tests
Add JVM unit tests in `android/app/src/test/java/dev/turbodesktop/remote/` for any pure logic you add (URL normalising, audit line mapping, history `answer` parsing). Keep them independent of Android framework classes (move logic into small pure functions if needed).

## Final answer
Changed files, tests added, skills applied, anything not done and why. Under 250 words.
