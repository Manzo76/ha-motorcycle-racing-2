"""Update coordinator for the Motorcycle Racing integration."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AuthError, ProviderError, SeriesData, build_provider
from .const import (
    CONF_LIVE_SCAN_INTERVAL,
    CONF_SCAN_INTERVAL,
    CONF_SERIES,
    DEFAULT_LIVE_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    RACE_WEEKEND_WINDOW_HOURS,
    SERIES_CATALOGUE,
)

_LOGGER = logging.getLogger(__name__)


class RacingCoordinator(DataUpdateCoordinator[SeriesData]):
    """Polls one series and speeds up when there is track action."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self.config = {**entry.data, **entry.options}
        self.series_key: str = self.config[CONF_SERIES]
        catalogue = SERIES_CATALOGUE.get(self.series_key, {})
        self.series_name: str = self.config.get("series_name") or catalogue.get(
            "name", self.series_key
        )
        self.accent: str = catalogue.get("accent", "#FF6B00")

        self._idle_interval = timedelta(
            minutes=self.config.get(
                CONF_SCAN_INTERVAL, int(DEFAULT_SCAN_INTERVAL.total_seconds() // 60)
            )
        )
        self._live_interval = timedelta(
            minutes=self.config.get(
                CONF_LIVE_SCAN_INTERVAL,
                int(DEFAULT_LIVE_SCAN_INTERVAL.total_seconds() // 60),
            )
        )

        self._provider = build_provider(async_get_clientsession(hass), self.config)

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{self.series_key}",
            update_interval=self._idle_interval,
            config_entry=entry,
        )

    @property
    def attribution(self) -> str:
        return self._provider.attribution

    async def _async_update_data(self) -> SeriesData:
        try:
            data = await self._provider.async_get_data()
        except AuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except ProviderError as err:
            raise UpdateFailed(str(err)) from err

        self._retune_interval(data)
        return data

    def _retune_interval(self, data: SeriesData) -> None:
        """Poll quickly during a race weekend, slowly the rest of the time."""
        wanted = self._idle_interval
        if self.is_race_weekend(data):
            wanted = self._live_interval
        if wanted != self.update_interval:
            _LOGGER.debug(
                "%s: switching poll interval to %s", self.series_name, wanted
            )
            self.update_interval = wanted

    @staticmethod
    def is_race_weekend(data: SeriesData | None) -> bool:
        if not data:
            return False
        if data.live_session:
            return True
        now = datetime.now(timezone.utc)
        window = timedelta(hours=RACE_WEEKEND_WINDOW_HOURS)
        event = data.next_event
        if event and event.start and 0 <= (event.start - now).total_seconds() <= window.total_seconds():
            return True
        if event and event.start and event.end and event.start <= now <= event.end:
            return True
        return False
