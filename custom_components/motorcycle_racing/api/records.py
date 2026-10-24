"""All-time records read from Wikipedia list pages (wins, poles, podiums, titles, sprint wins)."""

from __future__ import annotations

import re
from typing import Any

from .wikitable import parse_tables

# page title, {record key: (column name that holds the count, label)}
PAGES: dict[str, tuple[str, dict[str, str]]] = {
    "all": (
        "List of Grand Prix motorcycle racing rider records",
        {"wins": "wins", "poles": "poles", "podiums": "podiums", "titles": "titles",
         "fastest_laps": "fastest laps"},
    ),
    "wins": ("List of 500cc/MotoGP race winners", {"wins": "wins"}),
    "poles": ("List of 500cc/MotoGP polesitters", {"poles": "poles"}),
    "sprints": ("List of MotoGP sprint race winners", {"sprints": "sprint wins"}),
}

_MARKS = re.compile(r"[\*†‡§\[\]\d]+$")


def _clean_name(text: str) -> str:
    return _MARKS.sub("", text or "").strip(" *†‡")


def _count(text: str) -> int | None:
    m = re.search(r"\d[\d,]*", text or "")
    return int(m.group(0).replace(",", "")) if m else None


def parse_ranking(html: str, column: str, limit: int = 10) -> list[dict[str, Any]]:
    """First table with a Rider column and `column`; returns rank/rider/count rows."""
    for grid in parse_tables(html):
        if not grid:
            continue
        head = [c.text.strip().lower() for c in grid[0]]
        if "rider" not in head or column not in head:
            continue
        ri, ci = head.index("rider"), head.index(column)
        out: list[dict[str, Any]] = []
        for row in grid[1:]:
            if len(row) <= max(ri, ci):
                continue
            name = _clean_name(row[ri].text)
            value = _count(row[ci].text)
            if not name or value is None:
                continue
            out.append({"rider": name, "value": value})
            if len(out) >= limit:
                break
        if out:
            for i, item in enumerate(out, start=1):
                item["rank"] = i
            return out
    return []
