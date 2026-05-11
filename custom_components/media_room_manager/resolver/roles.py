"""Role assignment: maps ControlRole to device/output_group for an active path.

Given a resolved ZoneResolverResult and the SystemConfig, identifies which
device and output group holds each control role for the zone:

- volume: pinned from zone.volume_authority_device_id / output_group_id.
- transport: from the source device's output group that provides
  ControlRole.TRANSPORT.
- metadata_source: from the source device's output group that provides
  ControlRole.METADATA_SOURCE.

For physical sources the "source output group" is identified from the first
hop's output_group_id in a resolved path.  For virtual sources (no path hops)
we inspect all output groups on the source device directly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ..graph.model import ControlRole, Zone
from ..graph.system_config import SystemConfig
from .path import ResolvedSinglePath, ZoneResolverResult

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class RoleAssignment:
    """The device / output-group assignments for each control role in a zone.

    Any field may be None if the role holder cannot be determined (e.g. no
    volume authority is pinned, or the source device has no output group that
    provides the transport role).
    """

    volume_device_id: str | None
    volume_output_group_id: str | None
    transport_device_id: str | None
    transport_output_group_id: str | None
    metadata_source_device_id: str | None
    metadata_source_output_group_id: str | None


def _find_role_in_device(
    config: SystemConfig,
    device_id: str,
    role: ControlRole,
    preferred_og_id: str | None = None,
) -> str | None:
    """Return the output_group_id on device_id that provides *role*, or None.

    If preferred_og_id is provided, check that group first; fall back to
    scanning all output groups on the device.
    """
    device = next((d for d in config.devices if d.id == device_id), None)
    if device is None:
        return None

    # Try the preferred output group first.
    if preferred_og_id is not None:
        for og in device.output_groups:
            if og.id == preferred_og_id and role in og.provides_roles:
                return og.id

    # Fall back to scanning all output groups.
    for og in device.output_groups:
        if role in og.provides_roles:
            return og.id

    return None


def _source_output_group_id(result: ZoneResolverResult) -> str | None:
    """Identify the output group id on the source device from the resolved paths.

    For physical sources this is the exit output group from the first hop of
    any resolved path (the source hop has no entry interface).
    Returns None for virtual sources or when no paths were resolved.
    """
    all_paths = list(result.video_paths) + list(result.audio_paths)
    for path in all_paths:
        if not isinstance(path, ResolvedSinglePath):
            continue
        if not path.hops:
            continue
        first_hop = path.hops[0]
        if first_hop.device_id == result.source_device_id:
            return first_hop.output_group_id
    return None


def resolve_roles(
    zone: Zone,
    result: ZoneResolverResult,
    config: SystemConfig,
) -> RoleAssignment:
    """Compute the RoleAssignment for an active zone path.

    Parameters
    ----------
    zone:
        The Zone being activated (for volume authority pinning).
    result:
        The ZoneResolverResult from the path resolver.
    config:
        The full SystemConfig (for device/output-group lookup).

    Returns
    -------
    RoleAssignment with all discoverable roles filled in.
    """
    # ------------------------------------------------------------------
    # Volume: always from the zone's pinned authority fields.
    # ------------------------------------------------------------------
    volume_device_id = zone.volume_authority_device_id
    volume_og_id = zone.volume_authority_output_group_id

    # ------------------------------------------------------------------
    # Transport / metadata_source: from the source device's output group.
    # ------------------------------------------------------------------
    source_og_id = _source_output_group_id(result)

    transport_device_id: str | None = None
    transport_og_id: str | None = None
    metadata_device_id: str | None = None
    metadata_og_id: str | None = None

    source_device_id = result.source_device_id

    transport_og = _find_role_in_device(
        config, source_device_id, ControlRole.TRANSPORT, preferred_og_id=source_og_id
    )
    if transport_og is not None:
        transport_device_id = source_device_id
        transport_og_id = transport_og

    metadata_og = _find_role_in_device(
        config, source_device_id, ControlRole.METADATA_SOURCE, preferred_og_id=source_og_id
    )
    if metadata_og is not None:
        metadata_device_id = source_device_id
        metadata_og_id = metadata_og

    return RoleAssignment(
        volume_device_id=volume_device_id,
        volume_output_group_id=volume_og_id,
        transport_device_id=transport_device_id,
        transport_output_group_id=transport_og_id,
        metadata_source_device_id=metadata_device_id,
        metadata_source_output_group_id=metadata_og_id,
    )
