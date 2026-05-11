"""Orchestrator: translates zone activation requests into adapter call sequences.

Activation sequence
-------------------
1. Resolve path via PathResolver.
2. Enforce contention policy (deny → error; preempt → tear down conflicts).
3. Power on devices source→sink order, respecting power_handling and
   power_on_delay.
4. Select inputs in REVERSE order (sink→source), deduplicated by
   (device_id, output_group_id).
5. If a virtual source is requested, select it on the source device's binding.
6. Resolve roles (volume / transport / metadata_source).
7. Issue transport "play" on the transport role holder if present.
8. Update ActivePathsRegistry.
9. Return OrchestratorResult.

Deactivation sequence
---------------------
1. Retrieve the active ZoneResolverResult for the zone.
2. Remove the zone from ActivePathsRegistry.
3. Power off devices that are no longer used by any other active zone.
4. Return OrchestratorResult.

Every adapter call is wrapped in _call_with_retry which retries up to
retry_count additional times with a 0.5 s sleep between attempts.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from homeassistant.core import HomeAssistant

from ..adapters.registry import AdapterRegistry
from ..graph.model import ContentionPolicy, DeviceInstance, InstanceBinding, PowerHandling
from ..graph.system_config import SystemConfig
from ..resolver.path import (
    ActivePathsRegistry,
    ContentionReport,
    PathHop,
    PathResolver,
    ResolvedSinglePath,
    ZoneResolverResult,
)
from ..resolver.roles import RoleAssignment, resolve_roles

_LOGGER = logging.getLogger(__name__)

_RETRY_SLEEP: float = 0.5


# ---------------------------------------------------------------------------
# Protocols and result types
# ---------------------------------------------------------------------------


class DeviceStateTrackerProtocol(Protocol):
    """Protocol for querying observed device power state."""

    def get_power_state(self, device_id: str) -> str | None:
        """Return 'on', 'off', or None (unknown)."""
        ...


@dataclass(frozen=True)
class OrchestratorResult:
    """Result of an orchestrator activate or deactivate call."""

    success: bool
    zone_id: str
    error_detail: str | None = None
    contention_reports: tuple[ContentionReport, ...] = field(default_factory=tuple)
    role_assignment: RoleAssignment | None = None


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class Orchestrator:
    """Coordinates device power, input selection, and transport for zones.

    Parameters
    ----------
    hass:
        The Home Assistant instance.
    config:
        The current SystemConfig (devices, connections, zones, instances).
    adapter_registry:
        Maps mechanism kind strings to adapter instances.
    active_paths:
        Shared in-memory registry of currently-active zone paths.
    state_tracker:
        Optional; provides observed power state for toggle devices.
    retry_count:
        How many additional attempts to make on adapter failures (total
        attempts = retry_count + 1).
    entity_id_resolver:
        Optional callable mapping entity_registry_id → entity_id string.
        When omitted the HA entity registry is queried at call time.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        config: SystemConfig,
        adapter_registry: AdapterRegistry,
        active_paths: ActivePathsRegistry,
        state_tracker: DeviceStateTrackerProtocol | None = None,
        retry_count: int = 2,
        entity_id_resolver: Callable[[str], str | None] | None = None,
    ) -> None:
        """Initialise the orchestrator."""
        self._hass = hass
        self._config = config
        self._adapters = adapter_registry
        self._active = active_paths
        self._state_tracker = state_tracker
        self._retry_count = retry_count
        self._entity_id_resolver = entity_id_resolver

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def async_activate_zone(
        self,
        zone_id: str,
        source_device_id: str,
        virtual_source_id: str | None = None,
        sink_device_id: str | None = None,
    ) -> OrchestratorResult:
        """Activate a zone: resolve path, power on devices, select inputs.

        Parameters
        ----------
        zone_id:
            ID of the zone to activate.
        source_device_id:
            Device ID of the signal source.
        virtual_source_id:
            If set, a virtual source on source_device_id (e.g. tuner).
        sink_device_id:
            For selectable_exclusive zones, which sink to use.
        """
        try:
            return await self._do_activate(
                zone_id, source_device_id, virtual_source_id, sink_device_id
            )
        except Exception as exc:  # intentional broad catch
            _LOGGER.error("Zone %s activation failed: %s", zone_id, exc)
            return OrchestratorResult(
                success=False,
                zone_id=zone_id,
                error_detail=str(exc),
            )

    async def async_deactivate_zone(self, zone_id: str) -> OrchestratorResult:
        """Deactivate a zone: power off unused devices.

        Parameters
        ----------
        zone_id:
            ID of the zone to deactivate.
        """
        try:
            return await self._do_deactivate(zone_id)
        except Exception as exc:
            _LOGGER.error("Zone %s deactivation failed: %s", zone_id, exc)
            return OrchestratorResult(
                success=False,
                zone_id=zone_id,
                error_detail=str(exc),
            )

    # ------------------------------------------------------------------
    # Activation implementation
    # ------------------------------------------------------------------

    async def _do_activate(
        self,
        zone_id: str,
        source_device_id: str,
        virtual_source_id: str | None,
        sink_device_id: str | None,
    ) -> OrchestratorResult:
        zone = next((z for z in self._config.zones if z.id == zone_id), None)
        if zone is None:
            raise ValueError(f"Zone {zone_id!r} not found in config")

        resolver = PathResolver(self._config, self._active)
        result = resolver.resolve(zone_id, source_device_id, virtual_source_id, sink_device_id)

        # ---- Contention handling ----
        if result.contentions:
            if zone.contention_policy == ContentionPolicy.DENY:
                return OrchestratorResult(
                    success=False,
                    zone_id=zone_id,
                    error_detail="Contention detected and policy is DENY",
                    contention_reports=result.contentions,
                )

            if zone.contention_policy == ContentionPolicy.PREEMPT:
                conflicting_zones = {r.conflicting_zone_id for r in result.contentions}
                for conflicting_zone_id in conflicting_zones:
                    preempt_result = await self._do_deactivate(conflicting_zone_id)
                    if not preempt_result.success:
                        raise RuntimeError(
                            f"Failed to preempt zone {conflicting_zone_id!r}: "
                            f"{preempt_result.error_detail}"
                        )
                # Re-resolve now that conflicts are cleared.
                result = resolver.resolve(
                    zone_id, source_device_id, virtual_source_id, sink_device_id
                )

        # ---- Collect ordered device hops ----
        all_hops = _all_hops_ordered(result)

        # ---- Power on: source→sink order ----
        await self._power_on_sequence(all_hops)

        # ---- Input selection: sink→source order ----
        await self._input_select_sequence(all_hops)

        # ---- Virtual source selection ----
        if virtual_source_id is not None:
            await self._select_virtual_source(source_device_id, virtual_source_id)

        # ---- Role resolution ----
        role_assignment = resolve_roles(zone, result, self._config)

        # ---- Transport activation ----
        if role_assignment.transport_device_id is not None:
            await self._send_transport_play(
                role_assignment.transport_device_id,
                role_assignment.transport_output_group_id,
            )

        # ---- Update registry ----
        self._active.update(result)

        return OrchestratorResult(
            success=True,
            zone_id=zone_id,
            contention_reports=result.contentions,
            role_assignment=role_assignment,
        )

    # ------------------------------------------------------------------
    # Deactivation implementation
    # ------------------------------------------------------------------

    async def _do_deactivate(self, zone_id: str) -> OrchestratorResult:
        active_result = self._active.get(zone_id)

        # Collect devices in this zone's paths before removing.
        zone_device_ids: set[str] = set()
        if active_result is not None:
            for hop in _all_hops_ordered(active_result):
                zone_device_ids.add(hop.device_id)

        # Remove from registry first so contention checks below are clean.
        self._active.remove(zone_id)

        # Find devices still needed by other active zones.
        still_needed: set[str] = set()
        for other_result in self._active.all_active().values():
            for hop in _all_hops_ordered(other_result):
                still_needed.add(hop.device_id)

        # Power off devices no longer needed.
        for device_id in zone_device_ids:
            if device_id in still_needed:
                continue
            device = next((d for d in self._config.devices if d.id == device_id), None)
            if device is None:
                continue
            ph = self._effective_power_handling(device_id)
            if ph in (PowerHandling.ALWAYS_ON, PowerHandling.DISABLED):
                continue
            # For toggle: always issue turn-off (we can't be sure of current state).
            binding = self._any_binding_for_device(device_id)
            if binding is None:
                continue
            entity_id = self._resolve_entity_id(binding.entity_registry_id)
            if entity_id is None:
                _LOGGER.warning(
                    "Cannot power off device %s: entity_registry_id %s not found",
                    device_id,
                    binding.entity_registry_id,
                )
                continue
            adapter = self._get_adapter_for_binding(binding) or self._infer_adapter(entity_id)
            if adapter is None:
                _LOGGER.debug("Skipping power-off for device %s: no adapter resolved", device_id)
                continue
            await self._call_with_retry(
                adapter.async_power_off, self._hass, entity_id, **self._mechanism_kwargs(binding)
            )

        return OrchestratorResult(success=True, zone_id=zone_id)

    # ------------------------------------------------------------------
    # Power-on helpers
    # ------------------------------------------------------------------

    async def _power_on_sequence(self, hops: list[PathHop]) -> None:
        """Power on devices in path order (source→sink), skipping duplicates."""
        seen: set[str] = set()
        for hop in hops:
            device_id = hop.device_id
            if device_id in seen:
                continue
            seen.add(device_id)

            device = next((d for d in self._config.devices if d.id == device_id), None)
            if device is None:
                continue

            ph = self._effective_power_handling(device_id)

            if ph == PowerHandling.DISABLED or ph == PowerHandling.ALWAYS_ON:
                continue

            if ph == PowerHandling.TOGGLE:
                # Only issue power on if state is not already "on".
                state = (
                    self._state_tracker.get_power_state(device_id) if self._state_tracker else None
                )
                if state == "on":
                    continue

            # discrete_capable or toggle (not-on): issue power on.
            binding = self._any_binding_for_device(device_id)
            if binding is None:
                continue
            entity_id = self._resolve_entity_id(binding.entity_registry_id)
            if entity_id is None:
                _LOGGER.warning(
                    "Cannot power on device %s: entity_registry_id %s not found",
                    device_id,
                    binding.entity_registry_id,
                )
                continue
            adapter = self._get_adapter_for_binding(binding) or self._infer_adapter(entity_id)
            if adapter is None:
                _LOGGER.debug("Skipping power-on for device %s: no adapter resolved", device_id)
                continue

            await self._call_with_retry(
                adapter.async_power_on, self._hass, entity_id, **self._mechanism_kwargs(binding)
            )

            # Respect power_on_delay.
            if device.power_on_delay > 0:
                await asyncio.sleep(device.power_on_delay)

    # ------------------------------------------------------------------
    # Input selection helpers
    # ------------------------------------------------------------------

    async def _input_select_sequence(self, hops: list[PathHop]) -> None:
        """Select inputs in reverse (sink→source) order, deduplicating by og."""
        seen: set[tuple[str, str]] = set()
        for hop in reversed(hops):
            if hop.entry_interface_id is None:
                # Source hop: no input to select.
                continue
            if hop.output_group_id is None:
                # No selection mechanism for this hop.
                continue

            key = (hop.device_id, hop.output_group_id)
            if key in seen:
                continue
            seen.add(key)

            device = next((d for d in self._config.devices if d.id == hop.device_id), None)
            if device is None:
                continue

            og = next((og for og in device.output_groups if og.id == hop.output_group_id), None)
            if og is None or og.selection_mechanism is None:
                continue

            # Determine the label: the label of the entry interface.
            entry_iface = next(
                (i for i in device.interfaces if i.id == hop.entry_interface_id), None
            )
            if entry_iface is None:
                continue

            label = entry_iface.label

            # Find the binding for this output group.
            binding = self._get_binding(hop.device_id, hop.output_group_id)
            if binding is None:
                continue
            label = self._apply_label_remap(binding, label)

            entity_id = self._resolve_entity_id(binding.entity_registry_id)
            if entity_id is None:
                _LOGGER.warning(
                    "Cannot select input on device %s og %s: entity_registry_id %s not found",
                    hop.device_id,
                    hop.output_group_id,
                    binding.entity_registry_id,
                )
                continue

            adapter = self._adapters.get(og.selection_mechanism.kind.value)
            if adapter is None:
                continue

            await self._call_with_retry(
                adapter.async_select_input,
                self._hass,
                entity_id,
                label,
                **self._mechanism_kwargs(binding),
            )

    # ------------------------------------------------------------------
    # Virtual source selection
    # ------------------------------------------------------------------

    async def _select_virtual_source(self, source_device_id: str, virtual_source_id: str) -> None:
        """Select a virtual source on the source device's primary binding."""
        device = next((d for d in self._config.devices if d.id == source_device_id), None)
        if device is None:
            return

        # Find the virtual source label.
        vs = next((vs for vs in device.virtual_sources if vs.id == virtual_source_id), None)
        if vs is None:
            _LOGGER.warning(
                "Virtual source %s not found on device %s", virtual_source_id, source_device_id
            )
            return

        label = vs.label

        # Find the binding on the output group that routes this virtual source.
        og_id: str | None = vs.routable_to_output_group[0] if vs.routable_to_output_group else None
        if og_id is None and device.output_groups:
            og_id = device.output_groups[0].id

        binding = self._get_binding(source_device_id, og_id) if og_id else None
        if binding is None:
            # Fall back to any binding on this device.
            binding = self._any_binding_for_device(source_device_id)
        if binding is None:
            _LOGGER.warning(
                "No binding found for virtual source selection on device %s", source_device_id
            )
            return

        label = self._apply_label_remap(binding, label)
        entity_id = self._resolve_entity_id(binding.entity_registry_id)
        if entity_id is None:
            _LOGGER.warning(
                "Cannot select virtual source on device %s: entity_registry_id %s not found",
                source_device_id,
                binding.entity_registry_id,
            )
            return

        og = next((og for og in device.output_groups if og.id == binding.output_group_id), None)
        if og is None or og.selection_mechanism is None:
            return

        adapter = self._adapters.get(og.selection_mechanism.kind.value)
        if adapter is None:
            return

        await self._call_with_retry(
            adapter.async_select_input,
            self._hass,
            entity_id,
            label,
            **self._mechanism_kwargs(binding),
        )

    # ------------------------------------------------------------------
    # Transport helpers
    # ------------------------------------------------------------------

    async def _send_transport_play(self, device_id: str, output_group_id: str | None) -> None:
        """Issue a transport 'play' command on the given device/output_group."""
        binding = self._get_binding(device_id, output_group_id)
        if binding is None:
            binding = self._any_binding_for_device(device_id)
        if binding is None:
            _LOGGER.warning("No binding for transport play on device %s", device_id)
            return

        entity_id = self._resolve_entity_id(binding.entity_registry_id)
        if entity_id is None:
            _LOGGER.warning(
                "Cannot send transport play on device %s: entity_registry_id %s not found",
                device_id,
                binding.entity_registry_id,
            )
            return

        device = next((d for d in self._config.devices if d.id == device_id), None)
        if device is None:
            return

        og_id = binding.output_group_id
        og = next((og for og in device.output_groups if og.id == og_id), None)
        if og is None or og.selection_mechanism is None:
            return

        adapter = self._adapters.get(og.selection_mechanism.kind.value)
        if adapter is None:
            return

        await self._call_with_retry(
            adapter.async_send_transport,
            self._hass,
            entity_id,
            "play",
            **self._mechanism_kwargs(binding),
        )

    # ------------------------------------------------------------------
    # Retry wrapper
    # ------------------------------------------------------------------

    async def _call_with_retry(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        """Call *func* with retries on failure.

        Attempts up to retry_count + 1 times total.  Sleeps _RETRY_SLEEP
        seconds between attempts.  Re-raises on the final failure.
        """
        last_exc: Exception | None = None
        total_attempts = self._retry_count + 1
        for attempt in range(total_attempts):
            try:
                await func(*args, **kwargs)
                return
            except Exception as exc:
                last_exc = exc
                if attempt < total_attempts - 1:
                    _LOGGER.debug(
                        "Adapter call %s failed (attempt %d/%d): %s; retrying…",
                        getattr(func, "__name__", func),
                        attempt + 1,
                        total_attempts,
                        exc,
                    )
                    await asyncio.sleep(_RETRY_SLEEP)
        if last_exc is not None:
            raise last_exc

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------

    def _get_binding(self, device_id: str, output_group_id: str | None) -> InstanceBinding | None:
        """Return the InstanceBinding for (device_id, output_group_id), or None."""
        inst = next((i for i in self._config.device_instances if i.device_id == device_id), None)
        if inst is None:
            return None
        if output_group_id is None:
            return inst.bindings[0] if inst.bindings else None
        return next((b for b in inst.bindings if b.output_group_id == output_group_id), None)

    def _any_binding_for_device(self, device_id: str) -> InstanceBinding | None:
        """Return the first available InstanceBinding for device_id, or None."""
        inst = next((i for i in self._config.device_instances if i.device_id == device_id), None)
        if inst is None or not inst.bindings:
            return None
        return inst.bindings[0]

    def _resolve_entity_id(self, entity_registry_id: str) -> str | None:
        """Map entity_registry_id to an entity_id string.

        Uses the injected resolver if provided; otherwise queries the HA
        entity registry directly.
        """
        if self._entity_id_resolver is not None:
            return self._entity_id_resolver(entity_registry_id)

        from homeassistant.helpers import entity_registry as er  # local import

        reg = er.async_get(self._hass)
        entry = next((e for e in reg.entities.values() if e.id == entity_registry_id), None)
        return entry.entity_id if entry else None

    def _apply_label_remap(self, binding: InstanceBinding, label: str) -> str:
        """Return the remapped label if a remap is defined; otherwise the original."""
        for original, remapped in binding.label_remaps:
            if label == original:
                return remapped
        return label

    def _mechanism_kwargs(self, binding: InstanceBinding) -> dict[str, Any]:
        """Return mechanism-specific kwargs from binding.mechanism_params."""
        return dict(binding.mechanism_params)

    def _effective_power_handling(self, device_id: str) -> PowerHandling:
        """Return the effective power handling for device_id.

        Checks for a DeviceInstance override first, then falls back to the
        device's own power_handling field.
        """
        inst: DeviceInstance | None = next(
            (i for i in self._config.device_instances if i.device_id == device_id), None
        )
        if inst is not None and inst.power_handling_override is not None:
            return inst.power_handling_override
        device = next((d for d in self._config.devices if d.id == device_id), None)
        if device is None:
            return PowerHandling.DISABLED
        return device.power_handling

    def _get_adapter_for_binding(self, binding: InstanceBinding) -> Any:
        """Return the adapter to use for power operations on the device owning this binding.

        First tries the output group's own selection_mechanism.  If that output
        group has no mechanism, falls back to scanning other output groups on
        the same device.  Returns None only when no mechanism is found anywhere
        on the device (e.g. a fully passive device with no bound entities).
        """
        # Find the device + instance that owns this binding.
        device: Any = None
        for d in self._config.devices:
            for di in self._config.device_instances:
                if di.device_id != d.id:
                    continue
                for b in di.bindings:
                    if (
                        b.output_group_id == binding.output_group_id
                        and b.entity_registry_id == binding.entity_registry_id
                    ):
                        device = d

        if device is None:
            return None

        # Try the specific output group first.
        og = next((og for og in device.output_groups if og.id == binding.output_group_id), None)
        if og is not None and og.selection_mechanism is not None:
            return self._adapters.get(og.selection_mechanism.kind.value)

        # Fall back to any output group with a mechanism on this device.
        for og in device.output_groups:
            if og.selection_mechanism is not None:
                return self._adapters.get(og.selection_mechanism.kind.value)

        # Last resort: check other bindings on the same device instance for the mechanism.
        device_inst: DeviceInstance | None = next(
            (i for i in self._config.device_instances if i.device_id == device.id), None
        )
        if device_inst is not None:
            for other_binding in device_inst.bindings:
                other_og = next(
                    (og for og in device.output_groups if og.id == other_binding.output_group_id),
                    None,
                )
                if other_og is not None and other_og.selection_mechanism is not None:
                    return self._adapters.get(other_og.selection_mechanism.kind.value)

        return None

    def _infer_adapter(self, entity_id: str) -> Any:
        """Infer an adapter from the entity_id domain when no mechanism is explicit.

        Falls back to ``media_player_source`` for media_player entities so
        power operations work on sink devices (e.g. TVs) that have no input
        selection mechanism defined.
        """
        domain = entity_id.split(".", 1)[0] if "." in entity_id else ""
        if domain == "media_player":
            return self._adapters.get("media_player_source")
        return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _all_hops_ordered(result: ZoneResolverResult) -> list[PathHop]:
    """Return all hops from all resolved paths in result, in path order.

    De-duplicates by (device_id) across paths so power-on / deactivation
    processing each device once.  Ordering is source-to-sink.
    """
    hops: list[PathHop] = []
    seen_devices: set[str] = set()

    for path in list(result.video_paths) + list(result.audio_paths):
        if not isinstance(path, ResolvedSinglePath):
            continue
        for hop in path.hops:
            if hop.device_id not in seen_devices:
                seen_devices.add(hop.device_id)
                hops.append(hop)

    return hops
