"""Sensors for the Motorcycle Racing integration."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import RacingConfigEntry
from .const import CONF_FAVOURITE_RIDER
from .coordinator import RacingCoordinator
from .entity import RacingEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RacingConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensors for one series."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        NextRaceSensor(coordinator),
        NextSessionSensor(coordinator),
        NextSessionTimeSensor(coordinator),
        LastRaceSensor(coordinator),
        RiderStandingsSensor(coordinator),
        TeamStandingsSensor(coordinator),
        SeasonRoundSensor(coordinator),
    ]
    if (entry.options.get(CONF_FAVOURITE_RIDER) or "").strip():
        entities.append(FavouriteRiderSensor(coordinator))
    async_add_entities(entities)


def _countdown(target: datetime | None) -> dict[str, Any]:
    if not target:
        return {"days_until": None, "hours_until": None, "minutes_until": None}
    delta = target - datetime.now(timezone.utc)
    total_minutes = int(delta.total_seconds() // 60)
    return {
        "days_until": delta.days,
        "hours_until": round(delta.total_seconds() / 3600, 1),
        "minutes_until": total_minutes,
    }


class NextRaceSensor(RacingEntity, SensorEntity):
    """The next round on the calendar."""

    _attr_translation_key = "next_race"
    _attr_icon = "mdi:flag-checkered"

    def __init__(self, coordinator: RacingCoordinator) -> None:
        super().__init__(coordinator, "next_race")

    @property
    def native_value(self) -> str | None:
        event = self.series.next_event
        return event.name if event else "No race scheduled"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        event = self.series.next_event
        if not event:
            return {"season": self.series.season}
        race = event.race_session
        attrs = event.as_dict()
        attrs.update(_countdown(race.start if race else event.start))
        attrs["race_start"] = race.start.isoformat() if race and race.start else None
        attrs["season"] = self.series.season
        attrs["series"] = self.series.series_name
        attrs["accent_colour"] = self.coordinator.accent
        return attrs


class NextSessionSensor(RacingEntity, SensorEntity):
    """The next on-track session, whatever kind it is."""

    _attr_translation_key = "next_session"
    _attr_icon = "mdi:timer-outline"

    def __init__(self, coordinator: RacingCoordinator) -> None:
        super().__init__(coordinator, "next_session")

    @property
    def native_value(self) -> str | None:
        session = self.series.next_session
        return session.name if session else "No session scheduled"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        session = self.series.next_session
        event = self.series.next_session_event
        if not session:
            return {}
        attrs = session.as_dict()
        attrs.update(_countdown(session.start))
        attrs["event"] = event.name if event else None
        attrs["round"] = event.round_number if event else None
        return attrs


class NextSessionTimeSensor(RacingEntity, SensorEntity):
    """Timestamp of the next session, for automations and countdown cards."""

    _attr_translation_key = "next_session_time"
    _attr_icon = "mdi:clock-start"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: RacingCoordinator) -> None:
        super().__init__(coordinator, "next_session_time")

    @property
    def native_value(self) -> datetime | None:
        session = self.series.next_session
        return session.start if session else None


class LastRaceSensor(RacingEntity, SensorEntity):
    """Winner of the most recent race, with the full classification attached."""

    _attr_translation_key = "last_race"
    _attr_icon = "mdi:trophy"

    def __init__(self, coordinator: RacingCoordinator) -> None:
        super().__init__(coordinator, "last_race")

    @property
    def native_value(self) -> str | None:
        results = self.series.last_results
        if results:
            return results[0].rider
        event = self.series.last_event
        return event.name if event else "No results yet"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        event = self.series.last_event
        results = self.series.last_results
        attrs: dict[str, Any] = {
            "event": event.name if event else None,
            "circuit": event.circuit if event else None,
            "country": event.country if event else None,
            "round": event.round_number if event else None,
            "date": event.start.isoformat() if event and event.start else None,
            "season": self.series.season,
            "podium": [row.as_dict() for row in results[:3]],
            "classification": [row.as_dict() for row in results],
            "poster": event.poster if event else None,
        }
        if results:
            attrs["winner"] = results[0].rider
            attrs["winner_team"] = results[0].team
            attrs["winning_time"] = results[0].time
        return attrs


class RiderStandingsSensor(RacingEntity, SensorEntity):
    """Championship leader, with the whole table in attributes."""

    _attr_translation_key = "rider_standings"
    _attr_icon = "mdi:podium-gold"

    def __init__(self, coordinator: RacingCoordinator) -> None:
        super().__init__(coordinator, "rider_standings")

    @property
    def native_value(self) -> str | None:
        rows = self.series.rider_standings
        return rows[0].name if rows else "Unavailable"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        rows = self.series.rider_standings
        attrs: dict[str, Any] = {
            "season": self.series.season,
            "standings": [row.as_dict() for row in rows],
        }
        if rows:
            attrs["leader"] = rows[0].name
            attrs["leader_points"] = rows[0].points
            attrs["leader_team"] = rows[0].team
        if len(rows) > 1 and rows[0].points is not None and rows[1].points is not None:
            attrs["lead_margin"] = round(rows[0].points - rows[1].points, 1)
            attrs["runner_up"] = rows[1].name
        return attrs


class TeamStandingsSensor(RacingEntity, SensorEntity):
    """Leading team or constructor."""

    _attr_translation_key = "team_standings"
    _attr_icon = "mdi:account-group"

    def __init__(self, coordinator: RacingCoordinator) -> None:
        super().__init__(coordinator, "team_standings")

    @property
    def available(self) -> bool:
        return super().available and bool(self.series.team_standings)

    @property
    def native_value(self) -> str | None:
        rows = self.series.team_standings
        return rows[0].name if rows else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        rows = self.series.team_standings
        return {
            "season": self.series.season,
            "standings": [row.as_dict() for row in rows],
            "leader_points": rows[0].points if rows else None,
        }


class SeasonRoundSensor(RacingEntity, SensorEntity):
    """How far through the season we are."""

    _attr_translation_key = "season_round"
    _attr_icon = "mdi:calendar-range"

    def __init__(self, coordinator: RacingCoordinator) -> None:
        super().__init__(coordinator, "season_round")

    @property
    def native_value(self) -> int | None:
        completed = [e for e in self.series.events if e.finished]
        return len(completed)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        events = self.series.events
        total = len(events)
        completed = len([e for e in events if e.finished])
        return {
            "season": self.series.season,
            "total_rounds": total,
            "rounds_completed": completed,
            "rounds_remaining": max(total - completed, 0),
            "progress_percent": round(completed / total * 100) if total else 0,
            "calendar": [
                {
                    "round": event.round_number,
                    "name": event.name,
                    "circuit": event.circuit,
                    "country": event.country,
                    "date": event.start.isoformat() if event.start else None,
                    "finished": event.finished,
                }
                for event in events
            ],
            "badge": self.series.badge,
            "logo": self.series.logo,
            "fanart": self.series.fanart,
        }


class FavouriteRiderSensor(RacingEntity, SensorEntity):
    """Championship position of the rider you actually care about."""

    _attr_translation_key = "favourite_rider"
    _attr_icon = "mdi:star"

    def __init__(self, coordinator: RacingCoordinator) -> None:
        super().__init__(coordinator, "favourite_rider")
        self._needle = (
            coordinator.entry.options.get(CONF_FAVOURITE_RIDER, "").strip().lower()
        )

    def _match(self, rows) -> Any:
        for row in rows:
            if self._needle in (getattr(row, "name", None) or "").lower():
                return row
            if self._needle in (getattr(row, "rider", None) or "").lower():
                return row
        return None

    @property
    def native_value(self) -> int | None:
        row = self._match(self.series.rider_standings)
        return row.position if row else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        standing = self._match(self.series.rider_standings)
        result = self._match(self.series.last_results)
        leader = self.series.rider_standings[0] if self.series.rider_standings else None
        attrs: dict[str, Any] = {
            "rider": standing.name if standing else self._needle.title(),
            "points": standing.points if standing else None,
            "team": standing.team if standing else None,
            "last_race_position": result.position if result else None,
            "last_race_time": result.time if result else None,
        }
        if standing and leader and standing.points is not None and leader.points is not None:
            attrs["points_behind_leader"] = round(leader.points - standing.points, 1)
        return attrs
