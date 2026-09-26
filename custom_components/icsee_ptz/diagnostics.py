"""Diagnostics download (passwords and identifiers hidden)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import (
    CONF_HOST,
    CONF_MAC,
    CONF_PASSWORD,
    CONF_UNIQUE_ID,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant

from .coordinator import ICSeeConfigEntry

TO_REDACT = {
    CONF_HOST,
    CONF_MAC,
    CONF_PASSWORD,
    CONF_UNIQUE_ID,
    CONF_USERNAME,
    "SerialNo",
    "SN",
    "MAC",
    "HostIP",
    "GateWay",
    # security configs
    "QuestionAnswer",
    "CustomQuestion",
    "SecurityEmail",
    "SecurityPhone",
    "User",
    "Password",
    "PasswordV2",
    "Addr",
    "ServName",
    "BoxID",
    "Users",
    "WlanMac",
    "NaInfoCode",
    "DeviceID",
    "ServerAddr",
    "UserName",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ICSeeConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data.coordinator
    return async_redact_data(
        {
            "entry": {"data": dict(entry.data), "options": dict(entry.options)},
            "connected": entry.runtime_data.device.is_connected,
            "system_info": coordinator.system_info,
            "abilities": coordinator.abilities,
            "supported_configs": sorted(coordinator.supported or ()),
            "configs": coordinator.data,
        },
        TO_REDACT,
    )
