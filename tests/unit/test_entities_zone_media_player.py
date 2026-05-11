"""Tests for entities/zone_media_player.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.media_room_manager.adapters.registry import AdapterRegistry
from custom_components.media_room_manager.entities.zone_media_player import (
    ZoneMediaPlayer,
    _find_source_ref,
    _get_source_list,
    _map_ha_state_to_media_player_state,
    compute_supported_features,
)
from custom_components.media_room_manager.graph.model import (
    ControlRole,
    Device,
    DeviceInstance,
    InstanceBinding,
    MechanismKind,
    OutputGroup,
    SelectionMechanism,
    SourceRef,
    SourceVisibilitySelection,
    VirtualSource,
    Zone,
)
from custom_components.media_room_manager.graph.system_config import SystemConfig
from custom_components.media_room_manager.orchestrator.orchestrator import (
    Orchestrator,
    OrchestratorResult,
)
from custom_components.media_room_manager.resolver.path import (
    ActivePathsRegistry,
    PathHop,
    ResolvedSinglePath,
    ZoneResolverResult,
)
from custom_components.media_room_manager.resolver.roles import RoleAssignment

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_hass() -> MagicMock:
    hass = MagicMock()
    hass.services.async_call = AsyncMock()
    hass.states.get = MagicMock(return_value=None)
    hass.bus.async_listen = MagicMock(return_value=MagicMock())
    return hass


def _simple_device(
    device_id: str,
    name: str,
    roles: list[ControlRole],
    mech: bool = True,
) -> Device:
    sm = SelectionMechanism(kind=MechanismKind.MEDIA_PLAYER_SOURCE) if mech else None
    og = OutputGroup(id="main", provides_roles=tuple(roles), selection_mechanism=sm)
    return Device(
        id=device_id,
        name=name,
        profile_id="test/profile",
        output_groups=(og,),
    )


def _simple_binding(device_id: str, og_id: str, entity_reg_id: str) -> DeviceInstance:
    return DeviceInstance(
        device_id=device_id,
        bindings=(
            InstanceBinding(
                output_group_id=og_id,
                entity_registry_id=entity_reg_id,
            ),
        ),
    )


def _simple_zone(zone_id: str, name: str, sink_ids: list[str]) -> Zone:
    return Zone(
        id=zone_id,
        name=name,
        sink_device_ids=tuple(sink_ids),
    )


def _simple_config(
    zones: list[Zone] | None = None,
    devices: list[Device] | None = None,
    device_instances: list[DeviceInstance] | None = None,
    source_visibility: list[SourceVisibilitySelection] | None = None,
) -> SystemConfig:
    return SystemConfig(
        zones=zones or [],
        devices=devices or [],
        device_instances=device_instances or [],
        source_visibility=source_visibility or [],
    )


def _simple_orchestrator(hass: MagicMock, config: SystemConfig) -> Orchestrator:
    return Orchestrator(
        hass,
        config,
        AdapterRegistry(),
        ActivePathsRegistry(),
    )


# ---------------------------------------------------------------------------
# Tests: compute_supported_features
# ---------------------------------------------------------------------------


class TestComputeSupportedFeatures:
    """Tests for the static supported_features computation."""

    def test_transport_role_adds_play_pause_stop(self) -> None:
        """Devices with TRANSPORT role contribute play/pause/stop/next/prev/seek."""
        from homeassistant.components.media_player import MediaPlayerEntityFeature

        device = _simple_device("src", "Source", [ControlRole.TRANSPORT])
        zone = _simple_zone("z1", "Living Room", ["src"])
        config = _simple_config(zones=[zone], devices=[device])

        features = compute_supported_features(zone, config)

        assert features & MediaPlayerEntityFeature.PLAY
        assert features & MediaPlayerEntityFeature.PAUSE
        assert features & MediaPlayerEntityFeature.STOP
        assert features & MediaPlayerEntityFeature.NEXT_TRACK
        assert features & MediaPlayerEntityFeature.PREVIOUS_TRACK
        assert features & MediaPlayerEntityFeature.SEEK

    def test_volume_role_adds_volume_features(self) -> None:
        """Devices with VOLUME role contribute volume_set/step/mute."""
        from homeassistant.components.media_player import MediaPlayerEntityFeature

        device = _simple_device("avr", "AVR", [ControlRole.VOLUME])
        zone = Zone(
            id="z1",
            name="Living Room",
            sink_device_ids=("avr",),
            volume_authority_device_id="avr",
        )
        config = _simple_config(zones=[zone], devices=[device])

        features = compute_supported_features(zone, config)

        assert features & MediaPlayerEntityFeature.VOLUME_SET
        assert features & MediaPlayerEntityFeature.VOLUME_STEP
        assert features & MediaPlayerEntityFeature.VOLUME_MUTE

    def test_metadata_source_role_adds_browse_media(self) -> None:
        """Devices with METADATA_SOURCE role contribute BROWSE_MEDIA."""
        from homeassistant.components.media_player import MediaPlayerEntityFeature

        device = _simple_device("src", "Source", [ControlRole.METADATA_SOURCE])
        zone = _simple_zone("z1", "Living Room", ["src"])
        config = _simple_config(zones=[zone], devices=[device])

        features = compute_supported_features(zone, config)

        assert features & MediaPlayerEntityFeature.BROWSE_MEDIA

    def test_source_selection_with_mechanism_adds_select_source(self) -> None:
        """Devices with SOURCE_SELECTION role and mechanism contribute SELECT_SOURCE."""
        from homeassistant.components.media_player import MediaPlayerEntityFeature

        device = _simple_device("avr", "AVR", [ControlRole.SOURCE_SELECTION])
        zone = _simple_zone("z1", "Living Room", ["avr"])
        config = _simple_config(zones=[zone], devices=[device])

        features = compute_supported_features(zone, config)

        assert features & MediaPlayerEntityFeature.SELECT_SOURCE

    def test_visible_sources_adds_select_source(self) -> None:
        """Zones with visible sources in config always get SELECT_SOURCE."""
        from homeassistant.components.media_player import MediaPlayerEntityFeature

        device = _simple_device("src", "Source", [])  # no roles
        zone = _simple_zone("z1", "Living Room", ["src"])
        svs = SourceVisibilitySelection(
            zone_id="z1",
            visible_sources=(SourceRef(device_id="src"),),
        )
        config = _simple_config(zones=[zone], devices=[device], source_visibility=[svs])

        features = compute_supported_features(zone, config)

        assert features & MediaPlayerEntityFeature.SELECT_SOURCE

    def test_empty_zone_has_no_features(self) -> None:
        """A zone with no devices and no source visibility has zero features."""
        from homeassistant.components.media_player import MediaPlayerEntityFeature

        zone = _simple_zone("z1", "Empty Zone", [])
        config = _simple_config(zones=[zone])

        features = compute_supported_features(zone, config)

        assert features == MediaPlayerEntityFeature(0)

    def test_union_of_multiple_devices(self) -> None:
        """Union of features across multiple devices."""
        from homeassistant.components.media_player import MediaPlayerEntityFeature

        src = _simple_device("src", "Source", [ControlRole.TRANSPORT, ControlRole.METADATA_SOURCE])
        avr = _simple_device("avr", "AVR", [ControlRole.VOLUME])
        zone = Zone(
            id="z1",
            name="Living Room",
            sink_device_ids=("avr",),
            volume_authority_device_id="avr",
        )
        config = _simple_config(zones=[zone], devices=[src, avr])

        features = compute_supported_features(zone, config)

        assert features & MediaPlayerEntityFeature.PLAY
        assert features & MediaPlayerEntityFeature.VOLUME_SET
        assert features & MediaPlayerEntityFeature.BROWSE_MEDIA


# ---------------------------------------------------------------------------
# Tests: _get_source_list
# ---------------------------------------------------------------------------


class TestGetSourceList:
    """Tests for source list building from source visibility config."""

    def test_empty_when_no_source_visibility(self) -> None:
        """Returns empty list when zone has no source visibility selection."""
        zone = _simple_zone("z1", "Living Room", [])
        config = _simple_config(zones=[zone])

        result = _get_source_list(zone, config)

        assert result == []

    def test_uses_display_name_when_set(self) -> None:
        """Uses the display_name from SourceRef when provided."""
        zone = _simple_zone("z1", "Living Room", ["src"])
        svs = SourceVisibilitySelection(
            zone_id="z1",
            visible_sources=(SourceRef(device_id="src", display_name="Apple TV"),),
        )
        config = _simple_config(zones=[zone], source_visibility=[svs])

        result = _get_source_list(zone, config)

        assert result == ["Apple TV"]

    def test_uses_device_name_as_fallback(self) -> None:
        """Falls back to device.name when no display_name is set."""
        device = _simple_device("src", "Apple TV 4K", [])
        zone = _simple_zone("z1", "Living Room", ["src"])
        svs = SourceVisibilitySelection(
            zone_id="z1",
            visible_sources=(SourceRef(device_id="src"),),
        )
        config = _simple_config(zones=[zone], devices=[device], source_visibility=[svs])

        result = _get_source_list(zone, config)

        assert result == ["Apple TV 4K"]

    def test_uses_virtual_source_label(self) -> None:
        """Uses virtual source label for virtual source refs."""

        vs = VirtualSource(id="tuner", label="Tuner FM", routable_to_output_group=("main",))
        device = Device(
            id="avr",
            name="AVR",
            profile_id="test",
            virtual_sources=(vs,),
        )
        zone = _simple_zone("z1", "Living Room", ["avr"])
        svs = SourceVisibilitySelection(
            zone_id="z1",
            visible_sources=(SourceRef(device_id="avr", virtual_source_id="tuner"),),
        )
        config = _simple_config(zones=[zone], devices=[device], source_visibility=[svs])

        result = _get_source_list(zone, config)

        assert result == ["Tuner FM"]

    def test_multiple_sources_ordered(self) -> None:
        """Returns sources in the order defined in visible_sources."""
        d1 = _simple_device("src1", "Apple TV", [])
        d2 = _simple_device("src2", "PS5", [])
        zone = _simple_zone("z1", "Living Room", ["avr"])
        svs = SourceVisibilitySelection(
            zone_id="z1",
            visible_sources=(
                SourceRef(device_id="src1"),
                SourceRef(device_id="src2"),
            ),
        )
        config = _simple_config(zones=[zone], devices=[d1, d2], source_visibility=[svs])

        result = _get_source_list(zone, config)

        assert result == ["Apple TV", "PS5"]


# ---------------------------------------------------------------------------
# Tests: _find_source_ref
# ---------------------------------------------------------------------------


class TestFindSourceRef:
    """Tests for source ref lookup by display name."""

    def test_finds_by_display_name(self) -> None:
        """Returns SourceRef matching the given display name."""
        zone = _simple_zone("z1", "Living Room", ["src"])
        ref = SourceRef(device_id="src", display_name="Apple TV")
        svs = SourceVisibilitySelection(zone_id="z1", visible_sources=(ref,))
        config = _simple_config(zones=[zone], source_visibility=[svs])

        result = _find_source_ref("Apple TV", zone, config)

        assert result is not None
        assert result.device_id == "src"

    def test_returns_none_for_unknown_name(self) -> None:
        """Returns None when the display name is not found."""
        zone = _simple_zone("z1", "Living Room", ["src"])
        ref = SourceRef(device_id="src", display_name="Apple TV")
        svs = SourceVisibilitySelection(zone_id="z1", visible_sources=(ref,))
        config = _simple_config(zones=[zone], source_visibility=[svs])

        result = _find_source_ref("PS5", zone, config)

        assert result is None

    def test_finds_by_device_name_fallback(self) -> None:
        """Returns SourceRef matching the device name when no display_name is set."""
        device = _simple_device("src", "Apple TV 4K", [])
        zone = _simple_zone("z1", "Living Room", ["src"])
        ref = SourceRef(device_id="src")  # no display_name
        svs = SourceVisibilitySelection(zone_id="z1", visible_sources=(ref,))
        config = _simple_config(zones=[zone], devices=[device], source_visibility=[svs])

        result = _find_source_ref("Apple TV 4K", zone, config)

        assert result is not None
        assert result.device_id == "src"


# ---------------------------------------------------------------------------
# Tests: _map_ha_state_to_media_player_state
# ---------------------------------------------------------------------------


class TestMapHaState:
    """Tests for HA state string → MediaPlayerState mapping."""

    def test_playing(self) -> None:
        """'playing' maps to PLAYING."""
        from homeassistant.components.media_player.const import MediaPlayerState

        assert _map_ha_state_to_media_player_state("playing") == MediaPlayerState.PLAYING

    def test_paused(self) -> None:
        """'paused' maps to PAUSED."""
        from homeassistant.components.media_player.const import MediaPlayerState

        assert _map_ha_state_to_media_player_state("paused") == MediaPlayerState.PAUSED

    def test_idle(self) -> None:
        """'idle' maps to IDLE."""
        from homeassistant.components.media_player.const import MediaPlayerState

        assert _map_ha_state_to_media_player_state("idle") == MediaPlayerState.IDLE

    def test_off(self) -> None:
        """'off' maps to OFF."""
        from homeassistant.components.media_player.const import MediaPlayerState

        assert _map_ha_state_to_media_player_state("off") == MediaPlayerState.OFF

    def test_unknown_state_maps_to_idle(self) -> None:
        """Unknown states map to IDLE as a safe default."""
        from homeassistant.components.media_player.const import MediaPlayerState

        assert _map_ha_state_to_media_player_state("unknown_xyz") == MediaPlayerState.IDLE


# ---------------------------------------------------------------------------
# Tests: ZoneMediaPlayer construction and properties
# ---------------------------------------------------------------------------


class TestZoneMediaPlayerConstruction:
    """Tests for ZoneMediaPlayer initialization."""

    def test_unique_id(self) -> None:
        """unique_id is based on zone id."""
        hass = _make_hass()
        zone = _simple_zone("living_room", "Living Room", [])
        config = _simple_config(zones=[zone])
        orch = _simple_orchestrator(hass, config)
        active = ActivePathsRegistry()

        player = ZoneMediaPlayer(hass, zone, config, orch, active, AdapterRegistry())

        assert player.unique_id == "mrm_zone_living_room"

    def test_name(self) -> None:
        """name equals zone.name."""
        hass = _make_hass()
        zone = _simple_zone("z1", "Theater Room", [])
        config = _simple_config(zones=[zone])
        orch = _simple_orchestrator(hass, config)
        active = ActivePathsRegistry()

        player = ZoneMediaPlayer(hass, zone, config, orch, active, AdapterRegistry())

        assert player.name == "Theater Room"

    def test_should_poll_false(self) -> None:
        """should_poll is False (push-based updates)."""
        hass = _make_hass()
        zone = _simple_zone("z1", "Room", [])
        config = _simple_config(zones=[zone])
        orch = _simple_orchestrator(hass, config)
        active = ActivePathsRegistry()

        player = ZoneMediaPlayer(hass, zone, config, orch, active, AdapterRegistry())

        assert player.should_poll is False

    def test_supported_features_computed(self) -> None:
        """supported_features is computed from config at construction."""
        from homeassistant.components.media_player import MediaPlayerEntityFeature

        hass = _make_hass()
        device = _simple_device("src", "Source", [ControlRole.TRANSPORT])
        zone = _simple_zone("z1", "Room", ["src"])
        config = _simple_config(zones=[zone], devices=[device])
        orch = _simple_orchestrator(hass, config)
        active = ActivePathsRegistry()

        player = ZoneMediaPlayer(hass, zone, config, orch, active, AdapterRegistry())

        assert player.supported_features & MediaPlayerEntityFeature.PLAY

    def test_device_info_identifiers(self) -> None:
        """device_info uses zone domain identifier."""
        from custom_components.media_room_manager.const import DOMAIN

        hass = _make_hass()
        zone = _simple_zone("z1", "Room", [])
        config = _simple_config(zones=[zone])
        orch = _simple_orchestrator(hass, config)
        active = ActivePathsRegistry()

        player = ZoneMediaPlayer(hass, zone, config, orch, active, AdapterRegistry())

        assert (DOMAIN, "zone_z1") in player.device_info["identifiers"]


# ---------------------------------------------------------------------------
# Tests: ZoneMediaPlayer state
# ---------------------------------------------------------------------------


class TestZoneMediaPlayerState:
    """Tests for state computation."""

    def test_state_off_when_no_active_path(self) -> None:
        """State is OFF when the zone has no active path."""
        from homeassistant.components.media_player.const import MediaPlayerState

        hass = _make_hass()
        zone = _simple_zone("z1", "Room", [])
        config = _simple_config(zones=[zone])
        orch = _simple_orchestrator(hass, config)
        active = ActivePathsRegistry()

        player = ZoneMediaPlayer(hass, zone, config, orch, active, AdapterRegistry())

        assert player.state == MediaPlayerState.OFF

    def test_state_idle_when_path_active_no_metadata_entity(self) -> None:
        """State is IDLE when path is active but no metadata entity is available."""
        from homeassistant.components.media_player.const import MediaPlayerState

        from custom_components.media_room_manager.resolver.path import (
            ZoneResolverResult,
        )

        hass = _make_hass()
        zone = _simple_zone("z1", "Room", ["src"])
        config = _simple_config(zones=[zone])
        orch = _simple_orchestrator(hass, config)
        active = ActivePathsRegistry()

        # Insert a minimal active path.
        result = ZoneResolverResult(
            zone_id="z1",
            source_device_id="src",
            virtual_source_id=None,
            is_virtual_source=False,
            sink_device_ids=("src",),
            video_paths=(),
            audio_paths=(),
            contentions=(),
            exclusive_output_usage=(),
        )
        active.update(result)

        player = ZoneMediaPlayer(hass, zone, config, orch, active, AdapterRegistry())

        assert player.state == MediaPlayerState.IDLE

    def test_state_from_metadata_entity(self) -> None:
        """State mirrors the metadata source entity's state."""
        from unittest.mock import MagicMock

        from homeassistant.components.media_player.const import MediaPlayerState

        from custom_components.media_room_manager.resolver.path import (
            ZoneResolverResult,
        )

        hass = _make_hass()
        mock_state = MagicMock()
        mock_state.state = "playing"
        hass.states.get = MagicMock(return_value=mock_state)

        zone = _simple_zone("z1", "Room", ["src"])
        config = _simple_config(zones=[zone])
        orch = _simple_orchestrator(hass, config)
        active = ActivePathsRegistry()

        result = ZoneResolverResult(
            zone_id="z1",
            source_device_id="src",
            virtual_source_id=None,
            is_virtual_source=False,
            sink_device_ids=("src",),
            video_paths=(),
            audio_paths=(),
            contentions=(),
            exclusive_output_usage=(),
        )
        active.update(result)

        player = ZoneMediaPlayer(hass, zone, config, orch, active, AdapterRegistry())
        # Inject a metadata entity id as if a subscription was set up.
        player._metadata_entity_id = "media_player.apple_tv"

        assert player.state == MediaPlayerState.PLAYING

    def test_available_false_on_error(self) -> None:
        """available is False when error_detail is set."""
        hass = _make_hass()
        zone = _simple_zone("z1", "Room", [])
        config = _simple_config(zones=[zone])
        orch = _simple_orchestrator(hass, config)
        active = ActivePathsRegistry()

        player = ZoneMediaPlayer(hass, zone, config, orch, active, AdapterRegistry())
        player._error_detail = "Test error"

        assert player.available is False

    def test_available_true_normally(self) -> None:
        """available is True in normal (non-error) state."""
        hass = _make_hass()
        zone = _simple_zone("z1", "Room", [])
        config = _simple_config(zones=[zone])
        orch = _simple_orchestrator(hass, config)
        active = ActivePathsRegistry()

        player = ZoneMediaPlayer(hass, zone, config, orch, active, AdapterRegistry())

        assert player.available is True

    def test_error_detail_in_extra_attributes(self) -> None:
        """error_detail appears in extra_state_attributes when set."""
        hass = _make_hass()
        zone = _simple_zone("z1", "Room", [])
        config = _simple_config(zones=[zone])
        orch = _simple_orchestrator(hass, config)
        active = ActivePathsRegistry()

        player = ZoneMediaPlayer(hass, zone, config, orch, active, AdapterRegistry())
        player._error_detail = "Path resolution failed"

        attrs = player.extra_state_attributes
        assert attrs.get("error_detail") == "Path resolution failed"

    def test_no_error_detail_when_no_error(self) -> None:
        """error_detail is absent from extra attributes when no error."""
        hass = _make_hass()
        zone = _simple_zone("z1", "Room", [])
        config = _simple_config(zones=[zone])
        orch = _simple_orchestrator(hass, config)
        active = ActivePathsRegistry()

        player = ZoneMediaPlayer(hass, zone, config, orch, active, AdapterRegistry())

        attrs = player.extra_state_attributes
        assert "error_detail" not in attrs


# ---------------------------------------------------------------------------
# Tests: ZoneMediaPlayer source list and select_source
# ---------------------------------------------------------------------------


class TestZoneMediaPlayerSources:
    """Tests for source list and source selection."""

    def test_source_list_returns_configured_sources(self) -> None:
        """source_list returns the visible sources for the zone."""
        hass = _make_hass()
        device = _simple_device("src", "Apple TV", [])
        zone = _simple_zone("z1", "Room", ["src"])
        svs = SourceVisibilitySelection(
            zone_id="z1",
            visible_sources=(SourceRef(device_id="src", display_name="Apple TV"),),
        )
        config = _simple_config(zones=[zone], devices=[device], source_visibility=[svs])
        orch = _simple_orchestrator(hass, config)
        active = ActivePathsRegistry()

        player = ZoneMediaPlayer(hass, zone, config, orch, active, AdapterRegistry())

        assert player.source_list == ["Apple TV"]

    @pytest.mark.asyncio
    async def test_select_source_calls_orchestrator(self) -> None:
        """select_source triggers orchestrator.async_activate_zone."""
        hass = _make_hass()
        device = _simple_device("src", "Apple TV", [])
        zone = _simple_zone("z1", "Room", ["src"])
        svs = SourceVisibilitySelection(
            zone_id="z1",
            visible_sources=(SourceRef(device_id="src", display_name="Apple TV"),),
        )
        config = _simple_config(zones=[zone], devices=[device], source_visibility=[svs])
        orch = _simple_orchestrator(hass, config)
        orch.async_activate_zone = AsyncMock(
            return_value=OrchestratorResult(success=True, zone_id="z1")
        )
        active = ActivePathsRegistry()

        player = ZoneMediaPlayer(hass, zone, config, orch, active, AdapterRegistry())
        player.async_write_ha_state = MagicMock()

        await player.async_select_source("Apple TV")

        orch.async_activate_zone.assert_awaited_once_with("z1", "src", virtual_source_id=None)

    @pytest.mark.asyncio
    async def test_select_source_unknown_source_logs_warning(self) -> None:
        """Selecting an unknown source logs a warning and does nothing."""
        hass = _make_hass()
        zone = _simple_zone("z1", "Room", [])
        config = _simple_config(zones=[zone])
        orch = _simple_orchestrator(hass, config)
        orch.async_activate_zone = AsyncMock()
        active = ActivePathsRegistry()

        player = ZoneMediaPlayer(hass, zone, config, orch, active, AdapterRegistry())
        player.async_write_ha_state = MagicMock()

        await player.async_select_source("Unknown Source")

        orch.async_activate_zone.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_select_source_sets_error_on_failure(self) -> None:
        """select_source sets error_detail when orchestrator fails."""
        hass = _make_hass()
        device = _simple_device("src", "Apple TV", [])
        zone = _simple_zone("z1", "Room", ["src"])
        svs = SourceVisibilitySelection(
            zone_id="z1",
            visible_sources=(SourceRef(device_id="src", display_name="Apple TV"),),
        )
        config = _simple_config(zones=[zone], devices=[device], source_visibility=[svs])
        orch = _simple_orchestrator(hass, config)
        orch.async_activate_zone = AsyncMock(
            return_value=OrchestratorResult(
                success=False, zone_id="z1", error_detail="Path not found"
            )
        )
        active = ActivePathsRegistry()

        player = ZoneMediaPlayer(hass, zone, config, orch, active, AdapterRegistry())
        player.async_write_ha_state = MagicMock()

        await player.async_select_source("Apple TV")

        assert player._error_detail == "Path not found"


# ---------------------------------------------------------------------------
# Tests: ZoneMediaPlayer transport commands
# ---------------------------------------------------------------------------


class TestZoneMediaPlayerTransport:
    """Tests for transport command pass-through."""

    def _make_player_with_active_path(self, hass: MagicMock) -> tuple[ZoneMediaPlayer, MagicMock]:
        """Helper: build a player with an active path and mock adapter."""
        device = _simple_device(
            "src", "Apple TV", [ControlRole.TRANSPORT, ControlRole.METADATA_SOURCE]
        )
        zone = Zone(
            id="z1",
            name="Room",
            sink_device_ids=("src",),
            volume_authority_device_id=None,
        )
        binding = _simple_binding("src", "main", "reg-001")
        config = _simple_config(zones=[zone], devices=[device], device_instances=[binding])

        hop = PathHop(
            device_id="src",
            entry_interface_id=None,
            exit_interface_id=None,
            output_group_id="main",
        )
        path = ResolvedSinglePath(
            carrier="video",
            source_device_id="src",
            sink_device_id="src",
            hops=(hop,),
        )
        result = ZoneResolverResult(
            zone_id="z1",
            source_device_id="src",
            virtual_source_id=None,
            is_virtual_source=False,
            sink_device_ids=("src",),
            video_paths=(path,),
            audio_paths=(),
            contentions=(),
            exclusive_output_usage=(),
        )
        active = ActivePathsRegistry()
        active.update(result)

        orch = _simple_orchestrator(hass, config)
        adapter_reg = AdapterRegistry()
        player = ZoneMediaPlayer(hass, zone, config, orch, active, adapter_reg)

        # Patch entity registry resolution to return a known entity_id.
        mock_entity_id = "media_player.apple_tv"

        def _resolver(reg_id: str) -> str | None:
            return mock_entity_id if reg_id == "reg-001" else None

        with patch(
            "custom_components.media_room_manager.entities.zone_media_player."
            "_resolve_entity_id_from_registry",
            side_effect=_resolver,
        ):
            return player, adapter_reg

    @pytest.mark.asyncio
    async def test_media_play_routes_to_transport(self) -> None:
        """async_media_play sends 'play' transport command to the transport role holder."""
        hass = _make_hass()
        device = _simple_device("src", "Apple TV", [ControlRole.TRANSPORT])
        zone = _simple_zone("z1", "Room", ["src"])
        binding = _simple_binding("src", "main", "reg-001")
        hop = PathHop("src", None, None, "main")
        path = ResolvedSinglePath("video", "src", "src", (hop,))
        result = ZoneResolverResult(
            zone_id="z1",
            source_device_id="src",
            virtual_source_id=None,
            is_virtual_source=False,
            sink_device_ids=("src",),
            video_paths=(path,),
            audio_paths=(),
            contentions=(),
            exclusive_output_usage=(),
        )
        active = ActivePathsRegistry()
        active.update(result)

        config = _simple_config(zones=[zone], devices=[device], device_instances=[binding])
        orch = _simple_orchestrator(hass, config)
        adapter_reg = AdapterRegistry()
        mock_adapter = MagicMock()
        mock_adapter.async_send_transport = AsyncMock()
        adapter_reg._adapters["media_player_source"] = mock_adapter

        player = ZoneMediaPlayer(hass, zone, config, orch, active, adapter_reg)

        with patch(
            "custom_components.media_room_manager.entities.zone_media_player."
            "_resolve_entity_id_from_registry",
            return_value="media_player.apple_tv",
        ):
            await player.async_media_play()

        mock_adapter.async_send_transport.assert_awaited_once_with(
            hass, "media_player.apple_tv", "play", position=None
        )

    @pytest.mark.asyncio
    async def test_transport_no_op_when_no_active_path(self) -> None:
        """Transport commands are no-ops when no path is active."""
        hass = _make_hass()
        device = _simple_device("src", "Apple TV", [ControlRole.TRANSPORT])
        zone = _simple_zone("z1", "Room", ["src"])
        config = _simple_config(zones=[zone], devices=[device])
        orch = _simple_orchestrator(hass, config)
        active = ActivePathsRegistry()

        adapter_reg = AdapterRegistry()
        mock_adapter = MagicMock()
        mock_adapter.async_send_transport = AsyncMock()
        adapter_reg._adapters["media_player_source"] = mock_adapter

        player = ZoneMediaPlayer(hass, zone, config, orch, active, adapter_reg)

        await player.async_media_play()

        mock_adapter.async_send_transport.assert_not_awaited()


# ---------------------------------------------------------------------------
# Tests: ZoneMediaPlayer volume commands
# ---------------------------------------------------------------------------


class TestZoneMediaPlayerVolume:
    """Tests for volume command pass-through."""

    @pytest.mark.asyncio
    async def test_set_volume_calls_adapter(self) -> None:
        """async_set_volume_level calls adapter.async_set_volume on volume authority."""
        hass = _make_hass()
        device = _simple_device("avr", "AVR", [ControlRole.VOLUME])
        zone = Zone(
            id="z1",
            name="Room",
            sink_device_ids=("avr",),
            volume_authority_device_id="avr",
            volume_authority_output_group_id="main",
        )
        binding = _simple_binding("avr", "main", "reg-avr")
        config = _simple_config(zones=[zone], devices=[device], device_instances=[binding])
        orch = _simple_orchestrator(hass, config)
        active = ActivePathsRegistry()

        adapter_reg = AdapterRegistry()
        mock_adapter = MagicMock()
        mock_adapter.async_set_volume = AsyncMock()
        adapter_reg._adapters["media_player_source"] = mock_adapter

        player = ZoneMediaPlayer(hass, zone, config, orch, active, adapter_reg)

        with patch(
            "custom_components.media_room_manager.entities.zone_media_player."
            "_resolve_entity_id_from_registry",
            return_value="media_player.avr",
        ):
            await player.async_set_volume_level(0.5)

        mock_adapter.async_set_volume.assert_awaited_once_with(hass, "media_player.avr", 0.5)

    @pytest.mark.asyncio
    async def test_volume_no_op_when_no_authority(self) -> None:
        """Volume commands are no-ops when no volume authority is configured."""
        hass = _make_hass()
        zone = _simple_zone("z1", "Room", [])
        config = _simple_config(zones=[zone])
        orch = _simple_orchestrator(hass, config)
        active = ActivePathsRegistry()

        adapter_reg = AdapterRegistry()
        mock_adapter = MagicMock()
        mock_adapter.async_set_volume = AsyncMock()
        adapter_reg._adapters["media_player_source"] = mock_adapter

        player = ZoneMediaPlayer(hass, zone, config, orch, active, adapter_reg)

        await player.async_set_volume_level(0.5)

        mock_adapter.async_set_volume.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_volume_up_calls_adapter(self) -> None:
        """async_volume_up calls adapter.async_volume_up."""
        hass = _make_hass()
        device = _simple_device("avr", "AVR", [ControlRole.VOLUME])
        zone = Zone(
            id="z1",
            name="Room",
            sink_device_ids=("avr",),
            volume_authority_device_id="avr",
            volume_authority_output_group_id="main",
        )
        binding = _simple_binding("avr", "main", "reg-avr")
        config = _simple_config(zones=[zone], devices=[device], device_instances=[binding])
        orch = _simple_orchestrator(hass, config)
        active = ActivePathsRegistry()

        adapter_reg = AdapterRegistry()
        mock_adapter = MagicMock()
        mock_adapter.async_volume_up = AsyncMock()
        adapter_reg._adapters["media_player_source"] = mock_adapter

        player = ZoneMediaPlayer(hass, zone, config, orch, active, adapter_reg)

        with patch(
            "custom_components.media_room_manager.entities.zone_media_player."
            "_resolve_entity_id_from_registry",
            return_value="media_player.avr",
        ):
            await player.async_volume_up()

        mock_adapter.async_volume_up.assert_awaited_once_with(hass, "media_player.avr")

    @pytest.mark.asyncio
    async def test_mute_calls_adapter(self) -> None:
        """async_mute_volume calls adapter.async_mute."""
        hass = _make_hass()
        device = _simple_device("avr", "AVR", [ControlRole.VOLUME])
        zone = Zone(
            id="z1",
            name="Room",
            sink_device_ids=("avr",),
            volume_authority_device_id="avr",
            volume_authority_output_group_id="main",
        )
        binding = _simple_binding("avr", "main", "reg-avr")
        config = _simple_config(zones=[zone], devices=[device], device_instances=[binding])
        orch = _simple_orchestrator(hass, config)
        active = ActivePathsRegistry()

        adapter_reg = AdapterRegistry()
        mock_adapter = MagicMock()
        mock_adapter.async_mute = AsyncMock()
        adapter_reg._adapters["media_player_source"] = mock_adapter

        player = ZoneMediaPlayer(hass, zone, config, orch, active, adapter_reg)

        with patch(
            "custom_components.media_room_manager.entities.zone_media_player."
            "_resolve_entity_id_from_registry",
            return_value="media_player.avr",
        ):
            await player.async_mute_volume(True)

        mock_adapter.async_mute.assert_awaited_once_with(hass, "media_player.avr", True)


# ---------------------------------------------------------------------------
# Tests: ZoneMediaPlayer metadata pass-through
# ---------------------------------------------------------------------------


class TestZoneMediaPlayerMetadata:
    """Tests for metadata attribute mirroring."""

    def test_metadata_attributes_initially_none(self) -> None:
        """Metadata attributes are None before any subscription fires."""
        hass = _make_hass()
        zone = _simple_zone("z1", "Room", [])
        config = _simple_config(zones=[zone])
        orch = _simple_orchestrator(hass, config)
        active = ActivePathsRegistry()

        player = ZoneMediaPlayer(hass, zone, config, orch, active, AdapterRegistry())

        assert player.media_title is None
        assert player.media_artist is None
        assert player.media_album_name is None
        assert player.media_image_url is None

    def test_update_metadata_from_state(self) -> None:
        """_update_metadata_from_state populates metadata from HA state attributes."""
        from unittest.mock import MagicMock

        hass = _make_hass()
        zone = _simple_zone("z1", "Room", [])
        config = _simple_config(zones=[zone])
        orch = _simple_orchestrator(hass, config)
        active = ActivePathsRegistry()

        player = ZoneMediaPlayer(hass, zone, config, orch, active, AdapterRegistry())

        mock_state = MagicMock()
        mock_state.attributes = {
            "media_title": "Test Song",
            "media_artist": "Test Artist",
            "media_album_name": "Test Album",
            "media_image_url": "http://example.com/image.jpg",
        }
        player._update_metadata_from_state(mock_state)

        assert player.media_title == "Test Song"
        assert player.media_artist == "Test Artist"
        assert player.media_album_name == "Test Album"
        assert player.media_image_url == "http://example.com/image.jpg"

    def test_update_metadata_clears_absent_attributes(self) -> None:
        """Metadata attrs are cleared when absent from state attributes."""
        from unittest.mock import MagicMock

        hass = _make_hass()
        zone = _simple_zone("z1", "Room", [])
        config = _simple_config(zones=[zone])
        orch = _simple_orchestrator(hass, config)
        active = ActivePathsRegistry()

        player = ZoneMediaPlayer(hass, zone, config, orch, active, AdapterRegistry())
        # Pre-populate.
        player._metadata["media_title"] = "Old Song"

        # State with no media_title.
        mock_state = MagicMock()
        mock_state.attributes = {"media_artist": "New Artist"}
        player._update_metadata_from_state(mock_state)

        assert player.media_title is None
        assert player.media_artist == "New Artist"

    @pytest.mark.asyncio
    async def test_metadata_subscription_updates_state(self) -> None:
        """When metadata_source state changes, entity state is updated."""
        from unittest.mock import MagicMock

        hass = _make_hass()
        zone = _simple_zone("z1", "Room", [])
        config = _simple_config(zones=[zone])
        orch = _simple_orchestrator(hass, config)
        active = ActivePathsRegistry()

        player = ZoneMediaPlayer(hass, zone, config, orch, active, AdapterRegistry())
        player.async_write_ha_state = MagicMock()

        role = RoleAssignment(
            volume_device_id=None,
            volume_output_group_id=None,
            transport_device_id=None,
            transport_output_group_id=None,
            metadata_source_device_id="src",
            metadata_source_output_group_id="main",
        )

        device = _simple_device("src", "Source", [ControlRole.METADATA_SOURCE])
        binding = _simple_binding("src", "main", "reg-001")
        player._config = _simple_config(
            zones=[zone],
            devices=[device],
            device_instances=[binding],
        )

        initial_state = MagicMock()
        initial_state.attributes = {}
        hass.states.get = MagicMock(return_value=initial_state)

        with patch(
            "custom_components.media_room_manager.entities.zone_media_player."
            "_resolve_entity_id_from_registry",
            return_value="media_player.source",
        ):
            await player._async_update_metadata_subscription(role)

        assert player._metadata_entity_id == "media_player.source"
        assert hass.bus.async_listen.called
