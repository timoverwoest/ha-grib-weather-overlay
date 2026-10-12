"""The sensors: what they report, and when they refuse to go unavailable.

These are the only entities this integration publishes, so they are the only
way an automation can notice that an entry has gone stale -- which makes their
availability rule the part worth pinning down.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.grib_overlay.const import (
    CONF_API_KEY,
    CONF_DATASET,
    CONF_PARAMETERS,
    CONF_SOURCE,
    CONF_UPDATE_INTERVAL_MINUTES,
    DOMAIN,
)
from custom_components.grib_overlay.coordinator import GribOverlayCoordinator
from custom_components.grib_overlay.sensor import SENSORS, async_setup_entry

RUN = datetime(2026, 9, 25, 12, tzinfo=UTC)


def _frame(hours: int) -> SimpleNamespace:
    return SimpleNamespace(run_time=RUN, valid_time=RUN + timedelta(hours=hours))


def _entry(hass, **options) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SOURCE: "knmi",
            CONF_API_KEY: "k",
            CONF_DATASET: "harmonie_arome_cy43_p1",
            CONF_PARAMETERS: ["wind_10m"],
        },
        options=options,
        title="HARMONIE-AROME",
    )
    entry.add_to_hass(hass)
    return entry


def _coordinator(entry, *, frames=None, cache_bytes=2_097_152, ok=True):
    return SimpleNamespace(
        entry=entry,
        frames=frames if frames is not None else {},
        cache_bytes=cache_bytes,
        last_update_success=ok,
        source=SimpleNamespace(
            name="KNMI Data Platform", async_stop_notifications=AsyncMock()
        ),
        async_add_listener=lambda *args, **kwargs: lambda: None,
    )


async def _entities(hass, coordinator) -> dict[str, object]:
    """Run the platform's setup and return its entities by description key."""
    added: list = []
    entry = coordinator.entry
    entry.runtime_data = coordinator
    await async_setup_entry(hass, entry, lambda new, *_args, **_kw: added.extend(new))
    return {e.entity_description.key: e for e in added}


async def test_every_sensor_reports_what_the_run_holds(hass) -> None:
    frames = {"wind_10m": [_frame(0), _frame(1)], "precipitation": [_frame(0)]}
    sensors = await _entities(hass, _coordinator(_entry(hass), frames=frames))

    assert sensors["run_time"].native_value == RUN
    assert sensors["forecast_until"].native_value == RUN + timedelta(hours=1)
    assert sensors["frames"].native_value == 3
    assert sensors["cache_size"].native_value == 2_097_152


async def test_an_entry_with_nothing_cached_reports_nothing_not_zero(hass) -> None:
    """A timestamp of "now" would look like fresh data; None reads as unknown."""
    sensors = await _entities(
        hass, _coordinator(_entry(hass), frames={}, cache_bytes=None)
    )
    assert sensors["run_time"].native_value is None
    assert sensors["forecast_until"].native_value is None
    assert sensors["cache_size"].native_value is None
    assert sensors["frames"].native_value == 0


async def test_a_failed_poll_does_not_hide_how_old_the_data_is(hass) -> None:
    """The cards keep showing the previous run when a provider is down, so the
    sensor that says how old that run is has to keep answering.
    """
    frames = {"wind_10m": [_frame(0)]}
    sensors = await _entities(hass, _coordinator(_entry(hass), frames=frames, ok=False))
    assert sensors["run_time"].available is True
    assert sensors["run_time"].native_value == RUN


async def test_with_no_data_and_a_failed_poll_it_is_unavailable(hass) -> None:
    sensors = await _entities(hass, _coordinator(_entry(hass), frames={}, ok=False))
    assert sensors["run_time"].available is False


async def test_all_four_group_under_one_service_device(hass) -> None:
    entry = _entry(hass)
    sensors = await _entities(hass, _coordinator(entry))
    assert len(sensors) == len(SENSORS)
    for key, sensor in sensors.items():
        assert sensor.unique_id == f"{entry.entry_id}_{key}"
        assert sensor.device_info["identifiers"] == {(DOMAIN, entry.entry_id)}
        assert sensor.device_info["manufacturer"] == "KNMI Data Platform"
        assert sensor.device_info["model"] == "harmonie_arome_cy43_p1"


@pytest.mark.parametrize("minutes", [5, 30, 180])
async def test_an_entity_cannot_start_a_second_poll_timer(hass, minutes: int) -> None:
    """DataUpdateCoordinator schedules its own refresh as soon as the first
    entity subscribes. This coordinator drives polling itself, offset per entry
    so a dozen sources do not hit their providers on the same second -- so its
    update_interval has to stay unset or every entry would poll twice.
    """
    entry = _entry(hass, **{CONF_UPDATE_INTERVAL_MINUTES: minutes})
    coordinator = GribOverlayCoordinator(hass, entry)
    assert coordinator.update_interval is None
    assert coordinator.poll_interval == timedelta(minutes=minutes)


async def test_the_cache_measurement_counts_the_run_directories(
    hass, tmp_path: Path
) -> None:
    entry = _entry(hass)
    coordinator = GribOverlayCoordinator(hass, entry)
    coordinator.storage_dir = tmp_path / "storage"
    (coordinator.storage_dir / "run-A").mkdir(parents=True)
    (coordinator.storage_dir / "run-A" / "wind.png").write_bytes(b"x" * 500)
    (coordinator.storage_dir / "run-B").mkdir()
    (coordinator.storage_dir / "run-B" / "wind.png").write_bytes(b"x" * 300)
    assert coordinator._measure_cache() == 800


async def test_a_cache_that_does_not_exist_measures_as_unknown(hass) -> None:
    coordinator = GribOverlayCoordinator(hass, _entry(hass))
    coordinator.storage_dir = Path("/nonexistent/grib-overlay")
    assert coordinator._measure_cache() is None
