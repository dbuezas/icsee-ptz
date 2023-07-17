"""Support for ICSee devices."""
from __future__ import annotations
from .const import CONF_CHANNEL, CONF_PRESET, CONF_STEP, DOMAIN, Data

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_USERNAME,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

PLATFORMS = [
    Platform.BINARY_SENSOR,
]

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Hello World from a config entry."""

    # Store an instance of the "connecting" class that does the work of speaking
    # with your actual devices.

    data: Data = {
        "name": entry.data[CONF_NAME],
        "host": entry.data[CONF_HOST],
        "user": entry.data[CONF_USERNAME],
        "password": entry.data[CONF_PASSWORD],
        "step": entry.options.get(CONF_STEP, 2),
        "preset": entry.options.get(CONF_PRESET, 0),
        "channel": entry.options.get(CONF_CHANNEL, 0),
    }
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = data

    # This creates each HA object for each platform your device requires.
    # It's done by calling the `async_setup_entry` function in each platform module.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # This is called when an entry/configured device is to be removed. The class
    # needs to unload itself, and remove callbacks. See the classes for further
    # details
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update listener. Called when integration options are changed"""
    await hass.config_entries.async_reload(entry.entry_id)
