"""Sensors that make one entry's state visible inside Home Assistant itself.

Until now this integration published nothing: the cards showed the weather, but
nothing in Home Assistant said whether an entry was still getting data. The
four sensors here are the questions you cannot answer from the map --

* how old is the run I am looking at,
* how far ahead does it actually reach (which is not always the horizon that
  was asked for -- a source stops where its model stops),
* did anything decode at all,
* and how much disk is this costing --

each of which is something to automate on: notify me when the run is more than
six hours old, when the frame count drops to zero, when the cache passes a
gigabyte.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfInformation
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DATASET, DOMAIN
from .coordinator import Frame, GribOverlayConfigEntry, GribOverlayCoordinator


@dataclass(frozen=True, kw_only=True)
class GribOverlaySensorDescription(SensorEntityDescription):
    """A sensor described by how to read its value off the coordinator."""

    value_fn: Callable[[GribOverlayCoordinator], datetime | int | None]


def _run_time(coordinator: GribOverlayCoordinator) -> datetime | None:
    """The run every cached frame belongs to, read off the fullest parameter."""
    frames: list[Frame] = max(coordinator.frames.values(), key=len, default=[])
    return frames[0].run_time if frames else None


def _forecast_until(coordinator: GribOverlayCoordinator) -> datetime | None:
    """The furthest valid time any parameter reaches in the run being served."""
    times = [flist[-1].valid_time for flist in coordinator.frames.values() if flist]
    return max(times) if times else None


def _frame_count(coordinator: GribOverlayCoordinator) -> int:
    """How many rendered frames this entry is serving, over all parameters."""
    return sum(len(flist) for flist in coordinator.frames.values())


SENSORS: tuple[GribOverlaySensorDescription, ...] = (
    GribOverlaySensorDescription(
        key="run_time",
        translation_key="run_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_run_time,
    ),
    GribOverlaySensorDescription(
        key="forecast_until",
        translation_key="forecast_until",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_forecast_until,
    ),
    GribOverlaySensorDescription(
        key="frames",
        translation_key="frames",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="frames",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_frame_count,
    ),
    GribOverlaySensorDescription(
        key="cache_size",
        translation_key="cache_size",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.MEGABYTES,
        suggested_display_precision=0,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda coordinator: coordinator.cache_bytes,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GribOverlayConfigEntry,
    # AddEntitiesCallback rather than the config-entry-specific protocol, which
    # arrived in a core newer than the one hacs.json asks for. The two are
    # interchangeable here; this one keeps the floor where it is.
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add this entry's sensors."""
    async_add_entities(
        GribOverlaySensor(entry.runtime_data, description) for description in SENSORS
    )


class GribOverlaySensor(CoordinatorEntity[GribOverlayCoordinator], SensorEntity):
    """One reading off the coordinator, grouped under the entry's own device."""

    _attr_has_entity_name = True
    entity_description: GribOverlaySensorDescription

    def __init__(
        self,
        coordinator: GribOverlayCoordinator,
        description: GribOverlaySensorDescription,
    ) -> None:
        """Bind one sensor description to the coordinator it reads from."""
        super().__init__(coordinator)
        self.entity_description = description
        entry = coordinator.entry
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer=coordinator.source.name,
            model=entry.data.get(CONF_DATASET),
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def available(self) -> bool:
        """Whether this sensor has something to say.

        Deliberately not the coordinator's `last_update_success` alone: a
        provider that is down for an hour leaves the previous run in place and
        the cards keep working, so going unavailable would hide exactly the
        answer being asked for -- how old the data now is.
        """
        return self.coordinator.last_update_success or bool(self.coordinator.frames)

    @property
    def native_value(self) -> datetime | int | None:
        """The current reading, taken from the coordinator."""
        return self.entity_description.value_fn(self.coordinator)
