"""Coordinator <-> source push-notification wiring, with the source mocked.

The real MQTT connection to KNMI's broker is exercised manually via
dev/verify_knmi_mqtt.py (needs a real registered API key); these tests only
verify the coordinator wires things up correctly and reacts sensibly to a
notification, independent of any real network/MQTT library behavior.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

from custom_components.grib_overlay.const import (
    CONF_API_KEY,
    CONF_DATASET,
    CONF_NOTIFICATION_API_KEY,
    CONF_PARAMETERS,
    CONF_SOURCE,
    DOMAIN,
)
from custom_components.grib_overlay.coordinator import GribOverlayCoordinator
from pytest_homeassistant_custom_component.common import MockConfigEntry


def _make_entry(hass, notification_key: str | None = "notify-key") -> MockConfigEntry:
    """An entry with a Notification Service key, since without one KNMI's push
    channel is (correctly) never attempted."""
    data = {
        CONF_SOURCE: "knmi",
        CONF_API_KEY: "test-key",
        CONF_DATASET: "harmonie_arome_cy43_p1",
        CONF_PARAMETERS: ["wind_10m"],
    }
    if notification_key:
        data[CONF_NOTIFICATION_API_KEY] = notification_key
    entry = MockConfigEntry(domain=DOMAIN, data=data)
    entry.add_to_hass(hass)
    return entry


async def test_async_setup_starts_push_notifications_for_the_right_dataset(hass) -> None:
    entry = _make_entry(hass)
    coordinator = GribOverlayCoordinator(hass, entry)
    coordinator.source.async_start_notifications = AsyncMock()

    await coordinator._async_start_notifications()

    coordinator.source.async_start_notifications.assert_awaited_once()
    dataset_arg, callback_arg = coordinator.source.async_start_notifications.call_args.args
    assert dataset_arg.key == "harmonie_arome_cy43_p1"
    assert callback_arg == coordinator._on_new_file_notified


async def test_setup_skipped_without_a_notification_service_key(hass) -> None:
    """No Notification Service key -> no MQTT attempt at all.

    Connecting anyway with the Open Data key is a guaranteed CONNACK "Not
    authorized", i.e. a warning in the log on every single startup.
    """
    entry = _make_entry(hass, notification_key=None)
    coordinator = GribOverlayCoordinator(hass, entry)
    assert coordinator.source.supports_push_notifications is False
    coordinator.source.async_start_notifications = AsyncMock()

    await coordinator._async_start_notifications()

    coordinator.source.async_start_notifications.assert_not_awaited()


async def test_notification_for_new_run_triggers_a_refresh(hass) -> None:
    entry = _make_entry(hass)
    coordinator = GribOverlayCoordinator(hass, entry)
    coordinator._current_run_filename = "HARM43_V1_P1_2026071802.tar"
    coordinator.async_request_refresh = AsyncMock()

    coordinator._on_new_file_notified("HARM43_V1_P1_2026071803.tar")
    await hass.async_block_till_done()

    coordinator.async_request_refresh.assert_awaited_once()


async def test_notification_for_already_processed_run_is_ignored(hass) -> None:
    entry = _make_entry(hass)
    coordinator = GribOverlayCoordinator(hass, entry)
    coordinator._current_run_filename = "HARM43_V1_P1_2026071802.tar"
    coordinator.async_request_refresh = AsyncMock()

    coordinator._on_new_file_notified("HARM43_V1_P1_2026071802.tar")
    await hass.async_block_till_done()

    coordinator.async_request_refresh.assert_not_awaited()


async def test_unload_stops_notifications(hass) -> None:
    entry = _make_entry(hass)
    coordinator = GribOverlayCoordinator(hass, entry)
    coordinator.source.async_stop_notifications = AsyncMock()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    from custom_components.grib_overlay import async_unload_entry

    await async_unload_entry(hass, entry)

    coordinator.source.async_stop_notifications.assert_awaited_once()


async def test_rejected_api_key_warns_once_and_re_arms(hass, caplog) -> None:
    """A bad key fails every poll; without this the log says only "Error
    fetching ... data" and never which of KNMI's three keys is wrong."""
    from custom_components.grib_overlay.sources.base import GribSourceAuthError
    from homeassistant.helpers.update_coordinator import UpdateFailed
    from types import SimpleNamespace
    import pytest

    entry = _make_entry(hass)
    coordinator = GribOverlayCoordinator(hass, entry)
    coordinator.source.async_list_datasets = AsyncMock(
        side_effect=GribSourceAuthError("KNMI API rejected the API key (HTTP 403)", status=403)
    )

    for _ in range(3):
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()

    warnings = [r for r in caplog.records if r.levelname == "WARNING" and "API key was rejected" in r.message]
    assert len(warnings) == 1, "the same rejection must not be logged every poll"
    text = warnings[0].getMessage()
    assert "harmonie_arome_cy43_p1" in text  # 403 -> names the dataset it lacks access to
    assert "NOT authorised" in text
    assert "THREE separate keys" in text  # points at the right key of the three

    # A key that starts working again is reported, and re-arms the warning.
    caplog.clear()
    dataset = SimpleNamespace(key=entry.data[CONF_DATASET], parameters=[])
    coordinator.source.async_list_datasets = AsyncMock(return_value=[dataset])
    coordinator.source.async_list_files = AsyncMock(return_value=[])
    with pytest.raises(UpdateFailed):  # no files, but auth succeeded
        await coordinator._async_update_data()
    assert any("accepted again" in r.getMessage() for r in caplog.records)
    assert coordinator._auth_warned is False


async def test_unrecognised_key_gets_different_advice_than_unauthorised(hass, caplog) -> None:
    from custom_components.grib_overlay.sources.base import GribSourceAuthError
    from homeassistant.helpers.update_coordinator import UpdateFailed
    import pytest

    entry = _make_entry(hass)
    coordinator = GribOverlayCoordinator(hass, entry)
    coordinator.source.async_list_datasets = AsyncMock(
        side_effect=GribSourceAuthError("KNMI API rejected the API key (HTTP 401)", status=401)
    )
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()

    text = next(r.getMessage() for r in caplog.records if "API key was rejected" in r.getMessage())
    assert "not recognised at all" in text
    assert "expire or be revoked" in text


async def test_refreshes_run_as_entry_background_tasks(hass) -> None:
    """A plain hass task is only cancelled in the "final writes" shutdown stage.

    Decoding a run takes minutes, so a restart mid-run then reliably logged a
    CancelledError traceback. Tying the refresh to the config entry means it is
    cancelled quietly at unload instead.
    """
    from unittest.mock import patch

    entry = _make_entry(hass)
    coordinator = GribOverlayCoordinator(hass, entry)
    coordinator.async_request_refresh = AsyncMock()

    with patch.object(
        type(entry), "async_create_background_task", autospec=True
    ) as background, patch.object(hass, "async_create_task") as plain:
        coordinator._scheduled_poll(None)
        coordinator._on_new_file_notified("HARM43_V1_P1_2026090512.tar")

    assert background.call_count == 2, "both the poll and the push must use it"
    plain.assert_not_called()
    # The task names carry the entry id, so several entries stay tellable apart.
    names = [c.args[3] for c in background.call_args_list]
    assert names == [f"{DOMAIN}-poll-{entry.entry_id}", f"{DOMAIN}-push-{entry.entry_id}"]

    # Close the coroutines the mock never awaited.
    for call in background.call_args_list:
        call.args[2].close()
