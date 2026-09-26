"""Manual alarm siren (only on cameras with the OneKeyManulAlarm ability)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.siren import SirenEntity, SirenEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .binary_sensor import _run
from .coordinator import ICSeeConfigEntry, ICSeeCoordinator
from .entity import ICSeeEntity

PARALLEL_UPDATES = 1

ABILITY = "SystemFunction.AlarmFunction.OneKeyManulAlarm"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ICSeeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    if coordinator.ability(ABILITY):
        async_add_entities([ICSeeSiren(coordinator)])


class ICSeeSiren(ICSeeEntity, SirenEntity):
    _attr_translation_key = "siren"
    _attr_supported_features = SirenEntityFeature.TURN_ON | SirenEntityFeature.TURN_OFF
    _attr_assumed_state = True  # the camera does not report the siren state

    def __init__(self, coordinator: ICSeeCoordinator) -> None:
        super().__init__(coordinator, "siren")
        self._attr_is_on = False

    @property
    def available(self) -> bool:
        return self.device.is_connected

    async def async_turn_on(self, **kwargs: Any) -> None:
        await _run(self.device.async_remote_ctrl("ManuIntelAlarm", "0x00000001"))
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await _run(self.device.async_remote_ctrl("ManuIntelAlarm", "0x00000000"))
        self._attr_is_on = False
        self.async_write_ha_state()
