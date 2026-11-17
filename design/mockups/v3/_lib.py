"""Drawing kit for the v2 phone mockups (360x800 dp). Tokens mirror TOKENS.md; text is measured with the real
Be Vietnam Pro / JetBrains Mono metrics (fontTools) so wrapping and clipping in the SVG match the bundled fonts."""
import json
from pathlib import Path
from xml.sax.saxutils import escape

from fontTools.ttLib import TTFont

HERE = Path(__file__).parent
W, H = 360, 800

# ---------------------------------------------------------------- colour roles (TOKENS.md)
BG, SC_LOW, SC, SC_HIGH, SC_HIGHEST = "#0F1114", "#16191D", "#1C2025", "#242930", "#2D333B"
ON, ON_VAR, MUTED = "#ECEAE4", "#A9B0BA", "#8C95A0"
OUTLINE, OUTLINE_VAR = "#6B737E", "#2E343C"
PRIMARY, ON_PRIMARY, PRIMARY_C, ON_PRIMARY_C = "#5CD6B0", "#04281F", "#123A30", "#9FF0D4"
AI, AI_TEXT, ON_AI, AI_C, ON_AI_C = "#E0461D", "#FF8A5C", "#1A0702", "#3A1A10", "#FFB59C"
STOP, STOP_TEXT, ON_STOP, STOP_C, ON_STOP_C = "#FF5468", "#FF7A86", "#2B0508", "#3D1419", "#FFB3BA"
WARN, ON_WARN, WARN_C, ON_WARN_C = "#F2B84B", "#2A1B00", "#3A2C0E", "#FFD98A"
INV, ON_INV = "#ECEAE4", "#0F1114"
SCRIM = "#000000"

SANS = "'Be Vietnam Pro', sans-serif"
MONO = "'JetBrains Mono', monospace"

# ---------------------------------------------------------------- type scale: (size, line height, weight)
T = {
    "headlineMedium": (28, 36, 600), "headlineSmall": (24, 32, 600), "titleLarge": (20, 28, 600),
    "titleMedium": (16, 24, 600), "bodyLarge": (16, 24, 400), "bodyMedium": (14, 20, 400), "bodySmall": (12, 16, 400),
    "labelLarge": (14, 20, 500), "labelMedium": (12, 16, 500), "button": (16, 24, 600),
}

_FONTS = {w: TTFont(HERE / "_fonts" / f"BeVietnamPro-{n}.ttf", lazy=True)
          for w, n in ((400, "Regular"), (500, "Medium"), (600, "SemiBold"), (700, "Bold"))}
_METRICS = {}
for w, f in _FONTS.items():
    cmap, hmtx, upm = f.getBestCmap(), f["hmtx"].metrics, f["head"].unitsPerEm
    _METRICS[w] = (cmap, hmtx, upm)
ICONS = json.loads((HERE / "_icons.json").read_text(encoding="utf-8"))
WARNINGS = []


def tw(s, size, weight=400, mono=False, ls=0.0):
    """Advance width of a string in dp."""
    if mono:
        return len(s) * 0.6 * size + ls * len(s)
    cmap, hmtx, upm = _METRICS[min(_METRICS, key=lambda k: abs(k - weight))]
    total = 0
    for ch in s:
        g = cmap.get(ord(ch))
        total += hmtx[g][0] if g else upm * 0.55
    return total / upm * size + ls * len(s)


def wrap(s, size, maxw, weight=400, mono=False):
    lines, cur = [], ""
    for word in s.split(" "):
        test = (cur + " " + word).strip()
        if tw(test, size, weight, mono) <= maxw or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


class Svg:
    def __init__(self, key, title, w=W, h=H):
        self.key, self.title, self.parts, self.defs = key, title, [], []
        self.w, self.h = w, h

    def add(self, s):
        self.parts.append(s)

    def id(self, name):
        return f"{self.key}-{name}"

    # -------------------------------------------------------- primitives
    def rect(self, x, y, w, h, fill=SC, r=0, stroke=None, sw=1, op=None, dash=None):
        st = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
        if dash:
            st += f' stroke-dasharray="{dash}"'
        o = f' opacity="{op}"' if op is not None else ""
        self.add(f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" rx="{r:g}" fill="{fill}"{o}{st}/>')

    def circle(self, x, y, r, fill, stroke=None, sw=1, op=None):
        st = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
        o = f' opacity="{op}"' if op is not None else ""
        self.add(f'<circle cx="{x:g}" cy="{y:g}" r="{r:g}" fill="{fill}"{st}{o}/>')

    def line(self, x1, y1, x2, y2, c=OUTLINE_VAR, sw=1):
        self.add(f'<line x1="{x1:g}" y1="{y1:g}" x2="{x2:g}" y2="{y2:g}" stroke="{c}" stroke-width="{sw}"/>')

    def text(self, x, base, s, size=14, fill=ON, weight=400, anchor="start", mono=False, ls=0, maxw=None):
        if maxw is not None and tw(s, size, weight, mono, ls) > maxw + 0.5:
            WARNINGS.append(f"{self.key}: text too wide ({tw(s, size, weight, mono, ls):.0f}>{maxw:.0f}): {s}")
        fam = MONO if mono else SANS
        ex = f' letter-spacing="{ls}"' if ls else ""
        tn = ' font-feature-settings="\'tnum\'"' if not mono else ' style="font-variant-ligatures:none"'
        self.add(f'<text x="{x:g}" y="{base:g}" font-family="{fam}" font-size="{size}" font-weight="{weight}" '
                 f'fill="{fill}" text-anchor="{anchor}"{ex}{tn}>{escape(s)}</text>')

    def t(self, x, top, s, role="bodyMedium", fill=ON, anchor="start", maxw=None, mono=False, weight=None, ls=0):
        """One line of text placed in its line box (top = top of the line box). Returns the bottom of the box."""
        size, lh, wt = T[role]
        wt = weight or wt
        self.text(x, top + lh / 2 + size * 0.36, s, size, fill, wt, anchor, mono, ls, maxw)
        return top + lh

    def para(self, x, top, s, role="bodyMedium", fill=ON_VAR, maxw=W - 32, anchor="start", mono=False, weight=None,
             max_lines=None):
        size, lh, wt = T[role]
        wt = weight or wt
        lines = wrap(s, size, maxw, wt, mono)
        if max_lines and len(lines) > max_lines:
            lines = lines[:max_lines]
            last = lines[-1]
            while tw(last + "…", size, wt, mono) > maxw and " " in last:
                last = last.rsplit(" ", 1)[0]
            lines[-1] = last + "…"
        for i, ln in enumerate(lines):
            self.text(x, top + i * lh + lh / 2 + size * 0.36, ln, size, fill, wt, anchor, mono)
        return top + len(lines) * lh

    def icon(self, name, cx, cy, size=24, fill=ON_VAR, filled=False):
        key = name + ("_fill1" if filled and name + "_fill1" in ICONS else "")
        d = ICONS[key]
        s = size / 960
        x, y = cx - size / 2, cy - size / 2
        self.add(f'<path transform="translate({x:g},{y:g}) scale({s:g}) translate(0,960)" d="{d}" fill="{fill}"/>')

    # -------------------------------------------------------- components
    def button(self, x, y, w, label, kind="filled", h=56, icon=None, fill=PRIMARY, fg=ON_PRIMARY, trailing_icon=None):
        """M3 common button. kind: filled | tonal | outlined | text. Label is titleMedium (16/24 SemiBold)."""
        if kind == "outlined":
            self.rect(x + 0.5, y + 0.5, w - 1, h - 1, "none", h / 2, stroke=OUTLINE, sw=1)
            fg = ON if fg == ON_PRIMARY else fg
        elif kind == "text":
            fg = PRIMARY if fg == ON_PRIMARY else fg
        else:
            self.rect(x, y, w, h, fill, h / 2)
        size = 16 if h >= 48 else 14
        lw = tw(label, size, 600)
        iw = 20 + 8 if icon else 0
        tiw = 8 + 18 if trailing_icon else 0
        total = lw + iw + tiw
        if total > w - 32:
            WARNINGS.append(f"{self.key}: button label too wide: {label}")
        sx = x + (w - total) / 2
        if icon:
            self.icon(icon, sx + 10, y + h / 2, 20, fg, filled=icon in ("fingerprint", "stop", "pan_tool", "key"))
        self.text(sx + iw, y + h / 2 + size * 0.36, label, size, fg, 600)
        if trailing_icon:
            self.icon(trailing_icon, sx + iw + lw + 8 + 9, y + h / 2, 18, fg)

    def status_bar(self, time="18:40"):
        self.text(22, 22, time, 13, ON, 500)
        # wifi + battery glyphs (system chrome, drawn plainly)
        self.icon("wifi", 300, 17, 16, ON, filled=False)
        self.rect(314, 11, 22, 11, "none", 3, stroke=ON, sw=1.2)
        self.rect(316, 13, 14, 7, ON, 1.5)
        self.rect(337, 14.5, 2, 4, ON, 1)

    def gesture_bar(self, fill=None):
        if fill:
            self.rect(0, 776, W, 24, fill)
        self.rect(W / 2 - 54, 787, 108, 4, ON, 2, op=0.45)

    def presence(self, state="idle", stop=True, route="Tailscale", name="PC-NHA"):
        """Global header: which PC, how it is reached, what the AI is doing. One source of truth for state."""
        col, label = {"idle": (PRIMARY, "Sẵn sàng"), "acting": (AI, "AI đang điều khiển"),
                      "locked": (AI, "Đang khoá phím/chuột"), "stopped": (STOP, "Đã dừng"),
                      "offline": (WARN, "Mất kết nối")}[state]
        tcol = {"idle": ON_VAR, "acting": AI_TEXT, "locked": AI_TEXT, "stopped": STOP_TEXT, "offline": WARN}[state]
        self.rect(16, 44, 40, 40, SC_HIGH, 12)
        self.icon("desktop_windows", 36, 64, 22, ON_VAR, filled=True)
        self.t(68, 42, name, "titleMedium", ON)
        self.text(68 + tw(name, 16, 600) + 6, 42 + 12 + 13 * 0.36, f"· {route}", 13, MUTED, 400)
        self.circle(72, 75, 4, col)
        if state == "locked":
            self.circle(72, 75, 7, "none", stroke=AI, sw=1.5, op=0.6)
        self.t(82, 65, label, "bodySmall", tcol, weight=600, maxw=146 if stop else 250)
        if stop:
            self.rect(236, 40, 108, 48, STOP, 24)
            self.icon("stop", 260, 64, 22, ON_STOP, filled=True)
            self.text(276, 64 + 15 * 0.36, "STOP", 15, ON_STOP, 700, ls=1.2)

    def nav(self, active, badge=None):
        self.rect(0, 712, W, 88, SC)
        items = [("assignment", "Việc"), ("verified_user", "Duyệt"), ("bar_chart", "Báo cáo"), ("settings", "Cài đặt")]
        for i, (ic, lab) in enumerate(items):
            cx = 45 + i * 90
            on = lab == active
            if on:
                self.rect(cx - 28, 718, 56, 32, PRIMARY_C, 16)
            self.icon(ic, cx, 734, 24, ON_PRIMARY_C if on else ON_VAR, filled=on)
            if badge and lab == "Duyệt":
                self.circle(cx + 13, 724, 8, WARN)
                self.text(cx + 13, 728, str(badge), 11, ON_WARN, 700, "middle")
            self.text(cx, 768, lab, 12, ON if on else ON_VAR, 600 if on else 500, "middle")
        self.gesture_bar()

    def edge(self, mode):
        """The signature: the phone frame glows like the PC screen edge while the AI holds the controls."""
        if mode is None:
            return
        f = self.id("glow")
        strong = mode == "locked"
        self.defs.append(f'<filter id="{f}" x="-20%" y="-20%" width="140%" height="140%">'
                         f'<feGaussianBlur stdDeviation="{10 if strong else 8}"/></filter>')
        self.add(f'<rect x="0" y="0" width="{self.w}" height="{self.h}" rx="28" fill="none" stroke="{AI}" '
                 f'stroke-width="{28 if strong else 22}" opacity="{0.42 if strong else 0.3}" filter="url(#{f})"/>')
        sw = 6 if strong else 3
        self.add(f'<rect x="{sw / 2}" y="{sw / 2}" width="{self.w - sw}" height="{self.h - sw}" rx="{28 - sw / 2}" fill="none" '
                 f'stroke="{AI}" stroke-width="{sw}"/>')

    def stepper(self, n, back=True, total=3):
        if back:
            self.icon("arrow_back", 40, 60, 24, ON)
        x0 = 72 if back else 16
        self.t(x0, 48, f"Bước {n} trên {total}", "labelMedium", ON_VAR)
        segw = (344 - x0 - 8 * (total - 1)) / total
        for i in range(total):
            self.rect(x0 + i * (segw + 8), 70, segw, 4, PRIMARY if i < n else SC_HIGHEST, 2)

    def list_group(self, x, y, w, rows, h=56):
        """Grouped list container; rows = list of callables(row_top) drawn inside. Dividers inset 56."""
        self.rect(x, y, w, h * len(rows), SC, 16)
        for i, draw in enumerate(rows):
            if i:
                self.line(x + 56, y + i * h, x + w, y + i * h)
            draw(y + i * h)
        return y + h * len(rows)

    def keycap(self, x, y, label):
        w = tw(label, 13, 500, mono=True) + 16
        self.rect(x, y, w, 28, SC_HIGHEST, 6, stroke=OUTLINE, sw=1)
        self.rect(x + 1, y + 24, w - 2, 3, SC_HIGH, 2)
        self.text(x + w / 2, y + 18.5, label, 13, ON, 500, "middle", mono=True)
        return x + w

    def code(self, x, y, w, cmd, copy=True, h=48, color=PRIMARY):
        self.rect(x, y, w, h, SC_HIGH, 12)
        self.text(x + 14, y + h / 2 + 13 * 0.36, cmd, 13, color, 500, mono=True, maxw=w - (60 if copy else 28))
        if copy:
            self.icon("content_copy", x + w - 24, y + h / 2, 20, ON_VAR)

    def render(self, fonts_inline=True):
        fonts = "".join(
            f"@font-face{{font-family:'Be Vietnam Pro';font-weight:{w};src:url('_fonts/BeVietnamPro-{n}.ttf')}}"
            for w, n in ((400, "Regular"), (500, "Medium"), (600, "SemiBold"), (700, "Bold")))
        fonts += "@font-face{font-family:'JetBrains Mono';font-weight:100 800;src:url('_fonts/JetBrainsMono.ttf')}"
        fonts = fonts if fonts_inline else ""
        clip = self.id("frame")
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" viewBox="0 0 {self.w} {self.h}">'
                f'<title>{escape(self.title)}</title><defs><style>{fonts}</style>'
                f'<clipPath id="{clip}"><rect width="{self.w}" height="{self.h}" rx="28"/></clipPath>{"".join(self.defs)}</defs>'
                f'<g clip-path="url(#{clip})"><rect width="{self.w}" height="{self.h}" fill="{BG}"/>{"".join(self.parts)}</g></svg>')
