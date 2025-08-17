import logging
from datetime import date, datetime
from decimal import Decimal

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CALCULATED_VALUES, DOMAIN
from .coordinator import EnergyStatsCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    _LOGGER.debug("Executing async_setup_entry (sensor)...")
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for key in coordinator.data["calculated_keys"]:
        _LOGGER.debug("Creating sensor for %s", key)
        entity = EnergyStatsSensor(coordinator, key)
        entities.append(entity)

    async_add_entities(entities)


async def async_update_entities(hass, entry, async_add_entities):
    _LOGGER.debug("Executing async_update_entities...")
    registry = er.async_get(hass)
    existing_entities = {
        entity.entity_id
        for entity in registry.entities.values()
        if entity.config_entry_id == entry.entry_id
    }
    _LOGGER.debug("Found existing entities: %s", str(existing_entities))
    coordinator = hass.data[DOMAIN][entry.entry_id]
    new_entities = []
    for key in coordinator.data["calculated_keys"]:
        unique_id = f"{entry.entry_id}_{key}"
        entity_id = f"sensor.{unique_id}"
        if entity_id not in existing_entities:
            new_entities.append(EnergyStatsSensor(coordinator, key))
    if new_entities:
        async_add_entities(new_entities)


class EnergyStatsSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator: EnergyStatsCoordinator, key: str) -> None:
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
    def native_value(self) -> StateType | date | datetime | Decimal | None:  # type: ignore[override]
        return self.coordinator.data.get(self._key)

    @property
    def available(self) -> bool:  # type: ignore[override]
        return super().available and (self._key in self.coordinator.data)
