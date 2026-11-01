"""Greek dynamic electricity prices for Home Assistant."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import GreekEnergyConfigEntry, GreekEnergyCoordinator

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: GreekEnergyConfigEntry) -> bool:
    """Set up from a config entry."""
    coordinator = GreekEnergyCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    coordinator.async_start_ticks()
    entry.async_on_unload(coordinator.async_stop_ticks)
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: GreekEnergyConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_options_updated(
    hass: HomeAssistant, entry: GreekEnergyConfigEntry
) -> None:
    """Reload when the tariff settings change."""
    await hass.config_entries.async_reload(entry.entry_id)
