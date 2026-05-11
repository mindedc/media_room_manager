"""Voluptuous schemas for graph model dataclasses.

Each schema validates a dict representation of the corresponding dataclass and
can be used both for validation and for round-trip serialization.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

import voluptuous as vol

from .model import (
    AuxEntity,
    Connection,
    ContentionPolicy,
    ControlRole,
    Device,
    DeviceInstance,
    DynamicVirtualSources,
    InstanceBinding,
    Interface,
    InterfaceDirection,
    InterfaceType,
    MechanismKind,
    OutputGroup,
    PowerHandling,
    SelectionMechanism,
    SinkMode,
    SourceRef,
    SourceVisibilitySelection,
    VirtualSource,
    Zone,
)

# ---------------------------------------------------------------------------
# Reusable leaf validators
# ---------------------------------------------------------------------------

_str_non_empty = vol.All(str, vol.Length(min=1))


def _enum_in(enum_class: type[StrEnum]) -> vol.In:
    """Return a validator that accepts any value of the given StrEnum."""
    return vol.In([e.value for e in enum_class])


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

INTERFACE_SCHEMA = vol.Schema(
    {
        vol.Required("id"): _str_non_empty,
        vol.Required("direction"): _enum_in(InterfaceDirection),
        vol.Required("type"): _enum_in(InterfaceType),
        vol.Required("label"): _str_non_empty,
        vol.Optional("output_group"): vol.Any(None, _str_non_empty),
        vol.Optional("routable_to_output_group", default=[]): [_str_non_empty],
    }
)


def interface_from_dict(d: dict[str, Any]) -> Interface:
    """Validate and construct an Interface from a dict."""
    v = INTERFACE_SCHEMA(d)
    return Interface(
        id=v["id"],
        direction=InterfaceDirection(v["direction"]),
        type=InterfaceType(v["type"]),
        label=v["label"],
        output_group=v.get("output_group"),
        routable_to_output_group=tuple(v.get("routable_to_output_group", [])),
    )


def interface_to_dict(i: Interface) -> dict[str, Any]:
    """Serialize an Interface to a dict."""
    d: dict[str, Any] = {
        "id": i.id,
        "direction": i.direction.value,
        "type": i.type.value,
        "label": i.label,
        "routable_to_output_group": list(i.routable_to_output_group),
    }
    if i.output_group is not None:
        d["output_group"] = i.output_group
    return d


# ---------------------------------------------------------------------------
# SelectionMechanism
# ---------------------------------------------------------------------------

SELECTION_MECHANISM_SCHEMA = vol.Schema(
    {
        vol.Required("kind"): _enum_in(MechanismKind),
        vol.Optional("expected_domain"): vol.Any(None, _str_non_empty),
        vol.Optional("expected_features", default=[]): [_str_non_empty],
        vol.Optional("expected_options", default=[]): [_str_non_empty],
        vol.Optional("expected_commands", default=[]): [_str_non_empty],
    }
)


def selection_mechanism_from_dict(d: dict[str, Any]) -> SelectionMechanism:
    """Validate and construct a SelectionMechanism from a dict."""
    v = SELECTION_MECHANISM_SCHEMA(d)
    return SelectionMechanism(
        kind=MechanismKind(v["kind"]),
        expected_domain=v.get("expected_domain"),
        expected_features=tuple(v.get("expected_features", [])),
        expected_options=tuple(v.get("expected_options", [])),
        expected_commands=tuple(v.get("expected_commands", [])),
    )


def selection_mechanism_to_dict(m: SelectionMechanism) -> dict[str, Any]:
    """Serialize a SelectionMechanism to a dict."""
    return {
        "kind": m.kind.value,
        "expected_domain": m.expected_domain,
        "expected_features": list(m.expected_features),
        "expected_options": list(m.expected_options),
        "expected_commands": list(m.expected_commands),
    }


# ---------------------------------------------------------------------------
# OutputGroup
# ---------------------------------------------------------------------------

OUTPUT_GROUP_SCHEMA = vol.Schema(
    {
        vol.Required("id"): _str_non_empty,
        vol.Optional("provides_roles", default=[]): [_enum_in(ControlRole)],
        vol.Optional("selection_mechanism"): vol.Any(None, dict),
    }
)


def output_group_from_dict(d: dict[str, Any]) -> OutputGroup:
    """Validate and construct an OutputGroup from a dict."""
    v = OUTPUT_GROUP_SCHEMA(d)
    mech_dict = v.get("selection_mechanism")
    return OutputGroup(
        id=v["id"],
        provides_roles=tuple(ControlRole(r) for r in v.get("provides_roles", [])),
        selection_mechanism=(selection_mechanism_from_dict(mech_dict) if mech_dict else None),
    )


def output_group_to_dict(og: OutputGroup) -> dict[str, Any]:
    """Serialize an OutputGroup to a dict."""
    return {
        "id": og.id,
        "provides_roles": [r.value for r in og.provides_roles],
        "selection_mechanism": (
            selection_mechanism_to_dict(og.selection_mechanism) if og.selection_mechanism else None
        ),
    }


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

CONNECTION_SCHEMA = vol.Schema(
    {
        vol.Required("id"): _str_non_empty,
        vol.Required("from_device_id"): _str_non_empty,
        vol.Required("from_interface_id"): _str_non_empty,
        vol.Required("to_device_id"): _str_non_empty,
        vol.Required("to_interface_id"): _str_non_empty,
    }
)


def connection_from_dict(d: dict[str, Any]) -> Connection:
    """Validate and construct a Connection from a dict."""
    v = CONNECTION_SCHEMA(d)
    return Connection(
        id=v["id"],
        from_device_id=v["from_device_id"],
        from_interface_id=v["from_interface_id"],
        to_device_id=v["to_device_id"],
        to_interface_id=v["to_interface_id"],
    )


def connection_to_dict(c: Connection) -> dict[str, Any]:
    """Serialize a Connection to a dict."""
    return {
        "id": c.id,
        "from_device_id": c.from_device_id,
        "from_interface_id": c.from_interface_id,
        "to_device_id": c.to_device_id,
        "to_interface_id": c.to_interface_id,
    }


# ---------------------------------------------------------------------------
# VirtualSource / DynamicVirtualSources / AuxEntity
# ---------------------------------------------------------------------------

VIRTUAL_SOURCE_SCHEMA = vol.Schema(
    {
        vol.Required("id"): _str_non_empty,
        vol.Required("label"): _str_non_empty,
        vol.Optional("routable_to_output_group", default=[]): [_str_non_empty],
    }
)

DYNAMIC_VIRTUAL_SOURCES_SCHEMA = vol.Schema(
    {
        vol.Required("source"): _str_non_empty,
        vol.Required("output_group"): _str_non_empty,
        vol.Optional("exclude", default=[]): [str],
    }
)

AUX_ENTITY_SCHEMA = vol.Schema(
    {
        vol.Required("id"): _str_non_empty,
        vol.Required("expected_domain"): _str_non_empty,
        vol.Optional("expected_features", default=[]): [_str_non_empty],
        vol.Optional("expected_commands", default=[]): [_str_non_empty],
        vol.Optional("expected_options", default=[]): [_str_non_empty],
    }
)


def virtual_source_from_dict(d: dict[str, Any]) -> VirtualSource:
    """Validate and construct a VirtualSource from a dict."""
    v = VIRTUAL_SOURCE_SCHEMA(d)
    return VirtualSource(
        id=v["id"],
        label=v["label"],
        routable_to_output_group=tuple(v.get("routable_to_output_group", [])),
    )


def virtual_source_to_dict(vs: VirtualSource) -> dict[str, Any]:
    """Serialize a VirtualSource to a dict."""
    return {
        "id": vs.id,
        "label": vs.label,
        "routable_to_output_group": list(vs.routable_to_output_group),
    }


def dynamic_virtual_sources_from_dict(d: dict[str, Any]) -> DynamicVirtualSources:
    """Validate and construct DynamicVirtualSources from a dict."""
    v = DYNAMIC_VIRTUAL_SOURCES_SCHEMA(d)
    return DynamicVirtualSources(
        source=v["source"],
        output_group=v["output_group"],
        exclude=tuple(v.get("exclude", [])),
    )


def dynamic_virtual_sources_to_dict(dvs: DynamicVirtualSources) -> dict[str, Any]:
    """Serialize DynamicVirtualSources to a dict."""
    return {
        "source": dvs.source,
        "output_group": dvs.output_group,
        "exclude": list(dvs.exclude),
    }


def aux_entity_from_dict(d: dict[str, Any]) -> AuxEntity:
    """Validate and construct an AuxEntity from a dict."""
    v = AUX_ENTITY_SCHEMA(d)
    return AuxEntity(
        id=v["id"],
        expected_domain=v["expected_domain"],
        expected_features=tuple(v.get("expected_features", [])),
        expected_commands=tuple(v.get("expected_commands", [])),
        expected_options=tuple(v.get("expected_options", [])),
    )


def aux_entity_to_dict(ae: AuxEntity) -> dict[str, Any]:
    """Serialize an AuxEntity to a dict."""
    return {
        "id": ae.id,
        "expected_domain": ae.expected_domain,
        "expected_features": list(ae.expected_features),
        "expected_commands": list(ae.expected_commands),
        "expected_options": list(ae.expected_options),
    }


# ---------------------------------------------------------------------------
# Device
# ---------------------------------------------------------------------------

DEVICE_SCHEMA = vol.Schema(
    {
        vol.Required("id"): _str_non_empty,
        vol.Required("name"): _str_non_empty,
        vol.Required("profile_id"): _str_non_empty,
        vol.Optional("power_handling", default=PowerHandling.DISABLED.value): _enum_in(
            PowerHandling
        ),
        vol.Optional("power_on_delay", default=0): vol.All(int, vol.Range(min=0)),
        vol.Optional("exclusive_outputs", default=False): bool,
        vol.Optional("output_groups", default=[]): [dict],
        vol.Optional("interfaces", default=[]): [dict],
        vol.Optional("virtual_sources", default=[]): [dict],
        vol.Optional("dynamic_virtual_sources"): vol.Any(None, dict),
        vol.Optional("aux_entities", default=[]): [dict],
        vol.Optional("inputs_are_exclusive_per_output_group", default=[]): [_str_non_empty],
    }
)


def device_from_dict(d: dict[str, Any]) -> Device:
    """Validate and construct a Device from a dict."""
    v = DEVICE_SCHEMA(d)
    dvs_dict = v.get("dynamic_virtual_sources")
    return Device(
        id=v["id"],
        name=v["name"],
        profile_id=v["profile_id"],
        power_handling=PowerHandling(v["power_handling"]),
        power_on_delay=v["power_on_delay"],
        exclusive_outputs=v["exclusive_outputs"],
        output_groups=tuple(output_group_from_dict(og) for og in v["output_groups"]),
        interfaces=tuple(interface_from_dict(i) for i in v["interfaces"]),
        virtual_sources=tuple(virtual_source_from_dict(vs) for vs in v["virtual_sources"]),
        dynamic_virtual_sources=(dynamic_virtual_sources_from_dict(dvs_dict) if dvs_dict else None),
        aux_entities=tuple(aux_entity_from_dict(ae) for ae in v["aux_entities"]),
        inputs_are_exclusive_per_output_group=tuple(v["inputs_are_exclusive_per_output_group"]),
    )


def device_to_dict(dev: Device) -> dict[str, Any]:
    """Serialize a Device to a dict."""
    return {
        "id": dev.id,
        "name": dev.name,
        "profile_id": dev.profile_id,
        "power_handling": dev.power_handling.value,
        "power_on_delay": dev.power_on_delay,
        "exclusive_outputs": dev.exclusive_outputs,
        "output_groups": [output_group_to_dict(og) for og in dev.output_groups],
        "interfaces": [interface_to_dict(i) for i in dev.interfaces],
        "virtual_sources": [virtual_source_to_dict(vs) for vs in dev.virtual_sources],
        "dynamic_virtual_sources": (
            dynamic_virtual_sources_to_dict(dev.dynamic_virtual_sources)
            if dev.dynamic_virtual_sources
            else None
        ),
        "aux_entities": [aux_entity_to_dict(ae) for ae in dev.aux_entities],
        "inputs_are_exclusive_per_output_group": list(dev.inputs_are_exclusive_per_output_group),
    }


# ---------------------------------------------------------------------------
# Zone / SourceRef / SourceVisibilitySelection / InstanceBinding / DeviceInstance
# ---------------------------------------------------------------------------

SOURCE_REF_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): _str_non_empty,
        vol.Optional("virtual_source_id"): vol.Any(None, _str_non_empty),
        vol.Optional("display_name"): vol.Any(None, _str_non_empty),
    }
)

ZONE_SCHEMA = vol.Schema(
    {
        vol.Required("id"): _str_non_empty,
        vol.Required("name"): _str_non_empty,
        vol.Optional("sink_device_ids", default=[]): [_str_non_empty],
        vol.Optional("sink_mode", default=SinkMode.SINGLE.value): _enum_in(SinkMode),
        vol.Optional("volume_authority_device_id"): vol.Any(None, _str_non_empty),
        vol.Optional("volume_authority_output_group_id"): vol.Any(None, _str_non_empty),
        vol.Optional("contention_policy", default=ContentionPolicy.DENY.value): _enum_in(
            ContentionPolicy
        ),
        vol.Optional("default_sink_device_id"): vol.Any(None, _str_non_empty),
    }
)

INSTANCE_BINDING_SCHEMA = vol.Schema(
    {
        vol.Required("output_group_id"): _str_non_empty,
        vol.Required("entity_registry_id"): _str_non_empty,
        vol.Optional("label_remaps", default=[]): [[str]],
    }
)

DEVICE_INSTANCE_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): _str_non_empty,
        vol.Optional("bindings", default=[]): [dict],
        vol.Optional("power_handling_override"): vol.Any(None, _enum_in(PowerHandling)),
    }
)

SOURCE_VISIBILITY_SCHEMA = vol.Schema(
    {
        vol.Required("zone_id"): _str_non_empty,
        vol.Optional("visible_sources", default=[]): [dict],
    }
)


def source_ref_from_dict(d: dict[str, Any]) -> SourceRef:
    """Validate and construct a SourceRef from a dict."""
    v = SOURCE_REF_SCHEMA(d)
    return SourceRef(
        device_id=v["device_id"],
        virtual_source_id=v.get("virtual_source_id"),
        display_name=v.get("display_name"),
    )


def source_ref_to_dict(ref: SourceRef) -> dict[str, Any]:
    """Serialize a SourceRef to a dict."""
    return {
        "device_id": ref.device_id,
        "virtual_source_id": ref.virtual_source_id,
        "display_name": ref.display_name,
    }


def zone_from_dict(d: dict[str, Any]) -> Zone:
    """Validate and construct a Zone from a dict."""
    v = ZONE_SCHEMA(d)
    return Zone(
        id=v["id"],
        name=v["name"],
        sink_device_ids=tuple(v.get("sink_device_ids", [])),
        sink_mode=SinkMode(v["sink_mode"]),
        volume_authority_device_id=v.get("volume_authority_device_id"),
        volume_authority_output_group_id=v.get("volume_authority_output_group_id"),
        contention_policy=ContentionPolicy(v["contention_policy"]),
        default_sink_device_id=v.get("default_sink_device_id"),
    )


def zone_to_dict(zone: Zone) -> dict[str, Any]:
    """Serialize a Zone to a dict."""
    return {
        "id": zone.id,
        "name": zone.name,
        "sink_device_ids": list(zone.sink_device_ids),
        "sink_mode": zone.sink_mode.value,
        "volume_authority_device_id": zone.volume_authority_device_id,
        "volume_authority_output_group_id": zone.volume_authority_output_group_id,
        "contention_policy": zone.contention_policy.value,
        "default_sink_device_id": zone.default_sink_device_id,
    }


def instance_binding_from_dict(d: dict[str, Any]) -> InstanceBinding:
    """Validate and construct an InstanceBinding from a dict."""
    v = INSTANCE_BINDING_SCHEMA(d)
    return InstanceBinding(
        output_group_id=v["output_group_id"],
        entity_registry_id=v["entity_registry_id"],
        label_remaps=tuple(tuple(pair) for pair in v.get("label_remaps", [])),
    )


def instance_binding_to_dict(b: InstanceBinding) -> dict[str, Any]:
    """Serialize an InstanceBinding to a dict."""
    return {
        "output_group_id": b.output_group_id,
        "entity_registry_id": b.entity_registry_id,
        "label_remaps": [list(pair) for pair in b.label_remaps],
    }


def device_instance_from_dict(d: dict[str, Any]) -> DeviceInstance:
    """Validate and construct a DeviceInstance from a dict."""
    v = DEVICE_INSTANCE_SCHEMA(d)
    ph_override = v.get("power_handling_override")
    return DeviceInstance(
        device_id=v["device_id"],
        bindings=tuple(instance_binding_from_dict(b) for b in v.get("bindings", [])),
        power_handling_override=PowerHandling(ph_override) if ph_override else None,
    )


def device_instance_to_dict(inst: DeviceInstance) -> dict[str, Any]:
    """Serialize a DeviceInstance to a dict."""
    return {
        "device_id": inst.device_id,
        "bindings": [instance_binding_to_dict(b) for b in inst.bindings],
        "power_handling_override": (
            inst.power_handling_override.value if inst.power_handling_override else None
        ),
    }


def source_visibility_from_dict(d: dict[str, Any]) -> SourceVisibilitySelection:
    """Validate and construct a SourceVisibilitySelection from a dict."""
    v = SOURCE_VISIBILITY_SCHEMA(d)
    return SourceVisibilitySelection(
        zone_id=v["zone_id"],
        visible_sources=tuple(source_ref_from_dict(ref) for ref in v.get("visible_sources", [])),
    )


def source_visibility_to_dict(sel: SourceVisibilitySelection) -> dict[str, Any]:
    """Serialize a SourceVisibilitySelection to a dict."""
    return {
        "zone_id": sel.zone_id,
        "visible_sources": [source_ref_to_dict(ref) for ref in sel.visible_sources],
    }
