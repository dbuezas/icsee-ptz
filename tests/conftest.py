"""Test fixtures: a fake camera built from real (redacted) camera answers."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import re
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.icsee_ptz.const import DOMAIN
from custom_components.icsee_ptz.device import (
    AuthFailed,
    CannotConnect,
    CommandFailed,
    ConfigNotSupported,
)

FIXTURES = Path(__file__).parent / "fixtures"
SERIAL = "0123456789abcdef"

ENTRY_DATA = {
    "name": "Garten",
    "host": "192.0.2.10",
    "port": 34567,
    "username": "admin",
    "password": "secret",
    "unique_id": SERIAL,
    "mac": "b4:fb:e3:00:00:01",
    "channel_count": 1,
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


class FakeDevice:
    """Behaves like ICSeeDevice, backed by fixture data."""

    def __init__(self, fixture: str = "garten") -> None:
        data = json.loads((FIXTURES / f"{fixture}.json").read_text())
        self.system_info: dict[str, Any] = data["system_info"]
        self.abilities: dict[str, Any] = data["abilities"]
        self.configs: dict[str, Any] = data["configs"]
        self.host, self.port = ENTRY_DATA["host"], ENTRY_DATA["port"]
        self.username, self.password = ENTRY_DATA["username"], ENTRY_DATA["password"]
        self.is_connected = True
        self.auth_failed = False
        self.ignore_writes = False  # simulate firmware that says OK but ignores
        self.set_ret = 100
        self.connect_error: Exception | None = None
        self.writes: list[tuple[str, Any]] = []
        self.async_ptz = AsyncMock()
        self.async_set_time = AsyncMock()
        self.async_reboot = AsyncMock()
        self.async_force_frame = AsyncMock()
        self.async_remote_ctrl = AsyncMock()
        self.async_talk = AsyncMock()
        self._alarm_callbacks: list = []
        self._connection_callbacks: list = []

    # connection
    async def async_connect(self) -> None:
        if self.connect_error:
            raise self.connect_error

    async def async_check(self) -> dict[str, Any]:
        if self.connect_error:
            raise self.connect_error
        return self.system_info

    async def async_run(self) -> None:
        return None

    def close(self) -> None:
        pass

    def add_alarm_callback(self, cb):
        self._alarm_callbacks.append(cb)
        return lambda: self._alarm_callbacks.remove(cb)

    def add_connection_callback(self, cb):
        self._connection_callbacks.append(cb)
        return lambda: self._connection_callbacks.remove(cb)

    def fire_alarm(self, what: dict[str, Any]) -> None:
        for cb in list(self._alarm_callbacks):
            cb(what)

    # configs
    def _split(self, name: str) -> tuple[str, int | None]:
        if m := re.fullmatch(r"(.+)\.\[(\d+)\]", name):
            return m.group(1), int(m.group(2))
        return name, None

    async def async_get_system_info(self) -> dict[str, Any]:
        return self.system_info

    async def async_get_value(self, name: str, code: int) -> Any:
        return await self.async_get_config(name)

    async def async_get_ability(self, name: str) -> Any:
        if name not in self.abilities:
            raise ConfigNotSupported(name, 103)
        return copy.deepcopy(self.abilities[name])

    async def async_get_config(self, name: str) -> Any:
        base, channel = self._split(name)
        if base not in self.configs:
            raise ConfigNotSupported(name, 607)
        value = self.configs[base]
        if channel is not None:
            if base == "Simplify.Encode":
                raise ConfigNotSupported(name, 607)  # like the real cameras
            value = value[channel]
        return copy.deepcopy(value)

    async def async_set_config(self, name: str, value: Any) -> int:
        if self.set_ret not in (100, 603):
            raise CommandFailed(name, self.set_ret)
        self.writes.append((name, copy.deepcopy(value)))
        if self.ignore_writes:
            return 100
        base, channel = self._split(name)
        if channel is None:
            self.configs[base] = copy.deepcopy(value)
        else:
            self.configs[base][channel] = copy.deepcopy(value)
        return self.set_ret


@pytest.fixture
def fake_device() -> FakeDevice:
    return FakeDevice()


@pytest.fixture
def mock_device(fake_device: FakeDevice):
    with (
        patch("custom_components.icsee_ptz.ICSeeDevice", return_value=fake_device),
        patch(
            "custom_components.icsee_ptz.config_flow.ICSeeDevice",
            return_value=fake_device,
        ),
        patch("custom_components.icsee_ptz.async_discover", return_value=[]),
        patch(
            "custom_components.icsee_ptz.config_flow.async_discover", return_value=[]
        ),
        patch(
            "custom_components.icsee_ptz.config_flow.get_mac_address",
            return_value="b4:fb:e3:00:00:01",
        ),
    ):
        yield fake_device


@pytest.fixture
def config_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Garten",
        unique_id=SERIAL,
        version=4,
        data=dict(ENTRY_DATA),
        options={"channel": 0, "step": 2, "preset": 0},
    )


@pytest.fixture
async def setup_integration(hass, mock_device, config_entry):
    """Set up the integration with the fake Garten camera."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


__all__ = ["AuthFailed", "CannotConnect", "FakeDevice", "SERIAL"]
