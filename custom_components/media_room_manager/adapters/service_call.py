"""Adapter for service_call mechanism.

Calls an arbitrary HA service with statically-enumerated parameters.
The only runtime substitution is the $value sentinel: any dict value whose
string representation is exactly "$value" (the literal four characters, nothing
more) is replaced with the operation's input value at call time.

Partial embedding is NOT supported. "$value" must be the entire value of a
field, not a substring. "prefix-$value" is left unchanged.

Required kwargs for each method:
  domain:  str            — HA service domain
  service: str            — HA service name
  data:    dict[str, Any] — service data; top-level "$value" entries substituted
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .base import AdapterBase

_LOGGER = logging.getLogger(__name__)

_VALUE_SENTINEL = "$value"


def _substitute(data: dict[str, Any], value: Any) -> dict[str, Any]:
    """Return a copy of data with top-level "$value" entries replaced by value.

    Only exact matches are substituted. Partial embedding (e.g. "prefix-$value")
    is intentionally left unchanged.
    """
    return {k: (value if v == _VALUE_SENTINEL else v) for k, v in data.items()}


class ServiceCallAdapter(AdapterBase):
    """Calls an arbitrary HA service, optionally substituting $value at runtime."""

    async def _call(
        self,
        hass: HomeAssistant,
        domain: str,
        service: str,
        data: dict[str, Any],
        value: Any = None,
    ) -> None:
        """Substitute $value in data and call the service."""
        resolved = _substitute(data, value)
        await hass.services.async_call(domain, service, resolved, blocking=True)

    async def async_select_input(
        self,
        hass: HomeAssistant,
        entity_id: str,
        label: str,
        **kwargs: Any,
    ) -> None:
        """Call the configured service, substituting $value with the input label.

        Required kwargs: domain, service, data
        """
        await self._call(hass, kwargs["domain"], kwargs["service"], kwargs["data"], value=label)

    async def async_power_on(
        self,
        hass: HomeAssistant,
        entity_id: str,
        **kwargs: Any,
    ) -> None:
        """Call the configured power-on service.

        Required kwargs: domain, service, data
        """
        await self._call(hass, kwargs["domain"], kwargs["service"], kwargs["data"])

    async def async_power_off(
        self,
        hass: HomeAssistant,
        entity_id: str,
        **kwargs: Any,
    ) -> None:
        """Call the configured power-off service.

        Required kwargs: domain, service, data
        """
        await self._call(hass, kwargs["domain"], kwargs["service"], kwargs["data"])

    async def async_set_volume(
        self,
        hass: HomeAssistant,
        entity_id: str,
        level: float,
        **kwargs: Any,
    ) -> None:
        """Call the configured volume service, substituting $value with level.

        Required kwargs: domain, service, data
        """
        await self._call(hass, kwargs["domain"], kwargs["service"], kwargs["data"], value=level)

    async def async_mute(
        self,
        hass: HomeAssistant,
        entity_id: str,
        muted: bool,
        **kwargs: Any,
    ) -> None:
        """Call the configured mute service, substituting $value with muted.

        Required kwargs: domain, service, data
        """
        await self._call(hass, kwargs["domain"], kwargs["service"], kwargs["data"], value=muted)

    async def async_send_transport(
        self,
        hass: HomeAssistant,
        entity_id: str,
        command: str,
        position: float | None = None,
        **kwargs: Any,
    ) -> None:
        """Call the configured transport service, substituting $value with command or position.

        Required kwargs: domain, service, data
        For seek, position is used as the substituted value; for all other commands,
        the command string is used.
        """
        value: Any = command if position is None else position
        await self._call(hass, kwargs["domain"], kwargs["service"], kwargs["data"], value=value)
