"""
Builds one DuckDB file per Child Protection snapshot run under
data/cp_duckdb_runs/<run_id>.duckdb, each containing that run's 6 tables
under a `raw` schema - the Child Protection counterpart to
real_tools/bdm/build_per_run_warehouses.py, for the same reason: dbt's
source config and the Soda checks file both refer to bare table names
with no run_id-scoped `where`, so a real per-run `dbt test` / `soda scan`
result needs its own physical warehouse, one per periodic extract.

Unlike birth-registrations' single CSV per run, generator/generate_cp_runs.py
writes one directory per run_id with 6 CSVs (cp_clients.csv,
cp_notifications.csv, ...) - see data/cp_raw/manifest.json for the run list.
"""
from __future__ import annotations
import json
import os

import duckdb
import pandas as pd

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
CP_RAW_DIR = os.path.join(ROOT, "data", "cp_raw")
OUT_DIR = os.path.join(ROOT, "data", "cp_duckdb_runs")

TABLES = ["cp_clients", "cp_notifications", "cp_investigations", "cp_placements", "cp_carers", "cp_case_workers"]


def build_all(raw_dir: str = CP_RAW_DIR, out_dir: str = OUT_DIR) -> list[str]:
    with open(os.path.join(raw_dir, "manifest.json")) as f:
        manifest = json.load(f)

    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for entry in manifest:
        run_id = entry["run_id"]
        run_dir = os.path.join(raw_dir, run_id)
        db_path = os.path.join(out_dir, f"{run_id}.duckdb")
        if os.path.exists(db_path):
            os.remove(db_path)

        conn = duckdb.connect(db_path)
        conn.execute("CREATE SCHEMA IF NOT EXISTS raw")
        for table in TABLES:
            df = pd.read_csv(os.path.join(run_dir, f"{table}.csv"))
            combined_csv = os.path.join(out_dir, f"_{run_id}_{table}.csv")
            df.to_csv(combined_csv, index=False)
            conn.execute(
                f"CREATE OR REPLACE TABLE raw.{table} AS SELECT * FROM read_csv_auto(?, header=true)",
                [combined_csv],
            )
            os.remove(combined_csv)
        conn.close()
        paths.append(db_path)
        print(f"{run_id}: -> {db_path}")

    return paths


if __name__ == "__main__":
    build_all()
