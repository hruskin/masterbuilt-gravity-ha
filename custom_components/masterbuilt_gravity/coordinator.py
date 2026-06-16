"""Data update coordinator for Masterbuilt Gravity."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MasterbuiltApi, MasterbuiltApiError, MasterbuiltAuthError
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class MasterbuiltCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Polls the cloud and exposes per-device reported shadow state.

    ``self.data`` maps macAddress -> reported state dict.
    ``self.devices`` maps macAddress -> device metadata (givenName, model, ...).
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: MasterbuiltApi) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.api = api
        self.entry = entry
        self.devices: dict[str, dict[str, Any]] = {}

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        try:
            if not self.devices:
                for dev in await self.api.async_get_devices():
                    mac = dev.get("macAddress")
                    if mac:
                        self.devices[mac] = dev
            result: dict[str, dict[str, Any]] = {}
            for mac in self.devices:
                try:
                    result[mac] = await self.api.async_get_shadow(mac)
                except MasterbuiltApiError as err:
                    _LOGGER.debug("Shadow fetch failed for %s: %s", mac, err)
                    result[mac] = self.data.get(mac, {}) if self.data else {}
            return result
        except MasterbuiltAuthError as err:
            raise UpdateFailed(f"authentication failed: {err}") from err
        except MasterbuiltApiError as err:
            raise UpdateFailed(str(err)) from err
