"""Device Registry setup for Media Room Manager.

Registers HA Device Registry entries for:
- Each Media Room Manager zone (identifiers keyed on zone ID).
- Each orchestrated physical device (identifiers keyed on device ID).

Entities created by the entities package are linked to these device entries
via their device_info properties, so HA groups them together in the UI.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo

from ..const import DOMAIN
from ..graph.system_config import SystemConfig

_LOGGER = logging.getLogger(__name__)


def _zone_device_info(zone_id: str, zone_name: str) -> DeviceInfo:
    """Build a DeviceInfo for a zone device registry entry.

    Parameters
    ----------
    zone_id:
        The zone's identifier string.
    zone_name:
        Human-readable name for the zone.
    """
    return DeviceInfo(
        identifiers={(DOMAIN, f"zone_{zone_id}")},
        name=zone_name,
        manufacturer="Media Room Manager",
    )


def _physical_device_info(device_id: str, device_name: str) -> DeviceInfo:
    """Build a DeviceInfo for a physical device registry entry.

    Parameters
    ----------
    device_id:
        The physical device's identifier string.
    device_name:
        Human-readable name for the device.
    """
    return DeviceInfo(
        identifiers={(DOMAIN, f"device_{device_id}")},
        name=device_name,
        manufacturer="Media Room Manager",
    )


async def async_register_devices(
    hass: HomeAssistant,
    entry: ConfigEntry,
    config: SystemConfig,
) -> None:
    """Create Device Registry entries for all zones and physical devices.

    Each zone gets its own device entry; each orchestrated physical device
    gets its own device entry. Entity device_info properties reference these
    entries via the same identifiers tuples.

    Parameters
    ----------
    hass:
        The Home Assistant instance.
    entry:
        The config entry for this integration installation.
    config:
        The full system configuration containing zones and devices.
    """
    dev_reg = dr.async_get(hass)

    # Register a device entry for each zone.
    for zone in config.zones:
        dev_reg.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, f"zone_{zone.id}")},
            name=zone.name,
            manufacturer="Media Room Manager",
        )
        _LOGGER.debug("Registered device registry entry for zone %r", zone.id)

    # Register a device entry for each physical device.
    for device in config.devices:
        dev_reg.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, f"device_{device.id}")},
            name=device.name,
            manufacturer="Media Room Manager",
        )
        _LOGGER.debug("Registered device registry entry for device %r", device.id)
