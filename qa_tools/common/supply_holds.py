"""Supplies nothing can place, kept until somebody places them
(REQ-PIPE-064, made durable by REQ-PIPE-078).

A HOLD IS THE CORRECT OUTPUT OF THE RULE, NOT A DEFECT IN IT. Where a
rule genuinely cannot know, it says so rather than committing silently
- a standing principle in this design rather than a one-off, and it has
now produced three separate requirements in this area alone. Defaulting
a supply nothing can place into a future slot is the forward cascade
again, arriving by the recovery path rather than by the rule.

THEY AGGREGATE, and that is a scale requirement rather than a
presentation choice. At two datasets a banner per held supply is fine;
at the ~30 this is a PoC for it is thirty banners, and a banner per
dataset is exactly how people learn to ignore a whole class of warning.
So this counts and groups, and never returns one element per supply -
`tally()` does it in SQL for the same reason (criterion 8).

IT USED TO LIVE FOR ONE RUN, and that is what REQ-PIPE-078 changed.
`holds_in()` aggregated a run's own assignments in memory and threw
them away; `filing.file_arrivals()` skipped a held dataset with a bare
`continue`. Both were correct about the hold and wrong about its
lifetime: the state a person was meant to drain was a message that
scrolled past in one run's output. `qa.hold` is where one lives now,
and only a recorded decision ends it.

RAISED ONCE, RESOLVED ONCE, and that is a different discipline from
the write-once filing beside it (NFR 4). A filing must never be
re-derived against a schedule that has moved on, so `qa.filing` is
write-once. A hold is mutable by design - resolving it is the whole
point - so the two are deliberately separate tables and this paragraph
exists so nobody has to infer the rule from the absence of a trigger.

THE TWO KINDS ARE RECORDED ON THE SAME TERMS (criterion 3) and
RESOLVED DIFFERENTLY, which is why `kind` is a column rather than a
detail in the reason. A DELIVERY-LEVEL hold (REQ-PIPE-059) is two
files in one delivery both matching one dataset: it needs somebody to
say which FILE is the supply. An ASSIGNMENT-RULE hold (REQ-PIPE-064)
is a supply the rule found no claimable slot for: it needs somebody to
say which SLOT it fills. A queue that cannot tell them apart cannot
say what to do about either.

WHAT A HOLD COSTS, stated because the blast radius is not zero. The
held supply stays STAGED - staging asserts only that this landed at
this time, which is true wherever it eventually files, so holding costs
nothing and loses nothing there. It is NOT QA'd: the single-table
checks could run without a period, but drift and previous-period
comparison cannot, so partial QA produces a verdict that has to be
thrown away once the slot is known - or worse, a GREEN one sitting in
history against no period at all. Every other dataset in the delivery
is processed normally, but any cross-table check reading a held table
reads RED naming it. Scoped to what actually depends on the held thing.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from qa_tools.common import replay_clock as _replay_clock
from qa_tools.common.assignment import Assignment

TABLE = "qa.hold"

#: THE DELIVERY-LEVEL KIND IS RETIRED (REQ-PIPE-105 criterion 6, Keith,
#: 2026-10-02): two files for one dataset in one arrival are CONTESTED
#: now, filed and visible to the promotion gate, rather than held. The
#: kind went rather than staying defined and unable to fire.
#:
#: The assignment rule found no slot it could confidently claim
#: (REQ-PIPE-064). Resolved by somebody saying which slot it fills.
ASSIGNMENT_RULE = "assignment-rule"

KINDS = (ASSIGNMENT_RULE,)

#: What a person can do about each kind. NAMED, NEVER GUESSED: a hold
#: whose record does not carry the resolution path is indistinguishable
#: from a bug (NFR 2), and the two kinds genuinely need different acts.
RESPONSES = {
    # PLACE, THE OPERATION THAT NOW EXISTS (REQ-PIPE-163 criterion 12) - it
    # said "file it to a slot yourself" while there was no way to.
    ASSIGNMENT_RULE: ("place it into the period it belongs to",
                       "reject the supply"),
}


@dataclass(frozen=True)
class HeldSupply:
    """One supply the rule declined to place, and why."""

    dataset_id: str
    supply_id: str
    unavailable: tuple[tuple[str, str], ...]

    @classmethod
    def of(cls, decided: Assignment) -> "HeldSupply":
        return cls(dataset_id=decided.dataset_id, supply_id=decided.supply_id,
                    unavailable=decided.unavailable)


@dataclass(frozen=True)
class Holds:
    """Every outstanding hold, as ONE thing rather than a list of
    banners (criterion 8)."""

    supplies: tuple[HeldSupply, ...]

    @property
    def total(self) -> int:
        return len(self.supplies)

    @property
    def datasets(self) -> tuple[str, ...]:
        return tuple(sorted({h.dataset_id for h in self.supplies}))

    @property
    def needs_action(self) -> bool:
        """Criterion 5: a hold is an event NEEDING ACTION, not an
        informational one. The distinction is the whole difference
        between a queue somebody drains and a line in a log."""
        return self.total > 0

    def summary(self) -> str:
        """One line for the whole class, never one per supply."""
        if not self.supplies:
            return "No supply is currently held."
        datasets = self.datasets
        return (f"{self.total} supply/supplies held across "
                f"{len(datasets)} dataset(s) - {', '.join(datasets)}. "
                f"Each needs somebody to assign it to a slot or reject it.")


def _schedule_file() -> str:
    from qa_tools.common import agreement

    path = agreement.CALENDAR_YAML
    root = path.parent.parent
    return str(path.relative_to(root))


#: Where a dataset's delivery dates are authored (REQ-PIPE-154 criterion 3):
#: the agreement's own file, relative to the repository - one path, never a
#: second literal copy of it (REQ-PIPE-110 criterion 17).
SCHEDULE_FILE = _schedule_file()


def reason_for(decided: Assignment) -> dict:
    """What a hold records about why the rule could not place a supply -
    the one place its shape is decided. A schedule-ended hold carries that
    as a field, the last period, and the file and command that fix it
    (REQ-PIPE-154 criteria 1-3)."""
    reason = {"unavailable": [list(pair) for pair in decided.unavailable],
              "considered": list(decided.considered)}
    if decided.schedule_ended:
        reason.update(schedule_ended=True, last_period=decided.last_period,
                      fix_file=SCHEDULE_FILE)
        try:
            from qa_tools.common import schedule
            calendar = schedule.calendar_for_dataset(decided.dataset_id).name
            year = (decided.received_at.year if decided.received_at else None)
            reason["fix_command"] = (f"mothman schedule candidate-dates --calendar {calendar}"
                                     + (f" --year {year}" if year else ""))
        except Exception:  # noqa: BLE001 - the file alone is still the fix
            pass
    if decided.agreement_refused:
        reason.update(agreement_refused=True, refusal=decided.agreement_refused)
    return reason


def holds_in(decisions) -> Holds:
    """The holds among a run's assignments, before anything is recorded.

    STILL IN MEMORY, and still useful: this is what the assignment pass
    produces, and `record_assignment_holds()` is what makes it durable.
    Keeping them separate means the rule can be exercised without a
    database, which is how most of its own tests are written.
    """
    return Holds(supplies=tuple(HeldSupply.of(d) for d in decisions if d.is_held))


@dataclass(frozen=True)
class Held:
    """One outstanding hold, as recorded."""

    dataset_id: str
    supply_id: str
    kind: str
    reason: dict
    raised_by: str
    delivery: str | None
    raised_at: datetime
    resolved_by: int | None = None
    resolved_at: datetime | None = None

    @property
    def outstanding(self) -> bool:
        return self.resolved_by is None

    @property
    def responses(self) -> tuple[str, ...]:
        # ADD DATES, AND NOTHING ELSE (Keith, 2026-10-07, post-build-review
        # #132 A3): a supply held because its schedule ended files itself
        # once the dates exist, so filing it by hand or rejecting it is the
        # wrong fix to offer.
        if self.schedule_ended:
            return (f"add the next delivery dates to {SCHEDULE_FILE} - it files itself "
                    f"on the next processing pass",)
        if self.agreement_refused:
            # OURS TO FIX, IN CONFIGURATION (REQ-PIPE-173): it files itself
            # once the agreement matches its recorded judgements again.
            return ("restore the delivery agreement or declare the correction - it files "
                    "itself on the next processing pass",)
        if self.correction:
            # REQ-PIPE-170 criterion 8: a confirmed correction left it no period.
            # NOT PROMOTE (post-build-review #173): a held supply's data was
            # never checked against a period, so promoting it is refused. A
            # re-file is refused too - it has no period to leave.
            return (self._place_response(),
                    "declare a correction adding a date that covers its receipt",
                    "reject the supply")
        if self.kind == ASSIGNMENT_RULE:
            return (self._place_response(), "reject the supply")
        return RESPONSES.get(self.kind, ())

    def _place_response(self) -> str:
        """Place, naming the terminal screen and the exact command, its
        supply and dataset filled in (REQ-PIPE-163 criterion 12)."""
        from qa_tools.common import placing

        return (f"{RESPONSES[ASSIGNMENT_RULE][0]} - at '{placing.where_to_decide(self.dataset_id)}', "
                f"or `{placing.flag_form(self.dataset_id, self.supply_id)}`")

    @property
    def place_command(self) -> str | None:
        """The command that places it, or None where placing is not how this
        hold is resolved (schedule ended, agreement refused)."""
        from qa_tools.common import placing

        if self.schedule_ended or self.agreement_refused or self.kind != ASSIGNMENT_RULE:
            return None
        return placing.flag_form(self.dataset_id, self.supply_id)

    @property
    def correction(self) -> str | None:
        """The confirmed correction that held it (REQ-PIPE-170), from the record."""
        return self.reason.get("correction")

    @property
    def agreement_refused(self) -> bool:
        """Held because its dataset is refused (REQ-PIPE-173) - from the record."""
        return self.reason.get("agreement_refused") is True

    @property
    def schedule_ended(self) -> bool:
        """Held because the dataset's schedule ran out (REQ-PIPE-154
        criterion 2) - read from the record, never from its prose."""
        return self.reason.get("schedule_ended") is True

    @property
    def unavailable(self) -> tuple[tuple[str, str], ...]:
        """Each slot considered and what made it unavailable, for an
        assignment-rule hold."""
        return tuple((pair[0], pair[1])
                      for pair in (self.reason.get("unavailable") or ()))

    def describe(self) -> str:
        """Why this supply is held, in words a person can act on.

        Criterion 1 asks the record to name the supply and the reason;
        this is that record read back, and it says what to do about it
        because a hold nobody can clear is indistinguishable from a bug.
        """
        if self.correction:
            return (f"Held when correction {self.correction} was confirmed: the corrected "
                    f"calendar offers it no period"
                    + (f" ({self.reason.get('correction_reason')})"
                       if self.reason.get("correction_reason") else "") + ".")
        if self.schedule_ended:
            # THE FIX IS OURS, NOT THE SUPPLIER'S (REQ-PIPE-154 criteria 1
            # and 3), so the reason says where to make it.
            command = self.reason.get("fix_command")
            how = f" `{command}` proposes them." if command else ""
            from qa_tools.common import hierarchy

            try:
                name = hierarchy.dataset(self.dataset_id).dataset_name
            except Exception:  # noqa: BLE001 - a dataset since removed keeps its id
                name = self.dataset_id
            # THE DATASET'S NAME, not its id (#132 A3 - it read "cp-clients's").
            return (f"{self.supply_id} arrived after the {name} schedule ended - "
                    f"its last authored period is {self.reason.get('last_period')}, and "
                    f"there is no later date to file it to. Add dates to the dataset's "
                    f"calendar in {SCHEDULE_FILE}.{how} The next processing pass then "
                    f"files it by the rule. Raised by {self.raised_by}.")
        if self.agreement_refused:
            # OUR CONFIGURATION, NOT THE SUPPLIER (REQ-PIPE-173 criterion 2).
            return (f"{self.supply_id} is held because its dataset is refused.\n"
                    f"{self.reason.get('refusal', '')}\nThe next processing pass files it "
                    f"by the rule once the agreement matches again. Raised by "
                    f"{self.raised_by}.")
        reasons = "; ".join(f"{name}: {why}" for name, why in self.unavailable)
        why = (f"{self.supply_id} could not be placed - "
                f"{reasons or 'no slot was open'}")
        return (f"{why}. It stays staged and is not checked until somebody "
                f"resolves it. Raised by {self.raised_by}.")


@dataclass(frozen=True)
class Tally:
    """How many holds there are and where, WITHOUT reading one row per
    supply (criterion 8).

    The whole queue at thirty datasets is a `GROUP BY`, not a fetch of
    every held supply followed by counting them in Python - which is
    the same design that turns one banner into thirty.
    """

    by_dataset: tuple[tuple[str, int], ...]
    by_kind: tuple[tuple[str, int], ...]
    #: (datasets, supplies) held because their schedule ended (REQ-PIPE-154
    #: criterion 6) - counted apart, since the fix is configuration.
    schedule_ended: tuple[int, int] = (0, 0)

    @property
    def total(self) -> int:
        return sum(n for _, n in self.by_dataset)

    @property
    def datasets(self) -> tuple[str, ...]:
        return tuple(name for name, _ in self.by_dataset)

    @property
    def needs_action(self) -> bool:
        return self.total > 0

    def summary(self) -> str:
        if not self.total:
            return "No supply is currently held."
        line = (f"{self.total} supply/supplies held across "
                f"{len(self.by_dataset)} dataset(s) - {', '.join(self.datasets)}. "
                f"Each needs somebody to resolve it.")
        datasets, supplies = self.schedule_ended
        if supplies:
            line += (f" {supplies} of them, across {datasets} dataset(s), because the "
                     f"dataset's schedule has ended - add dates in {SCHEDULE_FILE} and the "
                     f"next processing pass files them.")
        return line


def raise_hold(conn, *, dataset_id: str, supply_id: str, kind: str,
                reason: dict, raised_by: str, delivery: str | None = None) -> bool:
    """Record a hold, once.

    Returns True where a row was written, False where this supply was
    already held - the ordinary case on every run after the first,
    because a hold is re-encountered by every pass over the same
    delivery until somebody resolves it.

    ON CONFLICT DO NOTHING IS CRITERION 2 IN ONE CLAUSE: a later run
    passing over the same held supply must not clear it, and must not
    re-raise it either as though it were new. The first run to see it
    owns `raised_by`, which is what makes "when did this start" a
    question with an answer.
    """
    if kind not in KINDS:
        raise ValueError(f"unknown hold kind {kind!r} - expected one of {KINDS}")
    rows = conn.execute(
        f"INSERT INTO {TABLE} (dataset_id, supply_id, kind, reason, raised_by, delivery, "
        "raised_at) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (dataset_id, supply_id) DO NOTHING "
        "RETURNING dataset_id",
        [dataset_id, supply_id, kind, json.dumps(reason), raised_by, delivery,
         _replay_clock.now()]).fetchall()
    return bool(rows)


def raise_again(conn, *, dataset_id: str, supply_id: str, kind: str, reason: dict,
                raised_by: str) -> None:
    """Hold a supply that may have been held before (REQ-PIPE-170 criterion
    8; delivery-critic on 170, D4): a hold is one row per supply for all
    time, so raise_hold's ON CONFLICT DO NOTHING left a supply whose earlier
    hold was resolved filed nowhere with no hold open. A resolved row is
    reopened with the new reason; an open one is left as it is."""
    conn.execute(
        f"INSERT INTO {TABLE} (dataset_id, supply_id, kind, reason, raised_by, raised_at) "
        "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (dataset_id, supply_id) DO UPDATE SET "
        "kind = EXCLUDED.kind, reason = EXCLUDED.reason, raised_by = EXCLUDED.raised_by, "
        "raised_at = EXCLUDED.raised_at, resolved_by = NULL, resolved_at = NULL "
        f"WHERE {TABLE}.resolved_by IS NOT NULL",
        [dataset_id, supply_id, kind, json.dumps(reason), raised_by, _replay_clock.now()])


def resolve(conn, *, dataset_id: str, supply_id: str, decision_id: int) -> bool:
    """Close a hold, naming the decision that closed it (criterion 6).

    Returns True where an outstanding hold was closed, False where
    there was none - so a promotion or rejection of a supply nobody
    held is not an error, it is simply the ordinary path.

    ONLY AN OUTSTANDING HOLD IS TOUCHED (`WHERE resolved_by IS NULL`).
    Re-resolving a closed one would rewrite which decision ended it,
    and the record exists to answer exactly that.
    """
    rows = conn.execute(
        f"UPDATE {TABLE} SET resolved_by = ?, resolved_at = ? "
        "WHERE dataset_id = ? AND supply_id = ? AND resolved_by IS NULL "
        "RETURNING dataset_id",
        [decision_id, _replay_clock.now(), dataset_id, supply_id]).fetchall()
    return bool(rows)


def _held_from(row) -> Held:
    dataset_id, supply_id, kind, reason, raised_by, delivery, raised_at, \
        resolved_by, resolved_at = row
    if isinstance(reason, str):
        reason = json.loads(reason)
    return Held(dataset_id=dataset_id, supply_id=supply_id, kind=kind,
                 reason=reason or {}, raised_by=raised_by, delivery=delivery,
                 raised_at=raised_at, resolved_by=resolved_by,
                 resolved_at=resolved_at)


_COLUMNS = ("dataset_id, supply_id, kind, reason, raised_by, delivery, "
            "raised_at, resolved_by, resolved_at")


def outstanding(conn, *, dataset_id: str | None = None) -> tuple[Held, ...]:
    """Every hold still waiting on a person, oldest first.

    A RESOLVED HOLD IS NOT RETURNED and is not deleted either: the row
    stays, pointing at the decision that ended it, because "why is this
    no longer waiting on me" is a question somebody asks later.
    """
    where = "resolved_by IS NULL"
    params: list = []
    if dataset_id is not None:
        where += " AND dataset_id = ?"
        params.append(dataset_id)
    rows = conn.execute(
        f"SELECT {_COLUMNS} FROM {TABLE} WHERE {where} "
        "ORDER BY raised_at, dataset_id, supply_id", params).fetchall()
    return tuple(_held_from(row) for row in rows)


def hold_on(conn, dataset_id: str, supply_id: str) -> Held | None:
    """This supply's outstanding hold, or None where it has none."""
    rows = conn.execute(
        f"SELECT {_COLUMNS} FROM {TABLE} "
        "WHERE dataset_id = ? AND supply_id = ? AND resolved_by IS NULL",
        [dataset_id, supply_id]).fetchall()
    return _held_from(rows[0]) if rows else None


def held_datasets(conn, *, dataset_ids=None) -> frozenset[str]:
    """Which datasets have a supply held right now.

    What criterion 5 and criterion 9 are asked in practice - do not
    promote this, do not check it - so it answers in one query rather
    than making every caller fetch the holds and reduce them.
    """
    where = "resolved_by IS NULL"
    params: list = []
    if dataset_ids is not None:
        ids = list(dataset_ids)
        if not ids:
            return frozenset()
        where += f" AND dataset_id IN ({', '.join('?' for _ in ids)})"
        params.extend(ids)
    rows = conn.execute(
        f"SELECT DISTINCT dataset_id FROM {TABLE} WHERE {where}", params).fetchall()
    return frozenset(row[0] for row in rows)


def tally(conn) -> Tally:
    """How many outstanding holds, by dataset and by kind (criterion 8).

    TWO AGGREGATES RATHER THAN ONE FETCH. The queue's headline is a
    number and its grouping is a handful of rows; neither needs the
    held supplies themselves, and at thirty datasets over years the
    difference between a `GROUP BY` and a full read is the difference
    between a page that loads and one nobody opens.
    """
    by_dataset = conn.execute(
        f"SELECT dataset_id, count(*) FROM {TABLE} WHERE resolved_by IS NULL "
        "GROUP BY dataset_id ORDER BY dataset_id").fetchall()
    by_kind = conn.execute(
        f"SELECT kind, count(*) FROM {TABLE} WHERE resolved_by IS NULL "
        "GROUP BY kind ORDER BY kind").fetchall()
    ended = conn.execute(
        f"SELECT count(DISTINCT dataset_id), count(*) FROM {TABLE} WHERE resolved_by IS NULL "
        "AND (reason->>'schedule_ended')::boolean IS TRUE").fetchall()[0]
    return Tally(by_dataset=tuple((row[0], row[1]) for row in by_dataset),
                  by_kind=tuple((row[0], row[1]) for row in by_kind),
                  schedule_ended=(int(ended[0]), int(ended[1])))


def arrival_key_of(supply: str) -> str:
    """The arrival a supply belongs to, from either name it goes by.

    A SUPPLY ID IS NOT A TABLE NAME, and the key they share is the only
    safe join between them (post-build-review #64). A decision names
    the physical table `cp_clients__202605010100000000`; a hold names
    the supply `cp-clients@202605010100000000`. Matching the two on
    equality silently resolves nothing, which is the worst of the
    available failures: the decision lands, the hold stays, and the
    queue keeps asking for work somebody has already done.
    """
    from qa_tools.common import supply_db, supply_files

    text = supply or ""
    if "@" in text:
        return supply_files.staging_key_of(text)
    # A TABLE'S KEY IS ITS SECOND SEGMENT (REQ-PIPE-193 criterion 13): the
    # last one is a pair's ordinal (`cp_clients__<key>__2`), not its key.
    parts = supply_db.split_staged(text)
    if parts:
        return parts[1]
    return text


def resolve_for_supply(conn, *, dataset_id: str, supply: str,
                        decision_id: int) -> tuple[str, ...]:
    """Close any hold this decision answers, and say which.

    Returns the supply ids resolved - usually none, because most
    decisions are about supplies nobody held.

    MATCHED ON THE SUPPLY, by the one resolver (REQ-PIPE-193 criterion 13,
    post-build-review #170). A decision may name a physical table rather
    than a supply id (post-build-review #64), so a table is resolved to its
    supply first; the arrival key alone would let a decision about one
    file of a pair resolve the other file's hold.
    """
    from qa_tools.common import supply_files

    if not supply:
        return ()
    about = supply if "@" in supply else (
        supply_files.supply_for_table(conn, dataset_id, supply) or supply)
    resolved = []
    for held in outstanding(conn, dataset_id=dataset_id):
        if held.supply_id != about:
            continue
        if resolve(conn, dataset_id=dataset_id, supply_id=held.supply_id,
                    decision_id=decision_id):
            resolved.append(held.supply_id)
    return tuple(resolved)


def held_tables(conn, *, arrival_key: str, supply: str | None = None) -> frozenset[str]:
    """The LOGICAL TABLE NAMES a run of THIS ARRIVAL must not build a view
    for - the tables whose supply in this arrival is held.

    SCOPED TO THE ARRIVAL (found 2026-10-05 by the sprint-6
    delivery-critic). It used to return every dataset with ANY open hold,
    so one held supply withheld the table from every later run of that
    dataset - and once REQ-PIPE-115 ran no tool for a withheld own table,
    eight on-time, filed Case Workers supplies got no QA at all and read
    green. A hold is about one supply; a dataset's next supply is checked
    on its own terms (REQ-PIPE-078 criterion 9).

    The translation from dataset id to table name lives here rather
    than at each call site, because there are two warehouse builders
    and a third would make three copies of the same lookup - and the
    one that gets it wrong builds a view for a held supply, which is
    criterion 9 failing silently in the direction that produces a
    verdict rather than an error.

    A DATASET THE TREE NO LONGER KNOWS IS SKIPPED rather than raising.
    A hold outlives the schedule it was raised under, and a run that
    cannot start because a retired dataset is still held is a worse
    failure than a view nothing reads.

    A RUN ABOUT ONE SUPPLY (`supply`) is withheld its own table only where
    THAT supply is held (REQ-PIPE-193 criterion 13, #170): a settled
    pair's two files share an arrival, and one file's hold says nothing
    about the other. Other datasets' holds in the arrival still count.
    """
    from qa_tools.common import hierarchy, supply_files

    own = supply_files.dataset_of(supply) if supply else None
    tables = set()
    for held in outstanding(conn):
        if own is not None and held.dataset_id == own:
            if held.supply_id != supply:
                continue
        elif arrival_key_of(held.supply_id) != arrival_key:
            continue
        try:
            tables.add(hierarchy.dataset(held.dataset_id).table)
        except Exception:
            continue
    return frozenset(tables)
