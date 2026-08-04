"""Calendar entity for the Motorcycle Racing integration."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import RacingConfigEntry
from .coordinator import RacingCoordinator
from .entity import RacingEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RacingConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([RacingCalendar(entry.runtime_data)])


class RacingCalendar(RacingEntity, CalendarEntity):
    """Every session of the season, ready to drop into a calendar card."""

    _attr_translation_key = "calendar"
    _attr_icon = "mdi:calendar-check"

    def __init__(self, coordinator: RacingCoordinator) -> None:
        super().__init__(coordinator, "calendar")
        self._attr_name = None  # use the device name

    def _build_events(self) -> list[CalendarEvent]:
        events: list[CalendarEvent] = []
        for race in self.series.events:
            sessions = race.sessions or []
            if not sessions and race.start:
                events.append(
                    CalendarEvent(
                        summary=f"{self.coordinator.series_name}: {race.name}",
                        start=race.start,
                        end=race.end or race.start + timedelta(hours=2),
                        location=race.circuit or race.country or "",
                        description=f"Round {race.round_number}" if race.round_number else "",
                    )
                )
                continue
            for session in sessions:
                if not session.start:
                    continue
                events.append(
                    CalendarEvent(
                        summary=f"{self.coordinator.series_name} {session.name} – {race.name}",
                        start=session.start,
                        end=session.end or session.start + timedelta(minutes=45),
                        location=session.circuit or race.circuit or "",
                        description=" · ".join(
                            filter(
                                None,
                                [
                                    f"Round {race.round_number}"
                                    if race.round_number
                                    else None,
                                    race.country,
                                    (session.weather or {}).get("weather"),
                                ],
                            )
                        ),
                    )
                )
        events.sort(key=lambda event: event.start)
        return events

    @property
    def event(self) -> CalendarEvent | None:
        now = datetime.now(timezone.utc)
        for event in self._build_events():
            if event.end >= now:
                return event
        return None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        return [
            event
            for event in self._build_events()
            if event.end >= start_date and event.start <= end_date
        ]
