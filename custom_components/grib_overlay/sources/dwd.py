"""DWD Open Data GRIB source: the EWAM wave model and the ICON-D2 weather model.

Unlike KNMI (one ~GB .tar per run), DWD's Open Data server publishes one small
GRIB2 file per parameter per lead time under an Apache-style directory index,
freely and without an API key. This source lists the latest run and downloads
the individual ``.grib2.bz2`` files (bunzip2'd in-process) for the coordinator's
per-file path (``provides_archive = False``).

Decoding is handled by the in-tree pure-Python GRIB2 decoder (grib2.py): EWAM
and ICON-D2's regular lat/lon files use simple grid-point packing, so no
eccodes/libaec/openjpeg binary is needed. (ICON-EU, by contrast, is CCSDS
packed -- which is why it is not offered here.)
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
_ICON_D2_BASE = "https://opendata.dwd.de/weather/nwp/icon-d2/grib"

# Parallel downloads per run. ICON-D2 is a few hundred ~1 MB files; a handful at
# a time keeps a run to a minute or two without hammering the server.
_DOWNLOAD_CONCURRENCY = 4

_WAVE = {"discipline": 10, "parameterCategory": 0}

# EWAM wave parameters (GRIB2 discipline 10, category 0). ``key`` is our stable
# id; the DWD server sub-directory it lives in is mapped in _EWAM_DIR below.
# Parameter numbers verified against real files: 3 = significant wave height,
# 14 = mean wave direction, 15 = mean wave period; swell 8/7/9 (+36 peak
# period), wind sea 5/4/6 (+35 peak period).
#
# Keys come in families sharing a prefix (``swell_height`` / ``swell_period`` /
# ``swell_direction``): that is how the card and the point API know which
# direction belongs to which height (see base.direction_key_for).
_EWAM_PARAMETERS: tuple[GribParameter, ...] = (
    GribParameter(
        key="wave_height",
        name="Golfhoogte (significant)",
        unit="m",
        grib_filter={**_WAVE, "parameterNumber": 3},
        colormap="wave",
        value_range=(0, 8),
    ),
    GribParameter(
        key="wave_period",
        name="Golfperiode (gemiddeld)",
        unit="s",
        grib_filter={**_WAVE, "parameterNumber": 15},
        colormap="wave_period",
        value_range=(0, 16),
    ),
    GribParameter(
        key="wave_direction",
        name="Golfrichting (gemiddeld)",
        unit="°",
        grib_filter={**_WAVE, "parameterNumber": 14},
        colormap="direction",
        value_range=(0, 360),
    ),
    GribParameter(
        key="swell_height",
        name="Deining: hoogte",
        unit="m",
        grib_filter={**_WAVE, "parameterNumber": 8},
        colormap="wave",
        value_range=(0, 8),
    ),
    GribParameter(
        key="swell_period",
        name="Deining: periode (gemiddeld)",
        unit="s",
        grib_filter={**_WAVE, "parameterNumber": 9},
        colormap="wave_period",
        value_range=(0, 16),
    ),
    GribParameter(
        key="swell_peak_period",
        name="Deining: piekperiode",
        unit="s",
        grib_filter={**_WAVE, "parameterNumber": 36},
        colormap="wave_period",
        value_range=(0, 20),
    ),
    GribParameter(
        key="swell_direction",
        name="Deining: richting",
        unit="°",
        grib_filter={**_WAVE, "parameterNumber": 7},
        colormap="direction",
        value_range=(0, 360),
    ),
    GribParameter(
        key="wind_wave_height",
        name="Windgolven: hoogte",
        unit="m",
        grib_filter={**_WAVE, "parameterNumber": 5},
        colormap="wave",
        value_range=(0, 8),
    ),
    GribParameter(
        key="wind_wave_period",
        name="Windgolven: periode (gemiddeld)",
        unit="s",
        grib_filter={**_WAVE, "parameterNumber": 6},
        colormap="wave_period",
        value_range=(0, 16),
    ),
    GribParameter(
        key="wind_wave_peak_period",
        name="Windgolven: piekperiode",
        unit="s",
        grib_filter={**_WAVE, "parameterNumber": 35},
        colormap="wave_period",
        value_range=(0, 20),
    ),
    GribParameter(
        key="wind_wave_direction",
        name="Windgolven: richting",
        unit="°",
        grib_filter={**_WAVE, "parameterNumber": 4},
        colormap="direction",
        value_range=(0, 360),
    ),
)

# EWAM runs at 00 and 12 UTC to +78 h. DWD publishes a run over ~35 minutes,
# lead time by lead time, starting ~3 h 15 min after the run time.
_EWAM_RUN_HOURS = ("00", "12")
_EWAM_LAST_STEP = 78

# key -> DWD Open Data sub-directory name.
_EWAM_DIR = {
    "wave_height": "swh",
    "wave_period": "tm10",
    "wave_direction": "mwd",
    "swell_height": "shts",
    "swell_period": "mpts",
    "swell_peak_period": "ppts",
    "swell_direction": "mdts",
    "wind_wave_height": "shww",
    "wind_wave_period": "mpww",
    "wind_wave_peak_period": "ppww",
    "wind_wave_direction": "mdww",
}


def _met(category: int, number: int) -> dict:
    """GRIB2 filter for a meteorological (discipline 0) field."""
    return {"discipline": 0, "parameterCategory": category, "parameterNumber": number}


# ICON-D2 near-surface parameters. The keys deliberately match KNMI HARMONIE's,
# so the comparison views line the two models up parameter by parameter.
# Codes verified against real regular-lat-lon files.
_ICON_D2_PARAMETERS: tuple[GribParameter, ...] = (
    GribParameter(
        key="wind_10m",
        name="Wind (10m)",
        unit="m/s",
        kind="vector",
        grib_filter_u=_met(2, 2),
        grib_filter_v=_met(2, 3),
        colormap="wind",
        value_range=(0, 25),
    ),
    # ICON publishes the gust as a speed (the maximum over the past hour), not
    # as u/v like HARMONIE -- so a scalar, without its own direction.
    GribParameter(
        key="wind_gust_10m",
        name="Windstoten (10m)",
        unit="m/s",
        grib_filter=_met(2, 22),
        colormap="wind",
        value_range=(0, 35),
    ),
    GribParameter(
        key="temperature_2m",
        name="Temperatuur (2m)",
        unit="°C",
        grib_filter=_met(0, 0),
        offset=-273.15,  # Kelvin -> Celsius
        colormap="temperature",
        value_range=(-10, 35),
    ),
    GribParameter(
        key="dewpoint_2m",
        name="Dauwpunt (2m)",
        unit="°C",
        grib_filter=_met(0, 6),
        offset=-273.15,
        colormap="temperature",
        value_range=(-15, 25),
    ),
    GribParameter(
        key="humidity_2m",
        name="Relatieve luchtvochtigheid (2m)",
        unit="%",
        grib_filter=_met(1, 1),  # already a percentage (KNMI's is a fraction)
        colormap="humidity",
        value_range=(0, 100),
    ),
    # tot_prec is the total since the run started; the coordinator turns it into
    # the amount per hour, which is what KNMI delivers and the card expects.
    GribParameter(
        key="precipitation",
        name="Neerslag",
        unit="mm",
        grib_filter=_met(1, 52),
        colormap="precipitation",
        value_range=(0, 20),
        accumulated=True,
    ),
    GribParameter(
        key="pressure_msl",
        name="Luchtdruk (zeeniveau)",
        unit="hPa",
        grib_filter=_met(3, 1),
        scale=0.01,  # Pa -> hPa
        colormap="pressure",
        value_range=(980, 1040),
    ),
    GribParameter(
        key="visibility",
        name="Zicht",
        unit="km",
        grib_filter=_met(19, 0),
        scale=0.001,  # m -> km
        colormap="visibility",
        value_range=(0, 50),
    ),
    GribParameter(
        key="cloud_cover",
        name="Bewolking",
        unit="%",
        grib_filter=_met(6, 1),
        colormap="cloud",
        value_range=(0, 100),
    ),
    GribParameter(
        key="cape",
        name="CAPE (onweersenergie)",
        unit="J/kg",
        grib_filter=_met(7, 6),
        colormap="cape",
        value_range=(0, 2000),
    ),
)

# key -> DWD Open Data sub-directories. Wind needs two files (u and v), which
# the download joins into one GRIB file so it decodes like HARMONIE's.
_ICON_D2_DIRS: dict[str, tuple[str, ...]] = {
    "wind_10m": ("u_10m", "v_10m"),
    "wind_gust_10m": ("vmax_10m",),
    "temperature_2m": ("t_2m",),
    "dewpoint_2m": ("td_2m",),
    "humidity_2m": ("relhum_2m",),
    "precipitation": ("tot_prec",),
    "pressure_msl": ("pmsl",),
    "visibility": ("vis",),
    "cloud_cover": ("clct",),
    "cape": ("cape_ml",),
}

# ICON-D2 runs every three hours, each to +48 h. The server keeps one run per
# hour-of-day directory and overwrites it step by step while the next run is
# published (~40-80 minutes after the run time), so the same directory briefly
# holds two runs.
_ICON_D2_RUN_HOURS = ("00", "03", "06", "09", "12", "15", "18", "21")
_ICON_D2_LAST_STEP = 48
_ICON_D2_PROBE_DIR = "t_2m"

KNOWN_DATASETS: tuple[GribDatasetInfo, ...] = (
    GribDatasetInfo(
        key="ewam",
        name="DWD EWAM - Europese golven (Noordzee, Atlantische Oceaan, Middellandse Zee)",
        version="1.0",
        description=(
            "DWD EWAM golfmodel: significante golfhoogte, deining en windgolven "
            "(hoogte, richting, periode) over de Europese zeeën (regulier lat-lon "
            "grid, ~0,05°). GRIB2, open data, geen sleutel nodig."
        ),
        grid_type="regular_latlon",
        bounds=(30.0, -10.5, 66.0, 42.0),
        output_frequency_hours=1,
        forecast_horizon_hours=78,
        parameters=_EWAM_PARAMETERS,
    ),
    GribDatasetInfo(
        key="icon_d2",
        name="DWD ICON-D2 - weermodel 2,2 km (Duitsland, Benelux, zuidelijke Noordzee)",
        version="1.0",
        description=(
            "DWD ICON-D2: uurlijkse voorspelling op ~2,2 km (regulier lat-lon grid, "
            "0,02°) voor Midden-Europa inclusief heel Nederland en de zuidelijke "
            "Noordzee. Elke 3 uur een nieuwe run, tot +48 uur. GRIB2, open data, "
            "geen sleutel nodig."
        ),
        grid_type="regular_latlon",
        bounds=(43.18, -3.94, 58.08, 20.34),
        output_frequency_hours=1,
        forecast_horizon_hours=_ICON_D2_LAST_STEP,
        parameters=_ICON_D2_PARAMETERS,
    ),
)

# EWAM_SWH_2026072200_003.grib2.bz2  ->  (filename, run YYYYMMDDHH, step hours)
_FILE_RE = re.compile(r'href="(EWAM_[A-Z0-9]+_(\d{10})_(\d{3})\.grib2\.bz2)"')


def _icon_d2_file_re(dwd_dir: str) -> re.Pattern:
    # icon-d2_germany_regular-lat-lon_single-level_2026091600_003_2d_t_2m.grib2.bz2
    return re.compile(
        r'href="(icon-d2_germany_regular-lat-lon_single-level_(\d{10})_(\d{3})_2d_'
        + re.escape(dwd_dir)
        + r'\.grib2\.bz2)"'
    )


def _require_steps(run: str, dwd_dir: str, steps: dict, wanted: list[int]) -> None:
    """Refuse a run caught mid-publication before anything is downloaded.

    The coordinator processes a run once, so gaps would stay; failing here makes
    it retry at the next poll instead.
    """
    missing = [s for s in wanted if s not in steps]
    if missing:
        raise GribSourceError(
            f"{run} is not complete yet: {dwd_dir} lacks {len(missing)} of "
            f"{len(wanted)} lead times"
        )


class DwdSource(GribSource):
    """GribSource for DWD Open Data (opendata.dwd.de): EWAM waves and ICON-D2."""

    key = "dwd"
    name = "DWD Open Data"
    supports_push_notifications = False
    provides_archive = False

    def __init__(self, session: aiohttp.ClientSession, api_key: str | None = None,
                 notification_api_key: str | None = None, instance_id: str | None = None) -> None:
        self._session = session  # api_key/instance_id unused: DWD Open Data needs no key or push

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

    # -- EWAM -------------------------------------------------------------------

    async def _runs_for(self, dwd_dir: str) -> dict[str, list[tuple[int, str, str]]]:
        """Map run id -> [(step_hours, run_hour, filename)] for one parameter dir."""
        runs: dict[str, list[tuple[int, str, str]]] = {}
        for hh in _EWAM_RUN_HOURS:
            html = await self._list_dir(f"{_BASE}/{hh}/{dwd_dir}/")
            for filename, run, step in _FILE_RE.findall(html):
                runs.setdefault(run, []).append((int(step), hh, filename))
        return runs

    async def _download_ewam_run(
        self, run_id: str, run_dir: Path, param_keys: list[str], horizon_hours: float, loop
    ) -> list[Path]:
        wanted_steps = [s for s in range(_EWAM_LAST_STEP + 1) if s <= horizon_hours]
        keys = [k for k in param_keys if k in _EWAM_DIR]
        listings = await asyncio.gather(*(self._runs_for(_EWAM_DIR[k]) for k in keys))
        available: dict[str, dict[int, str]] = {}
        for key, runs in zip(keys, listings):
            steps = {step: f"{_BASE}/{hh}/{_EWAM_DIR[key]}/{name}" for step, hh, name in runs.get(run_id, [])}
            _require_steps(f"EWAM run {run_id}", _EWAM_DIR[key], steps, wanted_steps)
            available[key] = steps
        return await self._fetch_all(
            [([available[k][s]], run_dir / f"{k}_{s:03d}.grib2") for k in keys for s in wanted_steps],
            loop,
        )

    # -- ICON-D2 ----------------------------------------------------------------

    async def _icon_d2_steps(self, hh: str, dwd_dir: str) -> dict[str, dict[int, str]]:
        """Map run id -> {step: filename} for one run-hour directory."""
        html = await self._list_dir(f"{_ICON_D2_BASE}/{hh}/{dwd_dir}/")
        runs: dict[str, dict[int, str]] = {}
        for filename, run, step in _icon_d2_file_re(dwd_dir).findall(html):
            runs.setdefault(run, {})[int(step)] = filename
        return runs

    async def _icon_d2_latest_complete_run(self) -> str | None:
        """The newest run whose last lead time is on the server.

        A run that is still being published must not be picked up: the
        coordinator processes a run once, so a half-published run would stay
        half-empty until the next one.
        """
        listings = await asyncio.gather(
            *(self._icon_d2_steps(hh, _ICON_D2_PROBE_DIR) for hh in _ICON_D2_RUN_HOURS)
        )
        complete = [
            run
            for runs in listings
            for run, steps in runs.items()
            if _ICON_D2_LAST_STEP in steps
        ]
        return max(complete) if complete else None

    async def _download_icon_d2_run(
        self, run_id: str, run_dir: Path, param_keys: list[str], horizon_hours: float, loop
    ) -> list[Path]:
        hh = run_id[8:10]
        wanted_steps = [s for s in range(_ICON_D2_LAST_STEP + 1) if s <= horizon_hours]
        keys = [k for k in param_keys if k in _ICON_D2_DIRS]
        dirs = sorted({d for k in keys for d in _ICON_D2_DIRS[k]})
        # List everything first: only start downloading once every file we need
        # is there, so a run caught mid-publication fails cleanly (and is retried
        # at the next poll) instead of leaving gaps.
        listings = await asyncio.gather(*(self._icon_d2_steps(hh, d) for d in dirs))
        available = {d: runs.get(run_id, {}) for d, runs in zip(dirs, listings)}
        for dwd_dir, steps in available.items():
            _require_steps(f"ICON-D2 run {run_id}", dwd_dir, steps, wanted_steps)
        return await self._fetch_all(
            [
                (
                    [f"{_ICON_D2_BASE}/{hh}/{d}/{available[d][s]}" for d in _ICON_D2_DIRS[k]],
                    run_dir / f"{k}_{s:03d}.grib2",
                )
                for k in keys
                for s in wanted_steps
            ],
            loop,
        )

    async def _fetch_all(self, jobs: list[tuple[list[str], Path]], loop) -> list[Path]:
        """Download ``(urls, dest)`` jobs a few at a time; return the paths in job order.

        Job order is per parameter in ascending lead time: the coordinator relies
        on that to turn accumulated totals into hourly amounts.
        """
        semaphore = asyncio.Semaphore(_DOWNLOAD_CONCURRENCY)

        async def fetch(urls: list[str], dest: Path) -> Path:
            async with semaphore:
                await self._download_bunzip(urls, dest, loop)
            return dest

        # Let every download finish (or fail) before reporting, so nothing is
        # still writing into run_dir when the caller cleans it up after an error.
        results = await asyncio.gather(
            *(fetch(urls, dest) for urls, dest in jobs), return_exceptions=True
        )
        for result in results:
            if isinstance(result, BaseException):
                raise result
        return list(results)

    # -- GribSource ---------------------------------------------------------------

    async def async_list_files(
        self,
        dataset: GribDatasetInfo,
        *,
        max_keys: int = 20,
        order_by: str = "lastModified",
        sorting: str = "desc",
    ) -> list[GribFileInfo]:
        if dataset.key == "icon_d2":
            latest = await self._icon_d2_latest_complete_run()
        else:
            # swh is always present; probe with it. Only a run whose last lead time
            # is out counts: DWD publishes over ~35 minutes, and a run picked up
            # halfway would stay that way until the next one, 12 hours later.
            runs = await self._runs_for("swh")
            complete = [
                run
                for run, entries in runs.items()
                if any(step == _EWAM_LAST_STEP for step, _, _ in entries)
            ]
            latest = max(complete) if complete else None
        if latest is None:
            return []
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
        if dataset.key == "icon_d2":
            return await self._download_icon_d2_run(
                run_id, run_dir, param_keys, horizon_hours, loop
            )
        return await self._download_ewam_run(run_id, run_dir, param_keys, horizon_hours, loop)

    async def _download_bunzip(self, urls: list[str], dest: Path, loop) -> None:
        """Download one or more .bz2 GRIB files and write them, joined, to ``dest``."""
        compressed: list[bytes] = []
        for url in urls:
            try:
                async with self._session.get(url) as resp:
                    if resp.status >= 400:
                        raise GribSourceError(f"DWD download {url} returned HTTP {resp.status}")
                    compressed.append(await resp.read())
            except aiohttp.ClientError as err:
                raise GribSourceError(f"DWD download failed: {err}") from err
        await loop.run_in_executor(
            None, lambda: dest.write_bytes(b"".join(bz2.decompress(c) for c in compressed))
        )
