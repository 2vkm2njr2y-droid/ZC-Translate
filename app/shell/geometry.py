"""Pure geometry and DPI helpers for the selection overlay.

All rectangles use physical screen pixels unless the name ends in ``_css``.
Keeping this module free of Win32 imports makes the placement rules easy to
test without a GUI.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class Rect:
    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self) -> float:
        return max(0.0, self.right - self.left)

    @property
    def height(self) -> float:
        return max(0.0, self.bottom - self.top)

    @property
    def center_x(self) -> float:
        return self.left + self.width / 2.0

    @property
    def center_y(self) -> float:
        return self.top + self.height / 2.0

    @property
    def is_empty(self) -> bool:
        return self.width <= 0.5 or self.height <= 0.5

    def as_points(self) -> tuple[float, float, float, float]:
        return self.left, self.top, self.right, self.bottom


def union_rects(rects: Iterable[Rect]) -> Rect | None:
    items = [rect for rect in rects if rect is not None and not rect.is_empty]
    if not items:
        return None
    return Rect(
        min(rect.left for rect in items),
        min(rect.top for rect in items),
        max(rect.right for rect in items),
        max(rect.bottom for rect in items),
    )


def rect_from_points(x1: float, y1: float, x2: float, y2: float) -> Rect:
    return Rect(min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))


def inflate_rect(rect: Rect, *, left: float = 0.0, top: float = 0.0,
                 right: float = 0.0, bottom: float = 0.0) -> Rect:
    return Rect(rect.left - left, rect.top - top, rect.right + right, rect.bottom + bottom)


def rect_contains_point(rect: Rect, x: float, y: float, tolerance: float = 0.0) -> bool:
    return (
        rect.left - tolerance <= x <= rect.right + tolerance
        and rect.top - tolerance <= y <= rect.bottom + tolerance
    )


def choose_anchor(
    selection_rects: Iterable[Rect],
    gesture_bounds: Rect | None,
    up_point: tuple[float, float],
    *,
    tolerance: float = 48.0,
) -> Rect | None:
    """Prefer the UIA selection rectangle, with a safe gesture fallback.

    Some providers return rectangles in a different DPI space, so a rectangle
    that does not contain the mouse-up point is treated as suspicious.  The
    caller still gets an anchor, just one based on the user's drag bounds.
    """

    union = union_rects(selection_rects)
    if union is not None and rect_contains_point(union, up_point[0], up_point[1], tolerance):
        return union
    fallback = gesture_bounds if gesture_bounds is not None and not gesture_bounds.is_empty else None
    if fallback is not None:
        return fallback
    return union


def overlay_width_css(
    anchor: Rect,
    scale: float,
    work_width_css: float,
    *,
    min_width: float = 300.0,
    max_width: float = 440.0,
) -> float:
    scale = max(0.5, min(scale, 4.0))
    anchor_css = anchor.width / scale
    width = max(min_width, min(max_width, anchor_css + 48.0))
    available = max(220.0, work_width_css - 16.0)
    return max(220.0, min(width, available))


def max_height_css(work_height_css: float, *, maximum: float = 360.0) -> float:
    return max(96.0, min(maximum, work_height_css - 24.0))


def css_height(height_css: float, maximum_css: float, *, minimum: float = 56.0) -> float:
    return max(minimum, min(maximum_css, height_css))


def place_overlay(
    anchor: Rect,
    work_area: Rect,
    width_css: float,
    height_css: float,
    scale: float,
    *,
    gap_css: float = 8.0,
) -> Rect:
    """Return the physical rectangle for the floating card.

    The card is centred over the selection and sits above it.  If the top of
    the work area is reached it flips below the selection, then clamps to the
    monitor work area.
    """

    scale = max(0.5, min(scale, 4.0))
    width = max(120.0, round(width_css * scale))
    height = max(48.0, round(height_css * scale))
    gap = max(0.0, round(gap_css * scale))

    max_width = max(1.0, work_area.width)
    max_height = max(1.0, work_area.height)
    width = min(width, max_width)
    height = min(height, max_height)

    x = anchor.center_x - width / 2.0
    x = max(work_area.left, min(x, work_area.right - width))

    y = anchor.top - gap - height
    if y < work_area.top:
        y = anchor.bottom + gap
    if y + height > work_area.bottom:
        y = max(work_area.top, work_area.bottom - height)
    if y < work_area.top:
        y = work_area.top

    return Rect(x, y, x + width, y + height)
