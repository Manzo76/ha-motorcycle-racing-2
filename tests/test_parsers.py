"""Offline checks for the parsing helpers. No network, no Home Assistant."""

import importlib
import sys
import types
from pathlib import Path

# Load custom_components/motorcycle_racing/api as a standalone package, so this
# runs without Home Assistant installed.
ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "motorcycle_racing"
for name, path in (("mr", ROOT), ("mr.api", ROOT / "api")):
    module = types.ModuleType(name)
    module.__path__ = [str(path)]
    sys.modules[name] = module

base = importlib.import_module("mr.api.base")
models = importlib.import_module("mr.api.models")
motogp = importlib.import_module("mr.api.motogp")
sportsdb = importlib.import_module("mr.api.sportsdb")

classify_session, parse_dt = base.classify_session, base.parse_dt
MotoGPProvider, _session_name = motogp.MotoGPProvider, motogp._session_name
SportsDBProvider, _split_results = sportsdb.SportsDBProvider, sportsdb._split_results

failures = []


def check(label, got, want):
    if got != want:
        failures.append(f"{label}: expected {want!r}, got {got!r}")


# --- session classification -------------------------------------------------
check("FP1", classify_session("FP1"), "practice")
check("Q2", classify_session("Q2"), "qualifying")
check("Superpole", classify_session("Superpole"), "qualifying")
check("Superpole Race", classify_session("Superpole Race"), "race")
check("SPR", classify_session("SPR"), "sprint")
check("RAC", classify_session("RAC"), "race")
check("WUP", classify_session("Warm Up"), "warmup")

check("label FP", _session_name({"type": "FP", "number": 1}), "Free Practice 1")
check("label RAC", _session_name({"type": "RAC"}), "Race")
check("label unknown", _session_name({"type": "XYZ"}), "Xyz")

# --- date parsing -----------------------------------------------------------
check("iso z", parse_dt("2026-08-30T13:00:00Z").hour, 13)
check("offset", parse_dt("2026-08-30T13:00:00+02:00").utcoffset().seconds, 7200)
check("date only", parse_dt("2026-08-30").day, 30)
check("naive space", parse_dt("2026-08-30 13:00:00").tzinfo is not None, True)
check("empty", parse_dt(""), None)

# --- MotoGP event parsing ---------------------------------------------------
provider = MotoGPProvider(None, "motogp", "motogp", "MotoGP")
event = provider._parse_event(
    {
        "id": "abc-123",
        "sponsored_name": "Gran Premio di San Marino",
        "name": "San Marino",
        "sequence": 14,
        "circuit": {"name": "Misano World Circuit"},
        "country": {"name": "Italy", "iso": "IT"},
        "date_start": "2026-09-11T08:00:00+00:00",
        "date_end": "2026-09-13T16:00:00+00:00",
        "event_files": {"poster": {"url": "https://example.invalid/p.jpg"}},
    },
    finished=False,
)
check("event name", event.name, "Gran Premio di San Marino")
check("event round", event.round_number, 14)
check("event circuit", event.circuit, "Misano World Circuit")
check("event iso", event.country_iso, "IT")
check("event poster", event.poster, "https://example.invalid/p.jpg")
check("test event skipped", provider._parse_event({"id": "x", "test": True}, False), None)

# race_session picks the last race of the weekend
Session = models.Session

event.sessions = [
    Session("Free Practice 1", "practice", parse_dt("2026-09-11T09:00:00Z")),
    Session("Sprint", "sprint", parse_dt("2026-09-12T13:00:00Z")),
    Session("Race", "race", parse_dt("2026-09-13T12:00:00Z")),
]
check("race session", event.race_session.name, "Race")
check("as_dict sessions", len(event.as_dict()["sessions"]), 3)

# --- TheSportsDB result blob -----------------------------------------------
blob = """1. Nicolo Bulega  Aruba.it Racing
2. Iker Lecuona  Aruba.it Racing
3. Sam Lowes  Elf Marc VDS
not a result line
"""
rows = _split_results(blob)
check("result count", len(rows), 3)
check("result winner", rows[0].rider, "Nicolo Bulega")
check("result team", rows[0].team, "Aruba.it Racing")
check("result empty", _split_results(None), [])

sdb = SportsDBProvider(None, "4454", "worldsbk", "WorldSBK")
sdb_event = sdb._parse_event(
    {
        "idEvent": "2059321",
        "strEvent": "British Round Race 1",
        "dateEvent": "2026-07-18",
        "strTime": "13:00:00",
        "strVenue": "Donington Park",
        "strCountry": "United Kingdom",
        "intRound": "8",
        "strResult": "1. Bulega",
    }
)
check("sdb name", sdb_event.name, "British Round Race 1")
check("sdb round", sdb_event.round_number, 8)
check("sdb finished", sdb_event.finished, True)
check("sdb session kind", sdb_event.sessions[0].kind, "race")
check("sdb start hour", sdb_event.sessions[0].start.hour, 13)

# --- season-over detection --------------------------------------------------
from datetime import datetime, timedelta, timezone

NOW = datetime(2026, 10, 24, 14, 0, tzinfo=timezone.utc)


def _event(eid, start):
    return models.RaceEvent(
        event_id=eid, name=f"Round {eid}", start=start, end=start + timedelta(hours=3)
    )


def _series(season, last, nxt):
    data = models.SeriesData(series_key="bsb", series_name="BSB", season=season)
    data.last_event, data.next_event = last, nxt
    data.next_session = object() if nxt else None
    data.rider_standings = [
        models.StandingRow(position=1, name="Champ", points=500, team="Team A"),
        models.StandingRow(position=2, name="Runner", points=450),
    ]
    data.team_standings = [models.StandingRow(position=1, name="Team A", points=800)]
    return data


# BSB case: season finished in October, next event is May next year (189 days).
last = _event("12", NOW - timedelta(days=7))
nxt = _event("13", NOW + timedelta(days=189))
done = models.apply_season_state(_series("2026", last, nxt), NOW)
check("bsb season_over", done.season_over, True)
check("bsb next_event cleared", done.next_event, None)
check("bsb next_session cleared", done.next_session, None)
check("bsb next season kept", done.next_season_event.event_id, "13")
check("bsb champion rider", done.champion_rider.name, "Champ")
check("bsb champion team", done.champion_team.name, "Team A")

# Mid-season break (~5 weeks) is NOT the end of the season.
mid = models.apply_season_state(
    _series("2026", _event("5", NOW - timedelta(days=10)), _event("6", NOW + timedelta(days=25))),
    NOW,
)
check("mid-season not over", mid.season_over, False)
check("mid-season next kept", mid.next_event.event_id, "6")
check("mid-season no champion", mid.champion_rider, None)

# No upcoming events at all after racing happened -> over.
none_left = models.apply_season_state(_series("2026", _event("9", NOW - timedelta(days=3)), None), NOW)
check("no upcoming -> over", none_left.season_over, True)
check("no upcoming -> no next season", none_left.next_season_event, None)

# Brand-new data with nothing raced is not "over".
fresh = models.apply_season_state(_series("2026", None, _event("1", NOW + timedelta(days=60))), NOW)
check("fresh season not over", fresh.season_over, False)

# Year-rollover guard: 2026 season, next event in 2027 within 100 days.
roll = models.apply_season_state(
    _series("2026", _event("20", datetime(2026, 11, 20, tzinfo=timezone.utc)), _event("21", datetime(2027, 1, 20, tzinfo=timezone.utc))),
    datetime(2026, 11, 25, tzinfo=timezone.utc),
)
check("year rollover over", roll.season_over, True)


# --- champion history -------------------------------------------------------
import asyncio
import json

compose = models.compose_champions
ChampionRow = models.ChampionRow

# shipped dataset is valid, newest-first-sortable and covers the two static series
shipped = json.loads((ROOT / "data" / "champions.json").read_text(encoding="utf-8"))
for key in ("worldsbk", "bsb"):
    rows = [ChampionRow.from_dict(r) for r in shipped[key]]
    check(f"{key} rows valid", all(rows), True)
    check(f"{key} has 2025", any(r.season == "2025" for r in rows), True)
check("bsb 2025 champion", next(r for r in shipped["bsb"] if r["season"] == "2025")["rider"], "Kyle Ryde")
check("wsbk 2023 champion", next(r for r in shipped["worldsbk"] if r["season"] == "2023")["rider"], "\u00c1lvaro Bautista")

hist = [ChampionRow.from_dict(r) for r in shipped["bsb"]]
# season in progress: history only, newest first
live = _series("2026", _event("5", NOW - timedelta(days=10)), _event("6", NOW + timedelta(days=25)))
merged = compose(hist, models.apply_season_state(live, NOW))
check("history newest first", merged[0].season, "2025")
check("history sorted desc", [r.season for r in merged], sorted([r.season for r in merged], reverse=True))

# season over: this season's champion is added on top, once
over = models.apply_season_state(
    _series("2026", _event("12", datetime(2026, 10, 18, tzinfo=timezone.utc)), _event("13", NOW + timedelta(days=189))), NOW
)
merged = compose(hist, over)
check("current champion on top", (merged[0].season, merged[0].rider), ("2026", "Champ"))
check("current champion team title", merged[0].team_champion, "Team A")
check("2025 follows 2026", merged[1].season, "2025")
# already in history -> not duplicated
again = compose(merged, over)
check("no duplicate season", [r.season for r in again].count("2026"), 1)
check("limit respected", len(compose(hist, over, limit=3)), 3)
check("bad row rejected", ChampionRow.from_dict({"season": "2020"}), None)

# MotoGP champion lookup against a fake pulselive
class FakeMotoGP(MotoGPProvider):
    async def _get_json(self, url, params=None):
        if url.endswith("/results/seasons"):
            return [
                {"id": "s26", "year": 2026, "current": True},
                {"id": "s25", "year": 2025, "current": False},
                {"id": "s24", "year": 2024, "current": False},
            ]
        if url.endswith("/results/categories"):
            if params["seasonUuid"] == "s24":
                return [{"id": "c-gp", "name": "MotoGP\u2122"}, {"id": "c-m2", "name": "Moto2\u2122"}]
            return [{"id": "c-gp", "name": "MotoGP\u2122"}]
        if url.endswith("/results/standings"):
            who = {"s25": ("Marc M\u00e1rquez", "Ducati Lenovo Team", 545), "s24": ("Jorge Mart\u00edn", "Prima Pramac Racing", 508)}[params["seasonUuid"]]
            return {"classification": [
                {"position": 1, "points": who[2], "rider": {"full_name": who[0], "number": 93}, "team": {"name": who[1]}, "constructor": {"name": "Ducati"}},
                {"position": 2, "points": 467, "rider": {"full_name": "Alex M\u00e1rquez", "number": 73}, "team": {"name": "Gresini"}, "constructor": {"name": "Ducati"}},
            ]}
        raise AssertionError(url)

fake = FakeMotoGP(None, "motogp", "motogp", "MotoGP")
past = asyncio.run(fake.async_list_past_seasons(10))
check("past seasons exclude current", past, [("2025", "s25"), ("2024", "s24")])
champ = asyncio.run(fake.async_get_champion("2025", "s25"))
check("fake champion rider", champ.rider, "Marc M\u00e1rquez")
check("fake champion team", champ.team, "Ducati Lenovo Team")
check("fake champion constructor", champ.constructor, "Ducati")
check("fake champion points", champ.points, 545.0)
check("fake team title", champ.team_champion, "Ducati Lenovo Team")
moto2 = FakeMotoGP(None, "moto2", "moto2", "Moto2")
check("class that did not run -> None", asyncio.run(moto2.async_get_champion("2025", "s25")), None)

if failures:
    print("FAILURES:")
    for line in failures:
        print("  -", line)
    sys.exit(1)
print("All parser checks passed.")
