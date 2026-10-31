"""Native controller for the hidden translation card WebView."""

from __future__ import annotations

import json
import logging
import math
import threading
from typing import Any

from . import geometry, win32
from .geometry import Rect

logger = logging.getLogger(__name__)


class OverlayController:
    def __init__(self, window: Any) -> None:
        self.window = window
        self._lock = threading.RLock()
        self._hwnd = 0
        self._visible = False
        self._anchor: Rect | None = None
        self._work_area: Rect | None = None
        self._scale = 1.0
        self._width_css = 360.0
        self._height_css = 96.0
        self._max_height_css = 360.0
        self._rect: Rect | None = None

    @property
    def hwnd(self) -> int:
        return self._hwnd

    @property
    def visible(self) -> bool:
        return self._visible

    @property
    def available(self) -> bool:
        return bool(self._hwnd)

    def attach(self) -> bool:
        with self._lock:
            if self._hwnd:
                return True
            try:
                hwnd = win32.get_hwnd(self.window)
            except Exception:
                logger.debug("Overlay native window is not ready", exc_info=True)
                return False
            try:
                win32.apply_no_activate_tool_style(hwnd)
                win32.apply_native_border_policy(hwnd)
            except Exception:
                logger.warning("Could not apply overlay window style", exc_info=True)
                return False
            self._hwnd = hwnd
            logger.info("Selection overlay window attached")
            return True

    def status(self) -> dict[str, Any]:
        return {"available": self.available, "visible": self._visible, "detail": "浮层就绪" if self.available else "浮层未就绪"}

    def show(self, text: str, anchor: Rect) -> bool:
        if not text or anchor is None:
            return False
        with self._lock:
            if not self.attach():
                return False
            try:
                work, _screen, scale = win32.get_monitor_geometry(
                    int(round(anchor.center_x)), int(round(anchor.center_y))
                )
            except Exception:
                logger.debug("Could not resolve monitor for overlay", exc_info=True)
                return False
            self._anchor = anchor
            self._work_area = work
            self._scale = scale
            self._width_css = geometry.overlay_width_css(
                anchor, scale, work.width / scale
            )
            self._max_height_css = geometry.max_height_css(work.height / scale)
            self._height_css = min(96.0, self._max_height_css)
            rect = geometry.place_overlay(
                anchor, work, self._width_css, self._height_css, scale
            )
            self._rect = rect
            try:
                with win32.per_monitor_dpi_context():
                    win32.set_window_rect(self._hwnd, rect, show=False)
                    win32.apply_round_region(
                        self._hwnd,
                        max(1, int(round(rect.width))),
                        max(1, int(round(rect.height))),
                        win32.OVERLAY_RADIUS_CSS * scale,
                    )
            except Exception:
                logger.debug("Could not position overlay", exc_info=True)
            payload = json.dumps(
                {
                    "text": text,
                    "width": round(self._width_css, 2),
                    "maxHeight": round(self._max_height_css, 2),
                },
                ensure_ascii=True,
            )
            try:
                self.window.evaluate_js(
                    f"window.zcOverlay && window.zcOverlay.show({payload});"
                )
            except Exception:
                logger.warning("Could not show overlay content", exc_info=True)
                return False
            try:
                # A WebView2 created hidden does not paint its composition
                # surface when the parent is shown only with ShowWindow().
                # Going through WinForms initializes the surface; the window's
                # WS_EX_NOACTIVATE style keeps Activate() from stealing focus.
                self.window.show()
                with win32.per_monitor_dpi_context():
                    win32.show_window_no_activate(self._hwnd, rect)
                    win32.apply_round_region(
                        self._hwnd,
                        max(1, int(round(rect.width))),
                        max(1, int(round(rect.height))),
                        win32.OVERLAY_RADIUS_CSS * scale,
                    )
            except Exception:
                logger.warning("Could not display overlay", exc_info=True)
                return False
            self._visible = True
            try:
                self.window.evaluate_js(
                    "window.zcOverlay && window.zcOverlay.refreshSize();"
                )
            except Exception:
                logger.debug("Could not request overlay measurement", exc_info=True)
            return True

    def resize(self, width_css: float, height_css: float) -> bool:
        try:
            width = float(width_css)
            height = float(height_css)
        except (TypeError, ValueError):
            return False
        if not math.isfinite(width) or not math.isfinite(height):
            return False
        with self._lock:
            if not self._visible or not self._anchor or not self._work_area or not self._hwnd:
                return False
            width = max(220.0, min(600.0, width))
            height = geometry.css_height(height, self._max_height_css)
            self._width_css = width
            self._height_css = height
            rect = geometry.place_overlay(
                self._anchor, self._work_area, width, height, self._scale
            )
            self._rect = rect
            try:
                with win32.per_monitor_dpi_context():
                    win32.set_window_rect(self._hwnd, rect, show=True)
                    win32.apply_round_region(
                        self._hwnd,
                        max(1, int(round(rect.width))),
                        max(1, int(round(rect.height))),
                        win32.OVERLAY_RADIUS_CSS * self._scale,
                    )
            except Exception:
                logger.debug("Could not resize overlay", exc_info=True)
                return False
            return True

    def hide(self, *, cancel: bool = True) -> None:
        with self._lock:
            if cancel and self._hwnd:
                try:
                    self.window.evaluate_js(
                        "window.zcOverlay && window.zcOverlay.cancel();"
                    )
                except Exception:
                    logger.debug("Could not cancel overlay content", exc_info=True)
            if self._hwnd:
                try:
                    win32.hide_window(self._hwnd)
                except Exception:
                    logger.debug("Could not hide overlay", exc_info=True)
            self._visible = False

    def contains_point(self, x: float, y: float, tolerance: float = 4.0) -> bool:
        with self._lock:
            if not self._visible or not self._rect:
                return False
            return geometry.rect_contains_point(self._rect, x, y, tolerance)

    def destroy(self) -> None:
        self.hide()
        try:
            self.window.destroy()
        except Exception:
            logger.debug("Could not destroy overlay window", exc_info=True)
