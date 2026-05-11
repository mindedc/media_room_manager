"""WebSocket commands for the path resolver.

Commands:
  media_room_manager/resolve_path  — returns the resolver result for a
      (zone, source, optional sink) triple without commanding any devices.
      This powers the Looking Glass in the Diagnostics panel.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from ..const import DOMAIN
from ..graph.system_config import SystemConfig
from ..resolver.path import (
    ActivePathsRegistry,
    ContentionReport,
    PathResolutionError,
    PathResolver,
    ResolvedSinglePath,
    ZoneResolverResult,
)


def _get_system_config(hass: HomeAssistant) -> SystemConfig | None:
    """Return the SystemConfig from hass.data, or None."""
    domain_data = hass.data.get(DOMAIN, {})
    if not domain_data:
        return None
    entry_data = next(iter(domain_data.values()))
    config = entry_data.get("system_config")
    if not isinstance(config, SystemConfig):
        return None
    return config


def _get_active_registry(hass: HomeAssistant) -> ActivePathsRegistry | None:
    """Return the ActivePathsRegistry from hass.data, or None."""
    domain_data = hass.data.get(DOMAIN, {})
    if not domain_data:
        return None
    entry_data = next(iter(domain_data.values()))
    reg = entry_data.get("active_paths")
    if not isinstance(reg, ActivePathsRegistry):
        return None
    return reg


def _serialize_path(path: ResolvedSinglePath | PathResolutionError) -> dict[str, Any]:
    """Serialize a path result to a JSON-safe dict."""
    if isinstance(path, PathResolutionError):
        return {
            "type": "error",
            "carrier": path.carrier,
            "source_device_id": path.source_device_id,
            "sink_device_id": path.sink_device_id,
            "reason": path.reason,
        }
    return {
        "type": "resolved",
        "carrier": path.carrier,
        "source_device_id": path.source_device_id,
        "sink_device_id": path.sink_device_id,
        "hops": [
            {
                "device_id": hop.device_id,
                "entry_interface_id": hop.entry_interface_id,
                "exit_interface_id": hop.exit_interface_id,
                "output_group_id": hop.output_group_id,
            }
            for hop in path.hops
        ],
    }


def _serialize_contention(report: ContentionReport) -> dict[str, Any]:
    """Serialize a ContentionReport to a JSON-safe dict."""
    return {
        "device_id": report.device_id,
        "kind": report.kind,
        "output_group_id": report.output_group_id,
        "conflicting_zone_id": report.conflicting_zone_id,
        "conflicting_input_interface_id": report.conflicting_input_interface_id,
        "conflicting_output_interface_id": report.conflicting_output_interface_id,
    }


def _serialize_result(result: ZoneResolverResult) -> dict[str, Any]:
    """Serialize a ZoneResolverResult to a JSON-safe dict."""
    return {
        "zone_id": result.zone_id,
        "source_device_id": result.source_device_id,
        "virtual_source_id": result.virtual_source_id,
        "is_virtual_source": result.is_virtual_source,
        "sink_device_ids": list(result.sink_device_ids),
        "video_paths": [_serialize_path(p) for p in result.video_paths],
        "audio_paths": [_serialize_path(p) for p in result.audio_paths],
        "contentions": [_serialize_contention(c) for c in result.contentions],
        "exclusive_output_usage": [
            {"device_id": dev_id, "interface_id": iface_id}
            for dev_id, iface_id in result.exclusive_output_usage
        ],
    }


def async_register_resolver_commands(hass: HomeAssistant) -> None:
    """Register resolver-related WebSocket commands."""
    websocket_api.async_register_command(hass, ws_resolve_path)


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/resolve_path",
        vol.Required("zone_id"): str,
        vol.Required("source_device_id"): str,
        vol.Optional("virtual_source_id"): vol.Any(str, None),
        vol.Optional("sink_device_id"): vol.Any(str, None),
    }
)
@websocket_api.async_response
@callback
async def ws_resolve_path(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Resolve the signal path for a (zone, source, optional sink) triple.

    Pure analysis — no devices are commanded. Intended for the Looking Glass.
    """
    config = _get_system_config(hass)
    if config is None:
        connection.send_error(msg["id"], "not_available", "System config not loaded")
        return

    active_registry = _get_active_registry(hass)
    resolver = PathResolver(config, active_registry)

    result = resolver.resolve(
        zone_id=msg["zone_id"],
        source_device_id=msg["source_device_id"],
        virtual_source_id=msg.get("virtual_source_id"),
        sink_device_id=msg.get("sink_device_id"),
    )

    connection.send_result(msg["id"], _serialize_result(result))
