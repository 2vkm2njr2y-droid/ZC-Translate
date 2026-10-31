from __future__ import annotations

import contextlib

from app.shell import overlay as overlay_module
from app.shell.geometry import Rect


class FakeWindow:
    def __init__(self) -> None:
        self.scripts: list[str] = []
        self.destroyed = 0
        self.shown = 0

    def evaluate_js(self, script):
        self.scripts.append(script)
        return None

    def show(self):
        self.shown += 1

    def destroy(self):
        self.destroyed += 1


def make_overlay(monkeypatch):
    window = FakeWindow()
    calls: dict[str, object] = {}
    monkeypatch.setattr(overlay_module.win32, "get_hwnd", lambda _window: 123)
    monkeypatch.setattr(overlay_module.win32, "apply_no_activate_tool_style", lambda _hwnd: None)
    monkeypatch.setattr(
        overlay_module.win32,
        "apply_native_border_policy",
        lambda hwnd: calls.setdefault("border", []).append(hwnd),
    )
    monkeypatch.setattr(
        overlay_module.win32,
        "get_monitor_geometry",
        lambda _x, _y: (Rect(0, 0, 1600, 900), Rect(0, 0, 1600, 900), 1.0),
    )
    monkeypatch.setattr(
        overlay_module.win32, "per_monitor_dpi_context", lambda: contextlib.nullcontext()
    )
    monkeypatch.setattr(
        overlay_module.win32,
        "set_window_rect",
        lambda hwnd, rect, show=False: calls.setdefault("rects", []).append((rect, show)),
    )
    monkeypatch.setattr(
        overlay_module.win32,
        "show_window_no_activate",
        lambda hwnd, rect: calls.setdefault("show", []).append(rect),
    )
    monkeypatch.setattr(
        overlay_module.win32,
        "apply_round_region",
        lambda *args: calls.setdefault("regions", []).append(args),
    )
    monkeypatch.setattr(
        overlay_module.win32, "hide_window", lambda hwnd: calls.setdefault("hide", []).append(hwnd)
    )
    controller = overlay_module.OverlayController(window)
    return controller, window, calls


def test_attach_suppresses_native_border(monkeypatch):
    controller, _window, calls = make_overlay(monkeypatch)
    assert controller.attach() is True
    assert calls["border"] == [123]


def test_show_positions_and_uses_escaped_payload(monkeypatch):
    controller, window, calls = make_overlay(monkeypatch)
    assert controller.attach() is True
    assert controller.show('你好 "world"\nnext', Rect(100, 300, 500, 340)) is True
    assert controller.visible is True
    assert calls["show"]
    show_script = next(script for script in window.scripts if "zcOverlay.show" in script)
    assert r"\u4f60\u597d" in show_script
    assert r"\"world\"" in show_script
    assert "\\n" in show_script
    assert calls["rects"]


def test_resize_repositions_and_clamps(monkeypatch):
    controller, _window, calls = make_overlay(monkeypatch)
    controller.attach()
    controller.show("hello", Rect(200, 400, 500, 430))
    before = len(calls["rects"])
    assert controller.resize(360, 200) is True
    assert len(calls["rects"]) > before
    rect = calls["rects"][-1][0]
    assert rect.width == 360
    assert rect.height == 200


def test_hide_cancels_and_hides(monkeypatch):
    controller, window, calls = make_overlay(monkeypatch)
    controller.attach()
    controller.show("hello", Rect(200, 400, 500, 430))
    controller.hide()
    assert controller.visible is False
    assert "zcOverlay.cancel" in window.scripts[-1]
    assert calls["hide"] == [123]


def test_contains_point_uses_last_rect(monkeypatch):
    controller, _window, _calls = make_overlay(monkeypatch)
    controller.attach()
    controller.show("hello", Rect(200, 400, 500, 430))
    assert controller.contains_point(250, 350)
    assert not controller.contains_point(1200, 800)


def test_destroy_destroys_window(monkeypatch):
    controller, window, _calls = make_overlay(monkeypatch)
    controller.attach()
    controller.destroy()
    assert window.destroyed == 1
