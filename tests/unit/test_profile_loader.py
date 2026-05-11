"""Tests for the profile YAML loader."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import voluptuous as vol
import yaml

from custom_components.media_room_manager.profiles.loader import load_profile_yaml
from custom_components.media_room_manager.profiles.types import ProfileCategory


def _write_yaml(tmp_path: Path, content: str) -> Path:
    """Write YAML content to a temp file and return the path."""
    p = tmp_path / "profile.yaml"
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


def test_load_minimal_valid_profile(tmp_path: Path) -> None:
    """A minimal valid profile YAML should load without errors."""
    path = _write_yaml(
        tmp_path,
        """
        profile_id: test/minimal
        schema_version: 1
        manufacturer: Test Co
        model: Model X
        category: source
        power_handling: discrete_capable
        """,
    )
    p = load_profile_yaml(path)
    assert p.profile_id == "test/minimal"
    assert p.category == ProfileCategory.SOURCE


def test_load_profile_with_output_groups_and_interfaces(tmp_path: Path) -> None:
    """A profile with output groups and interfaces should load and reflect structure."""
    path = _write_yaml(
        tmp_path,
        """
        profile_id: test/full
        schema_version: 1
        manufacturer: Test Co
        model: Full Model
        category: avr
        power_handling: discrete_capable
        power_on_delay: 5
        output_groups:
          - id: main
            selection_mechanism:
              kind: media_player_source
              expected_domain: media_player
              expected_features: [turn_on, select_source]
            provides_roles: [power, volume]
        interfaces:
          - id: hdmi_1
            direction: input
            type: hdmi
            label: "HDMI 1"
            routable_to_output_group: [main]
          - id: hdmi_out
            direction: output
            type: hdmi_audio_return
            label: "HDMI MAIN"
            output_group: main
        """,
    )
    p = load_profile_yaml(path)
    assert p.profile_id == "test/full"
    assert p.power_on_delay == 5
    assert len(p.output_groups) == 1
    assert len(p.interfaces) == 2


def test_load_nonexistent_file_raises(tmp_path: Path) -> None:
    """Loading a file that doesn't exist should raise FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load_profile_yaml(tmp_path / "ghost.yaml")


def test_load_invalid_yaml_raises(tmp_path: Path) -> None:
    """A file with malformed YAML should raise yaml.YAMLError."""
    path = tmp_path / "bad.yaml"
    path.write_text(": this: is: not: valid: yaml: ::::", encoding="utf-8")
    with pytest.raises(yaml.YAMLError):
        load_profile_yaml(path)


def test_load_yaml_wrong_type_raises(tmp_path: Path) -> None:
    """A YAML file whose root is a list (not a mapping) should raise vol.Invalid."""
    path = _write_yaml(tmp_path, "- one\n- two\n")
    with pytest.raises(vol.Invalid):
        load_profile_yaml(path)


def test_load_schema_violation_raises(tmp_path: Path) -> None:
    """A YAML file with a schema violation (bad category) should raise vol.Invalid."""
    path = _write_yaml(
        tmp_path,
        """
        profile_id: test/bad
        schema_version: 1
        manufacturer: Bad Corp
        model: Bad Model
        category: not_a_real_category
        """,
    )
    with pytest.raises(vol.Invalid):
        load_profile_yaml(path)


def test_load_profile_with_discovery_block(tmp_path: Path) -> None:
    """A profile with a discovery block should load and expose discovery data."""
    path = _write_yaml(
        tmp_path,
        """
        profile_id: test/discovered
        schema_version: 1
        manufacturer: Acme
        model: AMP-1
        category: avr
        output_groups:
          - id: main
            selection_mechanism:
              kind: media_player_source
              expected_domain: media_player
        discovery:
          output_groups:
            - output_group: main
              is_discovery_anchor: true
              match_threshold: 60
              signals:
                - kind: device_registry
                  manufacturer: Acme
                  model_patterns: ["AMP-1"]
                  weight: 100
        """,
    )
    p = load_profile_yaml(path)
    assert p.discovery is not None
    assert len(p.discovery.output_groups) == 1
    entry = p.discovery.output_groups[0]
    assert entry.is_discovery_anchor is True
    assert entry.signals[0].manufacturer == "Acme"
