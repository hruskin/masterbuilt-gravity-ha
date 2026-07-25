"""Climate platform for Masterbuilt Gravity.

Reads come from the CAS shadow poll (the coordinator); writes go out over AWS IoT
MQTT (see ``mqtt_control``), because the REST API exposes no shadow write.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MasterbuiltConfigEntry
from .const import (
    DEFAULT_MAX_TEMP_F,
    DEFAULT_MIN_TEMP_F,
    TARGET_OFF,
)
from .entity import MasterbuiltEntity
from .mqtt_control import MasterbuiltControlError

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MasterbuiltConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one thermostat per paired grill."""
    coordinator = entry.runtime_data
    async_add_entities(
        MasterbuiltClimate(coordinator, mac) for mac in coordinator.devices
    )


class MasterbuiltClimate(MasterbuiltEntity, ClimateEntity):
    """Thermostat for the grill's cooking chamber (heat source ``t2``)."""

    _attr_translation_key = "grill"
    _attr_name = None  # the device name is the entity name
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_target_temperature_step = 5

    def __init__(self, coordinator: Any, mac: str) -> None:
        super().__init__(coordinator, mac, "climate")
        # Last value we commanded, used to keep the UI responsive between the
        # command and the grill reporting it back (and see target_temperature).
        self._optimistic_target: float | None = None

    # ------------------------------------------------------------------ helpers

    @property
    def _t2(self) -> dict[str, Any]:
        return (self.reported.get("heat") or {}).get("t2") or {}

    # -------------------------------------------------------------------- state

    @property
    def temperature_unit(self) -> str:
        """The grill reports in its own configured unit; mirror it."""
        return (
            UnitOfTemperature.FAHRENHEIT
            if self.reported.get("fah")
            else UnitOfTemperature.CELSIUS
        )

    @property
    def current_temperature(self) -> float | None:
        return self.reported.get("mainTemp")

    @property
    def target_temperature(self) -> float | None:
        """The active setpoint.

        The grill reports ``trgt: 0`` whenever no cook is set (typically while
        powered off). Returning None for that case leaves the thermostat card with
        nothing to render and no way to pick a temperature, so fall back to the last
        value we commanded and finally to the grill's own minimum. That always gives
        the user a slider to drag; a real reported setpoint always wins.
        """
        val = self._t2.get("trgt")
        if val is not None and val != TARGET_OFF and val > 0:
            return val
        if self._optimistic_target is not None:
            return self._optimistic_target
        return self.min_temp

    @property
    def min_temp(self) -> float:
        val = self._t2.get("min")
        return val if val else DEFAULT_MIN_TEMP_F

    @property
    def max_temp(self) -> float:
        val = self._t2.get("max")
        return val if val else DEFAULT_MAX_TEMP_F

    @property
    def hvac_mode(self) -> HVACMode:
        return HVACMode.HEAT if self.reported.get("pwrOn") else HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction:
        """OFF when unpowered, HEATING while driving the fire, else IDLE.

        ``heat.t2.heating`` is the grill actively working (fan/auger). It goes false
        once the chamber settles at temperature, so IDLE here means "powered and at
        or above setpoint", not "not cooking".
        """
        if not self.reported.get("pwrOn"):
            return HVACAction.OFF
        return HVACAction.HEATING if self._t2.get("heating") else HVACAction.IDLE

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the fire intensity, which has no natural climate mapping."""
        attrs: dict[str, Any] = {}
        if (intensity := self._t2.get("intensity")) is not None:
            attrs["intensity"] = intensity
        return attrs

    # ---------------------------------------------------------------- commands

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the chamber setpoint."""
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return
        target = int(round(temp))
        self._optimistic_target = target
        self.async_write_ha_state()  # reflect immediately; the poll confirms it
        await self._send(
            self.coordinator.control.async_set_target_temperature(self._mac, target)
        )

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """HEAT powers the grill on; OFF powers it off."""
        await self._send(
            self.coordinator.control.async_set_power(
                self._mac, hvac_mode == HVACMode.HEAT
            )
        )

    async def async_turn_on(self) -> None:
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def _send(self, coro: Any) -> None:
        """Await a control coroutine, then refresh so the UI reflects reality.

        The grill applies a desired document and reports back within a couple of
        seconds; the refresh is what turns the optimistic UI change into confirmed
        state. If the write never lands, the next poll simply shows the old value.
        """
        try:
            await coro
        except MasterbuiltControlError as err:
            raise HomeAssistantError(f"Could not send command to grill: {err}") from err
        await self.coordinator.async_request_refresh()
