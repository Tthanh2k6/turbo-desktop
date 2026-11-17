"""FastAPI app: pairing, signed requests, sessions, tasks, approvals, STOP, audit."""
from __future__ import annotations

import asyncio
import json
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from . import crypto, reaper, screen, totp
from .audit import AuditLog
from contextlib import asynccontextmanager

from .bridge import DesktopBridge
from .manager import PcLocked, TaskManager, _today
from .runners import FakeRunner, RunnerFactory
from .store import SecretStore

NONCE_TTL = 180
SESSION_TTL = 7200
PAIR_CODE_TTL = 300
PAIR_MAX_ATTEMPTS = 5
MAX_BODY = 64 * 1024
LOCK_STRIKES = 5
LOCK_WINDOW = 600
LOCK_SECONDS = 900
PROXY_HEADERS = ("cf-connecting-ip", "cf-ray", "x-forwarded-for", "cf-access-jwt-assertion")


@dataclass
class Settings:
    data_dir: Path
    runner_factory: RunnerFactory = FakeRunner
    approval_timeout: float = 120.0
    session_ttl: float = SESSION_TTL
    pair_code_ttl: float = PAIR_CODE_TTL
    clock: Callable[[], float] = time.time
    loopback_hosts: tuple[str, ...] = ("127.0.0.1", "::1")
    public_url: str = "http://127.0.0.1:8750"
    classifier: Callable[[dict], bool] | None = None
    totp_required: bool = True
    approval_engine: str = "hub"
    policy: dict = field(default_factory=dict)   # shown read-only on the phone (Settings screen)
    urls: tuple = ()   # ((name, url), ...) in connection order, shown to the phone at pairing
    desktop_state_dir: Path | None = None
    persist_sessions: bool = False
    biometric_required: bool = True
    connections: tuple[str, ...] = ("local", "lan", "tailscale", "cloudflare")
    require_access_header: bool = False
    system_state: Callable | None = None   # async () -> dict (desktop-mcp system_state)
    internal_token: str = field(default_factory=lambda: secrets.token_urlsafe(24))
    remote_task_lock: str = "whole_task"
    max_task_minutes: int = 15
    screen_view_enabled: bool = True
    screen_view_max_fps: float = 2.0
    secret_title_patterns: tuple[str, ...] = tuple(screen.SECRET_TITLE_PATTERNS)
    screen_grabber: Callable | None = None
    window_enumerator: Callable | None = None


@dataclass
class Ctx:
    device_id: str
    nonce: str
    ts: str
    path_qs: str
    session: str | None = None


@dataclass
class PairingState:
    code: str
    exp: float
    attempts: int = 0


@dataclass
class Session:
    id: str
    device_id: str
    exp: float


@dataclass
class State:
    settings: Settings
    store: SecretStore
    audit: AuditLog
    manager: TaskManager
    nonces: dict[tuple[str, str], float] = field(default_factory=dict)
    sessions: dict[str, Session] = field(default_factory=dict)
    pairing: PairingState | None = None
    strikes: dict[str, list[float]] = field(default_factory=dict)
    locked_until: dict[str, float] = field(default_factory=dict)
    task_tokens: dict[str, str] = field(default_factory=dict)
    started: int = 0
    totp_window_exp: float = 0.0   # enrolment window: the phone may fetch the otpauth secret once until then
    screen_last_at: dict[str, float] = field(default_factory=dict)
    screen_audit_at: dict[str, float] = field(default_factory=dict)
    bridge: DesktopBridge | None = None


def create_app(settings: Settings) -> FastAPI:
    store = SecretStore(settings.data_dir)
    audit = AuditLog(settings.data_dir / "audit.jsonl")
    thumbs = settings.data_dir / "thumbs"
    thumbs.mkdir(parents=True, exist_ok=True)
    manager = TaskManager(audit, settings.runner_factory, approval_timeout=settings.approval_timeout,
                          clock=settings.clock, approval_required=settings.classifier, thumbs_dir=thumbs,
                          system_state=settings.system_state, usage_path=settings.data_dir / "usage.json",
                          tasks_path=settings.data_dir / "tasks.jsonl",
                          engine=settings.approval_engine)
    st = State(settings, store, audit, manager)
    st.started = int(settings.clock())
    sessions_file = settings.data_dir / "sessions.dpapi"
    if settings.persist_sessions and sessions_file.exists():
        from . import dpapi
        for sid, d in json.loads(dpapi.unprotect(sessions_file.read_bytes())).items():
            if d["exp"] > settings.clock():
                st.sessions[sid] = Session(sid, d["device"], d["exp"])

    def save_sessions() -> None:
        if settings.persist_sessions:
            from . import dpapi
            raw = json.dumps({k: {"device": v.device_id, "exp": v.exp} for k, v in st.sessions.items()}).encode()
            sessions_file.write_bytes(dpapi.protect(raw))
    activity = [0.0]

    def lock_remote_task_cfg() -> str:
        if settings.remote_task_lock != "whole_task":
            return settings.remote_task_lock
        return str(settings.policy.get("lockRemoteTask", settings.remote_task_lock))

    def screen_view_cfg() -> dict:
        sv = settings.policy.get("screenView") or {}
        if not settings.screen_view_enabled:
            enabled = False
        elif "enabled" in sv:
            enabled = bool(sv["enabled"])
        elif settings.policy.get("preset") == "strict":
            enabled = False
        else:
            enabled = True
        fps = sv.get("maxFps", settings.screen_view_max_fps)
        fps_val = int(fps) if float(fps).is_integer() else float(fps)
        return {"enabled": enabled, "maxFps": fps_val}

    bridge = DesktopBridge(
        manager, settings.desktop_state_dir, settings.clock, lambda: activity[0],
        remote_task=lock_remote_task_cfg,
        max_task_minutes=lambda: settings.max_task_minutes,
    ) if settings.desktop_state_dir else None
    st.bridge = bridge

    pid_file = settings.data_dir / "agent.pid"

    async def track_agent():
        last = None
        while True:
            pid = manager.agent_pid
            if pid != last:
                last = pid
                reaper.record(pid_file, pid)
            await asyncio.sleep(1)

    @asynccontextmanager
    async def lifespan(_app):
        if reaper.reap(pid_file):
            audit.append("agent_reaped", {"why": "leftover agent from a previous hub run"})
        tasks = [asyncio.create_task(track_agent())] + ([asyncio.create_task(bridge.run())] if bridge else [])
        try:
            yield
        finally:
            for t in tasks:
                t.cancel()
            if manager._runner is not None:
                await manager._runner.kill()      # clean shutdown never leaves the agent running
            reaper.record(pid_file, None)

    app = FastAPI(title="turbo-desktop hub", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.hub = st
    now = settings.clock

    # ------------------------------------------------------------ helpers
    def path_qs(request: Request) -> str:
        q = request.url.query
        return request.url.path + (("?" + q) if q else "")

    def sign_response(ctx_nonce: str, ctx_path: str, status: int, body: bytes) -> dict[str, str]:
        ts = str(int(now()))
        sig = crypto.sign(store.hub_key, crypto.canonical_response(status, ctx_path, body, ts, ctx_nonce))
        return {"X-Hub-Ts": ts, "X-Hub-Sig": sig}

    def reply(ctx: Ctx, obj, status: int = 200) -> Response:
        body = json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode()
        return Response(body, status_code=status, media_type="application/json",
                        headers=sign_response(ctx.nonce, ctx.path_qs, status, body))

    def source(request: Request) -> str:
        # behind cloudflared the TCP peer is always loopback, the real client is in Cf-Connecting-Ip
        return request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "?")

    def via_proxy(request: Request) -> bool:
        return any(h in request.headers for h in PROXY_HEADERS)

    def guard(request: Request) -> None:
        """First thing every unauthenticated-or-signed route does: lockout and size limits, before any crypto."""
        if via_proxy(request):
            if "cloudflare" not in settings.connections:
                raise HTTPException(403, "tunnel access is not enabled")
            if settings.require_access_header and "cf-access-jwt-assertion" not in request.headers:
                raise HTTPException(403, "Cloudflare Access login required")
        src = source(request)
        until = st.locked_until.get(src, 0)
        if until > now():
            raise HTTPException(429, "locked out, try later")
        if until:
            st.locked_until.pop(src, None)
        if int(request.headers.get("content-length") or 0) > MAX_BODY:
            raise HTTPException(413, "body too large")

    def strike(request: Request, why: str) -> None:
        src, t = source(request), now()
        hits = [x for x in st.strikes.get(src, []) if x > t - LOCK_WINDOW] + [t]
        st.strikes[src] = hits
        if len(hits) >= LOCK_STRIKES:
            st.locked_until[src] = t + LOCK_SECONDS
            st.strikes.pop(src, None)
            audit.append("lockout", {"source": src, "seconds": LOCK_SECONDS, "last": why})
            asyncio.get_running_loop().create_task(
                manager.emit({"type": "hub_alert", "what": f"source {src} locked out for 15 min ({why})"}))

    def reject(request: Request, status: int, why: str, device: str | None = None) -> HTTPException:
        audit.append("rejected", {"why": why, "device": device, "path": request.url.path, "client": source(request)})
        if status in (401, 403):
            strike(request, why)
        return HTTPException(status, why)

    def prune_nonces() -> None:
        t = now()
        for k in [k for k, exp in st.nonces.items() if exp < t]:
            del st.nonces[k]

    def check_fresh(request: Request, ts: str, nonce: str) -> None:
        try:
            if abs(now() - int(ts)) > crypto.MAX_SKEW_SECONDS:
                raise reject(request, 401, "stale timestamp")
            if int(ts) < st.started:   # nonces are in memory only: nothing signed before this start can be replayed
                raise reject(request, 401, "stale timestamp (before hub start)")
        except ValueError:
            raise reject(request, 401, "bad timestamp")
        if not nonce or len(nonce) > 128:
            raise reject(request, 401, "bad nonce")

    def claim_nonce(request: Request, device_id: str, nonce: str) -> None:
        prune_nonces()
        key = (device_id, nonce)
        if key in st.nonces:
            raise reject(request, 401, "replayed nonce", device_id)
        st.nonces[key] = now() + NONCE_TTL

    async def signed(request: Request) -> Ctx:
        h = request.headers
        dev_id, ts, nonce, sig = h.get("x-device", ""), h.get("x-ts", ""), h.get("x-nonce", ""), h.get("x-sig", "")
        guard(request)
        device = store.get_device(dev_id)
        if device is None and not (dev_id and len(dev_id) <= 32):
            raise reject(request, 401, "unknown device", dev_id[:16])
        body = await request.body()
        if len(body) > MAX_BODY:
            raise HTTPException(413, "body too large")
        check_fresh(request, ts, nonce)
        if device is None:
            await manager.emit({"type": "hub_alert", "what": "unpaired device rejected", "device": dev_id[:16]})
            raise reject(request, 401, "unknown device", dev_id[:16])
        msg = crypto.canonical_request(request.method, path_qs(request), body, ts, nonce)
        if not crypto.verify(crypto.pub_from_b64(device.pub), msg, sig):
            raise reject(request, 401, "bad signature", dev_id)
        claim_nonce(request, dev_id, nonce)
        return Ctx(dev_id, nonce, ts, path_qs(request))

    async def strong(request: Request, ctx: Ctx = Depends(signed)) -> Ctx:
        """Second signature from the biometric-gated key, over the same canonical request."""
        if not settings.biometric_required:
            return ctx
        device = store.get_device(ctx.device_id)
        msg = crypto.canonical_request(request.method, ctx.path_qs, await request.body(), ctx.ts, ctx.nonce)
        sig = request.headers.get("x-auth-sig", "")
        if device is None or not device.auth_pub or not crypto.verify(crypto.pub_from_b64(device.auth_pub), msg, sig):
            raise reject(request, 401, "missing or bad biometric signature", ctx.device_id)
        return ctx

    async def in_session(request: Request, ctx: Ctx = Depends(signed)) -> Ctx:
        sid = request.headers.get("x-session", "")
        s = st.sessions.get(sid)
        if s is None or s.device_id != ctx.device_id:
            raise reject(request, 401, "no session", ctx.device_id)
        if s.exp < now():
            st.sessions.pop(sid, None)
            raise reject(request, 401, "session expired", ctx.device_id)
        ctx.session = sid
        activity[0] = now()   # a phone is talking to us: the desktop MCP may route approvals here
        return ctx

    def require_admin(request: Request) -> None:
        host = request.client.host if request.client else ""
        if host not in settings.loopback_hosts:
            raise HTTPException(403, "admin is local only")
        if via_proxy(request):
            raise HTTPException(403, "admin is not reachable through a proxy or tunnel")
        if not secrets.compare_digest(request.headers.get("x-admin-token", ""), store.admin_token):
            raise HTTPException(403, "bad admin token")

    # ------------------------------------------------------------ pairing
    def new_pairing() -> dict:
        code = f"{secrets.randbelow(10**6):06d}"
        st.pairing = PairingState(code, now() + settings.pair_code_ttl)
        audit.append("pairing_created", {"expires_in": settings.pair_code_ttl})
        return {"v": 1, "url": settings.public_url, "hubKey": store.hub_pub_b64, "code": code,
                "exp": int(st.pairing.exp), "fp": crypto.fingerprint(store.hub_pub_b64),
                "urls": [{"name": n, "url": u} for n, u in settings.urls],
                # NOT part of the phone QR: shown as a separate QR for Google Authenticator
                "otpauth": totp.otpauth_uri(store.totp_secret) if settings.totp_required else None,
                "needs": {"totp": settings.totp_required, "biometric": settings.biometric_required}}

    def open_enroll_window() -> int:
        st.totp_window_exp = now() + settings.pair_code_ttl
        audit.append("totp_enroll_opened", {"expires_in": settings.pair_code_ttl})
        return int(settings.pair_code_ttl)

    @app.post("/admin/totp")
    async def admin_totp(request: Request):
        require_admin(request)
        if not settings.totp_required:
            raise HTTPException(409, "totp is off for this preset")
        try:
            raw = await request.body()
            rotate = bool(json.loads(raw).get("rotate")) if raw.strip() else False
        except (ValueError, AttributeError):
            raise HTTPException(400, "bad json")
        if rotate:
            store.rotate_totp()
            audit.append("totp_rotated", {})
        expires = open_enroll_window()
        return {"otpauth": totp.otpauth_uri(store.totp_secret), "secret": totp.b32(store.totp_secret),
                "expiresIn": expires}

    @app.post("/admin/pairing")
    async def admin_pairing(request: Request):
        require_admin(request)
        return new_pairing()

    @app.get("/admin/devices")
    async def admin_devices(request: Request):
        require_admin(request)
        return [{"id": d.id, "name": d.name, "paired_at": d.paired_at} for d in store.list_devices()]

    def revoke(device_id: str) -> bool:
        ok = store.remove_device(device_id)
        for sid in [k for k, s in st.sessions.items() if s.device_id == device_id]:
            del st.sessions[sid]
        if ok:
            audit.append("device_revoked", {"device": device_id})
        return ok

    @app.delete("/admin/devices/{device_id}")
    async def admin_revoke(device_id: str, request: Request):
        require_admin(request)
        if not revoke(device_id):
            raise HTTPException(404, "no such device")
        await manager.emit({"type": "device_revoked", "device": device_id})
        return {"ok": True}

    @app.post("/admin/tasks")
    async def admin_task(request: Request):
        require_admin(request)
        try:
            task = await manager.start_task(str((await request.json())["text"]), "local-admin")
        except RuntimeError:
            raise HTTPException(423, "stopped")
        except PcLocked as e:
            raise HTTPException(423, str(e))
        except ValueError as e:
            raise HTTPException(409, str(e))
        return {"taskId": task.id}

    @app.get("/admin/events")
    async def admin_events(request: Request, since: int = 0):
        require_admin(request)
        activity[0] = now()
        return manager.events_since(since)[:500]

    @app.post("/admin/approvals/{approval_id}")
    async def admin_decide(approval_id: str, request: Request):
        require_admin(request)
        decision = str((await request.json())["decision"])
        res = manager.resolve(approval_id, decision)
        if res == "ok":
            audit.append("approval_decision_by", {"approval": approval_id, "device": "local-admin", "decision": decision})
        return {"result": res}

    @app.post("/admin/stop")
    async def admin_stop(request: Request):
        require_admin(request)
        await manager.stop("pc-admin")
        return {"stopped": True}

    @app.post("/admin/resume")
    async def admin_resume(request: Request):
        require_admin(request)
        await manager.resume("pc-admin")
        return {"stopped": False}

    @app.get("/admin/status")
    async def admin_status(request: Request):
        require_admin(request)
        ok, msg = audit.verify()
        return {"stopped": manager.stopped, "devices": len(store.list_devices()), "audit_ok": ok, "audit": msg,
                "running": bool(manager.running_task()),
                "agent_pid": manager.agent_pid, "paused": manager.paused}

    @app.post("/pair")
    async def pair(request: Request):
        guard(request)
        if via_proxy(request):
            raise HTTPException(403, "pairing is local only (not through a tunnel)")
        body = await request.body()
        if len(body) > MAX_BODY:
            raise HTTPException(413, "body too large")
        h = request.headers
        ts, nonce, sig = h.get("x-ts", ""), h.get("x-nonce", ""), h.get("x-sig", "")
        p = st.pairing
        if p is None or p.exp < now():
            st.pairing = None
            raise reject(request, 403, "pairing failed", "no active code")
        p.attempts += 1
        if p.attempts > PAIR_MAX_ATTEMPTS:
            st.pairing = None
            raise reject(request, 403, "pairing failed", "too many attempts, code burned")
        try:
            data = json.loads(body)
            code, name, pub = str(data["code"]), str(data.get("name", "phone")), str(data["pub"])
            auth_pub = str(data.get("authPub") or "")
            pub_key = crypto.pub_from_b64(pub)
            auth_key = crypto.pub_from_b64(auth_pub) if auth_pub else None
            if settings.biometric_required and auth_key is None:
                raise KeyError("authPub")
        except (ValueError, KeyError, TypeError):
            raise reject(request, 400, "bad pairing request")
        check_fresh(request, ts, nonce)
        if not secrets.compare_digest(code.encode(), p.code.encode()):
            raise reject(request, 403, "pairing failed", "wrong code")
        msg = crypto.canonical_request("POST", "/pair", body, ts, nonce)
        if not crypto.verify(pub_key, msg, sig) or (
                auth_key is not None and not crypto.verify(auth_key, msg, h.get("x-auth-sig", ""))):
            raise reject(request, 403, "pairing failed", "bad signature")
        claim_nonce(request, "pairing", nonce)
        st.pairing = None  # one-time
        dev = store.add_device(name, pub, now(), auth_pub)
        audit.append("paired", {"device": dev.id, "name": dev.name})
        await manager.emit({"type": "paired", "device": dev.id, "name": dev.name})
        enroll = settings.totp_required
        if enroll:
            open_enroll_window()   # pairing is local and physical: the phone may now fetch the Authenticator key
        return reply(Ctx(dev.id, nonce, ts, "/pair"),
                     {"deviceId": dev.id, "hubPub": store.hub_pub_b64, "totpEnroll": enroll,
                      "needs": {"totp": settings.totp_required, "biometric": settings.biometric_required}})

    @app.get("/hello")
    async def hello(ctx: Ctx = Depends(signed)):
        """Signed liveness check without a session (used while waking the PC and to pick a transport)."""
        return reply(ctx, {"ok": True, "now": int(now())})

    @app.get("/policy")
    async def get_policy(ctx: Ctx = Depends(signed)):
        """What the app must ask for before it can open a session (no session needed)."""
        return reply(ctx, {"preset": settings.policy.get("preset", ""),
                           "needs": {"totp": settings.totp_required, "biometric": settings.biometric_required},
                           "sessionHours": settings.policy.get("sessionHours", settings.session_ttl / 3600),
                           "screenView": screen_view_cfg(),
                           "lockRemoteTask": lock_remote_task_cfg()})

    def not_proxied(request: Request) -> None:
        if via_proxy(request):
            raise HTTPException(403, "totp enrolment is local only (not through a tunnel)")

    @app.get("/totp/enroll")
    async def totp_enroll(_: None = Depends(not_proxied), ctx: Ctx = Depends(strong)):
        if not settings.totp_required or st.totp_window_exp <= now():
            st.totp_window_exp = 0.0
            return reply(ctx, {"detail": "enrollment closed"}, 403)
        st.totp_window_exp = 0.0   # one-shot
        audit.append("totp_enroll_fetched", {"device": ctx.device_id})
        return reply(ctx, {"otpauth": totp.otpauth_uri(store.totp_secret), "secret": totp.b32(store.totp_secret),
                           "issuer": "turbo-desktop", "account": "pc", "digits": totp.DIGITS, "period": totp.PERIOD})

    # ------------------------------------------------------------ session
    @app.post("/session/start")
    async def session_start(request: Request, ctx: Ctx = Depends(strong)):
        if settings.totp_required:
            try:
                code = str(json.loads(await request.body())["totp"])
            except (ValueError, KeyError, TypeError):
                raise reject(request, 401, "totp required", ctx.device_id)
            step = totp.verify(store.totp_secret, code, now(), store.totp_last_step)
            if step is None:
                raise reject(request, 401, "bad or reused totp", ctx.device_id)
            store.set_totp_last_step(step)
        s = Session(secrets.token_urlsafe(24), ctx.device_id, now() + settings.session_ttl)
        st.sessions[s.id] = s
        save_sessions()
        audit.append("session_start", {"device": ctx.device_id})
        return reply(ctx, {"sessionId": s.id, "expiresAt": int(s.exp), "stopped": manager.stopped})

    @app.post("/unpair")
    async def unpair(ctx: Ctx = Depends(in_session)):
        revoke(ctx.device_id)
        return reply(ctx, {"ok": True})

    @app.get("/status")
    async def status(ctx: Ctx = Depends(in_session)):
        t = manager.running_task()
        sv = screen_view_cfg()
        lrt = lock_remote_task_cfg()
        pol = {**settings.policy, "screenView": sv, "lockRemoteTask": lrt}
        return reply(ctx, {"stopped": manager.stopped, "running": t.id if t else None,
                           "paused": manager.paused, "policy": pol,
                           "screenView": sv, "lockRemoteTask": lrt,
                           "inputLock": manager.input_lock, "indicator": manager.indicator,
                           "usage": {"session": manager.session_usage,
                                     "today": manager.daily_usage.get(_today(now()), {})},
                           "pendingApprovals": len(manager.pending_approvals()), "now": int(now())})

    @app.get("/screen.jpg")
    async def get_screen_jpg(w: int = 960, q: int = 60, ctx: Ctx = Depends(in_session)):
        sv = screen_view_cfg()
        if not sv["enabled"]:
            return reply(ctx, {"detail": "screen view is off"}, 403)
        t = now()
        max_fps = float(sv["maxFps"])
        min_interval = (1.0 / max_fps) if max_fps > 0 else 0.0
        last = st.screen_last_at.get(ctx.device_id)
        if last is not None and t - last < min_interval:
            return reply(ctx, {"detail": "rate limit exceeded"}, 429)
        st.screen_last_at[ctx.device_id] = t
        jpeg, redacted = await asyncio.to_thread(   # capture + encode off the event loop
            screen.capture_screen_jpeg,
            max_width=w,
            quality=q,
            patterns=settings.secret_title_patterns,
            grabber=settings.screen_grabber,
            window_enumerator=settings.window_enumerator,
        )
        last_audit = st.screen_audit_at.get(ctx.device_id)
        if last_audit is None or t - last_audit >= 60.0:
            st.screen_audit_at[ctx.device_id] = t
            audit.append("screen_view", {"device": ctx.device_id, "redacted": redacted})
        if settings.desktop_state_dir:
            settings.desktop_state_dir.mkdir(parents=True, exist_ok=True)
            tmp = settings.desktop_state_dir / "screen_view.json.tmp"
            tmp.write_text(json.dumps({"until": t + 5}), "utf-8")
            tmp.replace(settings.desktop_state_dir / "screen_view.json")
        headers = {"X-Redacted": str(redacted), **sign_response(ctx.nonce, ctx.path_qs, 200, jpeg)}
        return Response(jpeg, status_code=200, media_type="image/jpeg", headers=headers)

    # ------------------------------------------------------------ tasks
    @app.post("/tasks")
    async def post_task(request: Request, ctx: Ctx = Depends(in_session)):
        try:
            text = str(json.loads(await request.body())["text"]).strip()
        except (ValueError, KeyError, TypeError):
            raise HTTPException(400, "text required")
        if not text or len(text) > 4000:
            raise HTTPException(400, "text empty or too long")
        if running := manager.running_task():
            return reply(ctx, {"detail": "busy", "running": running.id}, 409)
        try:
            task = await manager.start_task(text, ctx.device_id)
        except RuntimeError:
            return reply(ctx, {"error": "stopped"}, 423)
        except PcLocked as e:
            return reply(ctx, {"error": "pc_locked", "message": str(e)}, 423)
        except ValueError:
            running = manager.running_task()
            return reply(ctx, {"detail": "busy", "running": running.id if running else None}, 409)
        return reply(ctx, {"taskId": task.id})

    @app.get("/tasks")
    async def get_tasks(ctx: Ctx = Depends(in_session)):
        return reply(ctx, [{"id": t.id, "text": t.text, "status": t.status, "startedAt": int(t.started_at),
                            "finishedAt": int(t.finished_at) if t.finished_at else None}
                           for t in sorted(manager.tasks.values(), key=lambda x: -x.started_at)][:50])

    # ------------------------------------------------------------ events
    @app.get("/events/poll")
    async def events_poll(since: int = 0, ctx: Ctx = Depends(in_session)):
        return reply(ctx, manager.events_since(since)[:500])

    def sse_frame(ev: dict) -> bytes:
        payload = json.dumps(ev, separators=(",", ":"), ensure_ascii=False)
        sig = crypto.sign(store.hub_key, crypto.canonical_event(payload))
        return ("data: " + json.dumps({"p": payload, "sig": sig}, separators=(",", ":")) + "\n\n").encode()

    @app.get("/events")
    async def events(request: Request, since: int = 0, ctx: Ctx = Depends(in_session)):
        q = manager.subscribe()
        backlog = manager.events_since(since)

        async def gen():
            try:
                last = since
                for ev in backlog:
                    last = ev["seq"]
                    yield sse_frame(ev)
                while True:
                    try:
                        ev = await asyncio.wait_for(q.get(), 15)
                    except asyncio.TimeoutError:
                        yield b": hb\n\n"
                        s = st.sessions.get(ctx.session or "")
                        if s is None or s.exp < now() or await request.is_disconnected():
                            return
                        continue
                    if ev["seq"] > last:
                        last = ev["seq"]
                        yield sse_frame(ev)
            finally:
                manager.unsubscribe(q)

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no",
                                          **sign_response(ctx.nonce, ctx.path_qs, 200, b"")})

    # ------------------------------------------------------------ approvals
    @app.get("/approvals")
    async def approvals(ctx: Ctx = Depends(in_session)):
        return reply(ctx, [{"approvalId": a.id, "taskId": a.task_id, "tool": a.event.get("tool"),
                            "window": a.event.get("window"), "control": a.event.get("control"),
                            "action": a.event.get("action"), "crop_png_b64": a.event.get("crop_png_b64"),
                            "expiresAt": a.expires_at} for a in manager.pending_approvals()])

    @app.post("/approvals/{approval_id}")
    async def decide(approval_id: str, request: Request, ctx: Ctx = Depends(in_session),
                     _strong: Ctx = Depends(strong)):
        try:
            decision = str(json.loads(await request.body())["decision"])
            res = manager.resolve(approval_id, decision)
        except (ValueError, KeyError, TypeError):
            raise HTTPException(400, "decision must be allow or deny")
        if res == "unknown":
            raise HTTPException(404, "no such approval")
        if res == "already":
            return reply(ctx, {"error": "already decided"}, 409)
        audit.append("approval_decision_by", {"approval": approval_id, "device": ctx.device_id, "decision": decision})
        return reply(ctx, {"ok": True})

    # ------------------------------------------------------------ STOP / audit
    @app.post("/stop")
    async def stop(ctx: Ctx = Depends(in_session)):
        await manager.stop(ctx.device_id)
        return reply(ctx, {"stopped": True})

    @app.post("/takeover")
    async def takeover(ctx: Ctx = Depends(in_session)):
        await manager.takeover(ctx.device_id)
        return reply(ctx, {"paused": True})

    @app.post("/resume")
    async def resume(ctx: Ctx = Depends(in_session)):
        await manager.resume(ctx.device_id)
        return reply(ctx, {"stopped": False})

    @app.get("/audit")
    async def get_audit(limit: int = 50, ctx: Ctx = Depends(in_session)):
        ok, msg = audit.verify()
        return reply(ctx, {"chainOk": ok, "chainInfo": msg, "entries": audit.read(max(1, min(limit, 200)))})

    @app.get("/report")
    async def get_report(days: str = "7", ctx: Ctx = Depends(in_session)):
        if days not in ("1", "7", "30"):
            return reply(ctx, {"detail": "days must be 1, 7, or 30"}, 400)
        return reply(ctx, manager.report(int(days)))

    # ------------------------------------------------------------ claude permission-prompt bridge
    @app.post("/internal/approve")
    async def internal_approve(request: Request):
        host = request.client.host if request.client else ""
        if host not in settings.loopback_hosts or via_proxy(request):
            raise HTTPException(403, "local only")
        tok = request.headers.get("x-task-token", "")
        if not secrets.compare_digest(tok, settings.internal_token):
            raise HTTPException(403, "bad token")
        task = manager.running_task()
        if task is None:
            raise HTTPException(409, "no running task")
        data = await request.json()
        call = {"tool": data.get("tool_name"), "input": data.get("input") or {}}
        allowed = await manager.gate(task.id, call)
        return {"behavior": "allow", "updatedInput": call["input"]} if allowed else \
               {"behavior": "deny", "message": "Denied by the owner (or timed out / STOP)."}

    return app
