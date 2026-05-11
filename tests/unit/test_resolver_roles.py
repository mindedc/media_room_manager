"""Tests for resolver.roles: RoleAssignment and resolve_roles()."""

from __future__ import annotations

from custom_components.media_room_manager.graph.model import (
    ContentionPolicy,
    ControlRole,
    Device,
    Interface,
    InterfaceDirection,
    InterfaceType,
    OutputGroup,
    SinkMode,
    Zone,
)
from custom_components.media_room_manager.graph.system_config import SystemConfig
from custom_components.media_room_manager.resolver.path import (
    PathHop,
    PathResolutionError,
    ResolvedSinglePath,
    ZoneResolverResult,
)
from custom_components.media_room_manager.resolver.roles import resolve_roles

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _out(iface_id: str, og: str) -> Interface:
    return Interface(
        id=iface_id,
        direction=InterfaceDirection.OUTPUT,
        type=InterfaceType.HDMI,
        label=iface_id,
        output_group=og,
    )


def _inp(iface_id: str, routable: list[str]) -> Interface:
    return Interface(
        id=iface_id,
        direction=InterfaceDirection.INPUT,
        type=InterfaceType.HDMI,
        label=iface_id,
        routable_to_output_group=tuple(routable),
    )


def _device_with_roles(dev_id: str, og_id: str, roles: list[ControlRole]) -> Device:
    og = OutputGroup(id=og_id, provides_roles=tuple(roles))
    return Device(
        id=dev_id,
        name=dev_id,
        profile_id="test/p",
        output_groups=(og,),
        interfaces=(
            _out("out1", og_id),
            _inp("in1", [og_id]),
        ),
    )


def _zone(
    zone_id: str,
    vol_dev: str | None = None,
    vol_og: str | None = None,
) -> Zone:
    return Zone(
        id=zone_id,
        name=zone_id,
        sink_device_ids=("sink",),
        sink_mode=SinkMode.SINGLE,
        volume_authority_device_id=vol_dev,
        volume_authority_output_group_id=vol_og,
        contention_policy=ContentionPolicy.DENY,
    )


def _resolved_result(
    zone_id: str,
    source_device_id: str,
    source_og_id: str,
    sink_device_id: str,
) -> ZoneResolverResult:
    hops = (
        PathHop(
            device_id=source_device_id,
            entry_interface_id=None,
            exit_interface_id="out1",
            output_group_id=source_og_id,
        ),
        PathHop(
            device_id=sink_device_id,
            entry_interface_id="in1",
            exit_interface_id=None,
            output_group_id=None,
        ),
    )
    path = ResolvedSinglePath(
        carrier="video",
        source_device_id=source_device_id,
        sink_device_id=sink_device_id,
        hops=hops,
    )
    return ZoneResolverResult(
        zone_id=zone_id,
        source_device_id=source_device_id,
        virtual_source_id=None,
        is_virtual_source=False,
        sink_device_ids=(sink_device_id,),
        video_paths=(path,),
        audio_paths=(),
        contentions=(),
        exclusive_output_usage=(),
    )


def _virtual_result(zone_id: str, source_device_id: str) -> ZoneResolverResult:
    return ZoneResolverResult(
        zone_id=zone_id,
        source_device_id=source_device_id,
        virtual_source_id="vs1",
        is_virtual_source=True,
        sink_device_ids=("sink",),
        video_paths=(),
        audio_paths=(),
        contentions=(),
        exclusive_output_usage=(),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_volume_authority_pinned() -> None:
    """volume_device_id / volume_output_group_id come from the zone fields."""
    source = _device_with_roles("source", "main", [ControlRole.TRANSPORT])
    sink = Device(id="sink", name="sink", profile_id="p", output_groups=())
    config = SystemConfig(devices=[source, sink], zones=[])

    zone = _zone("z1", vol_dev="avr", vol_og="main")
    result = _resolved_result("z1", "source", "main", "sink")

    ra = resolve_roles(zone, result, config)
    assert ra.volume_device_id == "avr"
    assert ra.volume_output_group_id == "main"


def test_transport_from_source_output_group() -> None:
    """transport_device_id resolved from source output group that provides TRANSPORT."""
    source = _device_with_roles("source", "main", [ControlRole.TRANSPORT])
    sink = Device(id="sink", name="sink", profile_id="p", output_groups=())
    config = SystemConfig(devices=[source, sink], zones=[])

    zone = _zone("z1")
    result = _resolved_result("z1", "source", "main", "sink")

    ra = resolve_roles(zone, result, config)
    assert ra.transport_device_id == "source"
    assert ra.transport_output_group_id == "main"


def test_metadata_source_from_source_output_group() -> None:
    """metadata_source resolved from source og providing METADATA_SOURCE."""
    source = _device_with_roles(
        "source", "main", [ControlRole.TRANSPORT, ControlRole.METADATA_SOURCE]
    )
    sink = Device(id="sink", name="sink", profile_id="p", output_groups=())
    config = SystemConfig(devices=[source, sink], zones=[])

    zone = _zone("z1")
    result = _resolved_result("z1", "source", "main", "sink")

    ra = resolve_roles(zone, result, config)
    assert ra.metadata_source_device_id == "source"
    assert ra.metadata_source_output_group_id == "main"


def test_transport_not_found_when_no_roles() -> None:
    """transport fields are None when source output group provides no roles."""
    og = OutputGroup(id="main", provides_roles=())
    source = Device(
        id="source",
        name="source",
        profile_id="p",
        output_groups=(og,),
        interfaces=(_out("out1", "main"), _inp("in1", ["main"])),
    )
    sink = Device(id="sink", name="sink", profile_id="p", output_groups=())
    config = SystemConfig(devices=[source, sink], zones=[])

    zone = _zone("z1")
    result = _resolved_result("z1", "source", "main", "sink")

    ra = resolve_roles(zone, result, config)
    assert ra.transport_device_id is None
    assert ra.transport_output_group_id is None


def test_missing_volume_authority_returns_none() -> None:
    """When zone has no volume authority, both volume fields are None."""
    source = _device_with_roles("source", "main", [ControlRole.TRANSPORT])
    sink = Device(id="sink", name="sink", profile_id="p", output_groups=())
    config = SystemConfig(devices=[source, sink], zones=[])

    zone = _zone("z1", vol_dev=None, vol_og=None)
    result = _resolved_result("z1", "source", "main", "sink")

    ra = resolve_roles(zone, result, config)
    assert ra.volume_device_id is None
    assert ra.volume_output_group_id is None


def test_virtual_source_transport_still_resolved() -> None:
    """For virtual sources (no path hops), transport is still resolved from source device."""
    source = _device_with_roles("source", "main", [ControlRole.TRANSPORT])
    config = SystemConfig(devices=[source], zones=[])

    zone = _zone("z1")
    result = _virtual_result("z1", "source")

    ra = resolve_roles(zone, result, config)
    # No path hops → source_og_id is None → falls back to scanning all ogs.
    assert ra.transport_device_id == "source"
    assert ra.transport_output_group_id == "main"


def test_virtual_source_no_transport_role() -> None:
    """Virtual source on device with no transport role → transport fields are None."""
    og = OutputGroup(id="main", provides_roles=(ControlRole.VOLUME,))
    source = Device(
        id="source",
        name="source",
        profile_id="p",
        output_groups=(og,),
        interfaces=(),
    )
    config = SystemConfig(devices=[source], zones=[])

    zone = _zone("z1")
    result = _virtual_result("z1", "source")

    ra = resolve_roles(zone, result, config)
    assert ra.transport_device_id is None


def test_error_path_ignored_for_role_resolution() -> None:
    """PathResolutionError entries in paths are ignored; resolver uses resolved paths only."""
    source = _device_with_roles("source", "main", [ControlRole.TRANSPORT])
    sink = Device(id="sink", name="sink", profile_id="p", output_groups=())
    config = SystemConfig(devices=[source, sink], zones=[])

    error = PathResolutionError(
        carrier="audio",
        source_device_id="source",
        sink_device_id="sink",
        reason="no path",
    )
    video_hop = (
        PathHop("source", None, "out1", "main"),
        PathHop("sink", "in1", None, None),
    )
    video_path = ResolvedSinglePath("video", "source", "sink", video_hop)

    result = ZoneResolverResult(
        zone_id="z1",
        source_device_id="source",
        virtual_source_id=None,
        is_virtual_source=False,
        sink_device_ids=("sink",),
        video_paths=(video_path,),
        audio_paths=(error,),
        contentions=(),
        exclusive_output_usage=(),
    )

    zone = _zone("z1")
    ra = resolve_roles(zone, result, config)
    assert ra.transport_device_id == "source"
