"""Tests for MRMStore and SystemConfig round-trip persistence."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.media_room_manager.graph.model import (
    Connection,
    Device,
    Interface,
    InterfaceDirection,
    InterfaceType,
    OutputGroup,
    PowerHandling,
    Zone,
)
from custom_components.media_room_manager.graph.system_config import SystemConfig
from custom_components.media_room_manager.store import MRMStore

# ---------------------------------------------------------------------------
# SystemConfig unit tests
# ---------------------------------------------------------------------------


def test_system_config_empty() -> None:
    cfg = SystemConfig.empty()
    assert cfg.schema_version == 1
    assert cfg.devices == []
    assert cfg.zones == []
    assert cfg.connections == []


def test_system_config_roundtrip_empty() -> None:
    cfg = SystemConfig.empty()
    d = cfg.to_dict()
    cfg2 = SystemConfig.from_dict(d)
    assert cfg2.schema_version == cfg.schema_version
    assert cfg2.devices == []
    assert cfg2.zones == []


def test_system_config_roundtrip_with_data() -> None:
    device = Device(
        id="atv",
        name="Apple TV",
        profile_id="apple/apple-tv-4k",
        power_handling=PowerHandling.DISCRETE_CAPABLE,
        output_groups=(OutputGroup(id="main"),),
        interfaces=(
            Interface(
                id="hdmi_out",
                direction=InterfaceDirection.OUTPUT,
                type=InterfaceType.HDMI,
                label="HDMI OUT",
                output_group="main",
            ),
        ),
    )
    zone = Zone(
        id="living_room",
        name="Living Room",
        sink_device_ids=("tv",),
        volume_authority_device_id="avr",
    )
    connection = Connection(
        id="atv_to_avr",
        from_device_id="atv",
        from_interface_id="hdmi_out",
        to_device_id="avr",
        to_interface_id="hdmi_in_1",
    )

    cfg = SystemConfig(devices=[device], zones=[zone], connections=[connection])
    d = cfg.to_dict()
    cfg2 = SystemConfig.from_dict(d)

    assert len(cfg2.devices) == 1
    assert cfg2.devices[0] == device
    assert len(cfg2.zones) == 1
    assert cfg2.zones[0] == zone
    assert len(cfg2.connections) == 1
    assert cfg2.connections[0] == connection


def test_system_config_from_dict_missing_version_rejected() -> None:
    import voluptuous as vol

    with pytest.raises(vol.Invalid):
        SystemConfig.from_dict({"devices": []})


# ---------------------------------------------------------------------------
# MRMStore tests (mocked HA Store)
# ---------------------------------------------------------------------------


def _make_store(raw_data: dict | None = None) -> MRMStore:
    """Return an MRMStore with its internal HA Store fully mocked."""
    hass = MagicMock()
    store = MRMStore(hass)
    store._store = MagicMock()
    store._store.async_load = AsyncMock(return_value=raw_data)
    store._store.async_save = AsyncMock()
    return store


@pytest.mark.asyncio
async def test_store_load_no_existing_data() -> None:
    store = _make_store(raw_data=None)
    cfg = await store.async_load()
    assert cfg.devices == []
    assert cfg.zones == []
    assert store.config is cfg


@pytest.mark.asyncio
async def test_store_load_existing_data() -> None:
    existing = SystemConfig(
        devices=[Device(id="atv", name="Apple TV", profile_id="apple/apple-tv-4k")],
        zones=[Zone(id="lr", name="Living Room")],
    )
    store = _make_store(raw_data=existing.to_dict())
    cfg = await store.async_load()
    assert len(cfg.devices) == 1
    assert cfg.devices[0].id == "atv"
    assert len(cfg.zones) == 1


@pytest.mark.asyncio
async def test_store_save_and_reload() -> None:
    store = _make_store(raw_data=None)
    cfg = SystemConfig(
        devices=[Device(id="avr", name="Marantz", profile_id="marantz/sr8015")],
        zones=[Zone(id="theater", name="Theater")],
    )
    await store.async_save(cfg)
    store._store.async_save.assert_called_once()
    saved_dict = store._store.async_save.call_args[0][0]
    assert saved_dict["devices"][0]["id"] == "avr"


@pytest.mark.asyncio
async def test_store_load_corrupt_data_returns_empty() -> None:
    store = _make_store(raw_data={"not_valid": True})
    cfg = await store.async_load()
    assert cfg.devices == []


@pytest.mark.asyncio
async def test_store_config_none_before_load() -> None:
    store = _make_store()
    assert store.config is None
