"""Per-zone MediaPlayerEntity for Media Room Manager.

Each zone configured in the system surfaces as a standard HA media_player entity.
The entity:
- Exposes the zone's source_list from its source visibility configuration.
- Routes select_source to the orchestrator.
- Routes transport commands to the active source's transport role holder.
- Routes volume commands to the zone's pinned volume authority.
- Subscribes to the metadata_source role holder's state changes and mirrors
  media_title, media_artist, media_album_name, media_image_url, etc.
- Computes supported_features as the static union of features across all
  devices that could hold a role in any path through this zone.
- State is off when no active path exists; playing/paused/idle from the
  underlying metadata_source entity; unavailable on error.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from homeassistant.components.media_player import MediaPlayerEntity
from homeassistant.components.media_player.const import MediaPlayerEntityFeature, MediaPlayerState
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.helpers.device_registry import DeviceInfo

from ..adapters.registry import AdapterRegistry
from ..const import DOMAIN
from ..graph.model import (
    ControlRole,
    InstanceBinding,
    SourceRef,
    Zone,
)
from ..graph.system_config import SystemConfig
from ..orchestrator.orchestrator import Orchestrator
from ..resolver.path import ActivePathsRegistry
from ..resolver.roles import RoleAssignment

_LOGGER = logging.getLogger(__name__)

# Mapping from ControlRole to MediaPlayerEntityFeature bits.
_ROLE_FEATURE_MAP: dict[ControlRole, MediaPlayerEntityFeature] = {
    ControlRole.TRANSPORT: (
        MediaPlayerEntityFeature.PLAY
        | MediaPlayerEntityFeature.PAUSE
        | MediaPlayerEntityFeature.STOP
        | MediaPlayerEntityFeature.NEXT_TRACK
        | MediaPlayerEntityFeature.PREVIOUS_TRACK
        | MediaPlayerEntityFeature.SEEK
    ),
    ControlRole.VOLUME: (
        MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.VOLUME_MUTE
    ),
    ControlRole.METADATA_SOURCE: MediaPlayerEntityFeature.BROWSE_MEDIA,
}

# Metadata attributes mirrored from the metadata_source role holder.
_METADATA_ATTRS = (
    "media_title",
    "media_artist",
    "media_album_name",
    "media_image_url",
    "media_duration",
    "media_position",
    "media_position_updated_at",
    "media_content_type",
    "media_content_id",
    "app_id",
    "app_name",
    "entity_picture",
)


def compute_supported_features(
    zone: Zone,
    config: SystemConfig,
) -> MediaPlayerEntityFeature:
    """Compute the static union of features for a zone.

    Scans all devices reachable as sink devices for the zone and all devices
    referenced as volume authority. Unions the feature bits for every role
    provided by any output group on those devices.

    Also adds SELECT_SOURCE if there are any source_visibility entries for
    the zone (i.e., sources the user can select).

    Parameters
    ----------
    zone:
        The zone to compute features for.
    config:
        The full system configuration.
    """
    features = MediaPlayerEntityFeature(0)

    # Collect all device IDs relevant to this zone:
    # - sink devices (likely have transport, metadata_source)
    # - volume authority (has volume)
    # - all devices in the graph (reachable through paths)
    relevant_device_ids: set[str] = set(zone.sink_device_ids)
    if zone.volume_authority_device_id:
        relevant_device_ids.add(zone.volume_authority_device_id)

    # Also include all devices that could be transit devices (the whole graph).
    # Per README: "union of features across all devices that could hold a role
    # in any path through this zone."  We scan all devices for roles.
    all_device_ids: set[str] = {d.id for d in config.devices}
    relevant_device_ids.update(all_device_ids)

    for device_id in relevant_device_ids:
        device = next((d for d in config.devices if d.id == device_id), None)
        if device is None:
            continue
        for og in device.output_groups:
            for role in og.provides_roles:
                if role in _ROLE_FEATURE_MAP:
                    features |= _ROLE_FEATURE_MAP[role]
                if role == ControlRole.SOURCE_SELECTION and og.selection_mechanism is not None:
                    features |= MediaPlayerEntityFeature.SELECT_SOURCE

    # If source visibility is configured for this zone, add SELECT_SOURCE.
    svs = next((s for s in config.source_visibility if s.zone_id == zone.id), None)
    if svs and svs.visible_sources:
        features |= MediaPlayerEntityFeature.SELECT_SOURCE

    return features


def _get_source_list(zone: Zone, config: SystemConfig) -> list[str]:
    """Return the ordered list of display names for the zone's visible sources.

    Looks up the SourceVisibilitySelection for the zone and builds the
    display name list. Falls back to device name or device_id if no
    display_name is set on the SourceRef.
    """
    svs = next((s for s in config.source_visibility if s.zone_id == zone.id), None)
    if svs is None:
        return []

    names: list[str] = []
    for src_ref in svs.visible_sources:
        if src_ref.display_name:
            names.append(src_ref.display_name)
        elif src_ref.virtual_source_id is not None:
            # Find the virtual source label on the device.
            device = next((d for d in config.devices if d.id == src_ref.device_id), None)
            if device:
                vs = next(
                    (v for v in device.virtual_sources if v.id == src_ref.virtual_source_id),
                    None,
                )
                names.append(vs.label if vs else src_ref.virtual_source_id)
            else:
                names.append(src_ref.virtual_source_id)
        else:
            device = next((d for d in config.devices if d.id == src_ref.device_id), None)
            names.append(device.name if device else src_ref.device_id)

    return names


def _find_source_ref(source_name: str, zone: Zone, config: SystemConfig) -> SourceRef | None:
    """Find the SourceRef matching a display name for select_source.

    Parameters
    ----------
    source_name:
        The display name as shown in source_list.
    zone:
        The zone to search within.
    config:
        The full system configuration.
    """
    svs = next((s for s in config.source_visibility if s.zone_id == zone.id), None)
    if svs is None:
        return None

    for src_ref in svs.visible_sources:
        if src_ref.display_name and src_ref.display_name == source_name:
            return src_ref
        if src_ref.virtual_source_id is not None and src_ref.display_name is None:
            device = next((d for d in config.devices if d.id == src_ref.device_id), None)
            if device:
                vs = next(
                    (v for v in device.virtual_sources if v.id == src_ref.virtual_source_id),
                    None,
                )
                label = vs.label if vs else src_ref.virtual_source_id
                if label == source_name:
                    return src_ref
        elif src_ref.virtual_source_id is None and src_ref.display_name is None:
            device = next((d for d in config.devices if d.id == src_ref.device_id), None)
            display = device.name if device else src_ref.device_id
            if display == source_name:
                return src_ref

    return None


def _resolve_entity_id_from_registry(hass: HomeAssistant, entity_registry_id: str) -> str | None:
    """Resolve an entity_registry_id UUID to an entity_id string.

    Parameters
    ----------
    hass:
        The Home Assistant instance.
    entity_registry_id:
        The entity registry UUID to look up.
    """
    from homeassistant.helpers import entity_registry as er

    reg = er.async_get(hass)
    entry = next((e for e in reg.entities.values() if e.id == entity_registry_id), None)
    return entry.entity_id if entry else None


class ZoneMediaPlayer(MediaPlayerEntity):
    """Virtual media_player entity representing a Media Room Manager zone.

    One instance is created per zone. It orchestrates the underlying physical
    devices and exposes a clean media_player interface to Home Assistant.
    """

    _attr_should_poll = False

    def __init__(
        self,
        hass: HomeAssistant,
        zone: Zone,
        config: SystemConfig,
        orchestrator: Orchestrator,
        active_paths: ActivePathsRegistry,
        adapter_registry: AdapterRegistry,
    ) -> None:
        """Initialize the zone media player entity.

        Parameters
        ----------
        hass:
            The Home Assistant instance.
        zone:
            The zone this entity represents.
        config:
            The full system configuration.
        orchestrator:
            The orchestrator used to activate/deactivate zones.
        active_paths:
            The shared in-memory active paths registry.
        adapter_registry:
            The adapter registry for issuing volume/transport commands.
        """
        self._zone = zone
        self._config = config
        self._orchestrator = orchestrator
        self._active_paths = active_paths
        self._adapter_registry = adapter_registry

        self._attr_unique_id = f"mrm_zone_{zone.id}"
        self._attr_name = zone.name
        self._attr_supported_features = compute_supported_features(zone, config)

        # Mutable state
        self._error_detail: str | None = None
        self._metadata: dict[str, Any] = {}
        self._metadata_unsub: Callable[[], None] | None = None
        self._metadata_entity_id: str | None = None

        # Set hass on init so HA framework can use it before async_added_to_hass.
        self.hass = hass

    # ------------------------------------------------------------------
    # HA Entity properties
    # ------------------------------------------------------------------

    @property
    def unique_id(self) -> str:
        """Return unique entity id."""
        return f"mrm_zone_{self._zone.id}"

    @property
    def name(self) -> str:
        """Return the zone name."""
        return self._zone.name

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the zone device registry entry."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"zone_{self._zone.id}")},
            name=self._zone.name,
            manufacturer="Media Room Manager",
        )

    # ------------------------------------------------------------------
    # MediaPlayer state
    # ------------------------------------------------------------------

    @property
    def state(self) -> MediaPlayerState | None:
        """Return the current state of the zone.

        - off: no active path
        - playing/paused/idle: from the metadata_source entity state
        - unavailable: on error
        """
        if self._error_detail is not None:
            return MediaPlayerState.OFF  # unavailable is handled by HA when entity is unavailable

        active = self._active_paths.get(self._zone.id)
        if active is None:
            return MediaPlayerState.OFF

        # Try to get state from the metadata_source entity.
        if self._metadata_entity_id and self.hass:
            ha_state = self.hass.states.get(self._metadata_entity_id)
            if ha_state is not None:
                return _map_ha_state_to_media_player_state(ha_state.state)

        return MediaPlayerState.IDLE

    @property
    def available(self) -> bool:
        """Return False when there is an error on the zone."""
        return self._error_detail is None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes including error_detail and metadata."""
        attrs: dict[str, Any] = {}
        if self._error_detail is not None:
            attrs["error_detail"] = self._error_detail
        return attrs

    # ------------------------------------------------------------------
    # Source list
    # ------------------------------------------------------------------

    @property
    def source_list(self) -> list[str]:
        """Return the list of available sources for this zone."""
        return _get_source_list(self._zone, self._config)

    @property
    def source(self) -> str | None:
        """Return the current active source name, if any."""
        active = self._active_paths.get(self._zone.id)
        if active is None:
            return None
        # Find the display name of the active source.
        svs = next((s for s in self._config.source_visibility if s.zone_id == self._zone.id), None)
        if svs is None:
            return None
        for src_ref in svs.visible_sources:
            if src_ref.device_id != active.source_device_id:
                continue
            if src_ref.virtual_source_id != active.virtual_source_id:
                continue
            if src_ref.display_name:
                return src_ref.display_name
            # Build display name from device/virtual source.
            if src_ref.virtual_source_id:
                device = next((d for d in self._config.devices if d.id == src_ref.device_id), None)
                if device:
                    vs = next(
                        (v for v in device.virtual_sources if v.id == src_ref.virtual_source_id),
                        None,
                    )
                    return vs.label if vs else src_ref.virtual_source_id
            device = next((d for d in self._config.devices if d.id == src_ref.device_id), None)
            return device.name if device else src_ref.device_id
        return None

    # ------------------------------------------------------------------
    # Metadata attributes
    # ------------------------------------------------------------------

    @property
    def media_title(self) -> str | None:
        """Return the media title from the metadata source."""
        val = self._metadata.get("media_title")
        return str(val) if val is not None else None

    @property
    def media_artist(self) -> str | None:
        """Return the media artist from the metadata source."""
        val = self._metadata.get("media_artist")
        return str(val) if val is not None else None

    @property
    def media_album_name(self) -> str | None:
        """Return the media album name from the metadata source."""
        val = self._metadata.get("media_album_name")
        return str(val) if val is not None else None

    @property
    def media_image_url(self) -> str | None:
        """Return the media image URL from the metadata source."""
        val = self._metadata.get("media_image_url")
        return str(val) if val is not None else None

    @property
    def media_duration(self) -> int | None:
        """Return the media duration (seconds) from the metadata source."""
        val = self._metadata.get("media_duration")
        return int(val) if val is not None else None

    @property
    def media_position(self) -> int | None:
        """Return the media position (seconds) from the metadata source."""
        val = self._metadata.get("media_position")
        return int(val) if val is not None else None

    @property
    def media_position_updated_at(self) -> Any:
        """Return when media_position was last updated."""
        return self._metadata.get("media_position_updated_at")

    @property
    def volume_level(self) -> float | None:
        """Return volume from the volume authority entity."""
        vol_entity_id = self._get_volume_entity_id()
        if vol_entity_id is None or self.hass is None:
            return None
        state = self.hass.states.get(vol_entity_id)
        if state is None:
            return None
        return state.attributes.get("volume_level")

    @property
    def is_volume_muted(self) -> bool | None:
        """Return mute state from the volume authority entity."""
        vol_entity_id = self._get_volume_entity_id()
        if vol_entity_id is None or self.hass is None:
            return None
        state = self.hass.states.get(vol_entity_id)
        if state is None:
            return None
        return state.attributes.get("is_volume_muted")

    # ------------------------------------------------------------------
    # Select source (triggers orchestrator activation)
    # ------------------------------------------------------------------

    async def async_select_source(self, source: str) -> None:
        """Select a source — triggers orchestrator zone activation.

        Parameters
        ----------
        source:
            Display name of the source to activate.
        """
        src_ref = _find_source_ref(source, self._zone, self._config)
        if src_ref is None:
            _LOGGER.warning(
                "Zone %s: select_source called with unknown source %r", self._zone.id, source
            )
            return

        result = await self._orchestrator.async_activate_zone(
            self._zone.id,
            src_ref.device_id,
            virtual_source_id=src_ref.virtual_source_id,
        )

        if not result.success:
            self._error_detail = result.error_detail
            self.async_write_ha_state()
            return

        self._error_detail = None

        # Update metadata subscription to the new role assignment.
        if result.role_assignment is not None:
            await self._async_update_metadata_subscription(result.role_assignment)

        self.async_write_ha_state()

    # ------------------------------------------------------------------
    # Transport commands
    # ------------------------------------------------------------------

    async def async_media_play(self) -> None:
        """Send play command to the active transport role holder."""
        await self._async_send_transport("play")

    async def async_media_pause(self) -> None:
        """Send pause command to the active transport role holder."""
        await self._async_send_transport("pause")

    async def async_media_stop(self) -> None:
        """Send stop command to the active transport role holder."""
        await self._async_send_transport("stop")

    async def async_media_next_track(self) -> None:
        """Send next track command to the active transport role holder."""
        await self._async_send_transport("next_track")

    async def async_media_previous_track(self) -> None:
        """Send previous track command to the active transport role holder."""
        await self._async_send_transport("previous_track")

    async def async_media_seek(self, position: float) -> None:
        """Send seek command to the active transport role holder.

        Parameters
        ----------
        position:
            Position to seek to in seconds.
        """
        await self._async_send_transport("seek", position=position)

    async def _async_send_transport(self, command: str, position: float | None = None) -> None:
        """Route a transport command to the active transport role holder.

        Parameters
        ----------
        command:
            Transport command string (play/pause/stop/next_track/previous_track/seek).
        position:
            For seek commands, the target position in seconds.
        """
        role_assignment = self._get_current_role_assignment()
        if role_assignment is None or role_assignment.transport_device_id is None:
            _LOGGER.debug(
                "Zone %s: transport command %r ignored — no active transport role holder",
                self._zone.id,
                command,
            )
            return

        entity_id, adapter = self._resolve_role_entity_and_adapter(
            role_assignment.transport_device_id,
            role_assignment.transport_output_group_id,
        )
        if entity_id is None or adapter is None:
            _LOGGER.warning(
                "Zone %s: cannot send transport %r — no entity/adapter for transport role",
                self._zone.id,
                command,
            )
            return

        await adapter.async_send_transport(self.hass, entity_id, command, position=position)

    # ------------------------------------------------------------------
    # Volume commands
    # ------------------------------------------------------------------

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level on the volume authority.

        Parameters
        ----------
        volume:
            Volume level 0.0-1.0.
        """
        entity_id, adapter = self._resolve_volume_entity_and_adapter()
        if entity_id is None or adapter is None:
            return
        await adapter.async_set_volume(self.hass, entity_id, volume)

    async def async_volume_up(self) -> None:
        """Increase volume on the volume authority."""
        entity_id, adapter = self._resolve_volume_entity_and_adapter()
        if entity_id is None or adapter is None:
            return
        await adapter.async_volume_up(self.hass, entity_id)

    async def async_volume_down(self) -> None:
        """Decrease volume on the volume authority."""
        entity_id, adapter = self._resolve_volume_entity_and_adapter()
        if entity_id is None or adapter is None:
            return
        await adapter.async_volume_down(self.hass, entity_id)

    async def async_mute_volume(self, mute: bool) -> None:
        """Set mute state on the volume authority.

        Parameters
        ----------
        mute:
            True to mute, False to unmute.
        """
        entity_id, adapter = self._resolve_volume_entity_and_adapter()
        if entity_id is None or adapter is None:
            return
        await adapter.async_mute(self.hass, entity_id, mute)

    # ------------------------------------------------------------------
    # HA lifecycle
    # ------------------------------------------------------------------

    async def async_added_to_hass(self) -> None:
        """Called when entity is added to HA. Set up any active subscriptions."""
        # If a path is already active (e.g. restoring state), subscribe to
        # the current metadata source.
        active = self._active_paths.get(self._zone.id)
        if active is not None:
            from ..resolver.roles import resolve_roles

            zone = self._zone
            role_assignment = resolve_roles(zone, active, self._config)
            await self._async_update_metadata_subscription(role_assignment)

    async def async_will_remove_from_hass(self) -> None:
        """Cancel state subscriptions when entity is removed."""
        self._cancel_metadata_subscription()

    # ------------------------------------------------------------------
    # Metadata subscription helpers
    # ------------------------------------------------------------------

    async def _async_update_metadata_subscription(self, role_assignment: RoleAssignment) -> None:
        """Subscribe to the new metadata_source entity state changes.

        Cancels any existing subscription first.

        Parameters
        ----------
        role_assignment:
            The new role assignment containing the metadata source device/og.
        """
        self._cancel_metadata_subscription()
        self._metadata = {}

        if role_assignment.metadata_source_device_id is None:
            self._metadata_entity_id = None
            return

        entity_id = self._resolve_role_entity_id(
            role_assignment.metadata_source_device_id,
            role_assignment.metadata_source_output_group_id,
        )
        if entity_id is None:
            self._metadata_entity_id = None
            return

        self._metadata_entity_id = entity_id

        # Populate initial metadata from current state.
        if self.hass:
            current_state = self.hass.states.get(entity_id)
            if current_state is not None:
                self._update_metadata_from_state(current_state)

        # Subscribe to future state changes.
        @callback
        def _on_state_change(event: Any) -> None:
            new_state: State | None = event.data.get("new_state")
            if new_state is not None:
                self._update_metadata_from_state(new_state)
                self.async_write_ha_state()

        if self.hass:
            self._metadata_unsub = self.hass.bus.async_listen(
                "state_changed",
                _on_state_change,
                event_filter=lambda e: e.data.get("entity_id") == entity_id,
            )

    def _cancel_metadata_subscription(self) -> None:
        """Cancel the current metadata_source state subscription if active."""
        if self._metadata_unsub is not None:
            self._metadata_unsub()
            self._metadata_unsub = None

    @callback
    def _update_metadata_from_state(self, state: State) -> None:
        """Update the local metadata dict from a HA State object.

        Parameters
        ----------
        state:
            The new state of the metadata source entity.
        """
        attrs = state.attributes
        for attr in _METADATA_ATTRS:
            value = attrs.get(attr)
            if value is not None:
                self._metadata[attr] = value
            else:
                self._metadata.pop(attr, None)

    # ------------------------------------------------------------------
    # Role / binding helpers
    # ------------------------------------------------------------------

    def _get_current_role_assignment(self) -> RoleAssignment | None:
        """Return the RoleAssignment for the currently active path, if any."""
        active = self._active_paths.get(self._zone.id)
        if active is None:
            return None
        from ..resolver.roles import resolve_roles

        return resolve_roles(self._zone, active, self._config)

    def _get_binding(self, device_id: str, output_group_id: str | None) -> InstanceBinding | None:
        """Return the InstanceBinding for (device_id, output_group_id), or None.

        Parameters
        ----------
        device_id:
            The device to look up.
        output_group_id:
            The output group to find the binding for.
        """
        inst = next((i for i in self._config.device_instances if i.device_id == device_id), None)
        if inst is None:
            return None
        if output_group_id is None:
            return inst.bindings[0] if inst.bindings else None
        return next((b for b in inst.bindings if b.output_group_id == output_group_id), None)

    def _resolve_role_entity_id(self, device_id: str, output_group_id: str | None) -> str | None:
        """Resolve a device/output_group pair to an entity_id string.

        Parameters
        ----------
        device_id:
            The device whose binding to look up.
        output_group_id:
            The output group binding to use.
        """
        binding = self._get_binding(device_id, output_group_id)
        if binding is None:
            return None
        return _resolve_entity_id_from_registry(self.hass, binding.entity_registry_id)

    def _resolve_role_entity_and_adapter(
        self, device_id: str, output_group_id: str | None
    ) -> tuple[str | None, Any]:
        """Resolve (entity_id, adapter) for a device/output_group pair.

        Parameters
        ----------
        device_id:
            The device whose binding to look up.
        output_group_id:
            The output group binding to use.

        Returns
        -------
        (entity_id, adapter) — either may be None if unresolvable.
        """
        binding = self._get_binding(device_id, output_group_id)
        if binding is None:
            return None, None

        entity_id = _resolve_entity_id_from_registry(self.hass, binding.entity_registry_id)
        if entity_id is None:
            return None, None

        device = next((d for d in self._config.devices if d.id == device_id), None)
        if device is None:
            return entity_id, None

        og_id = output_group_id or (device.output_groups[0].id if device.output_groups else None)
        og = next((og for og in device.output_groups if og.id == og_id), None)
        if og is None or og.selection_mechanism is None:
            # Fall back to media_player_source for media_player entities.
            if entity_id and "." in entity_id and entity_id.split(".")[0] == "media_player":
                return entity_id, self._adapter_registry.get("media_player_source")
            return entity_id, None

        adapter = self._adapter_registry.get(og.selection_mechanism.kind.value)
        return entity_id, adapter

    def _resolve_volume_entity_and_adapter(self) -> tuple[str | None, Any]:
        """Resolve the volume authority entity and adapter for this zone.

        Returns
        -------
        (entity_id, adapter) — either may be None if no volume authority is
        configured or unresolvable.
        """
        if self._zone.volume_authority_device_id is None:
            return None, None
        return self._resolve_role_entity_and_adapter(
            self._zone.volume_authority_device_id,
            self._zone.volume_authority_output_group_id,
        )

    def _get_volume_entity_id(self) -> str | None:
        """Return the entity_id of the volume authority entity, or None."""
        if self._zone.volume_authority_device_id is None:
            return None
        return self._resolve_role_entity_id(
            self._zone.volume_authority_device_id,
            self._zone.volume_authority_output_group_id,
        )

    # ------------------------------------------------------------------
    # Public mutators used by tests / other entities
    # ------------------------------------------------------------------

    def set_error(self, error_detail: str | None) -> None:
        """Set or clear the error state on this entity.

        Parameters
        ----------
        error_detail:
            Human-readable error description, or None to clear.
        """
        self._error_detail = error_detail
        self.async_write_ha_state()

    def notify_path_changed(self, role_assignment: RoleAssignment | None) -> None:
        """Called by external code when the active path or role assignment changes.

        Updates the metadata subscription and writes HA state.

        Parameters
        ----------
        role_assignment:
            The new role assignment, or None if the zone was deactivated.
        """
        if role_assignment is None:
            self._cancel_metadata_subscription()
            self._metadata = {}
            self._metadata_entity_id = None
        self.async_write_ha_state()


def _map_ha_state_to_media_player_state(state_str: str) -> MediaPlayerState:
    """Map a raw HA state string to a MediaPlayerState enum value.

    Parameters
    ----------
    state_str:
        The raw state string from a HA State object.
    """
    _STATE_MAP: dict[str, MediaPlayerState] = {
        "playing": MediaPlayerState.PLAYING,
        "paused": MediaPlayerState.PAUSED,
        "idle": MediaPlayerState.IDLE,
        "off": MediaPlayerState.OFF,
        "on": MediaPlayerState.IDLE,
        "standby": MediaPlayerState.IDLE,
        "buffering": MediaPlayerState.PLAYING,
    }
    return _STATE_MAP.get(state_str, MediaPlayerState.IDLE)
