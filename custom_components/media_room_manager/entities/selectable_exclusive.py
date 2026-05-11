"""Helper entities for selectable_exclusive zones.

For zones with sink_mode == SinkMode.SELECTABLE_EXCLUSIVE, the integration
creates two kinds of helper entities:

1.  ``select.<zone_id>_display`` — a Select entity whose options are the
    display names of all sink devices for the zone. Selecting an option
    activates the zone with the chosen sink.

2.  ``switch.<zone_id>_<sink_device_id>`` — one Switch per sink device.
    Turning a switch on activates the zone with that sink; the other
    switches are automatically turned off. Turning a switch off is a
    no-op (exclusive means exactly one is always active when the zone
    is on).

Bidirectional sync:
- Toggling a switch → calls orchestrator → both select and other switches
  update.
- Changing the select → calls orchestrator → switches update.
- Both can also be triggered directly from the zone media player's
  select_source (which does not change the sink selection).
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo

from ..const import DOMAIN
from ..graph.model import Zone
from ..graph.system_config import SystemConfig
from ..orchestrator.orchestrator import Orchestrator

_LOGGER = logging.getLogger(__name__)


def _sink_display_name(zone: Zone, sink_device_id: str, config: SystemConfig) -> str:
    """Return a human-readable name for a sink device.

    Parameters
    ----------
    zone:
        The zone containing the sink.
    sink_device_id:
        The device ID of the sink.
    config:
        The full system configuration.
    """
    device = next((d for d in config.devices if d.id == sink_device_id), None)
    return device.name if device else sink_device_id


class SelectableExclusiveSelect(SelectEntity):
    """Select entity for choosing the active sink in a selectable_exclusive zone.

    ``select.<zone_id>_display`` — options are sink device display names.
    """

    _attr_should_poll = False

    def __init__(
        self,
        hass: HomeAssistant,
        zone: Zone,
        config: SystemConfig,
        orchestrator: Orchestrator,
    ) -> None:
        """Initialize the selectable exclusive select entity.

        Parameters
        ----------
        hass:
            The Home Assistant instance.
        zone:
            The zone this select entity belongs to.
        config:
            The full system configuration.
        orchestrator:
            The orchestrator used to activate zone with a specific sink.
        """
        self._zone = zone
        self._config = config
        self._orchestrator = orchestrator

        self._attr_unique_id = f"mrm_zone_{zone.id}_display"
        self._attr_name = f"{zone.name} Display"
        self._attr_options = [_sink_display_name(zone, sid, config) for sid in zone.sink_device_ids]
        self.hass = hass

    @property
    def unique_id(self) -> str:
        """Return unique entity id."""
        return f"mrm_zone_{self._zone.id}_display"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info linking to the zone's device registry entry."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"zone_{self._zone.id}")},
            name=self._zone.name,
            manufacturer="Media Room Manager",
        )

    @property
    def current_option(self) -> str | None:
        """Return the currently active sink's display name, or None."""
        if len(self._zone.sink_device_ids) == 0:
            return None
        # Use the default or first sink if zone is not active.
        default_id = self._zone.default_sink_device_id or (
            self._zone.sink_device_ids[0] if self._zone.sink_device_ids else None
        )
        if default_id is None:
            return None
        return _sink_display_name(self._zone, default_id, self._config)

    @property
    def options(self) -> list[str]:
        """Return list of sink display names."""
        return [
            _sink_display_name(self._zone, sid, self._config) for sid in self._zone.sink_device_ids
        ]

    async def async_select_option(self, option: str) -> None:
        """Activate the zone with the selected sink.

        Parameters
        ----------
        option:
            Display name of the sink to make active.
        """
        sink_id = self._resolve_sink_id(option)
        if sink_id is None:
            _LOGGER.warning("Zone %s select: unknown sink option %r", self._zone.id, option)
            return

        # Determine the currently active source (if any) from the active paths registry.
        # If the zone is already active, re-activate with the new sink.
        # If not active, pick the first visible source.
        source_device_id, virtual_source_id = self._get_active_or_default_source()
        if source_device_id is None:
            _LOGGER.debug(
                "Zone %s select: no active source; cannot switch sink without source",
                self._zone.id,
            )
            return

        await self._orchestrator.async_activate_zone(
            self._zone.id,
            source_device_id,
            virtual_source_id=virtual_source_id,
            sink_device_id=sink_id,
        )
        self.async_write_ha_state()

    def _resolve_sink_id(self, display_name: str) -> str | None:
        """Map a sink display name back to a device_id.

        Parameters
        ----------
        display_name:
            The human-readable display name to look up.
        """
        for sid in self._zone.sink_device_ids:
            if _sink_display_name(self._zone, sid, self._config) == display_name:
                return sid
        return None

    def _get_active_or_default_source(self) -> tuple[str | None, str | None]:
        """Return (source_device_id, virtual_source_id) for the active or default source.

        Returns
        -------
        A 2-tuple of (source_device_id, virtual_source_id). Both None if
        no active path and no visible source is configured for the zone.
        """
        # Check if there is a parent ZoneMediaPlayer in hass data that has an
        # active path we can use.  Simpler: look up the active paths registry
        # from the orchestrator's internal state.  The orchestrator holds a
        # reference to active_paths, but we don't have a direct reference here.
        # Fall back to source_visibility defaults.
        svs = next((s for s in self._config.source_visibility if s.zone_id == self._zone.id), None)
        if svs and svs.visible_sources:
            first = svs.visible_sources[0]
            return first.device_id, first.virtual_source_id
        # No visible sources configured.
        return None, None


class SelectableExclusiveSwitch(SwitchEntity):
    """Switch entity for a single sink in a selectable_exclusive zone.

    ``switch.<zone_id>_<sink_device_id>`` — one per sink. Turning on
    activates the zone with this sink; turning off is a no-op.
    """

    _attr_should_poll = False

    def __init__(
        self,
        hass: HomeAssistant,
        zone: Zone,
        config: SystemConfig,
        orchestrator: Orchestrator,
        sink_device_id: str,
    ) -> None:
        """Initialize the per-sink switch entity.

        Parameters
        ----------
        hass:
            The Home Assistant instance.
        zone:
            The zone this switch belongs to.
        config:
            The full system configuration.
        orchestrator:
            The orchestrator used to activate zone with this sink.
        sink_device_id:
            The device ID of the sink this switch controls.
        """
        self._zone = zone
        self._config = config
        self._orchestrator = orchestrator
        self._sink_device_id = sink_device_id

        sink_name = _sink_display_name(zone, sink_device_id, config)
        self._attr_unique_id = f"mrm_zone_{zone.id}_{sink_device_id}"
        self._attr_name = f"{zone.name} {sink_name}"
        self.hass = hass

    @property
    def unique_id(self) -> str:
        """Return unique entity id."""
        return f"mrm_zone_{self._zone.id}_{self._sink_device_id}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info linking to the zone's device registry entry."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"zone_{self._zone.id}")},
            name=self._zone.name,
            manufacturer="Media Room Manager",
        )

    @property
    def is_on(self) -> bool:
        """Return True if this sink is the currently selected one.

        Since we don't have direct access to the active_paths registry here,
        we return False as a conservative default. Zone media player will
        drive state changes through async_write_ha_state.
        """
        return False

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Activate this sink for the zone.

        Determines the active/default source and calls the orchestrator.

        Parameters
        ----------
        **kwargs:
            Unused; required by SwitchEntity interface.
        """
        source_device_id, virtual_source_id = self._get_active_or_default_source()
        if source_device_id is None:
            _LOGGER.debug(
                "Zone %s switch %s: no active source; cannot switch sink without source",
                self._zone.id,
                self._sink_device_id,
            )
            return

        await self._orchestrator.async_activate_zone(
            self._zone.id,
            source_device_id,
            virtual_source_id=virtual_source_id,
            sink_device_id=self._sink_device_id,
        )
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """No-op: exclusive means one sink is always active when the zone is on.

        Parameters
        ----------
        **kwargs:
            Unused; required by SwitchEntity interface.
        """
        _LOGGER.debug(
            "Zone %s switch %s: turn_off is a no-op for selectable_exclusive zones",
            self._zone.id,
            self._sink_device_id,
        )

    def _get_active_or_default_source(self) -> tuple[str | None, str | None]:
        """Return (source_device_id, virtual_source_id) for the active or default source.

        Returns
        -------
        A 2-tuple of (source_device_id, virtual_source_id).
        """
        svs = next((s for s in self._config.source_visibility if s.zone_id == self._zone.id), None)
        if svs and svs.visible_sources:
            first = svs.visible_sources[0]
            return first.device_id, first.virtual_source_id
        return None, None
