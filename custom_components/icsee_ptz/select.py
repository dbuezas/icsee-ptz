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
from .binary_sensor import _run
from .const import CONF_CHANNEL_COUNT, CONF_STEP, DOMAIN
from .coordinator import ICSeeConfigEntry, ICSeeCoordinator
from .entity import (
    ICSeeConfigEntity,
    ICSeeConfigEntityDescription,
    ICSeeEntity,
    config_entities,
    get_path,
)

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
    has_white_light = coordinator.ability(OTHER + "SupportDoubleLightBoxCamera") or (
        coordinator.ability(OTHER + "SupportCameraWhiteLight")
    )
    # On cameras with a white light, 0 ("auto") does not turn on the infrared
    # light at night (seen on an XM530 R80X30); "auto_infrared" (5) does.
    values = [1, 2] if has_white_light else [0, 1, 2]
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
        # XM SDK header: 0 = average metering, 1 = center metering
        key="metering",
        translation_key="metering",
        config="Camera.ParamEx",
        path=("AeMeansure",),
        value_map={0: "average", 1: "center"},
        entity_category=EntityCategory.CONFIG,
    ),
    ICSeeSelectEntityDescription(
        # XM SDK header: 0 = IR-cut switches with the IR light, 1 = switches by itself
        key="ircut_switching",
        translation_key="ircut_switching",
        config="Camera.Param",
        path=("IRCUTMode",),
        value_map={0: "with_ir_light", 1: "automatic"},
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
    ICSeeSelectEntityDescription(
        # values 0..3 confirmed in the app; 1 and 3 are portrait ("corridor")
        key="corridor_mode",
        translation_key="corridor_mode",
        config="Camera.ParamEx",
        path=("CorridorMode",),
        value_map={0: "rotate_0", 1: "rotate_90", 2: "rotate_180", 3: "rotate_270"},
        ability=OTHER + "SupportCorridorMode",
        entity_category=EntityCategory.CONFIG,
    ),
    ICSeeSelectEntityDescription(
        key="time_format",
        translation_key="time_format",
        config="General.Location",
        path=("TimeFormat",),
        value_map={"24": "hours_24", "12": "hours_12"},
        entity_category=EntityCategory.CONFIG,
    ),
    ICSeeSelectEntityDescription(
        key="date_format",
        translation_key="date_format",
        config="General.Location",
        path=("DateFormat",),
        value_map={"YYMMDD": "ymd", "MMDDYY": "mdy", "DDMMYY": "dmy"},
        entity_category=EntityCategory.CONFIG,
    ),
    ICSeeSelectEntityDescription(
        key="auto_restart_day",
        translation_key="auto_restart_day",
        config="General.AutoMaintain",
        path=("AutoRebootDay",),
        value_map={
            d: d.lower()
            for d in (
                "Never",
                "Everyday",
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
                "Saturday",
                "Sunday",
            )
        },
        entity_category=EntityCategory.CONFIG,
    ),
    ICSeeSelectEntityDescription(
        key="human_detection_sensitivity",
        translation_key="human_detection_sensitivity",
        config="Detect.HumanDetection",
        path=("Sensitivity",),
        value_map={0: "low", 1: "medium", 2: "high"},
        # the app hides it when the camera says it has no sensitivity setting
        exists_fn=lambda c, _v: (c.abilities.get("HumanRuleLimit") or {}).get(
            "Sensitivity", True
        )
        is not False,
        entity_category=EntityCategory.CONFIG,
    ),
    ICSeeSelectEntityDescription(
        # a bit mask: 1 = people, 2 = vehicles; 0 on old firmware means people
        key="detection_objects",
        translation_key="detection_objects",
        config="Detect.HumanDetection",
        path=("ObjectType",),
        value_map={1: "people", 2: "vehicles", 3: "people_and_vehicles"},
        to_option=lambda value: {0: "people", 1: "people", 2: "vehicles"}.get(
            value, "people_and_vehicles" if value == 3 else None
        ),
        ability="SystemFunction.AlarmFunction.MultiAlgoCombinePed",
        exists_fn=lambda c, _v: _hex(
            (c.abilities.get("HumanRuleLimit") or {}).get("dwLowObjectType")
        )
        == 3,
        entity_category=EntityCategory.CONFIG,
    ),
    ICSeeSelectEntityDescription(
        # SD card recording; the app's "on" is ConfigRecord (by the schedule)
        key="recording_mode",
        translation_key="recording_mode",
        config="Record",
        path=("RecordMode",),
        value_map={
            "ConfigRecord": "schedule",
            "ManualRecord": "always",
            "ClosedRecord": "off",
        },
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
    entities: list[SelectEntity] = config_entities(coordinator, SELECTS, ICSeeSelect)
    entities += [
        PtzPresetSelect(coordinator, channel)
        for channel in range(entry.data.get(CONF_CHANNEL_COUNT, 1))
        if coordinator.channel_value("Uart.PTZPreset", channel)
    ]
    entities += config_entities(coordinator, (SMART_ENCODE,), SmartEncodeSelect)
    entities += config_entities(coordinator, OSD_POSITIONS, OsdPositionSelect)
    async_add_entities(entities)


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


class PtzPresetSelect(ICSeeEntity, SelectEntity):
    """Go to one of the PTZ positions saved on the camera."""

    _attr_translation_key = "ptz_preset"
    _attr_current_option = None  # an action, not a state

    def __init__(self, coordinator: ICSeeCoordinator, channel: int) -> None:
        super().__init__(coordinator, f"ptz_preset_{channel}", channel)

    def _presets(self) -> dict[str, int]:
        presets = self.coordinator.channel_value("Uart.PTZPreset", self.channel) or []
        return {
            p.get("PresetName") or f"Preset {p['Id']}": int(p["Id"])
            for p in presets
            if isinstance(p, dict) and "Id" in p
        }

    @property
    def options(self) -> list[str]:
        return list(self._presets())

    async def async_select_option(self, option: str) -> None:
        if (preset := self._presets().get(option)) is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_option",
                translation_placeholders={"option": option},
            )
        step = self.coordinator.config_entry.options.get(CONF_STEP, 2)
        await _run(self.device.async_ptz("GotoPreset", step, preset, self.channel))


def _intel264(coordinator: ICSeeCoordinator, field: str) -> bool:
    values = (coordinator.abilities.get("Encode264ability") or {}).get(field) or []
    return bool(values) and _hex(values[0]) not in (None, 0)


# Main stream "smart" encoding, as in the app: H264 / H264+ / H265X
SMART_ENCODE = ICSeeSelectEntityDescription(
    key="smart_encoding",
    translation_key="smart_encoding",
    config="AVEnc.SmartH264V2",
    path=("Smart264V2", 0, "SmartH264"),
    exists_fn=lambda c, _v: _intel264(c, "uIntel264") or _intel264(c, "uIntel264Plus"),
    entity_category=EntityCategory.CONFIG,
)


class SmartEncodeSelect(ICSeeConfigEntity, SelectEntity):
    entity_description: ICSeeSelectEntityDescription

    @property
    def options(self) -> list[str]:
        options = ["h264"]
        if _intel264(self.coordinator, "uIntel264"):
            options.append("h264_plus")
        if _intel264(self.coordinator, "uIntel264Plus"):
            options.append("h265x")
        return options

    @property
    def current_option(self) -> str | None:
        value = self.coordinator.channel_value("AVEnc.SmartH264V2", self.channel)
        if not isinstance(value, dict):
            return None
        smart = get_path(value, ("Smart264V2", 0, "SmartH264"))
        plus = get_path(value, ("Smart264PlusV2", 0, "SmartH264Plus"))
        if not smart:
            return "h264"
        return "h265x" if plus else "h264_plus"

    async def async_select_option(self, option: str) -> None:
        if option not in self.options:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_option",
                translation_placeholders={"option": option},
            )
        await self.async_write_fields(
            {
                ("Smart264V2", 0, "SmartH264"): option != "h264",
                ("Smart264PlusV2", 0, "SmartH264Plus"): 1 if option == "h265x" else 0,
            }
        )


# ---- Position of the time and the camera name on the video -------------------

# RelativePos is [x, y, ?, ?] with x and y in 0..8191 of the picture size. The
# app puts the text 10 px (of a 16:9 phone preview) from the corner.
OSD_SCALE = 8191
OSD_MARGIN_X = 76
OSD_MARGIN_Y = 135
OSD_CHAR_WIDTH = 100  # about one character, in 0..8191 units
OSD_BOTTOM_Y = 7552  # top of the text when it is at the bottom
OSD_TIME_CHARS = 20  # "2026-01-31 12:00:00" and a little more


@dataclass(frozen=True, kw_only=True)
class OsdPositionEntityDescription(ICSeeSelectEntityDescription):
    text_chars: Callable[[Any], int]


OSD_POSITIONS: tuple[OsdPositionEntityDescription, ...] = (
    OsdPositionEntityDescription(
        key="time_position",
        translation_key="time_position",
        config="AVEnc.VideoWidget",
        path=("TimeTitleAttribute", "RelativePos"),
        text_chars=lambda _widget: OSD_TIME_CHARS,
        entity_category=EntityCategory.CONFIG,
    ),
    OsdPositionEntityDescription(
        key="name_position",
        translation_key="name_position",
        config="AVEnc.VideoWidget",
        path=("ChannelTitleAttribute", "RelativePos"),
        text_chars=lambda widget: len(
            get_path(widget, ("ChannelTitle", "Name")) or "camera"
        ),
        entity_category=EntityCategory.CONFIG,
    ),
)


class OsdPositionSelect(ICSeeConfigEntity, SelectEntity):
    """Put the text in one corner of the picture."""

    entity_description: OsdPositionEntityDescription
    _attr_options = ["top_left", "top_right", "bottom_left", "bottom_right"]

    @property
    def current_option(self) -> str | None:
        pos = self.config_value
        if not isinstance(pos, list) or len(pos) < 2:
            return None
        top = "top" if pos[1] < OSD_SCALE / 2 else "bottom"
        left = "left" if pos[0] < OSD_SCALE / 2 else "right"
        return f"{top}_{left}"

    async def async_select_option(self, option: str) -> None:
        if option not in self.options:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_option",
                translation_placeholders={"option": option},
            )
        widget = self.coordinator.channel_value(
            self.entity_description.config, self.channel
        )
        width = self.entity_description.text_chars(widget) * OSD_CHAR_WIDTH
        x = (
            OSD_MARGIN_X
            if option.endswith("left")
            else OSD_SCALE - OSD_MARGIN_X - width
        )
        y = OSD_MARGIN_Y if option.startswith("top") else OSD_BOTTOM_Y
        pos = list(self.config_value)
        pos[0], pos[1] = max(0, x), y
        await self.async_write_value(pos)
