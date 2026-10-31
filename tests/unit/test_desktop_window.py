from __future__ import annotations

from types import SimpleNamespace

from app import desktop
from app.backend.services.settings import update_settings
from app.backend.storage.db import Database


def make_app(theme: str = "system"):
    db = Database(":memory:")
    update_settings(db, {"theme": theme})
    return SimpleNamespace(state=SimpleNamespace(db=db))


def test_window_background_follows_saved_theme():
    assert desktop.window_background_color(make_app("dark")) == "#0b1220"
    assert desktop.window_background_color(make_app("light")) == "#f4f6fb"


def test_window_background_follows_system_theme(monkeypatch):
    app = make_app("system")
    monkeypatch.setattr(desktop, "_system_theme_is_dark", lambda: True)
    assert desktop.window_background_color(app) == "#0b1220"
    monkeypatch.setattr(desktop, "_system_theme_is_dark", lambda: False)
    assert desktop.window_background_color(app) == "#f4f6fb"
