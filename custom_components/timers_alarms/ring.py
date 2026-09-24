"""Ring engine: loop a tone on a device's media_player until dismissed.

Device-exact: the caller passes the media_player belonging to the source device.
Verified working on emOS Dots and Nabu Casa Voice PE (spikes 2026-09-24): a
looped tone is heard, and a voice "stop" (routed to RingEngine.stop) silences it.
On dismissal we FLUSH first (media_stop) so the ring is gone before the assistant
speaks its confirmation.
"""

from __future__ import annotations

import asyncio
import logging

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

BURST_GAP_S = 0.4  # silence between loop bursts so a spoken "stop" can land


class RingEngine:
    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        # device_id -> (task, media_player)
        self._active: dict[str, tuple[asyncio.Task, str]] = {}

    def is_ringing(self, device_id: str) -> bool:
        return device_id in self._active

    async def start(
        self,
        device_id: str,
        media_player: str,
        tone_url: str,
        tone_duration: float,
        max_seconds: int,
    ) -> None:
        """Begin (or restart) a ring on media_player for device_id."""
        await self.stop(device_id)  # never stack two loops on one device
        task = self.hass.async_create_task(
            self._loop(device_id, media_player, tone_url, tone_duration, max_seconds)
        )
        self._active[device_id] = (task, media_player)

    async def _loop(
        self,
        device_id: str,
        media_player: str,
        tone_url: str,
        tone_duration: float,
        max_seconds: int,
    ) -> None:
        elapsed = 0.0
        try:
            while elapsed < max_seconds:
                await self.hass.services.async_call(
                    "media_player",
                    "play_media",
                    {
                        "entity_id": media_player,
                        "media_content_id": tone_url,
                        "media_content_type": "music",
                    },
                    blocking=False,
                )
                wait = max(1.0, float(tone_duration)) + BURST_GAP_S
                await asyncio.sleep(wait)
                elapsed += wait
            _LOGGER.info(
                "Ring on %s auto-stopped after %ss cap (no dismissal)",
                media_player,
                max_seconds,
            )
        except asyncio.CancelledError:
            raise
        finally:
            self._active.pop(device_id, None)
            await self._flush(media_player)

    async def stop(self, device_id: str) -> bool:
        """Silence the ring for a device NOW. Returns whether it was ringing."""
        entry = self._active.pop(device_id, None)
        if entry is None:
            return False
        task, media_player = entry
        task.cancel()
        await self._flush(media_player)
        return True

    async def stop_all(self) -> None:
        for device_id in list(self._active):
            await self.stop(device_id)

    async def _flush(self, media_player: str) -> None:
        try:
            await self.hass.services.async_call(
                "media_player", "media_stop", {"entity_id": media_player}, blocking=True
            )
        except Exception as err:  # noqa: BLE001 - flush must never raise into the loop
            _LOGGER.debug("media_stop on %s failed: %s", media_player, err)
