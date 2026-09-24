"""Helpers: resolving the source device's media_player, duration formatting."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er


def resolve_media_player(
    hass: HomeAssistant, device_id: str | None, fallback: str | None
) -> str | None:
    """Return the media_player entity_id to ring on for a source device.

    Prefers a media_player that belongs to the SAME HA device as the voice
    satellite (device-exact — an emOS Dot / Voice PE carries its media_player on
    the same device). Falls back to the configured fallback player when the
    source device has no speaker (or no device_id was supplied, e.g. a text
    command).
    """
    if device_id:
        ent_reg = er.async_get(hass)
        entities = er.async_entries_for_device(ent_reg, device_id, include_disabled_entities=False)
        players = [e.entity_id for e in entities if e.domain == "media_player"]
        # Prefer an assist/voice-assistant media_player if several exist.
        players.sort(key=lambda eid: (0 if "voice" in eid or "assist" in eid else 1, eid))
        if players:
            return players[0]
    return fallback


def device_name(hass: HomeAssistant, device_id: str | None) -> str:
    if not device_id:
        return "this device"
    dev = dr.async_get(hass).async_get(device_id)
    if dev:
        return dev.name_by_user or dev.name or "this device"
    return "this device"


def spoken_duration(total_seconds: int) -> str:
    """'1 hour and 5 minutes', '10 minutes', '30 seconds'."""
    h, rem = divmod(int(total_seconds), 3600)
    m, s = divmod(rem, 60)
    parts: list[str] = []
    if h:
        parts.append(f"{h} hour{'s' if h != 1 else ''}")
    if m:
        parts.append(f"{m} minute{'s' if m != 1 else ''}")
    if s and not h:  # drop seconds once we're into hours; keep for m:s and bare s
        parts.append(f"{s} second{'s' if s != 1 else ''}")
    if not parts:
        return "0 seconds"
    if len(parts) == 1:
        return parts[0]
    return " and ".join([", ".join(parts[:-1]), parts[-1]]) if len(parts) > 2 else " and ".join(parts)
