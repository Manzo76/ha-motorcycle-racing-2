"""Tiny, dependency-free Wikipedia table reader.

Home Assistant ships no HTML parser we can rely on, so this uses the standard
library. It understands rowspan/colspan (Wikipedia entry lists lean on them
heavily), ignores <style>, <script>, <sup> (citation marks) and images (flag
icons), and remembers the first wiki link inside each cell.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import unquote


@dataclass(slots=True)
class Cell:
    text: str = ""
    link: str | None = None  # wiki article title of the first link, if any
    header: bool = False


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[tuple[Cell, int, int]]]] = []
        self._stack: list[list[list[tuple[Cell, int, int]]]] = []
        self._row: list[tuple[Cell, int, int]] | None = None
        self._cell: Cell | None = None
        self._span = (1, 1)
        self._skip = 0
        self._parts: list[str] = []
        self._table_classes: list[str] = []
        self._in_a = False
        self._a_has_text = False
        self._a_link: str | None = None

    @staticmethod
    def _int(value: str | None) -> int:
        try:
            return max(1, int(re.sub(r"\D", "", value or "") or 1))
        except ValueError:
            return 1

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("style", "script", "sup"):
            self._skip += 1
        elif tag == "table":
            self._stack.append([])
            self._table_classes.append(a.get("class") or "")
        elif tag == "tr" and self._stack:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = Cell(header=tag == "th")
            self._parts = []
            self._span = (self._int(a.get("rowspan")), self._int(a.get("colspan")))
        elif tag == "a" and self._cell is not None and not self._cell.link and not self._skip:
            href = a.get("href") or ""
            if href.startswith("/wiki/") and ":" not in href[6:]:
                self._cell.link = unquote(href[6:]).split("#")[0].replace("_", " ")
                self._a_link = self._cell.link
            self._in_a, self._a_has_text = True, False
        elif tag == "img" and self._in_a and not self._a_has_text and self._cell is not None:
            # A link wrapping a flag/logo picture is not the team or rider article.
            if self._cell.link == self._a_link:
                self._cell.link = None
        elif tag == "br" and self._cell is not None:
            self._parts.append(" | ")

    def handle_endtag(self, tag):
        if tag in ("style", "script", "sup"):
            self._skip = max(0, self._skip - 1)
        elif tag == "a":
            # A link with no visible text (a flag icon) is not the team/rider article.
            if (
                self._in_a
                and not self._a_has_text
                and self._cell is not None
                and self._cell.link == self._a_link
            ):
                self._cell.link = None
            self._in_a, self._a_link = False, None
        elif tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._cell.text = re.sub(r"\s+", " ", "".join(self._parts)).strip()
            self._row.append((self._cell, self._span[0], self._span[1]))
            self._cell = None
        elif tag == "tr" and self._row is not None and self._stack:
            if self._row:
                self._stack[-1].append(self._row)
            self._row = None
        elif tag == "table" and self._stack:
            self.tables.append(self._stack.pop())
            if self._table_classes:
                self._table_classes.pop()

    def handle_data(self, data):
        if self._cell is not None and not self._skip:
            self._parts.append(data)
            if self._in_a and data.strip():
                self._a_has_text = True


def parse_tables(html: str) -> list[list[list[Cell]]]:
    """Return every table as a rectangular grid of Cells (spans expanded)."""
    parser = _TableParser()
    parser.feed(html)
    grids: list[list[list[Cell]]] = []
    for raw in parser.tables:
        grid: list[list[Cell]] = []
        pending: dict[int, tuple[Cell, int]] = {}  # column -> (cell, rows left)
        for raw_row in raw:
            row: list[Cell] = []
            col = 0
            queue = list(raw_row)
            while queue or col in pending:
                if col in pending:
                    cell, left = pending[col]
                    row.append(cell)
                    if left <= 1:
                        del pending[col]
                    else:
                        pending[col] = (cell, left - 1)
                    col += 1
                    continue
                cell, rows, cols = queue.pop(0)
                for _ in range(cols):
                    row.append(cell)
                    if rows > 1:
                        pending[col] = (cell, rows - 1)
                    col += 1
            grid.append(row)
        grids.append(grid)
    return grids


# --------------------------------------------------------------------------
# Entry lists ("Teams and riders")
# --------------------------------------------------------------------------


@dataclass(slots=True)
class Entry:
    team: str
    team_title: str | None
    constructor: str | None
    bike: str | None
    number: str | None
    rider: str
    rider_title: str | None
    rounds: int | None  # how many rounds the rider is listed for; None = all/unknown


_NOT_RIDERS = {"", "tba", "none", "tbc", "tbd", "n/a", "-", "vacant", "to be announced"}


def norm(name: str | None) -> str:
    """Accent- and case-insensitive key for matching names across seasons."""
    text = unicodedata.normalize("NFKD", name or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def count_rounds(text: str | None) -> int | None:
    """"1-6, 9-13" -> 11. Returns None when no round numbers are present."""
    if not text:
        return None
    total = 0
    found = False
    for part in re.split(r"[,&;]", text):
        m = re.search(r"(\d+)\s*[–—\-]\s*(\d+)", part)
        if m:
            found = True
            total += max(0, int(m.group(2)) - int(m.group(1)) + 1)
            continue
        m = re.search(r"\d+", part)
        if m:
            found = True
            total += 1
    return total if found else None


def parse_entry_list(html: str) -> list[Entry]:
    """Find the "Teams and riders" table of a season page and return its rows."""
    for grid in parse_tables(html):
        if not grid:
            continue
        head = [c.text.lower() for c in grid[0]]
        if not any("rider" in h for h in head) or not any(h.endswith("team") or h == "team" or "entrant" in h for h in head):
            continue
        idx = {}
        for i, h in enumerate(head):
            if "rider" in h and "rider" not in idx:
                idx["rider"] = i
            elif h.endswith("no.") or h == "no" or h.endswith("no"):
                idx.setdefault("number", i)
            elif "constructor" in h:
                idx["constructor"] = i
            elif "motorcycle" in h or h == "bike":
                idx["bike"] = i
            elif "rounds" in h:
                idx["rounds"] = i
            elif "team" in h or "entrant" in h:
                idx.setdefault("team", i)
        if "rider" not in idx or "team" not in idx:
            continue
        entries: list[Entry] = []
        for row in grid[1:]:
            if len(row) <= idx["rider"]:
                continue
            rider_cell = row[idx["rider"]]
            rider = rider_cell.text.strip()
            if norm(rider) in _NOT_RIDERS:
                continue
            team_cell = row[idx["team"]]
            # Some teams list two names separated by a line break: use the first.
            team_name = team_cell.text.split(" | ")[0].strip()

            def get(key):
                i = idx.get(key)
                return row[i].text or None if i is not None and i < len(row) else None

            entries.append(
                Entry(
                    team=team_name,
                    team_title=team_cell.link,
                    constructor=get("constructor"),
                    bike=get("bike"),
                    number=get("number"),
                    rider=rider,
                    rider_title=rider_cell.link,
                    rounds=count_rounds(get("rounds")),
                )
            )
        if entries:
            return entries
    return []


# --------------------------------------------------------------------------
# Rider market: compare two seasons
# --------------------------------------------------------------------------


def _full_timers(entries: list[Entry]) -> list[Entry]:
    """Drop one-off replacements: riders listed for under half the longest run."""
    longest = max((e.rounds or 0 for e in entries), default=0)
    if longest <= 0:
        return entries
    return [e for e in entries if e.rounds is None or e.rounds * 2 >= longest]


def compute_moves(previous: list[Entry], upcoming: list[Entry]) -> list[dict]:
    """Rider market between two entry lists.

    kind: "move" (different team), "new" (not on last year's grid) or "out"
    (on last year's grid, missing from the new list - may simply be unannounced).
    """
    prev = {norm(e.rider): e for e in _full_timers(previous)}
    nxt = {norm(e.rider): e for e in upcoming}
    moves: list[dict] = []
    for key, entry in nxt.items():
        old = prev.get(key)
        if old is None:
            moves.append(
                {"kind": "new", "rider": entry.rider, "number": entry.number, "from": None,
                 "to": entry.team, "constructor": entry.constructor}
            )
        elif norm(old.team) != norm(entry.team):
            moves.append(
                {"kind": "move", "rider": entry.rider, "number": entry.number, "from": old.team,
                 "to": entry.team, "constructor": entry.constructor}
            )
    for key, entry in prev.items():
        if key not in nxt:
            moves.append(
                {"kind": "out", "rider": entry.rider, "number": entry.number, "from": entry.team,
                 "to": None, "constructor": entry.constructor}
            )
    order = {"move": 0, "new": 1, "out": 2}
    moves.sort(key=lambda m: (order[m["kind"]], m["rider"]))
    return moves


# --------------------------------------------------------------------------
# Infobox
# --------------------------------------------------------------------------

INFOBOX_KEYS = (
    "base", "headquarters", "founded", "team principal", "principal", "manager",
    "team manager", "sponsors", "sponsor", "title sponsor", "technical partners",
    "constructor", "motorcycle", "tyres", "riders", "current riders", "debut", "owner",
    "founder", "founders", "national origin", "country",
)


def parse_infobox(html: str) -> dict[str, str]:
    """Pull a handful of labelled facts out of an article's infobox."""
    facts: dict[str, str] = {}
    for grid in parse_tables(html):
        for row in grid:
            if len(row) < 2 or not row[0].header:
                continue
            label = re.sub(r"[^a-z ]", "", row[0].text.lower()).strip()
            value = row[1].text.strip()
            if label in INFOBOX_KEYS and value and label not in facts and len(value) < 300:
                facts[label] = value
    return facts
