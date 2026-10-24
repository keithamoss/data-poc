"""Stages any collection's arriving files into the one supply database, and
gives each run a schema of views to read them through (REQ-QAC-242,
REQ-PIPE-068).

WHY A RUN NEEDS ITS OWN VIEW OF THINGS AT ALL: a real dbt or Soda
invocation has no run-scoped `where` clause to filter by - README.md is
explicit that the schema.yml and checks files "don't need to change" to run
the real tools - so the only way to get a genuine per-run `dbt test` or
`soda scan` is to point the tool at something holding just that arrival's
rows. Nothing about the SQL models or the checks files changes; only what a
bare table name resolves to. See qa_tools/common/supply_db.py for the whole
of that reasoning, including why ambiguity is absence.

ONE PHYSICAL TABLE PER ARRIVAL, never an overwrite (REQ-PIPE-060 criterion
4): the physical name carries the arrival instant, so re-staging the same
arrival replaces that arrival rather than losing a previous one - which is
also criterion 15, because a table with no load record is unloaded whatever
the catalogue says.

BUILT FROM CHILD PROTECTION'S BUILDER, which had grown past Birth
Registrations': N tables a delivery, attributed by pattern (REQ-PIPE-058),
and a view build that reads a sample dataset's newest version from its own
schema (REQ-PIPE-106). Birth Registrations' one difference is kept behind its
legacy flag (qa_tools/tools/legacy.py) - never read from the collection's id.
"""
from __future__ import annotations

import functools
import os
import sys

from qa_tools import collections
from qa_tools.common import (
    arrivals, file_checks, hierarchy, load_log, replay_clock, sample_data,
    supply_db, supply_holds, trial,
)
from qa_tools.common.csv_io import DUCKDB_NULLSTR, load_null_values_by_column, read_csv_explicit_nulls

__all__ = ["build_all", "stage_arrival", "stage_table", "stager"]

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


def contract_for(collection_id: str) -> str:
    return os.path.join(ROOT, collections.by_id(collection_id).check_file("contract"))


def tables(collection_id: str) -> list[str]:
    """The collection's tables, in the order contract/data-asset.yaml
    declares them - resolved, not restated (REQ-QAC-039). Asked of the
    hierarchy on every call, never the registry's cached view of it: a
    dataset graduating out of sample data is a configuration change this
    process must see."""
    return [d.table for d in hierarchy.datasets_in_collection(collection_id)]


def _sample_and_agreed_tables(collection_id: str) -> tuple[list[str], list[str]]:
    """This collection's tables, split by whether a schedule is agreed.

    Read from configuration on every call rather than computed once at
    import, because a dataset GRADUATES (REQ-PIPE-106 criterion 16) by its
    configuration changing - and a module-level constant would hold the
    answer from whenever this process started.
    """
    sample, agreed = [], []
    for table in tables(collection_id):
        dataset_id = hierarchy.dataset_for_table(table).dataset_id
        (sample if sample_data.is_sample(dataset_id) else agreed).append(table)
    return sample, agreed


def _build_run_views(conn, collection_id: str, run_id: str, key: str,
                     trial_scope) -> supply_db.Resolution:
    """The run's view schema, over one source schema or two.

    AGREED TABLES ARE SCOPED TO THIS ARRIVAL and sample tables are not, and
    the asymmetry is the point rather than an oversight. An agreed supply
    belongs to an arrival: this run is checking what arrived, and the
    read-the-newest rule for the tables it did NOT carry is the period's
    job, not this function's. Sample data has no arrival that matters - it
    sits in its own schema until a person discards it (criterion 18) - so
    the newest version of it is simply what a check developed against it
    should read, whichever run staged it.

    `sample_data.newest()` decides between versions rather than a `max()`
    here, for the reason its own docstring gives: a physical name orders by
    its arrival key and ordinal, never lexically.
    """
    sample_tables, agreed_tables = _sample_and_agreed_tables(collection_id)
    staging = supply_db.staging_schema_for(run_id)
    # A HELD SUPPLY GETS NO VIEW (REQ-PIPE-078 criterion 9). The ambiguity
    # rule already withholds one where two files claim a dataset; this
    # extends the same refusal to a supply the assignment rule could not
    # place, which resolves to exactly one table and would otherwise be
    # checked against no period at all.
    res = supply_db.create_run_views(conn, run_id, supply_db.candidates_in(
        conn, staging, agreed_tables, arrival=key,
        loaded=load_log.loaded_tables(trial_scope)), source_schema=staging,
        held=supply_holds.held_supplies(conn, arrival_key=key))
    if not sample_tables:
        return res
    # THE LOAD-RECORD GATE STILL APPLIES (REQ-PIPE-060 criterion 7).
    # Physical presence is not readability wherever the table sits, and a
    # truncated sample table is exactly as indistinguishable from a short
    # one as a truncated staged table is.
    found = supply_db.candidates_in(conn, sample_data.SCHEMA, sample_tables,
                                    loaded=load_log.loaded_tables(trial_scope))
    newest = {logical: [sample_data.newest(versions)]
              for logical, versions in found.items()
              if sample_data.newest(versions) is not None}
    return supply_db.add_run_views(conn, run_id, newest, sample_data.SCHEMA, res)


def stage_table(collection_id: str, run_id: str, table: str, csv_path: str,
                dsn: str | None = None, *, contract_path: str | None = None,
                ordinal: int = 0, received_at=None, dataset_id: str = "",
                delivery_name: str = "") -> str | None:
    """Stage exactly one arriving file as one table of that run, and rebuild
    the run's views. Returns the physical staged table, or None where the
    file could not be loaded at all.

    Called once per arriving file, so a delivery fills in as each of its
    tables lands, in whatever order they actually arrive
    (docs/aws-event-driven-mvp-design.md). Since REQ-PIPE-105 nothing
    decides completeness: every arriving file is its own arrival, checked
    against the newest supply staged for its period.

    `received_at` IS OUR OWN RECEIPT INSTANT and nothing else (criterion
    11) - never a timestamp inside the supplier's file, never a column in
    their data, never the file's mtime. It names the staged table. Callers
    that genuinely have no receipt (the single-run test path) may leave it
    out, and the run id stands in.

    THE RUN'S VIEWS ARE REBUILT on every call, and built HERE, serially,
    rather than by the tools that read them: a run is readable only for the
    tables that have actually landed, and a table with no staged arrival is
    absent rather than empty - the distinction that stops a check passing
    over nothing. By the time anything reads, the writing is done
    (criterion 9).

    A FILE THAT CANNOT BE LOADED LEAVES NO TABLE (criterion 5) and does not
    raise: it writes a FAILED load record and returns None, so every other
    file in the same delivery is still staged (criterion 6). The failure is
    durable, and `mothman supply failures` is the queue it lands in.

    THE ROWS AS DELIVERED, never stamped (REQ-PIPE-248): a staged table is
    one arrival's, so the run's view says which run a row is in, and no
    column needs to.
    """
    collections.by_id(collection_id)  # refuses an unknown collection by name
    contract_path = contract_path or contract_for(collection_id)
    arrival = received_at if received_at is not None else run_id
    # A REPLAY STAMPS THE LOAD AS RECEIVED (REQ-PIPE-081 criteria 27-31).
    if received_at is not None:
        replay_clock.anchor(received_at)
    physical = supply_db.staged_table(table, arrival, ordinal)
    # THE SAME SEGMENT staged_table() names the physical table with - not
    # arrival_key() directly. They disagreed for one commit and the run
    # built views over candidates that could never match.
    key = supply_db.arrival_segment(arrival)
    delivery_name = delivery_name or run_id
    # THE DATASET, NEVER THE TABLE NAME in its place - a load record filed
    # under 'cp_carers' belongs to no dataset, so no failed-load blocker
    # keyed on 'cp-carers' ever saw it (found with REQ-QAC-096).
    dataset_id = dataset_id or hierarchy.dataset_for_table(table).dataset_id

    conn = supply_db.connect(dsn=dsn)
    try:
        supply_db.ensure_schemas(conn)
        # WHERE THIS RUN'S SUPPLIES GO. Shared `staging` for a real arrival;
        # a schema of the trial's own for a trial, so that declining to keep
        # a check leaves nothing among real supplies even in principle
        # (REQ-PIPE-103 criterion 6). Read from the run id rather than
        # passed in - see supply_db.is_trial_run().
        #
        # AND `sample` FOR A DATASET WITH NO AGREED CALENDAR (REQ-PIPE-106
        # criterion 4). PER DATASET rather than per run, which is why the
        # view build reads two sources: datasets in one collection can be a
        # mix of agreed and still-being-developed-against, and a cross-table
        # check across them has to read both (criterion 14).
        staging = sample_data.ensure_schema_for_table(conn, run_id, table)
        trial_scope = trial.scope_for(run_id)
        # FILE CHECKS FIRST, on the bytes as delivered (REQ-QAC-096), and
        # outside the catch-all below so an evaluator bug fails the run
        # rather than reading as a fault in the supplier's file.
        screening = file_checks.screen(
            conn, csv_path, contract_path=contract_path, table=table, run_id=run_id,
            dataset_id=dataset_id, delivery=delivery_name, staging=staging,
            physical=physical, trial_scope=trial_scope)
        if screening.refused is not None:
            return None
        rows = None
        try:
            df = read_csv_explicit_nulls(
                csv_path, load_null_values_by_column(contract_path).get(table, {}))
            # Handed over as a real staging CSV rather than through the
            # dataframe, so the explicit-null handling csv_io owns stays the
            # one place that decides what an empty cell means. IN OUR OWN
            # SCRATCH, never beside the source file - that directory is the
            # supplier's delivery.
            staging_csv = str(supply_db.staging_csv(physical))
            df.to_csv(staging_csv, index=False)
            try:
                # DuckDB reads the file and says what is in it; PostgreSQL
                # stores it (REQ-PIPE-087).
                supply_db.load_csv_into(conn, staging, physical, staging_csv, DUCKDB_NULLSTR)
            finally:
                os.remove(staging_csv)
            rows = len(df)
        except Exception as exc:  # noqa: BLE001 - every load failure is the same outcome
            # NO TABLE AT ALL rather than a truncated one (criterion 5).
            # CASCADE, because a run's view schema holds views over this
            # table and PostgreSQL refuses to drop a table those depend on
            # (DependentObjectsStillExist). Dropping the views with it is
            # correct - a view onto a table that failed to load resolves to
            # nothing anyone should read.
            conn.execute(f'DROP TABLE IF EXISTS "{staging}"."{physical}" CASCADE')
            screening.record_against(load_log.record_load(
                delivery_name, dataset_id, physical, load_log.FAILED,
                replay_clock.now().isoformat(), reason=load_log.own_words(exc),
                trial=trial_scope), conn=conn)
            # THE LIBRARY'S OWN MESSAGE ONLY HERE, on standard error, for
            # whoever ran the load - it can quote a row, and the recorded
            # reason is published (REQ-DASH-148 criterion 13).
            print(f"{run_id}: {table} could not be loaded ({type(exc).__name__}: {exc}) "
                  f"- no table staged, recorded for human action", file=sys.stderr)
            return None
        # AFTER THE LOAD, NEVER BEFORE (criterion 14). A crash between these
        # two lines re-loads a table that was already fine; the other order
        # skips one that never loaded.
        screening.record_against(load_log.record_load(
            delivery_name, dataset_id, physical, load_log.LOADED,
            replay_clock.now().isoformat(), row_count=rows, trial=trial_scope), conn=conn)
        res = _build_run_views(conn, collection_id, run_id, key, trial_scope)
        # Recorded at staging time, which is the only moment this is an
        # observed fact rather than a re-derivation.
        supply_db.record_resolution(conn, res)
    finally:
        conn.close()
    print(f"{run_id}: {table}: {rows} rows -> {staging}.{physical}")
    return physical


def stage_arrival(collection_id: str, arrival, dsn: str | None = None) -> list[str]:
    """Stage ONE recognised arrival - build_all()'s loop body, shared with the
    processing pass (REQ-PIPE-151), which stages only the arrivals it is
    about to process. Returns the physical tables staged."""
    staged = []
    # WHAT IS IN THIS DELIVERY, not what we assumed would be (REQ-PIPE-058):
    # a supplier renaming an extract is a configuration change, and a
    # delivery missing a file simply does not stage that dataset.
    for dataset_id, filenames in sorted(arrival.files_by_dataset.items()):
        table = hierarchy.dataset(dataset_id).table
        for ordinal, filename in enumerate(sorted(filenames), start=1):
            # EVERY FILE THAT MATCHED IS STAGED, including both halves of a
            # held supply (REQ-PIPE-059): the material to resolve the hold
            # with has to be there. They get distinct physical names, and no
            # view resolves the logical one - REQ-PIPE-068 refuses to choose
            # between candidates - so nothing can read it.
            # AN ORDINAL, NOT THE FILENAME - a supplier's filename must never
            # reach a SQL identifier, and the ordinal is ours. One file needs
            # no suffix at all, which keeps the ordinary name readable.
            physical = stage_table(
                collection_id, arrival.run_id, table,
                os.path.join(str(arrival.path), filename), dsn=dsn,
                ordinal=ordinal if len(filenames) > 1 else 0,
                received_at=arrival.received_at, dataset_id=dataset_id,
                delivery_name=arrival.delivery_name)
            if physical is not None:
                staged.append(physical)
    print(f"{arrival.run_id}: staged {len(staged)} table(s)")
    return staged


def stager(collection_id: str):
    """stage_arrival() for one collection, as a one-argument callable - what
    arrival_lifecycle.staged_as_it_arrives() is handed."""
    return functools.partial(stage_arrival, collection_id)


def build_all(collection_id: str, dsn: str | None = None,
              deliveries_dir=None, receipts_dir=None) -> list[str]:
    """Stage every recognised arrival of one collection, from where it
    arrived (REQ-GEN-043). `deliveries_dir`/`receipts_dir` are the one way to
    redirect this - there is no `raw_dir`, which a test once passed and got
    the whole real delivery tree staged instead (2026-09-27)."""
    coll = collections.by_id(collection_id)
    staged = []
    for arrival in arrivals.arrivals_for(coll.id, coll.run_prefix, deliveries_dir, receipts_dir):
        staged.extend(stage_arrival(coll.id, arrival, dsn=dsn))
    return staged
