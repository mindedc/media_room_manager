"""End-to-end orchestrator integration test.

Scenario: Apple TV → AVR (discrete_capable, power_on_delay=5) → TV (discrete_capable).
Zone: living_room, sink=TV, volume_authority=AVR.

Expected service call order:
  1. media_player.turn_on  apple_tv      (discrete_capable, no delay)
  2. media_player.turn_on  avr           (discrete_capable)
  3. asyncio.sleep(5)                    (power_on_delay for AVR)
  4. media_player.turn_on  tv            (discrete_capable, no delay)
  5. media_player.select_source avr      ("HDMI 1" — ATV input label)
  6. media_player.media_play  apple_tv   (transport on source)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.media_room_manager.adapters.registry import AdapterRegistry
from custom_components.media_room_manager.graph.model import (
    Connection,
    ContentionPolicy,
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
    Zone,
)
from custom_components.media_room_manager.graph.system_config import SystemConfig
from custom_components.media_room_manager.orchestrator.orchestrator import Orchestrator
from custom_components.media_room_manager.resolver.path import ActivePathsRegistry


def _out(iface_id: str, og: str, label: str | None = None) -> Interface:
    return Interface(
        id=iface_id,
        direction=InterfaceDirection.OUTPUT,
        type=InterfaceType.HDMI,
        label=label or iface_id,
        output_group=og,
    )


def _inp(iface_id: str, routable: list[str], label: str) -> Interface:
    return Interface(
        id=iface_id,
        direction=InterfaceDirection.INPUT,
        type=InterfaceType.HDMI,
        label=label,
        routable_to_output_group=tuple(routable),
    )


def _conn(cid: str, fd: str, fi: str, td: str, ti: str) -> Connection:
    return Connection(
        id=cid, from_device_id=fd, from_interface_id=fi, to_device_id=td, to_interface_id=ti
    )


# ---------------------------------------------------------------------------
# Build config
# ---------------------------------------------------------------------------


def _build_config() -> tuple[SystemConfig, dict[str, str]]:
    """Construct the Apple TV → AVR → TV scenario."""
    atv_og = OutputGroup(
        id="main",
        provides_roles=(ControlRole.TRANSPORT, ControlRole.METADATA_SOURCE),
        selection_mechanism=SelectionMechanism(kind=MechanismKind.MEDIA_PLAYER_SOURCE),
    )
    avr_og = OutputGroup(
        id="avr_main",
        provides_roles=(),
        selection_mechanism=SelectionMechanism(kind=MechanismKind.MEDIA_PLAYER_SOURCE),
    )
    tv_og = OutputGroup(
        id="screen",
        provides_roles=(),
        selection_mechanism=None,  # TV has no source selection
    )

    apple_tv = Device(
        id="apple_tv",
        name="Apple TV 4K",
        profile_id="apple/atv4k",
        power_handling=PowerHandling.DISCRETE_CAPABLE,
        power_on_delay=0,
        output_groups=(atv_og,),
        interfaces=(_out("atv_hdmi", "main", label="HDMI"),),
    )
    avr = Device(
        id="avr",
        name="Denon AVR-X1700H",
        profile_id="denon/avrx1700h",
        power_handling=PowerHandling.DISCRETE_CAPABLE,
        power_on_delay=5,
        output_groups=(avr_og,),
        interfaces=(
            _inp("avr_in1", ["avr_main"], label="HDMI 1"),
            _out("avr_hdmi", "avr_main", label="HDMI OUT"),
        ),
    )
    tv = Device(
        id="tv",
        name="Sony Bravia",
        profile_id="sony/bravia",
        power_handling=PowerHandling.DISCRETE_CAPABLE,
        power_on_delay=0,
        output_groups=(tv_og,),
        interfaces=(_inp("tv_hdmi", ["screen"], label="HDMI 1"),),
    )

    zone = Zone(
        id="living_room",
        name="Living Room",
        sink_device_ids=("tv",),
        sink_mode=SinkMode.SINGLE,
        contention_policy=ContentionPolicy.DENY,
        volume_authority_device_id="avr",
        volume_authority_output_group_id="avr_main",
    )

    conns = [
        _conn("c1", "apple_tv", "atv_hdmi", "avr", "avr_in1"),
        _conn("c2", "avr", "avr_hdmi", "tv", "tv_hdmi"),
    ]

    instances = [
        DeviceInstance(
            "apple_tv",
            bindings=(InstanceBinding(output_group_id="main", entity_registry_id="reg-atv"),),
        ),
        DeviceInstance(
            "avr",
            bindings=(InstanceBinding(output_group_id="avr_main", entity_registry_id="reg-avr"),),
        ),
        DeviceInstance(
            "tv",
            bindings=(InstanceBinding(output_group_id="screen", entity_registry_id="reg-tv"),),
        ),
    ]

    config = SystemConfig(
        devices=[apple_tv, avr, tv],
        connections=conns,
        zones=[zone],
        device_instances=instances,
    )
    entity_map = {
        "reg-atv": "media_player.apple_tv",
        "reg-avr": "media_player.avr",
        "reg-tv": "media_player.tv",
    }
    return config, entity_map


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


async def test_e2e_activation_order() -> None:
    """Verify the full activation call sequence for Apple TV → AVR → TV."""
    config, entity_map = _build_config()

    hass = MagicMock()
    hass.services.async_call = AsyncMock()

    active = ActivePathsRegistry()
    orch = Orchestrator(
        hass=hass,
        config=config,
        adapter_registry=AdapterRegistry(),
        active_paths=active,
        retry_count=0,
        entity_id_resolver=lambda reg_id: entity_map.get(reg_id),
    )

    sleep_calls: list[float] = []

    async def _fake_sleep(secs: float) -> None:
        sleep_calls.append(secs)

    with patch("asyncio.sleep", side_effect=_fake_sleep):
        result = await orch.async_activate_zone("living_room", "apple_tv")

    assert result.success, result.error_detail
    assert active.get("living_room") is not None

    # ---- Verify power-on calls ----
    all_calls = hass.services.async_call.call_args_list

    turn_on_calls = [c for c in all_calls if c.args[1] == "turn_on"]
    turned_on_entities = [c.args[2]["entity_id"] for c in turn_on_calls]

    assert "media_player.apple_tv" in turned_on_entities, "Apple TV should be powered on"
    assert "media_player.avr" in turned_on_entities, "AVR should be powered on"
    assert "media_player.tv" in turned_on_entities, "TV should be powered on"

    # ---- Verify power-on order (apple_tv < avr < tv in turned_on list) ----
    atv_idx = turned_on_entities.index("media_player.apple_tv")
    avr_idx = turned_on_entities.index("media_player.avr")
    tv_idx = turned_on_entities.index("media_player.tv")
    assert atv_idx < avr_idx, "Apple TV must be powered on before AVR"
    assert avr_idx < tv_idx, "AVR must be powered on before TV"

    # ---- Verify AVR power_on_delay caused sleep(5) ----
    assert 5 in sleep_calls, f"Expected asyncio.sleep(5) for AVR, got: {sleep_calls}"
    # Apple TV delay=0 → no sleep for it (or sleep(0) won't be in list because we skip delay=0)
    non_avr_sleeps = [s for s in sleep_calls if s != 5]
    assert all(s == 0 for s in non_avr_sleeps), (
        f"Unexpected non-zero sleeps (besides AVR): {non_avr_sleeps}"
    )

    # ---- Verify input selection on AVR (not TV) ----
    select_calls = [c for c in all_calls if c.args[1] == "select_source"]
    avr_select = [c for c in select_calls if c.args[2]["entity_id"] == "media_player.avr"]
    assert len(avr_select) >= 1, "AVR should have select_source called"

    # The label should be the entry interface label on AVR for the Apple TV input.
    avr_source_values = [c.args[2]["source"] for c in avr_select]
    assert "HDMI 1" in avr_source_values, f"AVR source should be 'HDMI 1', got {avr_source_values}"

    # TV has no selection_mechanism — no select_source.
    tv_select = [c for c in select_calls if c.args[2]["entity_id"] == "media_player.tv"]
    assert len(tv_select) == 0, "TV should NOT have select_source called (no mechanism)"

    # ---- Verify transport play on Apple TV ----
    play_calls = [c for c in all_calls if c.args[1] == "media_play"]
    atv_play = [c for c in play_calls if c.args[2]["entity_id"] == "media_player.apple_tv"]
    assert len(atv_play) >= 1, "Apple TV should receive media_play (transport)"

    # ---- Verify role assignment ----
    assert result.role_assignment is not None
    assert result.role_assignment.volume_device_id == "avr"
    assert result.role_assignment.transport_device_id == "apple_tv"


async def test_e2e_deactivation_powers_off_all() -> None:
    """After deactivation with no other active zones, all devices are powered off."""
    config, entity_map = _build_config()

    hass = MagicMock()
    hass.services.async_call = AsyncMock()

    active = ActivePathsRegistry()
    orch = Orchestrator(
        hass=hass,
        config=config,
        adapter_registry=AdapterRegistry(),
        active_paths=active,
        retry_count=0,
        entity_id_resolver=lambda reg_id: entity_map.get(reg_id),
    )

    with patch("asyncio.sleep", new_callable=AsyncMock):
        act = await orch.async_activate_zone("living_room", "apple_tv")
    assert act.success, act.error_detail

    hass.services.async_call.reset_mock()

    deact = await orch.async_deactivate_zone("living_room")
    assert deact.success, deact.error_detail
    assert active.get("living_room") is None

    turn_off_calls = [c for c in hass.services.async_call.call_args_list if c.args[1] == "turn_off"]
    powered_off = {c.args[2]["entity_id"] for c in turn_off_calls}
    assert "media_player.apple_tv" in powered_off
    assert "media_player.avr" in powered_off
    assert "media_player.tv" in powered_off
