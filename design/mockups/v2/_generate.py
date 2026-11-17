"""Turbo Remote v2 mockups. Run: python -X utf8 _generate.py  (writes NN-*.svg and _sheet.html next to this file).
Vietnamese text comes from res/values/strings*.xml where a string exists; new strings are listed in TOKENS.md."""
import base64
from _lib import *  # noqa: F403  (drawing kit + tokens)

SCREENS = []


def screen(key, title):
    def deco(fn):
        SCREENS.append((key, title, fn))
        return fn
    return deco


# ===================================================================================== 01 welcome
@screen("01-welcome", "01 Chào mừng: chọn mức bảo mật")
def welcome(s):
    s.status_bar()
    s.rect(16, 46, 32, 32, PRIMARY_C, 10)
    s.icon("desktop_windows", 32, 62, 18, ON_PRIMARY_C, filled=True)
    s.t(58, 52, "Turbo Remote", "titleMedium", ON)
    s.t(16, 96, "Bước 1 trên 3", "labelMedium", ON_VAR)
    for i in range(3):
        s.rect(108 + i * 82, 102, 74, 4, PRIMARY if i == 0 else SC_HIGHEST, 2)
    y = s.t(16, 128, "Chào mừng", "headlineMedium", ON)
    y = s.para(16, y + 4, "Chọn mức bảo mật. Đổi lại bất cứ lúc nào.", "bodyLarge", ON_VAR)
    y += 16
    # selected preset, expanded
    top = y
    facts = [("wifi", "Cùng mạng Wi-Fi với máy tính, ghép một lần"),
             ("schedule", "Phiên 12 giờ, không cần mã Authenticator"),
             ("verified_user", "Chỉ hỏi trước khi xoá vĩnh viễn, thanh toán, gỡ phần mềm, đổi cài đặt bảo mật Windows")]
    fy = top + 84
    heights = []
    for _, f in facts:
        heights.append(len(wrap(f, 14, 236)) * 20)
    card_h = 84 + sum(heights) + 8 * (len(facts) - 1) + 20
    s.rect(16, top, 328, card_h, SC_HIGH, 20, stroke=PRIMARY, sw=2)
    s.icon("radio_button_checked", 44, top + 32, 24, PRIMARY, filled=True)
    s.t(68, top + 18, "Thoáng", "titleLarge", ON)
    cw = tw("Dễ dùng, mặc định", 12, 500) + 20
    s.rect(68, top + 50, cw, 24, PRIMARY_C, 12)
    s.t(78, top + 54, "Dễ dùng, mặc định", "labelMedium", ON_PRIMARY_C)
    for (ic, f), hgt in zip(facts, heights):
        s.icon(ic, 80, fy + 10, 18, ON_VAR)
        s.para(100, fy, f, "bodyMedium", ON, maxw=232)
        fy += hgt + 8
    y = top + card_h + 12
    for name, tag in (("Cân bằng", "Cho điện thoại ở nhà hoặc qua Tailscale"), ("Chặt", "Cách bảo mật của chủ dự án")):
        s.rect(16, y, 328, 64, SC, 20)
        s.icon("radio_button_unchecked", 44, y + 32, 24, ON_VAR)
        s.t(68, y + 10, name, "titleMedium", ON)
        s.t(68, y + 36, tag, "bodySmall", ON_VAR, maxw=260)
        y += 72
    s.para(16, y + 4, "Từng mục vẫn bật hoặc tắt riêng được trong turbo-desktop.toml trên máy tính", "bodySmall", MUTED)
    s.button(16, 700, 328, "Dùng mức Thoáng")
    s.gesture_bar()


# ===================================================================================== 02 pairing
def qr(s, x, y, size, seed=7):
    n = 21
    c = size / n
    rnd = seed
    s.rect(x - 6, y - 6, size + 12, size + 12, "#D9D6CF", 4)
    for i in range(n):
        for j in range(n):
            rnd = (rnd * 1103515245 + 12345) & 0x7FFFFFFF
            finder = (i < 7 and j < 7) or (i < 7 and j >= n - 7) or (i >= n - 7 and j < 7)
            if finder:
                a, b = i % 14 if i < 7 else i - (n - 7), j % 14 if j < 7 else j - (n - 7)
                on = a in (0, 6) or b in (0, 6) or (2 <= a <= 4 and 2 <= b <= 4)
            else:
                on = (rnd >> 7) & 1
            if on:
                s.rect(x + j * c, y + i * c, c + 0.2, c + 0.2, "#16181B")


@screen("02-pairing", "02 Ghép với máy tính (quét QR)")
def pairing(s):
    s.status_bar()
    s.stepper(2)
    y = s.t(16, 96, "Ghép với máy tính", "headlineSmall", ON)
    y = s.t(16, y + 2, "Làm một lần, ngay tại máy tính", "bodyMedium", ON_VAR)
    y += 20

    def step(n, top, label):
        s.circle(28, top + 12, 12, SC_HIGHEST)
        s.text(28, top + 16.5, str(n), 12, ON, 600, "middle")
        return s.para(50, top + 2, label, "bodyMedium", ON, maxw=290)

    step(1, y, "Trên máy tính chạy:")
    s.code(16, y + 32, 328, "python -m turbo_hub pair")
    y += 96
    y = step(2, y, "Hướng camera vào mã QR trên màn hình máy tính") + 12
    # viewfinder
    vh = 300
    s.rect(16, y, 328, vh, "#07080A", 20)
    s.rect(52, y + 28, 256, 176, "#1E2226", 10)          # PC screen in the camera view, slightly out of focus
    s.rect(52, y + 196, 256, 8, "#2A2F35", 4)
    qr(s, 128, y + 54, 104)
    bx, by, bs = 108, y + 34, 144
    for (cx, cy, dx, dy) in ((bx, by, 1, 1), (bx + bs, by, -1, 1), (bx, by + bs, 1, -1), (bx + bs, by + bs, -1, -1)):
        s.add(f'<path d="M{cx} {cy + 26 * dy} V{cy} H{cx + 26 * dx}" fill="none" stroke="{PRIMARY}" '
              f'stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>')
    s.rect(32, y + vh - 52, 296, 36, SCRIM, 18, op=0.6)
    s.icon("qr_code_scanner", 54, y + vh - 34, 18, ON)
    s.t(70, y + vh - 44, "Đang tìm mã QR…", "labelLarge", ON)
    y += vh + 16
    s.icon("info", 26, y + 10, 20, ON_VAR, filled=True)
    s.para(44, y, "Sau khi ghép, so khớp mã hub với màn hình máy tính", "bodyMedium", ON_VAR, maxw=296)
    s.button(16, 712, 328, "Hoặc nhập tay", "outlined", h=48, icon="keyboard")
    s.gesture_bar()


# ===================================================================================== 03 2FA setup
KEY = ["JBSW", "Y3DP", "EHPK", "3PXP", "KZ4W", "GQ2T", "MN7R", "C5DA"]


@screen("03a-2fa-setup", "03 Thiết lập 2FA")
def totp_setup(s):
    s.status_bar()
    s.stepper(3)
    s.icon("check_circle", 26, 108, 20, PRIMARY, filled=True)
    s.t(44, 98, "Đã ghép với PC-NHA", "labelLarge", PRIMARY)
    y = s.t(16, 128, "Thiết lập 2FA", "headlineSmall", ON)
    y = s.para(16, y + 4, "Mức bảo mật này cần mã 6 số mỗi lần mở phiên. Thêm khoá vào Google Authenticator một lần.",
               "bodyMedium", ON_VAR)
    y += 16
    s.rect(16, y, 328, 150, SC, 16)
    s.t(32, y + 14, "Khoá bí mật", "labelLarge", ON_VAR)
    s.rect(256, y + 8, 76, 32, SC_HIGH, 16)
    s.icon("visibility_off", 276, y + 24, 18, ON)
    s.t(292, y + 14, "Ẩn", "labelLarge", ON)
    for row in range(2):
        x = 32
        for g in KEY[row * 4:(row + 1) * 4]:
            s.text(x, y + 72 + row * 32, g, 20, ON, 500, mono=True, ls=1)
            x += tw(g, 20, mono=True, ls=1) + 14
    s.t(32, y + 116, "turbo-desktop · pc · 6 số · 30 giây", "bodySmall", MUTED)
    y += 166
    s.button(16, y, 328, "Thêm vào Google Authenticator", trailing_icon="open_in_new")
    y += 64
    s.button(16, y, 328, "Sao chép khoá", "outlined", h=48, icon="content_copy")
    y += 60
    s.icon("timer", 26, y + 10, 18, ON_VAR)
    s.para(44, y, "Lấy được khoá trong 4:12 nữa. Sau đó phải mở lại trên máy tính.", "bodySmall", ON_VAR, maxw=296)
    y += 44
    s.line(16, y, 344, y)
    y += 14
    s.icon("help", 26, y + 10, 18, ON_VAR, filled=True)
    s.t(44, y, "Mất 2FA? Trên máy tính chạy:", "bodySmall", ON_VAR)
    s.code(44, y + 24, 300, "python -m turbo_hub totp --rotate", copy=False, h=36, color=ON)
    s.button(16, 708, 328, "Tôi đã thêm xong", "tonal", fill=PRIMARY_C, fg=ON_PRIMARY_C)
    s.gesture_bar()


@screen("03b-2fa-expired", "03b Thiết lập 2FA: hết hạn lấy khoá")
def totp_expired(s):
    s.status_bar()
    s.stepper(3)
    s.circle(52, 140, 36, WARN_C)
    s.icon("timer_off", 52, 140, 36, ON_WARN_C, filled=True)
    y = s.t(16, 192, "Hết hạn lấy khoá", "headlineSmall", ON)
    y = s.para(16, y + 4, "Vì an toàn, điện thoại chỉ lấy được khoá trong 5 phút sau khi ghép.", "bodyMedium", ON_VAR)
    y += 20
    s.rect(16, y, 328, 156, SC, 16)

    def step(n, top, label):
        s.circle(44, top + 12, 12, SC_HIGHEST)
        s.text(44, top + 16.5, str(n), 12, ON, 600, "middle")
        return s.para(66, top + 2, label, "bodyMedium", ON, maxw=262)

    step(1, y + 16, "Trên máy tính chạy:")
    s.code(66, y + 48, 262, "python -m turbo_hub totp")
    step(2, y + 116, "Bấm Thử lại trong vòng 5 phút")
    y += 172
    s.icon("qr_code_scanner", 26, y + 10, 18, ON_VAR)
    y = s.para(44, y, "Lệnh này cũng hiện mã QR trên máy tính. Có thể quét thẳng bằng Google Authenticator.",
               "bodySmall", ON_VAR, maxw=296) + 12
    s.icon("help", 26, y + 10, 18, ON_VAR, filled=True)
    s.para(44, y, "Mất 2FA? Thêm --rotate để tạo khoá mới. Khoá cũ hết dùng được.", "bodySmall", ON_VAR, maxw=296)
    s.button(16, 644, 328, "Thử lại", icon="refresh")
    s.button(16, 708, 328, "Tôi đã thêm từ máy tính", "text", h=48)
    s.gesture_bar()


# ===================================================================================== 04 open session
def session_head(s):
    s.status_bar()
    s.rect(16, 48, 40, 40, SC_HIGH, 12)
    s.icon("desktop_windows", 36, 68, 22, ON_VAR, filled=True)
    s.t(68, 46, "PC-NHA", "titleMedium", ON)
    s.circle(72, 79, 4, PRIMARY)
    s.t(82, 69, "Tailscale · đã kết nối", "bodySmall", ON_VAR, weight=500)


@screen("04a-session-no2fa", "04a Mở phiên (mức Thoáng, không 2FA)")
def session_plain(s):
    session_head(s)
    y = s.t(16, 128, "Mở phiên", "headlineMedium", ON)
    y = s.t(16, y + 4, "Phiên cũ đã hết hạn hoặc chưa có phiên", "bodyMedium", ON_VAR)
    y += 24

    def row(ic, a, b):
        def d(top):
            s.icon(ic, 40, top + 32, 22, ON_VAR)
            s.t(68, top + 12, a, "labelLarge", ON)
            s.t(68, top + 34, b, "bodySmall", MUTED)
        return d

    s.list_group(16, y, 328, [row("qr_code_scanner", "Không cần quét lại QR", "Điện thoại này đã ghép với PC-NHA"),
                              row("schedule", "Mức Thoáng · phiên 12 giờ", "Không cần mã Authenticator")], h=64)
    s.button(16, 644, 328, "Mở phiên", icon="lock_open")
    s.button(16, 708, 328, "Huỷ ghép với máy tính này", "text", h=48, fg=STOP_TEXT)
    s.gesture_bar()


@screen("04b-session-2fa", "04b Mở phiên (mức Chặt: 2FA + vân tay)")
def session_totp(s):
    session_head(s)
    y = s.t(16, 128, "Mở phiên", "headlineMedium", ON)
    y = s.t(16, y + 4, "Phiên cũ đã hết hạn hoặc chưa có phiên", "bodyMedium", ON_VAR)
    y += 28
    y = s.t(16, y, "Mã 6 số trong Google Authenticator", "labelLarge", ON)
    y += 8
    digits = ["4", "8", "1", "", "", ""]
    for i, dgt in enumerate(digits):
        x = 16 + i * 56
        focus = i == 3
        s.rect(x, y, 48, 60, SC_HIGH, 12, stroke=PRIMARY if focus else OUTLINE, sw=2 if focus else 1)
        if dgt:
            s.text(x + 24, y + 30 + 24 * 0.36, dgt, 24, ON, 500, "middle", mono=True)
        if focus:
            s.rect(x + 23, y + 18, 2, 24, PRIMARY, 1)
    y += 72
    y = s.para(16, y, "Mã đổi sau mỗi 30 giây. Mỗi mã chỉ dùng một lần.", "bodySmall", ON_VAR)
    y += 12
    s.rect(16, y, 112, 40, "none", 20, stroke=OUTLINE)
    s.icon("content_paste", 40, y + 20, 18, ON)
    s.t(56, y + 10, "Dán mã", "labelLarge", ON)
    s.rect(136, y, 176, 40, "none", 20, stroke=OUTLINE)
    s.icon("open_in_new", 160, y + 20, 18, ON)
    s.t(176, y + 10, "Mở Authenticator", "labelLarge", ON)
    y += 64
    s.line(16, y, 344, y)
    y += 16
    s.icon("fingerprint", 26, y + 10, 18, ON_VAR)
    y = s.para(44, y, "Sau đó xác nhận bằng vân tay hoặc mã khoá màn hình", "bodySmall", ON_VAR, maxw=296) + 8
    s.icon("lock", 26, y + 10, 18, ON_VAR, filled=True)
    s.para(44, y, "Sai 5 lần: khoá 15 phút và máy tính báo cho bạn", "bodySmall", ON_VAR, maxw=296)
    s.button(16, 644, 328, "Mở phiên và xác nhận", icon="fingerprint")
    s.button(16, 708, 328, "Huỷ ghép với máy tính này", "text", h=48, fg=STOP_TEXT)
    s.gesture_bar()


# ===================================================================================== 05 tasks
@screen("05-tasks", "05 Việc (sẵn sàng)")
def tasks(s):
    s.status_bar()
    s.presence("idle")
    s.rect(16, 104, 328, 60, SC, 16)
    s.icon("schedule", 38, 134, 20, ON_VAR)
    s.t(60, 112, "Phiên còn 1 giờ 58 phút", "labelLarge", ON, weight=600)
    s.t(60, 134, "Hôm nay: 3.080 token · $0,00", "bodySmall", MUTED)
    s.t(332, 122, "Gia hạn", "labelLarge", PRIMARY, "end", weight=600)
    y = s.t(16, 184, "Giao việc cho máy tính", "headlineSmall", ON)
    y += 12
    s.rect(16, y, 328, 148, SC_HIGH, 16)
    s.para(32, y + 16, "Ví dụ: mở Máy tính và tính 12,5 + 7", "bodyLarge", MUTED, maxw=296)
    s.button(212, y + 96, 120, "Gửi việc", h=40, icon="send")
    y += 156
    y = s.para(16, y, "Gợi ý: nói rõ mở ứng dụng nào, làm gì", "bodySmall", ON_VAR) + 20
    y = s.t(16, y, "Việc gần đây", "titleMedium", ON)
    y += 8
    items = [("check_circle", PRIMARY, "Mở Máy tính và tính (12,5 + 7) × 3", "Xong · 18:09 · 1.920 token"),
             ("stop_circle", STOP_TEXT, "Mở Notepad, viết danh sách mua sắm rồi lưu ra Desktop", "Đã dừng · 17:52 · 4.410 token"),
             ("check_circle", PRIMARY, "Đổi tên thư mục “Ảnh 2025” thành “Ảnh cũ”", "Xong · 16:30 · 2.760 token")]

    def row(it):
        ic, col, a, b = it

        def d(top):
            s.icon(ic, 40, top + 32, 24, col, filled=True)
            s.para(68, top + 10, a, "bodyMedium", ON, maxw=244, max_lines=1, weight=500)
            s.t(68, top + 34, b, "bodySmall", MUTED)
            s.icon("chevron_right", 324, top + 32, 20, MUTED)
        return d

    s.list_group(16, y, 328, [row(i) for i in items], h=64)
    s.nav("Việc")


# ===================================================================================== 06-08 live
def timeline(s, top, steps, x=36):
    """steps: (kind, title, meta). kind: done | note | current | stopped."""
    y = top
    pos = []
    for kind, title, meta in steps:
        lines = wrap(title, 14, 252, 500)
        h = 20 * len(lines) + 22
        if kind == "note":
            h += 16
        pos.append((kind, title, meta, y, h, lines))
        y += h + 12
    s.line(x, top + 12, x, pos[-1][3] + 12, OUTLINE_VAR, 2)
    for kind, title, meta, yy, h, lines in pos:
        if kind == "done":
            s.circle(x, yy + 12, 11, SC_HIGH)
            s.icon("check", x, yy + 12, 16, PRIMARY)
        elif kind == "note":
            s.circle(x, yy + 12, 11, SC_HIGH)
            s.icon("chat_bubble", x, yy + 12, 14, ON_VAR, filled=True)
        elif kind == "current":
            s.circle(x, yy + 12, 14, AI, op=0.25)
            s.circle(x, yy + 12, 6, AI)
        elif kind == "stopped":
            s.circle(x, yy + 12, 11, STOP_C)
            s.icon("stop", x, yy + 12, 14, STOP_TEXT, filled=True)
        tx = x + 24
        if kind == "note":
            s.rect(tx - 8, yy - 6, 300 - (tx - 16) + 28, 20 * len(lines) + 40, SC, 12)
            s.t(tx, yy - 2, "AI", "labelMedium", ON_VAR)
            yy += 16
        col = {"current": AI_TEXT, "stopped": STOP_TEXT}.get(kind, ON)
        for i, ln in enumerate(lines):
            s.t(tx, yy + 2 + i * 20, ln, "bodyMedium", ON_VAR if kind == "note" else col,
                weight=400 if kind == "note" else 500)
        s.t(tx, yy + 2 + 20 * len(lines), meta, "bodySmall", MUTED)
    return y


def task_card(s, y, meta):
    s.rect(16, y, 328, 96, SC, 16)
    s.t(32, y + 14, "Việc này", "labelMedium", ON_VAR)
    s.t(32, y + 32, "Mở Máy tính và tính (12,5 + 7) × 3", "titleMedium", ON, maxw=296)
    s.icon("timer", 41, y + 72, 16, MUTED)
    s.t(54, y + 64, meta, "bodySmall", ON_VAR)
    return y + 96


@screen("06-live-acting", "06 Trực tiếp: AI đang điều khiển")
def live_acting(s):
    s.status_bar("18:09")
    s.presence("acting")
    y = task_card(s, 104, "00:12 · 1.800 token vào · 120 ra")
    y = s.t(16, y + 16, "Các bước", "titleMedium", ON) + 12
    timeline(s, y, [("done", "Đã mở Máy tính (w3)", "18:09:17 · qua UIA"),
                    ("done", "Đã đọc 42 điều khiển", "18:09:18"),
                    ("note", "Nhập 12,5 + 7 rồi nhân 3.", "18:09:18"),
                    ("done", "Đã chạy 6 bước (6 thành công)", "18:09:20 · qua UIA"),
                    ("current", "Đang bấm “=”…", "18:09:21 · qua UIA")])
    s.button(16, 620, 328, "Lấy lại quyền", "outlined", h=48, icon="pan_tool")
    s.para(16, 674, "Mở khoá phím/chuột ngay và tạm dừng việc đang chạy", "bodySmall", MUTED)
    s.nav("Trực tiếp")
    s.edge("acting")


@screen("07-live-locked", "07 Trực tiếp: PC đang khoá phím/chuột")
def live_locked(s):
    s.status_bar("18:12")
    s.presence("locked")
    y = 104
    s.rect(16, y, 328, 176, AI_C, 20)
    s.icon("lock", 44, y + 30, 24, ON_AI_C, filled=True)
    s.t(68, y + 18, "PC đang khoá phím/chuột", "titleMedium", ON_AI_C)
    s.para(68, y + 44, "AI đang dùng chuột/phím thật. Tự mở sau 0:42.", "bodyMedium", ON, maxw=260)
    s.button(32, y + 100, 296, "Lấy lại quyền", fill=AI, fg=ON_AI, icon="pan_tool")
    y += 188
    s.para(16, y, "Mở khoá phím/chuột ngay và tạm dừng việc đang chạy", "bodySmall", ON_VAR)
    y = s.t(16, y + 32, "Các bước", "titleMedium", ON) + 12
    timeline(s, y, [("done", "Đã mở Notepad (w5)", "18:11:58 · qua UIA"),
                    ("done", "Đã gõ vào “Văn bản” (qua UIA)", "18:12:03 · qua UIA"),
                    ("current", "Đang gõ vào “Tên tệp”…", "18:12:06 · chuột/phím thật")])
    s.nav("Trực tiếp")
    s.edge("locked")


@screen("08-live-stopped", "08 Trực tiếp: đã dừng")
def live_stopped(s):
    s.status_bar("18:09")
    s.presence("stopped", stop=False)
    s.circle(180, 156, 40, STOP_C)
    s.icon("stop_circle", 180, 156, 40, STOP_TEXT, filled=True)
    s.t(180, 210, "Đã dừng", "headlineSmall", ON, "middle")
    s.para(180, 248, "Tiến trình AI đã bị tắt. Việc mới và mọi thao tác bị chặn.", "bodyMedium", ON_VAR,
           maxw=280, anchor="middle")
    s.button(16, 312, 328, "Cho chạy lại", fill=INV, fg=ON_INV, icon="play_arrow")
    y = 392
    s.rect(16, y, 328, 100, SC, 16)
    s.icon("keyboard", 40, y + 26, 20, ON_VAR)
    s.t(60, y + 16, "Trên máy tính, phím nóng này cũng dừng:", "bodySmall", ON_VAR)
    x = 32
    for i, k in enumerate(["Ctrl", "Alt", "Shift", "K"]):
        x = s.keycap(x, y + 52, k)
        if i < 3:
            s.text(x + 9, y + 71, "+", 14, MUTED, 500, "middle")
            x += 18
    y = s.t(16, y + 120, "Việc bị dừng", "titleMedium", ON) + 12
    timeline(s, y, [("done", "Đã mở Máy tính (w3)", "18:09:17 · qua UIA"),
                    ("stopped", "Đã dừng (STOP)", "18:09:21 · từ điện thoại này")])
    s.nav("Trực tiếp")


# ===================================================================================== 09 approval
@screen("09-approval", "09 Duyệt: AI muốn bấm “Gửi”")
def approval(s):
    s.status_bar("18:08")
    s.presence("acting")
    s.t(16, 104, "Cần bạn duyệt", "headlineSmall", ON)
    s.rect(256, 104, 88, 32, WARN_C, 16)
    s.icon("timer", 274, 120, 18, ON_WARN_C)
    s.text(316, 120 + 16 * 0.36, "1:49", 16, ON_WARN_C, 600, "middle", mono=True)
    y = 152
    s.rect(16, y, 328, 336, SC, 20)
    s.t(32, y + 16, "AI muốn bấm “Gửi”", "titleLarge", ON)
    s.icon("web_asset", 41, y + 58, 18, ON_VAR)
    s.t(56, y + 48, "trong cửa sổ Thư – Soạn thư", "bodyMedium", ON_VAR)
    # crop of the control, as captured
    cy = y + 84
    s.rect(32, cy, 296, 128, "#0A0C0E", 12)
    s.rect(32, cy, 296, 28, "#1A1D21", 12)
    s.rect(32, cy + 14, 296, 14, "#1A1D21")
    for i, w in enumerate((40, 52, 34)):
        s.rect(44 + sum((40, 52, 34)[:i]) + i * 10, cy + 9, w, 10, "#2B3036", 3)
    s.rect(48, cy + 44, 170, 8, "#24282D", 4)
    s.rect(48, cy + 60, 200, 8, "#24282D", 4)
    s.rect(48, cy + 76, 140, 8, "#24282D", 4)
    s.rect(236, cy + 82, 76, 32, "#3A6FD8", 6)
    s.text(274, cy + 103, "Gửi", 14, "#FFFFFF", 600, "middle")
    s.rect(230, cy + 76, 88, 44, "none", 9, stroke=WARN, sw=2, dash="5 4")
    s.t(32, cy + 136, "Ảnh cắt đúng vùng điều khiển, chụp lúc yêu cầu", "bodySmall", MUTED)
    s.line(32, cy + 168, 328, cy + 168)
    iy = cy + 180
    s.icon("assignment", 41, iy + 10, 18, ON_VAR)
    s.para(56, iy, "Việc: gửi báo cáo tuần cho nhóm qua Thư", "bodySmall", ON_VAR, maxw=272)
    s.icon("schedule", 41, iy + 34, 18, ON_VAR)
    s.t(56, iy + 24, "Không trả lời sau 2 phút = Từ chối", "bodySmall", ON_VAR)
    s.button(16, 512, 156, "Từ chối", "outlined", icon="close")
    s.button(184, 512, 160, "Cho phép", fill=WARN, fg=ON_WARN, icon="check")
    s.icon("fingerprint", 26, 592, 18, MUTED)
    s.para(44, 582, "Cho phép hoặc Từ chối sẽ hỏi vân tay hoặc mã khoá màn hình", "bodySmall", MUTED, maxw=296)
    s.nav("Duyệt", badge=1)
    s.edge("acting")


# ===================================================================================== 10 audit
@screen("10-audit", "10 Nhật ký")
def audit(s):
    s.status_bar("18:10")
    s.presence("idle")
    s.t(16, 104, "Nhật ký", "headlineSmall", ON)
    s.circle(320, 120, 20, SC_HIGH)
    s.icon("refresh", 320, 120, 22, ON)
    y = 152
    s.rect(16, y, 328, 64, PRIMARY_C, 16)
    s.icon("verified_user", 42, y + 32, 24, ON_PRIMARY_C, filled=True)
    s.t(66, y + 12, "Chuỗi băm hợp lệ · 25 mục", "labelLarge", ON_PRIMARY_C, weight=600)
    s.t(66, y + 34, "Mỗi dòng ghi kèm mã băm của dòng trước", "bodySmall", ON_PRIMARY_C)
    y += 80
    x = 16
    for i, c in enumerate(["Tất cả", "Hành động", "Duyệt", "Dừng"]):
        w = tw(c, 14, 500) + (40 if i == 0 else 24)
        if i == 0:
            s.rect(x, y, w, 32, PRIMARY_C, 8)
            s.icon("check", x + 16, y + 16, 18, ON_PRIMARY_C)
            s.t(x + 28, y + 6, c, "labelLarge", ON_PRIMARY_C)
        else:
            s.rect(x + 0.5, y + 0.5, w - 1, 31, "none", 8, stroke=OUTLINE)
            s.t(x + 12, y + 6, c, "labelLarge", ON_VAR)
        x += w + 8
    y += 48
    s.t(16, y, "Hôm nay", "labelMedium", ON_VAR)
    y += 24
    rows = [("18:09:33", "play_arrow", ON_VAR, "Cho chạy lại", "Điện thoại này"),
            ("18:09:21", "stop_circle", STOP_TEXT, "Đã dừng (STOP)", "Điện thoại này"),
            ("18:09:21", "flag", ON_VAR, "Kết thúc việc: đã dừng", "Mở Máy tính và tính (12,5 + 7) × 3"),
            ("18:09:21", "visibility", ON_VAR, "Đã đọc cửa sổ Máy tính", "Đọc giao diện · qua UIA"),
            ("18:09:17", "open_in_new", ON_VAR, "Đã mở Máy tính (w3)", "Mở ứng dụng · qua UIA"),
            ("18:08:56", "gpp_maybe", WARN, "Từ chối: bấm “Gửi”", "Thư – Soạn thư · bạn quyết định")]
    for i, (tm, ic, col, a, b) in enumerate(rows):
        top = y + i * 60
        if i:
            s.line(16, top, 344, top)
        s.text(16, top + 26, tm, 12, MUTED, 400, mono=True)
        s.icon(ic, 96, top + 30, 20, col, filled=ic in ("stop_circle", "gpp_maybe"))
        s.t(118, top + 10, a, "labelLarge", ON, maxw=206)
        s.para(118, top + 32, b, "bodySmall", MUTED, maxw=200, max_lines=1)
        s.icon("chevron_right", 334, top + 30, 18, MUTED)
    s.nav("Nhật ký")


# ===================================================================================== 11 settings
def setting_rows(s, rows):
    out = []
    for ic, title, value, kind in rows:
        def d(top, ic=ic, title=title, value=value, kind=kind):
            s.icon(ic, 40, top + 28, 22, ON_VAR, filled=ic in ("lock", "key"))
            vw = tw(value, 13, 500) if value else 0
            right = 320 if kind == "nav" else 328
            vcol = PRIMARY if value in ("Bật", "Đã thiết lập") else ON_VAR
            if 68 + tw(title, 14, 500) + 12 + vw <= right:
                s.t(68, top + 18, title, "labelLarge", ON)
                if value:
                    s.text(right, top + 28 + 13 * 0.36, value, 13, vcol, 500, "end")
            else:   # two-line list item: value moves under the title
                s.t(68, top + 8, title, "labelLarge", ON, maxw=right - 68)
                s.t(68, top + 30, value, "bodySmall", vcol, maxw=right - 68)
            if kind == "nav":
                s.icon("chevron_right", 330, top + 28, 18, MUTED)
            if kind == "locked":
                pass
        out.append(d)
    return out


@screen("11-settings", "11 Cài đặt (có Ngôn ngữ và 2FA)")
def settings(s):
    s.status_bar("18:11")
    s.presence("idle")
    s.t(16, 104, "Cài đặt", "headlineSmall", ON)
    y = 152
    s.t(16, y, "Trên điện thoại này", "labelLarge", ON_VAR)
    y = s.list_group(16, y + 28, 328, setting_rows(s, [
        ("language", "Ngôn ngữ", "Theo hệ thống", "nav"),
        ("key", "Xác thực 2 bước (2FA)", "Đã thiết lập", "nav"),
        ("battery_saver", "Giữ kết nối trên Xiaomi/HyperOS", "", "nav")]))
    y += 24
    s.t(16, y, "Bảo mật · đặt trên máy tính", "labelLarge", ON_VAR)
    y += 28
    s.rect(16, y, 328, 76, SC_HIGH, 16)
    s.icon("shield", 40, y + 26, 22, ON_PRIMARY_C, filled=True)
    s.t(64, y + 14, "Mức hiện tại: Cân bằng", "labelLarge", ON, weight=600)
    s.para(64, y + 36, "Đổi trong turbo-desktop.toml trên máy tính.", "bodySmall", ON_VAR, maxw=264)
    y += 84
    s.list_group(16, y, 328, setting_rows(s, [
        ("lock", "STOP, nhật ký, ô mật khẩu", "Luôn bật", "locked"),
        ("gpp_maybe", "Hỏi trước khi gửi, xoá, cài", "Bật", "plain"),
        ("pin", "Mã 2FA khi mở phiên", "Bật", "plain") if "pin" in ICONS else
        ("password", "Mã 2FA khi mở phiên", "Bật", "plain") if "password" in ICONS else
        ("key", "Mã 2FA khi mở phiên", "Bật", "plain"),
        ("mouse", "Khoá phím/chuột", "Khi dùng chuột thật", "nav"),
        ("fingerprint", "Vân tay khi duyệt", "Tắt", "plain")]))
    s.nav("Cài đặt")


@screen("11b-language", "11b Cài đặt > Ngôn ngữ (bottom sheet)")
def language(s):
    settings(s)
    s.rect(0, 0, W, H, SCRIM, op=0.55)
    top = 452
    s.rect(0, top, W, H - top + 30, SC_LOW, 28)
    s.rect(W / 2 - 16, top + 12, 32, 4, OUTLINE, 2)
    s.t(24, top + 32, "Ngôn ngữ", "titleLarge", ON)
    s.para(24, top + 64, "Chỉ đổi ngôn ngữ của ứng dụng này.", "bodyMedium", ON_VAR, maxw=312)
    opts = [("Theo hệ thống", "Máy đang dùng: English", True), ("Tiếng Việt", None, False), ("English", None, False)]
    y = top + 100
    for name, sub, on in opts:
        h = 64 if sub else 56
        s.icon("radio_button_checked" if on else "radio_button_unchecked", 44, y + h / 2, 24,
               PRIMARY if on else ON_VAR, filled=on)
        if sub:
            s.t(72, y + 10, name, "bodyLarge", ON)
            s.t(72, y + 34, sub, "bodySmall", MUTED)
        else:
            s.t(72, y + 16, name, "bodyLarge", ON)
        y += h
    s.gesture_bar()


# ===================================================================================== build
def build():
    out = []
    for key, title, fn in SCREENS:
        s = Svg(key, title)
        fn(s)
        svg = s.render()
        (HERE / f"{key}.svg").write_text(svg, encoding="utf-8")
        out.append((key, title, svg, s.render(fonts_inline=False)))
    # contact sheet: fonts embedded so headless Edge renders the real typefaces
    faces = ""
    for w, n in ((400, "Regular"), (500, "Medium"), (600, "SemiBold"), (700, "Bold")):
        b = base64.b64encode((HERE / "_fonts" / f"BeVietnamPro-{n}.ttf").read_bytes()).decode()
        faces += f"@font-face{{font-family:'Be Vietnam Pro';font-weight:{w};src:url(data:font/ttf;base64,{b})}}"
    b = base64.b64encode((HERE / "_fonts" / "JetBrainsMono.ttf").read_bytes()).decode()
    faces += f"@font-face{{font-family:'JetBrains Mono';font-weight:100 800;src:url(data:font/ttf;base64,{b})}}"
    cells = "".join(f'<figure><div class="ph">{inline}</div><figcaption>{escape(title)}</figcaption></figure>'
                    for key, title, svg, inline in out)
    html = (f'<!doctype html><meta charset="utf-8"><title>Turbo Remote v2</title><style>{faces}'
            "body{margin:0;background:#2A2D31;font-family:'Be Vietnam Pro';color:#ECEAE4;padding:40px}"
            "h1{font-weight:600;font-size:28px;margin:0 0 6px}p{margin:0 0 32px;color:#A9B0BA;font-size:15px}"
            ".g{display:grid;grid-template-columns:repeat(5,360px);gap:44px 36px}"
            "figure{margin:0}.ph{width:360px;height:800px;border-radius:28px;box-shadow:0 12px 40px #0008}"
            "figcaption{margin-top:14px;font-size:15px;font-weight:500;color:#D7D4CD}</style>"
            "<h1>Turbo Remote v2</h1><p>360×800 dp · tối · Be Vietnam Pro + JetBrains Mono · Material Symbols Rounded"
            " · 17/11/2026</p>"
            f'<div class="g">{cells}</div>')
    (HERE / "_sheet.html").write_text(html, encoding="utf-8")
    for w in WARNINGS:
        print("WARN", w)
    print(len(out), "screens")


if __name__ == "__main__":
    build()
