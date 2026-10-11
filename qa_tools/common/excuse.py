"""A person can excuse a late supply, with a reason, without changing the
calendar it was judged against (REQ-PIPE-161).

AN ANNOTATION, NOT A HOLDING DECISION (NFR 1). An excuse is a decision-log
entry about ONE SUPPLY's lateness against ONE SLOT. It changes no
configuration, no data, no check result, no filing and nothing a period
resolves to (criterion 4) - qa.slot_holds lists only the actions that
change a slot, so it ignores this by construction, as it ignores
acknowledge and mark-not-supplied.

THE VERDICT IS NOT REWRITTEN (criterion 5): the supply still classifies as
late, and reads late AND excused. Turning late into on time would be the
retroactive re-judgement REQ-PIPE-111 exists to stop, through another door.

AN EXCUSE LAPSES, NEVER DISAPPEARS (criterion 7; REQ-PIPE-168's NFR): it
is about the slot it names, so once the supply is re-filed elsewhere, or a
correction re-judges it on time, the excuse no longer applies and is
reported lapsed. A WITHDRAWAL is its own entry (criterion 8). Nothing is
deleted; everything here is read from the append-only log.

RECORDED DECISIONS AND FILINGS ONLY, never supply rows.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from qa_tools.common import decision_log, qa_store

LATE = "late"
_CURRENT = f'"{qa_store.SCHEMA}".filing_current'


@dataclass(frozen=True)
class Excuse:
    """One excuse entry and what has become of it."""

    slot: str
    actor: str
    reason: str
    at: str
    #: The withdrawal that ended it: {"actor", "reason", "at"}, or None.
    withdrawn: dict | None = None
    #: Why it no longer applies, where it has lapsed - re-filed or re-judged.
    lapsed: str | None = None
    #: When it lapsed, where that is recorded - the re-file decision or the
    #: re-judgement - so a date on show before it still shows the excuse.
    lapsed_at: str | None = None

    @property
    def in_force(self) -> bool:
        return self.withdrawn is None and self.lapsed is None

    def as_record(self) -> dict:
        return {"slot": self.slot, "actor": self.actor, "reason": self.reason,
                "at": self.at, "withdrawn": self.withdrawn, "lapsed": self.lapsed,
                "lapsedAt": self.lapsed_at}


def _iso(value) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _current(conn, dataset_id: str, supply: str) -> tuple[str | None, str | None] | None:
    """(slot, classification) of the supply's current filing, or None."""
    rows = conn.execute(
        f"SELECT slot, classification FROM {_CURRENT} WHERE dataset_id = ? AND supply_id = ?",
        [dataset_id, supply]).fetchall()
    return rows[0] if rows else None


def history(conn, dataset_id: str, supply: str, as_at: str | None = None) -> list[Excuse]:
    """Every excuse this supply has had, oldest first, each with its
    withdrawal or lapse - as at `as_at` (an effective instant), or now."""
    rows = conn.execute(
        f"SELECT action, actor, reason, effective_at, to_slot FROM {decision_log.TABLE} "
        "WHERE dataset_id = ? AND supply = ? AND action IN (?, ?) "
        "AND (CAST(? AS timestamptz) IS NULL OR effective_at <= CAST(? AS timestamptz)) "
        "ORDER BY effective_at, id",
        [dataset_id, supply, decision_log.EXCUSE_LATENESS, decision_log.WITHDRAW_EXCUSE,
         as_at, as_at]).fetchall()
    out: list[Excuse] = []
    for action, actor, reason, at, slot in rows:
        if action == decision_log.EXCUSE_LATENESS:
            out.append(Excuse(slot=slot, actor=actor, reason=reason or "", at=_iso(at)))
        elif out and out[-1].withdrawn is None:
            last = out[-1]
            out[-1] = Excuse(slot=last.slot, actor=last.actor, reason=last.reason,
                             at=last.at, withdrawn={"actor": actor, "reason": reason or "",
                                                    "at": _iso(at)})
    lapsed = []
    for e in out:
        why = at = None
        if e.withdrawn is None:
            why, at = _lapse(conn, dataset_id, supply, e.at, e.slot)
        # AS AT A DATE BEFORE THE LAPSE, it had not lapsed yet
        # (delivery-critic on 161, #11).
        if why and as_at and at and _instant(at) > _instant(as_at):
            why = at = None
        lapsed.append(Excuse(**{**e.__dict__, "lapsed": why, "lapsed_at": at})
                      if why else e)
    return lapsed


def _instant(value):
    """An instant to compare - never two ISO strings with different offsets."""
    from datetime import datetime

    return datetime.fromisoformat(value) if isinstance(value, str) else value


def _lapse(conn, dataset_id: str, supply: str, after: str,
           excused_slot: str) -> tuple[str | None, str | None]:
    """Why and when an excuse recorded at `after` stopped applying, or
    (None, None).

    THE FIRST RE-FILE AFTER IT, wherever it went (delivery-critic on 161,
    #2): a supply re-filed away and back has a NEW filing, and the excuse
    was about the old one - comparing slot names revived it.

    ELSE THE FIRST CORRECTION THAT RE-JUDGED IT NOT LATE (#3, PROVISIONAL):
    a lapse is a fact about the past, so a later correction judging it late
    again does not bring the old excuse back; a person excuses afresh.

    ELSE, where the supply simply no longer reads late, that - with no
    instant to put on it."""
    rows = conn.execute(
        f"SELECT effective_at, to_slot FROM {decision_log.TABLE} WHERE dataset_id = ? "
        "AND supply = ? AND action = ? AND effective_at > CAST(? AS timestamptz) "
        "ORDER BY effective_at, id LIMIT 1",
        [dataset_id, supply, decision_log.REFILE, after]).fetchall()
    if rows:
        return f"re-filed to {rows[0][1]}", _iso(rows[0][0])
    from qa_tools.common import verdict

    rows = conn.execute(
        f"SELECT classification, correction_ref, recorded_at FROM {verdict.TABLE} "
        "WHERE dataset_id = ? AND supply_id = ? AND correction_ref IS NOT NULL "
        "AND recorded_at > CAST(? AS timestamptz) AND classification IS DISTINCT FROM ? "
        "ORDER BY id LIMIT 1", [dataset_id, supply, after, LATE]).fetchall()
    if rows:
        said = (rows[0][0] or "not judged").replace("_", " ")
        return f"re-judged {said} by {rows[0][1]}", _iso(rows[0][2])
    now = _current(conn, dataset_id, supply)
    slot, classification = now if now else (None, None)
    if slot is None:
        return "no longer filed to a period", None
    if slot != excused_slot:
        return f"re-filed to {slot}", None
    if classification != LATE:
        return f"re-judged {(classification or 'not judged').replace('_', ' ')}", None
    return None, None


def in_force(conn, dataset_id: str, supply: str, as_at: str | None = None) -> Excuse | None:
    """The excuse this supply carries now (or as at `as_at`), or None."""
    found = [e for e in history(conn, dataset_id, supply, as_at) if e.in_force]
    return found[-1] if found else None


def why_not_excusable(conn, dataset_id: str, supply: str, slot: str | None) -> str | None:
    """None where `supply` may be excused in `slot`; otherwise why not, in
    words a person can act on (criterion 3)."""
    if not slot:
        return "no period was named"
    now = _current(conn, dataset_id, supply)
    if now is None:
        return f"{supply} has no filing for {dataset_id}"
    filed, classification = now
    if filed != slot:
        return (f"it is filed to {filed or 'no period (held)'}, not {slot} - an excuse is "
                f"about its lateness against the slot it is filed to")
    if classification != LATE:
        said = (classification or "not judged").replace("_", " ")
        return f"it is {said} for {slot}, not late, so there is no lateness to excuse"
    already = in_force(conn, dataset_id, supply)
    if already is not None:
        return (f"it is already excused, by {already.actor} at {already.at} - withdraw that "
                f"first to excuse it again")
    return None


def why_not_withdrawable(conn, dataset_id: str, supply: str, slot: str | None) -> str | None:
    """None where `supply` carries an excuse in force for `slot`."""
    found = in_force(conn, dataset_id, supply)
    if found is None:
        return f"{supply} carries no excuse in force"
    if slot and found.slot != slot:
        return f"its excuse is for {found.slot}, not {slot}"
    return None


# ---- the range form (criteria 9, 15-17) ---------------------------------

def _period_dates(dataset_id: str) -> dict[str, date]:
    """Every period name of the dataset's calendar to its date."""
    from qa_tools.common import schedule

    cal = schedule.calendar_for_dataset(dataset_id)
    try:
        periods = schedule.periods_for_calendar(cal.name)
    except Exception:  # noqa: BLE001 - a cadence rule needs a horizon
        from qa_tools.common import asset_time

        periods = schedule.periods_for_calendar(
            cal.name, until=asset_time.local_date(asset_time.now()))
    return {p.name: p.date for p in periods}


def _date_of(name: str, dates: dict[str, date]) -> date | None:
    if name in dates:
        return dates[name]
    try:
        return date.fromisoformat(name)
    except ValueError:
        return None


@dataclass(frozen=True)
class RangePlan:
    """What a range excuse would do: the supplies it excuses and those it
    skips with why, each as (supply, slot[, why])."""

    excuse: tuple[tuple[str, str], ...]
    skipped: tuple[tuple[str, str, str], ...]


def _superseded_why(conn, dataset_id: str, supply: str) -> str | None:
    """Why a range skips a superseded supply (Keith, 2026-10-11, answer
    (a)): a range covers current AND rejected supplies, never superseded
    ones - a superseded version was replaced rather than decided on, so a
    range about a run of late periods is not about it. Excusing one alone,
    by name, is still open."""
    from qa_tools.common import supersession

    if not supersession.is_superseded(conn, dataset_id, supply):
        return None
    newer = supersession.superseded_by(conn, dataset_id, supply)
    by = f" by {newer}" if newer else ""
    return (f"it was superseded{by} - a range excuses current and rejected supplies, not "
            f"superseded ones; excuse it by name if it needs one")


def range_plan(conn, dataset_id: str, first: str, last: str) -> RangePlan:
    """Every supply FILED in the periods `first` to `last` inclusive: late
    and not yet excused ones are excused, the rest skipped and why -
    superseded ones always skipped (answer (a)).

    Supplies currently filed there, by the slot each is filed to - an
    excuse is about a supply against its slot, never about a period.
    """
    dates = _period_dates(dataset_id)
    lo, hi = _date_of(first, dates), _date_of(last, dates)
    if lo is None or hi is None:
        unknown = first if lo is None else last
        raise decision_log.DecisionRefused(
            f"{unknown!r} is not a period of {dataset_id}'s calendar.")
    if lo > hi:
        raise decision_log.DecisionRefused(
            f"the range runs backwards: {first} is after {last}.")
    rows = conn.execute(
        f"SELECT supply_id, slot FROM {_CURRENT} WHERE dataset_id = ? AND slot IS NOT NULL "
        "ORDER BY supply_id", [dataset_id]).fetchall()
    excuse, skipped = [], []
    for supply, slot in rows:
        when = _date_of(slot, dates)
        if when is None or not lo <= when <= hi:
            continue
        why = _superseded_why(conn, dataset_id, supply) or why_not_excusable(
            conn, dataset_id, supply, slot)
        (skipped.append((supply, slot, why)) if why else excuse.append((supply, slot)))
    key = lambda item: (_date_of(item[1], dates), item[0])  # noqa: E731
    return RangePlan(tuple(sorted(excuse, key=key)), tuple(sorted(skipped, key=key)))
