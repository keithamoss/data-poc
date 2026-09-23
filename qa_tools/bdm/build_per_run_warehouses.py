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

from qa_tools.common.csv_io import DUCKDB_NULLSTR, load_null_values_by_column, read_csv_explicit_nulls
from qa_tools.common import asset_time

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
RAW_DIR = os.path.join(ROOT, "data", "raw")
OUT_DIR = os.path.join(ROOT, "data", "duckdb_runs")
CONTRACT_PATH = os.path.join(ROOT, "contract", "bdm-birth-registrations-contract.yaml")


def build_one(run_id: str, csv_path: str, run_date: str, dirty_severity: str, out_dir: str = OUT_DIR,
              contract_path: str = CONTRACT_PATH) -> str:
    """Builds exactly one data/duckdb_runs/<run_id>.duckdb from one already-
    on-disk CSV - the single-arrival counterpart to build_all()'s per-
    manifest-entry loop body (same logic, factored out so a Lambda handler
    processing one arriving file doesn't need a manifest.json at all - see
    plans/running-thoughts.md #5 Thread B / docs/aws-event-driven-mvp-
    design.md). build_all() below is now just this, called once per
    manifest entry - verified byte-identical output for the same run."""
    null_values = load_null_values_by_column(contract_path).get("birth_registrations", {})
    os.makedirs(out_dir, exist_ok=True)
    db_path = os.path.join(out_dir, f"{run_id}.duckdb")
    if os.path.exists(db_path):
        os.remove(db_path)

    df = read_csv_explicit_nulls(csv_path, null_values)
    df["run_id"] = run_id
    df["run_date"] = run_date
    df["dirty_severity"] = dirty_severity

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
        "CREATE OR REPLACE TABLE raw.birth_registrations AS SELECT * FROM read_csv_auto(?, header=true, nullstr=?)",
        [combined_csv, DUCKDB_NULLSTR],
    )
    # A plain view, not used by dbt/Soda (both only ever query
    # raw.birth_registrations - the dbt source's own declared schema) -
    # added purely so qa_tools/bdm/dataset_stats.py's bare, unqualified
    # `birth_registrations` reference (written against the COMBINED
    # warehouse's own default `main` schema, pipeline/load.py) also
    # resolves against one of THESE per-run files - needed for
    # orchestrate_bdm.run_single() (plans/running-thoughts.md #5 Thread B),
    # which has no combined warehouse to point dataset_stats at in a
    # single-arrival Lambda world and reuses this per-run file for that
    # too. Harmless/unused for the existing batch path.
    conn.execute("CREATE OR REPLACE VIEW main.birth_registrations AS SELECT * FROM raw.birth_registrations")
    conn.close()
    os.remove(combined_csv)
    print(f"{run_id}: {len(df)} rows -> {db_path}")
    return db_path


def build_all(raw_dir: str = RAW_DIR, out_dir: str = OUT_DIR) -> list[str]:
    with open(os.path.join(raw_dir, "manifest.json")) as f:
        manifest = json.load(f)

    paths = []
    for entry in manifest:
        db_path = build_one(
            entry["run_id"], os.path.join(raw_dir, entry["file"]),
            asset_time.local_date(entry["received_at"]).isoformat(), entry["dirty_severity"],
            out_dir=out_dir)
        paths.append(db_path)

    return paths


if __name__ == "__main__":
    build_all()
