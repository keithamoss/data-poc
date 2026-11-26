"""The scenario map's WRITER (REQ-GEN-045; moved into the generator by
REQ-GEN-386 criterion 5): the committed SCENARIOS-<asset>.md, the join of the
register (scenarios/register.py) and where each scenario landed
(scenarios/placements.py). The real pipeline keeps only the map's reader,
qa_tools/common/scenario_map.py's read_map_data and map_path, which the
dashboard build reads.

THE DATA BLOCK'S MARKERS ARE WRITTEN HERE AND READ THERE: the generator may
not import the pipeline, nor the pipeline scenarios/, so each side holds the
two marker strings, and tests/test_scenario_map.py reads back what this writes
through the reader, so the two cannot drift apart unnoticed. The map's path is
the pipeline's (scenario_map.map_path); the caller - the bootstrap or cli/ -
passes it.

What the map is for, from the module it came out of:

The scenario map - which scenario is which, and where to look at it
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
dataset, the supplies, the period and the in-place-on date; it does not, and
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
from pathlib import Path
from typing import Iterable, Mapping

from asset_model.statuses import status_words
from scenarios import register as scenarios_mod
from scenarios.placements import Placement, read_placements

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
only in a passing test run.

The dashboard does not label them. A supply that is failing reads as
failing, the same as a real one would, because that is the point. **This
is the list that says which problems were on purpose, and where to look
at it.**

Each entry gives coordinates - the dataset, the supplies, the period,
and the date to set the In the warehouse on picker to - and never a link. The
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


def _target_text(target: Mapping) -> str:
    """"Warn on place_of_birth_facility.completeness (450 of 2,078 blank),
    the 2026-09-14 14:00 arrival" - what the rows were built to, never
    what the tools found."""
    moved = [m for m in target.get("moved") or () if m.get("to") == target.get("built_to")]
    rules = ", ".join(
        f"{m['rule']} ({m.get('nulls', m.get('values'))} of {m['of_rows']:,})" for m in moved
    ) or ", ".join(target.get("rules") or ()) or "the seed's choice"
    on = "" if target.get("built_to") == "green" else f" on {rules}"
    # THE STATUS IN WORDS (REQ-DASH-359 criterion 13): 'Warn on ...', never
    # the generator's stored target value.
    built = status_words(target.get("built_to"), "label")
    return f"{built}{on}, the {target.get('date')} {target.get('at')} arrival"


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
            # THE DATE CONTROL'S OWN WORDS, lower case (REQ-DASH-277 criterion 3).
            f'| Set "in the warehouse on" to | {placement.in_place_on} |',
            *[f"| Built to | {_target_text(t)} |" for t in placement.targets],
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
            # WHAT IT DEMONSTRATES, BY REQUIREMENT (REQ-DASH-139 criterion 3).
            "requirements": scenario.requirements,
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
                "inPlaceOn": placement.in_place_on,
            }
            if placement.targets:
                entry["coordinates"]["targets"] = list(placement.targets)
            # THE SUBJECT, BY NAME (REQ-DASH-208 criterion 2).
            entry["coordinates"]["subject"] = placement.subject
        entries.append(entry)
    return _DATA_OPEN + json.dumps({"scenarios": entries}, indent=1) + _DATA_CLOSE


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
        f"behind them today.** {len(scenarios)} scenarios are registered in all"
        + ("; the rest are unit tests with nothing to look at." if len(scenarios) > len(injected)
           else "."), "",
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


def build_for_selected(*, naming_mine: set[str] | frozenset[str],
                       register_path: Path | str | None = None,
                       placements_path: Path | str | None = None) -> str:
    """The selected asset's map: the one register's scenarios that ITS OWN
    asset placed (its placements record), plus those naming one of its
    datasets, with this asset's own placements (REQ-PIPE-352 criterion 3).
    SETTLED by Keith 2026-11-03 (morning report 12 Q5): an unplaced scenario
    naming no dataset is in NEITHER map - the register in plans/supply-model.md
    still holds everything. REJECTED unplaced-in-both, and membership from the
    injections table alone.

    `naming_mine` is the scenarios naming one of this asset's datasets, which
    only the generator's injection table knows
    (generator.scenario_injection.this_assets_scenarios); the caller passes
    it. Required, so no caller gets every asset's scenarios by forgetting
    it."""
    placements = read_placements(placements_path)
    entries = [s for s in scenarios_mod.parse_register(register_path)
               if s.id in naming_mine or s.id in placements]
    return build_map(entries, placements)


def write_map(*, naming_mine: set[str] | frozenset[str],
              map_path: Path | str,
              register_path: Path | str | None = None,
              placements_path: Path | str | None = None) -> Path:
    """Rebuild the selected asset's committed map. Returns the path written.
    `naming_mine` as build_for_selected takes it; `map_path` is the
    pipeline's scenario_map.map_path(), which the caller passes."""
    out = Path(map_path)
    out.write_text(build_for_selected(naming_mine=naming_mine, register_path=register_path,
                                      placements_path=placements_path))
    return out
