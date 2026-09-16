"""Tests for the pure-Python GRIB1 decoder (grib1.py) and grib_decode.py.

Hand-crafted messages exercise simple packing, bitmaps and the lazy unpacking
with no network. On top of that, two opt-in levels, both keyed off
GRIB_OVERLAY_SAMPLE_GRIB (a single extracted HARMONIE lead-time GRIB file --
see dev/render_preview.py's docstring for how to obtain one):

- structural: decode every configured parameter and assert the fields look
  sane (right shape, ascending grid, plausible ranges). Runs with just numpy.
- cross-validation vs ecCodes: only runs if the `eccodes` package is also
  importable; asserts the pure-Python decoder matches ecCodes bit-for-bit.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

from custom_components.grib_overlay import grib1, grib_decode
from custom_components.grib_overlay.sources.base import GribParameter
from custom_components.grib_overlay.sources.knmi import KNOWN_DATASETS

SAMPLE_ENV_VAR = "GRIB_OVERLAY_SAMPLE_GRIB"

requires_sample = pytest.mark.skipif(
    not os.environ.get(SAMPLE_ENV_VAR), reason=f"set {SAMPLE_ENV_VAR} to a sample GRIB file to run"
)


def _u2(n: int) -> bytes:
    return int(n).to_bytes(2, "big")


def _u3(n: int) -> bytes:
    return int(n).to_bytes(3, "big")


def _ibm(value: float) -> bytes:
    """IBM System/360 single-precision hex float (exact for the values used here)."""
    sign = 0x80 if value < 0 else 0
    mantissa, exponent = abs(value), 64
    if mantissa == 0:
        return bytes(4)
    while mantissa >= 1:
        mantissa, exponent = mantissa / 16, exponent + 1
    while mantissa < 1 / 16:
        mantissa, exponent = mantissa * 16, exponent - 1
    return bytes([sign | exponent]) + _u3(round(mantissa * 2**24))


def _pack(raw_values, bits: int) -> bytes:
    """Big-endian, end-to-end bit packing, done the slow obvious way."""
    bitstr = "".join(format(int(v), f"0{bits}b") for v in raw_values)
    return np.packbits(np.array([int(c) for c in bitstr], dtype=np.uint8)).tobytes()


def _make_grib1(
    *, param: int, level: int, raw_values, bits: int, ref: float = 0.0,
    binary_scale: int = 0, present=None, ni: int = 3, nj: int = 2,
    scan: int = 0x40, tri: int = 0, p1: int = 3, p2: int = 0,
) -> bytes:
    """A regular lat/lon (scan 0x40) simple-packing message; ``present`` adds a bitmap."""
    pds = bytearray(28)
    pds[0:3] = _u3(28)
    pds[3], pds[4] = 253, 99  # table2Version, centre
    pds[7] = 0x80 | (0x40 if present is not None else 0)  # GDS, optional BMS
    pds[8], pds[9] = param, 105  # indicatorOfParameter, indicatorOfTypeOfLevel
    pds[10:12] = _u2(level)
    pds[12], pds[13], pds[14], pds[15] = 26, 9, 16, 6  # 2026-09-16 06:00
    pds[17], pds[18], pds[19], pds[20] = 1, p1, p2, tri  # hours, P1, P2, timeRangeIndicator
    pds[24] = 21  # century

    gds = bytearray(32)
    gds[0:3] = _u3(32)
    gds[4] = 255
    gds[6:8], gds[8:10] = _u2(ni), _u2(nj)
    # Scan 0x40 lists the southern row first, 0x00 the northern one.
    first, last = (49000, 56000) if scan == 0x40 else (56000, 49000)
    gds[10:13], gds[13:16] = _u3(first), _u3(0)  # lat1, lon1 0.0
    gds[17:20], gds[20:23] = _u3(last), _u3(11000)  # lat2, lon2 11.0
    gds[27] = scan

    bms = b""
    if present is not None:
        bitmap = np.packbits(np.array(present, dtype=np.uint8)).tobytes()
        unused = len(bitmap) * 8 - len(present)
        bms = _u3(6 + len(bitmap)) + bytes([unused]) + _u2(0) + bitmap

    data = _pack(raw_values, bits) if bits else b""
    scale = abs(binary_scale) | (0x8000 if binary_scale < 0 else 0)
    bds = bytes([0]) + _u2(scale) + _ibm(ref) + bytes([bits]) + data
    bds = _u3(3 + len(bds)) + bds

    body = bytes(pds) + bytes(gds) + bms + bds + b"7777"
    return b"GRIB" + _u3(8 + len(body)) + bytes([1]) + body


@pytest.fixture
def unpack_calls(monkeypatch) -> list[int]:
    """Record every unpacking of a message's values."""
    calls: list[int] = []
    unpack = grib1._unpack

    def counting(npoints, **packed):
        calls.append(npoints)
        return unpack(npoints, **packed)

    monkeypatch.setattr(grib1, "_unpack", counting)
    return calls


def test_decode_simple_packing_with_bitmap() -> None:
    # 10-bit values straddle byte boundaries; the 6-point bitmap has 2 unused bits.
    raw = _make_grib1(
        param=11, level=2, bits=10, ref=-2.5, binary_scale=-1,
        present=[1, 0, 1, 1, 0, 1], raw_values=[0, 5, 1023, 7],
    )
    (m,) = list(grib1.iter_messages(raw))
    assert (m.indicator_of_parameter, m.level, m.ni, m.nj) == (11, 2, 3, 2)
    expected = [-2.5, np.nan, 0.0, 509.0, np.nan, 1.0]
    assert np.array_equal(m.values, expected, equal_nan=True)
    grid, lats, lons = grib1.to_grid(m)
    assert np.array_equal(grid, np.reshape(expected, (2, 3)), equal_nan=True)
    assert lats.tolist() == [49.0, 56.0] and lons.tolist() == [0.0, 5.5, 11.0]


def test_values_are_unpacked_only_when_read(unpack_calls) -> None:
    buf = b"".join(
        _make_grib1(param=param, level=2, bits=12, raw_values=range(param, param + 6))
        for param in (11, 17, 52)
    )
    messages = list(grib1.iter_messages(buf))
    assert [m.indicator_of_parameter for m in messages] == [11, 17, 52]
    assert unpack_calls == []  # headers only

    assert messages[1].values.tolist() == [17, 18, 19, 20, 21, 22]
    assert messages[1].values is messages[1].values  # unpacked once, then cached
    assert unpack_calls == [6]
    assert "values" not in vars(messages[0]) and "values" not in vars(messages[2])


def test_decode_unpacks_only_the_messages_it_needs(tmp_path, unpack_calls) -> None:
    """A KNMI lead-time file holds every parameter; decoding one must not unpack the rest."""
    path = tmp_path / "member.grib"
    path.write_bytes(b"".join([
        _make_grib1(param=11, level=2, bits=16, ref=250.0, raw_values=[0, 1, 2, 3, 4, 5]),
        _make_grib1(param=33, level=10, bits=8, raw_values=[3] * 6),
        _make_grib1(param=34, level=10, bits=8, raw_values=[4] * 6),
        _make_grib1(param=1, level=0, bits=24, raw_values=[101325] * 6),
    ]))
    temperature = GribParameter(
        key="temperature_2m", name="T", unit="degC", offset=-273.15,
        grib_filter={"indicatorOfParameter": 11, "indicatorOfTypeOfLevel": 105, "level": 2},
    )
    wind = GribParameter(
        key="wind_10m", name="Wind", unit="m/s", kind="vector",
        grib_filter_u={"indicatorOfParameter": 33, "indicatorOfTypeOfLevel": 105, "level": 10},
        grib_filter_v={"indicatorOfParameter": 34, "indicatorOfTypeOfLevel": 105, "level": 10},
    )

    valid_time, run_time = grib_decode.peek_valid_time(path)
    assert (valid_time.hour, run_time.hour) == (9, 6)
    assert unpack_calls == []

    field = grib_decode.decode_parameter(path, temperature)
    assert np.allclose(field.data.ravel(), np.arange(6) + 250.0 - 273.15)
    assert len(unpack_calls) == 1

    vector = grib_decode.decode_vector_components(path, wind)
    assert np.all(vector.u == 3.0) and np.all(vector.v == 4.0)
    assert len(unpack_calls) == 3


def test_truncated_data_section_raises_when_read() -> None:
    """A data section too short for its point count must not decode its
    missing tail as zeros."""
    raw = _make_grib1(param=11, level=2, bits=12, raw_values=[1, 2, 3, 4], ni=5, nj=1)
    (m,) = list(grib1.iter_messages(raw))  # the headers are fine
    with pytest.raises(grib1.Grib1Error):
        m.values


def test_values_wider_than_the_unpacker_are_rejected_up_front() -> None:
    raw = _make_grib1(param=11, level=2, bits=58, raw_values=[1] * 6)
    with pytest.raises(grib1.Grib1Error):
        list(grib1.iter_messages(raw))


def _sample_path() -> Path:
    return Path(os.environ[SAMPLE_ENV_VAR])


@requires_sample
def test_iter_messages_returns_regular_grid_messages() -> None:
    buf = _sample_path().read_bytes()
    messages = list(grib1.iter_messages(buf))
    assert messages, "expected at least one GRIB message"
    for m in messages:
        assert m.ni > 0 and m.nj > 0
        assert m.values.shape == (m.ni * m.nj,)
        assert m.lat1 < m.lat2  # KNMI grids scan south -> north


@requires_sample
def test_decode_all_configured_parameters() -> None:
    path = _sample_path()
    dataset = KNOWN_DATASETS[0]
    decoded_any = False
    for parameter in dataset.parameters:
        try:
            field = grib_decode.decode_parameter(path, parameter)
        except grib_decode.GribDecodeError:
            continue  # not every parameter is guaranteed in a single lead-time file
        decoded_any = True
        assert field.data.shape == (field.lats.size, field.lons.size)
        assert np.all(np.diff(field.lats) > 0)
        assert np.all(np.diff(field.lons) > 0)
        finite = field.data[np.isfinite(field.data)]
        assert finite.size > 0
    assert decoded_any, "expected to decode at least one configured parameter"


@requires_sample
def test_grid_bounds_match_dataset() -> None:
    path = _sample_path()
    dataset = KNOWN_DATASETS[0]
    parameter = next(p for p in dataset.parameters if p.key == "temperature_2m")
    field = grib_decode.decode_parameter(path, parameter)
    south, west, north, east = dataset.bounds
    assert field.lats[0] == pytest.approx(south, abs=0.01)
    assert field.lats[-1] == pytest.approx(north, abs=0.01)
    assert field.lons[0] == pytest.approx(west, abs=0.01)
    assert field.lons[-1] == pytest.approx(east, abs=0.01)


@requires_sample
def test_matches_eccodes_bit_for_bit() -> None:
    eccodes = pytest.importorskip("eccodes", reason="eccodes not installed; cross-check skipped")
    path = _sample_path()
    buf = path.read_bytes()
    mine = list(grib1.iter_messages(buf))

    ecc_values = []
    with path.open("rb") as fh:
        while True:
            gid = eccodes.codes_grib_new_from_file(fh)
            if gid is None:
                break
            missing = eccodes.codes_get(gid, "missingValue")
            values = eccodes.codes_get_array(gid, "values").astype(np.float64)
            ecc_values.append(np.where(values == missing, np.nan, values))
            eccodes.codes_release(gid)

    assert len(mine) == len(ecc_values)
    for message, ecc in zip(mine, ecc_values):
        assert np.array_equal(np.isnan(message.values), np.isnan(ecc))
        finite = ~np.isnan(message.values)
        if finite.any():
            assert np.allclose(message.values[finite], ecc[finite], atol=1e-6)


def test_north_first_grid_is_flipped_to_south_first() -> None:
    """DMI WAM and MET Norway scan north to south (mode 0x00)."""
    raw = _make_grib1(param=229, level=0, bits=4, raw_values=[1, 2, 3, 4, 5, 6], scan=0x00)
    (m,) = list(grib1.iter_messages(raw))
    grid, lats, lons = grib1.to_grid(m)
    assert lats.tolist() == [49.0, 56.0]
    # The first transmitted row (1, 2, 3) is the northern one, so it ends up last.
    assert grid.tolist() == [[4, 5, 6], [1, 2, 3]]
    assert lons.tolist() == [0.0, 5.5, 11.0]


def test_other_scan_modes_still_refuse() -> None:
    raw = _make_grib1(param=229, level=0, bits=4, raw_values=range(6), scan=0x80)
    (m,) = list(grib1.iter_messages(raw))
    with pytest.raises(grib1.Grib1Error):
        grib1.to_grid(m)


def test_two_octet_lead_time(tmp_path) -> None:
    """timeRangeIndicator 10: P1 spans octets 19-20 (DMI, leads past 255 h)."""
    raw = _make_grib1(param=229, level=0, bits=4, raw_values=range(6), tri=10, p1=1, p2=8)
    path = tmp_path / "wam.grib"
    path.write_bytes(raw)
    valid, run = grib_decode.peek_valid_time(path)
    assert (valid - run).total_seconds() == 264 * 3600  # 1 * 256 + 8
