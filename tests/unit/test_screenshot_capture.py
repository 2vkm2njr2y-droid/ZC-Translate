from __future__ import annotations

import base64
import io

import pytest
from PIL import Image

from app.backend.services import screenshot


def _image(width: int = 40, height: int = 20) -> Image.Image:
    return Image.new("RGB", (width, height), "#336699")


def test_encode_image_returns_png_data_url(monkeypatch):
    monkeypatch.setattr(screenshot, "_pil", lambda: (Image, None))
    payload = screenshot._encode_image(_image())
    assert payload["ok"] is True
    assert payload["width"] == 40
    assert payload["height"] == 20
    assert payload["data_url"].startswith("data:image/png;base64,")
    raw = base64.b64decode(payload["data_url"].split(",", 1)[1])
    assert Image.open(io.BytesIO(raw)).size == (40, 20)


def test_encode_image_downscales_large_capture(monkeypatch):
    monkeypatch.setattr(screenshot, "_pil", lambda: (Image, None))
    payload = screenshot._encode_image(_image(5000, 100))
    assert payload["width"] == 4096
    assert payload["height"] == 82


def test_capture_success(monkeypatch):
    monkeypatch.setattr(screenshot, "_platform_supported", lambda: True)
    monkeypatch.setattr(screenshot, "_clipboard_sequence", lambda: 2)
    monkeypatch.setattr(screenshot, "_snip_windows", lambda: set())
    monkeypatch.setattr(screenshot, "_read_new_clipboard_image", lambda _seq: _image())
    monkeypatch.setattr(screenshot, "_launch_snip", lambda: None)
    monkeypatch.setattr(screenshot, "_sleep", lambda _seconds: None)
    payload = screenshot.capture_native_region()
    assert payload["width"] == 40
    assert payload["data_url"].startswith("data:image/png;base64,")


def test_capture_cancelled_when_overlay_closes(monkeypatch):
    monkeypatch.setattr(screenshot, "_platform_supported", lambda: True)
    monkeypatch.setattr(screenshot, "_clipboard_sequence", lambda: 1)
    monkeypatch.setattr(screenshot, "_read_clipboard_image", lambda: None)
    monkeypatch.setattr(screenshot, "_launch_snip", lambda: None)
    monkeypatch.setattr(screenshot, "_sleep", lambda _seconds: None)

    clock = [0.0]

    def now() -> float:
        clock[0] += 0.2
        return clock[0]

    windows = iter([set(), {11}, set(), set(), set(), set()])

    def snip_windows():
        return next(windows, set())

    monkeypatch.setattr(screenshot, "_now", now)
    monkeypatch.setattr(screenshot, "_snip_windows", snip_windows)
    with pytest.raises(screenshot.CaptureCancelled):
        screenshot.capture_native_region(timeout=30.0)


def test_capture_timeout(monkeypatch):
    monkeypatch.setattr(screenshot, "_platform_supported", lambda: True)
    monkeypatch.setattr(screenshot, "_clipboard_sequence", lambda: 1)
    monkeypatch.setattr(screenshot, "_read_clipboard_image", lambda: None)
    monkeypatch.setattr(screenshot, "_snip_windows", lambda: set())
    monkeypatch.setattr(screenshot, "_launch_snip", lambda: None)
    monkeypatch.setattr(screenshot, "_sleep", lambda _seconds: None)

    clock = [0.0]

    def now() -> float:
        clock[0] += 0.5
        return clock[0]

    monkeypatch.setattr(screenshot, "_now", now)
    with pytest.raises(screenshot.CaptureTimeout):
        screenshot.capture_native_region(timeout=3.0)


def test_capture_is_serialised(monkeypatch):
    monkeypatch.setattr(screenshot, "_platform_supported", lambda: True)
    assert screenshot._capture_lock.acquire(blocking=False)
    try:
        with pytest.raises(screenshot.CaptureBusy):
            screenshot.capture_native_region()
    finally:
        screenshot._capture_lock.release()
