"""Typed dataclasses for device profiles.

Profiles are read-only library data — they describe what a device model is and
how it should be controlled. They are never mutated at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from ..graph.model import InterfaceDirection, InterfaceType, PowerHandling


class ProfileCategory(StrEnum):
    """Top-level category for a device profile."""

    SOURCE = "source"
    AVR = "avr"
    MATRIX = "matrix"
    VIDEO_PROCESSOR = "video_processor"
    PASSIVE_CONVERTER = "passive_converter"
    DISPLAY = "display"
    OTHER = "other"


@dataclass(frozen=True)
class ProfileSelectionMechanism:
    """How an output group switches its active input.

    Mirrors the graph model's SelectionMechanism but lives in the profile layer.
    """

    kind: str
    expected_domain: str | None = None
    expected_features: tuple[str, ...] = field(default_factory=tuple)
    expected_options: tuple[str, ...] = field(default_factory=tuple)
    expected_commands: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RoleOperation:
    """A single named operation for a role (e.g. power_on, play, pause)."""

    command: str
    delay: float = 0.0


@dataclass(frozen=True)
class RoleOperationSet:
    """All operations for one control role declared in a non-media_player output group."""

    kind: str
    operations: dict[str, RoleOperation] = field(default_factory=dict)


@dataclass(frozen=True)
class ProfileOutputGroup:
    """An output group declaration inside a profile."""

    id: str
    provides_roles: tuple[str, ...] = field(default_factory=tuple)
    selection_mechanism: ProfileSelectionMechanism | None = None
    role_operations: dict[str, RoleOperationSet] = field(default_factory=dict)


@dataclass(frozen=True)
class ProfileInterface:
    """An interface declaration inside a profile."""

    id: str
    direction: InterfaceDirection
    type: InterfaceType
    label: str
    output_group: str | None = None
    routable_to_output_group: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ProfileVirtualSource:
    """A static virtual source declared in a profile."""

    id: str
    label: str
    routable_to_output_group: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ProfileDynamicVirtualSources:
    """Config for dynamic virtual source discovery on a profile's output group."""

    source: str
    output_group: str
    exclude: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ProfileAuxEntity:
    """An auxiliary entity declared in a profile (not tied to an output group)."""

    id: str
    expected_domain: str
    expected_features: tuple[str, ...] = field(default_factory=tuple)
    expected_commands: tuple[str, ...] = field(default_factory=tuple)
    expected_options: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DiscoverySignal:
    """A single signal used during device auto-discovery."""

    kind: str
    weight: int
    manufacturer: str | None = None
    model_patterns: tuple[str, ...] = field(default_factory=tuple)
    domain: str | None = None
    values: tuple[int, ...] = field(default_factory=tuple)
    includes_any: tuple[str, ...] = field(default_factory=tuple)
    includes: tuple[str, ...] = field(default_factory=tuple)
    matches: tuple[str, ...] = field(default_factory=tuple)
    friendly_name_patterns: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DiscoveryOutputGroupEntry:
    """Discovery signals for one output group in a profile's discovery block."""

    output_group: str
    signals: tuple[DiscoverySignal, ...] = field(default_factory=tuple)
    is_discovery_anchor: bool = False
    match_threshold: int = 60
    optional: bool = False


@dataclass(frozen=True)
class ProfileDiscovery:
    """The discovery block for a profile."""

    output_groups: tuple[DiscoveryOutputGroupEntry, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Profile:
    """A complete device profile describing how a device model should be controlled.

    Profiles are immutable, versioned, and indexed by profile_id. Users instantiate
    profiles into Device instances in their system graph.
    """

    profile_id: str
    schema_version: int
    manufacturer: str
    model: str
    category: ProfileCategory
    power_handling: PowerHandling = PowerHandling.DISABLED
    power_on_delay: int = 0
    exclusive_outputs: bool = False
    output_groups: tuple[ProfileOutputGroup, ...] = field(default_factory=tuple)
    interfaces: tuple[ProfileInterface, ...] = field(default_factory=tuple)
    virtual_sources: tuple[ProfileVirtualSource, ...] = field(default_factory=tuple)
    dynamic_virtual_sources: ProfileDynamicVirtualSources | None = None
    aux_entities: tuple[ProfileAuxEntity, ...] = field(default_factory=tuple)
    inputs_are_exclusive_per_output_group: tuple[str, ...] = field(default_factory=tuple)
    discovery: ProfileDiscovery | None = None
