"""Constants for the Voice Timers & Alarms integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "timers_alarms"

# Entity platforms this integration forwards (the "Alerts" dashboard surface).
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SWITCH]

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
    CONF_TIMER_TONE: "simple_timer",
    CONF_ALARM_TONE: "simple_alarm",
    CONF_FALLBACK_MEDIA_PLAYER: None,  # used only when the source device has no media_player
    CONF_RING_VOLUME: None,            # None = leave the device's current volume
    CONF_MAX_RING_SECONDS: 120,        # safety cap on a ring nobody dismisses
}

# Tone library. id -> (label, filename under tones/, duration_seconds).
# Defaults are the Amazon Alexa "Simple Timer" / "Simple Alarm" sounds (Amal's
# household devices — see tones/LICENSE.md re: not shipping these on resale
# units). "default" is the CC-BY HA Voice PE sound, kept as a clean fallback.
# The rest of the Alexa audition set lands as selectable options in M4.
TONES: dict[str, tuple[str, str, float]] = {
    "simple_timer": ("Simple Timer (Alexa)", "simple_timer.mp3", 6.0),
    "simple_alarm": ("Simple Alarm (Alexa)", "simple_alarm.mp3", 6.0),
    "default": ("Default (CC)", "default.flac", 2.7),
}

# Tones are served to media players from this URL path (static path registered
# in async_setup_entry).
STATIC_URL_PATH = f"/{DOMAIN}/tones"

# ── "Alerts" sidebar dashboard ────────────────────────────────────────────────
# The integration ships its own dashboard as a custom frontend panel (self-
# contained, no HACS, no hand-maintained YAML) and toggles its sidebar presence
# via switch.alerts_dashboard — mirroring how the EchoMuse add-on's dashboard is
# exposed. The panel web component is served statically from the integration.
FRONTEND_URL_PATH = f"/{DOMAIN}/frontend"   # static dir serving the panel JS
PANEL_URL_PATH = "alerts"                    # sidebar route (/alerts)
PANEL_WEBCOMPONENT = "ta-alerts-panel"
PANEL_TITLE = "Alerts"
PANEL_ICON = "mdi:bell-ring"
# Bumped when the panel JS changes so the browser re-fetches it.
PANEL_JS_VERSION = "2"

# Whether the Alerts panel is shown in the sidebar (switch state restored across
# restarts; defaults on). Kept in hass.data, not options, so a toggle needn't
# reload the whole entry.
DATA_PANEL_SHOWN = "panel_shown"

# Dispatcher signal fired by the Controller whenever the set of active alerts
# changes (create / cancel / expire / restore). The Alerts sensor listens.
SIGNAL_ALERTS_UPDATED = f"{DOMAIN}_alerts_updated"

# Services
SERVICE_CANCEL = "cancel"
SERVICE_CANCEL_ALL = "cancel_all"
ATTR_ALERT_ID = "id"
ATTR_DEVICE_ID = "device_id"

# Storage
STORAGE_KEY = f"{DOMAIN}.state"
STORAGE_VERSION = 1

# hass.data layout: hass.data[DOMAIN] = {"controller": Controller}
DATA_CONTROLLER = "controller"
