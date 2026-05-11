"""Tests for ServiceCallAdapter, including $value substitution rules."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.media_room_manager.adapters.service_call import (
    ServiceCallAdapter,
    _substitute,
)


def _make_hass() -> MagicMock:
    hass = MagicMock()
    hass.services.async_call = AsyncMock()
    return hass


ENTITY_ID = "media_player.custom_device"


@pytest.fixture()
def adapter() -> ServiceCallAdapter:
    return ServiceCallAdapter()


# ---------------------------------------------------------------------------
# _substitute helper
# ---------------------------------------------------------------------------


def test_substitute_replaces_exact_sentinel() -> None:
    result = _substitute({"source": "$value", "extra": "fixed"}, "HDMI 1")
    assert result == {"source": "HDMI 1", "extra": "fixed"}


def test_substitute_does_not_replace_partial_match() -> None:
    """Only an exact "$value" string is substituted — not a substring."""
    result = _substitute({"cmd": "prefix-$value"}, "X")
    assert result["cmd"] == "prefix-$value"


def test_substitute_does_not_replace_postfix() -> None:
    result = _substitute({"cmd": "$value-suffix"}, "X")
    assert result["cmd"] == "$value-suffix"


def test_substitute_integer_value() -> None:
    result = _substitute({"level": "$value"}, 42)
    assert result["level"] == 42


def test_substitute_bool_value() -> None:
    result = _substitute({"muted": "$value"}, True)
    assert result["muted"] is True


def test_substitute_non_string_field_unchanged() -> None:
    result = _substitute({"count": 5, "name": "static"}, "replaced")
    assert result == {"count": 5, "name": "static"}


def test_substitute_multiple_sentinel_fields() -> None:
    result = _substitute({"a": "$value", "b": "$value"}, "val")
    assert result == {"a": "val", "b": "val"}


# ---------------------------------------------------------------------------
# async_select_input
# ---------------------------------------------------------------------------


async def test_select_input_substitutes_label(adapter: ServiceCallAdapter) -> None:
    hass = _make_hass()
    await adapter.async_select_input(
        hass,
        ENTITY_ID,
        "HDMI 2",
        domain="my_integration",
        service="select_source",
        data={"entity_id": ENTITY_ID, "source": "$value"},
    )
    hass.services.async_call.assert_called_once_with(
        "my_integration",
        "select_source",
        {"entity_id": ENTITY_ID, "source": "HDMI 2"},
        blocking=True,
    )


async def test_select_input_no_sentinel_passes_data_unchanged(
    adapter: ServiceCallAdapter,
) -> None:
    hass = _make_hass()
    await adapter.async_select_input(
        hass,
        ENTITY_ID,
        "ignored",
        domain="dom",
        service="svc",
        data={"key": "static_value"},
    )
    hass.services.async_call.assert_called_once_with(
        "dom", "svc", {"key": "static_value"}, blocking=True
    )


# ---------------------------------------------------------------------------
# async_power_on / off
# ---------------------------------------------------------------------------


async def test_power_on_calls_service(adapter: ServiceCallAdapter) -> None:
    hass = _make_hass()
    await adapter.async_power_on(
        hass, ENTITY_ID, domain="dom", service="power_on", data={"cmd": "ON"}
    )
    hass.services.async_call.assert_called_once_with(
        "dom", "power_on", {"cmd": "ON"}, blocking=True
    )


async def test_power_off_calls_service(adapter: ServiceCallAdapter) -> None:
    hass = _make_hass()
    await adapter.async_power_off(hass, ENTITY_ID, domain="dom", service="power_off", data={})
    hass.services.async_call.assert_called_once_with("dom", "power_off", {}, blocking=True)


# ---------------------------------------------------------------------------
# async_set_volume
# ---------------------------------------------------------------------------


async def test_set_volume_substitutes_level(adapter: ServiceCallAdapter) -> None:
    hass = _make_hass()
    await adapter.async_set_volume(
        hass,
        ENTITY_ID,
        0.75,
        domain="dom",
        service="set_vol",
        data={"vol": "$value"},
    )
    hass.services.async_call.assert_called_once_with("dom", "set_vol", {"vol": 0.75}, blocking=True)


# ---------------------------------------------------------------------------
# async_send_transport
# ---------------------------------------------------------------------------


async def test_transport_substitutes_command(adapter: ServiceCallAdapter) -> None:
    hass = _make_hass()
    await adapter.async_send_transport(
        hass,
        ENTITY_ID,
        "play",
        domain="dom",
        service="send_cmd",
        data={"action": "$value"},
    )
    hass.services.async_call.assert_called_once_with(
        "dom", "send_cmd", {"action": "play"}, blocking=True
    )


async def test_transport_seek_substitutes_position(adapter: ServiceCallAdapter) -> None:
    hass = _make_hass()
    await adapter.async_send_transport(
        hass,
        ENTITY_ID,
        "seek",
        position=90.0,
        domain="dom",
        service="seek",
        data={"pos": "$value"},
    )
    hass.services.async_call.assert_called_once_with("dom", "seek", {"pos": 90.0}, blocking=True)
