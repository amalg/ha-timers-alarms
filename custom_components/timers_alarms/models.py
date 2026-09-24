"""Data models for Voice Timers & Alarms."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


@dataclass
class Timer:
    """A countdown timer bound to the device that created it."""

    device_id: str
    media_player: str | None
    total_seconds: int
    name: str = ""
    id: str = field(default_factory=_new_id)
    # Monotonic-independent wall clock: stored so remaining time survives a
    # restart. created_at/expires_at are epoch seconds.
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0

    def __post_init__(self) -> None:
        if not self.expires_at:
            self.expires_at = self.created_at + self.total_seconds

    def remaining(self, now: float | None = None) -> int:
        """Whole seconds left, floored at 0."""
        now = time.time() if now is None else now
        return max(0, int(round(self.expires_at - now)))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "device_id": self.device_id,
            "media_player": self.media_player,
            "total_seconds": self.total_seconds,
            "name": self.name,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Timer":
        return cls(
            device_id=d["device_id"],
            media_player=d.get("media_player"),
            total_seconds=int(d["total_seconds"]),
            name=d.get("name", ""),
            id=d.get("id", _new_id()),
            created_at=float(d.get("created_at", time.time())),
            expires_at=float(d.get("expires_at", 0.0)),
        )
