"""Voluptuous schema for device profile YAML files.

Profiles are validated at load time. Any profile that doesn't pass this schema
is rejected; the integration does not silently ignore malformed profiles.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from ..graph.model import InterfaceDirection, InterfaceType, PowerHandling
from .types import (
    DiscoveryOutputGroupEntry,
    DiscoverySignal,
    Profile,
    ProfileAuxEntity,
    ProfileCategory,
    ProfileDiscovery,
    ProfileDynamicVirtualSources,
    ProfileInterface,
    ProfileOutputGroup,
    ProfileSelectionMechanism,
    ProfileVirtualSource,
    RoleOperation,
    RoleOperationSet,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_str_non_empty = vol.All(str, vol.Length(min=1))
_VALID_MECHANISM_KINDS = [
    "media_player_source",
    "select_entity",
    "switch_combo",
    "remote_command",
    "service_call",
]
_VALID_SIGNAL_KINDS = [
    "device_registry",
    "platform",
    "supported_features",
    "source_list_signature",
    "sound_mode_list_signature",
    "device_class",
    "friendly_name",
    "attribute_constellation",
]
_VALID_ROLES = [
    "transport",
    "volume",
    "metadata_source",
    "power",
    "source_selection",
]

# ---------------------------------------------------------------------------
# Role operations
# ---------------------------------------------------------------------------

ROLE_OPERATION_SCHEMA = vol.Schema(
    {
        vol.Required("command"): _str_non_empty,
        vol.Optional("delay", default=0.0): vol.Coerce(float),
    }
)

ROLE_OPERATION_SET_SCHEMA = vol.Schema(
    {
        vol.Required("kind"): vol.In(_VALID_MECHANISM_KINDS),
        vol.Required("operations"): {str: dict},
    }
)

# ---------------------------------------------------------------------------
# Selection mechanism
# ---------------------------------------------------------------------------

PROFILE_SELECTION_MECHANISM_SCHEMA = vol.Schema(
    {
        vol.Required("kind"): vol.In(_VALID_MECHANISM_KINDS),
        vol.Optional("expected_domain"): vol.Any(None, _str_non_empty),
        vol.Optional("expected_features", default=[]): [_str_non_empty],
        vol.Optional("expected_options", default=[]): [_str_non_empty],
        vol.Optional("expected_commands", default=[]): [_str_non_empty],
    }
)

# ---------------------------------------------------------------------------
# Output groups
# ---------------------------------------------------------------------------

PROFILE_OUTPUT_GROUP_SCHEMA = vol.Schema(
    {
        vol.Required("id"): _str_non_empty,
        vol.Optional("provides_roles", default=[]): [vol.In(_VALID_ROLES)],
        vol.Optional("selection_mechanism"): vol.Any(None, dict),
        vol.Optional("role_operations", default={}): {str: dict},
        vol.Optional("aux_entity"): _str_non_empty,  # reference to aux_entities[].id
    }
)

# ---------------------------------------------------------------------------
# Interfaces
# ---------------------------------------------------------------------------

PROFILE_INTERFACE_SCHEMA = vol.Schema(
    {
        vol.Required("id"): _str_non_empty,
        vol.Required("direction"): vol.In([d.value for d in InterfaceDirection]),
        vol.Required("type"): vol.In([t.value for t in InterfaceType]),
        vol.Required("label"): _str_non_empty,
        vol.Optional("output_group"): vol.Any(None, _str_non_empty),
        vol.Optional("routable_to_output_group", default=[]): [_str_non_empty],
    }
)

# ---------------------------------------------------------------------------
# Virtual sources
# ---------------------------------------------------------------------------

PROFILE_VIRTUAL_SOURCE_SCHEMA = vol.Schema(
    {
        vol.Required("id"): _str_non_empty,
        vol.Required("label"): _str_non_empty,
        vol.Optional("routable_to_output_group", default=[]): [_str_non_empty],
    }
)

PROFILE_DYNAMIC_VIRTUAL_SOURCES_SCHEMA = vol.Schema(
    {
        vol.Required("source"): _str_non_empty,
        vol.Required("output_group"): _str_non_empty,
        vol.Optional("exclude", default=[]): [str],
    }
)

# ---------------------------------------------------------------------------
# Aux entities
# ---------------------------------------------------------------------------

PROFILE_AUX_ENTITY_SCHEMA = vol.Schema(
    {
        vol.Required("id"): _str_non_empty,
        vol.Required("expected_domain"): _str_non_empty,
        vol.Optional("expected_features", default=[]): [_str_non_empty],
        vol.Optional("expected_commands", default=[]): [_str_non_empty],
        vol.Optional("expected_options", default=[]): [_str_non_empty],
    }
)

# ---------------------------------------------------------------------------
# Discovery signals
# ---------------------------------------------------------------------------

DISCOVERY_SIGNAL_SCHEMA = vol.Schema(
    {
        vol.Required("kind"): vol.In(_VALID_SIGNAL_KINDS),
        vol.Required("weight"): vol.All(int, vol.Range(min=0, max=100)),
        vol.Optional("manufacturer"): _str_non_empty,
        vol.Optional("model_patterns", default=[]): [_str_non_empty],
        vol.Optional("domain"): _str_non_empty,
        vol.Optional("values", default=[]): [int],
        vol.Optional("includes_any", default=[]): [str],
        vol.Optional("includes", default=[]): [str],
        vol.Optional("matches", default=[]): [str],
        vol.Optional("friendly_name_patterns", default=[]): [_str_non_empty],
    }
)

DISCOVERY_OUTPUT_GROUP_ENTRY_SCHEMA = vol.Schema(
    {
        vol.Required("output_group"): _str_non_empty,
        vol.Optional("is_discovery_anchor", default=False): bool,
        vol.Optional("match_threshold", default=60): vol.All(int, vol.Range(min=0, max=100)),
        vol.Optional("optional", default=False): bool,
        vol.Optional("signals", default=[]): [dict],
    }
)

PROFILE_DISCOVERY_SCHEMA = vol.Schema(
    {
        vol.Required("output_groups"): [dict],
    }
)

# ---------------------------------------------------------------------------
# Top-level profile schema
# ---------------------------------------------------------------------------

PROFILE_SCHEMA = vol.Schema(
    {
        vol.Required("profile_id"): _str_non_empty,
        vol.Required("schema_version"): int,
        vol.Required("manufacturer"): _str_non_empty,
        vol.Required("model"): _str_non_empty,
        vol.Required("category"): vol.In([c.value for c in ProfileCategory]),
        vol.Optional("power_handling", default=PowerHandling.DISABLED.value): vol.In(
            [p.value for p in PowerHandling]
        ),
        vol.Optional("power_on_delay", default=0): vol.All(int, vol.Range(min=0)),
        vol.Optional("exclusive_outputs", default=False): bool,
        vol.Optional("output_groups", default=[]): [dict],
        vol.Optional("inputs_are_exclusive_per_output_group", default=[]): [_str_non_empty],
        vol.Optional("interfaces", default=[]): [dict],
        vol.Optional("virtual_sources", default=[]): [dict],
        vol.Optional("dynamic_virtual_sources"): vol.Any(None, dict),
        vol.Optional("aux_entities", default=[]): [dict],
        vol.Optional("discovery"): vol.Any(None, dict),
    }
)


# ---------------------------------------------------------------------------
# Constructor helpers
# ---------------------------------------------------------------------------


def _build_role_operation(d: dict[str, Any]) -> RoleOperation:
    v = ROLE_OPERATION_SCHEMA(d)
    return RoleOperation(command=v["command"], delay=v["delay"])


def _build_role_operation_set(d: dict[str, Any]) -> RoleOperationSet:
    v = ROLE_OPERATION_SET_SCHEMA(d)
    return RoleOperationSet(
        kind=v["kind"],
        operations={k: _build_role_operation(op) for k, op in v["operations"].items()},
    )


def _build_selection_mechanism(d: dict[str, Any]) -> ProfileSelectionMechanism:
    v = PROFILE_SELECTION_MECHANISM_SCHEMA(d)
    return ProfileSelectionMechanism(
        kind=v["kind"],
        expected_domain=v.get("expected_domain"),
        expected_features=tuple(v.get("expected_features", [])),
        expected_options=tuple(v.get("expected_options", [])),
        expected_commands=tuple(v.get("expected_commands", [])),
    )


def _build_output_group(d: dict[str, Any]) -> ProfileOutputGroup:
    v = PROFILE_OUTPUT_GROUP_SCHEMA(d)
    mech_dict = v.get("selection_mechanism")
    return ProfileOutputGroup(
        id=v["id"],
        provides_roles=tuple(v.get("provides_roles", [])),
        selection_mechanism=(_build_selection_mechanism(mech_dict) if mech_dict else None),
        role_operations={
            role: _build_role_operation_set(ops)
            for role, ops in v.get("role_operations", {}).items()
        },
    )


def _build_interface(d: dict[str, Any]) -> ProfileInterface:
    v = PROFILE_INTERFACE_SCHEMA(d)
    return ProfileInterface(
        id=v["id"],
        direction=InterfaceDirection(v["direction"]),
        type=InterfaceType(v["type"]),
        label=v["label"],
        output_group=v.get("output_group"),
        routable_to_output_group=tuple(v.get("routable_to_output_group", [])),
    )


def _build_virtual_source(d: dict[str, Any]) -> ProfileVirtualSource:
    v = PROFILE_VIRTUAL_SOURCE_SCHEMA(d)
    return ProfileVirtualSource(
        id=v["id"],
        label=v["label"],
        routable_to_output_group=tuple(v.get("routable_to_output_group", [])),
    )


def _build_dynamic_virtual_sources(d: dict[str, Any]) -> ProfileDynamicVirtualSources:
    v = PROFILE_DYNAMIC_VIRTUAL_SOURCES_SCHEMA(d)
    return ProfileDynamicVirtualSources(
        source=v["source"],
        output_group=v["output_group"],
        exclude=tuple(v.get("exclude", [])),
    )


def _build_aux_entity(d: dict[str, Any]) -> ProfileAuxEntity:
    v = PROFILE_AUX_ENTITY_SCHEMA(d)
    return ProfileAuxEntity(
        id=v["id"],
        expected_domain=v["expected_domain"],
        expected_features=tuple(v.get("expected_features", [])),
        expected_commands=tuple(v.get("expected_commands", [])),
        expected_options=tuple(v.get("expected_options", [])),
    )


def _build_discovery_signal(d: dict[str, Any]) -> DiscoverySignal:
    v = DISCOVERY_SIGNAL_SCHEMA(d)
    return DiscoverySignal(
        kind=v["kind"],
        weight=v["weight"],
        manufacturer=v.get("manufacturer"),
        model_patterns=tuple(v.get("model_patterns", [])),
        domain=v.get("domain"),
        values=tuple(v.get("values", [])),
        includes_any=tuple(v.get("includes_any", [])),
        includes=tuple(v.get("includes", [])),
        matches=tuple(v.get("matches", [])),
        friendly_name_patterns=tuple(v.get("friendly_name_patterns", [])),
    )


def _build_discovery_output_group_entry(d: dict[str, Any]) -> DiscoveryOutputGroupEntry:
    v = DISCOVERY_OUTPUT_GROUP_ENTRY_SCHEMA(d)
    return DiscoveryOutputGroupEntry(
        output_group=v["output_group"],
        signals=tuple(_build_discovery_signal(s) for s in v.get("signals", [])),
        is_discovery_anchor=v.get("is_discovery_anchor", False),
        match_threshold=v.get("match_threshold", 60),
        optional=v.get("optional", False),
    )


def _build_discovery(d: dict[str, Any]) -> ProfileDiscovery:
    v = PROFILE_DISCOVERY_SCHEMA(d)
    return ProfileDiscovery(
        output_groups=tuple(_build_discovery_output_group_entry(og) for og in v["output_groups"])
    )


def _selection_mechanism_to_dict(mech: ProfileSelectionMechanism) -> dict[str, Any]:
    return {
        "kind": mech.kind,
        "expected_domain": mech.expected_domain,
        "expected_features": list(mech.expected_features),
        "expected_options": list(mech.expected_options),
        "expected_commands": list(mech.expected_commands),
    }


def _role_operation_to_dict(op: RoleOperation) -> dict[str, Any]:
    return {"command": op.command, "delay": op.delay}


def _role_operation_set_to_dict(ros: RoleOperationSet) -> dict[str, Any]:
    return {
        "kind": ros.kind,
        "operations": {k: _role_operation_to_dict(v) for k, v in ros.operations.items()},
    }


def _output_group_to_dict(og: ProfileOutputGroup) -> dict[str, Any]:
    return {
        "id": og.id,
        "provides_roles": list(og.provides_roles),
        "selection_mechanism": (
            _selection_mechanism_to_dict(og.selection_mechanism) if og.selection_mechanism else None
        ),
        "role_operations": {
            k: _role_operation_set_to_dict(v) for k, v in og.role_operations.items()
        },
    }


def _interface_to_dict(iface: ProfileInterface) -> dict[str, Any]:
    return {
        "id": iface.id,
        "direction": iface.direction.value,
        "type": iface.type.value,
        "label": iface.label,
        "output_group": iface.output_group,
        "routable_to_output_group": list(iface.routable_to_output_group),
    }


def _virtual_source_to_dict(vs: ProfileVirtualSource) -> dict[str, Any]:
    return {
        "id": vs.id,
        "label": vs.label,
        "routable_to_output_group": list(vs.routable_to_output_group),
    }


def _dynamic_virtual_sources_to_dict(dvs: ProfileDynamicVirtualSources) -> dict[str, Any]:
    return {
        "source": dvs.source,
        "output_group": dvs.output_group,
        "exclude": list(dvs.exclude),
    }


def _aux_entity_to_dict(ae: ProfileAuxEntity) -> dict[str, Any]:
    return {
        "id": ae.id,
        "expected_domain": ae.expected_domain,
        "expected_features": list(ae.expected_features),
        "expected_commands": list(ae.expected_commands),
        "expected_options": list(ae.expected_options),
    }


def _discovery_signal_to_dict(sig: DiscoverySignal) -> dict[str, Any]:
    return {
        "kind": sig.kind,
        "weight": sig.weight,
        "manufacturer": sig.manufacturer,
        "model_patterns": list(sig.model_patterns),
        "domain": sig.domain,
        "values": list(sig.values),
        "includes_any": list(sig.includes_any),
        "includes": list(sig.includes),
        "matches": list(sig.matches),
        "friendly_name_patterns": list(sig.friendly_name_patterns),
    }


def _discovery_output_group_entry_to_dict(entry: DiscoveryOutputGroupEntry) -> dict[str, Any]:
    return {
        "output_group": entry.output_group,
        "is_discovery_anchor": entry.is_discovery_anchor,
        "match_threshold": entry.match_threshold,
        "optional": entry.optional,
        "signals": [_discovery_signal_to_dict(s) for s in entry.signals],
    }


def _discovery_to_dict(disc: ProfileDiscovery) -> dict[str, Any]:
    return {
        "output_groups": [_discovery_output_group_entry_to_dict(e) for e in disc.output_groups],
    }


def profile_to_dict(profile: Profile) -> dict[str, Any]:
    """Serialize a Profile to a plain dict suitable for JSON / WebSocket responses."""
    return {
        "profile_id": profile.profile_id,
        "schema_version": profile.schema_version,
        "manufacturer": profile.manufacturer,
        "model": profile.model,
        "category": profile.category.value,
        "power_handling": profile.power_handling.value,
        "power_on_delay": profile.power_on_delay,
        "exclusive_outputs": profile.exclusive_outputs,
        "output_groups": [_output_group_to_dict(og) for og in profile.output_groups],
        "interfaces": [_interface_to_dict(i) for i in profile.interfaces],
        "virtual_sources": [_virtual_source_to_dict(vs) for vs in profile.virtual_sources],
        "dynamic_virtual_sources": (
            _dynamic_virtual_sources_to_dict(profile.dynamic_virtual_sources)
            if profile.dynamic_virtual_sources
            else None
        ),
        "aux_entities": [_aux_entity_to_dict(ae) for ae in profile.aux_entities],
        "inputs_are_exclusive_per_output_group": list(
            profile.inputs_are_exclusive_per_output_group
        ),
        "discovery": _discovery_to_dict(profile.discovery) if profile.discovery else None,
    }


def profile_from_dict(d: dict[str, Any]) -> Profile:
    """Validate and construct a Profile from a raw dict (e.g. parsed YAML).

    Raises vol.Invalid if the dict doesn't conform to the profile schema.
    """
    v = PROFILE_SCHEMA(d)
    dvs_dict = v.get("dynamic_virtual_sources")
    disc_dict = v.get("discovery")
    return Profile(
        profile_id=v["profile_id"],
        schema_version=v["schema_version"],
        manufacturer=v["manufacturer"],
        model=v["model"],
        category=ProfileCategory(v["category"]),
        power_handling=PowerHandling(v["power_handling"]),
        power_on_delay=v["power_on_delay"],
        exclusive_outputs=v["exclusive_outputs"],
        output_groups=tuple(_build_output_group(og) for og in v.get("output_groups", [])),
        interfaces=tuple(_build_interface(i) for i in v.get("interfaces", [])),
        virtual_sources=tuple(_build_virtual_source(vs) for vs in v.get("virtual_sources", [])),
        dynamic_virtual_sources=(_build_dynamic_virtual_sources(dvs_dict) if dvs_dict else None),
        aux_entities=tuple(_build_aux_entity(ae) for ae in v.get("aux_entities", [])),
        inputs_are_exclusive_per_output_group=tuple(
            v.get("inputs_are_exclusive_per_output_group", [])
        ),
        discovery=(_build_discovery(disc_dict) if disc_dict else None),
    )
