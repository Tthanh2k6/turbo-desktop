"""Generates the 9 phone mockups (412x915 dp) as SVG. Run: python _generate.py
Design notes: operator-console feel. Graphite surfaces, one signal colour per meaning (mint = running/ok,
amber = needs you, red = STOP/danger). Material 3 spacing (4/8/16/24), 48dp touch targets, 16dp gutters,
text >= 14sp, labels in Vietnamese (default language)."""
from pathlib import Path
from xml.sax.saxutils import escape

W, H = 412, 915
BG, S1, S2, LINE = "#14161A", "#1D2026", "#262A32", "#343944"
TX, TX2, TX3 = "#ECE9E2", "#A9ADB5", "#9AA0AB"   # TX3 raised for WCAG AA (>= 4.5:1 on S1/S2)
MINT, AMBER, RED, BLUE = "#5CD6B0", "#F2B84B", "#FF6B63", "#7AA8FF"
ORANGE = "#E0461D"   # AI-is-controlling indicator (same colour as the border on the PC screen)
SANS = "Roboto, 'Segoe UI', Arial, sans-serif"
MONO = "'JetBrains Mono', Consolas, monospace"


class Svg:
    def __init__(self, title):
        self.title, self.parts = title, []

    def add(self, s):
        self.parts.append(s)

    def rect(self, x, y, w, h, fill=S1, r=0, stroke=None, sw=1, op=None):
        st = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
        o = f' fill-opacity="{op}"' if op else ""
        self.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}"{o}{st}/>')

    def text(self, x, y, s, size=16, fill=TX, weight=400, anchor="start", mono=False, ls=0):
        fam = MONO if mono else SANS
        self.add(f'<text x="{x}" y="{y}" font-family="{fam}" font-size="{size}" font-weight="{weight}" '
                 f'fill="{fill}" text-anchor="{anchor}" letter-spacing="{ls}">{escape(s)}</text>')

    def line(self, x1, y1, x2, y2, c=LINE, sw=1):
        self.add(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{c}" stroke-width="{sw}"/>')

    def circle(self, x, y, r, fill):
        self.add(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}"/>')

    def button(self, x, y, w, label, fill=MINT, fg="#08201A", h=48, outline=False):
        if outline:
            self.rect(x, y, w, h, "none", 24, stroke=LINE, sw=1.5)
            fg = TX
        else:
            self.rect(x, y, w, h, fill, 24)
        self.text(x + w / 2, y + h / 2 + 5.5, label, 16, fg, 600, "middle")

    def switch(self, x, y, on):
        self.rect(x, y, 52, 32, MINT if on else S2, 16, stroke=None if on else TX3, sw=2)
        self.circle(x + (36 if on else 16), y + 16, 12 if on else 8, "#08201A" if on else TX3)

    def card(self, x, y, w, h, fill=S1, r=16, stroke=None):
        self.rect(x, y, w, h, fill, r, stroke=stroke)

    def chrome(self, active=None, stop=True, title="Turbo Remote", sub=None, nav=True, back=False):
        self.rect(0, 0, W, H, BG)
        self.text(16, 18, "09:41", 12, TX2, 500)
        self.text(W - 16, 18, "Tailscale · đã kết nối", 12, TX2, 400, "end")
        if back:
            self.text(16, 62, "←", 24, TX2)
        self.text(48 if back else 16, 62, title, 20, TX, 600)
        if sub:
            self.text(48 if back else 16, 80, sub, 13, TX3)
        if stop:
            self.rect(W - 112, 34, 96, 44, RED, 22)
            self.rect(W - 100, 48, 14, 14, "#2A0A08", 3)
            self.text(W - 76, 62, "STOP", 15, "#2A0A08", 800, ls=1)
        if nav:
            self.rect(0, H - 80, W, 80, S1)
            self.line(0, H - 80, W, H - 80)
            items = [("Việc", "▤"), ("Trực tiếp", "▶"), ("Duyệt", "✔"), ("Nhật ký", "☰"), ("Cài đặt", "⚙")]
            for i, (lab, ic) in enumerate(items):
                cx = 41 + i * 82.5
                on = lab == active
                if on:
                    self.rect(cx - 32, H - 72, 64, 32, "#1F3B33", 16)
                self.text(cx, H - 51, ic, 18, MINT if on else TX2, 400, "middle")
                self.text(cx, H - 22, lab, 12, TX if on else TX3, 600 if on else 400, "middle")

    def frame(self, solid=False):
        """Orange frame around the whole screen: glowing while the AI acts, solid while PC input is locked."""
        if not solid:
            for i, op in ((10, 0.10), (7, 0.18), (4, 0.30)):
                self.add(f'<rect x="{i/2}" y="{i/2}" width="{W - i}" height="{H - i}" rx="18" fill="none" stroke="{ORANGE}" '
                         f'stroke-width="{i}" stroke-opacity="{op}"/>')
            self.add(f'<rect x="1.5" y="1.5" width="{W - 3}" height="{H - 3}" rx="16" fill="none" stroke="{ORANGE}" stroke-width="3" stroke-opacity="0.9"/>')
        else:
            self.add(f'<rect x="3" y="3" width="{W - 6}" height="{H - 6}" rx="16" fill="none" stroke="{ORANGE}" stroke-width="6"/>')

    def chip(self, x, y, label, color=ORANGE, w=None):
        w = w or (len(label) * 8.2 + 44)
        self.rect(x, y, w, 32, "#2B1812", 16, stroke=color, sw=1.5)
        self.circle(x + 18, y + 16, 5, color)
        self.text(x + 32, y + 21, label, 13, TX, 600)
        return w

    def save(self, path):
        body = "\n".join(self.parts)
        Path(path).write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" '
            f'aria-label="{escape(self.title)}">\n<title>{escape(self.title)}</title>\n{body}\n</svg>\n', "utf-8")


OUT = Path(__file__).parent


def s01():
    s = Svg("Chọn mức bảo mật lần đầu")
    s.chrome(stop=False, title="Chào mừng", sub="Chọn mức bảo mật. Đổi lại bất cứ lúc nào.", nav=False)
    s.text(16, 122, "Bước 1 trên 3", 12, MINT, 600, ls=0.5)
    opts = [("Thoáng", "Dễ dùng, mặc định", "Cùng mạng Wi-Fi với máy tính, ghép một lần. Phiên 12 giờ, không cần mã Authenticator. Chỉ hỏi trước khi xoá vĩnh viễn, thanh toán, gỡ phần mềm, đổi cài đặt bảo mật Windows.", True),
            ("Cân bằng", "Điều khiển từ điện thoại trong nhà hoặc qua Tailscale", "Phiên 2 giờ, mã Google Authenticator khi mở phiên. Hỏi cả khi gửi, xoá, cài đặt, mở terminal.", False),
            ("Chặt", "Cách bảo mật của chủ dự án", "Vân tay + mã Authenticator, hỏi mọi hành động nhạy cảm, Cloudflare Access bắt buộc nếu bật tunnel.", False)]
    y = 140
    for name, tag, desc, sel in opts:
        s.card(16, y, W - 32, 198, S2 if sel else S1, 20, stroke=MINT if sel else LINE)
        s.circle(44, y + 34, 11, "none")
        s.add(f'<circle cx="44" cy="{y + 34}" r="11" fill="none" stroke="{MINT if sel else TX3}" stroke-width="2"/>')
        if sel:
            s.circle(44, y + 34, 6, MINT)
        s.text(68, y + 40, name, 20, TX, 700)
        s.text(32, y + 72, tag, 13, MINT if sel else TX2, 500)
        words, line, ly = desc.split(), "", y + 100
        for w in words:
            if len(line) + len(w) > 44:
                s.text(32, ly, line, 14, TX2); ly += 22; line = ""
            line += w + " "
        s.text(32, ly, line, 14, TX2)
        y += 214
    s.button(16, 800, W - 32, "Dùng mức Thoáng")
    s.text(W / 2, 876, "Từng mục vẫn bật/tắt riêng được trong Cài đặt", 13, TX3, 400, "middle")
    s.save(OUT / "01-first-run-preset.svg")


def s02():
    s = Svg("Ghép với máy tính")
    s.chrome(stop=False, title="Ghép với máy tính", sub="Làm một lần, ngay tại máy tính", nav=False, back=True)
    s.text(16, 122, "Bước 2 trên 3", 12, MINT, 600, ls=0.5)
    s.text(16, 156, "Trên máy tính chạy:", 15, TX2)
    s.rect(16, 168, W - 32, 44, S2, 12)
    s.text(32, 196, "python -m turbo_hub pair", 15, MINT, 500, mono=True)
    s.card(16, 232, W - 32, 300, S1, 20)
    s.rect(56, 248, 300, 268, "#000", 12)
    s.rect(72, 264, 268, 236, "none", 12, stroke=MINT, sw=3)
    for cx, cy in ((72, 264), (340, 264), (72, 500), (340, 500)):
        s.circle(cx, cy, 3, MINT)
    s.text(W / 2, 390, "Hướng camera vào mã QR", 15, TX, 500, "middle")
    s.text(W / 2, 414, "trên màn hình máy tính", 13, TX2, 400, "middle")
    s.text(16, 570, "Hoặc nhập tay", 14, TX2, 600)
    s.rect(16, 582, W - 32, 56, S1, 12, stroke=LINE)
    s.text(32, 616, "Dán nội dung ghép (turbo-pair:…)", 15, TX3)
    s.rect(16, 650, 190, 56, S1, 12, stroke=LINE)
    s.text(32, 684, "Mã 6 số", 15, TX3)
    s.rect(222, 650, 174, 56, S1, 12, stroke=LINE)
    s.text(238, 684, "Địa chỉ hub", 15, TX3)
    s.card(16, 728, W - 32, 76, "#2A2416", 16)
    s.text(32, 756, "Sau khi ghép, so khớp 5 nhóm ký tự", 14, AMBER, 600)
    s.text(32, 780, "ở đây với màn hình máy tính:  9F3A  C21D  7B80", 14, TX2, mono=True)
    s.button(16, 830, W - 32, "Ghép")
    s.save(OUT / "02-pairing.svg")


def s03():
    s = Svg("Màn hình chính: giao việc")
    s.chrome("Việc", sub="Máy tính đã kết nối · qua Tailscale")
    s.card(16, 100, W - 32, 64, S1, 16)
    s.circle(40, 132, 6, MINT)
    s.text(56, 128, "Phiên còn 1 giờ 23 phút", 15, TX, 600)
    s.text(56, 148, "Hôm nay: 12.400 token · $0,31", 13, TX2)
    s.text(W - 32, 138, "Gia hạn", 14, MINT, 600, "end")
    s.text(16, 200, "Giao việc cho máy tính", 14, TX2, 600)
    s.card(16, 212, W - 32, 168, S1, 20, stroke=LINE)
    s.text(32, 246, "Mở Máy tính và tính (12,5 + 7) × 3", 17, TX)
    s.rect(31, 256, 2, 20, MINT)
    s.text(32, 352, "Gợi ý: nói rõ mở ứng dụng nào, làm gì", 13, TX3)
    s.button(W - 160, 396, 144, "Gửi việc")
    s.text(16, 480, "Việc gần đây", 14, TX2, 600)
    rows = [("Tính (12,5 + 7) × 3", "Xong · 4 bước · 2.100 token", MINT),
            ("Tạo thư mục Báo cáo trên Desktop", "Xong · 6 bước · 3.800 token", MINT),
            ("Xoá thư mục Báo cáo cũ", "Bạn đã từ chối · 3 bước", AMBER)]
    y = 496
    for t, d, c in rows:
        s.card(16, y, W - 32, 76, S1, 16)
        s.rect(16, y + 20, 4, 36, c, 2)
        s.text(36, y + 34, t, 16, TX, 500)
        s.text(36, y + 58, d, 13, TX2)
        y += 88
    s.save(OUT / "03-home-task.svg")


def s04():
    s = Svg("Đang chạy: nhật ký trực tiếp")
    s.chrome("Trực tiếp", title="Đang chạy", sub="Mở Máy tính và tính (12,5 + 7) × 3")
    s.rect(16, 96, W - 32, 6, S2, 3)
    s.rect(16, 96, 190, 6, MINT, 3)
    ev = [("09:40:12", "Kế hoạch: mở Calculator, nhập phép tính", TX2, ""),
          ("09:40:13", "Công cụ  windows_list", TX, "ok"),
          ("09:40:14", "Công cụ  launch_app  Calculator", TX, "ok"),
          ("09:40:16", "Công cụ  inspect_compact  w1", TX, "ok · 38 điều khiển"),
          ("09:40:18", "Công cụ  act  [w1:e12] Nút 1", TX, "ok · UIA"),
          ("09:40:18", "Công cụ  act  [w1:e19] Nút dấu cộng", TX, "ok · UIA"),
          ("09:40:19", "Công cụ  act  [w1:e31] Nút bằng", TX, "ok · UIA")]
    s.chip(16, 108, "AI đang điều khiển")
    y = 156
    for t, line, c, res in ev:
        s.text(16, y + 14, t, 12, TX3, 400, mono=True)
        s.text(94, y + 14, line, 14, c)
        if res:
            s.text(94, y + 34, res, 12, MINT)
            y += 52
        else:
            y += 40
    s.card(16, 508, W - 32, 84, S2, 16)
    s.text(32, 534, "Kết quả đọc được", 12, TX3, 600, ls=0.5)
    s.text(32, 576, "58,5", 28, TX, 700, mono=True)
    s.card(16, 604, W - 32, 84, S1, 16)
    s.text(32, 630, "Việc này", 12, TX3, 600, ls=0.5)
    s.text(32, 656, "2.100 token vào · 380 ra", 15, TX)
    s.text(32, 678, "Phiên: 9.800 · Hôm nay: 12.400 · $0,31", 13, TX2)
    s.button(16, 704, W - 32, "Lấy lại quyền (tạm dừng việc này)", fill="none", fg=TX, outline=True)
    s.text(W / 2, 774, "Mở khoá phím/chuột ngay và giữ AI lại", 12, TX3, 400, "middle")
    s.frame()
    s.save(OUT / "04-live-run.svg")


def s05():
    s = Svg("Duyệt hành động nhạy cảm")
    s.chrome("Duyệt", sub="Máy tính đang đợi bạn")
    s.rect(0, 0, W, H - 80, "#000", op=0.55)
    s.rect(0, 240, W, H - 80 - 240, S1, 28)
    s.rect(W / 2 - 18, 252, 36, 4, TX3, 2)
    s.circle(44, 296, 14, AMBER)
    s.text(44, 301, "!", 16, "#2A1B00", 800, "middle")
    s.text(68, 302, "Cần bạn duyệt", 20, TX, 700)
    s.text(W - 24, 302, "1:48", 15, AMBER, 700, "end", mono=True)
    s.text(24, 340, "AI muốn bấm  “Gửi”", 18, TX, 600)
    s.text(24, 364, "trong cửa sổ  Thư mới – Mail", 14, TX2)
    s.rect(24, 384, W - 48, 150, S2, 16)
    s.rect(40, 402, W - 80, 114, "#fff", 8)
    s.rect(56, 420, 160, 10, "#C9CDD4", 5)
    s.rect(56, 440, 230, 10, "#E1E3E8", 5)
    s.rect(W - 160, 462, 96, 40, "#2B6BFF", 10)
    s.text(W - 112, 487, "Gửi", 15, "#fff", 600, "middle")
    s.add(f'<rect x="{W - 166}" y="456" width="108" height="52" rx="14" fill="none" stroke="{RED}" stroke-width="3"/>')
    s.text(24, 560, "Ảnh cắt đúng vùng điều khiển, chụp lúc yêu cầu", 12, TX3)
    s.text(24, 592, "Không trả lời sau 2 phút = Từ chối", 13, TX2)
    s.button(24, 616, 172, "Từ chối", outline=True)
    s.button(212, 616, 176, "Cho phép", fill=AMBER, fg="#2A1B00")
    s.text(W / 2, 700, "Cho phép sẽ hỏi vân tay (chỉ khi mức Chặt)", 13, TX3, 400, "middle")
    s.save(OUT / "05-approval-sheet.svg")


def s06():
    s = Svg("Mở phiên: mã Authenticator")
    s.chrome(stop=False, title="Mở phiên", sub="Phiên cũ đã hết hạn", nav=False, back=True)
    s.card(16, 108, W - 32, 78, S1, 16)
    s.text(32, 140, "Không cần quét lại QR", 15, TX, 600)
    s.text(32, 164, "Chỉ cần mã Google Authenticator và vân tay", 13, TX2)
    s.text(16, 232, "Mã 6 số trong Google Authenticator", 14, TX2, 600)
    for i, d in enumerate("48"):
        s.rect(16 + i * 62, 248, 54, 68, S2, 12, stroke=MINT if i == 2 else None, sw=2)
        s.text(43 + i * 62, 294, d, 30, TX, 700, "middle", mono=True)
    for i in range(2, 6):
        s.rect(16 + i * 62, 248, 54, 68, S1, 12, stroke=MINT if i == 2 else LINE, sw=2)
    s.text(16, 346, "Mã đổi sau mỗi 30 giây. Mỗi mã chỉ dùng một lần.", 13, TX3)
    keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "", "0", "⌫"]
    for i, k in enumerate(keys):
        if not k:
            continue
        x, y = 16 + (i % 3) * 130, 400 + (i // 3) * 76
        s.rect(x, y, 122, 64, S1, 16)
        s.text(x + 61, y + 42, k, 24, TX, 500, "middle")
    s.button(16, 724, W - 32, "Mở phiên và xác nhận vân tay")
    s.text(W / 2, 800, "Sai 5 lần: khoá 15 phút và máy tính báo cho bạn", 13, TX3, 400, "middle")
    s.text(W / 2, 826, "Phiên mới kéo dài 2 giờ", 13, TX2, 400, "middle")
    s.save(OUT / "06-open-session.svg")


def wrap(text, n):
    out, line = [], ""
    for w in text.split():
        if len(line) + len(w) + 1 > n:
            out.append(line.strip()); line = ""
        line += w + " "
    out.append(line.strip())
    return out


def s07():
    s = Svg("Cài đặt: bảo mật theo mức")
    s.chrome("Cài đặt", title="Cài đặt", sub="Mức hiện tại: Cân bằng")
    y = 100
    TEXT_W = 38   # characters per line: the text column stops 12dp before the 52dp toggle (never runs under it)

    def group(name, color, items):
        nonlocal y
        s.text(16, y + 14, name, 12, color, 700, ls=1)
        y += 26
        for t, d, kind in items:
            lines = wrap(d, TEXT_W)
            h = 28 + 24 + 18 * len(lines) + 8
            s.card(16, y, W - 32, h, S1, 16)
            s.text(32, y + 30, t, 16, TX, 600)
            for k, ln in enumerate(lines):
                s.text(32, y + 52 + 18 * k, ln, 13, TX2)
            if kind in (True, False):
                s.switch(W - 84, y + 12, kind)
            elif kind == "locked":
                s.switch(W - 84, y + 12, True)
                s.text(W - 58, y + h - 14, "🔒", 12, TX3, 400, "middle")
            else:
                s.text(W - 32, y + 34, kind + " ›", 14, MINT, 600, "end")
            y += h + 8
        y += 4
    group("CƠ BẢN (luôn bật)", MINT, [("STOP, nhật ký, ô mật khẩu", "Nút STOP, nhật ký kiểm toán và ô mật khẩu luôn được giữ.", "locked")])
    group("TRUNG BÌNH", AMBER, [("Hỏi trước khi gửi / xoá / cài", "AI tạm dừng và hỏi bạn trên điện thoại.", True),
                                ("Mã Google Authenticator", "Cần mã 6 số mỗi lần mở phiên mới.", True),
                                ("Khoá phím/chuột khi AI thao tác", "Chỉ khi AI dùng chuột/phím thật, tối đa 60 giây.", "Khi dùng chuột thật"),
                                ("Viền màn hình khi AI điều khiển", "Luôn bật khi đang khoá phím/chuột hoặc dùng chuột thật.", "locked")])
    group("CHẶT", RED, [("Vân tay khi duyệt", "Cho phép hoặc Từ chối đều cần vân tay.", False),
                        ("Cloudflare Access bắt buộc", "Tunnel chỉ nhận người đã đăng nhập Cloudflare.", False)])
    s.save(OUT / "07-settings.svg")


def s08():
    s = Svg("Nhật ký kiểm toán")
    s.chrome("Nhật ký", title="Nhật ký", sub="Chuỗi băm còn nguyên vẹn")
    s.card(16, 96, W - 32, 52, "#16302A", 14)
    s.circle(38, 122, 6, MINT)
    s.text(54, 127, "Chuỗi băm hợp lệ · 128 mục", 14, TX, 600)
    rows = [("09:40:19", "action", "act [w1:e31] Nút bằng", TX),
            ("09:40:12", "task_start", "Mở Máy tính và tính…", TX),
            ("09:38:02", "approval_resolved", "Từ chối: Xoá “Báo cáo cũ”", AMBER),
            ("09:37:41", "approval_requested", "Xoá “Báo cáo cũ” · thumbnail #a91f", AMBER),
            ("09:30:00", "session_start", "Điện thoại Pixel, mã TOTP đúng", TX),
            ("09:29:41", "rejected", "Chữ ký sai từ 10.0.2.2", RED),
            ("09:12:08", "stop", "Bấm STOP từ điện thoại", RED)]
    y = 164
    for t, k, d, c in rows:
        s.line(16, y + 62, W - 16, y + 62)
        s.text(16, y + 20, t, 12, TX3, 400, mono=True)
        s.text(96, y + 20, k, 12, c, 600, mono=True)
        s.text(16, y + 46, d, 15, TX)
        y += 70
    s.text(W / 2, 700, "Mỗi dòng ghi kèm mã băm của dòng trước", 13, TX3, 400, "middle")
    s.save(OUT / "08-audit-log.svg")


def s09():
    s = Svg("Trạng thái STOP")
    s.chrome("Việc", sub="Đã dừng. Máy tính không nhận lệnh.")
    s.rect(0, 0, W, 8, RED)
    s.card(16, 108, W - 32, 252, "#2A1513", 24, stroke=RED)
    s.circle(W / 2, 168, 30, RED)
    s.rect(W / 2 - 12, 156, 24, 24, "#2A0A08", 4)
    s.text(W / 2, 232, "ĐÃ DỪNG", 28, TX, 800, "middle", ls=2)
    s.text(W / 2, 262, "Tiến trình AI đã bị tắt lúc 09:12:08", 14, TX2, 400, "middle")
    s.text(W / 2, 286, "Việc mới và mọi thao tác bị chặn", 14, TX2, 400, "middle")
    s.button(40, 308, W - 80, "Cho chạy lại", fill=TX, fg=BG)
    s.text(16, 404, "Chuyện gì đã xảy ra", 14, TX2, 600)
    s.card(16, 416, W - 32, 140, S1, 16)
    s.text(32, 446, "09:12:06  Đang tính “(12,5 + 7) × 3”", 14, TX, mono=False)
    s.text(32, 474, "09:12:08  Bạn bấm STOP", 14, RED, 600)
    s.text(32, 502, "09:12:08  Dừng 1 tiến trình, huỷ 0 yêu cầu duyệt", 14, TX2)
    s.text(32, 530, "Mục này đã ghi vào nhật ký", 13, TX3)
    s.text(16, 590, "Phím nóng trên máy tính", 14, TX2, 600)
    s.rect(16, 602, W - 32, 52, S1, 14)
    s.text(32, 634, "Ctrl + Alt + Shift + K", 15, TX, 500, mono=True)
    s.text(W - 32, 634, "cũng dừng", 13, TX3, 400, "end")
    s.text(16, 690, "Khung cam trên máy tính", 14, TX2, 600)
    s.rect(16, 702, W - 32, 76, S1, 14)
    s.rect(32, 722, 44, 36, "none", 6, stroke=TX3, sw=2)
    s.add(f'<rect x="32" y="722" width="44" height="36" rx="6" fill="none" stroke="{ORANGE}" stroke-width="2" stroke-dasharray="4 4"/>')
    s.text(92, 744, "Đã tắt vì AI đã dừng", 14, TX, 500)
    s.text(92, 764, "Chỉ bật lại khi bạn cho chạy lại", 12, TX3)
    s.save(OUT / "09-stop-state.svg")


def s10():
    s = Svg("Đang chạy: phím và chuột của PC bị khoá")
    s.chrome("Trực tiếp", title="Đang chạy", sub="Mở Paint và vẽ một hình tròn")
    s.rect(16, 96, W - 32, 6, S2, 3)
    s.rect(16, 96, 120, 6, MINT, 3)
    s.chip(16, 120, "PC đang khoá phím/chuột", ORANGE, 236)
    s.text(264, 141, "còn 41 giây", 13, TX2, 500)
    ev = [("09:44:02", "Công cụ  act  [w3:e7] Canvas", TX, "dùng chuột thật · phím chuột của PC đang khoá"),
          ("09:44:04", "Công cụ  act  kéo chuột (40,60)→(180,60)", TX, "ok")]
    y = 176
    for t, line, c, res in ev:
        s.text(16, y + 14, t, 12, TX3, mono=True)
        s.text(94, y + 14, line, 14, c)
        s.text(94, y + 34, res, 12, MINT)
        y += 56
    more = [("09:44:06", "Công cụ  act  kéo chuột (180,60)→(180,140)", "ok"),
            ("09:44:08", "Công cụ  act  kéo chuột (180,140)→(40,140)", "ok"),
            ("09:44:10", "Công cụ  screenshot  w3", "ok · ảnh 480×320"),
            ("09:44:12", "Công cụ  act  [w3:e9] Nút Lưu", "đang chạy…")]
    y2 = 288
    for t, line, res in more:
        s.text(16, y2 + 14, t, 12, TX3, mono=True)
        s.text(94, y2 + 14, line, 14, TX)
        s.text(94, y2 + 34, res, 12, MINT)
        y2 += 56
    s.card(16, 520, W - 32, 92, "#2A1813", 18, stroke=ORANGE)
    s.text(32, 550, "Máy tính đang hiện thanh “AI đang điều khiển”", 14, TX, 600)
    s.text(32, 574, "Phím và chuột vật lý tạm bị khoá để AI không bị phá.", 13, TX2)
    s.text(32, 596, "Tự mở khoá sau tối đa 60 giây.", 13, TX2)
    s.button(16, 740, W - 32, "Lấy lại quyền", fill=ORANGE, fg="#fff")
    s.text(W / 2, 806, "Mở khoá phím/chuột ngay và tạm dừng việc đang chạy", 12, TX3, 400, "middle")
    s.frame(solid=True)
    s.save(OUT / "10-live-input-locked.svg")


if __name__ == "__main__":
    for fn in (s01, s02, s03, s04, s05, s06, s07, s08, s09, s10):
        fn()
    print("wrote 10 mockups to", OUT)


def _lum(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def contrast(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


if __name__ == "__main__":
    for fg in (TX, TX2, TX3, MINT, AMBER, RED, ORANGE):
        for bg in (BG, S1, S2):
            r = contrast(fg, bg)
            print(f"{fg} on {bg}: {r:.1f}", "OK" if r >= 4.5 else "FAIL (large text only)")
