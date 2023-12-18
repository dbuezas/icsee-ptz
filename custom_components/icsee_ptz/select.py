import logging
from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import logging
from .icsee_entity import ICSeeEntity

from .const import (
    CONF_CHANNEL_COUNT,
    CONF_EXPERIMENTAL_ENTITIES,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add sensors for passed config_entry in HA."""
    if not entry.options.get(CONF_EXPERIMENTAL_ENTITIES):
        return

    async_add_entities(
        [
            WhiteLightSelect(hass, entry, channel)
            for channel in range(entry.data[CONF_CHANNEL_COUNT])
        ],
        update_before_add=False,
    )
WHITE_LIGHT_WORK_MODE_LIST = ['Intelligent', 'Auto', 'Close']

class WhiteLightSelect(ICSeeEntity, SelectEntity):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, channel: int = 0):
        super().__init__(hass, entry)
        self.channel = channel
        self._attr_icon = "mdi:light-flood-down"
        assert self._attr_unique_id  # set by ICSeeEntity
        self._attr_unique_id += f"_WhiteLightSelect_{self.channel}"
        if channel == 0:
            self._attr_name = "White light"
        else:
            self._attr_name = f"White light {channel}"
        self._attr_options = WHITE_LIGHT_WORK_MODE_LIST

    @property
    def current_option(self) -> str | None:
        return self.cam.camara_info["WhiteLight"]["WorkMode"]

    async def async_select_option(self, option: str) -> None:
        await self.cam.dvrip.set_info("Camera.WhiteLight.WorkMode", option)
        self.cam.camara_info["WhiteLight"]["WorkMode"] = option
