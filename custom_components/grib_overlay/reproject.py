"""Reproject a rotated lat/lon GRIB grid onto a regular geographic grid.

KNMI's Europe HARMONIE datasets (e.g. ``harmonie_arome_cy43_p3``) are on a
*rotated* lat/lon grid: the grid is regular in a coordinate system whose pole
has been moved to ``(south_pole_lat, south_pole_lon)`` (GRIB1 data
representation type 10). To overlay such a field on a normal geographic Leaflet
map we resample it onto a regular geographic lat/lon grid; for wind we also
rotate the u/v components from grid-relative to true east/north.

The rotation is the standard two-step pole move (rotate about the z-axis by the
pole longitude, then about the y-axis to bring the pole to the requested
latitude); the optional GRIB "angle of rotation" is a further spin about the
new polar axis, applied as a rotated-longitude offset (0 for the KNMI grids).

All functions are numpy, blocking/CPU-bound; callers run them in an executor.
"""

from __future__ import annotations

import numpy as np

# Cap the regular output grid so reprojection + PNG stay cheap on a HAOS box.
_MAX_OUT_PER_AXIS = 600
# Don't oversample far beyond the ~0.05 deg native rotated resolution.
_MIN_STEP_DEG = 0.05


def _to_cartesian(lon_rad: np.ndarray, lat_rad: np.ndarray):
    clat = np.cos(lat_rad)
    return np.cos(lon_rad) * clat, np.sin(lon_rad) * clat, np.sin(lat_rad)


def geo_to_rotated(lat, lon, sp_lat: float, sp_lon: float):
    """Geographic (deg) -> rotated (rlat, rlon) (deg). Vectorized over arrays."""
    theta = np.radians(90.0 + sp_lat)
    phi = np.radians(sp_lon)
    ct, st, cp, sp = np.cos(theta), np.sin(theta), np.cos(phi), np.sin(phi)
    x, y, z = _to_cartesian(np.radians(lon), np.radians(lat))
    # rotated_cart = Ry(theta) . Rz(phi) . geo_cart
    x2 = ct * cp * x + ct * sp * y + st * z
    y2 = -sp * x + cp * y
    z2 = -st * cp * x - st * sp * y + ct * z
    z2 = np.clip(z2, -1.0, 1.0)
    return np.degrees(np.arcsin(z2)), np.degrees(np.arctan2(y2, x2))


def rotated_to_geo(rlat, rlon, sp_lat: float, sp_lon: float):
    """Rotated (deg) -> geographic (lat, lon) (deg). Vectorized over arrays."""
    theta = np.radians(90.0 + sp_lat)
    phi = np.radians(sp_lon)
    ct, st, cp, sp = np.cos(theta), np.sin(theta), np.cos(phi), np.sin(phi)
    x, y, z = _to_cartesian(np.radians(rlon), np.radians(rlat))
    # geo_cart = Rz(-phi) . Ry(-theta) . rotated_cart  (inverse of the above)
    x2 = cp * ct * x - sp * y - cp * st * z
    y2 = sp * ct * x + cp * y - sp * st * z
    z2 = st * x + ct * z
    z2 = np.clip(z2, -1.0, 1.0)
    return np.degrees(np.arcsin(z2)), np.degrees(np.arctan2(y2, x2))


def _geo_from(rlat, rlon, rot):
    sp_lat, sp_lon, angle = rot
    return rotated_to_geo(rlat, rlon + angle, sp_lat, sp_lon)


def _rotated_from(lat, lon, rot):
    sp_lat, sp_lon, angle = rot
    rlat, rlon = geo_to_rotated(lat, lon, sp_lat, sp_lon)
    return rlat, rlon - angle


def _geo_bbox(rlats: np.ndarray, rlons: np.ndarray, rot) -> tuple[float, float, float, float]:
    """Geographic bounding box of the rotated grid, sampled along its border."""
    rlat1, rlat2 = float(rlats[0]), float(rlats[-1])
    rlon1, rlon2 = float(rlons[0]), float(rlons[-1])
    edge_rlat = np.concatenate([rlats, rlats, np.full(rlons.size, rlat1), np.full(rlons.size, rlat2)])
    edge_rlon = np.concatenate([np.full(rlats.size, rlon1), np.full(rlats.size, rlon2), rlons, rlons])
    glat, glon = _geo_from(edge_rlat, edge_rlon, rot)
    return float(glat.min()), float(glat.max()), float(glon.min()), float(glon.max())


def _regular_axes(lat_min, lat_max, lon_min, lon_max):
    span = max(lat_max - lat_min, lon_max - lon_min)
    step = max(span / (_MAX_OUT_PER_AXIS - 1), _MIN_STEP_DEG)
    ny = max(2, int(round((lat_max - lat_min) / step)) + 1)
    nx = max(2, int(round((lon_max - lon_min) / step)) + 1)
    return np.linspace(lat_min, lat_max, ny), np.linspace(lon_min, lon_max, nx)


def _bilinear(grid: np.ndarray, rlats: np.ndarray, rlons: np.ndarray, rlat_t, rlon_t) -> np.ndarray:
    """Bilinearly sample ``grid`` (rows south->north) at target rotated coords.

    NaN source corners are dropped from the weighted average (like the on-disk
    point sampler); targets outside the source grid become NaN.
    """
    nj, ni = grid.shape
    dlat = (rlats[-1] - rlats[0]) / (nj - 1)
    dlon = (rlons[-1] - rlons[0]) / (ni - 1)
    fy = (rlat_t - rlats[0]) / dlat
    fx = (rlon_t - rlons[0]) / dlon
    inside = (fx >= 0) & (fx <= ni - 1) & (fy >= 0) & (fy <= nj - 1)
    fxc = np.clip(fx, 0, ni - 1)
    fyc = np.clip(fy, 0, nj - 1)
    x0 = np.floor(fxc).astype(np.intp)
    y0 = np.floor(fyc).astype(np.intp)
    x1 = np.minimum(x0 + 1, ni - 1)
    y1 = np.minimum(y0 + 1, nj - 1)
    tx = fxc - x0
    ty = fyc - y0
    corners = (
        (grid[y0, x0], (1 - tx) * (1 - ty)),
        (grid[y0, x1], tx * (1 - ty)),
        (grid[y1, x0], (1 - tx) * ty),
        (grid[y1, x1], tx * ty),
    )
    num = np.zeros(fx.shape, dtype=np.float64)
    den = np.zeros(fx.shape, dtype=np.float64)
    for value, weight in corners:
        finite = np.isfinite(value)
        w = np.where(finite, weight, 0.0)
        num += np.where(finite, value, 0.0) * w
        den += w
    out = np.divide(num, den, out=np.full(fx.shape, np.nan), where=den > 0)
    out[~inside] = np.nan
    return out


def _bearing(lat1, lon1, lat2, lon2) -> np.ndarray:
    """Initial great-circle bearing (radians, from north, +east) from P1 to P2."""
    lat1r, lat2r = np.radians(lat1), np.radians(lat2)
    dlon = np.radians(lon2 - lon1)
    y = np.sin(dlon) * np.cos(lat2r)
    x = np.cos(lat1r) * np.sin(lat2r) - np.sin(lat1r) * np.cos(lat2r) * np.cos(dlon)
    return np.arctan2(y, x)


def regrid_scalar(grid: np.ndarray, rlats: np.ndarray, rlons: np.ndarray, rotation):
    """Resample a rotated scalar field onto a regular geographic grid.

    Returns ``(out[NY, NX] rows south->north, lats[NY] asc, lons[NX] asc)``.
    """
    lat_min, lat_max, lon_min, lon_max = _geo_bbox(rlats, rlons, rotation)
    lats_geo, lons_geo = _regular_axes(lat_min, lat_max, lon_min, lon_max)
    lon_mesh, lat_mesh = np.meshgrid(lons_geo, lats_geo)
    rlat_t, rlon_t = _rotated_from(lat_mesh, lon_mesh, rotation)
    out = _bilinear(grid, rlats, rlons, rlat_t, rlon_t)
    return out, lats_geo, lons_geo


def regrid_vector(u: np.ndarray, v: np.ndarray, rlats: np.ndarray, rlons: np.ndarray, rotation):
    """Resample rotated u/v onto a regular geographic grid AND rotate to true N/E.

    The components are grid-relative on the rotated grid; at each target point
    we find the geographic bearing of the rotated grid's north axis and rotate
    (u, v) into east/north. Returns ``(u_geo, v_geo, lats, lons)``.
    """
    lat_min, lat_max, lon_min, lon_max = _geo_bbox(rlats, rlons, rotation)
    lats_geo, lons_geo = _regular_axes(lat_min, lat_max, lon_min, lon_max)
    lon_mesh, lat_mesh = np.meshgrid(lons_geo, lats_geo)
    rlat_t, rlon_t = _rotated_from(lat_mesh, lon_mesh, rotation)
    u_s = _bilinear(u, rlats, rlons, rlat_t, rlon_t)
    v_s = _bilinear(v, rlats, rlons, rlat_t, rlon_t)

    # Angle of the rotated grid's +j (north) axis, as a geographic bearing:
    # step a little north in rotated space and see which way that points.
    eps = 0.01
    lat_n, lon_n = _geo_from(rlat_t + eps, rlon_t, rotation)
    alpha = _bearing(lat_mesh, lon_mesh, lat_n, lon_n)
    ca, sa = np.cos(alpha), np.sin(alpha)
    u_geo = u_s * ca + v_s * sa
    v_geo = -u_s * sa + v_s * ca
    return u_geo, v_geo, lats_geo, lons_geo
