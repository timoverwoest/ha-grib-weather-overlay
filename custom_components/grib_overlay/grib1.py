"""Minimal, dependency-free GRIB1 decoder for KNMI HARMONIE files.

Why not eccodes/cfgrib? The ecCodes binary library ships as the ``eccodeslib``
wheel, which is only built for a subset of Python ABIs/platforms. On a Home
Assistant install running a newer CPython (e.g. 3.14) than eccodeslib has
wheels for, ``pip install eccodes`` fails outright, taking the whole
integration down with a RequirementsNotFound error. KNMI's HARMONIE files use
only the simplest corner of the GRIB1 format, so decoding them ourselves with
just numpy removes that fragile binary dependency entirely.

Scope (verified bit-exact against ecCodes across every message in a real
``harmonie_arome_cy43_p1`` run):
- GRIB edition 1 only.
- Section 2 (GDS): regular lat/lon grid (data representation type 0) and
  rotated lat/lon grid (type 10, used by the Europe ``p3`` dataset -- the
  extra rotation-pole octets are read and exposed as ``rotation`` so callers
  can reproject to a regular geographic grid; see reproject.py).
- Section 3 (BMS): optional bitmap for missing values (in-line bitmap only,
  no predefined bitmap tables).
- Section 4 (BDS): grid-point, simple packing; constant fields
  (bitsPerValue == 0) supported.
- Reference value is IBM single-precision hex float (GRIB1), NOT IEEE 754.

Anything outside this scope raises Grib1Error so the caller can skip the
message rather than silently mis-decode it.

All functions are blocking/CPU-bound by design; callers run them in an
executor.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

MISSING = np.nan


class Grib1Error(Exception):
    """Raised when a message uses a GRIB1 feature this minimal decoder doesn't support."""


@dataclass
class Grib1Message:
    # Product Definition Section (raw numeric keys, matching what sources/*.py filter on)
    table2_version: int
    centre: int
    indicator_of_parameter: int
    indicator_of_type_of_level: int
    level: int
    data_date: int  # YYYYMMDD
    data_time: int  # HHMM
    unit_of_time_range: int
    p1: int
    p2: int
    time_range_indicator: int
    # Grid Definition Section (regular lat/lon)
    ni: int
    nj: int
    lat1: float
    lon1: float
    lat2: float
    lon2: float
    scan_mode: int
    # Decoded data, flat, in the message's own scan order; NaN where missing.
    values: np.ndarray
    # (south_pole_lat, south_pole_lon, angle_of_rotation) for a rotated lat/lon
    # grid (data representation type 10), else None. lat1/lon1/lat2/lon2 above
    # are then in the *rotated* coordinate system; reproject.py maps them back
    # to geographic coordinates.
    rotation: tuple[float, float, float] | None = None

    def matches(self, filt: dict) -> bool:
        """True if every (key, value) in ``filt`` matches this message's PDS.

        Keys are the raw GRIB1 numeric field names used by sources/knmi.py:
        indicatorOfParameter / indicatorOfTypeOfLevel / level.
        """
        mapping = {
            "indicatorOfParameter": self.indicator_of_parameter,
            "indicatorOfTypeOfLevel": self.indicator_of_type_of_level,
            "level": self.level,
            "table2Version": self.table2_version,
            "centre": self.centre,
        }
        for key, expected in filt.items():
            if mapping.get(key) != expected:
                return False
        return True


def _u(b: bytes) -> int:
    """Unsigned big-endian int from bytes."""
    return int.from_bytes(b, "big")


def _signed(raw: int, bits: int) -> int:
    """GRIB sign-and-magnitude integer (top bit is the sign, not two's complement)."""
    sign_bit = 1 << (bits - 1)
    if raw & sign_bit:
        return -(raw & (sign_bit - 1))
    return raw


def _ibm_hex_float(raw_bytes: bytes) -> float:
    """Decode a 4-byte IBM System/360 single-precision hex float (GRIB1 reference value)."""
    raw = _u(raw_bytes)
    sign = -1.0 if (raw >> 31) & 0x1 else 1.0
    exponent = (raw >> 24) & 0x7F
    mantissa = raw & 0x00FFFFFF
    return sign * (mantissa / (2 ** 24)) * (16.0 ** (exponent - 64))


def iter_messages(buf: bytes):
    """Yield a Grib1Message for each GRIB1 record in ``buf``.

    Messages using unsupported features raise Grib1Error; the caller decides
    whether to skip or propagate.
    """
    pos = 0
    while True:
        idx = buf.find(b"GRIB", pos)
        if idx < 0:
            return
        total_len = _u(buf[idx + 4:idx + 7])
        edition = buf[idx + 7]
        if edition != 1:
            raise Grib1Error(f"unsupported GRIB edition {edition}")
        if total_len <= 0 or idx + total_len > len(buf):
            return  # truncated / malformed trailer
        yield _parse_message(buf[idx:idx + total_len])
        pos = idx + total_len


def _parse_message(msg: bytes) -> Grib1Message:
    o = 8  # Section 0 (indicator) is 8 octets in edition 1

    # -- Section 1: Product Definition Section --
    pds_len = _u(msg[o:o + 3])
    pds = msg[o:o + pds_len]
    flags = pds[7]
    gds_present = bool(flags & 0x80)
    bms_present = bool(flags & 0x40)
    yy, month, day = pds[12], pds[13], pds[14]
    hour, minute = pds[15], pds[16]
    century = pds[24] if pds_len > 24 else 21
    year = (century - 1) * 100 + yy
    rec = {
        "table2_version": pds[3],
        "centre": pds[4],
        "indicator_of_parameter": pds[8],
        "indicator_of_type_of_level": pds[9],
        "level": _u(pds[10:12]),
        "data_date": year * 10000 + month * 100 + day,
        "data_time": hour * 100 + minute,
        "unit_of_time_range": pds[17],
        "p1": pds[18],
        "p2": pds[19],
        "time_range_indicator": pds[20],
    }
    o += pds_len

    # -- Section 2: Grid Definition Section --
    if not gds_present:
        raise Grib1Error("message without a Grid Definition Section is not supported")
    gds_len = _u(msg[o:o + 3])
    gds = msg[o:o + gds_len]
    data_rep_type = gds[5]
    # 0 = regular lat/lon; 10 = rotated lat/lon (same octet layout up to the
    # scan mode, with three extra rotation-pole fields at octets 33-42).
    if data_rep_type not in (0, 10):
        raise Grib1Error(f"unsupported grid data representation type {data_rep_type}")
    ni = _u(gds[6:8])
    nj = _u(gds[8:10])
    rotation = None
    if data_rep_type == 10:
        rotation = (
            _signed(_u(gds[32:35]), 24) / 1000.0,  # latitude of the southern pole
            _signed(_u(gds[35:38]), 24) / 1000.0,  # longitude of the southern pole
            _ibm_hex_float(gds[38:42]),            # angle of rotation
        )
    rec.update(
        ni=ni,
        nj=nj,
        lat1=_signed(_u(gds[10:13]), 24) / 1000.0,
        lon1=_signed(_u(gds[13:16]), 24) / 1000.0,
        lat2=_signed(_u(gds[17:20]), 24) / 1000.0,
        lon2=_signed(_u(gds[20:23]), 24) / 1000.0,
        scan_mode=gds[27],
        rotation=rotation,
    )
    o += gds_len

    # -- Section 3: Bit Map Section (optional) --
    bitmap = None
    if bms_present:
        bms_len = _u(msg[o:o + 3])
        bms = msg[o:o + bms_len]
        unused_bits = bms[3]
        table_ref = _u(bms[4:6])
        if table_ref != 0:
            raise Grib1Error("predefined bitmap tables are not supported")
        bitmap = np.unpackbits(np.frombuffer(bms[6:], dtype=np.uint8))
        if unused_bits:
            bitmap = bitmap[:-unused_bits]
        o += bms_len

    # -- Section 4: Binary Data Section --
    bds_len = _u(msg[o:o + 3])
    bds = msg[o:o + bds_len]
    bds_flags = bds[3]
    if bds_flags & 0x80:
        raise Grib1Error("spherical harmonic / non-grid-point data is not supported")
    if bds_flags & 0x40:
        raise Grib1Error("second-order (complex) packing is not supported")
    binary_scale = _signed(_u(bds[4:6]), 16)
    reference_value = _ibm_hex_float(bds[6:10])
    bits_per_value = bds[10]

    npoints = ni * nj
    n_present = int(bitmap.sum()) if bitmap is not None else npoints

    if bits_per_value == 0:
        present = np.full(n_present, reference_value, dtype=np.float64)
    else:
        packed = np.frombuffer(bds[11:], dtype=np.uint8)
        bits = np.unpackbits(packed)[: n_present * bits_per_value]
        bits = bits.reshape(n_present, bits_per_value)
        weights = (1 << np.arange(bits_per_value - 1, -1, -1)).astype(np.uint64)
        raw = (bits.astype(np.uint64) * weights).sum(axis=1)
        present = reference_value + raw.astype(np.float64) * (2.0 ** binary_scale)

    if bitmap is not None:
        values = np.full(npoints, MISSING, dtype=np.float64)
        values[bitmap.astype(bool)] = present
    else:
        values = present

    return Grib1Message(values=values, **rec)


def to_grid(message: Grib1Message) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (grid[Nj, Ni] south->north rows, lats[Nj] ascending, lons[Ni] ascending).

    Only scan mode 0x40 (+i west->east, +j south->north, i-consecutive) is
    produced by the KNMI HARMONIE datasets and validated here; other scan
    modes raise so we never silently return a flipped/rotated grid.
    """
    if message.scan_mode != 0x40:
        raise Grib1Error(f"unsupported scanning mode {message.scan_mode:#04x}")
    grid = message.values.reshape(message.nj, message.ni)
    lats = np.linspace(message.lat1, message.lat2, message.nj)
    lons = np.linspace(message.lon1, message.lon2, message.ni)
    return grid, lats, lons
