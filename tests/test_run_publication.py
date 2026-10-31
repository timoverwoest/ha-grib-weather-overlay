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
from pytest_homeassistant_custom_component.common import MockConfigEntry

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
from homeassistant.helpers.update_coordinator import UpdateFailed


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


def _runs(*names: str) -> AsyncMock:
    return AsyncMock(return_value=[SimpleNamespace(filename=n) for n in names])


async def test_with_nothing_cached_an_older_complete_run_fills_the_map(hass) -> None:
    """A cache that just moved (or a first start) need not stay empty for hours."""
    coordinator = _coordinator(hass)
    coordinator.source.async_list_files = _runs(
        "2026092512", "2026092506", "2026092500"
    )
    newest_incomplete = GribRunIncompleteError(
        "not complete yet: +168 h is not published"
    )

    async def _process(dataset, filename):
        if filename == "2026092512":
            raise newest_incomplete

    coordinator._process_new_run = AsyncMock(side_effect=_process)

    data = await coordinator._async_update_data()

    assert data["run_filename"] == "2026092506"
    assert [c.args[1] for c in coordinator._process_new_run.await_args_list] == [
        "2026092512",
        "2026092506",
    ]
    _, kwargs = coordinator.source.async_list_files.await_args
    assert kwargs["max_keys"] == 3
    coordinator._cleanup_old_runs.assert_called_once()


async def test_after_the_fallback_the_newest_run_is_taken_once_complete(hass) -> None:
    coordinator = _coordinator(hass)
    coordinator._current_run_filename = "2026092506"  # what the fallback took
    coordinator.source.async_list_files = _runs("2026092512")
    coordinator._process_new_run = AsyncMock()

    data = await coordinator._async_update_data()

    assert data["run_filename"] == "2026092512"
    # With a run cached only the newest is asked for: no extra probes per poll.
    _, kwargs = coordinator.source.async_list_files.await_args
    assert kwargs["max_keys"] == 1


async def test_when_no_listed_run_is_complete_it_says_why(hass) -> None:
    coordinator = _coordinator(
        hass, raises=GribRunIncompleteError("not complete yet: +168 h is not published")
    )
    coordinator.source.async_list_files = _runs("2026092512", "2026092506")

    with pytest.raises(UpdateFailed, match="not complete"):
        await coordinator._async_update_data()
    assert coordinator._process_new_run.await_count == 2
    assert coordinator._current_run_filename is None
