"""Exercises the real config flow against a mocked KNMI API."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant

from custom_components.grib_overlay.const import (
    CONF_ALIAS,
    CONF_API_KEY,
    CONF_COLOR_SCALES,
    CONF_DATASET,
    CONF_OBSERVATIONS_API_KEY,
    CONF_FORECAST_HORIZON_HOURS,
    CONF_NOTIFICATION_API_KEY,
    CONF_PARAMETERS,
    CONF_RETAIN_RUNS,
    CONF_SOURCE,
    CONF_UPDATE_INTERVAL_MINUTES,
    DOMAIN,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry

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


async def test_options_flow_stores_color_scales(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SOURCE: "knmi",
            CONF_API_KEY: "k",
            CONF_DATASET: "harmonie_arome_cy43_p1",
            CONF_PARAMETERS: ["wind_10m", "temperature_2m"],
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "form" and result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_FORECAST_HORIZON_HOURS: 24,
            CONF_RETAIN_RUNS: 2,
            CONF_UPDATE_INTERVAL_MINUTES: 30,
            CONF_COLOR_SCALES: "wind_10m: 0:#2c7fb8, 20:#bd0026",
        },
    )
    assert result["type"] == "create_entry"
    assert result["data"][CONF_COLOR_SCALES] == "wind_10m: 0:#2c7fb8, 20:#bd0026"


async def test_options_flow_can_clear_color_scales(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SOURCE: "knmi",
            CONF_API_KEY: "k",
            CONF_DATASET: "harmonie_arome_cy43_p1",
            CONF_PARAMETERS: ["wind_10m"],
        },
        options={CONF_COLOR_SCALES: "wind_10m: 0:#2c7fb8, 20:#bd0026"},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_FORECAST_HORIZON_HOURS: 24,
            CONF_RETAIN_RUNS: 2,
            CONF_UPDATE_INTERVAL_MINUTES: 30,
            CONF_COLOR_SCALES: "",  # emptied
        },
    )
    assert result["type"] == "create_entry"
    assert CONF_COLOR_SCALES not in result["data"]


async def test_options_flow_stores_alias(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SOURCE: "knmi",
            CONF_API_KEY: "k",
            CONF_DATASET: "harmonie_arome_cy43_p1",
            CONF_PARAMETERS: ["wind_10m"],
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_FORECAST_HORIZON_HOURS: 24,
            CONF_RETAIN_RUNS: 2,
            CONF_UPDATE_INTERVAL_MINUTES: 30,
            CONF_ALIAS: "  KNMI NL  ",  # stored trimmed
        },
    )
    assert result["type"] == "create_entry"
    assert result["data"][CONF_ALIAS] == "KNMI NL"


async def test_options_flow_can_clear_alias(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SOURCE: "knmi",
            CONF_API_KEY: "k",
            CONF_DATASET: "harmonie_arome_cy43_p1",
            CONF_PARAMETERS: ["wind_10m"],
        },
        options={CONF_ALIAS: "KNMI NL"},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_FORECAST_HORIZON_HOURS: 24,
            CONF_RETAIN_RUNS: 2,
            CONF_UPDATE_INTERVAL_MINUTES: 30,
            CONF_ALIAS: "   ",  # emptied
        },
    )
    assert result["type"] == "create_entry"
    assert CONF_ALIAS not in result["data"]


async def test_options_flow_stores_observations_key(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SOURCE: "knmi",
            CONF_API_KEY: "k",
            CONF_DATASET: "harmonie_arome_cy43_p1",
            CONF_PARAMETERS: ["wind_10m"],
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_FORECAST_HORIZON_HOURS: 24,
            CONF_RETAIN_RUNS: 2,
            CONF_UPDATE_INTERVAL_MINUTES: 30,
            CONF_OBSERVATIONS_API_KEY: "  obs-key  ",
        },
    )
    assert result["type"] == "create_entry"
    assert result["data"][CONF_OBSERVATIONS_API_KEY] == "obs-key"


async def test_options_flow_can_clear_observations_key(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SOURCE: "knmi",
            CONF_API_KEY: "k",
            CONF_DATASET: "harmonie_arome_cy43_p1",
            CONF_PARAMETERS: ["wind_10m"],
        },
        options={CONF_OBSERVATIONS_API_KEY: "obs-key"},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_FORECAST_HORIZON_HOURS: 24,
            CONF_RETAIN_RUNS: 2,
            CONF_UPDATE_INTERVAL_MINUTES: 30,
            CONF_OBSERVATIONS_API_KEY: "",
        },
    )
    assert result["type"] == "create_entry"
    assert CONF_OBSERVATIONS_API_KEY not in result["data"]


def test_source_uses_notification_key_for_mqtt() -> None:
    """The notification key (when set) is what MQTT authenticates with."""
    from custom_components.grib_overlay.sources.knmi import KnmiSource

    with_notify = KnmiSource(object(), "data-key", notification_api_key="notify-key")
    assert with_notify._notification_api_key == "notify-key"

    # Falls back to the Open Data key when no notification key is supplied.
    without_notify = KnmiSource(object(), "data-key")
    assert without_notify._notification_api_key == "data-key"

    # A unique MQTT client id is required by the KNMI broker (a missing one is
    # rejected with CONNACK "Not authorized").
    assert with_notify._mqtt_client_id.startswith("ha-grib-overlay-")
    assert with_notify._mqtt_client_id != without_notify._mqtt_client_id


def test_mqtt_client_id_is_stable_per_instance() -> None:
    """A given instance_id (config entry id) yields a stable client id across
    reloads, so the broker reuses one session instead of piling up new ones."""
    from custom_components.grib_overlay.sources.knmi import KnmiSource

    a = KnmiSource(object(), "k", instance_id="entry-123")
    b = KnmiSource(object(), "k", instance_id="entry-123")
    assert a._mqtt_client_id == b._mqtt_client_id == "ha-grib-overlay-entry-123"
    # Different entries differ; no instance_id falls back to a random unique id.
    assert KnmiSource(object(), "k", instance_id="other")._mqtt_client_id != a._mqtt_client_id
    assert KnmiSource(object(), "k")._mqtt_client_id != KnmiSource(object(), "k")._mqtt_client_id


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


async def _dataset_step(hass: HomeAssistant, aioclient_mock):
    """Walk the flow to the dataset step and return that form."""
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
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SOURCE: "knmi", CONF_API_KEY: "test-key"}
    )


def _choices(result, key):
    """The {value: label} mapping voluptuous offers for `key` in this form."""
    for marker, validator in result["data_schema"].schema.items():
        if marker == key:
            return getattr(validator, "container", None) or validator.options
    raise AssertionError(f"{key} not in the form")


async def test_dataset_and_parameter_labels_follow_the_instance_language(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """These names come from the provider at runtime, so Home Assistant's own
    translation files can't reach them -- the flow translates them itself."""
    hass.config.language = "en"
    result = await _dataset_step(hass, aioclient_mock)
    assert "Netherlands" in _choices(result, CONF_DATASET)["harmonie_arome_cy43_p1"]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DATASET: "harmonie_arome_cy43_p1"}
    )
    assert _choices(result, CONF_PARAMETERS)["wind_10m"].startswith("Wind (10 m)")


async def test_dutch_keeps_the_source_supplied_names(
    hass: HomeAssistant, aioclient_mock
) -> None:
    hass.config.language = "nl"
    result = await _dataset_step(hass, aioclient_mock)
    assert "Nederland" in _choices(result, CONF_DATASET)["harmonie_arome_cy43_p1"]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DATASET: "harmonie_arome_cy43_p1"}
    )
    assert _choices(result, CONF_PARAMETERS)["wind_10m"].startswith("Wind (10m)")
