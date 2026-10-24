// Headless render check for the sidebar panel.  node tests/panel_render.test.mjs
import { readFileSync } from "node:fs";
import vm from "node:vm";
import assert from "node:assert/strict";

const src = readFileSync(
  new URL("../custom_components/motorcycle_racing/www/motorcycle-racing-panel.js", import.meta.url), "utf8");
const registry = new Map();
class FakeShadow { constructor() { this.innerHTML = ""; } }
class FakeElement { attachShadow() { this.shadowRoot = new FakeShadow(); return this.shadowRoot; } dispatchEvent() {} }
const sandbox = {
  HTMLElement: FakeElement, Event: class {}, navigator: {},
  customElements: { get: (n) => registry.get(n), define: (n, c) => registry.set(n, c) },
  window: { localStorage: { _s: {}, getItem(k) { return this._s[k] ?? null; }, setItem(k, v) { this._s[k] = v; } } },
  console, Date, Intl, Math, Number, String, Object, Array, JSON, Promise, setTimeout, setInterval, clearInterval, encodeURIComponent,
};
vm.createContext(sandbox);
vm.runInContext(src, sandbox);
const Panel = registry.get("motorcycle-racing-panel");
assert.ok(Panel, "panel defined");

const rows = [
  { position: 1, rider: "Marc Marquez", number: 93, team: "Ducati", time: "40:01.1" },
  { position: 2, rider: "Alex Marquez", team: "Gresini", gap: "+1.2" },
  { position: 3, rider: "Pecco Bagnaia", team: "Ducati", gap: "+2.0" },
  { position: 4, rider: "Rider <b>Four</b>", team: "KTM", gap: "+3.0" },
];
const series = [
  { key: "motogp", name: "MotoGP", accent: "#D6001C", ready: true, season: "2026", season_over: false,
    live: null, next_event: { id: "e2", name: "Japanese GP", circuit: "Motegi", country: "Japan", start: "2026-10-02T04:00:00+00:00", end: "2026-10-04T08:00:00+00:00" },
    next_session: { name: "Race", start: "2026-10-04T07:00:00+00:00" },
    last_event: { id: "e1", name: "Australian GP", circuit: "Phillip Island", start: "2026-09-18T00:00:00+00:00", end: "2026-09-20T05:00:00+00:00", finished: true },
    last_results: rows,
    calendar: [{ id: "e1", round: 1, name: "Australian GP", finished: true, start: "2026-09-18T00:00:00+00:00" }, { id: "e2", round: 2, name: "Japanese GP", finished: false, start: "2026-10-02T04:00:00+00:00" }],
    riders: [{ position: 1, name: "Marc Marquez", team: "Ducati", points: 300 }], teams: [{ position: 1, name: "Ducati", points: 500 }],
    champions: [{ season: "2025", rider: "Marc Marquez", team: "Ducati", team_champion: "Ducati" }], attribution: "Data from motogp.com." },
  { key: "bsb", name: "British Superbikes", accent: "#00843D", ready: true, season: "2026", season_over: true,
    champion: { name: "Kyle Ryde" }, next_season_event: { name: "Donington", start: "2027-05-01T10:00:00+00:00" }, calendar: [], riders: [], teams: [], champions: [], last_results: [] },
];
const calls = [];
const hass = {
  locale: { language: "en-GB", time_zone: "local" }, config: { time_zone: "Europe/London" },
  callWS: async (msg) => {
    calls.push(msg.type);
    if (msg.type.endsWith("overview")) return { series };
    if (msg.type.endsWith("event_results")) return { sessions: [{ name: "Race", kind: "race", results: rows }, { name: "Qualifying", kind: "qualifying", results: rows }] };
    if (msg.type.endsWith("live")) return { live: { name: "Race" }, event: { name: "Japanese GP" }, sessions: [{ name: "Race", results: rows }] };
  },
};
const wait = () => new Promise((r) => setTimeout(r, 30));
const p = new Panel();
p.hass = hass;
await wait();
let html = p.shadowRoot.innerHTML;
assert.match(html, /Next: <b>Japanese GP/, "overview next race");
assert.match(html, /class="podium"/, "podium");
assert.doesNotMatch(html, /<b>Four<\/b>/, "html escaped");
assert.match(html, /Star us on GitHub/, "github link");
assert.match(html, /Wikimedia Commons/, "image credit");
assert.match(html, /British Superbikes/, "class chips");

p._cls = "bsb"; p._render();
html = p.shadowRoot.innerHTML;
assert.match(html, /season complete/, "season over");
assert.match(html, /Kyle Ryde/, "champion");
assert.match(html, /Next season/, "next season card");

p._cls = "motogp"; p._tab = "fixtures"; p._render();
assert.match(p.shadowRoot.innerHTML, /Japanese GP/);
p._click({ target: { closest: () => ({ dataset: { act: "event", id: "e1" } }) } });
await wait();
html = p.shadowRoot.innerHTML;
assert.ok(calls.includes("motorcycle_racing/event_results"), "results fetched");
assert.match(html, /Qualifying/, "session chips");
assert.match(html, /Australian GP/, "event picker");

p._tab = "live"; p._afterNav(); await wait();
assert.match(p.shadowRoot.innerHTML, /Race is live/, "live banner");

p._tab = "tables"; p._render();
assert.match(p.shadowRoot.innerHTML, /Ducati/, "tables");
p._tab = "history"; p._render();
assert.match(p.shadowRoot.innerHTML, /past champions/, "history");
console.log("Panel render checks passed.");
process.exit(0);
