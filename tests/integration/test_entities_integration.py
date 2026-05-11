"""Integration test for Phase 6 entities.

Configures a multi-zone system:
- Zone 1: "Living Room" — single sink (TV), volume authority = AVR
  Source: Apple TV (physical)
- Zone 2: "Theater" — selectable_exclusive (TV + Projector), volume authority = AVR
  Source: Apple TV (physical)
- Shared device: AVR (reachable from both zones → binary_sensor created)

Verifies:
- All expected entities are constructed with correct unique_ids.
- source_list is correctly populated from source_visibility.
- supported_features computation includes the right bits.
- select_source triggers orchestrator.async_activate_zone.
- transport commands route to the correct role holder.
- volume commands route to the volume authority.
- binary_sensor reflects shared device usage in active paths.
- selectable_exclusive select + switch entities exist with correct names.
- DeviceInfo identifiers are correct.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.media_room_manager.adapters.registry import AdapterRegistry
from custom_components.media_room_manager.const import DOMAIN
from custom_components.media_room_manager.entities.device_in_use import (
    DeviceInUseBinarySensor,
)
from custom_components.media_room_manager.entities.selectable_exclusive import (
    SelectableExclusiveSelect,
    SelectableExclusiveSwitch,
)
from custom_components.media_room_manager.entities.zone_media_player import (
    ZoneMediaPlayer,
)
from custom_components.media_room_manager.graph.model import (
    Connection,
    ControlRole,
    Device,
    DeviceInstance,
    InstanceBinding,
    Interface,
    InterfaceDirection,
    InterfaceType,
    MechanismKind,
    OutputGroup,
    PowerHandling,
    SelectionMechanism,
    SinkMode,
    SourceRef,
    SourceVisibilitySelection,
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

# ---------------------------------------------------------------------------
# Fixtures — build the multi-zone test system
# ---------------------------------------------------------------------------


def _make_hass() -> MagicMock:
    hass = MagicMock()
    hass.services.async_call = AsyncMock()
    hass.states.get = MagicMock(return_value=None)
    hass.bus.async_listen = MagicMock(return_value=MagicMock())
    return hass


def _build_system() -> tuple[SystemConfig, ActivePathsRegistry, AdapterRegistry]:
    """Build a multi-zone AV system for integration testing."""
    # Devices
    apple_tv = Device(
        id="apple_tv",
        name="Apple TV 4K",
        profile_id="apple/apple-tv-4k",
        power_handling=PowerHandling.DISCRETE_CAPABLE,
        output_groups=(
            OutputGroup(
                id="main",
                provides_roles=(ControlRole.TRANSPORT, ControlRole.METADATA_SOURCE),
                selection_mechanism=SelectionMechanism(kind=MechanismKind.MEDIA_PLAYER_SOURCE),
            ),
        ),
        interfaces=(
            Interface(
                id="hdmi_out",
                direction=InterfaceDirection.OUTPUT,
                type=InterfaceType.HDMI,
                label="HDMI OUT",
                output_group="main",
            ),
        ),
    )

    avr = Device(
        id="avr",
        name="Marantz AVR",
        profile_id="marantz/sr8015",
        power_handling=PowerHandling.DISCRETE_CAPABLE,
        output_groups=(
            OutputGroup(
                id="main",
                provides_roles=(ControlRole.VOLUME, ControlRole.SOURCE_SELECTION),
                selection_mechanism=SelectionMechanism(kind=MechanismKind.MEDIA_PLAYER_SOURCE),
            ),
        ),
        interfaces=(
            Interface(
                id="hdmi_1",
                direction=InterfaceDirection.INPUT,
                type=InterfaceType.HDMI,
                label="HDMI 1",
                routable_to_output_group=("main",),
            ),
            Interface(
                id="hdmi_main_out",
                direction=InterfaceDirection.OUTPUT,
                type=InterfaceType.HDMI,
                label="HDMI MAIN OUT",
                output_group="main",
            ),
        ),
    )

    tv = Device(
        id="tv",
        name="Sony TV",
        profile_id="sony/tv",
        power_handling=PowerHandling.DISCRETE_CAPABLE,
        output_groups=(
            OutputGroup(
                id="main",
                provides_roles=(),
                selection_mechanism=SelectionMechanism(kind=MechanismKind.MEDIA_PLAYER_SOURCE),
            ),
        ),
        interfaces=(
            Interface(
                id="hdmi_in_1",
                direction=InterfaceDirection.INPUT,
                type=InterfaceType.HDMI,
                label="HDMI 1",
                routable_to_output_group=("main",),
            ),
        ),
    )

    projector = Device(
        id="projector",
        name="JVC Projector",
        profile_id="jvc/nz9",
        power_handling=PowerHandling.DISCRETE_CAPABLE,
        output_groups=(
            OutputGroup(
                id="main",
                provides_roles=(),
                selection_mechanism=SelectionMechanism(kind=MechanismKind.MEDIA_PLAYER_SOURCE),
            ),
        ),
        interfaces=(
            Interface(
                id="hdmi_in_1",
                direction=InterfaceDirection.INPUT,
                type=InterfaceType.HDMI,
                label="HDMI 1",
                routable_to_output_group=("main",),
            ),
        ),
    )

    # Connections: Apple TV → AVR → TV; AVR → Projector also
    connections = [
        Connection(
            id="atv_avr",
            from_device_id="apple_tv",
            from_interface_id="hdmi_out",
            to_device_id="avr",
            to_interface_id="hdmi_1",
        ),
        Connection(
            id="avr_tv",
            from_device_id="avr",
            from_interface_id="hdmi_main_out",
            to_device_id="tv",
            to_interface_id="hdmi_in_1",
        ),
    ]

    # Zones
    living_room = Zone(
        id="living_room",
        name="Living Room",
        sink_device_ids=("tv",),
        sink_mode=SinkMode.SINGLE,
        volume_authority_device_id="avr",
        volume_authority_output_group_id="main",
    )

    theater = Zone(
        id="theater",
        name="Theater",
        sink_device_ids=("tv", "projector"),
        sink_mode=SinkMode.SELECTABLE_EXCLUSIVE,
        volume_authority_device_id="avr",
        volume_authority_output_group_id="main",
        default_sink_device_id="tv",
    )

    # Source visibility
    sv_living_room = SourceVisibilitySelection(
        zone_id="living_room",
        visible_sources=(SourceRef(device_id="apple_tv", display_name="Apple TV"),),
    )
    sv_theater = SourceVisibilitySelection(
        zone_id="theater",
        visible_sources=(SourceRef(device_id="apple_tv", display_name="Apple TV"),),
    )

    # Device instances (entity bindings)
    device_instances = [
        DeviceInstance(
            device_id="apple_tv",
            bindings=(
                InstanceBinding(
                    output_group_id="main",
                    entity_registry_id="reg-apple-tv",
                ),
            ),
        ),
        DeviceInstance(
            device_id="avr",
            bindings=(
                InstanceBinding(
                    output_group_id="main",
                    entity_registry_id="reg-avr",
                ),
            ),
        ),
        DeviceInstance(
            device_id="tv",
            bindings=(
                InstanceBinding(
                    output_group_id="main",
                    entity_registry_id="reg-tv",
                ),
            ),
        ),
        DeviceInstance(
            device_id="projector",
            bindings=(
                InstanceBinding(
                    output_group_id="main",
                    entity_registry_id="reg-projector",
                ),
            ),
        ),
    ]

    config = SystemConfig(
        devices=[apple_tv, avr, tv, projector],
        connections=connections,
        zones=[living_room, theater],
        device_instances=device_instances,
        source_visibility=[sv_living_room, sv_theater],
    )

    active_paths = ActivePathsRegistry()
    adapter_registry = AdapterRegistry()

    return config, active_paths, adapter_registry


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestEntitiesIntegration:
    """Integration test suite for Phase 6 entities."""

    def setup_method(self) -> None:
        """Set up the test system before each test."""
        self.hass = _make_hass()
        self.config, self.active_paths, self.adapter_registry = _build_system()
        self.orchestrator = Orchestrator(
            self.hass,
            self.config,
            self.adapter_registry,
            self.active_paths,
        )

    def _get_zone(self, zone_id: str) -> Zone:
        return next(z for z in self.config.zones if z.id == zone_id)

    def _make_player(self, zone_id: str) -> ZoneMediaPlayer:
        zone = self._get_zone(zone_id)
        return ZoneMediaPlayer(
            self.hass,
            zone,
            self.config,
            self.orchestrator,
            self.active_paths,
            self.adapter_registry,
        )

    # ------------------------------------------------------------------
    # Entity construction
    # ------------------------------------------------------------------

    def test_living_room_player_unique_id(self) -> None:
        """Living room media player has correct unique_id."""
        player = self._make_player("living_room")
        assert player.unique_id == "mrm_zone_living_room"

    def test_theater_player_unique_id(self) -> None:
        """Theater media player has correct unique_id."""
        player = self._make_player("theater")
        assert player.unique_id == "mrm_zone_theater"

    def test_living_room_source_list(self) -> None:
        """Living room source_list contains Apple TV."""
        player = self._make_player("living_room")
        assert "Apple TV" in player.source_list

    def test_theater_source_list(self) -> None:
        """Theater source_list contains Apple TV."""
        player = self._make_player("theater")
        assert "Apple TV" in player.source_list

    def test_supported_features_include_volume(self) -> None:
        """supported_features includes volume bits (AVR provides VOLUME role)."""
        from homeassistant.components.media_player import MediaPlayerEntityFeature

        player = self._make_player("living_room")
        assert player.supported_features & MediaPlayerEntityFeature.VOLUME_SET

    def test_supported_features_include_transport(self) -> None:
        """supported_features includes transport bits (Apple TV provides TRANSPORT)."""
        from homeassistant.components.media_player import MediaPlayerEntityFeature

        player = self._make_player("living_room")
        assert player.supported_features & MediaPlayerEntityFeature.PLAY

    def test_supported_features_include_select_source(self) -> None:
        """supported_features includes SELECT_SOURCE (visible sources configured)."""
        from homeassistant.components.media_player import MediaPlayerEntityFeature

        player = self._make_player("living_room")
        assert player.supported_features & MediaPlayerEntityFeature.SELECT_SOURCE

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def test_initial_state_is_off(self) -> None:
        """Zone state is OFF when no active path exists."""
        from homeassistant.components.media_player.const import MediaPlayerState

        player = self._make_player("living_room")
        assert player.state == MediaPlayerState.OFF

    def test_state_idle_after_path_activated(self) -> None:
        """Zone state is IDLE after a path is recorded in active_paths."""
        from homeassistant.components.media_player.const import MediaPlayerState

        # Manually insert an active path.
        result = ZoneResolverResult(
            zone_id="living_room",
            source_device_id="apple_tv",
            virtual_source_id=None,
            is_virtual_source=False,
            sink_device_ids=("tv",),
            video_paths=(),
            audio_paths=(),
            contentions=(),
            exclusive_output_usage=(),
        )
        self.active_paths.update(result)

        player = self._make_player("living_room")
        assert player.state == MediaPlayerState.IDLE

    # ------------------------------------------------------------------
    # select_source
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_select_source_calls_orchestrator(self) -> None:
        """select_source triggers async_activate_zone with the correct args."""
        self.orchestrator.async_activate_zone = AsyncMock(
            return_value=OrchestratorResult(success=True, zone_id="living_room")
        )
        player = self._make_player("living_room")
        player.async_write_ha_state = MagicMock()

        await player.async_select_source("Apple TV")

        self.orchestrator.async_activate_zone.assert_awaited_once_with(
            "living_room", "apple_tv", virtual_source_id=None
        )

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_transport_routes_to_apple_tv(self) -> None:
        """Transport commands route to Apple TV's adapter."""
        hop = PathHop("apple_tv", None, None, "main")
        path = ResolvedSinglePath("video", "apple_tv", "tv", (hop,))
        result = ZoneResolverResult(
            zone_id="living_room",
            source_device_id="apple_tv",
            virtual_source_id=None,
            is_virtual_source=False,
            sink_device_ids=("tv",),
            video_paths=(path,),
            audio_paths=(),
            contentions=(),
            exclusive_output_usage=(),
        )
        self.active_paths.update(result)

        mock_adapter = MagicMock()
        mock_adapter.async_send_transport = AsyncMock()
        self.adapter_registry._adapters["media_player_source"] = mock_adapter

        player = self._make_player("living_room")

        with patch(
            "custom_components.media_room_manager.entities.zone_media_player."
            "_resolve_entity_id_from_registry",
            side_effect=lambda hass, rid: f"media_player.{rid}",
        ):
            await player.async_media_play()

        mock_adapter.async_send_transport.assert_awaited_once()
        args = mock_adapter.async_send_transport.call_args
        assert args[0][2] == "play"  # command arg

    # ------------------------------------------------------------------
    # Volume
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_volume_routes_to_avr(self) -> None:
        """Volume commands route to the AVR's adapter."""
        mock_adapter = MagicMock()
        mock_adapter.async_set_volume = AsyncMock()
        self.adapter_registry._adapters["media_player_source"] = mock_adapter

        player = self._make_player("living_room")

        with patch(
            "custom_components.media_room_manager.entities.zone_media_player."
            "_resolve_entity_id_from_registry",
            side_effect=lambda hass, rid: "media_player.avr" if rid == "reg-avr" else None,
        ):
            await player.async_set_volume_level(0.7)

        mock_adapter.async_set_volume.assert_awaited_once_with(self.hass, "media_player.avr", 0.7)

    # ------------------------------------------------------------------
    # Selectable exclusive entities
    # ------------------------------------------------------------------

    def test_theater_select_entity_options(self) -> None:
        """Theater select entity lists TV and Projector as options."""
        zone = self._get_zone("theater")
        sel = SelectableExclusiveSelect(self.hass, zone, self.config, self.orchestrator)
        assert "Sony TV" in sel.options
        assert "JVC Projector" in sel.options

    def test_theater_switches_created_per_sink(self) -> None:
        """One switch entity per sink in the theater zone."""
        zone = self._get_zone("theater")
        switches = [
            SelectableExclusiveSwitch(self.hass, zone, self.config, self.orchestrator, sid)
            for sid in zone.sink_device_ids
        ]
        assert len(switches) == 2
        unique_ids = {sw.unique_id for sw in switches}
        assert "mrm_zone_theater_tv" in unique_ids
        assert "mrm_zone_theater_projector" in unique_ids

    @pytest.mark.asyncio
    async def test_select_projector_calls_orchestrator_with_projector_sink(self) -> None:
        """Selecting Projector in the theater select calls orchestrator with projector sink."""
        self.orchestrator.async_activate_zone = AsyncMock(
            return_value=OrchestratorResult(success=True, zone_id="theater")
        )
        zone = self._get_zone("theater")
        sel = SelectableExclusiveSelect(self.hass, zone, self.config, self.orchestrator)
        sel.async_write_ha_state = MagicMock()

        await sel.async_select_option("JVC Projector")

        self.orchestrator.async_activate_zone.assert_awaited_once_with(
            "theater",
            "apple_tv",
            virtual_source_id=None,
            sink_device_id="projector",
        )

    # ------------------------------------------------------------------
    # Binary sensor for shared AVR
    # ------------------------------------------------------------------

    def test_avr_in_use_sensor_unique_id(self) -> None:
        """AVR in-use sensor has correct unique_id."""
        avr = next(d for d in self.config.devices if d.id == "avr")
        sensor = DeviceInUseBinarySensor(self.hass, avr, self.config, self.active_paths)
        assert sensor.unique_id == "mrm_device_avr_in_use"

    def test_avr_not_in_use_initially(self) -> None:
        """AVR binary sensor is off when no zones are active."""
        avr = next(d for d in self.config.devices if d.id == "avr")
        sensor = DeviceInUseBinarySensor(self.hass, avr, self.config, self.active_paths)
        assert sensor.is_on is False

    def test_avr_in_use_when_path_active(self) -> None:
        """AVR binary sensor is on when AVR is in an active path."""
        hop1 = PathHop("apple_tv", None, None, "main")
        hop2 = PathHop("avr", "hdmi_1", "hdmi_main_out", "main")
        hop3 = PathHop("tv", "hdmi_in_1", None, None)
        path = ResolvedSinglePath("video", "apple_tv", "tv", (hop1, hop2, hop3))
        result = ZoneResolverResult(
            zone_id="living_room",
            source_device_id="apple_tv",
            virtual_source_id=None,
            is_virtual_source=False,
            sink_device_ids=("tv",),
            video_paths=(path,),
            audio_paths=(),
            contentions=(),
            exclusive_output_usage=(),
        )
        self.active_paths.update(result)

        avr = next(d for d in self.config.devices if d.id == "avr")
        sensor = DeviceInUseBinarySensor(self.hass, avr, self.config, self.active_paths)
        assert sensor.is_on is True

    def test_avr_not_in_use_after_deactivation(self) -> None:
        """AVR binary sensor is off after the zone deactivates."""
        hop = PathHop("avr", "hdmi_1", "hdmi_main_out", "main")
        path = ResolvedSinglePath("video", "apple_tv", "tv", (hop,))
        result = ZoneResolverResult(
            zone_id="living_room",
            source_device_id="apple_tv",
            virtual_source_id=None,
            is_virtual_source=False,
            sink_device_ids=("tv",),
            video_paths=(path,),
            audio_paths=(),
            contentions=(),
            exclusive_output_usage=(),
        )
        self.active_paths.update(result)
        self.active_paths.remove("living_room")

        avr = next(d for d in self.config.devices if d.id == "avr")
        sensor = DeviceInUseBinarySensor(self.hass, avr, self.config, self.active_paths)
        assert sensor.is_on is False

    # ------------------------------------------------------------------
    # DeviceInfo linkage
    # ------------------------------------------------------------------

    def test_living_room_player_device_info(self) -> None:
        """Living room player device_info links to zone device entry."""
        player = self._make_player("living_room")
        assert (DOMAIN, "zone_living_room") in player.device_info["identifiers"]

    def test_theater_select_device_info(self) -> None:
        """Theater select entity links to theater zone device entry."""
        zone = self._get_zone("theater")
        sel = SelectableExclusiveSelect(self.hass, zone, self.config, self.orchestrator)
        assert (DOMAIN, "zone_theater") in sel.device_info["identifiers"]

    def test_avr_sensor_device_info(self) -> None:
        """AVR in-use sensor links to AVR physical device entry."""
        avr = next(d for d in self.config.devices if d.id == "avr")
        sensor = DeviceInUseBinarySensor(self.hass, avr, self.config, self.active_paths)
        assert (DOMAIN, "device_avr") in sensor.device_info["identifiers"]
