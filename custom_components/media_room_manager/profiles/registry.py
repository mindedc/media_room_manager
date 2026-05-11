"""Profile registry — loads and indexes bundled (and eventually community/local) profiles.

Layered loading order: local > community-fetched > bundled.
Only bundled profiles are implemented in Phase 2.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .loader import load_profile_yaml
from .types import Profile

_LOGGER = logging.getLogger(__name__)

_BUNDLED_DIR = Path(__file__).parent / "bundled"


class ProfileRegistry:
    """Loads and indexes device profiles.

    Profiles are keyed by profile_id. When multiple layers provide a profile
    with the same id, the highest-precedence layer wins: local > community > bundled.
    """

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._profiles: dict[str, Profile] = {}

    def load_bundled(self) -> None:
        """Load all bundled profiles from the package's profiles/bundled/ directory."""
        loaded = 0
        errors = 0
        for yaml_path in sorted(_BUNDLED_DIR.rglob("*.yaml")):
            try:
                profile = load_profile_yaml(yaml_path)
                self._profiles[profile.profile_id] = profile
                loaded += 1
                _LOGGER.debug("Loaded bundled profile %s from %s", profile.profile_id, yaml_path)
            except Exception as exc:
                errors += 1
                _LOGGER.warning("Failed to load profile %s: %s", yaml_path, exc)
        _LOGGER.info("ProfileRegistry: loaded %d bundled profile(s), %d error(s)", loaded, errors)

    def get(self, profile_id: str) -> Profile | None:
        """Return a profile by id, or None if not found."""
        return self._profiles.get(profile_id)

    def list_all(self) -> list[Profile]:
        """Return all loaded profiles, sorted by profile_id."""
        return sorted(self._profiles.values(), key=lambda p: p.profile_id)

    def __len__(self) -> int:
        """Return the number of loaded profiles."""
        return len(self._profiles)
