"""Staging asserts only arrival facts, and a table is there or it is
not (REQ-PIPE-060) - the loaders' own half.

Against a REAL DuckDB database and REAL CSVs in tmp_path. The claims
here are about what survives a failure and what a name carries, and
both are properties of the real load rather than of the call.
"""
from __future__ import annotations

import csv

import psycopg
import pytest

import dbsupport

from qa_tools.bdm import build_per_run_warehouses as bdm
from qa_tools.common import load_log, supply_db

_RECEIPT = "2026-09-25T09:00:00+08:00"
_LATER = "2026-11-01T09:00:00+08:00"


@pytest.fixture
def staging(tmp_path, monkeypatch):
    # An EMPTY database on this worker's PostgreSQL, which is what a
    # fresh file used to give (REQ-TEST-095).
    dbsupport.reset_supply_db()
    return tmp_path


def _csv(path, rows=2):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["registration_id", "child_family_name"])
        for i in range(rows):
            writer.writerow([f"BR{i:04d}", "SMITH"])
    return str(path)


def _tables(schema=supply_db.STAGING_SCHEMA):
    conn = supply_db.connect(read_only=True)
    try:
        # supply_db keeps its own bookkeeping table in this schema;
        # the question here is which SUPPLIES are staged.
        return sorted(r[0] for r in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = ?",
            [schema]).fetchall() if not r[0].startswith("_"))
    finally:
        conn.close()


class TestTheNameCarriesTheArrival:
    """Criterion 4."""

    def test_a_resupply_does_not_overwrite_the_earlier_arrival(self, staging):
        log_dir = staging / "processing_log"
        first = bdm.build_one("run_001", _csv(staging / "a.csv", 2), "2026-09-25",
                               received_at=_RECEIPT, log_dir=log_dir)
        second = bdm.build_one("run_002", _csv(staging / "b.csv", 5), "2026-11-01",
                                received_at=_LATER, log_dir=log_dir)
        assert first != second
        assert _tables() == sorted([first, second]), (
            "a resupply must be a NEW table - the cheapest implementation, CREATE OR "
            "REPLACE on a shared name, keeps one version and destroys the history the "
            "read-the-newest rule exists for")
        conn = supply_db.connect(read_only=True)
        try:
            assert conn.execute(
                f'SELECT count(*) FROM "{supply_db.STAGING_SCHEMA}"."{first}"').fetchone()[0] == 2
        finally:
            conn.close()

    def test_the_name_is_the_receipt_instant_not_the_file(self, staging):
        """Criterion 11. The instant in the name is ours, so a supplier
        cannot move a supply in time by touching a file or writing a
        column."""
        physical = bdm.build_one("run_001", _csv(staging / "a.csv"), "2026-09-25",
                                  received_at=_RECEIPT,
                                  log_dir=staging / "processing_log")
        assert physical.endswith("__" + supply_db.arrival_key(_RECEIPT))

    def test_restaging_the_same_arrival_replaces_it_rather_than_adding(self, staging):
        """Criterion 15, and it is what makes an interrupted run
        resumable: what is already there is not trusted."""
        log_dir = staging / "processing_log"
        first = bdm.build_one("run_001", _csv(staging / "a.csv", 2), "2026-09-25",
                               received_at=_RECEIPT, log_dir=log_dir)
        again = bdm.build_one("run_001", _csv(staging / "a.csv", 7), "2026-09-25",
                               received_at=_RECEIPT, log_dir=log_dir)
        assert first == again and _tables() == [first]
        conn = supply_db.connect(read_only=True)
        try:
            assert conn.execute(
                f'SELECT count(*) FROM "{supply_db.STAGING_SCHEMA}"."{first}"').fetchone()[0] == 7
        finally:
            conn.close()


class TestAFileThatCannotBeLoaded:
    """Criteria 5 and 6."""

    def test_it_leaves_no_table_and_records_why(self, staging):
        log_dir = staging / "processing_log"
        physical = bdm.build_one("run_001", str(staging / "not-here.csv"), "2026-09-25",
                                  received_at=_RECEIPT, delivery_name="drop-1",
                                  log_dir=log_dir)
        assert physical is None
        assert _tables() == [], "a file that could not be loaded must leave NO table"
        failed = load_log.failures(log_dir)
        assert [(r.delivery, r.dataset_id) for r in failed] == [("drop-1", "birth-registrations")]
        assert failed[0].reason, "the reason a load failed is the whole value of the record"
        assert load_log.loaded_tables(log_dir) == frozenset()

    def test_the_rest_of_the_delivery_still_stages(self, staging):
        log_dir = staging / "processing_log"
        bdm.build_one("run_001", str(staging / "not-here.csv"), "2026-09-25",
                       received_at=_RECEIPT, delivery_name="drop-1", log_dir=log_dir)
        good = bdm.build_one("run_002", _csv(staging / "b.csv"), "2026-11-01",
                              received_at=_LATER, delivery_name="drop-1", log_dir=log_dir)
        assert good is not None and _tables() == [good]
        assert load_log.loaded_tables(log_dir) == frozenset({good})

    def test_a_failed_load_writes_no_loaded_record(self, staging):
        """Criterion 14 from the other side: nothing may claim a load
        that did not happen, which is the half that fails silently."""
        log_dir = staging / "processing_log"
        bdm.build_one("run_001", str(staging / "not-here.csv"), "2026-09-25",
                       received_at=_RECEIPT, log_dir=log_dir)
        assert all(not r.loaded for r in load_log.records(log_dir))

    def test_a_truncated_table_from_an_earlier_attempt_is_not_left_readable(self, staging):
        """The failure this whole mechanism exists for. A previous run
        left a table behind with no record; the load then fails. What
        must not happen is the stale table being readable as this
        arrival's supply."""
        log_dir = staging / "processing_log"
        physical = supply_db.staged_table(bdm.TABLE, _RECEIPT)
        conn = supply_db.connect()
        try:
            supply_db.ensure_schemas(conn)
            conn.execute(f'CREATE TABLE "{supply_db.STAGING_SCHEMA}"."{physical}" AS '
                         "SELECT 'BR0000' AS registration_id")
        finally:
            conn.close()

        assert bdm.build_one("run_001", str(staging / "not-here.csv"), "2026-09-25",
                              received_at=_RECEIPT, log_dir=log_dir) is None
        assert _tables() == [], "the stale table must go, not be left for a check to read"


class TestOnlyLoadedTablesAreReadable:
    """Criterion 7, at the layer a check actually reads."""

    def test_a_check_reads_the_run_view_only_where_a_record_exists(self, staging):
        log_dir = staging / "processing_log"
        physical = bdm.build_one("run_001", _csv(staging / "a.csv", 3), "2026-09-25",
                                  received_at=_RECEIPT, log_dir=log_dir)
        schema = supply_db.run_schema("run_001")
        conn = supply_db.connect(read_only=True)
        try:
            assert conn.execute(
                f'SELECT count(*) FROM "{schema}"."{bdm.TABLE}"').fetchone()[0] == 3
        finally:
            conn.close()

        # Lose the record, keep the table - an interrupted load, exactly.
        for path in log_dir.glob("*.json"):
            path.unlink()
        conn = supply_db.connect()
        try:
            res = supply_db.create_run_views(conn, "run_001", supply_db.candidates_in(
                conn, supply_db.STAGING_SCHEMA, [bdm.TABLE],
                arrival=supply_db.arrival_key(_RECEIPT),
                loaded=load_log.loaded_tables(log_dir)))
            assert res.resolved == {} and res.absent == [bdm.TABLE]
            with pytest.raises(psycopg.errors.UndefinedTable):
                conn.execute(f'SELECT * FROM "{res.schema}"."{bdm.TABLE}"')
        finally:
            conn.close()
        assert physical in _tables(), (
            "the TABLE is still there - readability is the record's job, not the "
            "catalogue's, which is the distinction the whole mechanism rests on")


class TestStagingIsSequential:
    """Criterion 9, and the NFR it comes from."""

    def test_build_all_stages_without_fanning_out(self):
        """One DuckDB file takes one writer, so a staging fan-out would
        have workers of a single invocation collide on its lock. This
        asserts the source rather than a timing, because the failure is
        a lock error under load rather than a slow test."""
        import inspect
        for module in (bdm, __import__("qa_tools.cp.build_cp_warehouses",
                                        fromlist=["build_all"])):
            source = inspect.getsource(module)
            for banned in ("ProcessPoolExecutor", "ThreadPoolExecutor", "multiprocessing"):
                assert banned not in source, (
                    f"{module.__name__} stages in parallel via {banned} - one DuckDB file "
                    f"takes one writer, and staging must be serial")


    def test_staging_happens_before_the_tools_fan_out(self):
        """Criterion 1, and criterion 9's second half. The tools run
        over a process pool; staging must be finished before the first
        worker starts, because building a view is a write and DuckDB
        gives a writer an exclusive lock."""
        import inspect

        from qa_tools.bdm import orchestrate_bdm
        from qa_tools.cp import orchestrate_cp

        for module, first in ((orchestrate_bdm, "build_per_run_warehouses.build_all()"),
                               (orchestrate_cp, "build_cp_warehouses.build_all()")):
            source = inspect.getsource(module)
            assert first in source, f"{module.__name__} no longer stages at all"
            fanout = source.find("ProcessPoolExecutor")
            if fanout == -1:
                continue
            assert source.find(first) < fanout, (
                f"{module.__name__} stages AFTER it fans out - two workers would then "
                f"collide on the one supply database's writer lock")

    def test_one_collection_is_staged_at_a_time(self):
        """Both orchestrators stage into the same file, so the command
        that runs both must not run them at once."""
        import inspect

        from cli import pipeline
        # run_command is wrapped by click, so read the module rather
        # than the command object.
        source = inspect.getsource(pipeline)
        source = source[source.index("def run_command("):]
        assert source.index("_run_bdm(sequential)") < source.index("_run_cp(sequential)")
        for banned in ("ProcessPoolExecutor", "ThreadPoolExecutor"):
            assert banned not in source, (
                f"mothman pipeline run drives both collections via {banned} - they stage "
                f"into ONE database file, which takes one writer")


class TestNothingIsWrittenIntoTheDelivery:
    """A delivery is a supplier-owned tree this pipeline treats as
    immutable, and the loader used to write its staging CSV beside the
    source file - which IS that tree.

    Found live rather than by review: one leaked through a crash and
    turned up on the next run as an 'unrecognised artefact' warning
    naming our own temporary file.
    """

    def test_the_delivery_directory_is_untouched_by_a_load(self, staging):
        drop = staging / "delivery"
        source = _csv(drop / "birth_registrations_2026-09-25.csv", 3)
        before = sorted(p.name for p in drop.iterdir())

        physical = bdm.build_one("run_001", source, "2026-09-25",
                                  received_at=_RECEIPT,
                                  log_dir=staging / "processing_log")
        assert physical is not None
        after = sorted(p.name for p in drop.iterdir())
        assert after == before, (
            f"the load left {sorted(set(after) - set(before))} in the delivery - a supplier's "
            f"directory is read, never written, and a stray file there is reported as an "
            f"unrecognised artefact on every later run")

    def test_a_failed_load_leaves_nothing_behind_either(self, staging):
        drop = staging / "delivery"
        drop.mkdir(parents=True, exist_ok=True)
        before = sorted(p.name for p in drop.iterdir())
        assert bdm.build_one("run_001", str(drop / "missing.csv"), "2026-09-25",
                              received_at=_RECEIPT,
                              log_dir=staging / "processing_log") is None
        assert sorted(p.name for p in drop.iterdir()) == before
