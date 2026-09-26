"""qa_tools/common/supply_db.py - one database, and one place where a
logical table name becomes a physical table (REQ-PIPE-068).

Every test here is against a REAL PostgreSQL rather than a mock, because
the whole point of the module is what the database actually does with
schemas and views - a mock would assert that the code calls the functions
it calls, which is not the claim.

THE ENGINE CHANGED UNDER THIS FILE (REQ-PIPE-087) and two things moved
with it. The database comes from conftest's per-worker fixture instead of
a file in tmp_path, so each test resets its schemas rather than getting a
fresh file. And the class that used to assert DuckDB's locking now
asserts the opposite property - that a writer does NOT exclude readers -
because that is the fact the new design rests on, and the old one was
load-bearing for a workaround that has been removed.
"""
from __future__ import annotations

import psycopg
import pytest

import dbsupport
from qa_tools.common import supply_db


@pytest.fixture
def db(supply_dsn, monkeypatch):
    """An empty supply database of this test's OWN.

    Not a cleared version of the worker's shared one, which is what the
    first attempt did and what silently destroyed the session-staged
    fixtures' data for every file that ran after this one on the same
    worker - see tests/dbsupport.py for that incident in full.
    """
    dbsupport.use_empty_supply_db(monkeypatch)
    conn = supply_db.connect()
    supply_db.ensure_schemas(conn)
    yield conn
    conn.close()


def _stage(conn, table: str, run_id: str, rows: int = 1) -> str:
    physical = supply_db.staged_table(table, run_id)
    # generate_series, not DuckDB's range() - the same one-column table of
    # integers, spelled the way PostgreSQL spells it.
    conn.execute(
        f'CREATE TABLE "{supply_db.STAGING_SCHEMA}"."{physical}" AS '
        f"SELECT * FROM generate_series(0, {rows - 1}) AS t(id)")
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
        with pytest.raises(psycopg.errors.UndefinedTable):
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
            "SELECT * FROM generate_series(0, 8) AS t(id)")
        res = supply_db.create_run_views(
            db, "run_007", supply_db.candidates_in(
                db, supply_db.STAGING_SCHEMA, ["cp_clients"]))
        assert res.resolved == {}
        assert res.ambiguous == {
            "cp_clients": ["cp_clients__007", "cp_clients__007b"]}
        with pytest.raises(psycopg.errors.UndefinedTable):
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

    def test_an_unset_dsn_is_an_error_naming_the_variable(self, monkeypatch):
        """There is no default and no file to fall back to, so the only
        useful thing to say is which variable is missing."""
        monkeypatch.delenv(supply_db.SUPPLY_DSN_ENV, raising=False)
        with pytest.raises(supply_db.SupplyDbError, match=supply_db.SUPPLY_DSN_ENV):
            supply_db.connect()

    def test_an_unreachable_database_says_so_and_names_the_host(self, monkeypatch):
        """REQ-PIPE-087 criterion 12: loud, naming where it tried, and
        never falling back to anything else."""
        monkeypatch.setenv(supply_db.SUPPLY_DSN_ENV,
                           "postgresql://nobody@127.0.0.1:1/absent")
        with pytest.raises(supply_db.SupplyDbError, match="cannot reach the supply database"):
            supply_db.connect()

    def test_a_password_never_reaches_the_error_message(self, monkeypatch):
        """This repository is public and its errors reach Actions logs."""
        monkeypatch.setenv(supply_db.SUPPLY_DSN_ENV,
                           "postgresql://bob:hunter2@127.0.0.1:1/absent")
        with pytest.raises(supply_db.SupplyDbError) as exc:
            supply_db.connect()
        assert "hunter2" not in str(exc.value)
        assert "***" in str(exc.value)

    def test_an_identifier_too_long_for_postgres_is_refused(self):
        """Postgres truncates past 63 bytes SILENTLY, which turns a
        staged table's arrival suffix into a collision rather than an
        error. The retired engine had no such limit, so nothing in this
        project used to have to care."""
        with pytest.raises(supply_db.SupplyDbError, match="63-byte identifier limit"):
            supply_db._ident("x" * 64, "table name")


class TestItNeverWaitsForeverForALock:
    """The failure mode this class exists for is a HANG, which is worse
    than an error: it is indistinguishable from slow, it holds its own
    locks while it waits, and nothing in a log says why.

    Real incident, 2026-09-27, and the reason this test exists: a QA tool
    left its connection idle in a transaction holding a read lock on a
    staged table, and the next load's DROP TABLE blocked behind it for
    six minutes until the run was killed by hand. PostgreSQL's default
    lock_timeout is 0, meaning wait forever.
    """

    def test_a_statement_blocked_on_a_lock_fails_instead_of_hanging(self, db, monkeypatch):
        import psycopg

        monkeypatch.setenv(supply_db.LOCK_TIMEOUT_ENV, "1000")
        db.execute(f'CREATE TABLE "{supply_db.STAGING_SCHEMA}"."lock_probe" (x int)')

        # A reader behaving exactly like the tool that caused this: a
        # SELECT inside a transaction it never commits, so ACCESS SHARE
        # is held indefinitely.
        leaker = psycopg.connect(supply_db.supply_db_dsn())
        try:
            leaker.execute(f'SELECT * FROM "{supply_db.STAGING_SCHEMA}"."lock_probe"')
            writer = supply_db.connect()
            try:
                with pytest.raises(psycopg.errors.LockNotAvailable):
                    writer.execute(
                        f'DROP TABLE "{supply_db.STAGING_SCHEMA}"."lock_probe" CASCADE')
            finally:
                writer.close()
        finally:
            leaker.close()

    def test_a_nonsense_timeout_is_refused_rather_than_ignored(self, monkeypatch):
        monkeypatch.setenv(supply_db.LOCK_TIMEOUT_ENV, "soon")
        with pytest.raises(supply_db.SupplyDbError, match="whole number of milliseconds"):
            supply_db.connect()


class TestAWriterDoesNotExcludeReaders:
    """The property the new design rests on, and the exact reverse of what
    this file used to assert.

    Under the retired engine a single writer took an exclusive lock over
    the whole database file and shut out every reader, which is why the
    fan-out opened read-only and why dbt got a scratch database of its
    own. Both workarounds are gone (REQ-PIPE-087), so the fact they were
    working around is worth pinning in the other direction - otherwise
    somebody reintroduces a workaround for a problem that no longer
    exists.
    """

    def test_a_reader_sees_committed_rows_while_another_connection_holds_one_open(self, db):
        _stage(db, "birth_registrations", "run_001", rows=3)
        writer = supply_db.connect()
        reader = supply_db.connect(read_only=True)
        try:
            physical = supply_db.staged_table("birth_registrations", "run_001")
            # A real open write transaction on one connection...
            with writer.raw.transaction():
                writer.raw.execute(
                    f'CREATE TABLE "{supply_db.STAGING_SCHEMA}"."held_open" (x int)')
                # ...while the other reads, rather than blocking on a lock.
                rows = reader.execute(
                    f'SELECT count(*) FROM "{supply_db.STAGING_SCHEMA}"."{physical}"'
                ).fetchall()
            assert rows[0][0] == 3
        finally:
            reader.close()
            writer.close()

    def test_a_read_only_connection_cannot_write(self, db):
        """read_only stopped being about parallelism and started being
        about what it says - so it has to actually refuse."""
        reader = supply_db.connect(read_only=True)
        try:
            with pytest.raises(Exception):
                reader.execute(f'CREATE TABLE "{supply_db.STAGING_SCHEMA}"."nope" (x int)')
        finally:
            reader.close()


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
