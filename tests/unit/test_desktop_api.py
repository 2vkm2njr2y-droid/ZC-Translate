from __future__ import annotations

from app import desktop
from app.backend.services import screenshot


class FakeWindow:
    def __init__(self) -> None:
        self.hidden = 0
        self.shown = 0

    def hide(self):
        self.hidden += 1

    def show(self):
        self.shown += 1


def test_capture_for_screenshot_hides_and_restores(monkeypatch):
    window = FakeWindow()
    api = desktop.DesktopApi()
    monkeypatch.setattr(api, "_window", lambda: window)
    monkeypatch.setattr(
        screenshot, "capture_native_region",
        lambda: {"ok": True, "data_url": "data:image/png;base64,AA==", "width": 10, "height": 5},
    )
    result = api.capture_for_screenshot()
    assert result["ok"] is True
    assert window.hidden == 1
    assert window.shown == 1


def test_capture_for_screenshot_maps_cancel(monkeypatch):
    window = FakeWindow()
    api = desktop.DesktopApi()
    monkeypatch.setattr(api, "_window", lambda: window)

    def cancel():
        raise screenshot.CaptureCancelled("cancelled")

    monkeypatch.setattr(screenshot, "capture_native_region", cancel)
    result = api.capture_for_screenshot()
    assert result["ok"] is False
    assert result["cancelled"] is True
    assert result["code"] == "SCREENSHOT_CANCELLED"
    assert window.hidden == 1
    assert window.shown == 1


def test_close_delegates_to_shell():
    api = desktop.DesktopApi()

    class FakeShell:
        main_window = FakeWindow()

        def close_main(self):
            return {"hidden": True, "tray": True}

        def overlay_resize(self, width, height):
            return (width, height) == (360, 120)

        def overlay_hide(self):
            return True

        def copy_text(self, text):
            return text == "hello"

        def selection_status(self):
            return {"available": True, "detail": "ok"}

    shell = FakeShell()
    api.attach(shell)
    assert api.close() == {"hidden": True, "tray": True}
    assert api.overlay_resize(360, 120) is True
    assert api.overlay_hide() is True
    assert api.copy_text("hello") is True
    assert api.selection_status()["available"] is True


def test_set_frame_color_delegates():
    api = desktop.DesktopApi()

    class FakeShell:
        def set_frame_color(self, color):
            return color == "#112233"

    api.attach(FakeShell())
    assert api.set_frame_color("#112233") is True
    assert api.set_frame_color("#000000") is False


def test_bridge_without_shell_is_safe():
    api = desktop.DesktopApi()
    assert api.overlay_resize(1, 1) is False
    assert api.overlay_hide() is False
    assert api.copy_text("x") is False
    assert api.selection_status()["available"] is False
