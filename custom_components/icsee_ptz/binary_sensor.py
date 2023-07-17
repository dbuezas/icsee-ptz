import logging
import threading

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
from dvrip import DVRIPCam

from .const import DOMAIN, Data

_LOGGER = logging.getLogger(__name__)

from datetime import timedelta

SCAN_INTERVAL = timedelta(seconds=20)


def alarmStart(self):
    # temporary fix until https://github.com/NeiroNx/python-dvr/pull/47 is released
    self.alarm = threading.Thread(
        name="DVRAlarm%08X" % self.session,
        target=self.alarm_thread,
        args=[self.busy],
    )
    res = self.get_command("", self.QCODES["AlarmSet"])
    self.alarm.start()
    return res


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
        "move",
    )
    platform.async_register_entity_service(
        "synchronize_clock",
        {},
        "synchronize_clock",
    )
    platform.async_register_entity_service(
        "force_frame",
        {},
        "force_frame",
    )
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            Alarm(hass, data),
        ],
        update_before_add=True,
    )


class Alarm(BinarySensorEntity):
    def __init__(self, hass: HomeAssistant, data: Data):
        self._attr_has_entity_name = True
        self._attr_device_class = BinarySensorDeviceClass.MOTION
        self._attr_name = "Motion Alarm"
        self.data = data
        self.dvrip = None
        self.dvrip_alarm = None
        self.first_update = True
        self.system_info = {}

    def onAlarm(self, what, n):
        self._attr_is_on = what["Status"] == "Start"
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        is_available_alarm = bool(self.dvrip_alarm and self.dvrip_alarm.socket)
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

    def move(self, cmd: str, **kwargs):
        assert self.dvrip
        step = kwargs.get("step", self.data["step"])
        preset = kwargs.get("preset", self.data["preset"])
        channel = kwargs.get("channel", self.data["channel"])
        if cmd == "Stop":
            self.dvrip.ptz("DirectionUp", preset=-1)
        else:
            self.dvrip.ptz(cmd, step=step, preset=preset, ch=channel)

    def synchronize_clock(self):
        assert self.dvrip
        self.dvrip.set_time()

    def force_frame(self):
        def callback(*args):
            assert self.dvrip
            self.dvrip.stop_monitor()

        try:
            assert self.dvrip
            self.dvrip.start_monitor(callback)
        except:
            pass

    async def async_will_remove_from_hass(self):
        if self.dvrip:
            self.dvrip.close()
        if self.dvrip_alarm:
            self.dvrip_alarm.close()
        self.dvrip = None
        self.dvrip_alarm = None

    def update(self):
        # Keepalive is currently broken in python-dvr (see https://github.com/NeiroNx/python-dvr/issues/48),
        # so I'm instead logging in again on every update.
        # To ensure no messages are lost, a new connection is established before dropping the previous one.
        was_available = self.available
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

        dvrip.login()
        dvrip_alarm.login()
        dvrip_alarm.setAlarm(self.onAlarm)
        alarmStart(dvrip_alarm)

        old_dvrip = self.dvrip
        old_dvrip_alarm = self.dvrip_alarm

        self.dvrip = dvrip
        self.dvrip_alarm = dvrip_alarm

        if old_dvrip:
            old_dvrip.close()
        if old_dvrip_alarm:
            old_dvrip_alarm.close()

        if self.first_update:
            self.first_update = False
            self.system_info = dvrip.get_system_info()
        if not was_available:
            self.dvrip.set_time()
