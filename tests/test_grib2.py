"""Tests for the pure-Python GRIB2 decoder (grib2.py), used for DWD EWAM waves.

A hand-crafted minimal GRIB2 message exercises the section/template parsing and
simple packing with no network. An opt-in test decodes a real EWAM file when
GRIB_OVERLAY_EWAM_GRIB points at one (a single ``.grib2`` from
opendata.dwd.de's ewam tree, bunzip2'd).
"""

from __future__ import annotations

import os
import struct
from pathlib import Path

import numpy as np
import pytest

from custom_components.grib_overlay import grib2


def _u2(n: int) -> bytes:
    return int(n).to_bytes(2, "big")


def _u4(n: int) -> bytes:
    return int(n).to_bytes(4, "big")


def _make_grib2(*, ni, nj, lat1, lon1, lat2, lon2, cat, num, ref, bits, raw_values,
                forecast_time=3, end_time=None) -> bytes:
    # Section 1 (identification), 21 octets, reference time 2026-07-22 00:00Z
    s1 = bytearray(21)
    s1[0:4] = _u4(21); s1[4] = 1
    s1[12:14] = _u2(2026); s1[14], s1[15], s1[16] = 7, 22, 0

    # Section 3 (grid definition), template 3.0 regular lat/lon, 72 octets
    s3 = bytearray(72)
    s3[0:4] = _u4(72); s3[4] = 3
    s3[6:10] = _u4(ni * nj)
    # s3[12:14] template = 0 (already zero)
    s3[30:34] = _u4(ni); s3[34:38] = _u4(nj)
    s3[46:50] = _u4(int(round(lat1 * 1e6)))
    s3[50:54] = _u4(int(round(lon1 * 1e6)))
    s3[55:59] = _u4(int(round(lat2 * 1e6)))
    s3[59:63] = _u4(int(round(lon2 * 1e6)))
    s3[71] = 0x00  # scan +i east, -j (north first)

    # Section 4 (product definition): template 4.0 (34 octets), or 4.8 (58
    # octets) when an interval end_time is given
    s4 = bytearray(34 if end_time is None else 58)
    s4[0:4] = _u4(len(s4)); s4[4] = 4
    if end_time is not None:
        s4[7:9] = _u2(8)
        s4[34:36] = _u2(end_time.year)
        s4[36:41] = bytes([end_time.month, end_time.day, end_time.hour, end_time.minute, 0])
    s4[9] = cat; s4[10] = num
    s4[17] = 1  # unit of time range = hour
    s4[18:22] = _u4(forecast_time)
    s4[22] = 101  # type of level
    s4[23] = 0    # scale factor
    s4[24:28] = _u4(0)  # level value

    # Section 5 (data representation), template 5.0 simple packing, 21 octets
    s5 = bytearray(21)
    s5[0:4] = _u4(21); s5[4] = 5
    s5[5:9] = _u4(len(raw_values))
    # s5[9:11] drt = 0
    s5[11:15] = struct.pack(">f", ref)
    # binary + decimal scale = 0
    s5[19] = bits

    # Section 6 (bitmap): none
    s6 = bytes([0, 0, 0, 6, 6, 255])

    # Section 7 (data): pack raw values big-endian bit order
    bit_list = []
    for v in raw_values:
        bit_list.extend(int(b) for b in format(v, f"0{bits}b"))
    packed = np.packbits(np.array(bit_list, dtype=np.uint8)).tobytes()
    s7 = _u4(5 + len(packed)) + bytes([7]) + packed

    body = bytes(s1) + bytes(s3) + bytes(s4) + bytes(s5) + s6 + s7 + b"7777"
    total = 16 + len(body)
    sec0 = b"GRIB" + b"\x00\x00" + bytes([10]) + bytes([2]) + total.to_bytes(8, "big")
    return sec0 + body


def test_parse_and_decode_simple_packing() -> None:
    raw = _make_grib2(
        ni=3, nj=2, lat1=50.0, lon1=4.0, lat2=48.0, lon2=8.0,
        cat=0, num=3, ref=10.0, bits=4, raw_values=[0, 1, 2, 3, 4, 5], forecast_time=3,
    )
    (m,) = list(grib2.iter_messages(raw))
    assert m.discipline == 10 and m.parameter_category == 0 and m.parameter_number == 3
    assert m.matches({"discipline": 10, "parameterCategory": 0, "parameterNumber": 3})
    assert not m.matches({"discipline": 10, "parameterNumber": 4})

    valid, run = grib2.message_times(m)
    assert run.year == 2026 and run.hour == 0
    assert (valid - run).total_seconds() == 3 * 3600

    grid, lats, lons = grib2.to_grid(m)
    assert grid.shape == (2, 3)
    assert np.all(np.diff(lats) > 0)  # south -> north after flip
    assert np.all(np.diff(lons) > 0)
    # values 10..15; row order flipped so the northern row (was first) is last
    assert set(np.round(grid.ravel()).astype(int)) == {10, 11, 12, 13, 14, 15}


def test_interval_product_is_valid_at_the_end_of_its_interval() -> None:
    """ICON-D2's precipitation is a total since the run start (forecast time 0,
    template 4.8); its value belongs to the END of that interval, not the start."""
    from datetime import datetime, timezone

    end = datetime(2026, 7, 22, 3, 0, tzinfo=timezone.utc)
    raw = _make_grib2(
        ni=2, nj=1, lat1=50.0, lon1=4.0, lat2=50.0, lon2=5.0,
        cat=1, num=52, ref=0.0, bits=4, raw_values=[1, 2], forecast_time=0, end_time=end,
    )
    (m,) = list(grib2.iter_messages(raw))
    valid, run = grib2.message_times(m)
    assert m.end_time == end
    assert valid == end and run.hour == 0


def test_zero_length_interval_is_not_offered_as_a_frame(tmp_path) -> None:
    """At +0h ICON's gust maximum and precipitation total cover no time at all:
    their zeros would show as a calm, dry first hour."""
    from datetime import datetime, timezone

    from custom_components.grib_overlay import grib_decode
    from custom_components.grib_overlay.sources.base import GribParameter

    param = GribParameter(
        key="wind_gust_10m", name="gust", unit="m/s",
        grib_filter={"discipline": 10, "parameterCategory": 2, "parameterNumber": 22},
    )
    run = datetime(2026, 7, 22, 0, tzinfo=timezone.utc)
    for end, expect_frame in ((run, False), (run.replace(hour=1), True)):
        path = tmp_path / f"gust_{end:%H}.grib2"
        path.write_bytes(_make_grib2(
            ni=2, nj=1, lat1=50.0, lon1=4.0, lat2=50.0, lon2=5.0,
            cat=2, num=22, ref=0.0, bits=4, raw_values=[0, 0], forecast_time=0, end_time=end,
        ))
        if expect_frame:
            assert grib_decode.decode_parameter(path, param).valid_time == end
        else:
            with pytest.raises(grib_decode.GribDecodeError):
                grib_decode.decode_parameter(path, param)


def test_longitude_wrap_normalisation() -> None:
    # DWD numbers 0..360; a domain from 349.5 (west) to 42 (east) must unwrap to
    # a monotonic -10.5 .. 42 axis.
    raw = _make_grib2(
        ni=4, nj=1, lat1=60.0, lon1=349.5, lat2=60.0, lon2=42.0,
        cat=0, num=3, ref=0.0, bits=4, raw_values=[1, 2, 3, 4],
    )
    (m,) = list(grib2.iter_messages(raw))
    _, _, lons = grib2.to_grid(m)
    assert lons[0] == pytest.approx(-10.5, abs=1e-4)
    assert lons[-1] == pytest.approx(42.0, abs=1e-4)
    assert np.all(np.diff(lons) > 0)


_EWAM = os.environ.get("GRIB_OVERLAY_EWAM_GRIB")


@pytest.mark.skipif(not _EWAM, reason="set GRIB_OVERLAY_EWAM_GRIB to a real EWAM .grib2 file")
def test_real_ewam_file() -> None:
    buf = Path(_EWAM).read_bytes()
    messages = list(grib2.iter_messages(buf))
    assert messages
    m = messages[0]
    assert m.discipline == 10  # oceanographic
    grid, lats, lons = grib2.to_grid(m)
    assert grid.shape == (m.nj, m.ni)
    assert np.all(np.diff(lats) > 0) and np.all(np.diff(lons) > 0)
    finite = grid[np.isfinite(grid)]
    assert finite.size > 0  # sea points present, land masked


@pytest.mark.parametrize("bits", [1, 3, 8, 9, 10, 12, 16, 17, 24, 31, 32])
def test_bit_unpacking_round_trips(bits) -> None:
    """Values packed end to end come back exactly, for whole-byte widths (fast
    path) and odd widths alike -- including a value that straddles a byte."""
    rng = np.random.default_rng(bits)
    values = rng.integers(0, 2**bits, size=37, dtype=np.uint64)
    bitstr = "".join(format(int(v), f"0{bits}b") for v in values)
    data = np.packbits(np.array([int(c) for c in bitstr], dtype=np.uint8)).tobytes()
    assert np.array_equal(grib2._unpack_bits(data, len(values), bits), values)
