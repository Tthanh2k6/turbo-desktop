"""Claude Code PermissionRequest hook: send the prompt to the turbo-desktop hub (phone + push) and show it on the PC.

Install with `python -m turbo_hub cc-hook install` (adds this hook to ~/.claude/settings.json), remove with
`python -m turbo_hub cc-hook uninstall`.

Whichever side answers first wins, the other closes:
  - phone: the approval card / notification in Turbo Remote;
  - PC: a small dialog from this script ("Cho phép" / "Từ chối" / "Để Claude Code hỏi").
No timeout: it waits until someone answers. If the hub is not running, it prints nothing and Claude Code asks as usual.

Env: TURBO_HUB_URL (default http://127.0.0.1:8750), TURBO_HUB_DATA (hub data dir), TURBO_CC_HOOK_NO_DIALOG=1.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

HUB = os.environ.get("TURBO_HUB_URL", "http://127.0.0.1:8750").rstrip("/")


def _data_dir() -> Path:
    env = os.environ.get("TURBO_HUB_DATA")
    return Path(env) if env else Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "turbo-desktop-hub"


def load_token() -> str | None:
    p = _data_dir() / "cc_hook_token.dpapi"
    if not p.exists():
        return None
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from turbo_hub import dpapi
    return dpapi.unprotect(p.read_bytes()).decode()


class Http:
    def __init__(self, base: str, token: str):
        self.base, self.token = base, token

    def call(self, method: str, path: str, body: dict | None = None, key: str = "", timeout: float = 5.0) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json", "X-CC-Token": self.token,
                                              "X-CC-Key": key})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))


def output(decision: str | None, by: str | None = None) -> str:
    """Hook stdout. None/withdrawn: print nothing, so Claude Code falls back to its own prompt."""
    if decision == "allow":
        d = {"behavior": "allow"}
    elif decision in ("deny", "stop"):
        who = {"pc": "on the PC", "phone": "on the phone"}.get(by or "", "")
        msg = "The owner pressed STOP on the phone." if decision == "stop" else f"The owner denied this {who}".strip() + "."
        d = {"behavior": "deny", "message": msg}
    else:
        return ""
    return json.dumps({"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": d}})


class Dialog:
    """Tk dialog that never takes keyboard input: buttons are mouse-only and enabled after a short delay, so the
    owner typing elsewhere cannot approve by accident."""

    def __init__(self, info: dict, on_choice):
        import tkinter as tk
        self.tk = tk
        self.root = tk.Tk()
        self.on_choice = on_choice
        r = self.root
        r.title("Claude Code cần duyệt")
        r.attributes("-topmost", True)
        r.resizable(False, False)
        r.configure(bg="#F7F6F3")
        pad = {"padx": 14}
        tk.Label(r, text="Claude Code cần bạn duyệt", font=("Segoe UI Semibold", 12), bg="#F7F6F3",
                 fg="#1C1B19").pack(anchor="w", pady=(12, 0), **pad)
        tk.Label(r, text=f"{info.get('window', 'Claude Code')}  ·  {info.get('tool', '')}", font=("Segoe UI", 9),
                 bg="#F7F6F3", fg="#5B5A56").pack(anchor="w", pady=(2, 6), **pad)
        txt = tk.Text(r, width=72, height=min(14, max(3, str(info.get("detail", "")).count("\n") + 2)),
                      font=("Consolas", 10), wrap="word", bg="#FFFFFF", fg="#1C1B19", relief="flat",
                      highlightthickness=1, highlightbackground="#DDDAD3", takefocus=0)
        txt.insert("1.0", info.get("detail") or info.get("control") or "")
        txt.configure(state="disabled")
        txt.pack(fill="x", **pad)
        tk.Label(r, text="Cũng đang chờ trên điện thoại. Bên nào bấm trước thì lấy bên đó.", font=("Segoe UI", 9),
                 bg="#F7F6F3", fg="#5B5A56").pack(anchor="w", pady=(6, 0), **pad)
        row = tk.Frame(r, bg="#F7F6F3")
        row.pack(fill="x", pady=12, **pad)
        self.buttons = []
        for label, val, bg, fg in (("Cho phép", "allow", "#1C1B19", "#FFFFFF"), ("Từ chối", "deny", "#E9E6DF", "#1C1B19"),
                                   ("Để Claude Code hỏi", "withdrawn", "#F7F6F3", "#5B5A56")):
            b = tk.Button(row, text=label, command=lambda v=val: self.choose(v), takefocus=0, state="disabled",
                          font=("Segoe UI", 10), bg=bg, fg=fg, activebackground=bg, relief="flat", padx=14, pady=5)
            b.pack(side="left", padx=(0, 8))
            self.buttons.append(b)
        r.protocol("WM_DELETE_WINDOW", lambda: None)   # closing the window is not an answer
        r.after(700, lambda: [b.configure(state="normal") for b in self.buttons])
        r.update_idletasks()
        w, h = r.winfo_width(), r.winfo_height()
        r.geometry(f"+{r.winfo_screenwidth() - w - 24}+{r.winfo_screenheight() - h - 72}")
        self.closed = False

    def choose(self, v: str) -> None:
        if not self.closed:
            self.on_choice(v)

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            self.root.destroy()

    def loop(self, done: threading.Event) -> None:
        def tick():
            if done.is_set():
                self.close()
            else:
                self.root.after(150, tick)
        self.root.after(150, tick)
        self.root.mainloop()


def _alive(pid: int) -> bool:
    if sys.platform != "win32":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    import ctypes
    k = ctypes.windll.kernel32
    h = k.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    code = ctypes.c_ulong()
    ok = k.GetExitCodeProcess(h, ctypes.byref(code))
    k.CloseHandle(h)
    return bool(ok) and code.value == 259     # STILL_ACTIVE


def run(payload: dict, http: Http, dialog_factory=Dialog, poll_wait: float = 20.0,
        watch_parent_process: bool = False) -> tuple[str | None, str | None]:
    """Returns (decision, by). decision None = let Claude Code ask itself."""
    try:
        created = http.call("POST", "/cc/permission", payload, timeout=5.0)
    except (urllib.error.URLError, OSError, ValueError):
        return None, None   # hub not running: Claude Code asks as usual
    if "decision" in created and "id" not in created:
        return created["decision"], created.get("by")
    rid, key = created["id"], created["key"]
    done = threading.Event()
    result: dict = {}
    lock = threading.Lock()

    def finish(decision, by):
        with lock:
            if not done.is_set():
                result.update(decision=decision, by=by)
                done.set()

    def poller():
        fails = 0
        while not done.is_set():
            try:
                r = http.call("GET", f"/cc/permission/{rid}?wait={poll_wait}", key=key, timeout=poll_wait + 10)
                fails = 0
                if r.get("decision"):
                    finish(r["decision"], r.get("by"))
            except urllib.error.HTTPError as e:
                if e.code == 404:          # hub restarted and forgot the request: let Claude Code ask
                    finish(None, None)
                time.sleep(1)
            except (urllib.error.URLError, OSError, ValueError):
                fails += 1
                time.sleep(min(5, fails))  # hub briefly away: keep the PC dialog, keep trying

    def pc_choice(v: str):
        try:
            r = http.call("POST", f"/cc/permission/{rid}", {"decision": v}, key=key)
            finish(r.get("decision") or v, r.get("by") or "pc")   # phone may have answered a moment earlier
        except (urllib.error.URLError, OSError, ValueError):
            finish(v, "pc")

    def watch_parent():
        # Claude Code gone (owner answered in its own prompt, pressed Esc, closed the session): withdraw the request.
        ppid = os.getppid()
        while not done.is_set():
            time.sleep(1.0)
            if not _alive(ppid):
                try:
                    http.call("POST", f"/cc/permission/{rid}", {"decision": "withdrawn"}, key=key)
                except (urllib.error.URLError, OSError, ValueError):
                    pass
                finish("withdrawn", "claude-code")

    threading.Thread(target=poller, daemon=True).start()
    if watch_parent_process:
        threading.Thread(target=watch_parent, daemon=True).start()
    dlg = None
    if dialog_factory is not None and os.environ.get("TURBO_CC_HOOK_NO_DIALOG") != "1":
        try:
            dlg = dialog_factory(created.get("info") or {}, pc_choice)
        except Exception:
            dlg = None
    if dlg is not None:
        dlg.loop(done)
    done.wait()
    d = result.get("decision")
    return (None if d == "withdrawn" else d), result.get("by")


def main() -> int:
    raw = sys.stdin.buffer.read().decode("utf-8", "replace")
    try:
        payload = json.loads(raw)
    except ValueError:
        return 0
    token = load_token()
    if not token:
        return 0
    decision, by = run(payload, Http(HUB, token), watch_parent_process=True)
    out = output(decision, by)
    if out:
        sys.stdout.write(out)
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
