"""Reads and writes the camera configs."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import copy
from dataclasses import dataclass
import functools
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, RET_NEEDS_REBOOT, SCAN_INTERVAL
from .device import (
    AuthFailed,
    CannotConnect,
    CommandFailed,
    ConfigNotSupported,
    ICSeeDevice,
)

_LOGGER = logging.getLogger(__name__)

# Most settings only change when the user writes them (and the write reads itself
# back). Re-reading all ~50 configs takes ~200ms each = ~10s of camera work, which
# starves the video encoder and PTZ. So read the whole set only once at startup;
# after that read only the "live" ones each poll. The "Refresh settings" button
# forces a full re-read on demand (e.g. after changing something in the phone app).

# A config that does not answer at startup (e.g. the camera was busy or still
# booting) used to be dropped forever, which left the camera on an unplayable
# fallback stream until a restart. Instead, keep retrying such a config on the next
# few polls, then give up so a genuinely silent config does not waste CPU/network.
RETRY_BUDGET = 3


class NoAnswer(Exception):
    """The camera did not answer a read twice (it probably does not know it)."""


@dataclass(frozen=True)
class ConfigSpec:
    """How a config is laid out on the camera."""

    per_channel: bool  # the value is a list with one element per channel
    channel_suffix: bool = (
        True  # write one channel as "Name.[ch]" (else the whole list)
    )
    code: int = 1042  # read command: 1042 config, 1020 status, 1472 users
    live: bool = False  # re-read every poll (changes on its own); else read rarely


CONFIGS: dict[str, ConfigSpec] = {
    "Camera.Param": ConfigSpec(per_channel=True),
    "Camera.ParamEx": ConfigSpec(per_channel=True),
    "Camera.ClearFog": ConfigSpec(per_channel=True),
    "Camera.WhiteLight": ConfigSpec(per_channel=False),
    "Simplify.Encode": ConfigSpec(per_channel=True, channel_suffix=False),
    "AVEnc.VideoColor": ConfigSpec(per_channel=True),
    "fVideo.Volume": ConfigSpec(per_channel=True),
    "fVideo.InVolume": ConfigSpec(per_channel=True),
    "fVideo.VolumeIn": ConfigSpec(per_channel=True),  # microphone on some cameras
    "AVEnc.SmartH264V2": ConfigSpec(per_channel=True),  # H.264+ / H.265X
    "NetWork.OnvifPwdCheckout": ConfigSpec(per_channel=False),
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
    "Record": ConfigSpec(per_channel=True),  # SD card recording
    # read only status
    "Users": ConfigSpec(per_channel=False, code=1472),
    "WifiRouteInfo": ConfigSpec(per_channel=False, code=1020, live=True),
    "Status.NatInfo": ConfigSpec(per_channel=False, live=True),  # cloud connection
    "StorageInfo": ConfigSpec(per_channel=False, code=1020, live=True),  # SD card
    "WorkState": ConfigSpec(per_channel=False, code=1020, live=True),  # alarm state
}

# Abilities (cmd 1360) read once at setup
ABILITIES = (
    "SystemFunction",
    "EncodeCapability",
    "Camera",
    "Encode264ability",
    "HumanRuleLimit",  # human and vehicle detection options
)

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
        self._force_full = False  # set by the Refresh button to re-read everything
        self._retry: dict[str, int] = (
            {}
        )  # configs that have not answered yet -> tries left

    async def _async_setup(self) -> None:
        """Read the device info and abilities once."""
        try:
            self.system_info = await self.device.async_get_system_info() or {}
            for name in ABILITIES:
                try:
                    self.abilities[name] = await self._read_retry(
                        name, self.device.async_get_ability
                    )
                except (ConfigNotSupported, CommandFailed, NoAnswer):
                    self.abilities[name] = {}
        except (CannotConnect, AuthFailed) as err:
            raise UpdateFailed(
                translation_domain=DOMAIN, translation_key="cannot_connect"
            ) from err

    async def _read_retry(
        self, name: str, read: Callable[[str], Awaitable[Any]]
    ) -> Any:
        """Read once more on a new connection if the camera does not answer.

        Some cameras and recorders never answer some names. Raise NoAnswer if it
        does not answer twice, or CannotConnect if the camera is gone.
        """
        try:
            return await read(name)
        except CannotConnect as err:
            _LOGGER.debug("No answer for %s: %s", name, err)
        await self.device.async_reset_commands()
        try:
            return await read(name)
        except CannotConnect as err:
            _LOGGER.debug("No answer for %s again: %s", name, err)
        await self.device.async_reset_commands()
        raise NoAnswer(name)

    async def _async_update_data(self) -> dict[str, Any]:
        data = dict(self.data or {})
        first = self.supported is None
        rediscover = first or self._force_full  # startup or the Refresh button
        self._force_full = False
        supported = set(self.supported or ())
        if rediscover:
            names = list(CONFIGS)  # try every config
        else:
            # normal poll: the values that change on their own, plus any config
            # that has not answered yet and still has retries left
            names = sorted({n for n in supported if CONFIGS[n].live} | set(self._retry))
        try:
            for name in names:
                code = CONFIGS[name].code
                if code == 1042:
                    read = self.device.async_get_config
                else:
                    read = functools.partial(self.device.async_get_value, code=code)
                try:
                    data[name] = await self._read_retry(name, read)
                    supported.add(name)
                    self._retry.pop(name, None)
                except ConfigNotSupported:
                    data.pop(name, None)  # the camera really lacks it: stop asking
                    supported.discard(name)
                    self._retry.pop(name, None)
                except (CommandFailed, NoAnswer) as err:
                    _LOGGER.debug("Reading %s failed: %s", name, err)
                    if name not in supported:
                        # unknown config (e.g. camera busy at boot): retry a few
                        # more polls, then give up so we don't waste CPU/network
                        left = self._retry.get(name, RETRY_BUDGET) - 1
                        if left > 0:
                            self._retry[name] = left
                        else:
                            self._retry.pop(name, None)
                    # a config we have seen before keeps its last known value
        except (CannotConnect, AuthFailed) as err:
            raise UpdateFailed(
                translation_domain=DOMAIN, translation_key="cannot_connect"
            ) from err
        self.supported = supported
        return data

    async def async_refresh_all(self) -> None:
        """Re-read every setting once now (the Refresh settings button)."""
        self._force_full = True
        await self.async_request_refresh()

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
