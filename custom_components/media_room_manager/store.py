"""Store-backed persistence for Media Room Manager.

Wraps HA's homeassistant.helpers.storage.Store to load and save the system
configuration. All disk I/O goes through this class; nothing else in the
integration writes directly to the config directory.
"""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN, STORAGE_KEY, STORAGE_VERSION
from .graph.system_config import SystemConfig

_LOGGER = logging.getLogger(__name__)

_STORAGE_KEY = STORAGE_KEY
_STORAGE_VERSION = STORAGE_VERSION


class MRMStore:
    """Wrapper around HA's Store for Media Room Manager system configuration."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the store."""
        self._store: Store[dict] = Store(  # type: ignore[type-arg]
            hass,
            _STORAGE_VERSION,
            _STORAGE_KEY,
            private=True,
            atomic_writes=True,
        )
        self._config: SystemConfig | None = None

    async def async_load(self) -> SystemConfig:
        """Load configuration from storage, or return an empty config if none exists."""
        raw = await self._store.async_load()
        if raw is None:
            _LOGGER.debug("%s: no stored config found, starting empty", DOMAIN)
            self._config = SystemConfig.empty()
        else:
            try:
                self._config = SystemConfig.from_dict(raw)
                _LOGGER.debug(
                    "%s: loaded config with %d device(s) and %d zone(s)",
                    DOMAIN,
                    len(self._config.devices),
                    len(self._config.zones),
                )
            except Exception:
                _LOGGER.exception("%s: failed to parse stored config, starting empty", DOMAIN)
                self._config = SystemConfig.empty()
        return self._config

    async def async_save(self, config: SystemConfig) -> None:
        """Persist configuration to storage."""
        self._config = config
        await self._store.async_save(config.to_dict())
        _LOGGER.debug("%s: config saved", DOMAIN)

    @property
    def config(self) -> SystemConfig | None:
        """Return the in-memory config, or None if not yet loaded."""
        return self._config
