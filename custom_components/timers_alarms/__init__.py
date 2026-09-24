"""Voice Timers & Alarms — device-exact timers and alarms for HA Assist.

Scaffold (M0). Sets up the config entry and a per-entry controller placeholder.
Intent registration, the ring engine, and the timer/alarm managers land in M1+.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DATA_CONTROLLER, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Voice Timers & Alarms from a config entry."""
    domain_data = hass.data.setdefault(DOMAIN, {})

    # M1: build the Controller (store + timer/alarm managers + ring engine),
    # load persisted state, and register intents. For now, a placeholder so the
    # integration loads cleanly and options are available.
    domain_data[entry.entry_id] = {DATA_CONTROLLER: None}

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    _LOGGER.info("Voice Timers & Alarms set up (scaffold; intents land in M1)")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    domain_data = hass.data.get(DOMAIN, {})
    domain_data.pop(entry.entry_id, None)
    # M1: unregister intents, cancel scheduled timers/alarms, stop any ring.
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
