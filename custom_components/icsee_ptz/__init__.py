"""The ICSee (XM / DVRIP) camera integration."""

from __future__ import annotations

from dataclasses import asdict
import logging

import voluptuous as vol

from homeassistant.components.binary_sensor import (
    DOMAIN as BINARY_SENSOR_DOMAIN,
    BinarySensorDeviceClass,
)
from homeassistant.config_entries import SOURCE_INTEGRATION_DISCOVERY
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
    EVENT_HOMEASSISTANT_STARTED,
    Platform,
)
from homeassistant.core import CoreState, Event, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import (
    config_validation as cv,
    discovery_flow,
    issue_registry as ir,
    service,
)
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import ConfigType

from .const import DEFAULT_PORT, DISCOVERY_INTERVAL, DOMAIN
from .coordinator import ICSeeConfigEntry, ICSeeCoordinator, ICSeeData
from .device import AuthFailed, CannotConnect, ICSeeDevice
from .discovery import async_discover

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CAMERA,
    Platform.MEDIA_PLAYER,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SIREN,
    Platform.SWITCH,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PTZ_COMMANDS = [
    "Stop",
    "DirectionUp",
    "DirectionDown",
    "DirectionLeft",
    "DirectionRight",
    "DirectionLeftUp",
    "DirectionLeftDown",
    "DirectionRightUp",
    "DirectionRightDown",
    "ZoomTile",
    "ZoomWide",
    "FocusNear",
    "FocusFar",
    "IrisSmall",
    "IrisLarge",
    "SetPreset",
    "GotoPreset",
    "ClearPreset",
    "StartTour",
    "StopTour",
]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the actions and start the background search."""
    # The PTZ actions target the motion alarm binary sensor (as before 5.0)
    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        "move",
        entity_domain=BINARY_SENSOR_DOMAIN,
        entity_device_classes=[BinarySensorDeviceClass.MOTION],
        schema={
            vol.Required("cmd"): vol.In(PTZ_COMMANDS),
            vol.Optional("step"): cv.positive_int,
            vol.Optional("preset"): cv.positive_int,
            vol.Optional("channel"): cv.positive_int,
        },
        func="async_move",
    )
    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        "synchronize_clock",
        entity_domain=BINARY_SENSOR_DOMAIN,
        entity_device_classes=[BinarySensorDeviceClass.MOTION],
        schema=None,
        func="async_synchronize_clock",
    )
    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        "force_frame",
        entity_domain=BINARY_SENSOR_DOMAIN,
        entity_device_classes=[BinarySensorDeviceClass.MOTION],
        schema=None,
        func="async_force_frame",
    )

    async def _discover(*_: object) -> None:
        for camera in await async_discover():
            discovery_flow.async_create_flow(
                hass,
                DOMAIN,
                context={"source": SOURCE_INTEGRATION_DISCOVERY},
                data=asdict(camera),
            )

    @callback
    def _start(_: Event | None = None) -> None:
        hass.async_create_background_task(_discover(), f"{DOMAIN} discovery")
        async_track_time_interval(
            hass, _discover, DISCOVERY_INTERVAL, cancel_on_shutdown=True
        )

    if hass.state is CoreState.running:
        _start()
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _start)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ICSeeConfigEntry) -> bool:
    device = ICSeeDevice(
        entry.data[CONF_HOST],
        entry.data.get(CONF_PORT, DEFAULT_PORT),
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
    )
    try:
        await device.async_connect()
    except AuthFailed as err:
        raise ConfigEntryAuthFailed(
            translation_domain=DOMAIN, translation_key="invalid_auth"
        ) from err
    except CannotConnect as err:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN, translation_key="cannot_connect"
        ) from err

    coordinator = ICSeeCoordinator(hass, entry, device)
    try:
        await coordinator.async_config_entry_first_refresh()
    except BaseException:
        device.close()
        raise
    entry.runtime_data = ICSeeData(device=device, coordinator=coordinator)

    entry.async_create_background_task(
        hass, device.async_run(), f"{DOMAIN} {entry.title}"
    )

    @callback
    def _check_connection() -> None:
        if device.auth_failed:
            entry.async_start_reauth(hass)
        if device.connected:
            # reconnected, e.g. after the camera restarted: settings are applied now
            ir.async_delete_issue(hass, DOMAIN, f"reboot_required_{entry.entry_id}")

    entry.async_on_unload(device.add_connection_callback(_check_connection))
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ICSeeConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        entry.runtime_data.device.close()
    return unloaded


async def _async_reload(hass: HomeAssistant, entry: ICSeeConfigEntry) -> None:
    """Options changed."""
    await hass.config_entries.async_reload(entry.entry_id)
