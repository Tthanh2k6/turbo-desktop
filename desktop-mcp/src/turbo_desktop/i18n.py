"""Lightweight i18n helper for turbo-desktop-mcp (TURBO_DESKTOP_LANG=en|vi, default en)."""
from __future__ import annotations

import os

SUPPORTED_LANGS = ("en", "vi")
DEFAULT_LANG = "en"

MESSAGES: dict[str, dict[str, str]] = {
    "banner": {
        "en": "AI is controlling the PC · keyboard/mouse paused · Esc ×3 to take over · Ctrl+Alt+Shift+K to stop",
        "vi": "AI đang điều khiển máy · bàn phím/chuột tạm khoá · Esc ×3 để lấy lại · Ctrl+Alt+Shift+K để dừng",
    },
    "remote_banner": {
        "en": "AI is working on a phone command · Esc ×3 to take over · Ctrl+Alt+Shift+K to stop",
        "vi": "AI đang làm việc theo lệnh từ điện thoại · Esc ×3 để lấy lại · Ctrl+Alt+Shift+K để dừng",
    },
    "screen_view": {
        "en": "Phone is viewing the screen",
        "vi": "Điện thoại đang xem màn hình",
    },
    "end_notice": {
        "en": "Keyboard and mouse returned to you",
        "vi": "Đã trả lại bàn phím và chuột cho bạn",
    },
    "prompt_title": {
        "en": "turbo-desktop: approve action?",
        "vi": "turbo-desktop: duyệt thao tác?",
    },
    "prompt_body": {
        "en": (
            'The AI wants to {action} "{control}" in "{window}".\n\n'
            "Why you are asked: {reason} (rule: {rule})\n\n"
            "Allow this one action?"
        ),
        "vi": (
            'AI muốn {action} "{control}" trong "{window}".\n\n'
            "Lý do cần duyệt: {reason} (quy tắc: {rule})\n\n"
            "Cho phép thao tác này?"
        ),
    },
    "takeover_error": {
        "en": "the owner took the keyboard and mouse back (Esc x3): run paused",
        "vi": "chủ máy đã lấy lại bàn phím và chuột (Esc x3): tạm dừng chạy",
    },
    "stop_hotkey_error": {
        "en": "STOP hotkey pressed: all actions blocked",
        "vi": "đã bấm phím nóng STOP: mọi thao tác bị chặn",
    },
    "stop_active_error": {
        "en": "emergency stop active: all actions blocked until resumed from the phone",
        "vi": "dừng khẩn cấp đang bật: mọi thao tác bị chặn cho đến khi mở lại từ điện thoại",
    },
    "stop_wait_error": {
        "en": "emergency stop active: wait cancelled",
        "vi": "dừng khẩn cấp đang bật: đã huỷ chờ",
    },
    "stop_launch_error": {
        "en": "emergency stop active",
        "vi": "dừng khẩn cấp đang bật",
    },
    "owner_busy_error": {
        "en": "owner is using the PC (input {idle:.1f}s ago); real input refused",
        "vi": "chủ máy đang dùng máy (có thao tác {idle:.1f}s trước); từ chối gửi phím/chuột thật",
    },
    "approval_denied_error": {
        "en": "approval denied or timed out: {reason}",
        "vi": "từ chối duyệt hoặc hết thời gian chờ: {reason}",
    },
    "secret_window_error": {
        "en": "secret window: its contents are never read or acted on",
        "vi": "cửa sổ bí mật: không bao giờ đọc hoặc thao tác trên nội dung này",
    },
    "elevated_window_error": {
        "en": "window belongs to an elevated process; UIPI blocks input from a normal process",
        "vi": "cửa sổ thuộc tiến trình quyền quản trị (elevated); UIPI chặn thao tác từ tiến trình thường",
    },
}


def get_lang(lang: str | None = None) -> str:
    """Return 'en' (default) or 'vi' based on explicit argument or TURBO_DESKTOP_LANG."""
    raw = (lang if lang is not None else os.environ.get("TURBO_DESKTOP_LANG", DEFAULT_LANG)) or DEFAULT_LANG
    norm = str(raw).strip().lower()
    if norm.startswith("vi"):
        return "vi"
    return "en"


def msg(key: str, *, lang: str | None = None, **kwargs) -> str:
    """Return the localized string for `key` in the active language ('en' or 'vi')."""
    entry = MESSAGES[key]
    chosen = get_lang(lang)
    template = entry.get(chosen) or entry[DEFAULT_LANG]
    return template.format(**kwargs) if kwargs else template


t = msg


def all_variants(key: str) -> set[str]:
    """Return all language variants for `key`."""
    return set(MESSAGES[key].values())


def is_msg(key: str, text: str | None) -> bool:
    """Return True if `text` matches any language variant of `key`."""
    return bool(text and text in MESSAGES.get(key, {}).values())


def format_approval_prompt(summary: dict, *, lang: str | None = None) -> tuple[str, str]:
    """Return (title, body) for the local Windows MessageBoxW approval dialog."""
    chosen = get_lang(lang)
    title = msg("prompt_title", lang=chosen)
    body = msg(
        "prompt_body",
        lang=chosen,
        action=summary.get("action") or "?",
        control=summary.get("control") or "?",
        window=summary.get("window") or "?",
        reason=summary.get("reason") or "?",
        rule=summary.get("rule") or "?",
    )
    return title, body
