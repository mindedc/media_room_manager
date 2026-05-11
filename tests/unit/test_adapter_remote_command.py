"""Tests for RemoteCommandAdapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.media_room_manager.adapters.remote_command import (
    RemoteCommandAdapter,
)


def _make_hass() -> MagicMock:
    hass = MagicMock()
    hass.services.async_call = AsyncMock()
    return hass


ENTITY_ID = "remote.ir_blaster"


@pytest.fixture()
def adapter() -> RemoteCommandAdapter:
    return RemoteCommandAdapter()


async def test_select_input_sends_command(adapter: RemoteCommandAdapter) -> None:
    hass = _make_hass()
    await adapter.async_select_input(hass, ENTITY_ID, "HDMI 1", command="KEY_HDMI1")
    hass.services.async_call.assert_called_once_with(
        "remote",
        "send_command",
        {"entity_id": ENTITY_ID, "command": "KEY_HDMI1"},
        blocking=True,
    )


async def test_power_on_sends_command(adapter: RemoteCommandAdapter) -> None:
    hass = _make_hass()
    await adapter.async_power_on(hass, ENTITY_ID, command="KEY_POWER_ON")
    hass.services.async_call.assert_called_once_with(
        "remote",
        "send_command",
        {"entity_id": ENTITY_ID, "command": "KEY_POWER_ON"},
        blocking=True,
    )


async def test_power_off_sends_command(adapter: RemoteCommandAdapter) -> None:
    hass = _make_hass()
    await adapter.async_power_off(hass, ENTITY_ID, command="KEY_POWER_OFF")
    hass.services.async_call.assert_called_once_with(
        "remote",
        "send_command",
        {"entity_id": ENTITY_ID, "command": "KEY_POWER_OFF"},
        blocking=True,
    )


async def test_transport_with_command_map(adapter: RemoteCommandAdapter) -> None:
    hass = _make_hass()
    cmap = {"play": "KEY_PLAY", "pause": "KEY_PAUSE"}
    await adapter.async_send_transport(hass, ENTITY_ID, "play", command_map=cmap)
    hass.services.async_call.assert_called_once_with(
        "remote",
        "send_command",
        {"entity_id": ENTITY_ID, "command": "KEY_PLAY"},
        blocking=True,
    )


async def test_transport_verb_sent_as_is_when_no_map(adapter: RemoteCommandAdapter) -> None:
    """Without command_map, the transport verb is sent directly as the command."""
    hass = _make_hass()
    await adapter.async_send_transport(hass, ENTITY_ID, "stop")
    hass.services.async_call.assert_called_once_with(
        "remote",
        "send_command",
        {"entity_id": ENTITY_ID, "command": "stop"},
        blocking=True,
    )


async def test_transport_unmapped_verb_falls_back_to_verb(
    adapter: RemoteCommandAdapter,
) -> None:
    hass = _make_hass()
    cmap = {"play": "KEY_PLAY"}
    await adapter.async_send_transport(hass, ENTITY_ID, "pause", command_map=cmap)
    hass.services.async_call.assert_called_once_with(
        "remote",
        "send_command",
        {"entity_id": ENTITY_ID, "command": "pause"},
        blocking=True,
    )


async def test_volume_raises(adapter: RemoteCommandAdapter) -> None:
    hass = _make_hass()
    with pytest.raises(NotImplementedError):
        await adapter.async_set_volume(hass, ENTITY_ID, 0.5)
