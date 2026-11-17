"""Config: defaults.toml < [presets.<name>] < the user's turbo-desktop.toml. Plain dicts and functions."""
from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path

DEFAULTS_PATH = Path(__file__).with_name("defaults.toml")
USER_FILE = "turbo-desktop.toml"
PRESETS = ("easy", "balanced", "strict")


def deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        out[k] = deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def user_config_path(data_dir: Path) -> Path:
    """Same order as desktop-mcp: $TURBO_DESKTOP_CONFIG, ./turbo-desktop.toml, %APPDATA%\\turbo-desktop\\, ~\\.
    If none exists the first writable default (APPDATA) is returned, which is where `setup` writes it."""
    env = os.environ.get("TURBO_DESKTOP_CONFIG")
    if env:
        return Path(env)
    appdata = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "turbo-desktop" / USER_FILE
    for p in (Path.cwd() / USER_FILE, appdata, Path.home() / USER_FILE):
        if p.exists():
            return p
    return appdata


def load_config(user_path: Path | None = None, preset: str | None = None) -> dict:
    defaults = tomllib.loads(DEFAULTS_PATH.read_text("utf-8"))
    presets = defaults.pop("presets", {})
    user = tomllib.loads(user_path.read_text("utf-8")) if user_path and user_path.exists() else {}
    name = preset or user.get("preset") or defaults.get("preset", "easy")
    if name not in presets:
        raise ValueError(f"unknown preset {name!r}; choose one of {', '.join(presets)}")
    cfg = deep_merge(deep_merge(defaults, presets[name]), user)
    cfg["preset"] = name
    return cfg


# ------------------------------------------------------------ policy helpers (plain functions)
def _any(patterns: list[str], text: str) -> bool:
    return bool(text) and any(re.search(p, text, re.I) for p in patterns)


def approval_required(cfg: dict, event: dict) -> bool:
    """Config-driven dangerous-action check. `event` keys: tool, input, window, control, action, process."""
    tool = str(event.get("tool", ""))
    if "desktop" not in tool:
        return False
    inp = event.get("input") or {}
    action = str(event.get("action") or inp.get("action") or "")
    control = " ".join(str(x) for x in (event.get("control"), inp.get("name")) if x)
    window, process = str(event.get("window") or ""), str(event.get("process") or "")
    keys = str(inp.get("keys") or "").lower()
    acting = {"click", "invoke", "press_keys", "toggle", "select", "set_value", "type", ""}
    if action not in acting:
        return False
    cats = cfg["approval"]["category"]
    for name in cfg["approval"]["enabled"]:
        c = cats.get(name)
        if c is None:
            continue
        hits = []
        if c.get("controls"):
            hits.append(_any(c["controls"], control))
        if c.get("processes"):
            hits.append(_any([f"^{p}(\\.exe)?$" for p in c["processes"]], process))
        if c.get("windows"):
            hits.append(_any(c["windows"], window))
        if c.get("keys"):
            hits.append(action == "press_keys" and keys in c["keys"])
        if hits and (all(hits) if c.get("match") == "all" else any(hits)):
            return True
    return False


def make_classifier(cfg: dict):
    def classify(event: dict) -> bool:
        try:
            return approval_required(cfg, event)
        except Exception:
            return True  # fail closed
    return classify


def default_agent_command(mode: str, claude: str | None) -> list[str]:
    if mode == "claude-stream-json":
        return [claude or "claude", "-p", "--input-format", "stream-json", "--output-format", "stream-json",
                "--verbose", "--mcp-config", "{mcp_config}", "--strict-mcp-config", "--tools", "",
                "--permission-prompt-tool", "{approval_tool}"]
    return [claude or "claude", "-p", "{task}", "--output-format", "stream-json", "--verbose"]


def write_user_config(path: Path, preset: str, phone: bool = False) -> None:
    """First-run wizard output: a short commented file; every key from defaults.toml can be added below."""
    path.parent.mkdir(parents=True, exist_ok=True)
    phone_block = ("\n# You said you will pair a phone: it reaches this PC over the same Wi-Fi (LAN).\n"
                   "[server]\nconnections = [\"local\", \"lan\"]\n") if phone else ""
    path.write_text(f'''# turbo-desktop.toml: your settings. Everything not listed here comes from the preset.
# All available keys, with explanations: hub/turbo_hub/defaults.toml
preset = "{preset}"      # easy | balanced | strict
{phone_block}
# Examples (remove the leading # to use):
# [server]
# connections = ["local", "tailscale"]   # local | lan | tailscale | cloudflare, tried in this order
# [session]
# hours = 4
# [auth]
# totp = true
# biometric = false
# [approval]
# enabled = ["permanent_delete", "payment", "send"]   # which categories ask first
# [deny_zones]
# banking = true
# [agent]
# mode = "oneshot"
# command = ["codex", "exec", "{{task}}"]
''', "utf-8")
