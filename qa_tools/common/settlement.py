"""Settling a contested pair - choose-file (REQ-PIPE-193).

Two files arrived for one dataset's table in one delivery, and nothing
says which is the supply. A person says, for EACH file, exactly one thing
(criterion 3): it is this period's supply, it belongs to another period
(re-filed), it is wrong (rejected), or it is a spare copy (kept but
superseded). Every file that becomes a supply is then filed, checked and
gated on its OWN receipt, like a first arrival (criterion 21).

ONE PLAN FOR THE WARNING AND THE EFFECT, as re-filing has (REQ-GHUB-142
criterion 2): `plan()` works out everything a settlement does, both the
warning panel (filing_decisions.consequences) and `apply()` are built from
it, and `apply()` works it out again under the lock and refuses if it
changed (criterion 18).

WHAT `apply()` WRITES, IN ONE TRANSACTION (NFR 1):
  - ONE person entry, `choose-file`, naming the pair's `#1` and its period,
    with one qa.decision_file row per file: its filename, the supply it
    now is and its outcome (criterion 8) - the one place which file each
    supply is, which the receipt view and the resolver read (criterion 10);
  - each file's rejection, supersession or re-file as its OWN entry naming
    the settlement as its cause, so every existing reader of a supply's
    state sees it unchanged (criterion 8);
  - `#2`'s own filing, whatever its outcome (criterion 12), and a new
    filing for the supply where its own receipt changes its period or
    verdict - or a hold where it lands where no slot is open (criteria 10
    and 11);
  - the QA run each new supply is owed (criterion 21), run after the
    commit as a separate, retryable step.
Nothing is deleted (criterion 9); a move is a catalogue change.

WHICH FILE IS `#1` (criterion 12, Keith 2026-10-13: always #2 for the
other): the file that is this period's supply, or the earlier-received
file where neither is.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime

from qa_tools.common import decision_log, qa_store, supply_db

_QA = f'"{qa_store.SCHEMA}"'

#: The four outcomes, as the flag form spells them (criterion 15).
SUPPLY, REFILE, REJECT, SUPERSEDE = "supply", "refile", "reject", "supersede"
OUTCOMES = (SUPPLY, REFILE, REJECT, SUPERSEDE)
#: As qa.decision_file records them.
RECORDED = {SUPPLY: "supply", REFILE: "refiled", REJECT: "rejected",
            SUPERSEDE: "superseded"}


@dataclass(frozen=True)
class PairFile:
    """One file of the pair, as it arrived."""
    filename: str
    received_at: datetime
    #: Its staged table, in staging form.
    table: str
    #: Whether the load refused it (REQ-PIPE-115 criterion 19).
    refused: bool


class Changed(decision_log.DecisionRefused):
    """What a settlement does changed between its warning and the lock
    (criterion 18) - the terminal shows it as it stands now and asks again."""


@dataclass(frozen=True)
class Answer:
    """What a person said one file is."""
    filename: str
    outcome: str
    to_period: str | None = None


@dataclass(frozen=True)
class FilePlan:
    file: PairFile
    outcome: str
    supply_id: str
    to_period: str | None = None
    #: For the supply: the period and verdict its own receipt earns, where
    #: either differs from the pair's filing (criterion 10); `held` where it
    #: lands where no slot is open (criterion 11).
    period_after: str | None = None
    classification_after: str | None = None
    new_filing: bool = False
    held: bool = False
    held_reason: dict | None = None
    #: Versions waiting in the period this file goes into, which it
    #: supersedes (REQ-PIPE-141 criterion 6's effects).
    displaced: tuple[str, ...] = ()

    @property
    def becomes_a_supply(self) -> bool:
        return self.outcome in (SUPPLY, REFILE) and not self.held

    @property
    def checked_in(self) -> str | None:
        """The period its QA run is against, where it gets one."""
        if self.outcome == REFILE:
            return self.to_period
        if self.outcome == SUPPLY and not self.held:
            return self.period_after
        return None


@dataclass(frozen=True)
class Plan:
    dataset_id: str
    pair: str
    period: str
    delivery: str
    classification: str | None
    files: tuple[FilePlan, ...] = field(default_factory=tuple)

    @property
    def runs(self) -> tuple[FilePlan, ...]:
        """The QA runs that follow, in receipt order (criterion 21)."""
        return tuple(f for f in self.files if f.becomes_a_supply)


def pair_files(conn, dataset_id: str, supply: str) -> tuple[str, str | None, list[PairFile]]:
    """(delivery, period, the pair's files in RECEIPT order) - criterion 3's
    order: earlier first, by our own receipt then receipt sequence."""
    from qa_tools.common import filing, hierarchy, load_log, supply_files

    pair = supply_files.pair_supply(supply)
    rows = conn.execute(
        f"SELECT slot, delivery FROM {filing.CURRENT} WHERE dataset_id = ? AND supply_id = ?",
        [dataset_id, pair]).fetchall()
    if not rows:
        return "", None, []
    period, delivery = rows[0]
    logical = hierarchy.dataset(dataset_id).table
    key = supply_files.staging_key_of(pair)
    ordered = supply_files.files_in_order(conn, dataset_id, delivery)
    out = []
    for filename, received in conn.execute(
            f"SELECT filename, received_instant FROM {_QA}.delivery_file "
            "WHERE delivery = ? AND dataset_id = ? "
            "ORDER BY received_instant, receipt_sequence, filename",
            [delivery, dataset_id]).fetchall():
        table = supply_files.staged_name(logical, key, ordered, filename)
        record = load_log.latest_for(table, conn=conn)
        out.append(PairFile(filename, received, table,
                            bool(record is not None and not record.loaded)))
    return delivery, period, out


def refused_before_asking(conn, dataset_id: str, supply: str) -> str | None:
    """Criterion 5: why a settlement cannot even be asked about - the named
    supply is not an open pair - or None."""
    from qa_tools.common import supply_files

    from qa_tools.common import hierarchy

    name = hierarchy.dataset(dataset_id).dataset_name
    if supply_files.open_contest(conn, dataset_id, supply) is None:
        settled = conn.execute(
            f"SELECT actor, effective_at FROM {decision_log.TABLE} WHERE dataset_id = ? "
            "AND supply = ? AND action = ? ORDER BY id DESC LIMIT 1",
            [dataset_id, supply_files.pair_supply(supply), decision_log.CHOOSE_FILE]
        ).fetchall()
        if settled:
            # WHO AND WHEN - the question a person asks next (#170).
            actor, when = settled[0]
            return (f"These two files for {name} were already settled, by {actor} on "
                    f"{str(when)[:16].replace('T', ' ')}. Nothing was recorded.")
        return (f"No pair of files for {name} is waiting to be settled here - two files "
                f"for one table whose contest is still open. Nothing was recorded.")
    found = supply_files.resolve(conn, dataset_id, supply_files.pair_supply(supply))
    if found is None or not found.period:
        # A PAIR HELD IN NO PERIOD has none to settle in - a settlement names
        # the period the pair was filed to (criterion 8).
        return (f"These two files arrived when no period of {name} was open, so the pair "
                f"is held and filed to no period - there is none to settle it in. Nothing "
                f"was recorded.")
    return None


def open_pair_in(conn, dataset_id: str, period: str, *, besides: str) -> str | None:
    """Why a settled file cannot go into `period`, where it holds ANOTHER
    pair still waiting to be settled - or None. Going in would supersede
    that pair, which a person cannot do to an open pair directly either
    (criterion 25; Keith, 2026-10-13, post-build-review #170)."""
    from qa_tools.common import dataset_blockers, supply_files

    waiting = []
    for blocker in dataset_blockers.contests(conn):
        if (blocker.dataset_id != dataset_id or not blocker.is_open
                or blocker.supply == supply_files.pair_supply(besides)):
            continue
        found = supply_files.resolve(conn, dataset_id, blocker.supply)
        if found is not None and found.period == period:
            waiting.append(" and ".join(blocker.files))
    if not waiting:
        return None
    return (f"{period} has two files of its own waiting to be settled - "
            f"{'; '.join(waiting)}. Settle that pair first, at "
            f"'{supply_files.where_to_settle(dataset_id)}', or name another period.")


def offered(file: PairFile) -> tuple[str, ...]:
    """What a file may be (criterion 7): a file the load refused, only
    rejected - never settled on the person's behalf."""
    return (REJECT,) if file.refused else OUTCOMES


def rule_broken(conn, dataset_id: str, period: str, files: list[PairFile],
                answers: list[Answer]) -> str | None:
    """Criteria 4, 6, 7 and 15's rules for a whole combination, or None.
    Each refusal says which rule."""
    names = [f.filename for f in files]
    given = [a.filename for a in answers]
    unknown = [n for n in given if n not in names]
    if unknown:
        return (f"{unknown[0]!r} is not one of the pair's files - they arrived as "
                f"{' and '.join(names)}.")
    if sorted(given) != sorted(names):
        missing = [n for n in names if n not in given]
        twice = sorted({n for n in given if given.count(n) > 1})
        return (f"each file needs exactly one outcome - {', '.join(twice)} was given more "
                f"than one" if twice else
                f"each file needs exactly one outcome - none was given for "
                f"{', '.join(missing)}")
    by_name = {f.filename: f for f in files}
    for a in answers:
        if a.outcome not in OUTCOMES:
            return f"{a.outcome!r} is not an outcome - one of {', '.join(OUTCOMES)}."
        if by_name[a.filename].refused and a.outcome != REJECT:
            return (f"{a.filename} never loaded, so it can only be rejected - nothing is "
                    f"settled on your behalf because only one file loaded.")
        if a.outcome == REFILE and not a.to_period:
            return f"a re-file of {a.filename} needs the period it belongs to."
        if a.outcome != REFILE and a.to_period:
            return f"only a re-file names a period, and {a.filename} is not re-filed."
        if a.outcome == REFILE and a.to_period == period:
            return (f"{a.filename} cannot be re-filed to {period} - that is the pair's own "
                    f"period, which is 'the supply for {period}'.")
    supplies = [a for a in answers if a.outcome == SUPPLY]
    if len(supplies) > 1:
        return f"only one file can be the supply for {period}."
    targets = [a.to_period for a in answers if a.outcome == REFILE]
    if len(set(targets)) < len(targets):
        return f"two files cannot both be re-filed to {targets[0]}."
    for a in answers:
        if a.outcome == SUPERSEDE and not supplies:
            return (f"{a.filename} can be a spare copy only where the other file is the "
                    f"supply for {period}.")
    return None


def plan(conn, *, dataset_id: str, supply: str, answers: list[Answer]) -> Plan:
    """Everything a settlement does, or a DecisionRefused naming the rule."""
    from qa_tools.common import filing, refiling, supersession, supply_files, supply_holds

    why = refused_before_asking(conn, dataset_id, supply)
    if why:
        raise decision_log.DecisionRefused(why)
    delivery, period, files = pair_files(conn, dataset_id, supply)
    broken = rule_broken(conn, dataset_id, period, files, answers)
    if broken:
        raise decision_log.DecisionRefused(broken)
    pair = supply_files.pair_supply(supply)
    second = pair[:-1] + "2"
    current = conn.execute(
        f"SELECT classification FROM {filing.CURRENT} WHERE dataset_id = ? AND supply_id = ?",
        [dataset_id, pair]).fetchall()
    classification = current[0][0] if current else None
    answer = {a.filename: a for a in answers}
    chosen = next((f for f in files if answer[f.filename].outcome == SUPPLY), files[0])
    planned = []
    for f in files:
        a = answer[f.filename]
        supply_id = pair if f is chosen else second
        fp = FilePlan(file=f, outcome=a.outcome, supply_id=supply_id, to_period=a.to_period)
        if a.outcome == REFILE:
            if not refiling._on_calendar(dataset_id, a.to_period):
                raise decision_log.DecisionRefused(
                    f"{a.to_period} is not a period {dataset_id} is delivered in - its "
                    f"calendar has no such period.")
            h = decision_log.held(conn, dataset_id, a.to_period)
            if h and h.held_as == decision_log.INHERITED:
                raise decision_log.DecisionRefused(
                    f"nothing was expected from {dataset_id} for {a.to_period}: it is "
                    f"inherited. Un-inherit it first, or re-file to another period.")
            blocked = open_pair_in(conn, dataset_id, a.to_period, besides=pair)
            if blocked:
                raise decision_log.DecisionRefused(f"{a.filename} cannot be re-filed: {blocked}")
            fp = replace(fp, displaced=tuple(supersession.waiting_in(
                conn, dataset_id, a.to_period, besides=pair)))
        elif a.outcome == SUPPLY:
            # ITS OWN RECEIPT DECIDES ITS PERIOD AND VERDICT (criteria 10, 11).
            judged = filing.assignment_at(dataset_id, supply_id, f.received_at)
            if judged.slot is None:
                fp = replace(fp, held=True, new_filing=True,
                             held_reason=supply_holds.reason_for(judged))
            else:
                verdict = filing._judged_for(dataset_id, judged.slot, f.received_at)
                moved = judged.slot != period
                blocked = moved and open_pair_in(conn, dataset_id, judged.slot, besides=pair)
                if blocked:
                    raise decision_log.DecisionRefused(
                        f"{f.filename}'s own receipt files it to {judged.slot}, and {blocked}")
                fp = replace(fp, period_after=judged.slot,
                             classification_after=verdict.classification,
                             new_filing=moved or verdict.classification != classification,
                             displaced=tuple(supersession.waiting_in(
                                 conn, dataset_id, judged.slot, besides=pair))
                             if moved else ())
        planned.append(fp)
    # A SPARE COPY ONLY BESIDE A SUPPLY KEPT IN THE PAIR'S PERIOD (criterion
    # 4): where the supply's own receipt holds it or moves it, there is
    # nothing in this period for the copy to be spare beside.
    supply_plan = next((p for p in planned if p.outcome == SUPPLY), None)
    if any(p.outcome == SUPERSEDE for p in planned) and supply_plan is not None and (
            supply_plan.held or supply_plan.period_after != period):
        where = ("is held - no period was open at its receipt" if supply_plan.held
                 else f"files it to {supply_plan.period_after}")
        raise decision_log.DecisionRefused(
            f"{supply_plan.file.filename}'s own receipt {where}, so the other file cannot "
            f"be a spare copy for {period}. Reject it or re-file it instead.")
    landing = [p.checked_in for p in planned if p.checked_in]
    if len(set(landing)) < len(landing):
        raise decision_log.DecisionRefused(
            f"both files would be filed to {landing[0]}, and a period holds one version of "
            f"a table.")
    return Plan(dataset_id=dataset_id, pair=pair, period=period, delivery=delivery,
                classification=classification, files=tuple(planned))


def _what_it_does(p: Plan) -> tuple:
    return tuple((f.file.filename, f.outcome, f.supply_id, f.to_period, f.period_after,
                  f.classification_after, f.held, tuple(sorted(f.displaced)))
                 for f in p.files)


def apply(conn, p: Plan, *, agency_id: str, collection_id: str, actor: str, reason: str,
          effective_at: str, answers: list[Answer]) -> tuple[int, tuple[int, ...]]:
    """Carry a settlement out in one transaction. Returns (the choose-file
    entry's id, the owed QA runs' ids in receipt order)."""
    from qa_tools.common import filing, supersession

    owed: list[int] = []
    opened: list[str] = []
    with decision_log.decision_transaction(conn):
        slots_touched = {p.period, *(f.to_period for f in p.files if f.to_period),
                         *(f.period_after for f in p.files if f.period_after)}
        for slot in sorted(s for s in slots_touched if s):
            decision_log.lock_slot(conn, p.dataset_id, slot)
        now = plan(conn, dataset_id=p.dataset_id, supply=p.pair, answers=answers)
        if _what_it_does(now) != _what_it_does(p):
            raise Changed(
                f"What settling the two files for {p.dataset_id} {p.period} would do has "
                f"changed since it was worked out - something was filed or decided "
                f"meanwhile. Nothing was done; ask again to see it as it stands now.")
        common = dict(agency_id=agency_id, collection_id=collection_id,
                      dataset_id=p.dataset_id, actor=actor,
                      actor_kind=decision_log.PERSON, effective_at=effective_at)
        # ONE ACT, ONE INSTANT (post-build-review #284 (B)): every entry the
        # settlement writes takes the latest instant across the pair, both its
        # files and whatever they displace - TS-80's reject of #2 stood six
        # days before the choose-file of #1.
        decision_log.act_spans(conn, p.dataset_id,
                               [p.pair, *(f.supply_id for f in p.files),
                                *(d for f in p.files for d in f.displaced)])
        with decision_log.apply_decision(conn, decision_log.Decision(
                action=decision_log.CHOOSE_FILE, supply=p.pair, from_slot=p.period,
                reason=reason, **common)) as entry_id:
            for f in p.files:
                conn.execute(
                    f"INSERT INTO {_QA}.decision_file (decision_id, filename, supply_id, "
                    "outcome, to_slot) VALUES (?, ?, ?, ?, ?)",
                    [entry_id, f.file.filename, f.supply_id, RECORDED[f.outcome],
                     f.to_period])
            for f in p.files:
                owed_id = _apply_file(conn, p, f, entry_id=entry_id, reason=reason,
                                      common=common)
                if owed_id is not None:
                    owed.append(owed_id)
            supersession.drop_if_empty(conn, p.period)
        # EACH PERIOD A FILE IS SETTLED INTO OPENS AT ITS FIRST FILING
        # (REQ-PIPE-271) - once the settlement stands, judged again under its
        # locks and recorded (post-build-review #267, S5), so a refused
        # settlement opens nothing.
        for f in p.files:
            for period in (f.to_period, f.period_after):
                if filing.open_on_refile(conn, p.dataset_id, f.supply_id, period,
                                         how="settlement", effective_at=effective_at):
                    opened.append(period)
    for period in opened:
        filing.settle_opening(conn, period, True)
    return entry_id, tuple(owed)


def _apply_file(conn, p: Plan, f: FilePlan, *, entry_id: int, reason: str,
                common: dict) -> int | None:
    """One file's effect, in the settlement's transaction - its own entry
    naming the settlement as its cause (criterion 8)."""
    from qa_tools.common import filing, recheck, supersession, supply_holds

    because = f"settled with the pair's other file: {reason}"
    is_second = f.supply_id != p.pair
    if f.outcome == REJECT:
        if is_second:
            filing.file_settled(conn, p.dataset_id, f.supply_id, p.period,
                                delivery=p.delivery, decision_id=entry_id,
                                received_at=f.file.received_at)
        schema = supply_db.REJECTED_SCHEMA
        supply_db.create_if_absent(conn, f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        with decision_log.apply_decision(conn, decision_log.Decision(
                action=decision_log.REJECT, supply=f.supply_id, from_slot=p.period,
                reason=because, caused_by_decision=entry_id, **common)):
            if not f.file.refused:
                supply_db.move_table(conn, f.file.table, supply_db.STAGING_SCHEMA, schema)
        return None
    if f.outcome == SUPERSEDE:
        filing.file_settled(conn, p.dataset_id, f.supply_id, p.period, delivery=p.delivery,
                            decision_id=entry_id, received_at=f.file.received_at)
        target = supersession.superseded_schema(p.period)
        with decision_log.apply_decision(conn, decision_log.Decision(
                action=decision_log.SUPERSEDE, supply=f.supply_id, from_slot=p.period,
                reason=because, caused_by_decision=entry_id, **common)):
            supply_db.create_if_absent(conn, f'CREATE SCHEMA IF NOT EXISTS "{target}"')
            supply_db.move_table(conn, f.file.table, supply_db.STAGING_SCHEMA, target)
        return None
    if f.outcome == REFILE:
        if is_second:
            filing.file_settled(conn, p.dataset_id, f.supply_id, f.to_period,
                                delivery=p.delivery, decision_id=entry_id,
                                received_at=f.file.received_at)
        with decision_log.apply_decision(conn, decision_log.Decision(
                action=decision_log.REFILE, supply=f.supply_id, from_slot=p.period,
                to_slot=f.to_period, reason=because, caused_by_decision=entry_id,
                **common)) as refile_id:
            if not is_second:
                filing.file_settled(conn, p.dataset_id, f.supply_id, f.to_period,
                                    delivery=p.delivery, decision_id=refile_id,
                                    received_at=f.file.received_at,
                                    branch="refiled-by-a-person")
        _displace(conn, p, f, f.to_period, common, entry_id)
        return recheck.owe(conn, dataset_id=p.dataset_id, supply_id=f.supply_id,
                           decision_id=entry_id)
    # THIS PERIOD'S SUPPLY.
    if f.held:
        filing.file_settled(conn, p.dataset_id, f.supply_id, None, delivery=p.delivery,
                            decision_id=entry_id, received_at=f.file.received_at)
        supply_holds.raise_hold(conn, dataset_id=p.dataset_id, supply_id=f.supply_id,
                                kind=supply_holds.ASSIGNMENT_RULE, reason=f.held_reason,
                                raised_by=f"choose-file {entry_id}", delivery=p.delivery)
        return None
    if f.new_filing:
        filing.file_settled(conn, p.dataset_id, f.supply_id, f.period_after,
                            delivery=p.delivery, decision_id=entry_id,
                            received_at=f.file.received_at)
    if f.period_after != p.period:
        _displace(conn, p, f, f.period_after, common, entry_id)
    return recheck.owe(conn, dataset_id=p.dataset_id, supply_id=f.supply_id,
                       decision_id=entry_id)


def _displace(conn, p: Plan, f: FilePlan, period: str, common: dict,
              entry_id: int) -> None:
    """A file going into another period supersedes the versions waiting
    there, each its own rule-actor entry (REQ-PIPE-141 criterion 6)."""
    from qa_tools.common import supersession

    for supply in f.displaced:
        supersession.supersede_by_rule(
            conn, agency_id=common["agency_id"], collection_id=common["collection_id"],
            dataset_id=p.dataset_id, supply=supply, period=period, by=f.supply_id,
            effective_at=common["effective_at"],
            reason=f"{f.supply_id} was settled into {period} in its place",
            caused_by_decision=entry_id)
