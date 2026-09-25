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
        # LOADED IS A SEPARATE QUESTION FROM RECOGNISED, and showing
        # them side by side is the point (REQ-PIPE-060 criterion 16):
        # a delivery can be perfectly recognised and only half staged,
        # and without this the half-staged one looks identical to the
        # healthy one.
        from qa_tools.common import load_log, supply_db
        done = load_log.latest_by_table()

        table = Table("Delivery", "Received", "Attributed to", "Loaded", "Notes",
                       box=None, pad_edge=False)
        for d in received:
            placed, notes, _collections = _describe(d, seen[d.name],
                                                     detailed=wanted is not None)
            expected = supply_db.expected_tables(seen[d.name], d.received_at)
            loaded = sum(1 for name in expected.values()
                          if name in done and done[name].loaded)
            if not expected:
                state = "[dim]-[/dim]"
            elif loaded == len(expected):
                state = f"{loaded}/{len(expected)}"
            else:
                # PARTIAL IS THE STATE WORTH SEEING. A delivery is
                # processed only where every file attributed to a
                # dataset has a load record, so anything short of that
                # is a delivery the next run must process again.
                state = f"[yellow]{loaded}/{len(expected)}[/yellow]"
            table.add_row(d.name, display_time.format_instant(d.received_at), placed,
                           state, notes)
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
    fail a run: attributing one by elimination - "the
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


@supply_group.command("log")
@click.option("--sql", "as_sql", is_flag=True,
               help="Print the SQL that reads the log, instead of the log itself.")
def log_command(as_sql: bool) -> None:
    """The committed record of what arrived (REQ-PIPE-069).

    One file per delivery, written once at recognition and never
    rewritten. It holds RECOGNITION facts - what arrived and what we
    thought it was - and never load outcomes, which happen later and
    live in their own record.
    """
    from qa_tools.common import delivery_log

    if as_sql:
        # QUERYABLE DIRECTLY FROM THE COMMITTED FILES (criterion 4):
        # DuckDB reads them off disk and joins them against the staging
        # and period schemas with nothing synced and nothing
        # duplicated. Printed rather than run, because running it means
        # opening a database and the committed-history path may not.
        console.print(delivery_log.sql())
        return

    found = delivery_log.records()
    if not found:
        console.print("No delivery has been logged yet. The log fills as the pipeline runs.")
        return

    from qa_tools.common import asset_time, display_time

    table = Table("Delivery", "Received", "Files", "Attributed", "Other",
                   box=None, pad_edge=False)
    for record in found:
        files = record.get("files") or []
        attributed = sum(1 for f in files if f.get("dataset_id"))
        other = len(files) - attributed
        table.add_row(
            record.get("delivery", ""),
            display_time.format_instant(
                asset_time.parse_instant(record["received_at"], "delivery log")),
            str(len(files)), str(attributed),
            f"[yellow]{other}[/yellow]" if other else "0")
    console.print(table)
    console.print(f"\n[dim]{len(found)} delivery record(s). "
                   f"`--sql` prints how to query them.[/dim]")


@supply_group.command("load")
@click.option("--collection", "collection_id", default=None,
               help="One collection only. Both are staged when this is left out.")
def load_command(collection_id: str | None) -> None:
    """Stage every recognised delivery into the supply database.

    Loads what has arrived, and nothing else: no period, no slot, no
    supersession. A file that cannot be loaded leaves no table and is
    listed by `mothman supply failures`.
    """
    # ARRIVAL IS THE ONLY TRIGGER (REQ-PIPE-060 criterion 10). Nothing
    # here asks which period a supply belongs to or what it supersedes,
    # because none of that is known at arrival and staging may not be
    # wrong about anything.
    #
    # SEQUENTIAL, DELIBERATELY (criterion 9). One DuckDB file takes one
    # writer, and a staging fan-out would have workers of a single
    # invocation collide on its lock. Staging is serial and the tools
    # fan out afterwards, over views that are already built.
    from qa_tools.common import load_log

    known = {"bdm": ("civil-registration", "qa_tools.bdm.build_per_run_warehouses"),
             "cp": ("child-protection", "qa_tools.cp.build_cp_warehouses")}
    if collection_id is not None and collection_id not in known:
        raise click.ClickException(
            f"unknown collection {collection_id!r} - one of {', '.join(sorted(known))}")

    before = set(load_log.loaded_tables())
    failed_before = {r.physical for r in load_log.failures()}
    records_before = len(load_log.records())

    import importlib

    for key in sorted(known) if collection_id is None else [collection_id]:
        _collection, module = known[key]
        console.print(f"[bold]{key}[/bold] - staging every recognised delivery")
        importlib.import_module(module).build_all()

    staged = sorted(set(load_log.loaded_tables()) - before)
    changed = len(load_log.records()) - records_before
    # TWO DIFFERENT NUMBERS, and saying only the first was misleading
    # in practice: a re-run of an unchanged delivery loads every table
    # again and makes NOTHING newly readable, which read as "0 table(s)
    # newly loaded" over a page of successful staging.
    console.print(f"\n{len(staged)} table(s) newly readable, "
                   f"{changed} load record(s) written "
                   f"[dim](an unchanged re-stage writes none)[/dim].")
    new_failures = [r for r in load_log.failures() if r.physical not in failed_before]
    if new_failures:
        console.print(f"[red]{len(new_failures)} failed to load[/red] "
                       f"[dim]- `mothman supply failures` for the queue[/dim]")


@supply_group.command("failures")
def failures_command() -> None:
    """Loads that failed, and are waiting on a person.

    Never retried on their own: the call is yours, and it is either to
    reject that supply or to fix the cause and stage it again. Reads
    committed records only - no database is opened.
    """
    # A REPROCESS NEEDS NO SPECIAL HANDLING (REQ-PIPE-060 criteria 17
    # and 19). The FILE is unchanged and our ability to read it
    # changed, and deliveries are immutable on disk, so staging again
    # re-reads the same bytes and writes a NEW record rather than
    # editing this one - the history of what went wrong survives the
    # fix.
    from qa_tools.common import asset_time, display_time, load_log

    found = load_log.failures()
    if not found:
        console.print("No load is currently recorded as failed.")
        return
    console.print(f"[red]{len(found)} load(s) failed[/red] "
                   f"[dim]- reject the supply, or fix and reprocess[/dim]\n")
    table = Table("Delivery", "Dataset", "Recorded", "Why", box=None, pad_edge=False)
    for record in found:
        table.add_row(
            record.delivery, record.dataset_id,
            display_time.format_instant(
                asset_time.parse_instant(record.recorded_at, "processing log")),
            record.reason or "unrecorded")
    console.print(table)
