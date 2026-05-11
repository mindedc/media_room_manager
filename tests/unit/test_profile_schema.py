"""Tests for the profile voluptuous schema and profile_from_dict."""

from __future__ import annotations

import pytest
import voluptuous as vol

from custom_components.media_room_manager.graph.model import (
    InterfaceDirection,
    InterfaceType,
    PowerHandling,
)
from custom_components.media_room_manager.profiles.schema import (
    profile_from_dict,
    profile_to_dict,
)
from custom_components.media_room_manager.profiles.types import ProfileCategory

# ---------------------------------------------------------------------------
# Minimal valid profile fixture
# ---------------------------------------------------------------------------

_MINIMAL = {
    "profile_id": "test/minimal",
    "schema_version": 1,
    "manufacturer": "Test Co",
    "model": "Model X",
    "category": "source",
    "power_handling": "discrete_capable",
}


def test_minimal_profile_parses() -> None:
    """A minimal profile dict with only required fields should parse cleanly."""
    p = profile_from_dict(_MINIMAL)
    assert p.profile_id == "test/minimal"
    assert p.schema_version == 1
    assert p.manufacturer == "Test Co"
    assert p.model == "Model X"
    assert p.category == ProfileCategory.SOURCE
    assert p.power_handling == PowerHandling.DISCRETE_CAPABLE
    assert p.power_on_delay == 0
    assert p.exclusive_outputs is False
    assert p.output_groups == ()
    assert p.interfaces == ()


def test_power_handling_defaults_to_disabled_when_omitted() -> None:
    """power_handling should default to 'disabled' when not specified."""
    d = {**_MINIMAL}
    del d["power_handling"]
    p = profile_from_dict(d)
    assert p.power_handling == PowerHandling.DISABLED


def test_all_power_handling_values_accepted() -> None:
    """All four power_handling values should be valid."""
    for value in ("discrete_capable", "toggle", "always_on", "disabled"):
        p = profile_from_dict({**_MINIMAL, "power_handling": value})
        assert p.power_handling == PowerHandling(value)


def test_invalid_power_handling_rejected() -> None:
    """An unrecognized power_handling value should raise vol.Invalid."""
    with pytest.raises(vol.Invalid):
        profile_from_dict({**_MINIMAL, "power_handling": "unknown_value"})


def test_invalid_category_rejected() -> None:
    """An unrecognized category value should raise vol.Invalid."""
    with pytest.raises(vol.Invalid):
        profile_from_dict({**_MINIMAL, "category": "not_a_category"})


def test_missing_required_field_raises() -> None:
    """Missing profile_id should raise vol.Invalid."""
    d = {k: v for k, v in _MINIMAL.items() if k != "profile_id"}
    with pytest.raises(vol.Invalid):
        profile_from_dict(d)


# ---------------------------------------------------------------------------
# Output groups
# ---------------------------------------------------------------------------


def test_output_group_with_selection_mechanism() -> None:
    """An output group with a select_entity mechanism should parse correctly."""
    d = {
        **_MINIMAL,
        "output_groups": [
            {
                "id": "out_1",
                "selection_mechanism": {
                    "kind": "select_entity",
                    "expected_domain": "select",
                    "expected_options": ["Input 1", "Input 2"],
                },
            }
        ],
    }
    p = profile_from_dict(d)
    assert len(p.output_groups) == 1
    og = p.output_groups[0]
    assert og.id == "out_1"
    assert og.selection_mechanism is not None
    assert og.selection_mechanism.kind == "select_entity"
    assert og.selection_mechanism.expected_options == ("Input 1", "Input 2")


def test_output_group_without_selection_mechanism() -> None:
    """An output group with no selection_mechanism is valid (passive device)."""
    d = {**_MINIMAL, "output_groups": [{"id": "main"}]}
    p = profile_from_dict(d)
    assert p.output_groups[0].selection_mechanism is None


def test_output_group_provides_roles() -> None:
    """provides_roles should be stored as a tuple of role strings."""
    d = {
        **_MINIMAL,
        "output_groups": [
            {
                "id": "main",
                "selection_mechanism": {
                    "kind": "media_player_source",
                    "expected_domain": "media_player",
                },
                "provides_roles": ["power", "volume", "source_selection"],
            }
        ],
    }
    p = profile_from_dict(d)
    assert set(p.output_groups[0].provides_roles) == {"power", "volume", "source_selection"}


def test_invalid_mechanism_kind_rejected() -> None:
    """An unrecognized mechanism kind should raise vol.Invalid."""
    d = {
        **_MINIMAL,
        "output_groups": [{"id": "out", "selection_mechanism": {"kind": "telepathy"}}],
    }
    with pytest.raises(vol.Invalid):
        profile_from_dict(d)


# ---------------------------------------------------------------------------
# Interfaces
# ---------------------------------------------------------------------------


def test_hdmi_input_interface() -> None:
    """An HDMI input interface with routable_to_output_group should parse."""
    d = {
        **_MINIMAL,
        "output_groups": [{"id": "main"}],
        "interfaces": [
            {
                "id": "hdmi_in_1",
                "direction": "input",
                "type": "hdmi",
                "label": "HDMI 1",
                "routable_to_output_group": ["main"],
            }
        ],
    }
    p = profile_from_dict(d)
    iface = p.interfaces[0]
    assert iface.id == "hdmi_in_1"
    assert iface.direction == InterfaceDirection.INPUT
    assert iface.type == InterfaceType.HDMI
    assert iface.routable_to_output_group == ("main",)
    assert iface.output_group is None


def test_output_interface() -> None:
    """An output interface with output_group should parse."""
    d = {
        **_MINIMAL,
        "output_groups": [{"id": "main"}],
        "interfaces": [
            {
                "id": "hdmi_out",
                "direction": "output",
                "type": "hdmi_audio_return",
                "label": "HDMI OUT",
                "output_group": "main",
            }
        ],
    }
    p = profile_from_dict(d)
    iface = p.interfaces[0]
    assert iface.direction == InterfaceDirection.OUTPUT
    assert iface.type == InterfaceType.HDMI_AUDIO_RETURN
    assert iface.output_group == "main"


def test_invalid_interface_type_rejected() -> None:
    """An unrecognized interface type should raise vol.Invalid."""
    d = {
        **_MINIMAL,
        "interfaces": [
            {
                "id": "weird",
                "direction": "input",
                "type": "telegraph",
                "label": "Old School",
            }
        ],
    }
    with pytest.raises(vol.Invalid):
        profile_from_dict(d)


# ---------------------------------------------------------------------------
# Virtual sources
# ---------------------------------------------------------------------------


def test_static_virtual_source() -> None:
    """A static virtual source should parse with id, label, and routing."""
    d = {
        **_MINIMAL,
        "output_groups": [{"id": "main"}],
        "virtual_sources": [
            {"id": "tuner", "label": "Tuner", "routable_to_output_group": ["main"]}
        ],
    }
    p = profile_from_dict(d)
    assert len(p.virtual_sources) == 1
    vs = p.virtual_sources[0]
    assert vs.id == "tuner"
    assert vs.routable_to_output_group == ("main",)


def test_dynamic_virtual_sources() -> None:
    """dynamic_virtual_sources block should parse with source, output_group, exclude."""
    d = {
        **_MINIMAL,
        "output_groups": [{"id": "main"}],
        "dynamic_virtual_sources": {
            "source": "source_list_minus_known",
            "output_group": "main",
            "exclude": ["Internet Radio"],
        },
    }
    p = profile_from_dict(d)
    assert p.dynamic_virtual_sources is not None
    dvs = p.dynamic_virtual_sources
    assert dvs.source == "source_list_minus_known"
    assert dvs.output_group == "main"
    assert dvs.exclude == ("Internet Radio",)


# ---------------------------------------------------------------------------
# Discovery block
# ---------------------------------------------------------------------------


def test_discovery_block_with_anchor() -> None:
    """A discovery block with an anchor signal should parse."""
    d = {
        **_MINIMAL,
        "output_groups": [{"id": "main"}],
        "discovery": {
            "output_groups": [
                {
                    "output_group": "main",
                    "is_discovery_anchor": True,
                    "match_threshold": 60,
                    "signals": [
                        {
                            "kind": "device_registry",
                            "manufacturer": "Test Co",
                            "model_patterns": ["Model X"],
                            "weight": 100,
                        }
                    ],
                }
            ]
        },
    }
    p = profile_from_dict(d)
    assert p.discovery is not None
    entry = p.discovery.output_groups[0]
    assert entry.is_discovery_anchor is True
    assert entry.match_threshold == 60
    sig = entry.signals[0]
    assert sig.kind == "device_registry"
    assert sig.manufacturer == "Test Co"
    assert sig.weight == 100


def test_invalid_signal_kind_rejected() -> None:
    """An unrecognized discovery signal kind should raise vol.Invalid."""
    d = {
        **_MINIMAL,
        "discovery": {
            "output_groups": [
                {
                    "output_group": "main",
                    "signals": [{"kind": "magic", "weight": 50}],
                }
            ]
        },
    }
    with pytest.raises(vol.Invalid):
        profile_from_dict(d)


# ---------------------------------------------------------------------------
# profile_to_dict round-trip
# ---------------------------------------------------------------------------


def test_profile_to_dict_round_trip() -> None:
    """profile_to_dict should produce a dict that profile_from_dict re-parses correctly."""
    d = {
        **_MINIMAL,
        "output_groups": [
            {
                "id": "main",
                "selection_mechanism": {
                    "kind": "media_player_source",
                    "expected_domain": "media_player",
                    "expected_features": ["turn_on", "select_source"],
                },
                "provides_roles": ["power", "volume"],
            }
        ],
        "interfaces": [
            {
                "id": "hdmi_in_1",
                "direction": "input",
                "type": "hdmi",
                "label": "HDMI 1",
                "routable_to_output_group": ["main"],
            },
            {
                "id": "hdmi_out",
                "direction": "output",
                "type": "hdmi_audio_return",
                "label": "HDMI OUT",
                "output_group": "main",
            },
        ],
        "dynamic_virtual_sources": {
            "source": "source_list_minus_known",
            "output_group": "main",
            "exclude": ["Internet Radio"],
        },
    }
    profile = profile_from_dict(d)
    serialized = profile_to_dict(profile)

    assert serialized["profile_id"] == "test/minimal"
    assert serialized["category"] == "source"
    assert serialized["power_handling"] == "discrete_capable"
    assert len(serialized["output_groups"]) == 1
    assert len(serialized["interfaces"]) == 2
    assert serialized["dynamic_virtual_sources"]["source"] == "source_list_minus_known"

    # Round-trip: deserialize again and confirm equality
    profile2 = profile_from_dict(serialized)
    assert profile == profile2


def test_exclusive_outputs_flag() -> None:
    """exclusive_outputs: true should be parsed and preserved."""
    d = {**_MINIMAL, "exclusive_outputs": True}
    p = profile_from_dict(d)
    assert p.exclusive_outputs is True
    serialized = profile_to_dict(p)
    assert serialized["exclusive_outputs"] is True


def test_inputs_are_exclusive_per_output_group() -> None:
    """inputs_are_exclusive_per_output_group should be a tuple of output group ids."""
    d = {
        **_MINIMAL,
        "output_groups": [{"id": "main"}, {"id": "zone_2"}],
        "inputs_are_exclusive_per_output_group": ["main", "zone_2"],
    }
    p = profile_from_dict(d)
    assert set(p.inputs_are_exclusive_per_output_group) == {"main", "zone_2"}
