"""Binary sensors for the Motorcycle Racing integration."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
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
    coordinator = entry.runtime_data
    async_add_entities(
        [
            RaceWeekendBinarySensor(coordinator),
            SessionLiveBinarySensor(coordinator),
            RaceDayBinarySensor(coordinator),
        ]
    )


class RaceWeekendBinarySensor(RacingEntity, BinarySensorEntity):
    """On from the Thursday of a race weekend until the flag drops on Sunday."""

    _attr_translation_key = "race_weekend"
    _attr_icon = "mdi:calendar-star"

    def __init__(self, coordinator: RacingCoordinator) -> None:
        super().__init__(coordinator, "race_weekend")

    @property
    def is_on(self) -> bool:
        return RacingCoordinator.is_race_weekend(self.series)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        event = self.series.next_event
        return {
            "event": event.name if event else None,
            "circuit": event.circuit if event else None,
            "round": event.round_number if event else None,
        }


class SessionLiveBinarySensor(RacingEntity, BinarySensorEntity):
    """On while a session is believed to be running."""

    _attr_translation_key = "session_live"
    _attr_icon = "mdi:broadcast"

    def __init__(self, coordinator: RacingCoordinator) -> None:
        super().__init__(coordinator, "session_live")

    @property
    def is_on(self) -> bool:
        session = self.series.live_session
        if session:
            return True
        upcoming = self.series.next_session
        if upcoming and upcoming.start and upcoming.end:
            now = datetime.now(timezone.utc)
            return upcoming.start <= now <= upcoming.end
        return False

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        session = self.series.live_session or self.series.next_session
        if not session:
            return {}
        return {
            "session": session.name,
            "kind": session.kind,
            "start": session.start.isoformat() if session.start else None,
            "weather": session.weather or None,
        }


class RaceDayBinarySensor(RacingEntity, BinarySensorEntity):
    """On during the calendar day of the main race."""

    _attr_translation_key = "race_day"
    _attr_icon = "mdi:flag-checkered"

    def __init__(self, coordinator: RacingCoordinator) -> None:
        super().__init__(coordinator, "race_day")

    @property
    def is_on(self) -> bool:
        event = self.series.next_event
        if not event:
            return False
        race = event.race_session
        start = race.start if race else event.start
        if not start:
            return False
        now = datetime.now(timezone.utc)
        return start.date() == now.date() or (
            start <= now <= start + timedelta(hours=3)
        )
