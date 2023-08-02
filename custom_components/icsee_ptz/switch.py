import logging
from homeassistant.components.switch import SwitchEntity

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_UNIQUE_ID
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import logging
from .icsee_entity import ICSeeEntity

from .const import CONF_CHANNEL, CONF_CHANNEL_COUNT, CONF_PRESET, CONF_STEP, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add sensors for passed config_entry in HA."""
    async_add_entities(
        [
            AlarmSwitch(hass, entry, channel)
            for channel in range(entry.data[CONF_CHANNEL_COUNT])
        ]
        + [
            HumanSwitch(hass, entry, channel)
            for channel in range(entry.data[CONF_CHANNEL_COUNT])
        ],
        update_before_add=False,
    )


class AlarmSwitch(ICSeeEntity, SwitchEntity):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, channel: int = 0):
        super().__init__(hass, entry)
        self.channel = channel
        self._attr_icon = "mdi:motion"
        self._attr_unique_id = (
            f"{self.entry.data[CONF_UNIQUE_ID]}_motion_switch_{self.channel}"
        )
        if channel == 0:
            self._attr_name = "Motion Detection Enabled"
        else:
            self._attr_name = f"Motion Detection Enabled {channel}"

    @property
    def is_on(self, **kwargs):
        return self.cam.detect_info["MotionDetect"][self.channel]["Enable"]

    async def async_turn_on(self, **kwargs):
        x = await self.cam.dvrip.get_info("Detect")
        x["MotionDetect"][self.channel]["Enable"] = True
        await self.cam.dvrip.set_info("Detect", x)
        self.cam.detect_info = x

    async def async_turn_off(self, **kwargs):
        x = await self.cam.dvrip.get_info("Detect")
        x["MotionDetect"][self.channel]["Enable"] = False
        await self.cam.dvrip.set_info("Detect", x)
        self.cam.detect_info = x


class HumanSwitch(ICSeeEntity, SwitchEntity):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, channel: int = 0):
        super().__init__(hass, entry)
        self.channel = channel
        self._attr_icon = "mdi:human"
        self._attr_unique_id = (
            f"{self.entry.data[CONF_UNIQUE_ID]}_human_switch_{self.channel}"
        )
        if channel == 0:
            self._attr_name = "Human Detection Enabled"
        else:
            self._attr_name = f"Human Detection Enabled {channel}"

    @property
    def is_on(self, **kwargs):
        return self.cam.detect_info["HumanDetection"][self.channel]["Enable"]

    async def async_turn_on(self, **kwargs):
        x = await self.cam.dvrip.get_info("Detect")
        x["HumanDetection"][self.channel]["Enable"] = True
        await self.cam.dvrip.set_info("Detect", x)
        self.cam.detect_info = x

    async def async_turn_off(self, **kwargs):
        x = await self.cam.dvrip.get_info("Detect")
        x["HumanDetection"][self.channel]["Enable"] = False
        await self.cam.dvrip.set_info("Detect", x)
        self.cam.detect_info = x
