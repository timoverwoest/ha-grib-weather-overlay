"""The diagnostics download: useful enough to debug with, and no keys in it.

A diagnostics file is made to be pasted into a public issue, and the three
KNMI keys are the most sensitive thing this integration holds -- so the
redaction is the part that has to be tested, not just the content.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.grib_overlay.const import (
    CONF_API_KEY,
    CONF_DATASET,
    CONF_NOTIFICATION_API_KEY,
    CONF_OBSERVATIONS_API_KEY,
    CONF_PARAMETERS,
    CONF_SOURCE,
    DOMAIN,
)
from custom_components.grib_overlay.diagnostics import (
    async_get_config_entry_diagnostics,
)
from homeassistant.config_entries import ConfigEntryState

SECRETS = ("open-data-secret", "mqtt-secret", "observations-secret")


def _frame(tmp_path: Path, key: str, hour: int) -> SimpleNamespace:
    return SimpleNamespace(
        valid_time=datetime(2026, 9, 25, hour, tzinfo=UTC),
        wind_path=tmp_path / f"{key}.wind.json",
        field_path=tmp_path / f"{key}.field.json",
    )


@pytest.fixture
def entry(hass, tmp_path: Path) -> MockConfigEntry:
    """An entry with all three keys set and one run on disk."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SOURCE: "knmi",
            CONF_API_KEY: SECRETS[0],
            CONF_DATASET: "harmonie_arome_cy43_p1",
            CONF_PARAMETERS: ["wind_10m", "precipitation"],
            CONF_NOTIFICATION_API_KEY: SECRETS[1],
        },
        options={CONF_OBSERVATIONS_API_KEY: SECRETS[2]},
    )
    entry.add_to_hass(hass)

    storage = tmp_path / "storage"
    run_dir = storage / "HARM43_V1_P1_2026092512"
    run_dir.mkdir(parents=True)
    (run_dir / "wind_10m_20260925T1200.png").write_bytes(b"x" * 1024)

    entry.runtime_data = SimpleNamespace(
        storage_dir=storage,
        current_run="HARM43_V1_P1_2026092512",
        last_update_success=True,
        last_exception=None,
        # precipitation is enabled but decoded to nothing: the case worth seeing.
        frames={"wind_10m": [_frame(tmp_path, "wind_10m", 12)], "precipitation": []},
        source=SimpleNamespace(
            name="KNMI Data Platform",
            supports_push_notifications=True,
            async_stop_notifications=AsyncMock(),
        ),
    )
    entry.mock_state(hass, ConfigEntryState.LOADED)
    return entry


async def test_no_key_appears_anywhere_in_the_output(hass, entry) -> None:
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    dumped = repr(diagnostics)
    for secret in SECRETS:
        assert secret not in dumped, secret
    # Redacted, not dropped: "set but wrong" has to stay distinguishable.
    assert diagnostics["entry"]["data"][CONF_API_KEY]
    assert diagnostics["entry"]["options"][CONF_OBSERVATIONS_API_KEY]


async def test_it_says_which_run_and_which_parameters_came_out_empty(
    hass, entry
) -> None:
    state = (await async_get_config_entry_diagnostics(hass, entry))["state"]
    assert state["current_run"] == "HARM43_V1_P1_2026092512"
    assert state["parameters_without_frames"] == ["precipitation"]
    assert state["frames"]["wind_10m"]["count"] == 1
    assert state["frames"]["wind_10m"]["last_valid_time"] == "2026-09-25T12:00:00+00:00"


async def test_the_cache_size_is_reported_per_run(hass, entry) -> None:
    """A cache that outgrew the disk is the other failure that is invisible."""
    storage = (await async_get_config_entry_diagnostics(hass, entry))["storage"]
    assert storage["exists"] is True
    assert storage["total_bytes"] == 1024
    assert storage["runs"]["HARM43_V1_P1_2026092512"]["files"] == 1


async def test_a_cache_that_is_not_there_yet_is_not_an_error(hass, entry) -> None:
    entry.runtime_data.storage_dir = Path("/nonexistent/grib-overlay")
    storage = (await async_get_config_entry_diagnostics(hass, entry))["storage"]
    assert storage == {"path": "/nonexistent/grib-overlay", "exists": False}
