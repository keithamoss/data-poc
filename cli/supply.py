"""mothman supply - what actually arrived (REQ-PIPE-057).

ITS OWN GROUP, Tier 1, and the argument had already run once so this
follows rather than re-derives it (REQ-PIPE-050, Keith 2026-09-24).
delivery-architect argued for folding into `pipeline` on taxonomy
grounds and lost, because cli/pipeline.py's own docstring calls that
group "not human-facing - for integration tests and for yourself", and
somebody looking at what a supplier sent is exactly a human. That same
decision rejected the obvious compromise by name - fold in now, move to
a `mothman supply` group when batches 3-6 justify one - because moving a
command later breaks whatever docs and muscle memory have formed, and
renames are how a CLI surface rots. This is that batch, and this is the
group it named.

A NAMING CAVEAT, accepted knowingly: a SUPPLY is the per-dataset unit
and a DELIVERY is the transport unit, so a group called `supply` listing
deliveries is not perfectly precise. It is the word a person reaches
for, and the alternative was a group called `delivery` that would then
be the wrong home for everything after sprint 10.

WHAT THIS GROUP WILL NEVER DO, because it will be re-proposed and each
proposal reads as an obvious convenience (Keith, 2026-09-24): show a
count of holds, a queue to work through, or a "you have N things
waiting" line on the bare command. His reason is stronger than the
convenience it defeats - ANY SUCH COUNT WOULD BE STALE BY CONSTRUCTION,
because the records live in committed history and a local `mothman`
reads the operator's own CHECKOUT. A wrong count on the front door is
worse than no count, and a command that fetched to fix it would stop
being a local operation. The standing division: the CLI DOES things, the
DASHBOARD SEES things.

So this command reports what recognition makes of the deliveries ON THIS
MACHINE, right now, which is a question about local state and therefore
one the CLI can answer honestly.
"""
from __future__ import annotations

import rich_click as click
from rich.console import Console
from rich.table import Table

from qa_tools.common import arrivals, delivery, hierarchy

console = Console()


@click.group("supply")
def supply_group() -> None:
    """Deliveries - what arrived, and what could not be placed."""


def _describe(d: delivery.Delivery, found, detailed: bool = False) -> tuple[str, str, str]:
    """One delivery as a row.

    SUMMARISED BY DEFAULT, in full only for a named one. Listing every
    dataset wraps a row to six lines, which is tolerable at this PoC's
    sixty deliveries and unreadable at the thousands this is a PoC for -
    and the question the list answers is "did anything odd arrive",
    which a count answers as well as a roll-call does.
    """
    if found.is_unplaceable:
        placed = "[yellow]nothing recognised[/yellow]"
    elif detailed:
        placed = ", ".join(
            f"{ds} ({len(names)})" for ds, names in sorted(found.by_dataset.items()))
    else:
        n = len(found.by_dataset)
        placed = f"{n} dataset{'' if n == 1 else 's'} - {', '.join(found.collections)}"
    notes = []
    if found.unmatched:
        notes.append(f"[yellow]{len(found.unmatched)} unrecognised[/yellow]")
    if found.contested:
        notes.append(f"[red]{len(found.contested)} claimed twice[/red]")
    if d.anomalies:
        notes.append(f"{len(d.anomalies)} anomal{'y' if len(d.anomalies) == 1 else 'ies'}")
    return placed, ", ".join(notes), ", ".join(found.collections)


@supply_group.command("deliveries")
@click.option("--name", "wanted", default=None,
               help="One delivery, by name. Validated before anything is opened.")
def deliveries_command(wanted: str | None) -> None:
    """What recognition makes of the deliveries on this machine.

    Reports; changes nothing. An unrecognised artefact, a delivery
    nothing can place and a delivery still in flight are all ordinary
    operational states rather than errors, so none of them makes this
    exit non-zero.
    """
    from qa_tools.common import display_time

    if wanted is not None:
        # VALIDATED AT THE CLI BOUNDARY. A delivery name is
        # supplier-controlled input that becomes a path, and until this
        # command existed the name always came from iterdir(), which is
        # why read_delivery() never validated one. Taking it as an
        # argument closes that loop rather than relying on it.
        wanted = delivery.validate_delivery_name(wanted)

    survey = delivery.survey()
    received = [d for d in survey.received if wanted is None or d.name == wanted]
    in_flight = [f for f in survey.in_flight if wanted is None or f.name == wanted]

    if wanted is not None and not received and not in_flight:
        raise click.ClickException(
            f"no delivery named {wanted!r} is present. `mothman supply deliveries` "
            f"lists what is.")

    if not survey.received and not survey.in_flight:
        # Not a failure, and not an empty table either: a freshly-cloned
        # machine has no data/ at all, and "nothing has arrived" is a
        # real answer worth saying in words (criterion 16).
        console.print("No deliveries are present on this machine.")
        return

    # RECOGNISED ONCE PER DELIVERY, not once per thing we want to say
    # about it. Three separate calls was three passes over every file
    # and three copies of every warning - and reading each delivery
    # once per run is this requirement's own scaling constraint.
    seen = {d.name: arrivals.recognise(d) for d in received}

    if received:
        table = Table("Delivery", "Received", "Attributed to", "Notes",
                       box=None, pad_edge=False)
        for d in received:
            placed, notes, _collections = _describe(d, seen[d.name],
                                                     detailed=wanted is not None)
            table.add_row(d.name, display_time.format_instant(d.received_at), placed, notes)
        console.print(table)

    if in_flight:
        # IN FLIGHT IS THE NORMAL CASE, not an edge one: under a real
        # transport a delivery has no receipt until our own boundary
        # rule says the drop is complete. The FILE NAMES are shown
        # rather than a count, because the question worth asking is
        # "is anything stuck" - a list going 2, 4, 6 across runs reads
        # as an upload progressing, and one stuck at 2 reads as one
        # that died.
        console.print(f"\n[bold]{len(in_flight)} in flight[/bold] "
                       f"[dim]- present, with no receipt record yet, so not processed[/dim]")
        for entry in in_flight:
            files = ", ".join(entry.files) or "no files yet"
            console.print(f"  {entry.name} [dim]- {files}[/dim]")

    if wanted is not None:
        for d in received:
            found = seen[d.name]
            for label, names in (("unrecognised", found.unmatched),
                                  ("anomalies", d.anomalies)):
                if names:
                    console.print(f"\n[bold]{label}[/bold]")
                    for name in names:
                        console.print(f"  {name}")

    spanning = [d for d in received if len(seen[d.name].collections) > 1]
    if spanning:
        console.print(f"\n[dim]{len(spanning)} deliver{'y' if len(spanning) == 1 else 'ies'} "
                       f"span more than one collection, which is legitimate - each file is "
                       f"attributed on its own dataset's terms.[/dim]")


@supply_group.command("unplaceable")
def unplaceable_command() -> None:
    """Deliveries nothing could place - reported, never guessed at.

    A delivery where no file matched any dataset's pattern. It does not
    fail a run (criterion 13): attributing one by elimination - "the
    only thing in a Birth Registrations delivery must be Birth
    Registrations" - is how a garbage file quietly becomes a supply.
    """
    found = arrivals.unplaceable()
    if not found:
        console.print("Every delivery present has at least one file that was placed.")
        return
    console.print(f"[yellow]{len(found)} unplaceable deliver"
                   f"{'y' if len(found) == 1 else 'ies'}[/yellow]")
    for d in found:
        # The artefact's NAME, never its contents - a filename in a
        # Birth Registrations or Child Protection context is itself
        # potentially identifying.
        console.print(f"  {d.name} [dim]- {', '.join(d.files) or 'empty'}[/dim]")


@supply_group.command("datasets")
def datasets_command() -> None:
    """Which filenames each dataset claims (REQ-PIPE-058).

    The question somebody asks when a supply went missing: did the
    pattern stop matching? Config only - opens no delivery and no
    database.
    """
    table = Table("Dataset", "Collection", "Arrival pattern", box=None, pad_edge=False)
    for entry in hierarchy.all_datasets():
        table.add_row(entry.dataset_id, entry.collection_id,
                       entry.arrival_pattern or "[red]none declared[/red]")
    console.print(table)
