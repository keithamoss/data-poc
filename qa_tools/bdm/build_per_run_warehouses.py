"""
Stages one run's Birth Registrations rows into the one supply database
and gives that run a schema of views to read them through
(REQ-PIPE-068).

WHY A RUN NEEDS ITS OWN VIEW OF THINGS AT ALL, which is the part that
has not changed: a real dbt or Soda invocation has no run-scoped `where`
clause to filter by - README.md is explicit that the schema.yml and
checks.yml files "don't need to change" to run the real tools - so the
only way to get a genuine per-run `dbt test` or `soda scan`, matching
this dataset's production reality of one daily extract landed and tested
at a time, is to point the tool at something containing just that one
day's rows. Nothing about the SQL model or the checks files changes;
only what a bare table name resolves to.

WHAT CHANGED is where that something lives. Until 2026-09-25 each run
built its own DuckDB FILE under data/duckdb_runs/<run_id>.duckdb and the
tools connected to the file. A supply, though, arrives, is staged, is
assigned to a slot and is later promoted, and none of that survives in a
file that exists for the length of one run - so the rows now land in the
staging schema of one durable database, as one physical table per
arrival, and the run reads them through views. See
qa_tools/common/supply_db.py for the whole of that reasoning, including
why ambiguity is absence and why dbt is the one tool that still gets a
scratch file.
"""
from __future__ import annotations
import os

from qa_tools.common.csv_io import DUCKDB_NULLSTR, load_null_values_by_column, read_csv_explicit_nulls
from qa_tools.common import arrivals, asset_time, supply_db

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
RAW_DIR = os.path.join(ROOT, "data", "raw")
CONTRACT_PATH = os.path.join(ROOT, "contract", "bdm-birth-registrations-contract.yaml")

#: The one logical table this dataset supplies.
TABLE = "birth_registrations"


def build_one(run_id: str, csv_path: str, run_date: str, db_path: str | None = None,
              contract_path: str = CONTRACT_PATH, discriminator: str = "") -> str:
    """Stage one already-on-disk CSV as this run's supply, and give the
    run a view of it. Returns the physical staged table's name.

    The single-arrival counterpart to build_all()'s loop body, factored
    out so a Lambda handler processing one arriving file needs no
    manifest at all (plans/running-thoughts.md #5 Thread B,
    docs/aws-event-driven-mvp-design.md).

    ONE PHYSICAL TABLE PER ARRIVAL, never an overwrite. What this
    replaced was `CREATE OR REPLACE TABLE raw.birth_registrations` in a
    file of its own, which is the cheapest implementation and the wrong
    one - it keeps exactly one version and so destroys the history a
    read-the-newest rule exists for (REQ-PIPE-060's own decision, and
    it matches Keith's real operational database).

    THE VIEWS ARE BUILT HERE, serially, and not by the tools that read
    them. Creating a view is a write, DuckDB gives a writer an
    exclusive lock, and the tools fan out over a process pool - so a
    tool that built its own view would lock out every other worker. By
    the time anything reads, the writing is done.
    """
    null_values = load_null_values_by_column(contract_path).get(TABLE, {})

    df = read_csv_explicit_nulls(csv_path, null_values)
    df["run_id"] = run_id
    df["run_date"] = run_date

    physical = supply_db.staged_table(TABLE, run_id, discriminator)
    conn = supply_db.connect(path=db_path)
    try:
        supply_db.ensure_schemas(conn)
        # Handed to DuckDB as a real staging CSV rather than through the
        # dataframe, so the explicit-null handling csv_io owns stays the
        # one place that decides what an empty cell means.
        staging_csv = os.path.join(os.path.dirname(csv_path), f"_staged_{physical}.csv")
        df.to_csv(staging_csv, index=False)
        try:
            conn.execute(
                f'CREATE OR REPLACE TABLE "{supply_db.STAGING_SCHEMA}"."{physical}" AS '
                "SELECT * FROM read_csv_auto(?, header=true, nullstr=?)",
                [staging_csv, DUCKDB_NULLSTR])
        finally:
            os.remove(staging_csv)
        # CREATE OR REPLACE on the PHYSICAL name above is not the
        # overwrite this design forbids: the name carries the arrival,
        # so replacing it re-loads the same arrival rather than losing a
        # previous one. That is what makes a re-run idempotent.
        res = supply_db.create_run_views(conn, run_id, supply_db.candidates_in(
            conn, supply_db.STAGING_SCHEMA, [TABLE], run_id=run_id))
        # Recorded at staging time, which is the only moment this is an
        # observed fact rather than a re-derivation (criterion 5).
        supply_db.record_resolution(conn, res)
    finally:
        conn.close()

    print(f"{run_id}: {len(df)} rows -> {supply_db.STAGING_SCHEMA}.{physical}")
    return physical


def build_all(raw_dir: str = RAW_DIR, db_path: str | None = None,
               deliveries_dir=None, receipts_dir=None) -> list[str]:
    """Stage every recognised arrival.

    `raw_dir` is kept for callers that still pass it and is no longer
    read: since REQ-GEN-043 the runs come from deliveries on disk, not
    from a manifest in a raw directory.
    """
    staged = []
    for arrival in arrivals.arrivals_for("civil-registration", "run_",
                                          deliveries_dir, receipts_dir):
        run_date = asset_time.local_date(arrival.received_at).isoformat()
        names = arrival.files_by_dataset.get("birth-registrations") or ()
        # EVERY FILE THAT MATCHED IS STAGED, both halves of a held
        # supply included (REQ-PIPE-059) - the material to resolve the
        # hold with has to be there. They get distinct physical names
        # and no view resolves the logical one, so nothing can read it.
        for filename in names:
            staged.append(build_one(
                arrival.run_id, str(arrival.path / filename), run_date,
                db_path=db_path,
                discriminator=filename if len(names) > 1 else ""))
    return staged


if __name__ == "__main__":
    build_all()
