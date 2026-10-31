from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .config import resolve_log_dir


def setup_logging(dev: bool = False) -> None:
    root = logging.getLogger()
    if any(isinstance(handler, RotatingFileHandler) for handler in root.handlers):
        return
    root.setLevel(logging.INFO if dev else logging.WARNING)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    log_dir = resolve_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_dir / "app.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    root.addHandler(file_handler)
    if dev:
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        console.setLevel(logging.INFO)
        root.addHandler(console)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
