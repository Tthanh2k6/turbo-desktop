"""UIA engine: windows, compact snapshots with stable refs and deltas, actions via patterns (real input only as
a fallback, gated by owner-idle check), OCR fallback for windows with an empty UIA tree."""
from __future__ import annotations

import csv
import io
import json
import os
import re
import shlex
import shutil
import tempfile
import subprocess
import time
import unicodedata
from pathlib import Path
from typing import Iterable

try:
    import winreg
except ImportError:  # pragma: no cover
    winreg = None  # type: ignore[assignment]

import uiautomation as auto
import win32api
import win32con
import win32gui

from . import i18n
from . import rules as rules_mod
from . import security as sec
from . import border as border_mod
from . import winsys
from .inputlock import InputLock, StateBridge

P = auto.PatternId

INTERACTIVE = {"Button", "CheckBox", "RadioButton", "Edit", "ComboBox", "ListItem", "TabItem", "MenuItem",
               "Hyperlink", "Slider", "Spinner", "TreeItem", "SplitButton", "Document", "DataItem"}
VALUE_ROLES = {"Edit", "ComboBox", "Document", "Spinner"}
TOGGLE_ROLES = {"CheckBox", "RadioButton", "MenuItem", "Button", "ListItem", "TabItem", "TreeItem", "DataItem"}
APP_ALIASES = {"vscode": "code", "edge": "msedge", "notepad": "notepad.exe", "calc": "calc.exe", "calculator": "calc.exe", "paint": "mspaint.exe",
               "explorer": "explorer.exe"}


def no_activate_startupinfo():
    """Start apps without stealing the owner's keyboard focus (SW_SHOWNOACTIVATE); apps may still ignore it."""
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 4
    return si


def _split_launch_args(args) -> list[str]:
    """Split Windows launch args preserving quoted paths with spaces and backslashes."""
    if not args:
        return []
    if isinstance(args, (list, tuple)):
        return [str(a) for a in args]
    s = str(args).strip()
    if not s:
        return []
    try:
        parts = shlex.split(s, posix=False)
    except ValueError:
        parts = s.split()
    out = []
    for tok in parts:
        if len(tok) >= 2 and tok[0] == tok[-1] and tok[0] in ('"', "'"):
            tok = tok[1:-1]
        out.append(tok)
    return out


# ---------------------------------------------------------------- Start Menu & AppsFolder resolution (pure + cached)

def fold_text(s: str) -> str:
    """Case- and Vietnamese-diacritic-insensitive normalisation (handles đ/Đ and NFD combining marks)."""
    s = (s or "").strip().lower().replace("đ", "d")
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", s).strip()


normalize_app_name = fold_text


def _clean_query(query: str) -> str:
    q = fold_text(query)
    for suf in (".exe", ".lnk"):
        if q.endswith(suf) and len(q) > len(suf):
            q = q[:-len(suf)].strip()
    return q


def start_menu_dirs() -> list[Path]:
    dirs: list[Path] = []
    for env_key in ("ProgramData", "APPDATA"):
        base = os.environ.get(env_key)
        if base:
            p = Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
            if p.exists():
                dirs.append(p)
    return dirs


def iter_start_menu_shortcuts(dirs: Iterable[Path | str] | None = None) -> list[Path]:
    roots = [Path(d) for d in dirs] if dirs is not None else start_menu_dirs()
    out: list[Path] = []
    for r in roots:
        try:
            if r.exists():
                out.extend(sorted(r.rglob("*.lnk")))
        except OSError:
            continue
    return out


def match_start_menu(query: str, shortcuts: Iterable[Path | str]) -> Path | None:
    """Match a Start Menu .lnk file by stem (case- and Vietnamese-diacritic-insensitive, exact match first then prefix)."""
    q = _clean_query(query)
    if not q:
        return None
    best: tuple[tuple[int, int, str], Path] | None = None
    for item in shortcuts:
        p = Path(item)
        if p.suffix and p.suffix.lower() != ".lnk":
            continue
        stem = p.stem
        folded = fold_text(stem)
        if not folded:
            continue
        if folded == q:
            rank = (0, len(folded), folded)
        elif folded.startswith(q):
            rank = (1, len(folded), folded)
        else:
            continue
        if best is None or rank < best[0]:
            best = (rank, p)
    return best[1] if best is not None else None


def parse_start_apps(raw: str) -> list[dict]:
    """Parse `Get-StartApps` output (JSON, CSV, or table) into [{"name": str, "app_id": str}, ...]."""
    text = (raw or "").strip()
    if not text:
        return []
    if text[0] in "[{":
        try:
            parsed = json.loads(text)
            items = [parsed] if isinstance(parsed, dict) else (parsed if isinstance(parsed, list) else [])
            out = []
            for it in items:
                if isinstance(it, dict):
                    name = str(it.get("Name") or it.get("name") or "").strip()
                    aid = str(it.get("AppID") or it.get("AppId") or it.get("app_id") or "").strip()
                    if name and aid:
                        out.append({"name": name, "app_id": aid})
            return out
        except ValueError:
            pass
    lines = [ln.strip("\r") for ln in text.splitlines() if ln.strip()]
    if lines and lines[0].lstrip().startswith('"') and "," in lines[0]:
        out = []
        for row in csv.DictReader(io.StringIO("\n".join(lines))):
            name = (row.get("Name") or row.get("name") or "").strip()
            aid = (row.get("AppID") or row.get("AppId") or row.get("app_id") or "").strip()
            if name and aid:
                out.append({"name": name, "app_id": aid})
        if out:
            return out
    out = []
    for ln in lines:
        s = ln.strip()
        if not s or re.fullmatch(r"[-\s]+", s):
            continue
        if re.match(r"^name\s+appid$", s, re.I):
            continue
        parts = re.split(r"\s{2,}", s)
        if len(parts) >= 2:
            name, aid = " ".join(parts[:-1]).strip(), parts[-1].strip()
        else:
            toks = s.rsplit(None, 1)
            if len(toks) != 2:
                continue
            name, aid = toks[0].strip(), toks[1].strip()
        if name and aid:
            out.append({"name": name, "app_id": aid})
    return out


def match_start_apps(query: str, apps: Iterable[dict | tuple]) -> dict | None:
    """Match a UWP / Start app by display name (case- and Vietnamese-diacritic-insensitive, exact first then prefix)."""
    q = _clean_query(query)
    if not q:
        return None
    best: tuple[tuple[int, int, str], dict] | None = None
    for item in apps:
        if isinstance(item, (tuple, list)) and len(item) >= 2:
            name, aid = str(item[0]).strip(), str(item[1]).strip()
        elif isinstance(item, dict):
            name = str(item.get("name") or item.get("Name") or "").strip()
            aid = str(item.get("app_id") or item.get("AppID") or item.get("AppId") or "").strip()
        else:
            continue
        if not name or not aid:
            continue
        folded = fold_text(name)
        if not folded:
            continue
        if folded == q:
            rank = (0, len(folded), folded)
        elif folded.startswith(q):
            rank = (1, len(folded), folded)
        else:
            continue
        entry = {"name": name, "app_id": aid}
        if best is None or rank < best[0]:
            best = (rank, entry)
    return best[1] if best is not None else None


_START_APPS_CACHE: dict = {"at": None, "apps": []}


def _run_get_start_apps() -> str:
    r = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", "Get-StartApps | ConvertTo-Json -Compress"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10,
        startupinfo=no_activate_startupinfo(),
    )
    return r.stdout or ""


def list_start_apps(now=time.monotonic, runner=None, ttl: float = 600.0, force_refresh: bool = False) -> list[dict]:
    """Enumerate Start/UWP apps via Get-StartApps once and cache for `ttl` seconds (default 10 min)."""
    t = float(now())
    if not force_refresh and _START_APPS_CACHE["at"] is not None and (t - _START_APPS_CACHE["at"]) < ttl:
        return list(_START_APPS_CACHE["apps"])
    fn = runner or _run_get_start_apps
    try:
        raw = fn()
        apps = parse_start_apps(raw) if isinstance(raw, str) else list(raw)
    except Exception:
        apps = []
    _START_APPS_CACHE["at"] = t
    _START_APPS_CACHE["apps"] = apps
    return list(apps)


def find_app_path(name: str) -> str | None:
    """Look up `name` in Windows Registry App Paths (HKCU then HKLM)."""
    if winreg is None or not name:
        return None
    key_name = name if name.lower().endswith(".exe") else f"{name}.exe"
    subkey = rf"Software\Microsoft\Windows\CurrentVersion\App Paths\{key_name}"
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root, subkey) as k:
                val, _ = winreg.QueryValueEx(k, "")
                if val:
                    p = os.path.expandvars(str(val).strip().strip('"'))
                    if Path(p).is_file():
                        return p
        except OSError:
            continue
    return None


def resolve_launch_target(target: str, *, which_fn=shutil.which, app_paths_fn=find_app_path,
                          shortcuts: Iterable[Path | str] | None = None,
                          start_apps: Iterable[dict | tuple] | None = None) -> dict | None:
    """Resolve `target` in order:
      1. explicit path / PATH executable / Registry App Paths -> {"how": "path", "matched": <name>, "path": <path>}
      2. Start Menu .lnk (exact then prefix, diacritic-insensitive) -> {"how": "start-menu", "matched": <stem>, "shortcut": <lnk>, "path": <lnk>}
      3. UWP shell:AppsFolder -> {"how": "appsfolder", "matched": <name>, "appId": <id>, "path": "shell:AppsFolder\\<id>"}
    """
    raw = (target or "").strip()
    if not raw:
        return None
    if raw.lower().startswith("shell:appsfolder\\"):
        aid = raw.split("\\", 1)[1]
        return {"how": "appsfolder", "matched": aid, "appId": aid, "path": raw}
    t = APP_ALIASES.get(raw.lower(), raw)
    if os.path.isabs(t) or os.sep in t or "/" in t:
        return {"how": "path", "matched": Path(t).name or t, "path": t}
    if which_fn is not None:
        w = which_fn(t)
        if w:
            return {"how": "path", "matched": Path(w).name or w, "path": w}
    if app_paths_fn is not None:
        ap = app_paths_fn(t)
        if ap:
            return {"how": "path", "matched": Path(ap).name or ap, "path": ap}
    lnks = iter_start_menu_shortcuts() if shortcuts is None else shortcuts
    lnk = match_start_menu(raw, lnks)
    if lnk is not None:
        return {"how": "start-menu", "matched": lnk.stem, "shortcut": str(lnk), "path": str(lnk)}
    apps = list_start_apps() if start_apps is None else start_apps
    app = match_start_apps(raw, apps)
    if app is not None:
        return {
            "how": "appsfolder",
            "matched": app["name"],
            "appId": app["app_id"],
            "path": f"shell:AppsFolder\\{app['app_id']}",
        }
    return None


_NAMED_KEYS = {"enter": "Enter", "return": "Enter", "esc": "Esc", "escape": "Esc", "tab": "Tab", "delete": "Delete", "del": "Delete",
               "backspace": "Backspace", "home": "Home", "end": "End", "up": "Up", "down": "Down", "left": "Left", "right": "Right",
               "apps": "Apps", "menu": "Apps", "pageup": "PageUp", "pagedown": "PageDown", "space": "Space", "insert": "Insert"}


def normalize_keys(keys: str) -> tuple[str, bool]:
    """Accept what models write and turn it into uiautomation SendKeys syntax:
    {{Esc}} -> {Esc};  Ctrl+Shift+N -> {Ctrl}{Shift}n;  Enter -> {Enter};  F2 -> {F2}.  Plain text is left alone."""
    k = keys or ""
    new = re.sub(r"\{\{(\w+)\}\}", lambda m: "{" + m.group(1) + "}", k)
    m = re.fullmatch(r"((?:ctrl|control|alt|shift|win)\+)+(\S+)", new.strip(), re.I)
    if m and "{" not in new:
        parts = new.strip().split("+")
        mods = "".join("{" + {"control": "Ctrl"}.get(p.lower(), p.capitalize()) + "}" for p in parts[:-1])
        last = parts[-1]
        low = last.lower()
        if low in _NAMED_KEYS:
            last = "{" + _NAMED_KEYS[low] + "}"
        elif re.fullmatch(r"f\d{1,2}", low):
            last = "{" + last.upper() + "}"
        else:
            last = last.lower() if len(last) == 1 else last
        new = mods + last
    elif "{" not in new:
        low = new.strip().lower()
        if low in _NAMED_KEYS:
            new = "{" + _NAMED_KEYS[low] + "}"
        elif re.fullmatch(r"f\d{1,2}", low):
            new = "{" + new.strip().upper() + "}"
    return new, new != k


class ToolError(Exception):
    def __init__(self, msg, **extra):
        super().__init__(msg)
        self.extra = extra


class OwnerBusy(ToolError):
    pass


def _clip(s, n):
    s = (s or "").replace("\r\n", "\\n").replace("\r", "\\n").replace("\n", "\\n")  # show line breaks, do not hide them
    return s if len(s) <= n else s[: n - 1] + "…"


def role_of(c) -> str:
    n = c.ControlTypeName or ""
    return n[:-7] if n.endswith("Control") else n


def no_input() -> bool:
    return os.environ.get("TURBO_DESKTOP_NO_INPUT") == "1"


DEFAULT_WINDOW_TIMEOUT = 4.0


def window_timeout() -> float:
    """Per-window UIA timeout in seconds (TURBO_DESKTOP_WINDOW_TIMEOUT, default 4.0s)."""
    raw = os.environ.get("TURBO_DESKTOP_WINDOW_TIMEOUT")
    if raw is None or not str(raw).strip():
        return DEFAULT_WINDOW_TIMEOUT
    try:
        return max(0.05, float(raw))
    except (TypeError, ValueError):
        return DEFAULT_WINDOW_TIMEOUT


def normalize_settle_ms(settle_ms: int | float | None) -> int:
    """Normalise settleMs: 0 (disabled) by default; positive values are clamped to 100..1000 ms."""
    if settle_ms is None or isinstance(settle_ms, bool):
        return 0
    try:
        ms = int(round(float(settle_ms)))
    except (TypeError, ValueError):
        raise ToolError(f"invalid settleMs {settle_ms!r} (expected 0 or 100..1000)")
    if ms <= 0:
        return 0
    return max(100, min(1000, ms))


def _parse_region_spec(region, param_name: str = "region") -> tuple[int, int, int, int] | None:
    """Validate `[x, y, w, h]` region spec (relative to window origin). Raises ToolError on invalid format or w/h <= 0."""
    if region is None:
        return None
    if not isinstance(region, (list, tuple)) or len(region) != 4:
        raise ToolError(f"invalid {param_name} {region!r} (expected [x, y, w, h])")
    vals: list[int] = []
    for v in region:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ToolError(f"invalid {param_name} {region!r} (expected 4 numbers [x, y, w, h])")
        vals.append(int(round(float(v))))
    x, y, w, h = vals
    if w <= 0 or h <= 0:
        raise ToolError(f"invalid {param_name} {region!r}: width and height must be > 0")
    return x, y, w, h


def _crop_region(img, region, param_name: str = "region"):
    """Crop `img` to `region=[x, y, w, h]` clamped to image bounds; return `(cropped_img, x1, y1)`."""
    parsed = _parse_region_spec(region, param_name)
    if parsed is None:
        return img, 0, 0
    x, y, w, h = parsed
    img_w, img_h = int(img.width), int(img.height)
    x1 = max(0, min(x, img_w))
    y1 = max(0, min(y, img_h))
    x2 = max(0, min(x + w, img_w))
    y2 = max(0, min(y + h, img_h))
    if x2 <= x1 or y2 <= y1:
        raise ToolError(
            f"invalid {param_name} {list(parsed)!r}: region lies outside window bounds ({img_w}x{img_h})"
        )
    return img.crop((x1, y1, x2, y2)), x1, y1


def _normalize_max_width(max_width: int | float | None) -> int:
    """Validate screenshot `maxWidth` (default 1280, must be > 0)."""
    if max_width is None:
        return 1280
    if isinstance(max_width, bool) or not isinstance(max_width, (int, float)):
        raise ToolError(f"invalid maxWidth {max_width!r}: must be a positive integer")
    mw = int(round(float(max_width)))
    if mw <= 0:
        raise ToolError(f"invalid maxWidth {max_width!r}: must be > 0")
    return mw


class Win:
    """Per-window state: ref registry and last snapshot (for deltas)."""

    def __init__(self, wid, hwnd):
        self.wid = wid
        self.hwnd = hwnd
        self.keys: dict = {}       # element key -> n
        self.refs: dict = {}       # n -> Control
        self.meta: dict = {}       # n -> dict(role,name,aid,...)
        self.next = 1
        self.prev: dict = {}  # ref -> signature
        self.ocr: dict = {}        # n -> (screen_x, screen_y, text)
        self.ocr_next = 1


class Desktop:
    def __init__(self, audit: sec.AuditLog | None = None, idle_fn=None, sleep_fn=time.sleep):
        self.audit = audit or sec.AuditLog()
        self.wins: dict[int, Win] = {}
        self.by_wid: dict[str, Win] = {}
        self.n_wid = 0
        self.launched: set[int] = set()
        self.idle_fn = idle_fn or winsys.idle_seconds
        self.sleep = sleep_fn
        self._own_input_at = 0.0
        self._pending_invokes: dict = {}
        self._note: dict = {}
        self.indicator = border_mod.Indicator(disabled_by_env=os.environ.get("TURBO_DESKTOP_NO_INDICATOR") == "1")
        self.lock = InputLock(indicator=self.indicator)
        self.bridge = StateBridge(
            self.lock,
            self.indicator,
            allow_windows=(os.environ.get("TURBO_DESKTOP_NO_INDICATOR") != "1" and not no_input()),
        )
        if sec.bridge_dir() is not None:
            self.bridge.start()

    # ------------------------------------------------------------ windows

    def _win(self, hwnd) -> Win:
        w = self.wins.get(hwnd)
        if not w:
            self.n_wid += 1
            w = Win(f"w{self.n_wid}", hwnd)
            self.wins[hwnd] = w
            self.by_wid[w.wid] = w
        return w

    def _own_hwnds(self) -> set[int]:
        out: set[int] = set()
        try:
            out.update(getattr(self.indicator.glow, "hwnds", ()) or ())
        except Exception:
            pass
        for attr in ("banner_hwnd", "ctrl_hwnd"):
            h = getattr(self.lock, attr, 0)
            if h:
                out.add(h)
        return out

    def windows_list(self, include_denied=True, hidden: bool = False, verbose: bool = True) -> list[dict]:
        fg = win32gui.GetForegroundWindow()
        own = self._own_hwnds()
        try:
            raw = winsys.enum_top_windows(hidden=hidden)
        except TypeError:
            raw = winsys.enum_top_windows()
        out = []
        for t in raw:
            if not hidden and winsys.is_irrelevant_window(t, own):
                continue
            name, el = winsys.process_info(t["pid"])
            if rules_mod.is_excluded_process(name):
                continue
            w = self._win(t["hwnd"])
            deny = sec.is_denied_window(name, t["title"], t.get("class"))
            secret = sec.secret_reason(t["title"], name)
            if not include_denied and (deny or secret):
                continue
            d = {"id": w.wid, "title": sec.HIDDEN_TITLE if secret else t["title"], "process": name,
                 "focused": t["hwnd"] == fg}
            if t.get("class"):
                d["class"] = t["class"]
            if verbose:
                d["hwnd"] = t["hwnd"]
                d["pid"] = t["pid"]
            if secret:
                d["secret"] = True            # the matched pattern is not shown: it would hint at what the title was
                d["rule"] = "secret-window"
                deny = "secret-window"
            if el and not winsys.we_are_admin():
                d["elevated"] = True
                d["actionable"] = False
            if deny:
                d["denied"] = deny
            out.append(d)
        return out

    def format_windows_list(self, verbose: bool = False, hidden: bool = False) -> str:
        """Compact line format: `w3 Calculator [CalculatorApp] *focused`.
        Drops hwnd and pid unless verbose=True; skips tool-irrelevant windows unless hidden=True;
        keeps denied, secret and elevated markers."""
        rows = self.windows_list(hidden=hidden, verbose=True)
        own = self._own_hwnds()
        lines = []
        for d in rows:
            if not hidden and winsys.is_irrelevant_window(d, own):
                continue
            parts = [f"{d['id']} {d['title']} [{d['process']}]"]
            if verbose:
                parts.append(f"pid={d.get('pid')} hwnd={d.get('hwnd')}")
            if d.get("focused"):
                parts.append("*focused")
            if d.get("secret"):
                parts.append("[secret]")
            if d.get("denied"):
                parts.append(f"[denied: {d['denied']}]")
            if d.get("elevated"):
                parts.append("[elevated]")
            lines.append(" ".join(parts))
        return "\n".join(lines)

    def find_window(self, spec) -> dict:
        """spec: 'w3' | hwnd int | title substring | 'process:notepad'."""
        spec_s = str(spec)
        wl = self.windows_list()
        for d in wl:
            if d["id"] == spec_s or str(d["hwnd"]) == spec_s:
                return d
        low = spec_s.lower()
        if low.startswith("process:"):
            m = [d for d in wl if d["process"].lower() == low[8:]]
        else:
            m = [d for d in wl if low in d["title"].lower()]
        if not m:
            raise ToolError(f"no window matches '{spec_s}'")
        return m[0]

    def _guard_window(self, d: dict, action: str, uia: bool = True):
        if sec.stop_requested():
            self.indicator.hide_now()
            raise ToolError(i18n.msg("stop_active_error"), stopped=True)
        if rules_mod.is_excluded_process(d.get("process")):
            raise ToolError(f"process '{d.get('process')}' is excluded by exclude_processes config",
                            excluded=True, process=d.get("process"))
        t = self._pending_invokes.get(d.get("pid")) if uia and action != "close" else None
        if t is not None:
            if t.is_alive():
                # field bug 10: while an Invoke is still pending (its handler opened a modal dialog), every UIA call into
                # that app blocks until the dialog closes. Say so at once instead of hanging.
                raise ToolError("this app is inside a modal dialog opened by a pending Invoke; UI Automation calls to it "
                                "block until it closes. Find the dialog with windows_list and close it "
                                "(window_control close, or press_keys {Esc} on the dialog); use the keyboard accelerator "
                                "instead of Invoke for menu items that open dialogs.", blocked=True)
            self._pending_invokes.pop(d.get("pid"), None)
        if d.get("secret"):
            self.audit.write(event="denied", window=d["title"], process=d["process"], action=action, rule="secret-window")
            raise ToolError(i18n.msg("secret_window_error"), denied="secret-window", rule="secret-window")
        if d.get("denied"):
            self.audit.write(event="denied", window=d["title"], process=d["process"], action=action, reason=d["denied"])
            raise ToolError(d["denied"], denied=True)
        if d.get("elevated") and action != "inspect":
            raise ToolError(i18n.msg("elevated_window_error"),
                            elevated=True, actionable=False)

    # ------------------------------------------------------------ snapshot

    def _ctrl_for(self, d):
        if not win32gui.IsWindow(d["hwnd"]):
            return None
        return auto.ControlFromHandle(d["hwnd"])

    def _facts(self, c, role, mode_all=False):
        """Gather name/value/state for one element."""
        name = c.Name or ""
        aid = c.AutomationId or ""
        pw = False
        try:
            pw = bool(c.GetPropertyValue(auto.PropertyId.IsPasswordProperty))
        except Exception:
            pass
        value = None
        flags = []
        if not c.IsEnabled:
            flags.append("disabled")
        if c.IsOffscreen:
            flags.append("offscreen")
        if pw:
            flags.append("password:protected")
        elif role in VALUE_ROLES or role == "Slider":
            try:
                vp = c.GetPattern(P.ValuePattern)
                if vp:
                    value = vp.Value
                    if vp.IsReadOnly:
                        flags.append("readonly")
                elif role == "Slider":
                    rv = c.GetPattern(P.RangeValuePattern)
                    value = str(rv.Value) if rv else None
            except Exception:
                pass
        if role in TOGGLE_ROLES:
            try:
                tp = c.GetPattern(P.TogglePattern)
                if tp:
                    st = tp.ToggleState
                    flags.append({0: "unchecked", 1: "checked", 2: "mixed"}.get(st, "?"))
                else:
                    sp = c.GetPattern(P.SelectionItemPattern)
                    if sp and sp.IsSelected:
                        flags.append("selected")
            except Exception:
                pass
        if role in ("ComboBox", "MenuItem", "TreeItem", "SplitButton"):
            try:
                ec = c.GetPattern(P.ExpandCollapsePattern)
                if ec and ec.ExpandCollapseState == 1:
                    flags.append("expanded")
            except Exception:
                pass
        return name, aid, value, flags, pw

    def inspect(self, window, mode="interactive", query=None, only_changed=False, max_chars=6000,
                max_nodes=700, ocr=None, onlyChanged: bool | None = None, maxChars: int | None = None,
                ocr_region: list[int] | tuple[int, ...] | None = None,
                ocrRegion: list[int] | tuple[int, ...] | None = None) -> str:
        if onlyChanged is not None:
            only_changed = bool(onlyChanged)
        if maxChars is not None:
            max_chars = int(maxChars)
        if ocrRegion is not None:
            ocr_region = ocrRegion
        parsed_ocr_region = _parse_region_spec(ocr_region, "ocrRegion")
        d = self.find_window(window)
        self._guard_window(d, "inspect")
        w = self._win(d["hwnd"])
        w_title = fold_text(d.get("title") or "")
        win_limit = window_timeout()
        walk_deadline = time.monotonic() + win_limit
        timed_out = False
        root = self._ctrl_for(d)
        if time.monotonic() >= walk_deadline:
            timed_out = True
        elements: list[tuple[int, str, object, str, tuple]] = []  # (n, line-without-ref, parent_key, role, anc_keys)
        sigs: dict[int, str] = {}
        all_sigs: dict[int, str] = {}
        skipped_off = 0
        count = 0
        q = (query or "").lower()
        seen_keys = set()

        def key_for(c, parent_key, idx):
            try:
                rid = c.GetRuntimeId()
            except Exception:
                rid = None
            if rid and len(rid) > 1:
                return ("rid", tuple(rid))
            return ("path", parent_key, c.ControlTypeName, c.Name, c.AutomationId, idx)

        def walk(c, depth, parent_key, in_titlebar, anc_keys=()):
            nonlocal skipped_off, count, timed_out
            if c is None or timed_out:
                return
            if time.monotonic() >= walk_deadline:
                timed_out = True
                return
            try:
                kids = c.GetChildren()
            except Exception:
                return
            if time.monotonic() >= walk_deadline:
                timed_out = True
                return
            idxs: dict = {}
            for ch in kids:
                if count >= max_nodes or timed_out:
                    return
                if time.monotonic() >= walk_deadline:
                    timed_out = True
                    return
                try:
                    role = role_of(ch)
                    tb = in_titlebar or role == "TitleBar"
                    ident = (role, ch.Name)
                    idx = idxs[ident] = idxs.get(ident, -1) + 1
                    key = key_for(ch, parent_key, idx)
                    cur_anc = anc_keys + (key,)
                    show = (mode == "all" and not tb) or (role in INTERACTIVE and not tb) or \
                           (mode == "text" and role == "Text" and not tb)
                    if mode == "all" and tb and role in ("Button",):
                        show = False
                    if show and role == "Button" and not tb and _is_caption_button(ch, w_title, q):
                        show = False
                    if show:
                        name, aid, value, flags, pw = self._facts(ch, role)
                        if "offscreen" in flags and mode != "all":
                            skipped_off += 1
                            show = False
                        elif mode == "all" and not (name or value or aid or role in INTERACTIVE):
                            show = False
                    if show:
                        n = w.keys.get(key)
                        if n is None:
                            n = w.next
                            w.next += 1
                            w.keys[key] = n
                        w.refs[n] = ch
                        w.meta[n] = {"role": role, "name": name, "aid": aid, "pw": pw}
                        seen_keys.add(n)
                        line = f"<{role}> "
                        if name:
                            line += f'"{_clip(name, 60)}"'
                        elif aid and not aid.isdigit():
                            line += f"#{_clip(aid, 30)}"
                        if value not in (None, ""):
                            line += f' = "{_clip(value, 80)}"'
                        elif role in VALUE_ROLES and not pw and value == "":
                            line += ' = ""'
                        if flags:
                            line += " " + " ".join(f"[{f}]" for f in flags)
                        all_sigs[n] = line
                        if not q or q in line.lower() or q in (aid or "").lower():
                            elements.append((n, line, parent_key, role, cur_anc))
                            sigs[n] = line
                            count += 1
                    walk(ch, depth + 1, key, tb, cur_anc)
                except Exception:
                    continue

        walk(root, 0, None, False)
        if timed_out and not seen_keys and not elements:
            raise ToolError(
                f"UI Automation on window '{d['title']}' ({d['process']}) timed out after {win_limit:.1f}s",
                hung=True,
                timeout=win_limit,
                window=w.wid,
                process=d["process"],
            )
        elapsed_note = ""
        tree_empty = (not seen_keys) or (len(seen_keys) <= 1 and mode != "all")
        ocr_lines = []
        want_ocr = (tree_empty or ocr is True or parsed_ocr_region is not None) and not timed_out and ocr is not False
        if want_ocr and (win32gui.IsWindow(d["hwnd"]) or ocr is True or parsed_ocr_region is not None):
            try:
                ocr_lines = self._ocr_window(w, d, ocr_region=parsed_ocr_region)
            except ToolError:
                raise
            except Exception as e:
                elapsed_note = f" ocr-unavailable: {_clip(str(e), 80)}"

        head = f'window {w.wid} "{_clip(d["title"], 60)}" ({d["process"]} pid {d.get("pid", "?")})'
        if d.get("focused"):
            head += " focused"
        if d.get("elevated"):
            head += " ELEVATED actionable=false"
        lines = []
        removed = []
        prev = w.prev.get(mode)
        if only_changed and prev is not None:
            for n, line, _, _, _ in elements:
                old = prev.get(n)
                if old is None:
                    lines.append(f"*[{w.wid}:e{n}] {line}")
                elif old != line:
                    lines.append(f"~[{w.wid}:e{n}] {line}")
            if not q:
                removed = [n for n in prev if n not in sigs]
                for n in removed:
                    lines.append(f"-[{w.wid}:e{n}] removed")
            unchanged = len(sigs) - sum(1 for l in lines if l[0] in "*~")
            foot = f"-- delta: {sum(1 for l in lines if l[0]=='*')} new, {sum(1 for l in lines if l[0]=='~')} changed, {len(removed)} removed, {max(unchanged, 0)} unchanged"
        else:
            lines = [f"[{w.wid}:e{n}] {line}" for n, line, _, _, _ in elements]
            foot = f"-- {len(elements)} elements"
        if not q:
            w.prev[mode] = dict(sigs)
        elif mode not in w.prev:
            w.prev[mode] = dict(all_sigs)
        if skipped_off:
            foot += f", {skipped_off} offscreen hidden"
        if count >= max_nodes:
            foot += ", TRUNCATED (max_nodes)"
        if timed_out:
            foot += f", TRUNCATED (window_timeout {win_limit:.1f}s)"
        if tree_empty:
            foot += ", treeEmpty: true"
            if ocr_lines:
                foot += ', via: "ocr"'
        elif ocr_lines:
            foot += ', via: "ocr"'
        for ol in ocr_lines:
            lines.append(ol)
        body = "\n".join(lines)
        if len(body) > max_chars:
            if not only_changed and elements:
                summarised = _summarise_siblings(elements, w.wid, first_n=8)
                if len(summarised) < len(elements):
                    lines = summarised + list(ocr_lines)
                    body = "\n".join(lines)
            if len(body) > max_chars:
                # Preserve any sibling summary lines ("... (first 8 shown; use query= to filter)") if still over max_chars
                sum_lines = [ln for ln in lines if "shown; use query= to filter)" in ln]
                body = body[:max_chars] + f"\n... truncated at {max_chars} chars (use query= to filter)"
                for sl in sum_lines:
                    if sl not in body:
                        body += "\n" + sl
        return sec.wrap_untrusted(f"{head}\n{body}\n{foot}{elapsed_note}", label=w.wid + " ")

    def _ocr_window(self, w: Win, d: dict, ocr_region=None) -> list[str]:
        img, (ox, oy) = winsys.capture_window(d["hwnd"])
        self._blackout_passwords(img, d, ox, oy)
        if ocr_region is not None:
            img, rx, ry = _crop_region(img, ocr_region, "ocrRegion")
            ox += rx
            oy += ry
        res = winsys.ocr_image(img)
        w.ocr.clear()
        w.ocr_next = 1
        out = []
        for r in res:
            n = w.ocr_next
            w.ocr_next += 1
            cx, cy = ox + r["x"] + r["w"] // 2, oy + r["y"] + r["h"] // 2
            w.ocr[n] = (cx, cy, r["text"])
            out.append(f'[{w.wid}:o{n}] text "{_clip(r["text"], 60)}" @{cx},{cy}')
        return out

    # ------------------------------------------------------------ resolving targets

    def _parse_ref(self, ref: str, window=None):
        if not ref or not isinstance(ref, str):
            raise ToolError(f"bad ref '{ref}' (expected like w1:e12)")
        s = ref.strip()
        if s.startswith("[") and s.endswith("]"):
            s = s[1:-1].strip()
        m = re.fullmatch(r"(?:(w\d+):)?([eo])(\d+)", s)
        if not m:
            raise ToolError(f"bad ref '{ref}' (expected like w1:e12)")
        wid, kind, n = m.group(1), m.group(2), int(m.group(3))
        if not wid:
            if window is None:
                raise ToolError("ref without window id needs window=")
            wid = self.find_window(window)["id"]
        w = self.by_wid.get(wid)
        if not w:
            raise ToolError(f"unknown window id {wid}; call windows_list")
        return w, kind, n

    def _alive(self, c) -> bool:
        try:
            c.Name  # noqa: B018
            return True
        except Exception:
            return False

    def _find_by_name(self, d, name, role=None):
        """Best match by name/AutomationId: exact beats substring, interactive roles beat labels,
        on-screen beats off-screen (menu items are often reported off-screen until opened)."""
        root = self._ctrl_for(d)
        low = name.lower()
        best, best_score = None, -1
        queue = [root]
        n = 0
        while queue and n < 1500:
            c = queue.pop(0)
            try:
                kids = c.GetChildren()
            except Exception:
                continue
            for ch in kids:
                n += 1
                queue.append(ch)
                try:
                    r = role_of(ch)
                    if role and r.lower() != role.lower():
                        continue
                    nm = (ch.Name or "")
                    aid = ch.AutomationId or ""
                    exact = nm.lower() == low or aid.lower() == low
                    if not exact and low not in nm.lower():
                        continue
                    score = (4 if exact else 0) + (2 if r in INTERACTIVE else 0) + (1 if not ch.IsOffscreen else 0)
                    if not exact and r not in INTERACTIVE:
                        continue
                    if score > best_score:
                        best, best_score = ch, score
                        if score == 7:
                            return ch
                except Exception:
                    pass
        return best

    def resolve(self, d, ref=None, name=None, role=None):
        w = self._win(d["hwnd"])
        if ref:
            w2, kind, n = self._parse_ref(ref, d["id"])
            if kind == "o":
                if n not in w2.ocr:
                    raise ToolError(f"stale OCR ref {ref}; inspect again")
                return w2, None, ("ocr", n)
            c = w2.refs.get(n)
            if c is None:
                raise ToolError(f"unknown ref {ref}; inspect first")
            if not self._alive(c):
                raise ToolError(f"stale ref {ref} (element gone); inspect again", stale=True)
            return w2, c, None
        if name:
            c = self._find_by_name(d, name, role)
            if c is None:
                raise ToolError(f"no element named '{name}'" + (f" role {role}" if role else ""))
            return w, c, None
        raise ToolError("need ref or name")

    # ------------------------------------------------------------ real input guard

    def wait_owner_idle(self):
        """Do not fight the owner for the mouse/keyboard. Waits up to TURBO_DESKTOP_IDLE_WAIT (10 s) until the owner
        has been idle for TURBO_DESKTOP_IDLE_SECONDS (5 s); otherwise fail."""
        need = float(os.environ.get("TURBO_DESKTOP_IDLE_SECONDS", "5"))
        wait = float(os.environ.get("TURBO_DESKTOP_IDLE_WAIT", "10"))
        end = time.time() + wait
        while True:
            idle = self.idle_fn()
            # input we injected ourselves resets the idle timer too; ignore for a short window after our own input
            if idle >= need or (time.time() - self._own_input_at) < idle:
                return
            if time.time() >= end:
                raise OwnerBusy(i18n.msg("owner_busy_error", idle=idle), ownerBusy=True)
            self.sleep(0.25)

    def real_input(self, fn):
        """Run fn() as real input: idle gate, input lock (owner's keyboard/mouse paused + banner), then restore the
        previous foreground window and cursor. Raises owner_took_over if the owner pressed Esc x3 meanwhile."""
        if no_input():
            raise ToolError("real input disabled (TURBO_DESKTOP_NO_INPUT=1) and no UIA pattern available")
        if not (self.lock.locked and getattr(self.lock, "remote_task", False)):
            self.wait_owner_idle()
        cfg = rules_mod.load_ruleset().input_lock
        use_lock = cfg["mode"] in ("real_input", "whole_task") and os.environ.get("TURBO_DESKTOP_INPUT_LOCK", "1") != "0"
        prev_fg = win32gui.GetForegroundWindow()
        try:
            prev_pos = win32api.GetCursorPos()
        except Exception:
            prev_pos = None
        self.indicator.real_input(True)     # hard floor: the frame shows while real input is sent, whatever [indicator] says
        if use_lock:
            self.bridge.check_release()
            self.lock.acquire(cfg["max_seconds"], whole_task=(cfg["mode"] == "whole_task"))
            self.indicator.locked(True)
            self.audit.write(event="input_lock", state="on", mode=cfg["mode"])
        try:
            return fn()
        finally:
            self._own_input_at = time.time()
            try:
                if prev_pos is not None:
                    win32api.SetCursorPos(prev_pos)
                if prev_fg and prev_fg != win32gui.GetForegroundWindow() and win32gui.IsWindow(prev_fg):
                    win32gui.SetForegroundWindow(prev_fg)
            except Exception:
                pass
            self.indicator.real_input(False)
            if use_lock:
                info = self.lock.end_one()
                self.lock.touch()
                self.indicator.locked(bool(info["locked"]))
                if info["owner_took_over"] or info["stopped"]:
                    self.indicator.hide_now()
                self.audit.write(event="input_lock", state="off" if not info["locked"] else "held", **info)
                if info["owner_took_over"] or info["stopped"]:
                    raise ToolError(i18n.msg("takeover_error") if info["owner_took_over"]
                                    else i18n.msg("stop_hotkey_error"),
                                    owner_took_over=bool(info["owner_took_over"]), stopped=bool(info["stopped"]))

    def _ind_activity(self):
        """Edge glow: any act / batch / launch / window_control (not read-only calls)."""
        try:
            ind = rules_mod.load_ruleset().indicator
            self.indicator.configure(ind["border"], ind["color"])
            self.indicator.activity()
        except Exception:
            pass

    def bring_front(self, hwnd) -> bool:
        """Make `hwnd` the foreground window before real input (a click lands on whatever is on top, keys go to the
        foreground window). Returns True only when it really is in front afterwards."""
        try:
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            if win32gui.GetForegroundWindow() != hwnd:
                win32api.keybd_event(0x12, 0, 0, 0)       # a tap of Alt lets SetForegroundWindow through
                win32api.keybd_event(0x12, 0, 2, 0)
                win32gui.SetForegroundWindow(hwnd)
            for _ in range(10):
                if win32gui.GetForegroundWindow() == hwnd:
                    return True
                time.sleep(0.05)
        except Exception:
            pass
        return win32gui.GetForegroundWindow() == hwnd

    def _front_or_fail(self, d):
        before = win32gui.GetForegroundWindow()
        if before != d["hwnd"]:
            try:
                self._note["focus"] = f"the window was not in front (front was '{win32gui.GetWindowText(before)[:50]}'); brought it to the front first"
            except Exception:
                self._note["focus"] = "the window was not in front; brought it to the front first"
        if not self.bring_front(d["hwnd"]):
            raise ToolError(f"window '{d['title']}' could not be brought to the front; no input was sent "
                            f"(another window kept the focus)", focus_lost=True)

    # ------------------------------------------------------------ acting

    def _describe(self, d, c):
        name = ""
        role = ""
        aid = ""
        help_text = ""
        multiline = False
        pw = False
        try:
            name = c.Name or ""
            role = role_of(c)
            aid = c.AutomationId or ""
            help_text = c.HelpText or ""
            pw = bool(c.GetPropertyValue(auto.PropertyId.IsPasswordProperty))
            if role in ("Document",):
                multiline = True
            elif role == "Edit":
                try:
                    multiline = bool(c.GetPropertyValue(auto.PropertyId.IsMultipleViewPatternAvailableProperty)) or \
                        "multi" in (c.ClassName or "").lower() or "richedit" in (c.ClassName or "").lower()
                except Exception:
                    pass
        except Exception:
            pass
        return {"name": name, "role": role, "automation_id": aid, "help_text": help_text,
                "multiline": multiline, "is_password": pw}

    def _dialog_title(self, c):
        try:
            p = c.GetParentControl()
            while p:
                if role_of(p) == "Window":
                    return p.Name
                p = p.GetParentControl()
        except Exception:
            pass
        return None

    def _tree_probe(self, d: dict) -> tuple:
        """Fast lightweight signature of a window's UIA tree and process dialogs for settle checks."""
        pid = d.get("pid")
        if pid and pid in self._pending_invokes and self._pending_invokes[pid].is_alive():
            return ("pending",)
        win_sigs = []
        try:
            for row in winsys.enum_top_windows(hidden=False):
                if pid and row.get("pid") == pid:
                    win_sigs.append((row.get("hwnd"), row.get("title", "")))
        except Exception:
            pass
        node_sigs = []
        deadline = time.monotonic() + min(0.5, window_timeout())
        root = self._ctrl_for(d)
        if root is not None:
            queue = [root]
            while queue and len(node_sigs) < 120 and time.monotonic() < deadline:
                c = queue.pop(0)
                try:
                    kids = c.GetChildren()
                except Exception:
                    continue
                for ch in kids:
                    if len(node_sigs) >= 120 or time.monotonic() >= deadline:
                        break
                    try:
                        role = role_of(ch)
                        name, aid, value, flags, _ = self._facts(ch, role)
                        node_sigs.append((role, name, aid, value, tuple(flags)))
                        queue.append(ch)
                    except Exception:
                        continue
        return (tuple(win_sigs), tuple(node_sigs))

    def _settle_uia(self, d: dict, settle_ms: int) -> int:
        """Wait until the window's UIA tree stops changing for `settle_ms` (100..1000 ms), up to 2x budget."""
        ms = normalize_settle_ms(settle_ms)
        if ms <= 0:
            return 0
        target_s = ms / 1000.0
        max_s = min(2.0, target_s * 2.0)
        step_s = min(0.05, target_s / 2.0)
        prev_sig = self._tree_probe(d)
        quiet_s = 0.0
        total_s = 0.0
        while quiet_s + 1e-9 < target_s and total_s + 1e-9 < max_s:
            if sec.stop_requested():
                break
            sleep_dur = min(step_s, max_s - total_s)
            self.sleep(sleep_dur)
            total_s += sleep_dur
            cur_sig = self._tree_probe(d)
            if cur_sig != prev_sig:
                prev_sig = cur_sig
                quiet_s = 0.0
            else:
                quiet_s += sleep_dur
        return int(round(total_s * 1000))

    def act(self, window=None, action="click", ref=None, name=None, role=None, text=None, value=None, keys=None,
            direction=None, amount=1, return_snapshot: bool = False, returnSnapshot: bool | None = None,
            settle_ms: int = 0, settleMs: int | None = None):
        if returnSnapshot is not None:
            return_snapshot = bool(returnSnapshot)
        if settleMs is not None:
            settle_ms = settleMs
        eff_settle = normalize_settle_ms(settle_ms)
        self.bridge.check_release()
        self._ind_activity()
        self._note = {}
        if not window and not ref:
            raise ToolError("need window= or a ref like w1:e12")
        d = self.find_window(window) if window else self.find_window(self._parse_ref(ref)[0].wid)
        self._guard_window(d, action, uia=not (action in ("press_keys", "send_text") and not ref and not name))
        if action in ("press_keys", "send_text") and not ref and not name:   # keys / text for the window itself (Ctrl+S, inline rename boxes)
            w, c, ocr = self._win(d["hwnd"]), None, None
        else:
            w, c, ocr = self.resolve(d, ref, name, role)
        info = {"name": "", "role": "text(ocr)", "automation_id": "", "help_text": "", "multiline": False, "is_password": False}
        if c is not None:
            info = self._describe(d, c)
        elif ocr:
            info["name"] = w.ocr[ocr[1]][2]
        cls = sec.classify_action(process=d["process"], window_title=d["title"], control_name=info["name"],
                                  control_role=info["role"], action=("ocr_click" if ocr else action), keys=keys,
                                  dialog_title=self._dialog_title(c) if c is not None else None,
                                  is_password=info["is_password"], class_name=d.get("class"),
                                  automation_id=info["automation_id"], help_text=info["help_text"],
                                  multiline=info["multiline"],
                                  text=(text if text is not None else value) if action in ("type", "set_value", "send_text") else None)
        base = {"window": d["title"], "process": d["process"], "control": info["name"], "role": info["role"], "action": action}
        if cls.level == "deny":
            self.audit.write(event="denied", reason=cls.reason, rule=cls.rule, **base)
            raise ToolError(cls.reason, denied=True, rule=cls.rule)
        approval = None
        if cls.level == "ask":
            before = self._thumb(d, c, "before")
            ok, approval = sec.request_approval(self.audit, {**base, "reason": cls.reason, "rule": cls.rule, "thumb": before})
            if not ok:
                raise ToolError(i18n.msg("approval_denied_error", reason=cls.reason), approval="deny", approvalId=approval, rule=cls.rule)
        try:
            via, extra = self._do(d, w, c, ocr, action, text, value, keys, direction, amount, info)
        except ToolError as e:
            self.audit.write(event="action", ok=False, error=str(e), approval_id=approval, **base)
            raise
        except Exception as e:
            self.audit.write(event="action", ok=False, error=f"{type(e).__name__}: {e}", approval_id=approval, **base)
            hint = ""
            if type(e).__name__ == "COMError":
                hint = (" (the element or the app refused the UI Automation call; for text inputs that are not real edit "
                        "controls, such as an Explorer inline rename box, use action send_text, which types with the keyboard)")
            raise ToolError(f"{type(e).__name__}: {_clip(str(e), 120)}{hint}")
        res = {"ok": True, "via": via, **extra, **self._note}
        if approval:
            res["approvalId"] = approval
            res["after"] = self._thumb(d, c, "after")
        self.audit.write(event="action", ok=True, via=via, approval_id=approval, **base)
        if eff_settle > 0 and not res.get("pending"):
            res["settledMs"] = self._settle_uia(d, eff_settle)
        if return_snapshot and not res.get("pending"):
            try:
                res["snapshot"] = self.inspect(d["id"], only_changed=True)
            except ToolError as e:
                res["snapshotError"] = str(e)
        return res

    def _thumb(self, d, c, tag):
        """Cropped screenshot of the control for approvals/audit (best effort). Returns file path or None."""
        try:
            img, (ox, oy) = winsys.capture_window(d["hwnd"])
            self._blackout_passwords(img, d, ox, oy)
            if c is not None:
                r = c.BoundingRectangle
                box = (max(r.left - ox - 8, 0), max(r.top - oy - 8, 0), min(r.right - ox + 8, img.width), min(r.bottom - oy + 8, img.height))
                if box[2] > box[0] and box[3] > box[1]:
                    img = img.crop(box)
            img.thumbnail((480, 320))
            dd = sec.state_dir() / "thumbs"
            dd.mkdir(parents=True, exist_ok=True)
            p = dd / f"{int(time.time()*1000)}_{tag}.png"
            img.save(p)
            return str(p)
        except Exception:
            return None

    def _state(self, c):
        try:
            role = role_of(c)
            _, _, value, flags, pw = self._facts(c, role)
            s = {}
            if value not in (None,):
                s["value"] = _clip(value, 120)
                if len(value) > 40:
                    s["length"] = len(value)  # lets the agent verify long text without counting characters
            fl = [f for f in flags if f in ("checked", "unchecked", "mixed", "selected", "expanded")]
            if fl:
                s["state"] = fl
            return s
        except Exception:
            return {}

    def _do(self, d, w, c, ocr, action, text, value, keys, direction, amount, info):
        if ocr:
            if action not in ("click", "invoke"):
                raise ToolError("OCR refs only support click")
            x, y, _ = w.ocr[ocr[1]]
            self.real_input(lambda: (self._front_or_fail(d), auto.Click(x, y)))
            return "ocr", {}
        role = info["role"]
        if action in ("click", "invoke"):
            # check-like controls: click toggles
            if role in ("CheckBox",):
                tp = c.GetPattern(P.TogglePattern)
                if tp:
                    tp.Toggle(0)
                    return "pattern", self._state(c)
            for pid in (P.InvokePattern,):
                pat = c.GetPattern(pid)
                if pat:
                    return "pattern", self._invoke(d, c, info)
            sp = c.GetPattern(P.SelectionItemPattern)
            if sp:
                sp.Select(0)
                return "pattern", self._state(c)
            tp = c.GetPattern(P.TogglePattern)
            if tp:
                tp.Toggle(0)
                return "pattern", self._state(c)
            ec = c.GetPattern(P.ExpandCollapsePattern)
            if ec:
                ec.Expand(0)
                return "pattern", self._state(c)
            r = c.BoundingRectangle
            if r.width() <= 0:
                raise ToolError("no pattern and element has no on-screen rect")
            self.real_input(lambda: (self._front_or_fail(d), auto.Click((r.left + r.right) // 2, (r.top + r.bottom) // 2)))
            return "input", {}
        if action == "toggle":
            tp = c.GetPattern(P.TogglePattern)
            if not tp:
                raise ToolError("element has no Toggle pattern")
            want = value
            if want is not None:
                want = str(want).lower() in ("1", "true", "on", "checked", "yes")
                if bool(tp.ToggleState == 1) == want:
                    return "pattern", self._state(c)
            tp.Toggle(0)
            return "pattern", self._state(c)
        if action == "send_text":  # real keyboard typing (IME-aware apps, rich editors); verified by read-back
            s = text if text is not None else value
            if s is None:
                raise ToolError("need text=")
            return self._type_real(d, c, self._resolve_secret(str(s)), replace=False)
        if action in ("set_value", "type"):
            s = text if text is not None else value
            if s is None:
                raise ToolError("need text= or value=")
            s = self._resolve_secret(str(s))
            if role == "Slider":
                rv = c.GetPattern(P.RangeValuePattern)
                if rv:
                    rv.SetValue(float(s))
                    return "pattern", self._state(c)
            vp = c.GetPattern(P.ValuePattern)
            if vp and not vp.IsReadOnly and role != "ComboBox":
                cls_low = (c.ClassName or "").lower()
                is_rich = "richedit" in cls_low or role == "Document"
                cur = vp.Value or ""
                if is_rich and cur.endswith("\r"):
                    cur = cur[:-1]
                new = s if action == "set_value" else cur + s
                vp.SetValue(new)
                got = vp.Value or ""
                if role == "Slider":
                    return "pattern", self._state(c)
                norm_got = got.replace("\r\n", "\n").replace("\r", "\n")
                norm_new = new.replace("\r\n", "\n").replace("\r", "\n")
                matched_val = (norm_got == norm_new) or (
                    is_rich and norm_got == (norm_new if norm_new.endswith("\n") else norm_new + "\n")
                )
                if not matched_val:  # tell the truth: max length, input filter or an app that rewrites the value
                    raise ToolError(f"value not applied as sent: field now holds {len(got)} of {len(new)} chars "
                                    f"(max length or input filter?)", truncated=len(got) < len(new),
                                    wanted=len(new), got=len(got), value=_clip(got, 60))
                return "pattern", self._state(c)
            if role == "ComboBox":
                return self._select_item(c, s)
            return self._type_real(d, c, s, replace=(action == "set_value"))
        if action == "select":
            s = text if text is not None else value
            if role == "ComboBox" or (s and c.GetPattern(P.ExpandCollapsePattern)):
                return self._select_item(c, str(s))
            sp = c.GetPattern(P.SelectionItemPattern)
            if sp:
                sp.Select(0)
                return "pattern", self._state(c)
            raise ToolError("nothing to select (give text= for combo boxes)")
        if action == "expand":
            want_collapse = str(value).lower() in ("false", "collapse")
            ec = c.GetPattern(P.ExpandCollapsePattern)
            if ec:
                (ec.Collapse if want_collapse else ec.Expand)(0)
                return "pattern", self._state(c)
            # WinForms combos expose 'Open' (collapsed) or 'Close' (expanded) child button without ExpandCollapsePattern
            for ch in c.GetChildren():
                if role_of(ch) != "Button":
                    continue
                bname = (ch.Name or "").lower()
                if bname in ("open", "mở"):
                    if not want_collapse:
                        ch.GetPattern(P.InvokePattern).Invoke(0)
                    return "pattern", {}
                if bname in ("close", "đóng"):
                    if want_collapse:
                        try:
                            ch.GetPattern(P.InvokePattern).Invoke(0)
                        except Exception:
                            pass
                        # WinForms DropDownList in an inactive window ignores UIA Close Invoke; CB_SHOWDROPDOWN collapses it cleanly.
                        hwnd = getattr(c, "NativeWindowHandle", 0)
                        if hwnd:
                            win32gui.SendMessage(int(hwnd), 0x014F, 0, 0)
                    return "pattern", {}
            raise ToolError("element has no ExpandCollapse pattern")
        if action == "focus":
            c.SetFocus()
            return "pattern", {}
        if action == "read":
            tp = c.GetPattern(P.TextPattern)
            txt = None
            vp = c.GetPattern(P.ValuePattern)
            if info["is_password"]:
                raise ToolError("password field", denied=True)
            if vp:
                txt = vp.Value
            elif tp:
                txt = tp.DocumentRange.GetText(4000)
            else:
                txt = c.Name
            return "pattern", {"length": len(txt or ""), "text": wrap_text(_clip_keep_nl(txt, 4000))}
        if action == "scroll":
            sp = c.GetPattern(P.ScrollPattern)
            if not sp:
                raise ToolError("element has no Scroll pattern")
            # ScrollAmount: 0 LargeDecrement, 1 SmallDecrement, 2 NoAmount, 3 LargeIncrement, 4 SmallIncrement
            dr = (direction or "down").lower()
            big = amount and int(amount) > 1
            inc, dec = (3, 0) if big else (4, 1)
            h, v = 2, 2
            if dr == "down": v = inc
            elif dr == "up": v = dec
            elif dr == "right": h = inc
            elif dr == "left": h = dec
            sp.Scroll(h, v)
            return "pattern", {}
        if action == "press_keys":
            if not keys:
                raise ToolError("need keys= (uiautomation SendKeys syntax, e.g. '{Ctrl}s')")
            keys, fixed = normalize_keys(keys)
            if fixed:
                self._note["keys"] = "read {{X}} as {X}"
            def go():
                self._front_or_fail(d)
                if c is not None:
                    try:
                        c.SetFocus()
                    except Exception:
                        pass
                try:
                    auto.SendKeys(keys, waitTime=0.02)
                except (TypeError, ValueError) as e:
                    raise ToolError(f"invalid keys {keys!r}: {e}. Syntax: '{{Ctrl}}s', '{{Esc}}', '{{Enter}}', plain text.")
            self.real_input(go)
            return "input", {}
        raise ToolError(f"unknown action '{action}'")

    def _invoke(self, d, c, info, wait=2.5):
        """Invoke can block for as long as a modal dialog stays open (the app handles the call inside its
        handler; field bug 5: a menu item that opens Save As hung the whole tool). Run it on a helper thread
        and return after `wait` seconds; a still-pending Invoke means 'a modal dialog is probably open'."""
        import threading
        name, role, hwnd = info["name"], info["role"], d["hwnd"]
        box = {}

        def run():
            try:
                with auto.UIAutomationInitializerInThread(debug=False):
                    c.GetPattern(P.InvokePattern).Invoke(0)  # UIA client objects are free-threaded
                    box["done"] = True
            except Exception as e:  # noqa: BLE001
                box["err"] = f"{type(e).__name__}"
                box["done"] = True

        t = threading.Thread(target=run, daemon=True)
        t.start()
        t.join(wait)
        if t.is_alive():
            self._pending_invokes[d["pid"]] = t
            return {"pending": True, "warn": "Invoke has not returned after %.1fs: a modal dialog is probably open. UIA calls to "
                                             "this app are blocked until it closes; use windows_list, then close the dialog" % wait}
        if box.get("err") and box["err"] != "COMError":
            raise ToolError(f"invoke failed: {box['err']}")
        if box.get("err") == "COMError":
            return {"warn": "Invoke raised COMError (a dialog may have opened); verify with windows_list/wait_for"}
        return {}

    def _type_real(self, d, c, s, replace):
        vp = c.GetPattern(P.ValuePattern) if c is not None else None
        before = (vp.Value or "") if vp else None

        def go():
            self._front_or_fail(d)
            if c is not None:
                c.SetFocus()
            if replace:
                auto.SendKeys("{Ctrl}a", waitTime=0)
            auto.SendKeys(s.replace("{", "{{}").replace("}", "{}}"), waitTime=0.01)

        self.real_input(go)
        if vp is not None:
            got = vp.Value or ""
            want = s if replace else before + s
            if got != want:
                raise ToolError(f"typed text not fully applied: field holds {len(got)} of {len(want)} chars "
                                f"(max length, input filter or IME?)", truncated=len(got) < len(want),
                                wanted=len(want), got=len(got), value=_clip(got, 60))
        return "input", self._state(c)

    def _resolve_secret(self, s: str) -> str:
        m = re.fullmatch(r"\$secret:([A-Za-z0-9_]+)", s)
        if not m:
            return s
        f = Path(os.environ.get("TURBO_DESKTOP_SECRETS", str(Path.home() / ".turbo-desktop-secrets.json")))
        try:
            return json.loads(f.read_text(encoding="utf-8"))[m.group(1)]
        except Exception:
            raise ToolError(f"secret {m.group(1)} not found in {f.name}")

    def _select_item(self, c, wanted: str):
        ec = c.GetPattern(P.ExpandCollapsePattern)
        opened = False
        if ec:
            ec.Expand(0)
            opened = True
        else:
            for ch in c.GetChildren():
                if role_of(ch) == "Button" and (ch.Name or "").lower() in ("open", "mở"):
                    ch.GetPattern(P.InvokePattern).Invoke(0)
                    opened = True
                    break
        item = None
        for _ in range(10):
            stack = list(c.GetChildren())
            while stack:
                x = stack.pop(0)
                if role_of(x) == "ListItem" and (x.Name or "").lower() == wanted.lower():
                    item = x
                    break
                stack.extend(x.GetChildren())
            if item:
                break
            time.sleep(0.1)
        if not item:
            if opened and ec:
                ec.Collapse(0)
            raise ToolError(f"no option '{wanted}' in combo box")
        item.GetPattern(P.SelectionItemPattern).Select(0)
        try:
            if ec:
                ec.Collapse(0)
            else:
                for ch in c.GetChildren():
                    if role_of(ch) == "Button" and (ch.Name or "").lower() in ("close", "đóng"):
                        ch.GetPattern(P.InvokePattern).Invoke(0)
        except Exception:
            pass
        return "pattern", self._state(c)

    # ------------------------------------------------------------ other tools

    def batch(self, steps: list[dict], window=None, return_snapshot=False,
              returnSnapshot: bool | None = None, settle_ms: int = 0,
              settleMs: int | None = None) -> dict:
        if returnSnapshot is not None:
            return_snapshot = bool(returnSnapshot)
        if settleMs is not None:
            settle_ms = settleMs
        eff_settle = normalize_settle_ms(settle_ms)
        self.bridge.check_release()
        self._ind_activity()
        results = []
        failed = None
        last_win = window
        for i, st in enumerate(steps):
            self.bridge.check_release()
            st = dict(st)
            op = st.pop("op", "act")
            st.setdefault("window", window)
            if st.get("window"):
                last_win = st["window"]
            elif st.get("ref"):
                try:
                    last_win = self._parse_ref(st["ref"])[0].wid
                except Exception:
                    pass
            try:
                if op == "act":
                    try:
                        r = self.act(**st)
                    except TypeError as e:   # e.g. an invented field such as "real": say what is valid
                        raise ToolError(f"bad step arguments: {e}. Valid fields: window, ref, name, role, action, text, "
                                        f"value, keys, direction, amount, returnSnapshot, settleMs (plus op)")
                    results.append({"i": i, **{k: v for k, v in r.items() if k != "after"}})
                elif op == "wait_for":
                    results.append({"i": i, **self.wait_for(**st)})
                elif op == "inspect":
                    st.setdefault("only_changed", True)
                    results.append({"i": i, "ok": True, "snapshot": self.inspect(**st)})
                else:
                    raise ToolError(f"unknown op {op}")
            except ToolError as e:
                results.append({"i": i, "ok": False, "error": str(e), **e.extra})
                failed = i
                break
        if failed is None:
            # All steps ran: list only the steps that carry something (a snapshot, a value, a note, real input).
            plain = lambda r: set(r) <= {"i", "ok", "via"} and r.get("ok") is True and r.get("via") in (None, "pattern")
            out = {"ok": True, "ran": len(results), "steps": [r for r in results if not plain(r)]}
            if not sec.stop_requested():
                self._ind_activity()
        else:
            out = {"ok": False, "steps": results, "failedAt": failed}
        snap_win = window or last_win
        if eff_settle > 0 and failed is None and snap_win:
            try:
                out["settledMs"] = self._settle_uia(self.find_window(snap_win), eff_settle)
            except ToolError:
                pass
        if return_snapshot and snap_win:
            try:
                out["snapshot"] = self.inspect(snap_win, only_changed=True)
            except ToolError as e:
                out["snapshotError"] = str(e)
        return out

    def _saw_windows_for(self, window=None, d: dict | None = None, title: str | None = None) -> list[dict]:
        try:
            wl = self.windows_list()
        except Exception:
            return []
        if d is not None:
            proc = (d.get("process") or "").lower()
            pid = d.get("pid")
            matched = [w for w in wl if (proc and (w.get("process") or "").lower() == proc) or (pid and w.get("pid") == pid)]
            if matched:
                return matched
        if window is not None:
            spec = str(window).strip().lower()
            if spec.startswith("process:"):
                pname = spec[8:]
                matched = [w for w in wl if (w.get("process") or "").lower() == pname]
                if matched:
                    return matched
            else:
                matched = [
                    w for w in wl
                    if spec in (w.get("process") or "").lower()
                    or spec in (w.get("title") or "").lower()
                    or w.get("id") == spec
                ]
                if matched:
                    return matched
        if title:
            low = title.lower()
            matched = [w for w in wl if low in (w.get("process") or "").lower() or low in (w.get("title") or "").lower()]
            if matched:
                return matched
        return wl

    def wait_for(self, window=None, text=None, gone=False, title=None, timeout=8.0, **_):
        timeout = 8.0 if timeout is None else float(timeout)
        end = time.time() + timeout
        last_d = None
        while True:
            self.bridge.check_release()
            if sec.stop_requested():  # field bug 4: STOP during a long wait was ignored
                self.indicator.hide_now()
                raise ToolError(i18n.msg("stop_wait_error"), stopped=True)
            if window is None and title:
                found = any(title.lower() in d["title"].lower() for d in self.windows_list())
                if found != bool(gone):
                    return {"ok": True}
            elif window is not None:
                try:
                    d = self.find_window(window)
                    last_d = d
                except ToolError:
                    if gone and not text:
                        return {"ok": True}
                    d = None
                if d is not None and text:
                    self._guard_window(d, "inspect")
                    root = self._ctrl_for(d)
                    ex = bool(root and root.Control(searchDepth=14, SubName=text).Exists(0, 0))
                    if ex != bool(gone):
                        return {"ok": True}
                elif d is not None and not text and not gone:
                    return {"ok": True}
            if time.time() >= end:
                seen = self._saw_windows_for(window=window, d=last_d, title=title)
                titles = [w["title"] for w in seen]
                seen_desc = ", ".join(f'{w["id"]} "{w["title"]}" [{w["process"]}]' for w in seen) if seen else "none"
                raise ToolError(
                    f"timeout waiting for {'gone ' if gone else ''}{text or title or window} (saw: {seen_desc})",
                    saw=titles,
                    windows=[{"id": w["id"], "title": w["title"], "process": w["process"]} for w in seen],
                )
            time.sleep(0.2)

    def _clean_launch(self, exe_name, path):
        """(argv, description) for a launch that does not reopen the user's previous documents, or None."""
        tmp = Path(tempfile.gettempdir()) / "turbo-desktop-clean"
        tmp.mkdir(parents=True, exist_ok=True)
        stamp = str(int(time.time() * 1000))
        if exe_name == "notepad":
            f = tmp / f"new-{stamp}.txt"
            f.write_text("", encoding="utf-8")
            return [path, str(f)], f"new temp file {f}"
        if exe_name == "code":
            d = tmp / f"ws-{stamp}"
            d.mkdir()
            return [path, "--new-window", str(d)], f"--new-window on temp folder {d}"
        return None

    def launch(self, target: str, args: str = "", wait=8.0, return_existing: bool = False,
               return_snapshot: bool = True, snapshot_query: str | None = None,
               snapshot_max_chars: int = 1500, **kw) -> dict:
        if "returnExisting" in kw:
            return_existing = bool(kw.pop("returnExisting"))
        if "returnSnapshot" in kw:
            return_snapshot = bool(kw.pop("returnSnapshot"))
        if "snapshotQuery" in kw:
            snapshot_query = kw.pop("snapshotQuery")
        if "snapshotMaxChars" in kw:
            snapshot_max_chars = int(kw.pop("snapshotMaxChars"))
        self.bridge.check_release()
        self._ind_activity()
        if sec.stop_requested():
            self.indicator.hide_now()
            raise ToolError(i18n.msg("stop_launch_error"), stopped=True)
        t = APP_ALIASES.get(target.lower(), target)
        resolved = resolve_launch_target(target)
        how = resolved["how"] if resolved else "path"
        matched = resolved["matched"] if resolved else (Path(t).name or t)
        path = resolved["path"] if resolved else t
        exe_name, proc_candidates = _resolve_launch_names(target, t, resolved)
        rs = rules_mod.load_ruleset()
        restores = any(c in rs.session_restore for c in proc_candidates)
        if restores:
            for c in proc_candidates:
                if c in rs.session_restore:
                    exe_name = c
                    break
        cls = sec.classify_action(process=exe_name, window_title=None, action="launch",
                                  session_restore=restores, ruleset=rs)
        if cls.level == "allow":
            for cand in proc_candidates:
                if cand != exe_name:
                    alt = sec.classify_action(process=cand, window_title=None, action="launch",
                                              session_restore=restores, ruleset=rs)
                    if alt.level != "allow":
                        cls = alt
                        break
        if cls.level != "deny" and matched:
            t_cls = sec.classify_action(process=exe_name, window_title=matched, action="launch",
                                        session_restore=restores, ruleset=rs)
            if t_cls.level == "deny":
                cls = t_cls
        base = {"action": "launch", "control": t, "window": "", "process": exe_name}
        if cls.level == "deny":
            self.audit.write(event="denied", reason=cls.reason, rule=cls.rule, **base)
            raise ToolError(cls.reason, denied=True, rule=cls.rule)
        argv = [path] + _split_launch_args(args)
        extra: dict = {"how": how, "matched": matched}
        if resolved and "shortcut" in resolved:
            extra["shortcut"] = resolved["shortcut"]
        if resolved and "appId" in resolved:
            extra["appId"] = resolved["appId"]
        if restores:
            require_clean = os.environ.get("TURBO_DESKTOP_REQUIRE_CLEAN") == "1"
            clean = self._clean_launch(exe_name, path) if (rs.preset == "strict" or require_clean) else None
            if require_clean and not clean:
                raise ToolError(f"{exe_name} reopens the user's previous documents and has no clean-launch path; refused "
                                f"(TURBO_DESKTOP_REQUIRE_CLEAN=1)", rule="launch-session-restore")
            if clean:
                argv = clean[0]
                extra = {**extra, "launchMode": "clean", "clean": clean[1]}
            else:
                extra = {**extra, "launchMode": "normal",
                         "warn": "this app may reopen the user's previous files; their contents will be visible to the model"}
        if cls.level == "ask":
            ok, aid = sec.request_approval(self.audit, {**base, "reason": cls.reason, "rule": cls.rule})
            if not ok:
                raise ToolError(i18n.msg("approval_denied_error", reason=cls.reason), approval="deny", rule=cls.rule)
        before_list = self.windows_list()
        before = {d["hwnd"] for d in before_list}
        proc = None
        try:
            if how in ("start-menu", "appsfolder"):
                os.startfile(path)
            else:
                proc = subprocess.Popen(argv, close_fds=True, startupinfo=no_activate_startupinfo())
        except OSError as e:
            raise ToolError(f"cannot start {t}: {e}")
        proc_pid = getattr(proc, "pid", None)
        wait_f = float(wait)
        step = min(0.25, max(0.02, wait_f / 4))

        def fresh(only_matched: bool) -> list[dict]:
            ws = [d for d in self.windows_list() if d["hwnd"] not in before]
            if only_matched:
                ws = [d for d in ws if _matches_launched_app(d, proc_pid, exe_name, matched, target)]
            return ws

        def settle(ws: list[dict], only_matched: bool, deadline: float) -> list[dict]:
            # Let a splash/launcher window hand over to the real one, then re-read.
            if wait_f >= 0.4:
                time.sleep(min(0.4, max(0.01, deadline - time.time())))
                again = fresh(only_matched)
                if again:
                    return again
            return ws

        end = time.time() + wait_f
        new: list[dict] = []
        unmatched: list[dict] = []
        while time.time() < end:
            time.sleep(min(step, max(0.01, end - time.time())))
            cand = fresh(False)
            mine = [d for d in cand if _matches_launched_app(d, proc_pid, exe_name, matched, target)]
            if mine:
                new = settle(mine, True, end)
                break
            if cand:
                unmatched = cand   # some new window, not obviously ours: keep looking for ours until `wait`
        if not new and unmatched:
            new = [d for d in fresh(False) if d["hwnd"] in {u["hwnd"] for u in unmatched}] or unmatched
        if not new:
            # Apps like Zalo start through a launcher process: keep watching for up to `wait` seconds
            # for a new top-level window of the launched process or of the resolved app name.
            end2 = time.time() + wait_f
            while time.time() < end2:
                time.sleep(min(step, max(0.01, end2 - time.time())))
                mine = fresh(True)
                if mine:
                    new = settle(mine, True, end2)
                    break
        if len(new) > 1:
            new.sort(key=lambda d: (0 if _matches_launched_app(d, proc_pid, exe_name, matched, target) else 1))
        for d in new:
            self.launched.add(d["hwnd"])
        if not new:
            # Single-instance apps (Win11 Notepad, Explorer, Settings) may answer with a window that already existed.
            # Never hand that back by default: it can hold the owner's documents.
            now = self.windows_list()
            cand_names = {exe_name, fold_text(matched).replace(" ", "")}
            reused = [d for d in now if d["hwnd"] in before and (d["process"].lower() in cand_names or d["focused"])]
            reused = [d for d in reused if d["process"].lower() in cand_names or (
                d["focused"] and d["hwnd"] not in {b["hwnd"] for b in before_list if b.get("focused")})]
            if reused:
                extra = {**extra, "reused_existing_window": True}
                if return_existing:
                    new = reused
        self.audit.write(event="action", ok=bool(new) or bool(extra.get("reused_existing_window")), via="launch",
                         how=how, matched=matched, new_windows=[d["title"] for d in new], **base)
        out: dict = {
            "ok": True,
            **extra,
            "windows": [{k: d[k] for k in ("id", "title", "process", "pid")} for d in new],
        }
        if new and return_snapshot:
            try:
                out["snapshot"] = self.inspect(
                    new[0]["id"],
                    "interactive",
                    query=snapshot_query,
                    max_chars=int(snapshot_max_chars),
                )
            except ToolError as e:
                out["snapshotError"] = str(e)
            except Exception as e:
                out["snapshotError"] = str(e)
        elif not new:
            out["pending"] = True
            if extra.get("reused_existing_window"):
                out["hint"] = (f"{matched} reused an existing window; pass returnExisting=true or inspect the "
                               f"existing window directly instead of calling wait_for")
            elif not winsys.on_input_desktop() and (how == "appsfolder" or exe_name in ("calc", "calculator", "calculatorapp")):
                out["hint"] = (f"{matched} started from an isolated Win32 desktop (not the active input desktop); "
                               f"UWP/Store apps activate on the interactive Default desktop and are invisible here")
            else:
                out["hint"] = (f"{matched} started but no new window appeared yet (launcher or tray app); "
                               f"do not loop on wait_for—check open windows or pass returnExisting=true")
        if not sec.stop_requested():
            self._ind_activity()
        return out

    def close_launched(self):
        """Close every window this Desktop launched (matched by window handle, so UWP apps whose process differs
        from the launcher are found too). Windows we did not launch are never touched."""
        try:
            self.bridge.stop()
        except Exception:
            pass
        try:
            if getattr(self.lock, "locked", False):
                self.lock.release("exit")
            self.indicator.hide_now()
        except Exception:
            pass
        for hwnd in list(self.launched):
            try:
                if win32gui.IsWindow(hwnd):
                    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            except Exception:
                pass
        self.launched.clear()

    def window_control(self, window, action):
        self.bridge.check_release()
        self._ind_activity()
        d = self.find_window(window)
        self._guard_window(d, "focus" if action != "close" else "close")
        hwnd = d["hwnd"]
        if action == "close":
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
        elif action == "minimize":
            win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
        elif action == "maximize":
            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
        elif action == "restore":
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        elif action == "activate":
            self.real_input(lambda: win32gui.SetForegroundWindow(hwnd))
        else:
            raise ToolError(f"unknown window action {action}")
        self.audit.write(event="window", action=action, window=d["title"], process=d["process"])
        return {"ok": True}

    def _blackout_passwords(self, img, d: dict | None = None, ox: int = 0, oy: int = 0, rects=None):
        try:
            root = self._ctrl_for(d) if (rects is None and d is not None) else None
            blackout_password_fields(img, ox, oy, rects=rects, root=root)
        except Exception:
            pass
        return img

    def screenshot(self, window, region=None, max_width: int = 1280, maxWidth: int | None = None):
        if maxWidth is not None:
            max_width = maxWidth
        mw = _normalize_max_width(max_width)
        parsed_region = _parse_region_spec(region, "region")
        d = self.find_window(window)
        self._guard_window(d, "inspect")
        img, (ox, oy) = winsys.capture_window(d["hwnd"])
        self._blackout_passwords(img, d, ox, oy)
        if parsed_region is not None:
            img, _, _ = _crop_region(img, parsed_region, "region")
        if img.width > mw:
            img = img.resize((mw, max(1, int(img.height * mw / img.width))))
        import io
        buf = io.BytesIO()
        img.save(buf, "PNG")
        self.audit.write(event="screenshot", window=d["title"], process=d["process"])
        return buf.getvalue()


def _password_rects(root) -> list[tuple[int, int, int, int]]:
    out: list[tuple[int, int, int, int]] = []
    if root is None:
        return out
    stack = [root]
    while stack:
        x = stack.pop()
        if x is None:
            continue
        try:
            kids = x.GetChildren()
        except Exception:
            continue
        for k in kids:
            try:
                if role_of(k) == "Edit" and k.GetPropertyValue(auto.PropertyId.IsPasswordProperty):
                    r = k.BoundingRectangle
                    out.append((int(r.left), int(r.top), int(r.right), int(r.bottom)))
            except Exception:
                pass
            stack.append(k)
    return out


def blackout_password_fields(img, ox: int = 0, oy: int = 0, rects: Iterable | None = None, root=None):
    """Black out password-field rectangles (screen coords `(left, top, right, bottom)` or objects with
    `.left/.top/.right/.bottom`, offset by window origin `(ox, oy)`) on `img` in place and return `img`."""
    from PIL import ImageDraw

    rect_list = list(rects) if rects is not None else _password_rects(root)
    if not rect_list:
        return img
    draw = ImageDraw.Draw(img)
    for r in rect_list:
        try:
            if hasattr(r, "left"):
                l, t, right, b = int(r.left), int(r.top), int(r.right), int(r.bottom)
            else:
                l, t, right, b = int(r[0]), int(r[1]), int(r[2]), int(r[3])
            if right > l and b > t:
                draw.rectangle((l - ox, t - oy, right - ox, b - oy), fill="black")
        except Exception:
            continue
    return img


def _resolve_launch_names(target: str, t: str, resolved: dict | None) -> tuple[str, list[str]]:
    """Return `(primary_exe_stem, candidate_process_names)` for launch classification."""
    how = resolved["how"] if resolved else "path"
    matched = resolved["matched"] if resolved else (Path(t).name or t)
    path = resolved["path"] if resolved else t
    lnk_target = None
    if resolved:
        for k in ("target", "exe", "target_exe", "target_path", "executable"):
            if resolved.get(k):
                lnk_target = str(resolved[k])
                break
    if lnk_target:
        exe_stem = Path(lnk_target).stem.lower()
    elif how == "path" or str(path).lower().endswith(".exe"):
        exe_stem = Path(path).stem.lower()
    else:
        exe_stem = Path(t).stem.lower()
    folded_matched = rules_mod.fold_process_name(fold_text(_clean_query(matched)))
    folded_target = rules_mod.fold_process_name(fold_text(_clean_query(target)))
    folded_exe = rules_mod.fold_process_name(fold_text(_clean_query(exe_stem)))
    mapped = (
        rules_mod.DISPLAY_PROCESS_ALIASES.get(folded_matched)
        or rules_mod.DISPLAY_PROCESS_ALIASES.get(folded_target)
        or rules_mod.DISPLAY_PROCESS_ALIASES.get(folded_exe)
    )
    if lnk_target or how == "path":
        primary = mapped or exe_stem or folded_matched
    else:
        primary = mapped or folded_matched or exe_stem
    cands: list[str] = []
    for item in (primary, exe_stem, folded_matched, mapped, folded_target, fold_text(_clean_query(matched))):
        c = (item or "").strip().lower().removesuffix(".exe")
        if c and c not in cands:
            cands.append(c)
    return (primary or exe_stem), cands


def _clip_keep_nl(s, n):
    s = (s or "").replace("\r\n", "\n").replace("\r", "\n")
    return s if len(s) <= n else s[:n] + "…"


def wrap_text(s):
    return sec.wrap_untrusted(s, "text ")


_CAPTION = ("minimize", "maximize", "restore", "close")


def _is_caption_button(ctrl, w_title: str, q: str) -> bool:
    """Minimize/Maximize/Restore/Close buttons that WinUI apps draw outside a TitleBar ("Close Calculator").
    window_control does these; hide them from snapshots unless the query asks for one.
    A bare "Close" is only treated as a caption button when its AutomationId is "Close"."""
    try:
        name = fold_text(ctrl.Name or "")
    except Exception:
        return False
    try:
        aid = (ctrl.AutomationId or "").strip()
    except Exception:
        aid = ""
    for c in _CAPTION:
        if w_title and name == f"{c} {w_title}":
            return not (q and c in q)
        if name == c:
            if c == "close" and aid.lower() != "close":
                return False
            return not (q and c in q)
    return False


def _matches_launched_app(d: dict, proc_pid: int | None, exe_name: str, matched: str, target: str) -> bool:
    """True when window `d` belongs to the launched process (by pid or process name) or resolved app name."""
    if proc_pid is not None and d.get("pid") == proc_pid:
        return True
    cands = set()
    for raw in (exe_name, Path(matched).stem if matched else "", matched, _clean_query(target)):
        f = fold_text(raw)
        for suf in (".exe", ".lnk"):
            if f.endswith(suf) and len(f) > len(suf):
                f = f[:-len(suf)].strip()
        if f:
            cands.add(f)
            cands.add(f.replace(" ", ""))
    w_proc = fold_text(d.get("process") or "")
    w_proc_ns = w_proc.replace(" ", "")
    w_title = fold_text(d.get("title") or "")
    for c in cands:
        if not c:
            continue
        if w_proc and (c == w_proc or c == w_proc_ns or (len(c) >= 3 and (c in w_proc or w_proc in c))):
            return True
        if w_title and len(c) >= 2 and c in w_title:
            return True
    return False


def _summarise_siblings(
    elements: list[tuple[int, str, object, str, tuple]],
    wid: str,
    first_n: int = 8,
    prefix: str = "",
) -> list[str]:
    """Collapse repeated sibling groups (> first_n items with the same parent and role, or consecutive same-role runs)
    into the first `first_n` items followed by `<Role> ×<total> (first <first_n> shown; use query= to filter)`."""
    from collections import Counter

    group_counts = Counter((pk, role) for _, _, pk, role, _ in elements)
    big_groups = {g for g, c in group_counts.items() if c > first_n}

    if big_groups:
        seen_in_group: dict[tuple[object, str], int] = {}
        omitted_keys: set[object] = set()
        out: list[str] = []
        for n, line, pk, role, anc_keys in elements:
            if any(k in omitted_keys for k in anc_keys[:-1]):
                continue
            g = (pk, role)
            if g in big_groups:
                idx = seen_in_group.get(g, 0)
                seen_in_group[g] = idx + 1
                if idx < first_n:
                    out.append(f"{prefix}[{wid}:e{n}] {line}")
                else:
                    if anc_keys:
                        omitted_keys.add(anc_keys[-1])
                    if idx == first_n:
                        out.append(f"{role} ×{group_counts[g]} (first {first_n} shown; use query= to filter)")
            else:
                out.append(f"{prefix}[{wid}:e{n}] {line}")
        return out

    # Fallback when each repeated item has its own wrapper parent: collapse consecutive same-role runs > first_n
    out = []
    i = 0
    m = len(elements)
    while i < m:
        role = elements[i][3]
        j = i + 1
        while j < m and elements[j][3] == role:
            j += 1
        run_len = j - i
        if run_len > first_n:
            for k in range(i, i + first_n):
                n, line, _, _, _ = elements[k]
                out.append(f"{prefix}[{wid}:e{n}] {line}")
            out.append(f"{role} ×{run_len} (first {first_n} shown; use query= to filter)")
        else:
            for k in range(i, j):
                n, line, _, _, _ = elements[k]
                out.append(f"{prefix}[{wid}:e{n}] {line}")
        i = j
    return out
