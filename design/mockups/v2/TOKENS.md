# Turbo Remote v2: design tokens

Source of truth for the Compose theme (`MaterialTheme(colorScheme, typography, shapes)` plus a small `TurboColors` for the roles M3 has no slot for). The mockups in this folder are generated from the same values (`_lib.py`). Regenerate: `python -X utf8 _generate.py && sh _render.sh`.

## Colour roles (dark only)

Contrast is WCAG 2.x, computed by script (see `_lib.py` values). AA needs 4.5:1 for text under 18.66 sp bold / 24 sp, 3:1 for large text and for icons and control boundaries.

| Role | Hex | M3 slot | Use |
| --- | --- | --- | --- |
| `bg` | #0F1114 | background, surface | screen |
| `surfaceContainerLow` | #16191D | surfaceContainerLow | bottom sheets |
| `surfaceContainer` | #1C2025 | surfaceContainer | list groups, cards, nav bar |
| `surfaceContainerHigh` | #242930 | surfaceContainerHigh | inputs, code blocks, avatar tile, selected preset |
| `surfaceContainerHighest` | #2D333B | surfaceContainerHighest | keycaps, step numbers, inactive progress |
| `onSurface` | #ECEAE4 | onSurface | main text (warm ivory) |
| `onSurfaceVariant` | #A9B0BA | onSurfaceVariant | secondary text, icons |
| `muted` | #8C95A0 | (custom) | meta, timestamps, placeholders. Not on `surfaceContainerHighest` (4.20) |
| `outline` | #6B737E | outline | input and outlined-button borders |
| `outlineVariant` | #2E343C | outlineVariant | dividers, timeline rail (decorative) |
| `primary` mint | #5CD6B0 | primary | OK, the one main action per screen |
| `onPrimary` | #04281F | onPrimary | text on mint |
| `primaryContainer` | #123A30 | primaryContainer, secondaryContainer | nav indicator, tonal buttons, "chain valid" |
| `onPrimaryContainer` | #9FF0D4 | onPrimaryContainer | text/icons on it |
| `ai` orange | #E0461D | (custom) | AI holds the PC: frame edge, live dot, "take over" button fill. Same colour as the PC screen border |
| `aiText` | #FF8A5C | (custom) | orange text (raw #E0461D is 4.56 on `bg` only, 3.95 on cards) |
| `onAi` | #1A0702 | (custom) | text on orange fill. White on orange is 4.15 and fails, the old build used it |
| `aiContainer` / `onAiContainer` | #3A1A10 / #FFB59C | (custom) | "input locked" banner |
| `stop` red | #FF5468 | error | STOP button only |
| `onStop` | #2B0508 | onError | text on STOP |
| `stopText` | #FF7A86 | (custom) | red text: "Đã dừng", unpair |
| `stopContainer` / `onStopContainer` | #3D1419 / #FFB3BA | errorContainer | stopped state |
| `warn` amber | #F2B84B | tertiary | needs your decision: approvals, Allow button, badge |
| `onWarn` | #2A1B00 | onTertiary | text on amber |
| `warnContainer` / `onWarnContainer` | #3A2C0E / #FFD98A | tertiaryContainer | countdown pill, "key window expired" |
| `inverse` / `onInverse` | #ECEAE4 / #0F1114 | inverseSurface | "Cho chạy lại" after STOP (deliberate, not mint) |

Checked pairs (all pass AA for their use):

| Pair | Ratio |
| --- | --- |
| onSurface on bg / on surfaceContainerHighest | 15.72 / 10.59 |
| onSurfaceVariant on bg / on surfaceContainerHighest | 8.65 / 5.83 |
| muted on bg / on surfaceContainerHigh | 6.23 / 4.82 |
| primary on bg / on surfaceContainerHigh | 10.54 / 8.15 |
| onPrimary on primary | 8.81 |
| onPrimaryContainer on primaryContainer | 9.49 |
| aiText on bg / on surfaceContainer | 8.14 / 7.05 |
| onAi on ai | 4.71 |
| onAiContainer on aiContainer; onSurface on aiContainer | 9.24; 13.07 |
| stopText on bg / surfaceContainer / stopContainer | 7.55 / 6.53 / 6.38 |
| onStop on stop | 5.96 |
| onStopContainer on stopContainer | 9.45 |
| warn on bg / surfaceContainer | 10.56 / 9.15 |
| onWarn on warn; onWarnContainer on warnContainer | 9.35; 10.05 |
| onInverse on inverse | 15.72 |
| outline on bg / surfaceContainerHigh (non-text, needs 3:1) | 3.94 / 3.05 |
| ai edge on bg (non-text) | 4.56 |

Meaning is never colour alone: every state also has an icon and a word (dot + "AI đang điều khiển", stop icon + "Đã dừng").

## Typography

Family: **Be Vietnam Pro** (OFL) for UI, **JetBrains Mono** (OFL) for the TOTP key, PC commands, timestamps and keycaps.

Why Be Vietnam Pro: designed by Vietnamese type designers for Vietnamese stacked diacritics (ể, ố, ữ sit cleanly at 12 sp where Roboto crowds), calm neo-grotesque shapes that suit the "Mac-like, understated" brief, static weights 400/500/600/700, Latin + Vietnamese subsets. Bundle it in `res/font/` (4 TTF ≈ 545 KB, JetBrains Mono variable 187 KB) instead of Google Fonts downloadable fonts: the downloadable provider needs Google Play services, which the owner's Xiaomi on a Chinese ROM may not have, and a silent fallback to Roboto would make the app look different on that phone. Files are in `_fonts/` with their OFL licences.

Mono: turn ligatures off (`fontFeatureSettings = "liga 0, calt 0"`), otherwise `--rotate` renders as a long dash. UI numbers use tabular figures (`"tnum"`) so timers and token counts don't jitter.

| Style | Size / line | Weight | Use |
| --- | --- | --- | --- |
| headlineMedium | 28 / 36 | 600 | onboarding and session titles |
| headlineSmall | 24 / 32 | 600 | tab titles ("Nhật ký"), state titles ("Đã dừng") |
| titleLarge | 20 / 28 | 600 | approval statement, preset name, sheet title |
| titleMedium | 16 / 24 | 600 | PC name, section titles, card titles |
| bodyLarge | 16 / 24 | 400 | task input, sheet options |
| bodyMedium | 14 / 20 | 400 | body copy, list primary (500 for list titles) |
| bodySmall | 12 / 16 | 400 | meta, helper text. Smallest size in the app |
| labelLarge | 14 / 20 | 500 | chips, list rows, small buttons |
| labelMedium | 12 / 16 | 500 | nav labels, eyebrows, step counter |
| button | 16 / 24 | 600 | 48/56 dp buttons |
| mono key | 20 / 28 | 500, +1 tracking | TOTP key, groups of 4 |
| mono code | 13 / 20 | 500 | commands |
| mono time | 12 / 16 | 400 | audit timestamps |

Sentence case everywhere ("Đã dừng", not "ĐÃ DỪNG"). STOP stays upper case because it is the button's name.

## Spacing

4 dp grid. Gutter 16. Inside cards 16. Between items in a group 8–12, between sections 24, title to its content 8–12. Bottom actions sit above the nav or gesture bar with 8–16 clear. List rows 56 (one line) / 64 (two lines), dividers inset 56.

## Shape

| Token | Radius | Use |
| --- | --- | --- |
| extraSmall | 6 | keycaps |
| small | 8 | filter chips |
| medium | 12 | inputs, OTP cells, code blocks, avatar tile, image crop |
| large | 16 | cards, list groups |
| largeIncreased | 20 | preset cards, approval card, state banners |
| extraLarge | 28 | bottom sheet top corners |
| full | 50% | buttons, pills, nav indicator, presence dot |

## Elevation

Flat, tonal only (no drop shadows on dark): bg < surfaceContainerLow < surfaceContainer < High < Highest. A thing that floats above content (bottom sheet) gets a 55 % black scrim. Selected preset = surfaceContainerHigh + 2 dp mint outline.

## Icons

Material Symbols **Rounded**, weight 400, grade 0, optical size 24. Outline by default, filled for the selected nav item and for status glyphs (check_circle, stop_circle, lock, gpp_maybe). Sizes: 24 nav and list leading, 20 inside buttons and cards, 18 in helper lines and chips, 16 in meta rows. Touch target ≥ 48 dp even when the glyph is 18–24. Compose: import the ~40 SVGs used (list in `_fetch_icons.py`, Apache-2.0) as vector drawables / ImageVectors. That keeps the APK small and matches the mockups exactly; `Icons.Rounded` from material-icons-extended is the older Material Icons set and differs in places. No text glyphs (▤ ▶ ✔ ☰ ⚙) and no emoji.

Nav: Việc `assignment`, Trực tiếp `desktop_windows`, Duyệt `verified_user`, Nhật ký `history`, Cài đặt `settings`.

## Components (as drawn)

- **Presence header** (main shell, every tab): PC tile + "PC-NHA · Tailscale" + one state line (dot + word) + STOP. It is the only place that states the AI's status, so tab titles never change with state (fixes "Đang chạy" header over a "Sẵn sàng" chip). STOP hides while stopped; the state line says "Đã dừng".
- **Frame edge** (signature): while acting, 3 dp orange edge + soft inner glow; while input is locked, 6 dp + stronger glow. Matches the PC border. Static under reduced motion, otherwise a slow breathe.
- **Navigation bar**: M3 Expressive short bar, 64 dp + system inset, 56×32 pill indicator, labels always shown (5 items, beginners), badge on Duyệt in amber.
- **Buttons**: 56 dp for the screen's main action, 48 dp secondary, 40 dp inline (send). One filled button per screen.
- **Settings policy rows** show the value as text ("Bật", "Tắt", "Luôn bật") instead of disabled switches, which read as "off".
- **Live log** shows sentences only (sum_* / verb_* strings); raw tool names and JSON live behind a tap in Audit.

## Motion

| Token | Duration | Easing | Use |
| --- | --- | --- | --- |
| short | 100 ms | standard | press feedback, chip select |
| medium | 250 ms | emphasized decelerate | sheet, banner in |
| exit | 200 ms | emphasized accelerate | sheet, banner out |
| long | 400 ms | emphasized | state change (acting → stopped) |
| edge breathe | 1600 ms per cycle | ease-in-out | orange edge while acting; none when locked (solid), none under reduced motion |
| timeline add | 250 ms | decelerate, 8 dp rise | new step |

## New or changed strings (vi; en needed too)

Changed: `sess_info2` split by state; `sess_button` = "Mở phiên" when no 2FA; `stop_title` sentence case; `fmtLeft` → "1 giờ 58 phút" (no "h"/"min"); `set_language` becomes a row "Ngôn ngữ" with values "Theo hệ thống", "Tiếng Việt", "English".

New: Thiết lập 2FA screen ("Thiết lập 2FA", "Khoá bí mật", "Hiện"/"Ẩn", "Thêm vào Google Authenticator", "Sao chép khoá", "Lấy được khoá trong %1$s nữa…", "Tôi đã thêm xong", "Mất 2FA? Trên máy tính chạy:", "Hết hạn lấy khoá", "Thử lại", "Tôi đã thêm từ máy tính"); "Đã ghép với %1$s"; "Dán mã", "Mở Authenticator"; "Sau đó xác nhận bằng vân tay…"; "Các bước", "Việc bị dừng", "Đang tìm mã QR…"; preset fact lines (split from `preset_*_desc`); audit filter chips "Tất cả / Hành động / Duyệt / Dừng" and human audit titles; settings groups "Trên điện thoại này", "Bảo mật · đặt trên máy tính", row "Xác thực 2 bước (2FA)" (same name the hub prints: "Cài đặt > Xác thực 2 bước"), "Chỉ đổi ngôn ngữ của ứng dụng này.", "Máy đang dùng: %1$s".
