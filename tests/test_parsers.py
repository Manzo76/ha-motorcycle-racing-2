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

if failures:
    print("FAILURES:")
    for line in failures:
        print("  -", line)
    sys.exit(1)
print("All parser checks passed.")
