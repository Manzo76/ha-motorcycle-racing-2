"""Shared plumbing for Motorcycle Racing data providers."""

from __future__ import annotations

import asyncio
import logging
import urllib.parse
from datetime import datetime, timezone
from typing import Any

import aiohttp

from .models import SeriesData

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=25)

# Some upstream endpoints sit behind a WAF that rejects bare client libraries.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-GB,en;q=0.9",
}


class ProviderError(Exception):
    """Raised when a provider cannot produce usable data."""


class AuthError(ProviderError):
    """Raised when the upstream rejected our credentials."""


class RacingProvider:
    """Base class for a source of motorcycle racing data."""

    attribution: str = ""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def async_get_data(self) -> SeriesData:
        """Return a fully populated :class:`SeriesData`."""
        raise NotImplementedError

    async def _get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        """GET a URL and return decoded JSON, with one retry on transient errors."""
        last_error: Exception | None = None
        for attempt in (1, 2):
            try:
                async with self._session.get(
                    url,
                    params=params,
                    headers=BROWSER_HEADERS,
                    timeout=REQUEST_TIMEOUT,
                ) as resp:
                    if resp.status in (401, 403):
                        raise AuthError(f"{url} returned {resp.status}")
                    if resp.status == 429:
                        raise ProviderError(f"Rate limited by {url}")
                    resp.raise_for_status()
                    # TheSportsDB serves JSON as text/plain on some endpoints.
                    return await resp.json(content_type=None)
            except AuthError:
                raise
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
                last_error = err
                if attempt == 1:
                    await asyncio.sleep(1.5)
        raise ProviderError(f"Failed to fetch {url}: {last_error}") from last_error


async def fetch_wikipedia_thumbnail(session: aiohttp.ClientSession, title: str) -> str | None:
    """Best-effort lookup of a Wikipedia page's lead image, for circuit layouts.

    Used to give the dashboard card a "last circuit / next circuit" picture
    without shipping (and having to keep fresh) our own image library. A
    single attempt, no retries: a 404 here just means "no article by that
    name", which is not worth the base client's retry-with-backoff treatment.
    """
    if not title:
        return None
    encoded = urllib.parse.quote(title.strip().replace(" ", "_"))
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"
    try:
        async with session.get(
            url, headers=BROWSER_HEADERS, timeout=REQUEST_TIMEOUT
        ) as resp:
            if resp.status != 200:
                return None
            payload = await resp.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
        _LOGGER.debug("Wikipedia lookup failed for %r: %s", title, err)
        return None
    if not isinstance(payload, dict):
        return None
    thumb = payload.get("thumbnail") or {}
    original = payload.get("originalimage") or {}
    return thumb.get("source") or original.get("source")


def classify_session(name: str) -> str:
    """Map a free-text session name onto our session kinds."""
    lowered = (name or "").strip().lower()
    if not lowered:
        return "other"
    if "sprint" in lowered or lowered.startswith("spr"):
        return "sprint"
    if "warm" in lowered:
        return "warmup"
    if "test" in lowered:
        return "test"
    if lowered.startswith("q") or "qualif" in lowered or "superpole" in lowered:
        # "Superpole Race" is a race, not qualifying.
        return "race" if "race" in lowered else "qualifying"
    if lowered.startswith(("fp", "p", "pr")) or "practice" in lowered:
        return "practice"
    if lowered.startswith("rac") or "race" in lowered or "grand prix" in lowered:
        return "race"
    return "other"


def parse_dt(value: str | None) -> datetime | None:
    """Parse the assorted date formats these APIs return, always as aware UTC."""
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    for fmt in (None, "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            parsed = (
                datetime.fromisoformat(text)
                if fmt is None
                else datetime.strptime(text, fmt)
            )
        except (ValueError, TypeError):
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    _LOGGER.debug("Could not parse datetime %r", value)
    return None


def to_int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def to_float(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None
