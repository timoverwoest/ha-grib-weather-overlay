"""A cache folder on a hung NAS share must not hold up Home Assistant.

A call into a hung CIFS share cannot be interrupted: the executor thread stays
blocked, and a start or a stop that waits on it never finishes. These tests
simulate that -- an executor job that blocks until the test lets it go -- and
check that entry setup returns within seconds, that what needs the share runs in
the background, and that a share which does not answer costs one stuck thread,
not one per entry per poll.
"""

from __future__ import annotations

import asyncio
import threading
import time
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.grib_overlay import (
    coordinator as coordinator_module,
    storage_paths,
)
from custom_components.grib_overlay.const import (
    CONF_API_KEY,
    CONF_DATASET,
    CONF_PARAMETERS,
    CONF_SOURCE,
    CONF_STORAGE_PATH,
    DOMAIN,
)
from custom_components.grib_overlay.coordinator import GribOverlayCoordinator
from homeassistant.helpers.update_coordinator import UpdateFailed

# Setup has to come back well inside this, whatever the share is doing.
SETUP_BUDGET_SECONDS = 3.0


class Hang:
    """A blocking call that a test can release, like a share that comes back."""

    def __init__(self, result=None) -> None:
        self.release = threading.Event()
        self.entered = threading.Event()
        self.calls = 0
        self._result = result

    def __call__(self, *args, **kwargs):
        self.calls += 1
        self.entered.set()
        self.release.wait(timeout=20)
        return self._result


@pytest.fixture
def hang():
    """Yield a Hang; always let the thread go so the test run can finish."""
    pending: list[Hang] = []

    def _make(result=None) -> Hang:
        h = Hang(result)
        pending.append(h)
        return h

    yield _make
    for h in pending:
        h.release.set()


def _entry(hass, tmp_path) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SOURCE: "noaa",
            CONF_API_KEY: "",
            CONF_DATASET: "gfs",
            CONF_PARAMETERS: ["wind_10m"],
        },
        options={CONF_STORAGE_PATH: str(tmp_path)},
    )
    entry.add_to_hass(hass)
    return entry


async def _settle(hass) -> None:
    await hass.async_block_till_done()


def _stop_timers(coordinator: GribOverlayCoordinator) -> None:
    coordinator._cancel_storage_timers()
    coordinator._cancel_offset()
    if coordinator._unsub_poll:
        coordinator._unsub_poll()


async def test_setup_returns_while_the_restore_hangs(hass, tmp_path, hang) -> None:
    """The restore blocks on the share; async_setup must not wait for it."""
    restore = hang(result=("run-1", {}))
    coordinator = GribOverlayCoordinator(hass, _entry(hass, tmp_path))

    started = time.monotonic()
    with patch.object(coordinator, "_restore_from_disk", restore):
        await coordinator.async_setup()
        elapsed = time.monotonic() - started

        assert elapsed < SETUP_BUDGET_SECONDS
        # The restore really is stuck in an executor thread meanwhile.
        assert await hass.async_add_executor_job(restore.entered.wait, 5)
        assert coordinator.frames == {}
        assert coordinator._current_run_filename is None

        restore.release.set()
        await coordinator._prepare_task

    assert coordinator._storage_ready is True
    assert coordinator._current_run_filename == "run-1"
    _stop_timers(coordinator)


async def test_a_refresh_does_not_wait_for_a_hung_restore(
    hass, tmp_path, hang, monkeypatch
) -> None:
    """The first refresh gives up on the cache quickly and says why."""
    monkeypatch.setattr(coordinator_module, "STORAGE_WAIT_SECONDS", 0.3)
    restore = hang(result=(None, {}))
    coordinator = GribOverlayCoordinator(hass, _entry(hass, tmp_path))
    coordinator.source.async_list_datasets = AsyncMock(
        return_value=[
            type("D", (), {"key": "gfs", "parameters": []})(),
        ]
    )
    coordinator.source.async_list_files = AsyncMock(
        return_value=[type("F", (), {"filename": "run-A"})()]
    )
    coordinator._process_new_run = AsyncMock()

    started = time.monotonic()
    with (
        patch.object(coordinator, "_restore_from_disk", restore),
        pytest.raises(UpdateFailed, match="not ready"),
    ):
        await coordinator._async_update_data()
    assert time.monotonic() - started < SETUP_BUDGET_SECONDS

    # Nothing was downloaded blind: with the cache unknown, a run could be
    # fetched that is already there, or land in a scratch dir not yet cleared.
    coordinator._process_new_run.assert_not_called()

    restore.release.set()
    await coordinator._prepare_task
    _stop_timers(coordinator)


async def test_a_share_that_does_not_answer_is_not_touched_again(
    hass, tmp_path, hang, monkeypatch, caplog
) -> None:
    """17 entries on one dead share cost one stuck thread, and one warning."""
    monkeypatch.setattr(storage_paths, "PROBE_TIMEOUT", 0.3)
    probe = hang(result=storage_paths.PROBE_OK)
    restore = hang(result=(None, {}))
    coordinators = []
    for _ in range(17):
        coordinators.append(GribOverlayCoordinator(hass, _entry(hass, tmp_path)))

    with (
        patch.object(storage_paths, "_probe_root", probe),
        patch.object(GribOverlayCoordinator, "_restore_from_disk", restore),
    ):
        started = time.monotonic()
        for coordinator in coordinators:
            await coordinator.async_setup()
        # All 17 set up; none waited for the share.
        assert time.monotonic() - started < SETUP_BUDGET_SECONDS

        # Let every restore attempt run into the 0.3 s probe deadline.
        await asyncio.gather(
            *(c._prepare_task for c in coordinators if c._prepare_task)
        )

    assert probe.calls == 1  # one thread on the dead share, not seventeen
    assert restore.calls == 0  # nothing went on to touch the folder itself
    assert all(not c._storage_ready for c in coordinators)
    assert caplog.text.count("not answering") == 1
    assert "keeps starting" in caplog.text
    for coordinator in coordinators:
        assert coordinator._unsub_storage_retry is not None  # tried again later
        _stop_timers(coordinator)


async def test_the_restore_happens_once_the_share_answers(
    hass, tmp_path, hang, monkeypatch
) -> None:
    """A share that was hung and comes back is picked up by the retry."""
    monkeypatch.setattr(storage_paths, "PROBE_TIMEOUT", 0.2)
    monkeypatch.setattr(storage_paths, "PROBE_TTL", 0.0)
    coordinator = GribOverlayCoordinator(hass, _entry(hass, tmp_path))
    probe = hang(result=storage_paths.PROBE_OK)

    with patch.object(storage_paths, "_probe_root", probe):
        await coordinator.async_setup()
        await coordinator._prepare_task
        assert coordinator._storage_ready is False

        probe.release.set()  # the NAS answers
        await hass.async_add_executor_job(time.sleep, 0.1)
        coordinator._unsub_storage_retry()  # the timer fires: do what it does
        coordinator._retry_storage()
        await coordinator._prepare_task

    assert coordinator._storage_ready is True
    _stop_timers(coordinator)


async def test_a_missing_folder_is_not_a_dead_share(hass, tmp_path) -> None:
    """The root is made on first use; only a hang or an I/O error is a problem."""
    status = await storage_paths.async_probe_root(hass, tmp_path / "not-yet")
    assert status == storage_paths.PROBE_OK


async def test_an_io_error_is_reported_not_raised(hass, tmp_path) -> None:
    with patch.object(storage_paths.os, "scandir", side_effect=OSError(5, "I/O")):
        status = await storage_paths.async_probe_root(hass, tmp_path)
    assert status == storage_paths.PROBE_ERROR


async def test_nothing_new_starts_while_home_assistant_stops(
    hass, tmp_path
) -> None:
    coordinator = GribOverlayCoordinator(hass, _entry(hass, tmp_path))
    with (
        patch.object(
            type(hass), "is_stopping", new_callable=lambda: property(lambda s: True)
        ),
        patch.object(storage_paths, "_probe_root") as probe,
        patch.object(coordinator, "_restore_from_disk") as restore,
    ):
        await coordinator._async_prepare_storage()

    probe.assert_not_called()
    restore.assert_not_called()


async def test_unloading_cancels_a_restore_that_is_still_waiting(
    hass, tmp_path, hang
) -> None:
    """The await ends on unload; only the (uninterruptible) thread is left."""
    restore = hang(result=(None, {}))
    coordinator = GribOverlayCoordinator(hass, _entry(hass, tmp_path))
    with patch.object(coordinator, "_restore_from_disk", restore):
        await coordinator.async_setup()
        assert await hass.async_add_executor_job(restore.entered.wait, 5)
        task = coordinator._prepare_task
        coordinator._cancel_storage_timers()
        with pytest.raises(asyncio.CancelledError):
            await task
        restore.release.set()
    _stop_timers(coordinator)


async def test_the_cache_is_measured_late_and_in_the_background(
    hass, tmp_path, monkeypatch
) -> None:
    """Restoring no longer walks the whole share; the size follows afterwards."""
    monkeypatch.setattr(coordinator_module, "CACHE_MEASURE_DELAY_SECONDS", 0.0)
    coordinator = GribOverlayCoordinator(hass, _entry(hass, tmp_path))
    run = coordinator.storage_dir / "run-A"
    run.mkdir(parents=True)
    (run / "wind.png").write_bytes(b"x" * 500)

    with patch.object(
        coordinator, "_measure_cache", wraps=coordinator._measure_cache
    ) as measure:
        await coordinator.async_setup()
        await coordinator._prepare_task
        assert coordinator._storage_ready is True
        measure.assert_not_called()  # not during setup/restore
        assert coordinator.cache_bytes is None

        await asyncio.sleep(0.1)
        await _settle(hass)

    assert coordinator.cache_bytes == 500
    _stop_timers(coordinator)


async def test_a_measurement_that_takes_too_long_is_given_up(
    hass, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(coordinator_module, "CACHE_MEASURE_BUDGET_SECONDS", -1.0)
    coordinator = GribOverlayCoordinator(hass, _entry(hass, tmp_path))
    (coordinator.storage_dir / "run-A").mkdir(parents=True)
    (coordinator.storage_dir / "run-A" / "wind.png").write_bytes(b"x")
    assert coordinator._measure_cache() is None


async def test_entry_setup_returns_while_the_share_hangs(
    hass, tmp_path, hang
) -> None:
    """The real thing: set the entry up through Home Assistant with a hung share."""
    probe = hang(result=storage_paths.PROBE_OK)
    entry = _entry(hass, tmp_path)

    started = time.monotonic()
    with (
        patch.object(storage_paths, "_probe_root", probe),
        patch.object(
            GribOverlayCoordinator,
            "_async_update_data",
            AsyncMock(return_value={"run_filename": None, "dataset": "gfs"}),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        assert time.monotonic() - started < SETUP_BUDGET_SECONDS
        assert entry.runtime_data.frames == {}

        probe.release.set()
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
