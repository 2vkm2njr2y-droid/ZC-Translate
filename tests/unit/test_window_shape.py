from __future__ import annotations

import ctypes
from ctypes import wintypes
from types import SimpleNamespace

from app.shell import win32


class FakeFunction:
    """Callable that also accepts ctypes ``argtypes``/``restype`` attributes."""

    def __init__(self, function):
        self._function = function

    def __call__(self, *args):
        return self._function(*args)


def install_fakes(monkeypatch, *, dpi=144, set_rgn_result=1):
    calls = {"round": [], "rgn": [], "dwm": [], "deleted": [], "extend": []}
    user32 = SimpleNamespace()
    gdi32 = SimpleNamespace()
    dwmapi = SimpleNamespace()

    def get_window_rect(_hwnd, pointer):
        rect = ctypes.cast(pointer, ctypes.POINTER(wintypes.RECT)).contents
        rect.left = 0
        rect.top = 0
        rect.right = 620
        rect.bottom = 460
        return 1

    def get_dpi(_hwnd):
        return dpi

    def create_round_rect_rgn(left, top, right, bottom, ellipse_width, ellipse_height):
        calls["round"].append((left, top, right, bottom, ellipse_width, ellipse_height))
        return 0x1234

    def set_window_rgn(hwnd, region, redraw):
        calls["rgn"].append((hwnd, region, redraw))
        return set_rgn_result

    def delete_object(handle):
        calls["deleted"].append(handle)
        return 1

    def dwm_set(attribute_hwnd, attribute, pointer, size):
        attribute = getattr(attribute, "value", attribute)
        value = ctypes.cast(pointer, ctypes.POINTER(ctypes.c_uint)).contents.value
        calls["dwm"].append((attribute, value, size))
        return 0

    def dwm_extend(_hwnd, pointer):
        margins = ctypes.cast(pointer, ctypes.POINTER(win32.MARGINS)).contents
        calls["extend"].append(
            (
                margins.cxLeftWidth,
                margins.cxRightWidth,
                margins.cyTopHeight,
                margins.cyBottomHeight,
            )
        )
        return 0

    user32.GetWindowRect = FakeFunction(get_window_rect)
    user32.GetDpiForWindow = FakeFunction(get_dpi)
    user32.SetWindowRgn = FakeFunction(set_window_rgn)
    gdi32.CreateRoundRectRgn = FakeFunction(create_round_rect_rgn)
    gdi32.DeleteObject = FakeFunction(delete_object)
    dwmapi.DwmSetWindowAttribute = FakeFunction(dwm_set)
    dwmapi.DwmExtendFrameIntoClientArea = FakeFunction(dwm_extend)

    modules = {"user32": user32, "gdi32": gdi32, "dwmapi": dwmapi}
    monkeypatch.setattr(win32, "_lib", lambda name: modules[name])
    return calls


def test_apply_round_region_at_150_percent(monkeypatch):
    calls = install_fakes(monkeypatch, dpi=144)

    win32.apply_round_region(123, 620, 460, 48)

    assert calls["round"] == [(0, 0, 621, 461, 96, 96)]
    assert calls["rgn"][0][0].value == 123
    assert calls["rgn"][0][2] is True


def test_failed_region_application_releases_handle(monkeypatch):
    calls = install_fakes(monkeypatch, set_rgn_result=0)

    win32.apply_round_region(123, 620, 460, 32)

    assert calls["deleted"]


def test_tiny_window_is_not_shaped(monkeypatch):
    calls = install_fakes(monkeypatch)

    win32.apply_round_region(123, 1, 460, 32)

    assert calls["round"] == []
    assert calls["rgn"] == []


def test_apply_dwm_rounding_uses_native_corners(monkeypatch):
    calls = install_fakes(monkeypatch)

    win32.apply_dwm_rounding(123)

    assert calls["extend"] == [(1, 1, 1, 1)]
    assert [(attr, value) for attr, value, _size in calls["dwm"]] == [
        (2, 2),
        (34, 0xFFFFFFFE),
        (33, 2),
    ]


def test_apply_native_border_policy_disables_frame(monkeypatch):
    calls = install_fakes(monkeypatch)

    win32.apply_native_border_policy(123)

    assert [(attr, value) for attr, value, _size in calls["dwm"]] == [
        (2, 1),
        (34, 0xFFFFFFFE),
        (33, 1),
    ]
