"""Coordinator <-> source push-notification wiring, with the source mocked.

The real MQTT connection to KNMI's broker is exercised manually via
dev/verify_knmi_mqtt.py (needs a real registered API key); these tests only
verify the coordinator wires things up correctly and reacts sensibly to a
notification, independent of any real network/MQTT library behavior.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

from custom_components.grib_overlay.const import CONF_API_KEY, CONF_DATASET, CONF_PARAMETERS, CONF_SOURCE, DOMAIN
from custom_components.grib_overlay.coordinator import GribOverlayCoordinator
from pytest_homeassistant_custom_component.common import MockConfigEntry


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


async def test_async_setup_starts_push_notifications_for_the_right_dataset(hass) -> None:
    entry = _make_entry(hass)
    coordinator = GribOverlayCoordinator(hass, entry)
    coordinator.source.async_start_notifications = AsyncMock()

    await coordinator._async_start_notifications()

    coordinator.source.async_start_notifications.assert_awaited_once()
    dataset_arg, callback_arg = coordinator.source.async_start_notifications.call_args.args
    assert dataset_arg.key == "harmonie_arome_cy43_p1"
    assert callback_arg == coordinator._on_new_file_notified


async def test_setup_skipped_when_source_does_not_support_push(hass) -> None:
    entry = _make_entry(hass)
    coordinator = GribOverlayCoordinator(hass, entry)
    coordinator.source.supports_push_notifications = False
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
