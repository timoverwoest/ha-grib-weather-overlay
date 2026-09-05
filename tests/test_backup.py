"""Backup safety.

Two layers, both covered here:

* nothing the integration writes lives under /config, so a backup's tar of that
  folder can no longer trip over a working file we removed mid-backup (this is
  what actually fixed it -- pausing could not help once a long decode outlasted
  the drain timeout);
* the churn pause is still honoured, for the one-time cleanup of the pre-0.26
  /config cache and for anyone pointing storage_path back into the config folder.
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
    CONF_STORAGE_PATH,
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


async def test_working_files_stay_out_of_the_config_folder(hass) -> None:
    """The real fix: no path the coordinator writes to is inside /config."""
    entry = _make_entry(hass)
    coordinator = GribOverlayCoordinator(hass, entry)

    config_dir = hass.config.path()
    assert not str(coordinator.storage_dir).startswith(config_dir)
    assert not str(coordinator._raw_dir).startswith(config_dir)
    # Scratch space must also sit beside -- not inside -- the entry directory,
    # or the run-retention cleanup could delete an in-flight download.
    assert coordinator.storage_dir not in coordinator._raw_dir.parents


async def test_run_archive_is_downloaded_into_the_scratch_dir(hass, tmp_path) -> None:
    """The ~850MB archive must land in scratch, never in /config or a run dir."""
    entry = _make_entry(hass)
    hass.config_entries.async_update_entry(entry, options={CONF_STORAGE_PATH: str(tmp_path)})
    coordinator = GribOverlayCoordinator(hass, entry)

    destinations = []

    async def _capture(dataset, filename, destination):
        destinations.append(destination)
        return destination

    coordinator.source.async_download_file = _capture
    coordinator._extract_archive = MagicMock(return_value=[])
    coordinator._decode_members = MagicMock(return_value={"wind_10m": []})

    dataset = SimpleNamespace(
        key=entry.data[CONF_DATASET],
        parameters=[SimpleNamespace(key="wind_10m")],
    )
    await coordinator._process_new_run(dataset, "HARM43_V1_P1_2026090219.tar")

    (tar_path,) = destinations
    assert coordinator._raw_dir in tar_path.parents
    assert not str(tar_path).startswith(hass.config.path())
    # And the members are extracted into scratch, not into the run directory.
    _, extract_target = coordinator._extract_archive.call_args[0]
    assert coordinator._raw_dir in extract_target.parents


async def test_scratch_dir_is_cleaned_up_even_when_decoding_fails(hass, tmp_path) -> None:
    """A leaked archive would cost ~850MB on real disk until the next restart."""
    entry = _make_entry(hass)
    hass.config_entries.async_update_entry(entry, options={CONF_STORAGE_PATH: str(tmp_path)})
    coordinator = GribOverlayCoordinator(hass, entry)

    raw_dir = coordinator._raw_dir / "run-A"

    async def _download(dataset, filename, destination):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"archive")
        return destination

    coordinator.source.async_download_file = _download
    coordinator._extract_archive = MagicMock(return_value=[])
    coordinator._decode_members = MagicMock(side_effect=OSError("corrupt member"))

    dataset = SimpleNamespace(
        key=entry.data[CONF_DATASET],
        parameters=[SimpleNamespace(key="wind_10m")],
    )
    with pytest.raises(OSError):
        await coordinator._process_new_run(dataset, "run-A.tar")

    assert not raw_dir.exists()


async def test_stale_scratch_is_dropped_on_setup(hass, tmp_path) -> None:
    """A restart mid-download strands a run archive; setup has to clear it.

    _process_new_run cleans up in a finally, but a shutdown cancels that await
    too (the log shows exactly that: CancelledError at the rmtree during "final
    writes shutdown stage"), so the next start is the only chance.
    """
    entry = _make_entry(hass)
    hass.config_entries.async_update_entry(entry, options={CONF_STORAGE_PATH: str(tmp_path)})
    coordinator = GribOverlayCoordinator(hass, entry)

    stranded = coordinator._raw_dir / "HARM43_V1_P1_2026090500"
    stranded.mkdir(parents=True)
    (stranded / "HARM43_V1_P1_2026090500.tar").write_bytes(b"a stranded 850MB archive")
    # A processed run must survive -- it is the fast-restart cache.
    keep = coordinator.storage_dir / "HARM43_V1_P1_2026090419"
    keep.mkdir(parents=True)
    (keep / "frames.json").write_text("{}")

    await coordinator._async_drop_stale_scratch()

    assert not coordinator._raw_dir.exists()
    assert (keep / "frames.json").exists()


async def test_storage_path_option_overrides_the_default(hass, tmp_path) -> None:
    entry = _make_entry(hass)
    hass.config_entries.async_update_entry(entry, options={CONF_STORAGE_PATH: str(tmp_path)})
    coordinator = GribOverlayCoordinator(hass, entry)
    assert coordinator.storage_dir == tmp_path / entry.entry_id


async def test_legacy_config_cache_is_cleared_on_setup(hass, tmp_path) -> None:
    """Upgrading must actually shrink the backup, not just stop growing it."""
    entry = _make_entry(hass)
    hass.config_entries.async_update_entry(
        entry, options={CONF_STORAGE_PATH: str(tmp_path / "new")}
    )
    coordinator = GribOverlayCoordinator(hass, entry)

    legacy = coordinator._legacy_storage_dir
    legacy.mkdir(parents=True)
    (legacy / "old_run").mkdir()
    (legacy / "old_run" / "wind_10m_20260904T0000.png").write_bytes(b"cached")

    await coordinator._async_migrate_legacy_storage()

    assert not legacy.exists()
    assert coordinator._legacy_migrated is True


async def test_legacy_cache_is_dropped_when_it_cannot_be_moved(hass, tmp_path) -> None:
    """A move isn't always possible (/config and /share are separate mounts).

    Then the old copy is simply discarded -- it is a cache, rebuilt on the next
    run -- rather than left behind to keep bloating every backup.
    """
    entry = _make_entry(hass)
    new_root = tmp_path / "new"
    hass.config_entries.async_update_entry(entry, options={CONF_STORAGE_PATH: str(new_root)})
    coordinator = GribOverlayCoordinator(hass, entry)
    # Destination already populated -> the rename is skipped.
    coordinator.storage_dir.mkdir(parents=True)
    (coordinator.storage_dir / "keep_me").write_text("current cache")

    legacy = coordinator._legacy_storage_dir
    legacy.mkdir(parents=True)
    (legacy / "old_run").mkdir()

    await coordinator._async_migrate_legacy_storage()

    assert not legacy.exists()
    assert (coordinator.storage_dir / "keep_me").read_text() == "current cache"


async def test_legacy_cache_is_left_alone_during_a_backup(hass, tmp_path) -> None:
    entry = _make_entry(hass)
    hass.config_entries.async_update_entry(
        entry, options={CONF_STORAGE_PATH: str(tmp_path / "new")}
    )
    coordinator = GribOverlayCoordinator(hass, entry)
    legacy = coordinator._legacy_storage_dir
    legacy.mkdir(parents=True)

    GribOverlayCoordinator.set_backup_active(True)
    await coordinator._async_migrate_legacy_storage()

    # Deleting hundreds of MB while the backup walks /config is the very race
    # we are fixing -- it has to wait for the next poll instead.
    assert legacy.exists()
    assert coordinator._legacy_migrated is False
