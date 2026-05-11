"""Adapter for select_entity mechanism.

The bound entity is a select. Input selection maps to select.select_option.
No other operations (power, volume, transport) are supported by this mechanism.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .base import AdapterBase


class SelectEntityAdapter(AdapterBase):
    """Controls a select entity by choosing an option for input selection."""

    async def async_select_input(
        self,
        hass: HomeAssistant,
        entity_id: str,
        label: str,
        **kwargs: Any,
    ) -> None:
        """Select the option matching label via select.select_option."""
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": entity_id, "option": label},
            blocking=True,
        )
