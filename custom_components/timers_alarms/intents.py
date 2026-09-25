"""Intent handlers — device-exact via intent_obj.device_id.

We OVERRIDE Home Assistant's built-in timer intent handlers (register our
handlers under the built-in intent_types), so both HA's built-in timer sentences
and our own custom sentences route into our store / device-exact ring / tones.

M3 unifies timers and alarms: the keyword (timer / alarm / alert) is cosmetic —
what decides the behavior is the KIND OF TIME given. A duration ("for 20
minutes") is a countdown timer; a time-of-day ("for 3 pm", "at 7:30") is a
one-shot alarm (we compute seconds-until-next-occurrence and use the same
countdown+ring machinery, tagged kind="alarm"). Everything self-deletes on
expiry or cancel.

No slot_schema: built-in sentences may send slots we don't use; we read leniently.
"""

from __future__ import annotations

from homeassistant.helpers import intent
from homeassistant.util import dt as dt_util

from .controller import Controller
from .util import (
    apply_meridiem,
    count_phrase,
    next_occurrence,
    spoken_clock,
    spoken_duration,
    spoken_duration_adjective,
)

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


def _duration(slots: dict) -> int:
    return _int(slots, "hours") * 3600 + _int(slots, "minutes") * 60 + _int(slots, "seconds")


def _parse_clock(slots: dict) -> tuple[int, int, bool] | None:
    """Return (hour_0_23, minute, ambiguous) for a time-of-day, else None.

    `ambiguous` = a 1–12 hour was given with no am/pm, so the alarm should land on
    whichever of the two daily occurrences is soonest.
    """
    named = _val(slots, "named_time")  # "12:00" (noon) / "00:00" (midnight)
    if named:
        h, m = named.split(":")
        return int(h), int(m), False
    if "time_hour" not in slots:
        return None
    hour = _int(slots, "time_hour")
    minute = _int(slots, "time_minute")
    past = _val(slots, "past_min")  # "half past 7" -> 30
    to = _val(slots, "to_min")      # "quarter to 5" -> 45, hour-1
    if past is not None:
        minute = int(past)
    if to is not None:
        minute = int(to)
        hour = (hour - 1) % 24
    mer = _val(slots, "meridiem")
    if mer:
        return apply_meridiem(hour, mer), minute, False
    if hour == 0 or hour > 12:
        return hour, minute, False  # unambiguous 24-hour clock
    return hour, minute, True


def _describe(t) -> str:
    """Spoken noun phrase for one alert: 'the 20 minute timer' / 'the 3 PM alarm'."""
    if t.kind == "alarm":
        return f"{t.label_time} alarm" if t.label_time else "alarm"
    return f"{spoken_duration_adjective(t.total_seconds)} timer"


class _Base(intent.IntentHandler):
    slot_schema = None  # accept any slots the built-in sentences produce

    def __init__(self, controller: Controller) -> None:
        self.controller = controller


class StartTimerHandler(_Base):
    intent_type = INTENT_START

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        s = intent_obj.slots
        dev = intent_obj.device_id
        response = intent_obj.create_response()

        clock = _parse_clock(s)
        if clock is not None:
            hour, minute, ambiguous = clock
            target = next_occurrence(hour, minute, ambiguous)
            total = int(round((target - dt_util.now()).total_seconds()))
            total = max(1, total)
            label = spoken_clock(target)
            await self.controller.create_timer(
                dev, total, kind="alarm", label_time=label
            )
            response.async_set_speech(f"Alarm set for {label}.")
            return response

        total = _duration(s)
        if total > 0:
            await self.controller.create_timer(dev, total, kind="timer")
            response.async_set_speech(f"Timer set for {spoken_duration(total)}.")
            return response

        response.async_set_speech(
            "Sorry, how long should it run, or what time should it go off?"
        )
        return response


def _resolve(controller: Controller, dev: str | None, slots: dict):
    """Resolve an alert reference. Returns (alert_or_None, miss_message).

    By index/ordinal ('number 1', 'the first one'), by alarm time ('the 3 pm
    alarm'), by timer duration ('the 20 minute timer'), else the soonest.
    """
    idx = _int(slots, "index") or _int(slots, "ordinal")
    if idx:
        return controller.find_by_index(dev, idx), f"There's no number {idx}."
    clock = _parse_clock(slots)
    if clock is not None:
        hour, minute, ambiguous = clock
        return (
            controller.find_by_time(dev, hour, minute, ambiguous),
            "I don't have an alarm set for that time.",
        )
    dur = _duration(slots)
    if dur > 0:
        return (
            controller.find_by_duration(dev, dur),
            f"I don't have a {spoken_duration_adjective(dur)} timer.",
        )
    return controller.find_timer(dev), "I couldn't find a timer or alarm."


def _has_reference(slots: dict) -> bool:
    return bool(
        _int(slots, "index")
        or _int(slots, "ordinal")
        or _parse_clock(slots) is not None
        or _duration(slots) > 0
    )


class CancelTimerHandler(_Base):
    intent_type = INTENT_CANCEL

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        dev = intent_obj.device_id
        response = intent_obj.create_response()
        # A ringing alert is dismissed first (flush the ring), then confirm.
        if dev and await self.controller.stop_ring(dev):
            response.async_set_speech("Okay.")
            return response
        alert, miss = _resolve(self.controller, dev, intent_obj.slots)
        if alert is None:
            response.async_set_speech(miss)
            return response
        await self.controller.cancel_timer(alert)
        response.async_set_speech(f"Canceled the {_describe(alert)}.")
        return response


class CancelAllTimersHandler(_Base):
    intent_type = INTENT_CANCEL_ALL

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        response = intent_obj.create_response()
        if intent_obj.device_id:
            await self.controller.stop_ring(intent_obj.device_id)
        victims = await self.controller.cancel_all_timers(intent_obj.device_id)
        if not victims:
            response.async_set_speech("No timers or alarms to cancel.")
            return response
        timers = sum(1 for t in victims if t.kind == "timer")
        alarms = sum(1 for t in victims if t.kind == "alarm")
        response.async_set_speech(f"Canceled {count_phrase(timers, alarms)}.")
        return response


class TimerStatusHandler(_Base):
    intent_type = INTENT_STATUS

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        dev = intent_obj.device_id
        s = intent_obj.slots
        response = intent_obj.create_response()

        # A specific alert referenced by number / alarm time / timer duration?
        if _has_reference(s):
            alert, _miss = _resolve(self.controller, dev, s)
            if alert is None:
                response.async_set_speech("I couldn't find that one.")
            elif alert.kind == "alarm":
                response.async_set_speech(
                    f"The {alert.label_time} alarm goes off in "
                    f"{spoken_duration(alert.remaining())}."
                )
            else:
                response.async_set_speech(
                    f"The {spoken_duration_adjective(alert.total_seconds)} timer has "
                    f"{spoken_duration(alert.remaining())} left."
                )
            return response

        alerts = self.controller.scoped_timers(dev)
        if not alerts:
            response.async_set_speech("No timers or alarms are set.")
            return response

        timers = sum(1 for t in alerts if t.kind == "timer")
        alarms = sum(1 for t in alerts if t.kind == "alarm")

        if len(alerts) == 1:
            t = alerts[0]
            if t.kind == "alarm":
                response.async_set_speech(
                    f"You have one alarm, set for {t.label_time}, going off in "
                    f"{spoken_duration(t.remaining())}."
                )
            else:
                response.async_set_speech(
                    f"You have one timer, set for {spoken_duration(t.total_seconds)}, "
                    f"with {spoken_duration(t.remaining())} left."
                )
            return response

        parts = []
        for i, t in enumerate(alerts, 1):
            if t.kind == "alarm":
                parts.append(
                    f"number {i}, an alarm for {t.label_time}, in "
                    f"{spoken_duration(t.remaining())}"
                )
            else:
                parts.append(
                    f"number {i}, a {spoken_duration_adjective(t.total_seconds)} timer, "
                    f"{spoken_duration(t.remaining())} left"
                )
        response.async_set_speech(
            f"You have {count_phrase(timers, alarms)}. " + ". ".join(parts) + "."
        )
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
