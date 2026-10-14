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

IT USED TO SAY THIS GROUP WOULD NEVER SHOW A QUEUE, and that has been
reversed knowingly rather than forgotten (REQ-GHUB-082 criterion 16,
signed 2026-09-28; REQ-PIPE-057's decisions 22 and 23 amended the same
day this landed). The old rule was right for the reason it gave: a count
would be STALE BY CONSTRUCTION, because the records lived in committed
history and a local `mothman` read the operator's own CHECKOUT, so a
front-page number was a count as of whenever they last pulled.

THE REASON STOPPED BEING TRUE, which is why the rule went with it.
REQ-PIPE-089 moved the records into the database, and every `mothman`
pointed at it reads the same rows as everybody else - so `mothman supply
queue` is as current as the dashboard, without fetching anything. What
the old rule protected against was a wrong number presented as a live
one, and that failure mode no longer has a mechanism.

WHAT SURVIVES OF IT, and is worth keeping: there is still no count on
the bare command. A queue is something you go and look at, not something
the front door shouts at you, and at thirty datasets a standing number
in the banner is the thing people stop seeing.

So this group both DOES things and, now, shows the state those things
act on - because both questions are answered by the one database rather
than by a checkout that may be a week old.
"""
from __future__ import annotations

import sys
from pathlib import Path

import rich_click as click
from rich.console import Console
from rich.table import Table

from cli import common
from qa_tools.common import (arrivals, asset_time, decision_log, delivery,
                             filing_decisions, hierarchy, people, supply_db)

console = Console()


#: The short names `mothman pipeline run --collection` takes, accepted here
#: too so one collection is not spelled two ways across the CLI.
_SHORT_COLLECTION = {"bdm": "civil-registration", "cp": "child-protection"}


def _collection(ctx, param, value):
    """A --collection value, as a collection id - or a usage error naming the
    known ones (#123 CLI side-find: an unknown name died in a traceback)."""
    if value is None:
        return None
    value = _SHORT_COLLECTION.get(value, value)
    known = sorted({d.collection_id for d in hierarchy.all_datasets()})
    if value not in known:
        raise click.BadParameter(
            f"{value!r} is not a collection. Known: {', '.join(known)} "
            f"(or bdm, cp).", ctx=ctx, param=param)
    return value


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

        table = Table("Delivery", "Received", "Filed", "Attributed to", "Loaded", "Notes",
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
            table.add_row(d.name, display_time.format_instant(d.received_at),
                           _filed_by_text(d), placed, state, notes)
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
            if d.stated_original:
                # BESIDE THE RECEIPT, LABELLED AS THE FILER'S STATEMENT
                # (REQ-PIPE-103 criterion 19) - never presented as it.
                console.print("\n[bold]originally received[/bold] "
                              "[dim](stated by the person who filed it; recorded, "
                              "never used)[/dim]")
                for name, value in sorted(d.stated_original.items()):
                    console.print(f"  {name}  {_stated_text(value)}")
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


def _filed_by_text(d) -> str:
    """Whether a person filed it, by which route and who (REQ-PIPE-147
    criterion 7) - the person resolved through contract/people.yaml."""
    from qa_tools.common import people

    filed_by = getattr(d, "filed_by", None) or {}
    if filed_by.get("kind") != "person":
        return "[dim]automatically[/dim]"
    stated = sorted({_stated_text(v) for v in (d.stated_original or {}).values()})
    note = f"; originally {', '.join(stated)} (stated)" if stated else ""
    return f"by hand ({filed_by.get('route')}) - {people.display_name(filed_by.get('who'))}{note}"


def _stated_text(value: str) -> str:
    from qa_tools.common import delivery as delivery_mod
    from qa_tools.common import display_time

    return "not known" if value == delivery_mod.NOT_KNOWN else display_time.format_instant(value)


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
@click.option("--collection", "collection_id", callback=_collection, default=None,
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
        console.print(f"[red]{len(new_failures)} could not be loaded[/red] "
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
    from qa_tools.common import asset_time, dataset_blockers, display_time

    # A SUPPLY A PERSON HAS REJECTED IS SETTLED, and is not listed again
    # (REQ-PIPE-153 criterion 4).
    found = dataset_blockers.unsettled_failures()
    if not found:
        console.print("No supply is waiting because it could not be loaded.")
        return
    console.print(f"[red]{len(found)} supply/supplies could not be loaded[/red] "
                   f"[dim]- reject the supply, or fix and reprocess[/dim]\n")
    table = Table("Delivery", "Dataset", "Recorded", "Why", box=None, pad_edge=False)
    for record in found:
        table.add_row(
            record.delivery, record.dataset_id,
            display_time.format_instant(
                asset_time.parse_instant(record.recorded_at, "processing log")),
            record.reason or "unrecorded")
    console.print(table)


@supply_group.command("history")
@click.option("--dataset", "dataset_id", required=True,
               help="The dataset whose own arrival timeline to show.")
@click.option("--limit", default=15, show_default=True,
               help="How many of the most recent arrivals to list.")
def history_command(dataset_id: str, limit: int) -> None:
    """One dataset's own arrival timeline.

    A file resent for this table appears here on its own, not folded
    into a delivery of other tables that did not change - and the
    tables that shared that delivery gain nothing from it.

    RECORDED IN THE DATABASE since REQ-PIPE-104 - this used to read a
    gitignored `filings/` tree, which would have started committing state
    to the repository the day REQ-PIPE-062 turned recording on.
    """
    from qa_tools.common import arrival_history, asset_time, display_time, hierarchy

    # Fails on an unknown id before anything is read, so the error is
    # about what was typed rather than about an empty result.
    hierarchy.dataset(dataset_id)

    found = arrival_history.arrivals_of(dataset_id)
    if not found:
        console.print(f"No arrival of {dataset_id} has been recorded yet.")
        return

    latest = found[-1]
    console.print(f"[bold]{dataset_id}[/bold] - {len(found)} arrival(s) recorded")
    console.print(f"Most recent arrival: [bold]{latest.supply_id}[/bold] "
                   f"[dim]({display_time.format_instant(asset_time.parse_instant(latest.received_at, 'arrival history'))})[/dim]")
    # SAID IN WORDS, not left as a blank column. The promoted version is
    # a different question from the arrived one and they diverge exactly
    # when it matters - a broken file arriving while the warehouse still
    # holds the good one - so silence here would read as "same thing".
    console.print("[dim]Most recent PROMOTED supply: not tracked yet - promotion is a later "
                   "sprint, and reporting the latest arrival as promoted is the conflation "
                   "this deliberately avoids.[/dim]\n")

    table = Table("Arrival", "Received", "Delivery", "Arrived with", box=None, pad_edge=False)
    for entry in reversed(found[-limit:]):
        others = [d for d in arrival_history.delivery_companions(entry.delivery)
                   if d != dataset_id]
        table.add_row(
            entry.supply_id,
            display_time.format_instant(
                asset_time.parse_instant(entry.received_at, "arrival history")),
            entry.delivery,
            f"{len(others)} other dataset(s)" if others else "[dim]on its own[/dim]")
    console.print(table)


@supply_group.command("filings")
@click.option("--dataset", "dataset_id", required=True,
               help="The dataset whose filings to show.")
@click.option("--limit", default=15, show_default=True,
               help="How many of the most recent filings to list.")
def filings_command(dataset_id: str, limit: int) -> None:
    """Which slot each of this dataset's supplies was filed against.

    Says WHY, not just where: the rule branch is recorded when the
    filing is made, because recomputing it later gives a different
    answer - the slot state it was decided against has moved on.

    Reads committed records only. No database is opened.
    """
    from qa_tools.common import assignment, filing, hierarchy

    hierarchy.dataset(dataset_id)
    found = filing.filings_of(dataset_id)
    if not found:
        console.print(f"No supply of {dataset_id} has been filed yet.")
        return

    readable = {
        assignment.OPEN_UNFILLED: "the period open when it arrived",
        assignment.RESUPPLY: "resupply - the open period was already filled",
        assignment.HELD: "[yellow]no period was open for it - held for a person[/yellow]",
    }
    placed = _placements(dataset_id)
    console.print(f"[bold]{dataset_id}[/bold] - {len(found)} supply/supplies filed\n")
    table = Table("Supply", "Filed against", "Why", box=None, pad_edge=False)
    for record in found[-limit:]:
        why = readable.get(record.get("branch", ""), record.get("branch", ""))
        if record.get("supply_id") in placed:
            # Said as a placement (REQ-PIPE-163 criterion 41), by whoever made
            # it - the rule places held supplies too (#188 D5).
            from qa_tools.common import placing

            by = "the rule" if placed[record.get("supply_id")] == "rule" else "a person"
            why = f"{placing.said(record.get('slot'))} by {by}, from held"
        table.add_row(record.get("supply_id", ""),
                       record.get("slot") or "[yellow]unfiled[/yellow]", why)
    console.print(table)


def _placements(dataset_id: str) -> dict[str, str]:
    """{supply: actor_kind} for the supplies whose current filing PLACED them
    from held - a re-file from no period (REQ-PIPE-163 criterion 2)."""
    from qa_tools.common import decision_log, filing, supply_db

    with supply_db.connect(read_only=True, label="mothman:supply-filings") as conn:
        return {r[0]: r[1] for r in conn.execute(
            f"SELECT f.supply_id, d.actor_kind FROM {filing.CURRENT} f JOIN {decision_log.TABLE} d "
            "ON d.id = f.refiled_by WHERE f.dataset_id = ? AND d.action = ? "
            "AND d.from_slot IS NULL AND d.to_slot IS NOT NULL",
            [dataset_id, decision_log.REFILE]).fetchall()}


@supply_group.command("decisions")
@click.option("--dataset", "dataset_id", default=None,
               help="One dataset's decisions. Omit for the whole log.")
@click.option("--as-at", "as_at", default=None,
               help="What the log said at a past instant - an ISO timestamp. "
                    "Reads the instant a decision TOOK EFFECT, not when it was "
                    "recorded, so a decision made in January and written up in "
                    "March counts from January.")
@click.option("--limit", default=20, show_default=True,
               help="How many entries to list.")
def decisions_command(dataset_id: str | None, as_at: str | None, limit: int) -> None:
    """Who decided what happened to a supply, and why (REQ-PIPE-091).

    The single system of record for every filing decision - promote,
    reject, demote and re-file. It is append-only and the database
    enforces that, so what this prints is what was decided rather than
    what somebody tidied up afterwards.

    READ-ONLY, and that is the point of having it: criterion 10 is that
    the whole history is readable without write access, and a log nobody
    can read is a log nobody trusts.
    """
    from qa_tools.common import (decision_log, display_time, hierarchy, qa_store,
                                  supply_db)

    if dataset_id:
        hierarchy.dataset(dataset_id)

    with supply_db.connect(read_only=True, label="mothman:supply-decisions") as conn:
        qa_store.ensure_schema(conn)
        entries = (decision_log.decisions_for(conn, dataset_id, as_at=as_at)
                    if dataset_id else decision_log.all_decisions(conn, limit=limit))
        promoted = (decision_log.promoted_supply(conn, dataset_id, as_at=as_at)
                     if dataset_id else None)

    where = f" for [bold]{dataset_id}[/bold]" if dataset_id else ""
    if not entries:
        console.print(f"No filing decision has been recorded{where} yet.")
        return

    # Newest first whichever read produced them - a reader opens this
    # asking what happened most recently, and decisions_for() is ordered
    # the other way because that is the order a history reads in.
    shown = list(reversed(entries))[:limit] if dataset_id else entries
    console.print(f"[bold]{len(entries)}[/bold] decision(s){where}"
                   + (f", as at {as_at}" if as_at else "") + "\n")
    table = Table("Took effect", "Action", "Supply", "Slot", "Who", "Why",
                   box=None, pad_edge=False)
    for entry in shown:
        action = entry["action"]
        if action == decision_log.REFILE and not entry["from_slot"]:
            # A PLACEMENT, SAID AS ONE (REQ-PIPE-163 criterion 41) - never
            # a re-file, "None -> period" or a machine name.
            from qa_tools.common import placing

            slot, action = placing.said(entry["to_slot"]), "placement"
        elif action == decision_log.REFILE and not entry["to_slot"]:
            slot = f"held - out of {entry['from_slot']}"
        elif action == decision_log.REFILE:
            slot = f"{entry['from_slot']} -> {entry['to_slot']}"
        else:
            slot = entry["to_slot"] or entry["from_slot"] or ""
        # FREE TEXT IS TEXT, NEVER MARKUP (delivery-critic on 161, #9): a
        # reason containing "[/]" took the whole listing down.
        from rich.markup import escape

        who = escape(entry["actor"] or "")
        if entry["action"] == decision_log.STILL_FAILING:
            # FULL PROMINENCE, NEVER DIMMED (REQ-PIPE-121 criteria 12 and 13):
            # a re-evaluation left waiting supplies failing, and a person must
            # look - the one rule entry this list does not quieten.
            who = f"[bold red]{who} (rule)[/bold red]"
            action = f"[bold red]{action}[/bold red]"
        elif entry["actor_kind"] == decision_log.RULE:
            who = f"[dim]{who} (rule)[/dim]"
        # ON THE ASSET'S CLOCK (REQ-DASH-071). The column stores an
        # INSTANT, so psycopg hands it back in UTC whatever offset it was
        # written with - printing that raw would tell a Perth reader a
        # 9:30am promotion happened at 1:30am, which is the exact defect
        # the display standard exists to prevent.
        table.add_row(display_time.format_instant(entry["effective_at"]),
                       action, escape(entry["supply"] or ""),
                       slot, who, escape(entry["reason"]) if entry["reason"] else "[dim]-[/dim]")
    console.print(table)

    if dataset_id:
        if promoted:
            console.print(f"\nCurrently promoted: [bold]{promoted['supply']}[/bold] "
                           f"into {promoted['to_slot']}")
        else:
            console.print("\nNothing is promoted for this dataset.")


@supply_group.command("holds")
def holds_command() -> None:
    """Supplies nothing could place, waiting on a person.

    A hold is the correct output of the rule rather than a fault in
    it: where the rule genuinely cannot know which period a supply is
    for, it says so instead of putting it somewhere plausible. Putting
    it somewhere plausible is how a cascade starts.

    Counted together rather than one entry per supply - at thirty
    datasets a banner each is how people learn to ignore the whole
    class.
    """
    from qa_tools.common import qa_store, supply_db, supply_holds

    # A REAL READ SINCE REQ-PIPE-078. This used to print the summary of
    # an empty in-memory aggregation and a line saying so, because
    # holds lived for one run and there was nothing to read back. They
    # have a store now, and a hold stays in it until a decision ends it.
    with supply_db.connect(label="mothman:holds") as conn:
        qa_store.ensure_schema(conn)
        counted = supply_holds.tally(conn)
        console.print(counted.summary())
        if not counted.needs_action:
            return
        # THE TALLY ANSWERS THE HEADLINE AND THE ROWS ANSWER THE WORK.
        # Counting is a GROUP BY rather than a read of every held supply
        # (criterion 8); the detail below is fetched only once there is
        # something to show, which at thirty datasets is the difference
        # that matters.
        for held in supply_holds.outstanding(conn):
            if held.turned_off:
                continue   # quiet: the summary's count (post-build-review #190 D12)
            console.print(f"\n[yellow]{held.dataset_id}[/yellow] - {held.supply_id} "
                           f"[dim]({held.kind})[/dim]")
            console.print(f"  {held.describe()}", markup=False, highlight=False)
            command = held.place_command
            for response in held.responses:
                if command and response.startswith(supply_holds.RESPONSES[
                        supply_holds.ASSIGNMENT_RULE][0]):
                    # PLACE, ITS SCREEN AND ITS COMMAND (REQ-PIPE-163 criterion
                    # 12), the command on a line of its own so it copies cleanly.
                    # Every other response is kept (#188 D4).
                    from qa_tools.common import placing

                    console.print(f"  [dim]- place it into the period it belongs to, at "
                                  f"'{placing.where_to_decide(held.dataset_id)}', or:[/dim]")
                    console.print(command, soft_wrap=True, highlight=False, markup=False)
                    continue
                console.print(f"  [dim]- {response}[/dim]")


@supply_group.command("install-guard")
def install_guard_command() -> None:
    """Install, or bring up to date, the database guard on period tables
    (REQ-PIPE-129 criteria 11 and 18).

    A schema built from empty installs it; this is for a database whose
    guard was dropped, or one built before its definition last changed.
    Where the platform refuses the event triggers it says so, and the
    other two guards still run.
    """
    from qa_tools.common import period_tables, supply_db

    with supply_db.connect(label="mothman:install-guard") as conn:
        if period_tables.install_guard(conn) and period_tables.guard_installed(conn):
            console.print("[green]The period-table guard is installed.[/green]")
            return
    console.print("[yellow]This database refused the event triggers[/yellow] - they need "
                  "elevated rights. The decision log and the move code path still guard "
                  "period tables; anything else issuing DDL against one is unguarded.")
    raise SystemExit(1)


@supply_group.command("tidy")
@click.option("--yes", is_flag=True, help="Skip the confirmation - except where the "
              "environment confirms changes (production), which always asks for its id.")
def tidy_command(yes: bool) -> None:
    """Drop per-run schemas nothing is using any more.

    WHY THIS IS A COMMAND RATHER THAN AN AUTOMATIC STEP (Keith,
    2026-09-27). A run now discards its own view and dbt schemas as it
    finishes, so in the ordinary case there is nothing here to do -
    what is left belongs to a run that was interrupted. Sweeping that
    automatically is what this replaced, and the reason it had to stop
    is that a sweep cannot tell an interrupted run's leftovers from a
    run happening RIGHT NOW in another process. A person can.

    So this asks first, and names what it is about to drop.

    A CRASHED TRIAL IS THE OTHER THING THIS CLEARS (REQ-PIPE-103). A
    trial drops all of its schemas in one transaction when it ends,
    so nothing is ever half-cleared - but `kill -9` still leaves the
    lot, and a trial's staging schema is one of them. They are listed
    here for the same reason and on the same terms: identifiable from
    their names alone, and never dropped without being shown first.
    """
    from qa_tools.common import supply_db, trial

    conn = supply_db.connect(label="mothman:supply-tidy")
    try:
        leftovers = sorted(set(
            supply_db.run_schemas(conn) + supply_db.dbt_schemas(conn)
            + trial.orphan_schemas(conn)))
        if not leftovers:
            console.print("[green]Nothing to tidy[/green] - no per-run schemas are left over.")
            return
        console.print(f"[yellow]{len(leftovers)} per-run schema(s) left over:[/yellow]")
        for schema in leftovers:
            console.print(f"  {schema}")
        # The environment named in the prompt (REQ-TEST-114 criterion 4), and
        # its typed id where it confirms changes (post-build-review #119 D2).
        if not common.confirm_drop("Drop these? Anything still running will lose the "
                                   "schema it is reading through", yes=yes):
            console.print("[dim]Left alone.[/dim]")
            return
        for schema in leftovers:
            conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        console.print(f"[green]Dropped {len(leftovers)} schema(s).[/green]")
    finally:
        conn.close()


@supply_group.command("discard-sample")
@click.option("--dataset", "dataset_id", required=True,
              help="The dataset whose pre-graduation data to discard.")
@click.option("--yes", is_flag=True, help="Skip the confirmation - except where the "
              "environment confirms changes (production), which always asks for its id.")
def discard_sample_command(dataset_id: str, yes: bool) -> None:
    """Discard a dataset's pre-graduation data (REQ-PIPE-106 criteria 17, 18).

    A PERSON DOES THIS, AND ONLY A PERSON. Nothing in the pipeline
    discards sample data: not graduation, not a schedule, not as a side
    effect of anything else. That is Keith's own condition from the day he
    settled the fork (2026-09-27) and it is the half a bare "discard"
    would have lost - graduation and discarding are two acts, and a
    dataset growing up destroys nothing on its own.

    WHY IT IS DISCARDED AT ALL, since the recommendation at the time was
    to leave it where it is: sample data was received to develop checks
    against, not as a supply anybody agreed, so keeping it for ever means
    an agreed dataset carries rows nobody ever owed. Filing it to the
    first period was rejected outright - that asserts it met a schedule
    which did not exist when it arrived.

    THE QA RECORD IS NOT TOUCHED (criterion 19). Developing a check is
    real work and its record survives; this removes the DATA the checks
    ran against, which is a different thing in a different place.
    """
    from qa_tools.common import hierarchy, sample_data, schedule, supply_db

    try:
        hierarchy.dataset(dataset_id)
    except Exception as exc:  # noqa: BLE001 - the hierarchy's own message names the ids
        raise click.ClickException(str(exc)) from exc
    kind = schedule.no_calendar(dataset_id)
    if kind is None:
        # A GRADUATED DATASET'S DATA IS NOT THIS COMMAND'S TO TOUCH.
        # Refusing is not pedantry: once a calendar is agreed the supplies
        # are filed to periods and promoted, and "discard the sample data"
        # has no meaning for them. Whatever is still in the sample schema
        # from before graduation is reached by re-declaring nothing - it is
        # keyed by dataset, and the dataset is the same one - so the honest
        # answer is to say which state it is in rather than guess.
        raise click.ClickException(
            f"{dataset_id} has an agreed delivery calendar, so it has no "
            f"pre-graduation data to discard. If it graduated and left sample "
            f"data behind, discard it before the calendar is agreed.")

    conn = supply_db.connect(label="mothman:discard-sample")
    try:
        found = sample_data.staged_tables(conn, dataset_id)
        if not found:
            console.print(f"[green]Nothing to discard[/green] - {dataset_id} has no "
                           f"data in the {sample_data.SCHEMA} schema.")
            return
        waiting = ("no schedule agreed yet" if kind == schedule.NOT_YET_AGREED
                   else "one-off extraction, no schedule ever")
        console.print(f"[yellow]{len(found)} table(s)[/yellow] in "
                       f"{sample_data.SCHEMA} for [bold]{dataset_id}[/bold] ({waiting}):")
        for physical in found:
            console.print(f"  {physical}")
        if not common.confirm_drop("Discard these? The data goes, the QA record made "
                                   "against it stays", yes=yes):
            console.print("[dim]Left alone.[/dim]")
            return
        dropped = sample_data.discard(conn, dataset_id)
        console.print(f"[green]Discarded {len(dropped)} table(s).[/green] "
                       f"The QA record is untouched.")
    finally:
        conn.close()


@supply_group.command("grant-publisher")
@click.option("--role", default="mothman_publisher", show_default=True,
              help="The role the dashboard build connects as.")
@click.option("--password", default=None,
              help="Set or rotate the role's password. Omitted, an existing "
                   "role keeps the password it has.")
def grant_publisher_command(role: str, password: str | None) -> None:
    """Give the dashboard build a read-only role (REQ-PIPE-089 criteria 7, 23).

    READ ON THE QA METADATA SCHEMA, AND NOTHING ELSE. Not "everything
    except supply data" - a grant written as an exclusion has to be
    revisited every time a schema is added, and the one nobody
    revisits is the one that leaks. Every other schema is unreachable
    because nothing was ever granted on it.

    Run as somebody who can create a role. It is idempotent, so
    re-running after a schema change re-applies the grants.
    """
    from qa_tools.common import qa_store, supply_db

    with supply_db.connect(label="mothman:grant-publisher") as conn:
        qa_store.ensure_schema(conn)
        qa_store.ensure_publisher_role(conn, role, password)

    console.print(f"[green]{role}[/green] may SELECT in schema "
                  f"[cyan]{qa_store.SCHEMA}[/cyan], and holds nothing anywhere else.")
    console.print("The dashboard build connects as this role; the pipeline does not.",
                  style="dim")
    if password is None:
        console.print("No password set - pass --password to set or rotate one.",
                      style="dim")


# ---------------------------------------------------------------------------
# Filing decisions (REQ-GHUB-082). The wizard bodies live in
# cli/filing_tui.py; these are the flag-invocable forms of the same
# thing, which is this CLI's standing wizard/flags duality rather than a
# second implementation - every one of them calls the same
# qa_tools/common/filing_decisions.apply().
# ---------------------------------------------------------------------------

@supply_group.command("queue")
@click.option("--collection", "collection_id", callback=_collection, required=True,
               help="Which collection's queue to show.")
def queue_command(collection_id: str) -> None:
    """Supplies waiting on a person (REQ-GHUB-082 criterion 16).

    THE SAME DEFINITION THE TICKET POLICY USES, never a second one -
    `slot_state.NEEDS_ACTION`, filtered to the states that hold a
    supply. A terminal and a ticket disagreeing about what is
    outstanding is the failure this avoids by construction.
    """
    from cli import filing_tui
    from qa_tools.common import filing_queue

    try:
        with filing_tui.open_log() as conn:
            waiting = filing_queue.awaiting(conn, collection_id)
            owed_now = _owed_in(conn, collection_id)
    except filing_queue.LogUnreachable as exc:
        filing_tui.say_unreachable(exc)
        raise SystemExit(1) from exc
    if not waiting:
        console.print("Nothing is waiting on a person.", style="green")
    else:
        console.print(f"[bold]{len(waiting)}[/bold] supply/supplies waiting on a decision\n")
        console.print(filing_tui.queue_table(waiting))
    _say_owed(owed_now)


def _owed_in(conn, collection_id: str) -> list:
    """QA owed and not yet run for this collection - re-checks and
    re-evaluations (REQ-PIPE-140 criterion 7, REQ-PIPE-121 criterion 16)."""
    from qa_tools.common import hierarchy, recheck

    mine = {d.dataset_id for d in hierarchy.datasets_in_collection(collection_id)}
    return [o for o in recheck.owed(conn) if o.dataset_id in mine]


def _say_owed(owed_now: list) -> None:
    """WHILE OWED, SHOWN AS OWED (REQ-PIPE-121 criterion 16): a re-check a
    run left undone is otherwise invisible until the processing pass
    finishes it (REQ-PIPE-151)."""
    if not owed_now:
        return
    console.print(f"\n[bold yellow]{len(owed_now)}[/bold yellow] QA run(s) owed, not yet "
                  "done - the processing pass completes them:")
    for o in owed_now:
        what = (f"re-check of {o.supply_id}" if o.kind == "recheck"
                else f"re-evaluation of {o.period}'s readers of {', '.join(o.tables or [])}")
        why = f" - last attempt: {o.last_failure}" if o.last_failure else ""
        console.print(f"  {what} (owed to decision {o.caused_by_decision}){why}")


@supply_group.command("slots")
@click.option("--collection", "collection_id", callback=_collection, required=True,
               help="Which collection's periods to show.")
@click.option("--dataset", "dataset_id", default=None,
               help="Narrow to one dataset.")
def slots_command(collection_id: str, dataset_id: str | None) -> None:
    """Where every period stands (REQ-GHUB-082 criterion 18).

    WHAT THE DECISIONS RESOLVE TO, whichever route recorded each of
    them - which is the difference between this and `mothman supply
    decisions`: that one lists what happened, this says what is true
    now.
    """
    from cli import filing_tui

    filing_tui.standing_view(collection_id, dataset_id)


@supply_group.command("amber-setting")
@click.option("--collection", "collection_id", callback=_collection, default=None,
               help="Narrow to one collection.")
def amber_setting_command(collection_id: str | None) -> None:
    """The amber setting in force for each dataset, and where it was set
    (REQ-PIPE-122 NFR 1) - so a value nobody remembers setting can be found.

    Plain lines, one per dataset, so the list can be read or grepped.
    """
    from qa_tools.common import amber_setting, asset_time, hierarchy

    today = asset_time.local_date(asset_time.now())
    entries = (hierarchy.datasets_in_collection(collection_id) if collection_id
               else hierarchy.all_datasets())
    for entry in entries:
        try:
            said = amber_setting.describe(entry.dataset_id, today)
        except amber_setting.AmberSettingError as exc:
            said = f"none in force - {exc}"
        click.echo(f"{entry.dataset_id}  {said}")


@supply_group.command("superseded")
@click.option("--collection", "collection_id", callback=_collection, required=True,
               help="Which collection's superseded supplies to list.")
@click.option("--dataset", "dataset_id", default=None, help="Narrow to one dataset.")
@click.option("--period", default=None, help="Narrow to one period.")
def superseded_command(collection_id: str, dataset_id: str | None, period: str | None) -> None:
    """Superseded supplies, and what superseded each (REQ-PIPE-120 criterion 7).

    None of them is in the queue of supplies awaiting a decision - a newer
    version of the same table for the same period took its place - so this
    is where a person finds one to bring back with `--operation
    un-supersede`.
    """
    from qa_tools.common import hierarchy, supersession, supply_db

    # ONE PLAIN LINE PER SUPPLY, not a table: the ids are what a person
    # pastes into un-supersede, and a table column truncates or folds them.
    datasets = [d.dataset_id for d in hierarchy.datasets_in_collection(collection_id)
                if dataset_id in (None, d.dataset_id)]
    lines = []
    with supply_db.connect(read_only=True, label="mothman:supply-superseded") as conn:
        for ds in datasets:
            periods = [period] if period else [r[0] for r in conn.execute(
                "SELECT DISTINCT slot FROM qa.filing_current WHERE dataset_id = ? AND slot IS NOT NULL "
                "ORDER BY slot", [ds]).fetchall()]
            for p in periods:
                for v in supersession.superseded_in(conn, ds, p):
                    lines.append(f"{ds}  {p}  {v['supply']}  superseded by "
                                 f"{v['superseded_by'] or 'a person'}")
    if not lines:
        click.echo("Nothing is superseded here.")
        return
    click.echo(f"Superseded supplies - {collection_id} ({len(lines)}):")
    for line in lines:
        click.echo(f"  {line}")
    click.echo("To bring one back: mothman supply decide --operation un-supersede "
               "--dataset <id> --period <period> --supply <supply> --reason '<why>'")


@supply_group.command("decide")
@click.option("--operation", required=True,
               type=click.Choice(list(filing_decisions.OPERATIONS), case_sensitive=False),
               help="Which filing decision to record.")
@click.option("--dataset", "dataset_id", required=True, help="The dataset.")
@click.option("--period", default=None,
               help="The period the decision is about. Required, except for a range "
                    "excuse (--from-period and --through-period), a place (--to-period) and "
                    "rejecting a held supply, which has no period.")
@click.option("--from-period", "from_period", default=None,
               help="For excuse-lateness over a RANGE: the first period. Every late "
                    "supply filed from here to --through-period is excused, one entry "
                    "each, after a panel shows which and which are skipped.")
@click.option("--through-period", "through_period", default=None,
               help="For excuse-lateness over a range: the last period, inclusive.")
@click.option("--supply", default=None,
               help="The supply being acted on, where the operation acts on one. "
                    "Taken from the slot when omitted - except a place, which names it.")
@click.option("--stands-on", "stands_on", default=None,
               help="For a substitute: the earlier period this one stands on.")
@click.option("--to-period", "to_period", default=None,
               help="For a re-file or a place: the period the supply goes into.")
@click.option("--reason", default=None,
               help="Why. Required - a decision nobody can explain is the "
                    "thing the log exists to prevent.")
@click.option("--yes", is_flag=True,
               help="Skip the confirmation prompt. A decision whose warning lists "
                    "consequences also needs --acknowledge KEY.")
@click.option("--acknowledge", "acknowledged", default=None, metavar="KEY",
               help="Confirm a decision's consequences beyond its own slot, by the key "
                    "its warning showed - needed with --yes where there are any.")
@click.option("--wait", is_flag=True,
               help="For a place, a re-file or a re-check: run its checks now, in the foreground, and "
                    "end with where the supply stands. Without it the checks are left owed "
                    "for `mothman pipeline process`.")
@click.option("--file-outcome", "file_outcomes", multiple=True,
               metavar="'<filename>=<supply|refile:<period>|reject|supersede>'",
               help="For choose-file only, once per file of the pair, by the filename it "
                    "arrived under: supply = the supply for the period; refile:<period> = "
                    "re-file - this file belongs to another period; reject = reject - this "
                    "file is wrong; it can be promoted back later on its own; supersede = a "
                    "spare copy - kept, can be brought back.")
def decide_command(operation: str, dataset_id: str, period: str | None,
                    from_period: str | None, through_period: str | None,
                    supply: str | None, stands_on: str | None,
                    to_period: str | None, reason: str | None, yes: bool,
                    acknowledged: str | None, wait: bool = False,
                    file_outcomes: tuple[str, ...] = ()) -> None:
    """Record one filing decision (REQ-GHUB-082 criteria 2, 3, 28).

    It leaves a decision's checks owed unless --wait is given: `mothman
    pipeline process` runs every owed QA run. --wait runs them now, for a
    place or a re-file, and exits 3 where the decision stands but its checks
    did not finish.

    \b
    A held supply - one the filing rule could not file to any period - is
    placed into the period it belongs to:
      mothman supply decide --operation place --dataset cp-carers \\
        --supply 'cp-carers@<key>' --to-period 2026-Q3 --reason '<why>'

    THE FLAG FORM OF THE WIZARD, calling the same implementation the
    GitHub route calls. The actor is whoever `git config user.email`
    says, checked against contract/people.yaml - there is no way to
    state one, on either route.

    IT WRITES THE DECISION LOG AND CALLS NO GITHUB (criterion 30). The
    slot's ticket is brought up to date by REQ-PIPE-083's own pass, so
    this needs no `gh` auth and works where that domain is unreachable.
    """
    from cli import filing_tui
    from qa_tools.common import filing_queue

    operation = operation.lower()
    # --wait IS FOR A DECISION THAT OWES A QA RUN (REQ-PIPE-163 criteria 25 and
    # 27): a placement or a re-file.
    # UN-SUPERSEDE OWES ONE TOO (REQ-PIPE-120; #188 D1).
    if wait and operation not in (filing_decisions.PLACE, filing_decisions.REFILE,
                                  filing_decisions.UN_SUPERSEDE, filing_decisions.RECHECK):
        raise click.UsageError(
            f"--wait runs the QA a decision owes, and a {operation} owes none - it is for "
            f"--operation place, refile, un-supersede and re-check.")
    if operation == filing_decisions.PLACE:
        _place_from_flags(dataset_id, period, supply, to_period, stands_on, from_period,
                          through_period, reason=reason, yes=yes,
                          acknowledged=acknowledged, wait=wait)
        return

    # A SETTLEMENT TAKES ITS OWN FLAGS AND NO OTHERS (REQ-PIPE-193 criterion
    # 15) - each refusal names the flag.
    if operation.lower() == filing_decisions.CHOOSE_FILE:
        for flag, value in (("--supply", supply), ("--to-period", to_period),
                            ("--stands-on", stands_on), ("--from-period", from_period),
                            ("--through-period", through_period)):
            if value:
                raise click.UsageError(
                    f"{flag} cannot be used with --operation choose-file: the pair is "
                    f"named by --dataset and --period, and each file's outcome by "
                    f"--file-outcome.")
        if period is None:
            raise click.UsageError("--period is required.")
        outcome = _settle_from_flags(dataset_id, period, file_outcomes, reason=reason,
                                     yes=yes, acknowledged=acknowledged)
        if outcome is None:
            raise SystemExit(1)
        return
    if file_outcomes:
        raise click.UsageError("--file-outcome is for --operation choose-file only.")

    # ONE SHARED PAIR OF RANGE FLAGS (REQ-PIPE-161 criterion 15), never
    # --to-period, which is a re-file's target.
    ranged = from_period is not None or through_period is not None
    if ranged:
        if operation.lower() != filing_decisions.EXCUSE_LATENESS:
            raise click.UsageError("--from-period and --through-period are for "
                                   "--operation excuse-lateness only.")
        if from_period is None or through_period is None or period is not None:
            raise click.UsageError("a range excuse takes both --from-period and "
                                   "--through-period, and no --period.")
        ignored = [flag for flag, value in (("--supply", supply), ("--to-period", to_period),
                                            ("--stands-on", stands_on)) if value]
        if ignored:
            raise click.UsageError(f"a range excuse names no single supply or target, so "
                                   f"{', '.join(ignored)} cannot be used with it.")
        outcome = filing_tui.apply_decision(
            operation=operation.lower(), dataset_id=dataset_id, period=from_period,
            through_period=through_period, reason=reason, yes=yes,
            acknowledged=acknowledged)
        if outcome is None:
            raise SystemExit(1)
        return
    if period is None and not (operation == filing_decisions.REJECT and supply):
        # A HELD SUPPLY HAS NO PERIOD (REQ-PIPE-163 criterion 11): it is
        # rejected by --supply alone, and the log refuses one that is not held.
        raise click.UsageError("--period is required.")

    if supply is None:
        try:
            with filing_tui.open_log() as conn:
                found = [s for s in filing_queue.slots_of(
                    conn, hierarchy.dataset(dataset_id).collection_id,
                    dataset_id=dataset_id) if s.period == period
                    # The slot's own supply, never another version waiting in it.
                    and s.state != filing_queue.ANOTHER_VERSION_WAITING]
        except filing_queue.LogUnreachable as exc:
            filing_tui.say_unreachable(exc)
            raise SystemExit(1) from exc
        supply = found[0].supply if found else None

    outcome = filing_tui.apply_decision(
        operation=operation.lower(), dataset_id=dataset_id, period=period,
        supply=supply, stands_on=stands_on, to_period=to_period,
        reason=reason, yes=yes, acknowledged=acknowledged, flag_route=True, wait=wait)
    # A REFUSAL FAILS AND A NO-OP DOES NOT (criterion 26). Both end with
    # nothing appended and a panel already saying which, but a script
    # that treats "already promoted" as an error is a script that stops
    # on the ordinary case of two people working the same slot.
    if outcome is None:
        raise SystemExit(1)
    if outcome.checks_finished is False:
        raise SystemExit(filing_tui.CHECKS_STILL_OWED_EXIT)


def _place_from_flags(dataset_id: str, period: str | None, supply: str | None,
                      to_period: str | None, stands_on: str | None, from_period: str | None,
                      through_period: str | None, *, reason: str | None, yes: bool,
                      acknowledged: str | None, wait: bool) -> None:
    """A placement from the flag form (REQ-PIPE-163 criterion 15): --supply
    and --to-period, never --period, which a held supply does not have."""
    from cli import filing_tui
    from qa_tools.common import supply_files

    if not supply:
        raise click.UsageError("a placement names the held supply, with --supply.")
    if period:
        raise click.UsageError(
            "--period cannot be used with --operation place: a held supply has no period. "
            "Name the period it goes into with --to-period.")
    for flag, value in (("--stands-on", stands_on), ("--from-period", from_period),
                        ("--through-period", through_period)):
        if value:
            raise click.UsageError(f"{flag} cannot be used with --operation place.")
    if not to_period:
        raise click.UsageError("a placement names the period it goes into, with --to-period.")
    own = supply_files.dataset_of(supply)
    if own and own != dataset_id:
        raise click.UsageError(
            f"{supply} is a supply of {own}, not {dataset_id}. Give --dataset {own}.")
    if wait:
        # A PAIR HELD WHOLE OWES NO RUN until it is settled (REQ-PIPE-163
        # criterion 37), so --wait is refused under criterion 27, saying
        # where the settlement is made and naming both files.
        from qa_tools.common import placing

        with filing_tui.open_log() as conn:
            contest = supply_files.open_contest(conn, dataset_id, supply)
        if contest is not None:
            raise click.UsageError(
                f"--wait runs the QA a decision owes, and placing a pair owes none: neither "
                f"{' nor '.join(contest.files)} is checked until the pair is settled where it "
                f"is placed, at '{placing.where_to_decide(dataset_id)}'. Place it without "
                f"--wait, then settle it there.")
    outcome = filing_tui.apply_decision(
        operation=filing_decisions.PLACE, dataset_id=dataset_id, period=to_period,
        supply=supply, to_period=to_period, reason=reason, yes=yes,
        acknowledged=acknowledged, flag_route=True, wait=wait)
    if outcome is None:
        raise SystemExit(1)
    if outcome.checks_finished is False:
        raise SystemExit(filing_tui.CHECKS_STILL_OWED_EXIT)


def _settle_from_flags(dataset_id: str, period: str, tokens: tuple[str, ...], *,
                       reason: str | None, yes: bool, acknowledged: str | None):
    """choose-file from the flag form (REQ-PIPE-193 criterion 15): the same
    rules, refusals, warning and confirmation as the TUI. A file given no
    outcome is asked for through the TUI's own screens at a terminal, and
    refused - naming the form with the pair's real filenames - without one."""
    import sys

    from cli import filing_tui, settle_tui
    from qa_tools.common import dataset_blockers, settlement, supply_files

    with filing_tui.open_log() as conn:
        pair = None
        for blocker in dataset_blockers.contests(conn):
            found = supply_files.resolve(conn, dataset_id, blocker.supply)
            if (blocker.dataset_id == dataset_id and blocker.is_open
                    and found is not None and found.period == period):
                pair = blocker.supply
                break
        if pair is None:
            filing_tui._show(f"No pair of files is waiting to be settled for {dataset_id} "
                             f"{period}. Nothing was recorded.",
                             title=settle_tui.REFUSED_TITLE, style="red")
            return None
        _delivery, _p, files = settlement.pair_files(conn, dataset_id, pair)
    names = [f.filename for f in files]
    answers = [settle_tui.parse_outcome(t, names) for t in tokens]
    given = {a.filename for a in answers}
    if len(given) != len(answers):
        raise click.UsageError("each file takes exactly one --file-outcome.")
    missing = [n for n in names if n not in given]
    interactive = sys.stdin.isatty() and sys.stdout.isatty()
    if missing and not interactive:
        raise click.UsageError(
            f"no outcome was given for {' and '.join(missing)}. Give one per file:\n"
            + "\n".join(f"  --file-outcome '{n}=<supply|refile:<period>|reject|supersede>'"
                         for n in names))
    if not (reason or "").strip() and not interactive:
        # SAID AS WHAT IS MISSING, with the command as given (#170).
        raise click.UsageError(
            "--reason is missing - a settlement records why. The same command with it:\n"
            f"  mothman supply decide --operation choose-file --dataset {dataset_id} "
            f"--period {period} "
            + " ".join(f"--file-outcome '{t}'" for t in tokens)
            + " --reason '<why>' --yes")
    # A FILE GIVEN ALONE IS KEPT, and only the other asked (criterion 15, #170).
    return settle_tui.settle(dataset_id, period, pair, answers=answers or None,
                             reason=reason, yes=yes, acknowledged=acknowledged,
                             summary=bool(missing))


@supply_group.command("corrections")
@click.option("--reference", default=None,
              help="Show one pending correction's moves and verdict changes in full.")
def corrections_command(reference: str | None) -> None:
    """Calendar corrections awaiting the data asset's manager (REQ-PIPE-170).

    \b
    Examples:
      mothman supply corrections
      mothman supply corrections --reference CAB-123

    A correction declared in contract/calendar.yaml (or the timezone's in
    contract/data-asset.yaml) is pending until the asset manager confirms
    it. With --reference, its moves and verdict changes are worked out NOW,
    from what is filed today - by the same computation as the impact preview
    the change board saw - summary by dataset first. Anyone allowlisted may
    look; only the asset manager confirms (`mothman supply
    confirm-correction`). Reads the database; changes nothing.
    """
    from qa_tools.common import correction_apply, correction_trial

    with supply_db.connect(read_only=True, label="mothman:corrections") as conn:
        try:
            found = correction_apply.pending(conn)
        except correction_trial.Unreadable as exc:
            raise click.ClickException(str(exc)) from exc
        parked = correction_apply.parked(conn)
        # A CONFIRMED REFERENCE shows its parked moves (delivery-critic #152,
        # 5); an unknown one is refused whatever else is pending.
        if reference is not None and reference not in {p.reference for p in found}:
            mine = [m for m in parked if m.reference == reference]
            if mine:
                _show_parked(mine)
                return
            if reference in correction_apply.applied_references(conn):
                console.print(f"{reference} is confirmed and has no parked moves.",
                              style="green", markup=False)
                return
            raise click.ClickException(f"{reference} is not a correction awaiting "
                                       f"confirmation or one with parked moves - `mothman "
                                       f"supply corrections` lists both.")
        if reference is None:
            _show_parked(parked)
        if not found:
            if not parked:
                console.print("No corrections are waiting to be confirmed.", style="green")
            return
        if reference is None:
            console.print(f"{len(found)} correction(s) waiting for the data asset's "
                          f"manager to confirm, oldest first:", style="bold")
            docs = correction_trial.working()
            for p in found:
                affected = correction_apply.affected_datasets(p, docs[0])
                console.print(f"  {p.reference} ({p.date}) on {p.label}: {p.reason}",
                              markup=False, highlight=False)
                console.print(f"      affects {', '.join(affected) or 'no dataset'}",
                              style="dim", markup=False)
            console.print(f"\nSee one in full: mothman supply corrections --reference "
                          f"{found[0].reference}", style="dim", markup=False)
            return
        try:
            p, t = correction_apply.trial_for(conn, reference)
        except decision_log.DecisionRefused as exc:
            raise click.ClickException(str(exc)) from exc
        _show_correction(p, t)


def _show_parked(parked: list) -> None:
    """Each confirmed correction's move that waits on another decision
    (Keith, 2026-10-11, (p)), and the two ways it ends."""
    if not parked:
        return
    from qa_tools.common import correction_apply

    console.print(f"{len(parked)} move(s) from confirmed corrections are parked until what "
                  f"blocks them is cleared - the next processing pass then moves each to the "
                  f"period confirmed:", style="bold yellow")
    for m in parked:
        console.print(f"  {m.reference}: {m.dataset_id} {m.supply_id}  "
                      f"{m.from_period or 'held'} -> {m.to_period or 'held'}", markup=False,
                      highlight=False)
        console.print(f"      blocked: {m.blocked.splitlines()[0]}", style="dim", markup=False)
    # NEVER A KEEP THAT WOULD BE REFUSED (post-build-review #190 D5).
    keepable = [m for m in parked if not correction_apply.keep_refusal(m)]
    if not keepable:
        console.print("None of them can be kept where it is - each is in a period that no "
                      "longer owes a supply.\n", style="dim", markup=False)
        return
    first = keepable[0]
    console.print(f"Or keep one where it is (the asset manager): mothman supply "
                  f"confirm-correction --reference {first.reference} --keep {first.supply_id} "
                  f"--keep-reason '<why>'\n", style="dim", markup=False, soft_wrap=True)


def keep_parked_moves(conn, reference: str, keeps, keep_reason: str | None, *, actor: dict,
                      yes: bool) -> bool:
    """Keep parked supplies where they are, with one reason - the flag
    route's and the terminal's one body (Keith, 2026-10-11)."""
    from qa_tools.common import correction_apply

    by_supply = {m.supply_id: m for m in correction_apply.parked(conn, reference)}
    unknown = [k for k in keeps if k not in by_supply]
    if unknown:
        raise click.ClickException(f"{', '.join(unknown)} is not parked under {reference}, so "
                                   f"there is nothing to keep. `mothman supply corrections` "
                                   f"lists what is parked.")
    if not (keep_reason or "").strip() and not yes:
        keep_reason = common.text_prompt("Why do the kept supplies stay where they are?",
                                         flag_hint="--keep-reason")
    if not (keep_reason or "").strip():
        raise click.ClickException("keeping a supply needs a reason - why it stays where it "
                                   "is (--keep-reason).")
    if not common.confirm_change(
            f"Keep {len(keeps)} parked supply/supplies of {reference} where they are, as "
            f"{people.actor_name(actor)}?", yes=yes, default=False, flag_hint="pass --yes"):
        console.print("Not kept.", style="yellow")
        return False
    # ALL OR NOTHING (delivery-critic #152, 10), as a confirmation is.
    try:
        with decision_log.decision_transaction(conn):
            for supply in keeps:
                m = by_supply[supply]
                correction_apply.keep_parked(conn, reference, m.dataset_id, supply,
                                             actor=actor, reason=keep_reason,
                                             effective_at=asset_time.now().isoformat())
    except (decision_log.DecisionRefused, people.RoleRefused) as exc:
        raise click.ClickException(f"{exc} Nothing was kept.") from exc
    for supply in keeps:
        console.print(f"Kept {by_supply[supply].dataset_id} {supply} where it is.",
                      style="green", markup=False)
    return True


def _show_correction(p, t) -> str:
    """The moves summary first (criterion 14), then each supply, then the
    key a scripted confirmation acknowledges. Returns the key."""
    from qa_tools.common import correction_apply, correction_trial

    text = correction_trial.report(t, as_at=asset_time.now(),
                                   database=correction_trial.database_label(),
                                   against=f"the agreement before {p.reference}",
                                   title=f"Correction {p.reference}: what confirming it does")
    console.print(text, markup=False, highlight=False, soft_wrap=True)
    key = correction_apply.key(t)
    console.print(f"Confirm all of it, keeping any supply where it is:\n  mothman supply "
                  f"confirm-correction --reference {p.reference} --yes --acknowledge {key} "
                  f"[--keep <supply> ... --keep-reason '<why>']", style="dim", markup=False,
                  soft_wrap=True)
    return key


@supply_group.command("confirm-correction")
@click.option("--reference", required=True, help="The correction's change reference.")
@click.option("--keep", "keeps", multiple=True, metavar="SUPPLY",
              help="A supply to KEEP where it is rather than move. Repeat for each.")
@click.option("--keep-reason", "keep_reason", default=None,
              help="Why the kept supplies stay - one reason covers them all, recorded on "
                   "each.")
@click.option("--yes", is_flag=True, help="Skip the confirmation prompt; needs --acknowledge.")
@click.option("--acknowledge", "acknowledged", default=None, metavar="KEY",
              help="The key `mothman supply corrections --reference` showed, so a list "
                   "that changed since is refused.")
@click.option("--output", type=click.Path(dir_okay=False), default=None,
              help="Write what was applied as Markdown, to attach to the change reference.")
def confirm_correction_command(reference: str, keeps: tuple[str, ...],
                               keep_reason: str | None, yes: bool,
                               acknowledged: str | None, output: str | None) -> None:
    """Confirm a calendar correction's moves - the data asset's manager only.

    \b
    Examples:
      mothman supply confirm-correction --reference CAB-123
      mothman supply confirm-correction --reference CAB-123 --keep cp-clients@2024... \\
          --keep-reason 'genuinely Q3 data, sent early' --yes --acknowledge 1a2b3c4d

    Applies every move and verdict change the correction makes, in one step:
    each moved supply is re-filed (and re-checked by the next pass), one the
    corrected calendar offers no period is held, and every verdict is
    re-judged against the period it ends up in. A kept supply stays where it
    is, recorded as kept. A move another decision blocks is PARKED: it waits
    on the outstanding list and the processing pass moves it once the
    blocker clears - or, run again on the confirmed reference with --keep,
    it is kept where it is. Prints what was applied, to attach to the change
    reference.
    """
    from cli import filing_tui
    from qa_tools.common import correction_apply, correction_trial

    actor = filing_tui.actor_at_the_keyboard()
    # REFUSED BEFORE ANY REASON IS ASKED FOR (criterion 18), naming the role,
    # its level and who holds it.
    why = manager_refusal(actor)
    if why:
        raise click.ClickException(why)
    with supply_db.connect(label="mothman:confirm-correction") as conn:
        # AN APPLIED CORRECTION WITH PARKED MOVES (Keith, 2026-10-11, (p)):
        # --keep keeps a parked supply where it is instead.
        if reference in correction_apply.applied_references(conn):
            if not correction_apply.parked(conn, reference):
                raise click.ClickException(f"{reference} is already confirmed and has no "
                                           f"parked moves - there is nothing to confirm.")
            if acknowledged or output:
                console.print("--acknowledge and --output apply to confirming a correction, "
                              "not to keeping a parked move - ignored.", style="yellow",
                              markup=False)
            if not keeps:
                _show_parked(correction_apply.parked(conn, reference))
                raise click.ClickException(
                    f"{reference} is already confirmed; its parked moves go ahead on their "
                    f"own once what blocks them is cleared. --keep <supply> keeps one where "
                    f"it is instead.")
            keep_parked_moves(conn, reference, keeps, keep_reason, actor=actor, yes=yes)
            return
        try:
            p, t = correction_apply.trial_for(conn, reference)
        except (decision_log.DecisionRefused, correction_trial.Unreadable) as exc:
            raise click.ClickException(str(exc)) from exc
        key = _show_correction(p, t)
        keep = _resolve_keeps(t, keeps)
        if keep and not keep_reason and not yes:
            keep_reason = common.text_prompt("Why do the kept supplies stay where they are?",
                                             flag_hint="--keep-reason")
        if yes and acknowledged is None:
            raise click.ClickException(f"--yes confirms without asking, so it needs the key "
                                       f"of what it confirms: --acknowledge {key}.")
        apply_correction(conn, p, t, actor=actor, keep=keep, keep_reason=keep_reason,
                         acknowledged=acknowledged if yes else key, yes=yes, output=output)


def manager_refusal(actor) -> str | None:
    """Why this person may not confirm a correction, naming the role, its
    level and who holds it (criterion 18) - or None."""
    try:
        people.require_role(actor, people.MANAGER, people.DATA_ASSET)
    except people.RoleRefused as exc:
        holders = ", ".join(people.actor_name(m) for m in people.asset_managers()) or "nobody"
        return (f"{exc} Confirming a correction needs the manager role at "
                f"{people.LEVEL_WORDS[people.DATA_ASSET]}, held by: {holders}.")
    return None


def apply_correction(conn, p, t, *, actor: dict, keep: set, keep_reason: str | None,
                     acknowledged: str, yes: bool, output: str | None) -> bool:
    """Confirm, apply, then print what was applied and where it goes - the
    flag route's and the terminal's one body (criteria 10, 16, 22)."""
    from qa_tools.common import correction_apply, correction_trial

    if not common.confirm_change(
            f"Apply correction {p.reference} - "
            f"{sum(1 for m in t.moves if not m.blocked and (m.dataset_id, m.supply_id) not in keep)}"
            f" move(s), {len(keep)} kept"
            + (f", {parked} parked until what blocks them clears"
               if (parked := sum(1 for m in t.moves if m.blocked
                                 and (m.dataset_id, m.supply_id) not in keep)) else "")
            + f" - as {people.actor_name(actor)}?",
            yes=yes, default=False, flag_hint=f"pass --yes --acknowledge {acknowledged}"):
        console.print("Not applied.", style="yellow")
        return False
    try:
        done = correction_apply.confirm(
            conn, p.reference, actor=actor, keep=keep, keep_reason=keep_reason,
            acknowledge=acknowledged, effective_at=asset_time.now().isoformat())
    except (decision_log.DecisionRefused, people.RoleRefused) as exc:
        raise click.ClickException(str(exc)) from exc
    text = correction_apply.summary(p, t, done, as_at=asset_time.now(),
                                    database=correction_trial.database_label())
    console.print(text, markup=False, highlight=False, soft_wrap=True)
    if output is None and sys.stdin.isatty():
        output = common.path_prompt("Write this to a file to attach? A path, or blank to skip:",
                                    flag_hint="--output")
    if output:
        Path(output).write_text(text)
        console.print(f"Written to {output}.", style="green", markup=False)
    console.print(f"Attach it to {p.reference} and share it with the correction's approver"
                  f"{f' ({p.approver})' if p.approver else ''}, who compares it with what they "
                  f"approved. Moved supplies are re-checked and re-gated by the next "
                  f"processing pass.", style="bold", markup=False, soft_wrap=True)
    return True


def _resolve_keeps(t, keeps: tuple[str, ...]) -> set[tuple[str, str]]:
    """Each --keep, as (dataset, supply) among the proposed moves."""
    by_supply = {m.supply_id: m.dataset_id for m in t.moves}
    out = set()
    for raw in keeps:
        if raw not in by_supply:
            raise click.ClickException(f"{raw} is not among this correction's proposed moves, "
                                       f"so there is nothing to keep.")
        out.add((by_supply[raw], raw))
    return out
