#!/bin/sh
# Render _sheet.html to _sheet.png with headless Edge (no window). Usage: sh _render.sh
D="$(cd "$(dirname "$0")" && pwd -W 2>/dev/null || pwd)"
"/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" --headless=new --disable-gpu --hide-scrollbars \
  --force-device-scale-factor=1 --window-size=2440,2010 --screenshot="$D/_sheet.png" "file:///$D/_sheet.html" 2>/dev/null
