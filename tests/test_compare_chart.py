"""The comparison chart is drawn at the width it gets, not stretched to it.

It used to be a fixed 640 x 230 viewBox at 100 % width. In a wide browser that
is a factor of 2.6: 11 px labels shown at 28 px, and a chart some 600 px tall
that ran under the dashboard's bottom bar. Now it is drawn 1:1 at the width of
its box, its height grows only up to a point, and both views that show it draw
it again when they are resized.
"""

from __future__ import annotations

from pathlib import Path

JS = Path("custom_components/grib_overlay/www/grib-overlay-card.js").read_text(
    encoding="utf-8"
)
CHART = JS.split("function compareChartSvg(", 1)[1].split("\n}\n", 1)[0]
COMPARE_CARD = JS.split("class GribCompareCard extends HTMLElement", 1)[1].split(
    "class GribWeatherMapCard extends HTMLElement", 1
)[0]
MAIN_CARD = JS.split("class GribOverlayCard extends HTMLElement", 1)[1].split(
    "class GribCompareCard extends HTMLElement", 1
)[0]


def test_the_chart_is_drawn_one_to_one() -> None:
    assert 'width="100%"' not in CHART
    assert 'viewBox="0 0 ${W} ${H}" width="${W}" height="${H}"' in CHART
    assert "W = Math.max(COMPARE_CHART_MIN_WIDTH, Math.round(width || 640))" in CHART


def test_its_height_grows_only_up_to_a_point() -> None:
    assert "Math.min(320, Math.max(220, W * 0.32))" in CHART


def test_a_wider_chart_gets_more_time_labels_not_bigger_ones() -> None:
    assert "Math.floor((px1 - px0) / 70)" in CHART
    assert "spanH / cc <= maxLabels" in CHART


def test_the_compare_card_redraws_it_when_resized() -> None:
    render = COMPARE_CARD.split("  _renderComparison() {", 1)[1]
    assert "this._watchChartWidth();" in render
    assert "fitCompareChart(this._els.cmpview, this._compareSpec());" in render
    assert "new ResizeObserver(() => fitCompareChart(" in COMPARE_CARD
    # Released when the card leaves the page, set up again on the next render.
    assert "this._chartObserver.disconnect();" in COMPARE_CARD


def test_the_full_screen_meteogram_redraws_it_too() -> None:
    assert "new ResizeObserver(() => this._fitDetailChart())" in MAIN_CARD
    assert "this._detailChartObserver.disconnect();" in MAIN_CARD
    body = MAIN_CARD.split("  _setDetailBody(html) {", 1)[1].split("\n  }\n", 1)[0]
    assert "this._fitDetailChart();" in body
