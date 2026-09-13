"""
Loads every generated run CSV in data/raw/ into one SQLite table,
birth_registrations, tagged with run_id/run_date - the "warehouse" that all
four check engines (contract, soda, dbt, drift) query against.

One table with a run_id column (rather than one table per run) is what lets
the drift engine compare across runs, and lets the "last 24h" scoped Soda
check (bdm-birth-registrations-soda-checks.yml's `filter ... [recent]`
block) filter on extract_timestamp within a single unified table, exactly
as it would against a real warehouse.

Booleans and dates come back from pandas.to_csv as plain strings, so they're
normalized on the way in (SQLite has no native boolean/date type; this
engine stores them as TEXT/INTEGER and each check engine parses what it
needs).
"""
from __future__ import annotations
import glob
import json
import os
import sqlite3

import pandas as pd

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "warehouse.db")

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
    conn = sqlite3.connect(db_path)

    frames = []
    for entry in manifest:
        path = os.path.join(raw_dir, entry["file"])
        df = pd.read_csv(path)
        df["run_id"] = entry["run_id"]
        df["run_date"] = entry["run_date"]
        df["dirty_severity"] = entry["dirty_severity"]
        frames.append(df)

    full = pd.concat(frames, ignore_index=True)
    # is_multiple_birth round-trips through CSV as True/False strings; store as 0/1
    full["is_multiple_birth"] = full["is_multiple_birth"].astype(str).map(
        {"True": 1, "False": 0, "true": 1, "false": 0}
    ).fillna(0).astype(int)

    full.to_sql(TABLE, conn, if_exists="replace", index=False)
    conn.execute(f"CREATE INDEX idx_{TABLE}_run ON {TABLE}(run_id)")
    conn.commit()

    n = conn.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0]
    runs = conn.execute(f"SELECT COUNT(DISTINCT run_id) FROM {TABLE}").fetchone()[0]
    conn.close()
    print(f"Loaded {n} rows across {runs} runs into {db_path}")


if __name__ == "__main__":
    load_all()
