"""Tests for entities/registry_setup.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from custom_components.media_room_manager.const import DOMAIN
from custom_components.media_room_manager.entities.registry_setup import (
    _physical_device_info,
    _zone_device_info,
    async_register_devices,
)
from custom_components.media_room_manager.graph.model import (
    Device,
    Zone,
)
from custom_components.media_room_manager.graph.system_config import SystemConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _simple_device(device_id: str, name: str) -> Device:
    return Device(id=device_id, name=name, profile_id="test/p")


def _simple_zone(zone_id: str, name: str) -> Zone:
    return Zone(id=zone_id, name=name)


def _simple_config(
    zones: list[Zone] | None = None,
    devices: list[Device] | None = None,
) -> SystemConfig:
    return SystemConfig(zones=zones or [], devices=devices or [])


# ---------------------------------------------------------------------------
# Tests: DeviceInfo builders
# ---------------------------------------------------------------------------


class TestDeviceInfoBuilders:
    """Tests for the DeviceInfo constructor helpers."""

    def test_zone_device_info_identifiers(self) -> None:
        """Zone DeviceInfo has correct identifiers and manufacturer."""
        info = _zone_device_info("living_room", "Living Room")

        assert (DOMAIN, "zone_living_room") in info["identifiers"]
        assert info["name"] == "Living Room"
        assert info["manufacturer"] == "Media Room Manager"

    def test_physical_device_info_identifiers(self) -> None:
        """Physical device DeviceInfo has correct identifiers and manufacturer."""
        info = _physical_device_info("avr_001", "Marantz AVR")

        assert (DOMAIN, "device_avr_001") in info["identifiers"]
        assert info["name"] == "Marantz AVR"
        assert info["manufacturer"] == "Media Room Manager"


# ---------------------------------------------------------------------------
# Tests: async_register_devices
# ---------------------------------------------------------------------------


class TestAsyncRegisterDevices:
    """Tests for the device registry registration function."""

    @pytest.mark.asyncio
    async def test_registers_zone_entries(self) -> None:
        """Creates device registry entries for each zone."""
        hass = MagicMock()
        entry = MagicMock()
        entry.entry_id = "test_entry"

        zone1 = _simple_zone("z1", "Living Room")
        zone2 = _simple_zone("z2", "Theater")
        config = _simple_config(zones=[zone1, zone2])

        mock_dev_reg = MagicMock()
        mock_dev_reg.async_get_or_create = MagicMock()

        with patch(
            "custom_components.media_room_manager.entities.registry_setup.dr.async_get",
            return_value=mock_dev_reg,
        ):
            await async_register_devices(hass, entry, config)

        calls = mock_dev_reg.async_get_or_create.call_args_list
        identifiers_used = [call.kwargs.get("identifiers") for call in calls]

        assert {(DOMAIN, "zone_z1")} in identifiers_used
        assert {(DOMAIN, "zone_z2")} in identifiers_used

    @pytest.mark.asyncio
    async def test_registers_device_entries(self) -> None:
        """Creates device registry entries for each physical device."""
        hass = MagicMock()
        entry = MagicMock()
        entry.entry_id = "test_entry"

        device1 = _simple_device("avr", "Marantz AVR")
        device2 = _simple_device("tv", "Sony TV")
        config = _simple_config(devices=[device1, device2])

        mock_dev_reg = MagicMock()
        mock_dev_reg.async_get_or_create = MagicMock()

        with patch(
            "custom_components.media_room_manager.entities.registry_setup.dr.async_get",
            return_value=mock_dev_reg,
        ):
            await async_register_devices(hass, entry, config)

        calls = mock_dev_reg.async_get_or_create.call_args_list
        identifiers_used = [call.kwargs.get("identifiers") for call in calls]

        assert {(DOMAIN, "device_avr")} in identifiers_used
        assert {(DOMAIN, "device_tv")} in identifiers_used

    @pytest.mark.asyncio
    async def test_registers_both_zones_and_devices(self) -> None:
        """Registers both zone and device entries in the same call."""
        hass = MagicMock()
        entry = MagicMock()
        entry.entry_id = "test_entry"

        zone = _simple_zone("z1", "Room")
        device = _simple_device("avr", "AVR")
        config = _simple_config(zones=[zone], devices=[device])

        mock_dev_reg = MagicMock()
        mock_dev_reg.async_get_or_create = MagicMock()

        with patch(
            "custom_components.media_room_manager.entities.registry_setup.dr.async_get",
            return_value=mock_dev_reg,
        ):
            await async_register_devices(hass, entry, config)

        assert mock_dev_reg.async_get_or_create.call_count == 2

    @pytest.mark.asyncio
    async def test_empty_config_no_registrations(self) -> None:
        """Empty config results in zero device registry calls."""
        hass = MagicMock()
        entry = MagicMock()
        entry.entry_id = "test_entry"

        config = _simple_config()

        mock_dev_reg = MagicMock()
        mock_dev_reg.async_get_or_create = MagicMock()

        with patch(
            "custom_components.media_room_manager.entities.registry_setup.dr.async_get",
            return_value=mock_dev_reg,
        ):
            await async_register_devices(hass, entry, config)

        mock_dev_reg.async_get_or_create.assert_not_called()

    @pytest.mark.asyncio
    async def test_zone_entry_has_correct_name(self) -> None:
        """Zone device registry entry has the correct name."""
        hass = MagicMock()
        entry = MagicMock()
        entry.entry_id = "test_entry"

        zone = _simple_zone("z1", "My Theater")
        config = _simple_config(zones=[zone])

        captured_calls: list[dict] = []

        def _capture(**kwargs: object) -> None:
            captured_calls.append(kwargs)

        mock_dev_reg = MagicMock()
        mock_dev_reg.async_get_or_create = MagicMock(side_effect=_capture)

        with patch(
            "custom_components.media_room_manager.entities.registry_setup.dr.async_get",
            return_value=mock_dev_reg,
        ):
            await async_register_devices(hass, entry, config)

        assert len(captured_calls) == 1
        assert captured_calls[0]["name"] == "My Theater"
        assert captured_calls[0]["manufacturer"] == "Media Room Manager"
