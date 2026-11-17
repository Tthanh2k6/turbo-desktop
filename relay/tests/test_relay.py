"""Run with the hub venv (it has `cryptography` for signing in the test; the relay itself uses only the stdlib):
    hub\\.venv\\Scripts\\python -m pytest relay\\tests
"""
import base64
import json
import os
import secrets
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

import wol_relay as w


class FakeSock:
    sent = []

    def setsockopt(self, *a):
        pass

    def sendto(self, data, addr):
        FakeSock.sent.append((data, addr))

    def close(self):
        pass


class Phone:
    def __init__(self):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.pub = base64.b64encode(self.key.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)).decode()
        self.id = w.device_id_for(self.pub)

    def headers(self, method, path, body, ts, nonce=None):
        nonce = nonce or secrets.token_hex(8)
        sig = base64.b64encode(self.key.sign(w.canonical_request(method, path, body, str(ts), nonce),
                                             ec.ECDSA(hashes.SHA256()))).decode()
        return {"x-device": self.id, "x-ts": str(ts), "x-nonce": nonce, "x-sig": sig}


@pytest.fixture
def relay(tmp_path):
    FakeSock.sent = []
    t = [1_700_000_000.0]
    r = w.Relay(str(tmp_path), "AA:BB:CC:DD:EE:FF", ("255.255.255.255", "192.168.1.255"), clock=lambda: t[0],
                sock_factory=FakeSock)
    r.t = t
    return r


def pair(relay, phone):
    code = relay.open_pairing()
    body = json.dumps({"code": code, "pub": phone.pub, "name": "p"}).encode()
    h = phone.headers("POST", "/pair", body, int(relay.t[0]))
    return relay.handle("POST", "/pair", h, body, "1.2.3.4")


def test_magic_packet_bytes():
    p = w.magic_packet("aa:bb:cc:dd:ee:ff")
    assert len(p) == 102 and p[:6] == b"\xff" * 6 and p[6:] == bytes.fromhex("aabbccddeeff") * 16
    with pytest.raises(ValueError):
        w.magic_packet("aa:bb")


def test_wake_sends_packet_to_ports_9_and_7_on_each_broadcast(relay):
    ph = Phone()
    assert pair(relay, ph)[0] == 200
    h = ph.headers("POST", "/wake", b"", int(relay.t[0]))
    status, out = relay.handle("POST", "/wake", h, b"", "1.2.3.4")
    assert status == 200 and out["sent_bytes"] == 102
    assert sorted((a for _, a in FakeSock.sent)) == sorted(
        [("255.255.255.255", 9), ("255.255.255.255", 7), ("192.168.1.255", 9), ("192.168.1.255", 7)])
    assert all(d == w.magic_packet("AA:BB:CC:DD:EE:FF") for d, _ in FakeSock.sent)


def test_signature_required(relay):
    ph = Phone()
    pair(relay, ph)
    ts = int(relay.t[0])
    assert relay.handle("POST", "/wake", {}, b"", "9.9.9.9")[0] == 401                    # no headers
    h = ph.headers("POST", "/wake", b"", ts)
    h["x-sig"] = Phone().headers("POST", "/wake", b"", ts)["x-sig"]                       # signed by another key
    assert relay.handle("POST", "/wake", h, b"", "9.9.9.9")[0] == 401
    stranger = Phone()                                                                    # unpaired phone
    assert relay.handle("POST", "/wake", stranger.headers("POST", "/wake", b"", ts), b"", "9.9.9.9")[0] == 401
    assert FakeSock.sent == []


def test_old_timestamp_and_replay(relay):
    ph = Phone()
    pair(relay, ph)
    ts = int(relay.t[0])
    assert relay.handle("POST", "/wake", ph.headers("POST", "/wake", b"", ts - 120), b"", "1.1.1.1")[0] == 401
    h = ph.headers("POST", "/wake", b"", ts, nonce="same")
    assert relay.handle("POST", "/wake", h, b"", "1.1.1.1")[0] == 200
    assert relay.handle("POST", "/wake", h, b"", "1.1.1.1")[0] == 401


def test_lockout_after_5_failures(relay):
    for _ in range(5):
        relay.handle("POST", "/wake", {}, b"", "7.7.7.7")
    assert relay.handle("POST", "/wake", {}, b"", "7.7.7.7")[0] == 429
    relay.t[0] += 901
    assert relay.handle("POST", "/wake", {}, b"", "7.7.7.7")[0] == 401


def test_pairing_closed_unless_enabled_and_one_time(relay):
    ph = Phone()
    body = json.dumps({"code": "123456", "pub": ph.pub}).encode()
    assert relay.handle("POST", "/pair", ph.headers("POST", "/pair", body, int(relay.t[0])), body, "1.1.1.1")[0] == 403
    assert pair(relay, ph)[0] == 200
    assert pair.__name__ and relay.pair_code is None                                       # code consumed


def test_pure_python_ecdsa_matches_cryptography():
    for _ in range(5):
        ph, msg = Phone(), secrets.token_bytes(40)
        sig = base64.b64encode(ph.key.sign(msg, ec.ECDSA(hashes.SHA256()))).decode()
        assert w.verify_signature(ph.pub, msg, sig)
        assert not w.verify_signature(ph.pub, msg + b"x", sig)


def test_refuses_all_interfaces():
    with pytest.raises(SystemExit):
        w.main(["serve", "--mac", "AA:BB:CC:DD:EE:FF", "--bind", "0.0.0.0"])
