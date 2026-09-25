"""Services for managing alerts from the dashboard / automations.

- timers_alarms.cancel: cancel one alert by id (the id the Alerts sensor exposes).
- timers_alarms.cancel_all: cancel all, optionally scoped to a device.
"""

from __future__ import annotations

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_ALERT_ID,
    ATTR_DEVICE_ID,
    DATA_CONTROLLER,
    DOMAIN,
    SERVICE_CANCEL,
    SERVICE_CANCEL_ALL,
)
from .controller import Controller

_CANCEL_SCHEMA = vol.Schema({vol.Required(ATTR_ALERT_ID): cv.string})
_CANCEL_ALL_SCHEMA = vol.Schema({vol.Optional(ATTR_DEVICE_ID): cv.string})


def _controller(hass: HomeAssistant) -> Controller | None:
    """The single-instance controller (first configured entry)."""
    for data in hass.data.get(DOMAIN, {}).values():
        if isinstance(data, dict) and DATA_CONTROLLER in data:
            return data[DATA_CONTROLLER]
    return None


def async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_CANCEL):
        return

    async def _cancel(call: ServiceCall) -> None:
        controller = _controller(hass)
        if controller:
            await controller.cancel_by_id(call.data[ATTR_ALERT_ID])

    async def _cancel_all(call: ServiceCall) -> None:
        controller = _controller(hass)
        if controller:
            await controller.cancel_all_timers(call.data.get(ATTR_DEVICE_ID))

    hass.services.async_register(DOMAIN, SERVICE_CANCEL, _cancel, _CANCEL_SCHEMA)
    hass.services.async_register(
        DOMAIN, SERVICE_CANCEL_ALL, _cancel_all, _CANCEL_ALL_SCHEMA
    )


def async_unregister_services(hass: HomeAssistant) -> None:
    hass.services.async_remove(DOMAIN, SERVICE_CANCEL)
    hass.services.async_remove(DOMAIN, SERVICE_CANCEL_ALL)
