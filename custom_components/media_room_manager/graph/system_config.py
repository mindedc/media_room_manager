"""SystemConfig aggregate holding all graph data.

SystemConfig is the top-level object persisted to HA's Store. It is
intentionally flat — a collection of lists with no cross-references
encoded in the object graph itself (references are by ID strings).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import voluptuous as vol

from .model import Connection, Device, DeviceInstance, SourceVisibilitySelection, Zone
from .schema import (
    connection_from_dict,
    connection_to_dict,
    device_from_dict,
    device_instance_from_dict,
    device_instance_to_dict,
    device_to_dict,
    source_visibility_from_dict,
    source_visibility_to_dict,
    zone_from_dict,
    zone_to_dict,
)

SYSTEM_CONFIG_SCHEMA_VERSION = 1

_SYSTEM_CONFIG_SCHEMA = vol.Schema(
    {
        vol.Required("schema_version"): int,
        vol.Optional("devices", default=[]): [dict],
        vol.Optional("connections", default=[]): [dict],
        vol.Optional("zones", default=[]): [dict],
        vol.Optional("device_instances", default=[]): [dict],
        vol.Optional("source_visibility", default=[]): [dict],
    }
)


@dataclass
class SystemConfig:
    """Top-level container for all Media Room Manager graph data."""

    schema_version: int = SYSTEM_CONFIG_SCHEMA_VERSION
    devices: list[Device] = field(default_factory=list)
    connections: list[Connection] = field(default_factory=list)
    zones: list[Zone] = field(default_factory=list)
    device_instances: list[DeviceInstance] = field(default_factory=list)
    source_visibility: list[SourceVisibilitySelection] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a storage-ready dict."""
        return {
            "schema_version": self.schema_version,
            "devices": [device_to_dict(d) for d in self.devices],
            "connections": [connection_to_dict(c) for c in self.connections],
            "zones": [zone_to_dict(z) for z in self.zones],
            "device_instances": [device_instance_to_dict(i) for i in self.device_instances],
            "source_visibility": [source_visibility_to_dict(s) for s in self.source_visibility],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SystemConfig:
        """Validate and deserialize from a dict loaded from storage."""
        v = _SYSTEM_CONFIG_SCHEMA(d)
        return cls(
            schema_version=v["schema_version"],
            devices=[device_from_dict(dev) for dev in v["devices"]],
            connections=[connection_from_dict(conn) for conn in v["connections"]],
            zones=[zone_from_dict(z) for z in v["zones"]],
            device_instances=[device_instance_from_dict(inst) for inst in v["device_instances"]],
            source_visibility=[source_visibility_from_dict(s) for s in v["source_visibility"]],
        )

    @classmethod
    def empty(cls) -> SystemConfig:
        """Return a fresh empty config at the current schema version."""
        return cls()
