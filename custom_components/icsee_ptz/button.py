from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_ADD_PTZ_BUTTONS_ALL_CHANNELS,
    CONF_CHANNEL,
    CONF_CHANNEL_COUNT,
    CONF_PRESET,
    CONF_STEP,
)
from .icsee_entity import ICSeeEntity


@dataclass(frozen=True, kw_only=True)
class ICSeeButtonEntityDescription(ButtonEntityDescription):
    """A class that describes PTZ button entities."""

    ptz_cmd: str


BUTTON_ENTITIES: tuple[ICSeeButtonEntityDescription, ...] = (
    ICSeeButtonEntityDescription(
        key="ptz_stop",
        name="PTZ stop",
        icon="mdi:stop-circle",
        ptz_cmd="Stop",
    ),
    ICSeeButtonEntityDescription(
        key="ptz_up",
        name="PTZ up",
        icon="mdi:arrow-up-bold-box",
        ptz_cmd="DirectionUp",
    ),
    ICSeeButtonEntityDescription(
        key="ptz_down",
        name="PTZ down",
        icon="mdi:arrow-down-bold-box",
        ptz_cmd="DirectionDown",
    ),
    ICSeeButtonEntityDescription(
        key="ptz_left",
        name="PTZ left",
        icon="mdi:arrow-left-bold-box",
        ptz_cmd="DirectionLeft",
    ),
    ICSeeButtonEntityDescription(
        key="ptz_right",
        name="PTZ right",
        icon="mdi:arrow-right-bold-box",
        ptz_cmd="DirectionRight",
    ),
    ICSeeButtonEntityDescription(
        key="ptz_left_up",
        name="PTZ left up",
        icon="mdi:arrow-top-left-bold-box",
        ptz_cmd="DirectionLeftUp",
        entity_registry_enabled_default=False,
    ),
    ICSeeButtonEntityDescription(
        key="ptz_left_down",
        name="PTZ left down",
        icon="mdi:arrow-bottom-left-bold-box",
        ptz_cmd="DirectionLeftDown",
        entity_registry_enabled_default=False,
    ),
    ICSeeButtonEntityDescription(
        key="ptz_right_up",
        name="PTZ right up",
        icon="mdi:arrow-top-right-bold-box",
        ptz_cmd="DirectionRightUp",
        entity_registry_enabled_default=False,
    ),
    ICSeeButtonEntityDescription(
        key="ptz_right_down",
        name="PTZ right down",
        icon="mdi:arrow-bottom-right-bold-box",
        ptz_cmd="DirectionRightDown",
        entity_registry_enabled_default=False,
    ),
    ICSeeButtonEntityDescription(
        key="ptz_zoom_in",
        name="PTZ zoom in",
        icon="mdi:magnify-plus",
        ptz_cmd="ZoomTile",
        entity_registry_enabled_default=False,
    ),
    ICSeeButtonEntityDescription(
        key="ptz_zoom_out",
        name="PTZ zoom out",
        icon="mdi:magnify-minus",
        ptz_cmd="ZoomWide",
        entity_registry_enabled_default=False,
    ),
    ICSeeButtonEntityDescription(
        key="home_go_to",
        name="Home go to",
        icon="mdi:home-import-outline",
        ptz_cmd="GotoPreset",
    ),
    ICSeeButtonEntityDescription(
        key="home_set",
        name="Home set current position",
        icon="mdi:home-export-outline",
        ptz_cmd="SetPreset",
    ),
    ICSeeButtonEntityDescription(
        key="home_clear",
        name="Home clear",
        icon="mdi:home-remove-outline",
        ptz_cmd="ClearPreset",
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add PTZ button entities for passed config_entry in HA."""
    add_all_channels = entry.options.get(CONF_ADD_PTZ_BUTTONS_ALL_CHANNELS, False)
    configured_channel = entry.options.get(CONF_CHANNEL, 0)
    channels = (
        range(entry.data[CONF_CHANNEL_COUNT])
        if add_all_channels
        else [configured_channel]
    )
    async_add_entities(
        [
            ICSeeButtonEntity(hass, entry, description, channel)
            for description in BUTTON_ENTITIES
            for channel in channels
        ],
        update_before_add=False,
    )


class ICSeeButtonEntity(ICSeeEntity, ButtonEntity):
    """PTZ button entity for ICSee cameras."""

    entity_description: ICSeeButtonEntityDescription

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        description: ICSeeButtonEntityDescription,
        channel: int = 0,
    ) -> None:
        super().__init__(hass, entry)
        self.entity_description = description
        self.channel = channel
        assert self._attr_unique_id  # set by ICSeeEntity
        self._attr_unique_id += f"_{description.key}_{channel}"
        add_all_channels = entry.options.get(CONF_ADD_PTZ_BUTTONS_ALL_CHANNELS, False)
        if add_all_channels and entry.data[CONF_CHANNEL_COUNT] > 1:
            self._attr_name = f"{description.name} {channel}"
        else:
            self._attr_name = description.name

    async def async_press(self) -> None:
        """Execute the PTZ button command."""
        cmd = self.entity_description.ptz_cmd
        step = self.entry.options.get(CONF_STEP, 2)
        preset = self.entry.options.get(CONF_PRESET, 0)
        channel = self.entry.options.get(CONF_CHANNEL, self.channel)
        if cmd == "Stop":
            await self.cam.dvrip.ptz("DirectionUp", preset=-1)
        else:
            await self.cam.dvrip.ptz(cmd, step=step, preset=preset, ch=channel)
