"""Read-only WebSocket inspection commands.

Commands:
  media_room_manager/list_devices      — returns all configured devices
  media_room_manager/list_zones        — returns all configured zones
  media_room_manager/list_connections  — returns all configured connections
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from ..const import DOMAIN
from ..graph.schema import connection_to_dict, device_to_dict, zone_to_dict


def _get_config(hass: HomeAssistant, entry_id: str | None = None) -> Any:
    """Return the SystemConfig for the given entry, or the first found."""
    domain_data = hass.data.get(DOMAIN, {})
    if not domain_data:
        return None
    if entry_id is not None:
        entry_data = domain_data.get(entry_id)
        return entry_data["config"] if entry_data else None
    # Single-instance: return the first entry's config
    return next(iter(domain_data.values()))["config"]


def async_register_inspection_commands(hass: HomeAssistant) -> None:
    """Register the read-only inspection WebSocket commands."""
    websocket_api.async_register_command(hass, ws_list_devices)
    websocket_api.async_register_command(hass, ws_list_zones)
    websocket_api.async_register_command(hass, ws_list_connections)


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/list_devices",
    }
)
@callback
def ws_list_devices(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return all configured devices."""
    config = _get_config(hass)
    if config is None:
        connection.send_result(msg["id"], {"devices": []})
        return
    connection.send_result(
        msg["id"],
        {"devices": [device_to_dict(d) for d in config.devices]},
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/list_zones",
    }
)
@callback
def ws_list_zones(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return all configured zones."""
    config = _get_config(hass)
    if config is None:
        connection.send_result(msg["id"], {"zones": []})
        return
    connection.send_result(
        msg["id"],
        {"zones": [zone_to_dict(z) for z in config.zones]},
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/list_connections",
    }
)
@callback
def ws_list_connections(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return all configured connections."""
    config = _get_config(hass)
    if config is None:
        connection.send_result(msg["id"], {"connections": []})
        return
    connection.send_result(
        msg["id"],
        {"connections": [connection_to_dict(c) for c in config.connections]},
    )
