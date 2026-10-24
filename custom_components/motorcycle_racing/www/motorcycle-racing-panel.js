/* Motorcycle Racing - sidebar dashboard panel (v1)
 * Overview / Live / Fixtures / Results / Tables / Past champions.
 * Data comes from the integration's websocket API (motorcycle_racing/*).
 * Background photo: CC0 / public domain, Wikimedia Commons (see footer).
 */
const PANEL_REPO = "https://github.com/Manzo76/ha-motorcycle-racing-2";
const BG_FILE =
  "Motor-Sport-Museum am Hockenheimring, unidentified motorcycle, pic-005.JPG";
const BG_URL =
  "https://commons.wikimedia.org/wiki/Special:FilePath/" +
  encodeURIComponent(BG_FILE) +
  "?width=1920";
const BG_PAGE =
  "https://commons.wikimedia.org/wiki/File:" +
  encodeURIComponent(BG_FILE.replace(/ /g, "_"));

const TABS = [
  ["overview", "Overview"],
  ["live", "Live"],
  ["fixtures", "Fixtures"],
  ["results", "Results"],
  ["tables", "Tables"],
  ["history", "Past champions"],
];

const esc = (v) =>
  String(v ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]
  );

function store(key, value) {
  try {
    if (value === undefined) return window.localStorage.getItem(key);
    window.localStorage.setItem(key, value);
  } catch (_) {
    return null;
  }
  return null;
}

class MotorcycleRacingPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._data = null;
    this._error = null;
    this._cls = store("mr_class");
    this._tab = store("mr_tab") || "overview";
    this._tableKind = "riders";
    this._eventId = null;
    this._sessionIdx = null;
    this._results = {}; // `${series}:${event}` -> payload
    this._live = null;
    this._timers = [];
    this._loading = false;
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this._start();
  }
  set narrow(v) {
    this._narrow = v;
  }
  set panel(v) {
    this._panel = v;
  }

  connectedCallback() {
    this._render();
  }
  disconnectedCallback() {
    this._timers.forEach(clearInterval);
    this._timers = [];
  }

  // ---- data ---------------------------------------------------------------

  _start() {
    this._refresh();
    this._timers.push(setInterval(() => this._refresh(), 60000));
    this._timers.push(
      setInterval(() => {
        if (this._tab === "live") this._loadLive();
      }, 30000)
    );
  }

  async _refresh() {
    try {
      const res = await this._hass.callWS({ type: "motorcycle_racing/overview" });
      this._data = res.series || [];
      this._error = null;
      if (!this._series() && this._data.length) this._cls = this._data[0].key;
    } catch (err) {
      this._error = (err && err.message) || "Could not load racing data";
    }
    this._render();
    if (this._tab === "live") this._loadLive();
    if (this._tab === "results") this._loadResults();
  }

  async _loadLive() {
    const s = this._series();
    if (!s) return;
    try {
      this._live = {
        series: s.key,
        ...(await this._hass.callWS({ type: "motorcycle_racing/live", series: s.key })),
      };
    } catch (_) {
      this._live = { series: s.key, sessions: [], event: null, live: null };
    }
    this._render();
  }

  async _loadResults() {
    const s = this._series();
    if (!s) return;
    const id = this._eventId || this._defaultEvent(s);
    if (!id) return;
    const key = `${s.key}:${id}`;
    if (this._results[key] && this._results[key].done) return;
    this._results[key] = { done: false, sessions: [] };
    this._render();
    try {
      const res = await this._hass.callWS({
        type: "motorcycle_racing/event_results",
        series: s.key,
        event_id: id,
      });
      this._results[key] = { done: true, sessions: res.sessions || [] };
    } catch (_) {
      this._results[key] = { done: true, sessions: [], error: true };
    }
    this._render();
  }

  _series() {
    return (this._data || []).find((s) => s.key === this._cls) || null;
  }

  _defaultEvent(s) {
    const finished = (s.calendar || []).filter((e) => e.finished);
    return (finished[finished.length - 1] || s.last_event || {}).id || null;
  }

  // ---- time ---------------------------------------------------------------

  _zone() {
    const h = this._hass || {};
    const loc = h.locale || {};
    if (loc.time_zone === "server") return h.config && h.config.time_zone;
    return undefined; // browser local
  }
  _lang() {
    return (this._hass && this._hass.locale && this._hass.locale.language) || undefined;
  }
  _fmt(iso, opts) {
    if (!iso) return "";
    const d = new Date(iso);
    if (isNaN(d)) return "";
    try {
      return new Intl.DateTimeFormat(this._lang(), { timeZone: this._zone(), ...opts }).format(d);
    } catch (_) {
      return new Intl.DateTimeFormat(undefined, opts).format(d);
    }
  }
  _day(iso) {
    return this._fmt(iso, { weekday: "short", day: "numeric", month: "short" });
  }
  _date(iso) {
    return this._fmt(iso, { day: "numeric", month: "short", year: "numeric" });
  }
  _time(iso) {
    return this._fmt(iso, { hour: "2-digit", minute: "2-digit", timeZoneName: "short" });
  }
  _range(e) {
    if (!e || !e.start) return "";
    const a = this._fmt(e.start, { day: "numeric", month: "short" });
    const b = e.end ? this._fmt(e.end, { day: "numeric", month: "short" }) : a;
    return a === b ? a : `${a} - ${b}`;
  }

  // ---- views --------------------------------------------------------------

  _table(rows, cols) {
    if (!rows || !rows.length) return `<p class="muted">Nothing to show yet.</p>`;
    const head = cols.map((c) => `<th class="${c.cls || ""}">${esc(c.h)}</th>`).join("");
    const body = rows
      .map(
        (r) =>
          `<tr>${cols
            .map((c) => `<td class="${c.cls || ""}">${c.f(r)}</td>`)
            .join("")}</tr>`
      )
      .join("");
    return `<div class="scroll"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
  }

  _podium(rows) {
    const top = (rows || []).slice(0, 3);
    if (top.length < 3) return "";
    const order = [top[1], top[0], top[2]];
    const cls = ["p2", "p1", "p3"];
    return `<div class="podium">${order
      .map(
        (r, i) =>
          `<div class="pod ${cls[i]}"><div class="step">${esc(r.position)}</div><b>${esc(
            r.rider
          )}</b><span>${esc(r.team || "")}</span></div>`
      )
      .join("")}</div>`;
  }

  _resultCols() {
    return [
      { h: "Pos", cls: "n", f: (r) => esc(r.position ?? "-") },
      { h: "Rider", f: (r) => `<b>${esc(r.rider)}</b>${r.number ? ` <i>#${esc(r.number)}</i>` : ""}` },
      { h: "Team", cls: "hide-narrow", f: (r) => esc(r.team || "") },
      { h: "Time / gap", cls: "n", f: (r) => esc(r.position === 1 ? r.time || "" : r.gap || r.time || r.status || "") },
    ];
  }

  _standCols() {
    return [
      { h: "Pos", cls: "n", f: (r) => esc(r.position ?? "-") },
      { h: "Name", f: (r) => `<b>${esc(r.name)}</b>` },
      { h: "Team", cls: "hide-narrow", f: (r) => esc(r.team || "") },
      { h: "Pts", cls: "n", f: (r) => esc(r.points ?? "") },
    ];
  }

  _viewOverview(s) {
    let hero;
    if (s.live) {
      hero = `<div class="status live"><span class="dot"></span>${esc(s.live.name)} is live now</div>`;
    } else if (s.season_over) {
      const c = s.champion;
      hero = `<div class="status done">${esc(s.season)} season complete${
        c ? ` &middot; Champion <b>${esc(c.name)}</b>` : ""
      }</div>`;
    } else if (s.next_event) {
      const ns = s.next_session;
      hero = `<div class="status">Next: <b>${esc(s.next_event.name)}</b> &middot; ${esc(
        this._range(s.next_event)
      )}${ns ? ` &middot; ${esc(ns.name)} ${esc(this._day(ns.start))} ${esc(this._time(ns.start))}` : ""}</div>`;
    } else {
      hero = `<div class="status">No upcoming rounds</div>`;
    }
    const last = s.last_event;
    const nextSeason = s.next_season_event;
    return `
      ${hero}
      <div class="grid">
        <section class="card">
          <h3>${last ? `Last race: ${esc(last.name)}` : "Last race"}</h3>
          ${last ? `<p class="muted">${esc(last.circuit || "")} &middot; ${esc(this._date(last.end || last.start))}</p>` : ""}
          ${this._podium(s.last_results)}
          ${this._table((s.last_results || []).slice(0, 10), this._resultCols())}
        </section>
        <section class="card">
          <h3>${esc(s.name)} championship ${esc(s.season || "")}</h3>
          ${this._table((s.riders || []).slice(0, 10), this._standCols())}
        </section>
        <section class="card">
          <h3>${s.season_over ? "Next season" : "Next round"}</h3>
          ${(() => {
            const e = s.season_over ? nextSeason : s.next_event;
            if (!e) return `<p class="muted">Not announced yet.</p>`;
            return `<p><b>${esc(e.name)}</b></p><p class="muted">${esc(e.circuit || "")}${
              e.country ? ` &middot; ${esc(e.country)}` : ""
            }</p><p>${esc(this._date(e.start))}</p>`;
          })()}
        </section>
      </div>`;
  }

  _viewLive(s) {
    const live = this._live && this._live.series === s.key ? this._live : null;
    if (!live) return `<p class="muted">Loading live data...</p>`;
    if (!live.event) return `<p class="muted">No race weekend to show.</p>`;
    const sessions = (live.sessions || []).filter((x) => (x.results || []).length);
    const head = live.live
      ? `<div class="status live"><span class="dot"></span>${esc(live.live.name)} is live &middot; ${esc(
          live.event.name
        )}</div>`
      : `<div class="status">${esc(live.event.name)} &middot; latest sessions</div>`;
    if (!sessions.length) {
      return `${head}<p class="muted">Timing will appear here once a session has started. Refreshes every 30 seconds.</p>`;
    }
    const idx = this._sessionIdx != null && this._sessionIdx < sessions.length ? this._sessionIdx : sessions.length - 1;
    const cur = sessions[idx];
    return `${head}
      <div class="chips small">${sessions
        .map((x, i) => `<button data-act="session" data-i="${i}" class="${i === idx ? "on" : ""}">${esc(x.name)}</button>`)
        .join("")}</div>
      <section class="card">${this._table(cur.results, this._resultCols())}</section>`;
  }

  _viewFixtures(s) {
    const cal = s.calendar || [];
    if (!cal.length) return `<p class="muted">No calendar available.</p>`;
    const nextId = s.next_event && s.next_event.id;
    const lastId = s.last_event && s.last_event.id;
    return `<section class="card"><div class="fixtures">${cal
      .map((e) => {
        const tag =
          e.id === nextId ? `<em class="tag next">Next</em>` : e.id === lastId ? `<em class="tag last">Last</em>` : e.finished ? `<em class="tag">Done</em>` : "";
        return `<button class="fx ${e.finished ? "done" : ""} ${e.id === nextId ? "next" : ""}" data-act="event" data-id="${esc(e.id)}">
          <span class="rd">${esc(e.round ?? "")}</span>
          <span class="nm"><b>${esc(e.name)}</b><small>${esc(e.circuit || "")}${e.country ? ` &middot; ${esc(e.country)}` : ""}</small></span>
          <span class="dt">${esc(this._range(e))}</span>${tag}</button>`;
      })
      .join("")}</div></section>`;
  }

  _viewResults(s) {
    const finished = (s.calendar || []).filter((e) => e.finished || e.id === (s.last_event && s.last_event.id));
    if (!finished.length) return `<p class="muted">No results yet this season.</p>`;
    const id = this._eventId || this._defaultEvent(s);
    const opts = finished
      .slice()
      .reverse()
      .map((e) => `<option value="${esc(e.id)}" ${e.id === id ? "selected" : ""}>${esc(e.round ? `R${e.round} ` : "")}${esc(e.name)}</option>`)
      .join("");
    const res = this._results[`${s.key}:${id}`];
    let body = `<p class="muted">Loading...</p>`;
    if (res && res.done) {
      const sessions = (res.sessions || []).filter((x) => (x.results || []).length);
      if (!sessions.length) {
        body = `<p class="muted">No classification published for this weekend.</p>`;
      } else {
        const race = sessions.map((x, i) => [x, i]).filter(([x]) => x.kind === "race").pop();
        const idx = this._sessionIdx != null && this._sessionIdx < sessions.length ? this._sessionIdx : race ? race[1] : sessions.length - 1;
        body = `<div class="chips small">${sessions
          .map((x, i) => `<button data-act="session" data-i="${i}" class="${i === idx ? "on" : ""}">${esc(x.name)}</button>`)
          .join("")}</div>${this._table(sessions[idx].results, this._resultCols())}`;
      }
    }
    return `<label class="sel">Race weekend <select data-act="pick-event">${opts}</select></label>
      <section class="card">${body}</section>`;
  }

  _viewTables(s) {
    const kind = this._tableKind;
    const rows = kind === "teams" ? s.teams : s.riders;
    const cols =
      kind === "teams"
        ? [
            { h: "Pos", cls: "n", f: (r) => esc(r.position ?? "-") },
            { h: "Team", f: (r) => `<b>${esc(r.name)}</b>` },
            { h: "Pts", cls: "n", f: (r) => esc(r.points ?? "") },
          ]
        : this._standCols();
    return `<div class="chips small">
        <button data-act="tkind" data-k="riders" class="${kind === "riders" ? "on" : ""}">Riders</button>
        <button data-act="tkind" data-k="teams" class="${kind === "teams" ? "on" : ""}">Teams</button></div>
      <section class="card"><h3>${esc(s.name)} ${esc(s.season || "")}${s.season_over ? " - final" : ""}</h3>${this._table(rows, cols)}</section>`;
  }

  _viewHistory(s) {
    const hasTeamTitle = (s.champions || []).some((c) => c.team_champion);
    const cols = [
      { h: "Season", cls: "n", f: (r) => esc(r.season) },
      { h: "Champion", f: (r) => `<b>${esc(r.rider)}</b>` },
      { h: "Team", cls: "hide-narrow", f: (r) => esc(r.team || "") },
    ];
    if (hasTeamTitle) cols.push({ h: "Team title", cls: "hide-narrow", f: (r) => esc(r.team_champion || "") });
    const note = (s.champions || []).length
      ? ""
      : `<p class="muted">History is still loading - it fills in over a few minutes after install.</p>`;
    return `<section class="card"><h3>${esc(s.name)} past champions</h3>${note}${this._table(s.champions, cols)}</section>`;
  }

  // ---- shell --------------------------------------------------------------

  _share() {
    const text = "Motorcycle Racing for Home Assistant - live results, fixtures and tables";
    if (navigator.share) {
      navigator.share({ title: "Motorcycle Racing", text, url: PANEL_REPO }).catch(() => {});
    } else {
      window.open(
        `mailto:?subject=${encodeURIComponent("Motorcycle Racing for Home Assistant")}&body=${encodeURIComponent(text + "\n" + PANEL_REPO)}`
      );
    }
  }

  _render() {
    const root = this.shadowRoot;
    if (!root) return;
    const series = this._data || [];
    const s = this._series();
    const accent = (s && s.accent) || "#e4002b";
    let view;
    if (this._error) view = `<p class="muted err">${esc(this._error)}</p>`;
    else if (!this._data) view = `<p class="muted">Loading...</p>`;
    else if (!series.length) view = `<p class="muted">No racing classes are set up yet. Add one under Settings &rarr; Devices &amp; services.</p>`;
    else if (!s.ready) view = `<p class="muted">${esc(s.name)} is still loading its first data.</p>`;
    else {
      const fn = {
        overview: "_viewOverview",
        live: "_viewLive",
        fixtures: "_viewFixtures",
        results: "_viewResults",
        tables: "_viewTables",
        history: "_viewHistory",
      }[this._tab];
      view = this[fn](s);
    }
    root.innerHTML = `
      <style>
        :host { display:block; min-height:100vh; color:#f2f2f5; font-family: var(--paper-font-body1_-_font-family, Roboto, system-ui, sans-serif); --accent:${esc(accent)}; }
        .bg { position:fixed; inset:0; z-index:0; background:#0b0b10 url("${BG_URL}") center/cover no-repeat; }
        .bg::after { content:""; position:absolute; inset:0; background:linear-gradient(180deg, rgba(8,8,14,.78), rgba(8,8,14,.93)); }
        .wrap { position:relative; z-index:1; max-width:1100px; margin:0 auto; padding:16px 16px 40px; }
        header { display:flex; align-items:center; gap:12px; flex-wrap:wrap; margin-bottom:12px; }
        header h1 { margin:0; font-size:1.5rem; letter-spacing:.02em; flex:1; }
        header h1 span { color:var(--accent); }
        .menu { background:none; border:0; color:inherit; font-size:1.5rem; cursor:pointer; display:${this._narrow ? "block" : "none"}; }
        .chips { display:flex; gap:8px; flex-wrap:wrap; margin:8px 0 12px; }
        .chips button, .tabs button { background:rgba(255,255,255,.08); color:inherit; border:1px solid rgba(255,255,255,.14); border-radius:999px; padding:7px 14px; font:inherit; cursor:pointer; backdrop-filter:blur(6px); }
        .chips button.on { background:var(--accent); border-color:var(--accent); color:#fff; font-weight:600; }
        .chips.small button { padding:5px 12px; font-size:.85rem; }
        .tabs { display:flex; gap:6px; overflow-x:auto; margin-bottom:14px; border-bottom:1px solid rgba(255,255,255,.12); padding-bottom:10px; }
        .tabs button { border-radius:8px; white-space:nowrap; }
        .tabs button.on { background:rgba(255,255,255,.18); border-color:var(--accent); box-shadow:inset 0 -3px 0 var(--accent); font-weight:600; }
        .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); gap:14px; }
        .card { background:rgba(18,18,26,.72); border:1px solid rgba(255,255,255,.1); border-radius:14px; padding:14px 16px; backdrop-filter:blur(10px); margin-bottom:14px; }
        .card h3 { margin:0 0 6px; font-size:1.05rem; }
        .status { background:rgba(18,18,26,.72); border-left:4px solid var(--accent); padding:12px 16px; border-radius:10px; margin-bottom:14px; backdrop-filter:blur(10px); }
        .status.live { border-color:#2ecc71; } .status.done { border-color:#f1c40f; }
        .dot { display:inline-block; width:10px; height:10px; border-radius:50%; background:#2ecc71; margin-right:8px; animation:pulse 1.2s infinite; }
        @keyframes pulse { 50% { opacity:.25; } }
        .muted { opacity:.7; } .err { color:#ff8a80; opacity:1; }
        .scroll { overflow-x:auto; }
        table { width:100%; border-collapse:collapse; font-size:.92rem; }
        th { text-align:left; font-weight:600; opacity:.7; font-size:.78rem; text-transform:uppercase; letter-spacing:.05em; padding:6px 8px; }
        td { padding:7px 8px; border-top:1px solid rgba(255,255,255,.07); }
        .n { text-align:right; white-space:nowrap; } td i { opacity:.55; font-style:normal; }
        .podium { display:flex; gap:8px; align-items:flex-end; justify-content:center; margin:10px 0 12px; }
        .pod { flex:1; max-width:170px; text-align:center; padding:8px 6px; border-radius:10px 10px 0 0; background:rgba(255,255,255,.07); }
        .pod b, .pod span { display:block; font-size:.85rem; } .pod span { opacity:.65; font-size:.75rem; }
        .pod .step { font-size:1.4rem; font-weight:800; }
        .pod.p1 { background:linear-gradient(#d4af3733,#d4af3711); padding-top:22px; } .pod.p1 .step { color:#f1c40f; }
        .pod.p2 .step { color:#c0c6cc; } .pod.p3 { padding-top:2px; } .pod.p3 .step { color:#cd7f32; }
        .fixtures { display:flex; flex-direction:column; gap:6px; }
        .fx { display:flex; align-items:center; gap:12px; background:rgba(255,255,255,.05); border:1px solid transparent; color:inherit; border-radius:10px; padding:10px 12px; font:inherit; text-align:left; cursor:pointer; }
        .fx:hover { border-color:var(--accent); } .fx.next { border-color:var(--accent); background:rgba(255,255,255,.1); } .fx.done { opacity:.8; }
        .fx .rd { width:28px; font-weight:800; opacity:.6; } .fx .nm { flex:1; } .fx small { display:block; opacity:.65; } .fx .dt { opacity:.8; white-space:nowrap; }
        .tag { font-style:normal; font-size:.7rem; padding:2px 8px; border-radius:999px; background:rgba(255,255,255,.14); } .tag.next { background:var(--accent); }
        label.sel { display:block; margin-bottom:10px; } select { margin-left:8px; background:rgba(18,18,26,.85); color:inherit; border:1px solid rgba(255,255,255,.2); border-radius:8px; padding:7px 10px; font:inherit; max-width:100%; }
        footer { margin-top:24px; display:flex; flex-wrap:wrap; gap:10px; align-items:center; font-size:.8rem; opacity:.9; }
        footer a, footer button { color:inherit; background:rgba(255,255,255,.1); border:1px solid rgba(255,255,255,.18); border-radius:999px; padding:6px 14px; text-decoration:none; cursor:pointer; font:inherit; }
        footer .credit { flex-basis:100%; opacity:.6; font-size:.72rem; } footer .credit a { background:none; border:0; padding:0; text-decoration:underline; }
        @media (max-width:640px) { .hide-narrow { display:none; } .fx .dt { display:none; } }
      </style>
      <div class="bg"></div>
      <div class="wrap">
        <header>
          <button class="menu" data-act="menu" aria-label="Menu">&#9776;</button>
          <h1>Motorcycle <span>Racing</span></h1>
        </header>
        <div class="chips">${series
          .map((x) => `<button data-act="cls" data-k="${esc(x.key)}" class="${x.key === this._cls ? "on" : ""}">${esc(x.name)}</button>`)
          .join("")}</div>
        <nav class="tabs">${TABS.map(([k, label]) => `<button data-act="tab" data-k="${k}" class="${k === this._tab ? "on" : ""}">${label}</button>`).join("")}</nav>
        ${view}
        <footer>
          <a href="${PANEL_REPO}" target="_blank" rel="noopener">&#9733; Star us on GitHub</a>
          <button data-act="share">Share with friends</button>
          <a href="${PANEL_REPO}/issues" target="_blank" rel="noopener">Report a problem</a>
          <span class="credit">Background photo: CC0 / public domain, <a href="${BG_PAGE}" target="_blank" rel="noopener">Wikimedia Commons</a>. ${esc((s && s.attribution) || "")} Not affiliated with any championship.</span>
        </footer>
      </div>`;
    root.onclick = (ev) => this._click(ev);
    root.onchange = (ev) => {
      const t = ev.target;
      if (t && t.dataset && t.dataset.act === "pick-event") {
        this._eventId = t.value;
        this._sessionIdx = null;
        this._loadResults();
        this._render();
      }
    };
  }

  _click(ev) {
    const el = ev.target && ev.target.closest ? ev.target.closest("[data-act]") : null;
    if (!el) return;
    const act = el.dataset.act;
    if (act === "cls") {
      this._cls = el.dataset.k;
      store("mr_class", this._cls);
      this._eventId = null;
      this._sessionIdx = null;
      this._live = null;
      this._afterNav();
    } else if (act === "tab") {
      this._tab = el.dataset.k;
      store("mr_tab", this._tab);
      this._sessionIdx = null;
      this._afterNav();
    } else if (act === "session") {
      this._sessionIdx = Number(el.dataset.i);
      this._render();
    } else if (act === "tkind") {
      this._tableKind = el.dataset.k;
      this._render();
    } else if (act === "event") {
      this._eventId = el.dataset.id;
      this._tab = "results";
      this._sessionIdx = null;
      this._afterNav();
    } else if (act === "share") {
      this._share();
    } else if (act === "menu") {
      this.dispatchEvent(new Event("hass-toggle-menu", { bubbles: true, composed: true }));
    }
  }

  _afterNav() {
    this._render();
    if (this._tab === "live") this._loadLive();
    if (this._tab === "results") this._loadResults();
  }
}

if (!customElements.get("motorcycle-racing-panel")) {
  customElements.define("motorcycle-racing-panel", MotorcycleRacingPanel);
}
