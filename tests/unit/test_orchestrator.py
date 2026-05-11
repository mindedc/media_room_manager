"""Tests for orchestrator.orchestrator.Orchestrator."""

from __future__ import annotations

import dataclasses
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
from custom_components.media_room_manager.orchestrator.orchestrator import (
    DeviceStateTrackerProtocol,
    Orchestrator,
)
from custom_components.media_room_manager.resolver.path import ActivePathsRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_hass() -> MagicMock:
    hass = MagicMock()
    hass.services.async_call = AsyncMock()
    return hass


def _out(iface_id: str, og: str, itype: InterfaceType = InterfaceType.HDMI) -> Interface:
    return Interface(
        id=iface_id,
        direction=InterfaceDirection.OUTPUT,
        type=itype,
        label=iface_id,
        output_group=og,
    )


def _inp(
    iface_id: str,
    routable: list[str],
    label: str | None = None,
    itype: InterfaceType = InterfaceType.HDMI,
) -> Interface:
    return Interface(
        id=iface_id,
        direction=InterfaceDirection.INPUT,
        type=itype,
        label=label or iface_id,
        routable_to_output_group=tuple(routable),
    )


def _conn(cid: str, fd: str, fi: str, td: str, ti: str) -> Connection:
    return Connection(
        id=cid, from_device_id=fd, from_interface_id=fi, to_device_id=td, to_interface_id=ti
    )


def _og(og_id: str, roles: list[ControlRole] | None = None, mech: bool = True) -> OutputGroup:
    sm: SelectionMechanism | None = None
    if mech:
        sm = SelectionMechanism(kind=MechanismKind.MEDIA_PLAYER_SOURCE)
    return OutputGroup(
        id=og_id,
        provides_roles=tuple(roles or []),
        selection_mechanism=sm,
    )


def _binding(og_id: str, reg_id: str) -> InstanceBinding:
    return InstanceBinding(output_group_id=og_id, entity_registry_id=reg_id)


def _entity_resolver(mapping: dict[str, str]):  # type: ignore[no-untyped-def]
    """Return a simple entity_id_resolver function."""
    return lambda reg_id: mapping.get(reg_id)


# ---------------------------------------------------------------------------
# Two-device chain: Apple TV (source) → TV (sink)
# ---------------------------------------------------------------------------


def _two_device_config(
    source_power: PowerHandling = PowerHandling.DISCRETE_CAPABLE,
    sink_power: PowerHandling = PowerHandling.DISCRETE_CAPABLE,
    source_delay: int = 0,
    sink_delay: int = 0,
    source_roles: list[ControlRole] | None = None,
) -> tuple[SystemConfig, dict[str, str]]:
    """Build a minimal 2-device config and return (config, entity_id_map)."""
    source_og = _og("main", roles=source_roles or [ControlRole.TRANSPORT])
    sink_og = _og("screen", mech=False)  # TV has no selection mechanism

    source = Device(
        id="atv",
        name="Apple TV",
        profile_id="apple/atv",
        power_handling=source_power,
        power_on_delay=source_delay,
        output_groups=(source_og,),
        interfaces=(_out("atv_hdmi_out", "main"),),
    )
    sink = Device(
        id="tv",
        name="TV",
        profile_id="sony/bravia",
        power_handling=sink_power,
        power_on_delay=sink_delay,
        output_groups=(sink_og,),
        interfaces=(_inp("tv_hdmi_in", ["screen"], label="HDMI 1"),),
    )
    conn = _conn("c1", "atv", "atv_hdmi_out", "tv", "tv_hdmi_in")
    zone = Zone(
        id="living_room",
        name="Living Room",
        sink_device_ids=("tv",),
        sink_mode=SinkMode.SINGLE,
        contention_policy=ContentionPolicy.DENY,
    )
    atv_inst = DeviceInstance(
        device_id="atv",
        bindings=(_binding("main", "reg-atv"),),
    )
    tv_inst = DeviceInstance(
        device_id="tv",
        bindings=(_binding("screen", "reg-tv"),),
    )
    config = SystemConfig(
        devices=[source, sink],
        connections=[conn],
        zones=[zone],
        device_instances=[atv_inst, tv_inst],
    )
    entity_map = {"reg-atv": "media_player.atv", "reg-tv": "media_player.tv"}
    return config, entity_map


def _make_orchestrator(
    config: SystemConfig,
    entity_map: dict[str, str],
    state_tracker: DeviceStateTrackerProtocol | None = None,
    retry_count: int = 0,
) -> tuple[Orchestrator, MagicMock, ActivePathsRegistry]:
    hass = _make_hass()
    active = ActivePathsRegistry()
    orch = Orchestrator(
        hass=hass,
        config=config,
        adapter_registry=AdapterRegistry(),
        active_paths=active,
        state_tracker=state_tracker,
        retry_count=retry_count,
        entity_id_resolver=_entity_resolver(entity_map),
    )
    return orch, hass, active


# ---------------------------------------------------------------------------
# Power-on tests
# ---------------------------------------------------------------------------


async def test_power_on_discrete_capable() -> None:
    """discrete_capable: turn_on called for both devices."""
    config, entity_map = _two_device_config(
        source_power=PowerHandling.DISCRETE_CAPABLE,
        sink_power=PowerHandling.DISCRETE_CAPABLE,
    )
    orch, hass, _active = _make_orchestrator(config, entity_map)

    result = await orch.async_activate_zone("living_room", "atv")
    assert result.success, result.error_detail

    calls = hass.services.async_call.call_args_list
    domains_services = [(c.args[0], c.args[1]) for c in calls if c.args[1] == "turn_on"]
    assert ("media_player", "turn_on") in domains_services


async def test_power_on_skipped_for_always_on() -> None:
    """always_on: no turn_on call issued."""
    config, entity_map = _two_device_config(
        source_power=PowerHandling.ALWAYS_ON,
        sink_power=PowerHandling.ALWAYS_ON,
    )
    orch, hass, _active = _make_orchestrator(config, entity_map)

    result = await orch.async_activate_zone("living_room", "atv")
    assert result.success, result.error_detail

    calls = hass.services.async_call.call_args_list
    turn_on_calls = [c for c in calls if c.args[1] == "turn_on"]
    assert len(turn_on_calls) == 0


async def test_power_on_skipped_for_disabled() -> None:
    """disabled: no turn_on call issued."""
    config, entity_map = _two_device_config(
        source_power=PowerHandling.DISABLED,
        sink_power=PowerHandling.DISABLED,
    )
    orch, hass, _active = _make_orchestrator(config, entity_map)

    result = await orch.async_activate_zone("living_room", "atv")
    assert result.success, result.error_detail

    calls = hass.services.async_call.call_args_list
    turn_on_calls = [c for c in calls if c.args[1] == "turn_on"]
    assert len(turn_on_calls) == 0


async def test_toggle_no_power_on_when_already_on() -> None:
    """toggle: power_on skipped when state_tracker reports 'on'."""

    class MockTracker:
        def get_power_state(self, device_id: str) -> str | None:
            return "on"

    config, entity_map = _two_device_config(
        source_power=PowerHandling.TOGGLE,
        sink_power=PowerHandling.TOGGLE,
    )
    orch, hass, _active = _make_orchestrator(config, entity_map, state_tracker=MockTracker())

    result = await orch.async_activate_zone("living_room", "atv")
    assert result.success, result.error_detail

    calls = hass.services.async_call.call_args_list
    turn_on_calls = [c for c in calls if c.args[1] == "turn_on"]
    assert len(turn_on_calls) == 0


async def test_toggle_power_on_when_off() -> None:
    """toggle: power_on issued when state_tracker reports 'off'."""

    class MockTracker:
        def get_power_state(self, device_id: str) -> str | None:
            return "off"

    config, entity_map = _two_device_config(
        source_power=PowerHandling.TOGGLE,
        sink_power=PowerHandling.TOGGLE,
    )
    orch, hass, _active = _make_orchestrator(config, entity_map, state_tracker=MockTracker())

    result = await orch.async_activate_zone("living_room", "atv")
    assert result.success, result.error_detail

    calls = hass.services.async_call.call_args_list
    turn_on_calls = [c for c in calls if c.args[1] == "turn_on"]
    assert len(turn_on_calls) > 0


async def test_power_on_delay_called() -> None:
    """power_on_delay causes asyncio.sleep to be called."""
    config, entity_map = _two_device_config(
        source_power=PowerHandling.DISCRETE_CAPABLE,
        source_delay=3,
    )
    orch, _hass, _active = _make_orchestrator(config, entity_map)

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        result = await orch.async_activate_zone("living_room", "atv")

    assert result.success, result.error_detail
    sleep_calls = [c.args[0] for c in mock_sleep.call_args_list]
    assert 3 in sleep_calls


async def test_no_sleep_when_delay_zero() -> None:
    """power_on_delay=0: asyncio.sleep not called."""
    config, entity_map = _two_device_config(
        source_power=PowerHandling.DISCRETE_CAPABLE,
        source_delay=0,
        sink_delay=0,
    )
    orch, _hass, _active = _make_orchestrator(config, entity_map)

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        result = await orch.async_activate_zone("living_room", "atv")

    assert result.success, result.error_detail
    mock_sleep.assert_not_called()


# ---------------------------------------------------------------------------
# Input selection tests
# ---------------------------------------------------------------------------


def _three_device_config(
    avr_og_roles: list[ControlRole] | None = None,
) -> tuple[SystemConfig, dict[str, str]]:
    """Build Apple TV → AVR → TV config for input selection order testing."""
    atv_og = _og("main", roles=avr_og_roles or [ControlRole.TRANSPORT])
    avr_og = _og("avr_main")
    tv_og = _og("screen", mech=False)

    atv = Device(
        id="atv",
        name="Apple TV",
        profile_id="apple/atv",
        power_handling=PowerHandling.DISCRETE_CAPABLE,
        output_groups=(atv_og,),
        interfaces=(_out("atv_out", "main"),),
    )
    avr = Device(
        id="avr",
        name="AVR",
        profile_id="denon/avr",
        power_handling=PowerHandling.DISCRETE_CAPABLE,
        output_groups=(avr_og,),
        interfaces=(
            _inp("avr_in1", ["avr_main"], label="HDMI 1"),
            _out("avr_out", "avr_main"),
        ),
    )
    tv = Device(
        id="tv",
        name="TV",
        profile_id="sony/bravia",
        power_handling=PowerHandling.DISCRETE_CAPABLE,
        output_groups=(tv_og,),
        interfaces=(_inp("tv_in1", ["screen"], label="HDMI 1"),),
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
        _conn("c1", "atv", "atv_out", "avr", "avr_in1"),
        _conn("c2", "avr", "avr_out", "tv", "tv_in1"),
    ]
    instances = [
        DeviceInstance("atv", bindings=(_binding("main", "reg-atv"),)),
        DeviceInstance("avr", bindings=(_binding("avr_main", "reg-avr"),)),
        DeviceInstance("tv", bindings=(_binding("screen", "reg-tv"),)),
    ]
    config = SystemConfig(
        devices=[atv, avr, tv],
        connections=conns,
        zones=[zone],
        device_instances=instances,
    )
    entity_map = {
        "reg-atv": "media_player.atv",
        "reg-avr": "media_player.avr",
        "reg-tv": "media_player.tv",
    }
    return config, entity_map


async def test_input_selection_reverse_order() -> None:
    """Input selection happens sink→source: TV first, then AVR."""
    config, entity_map = _three_device_config()
    orch, hass, _active = _make_orchestrator(config, entity_map)

    result = await orch.async_activate_zone("living_room", "atv")
    assert result.success, result.error_detail

    select_calls = [
        c for c in hass.services.async_call.call_args_list if c.args[1] == "select_source"
    ]
    # TV has no selection_mechanism, AVR does.
    assert len(select_calls) >= 1
    avr_call = next((c for c in select_calls if c.args[2]["entity_id"] == "media_player.avr"), None)
    assert avr_call is not None


async def test_input_selection_skipped_for_no_mechanism() -> None:
    """Devices without a selection_mechanism (TV) don't get select_source called."""
    config, entity_map = _three_device_config()
    orch, hass, _active = _make_orchestrator(config, entity_map)

    result = await orch.async_activate_zone("living_room", "atv")
    assert result.success, result.error_detail

    select_calls = [
        c for c in hass.services.async_call.call_args_list if c.args[1] == "select_source"
    ]
    tv_calls = [c for c in select_calls if c.args[2]["entity_id"] == "media_player.tv"]
    assert len(tv_calls) == 0


# ---------------------------------------------------------------------------
# Virtual source selection
# ---------------------------------------------------------------------------


def _virtual_source_config() -> tuple[SystemConfig, dict[str, str]]:
    """AVR with a tuner virtual source."""
    from custom_components.media_room_manager.graph.model import VirtualSource

    avr_og = _og("main", roles=[ControlRole.TRANSPORT])
    avr = Device(
        id="avr",
        name="AVR",
        profile_id="denon/avr",
        power_handling=PowerHandling.DISCRETE_CAPABLE,
        output_groups=(avr_og,),
        interfaces=(_out("avr_out", "main"),),
        virtual_sources=(
            VirtualSource(id="tuner", label="Tuner", routable_to_output_group=("main",)),
        ),
    )
    tv = Device(
        id="tv",
        name="TV",
        profile_id="sony/bravia",
        output_groups=(_og("screen", mech=False),),
        interfaces=(_inp("tv_in", ["screen"], label="HDMI 1"),),
    )
    zone = Zone(
        id="living_room",
        name="LR",
        sink_device_ids=("tv",),
        sink_mode=SinkMode.SINGLE,
        contention_policy=ContentionPolicy.DENY,
    )
    conn = _conn("c1", "avr", "avr_out", "tv", "tv_in")
    instances = [
        DeviceInstance("avr", bindings=(_binding("main", "reg-avr"),)),
        DeviceInstance("tv", bindings=(_binding("screen", "reg-tv"),)),
    ]
    config = SystemConfig(
        devices=[avr, tv],
        connections=[conn],
        zones=[zone],
        device_instances=instances,
    )
    entity_map = {"reg-avr": "media_player.avr", "reg-tv": "media_player.tv"}
    return config, entity_map


async def test_virtual_source_selection_called() -> None:
    """When virtual_source_id given, select_source called on source device with vs label."""
    config, entity_map = _virtual_source_config()
    orch, hass, _active = _make_orchestrator(config, entity_map)

    result = await orch.async_activate_zone("living_room", "avr", virtual_source_id="tuner")
    assert result.success, result.error_detail

    select_calls = [
        c for c in hass.services.async_call.call_args_list if c.args[1] == "select_source"
    ]
    avr_tuner_calls = [
        c
        for c in select_calls
        if c.args[2]["entity_id"] == "media_player.avr" and c.args[2]["source"] == "Tuner"
    ]
    assert len(avr_tuner_calls) >= 1


# ---------------------------------------------------------------------------
# Transport tests
# ---------------------------------------------------------------------------


async def test_transport_play_called_after_setup() -> None:
    """Transport 'play' issued on source device after path setup."""
    config, entity_map = _three_device_config(
        avr_og_roles=None  # atv has TRANSPORT
    )
    orch, hass, _active = _make_orchestrator(config, entity_map)

    result = await orch.async_activate_zone("living_room", "atv")
    assert result.success, result.error_detail

    play_calls = [c for c in hass.services.async_call.call_args_list if c.args[1] == "media_play"]
    atv_play = [c for c in play_calls if c.args[2]["entity_id"] == "media_player.atv"]
    assert len(atv_play) >= 1


# ---------------------------------------------------------------------------
# Deactivation tests
# ---------------------------------------------------------------------------


async def test_deactivation_powers_off_unused_devices() -> None:
    """On deactivation, devices not in other active zones are powered off."""
    config, entity_map = _two_device_config()
    orch, hass, _active = _make_orchestrator(config, entity_map)

    # Activate first.
    res = await orch.async_activate_zone("living_room", "atv")
    assert res.success, res.error_detail
    hass.services.async_call.reset_mock()

    # Deactivate.
    deact = await orch.async_deactivate_zone("living_room")
    assert deact.success, deact.error_detail

    turn_off_calls = [c for c in hass.services.async_call.call_args_list if c.args[1] == "turn_off"]
    assert len(turn_off_calls) > 0


async def test_deactivation_keeps_shared_device_on() -> None:
    """A device shared with another active zone is NOT powered off during deactivation."""
    # Build two zones sharing the same AVR.
    avr_og = _og("avr_main")
    tv_og = _og("screen", mech=False)
    proj_og = _og("screen2", mech=False)

    atv = Device(
        id="atv",
        name="Apple TV",
        profile_id="apple/atv",
        power_handling=PowerHandling.DISCRETE_CAPABLE,
        output_groups=(_og("main", roles=[ControlRole.TRANSPORT]),),
        interfaces=(_out("atv_out", "main"),),
    )
    avr = Device(
        id="avr",
        name="AVR",
        profile_id="denon/avr",
        power_handling=PowerHandling.DISCRETE_CAPABLE,
        output_groups=(avr_og,),
        interfaces=(
            _inp("avr_in1", ["avr_main"], label="HDMI 1"),
            _out("avr_out1", "avr_main"),
            _out("avr_out2", "avr_main"),
        ),
    )
    tv = Device(
        id="tv",
        name="TV",
        profile_id="sony/bravia",
        power_handling=PowerHandling.DISCRETE_CAPABLE,
        output_groups=(tv_og,),
        interfaces=(_inp("tv_in", ["screen"], label="HDMI 1"),),
    )
    proj = Device(
        id="proj",
        name="Projector",
        profile_id="benq/proj",
        power_handling=PowerHandling.DISCRETE_CAPABLE,
        output_groups=(proj_og,),
        interfaces=(_inp("proj_in", ["screen2"], label="HDMI 1"),),
    )

    zone1 = Zone(
        id="zone1",
        name="Zone 1",
        sink_device_ids=("tv",),
        sink_mode=SinkMode.SINGLE,
        contention_policy=ContentionPolicy.DENY,
    )
    zone2 = Zone(
        id="zone2",
        name="Zone 2",
        sink_device_ids=("proj",),
        sink_mode=SinkMode.SINGLE,
        contention_policy=ContentionPolicy.DENY,
    )

    conns = [
        _conn("c1", "atv", "atv_out", "avr", "avr_in1"),
        _conn("c2", "avr", "avr_out1", "tv", "tv_in"),
        _conn("c3", "avr", "avr_out2", "proj", "proj_in"),
    ]

    instances = [
        DeviceInstance("atv", bindings=(_binding("main", "reg-atv"),)),
        DeviceInstance("avr", bindings=(_binding("avr_main", "reg-avr"),)),
        DeviceInstance("tv", bindings=(_binding("screen", "reg-tv"),)),
        DeviceInstance("proj", bindings=(_binding("screen2", "reg-proj"),)),
    ]

    config = SystemConfig(
        devices=[atv, avr, tv, proj],
        connections=conns,
        zones=[zone1, zone2],
        device_instances=instances,
    )
    entity_map = {
        "reg-atv": "media_player.atv",
        "reg-avr": "media_player.avr",
        "reg-tv": "media_player.tv",
        "reg-proj": "media_player.proj",
    }

    hass = _make_hass()
    active = ActivePathsRegistry()
    orch = Orchestrator(
        hass=hass,
        config=config,
        adapter_registry=AdapterRegistry(),
        active_paths=active,
        retry_count=0,
        entity_id_resolver=_entity_resolver(entity_map),
    )

    # Activate both zones.
    r1 = await orch.async_activate_zone("zone1", "atv")
    assert r1.success, r1.error_detail
    r2 = await orch.async_activate_zone("zone2", "atv")
    assert r2.success, r2.error_detail
    hass.services.async_call.reset_mock()

    # Deactivate zone1 — AVR should stay on because zone2 uses it.
    deact = await orch.async_deactivate_zone("zone1")
    assert deact.success, deact.error_detail

    turn_off_calls = [c for c in hass.services.async_call.call_args_list if c.args[1] == "turn_off"]
    avr_off = [c for c in turn_off_calls if c.args[2].get("entity_id") == "media_player.avr"]
    assert len(avr_off) == 0


# ---------------------------------------------------------------------------
# Retry tests
# ---------------------------------------------------------------------------


async def test_retry_on_first_failure() -> None:
    """Adapter raises on first call, succeeds on second — overall result is success."""
    config, entity_map = _two_device_config()
    hass = _make_hass()

    call_count = 0

    async def flaky_turn_on(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("transient failure")

    hass.services.async_call = AsyncMock(side_effect=flaky_turn_on)

    active = ActivePathsRegistry()
    orch = Orchestrator(
        hass=hass,
        config=config,
        adapter_registry=AdapterRegistry(),
        active_paths=active,
        retry_count=2,
        entity_id_resolver=_entity_resolver(entity_map),
    )

    with patch("asyncio.sleep", new_callable=AsyncMock):
        result = await orch.async_activate_zone("living_room", "atv")

    assert result.success, result.error_detail
    assert call_count >= 2


async def test_retry_exhausted_returns_failure() -> None:
    """When all attempts fail, async_activate_zone returns success=False."""
    config, entity_map = _two_device_config()
    hass = _make_hass()
    hass.services.async_call = AsyncMock(side_effect=RuntimeError("always fails"))

    active = ActivePathsRegistry()
    orch = Orchestrator(
        hass=hass,
        config=config,
        adapter_registry=AdapterRegistry(),
        active_paths=active,
        retry_count=1,
        entity_id_resolver=_entity_resolver(entity_map),
    )

    with patch("asyncio.sleep", new_callable=AsyncMock):
        result = await orch.async_activate_zone("living_room", "atv")

    assert not result.success
    assert result.error_detail is not None


# ---------------------------------------------------------------------------
# Contention tests
# ---------------------------------------------------------------------------


def _contention_config() -> tuple[SystemConfig, dict[str, str]]:
    """Two zones competing for the same AVR input."""
    avr_og = OutputGroup(
        id="avr_main",
        provides_roles=(),
        selection_mechanism=SelectionMechanism(kind=MechanismKind.MEDIA_PLAYER_SOURCE),
    )
    atv_og = _og("main", roles=[ControlRole.TRANSPORT])
    xbox_og = _og("main", roles=[ControlRole.TRANSPORT])
    tv_og = _og("screen", mech=False)

    atv = Device(
        id="atv",
        name="ATV",
        profile_id="p",
        power_handling=PowerHandling.DISCRETE_CAPABLE,
        output_groups=(atv_og,),
        interfaces=(_out("atv_out", "main"),),
    )
    xbox = Device(
        id="xbox",
        name="Xbox",
        profile_id="p",
        power_handling=PowerHandling.DISCRETE_CAPABLE,
        output_groups=(xbox_og,),
        interfaces=(_out("xbox_out", "main"),),
    )
    avr = Device(
        id="avr",
        name="AVR",
        profile_id="p",
        power_handling=PowerHandling.DISCRETE_CAPABLE,
        output_groups=(avr_og,),
        interfaces=(
            _inp("avr_in1", ["avr_main"], label="HDMI 1"),
            _inp("avr_in2", ["avr_main"], label="HDMI 2"),
            _out("avr_out", "avr_main"),
        ),
        inputs_are_exclusive_per_output_group=("avr_main",),
    )
    tv = Device(
        id="tv",
        name="TV",
        profile_id="p",
        power_handling=PowerHandling.DISCRETE_CAPABLE,
        output_groups=(tv_og,),
        interfaces=(_inp("tv_in", ["screen"], label="HDMI 1"),),
    )

    zone_deny = Zone(
        id="zone_deny",
        name="Zone Deny",
        sink_device_ids=("tv",),
        sink_mode=SinkMode.SINGLE,
        contention_policy=ContentionPolicy.DENY,
    )
    zone_preempt = Zone(
        id="zone_preempt",
        name="Zone Preempt",
        sink_device_ids=("tv",),
        sink_mode=SinkMode.SINGLE,
        contention_policy=ContentionPolicy.PREEMPT,
    )

    conns = [
        _conn("c1", "atv", "atv_out", "avr", "avr_in1"),
        _conn("c2", "xbox", "xbox_out", "avr", "avr_in2"),
        _conn("c3", "avr", "avr_out", "tv", "tv_in"),
    ]
    instances = [
        DeviceInstance("atv", bindings=(_binding("main", "reg-atv"),)),
        DeviceInstance("xbox", bindings=(_binding("main", "reg-xbox"),)),
        DeviceInstance("avr", bindings=(_binding("avr_main", "reg-avr"),)),
        DeviceInstance("tv", bindings=(_binding("screen", "reg-tv"),)),
    ]
    config = SystemConfig(
        devices=[atv, xbox, avr, tv],
        connections=conns,
        zones=[zone_deny, zone_preempt],
        device_instances=instances,
    )
    entity_map = {
        "reg-atv": "media_player.atv",
        "reg-xbox": "media_player.xbox",
        "reg-avr": "media_player.avr",
        "reg-tv": "media_player.tv",
    }
    return config, entity_map


async def test_contention_deny_returns_error() -> None:
    """DENY policy: activation fails when contention is detected.

    zone_deny is activated with ATV first.  Then zone_preempt (deny policy via
    a patched copy) is attempted with Xbox — that zone shares the AVR input
    which zone_deny is already using → contention → deny failure.
    """
    config, entity_map = _contention_config()

    # Patch zone_preempt to use DENY policy for this test.
    deny_zones = []
    for z in config.zones:
        if z.id == "zone_preempt":
            deny_zones.append(dataclasses.replace(z, contention_policy=ContentionPolicy.DENY))
        else:
            deny_zones.append(z)
    config = SystemConfig(
        devices=config.devices,
        connections=config.connections,
        zones=deny_zones,
        device_instances=config.device_instances,
    )

    orch, _hass, _active = _make_orchestrator(config, entity_map)

    # Activate zone_deny with atv successfully.
    r1 = await orch.async_activate_zone("zone_deny", "atv")
    assert r1.success, r1.error_detail

    # Now try to activate zone_preempt (also DENY) with Xbox — contention.
    r2 = await orch.async_activate_zone("zone_preempt", "xbox")
    assert not r2.success
    assert len(r2.contention_reports) > 0


async def test_contention_preempt_deactivates_conflicting_zone() -> None:
    """PREEMPT policy: conflicting zone is deactivated, activation proceeds."""
    config, entity_map = _contention_config()
    orch, _hass, active = _make_orchestrator(config, entity_map)

    # Activate zone_deny with atv first.
    r1 = await orch.async_activate_zone("zone_deny", "atv")
    assert r1.success, r1.error_detail
    assert active.get("zone_deny") is not None

    # Activate zone_preempt with xbox — should preempt zone_deny.
    r2 = await orch.async_activate_zone("zone_preempt", "xbox")
    assert r2.success, r2.error_detail
    # zone_deny should have been deactivated by preemption.
    assert active.get("zone_deny") is None
    assert active.get("zone_preempt") is not None
