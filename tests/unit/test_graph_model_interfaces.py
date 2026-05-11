"""Tests for InterfaceType, InterfaceDirection, and Interface dataclasses."""

from custom_components.media_room_manager.graph.model import (
    AUDIO_TYPES,
    VIDEO_TYPES,
    Interface,
    InterfaceDirection,
    InterfaceType,
)


def test_interface_type_values() -> None:
    """All expected type values are present."""
    assert InterfaceType.HDMI == "hdmi"
    assert InterfaceType.HDMI_AUDIO_RETURN == "hdmi_audio_return"
    assert InterfaceType.OPTICAL_AUDIO == "optical_audio"
    assert InterfaceType.COAX_AUDIO == "coax_audio"
    assert InterfaceType.RCA_AUDIO == "rca_audio"
    assert InterfaceType.XLR_AUDIO == "xlr_audio"
    assert InterfaceType.COMPONENT_VIDEO == "component_video"
    assert InterfaceType.COMPOSITE_VIDEO == "composite_video"


def test_interface_direction_values() -> None:
    assert InterfaceDirection.INPUT == "input"
    assert InterfaceDirection.OUTPUT == "output"


def test_audio_types_set() -> None:
    assert InterfaceType.HDMI in AUDIO_TYPES
    assert InterfaceType.HDMI_AUDIO_RETURN in AUDIO_TYPES
    assert InterfaceType.OPTICAL_AUDIO in AUDIO_TYPES
    assert InterfaceType.COAX_AUDIO in AUDIO_TYPES
    assert InterfaceType.RCA_AUDIO in AUDIO_TYPES
    assert InterfaceType.XLR_AUDIO in AUDIO_TYPES
    assert InterfaceType.COMPONENT_VIDEO not in AUDIO_TYPES
    assert InterfaceType.COMPOSITE_VIDEO not in AUDIO_TYPES


def test_video_types_set() -> None:
    assert InterfaceType.HDMI in VIDEO_TYPES
    assert InterfaceType.HDMI_AUDIO_RETURN in VIDEO_TYPES
    assert InterfaceType.COMPONENT_VIDEO in VIDEO_TYPES
    assert InterfaceType.COMPOSITE_VIDEO in VIDEO_TYPES
    assert InterfaceType.OPTICAL_AUDIO not in VIDEO_TYPES
    assert InterfaceType.RCA_AUDIO not in VIDEO_TYPES


def test_interface_construction_output() -> None:
    """Output interface construction with output_group."""
    iface = Interface(
        id="hdmi_out_1",
        direction=InterfaceDirection.OUTPUT,
        type=InterfaceType.HDMI,
        label="HDMI OUT 1",
        output_group="main",
    )
    assert iface.id == "hdmi_out_1"
    assert iface.direction == InterfaceDirection.OUTPUT
    assert iface.type == InterfaceType.HDMI
    assert iface.label == "HDMI OUT 1"
    assert iface.output_group == "main"
    assert iface.routable_to_output_group == ()


def test_interface_construction_input() -> None:
    """Input interface construction with routable_to_output_group."""
    iface = Interface(
        id="hdmi_in_1",
        direction=InterfaceDirection.INPUT,
        type=InterfaceType.HDMI,
        label="HDMI IN 1",
        routable_to_output_group=("main", "zone_2"),
    )
    assert iface.routable_to_output_group == ("main", "zone_2")
    assert iface.output_group is None


def test_interface_carries_audio() -> None:
    hdmi = Interface("h", InterfaceDirection.OUTPUT, InterfaceType.HDMI, "HDMI")
    optical = Interface("o", InterfaceDirection.OUTPUT, InterfaceType.OPTICAL_AUDIO, "OPT")
    component = Interface("c", InterfaceDirection.OUTPUT, InterfaceType.COMPONENT_VIDEO, "COMP")

    assert hdmi.carries_audio() is True
    assert optical.carries_audio() is True
    assert component.carries_audio() is False


def test_interface_carries_video() -> None:
    hdmi = Interface("h", InterfaceDirection.OUTPUT, InterfaceType.HDMI, "HDMI")
    rca = Interface("r", InterfaceDirection.OUTPUT, InterfaceType.RCA_AUDIO, "RCA")
    composite = Interface("c", InterfaceDirection.OUTPUT, InterfaceType.COMPOSITE_VIDEO, "COMP")

    assert hdmi.carries_video() is True
    assert rca.carries_video() is False
    assert composite.carries_video() is True


def test_interface_frozen() -> None:
    """Interface is immutable."""
    iface = Interface("id", InterfaceDirection.INPUT, InterfaceType.HDMI, "HDMI")
    try:
        iface.id = "new_id"  # type: ignore[misc]
        raise AssertionError("Should have raised FrozenInstanceError")
    except AssertionError:
        raise
    except Exception:
        pass


def test_interface_equality() -> None:
    a = Interface("id", InterfaceDirection.INPUT, InterfaceType.HDMI, "HDMI")
    b = Interface("id", InterfaceDirection.INPUT, InterfaceType.HDMI, "HDMI")
    c = Interface("other", InterfaceDirection.INPUT, InterfaceType.HDMI, "HDMI")
    assert a == b
    assert a != c
