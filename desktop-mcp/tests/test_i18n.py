"""Unit tests for i18n (TURBO_DESKTOP_LANG=en|vi, default en)."""
from __future__ import annotations

import pytest

from turbo_desktop import border as bd, i18n, inputlock as il, security as sec
from turbo_desktop.engine import Desktop, OwnerBusy, ToolError


def test_default_lang_is_english(monkeypatch):
    monkeypatch.delenv("TURBO_DESKTOP_LANG", raising=False)
    assert i18n.get_lang() == "en"
    assert il.BANNER_TEXT == (
        "AI is controlling the PC · keyboard/mouse paused · Esc ×3 to take over · Ctrl+Alt+Shift+K to stop"
    )
    assert il.REMOTE_BANNER_TEXT == (
        "AI is working on a phone command · Esc ×3 to take over · Ctrl+Alt+Shift+K to stop"
    )
    assert il.SCREEN_VIEW_TEXT == "Phone is viewing the screen"
    assert il.END_TEXT == "Keyboard and mouse returned to you"
    assert sec.PROMPT_TITLE == "turbo-desktop: approve action?"
    assert sec.PROMPT_TITLE.lower() in sec.OWNER_APPROVAL_TITLES

    title, body = i18n.format_approval_prompt({
        "action": "click",
        "control": "Pay now",
        "window": "Checkout",
        "reason": "Payment.",
        "rule": "payment",
    })
    assert title == "turbo-desktop: approve action?"
    assert 'The AI wants to click "Pay now" in "Checkout".' in body
    assert "Why you are asked: Payment. (rule: payment)" in body
    assert "Allow this one action?" in body


def test_vietnamese_lang_mode(monkeypatch):
    monkeypatch.setenv("TURBO_DESKTOP_LANG", "vi")
    assert i18n.get_lang() == "vi"
    assert il.BANNER_TEXT == (
        "AI đang điều khiển máy · bàn phím/chuột tạm khoá · Esc ×3 để lấy lại · Ctrl+Alt+Shift+K để dừng"
    )
    assert il.REMOTE_BANNER_TEXT == (
        "AI đang làm việc theo lệnh từ điện thoại · Esc ×3 để lấy lại · Ctrl+Alt+Shift+K để dừng"
    )
    assert il.SCREEN_VIEW_TEXT == "Điện thoại đang xem màn hình"
    assert il.END_TEXT == "Đã trả lại bàn phím và chuột cho bạn"
    assert sec.PROMPT_TITLE == "turbo-desktop: duyệt thao tác?"
    assert sec.PROMPT_TITLE.lower() in sec.OWNER_APPROVAL_TITLES

    title, body = i18n.format_approval_prompt({
        "action": "click",
        "control": "Thanh toán",
        "window": "Giỏ hàng",
        "reason": "Payment.",
        "rule": "payment",
    })
    assert title == "turbo-desktop: duyệt thao tác?"
    assert 'AI muốn click "Thanh toán" trong "Giỏ hàng".' in body
    assert "Lý do cần duyệt: Payment. (quy tắc: payment)" in body
    assert "Cho phép thao tác này?" in body


@pytest.mark.parametrize("raw,expected", [
    (None, "en"),
    ("", "en"),
    ("en", "en"),
    ("EN-US", "en"),
    ("fr", "en"),
    ("vi", "vi"),
    ("VI", "vi"),
    ("vi-VN", "vi"),
    ("vi_VN", "vi"),
])
def test_get_lang_normalization(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv("TURBO_DESKTOP_LANG", raising=False)
    else:
        monkeypatch.setenv("TURBO_DESKTOP_LANG", raw)
    assert i18n.get_lang() == expected


def test_inputlock_and_state_bridge_respect_lang(tmp_path, monkeypatch):
    # 1. Default English
    monkeypatch.delenv("TURBO_DESKTOP_LANG", raising=False)
    lock_en = il.InputLock(banner_class="TurboDesktopBannerI18nEn")
    assert lock_en._text == "AI is controlling the PC · keyboard/mouse paused · Esc ×3 to take over · Ctrl+Alt+Shift+K to stop"
    lock_en.set_screen_view(True, start_thread=False)
    assert lock_en._text == "Phone is viewing the screen"
    lock_en.set_screen_view(False, start_thread=False)
    assert lock_en._text == "AI is controlling the PC · keyboard/mouse paused · Esc ×3 to take over · Ctrl+Alt+Shift+K to stop"

    # 2. Switch to Vietnamese
    monkeypatch.setenv("TURBO_DESKTOP_LANG", "vi")
    lock_vi = il.InputLock(banner_class="TurboDesktopBannerI18nVi")
    assert lock_vi._text == "AI đang điều khiển máy · bàn phím/chuột tạm khoá · Esc ×3 để lấy lại · Ctrl+Alt+Shift+K để dừng"
    lock_vi.set_screen_view(True, start_thread=False)
    assert lock_vi._text == "Điện thoại đang xem màn hình"
    lock_vi.set_screen_view(False, start_thread=False)
    assert lock_vi._text == "AI đang điều khiển máy · bàn phím/chuột tạm khoá · Esc ×3 để lấy lại · Ctrl+Alt+Shift+K để dừng"

    ind = bd.Indicator(disabled_by_env=True, state_dir=tmp_path)
    bridge = il.StateBridge(lock=lock_vi, indicator=ind, state_dir=tmp_path, now=lambda: 1000.0, allow_windows=False)
    sec.atomic_write_json(tmp_path / "screen_view.json", {"until": 1005.0})
    bridge.tick()
    assert bridge.banner_text == "Điện thoại đang xem màn hình"
    assert lock_vi._text == "Điện thoại đang xem màn hình"


def test_engine_error_messages_in_en_and_vi(monkeypatch):
    # OwnerBusy message in en and vi
    monkeypatch.delenv("TURBO_DESKTOP_LANG", raising=False)
    monkeypatch.setenv("TURBO_DESKTOP_IDLE_WAIT", "0.05")
    dt = Desktop(idle_fn=lambda: 1.2, sleep_fn=lambda _: None)
    try:
        dt._own_input_at = 0
        with pytest.raises(OwnerBusy) as exc_en:
            dt.wait_owner_idle()
        assert "owner is using the PC (input 1.2s ago); real input refused" in str(exc_en.value)

        monkeypatch.setenv("TURBO_DESKTOP_LANG", "vi")
        with pytest.raises(OwnerBusy) as exc_vi:
            dt.wait_owner_idle()
        assert "chủ máy đang dùng máy (có thao tác 1.2s trước); từ chối gửi phím/chuột thật" in str(exc_vi.value)

        # STOP and secret-window messages in vi
        (sec.state_dir() / "STOP").write_text("x", encoding="utf-8")
        try:
            with pytest.raises(ToolError) as stop_vi:
                dt._guard_window({"title": "App", "process": "app"}, "click")
            assert stop_vi.value.extra.get("stopped") is True
            assert "dừng khẩn cấp đang bật" in str(stop_vi.value)
        finally:
            (sec.state_dir() / "STOP").unlink(missing_ok=True)

        with pytest.raises(ToolError) as secret_vi:
            dt._guard_window({"title": "[hidden: secret window]", "process": "notepad", "secret": True}, "inspect")
        assert secret_vi.value.extra.get("denied") == "secret-window"
        assert "cửa sổ bí mật" in str(secret_vi.value)
    finally:
        dt.close_launched()
