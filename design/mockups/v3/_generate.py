"""Turbo Remote v3 mockups: one "Việc" screen (player + task card + steps + composer), see design/LIVE_V3.md section E.
Run: python -X utf8 _generate.py && sh _render.sh   (tokens, fonts and drawing kit copied from v2)."""
import base64
from _lib import *  # noqa: F403

SCREENS = []


def screen(key, title, w=W, h=H):
    def deco(fn):
        SCREENS.append((key, title, fn, w, h))
        return fn
    return deco


# ===================================================================================== the PC picture (1600x900 space)
def pc_desktop(s, x, y, w, h, state="idle", redact=False, r=12):
    """A Windows desktop as captured by /screen.jpg, drawn in a 1600x900 viewBox scaled into (x, y, w, h)."""
    cid = s.id(f"pc{len(s.defs)}")
    gid = s.id(f"wall{len(s.defs)}")
    s.defs.append(f'<clipPath id="{cid}"><rect width="1600" height="900" rx="{r * 1600 / w:g}"/></clipPath>'
                  f'<linearGradient id="{gid}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#22405E"/>'
                  f'<stop offset="1" stop-color="#0D1826"/></linearGradient>')
    p = []
    R = lambda X, Y, W_, H_, f, rr=0, extra="": p.append(  # noqa: E731
        f'<rect x="{X}" y="{Y}" width="{W_}" height="{H_}" rx="{rr}" fill="{f}" {extra}/>')
    Tx = lambda X, Y, t, sz, f, wt=500, a="start": p.append(  # noqa: E731
        f'<text x="{X}" y="{Y}" font-family="{SANS}" font-size="{sz}" font-weight="{wt}" fill="{f}" '
        f'text-anchor="{a}">{escape(t)}</text>')
    R(0, 0, 1600, 900, f"url(#{gid})")
    # chat app window (generic, no logo)
    wx, wy, ww, wh = 150, 70, 1000, 730
    R(wx, wy, ww, wh, "#F4F5F7", 14)
    R(wx, wy, ww, 52, "#E6E8EC", 14)
    R(wx, wy + 30, ww, 22, "#E6E8EC")
    Tx(wx + 24, wy + 34, "Zalo", 22, "#30343A", 600)
    for i in range(3):
        R(wx + ww - 150 + i * 48, wy + 18, 18, 18, "#B8BDC5", 4)
    R(wx, wy + 52, 330, wh - 52, "#FFFFFF")
    R(wx + 16, wy + 68, 298, 44, "#EEF0F3", 22)
    Tx(wx + 44, wy + 98, "Tìm kiếm", 20, "#8A9099", 400)
    names = ["Chị Lan", "Nhóm Kế toán", "Anh Minh", "Cloud của tôi", "Phòng Kinh doanh", "Mẹ"]
    for i, n in enumerate(names):
        cy = wy + 130 + i * 92
        if i == 0:
            R(wx, cy - 6, 330, 92, "#E3EEFF")
        p.append(f'<circle cx="{wx + 50}" cy="{cy + 40}" r="28" fill="{["#7FA7E8", "#9BC59D", "#E3A77F", "#A99BE0", "#E8C27F", "#E39BB5"][i]}"/>')
        Tx(wx + 92, cy + 34, n, 21, "#1E2227", 600 if i == 0 else 500)
        R(wx + 92, cy + 50, 180 - i * 12, 12, "#C9CED6", 6)
    # conversation
    mx = wx + 330
    R(mx, wy + 52, ww - 330, 64, "#FFFFFF")
    Tx(mx + 28, wy + 92, "Chị Lan", 24, "#1E2227", 600)
    bub = [(0, 300, 2), (0, 380, 1), (1, 260, 1), (0, 420, 2), (0, 220, 1)]
    by = wy + 150
    for side, bw, lines in bub:
        bh = 30 + lines * 28
        bx = mx + 30 if side == 0 else mx + (ww - 330) - 30 - bw
        R(bx, by, bw, bh, "#FFFFFF" if side == 0 else "#D4E6FF", 16, 'stroke="#E1E4E8"')
        for k in range(lines):
            R(bx + 18, by + 22 + k * 28, bw - 36 - k * 60, 12, "#B5BBC4", 6)
        by += bh + 22
    R(mx + 24, wy + wh - 70, ww - 330 - 48, 48, "#EEF0F3", 24)
    # second window: a password manager (redacted when served)
    sx, sy, sw_, sh = 1190, 150, 360, 420
    if redact:
        R(sx, sy, sw_, sh, "#000000", 10)
        p.append(f'<path transform="translate({sx + sw_ / 2 - 36},{sy + sh / 2 - 60}) scale(0.075) translate(0,960)" '
                 f'd="{ICONS["lock_fill1"]}" fill="#5B6370"/>')
        Tx(sx + sw_ / 2, sy + sh / 2 + 56, "Đã che", 26, "#8C95A0", 600, "middle")
    else:
        R(sx, sy, sw_, sh, "#2A2E35", 10)
    # taskbar
    R(0, 852, 1600, 48, "#16191E")
    for i in range(6):
        R(640 + i * 56, 862, 30, 28, "#3A6FD8" if i == 2 else "#4A5260", 6)
    Tx(1560, 884, "18:41", 18, "#D6D9DE", 500, "end")
    if state == "running":
        p.append('<rect x="5" y="5" width="1590" height="890" fill="none" stroke="#E0461D" stroke-width="10"/>')
        R(500, 14, 600, 40, "#E0461D", 20)
        Tx(800, 41, "AI đang làm việc theo lệnh từ điện thoại · Esc ×3 để lấy lại", 17, "#1A0702", 600, "middle")
    s.add(f'<svg x="{x}" y="{y}" width="{w}" height="{h}" viewBox="0 0 1600 900">'
          f'<g clip-path="url(#{cid})">{"".join(p)}</g></svg>')


def pill(s, x, y, label, dot=None, fill=SCRIM, op=0.62, fg=ON, h=24, size=11, icon=None):
    w = tw(label, size, 600) + 20 + (12 if dot else 0) + (18 if icon else 0)
    s.rect(x, y, w, h, fill, h / 2, op=op)
    tx = x + 10
    if dot:
        s.circle(tx + 3, y + h / 2, 4, dot)
        tx += 12
    if icon:
        s.icon(icon, tx + 7, y + h / 2, 14, fg)
        tx += 18
    s.text(tx, y + h / 2 + size * 0.36, label, size, fg, 600)
    return x + w


def round_btn(s, cx, cy, icon, r=18, fill=SCRIM, op=0.62, fg=ON, size=20):
    s.circle(cx, cy, r, fill, op=op)
    s.icon(icon, cx, cy, size, fg, filled=icon in ("pause",))


def player(s, state):
    x, y, w = 16, 104, 328
    h = round(w * 9 / 16)
    pc_desktop(s, x, y, w, h, "running" if state == "running" else "idle")
    if state == "running":
        pill(s, x + 8, y + h - 34, "TRỰC TIẾP · 2 hình/giây", dot=AI)
        round_btn(s, x + w - 66, y + h - 26, "pause")
    else:
        pill(s, x + 8, y + h - 34, "Ảnh lúc 18:43", icon="photo_camera")
        round_btn(s, x + w - 66, y + h - 26, "play_arrow")
    round_btn(s, x + w - 26, y + h - 26, "fullscreen")
    return y + h


def composer(s, busy):
    y = 652
    s.rect(0, y - 12, W, 72, BG)
    s.line(0, y - 12, W, y - 12, OUTLINE_VAR)
    s.rect(16, y, 272, 48, SC_HIGH if not busy else SC, 24, stroke=None if not busy else OUTLINE_VAR)
    if busy:
        s.icon("progress_activity", 40, y + 24, 18, MUTED)
        s.t(56, y + 14, "Đang có việc chạy", "bodyMedium", MUTED)
        s.circle(320, y + 24, 24, SC_HIGH)
        s.icon("arrow_upward", 320, y + 24, 22, OUTLINE)
    else:
        s.t(32, y + 12, "Giao việc cho máy tính…", "bodyLarge", MUTED)
        s.circle(320, y + 24, 24, PRIMARY)
        s.icon("arrow_upward", 320, y + 24, 22, ON_PRIMARY)


def history(s, y, items):
    def row(it):
        ic, col, a, b = it

        def d(top):
            s.icon(ic, 40, top + 32, 22, col, filled=True)
            s.para(68, top + 10, a, "bodyMedium", ON, maxw=244, max_lines=1, weight=500)
            s.t(68, top + 34, b, "bodySmall", MUTED)
            s.icon("chevron_right", 324, top + 32, 20, MUTED)
        return d

    return s.list_group(16, y, 328, [row(i) for i in items], h=64)


HIST = [("check_circle", PRIMARY, "Mở Máy tính và tính (12,5 + 7) × 3", "Xong · 18:09"),
        ("stop_circle", STOP_TEXT, "Mở Notepad, viết danh sách mua sắm rồi lưu ra Desktop", "Đã dừng · 17:52"),
        ("check_circle", PRIMARY, "Đổi tên thư mục “Ảnh 2025” thành “Ảnh cũ”", "Xong · 16:30"),
        ("check_circle", PRIMARY, "Xem dung lượng ổ C còn trống bao nhiêu", "Xong · 15:02")]
PROMPT = "Mở Zalo và tóm tắt tin nhắn mới từ chị Lan"
ANSWER = ("Chị Lan nhắn 4 tin từ 17:52 đến 18:20. Chị hỏi đã gửi báo giá bản cuối chưa và nhắc hạn chót là 10 giờ "
          "sáng mai. Chị cũng gửi tệp “Bao_gia_v3.xlsx” và nhờ xem lại dòng phí vận chuyển.")


def task_card_top(s, y, h):
    s.rect(16, y, 328, h, SC, 16)
    s.t(32, y + 14, "Bạn giao · 18:40", "labelMedium", MUTED)
    return s.para(32, y + 34, PROMPT, "bodyLarge", ON, maxw=296, weight=500)


# ===================================================================================== 12 idle
@screen("12-viec-idle", "12 Việc: rảnh (ảnh tĩnh PC, lịch sử)")
def idle(s):
    s.status_bar("18:44")
    s.presence("idle")
    y = player(s, "idle") + 8
    s.t(16, y, "Chạm để xem toàn màn hình", "bodySmall", MUTED)
    y = s.t(16, y + 28, "Việc gần đây", "titleMedium", ON) + 8
    history(s, y, HIST)
    composer(s, busy=False)
    s.nav("Việc")


# ===================================================================================== 13 running
@screen("13-viec-running", "13 Việc: đang chạy (xem trực tiếp, PC bị khoá)")
def running(s):
    s.status_bar("18:41")
    s.presence("locked")
    y = player(s, "running") + 12
    top = y
    y = task_card_top(s, top, 154)
    s.line(32, y + 10, 328, y + 10)
    y += 22
    s.circle(41, y + 10, 8, AI, op=0.25)
    s.circle(41, y + 10, 4, AI)
    s.t(56, y, "Đang làm · bước 7 · 1:42", "labelLarge", AI_TEXT, weight=600)
    s.icon("lock", 41, y + 34, 16, ON_VAR, filled=True)
    s.t(56, y + 24, "PC đang khoá phím/chuột cho tới khi xong", "bodySmall", ON_VAR)
    y = top + 154 + 8
    s.rect(16, y, 328, 48, SC_LOW, 12)
    s.icon("list_alt", 40, y + 24, 20, ON_VAR)
    s.t(60, y + 14, "Chi tiết từng bước (12)", "labelLarge", ON)
    s.icon("expand_more", 324, y + 24, 22, ON_VAR)
    y += 60
    s.button(16, y, 328, "Lấy lại quyền", "outlined", h=44, icon="pan_tool")
    s.para(16, y + 50, "Mở khoá phím/chuột ngay và tạm dừng việc", "bodySmall", MUTED)
    composer(s, busy=True)
    s.nav("Việc")
    s.edge("acting")


# ===================================================================================== 14 done (long scroll frame)
STEPS = [("open_in_new", "Mở Zalo (qua Start Menu)", "18:40:05"), ("visibility", "Đọc cửa sổ ×3", "18:40:12"),
         ("touch_app", "Bấm “Tìm kiếm”", "18:40:30"), ("keyboard", "Gõ “Lan”", "18:40:41"),
         ("visibility", "Đọc cửa sổ ×2", "18:40:55"), ("touch_app", "Bấm “Chị Lan”", "18:41:20"),
         ("swipe_vertical", "Cuộn khung tin nhắn", "18:41:48"), ("visibility", "Đọc cửa sổ ×2", "18:42:30")]


@screen("14-viec-done", "14 Việc: xong (câu trả lời đầy đủ, bước đã mở) · khung cuộn dài", h=1350)
def done(s):
    s.status_bar("18:43")
    s.presence("idle")
    y = player(s, "idle") + 12
    top = y
    ans_lines = wrap(ANSWER, 16, 296, 400)
    card_h = 34 + 48 + 22 + 30 + 28 + len(ans_lines) * 24 + 56
    y = task_card_top(s, top, card_h)
    s.line(32, y + 10, 328, y + 10)
    y += 22
    s.icon("check_circle", 41, y + 10, 18, PRIMARY, filled=True)
    s.t(56, y, "Xong · 12 bước · 3:09", "labelLarge", PRIMARY, weight=600)
    y += 34
    s.t(32, y, "Kết quả", "labelMedium", ON_VAR)
    y = s.para(32, y + 22, ANSWER, "bodyLarge", ON, maxw=296) + 8
    s.rect(24, y, 104, 40, "none", 20)
    s.icon("content_copy", 44, y + 20, 18, PRIMARY)
    s.t(60, y + 10, "Sao chép", "labelLarge", PRIMARY, weight=600)
    s.icon("refresh", 162, y + 20, 18, PRIMARY)
    s.t(178, y + 10, "Giao lại", "labelLarge", PRIMARY, weight=600)
    y = top + card_h + 8
    rows_h = 48 + len(STEPS) * 36 + 8
    s.rect(16, y, 328, rows_h, SC_LOW, 12)
    s.icon("list_alt", 40, y + 24, 20, ON_VAR)
    s.t(60, y + 14, "Chi tiết từng bước (12)", "labelLarge", ON)
    s.icon("expand_less", 324, y + 24, 22, ON_VAR)
    ry = y + 48
    for ic, lab, tm in STEPS:
        s.icon(ic, 40, ry + 18, 16, ON_VAR)
        s.t(60, ry + 8, lab, "bodyMedium", ON, maxw=200)
        s.text(328, ry + 18 + 12 * 0.36, tm, 12, MUTED, 400, "end", mono=True)
        ry += 36
    y += rows_h + 20
    y = s.t(16, y, "Việc gần đây", "titleMedium", ON) + 8
    history(s, y, HIST[:2])
    # fixed bottom (composer + nav) on a taller frame: shift by drawing at the frame bottom
    off = s.h - H
    s.add(f'<g transform="translate(0,{off})">')
    composer(s, busy=False)
    s.nav("Việc")
    s.add("</g>")


# ===================================================================================== 15 player full screen (landscape)
@screen("15-player-fullscreen", "15 Xem màn hình PC toàn màn hình (ngang 800×360)", w=800, h=360)
def fullscreen(s):
    s.rect(0, 0, 800, 360, "#000000")
    pc_desktop(s, 80, 0, 640, 360, "running", redact=True, r=0)
    for gid, y0, y1, a, b in (("st", 0, 72, 0.7, 0), ("sb", 280, 360, 0, 0.75)):
        g = s.id(gid)
        s.defs.append(f'<linearGradient id="{g}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-opacity="{a}"/>'
                      f'<stop offset="1" stop-opacity="{b}"/></linearGradient>')
        s.add(f'<rect x="80" y="{y0}" width="640" height="{y1 - y0}" fill="url(#{g})"/>')
    round_btn(s, 112, 34, "close", r=20)
    s.rect(624, 14, 96, 40, STOP, 20)
    s.icon("stop", 646, 34, 20, ON_STOP, filled=True)
    s.text(660, 34 + 14 * 0.36, "STOP", 14, ON_STOP, 700, ls=1.2)
    nx = pill(s, 96, 314, "TRỰC TIẾP · 2 hình/giây", dot=AI, h=28, size=12)
    pill(s, nx + 8, 314, "Đã che 1 cửa sổ bí mật", icon="visibility_off", h=28, size=12)
    round_btn(s, 688, 328, "pause", r=22, size=22)
    round_btn(s, 636, 328, "fullscreen_exit", r=22, size=22)


# ===================================================================================== 16 settings additions
@screen("16-settings-v3", "16 Cài đặt: Xem màn hình PC + khoá suốt cả việc")
def settings(s):
    s.status_bar("18:45")
    s.presence("idle")
    s.t(16, 104, "Cài đặt", "headlineSmall", ON)
    y = 152
    s.t(16, y, "Bảo mật · đặt trên máy tính", "labelLarge", ON_VAR)
    y += 28
    s.rect(16, y, 328, 76, SC_HIGH, 16)
    s.icon("shield", 40, y + 26, 22, ON_PRIMARY_C, filled=True)
    s.t(64, y + 14, "Mức hiện tại: Cân bằng", "labelLarge", ON, weight=600)
    s.para(64, y + 36, "Đổi trong turbo-desktop.toml trên máy tính.", "bodySmall", ON_VAR, maxw=264)
    y += 84

    def row(ic, title, value, sub=None, new=False):
        def d(top):
            s.icon(ic, 40, top + 36, 22, ON_VAR, filled=ic in ("lock",))
            s.t(68, top + 10, title, "labelLarge", ON, maxw=236)
            s.t(68, top + 32, value, "bodySmall", PRIMARY if value.startswith(("Bật", "Suốt")) else ON_VAR, weight=500)
            if sub:
                s.t(68, top + 50, sub, "bodySmall", MUTED, maxw=250)
            s.icon("chevron_right", 330, top + 36, 18, MUTED)
        return d

    def tworow(ic, title, value):
        def d(top):
            s.icon(ic, 40, top + 36, 22, ON_VAR, filled=ic in ("lock",))
            lines = wrap(title, 14, 236, 500)
            for k, ln in enumerate(lines):
                s.t(68, top + 6 + k * 20, ln, "labelLarge", ON)
            s.t(68, top + 6 + len(lines) * 20 + 2, value, "bodySmall", PRIMARY, weight=500)
            s.icon("chevron_right", 330, top + 36, 18, MUTED)
        return d

    y = s.list_group(16, y, 328, [
        row("videocam", "Xem màn hình PC", "Bật · 2 hình/giây", "Cửa sổ khớp mẫu bí mật bị che đen"),
        tworow("mouse", "Khoá phím/chuột khi làm việc từ điện thoại", "Suốt cả việc"),
        row("gpp_maybe", "Hỏi trước khi gửi, xoá, cài", "Bật")], h=72)
    y += 24
    s.t(16, y, "Trên điện thoại này", "labelLarge", ON_VAR)
    def toggle(ic, title, sub):
        def d(top):
            s.icon(ic, 40, top + 36, 22, ON_VAR)
            s.t(68, top + 14, title, "labelLarge", ON, maxw=200)
            s.t(68, top + 36, sub, "bodySmall", MUTED, maxw=200)
            s.rect(284, top + 20, 52, 32, SC_HIGHEST, 16, stroke=OUTLINE, sw=2)
            s.circle(300, top + 36, 8, OUTLINE)
        return d

    s.list_group(16, y + 28, 328, [row("language", "Ngôn ngữ", "Theo hệ thống"),
                                   toggle("tune", "Hiện chi phí quy đổi theo API", "Tắt · chỉ để so sánh")], h=72)
    s.nav("Cài đặt")


# ===================================================================================== 17-18 Báo cáo
BAR, BAR_TODAY = "#3E8F78", PRIMARY   # one series, mint; today in full mint and labelled


def report_head(s, seg):
    s.status_bar("18:46")
    s.presence("idle")
    s.t(16, 104, "Báo cáo", "headlineSmall", ON)
    y = 148
    s.rect(16.5, y + 0.5, 327, 39, "none", 20, stroke=OUTLINE)
    for i, lab in enumerate(("Tổng quan", "Nhật ký")):
        x = 16 + i * 164
        on = lab == seg
        if on:
            s.rect(x, y, 164, 40, PRIMARY_C, 20)
        lw = tw(lab, 14, 600 if on else 500) + (26 if on else 0)
        lx = x + (164 - lw) / 2
        if on:
            s.icon("check", lx + 9, y + 20, 18, ON_PRIMARY_C)
            lx += 26
        s.t(lx, y + 10, lab, "labelLarge", ON_PRIMARY_C if on else ON, weight=600 if on else 500)
    s.line(180, y, 180, y + 40, OUTLINE)
    return y + 56


def chips(s, y, labels, sel):
    x = 16
    for i, c in enumerate(labels):
        on = i == sel
        w = tw(c, 14, 500) + (40 if on else 24)
        if on:
            s.rect(x, y, w, 32, PRIMARY_C, 8)
            s.icon("check", x + 16, y + 16, 18, ON_PRIMARY_C)
            s.t(x + 28, y + 6, c, "labelLarge", ON_PRIMARY_C)
        else:
            s.rect(x + 0.5, y + 0.5, w - 1, 31, "none", 8, stroke=OUTLINE)
            s.t(x + 12, y + 6, c, "labelLarge", ON_VAR)
        x += w + 8


@screen("17-bao-cao-tong-quan", "17 Báo cáo · Tổng quan (không tiền; token giải thích bằng lời) · khung cuộn dài", h=1080)
def report_overview(s):
    y = report_head(s, "Tổng quan")
    chips(s, y, ("Hôm nay", "7 ngày", "30 ngày"), 1)
    y += 48
    tiles = [("12", "Việc xong", "check_circle", PRIMARY), ("1", "Dừng / lỗi", "stop_circle", STOP_TEXT),
             ("38 phút", "Thời gian AI làm", "schedule", ON_VAR)]
    tw_ = (328 - 16) / 3
    for i, (num, lab, ic, col) in enumerate(tiles):
        tx = 16 + i * (tw_ + 8)
        s.rect(tx, y, tw_, 104, SC, 16)
        s.icon(ic, tx + 23, y + 24, 18, col, filled=ic != "schedule")
        s.t(tx + 14, y + 42, num, "headlineSmall" if len(num) < 4 else "titleLarge", ON)
        s.para(tx + 14, y + 72, lab, "bodySmall", ON_VAR, maxw=tw_ - 22)
    y += 120
    # bar chart: tasks per day. One series, so no legend; the title names it. Thin bars, rounded data end,
    # recessive grid, one direct label (today).
    s.rect(16, y, 328, 224, SC, 16)
    s.t(32, y + 16, "Việc mỗi ngày", "titleMedium", ON)
    s.t(32, y + 40, "7 ngày qua · 13 việc", "bodySmall", MUTED)
    data = [("T3", 1), ("T4", 0), ("T5", 2), ("T6", 3), ("T7", 1), ("CN", 2), ("Nay", 4)]
    base, top_, bw = y + 188, y + 80, 20
    for g in (0, 2, 4):
        gy = base - (base - top_) * g / 4
        s.line(48, gy, 328, gy, OUTLINE_VAR)
        s.text(38, gy + 4, str(g), 11, MUTED, 400, "end")
    step = (328 - 52) / 7
    for i, (d, v) in enumerate(data):
        bx = 52 + i * step + (step - bw) / 2
        h = (base - top_) * v / 4
        if v:
            s.add(f'<path d="M{bx:g} {base:g} V{base - h + 4:g} Q{bx:g} {base - h:g} {bx + 4:g} {base - h:g} '
                  f'H{bx + bw - 4:g} Q{bx + bw:g} {base - h:g} {bx + bw:g} {base - h + 4:g} V{base:g} Z" '
                  f'fill="{BAR_TODAY if d == "Nay" else BAR}"/>')
        s.text(bx + bw / 2, base + 18, d, 11, ON if d == "Nay" else MUTED, 600 if d == "Nay" else 400, "middle")
    nx = 52 + 6 * step + (step - bw) / 2
    s.text(nx + bw / 2, top_ - 6, "4", 12, ON, 600, "middle")
    y += 240
    s.t(16, y, "Hạn mức AI", "titleMedium", ON)
    y += 32
    s.rect(16, y, 328, 120, SC, 16)
    s.icon("bar_chart", 41, y + 24, 20, ON_VAR)
    s.t(60, y + 14, "Đã dùng khoảng 41.000 token hôm nay", "labelLarge", ON, weight=600, maxw=272)
    s.para(32, y + 46, "Token là lượng chữ AI đọc và viết. Gói Claude của bạn không tính tiền theo token; con số chỉ "
           "để so sánh.", "bodySmall", ON_VAR, maxw=296)
    y += 136
    s.t(16, y, "Theo app", "titleMedium", ON)
    y += 32
    apps = [("Zalo", 5), ("Máy tính", 4), ("Notepad", 2)]

    def arow(it):
        name, n = it

        def d(top):
            s.icon("web_asset", 40, top + 24, 20, ON_VAR)
            s.t(68, top + 14, name, "labelLarge", ON)
            s.rect(160, top + 20, 110 * n / 5, 8, BAR, 4)
            s.text(328, top + 24 + 13 * 0.36, f"{n} việc", 13, ON_VAR, 500, "end")
        return d

    s.list_group(16, y, 328, [arow(a) for a in apps], h=48)
    s.add(f'<g transform="translate(0,{s.h - H})">')
    s.nav("Báo cáo")
    s.add("</g>")


@screen("18-bao-cao-nhat-ky", "18 Báo cáo · Nhật ký (danh sách kiểm toán từ v2)")
def report_log(s):
    y = report_head(s, "Nhật ký")
    s.rect(16, y, 328, 56, PRIMARY_C, 16)
    s.icon("verified_user", 42, y + 28, 22, ON_PRIMARY_C, filled=True)
    s.t(66, y + 8, "Chuỗi băm hợp lệ · 25 mục", "labelLarge", ON_PRIMARY_C, weight=600)
    s.t(66, y + 30, "Mỗi dòng ghi kèm mã băm của dòng trước", "bodySmall", ON_PRIMARY_C)
    y += 68
    chips(s, y, ["Tất cả", "Hành động", "Duyệt", "Dừng"], 0)
    y += 44
    s.t(16, y, "Hôm nay", "labelMedium", ON_VAR)
    y += 22
    rows = [("18:43:09", "check_circle", PRIMARY, "Xong: tóm tắt tin chị Lan", "12 bước · 3:09"),
            ("18:40:05", "open_in_new", ON_VAR, "Đã mở Zalo (w4)", "Mở ứng dụng · qua Start Menu"),
            ("18:40:02", "assignment", ON_VAR, "Bắt đầu việc", "Mở Zalo và tóm tắt tin nhắn mới…"),
            ("18:09:21", "stop_circle", STOP_TEXT, "Đã dừng (STOP)", "Điện thoại này"),
            ("18:08:56", "gpp_maybe", WARN, "Từ chối: bấm “Gửi”", "Thư – Soạn thư · bạn quyết định"),
            ("18:05:40", "videocam", ON_VAR, "Xem màn hình PC (1 phút)", "Điện thoại này")]
    for i, (tm, ic, col, a, b) in enumerate(rows):
        top = y + i * 60
        if top + 60 > 712:
            break
        if i:
            s.line(16, top, 344, top)
        s.text(16, top + 26, tm, 12, MUTED, 400, mono=True)
        s.icon(ic, 96, top + 30, 20, col, filled=ic in ("stop_circle", "gpp_maybe", "check_circle"))
        s.t(118, top + 10, a, "labelLarge", ON, maxw=206)
        s.para(118, top + 32, b, "bodySmall", MUTED, maxw=200, max_lines=1)
        s.icon("chevron_right", 334, top + 30, 18, MUTED)
    s.nav("Báo cáo")


# ===================================================================================== build
def build():
    out = []
    for key, title, fn, w, h in SCREENS:
        s = Svg(key, title, w, h)
        fn(s)
        (HERE / f"{key}.svg").write_text(s.render(), encoding="utf-8")
        out.append((key, title, w, h, s.render(fonts_inline=False)))
    faces = ""
    for wt, n in ((400, "Regular"), (500, "Medium"), (600, "SemiBold"), (700, "Bold")):
        b = base64.b64encode((HERE / "_fonts" / f"BeVietnamPro-{n}.ttf").read_bytes()).decode()
        faces += f"@font-face{{font-family:'Be Vietnam Pro';font-weight:{wt};src:url(data:font/ttf;base64,{b})}}"
    b = base64.b64encode((HERE / "_fonts" / "JetBrainsMono.ttf").read_bytes()).decode()
    faces += f"@font-face{{font-family:'JetBrains Mono';font-weight:100 800;src:url(data:font/ttf;base64,{b})}}"
    port = [o for o in out if o[2] == W]
    land = [o for o in out if o[2] != W]
    cell = lambda o: (f'<figure><div class="ph" style="width:{o[2]}px;height:{o[3]}px">{o[4]}</div>'  # noqa: E731
                      f'<figcaption>{escape(o[1])}</figcaption></figure>')
    html = (f'<!doctype html><meta charset="utf-8"><title>Turbo Remote v3</title><style>{faces}'
            "body{margin:0;background:#2A2D31;font-family:'Be Vietnam Pro';color:#ECEAE4;padding:40px}"
            "h1{font-weight:600;font-size:28px;margin:0 0 6px}p{margin:0 0 32px;color:#A9B0BA;font-size:15px}"
            ".g{display:flex;gap:36px;align-items:flex-start;flex-wrap:wrap;margin-bottom:44px}"
            "figure{margin:0}.ph{border-radius:28px;box-shadow:0 12px 40px #0008;overflow:hidden}"
            "figcaption{margin-top:14px;font-size:15px;font-weight:500;color:#D7D4CD;max-width:360px}</style>"
            "<h1>Turbo Remote v3 · màn Việc</h1><p>Player 16:9 + thẻ việc (lệnh / trạng thái / kết quả) + bước gọn"
            " + ô giao việc ở dưới · nav 4 mục · 17/11/2026</p>"
            f'<div class="g">{"".join(cell(o) for o in port)}</div><div class="g">{"".join(cell(o) for o in land)}</div>')
    (HERE / "_sheet.html").write_text(html, encoding="utf-8")
    for w_ in WARNINGS:
        print("WARN", w_)
    print(len(out), "screens")


if __name__ == "__main__":
    build()
