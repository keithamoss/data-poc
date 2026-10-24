"""A supply's status from the newest result of every check that read it -
NEWEST BY EVALUATION ORDER (REQ-PIPE-279 criterion 9), which replaced
"newest cause wins" (REQ-PIPE-121 criterion 10)."""
from __future__ import annotations

import attempt_support
import test_supersession as _base
from qa_tools.common import decision_log as dl, qa_store, supply_status
from test_supersession import DS, _filed

conn = _base.conn
period = _base.period


def _shown(conn, dataset_id: str, supply: str) -> list[dict]:
    """Every result about the supply, as results_about SHOWS it."""
    return supply_status.results_about(conn, dataset_id, supply, view=supply_status.View()).shown


def _run(conn, key, *, instant, supply, status, scope="arrival", cause=None):
    """A completed run of `supply`'s own check, opened when this is called."""
    conn.execute(
        "INSERT INTO qa.run (run_key, agency_id, collection_id, run_timestamp, run_instant, "
        "completed_at, run_by, environment, dataset_id, supply_id, scope, caused_by_decision) "
        "VALUES (?, 'a', 'c', ?, ?, now(), 't', 'test', ?, ?, ?, ?)",
        [key, instant, instant, DS, supply, scope, cause])
    qa_store.record_results(conn, key, [{"dataset_id": DS, "check_id": "x", "status": status}],
                            tool="dbt", agency_id="a", collection_id="c")
    attempt_support.opened(conn, key)


class TestTheLaterOpenedRunIsNewer:
    """REQ-PIPE-279 criterion 9 (Keith, K1 = A), A DELIBERATE CHANGE: this
    class asserted post-build-review #116 D1, that runs are ordered by the
    asset's timeline - an arrival's by its receipt, a decision's re-run by
    its effective time. That named an arrival newest over a re-check opened
    after it whenever the decision was recorded with an earlier effective
    time; the re-check is the only result that saw the decision, so it is
    the newer one. Opening order, never a time, decides."""

    def test_a_re_check_opened_after_an_arrival_is_newer_whatever_its_effective_time(
            self, conn, period):
        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        with conn.raw.transaction():
            # Recorded after the arrival's run, effective BEFORE its receipt.
            cause = dl.record_automatic(conn, dl.Decision(
                agency_id="x", collection_id="y", dataset_id=DS,
                action=dl.PROMOTION_WITHHELD, supply=a, actor="rule", actor_kind=dl.RULE,
                effective_at="2026-04-30T01:00:00+00:00", to_slot=period, reason="r"))
        _run(conn, a_table, instant="2026-10-05T06:00:00+00:00", supply=a, status="pass")
        _run(conn, a_table + "__r1", instant="2026-10-05T05:00:00+00:00", supply=a,
             status="fail", scope="full", cause=cause)
        assert [r["run_id"] for r in _shown(conn, DS, a)] == [
            a_table, a_table + "__r1"]
        assert [r["status"] for r in supply_status.latest_results(conn, DS, a)] == ["fail"]
