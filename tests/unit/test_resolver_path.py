"""Tests for resolver.path: BFS, PathHop construction, contention detection."""

from __future__ import annotations

from custom_components.media_room_manager.graph.model import (
    Connection,
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
    ActivePathsRegistry,
    PathResolutionError,
    PathResolver,
    ResolvedSinglePath,
    ZoneResolverResult,
)

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _out(iface_id: str, itype: InterfaceType, og: str) -> Interface:
    return Interface(
        id=iface_id,
        direction=InterfaceDirection.OUTPUT,
        type=itype,
        label=iface_id,
        output_group=og,
    )


def _inp(iface_id: str, itype: InterfaceType, routable: list[str]) -> Interface:
    return Interface(
        id=iface_id,
        direction=InterfaceDirection.INPUT,
        type=itype,
        label=iface_id,
        routable_to_output_group=tuple(routable),
    )


def _conn(cid: str, fd: str, fi: str, td: str, ti: str) -> Connection:
    return Connection(
        id=cid, from_device_id=fd, from_interface_id=fi, to_device_id=td, to_interface_id=ti
    )


def _og(og_id: str) -> OutputGroup:
    return OutputGroup(id=og_id)


def _device(
    dev_id: str,
    ifaces: list[Interface],
    ogs: list[OutputGroup],
    exclusive_outputs: bool = False,
    inputs_exclusive: list[str] | None = None,
) -> Device:
    return Device(
        id=dev_id,
        name=dev_id,
        profile_id="test/p",
        interfaces=tuple(ifaces),
        output_groups=tuple(ogs),
        exclusive_outputs=exclusive_outputs,
        inputs_are_exclusive_per_output_group=tuple(inputs_exclusive or []),
    )


def _zone(zone_id: str, sinks: list[str], mode: SinkMode = SinkMode.SINGLE) -> Zone:
    return Zone(id=zone_id, name=zone_id, sink_device_ids=tuple(sinks), sink_mode=mode)


def _config(
    devices: list[Device], connections: list[Connection], zones: list[Zone]
) -> SystemConfig:
    return SystemConfig(devices=devices, connections=connections, zones=zones)


# ---------------------------------------------------------------------------
# Two-device linear path
# ---------------------------------------------------------------------------


def test_two_device_video_path() -> None:
    """Source → Sink via one HDMI connection."""
    src = _device("src", [_out("o1", InterfaceType.HDMI, "main")], [_og("main")])
    sink = _device("sink", [_inp("i1", InterfaceType.HDMI, ["main"])], [_og("main")])
    conn = _conn("c1", "src", "o1", "sink", "i1")
    zone = _zone("z1", ["sink"])
    config = _config([src, sink], [conn], [zone])
    resolver = PathResolver(config)

    result = resolver.resolve("z1", "src")
    assert len(result.video_paths) == 1
    path = result.video_paths[0]
    assert isinstance(path, ResolvedSinglePath)
    assert path.carrier == "video"
    assert len(path.hops) == 2

    src_hop, sink_hop = path.hops
    assert src_hop.device_id == "src"
    assert src_hop.entry_interface_id is None
    assert src_hop.exit_interface_id == "o1"

    assert sink_hop.device_id == "sink"
    assert sink_hop.entry_interface_id == "i1"
    assert sink_hop.exit_interface_id is None
    assert sink_hop.output_group_id == "main"


def test_two_device_audio_path() -> None:
    src = _device("src", [_out("o1", InterfaceType.HDMI, "main")], [_og("main")])
    sink = _device("sink", [_inp("i1", InterfaceType.HDMI, ["main"])], [_og("main")])
    conn = _conn("c1", "src", "o1", "sink", "i1")
    zone = _zone("z1", ["sink"])
    config = _config([src, sink], [conn], [zone])

    result = PathResolver(config).resolve("z1", "src")
    audio = result.audio_paths[0]
    assert isinstance(audio, ResolvedSinglePath)
    assert audio.carrier == "audio"


def test_no_path_returns_error() -> None:
    src = _device("src", [_out("o1", InterfaceType.HDMI, "main")], [_og("main")])
    sink = _device("sink", [_inp("i1", InterfaceType.HDMI, ["main"])], [_og("main")])
    # No connection
    zone = _zone("z1", ["sink"])
    config = _config([src, sink], [], [zone])

    result = PathResolver(config).resolve("z1", "src")
    assert isinstance(result.video_paths[0], PathResolutionError)
    assert isinstance(result.audio_paths[0], PathResolutionError)


# ---------------------------------------------------------------------------
# Three-device chain (transit device transparency — task 4.3)
# ---------------------------------------------------------------------------


def test_three_device_video_path_with_transit() -> None:
    """Source → AVR → TV: transit AVR routes via output group."""
    src = _device("src", [_out("src_hdmi", InterfaceType.HDMI, "main")], [_og("main")])
    avr = _device(
        "avr",
        [
            _inp("avr_in", InterfaceType.HDMI, ["main"]),
            _out("avr_out", InterfaceType.HDMI, "main"),
        ],
        [_og("main")],
    )
    tv = _device("tv", [_inp("tv_in", InterfaceType.HDMI, ["main"])], [_og("main")])
    c1 = _conn("c1", "src", "src_hdmi", "avr", "avr_in")
    c2 = _conn("c2", "avr", "avr_out", "tv", "tv_in")
    zone = _zone("z1", ["tv"])
    config = _config([src, avr, tv], [c1, c2], [zone])

    result = PathResolver(config).resolve("z1", "src")
    path = result.video_paths[0]
    assert isinstance(path, ResolvedSinglePath)
    assert len(path.hops) == 3

    src_hop, avr_hop, tv_hop = path.hops
    assert src_hop.device_id == "src"
    assert avr_hop.device_id == "avr"
    assert avr_hop.entry_interface_id == "avr_in"
    assert avr_hop.exit_interface_id == "avr_out"
    assert avr_hop.output_group_id == "main"
    assert tv_hop.device_id == "tv"
    assert tv_hop.entry_interface_id == "tv_in"
    assert tv_hop.exit_interface_id is None


def test_transit_respects_routable_groups() -> None:
    """Input not routable to the output group blocks transit."""
    src = _device("src", [_out("o1", InterfaceType.HDMI, "main")], [_og("main")])
    # avr_in is only routable to zone2, not main
    avr = _device(
        "avr",
        [
            _inp("avr_in", InterfaceType.HDMI, ["zone2"]),
            _out("avr_out", InterfaceType.HDMI, "main"),
        ],
        [_og("main"), _og("zone2")],
    )
    tv = _device("tv", [_inp("tv_in", InterfaceType.HDMI, ["main"])], [_og("main")])
    c1 = _conn("c1", "src", "o1", "avr", "avr_in")
    c2 = _conn("c2", "avr", "avr_out", "tv", "tv_in")
    zone = _zone("z1", ["tv"])
    config = _config([src, avr, tv], [c1, c2], [zone])

    result = PathResolver(config).resolve("z1", "src")
    assert isinstance(result.video_paths[0], PathResolutionError)


# ---------------------------------------------------------------------------
# ARC reverse audio (task 4.4)
# ---------------------------------------------------------------------------


def test_arc_audio_reverse_path() -> None:
    """TV is audio source; audio flows backward via ARC to AVR."""
    # Connection: avr.arc_out → tv.arc_in
    avr = _device(
        "avr",
        [_out("arc_out", InterfaceType.HDMI_AUDIO_RETURN, "main")],
        [_og("main")],
    )
    tv = _device(
        "tv",
        [
            _inp("arc_in", InterfaceType.HDMI_AUDIO_RETURN, ["main"]),
        ],
        [_og("main")],
    )
    conn = _conn("c1", "avr", "arc_out", "tv", "arc_in")
    zone = _zone("z1", ["avr"])
    config = _config([avr, tv], [conn], [zone])

    # TV is the audio source; AVR is the sink (volume authority).
    result = PathResolver(config).resolve("z1", "tv")
    audio = result.audio_paths[0]
    assert isinstance(audio, ResolvedSinglePath), f"Expected resolved, got: {audio}"
    assert audio.source_device_id == "tv"
    assert audio.sink_device_id == "avr"
    assert len(audio.hops) == 2

    src_hop, sink_hop = audio.hops
    assert src_hop.device_id == "tv"
    assert src_hop.exit_interface_id == "arc_in"  # ARC input used as audio source
    assert sink_hop.device_id == "avr"
    assert sink_hop.entry_interface_id == "arc_out"  # ARC output receives audio


# ---------------------------------------------------------------------------
# Multi-sink zones (task 4.6)
# ---------------------------------------------------------------------------


def test_simultaneous_zone_resolves_to_all_sinks() -> None:
    src = _device(
        "src",
        [_out("o1", InterfaceType.HDMI, "main"), _out("o2", InterfaceType.HDMI, "main2")],
        [_og("main"), _og("main2")],
    )
    tv1 = _device("tv1", [_inp("in1", InterfaceType.HDMI, ["main"])], [_og("main")])
    tv2 = _device("tv2", [_inp("in2", InterfaceType.HDMI, ["main"])], [_og("main")])
    c1 = _conn("c1", "src", "o1", "tv1", "in1")
    c2 = _conn("c2", "src", "o2", "tv2", "in2")
    zone = _zone("z1", ["tv1", "tv2"], SinkMode.SIMULTANEOUS)
    config = _config([src, tv1, tv2], [c1, c2], [zone])

    result = PathResolver(config).resolve("z1", "src")
    assert result.sink_device_ids == ("tv1", "tv2")
    assert len(result.video_paths) == 2
    assert all(isinstance(p, ResolvedSinglePath) for p in result.video_paths)
    sink_ids = {p.sink_device_id for p in result.video_paths if isinstance(p, ResolvedSinglePath)}
    assert sink_ids == {"tv1", "tv2"}


def test_selectable_exclusive_uses_requested_sink() -> None:
    src = _device(
        "src",
        [_out("o1", InterfaceType.HDMI, "main"), _out("o2", InterfaceType.HDMI, "main")],
        [_og("main")],
    )
    tv1 = _device("tv1", [_inp("in1", InterfaceType.HDMI, ["main"])], [_og("main")])
    tv2 = _device("tv2", [_inp("in2", InterfaceType.HDMI, ["main"])], [_og("main")])
    c1 = _conn("c1", "src", "o1", "tv1", "in1")
    c2 = _conn("c2", "src", "o2", "tv2", "in2")
    zone = _zone("z1", ["tv1", "tv2"], SinkMode.SELECTABLE_EXCLUSIVE)
    config = _config([src, tv1, tv2], [c1, c2], [zone])

    result = PathResolver(config).resolve("z1", "src", sink_device_id="tv2")
    assert result.sink_device_ids == ("tv2",)
    assert len(result.video_paths) == 1
    path = result.video_paths[0]
    assert isinstance(path, ResolvedSinglePath)
    assert path.sink_device_id == "tv2"


# ---------------------------------------------------------------------------
# Virtual sources (task 4.7)
# ---------------------------------------------------------------------------


def test_virtual_source_skips_graph_traversal() -> None:
    src = _device("src", [], [_og("main")])
    tv = _device("tv", [_inp("tv_in", InterfaceType.HDMI, ["main"])], [_og("main")])
    zone = _zone("z1", ["tv"])
    config = _config([src, tv], [], [zone])

    result = PathResolver(config).resolve("z1", "src", virtual_source_id="tuner")
    assert result.is_virtual_source is True
    assert result.virtual_source_id == "tuner"
    assert result.video_paths == ()
    assert result.audio_paths == ()
    assert result.contentions == ()


# ---------------------------------------------------------------------------
# exclusive_outputs tracking (task 4.8)
# ---------------------------------------------------------------------------


def test_exclusive_outputs_tracked() -> None:
    src = _device("src", [_out("src_out", InterfaceType.HDMI, "main")], [_og("main")])
    lumagen = _device(
        "lumagen",
        [
            _inp("luma_in", InterfaceType.HDMI, ["main"]),
            _out("luma_out_a", InterfaceType.HDMI, "main"),
        ],
        [_og("main")],
        exclusive_outputs=True,
    )
    tv = _device("tv", [_inp("tv_in", InterfaceType.HDMI, ["main"])], [_og("main")])
    c1 = _conn("c1", "src", "src_out", "lumagen", "luma_in")
    c2 = _conn("c2", "lumagen", "luma_out_a", "tv", "tv_in")
    zone = _zone("z1", ["tv"])
    config = _config([src, lumagen, tv], [c1, c2], [zone])

    result = PathResolver(config).resolve("z1", "src")
    assert ("lumagen", "luma_out_a") in result.exclusive_output_usage


# ---------------------------------------------------------------------------
# Contention detection (task 4.9)
# ---------------------------------------------------------------------------


def _build_active_result(
    zone_id: str,
    device_id: str,
    entry_iface: str,
    exit_iface: str,
    og_id: str,
    source_id: str,
    sink_id: str,
) -> ZoneResolverResult:
    """Build a minimal active ZoneResolverResult for contention tests."""
    from custom_components.media_room_manager.resolver.path import PathHop

    hop = PathHop(
        device_id=device_id,
        entry_interface_id=entry_iface,
        exit_interface_id=exit_iface,
        output_group_id=og_id,
    )
    path = ResolvedSinglePath(
        carrier="video",
        source_device_id=source_id,
        sink_device_id=sink_id,
        hops=(hop,),
    )
    return ZoneResolverResult(
        zone_id=zone_id,
        source_device_id=source_id,
        virtual_source_id=None,
        is_virtual_source=False,
        sink_device_ids=(sink_id,),
        video_paths=(path,),
        audio_paths=(),
        contentions=(),
        exclusive_output_usage=(),
    )


def test_input_side_contention_detected() -> None:
    """Two zones competing for the same AVR input group on different inputs."""
    avr = _device(
        "avr",
        [
            _inp("hdmi1", InterfaceType.HDMI, ["main"]),
            _inp("hdmi2", InterfaceType.HDMI, ["main"]),
            _out("avr_out", InterfaceType.HDMI, "main"),
        ],
        [_og("main")],
        inputs_exclusive=["main"],
    )
    src1 = _device("src1", [_out("o1", InterfaceType.HDMI, "main")], [_og("main")])
    src2 = _device("src2", [_out("o2", InterfaceType.HDMI, "main")], [_og("main")])
    tv = _device("tv", [_inp("tv_in", InterfaceType.HDMI, ["main"])], [_og("main")])
    c1 = _conn("c1", "src1", "o1", "avr", "hdmi1")
    c2 = _conn("c2", "src2", "o2", "avr", "hdmi2")
    c3 = _conn("c3", "avr", "avr_out", "tv", "tv_in")
    zone1 = _zone("z1", ["tv"])
    zone2 = _zone("z2", ["tv"])
    config = _config([avr, src1, src2, tv], [c1, c2, c3], [zone1, zone2])

    # Zone 1 is already active using hdmi1.
    active = ActivePathsRegistry()
    active.update(_build_active_result("z1", "avr", "hdmi1", "avr_out", "main", "src1", "tv"))

    # Zone 2 wants to use hdmi2 — input-side contention.
    resolver = PathResolver(config, active)
    result = resolver.resolve("z2", "src2")
    assert len(result.contentions) > 0
    contention = result.contentions[0]
    assert contention.kind == "input_side"
    assert contention.device_id == "avr"
    assert contention.conflicting_zone_id == "z1"


def test_output_side_contention_detected() -> None:
    """Two zones competing for different outputs of an exclusive_outputs device."""
    lumagen = _device(
        "lumagen",
        [
            _inp("luma_in", InterfaceType.HDMI, ["main"]),
            _out("out_a", InterfaceType.HDMI, "main"),
            _out("out_b", InterfaceType.HDMI, "main"),
        ],
        [_og("main")],
        exclusive_outputs=True,
    )
    src = _device("src", [_out("src_out", InterfaceType.HDMI, "main")], [_og("main")])
    tv_a = _device("tv_a", [_inp("in_a", InterfaceType.HDMI, ["main"])], [_og("main")])
    tv_b = _device("tv_b", [_inp("in_b", InterfaceType.HDMI, ["main"])], [_og("main")])
    c_src = _conn("c_src", "src", "src_out", "lumagen", "luma_in")
    c_a = _conn("c_a", "lumagen", "out_a", "tv_a", "in_a")
    c_b = _conn("c_b", "lumagen", "out_b", "tv_b", "in_b")
    zone_a = _zone("z_a", ["tv_a"])
    zone_b = _zone("z_b", ["tv_b"])
    config = _config([lumagen, src, tv_a, tv_b], [c_src, c_a, c_b], [zone_a, zone_b])

    # Zone A is active using out_a.
    active = ActivePathsRegistry()
    active.update(_build_active_result("z_a", "lumagen", "luma_in", "out_a", "main", "src", "tv_a"))

    # Zone B wants out_b — output-side contention.
    resolver = PathResolver(config, active)
    result = resolver.resolve("z_b", "src")
    assert len(result.contentions) > 0
    contention = result.contentions[0]
    assert contention.kind == "output_side"
    assert contention.device_id == "lumagen"
    assert contention.conflicting_zone_id == "z_a"


def test_no_contention_when_same_input_used() -> None:
    """Two zones sharing the same AVR input (no exclusive constraint) → no contention."""
    avr = _device(
        "avr",
        [
            _inp("hdmi1", InterfaceType.HDMI, ["main"]),
            _out("avr_out", InterfaceType.HDMI, "main"),
        ],
        [_og("main")],
        # inputs_exclusive NOT set for this device
    )
    src = _device("src", [_out("src_out", InterfaceType.HDMI, "main")], [_og("main")])
    tv1 = _device("tv1", [_inp("tv1_in", InterfaceType.HDMI, ["main"])], [_og("main")])
    tv2 = _device("tv2", [_inp("tv2_in", InterfaceType.HDMI, ["main"])], [_og("main")])
    # Two paths through the same AVR hdmi1 input — allowed since no exclusive constraint.
    c1 = _conn("c1", "src", "src_out", "avr", "hdmi1")
    c2 = _conn("c2", "avr", "avr_out", "tv1", "tv1_in")
    # tv2 has no path — but the contention check is what matters here.
    zone1 = _zone("z1", ["tv1"])
    zone2 = _zone("z2", ["tv1"])
    config = _config([avr, src, tv1, tv2], [c1, c2], [zone1, zone2])

    active = ActivePathsRegistry()
    active.update(_build_active_result("z1", "avr", "hdmi1", "avr_out", "main", "src", "tv1"))

    resolver = PathResolver(config, active)
    result = resolver.resolve("z2", "src")
    input_side = [c for c in result.contentions if c.kind == "input_side"]
    assert len(input_side) == 0


# ---------------------------------------------------------------------------
# ActivePathsRegistry
# ---------------------------------------------------------------------------


def test_active_registry_update_and_get() -> None:
    reg = ActivePathsRegistry()
    result = ZoneResolverResult(
        zone_id="z1",
        source_device_id="src",
        virtual_source_id=None,
        is_virtual_source=False,
        sink_device_ids=("tv",),
        video_paths=(),
        audio_paths=(),
        contentions=(),
        exclusive_output_usage=(),
    )
    reg.update(result)
    assert reg.get("z1") is result


def test_active_registry_remove() -> None:
    reg = ActivePathsRegistry()
    result = ZoneResolverResult(
        zone_id="z1",
        source_device_id="src",
        virtual_source_id=None,
        is_virtual_source=False,
        sink_device_ids=("tv",),
        video_paths=(),
        audio_paths=(),
        contentions=(),
        exclusive_output_usage=(),
    )
    reg.update(result)
    reg.remove("z1")
    assert reg.get("z1") is None


def test_active_registry_remove_missing_is_safe() -> None:
    reg = ActivePathsRegistry()
    reg.remove("nonexistent")  # should not raise


# ---------------------------------------------------------------------------
# Zone not found
# ---------------------------------------------------------------------------


def test_missing_zone_returns_empty_result() -> None:
    config = _config([], [], [])
    result = PathResolver(config).resolve("no_such_zone", "src")
    assert result.zone_id == "no_such_zone"
    assert result.video_paths == ()
    assert result.audio_paths == ()
