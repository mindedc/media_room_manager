"""Binary sensor for shared physical device usage tracking.

``binary_sensor.<device_id>_in_use`` is created for every physical device that
is reachable from more than one zone. It is ``on`` when the device appears in
any currently-active ZoneResolverResult's path device list.

This allows automations like "turn on the AVR cooling fan when the AVR is in
use by any zone" without coupling to a specific zone's media_player state.

Only created for devices reachable from > 1 zone (per README). Devices used
by exactly one zone are already covered by that zone's media_player state.
"""

from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo

from ..const import DOMAIN
from ..graph.model import Device
from ..graph.system_config import SystemConfig
from ..resolver.path import ActivePathsRegistry, ResolvedSinglePath

_LOGGER = logging.getLogger(__name__)


def _get_devices_in_active_paths(active_paths: ActivePathsRegistry) -> set[str]:
    """Collect all device IDs present in any currently-active path.

    Parameters
    ----------
    active_paths:
        The shared in-memory active paths registry.

    Returns
    -------
    Set of device_id strings for every device in any active path hop.
    """
    device_ids: set[str] = set()
    for result in active_paths.all_active().values():
        # Include source device (may have no hops but is still "in use").
        device_ids.add(result.source_device_id)
        # Include all hop devices from resolved paths.
        for path in list(result.video_paths) + list(result.audio_paths):
            if isinstance(path, ResolvedSinglePath):
                for hop in path.hops:
                    device_ids.add(hop.device_id)
    return device_ids


class DeviceInUseBinarySensor(BinarySensorEntity):
    """Binary sensor that is 'on' when a shared device is in any active path.

    Only created for devices reachable from more than one zone.
    """

    _attr_should_poll = False

    def __init__(
        self,
        hass: HomeAssistant,
        device: Device,
        config: SystemConfig,
        active_paths: ActivePathsRegistry,
    ) -> None:
        """Initialize the binary sensor.

        Parameters
        ----------
        hass:
            The Home Assistant instance.
        device:
            The physical device this sensor monitors.
        config:
            The full system configuration.
        active_paths:
            The shared active paths registry to query for device usage.
        """
        self._device = device
        self._config = config
        self._active_paths = active_paths

        self._attr_unique_id = f"mrm_device_{device.id}_in_use"
        self._attr_name = f"{device.name} In Use"
        self.hass = hass

    @property
    def unique_id(self) -> str:
        """Return unique entity id."""
        return f"mrm_device_{self._device.id}_in_use"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info linking to the physical device registry entry."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"device_{self._device.id}")},
            name=self._device.name,
            manufacturer="Media Room Manager",
        )

    @property
    def is_on(self) -> bool:
        """Return True if this device is in any currently-active path."""
        return self._device.id in _get_devices_in_active_paths(self._active_paths)

    def update_state(self) -> None:
        """Push a state update to HA. Called externally when paths change."""
        self.async_write_ha_state()
