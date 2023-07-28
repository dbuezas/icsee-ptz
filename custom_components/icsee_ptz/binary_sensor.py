from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.core import HomeAssistant
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers import entity_platform
from homeassistant.helpers import config_validation as cv
import logging
import voluptuous as vol
from .asyncio_dvrip import DVRIPCam, SomethingIsWrongWithCamera

from .const import DOMAIN, Data

_LOGGER = logging.getLogger(__name__)


SCAN_INTERVAL = timedelta(seconds=20)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add sensors for passed config_entry in HA."""
    platform = entity_platform.async_get_current_platform()

    platform.async_register_entity_service(
        "move",
        {
            vol.Required("cmd"): cv.string,
            vol.Optional("step"): cv.positive_int,
            vol.Optional("preset"): cv.positive_int,
            vol.Optional("channel"): cv.positive_int,
        },
        "async_move",
    )
    platform.async_register_entity_service(
        "synchronize_clock",
        {},
        "async_synchronize_clock",
    )
    platform.async_register_entity_service(
        "force_frame",
        {},
        "async_force_frame",
    )
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            Alarm(hass, data),
        ],
        update_before_add=False,
    )


class Alarm(BinarySensorEntity):
    def __init__(self, hass: HomeAssistant, data: Data):
        self._attr_has_entity_name = True
        self._attr_device_class = BinarySensorDeviceClass.MOTION
        self._attr_name = "Motion Alarm"
        self.hass = hass
        self.data = data
        self.dvrip = None
        self.dvrip_alarm = None
        self.system_info: dict = {}

    def onAlarm(self, what, n):
        self._attr_is_on = what["Status"] == "Start"
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        self.async_schedule_update_ha_state(force_refresh=True)

    @property
    def available(self) -> bool:
        is_available_alarm = bool(
            self.dvrip_alarm and self.dvrip_alarm.socket_reader)
        return is_available_alarm

    @property
    def unique_id(self) -> str:
        assert self.name
        return DOMAIN + "_" + self.data["host"].replace(".", "_") + "_" + self.name

    @property
    def device_info(self) -> DeviceInfo:
        assert self.name

        return DeviceInfo(
            name=self.data["name"],
            identifiers={(DOMAIN, self.data["name"])},
            sw_version=self.system_info.get("SoftWareVersion"),
            hw_version=self.system_info.get("HardWare"),
            model=self.system_info.get("DeviceModel"),
            connections={("ip", self.data["host"])},
        )

    async def async_move(self, cmd: str, **kwargs):
        assert self.dvrip
        step = kwargs.get("step", self.data["step"])
        preset = kwargs.get("preset", self.data["preset"])
        channel = kwargs.get("channel", self.data["channel"])
        if cmd == "Stop":
            await self.dvrip.ptz("DirectionUp", preset=-1)
        else:
            await self.dvrip.ptz(cmd, step=step, preset=preset, ch=channel)

    async def async_synchronize_clock(self):
        assert self.dvrip
        await self.dvrip.set_time()

    async def async_force_frame(self):
        def callback(*args):
            assert self.dvrip
            self.dvrip.stop_monitor()

        try:
            assert self.dvrip
            await self.dvrip.start_monitor(callback)
        except:
            pass

    async def async_will_remove_from_hass(self):
        if self.dvrip:
            self.dvrip.close()
        if self.dvrip_alarm:
            self.dvrip_alarm.close()
        self.dvrip = None
        self.dvrip_alarm = None

    async def async_update(self):
        # Keepalive is currently broken in python-dvr (see https://github.com/NeiroNx/python-dvr/issues/48),
        # so I'm instead logging in again on every update.
        # To ensure no messages are lost, a new connection is established before dropping the previous one.
        dvrip = DVRIPCam(
            self.data["host"],
            user=self.data["user"],
            password=self.data["password"],
        )
        dvrip_alarm = DVRIPCam(
            self.data["host"],
            user=self.data["user"],
            password=self.data["password"],
        )
        try:
            await dvrip.login(self.hass.loop)
            await dvrip_alarm.login(self.hass.loop)
            dvrip_alarm.setAlarm(self.onAlarm)
            await dvrip_alarm.alarmStart(self.hass.loop)
            if not self.system_info:
                self.system_info = await dvrip.get_system_info()  # type: ignore
                await dvrip.set_time()
        except SomethingIsWrongWithCamera:
            pass

        dvrip, self.dvrip = self.dvrip, dvrip
        dvrip_alarm, self.dvrip_alarm = self.dvrip_alarm, dvrip_alarm

        if dvrip:
            dvrip.close()
        if dvrip_alarm:
            dvrip_alarm.close()
