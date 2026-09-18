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

Assumes data/raw/ (generator output), data/warehouse.duckdb (the combined
warehouse, still built by pipeline/load.py/orchestrate.py - see that
file's docstring for why it's still needed) and data/duckdb_runs/*.duckdb
(per-run real warehouses, qa_tools/bdm/build_per_run_warehouses.py)
already exist - run ./run_pipeline.sh first if they don't.

Run as `python3 -m qa_tools.bdm.orchestrate_bdm` (this is a package
now, not a flat script directory - see plans/qa-pipeline.md #84).
"""
from __future__ import annotations
import json
import os
import sys
from datetime import datetime, timezone

import duckdb

from qa_tools.common import parallel_orchestrate
from qa_tools.common.git_identity import get_run_by
from qa_tools.common.qa_results_reader import read_dataset_stats
from qa_tools.common.qa_results_writer import write_qa_result
from . import build_per_run_warehouses
from . import dataset_stats
from . import run_dbt_bdm
from . import run_soda_bdm
from . import run_datacontract_bdm
from . import run_evidently_bdm

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
MANIFEST_PATH = os.path.join(ROOT, "data", "raw", "manifest.json")
RESULTS_PATH = os.path.join(ROOT, "reports", "results_bdm.json")
WAREHOUSE_DB_PATH = os.path.join(ROOT, "data", "warehouse.duckdb")

AGENCY_ID = "registry-services"
DATASET_ID = "birth-registrations"


def _run_one(entry: dict, run_timestamp: str, run_by: str, reference_run_id: str, reference_csv: str) -> list[dict]:
    run_id = entry["run_id"]
    csv_filename = entry["file"]
    print(f"--- {run_id} ---")

    results: list[dict] = []
    results.extend(run_dbt_bdm.evaluate_dbt_bdm(run_id, run_timestamp))
    results.extend(run_soda_bdm.evaluate_soda_bdm(run_id, run_timestamp))
    results.extend(run_datacontract_bdm.evaluate_datacontract_bdm(run_id, csv_filename, run_timestamp))
    results.extend(run_evidently_bdm.evaluate_evidently_bdm(
        run_id, csv_filename, run_timestamp, reference_run_id=reference_run_id, reference_csv=reference_csv))

    # Computed and committed here, not by the dashboard-building layer -
    # this is the one point in the whole pipeline with a legitimate,
    # already-open connection to real (here, synthetic-standing-in-for-
    # real) data, so this is where it has to happen. See dataset_stats.py's
    # own docstring - Keith's hard rule, 2026-09-16: CI must never touch
    # data, only ever committed history.
    conn = duckdb.connect(WAREHOUSE_DB_PATH, read_only=True)
    stats = dataset_stats.compute_dataset_stats(conn, run_id, entry)
    conn.close()
    # run_by stamped only on this write, not the 4 real-tool writes above -
    # one value per run is all qa_tools/common/changelog.py needs, and
    # dataset_stats.json is the one file guaranteed to exist for every
    # run (see write_qa_result()'s own docstring).
    write_qa_result(AGENCY_ID, DATASET_ID, run_id, run_timestamp, "dataset_stats", stats, run_by=run_by)

    return results


def run_single(run_id: str, csv_path: str, run_date: str, dirty_severity: str, reference_run_id: str,
               reference_csv: str, run_by: str | None = None, previous_run_id: str | None = None,
               previous_csv: str | None = None) -> list[dict]:
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

    A second, separate real gap found while building this (not the same
    as the reference-run one above): run_evidently_bdm.evaluate_evidently_
    bdm()'s row-count-growth check reads RAW_DIR/manifest.json directly to
    find "the immediately preceding run" - there's no manifest at all in
    a single-arrival Lambda world, so this writes one, synthetically,
    containing just [previous_entry (if given), this_entry] - the same
    two-entry shape _previous_run_file() already knows how to read.
    Without previous_run_id/previous_csv (the MVP default - no caller
    passes them yet), the row-count-growth check is silently SKIPPED for
    every single Lambda-triggered run, exactly as it already is for any
    genuinely-first run today (_previous_run_file() returns None) - a
    real, deliberate MVP simplification, not a bug: knowing "what
    immediately preceded this delivery" needs either a real manifest
    concept or the caller (a Lambda handler, or whatever tracks recent
    deliveries) explicitly tracking and passing it, which nothing does
    yet. Flagged in the design doc as a real open follow-up, not solved
    here."""
    run_timestamp = datetime.now(timezone.utc).isoformat()
    run_by = run_by or get_run_by()

    os.makedirs(build_per_run_warehouses.RAW_DIR, exist_ok=True)
    csv_filename = f"{run_id}.csv"
    dest_path = os.path.join(build_per_run_warehouses.RAW_DIR, csv_filename)
    if os.path.abspath(csv_path) != os.path.abspath(dest_path):
        with open(csv_path, "rb") as src, open(dest_path, "wb") as dst:
            dst.write(src.read())

    entry = {"run_id": run_id, "file": csv_filename, "run_date": run_date, "dirty_severity": dirty_severity}
    synthetic_manifest = []
    if previous_run_id is not None:
        synthetic_manifest.append({"run_id": previous_run_id, "file": previous_csv})
    synthetic_manifest.append(entry)
    with open(os.path.join(build_per_run_warehouses.RAW_DIR, "manifest.json"), "w") as f:
        json.dump(synthetic_manifest, f)

    # out_dir passed explicitly, read off the module attribute rather than
    # relying on build_one()'s own default parameter value - a real bug
    # caught while writing this function's own test: a default arg is
    # bound once at module-import time, so a test (or any other caller)
    # monkeypatching build_per_run_warehouses.OUT_DIR afterwards would be
    # silently ignored and this would write into the REAL data/duckdb_runs/
    # instead - reproduced for real (a stray pytest_bdm_dirty.duckdb
    # actually appeared there) before this fix.
    db_path = build_per_run_warehouses.build_one(run_id, dest_path, run_date, dirty_severity,
                                                  out_dir=build_per_run_warehouses.OUT_DIR)

    # _run_one()'s own dataset_stats computation connects to the module-
    # level WAREHOUSE_DB_PATH global - the combined, all-runs warehouse
    # (pipeline/load.py) in the batch path, which doesn't exist at all in
    # a single-arrival Lambda world. Rebound here (global, not a local -
    # _run_one() reads the module's own global namespace, re-resolved on
    # every call, not captured at def time) to this run's own per-run
    # file instead - build_one() above now also creates a
    # main.birth_registrations VIEW there for exactly this reason (see
    # its own comment). Safe: a single Lambda invocation is single-
    # threaded, so there's no concurrent call this could race with.
    global WAREHOUSE_DB_PATH
    WAREHOUSE_DB_PATH = db_path
    return _run_one(entry, run_timestamp, run_by, reference_run_id, reference_csv)


def run_pipeline(sequential: bool = False) -> dict:
    build_per_run_warehouses.build_all()

    with open(MANIFEST_PATH) as f:
        manifest = json.load(f)

    # The first manifest entry (run_01, always clean by RUN_PLAN
    # construction) - NOT run_evidently_bdm.REFERENCE_RUN_ID, a hardcoded
    # literal that goes stale every time the anchor date rolls forward
    # (generator/anchor_date.py). A real bug, found live: with the anchor
    # date advanced, data/raw/'s actual run_01 file no longer matched that
    # constant, and because old dated files aren't cleaned up between
    # regenerations, evidently silently compared against a stale leftover
    # file from a previous anchor date instead of failing loudly - see
    # plans/qa-pipeline.md for the regression test this got.
    reference_entry = manifest[0]
    run_timestamp = datetime.now(timezone.utc).isoformat()
    # Fails loudly here, before any real tool runs, if git identity isn't
    # configured (Keith's call, 2026-09-16) - see git_identity.py's own
    # docstring for why this can't fall back to "unknown".
    run_by = get_run_by()
    all_results = parallel_orchestrate.run_manifest(
        manifest, _run_one, run_timestamp, run_by, reference_entry["run_id"], reference_entry["file"],
        sequential=sequential)

    # Read back rather than threaded through _run_one's own return value -
    # parallel_orchestrate.run_manifest's contract is a flat list of check
    # results, shared with orchestrate_cp.py, not worth complicating for
    # this. Also means this is the exact same code path build_results_
    # from_history.py uses for the committed-history-only rebuild, so the
    # two can't drift on how dataset_stats gets assembled.
    dataset_stats_by_run = {}
    for entry in manifest:
        stats = read_dataset_stats(AGENCY_ID, DATASET_ID, entry["run_id"])
        if stats is not None:
            dataset_stats_by_run[entry["run_id"]] = stats

    n_pass = sum(1 for r in all_results if r["status"] == "pass")
    n_warn = sum(1 for r in all_results if r["status"] == "warn")
    n_fail = sum(1 for r in all_results if r["status"] == "fail")
    n_error = sum(1 for r in all_results if r["status"] == "error")

    output = {
        "generated_at": run_timestamp,
        "dataset": "registry-services.civil-registration.birth-registrations",
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
