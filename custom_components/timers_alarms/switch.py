"""switch.alerts_dashboard — shows/hides the Alerts panel in the sidebar.

Mirrors how the EchoMuse add-on's dashboard is toggled: an entity that adds or
removes the sidebar dashboard live. State is restored across restarts; defaults
on so the dashboard is present out of the box.
"""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import panel
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([AlertsDashboardSwitch(entry)])


class AlertsDashboardSwitch(SwitchEntity, RestoreEntity):
    """Toggle the Alerts sidebar dashboard on/off."""

    _attr_has_entity_name = False
    _attr_name = "Alerts Dashboard"
    _attr_icon = "mdi:view-dashboard"
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry) -> None:
        self._attr_unique_id = f"{entry.entry_id}_alerts_dashboard"
        self._attr_is_on = True  # default until restored

    async def async_added_to_hass(self) -> None:
        last = await self.async_get_last_state()
        if last is not None:
            self._attr_is_on = last.state == "on"
        await self._apply()

    async def _apply(self) -> None:
        if self._attr_is_on:
            await panel.async_show_panel(self.hass)
        else:
            panel.async_hide_panel(self.hass)

    async def async_turn_on(self, **kwargs) -> None:
        self._attr_is_on = True
        await panel.async_show_panel(self.hass)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        self._attr_is_on = False
        panel.async_hide_panel(self.hass)
        self.async_write_ha_state()
