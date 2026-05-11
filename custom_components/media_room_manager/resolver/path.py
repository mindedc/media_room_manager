"""Path resolver: BFS-based signal-path computation over the connection graph.

Given (source_device, zone) and the current SystemConfig, PathResolver walks
audio and video subgraphs independently to produce an ordered list of
(device, input_interface, output_interface, output_group) hops for the
orchestrator to execute.

Design notes:
- Transit devices are transparent: any input can reach any output of compatible
  carrier within the same output group (subject to routable_to_output_group).
- hdmi_audio_return interfaces carry audio in both directions. The reverse
  direction (INPUT acting as audio source, OUTPUT acting as audio sink) is
  handled by special-casing in the BFS expansion.
- Contention is detected against the ActivePathsRegistry (in-memory state).
- For exclusive_outputs devices, the output interface in use is recorded but
  the resolver does not refuse to compute paths through them.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass

from ..graph.model import InterfaceDirection, InterfaceType, SinkMode
from ..graph.system_config import SystemConfig
from .graph_view import GraphView

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PathHop:
    """One device's role in a resolved signal path.

    entry_interface_id: interface where signal arrives (None for the source hop).
        For ARC reverse paths the "entry" at the sink may be an OUTPUT-type
        interface — the physical port that carries audio in both directions.
    exit_interface_id: interface where signal leaves (None for the sink hop).
        For ARC source hops the "exit" at the source may be an INPUT-type
        interface (hdmi_audio_return carrying audio in reverse).
    output_group_id: the output group whose selection mechanism the orchestrator
        should invoke. None means no selection is required (source devices,
        passive devices with no mechanism, or ARC where routing is implicit).
    """

    device_id: str
    entry_interface_id: str | None
    exit_interface_id: str | None
    output_group_id: str | None


@dataclass(frozen=True)
class ResolvedSinglePath:
    """A resolved audio or video path from one source to one sink."""

    carrier: str  # "audio" or "video"
    source_device_id: str
    sink_device_id: str
    hops: tuple[PathHop, ...]


@dataclass(frozen=True)
class PathResolutionError:
    """Returned when no path can be found between source and sink."""

    carrier: str
    source_device_id: str
    sink_device_id: str
    reason: str


@dataclass(frozen=True)
class ContentionReport:
    """A contention detected between the requested path and an active zone."""

    device_id: str
    kind: str  # "input_side" or "output_side"
    output_group_id: str | None
    conflicting_zone_id: str
    conflicting_input_interface_id: str | None = None
    conflicting_output_interface_id: str | None = None


@dataclass(frozen=True)
class ZoneResolverResult:
    """Complete resolver output for a zone activation request."""

    zone_id: str
    source_device_id: str
    virtual_source_id: str | None
    is_virtual_source: bool
    sink_device_ids: tuple[str, ...]
    # One entry per sink_device_id (parallel ordering)
    video_paths: tuple[ResolvedSinglePath | PathResolutionError, ...]
    audio_paths: tuple[ResolvedSinglePath | PathResolutionError, ...]
    contentions: tuple[ContentionReport, ...]
    # (device_id, interface_id) pairs for exclusive_outputs devices in the path
    exclusive_output_usage: tuple[tuple[str, str], ...]


# ---------------------------------------------------------------------------
# Active paths registry
# ---------------------------------------------------------------------------


class ActivePathsRegistry:
    """In-memory registry of currently-active zone resolver results.

    The orchestrator updates this when zones are activated or deactivated.
    The resolver consults it for contention detection.
    """

    def __init__(self) -> None:
        self._active: dict[str, ZoneResolverResult] = {}

    def update(self, result: ZoneResolverResult) -> None:
        """Record or replace the active path for a zone."""
        self._active[result.zone_id] = result

    def remove(self, zone_id: str) -> None:
        """Remove the active path for a zone (on deactivation)."""
        self._active.pop(zone_id, None)

    def get(self, zone_id: str) -> ZoneResolverResult | None:
        """Return the active result for a zone, or None."""
        return self._active.get(zone_id)

    def all_active(self) -> dict[str, ZoneResolverResult]:
        """Return all active zone results."""
        return dict(self._active)


# ---------------------------------------------------------------------------
# BFS internals
# ---------------------------------------------------------------------------

# Nodes are (device_id, interface_id) tuples.
_Node = tuple[str, str]


def _bfs(
    view: GraphView,
    source_device_id: str,
    sink_device_id: str,
    carrier: str,
) -> list[_Node] | None:
    """BFS from source to sink for the given carrier.

    Returns an ordered list of (device_id, interface_id) nodes representing
    the path, or None if no path exists.

    Each consecutive pair of nodes on the same device represents a transit hop
    (entry interface → exit interface). A connection hop crosses devices.
    """
    # Starting nodes: interfaces from which signal originates at the source.
    if carrier == "video":
        starts = view.source_video_interfaces(source_device_id)
    else:
        starts = view.source_audio_interfaces(source_device_id)

    # Sink nodes: interfaces where signal can terminate at the sink.
    if carrier == "video":
        sink_set: set[_Node] = {
            (sink_device_id, iface.id) for iface in view.sink_video_interfaces(sink_device_id)
        }
    else:
        sink_set = {
            (sink_device_id, iface.id) for iface in view.sink_audio_interfaces(sink_device_id)
        }

    if not starts or not sink_set:
        return None

    parent: dict[_Node, _Node | None] = {}
    for start_iface in starts:
        node: _Node = (source_device_id, start_iface.id)
        parent[node] = None

    queue: deque[_Node] = deque(parent.keys())

    while queue:
        node = queue.popleft()
        device_id, iface_id = node

        if node in sink_set:
            return _reconstruct(parent, node)

        iface = view.get_interface(device_id, iface_id)
        if iface is None:
            continue

        if iface.direction == InterfaceDirection.OUTPUT:
            # Follow the cable to the next device's input.
            conn = view.connection_from_output(device_id, iface_id)
            if conn:
                nxt: _Node = (conn.to_device_id, conn.to_interface_id)
                if nxt not in parent:
                    parent[nxt] = node
                    queue.append(nxt)

        else:  # INPUT
            # Transit transparency: expand to output interfaces in same device.
            for out_iface in view.output_interfaces_reachable_from_input(
                device_id, iface_id, carrier
            ):
                nxt = (device_id, out_iface.id)
                if nxt not in parent:
                    parent[nxt] = node
                    queue.append(nxt)

            # ARC reverse (audio only): an hdmi_audio_return INPUT can send
            # audio backward through the cable to the connected OUTPUT.
            if carrier == "audio" and iface.type == InterfaceType.HDMI_AUDIO_RETURN:
                for conn in view.connections_to_input(device_id, iface_id):
                    from_iface = view.get_interface(conn.from_device_id, conn.from_interface_id)
                    if (
                        from_iface is not None
                        and from_iface.type == InterfaceType.HDMI_AUDIO_RETURN
                    ):
                        nxt = (conn.from_device_id, conn.from_interface_id)
                        if nxt not in parent:
                            parent[nxt] = node
                            queue.append(nxt)

    return None


def _reconstruct(parent: dict[_Node, _Node | None], target: _Node) -> list[_Node]:
    """Walk parent pointers from target back to a start node."""
    path: list[_Node] = []
    cur: _Node | None = target
    while cur is not None:
        path.append(cur)
        cur = parent[cur]
    path.reverse()
    return path


def _nodes_to_hops(view: GraphView, nodes: list[_Node]) -> tuple[PathHop, ...]:
    """Convert a BFS node path to a tuple of PathHop objects.

    The node list alternates between same-device transit pairs and
    cross-device connection steps:
      (src, out) → (transit, in) → (transit, out) → (sink, in)

    Consecutive nodes on the same device are collapsed into a single hop.
    """
    if not nodes:
        return ()

    hops: list[PathHop] = []
    i = 0
    n = len(nodes)

    while i < n:
        dev, iface_id = nodes[i]

        if i == 0:
            # Source hop: signal exits this device.
            out_group = _exit_group(view, dev, iface_id)
            hops.append(PathHop(dev, None, iface_id, out_group))
            i += 1
            continue

        if i == n - 1:
            # Sink hop: signal enters this device and stops.
            in_group = _entry_group(view, dev, iface_id)
            hops.append(PathHop(dev, iface_id, None, in_group))
            i += 1
            continue

        # Check if the NEXT node is on the same device (transit pair).
        next_dev, next_iface_id = nodes[i + 1]
        if next_dev == dev:
            # Transit: (dev, entry) → (dev, exit)
            out_group = _exit_group(view, dev, next_iface_id)
            hops.append(PathHop(dev, iface_id, next_iface_id, out_group))
            i += 2
        else:
            # Unexpected single-node stop mid-path; treat as sink.
            in_group = _entry_group(view, dev, iface_id)
            hops.append(PathHop(dev, iface_id, None, in_group))
            i += 1

    return tuple(hops)


def _exit_group(view: GraphView, device_id: str, interface_id: str) -> str | None:
    """Output group for an exit interface.

    For a normal OUTPUT interface this is iface.output_group.
    For an hdmi_audio_return INPUT acting as an ARC audio source there is no
    output group to select — returns None.
    """
    iface = view.get_interface(device_id, interface_id)
    if iface is None:
        return None
    return iface.output_group  # None for INPUT interfaces


def _entry_group(view: GraphView, device_id: str, interface_id: str) -> str | None:
    """Output group for an entry interface.

    For a normal INPUT interface this is the first entry in
    routable_to_output_group (there is typically exactly one).
    For an hdmi_audio_return OUTPUT acting as an ARC audio sink, use its
    own output_group (the group whose mechanism routes audio via ARC).
    """
    iface = view.get_interface(device_id, interface_id)
    if iface is None:
        return None
    if iface.direction == InterfaceDirection.INPUT:
        return iface.routable_to_output_group[0] if iface.routable_to_output_group else None
    # hdmi_audio_return OUTPUT acting as ARC sink
    return iface.output_group


# ---------------------------------------------------------------------------
# Exclusive-output usage extraction
# ---------------------------------------------------------------------------


def _exclusive_output_usage(
    view: GraphView,
    paths: list[ResolvedSinglePath],
) -> tuple[tuple[str, str], ...]:
    """Collect (device_id, exit_interface_id) for exclusive_outputs devices in paths."""
    seen: set[tuple[str, str]] = set()
    result: list[tuple[str, str]] = []
    for path in paths:
        for hop in path.hops:
            if hop.exit_interface_id is None:
                continue
            device = view.get_device(hop.device_id)
            if device is not None and device.exclusive_outputs:
                key = (hop.device_id, hop.exit_interface_id)
                if key not in seen:
                    seen.add(key)
                    result.append(key)
    return tuple(result)


# ---------------------------------------------------------------------------
# Contention detection
# ---------------------------------------------------------------------------


def _detect_contentions(
    view: GraphView,
    new_paths: list[ResolvedSinglePath],
    requesting_zone_id: str,
    active_registry: ActivePathsRegistry,
) -> tuple[ContentionReport, ...]:
    """Detect input-side and output-side contentions against active zones."""
    reports: list[ContentionReport] = []

    for zone_id, active_result in active_registry.all_active().items():
        if zone_id == requesting_zone_id:
            continue

        active_paths: list[ResolvedSinglePath] = [
            p
            for p in list(active_result.video_paths) + list(active_result.audio_paths)
            if isinstance(p, ResolvedSinglePath)
        ]

        for new_path in new_paths:
            for new_hop in new_path.hops:
                if new_hop.output_group_id is None:
                    continue
                device = view.get_device(new_hop.device_id)
                if device is None:
                    continue

                for active_path in active_paths:
                    for active_hop in active_path.hops:
                        if active_hop.device_id != new_hop.device_id:
                            continue

                        # Input-side: same device+output_group, different entry interface.
                        if (
                            new_hop.output_group_id == active_hop.output_group_id
                            and new_hop.entry_interface_id is not None
                            and active_hop.entry_interface_id is not None
                            and new_hop.entry_interface_id != active_hop.entry_interface_id
                            and new_hop.output_group_id
                            in device.inputs_are_exclusive_per_output_group
                        ):
                            reports.append(
                                ContentionReport(
                                    device_id=new_hop.device_id,
                                    kind="input_side",
                                    output_group_id=new_hop.output_group_id,
                                    conflicting_zone_id=zone_id,
                                    conflicting_input_interface_id=active_hop.entry_interface_id,
                                )
                            )

                        # Output-side: exclusive_outputs device, different exit interface.
                        if (
                            device.exclusive_outputs
                            and new_hop.exit_interface_id is not None
                            and active_hop.exit_interface_id is not None
                            and new_hop.exit_interface_id != active_hop.exit_interface_id
                        ):
                            reports.append(
                                ContentionReport(
                                    device_id=new_hop.device_id,
                                    kind="output_side",
                                    output_group_id=new_hop.output_group_id,
                                    conflicting_zone_id=zone_id,
                                    conflicting_output_interface_id=active_hop.exit_interface_id,
                                )
                            )

    return tuple(reports)


# ---------------------------------------------------------------------------
# PathResolver
# ---------------------------------------------------------------------------


class PathResolver:
    """Resolves signal paths for zone activations.

    Reads from the SystemConfig (via GraphView) and the ActivePathsRegistry.
    Does not mutate any state.
    """

    def __init__(
        self,
        config: SystemConfig,
        active_registry: ActivePathsRegistry | None = None,
    ) -> None:
        self._view = GraphView(config)
        self._active = active_registry or ActivePathsRegistry()

    @property
    def view(self) -> GraphView:
        """Expose the underlying GraphView for inspection commands."""
        return self._view

    def resolve(
        self,
        zone_id: str,
        source_device_id: str,
        virtual_source_id: str | None = None,
        sink_device_id: str | None = None,
    ) -> ZoneResolverResult:
        """Compute the resolver result for a zone activation request.

        zone_id: the zone being activated.
        source_device_id: the source device.
        virtual_source_id: if set, this is a virtual source on source_device_id.
        sink_device_id: for selectable_exclusive zones, which sink to use.
            If None, uses the zone's default_sink_device_id or the first sink.
        """
        zone = self._view.get_zone(zone_id)
        if zone is None:
            return ZoneResolverResult(
                zone_id=zone_id,
                source_device_id=source_device_id,
                virtual_source_id=virtual_source_id,
                is_virtual_source=virtual_source_id is not None,
                sink_device_ids=(),
                video_paths=(),
                audio_paths=(),
                contentions=(),
                exclusive_output_usage=(),
            )

        # Determine sink devices.
        sink_ids = self._sink_ids_for_request(zone, sink_device_id)

        if not sink_ids:
            return ZoneResolverResult(
                zone_id=zone_id,
                source_device_id=source_device_id,
                virtual_source_id=virtual_source_id,
                is_virtual_source=virtual_source_id is not None,
                sink_device_ids=(),
                video_paths=(),
                audio_paths=(),
                contentions=(),
                exclusive_output_usage=(),
            )

        # Virtual source: no graph traversal, just record the device.
        if virtual_source_id is not None:
            return ZoneResolverResult(
                zone_id=zone_id,
                source_device_id=source_device_id,
                virtual_source_id=virtual_source_id,
                is_virtual_source=True,
                sink_device_ids=tuple(sink_ids),
                video_paths=(),
                audio_paths=(),
                contentions=(),
                exclusive_output_usage=(),
            )

        # Resolve paths for each sink.
        video_paths: list[ResolvedSinglePath | PathResolutionError] = []
        audio_paths: list[ResolvedSinglePath | PathResolutionError] = []

        for sink_id in sink_ids:
            video_paths.append(self._resolve_one(source_device_id, sink_id, "video"))
            audio_paths.append(self._resolve_one(source_device_id, sink_id, "audio"))

        resolved_video = [p for p in video_paths if isinstance(p, ResolvedSinglePath)]
        resolved_audio = [p for p in audio_paths if isinstance(p, ResolvedSinglePath)]
        all_resolved = resolved_video + resolved_audio

        exclusive = _exclusive_output_usage(self._view, all_resolved)
        contentions = _detect_contentions(self._view, all_resolved, zone_id, self._active)

        return ZoneResolverResult(
            zone_id=zone_id,
            source_device_id=source_device_id,
            virtual_source_id=None,
            is_virtual_source=False,
            sink_device_ids=tuple(sink_ids),
            video_paths=tuple(video_paths),
            audio_paths=tuple(audio_paths),
            contentions=contentions,
            exclusive_output_usage=exclusive,
        )

    def _sink_ids_for_request(self, zone: object, requested_sink: str | None) -> list[str]:
        """Return the list of sink device IDs to resolve paths to."""
        from ..graph.model import Zone as ZoneModel  # local import avoids circular

        assert isinstance(zone, ZoneModel)

        if zone.sink_mode == SinkMode.SIMULTANEOUS:
            return list(zone.sink_device_ids)

        if zone.sink_mode == SinkMode.SELECTABLE_EXCLUSIVE:
            target = (
                requested_sink
                or zone.default_sink_device_id
                or (zone.sink_device_ids[0] if zone.sink_device_ids else None)
            )
            return [target] if target else []

        # SINGLE (default)
        if requested_sink:
            return [requested_sink]
        if zone.sink_device_ids:
            return [zone.sink_device_ids[0]]
        return []

    def _resolve_one(
        self, source_device_id: str, sink_device_id: str, carrier: str
    ) -> ResolvedSinglePath | PathResolutionError:
        """Resolve one carrier path from source to a single sink."""
        nodes = _bfs(self._view, source_device_id, sink_device_id, carrier)
        if nodes is None:
            return PathResolutionError(
                carrier=carrier,
                source_device_id=source_device_id,
                sink_device_id=sink_device_id,
                reason=f"No {carrier} path from {source_device_id} to {sink_device_id}",
            )
        hops = _nodes_to_hops(self._view, nodes)
        return ResolvedSinglePath(
            carrier=carrier,
            source_device_id=source_device_id,
            sink_device_id=sink_device_id,
            hops=hops,
        )
