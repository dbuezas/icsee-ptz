"""Camera entities, played by Home Assistant's built-in go2rtc.

The built-in go2rtc has no DVRIP module, so the video comes from the camera's
RTSP server. A repair issue asks to turn it on when it is off.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_CHANNEL_COUNT, DOMAIN
from .coordinator import ICSeeConfigEntry, ICSeeCoordinator
from .entity import ICSeeEntity

PARALLEL_UPDATES = 0

STREAMS = (("main", 0), ("sub", 1))  # (translation/unique key, stream number)


def _rtsp(coordinator: ICSeeCoordinator) -> dict[str, Any] | None:
    return coordinator.channel_value("NetWork.RTSP", 0)


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

    issue_id = f"rtsp_disabled_{entry.entry_id}"

    @callback
    def _check_rtsp() -> None:
        rtsp = _rtsp(coordinator)
        if rtsp is not None and not rtsp.get("IsServer"):
            ir.async_create_issue(
                hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="rtsp_disabled",
                translation_placeholders={"name": entry.title},
            )
        else:
            ir.async_delete_issue(hass, DOMAIN, issue_id)

    _check_rtsp()
    entry.async_on_unload(coordinator.async_add_listener(_check_rtsp))
    entry.async_on_unload(lambda: ir.async_delete_issue(hass, DOMAIN, issue_id))


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
        rtsp = _rtsp(self.coordinator)
        return self.device.is_connected and (rtsp is None or bool(rtsp.get("IsServer")))

    @property
    def use_stream_for_stills(self) -> bool:
        # Snapshots come from the stream (via go2rtc); OPSNAP is not supported by many cameras
        return True

    async def stream_source(self) -> str | None:
        device = self.device
        user = quote(device.username, safe="")
        password = quote(device.password, safe="")
        rtsp = _rtsp(self.coordinator)
        if rtsp is None:
            # Camera without an RTSP config: only an external go2rtc can play this
            return (
                f"dvrip://{user}:{password}@{device.host}:{device.port}"
                f"?channel={self.channel}&subtype={self._subtype}"
            )
        if not rtsp.get("IsServer"):
            return None
        port = (rtsp.get("Server") or {}).get("Port") or 554
        # XM RTSP path; channels start at 1 here
        return (
            f"rtsp://{device.host}:{port}/user={user}&password={password}"
            f"&channel={self.channel + 1}&stream={self._subtype}.sdp?real_stream"
        )

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        return None
