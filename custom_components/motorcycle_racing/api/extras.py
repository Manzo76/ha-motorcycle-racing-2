# Motorcycle Racing for Home Assistant - Made by Manzo.
# Copyright (c) 2026 Manzo76. All rights reserved. See LICENSE.
"""News, rider market, team profiles and TV listings for the dashboard panel.

Everything here is fetched live and cached in memory. Every public method
returns a plain dict and never raises for an upstream problem: it returns an
empty result with an ``error`` flag, so one broken source only blanks one tab.
"""

from __future__ import annotations

import asyncio
import html as htmllib
import json
import logging
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import aiohttp

from .records import PAGES, parse_ranking
from .wikitable import Entry, compute_moves, norm, parse_entry_list, parse_infobox

_LOGGER = logging.getLogger(__name__)

TIMEOUT = aiohttp.ClientTimeout(total=25)
HEADERS = {
    "User-Agent": (
        "HA-Motorcycle-Racing/0.7 (+https://github.com/Manzo76/ha-motorcycle-racing-2; "
        "Home Assistant custom integration)"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
}

NEWS_SOURCE = "Crash.net"
NEWS_FEEDS = {
    "gp": "https://www.crash.net/rss/motogp",
    "worldsbk": "https://www.crash.net/rss/wsbk",
    "bsb": "https://www.crash.net/rss/bsb",
}
# which feed / title filter each series uses
SERIES_NEWS = {
    "motogp": ("gp", None),
    "moto2": ("gp", ("moto2",)),
    "moto3": ("gp", ("moto3",)),
    "motoe": ("gp", ("motoe",)),
    "worldsbk": ("worldsbk", None),
    "bsb": ("bsb", None),
}
# Wikipedia season pages that carry a "Teams and riders" table
ENTRY_PAGES = {
    "motogp": "{year} MotoGP World Championship",
    "moto2": "{year} Moto2 World Championship",
    "moto3": "{year} Moto3 World Championship",
}
MARKET_WORDS = re.compile(
    r"\b(2027|2028|sign(?:s|ed|ing)?|contract|extend(?:s|ed)?|extension|line-?up|replac\w+|"
    r"leav\w+|join\w*|switch\w*|mov(?:e|es|ing)|rumou?rs?|seat|promot\w+|set to|confirm\w*)\b",
    re.I,
)

REPO_API = "https://api.github.com/repos/Manzo76/ha-motorcycle-racing-2"
NEWS_TTL = 15 * 60
WIKI_TTL = 6 * 3600


def _plain(text: str | None, limit: int = 220) -> str:
    text = re.sub(r"<[^>]+>", " ", htmllib.unescape(text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        text = text[: limit - 1].rsplit(" ", 1)[0] + "…"
    return text


def _parse_date(text: str | None) -> str | None:
    if not text:
        return None
    try:
        return parsedate_to_datetime(text.strip()).astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None


def parse_rss(xml_text: str) -> list[dict[str, Any]]:
    """Parse an RSS 2.0 feed into news items (newest first)."""
    root = ET.fromstring(xml_text.strip())
    items: list[dict[str, Any]] = []
    for node in root.iter("item"):
        title = _plain(node.findtext("title"), 200)
        link = (node.findtext("link") or "").strip()
        if not title or not link.startswith("http"):
            continue
        items.append(
            {
                "title": title,
                "link": link,
                "published": _parse_date(node.findtext("pubDate")),
                "summary": _plain(node.findtext("description")),
                "category": _plain(node.findtext("category"), 60) or None,
                "source": NEWS_SOURCE,
            }
        )
    items.sort(key=lambda i: i["published"] or "", reverse=True)
    return items


class Extras:
    """Live fetchers shared by every series."""

    def __init__(self, session: aiohttp.ClientSession, data_dir: Path) -> None:
        self._session = session
        self._data_dir = data_dir
        self._cache: dict[str, tuple[float, Any]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._broadcasters: dict[str, Any] | None = None

    # -- plumbing ----------------------------------------------------------

    async def _cached(self, key: str, ttl: float, factory):
        hit = self._cache.get(key)
        if hit and time.monotonic() - hit[0] < ttl:
            return hit[1]
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            hit = self._cache.get(key)
            if hit and time.monotonic() - hit[0] < ttl:
                return hit[1]
            value = await factory()
            # Do not cache failures for long: let the next request retry soon.
            self._cache[key] = (time.monotonic() - (ttl - 120 if value is None else 0), value)
            return value

    async def _get_text(self, url: str, params: dict[str, Any] | None = None) -> str | None:
        try:
            async with self._session.get(url, params=params, headers=HEADERS, timeout=TIMEOUT) as resp:
                if resp.status != 200:
                    _LOGGER.debug("%s returned %s", url, resp.status)
                    return None
                return await resp.text()
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            _LOGGER.debug("Fetch failed for %s: %s", url, err)
            return None

    async def _wiki_html(self, title: str, section0: bool = False) -> str | None:
        params = {
            "action": "parse", "page": title, "prop": "text", "format": "json",
            "formatversion": "2", "redirects": "1", "disabletoc": "1", "disableeditsection": "1",
        }
        if section0:
            params["section"] = "0"
        raw = await self._get_text("https://en.wikipedia.org/w/api.php", params)
        if not raw:
            return None
        try:
            return json.loads(raw).get("parse", {}).get("text")
        except (ValueError, AttributeError):
            return None

    # -- news --------------------------------------------------------------

    async def _feed(self, name: str) -> list[dict[str, Any]] | None:
        async def load():
            raw = await self._get_text(NEWS_FEEDS[name])
            if not raw:
                return None
            try:
                return parse_rss(raw)
            except ET.ParseError as err:
                _LOGGER.debug("Bad RSS from %s: %s", name, err)
                return None

        return await self._cached(f"feed:{name}", NEWS_TTL, load)

    async def async_news(self, series: str, limit: int = 20) -> dict[str, Any]:
        feed, words = SERIES_NEWS.get(series, ("gp", None))
        items = await self._feed(feed)
        if items is None:
            return {"items": [], "error": True, "source": NEWS_SOURCE}
        note = None
        if words:
            def match(item):
                blob = f"{item['title']} {item['summary']}".lower().replace(" ", "")
                return any(w in blob for w in words)

            picked = [i for i in items if match(i)]
            if len(picked) < 3:
                note = "Not much class-specific news right now - showing Grand Prix headlines."
                picked = items
            items = picked
        return {"items": items[:limit], "source": NEWS_SOURCE, "note": note}

    # -- rider market ------------------------------------------------------

    async def _entries(self, series: str, year: int) -> list[Entry] | None:
        template = ENTRY_PAGES.get(series)
        if not template:
            return None

        async def load():
            html = await self._wiki_html(template.format(year=year))
            if not html:
                return None
            # The page is large; parse it off the event loop.
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, parse_entry_list, html)

        return await self._cached(f"entries:{series}:{year}", WIKI_TTL, load)

    async def async_transfers(self, series: str, season: str | None) -> dict[str, Any]:
        try:
            year = int(season or "")
        except ValueError:
            year = datetime.now().year
        out: dict[str, Any] = {"moves": [], "year": year + 1, "headlines": []}
        if series in ENTRY_PAGES:
            prev, nxt = await asyncio.gather(
                self._entries(series, year), self._entries(series, year + 1)
            )
            if prev and nxt:
                out["moves"] = compute_moves(prev, nxt)
                out["entries"] = len(nxt)
                out["source"] = "Wikipedia entry lists"
            else:
                out["error"] = True
        # Rider-market headlines work for every class, including WorldSBK and BSB.
        news = await self.async_news(series, limit=60)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=150)).isoformat()
        out["headlines"] = [
            i for i in news["items"]
            if MARKET_WORDS.search(i["title"]) and (i["published"] or "") >= cutoff
        ][:12]
        out["headline_source"] = NEWS_SOURCE
        return out

    # -- team profile ------------------------------------------------------

    async def async_teams(self, series: str, season: str | None) -> dict[str, Any]:
        """Team list with riders from this season's entry list (Grand Prix classes)."""
        try:
            year = int(season or "")
        except ValueError:
            year = datetime.now().year
        entries = await self._entries(series, year)
        if not entries:
            return {"teams": []}
        teams: dict[str, dict[str, Any]] = {}
        for e in entries:
            t = teams.setdefault(
                e.team,
                {"name": e.team, "title": e.team_title, "constructor": e.constructor,
                 "bike": e.bike, "riders": []},
            )
            if e.rounds is None or e.rounds * 2 >= max((x.rounds or 0 for x in entries), default=0):
                t["riders"].append({"name": e.rider, "number": e.number})
        return {"teams": [t for t in teams.values() if t["riders"]], "year": year}

    async def async_team_profile(self, title: str | None, name: str) -> dict[str, Any]:
        """Summary, picture and infobox facts (base, principal, sponsors...) from Wikipedia."""
        key = norm(title or name)

        async def load():
            page = title
            if not page:
                raw = await self._get_text(
                    "https://en.wikipedia.org/w/api.php",
                    {"action": "opensearch", "search": f"{name} motorcycle racing team",
                     "limit": "1", "format": "json"},
                )
                try:
                    page = json.loads(raw)[1][0] if raw else None
                except (ValueError, IndexError, TypeError):
                    page = None
            if not page:
                return {}
            summary_raw = await self._get_text(
                "https://en.wikipedia.org/api/rest_v1/page/summary/"
                + urllib.parse.quote(page.replace(" ", "_"), safe="")
            )
            profile: dict[str, Any] = {"title": page}
            try:
                summary = json.loads(summary_raw) if summary_raw else {}
            except ValueError:
                summary = {}
            profile["extract"] = _plain(summary.get("extract"), 700)
            profile["image"] = (summary.get("thumbnail") or {}).get("source")
            profile["url"] = ((summary.get("content_urls") or {}).get("desktop") or {}).get("page")
            html = await self._wiki_html(page, section0=True)
            profile["facts"] = parse_infobox(html) if html else {}
            return profile

        profile = await self._cached(f"team:{key}", WIKI_TTL, load)
        return profile or {}

    # -- project stats -----------------------------------------------------

    async def async_repo_stats(self) -> dict[str, Any]:
        """Public GitHub counters (stars, forks, watchers). No user data involved."""
        async def load():
            raw = await self._get_text(REPO_API)
            if not raw:
                return None
            try:
                d = json.loads(raw)
                return {
                    "stars": int(d["stargazers_count"]),
                    "forks": int(d["forks_count"]),
                    "watchers": int(d.get("subscribers_count", 0)),
                }
            except (ValueError, KeyError, TypeError):
                return None

        return await self._cached("repo_stats", 3600, load) or {}

    # -- records -----------------------------------------------------------

    async def _records_page(self, key: str) -> dict[str, list[dict[str, Any]]] | None:
        title, columns = PAGES[key]

        async def load():
            html = await self._wiki_html(title)
            if not html:
                return None
            loop = asyncio.get_running_loop()

            def work():
                return {name: parse_ranking(html, col) for name, col in columns.items()}

            return await loop.run_in_executor(None, work)

        return await self._cached(f"records:{key}", WIKI_TTL, load)

    def _load_lap_records(self) -> dict[str, Any]:
        try:
            return json.loads((self._data_dir / "lap_records.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as err:
            _LOGGER.warning("Could not read lap_records.json: %s", err)
            return {}

    async def async_records(self, series: str) -> dict[str, Any]:
        """All-time record tables. Premier-class lists only exist for MotoGP."""
        keys = ["all"] + (["wins", "poles", "sprints"] if series == "motogp" else [])
        pages = await asyncio.gather(*(self._records_page(k) for k in keys))
        tables: dict[str, list[dict[str, Any]]] = {}
        for key, page in zip(keys, pages):
            if page:
                for name, rows in page.items():
                    if rows:
                        tables[f"{'premier_' if key != 'all' else 'all_'}{name}"] = rows
        out: dict[str, Any] = {"series": series, "tables": tables, "source": "Wikipedia"}
        if not tables:
            out["error"] = True
        if series == "motogp":
            loop = asyncio.get_running_loop()
            out["lap_records"] = await loop.run_in_executor(None, self._load_lap_records)
        return out

    # -- TV guide ----------------------------------------------------------

    def _load_broadcasters(self) -> dict[str, Any]:
        if self._broadcasters is None:
            try:
                self._broadcasters = json.loads(
                    (self._data_dir / "broadcasters.json").read_text(encoding="utf-8")
                )
            except (OSError, ValueError) as err:
                _LOGGER.warning("Could not read broadcasters.json: %s", err)
                self._broadcasters = {"countries": {}}
        return self._broadcasters

    async def async_tv(self, country: str | None) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        data = await loop.run_in_executor(None, self._load_broadcasters)
        countries = data.get("countries", {})
        listing = sorted(({"code": c, "name": v["name"]} for c, v in countries.items()), key=lambda x: x["name"])
        code = (country or "").upper()
        picked = countries.get(code)
        fallback = data.get("fallback", {})
        return {
            "countries": listing,
            "country": code if picked else None,
            "channels": (picked or {}).get("channels", {}),
            "fallback": fallback,
            "retrieved": data.get("retrieved"),
            "sources": data.get("sources", []),
        }
