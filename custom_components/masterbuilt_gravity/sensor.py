"""Sensor platform for Masterbuilt Gravity."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MasterbuiltConfigEntry
from .const import TARGET_OFF, active_errors, error_text
from .entity import MasterbuiltEntity


def _heat_target(r: dict[str, Any]) -> Any:
    val = r.get("heat", {}).get("t2", {}).get("trgt")
    return None if val is None or val == TARGET_OFF else val


def _probe_temp(n: int) -> Callable[[dict[str, Any]], Any]:
    return lambda r: r.get("probes", {}).get(f"p{n}", {}).get("temp")


def _probe_target(n: int) -> Callable[[dict[str, Any]], Any]:
    def _fn(r: dict[str, Any]) -> Any:
        val = r.get("probes", {}).get(f"p{n}", {}).get("trgt")
        return None if not val else val
    return _fn


def _probe_present(n: int) -> Callable[[dict[str, Any]], bool]:
    return lambda r: f"p{n}" in (r.get("probes") or {})


@dataclass(frozen=True, kw_only=True)
class MbSensorDescription(SensorEntityDescription):
    """Sensor description with a value extractor."""

    value_fn: Callable[[dict[str, Any]], Any]
    is_temperature: bool = False
    present_fn: Callable[[dict[str, Any]], bool] | None = None
    attrs_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


SENSORS: tuple[MbSensorDescription, ...] = (
    MbSensorDescription(
        key="grill_temp",
        translation_key="grill_temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        is_temperature=True,
        value_fn=lambda r: r.get("mainTemp"),
    ),
    MbSensorDescription(
        key="target_temp",
        translation_key="target_temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        is_temperature=True,
        value_fn=_heat_target,
    ),
    MbSensorDescription(
        key="heat_intensity",
        translation_key="heat_intensity",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="%",
        value_fn=lambda r: r.get("heat", {}).get("t2", {}).get("intensity"),
    ),
    MbSensorDescription(
        key="rssi",
        translation_key="rssi",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda r: r.get("RSSI"),
    ),
    MbSensorDescription(
        key="error",
        translation_key="error",
        icon="mdi:alert-circle",
        value_fn=error_text,
        attrs_fn=lambda r: {"codes": active_errors(r), "raw": r.get("errors")},
    ),
)

PROBE_SENSORS: tuple[MbSensorDescription, ...] = tuple(
    desc
    for n in (1, 2, 3, 4)
    for desc in (
        MbSensorDescription(
            key=f"probe{n}_temp",
            translation_key=f"probe{n}_temp",
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            is_temperature=True,
            value_fn=_probe_temp(n),
            present_fn=_probe_present(n),
        ),
        MbSensorDescription(
            key=f"probe{n}_target",
            translation_key=f"probe{n}_target",
            device_class=SensorDeviceClass.TEMPERATURE,
            is_temperature=True,
            entity_registry_enabled_default=False,
            value_fn=_probe_target(n),
            present_fn=_probe_present(n),
        ),
    )
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MasterbuiltConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[MasterbuiltSensor] = []
    for mac in coordinator.devices:
        for desc in (*SENSORS, *PROBE_SENSORS):
            entities.append(MasterbuiltSensor(coordinator, mac, desc))
    async_add_entities(entities)


class MasterbuiltSensor(MasterbuiltEntity, SensorEntity):
    """A single reported-state value."""

    entity_description: MbSensorDescription

    def __init__(self, coordinator, mac: str, description: MbSensorDescription) -> None:
        super().__init__(coordinator, mac, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.reported)

    @property
    def native_unit_of_measurement(self) -> str | None:
        if self.entity_description.is_temperature:
            return (
                UnitOfTemperature.FAHRENHEIT
                if self.reported.get("fah")
                else UnitOfTemperature.CELSIUS
            )
        return self.entity_description.native_unit_of_measurement

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
