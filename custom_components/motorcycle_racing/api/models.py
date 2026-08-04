"""Normalised data model shared by every Motorcycle Racing provider.

Providers translate whatever their upstream API returns into these objects, so
the sensors, calendar and Lovelace card never need to know where the data came
from.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


@dataclass(slots=True)
class Session:
    """A single on-track session inside a race weekend."""

    name: str
    kind: str  # practice | qualifying | sprint | race | warmup | test | other
    start: datetime | None = None
    end: datetime | None = None
    circuit: str | None = None
    weather: dict[str, Any] = field(default_factory=dict)
    session_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "start": _iso(self.start),
            "end": _iso(self.end),
            "circuit": self.circuit,
            "weather": self.weather or None,
        }


@dataclass(slots=True)
class RaceEvent:
    """A race weekend / round."""

    event_id: str
    name: str
    short_name: str | None = None
    round_number: int | None = None
    circuit: str | None = None
    country: str | None = None
    country_iso: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    finished: bool = False
    sessions: list[Session] = field(default_factory=list)
    poster: str | None = None
    banner: str | None = None
    circuit_map: str | None = None

    @property
    def race_session(self) -> Session | None:
        """The main race, falling back to the last session of the weekend."""
        races = [s for s in self.sessions if s.kind == "race"]
        if races:
            return sorted(races, key=lambda s: s.start or datetime.max)[-1]
        dated = [s for s in self.sessions if s.start]
        return sorted(dated, key=lambda s: s.start)[-1] if dated else None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "short_name": self.short_name,
            "round": self.round_number,
            "circuit": self.circuit,
            "country": self.country,
            "country_code": self.country_iso,
            "start": _iso(self.start),
            "end": _iso(self.end),
            "finished": self.finished,
            "sessions": [s.as_dict() for s in self.sessions],
            "poster": self.poster,
            "banner": self.banner,
            "circuit_map": self.circuit_map,
        }


@dataclass(slots=True)
class ResultRow:
    """One line of a race classification."""

    position: int | None
    rider: str
    number: int | None = None
    team: str | None = None
    constructor: str | None = None
    nationality: str | None = None
    time: str | None = None
    gap: str | None = None
    points: float | None = None
    status: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "position": self.position,
            "rider": self.rider,
            "number": self.number,
            "team": self.team,
            "constructor": self.constructor,
            "nationality": self.nationality,
            "time": self.time,
            "gap": self.gap,
            "points": self.points,
            "status": self.status,
        }


@dataclass(slots=True)
class StandingRow:
    """One line of a championship table."""

    position: int | None
    name: str
    points: float | None = None
    team: str | None = None
    constructor: str | None = None
    nationality: str | None = None
    wins: int | None = None
    number: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "position": self.position,
            "name": self.name,
            "points": self.points,
            "team": self.team,
            "constructor": self.constructor,
            "nationality": self.nationality,
            "wins": self.wins,
            "number": self.number,
        }


@dataclass(slots=True)
class SeriesData:
    """Everything the coordinator knows about one series right now."""

    series_key: str
    series_name: str
    season: str | None = None
    events: list[RaceEvent] = field(default_factory=list)
    next_event: RaceEvent | None = None
    last_event: RaceEvent | None = None
    next_session: Session | None = None
    next_session_event: RaceEvent | None = None
    live_session: Session | None = None
    last_results: list[ResultRow] = field(default_factory=list)
    rider_standings: list[StandingRow] = field(default_factory=list)
    team_standings: list[StandingRow] = field(default_factory=list)
    badge: str | None = None
    logo: str | None = None
    fanart: str | None = None
    attribution: str | None = None
