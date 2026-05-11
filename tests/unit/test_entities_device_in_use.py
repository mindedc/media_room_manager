"""Tests for entities/device_in_use.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.media_room_manager.entities.device_in_use import (
    DeviceInUseBinarySensor,
    _get_devices_in_active_paths,
)
from custom_components.media_room_manager.graph.model import (
    Device,
    OutputGroup,
)
from custom_components.media_room_manager.graph.system_config import SystemConfig
from custom_components.media_room_manager.resolver.path import (
    ActivePathsRegistry,
    PathHop,
    ResolvedSinglePath,
    ZoneResolverResult,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_hass() -> MagicMock:
    return MagicMock()


def _simple_device(device_id: str, name: str) -> Device:
    og = OutputGroup(id="main")
    return Device(id=device_id, name=name, profile_id="test/p", output_groups=(og,))


def _simple_config(devices: list[Device] | None = None) -> SystemConfig:
    return SystemConfig(devices=devices or [])


def _resolved_result(
    zone_id: str,
    source_device_id: str,
    path_device_ids: list[str],
) -> ZoneResolverResult:
    """Build a minimal ZoneResolverResult with hops for the given devices."""
    hops = tuple(
        PathHop(
            device_id=did,
            entry_interface_id=None,
            exit_interface_id=None,
            output_group_id=None,
        )
        for did in path_device_ids
    )
    path = ResolvedSinglePath(
        carrier="video",
        source_device_id=source_device_id,
        sink_device_id=path_device_ids[-1] if path_device_ids else source_device_id,
        hops=hops,
    )
    return ZoneResolverResult(
        zone_id=zone_id,
        source_device_id=source_device_id,
        virtual_source_id=None,
        is_virtual_source=False,
        sink_device_ids=(path_device_ids[-1],) if path_device_ids else (source_device_id,),
        video_paths=(path,),
        audio_paths=(),
        contentions=(),
        exclusive_output_usage=(),
    )


# ---------------------------------------------------------------------------
# Tests: _get_devices_in_active_paths
# ---------------------------------------------------------------------------


class TestGetDevicesInActivePaths:
    """Tests for the internal helper that collects devices from active paths."""

    def test_empty_registry_returns_empty_set(self) -> None:
        """No active paths → empty set."""
        active = ActivePathsRegistry()
        assert _get_devices_in_active_paths(active) == set()

    def test_includes_source_device(self) -> None:
        """Source device is included even if it has no hops."""
        active = ActivePathsRegistry()
        result = ZoneResolverResult(
            zone_id="z1",
            source_device_id="src",
            virtual_source_id=None,
            is_virtual_source=False,
            sink_device_ids=("sink",),
            video_paths=(),
            audio_paths=(),
            contentions=(),
            exclusive_output_usage=(),
        )
        active.update(result)

        assert "src" in _get_devices_in_active_paths(active)

    def test_includes_hop_devices(self) -> None:
        """All hop devices are included in the returned set."""
        active = ActivePathsRegistry()
        result = _resolved_result("z1", "src", ["src", "avr", "tv"])
        active.update(result)

        devices = _get_devices_in_active_paths(active)
        assert "src" in devices
        assert "avr" in devices
        assert "tv" in devices

    def test_multiple_zones_combined(self) -> None:
        """Devices from multiple active zones are unioned."""
        active = ActivePathsRegistry()
        active.update(_resolved_result("z1", "src1", ["src1", "avr"]))
        active.update(_resolved_result("z2", "src2", ["src2", "tv"]))

        devices = _get_devices_in_active_paths(active)
        assert "src1" in devices
        assert "avr" in devices
        assert "src2" in devices
        assert "tv" in devices

    def test_not_in_active_paths(self) -> None:
        """Device not in any active path is not in the returned set."""
        active = ActivePathsRegistry()
        active.update(_resolved_result("z1", "src", ["src", "tv"]))

        devices = _get_devices_in_active_paths(active)
        assert "avr_not_in_path" not in devices


# ---------------------------------------------------------------------------
# Tests: DeviceInUseBinarySensor
# ---------------------------------------------------------------------------


class TestDeviceInUseBinarySensor:
    """Tests for the binary sensor entity."""

    def test_unique_id(self) -> None:
        """unique_id follows mrm_device_<id>_in_use pattern."""
        hass = _make_hass()
        device = _simple_device("avr", "Marantz AVR")
        config = _simple_config([device])
        active = ActivePathsRegistry()

        sensor = DeviceInUseBinarySensor(hass, device, config, active)

        assert sensor.unique_id == "mrm_device_avr_in_use"

    def test_name(self) -> None:
        """name includes device name and 'In Use'."""
        hass = _make_hass()
        device = _simple_device("avr", "Marantz AVR")
        config = _simple_config([device])
        active = ActivePathsRegistry()

        sensor = DeviceInUseBinarySensor(hass, device, config, active)

        assert sensor.name == "Marantz AVR In Use"

    def test_is_on_false_when_no_active_paths(self) -> None:
        """is_on is False when no zones are active."""
        hass = _make_hass()
        device = _simple_device("avr", "AVR")
        config = _simple_config([device])
        active = ActivePathsRegistry()

        sensor = DeviceInUseBinarySensor(hass, device, config, active)

        assert sensor.is_on is False

    def test_is_on_true_when_device_in_active_path(self) -> None:
        """is_on is True when the device is in an active path."""
        hass = _make_hass()
        device = _simple_device("avr", "AVR")
        config = _simple_config([device])
        active = ActivePathsRegistry()
        active.update(_resolved_result("z1", "src", ["src", "avr", "tv"]))

        sensor = DeviceInUseBinarySensor(hass, device, config, active)

        assert sensor.is_on is True

    def test_is_on_false_when_device_not_in_active_path(self) -> None:
        """is_on is False when the device is not in any active path."""
        hass = _make_hass()
        device = _simple_device("avr", "AVR")
        config = _simple_config([device])
        active = ActivePathsRegistry()
        # Active path uses different devices.
        active.update(_resolved_result("z1", "src", ["src", "tv"]))

        sensor = DeviceInUseBinarySensor(hass, device, config, active)

        assert sensor.is_on is False

    def test_is_on_updates_dynamically(self) -> None:
        """is_on reflects the current state of active_paths (live registry)."""
        hass = _make_hass()
        device = _simple_device("avr", "AVR")
        config = _simple_config([device])
        active = ActivePathsRegistry()

        sensor = DeviceInUseBinarySensor(hass, device, config, active)
        assert sensor.is_on is False

        # Add a path that uses the device.
        active.update(_resolved_result("z1", "src", ["src", "avr", "tv"]))
        assert sensor.is_on is True

        # Remove the active path.
        active.remove("z1")
        assert sensor.is_on is False

    def test_device_info_uses_device_identifiers(self) -> None:
        """device_info links to the physical device registry entry."""
        from custom_components.media_room_manager.const import DOMAIN

        hass = _make_hass()
        device = _simple_device("avr", "AVR")
        config = _simple_config([device])
        active = ActivePathsRegistry()

        sensor = DeviceInUseBinarySensor(hass, device, config, active)

        assert (DOMAIN, "device_avr") in sensor.device_info["identifiers"]
