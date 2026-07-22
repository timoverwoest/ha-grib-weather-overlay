"""Unit tests for the scalar field grid build + point sampling (no GRIB/HA)."""

from __future__ import annotations

import numpy as np

from custom_components.grib_overlay import field_grid


def _field():
    # 4x4 grid, ascending lats (row 0 = south) and lons (col 0 = west).
    lats = np.array([49.0, 51.0, 53.0, 55.0])
    lons = np.array([0.0, 2.0, 4.0, 6.0])
    # value = latitude, so sampling should recover the latitude at any point.
    data = np.repeat(lats[:, None], 4, axis=1)
    return field_grid.build_field(data, lats, lons)


def test_build_field_is_north_first():
    field = _field()
    assert field["la1"] == 55.0  # first row is northernmost
    assert field["lo1"] == 0.0
    assert field["nx"] == 4 and field["ny"] == 4
    # data[0] is the NW corner: latitude 55.0
    assert field["data"][0] == 55.0


def test_sample_field_interpolates_and_bounds():
    field = _field()
    # value == latitude, so sampling at lat=52 should give ~52 regardless of lon.
    assert abs(field_grid.sample_field(field, 52.0, 3.0) - 52.0) < 0.01
    assert abs(field_grid.sample_field(field, 55.0, 0.0) - 55.0) < 0.01
    # outside the grid -> None
    assert field_grid.sample_field(field, 40.0, 3.0) is None
    assert field_grid.sample_field(field, 52.0, 20.0) is None


def test_sample_field_handles_missing_values():
    lats = np.array([49.0, 51.0])
    lons = np.array([0.0, 2.0])
    data = np.array([[1.0, np.nan], [np.nan, np.nan]])
    field = field_grid.build_field(data, lats, lons)
    # only one finite corner; nearest that corner still resolves, far corner None
    assert field_grid.sample_field(field, 49.0, 0.0) is not None
