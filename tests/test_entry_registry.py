"""How anything finds a coordinator: through the config entry, not a side dict.

The entry carries its coordinator in ``runtime_data``, which Home Assistant
clears on unload by itself. These tests pin that contract, because five
modules (the HTTP views, the backup platform, the observations and chart key
lookups) depend on a lookup that cannot hand out a coordinator for an entry
that is not set up.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.grib_overlay.const import (
    CONF_API_KEY,
    CONF_DATASET,
    CONF_PARAMETERS,
    CONF_SOURCE,
    DOMAIN,
)
from custom_components.grib_overlay.coordinator import (
    async_coordinator_for,
    async_loaded_coordinators,
)
from homeassistant.config_entries import ConfigEntryState


def _stub(name: str) -> SimpleNamespace:
    """A stand-in coordinator: only unloading it has to work for real."""
    return SimpleNamespace(
        name=name, source=SimpleNamespace(async_stop_notifications=AsyncMock())
    )


def _loaded(hass, coordinator: object, *, domain: str = DOMAIN) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=domain,
        data={
            CONF_SOURCE: "knmi",
            CONF_API_KEY: "k",
            CONF_DATASET: "harmonie_arome_cy43_p1",
            CONF_PARAMETERS: ["wind_10m"],
        },
    )
    entry.add_to_hass(hass)
    entry.runtime_data = coordinator
    entry.mock_state(hass, ConfigEntryState.LOADED)
    return entry


def test_a_loaded_entry_hands_out_its_coordinator(hass) -> None:
    coordinator = _stub("one")
    entry = _loaded(hass, coordinator)
    assert async_coordinator_for(hass, entry.entry_id) is coordinator
    assert async_loaded_coordinators(hass) == [coordinator]


def test_an_unknown_entry_id_is_not_an_error(hass) -> None:
    """The card asks by id; a stale dashboard must get a 404, not a traceback."""
    assert async_coordinator_for(hass, "01JUNKJUNKJUNKJUNKJUNKJUNK") is None


def test_an_entry_of_another_integration_is_never_returned(hass) -> None:
    """Entry ids are global, so the domain has to be checked."""
    other = _loaded(hass, _stub("someone else"), domain="light")
    assert async_coordinator_for(hass, other.entry_id) is None
    assert async_loaded_coordinators(hass) == []


def test_an_entry_that_is_not_set_up_is_never_returned(hass) -> None:
    """runtime_data does not exist before setup, so reading it would raise."""
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_SOURCE: "knmi"})
    entry.add_to_hass(hass)
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert async_coordinator_for(hass, entry.entry_id) is None
    assert async_loaded_coordinators(hass) == []


def test_every_loaded_entry_is_listed(hass) -> None:
    first, second = _stub("one"), _stub("two")
    _loaded(hass, first)
    _loaded(hass, second)
    listed = async_loaded_coordinators(hass)
    assert len(listed) == 2
    assert {id(c) for c in listed} == {id(first), id(second)}
