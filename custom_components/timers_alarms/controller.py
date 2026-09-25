"""Controller: owns timer state, scheduling, persistence and the ring engine.

The intents call into this. One instance per config entry, in hass.data.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.network import get_url

from .const import (
    CONF_ALARM_TONE,
    CONF_FALLBACK_MEDIA_PLAYER,
    CONF_MAX_RING_SECONDS,
    CONF_RING_VOLUME,
    CONF_TIMER_TONE,
    DEFAULTS,
    SIGNAL_ALERTS_UPDATED,
    STATIC_URL_PATH,
    TONES,
)
from .models import Timer
from .ring import RingEngine
from .store import StateStore
from .util import (
    clock_hm_from_epoch,
    device_name,
    resolve_media_player,
    spoken_duration_adjective,
)

_LOGGER = logging.getLogger(__name__)


class Controller:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.store = StateStore(hass)
        self.ring = RingEngine(hass)
        self._timers: dict[str, Timer] = {}
        self._cancels: dict[str, Callable[[], None]] = {}  # timer_id -> unschedule
        # Alerts that have FIRED and are currently ringing — kept visible on the
        # dashboard (status "alerting") until dismissed or the ring self-caps.
        self._ringing: dict[str, Timer] = {}
        self._ring_cleanup: dict[str, Callable[[], None]] = {}  # id -> cancel

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
        self._notify()

    async def async_unload(self) -> None:
        for cancel in list(self._cancels.values()):
            cancel()
        self._cancels.clear()
        for cancel in list(self._ring_cleanup.values()):
            cancel()
        self._ring_cleanup.clear()
        self._ringing.clear()
        await self.ring.stop_all()

    async def _persist(self) -> None:
        await self.store.save_timers(list(self._timers.values()))

    def _notify(self) -> None:
        """Tell entities (the Alerts sensor) the active set changed."""
        async_dispatcher_send(self.hass, SIGNAL_ALERTS_UPDATED)

    # ── dashboard view ─────────────────────────────────────────────────────────
    def active_items(self) -> list[dict]:
        """A serializable snapshot of every active alert, soonest first — the
        single source of truth the Alerts sensor and panel render from.

        Each item carries where it will ring (target device + media_player) and
        an absolute fires_at (epoch seconds) so the panel can tick down locally.
        """
        def entry(t: Timer, ringing: bool) -> dict:
            target = device_name(self.hass, t.device_id)
            if target == "this device" and t.media_player:
                st = self.hass.states.get(t.media_player)
                target = (st.name if st else None) or t.media_player
            if t.kind == "alarm":
                label = f"{t.label_time} alarm" if t.label_time else "alarm"
            else:
                label = f"{spoken_duration_adjective(t.total_seconds)} timer"
            return {
                "id": t.id,
                "kind": t.kind,
                "status": "alerting" if ringing else "counting",
                "label": label,
                "target": target,
                "target_media_player": t.media_player,
                "fires_at": t.expires_at,
                "duration_s": t.total_seconds,
                "remaining_s": 0 if ringing else t.remaining(),
                "created": t.created_at,
            }

        # Ringing alerts float to the top, then the counting ones (soonest first).
        items = [entry(t, True) for t in sorted(self._ringing.values(), key=lambda t: t.expires_at)]
        items += [entry(t, False) for t in sorted(self._timers.values(), key=lambda t: t.expires_at)]
        return items

    # ── timers ───────────────────────────────────────────────────────────────
    async def create_timer(
        self,
        device_id: str | None,
        total_seconds: int,
        name: str = "",
        kind: str = "timer",
        label_time: str = "",
    ) -> Timer:
        mp = resolve_media_player(
            self.hass, device_id, self._opt(CONF_FALLBACK_MEDIA_PLAYER)
        )
        timer = Timer(
            device_id=device_id or "",
            media_player=mp,
            total_seconds=int(total_seconds),
            name=name.strip(),
            kind=kind,
            label_time=label_time,
        )
        self._timers[timer.id] = timer
        self._schedule(timer)
        await self._persist()
        self._notify()
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
            self._notify()
            return
        # Keep it visible as "alerting" while it rings; auto-clear just after the
        # ring's own safety cap in case nobody dismisses it.
        self._ringing[timer.id] = timer
        url, duration = self._tone(timer.kind)
        await self.ring.start(
            timer.device_id, timer.media_player, url, duration, self._max_ring
        )
        self._ring_cleanup[timer.id] = async_call_later(
            self.hass, self._max_ring + 2, lambda _now: self._end_ring(timer.id)
        )
        self._notify()

    def _end_ring(self, alert_id: str) -> None:
        """Drop a ringing alert from the dashboard (dismissed or self-capped)."""
        existed = self._ringing.pop(alert_id, None) is not None
        cancel = self._ring_cleanup.pop(alert_id, None)
        if cancel:
            cancel()
        if existed:
            self._notify()

    def timers_for(self, device_id: str | None) -> list[Timer]:
        items = list(self._timers.values())
        if device_id:
            items = [t for t in items if t.device_id == device_id]
        return sorted(items, key=lambda t: t.expires_at)

    def scoped_timers(self, device_id: str | None) -> list[Timer]:
        """Timers/alarms for cancel/list/reference: this device's, else all —
        ordered SOONEST-TO-FIRE so index 1 ('timer 1', 'the first one') is always
        the next alert to go off, matching the dashboard and the spoken list."""
        items = self.timers_for(device_id) or self.timers_for(None)
        return sorted(items, key=lambda t: t.expires_at)

    def find_by_index(self, device_id: str | None, index: int) -> Timer | None:
        ts = self.scoped_timers(device_id)
        return ts[index - 1] if 1 <= index <= len(ts) else None

    def find_by_duration(
        self, device_id: str | None, total_seconds: int
    ) -> Timer | None:
        for t in self.scoped_timers(device_id):
            if t.kind == "timer" and t.total_seconds == total_seconds:
                return t
        return None

    def find_by_time(
        self, device_id: str | None, hour: int, minute: int, ambiguous: bool
    ) -> Timer | None:
        """Find an alarm firing at the given clock time ('the 3 PM alarm'). When
        the hour was given without am/pm we match on the 12-hour position."""
        for t in self.scoped_timers(device_id):
            if t.kind != "alarm":
                continue
            h, m = clock_hm_from_epoch(t.expires_at)
            if m != minute:
                continue
            if h == hour or (ambiguous and h % 12 == hour % 12):
                return t
        return None

    def find_timer(self, device_id: str | None, name: str = "") -> Timer | None:
        """Fallback match: the soonest-created timer for this device."""
        ts = self.scoped_timers(device_id)
        return ts[0] if ts else None

    async def cancel_timer(self, timer: Timer) -> None:
        self._timers.pop(timer.id, None)
        cancel = self._cancels.pop(timer.id, None)
        if cancel:
            cancel()
        await self._persist()
        self._notify()

    async def cancel_by_id(self, alert_id: str) -> bool:
        """Cancel one alert by id (used by the dashboard/service). Works whether
        it's still counting down or currently ringing (flushes the ring)."""
        timer = self._timers.get(alert_id) or self._ringing.get(alert_id)
        if timer is None:
            return False
        if timer.device_id:
            await self.ring.stop(timer.device_id)
        if alert_id in self._ringing:
            self._end_ring(alert_id)
        else:
            await self.cancel_timer(timer)
        return True

    async def cancel_all_timers(self, device_id: str | None) -> list[Timer]:
        # Flush any active ring too (a fired alert is out of _timers and in
        # _ringing), then cancel the scheduled ones.
        if device_id:
            await self.ring.stop(device_id)
        else:
            await self.ring.stop_all()
        ringing = [t for t in list(self._ringing.values()) if not device_id or t.device_id == device_id]
        for t in ringing:
            self._end_ring(t.id)
        victims = self.timers_for(device_id)
        for t in victims:
            await self.cancel_timer(t)
        return victims + ringing

    async def stop_ring(self, device_id: str) -> bool:
        """Silence a ringing alert on a device (voice 'stop'/'cancel')."""
        was = await self.ring.stop(device_id)
        for tid in [t.id for t in list(self._ringing.values()) if t.device_id == device_id]:
            self._end_ring(tid)
        return was
