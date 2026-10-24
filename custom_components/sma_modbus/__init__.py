"""The SMA Sunny Tripower Modbus integration."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

try:
    from homeassistant.components.http import StaticPathConfig
except ImportError:
    StaticPathConfig = None  # type: ignore[assignment,misc]

from .const import DOMAIN
from .coordinator import SmaModbusCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: Final[list[Platform]] = [Platform.SENSOR]
URL_CARD_PATH: Final[str] = "/sma_modbus/sma-tripower-card.js"
LOCAL_CARD_PATH: Final[Path] = Path(__file__).parent / "frontend" / "sma-tripower-card.js"


async def _async_register_frontend(hass: HomeAssistant) -> None:
    """Register custom Lovelace card HTTP static path and resource."""
    if not LOCAL_CARD_PATH.exists():
        return

    # 1. Register HTTP static paths (both directory and direct file URL)
    frontend_dir = LOCAL_CARD_PATH.parent
    if hasattr(hass.http, "async_register_static_paths") and StaticPathConfig is not None:
        try:
            await hass.http.async_register_static_paths([
                StaticPathConfig(URL_CARD_PATH, str(LOCAL_CARD_PATH), cache_headers=False),
                StaticPathConfig("/sma_modbus", str(frontend_dir), cache_headers=False),
            ])
            _LOGGER.debug("Registered static paths %s and /sma_modbus", URL_CARD_PATH)
        except Exception as err:
            _LOGGER.debug("Error in async_register_static_paths: %s", err)
    elif hasattr(hass.http, "register_static_path"):
        try:
            hass.http.register_static_path(URL_CARD_PATH, str(LOCAL_CARD_PATH), cache_headers=False)
            hass.http.register_static_path("/sma_modbus", str(frontend_dir), cache_headers=False)
            _LOGGER.debug("Registered legacy static paths")
        except Exception as err:
            _LOGGER.debug("Error in register_static_path: %s", err)

    # 2. Automatically copy to /config/www/ so /local/sma-tripower-card.js always works out-of-the-box
    try:
        import shutil
        www_dir = Path(hass.config.path("www"))
        www_dir.mkdir(parents=True, exist_ok=True)
        target_file = www_dir / "sma-tripower-card.js"
        if not target_file.exists() or target_file.read_bytes() != LOCAL_CARD_PATH.read_bytes():
            await hass.async_add_executor_job(shutil.copy2, str(LOCAL_CARD_PATH), str(target_file))
            _LOGGER.info("Copied sma-tripower-card.js to %s", target_file)
    except Exception as err:
        _LOGGER.debug("Could not copy card to www directory: %s", err)

    # 3. Automatically register into Lovelace resources if available
    try:
        lovelace = hass.data.get("lovelace")
        if lovelace and hasattr(lovelace, "resources") and lovelace.resources:
            resources = lovelace.resources
            if hasattr(resources, "loaded") and not resources.loaded:
                await resources.async_load()

            items = []
            if hasattr(resources, "async_items"):
                items = resources.async_items()
            elif hasattr(resources, "async_get_items"):
                items = resources.async_get_items()
            elif hasattr(resources, "data"):
                items = resources.data

            existing_urls = [
                item.get("url")
                for item in items
                if isinstance(item, dict) and "url" in item
            ]

            if (
                URL_CARD_PATH not in existing_urls
                and "/local/sma-tripower-card.js" not in existing_urls
                and hasattr(resources, "async_create_item")
            ):
                await resources.async_create_item({
                    "res_type": "module",
                    "url": URL_CARD_PATH,
                })
                _LOGGER.info("Registered Lovelace resource: %s", URL_CARD_PATH)
    except Exception as err:
        _LOGGER.debug("Could not automatically register Lovelace resource: %s", err)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the SMA Sunny Tripower Modbus component."""
    await _async_register_frontend(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SMA Sunny Tripower Modbus from a config entry."""
    # Ensure frontend card is registered
    await _async_register_frontend(hass)

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
