"""Config flow: pick a source, a dataset, and which parameters to enable."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_API_KEY,
    CONF_DATASET,
    CONF_FORECAST_HORIZON_HOURS,
    CONF_PARAMETERS,
    CONF_RETAIN_RUNS,
    CONF_SOURCE,
    CONF_UPDATE_INTERVAL_MINUTES,
    DEFAULT_FORECAST_HORIZON_HOURS,
    DEFAULT_RETAIN_RUNS,
    DEFAULT_UPDATE_INTERVAL_MINUTES,
    DOMAIN,
)
from .sources.base import GribDatasetInfo, GribSourceAuthError, GribSourceError
from .sources.registry import SOURCE_REGISTRY, get_source_class

_LOGGER = logging.getLogger(__name__)


class GribOverlayConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handles: pick source + API key -> pick dataset -> pick parameters."""

    VERSION = 1

    def __init__(self) -> None:
        self._source_key: str | None = None
        self._api_key: str | None = None
        self._datasets: list[GribDatasetInfo] = []
        self._dataset: GribDatasetInfo | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            source_key = user_input[CONF_SOURCE]
            api_key = user_input[CONF_API_KEY]
            source_cls = get_source_class(source_key)
            session = async_get_clientsession(self.hass)
            source = source_cls(session, api_key)
            try:
                datasets = await source.async_list_datasets()
                if datasets:
                    # Cheap auth check: list a handful of files for the first dataset.
                    await source.async_list_files(datasets[0], max_keys=1)
            except GribSourceAuthError:
                errors["base"] = "invalid_auth"
            except GribSourceError:
                errors["base"] = "cannot_connect"
            else:
                self._source_key = source_key
                self._api_key = api_key
                self._datasets = datasets
                return await self.async_step_dataset()

        schema = vol.Schema(
            {
                vol.Required(CONF_SOURCE, default="knmi"): vol.In(
                    {key: cls.name for key, cls in SOURCE_REGISTRY.items()}
                ),
                vol.Required(CONF_API_KEY): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_dataset(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            dataset_key = user_input[CONF_DATASET]
            self._dataset = next(d for d in self._datasets if d.key == dataset_key)
            await self.async_set_unique_id(f"{self._source_key}:{dataset_key}")
            self._abort_if_unique_id_configured()
            return await self.async_step_parameters()

        schema = vol.Schema(
            {
                vol.Required(CONF_DATASET, default=self._datasets[0].key): vol.In(
                    {d.key: d.name for d in self._datasets}
                ),
            }
        )
        return self.async_show_form(step_id="dataset", data_schema=schema, errors=errors)

    async def async_step_parameters(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        assert self._dataset is not None
        errors: dict[str, str] = {}
        if user_input is not None:
            selected = user_input[CONF_PARAMETERS]
            if not selected:
                errors["base"] = "no_parameters_selected"
            else:
                return self.async_create_entry(
                    title=f"{self._dataset.name}",
                    data={
                        CONF_SOURCE: self._source_key,
                        CONF_API_KEY: self._api_key,
                        CONF_DATASET: self._dataset.key,
                        CONF_PARAMETERS: selected,
                    },
                )

        all_keys = [p.key for p in self._dataset.parameters]
        schema = vol.Schema(
            {
                vol.Required(CONF_PARAMETERS, default=all_keys): cv.multi_select(
                    {p.key: f"{p.name} ({p.unit})" for p in self._dataset.parameters}
                ),
            }
        )
        return self.async_show_form(step_id="parameters", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> "GribOverlayOptionsFlow":
        return GribOverlayOptionsFlow(config_entry)


class GribOverlayOptionsFlow(config_entries.OptionsFlow):
    """Lets the user tweak retention, forecast horizon and polling interval later."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self._config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_FORECAST_HORIZON_HOURS,
                    default=options.get(CONF_FORECAST_HORIZON_HOURS, DEFAULT_FORECAST_HORIZON_HOURS),
                ): vol.All(vol.Coerce(float), vol.Range(min=1, max=72)),
                vol.Required(
                    CONF_RETAIN_RUNS,
                    default=options.get(CONF_RETAIN_RUNS, DEFAULT_RETAIN_RUNS),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=10)),
                vol.Required(
                    CONF_UPDATE_INTERVAL_MINUTES,
                    default=options.get(CONF_UPDATE_INTERVAL_MINUTES, DEFAULT_UPDATE_INTERVAL_MINUTES),
                ): vol.All(vol.Coerce(int), vol.Range(min=5, max=180)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
