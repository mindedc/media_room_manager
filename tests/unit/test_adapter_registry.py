"""Tests for AdapterRegistry."""

from __future__ import annotations

import pytest

from custom_components.media_room_manager.adapters.media_player_source import (
    MediaPlayerSourceAdapter,
)
from custom_components.media_room_manager.adapters.registry import AdapterRegistry
from custom_components.media_room_manager.adapters.remote_command import (
    RemoteCommandAdapter,
)
from custom_components.media_room_manager.adapters.select_entity import SelectEntityAdapter
from custom_components.media_room_manager.adapters.service_call import ServiceCallAdapter
from custom_components.media_room_manager.adapters.switch_combo import SwitchComboAdapter


@pytest.fixture()
def registry() -> AdapterRegistry:
    return AdapterRegistry()


def test_all_five_kinds_registered(registry: AdapterRegistry) -> None:
    expected = {
        "media_player_source",
        "select_entity",
        "switch_combo",
        "remote_command",
        "service_call",
    }
    assert set(registry.kinds()) == expected


def test_get_media_player_source(registry: AdapterRegistry) -> None:
    assert isinstance(registry.get("media_player_source"), MediaPlayerSourceAdapter)


def test_get_select_entity(registry: AdapterRegistry) -> None:
    assert isinstance(registry.get("select_entity"), SelectEntityAdapter)


def test_get_switch_combo(registry: AdapterRegistry) -> None:
    assert isinstance(registry.get("switch_combo"), SwitchComboAdapter)


def test_get_remote_command(registry: AdapterRegistry) -> None:
    assert isinstance(registry.get("remote_command"), RemoteCommandAdapter)


def test_get_service_call(registry: AdapterRegistry) -> None:
    assert isinstance(registry.get("service_call"), ServiceCallAdapter)


def test_get_unknown_kind_returns_none(registry: AdapterRegistry) -> None:
    assert registry.get("telepathy") is None


def test_get_required_raises_for_unknown_kind(registry: AdapterRegistry) -> None:
    with pytest.raises(ValueError, match="telepathy"):
        registry.get_required("telepathy")


def test_get_required_returns_adapter(registry: AdapterRegistry) -> None:
    adapter = registry.get_required("media_player_source")
    assert isinstance(adapter, MediaPlayerSourceAdapter)


def test_kinds_are_sorted(registry: AdapterRegistry) -> None:
    kinds = registry.kinds()
    assert kinds == sorted(kinds)
