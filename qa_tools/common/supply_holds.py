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
    ASSIGNMENT_RULE: ("file it to a slot yourself",
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
        return RESPONSES.get(self.kind, ())

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
        return (f"{self.total} supply/supplies held across "
                f"{len(self.by_dataset)} dataset(s) - {', '.join(self.datasets)}. "
                f"Each needs somebody to resolve it.")


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
        f"INSERT INTO {TABLE} (dataset_id, supply_id, kind, reason, raised_by, delivery) "
        "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (dataset_id, supply_id) DO NOTHING "
        "RETURNING dataset_id",
        [dataset_id, supply_id, kind, json.dumps(reason), raised_by, delivery]).fetchall()
    return bool(rows)


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
        f"UPDATE {TABLE} SET resolved_by = ?, resolved_at = now() "
        "WHERE dataset_id = ? AND supply_id = ? AND resolved_by IS NULL "
        "RETURNING dataset_id",
        [decision_id, dataset_id, supply_id]).fetchall()
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
    return Tally(by_dataset=tuple((row[0], row[1]) for row in by_dataset),
                  by_kind=tuple((row[0], row[1]) for row in by_kind))


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
    text = supply or ""
    if "@" in text:
        return text.rsplit("@", 1)[-1].split("#", 1)[0]
    if "__" in text:
        return text.rsplit("__", 1)[-1]
    return text


def resolve_for_supply(conn, *, dataset_id: str, supply: str,
                        decision_id: int) -> tuple[str, ...]:
    """Close any hold this decision answers, and say which.

    Returns the supply ids resolved - usually none, because most
    decisions are about supplies nobody held.

    MATCHED ON THE ARRIVAL KEY rather than on the id, for the reason
    `arrival_key_of` gives. (It used to resolve several at once for the
    delivery-level hold, retired 2026-10-02 by REQ-PIPE-105 criterion 6;
    matching on the key costs nothing and stays.)
    """
    if not supply:
        return ()
    key = arrival_key_of(supply)
    resolved = []
    for held in outstanding(conn, dataset_id=dataset_id):
        if arrival_key_of(held.supply_id) != key:
            continue
        if resolve(conn, dataset_id=dataset_id, supply_id=held.supply_id,
                    decision_id=decision_id):
            resolved.append(held.supply_id)
    return tuple(resolved)


def held_tables(conn, *, arrival_key: str) -> frozenset[str]:
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
    """
    from qa_tools.common import hierarchy

    tables = set()
    for held in outstanding(conn):
        if arrival_key_of(held.supply_id) != arrival_key:
            continue
        try:
            tables.add(hierarchy.dataset(held.dataset_id).table)
        except Exception:
            continue
    return frozenset(tables)
