"""Camera speaker as a media player, e.g. for TTS."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components import media_source
from homeassistant.components.ffmpeg import get_ffmpeg_manager
from homeassistant.components.media_player import (
    BrowseMedia,
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
    async_process_play_media_url,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import ICSeeConfigEntry, ICSeeCoordinator
from .device import CannotConnect, CommandFailed
from .entity import ICSeeEntity

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1

ABILITY = "SystemFunction.PreviewFunction.Talk"
VOLUME_ABILITY = "SystemFunction.OtherFunction.SupportSetVolume"
MAX_SECONDS = 300  # longest clip we play
SAMPLE_RATE = 8000  # G.711 A-law, mono, 1 byte per sample


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ICSeeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    if coordinator.ability(ABILITY):
        async_add_entities([ICSeeSpeaker(coordinator)])


class ICSeeSpeaker(ICSeeEntity, MediaPlayerEntity):
    _attr_translation_key = "speaker"
    _attr_device_class = MediaPlayerDeviceClass.SPEAKER
    _attr_media_content_type = MediaType.MUSIC

    def __init__(self, coordinator: ICSeeCoordinator) -> None:
        super().__init__(coordinator, "speaker")
        self._task: asyncio.Task | None = None
        features = (
            MediaPlayerEntityFeature.PLAY_MEDIA
            | MediaPlayerEntityFeature.BROWSE_MEDIA
            | MediaPlayerEntityFeature.MEDIA_ANNOUNCE
            | MediaPlayerEntityFeature.STOP
        )
        if self._volume_config() is not None and coordinator.ability(VOLUME_ABILITY):
            features |= MediaPlayerEntityFeature.VOLUME_SET
        self._attr_supported_features = features

    def _volume_config(self) -> dict[str, Any] | None:
        return self.coordinator.channel_value("fVideo.Volume", 0)

    @property
    def available(self) -> bool:
        return self.device.is_connected

    @property
    def state(self) -> MediaPlayerState:
        if self._task and not self._task.done():
            return MediaPlayerState.PLAYING
        return MediaPlayerState.IDLE

    @property
    def volume_level(self) -> float | None:
        volume = self._volume_config()
        if not volume or "LeftVolume" not in volume:
            return None
        return int(volume["LeftVolume"]) / 100

    async def async_set_volume_level(self, volume: float) -> None:
        level = round(volume * 100)

        def mutate(obj: dict[str, Any]) -> None:
            obj["LeftVolume"] = level
            if "RightVolume" in obj:
                obj["RightVolume"] = level

        await self.coordinator.async_update_config("fVideo.Volume", 0, mutate)

    async def async_browse_media(
        self,
        media_content_type: MediaType | str | None = None,
        media_content_id: str | None = None,
    ) -> BrowseMedia:
        return await media_source.async_browse_media(
            self.hass,
            media_content_id,
            content_filter=lambda item: item.media_content_type.startswith("audio/"),
        )

    async def async_play_media(
        self, media_type: MediaType | str, media_id: str, **kwargs: Any
    ) -> None:
        if media_source.is_media_source_id(media_id):
            media_id = (
                await media_source.async_resolve_media(
                    self.hass, media_id, self.entity_id
                )
            ).url
        url = async_process_play_media_url(self.hass, media_id)
        audio = await self._to_alaw(url)
        await self.async_media_stop()
        self._task = self.hass.async_create_background_task(
            self._play(audio), f"{DOMAIN} speaker {self.entity_id}"
        )
        self.async_write_ha_state()

    async def async_media_stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        self.async_write_ha_state()

    async def _play(self, audio: bytes) -> None:
        try:
            await self.device.async_talk(audio)
        except (CannotConnect, CommandFailed) as err:
            _LOGGER.warning("%s: playing audio failed: %s", self.entity_id, err)
        finally:
            self.hass.loop.call_soon(self.async_write_ha_state)

    async def _to_alaw(self, url: str) -> bytes:
        ffmpeg = get_ffmpeg_manager(self.hass).binary
        proc = await asyncio.create_subprocess_exec(
            ffmpeg, "-hide_banner", "-loglevel", "error", "-i", url,
            "-t", str(MAX_SECONDS), "-f", "alaw", "-ar", str(SAMPLE_RATE), "-ac", "1", "-",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )  # fmt: skip
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), 60)
        except TimeoutError:
            proc.kill()
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="audio_convert_failed"
            ) from None
        if proc.returncode or not stdout:
            _LOGGER.warning(
                "ffmpeg failed for %s: %s", url, stderr.decode(errors="replace")
            )
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="audio_convert_failed"
            )
        return stdout
