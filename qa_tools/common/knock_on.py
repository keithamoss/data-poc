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
the newest COUNTED result of one of its reading checks read the moved table
as a DIFFERENT supply than the period now holds, read nothing of it, or was
not evaluated for want of a table (REQ-PIPE-269 criterion 8). A reader that
already read what the period holds - the usual case right after an arrival,
whose own run re-evaluated its readers (REQ-PIPE-079 criterion 6) - is only
re-gated.

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

from qa_tools.common import replay_clock as _replay_clock
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
            "caused_by_decision, owed_at) VALUES (?, ?, ?, ?, ?, ?) RETURNING id",
            [recheck.REEVALUATE, slot["dataset"], period, sorted(slot["tables"]),
             slot["decision"], _replay_clock.now()]).fetchall()[0][0]))
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


def read_as(record: dict, table: str) -> str | None:
    """The supply a result READ `table` as, from what it recorded reading
    (qa.check_read, REQ-PIPE-279 criterion 1) - None where it read nothing of
    it, held or absent. It was the run-level qa.tables_read, matched by
    physical name, which says what the RUN read rather than the check."""
    read = (record.get("reads") or {}).get(table) or {}
    return read.get("supply_id") if read.get("state") == qa_store.READ else None


def stale_for(latest: list[dict], table: str, holds: str | None) -> bool:
    """Whether a reader's reading checks must run again (REQ-PIPE-121 NFR 4
    as REQ-PIPE-269 criterion 8 has it): where its newest COUNTED result
    read the moved table as a different supply than the period now holds,
    read nothing of it, or was not evaluated for want of a table - so a
    reader that could not read a table is re-run, not only re-gated. An
    owed check's red stand-in (supply_status.stand_in) has no result of the
    warehouse as it stands, so it is stale too."""
    from qa_tools.common import carried

    if not latest:
        return True
    for r in latest:
        if r.get("warehouse_reason") or carried.not_evaluated_reason(r):
            return True
        got = read_as(r, table)
        if got is None or got != holds:
            return True
    return False


def readers(conn, period: str, tables: list[str], reads: dict[str, list[str]]) -> list[Reader]:
    """Every supply in `period` whose cross-table checks read one of
    `tables`, and whether each must run again (criteria 1, 4; NFR 4)."""
    from qa_tools.common import decision_log, recheck, reevaluation, supersession, supply_status

    found: dict[tuple[str, str], Reader] = {}
    owed_rechecks: dict[str, set[str]] = {}
    for table in tables:
        checks = reevaluation.reading_checks(table=table, period=period, reads=reads)
        by_dataset: dict[str, set[str]] = {}
        for cid in checks:
            for dataset_id in reevaluation.counts_toward(cid, table=table, reads=reads):
                by_dataset.setdefault(dataset_id, set()).add(cid)
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
                # NOR ONE OWED ITS FULL RE-CHECK (post-build-review #173, L3):
                # re-filed or settled, its newest results are another
                # period's, and re-gating on them is how the rule would
                # promote it here unchecked. Its re-check reads the period as
                # it stands and gates it, as the first run does above.
                if supply in owed_rechecks.setdefault(dataset_id, {
                        o.supply_id for o in recheck.owed(conn, dataset_id)
                        if o.kind == recheck.RECHECK}):
                    continue
                reader = found.setdefault((dataset_id, supply),
                                          Reader(dataset_id, supply, is_waiting))
                reader.tables.add(table)
                # THIS PERIOD'S READING (post-build-review #266 S5): a reader
                # standing in several periods is stale here by what it read
                # beside this period's tables, not another's.
                latest = [r for r in supply_status.latest_results(
                              conn, dataset_id, supply,
                              view=supply_status.View(period=period))
                          if r.get("check_id") in mine]
                if stale_for(latest, table, holds):
                    reader.stale = True
    return sorted(found.values(), key=lambda r: (r.dataset_id, r.supply))


def complete(item, *, run_by: str | None = None, on_step=None):
    """Run one owed re-evaluation to the end: re-run the stale readers'
    reading checks, re-gate every waiting reader, shout once for those still
    failing, and clear it. A failure leaves it owed and reported (criterion
    14): the promotion that caused it stands, and each waiting reader keeps
    its earlier verdict."""
    from qa_tools.common import decision_log, hierarchy, promotion, recheck

    period, tables = item.period, list(item.tables or [])
    reads = promotion._declared_reads()
    with supply_db.connect(label="mothman:knock-on") as conn:
        touched = readers(conn, period, tables, reads)
        # A REFUSED READER WAITS (Keith, 2026-10-11, (f); delivery-critic on
        # (f)-(i), findings 2 and 3): its checks are not run and it is not
        # gated, and the item stays owed for it - every other reader goes on.
        from qa_tools.common import agreement_drift

        try:
            refused = agreement_drift.refusals(conn, sorted({r.dataset_id for r in touched}))
        except Exception:  # noqa: BLE001 - an unevaluable backstop refuses nothing
            refused = {}
    waiting_on = sorted({r.dataset_id for r in touched if r.dataset_id in refused})
    touched = [r for r in touched if r.dataset_id not in refused]
    # WHAT EACH WAITING READER WAS FAILING BEFORE (REQ-PIPE-278 criterion 4):
    # a failure the re-evaluation did not change gets no still-failing record.
    with supply_db.connect(read_only=True, label="mothman:knock-on") as conn:
        before = {(r.dataset_id, r.supply): _failing_checks(conn, r.dataset_id, r.supply)
                  for r in touched if r.waiting}
    last_key = ""
    stale = [r for r in touched if r.stale]
    try:
        for n, reader in enumerate(stale, 1):
            if on_step is not None:
                # WHICH RE-CHECK OF HOW MANY (REQ-PIPE-211 criterion 13), said
                # through the caller's own progress line.
                on_step(f"re-check {n} of {len(stale)} - {reader.dataset_id} for {period}")
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
        # A MISSING CHECK STOPS EVERYTHING, here as in an arrival's run
        # (REQ-PIPE-188 criterion 6; Keith, 2026-10-12, "stop everything"): it
        # is a defect in what the tools were asked for, not a run that broke,
        # so it is left owed AND it stops the batch rather than waiting for
        # the next pass to fail the same way.
        from qa_tools.common import asked_for

        if isinstance(exc, asked_for.MissingCheck):
            raise
        return recheck.Outcome(item.id, last_key, False,
                               f"the re-evaluation of {period}'s readers did not complete "
                               f"({message}); waiting supplies keep their earlier verdicts "
                               f"and it is still owed")
    failing: list[tuple[str, str, str]] = []
    with supply_db.connect(label="mothman:knock-on") as conn:
        # AS LONG AFTER ITS CAUSE AS IT REALLY RAN (decision_log.follows, the
        # one rule re-checks use too - #117 D7): live, when it ran; in a
        # bootstrap replaying four years, the cause's instant, never today
        # (REQ-PIPE-081).
        now = decision_log.follows(conn, item.caused_by_decision)
        # criterion 6: a promoted reader is shown, never acted on
        waiting = [r for r in touched if r.waiting]
        by_collection: dict[str, list[dict]] = {}
        from qa_tools.common import supply_files

        for reader in waiting:
            ds = hierarchy.dataset(reader.dataset_id)
            # ITS OWN TABLES, AND CONTESTED ONLY WHILE ITS CONTEST IS OPEN -
            # both by the one resolver (REQ-PIPE-193 criterion 13; REQ-PIPE-194
            # criterion 8), never by the `#` in its id.
            by_collection.setdefault(ds.collection_id, []).append({
                "dataset_id": reader.dataset_id, "supply": reader.supply, "period": period,
                "physical_tables": supply_files.tables_in(conn, reader.dataset_id,
                                                          reader.supply,
                                                          supply_db.STAGING_SCHEMA),
                "contested": supply_files.open_contest(
                    conn, reader.dataset_id, reader.supply) is not None})
    # THE WAITING READERS ARE RE-GATED AS ONE GATE APPLICATION (REQ-PIPE-267
    # criterion 2): the knock-on is a gate entry, so every waiting supply
    # connected to them is gated with them. Taken after the application that
    # caused this has released the period (criterion 17); held by another,
    # this stays owed for the next pass.
    from qa_tools.common import gate

    still_not_judged: list[str] = []
    outcomes: dict[tuple[str, str], str] = {}
    for collection_id, items in sorted(by_collection.items()):
        applied = gate.apply(collection_id, period, entry=gate.KNOCK_ON, checked=items,
                             effective_at=now, run_by=run_by)
        gate.report(applied)
        if applied.contended:
            return recheck.Outcome(
                item.id, last_key, False,
                f"{period}: {len(touched)} reader(s) re-evaluated; another gate holds "
                f"{period}, so they are re-gated by the next pass - still owed",
                contended=True)
        if applied.failed:
            # A FAILED APPLICATION IS NOT A COMPLETED KNOCK-ON (post-build-review
            # #274 D6): it was abandoned and promoted nothing, so the item stays
            # owed and reported (criterion 14) - its readers' packages are owed
            # their gate too (gate._owe_retry), and whichever runs first gates them.
            message = "; ".join(f"{d}: {w}" for d, w in sorted(applied.failed.items()))
            recheck.fail(item.id, message)
            return recheck.Outcome(
                item.id, last_key, False,
                f"{period}: {len(touched)} reader(s) re-evaluated; their gate did not "
                f"complete ({message}) - still owed")
        for reader in waiting:
            why = applied.refused.get(reader.dataset_id)
            if why and _fails_the_rules(why) and reader.dataset_id not in {
                    d for d, _s, _w in failing}:
                failing.append((reader.dataset_id, reader.supply, why))
            # WHAT THE RE-GATING LEFT IT AS (REQ-PIPE-276 criterion 10), in the
            # gate's own words: never 'rejected' or 'refused' for a gate outcome.
            if reader.dataset_id in applied.promoted:
                outcomes[(reader.dataset_id, reader.supply)] = "promoted by the rule"
            elif reader.dataset_id in applied.held_back:
                outcomes[(reader.dataset_id, reader.supply)] = "still held back"
            elif reader.dataset_id in applied.frozen:
                outcomes[(reader.dataset_id, reader.supply)] = (
                    "still waiting - refused by the agreement backstop")
            else:
                outcomes[(reader.dataset_id, reader.supply)] = "still waiting for a person"
        # STILL NOT JUDGED, AND THIS ITEM IS ITS RETRY (Keith, 2026-10-25,
        # answer 1a; gate._owe_not_judged): a reader whose re-run check still
        # records nothing that counts keeps this item owed - retried by the
        # next pass, never in the same one (recheck.run_all_owed), and red,
        # never a failure of the pass.
        for dataset_id, wanted in sorted(applied.not_judged.items()):
            if set(wanted) <= set(tables):
                still_not_judged.append(dataset_id)
    if failing:
        with supply_db.connect(label="mothman:knock-on") as conn:
            changed = [f for f in failing
                       if _failing_checks(conn, f[0], f[1]) != before.get((f[0], f[1]))]
            own, holding = _by_root(conn, period, changed)
            if own:
                _shout(conn, item, period, own, effective_at=now, holding=holding)
    if waiting_on:
        return recheck.Outcome(
            item.id, last_key, False,
            f"{period}: {len(touched)} reader(s) re-evaluated; still owed for "
            f"{', '.join(waiting_on)}, refused by the agreement backstop", frozen=True)
    if still_not_judged:
        return recheck.Outcome(
            item.id, last_key, False,
            f"{period}: {len(touched)} reader(s) re-evaluated; "
            f"{', '.join(still_not_judged)} still not judged - a re-checked check recorded "
            f"no result that counts, so it is held back and this stays owed for the next "
            f"pass", status="red", not_judged=True)
    recheck.clear(item.id, last_key or f"knock-on/{item.id}")
    names = ", ".join(f"{d}" for d, _s, _w in failing)
    return recheck.Outcome(
        item.id, last_key, True,
        f"{period}: {len(touched)} reader(s) re-evaluated"
        + (f"; still failing: {names}" if failing else ""),
        regated=_regated(touched, outcomes, period))


def _regated(touched, outcomes: dict, period: str) -> tuple:
    """(dataset, supply, period, status, gate result) for every reader a
    re-evaluation touched - each waiting one with what its re-gating did,
    each promoted one 'still promoted' (criterion 6: never demoted)."""
    from qa_tools.common import supply_status

    out = []
    with supply_db.connect(read_only=True, label="mothman:knock-on") as conn:
        for r in touched:
            try:
                status = supply_status.status(conn, r.dataset_id, r.supply) or "no verdict"
            except Exception:  # noqa: BLE001 - said, never a traceback
                status = "verdict could not be read"
            result = outcomes.get((r.dataset_id, r.supply)) if r.waiting else "still promoted"
            out.append((r.dataset_id, r.supply, period, status,
                        result or "still waiting for a person"))
    return tuple(out)


def _fails_the_rules(why: str) -> bool:
    """Whether a refusal is the supply FAILING the automatic rules - red, or
    amber under hold (criterion 12) - rather than waiting for some other
    reason (a filled slot, a person's earlier decision)."""
    from qa_tools.common import promotion

    return "status is red" in why or why == promotion.AMBER_WAITING_REASON


def _failing_checks(conn, dataset_id: str, supply: str) -> frozenset[str]:
    """The checks counted toward a supply that fail - its failure, as the
    still-failing rule compares it before and after a re-evaluation."""
    from qa_tools.common import promotion, supply_status

    try:
        latest = supply_status.latest_results(conn, dataset_id, supply)
    except Exception:  # noqa: BLE001 - nothing readable compares as nothing
        return frozenset()
    return frozenset(r["check_id"] for r in promotion._contributing_records(
        dataset_id, latest, promotion._declared_reads())
        if (r.get("status") or "") in ("fail", "error"))


def _by_root(conn, period: str, failing: list[tuple[str, str, str]]):
    """(the failing supplies whose red is their own, {root supply: the
    failing supplies it holds back}) - REQ-PIPE-278 criterion 4: a supply
    whose failing checks are all another table's doing is named in its
    ROOT CAUSE's record, never given one of its own."""
    from qa_tools.common import root_cause

    own, holding = [], {}
    for f in failing:
        root = root_cause.root_of(conn, f[0], f[1], period)
        if root is None:
            own.append(f)
        else:
            holding.setdefault(root.supply or root.key, []).append(f)
    return own, holding


def _shout(conn, item, period: str, failing: list[tuple[str, str, str]], *,
           effective_at: str, holding: dict | None = None) -> None:
    """ONE record per causing decision and ROOT CAUSE naming every failing
    supply it holds back (criterion 12; REQ-PIPE-278 criterion 4), with the
    rule as actor - `still-failing`, which the terminal shows at full
    prominence (criterion 13)."""
    from qa_tools.common import decision_log, hierarchy

    cause = conn.execute(
        f"SELECT action, dataset_id, supply FROM {decision_log.TABLE} WHERE id = ?",
        [item.caused_by_decision]).fetchall()
    action, cause_ds, cause_supply = cause[0] if cause else ("decision", item.dataset_id, "")
    try:
        cause_name = hierarchy.dataset(cause_ds).dataset_name
    except hierarchy.UnknownDatasetError:
        cause_name = cause_ds
    def held(supply: str) -> str:
        found = (holding or {}).get(supply) or []
        return ("; it holds back " + ", ".join(
            f"{hierarchy.dataset(d).dataset_name} ({s})" for d, s, _w in found)) if found else ""

    names = ", ".join(f"{hierarchy.dataset(d).dataset_name} ({s}: {w}{held(s)})"
                      for d, s, w in failing)
    reason = (f"{action.capitalize()} of {period} {cause_name} ({cause_supply}) left "
              f"{len(failing)} waiting supply(ies) still failing the automatic rules after "
              f"re-evaluation: {names}. A person decides.")
    ds = hierarchy.dataset(failing[0][0])
    decision_log.record_automatic(conn, decision_log.Decision(
        agency_id=ds.agency_id, collection_id=ds.collection_id, dataset_id=failing[0][0],
        action=decision_log.STILL_FAILING, supply="", actor="re-evaluation rule",
        actor_kind=decision_log.RULE, effective_at=effective_at, to_slot=period,
        reason=reason, caused_by_decision=item.caused_by_decision))


def follow_up_stream(collection_id: str, *, run_by: str | None = None, on_step=None) -> list:
    """`follow_up` for every collection sharing a calendar with this one
    (post-build-review #251): a promotion that opens a period makes every
    owe-nothing dataset on that calendar inherit, so the re-evaluations it
    owes can belong to another collection. The streams a bootstrap replays
    together are exactly these (REQ-PIPE-262), so they are asked rather
    than worked out again."""
    from qa_tools import collections
    from qa_tools.common import bootstrap

    short = collections.by_id(collection_id).short
    stream = next(s for s in bootstrap.streams([c.short for c in collections.all_collections()])
                  if short in s)
    done = []
    for name in stream:
        done += follow_up(collections.by_short(name).id, run_by=run_by, on_step=on_step)
    return done


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
