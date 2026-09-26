"""Motion alarm binary sensor. It is also the target of the PTZ actions."""

from __future__ import annotations

from typing import Any

from collections.abc import Callable
from dataclasses import dataclass
import time

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_CHANNEL, CONF_CHANNEL_COUNT, CONF_PRESET, CONF_STEP, DOMAIN
from .coordinator import ICSeeConfigEntry, ICSeeCoordinator
from .device import CannotConnect, CommandFailed
from .entity import (
    ICSeeConfigEntity,
    ICSeeConfigEntityDescription,
    ICSeeEntity,
    config_entities,
)

PARALLEL_UPDATES = 0
PUSH_GRACE = 60  # seconds a pushed alarm wins over the polled state


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ICSeeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        MotionAlarm(coordinator, channel)
        for channel in range(entry.data.get(CONF_CHANNEL_COUNT, 1))
    )
    async_add_entities(
        config_entities(coordinator, CONFIG_SENSORS, ICSeeConfigBinarySensor)
    )


@dataclass(frozen=True, kw_only=True)
class ICSeeBinarySensorEntityDescription(
    ICSeeConfigEntityDescription, BinarySensorEntityDescription
):
    is_on_fn: Callable[[Any], bool]


def _any_set(*keys: str) -> Callable[[Any], bool]:
    def is_on(value: Any) -> bool:
        return any(bool(value.get(k)) for k in keys)

    return is_on


CONFIG_SENSORS: tuple[ICSeeBinarySensorEntityDescription, ...] = (
    ICSeeBinarySensorEntityDescription(
        # Security questions let anyone who knows the answers reset the password
        key="password_reset_questions",
        translation_key="password_reset_questions",
        config="General.PwdSafety",
        path=("PwdReset",),
        is_on_fn=lambda answers: any(a.get("QuestionAnswer") for a in answers),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ICSeeBinarySensorEntityDescription(
        key="telnet_open",
        translation_key="telnet_open",
        config="Ability.TelnetDebugMode",
        path=("Open",),
        is_on_fn=bool,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ICSeeBinarySensorEntityDescription(
        key="app_bound",
        translation_key="app_bound",
        config="General.AppBindFlag",
        path=("BeBinded",),
        is_on_fn=bool,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ICSeeBinarySensorEntityDescription(
        key="password_reset_contact",
        translation_key="password_reset_contact",
        config="General.PwdSafety",
        path=(),
        is_on_fn=_any_set("SecurityEmail", "SecurityPhone"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


class ICSeeConfigBinarySensor(ICSeeConfigEntity, BinarySensorEntity):
    entity_description: ICSeeBinarySensorEntityDescription

    @property
    def is_on(self) -> bool | None:
        value = self.config_value
        return None if value is None else self.entity_description.is_on_fn(value)


class MotionAlarm(ICSeeEntity, BinarySensorEntity):
    """Turns on while the camera reports an alarm (motion, human, ...)."""

    _attr_device_class = BinarySensorDeviceClass.MOTION
    _attr_translation_key = "motion_alarm"

    def __init__(self, coordinator: ICSeeCoordinator, channel: int) -> None:
        super().__init__(coordinator, f"alarm_{channel}", channel)  # legacy unique id
        self._last_push = 0.0
        self._attr_is_on = self._polled()

    def _polled(self) -> bool | None:
        """Current alarm state from WorkState (one bit per channel)."""
        state = (self.coordinator.channel_value("WorkState", 0) or {}).get("AlarmState")
        if not isinstance(state, dict) or state.get("VideoMotion") is None:
            return None
        try:
            bits = int(state["VideoMotion"], 16)
        except (TypeError, ValueError):
            return None
        return bool(bits >> self.channel & 1)

    @callback
    def _handle_coordinator_update(self) -> None:
        polled = self._polled()
        # Use the polled state at start, and when an event was missed (e.g. the
        # "motion ended" event during a connection drop)
        recent_push = time.monotonic() - self._last_push < PUSH_GRACE
        if polled is not None and polled != self._attr_is_on and not recent_push:
            self._attr_is_on = polled
        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        # Pushed by the camera; does not depend on the config polling
        return self.device.is_connected

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.device.add_alarm_callback(self._on_alarm))

    @callback
    def _on_alarm(self, what: dict[str, Any]) -> None:
        if what.get("Channel") != self.channel:
            return
        self._last_push = time.monotonic()
        self._attr_is_on = what.get("Status") == "Start"
        self._attr_extra_state_attributes = what
        self.async_write_ha_state()

    # ---- entity actions (registered in __init__.async_setup) ---------------

    async def async_move(self, cmd: str, **kwargs: Any) -> None:
        options = self.coordinator.config_entry.options
        step = kwargs.get("step", options.get(CONF_STEP, 2))
        preset = kwargs.get("preset", options.get(CONF_PRESET, 0))
        channel = kwargs.get("channel", options.get(CONF_CHANNEL, self.channel))
        await _run(self.device.async_ptz(cmd, step, preset, channel))

    async def async_synchronize_clock(self) -> None:
        await _run(self.device.async_set_time())

    async def async_force_frame(self) -> None:
        await _run(self.device.async_force_frame())


async def _run(coro: Any) -> None:
    try:
        await coro
    except CannotConnect as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="cannot_connect"
        ) from err
    except CommandFailed as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="command_failed",
            translation_placeholders={"config": err.name, "ret": str(err.ret)},
        ) from err
