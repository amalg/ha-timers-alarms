"""Helpers: media_player resolution, duration + clock formatting, alarm times."""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util


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


def spoken_duration_adjective(total_seconds: int) -> str:
    """Singular-unit form for use as an adjective before 'timer': '20 minute',
    '1 hour', '90 second'. Falls back to spoken_duration for mixed units."""
    h, rem = divmod(int(total_seconds), 3600)
    m, s = divmod(rem, 60)
    nonzero = [(n, u) for n, u in ((h, "hour"), (m, "minute"), (s, "second")) if n]
    if len(nonzero) == 1:
        n, u = nonzero[0]
        return f"{n} {u}"
    return spoken_duration(total_seconds)


# ── time-of-day / alarms (M3) ─────────────────────────────────────────────────
def apply_meridiem(hour: int, meridiem: str | None) -> int:
    """Fold a 12-hour clock + am/pm into a 0–23 hour."""
    if meridiem == "am":
        return 0 if hour == 12 else hour
    if meridiem == "pm":
        return hour if hour == 12 else (hour + 12) % 24
    return hour


def next_occurrence(hour: int, minute: int, ambiguous: bool) -> datetime:
    """The next local datetime matching hour:minute (one-shot alarm target).

    `ambiguous` means a 12-hour hour was given with no am/pm — we pick whichever
    of the two daily occurrences (H or H+12) comes soonest, like a phone alarm.
    """
    now = dt_util.now()

    def at(h: int) -> datetime:
        t = now.replace(hour=h % 24, minute=minute, second=0, microsecond=0)
        if t <= now:
            t += timedelta(days=1)
        return t

    if ambiguous:
        return min(at(hour), at(hour + 12))
    return at(hour)


def spoken_clock(dt: datetime) -> str:
    """'3 PM', '3:15 PM', '7:05 AM' — friendly for TTS and the dashboard."""
    h = dt.hour % 12 or 12
    mer = "AM" if dt.hour < 12 else "PM"
    return f"{h} {mer}" if dt.minute == 0 else f"{h}:{dt.minute:02d} {mer}"


def spoken_clock_from_epoch(epoch: float) -> str:
    return spoken_clock(dt_util.as_local(dt_util.utc_from_timestamp(epoch)))


def clock_hm_from_epoch(epoch: float) -> tuple[int, int]:
    """(hour, minute) in HA-local time for an alarm's fire time."""
    dt = dt_util.as_local(dt_util.utc_from_timestamp(epoch))
    return dt.hour, dt.minute


def count_phrase(timers: int, alarms: int) -> str:
    """'2 timers', '1 alarm', '2 timers and 1 alarm', 'nothing'."""
    parts = []
    if timers:
        parts.append(f"{timers} timer{'s' if timers != 1 else ''}")
    if alarms:
        parts.append(f"{alarms} alarm{'s' if alarms != 1 else ''}")
    if not parts:
        return "nothing"
    return " and ".join(parts)
