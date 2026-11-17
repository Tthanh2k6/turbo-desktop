#!/usr/bin/env python3
"""Wake-on-LAN relay for turbo-desktop. Python 3.8+ standard library only (runs in Termux).

Runs on an always-on device in the same LAN as the PC (e.g. a rooted Android tablet with Termux, a Raspberry Pi,
another PC). The phone calls it over Tailscale; it sends a WOL magic packet for the configured MAC.

  python wol_relay.py serve --mac AA:BB:CC:DD:EE:FF --bind 100.x.y.z [--port 8760] [--pair]

Security: listens ONLY on the address given by --bind (0.0.0.0 is refused). Every request must carry the same
signature headers as the hub (X-Device, X-Ts, X-Nonce, X-Sig = ECDSA P-256 / SHA-256 over
"METHOD\\nPATH\\nSHA256(body)\\nTS\\nNONCE"), from a phone key in this relay's OWN pairing list. Timestamps older
than 60 s and reused nonces are refused; 5 failures from one address lock it out for 15 minutes.
Pairing is only possible while the relay was started with --pair (5 minutes, one code).
"""
import argparse
import base64
import hashlib
import json
import os
import secrets
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ---------------------------------------------------------------- pure-python ECDSA P-256 verification
_P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
_A = _P - 3
_N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
_G = (0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296,
      0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5)


def _add(p, q):
    if p is None:
        return q
    if q is None:
        return p
    (x1, y1), (x2, y2) = p, q
    if x1 == x2:
        if (y1 + y2) % _P == 0:
            return None
        lam = (3 * x1 * x1 + _A) * pow(2 * y1, -1, _P) % _P
    else:
        lam = (y2 - y1) * pow(x2 - x1, -1, _P) % _P
    x3 = (lam * lam - x1 - x2) % _P
    return x3, (lam * (x1 - x3) - y1) % _P


def _mul(k, pt):
    r = None
    while k:
        if k & 1:
            r = _add(r, pt)
        pt = _add(pt, pt)
        k >>= 1
    return r


def _parse_pub(b64):
    der = base64.b64decode(b64)
    pt = der[-65:]
    if len(pt) != 65 or pt[0] != 4:
        raise ValueError("not an uncompressed P-256 key")
    q = (int.from_bytes(pt[1:33], "big"), int.from_bytes(pt[33:], "big"))
    if (q[1] * q[1] - (q[0] ** 3 + _A * q[0] + 0)) % _P != _b_check(q[0]):
        raise ValueError("point not on curve")
    return q


def _b_check(x):  # y^2 = x^3 - 3x + b ; return the right-hand side minus x^3 - 3x, i.e. b
    return 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B


def _parse_der_sig(sig):
    if sig[0] != 0x30:
        raise ValueError("bad signature")
    i = 2 if sig[1] < 0x80 else 2 + (sig[1] & 0x7F)
    if sig[i] != 0x02:
        raise ValueError("bad signature")
    lr = sig[i + 1]
    r = int.from_bytes(sig[i + 2:i + 2 + lr], "big")
    j = i + 2 + lr
    if sig[j] != 0x02:
        raise ValueError("bad signature")
    ls = sig[j + 1]
    s = int.from_bytes(sig[j + 2:j + 2 + ls], "big")
    return r, s


def verify_signature(pub_b64, message, sig_b64):
    try:
        q = _parse_pub(pub_b64)
        r, s = _parse_der_sig(base64.b64decode(sig_b64, validate=True))
    except (ValueError, IndexError):
        return False
    if not (1 <= r < _N and 1 <= s < _N):
        return False
    e = int.from_bytes(hashlib.sha256(message).digest(), "big")
    w = pow(s, -1, _N)
    pt = _add(_mul(e * w % _N, _G), _mul(r * w % _N, q))
    return pt is not None and pt[0] % _N == r


def canonical_request(method, path, body, ts, nonce):
    return ("%s\n%s\n%s\n%s\n%s" % (method.upper(), path, hashlib.sha256(body).hexdigest(), ts, nonce)).encode()


def device_id_for(pub_b64):
    return hashlib.sha256(base64.b64decode(pub_b64)).hexdigest()[:16]


# ---------------------------------------------------------------- Wake-on-LAN
def magic_packet(mac):
    raw = bytes.fromhex(mac.replace(":", "").replace("-", ""))
    if len(raw) != 6:
        raise ValueError("MAC must be 6 bytes")
    return b"\xff" * 6 + raw * 16


def send_wol(mac, broadcasts=("255.255.255.255",), ports=(9, 7), sock_factory=None):
    packet = magic_packet(mac)
    mk = sock_factory or (lambda: socket.socket(socket.AF_INET, socket.SOCK_DGRAM))
    sock = mk()
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for b in broadcasts:
            for p in ports:
                sock.sendto(packet, (b, p))
    finally:
        sock.close()
    return len(packet)


# ---------------------------------------------------------------- relay state + handler
class Relay:
    def __init__(self, state_dir, mac, broadcasts=("255.255.255.255",), clock=time.time, sock_factory=None):
        self.dir, self.mac, self.broadcasts, self.clock = state_dir, mac, broadcasts, clock
        self.sock_factory = sock_factory
        os.makedirs(state_dir, exist_ok=True)
        self.devices_path = os.path.join(state_dir, "relay_devices.json")
        self.devices = json.load(open(self.devices_path)) if os.path.exists(self.devices_path) else {}
        self.nonces, self.strikes, self.locked = {}, {}, {}
        self.pair_code, self.pair_exp = None, 0
        self.lock = threading.Lock()

    def open_pairing(self):
        self.pair_code, self.pair_exp = "%06d" % secrets.randbelow(10 ** 6), self.clock() + 300
        return self.pair_code

    def _strike(self, src):
        t = self.clock()
        hits = [x for x in self.strikes.get(src, []) if x > t - 600] + [t]
        self.strikes[src] = hits
        if len(hits) >= 5:
            self.locked[src] = t + 900
            self.strikes.pop(src, None)

    def _fresh(self, ts, nonce, key):
        try:
            if abs(self.clock() - int(ts)) > 60:
                return False
        except ValueError:
            return False
        now = self.clock()
        for k in [k for k, e in self.nonces.items() if e < now]:
            del self.nonces[k]
        if not nonce or len(nonce) > 128 or (key, nonce) in self.nonces:
            return False
        self.nonces[(key, nonce)] = now + 180
        return True

    def handle(self, method, path, headers, body, src):
        """Returns (status, dict). `headers` keys are lower-case."""
        with self.lock:
            if self.locked.get(src, 0) > self.clock():
                return 429, {"error": "locked out"}
            if len(body) > 4096:
                return 413, {"error": "too large"}
            h = lambda k: headers.get(k, "")  # noqa: E731
            ts, nonce, sig = h("x-ts"), h("x-nonce"), h("x-sig")
            if method == "POST" and path == "/pair":
                return self._pair(body, ts, nonce, sig, src)
            dev = self.devices.get(h("x-device"))
            if dev is None or not self._fresh(ts, nonce, dev["id"]) or not verify_signature(
                    dev["pub"], canonical_request(method, path, body, ts, nonce), sig):
                self._strike(src)
                return 401, {"error": "unauthorized"}
            if method == "POST" and path == "/wake":
                n = send_wol(self.mac, self.broadcasts, sock_factory=self.sock_factory)
                return 200, {"ok": True, "sent_bytes": n}
            if method == "GET" and path == "/hello":
                return 200, {"ok": True}
            return 404, {"error": "not found"}

    def _pair(self, body, ts, nonce, sig, src):
        if not self.pair_code or self.pair_exp < self.clock():
            return 403, {"error": "pairing is closed (start the relay with --pair)"}
        try:
            d = json.loads(body)
            code, pub, name = str(d["code"]), str(d["pub"]), str(d.get("name", "phone"))[:60]
            ok = (secrets.compare_digest(code, self.pair_code) and self._fresh(ts, nonce, "pair")
                  and verify_signature(pub, canonical_request("POST", "/pair", body, ts, nonce), sig))
        except (ValueError, KeyError, TypeError):
            ok = False
        if not ok:
            self._strike(src)
            return 403, {"error": "pairing failed"}
        self.pair_code = None
        did = device_id_for(pub)
        self.devices[did] = {"id": did, "name": name, "pub": pub}
        tmp = self.devices_path + ".tmp"
        json.dump(self.devices, open(tmp, "w"))
        os.replace(tmp, self.devices_path)
        return 200, {"deviceId": did}


def make_handler(relay):
    class H(BaseHTTPRequestHandler):
        def _do(self):
            n = min(int(self.headers.get("Content-Length") or 0), 8192)
            body = self.rfile.read(n) if n else b""
            headers = {k.lower(): v for k, v in self.headers.items()}
            status, obj = relay.handle(self.command, self.path, headers, body, self.client_address[0])
            out = json.dumps(obj).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

        do_GET = do_POST = _do

        def log_message(self, fmt, *args):
            sys.stderr.write("%s %s\n" % (self.client_address[0], fmt % args))

    return H


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sv = sub.add_parser("serve")
    sv.add_argument("--mac", required=True)
    sv.add_argument("--bind", required=True, help="Tailscale IP of this device (never 0.0.0.0)")
    sv.add_argument("--port", type=int, default=8760)
    sv.add_argument("--broadcast", action="append", help="extra broadcast address, e.g. 192.168.1.255")
    sv.add_argument("--state-dir", default=os.path.join(os.path.expanduser("~"), ".turbo-wol-relay"))
    sv.add_argument("--pair", action="store_true", help="open a 5-minute pairing window and print the code")
    a = ap.parse_args(argv)
    if a.bind in ("0.0.0.0", "::", ""):
        raise SystemExit("refusing to listen on all interfaces; pass the Tailscale IP")
    relay = Relay(a.state_dir, a.mac, tuple(["255.255.255.255"] + (a.broadcast or [])))
    if a.pair:
        print("pairing code (valid 5 min):", relay.open_pairing())
    srv = ThreadingHTTPServer((a.bind, a.port), make_handler(relay))
    print("wol relay listening on %s:%d for MAC %s, %d paired phone(s)" % (a.bind, a.port, a.mac, len(relay.devices)))
    srv.serve_forever()


if __name__ == "__main__":
    main()
