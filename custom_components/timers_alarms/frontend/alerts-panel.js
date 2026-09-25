/*
 * Alerts — sidebar panel for the Voice Timers & Alarms integration.
 *
 * Self-contained vanilla web component (no build step, no HACS). Renders the
 * active timers/alarms exposed by sensor.<...> (found via its `ta_marker`
 * attribute) and lets you see WHERE each one will ring and cancel it. Countdowns
 * tick locally from each item's absolute `fires_at`, so they stay live without
 * server round-trips. Reminders get their own section later (separate project).
 */

const ICONS = { timer: "⏲", alarm: "⏰" };

function fmtRemaining(sec) {
  sec = Math.max(0, Math.round(sec));
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  const pad = (n) => String(n).padStart(2, "0");
  return h ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
}

class TaAlertsPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._lastKey = null;
    this._items = [];
  }

  set hass(hass) {
    this._hass = hass;
    const sensor = this._findSensor(hass);
    this._items = (sensor && sensor.attributes.items) || [];
    // Only rebuild the DOM when the SET of alerts changes; otherwise just let
    // the 1 Hz ticker refresh the countdowns (keeps cancel buttons clickable).
    const key = this._items.map((i) => i.id).join(",");
    if (key !== this._lastKey) {
      this._lastKey = key;
      this._render();
    }
  }

  connectedCallback() {
    this._render();
    this._ticker = setInterval(() => this._tick(), 1000);
  }

  disconnectedCallback() {
    clearInterval(this._ticker);
  }

  _findSensor(hass) {
    if (!hass) return null;
    for (const id of Object.keys(hass.states)) {
      if (id.startsWith("sensor.") && hass.states[id].attributes.ta_marker) {
        return hass.states[id];
      }
    }
    return null;
  }

  _tick() {
    if (!this.shadowRoot) return;
    const now = Date.now() / 1000;
    for (const el of this.shadowRoot.querySelectorAll("[data-fires]")) {
      el.textContent = fmtRemaining(parseFloat(el.dataset.fires) - now);
    }
  }

  _cancel(id) {
    this._hass.callService("timers_alarms", "cancel", { id });
  }

  _cancelAll() {
    this._hass.callService("timers_alarms", "cancel_all", {});
  }

  _render() {
    const now = Date.now() / 1000;
    const rows = this._items
      .map((i) => {
        const alerting = i.status === "alerting";
        const right = alerting
          ? `<div class="remaining alerting">🔔 Alerting</div>`
          : `<div class="remaining" data-fires="${i.fires_at}">${fmtRemaining(
              i.fires_at - now
            )}</div>`;
        return `
        <div class="row${alerting ? " is-alerting" : ""}">
          <div class="icon">${alerting ? "🔔" : ICONS[i.kind] || "⏲"}</div>
          <div class="meta">
            <div class="label">${i.label}</div>
            <div class="target">rings on ${i.target || "?"}</div>
          </div>
          ${right}
          <button class="cancel" data-id="${i.id}" title="${
          alerting ? "Dismiss" : "Cancel"
        }">✕</button>
        </div>`;
      })
      .join("");

    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; padding: 16px; box-sizing: border-box;
                color: var(--primary-text-color); }
        .wrap { max-width: 720px; margin: 0 auto; }
        h2 { font-size: 15px; font-weight: 500; text-transform: uppercase;
             letter-spacing: .05em; color: var(--secondary-text-color);
             margin: 24px 0 8px; }
        .card { background: var(--card-background-color, #fff);
                border-radius: var(--ha-card-border-radius, 12px);
                box-shadow: var(--ha-card-box-shadow, 0 2px 4px rgba(0,0,0,.1));
                padding: 8px; }
        .row { display: flex; align-items: center; gap: 12px; padding: 10px 8px;
               border-bottom: 1px solid var(--divider-color, #e0e0e0); }
        .row:last-child { border-bottom: none; }
        .icon { font-size: 24px; width: 28px; text-align: center; }
        .meta { flex: 1 1 auto; min-width: 0; }
        .label { font-weight: 500; }
        .target { font-size: 12px; color: var(--secondary-text-color); }
        .remaining { font-variant-numeric: tabular-nums; font-size: 20px;
                     font-weight: 500; color: var(--primary-color); }
        .remaining.alerting { color: var(--error-color, #db4437); font-size: 16px;
                              animation: ta-pulse 1s ease-in-out infinite; }
        .row.is-alerting { background: rgba(219,68,55,.08); border-radius: 8px; }
        @keyframes ta-pulse { 0%,100% { opacity: 1; } 50% { opacity: .35; } }
        button.cancel { border: none; background: transparent; cursor: pointer;
                        font-size: 18px; color: var(--secondary-text-color);
                        border-radius: 50%; width: 32px; height: 32px; }
        button.cancel:hover { background: var(--secondary-background-color);
                              color: var(--error-color, #db4437); }
        .empty { padding: 20px 8px; color: var(--secondary-text-color); }
        .bar { display: flex; justify-content: flex-end; margin-top: 8px; }
        .bar button { border: none; background: var(--secondary-background-color);
                      color: var(--primary-text-color); border-radius: 8px;
                      padding: 8px 14px; cursor: pointer; }
        .soon { color: var(--secondary-text-color); font-style: italic; }
      </style>
      <div class="wrap">
        <h2>Timers &amp; Alarms</h2>
        <div class="card">
          ${rows || '<div class="empty">No active timers or alarms.</div>'}
        </div>
        ${
          this._items.length
            ? '<div class="bar"><button id="cancelAll">Cancel all</button></div>'
            : ""
        }

        <h2>Reminders</h2>
        <div class="card">
          <div class="empty soon">Coming soon.</div>
        </div>
      </div>`;

    for (const b of this.shadowRoot.querySelectorAll("button.cancel")) {
      b.addEventListener("click", () => this._cancel(b.dataset.id));
    }
    const all = this.shadowRoot.getElementById("cancelAll");
    if (all) all.addEventListener("click", () => this._cancelAll());
  }
}

customElements.define("ta-alerts-panel", TaAlertsPanel);
