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

from dataclasses import dataclass, replace
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
    #: What the later period carries - when the warning was recorded, or, once
    #: read through as_now(), as at the instant asked about. None where nothing.
    carried: str | None
    effective_at: datetime
    #: True where the later period carries nothing because a person emptied it
    #: (an un-inherit) - not because its inheritance was refused when it opened.
    emptied: bool = False


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


def _not_older(period_a: str | None, period_b: str, dataset_id: str) -> bool:
    """Whether period_a's supply is KNOWN to be at least as new as period_b's.
    An unknown date answers False - so a period whose date cannot be read is
    never taken to carry the newer supply forward, and never clears a warning
    by default (post-build-review #267)."""
    if period_a is None:
        return False
    a, b = _date(period_a, dataset_id), _date(period_b, dataset_id)
    return a is not None and b is not None and a >= b


def name_of(dataset_id: str) -> str:
    """A dataset BY NAME, as every sentence here says it (REQ-GHUB-142 NFR 2,
    Keith 2026-10-24 K1): ids are for commands only."""
    try:
        return hierarchy.dataset(dataset_id).dataset_name
    except hierarchy.UnknownDatasetError:
        return dataset_id


#: Said after every refusal, so nobody wonders whether half of it happened.
NOTHING_RECORDED = "Nothing was recorded."


# ---------------------------------------------------------------------------
# The operation (REQ-PIPE-280)
# ---------------------------------------------------------------------------

def plan(conn: supply_db.SupplyConnection, dataset_id: str, period: str) -> Plan:
    """What carrying `dataset_id` forward into `period` would do, or the
    refusal (criterion 6). Asked again under the lock by `carry_forward`, so
    what a person confirmed is what happens."""
    from qa_tools.common import inheritance

    name = name_of(dataset_id)
    # NOT A PERIOD AT ALL (CLI UX critic S4, #267): a typo, or a period of
    # another calendar, is said as one - never "takes part in X", which is
    # false of a period that does not exist. Shared with inherit.
    wrong = inheritance.not_a_period(dataset_id, period)
    if wrong:
        raise CarryForwardRefused(f"{wrong} {NOTHING_RECORDED}")
    skipped, _reason = inheritance._does_not_participate(dataset_id, period)
    if not skipped:
        raise CarryForwardRefused(
            f"{name} takes part in {period}, so it is supplied there, not carried "
            f"forward. {NOTHING_RECORDED}")
    if not period_schema.opened(conn, period):
        # NOT OPENED YET (functional critic D3, #267): a carry-forward re-points
        # what an opened period carries, or gives one to an opened period that
        # carries nothing. A period that has not opened carries neither, and it
        # inherits the newest promoted supply when it opens, at its first
        # filing - so there is nothing for a person to carry forward, and
        # opening it from here would be the explicit open command REQ-PIPE-098
        # criterion 4 leaves unbuilt (Keith, 2026-10-19, 'Leave until needed').
        raise CarryForwardRefused(
            f"{period} is not open yet, so there is nothing to carry forward into: it "
            f"inherits the newest promoted {name} when it opens, at its first filing. "
            f"{NOTHING_RECORDED}")
    h = decision_log.held(conn, dataset_id, period)
    if h and h.held_as == decision_log.PROMOTED:
        raise CarryForwardRefused(
            f"{period} holds a {name} supply of its own, so nothing is carried "
            f"forward into it. {NOTHING_RECORDED}")
    if h and h.held_as == decision_log.SUBSTITUTED:
        raise CarryForwardRefused(
            f"{period} is substituted onto {h.stands_on} for {name}, which a person "
            f"decided - de-substitute it first. {NOTHING_RECORDED}")
    newest = inheritance._most_recent_promoted(conn, dataset_id, period)
    if newest is None:
        raise CarryForwardRefused(
            f"there is no earlier promoted {name} supply to carry forward into "
            f"{period}. The table is genuinely absent, and an empty one would be a lie "
            f"with a schema on it. {NOTHING_RECORDED}")
    stands_on, supply = newest
    inherited = bool(h and h.held_as == decision_log.INHERITED)
    return Plan(dataset_id=dataset_id, period=period,
                before_supply=h.holder if inherited else None,
                before_period=h.stands_on if inherited else None,
                supply=supply, stands_on=stands_on,
                already=inherited and h.holder == supply)


def already_words(p: Plan) -> str:
    """The no-op (criterion 6): 'Already so', never a refusal."""
    return (f"{p.period} already carries forward the newest promoted {name_of(p.dataset_id)} "
            f"(received {received(p.dataset_id, p.supply)}). Nothing to do.")


def undo_line(p: Plan) -> str:
    """The operation's undo line (criterion 8, REQ-PIPE-128 criterion 6)."""
    if p.before_supply:
        return (f"There is no step back to the supply received "
                f"{received(p.dataset_id, p.before_supply)}; un-inherit removes what "
                f"{p.period} carries forward, and leaves its readers with no table.")
    # THE REFUSED CASE (Keith, 2026-10-24, K2): there was nothing to step back
    # to, so the line says how to carry nothing again, and what it costs.
    return "To carry nothing again, un-inherit \u2014 its readers are left with no table."


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
        table = supply_db._ident(entry.table, "table name")
        # NOTHING ELSE READS THE VIEW (functional critic D4, #267): it is
        # dropped and made again below, and a view built on it would either
        # stop the drop with a raw error or - with CASCADE - vanish unseen.
        readers = _views_reading(conn, schema, table)
        if readers:
            raise CarryForwardRefused(
                f"{', '.join(readers)} {'reads' if len(readers) == 1 else 'read'} "
                f"{period}'s {entry.table}, so what it carries forward cannot be "
                f"replaced under {'it' if len(readers) == 1 else 'them'}. "
                f"{NOTHING_RECORDED}")
        with decision_log.apply_decision(conn, decision):
            # DROPPED AND MADE AGAIN, IN THIS ONE TRANSACTION (D4): CREATE OR
            # REPLACE refuses a newer supply whose columns changed type or
            # order, and the two statements commit together, so no committed
            # state holds nothing for the table (criterion 4).
            conn.execute(f'DROP VIEW IF EXISTS "{schema}"."{table}"')
            conn.execute(
                f'CREATE VIEW "{schema}"."{table}" AS SELECT * FROM '
                f'"{period_schema.period_schema(p.stands_on)}"."{physical}"')
    return p


def _views_reading(conn, schema: str, table: str) -> list[str]:
    """Every view (schema.name) built on this period view, from the catalogue."""
    rows = conn.execute(
        "SELECT DISTINCT n.nspname || '.' || c.relname FROM pg_depend d "
        "JOIN pg_rewrite r ON r.oid = d.objid JOIN pg_class c ON c.oid = r.ev_class "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE d.refobjid = to_regclass(?) AND c.oid <> d.refobjid ORDER BY 1",
        [f'"{schema}"."{table}"']).fetchall()
    return [r[0] for r in rows]


# ---------------------------------------------------------------------------
# The warning (REQ-PIPE-271 criteria 6 to 8)
# ---------------------------------------------------------------------------

_INHERITING = (decision_log.INHERIT, decision_log.INHERIT_REFUSED, decision_log.CARRY_FORWARD)


def _record_reason(conn, w: Warning) -> str:
    """The warning's words for its own record, read through the promotion's
    own connection (functional critic S7, #267): a fresh connection per
    receipt, inside the promotion's transaction, could refuse a promotion
    over a sentence. A wording fault that is not the database's is caught and
    the ids said instead - the database's own errors are not, since the
    transaction is lost to them either way."""
    import psycopg

    try:
        return " ".join(lines(w, voice="record", conn=conn))
    except psycopg.Error:
        raise
    except Exception:  # noqa: BLE001 - see the docstring
        return (f"A newer {w.dataset_id} ({w.supply}, promoted into {w.promoted_into}) "
                f"could be carried forward into {w.period}.")


def _record_warning(conn, *, dataset_id: str, target: str, supply: str,
                    promoted_into: str, carried: str | None, effective_at: str,
                    caused_by: int) -> int | None:
    """One warning entry (criterion 6) - unless one naming this supply already
    stands for this period: once per supply and period."""
    if any(w.supply == supply for w in standing(conn, dataset_id=dataset_id,
                                                 period=target)):
        return None
    entry = hierarchy.dataset(dataset_id)
    w = Warning(id=0, dataset_id=dataset_id, period=target, supply=supply,
                promoted_into=promoted_into, carried=carried,
                effective_at=_instant(effective_at))
    decision = decision_log.Decision(
        agency_id=entry.agency_id, collection_id=entry.collection_id,
        dataset_id=dataset_id, action=decision_log.CARRY_FORWARD_WARNING,
        supply=supply, actor=RULE_ACTOR, actor_kind=decision_log.RULE,
        effective_at=effective_at, to_slot=target, stands_on=promoted_into,
        replaces=carried, caused_by_decision=caused_by, reason=_record_reason(conn, w))
    with decision_log.apply_decision(conn, decision) as entry_id:
        pass
    return entry_id


def warn_after_promotion(conn: supply_db.SupplyConnection, *, dataset_id: str,
                         supply: str, period: str, effective_at: str,
                         promotion_id: int) -> list[int]:
    """Record a warning for every open period later than `period` that
    inherits `dataset_id` - or whose inheritance of it was refused - and
    carries something older than `supply` (criterion 6). Called inside the
    promotion's own transaction, so a promotion is never committed without
    the warnings it owes. Returns the ids written.

    A SUBSTITUTED PERIOD IS NEVER WARNED (Keith, 2026-10-24, K8): a person
    chose what it stands on, so a newer supply is not one it could carry."""
    rows = conn.execute(
        f"SELECT DISTINCT to_slot FROM {decision_log.TABLE} WHERE dataset_id = ? "
        f"AND action IN ({', '.join('?' for _ in _INHERITING)}) AND to_slot IS NOT NULL",
        [dataset_id, *_INHERITING]).fetchall()
    if not rows:
        return []   # nothing inherits this dataset: the ordinary case, one query
    later = sorted(p for (p,) in rows if p != period and _newer(period, p, dataset_id))
    written: list[int] = []
    for target in later:
        h = decision_log.held(conn, dataset_id, target)
        if h is None:
            refused = bool(conn.execute(
                f"SELECT 1 FROM {decision_log.TABLE} WHERE dataset_id = ? AND to_slot = ? "
                "AND action = ? LIMIT 1",
                [dataset_id, target, decision_log.INHERIT_REFUSED]).fetchall())
            if not refused:
                continue
            carried = None
        elif h.held_as == decision_log.INHERITED:
            carried = h.holder
            if carried == supply or not _newer(h.stands_on, period, dataset_id):
                continue
        else:
            # Promoted, substituted, or emptied by a person: not an inheritance
            # the rule made, so nothing to warn about.
            continue
        made = _record_warning(conn, dataset_id=dataset_id, target=target, supply=supply,
                               promoted_into=period, carried=carried,
                               effective_at=effective_at, caused_by=promotion_id)
        if made is not None:
            written.append(made)
    return written


def warn_at_opening(conn: supply_db.SupplyConnection, *, dataset_id: str, period: str,
                    carried: tuple[str, str] | None, effective_at: str) -> int | None:
    """The ordinary warning, raised by an OPENING (Keith, 2026-10-24, K6).

    A period inherits as at the instant it opens - its first filing's
    RECEIPT - so a promotion processed before the filing but taking effect
    after that receipt is not what it carries. That promotion's own warning
    looked for later periods while this one was not yet open, so the opening
    raises it instead: naming the promotion as its cause, dated when the
    promotion took effect. `carried` is (period, supply) inherited, or None
    where the inheritance was refused. Inside the opening's transaction."""
    from qa_tools.common import inheritance

    now = inheritance._most_recent_promoted(conn, dataset_id, period)
    if now is None:
        return None
    stands_on, supply = now
    if carried is not None and (carried[1] == supply
                                or not _newer(carried[0], stands_on, dataset_id)):
        return None
    h = decision_log.held(conn, dataset_id, stands_on)
    row = conn.execute(f"SELECT effective_at FROM {decision_log.TABLE} WHERE id = ?",
                       [h.decision_id]).fetchone()
    at = _instant(effective_at)
    if row and _instant(row[0]) > at:
        at = _instant(row[0])
    return _record_warning(conn, dataset_id=dataset_id, target=period, supply=supply,
                           promoted_into=stands_on,
                           carried=carried[1] if carried else None,
                           effective_at=at.isoformat(), caused_by=h.decision_id)


def _instant(value) -> datetime:
    from qa_tools.common import asset_time

    return value if isinstance(value, datetime) else asset_time.parse_instant(
        value, "carry-forward warning")


def _iso(value) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else value


def recorded(conn: supply_db.SupplyConnection, *, dataset_id: str | None = None,
             period: str | None = None) -> list[Warning]:
    """Every warning recorded, oldest first, as it was recorded."""
    rows = conn.execute(
        f"SELECT id, dataset_id, to_slot, supply, stands_on, replaces, effective_at "
        f"FROM {decision_log.TABLE} WHERE action = ? "
        "AND (CAST(? AS text) IS NULL OR dataset_id = ?) "
        "AND (CAST(? AS text) IS NULL OR to_slot = ?) ORDER BY effective_at, id",
        [decision_log.CARRY_FORWARD_WARNING, dataset_id, dataset_id, period, period]
    ).fetchall()
    return [Warning(id=i, dataset_id=d, period=p, supply=s, promoted_into=e, carried=c,
                    effective_at=at) for i, d, p, s, e, c, at in rows]


def as_now(conn: supply_db.SupplyConnection, w: Warning, as_at=None) -> Warning:
    """The warning as the later period stands AS AT `as_at` (now where None) -
    what it carries then, not what it carried when the warning was raised
    (Keith, 2026-10-24, K5; functional critic D2): an un-inherit since leaves
    it carrying nothing, and the words must say so."""
    h = decision_log.held(conn, w.dataset_id, w.period, _iso(as_at))
    if h is None:
        return replace(w, carried=None, emptied=False)   # refused at opening, never held
    if h.held_as == decision_log.INHERITED:
        return replace(w, carried=h.holder, emptied=False)
    if h.held_as is None:
        return replace(w, carried=None, emptied=True)    # a person emptied it
    return w


def _cleared_as_at(conn, w: Warning, as_at) -> bool:
    """Whether a clearing condition holds as at `as_at` (criterion 8)."""
    at = _iso(as_at)
    source = decision_log.held(conn, w.dataset_id, w.promoted_into, at)
    if not (source and source.held_as == decision_log.PROMOTED and source.holder == w.supply):
        return True   # the newer supply left its period
    target = decision_log.held(conn, w.dataset_id, w.period, at)
    if target and target.held_as in (decision_log.PROMOTED, decision_log.SUBSTITUTED):
        # A supply of its own - or a SUBSTITUTION, which a person chose
        # (Keith, 2026-10-24, K8, amending criterion 8's list).
        return True
    if target and target.held_as == decision_log.INHERITED and (
            target.holder == w.supply
            or _not_older(target.stands_on, w.promoted_into, w.dataset_id)):
        return True   # it carries the newer supply forward, or one KNOWN to be newer still
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
    first - each read as the later period stands then (as_now). OPENS ITS OWN
    READ-ONLY CONNECTION when not given one, as inheritance.refusals() does,
    so outstanding.py reads it without opening one of its own."""
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
    return sorted((as_now(conn, w, as_at) for w in best.values()),
                  key=lambda w: (w.dataset_id, w.period))


def raised_by_promotion(conn: supply_db.SupplyConnection, *, dataset_id: str, supply: str,
                        period: str) -> list[str]:
    """The later periods the newest promotion of `supply` into `period` raised
    a warning for, oldest first - what that promotion made available to carry
    forward (Keith, 2026-10-24, K4)."""
    rows = conn.execute(
        f"SELECT DISTINCT w.to_slot FROM {decision_log.TABLE} w WHERE w.action = ? "
        f"AND w.caused_by_decision = (SELECT max(id) FROM {decision_log.TABLE} "
        "WHERE dataset_id = ? AND action = ? AND supply = ? AND to_slot = ?) "
        "ORDER BY w.to_slot",
        [decision_log.CARRY_FORWARD_WARNING, dataset_id, decision_log.PROMOTE, supply,
         period]).fetchall()
    return [r[0] for r in rows]


def made_available(dataset_id: str, periods: list[str]) -> str | None:
    """The line a promotion that raised warnings adds to what it says (K4):
    which periods it could now be carried forward into, and how - from the
    period's door, or by the command, each on a line of its own."""
    if not periods:
        return None
    name = name_of(dataset_id)
    where = (f"from the {periods[0]} door" if len(periods) == 1
             else "from each period's door")
    commands = [command(Warning(id=0, dataset_id=dataset_id, period=p, supply="",
                                promoted_into="", carried=None, effective_at=datetime.min))
                for p in periods]
    return "\n".join([f"This makes a newer {name} available to carry forward into "
                      f"{', '.join(periods)}. Carry it forward {where}, or:"] + commands)


def carried_periods(conn: supply_db.SupplyConnection, dataset_id: str) -> list:
    """Every opened period this dataset owes nothing for, as the period door
    lists it (REQ-PIPE-280 criterion 1): inherited, or carrying nothing because
    its inheritance was refused. Not slots - the dataset owes nothing there -
    so the slot list never shows them, and without these the door could reach
    neither carry-forward nor un-inherit. Newest period first."""
    from qa_tools.common import slot_state
    from qa_tools.common.filing_queue import CARRIES_NOTHING

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

def received(dataset_id: str, supply: str | None, conn=None) -> str:
    """When a supply was received, as the page and the terminal say an instant
    - through `conn` where one is given, never a connection of its own."""
    from qa_tools.common import display_time, filing

    at = filing.received_at_of(dataset_id, supply, conn=conn) if supply else None
    return display_time.format_instant(at) if at else "on an unrecorded date"


def command(w: Warning) -> str:
    """REQ-PIPE-280's command in full, the reason left to fill in."""
    return (f"mothman supply decide --operation carry-forward --dataset {w.dataset_id} "
            f"--period {w.period} --reason '<why>'")


def headline(w: Warning) -> str:
    """The one line a collection card and the outstanding queue show - the
    same in every case (Keith, 2026-10-24, K7; functional critic S3)."""
    return f"A newer {name_of(w.dataset_id)} could be carried forward into {w.period}."


def lines(w: Warning, *, voice: str = "page", conn=None, in_door: bool = False) -> list[str]:
    """The warning in Keith's approved wording (criterion 7): the sentences,
    then the command on a line of its own, then the door - left out where the
    person is already in that door (CLI UX critic M5). `voice` is "page"
    (the dashboard's 'A person can ...'), "terminal" ('To carry ...') or
    "record" (the decision log's reason, which needs no lead-in).

    BUILT FROM WHAT THE LATER PERIOD HOLDS - `w` as standing() / as_now()
    read it, never as it was raised (Keith, 2026-10-24, K5): three cases, a
    stale inheritance, a refused one, and one a person emptied since. Datasets
    by name, ids in the command only (K1)."""
    name = name_of(w.dataset_id)
    newer = received(w.dataset_id, w.supply, conn)
    if w.carried:
        lead = (f"A newer {name} could be carried forward into {w.period}. {w.period} "
                f"carries forward the supply received {received(w.dataset_id, w.carried, conn)}; "
                f"the one received {newer} has been promoted into {w.promoted_into} since.")
        how = {"page": "A person can carry that one forward instead, in one step:",
               "terminal": "To carry that one forward instead, in one step:", "record": ""}
    elif w.emptied:
        # K5's own wording for a period a person emptied after it carried one.
        lead = (f"{w.period} carries nothing forward for {name}. The one received {newer}, "
                f"promoted into {w.promoted_into}, could be carried forward:")
        how = {"page": "", "terminal": "", "record": ""}
        if voice == "record":
            lead = lead[:-1] + "."
    else:
        lead = (f"{w.period} carries nothing forward for {name}: there was no earlier "
                f"promoted supply when it opened. The one received {newer} has been "
                f"promoted into {w.promoted_into} since, and a person can carry it "
                f"forward, in one step:")
        how = {"page": "", "terminal": "To carry it forward, in one step:", "record": ""}
        if voice in ("terminal", "record"):
            lead = lead.replace(", and a person can carry it forward, in one step:", ".")
    if voice == "record":
        return [lead]
    out = [lead] + ([how[voice]] if how[voice] else []) + [command(w)]
    return out if in_door else out + [f"or from the {w.period} door."]


# ---------------------------------------------------------------------------
# The dashboard (REQ-PIPE-271 criterion 7), from the decision log alone
# ---------------------------------------------------------------------------

def for_dashboard(dataset_id: str, conn: supply_db.SupplyConnection | None = None) -> list[dict]:
    """The warnings about this dataset, as the page needs them to show one as
    at the date on show: a run of asset days per warning, from and until
    (`until` None while it stands), and its words for those days - computed
    here, in Python, so the page never re-derives them.

    ONE PER PERIOD ON ANY DAY (functional critic D1, #267): each day is read
    through standing() as at its end - the same one-per-period-and-dataset
    rule the terminal reads - so two warnings for one period never show
    together. AND THE WORDS OF THAT DAY (K5): a run ends where what the later
    period carries changes, so an un-inherit is said from its day on.

    THE BUILD RULE (REQ-DOCS-101): recorded decisions only, never supply rows.
    """
    from qa_tools.common import asset_time

    if conn is None:
        with supply_db.connect(read_only=True, label="mothman:carry-forward") as opened:
            return for_dashboard(dataset_id, opened)
    warnings = recorded(conn, dataset_id=dataset_id)
    if not warnings:
        return []
    instants = set()
    for w in warnings:
        instants.add(w.effective_at)
        instants.update(at for (at,) in conn.execute(
            f"SELECT DISTINCT effective_at FROM {decision_log.TABLE} WHERE dataset_id = ? "
            "AND (to_slot IN (?, ?) OR from_slot IN (?, ?)) AND effective_at >= ?",
            [dataset_id, w.period, w.promoted_into, w.period, w.promoted_into,
             w.effective_at]).fetchall())
    days = sorted({asset_time.local_date(at) for at in instants})
    out: list[dict] = []
    running: dict[str, dict] = {}
    for day in days:
        shown = {w.period: w for w in standing(conn, dataset_id=dataset_id,
                                               as_at=asset_time.end_of_day(day))}
        for period in list(running):
            w = shown.get(period)
            if w is None or _said(w) != running[period]["_said"]:
                ended = running.pop(period)
                ended["until"] = day.isoformat()
                out.append(ended)
        for period, w in shown.items():
            if period not in running:
                running[period] = _run_of_days(w, day.isoformat(), conn)
    out.extend(running.values())
    for item in out:
        del item["_said"]
    return sorted(out, key=lambda x: (x["period"], x["from"]))


def _said(w: Warning) -> tuple:
    return (w.id, w.carried, w.emptied)


def _run_of_days(w: Warning, start: str, conn) -> dict:
    text = lines(w, voice="page", conn=conn)
    return {"id": w.id, "period": w.period, "supply": w.supply,
            "promotedInto": w.promoted_into, "carried": w.carried,
            "from": start, "until": None, "headline": headline(w),
            "sentences": text[:-2], "command": text[-2], "door": text[-1],
            "_said": _said(w)}
