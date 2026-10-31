"""Read the current text selection through Windows UI Automation.

The app already depends on pythonnet through pywebview, so the .NET Framework
UIAutomationClient assemblies can be used without adding a Python dependency.
Everything is lazy and failure-tolerant: if UI Automation is unavailable the
selection feature simply reports that it is disabled.
"""

from __future__ import annotations

import logging
import math
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from .geometry import Rect

logger = logging.getLogger(__name__)

_WPF_DIRS = (
    Path(os.environ.get("WINDIR", r"C:\Windows"))
    / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "WPF",
    Path(os.environ.get("WINDIR", r"C:\Windows"))
    / "Microsoft.NET" / "Framework" / "v4.0.30319" / "WPF",
)


@dataclass
class UiaSelection:
    text: str
    rects: list[Rect] = field(default_factory=list)
    process_id: int = 0


class UIAutomationReader:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._loaded = False
        self._error = ""
        self._last_attempt = 0.0
        self._modules: tuple[object, object, object] | None = None

    @property
    def available(self) -> bool:
        return self._loaded

    @property
    def detail(self) -> str:
        if self._loaded:
            return "UI Automation 可用"
        return self._error or "尚未初始化"

    def load(self) -> bool:
        with self._lock:
            if self._loaded:
                return True
            if os.name != "nt":
                self._error = "划译仅支持 Windows"
                return False
            now = time.monotonic()
            if self._error and now - self._last_attempt < 60.0:
                return False
            self._last_attempt = now
            try:
                self._load_modules()
                self._loaded = True
                self._error = ""
                logger.info("UI Automation selection reader initialized")
                return True
            except Exception as exc:  # noqa: BLE001
                first_line = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
                self._error = f"UI Automation 不可用：{first_line[:180]}"
                logger.warning("UI Automation initialization failed: %s", exc)
                return False

    def _load_modules(self) -> None:
        import clr  # type: ignore[import-not-found]

        try:
            clr.AddReference("UIAutomationClient")
            clr.AddReference("UIAutomationTypes")
        except Exception:
            # pythonnet's AddReference does not always probe the .NET Framework
            # WPF assemblies in the GAC (observed on some 4.8 machines).  Loading
            # the same system assemblies explicitly is equivalent and keeps the
            # app free of a UIA dependency.
            from System.Reflection import Assembly  # type: ignore[import-not-found]

            loaded = False
            for base in _WPF_DIRS:
                types_path = base / "UIAutomationTypes.dll"
                client_path = base / "UIAutomationClient.dll"
                if not types_path.is_file() or not client_path.is_file():
                    continue
                Assembly.LoadFrom(str(types_path))
                Assembly.LoadFrom(str(client_path))
                loaded = True
                break
            if not loaded:
                bitness = 64 if sys.maxsize > 2**32 else 32
                raise OSError(
                    f"未找到 .NET Framework {bitness} 位 UIAutomation 程序集"
                )
        from System.Windows.Automation import (  # type: ignore[import-not-found]
            AutomationElement,
            TextPattern,
            TreeWalker,
        )

        self._modules = (AutomationElement, TextPattern, TreeWalker)

    def read(self) -> UiaSelection | None:
        if not self.load():
            return None
        assert self._modules is not None
        automation_element, text_pattern, tree_walker = self._modules
        with self._lock:
            try:
                element = automation_element.FocusedElement
                if element is None:
                    return None
                try:
                    pid = int(element.Current.ProcessId)
                except Exception:
                    pid = 0
                if pid and pid == os.getpid():
                    return None
                walker = tree_walker.ControlViewWalker
                for _ in range(8):
                    if element is None:
                        break
                    selection = self._read_element(element, text_pattern)
                    if selection is not None:
                        selection.process_id = pid or selection.process_id
                        return selection
                    try:
                        element = walker.GetParent(element)
                    except Exception:
                        break
            except Exception as exc:  # noqa: BLE001
                logger.debug("UI Automation read failed: %s", exc)
            return None

    @staticmethod
    def _read_element(element: object, text_pattern: object) -> UiaSelection | None:
        try:
            pattern = element.GetCurrentPattern(text_pattern.Pattern)
        except Exception:
            return None
        if pattern is None:
            return None
        try:
            ranges = pattern.GetSelection()
        except Exception:
            return None
        if ranges is None:
            return None

        texts: list[str] = []
        rects: list[Rect] = []
        for text_range in ranges:
            try:
                value = text_range.GetText(-1)
            except Exception:
                continue
            if not value:
                continue
            texts.append(str(value))
            try:
                raw = text_range.GetBoundingRectangles()
                values = [float(item) for item in raw]
            except Exception:
                values = []
            for index in range(0, len(values) - 3, 4):
                left, top, width, height = values[index:index + 4]
                if not all(math.isfinite(item) for item in (left, top, width, height)):
                    continue
                if width > 0 and height > 0:
                    rects.append(Rect(left, top, left + width, top + height))
        text = "".join(texts)
        if not text.strip():
            return None
        return UiaSelection(text=text, rects=rects)
