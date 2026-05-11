"""Integration test: all 10 bundled profiles load without errors.

Verifies that the ProfileRegistry loads each bundled profile and that every
profile meets basic structural correctness requirements without needing a live
Home Assistant instance.
"""

from __future__ import annotations

import pytest

from custom_components.media_room_manager.graph.model import (
    InterfaceDirection,
    PowerHandling,
)
from custom_components.media_room_manager.profiles.registry import ProfileRegistry
from custom_components.media_room_manager.profiles.types import (
    ProfileCategory,
)


@pytest.fixture(scope="module")
def registry() -> ProfileRegistry:
    """Shared registry with bundled profiles loaded once for the module."""
    r = ProfileRegistry()
    r.load_bundled()
    return r


# ---------------------------------------------------------------------------
# Registry-level assertions
# ---------------------------------------------------------------------------


def test_exactly_ten_profiles_loaded(registry: ProfileRegistry) -> None:
    assert len(registry) == 10


@pytest.mark.parametrize(
    "profile_id",
    [
        "apple/apple-tv-4k",
        "anthem/mrx-740",
        "denon/avr-x1700h",
        "generic/hdmi-audio-extractor",
        "generic/hdmi-splitter-1x4",
        "hdfury/diva",
        "lumagen/radiance-pro",
        "marantz/sr8015",
        "monoprice/blackbird-8x8",
        "sony/dvp-ns500v",
    ],
)
def test_each_profile_is_accessible(registry: ProfileRegistry, profile_id: str) -> None:
    assert registry.get(profile_id) is not None


# ---------------------------------------------------------------------------
# Per-profile structural assertions
# ---------------------------------------------------------------------------


def test_apple_tv_4k(registry: ProfileRegistry) -> None:
    p = registry.get("apple/apple-tv-4k")
    assert p is not None
    assert p.category == ProfileCategory.SOURCE
    assert p.power_handling == PowerHandling.DISCRETE_CAPABLE
    assert p.dynamic_virtual_sources is not None
    assert p.dynamic_virtual_sources.source == "source_list_minus_known"
    assert len(p.output_groups) >= 1
    # At least one output interface (HDMI out)
    outputs = [i for i in p.interfaces if i.direction == InterfaceDirection.OUTPUT]
    assert len(outputs) >= 1


def test_anthem_mrx_740(registry: ProfileRegistry) -> None:
    p = registry.get("anthem/mrx-740")
    assert p is not None
    assert p.category == ProfileCategory.AVR
    assert p.power_handling == PowerHandling.DISCRETE_CAPABLE
    og_ids = {og.id for og in p.output_groups}
    assert "main" in og_ids
    assert "zone_2" in og_ids
    assert p.discovery is not None


def test_denon_avr_x1700h(registry: ProfileRegistry) -> None:
    p = registry.get("denon/avr-x1700h")
    assert p is not None
    assert p.category == ProfileCategory.AVR
    assert len(p.output_groups) == 1
    assert p.output_groups[0].id == "main"
    assert p.dynamic_virtual_sources is not None
    assert p.discovery is not None
    # Verify at least one HDMI input declared
    from custom_components.media_room_manager.graph.model import InterfaceType

    hdmi_inputs = [
        i
        for i in p.interfaces
        if i.direction == InterfaceDirection.INPUT and i.type == InterfaceType.HDMI
    ]
    assert len(hdmi_inputs) >= 1


def test_generic_hdmi_audio_extractor(registry: ProfileRegistry) -> None:
    p = registry.get("generic/hdmi-audio-extractor")
    assert p is not None
    assert p.category == ProfileCategory.PASSIVE_CONVERTER
    assert p.power_handling == PowerHandling.DISABLED
    assert len(p.output_groups) == 1
    assert p.output_groups[0].selection_mechanism is None
    outputs = [i for i in p.interfaces if i.direction == InterfaceDirection.OUTPUT]
    assert len(outputs) == 4
    inputs = [i for i in p.interfaces if i.direction == InterfaceDirection.INPUT]
    assert len(inputs) == 1


def test_generic_hdmi_splitter_1x4(registry: ProfileRegistry) -> None:
    p = registry.get("generic/hdmi-splitter-1x4")
    assert p is not None
    assert p.category == ProfileCategory.PASSIVE_CONVERTER
    assert p.power_handling == PowerHandling.DISABLED
    assert len(p.output_groups) == 1
    assert p.output_groups[0].selection_mechanism is None
    outputs = [i for i in p.interfaces if i.direction == InterfaceDirection.OUTPUT]
    assert len(outputs) == 4
    inputs = [i for i in p.interfaces if i.direction == InterfaceDirection.INPUT]
    assert len(inputs) == 1


def test_hdfury_diva(registry: ProfileRegistry) -> None:
    p = registry.get("hdfury/diva")
    assert p is not None
    assert p.category == ProfileCategory.MATRIX
    og_ids = {og.id for og in p.output_groups}
    assert "tx0" in og_ids
    assert "tx1" in og_ids
    # TX0 has audio extraction outputs; check tx0 has more than just hdmi_out
    tx0_outputs = [
        i
        for i in p.interfaces
        if i.direction == InterfaceDirection.OUTPUT and i.output_group == "tx0"
    ]
    assert len(tx0_outputs) >= 2
    assert p.aux_entities


def test_lumagen_radiance_pro(registry: ProfileRegistry) -> None:
    p = registry.get("lumagen/radiance-pro")
    assert p is not None
    assert p.category == ProfileCategory.VIDEO_PROCESSOR
    assert p.power_handling == PowerHandling.DISCRETE_CAPABLE
    assert p.exclusive_outputs is True
    assert p.power_on_delay > 0
    assert len(p.output_groups) == 1
    assert "main" in p.inputs_are_exclusive_per_output_group
    outputs = [i for i in p.interfaces if i.direction == InterfaceDirection.OUTPUT]
    assert len(outputs) == 2
    inputs = [i for i in p.interfaces if i.direction == InterfaceDirection.INPUT]
    assert len(inputs) == 8


def test_marantz_sr8015(registry: ProfileRegistry) -> None:
    p = registry.get("marantz/sr8015")
    assert p is not None
    assert p.category == ProfileCategory.AVR
    og_ids = {og.id for og in p.output_groups}
    assert og_ids == {"main", "zone_2"}
    assert "main" in p.inputs_are_exclusive_per_output_group
    assert "zone_2" in p.inputs_are_exclusive_per_output_group
    # Has a static virtual source (Tuner)
    assert len(p.virtual_sources) >= 1
    assert p.dynamic_virtual_sources is not None
    assert p.discovery is not None
    # Verify zone_2 output group is optional in discovery
    zone2_entries = [e for e in p.discovery.output_groups if e.output_group == "zone_2"]
    assert len(zone2_entries) == 1
    assert zone2_entries[0].optional is True


def test_monoprice_blackbird_8x8(registry: ProfileRegistry) -> None:
    p = registry.get("monoprice/blackbird-8x8")
    assert p is not None
    assert p.category == ProfileCategory.MATRIX
    assert len(p.output_groups) == 8
    assert p.aux_entities  # power switch
    # Each output group uses select_entity mechanism
    for og in p.output_groups:
        assert og.selection_mechanism is not None
        assert og.selection_mechanism.kind == "select_entity"
    # 8 inputs + 8 outputs = 16 interfaces
    outputs = [i for i in p.interfaces if i.direction == InterfaceDirection.OUTPUT]
    inputs = [i for i in p.interfaces if i.direction == InterfaceDirection.INPUT]
    assert len(outputs) == 8
    assert len(inputs) == 8


def test_sony_dvp_ns500v(registry: ProfileRegistry) -> None:
    p = registry.get("sony/dvp-ns500v")
    assert p is not None
    assert p.category == ProfileCategory.SOURCE
    assert p.power_handling == PowerHandling.TOGGLE
    # Has aux entity for the IR blaster remote
    assert p.aux_entities
    remote_aux = [ae for ae in p.aux_entities if ae.expected_domain == "remote"]
    assert len(remote_aux) >= 1
    assert len(p.output_groups) >= 1
