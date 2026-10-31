"""Small Win32 helpers shared by the tray, overlay and selection code.

Only the handful of APIs needed by the desktop shell are wrapped here.  The
module imports ctypes lazily so that unit tests can import it on non-Windows
machines without loading user32/gdi32.
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from ctypes import wintypes
from pathlib import Path
from typing import Any

from .geometry import Rect

logger = logging.getLogger(__name__)

LRESULT = ctypes.c_ssize_t
WPARAM = ctypes.c_size_t
LPARAM = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_void_p, ctypes.c_uint, WPARAM, LPARAM)


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]

SW_HIDE = 0
SW_SHOWNOACTIVATE = 4
SW_RESTORE = 9
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
SWP_NOOWNERZORDER = 0x0200
HWND_TOPMOST = ctypes.c_void_p(-1)
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008
WS_EX_NOACTIVATE = 0x08000000
MONITOR_DEFAULTTONEAREST = 2
MDT_EFFECTIVE_DPI = 0
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x0010
LR_DEFAULTSIZE = 0x0040
DIALOG_CONTEXT_PER_MONITOR_V2 = 0xFFFFFFFFFFFFFFFC
DWMWA_NCRENDERING_POLICY = 2
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_BORDER_COLOR = 34
DWMNCRP_DISABLED = 1
DWMNCRP_ENABLED = 2
DWMWCP_DONOTROUND = 1
DWMWCP_ROUND = 2
DWMWA_COLOR_NONE = 0xFFFFFFFE
# Keep in sync with ``--radius-window`` in app/frontend/assets/styles.css.
MAIN_WINDOW_RADIUS_CSS = 32.0
OVERLAY_RADIUS_CSS = 18.0


def _lib(name: str) -> Any:
    if os.name != "nt":
        raise OSError("Win32 is only available on Windows")
    return ctypes.WinDLL(name, use_last_error=True)


def get_hwnd(window: Any) -> int:
    """Return the native HWND for a pywebview window."""

    native = getattr(window, "native", None)
    if native is None:
        raise RuntimeError("窗口尚未创建")
    handle = native.Handle
    if hasattr(handle, "ToInt64"):
        return int(handle.ToInt64())
    return int(handle)


def foreground_hwnd() -> int:
    user32 = _lib("user32")
    user32.GetForegroundWindow.argtypes = ()
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    return int(user32.GetForegroundWindow() or 0)


def process_id_for_window(hwnd: int) -> int:
    user32 = _lib("user32")
    pid = ctypes.c_ulong()
    user32.GetWindowThreadProcessId.argtypes = (ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong))
    user32.GetWindowThreadProcessId.restype = ctypes.c_ulong
    user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(pid))
    return int(pid.value)


def foreground_process_id() -> int:
    hwnd = foreground_hwnd()
    return process_id_for_window(hwnd) if hwnd else 0


def window_title(hwnd: int) -> str:
    user32 = _lib("user32")
    user32.GetWindowTextLengthW.argtypes = (ctypes.c_void_p,)
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int)
    user32.GetWindowTextW.restype = ctypes.c_int
    length = int(user32.GetWindowTextLengthW(ctypes.c_void_p(hwnd)))
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(ctypes.c_void_p(hwnd), buffer, length + 1)
    return buffer.value


def get_cursor_position() -> tuple[int, int]:
    user32 = _lib("user32")
    point = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(point))
    return int(point.x), int(point.y)


def is_key_down(vk: int) -> bool:
    user32 = _lib("user32")
    user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
    user32.GetAsyncKeyState.restype = ctypes.c_short
    return bool(int(user32.GetAsyncKeyState(vk)) & 0x8000)


def is_window_visible(hwnd: int) -> bool:
    user32 = _lib("user32")
    user32.IsWindowVisible.argtypes = (ctypes.c_void_p,)
    user32.IsWindowVisible.restype = ctypes.c_bool
    return bool(user32.IsWindowVisible(ctypes.c_void_p(hwnd)))


def hide_window(hwnd: int) -> None:
    user32 = _lib("user32")
    user32.ShowWindow.argtypes = (ctypes.c_void_p, ctypes.c_int)
    user32.ShowWindow.restype = ctypes.c_bool
    user32.ShowWindow(ctypes.c_void_p(hwnd), SW_HIDE)


def restore_window(hwnd: int) -> None:
    user32 = _lib("user32")
    user32.ShowWindow.argtypes = (ctypes.c_void_p, ctypes.c_int)
    user32.ShowWindow.restype = ctypes.c_bool
    user32.SetForegroundWindow.argtypes = (ctypes.c_void_p,)
    user32.SetForegroundWindow.restype = ctypes.c_bool
    user32.BringWindowToTop.argtypes = (ctypes.c_void_p,)
    user32.BringWindowToTop.restype = ctypes.c_bool
    user32.ShowWindow(ctypes.c_void_p(hwnd), SW_RESTORE)
    try:
        user32.BringWindowToTop(ctypes.c_void_p(hwnd))
        user32.SetForegroundWindow(ctypes.c_void_p(hwnd))
    except Exception:
        logger.debug("SetForegroundWindow failed", exc_info=True)


def set_window_rect(hwnd: int, rect: Rect, *, show: bool = False) -> None:
    user32 = _lib("user32")
    user32.SetWindowPos.argtypes = (
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint,
    )
    user32.SetWindowPos.restype = ctypes.c_bool
    flags = SWP_NOACTIVATE | SWP_NOOWNERZORDER
    if show:
        flags |= SWP_SHOWWINDOW
    user32.SetWindowPos(
        ctypes.c_void_p(hwnd),
        HWND_TOPMOST,
        int(round(rect.left)),
        int(round(rect.top)),
        max(1, int(round(rect.width))),
        max(1, int(round(rect.height))),
        flags,
    )


def get_window_rect(hwnd: int) -> Rect:
    user32 = _lib("user32")
    rect = wintypes.RECT()
    user32.GetWindowRect.argtypes = (ctypes.c_void_p, ctypes.POINTER(wintypes.RECT))
    user32.GetWindowRect.restype = ctypes.c_bool
    if not user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(rect)):
        return Rect(0, 0, 0, 0)
    return Rect(rect.left, rect.top, rect.right, rect.bottom)


def resize_window(hwnd: int, width: int, height: int) -> None:
    """Resize without moving or activating; used after a tray restore."""
    user32 = _lib("user32")
    user32.SetWindowPos.argtypes = (
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint,
    )
    user32.SetWindowPos.restype = ctypes.c_bool
    user32.SetWindowPos(
        ctypes.c_void_p(hwnd),
        None,
        0,
        0,
        max(1, int(width)),
        max(1, int(height)),
        SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE,
    )


def show_window_no_activate(hwnd: int, rect: Rect) -> None:
    set_window_rect(hwnd, rect, show=True)


def apply_no_activate_tool_style(hwnd: int) -> None:
    user32 = _lib("user32")
    user32.GetWindowLongW.argtypes = (ctypes.c_void_p, ctypes.c_int)
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.SetWindowLongW.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_long)
    user32.SetWindowLongW.restype = ctypes.c_long
    style = int(user32.GetWindowLongW(ctypes.c_void_p(hwnd), GWL_EXSTYLE)) & 0xFFFFFFFF
    style |= WS_EX_TOOLWINDOW | WS_EX_TOPMOST | WS_EX_NOACTIVATE
    user32.SetWindowLongW(ctypes.c_void_p(hwnd), GWL_EXSTYLE, style)


def _dwm_set_attribute(hwnd: int, attribute: int, value: int) -> None:
    """Set one DWMWINDOWATTRIBUTE value and ignore unsupported OS builds."""

    try:
        dwmapi = _lib("dwmapi")
        dwmapi.DwmSetWindowAttribute.argtypes = (
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_void_p,
            ctypes.c_uint,
        )
        dwmapi.DwmSetWindowAttribute.restype = ctypes.c_long
        data = ctypes.c_uint(value & 0xFFFFFFFF)
        dwmapi.DwmSetWindowAttribute(
            ctypes.c_void_p(hwnd),
            ctypes.c_uint(attribute),
            ctypes.byref(data),
            ctypes.sizeof(data),
        )
    except Exception:
        logger.debug("Could not set DWM attribute %s", attribute, exc_info=True)


class MARGINS(ctypes.Structure):
    _fields_ = [
        ("cxLeftWidth", ctypes.c_int),
        ("cxRightWidth", ctypes.c_int),
        ("cyTopHeight", ctypes.c_int),
        ("cyBottomHeight", ctypes.c_int),
    ]


def _extend_frame_into_client_area(hwnd: int) -> None:
    try:
        dwmapi = _lib("dwmapi")
        dwmapi.DwmExtendFrameIntoClientArea.argtypes = (
            ctypes.c_void_p,
            ctypes.POINTER(MARGINS),
        )
        dwmapi.DwmExtendFrameIntoClientArea.restype = ctypes.c_long
        margins = MARGINS(1, 1, 1, 1)
        dwmapi.DwmExtendFrameIntoClientArea(
            ctypes.c_void_p(hwnd), ctypes.byref(margins)
        )
    except Exception:
        logger.debug("Could not extend the DWM frame", exc_info=True)


def apply_dwm_rounding(hwnd: int) -> None:
    """Fallback: let DWM draw the native rounded window silhouette (~8px)."""

    _dwm_set_attribute(hwnd, DWMWA_NCRENDERING_POLICY, DWMNCRP_ENABLED)
    _extend_frame_into_client_area(hwnd)
    _dwm_set_attribute(hwnd, DWMWA_BORDER_COLOR, DWMWA_COLOR_NONE)
    _dwm_set_attribute(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND)


def apply_native_border_policy(hwnd: int) -> None:
    """Remove the DWM frame around a Win32-region-shaped window.

    Windows 11 draws a 1px system border on top-level windows.  Once a window is
    clipped with ``SetWindowRgn`` that border can remain visible as a light
    fringe around the rounded card, so suppress it explicitly.  Opting out of
    DWM corner rounding also prevents an 8px system arc from competing with the
    32px application region.
    """

    _dwm_set_attribute(hwnd, DWMWA_NCRENDERING_POLICY, DWMNCRP_DISABLED)
    _dwm_set_attribute(hwnd, DWMWA_BORDER_COLOR, DWMWA_COLOR_NONE)
    _dwm_set_attribute(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_DONOTROUND)


def apply_round_region(hwnd: int, width: int, height: int, radius: float) -> None:
    if width <= 1 or height <= 1:
        return
    try:
        user32 = _lib("user32")
        gdi32 = _lib("gdi32")
        gdi32.CreateRoundRectRgn.argtypes = (
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.c_int, ctypes.c_int,
        )
        gdi32.CreateRoundRectRgn.restype = ctypes.c_void_p
        gdi32.DeleteObject.argtypes = (ctypes.c_void_p,)
        gdi32.DeleteObject.restype = ctypes.c_bool
        user32.SetWindowRgn.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool)
        user32.SetWindowRgn.restype = ctypes.c_int
        corner = max(4, int(round(float(radius))))
        region = gdi32.CreateRoundRectRgn(0, 0, width + 1, height + 1, corner * 2, corner * 2)
        if region:
            if not user32.SetWindowRgn(ctypes.c_void_p(hwnd), ctypes.c_void_p(region), True):
                # A failed SetWindowRgn leaves ownership with the caller.
                gdi32.DeleteObject(ctypes.c_void_p(region))
    except Exception:
        logger.debug("Could not apply rounded window region", exc_info=True)


@contextmanager
def per_monitor_dpi_context() -> Iterator[None]:
    """Use physical pixels on the current thread when Win10+ allows it."""

    if os.name != "nt":
        yield
        return
    user32 = _lib("user32")
    set_context = getattr(user32, "SetThreadDpiAwarenessContext", None)
    if set_context is None:
        yield
        return
    set_context.argtypes = (ctypes.c_void_p,)
    set_context.restype = ctypes.c_void_p
    previous = set_context(ctypes.c_void_p(DIALOG_CONTEXT_PER_MONITOR_V2))
    try:
        yield
    finally:
        if previous:
            try:
                set_context(ctypes.c_void_p(previous))
            except Exception:
                pass


def get_window_dpi(hwnd: int) -> int:
    try:
        user32 = _lib("user32")
        user32.GetDpiForWindow.argtypes = (ctypes.c_void_p,)
        user32.GetDpiForWindow.restype = ctypes.c_uint
        return int(user32.GetDpiForWindow(ctypes.c_void_p(hwnd))) or 96
    except Exception:
        return 96


def get_monitor_geometry(x: int, y: int) -> tuple[Rect, Rect, float]:
    """Return (work area, monitor rect, scale) for a physical screen point."""

    fallback = Rect(0, 0, 1920, 1080)
    try:
        user32 = _lib("user32")
        point = wintypes.POINT(x, y)
        user32.MonitorFromPoint.argtypes = (wintypes.POINT, ctypes.c_ulong)
        user32.MonitorFromPoint.restype = ctypes.c_void_p
        monitor = user32.MonitorFromPoint(point, MONITOR_DEFAULTTONEAREST)
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(info)
        user32.GetMonitorInfoW.argtypes = (
            ctypes.c_void_p, ctypes.POINTER(MONITORINFO),
        )
        user32.GetMonitorInfoW.restype = ctypes.c_bool
        if not monitor or not user32.GetMonitorInfoW(ctypes.c_void_p(monitor), ctypes.byref(info)):
            return fallback, fallback, 1.0
        work = Rect(info.rcWork.left, info.rcWork.top, info.rcWork.right, info.rcWork.bottom)
        screen = Rect(
            info.rcMonitor.left, info.rcMonitor.top,
            info.rcMonitor.right, info.rcMonitor.bottom,
        )
        dpi_x = ctypes.c_uint(96)
        dpi_y = ctypes.c_uint(96)
        try:
            shcore = _lib("shcore")
            shcore.GetDpiForMonitor.argtypes = (
                ctypes.c_void_p, ctypes.c_int,
                ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint),
            )
            shcore.GetDpiForMonitor.restype = ctypes.c_long
            if shcore.GetDpiForMonitor(
                ctypes.c_void_p(monitor), MDT_EFFECTIVE_DPI,
                ctypes.byref(dpi_x), ctypes.byref(dpi_y),
            ) != 0:
                dpi_x.value = 96
        except Exception:
            dpi_x.value = 96
        return work, screen, max(0.5, dpi_x.value / 96.0)
    except Exception:
        logger.debug("Could not read monitor geometry", exc_info=True)
        return fallback, fallback, 1.0


def load_icon_from_file(path: Path) -> int:
    try:
        if not path.is_file():
            return 0
        user32 = _lib("user32")
        user32.LoadImageW.argtypes = (
            ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint,
            ctypes.c_int, ctypes.c_int, ctypes.c_uint,
        )
        user32.LoadImageW.restype = ctypes.c_void_p
        return int(user32.LoadImageW(
            None, str(path), IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE
        ) or 0)
    except Exception:
        logger.debug("Could not load tray icon from %s", path, exc_info=True)
        return 0


def extract_exe_icon() -> int:
    if os.name != "nt":
        return 0
    try:
        shell32 = _lib("shell32")
        large = ctypes.c_void_p()
        small = ctypes.c_void_p()
        shell32.ExtractIconExW.argtypes = (
            ctypes.c_wchar_p, ctypes.c_int,
            ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p),
            ctypes.c_uint,
        )
        shell32.ExtractIconExW.restype = ctypes.c_uint
        count = shell32.ExtractIconExW(
            sys.executable, 0, ctypes.byref(large), ctypes.byref(small), 1
        )
        if count and small.value:
            if large.value:
                _lib("user32").DestroyIcon(ctypes.c_void_p(large.value))
            return int(small.value)
        if count and large.value:
            return int(large.value)
    except Exception:
        logger.debug("Could not extract executable icon", exc_info=True)
    return 0


def destroy_icon(icon: int) -> None:
    try:
        if icon:
            _lib("user32").DestroyIcon(ctypes.c_void_p(icon))
    except Exception:
        pass


def set_clipboard_text(text: str) -> bool:
    """Write Unicode text to the Windows clipboard, retrying briefly."""

    if os.name != "nt":
        return False
    user32 = _lib("user32")
    kernel32 = _lib("kernel32")
    user32.OpenClipboard.argtypes = (ctypes.c_void_p,)
    user32.OpenClipboard.restype = ctypes.c_bool
    user32.EmptyClipboard.restype = ctypes.c_bool
    user32.SetClipboardData.argtypes = (ctypes.c_uint, ctypes.c_void_p)
    user32.SetClipboardData.restype = ctypes.c_void_p
    user32.CloseClipboard.restype = ctypes.c_bool
    kernel32.GlobalAlloc.argtypes = (ctypes.c_uint, ctypes.c_size_t)
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = (ctypes.c_void_p,)
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = (ctypes.c_void_p,)
    kernel32.GlobalUnlock.restype = ctypes.c_bool
    kernel32.GlobalFree.argtypes = (ctypes.c_void_p,)
    kernel32.GlobalFree.restype = ctypes.c_void_p

    import time

    handle = None
    opened = False
    for _ in range(6):
        if user32.OpenClipboard(None):
            opened = True
            break
        time.sleep(0.02)
    if not opened:
        return False
    try:
        if not user32.EmptyClipboard():
            return False
        encoded = (text + "\x00").encode("utf-16-le")
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))
        if not handle:
            return False
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            return False
        try:
            ctypes.memmove(pointer, encoded, len(encoded))
        finally:
            kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            return False
        handle = None  # ownership transferred to the clipboard
        return True
    finally:
        user32.CloseClipboard()
        if handle:
            kernel32.GlobalFree(handle)
