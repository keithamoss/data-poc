"""Placing a held supply into a period (REQ-PIPE-163).

A HELD SUPPLY HAS NO PERIOD TO LEAVE. The assignment rule held it because
no period was open at its receipt (REQ-PIPE-064) - or a confirmed
correction left it none (REQ-PIPE-170 criterion 8), or a settlement filed
its file where nothing was open (REQ-PIPE-193 criterion 11). Until this
existed the only way out was rejection. Placing is a person saying which
period it belongs to.

RECORDED AS A RE-FILE FROM NO PERIOD (criterion 2), not as an action of
its own: the same filing row and decision-log entry a re-file appends, its
from-period empty, by the person who placed it. What a period holds is
already defined over re-files, so a new action would have been a second
thing every reader of the log had to learn. Every route still CALLS it a
placement (criterion 41) - `said()` is the one wording.

ONE PLACER (criterion 40). `place()` records the filing, resolves the hold
(decision_log.apply_decision does that for every decision) and owes the
re-check - for a person's placement, a confirmed correction's
(correction_apply._place) and the rule's drain of holds configuration now
covers (schedule_ended.refile_holds). So no second implementation of
placing exists to drift from this one.

A PERSON IS NOT THE RULE (criterion 6): a closed period, or one whose claim
window had not opened at receipt, can be named. What cannot be named is a
period the dataset owes nothing in (criterion 7), an inherited one (8), one
whose slot holds an open pair (33) or an unaccepted version (34), or any
period of a dataset the agreement backstop refuses (35) - each refused
before anything is recorded, and again under the slot's lock.

NO QA RUNS HERE (criterion 5). The checks are owed; the terminal runs them
after the transaction commits, the processing pass otherwise.
"""
from __future__ import annotations

from dataclasses import dataclass

from qa_tools.common import decision_log, supply_holds

#: The words every route uses for a placement (criterion 41).
VERB = "placed into"


def said(period: str) -> str:
    """How a placement is reported - never as a re-file or 'None -> period'."""
    return f"{VERB} {period}"


@dataclass(frozen=True)
class Plan:
    dataset_id: str
    supply: str
    to_period: str
    #: The receipt instant, ISO, or "" where none was recorded.
    received: str
    #: How it would classify against the period's slot (criterion 18).
    classification: str | None
    #: Both filenames where the supply is an open pair held whole
    #: (criterion 37) - placed together, still contested.
    pair_files: tuple[str, ...] = ()
    #: What the period holds now, for the warning (criterion 18).
    target_holds: str | None = None
    target_held_as: str | None = None

    @property
    def is_pair(self) -> bool:
        return len(self.pair_files) > 1


def where_to_decide(dataset_id: str) -> str:
    """The terminal screen that offers placing (criterion 12) - the same
    screen a contested pair is settled on."""
    from qa_tools.common import supply_files

    return supply_files.where_to_settle(dataset_id)


def flag_form(dataset_id: str, supply: str, to_period: str = "<period>") -> str:
    """The command that places a held supply (criterion 12)."""
    return (f"mothman supply decide --operation place --dataset {dataset_id} "
            f"--supply {supply} --to-period {to_period} --reason '<why>'")


def plan(conn, *, dataset_id: str, supply: str, to_period: str) -> Plan:
    """Everything placing `supply` into `to_period` would do, or a
    DecisionRefused naming what must come first. Records nothing."""
    from qa_tools.common import decision_log as dl
    from qa_tools.common import filing, settlement, supersession, supply_files

    held = supply_holds.hold_on(conn, dataset_id, supply)
    if held is None or held.kind != supply_holds.ASSIGNMENT_RULE:
        raise dl.DecisionRefused(
            f"{supply} is not held, so there is nothing to place - only a supply the filing "
            f"rule could not file to any period is placed. A filed supply is re-filed "
            f"instead. `mothman supply holds` lists what is held.")
    if held.schedule_ended:
        # Criterion 22: it files itself once dates cover it (REQ-PIPE-154).
        raise dl.DecisionRefused(
            f"{supply} is held because {dataset_id}'s schedule has ended, so it is not "
            f"placed by hand: add the next delivery dates to contract/calendar.yaml and it "
            f"files itself. Where a declared correction is needed:\n"
            f"  mothman schedule draft-correction")
    _refuse_a_backstopped_dataset(conn, dataset_id)
    why = period_problem(dataset_id, to_period)
    if why:
        raise dl.DecisionRefused(why)
    h = dl.held(conn, dataset_id, to_period)
    if h and h.held_as == dl.INHERITED:
        # Criterion 8, as a re-file says it (REQ-PIPE-141 criterion 12).
        raise dl.DecisionRefused(
            f"Nothing was expected from {dataset_id} for {to_period}: it is inherited. "
            f"Un-inherit it first, then place:\n"
            f"  mothman supply decide --operation un-inherit --dataset {dataset_id} "
            f"--period {to_period} --reason '<why>'")
    blocked = settlement.open_pair_in(conn, dataset_id, to_period, besides=supply)
    if blocked:
        # Criterion 33.
        raise dl.DecisionRefused(
            f"{blocked} Nothing was recorded. It is settled at "
            f"'{where_to_decide(dataset_id)}'.")
    waiting = supersession.waiting_in(conn, dataset_id, to_period, besides=supply)
    if waiting:
        # Criterion 34.
        from qa_tools.common import asset_time

        first = waiting[0]
        at = supersession._receipt(conn, dataset_id, first)
        when = asset_time.localise(at).strftime("%-d %B %Y %H:%M") if at else "an unknown time"
        raise dl.DecisionRefused(
            f"{to_period} already has a version of {dataset_id} waiting - {first}, received "
            f"{when} - neither promoted nor rejected. It is decided first, promoted or "
            f"rejected, at '{where_to_decide(dataset_id)}'. Nothing "
            f"was recorded.\n"
            f"  mothman supply decide --operation <promote|reject> --dataset {dataset_id} "
            f"--period {to_period} --supply {first} --reason '<why>'")
    received_at = supersession._receipt(conn, dataset_id, supply)
    judged = filing._judged_for(dataset_id, to_period, received_at)
    pair: tuple[str, ...] = ()
    contest = supply_files.open_contest(conn, dataset_id, supply)
    if contest is not None:
        pair = tuple(contest.files)
    return Plan(dataset_id=dataset_id, supply=supply, to_period=to_period,
                received=received_at.isoformat() if received_at else "",
                classification=judged.classification, pair_files=pair,
                target_holds=h.holder if h and h.held_as else None,
                target_held_as=h.held_as if h else None)


def _refuse_a_backstopped_dataset(conn, dataset_id: str) -> None:
    """Criterion 35: REQ-PIPE-173's own finding, its fix, and that the
    placement can be made again once the correction is declared."""
    from qa_tools.common import agreement_drift

    try:
        refused = agreement_drift.refusal_for(conn, dataset_id)
    except Exception:  # noqa: BLE001 - an unevaluable backstop refuses nothing
        refused = None
    if refused is None:
        return
    raise decision_log.DecisionRefused(
        f"{dataset_id}'s judged past changed without a declared correction, so nothing is "
        f"placed for it until that is put right. Nothing was recorded.\n"
        + refused.message()
        + "\nThe placement can be made again once the correction is declared.")


def period_problem(dataset_id: str, period: str) -> str | None:
    """Why `period` cannot be named for this dataset, or None where it is a
    period the dataset owes (criterion 7). Ends with the command that lists
    the dataset's periods, on a line of its own."""
    from qa_tools.common import refiling

    if refiling._on_calendar(dataset_id, period):
        return None
    listing = f"\n  mothman schedule show --dataset {dataset_id}"
    reason = _owes_nothing(dataset_id, period)
    if reason is None:
        return (f"{period} is not a period {dataset_id}'s calendar generates. Nothing was "
                f"recorded. Its periods:" + listing)
    return (f"{dataset_id} owes nothing in {period} - {reason.rstrip('.')}. A supply is placed only "
            f"into a period it owes. Nothing was recorded. Its periods:" + listing)


def _owes_nothing(dataset_id: str, period: str) -> str | None:
    """Why a period the CALENDAR generates is one this dataset owes nothing
    in - in the configuration's own words - or None where the calendar does
    not generate it at all. One resolution, the participation in force on
    the period's own date (REQ-PIPE-113 criterion 2)."""
    from qa_tools.common import asset_time, schedule, slots

    horizon = asset_time.local_date(asset_time.now())
    horizon = horizon.replace(year=horizon.year + slots.SLOT_LOOKUP_YEARS)
    try:
        sequence = slots._calendar_periods(dataset_id, horizon)
    except (schedule.ScheduleConfigError, schedule.NoCalendarAgreed, KeyError, ValueError):
        return None
    found = next((p for p in sequence if p.name == period), None)
    if found is None:
        return None
    reasons = schedule.not_expected_periods(dataset_id)
    if period in reasons:
        return f"it is listed not_expected: {reasons[period]}"
    agr = schedule._agreement(None)
    version = agr.participation_on(dataset_id, found.date)
    if version is None:
        first = schedule.owes_from(dataset_id)
        return (f"it is before {dataset_id} began owing supplies"
                + (f" on {first.isoformat()}" if first else ""))
    if version.participates is not None and found.date.month not in version.participates:
        return f"it does not participate in that period: {version.reason or 'no reason given'}"
    return "the participation configuration owes nothing there"


def place(conn, *, agency_id: str, collection_id: str, dataset_id: str, supply: str,
          to_period: str, actor: str, actor_kind: str, reason: str, effective_at: str,
          owe: bool = True, entry_out: list | None = None) -> int | None:
    """THE ONE PLACER (criterion 40): record a held supply's filing to
    `to_period` as a re-file from no period, which ends its hold, and owe
    its checks. In the caller's transaction. Returns the owed re-check's id,
    or None where `owe` is False - an open pair, which is settled before
    either file is checked (criterion 37)."""
    from qa_tools.common import filing, recheck

    with decision_log.apply_decision(conn, decision_log.Decision(
            agency_id=agency_id, collection_id=collection_id, dataset_id=dataset_id,
            action=decision_log.REFILE, supply=supply, actor=actor, actor_kind=actor_kind,
            effective_at=effective_at, from_slot=None, to_slot=to_period,
            reason=reason)) as entry_id:
        if entry_out is not None:
            entry_out.append(entry_id)
        filing.refile(conn, dataset_id, supply, to_period, decision_id=entry_id)
        if not owe:
            return None
        return recheck.owe(conn, dataset_id=dataset_id, supply_id=supply,
                           decision_id=entry_id)


def apply(conn, p: Plan, *, agency_id: str, collection_id: str, actor: str, reason: str,
          effective_at: str) -> tuple[int, ...]:
    """A person's placement, judged again under the slot's lock so that
    what they confirmed is what happens. Returns the owed re-checks."""
    with decision_log.decision_transaction(conn):
        decision_log.lock_slot(conn, p.dataset_id, p.to_period)
        now = plan(conn, dataset_id=p.dataset_id, supply=p.supply, to_period=p.to_period)
        if (now.pair_files, now.target_held_as) != (p.pair_files, p.target_held_as):
            raise decision_log.DecisionRefused(
                f"What placing {p.supply} would do has changed since it was worked out - "
                f"something was filed or decided for {p.dataset_id} meanwhile. Nothing was "
                f"done; ask again to see it as it stands now.")
        owed = place(conn, agency_id=agency_id, collection_id=collection_id,
                     dataset_id=p.dataset_id, supply=p.supply, to_period=p.to_period,
                     actor=actor, actor_kind=decision_log.PERSON, reason=reason,
                     effective_at=effective_at, owe=not p.is_pair)
    return (owed,) if owed is not None else ()


# ---------------------------------------------------------------------------
# The period chooser (criterion 16): periods offered as a choice, never typed.
# ---------------------------------------------------------------------------

#: One word for where a period stands now, from slot_state's reading.
_ONE_WORD = {
    "not-yet-due": "upcoming", "overdue": "overdue", "never-supplied": "missed",
    "awaiting-decision": "waiting", "returned-by-a-person": "empty",
    "two-files": "contested", "promoted": "promoted", "rejected": "rejected",
    "substituted": "substituted", "inherited": "inherited",
    "not-supplied-accepted": "unsupplied", "amber-waiting": "waiting",
    "awaiting-acknowledgement": "promoted", "another-version-waiting": "waiting",
}

#: States whose slot must be decided before anything is placed there.
_DECIDE_FIRST = ("awaiting-decision", "amber-waiting", "another-version-waiting")


@dataclass(frozen=True)
class PeriodChoice:
    """One row of the chooser: an owed period, or a run of periods the
    dataset owes nothing in, collapsed into one row that cannot be chosen."""

    label: str
    period: str | None
    selectable: bool


@dataclass(frozen=True)
class Choices:
    rows: tuple[PeriodChoice, ...]
    has_earlier: bool
    has_later: bool
    #: The owed period nearest the receipt on the later side (or the last),
    #: where the cursor starts - never "Earlier periods" (cli-ux critic, #188).
    nearest: str | None = None


def period_choices(dataset_id: str, received_at, states: dict[str, str], *,
                   page: int = 0, each_side: int = 3) -> Choices:
    """The periods to offer for a supply received at `received_at`
    (criterion 16): opening on the owed periods whose claim windows were
    nearest that instant on both sides, each marked closed or not yet open
    then, with its one-word state now and any decision it needs first; every
    run of periods the dataset owes nothing in is ONE row, marked with why
    and not selectable. `page` moves a window's width earlier (negative) or
    later. `states` is {period: slot_state value}, read by the caller."""
    from qa_tools.common import asset_time, slots

    from qa_tools.common import schedule

    horizon = asset_time.local_date(asset_time.now())
    horizon = horizon.replace(year=horizon.year + slots.SLOT_LOOKUP_YEARS)
    try:
        owed = {s.name: s for s in slots.slots_for_dataset(dataset_id, until=horizon)}
        sequence = [p for p in slots._calendar_periods(dataset_id, horizon)
                    if p.date <= horizon or p.name in owed]
    except (schedule.ScheduleConfigError, schedule.NoCalendarAgreed, KeyError, ValueError):
        # NO CALENDAR TO CHOOSE FROM (#188 D10) - an empty chooser, never a
        # traceback; the refusal that follows says why.
        return Choices((), False, False)
    rows: list[PeriodChoice] = []
    run: list[str] = []

    def close_run():
        if run:
            span = run[0] if len(run) == 1 else f"{run[0]} to {run[-1]}"
            why = _owes_nothing(dataset_id, run[0]) or "it owes nothing there"
            rows.append(PeriodChoice(f"{span} - owes nothing: {why}", None, False))
            run.clear()

    for p in sequence:
        slot = owed.get(p.name)
        if slot is None:
            run.append(p.name)
            continue
        close_run()
        rows.append(PeriodChoice(_label(slot, received_at, states.get(p.name)), p.name, True))
    close_run()
    owed_at = [i for i, r in enumerate(rows) if r.selectable]
    if not owed_at:
        return Choices(tuple(rows), False, False)
    # THE PIVOT: the first owed period whose claim window had not opened at
    # receipt - the nearest on the later side; the one before it is the
    # nearest on the earlier side.
    later = [k for k, i in enumerate(owed_at)
             if received_at is not None and owed[rows[i].period].claim_opens_at > received_at]
    pivot = later[0] if later else len(owed_at)
    start = max(0, pivot - each_side + page * 2 * each_side)
    start = min(start, max(0, len(owed_at) - 2 * each_side))
    end = min(len(owed_at), start + 2 * each_side)
    first, last = owed_at[start], owed_at[end - 1]
    # The owes-nothing rows either side of the window are shown too, so a
    # gap at its edge is never silently cut off.
    lo = first - 1 if first > 0 and not rows[first - 1].selectable else first
    hi = last + 1 if last + 1 < len(rows) and not rows[last + 1].selectable else last
    nearest = rows[owed_at[min(pivot, len(owed_at) - 1)]].period
    return Choices(tuple(rows[lo:hi + 1]), start > 0, end < len(owed_at), nearest)


def _label(slot, received_at, state: str | None) -> str:
    """'2024-Q3 - closed when it arrived - accepted' and any decision first."""
    if received_at is not None and slot.closes_at is not None and slot.closes_at <= received_at:
        when = "closed when it arrived"
    elif received_at is not None and slot.claim_opens_at > received_at:
        when = "not yet open when it arrived"
    else:
        when = "open when it arrived"
    word = _ONE_WORD.get(state or "", "upcoming")
    label = f"{slot.name} - {when} - {word}"
    if state == "inherited":
        label += " - un-inherit it first"
    elif state == "two-files":
        label += " - settle its two files first"
    elif state in _DECIDE_FIRST:
        label += " - decide the version waiting there first"
    return label
