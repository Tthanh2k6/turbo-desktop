"""Hub secrets: hub private key, paired devices, admin token. All encrypted with DPAPI at rest."""
from __future__ import annotations

import json
import os
import secrets
import threading
from dataclasses import dataclass, asdict
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from . import crypto, dpapi


@dataclass
class Device:
    id: str
    name: str
    pub: str  # b64 SPKI, plain device key (ordinary signed requests)
    paired_at: float
    auth_pub: str = ""  # b64 SPKI, biometric-gated key (session start, approvals)


def _atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


class SecretStore:
    def __init__(self, data_dir: Path):
        self.dir = data_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.hub_key = self._load_or_create_key()
        self.hub_pub_b64 = crypto.pub_to_b64(self.hub_key.public_key())
        self.admin_token = self._load_or_create_admin_token()
        self._devices: dict[str, Device] = self._load_devices()
        self.totp_secret, self.totp_last_step = self._load_totp()

    def _load_or_create_key(self) -> ec.EllipticCurvePrivateKey:
        p = self.dir / "hub_key.dpapi"
        if p.exists():
            pem = dpapi.unprotect(p.read_bytes())
            return serialization.load_pem_private_key(pem, None)  # type: ignore[return-value]
        key = crypto.generate_key()
        pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption())
        _atomic_write(p, dpapi.protect(pem))
        return key

    def _load_or_create_admin_token(self) -> str:
        p = self.dir / "admin_token.dpapi"
        if p.exists():
            return dpapi.unprotect(p.read_bytes()).decode()
        tok = secrets.token_urlsafe(32)
        _atomic_write(p, dpapi.protect(tok.encode()))
        return tok

    def _load_devices(self) -> dict[str, Device]:
        p = self.dir / "devices.dpapi"
        if not p.exists():
            return {}
        raw = json.loads(dpapi.unprotect(p.read_bytes()))
        return {d["id"]: Device(**d) for d in raw}

    def _save_devices(self) -> None:
        raw = json.dumps([asdict(d) for d in self._devices.values()]).encode()
        _atomic_write(self.dir / "devices.dpapi", dpapi.protect(raw))

    def add_device(self, name: str, pub_b64: str, now: float, auth_pub_b64: str) -> Device:
        crypto.pub_from_b64(pub_b64)  # validate
        if auth_pub_b64:
            crypto.pub_from_b64(auth_pub_b64)
        dev = Device(crypto.device_id_for(pub_b64), name[:60], pub_b64, now, auth_pub_b64)
        with self._lock:
            self._devices[dev.id] = dev
            self._save_devices()
        return dev

    def get_device(self, device_id: str) -> Device | None:
        return self._devices.get(device_id)

    def list_devices(self) -> list[Device]:
        return list(self._devices.values())

    def remove_device(self, device_id: str) -> bool:
        with self._lock:
            ok = self._devices.pop(device_id, None) is not None
            if ok:
                self._save_devices()
            return ok

    # TOTP (Google Authenticator compatible); secret and last accepted step live in one DPAPI file
    def _load_totp(self) -> tuple[bytes, int]:
        p = self.dir / "totp.dpapi"
        if p.exists():
            d = json.loads(dpapi.unprotect(p.read_bytes()))
            return bytes.fromhex(d["secret"]), int(d["last_step"])
        secret = secrets.token_bytes(20)
        self._write_totp(secret, 0)
        return secret, 0

    def _write_totp(self, secret: bytes, last_step: int) -> None:
        raw = json.dumps({"secret": secret.hex(), "last_step": last_step}).encode()
        _atomic_write(self.dir / "totp.dpapi", dpapi.protect(raw))

    def set_totp_last_step(self, step: int) -> None:
        with self._lock:
            self.totp_last_step = step
            self._write_totp(self.totp_secret, step)

    def rotate_totp(self) -> bytes:
        """New secret, step counter back to 0: the old Authenticator entry stops working at once."""
        secret = secrets.token_bytes(20)
        with self._lock:
            self.totp_secret, self.totp_last_step = secret, 0
            self._write_totp(secret, 0)
        return secret
