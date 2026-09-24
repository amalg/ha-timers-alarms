"""Persistence via HA's Store helper (JSON, survives restart)."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY, STORAGE_VERSION
from .models import Timer


class StateStore:
    """Loads/saves timers (alarms added in M3)."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)

    async def load_timers(self) -> list[Timer]:
        data = await self._store.async_load() or {}
        return [Timer.from_dict(d) for d in data.get("timers", [])]

    async def save_timers(self, timers: list[Timer]) -> None:
        data = await self._store.async_load() or {}
        data["timers"] = [t.to_dict() for t in timers]
        await self._store.async_save(data)
