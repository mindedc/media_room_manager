"""Adapter registry — maps mechanism kind strings to adapter instances.

The registry holds one pre-initialized instance per mechanism kind.
Adapters are stateless; hass and per-call config are passed at operation time.
"""

from __future__ import annotations

from .base import AdapterBase
from .media_player_source import MediaPlayerSourceAdapter
from .remote_command import RemoteCommandAdapter
from .select_entity import SelectEntityAdapter
from .service_call import ServiceCallAdapter
from .switch_combo import SwitchComboAdapter


class AdapterRegistry:
    """Maps mechanism kind strings to adapter instances.

    Used by the orchestrator to look up the adapter for an output group's
    selection mechanism or role_operations entry.
    """

    def __init__(self) -> None:
        """Initialize the registry with one instance per supported mechanism kind."""
        self._adapters: dict[str, AdapterBase] = {
            "media_player_source": MediaPlayerSourceAdapter(),
            "select_entity": SelectEntityAdapter(),
            "switch_combo": SwitchComboAdapter(),
            "remote_command": RemoteCommandAdapter(),
            "service_call": ServiceCallAdapter(),
        }

    def get(self, kind: str) -> AdapterBase | None:
        """Return the adapter instance for the given mechanism kind, or None."""
        return self._adapters.get(kind)

    def get_required(self, kind: str) -> AdapterBase:
        """Return the adapter for the given kind, raising ValueError if not found."""
        adapter = self._adapters.get(kind)
        if adapter is None:
            raise ValueError(
                f"No adapter registered for mechanism kind {kind!r}. "
                f"Supported kinds: {sorted(self._adapters)}"
            )
        return adapter

    def kinds(self) -> list[str]:
        """Return sorted list of all registered mechanism kind strings."""
        return sorted(self._adapters)
