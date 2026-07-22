"""Build the JSON that leaflet-velocity expects from raw u/v wind grids.

leaflet-velocity reads two "records" (u where parameterCategory,parameterNumber
== 2,2 and v == 2,3), each with a grid header (nx, ny, lo1, la1, dx, dy) and a
flat ``data`` array ordered from the NW corner (la1 = north, lo1 = west) going
east, then south -- row-major. Our decoded grids have ascending latitudes
(row 0 = south), so rows are flipped to put north first.

The grid is downsampled: a HARMONIE field is 390x390, which is both heavier
than the particle animation needs and slow to ship as JSON. leaflet-velocity
interpolates, so a coarser grid animates just as smoothly.
"""

from __future__ import annotations

from datetime import datetime

import numpy as np

# Target at most this many points per axis in the velocity grid.
_MAX_POINTS_PER_AXIS = 160


def _header(nx: int, ny: int, lons: np.ndarray, lats: np.ndarray, param_number: int,
            valid_time: datetime) -> dict:
    return {
        "parameterCategory": 2,
        "parameterNumber": param_number,  # 2 = u (eastward), 3 = v (northward)
        "parameterUnit": "m.s-1",
        "nx": nx,
        "ny": ny,
        "lo1": float(lons.min()),
        "la1": float(lats.max()),  # first grid point is the north-west corner
        "lo2": float(lons.max()),
        "la2": float(lats.min()),
        "dx": float((lons.max() - lons.min()) / (nx - 1)) if nx > 1 else 0.0,
        "dy": float((lats.max() - lats.min()) / (ny - 1)) if ny > 1 else 0.0,
        "refTime": valid_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "forecastTime": 0,
    }


def build_velocity_data(
    u: np.ndarray,
    v: np.ndarray,
    lats: np.ndarray,
    lons: np.ndarray,
    valid_time: datetime,
) -> list[dict]:
    """Return the two-record list leaflet-velocity consumes as its ``data``."""
    nj, ni = u.shape
    step = max(1, int(np.ceil(max(nj, ni) / _MAX_POINTS_PER_AXIS)))

    lats_ds = lats[::step]
    lons_ds = lons[::step]
    # Flip rows so the first row is the northernmost latitude, then downsample.
    u_ds = np.flipud(u)[::step, ::step]
    v_ds = np.flipud(v)[::step, ::step]
    ny, nx = u_ds.shape

    # leaflet-velocity can't plot missing values; fall back to 0 (calm).
    u_flat = np.nan_to_num(u_ds, nan=0.0).round(2).ravel().tolist()
    v_flat = np.nan_to_num(v_ds, nan=0.0).round(2).ravel().tolist()

    return [
        {"header": _header(nx, ny, lons_ds, lats_ds, 2, valid_time), "data": u_flat},
        {"header": _header(nx, ny, lons_ds, lats_ds, 3, valid_time), "data": v_flat},
    ]
