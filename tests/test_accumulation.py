"""Parameters the provider accumulates, and parameters switched on later.

ICON-D2 delivers precipitation as a total since the run started; the card (and
KNMI) work with the amount per hour. And a parameter enabled in the options
after a run was rendered is not in that run's cache, so the cache must not be
taken as complete.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from custom_components.grib_overlay import grib_decode
from custom_components.grib_overlay.const import (
    CONF_API_KEY,
    CONF_DATASET,
    CONF_PARAMETERS,
    CONF_SOURCE,
    CONF_STORAGE_PATH,
    DOMAIN,
)
from custom_components.grib_overlay.coordinator import (
    GribOverlayCoordinator,
    enabled_parameter_keys,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry

RUN = datetime(2026, 9, 16, 0, tzinfo=timezone.utc)


def _total(hours: int, values: list[float]) -> grib_decode.DecodedField:
    return grib_decode.DecodedField(
        parameter_key="precipitation",
        data=np.array(values, dtype=float),
        lats=np.array([50.0]),
        lons=np.array([4.0, 5.0]),
        valid_time=RUN + timedelta(hours=hours),
        run_time=RUN,
        unit="mm",
    )


def test_totals_become_hourly_amounts() -> None:
    totals: dict = {}
    step = GribOverlayCoordinator._deaccumulate
    assert step(_total(0, [0.0, 0.0]), totals).data.tolist() == [0.0, 0.0]
    assert step(_total(1, [1.0, 2.0]), totals).data.tolist() == [1.0, 2.0]
    assert step(_total(2, [1.5, 2.0]), totals).data.tolist() == pytest.approx([0.5, 0.0])
    # Packing rounding can make a total dip a hair; that is no negative rain.
    assert step(_total(3, [1.4999, 2.0]), totals).data.tolist() == [0.0, 0.0]


def test_a_run_seen_from_its_first_hour_needs_no_earlier_total() -> None:
    assert GribOverlayCoordinator._deaccumulate(_total(1, [0.4, 0.0]), {}).data.tolist() == [0.4, 0.0]


def test_a_later_first_total_is_not_passed_off_as_one_hour() -> None:
    with pytest.raises(grib_decode.GribDecodeError):
        GribOverlayCoordinator._deaccumulate(_total(3, [6.0, 0.0]), {})


def _entry(hass, tmp_path, **options) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SOURCE: "dwd",
            CONF_API_KEY: "",
            CONF_DATASET: "ewam",
            CONF_PARAMETERS: ["wave_height"],
        },
        options={CONF_STORAGE_PATH: str(tmp_path), **options},
    )
    entry.add_to_hass(hass)
    return entry


def _write_cached_run(coordinator: GribOverlayCoordinator, keys: list[str]) -> None:
    run_dir = coordinator.storage_dir / "2026091600"
    run_dir.mkdir(parents=True)
    frames = {}
    for key in keys:
        png = run_dir / f"{key}_20260916T0000.png"
        png.write_bytes(b"png")
        frames[key] = [
            {
                "valid_time": RUN.isoformat(),
                "run_time": RUN.isoformat(),
                "png": png.name,
                "wind": None,
                "field": None,
                "bounds": [30.0, -10.5, 66.0, 42.0],
                "legend": {"unit": "m", "min_value": 0, "max_value": 8, "stops": []},
            }
        ]
    (run_dir / coordinator.MANIFEST_NAME).write_text(
        json.dumps(
            {
                "manifest_version": coordinator.MANIFEST_VERSION,
                "color_scales": "",
                "run_filename": "2026091600",
                "frames": frames,
            }
        )
    )


async def test_options_choice_wins_over_the_setup_choice(hass, tmp_path) -> None:
    entry = _entry(hass, tmp_path)
    assert enabled_parameter_keys(entry) == ["wave_height"]
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_PARAMETERS: ["wave_height", "swell_height"]}
    )
    assert enabled_parameter_keys(entry) == ["wave_height", "swell_height"]


async def test_cache_without_a_newly_enabled_parameter_is_reprocessed(hass, tmp_path) -> None:
    entry = _entry(hass, tmp_path, **{CONF_PARAMETERS: ["wave_height", "swell_height"]})
    coordinator = GribOverlayCoordinator(hass, entry)
    _write_cached_run(coordinator, ["wave_height"])
    assert coordinator._load_cached_frames() == (None, {})


async def test_cache_with_the_enabled_parameters_is_restored(hass, tmp_path) -> None:
    entry = _entry(hass, tmp_path)
    coordinator = GribOverlayCoordinator(hass, entry)
    _write_cached_run(coordinator, ["wave_height"])
    run, frames = coordinator._load_cached_frames()
    assert run == "2026091600"
    assert list(frames) == ["wave_height"]


async def test_a_switched_off_parameter_is_not_offered_from_the_cache(hass, tmp_path) -> None:
    entry = _entry(hass, tmp_path)  # only wave_height enabled
    coordinator = GribOverlayCoordinator(hass, entry)
    _write_cached_run(coordinator, ["wave_height", "swell_height"])
    run, frames = coordinator._load_cached_frames()
    assert run == "2026091600"
    assert list(frames) == ["wave_height"]
