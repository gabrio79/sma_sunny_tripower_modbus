"""The SMA Sunny Tripower Modbus integration."""
from __future__ import annotations

import logging
from typing import Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import SmaModbusCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: Final[list[Platform]] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SMA Sunny Tripower Modbus from a config entry."""
    coordinator = SmaModbusCoordinator(hass, entry)

    # Perform initial data fetch
    await coordinator.async_config_entry_first_refresh()

    # Store coordinator instance
    entry.runtime_data = coordinator
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Listen for options updates
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an SMA Sunny Tripower Modbus config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    coordinator: SmaModbusCoordinator | None = getattr(entry, "runtime_data", None)
    if coordinator is None and DOMAIN in hass.data:
        coordinator = hass.data[DOMAIN].get(entry.entry_id)

    if coordinator is not None:
        await coordinator.async_close()

    if unload_ok and DOMAIN in hass.data:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options are changed."""
    await hass.config_entries.async_reload(entry.entry_id)
