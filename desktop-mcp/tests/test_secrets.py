"""Secrets deny zone (hard floor) and launch_app never handing back a window that already existed.
Origin: hub field run 12:27, launch_app Notepad returned the owner's '.env - Notepad' window and the agent inspected it."""
import subprocess

import pytest

from turbo_desktop import engine, rules, security as sec
from turbo_desktop.engine import ToolError

from conftest import FIX

SECRET_TITLES = [".env - Notepad", ".env.local - Visual Studio Code", "secrets.json", "my secret notes", "credentials.csv",
                 "server.pem - Notepad", "deploy.key", "id_rsa", "vault.kdbx - KeePass", "GitHub token", "Reset password",
                 "Mật khẩu ngân hàng", "api_key list", "API-KEY.txt"]
NORMAL_TITLES = ["notes.txt - Notepad", "TurboFixture", "Calculator", ".environment", "README.md - Visual Studio Code",
                 "Downloads - File Explorer"]


@pytest.mark.parametrize("title", SECRET_TITLES)
def test_secret_titles_match(title):
    assert sec.secret_reason(title)


@pytest.mark.parametrize("title", NORMAL_TITLES)
def test_normal_titles_do_not_match(title):
    assert sec.secret_reason(title) is None


def test_password_manager_processes():
    assert sec.secret_reason("Vault", "Bitwarden") == "password manager"
    assert sec.secret_reason("Vault", "KeePassXC.exe") == "password manager"


def test_users_can_add_patterns_but_not_remove_builtins(tmp_path, monkeypatch):
    cfg = tmp_path / "turbo-desktop.toml"
    cfg.write_text('[desktop]\npreset = "easy"\n[desktop.secrets]\npatterns = ["payroll"]\n'
                   '[desktop.overrides.password-managers]\ndisabled = true\n', encoding="utf-8")
    monkeypatch.setenv("TURBO_DESKTOP_CONFIG", str(cfg))
    assert sec.secret_reason("Payroll 2026.xlsx")                 # added
    assert sec.secret_reason(".env - Notepad")                    # built-in still there
    # nothing in the config can remove a built-in: 'patterns' is additive only, and there is no removal key
    cfg.write_text('[desktop.secrets]\npatterns = []\nremove = [".env"]\nenabled = false\n', encoding="utf-8")
    assert sec.secret_reason(".env - Notepad")
    assert sec.secret_reason("Vault", "bitwarden")


def start_titled(launch_app, title):
    return launch_app("turbo_editor.exe", "--title", title)


def test_secret_window_is_listed_hidden_and_never_read(launch_app, desktop):
    d = start_titled(launch_app, ".env - Notepad")
    row = [w for w in desktop.windows_list() if w["hwnd"] == d["hwnd"]][0]
    assert row["title"] == sec.HIDDEN_TITLE == "[hidden: secret window]"
    assert row["process"] == "turbo_editor" and row["denied"]
    for call in (lambda: desktop.inspect(row["id"]),
                 lambda: desktop.screenshot(row["id"]),
                 lambda: desktop.act(row["id"], "read", name="Text editor"),
                 lambda: desktop.act(row["id"], "set_value", name="Text editor", text="x"),
                 lambda: desktop.act(row["id"], "click", name="File"),
                 lambda: desktop.act(row["id"], "press_keys", keys="a"),
                 lambda: desktop.wait_for(window=row["id"], text="Text editor", timeout=1)):
        with pytest.raises(ToolError) as e:
            call()
        assert e.value.extra["denied"] == "secret-window" and e.value.extra["rule"] == "secret-window"
        assert ".env" not in str(e.value)                              # the message does not leak the title either
    # the real title never appears in any listing
    assert all(".env" not in w["title"] for w in desktop.windows_list())


def test_secret_window_through_mcp_tools(launch_app):
    """Same through the server functions (JSON results)."""
    import json
    from turbo_desktop import server
    d = start_titled(launch_app, "my secrets.txt")
    listing = server._guard(lambda: server._j(server.desk().windows_list()))
    assert "[hidden: secret window]" in listing and "secrets" not in listing.lower().replace("secret window", "")
    out = json.loads(server._guard(lambda: server.desk().inspect("process:turbo_editor")))
    assert out["ok"] is False and out["denied"] == "secret-window" and out["rule"] == "secret-window"
    server.desk().close_launched()


class FakePopen:
    def __init__(self, *a, **k):
        pass


def test_launch_never_returns_a_preexisting_window(monkeypatch, desktop):
    existing = {"id": "w9", "hwnd": 4242, "title": "notes - Editor", "process": "turbo_editor", "pid": 1, "focused": True}
    monkeypatch.setattr(engine.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(desktop, "windows_list", lambda *a, **k: [dict(existing)])
    exe = str(FIX / "turbo_editor.exe")
    r = desktop.launch(exe, wait=0.3)
    assert r["reused_existing_window"] is True and r["windows"] == []         # no ref handed out
    assert 4242 not in desktop.launched                                       # and we do not own it
    r = desktop.launch(exe, wait=0.3, return_existing=True)                   # only when asked explicitly
    assert r["reused_existing_window"] is True and r["windows"][0]["id"] == "w9"


def test_launch_of_a_real_new_window_has_no_reuse_flag(desktop):
    r = desktop.launch(str(FIX / "turbo_editor.exe"), "--title harmless", wait=8)
    try:
        assert r["ok"] and r["windows"] and "reused_existing_window" not in r
    finally:
        desktop.close_launched()


def test_session_restore_rule_then_secret_window_still_blocked(launch_app, desktop):
    """Whatever the preset, an inspect on a secret window is refused (Balanced and Strict too)."""
    import os
    d = start_titled(launch_app, "credentials - Notepad")
    for preset in ("easy", "balanced", "strict"):
        os.environ["TURBO_DESKTOP_PRESET"] = preset
        with pytest.raises(ToolError) as e:
            desktop.inspect(d["id"])
        assert e.value.extra["denied"] == "secret-window"
