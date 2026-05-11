"""Abstract base class for all output group adapters.

Each adapter implements one of the five supported control mechanisms:
media_player_source, select_entity, switch_combo, remote_command, service_call.

All methods raise NotImplementedError by default; subclasses override only
the operations their mechanism supports. The orchestrator checks capability
before calling rather than catching NotImplementedError at runtime.

Extra mechanism-specific config is passed via **kwargs so all adapters share
the same call signature and the registry can hold a single instance per kind.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant


class AdapterBase:
    """Base class for output group control adapters."""

    async def async_select_input(
        self,
        hass: HomeAssistant,
        entity_id: str,
        label: str,
        **kwargs: Any,
    ) -> None:
        """Select the input with the given label on the bound entity."""
        raise NotImplementedError(f"{type(self).__name__} does not support select_input")

    async def async_power_on(
        self,
        hass: HomeAssistant,
        entity_id: str,
        **kwargs: Any,
    ) -> None:
        """Power on the bound entity."""
        raise NotImplementedError(f"{type(self).__name__} does not support power_on")

    async def async_power_off(
        self,
        hass: HomeAssistant,
        entity_id: str,
        **kwargs: Any,
    ) -> None:
        """Power off the bound entity."""
        raise NotImplementedError(f"{type(self).__name__} does not support power_off")

    async def async_set_volume(
        self,
        hass: HomeAssistant,
        entity_id: str,
        level: float,
        **kwargs: Any,
    ) -> None:
        """Set volume to level (0.0-1.0)."""
        raise NotImplementedError(f"{type(self).__name__} does not support set_volume")

    async def async_volume_up(
        self,
        hass: HomeAssistant,
        entity_id: str,
        **kwargs: Any,
    ) -> None:
        """Increase volume by one step."""
        raise NotImplementedError(f"{type(self).__name__} does not support volume_up")

    async def async_volume_down(
        self,
        hass: HomeAssistant,
        entity_id: str,
        **kwargs: Any,
    ) -> None:
        """Decrease volume by one step."""
        raise NotImplementedError(f"{type(self).__name__} does not support volume_down")

    async def async_mute(
        self,
        hass: HomeAssistant,
        entity_id: str,
        muted: bool,
        **kwargs: Any,
    ) -> None:
        """Set mute state."""
        raise NotImplementedError(f"{type(self).__name__} does not support mute")

    async def async_send_transport(
        self,
        hass: HomeAssistant,
        entity_id: str,
        command: str,
        position: float | None = None,
        **kwargs: Any,
    ) -> None:
        """Send a transport command (play/pause/stop/next_track/previous_track/seek).

        For seek, pass position (seconds, float).
        """
        raise NotImplementedError(f"{type(self).__name__} does not support send_transport")
