"""Rules engine: loads rules/default_rules.toml, merges the user's turbo-desktop.toml, decides allow/ask/deny.

Plain functions and dicts. Rule fields are documented at the top of default_rules.toml.
"""
from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

PRESETS = ("easy", "balanced", "strict")
READ_ONLY_ACTIONS = {"read", "scroll", "focus", "expand", "wait", "inspect"}
DEFAULT_RULES_FILE = Path(__file__).resolve().parents[2] / "rules" / "default_rules.toml"


@dataclass
class Decision:
    level: str = "allow"          # allow | ask | deny
    rule: str = ""                # id of the rule that matched ("" = nothing matched)
    reason: str = ""

    def to_dict(self) -> dict:
        return {"dangerous": self.level != "allow", "level": self.level, "rule": self.rule, "reason": self.reason}


@dataclass
class RuleSet:
    preset: str = "easy"
    rules: list = field(default_factory=list)
    allowlist: set = field(default_factory=set)
    session_restore: set = field(default_factory=set)
    indicator: dict = field(default_factory=lambda: {"border": True, "color": "#E0461D"})
    secret_patterns: list = field(default_factory=list)
    input_lock: dict = field(default_factory=lambda: {"mode": "real_input", "max_seconds": 60})
    source: str = ""


def _read_toml(path) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def config_candidates() -> list:
    """One lookup order shared with the hub: env var, ./turbo-desktop.toml (cwd),
    %APPDATA%/turbo-desktop/turbo-desktop.toml, ~/turbo-desktop.toml."""
    appdata = os.environ.get("APPDATA")
    return [Path.cwd() / "turbo-desktop.toml",
            *([Path(appdata) / "turbo-desktop" / "turbo-desktop.toml"] if appdata else []),
            Path.home() / "turbo-desktop.toml"]


def find_user_config() -> Path | None:
    env = os.environ.get("TURBO_DESKTOP_CONFIG")
    if env:  # the env var wins even if its file is missing (then there is no user config)
        return Path(env) if Path(env).exists() else None
    for p in config_candidates():
        if p.exists():
            return p
    return None


def build_ruleset(default: dict, user: dict | None = None, preset: str | None = None) -> RuleSet:
    """Merge: user rules first (they win), then default rules of the chosen preset, with per-rule overrides."""
    user = user or {}
    section = user.get("desktop", user)
    user_preset = section.get("preset") or user.get("preset")
    chosen = (preset or os.environ.get("TURBO_DESKTOP_PRESET") or user_preset or "easy").lower()
    if chosen not in PRESETS:
        chosen = "easy"
    overrides = {**user.get("overrides", {}), **section.get("overrides", {})}
    rules = []
    user_rules = section.get("rules") if "rules" in section else user.get("rules", [])
    for r in user_rules:
        rules.append({"presets": list(PRESETS), **r, "id": r.get("id", "user-rule")})
    for r in default.get("rules", []):
        if chosen not in r.get("presets", PRESETS):
            continue
        ov = overrides.get(r["id"], {})
        if ov.get("disabled"):
            continue
        rules.append({**r, **({"level": ov["level"]} if "level" in ov else {})})
    allow = {a.lower() for a in default.get("apps", {}).get("allowlist", [])}
    for apps_sec in (user.get("apps", {}), section.get("apps", {})):
        allow |= {a.lower() for a in apps_sec.get("allowlist", [])}
    sr = {a.lower() for a in default.get("apps", {}).get("session_restore", {}).get("processes", [])}
    for apps_sec in (user.get("apps", {}), section.get("apps", {})):
        sr |= {a.lower() for a in apps_sec.get("session_restore", {}).get("processes", [])}
    il_def = default.get("input_lock", {})
    il_user = {**user.get("input_lock", {}), **section.get("input_lock", {})}
    mode = il_user.get("mode") or il_def.get("mode", {}).get(chosen, "real_input")
    if mode not in ("off", "real_input", "whole_task"):
        mode = il_def.get("mode", {}).get(chosen, "real_input")
    secs = il_user.get("max_seconds", il_def.get("max_seconds", 60))
    rs = RuleSet(chosen, rules, allow, sr)
    secrets_sec = section.get("secrets") or user.get("secrets") or {}
    rs.secret_patterns = [str(x) for x in secrets_sec.get("patterns", [])]   # additions only
    ind_def = default.get("indicator", {})
    ind_user = {**user.get("indicator", {}), **section.get("indicator", {})}
    rs.indicator = {"border": bool(ind_user.get("border", ind_def.get("border", True))),
                    "color": str(ind_user.get("color", ind_def.get("color", "#E0461D")))}
    rs.input_lock = {"mode": mode, "max_seconds": max(5, min(300, float(secs)))}
    return rs


_cache: dict = {"key": None, "rs": None}


def load_ruleset(preset: str | None = None, config_path=None) -> RuleSet:
    cfg = Path(config_path) if config_path else find_user_config()
    key = (preset, str(cfg), cfg.stat().st_mtime if cfg else 0, os.environ.get("TURBO_DESKTOP_PRESET"),
           DEFAULT_RULES_FILE.stat().st_mtime)
    if _cache["key"] == key:
        return _cache["rs"]
    rs = build_ruleset(_read_toml(DEFAULT_RULES_FILE), _read_toml(cfg) if cfg else None, preset)
    rs.source = str(cfg) if cfg else "defaults"
    _cache.update(key=key, rs=rs)
    return rs


# ---------------------------------------------------------------- matching

DISPLAY_PROCESS_ALIASES = {
    "windowspowershell": "powershell",
    "windowspowershellx86": "powershell",
    "windowspowershellise": "powershell",
    "powershell7": "pwsh",
    "registryeditor": "regedit",
    "commandprompt": "cmd",
    "windowsterminal": "windowsterminal",
    "taskmanager": "taskmgr",
    "taskscheduler": "taskschd",
    "localgrouppolicyeditor": "gpedit",
    "editgrouppolicy": "gpedit",
    "eventviewer": "mmc",
    "computermanagement": "mmc",
    "devicemanager": "mmc",
    "services": "mmc",
    "googlechrome": "chrome",
    "microsoftedge": "msedge",
    "visualstudiocode": "code",
    "vscode": "code",
    "microsoftword": "winword",
    "word": "winword",
    "microsoftexcel": "excel",
    "excel": "excel",
    "windowssecurity": "securityhealthui",
    "calculator": "calc",
    "paint": "mspaint",
    "fileexplorer": "explorer",
}


def fold_process_name(name: str | None) -> str:
    s = (name or "").strip().lower()
    for suf in (".exe", ".lnk"):
        if s.endswith(suf) and len(s) > len(suf):
            s = s[:-len(suf)].strip()
    return re.sub(r"[\s()]+", "", s)


def _rx(pattern, text) -> bool:
    return bool(re.search(pattern, text or "", re.I))


def rule_matches(r: dict, ctx: dict, allowlist: set) -> bool:
    raw_proc = (ctx.get("process") or "").lower().removesuffix(".exe")
    folded_proc = fold_process_name(ctx.get("process"))
    mapped_proc = DISPLAY_PROCESS_ALIASES.get(folded_proc, folded_proc)
    proc_cands = {raw_proc, folded_proc, mapped_proc} - {""}
    action = ctx.get("action", "click")
    if "process" in r:
        rule_procs = {p.lower().removesuffix(".exe") for p in r["process"]} | {fold_process_name(p) for p in r["process"]}
        if not (proc_cands & rule_procs):
            return False
    if "action" in r and action not in r["action"]:
        return False
    if r.get("level") != "deny" and action in READ_ONLY_ACTIONS and not r.get("include_read"):
        return False
    if "title" in r and not _rx(r["title"], ctx.get("title")):
        return False
    if "name" in r:
        hay = " ".join(filter(None, [ctx.get("name"), ctx.get("automation_id"), ctx.get("help_text")]))
        if not _rx(r["name"], hay):
            return False
    if "role" in r and (ctx.get("role") or "").lower() not in {x.lower() for x in r["role"]}:
        return False
    if "dialog" in r and not _rx(r["dialog"], " ".join(filter(None, [ctx.get("dialog_title"), ctx.get("dialog_text")]))):
        return False
    if "context" in r and not _rx(r["context"], ctx.get("context")):
        return False
    if "keys" in r and not _rx(r["keys"], (ctx.get("keys") or "").strip()):
        return False
    if r.get("unnamed") and (ctx.get("name") or "").strip():
        return False
    if r.get("unnamed") and (ctx.get("help_text") or "").strip():
        return False
    if "multiline" in r and bool(ctx.get("multiline")) != r["multiline"]:
        return False
    if "session_restore" in r and bool(ctx.get("session_restore")) != r["session_restore"]:
        return False
    if r.get("not_allowlisted") and (proc_cands & allowlist):
        return False
    return True


def decide(ctx: dict, ruleset: RuleSet | None = None) -> Decision:
    rs = ruleset or load_ruleset()
    for r in rs.rules:
        if rule_matches(r, ctx, rs.allowlist):
            return Decision(r.get("level", "ask"), r.get("id", "?"), r.get("why", ""))
    return Decision("allow")
