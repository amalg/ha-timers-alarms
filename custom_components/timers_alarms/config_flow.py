"""Config flow for Voice Timers & Alarms.

Single-instance integration. M0 creates the entry with defaults; the options
flow (tones, fallback media player, volume, ring cap) is fleshed out in M4 once
the tone library exists.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_ENABLE_ALARMS,
    CONF_ENABLE_TIMERS,
    CONF_FALLBACK_MEDIA_PLAYER,
    DEFAULTS,
    DOMAIN,
)


class TimersAlarmsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Single-instance setup."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self.async_create_entry(
                title="Voice Timers & Alarms", data={}, options=dict(DEFAULTS)
            )
        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return TimersAlarmsOptionsFlow()


class TimersAlarmsOptionsFlow(OptionsFlow):
    """Options: toggles + a fallback media player. Tone selectors added in M4."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        opts = {**DEFAULTS, **self.config_entry.options}
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_ENABLE_TIMERS, default=opts[CONF_ENABLE_TIMERS]
                ): bool,
                vol.Required(
                    CONF_ENABLE_ALARMS, default=opts[CONF_ENABLE_ALARMS]
                ): bool,
                vol.Optional(
                    CONF_FALLBACK_MEDIA_PLAYER,
                    description={"suggested_value": opts[CONF_FALLBACK_MEDIA_PLAYER]},
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="media_player")
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
