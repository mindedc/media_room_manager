"""Core graph model dataclasses for Media Room Manager.

The graph model is pure data. It has no Home Assistant dependencies and no I/O.
All objects are immutable frozen dataclasses validated by voluptuous schemas
defined in graph/schema.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class InterfaceType(StrEnum):
    """Physical port type on a device. Implies which signal carriers it supports."""

    HDMI = "hdmi"
    HDMI_AUDIO_RETURN = "hdmi_audio_return"
    OPTICAL_AUDIO = "optical_audio"
    COAX_AUDIO = "coax_audio"
    RCA_AUDIO = "rca_audio"
    XLR_AUDIO = "xlr_audio"
    COMPONENT_VIDEO = "component_video"
    COMPOSITE_VIDEO = "composite_video"


# Which carriers each interface type supports.
AUDIO_TYPES: frozenset[InterfaceType] = frozenset(
    {
        InterfaceType.HDMI,
        InterfaceType.HDMI_AUDIO_RETURN,
        InterfaceType.OPTICAL_AUDIO,
        InterfaceType.COAX_AUDIO,
        InterfaceType.RCA_AUDIO,
        InterfaceType.XLR_AUDIO,
    }
)

VIDEO_TYPES: frozenset[InterfaceType] = frozenset(
    {
        InterfaceType.HDMI,
        InterfaceType.HDMI_AUDIO_RETURN,
        InterfaceType.COMPONENT_VIDEO,
        InterfaceType.COMPOSITE_VIDEO,
    }
)


class InterfaceDirection(StrEnum):
    """Whether a port receives or sends signal."""

    INPUT = "input"
    OUTPUT = "output"


@dataclass(frozen=True)
class Interface:
    """A typed physical port on a device.

    Outputs declare their output_group. Inputs declare which output groups they
    can route signal to via routable_to_output_group.
    """

    id: str
    direction: InterfaceDirection
    type: InterfaceType
    label: str
    output_group: str | None = None
    routable_to_output_group: tuple[str, ...] = field(default_factory=tuple)

    def carries_audio(self) -> bool:
        """Return True if this interface type supports audio signals."""
        return self.type in AUDIO_TYPES

    def carries_video(self) -> bool:
        """Return True if this interface type supports video signals."""
        return self.type in VIDEO_TYPES


class PowerHandling(StrEnum):
    """How the integration manages a device's power state."""

    DISCRETE_CAPABLE = "discrete_capable"
    TOGGLE = "toggle"
    ALWAYS_ON = "always_on"
    DISABLED = "disabled"


class ControlRole(StrEnum):
    """A capability a device can fulfill in an active signal path."""

    TRANSPORT = "transport"
    VOLUME = "volume"
    METADATA_SOURCE = "metadata_source"
    POWER = "power"
    SOURCE_SELECTION = "source_selection"


class MechanismKind(StrEnum):
    """The five supported adapter mechanisms."""

    MEDIA_PLAYER_SOURCE = "media_player_source"
    SELECT_ENTITY = "select_entity"
    SWITCH_COMBO = "switch_combo"
    REMOTE_COMMAND = "remote_command"
    SERVICE_CALL = "service_call"


@dataclass(frozen=True)
class SelectionMechanism:
    """How an output group's active input is switched.

    Only the fields relevant to the mechanism kind are populated.
    """

    kind: MechanismKind
    expected_domain: str | None = None
    expected_features: tuple[str, ...] = field(default_factory=tuple)
    expected_options: tuple[str, ...] = field(default_factory=tuple)
    expected_commands: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class OutputGroup:
    """A device-internal grouping of outputs sharing one active input selection.

    Each output group may have its own bound HA entity and control mechanism.
    """

    id: str
    provides_roles: tuple[ControlRole, ...] = field(default_factory=tuple)
    selection_mechanism: SelectionMechanism | None = None


@dataclass(frozen=True)
class Connection:
    """A directed cable from one device's output interface to another's input.

    Connections are type-checked at the graph level; the path resolver uses
    them to walk signal routes.
    """

    id: str
    from_device_id: str
    from_interface_id: str
    to_device_id: str
    to_interface_id: str


@dataclass(frozen=True)
class VirtualSource:
    """A content source intrinsic to a device with no physical input port.

    Examples: AVR tuner, CD transport, DVR cable input.
    """

    id: str
    label: str
    routable_to_output_group: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DynamicVirtualSources:
    """Configuration for sources discovered at runtime from a bound entity's source_list."""

    source: str  # currently always "source_list_minus_known"
    output_group: str
    exclude: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class AuxEntity:
    """An auxiliary HA entity bound to a device but not tied to an output group.

    Examples: a standalone power switch on a matrix, an IR blaster entity.
    """

    id: str
    expected_domain: str
    expected_features: tuple[str, ...] = field(default_factory=tuple)
    expected_commands: tuple[str, ...] = field(default_factory=tuple)
    expected_options: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Device:
    """A physical unit of AV equipment in the user's system.

    Devices are instances of profiles. The graph holds device instances;
    the profile registry holds the reusable profile templates.
    """

    id: str
    name: str
    profile_id: str
    power_handling: PowerHandling = PowerHandling.DISABLED
    power_on_delay: int = 0
    exclusive_outputs: bool = False
    output_groups: tuple[OutputGroup, ...] = field(default_factory=tuple)
    interfaces: tuple[Interface, ...] = field(default_factory=tuple)
    virtual_sources: tuple[VirtualSource, ...] = field(default_factory=tuple)
    dynamic_virtual_sources: DynamicVirtualSources | None = None
    aux_entities: tuple[AuxEntity, ...] = field(default_factory=tuple)
    inputs_are_exclusive_per_output_group: tuple[str, ...] = field(default_factory=tuple)


class SinkMode(StrEnum):
    """How multiple sinks in a zone behave."""

    SINGLE = "single"
    SIMULTANEOUS = "simultaneous"
    SELECTABLE_EXCLUSIVE = "selectable_exclusive"


class ContentionPolicy(StrEnum):
    """How a zone responds when activating would conflict with another active path.

    The `share` policy is v1.x and must not be implemented in v1.0.
    """

    DENY = "deny"
    PREEMPT = "preempt"


@dataclass(frozen=True)
class SourceRef:
    """A reference to a source (physical device or virtual source) from a zone's perspective.

    device_id is always set. virtual_source_id is set only for virtual sources.
    """

    device_id: str
    virtual_source_id: str | None = None
    display_name: str | None = None  # user-provided display name override


@dataclass(frozen=True)
class InstanceBinding:
    """Runtime binding of a profile output group or aux entity to a HA entity.

    Stores the entity registry UUID (not the entity_id string) so renames
    don't break the binding.
    """

    output_group_id: str
    entity_registry_id: str
    label_remaps: tuple[tuple[str, str], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DeviceInstance:
    """A profile instantiated in the user's system, with entity bindings and remaps."""

    device_id: str
    bindings: tuple[InstanceBinding, ...] = field(default_factory=tuple)
    power_handling_override: PowerHandling | None = None


@dataclass(frozen=True)
class SourceVisibilitySelection:
    """The sources a zone exposes in its media_player source_list.

    Sources not in this list are hidden from the zone's entity.
    """

    zone_id: str
    visible_sources: tuple[SourceRef, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Zone:
    """A user-facing viewing or listening area.

    Each zone surfaces as a virtual media_player entity in HA. Zones reference
    devices by ID; the graph holds the device objects.
    """

    id: str
    name: str
    sink_device_ids: tuple[str, ...] = field(default_factory=tuple)
    sink_mode: SinkMode = SinkMode.SINGLE
    volume_authority_device_id: str | None = None
    volume_authority_output_group_id: str | None = None
    contention_policy: ContentionPolicy = ContentionPolicy.DENY
    default_sink_device_id: str | None = None
