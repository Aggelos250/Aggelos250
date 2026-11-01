"""Base entity for Greek Energy Prices."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import GreekEnergyCoordinator


class GreekEnergyEntity(CoordinatorEntity[GreekEnergyCoordinator]):
    """Common entity attributes."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: GreekEnergyCoordinator, key: str) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Greek electricity prices",
            manufacturer="ENTSO-E / HEnEx",
            model="Day-ahead market (GR)",
            entry_type=DeviceEntryType.SERVICE,
        )
