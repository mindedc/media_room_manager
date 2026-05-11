"""Tests for SwitchComboAdapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, call

import pytest

from custom_components.media_room_manager.adapters.switch_combo import SwitchComboAdapter


def _make_hass() -> MagicMock:
    hass = MagicMock()
    hass.services.async_call = AsyncMock()
    return hass


ROW = [
    "switch.matrix_out1_in1",
    "switch.matrix_out1_in2",
    "switch.matrix_out1_in3",
]


@pytest.fixture()
def adapter() -> SwitchComboAdapter:
    return SwitchComboAdapter()


async def test_turns_on_target_and_off_others(adapter: SwitchComboAdapter) -> None:
    """Selecting in2 should turn off in1 and in3, then turn on in2."""
    hass = _make_hass()
    target = "switch.matrix_out1_in2"
    await adapter.async_select_input(hass, target, "Input 2", row_entity_ids=ROW)
    calls = hass.services.async_call.call_args_list
    assert len(calls) == 2
    # First call: turn off all others
    first = calls[0]
    assert first == call(
        "switch",
        "turn_off",
        {"entity_id": ["switch.matrix_out1_in1", "switch.matrix_out1_in3"]},
        blocking=True,
    )
    # Second call: turn on target
    second = calls[1]
    assert second == call("switch", "turn_on", {"entity_id": target}, blocking=True)


async def test_single_switch_row_no_turn_off(adapter: SwitchComboAdapter) -> None:
    """A row with only one switch skips the turn_off call."""
    hass = _make_hass()
    target = "switch.matrix_out1_in1"
    await adapter.async_select_input(hass, target, "Input 1", row_entity_ids=[target])
    calls = hass.services.async_call.call_args_list
    assert len(calls) == 1
    assert calls[0] == call("switch", "turn_on", {"entity_id": target}, blocking=True)


async def test_selecting_first_in_row(adapter: SwitchComboAdapter) -> None:
    """Selecting the first switch turns off the rest."""
    hass = _make_hass()
    target = ROW[0]
    await adapter.async_select_input(hass, target, "Input 1", row_entity_ids=ROW)
    calls = hass.services.async_call.call_args_list
    off_call = calls[0]
    assert sorted(off_call[0][2]["entity_id"]) == sorted(ROW[1:])


async def test_power_on_raises(adapter: SwitchComboAdapter) -> None:
    hass = _make_hass()
    with pytest.raises(NotImplementedError):
        await adapter.async_power_on(hass, ROW[0])
