"""Broadlink RM-series devices over IPv6."""

import logging
from datetime import timedelta

import broadlink6

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_MAC, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_DEVTYPE, DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.REMOTE, Platform.SENSOR]

type BroadlinkConfigEntry = ConfigEntry[BroadlinkCoordinator]


class BroadlinkCoordinator(DataUpdateCoordinator[dict[str, float]]):
    """Owns the device session and polls its built-in sensors."""

    def __init__(self, hass: HomeAssistant, entry: BroadlinkConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.data[CONF_HOST]}",
            update_interval=timedelta(seconds=60),
        )
        self.device = broadlink6.Device(
            entry.data[CONF_HOST],
            entry.data[CONF_DEVTYPE],
            entry.data[CONF_MAC],
        )
        self._authenticated = False

    async def _async_update_data(self) -> dict[str, float]:
        try:
            return await self.hass.async_add_executor_job(
                self._with_session, self.device.check_sensors
            )
        except broadlink6.BroadlinkError as err:
            raise UpdateFailed(str(err)) from err

    def send_data(self, data: bytes) -> None:
        """Transmit a raw IR/RF packet; runs in an executor thread."""
        self._with_session(self.device.send_data, data)

    def _with_session(self, call, *args):
        if not self._authenticated:
            self.device.auth()
            self._authenticated = True

        try:
            return call(*args)
        except broadlink6.AuthorizationError:
            # The device drops sessions it has not heard from in a while.
            self.device.auth()
            return call(*args)


def device_info(entry: BroadlinkConfigEntry) -> DeviceInfo:
    """Registry entry shared by every entity of one physical device."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.unique_id)},
        name="Broadlink RM4",
        manufacturer="Broadlink",
        model=f"{entry.data[CONF_DEVTYPE]:#06x}",
    )


async def async_setup_entry(hass: HomeAssistant, entry: BroadlinkConfigEntry) -> bool:
    coordinator = BroadlinkCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BroadlinkConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
