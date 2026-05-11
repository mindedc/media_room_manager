"""Tests for async_setup_entry and async_unload_entry using HA mock environment."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.media_room_manager import async_setup_entry, async_unload_entry
from custom_components.media_room_manager.const import DOMAIN
from custom_components.media_room_manager.graph.system_config import SystemConfig


def _make_hass() -> MagicMock:
    hass = MagicMock()
    hass.data = {}
    return hass


def _make_entry(entry_id: str = "test_entry") -> MagicMock:
    entry = MagicMock()
    entry.entry_id = entry_id
    return entry


@pytest.mark.asyncio
async def test_setup_entry_loads_store() -> None:
    hass = _make_hass()
    entry = _make_entry()

    empty_config = SystemConfig.empty()

    with patch("custom_components.media_room_manager.MRMStore") as MockStore:
        mock_store = MagicMock()
        mock_store.async_load = AsyncMock(return_value=empty_config)
        MockStore.return_value = mock_store

        result = await async_setup_entry(hass, entry)

    assert result is True
    assert DOMAIN in hass.data
    assert "store" in hass.data[DOMAIN][entry.entry_id]
    assert "config" in hass.data[DOMAIN][entry.entry_id]


@pytest.mark.asyncio
async def test_setup_entry_stores_config() -> None:
    hass = _make_hass()
    entry = _make_entry()

    empty_config = SystemConfig.empty()

    with patch("custom_components.media_room_manager.MRMStore") as MockStore:
        mock_store = MagicMock()
        mock_store.async_load = AsyncMock(return_value=empty_config)
        MockStore.return_value = mock_store

        await async_setup_entry(hass, entry)

    stored = hass.data[DOMAIN][entry.entry_id]
    assert stored["config"] is empty_config


@pytest.mark.asyncio
async def test_unload_entry_cleans_up() -> None:
    hass = _make_hass()
    entry = _make_entry()

    hass.data[DOMAIN] = {entry.entry_id: {"store": MagicMock(), "config": MagicMock()}}

    result = await async_unload_entry(hass, entry)

    assert result is True
    assert entry.entry_id not in hass.data[DOMAIN]


@pytest.mark.asyncio
async def test_setup_entry_multiple_entries() -> None:
    """Multiple entries don't clobber each other's data."""
    hass = _make_hass()
    entry_a = _make_entry("entry_a")
    entry_b = _make_entry("entry_b")

    with patch("custom_components.media_room_manager.MRMStore") as MockStore:
        mock_store = MagicMock()
        mock_store.async_load = AsyncMock(return_value=SystemConfig.empty())
        MockStore.return_value = mock_store

        await async_setup_entry(hass, entry_a)
        await async_setup_entry(hass, entry_b)

    assert "entry_a" in hass.data[DOMAIN]
    assert "entry_b" in hass.data[DOMAIN]
