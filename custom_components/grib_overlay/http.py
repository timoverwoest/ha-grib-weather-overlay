"""HTTP views the frontend card uses to discover config entries and fetch frames.

Registered once (guarded in __init__.py) since routes are process-global, but
data is looked up per config entry so multiple grib_overlay entries (e.g.
different datasets, or later a different source) can coexist.
"""

from __future__ import annotations

import gzip
import json
import logging
import math

from aiohttp import web

from homeassistant.components import persistent_notification
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from . import client_errors
from . import field_grid
from . import labels
from . import observations
from . import weather_maps
from .const import CONF_ALIAS, CONF_DATASET, CONF_SOURCE, DOMAIN, HTTP_CLIENT_ERROR_PATH, HTTP_ENTRIES_PATH, HTTP_FIELD_PATH, HTTP_FRAME_IMAGE_PATH, HTTP_FRAMES_PATH, HTTP_POINT_ALL_PATH, HTTP_POINT_PATH, HTTP_STATION_OBS_PATH, HTTP_STATIONS_PATH, HTTP_WEATHER_MAPS_PATH, HTTP_WIND_PATH
from .coordinator import GribOverlayCoordinator, enabled_parameter_keys
from .sources.base import direction_key_for

_LOGGER = logging.getLogger(__name__)

# Failures already reported by a browser, so one broken card cannot fill the log.
CLIENT_ERRORS_SEEN = f"{DOMAIN}_client_errors_seen"


def _coordinator(hass: HomeAssistant, entry_id: str) -> GribOverlayCoordinator | None:
    return hass.data.get(DOMAIN, {}).get(entry_id)


def _point_payload(coordinator: GribOverlayCoordinator, key: str, lat: float, lon: float) -> dict:
    """Sample one parameter's time-series at (lat, lon), plus its colour legend.

    Runs off the event loop (reads the cached per-frame field JSON files). The
    legend lets the card colour cells without a separate frames request, and a
    from-direction series is attached for wind (u/v) and for a scalar that has a
    companion direction parameter -- the one of its own family (swell_height ->
    swell_direction), matching the single-point view.
    """
    frames = coordinator.frames.get(key, [])
    if not frames:
        return {"unit": None, "series": []}
    legend = frames[0].legend
    unit = legend.unit
    entries = [
        (f.valid_time.isoformat(), f.field_path, f.wind_path) for f in frames if f.field_path
    ]
    has_direction = any(wind_path is not None for _, _, wind_path in entries)

    dir_by_time: dict[str, object] = {}
    direction_key = direction_key_for(key) if unit != "°" else None
    comp_frames = coordinator.frames.get(direction_key, []) if direction_key else []
    if comp_frames and comp_frames[0].legend.unit == "°":
        dir_by_time = {
            f.valid_time.isoformat(): f.field_path for f in comp_frames if f.field_path
        }
        if dir_by_time:
            has_direction = True

    series = []
    for valid_time, field_path, wind_path in entries:
        try:
            field = json.loads(field_path.read_text())
        except (OSError, ValueError):
            continue
        point = {"valid_time": valid_time, "value": field_grid.sample_field(field, lat, lon)}
        if wind_path is not None and wind_path.exists():
            try:
                wind = json.loads(wind_path.read_text())
            except (OSError, ValueError):
                wind = None
            point["direction"] = _wind_direction(wind, lat, lon) if wind else None
        elif valid_time in dir_by_time:
            try:
                dfield = json.loads(dir_by_time[valid_time].read_text())
                point["direction"] = field_grid.sample_field(dfield, lat, lon)
            except (OSError, ValueError):
                point["direction"] = None
        series.append(point)

    payload = {
        "unit": unit,
        "legend": {
            "unit": legend.unit,
            "min_value": legend.min_value,
            "max_value": legend.max_value,
            "stops": list(legend.stops),
        },
        "series": series,
    }
    if has_direction:
        payload["direction_unit"] = "°"
    return payload


def _wind_direction(wind, lat: float, lon: float) -> float | None:
    """Meteorological FROM direction (degrees) from a stored u/v wind record pair.

    ``wind`` is the leaflet-velocity two-record list ([u_record, v_record]); each
    record's header carries the same nx/ny/lo1/la1/dx/dy grid used by the scalar
    field, so we can bilinearly sample u and v with ``field_grid.sample_field``.
    """
    if not isinstance(wind, list) or len(wind) < 2:
        return None
    try:
        u = field_grid.sample_field({**wind[0]["header"], "data": wind[0]["data"]}, lat, lon)
        v = field_grid.sample_field({**wind[1]["header"], "data": wind[1]["data"]}, lat, lon)
    except (KeyError, TypeError):
        return None
    if u is None or v is None or math.hypot(u, v) < 0.3:
        return None  # calm: direction is meaningless
    return round((270.0 - math.degrees(math.atan2(v, u))) % 360.0, 0)


# The lists are built in memory, so there is no file to keep a compressed copy
# beside: gzip them on the way out instead. A frame list for one entry is 49 kB
# of timestamps and urls, measured on a real instance, and about a seventh of
# that compressed. Small answers are left alone -- below a few kB the header
# costs more than the saving.
_COMPRESS_FROM_BYTES = 4096


def _json(request: web.Request, payload, status: int = 200) -> web.Response:
    """A JSON response, gzipped when it is worth it and the caller takes it."""
    body = json.dumps(payload).encode()
    if len(body) >= _COMPRESS_FROM_BYTES and "gzip" in (request.headers.get("Accept-Encoding") or ""):
        return web.Response(
            body=gzip.compress(body, 6),
            status=status,
            content_type="application/json",
            headers={"Content-Encoding": "gzip"},
        )
    return web.Response(body=body, status=status, content_type="application/json")


# The wind and field grids are tens of thousands of numbers written out as
# text: 210 kB for one wind frame, measured on a real instance, and the biggest
# thing the card ever downloads. As text they compress about fourfold, but
# aiohttp does not compress a response by itself. So keep a gzipped copy beside
# the file -- written the first time it is asked for, thrown away with the run
# it belongs to -- and hand that over to any browser that takes it.
def _read_for_transfer(path, accepts_gzip: bool) -> tuple[bytes, str | None]:
    """Blocking: the file's bytes, gzipped when the caller can take them."""
    if not accepts_gzip:
        return path.read_bytes(), None
    gz = path.with_name(path.name + ".gz")
    try:
        if gz.stat().st_mtime >= path.stat().st_mtime:
            return gz.read_bytes(), "gzip"
    except OSError:
        pass  # no copy yet, or an unreadable one: make it below
    raw = path.read_bytes()
    blob = gzip.compress(raw, 6)
    try:
        tmp = path.with_name(path.name + ".gz.tmp")
        tmp.write_bytes(blob)
        tmp.replace(gz)
    except OSError:
        pass  # a read-only cache still gets the compressed response
    return blob, "gzip"


async def _grid_response(hass: HomeAssistant, request: web.Request, path) -> web.Response:
    accepts_gzip = "gzip" in (request.headers.get("Accept-Encoding") or "")
    body, encoding = await hass.async_add_executor_job(_read_for_transfer, path, accepts_gzip)
    headers = {"Cache-Control": "max-age=3600"}
    if encoding:
        headers["Content-Encoding"] = encoding
    return web.Response(body=body, content_type="application/json", headers=headers)


class GribOverlayEntriesView(HomeAssistantView):
    """Lists configured grib_overlay entries and the parameters each offers."""

    url = HTTP_ENTRIES_PATH
    name = "api:grib_overlay:entries"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        entries = []
        for entry_id, coordinator in hass.data.get(DOMAIN, {}).items():
            entry = coordinator.entry
            dataset = next(
                (d for d in (await coordinator.source.async_list_datasets()) if d.key == entry.data[CONF_DATASET]),
                None,
            )
            if dataset is None:
                continue
            enabled = set(enabled_parameter_keys(entry))
            entries.append(
                {
                    "entry_id": entry_id,
                    "title": entry.title,
                    "alias": (entry.options.get(CONF_ALIAS) or entry.data.get(CONF_ALIAS) or ""),
                    "source": entry.data[CONF_SOURCE],
                    "dataset": {
                        "key": dataset.key,
                        "name": dataset.name,
                        "bounds": dataset.bounds,
                    },
                    "parameters": [
                        {
                            "key": p.key,
                            "name": p.name,
                            "unit": p.unit,
                            "colormap": p.colormap,
                        }
                        for p in dataset.parameters
                        if p.key in enabled
                    ],
                }
            )
        return _json(request, {"entries": entries})


class GribOverlayFramesView(HomeAssistantView):
    """Lists available frames (one entry per valid_time) for one entry's parameters."""

    url = HTTP_FRAMES_PATH + "/{entry_id}"
    name = "api:grib_overlay:frames"
    requires_auth = True

    async def get(self, request: web.Request, entry_id: str) -> web.Response:
        coordinator = _coordinator(request.app["hass"], entry_id)
        if coordinator is None:
            return web.json_response({"error": "unknown entry_id"}, status=404)

        only_parameter = request.query.get("parameter")
        result: dict[str, list[dict]] = {}
        for key, frames in coordinator.frames.items():
            if only_parameter and key != only_parameter:
                continue
            result[key] = [
                {
                    "frame_id": frame.png_path.stem,
                    "valid_time": frame.valid_time.isoformat(),
                    "run_time": frame.run_time.isoformat(),
                    "bounds": frame.bounds,
                    "image_url": f"{HTTP_FRAME_IMAGE_PATH}/{entry_id}/{key}/{frame.png_path.stem}.png",
                    "wind_url": (
                        f"{HTTP_WIND_PATH}/{entry_id}/{key}/{frame.png_path.stem}.json"
                        if frame.wind_path
                        else None
                    ),
                    "field_url": (
                        f"{HTTP_FIELD_PATH}/{entry_id}/{key}/{frame.png_path.stem}.json"
                        if frame.field_path
                        else None
                    ),
                    "legend": {
                        "unit": frame.legend.unit,
                        "min_value": frame.legend.min_value,
                        "max_value": frame.legend.max_value,
                        "stops": list(frame.legend.stops),
                    },
                }
                for frame in frames
            ]
        return _json(request, result)


class GribOverlayFrameImageView(HomeAssistantView):
    """Serves one cached frame PNG.

    requires_auth is False on purpose: Leaflet loads these via a plain
    ``L.imageOverlay`` (an <img> element), which cannot attach Home
    Assistant's bearer token, so an authed view would 401 and no overlay
    would appear. The metadata views above stay authenticated; only the
    rendered image bytes are public. That's acceptable here -- they are
    colour renderings of already-public KNMI weather data, addressed by an
    unguessable config-entry ULID plus parameter/frame id, with no path
    traversal (the frame id must match an in-memory frame).
    """

    url = HTTP_FRAME_IMAGE_PATH + "/{entry_id}/{parameter_key}/{frame_id}.png"
    name = "api:grib_overlay:frame_image"
    requires_auth = False

    async def get(
        self, request: web.Request, entry_id: str, parameter_key: str, frame_id: str
    ) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        coordinator = _coordinator(hass, entry_id)
        if coordinator is None:
            return web.Response(status=404)
        frame = coordinator.get_frame(parameter_key, frame_id)
        if frame is None or not frame.png_path.exists():
            return web.Response(status=404)
        data = await hass.async_add_executor_job(frame.png_path.read_bytes)
        return web.Response(body=data, content_type="image/png", headers={"Cache-Control": "max-age=3600"})


class GribOverlayWindView(HomeAssistantView):
    """Serves one wind frame's leaflet-velocity JSON (raw u/v grid)."""

    url = HTTP_WIND_PATH + "/{entry_id}/{parameter_key}/{frame_id}.json"
    name = "api:grib_overlay:wind"
    requires_auth = True  # fetched via hass.callApi, which sends the auth token

    async def get(
        self, request: web.Request, entry_id: str, parameter_key: str, frame_id: str
    ) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        coordinator = _coordinator(hass, entry_id)
        if coordinator is None:
            return web.Response(status=404)
        frame = coordinator.get_frame(parameter_key, frame_id)
        if frame is None or frame.wind_path is None or not frame.wind_path.exists():
            return web.Response(status=404)
        return await _grid_response(hass, request, frame.wind_path)


class GribOverlayFieldView(HomeAssistantView):
    """Serves one frame's compact scalar grid JSON (for the client-side readout)."""

    url = HTTP_FIELD_PATH + "/{entry_id}/{parameter_key}/{frame_id}.json"
    name = "api:grib_overlay:field"
    requires_auth = True  # fetched via hass.callApi

    async def get(
        self, request: web.Request, entry_id: str, parameter_key: str, frame_id: str
    ) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        coordinator = _coordinator(hass, entry_id)
        if coordinator is None:
            return web.Response(status=404)
        frame = coordinator.get_frame(parameter_key, frame_id)
        if frame is None or frame.field_path is None or not frame.field_path.exists():
            return web.Response(status=404)
        return await _grid_response(hass, request, frame.field_path)


class GribOverlayPointView(HomeAssistantView):
    """Returns a parameter's value time-series at a lat/lon (click value + meteogram)."""

    url = HTTP_POINT_PATH + "/{entry_id}/{parameter_key}"
    name = "api:grib_overlay:point"
    requires_auth = True

    async def get(self, request: web.Request, entry_id: str, parameter_key: str) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        coordinator = _coordinator(hass, entry_id)
        if coordinator is None:
            return web.json_response({"error": "unknown entry_id"}, status=404)
        try:
            lat = float(request.query["lat"])
            lon = float(request.query["lon"])
        except (KeyError, ValueError):
            return web.json_response({"error": "lat/lon required"}, status=400)

        payload = await hass.async_add_executor_job(
            _point_payload, coordinator, parameter_key, lat, lon
        )
        return _json(request, payload)


class GribOverlayPointAllView(HomeAssistantView):
    """Returns EVERY parameter's time-series + legend at a lat/lon in one request.

    Backs the detailed (all-parameters) meteogram: one round trip per entry, and
    the field files are read once inside a single executor job, so the card can
    present the table without a frames call plus a request per parameter.
    """

    url = HTTP_POINT_ALL_PATH + "/{entry_id}"
    name = "api:grib_overlay:point_all"
    requires_auth = True

    async def get(self, request: web.Request, entry_id: str) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        coordinator = _coordinator(hass, entry_id)
        if coordinator is None:
            return web.json_response({"error": "unknown entry_id"}, status=404)
        try:
            lat = float(request.query["lat"])
            lon = float(request.query["lon"])
        except (KeyError, ValueError):
            return web.json_response({"error": "lat/lon required"}, status=400)

        keys = list(coordinator.frames.keys())

        def _sample_all_params() -> dict:
            return {key: _point_payload(coordinator, key, lat, lon) for key in keys}

        params = await hass.async_add_executor_job(_sample_all_params)
        return _json(request, {"params": params})


class GribOverlayStationObsView(HomeAssistantView):
    """Downloads recent measurement-station observations for one parameter near a
    point, so the comparison can plot/store real measured values (KNMI weather
    stations via EDR, or RWS Waterinfo for water parameters). Values come back in
    the parameter's SOURCE unit, like the forecast point endpoint.
    """

    url = HTTP_STATION_OBS_PATH
    name = "api:grib_overlay:station_obs"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        try:
            param = request.query["param"]
            lat = float(request.query["lat"])
            lon = float(request.query["lon"])
        except (KeyError, ValueError):
            return web.json_response({"error": "param/lat/lon required"}, status=400)
        start = request.query.get("start", "")
        end = request.query.get("end", "")
        result = await observations.fetch_observations(hass, param, lat, lon, start, end)
        if result is None:
            _LOGGER.warning("station_obs: no observation source for parameter %s", param)
            return web.json_response(
                {"error": f"no observation source for parameter '{param}'"}, status=404
            )
        if result.get("error"):
            _LOGGER.warning("station_obs %s @ %.3f,%.3f -> %s", param, lat, lon, result["error"])
            return web.json_response(result, status=502)
        _LOGGER.debug(
            "station_obs %s @ %.3f,%.3f -> %s obs from %s",
            param, lat, lon, len(result.get("series") or []), (result.get("station") or {}).get("name"),
        )
        return _json(request, result)


class GribOverlayStationsView(HomeAssistantView):
    """Lists measurement stations near a point that actually HAVE data for one
    parameter, so the card only offers stations that will return something."""

    url = HTTP_STATIONS_PATH
    name = "api:grib_overlay:stations"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        try:
            param = request.query["param"]
            lat = float(request.query["lat"])
            lon = float(request.query["lon"])
            radius = float(request.query.get("radius", "10"))
        except (KeyError, ValueError):
            return web.json_response({"error": "param/lat/lon required"}, status=400)
        try:
            stations = await observations.nearby_stations(hass, param, lat, lon, radius)
        except Exception as err:  # noqa: BLE001 - never break the card over this
            _LOGGER.warning("stations lookup failed for %s: %s", param, err)
            stations = []
        return _json(request, {"stations": stations})


class GribOverlayWeatherMapsView(HomeAssistantView):
    """Lists KNMI's current weather charts (and fetches their images into the cache)."""

    url = HTTP_WEATHER_MAPS_PATH
    name = "api:grib_overlay:weather_maps"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        try:
            charts = await weather_maps.get(hass).charts()
        except weather_maps.WeatherMapError as err:
            _LOGGER.warning("KNMI weather charts unavailable: %s", err)
            return web.json_response({"charts": [], "error": str(err)})
        return web.json_response(
            {
                "charts": [
                    {**c.as_dict(), "image_url": f"{HTTP_WEATHER_MAPS_PATH}/{c.name}"}
                    for c in charts
                ],
                "attribution": "© KNMI",
            }
        )


class GribOverlayWeatherMapImageView(HomeAssistantView):
    """Serves one cached KNMI chart image.

    requires_auth is False for the same reason as the frame images: an <img>
    can't send Home Assistant's token. Only a chart that the authenticated
    listing above put in the cache is served, so this never calls KNMI; the
    charts themselves are KNMI's public open data.
    """

    url = HTTP_WEATHER_MAPS_PATH + "/{name}"
    name = "api:grib_overlay:weather_map_image"
    requires_auth = False

    async def get(self, request: web.Request, name: str) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        path = await weather_maps.get(hass).image(name)
        if path is None:
            return web.Response(status=404)
        data = await hass.async_add_executor_job(path.read_bytes)
        return web.Response(body=data, content_type="image/gif", headers={"Cache-Control": "max-age=600"})


class GribOverlayClientErrorView(HomeAssistantView):
    """Takes the card's own account of why the browser dropped it.

    Home Assistant replaces a card with a message-less "configuration error"
    as soon as handing it ``hass`` throws, and writes the reason to the browser
    console only. The card watches for that line and posts it here, so the
    reason ends up where the person running the instance can reach it: the log,
    and a notification.
    """

    url = HTTP_CLIENT_ERROR_PATH
    name = "api:grib_overlay:client_error"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        try:
            report = await request.json()
        except ValueError:
            return web.Response(status=400, text="not JSON")
        if not isinstance(report, dict) or not client_errors.events(report):
            return web.Response(status=400, text="no card errors in the report")
        seen = hass.data.setdefault(CLIENT_ERRORS_SEEN, {})
        if not client_errors.is_new(seen, report):
            return web.json_response({"logged": False, "reason": "already reported"})
        _LOGGER.error("%s", client_errors.format_report(report))
        persistent_notification.async_create(
            hass,
            client_errors.notification(report, labels.language(hass)),
            title=client_errors.TITLE.get(labels.language(hass), client_errors.TITLE["en"]),
            notification_id=f"{DOMAIN}_client_error",
        )
        return web.json_response({"logged": True})


VIEWS = (
    GribOverlayEntriesView,
    GribOverlayFramesView,
    GribOverlayFrameImageView,
    GribOverlayWindView,
    GribOverlayFieldView,
    GribOverlayPointView,
    GribOverlayPointAllView,
    GribOverlayStationObsView,
    GribOverlayStationsView,
    GribOverlayWeatherMapsView,
    GribOverlayWeatherMapImageView,
    GribOverlayClientErrorView,
)
