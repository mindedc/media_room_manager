"""Tests for OutputGroup, Connection, VirtualSource, and Device dataclasses."""

from custom_components.media_room_manager.graph.model import (
    AuxEntity,
    Connection,
    ControlRole,
    Device,
    DynamicVirtualSources,
    Interface,
    InterfaceDirection,
    InterfaceType,
    MechanismKind,
    OutputGroup,
    PowerHandling,
    SelectionMechanism,
    VirtualSource,
)


def test_selection_mechanism_construction() -> None:
    mech = SelectionMechanism(
        kind=MechanismKind.MEDIA_PLAYER_SOURCE,
        expected_domain="media_player",
        expected_features=("turn_on", "turn_off", "select_source"),
    )
    assert mech.kind == MechanismKind.MEDIA_PLAYER_SOURCE
    assert mech.expected_domain == "media_player"
    assert "turn_on" in mech.expected_features


def test_output_group_construction() -> None:
    og = OutputGroup(
        id="main",
        provides_roles=(ControlRole.POWER, ControlRole.VOLUME),
        selection_mechanism=SelectionMechanism(kind=MechanismKind.SELECT_ENTITY),
    )
    assert og.id == "main"
    assert ControlRole.POWER in og.provides_roles
    assert og.selection_mechanism is not None


def test_output_group_no_mechanism() -> None:
    """Passive transit devices have no selection mechanism."""
    og = OutputGroup(id="main")
    assert og.selection_mechanism is None
    assert og.provides_roles == ()


def test_connection_construction() -> None:
    conn = Connection(
        id="apple_tv_to_avr",
        from_device_id="apple_tv",
        from_interface_id="hdmi_out",
        to_device_id="avr",
        to_interface_id="hdmi_in_1",
    )
    assert conn.from_device_id == "apple_tv"
    assert conn.to_device_id == "avr"


def test_connection_frozen() -> None:
    conn = Connection("id", "dev_a", "out_1", "dev_b", "in_1")
    try:
        conn.from_device_id = "other"  # type: ignore[misc]
        raise AssertionError("Should have raised FrozenInstanceError")
    except AssertionError:
        raise
    except Exception:
        pass


def test_virtual_source_construction() -> None:
    vs = VirtualSource(id="tuner", label="Tuner", routable_to_output_group=("main", "zone_2"))
    assert vs.id == "tuner"
    assert "main" in vs.routable_to_output_group


def test_dynamic_virtual_sources() -> None:
    dvs = DynamicVirtualSources(
        source="source_list_minus_known",
        output_group="main",
        exclude=("Settings", "Search"),
    )
    assert dvs.source == "source_list_minus_known"
    assert "Settings" in dvs.exclude


def test_aux_entity_construction() -> None:
    aux = AuxEntity(
        id="ir_blaster",
        expected_domain="remote",
        expected_commands=("POWER", "PLAY", "PAUSE"),
    )
    assert aux.expected_domain == "remote"
    assert "POWER" in aux.expected_commands


def test_device_construction_minimal() -> None:
    """Device with minimal fields."""
    dev = Device(id="atv", name="Apple TV", profile_id="apple/apple-tv-4k")
    assert dev.id == "atv"
    assert dev.profile_id == "apple/apple-tv-4k"
    assert dev.power_handling == PowerHandling.DISABLED
    assert dev.power_on_delay == 0
    assert dev.exclusive_outputs is False
    assert dev.output_groups == ()
    assert dev.interfaces == ()


def test_device_construction_full() -> None:
    """Device with all fields populated."""
    iface = Interface(
        id="hdmi_out",
        direction=InterfaceDirection.OUTPUT,
        type=InterfaceType.HDMI,
        label="HDMI OUT",
        output_group="main",
    )
    og = OutputGroup(
        id="main",
        provides_roles=(ControlRole.TRANSPORT, ControlRole.METADATA_SOURCE),
    )
    vs = VirtualSource(id="tuner", label="Tuner", routable_to_output_group=("main",))
    dvs = DynamicVirtualSources(source="source_list_minus_known", output_group="main")

    dev = Device(
        id="avr",
        name="Marantz SR8015",
        profile_id="marantz/sr8015",
        power_handling=PowerHandling.DISCRETE_CAPABLE,
        power_on_delay=4,
        output_groups=(og,),
        interfaces=(iface,),
        virtual_sources=(vs,),
        dynamic_virtual_sources=dvs,
        inputs_are_exclusive_per_output_group=("main",),
    )
    assert dev.power_handling == PowerHandling.DISCRETE_CAPABLE
    assert dev.power_on_delay == 4
    assert len(dev.output_groups) == 1
    assert len(dev.interfaces) == 1
    assert dev.dynamic_virtual_sources is not None


def test_device_frozen() -> None:
    dev = Device(id="d", name="Dev", profile_id="p")
    try:
        dev.name = "Other"  # type: ignore[misc]
        raise AssertionError("Should have raised FrozenInstanceError")
    except AssertionError:
        raise
    except Exception:
        pass


def test_power_handling_values() -> None:
    assert PowerHandling.DISCRETE_CAPABLE == "discrete_capable"
    assert PowerHandling.TOGGLE == "toggle"
    assert PowerHandling.ALWAYS_ON == "always_on"
    assert PowerHandling.DISABLED == "disabled"


def test_control_role_values() -> None:
    assert ControlRole.TRANSPORT == "transport"
    assert ControlRole.VOLUME == "volume"
    assert ControlRole.METADATA_SOURCE == "metadata_source"
    assert ControlRole.POWER == "power"
    assert ControlRole.SOURCE_SELECTION == "source_selection"


def test_mechanism_kind_values() -> None:
    assert MechanismKind.MEDIA_PLAYER_SOURCE == "media_player_source"
    assert MechanismKind.SELECT_ENTITY == "select_entity"
    assert MechanismKind.SWITCH_COMBO == "switch_combo"
    assert MechanismKind.REMOTE_COMMAND == "remote_command"
    assert MechanismKind.SERVICE_CALL == "service_call"
