// Headless render check for the Lovelace card. No browser, no Home Assistant:
// stubs just enough DOM to let the card build its HTML, then asserts on it.
//   TZ=Europe/London node tests/card_render.test.mjs
import { readFileSync } from "node:fs";
import vm from "node:vm";
import assert from "node:assert/strict";

const src = readFileSync(
  new URL("../custom_components/motorcycle_racing/www/motorcycle-racing-card.js", import.meta.url),
  "utf8"
);

const registry = new Map();
class FakeShadow {
  constructor() { this.innerHTML = ""; }
  querySelector() { return null; }
}
class FakeElement {
  attachShadow() { this.shadowRoot = new FakeShadow(); return this.shadowRoot; }
}
const sandbox = {
  HTMLElement: FakeElement,
  customElements: { get: (n) => registry.get(n), define: (n, c) => registry.set(n, c) },
  window: {},
  console, Date, Intl, Math, Number, String, Object, Array, Boolean, Promise, JSON, setTimeout,
};
sandbox.window.customCards = [];
vm.createContext(sandbox);
vm.runInContext(src, sandbox);

const Card = registry.get("motorcycle-racing-card");
assert.ok(Card, "card defined");
assert.equal(sandbox.window.customCards.length, 3, "three cards registered once");

// Loading the module twice must not throw (HACS + Lovelace resource both load
// it). Each ES module has its own scope, so use a fresh context that shares the
// custom element registry and window.
const second = { ...sandbox };
vm.createContext(second);
vm.runInContext(src, second);
assert.equal(sandbox.window.customCards.length, 3, "no duplicate registration");

function entities(map) {
  return Object.fromEntries(
    Object.entries(map).map(([k, v]) => [`sensor.bsb_${k}`, v])
  );
}
const podium = [
  { position: 1, rider: "Kyle Ryde", team: "Ducati", time: "35:12.100" },
  { position: 2, rider: "Tommy Bridewell", team: "Honda", gap: "+0.8" },
  { position: 3, rider: "Danny Kent", team: "Yamaha", gap: "+1.9" },
];
const classification = [
  ...podium,
  { position: 4, rider: "Rider Four", team: "BMW", gap: "+3.0" },
  { position: 5, rider: "Rider Five", team: "Kawasaki", gap: "+4.0" },
];
const standings = [
  { position: 1, name: "Kyle Ryde", team: "Ducati", points: 612 },
  { position: 2, name: "Tommy Bridewell", team: "Honda", points: 590 },
];

async function mount(states, config = { series: "bsb" }, locale = {}) {
  const card = new Card();
  card.setConfig(config);
  const keys = Object.keys(states);
  const hass = {
    locale: { language: "en-GB", time_zone: "local", time_format: "24", ...locale },
    config: { time_zone: "Europe/London" },
    states,
    callWS: async ({ type }) => {
      if (type === "config/device_registry/list")
        return [{ id: "dev1", name: "British Superbikes", identifiers: [["motorcycle_racing", "x"]] }];
      return keys.map((id) => ({
        entity_id: id, device_id: "dev1",
        unique_id: `abc_${id.replace("sensor.bsb_", "").replace("binary_sensor.bsb_", "")}`,
      }));
    },
  };
  card.hass = hass;
  await new Promise((r) => setTimeout(r, 20));
  card.hass = hass;
  return card.shadowRoot.innerHTML;
}

const base = {
  "sensor.bsb_last_race": {
    state: "Kyle Ryde",
    attributes: { event: "Brands Hatch GP", winner: "Kyle Ryde", podium, classification, season: "2026" },
  },
  "sensor.bsb_rider_standings": { state: "Kyle Ryde", attributes: { standings, season: "2026" } },
};

// 1. Normal weekend, session starting 2026-10-25 12:30 UTC. UK is on BST until
//    25 Oct 01:00 UTC... clocks went back on 2026-10-25, so use a summer date.
const summerStart = "2026-07-12T12:30:00+00:00";
let html = await mount({
  ...base,
  "sensor.bsb_next_race": {
    state: "Oulton Park",
    attributes: {
      season: "2026", season_over: false, race_start: summerStart, start: summerStart,
      sessions: [{ name: "Race 1", kind: "race", start: summerStart }],
    },
  },
  "sensor.bsb_next_session": { state: "Race 1", attributes: { start: summerStart } },
  "sensor.bsb_next_session_time": { state: summerStart, attributes: {} },
});
assert.match(html, /Oulton Park/, "next race shown");
assert.match(html, /13:30/, "12:30 UTC shown as 13:30 BST, not GMT");
assert.match(html, /BST|GMT\+1/, "zone name shown");
assert.doesNotMatch(html, /12:30 GMT/, "no fixed GMT");
assert.match(html, /class="podium"/, "podium rendered");
assert.match(html, /pod p1/, "winner step");
assert.match(html, /Rider Four/, "table continues after podium");
assert.doesNotMatch(html, /Season complete/, "not season over");
assert.doesNotMatch(html, /class="live-banner"/, "not live");

// 2. Explicit GMT config still works.
html = await mount({
  ...base,
  "sensor.bsb_next_race": { state: "Oulton Park", attributes: { season_over: false, sessions: [{ name: "Race 1", kind: "race", start: summerStart }] } },
}, { series: "bsb", time_zone: "GMT" });
assert.match(html, /12:30/, "GMT override honoured");

// 3. Live session.
html = await mount({
  ...base,
  "sensor.bsb_next_race": { state: "Oulton Park", attributes: { season_over: false, sessions: [] } },
  "sensor.bsb_next_session": { state: "Race 1", attributes: {} },
  "binary_sensor.bsb_session_live": { state: "on", attributes: { session: "Race 1" } },
});
assert.match(html, /class="live-banner"/, "live banner");
assert.match(html, /lamp go/, "green lamps");
assert.match(html, /is-live/, "live glow");
assert.match(html, /Race 1 is live/, "gantry label");

// 4. Season complete (BSB case).
html = await mount({
  ...base,
  "sensor.bsb_next_race": {
    state: "Season complete",
    attributes: {
      season: "2026", season_over: true,
      next_season_event: "Donington Park", next_season_circuit: "Donington Park",
      next_season_start: "2027-05-01T10:00:00+00:00",
    },
  },
  "sensor.bsb_next_session": { state: "Season complete", attributes: {} },
  "sensor.bsb_rider_standings": {
    state: "Kyle Ryde",
    attributes: { standings, season: "2026", season_over: true, champion: "Kyle Ryde", champion_team: "Ducati", champion_points: 612, champion_number: 1 },
  },
  "sensor.bsb_team_standings": {
    state: "Ducati",
    attributes: { standings: [{ position: 1, name: "Ducati", points: 900 }], champion_team: "Ducati" },
  },
});
assert.match(html, /2026 champion/, "champion label");
assert.match(html, /Kyle Ryde/, "champion rider");
assert.match(html, /Team champions: Ducati/, "champion team");
assert.match(html, /Season complete/, "badge");
assert.match(html, /Next season/, "next season card");
assert.match(html, /Donington Park/, "next season event");
assert.doesNotMatch(html, /Next round/, "no next round card");
assert.doesNotMatch(html, /Weekend schedule/, "no schedule");
assert.match(html, /final standings/, "final standings heading");
assert.match(html, /1 May 2027/, "next season start date shown, labelled as next season");
assert.doesNotMatch(html, /Next session/, "no next session wording");

// 5. Unknown IANA zone must not throw.
html = await mount({
  ...base,
  "sensor.bsb_next_race": { state: "Oulton Park", attributes: { season_over: false, sessions: [{ name: "Race 1", kind: "race", start: summerStart }] } },
}, { series: "bsb", time_zone: "Not/AZone" });
assert.match(html, /Oulton Park/, "bad zone falls back");

console.log("Card render checks passed.");
