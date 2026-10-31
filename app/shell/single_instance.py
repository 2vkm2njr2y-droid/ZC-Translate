"""Single-instance hand-off for the tray application."""

from __future__ import annotations

import ctypes
import logging
import os
import threading
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

EVENT_NAME = r"Local\ZCTranslate.ShowRequest"
ERROR_ALREADY_EXISTS = 183
WAIT_OBJECT_0 = 0
INFINITE = 0xFFFFFFFF


class SingleInstance:
    def __init__(self, name: str = EVENT_NAME, kernel32: Any | None = None) -> None:
        self.name = name
        self._kernel32 = kernel32
        self._handle = 0
        self._stop = threading.Event()
        self._watcher: threading.Thread | None = None

    @property
    def acquired(self) -> bool:
        return bool(self._handle)

    def _k32(self) -> Any:
        if self._kernel32 is not None:
            return self._kernel32
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel32.CreateEventW.argtypes = (
            ctypes.c_void_p, ctypes.c_bool, ctypes.c_bool, ctypes.c_wchar_p,
        )
        self._kernel32.CreateEventW.restype = ctypes.c_void_p
        self._kernel32.SetEvent.argtypes = (ctypes.c_void_p,)
        self._kernel32.SetEvent.restype = ctypes.c_bool
        self._kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
        self._kernel32.CloseHandle.restype = ctypes.c_bool
        self._kernel32.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_ulong)
        self._kernel32.WaitForSingleObject.restype = ctypes.c_ulong
        return self._kernel32

    def acquire(self) -> bool:
        """Return True for the first instance; signal the existing one otherwise."""

        if os.name != "nt":
            return True
        try:
            kernel32 = self._k32()
            ctypes.set_last_error(0)
            handle = int(kernel32.CreateEventW(None, False, False, self.name) or 0)
            if not handle:
                logger.warning("Could not create single-instance event")
                return True
            if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
                kernel32.SetEvent(ctypes.c_void_p(handle))
                kernel32.CloseHandle(ctypes.c_void_p(handle))
                logger.info("Another ZCTranslate instance is running; asked it to show")
                return False
            self._handle = handle
            return True
        except Exception:
            logger.warning("Single-instance check failed; continuing", exc_info=True)
            return True

    def start_watcher(self, on_show: Callable[[], None]) -> None:
        if not self._handle or self._watcher is not None:
            return
        self._stop.clear()

        def worker() -> None:
            kernel32 = self._k32()
            while not self._stop.is_set():
                try:
                    result = int(kernel32.WaitForSingleObject(
                        ctypes.c_void_p(self._handle), 250
                    ))
                except Exception:
                    logger.debug("Single-instance wait failed", exc_info=True)
                    return
                if self._stop.is_set():
                    return
                if result == WAIT_OBJECT_0:
                    try:
                        on_show()
                    except Exception:
                        logger.exception("Single-instance show callback failed")
            return

        self._watcher = threading.Thread(
            target=worker, name="single-instance", daemon=True
        )
        self._watcher.start()

    def stop(self) -> None:
        self._stop.set()
        watcher = self._watcher
        if watcher and watcher.is_alive():
            watcher.join(timeout=1.0)
        self._watcher = None
        if self._handle:
            try:
                self._k32().CloseHandle(ctypes.c_void_p(self._handle))
            except Exception:
                pass
            self._handle = 0
