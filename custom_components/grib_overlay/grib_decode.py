"""Decode HARMONIE-style multi-message GRIB1 files.

Uses the low-level eccodes API directly rather than cfgrib/xarray: KNMI's
files bundle many parameters and levels under a local (non-standard)
parameter table in a single file, which trips up cfgrib's hypercube-building
heuristics. Matching messages by their raw numeric keys
(indicatorOfParameter / indicatorOfTypeOfLevel / level) is both simpler and
more robust for this data, and those keys are unaffected by KNMI's local
table not being loaded (unlike shortName, which resolves to "unknown").

All functions here are blocking (CPU-bound), by design -- callers (the
coordinator) are responsible for running them in an executor.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import eccodes
import numpy as np

from .sources.base import GribParameter


class GribDecodeError(Exception):
    """Raised when a requested parameter's message(s) can't be found or decoded."""


@dataclass
class DecodedField:
    parameter_key: str
    data: np.ndarray  # shape (Nj, Ni), row 0 = south, row Nj-1 = north, NaN = missing
    lats: np.ndarray  # 1D, ascending, length Nj
    lons: np.ndarray  # 1D, ascending, length Ni
    valid_time: datetime
    run_time: datetime
    unit: str


def _grib_datetime(date_int: int, time_int: int) -> datetime:
    year, month, day = date_int // 10000, (date_int // 100) % 100, date_int % 100
    hour, minute = time_int // 100, time_int % 100
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _message_matches(gid: int, expected: dict) -> bool:
    for key, value in expected.items():
        try:
            actual = (
                eccodes.codes_get(gid, key, int)
                if key == "indicatorOfTypeOfLevel"
                else eccodes.codes_get(gid, key)
            )
        except Exception:  # noqa: BLE001 - unknown/unsupported key means no match
            return False
        if actual != value:
            return False
    return True


def _find_messages(path: Path, filters: dict[str, dict]) -> dict[str, int]:
    """Scan a GRIB file once, returning {name: message_id} for each matched filter.

    Caller owns the returned message handles and must release them.
    """
    remaining = dict(filters)
    found: dict[str, int] = {}
    with path.open("rb") as fh:
        while remaining:
            gid = eccodes.codes_grib_new_from_file(fh)
            if gid is None:
                break
            matched_name = next(
                (name for name, filt in remaining.items() if _message_matches(gid, filt)), None
            )
            if matched_name is not None:
                found[matched_name] = gid
                del remaining[matched_name]
            else:
                eccodes.codes_release(gid)
    return found


def _grid_arrays(gid: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    ni = eccodes.codes_get(gid, "Ni")
    nj = eccodes.codes_get(gid, "Nj")
    values = eccodes.codes_get_array(gid, "values").astype(np.float64)
    lats_flat = eccodes.codes_get_array(gid, "latitudes")
    lons_flat = eccodes.codes_get_array(gid, "longitudes")
    missing = eccodes.codes_get(gid, "missingValue")
    values = np.where(values == missing, np.nan, values)
    grid = values.reshape(nj, ni)
    lats = lats_flat.reshape(nj, ni)[:, 0]
    lons = lons_flat.reshape(nj, ni)[0, :]
    return grid, lats, lons


def _message_times(gid: int) -> tuple[datetime, datetime]:
    valid_time = _grib_datetime(
        eccodes.codes_get(gid, "validityDate"), eccodes.codes_get(gid, "validityTime")
    )
    run_time = _grib_datetime(
        eccodes.codes_get(gid, "dataDate"), eccodes.codes_get(gid, "dataTime")
    )
    return valid_time, run_time


def peek_valid_time(path: Path) -> tuple[datetime, datetime]:
    """Cheaply read (valid_time, run_time) from a member's first message.

    Used by the coordinator to decide whether a lead-time file falls inside
    the configured forecast horizon before spending time decoding every
    configured parameter out of it.
    """
    with path.open("rb") as fh:
        gid = eccodes.codes_grib_new_from_file(fh)
        if gid is None:
            raise GribDecodeError(f"{path} contains no GRIB messages")
        try:
            return _message_times(gid)
        finally:
            eccodes.codes_release(gid)


def decode_parameter(path: Path, parameter: GribParameter) -> DecodedField:
    """Extract one GribParameter's field from a single-lead-time GRIB file."""
    if parameter.kind == "vector":
        gids = _find_messages(
            path, {"u": parameter.grib_filter_u, "v": parameter.grib_filter_v}
        )
        if "u" not in gids or "v" not in gids:
            for gid in gids.values():
                eccodes.codes_release(gid)
            raise GribDecodeError(
                f"Vector parameter '{parameter.key}' missing u/v component in {path}"
            )
        try:
            u_grid, lats, lons = _grid_arrays(gids["u"])
            v_grid, _, _ = _grid_arrays(gids["v"])
            valid_time, run_time = _message_times(gids["u"])
        finally:
            for gid in gids.values():
                eccodes.codes_release(gid)
        magnitude = np.sqrt(u_grid**2 + v_grid**2)
        data = magnitude * parameter.scale + parameter.offset
    else:
        gids = _find_messages(path, {"scalar": parameter.grib_filter})
        if "scalar" not in gids:
            raise GribDecodeError(f"Parameter '{parameter.key}' not found in {path}")
        gid = gids["scalar"]
        try:
            grid, lats, lons = _grid_arrays(gid)
            valid_time, run_time = _message_times(gid)
        finally:
            eccodes.codes_release(gid)
        data = grid * parameter.scale + parameter.offset

    return DecodedField(
        parameter_key=parameter.key,
        data=data,
        lats=lats,
        lons=lons,
        valid_time=valid_time,
        run_time=run_time,
        unit=parameter.unit,
    )
