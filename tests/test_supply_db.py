"""qa_tools/common/supply_db.py - one database, and one place where a
logical table name becomes a physical table (REQ-PIPE-068).

Every test here is against a REAL DuckDB database in tmp_path rather
than a mock, because the whole point of the module is what DuckDB
actually does with schemas, views and locks - a mock would assert that
the code calls the functions it calls, which is not the claim.
"""
from __future__ import annotations

import multiprocessing as mp
import time

import duckdb
import pytest

from qa_tools.common import supply_db


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv(supply_db.SUPPLY_DB_ENV, str(tmp_path / "supply.duckdb"))
    conn = supply_db.connect()
    supply_db.ensure_schemas(conn)
    yield conn
    conn.close()


def _stage(conn, table: str, run_id: str, rows: int = 1) -> str:
    physical = supply_db.staged_table(table, run_id)
    conn.execute(
        f'CREATE TABLE "{supply_db.STAGING_SCHEMA}"."{physical}" AS '
        f"SELECT * FROM range({rows}) t(id)")
    return physical


class TestOneNameResolvesToOneTable:
    """Criteria 1 and 4."""

    def test_a_single_candidate_becomes_a_readable_view(self, db):
        _stage(db, "birth_registrations", "run_001", rows=3)
        res = supply_db.create_run_views(
            db, "run_001", supply_db.candidates_in(
                db, supply_db.STAGING_SCHEMA, ["birth_registrations"]))
        assert res.resolved == {"birth_registrations": "birth_registrations__001"}
        got = db.execute(
            f'SELECT count(*) FROM "{res.schema}"."birth_registrations"').fetchone()[0]
        assert got == 3

    def test_a_name_with_no_candidate_is_absent_not_empty(self, db):
        res = supply_db.create_run_views(
            db, "run_001", supply_db.candidates_in(
                db, supply_db.STAGING_SCHEMA, ["cp_clients"]))
        assert res.absent == ["cp_clients"]
        assert res.resolved == {}
        # Absent means the NAME does not resolve - not that it resolves
        # to nothing. A check against it must fail loudly rather than
        # pass over zero rows, which is the false-green direction.
        with pytest.raises(duckdb.CatalogException):
            db.execute(f'SELECT * FROM "{res.schema}"."cp_clients"')


class TestAmbiguityIsAbsenceRatherThanAChoice:
    """Criterion 3, and REQ-PIPE-059 depends on it."""

    def test_two_candidates_produce_no_view_at_all(self, db):
        _stage(db, "cp_clients", "run_007")
        # A second physical table claiming the same logical name, which
        # is what two files delivered for one dataset looks like once
        # both are staged.
        db.execute(
            f'CREATE TABLE "{supply_db.STAGING_SCHEMA}"."cp_clients__007b" AS '
            "SELECT * FROM range(9) t(id)")
        res = supply_db.create_run_views(
            db, "run_007", supply_db.candidates_in(
                db, supply_db.STAGING_SCHEMA, ["cp_clients"]))
        assert res.resolved == {}
        assert res.ambiguous == {
            "cp_clients": ["cp_clients__007", "cp_clients__007b"]}
        with pytest.raises(duckdb.CatalogException):
            db.execute(f'SELECT * FROM "{res.schema}"."cp_clients"')

    def test_it_never_picks_the_first_one(self, db):
        """The failure this prevents is silent: a view over whichever
        candidate happened to sort first reads as a healthy table."""
        for suffix in ("a", "b", "c"):
            db.execute(
                f'CREATE TABLE "{supply_db.STAGING_SCHEMA}"."cp_carers__{suffix}" AS '
                "SELECT 1 AS id")
        res = supply_db.create_run_views(
            db, "r", supply_db.candidates_in(
                db, supply_db.STAGING_SCHEMA, ["cp_carers"]))
        assert res.resolved == {}
        assert len(res.ambiguous["cp_carers"]) == 3

    def test_ambiguous_and_absent_are_reported_apart(self, db):
        """They are the same thing to a check and completely different
        things to whoever has to fix it."""
        db.execute(
            f'CREATE TABLE "{supply_db.STAGING_SCHEMA}"."cp_carers__x" AS SELECT 1 AS id')
        db.execute(
            f'CREATE TABLE "{supply_db.STAGING_SCHEMA}"."cp_carers__y" AS SELECT 1 AS id')
        res = supply_db.create_run_views(
            db, "r", supply_db.candidates_in(
                db, supply_db.STAGING_SCHEMA, ["cp_carers", "cp_placements"]))
        assert list(res.ambiguous) == ["cp_carers"]
        assert res.absent == ["cp_placements"]


class TestCandidatesAreScopedToTheRun:
    """A real bug, found by running the pipeline against 42 real runs
    (2026-09-25).

    `create_run_views()` was being asked for candidates across the whole
    staging schema rather than for the run being built, so by the
    forty-second run the logical name had forty-two candidates, the
    ambiguity rule correctly refused to choose, and dbt failed to find a
    table that was sitting right there. The ambiguity rule was right;
    the question it was asked was wrong - and the symptom was a missing
    table, which reads nothing like a scoping mistake.
    """

    def test_a_run_sees_its_own_arrival_and_not_every_other_one(self, db):
        for run_id in ("run_001", "run_002", "run_042"):
            _stage(db, "birth_registrations", run_id)
        res = supply_db.create_run_views(db, "run_042", supply_db.candidates_in(
            db, supply_db.STAGING_SCHEMA, ["birth_registrations"], arrival=supply_db.arrival_key("run_042")))
        assert res.resolved == {"birth_registrations": "birth_registrations__042"}
        assert res.ambiguous == {}

    def test_unscoped_is_what_went_wrong(self, db):
        """The old call, kept as a test so the failure mode stays
        visible rather than becoming a thing nobody remembers."""
        for run_id in ("run_001", "run_002"):
            _stage(db, "birth_registrations", run_id)
        unscoped = supply_db.candidates_in(
            db, supply_db.STAGING_SCHEMA, ["birth_registrations"])
        assert len(unscoped["birth_registrations"]) == 2
        res = supply_db.create_run_views(db, "run_001", unscoped)
        assert res.resolved == {}, "this is the bug: every run after the first resolves nothing"

    def test_a_run_id_is_matched_whole_not_by_prefix(self, db):
        """`run_001` and `run_0011` are different runs, and a prefix
        test says the second belongs to the first."""
        _stage(db, "birth_registrations", "run_001")
        _stage(db, "birth_registrations", "run_0011")
        found = supply_db.candidates_in(
            db, supply_db.STAGING_SCHEMA, ["birth_registrations"], arrival=supply_db.arrival_key("run_001"))
        assert found["birth_registrations"] == ["birth_registrations__001"]

    def test_two_files_for_one_dataset_in_one_run_are_still_ambiguous(self, db):
        """The ambiguity this is actually for (REQ-PIPE-059) survives
        the scoping - it is within one run, not across runs."""
        _stage(db, "cp_clients", "run_007")
        # The real second-file form: an ordinal, never the supplier's
        # filename, because these become SQL identifiers.
        db.execute(
            f'CREATE TABLE "{supply_db.STAGING_SCHEMA}"'
            f'."{supply_db.staged_table("cp_clients", "run_007", 2)}" AS SELECT 1 AS id')
        found = supply_db.candidates_in(
            db, supply_db.STAGING_SCHEMA, ["cp_clients"], arrival=supply_db.arrival_key("run_007"))
        assert len(found["cp_clients"]) == 2
        res = supply_db.create_run_views(db, "run_007", found)
        assert res.resolved == {} and list(res.ambiguous) == ["cp_clients"]


class TestACandidateMustActuallyClaimTheName:
    def test_a_longer_name_is_not_a_candidate_for_a_shorter_one(self, db):
        """`cp_case_workers__x` is not a version of `cp_case`. A prefix
        test says it is, which is why this is matched on the separator."""
        _stage(db, "cp_case_workers", "run_001")
        found = supply_db.candidates_in(
            db, supply_db.STAGING_SCHEMA, ["cp_case", "cp_case_workers"])
        assert found["cp_case"] == []
        assert found["cp_case_workers"] == ["cp_case_workers__001"]

    def test_a_table_in_another_schema_is_not_a_candidate(self, db):
        db.execute('CREATE SCHEMA IF NOT EXISTS "somewhere_else"')
        db.execute('CREATE TABLE "somewhere_else"."cp_clients__001" AS SELECT 1 AS id')
        found = supply_db.candidates_in(
            db, supply_db.STAGING_SCHEMA, ["cp_clients"])
        assert found["cp_clients"] == []


class TestTheRunSchemaIsDisposable:
    """Criteria 1 and 6."""

    def test_the_schema_goes_when_the_run_does(self, db):
        _stage(db, "birth_registrations", "run_001")
        supply_db.create_run_views(db, "run_001", supply_db.candidates_in(
            db, supply_db.STAGING_SCHEMA, ["birth_registrations"]))
        assert supply_db.run_schemas(db) == [supply_db.run_schema("run_001")]
        supply_db.drop_run_schema(db, "run_001")
        assert supply_db.run_schemas(db) == []

    def test_dropping_a_schema_that_was_never_made_is_not_an_error(self, db):
        """The caller that matters is a cleanup path, which cannot know
        whether the run got far enough to create one."""
        supply_db.drop_run_schema(db, "run_never")

    def test_dropping_the_view_schema_leaves_the_data_alone(self, db):
        _stage(db, "birth_registrations", "run_001", rows=5)
        supply_db.create_run_views(db, "run_001", supply_db.candidates_in(
            db, supply_db.STAGING_SCHEMA, ["birth_registrations"]))
        supply_db.drop_run_schema(db, "run_001")
        still = db.execute(
            f'SELECT count(*) FROM "{supply_db.STAGING_SCHEMA}".'
            f'"birth_registrations__001"').fetchone()[0]
        assert still == 5, "a view schema is a lens, and dropping it must not drop the supply"

    def test_an_orphan_is_identifiable_without_any_other_record(self, db):
        """Criterion 6 in as many words: 'without reference to any other
        record'. The schema name alone has to say which run it was."""
        supply_db.create_run_views(db, "run_042", {})
        [orphan] = supply_db.run_schemas(db)
        assert supply_db.run_id_of(orphan) == "run_042"

    def test_a_schema_that_is_not_a_run_schema_is_left_alone(self, db):
        db.execute('CREATE SCHEMA IF NOT EXISTS "period_2026q1"')
        supply_db.create_run_views(db, "run_001", {})
        dropped = supply_db.drop_orphan_run_schemas(db)
        assert dropped == [supply_db.run_schema("run_001")]
        assert supply_db.run_id_of("period_2026q1") is None
        schemas = [r[0] for r in db.execute(
            "SELECT schema_name FROM information_schema.schemata").fetchall()]
        assert "period_2026q1" in schemas

    def test_the_run_in_flight_is_spared(self, db):
        supply_db.create_run_views(db, "run_001", {})
        supply_db.create_run_views(db, "run_002", {})
        dropped = supply_db.drop_orphan_run_schemas(db, keep=["run_002"])
        assert dropped == [supply_db.run_schema("run_001")]
        assert supply_db.run_schemas(db) == [supply_db.run_schema("run_002")]


class TestOneDatabase:
    """Criterion 7."""

    def test_staging_and_rejected_live_in_the_same_database(self, db):
        schemas = {r[0] for r in db.execute(
            "SELECT schema_name FROM information_schema.schemata").fetchall()}
        assert {supply_db.STAGING_SCHEMA, supply_db.REJECTED_SCHEMA} <= schemas

    def test_two_runs_share_one_database_and_do_not_collide(self, db):
        _stage(db, "birth_registrations", "run_001", rows=1)
        _stage(db, "birth_registrations", "run_002", rows=2)
        a = supply_db.create_run_views(db, "run_001", {
            "birth_registrations": ["birth_registrations__001"]})
        b = supply_db.create_run_views(db, "run_002", {
            "birth_registrations": ["birth_registrations__002"]})
        assert a.schema != b.schema
        assert db.execute(f'SELECT count(*) FROM "{a.schema}"."birth_registrations"').fetchone()[0] == 1
        assert db.execute(f'SELECT count(*) FROM "{b.schema}"."birth_registrations"').fetchone()[0] == 2

    def test_a_resupply_is_a_new_table_rather_than_an_overwrite(self, db):
        """The cheapest implementation is the wrong one: CREATE OR
        REPLACE keeps exactly one version and destroys the history the
        read-the-newest rule exists for."""
        assert supply_db.staged_table("cp_clients", "run_001") \
            != supply_db.staged_table("cp_clients", "run_002")


class TestWhereItRefusesToGuess:
    def test_an_unusable_run_id_is_an_error_rather_than_a_mangled_schema(self):
        with pytest.raises(supply_db.SupplyDbError):
            supply_db.run_schema('bad"; DROP SCHEMA staging; --')

    def test_an_unusable_table_name_is_an_error(self):
        with pytest.raises(supply_db.SupplyDbError):
            supply_db.staged_table("cp clients; drop", "run_001")

    def test_opening_a_database_that_does_not_exist_read_only_says_so(self, tmp_path, monkeypatch):
        """DuckDB's own message for this is about a file, which is not
        what the reader was looking for."""
        monkeypatch.setenv(supply_db.SUPPLY_DB_ENV, str(tmp_path / "nope.duckdb"))
        with pytest.raises(supply_db.SupplyDbError, match="nothing has been staged"):
            supply_db.connect(read_only=True)


def _reader(path, out):
    try:
        conn = duckdb.connect(path, read_only=True)
        conn.execute("SELECT 1").fetchall()
        time.sleep(1.5)
        conn.close()
        out.put("ok")
    except Exception as exc:  # pragma: no cover - the failure is the signal
        out.put(f"{type(exc).__name__}: {exc}")


class TestTheConcurrencyTheDesignRestsOn:
    """The reason the view schema is built serially and every check
    opens read-only. Asserted rather than assumed, because the whole
    fan-out design rests on it and `duckdb.org` is blocked from this
    environment - a real run is the better primary source anyway.
    """

    def test_many_readers_can_open_one_database_at_once(self, tmp_path):
        path = str(tmp_path / "supply.duckdb")
        conn = duckdb.connect(path)
        conn.execute("CREATE TABLE t AS SELECT 1 AS id")
        conn.close()
        out = mp.Queue()
        procs = [mp.Process(target=_reader, args=(path, out)) for _ in range(3)]
        for p in procs:
            p.start()
        for p in procs:
            p.join(30)
        assert [out.get() for _ in procs] == ["ok", "ok", "ok"]


class TestWhatARunReadIsRecorded:
    """Criterion 5. The view schema is discarded when the run ends, so
    "which version of this table did that run read" has to be answered
    from somewhere else - and years later, of an audit or of a check
    that started failing.
    """

    def test_a_resolution_survives_the_schema_it_describes(self, db):
        _stage(db, "birth_registrations", "run_001")
        res = supply_db.create_run_views(db, "run_001", supply_db.candidates_in(
            db, supply_db.STAGING_SCHEMA, ["birth_registrations"], arrival=supply_db.arrival_key("run_001")))
        supply_db.record_resolution(db, res)
        supply_db.drop_run_schema(db, "run_001")

        back = supply_db.resolution_for(db, "run_001")
        assert back.resolved == {"birth_registrations": "birth_registrations__001"}

    def test_it_records_why_a_name_was_not_readable(self, db):
        """Ambiguous and absent are different answers to "why is this
        table missing", and both are worth keeping."""
        for ordinal in (1, 2):
            db.execute(
                f'CREATE TABLE "{supply_db.STAGING_SCHEMA}"'
                f'."{supply_db.staged_table("cp_carers", "r", ordinal)}" AS SELECT 1 AS id')
        res = supply_db.create_run_views(db, "r", supply_db.candidates_in(
            db, supply_db.STAGING_SCHEMA, ["cp_carers", "cp_placements"], arrival=supply_db.arrival_key("r")))
        supply_db.record_resolution(db, res)

        back = supply_db.resolution_for(db, "r")
        assert back.ambiguous == {"cp_carers": ["cp_carers__0__1", "cp_carers__0__2"]}
        assert back.absent == ["cp_placements"]

    def test_restaging_replaces_the_record_rather_than_adding_to_it(self, db):
        _stage(db, "birth_registrations", "run_001")
        args = (db, "run_001", supply_db.candidates_in(
            db, supply_db.STAGING_SCHEMA, ["birth_registrations"], arrival=supply_db.arrival_key("run_001")))
        supply_db.record_resolution(db, supply_db.create_run_views(*args))
        supply_db.record_resolution(db, supply_db.create_run_views(*args))

        back = supply_db.resolution_for(db, "run_001")
        assert back.resolved == {"birth_registrations": "birth_registrations__001"}
        assert back.ambiguous == {} and back.absent == []

    def test_a_run_nobody_recorded_reads_as_empty_rather_than_raising(self, db):
        """The caller asking is reporting, and a report saying "nothing
        recorded" is more use than a traceback."""
        assert supply_db.resolution_for(db, "run_never").resolved == {}

    def test_the_record_names_the_run_and_the_schema_it_describes(self, db):
        _stage(db, "birth_registrations", "run_009")
        res = supply_db.create_run_views(db, "run_009", supply_db.candidates_in(
            db, supply_db.STAGING_SCHEMA, ["birth_registrations"], arrival=supply_db.arrival_key("run_009")))
        record = res.as_record()
        assert record["run_id"] == "run_009"
        assert record["schema"] == supply_db.run_schema("run_009")
        assert record["resolved"] == {"birth_registrations": "birth_registrations__009"}
