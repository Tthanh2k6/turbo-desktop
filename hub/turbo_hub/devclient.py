"""A simulated phone, used by tests and for emulator-less checks. Mirrors what the Android app does."""
from __future__ import annotations

import base64
import json
import secrets
import time
from typing import Callable

from . import crypto, totp


class DevClient:
    def __init__(self, http, hub_pub: str | None = None, clock: Callable[[], float] = time.time, name: str = "test-phone"):
        self.http, self.clock, self.name = http, clock, name
        self.key = crypto.generate_key()
        self.auth_key = crypto.generate_key()   # stands in for the biometric-gated Keystore key
        self.pub = crypto.pub_to_b64(self.key.public_key())
        self.auth_pub = crypto.pub_to_b64(self.auth_key.public_key())
        self.device_id = crypto.device_id_for(self.pub)
        self.hub_pub = hub_pub
        self.session: str | None = None

    def _headers(self, method: str, path_qs: str, body: bytes, ts=None, nonce=None, strong=False, device=True) -> dict:
        ts = str(int(self.clock())) if ts is None else str(ts)
        nonce = nonce or secrets.token_hex(12)
        msg = crypto.canonical_request(method, path_qs, body, ts, nonce)
        h = {"X-Ts": ts, "X-Nonce": nonce, "X-Sig": crypto.sign(self.key, msg), "Content-Type": "application/json"}
        if device:
            h["X-Device"] = self.device_id
        if strong:
            h["X-Auth-Sig"] = crypto.sign(self.auth_key, msg)
        if self.session:
            h["X-Session"] = self.session
        return h

    def request(self, method: str, path_qs: str, obj=None, *, strong=False, verify_resp=True, **hdr):
        body = json.dumps(obj, separators=(",", ":")).encode() if obj is not None else b""
        h = self._headers(method, path_qs, body, strong=strong, **hdr)
        r = self.http.request(method, path_qs, content=body, headers=h)
        if verify_resp and r.status_code < 400 and self.hub_pub and "x-hub-sig" in r.headers:
            msg = crypto.canonical_response(r.status_code, path_qs, r.content, r.headers["x-hub-ts"], h["X-Nonce"])
            assert crypto.verify(crypto.pub_from_b64(self.hub_pub), msg, r.headers["x-hub-sig"]), "hub signature invalid"
        return r

    def pair(self, code: str, **hdr):
        body = {"code": code, "name": self.name, "pub": self.pub, "authPub": self.auth_pub}
        raw = json.dumps(body, separators=(",", ":")).encode()
        h = self._headers("POST", "/pair", raw, strong=True, device=False, **hdr)
        return self.http.post("/pair", content=raw, headers=h)

    def start_session(self, secret: bytes | None = None, code: str | None = None, step_offset: int = 0):
        if code is None:
            code = totp.code_at(secret, int(self.clock() // 30) + step_offset)
        r = self.request("POST", "/session/start", {"totp": code}, strong=True)
        if r.status_code == 200:
            self.session = r.json()["sessionId"]
        return r
