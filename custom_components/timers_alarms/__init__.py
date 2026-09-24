"""Voice Timers & Alarms — device-exact timers (M1) and alarms (M3) for HA Assist."""

from __future__ import annotations

import logging
import os

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent as intent_helper

from . import intents as intents_mod
from .const import DATA_CONTROLLER, DOMAIN, STATIC_URL_PATH
from .controller import Controller

_LOGGER = logging.getLogger(__name__)

_TONES_DIR = os.path.join(os.path.dirname(__file__), "tones")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Voice Timers & Alarms from a config entry."""
    domain_data = hass.data.setdefault(DOMAIN, {})

    # Serve bundled tones to media players (idempotent across reloads).
    if not domain_data.get("_static_registered"):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(STATIC_URL_PATH, _TONES_DIR, False)]
        )
        domain_data["_static_registered"] = True

    controller = Controller(hass, entry)
    await controller.async_load()
    handlers = intents_mod.async_register(controller)

    domain_data[entry.entry_id] = {DATA_CONTROLLER: controller, "handlers": handlers}
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    _LOGGER.info("Voice Timers & Alarms ready (M1 timers): %d intents", len(handlers))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload: stop scheduled timers/rings and remove intents."""
    domain_data = hass.data.get(DOMAIN, {})
    data = domain_data.pop(entry.entry_id, None)
    if data:
        controller: Controller = data[DATA_CONTROLLER]
        await controller.async_unload()
        # Best-effort intent de-registration (intents live in hass.data).
        registry = hass.data.get(intent_helper.DATA_KEY, {})
        for h in data.get("handlers", []):
            registry.pop(h.intent_type, None)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
