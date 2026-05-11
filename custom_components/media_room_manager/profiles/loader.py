"""Profile YAML loader.

Reads a YAML file from disk, validates it against the profile schema, and
returns a typed Profile dataclass. All I/O is synchronous — profiles are
loaded at startup, not on-demand.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import voluptuous as vol
import yaml

from .schema import profile_from_dict
from .types import Profile

_LOGGER = logging.getLogger(__name__)


def load_profile_yaml(path: Path) -> Profile:
    """Load and validate a profile from a YAML file.

    Raises:
        FileNotFoundError: if the path doesn't exist.
        vol.Invalid: if the file content doesn't match the profile schema.
        yaml.YAMLError: if the file isn't valid YAML.
    """
    raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise vol.Invalid(f"Profile at {path} must be a YAML mapping, got {type(raw).__name__}")
    return profile_from_dict(raw)
