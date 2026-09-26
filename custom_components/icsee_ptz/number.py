"""Numbers for camera settings."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfDataRate, UnitOfTime
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
class ICSeeNumberEntityDescription(
    ICSeeConfigEntityDescription, NumberEntityDescription
):
    """A number backed by a config field."""

    to_value: Callable[[Any], float] = float
    to_raw: Callable[[float], Any] = int
    # more fields that get the same raw value (e.g. right speaker volume)
    also_paths: tuple[tuple[str | int, ...], ...] = ()
    max_fn: Callable[[ICSeeCoordinator, int], float] | None = None


def _fps_max(stream: str) -> Callable[[ICSeeCoordinator, int], float]:
    def max_fps(coordinator: ICSeeCoordinator, channel: int) -> float:
        ntsc = encode.is_ntsc(coordinator.channel_value("General.Location", 0))
        return encode.stream_max_fps(
            coordinator.abilities.get("EncodeCapability") or {},
            coordinator.channel_value("Simplify.Encode", channel) or {},
            stream,
            channel,
            ntsc,
        )

    return max_fps


def _encode(stream: str, prefix: str) -> tuple[ICSeeNumberEntityDescription, ...]:
    return (
        ICSeeNumberEntityDescription(
            key=f"{prefix}_fps",
            translation_key=f"{prefix}_fps",
            config="Simplify.Encode",
            path=(stream, "Video", "FPS"),
            native_min_value=1,
            native_max_value=30,
            native_step=1,
            max_fn=_fps_max(stream),
            mode=NumberMode.SLIDER,
            entity_category=EntityCategory.CONFIG,
        ),
        ICSeeNumberEntityDescription(
            key=f"{prefix}_bitrate",
            translation_key=f"{prefix}_bitrate",
            config="Simplify.Encode",
            path=(stream, "Video", "BitRate"),
            native_min_value=16,
            native_max_value=49152,
            native_step=1,
            max_fn=lambda c, _ch: float(
                (c.abilities.get("EncodeCapability") or {}).get("MaxBitrate") or 49152
            ),
            mode=NumberMode.BOX,
            device_class=NumberDeviceClass.DATA_RATE,
            native_unit_of_measurement=UnitOfDataRate.KILOBITS_PER_SECOND,
            entity_category=EntityCategory.CONFIG,
        ),
        ICSeeNumberEntityDescription(
            key=f"{prefix}_gop",
            translation_key=f"{prefix}_gop",
            config="Simplify.Encode",
            path=(stream, "Video", "GOP"),
            native_min_value=1,
            native_max_value=12,
            native_step=1,
            mode=NumberMode.BOX,
            native_unit_of_measurement=UnitOfTime.SECONDS,
            entity_category=EntityCategory.CONFIG,
        ),
    )


def _color(field: str, key: str) -> ICSeeNumberEntityDescription:
    return ICSeeNumberEntityDescription(
        key=key,
        translation_key=key,
        config="AVEnc.VideoColor",
        path=(0, "VideoColorParam", field),  # first time section
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.CONFIG,
    )


NUMBERS: tuple[ICSeeNumberEntityDescription, ...] = (
    *_encode(encode.MAIN, "main_stream"),
    *_encode(encode.SUB, "sub_stream"),
    ICSeeNumberEntityDescription(
        key="speaker_volume",
        translation_key="speaker_volume",
        config="fVideo.Volume",
        path=("LeftVolume",),
        also_paths=(("RightVolume",),),
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        ability=OTHER + "SupportSetVolume",
        entity_category=EntityCategory.CONFIG,
    ),
    ICSeeNumberEntityDescription(
        key="microphone_volume",
        translation_key="microphone_volume",
        config="fVideo.InVolume",
        path=("LeftVolume",),
        also_paths=(("RightVolume",),),
        native_min_value=1,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.CONFIG,
    ),
    ICSeeNumberEntityDescription(
        key="white_light_brightness",
        translation_key="white_light_brightness",
        config="Camera.WhiteLight",
        path=("Brightness",),
        native_min_value=1,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        ability=OTHER + "SupportCameraWhiteLight",
        entity_category=EntityCategory.CONFIG,
    ),
    ICSeeNumberEntityDescription(
        key="white_light_duration",
        translation_key="white_light_duration",
        config="Camera.WhiteLight",
        path=("MoveTrigLight", "Duration"),
        native_min_value=5,
        native_max_value=300,
        native_step=1,
        mode=NumberMode.BOX,
        device_class=NumberDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        ability=OTHER + "SupportCameraWhiteLight",
        entity_category=EntityCategory.CONFIG,
    ),
    _color("Brightness", "image_brightness"),
    _color("Contrast", "image_contrast"),
    _color("Saturation", "image_saturation"),
    _color("Hue", "image_hue"),
    ICSeeNumberEntityDescription(
        key="anti_fog_level",
        translation_key="anti_fog_level",
        config="Camera.ClearFog",
        path=("level",),
        native_min_value=1,
        native_max_value=100,
        native_step=1,
        entity_category=EntityCategory.CONFIG,
    ),
    ICSeeNumberEntityDescription(
        key="motion_sensitivity",
        translation_key="motion_sensitivity",
        config="Detect.MotionDetect",
        path=("Level",),
        native_min_value=1,
        native_max_value=6,
        native_step=1,
        ability="SystemFunction.AlarmFunction.MotionDetect",
        entity_category=EntityCategory.CONFIG,
    ),
    ICSeeNumberEntityDescription(
        # The app shows 0..10 and stores DncThr = 50 - 4 * level
        key="day_night_sensitivity",
        translation_key="day_night_sensitivity",
        config="Camera.Param",
        path=("DncThr",),
        native_min_value=0,
        native_max_value=10,
        native_step=1,
        to_value=lambda raw: float(max(0, min(10, round((50 - int(raw)) / 4)))),
        to_raw=lambda value: 50 - 4 * int(value),
        ability=OTHER + "SupportDNChangeByImage",
        entity_category=EntityCategory.CONFIG,
    ),
    ICSeeNumberEntityDescription(
        key="soft_light_threshold",
        translation_key="soft_light_threshold",
        config="Camera.ParamEx",
        path=("SoftLedThr",),
        native_min_value=1,
        native_max_value=5,
        native_step=1,
        entity_category=EntityCategory.CONFIG,
    ),
    ICSeeNumberEntityDescription(
        key="auto_restart_hour",
        translation_key="auto_restart_hour",
        config="General.AutoMaintain",
        path=("AutoRebootHour",),
        native_min_value=0,
        native_max_value=23,
        native_step=1,
        entity_category=EntityCategory.CONFIG,
    ),
    ICSeeNumberEntityDescription(
        key="tracking_return_time",
        translation_key="tracking_return_time",
        config="Detect.DetectTrack",
        path=("ReturnTime",),
        native_min_value=3,
        native_max_value=1800,
        native_step=1,
        mode=NumberMode.BOX,
        device_class=NumberDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        ability=OTHER + "SupportDetectTrack",
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ICSeeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(config_entities(coordinator, NUMBERS, ICSeeNumber))


class ICSeeNumber(ICSeeConfigEntity, NumberEntity):
    entity_description: ICSeeNumberEntityDescription

    @property
    def native_value(self) -> float | None:
        value = self.config_value
        if value is None:
            return None
        try:
            return self.entity_description.to_value(value)
        except (TypeError, ValueError):
            return None

    @property
    def native_max_value(self) -> float:
        desc = self.entity_description
        if desc.max_fn:
            return desc.max_fn(self.coordinator, self.channel)
        return super().native_max_value

    async def async_set_native_value(self, value: float) -> None:
        desc = self.entity_description
        raw = desc.to_raw(value)
        if desc.config == "Simplify.Encode" and desc.path[-1] == "FPS":
            self._check_budget(raw)
        fields = {desc.path: raw}
        for path in desc.also_paths:
            if path[-1] in (
                self.coordinator.channel_value(desc.config, self.channel) or {}
            ):
                fields[path] = raw
        await self.async_write_fields(fields)

    def _check_budget(self, fps: int) -> None:
        coordinator = self.coordinator
        stream = self.entity_description.path[0]
        enc = coordinator.channel_value("Simplify.Encode", self.channel)
        planned = {
            **enc,
            stream: {**enc[stream], "Video": {**enc[stream]["Video"], "FPS": fps}},
        }
        ntsc = encode.is_ntsc(coordinator.channel_value("General.Location", 0))
        capability = coordinator.abilities.get("EncodeCapability") or {}
        if not encode.fits(capability, planned, self.channel, ntsc):
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="over_encode_budget"
            )
