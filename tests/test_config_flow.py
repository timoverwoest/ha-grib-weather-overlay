"""Exercises the real config flow against a mocked KNMI API."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant

from custom_components.grib_overlay.const import (
    CONF_API_KEY,
    CONF_DATASET,
    CONF_NOTIFICATION_API_KEY,
    CONF_PARAMETERS,
    CONF_SOURCE,
    DOMAIN,
)

FILES_URL = (
    "https://api.dataplatform.knmi.nl/open-data/v1/datasets/"
    "harmonie_arome_cy43_p1/versions/1.0/files"
)


async def test_full_flow_creates_entry(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(
        FILES_URL,
        json={
            "files": [
                {
                    "filename": "HARM43_V1_P1_2026071802.tar",
                    "size": 859852800,
                    "lastModified": "2026-07-18T04:33:39+00:00",
                }
            ]
        },
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SOURCE: "knmi", CONF_API_KEY: "test-key"}
    )
    assert result["step_id"] == "dataset"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DATASET: "harmonie_arome_cy43_p1"}
    )
    assert result["step_id"] == "parameters"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PARAMETERS: ["wind_10m", "precipitation"]}
    )
    assert result["type"] == "create_entry"
    assert result["data"][CONF_DATASET] == "harmonie_arome_cy43_p1"
    assert result["data"][CONF_PARAMETERS] == ["wind_10m", "precipitation"]
    # Notification key not given -> not stored.
    assert CONF_NOTIFICATION_API_KEY not in result["data"]


async def test_optional_notification_key_is_stored(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(
        FILES_URL,
        json={
            "files": [
                {
                    "filename": "HARM43_V1_P1_2026071802.tar",
                    "size": 1,
                    "lastModified": "2026-07-18T04:33:39+00:00",
                }
            ]
        },
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_SOURCE: "knmi",
            CONF_API_KEY: "data-key",
            CONF_NOTIFICATION_API_KEY: "notify-key",
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DATASET: "harmonie_arome_cy43_p1"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PARAMETERS: ["wind_10m"]}
    )
    assert result["type"] == "create_entry"
    assert result["data"][CONF_API_KEY] == "data-key"
    assert result["data"][CONF_NOTIFICATION_API_KEY] == "notify-key"


def test_source_uses_notification_key_for_mqtt() -> None:
    """The notification key (when set) is what MQTT authenticates with."""
    from custom_components.grib_overlay.sources.knmi import KnmiSource

    with_notify = KnmiSource(object(), "data-key", notification_api_key="notify-key")
    assert with_notify._notification_api_key == "notify-key"

    # Falls back to the Open Data key when no notification key is supplied.
    without_notify = KnmiSource(object(), "data-key")
    assert without_notify._notification_api_key == "data-key"


async def test_invalid_auth_shows_error(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(FILES_URL, status=401)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SOURCE: "knmi", CONF_API_KEY: "bad-key"}
    )
    assert result["type"] == "form"
    assert result["errors"] == {"base": "invalid_auth"}


async def test_duplicate_dataset_aborts(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(
        FILES_URL,
        json={
            "files": [
                {
                    "filename": "HARM43_V1_P1_2026071802.tar",
                    "size": 1,
                    "lastModified": "2026-07-18T04:33:39+00:00",
                }
            ]
        },
    )

    async def _run_to_dataset_step():
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        return await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_SOURCE: "knmi", CONF_API_KEY: "test-key"}
        )

    result = await _run_to_dataset_step()
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DATASET: "harmonie_arome_cy43_p1"}
    )
    await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PARAMETERS: ["wind_10m"]}
    )

    result = await _run_to_dataset_step()
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DATASET: "harmonie_arome_cy43_p1"}
    )
    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"
