"""Active-alerts sensor — the data source for the Alerts dashboard.

One sensor whose state is the number of active timers/alarms and whose `items`
attribute is the full list (kind, label, target device, fires_at, remaining). The
custom panel and any ordinary Lovelace card can render from it; `ta_marker` lets
the panel find it without hard-coding an entity_id.
"""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DATA_CONTROLLER, DOMAIN, SIGNAL_ALERTS_UPDATED
from .controller import Controller


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    controller: Controller = hass.data[DOMAIN][entry.entry_id][DATA_CONTROLLER]
    async_add_entities([ActiveAlertsSensor(entry, controller)])


class ActiveAlertsSensor(SensorEntity):
    """Count of active timers/alarms, with the full list in attributes."""

    _attr_has_entity_name = False
    _attr_name = "Active Alerts"
    _attr_icon = "mdi:bell-ring"
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, controller: Controller) -> None:
        self._controller = controller
        self._attr_unique_id = f"{entry.entry_id}_active_alerts"

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_ALERTS_UPDATED, self._handle_update
            )
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> int:
        return len(self._controller.active_items())

    @property
    def extra_state_attributes(self) -> dict:
        items = self._controller.active_items()
        return {
            "ta_marker": True,  # lets the Alerts panel discover this entity
            "items": items,
            "timers": sum(1 for i in items if i["kind"] == "timer"),
            "alarms": sum(1 for i in items if i["kind"] == "alarm"),
        }
