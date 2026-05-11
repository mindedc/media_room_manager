"""Adapter for media_player_source mechanism.

The bound entity is a media_player. Source selection, power, volume, and
transport all map directly to standard HA media_player services.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .base import AdapterBase

_LOGGER = logging.getLogger(__name__)

_TRANSPORT_SERVICES: dict[str, str] = {
    "play": "media_play",
    "pause": "media_pause",
    "stop": "media_stop",
    "next_track": "media_next_track",
    "previous_track": "media_previous_track",
    "seek": "media_seek",
}


class MediaPlayerSourceAdapter(AdapterBase):
    """Controls a media_player entity using standard HA media_player services."""

    async def async_select_input(
        self,
        hass: HomeAssistant,
        entity_id: str,
        label: str,
        **kwargs: Any,
    ) -> None:
        """Select source by calling media_player.select_source."""
        await hass.services.async_call(
            "media_player",
            "select_source",
            {"entity_id": entity_id, "source": label},
            blocking=True,
        )

    async def async_power_on(
        self,
        hass: HomeAssistant,
        entity_id: str,
        **kwargs: Any,
    ) -> None:
        """Turn on via media_player.turn_on."""
        await hass.services.async_call(
            "media_player",
            "turn_on",
            {"entity_id": entity_id},
            blocking=True,
        )

    async def async_power_off(
        self,
        hass: HomeAssistant,
        entity_id: str,
        **kwargs: Any,
    ) -> None:
        """Turn off via media_player.turn_off."""
        await hass.services.async_call(
            "media_player",
            "turn_off",
            {"entity_id": entity_id},
            blocking=True,
        )

    async def async_set_volume(
        self,
        hass: HomeAssistant,
        entity_id: str,
        level: float,
        **kwargs: Any,
    ) -> None:
        """Set volume via media_player.volume_set."""
        await hass.services.async_call(
            "media_player",
            "volume_set",
            {"entity_id": entity_id, "volume_level": level},
            blocking=True,
        )

    async def async_volume_up(
        self,
        hass: HomeAssistant,
        entity_id: str,
        **kwargs: Any,
    ) -> None:
        """Increase volume via media_player.volume_up."""
        await hass.services.async_call(
            "media_player",
            "volume_up",
            {"entity_id": entity_id},
            blocking=True,
        )

    async def async_volume_down(
        self,
        hass: HomeAssistant,
        entity_id: str,
        **kwargs: Any,
    ) -> None:
        """Decrease volume via media_player.volume_down."""
        await hass.services.async_call(
            "media_player",
            "volume_down",
            {"entity_id": entity_id},
            blocking=True,
        )

    async def async_mute(
        self,
        hass: HomeAssistant,
        entity_id: str,
        muted: bool,
        **kwargs: Any,
    ) -> None:
        """Set mute state via media_player.volume_mute."""
        await hass.services.async_call(
            "media_player",
            "volume_mute",
            {"entity_id": entity_id, "is_volume_muted": muted},
            blocking=True,
        )

    async def async_send_transport(
        self,
        hass: HomeAssistant,
        entity_id: str,
        command: str,
        position: float | None = None,
        **kwargs: Any,
    ) -> None:
        """Send a transport command via the corresponding media_player service.

        Supported commands: play, pause, stop, next_track, previous_track, seek.
        For seek, position (seconds) must be provided.
        """
        service = _TRANSPORT_SERVICES.get(command)
        if service is None:
            _LOGGER.warning("Unsupported transport command %r", command)
            return

        data: dict[str, Any] = {"entity_id": entity_id}
        if command == "seek":
            if position is None:
                _LOGGER.warning("seek command requires a position value")
                return
            data["seek_position"] = position

        await hass.services.async_call(
            "media_player",
            service,
            data,
            blocking=True,
        )
