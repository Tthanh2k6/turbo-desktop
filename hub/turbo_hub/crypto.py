"""Canonical strings and ECDSA P-256 helpers shared with the Android client.

All public keys travel as base64 (standard alphabet) of X.509 SubjectPublicKeyInfo DER,
all signatures as base64 of DER-encoded ECDSA(SHA-256) (what Android Keystore emits).
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

MAX_SKEW_SECONDS = 60


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_request(method: str, path_qs: str, body: bytes, ts: str, nonce: str) -> bytes:
    return f"{method.upper()}\n{path_qs}\n{sha256_hex(body)}\n{ts}\n{nonce}".encode()


def canonical_response(status: int, path_qs: str, body: bytes, ts: str, nonce: str) -> bytes:
    return f"RESP\n{status}\n{path_qs}\n{sha256_hex(body)}\n{ts}\n{nonce}".encode()


def canonical_event(payload: str) -> bytes:
    return b"EVT\n" + payload.encode()


def generate_key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


def pub_to_b64(pub: ec.EllipticCurvePublicKey) -> str:
    der = pub.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return base64.b64encode(der).decode()


def pub_from_b64(b64: str) -> ec.EllipticCurvePublicKey:
    key = serialization.load_der_public_key(base64.b64decode(b64))
    if not isinstance(key, ec.EllipticCurvePublicKey) or not isinstance(key.curve, ec.SECP256R1):
        raise ValueError("public key must be EC P-256")
    return key


def device_id_for(pub_b64: str) -> str:
    return sha256_hex(base64.b64decode(pub_b64))[:16]


def fingerprint(pub_b64: str) -> str:
    h = sha256_hex(base64.b64decode(pub_b64))[:20].upper()
    return " ".join(h[i : i + 4] for i in range(0, 20, 4))


def sign(priv: ec.EllipticCurvePrivateKey, message: bytes) -> str:
    return base64.b64encode(priv.sign(message, ec.ECDSA(hashes.SHA256()))).decode()


def verify(pub: ec.EllipticCurvePublicKey, message: bytes, sig_b64: str) -> bool:
    try:
        pub.verify(base64.b64decode(sig_b64, validate=True), message, ec.ECDSA(hashes.SHA256()))
        return True
    except (InvalidSignature, ValueError):
        return False
