"""Intent handlers. Device-exact via intent_obj.device_id.

Intent names must match the phrasings shipped in custom_sentences/.
"""

from __future__ import annotations

import voluptuous as vol

from homeassistant.helpers import config_validation as cv, intent

from .controller import Controller
from .util import spoken_duration

INTENT_START_TIMER = "TimersAlarmsStartTimer"
INTENT_CANCEL_TIMER = "TimersAlarmsCancelTimer"
INTENT_CANCEL_ALL_TIMERS = "TimersAlarmsCancelAllTimers"
INTENT_TIMER_STATUS = "TimersAlarmsTimerStatus"
INTENT_STOP_RINGING = "TimersAlarmsStopRinging"


class _Base(intent.IntentHandler):
    def __init__(self, controller: Controller) -> None:
        self.controller = controller


class StartTimerHandler(_Base):
    intent_type = INTENT_START_TIMER
    slot_schema = {
        vol.Optional("hours"): cv.positive_int,
        vol.Optional("minutes"): cv.positive_int,
        vol.Optional("seconds"): cv.positive_int,
        vol.Optional("name"): cv.string,
    }

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        slots = self.async_validate_slots(intent_obj.slots)
        h = slots.get("hours", {}).get("value", 0) or 0
        m = slots.get("minutes", {}).get("value", 0) or 0
        s = slots.get("seconds", {}).get("value", 0) or 0
        name = (slots.get("name", {}).get("value") or "").strip()
        total = int(h) * 3600 + int(m) * 60 + int(s)

        response = intent_obj.create_response()
        if total <= 0:
            response.async_set_speech("Sorry, how long should the timer be?")
            return response
        await self.controller.create_timer(intent_obj.device_id, total, name)
        prefix = f"{name} timer" if name else "Timer"
        response.async_set_speech(f"{prefix} set for {spoken_duration(total)}.")
        return response


class CancelTimerHandler(_Base):
    intent_type = INTENT_CANCEL_TIMER
    slot_schema = {vol.Optional("name"): cv.string}

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        slots = self.async_validate_slots(intent_obj.slots)
        name = (slots.get("name", {}).get("value") or "").strip()
        response = intent_obj.create_response()

        # "cancel"/"stop" while ringing dismisses the ring first.
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
    intent_type = INTENT_CANCEL_ALL_TIMERS

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        response = intent_obj.create_response()
        if intent_obj.device_id:
            await self.controller.stop_ring(intent_obj.device_id)
        n = await self.controller.cancel_all_timers(intent_obj.device_id)
        response.async_set_speech(
            "No timers to cancel." if n == 0 else f"Canceled {n} timer{'s' if n != 1 else ''}."
        )
        return response


class TimerStatusHandler(_Base):
    intent_type = INTENT_TIMER_STATUS
    slot_schema = {vol.Optional("name"): cv.string}

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        slots = self.async_validate_slots(intent_obj.slots)
        name = (slots.get("name", {}).get("value") or "").strip()
        response = intent_obj.create_response()

        if name:
            timer = self.controller.find_timer(intent_obj.device_id, name)
            if timer is None:
                response.async_set_speech(f"There's no {name} timer.")
            else:
                response.async_set_speech(
                    f"{spoken_duration(timer.remaining())} left on the {name} timer."
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
                else f"{spoken_duration(t.remaining())}"
                for t in timers
            ]
            response.async_set_speech(f"{len(timers)} timers: " + "; ".join(parts) + ".")
        return response


class StopRingingHandler(_Base):
    intent_type = INTENT_STOP_RINGING

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        response = intent_obj.create_response()
        stopped = False
        if intent_obj.device_id:
            stopped = await self.controller.stop_ring(intent_obj.device_id)
        # Deliberately terse; the ring is already flushed before this speaks.
        response.async_set_speech("Okay." if stopped else "Nothing is ringing.")
        return response


def async_register(controller: Controller) -> list[intent.IntentHandler]:
    """Register all handlers; return them so they can be removed on unload."""
    handlers: list[intent.IntentHandler] = [
        StartTimerHandler(controller),
        CancelTimerHandler(controller),
        CancelAllTimersHandler(controller),
        TimerStatusHandler(controller),
        StopRingingHandler(controller),
    ]
    for h in handlers:
        intent.async_register(controller.hass, h)
    return handlers
