import os
from pathlib import Path

import pytest

from turbo_desktop import rules, security as sec

DEFAULT = rules._read_toml(rules.DEFAULT_RULES_FILE)


def rs(preset, user=None):
    return rules.build_ruleset(DEFAULT, user, preset)


def lvl(preset, name, role="button", process="someapp", action="click", user=None, **kw):
    return sec.classify_action(process=process, window_title="Some window", control_name=name, control_role=role,
                               action=action, ruleset=rs(preset, user), **kw).level


# preset, control name, expected level
NAME_TABLE = [
    # Easy: only permanent delete, payment, uninstall are ask
    ("easy", "Permanently delete", "ask"), ("easy", "Xoá vĩnh viễn", "ask"), ("easy", "Empty Recycle Bin", "ask"),
    ("easy", "Pay now", "ask"), ("easy", "Thanh toán", "ask"), ("easy", "Uninstall", "ask"), ("easy", "Gỡ cài đặt", "ask"),
    ("easy", "Send", "allow"), ("easy", "Gửi", "allow"), ("easy", "Delete", "allow"), ("easy", "Save", "allow"),
    ("easy", "Submit", "allow"),
    # Balanced adds the generic commit words (vi and en)
    ("balanced", "Send", "ask"), ("balanced", "Gửi", "ask"), ("balanced", "Xoá", "ask"), ("balanced", "Delete", "ask"),
    ("balanced", "Đăng xuất", "ask"), ("balanced", "Publish", "ask"), ("balanced", "Shut down", "ask"),
    ("balanced", "Save", "allow"), ("balanced", "Cancel", "allow"), ("balanced", "Hủy", "allow"),
    ("balanced", "Pay now", "ask"),
    ("strict", "Send", "ask"), ("strict", "Gửi", "ask"), ("strict", "Save", "allow"),
    # whole words only: "Resend" / "Compost" must not match
    ("balanced", "Compost", "allow"), ("balanced", "Posting history", "allow"),
]


@pytest.mark.parametrize("preset,name,expected", NAME_TABLE)
def test_name_table(preset, name, expected):
    assert lvl(preset, name) == expected


def test_decision_reports_rule_id():
    d = sec.classify_action(process="x", window_title="t", control_name="Thanh toán", control_role="button",
                            action="click", ruleset=rs("easy"))
    assert d.level == "ask" and d.rule == "payment" and d.reason


def test_automation_id_and_tooltip_count():
    assert lvl("balanced", "", automation_id="btnSend") == "allow"      # "btnSend" has no word boundary
    assert lvl("balanced", "", automation_id="send") == "ask"
    assert lvl("balanced", "", help_text="Delete this item") == "ask"
    assert lvl("easy", "OK", help_text="Pay now") == "ask"


def test_read_only_actions_never_ask():
    for a in ("read", "scroll", "focus", "expand"):
        assert lvl("balanced", "Delete", action=a) == "allow"


def test_confirm_in_danger_dialog_strict_only():
    kw = dict(dialog_title="Confirm delete")
    assert lvl("strict", "OK", **kw) == "ask"
    assert lvl("balanced", "OK", **kw) == "allow"
    assert lvl("easy", "OK", **kw) == "allow"


def test_unnamed_button_unknown_app_strict_only():
    assert lvl("strict", "", process="randomapp") == "ask"
    assert lvl("strict", "", process="notepad") == "allow"          # allowlisted app
    assert lvl("balanced", "", process="randomapp") == "allow"
    assert lvl("strict", "", process="randomapp", help_text="Close panel") == "allow"  # tooltip names it


@pytest.mark.parametrize("process,preset,expected", [
    ("powershell", "easy", "allow"), ("powershell", "balanced", "ask"), ("regedit", "balanced", "ask"),
    ("windowsterminal", "strict", "ask"), ("cmd", "balanced", "ask"), ("taskmgr", "balanced", "ask"),
    ("notepad", "balanced", "allow"),
])
def test_shells_and_admin_tools(process, preset, expected):
    assert lvl(preset, "Anything", process=process) == expected


def test_enter_rules():
    assert lvl("balanced", "", process="discord", action="press_keys", keys="{Enter}") == "ask"
    assert lvl("balanced", "Message box", process="randomapp", action="press_keys", keys="{Enter}") == "ask"
    assert lvl("balanced", "Text editor", process="notepad", action="press_keys", keys="{Enter}") == "allow"
    assert lvl("easy", "", process="discord", action="press_keys", keys="{Enter}") == "allow"
    assert lvl("strict", "Body", process="randomapp", action="press_keys", keys="{Enter}", multiline=True) == "ask"
    assert lvl("strict", "Body", process="notepad", action="press_keys", keys="{Enter}", multiline=True) == "allow"


def test_settings_accounts_privacy():
    for preset in ("easy", "balanced", "strict"):
        d = sec.classify_action(process="SystemSettings", window_title="Settings", control_name="Toggle",
                                control_role="button", action="click", window_context="Privacy & security > Camera",
                                ruleset=rs(preset))
        assert d.level == "ask" and d.rule == "settings-accounts-privacy"
    d = sec.classify_action(process="SystemSettings", window_title="Settings", control_name="Toggle", control_role="button",
                            action="click", window_context="System > Display", ruleset=rs("easy"))
    assert d.level == "allow"


@pytest.mark.parametrize("process,title,preset,expected", [
    ("Bitwarden", "Bitwarden", "easy", "deny"), ("keepassxc", "Database", "easy", "deny"),
    ("consent", "User Account Control", "easy", "deny"), ("LogonUI", "", "easy", "deny"),
    ("SecurityHealthUI", "Windows Security", "easy", "deny"),
    ("chrome", "Vietcombank - Internet Banking", "easy", "allow"),
    ("chrome", "Vietcombank - Internet Banking", "strict", "deny"),
    ("notepad", "notes.txt - Notepad", "strict", "allow"),
])
def test_deny_zones(process, title, preset, expected):
    d = sec.classify_action(process=process, window_title=title, control_name="x", action="click", ruleset=rs(preset))
    assert d.level == expected
    # deny zones also block just looking at the window
    d2 = sec.classify_action(process=process, window_title=title, action="read", ruleset=rs(preset))
    assert d2.level == expected


def test_password_floor_is_not_configurable():
    # user tries to switch every rule off: the code floor still denies
    user = {"desktop": {"preset": "easy", "overrides": {r["id"]: {"disabled": True} for r in DEFAULT["rules"]}}}
    d = sec.classify_action(process="x", window_title="t", control_name="Password", control_role="edit",
                            action="type", is_password=True, ruleset=rs("easy", user))
    assert d.level == "deny" and d.rule == "password-field"
    d = sec.classify_action(process="x", window_title="t", action="read", is_password=True, ruleset=rs("easy"))
    assert d.level == "deny"


# ---------------------------------------------------------------- merge with the user's file

def test_user_rule_wins_and_override_and_disable():
    user = {"desktop": {"preset": "easy",
                        "rules": [{"id": "my-ask-save", "level": "ask", "name": "^Save$", "why": "mine"}],
                        "overrides": {"payment": {"level": "deny"}, "uninstall": {"disabled": True}},
                        "apps": {"allowlist": ["MyApp"]}}}
    r = rs("easy", user)
    assert "myapp" in r.allowlist
    d = sec.classify_action(process="x", window_title="t", control_name="Save", control_role="button", ruleset=r)
    assert (d.level, d.rule, d.reason) == ("ask", "my-ask-save", "mine")
    d = sec.classify_action(process="x", window_title="t", control_name="Pay now", control_role="button", ruleset=r)
    assert d.level == "deny" and d.rule == "payment"
    d = sec.classify_action(process="x", window_title="t", control_name="Uninstall", control_role="button", ruleset=r)
    assert d.level == "allow"


def test_user_allow_rule_can_relax_a_balanced_rule():
    user = {"rules": [{"id": "ok-send-in-notes", "level": "allow", "process": ["mynotes"], "name": "send"}]}
    assert sec.classify_action(process="mynotes", window_title="t", control_name="Send", action="click",
                               ruleset=rs("balanced", user)).level == "allow"
    assert sec.classify_action(process="other", window_title="t", control_name="Send", action="click",
                               ruleset=rs("balanced", user)).level == "ask"


def test_preset_from_user_file_and_env(tmp_path, monkeypatch):
    cfg = tmp_path / "turbo-desktop.toml"
    cfg.write_text('[desktop]\npreset = "balanced"\n', encoding="utf-8")
    monkeypatch.delenv("TURBO_DESKTOP_PRESET", raising=False)
    assert rules.load_ruleset(config_path=cfg).preset == "balanced"
    monkeypatch.setenv("TURBO_DESKTOP_PRESET", "strict")
    assert rules.load_ruleset(config_path=cfg).preset == "strict"
    monkeypatch.setenv("TURBO_DESKTOP_PRESET", "nonsense")
    assert rules.load_ruleset(config_path=cfg).preset == "easy"


def test_every_default_rule_has_id_level_presets():
    ids = set()
    for r in DEFAULT["rules"]:
        assert r["id"] not in ids
        ids.add(r["id"])
        assert r["level"] in ("ask", "deny", "allow")
        assert set(r["presets"]) <= set(rules.PRESETS)


def test_config_lookup_order(tmp_path, monkeypatch):
    """Same order as the hub: env, ./turbo-desktop.toml, %APPDATA%/turbo-desktop/, ~/turbo-desktop.toml."""
    cwd, appdata, home = tmp_path / "cwd", tmp_path / "appdata", tmp_path / "home"
    (appdata / "turbo-desktop").mkdir(parents=True)
    cwd.mkdir()
    home.mkdir()
    monkeypatch.chdir(cwd)
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.setattr(Path, "home", classmethod(lambda c: home))
    monkeypatch.delenv("TURBO_DESKTOP_CONFIG", raising=False)
    assert rules.find_user_config() is None
    (home / "turbo-desktop.toml").write_text("", encoding="utf-8")
    assert rules.find_user_config() == home / "turbo-desktop.toml"
    (appdata / "turbo-desktop" / "turbo-desktop.toml").write_text("", encoding="utf-8")
    assert rules.find_user_config() == appdata / "turbo-desktop" / "turbo-desktop.toml"
    (cwd / "turbo-desktop.toml").write_text("", encoding="utf-8")
    assert rules.find_user_config() == cwd / "turbo-desktop.toml"
    env_file = tmp_path / "env.toml"
    env_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("TURBO_DESKTOP_CONFIG", str(env_file))
    assert rules.find_user_config() == env_file
    monkeypatch.setenv("TURBO_DESKTOP_CONFIG", str(tmp_path / "missing.toml"))
    assert rules.find_user_config() is None


def test_hub_classify_dict():
    d = sec.classify({"process": "x", "title": "t"}, {"name": "Thanh toán", "role": "button"}, "click")
    assert d["dangerous"] is True and d["level"] == "ask" and d["rule"] == "payment"
