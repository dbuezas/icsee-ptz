"""Selects for camera settings."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import encode
from .const import DOMAIN
from .coordinator import ICSeeConfigEntry, ICSeeCoordinator
from .entity import ICSeeConfigEntity, ICSeeConfigEntityDescription, config_entities

PARALLEL_UPDATES = 1

OTHER = "SystemFunction.OtherFunction."


@dataclass(frozen=True, kw_only=True)
class ICSeeSelectEntityDescription(
    ICSeeConfigEntityDescription, SelectEntityDescription
):
    """A select that maps camera values to option keys."""

    # camera value <-> option (option names are translation keys)
    value_map: dict[Any, str] | None = None
    # options for this camera; default: all of value_map
    options_fn: Callable[[ICSeeCoordinator, int, Any], list[str]] | None = None
    to_option: Callable[[Any], str | None] | None = None


# ---- Day/night (image + infrared) mode ------------------------------------

DAY_NIGHT = {
    0: "auto",
    1: "color",
    2: "black_white",
    3: "smart_alarm_light",
    4: "auto_white_light",
    5: "auto_infrared",
    6: "license_plate",
}


def _hex(value: Any) -> int | None:
    try:
        return int(value, 16) if isinstance(value, str) else int(value)
    except (TypeError, ValueError):
        return None


def _day_night_options(
    coordinator: ICSeeCoordinator, channel: int, value: Any
) -> list[str]:
    values = [0, 1, 2]
    has_white_light = coordinator.ability(OTHER + "SupportDoubleLightBoxCamera") or (
        coordinator.ability(OTHER + "SupportCameraWhiteLight")
    )
    if coordinator.ability(OTHER + "SupportSoftPhotosensitive") or has_white_light:
        values += [4, 5]
    if coordinator.ability("Camera.SupportIntellDoubleLight") or has_white_light:
        values.append(3)
    if (current := _hex(value)) in DAY_NIGHT and current not in values:
        values.append(current)
    return [DAY_NIGHT[v] for v in sorted(values)]


# ---- White light -----------------------------------------------------------

WHITE_LIGHT_MODES = {
    "Close": "close",
    "KeepOpen": "keep_open",
    "Auto": "auto",
    "Timing": "timing",
    "Intelligent": "intelligent",
    "Atmosphere": "atmosphere",
    "Glint": "glint",
}


def _white_light_options(
    coordinator: ICSeeCoordinator, channel: int, value: Any
) -> list[str]:
    if coordinator.ability(OTHER + "NotSupportAutoAndIntelligent"):
        modes = ["Close", "KeepOpen"]
    else:
        modes = ["Close", "KeepOpen", "Auto", "Timing"]
        if "MoveTrigLight" in (coordinator.channel_value("Camera.WhiteLight", 0) or {}):
            modes.append("Intelligent")
        if coordinator.ability(OTHER + "SupportMusicLightBulb"):
            modes += ["Atmosphere", "Glint"]
    if value in WHITE_LIGHT_MODES and value not in modes:
        modes.append(value)
    return [WHITE_LIGHT_MODES[m] for m in modes]


def _white_light_level(value: Any) -> str | None:
    try:
        level = int(value)
    except (TypeError, ValueError):
        return None
    return "low" if level <= 2 else "medium" if level == 3 else "high"


# ---- Encoding ----------------------------------------------------------------


def _encode_options(kind: str, stream: str):
    def options(coordinator: ICSeeCoordinator, channel: int, value: Any) -> list[str]:
        capability = coordinator.abilities.get("EncodeCapability") or {}
        enc = coordinator.channel_value("Simplify.Encode", channel) or {}
        if kind == "resolution":
            return encode.resolution_options(capability, enc, stream, channel)
        return encode.compression_options(capability, enc, stream)

    return options


QUALITY = {1: "bad", 2: "poor", 3: "general", 4: "good", 5: "better", 6: "best"}


def _encode(stream: str, prefix: str) -> tuple[ICSeeSelectEntityDescription, ...]:
    return (
        ICSeeSelectEntityDescription(
            key=f"{prefix}_resolution",
            translation_key=f"{prefix}_resolution",
            config="Simplify.Encode",
            path=(stream, "Video", "Resolution"),
            options_fn=_encode_options("resolution", stream),
            entity_category=EntityCategory.CONFIG,
        ),
        ICSeeSelectEntityDescription(
            key=f"{prefix}_quality",
            translation_key=f"{prefix}_quality",
            config="Simplify.Encode",
            path=(stream, "Video", "Quality"),
            value_map=QUALITY,
            entity_category=EntityCategory.CONFIG,
        ),
        ICSeeSelectEntityDescription(
            key=f"{prefix}_codec",
            translation_key=f"{prefix}_codec",
            config="Simplify.Encode",
            path=(stream, "Video", "Compression"),
            options_fn=_encode_options("compression", stream),
            entity_category=EntityCategory.CONFIG,
        ),
        ICSeeSelectEntityDescription(
            key=f"{prefix}_bitrate_control",
            translation_key=f"{prefix}_bitrate_control",
            config="Simplify.Encode",
            path=(stream, "Video", "BitRateControl"),
            value_map={"CBR": "cbr", "VBR": "vbr"},
            entity_category=EntityCategory.CONFIG,
        ),
    )


SELECTS: tuple[ICSeeSelectEntityDescription, ...] = (
    ICSeeSelectEntityDescription(
        key="DayNightColorSelect",  # legacy unique id
        translation_key="day_night_mode",
        config="Camera.Param",
        path=("DayNightColor",),
        value_map={f"0x{k:08X}": v for k, v in DAY_NIGHT.items()},
        options_fn=_day_night_options,
        to_option=lambda value: DAY_NIGHT.get(_hex(value)),  # type: ignore[arg-type]
    ),
    ICSeeSelectEntityDescription(
        key="WhiteLightSelect",  # legacy unique id
        translation_key="white_light_mode",
        config="Camera.WhiteLight",
        path=("WorkMode",),
        value_map=WHITE_LIGHT_MODES,
        options_fn=_white_light_options,
        ability=OTHER + "SupportCameraWhiteLight",
    ),
    ICSeeSelectEntityDescription(
        key="white_light_sensitivity",
        translation_key="white_light_sensitivity",
        config="Camera.WhiteLight",
        path=("MoveTrigLight", "Level"),
        value_map={1: "low", 3: "medium", 5: "high"},
        to_option=_white_light_level,
        ability=OTHER + "SupportCameraWhiteLight",
        entity_category=EntityCategory.CONFIG,
    ),
    ICSeeSelectEntityDescription(
        key="day_night_switch",
        translation_key="day_night_switch",
        config="Camera.ParamEx",
        path=("DayNightSwitch", "SwitchMode"),
        value_map={0: "auto", 1: "day", 2: "night", 3: "scheduled"},
        entity_category=EntityCategory.CONFIG,
    ),
    ICSeeSelectEntityDescription(
        key="image_style",
        translation_key="image_style",
        config="Camera.ParamEx",
        path=("Style",),
        value_map={"typedefault": "style_1", "type1": "style_2", "type2": "style_3"},
        entity_category=EntityCategory.CONFIG,
    ),
    ICSeeSelectEntityDescription(
        key="tracking_sensitivity",
        translation_key="tracking_sensitivity",
        config="Detect.DetectTrack",
        path=("Sensitivity",),
        value_map={0: "low", 1: "medium", 2: "high"},
        ability=OTHER + "SupportDetectTrack",
        entity_category=EntityCategory.CONFIG,
    ),
    *_encode(encode.MAIN, "main_stream"),
    *_encode(encode.SUB, "sub_stream"),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ICSeeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(config_entities(coordinator, SELECTS, ICSeeSelect))


class ICSeeSelect(ICSeeConfigEntity, SelectEntity):
    entity_description: ICSeeSelectEntityDescription

    @property
    def options(self) -> list[str]:
        desc = self.entity_description
        if desc.options_fn:
            return desc.options_fn(self.coordinator, self.channel, self.config_value)
        return list((desc.value_map or {}).values())

    @property
    def current_option(self) -> str | None:
        desc = self.entity_description
        value = self.config_value
        if value is None:
            return None
        if desc.to_option:
            return desc.to_option(value)
        if desc.value_map is None:
            return str(value)
        return desc.value_map.get(value)

    async def async_select_option(self, option: str) -> None:
        desc = self.entity_description
        if desc.value_map is None:
            value: Any = option
        else:
            value = next((k for k, v in desc.value_map.items() if v == option), None)
        if value is None or option not in self.options:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_option",
                translation_placeholders={"option": option},
            )
        if desc.config == "Simplify.Encode" and desc.path[-1] == "Resolution":
            self._check_budget(value)
        await self.async_write_value(value)

    def _check_budget(self, resolution: str) -> None:
        coordinator = self.coordinator
        enc = coordinator.channel_value("Simplify.Encode", self.channel)
        ntsc = encode.is_ntsc(coordinator.channel_value("General.Location", 0))
        capability = coordinator.abilities.get("EncodeCapability") or {}
        planned = {
            **enc,
            self.entity_description.path[0]: {**enc[self.entity_description.path[0]]},
        }
        planned[self.entity_description.path[0]]["Video"] = {
            **planned[self.entity_description.path[0]]["Video"],
            "Resolution": resolution,
        }
        if not encode.fits(capability, planned, self.channel, ntsc):
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="over_encode_budget"
            )
