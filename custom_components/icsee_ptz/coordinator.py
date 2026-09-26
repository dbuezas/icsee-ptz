"""Reads and writes the camera configs."""

from __future__ import annotations

from collections.abc import Callable
import copy
from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, RET_NEEDS_REBOOT, SCAN_INTERVAL
from .device import CannotConnect, CommandFailed, ConfigNotSupported, ICSeeDevice

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConfigSpec:
    """How a config is laid out on the camera."""

    per_channel: bool  # the value is a list with one element per channel
    channel_suffix: bool = (
        True  # write one channel as "Name.[ch]" (else the whole list)
    )
    code: int = 1042  # read command: 1042 config, 1020 status, 1472 users


CONFIGS: dict[str, ConfigSpec] = {
    "Camera.Param": ConfigSpec(per_channel=True),
    "Camera.ParamEx": ConfigSpec(per_channel=True),
    "Camera.ClearFog": ConfigSpec(per_channel=True),
    "Camera.WhiteLight": ConfigSpec(per_channel=False),
    "Simplify.Encode": ConfigSpec(per_channel=True, channel_suffix=False),
    "AVEnc.VideoColor": ConfigSpec(per_channel=True),
    "fVideo.Volume": ConfigSpec(per_channel=True),
    "fVideo.InVolume": ConfigSpec(per_channel=True),
    "Detect.MotionDetect": ConfigSpec(per_channel=True),
    "Detect.HumanDetection": ConfigSpec(per_channel=True),
    "Detect.BlindDetect": ConfigSpec(per_channel=True),
    "Detect.LossDetect": ConfigSpec(per_channel=True),
    "Detect.CarShapeDetection": ConfigSpec(per_channel=True),
    "Detect.DetectTrack": ConfigSpec(per_channel=False),
    "FbExtraStateCtrl": ConfigSpec(per_channel=False),
    "General.OneKeyMaskVideo": ConfigSpec(per_channel=True),
    "General.TimingSleep": ConfigSpec(per_channel=True),
    "General.Location": ConfigSpec(per_channel=False),
    # security
    "NetWork.Nat": ConfigSpec(per_channel=False),  # XMEye cloud / P2P access
    "NetWork.PMS": ConfigSpec(per_channel=False),  # cloud push notifications
    "NetWork.RTSP": ConfigSpec(per_channel=False),  # RTSP server (video)
    "General.PwdSafety": ConfigSpec(per_channel=False),  # password reset options
    "NetWork.DisableXmServerConn": ConfigSpec(per_channel=False),
    "NetWork.Upnp": ConfigSpec(per_channel=False),
    "NetWork.OnlineUpgrade": ConfigSpec(per_channel=False),
    "NetWork.DAS": ConfigSpec(per_channel=False),
    "NetWork.NetNTP": ConfigSpec(per_channel=False),
    "NetWork.CheckNetState": ConfigSpec(per_channel=False),
    "Ability.TelnetDebugMode": ConfigSpec(per_channel=False),
    "General.AppBindFlag": ConfigSpec(per_channel=False),
    "General.AutoMaintain": ConfigSpec(per_channel=False),
    "General.ResumePtzState": ConfigSpec(per_channel=False),
    "AVEnc.VideoWidget": ConfigSpec(per_channel=True),
    "fVideo.OsdLogo": ConfigSpec(per_channel=False),
    "Uart.PTZPreset": ConfigSpec(per_channel=True),
    "AVEnc.SystemAbnormalRebootCnt": ConfigSpec(per_channel=True),
    # read only status
    "Users": ConfigSpec(per_channel=False, code=1472),
    "WifiRouteInfo": ConfigSpec(per_channel=False, code=1020),
    "Status.NatInfo": ConfigSpec(per_channel=False),  # cloud connection state
    "StorageInfo": ConfigSpec(per_channel=False, code=1020),  # SD card
    "WorkState": ConfigSpec(per_channel=False, code=1020),  # current alarm state
}

# Abilities (cmd 1360) read once at setup
ABILITIES = ("SystemFunction", "EncodeCapability", "Camera")

type ICSeeConfigEntry = ConfigEntry[ICSeeData]


@dataclass
class ICSeeData:
    """Runtime data of a config entry."""

    device: ICSeeDevice
    coordinator: ICSeeCoordinator


class ICSeeCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls all supported configs of one camera."""

    config_entry: ICSeeConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: ICSeeConfigEntry, device: ICSeeDevice
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.title}",
            update_interval=SCAN_INTERVAL,
        )
        self.device = device
        self.abilities: dict[str, Any] = {}
        self.system_info: dict[str, Any] = {}
        self.supported: set[str] | None = None  # None until the first refresh

    async def _async_setup(self) -> None:
        """Read the device info and abilities once."""
        try:
            self.system_info = await self.device.async_get_system_info() or {}
            for name in ABILITIES:
                try:
                    self.abilities[name] = await self.device.async_get_ability(name)
                except (ConfigNotSupported, CommandFailed):
                    self.abilities[name] = {}
        except CannotConnect as err:
            raise UpdateFailed(
                translation_domain=DOMAIN, translation_key="cannot_connect"
            ) from err

    async def _async_update_data(self) -> dict[str, Any]:
        data = dict(self.data or {})
        first = self.supported is None
        names = list(CONFIGS) if first else sorted(self.supported or ())
        supported: set[str] = set()
        try:
            for name in names:
                try:
                    code = CONFIGS[name].code
                    if code == 1042:
                        data[name] = await self.device.async_get_config(name)
                    else:
                        data[name] = await self.device.async_get_value(name, code)
                    supported.add(name)
                except ConfigNotSupported:
                    data.pop(name, None)
                except CommandFailed as err:
                    _LOGGER.debug("Reading %s failed: %s", name, err)
                    if name in data:
                        supported.add(name)
        except CannotConnect as err:
            raise UpdateFailed(
                translation_domain=DOMAIN, translation_key="cannot_connect"
            ) from err
        if first:
            self.supported = supported
        return data

    # ---- helpers for entities ---------------------------------------------

    def ability(self, path: str) -> bool:
        """E.g. ability("SystemFunction.OtherFunction.SupportCameraWhiteLight")."""
        value: Any = self.abilities
        for key in path.split("."):
            if not isinstance(value, dict) or key not in value:
                return False
            value = value[key]
        return bool(value) and value not in ("0x00000000", "0")

    def channel_value(self, config: str, channel: int) -> Any:
        """The part of a config that belongs to one channel."""
        value = (self.data or {}).get(config)
        if value is None:
            return None
        if CONFIGS[config].per_channel:
            if not isinstance(value, list) or channel >= len(value):
                return None
            return value[channel]
        return value

    async def async_update_config(
        self, config: str, channel: int, mutate: Callable[[Any], None]
    ) -> None:
        """Read the config fresh, change it, write it back, and read it again."""
        spec = CONFIGS[config]
        use_suffix = spec.per_channel and spec.channel_suffix
        name = f"{config}.[{channel}]" if use_suffix else config
        try:
            current = await self.device.async_get_config(name)
            new = copy.deepcopy(current)
            if spec.per_channel and not use_suffix:
                mutate(new[channel])
            else:
                mutate(new)
            ret = await self.device.async_set_config(name, new)
            check = await self.device.async_get_config(name)
        except CannotConnect as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="cannot_connect"
            ) from err
        except ConfigNotSupported as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="not_supported",
                translation_placeholders={"config": config},
            ) from err
        except CommandFailed as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"config": config, "ret": str(err.ret)},
            ) from err

        data = dict(self.data or {})
        if use_suffix:
            values = list(data.get(config) or [])
            while len(values) <= channel:
                values.append(None)
            values[channel] = check
            data[config] = values
        else:
            data[config] = check
        self.async_set_updated_data(data)

        if ret == RET_NEEDS_REBOOT:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                f"reboot_required_{self.config_entry.entry_id}",
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="reboot_required",
                translation_placeholders={"name": self.config_entry.title},
            )
        elif _changed_paths_differ(current, new, check):
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="not_applied",
                translation_placeholders={"config": config},
            )


def _changed_paths_differ(before: Any, wanted: Any, actual: Any) -> bool:
    """True if a field we changed does not have the wanted value on the camera."""
    if isinstance(wanted, dict) and isinstance(before, dict):
        if not isinstance(actual, dict):
            return True
        return any(
            _changed_paths_differ(before.get(k), v, actual.get(k))
            for k, v in wanted.items()
            if before.get(k) != v
        )
    if (
        isinstance(wanted, list)
        and isinstance(before, list)
        and len(before) == len(wanted)
    ):
        if not isinstance(actual, list) or len(actual) != len(wanted):
            return True
        return any(
            _changed_paths_differ(b, w, a)
            for b, w, a in zip(before, wanted, actual, strict=True)
            if b != w
        )
    return before != wanted and actual != wanted
