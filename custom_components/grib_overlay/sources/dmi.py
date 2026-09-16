"""DMI Open Data GRIB source: WAM waves and the DKSS storm-surge model.

The Danish Meteorological Institute serves its forecast files without a key
through a STAC-style API (opendataapi.dmi.dk): one GRIB1 file per lead time,
listed per model run. For a route from Oslo to the Bay of Biscay these cover
what the other sources don't:

- WAM North Sea & Baltic (~5 km, 47-66N) and WAM North Atlantic (0.25 deg,
  30-78N): waves with swell and wind sea, every 6 hours to +132 h.
- DKSS North Sea & Baltic (~5 km, 48.5-65.9N, from 4.1W): currents, water level
  and water temperature, every 6 hours to +120 h.

All of it is simple-packed GRIB1 on a regular lat/lon grid, so grib1.py reads it
as it does KNMI's.
"""

from __future__ import annotations

import asyncio
import functools
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiohttp

from .base import (
    GribDatasetInfo,
    GribFileInfo,
    GribParameter,
    GribSource,
    GribSourceError,
)

API_BASE_URL = "https://opendataapi.dmi.dk/v1/forecastdata/collections"

# DMI runs both models every 6 hours and publishes a run over a couple of hours.
_RUN_INTERVAL_HOURS = 6
# How far back to look for the newest complete run.
_RUN_LOOKBACK = 5
_DOWNLOAD_CONCURRENCY = 4

_WAVE_LEVEL = {"indicatorOfTypeOfLevel": 102, "level": 0}  # ECMWF wave table 140


def _wave(number: int) -> dict:
    return {"indicatorOfParameter": number, **_WAVE_LEVEL}


# ECMWF table 140 codes, verified against real files: 229 swh, 230 mwd,
# 231 pp1d, 232 mwp; wind sea 234/235/236; total swell 237/238/239. Keys match
# EWAM's, so the comparison lines the models up (and each direction pairs with
# its family, see base.direction_key_for).
_WAM_PARAMETERS: tuple[GribParameter, ...] = (
    GribParameter(key="wave_height", name="Golfhoogte (significant)", unit="m",
                  grib_filter=_wave(229), colormap="wave", value_range=(0, 8)),
    GribParameter(key="wave_period", name="Golfperiode (gemiddeld)", unit="s",
                  grib_filter=_wave(232), colormap="wave_period", value_range=(0, 16)),
    GribParameter(key="wave_peak_period", name="Golf: piekperiode", unit="s",
                  grib_filter=_wave(231), colormap="wave_period", value_range=(0, 20)),
    GribParameter(key="wave_direction", name="Golfrichting (gemiddeld)", unit="°",
                  grib_filter=_wave(230), colormap="direction", value_range=(0, 360)),
    GribParameter(key="swell_height", name="Deining: hoogte", unit="m",
                  grib_filter=_wave(237), colormap="wave", value_range=(0, 8)),
    GribParameter(key="swell_period", name="Deining: periode (gemiddeld)", unit="s",
                  grib_filter=_wave(239), colormap="wave_period", value_range=(0, 16)),
    GribParameter(key="swell_direction", name="Deining: richting", unit="°",
                  grib_filter=_wave(238), colormap="direction", value_range=(0, 360)),
    GribParameter(key="wind_wave_height", name="Windgolven: hoogte", unit="m",
                  grib_filter=_wave(234), colormap="wave", value_range=(0, 8)),
    GribParameter(key="wind_wave_period", name="Windgolven: periode (gemiddeld)", unit="s",
                  grib_filter=_wave(236), colormap="wave_period", value_range=(0, 16)),
    GribParameter(key="wind_wave_direction", name="Windgolven: richting", unit="°",
                  grib_filter=_wave(235), colormap="direction", value_range=(0, 360)),
)

_SURFACE = {"indicatorOfTypeOfLevel": 1, "level": 0}

# DMI's local table (centre 94, table 128): 82 sea level, 49/50 current u/v,
# 80 water temperature. Each file also carries salinity, ice and currents at
# many depths, after these surface fields.
_DKSS_PARAMETERS: tuple[GribParameter, ...] = (
    GribParameter(
        key="current",
        name="Zeestroming (oppervlak)",
        unit="m/s",
        kind="vector",
        grib_filter_u={"indicatorOfParameter": 49, **_SURFACE},
        grib_filter_v={"indicatorOfParameter": 50, **_SURFACE},
        colormap="current",
        value_range=(0, 2.5),
    ),
    GribParameter(
        key="water_level",
        name="Waterstand",
        unit="m",
        grib_filter={"indicatorOfParameter": 82, **_SURFACE},
        colormap="water_level",
        value_range=(-2.5, 2.5),
    ),
    GribParameter(
        key="water_temperature",
        name="Watertemperatuur",
        unit="°C",
        grib_filter={"indicatorOfParameter": 80, **_SURFACE},
        colormap="temperature",
        value_range=(0, 25),
    ),
)

KNOWN_DATASETS: tuple[GribDatasetInfo, ...] = (
    GribDatasetInfo(
        key="dmi_wam_nsb",
        name="DMI WAM - golven Noordzee en Oostzee (~5 km)",
        version="1",
        description=(
            "DMI golfmodel WAM voor Noordzee, Kanaal en Oostzee (47-66°N, 13°W-30°O, "
            "~5 km): golfhoogte, deining en windgolven. Elke 6 uur, tot +132 uur. "
            "Open data, geen sleutel."
        ),
        grid_type="regular_latlon",
        bounds=(47.0, -13.0, 66.0, 30.0),
        output_frequency_hours=1,
        forecast_horizon_hours=132,
        parameters=_WAM_PARAMETERS,
    ),
    GribDatasetInfo(
        key="dmi_wam_natlant",
        name="DMI WAM - golven Noord-Atlantische Oceaan (0,25°)",
        version="1",
        description=(
            "DMI golfmodel WAM voor de Noord-Atlantische Oceaan (30-78°N, 69°W-30°O, "
            "0,25°), inclusief Golf van Biskaje en Noorse kust. Elke 6 uur, tot +132 uur."
        ),
        grid_type="regular_latlon",
        bounds=(30.0, -69.0, 78.0, 30.0),
        output_frequency_hours=1,
        forecast_horizon_hours=132,
        parameters=_WAM_PARAMETERS,
    ),
    GribDatasetInfo(
        key="dmi_dkss_nsbs",
        name="DMI DKSS - stroming en waterstand Noordzee en Oostzee (~5 km)",
        version="1",
        description=(
            "DMI stormvloedmodel DKSS voor Noordzee, Skagerrak en Oostzee "
            "(48,5-65,9°N, vanaf 4,1°W): oppervlaktestroming, waterstand en "
            "watertemperatuur. Elke 6 uur, tot +120 uur."
        ),
        grid_type="regular_latlon",
        bounds=(48.525, -4.125, 65.875, 30.292),
        output_frequency_hours=1,
        forecast_horizon_hours=120,
        parameters=_DKSS_PARAMETERS,
    ),
)

# Our dataset key -> DMI collection id.
_COLLECTION = {
    "dmi_wam_nsb": "wam_nsb",
    "dmi_wam_natlant": "wam_natlant",
    "dmi_dkss_nsbs": "dkss_nsbs",
}

# Datasets whose files carry far more than we use, with the surface fields up
# front: those are read only as far as the wanted messages go.
_PARTIAL_DOWNLOAD = {"dmi_dkss_nsbs"}


def _run_id(run: datetime) -> str:
    return run.strftime("%Y%m%d%H")


def _parse_run_id(run_id: str) -> datetime:
    return datetime.strptime(run_id, "%Y%m%d%H").replace(tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _grib1_key(message: bytes) -> tuple[int, int, int]:
    """(indicatorOfParameter, indicatorOfTypeOfLevel, level) from a GRIB1 message's PDS."""
    pds = message[8:]
    return pds[8], pds[9], int.from_bytes(pds[10:12], "big")


def _wanted_keys(parameters: list[GribParameter]) -> set[tuple[int, int, int]]:
    keys = set()
    for p in parameters:
        for filt in (p.grib_filter, p.grib_filter_u, p.grib_filter_v):
            if filt:
                keys.add((filt["indicatorOfParameter"], filt["indicatorOfTypeOfLevel"], filt["level"]))
    return keys


class DmiSource(GribSource):
    """GribSource for DMI's keyless forecast-data API (WAM, DKSS)."""

    key = "dmi"
    name = "DMI Open Data"
    supports_push_notifications = False
    provides_archive = False

    def __init__(self, session: aiohttp.ClientSession, api_key: str | None = None,
                 notification_api_key: str | None = None, instance_id: str | None = None) -> None:
        self._session = session
        # A complete run stays complete: remember those, so a poll only has to
        # look at the newer runs that may still be publishing.
        self._complete: dict[str, dict[str, dict[int, str]]] = {}

    async def async_list_datasets(self) -> list[GribDatasetInfo]:
        return list(KNOWN_DATASETS)

    async def _get_json(self, url: str) -> dict:
        try:
            async with self._session.get(url) as resp:
                if resp.status >= 400:
                    raise GribSourceError(f"DMI {url} returned HTTP {resp.status}")
                return await resp.json(content_type=None)
        except aiohttp.ClientError as err:
            raise GribSourceError(f"DMI request failed: {err}") from err

    async def _run_files(self, dataset: GribDatasetInfo, run: datetime) -> dict[int, str]:
        """{lead hours: download URL} for one model run."""
        url = f"{API_BASE_URL}/{_COLLECTION[dataset.key]}/items?modelRun={_iso(run)}&limit=1000"
        data = await self._get_json(url)
        files: dict[int, str] = {}
        for feature in data.get("features") or []:
            try:
                valid = datetime.fromisoformat(
                    feature["properties"]["datetime"].replace("Z", "+00:00")
                )
                href = feature["asset"]["data"]["href"]
            except (KeyError, TypeError, ValueError):
                continue
            files[int((valid - run).total_seconds() // 3600)] = href
        return files

    def _is_complete(self, dataset: GribDatasetInfo, files: dict[int, str]) -> bool:
        last = int(dataset.forecast_horizon_hours)
        return all(lead in files for lead in range(last + 1))

    async def _latest_complete_run(self, dataset: GribDatasetInfo) -> str | None:
        now = datetime.now(timezone.utc)
        newest = now.replace(
            hour=now.hour - now.hour % _RUN_INTERVAL_HOURS, minute=0, second=0, microsecond=0
        )
        cache = self._complete.setdefault(dataset.key, {})
        for i in range(_RUN_LOOKBACK):
            run = newest - timedelta(hours=_RUN_INTERVAL_HOURS * i)
            run_id = _run_id(run)
            if run_id in cache:
                return run_id
            files = await self._run_files(dataset, run)
            if self._is_complete(dataset, files):
                cache.clear()  # only the newest complete run is ever needed again
                cache[run_id] = files
                return run_id
        return None

    async def async_list_files(
        self,
        dataset: GribDatasetInfo,
        *,
        max_keys: int = 20,
        order_by: str = "lastModified",
        sorting: str = "desc",
    ) -> list[GribFileInfo]:
        run_id = await self._latest_complete_run(dataset)
        if run_id is None:
            return []
        return [GribFileInfo(filename=run_id, size=0, last_modified=_iso(_parse_run_id(run_id)))]

    async def async_download_file(
        self, dataset: GribDatasetInfo, filename: str, destination: Path
    ) -> Path:
        raise GribSourceError("DMI delivers one file per lead time; use async_download_run")

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
        files = self._complete.get(dataset.key, {}).get(run_id)
        if files is None:
            files = await self._run_files(dataset, _parse_run_id(run_id))
        leads = [lead for lead in sorted(files) if lead <= horizon_hours]
        parameters = [p for p in dataset.parameters if p.key in param_keys]
        wanted = _wanted_keys(parameters)
        partial = dataset.key in _PARTIAL_DOWNLOAD

        semaphore = asyncio.Semaphore(_DOWNLOAD_CONCURRENCY)

        async def fetch(lead: int) -> Path:
            dest = run_dir / f"{run_id}_{lead:03d}.grib"
            async with semaphore:
                messages = await self._download_messages(files[lead], wanted, partial)
            await loop.run_in_executor(None, dest.write_bytes, b"".join(messages))
            return dest

        # Let every download finish (or fail) before reporting, so nothing is
        # still writing into run_dir when the caller cleans it up after an error.
        results = await asyncio.gather(*(fetch(lead) for lead in leads), return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException):
                raise result
        return list(results)

    async def _download_messages(
        self, url: str, wanted: set[tuple[int, int, int]], partial: bool
    ) -> list[bytes]:
        """The GRIB1 messages of ``url`` that hold a wanted field.

        With ``partial``, reading stops as soon as every wanted field has been
        seen -- for DKSS that is the first ~0.6 MB of a ~9 MB file.
        """
        found: dict[tuple[int, int, int], bytes] = {}
        buf = b""
        try:
            async with self._session.get(url) as resp:
                if resp.status >= 400:
                    raise GribSourceError(f"DMI download {url} returned HTTP {resp.status}")
                async for chunk in resp.content.iter_chunked(256 * 1024):
                    buf += chunk
                    buf = self._take_messages(buf, wanted, found)
                    if partial and len(found) == len(wanted):
                        break
        except aiohttp.ClientError as err:
            raise GribSourceError(f"DMI download failed: {err}") from err
        if not found:
            raise GribSourceError(f"DMI file {url} holds none of the wanted fields")
        return list(found.values())

    @staticmethod
    def _take_messages(
        buf: bytes, wanted: set[tuple[int, int, int]], found: dict
    ) -> bytes:
        """Move every complete message at the start of ``buf`` into ``found``; return the rest."""
        while True:
            start = buf.find(b"GRIB")
            if start < 0:
                return buf[-3:]  # keep a possibly split "GRI"
            if len(buf) < start + 8:
                return buf[start:]
            if buf[start + 7] != 1:
                raise GribSourceError("DMI file is not GRIB edition 1")
            length = int.from_bytes(buf[start + 4:start + 7], "big")
            if len(buf) < start + length:
                return buf[start:]
            message = buf[start:start + length]
            key = _grib1_key(message)
            if key in wanted and key not in found:
                found[key] = message
            buf = buf[start + length:]
