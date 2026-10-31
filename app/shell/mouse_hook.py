"""Global low-level mouse hook used by selection translation.

Only the hook/event plumbing lives here.  The callback must be fast because
Windows silently removes a low-level hook whose callback blocks, so all UIA and
overlay work is done by ``SelectionService``.
"""

from __future__ import annotations

import ctypes
import logging
import threading
import time
from collections.abc import Callable
from ctypes import wintypes
from dataclasses import dataclass

logger = logging.getLogger(__name__)

WH_MOUSE_LL = 14
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_MOUSEWHEEL = 0x020A
WM_QUIT = 0x0012
PM_REMOVE = 0x0001


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", wintypes.POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


@dataclass(frozen=True)
class MouseEvent:
    kind: str
    x: int
    y: int
    at: float
    wheel_delta: int = 0


class GlobalMouseHook:
    def __init__(self, callback: Callable[[MouseEvent], None]) -> None:
        self.callback = callback
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._ready = threading.Event()
        self._stopping = False
        self._hook = 0
        self._proc = None

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and self._hook)

    def start(self) -> bool:
        if self.running:
            return True
        self._ready.clear()
        self._stopping = False
        self._thread = threading.Thread(target=self._run, name="mouse-hook", daemon=True)
        self._thread.start()
        if not self._ready.wait(2.0):
            logger.warning("Global mouse hook did not become ready")
            return False
        return self.running

    def stop(self) -> None:
        self._stopping = True
        if self._thread_id:
            try:
                user32 = ctypes.WinDLL("user32", use_last_error=True)
                user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            except Exception:
                logger.debug("Could not post WM_QUIT to mouse hook", exc_info=True)
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=1.5)
        self._hook = 0
        self._thread = None

    def _run(self) -> None:
        from .win32 import per_monitor_dpi_context

        with per_monitor_dpi_context():
            self._run_hook()

    def _run_hook(self) -> None:
        try:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            self._thread_id = int(kernel32.GetCurrentThreadId())
            hook_type = ctypes.WINFUNCTYPE(
                ctypes.c_ssize_t, ctypes.c_int, ctypes.c_size_t, ctypes.c_ssize_t
            )

            def hook_proc(n_code, w_param, l_param):
                try:
                    if n_code >= 0:
                        info = ctypes.cast(
                            l_param, ctypes.POINTER(MSLLHOOKSTRUCT)
                        ).contents
                        at = time.monotonic()
                        x, y = int(info.pt.x), int(info.pt.y)
                        event = None
                        if w_param == WM_LBUTTONDOWN:
                            event = MouseEvent("down", x, y, at)
                        elif w_param == WM_LBUTTONUP:
                            event = MouseEvent("up", x, y, at)
                        elif w_param == WM_MOUSEMOVE:
                            event = MouseEvent("move", x, y, at)
                        elif w_param == WM_MOUSEWHEEL:
                            delta = ctypes.c_short(info.mouseData >> 16).value
                            event = MouseEvent("wheel", x, y, at, delta)
                        if event is not None:
                            self.callback(event)
                except Exception:
                    logger.debug("Mouse hook callback failed", exc_info=True)
                try:
                    return user32.CallNextHookEx(None, n_code, w_param, l_param)
                except Exception:
                    return 0

            self._proc = hook_type(hook_proc)
            user32.SetWindowsHookExW.argtypes = (
                ctypes.c_int, hook_type, ctypes.c_void_p, ctypes.c_ulong,
            )
            user32.SetWindowsHookExW.restype = ctypes.c_void_p
            user32.CallNextHookEx.argtypes = (
                ctypes.c_void_p, ctypes.c_int, ctypes.c_size_t, ctypes.c_ssize_t,
            )
            user32.CallNextHookEx.restype = ctypes.c_ssize_t
            user32.UnhookWindowsHookEx.argtypes = (ctypes.c_void_p,)
            user32.UnhookWindowsHookEx.restype = ctypes.c_bool
            user32.GetMessageW.argtypes = (
                ctypes.POINTER(wintypes.MSG), ctypes.c_void_p,
                ctypes.c_uint, ctypes.c_uint,
            )
            user32.GetMessageW.restype = ctypes.c_int
            user32.TranslateMessage.argtypes = (ctypes.POINTER(wintypes.MSG),)
            user32.TranslateMessage.restype = ctypes.c_bool
            user32.DispatchMessageW.argtypes = (ctypes.POINTER(wintypes.MSG),)
            user32.DispatchMessageW.restype = ctypes.c_ssize_t
            kernel32.GetModuleHandleW.argtypes = (ctypes.c_wchar_p,)
            kernel32.GetModuleHandleW.restype = ctypes.c_void_p

            module = kernel32.GetModuleHandleW(None)
            self._hook = int(
                user32.SetWindowsHookExW(WH_MOUSE_LL, self._proc, module, 0) or 0
            )
            if not self._hook:
                logger.warning(
                    "SetWindowsHookExW(WH_MOUSE_LL) failed: %s", ctypes.get_last_error()
                )
                return
            self._ready.set()

            message = wintypes.MSG()
            while not self._stopping:
                result = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if result <= 0:
                    break
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
        except Exception:
            logger.exception("Global mouse hook stopped unexpectedly")
        finally:
            try:
                if self._hook:
                    user32.UnhookWindowsHookEx(ctypes.c_void_p(self._hook))
            except Exception:
                pass
            self._hook = 0
            self._ready.set()
            logger.info("Global mouse hook stopped")
