"""Carrying a newer supply forward, and the warning that one could be
(REQ-PIPE-271 criteria 5 to 8, REQ-PIPE-280).

A PERIOD INHERITS ONCE, WHEN IT OPENS (REQ-PIPE-098 criterion 2), and since
REQ-PIPE-271 it opens at its first filing - earlier than it used to, so the
supply it carries forward is more often overtaken: Case Workers' 2024-Q3
supply is promoted after 2024-Q4 opened standing on 2024-Q2's. Nothing
re-points the inheritance automatically (Keith, 2026-10-22, Q4 = B). The
rule WARNS instead, and a person carries the newer one forward in ONE step.

THE WARNING IS RECORDED, ITS STANDING IS DERIVED. A promotion into an earlier
period writes one `carry-forward-warning` entry per later open period it could
be carried into (criterion 6), and that entry is the audit record. Whether it
still stands is worked out from the log - the later period now carrying
forward the warned supply or a newer one, holding a supply of its own, or the
warned supply leaving its period, whichever comes first, clears it for good
(criterion 8) - so nothing has to remember to clear it, and an as-at view of
the past reads the same answer the terminal reads now.

ONE DECISION, NO GAP (REQ-PIPE-280 criteria 3 and 4). A carry-forward is one
entry naming what the period stood on before and after, and the view is
replaced inside that entry's transaction, so no committed state holds
nothing for the table. un-inherit then inherit was two decisions with a
period holding nothing in between - every reader red, the self-clearing red
Keith ruled out (plans/running-thoughts.md #113).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from qa_tools.common import decision_log, hierarchy, period_schema, schedule, supply_db

#: The rule's name on a warning it records.
RULE_ACTOR = "carry-forward rule"

#: The operation's own description, the one --help and the menus use
#: (REQ-PIPE-280 criterion 8).
DESCRIBED = ("inherit the newest promoted supply, replacing what this period carries "
             "forward (or giving it one)")


class CarryForwardRefused(decision_log.DecisionRefused):
    """A carry-forward this module will not make, in words for a person."""


@dataclass(frozen=True)
class Plan:
    """What a carry-forward would do: the period, what it stands on now and
    what it would stand on after. `already` where nothing would change."""

    dataset_id: str
    period: str
    before_supply: str | None
    before_period: str | None
    supply: str
    stands_on: str
    already: bool = False


@dataclass(frozen=True)
class Warning:
    """One recorded warning that a newer supply could be carried forward."""

    id: int
    dataset_id: str
    #: The later period, which inherits the dataset or whose inheritance was refused.
    period: str
    #: The newer supply, and the earlier period it was promoted into.
    supply: str
    promoted_into: str
    #: What the later period carried when the warning was recorded - None where nothing.
    carried: str | None
    effective_at: datetime


def _date(period: str, dataset_id: str):
    return schedule.date_of(period, dataset_id)


def _newer(period_a: str | None, period_b: str, dataset_id: str) -> bool:
    """Whether period_b's supply is newer than period_a's - by the periods'
    own dates, the order inheritance reads (inheritance._most_recent_promoted).
    Nothing (None) is older than anything."""
    if period_a is None:
        return True
    a, b = _date(period_a, dataset_id), _date(period_b, dataset_id)
    return a is not None and b is not None and b > a


# ---------------------------------------------------------------------------
# The operation (REQ-PIPE-280)
# ---------------------------------------------------------------------------

def plan(conn: supply_db.SupplyConnection, dataset_id: str, period: str) -> Plan:
    """What carrying `dataset_id` forward into `period` would do, or the
    refusal (criterion 6). Asked again under the lock by `carry_forward`, so
    what a person confirmed is what happens."""
    from qa_tools.common import inheritance

    skipped, _reason = inheritance._does_not_participate(dataset_id, period)
    if not skipped:
        raise CarryForwardRefused(
            f"{dataset_id} takes part in {period}, so it is supplied there, not carried "
            f"forward.")
    h = decision_log.held(conn, dataset_id, period)
    if h and h.held_as == decision_log.PROMOTED:
        raise CarryForwardRefused(
            f"{period} holds a {dataset_id} supply of its own, so nothing is carried "
            f"forward into it.")
    if h and h.held_as == decision_log.SUBSTITUTED:
        raise CarryForwardRefused(
            f"{period} is substituted onto {h.stands_on} for {dataset_id}, which a person "
            f"decided - de-substitute it first; nothing was carried forward.")
    newest = inheritance._most_recent_promoted(conn, dataset_id, period)
    if newest is None:
        raise CarryForwardRefused(
            f"there is no earlier promoted {dataset_id} supply to carry forward into "
            f"{period}. The table is genuinely absent, and an empty one would be a lie "
            f"with a schema on it.")
    stands_on, supply = newest
    inherited = bool(h and h.held_as == decision_log.INHERITED)
    return Plan(dataset_id=dataset_id, period=period,
                before_supply=h.holder if inherited else None,
                before_period=h.stands_on if inherited else None,
                supply=supply, stands_on=stands_on,
                already=inherited and h.holder == supply)


def already_words(p: Plan) -> str:
    """The no-op (criterion 6): 'Already so', never a refusal."""
    return (f"{p.period} already carries forward the newest promoted {p.dataset_id} "
            f"(received {received(p.dataset_id, p.supply)}). Nothing to do.")


def undo_line(p: Plan) -> str:
    """The operation's undo line (criterion 8, REQ-PIPE-128 criterion 6)."""
    if p.before_supply:
        return (f"There is no step back to the supply received "
                f"{received(p.dataset_id, p.before_supply)}; un-inherit removes what "
                f"{p.period} carries forward, and leaves its readers with no table.")
    return (f"There is no step back to carrying nothing; un-inherit removes what "
            f"{p.period} carries forward, and leaves its readers with no table.")


def carry_forward(conn: supply_db.SupplyConnection, *, dataset_id: str, period: str,
                  actor: str, reason: str, effective_at: str) -> Plan:
    """Make `period` stand on the newest promoted supply of `dataset_id` in an
    earlier period, as ONE decision (criteria 3 and 4). Returns the plan
    carried out; a plan with `already` set changed nothing.

    THE VIEW IS REPLACED, never dropped and re-made in two transactions: the
    entry and the view are one transaction, so the period never commits a
    state holding nothing for the table. The re-evaluation of its readers is
    owed by the one hook every decision passes through (decision_log's
    period-move detection, REQ-PIPE-121) - ONE, after the decision commits.
    """
    from qa_tools.common import inheritance

    if not (reason or "").strip():
        raise CarryForwardRefused(
            "a carry-forward needs a reason, on the same terms as every other filing "
            "decision a person makes.")
    if not period_schema.opened(conn, period):
        # THE ONE OPENING MECHANISM (REQ-PIPE-098 criterion 4): a period not yet
        # opened is opened first, inheriting what it owes nothing for.
        period_schema.open_period(conn, period, opened_by=actor, effective_at=effective_at)
    p = plan(conn, dataset_id, period)
    if p.already:
        return p
    entry = hierarchy.dataset(dataset_id)
    schema = period_schema.ensure_period_schema(conn, period)
    decision = decision_log.Decision(
        agency_id=entry.agency_id, collection_id=entry.collection_id,
        dataset_id=dataset_id, action=decision_log.CARRY_FORWARD, supply=p.supply,
        actor=actor, actor_kind=decision_log.PERSON, effective_at=effective_at,
        to_slot=period, stands_on=p.stands_on, replaces=p.before_supply, reason=reason)
    with decision_log.decision_transaction(conn):
        # JUDGED AGAIN UNDER THE LOCKS (#113), before the entry is written: a
        # promotion, an un-inherit or another carry-forward since the plan was
        # made refuses this one. Both slots, in a fixed order.
        for slot in sorted({period, p.stands_on} | ({p.before_period} - {None})):
            decision_log.lock_slot(conn, dataset_id, slot)
        if plan(conn, dataset_id, period) != p:
            raise CarryForwardRefused(
                f"What carrying {dataset_id} forward into {period} would do has changed "
                f"since it was worked out. Nothing was done; ask again.")
        physical = inheritance._still_stands_on(conn, dataset_id, p.stands_on, p.supply,
                                                entry.table)
        with decision_log.apply_decision(conn, decision):
            conn.execute(
                f'CREATE OR REPLACE VIEW "{schema}".'
                f'"{supply_db._ident(entry.table, "table name")}" AS SELECT * FROM '
                f'"{period_schema.period_schema(p.stands_on)}"."{physical}"')
    return p


# ---------------------------------------------------------------------------
# The warning (REQ-PIPE-271 criteria 6 to 8)
# ---------------------------------------------------------------------------

_INHERITING = (decision_log.INHERIT, decision_log.INHERIT_REFUSED, decision_log.CARRY_FORWARD)


def warn_after_promotion(conn: supply_db.SupplyConnection, *, dataset_id: str,
                         supply: str, period: str, effective_at: str,
                         promotion_id: int) -> list[int]:
    """Record a warning for every open period later than `period` that
    inherits `dataset_id` - or whose inheritance of it was refused - and
    carries something older than `supply` (criterion 6). Called inside the
    promotion's own transaction, so a promotion is never committed without
    the warnings it owes. Returns the ids written."""
    rows = conn.execute(
        f"SELECT DISTINCT to_slot FROM {decision_log.TABLE} WHERE dataset_id = ? "
        f"AND action IN ({', '.join('?' for _ in _INHERITING)}) AND to_slot IS NOT NULL",
        [dataset_id, *_INHERITING]).fetchall()
    if not rows:
        return []   # nothing inherits this dataset: the ordinary case, one query
    later = sorted(p for (p,) in rows if p != period and _newer(period, p, dataset_id))
    written: list[int] = []
    entry = hierarchy.dataset(dataset_id)
    for target in later:
        h = decision_log.held(conn, dataset_id, target)
        if h is None:
            refused = bool(conn.execute(
                f"SELECT 1 FROM {decision_log.TABLE} WHERE dataset_id = ? AND to_slot = ? "
                "AND action = ? LIMIT 1",
                [dataset_id, target, decision_log.INHERIT_REFUSED]).fetchall())
            if not refused:
                continue
            carried, carried_from = None, None
        elif h.held_as == decision_log.INHERITED:
            carried, carried_from = h.holder, h.stands_on
            if carried == supply or not _newer(carried_from, period, dataset_id):
                continue
        else:
            # Promoted, substituted, or emptied by a person: not an inheritance
            # the rule made, so nothing to warn about.
            continue
        if any(w.supply == supply for w in standing(conn, dataset_id=dataset_id,
                                                     period=target)):
            continue  # already warned, and it stands: once per supply and period
        decision = decision_log.Decision(
            agency_id=entry.agency_id, collection_id=entry.collection_id,
            dataset_id=dataset_id, action=decision_log.CARRY_FORWARD_WARNING,
            supply=supply, actor=RULE_ACTOR, actor_kind=decision_log.RULE,
            effective_at=effective_at, to_slot=target, stands_on=period,
            replaces=carried, caused_by_decision=promotion_id,
            reason=" ".join(lines(Warning(
                id=0, dataset_id=dataset_id, period=target, supply=supply,
                promoted_into=period, carried=carried,
                effective_at=_instant(effective_at)), voice="record")))
        with decision_log.apply_decision(conn, decision) as entry_id:
            written.append(entry_id)
    return written


def _instant(value) -> datetime:
    from qa_tools.common import asset_time

    return value if isinstance(value, datetime) else asset_time.parse_instant(
        value, "carry-forward warning")


def recorded(conn: supply_db.SupplyConnection, *, dataset_id: str | None = None,
             period: str | None = None) -> list[Warning]:
    """Every warning recorded, oldest first."""
    rows = conn.execute(
        f"SELECT id, dataset_id, to_slot, supply, stands_on, replaces, effective_at "
        f"FROM {decision_log.TABLE} WHERE action = ? "
        "AND (CAST(? AS text) IS NULL OR dataset_id = ?) "
        "AND (CAST(? AS text) IS NULL OR to_slot = ?) ORDER BY effective_at, id",
        [decision_log.CARRY_FORWARD_WARNING, dataset_id, dataset_id, period, period]
    ).fetchall()
    return [Warning(id=i, dataset_id=d, period=p, supply=s, promoted_into=e, carried=c,
                    effective_at=at) for i, d, p, s, e, c, at in rows]


def _cleared_as_at(conn, w: Warning, as_at) -> bool:
    """Whether a clearing condition holds as at `as_at` (criterion 8)."""
    at = as_at.isoformat() if hasattr(as_at, "isoformat") else as_at
    source = decision_log.held(conn, w.dataset_id, w.promoted_into, at)
    if not (source and source.held_as == decision_log.PROMOTED and source.holder == w.supply):
        return True   # the newer supply left its period
    target = decision_log.held(conn, w.dataset_id, w.period, at)
    if target and target.held_as == decision_log.PROMOTED:
        return True   # the later period holds a supply of its own
    if target and target.held_as == decision_log.INHERITED and (
            target.holder == w.supply
            or not _newer(target.stands_on, w.promoted_into, w.dataset_id)):
        return True   # it carries the newer supply forward, or a newer one still
    return False


def cleared_at(conn: supply_db.SupplyConnection, w: Warning):
    """The effective instant the warning stopped standing, or None where it
    still stands. ONCE CLEARED, CLEARED (criterion 8: 'SHALL NOT clear it any
    other way' read with its converse - nothing brings it back either): the
    first instant after it at which a clearing condition held."""
    rows = conn.execute(
        f"SELECT DISTINCT effective_at FROM {decision_log.TABLE} WHERE dataset_id = ? "
        "AND (to_slot IN (?, ?) OR from_slot IN (?, ?)) AND effective_at >= ? "
        "ORDER BY effective_at",
        [w.dataset_id, w.period, w.promoted_into, w.period, w.promoted_into,
         w.effective_at]).fetchall()
    for (at,) in rows:
        if _cleared_as_at(conn, w, at):
            return at
    return None


def standing(conn: supply_db.SupplyConnection | None = None, *,
             dataset_id: str | None = None, period: str | None = None,
             as_at=None) -> list[Warning]:
    """The warnings standing as at `as_at` (now where None) - ONE per dataset
    and later period, the newest warned supply (SCALE NFR), oldest period
    first. OPENS ITS OWN READ-ONLY CONNECTION when not given one, as
    inheritance.refusals() does, so outstanding.py reads it without opening
    one of its own."""
    if conn is None:
        with supply_db.connect(read_only=True,
                               label="mothman:carry-forward-warnings") as opened:
            return standing(opened, dataset_id=dataset_id, period=period, as_at=as_at)
    when = _instant(as_at) if as_at is not None else None
    best: dict[tuple[str, str], Warning] = {}
    for w in recorded(conn, dataset_id=dataset_id, period=period):
        if when is not None and w.effective_at > when:
            continue
        gone = cleared_at(conn, w)
        if gone is not None and (when is None or gone <= when):
            continue
        key = (w.dataset_id, w.period)
        current = best.get(key)
        if current is None or not _newer(w.promoted_into, current.promoted_into,
                                         w.dataset_id):
            best[key] = w
    return sorted(best.values(), key=lambda w: (w.dataset_id, w.period))


#: A period the dataset owes nothing for and which carries nothing forward for
#: it - its inheritance was refused when it opened (REQ-PIPE-098 criterion 10).
CARRIES_NOTHING = "carries-nothing-forward"


def carried_periods(conn: supply_db.SupplyConnection, dataset_id: str) -> list:
    """Every opened period this dataset owes nothing for, as the period door
    lists it (REQ-PIPE-280 criterion 1): inherited, or carrying nothing because
    its inheritance was refused. Not slots - the dataset owes nothing there -
    so the slot list never shows them, and without these the door could reach
    neither carry-forward nor un-inherit. Newest period first."""
    from qa_tools.common import slot_state

    rows = conn.execute(
        f"SELECT DISTINCT to_slot FROM {decision_log.TABLE} WHERE dataset_id = ? "
        f"AND action IN ({', '.join('?' for _ in _INHERITING)}) AND to_slot IS NOT NULL",
        [dataset_id, *_INHERITING]).fetchall()
    out = []
    for (period,) in rows:
        h = decision_log.held(conn, dataset_id, period)
        if h and h.held_as == decision_log.INHERITED:
            out.append(slot_state.SlotState(dataset_id=dataset_id, period=period,
                                            state=slot_state.INHERITED, supply=h.holder,
                                            stands_on=h.stands_on))
        elif h is None or h.held_as is None:
            out.append(slot_state.SlotState(dataset_id=dataset_id, period=period,
                                            state=CARRIES_NOTHING))
    return sorted(out, key=lambda s: s.period, reverse=True)


# ---------------------------------------------------------------------------
# Words (REQ-PIPE-271 criterion 7)
# ---------------------------------------------------------------------------

def received(dataset_id: str, supply: str | None) -> str:
    """When a supply was received, as the page and the terminal say an instant."""
    from qa_tools.common import display_time, filing

    at = filing.received_at_of(dataset_id, supply) if supply else None
    return display_time.format_instant(at) if at else "on an unrecorded date"


def command(w: Warning) -> str:
    """REQ-PIPE-280's command in full, the reason left to fill in."""
    return (f"mothman supply decide --operation carry-forward --dataset {w.dataset_id} "
            f"--period {w.period} --reason '<why>'")


def lines(w: Warning, *, voice: str = "page") -> list[str]:
    """The warning in Keith's approved wording (criterion 7): the sentences,
    then the command on a line of its own, then the door. `voice` is "page"
    (the dashboard's 'A person can ...'), "terminal" ('To carry ...') or
    "record" (the decision log's reason, which needs no lead-in)."""
    name = w.dataset_id
    if w.carried:
        lead = (f"A newer {name} could be carried forward into {w.period}. {w.period} "
                f"carries forward the supply received {received(name, w.carried)}; the one "
                f"received {received(name, w.supply)} has been promoted into "
                f"{w.promoted_into} since.")
        how = {"page": "A person can carry that one forward instead, in one step:",
               "terminal": "To carry that one forward instead, in one step:"}
    else:
        lead = (f"{w.period} carries nothing forward for {name}: there was no earlier "
                f"promoted supply when it opened. The one received "
                f"{received(name, w.supply)} has been promoted into {w.promoted_into} "
                f"since, and a person can carry it forward, in one step:")
        how = {"page": "", "terminal": ""}
        if voice == "terminal":
            lead = lead.replace(", and a person can carry it forward, in one step:", ".")
            how["terminal"] = "To carry it forward, in one step:"
    if voice == "record":
        return [lead.replace(", and a person can carry it forward, in one step:", ".")]
    out = [lead] + ([how[voice]] if how[voice] else [])
    return out + [command(w), f"or from the {w.period} door."]


# ---------------------------------------------------------------------------
# The dashboard (REQ-PIPE-271 criterion 7), from the decision log alone
# ---------------------------------------------------------------------------

def for_dashboard(dataset_id: str, conn: supply_db.SupplyConnection | None = None) -> list[dict]:
    """Every warning about this dataset, as the page needs it to show one as
    at the date on show: the later period, the asset days it stood from and
    until (`until` None while it stands), and its words - computed here, in
    Python, so the page never re-derives them.

    THE BUILD RULE (REQ-DOCS-101): recorded decisions only, never supply rows.
    """
    from qa_tools.common import asset_time

    if conn is None:
        with supply_db.connect(read_only=True, label="mothman:carry-forward") as opened:
            return for_dashboard(dataset_id, opened)
    out = []
    for w in recorded(conn, dataset_id=dataset_id):
        gone = cleared_at(conn, w)
        start = asset_time.local_date(w.effective_at).isoformat()
        until = asset_time.local_date(gone).isoformat() if gone is not None else None
        if until is not None and until <= start:
            continue  # cleared the day it was raised: never stood at a day's end
        text = lines(w, voice="page")
        out.append({"id": w.id, "period": w.period, "supply": w.supply,
                    "promotedInto": w.promoted_into, "carried": w.carried,
                    "from": start, "until": until,
                    "sentences": text[:-2], "command": text[-2], "door": text[-1]})
    return out
