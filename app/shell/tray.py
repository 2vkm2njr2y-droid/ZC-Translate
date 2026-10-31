"""Windows notification-area icon implemented with Shell_NotifyIconW."""

from __future__ import annotations

import ctypes
import logging
import os
import threading
from collections.abc import Callable
from ctypes import wintypes
from pathlib import Path

from ..backend.config import repo_root
from . import win32

logger = logging.getLogger(__name__)

NIM_ADD = 0
NIM_MODIFY = 1
NIM_DELETE = 2
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
NIF_INFO = 0x00000010
NIF_SHOWTIP = 0x00000080
NIIF_INFO = 0x00000001

WM_APP = 0x8000
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
WM_CONTEXTMENU = 0x007B
WM_COMMAND = 0x0111
WM_CLOSE = 0x0010
WM_DESTROY = 0x0002
WM_NULL = 0x0000

MF_STRING = 0x00000000
MF_SEPARATOR = 0x00000800
MF_CHECKED = 0x00000008
TPM_RETURNCMD = 0x0100
TPM_RIGHTBUTTON = 0x0002

MENU_SHOW = 1001
MENU_TOGGLE = 1002
MENU_QUIT = 1003


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HANDLE),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", GUID),
        ("hBalloonIcon", wintypes.HANDLE),
    ]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", win32.WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HANDLE),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HANDLE),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


def _icon_path() -> Path | None:
    root = Path(repo_root())
    for candidate in (
        root / "assets" / "zc-translate.ico",
        root / "zc-translate.ico",
    ):
        if candidate.is_file():
            return candidate
    return None


class TrayIcon:
    def __init__(
        self,
        *,
        on_show: Callable[[], None],
        on_toggle_selection: Callable[[], None],
        on_quit: Callable[[], None],
        is_selection_enabled: Callable[[], bool] | None = None,
    ) -> None:
        self.on_show = on_show
        self.on_toggle_selection = on_toggle_selection
        self.on_quit = on_quit
        self.is_selection_enabled = is_selection_enabled or (lambda: False)
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._hwnd = 0
        self._icon = 0
        self._icon_owned = False
        self._available = False
        self._stopping = False
        self._class_name = f"ZCTranslateTray_{id(self):x}"
        self._callback_message = WM_APP + 2
        self._taskbar_created = 0
        self._wndproc = None
        self._nid: NOTIFYICONDATAW | None = None

    @property
    def available(self) -> bool:
        return self._available

    def start(self) -> bool:
        if self._thread and self._thread.is_alive():
            return self._available
        if os.name != "nt":
            return False
        self._ready.clear()
        self._stopping = False
        self._thread = threading.Thread(target=self._run, name="tray-icon", daemon=True)
        self._thread.start()
        self._ready.wait(3.0)
        return self._available

    def stop(self) -> None:
        self._stopping = True
        # Remove the icon before tearing down windows so quitting from the
        # tray thread cannot leave a ghost icon during fast process exit.
        if self._nid is not None:
            try:
                self._notify(NIM_DELETE, self._nid)
                self._nid = None
            except Exception:
                logger.debug("Could not remove tray icon", exc_info=True)
        if self._hwnd:
            try:
                user32 = ctypes.WinDLL("user32", use_last_error=True)
                user32.PostMessageW(ctypes.c_void_p(self._hwnd), WM_CLOSE, 0, 0)
            except Exception:
                logger.debug("Could not stop tray window", exc_info=True)
        if (
            self._thread
            and self._thread.is_alive()
            and self._thread is not threading.current_thread()
        ):
            self._thread.join(timeout=2.0)
        if self._thread is not threading.current_thread():
            self._thread = None
        self._hwnd = 0
        self._available = False

    def set_tooltip(self, text: str) -> None:
        nid = self._nid
        if nid is None or not self._available:
            return
        try:
            nid.szTip = text[:127]
            nid.uFlags = NIF_TIP
            self._notify(NIM_MODIFY, nid)
        except Exception:
            logger.debug("Could not update tray tooltip", exc_info=True)

    def show_balloon(self, title: str, text: str) -> None:
        nid = self._nid
        if nid is None or not self._available:
            return
        try:
            nid.szInfoTitle = title[:63]
            nid.szInfo = text[:255]
            nid.dwInfoFlags = NIIF_INFO
            nid.uFlags = NIF_INFO | NIF_TIP
            self._notify(NIM_MODIFY, nid)
            nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        except Exception:
            logger.debug("Could not show tray balloon", exc_info=True)

    # --------------------------------------------------------------- internals
    @staticmethod
    def _notify(message: int, nid: NOTIFYICONDATAW) -> bool:
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        shell32.Shell_NotifyIconW.argtypes = (
            wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW),
        )
        shell32.Shell_NotifyIconW.restype = wintypes.BOOL
        return bool(shell32.Shell_NotifyIconW(message, ctypes.byref(nid)))

    def _load_icon(self) -> None:
        icon_path = _icon_path()
        if icon_path is not None:
            icon = win32.load_icon_from_file(icon_path)
            if icon:
                self._icon = icon
                self._icon_owned = True
                return
        icon = win32.extract_exe_icon()
        if icon:
            self._icon = icon
            self._icon_owned = True
            return
        try:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.LoadIconW.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
            user32.LoadIconW.restype = ctypes.c_void_p
            self._icon = int(user32.LoadIconW(None, ctypes.c_void_p(32512)) or 0)
        except Exception:
            self._icon = 0

    def _run(self) -> None:
        try:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

            kernel32.GetModuleHandleW.argtypes = (ctypes.c_wchar_p,)
            kernel32.GetModuleHandleW.restype = ctypes.c_void_p
            instance = kernel32.GetModuleHandleW(None)

            self._wndproc = win32.WNDPROC(self._window_proc)
            window_class = WNDCLASSW()
            window_class.lpfnWndProc = self._wndproc
            window_class.hInstance = instance
            window_class.lpszClassName = self._class_name
            user32.RegisterClassW.argtypes = (ctypes.POINTER(WNDCLASSW),)
            user32.RegisterClassW.restype = wintypes.ATOM
            atom = user32.RegisterClassW(ctypes.byref(window_class))
            if not atom:
                logger.warning("RegisterClassW for tray failed: %s", ctypes.get_last_error())
                return

            user32.CreateWindowExW.argtypes = (
                wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
            )
            user32.CreateWindowExW.restype = ctypes.c_void_p
            self._hwnd = int(user32.CreateWindowExW(
                0, self._class_name, "ZC 离线翻译", 0, 0, 0, 0, 0, None, None, instance, None
            ) or 0)
            if not self._hwnd:
                logger.warning("CreateWindowExW for tray failed: %s", ctypes.get_last_error())
                return

            user32.RegisterWindowMessageW.argtypes = (wintypes.LPCWSTR,)
            user32.RegisterWindowMessageW.restype = wintypes.UINT
            self._taskbar_created = int(user32.RegisterWindowMessageW("TaskbarCreated"))

            self._load_icon()
            nid = NOTIFYICONDATAW()
            nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
            nid.hWnd = self._hwnd
            nid.uID = 1
            nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
            nid.uCallbackMessage = self._callback_message
            nid.hIcon = self._icon
            nid.szTip = "ZC 离线翻译（托盘运行）"
            if not self._notify(NIM_ADD, nid):
                logger.warning("Shell_NotifyIconW(NIM_ADD) failed")
                return
            self._nid = nid
            self._available = True
            logger.info("Tray icon ready")
            self._ready.set()

            message = wintypes.MSG()
            user32.GetMessageW.argtypes = (
                ctypes.POINTER(wintypes.MSG), ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint,
            )
            user32.GetMessageW.restype = ctypes.c_int
            user32.TranslateMessage.argtypes = (ctypes.POINTER(wintypes.MSG),)
            user32.DispatchMessageW.argtypes = (ctypes.POINTER(wintypes.MSG),)
            user32.DispatchMessageW.restype = ctypes.c_ssize_t
            user32.DestroyWindow.argtypes = (ctypes.c_void_p,)
            user32.DestroyWindow.restype = wintypes.BOOL
            user32.PostQuitMessage.argtypes = (ctypes.c_int,)
            user32.PostQuitMessage.restype = None
            while not self._stopping:
                result = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if result <= 0:
                    break
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
        except Exception:
            logger.exception("Tray icon thread failed")
        finally:
            try:
                if self._nid is not None:
                    self._notify(NIM_DELETE, self._nid)
            except Exception:
                pass
            try:
                if self._hwnd:
                    ctypes.WinDLL("user32", use_last_error=True).DestroyWindow(
                        ctypes.c_void_p(self._hwnd)
                    )
            except Exception:
                pass
            if self._icon_owned and self._icon:
                win32.destroy_icon(self._icon)
            self._icon = 0
            self._icon_owned = False
            self._available = False
            self._nid = None
            self._ready.set()
            logger.info("Tray icon stopped")

    def _window_proc(self, hwnd, message, w_param, l_param):
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        try:
            if message == self._callback_message:
                event = int(l_param)
                if event in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                    self._invoke(self.on_show)
                elif event in (WM_RBUTTONUP, WM_CONTEXTMENU):
                    self._show_menu()
                return 0
            if message == self._taskbar_created and self._taskbar_created:
                nid = self._nid
                if nid is not None:
                    self._notify(NIM_ADD, nid)
                return 0
            if message == WM_COMMAND:
                self._handle_menu(int(w_param) & 0xFFFF)
                return 0
            if message == WM_CLOSE:
                user32.DestroyWindow.argtypes = (ctypes.c_void_p,)
                user32.DestroyWindow.restype = wintypes.BOOL
                user32.DestroyWindow(ctypes.c_void_p(hwnd))
                return 0
            if message == WM_DESTROY:
                user32.PostQuitMessage.argtypes = (ctypes.c_int,)
                user32.PostQuitMessage(0)
                return 0
        except Exception:
            logger.debug("Tray window proc failed", exc_info=True)
        user32.DefWindowProcW.argtypes = (
            ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t,
        )
        user32.DefWindowProcW.restype = ctypes.c_ssize_t
        return int(user32.DefWindowProcW(hwnd, message, w_param, l_param))

    def _show_menu(self) -> None:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        menu = None
        try:
            user32.CreatePopupMenu.argtypes = ()
            user32.CreatePopupMenu.restype = ctypes.c_void_p
            user32.AppendMenuW.argtypes = (
                ctypes.c_void_p, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR,
            )
            user32.AppendMenuW.restype = wintypes.BOOL
            user32.DestroyMenu.argtypes = (ctypes.c_void_p,)
            user32.DestroyMenu.restype = wintypes.BOOL
            user32.GetCursorPos.argtypes = (ctypes.POINTER(wintypes.POINT),)
            user32.GetCursorPos.restype = wintypes.BOOL
            user32.SetForegroundWindow.argtypes = (ctypes.c_void_p,)
            user32.SetForegroundWindow.restype = wintypes.BOOL
            user32.PostMessageW.argtypes = (
                ctypes.c_void_p, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t,
            )
            user32.PostMessageW.restype = wintypes.BOOL

            menu = user32.CreatePopupMenu()
            if not menu:
                return
            flags = MF_STRING | (MF_CHECKED if self._safe_enabled() else 0)
            user32.AppendMenuW(ctypes.c_void_p(menu), MF_STRING, MENU_SHOW, "打开主窗口")
            user32.AppendMenuW(
                ctypes.c_void_p(menu), flags, MENU_TOGGLE, "划译（选中文字自动翻译）"
            )
            user32.AppendMenuW(ctypes.c_void_p(menu), MF_SEPARATOR, 0, None)
            user32.AppendMenuW(ctypes.c_void_p(menu), MF_STRING, MENU_QUIT, "退出")
            point = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(point))
            user32.SetForegroundWindow(ctypes.c_void_p(self._hwnd))
            user32.TrackPopupMenu.argtypes = (
                ctypes.c_void_p, wintypes.UINT, ctypes.c_int, ctypes.c_int,
                ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p,
            )
            user32.TrackPopupMenu.restype = ctypes.c_int
            command = int(user32.TrackPopupMenu(
                ctypes.c_void_p(menu), TPM_RETURNCMD | TPM_RIGHTBUTTON,
                point.x, point.y, 0, ctypes.c_void_p(self._hwnd), None,
            ))
            user32.PostMessageW(ctypes.c_void_p(self._hwnd), WM_NULL, 0, 0)
            if command:
                self._handle_menu(command)
        except Exception:
            logger.debug("Could not show tray menu", exc_info=True)
        finally:
            if menu:
                try:
                    user32.DestroyMenu(ctypes.c_void_p(menu))
                except Exception:
                    pass

    def _safe_enabled(self) -> bool:
        try:
            return bool(self.is_selection_enabled())
        except Exception:
            return False

    def _handle_menu(self, command: int) -> None:
        if command == MENU_SHOW:
            self._invoke(self.on_show)
        elif command == MENU_TOGGLE:
            self._invoke(self.on_toggle_selection)
        elif command == MENU_QUIT:
            self._invoke(self.on_quit)

    @staticmethod
    def _invoke(callback: Callable[[], None]) -> None:
        try:
            callback()
        except Exception:
            logger.exception("Tray callback failed")
