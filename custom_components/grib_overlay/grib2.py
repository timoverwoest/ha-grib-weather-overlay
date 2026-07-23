"""Minimal, dependency-free GRIB2 decoder for DWD wave-model (EWAM) files.

The GRIB1 decoder in grib1.py covers KNMI's HARMONIE files; DWD's Open Data wave
model (EWAM) is GRIB2 instead. Rather than pull in the fragile eccodes binary
(the very dependency the GRIB1 decoder exists to avoid), we decode the small
corner of GRIB2 that EWAM actually uses, with numpy alone.

Scope (verified against real EWAM files from opendata.dwd.de):
- GRIB edition 2.
- Section 3 (Grid Definition): regular lat/lon, grid definition template 3.0.
- Section 4 (Product Definition): template 4.0 (analysis/forecast at a level).
- Section 5 (Data Representation): grid-point *simple* packing, template 5.0
  (reference value is IEEE-754 float32, plus binary and decimal scale factors).
  EWAM uses this -- crucially NOT CCSDS/AEC (5.42) or JPEG2000 (5.40), which
  would need a binary decompressor.
- Section 6 (Bit Map): in-line bitmap for missing (land) points.

Anything outside this scope raises Grib2Error so the caller can skip the message
rather than silently mis-decode it. Blocking/CPU-bound; run via an executor.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np

MISSING = np.nan


class Grib2Error(Exception):
    """Raised when a message uses a GRIB2 feature this minimal decoder doesn't support."""


@dataclass
class Grib2Message:
    # Identification (Section 0/1)
    discipline: int
    reference_time: datetime
    # Product Definition (Section 4, template 4.0)
    parameter_category: int
    parameter_number: int
    type_of_level: int
    level: float
    unit_of_time_range: int
    forecast_time: int
    # Grid Definition (Section 3, template 3.0) -- regular lat/lon
    ni: int
    nj: int
    lat1: float
    lon1: float
    lat2: float
    lon2: float
    scan_mode: int
    # Decoded data, flat, in the message's own scan order; NaN where missing.
    values: np.ndarray
    # Regular grids only -> never rotated; kept so callers can treat Grib1/Grib2
    # messages uniformly (see grib_decode.py).
    rotation: tuple[float, float, float] | None = None

    def matches(self, filt: dict) -> bool:
        """True if every (key, value) in ``filt`` matches. Keys are GRIB2 fields:
        discipline / parameterCategory / parameterNumber / indicatorOfTypeOfLevel
        / level."""
        mapping = {
            "discipline": self.discipline,
            "parameterCategory": self.parameter_category,
            "parameterNumber": self.parameter_number,
            "indicatorOfTypeOfLevel": self.type_of_level,
            "level": self.level,
        }
        for key, expected in filt.items():
            if mapping.get(key) != expected:
                return False
        return True


def _u(b: bytes) -> int:
    return int.from_bytes(b, "big")


def _sign_mag(raw: int, bits: int) -> int:
    """GRIB sign-and-magnitude integer (top bit = sign)."""
    sign_bit = 1 << (bits - 1)
    if raw & sign_bit:
        return -(raw & (sign_bit - 1))
    return raw


def _latlon(raw: int) -> float:
    """GRIB2 lat/lon: 4-byte sign-magnitude integer in units of 1e-6 degrees."""
    return _sign_mag(raw, 32) / 1_000_000.0


def _float32(b: bytes) -> float:
    """IEEE-754 single-precision float (GRIB2 reference value)."""
    return float(np.frombuffer(b, dtype=">f4")[0])


def iter_messages(buf: bytes):
    """Yield a Grib2Message for each GRIB2 record in ``buf``."""
    pos = 0
    while True:
        idx = buf.find(b"GRIB", pos)
        if idx < 0:
            return
        edition = buf[idx + 7]
        if edition != 2:
            raise Grib2Error(f"not a GRIB2 message (edition {edition})")
        total_len = _u(buf[idx + 8:idx + 16])
        if total_len <= 0 or idx + total_len > len(buf):
            return  # truncated / malformed
        yield _parse_message(buf[idx:idx + total_len])
        pos = idx + total_len


def _parse_message(msg: bytes) -> Grib2Message:
    discipline = msg[6]
    rec: dict = {"discipline": discipline}
    bitmap = None
    npoints = None

    o = 16  # Section 0 is 16 octets in edition 2
    while o < len(msg):
        if msg[o:o + 4] == b"7777":
            break
        seclen = _u(msg[o:o + 4])
        if seclen < 5 or o + seclen > len(msg):
            raise Grib2Error("malformed section length")
        secnum = msg[o + 4]
        s = msg[o:o + seclen]

        if secnum == 1:
            rec["reference_time"] = datetime(
                _u(s[12:14]), s[14], s[15], s[16], s[17], s[18], tzinfo=timezone.utc
            )
        elif secnum == 3:
            gdt = _u(s[12:14])
            if gdt != 0:
                raise Grib2Error(f"unsupported grid definition template {gdt}")
            rec.update(
                ni=_u(s[30:34]),
                nj=_u(s[34:38]),
                lat1=_latlon(_u(s[46:50])),
                lon1=_latlon(_u(s[50:54])),
                lat2=_latlon(_u(s[55:59])),
                lon2=_latlon(_u(s[59:63])),
                scan_mode=s[71],
            )
        elif secnum == 4:
            pdt = _u(s[7:9])
            if pdt not in (0, 8):  # 0 = instantaneous, 8 = accumulation/interval
                raise Grib2Error(f"unsupported product definition template {pdt}")
            rec.update(
                parameter_category=s[9],
                parameter_number=s[10],
                unit_of_time_range=s[17],
                forecast_time=_u(s[18:22]),
                type_of_level=s[22],
                level=_sign_mag(_u(s[24:28]), 32) / (10.0 ** s[23]) if s[23] != 255 else 0.0,
            )
        elif secnum == 5:
            drt = _u(s[9:11])
            if drt != 0:
                raise Grib2Error(f"unsupported data representation template {drt}")
            npoints = _u(s[5:9])
            rec["_ref"] = _float32(s[11:15])
            rec["_bin_scale"] = _sign_mag(_u(s[15:17]), 16)
            rec["_dec_scale"] = _sign_mag(_u(s[17:19]), 16)
            rec["_bits"] = s[19]
        elif secnum == 6:
            indicator = s[5]
            if indicator == 0:
                bitmap = np.unpackbits(np.frombuffer(s[6:], dtype=np.uint8))
            elif indicator != 255:
                raise Grib2Error("predefined bitmaps are not supported")
        elif secnum == 7:
            rec["_data"] = s[5:]

        o += seclen

    return _finish(rec, npoints, bitmap)


def _finish(rec: dict, npoints: int | None, bitmap) -> Grib2Message:
    ni, nj = rec["ni"], rec["nj"]
    total = ni * nj
    ref, bin_scale, dec_scale, bits = (
        rec.pop("_ref"), rec.pop("_bin_scale"), rec.pop("_dec_scale"), rec.pop("_bits")
    )
    data_bytes = rec.pop("_data")
    if bitmap is not None:
        bitmap = bitmap[:total].astype(bool)
        n_present = int(bitmap.sum())
    else:
        n_present = npoints if npoints is not None else total

    dec = 10.0 ** dec_scale
    if bits == 0:
        present = np.full(n_present, ref / dec, dtype=np.float64)
    else:
        packed = np.frombuffer(data_bytes, dtype=np.uint8)
        raw_bits = np.unpackbits(packed)[: n_present * bits].reshape(n_present, bits)
        weights = (1 << np.arange(bits - 1, -1, -1)).astype(np.uint64)
        raw = (raw_bits.astype(np.uint64) * weights).sum(axis=1)
        present = (ref + raw.astype(np.float64) * (2.0 ** bin_scale)) / dec

    if bitmap is not None:
        values = np.full(total, MISSING, dtype=np.float64)
        values[bitmap] = present
    else:
        values = present

    rec["values"] = values
    return Grib2Message(**rec)


def to_grid(message: Grib2Message) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (grid[Nj, Ni] rows south->north, lats[Nj] asc, lons[Ni] asc).

    Handles the two i-consecutive scan modes DWD emits for regular lat/lon:
    0x00 (north-first, +i east) and 0x40 (south-first, +i east). Longitudes are
    normalised to the -180..180 range (DWD numbers the domain 0..360, e.g. the
    western edge is 349.5 rather than -10.5).
    """
    scan = message.scan_mode
    if scan & 0x20:
        raise Grib2Error("j-consecutive scan order not supported")
    if scan & 0x80:
        raise Grib2Error("east-to-west scan not supported")
    grid = message.values.reshape(message.nj, message.ni)
    # DWD numbers the domain 0..360 and scans +i (west->east); when the domain
    # straddles the prime meridian the eastern edge wraps below the western
    # (e.g. lon1=349.5 .. lon2=42.0). Unwrap so the axis is monotonic, then map
    # back to -180..180.
    lon2 = message.lon2 + 360.0 if message.lon2 <= message.lon1 else message.lon2
    lons = np.linspace(message.lon1, lon2, message.ni)
    lons = np.where(lons > 180.0, lons - 360.0, lons)
    if scan & 0x40:  # +j : rows already run south -> north
        lats = np.linspace(message.lat1, message.lat2, message.nj)
    else:  # -j : first row is northernmost -> flip to south-first
        grid = np.flipud(grid)
        lats = np.linspace(message.lat2, message.lat1, message.nj)
    return grid, lats, lons


# GRIB2 unitOfTimeRange codes -> hours (same code table as GRIB1).
_TIME_UNIT_HOURS = {0: 1 / 60, 1: 1, 2: 24, 10: 3, 11: 6, 12: 12, 13: 0.25}


def message_times(message: Grib2Message) -> tuple[datetime, datetime]:
    """(valid_time, run_time) for a Grib2Message."""
    run_time = message.reference_time
    unit_hours = _TIME_UNIT_HOURS.get(message.unit_of_time_range, 1)
    valid_time = run_time + timedelta(hours=message.forecast_time * unit_hours)
    return valid_time, run_time
