# Motorcycle Racing for Home Assistant - Made by Manzo.
# Copyright (c) 2026 Manzo76. All rights reserved. See LICENSE.
"""Update coordinator for the Motorcycle Racing integration."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AuthError, ProviderError, SeriesData, build_provider
from .api.models import ChampionRow, apply_season_state, compose_champions
from .const import (
    CONF_LIVE_SCAN_INTERVAL,
    CONF_SCAN_INTERVAL,
    CONF_SERIES,
    DEFAULT_LIVE_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    HISTORY_REQUEST_DELAY,
    HISTORY_YEARS,
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

        # Past champions: loaded once from disk (and the shipped dataset), then
        # topped up in the background for series whose provider can look them up.
        self._store: Store = Store(hass, 1, f"{DOMAIN}_champions_{self.series_key}")
        self._history: list[ChampionRow] = []
        self._history_checked: set[str] = set()
        self._history_loaded = False
        self._history_season: str | None = None
        self._history_attempt: datetime | None = None
        self._history_task: asyncio.Task | None = None

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

        apply_season_state(data, datetime.now(timezone.utc))
        if not self._history_loaded:
            await self._async_load_history()
        data.champions = compose_champions(self._history, data)
        self._maybe_start_history_backfill(data)
        self._retune_interval(data)
        return data

    # -- champion history -------------------------------------------------

    @property
    def _can_backfill(self) -> bool:
        return hasattr(self._provider, "async_get_champion")

    def _read_shipped_history(self) -> list[dict]:
        path = Path(__file__).parent / "data" / "champions.json"
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as err:
            _LOGGER.debug("No shipped champion data: %s", err)
            return []
        rows = doc.get(self.series_key) if isinstance(doc, dict) else None
        return rows if isinstance(rows, list) else []

    async def _async_load_history(self) -> None:
        """Read saved + shipped champions. Never raises: history is a nice-to-have."""
        rows: dict[str, ChampionRow] = {}
        try:
            shipped = await self.hass.async_add_executor_job(self._read_shipped_history)
            for raw in shipped:
                row = ChampionRow.from_dict(raw) if isinstance(raw, dict) else None
                if row:
                    rows[row.season] = row
            stored = await self._store.async_load()
            if isinstance(stored, dict):
                for raw in stored.get("rows") or []:
                    row = ChampionRow.from_dict(raw) if isinstance(raw, dict) else None
                    if row:
                        rows[row.season] = row
                self._history_checked = {str(y) for y in stored.get("checked") or []}
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Could not load champion history: %s", err)
        self._history = list(rows.values())
        self._history_loaded = True

    def _maybe_start_history_backfill(self, data: SeriesData) -> None:
        """Fetch missing past seasons once at start-up and again on a new season."""
        if not self._can_backfill:
            return
        if self._history_task and not self._history_task.done():
            return
        now = datetime.now(timezone.utc)
        if (
            self._history_season == data.season
            and self._history_attempt is not None
            and now - self._history_attempt < timedelta(days=1)
        ):
            return
        self._history_season = data.season
        self._history_attempt = now
        self._history_task = self.hass.async_create_background_task(
            self._async_backfill_history(), name=f"{DOMAIN}_{self.series_key}_history"
        )

    async def _async_backfill_history(self) -> None:
        try:
            past = await self._provider.async_list_past_seasons(HISTORY_YEARS)
            known = {row.season for row in self._history}
            changed = False
            for year, season_uuid in past:
                if year in known or year in self._history_checked:
                    continue
                try:
                    row = await self._provider.async_get_champion(year, season_uuid)
                except (ProviderError, AuthError) as err:
                    _LOGGER.debug("%s %s champion lookup failed: %s", self.series_name, year, err)
                    continue
                self._history_checked.add(year)
                if row:
                    self._history.append(row)
                changed = True
                await asyncio.sleep(HISTORY_REQUEST_DELAY)
            if changed:
                await self._store.async_save(
                    {
                        "rows": [row.as_dict() for row in self._history],
                        "checked": sorted(self._history_checked),
                    }
                )
                if self.data:
                    self.data.champions = compose_champions(self._history, self.data)
                    self.async_update_listeners()
        except asyncio.CancelledError:
            raise
        except Exception as err:  # noqa: BLE001 - history is optional
            _LOGGER.debug("%s champion history backfill failed: %s", self.series_name, err)

    async def async_event_results(
        self, event_id: str, finished: bool, country_iso: str | None = None
    ) -> dict:
        """Sessions + classifications for one weekend. Finished weekends are cached."""
        cache = self.__dict__.setdefault("_results_cache", {})
        if event_id in cache:
            return cache[event_id]
        getter = getattr(self._provider, "async_get_event_results", None)
        if getter is None:
            return {"event_id": event_id, "sessions": []}
        try:
            result = await getter(event_id, country_iso=country_iso)
        except (ProviderError, AuthError) as err:
            _LOGGER.debug("Event results unavailable for %s: %s", event_id, err)
            return {"event_id": event_id, "sessions": [], "error": str(err)}
        if finished and any(s.get("results") for s in result.get("sessions", [])):
            cache[event_id] = result
        return result

    async def async_shutdown(self) -> None:
        if self._history_task and not self._history_task.done():
            self._history_task.cancel()
        await super().async_shutdown()

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
