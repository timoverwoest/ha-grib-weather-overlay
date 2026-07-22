"""Compact scalar grid storage + point sampling for click-value / meteogram.

A decoded field is downsampled and stored north-first (row 0 = northernmost
latitude) as a small JSON blob per frame per parameter. The point endpoint
reads these back and bilinearly samples a value at a lat/lon -- used both for
the click-to-read value and the meteogram time series.
"""

from __future__ import annotations

import math

import numpy as np

# Target at most this many points per axis in the stored grid.
_MAX_POINTS_PER_AXIS = 160


def build_field(data: np.ndarray, lats: np.ndarray, lons: np.ndarray) -> dict:
    """Downsample a decoded field (row 0 = south) into a north-first grid dict."""
    nj, ni = data.shape
    step = max(1, int(math.ceil(max(nj, ni) / _MAX_POINTS_PER_AXIS)))
    lats_ds = lats[::step]
    lons_ds = lons[::step]
    grid = np.flipud(data)[::step, ::step]  # north-first
    ny, nx = grid.shape
    # JSON has no NaN; store missing values as None.
    flat = [None if not math.isfinite(v) else round(float(v), 2) for v in grid.ravel()]
    return {
        "nx": nx,
        "ny": ny,
        "lo1": float(lons_ds.min()),
        "la1": float(lats_ds.max()),
        "dx": float((lons_ds.max() - lons_ds.min()) / (nx - 1)) if nx > 1 else 0.0,
        "dy": float((lats_ds.max() - lats_ds.min()) / (ny - 1)) if ny > 1 else 0.0,
        "data": flat,
    }


def sample_field(field: dict, lat: float, lon: float) -> float | None:
    """Bilinearly sample the stored grid at (lat, lon); None if outside/missing."""
    nx, ny = field["nx"], field["ny"]
    dx, dy = field["dx"], field["dy"]
    if nx < 2 or ny < 2 or dx == 0 or dy == 0:
        return None
    fx = (lon - field["lo1"]) / dx
    fy = (field["la1"] - lat) / dy  # la1 is north; rows increase southward
    if fx < 0 or fy < 0 or fx > nx - 1 or fy > ny - 1:
        return None
    x0, y0 = int(math.floor(fx)), int(math.floor(fy))
    x1, y1 = min(x0 + 1, nx - 1), min(y0 + 1, ny - 1)
    tx, ty = fx - x0, fy - y0
    data = field["data"]

    def at(x: int, y: int) -> float | None:
        return data[y * nx + x]

    corners = [
        (at(x0, y0), (1 - tx) * (1 - ty)),
        (at(x1, y0), tx * (1 - ty)),
        (at(x0, y1), (1 - tx) * ty),
        (at(x1, y1), tx * ty),
    ]
    total_w = sum(w for v, w in corners if v is not None)
    if total_w == 0:
        return None
    value = sum(v * w for v, w in corners if v is not None) / total_w
    return round(value, 2)
