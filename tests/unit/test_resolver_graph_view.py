"""Tests for resolver.graph_view.GraphView."""

from __future__ import annotations

from custom_components.media_room_manager.graph.model import (
    Connection,
    Device,
    Interface,
    InterfaceDirection,
    InterfaceType,
    OutputGroup,
    Zone,
)
from custom_components.media_room_manager.graph.system_config import SystemConfig
from custom_components.media_room_manager.resolver.graph_view import GraphView

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_device(
    device_id: str,
    interfaces: list[Interface] | None = None,
    output_groups: list[OutputGroup] | None = None,
) -> Device:
    return Device(
        id=device_id,
        name=device_id,
        profile_id="test/profile",
        interfaces=tuple(interfaces or []),
        output_groups=tuple(output_groups or []),
    )


def _out(iface_id: str, itype: InterfaceType, output_group: str) -> Interface:
    return Interface(
        id=iface_id,
        direction=InterfaceDirection.OUTPUT,
        type=itype,
        label=iface_id,
        output_group=output_group,
    )


def _inp(iface_id: str, itype: InterfaceType, routable: list[str]) -> Interface:
    return Interface(
        id=iface_id,
        direction=InterfaceDirection.INPUT,
        type=itype,
        label=iface_id,
        routable_to_output_group=tuple(routable),
    )


def _conn(conn_id: str, from_dev: str, from_iface: str, to_dev: str, to_iface: str) -> Connection:
    return Connection(
        id=conn_id,
        from_device_id=from_dev,
        from_interface_id=from_iface,
        to_device_id=to_dev,
        to_interface_id=to_iface,
    )


def _make_view(
    devices: list[Device] | None = None,
    connections: list[Connection] | None = None,
    zones: list[Zone] | None = None,
) -> GraphView:
    config = SystemConfig(
        devices=devices or [],
        connections=connections or [],
        zones=zones or [],
    )
    return GraphView(config)


# ---------------------------------------------------------------------------
# Basic lookups
# ---------------------------------------------------------------------------


def test_get_device_found() -> None:
    dev = _make_device("d1")
    view = _make_view(devices=[dev])
    assert view.get_device("d1") is dev


def test_get_device_missing() -> None:
    view = _make_view()
    assert view.get_device("nope") is None


def test_get_interface_found() -> None:
    iface = _out("hdmi_out", InterfaceType.HDMI, "main")
    dev = _make_device("d1", interfaces=[iface])
    view = _make_view(devices=[dev])
    assert view.get_interface("d1", "hdmi_out") is iface


def test_get_interface_missing_device() -> None:
    view = _make_view()
    assert view.get_interface("nope", "hdmi_out") is None


def test_get_output_group_found() -> None:
    og = OutputGroup(id="main")
    dev = _make_device("d1", output_groups=[og])
    view = _make_view(devices=[dev])
    assert view.get_output_group("d1", "main") is og


def test_get_zone_found() -> None:
    zone = Zone(id="z1", name="Living Room")
    view = _make_view(zones=[zone])
    assert view.get_zone("z1") is zone


# ---------------------------------------------------------------------------
# Connection lookups
# ---------------------------------------------------------------------------


def test_connection_from_output() -> None:
    conn = _conn("c1", "d1", "hdmi_out", "d2", "hdmi_in")
    view = _make_view(connections=[conn])
    assert view.connection_from_output("d1", "hdmi_out") is conn


def test_connection_from_output_missing() -> None:
    view = _make_view()
    assert view.connection_from_output("d1", "hdmi_out") is None


def test_connections_to_input() -> None:
    conn = _conn("c1", "d1", "hdmi_out", "d2", "hdmi_in")
    view = _make_view(connections=[conn])
    result = view.connections_to_input("d2", "hdmi_in")
    assert result == [conn]


def test_connections_to_input_multiple() -> None:
    c1 = _conn("c1", "d1", "o1", "d3", "in1")
    c2 = _conn("c2", "d2", "o2", "d3", "in1")
    view = _make_view(connections=[c1, c2])
    result = view.connections_to_input("d3", "in1")
    assert set(r.id for r in result) == {"c1", "c2"}


# ---------------------------------------------------------------------------
# inputs_routable_to_output_group
# ---------------------------------------------------------------------------


def test_inputs_routable_to_output_group() -> None:
    i1 = _inp("in1", InterfaceType.HDMI, ["main"])
    i2 = _inp("in2", InterfaceType.HDMI, ["main", "zone2"])
    i3 = _inp("in3", InterfaceType.HDMI, ["zone2"])
    dev = _make_device("d1", interfaces=[i1, i2, i3])
    view = _make_view(devices=[dev])
    result = {i.id for i in view.inputs_routable_to_output_group("d1", "main")}
    assert result == {"in1", "in2"}


def test_inputs_routable_excludes_outputs() -> None:
    out = _out("hdmi_out", InterfaceType.HDMI, "main")
    dev = _make_device("d1", interfaces=[out])
    view = _make_view(devices=[dev])
    assert view.inputs_routable_to_output_group("d1", "main") == []


# ---------------------------------------------------------------------------
# output_interfaces_reachable_from_input
# ---------------------------------------------------------------------------


def test_reachable_from_input_respects_routable_groups() -> None:
    """Input routable to 'main' reaches outputs in 'main' only."""
    in1 = _inp("in1", InterfaceType.HDMI, ["main"])
    out_main = _out("out_main", InterfaceType.HDMI, "main")
    out_zone2 = _out("out_zone2", InterfaceType.HDMI, "zone2")
    dev = _make_device("d1", interfaces=[in1, out_main, out_zone2])
    view = _make_view(devices=[dev])
    result = {i.id for i in view.output_interfaces_reachable_from_input("d1", "in1", "video")}
    assert result == {"out_main"}


def test_reachable_from_input_carrier_filter() -> None:
    """Audio-only outputs not reachable from input when carrier is video."""
    in1 = _inp("in1", InterfaceType.HDMI, ["main"])
    hdmi_out = _out("hdmi_out", InterfaceType.HDMI, "main")
    optical_out = _out("optical_out", InterfaceType.OPTICAL_AUDIO, "main")
    dev = _make_device("d1", interfaces=[in1, hdmi_out, optical_out])
    view = _make_view(devices=[dev])
    video_result = {i.id for i in view.output_interfaces_reachable_from_input("d1", "in1", "video")}
    audio_result = {i.id for i in view.output_interfaces_reachable_from_input("d1", "in1", "audio")}
    assert video_result == {"hdmi_out"}  # HDMI carries video
    assert audio_result == {"hdmi_out", "optical_out"}  # HDMI and optical carry audio


# ---------------------------------------------------------------------------
# source / sink interface helpers
# ---------------------------------------------------------------------------


def test_source_video_interfaces_output_only() -> None:
    out = _out("hdmi_out", InterfaceType.HDMI, "main")
    inp = _inp("hdmi_in", InterfaceType.HDMI, ["main"])
    dev = _make_device("d1", interfaces=[out, inp])
    view = _make_view(devices=[dev])
    result = [i.id for i in view.source_video_interfaces("d1")]
    assert result == ["hdmi_out"]


def test_source_audio_includes_arc_input() -> None:
    """hdmi_audio_return INPUT is included as an audio source (ARC reverse)."""
    arc_in = _inp("arc_in", InterfaceType.HDMI_AUDIO_RETURN, ["main"])
    hdmi_in = _inp("hdmi_in", InterfaceType.HDMI, ["main"])
    dev = _make_device("d1", interfaces=[arc_in, hdmi_in])
    view = _make_view(devices=[dev])
    result = {i.id for i in view.source_audio_interfaces("d1")}
    assert "arc_in" in result
    assert "hdmi_in" not in result


def test_sink_audio_includes_arc_output() -> None:
    """hdmi_audio_return OUTPUT is included as an audio sink (ARC reverse)."""
    arc_out = _out("arc_out", InterfaceType.HDMI_AUDIO_RETURN, "main")
    hdmi_in = _inp("hdmi_in", InterfaceType.HDMI, ["main"])
    dev = _make_device("d1", interfaces=[arc_out, hdmi_in])
    view = _make_view(devices=[dev])
    sink = {i.id for i in view.sink_audio_interfaces("d1")}
    assert "hdmi_in" in sink
    assert "arc_out" in sink


def test_sink_video_input_only() -> None:
    arc_out = _out("arc_out", InterfaceType.HDMI_AUDIO_RETURN, "main")
    hdmi_in = _inp("hdmi_in", InterfaceType.HDMI, ["main"])
    dev = _make_device("d1", interfaces=[arc_out, hdmi_in])
    view = _make_view(devices=[dev])
    result = [i.id for i in view.sink_video_interfaces("d1")]
    assert result == ["hdmi_in"]
