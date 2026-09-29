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
from qa_tools.common import period_schema, sample_data, supply_holds, trial
from qa_tools.common.csv_io import DUCKDB_NULLSTR, load_null_values_by_column, read_csv_explicit_nulls

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
CONTRACT_PATH = os.path.join(ROOT, "contract", "child-protection-contract.yaml")

# The six CP tables, in the order contract/data-asset.yaml declares
# them - resolved, not restated (REQ-QAC-039).
TABLES = [d.table for d in hierarchy.datasets_in_collection("child-protection")]


def _sample_and_agreed_tables() -> tuple[list[str], list[str]]:
    """This collection's tables, split by whether a schedule is agreed.

    Read from configuration on every call rather than computed once at
    import, because a dataset GRADUATES (criterion 16) by its
    configuration changing - and a module-level constant would hold the
    answer from whenever this process started.
    """
    sample, agreed = [], []
    for table in TABLES:
        dataset_id = hierarchy.dataset_for_table(table).dataset_id
        (sample if sample_data.is_sample(dataset_id) else agreed).append(table)
    return sample, agreed


def _build_run_views(conn, run_id: str, key: str, trial_scope) -> supply_db.Resolution:
    """The run's view schema, over one source schema or two.

    AGREED TABLES ARE SCOPED TO THIS ARRIVAL and sample tables are not,
    and the asymmetry is the point rather than an oversight. An agreed
    supply belongs to an arrival: this run is checking what arrived, and
    the read-the-newest rule for the tables it did NOT carry is the
    period's job, not this function's. Sample data has no arrival that
    matters - it sits in its own schema until a person discards it
    (criterion 18) - so the newest version of it is simply what a check
    developed against it should read, whichever run staged it.

    `period_schema.newest()` decides between versions rather than a
    `max()` here, for the reason its own docstring gives: a physical name
    orders by its arrival key and ordinal, never lexically.
    """
    sample_tables, agreed_tables = _sample_and_agreed_tables()
    staging = supply_db.staging_schema_for(run_id)
    # A HELD SUPPLY GETS NO VIEW (REQ-PIPE-078 criterion 9). The
    # ambiguity rule already withholds one where two files claim a
    # dataset; this extends the same refusal to a supply the assignment
    # rule could not place, which resolves to exactly one table and
    # would otherwise be checked against no period at all.
    res = supply_db.create_run_views(conn, run_id, supply_db.candidates_in(
        conn, staging, agreed_tables, arrival=key,
        loaded=load_log.loaded_tables(trial_scope)), source_schema=staging,
        held=supply_holds.held_tables(conn))
    if not sample_tables:
        return res
    # THE LOAD-RECORD GATE STILL APPLIES (REQ-PIPE-060 criterion 7).
    # Physical presence is not readability wherever the table sits, and a
    # truncated sample table is exactly as indistinguishable from a short
    # one as a truncated staged table is.
    found = supply_db.candidates_in(conn, sample_data.SCHEMA, sample_tables,
                                    loaded=load_log.loaded_tables(trial_scope))
    newest = {logical: [period_schema.newest(versions)]
              for logical, versions in found.items()
              if period_schema.newest(versions) is not None}
    return supply_db.add_run_views(conn, run_id, newest, sample_data.SCHEMA, res)


def add_table_to_run(run_id: str, table: str, csv_path: str, dsn: str | None = None,
                      contract_path: str = CONTRACT_PATH,
                      ordinal: int = 0, received_at=None, dataset_id: str = "",
                      delivery_name: str = "") -> str | None:
    """Stage exactly one CP table's CSV for that run, and rebuild the
    run's views. Returns the physical staged table, or None where the
    file could not be loaded at all.

    The single-arrival counterpart to build_all()'s per-delivery loop
    body, called once per arriving CP table file so a delivery fills in
    incrementally as each of the 6 real tables lands, in whatever order
    they actually arrive (see plans/running-thoughts.md #5 Thread B /
    docs/aws-event-driven-mvp-design.md). It only ever loads ONE table,
    and since REQ-PIPE-105 nothing anywhere decides completeness - there
    is no completion tracker to point at, because every arriving file is
    its own arrival and is checked against the newest supply staged for
    its period.

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

    NO SECOND COPY ANY MORE (REQ-PIPE-102, 2026-09-27). This used to
    copy csv_path into data/cp_raw/<run_id>/<table>.csv as well,
    because run_datacontract_cp.py and run_evidently_cp.py read CP's
    CSVs off disk rather than from the warehouse. REQ-QAC-088 pointed
    both at the warehouse and the reason went with it, leaving a third
    copy of every supply that nothing read and everything had to keep
    in step. Birth Registrations never had one.
    """
    arrival = received_at if received_at is not None else run_id
    physical = supply_db.staged_table(table, arrival, ordinal)
    # THE SAME SEGMENT staged_table() names the physical table with -
    # not arrival_key() directly. They disagreed for one commit and
    # the run built views over candidates that could never match.
    key = supply_db.arrival_segment(arrival)
    delivery_name = delivery_name or run_id
    dataset_id = dataset_id or table

    conn = supply_db.connect(dsn=dsn)
    try:
        supply_db.ensure_schemas(conn)
        # WHERE THIS RUN'S SUPPLIES GO. Shared `staging` for a real
        # arrival; a schema of the trial's own for a trial, so that
        # declining to keep a check leaves nothing among real supplies
        # even in principle (REQ-PIPE-103 criterion 6). Read from the
        # run id rather than passed in - see supply_db.is_trial_run().
        #
        # AND `sample` FOR A DATASET WITH NO AGREED CALENDAR
        # (REQ-PIPE-106 criterion 4). PER DATASET rather than per run,
        # which is the whole reason this collection needs the two-source
        # view build below: six datasets in one collection can legitimately
        # be a mix of agreed and still-being-developed-against, and a
        # cross-table check across them has to read both (criterion 14).
        staging = sample_data.ensure_schema_for_table(conn, run_id, table)
        trial_scope = trial.scope_for(run_id)
        rows = None
        try:
            df = read_csv_explicit_nulls(csv_path,
                                          load_null_values_by_column(contract_path).get(table, {}))
            # Our own scratch, for the reason supply_db.staging_csv()
            # gives: a temp file in a tree anything else reads back is
            # a stray artefact waiting to be reported as one.
            staging_csv = str(supply_db.staging_csv(physical))
            df.to_csv(staging_csv, index=False)
            try:
                # DuckDB reads the file and says what is in it;
                # PostgreSQL stores it (REQ-PIPE-087). The retired engine
                # did both in one CREATE TABLE AS, which is why this is
                # now a call rather than a statement - the inference and
                # the storage are two engines.
                supply_db.load_csv_into(
                    conn, staging, physical,
                    staging_csv, DUCKDB_NULLSTR)
            finally:
                os.remove(staging_csv)
            rows = len(df)
        except Exception as exc:  # noqa: BLE001 - every load failure is the same outcome
            # CASCADE, and this is a real behavioural difference rather
            # than a tidy-up: a run's view schema holds views over this
            # table, and PostgreSQL refuses to drop a table those depend
            # on where the retired engine allowed it
            # (DependentObjectsStillExist). Dropping the views with it is
            # correct - the table failed to load, so a view onto it
            # resolves to nothing anyone should read.
            conn.execute(f'DROP TABLE IF EXISTS "{staging}"."{physical}" CASCADE')
            load_log.record_load(delivery_name, dataset_id, physical, load_log.FAILED,
                             asset_time.now().isoformat(),
                             reason=f"{type(exc).__name__}: {exc}", trial=trial_scope)
            print(f"{run_id}: {table} FAILED to load ({type(exc).__name__}: {exc}) "
                  f"- no table staged, recorded for human action")
            return None
        # AFTER THE LOAD, NEVER BEFORE (criterion 14).
        load_log.record_load(delivery_name, dataset_id, physical, load_log.LOADED,
                         asset_time.now().isoformat(), row_count=rows, trial=trial_scope)
        res = _build_run_views(conn, run_id, key, trial_scope)
        # Recorded at staging time, which is the only moment this is an
        # observed fact rather than a re-derivation.
        supply_db.record_resolution(conn, res)
    finally:
        conn.close()
    print(f"{run_id}: {table} -> {staging}.{physical}")
    return physical


def build_all(dsn: str | None = None,
               deliveries_dir=None, receipts_dir=None) -> list[str]:
    """Stage every recognised arrival, from where it arrived."""
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
                        dsn=dsn,
                        ordinal=ordinal if len(filenames) > 1 else 0,
                        received_at=arrival.received_at, dataset_id=dataset_id,
                        delivery_name=arrival.delivery_name) is not None:
                    staged += 1
        run_ids.append(run_id)
        print(f"{run_id}: staged {staged} table(s)")

    return run_ids


if __name__ == "__main__":
    build_all()
