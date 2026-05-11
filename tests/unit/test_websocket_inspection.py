"""Tests for the read-only WebSocket inspection commands."""

from unittest.mock import MagicMock

from custom_components.media_room_manager.const import DOMAIN
from custom_components.media_room_manager.graph.model import (
    Connection,
    Device,
    PowerHandling,
    Zone,
)
from custom_components.media_room_manager.graph.system_config import SystemConfig
from custom_components.media_room_manager.websocket.inspection import (
    ws_list_connections,
    ws_list_devices,
    ws_list_zones,
)


def _make_hass(config: SystemConfig | None = None) -> MagicMock:
    hass = MagicMock()
    if config is not None:
        hass.data = {DOMAIN: {"entry_1": {"store": MagicMock(), "config": config}}}
    else:
        hass.data = {}
    return hass


def _make_connection() -> MagicMock:
    conn = MagicMock()
    conn.send_result = MagicMock()
    return conn


def test_list_devices_empty() -> None:
    hass = _make_hass(SystemConfig.empty())
    connection = _make_connection()
    ws_list_devices(hass, connection, {"id": 1})
    connection.send_result.assert_called_once()
    result = connection.send_result.call_args[0][1]
    assert result["devices"] == []


def test_list_devices_with_data() -> None:
    cfg = SystemConfig(
        devices=[
            Device(
                id="atv",
                name="Apple TV",
                profile_id="apple/apple-tv-4k",
                power_handling=PowerHandling.DISCRETE_CAPABLE,
            )
        ]
    )
    hass = _make_hass(cfg)
    connection = _make_connection()
    ws_list_devices(hass, connection, {"id": 1})
    result = connection.send_result.call_args[0][1]
    assert len(result["devices"]) == 1
    assert result["devices"][0]["id"] == "atv"


def test_list_zones_empty() -> None:
    hass = _make_hass(SystemConfig.empty())
    connection = _make_connection()
    ws_list_zones(hass, connection, {"id": 2})
    result = connection.send_result.call_args[0][1]
    assert result["zones"] == []


def test_list_zones_with_data() -> None:
    cfg = SystemConfig(zones=[Zone(id="living_room", name="Living Room")])
    hass = _make_hass(cfg)
    connection = _make_connection()
    ws_list_zones(hass, connection, {"id": 2})
    result = connection.send_result.call_args[0][1]
    assert len(result["zones"]) == 1
    assert result["zones"][0]["id"] == "living_room"


def test_list_connections_empty() -> None:
    hass = _make_hass(SystemConfig.empty())
    connection = _make_connection()
    ws_list_connections(hass, connection, {"id": 3})
    result = connection.send_result.call_args[0][1]
    assert result["connections"] == []


def test_list_connections_with_data() -> None:
    cfg = SystemConfig(
        connections=[
            Connection(
                id="c1",
                from_device_id="atv",
                from_interface_id="hdmi_out",
                to_device_id="avr",
                to_interface_id="hdmi_in_1",
            )
        ]
    )
    hass = _make_hass(cfg)
    connection = _make_connection()
    ws_list_connections(hass, connection, {"id": 3})
    result = connection.send_result.call_args[0][1]
    assert len(result["connections"]) == 1
    assert result["connections"][0]["id"] == "c1"


def test_list_devices_no_domain_data() -> None:
    """When the domain isn't set up yet, returns empty list."""
    hass = _make_hass(config=None)
    connection = _make_connection()
    ws_list_devices(hass, connection, {"id": 1})
    result = connection.send_result.call_args[0][1]
    assert result["devices"] == []
