"""Config flow for ICSee."""

from __future__ import annotations

from collections.abc import Mapping
from functools import partial
from ipaddress import IPv6Address, ip_address
import logging
from typing import Any

from getmac import get_mac_address
import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import (
    CONF_HOST,
    CONF_MAC,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_UNIQUE_ID,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_ADD_PTZ_BUTTONS_ALL_CHANNELS,
    CONF_CHANNEL,
    CONF_CHANNEL_COUNT,
    CONF_PRESET,
    CONF_STEP,
    DEFAULT_PORT,
    DEFAULT_USERNAME,
    DOMAIN,
)
from .device import AuthFailed, CannotConnect, ICSeeDevice
from .discovery import DiscoveredCamera, async_discover

_LOGGER = logging.getLogger(__name__)

CONF_DEVICE = "device"
MANUAL = "manual"


async def _async_get_mac_address(hass: HomeAssistant, host: str) -> str | None:
    """Get the MAC address from a host name, IPv4 or IPv6 address."""
    try:
        ip_addr = ip_address(host)
    except ValueError:
        return await hass.async_add_executor_job(
            partial(get_mac_address, hostname=host)
        )
    if ip_addr.version == 4:
        return await hass.async_add_executor_job(partial(get_mac_address, ip=host))
    ip_addr = IPv6Address(int(ip_addr))  # drop the scope id
    return await hass.async_add_executor_job(partial(get_mac_address, ip6=str(ip_addr)))


async def _async_validate(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Log in and return SystemInfo. Raise CannotConnect or AuthFailed."""
    device = ICSeeDevice(
        data[CONF_HOST], data[CONF_PORT], data[CONF_USERNAME], data[CONF_PASSWORD]
    )
    info = await device.async_check()
    if not info or not info.get("SerialNo"):
        raise CannotConnect("No serial number")
    return info


def _credentials_schema(
    defaults: Mapping[str, Any], with_host: bool, with_name: bool
) -> vol.Schema:
    schema: dict[Any, Any] = {}
    if with_name:
        schema[
            vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, vol.UNDEFINED))
        ] = str
    if with_host:
        schema[
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, vol.UNDEFINED))
        ] = str
        schema[
            vol.Optional(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT))
        ] = cv.port
    schema[
        vol.Required(
            CONF_USERNAME, default=defaults.get(CONF_USERNAME, DEFAULT_USERNAME)
        )
    ] = str
    schema[vol.Optional(CONF_PASSWORD, default="")] = str
    return vol.Schema(schema)


class ICSeePTZConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow for ICSee cameras."""

    VERSION = 4

    def __init__(self) -> None:
        self._discovered: dict[str, DiscoveredCamera] = {}
        self._defaults: dict[str, Any] = {}

    # ---- adding a camera -------------------------------------------------

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Search the network, then let the user pick a camera or enter one."""
        if user_input is not None:
            camera = self._discovered.get(user_input[CONF_DEVICE])
            if camera:
                self._defaults = {
                    CONF_NAME: camera.name,
                    CONF_HOST: camera.host,
                    CONF_PORT: camera.port,
                }
            return await self.async_step_credentials()

        configured = self._async_current_ids(include_ignore=False)
        self._discovered = {
            c.serial: c for c in await async_discover() if c.serial not in configured
        }
        if not self._discovered:
            return await self.async_step_credentials()
        options = [
            SelectOptionDict(value=serial, label=f"{c.name} ({c.host})")
            for serial, c in self._discovered.items()
        ]
        options.append(SelectOptionDict(value=MANUAL, label=MANUAL))
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            mode=SelectSelectorMode.LIST,
                            translation_key=CONF_DEVICE,
                        )
                    )
                }
            ),
        )

    async def async_step_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**self._defaults, **user_input}
            data.setdefault(CONF_PORT, DEFAULT_PORT)
            try:
                info = await _async_validate(self.hass, data)
            except AuthFailed:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            else:
                return await self._async_create(data, info)
        return self.async_show_form(
            step_id="credentials",
            data_schema=self.add_suggested_values_to_schema(
                _credentials_schema(
                    self._defaults,
                    with_host=CONF_HOST not in self._defaults,
                    with_name=True,
                ),
                user_input or self._defaults,
            ),
            errors=errors,
        )

    async def async_step_integration_discovery(
        self, discovery_info: dict[str, Any]
    ) -> ConfigFlowResult:
        """A camera was found by the background search."""
        camera = DiscoveredCamera(**discovery_info)
        await self.async_set_unique_id(camera.serial)
        # Known camera: follow a changed IP address
        self._abort_if_unique_id_configured(
            updates={CONF_HOST: camera.host, CONF_PORT: camera.port}
        )
        self._defaults = {
            CONF_NAME: camera.name,
            CONF_HOST: camera.host,
            CONF_PORT: camera.port,
        }
        self.context["title_placeholders"] = {"name": camera.name, "host": camera.host}
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**self._defaults, **user_input}
            try:
                info = await _async_validate(self.hass, data)
            except AuthFailed:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            else:
                return await self._async_create(data, info)
        return self.async_show_form(
            step_id="discovery_confirm",
            data_schema=self.add_suggested_values_to_schema(
                _credentials_schema(self._defaults, with_host=False, with_name=True),
                user_input or self._defaults,
            ),
            description_placeholders={
                "name": self._defaults[CONF_NAME],
                "host": self._defaults[CONF_HOST],
            },
            errors=errors,
        )

    async def _async_create(
        self, data: dict[str, Any], info: dict[str, Any]
    ) -> ConfigFlowResult:
        serial = str(info["SerialNo"])
        await self.async_set_unique_id(serial, raise_on_progress=False)
        self._abort_if_unique_id_configured(
            updates={CONF_HOST: data[CONF_HOST], CONF_PORT: data[CONF_PORT]}
        )
        mac = await _async_get_mac_address(self.hass, data[CONF_HOST])
        entry_data = {
            CONF_NAME: data[CONF_NAME],
            CONF_HOST: data[CONF_HOST],
            CONF_PORT: data[CONF_PORT],
            CONF_USERNAME: data[CONF_USERNAME],
            CONF_PASSWORD: data[CONF_PASSWORD],
            CONF_UNIQUE_ID: serial,
            CONF_MAC: format_mac(mac) if mac else None,
            CONF_CHANNEL_COUNT: max(
                1,
                int(info.get("VideoInChannel") or 0) + int(info.get("DigChannel") or 0),
            ),
        }
        return self.async_create_entry(title=data[CONF_NAME], data=entry_data)

    # ---- changing an existing camera --------------------------------------

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**entry.data, **user_input}
            try:
                await _async_validate(self.hass, data)
            except AuthFailed:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates=user_input
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=_credentials_schema(
                entry.data, with_host=False, with_name=False
            ),
            description_placeholders={"name": entry.title},
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**entry.data, **user_input}
            try:
                info = await _async_validate(self.hass, data)
            except AuthFailed:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(str(info["SerialNo"]))
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(
                    entry, data_updates=user_input
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                _credentials_schema(entry.data, with_host=True, with_name=False),
                {k: v for k, v in entry.data.items() if k != CONF_PASSWORD},
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return OptionsFlowHandler()


class OptionsFlowHandler(OptionsFlow):
    """PTZ defaults."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_CHANNEL, default=options.get(CONF_CHANNEL, 0)
                    ): cv.positive_int,
                    vol.Optional(
                        CONF_STEP, default=options.get(CONF_STEP, 2)
                    ): cv.positive_int,
                    vol.Optional(
                        CONF_PRESET, default=options.get(CONF_PRESET, 0)
                    ): cv.positive_int,
                    vol.Optional(
                        CONF_ADD_PTZ_BUTTONS_ALL_CHANNELS,
                        default=options.get(CONF_ADD_PTZ_BUTTONS_ALL_CHANNELS, False),
                    ): cv.boolean,
                }
            ),
        )
