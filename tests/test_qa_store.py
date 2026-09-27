"""The metadata schema that replaces the committed qa_results/ tree
(REQ-PIPE-089).

WRITTEN BEFORE THE CODE, and against `qa_store.py` as it already stood -
that module was drafted on 2026-09-26 and wired to nothing, so it had
never been executed once. Four of these failed against it, which is the
point of writing them first rather than after: an unexecuted module
reads as finished.

The four, because each is a criterion rather than a preference:

  A RUN IS NOT OBSERVABLE UNTIL IT IS COMPLETE (criterion 13). The draft
  had no way to say a run had finished, so a half-written run and a
  finished one were the same rows. This is the false-green shape this
  project keeps finding, and a reader cannot defend against it.

  TWO TOOLS IN ONE RUN DO NOT DELETE EACH OTHER (no criterion names it;
  it is a defect). `record_results` replaced by (run_key, scope), while
  the tree it replaces keyed a file by (scope, run, TOOL) - so Soda
  writing after dbt would have taken dbt's verdicts with it. Silent, and
  it would have looked like a tool that produced nothing.

  A DATASET STILL IN DEVELOPMENT IS MARKED AS SUCH (criterion 24).

  `tables_read` IS ROWS, NOT A DOCUMENT (decision 2) - the audit question
  "which version of this table did that run read" is the one worth being
  queryable across years.
"""
from __future__ import annotations

import pytest

from qa_tools.common import qa_store, supply_db


@pytest.fixture
def db(supply_dsn):
    """A worker's own database, EMPTIED of QA metadata for each test.

    Not decoration. The first run of this file failed three tests on
    rows a previous test had left behind - `soda_x` turning up in a
    cross-table assertion, a `births__` version in a table history -
    because a worker's database outlives any one test and these reuse
    run keys. That is the same latent-isolation shape this project found
    twice on 2026-09-27, so it gets closed here rather than worked
    around by making every run key unique.
    """
    with supply_db.connect(label="test-qa-store") as conn:
        qa_store.ensure_schema(conn)
        conn.execute(f'TRUNCATE "{qa_store.SCHEMA}".run CASCADE')
        yield conn


#: The facts the INVOCATION states rather than the record - the same
#: three the retired tree encoded in a file's path.
_KEYS = {"agency_id": "bdm", "collection_id": "birth-registrations"}


def _result(check_id: str, **over) -> dict:
    """One verified record, in the shape evaluate_*() really builds."""
    record = {
        "dataset_id": "birth-registrations",
        "check_id": check_id, "check_name": check_id.replace("_", " "),
        "status": "pass", "metric_value": 0.0, "unit": "rows",
        "row_count_total": 100, "row_count_invalid": 0,
    }
    record.update(over)
    return record


def _run(db, run_key="run_a", **over) -> str:
    kwargs = {"agency_id": "bdm", "collection_id": "birth-registrations",
              "run_timestamp": "2026-09-27T10:00:00+08:00", "run_by": "keith@example.gov.au",
              "environment": "local"}
    kwargs.update(over)
    qa_store.record_run(db, run_key=run_key, **kwargs)
    return run_key


class TestARunIsNotObservableUntilItIsComplete:
    """Criterion 13, and the one that needs a structure rather than a
    convention: every reader remembering to filter is the same as no
    filter at all, on the day one of them forgets."""

    def test_results_of_an_unfinished_run_are_not_returned(self, db):
        run_key = _run(db)
        qa_store.record_results(db, run_key, [_result("not_null_id")], tool="dbt", **_KEYS)

        assert qa_store.results_for_run(db, run_key) == [], \
            "a run nobody marked complete handed out its results anyway"

    def test_completing_the_run_makes_them_observable(self, db):
        run_key = _run(db)
        qa_store.record_results(db, run_key, [_result("not_null_id")], tool="dbt", **_KEYS)
        qa_store.complete_run(db, run_key)

        assert len(qa_store.results_for_run(db, run_key)) == 1

    def test_a_run_can_be_reopened_and_added_to(self, db):
        """Re-running a run is a real thing this pipeline does. The
        completeness marker has to survive it rather than latch."""
        run_key = _run(db)
        qa_store.record_results(db, run_key, [_result("not_null_id")], tool="dbt", **_KEYS)
        qa_store.complete_run(db, run_key)
        qa_store.reopen_run(db, run_key)

        assert qa_store.results_for_run(db, run_key) == []

    def test_the_incomplete_run_is_findable_by_someone_looking_for_it(self, db):
        """Invisible to a reader of results is not invisible full stop -
        an operator has to be able to see the wreckage of a crashed run."""
        run_key = _run(db)
        qa_store.record_results(db, run_key, [_result("not_null_id")], tool="dbt", **_KEYS)

        assert run_key in qa_store.incomplete_runs(db)
        qa_store.complete_run(db, run_key)
        assert run_key not in qa_store.incomplete_runs(db)


class TestTwoToolsInOneRunDoNotDeleteEachOther:
    """The defect in the draft. The tree keyed a file by (scope, run,
    tool); the draft replaced by (run, scope), losing the tool."""

    def test_soda_writing_after_dbt_leaves_dbts_verdicts_alone(self, db):
        run_key = _run(db)
        qa_store.record_results(db, run_key, [_result("dbt_not_null")], tool="dbt", **_KEYS)
        qa_store.record_results(db, run_key, [_result("soda_row_count", tool="soda", **_KEYS)],
                                tool="soda", **_KEYS)
        qa_store.complete_run(db, run_key)

        tools = sorted(r["tool"] for r in qa_store.results_for_run(db, run_key))
        assert tools == ["dbt", "soda"], \
            "one tool's write removed another tool's results from the same run"

    def test_re_running_one_tool_replaces_only_its_own_results(self, db):
        """Idempotence per tool, which is what the overwritten file gave."""
        run_key = _run(db)
        qa_store.record_results(db, run_key, [_result("a"), _result("b")], tool="dbt", **_KEYS)
        qa_store.record_results(db, run_key, [_result("soda_x", tool="soda", **_KEYS)], tool="soda", **_KEYS)
        qa_store.record_results(db, run_key, [_result("a")], tool="dbt", **_KEYS)
        qa_store.complete_run(db, run_key)

        rows = qa_store.results_for_run(db, run_key)
        assert sorted(r["check_id"] for r in rows) == ["a", "soda_x"]


class TestRecordsThatSpanDatasetsStayDistinguishable:
    """Criterion 5, and REQ-QAC-037's rule carried across unchanged: a
    check spanning datasets belongs to none of them."""

    def test_a_cross_table_result_is_not_returned_as_a_datasets_own(self, db):
        run_key = _run(db)
        qa_store.record_results(db, run_key, [_result("own_check")], tool="dbt", **_KEYS)
        qa_store.record_results(
            db, run_key, [_result("spanning_check", dataset_id=None)],
            tool="dbt", **_KEYS, scope=qa_store.CROSS_TABLE_SCOPE)
        qa_store.complete_run(db, run_key)

        own = qa_store.results_for_run(db, run_key, dataset_id="birth-registrations")
        assert [r["check_id"] for r in own] == ["own_check"]

        spanning = qa_store.cross_table_results(db, run_key)
        assert [r["check_id"] for r in spanning] == ["spanning_check"]


class TestADatasetStillInDevelopmentIsMarked:
    """Criterion 24, and decision 1: check development must be
    STRUCTURALLY incapable of counting toward real quality history."""

    def test_results_default_to_an_agreed_supply(self, db):
        run_key = _run(db)
        qa_store.record_results(db, run_key, [_result("a")], tool="dbt", **_KEYS)
        qa_store.complete_run(db, run_key)

        assert qa_store.results_for_run(db, run_key)[0]["supply_state"] == qa_store.AGREED

    def test_development_results_are_left_out_of_the_real_history(self, db):
        run_key = _run(db)
        qa_store.record_results(db, run_key, [_result("real_one")], tool="dbt", **_KEYS)
        qa_store.record_results(db, run_key, [_result("draft_one")], tool="dbt", **_KEYS,
                                supply_state=qa_store.IN_DEVELOPMENT)
        qa_store.complete_run(db, run_key)

        assert [r["check_id"] for r in qa_store.results_for_run(db, run_key)] == ["real_one"]

    def test_but_they_are_readable_when_asked_for_directly(self, db):
        """Excluded from quality history is not discarded - developing a
        check is real work and the person doing it has to see it."""
        run_key = _run(db)
        qa_store.record_results(db, run_key, [_result("draft_one")], tool="dbt", **_KEYS,
                                supply_state=qa_store.IN_DEVELOPMENT)
        qa_store.complete_run(db, run_key)

        rows = qa_store.results_for_run(db, run_key, supply_state=qa_store.IN_DEVELOPMENT)
        assert [r["check_id"] for r in rows] == ["draft_one"]


class TestTablesReadIsRowsRatherThanADocument:
    """Decision 2. dataset_stats stays a document because nothing
    queries inside it; this is the opposite case."""

    def test_which_version_of_a_table_a_run_read_is_a_query(self, db):
        run_key = _run(db)
        qa_store.record_tables_read(db, run_key, {
            "births": "births__2026-09-01",
            "registrations": "registrations__2026-09-01",
        })
        qa_store.complete_run(db, run_key)

        assert qa_store.tables_read_for_run(db, run_key)["births"] == "births__2026-09-01"

    def test_the_same_logical_table_across_runs_is_one_query(self, db):
        for n, physical in enumerate(("births__a", "births__b"), start=1):
            run_key = _run(db, run_key=f"run_{n}",
                           run_timestamp=f"2026-09-2{n}T10:00:00+08:00")
            qa_store.record_tables_read(db, run_key, {"births": physical})
            qa_store.complete_run(db, run_key)

        history = qa_store.table_history(db, "births")
        assert [row["physical_table"] for row in history] == ["births__a", "births__b"]


class TestTheHistoryQuestionThisWholeChangeIsFor:
    """The story: "every failure of this check since we started" as one
    question rather than a walk of a file tree (criterion 4)."""

    def test_one_checks_history_spans_runs(self, db):
        for n, status in enumerate(("pass", "fail", "pass"), start=1):
            run_key = _run(db, run_key=f"h{n}", run_timestamp=f"2026-09-2{n}T10:00:00+08:00")
            # ONE CALL, because that is what a tool does - it hands over
            # everything it found. Written as two calls first, which
            # correctly lost the first: a second write from the same tool
            # REPLACES that tool's results rather than adding to them,
            # which is the file this replaces being overwritten.
            qa_store.record_results(db, run_key, [_result("watched", status=status),
                                                  _result("ignored")], tool="dbt", **_KEYS)
            qa_store.complete_run(db, run_key)

        history = qa_store.history_for_check(db, "watched")
        assert [r["status"] for r in history] == ["pass", "fail", "pass"]

    def test_an_unfinished_runs_verdict_is_not_in_that_history(self, db):
        """Criterion 13 has to hold for every read, not just the obvious
        one - a half-written run leaking into a check's history is the
        same false green wearing a different hat."""
        done = _run(db, run_key="done", run_timestamp="2026-09-21T10:00:00+08:00")
        qa_store.record_results(db, done, [_result("watched", status="pass")], tool="dbt", **_KEYS)
        qa_store.complete_run(db, done)

        crashed = _run(db, run_key="crashed", run_timestamp="2026-09-22T10:00:00+08:00")
        qa_store.record_results(db, crashed, [_result("watched", status="fail")], tool="dbt", **_KEYS)

        assert [r["status"] for r in qa_store.history_for_check(db, "watched")] == ["pass"]


class TestEachToolsOwnOutputIsKeptWholeAndApart:
    """Criterion 3, and the NFR that it must not be dragged into a query
    that only wants verdicts - which is why it is its own table."""

    def test_raw_output_round_trips_per_run_and_tool(self, db):
        run_key = _run(db)
        qa_store.record_tool_output(db, run_key, "dbt", {"results": [{"unique_id": "x"}]})
        qa_store.record_tool_output(db, run_key, "soda", {"checks": []})
        qa_store.complete_run(db, run_key)

        assert qa_store.tool_output_for(db, run_key, "dbt") == {"results": [{"unique_id": "x"}]}
        assert qa_store.tool_output_for(db, run_key, "soda") == {"checks": []}

    def test_reading_verdicts_does_not_read_the_payload(self, db):
        """Structural rather than measured: the verdict query names one
        table, and the payload is not in it."""
        run_key = _run(db)
        qa_store.record_results(db, run_key, [_result("a")], tool="dbt", **_KEYS)
        qa_store.record_tool_output(db, run_key, "dbt", {"big": "x" * 10_000})
        qa_store.complete_run(db, run_key)

        assert "raw_output" not in qa_store.results_for_run(db, run_key)[0]


class TestAFinishedRunSaysWhoRanIt:
    """Criterion 6, enforced at COMPLETION rather than at registration.

    A run is opened by whoever reaches it first - the orchestrator,
    which knows who is running it, or a bare single-tool invocation,
    which does not. Requiring the identity up front would mean inventing
    one for the second case, and CLAUDE.md's rule on `get_run_by()` is
    that it never falls back to a placeholder. So the rule lands where
    it is actually meaningful: a run that FINISHED is attributable.
    """

    def test_a_run_with_no_identity_refuses_to_finish(self, db):
        qa_store.record_run(db, run_key="anon", agency_id="bdm",
                            collection_id="birth-registrations",
                            run_timestamp="2026-09-27T10:00:00+08:00")
        qa_store.record_results(db, "anon", [_result("a")], tool="dbt", **_KEYS)

        with pytest.raises(qa_store.UnattributedRun):
            qa_store.complete_run(db, "anon")

    def test_and_its_results_stay_invisible(self, db):
        """The refusal is not cosmetic - nothing downstream sees the run."""
        qa_store.record_run(db, run_key="anon", agency_id="bdm",
                            collection_id="birth-registrations",
                            run_timestamp="2026-09-27T10:00:00+08:00")
        qa_store.record_results(db, "anon", [_result("a")], tool="dbt", **_KEYS)
        with pytest.raises(qa_store.UnattributedRun):
            qa_store.complete_run(db, "anon")

        assert qa_store.results_for_run(db, "anon") == []
        assert "anon" in qa_store.incomplete_runs(db)

    def test_completing_a_run_nobody_registered_refuses_too(self, db):
        with pytest.raises(qa_store.UnattributedRun):
            qa_store.complete_run(db, "never-registered")

    def test_a_tools_defensive_registration_does_not_erase_the_identity(self, db):
        """The ordering that made COALESCE necessary. The orchestrator
        registers the run knowing who is running it; each tool's own
        write then registers it again knowing nothing. Plain EXCLUDED
        would let the last writer win, which here is the one with less
        information."""
        run_key = _run(db)
        qa_store.record_run(db, run_key=run_key, agency_id="bdm",
                            collection_id="birth-registrations",
                            run_timestamp="2026-09-27T10:00:00+08:00")

        qa_store.complete_run(db, run_key)
        assert qa_store.runs_for(db, "bdm", "birth-registrations")[0]["run_by"] \
            == "keith@example.gov.au"


class TestTwoWorkersCanCreateTheSchemaAtOnce:
    """A real bug, found by the first real `mothman pipeline bootstrap`
    against this schema rather than by review.

    `CREATE SCHEMA IF NOT EXISTS` is NOT atomic against a concurrent
    `CREATE SCHEMA` - PostgreSQL checks, then creates, and two sessions
    can both pass the check. The bootstrap runs its two collections in
    parallel, both called `ensure_schema`, and one died with
    `duplicate key value violates unique constraint
    "pg_namespace_nspname_index"`. Child Protection recorded nothing at
    all that run.

    IF NOT EXISTS reads as the careful option, which is what makes this
    worth a test rather than a comment: the whole DDL is full of them
    and every one has the same hazard.
    """

    def test_concurrent_ensure_schema_calls_all_succeed(self, supply_dsn):
        import threading

        from qa_tools.common import supply_db as db_mod

        with db_mod.connect(label="test-drop-qa") as conn:
            conn.execute(f'DROP SCHEMA IF EXISTS "{qa_store.SCHEMA}" CASCADE')

        failures: list[BaseException] = []
        start = threading.Barrier(8)

        def race():
            try:
                start.wait(timeout=10)
                with db_mod.connect(label="test-race") as conn:
                    qa_store.ensure_schema(conn)
            except BaseException as exc:  # noqa: BLE001 - the point is to collect it
                failures.append(exc)

        threads = [threading.Thread(target=race) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        assert not failures, \
            f"concurrent ensure_schema calls raised: {failures[0]!r}"


class TestEnsureSchemaIsCheapOnceTheSchemaExists:
    """The second real bug the first real bootstrap found, and a worse
    one than the create race above.

    `ensure_schema` ran the ENTIRE DDL on every write. Two statements in
    it take an AccessExclusiveLock - `ALTER TABLE ... DROP NOT NULL` and
    `CREATE OR REPLACE VIEW` - while a parallel worker inserting a
    result holds a RowShareLock on `qa.run` for the foreign-key check.
    PostgreSQL detected the deadlock and killed a real dbt run:

        Process A waits for RowShareLock on qa.run; blocked by B.
        Process B waits for AccessExclusiveLock on a view; blocked by A.

    Migration DDL on a hot write path is the defect. The fix is a
    version marker, so the DDL runs when the shape actually changes and
    never otherwise.

    The test drives the property rather than the deadlock, because a
    deadlock test is a race and this is not: hold a perfectly ordinary
    shared lock on one of the tables, and an `ensure_schema` that still
    wants an exclusive one cannot get past it.
    """

    def test_it_does_not_want_an_exclusive_lock_on_a_table_in_use(self, db, supply_dsn):
        from qa_tools.common import supply_db as db_mod

        qa_store.ensure_schema(db)  # up to date before the lock is taken

        holder = db_mod.connect(label="test-lock-holder")
        try:
            holder.raw.execute("BEGIN")
            holder.execute(f'LOCK TABLE "{qa_store.SCHEMA}".run IN ACCESS SHARE MODE')

            with db_mod.connect(label="test-ensure-under-lock") as other:
                # Raises psycopg.errors.LockNotAvailable once the
                # connection's own lock_timeout expires, which is what
                # the old ensure_schema did here.
                qa_store.ensure_schema(other)
        finally:
            holder.raw.execute("ROLLBACK")
            holder.close()

    def test_but_it_still_builds_the_schema_from_nothing(self, supply_dsn):
        """The cheap path must not become a path that never creates
        anything - which is the obvious way to break this fix."""
        from qa_tools.common import supply_db as db_mod

        with db_mod.connect(label="test-rebuild") as conn:
            conn.execute(f'DROP SCHEMA IF EXISTS "{qa_store.SCHEMA}" CASCADE')
            qa_store.ensure_schema(conn)
            assert conn.execute(
                f"SELECT to_regclass('{qa_store.SCHEMA}.check_result')").fetchall()[0][0]
