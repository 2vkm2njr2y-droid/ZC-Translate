from __future__ import annotations

from app.shell.geometry import (
    Rect,
    choose_anchor,
    css_height,
    inflate_rect,
    max_height_css,
    overlay_width_css,
    place_overlay,
    rect_contains_point,
    union_rects,
)


def test_union_rects_skips_empty_and_builds_bbox():
    union = union_rects([Rect(10, 20, 40, 50), Rect(30, 10, 60, 30), Rect(5, 5, 5, 5)])
    assert union == Rect(10, 10, 60, 50)
    assert union_rects([]) is None


def test_choose_anchor_uses_uia_when_point_inside():
    anchor = choose_anchor(
        [Rect(100, 100, 300, 140)],
        Rect(90, 90, 320, 150),
        (250, 125),
    )
    assert anchor == Rect(100, 100, 300, 140)


def test_choose_anchor_falls_back_when_uia_rect_is_far_away():
    fallback = choose_anchor(
        [Rect(500, 500, 700, 540)],
        Rect(100, 100, 160, 130),
        (150, 120),
    )
    assert fallback == Rect(100, 100, 160, 130)


def test_overlay_width_is_bounded_and_fits_work_area():
    assert overlay_width_css(Rect(0, 0, 80, 20), 1.0, 1600) == 300
    assert overlay_width_css(Rect(0, 0, 1000, 20), 1.0, 1600) == 440
    assert overlay_width_css(Rect(0, 0, 1000, 20), 1.0, 300) == 284


def test_place_overlay_prefers_above():
    rect = place_overlay(
        Rect(200, 300, 600, 360), Rect(0, 0, 1600, 900), 400, 120, 1.0
    )
    assert rect.left == 200
    assert rect.top == 172
    assert rect.bottom == 292


def test_place_overlay_flips_below_and_clamps():
    rect = place_overlay(
        Rect(50, 10, 300, 40), Rect(0, 0, 800, 600), 400, 120, 1.0
    )
    assert rect.top == 48
    assert rect.left == 0
    assert rect.right == 400

    bottom = place_overlay(
        Rect(700, 580, 750, 595), Rect(0, 0, 800, 600), 400, 120, 1.0
    )
    assert bottom.top >= 0
    assert bottom.bottom <= 600


def test_place_overlay_accounts_for_dpi_scale():
    rect = place_overlay(
        Rect(100, 300, 500, 340), Rect(0, 0, 2560, 1440), 400, 100, 1.5
    )
    assert rect.width == 600
    assert rect.height == 150
    assert rect.right >= 600


def test_inflate_rect_gives_flat_drag_a_line_height():
    rect = inflate_rect(Rect(100, 300, 500, 300), left=2, right=2, top=18, bottom=6)
    assert rect == Rect(98, 282, 502, 306)


def test_height_helpers():
    assert max_height_css(1000) == 360
    assert max_height_css(200) == 176
    assert max_height_css(100) == 96
    assert css_height(10, 200) == 56
    assert css_height(500, 360) == 360
    assert rect_contains_point(Rect(0, 0, 10, 10), 5, 5)
    assert not rect_contains_point(Rect(0, 0, 10, 10), 20, 5)
