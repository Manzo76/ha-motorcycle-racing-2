"""Constants for the Motorcycle Racing integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "motorcycle_racing"
PLATFORMS: Final = ["sensor", "binary_sensor", "calendar"]

MANUFACTURER: Final = "Motorcycle Racing"

CONF_SERIES: Final = "series"
CONF_PROVIDER: Final = "provider"
CONF_LEAGUE_ID: Final = "league_id"
CONF_CATEGORY_UUID: Final = "category_uuid"
CONF_API_KEY: Final = "api_key"
CONF_FAVOURITE_RIDER: Final = "favourite_rider"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_LIVE_SCAN_INTERVAL: Final = "live_scan_interval"
CONF_REGISTER_CARD: Final = "register_card"

PROVIDER_MOTOGP: Final = "motogp"
PROVIDER_SPORTSDB: Final = "sportsdb"

DEFAULT_SCAN_INTERVAL: Final = timedelta(minutes=30)
DEFAULT_LIVE_SCAN_INTERVAL: Final = timedelta(minutes=2)

# TheSportsDB public test key. Works, but is heavily rate limited and shared.
# Supporters get a personal key from https://www.thesportsdb.com/
DEFAULT_SPORTSDB_KEY: Final = "123"

# A race weekend is treated as "active" this many hours either side of a session.
RACE_WEEKEND_WINDOW_HOURS: Final = 96
SESSION_LIVE_MINUTES: Final = 90

ATTRIBUTION_MOTOGP: Final = "Data from motogp.com. Not affiliated with Dorna Sports."
ATTRIBUTION_SPORTSDB: Final = "Data from TheSportsDB.com"

CARD_URL: Final = f"/{DOMAIN}/motorcycle-racing-card.js"
CARD_FILENAME: Final = "motorcycle-racing-card.js"

# Bump this string whenever www/motorcycle-racing-card.js changes. It's the
# only thing that busts the browser's cache of that file - HA always fetches
# an ES module by its exact URL, so an unchanged "?v=" means a browser that
# already loaded the card (even a broken/placeholder version, or a 404 from
# before the file existed) will keep serving that cached copy forever.
CARD_VERSION: Final = "3"

# ---------------------------------------------------------------------------
# Series catalogue
#
# `motogp` provider series use the MotoGP results API and carry a category name
# that is matched against the season's category list at runtime, because the
# category UUIDs change every season.
#
# `sportsdb` provider series use TheSportsDB league IDs, which are stable.
# Users can add any other motorcycle series by picking "Other series" in the
# config flow, which searches TheSportsDB live.
# ---------------------------------------------------------------------------

SERIES_CATALOGUE: Final[dict[str, dict]] = {
    "motogp": {
        "name": "MotoGP",
        "provider": PROVIDER_MOTOGP,
        "category_match": "motogp",
        "accent": "#D6001C",
        "icon": "mdi:motorbike",
    },
    "moto2": {
        "name": "Moto2",
        "provider": PROVIDER_MOTOGP,
        "category_match": "moto2",
        "accent": "#0090D4",
        "icon": "mdi:motorbike",
    },
    "moto3": {
        "name": "Moto3",
        "provider": PROVIDER_MOTOGP,
        "category_match": "moto3",
        "accent": "#00A651",
        "icon": "mdi:motorbike",
    },
    "motoe": {
        "name": "MotoE",
        "provider": PROVIDER_MOTOGP,
        "category_match": "motoe",
        "accent": "#8DC63F",
        "icon": "mdi:lightning-bolt",
    },
    "worldsbk": {
        "name": "WorldSBK",
        "provider": PROVIDER_SPORTSDB,
        "league_id": "4454",
        "accent": "#E4002B",
        "icon": "mdi:motorbike",
    },
    "bsb": {
        "name": "British Superbikes",
        "provider": PROVIDER_SPORTSDB,
        "league_id": "5264",
        "accent": "#00843D",
        "icon": "mdi:motorbike",
    },
    "custom": {
        "name": "Other series",
        "provider": PROVIDER_SPORTSDB,
        "league_id": None,
        "accent": "#FF6B00",
        "icon": "mdi:motorbike",
    },
}

# Session names that count as the main race, in priority order.
RACE_SESSION_KEYS: Final = ("rac", "race", "grand prix", "sprint", "superpole race")
