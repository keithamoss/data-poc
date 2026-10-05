"""The mothman root command (plans/tooling.md #1). Bare `mothman` (no
subcommand) launches the interactive TUI menu directly - the only entry
point a human needs to remember. Every command is also directly
flag-invocable (`mothman bdm qa --run-id ...`) - the wizard is the same
implementation as the flags, just with prompts instead, per the wizard/
flags duality the whole CLI is designed around."""
from __future__ import annotations

import rich_click as click
import yaml
from rich.console import Console

# A DEVELOPER'S OWN .env, BEFORE ANYTHING READS THE ENVIRONMENT.
# First thing, and above the command imports on purpose: several of
# them read a DSN at import time, and a loader that ran after them
# would be a loader that works only sometimes. Never overrides
# something already set - see qa_tools/common/local_env.py.
from qa_tools.common.local_env import load_local_env

load_local_env()


def _config_refusal(exc) -> str:
    """One line for a configuration file that cannot be parsed - the file,
    the line, what is wrong - never a traceback (REQ-PIPE-122 criterion 24,
    Keith 2026-10-05; post-build-review #107)."""
    import os

    mark = getattr(exc, "problem_mark", None)
    where = "a configuration file"
    if mark is not None:
        name = mark.name
        try:
            name = os.path.relpath(name)
        except ValueError:
            pass
        where = f"{name} line {mark.line + 1}"
    problem = getattr(exc, "problem", None) or str(exc).splitlines()[0]
    return (f"{where}: {problem} - it cannot be read, so no command can run. "
            f"Fix it, then `mothman check` validates the rest.")


try:
    from . import (bdm, check, common, cp, dashboard, debug, env, filing_tui, github,
                   pipeline, plans, population, scenarios, schedule, supply)
except yaml.YAMLError as _exc:
    # READ AT IMPORT TIME by several command modules, so this is the only
    # place that can catch it - before any command, `--help` included.
    import sys as _sys

    print(_config_refusal(_exc), file=_sys.stderr)
    raise SystemExit(2) from None
from .banner import print_banner

click.rich_click.TEXT_MARKUP = "rich"
click.rich_click.STYLE_OPTION = common.TIER_1

console = Console()

_MAIN_MENU_QA = "Quality Assurance - run the real check chain against a dataset"
_MAIN_MENU_GENERATE = "Generate synthetic data"
_MAIN_MENU_DECIDE = "Filing decisions - what goes into a period"
_MAIN_MENU_BOOTSTRAP = "Set up this environment - generate data and run the checks over it"
_MAIN_MENU_EXIT = "Exit"

_DATASET_BDM = "Birth Registrations"
_DATASET_CP = "Child Protection"


def _main_menu_loop() -> None:
    print_banner(console)
    while True:
        choice = common.select(
            "What would you like to do?",
            [_MAIN_MENU_QA, _MAIN_MENU_DECIDE, _MAIN_MENU_GENERATE,
             _MAIN_MENU_BOOTSTRAP],
            flag_hint="mothman bdm qa / mothman supply queue / "
                       "mothman bdm generate-synthetic-data / "
                       "mothman pipeline bootstrap",
        )
        if choice is None:
            console.print("Goodbye.", style="dim")
            return
        console.print()
        if choice == _MAIN_MENU_QA:
            _qa_menu()
        elif choice == _MAIN_MENU_DECIDE:
            # REQ-GHUB-082 criterion 16: reachable without doing a QA
            # run first. Second on the menu rather than last, because
            # somebody sitting down to work is at least as likely to be
            # draining the queue as to be running new checks - and the
            # old rule that kept it off this menu entirely was reversed
            # knowingly (see cli/supply.py's own note on why).
            filing_tui.filing_menu()
        elif choice == _MAIN_MENU_GENERATE:
            _generate_menu()
        elif choice == _MAIN_MENU_BOOTSTRAP:
            _bootstrap_menu()
        console.print()


def _qa_menu() -> None:
    dataset = common.select(
        "Which dataset?", [_DATASET_BDM, _DATASET_CP],
        flag_hint="mothman bdm qa [--run-id/--file] / mothman cp qa [--run-id/--folder]")
    if dataset is None:
        return
    if dataset == _DATASET_BDM:
        bdm.run_qa_interactive()
    else:
        cp.run_qa_interactive()


def _generate_menu() -> None:
    dataset = common.select("Which dataset?", [_DATASET_BDM, _DATASET_CP],
                             flag_hint="mothman bdm generate-synthetic-data / mothman cp generate-synthetic-data")
    if dataset is None:
        return
    mod = bdm if dataset == _DATASET_BDM else cp
    if mod.manifest_exists() and not common.confirm(
            f"This will regenerate {mod.generated_output_dir()} "
            f"(deterministic - same content either way). Continue?",
            yes=False, default=True):
        console.print("Not regenerated.", style="yellow")
        return
    console.print("Generating synthetic data...", style="dim")
    mod.generate_synthetic_data()
    console.print(f"Generated -> {mod.generated_output_dir()}", style="green")


def _bootstrap_menu() -> None:
    """The first thing a newcomer needs, and the one they would not know
    to ask for by name - which is why it is on the main menu rather than
    only behind a flag."""
    from qa_tools.common.bootstrap import bootstrap

    console.print("Setting up this environment - generating synthetic data and "
                   "running the real checks over it.", style="dim")
    console.print("Safe to run more than once: if there is already data here it "
                   "will say so and stop.", style="dim")
    if not common.confirm("This takes a few minutes. Continue?", yes=False, default=True):
        console.print("Not run.", style="yellow")
        return
    result = bootstrap(on_step=lambda msg: console.print(f"{msg}...", style="dim"))
    if not result.populated:
        console.print(result.reason, style="yellow")
        return
    console.print(f"Ready - {result.staged_after} staged table(s) in this "
                   f"environment.", style="green")


class _MothmanGroup(click.RichGroup):
    """Turns a qa schema from another version into the clean one-paragraph
    refusal it already is, not a traceback (REQ-PIPE-144 criterion 29;
    delivery-critic, overnight sprint 4). The message names the remedy."""

    def invoke(self, ctx):
        from qa_tools.common import qa_store

        try:
            return super().invoke(ctx)
        except qa_store.SchemaVersionError as exc:
            raise click.ClickException(str(exc)) from None
        except yaml.YAMLError as exc:
            # The same refusal for a file read only once a command runs.
            raise click.ClickException(_config_refusal(exc)) from None


@click.group(cls=_MothmanGroup, invoke_without_command=True)
@click.pass_context
def cli(ctx: click.Context) -> None:
    """mothman - the unified CLI/TUI for this PoC's real pipeline."""
    if ctx.invoked_subcommand is None:
        common.require_tty("mothman <command> --help (see the available commands)")
        _main_menu_loop()


cli.add_command(bdm.bdm_group)
cli.add_command(cp.cp_group)
cli.add_command(dashboard.dashboard_group)
cli.add_command(env.env_group)
cli.add_command(github.github_group)
cli.add_command(debug.debug_group)
cli.add_command(pipeline.pipeline_group)
cli.add_command(plans.plans_group)
cli.add_command(schedule.schedule_group)
cli.add_command(scenarios.scenarios_group)
cli.add_command(supply.supply_group)
cli.add_command(population.population_command)
cli.add_command(check.check_command)


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
