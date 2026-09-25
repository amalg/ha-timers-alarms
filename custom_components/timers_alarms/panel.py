"""The 'Alerts' sidebar dashboard, shipped as part of the integration.

Rather than a hand-maintained Lovelace YAML dashboard, the integration serves a
small self-authored web component (no build step, no HACS) and registers it as a
custom frontend panel. switch.alerts_dashboard shows/hides it live — the same
"toggle in the sidebar" feel as the EchoMuse add-on's dashboard.
"""

from __future__ import annotations

import logging
import os

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import (
    DATA_PANEL_SHOWN,
    DOMAIN,
    FRONTEND_URL_PATH,
    PANEL_ICON,
    PANEL_JS_VERSION,
    PANEL_TITLE,
    PANEL_URL_PATH,
    PANEL_WEBCOMPONENT,
)

_LOGGER = logging.getLogger(__name__)

_FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend")


async def async_register_static(hass: HomeAssistant) -> None:
    """Serve the panel's JS from FRONTEND_URL_PATH (idempotent)."""
    data = hass.data.setdefault(DOMAIN, {})
    if data.get("_frontend_registered"):
        return
    await hass.http.async_register_static_paths(
        [StaticPathConfig(FRONTEND_URL_PATH, _FRONTEND_DIR, False)]
    )
    data["_frontend_registered"] = True


async def async_show_panel(hass: HomeAssistant) -> None:
    """Add the Alerts panel to the sidebar (idempotent)."""
    data = hass.data.setdefault(DOMAIN, {})
    if data.get(DATA_PANEL_SHOWN):
        return
    await async_register_static(hass)
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL_PATH,
        webcomponent_name=PANEL_WEBCOMPONENT,
        module_url=f"{FRONTEND_URL_PATH}/alerts-panel.js?v={PANEL_JS_VERSION}",
        sidebar_title=PANEL_TITLE,
        sidebar_icon=PANEL_ICON,
        require_admin=False,
    )
    data[DATA_PANEL_SHOWN] = True
    _LOGGER.debug("Alerts panel registered at /%s", PANEL_URL_PATH)


def async_hide_panel(hass: HomeAssistant) -> None:
    """Remove the Alerts panel from the sidebar (idempotent)."""
    data = hass.data.setdefault(DOMAIN, {})
    if not data.get(DATA_PANEL_SHOWN):
        return
    frontend.async_remove_panel(hass, PANEL_URL_PATH)
    data[DATA_PANEL_SHOWN] = False
    _LOGGER.debug("Alerts panel removed")
