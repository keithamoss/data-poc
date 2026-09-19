"""The mothman root command (plans/tooling.md #1). Bare `mothman` (no
subcommand) launches the interactive TUI menu directly - the only entry
point a human needs to remember. Every command is also directly
flag-invocable (`mothman bdm qa --run-id ...`) - the wizard is the same
implementation as the flags, just with prompts instead, per the wizard/
flags duality the whole CLI is designed around."""
from __future__ import annotations

import rich_click as click
from rich.console import Console

from . import bdm, common
from .banner import print_banner

click.rich_click.TEXT_MARKUP = "rich"
click.rich_click.STYLE_OPTION = common.TIER_1

console = Console()

_MAIN_MENU_QA = "Quality Assurance - run the real check chain against a dataset"
_MAIN_MENU_GENERATE = "Generate synthetic data - Birth Registrations"
_MAIN_MENU_EXIT = "Exit"


def _main_menu_loop() -> None:
    print_banner(console)
    while True:
        choice = common.select(
            "What would you like to do?",
            [_MAIN_MENU_QA, _MAIN_MENU_GENERATE],
            flag_hint="mothman bdm qa / mothman bdm generate-synthetic-data",
        )
        if choice is None:
            console.print("Goodbye.", style="dim")
            return
        console.print()
        if choice == _MAIN_MENU_QA:
            _qa_menu()
        elif choice == _MAIN_MENU_GENERATE:
            _generate_menu()
        console.print()


def _qa_menu() -> None:
    # Only Birth Registrations exists in Phase 1 - Child Protection joins
    # once its own QA flow is built (plans/tooling.md #1's own phase
    # order), so this is a single-choice "menu" for now rather than a
    # dead end with nothing to pick.
    dataset = common.select("Which dataset?", ["Birth Registrations"],
                             flag_hint="mothman bdm qa")
    if dataset is None:
        return
    bdm.run_qa_interactive()


def _generate_menu() -> None:
    dataset = common.select("Which dataset?", ["Birth Registrations"],
                             flag_hint="mothman bdm generate-synthetic-data")
    if dataset is None:
        return
    if bdm.manifest_exists() and not common.confirm(
            "This will regenerate data/raw/ (deterministic - same content either way). Continue?",
            yes=False, default=True):
        console.print("Not regenerated.", style="yellow")
        return
    console.print("Generating synthetic data...", style="dim")
    bdm.generate_synthetic_data()
    console.print(f"Generated -> {bdm.raw_dir()}", style="green")


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx: click.Context) -> None:
    """mothman - the unified CLI/TUI for this PoC's real pipeline."""
    if ctx.invoked_subcommand is None:
        common.require_tty("mothman <command> --help (see the available commands)")
        _main_menu_loop()


cli.add_command(bdm.bdm_group)


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
