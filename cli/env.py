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
