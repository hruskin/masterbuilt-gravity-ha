"""Base entity for Masterbuilt Gravity."""
from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_info import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MasterbuiltCoordinator


class MasterbuiltEntity(CoordinatorEntity[MasterbuiltCoordinator]):
    """Base entity tied to one grill (by mac address)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: MasterbuiltCoordinator, mac: str, key: str) -> None:
        super().__init__(coordinator)
        self._mac = mac
        self._attr_unique_id = f"{mac}_{key}"
        meta = coordinator.devices.get(mac, {})
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, mac)},
            name=meta.get("givenName") or "Masterbuilt Gravity",
            manufacturer="Masterbuilt",
            model=meta.get("model") or "Gravity Series",
            sw_version=(self.reported or {}).get("vers"),
        )

    @property
    def reported(self) -> dict[str, Any]:
        """Current reported shadow state for this grill."""
        return (self.coordinator.data or {}).get(self._mac, {}) or {}

    @property
    def available(self) -> bool:
        return super().available and self._mac in (self.coordinator.data or {})
