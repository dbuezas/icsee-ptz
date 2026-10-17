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
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_call_later

from .const import (
    CONF_CHANNEL,
    CONF_CHANNEL_COUNT,
    CONF_MOTION_MIN_MS,
    CONF_MOTION_STICK_MS,
    CONF_PRESET,
    CONF_STEP,
    DEFAULT_MOTION_MIN_MS,
    DEFAULT_MOTION_STICK_MS,
    DOMAIN,
)
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
    ICSeeBinarySensorEntityDescription(
        # UPnP has opened ports on the router
        key="upnp_ports_open",
        translation_key="upnp_ports_open",
        config="NetWork.Upnp",
        path=("State",),
        is_on_fn=bool,
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
        # Some cameras never set VideoMotion in WorkState, even during an alarm.
        # Only trust a polled "off" once the camera has shown a polled "on".
        self._poll_reports_motion = False
        self._attr_is_on = self._polled()
        options = coordinator.config_entry.options
        self._min_s = options.get(CONF_MOTION_MIN_MS, DEFAULT_MOTION_MIN_MS) / 1000
        self._stick_s = (
            options.get(CONF_MOTION_STICK_MS, DEFAULT_MOTION_STICK_MS) / 1000
        )
        self._pending: CALLBACK_TYPE | None = None  # delayed on or off

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
        if polled:
            self._poll_reports_motion = True
        # Use the polled state when an event was missed (e.g. the "motion ended"
        # event during a connection drop). A polled "off" only counts on cameras
        # that are known to report motion in WorkState.
        recent_push = time.monotonic() - self._last_push < PUSH_GRACE
        trusted = polled or self._poll_reports_motion
        if (
            polled is not None
            and polled != self._attr_is_on
            and not recent_push
            and trusted
        ):
            self._cancel_pending()
            self._attr_is_on = polled
        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        # Pushed by the camera; does not depend on the config polling
        return self.device.is_connected

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.device.add_alarm_callback(self._on_alarm))
        self.async_on_remove(self._cancel_pending)

    @callback
    def _on_alarm(self, what: dict[str, Any]) -> None:
        if what.get("Channel") != self.channel:
            return
        self._last_push = time.monotonic()
        self._attr_extra_state_attributes = what
        raw = what.get("Status") == "Start"
        if raw == bool(self._attr_is_on):
            # a stop before min_ms, or a start during the stick time
            self._cancel_pending()
            return
        if self._pending:
            return  # repeated event, the timer already runs
        delay = self._min_s if raw else self._stick_s
        if delay <= 0:
            self._set(raw)
            return

        @callback
        def _fire(_now: Any) -> None:
            self._pending = None
            self._set(raw)

        self._pending = async_call_later(self.hass, delay, _fire)

    @callback
    def _set(self, is_on: bool) -> None:
        self._attr_is_on = is_on
        self.async_write_ha_state()

    @callback
    def _cancel_pending(self) -> None:
        if self._pending:
            self._pending()
            self._pending = None

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
