"""The camera name shown on the video."""

from __future__ import annotations

import re
from dataclasses import dataclass

from homeassistant.components.text import TextEntity, TextEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_CHANNEL_COUNT, DOMAIN
from .coordinator import ICSeeConfigEntry
from .device import CannotConnect, CommandFailed
from .entity import ICSeeConfigEntity, ICSeeConfigEntityDescription, config_entities

PARALLEL_UPDATES = 1

# The app allows 32 ASCII characters, or 21 when there are other characters
MAX_ASCII = 32
MAX_OTHER = 21
ASCII = re.compile(r"^[ -~]*$")


@dataclass(frozen=True, kw_only=True)
class ICSeeTextEntityDescription(ICSeeConfigEntityDescription, TextEntityDescription):
    """A text backed by a config field."""


VIDEO_NAME = ICSeeTextEntityDescription(
    key="video_name",
    translation_key="video_name",
    config="AVEnc.VideoWidget",
    path=("ChannelTitle", "Name"),
    native_min=1,
    native_max=MAX_ASCII,
    entity_category=EntityCategory.CONFIG,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ICSeeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(config_entities(coordinator, (VIDEO_NAME,), VideoNameText))


class VideoNameText(ICSeeConfigEntity, TextEntity):
    """Changing the name needs two steps: the config, then the channel titles."""

    entity_description: ICSeeTextEntityDescription

    @property
    def native_value(self) -> str | None:
        return self.config_value

    async def async_set_value(self, value: str) -> None:
        limit = MAX_ASCII if ASCII.match(value) else MAX_OTHER
        if not value.strip() or len(value) > limit:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_video_name",
                translation_placeholders={"max": str(limit)},
            )
        await self.async_write_value(value)
        # the camera only redraws the name when it gets all channel titles
        coordinator = self.coordinator
        count = coordinator.config_entry.data.get(CONF_CHANNEL_COUNT, 1)
        titles = [
            (coordinator.channel_value("AVEnc.VideoWidget", ch) or {})
            .get("ChannelTitle", {})
            .get("Name", "")
            for ch in range(count)
        ]
        titles[self.channel] = value
        try:
            await self.device.async_set_channel_titles(titles)
        except CannotConnect as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="cannot_connect"
            ) from err
        except CommandFailed as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={
                    "config": "ChannelTitle",
                    "ret": str(err.ret),
                },
            ) from err
