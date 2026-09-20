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
    CONF_FORECAST_HORIZON_HOURS,
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


def _write_cached_run(
    coordinator: GribOverlayCoordinator,
    keys: list[str],
    leads=(0,),
    horizon=None,
    empty: list[str] | None = None,
    record_empty: bool = True,
) -> None:
    run_dir = coordinator.storage_dir / "2026091600"
    run_dir.mkdir(parents=True)
    frames = {}
    for key in keys:
        frames[key] = []
        for lead in leads:
            valid = RUN + timedelta(hours=lead)
            png = run_dir / f"{key}_{valid:%Y%m%dT%H%M}.png"
            png.write_bytes(b"png")
            frames[key].append(
                {
                    "valid_time": valid.isoformat(),
                    "run_time": RUN.isoformat(),
                    "png": png.name,
                    "wind": None,
                    "field": None,
                    "bounds": [30.0, -10.5, 66.0, 42.0],
                    "legend": {"unit": "m", "min_value": 0, "max_value": 8, "stops": []},
                }
            )
    manifest: dict = {
        "manifest_version": coordinator.MANIFEST_VERSION,
        "color_scales": "",
        "run_filename": "2026091600",
        "frames": frames,
    }
    for key in empty or []:
        frames[key] = []  # asked for, but the run held nothing for it
    if record_empty:
        manifest_empty = sorted(key for key, flist in frames.items() if not flist)
        if manifest_empty:
            manifest["empty_parameters"] = manifest_empty
    if horizon is not None:
        manifest["horizon_hours"] = horizon
    (run_dir / coordinator.MANIFEST_NAME).write_text(json.dumps(manifest))


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


async def test_a_run_missing_one_parameter_is_tried_once_more(hass, tmp_path) -> None:
    """A parameter that came out empty gets a second chance, not a permanent hole.

    The run may have been processed while the source was briefly missing that
    field -- or before this record existed at all (an older manifest).
    """
    entry = _entry(hass, tmp_path, **{CONF_PARAMETERS: ["wave_height", "swell_height"]})
    coordinator = GribOverlayCoordinator(hass, entry)
    _write_cached_run(
        coordinator, ["wave_height"], empty=["swell_height"], record_empty=False
    )
    assert coordinator._load_cached_frames() == (None, {})


async def test_a_second_empty_run_is_taken_as_it_is(hass, tmp_path) -> None:
    """Once the manifest records it, the run is not downloaded again and again."""
    entry = _entry(hass, tmp_path, **{CONF_PARAMETERS: ["wave_height", "swell_height"]})
    coordinator = GribOverlayCoordinator(hass, entry)
    _write_cached_run(coordinator, ["wave_height"], empty=["swell_height"])
    run, frames = coordinator._load_cached_frames()
    assert run == "2026091600"
    assert frames["swell_height"] == []


async def test_the_manifest_records_which_parameters_came_out_empty(hass, tmp_path) -> None:
    entry = _entry(hass, tmp_path)
    coordinator = GribOverlayCoordinator(hass, entry)
    run_dir = tmp_path / "run-empty"
    run_dir.mkdir()
    coordinator._write_frames_manifest(run_dir, "2026091600", {"wave_height": []}, 48.0)
    manifest = json.loads((run_dir / coordinator.MANIFEST_NAME).read_text())
    assert manifest["empty_parameters"] == ["wave_height"]


async def test_a_longer_horizon_processes_the_run_again(hass, tmp_path) -> None:
    """Otherwise the card stays at the old length until the next run."""
    entry = _entry(hass, tmp_path, **{CONF_FORECAST_HORIZON_HOURS: 120.0})
    coordinator = GribOverlayCoordinator(hass, entry)
    _write_cached_run(coordinator, ["wave_height"], leads=range(25), horizon=24.0)
    assert coordinator._load_cached_frames() == (None, {})


async def test_a_shorter_horizon_cuts_the_cached_run(hass, tmp_path) -> None:
    entry = _entry(hass, tmp_path, **{CONF_FORECAST_HORIZON_HOURS: 6.0})
    coordinator = GribOverlayCoordinator(hass, entry)
    _write_cached_run(coordinator, ["wave_height"], leads=range(25), horizon=24.0)
    run, frames = coordinator._load_cached_frames()
    assert run == "2026091600"
    assert len(frames["wave_height"]) == 7  # +0 .. +6 h


async def test_a_run_rendered_for_the_same_horizon_is_reused(hass, tmp_path) -> None:
    entry = _entry(hass, tmp_path, **{CONF_FORECAST_HORIZON_HOURS: 24.0})
    coordinator = GribOverlayCoordinator(hass, entry)
    _write_cached_run(coordinator, ["wave_height"], leads=range(25), horizon=24.0)
    assert len(coordinator._load_cached_frames()[1]["wave_height"]) == 25


async def test_the_manifest_records_the_horizon(hass, tmp_path) -> None:
    entry = _entry(hass, tmp_path)
    coordinator = GribOverlayCoordinator(hass, entry)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    coordinator._write_frames_manifest(run_dir, "2026091600", {}, 48.0)
    assert json.loads((run_dir / coordinator.MANIFEST_NAME).read_text())["horizon_hours"] == 48.0
