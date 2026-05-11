"""Tests for Zone, SourceVisibilitySelection, InstanceBinding, and supporting types."""

from custom_components.media_room_manager.graph.model import (
    ContentionPolicy,
    DeviceInstance,
    InstanceBinding,
    PowerHandling,
    SinkMode,
    SourceRef,
    SourceVisibilitySelection,
    Zone,
)


def test_sink_mode_values() -> None:
    assert SinkMode.SINGLE == "single"
    assert SinkMode.SIMULTANEOUS == "simultaneous"
    assert SinkMode.SELECTABLE_EXCLUSIVE == "selectable_exclusive"


def test_contention_policy_values() -> None:
    assert ContentionPolicy.DENY == "deny"
    assert ContentionPolicy.PREEMPT == "preempt"


def test_source_ref_physical() -> None:
    ref = SourceRef(device_id="apple_tv")
    assert ref.device_id == "apple_tv"
    assert ref.virtual_source_id is None
    assert ref.display_name is None


def test_source_ref_virtual_with_name() -> None:
    ref = SourceRef(device_id="avr", virtual_source_id="tuner", display_name="FM Radio")
    assert ref.virtual_source_id == "tuner"
    assert ref.display_name == "FM Radio"


def test_instance_binding_construction() -> None:
    binding = InstanceBinding(
        output_group_id="main",
        entity_registry_id="abc-123-uuid",
        label_remaps=(("HDMI 1", "Apple TV"),),
    )
    assert binding.entity_registry_id == "abc-123-uuid"
    assert binding.label_remaps == (("HDMI 1", "Apple TV"),)


def test_instance_binding_no_remaps() -> None:
    binding = InstanceBinding(output_group_id="main", entity_registry_id="uuid")
    assert binding.label_remaps == ()


def test_device_instance_construction() -> None:
    binding = InstanceBinding(output_group_id="main", entity_registry_id="uuid-1")
    inst = DeviceInstance(device_id="avr", bindings=(binding,))
    assert inst.device_id == "avr"
    assert len(inst.bindings) == 1
    assert inst.power_handling_override is None


def test_device_instance_power_override() -> None:
    inst = DeviceInstance(
        device_id="avr",
        power_handling_override=PowerHandling.ALWAYS_ON,
    )
    assert inst.power_handling_override == PowerHandling.ALWAYS_ON


def test_source_visibility_selection() -> None:
    refs = (
        SourceRef(device_id="apple_tv"),
        SourceRef(device_id="avr", virtual_source_id="tuner", display_name="Tuner"),
    )
    vis = SourceVisibilitySelection(zone_id="living_room", visible_sources=refs)
    assert vis.zone_id == "living_room"
    assert len(vis.visible_sources) == 2


def test_zone_minimal() -> None:
    zone = Zone(id="living_room", name="Living Room")
    assert zone.id == "living_room"
    assert zone.sink_mode == SinkMode.SINGLE
    assert zone.contention_policy == ContentionPolicy.DENY
    assert zone.volume_authority_device_id is None
    assert zone.sink_device_ids == ()


def test_zone_full() -> None:
    zone = Zone(
        id="theater",
        name="Theater",
        sink_device_ids=("tv", "projector"),
        sink_mode=SinkMode.SELECTABLE_EXCLUSIVE,
        volume_authority_device_id="avr",
        volume_authority_output_group_id="main",
        contention_policy=ContentionPolicy.PREEMPT,
        default_sink_device_id="projector",
    )
    assert zone.sink_mode == SinkMode.SELECTABLE_EXCLUSIVE
    assert zone.volume_authority_device_id == "avr"
    assert zone.default_sink_device_id == "projector"
    assert len(zone.sink_device_ids) == 2


def test_zone_frozen() -> None:
    zone = Zone(id="z", name="Z")
    try:
        zone.name = "other"  # type: ignore[misc]
        raise AssertionError("Should have raised FrozenInstanceError")
    except AssertionError:
        raise
    except Exception:
        pass
