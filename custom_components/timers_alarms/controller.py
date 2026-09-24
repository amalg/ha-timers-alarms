"""Controller: owns timer state, scheduling, persistence and the ring engine.

The intents call into this. One instance per config entry, in hass.data.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.network import get_url

from .const import (
    CONF_ALARM_TONE,
    CONF_FALLBACK_MEDIA_PLAYER,
    CONF_MAX_RING_SECONDS,
    CONF_RING_VOLUME,
    CONF_TIMER_TONE,
    DEFAULTS,
    STATIC_URL_PATH,
    TONES,
)
from .models import Timer
from .ring import RingEngine
from .store import StateStore
from .util import resolve_media_player

_LOGGER = logging.getLogger(__name__)


class Controller:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.store = StateStore(hass)
        self.ring = RingEngine(hass)
        self._timers: dict[str, Timer] = {}
        self._cancels: dict[str, Callable[[], None]] = {}  # timer_id -> unschedule

    # ── options ──────────────────────────────────────────────────────────────
    def _opt(self, key: str):
        return {**DEFAULTS, **self.entry.options}.get(key)

    @property
    def _max_ring(self) -> int:
        return int(self._opt(CONF_MAX_RING_SECONDS) or 120)

    def _tone(self, kind: str) -> tuple[str, float]:
        """Return (url, duration) for 'timer' or 'alarm' tone selection."""
        tone_id = self._opt(CONF_TIMER_TONE if kind == "timer" else CONF_ALARM_TONE)
        _label, filename, duration = TONES.get(tone_id) or TONES["default"]
        base = get_url(self.hass, prefer_external=False, allow_internal=True)
        return f"{base}{STATIC_URL_PATH}/{filename}", duration

    # ── lifecycle ────────────────────────────────────────────────────────────
    async def async_load(self) -> None:
        """Restore timers and reschedule the ones still in the future."""
        for t in await self.store.load_timers():
            if t.remaining() > 0:
                self._timers[t.id] = t
                self._schedule(t)
            # Timers that expired while HA was down are dropped in M1 (missed-ring
            # handling is M5).
        await self._persist()

    async def async_unload(self) -> None:
        for cancel in list(self._cancels.values()):
            cancel()
        self._cancels.clear()
        await self.ring.stop_all()

    async def _persist(self) -> None:
        await self.store.save_timers(list(self._timers.values()))

    # ── timers ───────────────────────────────────────────────────────────────
    async def create_timer(
        self, device_id: str | None, total_seconds: int, name: str = ""
    ) -> Timer:
        mp = resolve_media_player(
            self.hass, device_id, self._opt(CONF_FALLBACK_MEDIA_PLAYER)
        )
        timer = Timer(
            device_id=device_id or "",
            media_player=mp,
            total_seconds=int(total_seconds),
            name=name.strip(),
        )
        self._timers[timer.id] = timer
        self._schedule(timer)
        await self._persist()
        return timer

    def _schedule(self, timer: Timer) -> None:
        delay = max(0, timer.remaining())

        async def _fire(_now=None) -> None:
            await self._on_expire(timer.id)

        self._cancels[timer.id] = async_call_later(self.hass, delay, _fire)

    async def _on_expire(self, timer_id: str) -> None:
        timer = self._timers.pop(timer_id, None)
        self._cancels.pop(timer_id, None)
        if timer is None:
            return
        await self._persist()
        if not timer.media_player:
            _LOGGER.warning(
                "Timer %s expired but no media_player for device %s (set a fallback)",
                timer_id,
                timer.device_id,
            )
            return
        url, duration = self._tone("timer")
        await self.ring.start(
            timer.device_id, timer.media_player, url, duration, self._max_ring
        )

    def timers_for(self, device_id: str | None) -> list[Timer]:
        items = list(self._timers.values())
        if device_id:
            items = [t for t in items if t.device_id == device_id]
        return sorted(items, key=lambda t: t.expires_at)

    def find_timer(self, device_id: str | None, name: str = "") -> Timer | None:
        """Best-match a timer for cancel/status: by name if given, else the
        soonest for this device, else the only one."""
        candidates = self.timers_for(device_id) or self.timers_for(None)
        if name:
            name = name.strip().lower()
            named = [t for t in candidates if t.name.lower() == name]
            return named[0] if named else None
        return candidates[0] if candidates else None

    async def cancel_timer(self, timer: Timer) -> None:
        self._timers.pop(timer.id, None)
        cancel = self._cancels.pop(timer.id, None)
        if cancel:
            cancel()
        await self._persist()

    async def cancel_all_timers(self, device_id: str | None) -> int:
        victims = self.timers_for(device_id)
        for t in victims:
            await self.cancel_timer(t)
        return len(victims)

    async def stop_ring(self, device_id: str) -> bool:
        return await self.ring.stop(device_id)
