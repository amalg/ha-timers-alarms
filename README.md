# Voice Timers & Alarms (Home Assistant)

A Home Assistant **custom integration** for voice-driven **timers** and **alarms**
that ring on the **device you spoke to** — any Assist voice satellite (Home
Assistant Voice PE, ESPHome/emOS satellites, etc.) — with per‑device/fleet
**selectable tones**.

Built to work with the **classic Assist pipeline** (hassil sentence matching), so
it needs **no LLM conversation agent**. Device targeting, multiple named timers &
alarms, queries, cancel, and snooze all work under the default `conversation.home_assistant`
agent.

## Why this exists

- HA's built-in timers are limited (single unnamed timer + status + cancel-all in
  practice); **named/multiple timers, rich queries, and time-of-day alarms** are
  shaky-to-absent, and there's no central tone control.
- The excellent [`Pewidot/ha_voice_alarms`](https://github.com/Pewidot/ha_voice_alarms)
  proves the feature set, but it is **LLM-tool-based** (only fires under an LLM
  agent) and rings on **one configured `media_player`**, not the device you spoke
  to. We reuse its ideas (managers, storage, scheduling, config UI, sounds) but
  build a **classic-intent, device-exact** front end.

## Design (verified by spikes 2026-09-24)

- **Front end:** custom **IntentHandlers** (Python) + shipped `custom_sentences`.
  A Python intent handler receives `intent_obj.device_id` natively → **device-exact**
  with no template gymnastics. Custom sentences take precedence over the built-in
  timer intents (spiked: they intercept "set a timer for 5 minutes" cleanly).
- **Ring engine:** on fire, loop the selected tone to the **source device's**
  `media_player` (`media_player.play_media`), ducking/flushing on dismissal.
  Spiked working on **both** an emOS Dot and a stock Nabu Casa Voice PE — voice
  "stop" is heard *over* the tone and dismisses it. Order is **flush → then speak
  confirmation**.
- **State:** timers + alarms persisted via HA's `Store` helper (survives restart).
- **Alarms = time-of-day** (optionally repeating), scheduled centrally; they ring
  through the same engine and get their **own** selectable tone (distinct from
  timers, like real Alexa).
- **Tones:** bundled tone library + a **selector** (default tone + per‑device
  override, fleet default). Default ships a CC-licensed tone; non-CC tones stay
  opt-in (resale hygiene).

## Voice surface (target)

Timers: "set a timer for 10 minutes" · "set a 5 minute pizza timer" · "how much
time is left [on the pizza timer]" · "what timers are running" · "cancel the pizza
timer" · "cancel all timers".
Alarms: "set an alarm for 7am" · "wake me up at 6:30 on weekdays" · "what alarms
are set" · "cancel my 7am alarm" · "snooze".
Ringing: "stop" · "dismiss" · "snooze".

## Roadmap

- [x] Repo + scaffold
- [ ] **M1 — Timer MVP:** StartTimer/CancelTimer/TimerStatus/StopRinging intents,
      device-exact ring + dismissal (flush→confirm), Store persistence.
- [ ] **M2 — Multiple/named timers** + list/query.
- [ ] **M3 — Alarms** (time-of-day, repeating) + list/cancel/snooze.
- [ ] **M4 — Tones:** bundle library, per‑device/fleet selector (config + entities),
      two tones (timer vs alarm).
- [ ] **M5 — Polish:** offline-at-fire handling, quiet hours/DND, snooze UX, tests.

## Install (vendored, no HACS required)

Copy `custom_components/timers_alarms/` into your HA `config/custom_components/`
and the `custom_sentences/` into `config/custom_sentences/`, restart, then add the
**Voice Timers & Alarms** integration. (Ships `hacs.json` for HACS users too, but
this project is developed vendored.)

## Credits

Feature set and several internal patterns adapted from
[`Pewidot/ha_voice_alarms`](https://github.com/Pewidot/ha_voice_alarms) (see
in-code attributions). Front end and device-exact ring are original.
