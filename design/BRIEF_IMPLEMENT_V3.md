# Brief: implement Turbo Remote UI (v2 + v3) in Jetpack Compose

The owner approved the v2 mockups and then asked for the v3 changes. Implement both: v3 wins wherever they conflict. You edit files only and cannot run commands. The PM builds, runs the tests and sends compile errors back.

A previous run of this job was interrupted. These files already exist from that run: android/app/src/main/java/dev/turbodesktop/remote/{Theme.kt,Components.kt,ScreensSetup.kt,ScreensMain.kt}, plus edits in Ui.kt, Graph.kt, Platform.kt, strings_ui.xml (vi, en) and build.gradle.kts. Read them first. Keep what is good, finish what is missing, and delete leftovers. The fonts are already in res/font/ (be_vietnam_pro_regular|medium|semibold|bold.ttf, jetbrains_mono.ttf).

## Read first
1. Design skills (apply them; name the ones you used in your final answer):
   - C:\Users\TRUNG THANH\.claude\skills\frontend-design\SKILL.md
   - C:\Users\TRUNG THANH\.claude\skills\web-design-guidelines\SKILL.md
   - D:\Project\thu-thach-1tr\07_cong-cu\design-skills\ui-ux-pro-max-skill\.claude\skills\ui-ux-pro-max\SKILL.md
   - D:\Project\thu-thach-1tr\07_cong-cu\design-skills\ui-ux-pro-max-skill\.claude\skills\design-system\SKILL.md
2. design/LIVE_V3.md: the behaviour behind v3, sections A to F.
3. v2 mockups: design/mockups/v2/*.svg, TOKENS.md and _sheet.png.
   - Screens 01–04: welcome, pairing, 2FA setup and expired, open session.
   - Screen 09: approval.
   - Screen 10: audit.
   - Screen 11: settings and language.
4. v3 mockups: design/mockups/v3/*.svg and _sheet.png.
   - Screens 12–15: the merged "Việc" screen (idle, running, done) and the full-screen player.
   - Screen 16: settings additions.
   - Screens 17–18: Báo cáo. If 17-18 are missing, follow LIVE_V3 section F.
5. Current code: android/app/src/main/java/dev/turbodesktop/remote/.
   - Graph.kt: state and actions.
   - HubClient.kt: signed calls. Do NOT change its signing logic.
   - Platform.kt: Biometric, Notifier, openInAuthenticator, copySensitive, AppLang.
   - Protocol.kt: Needs, TotpEnroll.
   - MainActivity.kt.
   - Strings: res/values/strings_ui.xml (vi, default) and res/values-en/.
6. Hub API you will call (already implemented in hub/turbo_hub/app.py; read it for the exact shapes):
   - `GET /policy`: needs, screenView {enabled,maxFps}, lockRemoteTask.
   - `GET /status`: the same, plus state.
   - `GET /screen.jpg?w=960&q=60`: in session; returns a JPEG with the `X-Redacted` header. The response is signed over the raw bytes (see sign_response). Answers 429 if polled faster than maxFps and 403 when the feature is off.
   - `POST /tasks`: 409 `{"detail":"busy"}` while a task runs.
   - `GET /report?days=1|7|30`: being added now. The shape is in design/BRIEF_B3_REPORT.md. Code against it.
   - TOTP enrol, events SSE, approvals, stop/resume/takeover, audit: as already used by Graph.

## Do
- **Navigation.** Bottom nav has 4 items: Việc · Duyệt · Báo cáo · Cài đặt. Setup flow: welcome → pairing → 2FA setup (only when needs.totp) → open session.
- **Việc screen (v3):**
  - Top: a 16:9 player. Poll `/screen.jpg` at maxFps while the screen is visible and the app is in the foreground. Stop polling when not visible. When idle, refresh once on open, then every 10 s.
  - Player controls: pause, tap to full screen (screen 15, landscape), and a "Đã che N cửa sổ bí mật" chip when X-Redacted > 0. Hide the player entirely if screenView.enabled is false.
  - Add a signed binary GET to HubClient (`callBytes`). It must reuse the existing request builder and response-signature check, without changing them, and verify the signature over the bytes.
  - Task card: the prompt (input), a status line ("Đang làm · bước N · m:ss"), and the PC-locked line while it runs. When done, the full answer (output) with "Sao chép" and "Giao lại".
  - "Chi tiết từng bước (N)" is collapsed by default. One line per step: icon, short label, time. Consecutive reads are grouped ("Đọc cửa sổ ×3").
  - Recent tasks: no token figures.
  - Composer pinned at the bottom. Disable it while sending or while a task runs ("Đang có việc chạy"). Handle 409.
  - "AI đang khởi động… (lần đầu có thể mất khoảng 1 phút)" if no event arrives within 3 s of sending.
  - Notification when a task finishes, using Notifier.
  - "Lấy lại quyền" button while running.
- **Báo cáo:**
  - Segment control at the top: Tổng quan (default) / Nhật ký.
  - Tổng quan uses `/report`:
    - period chips;
    - 3 stat tiles (tasks done; stopped or failed; time the AI worked);
    - a simple bar chart drawn with Canvas (no chart library);
    - tokens in plain words with the helper sentence from LIVE_V3 F;
    - top apps.
  - Dollar amounts appear only if the Settings toggle "Hiện chi phí quy đổi theo API" is on. Store it in prefs, default off.
  - Nhật ký is the v2 audit list.
- **Setup screens, approval and settings:** as v2.
  - 2FA key hidden by default.
  - 6-box code input with "Dán mã" and "Mở Authenticator".
  - Code field only when needs.totp. Biometric only when needs.biometric.
  - Settings has rows for: Language (bottom sheet; AppLang.set, then recreate the activity), Xác thực 2 bước, Xem màn hình PC, Khoá phím/chuột khi làm việc từ điện thoại, the cost toggle, the Xiaomi keep-alive guidance, and read-only safety rows from policy.
- **Theme** from v2 TOKENS.md. Material Symbols Rounded through `Icons.Rounded.*`; material-icons-extended must be in build.gradle.kts.
- **Strings:** every visible string goes in strings_ui.xml (vi) and values-en (en). No hard-coded UI text in Kotlin. Replace Graph.ENROLL_CLOSED_MSG with a resource.
- **Test tags.** Keep these on the equivalent elements for the instrumented tests: allow, approval, chipLocked, deny, level, preset0, preset1, preset2, resume, row_border, row_floor, stopCard, takeover, usePreset. Also keep the tags the old Ui.kt used where an equivalent element exists: sendTask, totp, openSession, status, usage, pairButton, pairPaste, pairCode, pairUrl, frame_*.
- **Accessibility:** 48dp targets, contentDescription on icon-only buttons, no fixed heights that clip text at large font scale.

## Do not
- Do not edit hub/ or desktop-mcp/, the signing logic in HubClient/Keys, or design/.
- No new network endpoints beyond those listed. No analytics. No placeholder numbers in shipped UI.
- If a mockup element has no backing data, leave it out and list it.

## Final answer
Files created or changed, skills applied, elements left out and why, anything the PM must do. Under 300 words.
