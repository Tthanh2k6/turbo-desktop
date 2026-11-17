"""Fetch Material Symbols Rounded (24px, wght 400) path data once into _icons.json. Apache-2.0, google/material-design-icons."""
import json, re, urllib.request
from pathlib import Path
NAMES = ["desktop_windows", "assignment", "verified_user", "history", "settings", "stop", "stop_circle", "qr_code_scanner",
         "content_copy", "visibility", "visibility_off", "open_in_new", "fingerprint", "lock", "lock_open", "pan_tool",
         "play_arrow", "check_circle", "error", "schedule", "timer", "timer_off", "arrow_back", "chevron_right", "language",
         "key", "wifi", "power_settings_new", "battery_saver", "link_off", "send", "keyboard", "mouse", "touch_app", "info",
         "help", "refresh", "cloud", "progress_activity", "gpp_maybe", "shield", "flag", "chat_bubble", "apps", "check",
         "close", "content_paste", "radio_button_checked", "radio_button_unchecked", "smartphone", "tune", "visibility",
         "terminal", "calculate", "edit_note", "vpn_lock", "expand_more", "pending", "list_alt", "web_asset", "pin", "password", "dialpad"]
FILL = {"check_circle", "stop_circle", "verified_user", "settings", "assignment", "desktop_windows", "radio_button_checked",
        "lock", "error", "gpp_maybe", "info", "history", "pan_tool", "chat_bubble", "help", "timer_off", "key", "shield"}
BASE = "https://raw.githubusercontent.com/google/material-design-icons/master/symbols/web/{n}/materialsymbolsrounded/{n}{f}_24px.svg"
out, here = {}, Path(__file__).parent
for n in dict.fromkeys(NAMES):
    for f in ([""] + (["_fill1"] if n in FILL else [])):
        try:
            svg = urllib.request.urlopen(BASE.format(n=n, f=f), timeout=20).read().decode()
            out[n + f] = " ".join(re.findall(r'd="([^"]+)"', svg))
        except Exception as e:
            print("miss", n + f, e)
(here / "_icons.json").write_text(json.dumps(out), encoding="utf-8")
print(len(out), "icons")
