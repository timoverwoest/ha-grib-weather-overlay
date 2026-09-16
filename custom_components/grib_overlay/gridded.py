"""Per-lead-time member files for gridded data that doesn't arrive as GRIB.

The coordinator decodes a run from member files, one lead time each, through
grib_decode. Rijkswaterstaat's model output comes as one NetCDF file for a
whole run instead, so its source splits it into these members: a numpy ``.npz``
holding each field on a regular, south-first lat/lon grid plus the valid and
run time. grib_decode recognises them by their zip signature and hands back
messages that behave like GRIB messages (``matches``, ``values``, ``to_grid``).
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

MAGIC = b"PK\x03\x04"


class GriddedError(Exception):
    """Raised for a member file that doesn't hold what it should."""


@dataclass
class FieldMessage:
    """One field of a member, shaped like a GRIB message for grib_decode."""

    field: str
    values: np.ndarray  # flat, rows south -> north
    ni: int
    nj: int
    lats: np.ndarray
    lons: np.ndarray
    valid_time: datetime
    run_time: datetime
    rotation: None = None

    def matches(self, filt: dict) -> bool:
        """A filter is ``{"field": <name>}``."""
        return set(filt) == {"field"} and filt["field"] == self.field


def write_member(
    path: Path,
    *,
    fields: dict[str, np.ndarray],
    lats: np.ndarray,
    lons: np.ndarray,
    valid_time: datetime,
    run_time: datetime,
) -> None:
    """Store ``fields`` (each ``[len(lats), len(lons)]``, south-first) for one lead time."""
    lats = np.asarray(lats, dtype=np.float64)
    lons = np.asarray(lons, dtype=np.float64)
    if lats.ndim != 1 or lons.ndim != 1 or np.any(np.diff(lats) <= 0) or np.any(np.diff(lons) <= 0):
        raise GriddedError("lats and lons must be ascending 1-D axes")
    arrays = {}
    for name, grid in fields.items():
        grid = np.asarray(grid, dtype=np.float32)
        if grid.shape != (lats.size, lons.size):
            raise GriddedError(f"field {name} has shape {grid.shape}, expected {(lats.size, lons.size)}")
        arrays[f"field_{name}"] = grid
    buf = io.BytesIO()
    np.savez_compressed(
        buf,
        lats=lats,
        lons=lons,
        times=np.array([valid_time.timestamp(), run_time.timestamp()], dtype=np.float64),
        **arrays,
    )
    path.write_bytes(buf.getvalue())


def iter_messages(buf: bytes) -> list[FieldMessage]:
    try:
        with np.load(io.BytesIO(buf), allow_pickle=False) as npz:
            lats, lons, times = npz["lats"], npz["lons"], npz["times"]
            valid_time = datetime.fromtimestamp(float(times[0]), tz=timezone.utc)
            run_time = datetime.fromtimestamp(float(times[1]), tz=timezone.utc)
            return [
                FieldMessage(
                    field=key[len("field_"):],
                    values=npz[key].astype(np.float64).ravel(),
                    ni=lons.size,
                    nj=lats.size,
                    lats=lats,
                    lons=lons,
                    valid_time=valid_time,
                    run_time=run_time,
                )
                for key in npz.files
                if key.startswith("field_")
            ]
    except (KeyError, ValueError, OSError) as err:
        raise GriddedError(f"not a gridded member file: {err}") from err


def to_grid(message: FieldMessage) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    return message.values.reshape(message.nj, message.ni), message.lats, message.lons


def message_times(message: FieldMessage) -> tuple[datetime, datetime]:
    return message.valid_time, message.run_time
