"""Camera speaker as a media player, e.g. for TTS."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
import logging
from typing import Any
from urllib.parse import urlparse

from aiohttp import ClientError, ClientTimeout

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
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import ICSeeConfigEntry, ICSeeCoordinator
from .device import CannotConnect, CommandFailed
from .entity import ICSeeEntity

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1

ABILITY = "SystemFunction.PreviewFunction.Talk"
VOLUME_ABILITY = "SystemFunction.OtherFunction.SupportSetVolume"
CHUNK = 3200  # bytes = 0.4 s of 8 kHz A-law
FIRST_AUDIO_TIMEOUT = 20  # seconds
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
        url = await self._resolve_playlist(url)
        await self.async_media_stop()
        proc = await self._start_ffmpeg(url)
        assert proc.stdout
        try:
            # wait for the first audio, so a bad URL is reported to the caller
            first = await asyncio.wait_for(proc.stdout.read(CHUNK), FIRST_AUDIO_TIMEOUT)
        except TimeoutError:
            first = b""
        if not first:
            await _stop(proc)
            _LOGGER.warning("ffmpeg could not read %s", url)
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="audio_convert_failed"
            )
        self._task = self.hass.async_create_background_task(
            self._play(proc, first), f"{DOMAIN} speaker {self.entity_id}"
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

    async def _play(self, proc: asyncio.subprocess.Process, first: bytes) -> None:
        """Send the audio while ffmpeg converts it (works for endless radio streams)."""
        assert proc.stdout
        stdout = proc.stdout

        async def chunks() -> AsyncIterator[bytes]:
            yield first
            while data := await stdout.read(CHUNK):
                yield data

        try:
            await self.device.async_talk(chunks())
        except (CannotConnect, CommandFailed) as err:
            _LOGGER.warning("%s: playing audio failed: %s", self.entity_id, err)
        finally:
            await _stop(proc)
            self.hass.loop.call_soon(self.async_write_ha_state)

    async def _start_ffmpeg(self, url: str) -> asyncio.subprocess.Process:
        ffmpeg = get_ffmpeg_manager(self.hass).binary
        return await asyncio.create_subprocess_exec(
            ffmpeg, "-hide_banner", "-loglevel", "error", "-i", url, "-vn",
            "-f", "alaw", "-ar", str(SAMPLE_RATE), "-ac", "1", "-",
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )  # fmt: skip

    async def _resolve_playlist(self, url: str) -> str:
        """Radio stations often link a .m3u/.pls file; play the first stream in it."""
        path = urlparse(url).path.lower()
        if not path.endswith((".m3u", ".pls")):
            return url  # .m3u8 (HLS) and normal files are read by ffmpeg directly
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(url, timeout=ClientTimeout(total=10)) as resp:
                text = (await resp.content.read(65536)).decode(errors="replace")
        except (ClientError, TimeoutError) as err:
            _LOGGER.warning("Could not read playlist %s: %s", url, err)
            return url
        return parse_playlist(text) or url


async def _stop(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is None:
        proc.kill()
        await proc.wait()


def parse_playlist(text: str) -> str | None:
    """First stream URL in an .m3u or .pls playlist."""
    for line in text.splitlines():
        line = line.strip()
        if line.lower().startswith("file") and "=" in line:
            line = line.split("=", 1)[1].strip()  # .pls: File1=http://...
        if line.startswith(("http://", "https://")):
            return line
    return None
