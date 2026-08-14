"""Backup-safety: file churn is paused while Home Assistant makes a backup.

The integration downloads and deletes GRIB working files under /config; if a
file vanishes between the backup's file listing and the tar write the whole
backup aborts with FileNotFoundError. These tests verify the coordinator defers
run processing while a backup is in progress and that the backup platform hooks
toggle that state (draining any in-flight run first) without ever raising.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.grib_overlay import backup as backup_platform
from custom_components.grib_overlay.backup import async_post_backup, async_pre_backup
from custom_components.grib_overlay.const import (
    CONF_API_KEY,
    CONF_DATASET,
    CONF_PARAMETERS,
    CONF_SOURCE,
    DOMAIN,
)
from custom_components.grib_overlay.coordinator import GribOverlayCoordinator
from pytest_homeassistant_custom_component.common import MockConfigEntry


@pytest.fixture(autouse=True)
def _reset_backup_flag():
    """The backup flag is class-level state; keep tests isolated from each other."""
    GribOverlayCoordinator.set_backup_active(False)
    yield
    GribOverlayCoordinator.set_backup_active(False)


def _make_entry(hass) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SOURCE: "knmi",
            CONF_API_KEY: "test-key",
            CONF_DATASET: "harmonie_arome_cy43_p1",
            CONF_PARAMETERS: ["wind_10m"],
        },
    )
    entry.add_to_hass(hass)
    return entry


def _stub_source_with_new_run(coordinator: GribOverlayCoordinator) -> None:
    dataset = SimpleNamespace(key=coordinator.entry.data[CONF_DATASET], parameters=[])
    coordinator.source.async_list_datasets = AsyncMock(return_value=[dataset])
    coordinator.source.async_list_files = AsyncMock(
        return_value=[SimpleNamespace(filename="run-A")]
    )
    coordinator._process_new_run = AsyncMock()
    coordinator._cleanup_old_runs = MagicMock()


def test_backup_flag_toggles_and_auto_expires() -> None:
    GribOverlayCoordinator.set_backup_active(True)
    assert GribOverlayCoordinator.backup_in_progress() is True

    # If async_post_backup never fires (crashed backup), the pause must not last
    # forever -- it expires after _BACKUP_MAX_SECONDS.
    GribOverlayCoordinator._backup_since -= GribOverlayCoordinator._BACKUP_MAX_SECONDS + 1
    assert GribOverlayCoordinator.backup_in_progress() is False


async def test_update_defers_new_run_while_backup_active(hass) -> None:
    entry = _make_entry(hass)
    coordinator = GribOverlayCoordinator(hass, entry)
    _stub_source_with_new_run(coordinator)

    GribOverlayCoordinator.set_backup_active(True)
    data = await coordinator._async_update_data()

    coordinator._process_new_run.assert_not_awaited()
    assert coordinator._current_run_filename is None
    assert data["run_filename"] is None


async def test_update_processes_new_run_after_backup(hass) -> None:
    entry = _make_entry(hass)
    coordinator = GribOverlayCoordinator(hass, entry)
    _stub_source_with_new_run(coordinator)

    # A backup ran, then finished: the deferred run is picked up on the next poll.
    GribOverlayCoordinator.set_backup_active(True)
    await coordinator._async_update_data()
    GribOverlayCoordinator.set_backup_active(False)
    data = await coordinator._async_update_data()

    coordinator._process_new_run.assert_awaited_once()
    assert coordinator._current_run_filename == "run-A"
    assert data["run_filename"] == "run-A"


async def test_platform_hooks_toggle_backup_state(hass) -> None:
    entry = _make_entry(hass)
    coordinator = GribOverlayCoordinator(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await async_pre_backup(hass)
    assert GribOverlayCoordinator.backup_in_progress() is True

    await async_post_backup(hass)
    assert GribOverlayCoordinator.backup_in_progress() is False


async def test_pre_backup_does_not_block_on_in_flight_run(hass, monkeypatch) -> None:
    entry = _make_entry(hass)
    coordinator = GribOverlayCoordinator(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Simulate a run being processed (lock held). pre_backup must still return
    # promptly (flag set) rather than hang or raise waiting for the drain.
    monkeypatch.setattr(backup_platform, "_DRAIN_TIMEOUT", 0.05)
    await coordinator._process_lock.acquire()
    try:
        await async_pre_backup(hass)
        assert GribOverlayCoordinator.backup_in_progress() is True
    finally:
        coordinator._process_lock.release()
