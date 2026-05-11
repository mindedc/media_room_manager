"""Queryable view over a SystemConfig for path resolution.

GraphView pre-computes lookup indices from the flat SystemConfig so the
path resolver can answer questions like "what does this output connect to?",
"what outputs can signal reach from this input?", and "which inputs are
routable to this output group?" in O(1) average time.
"""

from __future__ import annotations

from ..graph.model import (
    Connection,
    Device,
    Interface,
    InterfaceDirection,
    InterfaceType,
    OutputGroup,
    Zone,
)
from ..graph.system_config import SystemConfig

_AUDIO_TYPES: frozenset[InterfaceType] = frozenset(
    {
        InterfaceType.HDMI,
        InterfaceType.HDMI_AUDIO_RETURN,
        InterfaceType.OPTICAL_AUDIO,
        InterfaceType.COAX_AUDIO,
        InterfaceType.RCA_AUDIO,
        InterfaceType.XLR_AUDIO,
    }
)

_VIDEO_TYPES: frozenset[InterfaceType] = frozenset(
    {
        InterfaceType.HDMI,
        InterfaceType.HDMI_AUDIO_RETURN,
        InterfaceType.COMPONENT_VIDEO,
        InterfaceType.COMPOSITE_VIDEO,
    }
)


class GraphView:
    """Pre-computed lookup indices over a SystemConfig.

    Instantiate once per SystemConfig change; the view is read-only.
    """

    def __init__(self, config: SystemConfig) -> None:
        self._devices: dict[str, Device] = {d.id: d for d in config.devices}
        self._zones: dict[str, Zone] = {z.id: z for z in config.zones}

        # device_id → interface_id → Interface
        self._ifaces: dict[str, dict[str, Interface]] = {}
        for device in config.devices:
            self._ifaces[device.id] = {iface.id: iface for iface in device.interfaces}

        # device_id → output_group_id → OutputGroup
        self._output_groups: dict[str, dict[str, OutputGroup]] = {}
        for device in config.devices:
            self._output_groups[device.id] = {og.id: og for og in device.output_groups}

        # (from_device_id, from_interface_id) → Connection
        self._conn_by_output: dict[tuple[str, str], Connection] = {}
        # (to_device_id, to_interface_id) → list[Connection]
        self._conn_by_input: dict[tuple[str, str], list[Connection]] = {}
        for conn in config.connections:
            self._conn_by_output[(conn.from_device_id, conn.from_interface_id)] = conn
            key = (conn.to_device_id, conn.to_interface_id)
            self._conn_by_input.setdefault(key, []).append(conn)

    # ------------------------------------------------------------------
    # Basic object lookups
    # ------------------------------------------------------------------

    def get_device(self, device_id: str) -> Device | None:
        """Return the Device with the given id, or None."""
        return self._devices.get(device_id)

    def get_interface(self, device_id: str, interface_id: str) -> Interface | None:
        """Return the Interface on device_id with the given id, or None."""
        return self._ifaces.get(device_id, {}).get(interface_id)

    def get_output_group(self, device_id: str, output_group_id: str) -> OutputGroup | None:
        """Return the OutputGroup on device_id with the given id, or None."""
        return self._output_groups.get(device_id, {}).get(output_group_id)

    def get_zone(self, zone_id: str) -> Zone | None:
        """Return the Zone with the given id, or None."""
        return self._zones.get(zone_id)

    def all_zones(self) -> list[Zone]:
        """Return all zones in the config."""
        return list(self._zones.values())

    def all_devices(self) -> list[Device]:
        """Return all devices in the config."""
        return list(self._devices.values())

    # ------------------------------------------------------------------
    # Connection lookups
    # ------------------------------------------------------------------

    def connection_from_output(self, device_id: str, interface_id: str) -> Connection | None:
        """Return the connection whose source is this output interface, or None."""
        return self._conn_by_output.get((device_id, interface_id))

    def connections_to_input(self, device_id: str, interface_id: str) -> list[Connection]:
        """Return all connections whose target is this input interface."""
        return list(self._conn_by_input.get((device_id, interface_id), []))

    # ------------------------------------------------------------------
    # Interface set queries
    # ------------------------------------------------------------------

    def inputs_routable_to_output_group(
        self, device_id: str, output_group_id: str
    ) -> list[Interface]:
        """All INPUT interfaces on device_id with output_group_id in routable_to_output_group."""
        result = []
        for iface in self._ifaces.get(device_id, {}).values():
            if (
                iface.direction == InterfaceDirection.INPUT
                and output_group_id in iface.routable_to_output_group
            ):
                result.append(iface)
        return result

    def outputs_in_output_group(self, device_id: str, output_group_id: str) -> list[Interface]:
        """All OUTPUT interfaces on device_id belonging to output_group_id."""
        result = []
        for iface in self._ifaces.get(device_id, {}).values():
            if (
                iface.direction == InterfaceDirection.OUTPUT
                and iface.output_group == output_group_id
            ):
                result.append(iface)
        return result

    def output_interfaces_reachable_from_input(
        self,
        device_id: str,
        input_interface_id: str,
        carrier: str,
    ) -> list[Interface]:
        """Output interfaces signal can reach from this input, filtered by carrier.

        Respects routable_to_output_group. carrier must be "audio" or "video".
        """
        iface = self.get_interface(device_id, input_interface_id)
        if iface is None or iface.direction != InterfaceDirection.INPUT:
            return []

        carrier_types = _AUDIO_TYPES if carrier == "audio" else _VIDEO_TYPES
        result = []
        for og_id in iface.routable_to_output_group:
            for out_iface in self.outputs_in_output_group(device_id, og_id):
                if out_iface.type in carrier_types:
                    result.append(out_iface)
        return result

    # ------------------------------------------------------------------
    # Source / sink interface queries
    # ------------------------------------------------------------------

    def source_video_interfaces(self, device_id: str) -> list[Interface]:
        """OUTPUT interfaces on device_id that carry video."""
        return [
            iface
            for iface in self._ifaces.get(device_id, {}).values()
            if iface.direction == InterfaceDirection.OUTPUT and iface.type in _VIDEO_TYPES
        ]

    def source_audio_interfaces(self, device_id: str) -> list[Interface]:
        """Interfaces on device_id from which audio can originate.

        Normally these are OUTPUT interfaces. An hdmi_audio_return INPUT is
        also included because audio can originate from it in the reverse
        direction (ARC/eARC).
        """
        result = []
        for iface in self._ifaces.get(device_id, {}).values():
            if iface.type not in _AUDIO_TYPES:
                continue
            if (
                iface.direction == InterfaceDirection.OUTPUT
                or iface.type == InterfaceType.HDMI_AUDIO_RETURN
            ):
                result.append(iface)
        return result

    def sink_video_interfaces(self, device_id: str) -> list[Interface]:
        """INPUT interfaces on device_id that carry video."""
        return [
            iface
            for iface in self._ifaces.get(device_id, {}).values()
            if iface.direction == InterfaceDirection.INPUT and iface.type in _VIDEO_TYPES
        ]

    def sink_audio_interfaces(self, device_id: str) -> list[Interface]:
        """Interfaces on device_id where audio can terminate.

        Normally these are INPUT interfaces. An hdmi_audio_return OUTPUT is
        also included because audio can arrive at it in the reverse direction
        (ARC/eARC).
        """
        result = []
        for iface in self._ifaces.get(device_id, {}).values():
            if iface.type not in _AUDIO_TYPES:
                continue
            if (
                iface.direction == InterfaceDirection.INPUT
                or iface.type == InterfaceType.HDMI_AUDIO_RETURN
            ):
                result.append(iface)
        return result
