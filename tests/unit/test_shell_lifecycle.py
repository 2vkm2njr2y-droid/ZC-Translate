from __future__ import annotations

from types import SimpleNamespace

from app.backend.services.settings import load_settings
from app.backend.storage.db import Database
from app.shell import shell as shell_module
from app.shell.shell import DesktopShell


class FakeEvent:
    def __init__(self) -> None:
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def __add__(self, handler):
        self.handlers.append(handler)
        return self


class FakeWindow:
    def __init__(self) -> None:
        self.events = SimpleNamespace(
            loaded=FakeEvent(), shown=FakeEvent(), closing=FakeEvent()
        )
        self.hidden = 0
        self.shown = 0
        self.destroyed = 0
        self.scripts = []

    def hide(self):
        self.hidden += 1

    def show(self):
        self.shown += 1

    def restore(self):
        pass

    def destroy(self):
        self.destroyed += 1

    def evaluate_js(self, script):
        self.scripts.append(script)


class FakeTray:
    def __init__(self) -> None:
        self.available = True
        self.started = 0
        self.stopped = 0
        self.balloons = []
        self.tooltips = []

    def start(self):
        self.started += 1
        return self.available

    def stop(self):
        self.stopped += 1

    def show_balloon(self, title, text):
        self.balloons.append((title, text))

    def set_tooltip(self, text):
        self.tooltips.append(text)


class FakeOverlay:
    def __init__(self) -> None:
        self.visible = False
        self.hides = 0
        self.destroys = 0

    def hide(self):
        self.hides += 1
        self.visible = False

    def resize(self, width, height):
        return True

    def destroy(self):
        self.destroys += 1


class FakeSelection:
    def __init__(self) -> None:
        self.stops = 0

    def stop(self):
        self.stops += 1

    def status(self):
        return {"available": True, "detail": "ok"}


def make_shell(db=None):
    db = db or Database(":memory:")
    main = FakeWindow()
    overlay = FakeWindow()
    app = SimpleNamespace(state=SimpleNamespace(db=db))
    shell = DesktopShell(main, overlay, app)
    shell._main_hwnd = 123
    shell.tray = FakeTray()
    shell.overlay = FakeOverlay()
    shell.selection = FakeSelection()
    return shell, main, overlay


def test_close_hides_when_tray_available(monkeypatch):
    shell, main, _overlay = make_shell()
    monkeypatch.setattr(shell_module.win32, "hide_window", lambda hwnd: None)
    result = shell.close_main()
    assert result["hidden"] is True
    assert shell.overlay.hides == 1
    assert shell.tray.balloons


def test_close_quits_when_tray_unavailable():
    shell, _main, _overlay = make_shell()
    shell.tray.available = False
    calls = []
    shell.quit = lambda: calls.append(True)
    result = shell.close_main()
    assert result["hidden"] is False
    assert calls == [True]


def test_show_main_restores_and_hides_overlay(monkeypatch):
    shell, _main, _overlay = make_shell()
    restored = []
    shaped = []
    monkeypatch.setattr(shell_module.win32, "restore_window", lambda hwnd: restored.append(hwnd))
    monkeypatch.setattr(shell_module.win32, "apply_dwm_rounding", lambda hwnd: shaped.append(hwnd))
    shell.show_main()
    assert restored == [123]
    assert shaped == [123]
    assert shell.overlay.hides == 1


def test_start_frame_applies_dwm_rounding(monkeypatch):
    shell, _main, _overlay = make_shell()
    shaped = []
    monkeypatch.setattr(
        shell_module.win32,
        "apply_dwm_rounding",
        lambda hwnd: shaped.append(hwnd),
    )
    monkeypatch.setattr(
        shell_module.win32,
        "get_window_rect",
        lambda hwnd: SimpleNamespace(width=620, height=460),
    )
    shell._start_frame()
    assert shaped == [123]
    assert shell._main_size == (620, 460)


class FakeTimer:
    def __init__(self, interval, callback):
        self.interval = interval
        self.callback = callback
        self.daemon = False
        self.started = False

    def start(self):
        self.started = True


def patch_timers(monkeypatch):
    timers = []

    def factory(interval, callback):
        timer = FakeTimer(interval, callback)
        timers.append(timer)
        return timer

    monkeypatch.setattr(shell_module.threading, "Timer", factory)
    return timers


def test_hide_captures_size_before_hiding(monkeypatch):
    shell, _main, _overlay = make_shell()
    monkeypatch.setattr(
        shell_module.win32,
        "get_window_rect",
        lambda hwnd: SimpleNamespace(width=908, height=634),
    )
    monkeypatch.setattr(shell_module.win32, "get_window_dpi", lambda hwnd: 144)
    monkeypatch.setattr(shell_module.win32, "is_window_minimized", lambda hwnd: False)
    monkeypatch.setattr(shell_module.win32, "hide_window", lambda hwnd: None)

    shell.hide_main()

    assert shell._main_size == (908, 634)
    assert shell._main_dpi == 144


def test_show_applies_captured_size_and_schedules_follow_up(monkeypatch):
    shell, _main, _overlay = make_shell()
    shell._main_size = (908, 634)
    shell._main_dpi = 144
    resized = []
    monkeypatch.setattr(shell_module.win32, "restore_window", lambda hwnd: None)
    monkeypatch.setattr(shell_module.win32, "resize_window", lambda hwnd, w, h: resized.append((w, h)))
    monkeypatch.setattr(shell_module.win32, "get_window_dpi", lambda hwnd: 144)
    monkeypatch.setattr(shell_module.win32, "is_window_minimized", lambda hwnd: False)
    monkeypatch.setattr(shell_module.win32, "apply_dwm_rounding", lambda hwnd: None)
    timers = patch_timers(monkeypatch)

    shell.show_main()

    assert resized == [(908, 634)]
    assert [timer.interval for timer in timers] == [0.08, 0.30]
    assert all(timer.started for timer in timers)


def test_show_scales_captured_size_after_dpi_change(monkeypatch):
    shell, _main, _overlay = make_shell()
    shell._main_size = (908, 634)
    shell._main_dpi = 144
    resized = []
    monkeypatch.setattr(shell_module.win32, "restore_window", lambda hwnd: None)
    monkeypatch.setattr(shell_module.win32, "resize_window", lambda hwnd, w, h: resized.append((w, h)))
    monkeypatch.setattr(shell_module.win32, "get_window_dpi", lambda hwnd: 96)
    monkeypatch.setattr(shell_module.win32, "is_window_minimized", lambda hwnd: False)
    monkeypatch.setattr(shell_module.win32, "apply_dwm_rounding", lambda hwnd: None)
    patch_timers(monkeypatch)

    shell.restore_main_size()

    # 908x634 at 144 DPI is the same logical size as 605x423 at 96 DPI.
    assert resized == [(605, 423)]


def test_start_frame_captures_size_when_dwm_rounding_fails(monkeypatch):
    shell, _main, _overlay = make_shell()
    monkeypatch.setattr(
        shell_module.win32,
        "get_window_rect",
        lambda hwnd: SimpleNamespace(width=620, height=460),
    )
    monkeypatch.setattr(shell_module.win32, "get_window_dpi", lambda hwnd: 96)
    monkeypatch.setattr(shell_module.win32, "is_window_minimized", lambda hwnd: False)

    def explode(hwnd):
        raise OSError("dwm unavailable")

    monkeypatch.setattr(shell_module.win32, "apply_dwm_rounding", explode)

    shell._start_frame()

    assert shell._main_size == (620, 460)
    assert shell._frame_started is False


def test_show_without_handle_uses_webview_fallback_and_reschedules(monkeypatch):
    shell, main, _overlay = make_shell()
    shell._main_hwnd = 0
    shell._resolve_main_hwnd = lambda: 0
    shell._main_size = (620, 460)
    shell._main_dpi = 96
    patch_timers(monkeypatch)

    shell.show_main()

    assert main.shown == 1


def test_toggle_selection_persists_and_notifies():
    shell, main, _overlay = make_shell()
    db = shell.db
    assert load_settings(db).get("selection_translate") is False
    shell.toggle_selection()
    assert load_settings(db).get("selection_translate") is True
    assert main.scripts
    shell.toggle_selection()
    assert load_settings(db).get("selection_translate") is False


def test_quit_stops_components_and_destroys_windows():
    shell, main, _overlay = make_shell()
    overlay = shell.overlay
    shell.quit()
    assert shell.selection.stops == 1
    assert shell.tray.stopped == 1
    assert overlay.hides == 1
    assert overlay.destroys == 1
    assert main.destroyed == 1


def test_closing_without_tray_allows_exit():
    shell, _main, _overlay = make_shell()
    shell.tray.available = False
    assert shell._on_main_closing() is True


def test_closing_with_tray_hides_and_cancels(monkeypatch):
    shell, _main, _overlay = make_shell()

    class FakeTimer:
        def __init__(self, interval, callback):
            self.interval = interval
            self.callback = callback
            self.daemon = False
            self.started = False

        def start(self):
            self.started = True

    timers = []
    monkeypatch.setattr(
        shell_module.threading,
        "Timer",
        lambda interval, callback: timers.append(FakeTimer(interval, callback))
        or timers[-1],
    )
    assert shell._on_main_closing() is False
    assert timers and timers[0].started is True


def test_selection_status_delegates():
    shell, _main, _overlay = make_shell()
    assert shell.selection_status()["available"] is True
    assert shell.overlay_resize(400, 120) is True
    assert shell.overlay_hide() is True


def test_set_frame_color_validates():
    shell, _main, _overlay = make_shell()
    assert shell.set_frame_color("#112233") is True
    assert shell.set_frame_color("not-a-color") is False
    assert shell.set_frame_color(None) is False
