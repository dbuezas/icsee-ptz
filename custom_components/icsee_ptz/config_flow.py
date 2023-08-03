from functools import partial
from ipaddress import IPv6Address, ip_address
from typing import Any
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv
from homeassistant.config_entries import ConfigEntry, OptionsFlow, ConfigFlow
from homeassistant.const import (
    CONF_HOST,
    CONF_MAC,
    CONF_NAME,
    CONF_USERNAME,
    CONF_PASSWORD,
)
from homeassistant.core import HomeAssistant, callback
import voluptuous as vol
import logging
from .const import (
    CONF_CHANNEL,
    CONF_CHANNEL_COUNT,
    CONF_PRESET,
    CONF_STEP,
    CONF_SYSTEM_CAPABILITIES,
    DOMAIN,
)
from .asyncio_dvrip import DVRIPCam, SomethingIsWrongWithCamera
from getmac import get_mac_address

_LOGGER = logging.getLogger(__name__)


async def _async_get_mac_address(hass: HomeAssistant, host: str) -> str | None:
    """Get mac address from host name, IPv4 address, or IPv6 address."""
    # ** Taken from dlna_dmr component **
    # Help mypy, which has trouble with the async_add_executor_job + partial call
    mac_address: str | None
    # getmac has trouble using IPv6 addresses as the "hostname" parameter so
    # assume host is an IP address, then handle the case it's not.
    try:
        ip_addr = ip_address(host)
    except ValueError:
        return await hass.async_add_executor_job(
            partial(get_mac_address, hostname=host)
        )
    else:
        if ip_addr.version == 4:
            return await hass.async_add_executor_job(partial(get_mac_address, ip=host))
        else:
            # Drop scope_id from IPv6 address by converting via int
            ip_addr = IPv6Address(int(ip_addr))
            return await hass.async_add_executor_job(
                partial(get_mac_address, ip6=str(ip_addr))
            )


class ICSeePTZConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow for ICSeePTZ"""

    VERSION = 1

    def __init__(self):
        """Initialize the ICSeePTZ flow."""
        self.discovery_info = None

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        _LOGGER.debug("async_step_user: %s", user_input)

        errors = {}
        if user_input:
            try:
                dvrip = DVRIPCam(
                    user_input[CONF_HOST],
                    user=user_input[CONF_USERNAME],
                    password=user_input[CONF_PASSWORD],
                )
                await dvrip.login(self.hass.loop)
                x: dict = await dvrip.get_info("Detect")  # type: ignore
                user_input[CONF_CHANNEL_COUNT] = len(x["MotionDetect"])
                user_input[
                    CONF_SYSTEM_CAPABILITIES
                ] = await dvrip.get_system_capabilities()
                mac = await _async_get_mac_address(
                    self.hass,
                    user_input[CONF_HOST],
                )
                user_input[CONF_MAC] = mac
                await self.async_set_unique_id(mac)
                self._abort_if_unique_id_configured(updates=user_input)

                return self.async_create_entry(
                    title=user_input[CONF_NAME], data=user_input
                )
            except SomethingIsWrongWithCamera:
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME): str,
                    vol.Required(CONF_HOST): str,
                    vol.Required(
                        CONF_USERNAME,
                        description={"suggested_value": "admin"},
                    ): cv.string,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            description_placeholders={
                CONF_NAME: "Garden camera",
                CONF_HOST: "192.168.0.101",
                CONF_USERNAME: "admin",
                CONF_PASSWORD: "icsee_app_password",
            },
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> OptionsFlow:
        """Create the options flow."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(OptionsFlow):
    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_CHANNEL,
                        description={
                            "suggested_value": self.config_entry.options.get(
                                CONF_CHANNEL, 0
                            )
                        },
                    ): cv.positive_int,
                    vol.Optional(
                        CONF_STEP,
                        description={
                            "suggested_value": self.config_entry.options.get(
                                CONF_STEP, 2
                            )
                        },
                    ): cv.positive_int,
                    vol.Optional(
                        CONF_PRESET,
                        description={
                            "suggested_value": self.config_entry.options.get(
                                CONF_PRESET, 0
                            )
                        },
                    ): cv.positive_int,
                }
            ),
        )
