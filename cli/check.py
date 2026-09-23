"""mothman check - every gate this repo has, in one command (Tier 3).

Keith's ask, 2026-09-20: make `npm test` something that gets run by
default rather than something to remember. The obvious-looking fix is a
rule - "run the JS suite when you touch the dashboard template" - and he
ruled it out in the same breath: "I don't want to maintain file lists
and so forth. That's messy." A list like that is wrong the moment
someone adds a file, and nothing tells you it has gone stale.

So the mechanism is not a trigger, it is a single command that runs
everything. There is nothing to decide and nothing to keep up to date:
if a gate exists, this runs it, and the report at the end says which
ones passed. The JS suite stops being a separate thing to remember
because it is no longer separate.

Deliberately runs EVERY gate rather than stopping at the first failure.
Fixing four things you were told about at once is one pass; finding them
one command at a time is four, and the last three are invisible while
the first is unfixed.

Order is cheapest-first, so the fast gates report while the slow ones
are still ahead of you - and the Python suite, far and away the longest,
goes last. Use `--no-pytest` when selective tests have already been run
locally (CLAUDE.md's own "run selective tests for smaller changes"
convention), which leaves everything else - including the JS suite -
still running in a couple of seconds.

This mirrors what .github/workflows/test.yml really runs, which is the
point: a green run here is real evidence about CI rather than a
different set of checks that happens to share some names. It is still
not a SUBSTITUTE for checking the actual run - CI's environment can
diverge from local on things no local command can see (see CLAUDE.md's
own standing rule on that).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import rich_click as click
from rich.console import Console
from rich.table import Table

console = Console()

ROOT = Path(__file__).resolve().parent.parent

# (label, argv, why-it-is-here). Node's suite is in here alongside the
# Python ones rather than left to a separate habit - see this module's
# own docstring.
_GATES: tuple[tuple[str, list[str], str], ...] = (
    ("ruff", ["uv", "run", "ruff", "check", "."],
     "real bugs in Python, not style"),
    ("yamllint", ["uv", "run", "yamllint", "--strict", "."],
     "duplicate mapping keys, which PyYAML swallows silently"),
    # Not coverable by check-yaml/yamllint: these are *.md files, so
    # neither hook ever globs them - see the module's own docstring for
    # the incident that produced this gate.
    ("agents", ["uv", "run", "python3", "-m", "qa_tools.common.validate_agents"],
     ".claude/agents/*.md frontmatter actually parses"),
    ("hierarchy", ["uv", "run", "mothman", "dashboard", "validate-hierarchy"],
     "every contract agrees with the one agency/collection/dataset tree"),
    ("schedule", ["uv", "run", "mothman", "schedule", "validate"],
     "a config typo can never leave a dataset expecting nothing"),
    ("requirements", ["uv", "run", "mothman", "dashboard", "validate-requirements"],
     "every linked test and implemented_by symbol still exists"),
    ("changelog", ["uv", "run", "mothman", "dashboard", "validate-changelog"],
     "CHANGELOG.yaml's schema and component tags"),
    ("npm test", ["npm", "test", "--silent"],
     "the dashboard template's own inline JS"),
    ("pytest", ["uv", "run", "pytest"],
     "the Python suite"),
)


def _run(label: str, argv: list[str]) -> int:
    """Streams the gate's own output rather than capturing it.

    A summary table telling you `pytest` failed and nothing else would
    be worse than no command at all - the failure itself is what you
    need, and it needs to appear while it happens, not after every other
    gate has finished."""
    console.rule(f"[bold]{label}", style="dim")
    if shutil.which(argv[0]) is None:
        console.print(
            f"{argv[0]!r} is not installed - skipping {label}. "
            f"See CLAUDE.md's environment-setup bullet.", style="yellow")
        return 127
    return subprocess.run(argv, cwd=ROOT).returncode


@click.command("check")
@click.option("--no-pytest", is_flag=True,
              help="Skip the Python suite (the slow one). Everything else still runs.")
@click.option("--only", "only", metavar="GATE",
              help="Run just one gate, by its name in the summary table. For a "
                   "pre-commit hook or a targeted re-run, where the point is "
                   "one fast check rather than the whole sweep.")
def check_command(no_pytest: bool, only: str | None) -> None:
    """Run every gate - lint, YAML, the validators, the JS suite, the Python suite."""
    gates = _GATES
    if only is not None:
        gates = tuple(g for g in _GATES if g[0] == only)
        if not gates:
            # Naming the real options beats "invalid value": the labels
            # are not guessable from the command name.
            raise click.ClickException(
                f"no gate called {only!r}. Available: "
                f"{', '.join(label for label, _, _ in _GATES)}.")

    results: list[tuple[str, int, str]] = []
    for label, argv, why in gates:
        if no_pytest and label == "pytest":
            continue
        results.append((label, _run(label, argv), why))

    console.print()
    table = Table(title="mothman check", title_style="bold", header_style="dim")
    table.add_column("Gate")
    table.add_column("Result")
    table.add_column("What it covers", style="dim")
    for label, code, why in results:
        if code == 0:
            outcome = "[green]passed[/green]"
        elif code == 127:
            outcome = "[yellow]not installed[/yellow]"
        else:
            outcome = f"[red]FAILED ({code})[/red]"
        table.add_row(label, outcome, why)
    console.print(table)

    failed = [label for label, code, _ in results if code not in (0, 127)]
    skipped = [label for label, code, _ in results if code == 127]
    if failed:
        raise click.ClickException(f"{len(failed)} gate(s) failed: {', '.join(failed)}")

    # Never "every gate passed" when one of them did not run. A summary
    # that overstates its own coverage is worse than no summary - the
    # whole reason this command exists is that a suite nobody remembered
    # to run looked exactly like a suite that passed.
    if skipped:
        console.print(f"Incomplete - no toolchain for: {', '.join(skipped)}. "
                      f"Everything that ran, passed. See CLAUDE.md's "
                      f"environment-setup bullet.", style="yellow")
    elif only is not None:
        # Same reasoning as the skipped-toolchain branch above: never
        # let a summary overstate what actually ran.
        console.print(f"The {only!r} gate passed. Other gates were not run.",
                      style="green")
    elif no_pytest:
        console.print("Every gate passed except the Python suite, which was skipped.",
                      style="green")
    else:
        console.print("Every gate passed.", style="green")


def main() -> None:
    sys.exit(check_command.main(standalone_mode=False) or 0)
