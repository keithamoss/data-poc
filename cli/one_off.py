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


def _rows() -> list[tuple[str, str, str]]:
    """(id, kind's singular display word, project) for every one-off found."""
    from asset_model import config_yaml, one_off_kinds

    out = []
    for kind, name in assets.one_offs():
        plug = one_off_kinds.get(kind)
        doc = config_yaml.load(assets.one_offs_root() / kind / name / "data-asset.yaml") \
            if (assets.one_offs_root() / kind / name / "data-asset.yaml").is_file() else {}
        out.append((name, plug.singular if plug else kind,
                    str((doc or {}).get("project") or "(no project named)")))
    return out


@click.group("one-off", invoke_without_command=True)
@click.pass_context
def one_off_group(ctx: click.Context) -> None:
    """One-offs - browse and select one in the TUI (bare `mothman one-off`),
    or name it with --id in a step. Runs with MOTHMAN_ASSET unset."""
    refuse_an_asset_beside()
    if ctx.invoked_subcommand is None:
        common.require_tty("mothman one-off list (every one-off), then a step with --id <id>")
        _tui()


def _tui() -> None:
    """Browse the one-offs and select one (Keith 2026-11-21, CLI Q1 (a))."""
    rows = _rows()
    if not rows:
        console.print(f"No one-offs found under {assets.one_offs_root()}.", style="yellow")
        return
    labels = {f"{name}  ({word}) - {project}": name for name, word, project in rows}
    picked = common.select("Which one-off?", list(labels),
                           "mothman one-off list, then a step with --id <id>")
    if picked is None:
        return
    chosen = choose(labels[picked])
    console.print(f"One-off: {chosen.name} ({_word(chosen.kind)}), folder {chosen.folder}.",
                  style="green")


def _word(kind: str) -> str:
    from asset_model import one_off_kinds

    plug = one_off_kinds.get(kind)
    return plug.singular if plug else kind


@one_off_group.command("list")
def list_command() -> None:
    """Every one-off found, one per line: its id, its kind and its project.
    Reads folder names and each one's data-asset.yaml; opens no connection."""
    rows = _rows()
    if not rows:
        click.echo(f"No one-offs found under {assets.one_offs_root()}.")
        return
    widths = [max(len(r[i]) for r in rows) for i in range(2)]
    for name, word, project in rows:
        click.echo(f"{name.ljust(widths[0])}  {word.ljust(widths[1])}  {project}")
