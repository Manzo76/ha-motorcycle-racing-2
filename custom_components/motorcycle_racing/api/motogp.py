"""Provider for the Grand Prix classes: MotoGP, Moto2, Moto3 and MotoE.

Reads the public JSON API that motogp.com itself uses. No key is needed, but it
is an undocumented endpoint, so every field is read defensively and a missing
piece degrades that one sensor rather than the whole integration.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from .base import (
    ProviderError,
    RacingProvider,
    classify_session,
    fetch_wikipedia_thumbnail,
    parse_dt,
    to_float,
    to_int,
)
from .models import RaceEvent, ResultRow, SeriesData, Session, StandingRow

_LOGGER = logging.getLogger(__name__)

BASE = "https://api.motogp.pulselive.com/motogp/v1"

SESSION_LABELS = {
    "FP": "Free Practice",
    "P": "Practice",
    "PR": "Practice",
    "Q": "Qualifying",
    "SPR": "Sprint",
    "RAC": "Race",
    "WUP": "Warm Up",
    "RAC1": "Race 1",
    "RAC2": "Race 2",
}


def _session_name(raw: dict[str, Any]) -> str:
    kind = (raw.get("type") or raw.get("session_type") or "").upper().strip()
    number = raw.get("number")
    label = SESSION_LABELS.get(kind)
    if label is None:
        label = kind.title() if kind else "Session"
    if number and kind in ("FP", "P", "PR", "Q"):
        return f"{label} {number}"
    return label


class MotoGPProvider(RacingProvider):
    """Grand Prix racing data from the official results API."""

    attribution = "Data from motogp.com. Not affiliated with Dorna Sports."

    def __init__(self, session, category_match: str, series_key: str, series_name: str) -> None:
        super().__init__(session)
        self._category_match = category_match
        self._series_key = series_key
        self._series_name = series_name
        self._season_uuid: str | None = None
        self._season_year: str | None = None
        self._category_uuid: str | None = None
        self._circuit_image_cache: dict[str, str | None] = {}

    # -- discovery ---------------------------------------------------------

    async def _async_resolve_season(self) -> None:
        seasons = await self._get_json(f"{BASE}/results/seasons")
        if not isinstance(seasons, list) or not seasons:
            raise ProviderError("No seasons returned by the MotoGP API")
        current = next(
            (s for s in seasons if str(s.get("current")) in ("1", "True", "true")),
            None,
        ) or max(seasons, key=lambda s: to_int(s.get("year")) or 0)
        self._season_uuid = current.get("id")
        self._season_year = str(current.get("year"))

    async def _async_resolve_category(self) -> None:
        cats = await self._get_json(
            f"{BASE}/results/categories", {"seasonUuid": self._season_uuid}
        )
        if not isinstance(cats, list):
            raise ProviderError("No categories returned by the MotoGP API")
        wanted = self._category_match.lower()
        for cat in cats:
            name = (cat.get("name") or "").lower().replace("™", "").strip()
            if name.replace(" ", "") == wanted or wanted in name:
                self._category_uuid = cat.get("id")
                return
        raise ProviderError(
            f"Category {self._category_match!r} not found in season {self._season_year}"
        )

    # -- fetching ----------------------------------------------------------

    async def _async_events(self) -> list[RaceEvent]:
        events: list[RaceEvent] = []
        seen: set[str] = set()
        for finished in (True, False):
            raw = await self._get_json(
                f"{BASE}/results/events",
                {"seasonUuid": self._season_uuid, "isFinished": str(finished).lower()},
            )
            if not isinstance(raw, list):
                continue
            for item in raw:
                event = self._parse_event(item, finished)
                if event and event.event_id not in seen:
                    seen.add(event.event_id)
                    events.append(event)
        events.sort(key=lambda e: e.start or datetime.max.replace(tzinfo=timezone.utc))
        for index, event in enumerate(events, start=1):
            if event.round_number is None:
                event.round_number = index
        return events

    def _parse_event(self, item: dict[str, Any], finished: bool) -> RaceEvent | None:
        event_id = item.get("id")
        if not event_id:
            return None
        if item.get("test"):
            return None
        country = item.get("country") or {}
        circuit = item.get("circuit") or {}
        files = item.get("event_files") or {}
        poster = None
        for key in ("poster", "main_poster", "event_poster"):
            candidate = files.get(key)
            if isinstance(candidate, dict):
                poster = candidate.get("url") or candidate.get("file")
            elif isinstance(candidate, str):
                poster = candidate
            if poster:
                break
        return RaceEvent(
            event_id=str(event_id),
            name=item.get("sponsored_name") or item.get("name") or "Grand Prix",
            short_name=item.get("short_name") or item.get("name"),
            round_number=to_int(item.get("sequence")),
            circuit=circuit.get("name"),
            country=country.get("name"),
            country_iso=country.get("iso"),
            start=parse_dt(item.get("date_start") or item.get("date_start_utc")),
            end=parse_dt(item.get("date_end") or item.get("date_end_utc")),
            finished=finished,
            poster=poster,
        )

    async def _async_circuit_image(self, circuit: str | None) -> str | None:
        """Look up a circuit layout picture for `circuit`, caching by name."""
        if not circuit:
            return None
        key = circuit.strip().lower()
        if key not in self._circuit_image_cache:
            image = await fetch_wikipedia_thumbnail(self._session, f"{circuit} circuit")
            if not image:
                image = await fetch_wikipedia_thumbnail(self._session, circuit)
            self._circuit_image_cache[key] = image
        return self._circuit_image_cache[key]

    async def _async_sessions(self, event: RaceEvent) -> list[Session]:
        raw = await self._get_json(
            f"{BASE}/results/sessions",
            {"eventUuid": event.event_id, "categoryUuid": self._category_uuid},
        )
        if not isinstance(raw, list):
            return []
        sessions: list[Session] = []
        for item in raw:
            name = _session_name(item)
            start = parse_dt(item.get("date"))
            condition = item.get("condition") or {}
            sessions.append(
                Session(
                    name=name,
                    kind=classify_session(item.get("type") or name),
                    start=start,
                    end=start + timedelta(minutes=45) if start else None,
                    circuit=item.get("circuit") or event.circuit,
                    weather={
                        k: v
                        for k, v in {
                            "track": condition.get("track"),
                            "air": condition.get("air"),
                            "ground": condition.get("ground"),
                            "humidity": condition.get("humidity"),
                            "weather": condition.get("weather"),
                        }.items()
                        if v
                    },
                    session_id=str(item.get("id")) if item.get("id") else None,
                )
            )
        sessions.sort(key=lambda s: s.start or datetime.max.replace(tzinfo=timezone.utc))
        return sessions

    async def _async_classification(self, session: Session) -> list[ResultRow]:
        if not session.session_id:
            return []
        raw = await self._get_json(
            f"{BASE}/results/session/{session.session_id}/classification",
            {"test": "false"},
        )
        rows = (raw or {}).get("classification") if isinstance(raw, dict) else None
        if not isinstance(rows, list):
            return []
        results: list[ResultRow] = []
        for item in rows:
            rider = item.get("rider") or {}
            team = item.get("team") or rider.get("team") or {}
            constructor = item.get("constructor") or rider.get("constructor") or {}
            country = rider.get("country") or {}
            gap = item.get("gap") or {}
            results.append(
                ResultRow(
                    position=to_int(item.get("position")),
                    rider=rider.get("full_name")
                    or " ".join(filter(None, [rider.get("name"), rider.get("surname")]))
                    or "Unknown",
                    number=to_int(rider.get("number")),
                    team=team.get("name") if isinstance(team, dict) else team,
                    constructor=constructor.get("name")
                    if isinstance(constructor, dict)
                    else constructor,
                    nationality=country.get("iso") or country.get("name"),
                    time=item.get("time"),
                    gap=gap.get("first") if isinstance(gap, dict) else gap,
                    points=to_float(item.get("points")),
                    status=item.get("status"),
                )
            )
        results.sort(key=lambda r: r.position if r.position is not None else 999)
        return results

    async def _async_standings(self) -> tuple[list[StandingRow], list[StandingRow]]:
        raw = await self._get_json(
            f"{BASE}/results/standings",
            {"seasonUuid": self._season_uuid, "categoryUuid": self._category_uuid},
        )
        rows = (raw or {}).get("classification") if isinstance(raw, dict) else None
        if not isinstance(rows, list):
            return [], []
        riders: list[StandingRow] = []
        team_points: dict[str, float] = {}
        for item in rows:
            rider = item.get("rider") or {}
            team = item.get("team") or rider.get("team") or {}
            constructor = item.get("constructor") or {}
            country = rider.get("country") or {}
            team_name = team.get("name") if isinstance(team, dict) else team
            points = to_float(item.get("points")) or 0.0
            riders.append(
                StandingRow(
                    position=to_int(item.get("position")),
                    name=rider.get("full_name")
                    or " ".join(filter(None, [rider.get("name"), rider.get("surname")]))
                    or "Unknown",
                    points=points,
                    team=team_name,
                    constructor=constructor.get("name")
                    if isinstance(constructor, dict)
                    else constructor,
                    nationality=country.get("iso") or country.get("name"),
                    number=to_int(rider.get("number")),
                )
            )
            if team_name:
                team_points[team_name] = team_points.get(team_name, 0.0) + points
        riders.sort(key=lambda r: r.position if r.position is not None else 999)
        teams = [
            StandingRow(position=index, name=name, points=points)
            for index, (name, points) in enumerate(
                sorted(team_points.items(), key=lambda kv: kv[1], reverse=True), start=1
            )
        ]
        return riders, teams

    # -- entry point -------------------------------------------------------

    async def async_get_data(self) -> SeriesData:
        if not self._season_uuid:
            await self._async_resolve_season()
        if not self._category_uuid:
            await self._async_resolve_category()

        data = SeriesData(
            series_key=self._series_key,
            series_name=self._series_name,
            season=self._season_year,
            attribution=self.attribution,
        )

        events = await self._async_events()
        data.events = events
        now = datetime.now(timezone.utc)

        upcoming = [e for e in events if (e.end or e.start or now) >= now]
        past = [e for e in events if (e.end or e.start or now) < now]
        data.next_event = upcoming[0] if upcoming else None
        data.last_event = past[-1] if past else None

        if data.next_event:
            data.next_event.circuit_map = await self._async_circuit_image(
                data.next_event.circuit
            )
            data.next_event.sessions = await self._async_sessions(data.next_event)
            for session in data.next_event.sessions:
                if session.start and session.start >= now:
                    data.next_session = session
                    data.next_session_event = data.next_event
                    break
                if (
                    session.start
                    and session.end
                    and session.start <= now <= session.end
                ):
                    data.live_session = session

        if data.last_event:
            data.last_event.circuit_map = await self._async_circuit_image(
                data.last_event.circuit
            )
            data.last_event.sessions = await self._async_sessions(data.last_event)
            race = data.last_event.race_session
            if race:
                try:
                    data.last_results = await self._async_classification(race)
                except ProviderError as err:
                    _LOGGER.debug("No classification for %s: %s", race.name, err)

        try:
            data.rider_standings, data.team_standings = await self._async_standings()
        except ProviderError as err:
            _LOGGER.debug("No standings available: %s", err)

        return data
