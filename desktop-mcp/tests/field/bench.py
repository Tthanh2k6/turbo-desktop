"""Measure scripted (no LLM) efficiency of the tools on our own windows: calls, response chars, ~tokens, wall time.
Run: python tests/field/bench.py   (prints a markdown table; paste into BENCH.md)"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("TURBO_DESKTOP_STATE_DIR", tempfile.mkdtemp(prefix="bench-state-"))
os.environ["TURBO_DESKTOP_NO_INPUT"] = "1"
os.environ["TURBO_DESKTOP_CONFIG"] = str(Path(os.environ["TURBO_DESKTOP_STATE_DIR"]) / "none.toml")

from turbo_desktop.engine import Desktop  # noqa: E402

try:
    import tiktoken
    _enc = tiktoken.get_encoding("cl100k_base")

    def toks(s):
        return len(_enc.encode(s))
except Exception:  # pragma: no cover
    def toks(s):
        return len(s) // 4

FIX = ROOT / "tests" / "fixtures"
rows = []


class Meter:
    def __init__(self, name):
        self.name, self.calls, self.chars, self.toks_, self.ok = name, 0, 0, 0, False

    def __enter__(self):
        self.t = time.time()
        return self

    def rec(self, out):
        s = out if isinstance(out, str) else json.dumps(out, ensure_ascii=False, separators=(",", ":"))
        self.calls += 1
        self.chars += len(s)
        self.toks_ += toks(s)
        return out

    def __exit__(self, *a):
        rows.append((self.name, self.calls, self.chars, self.toks_, round(time.time() - self.t, 2), self.ok))


def main():
    d = Desktop()
    tmp = ROOT / "tmp"
    # 1. fixture form fill: inspect + one batch (set 3 fields, submit) + one delta read
    p = subprocess.Popen([str(FIX / "turbo_fixture.exe")])
    time.sleep(2)
    try:
        w = d.find_window("TurboFixture")["id"]
        with Meter("Form fill (WinForms fixture, 4 fields)") as m:
            m.rec(d.inspect(w))
            os.environ["TURBO_DESKTOP_PRESET"] = "easy"
            m.rec(d.batch([
                {"action": "set_value", "name": "Full name", "text": "Nguyễn Văn An"},
                {"action": "select", "name": "Country", "text": "Vietnam"},
                {"action": "toggle", "name": "I agree to terms", "value": "true"},
                {"action": "click", "name": "Submit"},
            ], window=w, return_snapshot=True))
            for _ in range(10):   # the fixture writes its "Submitted" label a moment after the click (not counted)
                m.ok = "Submitted: Nguyễn Văn An / Vietnam / agree=True" in d.inspect(w, "text", query="Submitted")
                if m.ok:
                    break
                time.sleep(0.2)
    finally:
        p.kill()
    # 2. Calculator (launch returns first snapshot; one batch clicks and reads Display)
    with Meter("Calculator (12.5 + 7) x 3") as m:
        r = m.rec(d.launch("calc", snapshot_query="button"))
        w = r["windows"][0]["id"]
        steps = [{"action": "click", "name": n} for n in ("One", "Two", "Decimal separator", "Five", "Plus", "Seven",
                                                          "Equals", "Multiply by", "Three", "Equals")]
        steps.append({"op": "inspect", "mode": "text", "query": "Display", "only_changed": False})
        b = m.rec(d.batch(steps, window=w))
        out = b["steps"][-1].get("snapshot", "")
        m.ok = "58.5" in out
        d.window_control(w, "close")
    # 3. Launch + snapshot of the editor fixture (single call: launch_app includes first snapshot)
    try:
        with Meter("Launch + snapshot (editor fixture)") as m:
            r = m.rec(d.launch(str(FIX / "turbo_editor.exe")))
            m.ok = bool(r.get("ok") and r.get("windows") and "Text editor" in r.get("snapshot", ""))
    finally:
        d.close_launched()
    for r in rows:
        print("| {} | {} | {} | {} | {} s | {} |".format(r[0], r[1], r[2], r[3], r[4], "yes" if r[5] else "NO"))


if __name__ == "__main__":
    main()
