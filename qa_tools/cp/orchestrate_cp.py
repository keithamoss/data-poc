"""
Runs all four REAL tools (dbt-core, Soda Core, datacontract-cli, Evidently)
against every generated Child Protection snapshot run - the CP counterpart
to qa_tools/bdm/orchestrate_bdm.py. Aggregates into
reports/results_cp.json, same check-result record shape
(agency_id/collection_id/dataset_id/...) as reports/results_bdm.json,
except dataset_id varies per result across the 6 CP tables instead of
being one constant.

Runs the manifest's runs IN PARALLEL by default (qa_tools/common/
parallel_orchestrate.py, shared with orchestrate_bdm.py - see that
file's docstring and plans/performance.md #4), with a --sequential flag
for easier debugging.

Assumes data/cp_raw/ (generator/generate_cp_runs.py's output) already
exists - run that first if it doesn't. Builds data/cp_duckdb_runs/ itself
via build_cp_warehouses.build_all().

Run as `python3 -m qa_tools.cp.orchestrate_cp` (this is a package
now, not a flat script directory - see plans/qa-pipeline.md #84).
"""
from __future__ import annotations

from collections.abc import Callable
import json
import os
import sys


from qa_tools.common import arrivals, delivery, in_flight_log, run_id_guard, supply_db
from qa_tools.common import hierarchy
from qa_tools.common import parallel_orchestrate
from qa_tools.common.git_identity import get_run_by
from qa_tools.common.qa_results_reader import read_dataset_stats
from qa_tools.common.qa_results_writer import write_qa_result
from . import build_cp_warehouses
from . import cp_common
from . import dataset_stats
from . import run_dbt_cp
from . import run_soda_cp
from . import run_datacontract_cp
from . import run_evidently_cp
from qa_tools.common import asset_time

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
MANIFEST_PATH = os.path.join(ROOT, "data", "cp_raw", "manifest.json")
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


def _announce(on_step, label: str) -> None:
    """Report the step ABOUT to start. Optional by design: every existing
    caller (the full-manifest batch loop, the AWS Lambda handlers, the
    tests) passes nothing and behaves exactly as before - only the
    interactive CLI, where a human is actually watching, opts in."""
    if on_step is not None:
        on_step(label)

def _run_one(entry: dict, run_timestamp: str, run_by: str, reference_run_id: str,
             on_step: Callable[[str], None] | None = None) -> list[dict]:
    run_id = entry["run_id"]
    print(f"--- {run_id} ---")

    results: list[dict] = []
    _announce(on_step, RUN_STEPS[0])
    results.extend(run_dbt_cp.evaluate_dbt_cp(run_id, run_timestamp))
    _announce(on_step, RUN_STEPS[1])
    results.extend(run_soda_cp.evaluate_soda_cp(run_id, run_timestamp))
    _announce(on_step, RUN_STEPS[2])
    results.extend(run_datacontract_cp.evaluate_datacontract_cp(run_id, run_timestamp))
    _announce(on_step, RUN_STEPS[3])
    results.extend(run_evidently_cp.evaluate_evidently_cp(run_id, run_timestamp, reference_run_id=reference_run_id))

    # Same rationale as orchestrate_bdm.py's identical block - see
    # qa_tools/bdm/dataset_stats.py's own docstring.
    _announce(on_step, RUN_STEPS[4])
    conn = supply_db.connect(read_only=True)
    conn.execute(f"SET search_path = '{supply_db.run_schema(run_id)}'")
    stats = dataset_stats.compute_dataset_stats(conn, entry)
    tables_read = supply_db.resolution_for(conn, run_id).as_record()
    conn.close()
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
    return results


def run_single(entry: dict, reference_run_id: str, run_by: str | None = None,
               on_step: Callable[[str], None] | None = None) -> list[dict]:
    """The single-delivery counterpart to run_pipeline_cp()'s full-manifest
    batch loop - built for the AWS event-driven MVP (plans/running-
    thoughts.md #5 Thread B / docs/aws-event-driven-mvp-design.md).

    Unlike orchestrate_bdm.run_single() (one call per arriving file), this
    is called only ONCE per delivery, after a CP ingest Lambda has already
    called build_cp_warehouses.add_table_to_run() for all 6 real tables
    (each one landing its own CSV under data/cp_raw/<run_id>/ and its own
    table in data/cp_duckdb_runs/<run_id>.duckdb) and confirmed completion
    via qa_tools/cp/completion_tracker.py - this function has no way to
    check that itself, since it has no manifest to cross-reference against;
    calling it before all 6 tables have actually landed produces exactly
    the kind of incomplete/wrong cross-table-check result the explicit-
    completion-signal design exists to prevent.

    `entry` is a manifest-entry-shaped dict for this one delivery
    (run_id/received_at/dirty_severity at minimum - see data/cp_raw/
    manifest.json's own real shape for the full convention; row_counts
    isn't required, dataset_stats.compute_dataset_stats() derives its own
    counts from the live warehouse instead of trusting a passed-in one)."""
    run_timestamp = asset_time.now().isoformat()
    run_by = run_by or get_run_by()
    return _run_one(entry, run_timestamp, run_by, reference_run_id, on_step=on_step)


def run_pipeline_cp(sequential: bool = False) -> dict:
    build_cp_warehouses.build_all()

    # RECOGNISED FROM DISK, never read from a declaration
    # (REQ-GEN-043) - see orchestrate_bdm.py's identical comment.
    found_arrivals = arrivals.arrivals_for("child-protection", "cp_run_")

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
    run_id_guard.check(cp_common.AGENCY_ID, cp_common.COLLECTION_ID, found_arrivals)
    reference_run_id = manifest[0]["run_id"]
    run_timestamp = asset_time.now().isoformat()
    # Fails loudly here, before any real tool runs - see orchestrate_bdm.py's
    # identical comment and git_identity.py's own docstring.
    run_by = get_run_by()
    all_results = parallel_orchestrate.run_manifest(
        manifest, _run_one, run_timestamp, run_by, reference_run_id, sequential=sequential)

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

    # Same rationale as orchestrate_bdm.py's identical block.
    dataset_stats_by_run = {}
    for entry in manifest:
        stats = read_dataset_stats(cp_common.AGENCY_ID, cp_common.COLLECTION_ID, entry["run_id"])
        if stats is not None:
            dataset_stats_by_run[entry["run_id"]] = stats

    n_pass = sum(1 for r in all_results if r["status"] == "pass")
    n_warn = sum(1 for r in all_results if r["status"] == "warn")
    n_fail = sum(1 for r in all_results if r["status"] == "fail")
    n_error = sum(1 for r in all_results if r["status"] == "error")

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
    run_pipeline_cp(sequential="--sequential" in sys.argv)
