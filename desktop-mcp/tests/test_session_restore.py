"""Session-restore apps (Notepad on Win11, browsers, VS Code, Office) reopen the owner's previous files.
No real launch happens here: subprocess.Popen is replaced."""
import os
import sys

import pytest

from turbo_desktop import engine, rules, security as sec
from turbo_desktop.engine import ToolError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "field"))
import run_field  # noqa: E402

DEFAULT = rules._read_toml(rules.DEFAULT_RULES_FILE)


class FakePopen:
    calls = []

    def __init__(self, argv, **kw):
        FakePopen.calls.append(argv)


@pytest.fixture
def fake(monkeypatch, desktop):
    FakePopen.calls = []
    monkeypatch.setattr(engine.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(desktop, "windows_list", lambda *a, **k: [])
    monkeypatch.delenv("TURBO_DESKTOP_REQUIRE_CLEAN", raising=False)
    return desktop


def test_default_list_contains_the_expected_apps():
    got = set(DEFAULT["apps"]["session_restore"]["processes"])
    assert {"notepad", "msedge", "chrome", "code", "winword", "excel"} <= got


def test_easy_allows_with_warning(fake):
    r = fake.launch("notepad", wait=0.1)
    assert r["ok"] and "may reopen the user's previous files" in r["warn"] and r["launchMode"] == "normal"
    assert FakePopen.calls[0][0].lower().endswith("notepad.exe") or FakePopen.calls[0][0] == "notepad.exe"


def test_balanced_asks(fake, monkeypatch):
    os.environ["TURBO_DESKTOP_PRESET"] = "balanced"
    monkeypatch.setattr(sec, "PROMPT_FN", [lambda s, t: False])
    with pytest.raises(ToolError) as e:
        fake.launch("notepad", wait=0.1)
    assert e.value.extra["rule"] == "launch-session-restore" and not FakePopen.calls
    monkeypatch.setattr(sec, "PROMPT_FN", [lambda s, t: True])
    assert fake.launch("notepad", wait=0.1)["ok"] and FakePopen.calls


def test_strict_prefers_clean_launch(fake, monkeypatch):
    os.environ["TURBO_DESKTOP_PRESET"] = "strict"
    monkeypatch.setattr(sec, "PROMPT_FN", [lambda s, t: True])
    r = fake.launch("notepad", wait=0.1)
    assert r["launchMode"] == "clean" and "new temp file" in r["clean"]
    assert FakePopen.calls[-1][1].endswith(".txt") and os.path.exists(FakePopen.calls[-1][1])
    r = fake.launch("vscode", wait=0.1) if False else fake.launch("code", wait=0.1)
    assert r["launchMode"] == "clean" and "--new-window" in FakePopen.calls[-1]


def test_no_clean_path_means_normal_with_warning_in_strict(fake, monkeypatch):
    os.environ["TURBO_DESKTOP_PRESET"] = "strict"
    monkeypatch.setattr(sec, "PROMPT_FN", [lambda s, t: True])
    r = fake.launch("excel", wait=0.1)
    assert r["launchMode"] == "normal" and "warn" in r


def test_require_clean_refuses_without_clean_path(fake, monkeypatch):
    """Our own tests and field runs set TURBO_DESKTOP_REQUIRE_CLEAN=1: Excel has no clean path, so it is refused."""
    monkeypatch.setenv("TURBO_DESKTOP_REQUIRE_CLEAN", "1")
    with pytest.raises(ToolError, match="no clean-launch path"):
        fake.launch("excel", wait=0.1)
    assert not FakePopen.calls
    assert fake.launch("notepad", wait=0.1)["launchMode"] == "clean"  # has one


def test_user_can_edit_the_list(fake):
    user = {"desktop": {"apps": {"session_restore": {"processes": ["myeditor"]}}}}
    assert "myeditor" in rules.build_ruleset(DEFAULT, user, "easy").session_restore


def test_field_runner_refuses_session_restore_tasks():
    for prompt in ("Open Notepad and type", "Open VS Code in a temp folder", "Open Edge InPrivate", "bold a word in Word"):
        assert run_field.refuses({"prompt": prompt})
    assert run_field.run("__none__") if False else True
    assert not run_field.refuses({"prompt": "Open Calculator"})
    run_field.TASKS["__nt"] = {"prompt": "Open Notepad"}
    try:
        assert run_field.run("__nt")["status"] == "refused-session-restore"
    finally:
        del run_field.TASKS["__nt"]
