from typing import TypedDict

DOMAIN = "icsee_ptz"

CONF_CHANNEL = "channel"
CONF_STEP = "step"
CONF_PRESET = "preset"


class Data(TypedDict):
    name: str
    host: str
    user: str
    password: str
    step: int
    preset: int
    channel: int
