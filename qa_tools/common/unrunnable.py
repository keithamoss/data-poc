"""A check that could not read a table says so, and says why
(REQ-PIPE-105 criterion 13; REQ-PIPE-079 criteria 4 and 14 to 16).

ABSENT IS NOT SILENT. One file is one arrival, so a run reads its
siblings from its period - and a sibling that has not arrived yet, is
contested, or was filed elsewhere has no view. Every tool now leaves a
check over such a table OUT rather than erroring or reporting a false red
(REQ-PIPE-105's latent-defect fixes). Left there, the check simply does
not appear - which reads, to the dashboard, the promotion gate and the
tickets alike, exactly like a check that passed.

So each in-scope check that could not run gets ONE RECORD PER MISSING
TABLE, and the decision about what it reads as is
`period_schema.check_readiness()`'s, which tells four situations apart
because they need opposite actions:

  - NOT YET DUE        -> nodata. Nothing is wrong; a red here is how a
                          check earns the reputation that gets red ignored.
  - OVERDUE            -> red, "overdue for the period": chase the supplier.
  - AWAITING A DECISION-> red, "a supply is staged awaiting a decision":
                          go and decide. This is criterion 13's own case -
                          red for want of a promoted table, not for
                          anything in the data.
  - anything else      -> red, the named catch-all.

WHICH CHECKS: exactly the run's scope (qa_results_writer._scope_to_run) -
its own dataset's checks, and checks declaring they read its table - so
nothing is recorded here that would be thrown away there. A HELD table is
left to held_blast_radius, which already reports it; reporting it twice
would be two reds for one cause.

THE STATE IS AS AT THE ARRIVAL, not as at "now": a bootstrap replays four
years of arrivals, and asking today's clock whether a 2023 table was
overdue would say yes to everything.
"""
from __future__ import annotations

from datetime import datetime

from qa_tools.common import check_id as check_id_mod
from qa_tools.common import period_schema, slot_state, supply_db

#: The pseudo-tool these are recorded under, beside `held`. Not in
#: EXPECTED_TOOLS, for the reason held_blast_radius.TOOL gives.
TOOL = "unrunnable"

LABEL = "Not evaluated - a table it reads is not available"

#: slot_state's vocabulary -> period_schema's absence reasons.
_STATE_TO_REASON = {
    slot_state.NOT_YET_DUE: period_schema.NOT_YET_DUE,
    slot_state.OVERDUE: period_schema.PAST_DUE,
    slot_state.NEVER_SUPPLIED: period_schema.PAST_DUE,
    slot_state.AWAITING_DECISION: period_schema.STAGED_AWAITING_DECISION,
    slot_state.RETURNED: period_schema.STAGED_AWAITING_DECISION,
}


def supply_state(conn, dataset_id: str, period: str, as_at: datetime) -> str | None:
    """Why this dataset has nothing readable for this period, as at the
    arrival - one of period_schema's reasons, or None for the catch-all.

    A dataset with no slot named for this period (it does not participate
    in it, or its schedule cannot be built) has no reason to give, and
    falls through to the catch-all rather than being guessed at.
    """
    from qa_tools.common import filing
    from qa_tools.common import slots as slots_mod

    try:
        dataset_slots = slots_mod.slots_for_dataset(
            dataset_id, until=slots_mod.claimable_until(dataset_id, as_at.date()))
    except (ValueError, KeyError, FileNotFoundError):
        return None
    slot = next((s for s in dataset_slots if s.name == period), None)
    if slot is None:
        return None
    filings = slot_state.filings_by_period(
        conn, dataset_id, [r for r in filing.filings_of(dataset_id) if r.get("slot") == period])
    state = slot_state.state_of(conn, dataset_id=dataset_id, slot=slot, now=as_at,
                                filings=filings, ever_delivered=True)
    return _STATE_TO_REASON.get(state.state)


def _refused_with(conn, run_id: str) -> frozenset[str]:
    """The logical tables whose load FAILED for this run's own arrival -
    the same arrival key as the run's own staged table."""
    parts = supply_db.split_staged(run_id)
    if not parts:
        return frozenset()
    from qa_tools.common import load_log

    try:
        failed = [r for r in load_log.latest_by_table(conn=conn).values() if not r.loaded]
    except Exception:  # noqa: BLE001 - no load record means nothing refused
        return frozenset()
    return frozenset(p[0] for p in (supply_db.split_staged(r.physical) for r in failed)
                     if p and p[1] == parts[1])


def results_for(conn, *, run_id: str, run_timestamp: str, own_table: str,
                own_dataset: str, period: str, resolution: supply_db.Resolution,
                reads: dict[str, list[str]], as_at: datetime,
                checks_by_id: dict | None = None) -> list[dict]:
    """One record per in-scope check that reads an unreadable table,
    naming the first such table."""
    from qa_tools.common import hierarchy

    missing = ((set(resolution.absent) | set(resolution.ambiguous)) - set(resolution.held)
               - set(resolution.resolved))
    if not missing or not reads:
        return []
    if own_table in resolution.ambiguous or own_table in resolution.held:
        # NOTHING UNDER THE RUN OF A SUPPLY NOBODY HAS PLACED OR CHOSEN
        # (REQ-PIPE-115 criteria 6 and 16). Its own checks are not run,
        # and a sibling's check reading its table is that sibling's run's
        # to record.
        return []
    contested_own = own_table in resolution.ambiguous
    refused = _refused_with(conn, run_id)
    wrapped = period_schema.PeriodResolution(period=period, resolution=resolution)
    states: dict[str, str] = {}
    out: list[dict] = []
    checks_by_id = checks_by_id or {}
    for check, tables in sorted(reads.items()):
        parsed = check_id_mod.try_parse(check)
        if parsed is None:
            continue
        own = parsed.dataset == own_dataset
        # THE RUN'S SCOPE, and nothing wider - see the module docstring.
        if not ((own and not contested_own) or own_table in tables):
            continue
        try:
            home = hierarchy.dataset(parsed.dataset).table
        except Exception:  # noqa: BLE001 - not one of ours, nothing to say
            continue
        # ONE RECORD PER CHECK (a run holds one result per check). A
        # check that reads a HELD table is held_blast_radius's to record,
        # so it is left out here entirely rather than explained twice -
        # found on the first bootstrap under REQ-PIPE-131, the first to
        # produce real holds. Where several of its tables are unreadable,
        # the one record names them all (criterion 2 as amended).
        if (set(tables) | {home}) & set(resolution.held):
            continue
        found = []
        for table in sorted((set(tables) | {home}) & missing):
            if table not in states and table in refused:
                # COULD NOT BE LOADED WINS THE REASON (REQ-DASH-148
                # criterion 6): it came in this arrival and failed.
                states[table] = period_schema.COULD_NOT_LOAD
            if table not in states and table in resolution.ambiguous:
                # CONTESTED WINS THE REASON (REQ-PIPE-115 criteria 14 and
                # 15): the file is here, twice, and a slot reason would
                # send somebody after a supplier who has already sent it.
                states[table] = period_schema.CONTESTED
            if table not in states:
                try:
                    dataset_id = hierarchy.dataset_for_table(table).dataset_id
                    states[table] = supply_state(conn, dataset_id, period, as_at) or ""
                except Exception:  # noqa: BLE001 - the catch-all covers it
                    states[table] = ""
            verdict = period_schema.check_readiness(
                [table], wrapped,
                supply_states={table: states[table]} if states[table] else {})
            if verdict is not None:
                found.append((table, verdict))
        if not found:
            continue
        # ONE RECORD NAMING EVERY UNREADABLE TABLE (REQ-PIPE-115 criterion
        # 2 as amended 2026-10-05, Keith) - it used to name only the first.
        # Red where any table's reason is red; no data only where every
        # one is merely not yet due.
        first_table, first = next(((t, v) for t, v in found
                                   if v.status != period_schema.NODATA), found[0])
        meta = checks_by_id.get(check)
        out.append({
            "agency_id": parsed.agency,
            "collection_id": parsed.collection,
            "dataset_id": parsed.dataset,
            "check_id": check,
            "check_name": getattr(meta, "name", None) or parsed.check_name,
            "column_name": first_table,
            "dimension": "completeness",
            "label": LABEL,
            "run_id": run_id,
            "run_timestamp": run_timestamp,
            "status": "nodata" if first.status == period_schema.NODATA else "fail",
            "metric_value": None,
            "unit": None,
            "warn_threshold": None,
            "fail_threshold": None,
            "row_count_total": None,
            "row_count_invalid": None,
            "on_fail_action": "flag",
            "engine": getattr(meta, "tool", None) or parsed.tool,
            "unrunnable_table": first_table,
            "unrunnable_tables": [t for t, _ in found],
            "unrunnable_code": first.reason,
            "unrunnable_reason": ("; ".join(v.describe() for _, v in found)
                                  + ". This check did not fail - it could not be evaluated."),
        })
    return out


def describe(results) -> str:
    """One line for the terminal, never one per result."""
    if not results:
        return ""
    by_code: dict[str, set[str]] = {}
    for r in results:
        by_code.setdefault(r["unrunnable_code"], set()).add(r["unrunnable_table"])
    parts = "; ".join(f"{code}: {', '.join(sorted(t))}" for code, t in sorted(by_code.items()))
    return (f"{len(results)} check(s) could not be evaluated for want of a table - "
            f"{parts}. None of them is a verdict on anybody's data.")
