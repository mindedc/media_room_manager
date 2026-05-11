"""WebSocket commands for the profile registry.

Commands:
  media_room_manager/list_profiles  — returns all loaded profile ids and metadata
  media_room_manager/get_profile    — returns the full serialized Profile for a given profile_id
"""

from __future__ import annotations

from typing import Any, cast

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from ..const import DOMAIN
from ..profiles.registry import ProfileRegistry
from ..profiles.schema import profile_to_dict


def _get_registry(hass: HomeAssistant) -> ProfileRegistry | None:
    """Return the ProfileRegistry from hass.data, or None if not available."""
    domain_data = hass.data.get(DOMAIN, {})
    if not domain_data:
        return None
    entry_data = next(iter(domain_data.values()))
    return cast(ProfileRegistry | None, entry_data.get("registry"))


def async_register_profile_commands(hass: HomeAssistant) -> None:
    """Register profile-related WebSocket commands."""
    websocket_api.async_register_command(hass, ws_list_profiles)
    websocket_api.async_register_command(hass, ws_get_profile)


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/list_profiles",
    }
)
@callback
def ws_list_profiles(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return all loaded profiles as lightweight summary dicts."""
    registry = _get_registry(hass)
    if registry is None:
        connection.send_result(msg["id"], {"profiles": []})
        return
    summaries = [
        {
            "profile_id": p.profile_id,
            "manufacturer": p.manufacturer,
            "model": p.model,
            "category": p.category.value,
            "power_handling": p.power_handling.value,
        }
        for p in registry.list_all()
    ]
    connection.send_result(msg["id"], {"profiles": summaries})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/get_profile",
        vol.Required("profile_id"): str,
    }
)
@callback
def ws_get_profile(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return the full serialized Profile for the given profile_id."""
    registry = _get_registry(hass)
    if registry is None:
        connection.send_error(msg["id"], "not_found", "Profile registry not available")
        return
    profile = registry.get(msg["profile_id"])
    if profile is None:
        connection.send_error(msg["id"], "not_found", f"Profile '{msg['profile_id']}' not found")
        return
    connection.send_result(msg["id"], {"profile": profile_to_dict(profile)})
