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

import os
import shutil
import subprocess
import sys
from pathlib import Path

import rich_click as click
from rich.console import Console
from rich.table import Table

console = Console()

ROOT = Path(__file__).resolve().parent.parent

#: A gate that PASSED but has something worth knowing exits with this
#: instead of 0. See _GATES below for why it is opt-in and env-gated
#: rather than something any gate may emit whenever it likes.
WARNING_EXIT = 78
WARNING_EXIT_VAR = "MOTHMAN_GATE_WARNING_EXIT"

# (label, argv, why-it-is-here, can-warn). Node's suite is in here
# alongside the Python ones rather than left to a separate habit - see
# this module's own docstring.
#
# THE FOURTH FIELD IS THE WARNING OPT-IN, and it is per gate rather
# than global for one reason: a real failure that happened to exit 78
# would otherwise be re-read as a warning, turning red into yellow.
# That is the false-green direction, so only a gate that actually has a
# warning state gets its sentinel interpreted (post-build-review #23).
_GATES: tuple[tuple[str, list[str], str, bool], ...] = (
    ("ruff", ["uv", "run", "ruff", "check", "."],
     "real bugs in Python, not style", False),
    ("yamllint", ["uv", "run", "yamllint", "--strict", "."],
     "duplicate mapping keys, which PyYAML swallows silently", False),
    # Not coverable by check-yaml/yamllint: these are *.md files, so
    # neither hook ever globs them - see the module's own docstring for
    # the incident that produced this gate.
    ("agents", ["uv", "run", "python3", "-m", "qa_tools.common.validate_agents"],
     ".claude/agents/*.md frontmatter actually parses", False),
    ("hierarchy", ["uv", "run", "mothman", "dashboard", "validate-hierarchy"],
     "every contract agrees with the one agency/collection/dataset tree", False),
    # The one gate with a warning state today: REQ-PIPE-053's low
    # runway, which must be visible without failing the build.
    ("schedule", ["uv", "run", "mothman", "schedule", "validate"],
     "a config typo can never leave a dataset expecting nothing", True),
    ("requirements", ["uv", "run", "mothman", "dashboard", "validate-requirements"],
     "every linked test and implemented_by symbol still exists", False),
    ("changelog", ["uv", "run", "mothman", "dashboard", "validate-changelog"],
     "CHANGELOG.yaml's schema and component tags", False),
    ("npm test", ["npm", "test", "--silent"],
     "the dashboard template's own inline JS", False),
    ("pytest", ["uv", "run", "pytest"],
     "the Python suite", False),
)


def _run(label: str, argv: list[str], can_warn: bool = False) -> int:
    """Streams the gate's own output rather than capturing it.

    A summary table telling you `pytest` failed and nothing else would
    be worse than no command at all - the failure itself is what you
    need, and it needs to appear while it happens, not after every other
    gate has finished.

    Streaming is also why the warning channel is an exit code and not a
    marker line in the output: reading the output would mean piping it,
    and a gate whose stdout is a pipe stops colouring it.

    `can_warn` opts the gate in through the environment rather than
    letting it decide for itself. CI runs these same commands directly
    as their own workflow steps, where any non-zero exit is a failed
    step - so a gate must return 0 there, and only say more when
    something asked it to.
    """
    console.rule(f"[bold]{label}", style="dim")
    if shutil.which(argv[0]) is None:
        console.print(
            f"{argv[0]!r} is not installed - skipping {label}. "
            f"See CLAUDE.md's environment-setup bullet.", style="yellow")
        return 127
    env = None
    if can_warn:
        env = {**os.environ, WARNING_EXIT_VAR: str(WARNING_EXIT)}
    return subprocess.run(argv, cwd=ROOT, env=env).returncode


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
                f"{', '.join(label for label, _, _, _ in _GATES)}.")

    results: list[tuple[str, int, str, bool]] = []
    for label, argv, why, can_warn in gates:
        if no_pytest and label == "pytest":
            continue
        results.append((label, _run(label, argv, can_warn), why, can_warn))

    console.print()
    table = Table(title="mothman check", title_style="bold", header_style="dim")
    table.add_column("Gate")
    table.add_column("Result")
    table.add_column("What it covers", style="dim")
    for label, code, why, can_warn in results:
        if code == 0:
            outcome = "[green]passed[/green]"
        elif code == 127:
            outcome = "[yellow]not installed[/yellow]"
        elif can_warn and code == WARNING_EXIT:
            outcome = "[yellow]passed, with a warning[/yellow]"
        else:
            outcome = f"[red]FAILED ({code})[/red]"
        table.add_row(label, outcome, why)
    console.print(table)

    def _warned(code: int, can_warn: bool) -> bool:
        return can_warn and code == WARNING_EXIT

    failed = [label for label, code, _, can_warn in results
              if code not in (0, 127) and not _warned(code, can_warn)]
    skipped = [label for label, code, _, _ in results if code == 127]
    warned = [label for label, code, _, can_warn in results if _warned(code, can_warn)]
    if failed:
        raise click.ClickException(f"{len(failed)} gate(s) failed: {', '.join(failed)}")

    # Never "every gate passed" when one of them did not run. A summary
    # that overstates its own coverage is worse than no summary - the
    # whole reason this command exists is that a suite nobody remembered
    # to run looked exactly like a suite that passed.
    # A warning is reported BEFORE the closing line and never instead
    # of it: the gate passed, and the command's exit code says so. What
    # this fixes is the summary saying "Every gate passed" while a real
    # warning sat eight gates and two minutes further up the scrollback
    # (post-build-review #23).
    if warned:
        console.print(
            f"Passed, with a warning from: {', '.join(warned)}. "
            f"Scroll up for what it said - it is not failing the build.",
            style="yellow")

    if skipped:
        console.print(f"Incomplete - no toolchain for: {', '.join(skipped)}. "
                      f"Everything that ran, passed. See CLAUDE.md's "
                      f"environment-setup bullet.", style="yellow")
    elif warned:
        pass  # already said above; "Every gate passed" would talk over it
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
