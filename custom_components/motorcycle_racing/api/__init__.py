"""Data providers for the Motorcycle Racing integration."""

from __future__ import annotations

import aiohttp

from ..const import (
    CONF_API_KEY,
    CONF_LEAGUE_ID,
    CONF_PROVIDER,
    CONF_SERIES,
    DEFAULT_SPORTSDB_KEY,
    PROVIDER_MOTOGP,
    SERIES_CATALOGUE,
)
from .base import AuthError, ProviderError, RacingProvider
from .models import RaceEvent, ResultRow, SeriesData, Session, StandingRow
from .motogp import MotoGPProvider
from .sportsdb import SportsDBProvider

__all__ = [
    "AuthError",
    "ProviderError",
    "RaceEvent",
    "RacingProvider",
    "ResultRow",
    "SeriesData",
    "Session",
    "SportsDBProvider",
    "StandingRow",
    "build_provider",
]


def build_provider(session: aiohttp.ClientSession, config: dict) -> RacingProvider:
    """Create the right provider for a config entry."""
    series_key = config[CONF_SERIES]
    catalogue = SERIES_CATALOGUE.get(series_key, {})
    series_name = config.get("series_name") or catalogue.get("name") or series_key
    provider = config.get(CONF_PROVIDER) or catalogue.get("provider")

    if provider == PROVIDER_MOTOGP:
        return MotoGPProvider(
            session,
            category_match=catalogue.get("category_match", series_key),
            series_key=series_key,
            series_name=series_name,
        )

    league_id = config.get(CONF_LEAGUE_ID) or catalogue.get("league_id")
    if not league_id:
        raise ProviderError(f"No league configured for series {series_key}")
    return SportsDBProvider(
        session,
        league_id=str(league_id),
        series_key=series_key,
        series_name=series_name,
        api_key=config.get(CONF_API_KEY) or DEFAULT_SPORTSDB_KEY,
    )
