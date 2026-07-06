"""The device's built-in temperature and humidity sensors."""

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import BroadlinkConfigEntry, BroadlinkCoordinator, device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BroadlinkConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities(
        [
            BroadlinkSensor(
                entry,
                key="temperature",
                device_class=SensorDeviceClass.TEMPERATURE,
                unit=UnitOfTemperature.CELSIUS,
            ),
            BroadlinkSensor(
                entry,
                key="humidity",
                device_class=SensorDeviceClass.HUMIDITY,
                unit=PERCENTAGE,
            ),
        ]
    )


class BroadlinkSensor(CoordinatorEntity[BroadlinkCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        entry: BroadlinkConfigEntry,
        key: str,
        device_class: SensorDeviceClass,
        unit: str,
    ) -> None:
        super().__init__(entry.runtime_data)
        self._key = key
        self._attr_unique_id = f"{entry.unique_id}-{key}"
        self._attr_device_info = device_info(entry)
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.get(self._key)
