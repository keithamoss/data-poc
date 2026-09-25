"""
Stages one Child Protection snapshot's six tables into the one supply
database and gives that run a schema of views to read them through
(REQ-PIPE-068) - the Child Protection counterpart to
qa_tools/bdm/build_per_run_warehouses.py, for the same reason and with
the same history: dbt's source config and the Soda checks file both
refer to bare table names with no run-scoped `where`, so a genuine
per-run `dbt test` or `soda scan` needs a bare table name to resolve to
exactly one arrival's rows. Until 2026-09-25 that meant a DuckDB file
per run; it now means a view in that run's own schema, over one
physical staged table per arrival. See qa_tools/common/supply_db.py.

Unlike birth-registrations' single CSV per run, generator/generate_cp_runs.py
writes one directory per run_id with 6 CSVs (cp_clients.csv,
cp_notifications.csv, ...), which land together as ONE delivery.
"""
from __future__ import annotations
import os


from qa_tools.common import arrivals
from qa_tools.common import hierarchy
from qa_tools.common import supply_db
from qa_tools.common.csv_io import DUCKDB_NULLSTR, load_null_values_by_column, read_csv_explicit_nulls

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
CP_RAW_DIR = os.path.join(ROOT, "data", "cp_raw")
CONTRACT_PATH = os.path.join(ROOT, "contract", "child-protection-contract.yaml")

# The six CP tables, in the order contract/data-asset.yaml declares
# them - resolved, not restated (REQ-QAC-039).
TABLES = [d.table for d in hierarchy.datasets_in_collection("child-protection")]


def add_table_to_run(run_id: str, table: str, csv_path: str, db_path: str | None = None,
                      raw_dir: str = CP_RAW_DIR, contract_path: str = CONTRACT_PATH) -> str:
    """Loads exactly one CP table's CSV into that run's DuckDB file - the
    single-arrival counterpart to build_all()'s per-manifest-entry loop
    body, called once per arriving CP table file so a delivery's warehouse
    fills in incrementally as each of the 6 real tables lands, in whatever
    order they actually arrive (see plans/running-thoughts.md #5 Thread B /
    docs/aws-event-driven-mvp-design.md - CP's own completion-tracking
    design lives in qa_tools/cp/completion_tracker.py, not here; this
    function only ever loads one table, it never decides completeness).
    Safe to call for the same (run_id, table) more than once. The
    physical name carries the arrival, so replacing it re-loads that
    same arrival rather than losing a previous one - which is what
    makes this idempotent WITHOUT being the overwrite REQ-PIPE-060
    forbids.

    THE RUN'S VIEWS ARE REBUILT on every call, because CP's six tables
    arrive one at a time and a run is readable only for the tables that
    have actually landed. A table with no staged arrival is absent
    rather than empty, which is the distinction that stops a check
    passing over nothing.

    Also copies csv_path into raw_dir/<run_id>/<table>.csv if it isn't
    already there - a real constraint discovered while building this:
    run_datacontract_cp.py/run_evidently_cp.py both read CP's raw CSVs
    directly off disk under CP_RAW_DIR/<run_id>/, not just the DuckDB
    warehouse this function also builds (unlike BDM, where the combined
    warehouse is enough) - so a Lambda-arrived file needs to land in both
    places for orchestrate_cp.run_single()'s later 4-tool run to find it,
    same normalization orchestrate_bdm.run_single() does for its own
    RAW_DIR dependency."""
    null_values_by_table = load_null_values_by_column(contract_path)

    run_raw_dir = os.path.join(raw_dir, run_id)
    os.makedirs(run_raw_dir, exist_ok=True)
    dest_csv = os.path.join(run_raw_dir, f"{table}.csv")
    if os.path.abspath(csv_path) != os.path.abspath(dest_csv):
        with open(csv_path, "rb") as src, open(dest_csv, "wb") as dst:
            dst.write(src.read())

    df = read_csv_explicit_nulls(dest_csv, null_values_by_table.get(table, {}))
    staging_csv = os.path.join(run_raw_dir, f"_staged_{table}.csv")
    df.to_csv(staging_csv, index=False)

    physical = supply_db.staged_table(table, run_id)
    conn = supply_db.connect(path=db_path)
    try:
        supply_db.ensure_schemas(conn)
        try:
            conn.execute(
                f'CREATE OR REPLACE TABLE "{supply_db.STAGING_SCHEMA}"."{physical}" AS '
                "SELECT * FROM read_csv_auto(?, header=true, nullstr=?)",
                [staging_csv, DUCKDB_NULLSTR])
        finally:
            os.remove(staging_csv)
        supply_db.create_run_views(conn, run_id, supply_db.candidates_in(
            conn, supply_db.STAGING_SCHEMA, TABLES))
    finally:
        conn.close()
    print(f"{run_id}: {table} -> {supply_db.STAGING_SCHEMA}.{physical}")
    return physical


def build_all(raw_dir: str = CP_RAW_DIR, db_path: str | None = None,
               deliveries_dir=None, receipts_dir=None) -> list[str]:
    """Stage every recognised arrival - see the BDM counterpart for why
    `raw_dir` is kept but no longer read."""
    run_ids = []
    # One directory per arrival, recognised from disk (REQ-GEN-043) -
    # the six CP tables land together as ONE delivery, which is why the
    # run directory IS the delivery.
    for arrival in arrivals.arrivals_for("child-protection", "cp_run_",
                                          deliveries_dir, receipts_dir):
        run_id = arrival.run_id
        run_dir = str(arrival.path)
        for table in TABLES:
            add_table_to_run(run_id, table, os.path.join(run_dir, f"{table}.csv"),
                              db_path=db_path, raw_dir=raw_dir)
        run_ids.append(run_id)
        print(f"{run_id}: staged {len(TABLES)} table(s)")

    return run_ids


if __name__ == "__main__":
    build_all()
