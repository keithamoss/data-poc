"""A supply's status from the newest result of every check that READ it -
one function (REQ-PIPE-121 NFR 4, shared with REQ-DASH-126 and the status
REQ-PIPE-130 criterion 11 records at promotion).

WHICH RESULTS ARE ABOUT A SUPPLY is answered from what each run READ, not
from whose run it was. A cross-table check of cp-placements recorded in
the run of a carers arrival is a verdict about the placements supply that
run read (`qa.tables_read`), and it belongs in that supply's status just
as the supply's own checks do. Reading only the supply's own runs would
leave out exactly the refreshed cross-table result REQ-DASH-126 is about.

NEWEST CAUSE WINS (REQ-PIPE-121 criterion 10): where two runs recorded a
result for one check, the one whose cause took effect later is current -
a decision-triggered run by its decision's effective time, an arrival's by
its own run instant - never whichever run happened to finish last.

READ-ONLY, and only recorded QA results - never a supply row. So it is
safe on the dashboard build's path as well as the gate's.
"""
from __future__ import annotations

from qa_tools.common import qa_store, supply_db


def physical_of(dataset_id: str, supply: str) -> str:
    """The staged table name a supply arrived as - also its first run id.
    A supply named by its table already (a hand-staged one) is its own."""
    from qa_tools.common import recheck

    if "@" not in supply:
        return supply
    return recheck.first_run_id(dataset_id, supply)


def runs_about(conn, dataset_id: str, supply: str) -> list[str]:
    """Every completed run that read this supply's table AS this supply,
    oldest cause first."""
    from qa_tools.common import hierarchy

    table = hierarchy.dataset(dataset_id).table
    # ON THE ASSET'S OWN TIMELINE (post-build-review #116, D1): a run
    # caused by a decision is ordered by when the decision took effect, an
    # arrival's run by when ITS supply was received - never by the batch's
    # wall clock, which a replay stamps years after either, so a
    # re-evaluation could never outrank the arrival it re-evaluated.
    rows = conn.execute(
        f'SELECT r.run_key, COALESCE(d.effective_at, rc.received_instant, r.run_instant) '
        f'AS caused_at FROM "{qa_store.SCHEMA}".run_visible r '
        f'JOIN "{qa_store.SCHEMA}".tables_read t ON t.run_key = r.run_key '
        f'LEFT JOIN "{qa_store.SCHEMA}".decision d ON d.id = r.caused_by_decision '
        f'LEFT JOIN "{qa_store.SCHEMA}".supply_receipt rc '
        "ON rc.dataset_id = r.dataset_id AND rc.supply_id = r.supply_id "
        "WHERE t.logical_table = ? AND (t.supply = ? OR (t.supply IS NULL "
        "AND t.physical_table = ?)) ORDER BY caused_at, r.run_key",
        [table, supply, physical_of(dataset_id, supply)]).fetchall()
    return [r[0] for r in rows]


def latest_results(conn, dataset_id: str, supply: str) -> list[dict]:
    """The newest recorded result per check, across every run about this
    supply. Includes other datasets' results; status() keeps only what
    contributes to this dataset."""
    from qa_tools.common import qa_results_reader as reader

    latest: dict[str, dict] = {}
    for run_key in runs_about(conn, dataset_id, supply):
        cursor = conn.execute(
            f'SELECT * FROM "{qa_store.SCHEMA}".check_result_visible WHERE run_key = ? '
            "AND supply_state = ? ORDER BY id", [run_key, qa_store.AGREED])
        for record in reader._records(cursor, run_key):
            latest[record["check_id"]] = record
    return list(latest.values())


def status(conn: supply_db.SupplyConnection, dataset_id: str, supply: str, *,
           reads: dict[str, list[str]] | None = None) -> str | None:
    """green/amber/red (or a quiet status) from the newest result of every
    check contributing to this dataset that read this supply; None where
    nothing did."""
    from qa_tools.common import promotion

    reads = reads if reads is not None else promotion._declared_reads()
    return promotion.status_of(dataset_id, latest_results(conn, dataset_id, supply),
                               reads=reads)
