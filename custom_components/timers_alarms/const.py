"""Constants for the Voice Timers & Alarms integration."""

from __future__ import annotations

DOMAIN = "timers_alarms"

# Config entry options
CONF_ENABLE_TIMERS = "enable_timers"
CONF_ENABLE_ALARMS = "enable_alarms"
CONF_TIMER_TONE = "timer_tone"
CONF_ALARM_TONE = "alarm_tone"
CONF_FALLBACK_MEDIA_PLAYER = "fallback_media_player"
CONF_RING_VOLUME = "ring_volume"
CONF_MAX_RING_SECONDS = "max_ring_seconds"

DEFAULTS = {
    CONF_ENABLE_TIMERS: True,
    CONF_ENABLE_ALARMS: True,
    CONF_TIMER_TONE: "default",
    CONF_ALARM_TONE: "default",
    CONF_FALLBACK_MEDIA_PLAYER: None,  # used only when the source device has no media_player
    CONF_RING_VOLUME: None,            # None = leave the device's current volume
    CONF_MAX_RING_SECONDS: 120,        # safety cap on a ring nobody dismisses
}

# Tone library. id -> (label, filename under tones/). "default" must always exist
# and should be a CC-licensed sound (resale hygiene). Filled out in M4.
TONES: dict[str, tuple[str, str]] = {
    "default": ("Default (CC)", "default.flac"),
}

# Storage
STORAGE_KEY = f"{DOMAIN}.state"
STORAGE_VERSION = 1

# hass.data layout: hass.data[DOMAIN] = {"controller": Controller}
DATA_CONTROLLER = "controller"
