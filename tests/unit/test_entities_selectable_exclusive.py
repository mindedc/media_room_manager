"""Tests for entities/selectable_exclusive.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.media_room_manager.adapters.registry import AdapterRegistry
from custom_components.media_room_manager.entities.selectable_exclusive import (
    SelectableExclusiveSelect,
    SelectableExclusiveSwitch,
    _sink_display_name,
)
from custom_components.media_room_manager.graph.model import (
    ControlRole,
    Device,
    MechanismKind,
    OutputGroup,
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
from custom_components.media_room_manager.resolver.path import ActivePathsRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_hass() -> MagicMock:
    hass = MagicMock()
    hass.services.async_call = AsyncMock()
    return hass


def _simple_device(device_id: str, name: str) -> Device:
    og = OutputGroup(
        id="main",
        provides_roles=(ControlRole.TRANSPORT,),
        selection_mechanism=SelectionMechanism(kind=MechanismKind.MEDIA_PLAYER_SOURCE),
    )
    return Device(id=device_id, name=name, profile_id="test/p", output_groups=(og,))


def _se_zone(zone_id: str, name: str, sink_ids: list[str]) -> Zone:
    return Zone(
        id=zone_id,
        name=name,
        sink_device_ids=tuple(sink_ids),
        sink_mode=SinkMode.SELECTABLE_EXCLUSIVE,
    )


def _simple_config(
    zones: list[Zone],
    devices: list[Device],
    source_visibility: list[SourceVisibilitySelection] | None = None,
) -> SystemConfig:
    return SystemConfig(
        zones=zones,
        devices=devices,
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
# Tests: _sink_display_name
# ---------------------------------------------------------------------------


class TestSinkDisplayName:
    """Tests for the sink display name helper."""

    def test_uses_device_name(self) -> None:
        """Returns device.name for known device."""
        device = _simple_device("tv", "Sony TV")
        zone = _se_zone("z1", "Room", ["tv"])
        config = _simple_config([zone], [device])

        assert _sink_display_name(zone, "tv", config) == "Sony TV"

    def test_falls_back_to_device_id(self) -> None:
        """Falls back to device_id when device not found."""
        zone = _se_zone("z1", "Room", ["unknown"])
        config = _simple_config([zone], [])

        assert _sink_display_name(zone, "unknown", config) == "unknown"


# ---------------------------------------------------------------------------
# Tests: SelectableExclusiveSelect
# ---------------------------------------------------------------------------


class TestSelectableExclusiveSelect:
    """Tests for the select entity."""

    def test_unique_id(self) -> None:
        """unique_id follows the mrm_zone_<id>_display pattern."""
        hass = _make_hass()
        zone = _se_zone("theater", "Theater", ["tv", "projector"])
        tv = _simple_device("tv", "TV")
        proj = _simple_device("projector", "Projector")
        config = _simple_config([zone], [tv, proj])
        orch = _simple_orchestrator(hass, config)

        sel = SelectableExclusiveSelect(hass, zone, config, orch)

        assert sel.unique_id == "mrm_zone_theater_display"

    def test_name(self) -> None:
        """name includes zone name and 'Display'."""
        hass = _make_hass()
        zone = _se_zone("theater", "Theater Room", ["tv", "projector"])
        tv = _simple_device("tv", "TV")
        proj = _simple_device("projector", "Projector")
        config = _simple_config([zone], [tv, proj])
        orch = _simple_orchestrator(hass, config)

        sel = SelectableExclusiveSelect(hass, zone, config, orch)

        assert sel.name == "Theater Room Display"

    def test_options_list(self) -> None:
        """options returns sink device display names."""
        hass = _make_hass()
        zone = _se_zone("z1", "Room", ["tv", "projector"])
        tv = _simple_device("tv", "Sony TV")
        proj = _simple_device("projector", "JVC Projector")
        config = _simple_config([zone], [tv, proj])
        orch = _simple_orchestrator(hass, config)

        sel = SelectableExclusiveSelect(hass, zone, config, orch)

        assert sel.options == ["Sony TV", "JVC Projector"]

    def test_device_info_uses_zone_identifiers(self) -> None:
        """device_info links to the zone's device registry entry."""
        from custom_components.media_room_manager.const import DOMAIN

        hass = _make_hass()
        zone = _se_zone("z1", "Room", ["tv"])
        tv = _simple_device("tv", "TV")
        config = _simple_config([zone], [tv])
        orch = _simple_orchestrator(hass, config)

        sel = SelectableExclusiveSelect(hass, zone, config, orch)

        assert (DOMAIN, "zone_z1") in sel.device_info["identifiers"]

    @pytest.mark.asyncio
    async def test_select_option_calls_orchestrator(self) -> None:
        """async_select_option calls orchestrator with the resolved sink id."""
        hass = _make_hass()
        zone = _se_zone("z1", "Room", ["tv", "projector"])
        tv = _simple_device("tv", "TV")
        proj = _simple_device("projector", "Projector")
        src = _simple_device("src", "Apple TV")
        svs = SourceVisibilitySelection(
            zone_id="z1",
            visible_sources=(SourceRef(device_id="src"),),
        )
        config = _simple_config([zone], [tv, proj, src], source_visibility=[svs])
        orch = _simple_orchestrator(hass, config)
        orch.async_activate_zone = AsyncMock(
            return_value=OrchestratorResult(success=True, zone_id="z1")
        )

        sel = SelectableExclusiveSelect(hass, zone, config, orch)
        sel.async_write_ha_state = MagicMock()

        await sel.async_select_option("Projector")

        orch.async_activate_zone.assert_awaited_once_with(
            "z1",
            "src",
            virtual_source_id=None,
            sink_device_id="projector",
        )

    @pytest.mark.asyncio
    async def test_select_option_unknown_sink_logs_warning(self) -> None:
        """Selecting an unknown sink logs a warning and does not call orchestrator."""
        hass = _make_hass()
        zone = _se_zone("z1", "Room", ["tv"])
        tv = _simple_device("tv", "TV")
        config = _simple_config([zone], [tv])
        orch = _simple_orchestrator(hass, config)
        orch.async_activate_zone = AsyncMock()

        sel = SelectableExclusiveSelect(hass, zone, config, orch)
        sel.async_write_ha_state = MagicMock()

        await sel.async_select_option("Unknown Display")

        orch.async_activate_zone.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_select_option_no_source_skips_orchestrator(self) -> None:
        """When no source is configured, selecting a sink does nothing."""
        hass = _make_hass()
        zone = _se_zone("z1", "Room", ["tv"])
        tv = _simple_device("tv", "TV")
        config = _simple_config([zone], [tv])  # no source_visibility
        orch = _simple_orchestrator(hass, config)
        orch.async_activate_zone = AsyncMock()

        sel = SelectableExclusiveSelect(hass, zone, config, orch)
        sel.async_write_ha_state = MagicMock()

        await sel.async_select_option("TV")

        orch.async_activate_zone.assert_not_awaited()


# ---------------------------------------------------------------------------
# Tests: SelectableExclusiveSwitch
# ---------------------------------------------------------------------------


class TestSelectableExclusiveSwitch:
    """Tests for per-sink switch entities."""

    def test_unique_id(self) -> None:
        """unique_id follows mrm_zone_<zone_id>_<sink_device_id> pattern."""
        hass = _make_hass()
        zone = _se_zone("theater", "Theater", ["tv"])
        tv = _simple_device("tv", "Sony TV")
        config = _simple_config([zone], [tv])
        orch = _simple_orchestrator(hass, config)

        sw = SelectableExclusiveSwitch(hass, zone, config, orch, "tv")

        assert sw.unique_id == "mrm_zone_theater_tv"

    def test_name_includes_sink_name(self) -> None:
        """name includes zone name and sink device name."""
        hass = _make_hass()
        zone = _se_zone("z1", "Theater", ["tv"])
        tv = _simple_device("tv", "Sony TV")
        config = _simple_config([zone], [tv])
        orch = _simple_orchestrator(hass, config)

        sw = SelectableExclusiveSwitch(hass, zone, config, orch, "tv")

        assert sw.name == "Theater Sony TV"

    def test_is_on_default_false(self) -> None:
        """is_on defaults to False."""
        hass = _make_hass()
        zone = _se_zone("z1", "Room", ["tv"])
        tv = _simple_device("tv", "TV")
        config = _simple_config([zone], [tv])
        orch = _simple_orchestrator(hass, config)

        sw = SelectableExclusiveSwitch(hass, zone, config, orch, "tv")

        assert sw.is_on is False

    def test_device_info_uses_zone_identifiers(self) -> None:
        """device_info links to the zone's device registry entry."""
        from custom_components.media_room_manager.const import DOMAIN

        hass = _make_hass()
        zone = _se_zone("z1", "Room", ["tv"])
        tv = _simple_device("tv", "TV")
        config = _simple_config([zone], [tv])
        orch = _simple_orchestrator(hass, config)

        sw = SelectableExclusiveSwitch(hass, zone, config, orch, "tv")

        assert (DOMAIN, "zone_z1") in sw.device_info["identifiers"]

    @pytest.mark.asyncio
    async def test_turn_on_calls_orchestrator(self) -> None:
        """async_turn_on activates the zone with this sink."""
        hass = _make_hass()
        zone = _se_zone("z1", "Room", ["tv"])
        tv = _simple_device("tv", "TV")
        src = _simple_device("src", "Apple TV")
        svs = SourceVisibilitySelection(
            zone_id="z1",
            visible_sources=(SourceRef(device_id="src"),),
        )
        config = _simple_config([zone], [tv, src], source_visibility=[svs])
        orch = _simple_orchestrator(hass, config)
        orch.async_activate_zone = AsyncMock(
            return_value=OrchestratorResult(success=True, zone_id="z1")
        )

        sw = SelectableExclusiveSwitch(hass, zone, config, orch, "tv")
        sw.async_write_ha_state = MagicMock()

        await sw.async_turn_on()

        orch.async_activate_zone.assert_awaited_once_with(
            "z1",
            "src",
            virtual_source_id=None,
            sink_device_id="tv",
        )

    @pytest.mark.asyncio
    async def test_turn_off_is_noop(self) -> None:
        """async_turn_off does not call orchestrator (no-op for exclusive)."""
        hass = _make_hass()
        zone = _se_zone("z1", "Room", ["tv"])
        tv = _simple_device("tv", "TV")
        config = _simple_config([zone], [tv])
        orch = _simple_orchestrator(hass, config)
        orch.async_activate_zone = AsyncMock()

        sw = SelectableExclusiveSwitch(hass, zone, config, orch, "tv")
        sw.async_write_ha_state = MagicMock()

        await sw.async_turn_off()

        orch.async_activate_zone.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_turn_on_no_source_skips_orchestrator(self) -> None:
        """Turn on does nothing when no source visibility is configured."""
        hass = _make_hass()
        zone = _se_zone("z1", "Room", ["tv"])
        tv = _simple_device("tv", "TV")
        config = _simple_config([zone], [tv])  # no source_visibility
        orch = _simple_orchestrator(hass, config)
        orch.async_activate_zone = AsyncMock()

        sw = SelectableExclusiveSwitch(hass, zone, config, orch, "tv")
        sw.async_write_ha_state = MagicMock()

        await sw.async_turn_on()

        orch.async_activate_zone.assert_not_awaited()
