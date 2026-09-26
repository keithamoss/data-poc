"""Taking an empty environment to a populated one, idempotently.

The point of these is the SKIP path rather than the populate path. A
startup hook that rebuilds the world every time is a hook people
disable, so "found data, did nothing, said so" is the behaviour that
has to hold - and it has to be decided by asking the database, not by
trusting a marker file that can outlive the database it describes.

The populate path itself is deliberately NOT exercised end to end here:
it runs the whole real pipeline over both collections, which the suite
already covers at length and which would put minutes into this module
for nothing new. What is checked is that it calls the real orchestrators
with what it was given.
"""
from __future__ import annotations

import dbsupport
import pytest

from qa_tools.common import bootstrap as boot
from qa_tools.common import supply_db


@pytest.fixture
def empty_db(monkeypatch):
    """A database of this test's own - see tests/dbsupport.py for why
    each such test gets a whole database rather than a cleared one."""
    dbsupport.use_empty_supply_db(monkeypatch)
    with supply_db.connect(label="test") as conn:
        supply_db.ensure_schemas(conn)
        yield conn


class TestWhetherThereIsAnythingHere:
    def test_a_fresh_environment_reads_as_empty(self, empty_db):
        assert boot.staged_table_count(empty_db) == 0
        assert not boot.already_populated(empty_db)

    def test_a_staged_table_makes_it_populated(self, empty_db):
        empty_db.execute(
            f'CREATE TABLE "{supply_db.STAGING_SCHEMA}".t__20260101000000 (id int)')
        assert boot.staged_table_count(empty_db) == 1
        assert boot.already_populated(empty_db)

    def test_it_asks_the_database_rather_than_a_marker(self, empty_db):
        """The reason this is not a marker file: a marker survives a
        database being dropped, and then the one command whose job is to
        guarantee data is the one confidently doing nothing."""
        empty_db.execute(
            f'CREATE TABLE "{supply_db.STAGING_SCHEMA}".t__20260101000000 (id int)')
        assert boot.already_populated(empty_db)
        empty_db.execute(f'DROP TABLE "{supply_db.STAGING_SCHEMA}".t__20260101000000')
        assert not boot.already_populated(empty_db)

    def test_a_table_in_another_schema_does_not_count(self, empty_db):
        """Only STAGING says a supply has arrived. dbt's own schema
        holds models, which exist whether or not anything was supplied."""
        empty_db.execute(f'CREATE SCHEMA IF NOT EXISTS "{supply_db.DBT_SCHEMA}"')
        empty_db.execute(f'CREATE TABLE "{supply_db.DBT_SCHEMA}".some_model (id int)')
        assert not boot.already_populated(empty_db)


class TestItDoesNotRebuildWhatIsAlreadyThere:
    def test_it_skips_and_explains_when_data_is_present(self, empty_db, monkeypatch):
        empty_db.execute(
            f'CREATE TABLE "{supply_db.STAGING_SCHEMA}".t__20260101000000 (id int)')

        def _fail(*a, **k):
            raise AssertionError("bootstrap ran the pipeline against a populated database")
        monkeypatch.setattr("qa_tools.bdm.orchestrate_bdm.run_pipeline", _fail)
        monkeypatch.setattr("qa_tools.cp.orchestrate_cp.run_pipeline_cp", _fail)

        result = boot.bootstrap()
        assert result.populated is False
        assert result.staged_before == 1
        assert "already present" in result.reason
        assert "--force" in result.reason, \
            "a skip has to say how to override it, or the next person re-runs it by hand"

    def test_force_rebuilds_anyway(self, empty_db, monkeypatch):
        empty_db.execute(
            f'CREATE TABLE "{supply_db.STAGING_SCHEMA}".t__20260101000000 (id int)')
        called = []
        monkeypatch.setattr("cli.bdm.generate_synthetic_data", lambda: called.append("gen-bdm"))
        monkeypatch.setattr("cli.cp.generate_synthetic_data", lambda: called.append("gen-cp"))
        monkeypatch.setattr("qa_tools.bdm.orchestrate_bdm.run_pipeline",
                            lambda **k: called.append(("bdm", k)))
        monkeypatch.setattr("qa_tools.cp.orchestrate_cp.run_pipeline_cp",
                            lambda **k: called.append(("cp", k)))

        result = boot.bootstrap(force=True)
        assert result.populated is True
        assert ("bdm", {"sequential": False}) in called
        assert ("cp", {"sequential": False}) in called


class TestWhatItRuns:
    @pytest.fixture
    def spy(self, empty_db, monkeypatch):
        called = []
        monkeypatch.setattr("cli.bdm.generate_synthetic_data", lambda: called.append("gen-bdm"))
        monkeypatch.setattr("cli.cp.generate_synthetic_data", lambda: called.append("gen-cp"))
        monkeypatch.setattr("qa_tools.bdm.orchestrate_bdm.run_pipeline",
                            lambda **k: called.append("bdm"))
        monkeypatch.setattr("qa_tools.cp.orchestrate_cp.run_pipeline_cp",
                            lambda **k: called.append("cp"))
        return called

    def test_all_does_both_collections(self, spy):
        boot.bootstrap(collection="all")
        assert spy == ["gen-bdm", "bdm", "gen-cp", "cp"]

    def test_one_collection_leaves_the_other_alone(self, spy):
        boot.bootstrap(collection="bdm")
        assert spy == ["gen-bdm", "bdm"]

    def test_it_generates_before_checking(self, spy):
        """Order matters and is easy to get backwards: checks over data
        that has not been generated yet find nothing and report a clean
        bill of health."""
        boot.bootstrap(collection="cp")
        assert spy.index("gen-cp") < spy.index("cp")

    def test_progress_is_reported_rather_than_silent(self, spy):
        """A command that takes minutes and prints nothing reads as
        hung, and the first thing a newcomer does is kill it."""
        steps = []
        boot.bootstrap(collection="bdm", on_step=steps.append)
        assert len(steps) >= 3
        assert any("Generating" in s for s in steps)

    def test_it_works_with_no_progress_callback(self, spy):
        boot.bootstrap(collection="bdm")
