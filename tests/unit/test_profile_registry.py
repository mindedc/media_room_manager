"""Tests for the ProfileRegistry."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from custom_components.media_room_manager.profiles.registry import ProfileRegistry


def _make_registry_with_bundled() -> ProfileRegistry:
    """Return a registry with all bundled profiles loaded."""
    r = ProfileRegistry()
    r.load_bundled()
    return r


def _write_profile(path: Path, profile_id: str, category: str = "source") -> None:
    """Write a minimal profile YAML to path."""
    path.write_text(
        textwrap.dedent(
            f"""
            profile_id: {profile_id}
            schema_version: 1
            manufacturer: Test Co
            model: Model X
            category: {category}
            """
        ),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Load bundled profiles
# ---------------------------------------------------------------------------


def test_load_bundled_succeeds() -> None:
    """load_bundled should populate the registry with all bundled profiles."""
    r = _make_registry_with_bundled()
    assert len(r) == 10


def test_all_expected_profiles_present() -> None:
    """All 10 starter profiles should be accessible by profile_id."""
    r = _make_registry_with_bundled()
    expected_ids = [
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
    ]
    for profile_id in expected_ids:
        assert r.get(profile_id) is not None, f"Missing profile: {profile_id}"


def test_get_returns_none_for_unknown_id() -> None:
    """get() should return None for an unregistered profile_id."""
    r = _make_registry_with_bundled()
    assert r.get("not/a/real/profile") is None


def test_list_all_sorted() -> None:
    """list_all() should return profiles sorted by profile_id."""
    r = _make_registry_with_bundled()
    all_profiles = r.list_all()
    ids = [p.profile_id for p in all_profiles]
    assert ids == sorted(ids)


def test_list_all_returns_all_profiles() -> None:
    """list_all() count should match len()."""
    r = _make_registry_with_bundled()
    assert len(r.list_all()) == len(r)


# ---------------------------------------------------------------------------
# Error tolerance (bad profile files)
# ---------------------------------------------------------------------------


def test_bad_profile_is_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A directory with one bad profile should skip it and load the rest."""
    good = tmp_path / "good.yaml"
    bad = tmp_path / "bad.yaml"
    _write_profile(good, "test/good")
    bad.write_text("not: valid: yaml: ::::", encoding="utf-8")

    import custom_components.media_room_manager.profiles.registry as reg_mod

    monkeypatch.setattr(reg_mod, "_BUNDLED_DIR", tmp_path)

    r = ProfileRegistry()
    r.load_bundled()
    # bad profile skipped, good profile loaded
    assert len(r) == 1
    assert r.get("test/good") is not None


# ---------------------------------------------------------------------------
# Profile data spot-checks
# ---------------------------------------------------------------------------


def test_apple_tv_has_dynamic_virtual_sources() -> None:
    """The Apple TV 4K profile should have dynamic_virtual_sources configured."""
    r = _make_registry_with_bundled()
    p = r.get("apple/apple-tv-4k")
    assert p is not None
    assert p.dynamic_virtual_sources is not None
    assert p.dynamic_virtual_sources.source == "source_list_minus_known"


def test_lumagen_has_exclusive_outputs() -> None:
    """The Lumagen Radiance Pro profile should have exclusive_outputs: true."""
    r = _make_registry_with_bundled()
    p = r.get("lumagen/radiance-pro")
    assert p is not None
    assert p.exclusive_outputs is True


def test_marantz_has_two_output_groups() -> None:
    """The Marantz SR8015 profile should have two output groups: main and zone_2."""
    r = _make_registry_with_bundled()
    p = r.get("marantz/sr8015")
    assert p is not None
    og_ids = {og.id for og in p.output_groups}
    assert og_ids == {"main", "zone_2"}


def test_monoprice_has_eight_output_groups() -> None:
    """The Monoprice Blackbird 8x8 profile should have 8 output groups."""
    r = _make_registry_with_bundled()
    p = r.get("monoprice/blackbird-8x8")
    assert p is not None
    assert len(p.output_groups) == 8


def test_generic_splitter_is_passive_with_no_mechanism() -> None:
    """The generic HDMI splitter should have no selection_mechanism on its output group."""
    r = _make_registry_with_bundled()
    p = r.get("generic/hdmi-splitter-1x4")
    assert p is not None
    assert len(p.output_groups) == 1
    assert p.output_groups[0].selection_mechanism is None


def test_generic_audio_extractor_has_four_outputs() -> None:
    """The generic HDMI audio extractor should have four output interfaces."""
    r = _make_registry_with_bundled()
    p = r.get("generic/hdmi-audio-extractor")
    assert p is not None
    from custom_components.media_room_manager.graph.model import InterfaceDirection

    outputs = [i for i in p.interfaces if i.direction == InterfaceDirection.OUTPUT]
    assert len(outputs) == 4
