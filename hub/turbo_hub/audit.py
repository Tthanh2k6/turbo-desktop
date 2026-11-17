"""Append-only JSONL audit log, every line hash-chained to the previous one (sha256)."""
from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path

GENESIS = "0" * 64


def _line_hash(prev: str, i: int, ts: float, kind: str, data: dict) -> str:
    body = json.dumps({"i": i, "ts": ts, "kind": kind, "data": data}, sort_keys=True,
                      separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256((prev + body).encode()).hexdigest()


class AuditLog:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._last_hash = GENESIS
        self._count = 0
        if self.path.exists():
            for line in self.path.read_text("utf-8").splitlines():
                if line.strip():
                    try:
                        e = json.loads(line)
                        self._last_hash, self._count = e["hash"], e["i"] + 1
                    except (ValueError, KeyError):
                        break  # tampered tail: verify() reports it

    def append(self, kind: str, data: dict) -> dict:
        with self._lock:
            i, ts = self._count, round(time.time(), 3)
            h = _line_hash(self._last_hash, i, ts, kind, data)
            entry = {"i": i, "ts": ts, "kind": kind, "data": data, "prev": self._last_hash, "hash": h}
            with self.path.open("a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
            self._last_hash, self._count = h, i + 1
            return entry

    def read(self, limit: int = 100, offset_from_end: int = 0) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text("utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                out.append({"i": -1, "kind": "corrupt_line", "data": {}, "ts": 0, "prev": "", "hash": ""})
        end = len(out) - offset_from_end
        return out[max(0, end - limit):end]

    def verify(self) -> tuple[bool, str]:
        """Return (ok, message). Detects edited, removed, reordered and appended-without-chain lines."""
        if not self.path.exists():
            return True, "empty"
        prev, n = GENESIS, 0
        for lineno, line in enumerate(self.path.read_text("utf-8").splitlines(), 1):
            if not line.strip():
                return False, f"line {lineno}: blank line"
            try:
                e = json.loads(line)
                ok_shape = e["i"] == n and e["prev"] == prev
                expect = _line_hash(prev, e["i"], e["ts"], e["kind"], e["data"])
            except (ValueError, KeyError, TypeError):
                return False, f"line {lineno}: unreadable"
            if not ok_shape:
                return False, f"line {lineno}: chain broken (missing or reordered line)"
            if e["hash"] != expect:
                return False, f"line {lineno}: content does not match its hash"
            prev, n = e["hash"], n + 1
        return True, f"{n} entries"
