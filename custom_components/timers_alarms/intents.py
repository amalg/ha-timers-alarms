"""Intent handlers — device-exact via intent_obj.device_id.

We OVERRIDE Home Assistant's built-in timer intent handlers (register our
handlers under the built-in intent_types). HA's comprehensive built-in timer
sentences then route into OUR logic (our store, device-exact ring, our tones),
with no sentence-matching gaps and no native timers slipping through. Extra
phrasings (bare "stop"/"cancel", "what timers are running") are added in
custom_sentences mapped to these same intent_types.

No slot_schema: built-in sentences may send timer-identifying slots we don't use
(start_hours/start_minutes/name/…); we read leniently and ignore the rest.
"""

from __future__ import annotations

from homeassistant.helpers import intent

from .controller import Controller
from .util import spoken_duration, spoken_duration_adjective

# Built-in intent types we take over.
INTENT_START = "HassStartTimer"
INTENT_CANCEL = "HassCancelTimer"
INTENT_CANCEL_ALL = "HassCancelAllTimers"
INTENT_STATUS = "HassTimerStatus"


def _val(slots: dict, key: str, default=None):
    v = slots.get(key)
    return v.get("value", default) if isinstance(v, dict) else default


def _int(slots: dict, key: str) -> int:
    try:
        return int(_val(slots, key, 0) or 0)
    except (TypeError, ValueError):
        return 0


class _Base(intent.IntentHandler):
    slot_schema = None  # accept any slots the built-in sentences produce

    def __init__(self, controller: Controller) -> None:
        self.controller = controller


class StartTimerHandler(_Base):
    intent_type = INTENT_START

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        s = intent_obj.slots
        total = _int(s, "hours") * 3600 + _int(s, "minutes") * 60 + _int(s, "seconds")
        name = str(_val(s, "name", "") or "").strip()
        response = intent_obj.create_response()
        if total <= 0:
            response.async_set_speech("Sorry, how long should the timer be?")
            return response
        await self.controller.create_timer(intent_obj.device_id, total, name)
        prefix = f"{name} timer" if name else "Timer"
        response.async_set_speech(f"{prefix} set for {spoken_duration(total)}.")
        return response


def _resolve(controller: Controller, dev: str | None, slots: dict):
    """Resolve a timer reference: by index/ordinal ('timer 1', 'the first timer'),
    by original duration ('the 20 minute timer'), else the soonest-created.
    Returns (timer_or_None, miss_message)."""
    idx = _int(slots, "index") or _int(slots, "ordinal")
    dur = _int(slots, "hours") * 3600 + _int(slots, "minutes") * 60 + _int(slots, "seconds")
    if idx:
        return controller.find_by_index(dev, idx), f"There's no timer {idx}."
    if dur > 0:
        return controller.find_by_duration(dev, dur), f"I don't have a {spoken_duration_adjective(dur)} timer."
    return controller.find_timer(dev), "I couldn't find a timer."


class CancelTimerHandler(_Base):
    intent_type = INTENT_CANCEL

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        dev = intent_obj.device_id
        response = intent_obj.create_response()
        # A ringing timer is dismissed first (flush the ring), then confirm.
        if dev and await self.controller.stop_ring(dev):
            response.async_set_speech("Okay.")
            return response
        timer, miss = _resolve(self.controller, dev, intent_obj.slots)
        if timer is None:
            response.async_set_speech(miss)
            return response
        await self.controller.cancel_timer(timer)
        response.async_set_speech(
            f"Canceled the {spoken_duration_adjective(timer.total_seconds)} timer."
        )
        return response


class CancelAllTimersHandler(_Base):
    intent_type = INTENT_CANCEL_ALL

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        response = intent_obj.create_response()
        if intent_obj.device_id:
            await self.controller.stop_ring(intent_obj.device_id)
        n = await self.controller.cancel_all_timers(intent_obj.device_id)
        response.async_set_speech(
            "No timers to cancel." if n == 0
            else f"Canceled {n} timer{'s' if n != 1 else ''}."
        )
        return response


class TimerStatusHandler(_Base):
    intent_type = INTENT_STATUS

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        dev = intent_obj.device_id
        s = intent_obj.slots
        response = intent_obj.create_response()
        # A specific timer referenced by index/ordinal/duration?
        if _int(s, "index") or _int(s, "ordinal") or (
            _int(s, "hours") + _int(s, "minutes") + _int(s, "seconds") > 0
        ):
            timer, _miss = _resolve(self.controller, dev, s)
            response.async_set_speech(
                "I couldn't find that timer." if timer is None
                else f"The {spoken_duration_adjective(timer.total_seconds)} timer has "
                     f"{spoken_duration(timer.remaining())} left."
            )
            return response
        timers = self.controller.scoped_timers(dev)
        if not timers:
            response.async_set_speech("No timers are running.")
        elif len(timers) == 1:
            t = timers[0]
            response.async_set_speech(
                f"You have one timer, set for {spoken_duration(t.total_seconds)}, "
                f"with {spoken_duration(t.remaining())} left."
            )
        else:
            parts = [
                f"Timer {i}, set for {spoken_duration(t.total_seconds)}, "
                f"has {spoken_duration(t.remaining())} left"
                for i, t in enumerate(timers, 1)
            ]
            response.async_set_speech(f"You have {len(timers)} timers. " + ". ".join(parts) + ".")
        return response


def async_register(controller: Controller) -> list[intent.IntentHandler]:
    handlers: list[intent.IntentHandler] = [
        StartTimerHandler(controller),
        CancelTimerHandler(controller),
        CancelAllTimersHandler(controller),
        TimerStatusHandler(controller),
    ]
    for h in handlers:
        intent.async_register(controller.hass, h)
    return handlers
