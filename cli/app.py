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
    from . import (check, collection_cli, common, dashboard, debug, env, filing_tui, github,
                   pipeline, plans, population, scenarios, schedule, supply)
    from qa_tools import collections as _registry

    # EVERY COLLECTION'S GROUP, FROM THE REGISTRY (REQ-TEST-245 criterion 1),
    # built here inside the YAML guard: building them reads the hierarchy.
    _COLLECTIONS = _registry.all_collections()
    _GROUPS = [collection_cli.make_group(c) for c in _COLLECTIONS]
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
_MAIN_MENU_CALENDAR = "Calendar - the delivery agreement, and previewing a correction"
_MAIN_MENU_BOOTSTRAP = "Set up this environment - generate data and run the checks over it"
_MAIN_MENU_PROCESS = "Process what has arrived - check and gate it, finish what is owed"
_MAIN_MENU_EXIT = "Exit"



def _main_menu_loop() -> None:
    print_banner(console)
    while True:
        choice = common.select(
            "What would you like to do?",
            [_MAIN_MENU_QA, _MAIN_MENU_DECIDE, _MAIN_MENU_CALENDAR, _MAIN_MENU_PROCESS,
             _MAIN_MENU_GENERATE, _MAIN_MENU_BOOTSTRAP],
            flag_hint=f"mothman {_COLLECTIONS[0].short} qa / mothman supply queue / "
                      "mothman schedule preview-correction / mothman pipeline process / "
                      f"mothman {_COLLECTIONS[0].short} generate-synthetic-data / "
                      "mothman pipeline bootstrap",
        )
        if choice is None:
            console.print("Goodbye.", style="dim")
            return
        console.print()
        # A REFUSAL INSIDE A FLOW IS SAID, AND THE MENU CARRIES ON
        # (post-build-review #124 D5): a ClickException is how every flow
        # refuses, and letting it out of this loop ended the whole session
        # over, say, an empty answer to one prompt.
        try:
            _run_choice(choice)
        except click.ClickException as exc:
            exc.show()
        console.print()


def _run_choice(choice: str) -> None:
    if choice == _MAIN_MENU_QA:
        from qa_tools.common import arrival_lifecycle

        try:
            _qa_menu()
        except arrival_lifecycle.StageFailed as exc:
            from cli import lifecycle_report

            lifecycle_report.stage_failure(exc)
    elif choice == _MAIN_MENU_DECIDE:
        # REQ-GHUB-082 criterion 16: reachable without doing a QA
        # run first. Second on the menu rather than last, because
        # somebody sitting down to work is at least as likely to be
        # draining the queue as to be running new checks - and the
        # old rule that kept it off this menu entirely was reversed
        # knowingly (see cli/supply.py's own note on why).
        filing_tui.filing_menu()
    elif choice == _MAIN_MENU_CALENDAR:
        # REQ-PIPE-169 criterion 13 - Keith, 2026-10-07: the terminal is the
        # primary tool besides the dashboard, so a preview only reachable as
        # a command would be forgotten before a change board's request.
        from cli import schedule

        schedule.calendar_menu()
    elif choice == _MAIN_MENU_GENERATE:
        _generate_menu()
    elif choice == _MAIN_MENU_BOOTSTRAP:
        _bootstrap_menu()
    elif choice == _MAIN_MENU_PROCESS:
        # REQ-PIPE-151 criterion 13: the same body the flag-invocable
        # command runs. Its exit status is the command's business; here
        # the menu simply carries on.
        try:
            pipeline.run_process(confirm=common.confirm_change)
        except SystemExit:
            pass


def _which_collection(flag_hint: str):
    """The TUI's 'Which dataset?', listed from the registry in hierarchy
    order and labelled as people know them (REQ-TEST-245 criteria 2 and 5).
    The choice dispatches to THAT collection's own commands - there is no
    branch for an unknown answer to fall into."""
    every = _registry.all_collections()
    by_label = {collection_cli.label(c): c for c in every}
    # GROUPED BY AGENCY AND FILTERED BY TYPING ABOVE N_LIST, today's list
    # at or below it (REQ-TEST-252 criteria 4 and 5).
    groups: dict[str, list[str]] = {}
    for c in every:
        groups.setdefault(c.agency_name, []).append(collection_cli.label(c))
    chosen = common.grouped_select("Which dataset?", list(groups.items()), flag_hint=flag_hint,
                                   many=common.many_collections(),
                                   terms={collection_cli.label(c): common.collection_terms(c)
                                          for c in every})
    if chosen is None:
        return None
    collection_cli.refuse_a_broken_adapter(by_label[chosen])
    return collection_cli.of(by_label[chosen].id)


def _every_collections_hint(hint, generic: str | None = None) -> str:
    """A flag hint naming each collection's own command at N_LIST or fewer,
    as today; above it the generic form with one real example, never one
    entry per collection (REQ-TEST-252 criterion 14)."""
    every = _registry.all_collections()
    if not common.many_collections():
        return " / ".join(hint(c) for c in every)
    example = hint(every[0])
    generic = generic or example.replace(f"mothman {every[0].short} ", "mothman <collection> ", 1)
    return f"{generic} (for example `{example}`; `mothman collections` lists every one)"


def _qa_menu() -> None:
    chosen = _which_collection(_every_collections_hint(
        collection_cli.qa_hint, "mothman <collection> qa [--run-id/--file or --folder]"))
    if chosen is not None:
        chosen.run_qa_interactive()


def _generate_menu() -> None:
    mod = _which_collection(_every_collections_hint(
        lambda c: f"mothman {c.short} generate-synthetic-data"))
    if mod is None:
        return
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
    # NOT "READY" OVER A HISTORY THAT READ WRONG (REQ-GEN-186 criterion 3;
    # post-build-review #157): the same message the CLI fails with.
    from cli.pipeline import disagreement_message

    wrong = disagreement_message(result.disagreements)
    if wrong:
        console.print(wrong, style="red")
        return
    console.print(f"Ready - {result.staged_after} staged table(s) in this "
                   f"environment.", style="green")


class _MothmanGroup(click.RichGroup):
    """Turns a qa schema from another version into the clean one-paragraph
    refusal it already is, not a traceback (REQ-PIPE-144 criterion 29;
    delivery-critic, overnight sprint 4). The message names the remedy."""

    def invoke(self, ctx):
        from qa_tools.common import arrival_lifecycle, environments, qa_store, supply_db

        try:
            return super().invoke(ctx)
        except qa_store.SchemaVersionError as exc:
            raise click.ClickException(str(exc)) from None
        except arrival_lifecycle.StageFailed as exc:
            # REQ-TEST-150 criterion 7: the arrival, the stage and what had
            # completed - never the message that describes a completed run.
            from cli import lifecycle_report

            lifecycle_report.stage_failure(exc)
            raise SystemExit(2) from None
        except (supply_db.SupplyDbError, environments.EnvironmentError_) as exc:
            # A database this checkout must not act on, or no stated
            # environment (REQ-PIPE-107, REQ-PIPE-093): a refusal by design,
            # whose message already says what to do - not a crash.
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
        # NO ENVIRONMENT, NO MENU (REQ-TEST-114 criterion 8): REQ-PIPE-093's
        # refusal in place of a menu whose first item would fail anyway.
        from qa_tools.common import environments
        environments.current()
        _main_menu_loop()
    else:
        _state_the_environment_on_first_connection()


def _state_the_environment_on_first_connection() -> None:
    """One line naming the environment before a one-off command's own output
    once it connects (REQ-TEST-114 criteria 2 and 3), on STANDARD ERROR so a
    piped table is unchanged. At the first connection rather than at start,
    so a command that never touches a database says nothing."""
    from qa_tools.common import supply_db

    def state() -> None:
        statement = common.environment_statement()
        if statement:
            click.echo(statement, err=True)

    supply_db.on_first_connection(state)


@click.command("collections")
def collections_command() -> None:
    """Every registered collection: its short, id, label and agency."""
    # PLAIN TEXT, ONE PER LINE, so it reads the same through a pipe or with
    # NO_COLOR=1 as on a terminal (criterion 12). Reads the hierarchy only.
    every = _registry.all_collections()
    rows = [(c.short, c.id, collection_cli.label(c), c.agency_name) for c in every]
    widths = [max(len(r[i]) for r in rows) for i in range(3)] if rows else [0, 0, 0]
    for r in rows:
        click.echo("  ".join(v.ljust(w) for v, w in zip(r[:3], widths)) + "  " + r[3])


for _group in _GROUPS:
    cli.add_command(_group)
cli.add_command(collections_command)
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

# TWO PANELS IN `mothman --help`, AT EVERY SIZE (REQ-TEST-252 criterion 2,
# Keith 2026-10-16): every collection group in hierarchy order, then every
# other group and command in Click's own order - so no tool sits between two
# collections, today's two included.
from rich_click.rich_panel import RichCommandPanel  # noqa: E402

_COLLECTION_NAMES = [g.name for g in _GROUPS]
cli.add_panel(RichCommandPanel("Collections", commands=_COLLECTION_NAMES))
cli.add_panel(RichCommandPanel("Tools", commands=[n for n in sorted(cli.commands)
                                                  if n not in _COLLECTION_NAMES]))


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
