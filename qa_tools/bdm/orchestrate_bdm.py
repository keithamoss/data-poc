"""
Runs all four REAL tools (dbt-core, Soda Core, datacontract-cli, Evidently)
against every generated Birth Registrations run. Aggregates into
reports/results_bdm.json. The Child Protection counterpart is
qa_tools/cp/orchestrate_cp.py.

RUNS ONE ARRIVAL AT A TIME, IN RECEIPT ORDER, and this reversed on
2026-09-28. It used to run the manifest IN PARALLEL by default
(qa_tools/common/parallel_orchestrate.py, one process per CPU core -
measured ~3.4x on this project's own 15-run manifest, see
plans/performance.md #4). Promotion is what ended that: a supply is
filed as a fill of its open slot or a RESUPPLY of it according to
whether a PROMOTION has filled it (REQ-PIPE-131), so arrival N's filing
depends on arrival N-1's promotion, which depends on arrival N-1's
checks. `--sequential` still exists and no longer changes anything.
Each arrival goes through qa_tools/common/arrival_lifecycle.py, the one
per-arrival lifecycle the hand-filed path shares (REQ-PIPE-086); the
measurement of what the ordering cost is in
parallel_orchestrate.run_manifest's docstring, which the batch used to
call. Results come back in arrival order, so output stays byte-for-byte
reproducible.

Assumes data/raw/ (generator output) exists - run_pipeline() below builds
its own data/duckdb_runs/*.duckdb per-run real warehouses itself (via
build_per_run_warehouses.build_all()), so nothing needs pre-building
first. `mothman pipeline run` (cli/pipeline.py, Phase 4) wraps this
function end to end - generates synthetic data, then calls run_pipeline()
- as the real replacement for the retired ./run_pipeline.sh.

Run via `mothman pipeline run` or `mothman debug run-dbt`/etc. (single-
tool debugging) - never invoke this module bare (plans/tooling.md #1
Phase 4's completeness bar: mothman is the only programmatic access
point to this repo).
"""
from __future__ import annotations
import shutil

from collections.abc import Callable
import json
import os
import sys
from datetime import date


from . import bdm_common
from qa_tools.common import (arrivals, delivery, delivery_log, in_flight_log,
                              supply_db)
from qa_tools.common import decision_log
from qa_tools.common import drift_reference
from qa_tools.common import held_blast_radius
from qa_tools.common import filing
from qa_tools.common import parallel_orchestrate
from qa_tools.common import left_out, own_table
from qa_tools.common import period_overlay
from qa_tools.common import promotion
from qa_tools.common import ticket_reconciler
from qa_tools.common import trial
from qa_tools.common.git_identity import get_run_by
from qa_tools.common.qa_results_reader import read_dataset_stats
from qa_tools.common.qa_results_reader import canonical_order
from qa_tools.common.qa_results_writer import (
    finish_run, open_run, write_qa_result)
from . import build_per_run_warehouses
from . import dataset_stats
from . import run_dbt_bdm
from . import run_soda_bdm
from . import run_datacontract_bdm
from . import run_evidently_bdm
from qa_tools.common import arrival_lifecycle
from qa_tools.common import replay_clock
from qa_tools.common import asset_time

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
MANIFEST_PATH = os.path.join(ROOT, "data", "raw", "manifest.json")
RESULTS_PATH = os.path.join(ROOT, "reports", "results_bdm.json")

AGENCY_ID = bdm_common.AGENCY_ID
COLLECTION_ID = bdm_common.COLLECTION_ID
DATASET_ID = bdm_common.DATASET_ID


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
    # The real file inside the delivery that arrived (REQ-GEN-043),
    # not a name taken from a manifest we were handed.
    csv_filename = entry["csv_path"]
    print(f"--- {run_id} ---")
    try:
        return _run_one_inner(entry, run_id, csv_filename, run_timestamp, run_by,
                               reference_run_id, on_step)
    finally:
        # IN A finally, so a run that raised does not leave its schemas
        # behind for a later sweep to guess about.
        _discard_this_runs_schemas(run_id)


def _run_one_inner(entry: dict, run_id: str, csv_filename: str, run_timestamp: str,
                    run_by: str, reference_run_id: str | None,
                    on_step: Callable[[str], None] | None) -> list[dict]:
    # BEFORE ANY TOOL WRITES, so the run exists with the identity only
    # this layer knows (REQ-PIPE-089 criterion 6). Each tool's own write
    # registers the run again, defensively, knowing nothing about who is
    # running it - which is why record_run coalesces rather than letting
    # the last writer win.
    open_run(AGENCY_ID, COLLECTION_ID, run_id, run_timestamp, run_by,
             purpose=entry.get("purpose"))

    # NOTHING IT MAY READ, NOTHING IT MAY CHECK (2026-10-02). Birth
    # Registrations has one table, and since REQ-PIPE-105 a run's own
    # table can be unreadable as an ordinary matter: a same-day resupply
    # beside an unpromoted red supply is CONTESTED (criterion 6), and
    # with nothing promoted for the day its view falls through to
    # nothing. Every check here is about that table, so the four tools
    # have nothing to do - and running them anyway raised UndefinedTable
    # and took the whole batch down on the first bootstrap after the
    # overlay landed. The run still records its stats and what it read,
    # which is where the reason lives.
    #
    # HELD, CONTESTED OR REFUSED, AND NOTHING ELSE (REQ-PIPE-115 criteria
    # 5, 6 and 9). Any other reason the table is missing raises: a run
    # that cannot read what its own arrival carried has been set up
    # wrong, and recording nothing for it would be a silent gap.
    with supply_db.connect(read_only=True, label="mothman:bdm-readable") as conn:
        why = own_table.why_unreadable(
            conn, run_id, build_per_run_warehouses.TABLE,
            supply_db.resolution_for(conn, run_id), own_dataset=DATASET_ID,
            arrival_key=_arrival_key(entry))
    readable = why is None
    if not readable:
        print(own_table.describe(run_id, build_per_run_warehouses.TABLE, why))
    run_step = _run_step if readable else (lambda collection, tool, rid, call: [])

    # THE REFERENCE IS RESOLVED PER SUPPLY, HERE (REQ-QAC-108 criteria
    # 2 and 4). It used to be one run chosen for the whole batch -
    # `manifest[0]["run_id"]` - which measures every supply against the
    # beginning of history, so drift stops being detectable about a
    # year in. The reference is a property of THIS dataset and THIS
    # period, and a batch-level argument can be neither.
    #
    # None is a real answer rather than a failure: the dataset's first
    # supply has nothing earlier to be measured against, and so does one
    # whose earlier periods hold only views. The Evidently step reports
    # that as a check with NO REFERENCE and never as a pass, which is
    # criterion 5.
    #
    # AFTER FILING, WHICH IS WHY THIS WORKS. arrival_lifecycle.process()
    # files the arrival, then runs this, then the gate, one arrival at a
    # time, so by the time this line runs
    # the arrival has a period and every earlier arrival has been
    # promoted or refused.
    #
    # AND WHAT THE COMPARISON CROSSES (REQ-QAC-108 criteria 8 to 17): an
    # owed, overdue period with no accepted supply between the reference
    # and now makes the drift and volume checks red, the measurement kept.
    assessment = None
    if reference_run_id is None:
        assessment = drift_reference.assess_arrival(DATASET_ID, entry["received_at"])
        reference_run_id = assessment.run_id if assessment else None

    def _dbt() -> list[dict]:
        return run_step(COLLECTION_ID, "dbt-core", run_id,
            lambda: run_dbt_bdm.evaluate_dbt_bdm(run_id, run_timestamp))

    def _the_rest() -> list[dict]:
        got: list[dict] = []
        _announce(on_step, RUN_STEPS[1])
        got.extend(run_step(COLLECTION_ID, "Soda Core", run_id,
            lambda: run_soda_bdm.evaluate_soda_bdm(run_id, run_timestamp)))
        _announce(on_step, RUN_STEPS[2])
        got.extend(run_step(COLLECTION_ID, "datacontract-cli", run_id,
            lambda: run_datacontract_bdm.evaluate_datacontract_bdm(run_id, run_timestamp)))
        _announce(on_step, RUN_STEPS[3])
        got.extend(run_step(COLLECTION_ID, "Evidently", run_id,
            lambda: run_evidently_bdm.evaluate_evidently_bdm(
                run_id, run_timestamp, reference_run_id=reference_run_id,
                assessment=assessment)))
        return got

    # dbt BESIDE THE OTHER THREE (REQ-TEST-116 criterion 3) - see
    # parallel_orchestrate.beside(). Results keep tool order either way.
    _announce(on_step, RUN_STEPS[0])
    from_dbt, from_the_rest = parallel_orchestrate.beside(_dbt, _the_rest)
    results: list[dict] = [*from_dbt, *from_the_rest]

    # Computed and committed here, not by the dashboard-building layer -
    # this is the one point in the whole pipeline with a legitimate,
    # already-open connection to real (here, synthetic-standing-in-for-
    # real) data, so this is where it has to happen. See dataset_stats.py's
    # own docstring - Keith's hard rule, 2026-09-16: CI must never touch
    # data, only ever committed history.
    _announce(on_step, RUN_STEPS[4])
    # Through the run's own view schema, like every other read of supply
    # data (REQ-PIPE-068 criterion 2). It used to connect to the
    # combined all-runs warehouse and filter by run_id in SQL, which
    # made "which rows is this run allowed to see" a property of the
    # query rather than of what the run can reach.
    conn = supply_db.connect(read_only=True)
    conn.execute(f"SET search_path = '{supply_db.run_schema(run_id)}'")
    # THE ROWS ARE THE ARRIVAL'S (REQ-PIPE-140): a re-run reads the same
    # supply, whose rows carry the first run's id in their own column.
    stats = dataset_stats.compute_dataset_stats(conn, entry.get("data_run_id", run_id), entry)
    resolution = supply_db.resolution_for(conn, run_id)
    tables_read = resolution.as_record()
    conn.close()

    # WHAT A HELD TABLE COST THE CHECKS THAT READ IT (REQ-PIPE-078
    # criterion 10) - see orchestrate_cp.py's identical block for the
    # full account of why a silently-absent check is the dangerous
    # direction and why this is its own pseudo-tool.
    # NOTHING PER CHECK FOR A RUN THAT MAY NOT READ ITS OWN TABLE
    # (REQ-PIPE-115 criteria 6 and 16): its dataset is signalled once, by
    # its outstanding item, and a cross-table check is never recorded
    # under the run of the held or contested supply it reads.
    blast = held_blast_radius.results_for(
        held=resolution.held, reads=promotion._declared_reads(),
        run_id=run_id, run_timestamp=run_timestamp) if readable else []
    if blast:
        print(held_blast_radius.describe(blast))
        write_qa_result(AGENCY_ID, COLLECTION_ID, run_id, run_timestamp,
                         held_blast_radius.TOOL, {"held": resolution.held},
                         verified=blast)
        results.extend(blast)
    # THE SAME RECONCILIATION AS CHILD PROTECTION'S (REQ-PIPE-115
    # criteria 17 and 19) - see left_out.py. Birth Registrations' tools
    # filter nothing (its one table is readable or nothing runs), so this
    # is the guard that keeps it so: a tool that started leaving checks
    # out here would refuse the run rather than lose them silently.
    compared = left_out.reconcile(run_id, left_out.take(run_id), blast, lambda check: True)
    if compared:
        write_qa_result(AGENCY_ID, COLLECTION_ID, run_id, run_timestamp, left_out.TOOL,
                         {"left_out": compared})
    # run_by stamped only on this write, not the 4 real-tool writes above -
    # one value per run is all qa_tools/common/changelog.py needs, and
    # dataset_stats.json is the one file guaranteed to exist for every
    # run (see write_qa_result()'s own docstring).
    write_qa_result(AGENCY_ID, COLLECTION_ID, run_id, run_timestamp, "dataset_stats", stats, run_by=run_by)

    # WHICH PHYSICAL TABLE THIS RUN READ (REQ-PIPE-068 criterion 5).
    # The view schema is thrown away when the run ends, and the
    # question is asked years later - of an audit, or of a check that
    # started failing - so the answer goes into committed history
    # beside the run's results rather than being reconstructed from a
    # staging schema that has since moved on.
    write_qa_result(AGENCY_ID, COLLECTION_ID, run_id, run_timestamp,
                     "tables_read", tables_read)

    # EVERYTHING THIS RUN PRODUCES IS NOW WRITTEN, so the run says so -
    # and only here (REQ-PIPE-089 criterion 13). A run that raised on
    # any step above never reaches this line, which is what keeps a
    # partial run invisible rather than indistinguishable from a
    # finished one.
    finish_run(run_id)
    return results


def _discard_this_runs_schemas(run_id: str) -> None:
    """Give back what this run borrowed, as soon as it is done with it.

    PER RUN RATHER THAN A SWEEP AT THE END (Keith, 2026-09-27). The
    schemas used to be dropped after the whole fan-out because under
    DuckDB a drop locked the entire database; PostgreSQL locks only
    what is being dropped, so that reason retired with the engine. See
    supply_db.drop_run_schemas() for the hazard the sweep carried that
    this does not.

    NEVER FAILS THE RUN. The results are already recorded by the time
    this happens, so a tidy-up that cannot complete is a thing to
    report and move past - `mothman supply tidy` clears whatever is
    left. Turning a finished run into a failed one over housekeeping
    would be the worse outcome.

    A TRIAL GIVES BACK MORE, because it staged into a schema of its
    own rather than into shared staging (REQ-PIPE-103 criterion 6).
    Read from the run id rather than passed in, so every route into
    this function gets it without remembering to - which is the same
    reason supply_db.is_trial_run() exists.
    """
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
    except Exception as exc:  # noqa: BLE001 - see the docstring
        print(f"{run_id}: could not discard this run's schemas ({type(exc).__name__}: {exc}) "
              f"- results are recorded; `mothman supply tidy` clears leftovers")


def run_single(run_id: str, csv_path: str, run_date: str, reference_run_id: str,
               run_by: str | None = None,
               on_step: Callable[[str], None] | None = None,
               received_at=None) -> list[dict]:
    """The single-arrival counterpart to run_pipeline()'s full-manifest
    batch loop - built for the AWS event-driven MVP (plans/running-
    thoughts.md #5 Thread B / docs/aws-event-driven-mvp-design.md), called
    once per file a Lambda handler receives rather than once per whole
    manifest. Reuses _run_one() completely unchanged - same 4-real-tool
    evaluation, same dataset_stats computation, same write_qa_result()
    call - fed a synthetic one-or-two-entry "manifest" instead of a loop,
    so this never touches reports/results_bdm.json (that file is the
    full-batch rollup; a single invocation only ever writes this one
    run's own qa_results/ entry).

    csv_path can be anywhere (e.g. Lambda's own /tmp) and is STAGED
    FROM THERE (REQ-PIPE-102, 2026-09-27). This used to copy it into
    data/raw/ under "<run_id>.csv" first, and the docstring called that
    "a real, deliberate normalization step, not a workaround for a
    bug". The constraint it normalised for was real once: both
    datacontract and Evidently resolved a BARE FILENAME against a
    fixed RAW_DIR. Neither reads a file any more, so the copy
    normalised nothing, and data/raw/ - which existed only to be the
    thing bare names resolved against - has gone with it.

    reference_run_id has no manifest[0] to read here, so the caller
    must supply it, and the supply it names must have been staged -
    which `mothman bdm qa --local-file` now does explicitly rather
    than leaving the reference as a file on disk.

    THE ROW-COUNT-GROWTH CHECK'S "PREVIOUS RUN", AND WHY THIS NO LONGER
    TAKES previous_run_id/previous_csv (REQ-GEN-043). This used to WRITE
    a synthetic two-entry manifest.json into the raw directory so that
    run_evidently_bdm._previous_run_file() - which read that file - had
    something to read, with the preceding entry supplied by the caller.
    Two things changed. The check now resolves "the immediately
    preceding run" from the arrivals RECOGNISED on disk, so there is no
    file to write; and a caller DECLARING which delivery came before
    this one is exactly the shape REQ-GEN-043 exists to remove - a
    supply filed from an assertion rather than from what arrived.

    So the parameters are gone rather than kept and ignored. For a run
    that is genuinely part of the recognised delivery history (the
    Synthetic CLI flow, and since REQ-PIPE-103 a hand-received supply
    the operator chose to keep), the check now works better than it
    did: the
    real preceding arrival is found from disk without anyone passing
    it. For a run that is NOT - a TRIAL, or a Lambda arrival landing
    outside the delivery tree - the check is
    silently SKIPPED, exactly as it already is for any genuinely-first
    run (_previous_run_file() returns None). That is the same real MVP
    simplification as before, reached by a different route: knowing what
    preceded an arrival that was never filed as a delivery still needs
    something this function does not have."""
    trial.require_trial(run_id, "orchestrate_bdm.run_single")
    run_timestamp = asset_time.now().isoformat()
    run_by = run_by or get_run_by()

    # STAGED FROM WHERE IT IS (REQ-PIPE-102, 2026-09-27). This used to
    # copy the arriving file into data/raw/ first, and the reason was
    # never staging - it was that run_evidently_bdm and
    # run_datacontract_bdm resolved a BARE FILENAME against that
    # directory. Both read the warehouse now, so the copy served
    # nothing, and the directory it served has gone with it.
    # An arrival-shaped entry for this ONE file, carrying only what we
    # observed: which run, when we received it, where the file is. No
    # injected severity - that is generator bookkeeping and nothing in
    # the pipeline may read it (REQ-GEN-043).
    #
    # `received_at` IS THE REAL RECEIPT WHERE THERE IS ONE
    # (REQ-PIPE-103). A supply the operator chose to keep was filed as
    # a delivery a moment ago and has a receipt written by our own
    # clock; staging it under the start of `run_date` instead would
    # name its table for a different instant than its receipt says,
    # and the two would disagree for ever. Where there is no receipt -
    # a trial, a Lambda arrival outside the delivery tree - the start
    # of the run date stands in, as it always did.
    entry = {"run_id": run_id, "run_index": 1, "csv_path": csv_path,
              "received_at": asset_time.isoformat(
                  received_at or asset_time.start_of_day(date.fromisoformat(run_date))),
              "delivery": run_id}

    # Stages the arrival and builds this run's views (REQ-PIPE-068).
    #
    # THE GLOBAL THAT USED TO LIVE HERE IS GONE. _run_one()'s
    # dataset_stats step connected to a module-level WAREHOUSE_DB_PATH -
    # the combined all-runs DuckDB warehouse in the batch path, which
    # does not exist at all in a single-arrival Lambda world - so this
    # function rebound that global to the run's own database file before
    # calling it. With one supply database there is nothing to rebind:
    # both paths open the same database and read through the run's own
    # view schema, which is what scoped the rows all along.
    # THE RECEIPT IS PASSED ON ONLY WHERE THERE REALLY IS ONE. With
    # none, build_one() names the staged table after the RUN rather
    # than after a day - which is what every caller without a receipt
    # needs, because two runs sharing a run_date would otherwise claim
    # one physical table in shared staging.
    build_per_run_warehouses.build_one(run_id, csv_path, run_date,
                                        received_at=received_at)

    return _run_one(entry, run_timestamp, run_by, reference_run_id, on_step=on_step)



def _arrival_key(entry: dict) -> str | None:
    """The arrival segment a run's staged table carries, where the entry
    has a receipt."""
    received = entry.get("received_at")
    return supply_db.arrival_segment(received) if received else None


def file_and_overlay(arrival) -> None:
    """Everything between staging an arrival and checking it - see
    orchestrate_cp.file_and_overlay() for the account of both steps.

    Birth Registrations has one table, so what the overlay adds here is
    REQ-PIPE-105 criterion 6: two files for it in ONE arrival make it
    contested. A later arrival's file for the same day supersedes the
    earlier waiting one at filing (REQ-PIPE-118), so two arrivals never
    leave two versions staged for one day.
    """
    filing.file_arrivals([arrival])
    period_overlay.rebuild_for_arrival(arrival, tables=[build_per_run_warehouses.TABLE])


def promote_after(arrival, got: list[dict], run_by: str) -> None:
    """Promotion follows the run - see orchestrate_cp.promote_after()."""
    promotion.report(promotion.after_runs(
        [arrival], got,
        agency_id=AGENCY_ID, collection_id=COLLECTION_ID,
        actor=promotion.RULE_ACTOR, actor_kind=decision_log.RULE,
        effective_at=promotion.effective_at_for(
            arrival.received_at, seed=arrival.run_id,
            before=promotion.next_receipt(arrival)).isoformat()))
    # THE KNOCK-ON OF WHAT IT PROMOTED (REQ-PIPE-121): every period the
    # promotions moved a table into owes its readers a re-evaluation, owed in
    # the promotion's own transaction and completed here.
    from qa_tools.common import knock_on

    knock_on.follow_up(COLLECTION_ID, run_by=run_by)


def entry_for(arrival) -> dict:
    """The run entry for one arrival.

    TWO FILES IN ONE ARRIVAL GET A RUN (REQ-PIPE-105 criterion 6,
    2026-10-02): CONTESTED, filed so the run has a period, while the
    overlay refuses to choose between the two staged tables. path_for()
    still refuses to choose, so such a run is pointed at its delivery
    directory, which is all `csv_path` is used for here. The hand-filed
    path used to call path_for() unconditionally and so refused a
    contested file the batch would check - one of the drifts
    REQ-PIPE-086 found.
    """
    path = (arrival.path_for(DATASET_ID) if DATASET_ID not in arrival.contested
            else arrival.path)
    return arrival.as_entry() | {"csv_path": str(path)}


#: Birth Registrations' half of the one per-arrival lifecycle
#: (REQ-PIPE-086 criterion 2) - see qa_tools/common/arrival_lifecycle.py.
STEPS = arrival_lifecycle.Steps(
    file_and_overlay=lambda arrival, among: file_and_overlay(arrival),
    entry_for=entry_for,
    run_one=lambda *args, **kw: _run_one(*args, **kw),
    promote_after=lambda arrival, got, run_by: promote_after(arrival, got, run_by))


def run_arrivals(found_arrivals, run_by: str, on_step=None) -> list[dict]:
    """The hand-filed path: the same per-arrival lifecycle as the batch
    (REQ-PIPE-086), in receipt order - see orchestrate_cp.run_arrivals()."""
    return arrival_lifecycle.process_all(
        sorted(found_arrivals, key=lambda a: (a.sequence, a.run_index, a.run_id)),
        steps=STEPS, run_by=run_by, on_step=on_step,
        exclusive=True)


# ON THE REPLAY'S OWN CLOCK (REQ-PIPE-081 criteria 27-31): the batch is always
# a replay, so on a synthetic asset every record it writes is stamped with the
# replay's simulated time rather than today's; on a real one, the wall clock.
@replay_clock.on_replay_clock
def run_pipeline(sequential: bool = False,
                 record_deliveries: bool = True) -> dict:
    # A RUN'S TOOLS OVERLAP unless told not to (REQ-TEST-116 criteria 3, 5).
    parallel_orchestrate.TOOLS_CONCURRENTLY = not sequential
    build_per_run_warehouses.build_all()

    # RECOGNISED FROM DISK, never read from a declaration
    # (REQ-GEN-043). The generator's manifest.json is bookkeeping, and
    # a pipeline reading it would be filing supplies from what it was
    # told rather than from what arrived.
    found_arrivals = arrivals.arrivals_for("civil-registration", "run_")

    # ONE COMMITTED FILE PER DELIVERY, WRITTEN ONCE (REQ-PIPE-069).
    # Recognition facts only - what arrived and what we thought it was.
    # A delivery spanning collections is recognised by both
    # orchestrators, so the second write being a no-op is the ordinary
    # case rather than a guard against a bug.
    #
    # UNLESS THE CALLER ALREADY DID (REQ-TEST-116): a bootstrap running
    # both collections side by side records every delivery once before
    # either starts, because "the second write is a no-op" is a race
    # when the two writes are simultaneous.
    if record_deliveries:
        delivery_log.record_all()

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
    in_flight_log.record(COLLECTION_ID, asset_time.now().isoformat(), still_arriving)
    # TWO FILES IN ONE ARRIVAL GET A RUN NOW (REQ-PIPE-105 criterion 6,
    # 2026-10-02). They were a delivery-level HOLD and were skipped here;
    # they are CONTESTED instead - filed, so the run has a period, and
    # the overlay refuses to choose between the two staged tables. The
    # run records why in its tables_read and checks nothing of its own.
    # path_for() still refuses to choose, so such a run is pointed at its
    # delivery directory, which is all `csv_path` is used for here.
    # The run entry each arrival gets is entry_for()'s, shared with the
    # hand-filed path; the list is kept for the results file's `runs`.
    manifest = [entry_for(a) for a in found_arrivals]

    # THE BATCH NO LONGER CHOOSES A REFERENCE RUN (REQ-QAC-108
    # criterion 4, 2026-09-29). It used to take the first manifest
    # entry, which was itself a fix for a hardcoded literal that went
    # stale every time the anchor date rolled forward - and the fix
    # carried the same defect one level up: every supply, for ever,
    # measured against the beginning of history. _run_one_inner()
    # resolves the reference per supply now, from what was recorded.
    # WHERE EACH SUPPLY BELONGS IS NOW RECORDED (REQ-PIPE-075 criterion
    # 7, 2026-09-28) - see the file_arrivals() call below, and
    # orchestrate_cp.py's identical one. Filings land in the database,
    # in `qa.filing` (REQ-PIPE-104), which is why that destination was
    # built before this switch was flipped rather than with it.

    run_timestamp = asset_time.now().isoformat()

    # Fails loudly here, before any real tool runs, if git identity isn't
    # configured (Keith's call, 2026-09-16) - see git_identity.py's own
    # docstring for why this can't fall back to "unknown".
    run_by = get_run_by()

    # IN RECEIPT ORDER, ONE ARRIVAL AT A TIME - file, check, promote,
    # next. See orchestrate_cp.py's identical block for the chain that
    # forces it and parallel_orchestrate.run_manifest's docstring for
    # what it cost and what it bought.
    # THROUGH THE ONE PER-ARRIVAL LIFECYCLE (REQ-PIPE-086 criterion 2),
    # the same function a hand-filed delivery goes through, so the two can
    # never compose these steps differently.
    # SCRIPTED PERSON DECISIONS, PLAYED BACK BETWEEN ARRIVALS (REQ-GEN-135):
    # the batch replay is the one place they are raised, and the player
    # refuses unless the asset declares itself synthetic.
    from qa_tools.common import scripted_decisions

    all_results = arrival_lifecycle.process_all(
        found_arrivals, steps=STEPS, run_by=run_by, run_timestamp=run_timestamp,
        player=scripted_decisions.Player(COLLECTION_ID))

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
        ticket_reconciler.after_runs(COLLECTION_ID))

    # NOTHING TO SWEEP HERE ANY MORE (Keith, 2026-09-27). Each run
    # discards its own view and dbt schemas as it finishes - see
    # _discard_this_runs_schemas() above and
    # supply_db.drop_run_schemas(). The blanket sweep that used to sit
    # here could not tell a schema left by an interrupted run from one
    # belonging to a run happening right now in another process, so it
    # is now an explicit `mothman supply tidy`, run by someone who
    # knows nothing else is going.

    # Read back rather than threaded through _run_one's own return value -
    # the lifecycle's contract is a flat list of check results, shared
    # with orchestrate_cp.py, not worth complicating for this. Also means
    # this is the exact same code path build_results_from_history.py uses for the committed-history-only rebuild, so the
    # two can't drift on how dataset_stats gets assembled.
    dataset_stats_by_run = {}
    for arrival in found_arrivals:
        stats = read_dataset_stats(AGENCY_ID, COLLECTION_ID, arrival.run_id)
        if stats is not None:
            dataset_stats_by_run[arrival.run_id] = stats

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
        "dataset": f"{AGENCY_ID}.{COLLECTION_ID}.{DATASET_ID}",
        "runs": manifest,
        "dataset_stats": dataset_stats_by_run,
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
    run_pipeline(sequential="--sequential" in sys.argv)
