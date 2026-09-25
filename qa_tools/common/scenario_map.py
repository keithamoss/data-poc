"""The scenario map - which scenario is which, and where to look at it
(REQ-GEN-045).

WHAT IT IS FOR, in Keith's own framing: showing this to somebody, a
deliberately broken supply should read as a demonstration rather than
as a defect nobody got round to. The dashboard deliberately carries no
scenario label on the injected runs - "this is still just a proof of
concept", and the red IS the point - so the map is what tells a viewer
which red was on purpose.

TWO SOURCES, AND NEITHER IS HAND-MAINTAINED.

  The REGISTER (plans/supply-model.md, read by
  qa_tools/common/scenarios.py) says what each scenario IS and what it
  is meant to demonstrate. It is prose, reviewed by Keith as prose,
  and it is the authority on meaning.

  The GENERATOR'S OWN RECORD says where each one actually LANDED -
  which dataset, which supplies, which period. Only the generator
  knows, because a seeded regeneration moves things and a map written
  by hand drifts the first time it does.

The map is the join. Criterion 2 forbids anyone maintaining it, which
is why neither half is authored here.

COORDINATES ONLY, NEVER A LINK (criterion 5). The generator knows the
dataset, the supplies, the period and the as-of date; it does not, and
should not, know the dashboard's routing scheme. Emitting URLs here
would couple the two and break silently the next time a route changes -
so the dashboard constructs the link from these coordinates
(REQ-DASH-046), and this file would still be correct if there were no
dashboard at all.

MARKDOWN, COMMITTED (criterion 4). Anything reading the map reads a
committed file and never touches data/ - which is what lets the
dashboard build render it under the standing rule that CI opens no
data. The generator's record lives under data/ and only the generator
reads it.

NOTHING IS INJECTED YET. REQ-GEN-044 is the requirement that places
scenarios into the generated history and writes the record, and it is
not built - so every entry currently renders as criterion 6's "no
generated data behind it". That is the honest state rather than a
placeholder, and the map fills in on its own the moment the record
exists.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

from qa_tools.common import scenarios as scenarios_mod

ROOT = Path(__file__).resolve().parent.parent.parent

#: Where the generator records what it placed (REQ-GEN-044 criterion 7).
#: Under data/, because it is generator bookkeeping - the same place
#: data/generator_bookkeeping.json lives, and for the same reason: the
#: pipeline may not read either.
PLACEMENTS_PATH = ROOT / "data" / "scenario_placements.json"

#: The committed map itself.
MAP_PATH = ROOT / "SCENARIOS.md"


@dataclass(frozen=True)
class Placement:
    """Where one scenario actually landed."""

    scenario_id: str
    dataset: str
    supplies: tuple[str, ...]
    period: str
    as_of: str

    @classmethod
    def of(cls, record: Mapping) -> "Placement":
        return cls(
            scenario_id=str(record.get("scenario_id") or ""),
            dataset=str(record.get("dataset") or ""),
            supplies=tuple(record.get("supplies") or ()),
            period=str(record.get("period") or ""),
            as_of=str(record.get("as_of") or ""))

    @property
    def is_complete(self) -> bool:
        """A HALF-RECORDED PLACEMENT IS NOT A COORDINATE. Criterion 6
        says a scenario with no generated data behind it says so
        rather than emitting a coordinate that leads nowhere, and a
        record naming a dataset but no period leads exactly nowhere."""
        return bool(self.dataset and self.period and self.as_of)


def read_placements(path: Path | str | None = None) -> dict[str, Placement]:
    """What the generator recorded, keyed by scenario id.

    An ABSENT file is the ordinary state today, not an error: nothing
    injects yet. A malformed one is also empty rather than fatal -
    this builds a document, and a document that cannot be built stops
    a regeneration that had nothing else wrong with it.
    """
    source = Path(path or PLACEMENTS_PATH)
    if not source.is_file():
        return {}
    try:
        raw = json.loads(source.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    records = raw.get("placements") if isinstance(raw, dict) else raw
    out = {}
    for record in records or ():
        if isinstance(record, Mapping):
            placement = Placement.of(record)
            if placement.scenario_id:
                out[placement.scenario_id] = placement
    return out


_INTRO = """<!--
GENERATED FILE - do not edit by hand.

Rebuilt by `mothman scenarios map`, and in the same act as the
synthetic history itself, so the two cannot disagree (REQ-GEN-045
criterion 3). Two sources, neither hand-maintained: the test scenario
register in plans/supply-model.md says what each scenario is, and the
generator's own record says where it landed.
-->

# Scenario map

The synthetic history this proof of concept runs on has deliberately
awkward supplies in it - a delivery that arrives in the wrong order, a
file nothing can place, a table that will not load. They are there on
purpose, so the model can be seen working on real pages rather than
only in a green test run.

The dashboard does not label them. A supply that reads red reads red,
the same as a real one would, because that is the point. **This is the
list that says which red was on purpose, and where to look at it.**

Each entry gives coordinates - the dataset, the supplies, the period,
and the date to set the as-of picker to - and never a link. The
generator knows where a scenario landed; it does not know how the
dashboard addresses its pages, and a URL written here would break
silently the next time a route changed.

A scenario marked **not injected** has no generated data behind it.
Either it is a pure unit test with nothing to look at, or it is meant
for injection and has not been placed yet.
"""

_NO_DATA = "not injected - nothing to look at yet"
_UNIT_ONLY = "unit test - no generated data, nothing to navigate to"


def _sentence(text: str) -> str:
    """The register writes these as the tail of a sentence beginning
    "**Expect**:", so they arrive lowercase. Capitalised here rather
    than in the register, because the register reads correctly as it
    stands and this document reads them as statements of their own."""
    text = text.strip()
    return text[:1].upper() + text[1:] if text else text


def _entry(scenario: scenarios_mod.Scenario, placement: Placement | None) -> list[str]:
    lines = [f"### {scenario.id} - {scenario.title}", ""]
    # CRITERION 9: what it is meant to demonstrate, not only where it
    # landed. A coordinate with no meaning beside it sends a reader to
    # a page and tells them nothing about why they are there.
    if scenario.expect:
        lines += [f"**What it demonstrates.** {_sentence(scenario.expect)}", ""]
    elif scenario.body:
        # A few entries - TS-3 is the family heading for four sub-tests
        # - carry no "Expect" of their own. Their own narrative is
        # what they have, and an entry with nothing under its heading
        # reads as a gap in the register rather than as a heading.
        lines += [_sentence(scenario.body), ""]
    if scenario.breaks_as:
        lines += [f"**What it would look like if the rule were wrong.** "
                   f"{_sentence(scenario.breaks_as)}", ""]
    if scenario.config:
        lines += [f"*{scenario.config}*", ""]

    if placement is not None and placement.is_complete:
        supplies = ", ".join(f"`{s}`" for s in placement.supplies) or "—"
        lines += [
            "| Where to look | |",
            "|---|---|",
            f"| Dataset | {placement.dataset} |",
            f"| Supplies | {supplies} |",
            f"| Period | {placement.period} |",
            f"| Set the as-of date to | {placement.as_of} |",
            "",
        ]
    elif scenario.is_injected:
        lines += [f"**{_NO_DATA}**", ""]
    else:
        lines += [f"*{_UNIT_ONLY}*", ""]
    return lines


#: The machine-readable copy, inside the markdown rather than beside
#: it (REQ-DASH-046 criterion 5). ONE COMMITTED FILE, still markdown,
#: still self-explanatory to a person - an HTML comment renders as
#: nothing on GitHub - and the dashboard reads exact data rather than
#: re-parsing prose it would then have to keep in step.
#:
#: The alternative was a JSON sidecar, rejected because two files that
#: must agree is the shape this project keeps removing: one staleness
#: gate cannot cover both, and the pair drifts the first time somebody
#: regenerates one.
_DATA_OPEN = "<!-- scenario-map-data\n"
_DATA_CLOSE = "\n-->"


def _data_block(scenarios: Iterable[scenarios_mod.Scenario],
                 placements: Mapping[str, Placement]) -> str:
    entries = []
    for scenario in scenarios:
        placement = placements.get(scenario.id)
        entry = {
            "id": scenario.id, "mode": scenario.mode, "title": scenario.title,
            "section": scenario.section,
            "demonstrates": _sentence(scenario.expect or scenario.body or ""),
            "breaksAs": _sentence(scenario.breaks_as) if scenario.breaks_as else None,
            "config": scenario.config,
            # COORDINATES, NEVER A LINK (criterion 5 of REQ-GEN-045 and
            # criterion 3 of REQ-DASH-046). The dashboard builds the
            # link from these; nothing here knows a route.
            "coordinates": None,
        }
        if placement is not None and placement.is_complete:
            entry["coordinates"] = {
                "dataset": placement.dataset,
                "supplies": list(placement.supplies),
                "period": placement.period,
                "asOf": placement.as_of,
            }
        entries.append(entry)
    return _DATA_OPEN + json.dumps({"scenarios": entries}, indent=1) + _DATA_CLOSE


def read_map_data(map_path: Path | str | None = None) -> list[dict]:
    """The structured entries embedded in the committed map.

    Read by the dashboard build, which may open no data/ - so this
    reads the COMMITTED markdown and nothing else. A map with no data
    block returns nothing rather than raising, because the document is
    still a document without it.
    """
    text = Path(map_path or MAP_PATH).read_text()
    start = text.find(_DATA_OPEN)
    if start < 0:
        return []
    end = text.find(_DATA_CLOSE, start)
    if end < 0:
        return []
    try:
        raw = json.loads(text[start + len(_DATA_OPEN):end])
    except json.JSONDecodeError:
        return []
    return list(raw.get("scenarios") or ())


def build_map(scenarios: Iterable[scenarios_mod.Scenario],
               placements: Mapping[str, Placement]) -> str:
    """The whole document.

    READS AS A COMPLETE THING ON ITS OWN (criterion 8), with no
    dashboard to render it: a reader opening it on GitHub gets the
    explanation, the scenarios grouped as the register groups them,
    and the coordinates - not a table of ids that only means something
    inside an app.
    """
    scenarios = sorted(scenarios, key=lambda s: s.sort_key)
    injected = [s for s in scenarios if s.is_injected]
    placed = [s for s in injected if (placements.get(s.id) or Placement.of({})).is_complete]

    lines = [
        _INTRO.strip(), "",
        f"**{len(placed)} of {len(injected)} scenarios marked for injection have data "
        f"behind them today.** {len(scenarios)} scenarios are registered in all; the "
        f"rest are unit tests with nothing to look at.", "",
    ]

    by_section: dict[str, list] = {}
    for scenario in scenarios:
        by_section.setdefault(scenario.section or "Other", []).append(scenario)

    for section, entries in by_section.items():
        lines += [f"## {section}", ""]
        for scenario in entries:
            lines += _entry(scenario, placements.get(scenario.id))
    lines += ["", _data_block(scenarios, placements)]
    return "\n".join(lines).rstrip() + "\n"


def write_map(map_path: Path | str | None = None,
               register_path: Path | str | None = None,
               placements_path: Path | str | None = None) -> Path:
    """Rebuild the committed map. Returns the path written."""
    out = Path(map_path or MAP_PATH)
    out.write_text(build_map(scenarios_mod.parse_register(register_path),
                              read_placements(placements_path)))
    return out
