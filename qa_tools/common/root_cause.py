"""The ROOT CAUSE of a waiting supply that is red only by another table's
doing - one function, for the tickets, the still-failing record and the pages
that name it (REQ-PIPE-278 criterion 1; shared with REQ-DASH-204, REQ-DASH-275
and REQ-PIPE-210).

A waiting supply is red by ANOTHER TABLE'S DOING where either:

  - its latest gate outcome is a hold-back caused by another supply of its
    gate application that was not promoting - a package-mate, or a waiting
    supply joined to it (REQ-PIPE-267 criterion 13's structured fields); or
  - every check failing toward it is a cross-table check that could not run
    for want of another table (REQ-PIPE-270), recorded not evaluated.

Its root is where the chain of structured causes ends: the supply whose own
failure held the others back, or the absent table's SLOT. A root since
rejected or superseded stops being the root (architect v4 S8; Keith Q10 = A),
and the held-back supply is then its own root - it needs its own decision.

A FAILED RE-CHECK IS ITS OWN FAILURE (Keith, 2026-10-25, answer 3a;
post-build-review #274 Q3): the root is the supply whose OWN check failed,
whether its package arrived together or staggered. A hold-back whose
re-check against the warehouse ran and failed - Notifications v2 against the
warehouse's Clients, re-checked only because its package-mate Clients v2 was
red - names the package-mate as its cause (criterion 13's 'promotion-
withheld'), and is its own root all the same. Only a check that could not be
checked, or whose re-check counted nothing, is another table's doing.

From recorded results and the decision log only; never supply rows.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from qa_tools.common import decision_log


@dataclass(frozen=True)
class Root:
    """Where a chain of causes ends."""
    #: 'supply' - another supply's own failure; 'slot' - an absent table.
    kind: str
    dataset_id: str
    period: str
    supply: str | None = None
    #: For a slot: why its table could not be read (REQ-PIPE-270's code).
    reason: str | None = None

    @property
    def key(self) -> str:
        """The ticket key of the root's slot (slot_state.SlotState.key)."""
        return f"{self.dataset_id}/{self.period}"


def root_of(conn, dataset_id: str, supply: str, period: str, *, _seen=None) -> Root | None:
    """The root cause of this waiting supply's red, where the red is wholly
    another table's doing - else None (its red is its own)."""
    found = trace(conn, dataset_id, supply, period, _seen=_seen)
    return found.root if found is not None else None


@dataclass(frozen=True)
class Traced:
    """A root, and how a held-back supply reaches it (REQ-PIPE-276 criterion
    6; REQ-PIPE-210 criterion 2): the supplies it traces through on the way,
    nearest first, as (dataset, supply), and how it came to be held back -
    'package-mate' where every link is a supply received with it, 'joined'
    where a link is a supply already waiting, 'slot' where the root is the
    slot of an absent table and nothing lies between."""
    root: Root
    via: tuple[tuple[str, str], ...] = ()
    came: str = "slot"


def trace(conn, dataset_id: str, supply: str, period: str, *, _seen=None) -> Traced | None:
    """root_of with the path to the root - the ONE walk of the chain of
    structured causes (REQ-PIPE-278 criterion 1), never a second: the queue
    (REQ-PIPE-210), the terminal's grouping (REQ-PIPE-276) and the tickets
    all read it."""
    seen = set(_seen or ())
    if (dataset_id, supply) in seen:
        return None
    seen.add((dataset_id, supply))
    entry = _latest_gate_entry(conn, dataset_id, supply)
    if entry is not None and entry["action"] == decision_log.PROMOTION_WITHHELD \
            and entry["held_back_by"]:
        if _failed_on_its_own(entry["held_back_detail"]):
            return None  # its re-check ran against the warehouse and failed (3a)
        by = entry["held_back_by"]
        by_dataset = by.split("@", 1)[0]
        if _turned_down(conn, by_dataset, by):
            return None  # the root was turned down or replaced: its own root now
        came = (entry["held_back_detail"] or {}).get("came") or "package-mate"
        deeper = trace(conn, by_dataset, by, period, _seen=seen)
        if deeper is None:
            return Traced(Root("supply", by_dataset, period, supply=by), (), came)
        link = "joined" if "joined" in (came, deeper.came) else "package-mate"
        return Traced(deeper.root, ((by_dataset, by),) + deeper.via,
                      link if deeper.came != "slot" else came)
    root = _absent_table_root(conn, dataset_id, supply, period)
    return Traced(root) if root is not None else None


def held_back_by(conn, dataset_id: str, supply: str) -> tuple[str, str, str] | None:
    """(dataset, supply, came) of the supply this one's latest gate outcome
    says held it back, whatever has become of that supply since - from the
    structured cause, never the reason's prose - else None."""
    entry = _latest_gate_entry(conn, dataset_id, supply)
    if entry is None or entry["action"] != decision_log.PROMOTION_WITHHELD \
            or not entry["held_back_by"]:
        return None
    by = entry["held_back_by"]
    return by.split("@", 1)[0], by, (entry["held_back_detail"] or {}).get("came") \
        or "package-mate"


def turned_down(conn, dataset_id: str, supply: str) -> bool:
    """Whether a person turned this supply down (and has not promoted it
    since), or it was superseded - the reading root_of stops a chain on."""
    return _turned_down(conn, dataset_id, supply)


def _latest_gate_entry(conn, dataset_id: str, supply: str) -> dict | None:
    rows = conn.execute(
        f"SELECT action, held_back_by, held_back_detail FROM {decision_log.TABLE} "
        "WHERE dataset_id = ? AND supply = ? AND action IN (?, ?, ?) ORDER BY id DESC LIMIT 1",
        [dataset_id, supply, decision_log.PROMOTE, decision_log.PROMOTION_WITHHELD,
         decision_log.PROMOTION_REFUSED]).fetchall()
    if not rows:
        return None
    action, by, detail = rows[0]
    return {"action": action, "held_back_by": by, "held_back_detail": detail}


def _failed_on_its_own(detail) -> bool:
    """Whether a hold-back's re-check ran against a supply in the warehouse
    and FAILED - its structured 'failed' (gate.Cause.failed) - rather than
    could not be checked or counted nothing (Keith, 2026-10-25, 3a)."""
    detail = detail or {}
    if detail.get("not_counted"):
        return False
    if "failed" in detail:
        return bool(detail["failed"])
    # Recorded before the field existed: a named supply in the warehouse.
    return any((detail.get("against") or {}).values())


def _turned_down(conn, dataset_id: str, supply: str) -> bool:
    """Rejected and not promoted since (refiling._since_unrejected, the one
    reading of an un-reject - post-build-review #274), or superseded."""
    from qa_tools.common import refiling, supersession

    rows = conn.execute(
        f"SELECT 1 FROM {decision_log.TABLE} WHERE dataset_id = ? AND supply = ? "
        "AND action = ? LIMIT 1", [dataset_id, supply, decision_log.REJECT]).fetchall()
    if rows and not refiling._since_unrejected(conn, dataset_id, supply):
        return True
    return supersession.is_superseded(conn, dataset_id, supply)


def _absent_table_root(conn, dataset_id: str, supply: str, period: str) -> Root | None:
    """Every failing check counted toward the supply could not run for want
    of ONE other table: that table's slot is the root."""
    from qa_tools.common import carried, promotion, supply_status

    try:
        latest = supply_status.latest_results(conn, dataset_id, supply)
    except Exception:  # noqa: BLE001 - nothing to name is no root
        return None
    reads = promotion._declared_reads()
    failing = [r for r in promotion._contributing_records(dataset_id, latest, reads)
               if (r.get("status") or "") in ("fail", "error")]
    if not failing:
        return None
    tables, codes = set(), set()
    for r in failing:
        if not carried.not_evaluated_reason(r) or r.get("warehouse_reason"):
            return None  # a failure of its own (or an owed re-check, its own red)
        named = r.get("unrunnable_tables") or ([r["unrunnable_table"]]
                                              if r.get("unrunnable_table") else [])
        named = named or r.get("held_tables") or []
        if not named:
            return None
        tables.update(named)
        codes.add(r.get("unrunnable_code"))
    if len(tables) != 1:
        return None
    (table,) = tables
    absent = supply_status.dataset_of(table)
    if absent is None:
        return None
    return Root("slot", absent, period, reason=sorted(c for c in codes if c)[0]
                if any(codes) else None)


def held_back_by_roots(conn, states) -> tuple[dict[str, list], set[str]]:
    """For every waiting slot whose supply is red by another table's doing:
    ({root slot key: [the states it holds back]}, {keys of those states}).
    A root that is not yet due holds them back with no ticket at all
    (criterion 3) - they are in the second set and in no root's list. So does
    a red that only an owed re-check stands behind (criterion 5).

    FOLDED ONLY INTO A ROOT THAT IS TICKETED, OR NOT YET DUE (NFR 3, NO FALSE
    QUIET; post-build-review #274 D4): a root whose slot raises nothing for
    another reason - a resupply beside a promoted supply, a period marked not
    supplied - would carry the held-back supply's 'Also held back by this'
    line into no ticket at all, and nobody would be told. Such a supply is
    ticketed on its own."""
    from qa_tools.common import slot_state

    by_key = {s.key: s for s in states}
    holding: dict[str, list] = {}
    folded: set[str] = set()
    for s in states:
        if not s.supply or s.state not in (slot_state.AWAITING_DECISION,
                                           slot_state.AMBER_WAITING):
            continue
        if red_only_owed(conn, s.dataset_id, s.supply, s.period):
            # CRITERION 5: an owed re-check or re-evaluation clears this red by
            # itself, so it raises nothing - and nothing names it.
            folded.add(s.key)
            continue
        root = root_of(conn, s.dataset_id, s.supply, s.period)
        if root is None or (root.kind == "supply" and root.supply == s.supply):
            continue
        at_root = by_key.get(root.key)
        if at_root is not None and not at_root.needs_action \
                and at_root.state != slot_state.NOT_YET_DUE:
            continue  # its root raises nothing: ticketed on its own
        folded.add(s.key)
        # A ROOT NOT YET DUE raises nothing (criterion 3): its slot is not one
        # that needs a person, so the reconciler opens no ticket for it, and
        # these are folded into nothing until it is overdue - when its own
        # ticket names them. A root slot not among `states` is one nobody owes
        # yet, the same case.
        holding.setdefault(root.key, []).append(s)
    return holding, folded


def red_only_owed(conn, dataset_id: str, supply: str, period: str) -> bool:
    """REQ-PIPE-278 criterion 5: whether this waiting supply's red is only an
    owed re-check - an uncleared item that will run again what fails it, or
    re-gate it where nothing counted fails it now - and none of its own.

    COVERED: an owed 'recheck' of the supply covers every check; an owed
    'reevaluate' of its period covers the cross-table checks reading one of
    the tables it is owed for; an owed 'gate' of its package re-gates it but
    runs nothing, so it covers only a supply nothing counted fails now. A
    failing check of its own, or one no owed item will run again, is a red
    that will not clear by itself (NFR 3, NO FALSE QUIET)."""
    from qa_tools.common import carried, gate, promotion, recheck, reevaluation, supply_status

    reads = promotion._declared_reads()
    owed = recheck.owed(conn)
    full = any(o.kind == recheck.RECHECK and o.dataset_id == dataset_id
               and o.supply_id == supply for o in owed)
    tables: set[str] = set()
    for o in owed:
        if o.kind == recheck.REEVALUATE and o.period == period:
            for t in o.tables or ():
                if any(dataset_id in reevaluation.counts_toward(c, table=t, reads=reads)
                       for c in reevaluation.reading_checks(table=t, period=period,
                                                           reads=reads)):
                    tables.add(t)
    package = gate.package_of(conn, dataset_id, supply)
    regated = package is not None and gate.owed_gate(conn, package) is not None
    if not (full or tables or regated):
        return False
    try:
        latest = supply_status.latest_results(conn, dataset_id, supply)
    except Exception:  # noqa: BLE001 - nothing readable is not a red that clears
        return False
    failing = [r for r in promotion._contributing_records(dataset_id, latest, reads)
               if (r.get("status") or "") in ("fail", "error")]
    for r in failing:
        if full:
            continue
        wanted = set(r.get("reads") or ()) | set(r.get("unrunnable_tables") or ()) \
            | set(r.get("held_tables") or ())
        if not r.get("reads") and not carried.not_evaluated_reason(r):
            return False  # a failure of its own
        if not (wanted & tables):
            return False
    return True


def also_lines(held: list) -> list[str]:
    """'Also held back by this', one line per supply, with its period -
    datasets and periods only, never rows or filenames (REQ-DASH-204 NFR 4)."""
    from qa_tools.common import display_time, hierarchy

    out = []
    for s in sorted(held, key=lambda s: (s.dataset_id, s.period)):
        try:
            name = hierarchy.dataset(s.dataset_id).dataset_name
        except hierarchy.UnknownDatasetError:
            name = s.dataset_id
        out.append(f"- {name} ({s.dataset_id}), {display_time.format_period(s.period)}")
    return out


def beside_its_own(conn, dataset_id: str, supply: str) -> str | None:
    """REQ-PIPE-278 criterion 6: a supply with a failing check of its own is
    ticketed as today, naming beside its own failure what else holds it back
    - the tables its could-not-run checks wanted - or None."""
    from qa_tools.common import carried, promotion, supply_status

    try:
        latest = supply_status.latest_results(conn, dataset_id, supply)
    except Exception:  # noqa: BLE001 - nothing to name
        return None
    reads = promotion._declared_reads()
    failing = [r for r in promotion._contributing_records(dataset_id, latest, reads)
               if (r.get("status") or "") in ("fail", "error")]
    wanted = sorted({t for r in failing if carried.not_evaluated_reason(r)
                     for t in (r.get("unrunnable_tables") or r.get("held_tables") or [])})
    own = [r for r in failing if not carried.not_evaluated_reason(r)]
    if not own or not wanted:
        return None
    return ("Also held back for want of " + ", ".join(wanted)
            + ": its cross-table checks of them could not run.")


# ---------------------------------------------------------------------------
# The queue, one row per cause (REQ-PIPE-210; REQ-PIPE-276 criteria 6, 12, 16)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Beneath:
    """A supply listed beneath its root's item rather than counted: every red
    on it is another table's doing, and that table has an item of its own."""
    state: object
    traced: Traced
    #: How its latest gate outcome words why it is held back (REQ-PIPE-276
    #: criterion 5), or None where it has none.
    reason: str | None = None


@dataclass
class QueueGroups:
    """What the terminal's queue shows, worked out once for every surface
    that shows it - the Filing decisions queue, `mothman supply queue`, and
    the dashboard's card counts (REQ-PIPE-210 criteria 7, 8 and 10)."""
    #: The rows that are a decision of their own, counted and pickable.
    rows: list = field(default_factory=list)
    #: {row key: [Beneath]} - supplies listed beneath that row's item.
    beneath: dict = field(default_factory=dict)
    #: {row key: [line]} - what else a counted row says: the root of a red
    #: that is another table's doing with nothing to sit beneath (REQ-PIPE-210
    #: criterion 9), what else holds back a supply red on its own (criterion
    #: 5), the Order B link (REQ-PIPE-276 criterion 16).
    lines: dict = field(default_factory=dict)
    #: [(package, [states])] - a delivery still being checked or gated: one
    #: quiet line, never counted, never pickable (REQ-PIPE-276 criterion 12).
    gating: list = field(default_factory=list)
    #: Keys of counted rows held back because of another supply - whose
    #: State cell says so, over 'another version waiting' (REQ-PIPE-210
    #: criterion 3).
    held: set = field(default_factory=set)

    @property
    def count(self) -> int:
        """The number of things to decide (REQ-PIPE-210 criterion 8)."""
        return len(self.rows)

    @property
    def listed_beneath(self) -> int:
        return sum(len(v) for v in self.beneath.values())


def row_key(state) -> tuple:
    return (state.dataset_id, state.period, state.supply)


def _root_matches(root: Root, state) -> bool:
    if root.kind == "supply":
        return state.dataset_id == root.dataset_id and state.supply == root.supply
    return state.dataset_id == root.dataset_id and state.period == root.period


def holdback_reason(conn, dataset_id: str, supply: str) -> str | None:
    """The latest 'promotion-withheld' entry's own words for this supply, as
    the terminal says them: where its re-check against the warehouse RAN AND
    FAILED (held_back_detail.failed), '..., re-checked against the <dataset>
    in place in the warehouse (received <instant>), failed, because ...' -
    the result said, as a rule promotion's line says 'green' (CLI UX review,
    S3). The recorded entry keeps REQ-PIPE-267 criterion 13's own wording."""
    import re

    rows = conn.execute(
        f"SELECT action, reason, held_back_detail FROM {decision_log.TABLE} "
        "WHERE dataset_id = ? AND supply = ? "
        "AND action IN (?, ?, ?) ORDER BY id DESC LIMIT 1",
        [dataset_id, supply, decision_log.PROMOTE, decision_log.PROMOTION_WITHHELD,
         decision_log.PROMOTION_REFUSED]).fetchall()
    if not rows or rows[0][0] != decision_log.PROMOTION_WITHHELD:
        return None
    reason = (rows[0][1] or "").strip() or None
    if reason and _failed_on_its_own(rows[0][2]) and ", failed, because" not in reason:
        reason = re.sub(r"(in place in the warehouse \(received [^)]*\)) because",
                        r"\1, failed, because", reason, count=1)
    return reason


def own_checks_passed(conn, dataset_id: str, supply: str) -> bool:
    """Whether every counted check of this supply's own data passed or
    warned - none read another table."""
    from qa_tools.common import promotion, supply_status

    try:
        latest = supply_status.latest_results(conn, dataset_id, supply)
    except Exception:  # noqa: BLE001 - unreadable is not 'passed'
        return False
    own = [r for r in promotion._contributing_records(dataset_id, latest,
                                                      promotion._declared_reads())
           if not r.get("reads") and not r.get("unrunnable_tables")]
    return bool(own) and all((r.get("status") or "") in ("pass", "warn") for r in own)


def failed_recheck_words(conn, dataset_id: str, supply: str) -> str | None:
    """CLI UX review S5 (PROVISIONAL, Keith Q1 = a): a counted row whose
    re-check against the warehouse failed while the supply that caused that
    re-check still waits - 'red - <check> failed against the warehouse;
    decide <dataset> (received <instant>) first'."""
    from qa_tools.common import display_time, filing, gate, supersession

    entry = _latest_gate_entry(conn, dataset_id, supply)
    if entry is None or entry["action"] != decision_log.PROMOTION_WITHHELD \
            or not entry["held_back_by"] or not _failed_on_its_own(entry["held_back_detail"]):
        return None
    by = entry["held_back_by"]
    by_ds = by.split("@", 1)[0]
    if _turned_down(conn, by_ds, by):
        return None
    from qa_tools.common import supply_files

    found = supply_files.resolve(conn, by_ds, by)
    if found is None or not found.period \
            or by not in supersession.waiting_in(conn, by_ds, found.period):
        return None
    checks = (entry["held_back_detail"] or {}).get("checks") or []
    words = gate._check_words(checks[0]) if checks else "a cross-table check"
    got = filing.received_at_of(by_ds, by, conn=conn)
    when = display_time.format_instant(got) if got else by
    return f"red - {words} failed against the warehouse; decide {by_ds} (received {when}) first"


def _overdue_words(root: Root) -> str:
    """'red because cp-clients for 2024-Q4 is overdue; its checks run again
    once one is promoted' (REQ-PIPE-210 criterion 9) - in the reason's own
    words where it is not one of the clock's two."""
    from qa_tools.common import period_schema, unrunnable

    if root.kind == "supply":
        return (f"red because {root.dataset_id}'s supply for {root.period} is held back; "
                f"its checks run again once one is promoted")
    how = {period_schema.PAST_DUE: "is overdue",
           period_schema.NOT_YET_DUE: "is not yet due"}.get(root.reason or "")
    if how is None:
        try:
            how = "is " + unrunnable.words_for(root.reason) if root.reason else "is not in place"
        except KeyError:
            how = "is not in place"
    return (f"red because {root.dataset_id} for {root.period} {how}; its checks run again "
            f"once one is promoted")


def group_queue(conn, states, *, held=()) -> QueueGroups:
    """Split the queue's states into counted rows, supplies listed beneath
    their root's item, and deliveries still being gated (REQ-PIPE-210
    criteria 1, 2, 5, 8 and 9; REQ-PIPE-276 criteria 6 and 12), through
    trace() - the one root - and never a supply row or a reason's prose.

    `held` are the queue's held rows (filing_queue.HeldRow): a held supply
    has an item of its own, so a supply held back by it sits beneath it."""
    from qa_tools.common import gate

    out = QueueGroups()
    rest = []
    for s in states:
        package = gate.being_gated(conn, s.dataset_id, s.supply) if s.supply else None
        if package is not None:
            for got in out.gating:
                if got[0] == package:
                    got[1].append(s)
                    break
            else:
                out.gating.append((package, [s]))
            continue
        rest.append(s)
    traced = {}
    for s in rest:
        if not s.supply:
            continue
        found = trace(conn, s.dataset_id, s.supply, s.period)
        if found is not None and not (found.root.kind == "supply"
                                      and found.root.supply == s.supply):
            traced[row_key(s)] = found
    roots = [s for s in rest if row_key(s) not in traced]
    held_items = list(held)
    for s in rest:
        found = traced.get(row_key(s))
        if found is None:
            out.rows.append(s)
            continue
        at = next((r for r in roots if _root_matches(found.root, r)), None)
        if at is None and found.root.kind == "supply":
            at = next((h for h in held_items if h.dataset_id == found.root.dataset_id
                       and h.supply == found.root.supply), None)
        if at is None:
            # NOTHING TO SIT BENEATH (criterion 9; Keith, 2026-10-23, E = B): an
            # ordinary counted row naming its root, never 'nothing needs
            # deciding'.
            out.rows.append(s)
            out.lines.setdefault(row_key(s), []).append(_overdue_words(found.root))
            continue
        out.beneath.setdefault(row_key(at), []).append(
            Beneath(s, found, holdback_reason(conn, s.dataset_id, s.supply)))
    for s in out.rows:
        if not s.supply:
            continue
        failed = failed_recheck_words(conn, s.dataset_id, s.supply)
        if failed:
            out.lines.setdefault(row_key(s), []).append(failed)
            out.held.add(row_key(s))
        gone = turned_down_words(conn, s.dataset_id, s.supply)
        if gone:
            # ITS OWN COUNTED ROW ONCE ITS ROOT IS TURNED DOWN OR REPLACED
            # (REQ-PIPE-210 criterion 6), worded from the decision log as it
            # stands - never a 'waiting for' that can no longer happen.
            out.lines.setdefault(row_key(s), []).append(gone)
        also = beside_its_own(conn, s.dataset_id, s.supply)
        if also:
            out.lines.setdefault(row_key(s), []).append(also)
        link = order_b_link(conn, s.dataset_id, s.supply, s.period)
        if link:
            out.lines.setdefault(row_key(s), []).append(link)
    return out


def order_b_partner(conn, dataset_id: str, supply: str, period: str):
    """REQ-PIPE-276 criterion 16 (staggered Order B red): (check, the waiting
    supply) where a cross-table check counted toward this waiting supply
    failed reading the warehouse's supply of another table, and a LATER
    result of the same check that read this supply and a WAITING supply of
    that table in its place passed - so promoting that one re-checks this
    one. From what each result recorded reading; None where there is none."""
    from qa_tools.common import hierarchy, knock_on, supersession, supply_status

    try:
        shown = supply_status.results_about(conn, dataset_id, supply,
                                            view=supply_status.View()).shown
    except Exception:  # noqa: BLE001 - nothing readable links nothing
        return None
    table = hierarchy.dataset(dataset_id).table
    by_check: dict[str, dict[str, list]] = {}
    for r in shown:
        if r.get("reads") and knock_on.read_as(r, table) == supply:
            for t in r["reads"]:
                if t != table:
                    by_check.setdefault(r["check_id"], {}).setdefault(t, []).append(r)
    for check, by_table in sorted(by_check.items()):
        for t, records in sorted(by_table.items()):
            other_ds = supply_status.dataset_of(t)
            if other_ds is None:
                continue
            holder = knock_on._now_holds(conn, t, period)
            failed = [i for i, r in enumerate(records) if holder
                      and knock_on.read_as(r, t) == holder
                      and (r.get("status") or "") in ("fail", "error")]
            if not failed:
                continue
            waiting = set(supersession.waiting_in(conn, other_ds, period))
            later = [r for r in records[failed[-1] + 1:]
                     if knock_on.read_as(r, t) in waiting
                     and (r.get("status") or "") == "pass"]
            if later:
                return check, knock_on.read_as(later[-1], t)
    return None


def order_b_link(conn, dataset_id: str, supply: str, period: str) -> str | None:
    """Criterion 16's line on the waiting supply's queue row and door: 'Client
    reference passes against the cp-notifications waiting for a decision
    (received <instant>); promoting that one re-checks this one.'"""
    from qa_tools.common import display_time, filing, gate

    found = order_b_partner(conn, dataset_id, supply, period)
    if found is None:
        return None
    check, other = found
    other_ds = other.split("@", 1)[0]
    got = filing.received_at_of(other_ds, other, conn=conn)
    when = display_time.format_instant(got) if got else other
    words = gate._check_words(check)
    words = words[:1].upper() + words[1:]
    return (f"{words} passes against the {other_ds} waiting for a decision "
            f"(received {when}); promoting that one re-checks this one.")


def turned_down_words(conn, dataset_id: str, supply: str) -> str | None:
    """REQ-PIPE-210 criterion 6 (REQ-DASH-275 criterion 6's wording): where
    the supply that held this one back has since been turned down - 'The
    <dataset> file received with it was turned down; this supply now needs
    its own decision.' - or replaced - 'The <dataset> received with it has
    been replaced by the one received <instant>; ...' - else None."""
    from qa_tools.common import display_time, filing, supersession

    by = held_back_by(conn, dataset_id, supply)
    if by is None:
        return None
    by_ds, by_supply, _came = by
    if not _turned_down(conn, by_ds, by_supply):
        return None
    newer = (supersession.superseded_by(conn, by_ds, by_supply)
             if supersession.is_superseded(conn, by_ds, by_supply) else None)
    if newer:
        got = filing.received_at_of(by_ds, newer, conn=conn)
        when = display_time.format_instant(got) if got else newer
        return (f"The {by_ds} received with it has been replaced by the one received "
                f"{when}; this supply now needs its own decision.")
    return (f"The {by_ds} file received with it was turned down; this supply now needs its "
            f"own decision.")
