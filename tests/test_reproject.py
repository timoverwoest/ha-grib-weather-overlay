"""Tests for rotated lat/lon support: the reprojection math (reproject.py),
the GRIB1 GDS type-10 parsing (grib1.py), and the end-to-end decode path.

These need no sample GRIB file -- the rotation transforms are exercised with
plain arrays and a hand-crafted minimal rotated GRIB1 message.
"""

from __future__ import annotations

import numpy as np
import pytest

from custom_components.grib_overlay import grib1, grib_decode, reproject
from custom_components.grib_overlay.sources.base import GribParameter


# --------------------------------------------------------------------------
# rotation transforms
# --------------------------------------------------------------------------


def test_identity_pole_is_a_no_op() -> None:
    # South pole at the real south pole, no longitude offset -> identity.
    lats = np.array([45.0, 52.0, 60.0])
    lons = np.array([-5.0, 4.0, 15.0])
    rlat, rlon = reproject.geo_to_rotated(lats, lons, -90.0, 0.0)
    assert np.allclose(rlat, lats)
    assert np.allclose(rlon, lons)


def test_round_trip_geo_rotated_geo() -> None:
    lon, lat = np.meshgrid(np.linspace(-15, 25, 9), np.linspace(42, 66, 7))
    for sp_lat, sp_lon in [(-30.0, 15.0), (-40.0, 0.0), (-35.0, -10.0)]:
        rlat, rlon = reproject.geo_to_rotated(lat, lon, sp_lat, sp_lon)
        back_lat, back_lon = reproject.rotated_to_geo(rlat, rlon, sp_lat, sp_lon)
        assert np.allclose(back_lat, lat, atol=1e-6)
        assert np.allclose(back_lon, lon, atol=1e-6)


def test_rotated_north_pole_maps_to_expected_latitude() -> None:
    # The rotated north pole (rlat=90) sits at geographic latitude -sp_lat.
    lat, _ = reproject.rotated_to_geo(90.0, 0.0, -30.0, 15.0)
    assert lat == pytest.approx(30.0, abs=1e-6)


# --------------------------------------------------------------------------
# scalar / vector resampling
# --------------------------------------------------------------------------


def test_regrid_scalar_recovers_encoded_geo_latitude() -> None:
    rot = (-30.0, 15.0, 0.0)
    rlats = np.linspace(-14, 14, 57)
    rlons = np.linspace(-18, 18, 73)
    rlon_m, rlat_m = np.meshgrid(rlons, rlats)
    # Encode geographic latitude into the field; after reprojection each target
    # cell should read back its own geographic latitude.
    geo_lat, _ = reproject.rotated_to_geo(rlat_m, rlon_m, rot[0], rot[1])
    out, lats_geo, lons_geo = reproject.regrid_scalar(geo_lat, rlats, rlons, rot)
    _, lat_target = np.meshgrid(lons_geo, lats_geo)
    finite = np.isfinite(out)
    assert finite.mean() > 0.3  # a decent chunk of the bbox is covered
    assert np.allclose(out[finite], lat_target[finite], atol=0.3)


def test_regrid_vector_no_rotation_preserves_components() -> None:
    rot = (-90.0, 0.0, 0.0)  # no tilt
    rlats = np.linspace(40, 60, 41)
    rlons = np.linspace(-10, 20, 61)
    u = np.full((rlats.size, rlons.size), 1.0)
    v = np.zeros_like(u)
    u_geo, v_geo, _, _ = reproject.regrid_vector(u, v, rlats, rlons, rot)
    finite = np.isfinite(u_geo)
    assert np.allclose(u_geo[finite], 1.0, atol=1e-6)
    assert np.allclose(v_geo[finite], 0.0, atol=1e-6)


def test_regrid_vector_preserves_magnitude_under_rotation() -> None:
    rot = (-30.0, 15.0, 0.0)
    rlats = np.linspace(-12, 12, 49)
    rlons = np.linspace(-16, 16, 65)
    u = np.full((rlats.size, rlons.size), 3.0)
    v = np.full((rlats.size, rlons.size), 4.0)
    u_geo, v_geo, _, _ = reproject.regrid_vector(u, v, rlats, rlons, rot)
    finite = np.isfinite(u_geo)
    assert np.allclose(np.hypot(u_geo[finite], v_geo[finite]), 5.0, atol=1e-3)


# --------------------------------------------------------------------------
# GRIB1 GDS type-10 (rotated lat/lon) parsing + end-to-end decode
# --------------------------------------------------------------------------


def _u3(n: int) -> bytes:
    return int(n).to_bytes(3, "big")


def _u2(n: int) -> bytes:
    return int(n).to_bytes(2, "big")


def _sgn3(deg: float) -> bytes:
    raw = int(round(abs(deg) * 1000))
    if deg < 0:
        raw |= 1 << 23
    return raw.to_bytes(3, "big")


def _make_rotated_message(
    *, ni: int, nj: int, lat1: float, lon1: float, lat2: float, lon2: float,
    sp_lat: float, sp_lon: float,
) -> bytes:
    # Section 1 (PDS), 28 octets: temperature-like (param 11, level type 105, level 2)
    pds = bytearray(28)
    pds[0:3] = _u3(28)
    pds[3] = 253      # table2Version
    pds[4] = 99       # centre
    pds[6] = 255      # grid definition (not catalogued)
    pds[7] = 0x80     # GDS present, no BMS
    pds[8] = 11       # indicatorOfParameter
    pds[9] = 105      # indicatorOfTypeOfLevel
    pds[10:12] = _u2(2)   # level
    pds[12], pds[13], pds[14] = 26, 7, 18   # yy, month, day
    pds[15], pds[16] = 2, 0                 # hour, minute
    pds[17] = 1       # unitOfTimeRange (hours)
    pds[24] = 21      # century -> 2026

    # Section 2 (GDS), 42 octets: rotated lat/lon (type 10)
    gds = bytearray(42)
    gds[0:3] = _u3(42)
    gds[4] = 255      # PV/PL
    gds[5] = 10       # data representation type = rotated lat/lon
    gds[6:8] = _u2(ni)
    gds[8:10] = _u2(nj)
    gds[10:13] = _sgn3(lat1)
    gds[13:16] = _sgn3(lon1)
    gds[17:20] = _sgn3(lat2)
    gds[20:23] = _sgn3(lon2)
    gds[27] = 0x40    # scan mode +i east, +j north
    gds[32:35] = _sgn3(sp_lat)
    gds[35:38] = _sgn3(sp_lon)
    # gds[38:42] angle of rotation = 0.0 (IBM float all-zero)

    # Section 4 (BDS), 12 octets: constant field (bitsPerValue == 0), ref 0.0
    bds = bytearray(12)
    bds[0:3] = _u3(12)
    # flags/scale/reference all zero, bitsPerValue (octet 11) == 0

    body = bytes(pds) + bytes(gds) + bytes(bds) + b"7777"
    total = 8 + len(body)
    return b"GRIB" + _u3(total) + bytes([1]) + body


def test_parse_rotated_gds() -> None:
    raw = _make_rotated_message(
        ni=3, nj=2, lat1=-5.0, lon1=-10.0, lat2=5.0, lon2=10.0, sp_lat=-30.0, sp_lon=15.0
    )
    (msg,) = list(grib1.iter_messages(raw))
    assert msg.ni == 3 and msg.nj == 2
    assert msg.rotation is not None
    sp_lat, sp_lon, angle = msg.rotation
    assert sp_lat == pytest.approx(-30.0)
    assert sp_lon == pytest.approx(15.0)
    assert angle == pytest.approx(0.0)
    assert msg.lat1 == pytest.approx(-5.0)
    assert msg.lon2 == pytest.approx(10.0)
    grid, lats, lons = grib1.to_grid(msg)
    assert grid.shape == (2, 3)  # rotated-space coords, still regular


def test_decode_parameter_reprojects_rotated_message(tmp_path) -> None:
    raw = _make_rotated_message(
        ni=40, nj=30, lat1=-10.0, lon1=-15.0, lat2=10.0, lon2=15.0, sp_lat=-30.0, sp_lon=15.0
    )
    path = tmp_path / "rotated.grib"
    path.write_bytes(raw)
    param = GribParameter(
        key="temperature_2m", name="T", unit="degC",
        grib_filter={"indicatorOfParameter": 11, "indicatorOfTypeOfLevel": 105, "level": 2},
        offset=-273.15,
    )
    field = grib_decode.decode_parameter(path, param)
    # Reprojected onto a regular geographic grid: ascending 1-D axes, and the
    # constant 0 K field becomes a constant -273.15 degC where data exists.
    assert np.all(np.diff(field.lats) > 0)
    assert np.all(np.diff(field.lons) > 0)
    assert field.data.shape == (field.lats.size, field.lons.size)
    finite = field.data[np.isfinite(field.data)]
    assert finite.size > 0
    assert np.allclose(finite, -273.15, atol=1e-6)
