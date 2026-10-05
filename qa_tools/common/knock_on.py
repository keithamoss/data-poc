"""The knock-on effects of a table arriving in or leaving a period schema
(REQ-PIPE-121) - ONE MECHANISM, whatever decision moved it.

WHAT TRIGGERS IT is SEEN, not inferred from an action: decision_log's
apply_decision compares how each of the decision's periods is held before
and after the decision, and a change is a table arriving or leaving
(criterion 8). The outermost decision transaction then owes ONE
re-evaluation per period it moved anything in, caused by the latest of its
decisions - so a displacing promotion, which writes a supersession and a
promotion, re-checks its readers once (criterion 9) - in that same
transaction (criterion 15). Nothing about a period's movement escapes
because a route forgot to call something.

WHAT IT RE-EVALUATES (criteria 1, 2 and 4): within that period only, every
cross-table check that declares it reads a moved table - reevaluation.plan(),
the one answer to "which checks read this table", shared with an arrival's
own re-evaluation - for each supply WAITING there or PROMOTED there whose own
first run has happened. Never a supply's own table and column checks.

CHEAPEST CORRECT PATH FIRST (NFR 4): a reader's tools run again only where
the latest result of one of its reading checks read the moved table as a
DIFFERENT supply than the period now holds. A reader that already read what
the period holds - the usual case right after an arrival, whose own run
re-evaluated its readers (REQ-PIPE-079 criterion 6) - is only re-gated.

THEN THE GATE (criterion 3), for each WAITING supply it touched, exactly as
for a first arrival, reading the supply's whole status: the newest result of
every check that read it (supply_status). A PROMOTED reader is never
demoted, superseded or rejected (criterion 6) - red, it is shown red
promoted (REQ-DASH-126) and nothing else happens. A waiting reader that
still fails the automatic rules is ONE shout per causing decision, naming
every such supply, at the log's highest prominence (criterion 12).

A promotion the re-gating makes is itself a period movement, so it owes its
own re-evaluation through the same hook, and recheck.run_all_owed picks it
up (criterion 11). Bounded: a supply promotes at most once.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from qa_tools.common import qa_store, supply_db


def owe(conn: supply_db.SupplyConnection, moves: list[tuple[int, str, str]]) -> list[int]:
    """Owe one re-evaluation per period this transaction moved a table in or
    out of, caused by the latest decision that did. `moves` is
    [(decision id, dataset id, period)]. Returns the owed ids."""
    from qa_tools.common import hierarchy, recheck

    by_period: dict[str, dict] = {}
    for decision_id, dataset_id, period in moves:
        try:
            table = hierarchy.dataset(dataset_id).table
        except hierarchy.UnknownDatasetError:
            continue  # a dataset this asset does not have reads nothing
        slot = by_period.setdefault(period, {"tables": set(), "decision": decision_id,
                                             "dataset": dataset_id})
        slot["tables"].add(table)
        if decision_id > slot["decision"]:
            slot["decision"], slot["dataset"] = decision_id, dataset_id
    out = []
    for period, slot in sorted(by_period.items()):
        out.append(int(conn.execute(
            f"INSERT INTO {recheck.TABLE} (kind, dataset_id, period, tables, "
            "caused_by_decision) VALUES (?, ?, ?, ?, ?) RETURNING id",
            [recheck.REEVALUATE, slot["dataset"], period, sorted(slot["tables"]),
             slot["decision"]]).fetchall()[0][0]))
    return out


@dataclass
class Reader:
    """One supply whose cross-table checks read a moved table."""
    dataset_id: str
    supply: str
    waiting: bool
    tables: set[str] = field(default_factory=set)
    #: Whether its tools must run again - its latest result for a reading
    #: check read a different supply than the period now holds.
    stale: bool = False


def _now_holds(conn, table: str, period: str) -> str | None:
    """The supply the period's `table` now reads as - promoted or
    substituted there - or None."""
    from qa_tools.common import decision_log, hierarchy

    h = decision_log.held(conn, hierarchy.dataset_for_table(table).dataset_id, period)
    # INHERITED TOO (#116, D6): an inherited period reads the earlier supply
    # through its view, so a reader of it read that supply.
    return h.holder if h and h.held_as in (decision_log.PROMOTED, decision_log.SUBSTITUTED,
                                           decision_log.INHERITED) else None


def _read_as(conn, run_key: str, table: str) -> str | None:
    """The supply a run read `table` as, from what it recorded reading."""
    from qa_tools.common import hierarchy

    rows = conn.execute(
        f'SELECT physical_table, supply FROM "{qa_store.SCHEMA}".tables_read '
        "WHERE run_key = ? AND logical_table = ?", [run_key, table]).fetchall()
    if not rows:
        return None
    physical, supply = rows[0]
    if supply:
        return supply
    parts = supply_db.split_staged(physical)
    if not parts:
        return None
    dataset_id = hierarchy.dataset_for_table(table).dataset_id
    return f"{dataset_id}@{parts[1]}" + (f"#{parts[2]}" if parts[2] else "")


def readers(conn, period: str, tables: list[str], reads: dict[str, list[str]]) -> list[Reader]:
    """Every supply in `period` whose cross-table checks read one of
    `tables`, and whether each must run again (criteria 1, 4; NFR 4)."""
    from qa_tools.common import check_id as check_id_mod
    from qa_tools.common import decision_log, reevaluation, supersession, supply_status

    found: dict[tuple[str, str], Reader] = {}
    for table in tables:
        checks = reevaluation.plan(table=table, period=period, reads=reads).check_ids
        by_dataset: dict[str, set[str]] = {}
        for cid in checks:
            parsed = check_id_mod.try_parse(cid)
            if parsed is not None:
                by_dataset.setdefault(parsed.dataset, set()).add(cid)
        holds = _now_holds(conn, table, period)
        for dataset_id, mine in sorted(by_dataset.items()):
            h = decision_log.held(conn, dataset_id, period)
            waiting = supersession.waiting_in(conn, dataset_id, period)
            supplies = [(s, True) for s in waiting]
            if h and h.held_as == decision_log.PROMOTED and h.holder not in waiting:
                supplies.append((h.holder, False))
            for supply, is_waiting in supplies:
                # A SUPPLY NOT YET RUN IS SKIPPED (criterion 4): its own first
                # run will read the period as it stands.
                if qa_store.current_run(conn, dataset_id, supply) is None:
                    continue
                reader = found.setdefault((dataset_id, supply),
                                          Reader(dataset_id, supply, is_waiting))
                reader.tables.add(table)
                latest = [r for r in supply_status.latest_results(conn, dataset_id, supply)
                          if r.get("check_id") in mine]
                if not latest or any(_read_as(conn, r["run_id"], table) != holds
                                     for r in latest):
                    reader.stale = True
    return sorted(found.values(), key=lambda r: (r.dataset_id, r.supply))


def complete(item, *, run_by: str | None = None, on_step=None):
    """Run one owed re-evaluation to the end: re-run the stale readers'
    reading checks, re-gate every waiting reader, shout once for those still
    failing, and clear it. A failure leaves it owed and reported (criterion
    14): the promotion that caused it stands, and each waiting reader keeps
    its earlier verdict."""
    from qa_tools.common import (asset_time, decision_log, hierarchy, promotion, recheck,
                                 supply_status)

    period, tables = item.period, list(item.tables or [])
    reads = promotion._declared_reads()
    with supply_db.connect(label="mothman:knock-on") as conn:
        touched = readers(conn, period, tables, reads)
    last_key = ""
    try:
        for reader in touched:
            if not reader.stale:
                continue
            with supply_db.connect(label="mothman:knock-on") as conn:
                last_key = recheck.mint_run_id(conn, reader.dataset_id, reader.supply)
            recheck.execute(
                dataset_id=reader.dataset_id, supply_id=reader.supply, run_key=last_key,
                # A READERS-ONLY RUN (REQ-PIPE-140 criterion 2): the writer keeps
                # only the reading checks of the moved tables (criterion 2) and
                # names the decision on every one (criterion 5).
                purpose={"scope": "readers", "reads_table": ",".join(sorted(reader.tables)),
                         "caused_by_decision": item.caused_by_decision},
                run_by=run_by, on_step=on_step)
    except Exception as exc:  # noqa: BLE001 - criterion 14: reported, left owed
        message = f"{type(exc).__name__}: {exc}"
        recheck.fail(item.id, message)
        return recheck.Outcome(item.id, last_key, False,
                               f"the re-evaluation of {period}'s readers did not complete "
                               f"({message}); waiting supplies keep their earlier verdicts "
                               f"and it is still owed")
    failing: list[tuple[str, str, str]] = []
    with supply_db.connect(label="mothman:knock-on") as conn:
        # AT THE INSTANT ITS CAUSE TOOK EFFECT, not when this ran: a knock-on
        # follows its decision, and a bootstrap replaying four years must not
        # stamp every re-gated promotion with today (REQ-PIPE-081).
        cause = conn.execute(f"SELECT effective_at FROM {decision_log.TABLE} WHERE id = ?",
                             [item.caused_by_decision]).fetchall()
        now = (cause[0][0].isoformat() if cause and cause[0][0]
               else asset_time.now().isoformat())
        for reader in touched:
            if not reader.waiting:
                continue  # criterion 6: a promoted reader is shown, never acted on
            ds = hierarchy.dataset(reader.dataset_id)
            results = supply_status.latest_results(conn, reader.dataset_id, reader.supply)
            key = reader.supply.rsplit("@", 1)[-1]
            physical = list(supply_db.candidates_in(
                conn, supply_db.STAGING_SCHEMA, [ds.table],
                arrival=key.split("#", 1)[0]).get(ds.table) or [])
            gated = promotion.after_run(
                conn, agency_id=ds.agency_id, collection_id=ds.collection_id,
                supplies=[{"dataset_id": reader.dataset_id, "supply": reader.supply,
                           "period": period, "physical_tables": physical,
                           "contested": "#" in key}],
                results=results, reads=reads, actor=promotion.RULE_ACTOR,
                actor_kind=decision_log.RULE, effective_at=now)
            promotion.report(gated)
            why = gated.refused.get(reader.dataset_id)
            if why and _fails_the_rules(why):
                failing.append((reader.dataset_id, reader.supply, why))
        if failing:
            _shout(conn, item, period, failing, effective_at=now)
    recheck.clear(item.id, last_key or f"knock-on/{item.id}")
    names = ", ".join(f"{d}" for d, _s, _w in failing)
    return recheck.Outcome(
        item.id, last_key, True,
        f"{period}: {len(touched)} reader(s) re-evaluated"
        + (f"; still failing: {names}" if failing else ""))


def _fails_the_rules(why: str) -> bool:
    """Whether a refusal is the supply FAILING the automatic rules - red, or
    amber under hold (criterion 12) - rather than waiting for some other
    reason (a filled slot, a person's earlier decision)."""
    from qa_tools.common import promotion

    return "status is red" in why or why == promotion.AMBER_WAITING_REASON


def _shout(conn, item, period: str, failing: list[tuple[str, str, str]], *,
           effective_at: str) -> None:
    """ONE record per causing decision naming every failing supply
    (criterion 12), with the rule as actor - `still-failing`, which the
    terminal shows at full prominence (criterion 13)."""
    from qa_tools.common import decision_log, hierarchy

    cause = conn.execute(
        f"SELECT action, dataset_id, supply FROM {decision_log.TABLE} WHERE id = ?",
        [item.caused_by_decision]).fetchall()
    action, cause_ds, cause_supply = cause[0] if cause else ("decision", item.dataset_id, "")
    try:
        cause_name = hierarchy.dataset(cause_ds).dataset_name
    except hierarchy.UnknownDatasetError:
        cause_name = cause_ds
    names = ", ".join(f"{hierarchy.dataset(d).dataset_name} ({s}: {w})" for d, s, w in failing)
    reason = (f"{action.capitalize()} of {period} {cause_name} ({cause_supply}) left "
              f"{len(failing)} waiting supply(ies) still failing the automatic rules after "
              f"re-evaluation: {names}. A person decides.")
    ds = hierarchy.dataset(failing[0][0])
    decision_log.record_automatic(conn, decision_log.Decision(
        agency_id=ds.agency_id, collection_id=ds.collection_id, dataset_id=failing[0][0],
        action=decision_log.STILL_FAILING, supply="", actor="re-evaluation rule",
        actor_kind=decision_log.RULE, effective_at=effective_at, to_slot=period,
        reason=reason, caused_by_decision=item.caused_by_decision))


def follow_up(collection_id: str, *, run_by: str | None = None, on_step=None) -> list:
    """Complete every re-evaluation this collection owes - called right after
    a batch's promotions and after a person's decision, so the knock-on is
    done while the cause is fresh. What is left owed (a failure) waits for
    the processing pass (REQ-PIPE-151). Says something only where something
    happened."""
    from qa_tools.common import recheck

    done = recheck.run_all_owed(collection_id=collection_id, kinds=(recheck.REEVALUATE,),
                                run_by=run_by, on_step=on_step)
    for outcome in done:
        if not outcome.completed or "still failing" in outcome.message or outcome.run_key:
            print(f"knock-on: {outcome.message}")
    return done
