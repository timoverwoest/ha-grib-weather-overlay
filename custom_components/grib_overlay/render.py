"""Render a decoded GRIB field to a colored RGBA PNG overlay + legend metadata.

Blocking by design (numpy/Pillow work) -- run via executor from the
coordinator, same as grib_decode.py.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from io import BytesIO

import numpy as np
from PIL import Image

from .grib_decode import DecodedField


@dataclass(frozen=True)
class ColorStop:
    offset: float  # 0..1 position along the scale
    color: tuple[int, int, int]


# Per-parameter-category color scales. Chosen for a reasonably intuitive read
# at a glance (blue=calm/cold/wet, red=strong/hot, green=good visibility);
# not tied to any particular standard.
COLORMAPS: dict[str, tuple[ColorStop, ...]] = {
    "wind": (
        ColorStop(0.0, (98, 181, 229)),
        ColorStop(0.2, (127, 203, 133)),
        ColorStop(0.4, (240, 222, 105)),
        ColorStop(0.6, (238, 148, 72)),
        ColorStop(0.8, (218, 68, 55)),
        ColorStop(1.0, (137, 33, 109)),
    ),
    "precipitation": (
        ColorStop(0.0, (222, 235, 247)),
        ColorStop(0.3, (107, 174, 214)),
        ColorStop(0.6, (33, 113, 181)),
        ColorStop(1.0, (8, 48, 107)),
    ),
    "temperature": (
        ColorStop(0.0, (49, 54, 149)),
        ColorStop(0.25, (69, 117, 180)),
        ColorStop(0.5, (255, 255, 191)),
        ColorStop(0.75, (252, 141, 89)),
        ColorStop(1.0, (165, 0, 38)),
    ),
    "pressure": (
        ColorStop(0.0, (33, 102, 172)),
        ColorStop(0.5, (247, 247, 247)),
        ColorStop(1.0, (178, 24, 43)),
    ),
    "visibility": (
        ColorStop(0.0, (215, 48, 39)),
        ColorStop(0.5, (254, 224, 139)),
        ColorStop(1.0, (26, 152, 80)),
    ),
    "cloud": (
        ColorStop(0.0, (135, 206, 235)),
        ColorStop(1.0, (210, 210, 210)),
    ),
    "humidity": (
        ColorStop(0.0, (230, 184, 127)),
        ColorStop(1.0, (37, 111, 168)),
    ),
    "turbo": (
        ColorStop(0.0, (48, 18, 59)),
        ColorStop(0.33, (65, 182, 196)),
        ColorStop(0.66, (233, 216, 71)),
        ColorStop(1.0, (180, 30, 30)),
    ),
    # Wave height: calm sea blue -> rising -> dangerous. Distinct from the wind
    # ramp (starts deeper/oceanic).
    "wave": (
        ColorStop(0.0, (12, 44, 92)),
        ColorStop(0.2, (32, 120, 180)),
        ColorStop(0.4, (64, 190, 190)),
        ColorStop(0.6, (240, 214, 106)),
        ColorStop(0.8, (232, 120, 60)),
        ColorStop(1.0, (150, 30, 90)),
    ),
    # Wave period: short (choppy) -> long (swell).
    "wave_period": (
        ColorStop(0.0, (69, 117, 180)),
        ColorStop(0.4, (145, 191, 163)),
        ColorStop(0.7, (254, 224, 139)),
        ColorStop(1.0, (215, 48, 39)),
    ),
    # Ocean current speed: calm -> strong tidal stream.
    "current": (
        ColorStop(0.0, (20, 60, 110)),
        ColorStop(0.25, (30, 150, 170)),
        ColorStop(0.5, (110, 200, 120)),
        ColorStop(0.7, (240, 214, 106)),
        ColorStop(0.85, (232, 120, 60)),
        ColorStop(1.0, (150, 30, 90)),
    ),
    # Direction (0-360 deg): cyclic, so 0 and 360 share a colour.
    "direction": (
        ColorStop(0.0, (215, 48, 39)),
        ColorStop(0.25, (120, 190, 90)),
        ColorStop(0.5, (60, 180, 200)),
        ColorStop(0.75, (70, 90, 200)),
        ColorStop(1.0, (215, 48, 39)),
    ),
}


@dataclass(frozen=True)
class RenderedFrame:
    png_bytes: bytes
    bounds: tuple[float, float, float, float]  # (south, west, north, east)
    width: int
    height: int


@dataclass(frozen=True)
class Legend:
    unit: str
    min_value: float
    max_value: float
    stops: tuple[dict, ...]  # [{"offset": 0..1, "color": "#rrggbb"}, ...]


def _colormap_lut(name: str, size: int = 256) -> np.ndarray:
    stops = COLORMAPS.get(name, COLORMAPS["turbo"])
    positions = [s.offset for s in stops]
    colors = np.array([s.color for s in stops], dtype=np.float64)
    xs = np.linspace(0, 1, size)
    lut = np.empty((size, 3), dtype=np.uint8)
    for channel in range(3):
        lut[:, channel] = np.interp(xs, positions, colors[:, channel]).astype(np.uint8)
    return lut


def _legend_stops(colormap: str) -> tuple[dict, ...]:
    return tuple(
        {"offset": s.offset, "color": "#%02x%02x%02x" % s.color}
        for s in COLORMAPS.get(colormap, COLORMAPS["turbo"])
    )


def _mercator_north_first_rows(south: float, north: float, nrows: int) -> np.ndarray:
    """Source-row indices remapping a south-first, latitude-linear grid to an
    image whose rows run north (top) -> south (bottom) *uniformly in Web
    Mercator y*.

    Leaflet's imageOverlay stretches the PNG linearly in Web-Mercator pixel
    space between the bounds, but our grid rows are linear in latitude. Over a
    wide latitude span that mismatch visibly shifts the overlay (lower-latitude
    data creeps north). Pre-warping the rows here makes the PNG line up.
    """
    if nrows < 2 or north <= south:
        return np.arange(nrows - 1, -1, -1)  # just flip to north-first
    clamp = lambda d: max(min(d, 85.0), -85.0)
    merc = lambda d: math.log(math.tan(math.pi / 4 + math.radians(clamp(d)) / 2))
    ys = np.linspace(merc(north), merc(south), nrows)  # top=north -> bottom=south
    lats = np.degrees(2.0 * np.arctan(np.exp(ys)) - math.pi / 2)
    src = np.rint((lats - south) / (north - south) * (nrows - 1)).astype(int)
    return np.clip(src, 0, nrows - 1)


def render_field(
    field: DecodedField,
    *,
    colormap: str,
    value_range: tuple[float, float] | None,
    opacity: int = 200,
) -> tuple[RenderedFrame, Legend]:
    """Render one DecodedField to an RGBA PNG + Leaflet imageOverlay bounds + legend."""
    south, north = float(field.lats.min()), float(field.lats.max())
    west, east = float(field.lons.min()), float(field.lons.max())

    # Warp latitude rows to Web Mercator and put north on top in one gather, so
    # the PNG aligns with Leaflet's (Mercator) imageOverlay placement.
    data = field.data[_mercator_north_first_rows(south, north, field.data.shape[0])]

    if value_range is None:
        finite = data[np.isfinite(data)]
        vmin, vmax = (float(finite.min()), float(finite.max())) if finite.size else (0.0, 1.0)
    else:
        vmin, vmax = value_range
    if vmax <= vmin:
        vmax = vmin + 1.0

    normalized = np.clip((data - vmin) / (vmax - vmin), 0.0, 1.0)
    lut = _colormap_lut(colormap)
    idx = np.nan_to_num(normalized, nan=0.0)
    idx = (idx * (len(lut) - 1)).astype(np.uint8)

    rgb = lut[idx]
    alpha = np.where(np.isnan(data), 0, opacity).astype(np.uint8)
    rgba = np.dstack([rgb, alpha])  # already north-first from the row map above

    image = Image.fromarray(rgba, mode="RGBA")
    buf = BytesIO()
    image.save(buf, format="PNG", optimize=True)

    frame = RenderedFrame(
        png_bytes=buf.getvalue(),
        bounds=(south, west, north, east),
        width=image.width,
        height=image.height,
    )
    legend = Legend(
        unit=field.unit,
        min_value=vmin,
        max_value=vmax,
        stops=_legend_stops(colormap),
    )
    return frame, legend
