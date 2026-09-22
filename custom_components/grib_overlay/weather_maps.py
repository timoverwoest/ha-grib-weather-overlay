"""KNMI's surface weather charts (with fronts) for the weather-map card.

KNMI publishes its hand-analysed charts as open data -- dataset
``weather_maps`` 1.0 on the Open Data API, readable with the same key as
HARMONIE: ``AL_YYYYMMDDHH00.gif`` is the analysis for that time (00/06/12/18
UTC), ``PL_YYYYMMDDHH00.gif`` a forecast chart valid then (up to +48 h). They
are images in KNMI's own projection, so the card shows them as they are rather
than as a map layer.

The charts are fetched with the key on the server and kept in a small cache
next to the GRIB cache; the card lists them through an authenticated view and
loads the images from the cache. Only charts the listing put there can be
served, so an image request never makes us call KNMI.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import storage_paths
from .const import CONF_API_KEY, CONF_SOURCE, DOMAIN
from .sources.knmi import API_BASE_URL

_LOGGER = logging.getLogger(__name__)

DATA_KEY = f"{DOMAIN}_weather_maps"
DATASET_PATH = "datasets/weather_maps/versions/1.0/files"
NAME_RE = re.compile(r"^(AL|PL)_(\d{12})\.gif$")
_LIST_TTL_SECONDS = 600
_HISTORY_ANALYSES = 4  # the latest analysis and the three before it
_TIMEOUT = aiohttp.ClientTimeout(total=60)


class WeatherMapError(Exception):
    """The charts can't be listed or fetched (message is shown on the card)."""


@dataclass(frozen=True)
class Chart:
    name: str
    kind: str  # "analysis" | "forecast"
    valid_time: datetime
    issued: str  # KNMI's lastModified

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "valid_time": self.valid_time.isoformat(),
            "issued": self.issued,
        }


def select_charts(files: list[dict]) -> list[Chart]:
    """The charts worth showing, oldest first.

    The latest few analyses, plus the forecast charts valid after the newest
    analysis -- each in its most recently issued version.
    """
    newest: dict[str, Chart] = {}
    for f in files:
        match = NAME_RE.match(f.get("filename", ""))
        if not match:
            continue
        valid = datetime.strptime(match.group(2), "%Y%m%d%H%M").replace(tzinfo=timezone.utc)
        chart = Chart(
            name=f["filename"],
            kind="analysis" if match.group(1) == "AL" else "forecast",
            valid_time=valid,
            issued=f.get("lastModified", ""),
        )
        if chart.name not in newest or chart.issued > newest[chart.name].issued:
            newest[chart.name] = chart
    analyses = sorted((c for c in newest.values() if c.kind == "analysis"), key=lambda c: c.valid_time)
    analyses = analyses[-_HISTORY_ANALYSES:]
    latest = analyses[-1].valid_time if analyses else None
    forecasts = sorted(
        (c for c in newest.values() if c.kind == "forecast" and (latest is None or c.valid_time > latest)),
        key=lambda c: c.valid_time,
    )
    return analyses + forecasts


def knmi_api_key(hass: HomeAssistant) -> str | None:
    """The Open Data key of any configured KNMI entry."""
    for coordinator in hass.data.get(DOMAIN, {}).values():
        entry = getattr(coordinator, "entry", None)
        if entry is not None and entry.data.get(CONF_SOURCE) == "knmi" and entry.data.get(CONF_API_KEY):
            return entry.data[CONF_API_KEY]
    return None


class WeatherMaps:
    """Lists KNMI's charts and keeps their images in a small on-disk cache."""

    INDEX = "index.json"

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._dir: Path | None = None
        self._charts: list[Chart] = []
        self._listed_at = 0.0
        self._lock = asyncio.Lock()
        self._refreshing: asyncio.Task | None = None

    async def _cache_dir(self) -> Path:
        if self._dir is None:
            def make() -> Path:
                path = storage_paths.default_storage_root() / "weather_maps"
                path.mkdir(parents=True, exist_ok=True)
                return path

            self._dir = await self._hass.async_add_executor_job(make)
        return self._dir

    async def _get(self, url: str, key: str | None) -> aiohttp.ClientResponse:
        session = async_get_clientsession(self._hass)
        headers = {"Authorization": key} if key else None
        try:
            resp = await session.get(url, headers=headers, timeout=_TIMEOUT)
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise WeatherMapError(f"KNMI request failed: {err}") from err
        if resp.status in (401, 403):
            resp.release()
            raise WeatherMapError(
                f"KNMI refused the key for the weather charts (HTTP {resp.status})"
            )
        if resp.status >= 400:
            resp.release()
            raise WeatherMapError(f"KNMI returned HTTP {resp.status}")
        return resp

    async def charts(self) -> list[Chart]:
        """The current chart list, refreshed (and its images fetched) when stale.

        Listing the charts and fetching the ones we do not have takes a couple
        of seconds against KNMI -- measured at two on a real instance -- and it
        used to happen while the card sat waiting for its answer, which made
        this the slowest thing on the page by a wide margin. Charts change
        every few hours, so a list ten minutes old is still the right answer:
        hand it over at once and fetch the new one behind it. Only a card that
        has nothing at all to show waits.
        """
        if self._charts and time.monotonic() - self._listed_at < _LIST_TTL_SECONDS:
            return self._charts
        if self._charts:
            self._refresh_in_background()
            return self._charts
        async with self._lock:
            if self._charts:
                return self._charts
            return await self._refresh()

    def _refresh_in_background(self) -> None:
        if self._refreshing is not None and not self._refreshing.done():
            return
        self._refreshing = self._hass.async_create_background_task(
            self._refresh_quietly(), f"{DOMAIN}_weather_maps_refresh"
        )

    async def _refresh_quietly(self) -> None:
        async with self._lock:
            try:
                await self._refresh()
            except WeatherMapError as err:
                # The card keeps the charts it has; say why the new ones are late.
                _LOGGER.debug("Weather charts could not be refreshed: %s", err)

    async def _refresh(self) -> list[Chart]:
        key = knmi_api_key(self._hass)
        if not key:
            raise WeatherMapError("no KNMI entry configured")
        resp = await self._get(
            f"{API_BASE_URL}/{DATASET_PATH}?maxKeys=40&orderBy=lastModified&sorting=desc", key
        )
        async with resp:
            listing = await resp.json(content_type=None)
        charts = select_charts(listing.get("files") or [])
        await self._fetch_images(charts, key)
        self._charts, self._listed_at = charts, time.monotonic()
        return charts

    async def _fetch_images(self, charts: list[Chart], key: str) -> None:
        folder = await self._cache_dir()
        index_path = folder / self.INDEX

        def read_index() -> dict:
            try:
                return json.loads(index_path.read_text())
            except (OSError, ValueError):
                return {}

        index = await self._hass.async_add_executor_job(read_index)
        for chart in charts:
            path = folder / chart.name
            if index.get(chart.name) == chart.issued and await self._hass.async_add_executor_job(path.exists):
                continue
            resp = await self._get(f"{API_BASE_URL}/{DATASET_PATH}/{chart.name}/url", key)
            async with resp:
                link = (await resp.json(content_type=None)).get("temporaryDownloadUrl")
            if not link:
                raise WeatherMapError(f"KNMI gave no download link for {chart.name}")
            resp = await self._get(link, None)
            async with resp:
                body = await resp.read()
            await self._hass.async_add_executor_job(path.write_bytes, body)
            index[chart.name] = chart.issued

        wanted = {c.name for c in charts}

        def tidy() -> None:
            for old in folder.glob("*.gif"):
                if old.name not in wanted:
                    old.unlink(missing_ok=True)
            index_path.write_text(json.dumps({k: v for k, v in index.items() if k in wanted}))

        await self._hass.async_add_executor_job(tidy)

    async def image(self, name: str) -> Path | None:
        """A cached chart image -- only one the current listing put there."""
        if not NAME_RE.match(name) or name not in {c.name for c in self._charts}:
            return None
        path = (await self._cache_dir()) / name
        return path if await self._hass.async_add_executor_job(path.exists) else None


def get(hass: HomeAssistant) -> WeatherMaps:
    if DATA_KEY not in hass.data:
        hass.data[DATA_KEY] = WeatherMaps(hass)
    return hass.data[DATA_KEY]
