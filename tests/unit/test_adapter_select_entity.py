"""Tests for SelectEntityAdapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.media_room_manager.adapters.select_entity import SelectEntityAdapter


def _make_hass() -> MagicMock:
    hass = MagicMock()
    hass.services.async_call = AsyncMock()
    return hass


ENTITY_ID = "select.matrix_out_1"


@pytest.fixture()
def adapter() -> SelectEntityAdapter:
    return SelectEntityAdapter()


async def test_select_input_calls_select_option(adapter: SelectEntityAdapter) -> None:
    hass = _make_hass()
    await adapter.async_select_input(hass, ENTITY_ID, "Input 3")
    hass.services.async_call.assert_called_once_with(
        "select",
        "select_option",
        {"entity_id": ENTITY_ID, "option": "Input 3"},
        blocking=True,
    )


async def test_power_on_raises(adapter: SelectEntityAdapter) -> None:
    hass = _make_hass()
    with pytest.raises(NotImplementedError):
        await adapter.async_power_on(hass, ENTITY_ID)


async def test_volume_raises(adapter: SelectEntityAdapter) -> None:
    hass = _make_hass()
    with pytest.raises(NotImplementedError):
        await adapter.async_set_volume(hass, ENTITY_ID, 0.5)


async def test_transport_raises(adapter: SelectEntityAdapter) -> None:
    hass = _make_hass()
    with pytest.raises(NotImplementedError):
        await adapter.async_send_transport(hass, ENTITY_ID, "play")
