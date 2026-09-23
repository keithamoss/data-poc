"""
Loads every generated run CSV in data/raw/ into one DuckDB table,
birth_registrations, tagged with run_id/run_date - the "warehouse" that all
four check engines (contract, soda, dbt, drift) query against, and that
real dbt-duckdb / soda-core-duckdb also connect to directly.

One table with a run_id column (rather than one table per run) is what lets
the drift engine compare across runs, and lets the "last 24h" scoped Soda
check (bdm-birth-registrations-soda-checks.yml's `filter ... [recent]`
block) filter on extract_timestamp within a single unified table, exactly
as it would against a real warehouse.

is_multiple_birth comes back from pandas.to_csv as a "True"/"False" string;
normalized to 0/1 on the way in so every engine (equivalent and real alike)
sees the same representation DuckDB itself would use for a BOOLEAN column
cast from an integer.
"""
from __future__ import annotations
import json
import os

import duckdb
import pandas as pd

from qa_tools.common.csv_io import DUCKDB_NULLSTR, load_null_values_by_column, read_csv_explicit_nulls
from qa_tools.common import asset_time

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "warehouse.duckdb")
CONTRACT_PATH = os.path.join(os.path.dirname(__file__), "..", "contract", "bdm-birth-registrations-contract.yaml")

TABLE = "birth_registrations"

COLUMNS = [
    "registration_number", "child_given_names", "child_family_name",
    "date_of_birth", "sex", "place_of_birth_suburb", "place_of_birth_facility",
    "date_registered", "registering_parent_1_name", "registering_parent_2_name",
    "is_multiple_birth", "source_system_record_id", "extract_timestamp",
]


def load_all(db_path: str = DB_PATH, raw_dir: str = RAW_DIR) -> None:
    manifest_path = os.path.join(raw_dir, "manifest.json")
    with open(manifest_path) as f:
        manifest = json.load(f)

    if os.path.exists(db_path):
        os.remove(db_path)
    conn = duckdb.connect(db_path)

    null_values = load_null_values_by_column(CONTRACT_PATH).get(TABLE, {})
    frames = []
    for entry in manifest:
        path = os.path.join(raw_dir, entry["file"])
        df = read_csv_explicit_nulls(path, null_values)
        df["run_id"] = entry["run_id"]
        df["run_date"] = asset_time.local_date(entry["received_at"]).isoformat()
        df["dirty_severity"] = entry["dirty_severity"]
        frames.append(df)

    full = pd.concat(frames, ignore_index=True)
    # is_multiple_birth round-trips through CSV as True/False strings; store as 0/1
    full["is_multiple_birth"] = full["is_multiple_birth"].astype(str).map(
        {"True": 1, "False": 0, "true": 1, "false": 0}
    ).fillna(0).astype(int)

    # Registering a pandas dataframe straight into DuckDB couples this loader
    # to whichever arrow/pandas dtype backend happens to be installed (pandas
    # 3.x's default 'str' text dtype isn't one DuckDB 1.0's registration path
    # recognizes) - round-tripping through a plain CSV and DuckDB's own
    # read_csv_auto sidesteps that entirely, the same as loading a real daily
    # extract would.
    combined_csv = os.path.join(raw_dir, "_combined.csv")
    full.to_csv(combined_csv, index=False)
    conn.execute(
        f"CREATE OR REPLACE TABLE {TABLE} AS SELECT * FROM read_csv_auto(?, header=true, nullstr=?)",
        [combined_csv, DUCKDB_NULLSTR],
    )
    conn.execute(f"CREATE INDEX idx_{TABLE}_run ON {TABLE}(run_id)")
    os.remove(combined_csv)

    n = conn.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0]
    runs = conn.execute(f"SELECT COUNT(DISTINCT run_id) FROM {TABLE}").fetchone()[0]
    conn.close()
    print(f"Loaded {n} rows across {runs} runs into {db_path}")


if __name__ == "__main__":
    load_all()
