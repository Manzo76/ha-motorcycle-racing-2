# Motorcycle Racing for Home Assistant - Made by Manzo.
# Copyright (c) 2026 Manzo76. All rights reserved. See LICENSE.
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
    cancelled: bool = False
    cancel_reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "start": _iso(self.start),
            "end": _iso(self.end),
            "circuit": self.circuit,
            "weather": self.weather or None,
            "cancelled": self.cancelled,
            "cancel_reason": self.cancel_reason,
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
        """The main race that actually ran, falling back to the last session held.

        Cancelled sessions are never returned: a washed-out Sunday race must not
        be mistaken for a result to fetch.
        """
        live = [s for s in self.sessions if not s.cancelled]
        races = [s for s in live if s.kind == "race"]
        if races:
            return sorted(races, key=lambda s: s.start or datetime.max)[-1]
        dated = [s for s in live if s.start]
        return sorted(dated, key=lambda s: s.start)[-1] if dated else None

    @property
    def race_cancelled(self) -> bool:
        """True when the weekend's main race was called off."""
        return any(s.cancelled and s.kind == "race" for s in self.sessions)

    @property
    def cancel_reason(self) -> str | None:
        for s in self.sessions:
            if s.cancelled and s.kind == "race" and s.cancel_reason:
                return s.cancel_reason
        return None

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
            "race_cancelled": self.race_cancelled,
            "cancel_reason": self.cancel_reason,
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
class ChampionRow:
    """The rider (and optionally team) that won one season's championship."""

    season: str
    rider: str
    team: str | None = None
    constructor: str | None = None
    points: float | None = None
    number: int | None = None
    team_champion: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "season": self.season,
            "rider": self.rider,
            "team": self.team,
            "constructor": self.constructor,
            "points": self.points,
            "number": self.number,
            "team_champion": self.team_champion,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ChampionRow | None":
        season = str(raw.get("season") or "").strip()
        rider = (raw.get("rider") or "").strip()
        if not season or not rider:
            return None
        points = raw.get("points")
        number = raw.get("number")
        return cls(
            season=season,
            rider=rider,
            team=raw.get("team") or None,
            constructor=raw.get("constructor") or None,
            points=float(points) if isinstance(points, (int, float)) else None,
            number=int(number) if isinstance(number, (int, float)) else None,
            team_champion=raw.get("team_champion") or None,
        )


@dataclass(slots=True)
class SeriesData:
    """Everything the coordinator knows about one series right now."""

    series_key: str
    series_name: str
    season: str | None = None
    events: list[RaceEvent] = field(default_factory=list)
    next_event: RaceEvent | None = None
    last_event: RaceEvent | None = None
    # Most recent round whose race was cancelled, if it is newer than last_event.
    cancelled_event: RaceEvent | None = None
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
    # Set by apply_season_state() once the calendar has been fully raced.
    season_over: bool = False
    next_season_event: RaceEvent | None = None
    champion_rider: StandingRow | None = None
    champion_team: StandingRow | None = None
    # Past champions, newest season first. Filled by the coordinator.
    champions: list[ChampionRow] = field(default_factory=list)


# A gap this long between the last round raced and the next one on the calendar
# means the next one belongs to a new season (mid-season breaks are ~6 weeks).
SEASON_GAP_DAYS = 100


def _season_year(season: str | None) -> int | None:
    """Return the year for a plain "2026" season label, else None."""
    text = (season or "").strip()
    return int(text) if len(text) == 4 and text.isdigit() else None


def apply_season_state(data: SeriesData, now: datetime) -> SeriesData:
    """Work out whether the season has finished and, if so, who won it.

    Providers return the *next* event on the calendar, which after the final
    round is the opening round of next season (e.g. British Superbikes
    showing "next race in 189 days"). When the season is complete we move that
    event to ``next_season_event`` so "next race" and "next session" read as
    finished, and expose the champions from the final standings.
    """
    last = data.last_event
    nxt = data.next_event

    if nxt is None:
        # Nothing left on the calendar and at least one round has been raced.
        data.season_over = bool(last)
    elif last is not None:
        last_end = last.end or last.start
        if last_end and nxt.start:
            gap_days = (nxt.start - last_end).days
            data.season_over = gap_days > SEASON_GAP_DAYS
        year = _season_year(data.season)
        if (
            not data.season_over
            and year is not None
            and nxt.start is not None
            and nxt.start.year > year
            and last.start is not None
            and last.start.year == year
        ):
            data.season_over = True

    if not data.season_over:
        return data

    if nxt is not None:
        data.next_season_event = nxt
    data.next_event = None
    data.next_session = None
    data.next_session_event = None
    data.live_session = None
    if data.rider_standings:
        data.champion_rider = data.rider_standings[0]
    if data.team_standings:
        data.champion_team = data.team_standings[0]
    return data


def compose_champions(
    history: list[ChampionRow], data: SeriesData, limit: int = 25
) -> list[ChampionRow]:
    """Merge stored history with this season's champion, newest season first.

    Once a season is complete its champion is known from the live standings
    before any history source has caught up, so add it (keyed by the year the
    final round was raced) unless the history already has that season.
    """
    rows: dict[str, ChampionRow] = {row.season: row for row in history}
    champion = data.champion_rider
    last = data.last_event
    if data.season_over and champion and last and last.start:
        season = str(last.start.year)
        if season not in rows:
            rows[season] = ChampionRow(
                season=season,
                rider=champion.name,
                team=champion.team,
                constructor=champion.constructor,
                points=champion.points,
                number=champion.number,
                team_champion=data.champion_team.name if data.champion_team else None,
            )

    def _key(row: ChampionRow) -> int:
        digits = "".join(ch for ch in row.season[:4] if ch.isdigit())
        return int(digits) if digits else 0

    return sorted(rows.values(), key=_key, reverse=True)[:limit]
