"""Head-to-head Windows benchmark: UIA Compact Snapshots + Delta Diffs vs Screenshot-per-step.

Measures real tool calls, wall-clock ms, payload bytes, and token cost (tiktoken o200k_base for UIA text;
actual captured PNG dimensions for Anthropic W*H/750 and OpenAI tile vision formulas) across 4 native
Windows fixture tasks. Touches only its own test fixture windows and closes them in finally blocks.
"""
from __future__ import annotations

import base64
import io
import json
import math
import os
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

os.environ.setdefault("PYTHONUTF8", "1")
os.environ["TURBO_DESKTOP_NO_INDICATOR"] = "1"
os.environ["TURBO_DESKTOP_NO_INPUT"] = "1"
os.environ["TURBO_DESKTOP_PRESET"] = "easy"
os.environ["TURBO_DESKTOP_APPROVAL"] = "allow"

from turbo_desktop import security as sec  # noqa: E402
from turbo_desktop.engine import Desktop  # noqa: E402

try:
    import tiktoken
    _ENC = tiktoken.get_encoding("o200k_base")

    def count_text_tokens(text: str) -> int:
        return len(_ENC.encode(text))
except Exception:
    def count_text_tokens(text: str) -> int:
        return max(1, round(len(text) / 4))


def vision_tokens_anthropic(w: int, h: int) -> int:
    return math.ceil((w * h) / 750)


def vision_tokens_openai(w: int, h: int) -> int:
    tiles = math.ceil(w / 512) * math.ceil(h / 512)
    return tiles * 170 + 85


def measure_screenshot(dt: Desktop, wid: str) -> dict:
    t0 = time.perf_counter()
    png = dt.screenshot(wid)
    ms = (time.perf_counter() - t0) * 1000.0
    img = Image.open(io.BytesIO(png))
    w, h = img.size
    return {
        "ms": ms,
        "bytes": len(png),
        "b64_chars": len(base64.b64encode(png)),
        "width": w,
        "height": h,
        "anthropic_tok": vision_tokens_anthropic(w, h),
        "openai_tok": vision_tokens_openai(w, h),
    }


def _get_wid(launched: dict) -> str:
    if isinstance(launched.get("id"), str):
        return launched["id"]
    if isinstance(launched.get("window"), dict) and launched["window"].get("id"):
        return launched["window"]["id"]
    wins = launched.get("windows") or []
    if wins and isinstance(wins[0], dict) and wins[0].get("id"):
        return wins[0]["id"]
    raise RuntimeError(f"Could not extract wid from launch(): {launched!r}")


def run_benchmark() -> list[dict]:
    fixtures = ROOT / "tests" / "fixtures"
    tmp_dir = Path(tempfile.mkdtemp(prefix="td-bench-"))
    os.environ["TURBO_DESKTOP_STATE_DIR"] = str(tmp_dir)
    os.environ["TURBO_DESKTOP_AUDIT"] = str(tmp_dir / "audit.jsonl")

    dt = Desktop(audit=sec.AuditLog(tmp_dir / "audit.jsonl"))
    results = []

    # ── Task 1: Multi-field Form Fill + Submit + Delta (turbo_fixture.exe) ──
    fx = str(fixtures / "turbo_fixture.exe")
    wid = None
    try:
        t0 = time.perf_counter()
        launched = dt.launch(fx)
        wid = _get_wid(launched)
        snap1 = dt.inspect(wid, mode="interactive")
        batch_res = dt.batch([
            {"action": "set_value", "name": "Full name", "text": "Nguyễn Văn An"},
            {"action": "select", "name": "Country", "text": "Japan"},
            {"action": "toggle", "name": "I agree to terms", "value": "true"},
            {"action": "click", "name": "Submit"},
        ], window=wid, return_snapshot=True)
        verify_out = dt.inspect(wid, mode="text", query="Submitted")
        uia_ms = (time.perf_counter() - t0) * 1000.0
        uia_payload = json.dumps(launched) + "\n" + snap1 + "\n" + json.dumps(batch_res) + "\n" + verify_out
        ok = bool(batch_res.get("ok")) and "Submitted: Nguyễn Văn An / Japan / agree=True" in verify_out

        # Screenshot baseline: 1 initial screenshot + 4 step screenshots + 1 final verify = 6 captures
        shots = [measure_screenshot(dt, wid) for _ in range(6)]
        results.append({
            "task": "1. WinForms form fill (3 fields + Submit + verify)",
            "uia_calls": 4,
            "uia_ms": round(uia_ms, 1),
            "uia_bytes": len(uia_payload.encode("utf-8")),
            "uia_tokens": count_text_tokens(uia_payload),
            "uia_ok": ok,
            "shot_steps": len(shots),
            "shot_ms": round(sum(s["ms"] for s in shots), 1),
            "shot_bytes": sum(s["bytes"] for s in shots),
            "shot_dims": f"{shots[0]['width']}x{shots[0]['height']}",
            "shot_anthropic_tok": sum(s["anthropic_tok"] for s in shots),
            "shot_openai_tok": sum(s["openai_tok"] for s in shots),
            "shot_720p_anthropic_tok": len(shots) * vision_tokens_anthropic(1280, 720),
        })
    finally:
        if wid:
            try:
                dt.window_control(wid, "close")
            except Exception:
                pass

    # ── Task 2: 5-step Counter + Delta Diff Loop (turbo_fixture.exe) ──
    wid = None
    try:
        t0 = time.perf_counter()
        launched = dt.launch(fx)
        wid = _get_wid(launched)
        parts = [json.dumps(launched), dt.inspect(wid, mode="interactive")]
        for i in range(5):
            r = dt.act(wid, "click", name=f"Count {i}")
            delta = dt.inspect(wid, mode="interactive", only_changed=True)
            parts.append(json.dumps(r))
            parts.append(delta)
        uia_ms = (time.perf_counter() - t0) * 1000.0
        uia_payload = "\n".join(parts)
        ok = "Count 5" in dt.inspect(wid, mode="interactive")

        # Screenshot baseline: 1 initial + 5 post-click screenshots = 6 captures
        shots = [measure_screenshot(dt, wid) for _ in range(6)]
        results.append({
            "task": "2. 5-step stateful UI loop (click + delta diff)",
            "uia_calls": 12,
            "uia_ms": round(uia_ms, 1),
            "uia_bytes": len(uia_payload.encode("utf-8")),
            "uia_tokens": count_text_tokens(uia_payload),
            "uia_ok": ok,
            "shot_steps": len(shots),
            "shot_ms": round(sum(s["ms"] for s in shots), 1),
            "shot_bytes": sum(s["bytes"] for s in shots),
            "shot_dims": f"{shots[0]['width']}x{shots[0]['height']}",
            "shot_anthropic_tok": sum(s["anthropic_tok"] for s in shots),
            "shot_openai_tok": sum(s["openai_tok"] for s in shots),
            "shot_720p_anthropic_tok": len(shots) * vision_tokens_anthropic(1280, 720),
        })
    finally:
        if wid:
            try:
                dt.window_control(wid, "close")
            except Exception:
                pass

    # ── Task 3: Native Editor multi-line write + readback (turbo_editor.exe) ──
    ed = str(fixtures / "turbo_editor.exe")
    wid = None
    try:
        t0 = time.perf_counter()
        launched = dt.launch(ed)
        wid = _get_wid(launched)
        snap1 = dt.inspect(wid, mode="interactive")
        sample_text = "Line 1: Release v0.1.0\r\nLine 2: UIA delta benchmark\r\nLine 3: Unicode Tiếng Việt OK"
        res_set = dt.act(wid, "set_value", name="Text editor", text=sample_text)
        res_read = dt.act(wid, "read", name="Text editor")
        uia_ms = (time.perf_counter() - t0) * 1000.0
        uia_payload = "\n".join([json.dumps(launched), snap1, json.dumps(res_set), json.dumps(res_read)])
        ok = bool(res_set.get("ok")) and "Tiếng Việt OK" in str(res_read.get("text", ""))

        # Screenshot baseline: 1 initial + 1 click editor + 1 after typing = 3 captures
        shots = [measure_screenshot(dt, wid) for _ in range(3)]
        results.append({
            "task": "3. Native editor multi-line Unicode write + readback",
            "uia_calls": 4,
            "uia_ms": round(uia_ms, 1),
            "uia_bytes": len(uia_payload.encode("utf-8")),
            "uia_tokens": count_text_tokens(uia_payload),
            "uia_ok": ok,
            "shot_steps": len(shots),
            "shot_ms": round(sum(s["ms"] for s in shots), 1),
            "shot_bytes": sum(s["bytes"] for s in shots),
            "shot_dims": f"{shots[0]['width']}x{shots[0]['height']}",
            "shot_anthropic_tok": sum(s["anthropic_tok"] for s in shots),
            "shot_openai_tok": sum(s["openai_tok"] for s in shots),
            "shot_720p_anthropic_tok": len(shots) * vision_tokens_anthropic(1280, 720),
        })
    finally:
        if wid:
            try:
                dt.window_control(wid, "close")
            except Exception:
                pass

    # ── Task 4: Custom-drawn Canvas (no UIA tree -> Windows OCR fallback) ──
    cv = str(fixtures / "turbo_canvas.exe")
    wid = None
    try:
        t0 = time.perf_counter()
        launched = dt.launch(cv)
        wid = _get_wid(launched)
        snap_ocr = dt.inspect(wid, mode="interactive")
        uia_ms = (time.perf_counter() - t0) * 1000.0
        uia_payload = json.dumps(launched) + "\n" + snap_ocr
        ok = ("o1" in snap_ocr) or ("treeEmpty" in snap_ocr) or ("OCR" in snap_ocr.upper())

        # Screenshot baseline: 1 capture to inspect custom canvas
        shots = [measure_screenshot(dt, wid)]
        results.append({
            "task": "4. Custom-drawn canvas (no UIA tree -> Windows OCR fallback)",
            "uia_calls": 2,
            "uia_ms": round(uia_ms, 1),
            "uia_bytes": len(uia_payload.encode("utf-8")),
            "uia_tokens": count_text_tokens(uia_payload),
            "uia_ok": ok,
            "shot_steps": len(shots),
            "shot_ms": round(sum(s["ms"] for s in shots), 1),
            "shot_bytes": sum(s["bytes"] for s in shots),
            "shot_dims": f"{shots[0]['width']}x{shots[0]['height']}",
            "shot_anthropic_tok": sum(s["anthropic_tok"] for s in shots),
            "shot_openai_tok": sum(s["openai_tok"] for s in shots),
            "shot_720p_anthropic_tok": len(shots) * vision_tokens_anthropic(1280, 720),
        })
    finally:
        if wid:
            try:
                dt.window_control(wid, "close")
            except Exception:
                pass

    return results


if __name__ == "__main__":
    data = run_benchmark()
    print(json.dumps(data, indent=2, ensure_ascii=False))
