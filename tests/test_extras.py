"""Offline checks for the v2 data layer (Wikipedia tables, RSS, TV list). No network."""

import asyncio
import importlib
import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "motorcycle_racing"
for name, path in (("mr", ROOT), ("mr.api", ROOT / "api")):
    module = types.ModuleType(name)
    module.__path__ = [str(path)]
    sys.modules[name] = module

wt = importlib.import_module("mr.api.wikitable")
ex = importlib.import_module("mr.api.extras")

failures = []


def check(label, got, want):
    if got != want:
        failures.append(f"{label}: expected {want!r}, got {got!r}")


FLAG = '<span class="flagicon"><span class="mw-image-border"><a href="/wiki/Italy" title="Italy"><img alt="Italy" src="//x/y.png"></a></span></span> '


def table(rows):
    head = (
        "<tr><th>Team</th><th>Constructor</th><th>Motorcycle</th>"
        "<th><style>.mw-parser-output .tooltip-dotted{border-bottom:1px dotted}</style>No.</th><th>Rider</th>%s</tr>"
    )
    return head, rows


def html_2026():
    return (
        '<table class="wikitable"><tr><th>Team</th><th>Constructor</th><th>Motorcycle</th>'
        '<th><style>.a{x:y}</style>No.</th><th>Rider</th><th>Rounds</th></tr>'
        f'<tr><td rowspan="2">{FLAG}<a href="/wiki/Aprilia_Racing" title="Aprilia Racing">Aprilia Racing</a>\n</td>'
        '<th rowspan="3"><a href="/wiki/Aprilia">Aprilia</a></th><td rowspan="3">RS-GP26</td>'
        f'<td>72</td><td>{FLAG}<a href="/wiki/Marco_Bezzecchi">Marco Bezzecchi</a><sup>[4]</sup></td><td>1–22</td></tr>'
        f'<tr><td>89</td><td>{FLAG}<a href="/wiki/Jorge_Mart%C3%ADn">Jorge Martín</a></td><td>1–13</td></tr>'
        f'<tr><td>{FLAG}<a href="/wiki/Trackhouse_MotoGP_Team">Trackhouse</a></td><td>25</td>'
        f'<td>{FLAG}Raúl Fernández</td><td>1–22</td></tr>'
        f'<tr><td>{FLAG}Ducati Lenovo Team</td><th>Ducati</th><td>GP26</td><td>63</td><td>{FLAG}Francesco Bagnaia</td><td>1–22</td></tr>'
        f'<tr><td>{FLAG}Ducati Lenovo Team</td><th>Ducati</th><td>GP26</td><td>99</td><td>{FLAG}Fill In Rider</td><td>5</td></tr>'
        "</table>"
    )


def html_2027():
    return (
        '<table class="wikitable"><tr><th>Team</th><th>Constructor</th><th>Motorcycle</th>'
        '<th><style>.a{x:y}</style>No.</th><th>Rider</th></tr>'
        f'<tr><td rowspan="2">{FLAG}<a href="/wiki/Aprilia_Racing">Aprilia Racing</a></td>'
        '<th rowspan="2">Aprilia</th><td rowspan="2">RS-GP27</td>'
        f'<td>63</td><td>{FLAG}<a href="/wiki/Francesco_Bagnaia">Francesco Bagnaia</a><sup>[3]</sup></td></tr>'
        f'<tr><td>72</td><td>{FLAG}Marco Bezzecchi</td></tr>'
        f'<tr><td>{FLAG}Trackhouse</td><th>Aprilia</th><td>RS-GP27</td><td>25</td><td>{FLAG}Raul Fernandez</td></tr>'
        f'<tr><td>{FLAG}Ducati Lenovo Team</td><th>Ducati</th><td>TBA</td><td>TBA</td><td>None</td></tr>'
        f'<tr><td>{FLAG}Ducati Lenovo Team</td><th>Ducati</th><td>GP27</td><td>37</td><td>{FLAG}Pedro Acosta</td></tr>'
        "</table>"
    )


prev = wt.parse_entry_list(html_2026())
nxt = wt.parse_entry_list(html_2027())
check("2026 rider count", len(prev), 5)
check("rowspan team carried", prev[1].team, "Aprilia Racing")
check("rowspan constructor carried", prev[1].constructor, "Aprilia")
check("rowspan bike carried", prev[1].bike, "RS-GP26")
check("team link", prev[0].team_title, "Aprilia Racing")
check("citation stripped", prev[0].rider, "Marco Bezzecchi")
check("number column despite <style>", prev[0].number, "72")
check("rounds counted", prev[0].rounds, 22)
check("rounds 1-13", prev[1].rounds, 13)
check("rider link decoded", prev[1].rider_title, "Jorge Martín")
check("2027 skips TBA/None", [e.rider for e in nxt], ["Francesco Bagnaia", "Marco Bezzecchi", "Raul Fernandez", "Pedro Acosta"])
check("count_rounds split", wt.count_rounds("1–6, 9–13"), 11)
check("count_rounds none", wt.count_rounds(""), None)

moves = wt.compute_moves(prev, nxt)
kinds = {(m["kind"], m["rider"]): m for m in moves}
check("bagnaia moves", kinds[("move", "Francesco Bagnaia")]["from"], "Ducati Lenovo Team")
check("bagnaia moves to", kinds[("move", "Francesco Bagnaia")]["to"], "Aprilia Racing")
check("acosta is new", ("new", "Pedro Acosta") in kinds, True)
check("accent-insensitive match, no false move", ("move", "Raul Fernandez") in kinds or ("new", "Raul Fernandez") in kinds, False)
check("unchanged rider not listed", ("move", "Marco Bezzecchi") in kinds, False)
check("martin out", ("out", "Jorge Martín") in kinds, True)
check("one-off replacement ignored", ("out", "Fill In Rider") in kinds, False)

# infobox
box = (
    '<table class="infobox"><tr><th colspan="2">Team</th></tr>'
    '<tr><th scope="row">Base</th><td>Noale, Italy</td></tr>'
    '<tr><th scope="row">Team principal</th><td>Paolo Bonora</td></tr>'
    '<tr><th scope="row">Sponsors</th><td>Red Bull, Pirelli</td></tr>'
    '<tr><th scope="row">Website</th><td>x</td></tr></table>'
)
facts = wt.parse_infobox(box)
check("infobox base", facts.get("base"), "Noale, Italy")
check("infobox sponsors", facts.get("sponsors"), "Red Bull, Pirelli")
check("infobox ignores others", "website" in facts, False)

# RSS
RSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>
<item><title>Marc Marquez wins sprint</title><link>https://www.crash.net/motogp/news/1</link>
<pubDate>Sat, 24 Oct 2026 05:30:20 +0100</pubDate><description>&lt;p&gt;Great &amp;amp; fast sprint.&lt;/p&gt;</description><category>MotoGP</category></item>
<item><title>Moto2: rookie signs for 2027 with Italtrans</title><link>https://www.crash.net/motogp/news/2</link>
<pubDate>
 Fri, 23 Oct 2026 14:07:19 +0100
</pubDate><description>Moto2 rider market</description></item>
<item><title>No link here</title><link>javascript:x</link></item></channel></rss>"""
items = ex.parse_rss(RSS)
check("rss count", len(items), 2)
check("rss newest first", items[0]["title"], "Marc Marquez wins sprint")
check("rss summary cleaned", items[0]["summary"], "Great & fast sprint.")
check("rss date with whitespace", items[1]["published"], "2026-10-23T13:07:19+00:00")
check("rss rejects non-http link", all(i["link"].startswith("http") for i in items), True)


class FakeExtras(ex.Extras):
    def __init__(self):
        super().__init__(None, ROOT / "data")
        self.calls = []

    async def _get_text(self, url, params=None):
        self.calls.append((url, (params or {}).get("page")))
        if "rss" in url:
            return RSS
        if params and params.get("action") == "parse":
            page = params["page"]
            html = html_2026() if "2026" in page else html_2027() if "2027" in page else None
            return json.dumps({"parse": {"text": html}}) if html else None
        return None


fx = FakeExtras()
news = asyncio.run(fx.async_news("motogp"))
check("news items", len(news["items"]), 2)
moto2 = asyncio.run(fx.async_news("moto2"))
check("moto2 filter then fallback note", bool(moto2["note"]), True)  # only 1 match -> fallback
tr = asyncio.run(fx.async_transfers("motogp", "2026"))
check("transfers from wikipedia", any(m["kind"] == "move" for m in tr["moves"]), True)
check("transfers year", tr["year"], 2027)
check("market headline picked", [h["title"] for h in tr["headlines"]], ["Moto2: rookie signs for 2027 with Italtrans"])
# headline outside 150 days is dropped
old = asyncio.run(FakeExtras().async_transfers("worldsbk", "2026"))
check("worldsbk has no wiki moves", old["moves"], [])
before = len(fx.calls)
asyncio.run(fx.async_transfers("motogp", "2026"))
check("cached (no refetch)", len(fx.calls), before)
teams = asyncio.run(fx.async_teams("motogp", "2026"))
names = {t["name"]: [r["name"] for r in t["riders"]] for t in teams["teams"]}
check("teams grouped", names["Aprilia Racing"], ["Marco Bezzecchi", "Jorge Martín"])
check("teams drop replacement", "Fill In Rider" in names.get("Ducati Lenovo Team", []), False)

# TV list
tv = asyncio.run(fx.async_tv("gb"))
check("tv country", tv["country"], "GB")
check("tv uk bsb has free-to-air", any("Quest" in c for c in tv["channels"]["bsb"]), True)
check("tv uk motogp", tv["channels"]["gp"][0].startswith("TNT Sports"), True)
check("tv listing sorted", [c["name"] for c in tv["countries"]] == sorted(c["name"] for c in tv["countries"]), True)
tv2 = asyncio.run(fx.async_tv("zz"))
check("tv unknown country", (tv2["country"], tv2["channels"]), (None, {}))
check("tv fallback present", "gp" in tv2["fallback"], True)
data = json.loads((ROOT / "data" / "broadcasters.json").read_text(encoding="utf-8"))
check("tv dataset has retrieval date", bool(data["retrieved"]), True)
check("tv every country has channels", all(v["channels"] for v in data["countries"].values()), True)


# --- verbatim slice of the real 2027 MotoGP entry list (Wikipedia, 2026-10-24) ---
real = wt.parse_entry_list((Path(__file__).parent / "fixtures" / "wiki_2027_motogp_table.html").read_text(encoding="utf-8"))
check("real: rider count", len(real), 12)
check("real: first rider", (real[0].rider, real[0].number, real[0].team), ("Francesco Bagnaia", "63", "Aprilia Racing"))
check("real: team link not the flag", real[0].team_title, "Aprilia Racing")
check("real: rider link not the flag", real[0].rider_title, "Francesco Bagnaia")
check("real: rowspan constructor", real[1].constructor, "Aprilia")
check("real: redlink bike text", [e.bike for e in real if e.rider == "Johann Zarco"], ["RC214V"])
check("real: TBA number kept as text", [e.number for e in real if e.rider == "Daniel Holgado"], ["TBA"])
check("real: accents", [e.rider for e in real if "Fern" in e.rider], ["Ra\u00fal Fern\u00e1ndez"])
check("real: rider link with parentheses", [e.rider_title for e in real if "Fern" in e.rider], ["Ra\u00fal Fern\u00e1ndez (motorcyclist)"])
check("real: nested spans", [e.rider for e in real if "Giannantonio" in e.rider], ["Fabio Di Giannantonio"])
check("real: two-name team cell", [e.team for e in real if e.rider == "Johann Zarco"], ["Castrol Honda LCR Pro Honda LCR"])
check("real: no citation text", any("[" in e.rider for e in real), False)

if failures:
    print("FAILURES:")
    for line in failures:
        print("  -", line)
    sys.exit(1)
print("All extras checks passed.")
