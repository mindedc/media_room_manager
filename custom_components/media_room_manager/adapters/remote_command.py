"""Adapter for remote_command mechanism.

The bound entity is a remote (IR/RF blaster). Operations map to
remote.send_command calls with configured command strings and optional delays.

Required kwargs per method:
  async_select_input   — command: str, delay: float = 0.0
  async_power_on       — command: str, delay: float = 0.0
  async_power_off      — command: str, delay: float = 0.0
  async_send_transport — command_map: dict[str, str] | None, delay: float = 0.0

The 'delay' is stored in the profile's RoleOperation and passed by the
orchestrator. When delay > 0, the adapter issues the command and the
orchestrator is responsible for waiting after the call returns.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .base import AdapterBase

_LOGGER = logging.getLogger(__name__)


class RemoteCommandAdapter(AdapterBase):
    """Controls a remote entity by sending named commands."""

    async def _send(
        self,
        hass: HomeAssistant,
        entity_id: str,
        command: str,
    ) -> None:
        """Send a single command to the remote entity."""
        await hass.services.async_call(
            "remote",
            "send_command",
            {"entity_id": entity_id, "command": command},
            blocking=True,
        )

    async def async_select_input(
        self,
        hass: HomeAssistant,
        entity_id: str,
        label: str,
        **kwargs: Any,
    ) -> None:
        """Send the configured command for input selection.

        Required kwarg: command (str)
        """
        command: str = kwargs["command"]
        await self._send(hass, entity_id, command)

    async def async_power_on(
        self,
        hass: HomeAssistant,
        entity_id: str,
        **kwargs: Any,
    ) -> None:
        """Send the configured power-on command.

        Required kwarg: command (str)
        """
        command: str = kwargs["command"]
        await self._send(hass, entity_id, command)

    async def async_power_off(
        self,
        hass: HomeAssistant,
        entity_id: str,
        **kwargs: Any,
    ) -> None:
        """Send the configured power-off command.

        Required kwarg: command (str)
        """
        command: str = kwargs["command"]
        await self._send(hass, entity_id, command)

    async def async_send_transport(
        self,
        hass: HomeAssistant,
        entity_id: str,
        command: str,
        position: float | None = None,
        **kwargs: Any,
    ) -> None:
        """Send a transport command using the command_map to resolve the remote command.

        Optional kwarg: command_map (dict[str, str]) maps transport verbs to remote
        command strings. If absent or the verb isn't mapped, the verb itself is sent.
        """
        command_map: dict[str, str] | None = kwargs.get("command_map")
        remote_cmd = (command_map or {}).get(command, command)
        await self._send(hass, entity_id, remote_cmd)
