"""Tests for cutting a decoded field down to a dataset's window.

Only one source needs this so far: DWD publishes GWAM on the whole globe, and
keeping that would make every frame a world map -- thinned, by the time it
reaches the card, to a handful of points over the North Sea. The awkward part
is the longitude axis: a grid numbered 0..360 comes out of the decoder wrapped
to -180..180 but still in publishing order, so it jumps from 179.75 to -180
halfway and a window reaching west of Greenwich is two blocks, not one.
"""

from __future__ import annotations

import numpy as np
import pytest

from custom_components.grib_overlay import grib_decode
from custom_components.grib_overlay.sources.base import GribParameter

from .test_grib2 import _make_grib2

# 0, 45, 90, 135, 180, 225, 270, 315 -> the decoder's -180..180 mapping.
_WRAPPED = np.array([0.0, 45.0, 90.0, 135.0, 180.0, -135.0, -90.0, -45.0])


def test_a_grid_that_already_fits_is_left_alone() -> None:
    lats = np.array([50.0, 51.0, 52.0])
    lons = np.array([2.0, 3.0, 4.0])
    assert grib_decode._crop_plan(lats, lons, (40.0, -10.0, 60.0, 10.0)) is None


def test_a_wider_grid_is_cut_to_the_window() -> None:
    lats = np.arange(40.0, 60.1, 1.0)
    lons = np.arange(-10.0, 10.1, 1.0)
    rows, cols, cut_lats, cut_lons = grib_decode._crop_plan(
        lats, lons, (50.0, -2.0, 53.0, 4.0)
    )
    assert cut_lats.tolist() == [50.0, 51.0, 52.0, 53.0]
    assert cut_lons.tolist() == [-2.0, -1.0, 0.0, 1.0, 2.0, 3.0, 4.0]
    assert lats[rows].tolist() == cut_lats.tolist()
    assert lons[cols].tolist() == cut_lons.tolist()


def test_a_window_outside_the_grid_is_an_error() -> None:
    """Better a run that fails and is retried than frames of nothing."""
    lats = np.arange(40.0, 60.1, 1.0)
    lons = np.arange(-10.0, 10.1, 1.0)
    with pytest.raises(grib_decode.GribDecodeError, match="outside the grid"):
        grib_decode._crop_plan(lats, lons, (10.0, -40.0, 20.0, -30.0))


def test_a_wrapped_global_axis_comes_back_sorted_and_contiguous() -> None:
    lats = np.arange(-10.0, 10.1, 5.0)
    rows, cols, cut_lats, cut_lons = grib_decode._crop_plan(
        lats, _WRAPPED, (-5.0, -100.0, 5.0, 50.0)
    )
    assert cut_lons.tolist() == [-90.0, -45.0, 0.0, 45.0]
    assert np.all(np.diff(cut_lons) > 0)
    # The columns are the original positions of those longitudes, re-ordered:
    # 270 and 315 come from the end of the published row, 0 and 45 from its start.
    assert cols.tolist() == [6, 7, 0, 1]
    assert cut_lats.tolist() == [-5.0, 0.0, 5.0]


def test_the_same_plan_applies_to_several_grids() -> None:
    """u and v must be cut identically, or the wind would point somewhere else."""
    lats = np.arange(0.0, 4.1, 1.0)
    plan = grib_decode._crop_plan(lats, _WRAPPED, (1.0, -50.0, 3.0, 50.0))
    u = np.arange(5 * 8, dtype=float).reshape(5, 8)
    v = u * -1.0
    cut_u, cut_v = grib_decode._cropped(plan, u, v)
    assert cut_u.shape == cut_v.shape == (3, 3)
    assert np.array_equal(cut_u, -cut_v)
    # Column order follows the sorted longitudes (-45, 0, 45), so the value that
    # sat at index 7 leads each row.
    assert cut_u[0].tolist() == [15.0, 8.0, 9.0]


def _global_message() -> bytes:
    """One synthetic global field: 8 longitudes from 0 to 315, 4 latitudes."""
    return _make_grib2(
        ni=8, nj=4, lat1=30.0, lon1=0.0, lat2=0.0, lon2=315.0,
        cat=0, num=3, ref=0.0, bits=6, raw_values=list(range(32)), forecast_time=3,
    )


def test_decoding_with_a_window_keeps_the_values_it_kept(tmp_path) -> None:
    path = tmp_path / "global.grib2"
    path.write_bytes(_global_message())
    parameter = GribParameter(
        key="wave_height", name="x", unit="m",
        grib_filter={"discipline": 10, "parameterCategory": 0, "parameterNumber": 3},
    )

    whole = grib_decode.decode_parameter(path, parameter)
    cut = grib_decode.decode_parameter(path, parameter, (0.0, -100.0, 20.0, 50.0))

    assert whole.data.shape == (4, 8)
    assert cut.data.shape == (3, 4)
    assert np.all(np.diff(cut.lons) > 0)
    for lat in cut.lats:
        for lon in cut.lons:
            here = cut.data[np.argmin(abs(cut.lats - lat)), np.argmin(abs(cut.lons - lon))]
            there = whole.data[
                np.argmin(abs(whole.lats - lat)), np.argmin(abs(whole.lons - lon))
            ]
            assert here == there


def test_decoding_vector_components_with_a_window(tmp_path) -> None:
    """decode_vector_components has its own path through the crop."""
    path = tmp_path / "wind.grib2"
    u = _make_grib2(
        ni=8, nj=4, lat1=30.0, lon1=0.0, lat2=0.0, lon2=315.0,
        cat=2, num=2, ref=0.0, bits=6, raw_values=list(range(32)), forecast_time=3,
    )
    v = _make_grib2(
        ni=8, nj=4, lat1=30.0, lon1=0.0, lat2=0.0, lon2=315.0,
        cat=2, num=3, ref=0.0, bits=6, raw_values=list(range(32)), forecast_time=3,
    )
    path.write_bytes(u + v)
    parameter = GribParameter(
        key="wind_10m", name="x", unit="m/s", kind="vector",
        grib_filter_u={"discipline": 10, "parameterCategory": 2, "parameterNumber": 2},
        grib_filter_v={"discipline": 10, "parameterCategory": 2, "parameterNumber": 3},
    )

    vec = grib_decode.decode_vector_components(path, parameter, (0.0, -100.0, 20.0, 50.0))
    assert vec.u.shape == vec.v.shape == (3, 4)
    assert np.array_equal(vec.u, vec.v)
    assert np.all(np.diff(vec.lons) > 0)
