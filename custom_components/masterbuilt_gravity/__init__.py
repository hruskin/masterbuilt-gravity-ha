"""The Masterbuilt Gravity integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from homeassistant.helpers.storage import STORAGE_DIR

from .api import MasterbuiltApi
from .const import (
    CONF_COGNITO_CLIENT_SECRET,
    CONF_COGNITO_PASSWORD,
    CONF_COGNITO_USERNAME,
    CONF_EMAIL,
    CONF_PASSWORD,
    IOT_STORAGE_DIR,
)
from .coordinator import MasterbuiltCoordinator
from .mqtt_control import MasterbuiltMqttControl

PLATFORMS = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.NUMBER,
]

type MasterbuiltConfigEntry = ConfigEntry[MasterbuiltCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: MasterbuiltConfigEntry) -> bool:
    """Set up Masterbuilt Gravity from a config entry."""
    session = async_get_clientsession(hass)
    api = MasterbuiltApi(session, entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD])
    coordinator = MasterbuiltCoordinator(hass, entry, api)
    # Writes cannot go over the read-only REST API, so control rides AWS IoT MQTT.
    coordinator.control = MasterbuiltMqttControl(
        hass,
        hass.config.path(STORAGE_DIR, IOT_STORAGE_DIR),
        cognito_username=entry.data.get(CONF_COGNITO_USERNAME),
        cognito_password=entry.data.get(CONF_COGNITO_PASSWORD),
        cognito_client_secret=entry.data.get(CONF_COGNITO_CLIENT_SECRET),
    )
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MasterbuiltConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
