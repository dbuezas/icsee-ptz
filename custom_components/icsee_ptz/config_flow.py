from typing import Any
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv
from homeassistant.config_entries import ConfigEntry, OptionsFlow, ConfigFlow
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_UNIQUE_ID,
    CONF_USERNAME,
    CONF_PASSWORD,
)
from homeassistant.core import callback
import voluptuous as vol
import logging

from .const import CONF_CHANNEL, CONF_CHANNEL_COUNT, CONF_PRESET, CONF_STEP, DOMAIN
from .asyncio_dvrip import DVRIPCam, SomethingIsWrongWithCamera

_LOGGER = logging.getLogger(__name__)


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
                system_info: dict[str, str] = await dvrip.get_system_info()  # type: ignore
                uniqId = system_info["SerialNo"]
                user_input[CONF_UNIQUE_ID] = uniqId
                user_input[CONF_CHANNEL_COUNT] = 1
                x: dict = await dvrip.get_info("Detect")  # type: ignore
                user_input[CONF_CHANNEL_COUNT] = len(x["MotionDetect"])
                await self.async_set_unique_id(uniqId)
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
