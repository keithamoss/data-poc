"""mothman scenarios - the test scenario register and the map built
from it (REQ-GEN-045).

ITS OWN GROUP rather than folded into `dashboard` or `pipeline`. The
map is not a dashboard artefact - it is a committed markdown document
that reads on its own, and the dashboard merely renders it - and it is
not a pipeline step either. What it IS about is the scenario register,
which is a thing in its own right that both the generator and the
dashboard read.

READ-ONLY EXCEPT FOR THE MAP. Nothing here opens data/ or a warehouse:
the register is a committed markdown file and the generator's
placement record is read if it happens to exist, so this is safe to
run while editing either.
"""
from __future__ import annotations

import rich_click as click
from rich.console import Console
from rich.table import Table

from generator import public as generator
from qa_tools.common import scenario_map
from scenarios import placements as scenario_placements
from scenarios import register as scenarios

console = Console()


@click.group("scenarios")
def scenarios_group() -> None:
    """The deliberately awkward supplies, and where to look at them."""


@scenarios_group.command("map")
@click.option("--out", "out_path", default=None,
               help="Write somewhere other than the asset's committed SCENARIOS-<asset>.md.")
@click.option("--check", "check", is_flag=True,
              help="Write nothing; fail if the asset's committed SCENARIOS-<asset>.md is out of date.")
def map_command(out_path: str | None, check: bool) -> None:
    """Rebuild the selected asset's committed scenario map from the register.

    Regenerated in the same act as the synthetic history itself, so the
    two cannot disagree - this command is for rebuilding it on its own,
    after editing the register.
    """
    if check:
        _check_map()
        return
    # THIS ASSET'S SCENARIOS, as its map carries them (REQ-PIPE-352 criterion
    # 3; Keith 2026-11-03, Q5): its own placements, and those naming its datasets.
    naming_mine = generator.this_assets_scenarios()
    path = generator.write_map(map_path=out_path or scenario_map.map_path())
    placements = scenario_placements.read_placements()
    entries = [s for s in scenarios.parse_register() if s.id in naming_mine or s.id in placements]
    injected = [s for s in entries if s.is_injected]
    placed = [s for s in injected
               if (placements.get(s.id) or scenario_placements.Placement.of({})).is_complete]
    console.print(f"Wrote {path}")
    console.print(f"  {len(entries)} scenario(s), {len(injected)} marked for injection, "
                   f"{len(placed)} with data behind them.")
    if injected and not placed:
        # SAID OUT LOUD rather than left to be noticed. A map where
        # every entry reads "not injected" is the correct output today
        # and looks exactly like a broken one.
        console.print("  Nothing is injected yet - REQ-GEN-044 is the requirement "
                       "that places scenarios into the generated history.", style="dim")


def where_line(placement) -> str:
    """Where a placed scenario is to be looked at - its dataset, period and
    the date control's date, in the control's own words, lower case
    (REQ-DASH-277 criterion 3)."""
    return f"{placement.dataset} · {placement.period} · in the warehouse on {placement.in_place_on}"


@scenarios_group.command("list")
@click.option("--injected-only", is_flag=True,
               help="Only the scenarios the register marks for injection.")
def list_command(injected_only: bool) -> None:
    """List the register, without rebuilding anything."""
    entries = scenarios.parse_register()
    if injected_only:
        entries = [s for s in entries if s.is_injected]
    placements = scenario_placements.read_placements()

    table = Table(title="Test scenario register")
    table.add_column("Scenario")
    table.add_column("Mode")
    table.add_column("Title")
    table.add_column("Where")
    for scenario in sorted(entries, key=lambda s: s.sort_key):
        placement = placements.get(scenario.id)
        if placement is not None and placement.is_complete:
            where = where_line(placement)
        elif scenario.is_injected:
            where = "not injected yet"
        else:
            where = "-"
        table.add_row(scenario.id, scenario.mode, scenario.title, where)
    console.print(table)


@scenarios_group.command("validate")
def validate_command() -> None:
    """Gate: the scripted decisions hold against configuration alone
    (REQ-GEN-135 criterion 13) - every scenario registered, every decision
    a filing decision, every reason present, every dataset real - and every
    scenario link's date falls between its two events (REQ-GEN-201)."""
    from bootstrap import scripted_decision_checks
    from generator import scenario_injection
    from scenarios import scripted_decisions

    registered = {s.id for s in scenarios.parse_register()}
    script = scripted_decisions.load()
    found = scripted_decision_checks.problems(script, registered=registered,
                                              placement_of=scenario_injection.placement_of())
    # EACH SCENARIO LINK'S DATE BETWEEN ITS EVENTS (REQ-GEN-201), from
    # configuration and the calendar alone.
    found += scenario_injection.link_problems(scripts=script)
    # A SCENARIO IS ONE ASSET'S (REQ-PIPE-352 criterion 3).
    found += scenario_injection.mixed_asset_problems()
    # SCRIPTED CORRECTION CONFIRMATIONS (REQ-GEN-205 criterion 5), against
    # the declared corrections.
    from asset_model import declared_corrections
    from bootstrap import scripted_corrections

    confirmations = scripted_corrections.load()
    found += scripted_corrections.problems(confirmations, declared={
        p.reference for p in declared_corrections.pending_corrections(*declared_corrections.working())},
        injections=scenario_injection.this_assets_injections())
    if found:
        for problem in found:
            console.print(f"  - {problem}", style="red")
        raise click.ClickException(
            f"scripted decisions and scenario links FAILED ({len(found)} problem(s)) - "
            f"see above.")
    links = sum(len(i.links) for i in scenario_injection.this_assets_injections())
    console.print(f"scripted decisions OK - {len(script)} decision(s), "
                  f"{len(confirmations)} correction confirmation(s) and {links} scenario "
                  f"link(s), zero errors.")


def _check_map() -> None:
    """`map --check` (REQ-TEST-253 criterion 1): the docs gate's view of
    the selected asset's SCENARIOS-<asset>.md. The map is built from the register AND the generator's
    recorded placements; with no placements on this machine it cannot be
    judged, which is said as a warning rather than passed as current."""
    import os

    if not scenario_placements.placements_path().is_file():
        console.print(f"Cannot check {scenario_map.map_path().name}: no "
                      f"{scenario_placements.placements_path().name} on "
                      f"this machine (run `mothman pipeline bootstrap`).", style="yellow")
        if os.environ.get("MOTHMAN_GATE_WARNING_EXIT"):
            raise SystemExit(int(os.environ["MOTHMAN_GATE_WARNING_EXIT"]))
        return
    path = scenario_map.map_path()
    built = generator.build_map_for_selected()
    if not path.is_file() or path.read_text() != built:
        console.print(f"{path.name} is stale - run `mothman scenarios map`.", style="red")
        raise SystemExit(1)
    console.print(f"{path.name} is current.", style="green")
