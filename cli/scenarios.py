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

from qa_tools.common import scenario_map, scenarios

console = Console()


@click.group("scenarios")
def scenarios_group() -> None:
    """The deliberately awkward supplies, and where to look at them."""


@scenarios_group.command("map")
@click.option("--out", "out_path", default=None,
               help="Write somewhere other than the committed SCENARIOS.md.")
def map_command(out_path: str | None) -> None:
    """Rebuild the committed scenario map from the register.

    Regenerated in the same act as the synthetic history itself, so the
    two cannot disagree - this command is for rebuilding it on its own,
    after editing the register.
    """
    path = scenario_map.write_map(map_path=out_path)
    entries = scenarios.parse_register()
    placements = scenario_map.read_placements()
    injected = [s for s in entries if s.is_injected]
    placed = [s for s in injected
               if (placements.get(s.id) or scenario_map.Placement.of({})).is_complete]
    console.print(f"Wrote {path}")
    console.print(f"  {len(entries)} scenario(s), {len(injected)} marked for injection, "
                   f"{len(placed)} with data behind them.")
    if injected and not placed:
        # SAID OUT LOUD rather than left to be noticed. A map where
        # every entry reads "not injected" is the correct output today
        # and looks exactly like a broken one.
        console.print("  Nothing is injected yet - REQ-GEN-044 is the requirement "
                       "that places scenarios into the generated history.", style="dim")


@scenarios_group.command("list")
@click.option("--injected-only", is_flag=True,
               help="Only the scenarios the register marks for injection.")
def list_command(injected_only: bool) -> None:
    """List the register, without rebuilding anything."""
    entries = scenarios.parse_register()
    if injected_only:
        entries = [s for s in entries if s.is_injected]
    placements = scenario_map.read_placements()

    table = Table(title="Test scenario register")
    table.add_column("Scenario")
    table.add_column("Mode")
    table.add_column("Title")
    table.add_column("Where")
    for scenario in sorted(entries, key=lambda s: s.sort_key):
        placement = placements.get(scenario.id)
        if placement is not None and placement.is_complete:
            where = f"{placement.dataset} · {placement.period} · as of {placement.as_of}"
        elif scenario.is_injected:
            where = "not injected yet"
        else:
            where = "-"
        table.add_row(scenario.id, scenario.mode, scenario.title, where)
    console.print(table)
