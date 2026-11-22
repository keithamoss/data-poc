"""`mothman one-off` - the one command group every one-off step is reached
through (REQ-PIPE-446 criteria 3 and 8; REQ-PIPE-363 criteria 5, 6 and 11).

RUNS WITH MOTHMAN_ASSET UNSET, AND IS REFUSED WITH IT SET (Keith 2026-11-21,
v6 Q2 (b)): MOTHMAN_ASSET is for the enduring assets only. A one-off is named
by `--id`, or chosen in the TUI, which is bare `mothman one-off` (CLI Q1 (a)).
No per-collection command group is ever built for a one-off, so a one-off's
collection short can never clash with a top-level command.

THE STEPS ARE THEIR OWN REQUIREMENTS: open and load (REQ-PIPE-440, REQ-PIPE-442),
decide (REQ-PIPE-435), publish (REQ-PIPE-443), drop (REQ-PIPE-442). Each is
added to this group, taking `--id` through `id_option`, when it is built.
"""
from __future__ import annotations

import os
import subprocess
import sys

import rich_click as click
from rich.console import Console

from asset_model import assets

from . import common

console = Console()


def refuse_an_asset_beside() -> None:
    """Every `mothman one-off` command, first (REQ-PIPE-363 criterion 6,
    REQ-PIPE-446 criterion 3): MOTHMAN_ASSET set at all is refused, naming the
    variable and its value, before any configuration is read."""
    stated = os.environ.get(assets.ASSET_ENV)
    if stated:
        raise click.ClickException(
            f"{assets.ASSET_ENV} is {stated!r}, and `mothman one-off` runs with it unset: "
            f"{assets.ASSET_ENV} is for the enduring assets only, and a one-off is named by "
            f"--id or chosen in `mothman one-off`. Unset it and run this again.")


def id_option(fn):
    """`--id <id>`: the one-off a step acts for (REQ-PIPE-446 criterion 3)."""
    return click.option("--id", "one_off_id", required=True, metavar="ID",
                        help="The one-off to act for - its folder's name under "
                             "one-offs/<kind>/.")(fn)


def choose(one_off_id: str):
    """Select the one-off a step was given, refused as assets.select_one_off
    refuses."""
    try:
        return assets.select_one_off(one_off_id)
    except assets.AssetError as exc:
        raise click.ClickException(str(exc)) from None


#: The TUI's choice for a package not yet opened (REQ-PIPE-442 criterion 2).
OPEN_NEW = "Open a new package"
#: The TUI's steps once a one-off is chosen, each the command of that name.
STEPS = {"Load its package": "load", "Record its release decision": "decide",
         "Publish its page": "publish", "Drop it": "drop", "List every one-off": "list"}


@click.group("one-off", invoke_without_command=True)
@click.pass_context
def one_off_group(ctx: click.Context) -> None:
    """One-offs - browse and work on one in the TUI (bare `mothman one-off`),
    or name it with --id in a step. Runs with MOTHMAN_ASSET unset."""
    refuse_an_asset_beside()
    if ctx.invoked_subcommand is None:
        common.require_tty("mothman one-off list (every one-off), then a step with --id <id>")
        _tui(ctx)


def _tui(ctx: click.Context) -> None:
    """THE ONE-OFF TUI (Keith 2026-11-21, CLI Q1 (a); REQ-PIPE-442 criterion 2):
    a menu of its own, needing no asset, listing the one-offs as `list` does
    and offering to open a new package. Once one is chosen, every step acts on
    it for the rest of the session - the per-process claim allows one - and
    another needs a new session."""
    from qa_tools.common import one_off_lifecycle

    rows = one_off_lifecycle.rows(_ages_or_none())
    labels = {f"{r.one_off_id}  ({r.kind}) - {r.project} [{r.stage}]": r.one_off_id
              for r in rows}
    picked = common.select("Which one-off?", [*labels, OPEN_NEW],
                           "mothman one-off list, then a step with --id <id>")
    if picked is None:
        return
    if picked == OPEN_NEW:
        from asset_model import one_off_kinds

        kinds = [k.name for k in one_off_kinds.registered() if k.reader and k.generator]
        kind = common.select("Which kind?", kinds, "mothman one-off open --kind <kind>")
        if kind is None:
            return
        package = click.prompt(common._named("Where is the package (a folder or s3:// prefix)?"))
        ctx.invoke(open_command, kind_name=kind, package=package)
        return
    one_off_id = labels[picked]
    chosen = choose(one_off_id)
    console.print(f"One-off: {chosen.name} ({_word(chosen.kind)}), folder {chosen.folder}. "
                  f"Every step now acts on it; another one-off needs a new session.",
                  style="green")
    while True:
        step = common.select(f"{one_off_id}: which step?", list(STEPS),
                             f"mothman one-off <step> --id {one_off_id}")
        if step is None:
            return
        try:
            if STEPS[step] == "load":
                package = click.prompt(common._named("Where is its package?"))
                ctx.invoke(load_command, one_off_id=one_off_id, package=package)
            elif STEPS[step] == "decide":
                ctx.invoke(decide_command, one_off_id=one_off_id, decision=None, reason=None,
                           yes=False)
            elif STEPS[step] == "publish":
                ctx.invoke(publish_command, one_off_id=one_off_id, yes=False)
            elif STEPS[step] == "drop":
                ctx.invoke(drop_command, one_off_id=one_off_id)
            else:
                ctx.invoke(list_command)
        except click.ClickException as exc:
            exc.show()


def _word(kind: str) -> str:
    from asset_model import one_off_kinds

    plug = one_off_kinds.get(kind)
    return plug.singular if plug else kind


def _ages_or_none():
    """The server's databases' ages, or None where no server is configured or
    it cannot be reached - list still shows the stages git can see."""
    from qa_tools.common import one_off_lifecycle

    try:
        return one_off_lifecycle.database_ages()
    except Exception as exc:  # noqa: BLE001 - said, and the stages still shown
        console.print(f"The server's databases could not be listed ({type(exc).__name__}); "
                      f"stages are from git alone.", style="yellow")
        return None


def _age(hours: float | None) -> str:
    if hours is None:
        return "-"
    return f"{hours:.0f}h" if hours < 48 else f"{hours / 24:.0f}d"


@one_off_group.command("list")
def list_command() -> None:
    """Every one-off with its stage - opened, committed, pushed or loaded - how
    long since its database was created, and the command for its next step;
    then every one-off database still on the server, with its age
    (REQ-PIPE-442 criterion 10). Reads the one-offs root and git, and lists the
    server's databases through one administrative connection; never opens a
    one-off's own database."""
    from qa_tools.common import one_off_lifecycle

    ages = _ages_or_none()
    rows = one_off_lifecycle.rows(ages)
    if not rows:
        click.echo(f"No one-offs found under {assets.one_offs_root()}.")
        click.echo("Next: open one from its package:\n"
                   "  mothman one-off open --kind extraction <package>")
    else:
        widths = [max(len(getattr(r, f)) for r in rows) for f in ("one_off_id", "kind", "stage")]
        for r in rows:
            click.echo(f"{r.one_off_id.ljust(widths[0])}  {r.kind.ljust(widths[1])}  "
                       f"{r.stage.ljust(widths[2])}  {_age(r.age_hours):>4}  {r.project}")
            click.echo(f"  next: {r.next_step}")
    stray = one_off_lifecycle.stray_databases(ages)
    if stray:
        click.echo("One-off databases on the server:")
        for db, age in stray.items():
            click.echo(f"  {db}  {_age(age)}")
    if rows:
        click.echo("Next: a step with --id <id>, as each line says.")


@one_off_group.command("open")
@click.option("--kind", "kind_name", required=True, metavar="KIND",
              help="The kind of one-off, by its folder under one-offs/ (e.g. extraction).")
@click.argument("package")
def open_command(kind_name: str, package: str) -> None:
    """Generate one-offs/<kind>/<id>/ from a package - a local directory or an
    s3:// prefix - and its recipe alone (REQ-PIPE-440 criterion 1). Reads the
    package, the kind's template and the folder names; connects to nothing."""
    from asset_model import one_off_kinds

    kind = one_off_kinds.get(kind_name)
    if kind is None or kind.reader is None or kind.generator is None:
        known = ", ".join(k.name for k in one_off_kinds.registered()
                          if k.reader and k.generator) or "(none)"
        raise click.ClickException(f"no one-off kind {kind_name!r} can open a package - "
                                   f"kinds that can: {known}.")
    client = None
    if package.startswith("s3://"):
        import boto3

        client = boto3.client("s3")
    try:
        read = kind.reader(package, s3_client=client)
        folder = kind.generator(read, assets.one_offs_root())
    except ValueError as exc:
        raise click.ClickException(str(exc)) from None
    rel = folder
    try:
        rel = folder.relative_to(assets.ROOT)
    except ValueError:
        pass
    click.echo(f"Generated {rel} from {package} ({kind.singular} "
               f"{read.recipe.extraction_id}, {read.recipe.project}).")
    # THE NEXT STEP (REQ-PIPE-442 criterion 12): commit and push, then load.
    click.echo("\n".join([
        "Next: commit and push it, then load it:",
        f"  git add {rel}",
        f'  git commit -m "Open {kind.singular} {read.recipe.extraction_id}"',
        "  git push",
        f"  mothman one-off load --id {read.recipe.extraction_id} {package}"]))


@one_off_group.command("load")
@id_option
@click.argument("package")
def load_command(one_off_id: str, package: str) -> None:
    """Load a one-off's package - a local directory or an s3:// prefix - into
    a database of its own, supply_<id>, after its folder is gated: every gate
    its kind declares, then stage, check with all four tools and record, one
    delivery per collection (REQ-PIPE-442 criterion 3). A load that stopped
    is resumed by loading the same package again (criterion 5)."""
    from asset_model import one_off_kinds
    from qa_tools.common import git_identity, one_off_load

    chosen = choose(one_off_id)
    kind = one_off_kinds.get(chosen.kind)
    client = None
    if package.startswith("s3://"):
        import boto3

        client = boto3.client("s3")
    # THE REFUSALS FIRST, before reading or connecting to anything (REQ-PIPE-440
    # criteria 8, 9 and 12).
    refused = one_off_load.refusals(chosen.folder, package, assets.kind_template(chosen.kind),
                                    s3_client=client)
    # ALREADY PUBLISHED (REQ-PIPE-443 criterion 7): read from the destination,
    # since by then the one-off's database may be gone.
    from qa_tools.common import one_off_publish

    published = one_off_publish.load_refusal(chosen.kind, one_off_id)
    if published:
        refused = [*refused, published]
    if refused:
        raise click.ClickException("the load was refused, and nothing was loaded:\n"
                                   + "\n\n".join(refused))
    # EVERY GATE ITS KIND DECLARES, OVER ITS FOLDER (criterion 3; Keith
    # 2026-11-21, architect Q-A4 (a)): a load of an ungated folder could
    # publish a page from configuration no gate had read.
    failed = []
    for label in [g for g, applies in kind.gates.items() if applies]:
        if run_in_process(label):
            failed.append(label)
    if failed:
        raise click.ClickException(
            f"the folder {chosen.folder} failed the gate(s) {', '.join(failed)}, so nothing "
            f"was loaded. Run `mothman one-off gate --id {one_off_id} <gate>` to see why.")
    try:
        read = kind.reader(package, s3_client=client, opening=False)
        if read.recipe.extraction_id != one_off_id:
            raise ValueError(f"the package at {package} is extraction "
                             f"{read.recipe.extraction_id!r}, not {one_off_id!r}.")
        run_by = git_identity.get_run_by()
        report = one_off_load.load(read, run_by=run_by, s3_client=client,
                                   say=lambda line: click.echo(line))
    except (ValueError, one_off_load.LoadRefused) as exc:
        raise click.ClickException(str(exc)) from None
    failing = sum(1 for r in report["results"] if r.get("status") in ("fail", "error"))
    click.echo(f"Loaded {one_off_id} into {report['database']}: {len(report['runs'])} run(s), "
               f"{len(report['results'])} tool result(s), {failing} failing"
               + (f"; declared and not arrived: {', '.join(report['missing'])}"
                  if report["missing"] else "")
               + (f"; not declared, not filed: {', '.join(report['undeclared'])}"
                  if report["undeclared"] else "") + ".")
    # THE NEXT STEP (criterion 12).
    click.echo("\n".join(["Next: decide what to release, or publish it:",
                          f"  mothman one-off decide --id {one_off_id}",
                          f"  mothman one-off publish --id {one_off_id}"]))


@one_off_group.command("decide")
@id_option
@click.option("--decision", type=click.Choice(["release", "withhold"]), default=None,
              help="Release or withhold the whole one-off. Asked for where not given.")
@click.option("--reason", default=None, help="Why. Asked for where not given; required.")
@click.option("--yes", is_flag=True, help="Skip the one confirmation (the scripted form).")
def decide_command(one_off_id: str, decision: str | None, reason: str | None,
                   yes: bool) -> None:
    """Record one release-or-withhold decision for the WHOLE one-off, with a
    reason, once every dataset has a recorded outcome (REQ-PIPE-435). Recorded
    only - nothing is moved or sent. In filing_tui.apply_decision's order: who
    you are, any refusal, the reason, then one confirmation after the QA
    summary and the decision in force. The latest decision stands; every one is
    kept. Terminal only, never GitHub."""
    from qa_tools.common import git_identity, one_off_decision, people, supply_db

    chosen = choose(one_off_id)
    # 1. THE ACTOR, from git identity, against the kind's people.yaml read now.
    try:
        actor = people.person_by_email(git_identity.get_run_by())
    except (people.UnknownActor, git_identity.MissingGitIdentityError) as exc:
        raise click.ClickException(f"the decision was refused: {exc}") from None
    # 2. ANY REFUSAL, before a reason is asked for.
    with supply_db.connect(read_only=True, label="mothman:one-off-decide") as conn:
        summary = one_off_decision.qa_summary(conn)
        in_force = one_off_decision.standing(conn)
    refused = one_off_decision.refusal(summary)
    if refused:
        raise click.ClickException(f"the decision was refused: {refused}")
    if decision is None:
        decision = common.select("Release or withhold the whole one-off?",
                                 ["release", "withhold"],
                                 f"mothman one-off decide --id {one_off_id} --decision "
                                 f"release|withhold --reason <why> --yes")
        if decision is None:
            return
    # 3. THE REASON.
    if not (reason or "").strip():
        if not (sys.stdin.isatty() and sys.stdout.isatty()) and not yes:
            raise click.ClickException("a decision needs a reason - pass --reason. Nothing "
                                       "was recorded.")
        reason = "" if yes else click.prompt(common._named("Why?"), default="",
                                             show_default=False)
    if not (reason or "").strip():
        raise click.ClickException("a decision needs a reason, and none was given. Nothing "
                                   "was recorded.")
    # 4. THE QA SUMMARY AND THE DECISION IN FORCE, then one confirmation.
    click.echo(f"QA result of {one_off_id}, dataset by dataset:")
    for d in summary:
        click.echo(f"  {d.name} ({d.dataset_id}): {d.result}")
    unchecked = [d.dataset_id for d in summary if d.result == "Could not be checked"]
    if unchecked:
        click.echo(f"Could not be loaded or checked: {', '.join(unchecked)}.")
    click.echo("Decision in force: " + (one_off_decision.words(in_force) if in_force
                                         else "none recorded."))
    if not yes:
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            raise click.ClickException("no terminal to confirm at - pass --yes to record it "
                                       "without asking. Nothing was recorded.")
        if not common.confirm(f"Record '{decision}' for the whole of {one_off_id}?",
                              yes=False, default=False):
            click.echo("Not recorded.")
            return
    try:
        with supply_db.connect(label="mothman:one-off-decide") as conn:
            got = one_off_decision.record(conn, one_off_id, decision, reason, actor)
    except one_off_decision.DecisionRefused as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(f"Recorded: {one_off_decision.words(got).rstrip('.')}.")
    # THE PUBLISHED PAGE IS NOW BEHIND (REQ-PIPE-435 criterion 11), read from
    # the destination itself.
    from qa_tools.common import one_off_publish

    try:
        found = one_off_publish.published(chosen.kind, one_off_id)
    except one_off_publish.PublishRefused:
        found = None
    if found is not None:
        click.echo(f"The page published at {found.address} still shows the earlier state until "
                   f"{one_off_id} is published again: mothman one-off publish --id {one_off_id}")
    click.echo("Next: publish it, so its page carries the decision:\n"
               f"  mothman one-off publish --id {one_off_id}")


@one_off_group.command("drop")
@id_option
def drop_command(one_off_id: str) -> None:
    """Drop a one-off: its database supply_<id>, data/<id>/ and reports/<id>/
    (the dbt scratch among them), and its dbt target/, logs/ and dbt_packages -
    each listed with what it holds - once you type its id (REQ-PIPE-442
    criteria 6 to 8). No flag stands in for the typed id, and its committed
    configuration stays. A drop that stops part-way is finished by running it
    again."""
    from qa_tools.common import one_off_lifecycle

    chosen = choose(one_off_id)
    # THE TYPED ID ONLY (Keith 2026-11-21): no flag, no --yes, and no terminal
    # is a refusal in NeedsATerminal's words.
    try:
        common.require_tty("")
    except common.NotInteractive:
        raise common.NeedsATerminal(
            f"Dropping {one_off_id} removes its database and files, and has to be confirmed "
            f"by typing {one_off_id} at a terminal - no flag stands in for it. There is no "
            f"terminal here, so nothing was removed. Run it from one.") from None
    items = one_off_lifecycle.inventory()
    if not items:
        click.echo(f"{one_off_id} has nothing to remove: no database, no data/{one_off_id}/ "
                   f"and no reports/{one_off_id}/. Its committed configuration stays.")
        click.echo("Next: mothman one-off list")
        return
    click.echo(f"This removes, for {chosen.name} ({_word(chosen.kind)}):")
    for item in items:
        click.echo(f"  {item.what}: {item.holds}")
    click.echo(f"Its committed configuration, {chosen.folder}, stays.")
    # THE PUBLISHING WARNINGS (REQ-PIPE-443 criteria 8 and 9): no page means no
    # record will remain; a page older than the latest decision does not show
    # it, and publishing first is offered before the id is typed.
    warnings, offer = _drop_warnings(chosen)
    for line in warnings:
        click.echo(line)
    if offer and common.confirm(f"Publish {one_off_id} first, so its page shows every decision?",
                                yes=False, default=True):
        ctx = click.get_current_context()
        ctx.invoke(publish_command, one_off_id=one_off_id, yes=True)
    typed = click.prompt(common._named(f"Type {one_off_id} to remove them"), default="",
                         show_default=False)
    if typed.strip() != one_off_id:
        click.echo(f"Did not match {one_off_id!r} - nothing was removed.")
        return
    left = []
    for item in items:
        try:
            one_off_lifecycle.remove(item)
        except Exception as exc:  # noqa: BLE001 - each named, the rest still removed
            left.append(f"{item.what} ({type(exc).__name__}: {exc})")
            continue
        click.echo(f"Deleted {item.what}")
    if left:
        raise click.ClickException(
            "these could not be removed and remain: " + "; ".join(left)
            + f". Run `mothman one-off drop --id {one_off_id}` again to finish.")
    click.echo("Next: mothman one-off list")


def _drop_warnings(chosen) -> tuple[list[str], bool]:
    """The drop's publishing warnings, from the destination and the recorded
    decisions - or one saying they could not be read."""
    from qa_tools.common import one_off_decision, one_off_load, one_off_publish, supply_db

    decisions = []
    try:
        if one_off_load.database_name(chosen.name) in (_ages_or_none() or {}):
            with supply_db.connect(read_only=True, label="mothman:one-off-drop") as conn:
                decisions = one_off_decision.history(conn)
        return one_off_publish.drop_warnings(chosen.kind, chosen.name, decisions)
    except one_off_publish.PublishRefused as exc:
        return [f"Warning: whether {chosen.name} has a published page could not be read: {exc}"], \
            False


def _build_steps():
    """THE FOUR STEPS OF ANY ASSET'S BUILD (REQ-PIPE-443 criteria 1 and 2) -
    `mothman dashboard`'s own, and none of its publish()'s others."""
    from cli import dashboard as steps

    return [("Rebuilding check results from the recorded QA history...", steps._rebuild_results),
            ("Reshaping into dashboard JSON...", steps._build_data),
            ("Embedding...", steps._embed),
            ("Gate - dashboard structural + real-browser render check...", steps._check_renders)]


@one_off_group.command("publish")
@id_option
@click.option("--yes", is_flag=True, help="Skip the one confirmation (the scripted form).")
def publish_command(one_off_id: str, yes: bool) -> None:
    """Publish a one-off's QA page - one page named by its id, with its fonts/
    beside it - to the folder or S3 prefix its kind's template names, read now
    (REQ-PIPE-443). Shows the address, the decision in force and how many
    datasets are not yet checked, then asks (--yes confirms). Publishing again
    replaces its own page; another package's is never written over. Never from
    CI, and never to the recurring assets' hosting."""
    from qa_tools.common import one_off_decision, one_off_publish

    chosen = choose(one_off_id)
    try:
        planned = one_off_publish.plan(one_off_id)
    except one_off_publish.PublishRefused as exc:
        raise click.ClickException(f"nothing was published: {exc}") from None
    # WHAT IT WILL DO, BEFORE IT DOES IT (criterion 3; delivery-cli-ux C3): it
    # writes outside the repository to a place other people read.
    click.echo(f"Publishing {chosen.name} ({_word(chosen.kind)}) to: {planned.address}"
               + (" - replacing its own page there." if planned.replaces else ""))
    click.echo("Decision in force: " + (one_off_decision.words(planned.in_force)
                                         if planned.in_force else "none recorded - the page "
                                         "will say no release decision is recorded."))
    n = len(planned.not_yet_checked)
    click.echo(f"Datasets not yet checked: {n}"
               + (f" ({', '.join(planned.not_yet_checked)})" if n else "") + ".")
    if not yes:
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            raise click.ClickException("no terminal to confirm at - pass --yes to publish "
                                       "without asking. Nothing was published.")
        if not common.confirm(f"Publish {one_off_id}'s page to {planned.address}?", yes=False,
                              default=False):
            click.echo("Not published.")
            return
    try:
        address = one_off_publish.publish(planned, _build_steps(),
                                          say=lambda line: click.echo(line))
    except (one_off_publish.PublishRefused, click.ClickException) as exc:
        message = exc.format_message() if isinstance(exc, click.ClickException) else str(exc)
        raise click.ClickException(f"nothing was published: {message}") from None
    click.echo(f"Published -> {address}")
    # THE NEXT STEP (REQ-PIPE-442 criterion 12).
    click.echo("\n".join(["Next: record a decision, or drop it:",
                          f"  mothman one-off decide --id {one_off_id}",
                          f"  mothman one-off drop --id {one_off_id}"]))


@one_off_group.command("setup-dbt-utils")
def setup_dbt_utils_command() -> None:
    """Install this deployment's one local dbt_utils copy for one-offs, at the
    revision the enduring assets lock (REQ-PIPE-440 criterion 12). Run once per
    deployment; a load then makes no network fetch."""
    from qa_tools.common import one_off_load

    try:
        path = one_off_load.setup_dbt_utils()
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(f"dbt_utils {one_off_load.locked_revision()} installed at {path}.")


# ---- a per-asset gate over one one-off (REQ-PIPE-448, Keith 2026-11-22) ----

def _gate_argv(label: str) -> list[str]:
    from cli import check

    found = [argv for name, argv, _w, _c in check._GATES if name == label]
    if not found:
        raise KeyError(f"no gate called {label!r}")
    return found[0]


def run_in_process(label: str) -> int:
    """Run one gate in this process for the selected one-off - what `mothman
    one-off gate --id` does. Its argv is the gate's own: a module run as
    __main__, or a mothman command invoked."""
    import runpy
    import sys

    argv = _gate_argv(label)
    tail = argv[2:] if argv[:2] == ["uv", "run"] else argv
    try:
        if tail[:2] == ["python3", "-m"]:
            before = sys.argv
            sys.argv = [tail[2], *tail[3:]]
            try:
                runpy.run_module(tail[2], run_name="__main__")
            finally:
                sys.argv = before
            return 0
        if tail[:1] == ["mothman"]:
            from cli.app import cli

            cli.main(args=tail[1:], prog_name="mothman", standalone_mode=False)
            return 0
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
    except Exception as exc:  # noqa: BLE001 - a gate that raises has failed, said
        print(f"{label}: {type(exc).__name__}: {exc}")
        return 1
    raise ValueError(f"gate {label!r} has no in-process form ({' '.join(argv)})")




@one_off_group.command("gate", hidden=True)
@id_option
@click.option("--root", "root", default=None, hidden=True,
              help="The one-offs root, where `mothman check` was pointed elsewhere.")
@click.argument("label")
def gate_command(one_off_id: str, root: str | None, label: str) -> None:
    """Run one of `mothman check`'s per-asset gates for one one-off, in this
    process - what `mothman check` runs over a changed one-off folder. Hidden:
    a person runs `mothman check`."""
    from pathlib import Path

    if root:
        assets.use_one_offs_root(Path(root))
    choose(one_off_id)
    code = run_in_process(label)
    if code:
        raise SystemExit(code)

