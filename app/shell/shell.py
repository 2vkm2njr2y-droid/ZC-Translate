"""Lifecycle coordinator for the tray application and selection overlay."""

from __future__ import annotations

import logging
import threading
from typing import Any

from ..backend.services.settings import load_settings, update_settings
from . import win32
from .overlay import OverlayController
from .selection import SelectionService
from .single_instance import SingleInstance
from .tray import TrayIcon

logger = logging.getLogger(__name__)


class DesktopShell:
    def __init__(
        self,
        main_window: Any,
        overlay_window: Any,
        app: Any,
        *,
        single_instance: SingleInstance | None = None,
        frame_color: str = "#f4f6fb",
    ) -> None:
        self.main_window = main_window
        self.overlay_window = overlay_window
        self.app = app
        self.db = app.state.db
        self.frame_color = frame_color
        self.overlay = OverlayController(overlay_window)
        self.selection = SelectionService(
            self.overlay, settings_provider=self.settings
        )
        self.single_instance = single_instance
        self.tray = TrayIcon(
            on_show=self.show_main,
            on_toggle_selection=self.toggle_selection,
            on_quit=self.quit,
            is_selection_enabled=lambda: bool(self.settings().get("selection_translate")),
        )
        self._overlay_loaded = threading.Event()
        self._init_thread: threading.Thread | None = None
        self._quitting = False
        self._stopped = False
        self._first_close = True
        self._main_hwnd = 0
        self._main_size: tuple[int, int] | None = None
        self._frame_started = False

        overlay_window.events.loaded += self._on_overlay_loaded
        main_window.events.closing += self._on_main_closing
        main_window.events.shown += self._on_main_shown
        main_window.events.loaded += self._on_main_shown
        restored_event = getattr(main_window.events, "restored", None)
        if restored_event is not None:
            restored_event += self._on_main_restored
        initialized_event = getattr(main_window.events, "initialized", None)
        if initialized_event is not None:
            initialized_event += self._on_main_initialized

    # ------------------------------------------------------------------ public
    def start(self) -> None:
        try:
            self._main_hwnd = win32.get_hwnd(self.main_window)
        except Exception:
            # pywebview invokes its start callback just before the master
            # window is created.  The handle is resolved lazily on first use.
            logger.debug("Main window handle is not ready yet")
        self._start_frame()
        tray_ok = self.tray.start()
        if not tray_ok:
            logger.warning("Tray unavailable; closing the window will exit the app")
        self._update_tray_tooltip()
        if self.single_instance is not None:
            self.single_instance.start_watcher(self.show_main)
        self._init_thread = threading.Thread(
            target=self._start_selection, name="selection-init", daemon=True
        )
        self._init_thread.start()

    def _start_frame(self) -> None:
        if self._frame_started:
            return
        hwnd = self._main_hwnd or self._resolve_main_hwnd()
        if not hwnd:
            logger.debug("Main window handle unavailable; frame start deferred")
            return
        try:
            # DWM clips the opaque WebView2 window itself.  A Win32 region
            # cannot hide the WebView2 surface outside the cut-outs and would
            # leave black square corners; keep the stable native silhouette.
            win32.apply_dwm_rounding(hwnd)
            self._frame_started = True
            rect = win32.get_window_rect(hwnd)
            if rect.width > 0 and rect.height > 0:
                self._main_size = (int(rect.width), int(rect.height))
            logger.info("DWM rounded corners applied")
        except Exception:
            logger.exception("Could not apply DWM rounded corners")

    def set_frame_color(self, color: Any) -> bool:
        if not isinstance(color, str):
            return False
        value = color.strip()
        if len(value) != 7 or not value.startswith("#"):
            return False
        try:
            int(value[1:], 16)
        except ValueError:
            return False
        self.frame_color = value
        return True

    def restore_main_size(self) -> None:
        """Undo WinForms' DIP-sized restore bounds after tray/show cycles."""
        if not self._main_size:
            return
        hwnd = self._main_hwnd or self._resolve_main_hwnd()
        if not hwnd:
            return
        try:
            win32.resize_window(hwnd, *self._main_size)
        except Exception:
            logger.debug("Could not restore main window size", exc_info=True)

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        try:
            self.selection.stop()
        except Exception:
            logger.debug("Could not stop selection service", exc_info=True)
        try:
            self.tray.stop()
        except Exception:
            logger.debug("Could not stop tray", exc_info=True)
        try:
            if self.single_instance is not None:
                self.single_instance.stop()
        except Exception:
            logger.debug("Could not stop single-instance watcher", exc_info=True)
        self.overlay.hide()

    def settings(self) -> dict[str, Any]:
        return load_settings(self.db)

    def close_main(self) -> dict[str, Any]:
        if self._quitting:
            return {"hidden": False, "tray": False, "quitting": True}
        if not self.tray.available:
            self.quit()
            return {"hidden": False, "tray": False, "quitting": True}
        self.hide_main()
        return {"hidden": True, "tray": True, "quitting": False}

    def hide_main(self) -> None:
        if self._quitting:
            return
        self.overlay.hide()
        hwnd = self._main_hwnd or self._resolve_main_hwnd()
        if hwnd:
            try:
                win32.hide_window(hwnd)
            except Exception:
                logger.debug("Could not hide main window", exc_info=True)
                try:
                    self.main_window.hide()
                except Exception:
                    logger.debug("pywebview hide fallback failed", exc_info=True)
        else:
            try:
                self.main_window.hide()
            except Exception:
                logger.debug("Could not hide main window", exc_info=True)
        if self._first_close:
            self._first_close = False
            settings = self.settings()
            if settings.get("selection_translate"):
                self.tray.show_balloon(
                    "ZC 离线翻译", "已最小化到托盘。选中文字即可划译。"
                )
            else:
                self.tray.show_balloon(
                    "ZC 离线翻译", "已最小化到托盘。可在设置或托盘菜单中开启划译。"
                )

    def show_main(self) -> None:
        if self._quitting:
            return
        self.overlay.hide()
        hwnd = self._main_hwnd or self._resolve_main_hwnd()
        if hwnd:
            try:
                win32.restore_window(hwnd)
                self.restore_main_size()
                win32.apply_dwm_rounding(hwnd)
                return
            except Exception:
                logger.debug("Could not restore main window", exc_info=True)
        try:
            self.main_window.show()
            self.main_window.restore()
        except Exception:
            logger.warning("Could not show main window", exc_info=True)

    def toggle_selection(self) -> None:
        try:
            current = bool(self.settings().get("selection_translate"))
            update_settings(self.db, {"selection_translate": not current})
            if current:
                self.overlay.hide()
            self._update_tray_tooltip()
            self._notify_settings_changed()
            logger.info("Selection translation toggled from tray: %s", not current)
        except Exception:
            logger.exception("Could not toggle selection translation")

    def quit(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        logger.info("Quitting desktop shell")
        try:
            self.selection.stop()
        except Exception:
            logger.debug("Could not stop selection", exc_info=True)
        try:
            self.tray.stop()
        except Exception:
            logger.debug("Could not stop tray", exc_info=True)
        try:
            if self.single_instance is not None:
                self.single_instance.stop()
        except Exception:
            pass
        try:
            self.overlay.hide()
            self.overlay.destroy()
        except Exception:
            logger.debug("Could not destroy overlay", exc_info=True)
        try:
            self.main_window.destroy()
        except Exception:
            logger.debug("Could not destroy main window", exc_info=True)

    def selection_status(self) -> dict[str, Any]:
        try:
            return self.selection.status()
        except Exception:
            return {"available": False, "detail": "划译组件状态未知"}

    def overlay_resize(self, width: float, height: float) -> bool:
        return self.overlay.resize(width, height)

    def overlay_hide(self) -> bool:
        self.overlay.hide()
        return True

    def copy_text(self, text: str) -> bool:
        if not isinstance(text, str):
            return False
        return win32.set_clipboard_text(text[:1_000_000])

    # --------------------------------------------------------------- internals
    def _resolve_main_hwnd(self) -> int:
        try:
            self._main_hwnd = win32.get_hwnd(self.main_window)
        except Exception:
            return 0
        return self._main_hwnd

    def _on_overlay_loaded(self) -> None:
        self._overlay_loaded.set()

    def _start_selection(self) -> None:
        if not self._overlay_loaded.wait(12.0):
            logger.warning("Overlay page did not finish loading; selection disabled")
            return
        if self._quitting:
            return
        try:
            self._main_hwnd = self._main_hwnd or self._resolve_main_hwnd()
        except Exception:
            logger.debug("Could not resolve main window handle", exc_info=True)
        try:
            if not self.overlay.attach():
                logger.warning("Overlay native window unavailable; selection disabled")
                return
            self.selection.start()
        except Exception:
            logger.exception("Could not start selection translation")
        self._update_tray_tooltip()

    def _update_tray_tooltip(self) -> None:
        try:
            enabled = bool(self.settings().get("selection_translate"))
            suffix = "划译已开" if enabled else "划译已关"
            self.tray.set_tooltip(f"ZC 离线翻译 · {suffix}")
        except Exception:
            logger.debug("Could not update tray tooltip", exc_info=True)

    def _notify_settings_changed(self) -> None:
        try:
            self.main_window.evaluate_js(
                "window.dispatchEvent(new Event('zc-settings-changed'));"
            )
        except Exception:
            logger.debug("Could not notify main page about settings", exc_info=True)

    def _on_main_shown(self) -> None:
        self._start_frame()

    def _on_main_initialized(self) -> None:
        try:
            hwnd = self._main_hwnd or self._resolve_main_hwnd()
            if hwnd:
                win32.apply_dwm_rounding(hwnd)
        except Exception:
            logger.debug("Could not prepare the content window", exc_info=True)

    def _on_main_restored(self) -> None:
        self.restore_main_size()

    def _on_main_closing(self) -> bool:
        if self._quitting:
            return True
        if not self.tray.available:
            return True
        thread = threading.Timer(0.05, self.hide_main)
        thread.daemon = True
        thread.start()
        return False
