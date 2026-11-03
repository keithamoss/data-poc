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
supply_status's newest-result-per-check over supply_status.results_about, the
later-opened run winning (REQ-PIPE-279 criteria 9 and 21) - never a second
derivation. RECORDED QA RESULTS AND THE DECISION LOG ONLY, never a supply
row, so it is safe on the build's path.
"""
from __future__ import annotations

from qa_tools.common import decision_log, qa_store, supply_db


def _cause(conn, run_key: str) -> tuple[str, str]:
    """(instant, words) for what caused a run - an arrival, or the decision
    a re-evaluation followed (criterion 2).

    DATED BY THE RUN'S RECORDED INSTANT, whatever caused it (post-build-review
    #266 D2, Keith Q4 = A - one clock everywhere): qa.run.run_instant, the
    instant its results count from on the card (pipeline.warehouse_counts)
    and as at a past date (supply_status.recorded_by). It used to date a
    re-check by its cause's effective instant, so a re-check that failed and
    was retried days later turned the badge on the decision's day while the
    card stayed owed until the retry."""
    rows = conn.execute(
        f'SELECT r.run_instant, r.dataset_id, d.action, d.dataset_id '
        f'FROM "{qa_store.SCHEMA}".run r '
        f'LEFT JOIN "{qa_store.SCHEMA}".decision d ON d.id = r.caused_by_decision '
        "WHERE r.run_key = ?", [run_key]).fetchall()
    if not rows:
        return "", ""
    run_at, run_ds, action, cause_ds = rows[0]
    at = run_at.isoformat() if run_at else ""
    if action:
        return at, f"the {action} of {_name(cause_ds)}"
    return at, f"the arrival of {_name(run_ds)}"


def _cause_fields(conn, run_key: str, periods: dict) -> dict:
    """The structured half of a run's cause (REQ-DASH-337 criterion 11):
    {causeAction, causeDataset, causePeriod} - what the page names a cause by,
    '<collection>' <period> <dataset>' where the dataset is another
    collection's. Beside _cause's words, which stay as they were. Empty where
    the run is not recorded."""
    rows = conn.execute(
        f'SELECT r.dataset_id, r.supply_id, d.action, d.dataset_id, d.supply '
        f'FROM "{qa_store.SCHEMA}".run r '
        f'LEFT JOIN "{qa_store.SCHEMA}".decision d ON d.id = r.caused_by_decision '
        "WHERE r.run_key = ?", [run_key]).fetchall()
    if not rows:
        return {}
    run_ds, run_supply, action, cause_ds, cause_supply = rows[0]
    ds, supply = (cause_ds, cause_supply) if action else (run_ds, run_supply)
    if not ds:
        return {}
    return {"causeAction": action or "arrival", "causeDataset": ds,
            "causePeriod": _period_of(ds, supply, periods)}


def _period_of(dataset_id: str, supply: str | None, periods: dict) -> str | None:
    """The period a supply was filed to, from the filings - read once per
    dataset into `periods`. None where it was filed nowhere."""
    if not supply:
        return None
    if dataset_id not in periods:
        from qa_tools.common import filing

        try:
            periods[dataset_id] = {r.get("supply_id"): r.get("slot")
                                   for r in filing.filings_of(dataset_id)}
        except Exception:  # noqa: BLE001 - a period is decoration, never a failure
            periods[dataset_id] = {}
    return periods[dataset_id].get(supply)


def _by(conn, run_key: str) -> str | None:
    """The PERSON whose decision caused a run, by display name - None for the
    rule's or an arrival (REQ-DASH-272 criterion 3) - beside _cause's words,
    which every other reader words as they were."""
    from qa_tools.common import people

    rows = conn.execute(
        f'SELECT d.actor, d.actor_kind FROM "{qa_store.SCHEMA}".run r '
        f'JOIN "{qa_store.SCHEMA}".decision d ON d.id = r.caused_by_decision '
        "WHERE r.run_key = ?", [run_key]).fetchall()
    if not rows or rows[0][1] != decision_log.PERSON or not rows[0][0]:
        return None
    shown = people.display_name(rows[0][0])
    return "a person" if not shown or "@" in shown else shown


def for_dataset(dataset_id: str, conn=None) -> dict[str, dict]:
    """{run id: {promotedOn, promotedAt, timeline: [{at, status, cause}]}} for
    every supply of this dataset that was ever promoted, keyed by the run
    that checked it (the page knows runs). `timeline` holds the supply's
    status after each run that read it AND after each decision that changed
    what the warehouse holds beside it, where it changed, oldest first.

    COUNTED AS AT EACH STEP (REQ-PIPE-269 criteria 1 to 7, 9): a step's
    status is supply_status.count over the results recorded by then, in the
    warehouse as the decision log had it then - so a held-back partner's red
    never colours a supply it read, and a verdict about a partner that has
    since left stops counting the moment it leaves."""
    if conn is None:
        with supply_db.connect(read_only=True, label="mothman:red-promoted") as opened:
            return for_dataset(dataset_id, conn=opened)
    from pipeline import slot_timeline
    from qa_tools.common import hierarchy, promotion, supply_status

    reads = promotion._declared_reads()
    # The hierarchy's table index, read once for the dataset and given to
    # every supply's lookups (REQ-PIPE-254 criterion 19; post-build-review
    # #282 - it was read once per supply).
    known = hierarchy.by_table()
    out: dict[str, dict] = {}
    timelines: dict[str, list[dict]] = {}
    warehouses: dict[frozenset, supply_status.HoldingsTimeline] = {}
    owed = None
    periods: dict = {}
    for supply, promoted_on, promoted_at in conn.execute(
            f"SELECT DISTINCT ON (supply) supply, promoted_status, effective_at "
            f"FROM {decision_log.TABLE} WHERE dataset_id = ? AND action = ? "
            "ORDER BY supply, effective_at DESC, id DESC",
            [dataset_id, decision_log.PROMOTE]).fetchall():
        run = slot_timeline._run_for(conn, dataset_id, supply)
        if not run:
            continue
        # THE GATE'S OWN ANSWER (REQ-PIPE-279 criterion 21): the results about
        # this supply, in the order their runs were opened.
        shown = supply_status.results_about(conn, dataset_id, supply,
                                            view=supply_status.View()).shown
        involved = {dataset_id, *(d for r in shown for d in (
            supply_status.dataset_of(t, known) for t in (r.get("reads") or {})) if d)}
        for ds in involved:
            if ds not in timelines:
                timelines[ds] = slot_timeline.for_dataset(ds, conn=conn)
        tables = frozenset(involved)
        if tables not in warehouses:  # one per set of tables, shared by its supplies
            warehouses[tables] = supply_status.HoldingsTimeline(
                {ds: timelines[ds] for ds in involved})
        warehouse = warehouses[tables]
        if owed is None:
            owed = supply_status.owing(conn)
        # EACH STEP: a run that recorded a result about it, at its cause's
        # instant, and a decision that changed what a period beside it holds.
        # A STEP PER RUN, NOT PER INSTANT (post-build-review #266): a zip's
        # runs share their receipt's instant, and keying a step by the
        # instant alone gave every one of them the first run's cause. Runs at
        # one instant step in the order they were opened (shown's order), and
        # a decision at that instant after them.
        steps: dict = {}
        place: dict[str, tuple] = {}
        last = len(shown)
        for order, record in enumerate(shown):
            run_key = record["run_id"]
            if run_key not in place:
                at, cause = _cause(conn, run_key)
                by = _by(conn, run_key)
                when = supply_status.instant(at) if at else None
                place[run_key] = (when, order) if when is not None else None
                if when is not None:
                    steps[(when, order)] = (at, cause, by, _cause_fields(conn, run_key, periods))
        for ds in sorted(involved):
            name = _name(ds)  # once per dataset, not per entry (REQ-PIPE-254 criterion 19)
            for entry in timelines[ds]:
                when = supply_status.instant(entry["at"])
                steps.setdefault((when, last), (entry["at"], f"the {entry['action']} of {name}",
                                                _person(entry),
                                                {"causeAction": entry["action"], "causeDataset": ds,
                                                 "causePeriod": entry.get("slot")}))
        # AND WHERE AN OWED RE-CHECK CLEARS (post-build-review #266 D2): owed
        # until the run that cleared it, which need record nothing about this
        # supply - so the badge steps there as the card does.
        tables_read = {t for r in shown for t in (r.get("reads") or {})}
        for when, run_key in owed.changes(tables_read):
            if run_key:
                at, cause = _cause(conn, run_key)
                by = _by(conn, run_key)
                if at:
                    steps.setdefault((when, last), (at, cause, by,
                                                    _cause_fields(conn, run_key, periods)))
        timeline: list[dict] = []
        for step in sorted(steps):
            when = step[0]
            got = [r for r in shown if place[r["run_id"]] is None or place[r["run_id"]] <= step]
            if not got:
                continue
            counted = supply_status.count(dataset_id, supply, got,
                                          holdings=warehouse.at(when), owed=owed, at=when)
            try:
                # FOR DISPLAY, the recorded verdict - never the gate's reading
                # (post-build-review #132 A1).
                status = promotion.status_of(dataset_id, supply_status.newest_per_check(counted),
                                             reads=reads, for_gate=False)
            except promotion.UnreadableVerdictError:
                continue
            if timeline and timeline[-1]["status"] == status:
                continue
            at, cause, by, fields = steps[step]
            timeline.append({"at": at, "status": status, "cause": cause, **fields,
                             # WHO, where the cause is a person's decision
                             # (REQ-DASH-272 criterion 3) - beside the cause,
                             # which every other reader words as it was.
                             **({"by": by} if by else {})})
        out[run] = {"promotedOn": promoted_on,
                    "promotedAt": promoted_at.isoformat() if promoted_at else None,
                    "timeline": timeline}
    return out


def _person(entry: dict) -> str | None:
    """A slot timeline entry's person, by display name, or None."""
    from qa_tools.common import people

    if entry.get("actor_kind") != decision_log.PERSON or not entry.get("actor"):
        return None
    shown = people.display_name(entry["actor"])
    return "a person" if not shown or "@" in shown else shown


def _name(ds: str) -> str:
    from qa_tools.common import hierarchy

    try:
        return hierarchy.dataset(ds).dataset_name
    except Exception:  # noqa: BLE001 - a name is decoration, never a failure
        return ds or "a supply"


def status_on(health: dict, on: str) -> str | None:
    """The status in force at the end of asset day `on` - the page's own
    lookup (redPromotedBadge), here so a test can ask it of the build."""
    from qa_tools.common import asset_time

    found = None
    for step in health.get("timeline") or []:
        day = asset_time.local_date(asset_time.parse_instant(step["at"], "red promoted"))
        if day.isoformat() <= on:
            found = step["status"]
    return found
