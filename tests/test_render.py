"""Tests for render.py, in particular the Web-Mercator row warp that keeps a
wide-latitude overlay aligned with Leaflet's imageOverlay placement."""

from __future__ import annotations

import numpy as np

from custom_components.grib_overlay import grib_decode, render


def test_mercator_row_map_endpoints_and_direction() -> None:
    m = render._mercator_north_first_rows(30.0, 66.0, 721)
    assert m[0] == 720  # top image row comes from the northernmost data row
    assert m[-1] == 0  # bottom row from the southernmost
    assert np.all(np.diff(m) <= 0)  # north -> south, monotonic
    # Mercator stretches high latitudes, so the geometric-middle output row must
    # pull from a data row north of the middle (index > 360).
    assert m[360] > 360


def test_small_span_is_near_identity_flip() -> None:
    # For a narrow span (NL), the warp is essentially just a north-first flip.
    n = 100
    m = render._mercator_north_first_rows(49.0, 56.0, n)
    flip = np.arange(n - 1, -1, -1)
    # A 7-degree span barely curves in Mercator: within a few rows of a plain
    # flip (the small correction is what keeps even NL pixel-accurate).
    assert np.max(np.abs(m - flip)) <= 3


def test_render_field_shape_and_bounds() -> None:
    lats = np.linspace(30.0, 66.0, 40)
    lons = np.linspace(-10.5, 42.0, 30)
    data = np.tile(lats[:, None], (1, lons.size))  # value == latitude
    data[0, 0] = np.nan  # a missing point
    field = grib_decode.DecodedField(
        parameter_key="wave_height", data=data, lats=lats, lons=lons,
        valid_time=None, run_time=None, unit="m",
    )
    frame, legend = render.render_field(field, colormap="wave", value_range=(0, 8))
    assert frame.width == lons.size and frame.height == lats.size
    assert frame.bounds == (30.0, -10.5, 66.0, 42.0)
    assert len(frame.png_bytes) > 0
