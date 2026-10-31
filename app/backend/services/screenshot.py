"""Windows native screen snipping capture.

The app is an unpackaged pywebview/Win32 program, so the new packaged
``ms-screenclip:`` response protocol is not available.  Instead this module
opens the same built-in snipping overlay as Win+Shift+S and reads the resulting
image from the clipboard.  Everything stays in memory; no screenshot is written
to disk.
"""

from __future__ import annotations

import base64
import io
import logging
import os
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

_MAX_DIMENSION = 4096
_POLL_SECONDS = 0.1
_SETTLE_SECONDS = 0.2
_OVERLAY_GRACE_SECONDS = 0.8
_SNIP_PROCESS_NAMES = {
    "snippingtool.exe",
    "screensketch.exe",
    "screenclippinghost.exe",
}
_capture_lock = threading.Lock()


class CaptureError(RuntimeError):
    """Base class for native capture failures."""


class CaptureUnavailable(CaptureError):
    """The Windows snipping tool or a required component is unavailable."""


class CaptureCancelled(CaptureError):
    """The snipping overlay closed without producing a clipboard image."""


class CaptureTimeout(CaptureError):
    """No screenshot arrived before the timeout."""


class CaptureBusy(CaptureError):
    """Another native capture is already waiting for the user."""


def _now() -> float:
    return time.monotonic()


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def _platform_supported() -> bool:
    return os.name == "nt"


def _pil():
    try:
        from PIL import Image, ImageGrab
    except Exception as exc:  # pragma: no cover - depends on local install
        raise CaptureUnavailable(
            "截图组件未安装。请运行 scripts\\setup_ocr.ps1 安装 Pillow。"
        ) from exc
    return Image, ImageGrab


def _encode_image(image: Any, max_dimension: int = _MAX_DIMENSION) -> dict[str, Any]:
    """Convert a Pillow image into the API payload, downscaling if needed."""
    Image, _ImageGrab = _pil()
    image = image.convert("RGB")
    width, height = image.size
    if width <= 0 or height <= 0:
        raise CaptureUnavailable("截图内容为空，请重新选择区域。")
    if max(width, height) > max_dimension:
        scale = max_dimension / float(max(width, height))
        size = (max(1, round(width * scale)), max(1, round(height * scale)))
        resize = getattr(Image, "Resampling", Image).LANCZOS
        image = image.resize(size, resize)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", compress_level=6)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return {
        "ok": True,
        "data_url": "data:image/png;base64," + encoded,
        "width": image.width,
        "height": image.height,
    }


def _clipboard_sequence() -> int:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    user32.GetClipboardSequenceNumber.argtypes = ()
    user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
    return int(user32.GetClipboardSequenceNumber())


def _read_clipboard_image() -> Any | None:
    _Image, ImageGrab = _pil()
    try:
        value = ImageGrab.grabclipboard()
    except Exception:
        # The clipboard is frequently locked for a few milliseconds while the
        # snipping tool writes to it; the caller simply polls again.
        return None
    return value if hasattr(value, "size") and hasattr(value, "convert") else None


def _read_new_clipboard_image(before_sequence: int) -> Any | None:
    if _clipboard_sequence() == before_sequence:
        return None
    return _read_clipboard_image()


def _send_inputs(keys: list[tuple[int, int]]) -> None:
    """Send a batch of virtual-key down/up events via SendInput."""
    import ctypes
    from ctypes import wintypes

    class _KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_size_t),
        ]

    class _MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_size_t),
        ]

    class _HARDWAREINPUT(ctypes.Structure):
        _fields_ = [
            ("uMsg", wintypes.DWORD),
            ("wParamL", wintypes.WORD),
            ("wParamH", wintypes.WORD),
        ]

    class _INPUTUNION(ctypes.Union):
        _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT), ("hi", _HARDWAREINPUT)]

    class _INPUT(ctypes.Structure):
        _anonymous_ = ("u",)
        _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]

    if not keys:
        return
    items = []
    for vk, flags in keys:
        item = _INPUT()
        item.type = 1  # INPUT_KEYBOARD
        item.ki = _KEYBDINPUT(vk, 0, flags, 0, 0)
        items.append(item)
    array_type = _INPUT * len(items)
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.SendInput.argtypes = (
        wintypes.UINT,
        ctypes.POINTER(_INPUT),
        ctypes.c_int,
    )
    user32.SendInput.restype = wintypes.UINT
    sent = user32.SendInput(len(items), array_type(*items), ctypes.sizeof(_INPUT))
    if sent != len(items):
        error = ctypes.get_last_error()
        raise CaptureUnavailable(
            f"无法启动 Windows 截图工具（系统错误 {error}）。"
            "请确认屏幕已解锁、前台不是管理员权限程序，然后重试。"
        )


def _launch_snip() -> None:
    """Open the built-in snipping overlay with Win+Shift+S."""
    # VK_LWIN=0x5B, VK_SHIFT=0x10, VK_S=0x53; KEYEVENTF_KEYUP=0x0002.
    down = 0
    up = 0x0002
    _send_inputs([(0x5B, down), (0x10, down), (0x53, down)])
    _sleep(0.06)
    _send_inputs([(0x53, up), (0x10, up), (0x5B, up)])


def _process_image_name(pid: int) -> str:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = (
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    )
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL

    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(1024)
        buffer = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return os.path.basename(buffer.value).lower()
        return ""
    finally:
        kernel32.CloseHandle(handle)


def _snip_windows() -> set[int]:
    """Full-screen overlay windows belonging to the Windows snipping tool.

    The snip overlay covers the whole virtual desktop.  The editor window that
    can open afterwards is smaller, so filtering by coverage lets us notice the
    overlay closing even when the editor stays open (for example when
    "automatically copy to clipboard" is disabled).
    """
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = (enum_proc, wintypes.LPARAM)
    user32.EnumWindows.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = (wintypes.HWND,)
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.IsIconic.argtypes = (wintypes.HWND,)
    user32.IsIconic.restype = wintypes.BOOL
    user32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    virtual_left = user32.GetSystemMetrics(76)
    virtual_top = user32.GetSystemMetrics(77)
    virtual_width = user32.GetSystemMetrics(78)
    virtual_height = user32.GetSystemMetrics(79)
    found: set[int] = set()

    def callback(hwnd, _lparam):  # noqa: ANN001
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return True
        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return True
        width = rect.right - rect.left
        height = rect.bottom - rect.top
        if width < 200 or height < 120:
            return True
        if virtual_width > 0 and virtual_height > 0:
            covered_width = min(rect.right, virtual_left + virtual_width) - max(
                rect.left, virtual_left
            )
            covered_height = min(rect.bottom, virtual_top + virtual_height) - max(
                rect.top, virtual_top
            )
            if covered_width < virtual_width * 0.95 or covered_height < virtual_height * 0.95:
                return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return True
        if _process_image_name(pid.value) in _SNIP_PROCESS_NAMES:
            found.add(int(hwnd))
        return True

    user32.EnumWindows(enum_proc(callback), 0)
    return found


def capture_native_region(timeout: float = 30.0) -> dict[str, Any]:
    """Ask Windows for a region screenshot and return it as a PNG data URL."""
    if not _platform_supported():
        raise CaptureUnavailable("截图翻译仅支持 Windows。")
    if not _capture_lock.acquire(blocking=False):
        raise CaptureBusy("正在等待上一次截图完成，请稍后再试。")
    try:
        _pil()
        before_sequence = _clipboard_sequence()
        before_windows = _snip_windows()

        # The desktop shell hides its window before calling this endpoint.  The
        # short settle delay gives the compositor time to remove it from screen.
        _sleep(_SETTLE_SECONDS)
        _launch_snip()

        deadline = _now() + max(3.0, float(timeout))
        overlay_seen = False
        overlay_gone_at: float | None = None
        while _now() < deadline:
            image = _read_new_clipboard_image(before_sequence)
            if image is not None:
                payload = _encode_image(image)
                logger.info("Native screenshot captured: %sx%s", payload["width"], payload["height"])
                return payload

            current = _snip_windows()
            new_windows = current - before_windows
            if new_windows:
                overlay_seen = True
                overlay_gone_at = None
            elif overlay_seen:
                if overlay_gone_at is None:
                    overlay_gone_at = _now()
                elif _now() - overlay_gone_at >= _OVERLAY_GRACE_SECONDS:
                    # Final race check: the clipboard can update just after the
                    # overlay closes.
                    image = _read_new_clipboard_image(before_sequence)
                    if image is not None:
                        payload = _encode_image(image)
                        logger.info(
                            "Native screenshot captured: %sx%s",
                            payload["width"],
                            payload["height"],
                        )
                        return payload
                    raise CaptureCancelled(
                        "未检测到截图。可能已取消，或截图工具没有把图片复制到剪贴板；"
                        "请确认已开启“自动复制到剪贴板”。"
                    )
            _sleep(_POLL_SECONDS)

        raise CaptureTimeout(
            "等待截图超时。请重试，或确认 Windows 截图工具已开启“自动复制到剪贴板”。"
        )
    finally:
        _capture_lock.release()
