"""Sensor handling for Energy Stats integration."""

import logging
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CALCULATED_VALUES, DOMAIN
from .coordinator import EnergyStatsCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: Callable[[list[SensorEntity]], None],
) -> None:
    """Set up sensors for new entry."""
    _LOGGER.debug("Executing async_setup_entry (sensor)...")
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = []
    for key in coordinator.data["calculated_keys"]:
        _LOGGER.debug("Creating sensor for %s", key)
        entity = EnergyStatsSensor(coordinator, key)
        entities.append(entity)

    async_add_entities(entities)


class EnergyStatsSensor(CoordinatorEntity, SensorEntity):
    """Class for Energy Stats sensors."""

    def __init__(self, coordinator: EnergyStatsCoordinator, key: str) -> None:
        """Initialize a new sensor for the provided key."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._key = key
        self._attr_unique_id = f"{coordinator.entry_id}_{key}"
        self._attr_name = f"{CALCULATED_VALUES[key][0]}"
        self._attr_native_unit_of_measurement = CALCULATED_VALUES[key][3]
        self._attr_device_class = CALCULATED_VALUES[key][1]
        self._attr_state_class = CALCULATED_VALUES[key][2]
        self._attr_suggested_display_precision = 2

    @property
    def native_value(self) -> StateType | date | datetime | Decimal | None:
        """Return the value provided by the coordinator."""
        return self.coordinator.data.get(self._key)

    @property
    def available(self) -> bool:
        """Return if the sensor is available."""
        return super().available and (self._key in self.coordinator.data)
