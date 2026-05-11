"""Integration tests for the path resolver with multi-device fixture systems.

Each fixture represents a real-world AV system topology. Tests assert that
the resolver produces correct path hops for various source/zone combinations.

Fixtures:
  1. Marantz + Apple TV — simple 3-device chain with ARC
  2. Sports-bar matrix — 4x2 matrix with two simultaneous-zone TVs
  3. Media room TV+projector — simultaneous zone with shared AVR
  4. HDFury Diva — audio extraction path alongside video path
  5. Lumagen exclusive_outputs — two displays, only one used at a time
"""

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
    PathResolver,
    ResolvedSinglePath,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _out(iid: str, itype: InterfaceType, og: str) -> Interface:
    return Interface(
        id=iid, direction=InterfaceDirection.OUTPUT, type=itype, label=iid, output_group=og
    )


def _inp(iid: str, itype: InterfaceType, routable: list[str]) -> Interface:
    return Interface(
        id=iid,
        direction=InterfaceDirection.INPUT,
        type=itype,
        label=iid,
        routable_to_output_group=tuple(routable),
    )


def _conn(cid: str, fd: str, fi: str, td: str, ti: str) -> Connection:
    return Connection(
        id=cid, from_device_id=fd, from_interface_id=fi, to_device_id=td, to_interface_id=ti
    )


def _og(oid: str) -> OutputGroup:
    return OutputGroup(id=oid)


def _dev(
    did: str,
    ifaces: list[Interface],
    ogs: list[OutputGroup],
    excl: bool = False,
    inputs_excl: list[str] | None = None,
) -> Device:
    return Device(
        id=did,
        name=did,
        profile_id="test/p",
        interfaces=tuple(ifaces),
        output_groups=tuple(ogs),
        exclusive_outputs=excl,
        inputs_are_exclusive_per_output_group=tuple(inputs_excl or []),
    )


def _zone(
    zid: str, sinks: list[str], mode: SinkMode = SinkMode.SINGLE, default_sink: str | None = None
) -> Zone:
    return Zone(
        id=zid,
        name=zid,
        sink_device_ids=tuple(sinks),
        sink_mode=mode,
        default_sink_device_id=default_sink,
    )


def _hop_devices(path: ResolvedSinglePath) -> list[str]:
    return [hop.device_id for hop in path.hops]


# ---------------------------------------------------------------------------
# Fixture 1: Marantz + Apple TV (3-device chain + ARC audio)
#   Apple TV → Marantz AVR → TV
#   Video: appleTV → avr → tv
#   Audio: appleTV → avr (terminates; avr is volume authority)
#   ARC audio: tv → avr (TV as audio source via ARC)
# ---------------------------------------------------------------------------


def _marantz_fixture() -> tuple[SystemConfig, PathResolver]:
    apple_tv = _dev("apple_tv", [_out("atv_hdmi_out", InterfaceType.HDMI, "main")], [_og("main")])
    avr = _dev(
        "avr",
        [
            _inp("avr_hdmi1", InterfaceType.HDMI, ["main"]),
            _out("avr_hdmi_out", InterfaceType.HDMI_AUDIO_RETURN, "main"),
        ],
        [_og("main")],
        inputs_excl=["main"],
    )
    tv = _dev(
        "tv",
        [_inp("tv_arc_in", InterfaceType.HDMI_AUDIO_RETURN, ["main"])],
        [_og("main")],
    )
    conns = [
        _conn("c1", "apple_tv", "atv_hdmi_out", "avr", "avr_hdmi1"),
        _conn("c2", "avr", "avr_hdmi_out", "tv", "tv_arc_in"),
    ]
    zone = _zone("living_room", ["tv"])
    audio_zone = _zone("lr_audio", ["avr"])  # for audio-sink-is-avr tests
    config = SystemConfig(devices=[apple_tv, avr, tv], connections=conns, zones=[zone, audio_zone])
    return config, PathResolver(config)


def test_marantz_video_path() -> None:
    _config, resolver = _marantz_fixture()
    result = resolver.resolve("living_room", "apple_tv")
    path = result.video_paths[0]
    assert isinstance(path, ResolvedSinglePath)
    devices = _hop_devices(path)
    assert devices == ["apple_tv", "avr", "tv"]


def test_marantz_audio_terminates_at_avr() -> None:
    _config, resolver = _marantz_fixture()
    result = resolver.resolve("lr_audio", "apple_tv")
    path = result.audio_paths[0]
    assert isinstance(path, ResolvedSinglePath)
    devices = _hop_devices(path)
    assert devices == ["apple_tv", "avr"]
    assert path.hops[-1].device_id == "avr"
    assert path.hops[-1].exit_interface_id is None


def test_marantz_arc_audio_tv_to_avr() -> None:
    """TV as audio source sends audio to AVR via ARC."""
    _config, resolver = _marantz_fixture()
    result = resolver.resolve("lr_audio", "tv")
    path = result.audio_paths[0]
    assert isinstance(path, ResolvedSinglePath)
    devices = _hop_devices(path)
    assert devices == ["tv", "avr"]
    # TV exit is the ARC input interface (used as audio source)
    assert path.hops[0].exit_interface_id == "tv_arc_in"
    # AVR entry is its ARC output interface (receives audio in reverse)
    assert path.hops[1].entry_interface_id == "avr_hdmi_out"


def test_marantz_input_side_contention() -> None:
    """Zone 2 conflicts with zone 1 when using a different AVR input."""
    _config, _resolver = _marantz_fixture()

    # Add a second source and zone.
    blu_ray = _dev("blu_ray", [_out("bd_out", InterfaceType.HDMI, "main")], [_og("main")])
    # Patch the config with an additional source and connection.
    avr_patched = _dev(
        "avr",
        [
            _inp("avr_hdmi1", InterfaceType.HDMI, ["main"]),
            _inp("avr_hdmi2", InterfaceType.HDMI, ["main"]),
            _out("avr_hdmi_out", InterfaceType.HDMI_AUDIO_RETURN, "main"),
        ],
        [_og("main")],
        inputs_excl=["main"],
    )
    tv = _dev("tv", [_inp("tv_arc_in", InterfaceType.HDMI_AUDIO_RETURN, ["main"])], [_og("main")])
    zone1 = _zone("z1", ["tv"])
    zone2 = _zone("z2", ["tv"])
    conns = [
        _conn("c1", "apple_tv", "atv_hdmi_out", "avr", "avr_hdmi1"),
        _conn("c2", "avr", "avr_hdmi_out", "tv", "tv_arc_in"),
        _conn("c3", "blu_ray", "bd_out", "avr", "avr_hdmi2"),
    ]
    apple_tv = _dev("apple_tv", [_out("atv_hdmi_out", InterfaceType.HDMI, "main")], [_og("main")])
    config2 = SystemConfig(
        devices=[apple_tv, avr_patched, tv, blu_ray], connections=conns, zones=[zone1, zone2]
    )

    # Zone 1 is active using avr_hdmi1.
    from custom_components.media_room_manager.resolver.path import PathHop, ZoneResolverResult

    hop = PathHop(
        device_id="avr",
        entry_interface_id="avr_hdmi1",
        exit_interface_id="avr_hdmi_out",
        output_group_id="main",
    )
    active_path = ResolvedSinglePath(
        carrier="video", source_device_id="apple_tv", sink_device_id="tv", hops=(hop,)
    )
    active_result = ZoneResolverResult(
        zone_id="z1",
        source_device_id="apple_tv",
        virtual_source_id=None,
        is_virtual_source=False,
        sink_device_ids=("tv",),
        video_paths=(active_path,),
        audio_paths=(),
        contentions=(),
        exclusive_output_usage=(),
    )
    registry = ActivePathsRegistry()
    registry.update(active_result)

    resolver2 = PathResolver(config2, registry)
    result = resolver2.resolve("z2", "blu_ray")
    assert any(c.kind == "input_side" for c in result.contentions)


# ---------------------------------------------------------------------------
# Fixture 2: Sports-bar matrix (simultaneous zone)
#   Source → 4x2 Matrix → TV1 (out_1) and TV2 (out_2)
# ---------------------------------------------------------------------------


def _matrix_fixture() -> tuple[SystemConfig, PathResolver]:
    src = _dev("src", [_out("src_out", InterfaceType.HDMI, "main")], [_og("main")])
    matrix = _dev(
        "matrix",
        [
            _inp("mx_in1", InterfaceType.HDMI, ["out_1", "out_2"]),
            _out("mx_out1", InterfaceType.HDMI, "out_1"),
            _out("mx_out2", InterfaceType.HDMI, "out_2"),
        ],
        [_og("out_1"), _og("out_2")],
    )
    tv1 = _dev("tv1", [_inp("tv1_in", InterfaceType.HDMI, ["main"])], [_og("main")])
    tv2 = _dev("tv2", [_inp("tv2_in", InterfaceType.HDMI, ["main"])], [_og("main")])
    conns = [
        _conn("c1", "src", "src_out", "matrix", "mx_in1"),
        _conn("c2", "matrix", "mx_out1", "tv1", "tv1_in"),
        _conn("c3", "matrix", "mx_out2", "tv2", "tv2_in"),
    ]
    zone = _zone("bar", ["tv1", "tv2"], SinkMode.SIMULTANEOUS)
    config = SystemConfig(devices=[src, matrix, tv1, tv2], connections=conns, zones=[zone])
    return config, PathResolver(config)


def test_matrix_simultaneous_video_both_sinks() -> None:
    _config, resolver = _matrix_fixture()
    result = resolver.resolve("bar", "src")
    assert set(result.sink_device_ids) == {"tv1", "tv2"}
    for path in result.video_paths:
        assert isinstance(path, ResolvedSinglePath)


def test_matrix_video_path_uses_correct_output_group() -> None:
    _config, resolver = _matrix_fixture()
    result = resolver.resolve("bar", "src")
    paths_by_sink = {
        p.sink_device_id: p for p in result.video_paths if isinstance(p, ResolvedSinglePath)
    }
    path_tv1 = paths_by_sink["tv1"]
    # Matrix hop should use output group "out_1"
    matrix_hop = next(h for h in path_tv1.hops if h.device_id == "matrix")
    assert matrix_hop.output_group_id == "out_1"

    path_tv2 = paths_by_sink["tv2"]
    matrix_hop2 = next(h for h in path_tv2.hops if h.device_id == "matrix")
    assert matrix_hop2.output_group_id == "out_2"


# ---------------------------------------------------------------------------
# Fixture 3: Media room TV + projector (simultaneous, shared AVR)
#   Apple TV → AVR → TV (via HDMI)
#                AVR → Projector (via HDMI)
# ---------------------------------------------------------------------------


def _media_room_fixture() -> tuple[SystemConfig, PathResolver]:
    src = _dev("atv", [_out("atv_out", InterfaceType.HDMI, "main")], [_og("main")])
    avr = _dev(
        "avr",
        [
            _inp("avr_in", InterfaceType.HDMI, ["main"]),
            _out("avr_tv_out", InterfaceType.HDMI, "main"),
            _out("avr_proj_out", InterfaceType.HDMI, "main"),
        ],
        [_og("main")],
        inputs_excl=["main"],
    )
    tv = _dev("tv", [_inp("tv_in", InterfaceType.HDMI, ["main"])], [_og("main")])
    proj = _dev("proj", [_inp("proj_in", InterfaceType.HDMI, ["main"])], [_og("main")])
    conns = [
        _conn("c1", "atv", "atv_out", "avr", "avr_in"),
        _conn("c2", "avr", "avr_tv_out", "tv", "tv_in"),
        _conn("c3", "avr", "avr_proj_out", "proj", "proj_in"),
    ]
    zone = _zone("media", ["tv", "proj"], SinkMode.SIMULTANEOUS)
    config = SystemConfig(devices=[src, avr, tv, proj], connections=conns, zones=[zone])
    return config, PathResolver(config)


def test_media_room_video_to_tv_and_projector() -> None:
    _config, resolver = _media_room_fixture()
    result = resolver.resolve("media", "atv")
    assert set(result.sink_device_ids) == {"tv", "proj"}
    for path in result.video_paths:
        assert isinstance(path, ResolvedSinglePath)
        assert "avr" in _hop_devices(path)


def test_media_room_audio_both_paths_via_avr() -> None:
    _config, resolver = _media_room_fixture()
    result = resolver.resolve("media", "atv")
    # Audio terminates at AVR — but AVR is not in sink_device_ids.
    # Since zone sinks are tv and proj, audio path to tv includes avr.
    audio_paths = [p for p in result.audio_paths if isinstance(p, ResolvedSinglePath)]
    for path in audio_paths:
        assert "avr" in _hop_devices(path)


# ---------------------------------------------------------------------------
# Fixture 4: HDFury Diva (audio extraction)
#   Source → Diva (tx0 group) → TV (HDMI video)
#                                → Amp (optical audio extraction)
# ---------------------------------------------------------------------------


def _diva_fixture() -> tuple[SystemConfig, PathResolver]:
    src = _dev("src", [_out("src_hdmi", InterfaceType.HDMI, "main")], [_og("main")])
    diva = _dev(
        "diva",
        [
            _inp("diva_in", InterfaceType.HDMI, ["tx0"]),
            _out("diva_hdmi_out", InterfaceType.HDMI, "tx0"),
            _out("diva_optical_out", InterfaceType.OPTICAL_AUDIO, "tx0"),
        ],
        [_og("tx0")],
    )
    tv = _dev("tv", [_inp("tv_in", InterfaceType.HDMI, ["main"])], [_og("main")])
    amp = _dev(
        "amp", [_inp("amp_optical_in", InterfaceType.OPTICAL_AUDIO, ["main"])], [_og("main")]
    )
    conns = [
        _conn("c1", "src", "src_hdmi", "diva", "diva_in"),
        _conn("c2", "diva", "diva_hdmi_out", "tv", "tv_in"),
        _conn("c3", "diva", "diva_optical_out", "amp", "amp_optical_in"),
    ]
    zone_video = _zone("video_zone", ["tv"])
    zone_audio = _zone("audio_zone", ["amp"])
    config = SystemConfig(
        devices=[src, diva, tv, amp], connections=conns, zones=[zone_video, zone_audio]
    )
    return config, PathResolver(config)


def test_diva_video_path_via_hdmi() -> None:
    _config, resolver = _diva_fixture()
    result = resolver.resolve("video_zone", "src")
    path = result.video_paths[0]
    assert isinstance(path, ResolvedSinglePath)
    devices = _hop_devices(path)
    assert devices == ["src", "diva", "tv"]


def test_diva_audio_extraction_via_optical() -> None:
    _config, resolver = _diva_fixture()
    result = resolver.resolve("audio_zone", "src")
    path = result.audio_paths[0]
    assert isinstance(path, ResolvedSinglePath)
    devices = _hop_devices(path)
    assert devices == ["src", "diva", "amp"]
    # Diva exit is the optical output
    diva_hop = next(h for h in path.hops if h.device_id == "diva")
    assert diva_hop.exit_interface_id == "diva_optical_out"


# ---------------------------------------------------------------------------
# Fixture 5: Lumagen exclusive_outputs feeding two displays
# ---------------------------------------------------------------------------


def _lumagen_fixture() -> tuple[SystemConfig, PathResolver]:
    src = _dev("src", [_out("src_out", InterfaceType.HDMI, "main")], [_og("main")])
    lumagen = _dev(
        "lumagen",
        [
            _inp("luma_in", InterfaceType.HDMI, ["main"]),
            _out("luma_out_a", InterfaceType.HDMI, "main"),
            _out("luma_out_b", InterfaceType.HDMI, "main"),
        ],
        [_og("main")],
        excl=True,
    )
    display_a = _dev("display_a", [_inp("da_in", InterfaceType.HDMI, ["main"])], [_og("main")])
    display_b = _dev("display_b", [_inp("db_in", InterfaceType.HDMI, ["main"])], [_og("main")])
    conns = [
        _conn("c1", "src", "src_out", "lumagen", "luma_in"),
        _conn("c2", "lumagen", "luma_out_a", "display_a", "da_in"),
        _conn("c3", "lumagen", "luma_out_b", "display_b", "db_in"),
    ]
    zone_a = _zone("za", ["display_a"])
    zone_b = _zone("zb", ["display_b"])
    config = SystemConfig(
        devices=[src, lumagen, display_a, display_b], connections=conns, zones=[zone_a, zone_b]
    )
    return config, PathResolver(config)


def test_lumagen_path_to_display_a() -> None:
    _config, resolver = _lumagen_fixture()
    result = resolver.resolve("za", "src")
    path = result.video_paths[0]
    assert isinstance(path, ResolvedSinglePath)
    assert _hop_devices(path) == ["src", "lumagen", "display_a"]


def test_lumagen_exclusive_output_recorded() -> None:
    _config, resolver = _lumagen_fixture()
    result = resolver.resolve("za", "src")
    assert ("lumagen", "luma_out_a") in result.exclusive_output_usage


def test_lumagen_output_side_contention() -> None:
    """Zone B conflicts with active zone A because lumagen is exclusive_outputs."""
    config, _ = _lumagen_fixture()

    from custom_components.media_room_manager.resolver.path import PathHop, ZoneResolverResult

    hop = PathHop(
        device_id="lumagen",
        entry_interface_id="luma_in",
        exit_interface_id="luma_out_a",
        output_group_id="main",
    )
    path = ResolvedSinglePath(
        carrier="video", source_device_id="src", sink_device_id="display_a", hops=(hop,)
    )
    active_result = ZoneResolverResult(
        zone_id="za",
        source_device_id="src",
        virtual_source_id=None,
        is_virtual_source=False,
        sink_device_ids=("display_a",),
        video_paths=(path,),
        audio_paths=(),
        contentions=(),
        exclusive_output_usage=(("lumagen", "luma_out_a"),),
    )
    reg = ActivePathsRegistry()
    reg.update(active_result)

    resolver = PathResolver(config, reg)
    result = resolver.resolve("zb", "src")
    output_contentions = [c for c in result.contentions if c.kind == "output_side"]
    assert len(output_contentions) > 0
    assert output_contentions[0].conflicting_zone_id == "za"
