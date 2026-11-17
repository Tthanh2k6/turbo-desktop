"""Integration tests on our own fixture apps (tests/fixtures). Only windows these tests launch are touched.
Real mouse/keyboard tests are opt-in: TURBO_DESKTOP_REAL_INPUT=1."""
import os
import time

import pytest

from turbo_desktop.engine import ToolError

from conftest import REAL_INPUT


def refs(snapshot):
    """name -> ref from a snapshot text (first occurrence of an interactive role)."""
    import re
    out = {}
    for m in re.finditer(r'\[(w\d+:e\d+)\] <(\w+)> "([^"]*)"', snapshot):
        out.setdefault(m.group(3), m.group(1))
    return out


def test_windows_list_has_our_window_only_flags(launch_app, desktop):
    d = launch_app("turbo_fixture.exe")
    row = [w for w in desktop.windows_list() if w["hwnd"] == d["hwnd"]][0]
    assert row["title"] == "TurboFixture" and row["process"] == "turbo_fixture" and "elevated" not in row


def test_inspect_compact_format(launch_app, desktop):
    d = launch_app("turbo_fixture.exe")
    s = desktop.inspect(d["id"])
    assert s.startswith("<<<SCREEN_CONTENT") and "<<<END_SCREEN_CONTENT" in s
    assert '<Button> "Submit"' in s and '<CheckBox> "I agree to terms" [unchecked]' in s
    assert "<Text>" not in s                       # labels only in text/all mode
    assert len(s) < 1500                            # compact
    assert "[password:protected]" in s


def test_stable_refs_and_delta(launch_app, desktop):
    d = launch_app("turbo_fixture.exe")
    s1 = desktop.inspect(d["id"])
    r1 = refs(s1)
    desktop.act(d["id"], "click", ref=r1["Count 0"])
    s2 = desktop.inspect(d["id"], only_changed=True)
    assert "~[" + r1["Count 0"] + "]" in s2 and 'Count 1' in s2
    assert "Submit" not in s2 and "unchanged" in s2          # unchanged elements are not repeated
    r2 = refs(desktop.inspect(d["id"]))
    assert r2["Submit"] == r1["Submit"]                        # refs stay stable
    s3 = desktop.inspect(d["id"], only_changed=True)
    assert "0 new, 0 changed, 0 removed" in s3


def test_act_patterns_form(launch_app, desktop):
    d = launch_app("turbo_fixture.exe")
    w = d["id"]
    assert desktop.act(w, "set_value", name="Full name", text="Nguyễn Văn An")["via"] == "pattern"
    assert desktop.act(w, "select", name="Country", text="Japan")["value"] == "Japan"
    assert desktop.act(w, "toggle", name="I agree to terms", value="true")["state"] == ["checked"]
    assert desktop.act(w, "toggle", name="I agree to terms", value="true")["state"] == ["checked"]  # idempotent
    assert desktop.act(w, "type", name="Full name", text="!")["value"] == "Nguyễn Văn An!"
    desktop.act(w, "click", name="Submit")
    out = desktop.inspect(w, "text", query="Submitted")
    assert "Submitted: Nguyễn Văn An! / Japan / agree=True" in out


def test_unknown_combo_option_is_an_error(launch_app, desktop):
    d = launch_app("turbo_fixture.exe")
    with pytest.raises(ToolError, match="no option"):
        desktop.act(d["id"], "select", name="Country", text="Narnia")


def test_set_value_bypasses_maxlength_and_says_so_via_readback(launch_app, desktop):
    """WM_SETTEXT ignores MaxLength, so set_value stores all 600 chars. The result must reflect the real value."""
    d = launch_app("turbo_fixture.exe")
    r = desktop.act(d["id"], "set_value", name="Short code", text="x" * 600)
    assert r["ok"] and len(desktop.act(d["id"], "read", name="Short code")["text"]) > 600  # wrapper adds markers


@pytest.mark.skipif(not REAL_INPUT, reason="needs TURBO_DESKTOP_REAL_INPUT=1 (real keyboard)")
def test_real_typing_truncation_is_reported_truthfully(launch_app, desktop):
    os.environ["TURBO_DESKTOP_IDLE_SECONDS"] = "2"
    d = launch_app("turbo_fixture.exe", "--accept-keys")
    with pytest.raises(ToolError) as e:
        desktop.act(d["id"], "send_text", name="Short code", text="y" * 30)
    ex = e.value.extra
    assert ex["truncated"] is True and ex["wanted"] == 30 and ex["got"] == 10


def test_batch_stops_on_first_error(launch_app, desktop):
    d = launch_app("turbo_fixture.exe")
    r = desktop.batch([
        {"action": "set_value", "name": "Full name", "text": "Bo"},
        {"action": "click", "name": "No such button"},
        {"action": "click", "name": "Count 0"},
    ], window=d["id"], return_snapshot=True)
    assert r["ok"] is False and r["failedAt"] == 1 and len(r["steps"]) == 2
    assert "Count 0" in desktop.inspect(d["id"], query="Count")          # third step never ran
    assert "Full name" in r["snapshot"]


def test_batch_success_with_wait_and_delta(launch_app, desktop):
    d = launch_app("turbo_fixture.exe")
    desktop.inspect(d["id"])
    r = desktop.batch([
        {"action": "click", "name": "Count 0"},
        {"op": "wait_for", "text": "Count 1", "timeout": 3},
        {"action": "click", "name": "Count 1"},
    ], window=d["id"], return_snapshot=True)
    assert r["ok"] and "Count 2" in r["snapshot"]


def test_wait_for_text_title_and_gone(launch_app, desktop):
    d = launch_app("turbo_fixture.exe")
    assert desktop.wait_for(window=d["id"], text="Submit", timeout=2)["ok"]
    assert desktop.wait_for(title="TurboFixture", timeout=2)["ok"]
    with pytest.raises(ToolError, match="timeout"):
        desktop.wait_for(window=d["id"], text="Never appears", timeout=0.6)
    desktop.window_control(d["id"], "close")
    assert desktop.wait_for(title="TurboFixture", gone=True, timeout=5)["ok"]


def test_stale_ref_is_reported(launch_app, desktop):
    d = launch_app("turbo_fixture.exe")
    desktop.inspect(d["id"])
    desktop.window_control(d["id"], "close")
    time.sleep(1)
    with pytest.raises(ToolError):
        desktop.act(d["id"], "click", ref="e1")


def test_press_keys_refused_when_input_disabled(launch_app, desktop):
    if REAL_INPUT:
        pytest.skip("real input enabled")
    d = launch_app("turbo_fixture.exe")
    with pytest.raises(ToolError, match="real input disabled"):
        desktop.act(d["id"], "press_keys", name="Full name", keys="abc")


def test_editor_menu_and_text(launch_app, desktop):
    d = launch_app("turbo_editor.exe")
    desktop.act(d["id"], "set_value", name="Text editor", text="line1\r\nline2 tiếng Việt")
    assert "tiếng Việt" in desktop.act(d["id"], "read", name="Text editor")["text"]
    desktop.act(d["id"], "click", name="File")
    assert desktop.wait_for(window=d["id"], text="Save As...", timeout=2)["ok"]


def test_canvas_has_empty_tree_and_ocr_finds_text(launch_app, desktop):
    d = launch_app("turbo_canvas.exe")
    s = desktop.inspect(d["id"])
    assert "treeEmpty: true" in s
    if 'via: "ocr"' in s:
        assert 'text "Save"' in s and "@" in s
    else:
        pytest.fail("OCR gave nothing for the canvas window: " + s[-300:])


@pytest.mark.skipif(not REAL_INPUT, reason="needs TURBO_DESKTOP_REAL_INPUT=1 (moves the real mouse)")
def test_ocr_click_real_input(launch_app, desktop):
    os.environ["TURBO_DESKTOP_IDLE_SECONDS"] = "2"
    d = launch_app("turbo_canvas.exe")
    s = desktop.inspect(d["id"])
    ref = [l for l in s.splitlines() if 'text "Save"' in l][0].split("]")[0].lstrip("[")
    r = desktop.act(d["id"], "click", ref=ref)
    assert r["via"] == "ocr"
    assert desktop.wait_for(title="TurboCanvas clicked", timeout=3)["ok"]


def test_long_value_reports_length(launch_app, desktop):
    """Field bug 2: an agent could not verify a 600-char value; results now carry length."""
    d = launch_app("turbo_fixture.exe")
    r = desktop.act(d["id"], "set_value", name="Short code", text="x" * 600)
    assert r["length"] == 600
    assert desktop.act(d["id"], "read", name="Short code")["length"] == 600


def test_press_keys_without_target_goes_to_the_window(launch_app, desktop):
    """Field bug 9: act(press_keys) with only a window (e.g. Ctrl+S) answered 'need ref or name'."""
    if REAL_INPUT:
        pytest.skip("real input enabled")
    d = launch_app("turbo_fixture.exe")
    with pytest.raises(ToolError, match="real input disabled"):
        desktop.act(d["id"], "press_keys", keys="{Ctrl}s")


def test_normalize_keys_accepts_double_braces():
    from turbo_desktop.engine import normalize_keys
    assert normalize_keys("{{Ctrl}}s") == ("{Ctrl}s", True)
    assert normalize_keys("{{Esc}}") == ("{Esc}", True)
    assert normalize_keys("{Ctrl}s") == ("{Ctrl}s", False)
    assert normalize_keys("abc") == ("abc", False)


def test_batch_step_with_unknown_field_is_a_clear_error(launch_app, desktop):
    """Field round 5: a model invented a "real": true field and got a raw TypeError 'internal' result."""
    d = launch_app("turbo_fixture.exe")
    r = desktop.batch([{"action": "click", "name": "Count 0", "real": True}], window=d["id"])
    assert r["ok"] is False and "bad step arguments" in r["steps"][0]["error"] and "Valid fields" in r["steps"][0]["error"]


@pytest.mark.parametrize("given,expected", [
    ("Ctrl+Shift+N", "{Ctrl}{Shift}n"), ("ctrl+s", "{Ctrl}s"), ("Alt+F4", "{Alt}{F4}"), ("Shift+F10", "{Shift}{F10}"),
    ("Control+Enter", "{Ctrl}{Enter}"), ("Enter", "{Enter}"), ("esc", "{Esc}"), ("F2", "{F2}"), ("{Ctrl}s", "{Ctrl}s"),
    ("hello world", "hello world"), ("turbo-new", "turbo-new"), ("a+b", "a+b"),
])
def test_normalize_keys_models_syntax(given, expected):
    from turbo_desktop.engine import normalize_keys
    assert normalize_keys(given)[0] == expected


def test_send_text_without_target_types_into_the_window(launch_app, desktop):
    """Field round 5 (task 4): an inline rename box is not an addressable control; send_text with only a window must work."""
    if REAL_INPUT:
        pytest.skip("real input enabled")
    d = launch_app("turbo_fixture.exe")
    with pytest.raises(ToolError, match="real input disabled"):     # reaches the input stage instead of 'need ref or name'
        desktop.act(d["id"], "send_text", text="turbo-new")
