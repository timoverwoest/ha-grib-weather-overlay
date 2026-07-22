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
BASE_RUN_TIME = datetime(2026, 7, 18, 2, 0, tzinfo=timezone.utc)

# Mirrors the real colormap stops from render.py so the legend looks right.
LEGENDS = {
    "wind_10m": {"unit": "m/s", "min_value": 0, "max_value": 25, "stops": [
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
}

ENTRY_ID = "mock_entry_1"
PARAMETERS = [
    {"key": "wind_10m", "name": "Wind (10m)", "unit": "m/s", "colormap": "wind"},
    {"key": "precipitation", "name": "Neerslag", "unit": "mm", "colormap": "precipitation"},
    {"key": "temperature_2m", "name": "Temperatuur (2m)", "unit": "°C", "colormap": "temperature"},
]


def _frame_list(parameter_key: str) -> list[dict]:
    frames = []
    for i in range(FRAME_COUNT):
        valid_time = BASE_RUN_TIME + timedelta(hours=i * FRAME_STEP_HOURS)
        frame_id = f"{parameter_key}_{valid_time:%Y%m%dT%H%M}"
        wind_url = (
            f"/api/grib_overlay/wind/{ENTRY_ID}/{parameter_key}/{frame_id}.json"
            if parameter_key == "wind_10m"
            else None
        )
        frames.append(
            {
                "frame_id": frame_id,
                "valid_time": valid_time.isoformat(),
                "run_time": BASE_RUN_TIME.isoformat(),
                "bounds": list(BOUNDS),
                "image_url": f"/api/grib_overlay/frame/{ENTRY_ID}/{parameter_key}/{frame_id}.png",
                "wind_url": wind_url,
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
            self._json(
                {
                    "entries": [
                        {
                            "entry_id": ENTRY_ID,
                            "title": "KNMI - HARMONIE-AROME (mock)",
                            "source": "knmi",
                            "dataset": {
                                "key": "harmonie_arome_cy43_p1",
                                "name": "HARMONIE-AROME Cy43 - Nederland",
                                "bounds": list(BOUNDS),
                            },
                            "parameters": PARAMETERS,
                        }
                    ]
                }
            )
        elif parts[:2] == ["api", "grib_overlay"] and len(parts) >= 3 and parts[2] == "frames":
            entry_id = parts[3]
            query = parse_qs(parsed.query)
            only_param = query.get("parameter", [None])[0]
            result = {}
            for param in PARAMETERS:
                if only_param and param["key"] != only_param:
                    continue
                result[param["key"]] = _frame_list(param["key"])
            self._json(result)
        elif parts[:3] == ["api", "grib_overlay", "frame"]:
            # /api/grib_overlay/frame/{entry_id}/{parameter_key}/{frame_id}.png
            parameter_key = parts[4]
            self._file(OUTPUT_DIR / f"{parameter_key}.png", "image/png")
        elif parts[:3] == ["api", "grib_overlay", "wind"]:
            # /api/grib_overlay/wind/{entry_id}/{parameter_key}/{frame_id}.json
            self._file(DEV_DIR / "wind_sample.json", "application/json")
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
