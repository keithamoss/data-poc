"""Every held supply and every contested pair, open or resolved, with
the instants that bound it (REQ-PIPE-115 criteria 8, 10, 12, 24 and 27).

WHAT MAKES A DATASET RED FOR THE PERIOD ON SHOW. A supply nobody could
place, or a table two files claim, leaves its dataset with nothing that
may be checked - and since Keith's 2026-10-04 reversal that is said
ONCE, as a dataset-level red with its reason, rather than as a red per
check. The red is judged AS AT THE INSTANT ON SHOW (criterion 12), so
the build needs each one's whole life, not only whether it is open now:

- OPENED at the supply's own RECEIPT INSTANT - never the instant the
  hold was recorded, which depends on when a pass happened to run
  (Keith, 2026-10-04: rejected raised_at).
- RESOLVED at the instant the decision that ended it took effect, or
  never.

RECORDED QA METADATA ONLY: qa.hold, qa.delivery_file (through the
qa.delivery_contested view), qa.decision and the load record. Nothing
here reads a schema holding supply rows (Keith, 2026-09-27: a build may
read recorded QA results, never actual data, and never anything else).

TWO FILES FOR ONE DATASET IS THE OPPOSITE OF A CONTESTED FILE.
outstanding.CONTESTED_FILE is ONE file matching several datasets,
attributed to neither; this is SEVERAL files matching ONE dataset in one
delivery (REQ-PIPE-105 criterion 6). One label for both is the confusion
REQ-PIPE-144 took care to avoid, so they are separate kinds.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

HELD = "held"
CONTESTED = "contested"
#: A supply that arrived and could not be loaded (REQ-DASH-148).
REFUSED = "refused"


@dataclass(frozen=True)
class Blocker:
    """One held supply or contested pair over its whole life."""

    kind: str
    dataset_id: str
    supply: str
    #: The receipt instant, ISO, with the writer's offset where known.
    opened_at: str
    #: When the decision that ended it took effect, or None while open.
    resolved_at: str | None
    reason: str
    files: tuple[str, ...] = ()
    #: (file, why) for each file of a contested pair the load refused
    #: (criteria 24 and 27).
    load_failures: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    delivery: str | None = None
    #: Who ended it, where a PERSON's rejection did (REQ-PIPE-153
    #: criterion 16): {"actor", "at", "reason"}.
    rejected: dict | None = None
    #: Held because the dataset's schedule ended (REQ-PIPE-154): fixed by
    #: adding dates, never by a person filing or rejecting it (#132 A3).
    schedule_ended: bool = False

    @property
    def is_open(self) -> bool:
        return self.resolved_at is None

    def open_at(self, instant: datetime) -> bool:
        """Whether it was open at `instant` - from receipt until the
        resolving decision took effect."""
        opened = datetime.fromisoformat(self.opened_at)
        if instant < opened:
            return False
        return self.resolved_at is None or instant < datetime.fromisoformat(self.resolved_at)

    def as_record(self) -> dict:
        return {"kind": self.kind, "datasetId": self.dataset_id, "supply": self.supply,
                "openedAt": self.opened_at, "resolvedAt": self.resolved_at,
                "reason": self.reason, "files": list(self.files),
                "loadFailures": [{"file": f, "why": w} for f, w in self.load_failures],
                "delivery": self.delivery, "rejected": self.rejected,
                "scheduleEnded": self.schedule_ended}


def _iso(value) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _holds(db) -> list[Blocker]:
    from qa_tools.common import supply_holds

    rows = db.execute(
        "SELECT h.dataset_id, h.supply_id, h.kind, h.reason, h.raised_by, h.delivery, "
        "       h.raised_at, h.resolved_by, h.resolved_at, d.effective_at, "
        "       (SELECT df.received_at FROM qa.delivery_file df "
        "         WHERE df.delivery = h.delivery AND df.dataset_id = h.dataset_id "
        "         ORDER BY df.received_instant, df.receipt_sequence LIMIT 1) "
        "FROM qa.hold h LEFT JOIN qa.decision d ON d.id = h.resolved_by "
        "ORDER BY h.dataset_id, h.supply_id").fetchall()
    out = []
    for row in rows:
        held = supply_holds._held_from(row[:9])
        effective_at, received_at = row[9], row[10]
        out.append(Blocker(
            kind=HELD, dataset_id=held.dataset_id, supply=held.supply_id,
            # The receipt where the delivery recorded one; the instant it
            # was raised only for a hold with no delivery to say.
            opened_at=received_at or _iso(held.raised_at),
            resolved_at=(_iso(effective_at or held.resolved_at)
                         if held.resolved_by is not None else None),
            reason=held.describe(), delivery=held.delivery,
            schedule_ended=held.schedule_ended))
    return out


def _arrival_of(supply: str) -> str:
    """The arrival key of a supply id or a staged table's name.

    NOT supply_holds.arrival_key_of() alone: a contested pair's tables
    carry an ORDINAL after the key (`cp_clients__<key>__2`), and taking
    the last `__` segment reads the ordinal as the arrival - so a
    decision choosing between the two files never ended the contest.
    """
    from qa_tools.common import supply_db, supply_holds

    if "@" not in supply:
        parts = supply_db.split_staged(supply)
        if parts:
            return parts[1]
    return supply_holds.arrival_key_of(supply)


def _decided_keys(db) -> dict[tuple[str, str], str]:
    """(dataset, arrival key) -> the earliest instant a person's decision
    about that arrival's supply took effect. A refusal the rule recorded
    is not a choice between files, so it does not count."""
    from qa_tools.common import decision_log

    out: dict[tuple[str, str], str] = {}
    for dataset_id, supply, action, effective_at in db.execute(
            "SELECT dataset_id, supply, action, effective_at FROM qa.decision "
            "ORDER BY effective_at, id").fetchall():
        # A DECISION WITH NO SUPPLY is about a period, not an arrival - a
        # mark that a period was not supplied (REQ-PIPE-132) - so it
        # decides nothing about any arrival's files.
        if action in decision_log.RECORDS_A_REFUSAL or not supply:
            continue
        out.setdefault((dataset_id, _arrival_of(supply)), _iso(effective_at))
    return out


def _contested(db) -> list[Blocker]:
    from qa_tools.common import asset_time, load_log, supply_db

    decided = _decided_keys(db)
    failures = load_log.failures(conn=db)
    out = []
    for delivery, dataset_id, files, received_at in db.execute(
            "SELECT c.delivery, c.dataset_id, c.files, "
            "       (SELECT df.received_at FROM qa.delivery_file df "
            "         WHERE df.delivery = c.delivery AND df.dataset_id = c.dataset_id "
            "         ORDER BY df.received_instant, df.receipt_sequence LIMIT 1) "
            "FROM qa.delivery_contested c ORDER BY c.dataset_id, c.delivery").fetchall():
        files = tuple(files or ())
        key = asset_time.arrival_key(received_at)
        # THE ORDINAL IS THE FILE'S PLACE IN NAME ORDER - the same rule
        # supply_db.expected_tables() stages them under - so a refused
        # load can be said in terms of the file a person recognises.
        refused = []
        for record in failures:
            parts = supply_db.split_staged(record.physical)
            if record.dataset_id != dataset_id or not parts or parts[1] != key:
                continue
            try:
                name = files[int(parts[2]) - 1]
            except (ValueError, IndexError):
                name = record.physical
            refused.append((name, record.reason or "the load failed"))
        listed = " and ".join(files)
        reason = (f"Two files claim this dataset's table in delivery {delivery!r}: "
                  f"{listed}. Nothing is checked until a person chooses one.")
        if refused:
            reason += " " + " ".join(f"{name} could not be loaded ({why})."
                                     for name, why in refused)
        out.append(Blocker(
            kind=CONTESTED, dataset_id=dataset_id, supply=f"{dataset_id}@{key}#1",
            opened_at=received_at, resolved_at=decided.get((dataset_id, key)),
            reason=reason, files=files, load_failures=tuple(refused), delivery=delivery))
    return out


def _rejections(db) -> dict[tuple[str, str], dict]:
    """(dataset, arrival key) -> the first PERSON'S rejection of that
    arrival's supply: when it took effect, who, and why (REQ-PIPE-153)."""
    from qa_tools.common import decision_log

    out: dict[tuple[str, str], dict] = {}
    for dataset_id, supply, actor, actor_kind, reason, effective_at in db.execute(
            "SELECT dataset_id, supply, actor, actor_kind, reason, effective_at "
            "FROM qa.decision WHERE action = ? ORDER BY effective_at, id",
            [decision_log.REJECT]).fetchall():
        if actor_kind != decision_log.PERSON:
            continue
        out.setdefault((dataset_id, _arrival_of(supply)),
                       {"actor": actor, "at": _iso(effective_at), "reason": reason})
    return out


def _earlier(a: str | None, b: str | None) -> str | None:
    if a is None or b is None:
        return a or b
    return a if datetime.fromisoformat(a) <= datetime.fromisoformat(b) else b


def _failed_loads(db) -> list[Blocker]:
    """Every supply that could not be loaded, over its whole life
    (REQ-DASH-148 criteria 1 and 3, REQ-PIPE-153 criteria 2 and 3).

    OPEN FROM THE SUPPLY'S OWN RECEIPT, not from when its load record was
    written; CLOSED by the next record for the same table saying it
    loaded, or by a person's rejection of that supply, whichever came
    first. Derived from the load record and the decision log alone - a
    rejection writes nothing to the load record (153 criterion 3).

    A refused file belonging to a contested pair is the contest's to
    report (REQ-PIPE-115 criterion 27), so it is not listed here.
    """
    from qa_tools.common import load_log, supply_db

    in_contest = {(d, p) for d, p in _refused_in_contests(db)}
    rejected = _rejections(db)
    by_table: dict[str, list] = {}
    for record in load_log.records(conn=db):
        by_table.setdefault(record.physical, []).append(record)
    out = []
    for physical, history in sorted(by_table.items()):
        parts = supply_db.split_staged(physical)
        if not parts:
            continue
        for i, record in enumerate(history):
            if record.loaded or (i and not history[i - 1].loaded):
                continue
            if (record.dataset_id, physical) in in_contest:
                continue
            reloaded = next((r.recorded_at for r in history[i + 1:] if r.loaded), None)
            rejection = rejected.get((record.dataset_id, parts[1]))
            resolved = _earlier(reloaded, rejection["at"] if rejection else None)
            out.append(Blocker(
                kind=REFUSED, dataset_id=record.dataset_id,
                supply=f"{record.dataset_id}@{parts[1]}",
                opened_at=refused_opened_at(db, record),
                resolved_at=resolved,
                reason=(f"The supply could not be loaded: "
                        f"{(record.reason or 'no reason was recorded').rstrip().rstrip('.')}."
                        f" Nothing can read the table, so nothing is checked."),
                delivery=record.delivery,
                rejected=(rejection if rejection and resolved == rejection["at"] else None)))
    return out


def _refused_in_contests(db) -> set[tuple[str, str]]:
    from qa_tools.common import asset_time, load_log, supply_db

    keys = {(dataset_id, asset_time.arrival_key(received_at))
            for dataset_id, received_at in db.execute(
                "SELECT c.dataset_id, (SELECT df.received_at FROM qa.delivery_file df "
                "  WHERE df.delivery = c.delivery AND df.dataset_id = c.dataset_id "
                "  ORDER BY df.received_instant LIMIT 1) "
                "FROM qa.delivery_contested c").fetchall() if received_at}
    out = set()
    for record in load_log.records(conn=db):
        parts = supply_db.split_staged(record.physical)
        if not record.loaded and parts and (record.dataset_id, parts[1]) in keys:
            out.add((record.dataset_id, record.physical))
    return out


def all_blockers(conn=None) -> list[Blocker]:
    """Every held supply, contested pair and failed load, open or resolved."""
    from qa_tools.common import delivery_log

    with delivery_log._db(conn) as db:
        return _holds(db) + _contested(db) + _failed_loads(db)


def refused_in_a_contest(conn=None) -> frozenset[tuple[str, str]]:
    """(dataset, physical) for every refused load that belongs to a
    contested pair - reported by the contest, never as its own item
    (criterion 27)."""
    from qa_tools.common import delivery_log

    with delivery_log._db(conn) as db:
        return frozenset(_refused_in_contests(db))


def refused_opened_at(db, record) -> str:
    """When a refused load's signal opens: the supply's own receipt
    (REQ-DASH-148 criterion 3), falling back to the load record only where
    no receipt was recorded. ONE answer for the blocker and the outstanding
    item - two answers is how the item went missing on the scenario's own
    date while the blocker showed (post-build-review #118 D-B)."""
    received = db.execute(
        "SELECT received_at FROM qa.delivery_file WHERE delivery = ? AND dataset_id = ? "
        "ORDER BY received_instant, receipt_sequence LIMIT 1",
        [record.delivery, record.dataset_id]).fetchall()
    return received[0][0] if received else record.recorded_at


def unsettled_failures_opened(conn=None) -> list[tuple]:
    """unsettled_failures(), each with the instant its signal opens."""
    from qa_tools.common import delivery_log

    with delivery_log._db(conn) as db:
        return [(record, refused_opened_at(db, record))
                for record in unsettled_failures(conn=db)]


def unsettled_failures(conn=None) -> list:
    """load_log.failures(), which since REQ-PIPE-153 already leaves out
    every failed load a person's rejection has settled."""
    from qa_tools.common import load_log

    return load_log.failures(conn=conn)
