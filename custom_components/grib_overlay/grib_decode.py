"""Decode HARMONIE-style multi-message GRIB1 files.

Uses the in-tree pure-Python decoder in ``grib1.py`` rather than
eccodes/cfgrib: the ecCodes binary wheel isn't built for every CPython
ABI/platform, so on some Home Assistant installs ``pip install eccodes``
fails and takes the whole integration down. KNMI's HARMONIE files use only
the simplest GRIB1 packing, which grib1.py decodes bit-exactly with numpy
alone.

Messages are matched by their raw numeric keys (indicatorOfParameter /
indicatorOfTypeOfLevel / level); KNMI uses a local parameter table so
shortName-based matching wouldn't work anyway.

All functions here are blocking (CPU-bound), by design -- callers (the
coordinator) are responsible for running them in an executor.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from . import grib1, grib2, reproject
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


@dataclass
class DecodedVector:
    """Raw u/v wind components (for particle/vector overlays)."""

    u: np.ndarray  # shape (Nj, Ni), row 0 = south
    v: np.ndarray
    lats: np.ndarray  # 1D ascending
    lons: np.ndarray  # 1D ascending
    valid_time: datetime
    run_time: datetime


def _grib_datetime(date_int: int, time_int: int) -> datetime:
    year, month, day = date_int // 10000, (date_int // 100) % 100, date_int % 100
    hour, minute = time_int // 100, time_int % 100
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


# GRIB1 unitOfTimeRange codes -> hours, for the units KNMI HARMONIE emits.
_TIME_UNIT_HOURS = {0: 1 / 60, 1: 1, 2: 24, 10: 3, 11: 6, 12: 12, 13: 0.25}


def _iter_messages(buf: bytes):
    """Yield messages from a GRIB1 or GRIB2 buffer, dispatching on the edition."""
    idx = buf.find(b"GRIB")
    edition = buf[idx + 7] if idx >= 0 else 1
    return (grib2 if edition == 2 else grib1).iter_messages(buf)


def _to_grid(message):
    """Grid extraction dispatched by message type (GRIB1 vs GRIB2)."""
    module = grib2 if isinstance(message, grib2.Grib2Message) else grib1
    return module.to_grid(message)


def _message_times(message) -> tuple[datetime, datetime]:
    if isinstance(message, grib2.Grib2Message):
        return grib2.message_times(message)
    run_time = _grib_datetime(message.data_date, message.data_time)
    unit_hours = _TIME_UNIT_HOURS.get(message.unit_of_time_range, 1)
    # timeRangeIndicator 0/1 = instantaneous forecast valid at reference + P1.
    # Interval products (2=valid-over, 3=average, 4=accumulation, 5=difference)
    # span reference+P1..reference+P2 and are labelled at the end, i.e. P2 --
    # matching how ecCodes fills validityDate/validityTime.
    step = message.p2 if message.time_range_indicator in (2, 3, 4, 5) else message.p1
    valid_time = run_time + timedelta(hours=step * unit_hours)
    return valid_time, run_time


def _load_messages(path: Path) -> list:
    return list(_iter_messages(path.read_bytes()))


def _find(messages: list[grib1.Grib1Message], filt: dict) -> grib1.Grib1Message | None:
    return next((m for m in messages if m.matches(filt)), None)


def peek_valid_time(path: Path) -> tuple[datetime, datetime]:
    """Cheaply read (valid_time, run_time) from a member's first message.

    Used by the coordinator to decide whether a lead-time file falls inside
    the configured forecast horizon before spending time decoding every
    configured parameter out of it.
    """
    buf = path.read_bytes()
    for message in _iter_messages(buf):
        return _message_times(message)
    raise GribDecodeError(f"{path} contains no GRIB messages")


def decode_parameter(path: Path, parameter: GribParameter) -> DecodedField:
    """Extract one GribParameter's field from a single-lead-time GRIB file."""
    messages = _load_messages(path)

    if parameter.kind == "vector":
        u_msg = _find(messages, parameter.grib_filter_u)
        v_msg = _find(messages, parameter.grib_filter_v)
        if u_msg is None or v_msg is None:
            raise GribDecodeError(
                f"Vector parameter '{parameter.key}' missing u/v component in {path}"
            )
        u_grid, lats, lons = _to_grid(u_msg)
        v_grid, _, _ = _to_grid(v_msg)
        valid_time, run_time = _message_times(u_msg)
        # Wind speed (magnitude) is rotation-invariant, so for the scalar field
        # we can resample it directly -- no need to rotate the components.
        data = np.sqrt(u_grid**2 + v_grid**2) * parameter.scale + parameter.offset
        if u_msg.rotation is not None:
            data, lats, lons = reproject.regrid_scalar(data, lats, lons, u_msg.rotation)
    else:
        msg = _find(messages, parameter.grib_filter)
        if msg is None:
            raise GribDecodeError(f"Parameter '{parameter.key}' not found in {path}")
        grid, lats, lons = _to_grid(msg)
        valid_time, run_time = _message_times(msg)
        data = grid * parameter.scale + parameter.offset
        if msg.rotation is not None:
            data, lats, lons = reproject.regrid_scalar(data, lats, lons, msg.rotation)

    return DecodedField(
        parameter_key=parameter.key,
        data=data,
        lats=lats,
        lons=lons,
        valid_time=valid_time,
        run_time=run_time,
        unit=parameter.unit,
    )


def decode_vector_components(path: Path, parameter: GribParameter) -> DecodedVector:
    """Extract the raw u/v components of a vector parameter (wind), unscaled (m/s)."""
    if parameter.kind != "vector":
        raise GribDecodeError(f"Parameter '{parameter.key}' is not a vector parameter")
    messages = _load_messages(path)
    u_msg = _find(messages, parameter.grib_filter_u)
    v_msg = _find(messages, parameter.grib_filter_v)
    if u_msg is None or v_msg is None:
        raise GribDecodeError(
            f"Vector parameter '{parameter.key}' missing u/v component in {path}"
        )
    u_grid, lats, lons = _to_grid(u_msg)
    v_grid, _, _ = _to_grid(v_msg)
    valid_time, run_time = _message_times(u_msg)
    if u_msg.rotation is not None:
        # Rotated grid: resample AND rotate the components to true east/north so
        # particle/vector directions (and the meteogram bearing) stay correct.
        u_grid, v_grid, lats, lons = reproject.regrid_vector(
            u_grid, v_grid, lats, lons, u_msg.rotation
        )
    return DecodedVector(
        u=u_grid, v=v_grid, lats=lats, lons=lons, valid_time=valid_time, run_time=run_time
    )
