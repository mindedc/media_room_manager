"""Media Room Manager — AV signal-routing and orchestration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .store import MRMStore
from .websocket import async_register_commands

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Media Room Manager from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    store = MRMStore(hass)
    config = await store.async_load()

    hass.data[DOMAIN][entry.entry_id] = {"store": store, "config": config}

    async_register_commands(hass)

    _LOGGER.debug(
        "Media Room Manager entry %s set up; %d device(s) loaded",
        entry.entry_id,
        len(config.devices),
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    hass.data[DOMAIN].pop(entry.entry_id, None)
    return True
