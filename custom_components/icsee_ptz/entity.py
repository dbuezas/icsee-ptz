"""Base entities for the ICSee integration."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from homeassistant.const import CONF_MAC, CONF_UNIQUE_ID
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_CHANNEL_COUNT, DOMAIN
from .coordinator import CONFIGS, ICSeeCoordinator


class ICSeeEntity(CoordinatorEntity[ICSeeCoordinator]):
    """An entity of one camera channel."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: ICSeeCoordinator, unique_key: str, channel: int = 0
    ) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        serial = entry.data[CONF_UNIQUE_ID]
        self.channel = channel
        self.device = coordinator.device
        self._attr_unique_id = f"{serial}_{unique_key}"
        info = coordinator.system_info
        if channel and entry.data.get(CONF_CHANNEL_COUNT, 1) > 1:
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, f"{serial}_{channel}")},
                name=f"{entry.title} {channel}",
                via_device=(DOMAIN, serial),
            )
        else:
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, serial)},
                name=entry.title,
                model=info.get("DeviceModel") or info.get("HardWare"),
                hw_version=info.get("HardWare"),
                sw_version=info.get("SoftWareVersion"),
                serial_number=serial,
            )
            if mac := entry.data.get(CONF_MAC):
                self._attr_device_info["connections"] = {(CONNECTION_NETWORK_MAC, mac)}

    @property
    def available(self) -> bool:
        return super().available and self.device.is_connected

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self.device.add_connection_callback(self.async_write_ha_state)
        )


@dataclass(frozen=True, kw_only=True)
class ICSeeConfigEntityDescription(EntityDescription):
    """An entity backed by one field of a camera config."""

    config: str
    path: tuple[str | int, ...]
    # Only create the entity if this ability is set, e.g.
    # "SystemFunction.OtherFunction.SupportCameraWhiteLight"
    ability: str | None = None
    exists_fn: Callable[[ICSeeCoordinator, Any], bool] | None = None


def get_path(value: Any, path: Iterable[str | int]) -> Any:
    for key in path:
        if isinstance(value, dict):
            value = value.get(key)  # type: ignore[arg-type]
        elif isinstance(value, list) and isinstance(key, int) and key < len(value):
            value = value[key]
        else:
            return None
        if value is None:
            return None
    return value


def set_path(value: Any, path: tuple[str | int, ...], new: Any) -> None:
    for key in path[:-1]:
        value = value[key]
    value[path[-1]] = new


class ICSeeConfigEntity(ICSeeEntity):
    """Entity that reads and writes one config field."""

    entity_description: ICSeeConfigEntityDescription

    def __init__(
        self,
        coordinator: ICSeeCoordinator,
        description: ICSeeConfigEntityDescription,
        channel: int,
    ) -> None:
        super().__init__(coordinator, f"{description.key}_{channel}", channel)
        self.entity_description = description

    @property
    def config_value(self) -> Any:
        desc = self.entity_description
        return get_path(
            self.coordinator.channel_value(desc.config, self.channel), desc.path
        )

    @property
    def available(self) -> bool:
        return super().available and self.config_value is not None

    async def async_write_value(self, value: Any) -> None:
        await self.async_write_fields({self.entity_description.path: value})

    async def async_write_fields(
        self, fields: dict[tuple[str | int, ...], Any]
    ) -> None:
        def mutate(obj: Any) -> None:
            for path, value in fields.items():
                set_path(obj, path, value)

        await self.coordinator.async_update_config(
            self.entity_description.config, self.channel, mutate
        )


def config_entities[D: ICSeeConfigEntityDescription, E](
    coordinator: ICSeeCoordinator,
    descriptions: Iterable[D],
    factory: Callable[[ICSeeCoordinator, D, int], E],
) -> list[E]:
    """Create entities for the descriptions the camera supports."""
    channel_count = coordinator.config_entry.data.get(CONF_CHANNEL_COUNT, 1)
    entities = []
    for desc in descriptions:
        if desc.ability and not coordinator.ability(desc.ability):
            continue
        channels = range(channel_count) if CONFIGS[desc.config].per_channel else [0]
        for channel in channels:
            value = get_path(coordinator.channel_value(desc.config, channel), desc.path)
            if value is None:
                continue
            if desc.exists_fn and not desc.exists_fn(coordinator, value):
                continue
            entities.append(factory(coordinator, desc, channel))
    return entities
