"""Diagnostic sensors: users, WiFi, cloud status, SD card."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    CONF_USERNAME,
    PERCENTAGE,
    EntityCategory,
    UnitOfInformation,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ICSeeConfigEntry, ICSeeCoordinator
from .entity import (
    ICSeeConfigEntity,
    ICSeeConfigEntityDescription,
    ICSeeEntity,
    config_entities,
)

PARALLEL_UPDATES = 0

CLOUD_STATES = {
    "Conneted": "connected",
    "Connected": "connected",
    "DisEnable": "disabled",
}


def _hex(value: Any) -> int:
    try:
        return int(value, 16) if isinstance(value, str) else int(value or 0)
    except ValueError:
        return 0


def _storage(field: str) -> Callable[[Any], int]:
    """Sum a size field (MB) over all SD card partitions."""

    def total(disks: Any) -> int:
        return sum(
            _hex(part.get(field))
            for disk in disks or []
            for part in disk.get("Partition") or []
        )

    return total


@dataclass(frozen=True, kw_only=True)
class ICSeeSensorEntityDescription(
    ICSeeConfigEntityDescription, SensorEntityDescription
):
    """A sensor showing a value read from the camera."""

    value_fn: Callable[[Any], Any] = lambda value: value
    attrs_fn: Callable[[Any], dict[str, Any]] | None = None


SENSORS: tuple[ICSeeSensorEntityDescription, ...] = (
    ICSeeSensorEntityDescription(
        key="users",
        translation_key="users",
        config="Users",
        path=(),
        value_fn=len,
        # names and groups only, never passwords
        attrs_fn=lambda users: {
            "users": [
                {"name": u.get("Name"), "group": u.get("Group")}
                for u in users
                if isinstance(u, dict)
            ]
        },
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ICSeeSensorEntityDescription(
        key="wifi_signal",
        translation_key="wifi_signal",
        config="WifiRouteInfo",
        path=("SignalLevel",),
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        exists_fn=lambda coordinator, value: bool(
            (coordinator.channel_value("WifiRouteInfo", 0) or {}).get("WlanStatus")
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ICSeeSensorEntityDescription(
        key="cloud_status",
        translation_key="cloud_status",
        config="Status.NatInfo",
        path=("NatStatus",),
        value_fn=lambda status: CLOUD_STATES.get(status, "not_connected"),
        device_class=SensorDeviceClass.ENUM,
        options=["connected", "not_connected", "disabled"],
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ICSeeSensorEntityDescription(
        key="storage_total",
        translation_key="storage_total",
        config="StorageInfo",
        path=(),
        value_fn=_storage("TotalSpace"),
        exists_fn=lambda coordinator, disks: _storage("TotalSpace")(disks) > 0,
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ICSeeSensorEntityDescription(
        key="storage_free",
        translation_key="storage_free",
        config="StorageInfo",
        path=(),
        value_fn=_storage("RemainSpace"),
        exists_fn=lambda coordinator, disks: _storage("TotalSpace")(disks) > 0,
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
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
    entities: list[SensorEntity] = config_entities(coordinator, SENSORS, ICSeeSensor)
    entities.append(LoggedInAsSensor(coordinator))
    async_add_entities(entities)


class ICSeeSensor(ICSeeConfigEntity, SensorEntity):
    entity_description: ICSeeSensorEntityDescription
    # user names are shown, but not stored in the history database
    _unrecorded_attributes = frozenset({"users"})

    @property
    def native_value(self) -> Any:
        value = self.config_value
        return None if value is None else self.entity_description.value_fn(value)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        value = self.config_value
        if value is None or not self.entity_description.attrs_fn:
            return None
        return self.entity_description.attrs_fn(value)


class LoggedInAsSensor(ICSeeEntity, SensorEntity):
    """The camera account this integration uses."""

    _attr_translation_key = "logged_in_as"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: ICSeeCoordinator) -> None:
        super().__init__(coordinator, "logged_in_as")
        self._attr_native_value = coordinator.config_entry.data[CONF_USERNAME]
