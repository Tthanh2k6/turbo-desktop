"""UIA engine: windows, compact snapshots with stable refs and deltas, actions via patterns (real input only as
a fallback, gated by owner-idle check), OCR fallback for windows with an empty UIA tree."""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import subprocess
import time
from pathlib import Path

import uiautomation as auto
import win32api
import win32con
import win32gui

from . import rules as rules_mod
from . import security as sec
from . import border as border_mod
from . import winsys
from .inputlock import InputLock

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
        self.lock = InputLock()
        self.indicator = border_mod.Indicator(disabled_by_env=os.environ.get("TURBO_DESKTOP_NO_INDICATOR") == "1")

    # ------------------------------------------------------------ windows

    def _win(self, hwnd) -> Win:
        w = self.wins.get(hwnd)
        if not w:
            self.n_wid += 1
            w = Win(f"w{self.n_wid}", hwnd)
            self.wins[hwnd] = w
            self.by_wid[w.wid] = w
        return w

    def windows_list(self, include_denied=True) -> list[dict]:
        fg = win32gui.GetForegroundWindow()
        out = []
        for t in winsys.enum_top_windows():
            name, el = winsys.process_info(t["pid"])
            w = self._win(t["hwnd"])
            deny = sec.is_denied_window(name, t["title"], t["class"])
            d = {"id": w.wid, "hwnd": t["hwnd"], "title": t["title"], "process": name, "pid": t["pid"],
                 "focused": t["hwnd"] == fg}
            if el:
                d["elevated"] = True
                d["actionable"] = False
            if deny:
                d["denied"] = deny
            out.append(d)
        return out

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

    def _guard_window(self, d: dict, action: str):
        if sec.stop_requested():
            self.indicator.hide_now()
            raise ToolError("emergency stop active: all actions blocked until resumed from the phone", stopped=True)
        if d.get("denied"):
            self.audit.write(event="denied", window=d["title"], process=d["process"], action=action, reason=d["denied"])
            raise ToolError(d["denied"], denied=True)
        if d.get("elevated") and action != "inspect":
            raise ToolError("window belongs to an elevated process; UIPI blocks input from a normal process",
                            elevated=True, actionable=False)

    # ------------------------------------------------------------ snapshot

    def _ctrl_for(self, d):
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
                max_nodes=700, ocr=None) -> str:
        d = self.find_window(window)
        self._guard_window(d, "inspect")
        w = self._win(d["hwnd"])
        root = self._ctrl_for(d)
        elements: list[tuple[int, str]] = []  # (n, line-without-ref)
        sigs: dict[int, str] = {}
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

        def walk(c, depth, parent_key, in_titlebar):
            nonlocal skipped_off, count
            try:
                kids = c.GetChildren()
            except Exception:
                return
            idxs: dict = {}
            for ch in kids:
                if count >= max_nodes:
                    return
                try:
                    role = role_of(ch)
                    tb = in_titlebar or role == "TitleBar"
                    ident = (role, ch.Name)
                    idx = idxs[ident] = idxs.get(ident, -1) + 1
                    key = key_for(ch, parent_key, idx)
                    show = (mode == "all" and not tb) or (role in INTERACTIVE and not tb) or \
                           (mode == "text" and role == "Text" and not tb)
                    if mode == "all" and tb and role in ("Button",):
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
                        if not q or q in line.lower() or q in (aid or "").lower():
                            elements.append((n, line))
                            sigs[n] = line
                            count += 1
                    walk(ch, depth + 1, key, tb)
                except Exception:
                    continue

        walk(root, 0, None, False)
        elapsed_note = ""
        tree_empty = (not seen_keys) or (len(seen_keys) <= 1 and mode != "all")
        ocr_lines = []
        if tree_empty and ocr is not False:
            try:
                ocr_lines = self._ocr_window(w, d)
            except Exception as e:
                elapsed_note = f" ocr-unavailable: {_clip(str(e), 80)}"

        head = f'window {w.wid} "{_clip(d["title"], 60)}" ({d["process"]} pid {d["pid"]})'
        if d.get("focused"):
            head += " focused"
        if d.get("elevated"):
            head += " ELEVATED actionable=false"
        lines = []
        removed = []
        prev = w.prev.get(mode)
        if only_changed and prev is not None:
            for n, line in elements:
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
            lines = [f"[{w.wid}:e{n}] {line}" for n, line in elements]
            foot = f"-- {len(elements)} elements"
        if not q:
            w.prev[mode] = dict(sigs)
        if skipped_off:
            foot += f", {skipped_off} offscreen hidden"
        if count >= max_nodes:
            foot += ", TRUNCATED (max_nodes)"
        if tree_empty:
            foot += ", treeEmpty: true"
            if ocr_lines:
                foot += ', via: "ocr"'
        for ol in ocr_lines:
            lines.append(ol)
        body = "\n".join(lines)
        if len(body) > max_chars:
            body = body[:max_chars] + f"\n... truncated at {max_chars} chars (use query= to filter)"
        return sec.wrap_untrusted(f"{head}\n{body}\n{foot}{elapsed_note}", label=w.wid + " ")

    def _ocr_window(self, w: Win, d: dict) -> list[str]:
        img, (ox, oy) = winsys.capture_window(d["hwnd"])
        # black out password fields, if any are known
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
        m = re.fullmatch(r"(?:(w\d+):)?([eo])(\d+)", ref.strip())
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
                raise OwnerBusy(f"owner is using the PC (input {idle:.1f}s ago); real input refused", ownerBusy=True)
            self.sleep(0.25)

    def real_input(self, fn):
        """Run fn() as real input: idle gate, input lock (owner's keyboard/mouse paused + banner), then restore the
        previous foreground window and cursor. Raises owner_took_over if the owner pressed Esc x3 meanwhile."""
        if no_input():
            raise ToolError("real input disabled (TURBO_DESKTOP_NO_INPUT=1) and no UIA pattern available")
        self.wait_owner_idle()
        cfg = rules_mod.load_ruleset().input_lock
        use_lock = cfg["mode"] in ("real_input", "whole_task") and os.environ.get("TURBO_DESKTOP_INPUT_LOCK", "1") != "0"
        prev_fg = win32gui.GetForegroundWindow()
        prev_pos = win32api.GetCursorPos()
        self.indicator.real_input(True)     # hard floor: the frame shows while real input is sent, whatever [indicator] says
        if use_lock:
            self.lock.acquire(cfg["max_seconds"], whole_task=(cfg["mode"] == "whole_task"))
            self.indicator.locked(True)
            self.audit.write(event="input_lock", state="on", mode=cfg["mode"])
        try:
            return fn()
        finally:
            self._own_input_at = time.time()
            try:
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
                    raise ToolError("the owner took the keyboard and mouse back (Esc x3): run paused" if info["owner_took_over"]
                                    else "STOP hotkey pressed: all actions blocked",
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

    def act(self, window, action="click", ref=None, name=None, role=None, text=None, value=None, keys=None,
            direction=None, amount=1):
        self._ind_activity()
        d = self.find_window(window) if window else self.find_window(self._parse_ref(ref)[0].wid)
        self._guard_window(d, action)
        if action == "press_keys" and not ref and not name:   # keys for the window itself (shortcuts like Ctrl+S)
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
                                  is_password=info["is_password"], class_name=None,
                                  automation_id=info["automation_id"], help_text=info["help_text"],
                                  multiline=info["multiline"])
        base = {"window": d["title"], "process": d["process"], "control": info["name"], "role": info["role"], "action": action}
        if cls.level == "deny":
            self.audit.write(event="denied", reason=cls.reason, rule=cls.rule, **base)
            raise ToolError(cls.reason, denied=True, rule=cls.rule)
        approval = None
        if cls.level == "ask":
            before = self._thumb(d, c, "before")
            ok, approval = sec.request_approval(self.audit, {**base, "reason": cls.reason, "rule": cls.rule, "thumb": before})
            if not ok:
                raise ToolError(f"approval denied or timed out: {cls.reason}", approval="deny", approvalId=approval, rule=cls.rule)
        try:
            via, extra = self._do(d, w, c, ocr, action, text, value, keys, direction, amount, info)
        except ToolError as e:
            self.audit.write(event="action", ok=False, error=str(e), approval_id=approval, **base)
            raise
        except Exception as e:
            self.audit.write(event="action", ok=False, error=f"{type(e).__name__}: {e}", approval_id=approval, **base)
            raise ToolError(f"{type(e).__name__}: {_clip(str(e), 120)}")
        res = {"ok": True, "via": via, **extra}
        if approval:
            res["approvalId"] = approval
            res["after"] = self._thumb(d, c, "after")
        self.audit.write(event="action", ok=True, via=via, approval_id=approval, **base)
        return res

    def _thumb(self, d, c, tag):
        """Cropped screenshot of the control for approvals/audit (best effort). Returns file path or None."""
        try:
            img, (ox, oy) = winsys.capture_window(d["hwnd"])
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
                new = s if action == "set_value" else (vp.Value or "") + s
                vp.SetValue(new)
                got = vp.Value or ""
                if got != new:  # tell the truth: max length, input filter or an app that rewrites the value
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
            ec = c.GetPattern(P.ExpandCollapsePattern)
            if ec:
                (ec.Collapse if str(value).lower() in ("false", "collapse") else ec.Expand)(0)
                return "pattern", self._state(c)
            # WinForms combos: the 'Open' child button
            for ch in c.GetChildren():
                if role_of(ch) == "Button" and (ch.Name or "").lower() in ("open", "mở"):
                    ch.GetPattern(P.InvokePattern).Invoke(0)
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
            def go():
                self._front_or_fail(d)
                if c is not None:
                    try:
                        c.SetFocus()
                    except Exception:
                        pass
                auto.SendKeys(keys, waitTime=0.02)
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
            return {"pending": True, "warn": "Invoke has not returned after %.1fs: a modal dialog is probably open; use windows_list / wait_for" % wait}
        if box.get("err") and box["err"] != "COMError":
            raise ToolError(f"invoke failed: {box['err']}")
        if box.get("err") == "COMError":
            return {"warn": "Invoke raised COMError (a dialog may have opened); verify with windows_list/wait_for"}
        return {}

    def _type_real(self, d, c, s, replace):
        vp = c.GetPattern(P.ValuePattern)
        before = (vp.Value or "") if vp else None

        def go():
            self._front_or_fail(d)
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

    def batch(self, steps: list[dict], window=None, return_snapshot=False) -> dict:
        self._ind_activity()
        results = []
        failed = None
        for i, st in enumerate(steps):
            st = dict(st)
            op = st.pop("op", "act")
            st.setdefault("window", window)
            try:
                if op == "act":
                    r = self.act(**st)
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
        out = {"ok": failed is None, "steps": results}
        if failed is not None:
            out["failedAt"] = failed
        if return_snapshot and window:
            try:
                out["snapshot"] = self.inspect(window, only_changed=True)
            except ToolError as e:
                out["snapshotError"] = str(e)
        return out

    def wait_for(self, window=None, text=None, gone=False, title=None, timeout=8.0, **_):
        end = time.time() + float(timeout)
        while True:
            if sec.stop_requested():  # field bug 4: STOP during a long wait was ignored
                raise ToolError("emergency stop active: wait cancelled", stopped=True)
            if window is None and title:
                found = any(title.lower() in d["title"].lower() for d in self.windows_list())
                if found != bool(gone):
                    return {"ok": True}
            elif window is not None:
                try:
                    d = self.find_window(window)
                except ToolError:
                    if gone and not text:
                        return {"ok": True}
                    d = None
                if d is not None and text:
                    self._guard_window(d, "inspect")
                    root = self._ctrl_for(d)
                    ex = root.Control(searchDepth=14, SubName=text).Exists(0, 0)
                    if ex != bool(gone):
                        return {"ok": True}
                elif d is not None and not text and not gone:
                    return {"ok": True}
            if time.time() >= end:
                raise ToolError(f"timeout waiting for {'gone ' if gone else ''}{text or title or window}")
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

    def launch(self, target: str, args: str = "", wait=8.0) -> dict:
        self._ind_activity()
        t = APP_ALIASES.get(target.lower(), target)
        exe_name = Path(t).stem.lower()
        rs = rules_mod.load_ruleset()
        restores = exe_name in rs.session_restore
        cls = sec.classify_action(process=exe_name, window_title=None, action="launch", session_restore=restores)
        if cls.level == "deny":
            raise ToolError(cls.reason, denied=True, rule=cls.rule)
        base = {"action": "launch", "control": t, "window": "", "process": exe_name}
        if sec.stop_requested():
            raise ToolError("emergency stop active", stopped=True)
        path = t if os.path.isabs(t) or os.sep in t or "/" in t else (shutil.which(t) or t)
        argv = [path] + (args.split() if args else [])
        extra = {}
        if restores:
            require_clean = os.environ.get("TURBO_DESKTOP_REQUIRE_CLEAN") == "1"
            clean = self._clean_launch(exe_name, path) if (rs.preset == "strict" or require_clean) else None
            if require_clean and not clean:
                raise ToolError(f"{exe_name} reopens the user's previous documents and has no clean-launch path; refused "
                                f"(TURBO_DESKTOP_REQUIRE_CLEAN=1)", rule="launch-session-restore")
            if clean:
                argv = clean[0]
                extra = {"launchMode": "clean", "clean": clean[1]}
            else:
                extra = {"launchMode": "normal",
                         "warn": "this app may reopen the user's previous files; their contents will be visible to the model"}
        if cls.level == "ask":
            ok, aid = sec.request_approval(self.audit, {**base, "reason": cls.reason, "rule": cls.rule})
            if not ok:
                raise ToolError(f"approval denied or timed out: {cls.reason}", approval="deny", rule=cls.rule)
        before = {d["hwnd"] for d in self.windows_list()}
        try:
            subprocess.Popen(argv, close_fds=True, startupinfo=no_activate_startupinfo())
        except OSError as e:
            raise ToolError(f"cannot start {t}: {e}")
        end = time.time() + float(wait)
        new = []
        while time.time() < end:
            time.sleep(0.25)
            new = [d for d in self.windows_list() if d["hwnd"] not in before]
            if new:
                time.sleep(0.4)
                new = [d for d in self.windows_list() if d["hwnd"] not in before]
                break
        for d in new:
            self.launched.add(d["hwnd"])
        self.audit.write(event="action", ok=bool(new), via="launch", new_windows=[d["title"] for d in new], **base)
        return {"ok": True, **extra, "windows": [{k: d[k] for k in ("id", "title", "process", "pid")} for d in new]}

    def close_launched(self):
        """Close every window this Desktop launched (matched by window handle, so UWP apps whose process differs
        from the launcher are found too). Windows we did not launch are never touched."""
        for hwnd in list(self.launched):
            try:
                if win32gui.IsWindow(hwnd):
                    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            except Exception:
                pass
        self.launched.clear()

    def window_control(self, window, action):
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

    def screenshot(self, window, region=None):
        d = self.find_window(window)
        self._guard_window(d, "inspect")
        img, (ox, oy) = winsys.capture_window(d["hwnd"])
        from PIL import ImageDraw
        draw = ImageDraw.Draw(img)
        # redact password fields
        try:
            root = self._ctrl_for(d)
            for c in root.GetChildren():
                pass
            stack = [root]
            while stack:
                x = stack.pop()
                try:
                    kids = x.GetChildren()
                except Exception:
                    continue
                for k in kids:
                    try:
                        if role_of(k) == "Edit" and k.GetPropertyValue(auto.PropertyId.IsPasswordProperty):
                            r = k.BoundingRectangle
                            draw.rectangle((r.left - ox, r.top - oy, r.right - ox, r.bottom - oy), fill="black")
                    except Exception:
                        pass
                    stack.append(k)
        except Exception:
            pass
        if region:
            x, y, w_, h_ = region
            img = img.crop((x, y, x + w_, y + h_))
        if img.width > 1280:
            img = img.resize((1280, int(img.height * 1280 / img.width)))
        import io
        buf = io.BytesIO()
        img.save(buf, "PNG")
        self.audit.write(event="screenshot", window=d["title"], process=d["process"])
        return buf.getvalue()


def _clip_keep_nl(s, n):
    s = s or ""
    return s if len(s) <= n else s[:n] + "…"


def wrap_text(s):
    return sec.wrap_untrusted(s, "text ")
