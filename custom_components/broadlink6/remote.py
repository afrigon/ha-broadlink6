"""Remote entity transmitting raw Broadlink packets."""

import base64
from collections.abc import Iterable

from homeassistant.components.remote import ATTR_NUM_REPEATS, RemoteEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BroadlinkConfigEntry, device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BroadlinkConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([BroadlinkRemote(entry)])


class BroadlinkRemote(RemoteEntity):
    _attr_has_entity_name = True
    _attr_name = None
    _attr_should_poll = False
    _attr_is_on = True

    def __init__(self, entry: BroadlinkConfigEntry) -> None:
        self._coordinator = entry.runtime_data
        self._attr_unique_id = f"{entry.unique_id}-remote"
        self._attr_device_info = device_info(entry)

    async def async_turn_on(self, **kwargs) -> None:
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        self._attr_is_on = False
        self.async_write_ha_state()

    async def async_send_command(self, command: Iterable[str], **kwargs) -> None:
        if not self._attr_is_on:
            raise ServiceValidationError(
                "the remote is turned off; turn it on to send commands"
            )

        packets = [self._decode(item) for item in command]
        repeats = kwargs.get(ATTR_NUM_REPEATS, 1)

        for _ in range(repeats):
            for packet in packets:
                await self.hass.async_add_executor_job(
                    self._coordinator.send_data, packet
                )

    @staticmethod
    def _decode(command: str) -> bytes:
        if not command.startswith("b64:"):
            raise ServiceValidationError(
                "commands must be base64-encoded Broadlink packets ('b64:...')"
            )
        return base64.b64decode(command[4:])
