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
            where = f"{placement.dataset} · {placement.period} · in place on {placement.in_place_on}"
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
    a filing decision, every reason present, every dataset real."""
    from qa_tools.common import scripted_decisions

    registered = {s.id for s in scenarios.parse_register()}
    script = scripted_decisions.load()
    found = scripted_decisions.problems(script, registered=registered)
    if found:
        for problem in found:
            console.print(f"  - {problem}", style="red")
        raise click.ClickException(
            f"scripted decisions FAILED ({len(found)} problem(s)) - see above.")
    console.print(f"scripted decisions OK - {len(script)} decision(s), zero errors.")


@scenarios_group.command("bands")
@click.option("--dataset", "dataset_id", default=None,
              help="One dataset's rules (default: every dataset).")
@click.option("--rows", type=int, default=None,
              help="The supply's row count a band is worked out at (default: the "
                   "smallest supply the contract calls ordinary).")
def bands_command(dataset_id: str | None, rows: int | None) -> None:
    """Every rule's bands per tool, and whether it can read amber (REQ-GEN-183).

    \b
    Examples:
      mothman scenarios bands --dataset birth-registrations --rows 2000
      mothman scenarios bands

    A rule is the checks that implement it across tools - one dataset, column
    and category - and its amber band is where no implementing check fails and
    at least one warns, honouring each tool's own unit and operator. Read from
    the committed definitions the tools run; opens no database. What the
    synthetic generator reads to build a supply to a verdict.
    """
    from qa_tools.common import check_bands as cb, hierarchy

    try:
        cat = cb.catalogue()
    except cb.CatalogueError as exc:
        raise click.ClickException(str(exc)) from exc
    datasets = [dataset_id] if dataset_id else sorted({c.dataset_id for c in cat.checks})
    known = {c.dataset_id for c in cat.checks}
    for ds in datasets:
        if ds not in known:
            raise click.ClickException(f"{ds} has no checks - is it a dataset id?")
        n = rows or cb.default_rows(ds, cat)
        console.print(f"\n[bold]{hierarchy.dataset(ds).dataset_name}[/bold] ({ds}) - bands at {n} rows",
                      highlight=False)
        for r in sorted((r for r in cat.rules() if r.dataset_id == ds),
                        key=lambda r: (r.column or "", r.category, r.measure)):
            where = f"{r.column or '(the table)'} - {r.category}, {r.measure}"
            amber = r.amber(n)
            if amber:
                said = ", ".join(f"{lo}-{hi}" if lo != hi else f"{lo}" for lo, hi in amber)
                head = f"amber at {said}"
            else:
                head = "no amber band - closed by " + ", ".join(
                    c.rsplit(".", 1)[-1] for c in r.closed_by(n))
            console.print(f"  {where}: {head}", markup=False, highlight=False)
            for c in r.checks:
                bands = ("fails on any" if c.single_tier else
                         "; ".join(filter(None, [
                             "warns " + " or ".join(b.text() for b in c.warn) if c.warn else "",
                             "fails " + " or ".join(b.text() for b in c.fail) if c.fail
                             else "never fails"])))
                console.print(f"      {c.tool:<12} {bands}", markup=False, highlight=False,
                              style="dim")
        readers = cat.single_tier_readers(ds)
        if readers:
            console.print("  Single-tier checks reading each column:", style="bold")
            for col, ids in readers.items():
                console.print(f"    {col}: " + ", ".join(i.rsplit(".", 1)[-1] for i in ids),
                              markup=False, highlight=False, soft_wrap=True)
