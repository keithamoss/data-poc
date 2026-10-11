"""After a correction, the data asset's manager confirms its proposed moves
all at once, and may keep any supply where it is (REQ-PIPE-170).

PENDING IS DERIVED, NEVER STORED (Keith, 2026-10-08): a correction declared
in the configuration with no row in qa.correction_applied is pending. The
pass notes it from configuration alone; the moves are computed LIVE when
the asset manager opens it, by the impact preview's own computation
(correction_trial.trial, REQ-PIPE-169 criterion 6), so a re-file between
merge and confirmation is simply seen where it now is.

THE AGREEMENT BEFORE THE CORRECTION IS REBUILT FROM THE CORRECTION ITSELF
(PROVISIONAL): a declared correction lists every item's old value, so
agreement_freeze.revert() puts them back. No git history is read - a
shallow clone and the synthetic generator have none to read.

OLDEST FIRST (PROVISIONAL): pending corrections are confirmed in the order
they were declared, and each is trialled against the configuration with
every LATER pending correction reverted, so what one confirmation applies
is that correction's consequence and nothing else.

ALL OR NOTHING (Keith, 2026-10-07): every move, hold, placement, keep and
re-judgement of one confirmation is written in one transaction, then the
applied record - with a summary in the preview's own form (criterion 22).

A BLOCKED MOVE IS PARKED, NOT A REFUSAL (Keith, 2026-10-11, (p)): the rest
is confirmed, and each move another decision blocks waits in
qa.correction_parked, on the outstanding list, until its blocker clears -
then the pass moves it to the period CONFIRMED, as the rule, naming who
confirmed it - or the asset manager keeps the supply where it is, with a
reason, as a keep at confirmation is recorded.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime

from qa_tools.common import correction_trial, decision_log, qa_store

APPLIED = f'"{qa_store.SCHEMA}".correction_applied'
PARKED = f'"{qa_store.SCHEMA}".correction_parked'
RESOLVED = f'"{qa_store.SCHEMA}".correction_parked_resolved'
#: Who a placement of a held supply is recorded as - the rule files it, as
#: it drains a schedule-ended hold (REQ-PIPE-154); the confirming person is
#: named in the reason. A held supply has no period to leave, and the
#: decision log lets only the rule re-file one.
RULE_ACTOR = "mothman (a confirmed correction)"


@dataclass(frozen=True)
class Pending:
    """One declared correction with no applied record."""

    reference: str
    owner: tuple
    label: str
    date: str
    reason: str
    approver: str
    changes: tuple[tuple[str, object, object], ...]


def _declared(cal: dict, asset: dict) -> list[Pending]:
    """Every declared correction, ONE PER CHANGE REFERENCE (delivery-critic on
    170, D1): the gate makes each changed item be declared on its own owner,
    so one correction - a collection moved to another calendar, a date and a
    grace changed together - is several entries sharing a reference, and is
    trialled, listed and applied as one."""
    from qa_tools.common import agreement_freeze

    by_ref: dict[str, Pending] = {}
    for owner, entries in agreement_freeze._corrections_by_owner(cal, asset).items():
        for corr in entries:
            corr = corr or {}
            ref = str(corr.get("change_reference") or "")
            changes = tuple((str((c or {}).get("item")), (c or {}).get("old"),
                             (c or {}).get("new")) for c in corr.get("changes") or [])
            label = agreement_freeze._owner_label(owner)
            if ref in by_ref:
                was = by_ref[ref]
                by_ref[ref] = Pending(ref, was.owner, f"{was.label}; {label}", was.date,
                                      was.reason, was.approver, was.changes + changes)
                continue
            by_ref[ref] = Pending(
                reference=ref, owner=owner, label=label, date=str(corr.get("date") or ""),
                reason=str(corr.get("reason") or ""), approver=str(corr.get("approver") or ""),
                changes=changes)
    # BY DATE; a tie keeps the order the files are read in - calendars, then
    # datasets, then the timezone - not the order they were written (J4).
    return sorted(by_ref.values(), key=lambda p: p.date)


def applied_references(conn) -> set[str]:
    return {r[0] for r in conn.execute(f"SELECT change_reference FROM {APPLIED}").fetchall()}


def pending(conn, docs: tuple[dict, dict] | None = None) -> list[Pending]:
    """Every declared correction not yet applied, oldest first."""
    cal, asset = docs or correction_trial.working()
    done = applied_references(conn)
    return [p for p in _declared(cal, asset) if p.reference not in done]


def _on_own_calendar(agr, dataset_id: str) -> bool:
    """A dataset naming a calendar other than its collection's takes none of
    the collection's defaults (REQ-PIPE-181 criterion 9)."""
    own = agr.dataset(dataset_id)
    return bool(own and own.calendar
                and own.calendar != agr.collections.get(agr.collection_of(dataset_id)))


def affected_datasets(p: Pending, cal: dict) -> list[str]:
    """The datasets a correction's declared changes name - from configuration
    alone, which is all the pass's 'awaiting confirmation' marking reads."""
    from qa_tools.common import agreement, agreement_freeze, hierarchy

    every = [d.dataset_id for d in hierarchy.all_datasets()]
    out: set[str] = set()
    agr = agreement.from_doc(cal)
    for key, _old, _new in p.changes:
        parts = key.split()
        if parts[:1] == ["dataset"] and len(parts) > 1:
            out.add(parts[1])
        elif parts[:1] == ["calendar"] and len(parts) > 1:
            out.update(agreement_freeze._datasets_on(parts[1], agr))
        elif parts[:1] == ["collection"] and len(parts) > 1:
            # Every dataset of the collection that takes its defaults
            # (REQ-PIPE-181) - from the configuration before or after.
            out.update(d for d in every
                       if agr.collection_of(d) == parts[1] and not _on_own_calendar(agr, d))
        elif parts[:1] == ["timezone"]:
            out.update(every)
    return [d for d in every if d in out]


def states(p: Pending, all_pending: list[Pending],
           docs: tuple[dict, dict]) -> tuple[tuple[dict, dict], tuple[dict, dict]]:
    """(before, after) this correction: the configuration with every later
    pending correction reverted, then with this one reverted too."""
    from qa_tools.common import agreement_freeze

    cal, asset = docs
    later = all_pending[all_pending.index(p) + 1:]
    for q in reversed(later):
        cal, asset = agreement_freeze.revert(cal, asset, list(q.changes))
    work = (cal, asset)
    base = agreement_freeze.revert(cal, asset, list(p.changes))
    return base, work


class NotPending(decision_log.DecisionRefused):
    """A reference that is not a pending correction."""


def _find(conn, reference: str, docs) -> tuple[Pending, list[Pending]]:
    found = pending(conn, docs)
    match = [p for p in found if p.reference == reference]
    if not match:
        applied = reference in applied_references(conn)
        raise NotPending(
            f"{reference} was already applied - `mothman supply corrections` lists only "
            f"the ones still waiting."
            if applied else
            f"{reference} is not a declared correction. `mothman supply corrections` lists "
            f"the pending ones.")
    return match[0], found


def trial_for(conn, reference: str, *, at: datetime | None = None,
              docs: tuple[dict, dict] | None = None):
    """(the pending correction, its trial) - computed live, nothing stored."""
    docs = docs or correction_trial.working()
    p, found = _find(conn, reference, docs)
    base, work = states(p, found, docs)
    t = correction_trial.trial(conn, base, work, at=at,
                               dataset_ids=affected_datasets(p, docs[0]))
    return p, t


def key(t) -> str:
    """The consequences' key (criterion 16): changes whenever any move,
    hold, block or verdict change does, so a confirmation of a list that
    moved since it was shown is refused."""
    body = json.dumps({
        "moves": sorted([m.dataset_id, m.supply_id, m.from_period, m.to_period, m.verdict,
                         bool(m.blocked), m.if_kept] for m in t.moves),
        "verdicts": sorted([v.dataset_id, v.supply_id, v.slot, v.old, v.new]
                           for v in t.verdicts)}, default=str)
    return hashlib.sha256(body.encode()).hexdigest()[:8]


@dataclass(frozen=True)
class Applied:
    reference: str
    actor: str
    moved: tuple = ()
    placed: tuple = ()
    held: tuple = ()
    kept: tuple = ()
    rejudged: tuple = ()
    owed_rechecks: tuple = field(default_factory=tuple)
    #: (dataset, supply, from, to, verdict at the time, verdict now) for each
    #: supply moved - what its dashboard note says (Keith, 2026-10-11, (r)).
    moved_verdicts: tuple = ()
    #: (dataset, supply, from, to, what blocks it) for each move parked
    #: (Keith, 2026-10-11, (p)).
    parked: tuple = ()

    def as_record(self) -> dict:
        return {"reference": self.reference, "actor": self.actor,
                "moved": [list(x) for x in self.moved], "placed": [list(x) for x in self.placed],
                "held": [list(x) for x in self.held], "kept": [list(x) for x in self.kept],
                "rejudged": [list(x) for x in self.rejudged],
                "moved_verdicts": [list(x) for x in self.moved_verdicts],
                "parked": [list(x) for x in self.parked]}


def why_not_confirmable(t, keep: set[tuple[str, str]], keep_reason: str | None) -> str | None:
    """Why this confirmation cannot go ahead, or None (criteria 9, 15, 19)."""
    proposed = {(m.dataset_id, m.supply_id) for m in t.moves}
    unknown = sorted(f"{d} {s}" for d, s in keep - proposed)
    if unknown:
        return (f"{', '.join(unknown)} {'is' if len(unknown) == 1 else 'are'} not among "
                f"this correction's proposed moves, so there is nothing to keep")
    if keep and not (keep_reason or "").strip():
        return "keeping a supply needs a reason - why it stays where it is"
    # A BLOCKED MOVE NO LONGER STOPS THE REST (Keith, 2026-10-11, (p)): it is
    # parked by confirm(), never dropped.
    return None


def confirm(conn, reference: str, *, actor: dict, keep: set[tuple[str, str]] = frozenset(),
            keep_reason: str | None = None, acknowledge: str | None = None,
            effective_at: str, docs: tuple[dict, dict] | None = None) -> Applied:
    """Apply one pending correction's moves and re-judgements in one step,
    as the data asset's manager (criteria 4-9, 19-20), and record it."""
    from qa_tools.common import people, refiling

    # REFUSED BEFORE ANYTHING ELSE IS WORKED OUT (criterion 18).
    people.require_role(actor, people.MANAGER, people.DATA_ASSET)
    docs = docs or correction_trial.working()
    p, t = trial_for(conn, reference, docs=docs)
    if acknowledge is not None and acknowledge != key(t):
        raise decision_log.DecisionRefused(
            f"The moves for {reference} have changed since they were shown - something was "
            f"filed or decided meanwhile. Nothing was done; list them again "
            f"(`mothman supply corrections --reference {reference}`) and confirm with the new "
            f"key.")
    why = why_not_confirmable(t, set(keep), keep_reason)
    if why:
        raise decision_log.DecisionRefused(f"{reference} cannot be confirmed: {why}.")
    email = actor.get("email") or str(actor)
    _base, work = states(p, pending(conn, docs), docs)
    moved, placed, held, kept, rejudged, owed = [], [], [], [], [], []
    moved_verdicts: list = []
    parked_moves: list = []
    # ONE TRANSACTION, the decision log's own, so the knock-on re-evaluation
    # of every period this moved is owed once, at the end (REQ-PIPE-121) -
    # and UNDER THIS CORRECTION'S OWN AGREEMENT (delivery-critic on 170, D9):
    # every re-file, plan and verdict resolves slots through the agreement in
    # force, which on disk holds every merged correction, a later one included.
    with correction_trial.configured(*work), decision_log.decision_transaction(conn):
        for m in t.moves:
            entry = _entry(m.dataset_id)
            why_text = f"Correction {reference} ({p.reason})"
            if (m.dataset_id, m.supply_id) in keep:
                # A HELD supply kept is kept held, naming the period it was not
                # placed into (delivery-critic on 170, D3).
                with decision_log.apply_decision(conn, decision_log.Decision(
                        agency_id=entry.agency_id, collection_id=entry.collection_id,
                        dataset_id=m.dataset_id, action=decision_log.KEEP,
                        supply=m.supply_id, actor=email, actor_kind=decision_log.PERSON,
                        effective_at=effective_at, to_slot=m.from_period,
                        from_slot=None if m.from_period else m.to_period,
                        reason=f"Kept where it is under correction {reference}: "
                               f"{keep_reason}")) as keep_id:
                    pass
                # THE KEEP'S OWN DECISION ID travels in the applied record, so a
                # reader maps each keep to its correction exactly - one supply
                # can be kept against two corrections (delivery-critic on 172, #4).
                kept.append((m.dataset_id, m.supply_id, m.from_period, keep_reason, keep_id))
            elif m.blocked:
                conn.execute(
                    f"INSERT INTO {PARKED} (change_reference, dataset_id, supply_id, "
                    "from_period, to_period, blocked, confirmed_by, parked_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    [reference, m.dataset_id, m.supply_id, m.from_period, m.to_period,
                     m.blocked, email, effective_at])
                parked_moves.append((m.dataset_id, m.supply_id, m.from_period, m.to_period,
                                     m.blocked))
            elif m.placing:
                owed.append(_place(conn, m, entry, email, reference, effective_at))
                placed.append((m.dataset_id, m.supply_id, m.to_period))
            elif m.held:
                _hold(conn, m, entry, email, reference, p.reason, effective_at)
                held.append((m.dataset_id, m.supply_id, m.from_period))
            else:
                plan = refiling.plan(conn, dataset_id=m.dataset_id, supply=m.supply_id,
                                     to_period=m.to_period)
                # THE RULE'S MOVE, naming who confirmed it (Keith, 2026-10-11,
                # (o)): the manager approved the correction, not this filing,
                # so a later correction may move it again.
                owed.append(refiling.apply(
                    conn, plan, agency_id=entry.agency_id, collection_id=entry.collection_id,
                    actor=RULE_ACTOR, reason=f"{why_text}, confirmed by {email}",
                    effective_at=effective_at, actor_kind=decision_log.RULE))
                moved.append((m.dataset_id, m.supply_id, m.from_period, m.to_period))
                moved_verdicts.append((m.dataset_id, m.supply_id, m.from_period, m.to_period,
                                       m.old_verdict, m.verdict))
        # RE-JUDGED IN PLACE, after the moves (criterion 20: each supply judged
        # against the period it ends up in - a moved one already was, by its
        # new filing).
        from qa_tools.common import agreement as agreement_mod, verdict

        agr = agreement_mod.current()   # this correction's, inside configured()
        for ds in affected_datasets(p, docs[0]):
            for r in verdict.rejudged(conn, ds, agr):
                verdict.record_rejudgement(
                    conn, r, correction_ref=reference,
                    correction_changelog=f"{p.date}: {p.reason}",
                    recorded_at=effective_at)
                rejudged.append((ds, r.supply_id, r.slot, r.old.get("classification"),
                                 r.new.classification))
        done = Applied(reference, email, tuple(moved), tuple(placed), tuple(held), tuple(kept),
                       tuple(rejudged), tuple(x for x in owed if x is not None),
                       tuple(moved_verdicts), tuple(parked_moves))
        conn.execute(
            f"INSERT INTO {APPLIED} (change_reference, owner, actor, applied_at, summary) "
            "VALUES (?, ?, ?, ?, ?)",
            [reference, p.label, email, effective_at, json.dumps(done.as_record())])
    return done


@dataclass(frozen=True)
class Parked:
    """A confirmed correction's move that waits on another decision."""

    id: int
    reference: str
    dataset_id: str
    supply_id: str
    from_period: str | None
    to_period: str | None
    blocked: str
    confirmed_by: str
    parked_at: str

    @property
    def held(self) -> bool:
        return self.to_period is None

    @property
    def placing(self) -> bool:
        return self.from_period is None and self.to_period is not None


def parked(conn, reference: str | None = None) -> list[Parked]:
    """Every parked move not yet moved or kept, oldest first."""
    rows = conn.execute(
        f"SELECT p.id, p.change_reference, p.dataset_id, p.supply_id, p.from_period, "
        f"p.to_period, p.blocked, p.confirmed_by, p.parked_at FROM {PARKED} p "
        f"LEFT JOIN {RESOLVED} r ON r.parked_id = p.id WHERE r.parked_id IS NULL "
        + ("AND p.change_reference = ? " if reference else "")
        + "ORDER BY p.id", [reference] if reference else []).fetchall()
    return [Parked(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7],
                   r[8].isoformat() if hasattr(r[8], "isoformat") else str(r[8]))
            for r in rows]


def _resolve(conn, item: Parked, how: str, actor: str, at: str, decision_id) -> None:
    conn.execute(f"INSERT INTO {RESOLVED} (parked_id, how, actor, resolved_at, decision_id) "
                 "VALUES (?, ?, ?, ?, ?)", [item.id, how, actor, at, decision_id])


def drain_parked(conn, *, docs: tuple[dict, dict] | None = None, skip=frozenset(),
                 say=print, effective_at: str | None = None) -> list[tuple]:
    """Move every parked move whose blocker has cleared, to the period
    CONFIRMED (Keith, 2026-10-11), as the rule naming who confirmed it. A
    refused dataset (REQ-PIPE-173) is left parked, as is any move still
    blocked. Returns (dataset, supply, from, to) for each moved.

    A SUPPLY NO LONGER WHERE IT WAS PARKED FROM is left parked and said
    (PROVISIONAL): a person moved it since, and moving it again from
    somewhere else is not what was confirmed - the manager keeps it or
    clears it by hand."""
    from qa_tools.common import filing, replay_clock

    found = [p for p in parked(conn) if p.dataset_id not in skip]
    done: list[tuple] = []
    if not found:
        return done
    at = effective_at or replay_clock.now().isoformat()
    docs = docs or correction_trial.working()
    with correction_trial.configured(*docs):
        for item in found:
            if correction_trial._blocked(conn, item.dataset_id, item.supply_id,
                                         item.from_period, item.to_period):
                continue
            now = filing.filing_for(item.dataset_id, item.supply_id)
            if (now or {}).get("slot") != item.from_period:
                say(f"{item.supply_id}: parked under {item.reference} from "
                    f"{item.from_period or 'a hold'}, but it is now filed to "
                    f"{(now or {}).get('slot') or 'no period'} - left parked for the asset "
                    f"manager to keep or move by hand.")
                continue
            entry = _entry(item.dataset_id)
            with decision_log.decision_transaction(conn):
                decision_id = _carry_out(conn, item, entry, at)
                _resolve(conn, item, "moved", RULE_ACTOR, at, decision_id)
            say(f"{item.supply_id}: what blocked it under correction {item.reference} has "
                f"cleared, so it moves to {item.to_period or 'a hold'} as confirmed")
            done.append((item.dataset_id, item.supply_id, item.from_period, item.to_period))
    return done


def _carry_out(conn, item: Parked, entry, at: str):
    """The confirmed move itself - the same three shapes confirm() applies.
    Returns the decision id it was recorded under, where there is one."""
    from qa_tools.common import refiling

    why = (f"Correction {item.reference}, confirmed by {item.confirmed_by}, parked until "
           f"what blocked it cleared")
    if item.placing:
        _place(conn, item, entry, item.confirmed_by, item.reference, at)
    elif item.held:
        _hold(conn, item, entry, item.confirmed_by, item.reference, why, at)
    else:
        plan = refiling.plan(conn, dataset_id=item.dataset_id, supply=item.supply_id,
                             to_period=item.to_period)
        refiling.apply(conn, plan, agency_id=entry.agency_id,
                       collection_id=entry.collection_id, actor=RULE_ACTOR, reason=why,
                       effective_at=at, actor_kind=decision_log.RULE)
    rows = conn.execute(f"SELECT max(id) FROM {decision_log.TABLE} WHERE dataset_id = ? "
                        "AND supply = ?", [item.dataset_id, item.supply_id]).fetchall()
    return rows[0][0] if rows else None


def keep_parked(conn, reference: str, dataset_id: str, supply: str, *, actor: dict,
                reason: str, effective_at: str) -> int:
    """The asset manager keeps a parked supply where it is instead (Keith,
    2026-10-11), with a reason - recorded as a keep against the correction,
    exactly as a keep at confirmation is. Returns the keep's decision id."""
    from qa_tools.common import people

    people.require_role(actor, people.MANAGER, people.DATA_ASSET)
    if not (reason or "").strip():
        raise decision_log.DecisionRefused(
            "keeping a supply needs a reason - why it stays where it is")
    found = [p for p in parked(conn, reference)
             if p.dataset_id == dataset_id and p.supply_id == supply]
    if not found:
        raise decision_log.DecisionRefused(
            f"{reference} has no parked move for {dataset_id} {supply} - `mothman supply "
            f"corrections` lists what is parked.")
    item = found[0]
    email = actor.get("email") or str(actor)
    entry = _entry(dataset_id)
    with decision_log.decision_transaction(conn):
        with decision_log.apply_decision(conn, decision_log.Decision(
                agency_id=entry.agency_id, collection_id=entry.collection_id,
                dataset_id=dataset_id, action=decision_log.KEEP, supply=supply,
                actor=email, actor_kind=decision_log.PERSON, effective_at=effective_at,
                to_slot=item.from_period,
                from_slot=None if item.from_period else item.to_period,
                reason=f"Kept where it is under correction {reference}: {reason}")) as keep_id:
            pass
        _resolve(conn, item, "kept", email, effective_at, keep_id)
    return keep_id


def _entry(dataset_id: str):
    from qa_tools.common import hierarchy

    return hierarchy.dataset(dataset_id)


def _place(conn, m, entry, email: str, reference: str, effective_at: str):
    """A held supply the corrected calendar now covers is filed by the rule,
    as REQ-PIPE-154's drain files one, naming who confirmed it."""
    from qa_tools.common import filing, recheck

    with decision_log.apply_decision(conn, decision_log.Decision(
            agency_id=entry.agency_id, collection_id=entry.collection_id,
            dataset_id=m.dataset_id, action=decision_log.REFILE, supply=m.supply_id,
            actor=RULE_ACTOR, actor_kind=decision_log.RULE, effective_at=effective_at,
            from_slot=None, to_slot=m.to_period,
            reason=f"Correction {reference}, confirmed by {email}: the corrected calendar "
                   f"files it to {m.to_period}.")) as entry_id:
        filing.refile(conn, m.dataset_id, m.supply_id, m.to_period, decision_id=entry_id)
        return recheck.owe(conn, dataset_id=m.dataset_id, supply_id=m.supply_id,
                           decision_id=entry_id)


def _hold(conn, m, entry, email: str, reference: str, why: str, effective_at: str) -> None:
    """A filed supply the corrected calendar offers no period is HELD on
    confirmation (criterion 8, REQ-PIPE-064), naming the correction - out of
    its period, its tables back in staging where it was promoted."""
    from qa_tools.common import filing, period_tables, supply_db, supply_holds

    promoted = decision_log.promoted_into(conn, m.dataset_id, m.from_period) == m.supply_id
    with decision_log.apply_decision(conn, decision_log.Decision(
            agency_id=entry.agency_id, collection_id=entry.collection_id,
            dataset_id=m.dataset_id, action=decision_log.REFILE, supply=m.supply_id,
            actor=RULE_ACTOR, actor_kind=decision_log.RULE, effective_at=effective_at,
            from_slot=m.from_period, to_slot=None,
            reason=f"Correction {reference} ({why}), confirmed by {email}: the corrected "
                   f"calendar offers it no period, so it is held.")) as entry_id:
        if promoted and period_tables.take_out(
                conn, period=m.from_period, logical=entry.table, supply=m.supply_id,
                to_schema=supply_db.STAGING_SCHEMA) is None:
            # As refiling.apply refuses (delivery-critic on 170, L1).
            raise decision_log.DecisionRefused(
                f"{m.from_period} has no {entry.table} for {m.supply_id}, which the decision "
                f"log says it holds - nothing was done.")
        filing.refile(conn, m.dataset_id, m.supply_id, None, decision_id=entry_id)
    # AGAIN WHERE IT WAS HELD BEFORE (D4): a hold is one row per supply.
    supply_holds.raise_again(
        conn, dataset_id=m.dataset_id, supply_id=m.supply_id,
        kind=supply_holds.ASSIGNMENT_RULE,
        reason={"unavailable": [], "considered": [], "correction": reference,
                "correction_reason": why},
        raised_by=f"correction {reference}")


def summary(p: Pending, t, done: Applied, *, as_at: datetime, database: str) -> str:
    """What was actually applied, in the impact preview's own order and
    form (criterion 22), for the change reference and its approver."""
    applied_moves = tuple(
        m for m in t.moves if (m.dataset_id, m.supply_id) not in
        {(d, s) for d, s, *_ in done.kept} | {(d, s) for d, s, *_ in done.parked})
    applied_verdicts = tuple(correction_trial.VerdictChange(d, s, slot, old, new)
                             for d, s, slot, old, new in done.rejudged)
    shown = correction_trial.Trial(t.changes, t.slot_moves, t.obligations, applied_verdicts,
                                   applied_moves, t.not_proposed, t.unbuildable)
    text = correction_trial.report(shown, as_at=as_at, database=database,
                                   against=f"the agreement before {p.reference}",
                                   title=f"Applied: correction {p.reference}", applied=True)
    if done.kept:
        text += "\n## Kept where they are\n\n" + "".join(
            f"- {d} `{s}` in {period or 'no period'}: {why}\n" for d, s, period, why, *_ in done.kept)
    if done.parked:
        text += ("\n## Parked until what blocks them clears\n\n"
                 "The next processing pass after each blocker clears moves it to the period "
                 "below, as confirmed here.\n\n") + "".join(
            f"- {d} `{s}`: {frm or 'held'} -> {to or 'held'}; blocked: {why.splitlines()[0]}\n"
            for d, s, frm, to, why in done.parked)
    return text
