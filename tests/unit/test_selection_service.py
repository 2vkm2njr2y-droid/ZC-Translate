from __future__ import annotations

from app.shell import selection as selection_module
from app.shell.geometry import Rect
from app.shell.mouse_hook import MouseEvent
from app.shell.selection import SelectionGesture, SelectionService, normalize_selection
from app.shell.uia import UiaSelection


class FakeOverlay:
    def __init__(self) -> None:
        self.visible = False
        self.shows: list[tuple[str, Rect]] = []
        self.hides = 0
        self.inside = False

    @property
    def available(self) -> bool:
        return True

    def show(self, text: str, anchor: Rect) -> bool:
        self.shows.append((text, anchor))
        self.visible = True
        return True

    def hide(self) -> None:
        self.hides += 1
        self.visible = False

    def contains_point(self, x: float, y: float, tolerance: float = 4.0) -> bool:
        return self.inside


class FakeReader:
    def __init__(self) -> None:
        self.available = True
        self.detail = "fake"
        self.value: UiaSelection | None = None
        self.calls = 0

    def load(self) -> bool:
        return True

    def read(self) -> UiaSelection | None:
        self.calls += 1
        return self.value


class FakeHook:
    def __init__(self, callback) -> None:
        self.callback = callback
        self.started = 0
        self.stopped = 0
        self.running = True

    def start(self) -> bool:
        self.started += 1
        return True

    def stop(self) -> None:
        self.stopped += 1
        self.running = False


def make_service(*, enabled: bool = True, overlay: FakeOverlay | None = None):
    overlay = overlay or FakeOverlay()
    reader = FakeReader()
    hook = FakeHook
    service = SelectionService(
        overlay,
        lambda: {"selection_translate": enabled, "target_lang": "en"},
        reader=reader,
        hook_factory=hook,
        own_pid=1,
        debounce=0.0,
    )
    captured: list[SelectionGesture] = []
    service._schedule_capture = captured.append  # type: ignore[method-assign]
    return service, overlay, reader, captured


def test_normalize_selection_filters_noise():
    assert normalize_selection("  hello\r\nworld  ") == "hello\nworld"
    assert normalize_selection("   \n\n ") is None
    assert normalize_selection("123 !!!") is None
    assert normalize_selection("中") == "中"
    assert normalize_selection("x" * 4001) is None


def test_drag_schedules_capture():
    service, _overlay, _reader, captured = make_service()
    service.process_event(MouseEvent("down", 10, 10, 1.0))
    service.process_event(MouseEvent("move", 30, 30, 1.1))
    service.process_event(MouseEvent("up", 40, 40, 1.2))
    assert len(captured) == 1
    assert captured[0].bounds.width >= 30


def test_single_click_does_not_schedule(monkeypatch):
    monkeypatch.setattr(selection_module.win32, "is_key_down", lambda _vk: False)
    service, _overlay, _reader, captured = make_service()
    service.process_event(MouseEvent("down", 10, 10, 1.0))
    service.process_event(MouseEvent("up", 10, 10, 1.1))
    assert captured == []


def test_double_click_schedules_capture(monkeypatch):
    monkeypatch.setattr(selection_module.win32, "is_key_down", lambda _vk: False)
    service, _overlay, _reader, captured = make_service()
    service.process_event(MouseEvent("down", 10, 10, 1.0))
    service.process_event(MouseEvent("up", 10, 10, 1.1))
    service.process_event(MouseEvent("down", 10, 10, 1.2))
    service.process_event(MouseEvent("up", 10, 10, 1.3))
    assert len(captured) == 1
    assert captured[0].double_click is True


def test_shift_click_schedules_capture(monkeypatch):
    monkeypatch.setattr(selection_module.win32, "is_key_down", lambda _vk: True)
    service, _overlay, _reader, captured = make_service()
    service.process_event(MouseEvent("down", 10, 10, 1.0))
    service.process_event(MouseEvent("up", 10, 10, 1.1))
    assert len(captured) == 1
    assert captured[0].shift is True


def test_click_outside_visible_overlay_hides_it():
    overlay = FakeOverlay()
    overlay.visible = True
    service, _overlay, _reader, _captured = make_service(overlay=overlay)
    service.process_event(MouseEvent("down", 10, 10, 1.0))
    assert overlay.hides == 1


def test_wheel_outside_visible_overlay_hides_it():
    overlay = FakeOverlay()
    overlay.visible = True
    service, _overlay, _reader, _captured = make_service(overlay=overlay)
    service.process_event(MouseEvent("wheel", 10, 10, 1.0))
    assert overlay.hides == 1


def test_click_inside_overlay_is_ignored():
    overlay = FakeOverlay()
    overlay.visible = True
    overlay.inside = True
    service, _overlay, _reader, captured = make_service(overlay=overlay)
    service.process_event(MouseEvent("down", 10, 10, 1.0))
    service.process_event(MouseEvent("up", 10, 10, 1.1))
    assert captured == []
    assert overlay.hides == 0


def _gesture() -> SelectionGesture:
    return SelectionGesture(
        down=(10, 10),
        up=(200, 30),
        bounds=Rect(10, 10, 200, 30),
        double_click=False,
        shift=False,
        at=1.0,
    )


def test_deliver_uses_uia_text_and_anchor(monkeypatch):
    monkeypatch.setattr(selection_module.win32, "foreground_process_id", lambda: 999)
    service, overlay, reader, _captured = make_service()
    reader.value = UiaSelection("hello", [Rect(100, 10, 220, 40)])
    service._deliver(_gesture(), service._generation)
    assert overlay.shows
    assert overlay.shows[0][0] == "hello"
    assert overlay.shows[0][1] == Rect(100, 10, 220, 40)


def test_deliver_respects_disabled_setting(monkeypatch):
    monkeypatch.setattr(selection_module.win32, "foreground_process_id", lambda: 999)
    overlay = FakeOverlay()
    overlay.visible = True
    service, overlay, _reader, _captured = make_service(enabled=False, overlay=overlay)
    service._deliver(_gesture(), service._generation)
    assert overlay.shows == []
    assert overlay.hides == 1


def test_deliver_ignores_own_process(monkeypatch):
    monkeypatch.setattr(selection_module.win32, "foreground_process_id", lambda: 1)
    service, overlay, reader, _captured = make_service()
    reader.value = UiaSelection("hello", [Rect(100, 100, 220, 130)])
    service._deliver(_gesture(), service._generation)
    assert overlay.shows == []


def test_deliver_ignores_blank_selection(monkeypatch):
    monkeypatch.setattr(selection_module.win32, "foreground_process_id", lambda: 999)
    service, overlay, reader, _captured = make_service()
    reader.value = UiaSelection("   ", [Rect(100, 100, 220, 130)])
    service._deliver(_gesture(), service._generation)
    assert overlay.shows == []
