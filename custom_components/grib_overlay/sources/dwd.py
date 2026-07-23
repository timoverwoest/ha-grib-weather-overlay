"""DWD Open Data GRIB source: the EWAM European wave model.

Unlike KNMI (one ~GB .tar per run), DWD's Open Data server publishes one small
GRIB2 file per parameter per lead time under an Apache-style directory index,
freely and without an API key. This source lists the latest run and downloads
the individual ``.grib2.bz2`` files (bunzip2'd in-process) for the coordinator's
per-file path (``provides_archive = False``).

Decoding is handled by the in-tree pure-Python GRIB2 decoder (grib2.py): EWAM
uses simple grid-point packing, so no eccodes/libaec/openjpeg binary is needed.
"""

from __future__ import annotations

import asyncio
import bz2
import functools
import re
from datetime import datetime, timezone
from pathlib import Path

import aiohttp

from .base import (
    GribDatasetInfo,
    GribFileInfo,
    GribParameter,
    GribSource,
    GribSourceError,
)

_BASE = "https://opendata.dwd.de/weather/maritime/wave_models/ewam/grib"

# EWAM wave parameters (GRIB2 discipline 10, category 0). ``key`` is our stable
# id; the DWD server sub-directory it lives in is mapped in _EWAM_DIR below.
# Parameter numbers verified against real files: 3 = significant wave height,
# 14 = mean wave direction, 15 = mean wave period.
_EWAM_PARAMETERS: tuple[GribParameter, ...] = (
    GribParameter(
        key="wave_height",
        name="Golfhoogte (significant)",
        unit="m",
        grib_filter={"discipline": 10, "parameterCategory": 0, "parameterNumber": 3},
        colormap="wave",
        value_range=(0, 8),
    ),
    GribParameter(
        key="wave_period",
        name="Golfperiode (gemiddeld)",
        unit="s",
        grib_filter={"discipline": 10, "parameterCategory": 0, "parameterNumber": 15},
        colormap="wave_period",
        value_range=(0, 16),
    ),
    GribParameter(
        key="wave_direction",
        name="Golfrichting (gemiddeld)",
        unit="°",
        grib_filter={"discipline": 10, "parameterCategory": 0, "parameterNumber": 14},
        colormap="direction",
        value_range=(0, 360),
    ),
)

# key -> DWD Open Data sub-directory name.
_EWAM_DIR = {"wave_height": "swh", "wave_period": "tm10", "wave_direction": "mwd"}

KNOWN_DATASETS: tuple[GribDatasetInfo, ...] = (
    GribDatasetInfo(
        key="ewam",
        name="DWD EWAM - Europese golven (Noordzee, Atlantische Oceaan, Middellandse Zee)",
        version="1.0",
        description=(
            "DWD EWAM golfmodel: significante golfhoogte, gemiddelde golfrichting "
            "en -periode over de Europese zeeën (regulier lat-lon grid, ~0,05°). "
            "GRIB2, open data, geen sleutel nodig."
        ),
        grid_type="regular_latlon",
        bounds=(30.0, -10.5, 66.0, 42.0),
        output_frequency_hours=1,
        forecast_horizon_hours=78,
        parameters=_EWAM_PARAMETERS,
    ),
)

# EWAM_SWH_2026072200_003.grib2.bz2  ->  (filename, run YYYYMMDDHH, step hours)
_FILE_RE = re.compile(r'href="(EWAM_[A-Z0-9]+_(\d{10})_(\d{3})\.grib2\.bz2)"')


class DwdSource(GribSource):
    """GribSource for DWD Open Data (opendata.dwd.de) -- the EWAM wave model."""

    key = "dwd"
    name = "DWD Open Data (golven)"
    supports_push_notifications = False
    provides_archive = False

    def __init__(self, session: aiohttp.ClientSession, api_key: str | None = None,
                 notification_api_key: str | None = None) -> None:
        self._session = session  # api_key is unused: DWD Open Data needs no key

    async def async_list_datasets(self) -> list[GribDatasetInfo]:
        return list(KNOWN_DATASETS)

    async def _list_dir(self, url: str) -> str:
        try:
            async with self._session.get(url) as resp:
                if resp.status >= 400:
                    raise GribSourceError(f"DWD listing {url} returned HTTP {resp.status}")
                return await resp.text()
        except aiohttp.ClientError as err:
            raise GribSourceError(f"DWD listing failed: {err}") from err

    async def _runs_for(self, dwd_dir: str) -> dict[str, list[tuple[int, str, str]]]:
        """Map run id -> [(step_hours, run_hour, filename)] for one parameter dir."""
        runs: dict[str, list[tuple[int, str, str]]] = {}
        for hh in ("00", "12"):
            html = await self._list_dir(f"{_BASE}/{hh}/{dwd_dir}/")
            for filename, run, step in _FILE_RE.findall(html):
                runs.setdefault(run, []).append((int(step), hh, filename))
        return runs

    async def async_list_files(
        self,
        dataset: GribDatasetInfo,
        *,
        max_keys: int = 20,
        order_by: str = "lastModified",
        sorting: str = "desc",
    ) -> list[GribFileInfo]:
        runs = await self._runs_for("swh")  # swh is always present; probe with it
        if not runs:
            return []
        latest = max(runs)
        run_dt = datetime.strptime(latest, "%Y%m%d%H").replace(tzinfo=timezone.utc)
        return [GribFileInfo(filename=latest, size=0, last_modified=run_dt.isoformat())]

    async def async_download_file(
        self, dataset: GribDatasetInfo, filename: str, destination: Path
    ) -> Path:
        raise GribSourceError("DWD delivers individual files; use async_download_run")

    async def async_download_run(
        self,
        dataset: GribDatasetInfo,
        run_id: str,
        run_dir: Path,
        param_keys: list[str],
        horizon_hours: float,
    ) -> list[Path]:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, functools.partial(run_dir.mkdir, parents=True, exist_ok=True)
        )
        paths: list[Path] = []
        for key in param_keys:
            dwd_dir = _EWAM_DIR.get(key)
            if dwd_dir is None:
                continue
            entries = (await self._runs_for(dwd_dir)).get(run_id, [])
            for step, hh, filename in sorted(entries):
                if step > horizon_hours:
                    continue
                dest = run_dir / f"{key}_{step:03d}.grib2"
                await self._download_bunzip(f"{_BASE}/{hh}/{dwd_dir}/{filename}", dest, loop)
                paths.append(dest)
        return paths

    async def _download_bunzip(self, url: str, dest: Path, loop) -> None:
        try:
            async with self._session.get(url) as resp:
                if resp.status >= 400:
                    raise GribSourceError(f"DWD download {url} returned HTTP {resp.status}")
                compressed = await resp.read()
        except aiohttp.ClientError as err:
            raise GribSourceError(f"DWD download failed: {err}") from err
        await loop.run_in_executor(None, lambda: dest.write_bytes(bz2.decompress(compressed)))
