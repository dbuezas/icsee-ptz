"""Config flow: manual, discovery, reauth, reconfigure, options."""

from __future__ import annotations

from dataclasses import asdict
from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.icsee_ptz.const import DOMAIN
from custom_components.icsee_ptz.device import AuthFailed, CannotConnect
from custom_components.icsee_ptz.discovery import DiscoveredCamera

from .conftest import SERIAL

CAMERA = DiscoveredCamera(
    host="192.0.2.10",
    port=34567,
    serial=SERIAL,
    name="camera_1234",
    mac="b4:fb:e3:00:00:01",
    channels=1,
)
LOGIN = {"name": "Garten", "username": "admin", "password": "secret"}


async def test_manual(hass: HomeAssistant, mock_device) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["step_id"] == "credentials"  # nothing discovered
    mock_device.connect_error = CannotConnect("x")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**LOGIN, "host": "192.0.2.10", "port": 34567}
    )
    assert result["errors"] == {"base": "cannot_connect"}
    mock_device.connect_error = AuthFailed("x")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**LOGIN, "host": "192.0.2.10", "port": 34567}
    )
    assert result["errors"] == {"base": "invalid_auth"}
    mock_device.connect_error = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**LOGIN, "host": "192.0.2.10", "port": 34567}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == SERIAL
    assert result["data"]["host"] == "192.0.2.10"
    assert result["data"]["channel_count"] == 1


async def test_pick_discovered(hass: HomeAssistant, mock_device) -> None:
    with patch(
        "custom_components.icsee_ptz.config_flow.async_discover", return_value=[CAMERA]
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"device": SERIAL}
    )
    assert result["step_id"] == "credentials"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], LOGIN)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["host"] == CAMERA.host


async def test_background_discovery(hass: HomeAssistant, mock_device) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_INTEGRATION_DISCOVERY},
        data=asdict(CAMERA),
    )
    assert result["step_id"] == "discovery_confirm"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], LOGIN)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_discovery_updates_ip(
    hass: HomeAssistant, mock_device, config_entry
) -> None:
    config_entry.add_to_hass(hass)
    moved = asdict(CAMERA) | {"host": "192.0.2.99"}
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_INTEGRATION_DISCOVERY},
        data=moved,
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert config_entry.data["host"] == "192.0.2.99"


async def test_reauth(hass: HomeAssistant, mock_device, config_entry) -> None:
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"username": "admin", "password": "new"}
    )
    assert result["reason"] == "reauth_successful"
    await hass.async_block_till_done()
    assert config_entry.data["password"] == "new"


async def test_reconfigure(hass: HomeAssistant, mock_device, config_entry) -> None:
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "host": "192.0.2.50",
            "port": 34567,
            "username": "admin",
            "password": "secret",
        },
    )
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert config_entry.data["host"] == "192.0.2.50"


async def test_reconfigure_other_camera(
    hass: HomeAssistant, mock_device, config_entry
) -> None:
    config_entry.add_to_hass(hass)
    mock_device.system_info = {
        **mock_device.system_info,
        "SerialNo": "ffffffffffffffff",
    }
    result = await config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "host": "192.0.2.50",
            "port": 34567,
            "username": "admin",
            "password": "secret",
        },
    )
    assert result["reason"] == "wrong_device"


async def test_setup_auth_failed_starts_reauth(
    hass: HomeAssistant, mock_device, config_entry
) -> None:
    config_entry.add_to_hass(hass)
    mock_device.connect_error = AuthFailed("x")
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is config_entries.ConfigEntryState.SETUP_ERROR
    assert any(
        f["context"]["source"] == "reauth"
        for f in hass.config_entries.flow.async_progress()
    )


async def test_setup_offline_retries(
    hass: HomeAssistant, mock_device, config_entry
) -> None:
    config_entry.add_to_hass(hass)
    mock_device.connect_error = CannotConnect("x")
    await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is config_entries.ConfigEntryState.SETUP_RETRY


async def test_options(hass: HomeAssistant, setup_integration) -> None:
    result = await hass.config_entries.options.async_init(setup_integration.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"channel": 0, "step": 5, "preset": 1, "add_ptz_buttons_all_channels": False},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert setup_integration.options["step"] == 5
