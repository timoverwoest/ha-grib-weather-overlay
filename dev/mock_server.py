#!/usr/bin/env python3
"""Standalone HTTP server that fakes the grib_overlay HA API + static files.

Lets the frontend card (custom_components/grib_overlay/www/grib-overlay-card.js)
be exercised in a real browser without a running Home Assistant instance.
Reuses the PNGs already produced by dev/render_preview.py, relabelled as a
handful of fake sequential valid_times so the slider/animation controls have
something to page through.

Run:
    python3 dev/mock_server.py [port]
Then open dev/dev.html served from this same server (printed on start).
"""

from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
WWW_DIR = REPO_ROOT / "custom_components" / "grib_overlay" / "www"
OUTPUT_DIR = REPO_ROOT / "dev" / "output"
DEV_DIR = REPO_ROOT / "dev"

BOUNDS = (49.0, 0.0, 56.002, 11.281)  # south, west, north, east
FRAME_COUNT = 6
FRAME_STEP_HOURS = 1
# Anchor the mock run around "now" so the meteogram's now-column marker shows.
BASE_RUN_TIME = (
    datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) - timedelta(hours=2)
)

# Mirrors the real colormap stops from render.py so the legend looks right.
LEGENDS = {
    "wind_10m": {"unit": "m/s", "min_value": 0, "max_value": 25, "stops": [
        {"offset": 0.0, "color": "#62b5e5"}, {"offset": 0.2, "color": "#7fcb85"},
        {"offset": 0.4, "color": "#f0de69"}, {"offset": 0.6, "color": "#ee9448"},
        {"offset": 0.8, "color": "#da4437"}, {"offset": 1.0, "color": "#89216d"},
    ]},
    "wind_gust_10m": {"unit": "m/s", "min_value": 0, "max_value": 35, "stops": [
        {"offset": 0.0, "color": "#62b5e5"}, {"offset": 0.2, "color": "#7fcb85"},
        {"offset": 0.4, "color": "#f0de69"}, {"offset": 0.6, "color": "#ee9448"},
        {"offset": 0.8, "color": "#da4437"}, {"offset": 1.0, "color": "#89216d"},
    ]},
    "precipitation": {"unit": "mm", "min_value": 0, "max_value": 20, "stops": [
        {"offset": 0.0, "color": "#deebf7"}, {"offset": 0.3, "color": "#6badd6"},
        {"offset": 0.6, "color": "#2171b5"}, {"offset": 1.0, "color": "#08306b"},
    ]},
    "temperature_2m": {"unit": "°C", "min_value": -10, "max_value": 35, "stops": [
        {"offset": 0.0, "color": "#313695"}, {"offset": 0.25, "color": "#4575b4"},
        {"offset": 0.5, "color": "#ffffbf"}, {"offset": 0.75, "color": "#fc8d59"},
        {"offset": 1.0, "color": "#a50026"},
    ]},
    "pressure_msl": {"unit": "hPa", "min_value": 980, "max_value": 1040, "stops": [
        {"offset": 0.0, "color": "#4575b4"}, {"offset": 0.5, "color": "#ffffbf"},
        {"offset": 1.0, "color": "#d73027"},
    ]},
    "wave_height": {"unit": "m", "min_value": 0, "max_value": 8, "stops": [
        {"offset": 0.0, "color": "#0c2c5c"}, {"offset": 0.4, "color": "#40bebe"},
        {"offset": 0.6, "color": "#f0d66a"}, {"offset": 1.0, "color": "#961a5a"},
    ]},
    "wave_direction": {"unit": "°", "min_value": 0, "max_value": 360, "stops": [
        {"offset": 0.0, "color": "#d73027"}, {"offset": 0.5, "color": "#3cb4c8"},
        {"offset": 1.0, "color": "#d73027"},
    ]},
    "current": {"unit": "m/s", "min_value": 0, "max_value": 2, "stops": [
        {"offset": 0.0, "color": "#deebf7"}, {"offset": 0.5, "color": "#4292c6"},
        {"offset": 1.0, "color": "#084594"},
    ]},
}

ENTRY_ID = "mock_entry_1"
PARAMETERS = [
    {"key": "wind_10m", "name": "Wind (10m)", "unit": "m/s", "colormap": "wind"},
    {"key": "wind_gust_10m", "name": "Windstoten (10m)", "unit": "m/s", "colormap": "wind"},
    {"key": "precipitation", "name": "Neerslag", "unit": "mm", "colormap": "precipitation"},
    {"key": "temperature_2m", "name": "Temperatuur (2m)", "unit": "°C", "colormap": "temperature"},
    {"key": "pressure_msl", "name": "Luchtdruk (zeeniveau)", "unit": "hPa", "colormap": "pressure"},
    {"key": "wave_height", "name": "Golfhoogte (significant)", "unit": "m", "colormap": "wave"},
    {"key": "wave_direction", "name": "Golfrichting", "unit": "°", "colormap": "direction"},
]

# A second source with its own (coarser, 2-hourly) time axis, so the detailed
# meteogram's multi-source layout + union time-axis can be exercised.
PARAMETERS_DWD = [
    {"key": "wind_10m", "name": "Wind (10m)", "unit": "m/s", "colormap": "wind"},
    {"key": "wind_gust_10m", "name": "Windstoten (10m)", "unit": "m/s", "colormap": "wind"},
    {"key": "temperature_2m", "name": "Temperatuur (2m)", "unit": "°C", "colormap": "temperature"},
    {"key": "precipitation", "name": "Neerslag", "unit": "mm", "colormap": "precipitation"},
    {"key": "pressure_msl", "name": "Luchtdruk (zeeniveau)", "unit": "hPa", "colormap": "pressure"},
]

# entry_id -> config. Each entry may carry its own frame_count/step so the shared
# time axis in the detailed meteogram is a genuine union of differing model steps.
ENTRIES = {
    ENTRY_ID: {
        "entry_id": ENTRY_ID,
        "title": "KNMI - HARMONIE-AROME (mock)",
        "source": "knmi",
        "dataset": {
            "key": "harmonie_arome_cy43_p1",
            "name": "HARMONIE-AROME Cy43 - Nederland",
            "bounds": list(BOUNDS),
        },
        "parameters": PARAMETERS,
        "frame_count": FRAME_COUNT,
        "step_hours": FRAME_STEP_HOURS,
    },
    "mock_entry_2": {
        "entry_id": "mock_entry_2",
        "title": "DWD - ICON-EU (mock)",
        "source": "dwd",
        "dataset": {
            "key": "icon_eu",
            "name": "ICON-EU - Europa",
            "bounds": [40.0, -10.0, 62.0, 20.0],
        },
        "parameters": PARAMETERS_DWD,
        "frame_count": 5,
        "step_hours": 2,
    },
    # A source that has frames but no coverage at the test point (mirrors BSH's
    # North-Sea-only grid when clicking inland): `out_of_range` -> null samples,
    # so it is dropped from the table and named in the footer note.
    "mock_entry_3": {
        "entry_id": "mock_entry_3",
        "title": "BSH - Zeestroming Noordzee (mock)",
        "source": "bsh",
        "dataset": {
            "key": "bsh_current_northsea",
            "name": "BSH - Zeestroming Noordzee",
            "bounds": [51.0, -1.0, 57.0, 9.0],
        },
        "parameters": [
            {"key": "current", "name": "Zeestroming (oppervlak)", "unit": "m/s", "colormap": "current"},
        ],
        "frame_count": 4,
        "step_hours": 1,
        "out_of_range": True,
    },
}


def _synth_pressure_field() -> dict:
    """A smooth MSL-pressure grid (hPa) with a low over the NW and a high over the
    SE, north-first, in the field_grid dict shape the card contours into isobars."""
    south, west, north, east = BOUNDS
    nx, ny = 48, 32
    dx = (east - west) / (nx - 1)
    dy = (north - south) / (ny - 1)
    data: list[float] = []
    for j in range(ny):  # row 0 = northernmost
        lat = north - j * dy
        for i in range(nx):
            lon = west + i * dx
            d_low = (lon - 3.0) ** 2 + (lat - 54.0) ** 2
            d_high = (lon - 7.5) ** 2 + (lat - 52.0) ** 2
            # low + high, plus mild mesoscale wiggles so smoothing has an effect
            noise = 1.2 * math.sin(lon * 2.5) * math.cos(lat * 2.2)
            val = 1013.0 - 20.0 * math.exp(-d_low / 6.0) + 17.0 * math.exp(-d_high / 8.0) + noise
            data.append(round(val, 2))
    return {"nx": nx, "ny": ny, "lo1": west, "la1": north, "dx": dx, "dy": dy, "data": data}


def _public_entry(entry: dict) -> dict:
    """The subset of an ENTRIES config that the /entries endpoint exposes."""
    return {k: entry[k] for k in ("entry_id", "title", "source", "dataset", "parameters")}


def _point_payload(entry: dict, parameter_key: str, lat: float) -> dict:
    """A synthetic value series + colour legend for one parameter at a point.

    Mirrors the real point/point_all endpoints so the meteogram/value UI can be
    tested: a smooth series, a per-entry phase shift so the two sources differ,
    and a companion from-direction for wind/waves.
    """
    legend = LEGENDS.get(parameter_key, {})
    lo = legend.get("min_value", 0)
    hi = legend.get("max_value", 20)
    has_dir = parameter_key in ("wind_10m", "wind_gust_10m", "wave_height")
    out_of_range = entry.get("out_of_range", False)  # null samples (point off-grid)
    phase = 0.0 if entry["entry_id"] == ENTRY_ID else 1.1
    series = []
    for i in range(entry["frame_count"]):
        vt = BASE_RUN_TIME + timedelta(hours=i * entry["step_hours"])
        frac = 0.5 + 0.4 * math.sin(i / 2.0 + lat + phase)
        value = None if out_of_range else round(lo + frac * (hi - lo), 1)
        point = {"valid_time": vt.isoformat(), "value": value}
        if has_dir:
            # sweep direction so it crosses the 0/360 wrap (tests the break);
            # give gusts a small offset so wind vs gust direction are distinct.
            offset = 20 if parameter_key == "wind_gust_10m" else 0
            point["direction"] = None if out_of_range else round((300 + i * 25 + offset) % 360, 0)
        series.append(point)
    payload = {"unit": legend.get("unit", ""), "legend": legend, "series": series}
    if has_dir:
        payload["direction_unit"] = "°"
    return payload


def _frame_list(entry: dict, parameter_key: str) -> list[dict]:
    frames = []
    eid = entry["entry_id"]
    for i in range(entry["frame_count"]):
        valid_time = BASE_RUN_TIME + timedelta(hours=i * entry["step_hours"])
        frame_id = f"{parameter_key}_{valid_time:%Y%m%dT%H%M}"
        wind_url = (
            f"/api/grib_overlay/wind/{eid}/{parameter_key}/{frame_id}.json"
            if parameter_key == "wind_10m"
            else None
        )
        frames.append(
            {
                "frame_id": frame_id,
                "valid_time": valid_time.isoformat(),
                "run_time": BASE_RUN_TIME.isoformat(),
                "bounds": entry["dataset"]["bounds"],
                "image_url": f"/api/grib_overlay/frame/{eid}/{parameter_key}/{frame_id}.png",
                "wind_url": wind_url,
                "field_url": f"/api/grib_overlay/field/{eid}/{parameter_key}/{frame_id}.json",
                "legend": LEGENDS[parameter_key],
            }
        )
    return frames


class Handler(BaseHTTPRequestHandler):
    def _json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self.send_response(404)
            self.end_headers()
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        parsed = urlparse(self.path)
        parts = [p for p in parsed.path.split("/") if p]

        if parsed.path == "/dev.html":
            self._file(DEV_DIR / "dev.html", "text/html")
        elif parts[:1] == ["grib_overlay_static"]:
            rel = Path(*parts[1:])
            content_type = "text/css" if rel.suffix == ".css" else "application/javascript"
            self._file(WWW_DIR / rel, content_type)
        elif parsed.path == "/api/grib_overlay/entries":
            self._json({"entries": [_public_entry(e) for e in ENTRIES.values()]})
        elif parts[:2] == ["api", "grib_overlay"] and len(parts) >= 3 and parts[2] == "frames":
            entry_id = parts[3]
            entry = ENTRIES.get(entry_id)
            if entry is None:
                self._json({"error": "unknown entry_id"}, status=404)
                return
            query = parse_qs(parsed.query)
            only_param = query.get("parameter", [None])[0]
            result = {}
            for param in entry["parameters"]:
                if only_param and param["key"] != only_param:
                    continue
                result[param["key"]] = _frame_list(entry, param["key"])
            self._json(result)
        elif parts[:3] == ["api", "grib_overlay", "frame"]:
            # /api/grib_overlay/frame/{entry_id}/{parameter_key}/{frame_id}.png
            parameter_key = parts[4]
            self._file(OUTPUT_DIR / f"{parameter_key}.png", "image/png")
        elif parts[:3] == ["api", "grib_overlay", "wind"]:
            # /api/grib_overlay/wind/{entry_id}/{parameter_key}/{frame_id}.json
            self._file(DEV_DIR / "wind_sample.json", "application/json")
        elif parts[:3] == ["api", "grib_overlay", "field"]:
            # /api/grib_overlay/field/{entry_id}/{parameter_key}/{frame_id}.json
            parameter_key = parts[4]
            if parameter_key == "pressure_msl":
                # Synthetic MSL-pressure field (a low + a high) so the isobars
                # render mode has something to contour in the dev harness.
                self._json(_synth_pressure_field())
            else:
                self._file(DEV_DIR / f"field_{parameter_key}.json", "application/json")
        elif parts[:3] == ["api", "grib_overlay", "point_all"]:
            # /api/grib_overlay/point_all/{entry_id}?lat=&lon=
            entry = ENTRIES.get(parts[3], ENTRIES[ENTRY_ID])
            q = parse_qs(parsed.query)
            lat = float(q.get("lat", [52.0])[0])
            params = {
                p["key"]: _point_payload(entry, p["key"], lat) for p in entry["parameters"]
            }
            self._json({"params": params})
        elif parts[:3] == ["api", "grib_overlay", "point"]:
            # /api/grib_overlay/point/{entry_id}/{parameter_key}?lat=&lon=
            entry = ENTRIES.get(parts[3], ENTRIES[ENTRY_ID])
            q = parse_qs(parsed.query)
            lat = float(q.get("lat", [52.0])[0])
            self._json(_point_payload(entry, parts[4], lat))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt: str, *args) -> None:  # quieter default logging
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Serving mock grib_overlay API + card on http://127.0.0.1:{port}/dev.html")
    server.serve_forever()
