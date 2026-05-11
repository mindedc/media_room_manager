"""Entities package for Media Room Manager.

Registers all entity platforms for the integration. Entity types:
- zone_media_player: per-zone MediaPlayerEntity
- selectable_exclusive: select + switch entities for selectable_exclusive zones
- device_in_use: binary_sensor for shared physical devices
- registry_setup: device registry helpers
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from ..adapters.registry import AdapterRegistry
from ..graph.model import SinkMode
from ..graph.system_config import SystemConfig
from ..orchestrator.orchestrator import Orchestrator
from ..resolver.path import ActivePathsRegistry
from .device_in_use import DeviceInUseBinarySensor
from .selectable_exclusive import SelectableExclusiveSelect, SelectableExclusiveSwitch
from .zone_media_player import ZoneMediaPlayer

_LOGGER = logging.getLogger(__name__)

# Type alias to keep line length reasonable.
_AnyEntity = (
    ZoneMediaPlayer
    | SelectableExclusiveSelect
    | SelectableExclusiveSwitch
    | DeviceInUseBinarySensor
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up all Media Room Manager entities for a config entry.

    Creates ZoneMediaPlayer entities for every zone, plus helper entities for
    selectable_exclusive zones and binary_sensor entities for shared devices.
    In the current phase tests instantiate entities directly; this function
    exists to satisfy the correct HA platform signature.
    """
    from ..const import DOMAIN

    data = hass.data[DOMAIN][entry.entry_id]
    config: SystemConfig = data["config"]
    orchestrator: Orchestrator = data.get(
        "orchestrator",
        Orchestrator(hass, config, AdapterRegistry(), ActivePathsRegistry()),
    )
    active_paths: ActivePathsRegistry = data.get("active_paths", ActivePathsRegistry())
    adapter_registry: AdapterRegistry = data.get("adapter_registry", AdapterRegistry())

    entities: list[_AnyEntity] = []

    for zone in config.zones:
        player = ZoneMediaPlayer(hass, zone, config, orchestrator, active_paths, adapter_registry)
        entities.append(player)

        if zone.sink_mode == SinkMode.SELECTABLE_EXCLUSIVE and len(zone.sink_device_ids) > 1:
            sel = SelectableExclusiveSelect(hass, zone, config, orchestrator)
            entities.append(sel)
            for sink_device_id in zone.sink_device_ids:
                sw = SelectableExclusiveSwitch(hass, zone, config, orchestrator, sink_device_id)
                entities.append(sw)

    # Determine which devices are reachable from more than one zone.
    # Count zone reachability per device (device in sink_device_ids).
    device_zone_count: dict[str, int] = {}
    for zone in config.zones:
        for dev_id in zone.sink_device_ids:
            device_zone_count[dev_id] = device_zone_count.get(dev_id, 0) + 1

    for device in config.devices:
        if device_zone_count.get(device.id, 0) > 1:
            sensor = DeviceInUseBinarySensor(hass, device, config, active_paths)
            entities.append(sensor)

    if entities:
        async_add_entities(entities)

    _LOGGER.debug(
        "Media Room Manager: registered %d entities for entry %s",
        len(entities),
        entry.entry_id,
    )
