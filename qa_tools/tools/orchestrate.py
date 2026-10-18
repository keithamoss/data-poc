"""Runs all four REAL tools (dbt-core, Soda Core, datacontract-cli, Evidently)
over any collection's arrivals, one at a time in receipt order (REQ-PIPE-243).

ONE ARRIVAL AT A TIME, through qa_tools/common/arrival_lifecycle.py
(REQ-PIPE-086): file it, check it, promote it, then the next - because whether
an arrival FILLS its open slot or is a resupply of it (REQ-PIPE-131) depends on
what the arrival before it promoted. Filing every arrival up front once put all
108 Child Protection supplies in 2023-Q1. --sequential only stops a run's
tools overlapping.

Each arrival is staged as it arrives (qa_tools/tools/stage.py, REQ-PIPE-068)
into the supply database; nothing is staged up front.

BUILT FROM CHILD PROTECTION'S COPY, the N-table one: the reference, the
own-table guard, the could-not-run records and the reconciliation of what the
tools left out are all asked of the run's own table, and are the degenerate
case for a one-table collection. Birth Registrations' copy differed in four
places that change what is recorded, kept behind its `orchestrate.*` legacy
flags (qa_tools/tools/legacy.py). Run through `mothman pipeline run`/`bootstrap` or
a collection's `qa` command, never bare.
"""
from __future__ import annotations

import shutil
from collections.abc import Callable

from qa_tools import collections
from qa_tools.common import (
    arrival_lifecycle, arrivals, asked_for, asset_time, decision_log, delivery, delivery_log,
    drift_reference, filing, held_blast_radius, in_flight_log, left_out, own_table,
    parallel_orchestrate, period_overlay, promotion, replay_clock, supply_db,
    ticket_reconciler, trial, unrunnable,
)
from qa_tools.common.git_identity import get_run_by
from qa_tools.common.qa_results_reader import read_dataset_stats
from qa_tools.common.qa_results_writer import (
    finish_run, open_run, run_owner, scope_of_run, write_qa_result,
)
from qa_tools.tools import (
    dataset_stats, results_history, run_datacontract, run_dbt, run_evidently, run_soda, stage,
)

# The real, discrete steps one run goes through, in order - the single source
# of truth for both the labels a progress indicator shows and how many there
# are (plans/tooling.md #13). Very unevenly sized (dbt-core and
# datacontract-cli dominate), so a bar advances in genuine but lumpy jumps.
from qa_tools.tools.steps import RUN_STEPS  # noqa: E402,F401 - re-exported; defined there so the CLI can read it cheaply


class QaRunFailure(RuntimeError):
    """A tool failed partway through a run (REQ-PIPE-036 criterion 12). NAMES
    THE COLLECTION, RUN AND TOOL, because the bare exception a tool raises
    names none of them; the original cause is chained, not replaced."""


def _run_step(collection: str, tool: str, run_id: str, call):
    """One tool's evaluation, or a loud failure saying whose it was. The
    partial run's records stay: a run that stopped partway is never finished
    (finish_run below), so it cannot be mistaken for a complete one."""
    try:
        return call()
    except Exception as exc:  # noqa: BLE001 - re-raised, named, and chained
        raise QaRunFailure(
            f"{collection} run {run_id}: {tool} failed - {type(exc).__name__}: {exc}. "
            f"This run is INCOMPLETE and is not recorded as a finished one; "
            f"its partial results stay recorded, under an unfinished run.") from exc


def _announce(on_step, label: str) -> None:
    """Report the step ABOUT to start - only the interactive CLI opts in."""
    if on_step is not None:
        on_step(label)


def run_one(collection_id: str, entry: dict, run_timestamp: str, run_by: str,
            reference_run_id: str | None = None,
            on_step: Callable[[str], None] | None = None) -> list[dict]:
    """One QA run over one already-staged arrival of `collection_id`: every
    tool, the dataset statistics, the reconciliation and the records, with
    the run's own schemas discarded whatever happens. Returns the verified
    check results."""
    run_id = entry["run_id"]
    print(f"--- {run_id} ---")
    try:
        return _run_one_inner(collection_id, entry, run_id, run_timestamp, run_by,
                              reference_run_id, on_step)
    finally:
        # IN A finally, so a run that raised does not leave its schemas
        # behind for a later sweep to guess about.
        discard_run_schemas(run_id)


def discard_run_schemas(run_id: str) -> None:
    """Give back what this run borrowed, as soon as it is done with it - and
    everything a TRIAL borrowed, since it staged into a schema of its own
    (REQ-PIPE-103 criterion 6).

    PER RUN RATHER THAN A SWEEP AT THE END (Keith, 2026-09-27): a blanket
    sweep cannot tell an interrupted run's schema from one in use by another
    process. NEVER FAILS THE RUN - the results are recorded by now, and
    `mothman supply tidy` clears whatever is left. AND THE ON-DISK HALF:
    dbt's per-run target/ leaked 1.9 GB before it was found; safe to remove
    here and only here, once its artefacts have been parsed."""
    try:
        shutil.rmtree(supply_db.dbt_target_path(run_id), ignore_errors=True)
        conn = supply_db.connect(label="mothman:discard-run-schemas")
        try:
            if trial.is_trial(run_id):
                trial.discard(conn, run_id)
            else:
                supply_db.drop_run_schemas(conn, run_id)
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 - housekeeping never fails a finished run
        print(f"{run_id}: could not discard this run's schemas ({type(exc).__name__}: {exc}) "
              f"- results are recorded; `mothman supply tidy` clears leftovers")


def _run_one_inner(collection_id: str, entry: dict, run_id: str, run_timestamp: str,
                   run_by: str, reference_run_id: str | None,
                   on_step: Callable[[str], None] | None) -> list[dict]:
    coll = collections.by_id(collection_id)
    # BEFORE ANY TOOL WRITES, so the run exists with the identity only this
    # layer knows (REQ-PIPE-089 criterion 6).
    open_run(coll.agency_id, coll.id, run_id, run_timestamp, run_by, purpose=entry.get("purpose"))

    # THE REFERENCE IS RESOLVED PER SUPPLY (REQ-QAC-108 criteria 2 and 4), for
    # THIS RUN'S OWN DATASET (REQ-PIPE-105) - the run that checked its own
    # dataset's last promoted supply - and with what the comparison crosses
    # (criteria 8 to 17). None is a real answer: a first supply has nothing
    # earlier, reported as NO REFERENCE, never as a pass. After filing, which
    # is why this works.
    assessment = None
    if reference_run_id is None:
        owner = run_owner(run_id)
        assessment = drift_reference.assess_arrival(
            owner[0] if owner else run_evidently.drift_dataset(coll.id), entry["received_at"],
            period=(entry.get("purpose") or {}).get("period"))
        reference_run_id = assessment.run_id if assessment else None

    # NO TOOL RUNS FOR A RUN WHOSE OWN TABLE IS UNREADABLE (REQ-PIPE-115
    # criteria 5, 6 and 9): held, contested or refused, and any other reason
    # raises. A run id that names no table has no own table to guard.
    own = run_owner(run_id)
    why = None
    if own is not None:
        received = entry.get("received_at")
        with supply_db.connect(read_only=True, label="mothman:own-table-readable") as conn:
            why = own_table.why_unreadable(
                conn, run_id, own[1], supply_db.resolution_for(conn, run_id),
                own_dataset=own[0],
                arrival_key=supply_db.arrival_segment(received) if received else None)
    readable = why is None
    if not readable:
        print(own_table.describe(run_id, own[1], why))
    run_step = _run_step if readable else (lambda collection, tool, rid, call: [])

    def _dbt() -> list[dict]:
        return run_step(coll.id, "dbt-core", run_id,
                        lambda: run_dbt.evaluate(coll.id, run_id, run_timestamp))

    def _the_rest() -> list[dict]:
        got: list[dict] = []
        _announce(on_step, RUN_STEPS[1])
        got.extend(run_step(coll.id, "Soda Core", run_id,
                            lambda: run_soda.evaluate(coll.id, run_id, run_timestamp)))
        _announce(on_step, RUN_STEPS[2])
        got.extend(run_step(coll.id, "datacontract-cli", run_id,
                            lambda: run_datacontract.evaluate(coll.id, run_id, run_timestamp)))
        _announce(on_step, RUN_STEPS[3])
        got.extend(run_step(coll.id, "Evidently", run_id,
                            lambda: run_evidently.evaluate(
                                coll.id, run_id, run_timestamp,
                                reference_run_id=reference_run_id, assessment=assessment)))
        return got

    # dbt BESIDE THE OTHER THREE (REQ-TEST-116 criterion 3); results keep tool
    # order either way.
    _announce(on_step, RUN_STEPS[0])
    from_dbt, from_the_rest = parallel_orchestrate.beside(_dbt, _the_rest)
    results: list[dict] = [*from_dbt, *from_the_rest]

    # COMPUTED HERE, the one point with a legitimate connection to the rows,
    # and through the run's own view schema (REQ-PIPE-068 criterion 2). THE
    # ROWS ARE THE ARRIVAL'S (REQ-PIPE-140): a re-run reads the same supply.
    _announce(on_step, RUN_STEPS[4])
    conn = supply_db.connect(read_only=True)
    conn.execute(f"SET search_path = '{supply_db.run_schema(run_id)}'")
    stats = dataset_stats.compute_dataset_stats(coll.id, conn, entry)
    resolution = supply_db.resolution_for(conn, run_id)
    tables_read = resolution.as_record()
    conn.close()

    # WHAT A HELD TABLE COST THE CHECKS THAT READ IT (REQ-PIPE-078 criterion
    # 10): a check that silently does not appear is indistinguishable from one
    # that passed, so these say red and name the held table. Its own
    # pseudo-tool, not in EXPECTED_TOOLS. Nothing per check where the run may
    # not read its own table (REQ-PIPE-115 criteria 6 and 16).
    blast = held_blast_radius.results_for(
        held=resolution.held, reads=promotion._declared_reads(),
        run_id=run_id, run_timestamp=run_timestamp) if readable else []
    if blast:
        print(held_blast_radius.describe(blast))
        write_qa_result(coll.agency_id, coll.id, run_id, run_timestamp,
                        held_blast_radius.TOOL, {"held": resolution.held}, verified=blast)
        results.extend(blast)
    # AND WHAT A MISSING TABLE COST THEM (REQ-PIPE-105 criterion 13, REQ-PIPE-079
    # criteria 4 and 14-16): each in-scope check over an unreadable table gets a
    # could-not-be-evaluated record, never a verdict on the data.
    missing = _unrunnable_results(entry, run_id, run_timestamp, resolution) if readable else []
    if missing:
        print(unrunnable.describe(missing))
        write_qa_result(coll.agency_id, coll.id, run_id, run_timestamp, unrunnable.TOOL,
                        {"unreadable": sorted(set(resolution.absent) | set(resolution.ambiguous))},
                        verified=missing)
        results.extend(missing)

    # WHAT THE TOOLS LEFT OUT MUST BE WHAT THE RUN RECORDED AS NOT EVALUATED
    # (REQ-PIPE-115 criterion 17): a disagreement refuses the run before it is
    # finished. Each tool's in-scope left-out set is recorded where non-empty.
    noted = left_out.take(run_id)
    in_scope = scope_of_run(run_id)
    reconciles = _reconciles(entry, run_id)
    if reconciles:
        compared = left_out.reconcile(run_id, noted, [*blast, *missing], in_scope)
        if compared:
            write_qa_result(coll.agency_id, coll.id, run_id, run_timestamp, left_out.TOOL,
                            {"left_out": compared})
    # AND NOTHING IN SCOPE WENT MISSING ALTOGETHER (REQ-PIPE-188 criterion 6):
    # every in-scope check has a verdict or a not-evaluated record. A run with
    # no period records none, so there a check reading what it cannot read,
    # or one a tool said it left out, is excused (Keith, 2026-10-12).
    if readable:
        guarded = in_scope if reconciles else _excusing_unreadable(in_scope, resolution, noted)
        asked_for.check_nothing_missing(run_id, coll.id, results, guarded)
    # run_by stamped only here: one value per run is all the changelog needs.
    write_qa_result(coll.agency_id, coll.id, run_id, run_timestamp, "dataset_stats", stats,
                    run_by=run_by)
    # WHICH PHYSICAL TABLE THIS RUN READ (REQ-PIPE-068 criterion 5), recorded
    # because the view schema is thrown away and the question is asked later.
    write_qa_result(coll.agency_id, coll.id, run_id, run_timestamp, "tables_read", tables_read)
    # EVERYTHING THIS RUN PRODUCES IS NOW WRITTEN (REQ-PIPE-089 criterion 13):
    # a run that raised above never reaches this line.
    finish_run(run_id)
    return results


def _excusing_unreadable(in_scope, resolution, noted: dict[str, set[str]]):
    """`in_scope`, less the checks a run with no period has no record for:
    those reading a table it cannot read, and those a tool said it left out."""
    from qa_tools.common import tables_read

    gone = set(resolution.absent) | set(resolution.ambiguous) | set(resolution.held)
    reads = tables_read.declared_reads()
    left = set().union(*noted.values()) if noted else set()

    def guarded(check: str) -> bool:
        return (in_scope(check) and check not in left
                and not gone & set(reads.get(check, ())))
    return guarded


def _reconciles(entry: dict, run_id: str) -> bool:
    """A run with a scope, and a TRIAL (Keith, 2026-10-05), whose id names no
    table, so its scope is the whole collection. A supply filed to no period
    is excused (Keith, 2026-10-12) - for every collection since REQ-QAC-247."""
    return trial.is_trial(run_id) or _has_scope(entry, run_id)


def _has_scope(entry: dict, run_id: str) -> bool:
    """It names a table and its supply was filed to a period."""
    owner = run_owner(run_id)
    if owner is None:
        return False
    as_at = asset_time.parse_instant(entry["received_at"], f"received_at for {run_id}")
    return bool(_period_of_entry(entry, owner[0], as_at))


def _period_of_entry(entry: dict, dataset_id: str, as_at) -> str | None:
    """The period its purpose states (a re-check), else its arrival's filing -
    never derived from a settled pair's own receipt (REQ-PIPE-193 criterion 13)."""
    stated = (entry.get("purpose") or {}).get("period")
    return stated or filing.period_of(dataset_id, as_at)


def _unrunnable_results(entry: dict, run_id: str, run_timestamp: str, resolution) -> list[dict]:
    """The could-not-run records for this run - see unrunnable.py. A TRIAL is
    reconciled, so it records what it could not read too."""
    if trial.is_trial(run_id):
        noted = left_out.peek(run_id)
        return unrunnable.results_for_trial(
            run_id=run_id, run_timestamp=run_timestamp, resolution=resolution,
            reads=promotion._declared_reads(),
            left_out_ids=set().union(*noted.values()) if noted else set())
    owner = run_owner(run_id)
    if owner is None:
        return []
    own_dataset, table = owner
    as_at = asset_time.parse_instant(entry["received_at"], f"received_at for {run_id}")
    period = _period_of_entry(entry, own_dataset, as_at)
    if not period:
        return []
    with supply_db.connect(read_only=True, label="mothman:unrunnable") as conn:
        return unrunnable.results_for(
            conn, run_id=run_id, run_timestamp=run_timestamp, own_table=table,
            own_dataset=own_dataset, period=period, resolution=resolution,
            reads=promotion._declared_reads(), as_at=as_at)


def run_single(collection_id: str, entry: dict, reference_run_id: str | None = None,
               run_by: str | None = None,
               on_step: Callable[[str], None] | None = None) -> list[dict]:
    """ONE CALL PER ARRIVING FILE, already staged (REQ-PIPE-105 criterion 1):
    a run reads the newest supply staged for its period for every table its
    arrival did not carry, so a call after the first file is a true statement
    about the data as it stands. Trials only (REQ-PIPE-086 criterion 10)."""
    trial.require_trial(entry["run_id"], "orchestrate.run_single")
    return run_one(collection_id, entry, asset_time.now().isoformat(), run_by or get_run_by(),
                   reference_run_id, on_step=on_step)


def run_single_file(collection_id: str, run_id: str, table: str, csv_path: str, run_date: str,
                    reference_run_id: str | None, run_by: str | None = None,
                    on_step: Callable[[str], None] | None = None, received_at=None) -> list[dict]:
    """Stage one file from WHERE IT IS (REQ-PIPE-102) and run it as a trial.

    `received_at` IS THE REAL RECEIPT WHERE THERE IS ONE (REQ-PIPE-103); where
    there is none - a trial, a Lambda arrival outside the delivery tree - the
    start of the run date stands in for the entry, and the staged table is
    named after the RUN, so two runs sharing a run date never claim one
    physical table in shared staging."""
    from datetime import date

    trial.require_trial(run_id, "orchestrate.run_single_file")
    # IDENTITY AND CLOCK BEFORE ANYTHING IS STAGED: a missing git identity
    # fails here, with nothing to clean up, rather than after the trial table
    # exists and before run_one's own tidy-up can reach it.
    run_by = run_by or get_run_by()
    run_timestamp = asset_time.now().isoformat()
    entry = {"run_id": run_id, "run_index": 1, "csv_path": csv_path,
             "received_at": asset_time.isoformat(
                 received_at or asset_time.start_of_day(date.fromisoformat(run_date))),
             "delivery": run_id}
    stage.stage_table(collection_id, run_id, table, csv_path, received_at=received_at)
    return run_one(collection_id, entry, run_timestamp, run_by, reference_run_id,
                   on_step=on_step)


def simultaneous_with(arrival, among) -> list:
    """This arrival and every other in `among` sharing its receipt instant, in
    receipt order."""
    same = [a for a in (among or ()) if a.received_at == arrival.received_at]
    if not any(a is arrival for a in same):
        same.append(arrival)
    return sorted(same, key=lambda a: (a.sequence, a.run_index, a.run_id))


def file_and_overlay(collection_id: str, arrival, among=None) -> None:
    """Everything between staging an arrival and checking it: WHERE EACH
    SUPPLY BELONGS, recorded before any check runs over it (REQ-PIPE-075
    criterion 7), then the run's schema rebuilt over that period (REQ-PIPE-105
    criterion 5).

    A ZIP IS FILED WHOLE (Keith, 2026-10-03): the arrivals sharing this one's
    receipt instant are filed with it, because the overlay reads only FILED
    siblings - filing each file just before its own run left a zip's first
    file blind to the rest. Filing is per dataset and write-once, so filing a
    sibling here and again at its own turn is the same filing."""
    coll = collections.by_id(collection_id)
    filing.file_arrivals(simultaneous_with(arrival, among))
    period_overlay.rebuild_for_arrival(arrival, tables=[d.table for d in coll.datasets])


def _claim_window(collection_id: str, arrival):
    """How soon a scheduled pass gets to this delivery - the shortest claim
    window of the datasets it carries (Keith, 2026-10-11), else the adapter's
    `claim_window_dataset`'s, else none: never a borrowed one (REQ-PIPE-243
    criterion 2)."""
    from qa_tools.common import schedule

    if getattr(arrival, "received_at", None) is None:
        return None
    adapter = collections.adapter(collections.by_id(collection_id))
    on = asset_time.local_date(arrival.received_at)
    datasets = list(getattr(arrival, "files_by_dataset", None) or ())
    if not datasets and adapter.claim_window_dataset:
        datasets = [adapter.claim_window_dataset]
    return min((schedule.claim_window(d, on=on) for d in datasets), default=None)


def promote_after(collection_id: str, arrival, got: list[dict], run_by: str) -> None:
    """PROMOTION FOLLOWS THE RUN (REQ-PIPE-075 criteria 1 and 13), and is
    deliberately not inside it: a failed promotion must be retryable without
    re-running QA. WHEN THE DECISION TOOK EFFECT, not when this replay ran
    (REQ-PIPE-081). Then THE KNOCK-ON of what it promoted (REQ-PIPE-121)."""
    from qa_tools.common import knock_on

    coll = collections.by_id(collection_id)
    promotion.report(promotion.after_runs(
        [arrival], got, agency_id=coll.agency_id, collection_id=coll.id,
        actor=promotion.RULE_ACTOR, actor_kind=decision_log.RULE,
        effective_at=promotion.effective_at_for(
            arrival.received_at, seed=arrival.run_id,
            before=promotion.next_receipt(arrival),
            within=_claim_window(coll.id, arrival)).isoformat()))
    knock_on.follow_up(coll.id, run_by=run_by)


def entry_for(collection_id: str, arrival) -> dict:
    """The run entry for one arrival - the same for every collection since
    REQ-PIPE-248 (Birth Registrations' also named the arrival's file, which
    nothing read). It never asks the arrival for one path, so a contested
    file is checked rather than refused (REQ-PIPE-105 criterion 6)."""
    return arrival.as_entry()


def steps(collection_id: str) -> arrival_lifecycle.Steps:
    """A collection's half of the one per-arrival lifecycle (REQ-PIPE-086
    criterion 2). `among` is every arrival the caller knows of: a zip is
    filed whole. A collection with no adapter is refused here, by name,
    before any step runs (REQ-PIPE-240 criterion 6) - on EVERY call, which
    is why this is not cached: a cached Steps outlived a registry change and
    skipped the refusal (post-build-review #220), and building four lambdas
    costs nothing."""
    collections.adapter(collections.by_id(collection_id))
    return arrival_lifecycle.Steps(
        file_and_overlay=lambda arrival, among: file_and_overlay(collection_id, arrival, among),
        entry_for=lambda arrival: entry_for(collection_id, arrival),
        run_one=lambda *args, **kw: run_one(collection_id, *args, **kw),
        promote_after=lambda arrival, got, run_by: promote_after(collection_id, arrival, got,
                                                                 run_by))


def run_arrivals(collection_id: str, found_arrivals, run_by: str, on_step=None) -> list[dict]:
    """THE HAND-FILED PATH (REQ-PIPE-103 criterion 1): these arrivals one at a
    time, exactly as the batch does them, in receipt order."""
    return arrival_lifecycle.process_all(
        sorted(found_arrivals, key=lambda a: (a.sequence, a.run_index, a.run_id)),
        steps=steps(collection_id), run_by=run_by, on_step=on_step, exclusive=True)


# ON THE REPLAY'S OWN CLOCK (REQ-PIPE-081 criteria 27-31): on a synthetic asset
# every record the batch writes is stamped with the replay's simulated time.
@replay_clock.on_replay_clock
def run_pipeline(collection_id: str, sequential: bool = False,
                 record_deliveries: bool = True, *, start_at: int = 1, after_each=None,
                 player=None) -> dict:
    """Every recognised arrival of one collection, then its results file."""
    from qa_tools.common import scripted_decisions

    coll = collections.by_id(collection_id)
    # A RUN'S TOOLS OVERLAP unless told not to (REQ-TEST-116 criteria 3, 5).
    parallel_orchestrate.TOOLS_CONCURRENTLY = not sequential
    # RECOGNISED FROM DISK, never read from a declaration (REQ-GEN-043).
    found_arrivals = arrivals.arrivals_for(coll.id, coll.run_prefix)
    # A RESUME'S CLOCK STARTS AT ITS FIRST ARRIVAL (REQ-TEST-159 criterion 4).
    if start_at > 1 and replay_clock.active():
        replay_clock.anchor(found_arrivals[start_at - 1].received_at)

    # WHAT THIS RUN SAW IN FLIGHT (REQ-PIPE-057 criteria 5 and 7), on every run
    # with no threshold: a delivery whose boundary never closes must be visible
    # to more than whoever happened to run the pipeline.
    still_arriving = delivery.survey().in_flight
    for entry in still_arriving:
        print(f"note: delivery {entry.name!r} is present with no receipt record yet "
              f"({len(entry.files)} file(s): {', '.join(entry.files) or 'none'}) - "
              f"not processed.")
    in_flight_log.record(coll.id, asset_time.now().isoformat(), still_arriving)
    manifest = [entry_for(coll.id, a) for a in found_arrivals]

    run_timestamp = asset_time.now().isoformat()
    # Fails loudly here, before any real tool runs, if git identity is unset.
    run_by = get_run_by()

    # IN RECEIPT ORDER, ONE ARRIVAL AT A TIME, through the one per-arrival
    # lifecycle; SCRIPTED PERSON DECISIONS played back between arrivals
    # (REQ-GEN-135), refused unless the asset declares itself synthetic; EACH
    # ARRIVAL STAGED AS IT COMES (REQ-TEST-159).
    all_results = arrival_lifecycle.process_all(
        found_arrivals, steps=steps(coll.id), run_by=run_by, run_timestamp=run_timestamp,
        player=player if player is not None else scripted_decisions.Player(coll.id),
        prepare=arrival_lifecycle.staged_as_it_arrives(stage.stager(coll.id)),
        start_at=start_at, after_each=after_each)

    # A DELIVERY NO ARRIVAL CLAIMED is recorded once the arrivals are done.
    if record_deliveries:
        delivery_log.record_all()
    # THE TICKETS CATCH UP WITH THE SLOTS (REQ-PIPE-083 criteria 13 and 16),
    # every slot this collection is responsible for; silent where nothing is
    # configured.
    ticket_reconciler.report(ticket_reconciler.after_runs(coll.id))

    # Read back rather than threaded through - the same path the rebuild from
    # history uses, so the two cannot drift on how statistics are assembled.
    stats_by_run = {}
    for arrival in found_arrivals:
        stats = read_dataset_stats(coll.agency_id, coll.id, arrival.run_id)
        if stats is not None:
            stats_by_run[arrival.run_id] = stats
    return results_history.write_results_file(
        coll.id, runs=manifest, dataset_stats=stats_by_run, results=all_results,
        generated_at=run_timestamp)
