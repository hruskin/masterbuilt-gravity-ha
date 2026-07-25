"""Number platform for Masterbuilt Gravity: meat probe targets and the cook timer.

Reads come from the shadow poll; writes go out over AWS IoT MQTT (see ``mqtt_control``).
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MasterbuiltConfigEntry
from .const import (
    PROBE_MAX_C,
    PROBE_MAX_F,
    PROBE_MIN_C,
    PROBE_MIN_F,
    TIMER_MAX_MINUTES,
    probe_present,
)
from .entity import MasterbuiltEntity
from .mqtt_control import MasterbuiltControlError

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MasterbuiltConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up probe target numbers and the cook timer for each grill."""
    coordinator = entry.runtime_data
    entities: list[NumberEntity] = []
    for mac in coordinator.devices:
        entities += [MasterbuiltProbeTarget(coordinator, mac, n) for n in (1, 2, 3, 4)]
        entities.append(MasterbuiltCookTimer(coordinator, mac))
    async_add_entities(entities)


class _MbNumberBase(MasterbuiltEntity, NumberEntity):
    """Shared write plumbing: surface control failures, then refresh."""

    _attr_mode = NumberMode.BOX

    async def _send(self, coro: Any) -> None:
        try:
            await coro
        except MasterbuiltControlError as err:
            raise HomeAssistantError(f"Could not send command to grill: {err}") from err
        await self.coordinator.async_request_refresh()


class MasterbuiltProbeTarget(_MbNumberBase):
    """Target temperature for one meat probe.

    Only available while the probe is physically plugged in - the grill omits the
    ``probes.pN`` key entirely otherwise.
    """

    _attr_device_class = NumberDeviceClass.TEMPERATURE

    def __init__(self, coordinator: Any, mac: str, position: int) -> None:
        super().__init__(coordinator, mac, f"probe{position}_target_set")
        self._position = position
        self._attr_translation_key = f"probe{position}_target_set"

    @property
    def _probe(self) -> dict[str, Any]:
        return (self.reported.get("probes") or {}).get(f"p{self._position}") or {}

    @property
    def _fah(self) -> bool:
        return bool(self.reported.get("fah"))

    @property
    def native_unit_of_measurement(self) -> str:
        return (
            UnitOfTemperature.FAHRENHEIT if self._fah else UnitOfTemperature.CELSIUS
        )

    @property
    def native_min_value(self) -> float:
        return PROBE_MIN_F if self._fah else PROBE_MIN_C

    @property
    def native_max_value(self) -> float:
        return PROBE_MAX_F if self._fah else PROBE_MAX_C

    @property
    def native_value(self) -> float | None:
        """The probe's target, or None when no target is set (grill reports 0)."""
        val = self._probe.get("trgt")
        return None if not val or val <= 0 else val

    @property
    def available(self) -> bool:
        return super().available and probe_present(self.reported, self._position)

    async def async_set_native_value(self, value: float) -> None:
        await self._send(
            self.coordinator.control.async_set_probe_target(
                self._mac, self._position, int(round(value))
            )
        )


class MasterbuiltCookTimer(_MbNumberBase):
    """Count-down cook timer, in minutes.

    The grill exposes ``timers.dwn`` as ``{trgt, current, paused}``; ``trgt`` is the
    duration in minutes and ``current`` the remaining time, surfaced as an attribute.
    """

    _attr_translation_key = "cook_timer"
    _attr_device_class = NumberDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_native_min_value = 0
    _attr_native_max_value = TIMER_MAX_MINUTES
    _attr_native_step = 1
    _attr_icon = "mdi:timer-outline"

    def __init__(self, coordinator: Any, mac: str) -> None:
        super().__init__(coordinator, mac, "cook_timer")

    @property
    def _timer(self) -> dict[str, Any]:
        return (self.reported.get("timers") or {}).get("dwn") or {}

    @property
    def native_value(self) -> float | None:
        val = self._timer.get("trgt")
        return None if val is None else val

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        timer = self._timer
        if not timer:
            return None
        attrs: dict[str, Any] = {}
        if (current := timer.get("current")) is not None:
            attrs["remaining_minutes"] = current
        if (paused := timer.get("paused")) is not None:
            attrs["paused"] = paused
        return attrs or None

    async def async_set_native_value(self, value: float) -> None:
        await self._send(
            self.coordinator.control.async_set_timer(self._mac, int(round(value)))
        )
