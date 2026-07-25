"""Binary sensor platform for Masterbuilt Gravity."""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import MasterbuiltConfigEntry
from .const import (
    STALE_AFTER_SECONDS,
    active_errors,
    probe_present,
    probe_reached,
    target_reached,
)
from .entity import MasterbuiltEntity


@dataclass(frozen=True, kw_only=True)
class MbBinaryDescription(BinarySensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], bool | None]
    attrs_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None
    present_fn: Callable[[dict[str, Any]], bool] | None = None


BINARY_SENSORS: tuple[MbBinaryDescription, ...] = (
    MbBinaryDescription(
        key="power",
        translation_key="power",
        device_class=BinarySensorDeviceClass.POWER,
        value_fn=lambda r: r.get("pwrOn"),
    ),
    MbBinaryDescription(
        key="heating",
        translation_key="heating",
        device_class=BinarySensorDeviceClass.HEAT,
        value_fn=lambda r: r.get("heat", {}).get("t2", {}).get("heating"),
    ),
    MbBinaryDescription(
        key="engaged",
        translation_key="engaged",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda r: r.get("engaged"),
    ),
    MbBinaryDescription(
        key="door_open",
        translation_key="door_open",
        device_class=BinarySensorDeviceClass.DOOR,
        value_fn=lambda r: r.get("doorOpn"),
    ),
    MbBinaryDescription(
        key="lid_open",
        translation_key="lid_open",
        device_class=BinarySensorDeviceClass.OPENING,
        value_fn=lambda r: r.get("lidOpn"),
    ),
    MbBinaryDescription(
        key="problem",
        translation_key="problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda r: bool(active_errors(r)),
        attrs_fn=lambda r: {"codes": active_errors(r), "raw": r.get("errors")},
    ),
    MbBinaryDescription(
        key="target_reached",
        translation_key="target_reached",
        value_fn=target_reached,
    ),
)

PROBE_REACHED: tuple[MbBinaryDescription, ...] = tuple(
    MbBinaryDescription(
        key=f"probe{n}_reached",
        translation_key=f"probe{n}_reached",
        icon="mdi:thermometer-check",
        value_fn=lambda r, n=n: probe_reached(r, n),
        present_fn=lambda r, n=n: probe_present(r, n),
    )
    for n in (1, 2, 3, 4)
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MasterbuiltConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = [
        MasterbuiltBinarySensor(coordinator, mac, desc)
        for mac in coordinator.devices
        for desc in (*BINARY_SENSORS, *PROBE_REACHED)
    ]
    entities += [MasterbuiltCloudConnected(coordinator, mac) for mac in coordinator.devices]
    async_add_entities(entities)


class MasterbuiltBinarySensor(MasterbuiltEntity, BinarySensorEntity):
    entity_description: MbBinaryDescription

    def __init__(self, coordinator, mac: str, description: MbBinaryDescription) -> None:
        super().__init__(coordinator, mac, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.reported)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attrs_fn:
            return self.entity_description.attrs_fn(self.reported)
        return None

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        present = self.entity_description.present_fn
        return present(self.reported) if present else True


class MasterbuiltCloudConnected(MasterbuiltEntity, BinarySensorEntity):
    """Whether the grill is still talking to the cloud.

    A grill that drops its AWS IoT session keeps serving its last ``reported``
    document forever, so every other entity silently freezes at stale values and no
    command can take effect. The shadow's metadata timestamps are the only way to
    tell. Observed trigger: pairing over BLE appears to displace the Wi-Fi/cloud
    session (the shadow flag is named IS_BLE_OR_WIFI_ENGAGED); power-cycling the
    grill restores it.
    """

    _attr_translation_key = "cloud_connected"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, mac: str) -> None:
        super().__init__(coordinator, mac, "cloud_connected")

    @property
    def is_on(self) -> bool | None:
        ts = self.coordinator.last_reported.get(self._mac)
        if ts is None:
            return None
        return (time.time() - ts) <= STALE_AFTER_SECONDS

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        ts = self.coordinator.last_reported.get(self._mac)
        if ts is None:
            return None
        return {
            "last_reported": dt_util.utc_from_timestamp(ts).isoformat(),
            "seconds_since_report": int(time.time() - ts),
        }
