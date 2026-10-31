"""Selection gesture state machine and UIA-to-overlay bridge."""

from __future__ import annotations

import logging
import os
import queue
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from . import geometry, win32
from .geometry import Rect
from .mouse_hook import GlobalMouseHook, MouseEvent
from .uia import UIAutomationReader

logger = logging.getLogger(__name__)

MAX_SELECTION_CHARS = 4000
DEBOUNCE_SECONDS = 0.14
DOUBLE_CLICK_SECONDS = 0.5
VK_SHIFT = 0x10


@dataclass(frozen=True)
class SelectionGesture:
    down: tuple[float, float]
    up: tuple[float, float]
    bounds: Rect
    double_click: bool
    shift: bool
    at: float


def normalize_selection(text: str) -> str | None:
    value = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    value = re.sub(r"\n{3,}", "\n\n", value)
    if not value or len(value) > MAX_SELECTION_CHARS:
        return None
    if not any(char.isalpha() for char in value):
        return None
    return value


class SelectionService:
    def __init__(
        self,
        overlay: Any,
        settings_provider: Callable[[], dict[str, Any]],
        *,
        reader: UIAutomationReader | None = None,
        hook_factory: Callable[[Callable[[MouseEvent], None]], GlobalMouseHook] | None = None,
        own_pid: int | None = None,
        debounce: float = DEBOUNCE_SECONDS,
    ) -> None:
        self.overlay = overlay
        self.settings_provider = settings_provider
        self.reader = reader or UIAutomationReader()
        self.own_pid = int(own_pid if own_pid is not None else os.getpid())
        self.debounce = max(0.0, float(debounce))
        self._hook = (hook_factory or GlobalMouseHook)(self._enqueue)
        self._queue: queue.Queue[MouseEvent | None] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._started = False
        self._stopping = False
        self._state_lock = threading.RLock()
        self._timer: threading.Timer | None = None
        self._generation = 0
        self._down: tuple[float, float] | None = None
        self._bounds: Rect | None = None
        self._tracking = False
        self._down_inside_overlay = False
        self._last_up: tuple[float, float, float] | None = None
        self._last_text = ""
        self._last_text_at = 0.0
        self._hook_ok = False

    # ------------------------------------------------------------------ public
    @property
    def available(self) -> bool:
        return bool(self._started and self.reader.available and self._hook_ok)

    def start(self) -> bool:
        with self._state_lock:
            if self._started:
                return self.available
            self._stopping = False
            self.reader.load()
            self._worker = threading.Thread(
                target=self._worker_loop, name="selection-worker", daemon=True
            )
            self._worker.start()
            self._hook_ok = bool(self._hook.start())
            self._started = True
            if not self._hook_ok:
                logger.warning("Selection translation started without a mouse hook")
            elif not self.reader.available:
                logger.warning("Selection translation started without UI Automation")
            else:
                logger.info("Selection translation is ready")
            return self.available

    def stop(self) -> None:
        with self._state_lock:
            if self._stopping:
                return
            self._stopping = True
            self._generation += 1
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
        try:
            self._hook.stop()
        except Exception:
            logger.debug("Could not stop mouse hook", exc_info=True)
        self._queue.put(None)
        worker = self._worker
        if worker and worker.is_alive():
            worker.join(timeout=1.5)
        self._worker = None
        self._started = False
        self._hook_ok = False

    def status(self) -> dict[str, Any]:
        details: list[str] = []
        if not self.reader.available:
            details.append(self.reader.detail)
        if not self._hook_ok:
            details.append("全局鼠标钩子不可用")
        if not self.overlay.available:
            details.append("浮层未就绪")
        return {
            "available": self.available,
            "detail": "划译组件可用" if self.available else "；".join(details) or "正在启动",
        }

    def refresh(self) -> None:
        """Hide the card when selection translation is disabled by the user."""

        try:
            settings = self.settings_provider() or {}
        except Exception:
            settings = {}
        if not settings.get("selection_translate") and self.overlay.visible:
            self.overlay.hide()

    # --------------------------------------------------------------- internals
    def _enqueue(self, event: MouseEvent) -> None:
        if not self._stopping:
            self._queue.put(event)

    def _worker_loop(self) -> None:
        try:
            with win32.per_monitor_dpi_context():
                while not self._stopping:
                    try:
                        event = self._queue.get(timeout=0.25)
                    except queue.Empty:
                        continue
                    if event is None:
                        break
                    try:
                        self.process_event(event)
                    except Exception:
                        logger.debug("Selection event failed", exc_info=True)
        except Exception:
            logger.exception("Selection worker stopped unexpectedly")

    def process_event(self, event: MouseEvent) -> None:
        """Process one mouse event.  Public for tests; normally called by worker."""

        with self._state_lock:
            if event.kind == "wheel":
                if self.overlay.visible and not self.overlay.contains_point(event.x, event.y):
                    self.overlay.hide()
                return
            if event.kind == "down":
                self._down = (event.x, event.y)
                self._bounds = Rect(event.x, event.y, event.x, event.y)
                self._down_inside_overlay = bool(
                    self.overlay.visible and self.overlay.contains_point(event.x, event.y)
                )
                self._tracking = not self._down_inside_overlay
                if self.overlay.visible and not self._down_inside_overlay:
                    self.overlay.hide()
                return
            if event.kind == "move":
                if self._tracking and self._down is not None:
                    self._bounds = self._extend_bounds(
                        self._bounds, event.x, event.y
                    )
                return
            if event.kind != "up":
                return
            if self._down_inside_overlay or not self._tracking or self._down is None:
                self._reset_tracking()
                return
            down_x, down_y = self._down
            distance = ((event.x - down_x) ** 2 + (event.y - down_y) ** 2) ** 0.5
            last_up = self._last_up
            double_click = bool(
                last_up
                and event.at - last_up[2] <= DOUBLE_CLICK_SECONDS
                and ((event.x - last_up[0]) ** 2 + (event.y - last_up[1]) ** 2) ** 0.5 <= 6
            )
            self._last_up = (event.x, event.y, event.at)
            bounds = self._extend_bounds(
                self._bounds
                or geometry.rect_from_points(down_x, down_y, event.x, event.y),
                event.x,
                event.y,
            )
            shift = False
            try:
                shift = win32.is_key_down(VK_SHIFT)
            except Exception:
                pass
            gesture = SelectionGesture(
                down=(down_x, down_y),
                up=(event.x, event.y),
                bounds=bounds or geometry.rect_from_points(down_x, down_y, event.x, event.y),
                double_click=double_click,
                shift=shift,
                at=event.at,
            )
            self._reset_tracking()
            if distance >= 4.0 or double_click or shift:
                self._schedule_capture(gesture)

    @staticmethod
    def _extend_bounds(bounds: Rect | None, x: float, y: float) -> Rect:
        if bounds is None:
            return Rect(x, y, x, y)
        return Rect(
            min(bounds.left, x),
            min(bounds.top, y),
            max(bounds.right, x),
            max(bounds.bottom, y),
        )

    def _reset_tracking(self) -> None:
        self._down = None
        self._bounds = None
        self._tracking = False
        self._down_inside_overlay = False

    def _schedule_capture(self, gesture: SelectionGesture) -> None:
        with self._state_lock:
            if self._stopping:
                return
            self._generation += 1
            generation = self._generation
            if self._timer is not None:
                self._timer.cancel()
            timer = threading.Timer(
                self.debounce, self._deliver, args=(gesture, generation)
            )
            timer.daemon = True
            self._timer = timer
            timer.start()

    def _deliver(self, gesture: SelectionGesture, generation: int) -> None:
        with self._state_lock:
            if self._stopping or generation != self._generation:
                return
        try:
            settings = self.settings_provider() or {}
        except Exception:
            logger.warning("Could not read settings for selection", exc_info=True)
            return
        if not settings.get("selection_translate"):
            if self.overlay.visible:
                self.overlay.hide()
            return
        try:
            if win32.foreground_process_id() == self.own_pid:
                return
        except Exception:
            pass

        selection = None
        for attempt in range(3):
            if self._stopping:
                return
            try:
                selection = self.reader.read()
            except Exception:
                logger.debug("UIA selection read failed", exc_info=True)
                selection = None
            if selection and selection.text.strip():
                break
            if attempt < 2:
                time.sleep(0.06)
        if selection is None:
            return
        text = normalize_selection(selection.text)
        if not text:
            return
        fallback = gesture.bounds
        try:
            _work, _screen, scale = win32.get_monitor_geometry(
                int(gesture.up[0]), int(gesture.up[1])
            )
            # Chromium often reports selected text without range rectangles.
            # A horizontal mouse drag then has zero height, so give the anchor
            # a realistic text-line height instead of using the cursor row.
            fallback = geometry.inflate_rect(
                fallback,
                left=2.0 * scale,
                right=2.0 * scale,
                top=12.0 * scale,
                bottom=4.0 * scale,
            )
        except Exception:
            logger.debug("Could not inflate fallback anchor", exc_info=True)
        anchor = geometry.choose_anchor(
            selection.rects, fallback, gesture.up
        )
        if anchor is None:
            anchor = geometry.rect_from_points(
                gesture.up[0], gesture.up[1], gesture.up[0] + 1, gesture.up[1] + 1
            )
        now = time.monotonic()
        if (
            self.overlay.visible
            and text == self._last_text
            and now - self._last_text_at < 1.5
        ):
            return
        if self.overlay.show(text, anchor):
            self._last_text = text
            self._last_text_at = now
            logger.debug(
                "Selection overlay shown: chars=%s target=%s",
                len(text),
                settings.get("target_lang", ""),
            )
