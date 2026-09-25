"""Helpers: media_player resolution, duration + clock formatting, alarm times.

Time parsing (parse_when) is deliberately notation-agnostic: the speech-to-text
engine is outside our control and, depending on the user's config, can emit a
spoken time as "7 pm", "7 p.m.", "7:00", "7.00", "700", "seven pm", "1900", etc.
So we capture the phrase as a wildcard in the sentences and parse it here in
Python rather than trying to enumerate every notation in hassil templates.
"""

from __future__ import annotations

import re
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


# ── notation-agnostic time/duration parsing (M3, for wildcard capture) ─────────
_ONES = {
    "zero": 0, "oh": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50}
_DUR_UNITS = (
    (r"(\d+)\s*(?:hours?|hrs?|h)(?![a-z])", 3600),
    (r"(\d+)\s*(?:minutes?|mins?)(?![a-z])", 60),
    (r"(\d+)\s*(?:seconds?|secs?)(?![a-z])", 1),
)


def _words_to_digits(t: str) -> str:
    """Turn spoken number words into digits: 'seven'->'7', 'twenty five'->'25',
    'six oh five'->'6 0 5'. Leaves existing digits alone."""
    # tens + ones first ("twenty five" -> 25)
    for tw, tv in _TENS.items():
        t = re.sub(
            rf"\b{tw}[\s-]+(one|two|three|four|five|six|seven|eight|nine)\b",
            lambda m: str(tv + _ONES[m.group(1)]),
            t,
        )
        t = re.sub(rf"\b{tw}\b", str(tv), t)
    for w, v in _ONES.items():
        t = re.sub(rf"\b{w}\b", str(v), t)
    return t


def _parse_duration_text(t: str) -> int:
    total, found = 0, False
    for pat, mult in _DUR_UNITS:
        for m in re.finditer(pat, t):
            total += int(m.group(1)) * mult
            found = True
    if not found and re.search(r"\b(?:an?\s+)?half\s+(?:an\s+)?hour\b", t):
        return 1800
    return total if found else 0


def _finish_tod(hour: int, minute: int, meridiem: str | None):
    if hour > 23 or minute > 59:
        return None
    if meridiem == "pm":
        return (hour if hour == 12 else (hour + 12) % 24, minute, False)
    if meridiem == "am":
        return (0 if hour == 12 else hour, minute, False)
    if hour == 0 or hour > 12:
        return (hour, minute, False)          # unambiguous 24-hour clock
    return (hour, minute, True)               # ambiguous 12h -> nearest future


def _parse_tod_text(raw: str):
    """(hour, minute, ambiguous) for a time-of-day in any notation, else None."""
    t = " " + raw.lower().strip() + " "
    meridiem = None
    # meridiem in any notation: pm, p.m., p. m., p m, 7pm (digit-attached);
    # and worded times of day. Lookbehind (not a letter) so "spam"/"example"
    # don't false-match, while "7pm" does.
    if re.search(r"(?<![a-z])p\.?\s*\.?m\.?(?![a-z])", t) or re.search(
        r"\b(afternoon|evening|tonight|noon|midday)\b", t
    ) or re.search(r"\bnight\b", t):
        meridiem = "pm"
    elif re.search(r"(?<![a-z])a\.?\s*\.?m\.?(?![a-z])", t) or re.search(
        r"\bmorning\b", t
    ):
        meridiem = "am"
    # named times
    if re.search(r"\b(noon|midday)\b", t):
        return (12, 0, False)
    if re.search(r"\bmidnight\b", t):
        return (0, 0, False)
    t = _words_to_digits(t)
    # relative minutes
    m = re.search(r"half\s+past\D*(\d{1,2})", t)
    if m:
        return _finish_tod(int(m.group(1)), 30, meridiem)
    m = re.search(r"quarter\s+past\D*(\d{1,2})", t)
    if m:
        return _finish_tod(int(m.group(1)), 15, meridiem)
    m = re.search(r"quarter\s+(?:to|til|till|until)\D*(\d{1,2})", t)
    if m:
        return _finish_tod((int(m.group(1)) - 1) % 24, 45, meridiem)
    m = re.search(r"(\d{1,2})\D*(?:past|after)\D*(\d{1,2})", t)  # "20 past 6"
    if m:
        return _finish_tod(int(m.group(2)), int(m.group(1)), meridiem)
    # any digit groups: "6.05"/"6:05" -> [6,05]; "610"/"1230" -> jammed; "6 0 5"
    nums = re.findall(r"\d+", t)
    if not nums:
        return None
    if len(nums) == 1:
        v = nums[0]
        if len(v) >= 3:                       # "610" -> 6:10, "1230" -> 12:30
            hour, minute = int(v[:-2]), int(v[-2:])
        else:
            hour, minute = int(v), 0
    else:
        hour = int(nums[0])
        rest = "".join(nums[1:])              # "0"+"5"->"05", "30"->"30"
        minute = int(rest[:2])
    return _finish_tod(hour, minute, meridiem)


def parse_when(text: str):
    """Classify a captured 'when' phrase.

    Returns ('timer', total_seconds) for a duration, ('alarm', h, m, ambiguous)
    for a time-of-day, or None. Duration wins when unit words are present, so
    'for 5 minutes' is always a timer even though '5' alone would read as a time.
    """
    if not text:
        return None
    t = text.strip().lower()
    secs = _parse_duration_text(t)
    if secs > 0:
        return ("timer", secs)
    tod = _parse_tod_text(t)
    if tod is not None:
        return ("alarm", *tod)
    return None
