"""
Runs all four REAL tools (dbt-core, Soda Core, datacontract-cli, Evidently)
against every generated Birth Registrations run. Aggregates into
reports/results_bdm.json. The Child Protection counterpart is
qa_tools/cp/orchestrate_cp.py.

Runs the manifest's runs IN PARALLEL by default (qa_tools/common/
parallel_orchestrate.py, one process per CPU core - measured ~3.4x on
this project's own 15-run manifest, see plans/performance.md #4), with a
--sequential flag for easier debugging (parallel workers interleave their
print output and stack traces; a single run under investigation is
simpler to chase down sequentially). Either way, results come back in
manifest order, so output stays byte-for-byte reproducible for a given
manifest.

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

from collections.abc import Callable
import json
import os
import sys
from datetime import date


from . import bdm_common
from qa_tools.common import (arrivals, delivery, delivery_log, in_flight_log,
                              run_id_guard, supply_db)
from qa_tools.common import backlog
from qa_tools.common import parallel_orchestrate
from qa_tools.common.git_identity import get_run_by
from qa_tools.common.qa_results_reader import read_dataset_stats
from qa_tools.common.qa_results_reader import canonical_order
from qa_tools.common.qa_results_writer import write_qa_result
from . import build_per_run_warehouses
from . import dataset_stats
from . import run_dbt_bdm
from . import run_soda_bdm
from . import run_datacontract_bdm
from . import run_evidently_bdm
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

def _run_one(entry: dict, run_timestamp: str, run_by: str, reference_run_id: str, reference_csv: str,
             on_step: Callable[[str], None] | None = None) -> list[dict]:
    run_id = entry["run_id"]
    # The real file inside the delivery that arrived (REQ-GEN-043),
    # not a name taken from a manifest we were handed.
    csv_filename = entry["csv_path"]
    print(f"--- {run_id} ---")

    results: list[dict] = []
    _announce(on_step, RUN_STEPS[0])
    results.extend(_run_step(COLLECTION_ID, "dbt-core", run_id,
        lambda: run_dbt_bdm.evaluate_dbt_bdm(run_id, run_timestamp)))
    _announce(on_step, RUN_STEPS[1])
    results.extend(_run_step(COLLECTION_ID, "Soda Core", run_id,
        lambda: run_soda_bdm.evaluate_soda_bdm(run_id, run_timestamp)))
    _announce(on_step, RUN_STEPS[2])
    results.extend(_run_step(COLLECTION_ID, "datacontract-cli", run_id,
        lambda: run_datacontract_bdm.evaluate_datacontract_bdm(run_id, csv_filename, run_timestamp)))
    _announce(on_step, RUN_STEPS[3])
    results.extend(_run_step(COLLECTION_ID, "Evidently", run_id,
        lambda: run_evidently_bdm.evaluate_evidently_bdm( run_id, csv_filename, run_timestamp, reference_run_id=reference_run_id, reference_csv=reference_csv)))

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
    stats = dataset_stats.compute_dataset_stats(conn, run_id, entry)
    tables_read = supply_db.resolution_for(conn, run_id).as_record()
    conn.close()
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
    return results


def run_single(run_id: str, csv_path: str, run_date: str, reference_run_id: str,
               reference_csv: str, run_by: str | None = None,
               on_step: Callable[[str], None] | None = None) -> list[dict]:
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

    csv_path can be anywhere (e.g. Lambda's own /tmp) - run_datacontract_
    bdm.evaluate_datacontract_bdm()/run_evidently_bdm.evaluate_evidently_
    bdm() both resolve their csv_filename argument against the fixed
    RAW_DIR module constant internally (a real constraint discovered
    while building this, not something run_pipeline()'s manifest loop
    ever had to work around, since every manifest entry's file already
    lives there), so this copies the arrived file into RAW_DIR under
    "<run_id>.csv" first and uses that relative name for every downstream
    call - a real, deliberate normalization step, not a workaround for a
    bug. reference_run_id/reference_csv have no manifest[0] to read here -
    the caller must supply them, and reference_csv must already be a
    filename that resolves under RAW_DIR (the design doc's own "open
    question" on where a production reference run/file actually lives
    once there's no manifest at all is still open - this assumes it's
    already present, e.g. bundled with the Lambda deployment or fetched
    separately before this is called).

    THE ROW-COUNT-GROWTH CHECK'S "PREVIOUS RUN", AND WHY THIS NO LONGER
    TAKES previous_run_id/previous_csv (REQ-GEN-043). This used to WRITE
    a synthetic two-entry manifest.json into RAW_DIR so that
    run_evidently_bdm._previous_run_file() - which read that file - had
    something to read, with the preceding entry supplied by the caller.
    Two things changed. The check now resolves "the immediately
    preceding run" from the arrivals RECOGNISED on disk, so there is no
    file to write; and a caller DECLARING which delivery came before
    this one is exactly the shape REQ-GEN-043 exists to remove - a
    supply filed from an assertion rather than from what arrived.

    So the parameters are gone rather than kept and ignored. For a run
    that is genuinely part of the recognised delivery history (the
    Synthetic CLI flow), the check now works better than it did: the
    real preceding arrival is found from disk without anyone passing
    it. For a run that is NOT - an ad-hoc local file, an S3 key, a
    Lambda arrival landing outside the delivery tree - the check is
    silently SKIPPED, exactly as it already is for any genuinely-first
    run (_previous_run_file() returns None). That is the same real MVP
    simplification as before, reached by a different route: knowing what
    preceded an arrival that was never filed as a delivery still needs
    something this function does not have."""
    run_timestamp = asset_time.now().isoformat()
    run_by = run_by or get_run_by()

    os.makedirs(build_per_run_warehouses.RAW_DIR, exist_ok=True)
    csv_filename = f"{run_id}.csv"
    dest_path = os.path.join(build_per_run_warehouses.RAW_DIR, csv_filename)
    if os.path.abspath(csv_path) != os.path.abspath(dest_path):
        with open(csv_path, "rb") as src, open(dest_path, "wb") as dst:
            dst.write(src.read())

    # An arrival-shaped entry for this ONE file, carrying only what we
    # observed: which run, when we received it, where the file is. No
    # injected severity - that is generator bookkeeping and nothing in
    # the pipeline may read it (REQ-GEN-043).
    entry = {"run_id": run_id, "run_index": 1, "csv_path": dest_path,
              "received_at": asset_time.isoformat(
                  asset_time.start_of_day(date.fromisoformat(run_date))),
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
    build_per_run_warehouses.build_one(run_id, dest_path, run_date)

    return _run_one(entry, run_timestamp, run_by, reference_run_id, reference_csv, on_step=on_step)



def run_pipeline(sequential: bool = False) -> dict:
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
    for d in delivery.list_deliveries():
        delivery_log.record(d, arrivals.recognise(d))

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
    # A HELD SUPPLY IS SKIPPED, NOT FATAL (REQ-PIPE-059). Birth
    # Registrations is the only dataset in its collection, so a held
    # one means this arrival contributes nothing - but path_for() still
    # refuses to choose, and that refusal used to arrive as an
    # exception and take every other arrival with it.
    manifest = [a.as_entry() | {"csv_path": str(a.path_for("birth-registrations"))}
                for a in found_arrivals if "birth-registrations" not in a.held]

    # The first manifest entry (run_01, always clean by RUN_PLAN
    # construction) - NOT run_evidently_bdm.REFERENCE_RUN_ID, a hardcoded
    # literal that goes stale every time the anchor date rolls forward
    # (generator/anchor_date.py). A real bug, found live: with the anchor
    # date advanced, data/raw/'s actual run_01 file no longer matched that
    # constant, and because old dated files aren't cleaned up between
    # regenerations, evidently silently compared against a stale leftover
    # file from a previous anchor date instead of failing loudly - see
    # plans/qa-pipeline.md for the regression test this got.
    # WHERE EACH SUPPLY BELONGS IS NOT RECORDED YET, DELIBERATELY
    # (REQ-PIPE-062, Keith 2026-09-25). The assignment rule is built
    # and tested - qa_tools/common/assignment.py - and calling
    # filing.file_arrivals() here is all that is needed to turn it on.
    # It is off because ONLY A PROMOTION FILLS A SLOT and promotion
    # does not exist until batch 4, so today every supply that is not
    # on time for its own current slot files against the oldest slot
    # in the calendar: measured on a real run, 102 of 108 supplies
    # landed on 2023-Q1. A filing is WRITE-ONCE by criterion 10, so
    # recording those would bake a known artefact of a missing
    # dependency into permanent history, where it later reads as data.
    # Turn this on in the sprint that lands promotion, not before.

    # BEFORE ANY REAL TOOL RUNS (REQ-PIPE-057 criterion 19). Run ids
    # are positional, so a change in what recognition returns renames
    # committed history - a failure that would otherwise be found when
    # CI went red on paths nothing in this file mentions.
    run_id_guard.check(AGENCY_ID, COLLECTION_ID, found_arrivals)
    reference_entry = manifest[0]
    run_timestamp = asset_time.now().isoformat()
    # Fails loudly here, before any real tool runs, if git identity isn't
    # configured (Keith's call, 2026-09-16) - see git_identity.py's own
    # docstring for why this can't fall back to "unknown".
    run_by = get_run_by()
    all_results = parallel_orchestrate.run_manifest(
        manifest, _run_one, run_timestamp, run_by, reference_entry["run_id"],
        reference_entry["csv_path"],
        sequential=sequential)

    # DISCARD THE RUN SCHEMAS (REQ-PIPE-068 criteria 1 and 6). Here, after
    # the fan-out, rather than at the end of each run: dropping a schema
    # is a WRITE, DuckDB gives a writer an exclusive lock over the whole
    # database, and a worker that tidied up after itself would lock out
    # every other worker still reading. Sweeping everything is also what
    # clears a schema left behind by an interrupted run - it is
    # identifiable on its own terms, from its name alone, which is the
    # whole reason the name carries the run id.
    conn = supply_db.connect()
    try:
        dropped = supply_db.drop_orphan_run_schemas(conn)
    finally:
        conn.close()
    if dropped:
        print(f"discarded {len(dropped)} per-run view schema(s)")

    # HOW FAR PROCESSING GOT (REQ-PIPE-061 criteria 6-8). Advanced
    # AFTER the fan-out and only over arrivals that are genuinely
    # staged, so an interrupted run leaves the rest to the next one in
    # the same order. The marker is global - one arrival may span
    # collections - so both orchestrators advance the same one, and
    # advance() never moves it backwards.
    backlog.advance_past_staged()

    # Read back rather than threaded through _run_one's own return value -
    # parallel_orchestrate.run_manifest's contract is a flat list of check
    # results, shared with orchestrate_cp.py, not worth complicating for
    # this. Also means this is the exact same code path build_results_
    # from_history.py uses for the committed-history-only rebuild, so the
    # two can't drift on how dataset_stats gets assembled.
    dataset_stats_by_run = {}
    for entry in manifest:
        stats = read_dataset_stats(AGENCY_ID, COLLECTION_ID, entry["run_id"])
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
            "engines": sorted(set(r["engine"] for r in all_results)),
        },
    }

    os.makedirs(os.path.dirname(RESULTS_PATH), exist_ok=True)
    with open(RESULTS_PATH, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\n{len(all_results)} real check results ({n_pass} pass / {n_warn} warn / {n_fail} fail"
          f"{f' / {n_error} error' if n_error else ''}) across {len(manifest)} runs -> {RESULTS_PATH}")
    return output


if __name__ == "__main__":
    run_pipeline(sequential="--sequential" in sys.argv)
