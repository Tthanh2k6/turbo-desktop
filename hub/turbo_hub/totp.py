"""RFC 6238 TOTP (SHA1, 6 digits, 30 s) compatible with Google Authenticator."""
from __future__ import annotations

import base64
import hashlib
import hmac
import struct
from urllib.parse import quote

PERIOD = 30
DIGITS = 6


def code_at(secret: bytes, step: int) -> str:
    mac = hmac.new(secret, struct.pack(">Q", step), hashlib.sha1).digest()
    off = mac[-1] & 0x0F
    num = (struct.unpack(">I", mac[off:off + 4])[0] & 0x7FFFFFFF) % 10**DIGITS
    return f"{num:0{DIGITS}d}"


def verify(secret: bytes, code: str, now: float, last_used_step: int, window: int = 1) -> int | None:
    """Return the matched step, or None. Steps <= last_used_step are rejected (no reuse)."""
    if not (len(code) == DIGITS and code.isdigit()):
        return None
    cur = int(now // PERIOD)
    for step in range(cur - window, cur + window + 1):
        if step > last_used_step and hmac.compare_digest(code_at(secret, step), code):
            return step
    return None


def b32(secret: bytes) -> str:
    return base64.b32encode(secret).decode().rstrip("=")


def otpauth_uri(secret: bytes, account: str = "pc", issuer: str = "turbo-desktop") -> str:
    return (f"otpauth://totp/{quote(issuer)}:{quote(account)}?secret={b32(secret)}&issuer={quote(issuer)}"
            f"&algorithm=SHA1&digits={DIGITS}&period={PERIOD}")
