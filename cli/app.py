"""The mothman root command (plans/tooling.md #1). Bare `mothman` (no
subcommand) launches the interactive TUI menu directly - the only entry
point a human needs to remember. Every command is also directly
flag-invocable (`mothman bdm qa --run-id ...`) - the wizard is the same
implementation as the flags, just with prompts instead, per the wizard/
flags duality the whole CLI is designed around."""
from __future__ import annotations

import rich_click as click
from rich.console import Console

from . import (bdm, check, common, cp, dashboard, debug, github, pipeline, plans,
               population, scenarios, schedule, supply)
from .banner import print_banner

click.rich_click.TEXT_MARKUP = "rich"
click.rich_click.STYLE_OPTION = common.TIER_1

console = Console()

_MAIN_MENU_QA = "Quality Assurance - run the real check chain against a dataset"
_MAIN_MENU_GENERATE = "Generate synthetic data"
_MAIN_MENU_BOOTSTRAP = "Set up this environment - generate data and run the checks over it"
_MAIN_MENU_EXIT = "Exit"

_DATASET_BDM = "Birth Registrations"
_DATASET_CP = "Child Protection"


def _main_menu_loop() -> None:
    print_banner(console)
    while True:
        choice = common.select(
            "What would you like to do?",
            [_MAIN_MENU_QA, _MAIN_MENU_GENERATE, _MAIN_MENU_BOOTSTRAP],
            flag_hint="mothman bdm qa / mothman bdm generate-synthetic-data / "
                       "mothman pipeline bootstrap",
        )
        if choice is None:
            console.print("Goodbye.", style="dim")
            return
        console.print()
        if choice == _MAIN_MENU_QA:
            _qa_menu()
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
    mod, raw_dir_label = (bdm, "data/raw/") if dataset == _DATASET_BDM else (cp, "data/cp_raw/")
    if mod.manifest_exists() and not common.confirm(
            f"This will regenerate {raw_dir_label} (deterministic - same content either way). Continue?",
            yes=False, default=True):
        console.print("Not regenerated.", style="yellow")
        return
    console.print("Generating synthetic data...", style="dim")
    mod.generate_synthetic_data()
    console.print(f"Generated -> {mod.raw_dir()}", style="green")


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


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx: click.Context) -> None:
    """mothman - the unified CLI/TUI for this PoC's real pipeline."""
    if ctx.invoked_subcommand is None:
        common.require_tty("mothman <command> --help (see the available commands)")
        _main_menu_loop()


cli.add_command(bdm.bdm_group)
cli.add_command(cp.cp_group)
cli.add_command(dashboard.dashboard_group)
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
