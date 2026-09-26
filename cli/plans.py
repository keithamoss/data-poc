"""mothman plans - the delivery plan, counted against the register.

ITS OWN GROUP rather than folded into `dashboard`, which is where the
other validators live. Those answer "is this file well-formed"; these
answer "where has the work actually got to", which is a question a
person asks on purpose rather than a gate that runs on their behalf.
`dashboard validate-requirements` staying where it is keeps that line
clean.

Everything here reads two committed text files - plans/supply-model.md
and requirements.yaml. Nothing opens data/, a warehouse or committed
QA history, so it is safe under CLAUDE.md's CI rule and fast enough to
run while editing either one.
"""
from __future__ import annotations

import rich_click as click
from rich.console import Console
from rich.text import Text

from qa_tools.common import sprint_state

console = Console()


@click.group("plans")
def plans_group() -> None:
    """The delivery plan: sprint state, and what is waiting on what."""


@plans_group.command("sprints")
def sprints_command() -> None:
    """How far each sprint has got, counted from its criteria.

    The `sprints` gate in `mothman check` runs exactly this.
    """
    raise SystemExit(sprint_state.main())


@plans_group.command("dependencies")
def dependencies_command() -> None:
    """What each sprint waits on, and what is waiting on it.

    Both directions, because they are different questions. "What is
    sprint 10 waiting on" is what you ask before picking it up; "what
    is waiting on sprint 11" is what tells you promotion closes
    remainders in seven other sprints at once.
    """
    rows = sprint_state.dependency_view()
    if not rows:
        console.print("Nothing is waiting on anything - no deferral in the "
                       "register names a sprint or a requirement.")
        return
    for row in rows:
        # PRINTED AS `Text`, NOT AS A MARKUP STRING, and that is load
        # bearing rather than style: a heading carries the sprint's
        # state in square brackets, which Rich parses as a style tag.
        # `[blocked]` is not a style, so it was dropped silently and
        # every row rendered with its status missing - found by running
        # the command, covered by tests/test_cli_plans.py.
        #
        # The indented continuation lines are detail under a heading;
        # dimming them is what makes the sprint numbers scannable in a
        # list this long.
        indented = row.startswith("    ")
        console.print(Text(row, style="dim" if indented else "bold"), soft_wrap=True)

    stale = sprint_state.satisfied_blockers()
    if stale:
        console.print()
        console.print("[yellow]Worth re-testing - every blocker below has "
                       "since been delivered:[/yellow]")
        for s in stale:
            console.print(Text(f"  - {s}", style="yellow"), soft_wrap=True)
