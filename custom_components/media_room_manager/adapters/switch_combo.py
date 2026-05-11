"""Adapter for switch_combo mechanism.

For matrices exposed as a grid of switch entities (one per output x input pair).
Input selection turns on the target switch and turns off all other switches in
the same row (the mutually exclusive set for that output).

Call signature for async_select_input:
  entity_id         — the switch entity to turn ON
  label             — the input label (informational; not used for the call)
  row_entity_ids    — all switch entity ids in this output's row, including the target.
                      Switches in this list other than entity_id are turned OFF first,
                      then entity_id is turned ON.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .base import AdapterBase

_LOGGER = logging.getLogger(__name__)


class SwitchComboAdapter(AdapterBase):
    """Controls a matrix row of switch entities for input selection."""

    async def async_select_input(
        self,
        hass: HomeAssistant,
        entity_id: str,
        label: str,
        **kwargs: Any,
    ) -> None:
        """Select the input by toggling switches in the row.

        Turns off all switches in row_entity_ids except entity_id, then turns
        on entity_id. The turn-off step runs before turn-on to avoid briefly
        having two inputs active on the same output.

        Required kwarg:
          row_entity_ids: list[str] — all switch entity ids in this output's row.
        """
        row_entity_ids: list[str] = kwargs["row_entity_ids"]
        others = [eid for eid in row_entity_ids if eid != entity_id]
        if others:
            await hass.services.async_call(
                "switch",
                "turn_off",
                {"entity_id": others},
                blocking=True,
            )
        await hass.services.async_call(
            "switch",
            "turn_on",
            {"entity_id": entity_id},
            blocking=True,
        )
