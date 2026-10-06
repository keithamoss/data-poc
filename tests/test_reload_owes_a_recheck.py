"""A supply whose load failed, staged again and loaded, owes a re-check
(REQ-DASH-148 criterion 12): recorded in the same transaction as its new
load record, and run by the next processing pass through REQ-PIPE-140's
re-check, the reload recorded as its cause."""
from __future__ import annotations

import uuid

from qa_tools.common import load_log, qa_store, recheck, supply_db

WHEN = "2031-07-01T09:00:00+08:00"


def _physical():
    key = "".join(str(uuid.uuid4().int)[:18])
    return f"cp_carers__{key}", f"cp-carers@{key}"


def _owed_for(supply_id):
    with supply_db.connect(read_only=True, label="test-reload") as conn:
        return [o for o in recheck.owed(conn, "cp-carers") if o.supply_id == supply_id]


class TestAReloadAfterAFailureOwesARecheck:

    def test_the_load_that_follows_a_failure_owes_one_naming_itself(self, supply_dsn):
        physical, supply = _physical()
        with supply_db.connect(label="test-reload") as conn:
            qa_store.ensure_schema(conn)
        load_log.record_load("d1", "cp-carers", physical, load_log.FAILED, WHEN,
                             reason="ragged row")
        assert _owed_for(supply) == [], "a failure owes nothing"
        loaded = load_log.record_load("d1", "cp-carers", physical, load_log.LOADED, WHEN,
                                      row_count=10)
        [owed] = _owed_for(supply)
        assert owed.kind == recheck.RECHECK
        assert owed.caused_by_load == loaded.id and owed.caused_by_decision is None

    def test_a_first_load_owes_nothing(self, supply_dsn):
        physical, supply = _physical()
        load_log.record_load("d2", "cp-carers", physical, load_log.LOADED, WHEN, row_count=1)
        assert _owed_for(supply) == []

    def test_a_trial_owes_nothing(self, supply_dsn):
        physical, supply = _physical()
        load_log.record_load("d3", "cp-carers", physical, load_log.FAILED, WHEN,
                             reason="x", trial="trial_x")
        load_log.record_load("d3", "cp-carers", physical, load_log.LOADED, WHEN,
                             row_count=1, trial="trial_x")
        assert _owed_for(supply) == []

    def test_it_is_owed_in_the_same_transaction_as_the_load(self, supply_dsn):
        """A load record that rolls back takes its owed re-check with it."""
        physical, supply = _physical()
        load_log.record_load("d4", "cp-carers", physical, load_log.FAILED, WHEN, reason="x")
        with supply_db.connect(label="test-reload") as conn:
            try:
                with conn.raw.transaction():
                    load_log.record_load("d4", "cp-carers", physical, load_log.LOADED, WHEN,
                                         row_count=1, conn=conn)
                    raise RuntimeError("the caller's transaction fails")
            except RuntimeError:
                pass
        assert _owed_for(supply) == []
        assert load_log.latest_for(physical).outcome == load_log.FAILED
