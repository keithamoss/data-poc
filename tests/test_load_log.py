"""qa_tools/common/load_log.py - a table is loaded or it is not
(REQ-PIPE-060).

The claim under test is an ORDERING and a VISIBILITY rule, not a file
format: a record is written only after the load is durable, and a table
with no record is invisible to a check however physically present it is.
Both are tested against real records on a real temporary directory and,
where visibility is the point, a real DuckDB database - a mock would
assert that the code calls the functions it calls.
"""
from __future__ import annotations

import json

import pytest

import dbsupport

from qa_tools.common import load_log, supply_db


@pytest.fixture
def log_dir(tmp_path):
    return tmp_path / "processing_log"


def _rec(log_dir, physical, outcome=load_log.LOADED, at="2026-09-25T09:00:00+08:00",
          delivery="d1", dataset_id="cp-clients", **kw):
    return load_log.record(delivery, dataset_id, physical, outcome, at,
                            log_dir=log_dir, **kw)


class TestOnlyArrivalFacts:
    """Criteria 2 and 3."""

    def test_a_record_carries_the_delivery_the_dataset_and_when(self, log_dir):
        path = _rec(log_dir, "cp_clients__2026", row_count=9)
        written = json.loads(path.read_text())
        assert written["delivery"] == "d1"
        assert written["dataset_id"] == "cp-clients"
        assert written["physical"] == "cp_clients__2026"
        assert written["row_count"] == 9

    def test_no_period_no_slot_no_supersession(self, log_dir):
        """Criterion 3, and it is the whole point of this sprint:
        staging may not be wrong about anything, and the only way to be
        certain of that is to assert nothing it cannot observe."""
        written = json.loads(_rec(log_dir, "cp_clients__2026").read_text())
        forbidden = {"period", "slot", "supersedes", "superseded_by", "promoted"}
        assert forbidden.isdisjoint(written), (
            f"a load record asserted something arrival cannot know: "
            f"{sorted(forbidden & set(written))}")


class TestAnUnrecordedTableIsUnloaded:
    """Criteria 7 and 15."""

    def test_a_staged_table_with_no_record_is_not_a_candidate(self, tmp_path, monkeypatch, log_dir):
        # An EMPTY database on this worker's PostgreSQL, which is what a
        # fresh file used to give (REQ-TEST-095).
        dbsupport.reset_supply_db()
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
                loaded=load_log.loaded_tables(log_dir))
            assert found["cp_clients"] == []

            _rec(log_dir, physical)
            found = supply_db.candidates_in(
                conn, supply_db.STAGING_SCHEMA, ["cp_clients"],
                loaded=load_log.loaded_tables(log_dir))
            assert found["cp_clients"] == [physical]
        finally:
            conn.close()

    def test_a_failed_record_does_not_make_a_table_visible(self, log_dir):
        _rec(log_dir, "cp_clients__2026", outcome=load_log.FAILED, reason="bad csv")
        assert load_log.loaded_tables(log_dir) == frozenset()


class TestLatestWins:
    """Criterion 19."""

    def test_a_reprocess_writes_a_new_record_and_keeps_the_failed_one(self, log_dir):
        _rec(log_dir, "cp_clients__2026", outcome=load_log.FAILED,
              at="2026-09-25T09:00:00+08:00", reason="bad encoding")
        _rec(log_dir, "cp_clients__2026", outcome=load_log.LOADED,
              at="2026-09-25T11:00:00+08:00", row_count=4)

        assert len(load_log.records(log_dir)) == 2, (
            "the failed record must survive the fix - the history of what went wrong "
            "is the reason this is append-only")
        assert load_log.loaded_tables(log_dir) == frozenset({"cp_clients__2026"})
        assert load_log.failures(log_dir) == []

    def test_a_later_failure_supersedes_an_earlier_success(self, log_dir):
        _rec(log_dir, "cp_clients__2026", at="2026-09-25T09:00:00+08:00")
        _rec(log_dir, "cp_clients__2026", outcome=load_log.FAILED,
              at="2026-09-25T11:00:00+08:00", reason="reloaded and it broke")
        assert load_log.loaded_tables(log_dir) == frozenset()
        assert [r.reason for r in load_log.failures(log_dir)] == ["reloaded and it broke"]


class TestADeliveryIsProcessedOnlyInFull:
    """Criteria 8 and 16."""

    def test_a_partially_staged_delivery_is_not_processed(self, log_dir):
        _rec(log_dir, "cp_clients__2026")
        _rec(log_dir, "cp_carers__2026")
        expected = {"cp_clients__2026", "cp_carers__2026", "cp_placements__2026"}
        assert not load_log.delivery_is_processed("d1", expected, log_dir)
        _rec(log_dir, "cp_placements__2026")
        assert load_log.delivery_is_processed("d1", expected, log_dir)

    def test_another_deliverys_records_do_not_complete_this_one(self, log_dir):
        _rec(log_dir, "cp_clients__2026", delivery="d1")
        _rec(log_dir, "cp_carers__2026", delivery="d2")
        assert not load_log.delivery_is_processed(
            "d1", {"cp_clients__2026", "cp_carers__2026"}, log_dir)

    def test_a_delivery_that_staged_nothing_is_not_processed(self, log_dir):
        assert not load_log.delivery_is_processed("d1", set(), log_dir)


class TestUnreadableMeansUntrusted:
    def test_a_corrupt_record_is_skipped_rather_than_trusted(self, log_dir):
        _rec(log_dir, "cp_clients__2026")
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "broken--2026.json").write_text("{not json")
        assert load_log.loaded_tables(log_dir) == frozenset({"cp_clients__2026"})


class TestAnOutcomeIsOneOfTwoThings:
    def test_an_unknown_outcome_is_refused(self, log_dir):
        with pytest.raises(ValueError, match="load outcome"):
            _rec(log_dir, "cp_clients__2026", outcome="probably fine")


class TestAnUnchangedRestageWritesNothing:
    """record_load(), and the bound it puts on a committed tree."""

    def test_the_same_outcome_twice_writes_one_record(self, log_dir):
        first = load_log.record_load("d1", "cp-clients", "cp_clients__2026",
                                      load_log.LOADED, "2026-09-25T09:00:00+08:00",
                                      row_count=4, log_dir=log_dir)
        again = load_log.record_load("d1", "cp-clients", "cp_clients__2026",
                                      load_log.LOADED, "2026-09-25T11:00:00+08:00",
                                      row_count=4, log_dir=log_dir)
        assert first is not None and again is None
        assert len(load_log.records(log_dir)) == 1, (
            "a re-run stages every delivery again - without this the committed tree "
            "grows by one file per table per run and carries no signal at all")

    def test_a_changed_row_count_does_write(self, log_dir):
        load_log.record_load("d1", "cp-clients", "cp_clients__2026", load_log.LOADED,
                              "2026-09-25T09:00:00+08:00", row_count=4, log_dir=log_dir)
        load_log.record_load("d1", "cp-clients", "cp_clients__2026", load_log.LOADED,
                              "2026-09-25T11:00:00+08:00", row_count=9, log_dir=log_dir)
        assert len(load_log.records(log_dir)) == 2
        assert load_log.latest_by_table(log_dir)["cp_clients__2026"].row_count == 9

    def test_a_reprocessed_failure_still_writes_a_new_record(self, log_dir):
        """Criterion 19 is about a CHANGE of outcome, which is exactly
        what this still writes - the thing to check before putting a
        deduplicate anywhere near an append-only log."""
        load_log.record_load("d1", "cp-clients", "cp_clients__2026", load_log.FAILED,
                              "2026-09-25T09:00:00+08:00", reason="bad csv", log_dir=log_dir)
        load_log.record_load("d1", "cp-clients", "cp_clients__2026", load_log.LOADED,
                              "2026-09-25T11:00:00+08:00", row_count=4, log_dir=log_dir)
        assert len(load_log.records(log_dir)) == 2
        assert load_log.loaded_tables(log_dir) == frozenset({"cp_clients__2026"})
        assert [r.outcome for r in load_log.records(log_dir)] == [
            load_log.FAILED, load_log.LOADED], "the failed record must survive the fix"

    def test_a_repeated_failure_writes_one_record(self, log_dir):
        for at in ("2026-09-25T09:00:00+08:00", "2026-09-25T11:00:00+08:00"):
            load_log.record_load("d1", "cp-clients", "cp_clients__2026", load_log.FAILED,
                                  at, reason="bad csv", log_dir=log_dir)
        assert len(load_log.records(log_dir)) == 1
        assert len(load_log.failures(log_dir)) == 1
