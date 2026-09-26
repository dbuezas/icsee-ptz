"""Connection to one ICSee / XM (DVRIP) device."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
import logging
from typing import Any

from .asyncio_dvrip import (
    CommandFailed,
    ConfigNotSupported,
    DVRIPCam,
    SomethingIsWrongWithCamera,
)

_LOGGER = logging.getLogger(__name__)

RECONNECT_INTERVAL = 20  # seconds; the camera keepalive is unreliable, so we re-login

__all__ = [
    "AuthFailed",
    "CannotConnect",
    "CommandFailed",
    "ConfigNotSupported",
    "ICSeeDevice",
]


class CannotConnect(Exception):
    """The device can't be reached."""


class AuthFailed(Exception):
    """The device rejected the username or password."""


class ICSeeDevice:
    """Keeps a command connection and an alarm connection alive."""

    def __init__(self, host: str, port: int, username: str, password: str) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.dvrip: DVRIPCam | None = None
        self.dvrip_alarm: DVRIPCam | None = None
        self.connected = False
        self.auth_failed = False
        self._lock = asyncio.Lock()
        self._alarm_callbacks: list[Callable[[dict[str, Any]], None]] = []
        self._connection_callbacks: list[Callable[[], None]] = []

    def _new_cam(self) -> DVRIPCam:
        return DVRIPCam(
            self.host, port=self.port, user=self.username, password=self.password
        )

    async def _login(self, cam: DVRIPCam) -> None:
        try:
            await cam.connect(timeout=10)
        except SomethingIsWrongWithCamera as err:
            raise CannotConnect(str(err)) from err
        if not await cam.login(asyncio.get_running_loop()):
            cam.close()
            if cam.login_ret is None:
                raise CannotConnect("No reply to login")
            raise AuthFailed(f"Login rejected (Ret {cam.login_ret})")

    async def async_check(self) -> dict[str, Any]:
        """Log in once and return SystemInfo. Used by the config flow."""
        cam = self._new_cam()
        try:
            await self._login(cam)
            try:
                return await cam.get_command("SystemInfo")
            except SomethingIsWrongWithCamera as err:
                raise CannotConnect(str(err)) from err
        finally:
            cam.close()

    # ---- connection loop -------------------------------------------------

    @property
    def is_connected(self) -> bool:
        return bool(
            self.connected and self.dvrip_alarm and self.dvrip_alarm.socket_writer
        )

    def add_alarm_callback(
        self, cb: Callable[[dict[str, Any]], None]
    ) -> Callable[[], None]:
        self._alarm_callbacks.append(cb)
        return lambda: self._alarm_callbacks.remove(cb)

    def add_connection_callback(self, cb: Callable[[], None]) -> Callable[[], None]:
        self._connection_callbacks.append(cb)
        return lambda: self._connection_callbacks.remove(cb)

    def _on_alarm(self, what: dict[str, Any], _seq: int) -> None:
        for cb in list(self._alarm_callbacks):
            cb(what)

    def _set_connected(self, connected: bool) -> None:
        changed = connected != self.connected
        self.connected = connected
        if changed:
            for cb in list(self._connection_callbacks):
                cb()

    async def async_connect(self) -> None:
        """Open both connections once. Raise CannotConnect or AuthFailed."""
        dvrip = self._new_cam()
        dvrip_alarm = self._new_cam()
        try:
            await self._login(dvrip)
            await self._login(dvrip_alarm)
            dvrip_alarm.setAlarm(self._on_alarm)
            await dvrip_alarm.alarmStart(asyncio.get_running_loop())
        except (SomethingIsWrongWithCamera, CommandFailed) as err:
            dvrip.close()
            dvrip_alarm.close()
            raise CannotConnect(str(err)) from err
        except BaseException:
            dvrip.close()
            dvrip_alarm.close()
            raise
        # Open the new connections before dropping the old ones, so no alarm is lost
        async with self._lock:
            old, old_alarm = self.dvrip, self.dvrip_alarm
            self.dvrip, self.dvrip_alarm = dvrip, dvrip_alarm
        if old:
            old.close()
        if old_alarm:
            old_alarm.close()
        self.auth_failed = False
        if not self.connected:
            await self._safe(self.async_set_time())
        self._set_connected(True)

    async def async_run(self) -> None:
        """Keep reconnecting. Runs as a background task until cancelled."""
        try:
            while True:
                await asyncio.sleep(RECONNECT_INTERVAL)
                try:
                    await self.async_connect()
                except AuthFailed:
                    _LOGGER.warning("%s: login rejected", self.host)
                    self.auth_failed = True
                    self._set_connected(False)
                except CannotConnect as err:
                    _LOGGER.debug("%s: cannot connect: %s", self.host, err)
                    self._set_connected(False)
                except (
                    Exception
                ):  # never let the loop die, or the camera stays dead until reload
                    _LOGGER.exception(
                        "Unexpected error talking to camera %s", self.host
                    )
                    self._set_connected(False)
        finally:
            self.close()

    def close(self) -> None:
        for cam in (self.dvrip, self.dvrip_alarm):
            if cam:
                cam.close()
        self.dvrip = self.dvrip_alarm = None
        self.connected = False

    async def _safe(self, coro) -> None:
        try:
            await coro
        except Exception as err:  # noqa: BLE001 - best effort
            _LOGGER.debug("%s: %s", self.host, err)

    # ---- commands ----------------------------------------------------------

    async def _call(self, method: str, *args: Any) -> Any:
        async with self._lock:
            if not self.dvrip or not self.dvrip.socket_writer:
                raise CannotConnect("Not connected")
            try:
                return await getattr(self.dvrip, method)(*args)
            except SomethingIsWrongWithCamera as err:
                raise CannotConnect(str(err)) from err

    async def async_get_config(self, name: str) -> Any:
        return await self._call("get_config", name)

    async def async_get_value(self, name: str, code: int) -> Any:
        return await self._call("get_value", name, code)

    async def async_get_ability(self, name: str) -> Any:
        return await self._call("get_ability", name)

    async def async_set_config(self, name: str, value: Any) -> int:
        """Write a config. Return the DVRIP code (603 = reboot needed)."""
        return await self._call("set_config", name, value)

    async def async_get_system_info(self) -> dict[str, Any]:
        return await self._call("get_command", "SystemInfo")

    async def async_ptz(self, cmd: str, step: int, preset: int, channel: int) -> None:
        if cmd == "Stop":
            # The camera stops when it gets a move command with preset -1
            await self._call("ptz", "DirectionUp", 5, -1, channel)
        else:
            await self._call("ptz", cmd, step, preset, channel)

    async def async_set_time(self) -> None:
        await self._call("set_time")

    async def async_reboot(self) -> None:
        await self._call("reboot")

    async def async_remote_ctrl(self, ctrl_type: str, msg: str) -> None:
        await self._call("remote_ctrl", ctrl_type, msg)

    async def async_force_frame(self) -> None:
        """Start and stop a monitor stream; this makes the camera send a key frame."""
        cam = self._new_cam()
        try:
            await self._login(cam)

            def stop(*_args: Any) -> None:
                cam.stop_monitor()

            await asyncio.wait_for(cam.start_monitor(stop), 10)
        except (SomethingIsWrongWithCamera, TimeoutError, TypeError, ValueError) as err:
            raise CannotConnect(str(err)) from err
        finally:
            cam.close()

    async def async_talk(self, chunks: AsyncIterator[bytes]) -> None:
        """Play A-law audio on the speaker, on its own connection."""
        cam = self._new_cam()
        try:
            await self._login(cam)
            await cam.talk_stream(chunks)
        except SomethingIsWrongWithCamera as err:
            raise CannotConnect(str(err)) from err
        finally:
            cam.close()
