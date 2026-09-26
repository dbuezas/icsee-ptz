"""Switches for camera settings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ICSeeConfigEntry
from .entity import ICSeeConfigEntity, ICSeeConfigEntityDescription, config_entities

PARALLEL_UPDATES = 1

HEX_ON, HEX_OFF = "0x00000001", "0x00000000"


@dataclass(frozen=True, kw_only=True)
class ICSeeSwitchEntityDescription(
    ICSeeConfigEntityDescription, SwitchEntityDescription
):
    """A switch that writes on_value/off_value into a config field."""

    on_value: Any = True
    off_value: Any = False


def _alarm(
    key: str, config: str, ability: str, translation_key: str, enabled: bool = True
):
    return ICSeeSwitchEntityDescription(
        key=key,  # legacy unique id: {serial}_{key}_{channel}
        translation_key=translation_key,
        config=config,
        path=("Enable",),
        ability=f"SystemFunction.AlarmFunction.{ability}",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=enabled,
    )


def _param_ex(key: str, field: str | tuple[str, ...], **kwargs: Any):
    path = (field,) if isinstance(field, str) else field
    kwargs = {
        "on_value": 1,
        "off_value": 0,
        "entity_category": EntityCategory.CONFIG,
        **kwargs,
    }
    return ICSeeSwitchEntityDescription(
        key=key, translation_key=key, config="Camera.ParamEx", path=path, **kwargs
    )


SWITCHES: tuple[ICSeeSwitchEntityDescription, ...] = (
    _alarm("MotionDetect", "Detect.MotionDetect", "MotionDetect", "motion_detection"),
    # "HumanDection" (sic) is how the camera spells the ability
    _alarm(
        "HumanDetection", "Detect.HumanDetection", "HumanDection", "human_detection"
    ),
    _alarm(
        "BlindDetect",
        "Detect.BlindDetect",
        "BlindDetect",
        "tamper_detection",
        enabled=False,
    ),
    _alarm(
        "LossDetect",
        "Detect.LossDetect",
        "LossDetect",
        "video_loss_detection",
        enabled=False,
    ),
    _alarm(
        "CarShapeDetection",
        "Detect.CarShapeDetection",
        "CarShapeDetection",
        "vehicle_detection",
    ),
    ICSeeSwitchEntityDescription(
        key="motion_tracking",
        translation_key="motion_tracking",
        config="Detect.DetectTrack",
        path=("Enable",),
        on_value=1,
        off_value=0,
        ability="SystemFunction.OtherFunction.SupportDetectTrack",
        entity_category=EntityCategory.CONFIG,
    ),
    ICSeeSwitchEntityDescription(
        key="white_light",
        translation_key="white_light",
        config="Camera.WhiteLight",
        path=("WorkMode",),
        on_value="KeepOpen",
        off_value="Close",
        ability="SystemFunction.OtherFunction.SupportCameraWhiteLight",
    ),
    _param_ex(
        "white_light_one_key",
        "OneKeyOpenWL",
        on_value=True,
        off_value=False,
        entity_category=None,
    ),
    _param_ex("night_vision", "OpenDNC", on_value=True, off_value=False),
    _param_ex("night_enhance", "NightEnhance"),
    _param_ex("low_light_fill", "MicroFillLight"),
    _param_ex("starlight", "LowLuxMode", entity_registry_enabled_default=False),
    _param_ex(
        "wdr", ("BroadTrends", "AutoGain"), entity_registry_enabled_default=False
    ),
    _param_ex(
        "prevent_overexposure",
        "PreventOverExpo",
        ability="Camera.SupportPreventOverExpo",
        entity_registry_enabled_default=False,
    ),
    ICSeeSwitchEntityDescription(
        key="picture_flip",
        translation_key="picture_flip",
        config="Camera.Param",
        path=("PictureFlip",),
        on_value=HEX_ON,
        off_value=HEX_OFF,
        entity_category=EntityCategory.CONFIG,
    ),
    ICSeeSwitchEntityDescription(
        key="picture_mirror",
        translation_key="picture_mirror",
        config="Camera.Param",
        path=("PictureMirror",),
        on_value=HEX_ON,
        off_value=HEX_OFF,
        entity_category=EntityCategory.CONFIG,
    ),
    ICSeeSwitchEntityDescription(
        key="ircut_reverse",
        translation_key="ircut_reverse",
        config="Camera.Param",
        path=("IrcutSwap",),
        on_value=1,
        off_value=0,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ICSeeSwitchEntityDescription(
        key="anti_fog",
        translation_key="anti_fog",
        config="Camera.ClearFog",
        path=("enable",),
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ICSeeSwitchEntityDescription(
        key="privacy_mode",
        translation_key="privacy_mode",
        config="General.OneKeyMaskVideo",
        path=("Enable",),
        ability="SystemFunction.OtherFunction.SupportOneKeyMaskVideo",
    ),
    ICSeeSwitchEntityDescription(
        key="sleep_schedule",
        translation_key="sleep_schedule",
        config="General.TimingSleep",
        path=("Enable",),
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ICSeeSwitchEntityDescription(
        key="status_led",
        translation_key="status_led",
        config="FbExtraStateCtrl",
        path=("ison",),
        on_value=1,
        off_value=0,
        entity_category=EntityCategory.CONFIG,
    ),
    ICSeeSwitchEntityDescription(
        key="voice_prompts",
        translation_key="voice_prompts",
        config="FbExtraStateCtrl",
        path=("PlayVoiceTip",),
        on_value=1,
        off_value=0,
        entity_category=EntityCategory.CONFIG,
    ),
    ICSeeSwitchEntityDescription(
        key="cloud_access",
        translation_key="cloud_access",
        config="NetWork.Nat",
        path=("NatEnable",),
        entity_category=EntityCategory.CONFIG,
    ),
    ICSeeSwitchEntityDescription(
        key="cloud_push",
        translation_key="cloud_push",
        config="NetWork.PMS",
        path=("Enable",),
        entity_category=EntityCategory.CONFIG,
    ),
    ICSeeSwitchEntityDescription(
        key="password_reset_by_code",
        translation_key="password_reset_by_code",
        config="General.PwdSafety",
        path=("VerifyCodeRestorePwdType",),
        on_value=1,
        off_value=0,
        entity_category=EntityCategory.CONFIG,
    ),
    ICSeeSwitchEntityDescription(
        key="sub_stream",
        translation_key="sub_stream",
        config="Simplify.Encode",
        path=("ExtraFormat", "VideoEnable"),
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ICSeeSwitchEntityDescription(
        key="main_stream_audio",
        translation_key="main_stream_audio",
        config="Simplify.Encode",
        path=("MainFormat", "AudioEnable"),
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ICSeeSwitchEntityDescription(
        key="sub_stream_audio",
        translation_key="sub_stream_audio",
        config="Simplify.Encode",
        path=("ExtraFormat", "AudioEnable"),
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ICSeeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(config_entities(coordinator, SWITCHES, ICSeeSwitch))


class ICSeeSwitch(ICSeeConfigEntity, SwitchEntity):
    entity_description: ICSeeSwitchEntityDescription

    @property
    def is_on(self) -> bool | None:
        value = self.config_value
        if value is None:
            return None
        desc = self.entity_description
        if (
            isinstance(desc.on_value, str)
            and isinstance(value, str)
            and value.startswith("0x")
        ):
            return int(value, 16) == int(desc.on_value, 16)
        if isinstance(desc.on_value, bool):
            return bool(value)
        return value == desc.on_value

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.async_write_value(self.entity_description.on_value)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.async_write_value(self.entity_description.off_value)
