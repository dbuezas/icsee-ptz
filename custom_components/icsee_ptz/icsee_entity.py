import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_MAC, CONF_NAME
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from homeassistant.helpers.entity import DeviceInfo, Entity
from homeassistant.core import HomeAssistant
import logging
from .camera import Camera

from .const import CONF_CHANNEL, CONF_PRESET, CONF_STEP, DOMAIN

_LOGGER = logging.getLogger(__name__)


class ICSeeEntity(Entity):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        self._attr_has_entity_name = True
        self._attr_unique_id = entry.data[CONF_MAC]
        self.hass = hass
        self.entry = entry
        self.cam: Camera = hass.data[DOMAIN][entry.entry_id]
        self.cam.add_onload_callback(self.schedule_update_ha_state)

    @property
    def available(self) -> bool:
        return self.cam.is_connected

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            name=self.entry.data[CONF_NAME],
            identifiers={(DOMAIN, self.entry.data[CONF_MAC])},
            sw_version=self.cam.system_info.get("SoftWareVersion"),
            hw_version=self.cam.system_info.get("HardWare"),
            model=self.cam.system_info.get("DeviceModel"),
            connections={(CONNECTION_NETWORK_MAC, self.entry.data[CONF_MAC])},
        )
