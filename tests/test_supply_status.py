"""A supply's status from the newest result of every check that read it -
NEWEST CAUSE WINS (REQ-PIPE-121 criterion 10)."""
from __future__ import annotations

import test_supersession as _base
from qa_tools.common import decision_log as dl, supply_status
from test_supersession import DS, TABLE, _filed

conn = _base.conn
period = _base.period


def _run(conn, key, *, instant, supply, physical, scope="arrival", cause=None, period=None):
    conn.execute(
        "INSERT INTO qa.run (run_key, agency_id, collection_id, run_timestamp, run_instant, "
        "completed_at, dataset_id, supply_id, scope, period, reads_table, caused_by_decision) "
        "VALUES (?, 'a', 'c', ?, ?, now(), ?, ?, ?, ?, ?, ?)",
        [key, instant, instant, DS, supply, scope, period,
         TABLE if scope == "readers" else None, cause])
    conn.execute("INSERT INTO qa.tables_read (run_key, logical_table, physical_table, supply) "
                 "VALUES (?, ?, ?, ?)", [key, TABLE, physical, None if scope == "arrival"
                                         else supply])


class TestNewestCauseWins:
    """post-build-review #116 D1: runs were ordered by the batch's WALL
    CLOCK for an arrival and the cause's historic instant for a decision's
    run, so in any replay a re-evaluation could never outrank the arrival
    it re-evaluated."""

    def test_an_arrival_is_ordered_by_its_receipt_not_the_batch_clock(self, conn, period):
        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        with conn.raw.transaction():
            cause = dl.record_automatic(conn, dl.Decision(
                agency_id="x", collection_id="y", dataset_id=DS,
                action=dl.PROMOTION_WITHHELD, supply=a, actor="rule", actor_kind=dl.RULE,
                effective_at="2026-05-02T01:00:00+00:00", to_slot=period, reason="r"))
        # The arrival's run was STAMPED late (a replay's wall clock) ...
        _run(conn, a_table, instant="2026-10-05T06:00:00+00:00", supply=a, physical=a_table)
        # ... and the re-evaluation, caused a day after the receipt, earlier.
        _run(conn, a_table + "__r1", instant="2026-10-05T05:00:00+00:00", supply=a,
             physical=TABLE, scope="readers", cause=cause, period=period)
        assert supply_status.runs_about(conn, DS, a) == [a_table, a_table + "__r1"]
