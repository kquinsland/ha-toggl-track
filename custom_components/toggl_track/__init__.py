"""Example of a custom component exposing a service."""

from __future__ import annotations

from datetime import timedelta
import logging

from lib_toggl.client import Toggl

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant

from .const import DOMAIN, STARTUP_MESSAGE
from .coordinator import TogglTrackCoordinator
from .services import async_register_services

_LOGGER = logging.getLogger(__name__)


# For now, only define sensor platform
PLATFORMS: list[str] = ["sensor"]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the integration."""
    _LOGGER.info(STARTUP_MESSAGE)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up an instance of the integration.

    The goal is to support multiple instances of the platform so we don't have much to do for the _normal_ setup flow async_setup()
    After the user ahs done the config flow and we have the configuration data for this specific instance, we can do the rest of the setup.
    """
    _LOGGER.debug("Doing entry instance setup")

    api_key = entry.data[CONF_API_KEY]
    scan_interval = entry.data.get(CONF_SCAN_INTERVAL)
    api_client = Toggl(api_key)

    coordinator = TogglTrackCoordinator(
        hass,
        _LOGGER,
        # Polling interval. Will only be polled if there are subscribers.
        update_interval=timedelta(seconds=scan_interval),
        api=api_client,
    )

    # Get initial data from API
    await coordinator.async_config_entry_first_refresh()
    await coordinator.async_get_workspaces()

    # Assuming nothing went wrong, store instance of coordinator
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Init sensor
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Add services
    async_register_services(hass, coordinator)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry.

    This is called when an entry/configured device is to be removed. The class
    needs to unload itself, and remove callbacks. See the classes for further
    details
    """
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_update_options(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Update options."""
    # TODO: fetch workspace list again and do the user flow again?
    _LOGGER.debug("Reloading. Currently nothing to do here")
    await hass.config_entries.async_reload(config_entry.entry_id)
