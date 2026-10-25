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

from dataclasses import dataclass

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
        deeper = root_of(conn, by_dataset, by, period, _seen=seen)
        return deeper or Root("supply", by_dataset, period, supply=by)
    return _absent_table_root(conn, dataset_id, supply, period)


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
