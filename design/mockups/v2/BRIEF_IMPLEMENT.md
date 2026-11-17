# Brief: implement Turbo Remote UI v2 in Jetpack Compose

Owner approved the v2 mockups (17/11/2026). Implement them in the Android app. You edit files only; you cannot run commands. The PM builds and runs the tests after you finish and will send compile errors back to you.

## Read first
1. Design skills (apply them; name the ones you used in your final answer):
   - C:\Users\TRUNG THANH\.claude\skills\frontend-design\SKILL.md
   - C:\Users\TRUNG THANH\.claude\skills\web-design-guidelines\SKILL.md
   - D:\Project\thu-thach-1tr\07_cong-cu\design-skills\ui-ux-pro-max-skill\.claude\skills\ui-ux-pro-max\SKILL.md and ...\design-system\SKILL.md
2. The approved design: design/mockups/v2/*.svg (14 screens), design/mockups/v2/TOKENS.md (colour roles, type scale, spacing, radii, icons, motion, list of new/changed strings), design/mockups/v2/_sheet.png (all screens at once).
3. Product rules: DESIGN.md.
4. Current app code: android/app/src/main/java/dev/turbodesktop/remote/ (Ui.kt = all screens today; Graph.kt = state + actions; Platform.kt = Biometric, Notifier, openInAuthenticator, copySensitive, AppLang; Protocol.kt = Needs, TotpEnroll; MainActivity.kt), strings in android/app/src/main/res/values/strings_ui.xml (Vietnamese, default) and values-en/strings_ui.xml.

## Do
- Replace the UI with the v2 design. You may split Ui.kt into several files in the same package (e.g. Theme.kt, Components.kt, ScreensSetup.kt, ScreensMain.kt). Keep `fun App(activity: FragmentActivity)` as the entry point MainActivity calls.
- Theme: all colours, type scale, shapes, spacing from TOKENS.md as Compose tokens (one Theme.kt). Bundle the fonts: copy design/mockups/v2/_fonts/*.ttf into android/app/src/main/res/font/ with lowercase underscore names (be_vietnam_pro_regular.ttf, ..._medium, ..._semibold, ..._bold, jetbrains_mono.ttf) and build FontFamily from R.font. You cannot copy binary files with your tools: instead, write the list of copies needed into android/app/src/main/res/font/COPY_FONTS.txt (source -> target) and reference R.font names as if present; the PM copies them.
- Icons: Material Symbols Rounded via Compose `Icons.Rounded.*`. Add `implementation("androidx.compose.material:material-icons-extended")` to android/app/build.gradle.kts next to material-icons-core.
- Use the real state/actions only (no fake data): Graph.needs (show the 2FA code field only when needs.totp; biometric prompt only when needs.biometric), Graph.totpEnrollPending + Graph.fetchTotpEnrollment() for the 2FA setup screen (03a) and its expired state (03b, when it returns null after 403), openInAuthenticator(), copySensitive(), AppLang.current/set (recreate the activity after set), Graph.refreshPolicy() when the session screen opens, Graph.events/taskRunning/indicator/inputLocked/stopped/paused/pending/taskUsage/sessionUsage/dayUsage/status/via/online, sendTask, stop/resume/takeover, approvals, audit, refreshTasks.
- 2FA key starts HIDDEN (eye button reveals). 6-box code input with "Dán mã" (paste) and "Mở Authenticator".
- Live screen: one status in the top bar (Sẵn sàng / AI đang điều khiển / Đang khoá phím/chuột / Đã dừng), steps as a timeline (tick / orange dot for the current step / red for stop), orange screen edge when acting (pulsing) or locked (solid), "Lấy lại quyền" button. After a task is sent and no event arrives within 3 s show "AI đang khởi động… (lần đầu có thể mất khoảng 1 phút)". Final answer shown in full.
- Notification when a task finishes (use Notifier's status channel; add a small function in Platform.kt if needed; do not change signing code).
- Settings: Language row with bottom sheet (Theo hệ thống / Tiếng Việt / English), "Xác thực 2 bước (2FA)" row (state + "Thiết lập lại" which explains `python -m turbo_hub totp --rotate` and opens 03a if the window is open), safety rows shown as text "Luôn bật"/"Bật"/"Tắt" (read-only, from Graph.policy), Xiaomi/HyperOS keep-alive row (keep the existing guidance).
- Every visible string in strings_ui.xml (vi) and values-en (en). No hard-coded text in Kotlin. Replace Graph.ENROLL_CLOSED_MSG usage in the UI with a string resource (you may edit that one line in Graph.kt).
- Keep these testTags on the equivalent elements (instrumented tests use them): allow, approval, chipLocked, deny, level, preset0, preset1, preset2, resume, row_border, row_floor, stopCard, takeover, usePreset. Keep existing tags you find in Ui.kt where an equivalent element exists.
- Accessibility: 48dp touch targets, contentDescription on icon-only buttons, text contrast per TOKENS.md, respects font scale (no fixed heights that clip text).

## Do not
- Do not edit hub/, desktop-mcp/, HubClient.kt, Keys.kt, the request-signing logic, or anything under design/ except this folder's notes.
- No new network calls, no analytics, no placeholder numbers in shipped UI.
- Do not invent features that Graph does not support; if a mockup element has no backing state, leave it out and list it in your final answer.

## Final answer
List the files you created/changed, the skills you applied, mockup elements you left out and why, and anything the PM must do (font copies, gradle sync). Under 300 words.
