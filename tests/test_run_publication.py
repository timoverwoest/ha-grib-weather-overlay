"""What the coordinator does with a run the provider is still publishing.

Every centre writes a run out lead time by lead time, so for the first hours of
its life a run exists but is not yet downloadable to a long horizon. Treating
that as a failure put a red line in the log at every single run -- twice a day
per GFS entry, four times over -- followed by a "recovered" half an hour later.
It is not a failure: it is the run arriving. The coordinator stays on the run it
already has and looks again at the next poll.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.grib_overlay.const import (
    CONF_API_KEY,
    CONF_DATASET,
    CONF_PARAMETERS,
    CONF_SOURCE,
    DOMAIN,
)
from custom_components.grib_overlay.coordinator import GribOverlayCoordinator
from custom_components.grib_overlay.sources.base import (
    GribRunIncompleteError,
    GribSourceError,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry


def _coordinator(hass, *, raises: Exception | None = None) -> GribOverlayCoordinator:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SOURCE: "noaa",
            CONF_API_KEY: "",
            CONF_DATASET: "gfs",
            CONF_PARAMETERS: ["wind_10m"],
        },
    )
    entry.add_to_hass(hass)
    coordinator = GribOverlayCoordinator(hass, entry)
    dataset = SimpleNamespace(key="gfs", parameters=[])
    coordinator.source.async_list_datasets = AsyncMock(return_value=[dataset])
    coordinator.source.async_list_files = AsyncMock(
        return_value=[SimpleNamespace(filename="2026092512")]
    )
    coordinator._process_new_run = AsyncMock(side_effect=raises)
    coordinator._cleanup_old_runs = MagicMock()
    return coordinator


async def test_a_run_still_publishing_keeps_the_one_we_have(hass) -> None:
    coordinator = _coordinator(
        hass,
        raises=GribRunIncompleteError(
            "GFS run 2026092512 is not complete yet: +57 h is not published"
        ),
    )
    coordinator._current_run_filename = "2026092506"

    data = await coordinator._async_update_data()

    assert data["run_filename"] == "2026092506"
    # Not adopted: the next poll has to try this run again, not skip past it.
    assert coordinator._current_run_filename == "2026092506"
    coordinator._cleanup_old_runs.assert_not_called()


async def test_the_next_poll_picks_the_run_up_once_it_is_finished(hass) -> None:
    coordinator = _coordinator(
        hass, raises=GribRunIncompleteError("not complete yet: +57 h is not published")
    )
    coordinator._current_run_filename = "2026092506"
    await coordinator._async_update_data()

    coordinator._process_new_run = AsyncMock()
    data = await coordinator._async_update_data()

    assert data["run_filename"] == "2026092512"
    coordinator._cleanup_old_runs.assert_called_once()


async def test_with_no_run_at_all_it_still_says_why(hass) -> None:
    """Nothing to fall back on: an entry sitting empty has to explain itself."""
    coordinator = _coordinator(
        hass, raises=GribRunIncompleteError("not complete yet: +57 h is not published")
    )
    with pytest.raises(UpdateFailed, match="not complete"):
        await coordinator._async_update_data()


async def test_a_genuine_source_error_still_fails(hass) -> None:
    coordinator = _coordinator(hass, raises=GribSourceError("NOMADS returned HTTP 500"))
    coordinator._current_run_filename = "2026092506"
    with pytest.raises(UpdateFailed, match="HTTP 500"):
        await coordinator._async_update_data()
