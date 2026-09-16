"""Which direction goes with which height in the point series.

EWAM now offers three wave families (total, swell, wind waves), each with its
own direction. The point API used to attach the first direction parameter it
found to every scalar -- which would give swell the total-wave direction.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np

from custom_components.grib_overlay import field_grid, render
from custom_components.grib_overlay.coordinator import Frame
from custom_components.grib_overlay.http import _point_payload
from custom_components.grib_overlay.sources.base import direction_key_for

T = datetime(2026, 9, 16, 6, tzinfo=timezone.utc)


def test_direction_key_follows_the_family_prefix() -> None:
    assert direction_key_for("wave_height") == "wave_direction"
    assert direction_key_for("wave_period") == "wave_direction"
    assert direction_key_for("swell_peak_period") == "swell_direction"
    assert direction_key_for("wind_wave_height") == "wind_wave_direction"
    # Not a family member: wind carries its direction as u/v, current too.
    assert direction_key_for("wind_10m") is None
    assert direction_key_for("current") is None
    assert direction_key_for("swell_direction") is None


def _frame(tmp_path, key: str, unit: str, value: float) -> Frame:
    lats, lons = np.array([50.0, 51.0]), np.array([3.0, 4.0])
    path = tmp_path / f"{key}.field.json"
    path.write_text(json.dumps(field_grid.build_field(np.full((2, 2), value), lats, lons)))
    return Frame(
        parameter_key=key,
        valid_time=T,
        run_time=T,
        png_path=tmp_path / f"{key}.png",
        bounds=(50.0, 3.0, 51.0, 4.0),
        legend=render.Legend(unit=unit, min_value=0, max_value=1, stops=()),
        field_path=path,
    )


def test_each_height_gets_its_own_familys_direction(tmp_path) -> None:
    coordinator = SimpleNamespace(
        frames={
            "wave_direction": [_frame(tmp_path, "wave_direction", "°", 270.0)],
            "wave_height": [_frame(tmp_path, "wave_height", "m", 2.0)],
            "swell_height": [_frame(tmp_path, "swell_height", "m", 1.0)],
            "swell_direction": [_frame(tmp_path, "swell_direction", "°", 90.0)],
        }
    )
    swell = _point_payload(coordinator, "swell_height", 50.5, 3.5)
    assert swell["series"][0] == {"valid_time": T.isoformat(), "value": 1.0, "direction": 90.0}
    assert swell["direction_unit"] == "°"
    wave = _point_payload(coordinator, "wave_height", 50.5, 3.5)
    assert wave["series"][0]["direction"] == 270.0


def test_no_borrowed_direction_when_the_family_has_none(tmp_path) -> None:
    coordinator = SimpleNamespace(
        frames={
            "wave_direction": [_frame(tmp_path, "wave_direction", "°", 270.0)],
            "swell_height": [_frame(tmp_path, "swell_height", "m", 1.0)],
        }
    )
    payload = _point_payload(coordinator, "swell_height", 50.5, 3.5)
    assert "direction" not in payload["series"][0]
    assert "direction_unit" not in payload
