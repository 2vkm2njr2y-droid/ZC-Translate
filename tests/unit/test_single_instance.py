from __future__ import annotations

from app.shell import single_instance as module


def _value(handle) -> int:
    return int(getattr(handle, "value", handle) or 0)


class FakeKernel:
    def __init__(self, handle: int) -> None:
        self.handle = handle
        self.set_events = []
        self.closed = []

    def CreateEventW(self, *args):
        return self.handle

    def SetEvent(self, handle):
        self.set_events.append(_value(handle))
        return True

    def CloseHandle(self, handle):
        self.closed.append(_value(handle))
        return True

    def WaitForSingleObject(self, handle, timeout):
        return 0


def test_first_instance_acquires(monkeypatch):
    kernel = FakeKernel(123)
    monkeypatch.setattr(module.ctypes, "get_last_error", lambda: 0)
    instance = module.SingleInstance(kernel32=kernel)
    assert instance.acquire() is True
    assert instance.acquired is True
    instance.stop()
    assert kernel.closed == [123]


def test_second_instance_signals_existing(monkeypatch):
    kernel = FakeKernel(456)
    monkeypatch.setattr(module.ctypes, "get_last_error", lambda: module.ERROR_ALREADY_EXISTS)
    instance = module.SingleInstance(kernel32=kernel)
    assert instance.acquire() is False
    assert kernel.set_events == [456]
    assert kernel.closed == [456]
