"""Constants for the ICSee integration."""

from datetime import timedelta

DOMAIN = "icsee_ptz"

CONF_CHANNEL = "channel"
CONF_STEP = "step"
CONF_PRESET = "preset"
CONF_ADD_PTZ_BUTTONS_ALL_CHANNELS = "add_ptz_buttons_all_channels"
CONF_CHANNEL_COUNT = "channel_count"
CONF_SYSTEM_CAPABILITIES = "system_capabilities"
# Legacy option (<= 4.x): gated the old experimental entities. Ignored now.
CONF_EXPERIMENTAL_ENTITIES = "experimental_entities"

DEFAULT_PORT = 34567
DEFAULT_USERNAME = "admin"

SCAN_INTERVAL = timedelta(minutes=5)
DISCOVERY_INTERVAL = timedelta(minutes=5)

# DVRIP return codes
RET_OK = (100, 515)
RET_NEEDS_REBOOT = 603
RET_NOT_SUPPORTED = (103, 607)
