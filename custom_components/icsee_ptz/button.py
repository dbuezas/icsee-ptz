"""PTZ and maintenance buttons."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .binary_sensor import _run
from .const import (
    CONF_ADD_PTZ_BUTTONS_ALL_CHANNELS,
    CONF_CHANNEL,
    CONF_CHANNEL_COUNT,
    CONF_PRESET,
    CONF_STEP,
    DOMAIN,
)
from .coordinator import ICSeeConfigEntry, ICSeeCoordinator
from .entity import ICSeeEntity

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class ICSeePtzButtonEntityDescription(ButtonEntityDescription):
    ptz_cmd: str


def _ptz(key: str, cmd: str) -> ICSeePtzButtonEntityDescription:
    return ICSeePtzButtonEntityDescription(
        key=key,
        translation_key=key,
        ptz_cmd=cmd,
    )


PTZ_BUTTONS: tuple[ICSeePtzButtonEntityDescription, ...] = (
    _ptz("ptz_stop", "Stop"),
    _ptz("ptz_up", "DirectionUp"),
    _ptz("ptz_down", "DirectionDown"),
    _ptz("ptz_left", "DirectionLeft"),
    _ptz("ptz_right", "DirectionRight"),
    _ptz("ptz_left_up", "DirectionLeftUp"),
    _ptz("ptz_left_down", "DirectionLeftDown"),
    _ptz("ptz_right_up", "DirectionRightUp"),
    _ptz("ptz_right_down", "DirectionRightDown"),
    _ptz("ptz_zoom_in", "ZoomTile"),
    _ptz("ptz_zoom_out", "ZoomWide"),
    _ptz("home_go_to", "GotoPreset"),
    _ptz("home_set", "SetPreset"),
    _ptz("home_clear", "ClearPreset"),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ICSeeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    if entry.options.get(CONF_ADD_PTZ_BUTTONS_ALL_CHANNELS, False):
        channels = list(range(entry.data.get(CONF_CHANNEL_COUNT, 1)))
    else:
        channels = [entry.options.get(CONF_CHANNEL, 0)]
    entities: list[ButtonEntity] = [
        PtzButton(coordinator, description, channel)
        for description in PTZ_BUTTONS
        for channel in channels
    ]
    entities += [RebootButton(coordinator), SyncClockButton(coordinator)]
    async_add_entities(entities)


class PtzButton(ICSeeEntity, ButtonEntity):
    entity_description: ICSeePtzButtonEntityDescription

    def __init__(
        self,
        coordinator: ICSeeCoordinator,
        description: ICSeePtzButtonEntityDescription,
        channel: int,
    ) -> None:
        super().__init__(coordinator, f"{description.key}_{channel}", channel)
        self.entity_description = description

    @property
    def available(self) -> bool:
        return self.device.is_connected

    async def async_press(self) -> None:
        options = self.coordinator.config_entry.options
        await _run(
            self.device.async_ptz(
                self.entity_description.ptz_cmd,
                options.get(CONF_STEP, 2),
                options.get(CONF_PRESET, 0),
                self.channel,
            )
        )


class RebootButton(ICSeeEntity, ButtonEntity):
    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: ICSeeCoordinator) -> None:
        super().__init__(coordinator, "reboot")  # legacy unique id

    @property
    def available(self) -> bool:
        return self.device.is_connected

    async def async_press(self) -> None:
        await _run(self.device.async_reboot())
        # settings that needed a restart are applied now
        entry_id = self.coordinator.config_entry.entry_id
        ir.async_delete_issue(self.hass, DOMAIN, f"reboot_required_{entry_id}")


class SyncClockButton(ICSeeEntity, ButtonEntity):
    _attr_translation_key = "sync_clock"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: ICSeeCoordinator) -> None:
        super().__init__(coordinator, "sync_clock")

    @property
    def available(self) -> bool:
        return self.device.is_connected

    async def async_press(self) -> None:
        await _run(self.device.async_set_time())
