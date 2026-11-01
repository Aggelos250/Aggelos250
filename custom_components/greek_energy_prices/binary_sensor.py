"""Binary sensor: is now one of today's cheapest hours?"""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import GREECE_TZ
from .coordinator import GreekEnergyConfigEntry, GreekEnergyCoordinator
from .entity import GreekEnergyEntity
from .pricing import cheapest_intervals, interval_at

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GreekEnergyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensor."""
    async_add_entities([CheapNowBinarySensor(entry.runtime_data)])


class CheapNowBinarySensor(GreekEnergyEntity, BinarySensorEntity):
    """On while the current interval is among today's N cheapest hours."""

    def __init__(self, coordinator: GreekEnergyCoordinator) -> None:
        """Initialise."""
        super().__init__(coordinator, "cheap_now")

    @property
    def is_on(self) -> bool | None:
        """Return true during a cheap interval."""
        data = self.coordinator.data
        current = interval_at(data.today, dt_util.utcnow())
        if current is None:
            return None
        return current in cheapest_intervals(data.today, data.cheap_hours)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """List the cheap intervals for today."""
        data = self.coordinator.data
        return {
            "hours": data.cheap_hours,
            "intervals": [
                i.as_dict(GREECE_TZ)
                for i in cheapest_intervals(data.today, data.cheap_hours)
            ],
        }
