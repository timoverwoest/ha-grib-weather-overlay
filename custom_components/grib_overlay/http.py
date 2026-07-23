"""HTTP views the frontend card uses to discover config entries and fetch frames.

Registered once (guarded in __init__.py) since routes are process-global, but
data is looked up per config entry so multiple grib_overlay entries (e.g.
different datasets, or later a different source) can coexist.
"""

from __future__ import annotations

import json
import math

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from . import field_grid
from .const import CONF_DATASET, CONF_PARAMETERS, CONF_SOURCE, DOMAIN, HTTP_ENTRIES_PATH, HTTP_FIELD_PATH, HTTP_FRAME_IMAGE_PATH, HTTP_FRAMES_PATH, HTTP_POINT_PATH, HTTP_WIND_PATH
from .coordinator import GribOverlayCoordinator


def _coordinator(hass: HomeAssistant, entry_id: str) -> GribOverlayCoordinator | None:
    return hass.data.get(DOMAIN, {}).get(entry_id)


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
            enabled = set(entry.data.get(CONF_PARAMETERS, []))
            entries.append(
                {
                    "entry_id": entry_id,
                    "title": entry.title,
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
        return web.json_response({"entries": entries})


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
        return web.json_response(result)


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
        data = await hass.async_add_executor_job(frame.wind_path.read_bytes)
        return web.Response(
            body=data, content_type="application/json", headers={"Cache-Control": "max-age=3600"}
        )


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
        data = await hass.async_add_executor_job(frame.field_path.read_bytes)
        return web.Response(
            body=data, content_type="application/json", headers={"Cache-Control": "max-age=3600"}
        )


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

        frames = coordinator.frames.get(parameter_key, [])
        unit = frames[0].legend.unit if frames else None
        entries = [
            (f.valid_time.isoformat(), f.field_path, f.wind_path) for f in frames if f.field_path
        ]
        # Wind parameters carry u/v grids, so we can add a direction series too.
        has_direction = any(wind_path is not None for _, _, wind_path in entries)

        def _sample_all() -> list[dict]:
            series = []
            for valid_time, field_path, wind_path in entries:
                try:
                    field = json.loads(field_path.read_text())
                except (OSError, ValueError):
                    continue
                point = {
                    "valid_time": valid_time,
                    "value": field_grid.sample_field(field, lat, lon),
                }
                if wind_path is not None and wind_path.exists():
                    try:
                        wind = json.loads(wind_path.read_text())
                    except (OSError, ValueError):
                        wind = None
                    point["direction"] = _wind_direction(wind, lat, lon) if wind else None
                series.append(point)
            return series

        series = await hass.async_add_executor_job(_sample_all)
        payload = {"unit": unit, "series": series}
        if has_direction:
            payload["direction_unit"] = "°"
        return web.json_response(payload)


VIEWS = (
    GribOverlayEntriesView,
    GribOverlayFramesView,
    GribOverlayFrameImageView,
    GribOverlayWindView,
    GribOverlayFieldView,
    GribOverlayPointView,
)
