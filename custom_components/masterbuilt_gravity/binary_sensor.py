"""Binary sensor platform for Masterbuilt Gravity."""
from __future__ import annotations

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

from . import MasterbuiltConfigEntry
from .const import active_errors, target_reached
from .entity import MasterbuiltEntity


@dataclass(frozen=True, kw_only=True)
class MbBinaryDescription(BinarySensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], bool | None]
    attrs_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


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


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MasterbuiltConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities = [
        MasterbuiltBinarySensor(coordinator, mac, desc)
        for mac in coordinator.devices
        for desc in BINARY_SENSORS
    ]
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
