"""Unit tests for the leaflet-velocity JSON builder (no GRIB/HA needed)."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from custom_components.grib_overlay import velocity


def test_build_velocity_data_header_and_ordering() -> None:
    # 4x4 grid, ascending lats (row 0 = south) and lons (col 0 = west).
    lats = np.array([49.0, 51.0, 53.0, 55.0])
    lons = np.array([0.0, 2.0, 4.0, 6.0])
    u = np.arange(16, dtype=float).reshape(4, 4)  # row 0 = south
    v = np.zeros((4, 4))
    valid = datetime(2026, 7, 21, 15, 0, tzinfo=timezone.utc)

    records = velocity.build_velocity_data(u, v, lats, lons, valid)
    assert len(records) == 2
    uh, vh = records[0]["header"], records[1]["header"]

    # u = eastward (2,2), v = northward (2,3)
    assert (uh["parameterCategory"], uh["parameterNumber"]) == (2, 2)
    assert (vh["parameterCategory"], vh["parameterNumber"]) == (2, 3)

    # First grid point is the NW corner: la1 = north (max lat), lo1 = west.
    assert uh["la1"] == 55.0
    assert uh["la2"] == 49.0
    assert uh["lo1"] == 0.0
    assert uh["lo2"] == 6.0
    assert uh["nx"] == 4 and uh["ny"] == 4

    # Data must be north-first: first value = north-west corner = u[3, 0] = 12.
    assert records[0]["data"][0] == 12.0
    assert len(records[0]["data"]) == 16


def test_build_velocity_data_downsamples_large_grid() -> None:
    lats = np.linspace(49.0, 56.0, 390)
    lons = np.linspace(0.0, 11.0, 390)
    u = np.ones((390, 390))
    records = velocity.build_velocity_data(u, u, lats, lons, datetime(2026, 7, 21, tzinfo=timezone.utc))
    # 390 -> downsampled to <= 160 points per axis.
    assert records[0]["header"]["nx"] <= 160
    assert records[0]["header"]["ny"] <= 160
