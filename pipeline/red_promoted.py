"""How a PROMOTED supply is doing since, from its most recent cross-table
results - what REQ-DASH-126's "red promoted" label reads.

A promoted supply's verdict can change without anybody touching it: a
sibling arriving, or a re-evaluation after a decision (REQ-PIPE-121),
records a new result for a cross-table check that reads it. REQ-PIPE-121
criterion 6 says nothing is done about that automatically; criterion 7 says
it is SHOWN. So the build embeds, per promoted supply, the status it was
promoted on - recorded on the promotion itself (REQ-PIPE-130 criterion 11)
- and its status after each run that read it, with what caused that run,
and the page picks the one in force on the date on show (criterion 6).

ONE FUNCTION FOR THE STATUS (REQ-PIPE-121 NFR 4): each step is
supply_status's newest-result-per-check, newest cause wins - never a second
derivation. RECORDED QA RESULTS AND THE DECISION LOG ONLY, never a supply
row, so it is safe on the build's path.
"""
from __future__ import annotations

from qa_tools.common import decision_log, qa_store, supply_db


def _cause(conn, run_key: str) -> tuple[str, str]:
    """(instant, words) for what caused a run - an arrival, or the decision
    a re-evaluation followed (criterion 2)."""
    from qa_tools.common import hierarchy

    # THE ASSET'S TIMELINE, as supply_status orders runs (#116, D1): an
    # arrival's run is dated by its supply's receipt, never the batch clock.
    rows = conn.execute(
        f'SELECT COALESCE(rc.received_instant, r.run_instant), r.dataset_id, d.action, '
        f'd.dataset_id, d.effective_at FROM "{qa_store.SCHEMA}".run r '
        f'LEFT JOIN "{qa_store.SCHEMA}".decision d ON d.id = r.caused_by_decision '
        f'LEFT JOIN "{qa_store.SCHEMA}".supply_receipt rc '
        "ON rc.dataset_id = r.dataset_id AND rc.supply_id = r.supply_id "
        "WHERE r.run_key = ?", [run_key]).fetchall()
    if not rows:
        return "", ""
    run_at, run_ds, action, cause_ds, cause_at = rows[0]

    def name(ds):
        try:
            return hierarchy.dataset(ds).dataset_name
        except Exception:  # noqa: BLE001 - a name is decoration, never a failure
            return ds or "a supply"
    if action:
        return cause_at.isoformat(), f"the {action} of {name(cause_ds)}"
    return (run_at.isoformat() if run_at else ""), f"the arrival of {name(run_ds)}"


def _results_of(conn, run_key: str) -> list[dict]:
    """One run's agreed recorded results, as records."""
    from qa_tools.common import qa_results_reader as reader

    cursor = conn.execute(
        f'SELECT * FROM "{qa_store.SCHEMA}".check_result_visible WHERE run_key = ? '
        "AND supply_state = ? ORDER BY id", [run_key, qa_store.AGREED])
    return reader._records(cursor, run_key)


def for_dataset(dataset_id: str, conn=None) -> dict[str, dict]:
    """{run id: {promotedOn, promotedAt, timeline: [{at, status, cause}]}} for
    every supply of this dataset that was ever promoted, keyed by the run
    that checked it (the page knows runs). `timeline` holds the status after
    each run that read the supply, where it changed, oldest first."""
    if conn is None:
        with supply_db.connect(read_only=True, label="mothman:red-promoted") as opened:
            return for_dataset(dataset_id, conn=opened)
    from pipeline import slot_timeline
    from qa_tools.common import promotion, supply_status

    reads = promotion._declared_reads()
    out: dict[str, dict] = {}
    for supply, promoted_on, promoted_at in conn.execute(
            f"SELECT DISTINCT ON (supply) supply, promoted_status, effective_at "
            f"FROM {decision_log.TABLE} WHERE dataset_id = ? AND action = ? "
            "ORDER BY supply, effective_at DESC, id DESC",
            [dataset_id, decision_log.PROMOTE]).fetchall():
        run = slot_timeline._run_for(conn, dataset_id, supply)
        if not run:
            continue
        latest: dict[str, dict] = {}
        timeline: list[dict] = []
        for run_key in supply_status.runs_about(conn, dataset_id, supply):
            for record in _results_of(conn, run_key):
                latest[record["check_id"]] = record
            try:
                status = promotion.status_of(dataset_id, list(latest.values()), reads=reads)
            except promotion.UnreadableVerdictError:
                continue
            if timeline and timeline[-1]["status"] == status:
                continue
            at, cause = _cause(conn, run_key)
            timeline.append({"at": at, "status": status, "cause": cause})
        out[run] = {"promotedOn": promoted_on,
                    "promotedAt": promoted_at.isoformat() if promoted_at else None,
                    "timeline": timeline}
    return out
