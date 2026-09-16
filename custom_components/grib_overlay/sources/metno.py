"""MET Norway GRIB files: weather, waves and currents for the Norwegian coast.

The Norwegian Meteorological Institute's GRIB files API (api.met.no) serves
small ready-made files per area, without a key, for the waters at the Oslo end
of a North Sea route:

- weather: MEPS (wind, hourly precipitation, sea-level pressure), ~66 h;
- waves: WAVEWATCH III 4 km (significant height and direction), ~72 h;
- current: NorKyst 800 m (current 3 m below the surface), ~120 h.

All GRIB1, simple packing, on a 0.05 deg lat/lon grid. Each file holds every
lead time, but every message carries its valid time as its reference time
(P1 = 0); the files are split per lead time with the PDS rewritten to the
file's first time as the run and the lead as P1, so the coordinator sees an
ordinary run.

api.met.no asks every client to identify itself in the User-Agent (it
answers 403 otherwise) and to go easy on the service; one poll only fetches
the small availability lists, and files only when one was updated.
"""

from __future__ import annotations

import asyncio
import functools
import json
from collections import defaultdict
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

API_BASE_URL = "https://api.met.no/weatherapi/gribfiles/1.1"
PROJECT_URL = "https://github.com/timoverwoest/ha-grib-weather-overlay"
_TIMEOUT = aiohttp.ClientTimeout(total=120)

_WEATHER, _WAVES, _CURRENT = "weather", "waves", "current"
_PRECIPITATION = (61, 105, 0)

_PARAMETERS: tuple[GribParameter, ...] = (
    GribParameter(
        key="wind_10m",
        name="Wind (10m)",
        unit="m/s",
        kind="vector",
        grib_filter_u={"indicatorOfParameter": 33, "indicatorOfTypeOfLevel": 105, "level": 10},
        grib_filter_v={"indicatorOfParameter": 34, "indicatorOfTypeOfLevel": 105, "level": 10},
        colormap="wind",
        value_range=(0, 25),
    ),
    # Hourly amounts already (not a total since the run started).
    GribParameter(
        key="precipitation",
        name="Neerslag",
        unit="mm",
        grib_filter={"indicatorOfParameter": 61, "indicatorOfTypeOfLevel": 105, "level": 0},
        colormap="precipitation",
        value_range=(0, 20),
    ),
    # Labelled "surface pressure" by MET, but it is the sea-level value: it
    # stays within a few hPa over the hills around the fjord.
    GribParameter(
        key="pressure_msl",
        name="Luchtdruk (zeeniveau)",
        unit="hPa",
        grib_filter={"indicatorOfParameter": 1, "indicatorOfTypeOfLevel": 105, "level": 0},
        scale=0.01,
        colormap="pressure",
        value_range=(980, 1040),
    ),
    GribParameter(
        key="wave_height",
        name="Golfhoogte (significant)",
        unit="m",
        grib_filter={"indicatorOfParameter": 100, "indicatorOfTypeOfLevel": 105, "level": 0},
        colormap="wave",
        value_range=(0, 8),
    ),
    # The direction waves come from (MET switched to this convention in 2023).
    GribParameter(
        key="wave_direction",
        name="Golfrichting (gemiddeld)",
        unit="°",
        grib_filter={"indicatorOfParameter": 230, "indicatorOfTypeOfLevel": 105, "level": 0},
        colormap="direction",
        value_range=(0, 360),
    ),
    GribParameter(
        key="current",
        name="Zeestroming (3 m diep)",
        unit="m/s",
        kind="vector",
        grib_filter_u={"indicatorOfParameter": 49, "indicatorOfTypeOfLevel": 160, "level": 3},
        grib_filter_v={"indicatorOfParameter": 50, "indicatorOfTypeOfLevel": 160, "level": 3},
        colormap="current",
        value_range=(0, 1.5),
    ),
)

_CONTENT_OF = {
    "wind_10m": _WEATHER,
    "precipitation": _WEATHER,
    "pressure_msl": _WEATHER,
    "wave_height": _WAVES,
    "wave_direction": _WAVES,
    "current": _CURRENT,
}


def _dataset(area: str, label: str, bounds: tuple[float, float, float, float]) -> GribDatasetInfo:
    return GribDatasetInfo(
        key=f"metno_{area}",
        name=f"MET Norway - {label}: weer, golven en stroming",
        version="1.1",
        description=(
            f"MET Norway GRIB-bestanden voor {label}: wind, neerslag en luchtdruk "
            "(MEPS, ~66 uur), golven (WAVEWATCH III 4 km, ~72 uur) en stroming op 3 m "
            "diepte (NorKyst 800 m, ~120 uur), op 0,05°. Geen sleutel."
        ),
        grid_type="regular_latlon",
        bounds=bounds,
        output_frequency_hours=1,
        forecast_horizon_hours=120,
        parameters=_PARAMETERS,
    )


KNOWN_DATASETS: tuple[GribDatasetInfo, ...] = (
    _dataset("oslofjord", "Oslofjord", (58.9, 9.8, 60.0, 11.2)),
    _dataset("skagerrak", "Skagerrak", (57.7, 7.8, 59.4, 12.0)),
    _dataset("sorlandet", "Sørlandet", (57.8, 7.0, 58.8, 9.4)),
)

_version: str | None = None


def _user_agent() -> str:
    """Our application and a contact, as api.met.no's terms ask."""
    return f"ha-grib-weather-overlay/{_version or 'dev'} (+{PROJECT_URL})"


def _read_version() -> str:
    manifest = Path(__file__).resolve().parents[1] / "manifest.json"
    try:
        return json.loads(manifest.read_text()).get("version", "dev")
    except (OSError, ValueError):
        return "dev"


def _area(dataset: GribDatasetInfo) -> str:
    return dataset.key.removeprefix("metno_")


def _message_time(message: bytes) -> datetime:
    pds = message[8:]
    year = (pds[24] - 1) * 100 + pds[12]
    return datetime(year, pds[13], pds[14], pds[15], pds[16], tzinfo=timezone.utc)


def _key(message: bytes) -> tuple[int, int, int]:
    pds = message[8:]
    return pds[8], pds[9], int.from_bytes(pds[10:12], "big")


def _with_run_time(message: bytes, run: datetime, lead_hours: int) -> bytes:
    """``message`` with its reference time set to ``run`` and ``lead_hours`` as P1."""
    out = bytearray(message)
    pds = 8
    out[pds + 12] = (run.year - 1) % 100 + 1
    out[pds + 24] = (run.year - 1) // 100 + 1
    out[pds + 13:pds + 17] = bytes([run.month, run.day, run.hour, run.minute])
    out[pds + 17] = 1  # unit: hour
    if lead_hours <= 255:
        out[pds + 18], out[pds + 19], out[pds + 20] = lead_hours, 0, 0
    else:  # P1 over both octets
        out[pds + 18], out[pds + 19], out[pds + 20] = lead_hours >> 8, lead_hours & 0xFF, 10
    return bytes(out)


def split_by_lead(
    buf: bytes, content: str, run_dir: Path, horizon_hours: float
) -> list[Path]:
    """Blocking: one member file per lead time, the first valid time being the run."""
    groups: dict[datetime, list[bytes]] = defaultdict(list)
    pos = 0
    while True:
        start = buf.find(b"GRIB", pos)
        if start < 0 or start + 8 > len(buf):
            break
        if buf[start + 7] != 1:
            raise GribSourceError("MET Norway file is not GRIB edition 1")
        length = int.from_bytes(buf[start + 4:start + 7], "big")
        message = buf[start:start + length]
        if len(message) < length:
            raise GribSourceError("MET Norway file is truncated")
        groups[_message_time(message)].append(message)
        pos = start + length
    if not groups:
        raise GribSourceError(f"MET Norway {content} file holds no GRIB messages")

    run = min(groups)
    paths = []
    for valid in sorted(groups):
        lead = int((valid - run).total_seconds() // 3600)
        if lead > horizon_hours:
            continue
        messages = [
            _with_run_time(m, run, lead)
            for m in groups[valid]
            # At the first time there is no hour behind it yet: the "hourly
            # precipitation" there is a placeholder zero, not a dry hour.
            if not (lead == 0 and _key(m) == _PRECIPITATION)
        ]
        path = run_dir / f"{content}_{lead:03d}.grib"
        path.write_bytes(b"".join(messages))
        paths.append(path)
    return paths


class MetnoSource(GribSource):
    """GribSource for MET Norway's GRIB files API."""

    key = "metno"
    name = "MET Norway"
    supports_push_notifications = False
    provides_archive = False

    def __init__(self, session: aiohttp.ClientSession, api_key: str | None = None,
                 notification_api_key: str | None = None, instance_id: str | None = None) -> None:
        self._session = session

    async def async_list_datasets(self) -> list[GribDatasetInfo]:
        return list(KNOWN_DATASETS)

    async def _get(self, url: str) -> bytes:
        global _version
        if _version is None:
            _version = await asyncio.get_running_loop().run_in_executor(None, _read_version)
        try:
            async with self._session.get(
                url, headers={"User-Agent": _user_agent()}, timeout=_TIMEOUT
            ) as resp:
                if resp.status == 403:
                    raise GribSourceError(
                        "MET Norway refused the request (403); it requires an identifying "
                        "User-Agent and may have blocked this one"
                    )
                if resp.status >= 400:
                    raise GribSourceError(f"MET Norway {url} returned HTTP {resp.status}")
                return await resp.read()
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise GribSourceError(f"MET Norway request failed: {err}") from err

    async def async_list_files(
        self,
        dataset: GribDatasetInfo,
        *,
        max_keys: int = 20,
        order_by: str = "lastModified",
        sorting: str = "desc",
    ) -> list[GribFileInfo]:
        area = _area(dataset)
        updated = []
        for content in (_WEATHER, _WAVES, _CURRENT):
            body = await self._get(f"{API_BASE_URL}/available.json?content={content}")
            try:
                items = json.loads(body)
            except ValueError as err:
                raise GribSourceError(f"MET Norway availability list unreadable: {err}") from err
            for item in items:
                if (item.get("params") or {}).get("area") == area and item.get("updated"):
                    updated.append(item["updated"])
        if not updated:
            return []
        # Any content updated -> a new "run" for this area.
        latest = max(
            datetime.fromisoformat(u.replace("Z", "+00:00")) for u in updated
        )
        return [
            GribFileInfo(
                filename=latest.strftime("%Y%m%d%H%M%S"), size=0, last_modified=latest.isoformat()
            )
        ]

    async def async_download_file(
        self, dataset: GribDatasetInfo, filename: str, destination: Path
    ) -> Path:
        raise GribSourceError("MET Norway files are split per lead time; use async_download_run")

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
        area = _area(dataset)
        contents = sorted({_CONTENT_OF[k] for k in param_keys if k in _CONTENT_OF})
        paths: list[Path] = []
        for content in contents:
            body = await self._get(f"{API_BASE_URL}/?area={area}&content={content}")
            paths.extend(
                await loop.run_in_executor(
                    None, split_by_lead, body, content, run_dir, horizon_hours
                )
            )
        return paths
