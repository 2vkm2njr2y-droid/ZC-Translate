"""Settings helpers (defaults + SQLite overlay)."""

from __future__ import annotations

from typing import Any

from ..config import DEFAULT_SETTINGS
from ..storage.db import Database


def load_settings(db: Database) -> dict[str, Any]:
    settings = dict(DEFAULT_SETTINGS)
    stored = db.stored_settings()
    for key, value in stored.items():
        if key == "window" and isinstance(value, dict) and isinstance(settings.get("window"), dict):
            settings["window"] = {**settings["window"], **value}
        else:
            settings[key] = value
    return settings


def update_settings(db: Database, updates: dict[str, Any]) -> dict[str, Any]:
    clean = {key: value for key, value in updates.items() if value is not None}
    if clean:
        db.set_settings(clean)
    return load_settings(db)
