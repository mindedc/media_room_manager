"""Tests for MediaPlayerSourceAdapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.media_room_manager.adapters.media_player_source import (
    MediaPlayerSourceAdapter,
)


def _make_hass() -> MagicMock:
    hass = MagicMock()
    hass.services.async_call = AsyncMock()
    return hass


ENTITY_ID = "media_player.avr_main"


@pytest.fixture()
def adapter() -> MediaPlayerSourceAdapter:
    return MediaPlayerSourceAdapter()


# ---------------------------------------------------------------------------
# select_input
# ---------------------------------------------------------------------------


async def test_select_input_calls_select_source(adapter: MediaPlayerSourceAdapter) -> None:
    hass = _make_hass()
    await adapter.async_select_input(hass, ENTITY_ID, "HDMI 1")
    hass.services.async_call.assert_called_once_with(
        "media_player",
        "select_source",
        {"entity_id": ENTITY_ID, "source": "HDMI 1"},
        blocking=True,
    )


# ---------------------------------------------------------------------------
# power
# ---------------------------------------------------------------------------


async def test_power_on_calls_turn_on(adapter: MediaPlayerSourceAdapter) -> None:
    hass = _make_hass()
    await adapter.async_power_on(hass, ENTITY_ID)
    hass.services.async_call.assert_called_once_with(
        "media_player", "turn_on", {"entity_id": ENTITY_ID}, blocking=True
    )


async def test_power_off_calls_turn_off(adapter: MediaPlayerSourceAdapter) -> None:
    hass = _make_hass()
    await adapter.async_power_off(hass, ENTITY_ID)
    hass.services.async_call.assert_called_once_with(
        "media_player", "turn_off", {"entity_id": ENTITY_ID}, blocking=True
    )


# ---------------------------------------------------------------------------
# volume
# ---------------------------------------------------------------------------


async def test_set_volume(adapter: MediaPlayerSourceAdapter) -> None:
    hass = _make_hass()
    await adapter.async_set_volume(hass, ENTITY_ID, 0.5)
    hass.services.async_call.assert_called_once_with(
        "media_player",
        "volume_set",
        {"entity_id": ENTITY_ID, "volume_level": 0.5},
        blocking=True,
    )


async def test_volume_up(adapter: MediaPlayerSourceAdapter) -> None:
    hass = _make_hass()
    await adapter.async_volume_up(hass, ENTITY_ID)
    hass.services.async_call.assert_called_once_with(
        "media_player", "volume_up", {"entity_id": ENTITY_ID}, blocking=True
    )


async def test_volume_down(adapter: MediaPlayerSourceAdapter) -> None:
    hass = _make_hass()
    await adapter.async_volume_down(hass, ENTITY_ID)
    hass.services.async_call.assert_called_once_with(
        "media_player", "volume_down", {"entity_id": ENTITY_ID}, blocking=True
    )


async def test_mute_true(adapter: MediaPlayerSourceAdapter) -> None:
    hass = _make_hass()
    await adapter.async_mute(hass, ENTITY_ID, True)
    hass.services.async_call.assert_called_once_with(
        "media_player",
        "volume_mute",
        {"entity_id": ENTITY_ID, "is_volume_muted": True},
        blocking=True,
    )


async def test_mute_false(adapter: MediaPlayerSourceAdapter) -> None:
    hass = _make_hass()
    await adapter.async_mute(hass, ENTITY_ID, False)
    hass.services.async_call.assert_called_once_with(
        "media_player",
        "volume_mute",
        {"entity_id": ENTITY_ID, "is_volume_muted": False},
        blocking=True,
    )


# ---------------------------------------------------------------------------
# transport
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("verb", "service"),
    [
        ("play", "media_play"),
        ("pause", "media_pause"),
        ("stop", "media_stop"),
        ("next_track", "media_next_track"),
        ("previous_track", "media_previous_track"),
    ],
)
async def test_transport_verbs(adapter: MediaPlayerSourceAdapter, verb: str, service: str) -> None:
    hass = _make_hass()
    await adapter.async_send_transport(hass, ENTITY_ID, verb)
    hass.services.async_call.assert_called_once_with(
        "media_player", service, {"entity_id": ENTITY_ID}, blocking=True
    )


async def test_seek_with_position(adapter: MediaPlayerSourceAdapter) -> None:
    hass = _make_hass()
    await adapter.async_send_transport(hass, ENTITY_ID, "seek", position=42.5)
    hass.services.async_call.assert_called_once_with(
        "media_player",
        "media_seek",
        {"entity_id": ENTITY_ID, "seek_position": 42.5},
        blocking=True,
    )


async def test_seek_without_position_does_not_call(
    adapter: MediaPlayerSourceAdapter,
) -> None:
    hass = _make_hass()
    await adapter.async_send_transport(hass, ENTITY_ID, "seek")
    hass.services.async_call.assert_not_called()


async def test_unknown_transport_command_does_not_call(
    adapter: MediaPlayerSourceAdapter,
) -> None:
    hass = _make_hass()
    await adapter.async_send_transport(hass, ENTITY_ID, "eject_disc")
    hass.services.async_call.assert_not_called()
