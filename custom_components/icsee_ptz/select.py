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
            DayNightColorSelect(hass, entry, channel)
            for channel in range(entry.data[CONF_CHANNEL_COUNT])
        ],
        update_before_add=False,
    )


DAY_NIGHT_COLOR_MAPPING = {
    "Unknown": "0x00000000",
    "Color": "0x00000001",
    "IR Filter": "0x00000002",
    "IR LED, light on alert": "0x00000003",
    "Color light": "0x00000004",
    "IR LED": "0x00000005",
}

DAY_NIGHT_COLOR_MAPPING_INV = {v: k for k, v in DAY_NIGHT_COLOR_MAPPING.items()}


class DayNightColorSelect(ICSeeEntity, SelectEntity):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, channel: int = 0):
        super().__init__(hass, entry)
        self.channel = channel
        self._attr_icon = "mdi:light-flood-down"
        assert self._attr_unique_id  # set by ICSeeEntity
        self._attr_unique_id += f"_DayNightColorSelect_{self.channel}"
        if channel == 0:
            self._attr_name = "Day Night Color"
        else:
            self._attr_name = f"Day Night Color {channel}"
        self._attr_options = list(DAY_NIGHT_COLOR_MAPPING.keys())

    @property
    def current_option(self) -> str | None:
        x = self.cam.camara_info["Param"][self.channel]["DayNightColor"]
        return DAY_NIGHT_COLOR_MAPPING_INV[x]

    async def async_select_option(self, option: str) -> None:
        x = await self.cam.dvrip.get_info("Camera.Param")
        x[self.channel]["DayNightColor"] = DAY_NIGHT_COLOR_MAPPING[option]
        await self.cam.dvrip.set_info("Camera.Param", x)
        self.cam.camara_info["Param"] = x
