"""Diagnostic sensors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ICSeeConfigEntry
from .entity import ICSeeConfigEntity, ICSeeConfigEntityDescription, config_entities

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class ICSeeSensorEntityDescription(
    ICSeeConfigEntityDescription, SensorEntityDescription
):
    """A sensor showing a config field."""


SENSORS: tuple[ICSeeSensorEntityDescription, ...] = (
    ICSeeSensorEntityDescription(
        # Extra accounts, e.g. the hidden one the ICSee/XMEye apps create when
        # adding the camera. They can have admin rights.
        key="extra_users",
        translation_key="extra_users",
        config="System.ExUserMap",
        path=("UserNum",),
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ICSeeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(config_entities(coordinator, SENSORS, ICSeeSensor))


class ICSeeSensor(ICSeeConfigEntity, SensorEntity):
    entity_description: ICSeeSensorEntityDescription
    # user names are shown, but not stored in the history database
    _unrecorded_attributes = frozenset({"users"})

    @property
    def native_value(self) -> int | None:
        value = self.config_value
        return None if value is None else int(value)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.key != "extra_users":
            return None
        users = (self.coordinator.channel_value("System.ExUserMap", 0) or {}).get(
            "User"
        ) or []
        # names only, never passwords
        return {"users": [u.get("Name") for u in users if isinstance(u, dict)]}
