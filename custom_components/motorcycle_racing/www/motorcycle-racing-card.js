/**
 * motorcycle-racing-card
 *
 * Lovelace card for the Motorcycle Racing integration. Finds its entities by
 * walking the device registry for the series' device (or an explicit
 * `entity`), so it keeps working even if entity_ids end up numbered
 * (sensor.motogp_2 etc.) rather than the friendly sensor.motogp_next_race
 * form — it matches on the stable unique_id suffix instead.
 *
 * Minimal config:
 *   type: custom:motorcycle-racing-card
 *   series: motogp
 */

const SERIES_META = {
  motogp: { name: "MotoGP", accent: "#D6001C" },
  moto2: { name: "Moto2", accent: "#0090D4" },
  moto3: { name: "Moto3", accent: "#00A651" },
  motoe: { name: "MotoE", accent: "#8DC63F" },
  worldsbk: { name: "WorldSBK", accent: "#E4002B" },
  bsb: { name: "British Superbikes", accent: "#00843D" },
};

// Longest-suffix-first so "next_session_time" is matched before "next_session".
const ENTITY_KEYS = [
  "next_session_time",
  "next_session",
  "next_race",
  "last_race",
  "rider_standings",
  "team_standings",
  "season_round",
  "favourite_rider",
  "race_weekend",
  "session_live",
  "race_day",
  "calendar",
].sort((a, b) => b.length - a.length);

const SESSION_ICONS = {
  practice: "mdi:timer-sand",
  qualifying: "mdi:stopwatch-outline",
  sprint: "mdi:flag-checkered",
  race: "mdi:flag-checkered",
  warmup: "mdi:weather-sunny",
  test: "mdi:wrench-outline",
  other: "mdi:motorbike",
};

function fmtTime(iso, locale) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString(locale || undefined, {
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function relative(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const ms = d.getTime() - Date.now();
  const abs = Math.abs(ms);
  const mins = Math.round(abs / 60000);
  const hrs = Math.round(abs / 3600000);
  const days = Math.round(abs / 86400000);
  let text;
  if (mins < 60) text = `${mins}m`;
  else if (hrs < 48) text = `${hrs}h`;
  else text = `${days}d`;
  return ms >= 0 ? `in ${text}` : `${text} ago`;
}

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[c]));
}

class MotorcycleRacingCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._entities = null;
    this._resolving = null;
    this._resolvedFor = null;
  }

  setConfig(config) {
    if (!config || (!config.series && !config.entity)) {
      throw new Error("motorcycle-racing-card: set either 'series' or 'entity'");
    }
    this._config = config;
    this._entities = null;
    this._resolvedFor = null;
  }

  getCardSize() {
    return 7;
  }

  static getStubConfig() {
    return { series: "motogp" };
  }

  set hass(hass) {
    this._hass = hass;
    const resolveKey = this._config.entity || this._config.series;
    if (this._resolvedFor !== resolveKey && !this._resolving) {
      this._resolving = this._resolve(hass).finally(() => {
        this._resolving = null;
      });
    }
    this._render();
  }

  async _resolve(hass) {
    const config = this._config;
    try {
      let deviceId = null;

      if (config.entity) {
        const entityRegistry = await hass.callWS({
          type: "config/entity_registry/list",
        });
        const entry = entityRegistry.find((e) => e.entity_id === config.entity);
        deviceId = entry ? entry.device_id : null;
      } else {
        const meta = SERIES_META[config.series];
        const wanted = (meta ? meta.name : config.series).toLowerCase();
        const devices = await hass.callWS({ type: "config/device_registry/list" });
        const match = devices.find((d) => {
          const isOurs = (d.identifiers || []).some(
            (pair) => pair[0] === "motorcycle_racing"
          );
          const name = (d.name_by_user || d.name || "").toLowerCase();
          return isOurs && name === wanted;
        });
        deviceId = match ? match.id : null;
      }

      if (!deviceId) {
        this._entities = null;
        this._resolvedFor = config.entity || config.series;
        this._error = `No device found for ${config.entity || config.series}`;
        this._render();
        return;
      }

      const entityRegistry = await hass.callWS({
        type: "config/entity_registry/list",
      });
      const forDevice = entityRegistry.filter((e) => e.device_id === deviceId);

      const map = {};
      for (const entry of forDevice) {
        const uid = entry.unique_id || "";
        const key = ENTITY_KEYS.find((k) => uid.endsWith(`_${k}`));
        if (key) map[key] = entry.entity_id;
      }
      this._entities = map;
      this._error = null;
      this._resolvedFor = config.entity || config.series;
      this._render();
    } catch (err) {
      this._error = `Could not read the entity registry: ${err.message || err}`;
      this._render();
    }
  }

  _state(key) {
    const entityId = this._entities && this._entities[key];
    if (!entityId || !this._hass) return null;
    return this._hass.states[entityId] || null;
  }

  _attr(key, attr) {
    const st = this._state(key);
    return st ? st.attributes[attr] : undefined;
  }

  _renderGantry(nextSession, nextSessionTimeState, sessionLiveOn) {
    const startIso = nextSessionTimeState ? nextSessionTimeState.state : null;
    let lit = 0;
    let label = "No session scheduled";
    if (sessionLiveOn) {
      lit = 5;
      label = "Session live";
    } else if (startIso) {
      const hoursUntil = (new Date(startIso).getTime() - Date.now()) / 3600000;
      if (hoursUntil <= 0) {
        lit = 5;
        label = "Lights out";
      } else if (hoursUntil <= 5) {
        lit = Math.max(0, Math.min(5, Math.round(5 - hoursUntil)));
        label = `${relative(startIso)} · ${nextSession ? nextSession.state : ""}`;
      } else {
        label = `${nextSession ? nextSession.state : "Next session"} ${relative(startIso)}`;
      }
    }
    const lamps = Array.from({ length: 5 }, (_, i) =>
      `<span class="lamp ${i < lit ? "lit" : ""}"></span>`
    ).join("");
    return `
      <div class="gantry">
        <div class="lamps">${lamps}</div>
        <div class="gantry-label">${esc(label)}</div>
      </div>`;
  }

  _renderCircuit(label, event, resultLine) {
    if (!event) {
      return `
        <div class="circuit-card empty">
          <div class="circuit-label">${esc(label)}</div>
          <ha-icon icon="mdi:image-off-outline"></ha-icon>
          <div class="circuit-empty-text">No round yet</div>
        </div>`;
    }
    const img = event.circuit_map || event.poster;
    const imgHtml = img
      ? `<img src="${esc(img)}" alt="${esc(event.circuit || "")}" loading="lazy" />`
      : `<div class="circuit-placeholder"><ha-icon icon="mdi:racing-helmet"></ha-icon></div>`;
    return `
      <div class="circuit-card">
        <div class="circuit-label">${esc(label)}</div>
        ${imgHtml}
        <div class="circuit-meta">
          <div class="circuit-name">${esc(event.short_name || event.name || "")}</div>
          <div class="circuit-place">${esc([event.circuit, event.country].filter(Boolean).join(" · "))}</div>
          ${resultLine ? `<div class="circuit-result">${esc(resultLine)}</div>` : ""}
        </div>
      </div>`;
  }

  _renderSessions(sessions) {
    if (!sessions || !sessions.length) return "";
    const nextStart = this._attr("next_session", "start");
    const rows = sessions
      .map((s) => {
        const icon = SESSION_ICONS[s.kind] || SESSION_ICONS.other;
        const isNext = s.start && s.start === nextStart;
        return `
          <div class="session-row ${isNext ? "next" : ""}">
            <ha-icon icon="${icon}"></ha-icon>
            <span class="session-name">${esc(s.name)}</span>
            <span class="session-time">${esc(fmtTime(s.start, this._config.date_locale))}</span>
          </div>`;
      })
      .join("");
    return `<div class="section"><div class="section-title">Weekend schedule</div><div class="sessions">${rows}</div></div>`;
  }

  _renderResultsTable(rows, limit) {
    if (!rows || !rows.length) return "";
    const shown = rows.slice(0, limit || 5);
    const body = shown
      .map(
        (r) => `
        <tr>
          <td class="pos">${esc(r.position ?? "")}</td>
          <td class="name">${esc(r.rider || r.name || "")}</td>
          <td class="team">${esc(r.team || r.constructor || "")}</td>
          <td class="num">${esc(r.gap || r.time || "")}</td>
          <td class="num">${r.points != null ? esc(r.points) : ""}</td>
        </tr>`
      )
      .join("");
    return `
      <table class="results">
        <thead><tr><th></th><th>Rider</th><th>Team</th><th>Gap</th><th>Pts</th></tr></thead>
        <tbody>${body}</tbody>
      </table>`;
  }

  _renderStandingsTable(rows, limit) {
    if (!rows || !rows.length) return "";
    const shown = rows.slice(0, limit || 5);
    const body = shown
      .map(
        (r) => `
        <tr>
          <td class="pos">${esc(r.position ?? "")}</td>
          <td class="name">${esc(r.name || "")}</td>
          <td class="team">${esc(r.team || "")}</td>
          <td class="num">${r.points != null ? esc(r.points) : ""}</td>
        </tr>`
      )
      .join("");
    return `
      <table class="results">
        <thead><tr><th></th><th>Name</th><th>Team</th><th>Pts</th></tr></thead>
        <tbody>${body}</tbody>
      </table>`;
  }

  _render() {
    if (!this.shadowRoot) return;
    const config = this._config || {};
    const meta = SERIES_META[config.series] || {};
    const accent = config.accent || meta.accent || "#FF6B00";
    const title = config.title || meta.name || config.series || "Racing";

    if (this._error) {
      this.shadowRoot.innerHTML = `
        <style>${this._css(accent)}</style>
        <ha-card><div class="card-content error">${esc(this._error)}</div></ha-card>`;
      return;
    }

    if (!this._entities) {
      this.shadowRoot.innerHTML = `
        <style>${this._css(accent)}</style>
        <ha-card><div class="card-content">Loading ${esc(title)}…</div></ha-card>`;
      return;
    }

    const nextRace = this._state("next_race");
    const lastRace = this._state("last_race");
    const nextSession = this._state("next_session");
    const nextSessionTime = this._state("next_session_time");
    const raceWeekend = this._state("race_weekend");
    const sessionLive = this._state("session_live");
    const riderStandings = this._state("rider_standings");
    const teamStandings = this._state("team_standings");

    const showGantry = config.show_gantry !== false;
    const showSessions = config.show_sessions !== false;
    const showResults = config.show_results !== false;
    const showStandings = config.show_standings !== false;
    const showCircuit = config.show_circuit !== false;

    const nextEvent = nextRace
      ? { ...nextRace.attributes, name: nextRace.state }
      : null;
    const lastEvent = lastRace
      ? { ...lastRace.attributes, name: lastRace.attributes.event }
      : null;

    const badges = [];
    if (raceWeekend && raceWeekend.state === "on") badges.push("Race weekend");
    if (sessionLive && sessionLive.state === "on") badges.push("LIVE");

    let html = `
      <ha-card>
        <div class="header">
          <div class="title-row">
            <span class="dot"></span>
            <span class="title">${esc(title)}</span>
            ${badges.map((b) => `<span class="badge ${b === "LIVE" ? "live" : ""}">${esc(b)}</span>`).join("")}
          </div>
        </div>
        <div class="card-content">`;

    if (showCircuit && (nextEvent || lastEvent)) {
      const resultLine = lastRace && lastRace.attributes.winner
        ? `Winner: ${lastRace.attributes.winner}`
        : undefined;
      html += `<div class="circuits">
        ${this._renderCircuit("Last round", lastEvent, resultLine)}
        ${this._renderCircuit("Next round", nextEvent, nextEvent ? relative(nextEvent.race_start || nextEvent.start) : undefined)}
      </div>`;
    }

    if (showGantry) {
      html += this._renderGantry(nextSession, nextSessionTime, sessionLive && sessionLive.state === "on");
    }

    if (showSessions && nextEvent && nextEvent.sessions) {
      html += this._renderSessions(nextEvent.sessions);
    }

    if (showResults && lastRace) {
      const rows = lastRace.attributes.classification || [];
      html += `<div class="section">
        <div class="section-title">Last race${lastEvent && lastEvent.name ? ` · ${esc(lastEvent.name)}` : ""}</div>
        ${this._renderResultsTable(rows, config.results_rows) || `<div class="empty-row">No classification yet</div>`}
      </div>`;
    }

    if (showStandings && riderStandings) {
      const rows = riderStandings.attributes.standings || [];
      html += `<div class="section">
        <div class="section-title">Championship</div>
        ${this._renderStandingsTable(rows, config.standings_rows) || `<div class="empty-row">No standings yet</div>`}
      </div>`;

      const teamRows = teamStandings ? teamStandings.attributes.standings || [] : [];
      if (teamRows.length) {
        html += `<div class="section">
          <div class="section-title">Teams</div>
          ${this._renderStandingsTable(teamRows, config.standings_rows)}
        </div>`;
      }
    }

    html += `</div></ha-card>`;
    this.shadowRoot.innerHTML = `<style>${this._css(accent)}</style>${html}`;
  }

  _css(accent) {
    return `
      :host { --accent: ${accent}; }
      ha-card { overflow: hidden; }
      .header {
        padding: 12px 16px 0 16px;
      }
      .title-row { display: flex; align-items: center; gap: 8px; }
      .dot {
        width: 10px; height: 10px; border-radius: 50%;
        background: var(--accent);
        box-shadow: 0 0 6px var(--accent);
        flex-shrink: 0;
      }
      .title { font-size: 1.15em; font-weight: 600; flex-grow: 1; }
      .badge {
        font-size: 0.7em; font-weight: 600; text-transform: uppercase;
        padding: 2px 8px; border-radius: 999px;
        background: color-mix(in srgb, var(--accent) 20%, transparent);
        color: var(--accent);
        letter-spacing: 0.04em;
      }
      .badge.live { background: #d6001c; color: white; animation: pulse 1.6s ease-in-out infinite; }
      @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.55; } }
      .card-content { padding: 12px 16px 16px 16px; }
      .error { color: var(--error-color, #db4437); }
      .circuits { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 14px; }
      .circuit-card {
        border-radius: 10px;
        overflow: hidden;
        background: var(--secondary-background-color, #f2f2f2);
        display: flex; flex-direction: column;
      }
      .circuit-card img { width: 100%; height: 96px; object-fit: cover; display: block; background: #fff; }
      .circuit-placeholder {
        height: 96px; display: flex; align-items: center; justify-content: center;
        color: var(--secondary-text-color);
      }
      .circuit-card.empty { align-items: center; justify-content: center; padding: 16px 8px; text-align: center; color: var(--secondary-text-color); gap: 4px; }
      .circuit-label { font-size: 0.68em; text-transform: uppercase; letter-spacing: 0.06em; color: var(--secondary-text-color); padding: 6px 8px 0 8px; }
      .circuit-meta { padding: 4px 8px 8px 8px; }
      .circuit-name { font-weight: 600; font-size: 0.9em; line-height: 1.2; }
      .circuit-place { font-size: 0.78em; color: var(--secondary-text-color); }
      .circuit-result { font-size: 0.78em; color: var(--accent); margin-top: 2px; font-weight: 600; }
      .circuit-empty-text { font-size: 0.8em; }
      .gantry { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
      .lamps { display: flex; gap: 5px; }
      .lamp {
        width: 16px; height: 16px; border-radius: 50%;
        background: var(--divider-color, #444);
        opacity: 0.35;
        box-shadow: inset 0 0 0 2px rgba(0,0,0,0.15);
      }
      .lamp.lit { background: var(--accent); opacity: 1; box-shadow: 0 0 8px var(--accent); }
      .gantry-label { font-size: 0.85em; color: var(--secondary-text-color); }
      .section { margin-top: 14px; }
      .section-title {
        font-size: 0.75em; text-transform: uppercase; letter-spacing: 0.06em;
        color: var(--secondary-text-color); margin-bottom: 6px; font-weight: 600;
        border-left: 3px solid var(--accent); padding-left: 6px;
      }
      .sessions { display: flex; flex-direction: column; gap: 2px; }
      .session-row {
        display: flex; align-items: center; gap: 8px;
        padding: 4px 6px; border-radius: 6px; font-size: 0.85em;
      }
      .session-row ha-icon { --mdc-icon-size: 16px; color: var(--secondary-text-color); }
      .session-row.next { background: color-mix(in srgb, var(--accent) 12%, transparent); font-weight: 600; }
      .session-name { flex-grow: 1; }
      .session-time { color: var(--secondary-text-color); font-variant-numeric: tabular-nums; }
      table.results { width: 100%; border-collapse: collapse; font-size: 0.85em; }
      table.results th {
        text-align: left; font-size: 0.72em; text-transform: uppercase;
        color: var(--secondary-text-color); font-weight: 600; padding: 2px 6px;
      }
      table.results td {
        padding: 4px 6px; border-top: 1px solid var(--divider-color, #eee);
        font-variant-numeric: tabular-nums;
      }
      table.results td.pos { color: var(--accent); font-weight: 700; width: 1.6em; }
      table.results td.num { text-align: right; white-space: nowrap; }
      .empty-row { font-size: 0.85em; color: var(--secondary-text-color); }
    `;
  }
}

customElements.define("motorcycle-racing-card", MotorcycleRacingCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "motorcycle-racing-card",
  name: "Motorcycle Racing Card",
  description:
    "Next round, last result, championship standings and a start-light countdown for a motorcycle racing series (MotoGP, Moto2, Moto3, MotoE, WorldSBK, BSB or custom).",
});

/**
 * motorcycle-racing-tv-card
 *
 * Aggregates "next session" across every configured series' device and
 * shows whichever is happening soonest, with the UK TV channel and the
 * viewer's own local time (derived from the browser, so it's correct for
 * whoever is looking at the dashboard).
 *
 * Minimal config:
 *   type: custom:motorcycle-racing-tv-card
 */

// All UK live coverage sits on TNT Sports as of the 2025/2026 seasons
// (Eurosport's UK output folded into TNT Sports' channels/streaming). Keyed
// by device name (lowercased) so it degrades gracefully to a sensible
// default if a series airs elsewhere in future.
const TV_CHANNEL = {
  motogp: "TNT Sports",
  moto2: "TNT Sports",
  moto3: "TNT Sports",
  motoe: "TNT Sports",
  worldsbk: "TNT Sports",
  "british superbikes": "TNT Sports",
};

class MotorcycleTVCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._sessions = null;
    this._resolving = null;
    this._error = null;
  }

  setConfig(config) {
    this._config = config || {};
  }

  getCardSize() {
    return 5;
  }

  static getStubConfig() {
    return {};
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._sessions && !this._resolving) {
      this._resolving = this._resolve(hass).finally(() => {
        this._resolving = null;
      });
    }
    this._render();
  }

  async _resolve(hass) {
    try {
      const devices = await hass.callWS({ type: "config/device_registry/list" });
      const ours = devices.filter((d) =>
        (d.identifiers || []).some((pair) => pair[0] === "motorcycle_racing")
      );
      const entityRegistry = await hass.callWS({
        type: "config/entity_registry/list",
      });

      const sessions = [];
      for (const device of ours) {
        const forDevice = entityRegistry.filter((e) => e.device_id === device.id);
        const timeEntry = forDevice.find((e) =>
          (e.unique_id || "").endsWith("_next_session_time")
        );
        if (!timeEntry) continue;
        const timeState = hass.states[timeEntry.entity_id];
        if (!timeState || !timeState.state) continue;
        const start = new Date(timeState.state);
        if (Number.isNaN(start.getTime())) continue;

        const nameEntry = forDevice.find((e) =>
          (e.unique_id || "").endsWith("_next_session")
        );
        const nameState = nameEntry ? hass.states[nameEntry.entity_id] : null;
        const seriesName = device.name_by_user || device.name || "";
        sessions.push({
          series: seriesName,
          session: nameState && nameState.state ? nameState.state : "Session",
          start,
          channel: TV_CHANNEL[seriesName.toLowerCase()] || "Check local listings",
        });
      }
      sessions.sort((a, b) => a.start - b.start);
      this._sessions = sessions;
      this._error = null;
    } catch (err) {
      this._error = `Could not read the entity registry: ${err.message || err}`;
    }
    this._render();
  }

  _render() {
    if (!this.shadowRoot) return;
    const title = this._config.title || "On TV (UK)";

    if (this._error) {
      this.shadowRoot.innerHTML = `
        <style>${this._css()}</style>
        <ha-card><div class="card-content error">${esc(this._error)}</div></ha-card>`;
      return;
    }

    if (!this._sessions) {
      this.shadowRoot.innerHTML = `
        <style>${this._css()}</style>
        <ha-card><div class="card-content">Loading ${esc(title)}…</div></ha-card>`;
      return;
    }

    // Keep anything that started less than 30 minutes ago so a session that
    // just went live doesn't disappear from "next up".
    const cutoff = Date.now() - 30 * 60000;
    const upcoming = this._sessions.filter((s) => s.start.getTime() >= cutoff);

    if (!upcoming.length) {
      this.shadowRoot.innerHTML = `
        <style>${this._css()}</style>
        <ha-card>
          <div class="header"><div class="title-row"><span class="title">${esc(title)}</span></div></div>
          <div class="card-content"><div class="empty-row">Nothing scheduled</div></div>
        </ha-card>`;
      return;
    }

    const [next, ...rest] = upcoming;
    const dateLocale = this._config.date_locale;
    const nextTimeStr = next.start.toLocaleString(dateLocale || undefined, {
      weekday: "long",
      hour: "2-digit",
      minute: "2-digit",
    });

    let html = `
      <ha-card>
        <div class="header">
          <div class="title-row">
            <span class="dot"></span>
            <span class="title">${esc(title)}</span>
          </div>
        </div>
        <div class="card-content">
          <div class="next-up">
            <div class="next-series">${esc(next.series)}</div>
            <div class="next-session">${esc(next.session)}</div>
            <div class="next-meta">
              <span class="next-time">${esc(nextTimeStr)} · ${esc(relative(next.start.toISOString()))}</span>
              <span class="next-channel">${esc(next.channel)}</span>
            </div>
          </div>`;

    if (rest.length) {
      const rows = rest
        .slice(0, 6)
        .map(
          (s) => `
        <div class="upcoming-row">
          <span class="upcoming-series">${esc(s.series)}</span>
          <span class="upcoming-session">${esc(s.session)}</span>
          <span class="upcoming-time">${esc(fmtTime(s.start.toISOString(), dateLocale))}</span>
          <span class="upcoming-channel">${esc(s.channel)}</span>
        </div>`
        )
        .join("");
      html += `
          <div class="section">
            <div class="section-title">Also coming up</div>
            <div class="upcoming-list">${rows}</div>
          </div>`;
    }

    html += `</div></ha-card>`;
    this.shadowRoot.innerHTML = `<style>${this._css()}</style>${html}`;
  }

  _css() {
    return `
      ha-card { overflow: hidden; }
      .header { padding: 12px 16px 0 16px; }
      .title-row { display: flex; align-items: center; gap: 8px; }
      .dot {
        width: 10px; height: 10px; border-radius: 50%;
        background: #D6001C; box-shadow: 0 0 6px #D6001C; flex-shrink: 0;
      }
      .title { font-size: 1.15em; font-weight: 600; }
      .card-content { padding: 12px 16px 16px 16px; }
      .error { color: var(--error-color, #db4437); }
      .next-up {
        background: var(--secondary-background-color, #f2f2f2);
        border-radius: 10px; padding: 12px;
      }
      .next-series {
        font-size: 0.75em; text-transform: uppercase; letter-spacing: 0.06em;
        color: var(--secondary-text-color);
      }
      .next-session { font-size: 1.1em; font-weight: 700; margin-top: 2px; }
      .next-meta {
        display: flex; justify-content: space-between; align-items: center;
        margin-top: 8px; gap: 8px; flex-wrap: wrap;
      }
      .next-time { font-size: 0.9em; color: var(--secondary-text-color); }
      .next-channel {
        font-size: 0.85em; font-weight: 600; padding: 2px 10px; border-radius: 999px;
        background: color-mix(in srgb, #D6001C 18%, transparent); color: #D6001C;
      }
      .section { margin-top: 14px; }
      .section-title {
        font-size: 0.75em; text-transform: uppercase; letter-spacing: 0.06em;
        color: var(--secondary-text-color); margin-bottom: 6px; font-weight: 600;
      }
      .upcoming-list { display: flex; flex-direction: column; gap: 2px; }
      .upcoming-row {
        display: flex; align-items: center; gap: 8px; font-size: 0.85em;
        padding: 4px 0; border-top: 1px solid var(--divider-color, #eee);
      }
      .upcoming-series { font-weight: 600; flex: 0 0 auto; min-width: 70px; }
      .upcoming-session { color: var(--secondary-text-color); flex-grow: 1; }
      .upcoming-time { color: var(--secondary-text-color); white-space: nowrap; }
      .upcoming-channel { font-size: 0.8em; color: var(--secondary-text-color); white-space: nowrap; }
      .empty-row { font-size: 0.85em; color: var(--secondary-text-color); }
    `;
  }
}

customElements.define("motorcycle-racing-tv-card", MotorcycleTVCard);
window.customCards.push({
  type: "motorcycle-racing-tv-card",
  name: "Motorcycle Racing – On TV",
  description:
    "Shows the next motorcycle racing session on UK TV - series, session, local time and channel - across every configured series.",
});
