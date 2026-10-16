"""mothman env - which deployment is this, and what are the others.

Tier 2. Small, but it earns a command rather than living as a library
call: once the dashboard is built where the data is, "which environment
am I about to publish from" is a question somebody asks out loud before
running something irreversible.
"""
from __future__ import annotations

import rich_click as click
from rich.console import Console
from rich.table import Table

console = Console()


@click.group("env")
def env_group() -> None:
    """The deployment this checkout is acting as - Tier 2."""


@env_group.command("list")
def list_command() -> None:
    """Every declared environment, and which one this is."""
    from qa_tools.common import environments

    here = environments.current_or_none()
    table = Table(title="Declared environments (contract/environments.yaml)")
    table.add_column(""), table.add_column("id"), table.add_column("Label")
    table.add_column("Publishes"), table.add_column("What it is")
    for env in environments.all_environments():
        table.add_row(
            "->" if here and env.id == here.id else "",
            env.id, env.label,
            "yes" if env.publishes else "",
            env.description.replace("\n", " ").strip())
    console.print(table)
    if here is None:
        console.print(
            f"\n{environments.ENVIRONMENT_ENV} is not set, so this checkout cannot "
            f"say which of these it is. Nothing that publishes will run until it "
            f"does - deliberately.", style="yellow")


@env_group.command("current")
def current_command() -> None:
    """Which environment this checkout is acting as. Fails if unset."""
    from qa_tools.common import environments

    # A CONFIG MISTAKE IS NOT A CRASH. Unset or mistyped is the normal
    # way to get this wrong, and a traceback buries the one sentence
    # that says how to fix it.
    try:
        env = environments.current()
    except environments.EnvironmentError_ as exc:
        raise click.ClickException(str(exc)) from None
    console.print(f"{env.id} - {env.label}", style="green")
    if env.publishes:
        console.print("This is the publishing environment.", style="bold yellow")


@env_group.command("reset-synthetic")
def reset_synthetic_command() -> None:
    """Delete this SYNTHETIC asset's whole QA history, to start from empty.

    Deliveries, delivery files, filings, holds, decisions, runs and results,
    and every schema holding supply rows - rebuild-from-empty made explicit
    (REQ-PIPE-144). Refused unless contract/data-asset.yaml declares the asset
    synthetic, and only after you type a phrase naming what goes. Follow it
    with `mothman pipeline bootstrap`.
    """
    from qa_tools.common import supply_db, synthetic_reset

    if synthetic_reset.in_production():
        raise click.ClickException("this checkout is acting as `production` - nothing "
                                   "was deleted.")
    if not synthetic_reset.is_synthetic():
        raise click.ClickException(
            f"{synthetic_reset.asset_id()} is not declared synthetic in "
            f"contract/data-asset.yaml - its history is treated as real, and "
            f"nothing was deleted.")
    with supply_db.connect(label="mothman:reset-synthetic") as conn:
        counts = synthetic_reset.what_it_deletes(conn)
        schemas = synthetic_reset.schemas_to_drop(conn)
    console.print(f"This deletes ALL recorded QA history for "
                  f"{synthetic_reset.asset_id()}:", style="bold yellow")
    for table, n in counts.items():
        console.print(f"  {table}: {n} row(s)")
    console.print(f"  and {len(schemas)} schema(s): {', '.join(schemas) or 'none'}")
    phrase = synthetic_reset.confirmation_phrase()
    from cli import common

    typed = click.prompt(common._named(f'Type "{phrase}" to delete it'), default="",
                         show_default=False)
    with supply_db.connect(label="mothman:reset-synthetic") as conn:
        try:
            # EXACTLY THE SCHEMAS SHOWN, not a list read again afterwards -
            # a schema created in between must not be dropped unseen.
            dropped = synthetic_reset.reset(conn, typed, schemas=schemas)
        except (synthetic_reset.NotSynthetic, synthetic_reset.WouldReachOutside,
                ValueError) as exc:
            raise click.ClickException(str(exc)) from None
    console.print(f"Deleted {len(dropped)} schema(s). Run `mothman pipeline bootstrap` "
                  f"to regenerate.", style="green")
    # A DROPPED SCHEMA TAKES ITS GRANTS WITH IT, so a least-privilege
    # publisher role set up on it can no longer read anything.
    console.print("If a publisher role was set up, grant it again afterwards: "
                  "`mothman supply grant-publisher`.", style="dim")


@env_group.command("mark")
@click.option("--confirm", "typed", metavar="ENVIRONMENT_ID", default=None,
              help="The environment id, typed on the command line - for a setup script "
                   "with no terminal. Without it you are asked to type it.")
def mark_command(typed: str | None) -> None:
    """Record in the database which data asset and environment it belongs to.

    Every other command refuses a database whose recorded identity is missing
    or differs from this checkout's (REQ-PIPE-107), and none of them ever
    writes it - this is the only way it gets there. The identity written is
    this checkout's: the data asset in contract/data-asset.yaml and the
    environment stated in MOTHMAN_ENVIRONMENT, which you type to confirm.
    """
    from cli import common
    from qa_tools.common import db_identity, environments, supply_db

    try:
        want = db_identity.expected()
    except environments.EnvironmentError_ as exc:
        raise click.ClickException(str(exc)) from None
    if typed is None:
        try:
            common.require_tty("pass --confirm <environment id>")
        except common.NotInteractive as exc:
            raise click.ClickException(str(exc)) from None
        typed = common._ask_text(
            f"Type the environment id to mark this database as {want}") or ""
    # TYPED, NOT DEFAULTED (criterion 2): the stated environment is what gets
    # written, and the person has to say it back.
    if typed.strip() != want.environment:
        raise click.ClickException(
            f"that did not read {want.environment!r}, so nothing was marked.")
    with supply_db.connect(label="mothman:env-mark", for_marking=True) as conn:
        try:
            _, found = db_identity.read(conn)
        except db_identity.IdentityRefused as exc:
            found, unreadable = None, str(exc)
        else:
            unreadable = None
        if found == want:
            console.print(f"This database is already marked as {want}. Nothing changed.",
                          style="green")
            return
        if found is not None or unreadable:
            # ANOTHER IDENTITY IS NEVER OVERWRITTEN BY ACCIDENT (criterion 3),
            # AND NEVER BY FLAGS (REQ-PIPE-093 criteria 4 and 6; post-build-
            # review #119 D1): --confirm stands in for typing only to mark an
            # UNMARKED database, which is the setup scripts' whole need.
            # Replacing one - a production database relabelled, or relabelled
            # as production - needs a person at a terminal, typing out what is
            # being replaced. The expected text is never printed for them to
            # copy.
            what = (f"is already marked as {found}" if found
                    else f"has an unreadable identity ({unreadable})")
            try:
                common.require_tty("replacing a database's identity needs a person at a "
                                   "terminal; no flag stands in for that")
            except common.NotInteractive:
                raise click.ClickException(
                    f"this database {what}. Replacing an identity needs a person at a "
                    f"terminal; nothing was marked.") from None
            current = f"{found.data_asset_id}/{found.environment}" if found else "unreadable"
            console.print(f"This database {what}.", style="yellow")
            said = (common._ask_text(
                "Type the identity being replaced, as <data asset>/<environment> "
                "(or 'unreadable')") or "").strip()
            if said != current:
                raise click.ClickException("that is not the identity being replaced, so "
                                           "nothing was marked.")
        db_identity.mark(conn, want)
    console.print(f"Marked this database as {want}.", style="green")
