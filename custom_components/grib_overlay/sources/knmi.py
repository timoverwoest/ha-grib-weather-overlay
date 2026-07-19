"""KNMI Data Platform (dataplatform.knmi.nl) GRIB source.

API docs: https://developer.dataplatform.knmi.nl/open-data-api

Each listed "file" for the HARMONIE datasets is a single forecast run bundled
as a .tar archive containing one GRIB1 file per forecast lead time (verified
against the live API: a `harmonie_arome_cy43_p1` file such as
``HARM43_V1_P1_2026071802.tar`` is ~850MB and its members are named like
``HA43_N20_202607180200_00500_GB``, one member per lead time). There is no
per-member download endpoint, so a full run has to be downloaded before
individual lead times can be extracted -- see coordinator.py for the
extract-only-what's-needed handling of that.

The parameter table below was verified against a real decoded
``harmonie_arome_cy43_p1`` message (indicatorOfParameter / typeOfLevel /
level), cross-checked with KNMI's published HARMONIE GRIB code table
(https://www.knmidata.nl/open-data/harmonie). KNMI uses a local GRIB1
parameter table (centre=knmi, table2Version=253) with no standard shortName
definitions, so filtering is done on the raw numeric fields instead, which
are always present. Decoding is handled by the in-tree pure-Python decoder
in grib1.py (no eccodes/cfgrib binary dependency).

KNMI also runs an MQTT Notification Service
(https://developer.dataplatform.knmi.nl/notification-service) that pushes an
event as soon as a new file is published, so the coordinator doesn't have to
wait for its next poll. Connection details (broker host/port, websocket
transport, topic pattern, CloudEvents-style JSON payload with a
data.filename field) were verified live against the real broker. Note that
the Notification Service authorises separately from the Open Data API: the
public anonymous demo key is rejected for MQTT, and even a valid Open Data
API key can get CONNACK "Not authorized" unless it's also subscribed to the
Notification Service on the KNMI Developer Portal. Push is therefore strictly
a best-effort optimization: polling (async_list_files) remains the source of
truth and keeps working on its own if MQTT can't connect or is rejected. On
an auth rejection we stop reconnecting (paho would otherwise retry forever)
and log it once.
"""

from __future__ import annotations

import asyncio
import functools
import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import aiohttp
import paho.mqtt.client as mqtt

from .base import (
    GribDatasetInfo,
    GribFileInfo,
    GribParameter,
    GribSource,
    GribSourceAuthError,
    GribSourceError,
)

_LOGGER = logging.getLogger(__name__)

API_BASE_URL = "https://api.dataplatform.knmi.nl/open-data/v1"

MQTT_HOST = "mqtt.dataplatform.knmi.nl"
MQTT_PORT = 443
MQTT_WS_PATH = "/mqtt"

# Parameters offered by the harmonie_arome_cy43_p1 dataset's near-surface
# GRIB messages. grib_filter values are candidate GRIB1 shortNames; confirmed
# against a real message in grib_decode.py, adjusted there if KNMI's naming
# differs.
# Level 105 = "height above ground" (raw GRIB1 indicatorOfTypeOfLevel), the
# level type used by all near-surface HARMONIE fields except MSL pressure
# (level type 103).
_LEVEL_GROUND = 105
_LEVEL_MSL = 103

_HARMONIE_NL_PARAMETERS: tuple[GribParameter, ...] = (
    GribParameter(
        key="wind_10m",
        name="Wind (10m)",
        unit="m/s",
        kind="vector",
        grib_filter_u={"indicatorOfParameter": 33, "indicatorOfTypeOfLevel": _LEVEL_GROUND, "level": 10},
        grib_filter_v={"indicatorOfParameter": 34, "indicatorOfTypeOfLevel": _LEVEL_GROUND, "level": 10},
        colormap="wind",
        value_range=(0, 25),
    ),
    GribParameter(
        key="wind_gust_10m",
        name="Windstoten (10m)",
        unit="m/s",
        kind="vector",
        grib_filter_u={"indicatorOfParameter": 162, "indicatorOfTypeOfLevel": _LEVEL_GROUND, "level": 10},
        grib_filter_v={"indicatorOfParameter": 163, "indicatorOfTypeOfLevel": _LEVEL_GROUND, "level": 10},
        colormap="wind",
        value_range=(0, 35),
    ),
    GribParameter(
        key="temperature_2m",
        name="Temperatuur (2m)",
        unit="°C",
        grib_filter={"indicatorOfParameter": 11, "indicatorOfTypeOfLevel": _LEVEL_GROUND, "level": 2},
        scale=1.0,
        offset=-273.15,  # Kelvin -> Celsius
        colormap="temperature",
        value_range=(-10, 35),
    ),
    GribParameter(
        key="dewpoint_2m",
        name="Dauwpunt (2m)",
        unit="°C",
        grib_filter={"indicatorOfParameter": 17, "indicatorOfTypeOfLevel": _LEVEL_GROUND, "level": 2},
        scale=1.0,
        offset=-273.15,
        colormap="temperature",
        value_range=(-15, 25),
    ),
    GribParameter(
        key="humidity_2m",
        name="Relatieve luchtvochtigheid (2m)",
        unit="%",
        grib_filter={"indicatorOfParameter": 52, "indicatorOfTypeOfLevel": _LEVEL_GROUND, "level": 2},
        scale=100.0,  # KNMI stores RH as a 0-1 fraction -> percent
        colormap="humidity",
        value_range=(0, 100),
    ),
    GribParameter(
        key="precipitation",
        name="Neerslag",
        unit="mm",
        grib_filter={"indicatorOfParameter": 61, "indicatorOfTypeOfLevel": _LEVEL_GROUND, "level": 0},
        colormap="precipitation",
        value_range=(0, 20),
    ),
    GribParameter(
        key="pressure_msl",
        name="Luchtdruk (zeeniveau)",
        unit="hPa",
        grib_filter={"indicatorOfParameter": 1, "indicatorOfTypeOfLevel": _LEVEL_MSL, "level": 0},
        scale=0.01,  # Pa -> hPa
        colormap="pressure",
        value_range=(980, 1040),
    ),
    GribParameter(
        key="visibility",
        name="Zicht",
        unit="km",
        grib_filter={"indicatorOfParameter": 20, "indicatorOfTypeOfLevel": _LEVEL_GROUND, "level": 0},
        scale=0.001,  # m -> km
        colormap="visibility",
        value_range=(0, 50),
    ),
    GribParameter(
        key="cloud_cover",
        name="Bewolking",
        unit="%",
        grib_filter={"indicatorOfParameter": 71, "indicatorOfTypeOfLevel": _LEVEL_GROUND, "level": 0},
        scale=100.0,  # KNMI stores cloud cover as a 0-1 fraction -> percent
        colormap="cloud",
        value_range=(0, 100),
    ),
)

KNOWN_DATASETS: tuple[GribDatasetInfo, ...] = (
    GribDatasetInfo(
        key="harmonie_arome_cy43_p1",
        name="HARMONIE-AROME Cy43 - Nederland, near-surface parameters",
        version="1.0",
        description=(
            "Uurlijkse HARMONIE-AROME voorspelling voor Nederland, regular "
            "lat-lon grid, near-surface en grenslaag parameters."
        ),
        grid_type="regular_latlon",
        bounds=(49.0, 0.0, 56.002, 11.281),
        output_frequency_hours=1,
        forecast_horizon_hours=48,
        parameters=_HARMONIE_NL_PARAMETERS,
    ),
)


class KnmiSource(GribSource):
    """GribSource implementation for the KNMI Data Platform Open Data API."""

    key = "knmi"
    name = "KNMI Data Platform"
    supports_push_notifications = True

    def __init__(self, session: aiohttp.ClientSession, api_key: str) -> None:
        self._session = session
        self._api_key = api_key
        self._mqtt_client: mqtt.Client | None = None
        self._notify_auth_logged = False

    async def async_list_datasets(self) -> list[GribDatasetInfo]:
        return list(KNOWN_DATASETS)

    async def _request(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        headers = {"Authorization": self._api_key}
        try:
            async with self._session.get(url, headers=headers, params=params) as resp:
                if resp.status in (401, 403):
                    raise GribSourceAuthError(
                        f"KNMI API rejected the API key (HTTP {resp.status})"
                    )
                if resp.status >= 400:
                    body = await resp.text()
                    raise GribSourceError(f"KNMI API error {resp.status}: {body[:200]}")
                return await resp.json()
        except aiohttp.ClientError as err:
            raise GribSourceError(f"KNMI API request failed: {err}") from err

    async def async_list_files(
        self,
        dataset: GribDatasetInfo,
        *,
        max_keys: int = 20,
        order_by: str = "lastModified",
        sorting: str = "desc",
    ) -> list[GribFileInfo]:
        url = f"{API_BASE_URL}/datasets/{dataset.key}/versions/{dataset.version}/files"
        data = await self._request(
            url,
            params={"maxKeys": max_keys, "orderBy": order_by, "sorting": sorting},
        )
        return [
            GribFileInfo(
                filename=f["filename"],
                size=f["size"],
                last_modified=f["lastModified"],
            )
            for f in data.get("files", [])
        ]

    async def async_get_download_url(self, dataset: GribDatasetInfo, filename: str) -> str:
        url = (
            f"{API_BASE_URL}/datasets/{dataset.key}/versions/{dataset.version}"
            f"/files/{filename}/url"
        )
        data = await self._request(url)
        return data["temporaryDownloadUrl"]

    async def async_download_file(
        self, dataset: GribDatasetInfo, filename: str, destination: Path
    ) -> Path:
        download_url = await self.async_get_download_url(dataset, filename)
        loop = asyncio.get_running_loop()
        # A HARMONIE run is ~850MB; the streaming download is async, but the
        # filesystem writes are blocking, so run mkdir/open/write/close in the
        # executor to keep them off the event loop.
        await loop.run_in_executor(
            None, functools.partial(destination.parent.mkdir, parents=True, exist_ok=True)
        )
        try:
            async with self._session.get(download_url) as resp:
                if resp.status >= 400:
                    raise GribSourceError(
                        f"Downloading {filename} failed with HTTP {resp.status}"
                    )
                fh = await loop.run_in_executor(None, destination.open, "wb")
                try:
                    async for chunk in resp.content.iter_chunked(1024 * 1024):
                        await loop.run_in_executor(None, fh.write, chunk)
                finally:
                    await loop.run_in_executor(None, fh.close)
        except aiohttp.ClientError as err:
            raise GribSourceError(f"Downloading {filename} failed: {err}") from err
        return destination

    async def async_start_notifications(
        self, dataset: GribDatasetInfo, on_new_file: Callable[[str], None]
    ) -> None:
        if self._mqtt_client is not None:
            return  # already listening

        loop = asyncio.get_running_loop()
        topic = f"dataplatform/file/v1/{dataset.key}/{dataset.version}/created"

        def _on_connect(client, _userdata, _flags, reason_code, _properties) -> None:
            if reason_code == 0:
                _LOGGER.debug("Connected to KNMI notification service, subscribing to %s", topic)
                client.subscribe(topic, qos=1)
                return
            # "Not authorized" and friends are permanent for this API key, so
            # stop here instead of letting paho auto-reconnect forever (that
            # produced dozens of identical warnings). Log it only once.
            if not self._notify_auth_logged:
                self._notify_auth_logged = True
                _LOGGER.warning(
                    "KNMI notification service rejected the connection (%s); continuing "
                    "with polling only. Push updates need an API key that is authorised "
                    "for the Notification Service (a separate subscription on the KNMI "
                    "Developer Portal). Polling keeps working regardless.",
                    reason_code,
                )
            client.disconnect()  # clean disconnect => paho won't auto-reconnect

        def _on_message(_client, _userdata, msg) -> None:
            try:
                payload = json.loads(msg.payload)
                filename = payload["data"]["filename"]
            except (ValueError, KeyError, TypeError):
                _LOGGER.debug("Ignoring unparsable notification on %s", msg.topic)
                return
            loop.call_soon_threadsafe(on_new_file, filename)

        def _on_disconnect(_client, _userdata, _flags, reason_code, _properties) -> None:
            _LOGGER.debug("Disconnected from KNMI notification service: %s", reason_code)

        # Building the client calls tls_set(), which loads CA certs from disk
        # (blocking), and connect() does network I/O -- do it all in the executor.
        def _build_and_connect() -> mqtt.Client:
            client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                transport="websockets",
                protocol=mqtt.MQTTProtocolVersion.MQTTv5,
            )
            client.username_pw_set(username="", password=self._api_key)
            client.tls_set()
            client.ws_set_options(path=MQTT_WS_PATH)
            client.reconnect_delay_set(min_delay=5, max_delay=120)
            client.on_connect = _on_connect
            client.on_message = _on_message
            client.on_disconnect = _on_disconnect
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
            client.loop_start()
            return client

        try:
            client = await loop.run_in_executor(None, _build_and_connect)
        except Exception as err:  # noqa: BLE001 - push is best-effort, polling is the fallback
            _LOGGER.warning(
                "Could not connect to KNMI notification service (falling back to polling "
                "only): %s",
                err,
            )
            return
        self._mqtt_client = client

    async def async_stop_notifications(self) -> None:
        client = self._mqtt_client
        self._mqtt_client = None
        if client is None:
            return
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, client.loop_stop)
        await loop.run_in_executor(None, client.disconnect)
