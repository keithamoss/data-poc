"""qa_tools/common/load_log.py - a table is loaded or it is not
(REQ-PIPE-060).

The claim under test is an ORDERING and a VISIBILITY rule, not a file
format: a record is written only after the load is durable, and a table
with no record is invisible to a check however physically present it is.
Both are tested against real records in a real database - a mock would
assert that the code calls the functions it calls.

MOVED OFF DISK BY REQ-PIPE-089 (criteria 14 and 22). The claim is
unchanged, because it was never a claim about files; what changed is
that isolation now comes from each test worker having its own database
rather than from a temporary directory, and that "latest" is the
highest id on an append-only table rather than the largest timestamp
string.
"""
from __future__ import annotations

import pytest

import dbsupport

from qa_tools.common import load_log, supply_db


@pytest.fixture
def clean_log(supply_dsn):
    """An empty load log on this worker's own database.

    The temporary directory this replaces was per-test; a worker's
    database is not, so it is emptied here. Same isolation, and it also
    covers the reader functions, which used to take a directory and now
    simply query.
    """
    from qa_tools.common import qa_store

    with supply_db.connect(label="test-load-log") as conn:
        qa_store.ensure_schema(conn)
        conn.execute(f'TRUNCATE "{qa_store.SCHEMA}".load_outcome')
        yield conn


def _rec(physical, outcome=load_log.LOADED, at="2026-09-25T09:00:00+08:00",
         delivery="d1", dataset_id="cp-clients", **kw):
    return load_log.record(delivery, dataset_id, physical, outcome, at, **kw)


class TestOnlyArrivalFacts:
    """Criteria 2 and 3."""

    def test_a_record_carries_the_delivery_the_dataset_and_when(self, clean_log):
        _rec("cp_clients__2026", row_count=9)
        written = load_log.records()[0]
        assert written.delivery == "d1"
        assert written.dataset_id == "cp-clients"
        assert written.physical == "cp_clients__2026"
        assert written.row_count == 9
        assert written.recorded_at == "2026-09-25T09:00:00+08:00"

    def test_no_period_no_slot_no_supersession(self, clean_log):
        """Criterion 3, and it is the whole point of this sprint:
        staging may not be wrong about anything, and the only way to be
        certain of that is to assert nothing it cannot observe."""
        _rec("cp_clients__2026")
        recorded = vars(load_log.records()[0])
        forbidden = {"period", "slot", "supersedes", "superseded_by", "promoted"}
        assert forbidden.isdisjoint(recorded), (
            f"a load record asserted something arrival cannot know: "
            f"{sorted(forbidden & set(recorded))}")


class TestAnUnrecordedTableIsUnloaded:
    """Criteria 7 and 15."""

    def test_a_staged_table_with_no_record_is_not_a_candidate(self, tmp_path, monkeypatch, clean_log):
        # An EMPTY database on this worker's PostgreSQL, which is what a
        # fresh file used to give (REQ-TEST-095).
        dbsupport.use_empty_supply_db(monkeypatch)
        conn = supply_db.connect()
        supply_db.ensure_schemas(conn)
        physical = supply_db.staged_table("cp_clients", "2026-09-25T09:00:00+08:00")
        conn.execute(f'CREATE TABLE "{supply_db.STAGING_SCHEMA}"."{physical}" AS SELECT 1 AS id')
        try:
            # PHYSICALLY THERE, and physically readable - which is
            # exactly the state an interrupted load leaves behind, and
            # exactly why the catalogue cannot answer this question.
            assert conn.execute(
                f'SELECT count(*) FROM "{supply_db.STAGING_SCHEMA}"."{physical}"').fetchone()[0] == 1
            found = supply_db.candidates_in(
                conn, supply_db.STAGING_SCHEMA, ["cp_clients"],
                loaded=load_log.loaded_tables())
            assert found["cp_clients"] == []

            _rec(physical)
            found = supply_db.candidates_in(
                conn, supply_db.STAGING_SCHEMA, ["cp_clients"],
                loaded=load_log.loaded_tables())
            assert found["cp_clients"] == [physical]
        finally:
            conn.close()

    def test_a_failed_record_does_not_make_a_table_visible(self, clean_log):
        _rec("cp_clients__2026", outcome=load_log.FAILED, reason="bad csv")
        assert load_log.loaded_tables() == frozenset()


class TestLatestWins:
    """Criterion 19."""

    def test_a_reprocess_writes_a_new_record_and_keeps_the_failed_one(self, clean_log):
        _rec("cp_clients__2026", outcome=load_log.FAILED,
              at="2026-09-25T09:00:00+08:00", reason="bad encoding")
        _rec("cp_clients__2026", outcome=load_log.LOADED,
              at="2026-09-25T11:00:00+08:00", row_count=4)

        assert len(load_log.records()) == 2, (
            "the failed record must survive the fix - the history of what went wrong "
            "is the reason this is append-only")
        assert load_log.loaded_tables() == frozenset({"cp_clients__2026"})
        assert load_log.failures() == []

    def test_a_later_failure_supersedes_an_earlier_success(self, clean_log):
        _rec("cp_clients__2026", at="2026-09-25T09:00:00+08:00")
        _rec("cp_clients__2026", outcome=load_log.FAILED,
              at="2026-09-25T11:00:00+08:00", reason="reloaded and it broke")
        assert load_log.loaded_tables() == frozenset()
        assert [r.reason for r in load_log.failures()] == ["reloaded and it broke"]


class TestADeliveryIsProcessedOnlyInFull:
    """Criteria 8 and 16."""

    def test_a_partially_staged_delivery_is_not_processed(self, clean_log):
        _rec("cp_clients__2026")
        _rec("cp_carers__2026")
        expected = {"cp_clients__2026", "cp_carers__2026", "cp_placements__2026"}
        assert not load_log.delivery_is_processed("d1", expected)
        _rec("cp_placements__2026")
        assert load_log.delivery_is_processed("d1", expected)

    def test_another_deliverys_records_do_not_complete_this_one(self, clean_log):
        _rec("cp_clients__2026", delivery="d1")
        _rec("cp_carers__2026", delivery="d2")
        assert not load_log.delivery_is_processed(
            "d1", {"cp_clients__2026", "cp_carers__2026"})

    def test_a_delivery_that_staged_nothing_is_not_processed(self, clean_log):
        assert not load_log.delivery_is_processed("d1", set())


class TestUnreadableMeansUntrusted:
    """RETIRED BY REQ-PIPE-089, and left here saying so rather than
    silently deleted.

    The property was real while records were files: a half-written or
    corrupt JSON file had to read as NO record - untrusted - rather
    than crash the reader or, worse, be partially believed. The test
    wrote `{not json` into the log directory and asserted the rest
    still resolved.

    There is no directory to write it into any more, and a row is
    either committed or it is not, so the failure mode this defended
    against cannot occur. Removing the defence with the mechanism is
    correct; removing the RECORD of why it existed is how somebody
    later reintroduces a file-backed log without knowing what it costs.
    """


class TestAnOutcomeIsOneOfTwoThings:
    def test_an_unknown_outcome_is_refused(self, clean_log):
        with pytest.raises(ValueError, match="load outcome"):
            _rec("cp_clients__2026", outcome="probably fine")


class TestAnUnchangedRestageWritesNothing:
    """record_load(), and the bound it puts on a committed tree."""

    def test_the_same_outcome_twice_writes_one_record(self, clean_log):
        first = load_log.record_load("d1", "cp-clients", "cp_clients__2026",
                                      load_log.LOADED, "2026-09-25T09:00:00+08:00",
                                      row_count=4)
        again = load_log.record_load("d1", "cp-clients", "cp_clients__2026",
                                      load_log.LOADED, "2026-09-25T11:00:00+08:00",
                                      row_count=4)
        assert first is not None and again is None
        assert len(load_log.records()) == 1, (
            "a re-run stages every delivery again - without this the committed tree "
            "grows by one file per table per run and carries no signal at all")

    def test_a_changed_row_count_does_write(self, clean_log):
        load_log.record_load("d1", "cp-clients", "cp_clients__2026", load_log.LOADED,
                              "2026-09-25T09:00:00+08:00", row_count=4)
        load_log.record_load("d1", "cp-clients", "cp_clients__2026", load_log.LOADED,
                              "2026-09-25T11:00:00+08:00", row_count=9)
        assert len(load_log.records()) == 2
        assert load_log.latest_by_table()["cp_clients__2026"].row_count == 9

    def test_a_reprocessed_failure_still_writes_a_new_record(self, clean_log):
        """Criterion 19 is about a CHANGE of outcome, which is exactly
        what this still writes - the thing to check before putting a
        deduplicate anywhere near an append-only log."""
        load_log.record_load("d1", "cp-clients", "cp_clients__2026", load_log.FAILED,
                              "2026-09-25T09:00:00+08:00", reason="bad csv")
        load_log.record_load("d1", "cp-clients", "cp_clients__2026", load_log.LOADED,
                              "2026-09-25T11:00:00+08:00", row_count=4)
        assert len(load_log.records()) == 2
        assert load_log.loaded_tables() == frozenset({"cp_clients__2026"})
        assert [r.outcome for r in load_log.records()] == [
            load_log.FAILED, load_log.LOADED], "the failed record must survive the fix"

    def test_a_repeated_failure_writes_one_record(self, clean_log):
        for at in ("2026-09-25T09:00:00+08:00", "2026-09-25T11:00:00+08:00"):
            load_log.record_load("d1", "cp-clients", "cp_clients__2026", load_log.FAILED,
                                  at, reason="bad csv")
        assert len(load_log.records()) == 1
        assert len(load_log.failures()) == 1
