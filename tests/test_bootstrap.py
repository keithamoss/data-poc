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
        dbt = supply_db.dbt_schema("run_001")
        empty_db.execute(f'CREATE SCHEMA IF NOT EXISTS "{dbt}"')
        empty_db.execute(f'CREATE TABLE "{dbt}".some_model (id int)')
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
        _in_process(monkeypatch)

        result = boot.bootstrap(force=True)
        assert result.populated is True
        assert ("bdm", {"sequential": False, "record_deliveries": False}) in called
        assert ("cp", {"sequential": False, "record_deliveries": False}) in called


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
        monkeypatch.setattr(boot, "_record_deliveries", lambda: called.append("record"))
        _in_process(monkeypatch, called)
        return called

    def test_all_does_both_collections(self, spy):
        boot.bootstrap(collection="all")
        # Each collection records a delivery at its first arrival; the ones
        # neither claimed are recorded once both finish (REQ-TEST-159).
        assert spy == ["gen-bdm", "gen-cp", "concurrently", "bdm", "cp", "record"]

    def test_sequential_does_one_collection_then_the_other(self, spy):
        """REQ-TEST-116 criterion 5 - the reference a parallel bootstrap
        is compared against, so it has to be the old behaviour exactly."""
        boot.bootstrap(collection="all", sequential=True)
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


def _in_process(monkeypatch, called=None):
    """Stand in for the process pool: a monkeypatched orchestrator does
    not exist in a spawned process, so the dispatch runs here instead.
    What is under test is WHAT is dispatched and in what order around it;
    that two processes really run side by side is the pool's own job."""
    def run(names, sequential):
        if called is not None:
            called.append("concurrently")
        return {n: boot._run_collection(n, sequential) for n in names}
    monkeypatch.setattr(boot, "_run_concurrently", run)


class TestCollectionsRunSideBySide:
    """REQ-TEST-116 criteria 1, 2 and 6."""

    @pytest.fixture
    def spy(self, empty_db, monkeypatch):
        called = []
        monkeypatch.setattr("cli.bdm.generate_synthetic_data", lambda: called.append("gen-bdm"))
        monkeypatch.setattr("cli.cp.generate_synthetic_data", lambda: called.append("gen-cp"))
        monkeypatch.setattr("qa_tools.bdm.orchestrate_bdm.run_pipeline",
                            lambda **k: called.append(("bdm", k)))
        monkeypatch.setattr("qa_tools.cp.orchestrate_cp.run_pipeline_cp",
                            lambda **k: called.append(("cp", k)))
        monkeypatch.setattr(boot, "_record_deliveries", lambda: called.append("record"))
        dispatched = []

        def run(names, sequential):
            dispatched.append(list(names))
            return {n: boot._run_collection(n, sequential) for n in names}
        monkeypatch.setattr(boot, "_run_concurrently", run)
        return called, dispatched

    def test_both_collections_are_dispatched_together(self, spy):
        _called, dispatched = spy
        boot.bootstrap(collection="all")
        assert dispatched == [["bdm", "cp"]]

    def test_the_unclaimed_deliveries_are_recorded_once_after_both_run(self, spy):
        """REQ-TEST-159 reversed REQ-TEST-116's record-everything-first: each
        collection records a delivery at its first arrival (one transaction,
        ON CONFLICT DO NOTHING, so two collections sharing one is not a
        race), and the deliveries NEITHER claims are recorded once, after
        both have finished - not by either child."""
        called, _ = spy
        boot.bootstrap(collection="all")
        assert called.count("record") == 1
        assert called.index("record") > max(
            i for i, c in enumerate(called) if isinstance(c, tuple))
        assert all(c[1]["record_deliveries"] is False for c in called if isinstance(c, tuple))

    def test_generation_finishes_before_any_checking_starts(self, spy):
        called, _ = spy
        boot.bootstrap(collection="all")
        assert called[:2] == ["gen-bdm", "gen-cp"]

    def test_one_collection_is_not_dispatched_to_a_pool(self, spy):
        called, dispatched = spy
        boot.bootstrap(collection="cp")
        assert dispatched == []
        assert ("cp", {"sequential": False, "record_deliveries": True, "after_each": None}) \
            in called, "alone, a collection records its own deliveries as it always did"

    def test_the_wall_clock_is_reported(self, spy):
        """Criterion 6: the gain is measured rather than estimated."""
        result = boot.bootstrap(collection="all")
        assert set(result.timings) == {"bdm", "cp", "total"}
        assert all(isinstance(v, float) for v in result.timings.values())
