"""Rijkswaterstaat model output from NOOS-Matroos: DCSM currents/water level and SWAN waves.

Rijkswaterstaat publishes its operational North Sea models on the public
NOOS-Matroos service (noos.matroos.rws.nl), without a key. Its "direct" API
interpolates a model to a regular lat/lon grid of our choosing and returns
NetCDF-3, which netcdf3.py reads with numpy alone.

- DCSM (43-64N, 12W-13E): water level and surface current, from the Norwegian
  coast to northern Spain, every 10 minutes to +48 h (fetched hourly).
- SWAN North Sea (48-64N, 12W-9E) and SWAN coastal strip (the Dutch coast at a
  finer grid): wave height, period and direction, hourly to +48 h.

The models run every 3 hours. Every request makes Matroos interpolate on its
side, so we take one run in six hours and fetch it in a few pieces; each piece
is split into one member file per lead time (gridded.py) for the coordinator.
"""

from __future__ import annotations

import asyncio
import functools
import warnings
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiohttp
import numpy as np

from .. import gridded, netcdf3
from .base import (
    GribDatasetInfo,
    GribFileInfo,
    GribParameter,
    GribSource,
    GribSourceError,
)

API_BASE_URL = "https://noos.matroos.rws.nl/direct"

# Lead times per request: a DCSM hour over the whole domain is ~2.5 MB.
_WINDOW_HOURS = 6
_TIMEOUT = aiohttp.ClientTimeout(total=300)
# DCSM's grid interpolation leaves a few cells along coasts and in enclosed
# basins with impossible water levels (8-12 m). Such a cell differs from its
# neighbours by metres, where real water levels change by centimetres per
# grid step; masking deviations beyond this catches them (~0.04% of cells)
# and keeps real extremes, like a spring high water in the Gulf of St Malo.
_SPIKE_LIMIT_M = 2.0


@dataclass(frozen=True)
class _Model:
    source: str  # Matroos source name
    fields: tuple[str, ...]  # Matroos field names
    bbox: tuple[float, float, float, float]  # (south, west, north, east)
    step_deg: float
    run_interval_hours: int
    last_lead: int
    despike: tuple[str, ...] = ()


_MODELS = {
    "rws_dcsm": _Model(
        source="dcsm7_harmonie_bf_f2w",
        fields=("sep", "velu", "velv"),
        bbox=(43.0, -12.0, 64.0, 13.0),
        step_deg=0.05,
        run_interval_hours=6,
        last_lead=48,
        despike=("sep",),
    ),
    "rws_swan_dcsm": _Model(
        source="swan_dcsm_harmonie",
        fields=("wave_height_hm0", "wave_period_tm10", "wave_dir_th0"),
        bbox=(48.0, -12.0, 64.0, 9.0),
        step_deg=0.05,
        run_interval_hours=6,
        last_lead=48,
    ),
    "rws_swan_kuststrook": _Model(
        source="swan_kuststrook_harmonie",
        fields=("wave_height_hm0", "wave_period_tm10", "wave_dir_th0"),
        bbox=(50.9, 1.5, 54.4, 7.7),
        step_deg=0.02,
        run_interval_hours=6,
        last_lead=48,
    ),
}

_CURRENT = GribParameter(
    key="current",
    name="Zeestroming (oppervlak)",
    unit="m/s",
    kind="vector",
    grib_filter_u={"field": "velu"},
    grib_filter_v={"field": "velv"},
    colormap="current",
    value_range=(0, 2.5),
)
_WATER_LEVEL = GribParameter(
    key="water_level",
    name="Waterstand",
    unit="m",
    grib_filter={"field": "sep"},
    colormap="water_level",
    value_range=(-2.5, 2.5),
)
# Keys as EWAM/DMI, so the comparison lines them up. th0 is the direction the
# waves come from, as elsewhere.
_SWAN_PARAMETERS = (
    GribParameter(key="wave_height", name="Golfhoogte (significant)", unit="m",
                  grib_filter={"field": "wave_height_hm0"}, colormap="wave", value_range=(0, 8)),
    GribParameter(key="wave_period", name="Golfperiode (gemiddeld)", unit="s",
                  grib_filter={"field": "wave_period_tm10"}, colormap="wave_period",
                  value_range=(0, 16)),
    GribParameter(key="wave_direction", name="Golfrichting (gemiddeld)", unit="°",
                  grib_filter={"field": "wave_dir_th0"}, colormap="direction",
                  value_range=(0, 360)),
)

KNOWN_DATASETS: tuple[GribDatasetInfo, ...] = (
    GribDatasetInfo(
        key="rws_dcsm",
        name="RWS DCSM - stroming en waterstand (Noorse kust tot Noord-Spanje)",
        version="1",
        description=(
            "Rijkswaterstaat-model DCSM via NOOS-Matroos (43-64°N, 12°W-13°O, op 0,05°): "
            "waterstand en oppervlaktestroming, uurlijks tot +48 uur. Geen sleutel."
        ),
        grid_type="regular_latlon",
        bounds=_MODELS["rws_dcsm"].bbox,
        output_frequency_hours=1,
        forecast_horizon_hours=48,
        parameters=(_CURRENT, _WATER_LEVEL),
    ),
    GribDatasetInfo(
        key="rws_swan_dcsm",
        name="RWS SWAN - golven Noordzee",
        version="1",
        description=(
            "Rijkswaterstaat-golfmodel SWAN voor de Noordzee en het Kanaal (48-64°N, "
            "12°W-9°O, op 0,05°): golfhoogte, -periode en -richting, uurlijks tot +48 uur."
        ),
        grid_type="regular_latlon",
        bounds=_MODELS["rws_swan_dcsm"].bbox,
        output_frequency_hours=1,
        forecast_horizon_hours=48,
        parameters=_SWAN_PARAMETERS,
    ),
    GribDatasetInfo(
        key="rws_swan_kuststrook",
        name="RWS SWAN - golven Nederlandse kust (fijn)",
        version="1",
        description=(
            "Rijkswaterstaat-golfmodel SWAN voor de Nederlandse kuststrook (51-54,4°N, "
            "op 0,02°): golfhoogte, -periode en -richting, uurlijks tot +48 uur."
        ),
        grid_type="regular_latlon",
        bounds=_MODELS["rws_swan_kuststrook"].bbox,
        output_frequency_hours=1,
        forecast_horizon_hours=48,
        parameters=_SWAN_PARAMETERS,
    ),
)


def _stamp(dt: datetime) -> str:
    return dt.strftime("%Y%m%d%H%M")


def _parse_stamp(text: str) -> datetime:
    return datetime.strptime(text, "%Y%m%d%H%M").replace(tzinfo=timezone.utc)


def despike(grid: np.ndarray, limit: float) -> np.ndarray:
    """Mask cells that differ from the median of their neighbours by more than ``limit``."""
    padded = np.pad(grid, 1, constant_values=np.nan)
    rows, cols = grid.shape
    neighbours = np.stack([
        padded[1 + dy:1 + dy + rows, 1 + dx:1 + dx + cols]
        for dy in (-1, 0, 1)
        for dx in (-1, 0, 1)
        if (dy, dx) != (0, 0)
    ])
    count = np.sum(np.isfinite(neighbours), axis=0)
    # An all-NaN neighbourhood gives a NaN median (and a warning); such a cell
    # is kept -- count < 2 already excludes it.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        median = np.nanmedian(neighbours, axis=0)
    with np.errstate(invalid="ignore"):
        spike = (count >= 2) & (np.abs(grid - median) > limit)
    out = grid.copy()
    out[spike] = np.nan
    return out


def split_run(
    buf: bytes, model: _Model, run_time: datetime, run_dir: Path, wanted_leads: set[int]
) -> dict[int, Path]:
    """Blocking: write one gridded member per lead time found in a Matroos NetCDF."""
    try:
        data = netcdf3.read(buf)
    except netcdf3.NetCDFError as err:
        raise GribSourceError(f"Matroos answer is not NetCDF-3: {err}") from err
    try:
        lats = data.variables["y"].data.astype(np.float64)
        lons = data.variables["x"].data.astype(np.float64)
        minutes = data.variables["time"].data.astype(np.float64)
    except KeyError as err:
        raise GribSourceError(f"Matroos NetCDF lacks {err}") from err
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    grids: dict[str, np.ndarray] = {}
    for name in model.fields:
        var = data.variables.get(name)
        if var is None:
            raise GribSourceError(f"Matroos NetCDF lacks field {name}")
        order = [var.dimensions.index(d) for d in ("time", "y", "x")]
        grids[name] = np.transpose(var.masked(), order)

    # Regular axes come ascending from Matroos; flip defensively if not.
    if lats[0] > lats[-1]:
        lats = lats[::-1]
        grids = {k: g[:, ::-1, :] for k, g in grids.items()}

    written: dict[int, Path] = {}
    for t, minute in enumerate(minutes):
        valid = epoch + timedelta(minutes=float(minute))
        lead_minutes = (valid - run_time).total_seconds() / 60
        if lead_minutes % 60:
            continue  # hourly frames only
        lead = int(lead_minutes // 60)
        if lead not in wanted_leads:
            continue
        fields = {}
        for name, grid in grids.items():
            frame = grid[t]
            if name in model.despike:
                frame = despike(frame, _SPIKE_LIMIT_M)
            fields[name] = frame
        path = run_dir / f"{_stamp(run_time)}_{lead:03d}.npz"
        gridded.write_member(
            path, fields=fields, lats=lats, lons=lons, valid_time=valid, run_time=run_time
        )
        written[lead] = path
    return written


class RwsSource(GribSource):
    """GribSource for Rijkswaterstaat's NOOS-Matroos model output."""

    key = "rws"
    name = "Rijkswaterstaat (NOOS-Matroos)"
    supports_push_notifications = False
    provides_archive = False

    def __init__(self, session: aiohttp.ClientSession, api_key: str | None = None,
                 notification_api_key: str | None = None, instance_id: str | None = None) -> None:
        self._session = session

    async def async_list_datasets(self) -> list[GribDatasetInfo]:
        return list(KNOWN_DATASETS)

    async def _get(self, url: str) -> bytes:
        try:
            async with self._session.get(url, timeout=_TIMEOUT) as resp:
                if resp.status >= 400:
                    raise GribSourceError(f"Matroos {url} returned HTTP {resp.status}")
                return await resp.read()
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise GribSourceError(f"Matroos request failed: {err}") from err

    async def async_list_files(
        self,
        dataset: GribDatasetInfo,
        *,
        max_keys: int = 20,
        order_by: str = "lastModified",
        sorting: str = "desc",
    ) -> list[GribFileInfo]:
        model = _MODELS[dataset.key]
        now = datetime.now(timezone.utc)
        url = (
            f"{API_BASE_URL}/get_anal_times.php?database=maps2d&source={model.source}"
            f"&tstart={_stamp(now - timedelta(hours=36))}&tstop={_stamp(now)}"
        )
        text = (await self._get(url)).decode("utf-8", errors="replace")
        if "ERROR" in text[:200]:
            raise GribSourceError(f"Matroos: {text.strip()[:200]}")
        runs = []
        for token in text.split():
            try:
                run = _parse_stamp(token)
            except ValueError:
                continue
            if run.hour % model.run_interval_hours == 0:
                runs.append(run)
        if not runs:
            return []
        latest = max(runs)
        return [GribFileInfo(filename=_stamp(latest), size=0, last_modified=latest.isoformat())]

    async def async_download_file(
        self, dataset: GribDatasetInfo, filename: str, destination: Path
    ) -> Path:
        raise GribSourceError("Matroos output is fetched per run; use async_download_run")

    async def async_download_run(
        self,
        dataset: GribDatasetInfo,
        run_id: str,
        run_dir: Path,
        param_keys: list[str],
        horizon_hours: float,
    ) -> list[Path]:
        model = _MODELS[dataset.key]
        run_time = _parse_stamp(run_id)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, functools.partial(run_dir.mkdir, parents=True, exist_ok=True)
        )
        last = int(min(horizon_hours, model.last_lead))
        leads = set(range(last + 1))
        south, west, north, east = model.bbox
        xn = int(round((east - west) / model.step_deg)) + 1
        yn = int(round((north - south) / model.step_deg)) + 1

        written: dict[int, Path] = {}
        # One window at a time: each is interpolated on Matroos' side.
        for start in range(0, last + 1, _WINDOW_HOURS + 1):
            end = min(start + _WINDOW_HOURS, last)
            url = (
                f"{API_BASE_URL}/get_matroos.php?source={model.source}&anal={run_id}"
                f"&color={','.join(model.fields)}&coords=WGS84"
                f"&xmin={west}&xmax={east}&ymin={south}&ymax={north}&xn={xn}&yn={yn}"
                f"&from={_stamp(run_time + timedelta(hours=start))}"
                f"&to={_stamp(run_time + timedelta(hours=end))}&dtmin=60&format=nc"
            )
            body = await self._get(url)
            if not body.startswith(b"CDF"):
                raise GribSourceError(
                    f"Matroos {model.source} {run_id}: "
                    f"{body[:200].decode('utf-8', errors='replace').strip()}"
                )
            window = set(range(start, end + 1))
            written.update(
                await loop.run_in_executor(
                    None, split_run, body, model, run_time, run_dir, window
                )
            )
        missing = leads - set(written)
        if missing:
            raise GribSourceError(
                f"Matroos {model.source} run {run_id} is missing {len(missing)} of "
                f"{len(leads)} lead times"
            )
        return [written[lead] for lead in sorted(written)]
