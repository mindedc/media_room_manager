"""Tests for the const module."""

from custom_components.media_room_manager.const import DOMAIN


def test_domain() -> None:
    """Verify DOMAIN constant matches the integration domain."""
    assert DOMAIN == "media_room_manager"
