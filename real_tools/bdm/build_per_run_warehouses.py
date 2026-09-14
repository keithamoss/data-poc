"""
Builds one DuckDB file per run under data/duckdb_runs/<run_id>.duckdb, each
containing ONLY that run's rows in a `birth_registrations` table - the same
table name pipeline/load.py's combined warehouse uses, and the same one
dbt_project/models/staging/sources.yml declares as the `raw.birth_registrations`
source.

Why per-run databases rather than one combined warehouse.duckdb (which is
what pipeline/load.py builds, still needed for build_dashboard_data.py's
own direct queries against a run_id filter): a real dbt/Soda invocation
has no run_id-scoped `where` clause to filter by (README.md is explicit
that the schema.yml/checks.yml files "don't need to change" to run the real
tools), so the only way to get a real per-run `dbt test` / `soda scan`
result - matching this dataset's own production reality of one daily
extract landed and tested at a time - is to
point each invocation at a warehouse containing just that one day's rows.
Nothing about the SQL model or schema.yml/checks.yml changes; only which
physical DuckDB file the tool connects to for a given run.
"""
from __future__ import annotations
import json
import os

import duckdb
import pandas as pd

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
RAW_DIR = os.path.join(ROOT, "data", "raw")
OUT_DIR = os.path.join(ROOT, "data", "duckdb_runs")


def build_all(raw_dir: str = RAW_DIR, out_dir: str = OUT_DIR) -> list[str]:
    with open(os.path.join(raw_dir, "manifest.json")) as f:
        manifest = json.load(f)

    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for entry in manifest:
        run_id = entry["run_id"]
        db_path = os.path.join(out_dir, f"{run_id}.duckdb")
        if os.path.exists(db_path):
            os.remove(db_path)

        df = pd.read_csv(os.path.join(raw_dir, entry["file"]))
        df["run_id"] = run_id
        df["run_date"] = entry["run_date"]
        df["dirty_severity"] = entry["dirty_severity"]

        combined_csv = os.path.join(out_dir, f"_{run_id}.csv")
        df.to_csv(combined_csv, index=False)

        conn = duckdb.connect(db_path)
        # dbt_project/models/staging/sources.yml declares this source as
        # `raw.birth_registrations` - a real dbt source resolves through the
        # profile's database/schema, so the table has to live in a schema
        # actually named "raw" for `{{ source('raw', 'birth_registrations') }}`
        # to find it, not DuckDB's default "main" schema.
        conn.execute("CREATE SCHEMA IF NOT EXISTS raw")
        conn.execute(
            "CREATE OR REPLACE TABLE raw.birth_registrations AS SELECT * FROM read_csv_auto(?, header=true)",
            [combined_csv],
        )
        conn.close()
        os.remove(combined_csv)
        paths.append(db_path)
        print(f"{run_id}: {len(df)} rows -> {db_path}")

    return paths


if __name__ == "__main__":
    build_all()
