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
from qa_tools.common import asset_time
from qa_tools.common import hierarchy
from qa_tools.common import load_log
from qa_tools.common import supply_db
from qa_tools.common.csv_io import DUCKDB_NULLSTR, load_null_values_by_column, read_csv_explicit_nulls

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
CP_RAW_DIR = os.path.join(ROOT, "data", "cp_raw")
CONTRACT_PATH = os.path.join(ROOT, "contract", "child-protection-contract.yaml")

# The six CP tables, in the order contract/data-asset.yaml declares
# them - resolved, not restated (REQ-QAC-039).
TABLES = [d.table for d in hierarchy.datasets_in_collection("child-protection")]


def add_table_to_run(run_id: str, table: str, csv_path: str, db_path: str | None = None,
                      raw_dir: str = CP_RAW_DIR, contract_path: str = CONTRACT_PATH,
                      ordinal: int = 0, received_at=None, dataset_id: str = "",
                      delivery_name: str = "", log_dir=None) -> str | None:
    """Stage exactly one CP table's CSV for that run, and rebuild the
    run's views. Returns the physical staged table, or None where the
    file could not be loaded at all.

    The single-arrival counterpart to build_all()'s per-delivery loop
    body, called once per arriving CP table file so a delivery fills in
    incrementally as each of the 6 real tables lands, in whatever order
    they actually arrive (see plans/running-thoughts.md #5 Thread B /
    docs/aws-event-driven-mvp-design.md - CP's own completion-tracking
    design lives in qa_tools/cp/completion_tracker.py, not here; this
    function only ever loads one table, it never decides completeness).

    Safe to call for the same (run_id, table) more than once. The
    physical name carries the arrival instant (criterion 4), so
    replacing it re-loads that same arrival rather than losing a
    previous one - which is what makes this idempotent WITHOUT being
    the overwrite REQ-PIPE-060 forbids, and is also criterion 15: what
    is already there is replaced rather than trusted, because a table
    with no load record is unloaded whatever the catalogue says.

    `received_at` IS OUR OWN RECEIPT INSTANT and nothing else
    (criterion 11) - never a timestamp inside the supplier's file,
    never a column in their data, never the file's mtime.

    THE RUN'S VIEWS ARE REBUILT on every call, because CP's six tables
    arrive one at a time and a run is readable only for the tables that
    have actually landed. A table with no staged arrival is absent
    rather than empty, which is the distinction that stops a check
    passing over nothing.

    A FILE THAT CANNOT BE LOADED LEAVES NO TABLE (criterion 5) and does
    not raise, so the delivery's other five tables still stage
    (criterion 6).

    Also copies csv_path into raw_dir/<run_id>/<table>.csv if it isn't
    already there - a real constraint discovered while building this:
    run_datacontract_cp.py/run_evidently_cp.py both read CP's raw CSVs
    directly off disk under CP_RAW_DIR/<run_id>/, not just the staged
    tables this function also builds (unlike BDM, where the warehouse
    is enough) - so a Lambda-arrived file needs to land in both places
    for orchestrate_cp.run_single()'s later 4-tool run to find it, the
    same normalization orchestrate_bdm.run_single() does for its own
    RAW_DIR dependency.
    """
    arrival = received_at if received_at is not None else run_id
    physical = supply_db.staged_table(table, arrival, ordinal)
    key = supply_db.arrival_key(arrival)
    delivery_name = delivery_name or run_id
    dataset_id = dataset_id or table

    conn = supply_db.connect(path=db_path)
    try:
        supply_db.ensure_schemas(conn)
        rows = None
        try:
            run_raw_dir = os.path.join(raw_dir, run_id)
            os.makedirs(run_raw_dir, exist_ok=True)
            dest_csv = os.path.join(run_raw_dir, os.path.basename(csv_path) if ordinal
                                     else f"{table}.csv")
            if os.path.abspath(csv_path) != os.path.abspath(dest_csv):
                with open(csv_path, "rb") as src, open(dest_csv, "wb") as dst:
                    dst.write(src.read())

            df = read_csv_explicit_nulls(dest_csv,
                                          load_null_values_by_column(contract_path).get(table, {}))
            # Our own scratch, for the reason supply_db.staging_csv()
            # gives: a temp file in a tree anything else reads back is
            # a stray artefact waiting to be reported as one.
            staging_csv = str(supply_db.staging_csv(physical))
            df.to_csv(staging_csv, index=False)
            try:
                conn.execute(
                    f'CREATE OR REPLACE TABLE "{supply_db.STAGING_SCHEMA}"."{physical}" AS '
                    "SELECT * FROM read_csv_auto(?, header=true, nullstr=?)",
                    [staging_csv, DUCKDB_NULLSTR])
            finally:
                os.remove(staging_csv)
            rows = len(df)
        except Exception as exc:  # noqa: BLE001 - every load failure is the same outcome
            conn.execute(f'DROP TABLE IF EXISTS "{supply_db.STAGING_SCHEMA}"."{physical}"')
            load_log.record_load(delivery_name, dataset_id, physical, load_log.FAILED,
                             asset_time.now().isoformat(),
                             reason=f"{type(exc).__name__}: {exc}", log_dir=log_dir)
            print(f"{run_id}: {table} FAILED to load ({type(exc).__name__}: {exc}) "
                  f"- no table staged, recorded for human action")
            return None
        # AFTER THE LOAD, NEVER BEFORE (criterion 14).
        load_log.record_load(delivery_name, dataset_id, physical, load_log.LOADED,
                         asset_time.now().isoformat(), row_count=rows, log_dir=log_dir)
        res = supply_db.create_run_views(conn, run_id, supply_db.candidates_in(
            conn, supply_db.STAGING_SCHEMA, TABLES, arrival=key,
            loaded=load_log.loaded_tables(log_dir)))
        # Recorded at staging time, which is the only moment this is an
        # observed fact rather than a re-derivation.
        supply_db.record_resolution(conn, res)
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
        # WHAT IS IN THIS DELIVERY, not what we assumed would be
        # (REQ-PIPE-058). This used to loop over the six table names and
        # build `<table>.csv` for each, so Child Protection did not use
        # pattern attribution at all - a supplier renaming an extract
        # was a CODE change here while being a configuration change for
        # Birth Registrations. It also meant a delivery missing a file
        # failed on a path that did not exist rather than simply not
        # staging that dataset.
        staged = 0
        for dataset_id, filenames in sorted(arrival.files_by_dataset.items()):
            table = hierarchy.dataset(dataset_id).table
            for ordinal, filename in enumerate(sorted(filenames), start=1):
                # EVERY FILE THAT MATCHED IS STAGED, including both
                # halves of a held supply (REQ-PIPE-059): the material
                # to resolve the hold with has to be there. They get
                # distinct physical names, and no view resolves the
                # logical one - REQ-PIPE-068 refuses to choose between
                # candidates - so nothing can read it, which is how
                # "staged but not checked" is enforced by the mechanism
                # rather than by remembering.
                # AN ORDINAL, NOT THE FILENAME - a supplier's filename
                # must never reach a SQL identifier, and the ordinal is
                # ours.
                if add_table_to_run(
                        run_id, table, os.path.join(str(arrival.path), filename),
                        db_path=db_path, raw_dir=raw_dir,
                        ordinal=ordinal if len(filenames) > 1 else 0,
                        received_at=arrival.received_at, dataset_id=dataset_id,
                        delivery_name=arrival.delivery_name) is not None:
                    staged += 1
        run_ids.append(run_id)
        print(f"{run_id}: staged {staged} table(s)")

    return run_ids


if __name__ == "__main__":
    build_all()
