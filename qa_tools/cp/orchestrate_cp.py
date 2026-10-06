"""
Runs all four REAL tools (dbt-core, Soda Core, datacontract-cli, Evidently)
against every generated Child Protection snapshot run - the CP counterpart
to qa_tools/bdm/orchestrate_bdm.py. Aggregates into
reports/results_cp.json, same check-result record shape
(agency_id/collection_id/dataset_id/...) as reports/results_bdm.json,
except dataset_id varies per result across the 6 CP tables instead of
being one constant.

Runs one arrival at a time, in receipt order, through
qa_tools/common/arrival_lifecycle.py (REQ-PIPE-086) - see
orchestrate_bdm.py's docstring for why it stopped running in parallel.
--sequential now only stops a run's tools overlapping.

Assumes data/cp_raw/ (generator/generate_cp_runs.py's output) already
exists - run that first if it doesn't. Builds data/cp_duckdb_runs/ itself
via build_cp_warehouses.build_all().

Run as `python3 -m qa_tools.cp.orchestrate_cp` (this is a package
now, not a flat script directory - see plans/qa-pipeline.md #84).
"""
from __future__ import annotations
import shutil

from collections.abc import Callable
import json
import os
import sys


from qa_tools.common import (arrivals, delivery, delivery_log, in_flight_log,
                              supply_db)
from qa_tools.common import decision_log
from qa_tools.common import drift_reference
from qa_tools.common import filing
from qa_tools.common import held_blast_radius
from qa_tools.common import hierarchy
from qa_tools.common import parallel_orchestrate
from qa_tools.common import left_out, own_table
from qa_tools.common import period_overlay
from qa_tools.common import promotion
from qa_tools.common import ticket_reconciler
from qa_tools.common import unrunnable
from qa_tools.common import trial
from qa_tools.common.git_identity import get_run_by
from qa_tools.common.qa_results_reader import read_dataset_stats
from qa_tools.common.qa_results_reader import canonical_order
from qa_tools.common.qa_results_writer import (
    finish_run, open_run, run_owner, scope_of_run, write_qa_result)
from . import build_cp_warehouses
from . import cp_common
from . import dataset_stats
from . import run_dbt_cp
from . import run_soda_cp
from . import run_datacontract_cp
from . import run_evidently_cp
from qa_tools.common import arrival_lifecycle
from qa_tools.common import replay_clock
from qa_tools.common import asset_time

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
RESULTS_PATH = os.path.join(ROOT, "reports", "results_cp.json")


# The real, discrete steps one run of the check chain goes through, in
# order - the single source of truth for both the labels a progress
# indicator shows and how many there are (plans/tooling.md #13). The
# chain takes ~13.5s and used to print NOTHING for that whole stretch,
# so an operator got a static screen with no sign the tool was alive,
# working, or hung. These are genuinely known steps, so an indicator
# built on them is a real measure of progress rather than a decorative
# fake - the one honest caveat being that they are very unevenly sized
# (dbt-core ~5s and datacontract-cli ~6s dominate; Soda Core and
# Evidently are ~0.1s each - see plans/performance.md), so the bar
# advances in genuine but lumpy jumps.
RUN_STEPS = ("dbt-core", "Soda Core", "datacontract-cli", "Evidently", "Dataset statistics")


class QaRunFailure(RuntimeError):
    """A tool failed partway through a run (REQ-PIPE-036 criterion 12).

    NAMES THE DATASET AND THE TOOL, because the bare exception a tool
    raises names neither - and at ~30 datasets across two collections,
    "datacontract-cli exited 1" sends somebody to the logs to work out
    WHOSE run it was. The original cause is chained rather than
    replaced, so nothing about the diagnosis is lost.
    """


def _run_step(collection: str, tool: str, run_id: str, call):
    """Run one tool's evaluation, or fail loudly saying whose it was.

    The partial run's files STAY ON DISK. Deleting them would destroy
    the evidence of what did run, and they cannot be mistaken for a
    complete run anyway: completeness is derived from every expected
    file being present (qa_results_reader.EXPECTED_TOOLS), so a run
    that stopped after two tools is visibly missing four.
    """
    try:
        return call()
    except Exception as exc:  # noqa: BLE001 - re-raised, named, and chained
        raise QaRunFailure(
            f"{collection} run {run_id}: {tool} failed - {type(exc).__name__}: {exc}. "
            f"This run is INCOMPLETE and is not recorded as a finished one; "
            f"its partial results stay on disk.") from exc


def _announce(on_step, label: str) -> None:
    """Report the step ABOUT to start. Optional by design: every existing
    caller (the full-manifest batch loop, the AWS Lambda handlers, the
    tests) passes nothing and behaves exactly as before - only the
    interactive CLI, where a human is actually watching, opts in."""
    if on_step is not None:
        on_step(label)

def _run_one(entry: dict, run_timestamp: str, run_by: str,
             reference_run_id: str | None = None,
             on_step: Callable[[str], None] | None = None) -> list[dict]:
    run_id = entry["run_id"]
    print(f"--- {run_id} ---")
    try:
        return _run_one_inner(entry, run_id, run_timestamp, run_by, reference_run_id, on_step)
    finally:
        # Per run, in a finally - see orchestrate_bdm.py's identical
        # block and supply_db.drop_run_schemas() for why this stopped
        # being a sweep at the end of the fan-out.
        _discard_this_runs_schemas(run_id)


def _discard_this_runs_schemas(run_id: str) -> None:
    """Give back what this run borrowed, and everything a TRIAL
    borrowed. Never fails the run - see the BDM counterpart's own
    docstring for both."""
    try:
        # AND THE ON-DISK HALF, which was leaking. dbt's target/ is
        # per-run by the same mechanism the schemas are - so that two
        # parallel workers cannot clobber each other's manifest.json -
        # and nothing removed it: 1.9 GB across 80 scratch directories
        # by the time it was found, one of them holding 101 runs. Safe
        # here and only here: dbt's artefacts are parsed DURING
        # evaluation, and this runs once the results are recorded.
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


def _run_one_inner(entry: dict, run_id: str, run_timestamp: str, run_by: str,
                    reference_run_id: str | None,
                    on_step: Callable[[str], None] | None) -> list[dict]:
    # Before any tool writes - see orchestrate_bdm.py's identical block.
    open_run(cp_common.AGENCY_ID, cp_common.COLLECTION_ID, run_id, run_timestamp, run_by,
             purpose=entry.get("purpose"))

    # PER SUPPLY, NOT PER BATCH (REQ-QAC-108 criteria 2 and 4) - see
    # orchestrate_bdm.py's identical block for the full account, and
    # why None here means "no reference" rather than "use a default".
    if reference_run_id is None:
        # THIS RUN'S OWN DATASET, not cp-notifications' (REQ-PIPE-105).
        # A run is one file now, and the volume check it records is about
        # its own table - so its reference is the run that checked its
        # own dataset's last promoted supply, which is also the only run
        # sure to have recorded that table's numbers. Asking about
        # cp-notifications instead found nothing for any run filed before
        # the notifications file of its delivery.
        owner = run_owner(run_id)
        # AND WHAT THE COMPARISON CROSSES (REQ-QAC-108 criteria 8 to 17) -
        # see orchestrate_bdm.py's identical block.
        assessment = drift_reference.assess_arrival(
            owner[0] if owner else run_evidently_cp.DATASET_ID, entry["received_at"])
        reference_run_id = assessment.run_id if assessment else None
    else:
        assessment = None

    # NO TOOL RUNS FOR A RUN WHOSE OWN TABLE IS UNREADABLE (REQ-PIPE-115
    # criteria 5, 6 and 9) - see orchestrate_bdm.py's identical guard.
    # Every check in such a run's scope is the dataset's own or reads its
    # table, so nothing in it is evaluable. This used to run all four
    # tools over a HELD supply's staging-time view and record ordinary
    # verdicts against a supply with no period. A run id that names no
    # table (a fixture's) has no own table to guard.
    owner = run_owner(run_id)
    why = None
    if owner is not None:
        received = entry.get("received_at")
        with supply_db.connect(read_only=True, label="mothman:cp-readable") as conn:
            why = own_table.why_unreadable(
                conn, run_id, owner[1], supply_db.resolution_for(conn, run_id),
                own_dataset=owner[0],
                arrival_key=supply_db.arrival_segment(received) if received else None)
    readable = why is None
    if not readable:
        print(own_table.describe(run_id, owner[1], why))
    run_step = _run_step if readable else (lambda collection, tool, rid, call: [])

    def _dbt() -> list[dict]:
        return run_step(cp_common.COLLECTION_ID, "dbt-core", run_id,
            lambda: run_dbt_cp.evaluate_dbt_cp(run_id, run_timestamp))

    def _the_rest() -> list[dict]:
        got: list[dict] = []
        _announce(on_step, RUN_STEPS[1])
        got.extend(run_step(cp_common.COLLECTION_ID, "Soda Core", run_id,
            lambda: run_soda_cp.evaluate_soda_cp(run_id, run_timestamp)))
        _announce(on_step, RUN_STEPS[2])
        got.extend(run_step(cp_common.COLLECTION_ID, "datacontract-cli", run_id,
            lambda: run_datacontract_cp.evaluate_datacontract_cp(run_id, run_timestamp)))
        _announce(on_step, RUN_STEPS[3])
        got.extend(run_step(cp_common.COLLECTION_ID, "Evidently", run_id,
            lambda: run_evidently_cp.evaluate_evidently_cp(
                run_id, run_timestamp, reference_run_id=reference_run_id,
                assessment=assessment)))
        return got

    # dbt BESIDE THE OTHER THREE (REQ-TEST-116 criterion 3) - see
    # parallel_orchestrate.beside(). Results keep tool order either way.
    _announce(on_step, RUN_STEPS[0])
    from_dbt, from_the_rest = parallel_orchestrate.beside(_dbt, _the_rest)
    results: list[dict] = [*from_dbt, *from_the_rest]

    # Same rationale as orchestrate_bdm.py's identical block - see
    # qa_tools/bdm/dataset_stats.py's own docstring.
    _announce(on_step, RUN_STEPS[4])
    conn = supply_db.connect(read_only=True)
    conn.execute(f"SET search_path = '{supply_db.run_schema(run_id)}'")
    stats = dataset_stats.compute_dataset_stats(conn, entry)
    resolution = supply_db.resolution_for(conn, run_id)
    tables_read = resolution.as_record()
    conn.close()

    # WHAT A HELD TABLE COST THE CHECKS THAT READ IT (REQ-PIPE-078
    # criterion 10). Criterion 9 withheld its view, so those checks did
    # not run - and a check that silently does not appear is
    # indistinguishable from one that passed, to the dashboard, to the
    # promotion gate and to the tickets alike. These say red and name
    # the held table, which is the difference between somebody looking
    # for a broken check and somebody looking for the supply nobody has
    # placed.
    #
    # ITS OWN PSEUDO-TOOL, and deliberately NOT in EXPECTED_TOOLS: a
    # run with nothing held writes nothing here, and a completeness
    # rule that demanded it would make every clean run incomplete.
    # NOTHING PER CHECK where the run may not read its own table
    # (REQ-PIPE-115 criteria 6 and 16) - see orchestrate_bdm.py.
    blast = held_blast_radius.results_for(
        held=resolution.held, reads=promotion._declared_reads(),
        run_id=run_id, run_timestamp=run_timestamp) if readable else []
    if blast:
        print(held_blast_radius.describe(blast))
        write_qa_result(cp_common.AGENCY_ID, cp_common.COLLECTION_ID, run_id,
                         run_timestamp, held_blast_radius.TOOL,
                         {"held": resolution.held}, verified=blast)
        results.extend(blast)
    # AND WHAT A MISSING TABLE COST THEM (REQ-PIPE-105 criterion 13,
    # REQ-PIPE-079 criteria 4 and 14-16). Every tool now leaves a check
    # over an unreadable table OUT, so without this it would simply not
    # appear - indistinguishable from a pass. Each in-scope check gets a
    # record saying it could not be evaluated, red or no-data by why the
    # table is missing, and never as a verdict on the data. Only for a
    # run with a period: an unfiled supply's run is scoped to nothing.
    missing = (_unrunnable_results(entry, run_id, run_timestamp, resolution)
               if readable else [])
    if missing:
        print(unrunnable.describe(missing))
        write_qa_result(cp_common.AGENCY_ID, cp_common.COLLECTION_ID, run_id,
                         run_timestamp, unrunnable.TOOL,
                         {"unreadable": sorted(set(resolution.absent) | set(resolution.ambiguous))},
                         verified=missing)
        results.extend(missing)

    # WHAT THE TOOLS LEFT OUT MUST BE WHAT THE RUN RECORDED AS NOT
    # EVALUATED (REQ-PIPE-115 criterion 17) - see left_out.py. A check
    # left out and recorded by nobody reads as a pass, so a disagreement
    # refuses the run here, before it is finished, and stops the batch.
    # Only where unrunnable applies at all: a run with no period, or
    # whose id names no table, is scoped to nothing.
    #
    # AUDITABLE AFTER THE RUN (accepted at sign-off): each tool's
    # in-scope left-out set is recorded with the run, as its own raw
    # output, so a later reader can see what was compared rather than
    # only that it agreed. Nothing is written where nothing was left out.
    noted = left_out.take(run_id)
    if _reconciles(entry, run_id):
        compared = left_out.reconcile(run_id, noted, [*blast, *missing],
                                      scope_of_run(run_id))
        if compared:
            write_qa_result(cp_common.AGENCY_ID, cp_common.COLLECTION_ID, run_id,
                             run_timestamp, left_out.TOOL, {"left_out": compared})
    # run_by stamped only on this write - see orchestrate_bdm.py's
    # identical comment.
    write_qa_result(cp_common.AGENCY_ID, cp_common.COLLECTION_ID, run_id, run_timestamp, "dataset_stats", stats,
                     run_by=run_by)

    # WHICH PHYSICAL TABLE THIS RUN READ (REQ-PIPE-068 criterion 5).
    # The view schema is thrown away when the run ends, and the
    # question is asked years later - of an audit, or of a check that
    # started failing - so the answer goes into committed history
    # beside the run's results rather than being reconstructed from a
    # staging schema that has since moved on.
    write_qa_result(cp_common.AGENCY_ID, cp_common.COLLECTION_ID, run_id, run_timestamp,
                     "tables_read", tables_read)

    # EVERYTHING THIS RUN PRODUCES IS NOW WRITTEN, so the run says so -
    # and only here (REQ-PIPE-089 criterion 13). A run that raised on
    # any step above never reaches this line, which is what keeps a
    # partial run invisible rather than indistinguishable from a
    # finished one.
    finish_run(run_id)
    return results


def _reconciles(entry: dict, run_id: str) -> bool:
    """Whether this run's left-out checks are reconciled (REQ-PIPE-115
    criterion 17): a run with a scope, and - as amended 2026-10-05
    (Keith) - a TRIAL, so what a trial shows is trustworthy on the same
    terms as a real run. A trial's id names no table, so its scope is the
    whole collection."""
    return trial.is_trial(run_id) or _has_scope(entry, run_id)


def _has_scope(entry: dict, run_id: str) -> bool:
    """Whether this run is one unrunnable reports for - it names a table
    and its supply was filed to a period."""
    owner = run_owner(run_id)
    if owner is None:
        return False
    as_at = asset_time.parse_instant(entry["received_at"], f"received_at for {run_id}")
    return bool(filing.period_of(owner[0], as_at))


def _unrunnable_results(entry: dict, run_id: str, run_timestamp: str,
                        resolution) -> list[dict]:
    """The could-not-run records for this run - see unrunnable.py."""
    if trial.is_trial(run_id):
        # A TRIAL IS RECONCILED, so it records what it could not read
        # (delivery critic on 8a942e7, H2) - without these the
        # reconciliation crashed on an ordinary trial with an unloadable
        # sibling file.
        noted = left_out.peek(run_id)
        return unrunnable.results_for_trial(
            run_id=run_id, run_timestamp=run_timestamp, resolution=resolution,
            reads=promotion._declared_reads(),
            left_out_ids=set().union(*noted.values()) if noted else set())
    owner = run_owner(run_id)
    if owner is None:
        return []
    own_dataset, own_table = owner
    as_at = asset_time.parse_instant(entry["received_at"], f"received_at for {run_id}")
    period = filing.period_of(own_dataset, as_at)
    if not period:
        return []
    with supply_db.connect(read_only=True, label="mothman:unrunnable") as conn:
        return unrunnable.results_for(
            conn, run_id=run_id, run_timestamp=run_timestamp, own_table=own_table,
            own_dataset=own_dataset, period=period, resolution=resolution,
            reads=promotion._declared_reads(), as_at=as_at)


def run_single(entry: dict, reference_run_id: str | None = None, run_by: str | None = None,
               on_step: Callable[[str], None] | None = None) -> list[dict]:
    """The single-delivery counterpart to run_pipeline_cp()'s full-manifest
    batch loop - built for the AWS event-driven MVP (plans/running-
    thoughts.md #5 Thread B / docs/aws-event-driven-mvp-design.md).

    ONE CALL PER ARRIVING FILE, exactly like orchestrate_bdm.run_single()
    (REQ-PIPE-105 criterion 1). That is a reversal: this used to be called
    once per DELIVERY, after a CP ingest Lambda had staged all six tables
    and a completion tracker had confirmed they were all there, and this
    docstring used to warn that calling it sooner produced an incomplete
    cross-table result.

    WHAT MAKES THAT WARNING OBSOLETE rather than merely relaxed: a run
    reads the newest supply STAGED for its period for every table this
    arrival did not itself carry, falling back to the period's promoted
    state. So a call after the sixth file sees all six, and a call after
    the first sees the first plus whatever the period already holds -
    which is a true statement about the data as it stands, not a wrong
    one. The completion signal existed to make waiting safe; not waiting
    is safe, and it also removes the failure the signal could not avoid,
    where a supply waits silently on a marker nobody sends.

    `entry` is a manifest-entry-shaped dict for this one delivery
    (run_id/received_at/dirty_severity at minimum - see data/cp_raw/
    manifest.json's own real shape for the full convention; row_counts
    isn't required, dataset_stats.compute_dataset_stats() derives its own
    counts from the live warehouse instead of trusting a passed-in one)."""
    trial.require_trial(entry["run_id"], "orchestrate_cp.run_single")
    run_timestamp = asset_time.now().isoformat()
    run_by = run_by or get_run_by()
    return _run_one(entry, run_timestamp, run_by, reference_run_id, on_step=on_step)


def file_and_overlay(arrival, among=None) -> None:
    """Everything between staging an arrival and checking it.

    WHERE EACH SUPPLY BELONGS, RECORDED BEFORE ANY CHECK RUNS OVER IT
    (REQ-PIPE-075 criterion 7). filing.filled_slots() reads the decision
    log, so this sees what the arrivals before it filled. VERIFIED BEFORE
    FLIPPING IT, on a scratch database, because a filing is WRITE-ONCE and
    the artefact that kept this off was real: with every slot unfilled,
    102 of 108 supplies landed on 2023-Q1.

    AND THEN THE RUN CAN READ ITS PERIOD (REQ-PIPE-105 criterion 5). One
    file is one arrival, so the views staging gave this run hold ONE
    table and every cross-table check would ask it for six. Once filing
    has said which period this supply claims, the run's schema is rebuilt
    over that period: its own table from this arrival, every sibling from
    the one version staged for the period, else the period's promoted
    state. An unfiled supply keeps what staging gave it.

    A FUNCTION RATHER THAN A CLOSURE IN THE BATCH, because `mothman cp qa
    --commit` processes a hand-filed delivery's arrivals the same way
    (Keith, 2026-10-02) - two copies of these steps is how a hand-filed
    supply would come to differ from one that arrived on its own.

    A ZIP IS FILED WHOLE (REQ-PIPE-105 criterion 5, Keith, 2026-10-03).
    `among` is every arrival this pass knows of; the ones sharing THIS
    arrival's receipt instant are filed with it, before any is checked.
    The overlay reads only FILED siblings, so filing each file just before
    its own run left the first file of a zip blind to the rest - all 90
    "could not be evaluated" reds in the regenerate that found it were
    about a table the supply's own arrival carried. Simultaneous files
    are not waiting on each other (criterion 1), and filing a LATER one
    early would be. Filing is per dataset and write-once, so filing a
    sibling here and again at its own turn is the same filing.
    """
    filing.file_arrivals(simultaneous_with(arrival, among))
    period_overlay.rebuild_for_arrival(arrival, tables=build_cp_warehouses.TABLES)


def simultaneous_with(arrival, among) -> list:
    """This arrival and every other in `among` sharing its receipt
    instant, in receipt order."""
    same = [a for a in (among or ()) if a.received_at == arrival.received_at]
    if not any(a is arrival for a in same):
        same.append(arrival)
    return sorted(same, key=lambda a: (a.sequence, a.run_index, a.run_id))


def promote_after(arrival, got: list[dict], run_by: str) -> None:
    """PROMOTION FOLLOWS THE RUN (REQ-PIPE-075 criteria 1 and 13), and is
    deliberately not inside it: a promotion that fails must be retryable
    without re-running QA, which it is only while the two are separable.
    tests/test_promotion_after_run.py asserts that against
    _run_one_inner's own AST rather than trusting this comment.

    WHEN THE DECISION TOOK EFFECT, not when this replay ran
    (REQ-PIPE-081). A bootstrap walks four years of arrivals under one
    wall clock, and stamping every promotion with it left as-at-T with one
    day of history to answer over. See promotion.effective_at_for for why
    this is the same expression in production, where it still returns
    now.
    """
    promotion.report(promotion.after_runs(
        [arrival], got,
        agency_id=cp_common.AGENCY_ID, collection_id=cp_common.COLLECTION_ID,
        actor=promotion.RULE_ACTOR, actor_kind=decision_log.RULE,
        effective_at=promotion.effective_at_for(
            arrival.received_at, seed=arrival.run_id,
            before=promotion.next_receipt(arrival)).isoformat()))
    # THE KNOCK-ON OF WHAT IT PROMOTED (REQ-PIPE-121): every period the
    # promotions moved a table into owes its readers a re-evaluation, owed in
    # the promotion's own transaction and completed here.
    from qa_tools.common import knock_on

    knock_on.follow_up(cp_common.COLLECTION_ID, run_by=run_by)


def run_arrivals(found_arrivals, run_by: str, on_step=None) -> list[dict]:
    """Check these arrivals one at a time, exactly as the batch does: file
    and overlay, check, promote, then the next - in receipt order, because
    each filing depends on what the one before it promoted.

    THE HAND-FILED PATH (REQ-PIPE-103 criterion 1, under REQ-PIPE-105
    criterion 1). A folder handed to `mothman cp qa --commit` is one
    delivery and SIX arrivals, so it is six runs, and each records only
    what its own file is responsible for.
    """
    # THROUGH THE ONE PER-ARRIVAL LIFECYCLE (REQ-PIPE-086 criterion 2) -
    # the same function the batch calls, so the two cannot drift.
    return arrival_lifecycle.process_all(
        sorted(found_arrivals, key=lambda a: (a.sequence, a.run_index, a.run_id)),
        steps=STEPS, run_by=run_by, on_step=on_step,
        exclusive=True)


#: Child Protection's half of the one per-arrival lifecycle
#: (REQ-PIPE-086 criterion 2) - see qa_tools/common/arrival_lifecycle.py.
#: `among` is every arrival the caller knows of: a zip is filed whole.
STEPS = arrival_lifecycle.Steps(
    file_and_overlay=lambda arrival, among: file_and_overlay(arrival, among=among),
    entry_for=lambda arrival: arrival.as_entry(),
    run_one=lambda *args, **kw: _run_one(*args, **kw),
    promote_after=lambda arrival, got, run_by: promote_after(arrival, got, run_by))


# ON THE REPLAY'S OWN CLOCK (REQ-PIPE-081 criteria 27-31): the batch is always
# a replay, so on a synthetic asset every record it writes is stamped with the
# replay's simulated time rather than today's; on a real one, the wall clock.
@replay_clock.on_replay_clock
def run_pipeline_cp(sequential: bool = False,
                    record_deliveries: bool = True,
                    *, start_at: int = 1, after_each=None,
                    player=None) -> dict:
    # A RUN'S TOOLS OVERLAP unless told not to (REQ-TEST-116 criteria 3, 5).
    parallel_orchestrate.TOOLS_CONCURRENTLY = not sequential

    # RECOGNISED FROM DISK, never read from a declaration
    # (REQ-GEN-043) - see orchestrate_bdm.py's identical comment.
    found_arrivals = arrivals.arrivals_for("child-protection", "cp_run_")
    # A RESUME'S CLOCK STARTS AT ITS FIRST ARRIVAL (REQ-TEST-159 criterion
    # 4): anchored at arrival N's receipt before this writes anything.
    if start_at > 1 and replay_clock.active():
        replay_clock.anchor(found_arrivals[start_at - 1].received_at)

    # EACH DELIVERY IS RECORDED AT ITS FIRST ARRIVAL, and each arrival
    # STAGED as it comes (REQ-TEST-159, reversing REQ-TEST-116's
    # record-everything-up-front): see arrival_lifecycle.staged_as_it_arrives.
    # Write-once, so a delivery both collections claim is recorded by
    # whichever reaches it first, in one transaction.

    # WHAT THIS RUN SAW IN FLIGHT (REQ-PIPE-057 criteria 5 and 7).
    # Reported on EVERY run, with no interval and no threshold -
    # persistence becomes visible through repetition, so if it is still
    # there tomorrow you have seen it five times. Committed because the
    # alternative, terminal output only, loses the one genuinely bad
    # case: a delivery whose boundary never closes because something
    # upstream is broken would be visible to whoever ran the pipeline
    # and to nobody else. In-flight being the NORMAL state is exactly
    # what would let a stuck one hide.
    still_arriving = delivery.survey().in_flight
    for entry in still_arriving:
        print(f"note: delivery {entry.name!r} is present with no receipt record yet "
               f"({len(entry.files)} file(s): {', '.join(entry.files) or 'none'}) - "
               f"not processed.")
    in_flight_log.record(cp_common.COLLECTION_ID, asset_time.now().isoformat(), still_arriving)
    manifest = [a.as_entry() for a in found_arrivals]

    # The first manifest entry (cp_run_01, always clean by RUN_PLAN
    # construction) - NOT run_evidently_cp.REFERENCE_RUN_ID, a hardcoded
    # literal that goes stale every time the anchor date rolls forward
    # (generator/anchor_date.py) - see orchestrate_bdm.py's identical fix
    # and plans/qa-pipeline.md for the bug this was found as.
    # BEFORE ANY REAL TOOL RUNS (REQ-PIPE-057 criterion 19). Run ids
    # are positional, so a change in what recognition returns renames
    # committed history - a failure that would otherwise be found when
    # CI went red on paths nothing in this file mentions.
    # WHERE EACH SUPPLY BELONGS IS NOW RECORDED (REQ-PIPE-075 criterion
    # 7, 2026-09-28) - see the file_arrivals() call below. This comment
    # used to say it was deliberately off, because ONLY A PROMOTION
    # FILLS A SLOT and promotion did not exist, so every supply not on
    # time for its own slot filed against the oldest one in the
    # calendar. Filings land in the database, in `qa.filing`
    # (REQ-PIPE-104) - which is why that destination was built before
    # this switch was flipped rather than with it.

    # THE BATCH NO LONGER CHOOSES A REFERENCE RUN - see
    # orchestrate_bdm.py's identical note (REQ-QAC-108 criterion 4).
    run_timestamp = asset_time.now().isoformat()

    # Fails loudly here, before any real tool runs - see orchestrate_bdm.py's
    # identical comment and git_identity.py's own docstring.
    run_by = get_run_by()

    # IN RECEIPT ORDER, ONE ARRIVAL AT A TIME - file it, check it,
    # promote it, then the next. The chain is real rather than
    # cautious: a supply fills its open slot or is a resupply of it
    # according to whether a PROMOTION has filled it (REQ-PIPE-131), so
    # arrival N's filing depends on arrival N-1's promotion,
    # which depends on arrival N-1's checks.
    #
    # THIS COST THE CROSS-ARRIVAL PARALLELISM, and the measurement is in
    # parallel_orchestrate.run_manifest's own docstring along with what
    # it buys. Short version: filing every arrival up front put all 108
    # supplies in 2023-Q1, because nothing was ever filled while the
    # filings were being made.
    # THROUGH THE ONE PER-ARRIVAL LIFECYCLE (REQ-PIPE-086 criterion 2),
    # the same function a hand-filed delivery goes through.
    # SCRIPTED PERSON DECISIONS, PLAYED BACK BETWEEN ARRIVALS (REQ-GEN-135):
    # the batch replay is the one place they are raised, and the player
    # refuses unless the asset declares itself synthetic.
    from qa_tools.common import scripted_decisions

    all_results = arrival_lifecycle.process_all(
        found_arrivals, steps=STEPS, run_by=run_by, run_timestamp=run_timestamp,
        player=player if player is not None else scripted_decisions.Player(cp_common.COLLECTION_ID),
        prepare=arrival_lifecycle.staged_as_it_arrives(build_cp_warehouses.stage_arrival),
        start_at=start_at, after_each=after_each)

    # A DELIVERY NO ARRIVAL CLAIMED is recorded once the arrivals are done
    # (REQ-TEST-159): everything that was claimed was recorded as it arrived.
    if record_deliveries:
        delivery_log.record_all()

    # THE TICKETS CATCH UP WITH THE SLOTS (REQ-PIPE-083 criteria 13 and
    # 16). After promotion rather than beside it, because a ticket that
    # says something the decision log does not is worse than a ticket
    # that is a minute behind - and it reconciles EVERY slot this
    # collection is responsible for rather than the ones this run
    # touched, because a slot nobody delivered for is exactly the one
    # that needs a ticket and a pass scoped to arrivals can never see
    # it.
    #
    # SILENT WHERE NOTHING IS CONFIGURED. A run on somebody's laptop has
    # no GITHUB_REPOSITORY and no `gh`, which is not a broken run - it
    # is a run with no ticketing, the ordinary state of this repository
    # for most of its life.
    ticket_reconciler.report(
        ticket_reconciler.after_runs(cp_common.COLLECTION_ID))

    # NOTHING TO SWEEP HERE ANY MORE (Keith, 2026-09-27). Each run
    # discards its own view and dbt schemas as it finishes - see
    # _discard_this_runs_schemas() above and
    # supply_db.drop_run_schemas(). The blanket sweep that used to sit
    # here could not tell a schema left by an interrupted run from one
    # belonging to a run happening right now in another process, so it
    # is now an explicit `mothman supply tidy`, run by someone who
    # knows nothing else is going.

    # Same rationale as orchestrate_bdm.py's identical block.
    dataset_stats_by_run = {}
    for entry in manifest:
        stats = read_dataset_stats(cp_common.AGENCY_ID, cp_common.COLLECTION_ID, entry["run_id"])
        if stats is not None:
            dataset_stats_by_run[entry["run_id"]] = stats

    # ONE AGREED ORDERING down both paths (REQ-PIPE-038). A live run
    # emits a collection's tables interleaved; a rebuild reads them as
    # per-dataset files one after another. Same records either way, so
    # this is what keeps a diff between the two a real correctness
    # check rather than noise.
    all_results = canonical_order(all_results)
    n_pass = sum(1 for r in all_results if r["status"] == "pass")
    n_warn = sum(1 for r in all_results if r["status"] == "warn")
    n_fail = sum(1 for r in all_results if r["status"] == "fail")
    n_error = sum(1 for r in all_results if r["status"] == "error")
    # THE FIFTH VERDICT (REQ-QAC-108 criterion 5, 2026-09-29). A drift
    # or volume check with no reference period has measured nothing, and
    # counting it under any of the four above would say it did. Left out
    # of the summary entirely, the four stopped adding up to
    # total_checks - which is what the history rebuild's own test
    # noticed before anybody else did.
    n_nodata = sum(1 for r in all_results if r["status"] == "nodata")

    output = {
        "generated_at": run_timestamp,
        "dataset_stats": dataset_stats_by_run,
        "collection": f"{cp_common.AGENCY_ID}.{cp_common.COLLECTION_ID}",
        "datasets": sorted(d.dataset_id for d in hierarchy.datasets_in_collection(cp_common.COLLECTION_ID)),
        "runs": manifest,
        "results": all_results,
        "summary": {
            "total_checks": len(all_results),
            "pass": n_pass,
            "warn": n_warn,
            "fail": n_fail,
            "error": n_error,
            "nodata": n_nodata,
            "engines": sorted(set(r["engine"] for r in all_results)),
        },
    }

    os.makedirs(os.path.dirname(RESULTS_PATH), exist_ok=True)
    with open(RESULTS_PATH, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\n{len(all_results)} real check results ({n_pass} pass / {n_warn} warn / {n_fail} fail"
          f"{f' / {n_error} error' if n_error else ''}"
          f"{f' / {n_nodata} no reference' if n_nodata else ''}) across {len(manifest)} runs -> {RESULTS_PATH}")
    return output


if __name__ == "__main__":
    run_pipeline_cp(sequential="--sequential" in sys.argv)
