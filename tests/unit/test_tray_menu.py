from __future__ import annotations

from app.shell.tray import MENU_QUIT, MENU_SHOW, MENU_TOGGLE, TrayIcon


def test_menu_callbacks_and_checked_state():
    calls: list[str] = []
    tray = TrayIcon(
        on_show=lambda: calls.append("show"),
        on_toggle_selection=lambda: calls.append("toggle"),
        on_quit=lambda: calls.append("quit"),
        is_selection_enabled=lambda: True,
    )
    assert tray._safe_enabled() is True
    tray._handle_menu(MENU_SHOW)
    tray._handle_menu(MENU_TOGGLE)
    tray._handle_menu(MENU_QUIT)
    assert calls == ["show", "toggle", "quit"]


def test_menu_callback_errors_are_contained():
    def broken():
        raise RuntimeError("boom")

    tray = TrayIcon(
        on_show=broken,
        on_toggle_selection=broken,
        on_quit=broken,
        is_selection_enabled=lambda: (_ for _ in ()).throw(RuntimeError("state")),
    )
    assert tray._safe_enabled() is False
    tray._handle_menu(MENU_SHOW)
    tray._handle_menu(MENU_TOGGLE)
    tray._handle_menu(MENU_QUIT)
