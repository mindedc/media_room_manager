"""Tests for graph model voluptuous schemas and round-trip serialization."""

import pytest
import voluptuous as vol

from custom_components.media_room_manager.graph.schema import (
    connection_from_dict,
    connection_to_dict,
    device_from_dict,
    device_instance_from_dict,
    device_instance_to_dict,
    device_to_dict,
    instance_binding_from_dict,
    instance_binding_to_dict,
    interface_from_dict,
    interface_to_dict,
    output_group_from_dict,
    output_group_to_dict,
    source_visibility_from_dict,
    source_visibility_to_dict,
    virtual_source_from_dict,
    virtual_source_to_dict,
    zone_from_dict,
    zone_to_dict,
)

# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------


def test_interface_roundtrip_output() -> None:
    d = {
        "id": "hdmi_out",
        "direction": "output",
        "type": "hdmi",
        "label": "HDMI OUT",
        "output_group": "main",
    }
    iface = interface_from_dict(d)
    assert iface.id == "hdmi_out"
    assert iface.output_group == "main"
    assert interface_to_dict(iface)["id"] == "hdmi_out"


def test_interface_roundtrip_input() -> None:
    d = {
        "id": "hdmi_in_1",
        "direction": "input",
        "type": "hdmi",
        "label": "HDMI IN 1",
        "routable_to_output_group": ["main", "zone_2"],
    }
    iface = interface_from_dict(d)
    assert iface.routable_to_output_group == ("main", "zone_2")
    serialized = interface_to_dict(iface)
    assert serialized["routable_to_output_group"] == ["main", "zone_2"]


def test_interface_invalid_direction() -> None:
    with pytest.raises(vol.Invalid):
        interface_from_dict({"id": "x", "direction": "sideways", "type": "hdmi", "label": "X"})


def test_interface_invalid_type() -> None:
    with pytest.raises(vol.Invalid):
        interface_from_dict({"id": "x", "direction": "input", "type": "usb", "label": "X"})


def test_interface_missing_required() -> None:
    with pytest.raises(vol.Invalid):
        interface_from_dict({"id": "x", "direction": "input"})


# ---------------------------------------------------------------------------
# OutputGroup
# ---------------------------------------------------------------------------


def test_output_group_roundtrip() -> None:
    d = {
        "id": "main",
        "provides_roles": ["power", "volume"],
        "selection_mechanism": {
            "kind": "media_player_source",
            "expected_domain": "media_player",
            "expected_features": ["turn_on", "turn_off"],
        },
    }
    og = output_group_from_dict(d)
    assert og.id == "main"
    assert len(og.provides_roles) == 2
    assert og.selection_mechanism is not None

    back = output_group_to_dict(og)
    assert back["id"] == "main"
    assert back["selection_mechanism"]["kind"] == "media_player_source"


def test_output_group_no_mechanism_roundtrip() -> None:
    d = {"id": "main"}
    og = output_group_from_dict(d)
    assert og.selection_mechanism is None
    assert output_group_to_dict(og)["selection_mechanism"] is None


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------


def test_connection_roundtrip() -> None:
    d = {
        "id": "conn_1",
        "from_device_id": "atv",
        "from_interface_id": "hdmi_out",
        "to_device_id": "avr",
        "to_interface_id": "hdmi_in_1",
    }
    conn = connection_from_dict(d)
    assert conn.id == "conn_1"
    back = connection_to_dict(conn)
    assert back == d


def test_connection_missing_field() -> None:
    with pytest.raises(vol.Invalid):
        connection_from_dict({"id": "c", "from_device_id": "a"})


# ---------------------------------------------------------------------------
# VirtualSource
# ---------------------------------------------------------------------------


def test_virtual_source_roundtrip() -> None:
    d = {"id": "tuner", "label": "Tuner", "routable_to_output_group": ["main"]}
    vs = virtual_source_from_dict(d)
    assert vs.label == "Tuner"
    back = virtual_source_to_dict(vs)
    assert back["routable_to_output_group"] == ["main"]


# ---------------------------------------------------------------------------
# Device
# ---------------------------------------------------------------------------


def test_device_minimal_roundtrip() -> None:
    d = {"id": "atv", "name": "Apple TV", "profile_id": "apple/apple-tv-4k"}
    dev = device_from_dict(d)
    assert dev.id == "atv"
    assert dev.power_handling.value == "disabled"
    back = device_to_dict(dev)
    assert back["id"] == "atv"
    assert back["power_on_delay"] == 0
    assert back["exclusive_outputs"] is False


def test_device_full_roundtrip() -> None:
    d = {
        "id": "avr",
        "name": "Marantz SR8015",
        "profile_id": "marantz/sr8015",
        "power_handling": "discrete_capable",
        "power_on_delay": 4,
        "exclusive_outputs": False,
        "output_groups": [
            {
                "id": "main",
                "provides_roles": ["power", "volume", "source_selection"],
                "selection_mechanism": {
                    "kind": "media_player_source",
                    "expected_domain": "media_player",
                },
            }
        ],
        "interfaces": [
            {
                "id": "hdmi_in_1",
                "direction": "input",
                "type": "hdmi",
                "label": "CBL/SAT",
                "routable_to_output_group": ["main"],
            }
        ],
        "virtual_sources": [
            {"id": "tuner", "label": "Tuner", "routable_to_output_group": ["main"]}
        ],
        "dynamic_virtual_sources": {
            "source": "source_list_minus_known",
            "output_group": "main",
            "exclude": ["Internet Radio"],
        },
        "aux_entities": [],
        "inputs_are_exclusive_per_output_group": ["main"],
    }
    dev = device_from_dict(d)
    assert dev.power_on_delay == 4
    assert len(dev.output_groups) == 1
    assert len(dev.virtual_sources) == 1
    assert dev.dynamic_virtual_sources is not None

    back = device_to_dict(dev)
    dev2 = device_from_dict(back)
    assert dev == dev2


def test_device_invalid_power_handling() -> None:
    with pytest.raises(vol.Invalid):
        device_from_dict({"id": "x", "name": "X", "profile_id": "p", "power_handling": "sleep"})


def test_device_negative_delay_rejected() -> None:
    with pytest.raises(vol.Invalid):
        device_from_dict({"id": "x", "name": "X", "profile_id": "p", "power_on_delay": -1})


# ---------------------------------------------------------------------------
# Zone
# ---------------------------------------------------------------------------


def test_zone_roundtrip() -> None:
    d = {
        "id": "theater",
        "name": "Theater",
        "sink_device_ids": ["tv"],
        "sink_mode": "single",
        "volume_authority_device_id": "avr",
        "volume_authority_output_group_id": "main",
        "contention_policy": "deny",
    }
    zone = zone_from_dict(d)
    assert zone.sink_mode.value == "single"
    back = zone_to_dict(zone)
    zone2 = zone_from_dict(back)
    assert zone == zone2


def test_zone_invalid_sink_mode() -> None:
    with pytest.raises(vol.Invalid):
        zone_from_dict({"id": "z", "name": "Z", "sink_mode": "mirror"})


# ---------------------------------------------------------------------------
# InstanceBinding / DeviceInstance
# ---------------------------------------------------------------------------


def test_instance_binding_roundtrip() -> None:
    d = {
        "output_group_id": "main",
        "entity_registry_id": "uuid-abc",
        "label_remaps": [["HDMI 1", "Apple TV"]],
    }
    binding = instance_binding_from_dict(d)
    assert binding.label_remaps == (("HDMI 1", "Apple TV"),)
    back = instance_binding_to_dict(binding)
    assert back["label_remaps"] == [["HDMI 1", "Apple TV"]]


def test_device_instance_roundtrip() -> None:
    d = {
        "device_id": "avr",
        "bindings": [{"output_group_id": "main", "entity_registry_id": "uuid-1"}],
        "power_handling_override": "always_on",
    }
    inst = device_instance_from_dict(d)
    assert inst.power_handling_override is not None
    back = device_instance_to_dict(inst)
    inst2 = device_instance_from_dict(back)
    assert inst == inst2


# ---------------------------------------------------------------------------
# SourceVisibilitySelection
# ---------------------------------------------------------------------------


def test_source_visibility_roundtrip() -> None:
    d = {
        "zone_id": "living_room",
        "visible_sources": [
            {"device_id": "apple_tv"},
            {"device_id": "avr", "virtual_source_id": "tuner", "display_name": "Tuner"},
        ],
    }
    sel = source_visibility_from_dict(d)
    assert sel.zone_id == "living_room"
    assert len(sel.visible_sources) == 2
    back = source_visibility_to_dict(sel)
    sel2 = source_visibility_from_dict(back)
    assert sel == sel2
