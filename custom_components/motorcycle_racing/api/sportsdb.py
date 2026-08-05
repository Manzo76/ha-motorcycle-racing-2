"""Provider backed by TheSportsDB.

Covers every series that does not have its own first-party feed: WorldSBK,
World Supersport, British Superbikes, Endurance and anything else in
TheSportsDB's motorsport catalogue. It also supplies the artwork (badges,
posters, fanart) that the dashboard card leans on.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp

from .base import (
    RacingProvider,
    classify_session,
    fetch_wikipedia_thumbnail,
    parse_dt,
    to_float,
    to_int,
)
from .models import RaceEvent, ResultRow, SeriesData, Session, StandingRow

_LOGGER = logging.getLogger(__name__)

BASE = "https://www.thesportsdb.com/api/v1/json"

MOTORCYCLE_HINTS = (
    "moto",
    "superbike",
    "supersport",
    "sbk",
    "bsb",
    "sidecar",
    "speedway",
    "motocross",
    "supercross",
    "endurance world",
    "isle of man",
    "road racing",
    "trial",
    "enduro",
)

# "1. Nicolo Bulega", "1 Nicolo Bulega - Ducati", "P1 | Bulega"
_RESULT_LINE = re.compile(r"^\s*(?:P|POS\.?)?\s*(\d{1,2})\s*[.)\-:|]?\s+(.+)$", re.I)
# Rider and team are separated by two spaces, a tab, a pipe or a spaced dash.
_FIELD_SPLIT = re.compile(r"\s{2,}|\t+|\s*\|\s*|\s+[-–]\s+")
_HAS_LETTERS = re.compile(r"[A-Za-zÀ-ÿ]")


def _split_results(blob: str | None) -> list[ResultRow]:
    """Best-effort parse of TheSportsDB's free-text result field."""
    if not blob:
        return []
    rows: list[ResultRow] = []
    for line in blob.replace("\r", "\n").split("\n"):
        line = line.strip()
        if not line:
            continue
        match = _RESULT_LINE.match(line)
        if not match:
            continue
        position, remainder = match.groups()
        fields = [part.strip(" -–\t") for part in _FIELD_SPLIT.split(remainder, maxsplit=1)]
        rider = fields[0]
        if len(rider) < 3 or not _HAS_LETTERS.search(rider):
            continue
        rows.append(
            ResultRow(
                position=to_int(position),
                rider=rider,
                team=(fields[1] if len(fields) > 1 else "") or None,
            )
        )
    rows.sort(key=lambda r: r.position if r.position is not None else 999)
    return rows


class SportsDBProvider(RacingProvider):
    """Schedules, results and artwork from TheSportsDB."""

    attribution = "Data from TheSportsDB.com"

    def __init__(
        self,
        session: aiohttp.ClientSession,
        league_id: str,
        series_key: str,
        series_name: str,
        api_key: str = "123",
    ) -> None:
        super().__init__(session)
        self._league_id = str(league_id)
        self._series_key = series_key
        self._series_name = series_name
        self._api_key = api_key or "123"
        self._circuit_image_cache: dict[str, str | None] = {}

    @property
    def _root(self) -> str:
        return f"{BASE}/{self._api_key}"

    # -- static helpers used by the config flow ----------------------------

    @staticmethod
    async def async_list_motorcycle_leagues(
        session: aiohttp.ClientSession, api_key: str = "123"
    ) -> list[dict[str, str]]:
        """Return every motorcycle-ish league TheSportsDB knows about."""
        provider = SportsDBProvider(session, "0", "discovery", "discovery", api_key)
        payload = await provider._get_json(f"{provider._root}/all_leagues.php")
        leagues = (payload or {}).get("leagues") or []
        found: list[dict[str, str]] = []
        for league in leagues:
            if (league.get("strSport") or "").lower() != "motorsport":
                continue
            name = league.get("strLeague") or ""
            haystack = f"{name} {league.get('strLeagueAlternate') or ''}".lower()
            if not any(hint in haystack for hint in MOTORCYCLE_HINTS):
                continue
            if league.get("idLeague"):
                found.append({"id": str(league["idLeague"]), "name": name})
        found.sort(key=lambda item: item["name"])
        return found

    # -- fetching ----------------------------------------------------------

    def _parse_event(self, item: dict[str, Any]) -> RaceEvent | None:
        event_id = item.get("idEvent")
        if not event_id:
            return None
        start = parse_dt(item.get("strTimestamp"))
        if start is None:
            date_part = item.get("dateEvent")
            time_part = item.get("strTime") or "00:00:00"
            if date_part:
                start = parse_dt(f"{date_part}T{time_part}")
        name = item.get("strEvent") or "Race"
        session = Session(
            name="Race",
            kind=classify_session(name) if "practice" in name.lower() else "race",
            start=start,
            end=(start + timedelta(hours=1)) if start else None,
            circuit=item.get("strVenue"),
            session_id=str(event_id),
        )
        return RaceEvent(
            event_id=str(event_id),
            name=name,
            short_name=item.get("strEventAlternate") or name,
            round_number=to_int(item.get("intRound")),
            circuit=item.get("strVenue"),
            country=item.get("strCountry"),
            start=start,
            end=session.end,
            finished=(item.get("strStatus") or "").lower()
            in ("match finished", "finished", "ft")
            or bool(item.get("strResult")),
            sessions=[session],
            poster=item.get("strPoster") or item.get("strThumb"),
            banner=item.get("strBanner") or item.get("strThumb"),
            circuit_map=item.get("strMap"),
        )

    async def _async_circuit_image(self, circuit: str | None) -> str | None:
        """Fall back to a Wikipedia lead image when TheSportsDB has no map."""
        if not circuit:
            return None
        key = circuit.strip().lower()
        if key not in self._circuit_image_cache:
            image = await fetch_wikipedia_thumbnail(self._session, f"{circuit} circuit")
            if not image:
                image = await fetch_wikipedia_thumbnail(self._session, circuit)
            self._circuit_image_cache[key] = image
        return self._circuit_image_cache[key]

    async def _async_league_meta(self) -> dict[str, Any]:
        payload = await self._get_json(
            f"{self._root}/lookupleague.php", {"id": self._league_id}
        )
        leagues = (payload or {}).get("leagues") or []
        return leagues[0] if leagues else {}

    async def _async_events(self, endpoint: str) -> list[RaceEvent]:
        payload = await self._get_json(
            f"{self._root}/{endpoint}", {"id": self._league_id}
        )
        raw = (payload or {}).get("events") or []
        parsed = [self._parse_event(item) for item in raw]
        return [event for event in parsed if event]

    async def _async_season_events(self, season: str | None) -> list[RaceEvent]:
        if not season:
            return []
        payload = await self._get_json(
            f"{self._root}/eventsseason.php", {"id": self._league_id, "s": season}
        )
        raw = (payload or {}).get("events") or []
        parsed = [self._parse_event(item) for item in raw]
        return [event for event in parsed if event]

    async def _async_table(self, season: str | None) -> list[StandingRow]:
        params: dict[str, Any] = {"l": self._league_id}
        if season:
            params["s"] = season
        payload = await self._get_json(f"{self._root}/lookuptable.php", params)
        rows = (payload or {}).get("table") or []
        standings: list[StandingRow] = []
        for row in rows:
            name = row.get("strTeam") or row.get("name")
            if not name:
                continue
            standings.append(
                StandingRow(
                    position=to_int(row.get("intRank") or row.get("intPosition")),
                    name=name,
                    points=to_float(row.get("intPoints")),
                    wins=to_int(row.get("intWin")),
                )
            )
        standings.sort(key=lambda r: r.position if r.position is not None else 999)
        return standings

    # -- entry point -------------------------------------------------------

    async def async_get_data(self) -> SeriesData:
        meta = await self._async_league_meta()
        season = meta.get("strCurrentSeason")

        data = SeriesData(
            series_key=self._series_key,
            series_name=meta.get("strLeague") or self._series_name,
            season=season,
            badge=meta.get("strBadge"),
            logo=meta.get("strLogo"),
            fanart=meta.get("strFanart1") or meta.get("strFanart2"),
            attribution=self.attribution,
        )

        events: dict[str, RaceEvent] = {}
        for event in await self._async_season_events(season):
            events[event.event_id] = event
        for endpoint in ("eventsnextleague.php", "eventspastleague.php"):
            try:
                for event in await self._async_events(endpoint):
                    events[event.event_id] = event
            except Exception as err:  # noqa: BLE001 - one endpoint failing is survivable
                _LOGGER.debug("%s unavailable: %s", endpoint, err)

        ordered = sorted(
            events.values(),
            key=lambda e: e.start or datetime.max.replace(tzinfo=timezone.utc),
        )
        data.events = ordered

        now = datetime.now(timezone.utc)
        upcoming = [e for e in ordered if (e.end or e.start or now) >= now]
        past = [e for e in ordered if (e.end or e.start or now) < now]
        data.next_event = upcoming[0] if upcoming else None
        data.last_event = past[-1] if past else None

        for event in (data.next_event, data.last_event):
            if event and not event.circuit_map:
                event.circuit_map = await self._async_circuit_image(event.circuit)

        if data.next_event and data.next_event.sessions:
            session = data.next_event.sessions[0]
            if session.start and session.start >= now:
                data.next_session = session
                data.next_session_event = data.next_event
            elif session.start and session.end and session.start <= now <= session.end:
                data.live_session = session

        if data.last_event:
            detail = await self._get_json(
                f"{self._root}/lookupevent.php", {"id": data.last_event.event_id}
            )
            found = (detail or {}).get("events") or []
            if found:
                data.last_results = _split_results(found[0].get("strResult"))

        try:
            data.rider_standings = await self._async_table(season)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("No championship table for league %s: %s", self._league_id, err)

        return data
