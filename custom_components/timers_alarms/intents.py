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
from .util import spoken_duration

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


class CancelTimerHandler(_Base):
    intent_type = INTENT_CANCEL

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        name = str(_val(intent_obj.slots, "name", "") or "").strip()
        response = intent_obj.create_response()
        # A ringing timer is dismissed first (flush the ring), then confirm.
        if intent_obj.device_id and await self.controller.stop_ring(intent_obj.device_id):
            response.async_set_speech("Okay.")
            return response
        timer = self.controller.find_timer(intent_obj.device_id, name)
        if timer is None:
            response.async_set_speech(
                f"I couldn't find {'that timer' if name else 'a timer'}."
            )
            return response
        await self.controller.cancel_timer(timer)
        label = f"the {timer.name} timer" if timer.name else "the timer"
        response.async_set_speech(f"Canceled {label}.")
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
        name = str(_val(intent_obj.slots, "name", "") or "").strip()
        response = intent_obj.create_response()
        if name:
            timer = self.controller.find_timer(intent_obj.device_id, name)
            response.async_set_speech(
                f"There's no {name} timer." if timer is None
                else f"{spoken_duration(timer.remaining())} left on the {name} timer."
            )
            return response
        timers = self.controller.timers_for(intent_obj.device_id) or self.controller.timers_for(None)
        if not timers:
            response.async_set_speech("No timers are running.")
        elif len(timers) == 1:
            t = timers[0]
            lbl = f"the {t.name} timer" if t.name else "the timer"
            response.async_set_speech(f"{spoken_duration(t.remaining())} left on {lbl}.")
        else:
            parts = [
                f"{spoken_duration(t.remaining())} on {t.name}" if t.name
                else spoken_duration(t.remaining())
                for t in timers
            ]
            response.async_set_speech(f"{len(timers)} timers: " + "; ".join(parts) + ".")
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
