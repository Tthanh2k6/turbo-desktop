"""CLI: python -m turbo_hub setup | serve | run "<task>" | pair | devices | revoke <id> | stop | resume | verify-audit"""
from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import uvicorn

from . import config as cfgmod, screen
from .app import Settings, create_app
from .audit import AuditLog
from .runners import ClaudeRunner, FakeRunner, GenericRunner, find_claude
from .store import SecretStore
from .sysstate import mcp_system_state

TEXT = {
    "vi": {
        "choose": "Chọn mức bảo mật (Enter = 1):",
        "easy": "1) Thoáng  - máy này, hoặc điện thoại cùng Wi-Fi nếu bạn ghép; phiên 12 giờ, chỉ hỏi trước khi xoá vĩnh viễn, thanh toán, gỡ phần mềm, đổi cài đặt bảo mật Windows",
        "balanced": "2) Cân bằng - thêm Tailscale/LAN, phiên 2 giờ, mã Google Authenticator, hỏi cả khi gửi/xoá/cài đặt/terminal",
        "strict": "3) Chặt     - vân tay + mã Authenticator, hỏi mọi hành động nhạy cảm, Cloudflare Access bắt buộc nếu bật tunnel",
        "ask_phone": "Bạn sẽ ghép điện thoại qua cùng mạng Wi-Fi? [c/k]",
        "saved": "Đã lưu cài đặt vào",
        "next": "Tiếp theo: chạy `python -m turbo_hub serve`, rồi `python -m turbo_hub run \"mở Máy tính và tính 2 + 2\"`.",
        "totp_key": "Khoá Google Authenticator (nhập tay nếu không quét được):",
        "totp_phone": "Điện thoại cũng lấy được khoá này trong {n} phút: Cài đặt > Xác thực 2 bước.",
        "totp_off": "Mức bảo mật hiện tại không dùng mã 2FA.",
        "approve": "Cần duyệt: {action} \"{control}\" trong \"{window}\". Cho phép? [c/k] ",
    },
    "en": {
        "choose": "Choose a security level (Enter = 1):",
        "easy": "1) Easy     - this PC, or a phone on the same Wi-Fi if you pair one; 12 h sessions, asks only before permanent delete, payment, uninstall, Windows security settings",
        "balanced": "2) Balanced - adds Tailscale/LAN, 2 h sessions, Google Authenticator code, also asks for send/delete/install/terminal",
        "strict": "3) Strict   - fingerprint + Authenticator code, asks for every sensitive action, Cloudflare Access required if the tunnel is on",
        "ask_phone": "Will you pair a phone over the same Wi-Fi? [y/n]",
        "saved": "Saved settings to",
        "next": "Next: run `python -m turbo_hub serve`, then `python -m turbo_hub run \"open Calculator and compute 2 + 2\"`.",
        "totp_key": "Google Authenticator key (type it in if you cannot scan):",
        "totp_phone": "The phone app can also fetch this key within {n} minutes: Settings > 2FA.",
        "totp_off": "The current security level does not use a 2FA code.",
        "approve": "Approval needed: {action} \"{control}\" in \"{window}\". Allow? [y/n] ",
    },
}


def data_dir() -> Path:
    env = os.environ.get("TURBO_HUB_DATA")
    return Path(env) if env else Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "turbo-desktop-hub"


def tailscale_ip() -> str | None:
    try:
        out = subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=5).stdout.split()
        return out[0] if out and out[0].startswith("100.") else None
    except (OSError, subprocess.SubprocessError):
        return None


def lan_ip() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))   # no packet is sent; just selects the outgoing interface
            ip = s.getsockname()[0]
        return ip if ip.startswith(("192.168.", "10.", "172.")) else None
    except OSError:
        return None


def bind_sockets(port: int, hosts: list[str]) -> list[socket.socket]:
    socks = []
    for h in dict.fromkeys(["127.0.0.1", *hosts]):
        if h in ("0.0.0.0", "::", ""):
            raise SystemExit("refusing to bind all interfaces")
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind((h, port))
        s.listen(100)
        s.setblocking(False)
        socks.append(s)
    return socks


def admin(method: str, path: str, port: int, token: str, json_body=None):
    r = httpx.request(method, f"http://127.0.0.1:{port}{path}", headers={"X-Admin-Token": token},
                      json=json_body, timeout=10)
    r.raise_for_status()
    return r.json()


def show_qr(text: str, png_path: Path) -> None:
    import qrcode
    qr = qrcode.QRCode(border=2)
    qr.add_data(text)
    qr.make(fit=True)
    qr.make_image().save(png_path)
    try:
        qr.print_ascii(invert=True)
    except UnicodeEncodeError:
        pass


def agent_env(cfg: dict, dd: Path) -> dict:
    """Env for the desktop-mcp child: same config file and preset as the hub, plus the bridge's state folder."""
    return {"TURBO_DESKTOP_CONFIG": str(cfgmod.user_config_path(dd)), "TURBO_DESKTOP_PRESET": cfg["preset"],
            "TURBO_DESKTOP_STATE_DIR": str(dd / "desktop-state")}


def default_mcp_config(dd: Path) -> str | None:
    """No mcp_config set: use the desktop-mcp next to this hub (repo checkout) so a fresh install can act at all."""
    root = Path(__file__).resolve().parents[2] / "desktop-mcp"
    py = root / ".venv" / "Scripts" / "python.exe"
    if not py.exists():
        return None
    path = dd / "mcp.default.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"mcpServers": {"desktop": {"command": str(py), "args": ["-m", "turbo_desktop"],
                                                            "env": {"PYTHONPATH": str(root / "src")}}}}), "utf-8")
    return str(path)


def build_settings(cfg: dict, dd: Path, runner_kind: str, public_url: str | None, port: int, mcp_config: str | None):
    hub_local = f"http://127.0.0.1:{port}"
    internal = secrets.token_urlsafe(24)
    agent = cfg["agent"]
    mcp = mcp_config or agent.get("mcp_config") or (default_mcp_config(dd) if runner_kind != "fake" else None)
    if runner_kind == "fake":
        factory = FakeRunner
    elif agent["mode"] == "claude-stream-json":
        runner = ClaudeRunner(hub_local, internal, mcp, command=agent.get("command") or None,
                              system_prompt=agent.get("system_prompt") or None, model=agent.get("model") or None,
                              server_env=agent_env(cfg, dd))
        factory = lambda: runner  # noqa: E731  one long-lived process, reused per task
    else:
        cmd = agent.get("command") or cfgmod.default_agent_command("oneshot", find_claude())
        factory = lambda: GenericRunner(cmd, agent.get("parser", "text"))  # noqa: E731
    conns = tuple(cfg["server"]["connections"])
    sv = cfg.get("screen_view") or {}
    sv_enabled = bool(sv.get("enabled", cfg["preset"] != "strict"))
    sv_max_fps = sv.get("max_fps", 2)
    il = cfg.get("input_lock") or {}
    remote_task = str(il.get("remote_task", "whole_task"))
    max_task_min = int(il.get("max_task_minutes", 15))
    patterns = tuple((cfg.get("privacy") or {}).get("secret_title_patterns") or screen.SECRET_TITLE_PATTERNS)
    return Settings(
        data_dir=dd, runner_factory=factory, approval_timeout=float(cfg["approval"]["timeout_seconds"]),
        session_ttl=float(cfg["session"]["hours"]) * 3600, pair_code_ttl=float(cfg["auth"]["pairing_window_minutes"]) * 60,
        public_url=public_url or hub_local, internal_token=internal, system_state=mcp_system_state(mcp, agent_env(cfg, dd)),
        classifier=cfgmod.make_classifier(cfg), approval_engine=cfg["approval"].get("engine", "desktop-mcp"),
        desktop_state_dir=dd / "desktop-state",
        policy={"preset": cfg["preset"], "totp": bool(cfg["auth"]["totp"]), "biometric": bool(cfg["auth"]["biometric"]),
                "sessionHours": cfg["session"]["hours"], "lockMode": cfg["input_lock"]["mode"],
                "lockRemoteTask": remote_task,
                "screenView": {"enabled": sv_enabled, "maxFps": sv_max_fps},
                "border": bool(cfg["indicator"]["border"]), "cfAccess": bool(cfg["cloudflare"]["require_access"]),
                "ask": cfg["approval"]["enabled"]}, totp_required=bool(cfg["auth"]["totp"]),
        biometric_required=bool(cfg["auth"]["biometric"]), persist_sessions=bool(cfg["session"].get("persist", False)), connections=conns,
        require_access_header=bool(cfg["cloudflare"]["require_access"]),
        remote_task_lock=remote_task, max_task_minutes=max_task_min,
        screen_view_enabled=sv_enabled, screen_view_max_fps=float(sv_max_fps),
        secret_title_patterns=patterns)


def cmd_setup(a, dd: Path) -> None:
    path = cfgmod.user_config_path(dd)
    t = TEXT[a.lang]
    if a.preset:
        choice = a.preset
    else:
        print(t["choose"])
        for k in cfgmod.PRESETS:
            print("  " + t[k])
        pick = input("> ").strip() or "1"
        choice = cfgmod.PRESETS[int(pick) - 1] if pick in "123" else pick
    cfgmod.load_config(None, choice)  # validates the name
    phone = a.phone
    if phone is None and choice == "easy" and not a.preset:
        phone = input(t["ask_phone"] + " ").strip().lower()[:1] in ("y", "c")
    cfgmod.write_user_config(path, choice, bool(phone))
    print(f"{t['saved']} {path}\n{t['next']}")


def cmd_run(a, dd: Path) -> None:
    """Local use without a phone: start a task, print events, ask for approvals in this terminal."""
    t = TEXT[a.lang]
    token = SecretStore(dd).admin_token
    admin("POST", "/admin/tasks", a.port, token, {"text": a.task})
    since, asked = 0, set()
    while True:
        for ev in admin("GET", f"/admin/events?since={since}", a.port, token):
            since = ev["seq"]
            if ev["type"] in ("text", "tool_call", "tool_result", "warning", "final"):
                print(f"[{ev['type']}] {ev.get('text') or ev.get('tool') or ev.get('summary') or ''}")
            if ev["type"] == "approval_request" and ev["approval_id"] not in asked:
                asked.add(ev["approval_id"])
                ans = input(t["approve"].format(action=ev.get("action"), control=ev.get("control"),
                                                window=ev.get("window"))).strip().lower()
                admin("POST", f"/admin/approvals/{ev['approval_id']}", a.port, token,
                      {"decision": "allow" if ans[:1] in ("c", "y") else "deny"})
            if ev["type"] == "task_finished":
                return
        time.sleep(0.5)


def cmd_totp(a, dd: Path, token: str, cfg: dict) -> None:
    """Show (or rotate) the Authenticator key and open the enrolment window so the phone can fetch it too."""
    t = TEXT[a.lang]
    try:
        info = admin("POST", "/admin/totp", a.port, token, {"rotate": bool(a.rotate)})
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 409:
            print(t["totp_off"])
            return
        raise
    print(t["totp_key"])
    print("  " + " ".join(info["secret"][i:i + 4] for i in range(0, len(info["secret"]), 4)) + "\n")
    png = dd / "totp_qr.png"
    show_qr(info["otpauth"], png)
    if os.name == "nt" and os.environ.get("TURBO_NO_OPEN") != "1":
        try:
            os.startfile(str(png))  # type: ignore[attr-defined]
        except OSError:
            pass
    print("\n" + t["totp_phone"].format(n=max(1, int(info["expiresIn"]) // 60)))


def main(argv: list[str] | None = None) -> None:
    for stream in (sys.stdout, sys.stderr):   # Vietnamese text in a cp1252 console or a pipe must not crash setup
        try:
            if not stream.isatty():
                stream.reconfigure(encoding="utf-8")
            else:
                stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(prog="turbo_hub")
    ap.add_argument("--lang", choices=["vi", "en"], default=os.environ.get("TURBO_LANG", "vi"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    su = sub.add_parser("setup")
    su.add_argument("--preset", choices=cfgmod.PRESETS)
    su.add_argument("--phone", action=argparse.BooleanOptionalAction, default=None, help="will you pair a phone? (adds LAN)")
    sv = sub.add_parser("serve")
    sv.add_argument("--public-url", help="URL the phone should use (default: first enabled connection)")
    sv.add_argument("--runner", choices=["fake", "agent"], default="agent")
    sv.add_argument("--mcp-config", help="MCP config JSON with desktop-mcp and turbo-browser servers")
    sv.add_argument("--preset", choices=cfgmod.PRESETS, help="override the preset for this run")
    r = sub.add_parser("run")
    r.add_argument("task")
    tp = sub.add_parser("totp")
    tp.add_argument("--rotate", action="store_true", help="make a new secret; the old Authenticator entry stops working")
    for name in ("pair", "devices", "stop", "resume", "verify-audit"):
        sub.add_parser(name)
    rv = sub.add_parser("revoke")
    rv.add_argument("device_id")
    cch = sub.add_parser("cc-hook", help="approve Claude Code permission prompts from the phone or a PC dialog")
    cch.add_argument("action", choices=["install", "uninstall", "status", "print"])
    cch.add_argument("--settings", help="Claude Code settings file (default ~/.claude/settings.json)")
    for p in sub.choices.values():
        p.add_argument("--port", type=int, default=None)
    a = ap.parse_args(argv)
    dd = data_dir()
    if a.cmd == "setup":
        return cmd_setup(a, dd)
    if a.cmd == "cc-hook":
        from . import cc_hook_install as cch_mod
        target = Path(a.settings) if a.settings else None
        if a.action == "install":
            print(f"installed in {cch_mod.install(target)} (restart open Claude Code sessions)")
        elif a.action == "uninstall":
            print(f"removed from {cch_mod.uninstall(target)}")
        elif a.action == "print":
            print(json.dumps({"hooks": {"PermissionRequest": [{"matcher": "*", "hooks": [
                {"type": "command", "command": cch_mod.hook_command(), "timeout": cch_mod.TIMEOUT_SECONDS}]}]}}, indent=2))
        else:
            print("installed" if cch_mod.installed(target) else "not installed")
        return
    cfg = cfgmod.load_config(cfgmod.user_config_path(dd), getattr(a, "preset", None))
    a.port = a.port or cfg["server"]["port"]

    if a.cmd == "serve":
        conns = cfg["server"]["connections"]
        hosts, urls = [], {}
        if "lan" in conns and (ip := lan_ip()):
            hosts.append(ip); urls["lan"] = f"http://{ip}:{a.port}"
        if "tailscale" in conns and (ip := tailscale_ip()):
            hosts.append(ip); urls["tailscale"] = f"http://{ip}:{a.port}"
        urls["local"] = f"http://127.0.0.1:{a.port}"
        if "cloudflare" in conns and cfg["cloudflare"].get("url"):
            urls["cloudflare"] = cfg["cloudflare"]["url"].rstrip("/")
        # a phone can never use 127.0.0.1: prefer the first enabled non-local path for the pairing QR
        public = a.public_url or next((urls[c] for c in conns if c in urls and c != "local"), urls["local"])
        settings = build_settings(cfg, dd, a.runner, public, a.port, a.mcp_config)
        settings.urls = tuple((c, urls[c]) for c in conns if c in urls)
        if a.runner == "fake":   # demos/screenshots must never stream the real desktop
            from .screen import demo_frame
            settings.screen_grabber = demo_frame
        if a.public_url:   # explicit override, e.g. the emulator's 10.0.2.2
            settings.urls = (("local", a.public_url),) + tuple(x for x in settings.urls if x[0] != "local")
        app = create_app(settings)
        socks = bind_sockets(a.port, hosts)
        print(f"preset={cfg['preset']} listening on {[s.getsockname() for s in socks]}, phones use {public}, "
              f"agent={cfg['agent']['mode'] if a.runner == 'agent' else 'fake'}")
        if "cloudflare" in conns:
            print("cloudflare: run `cloudflared tunnel run <name>` pointing at http://127.0.0.1:%d" % a.port)
        uvicorn.Server(uvicorn.Config(app, log_level="warning")).run(sockets=socks)
        return

    if a.cmd == "verify-audit":
        ok, msg = AuditLog(dd / "audit.jsonl").verify()
        print(("OK: " if ok else "BROKEN: ") + msg)
        sys.exit(0 if ok else 1)

    token = SecretStore(dd).admin_token
    if a.cmd == "run":
        cmd_run(a, dd)
    elif a.cmd == "pair":
        info = admin("POST", "/admin/pairing", a.port, token)
        otp = info.pop("otpauth", None)
        info.pop("needs", None)
        text = "turbo-pair:" + base64.urlsafe_b64encode(json.dumps(info, separators=(",", ":")).encode()).decode()
        print("1) Scan this with the phone app (valid %d min), or paste the text below:\n" % cfg["auth"]["pairing_window_minutes"])
        show_qr(text, dd / "pairing_qr.png")
        print("\n" + text + f"\n\nHub key fingerprint: {info['fp']}\ncode: {info['code']}")
        if otp:
            print("\n2) Add this to Google Authenticator (needed to open each session):\n")
            show_qr(otp, dd / "totp_qr.png")
        print(f"\nQR images saved in {dd}")
    elif a.cmd == "totp":
        cmd_totp(a, dd, token, cfg)
    elif a.cmd == "devices":
        print(json.dumps(admin("GET", "/admin/devices", a.port, token), indent=2))
    elif a.cmd == "revoke":
        print(admin("DELETE", f"/admin/devices/{a.device_id}", a.port, token))
    elif a.cmd in ("stop", "resume"):
        print(admin("POST", f"/admin/{a.cmd}", a.port, token))


if __name__ == "__main__":
    main()
