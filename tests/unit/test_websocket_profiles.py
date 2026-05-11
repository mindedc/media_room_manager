"""Tests for the profile WebSocket commands."""

from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.media_room_manager.const import DOMAIN
from custom_components.media_room_manager.graph.system_config import SystemConfig
from custom_components.media_room_manager.profiles.registry import ProfileRegistry
from custom_components.media_room_manager.websocket.profiles import (
    ws_get_profile,
    ws_list_profiles,
)


def _make_hass(registry: ProfileRegistry | None = None) -> MagicMock:
    """Create a mock hass with the domain data and optional registry."""
    hass = MagicMock()
    if registry is not None:
        hass.data = {
            DOMAIN: {
                "entry_1": {
                    "store": MagicMock(),
                    "config": SystemConfig.empty(),
                    "registry": registry,
                }
            }
        }
    else:
        hass.data = {}
    return hass


def _make_connection() -> MagicMock:
    conn = MagicMock()
    conn.send_result = MagicMock()
    conn.send_error = MagicMock()
    return conn


def _loaded_registry() -> ProfileRegistry:
    """Return a registry with all bundled profiles loaded."""
    r = ProfileRegistry()
    r.load_bundled()
    return r


# ---------------------------------------------------------------------------
# list_profiles
# ---------------------------------------------------------------------------


def test_list_profiles_no_domain_data() -> None:
    """When the domain isn't set up, list_profiles returns an empty list."""
    hass = _make_hass(registry=None)
    connection = _make_connection()
    ws_list_profiles(hass, connection, {"id": 1})
    result = connection.send_result.call_args[0][1]
    assert result["profiles"] == []


def test_list_profiles_returns_all_bundled() -> None:
    """list_profiles should return a summary for every loaded profile."""
    registry = _loaded_registry()
    hass = _make_hass(registry=registry)
    connection = _make_connection()
    ws_list_profiles(hass, connection, {"id": 1})
    result = connection.send_result.call_args[0][1]
    assert len(result["profiles"]) == 10


def test_list_profiles_summary_fields() -> None:
    """Each profile summary should contain the expected metadata fields."""
    registry = _loaded_registry()
    hass = _make_hass(registry=registry)
    connection = _make_connection()
    ws_list_profiles(hass, connection, {"id": 1})
    summaries = connection.send_result.call_args[0][1]["profiles"]
    for summary in summaries:
        assert "profile_id" in summary
        assert "manufacturer" in summary
        assert "model" in summary
        assert "category" in summary
        assert "power_handling" in summary


def test_list_profiles_contains_expected_profile_id() -> None:
    """list_profiles result should include 'apple/apple-tv-4k'."""
    registry = _loaded_registry()
    hass = _make_hass(registry=registry)
    connection = _make_connection()
    ws_list_profiles(hass, connection, {"id": 1})
    ids = [s["profile_id"] for s in connection.send_result.call_args[0][1]["profiles"]]
    assert "apple/apple-tv-4k" in ids


# ---------------------------------------------------------------------------
# get_profile
# ---------------------------------------------------------------------------


def test_get_profile_no_domain_data() -> None:
    """When the domain isn't set up, get_profile returns not_found error."""
    hass = _make_hass(registry=None)
    connection = _make_connection()
    ws_get_profile(hass, connection, {"id": 1, "profile_id": "apple/apple-tv-4k"})
    connection.send_error.assert_called_once()
    error_code = connection.send_error.call_args[0][1]
    assert error_code == "not_found"


def test_get_profile_unknown_id_returns_error() -> None:
    """Requesting an unknown profile_id should send a not_found error."""
    registry = _loaded_registry()
    hass = _make_hass(registry=registry)
    connection = _make_connection()
    ws_get_profile(hass, connection, {"id": 1, "profile_id": "does/not/exist"})
    connection.send_error.assert_called_once()
    error_code = connection.send_error.call_args[0][1]
    assert error_code == "not_found"


def test_get_profile_returns_full_serialized_profile() -> None:
    """get_profile should return the full profile dict for a known profile_id."""
    registry = _loaded_registry()
    hass = _make_hass(registry=registry)
    connection = _make_connection()
    ws_get_profile(hass, connection, {"id": 1, "profile_id": "marantz/sr8015"})
    connection.send_result.assert_called_once()
    profile_dict = connection.send_result.call_args[0][1]["profile"]
    assert profile_dict["profile_id"] == "marantz/sr8015"
    assert profile_dict["manufacturer"] == "Marantz"
    assert profile_dict["model"] == "SR8015"
    assert len(profile_dict["output_groups"]) == 2


def test_get_profile_includes_discovery_block() -> None:
    """get_profile result should include the discovery block when present."""
    registry = _loaded_registry()
    hass = _make_hass(registry=registry)
    connection = _make_connection()
    ws_get_profile(hass, connection, {"id": 1, "profile_id": "denon/avr-x1700h"})
    profile_dict = connection.send_result.call_args[0][1]["profile"]
    assert profile_dict["discovery"] is not None
    assert len(profile_dict["discovery"]["output_groups"]) >= 1


def test_get_profile_lumagen_has_exclusive_outputs() -> None:
    """get_profile for Lumagen should report exclusive_outputs: true."""
    registry = _loaded_registry()
    hass = _make_hass(registry=registry)
    connection = _make_connection()
    ws_get_profile(hass, connection, {"id": 1, "profile_id": "lumagen/radiance-pro"})
    profile_dict = connection.send_result.call_args[0][1]["profile"]
    assert profile_dict["exclusive_outputs"] is True
