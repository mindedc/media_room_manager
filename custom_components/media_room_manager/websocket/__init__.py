"""WebSocket command surface for Media Room Manager."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from .inspection import async_register_inspection_commands
from .profiles import async_register_profile_commands


def async_register_commands(hass: HomeAssistant) -> None:
    """Register all WebSocket commands for this integration."""
    async_register_inspection_commands(hass)
    async_register_profile_commands(hass)
