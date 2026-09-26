"""Camera entities. Home Assistant's built-in go2rtc plays the DVRIP stream."""

from __future__ import annotations

from urllib.parse import quote

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_CHANNEL_COUNT
from .coordinator import ICSeeConfigEntry, ICSeeCoordinator
from .entity import ICSeeEntity

PARALLEL_UPDATES = 0

STREAMS = (("main", 0), ("sub", 1))  # (translation/unique key, dvrip subtype)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ICSeeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        ICSeeCamera(coordinator, stream, subtype, channel)
        for channel in range(entry.data.get(CONF_CHANNEL_COUNT, 1))
        for stream, subtype in STREAMS
    )


class ICSeeCamera(ICSeeEntity, Camera):
    _attr_supported_features = CameraEntityFeature.STREAM

    def __init__(
        self, coordinator: ICSeeCoordinator, stream: str, subtype: int, channel: int
    ) -> None:
        ICSeeEntity.__init__(self, coordinator, f"camera_{stream}_{channel}", channel)
        Camera.__init__(self)
        self._attr_translation_key = f"{stream}_stream"
        self._subtype = subtype

    @property
    def available(self) -> bool:
        return self.device.is_connected

    @property
    def use_stream_for_stills(self) -> bool:
        # Snapshots come from the stream (via go2rtc); OPSNAP is not supported by many cameras
        return True

    async def stream_source(self) -> str:
        device = self.device
        user = quote(device.username, safe="")
        password = quote(device.password, safe="")
        return (
            f"dvrip://{user}:{password}@{device.host}:{device.port}"
            f"?channel={self.channel}&subtype={self._subtype}"
        )

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        return None
