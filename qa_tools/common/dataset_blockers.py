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
    #: Held because its dataset is refused by the agreement backstop
    #: (REQ-PIPE-173) - the refusal's own hold, never "another blocker"
    #: beside it (delivery-critic on (f)-(i), finding 1).
    agreement_refused: bool = False
    #: Received while its dataset is turned off (REQ-PIPE-179 criterion 24):
    #: NOT a state needing a person, so it never blocks or reddens the page.
    turned_off: bool = False
    #: How a contested pair was settled (REQ-PIPE-194 criteria 10 and 13):
    #: {"actor", "at", "reason", "arrivalRunId", "files": [{"filename",
    #: "receivedAt", "outcome", "toPeriod", "supplyId", "runId"}]}, files in
    #: receipt order - or None.
    settlement: dict | None = None
    #: Where a later arrival's supply superseded the pair instead
    #: (criterion 10): {"supply", "receivedAt"}.
    superseded_by: dict | None = None

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
                "scheduleEnded": self.schedule_ended,
                "agreementRefused": self.agreement_refused,
                "turnedOff": self.turned_off,
                "settlement": self.settlement, "supersededBy": self.superseded_by,
                # WHERE IT IS SETTLED, for the page's own wording on any date
                # (REQ-PIPE-194 criteria 1 and 14, #171).
                "settleAt": _settle_at(self.dataset_id) if self.kind == CONTESTED else None}


def _settle_at(dataset_id: str) -> str:
    from qa_tools.common import supply_files

    return supply_files.where_to_settle(dataset_id)


def _iso(value) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _holds(db) -> list[Blocker]:
    from qa_tools.common import supply_holds

    rows = db.execute(
        "SELECT h.dataset_id, h.supply_id, h.kind, h.reason, h.raised_by, h.delivery, "
        "       h.raised_at, h.resolved_by, h.resolved_at, r.received_instant, d.effective_at, "
        "       (SELECT df.received_at FROM qa.delivery_file df "
        "         WHERE df.delivery = h.delivery AND df.dataset_id = h.dataset_id "
        "         ORDER BY df.received_instant, df.receipt_sequence LIMIT 1) "
        f"FROM qa.hold h LEFT JOIN {supply_holds._receipt_table()} r "
        "  ON r.dataset_id = h.dataset_id AND r.supply_id = h.supply_id "
        "LEFT JOIN qa.decision d ON d.id = h.resolved_by "
        "ORDER BY h.dataset_id, h.supply_id").fetchall()
    out = []
    for row in rows:
        # THE LABEL FROM CONFIGURATION AS IT STANDS (REQ-PIPE-179 criterion
        # 18), so the receipt instant travels with the hold.
        held = supply_holds._held_from(row[:10])
        effective_at, received_at = row[10], row[11]
        out.append(Blocker(
            kind=HELD, dataset_id=held.dataset_id, supply=held.supply_id,
            # The receipt where the delivery recorded one; the instant it
            # was raised only for a hold with no delivery to say.
            opened_at=received_at or _iso(held.raised_at),
            resolved_at=(_iso(effective_at or held.resolved_at)
                         if held.resolved_by is not None else None),
            reason=held.describe(), delivery=held.delivery,
            schedule_ended=held.schedule_ended, agreement_refused=held.agreement_refused,
            turned_off=held.turned_off))
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


def _settles_a_contest(action: str, actor_kind: str) -> bool:
    """THE ONE PLACE A CONTEST'S END IS COUNTED (REQ-PIPE-194 criterion 9):
    a person's settlement (choose-file, any combination including
    'neither'), or the RULE's supersession of the pair by a later arrival.
    Nothing else - a person's plain reject or supersede is refused on an
    open contest (REQ-PIPE-193 criterion 25), and an excused lateness says
    nothing about which file is the supply (post-build-review #160)."""
    from qa_tools.common import decision_log

    return action == decision_log.CHOOSE_FILE or (
        action == decision_log.SUPERSEDE and actor_kind == decision_log.RULE)


def _deciding(db) -> dict[tuple[str, str], dict]:
    """(dataset, arrival key) -> the FIRST decision that ended the contest:
    {"id", "action", "at", "actor", "reason", "superseded_by"}."""
    from qa_tools.common import decision_log

    out: dict[tuple[str, str], dict] = {}
    for (decision_id, dataset_id, supply, action, actor_kind, effective_at, actor, reason,
         superseded_by) in db.execute(
            "SELECT id, dataset_id, supply, action, actor_kind, effective_at, actor, reason, "
            "superseded_by FROM qa.decision WHERE action IN (?, ?) ORDER BY effective_at, id",
            [decision_log.CHOOSE_FILE, decision_log.SUPERSEDE]).fetchall():
        if not supply or not _settles_a_contest(action, actor_kind):
            continue
        out.setdefault((dataset_id, _arrival_of(supply)), {
            "id": decision_id, "action": action, "at": _iso(effective_at), "actor": actor,
            "reason": reason, "superseded_by": superseded_by})
    return out


def _how_it_ended(db, dataset_id: str, pair: str, delivery: str,
                  decided: dict | None) -> tuple[dict | None, dict | None]:
    """(settlement, superseded_by) for a resolved contest - from qa.decision,
    qa.decision_file and qa.delivery_file only (REQ-PIPE-194's NFR)."""
    from qa_tools.common import decision_log, supply_files

    if decided is None:
        return None, None
    if decided["action"] != decision_log.CHOOSE_FILE:
        by = decided["superseded_by"]
        received = db.execute(
            "SELECT received_at FROM qa.supply_receipt WHERE dataset_id = ? AND supply_id = ?",
            [dataset_id, by]).fetchall() if by else []
        return None, {"supply": by, "receivedAt": _iso(received[0][0]) if received else None}
    receipts = {name: _iso(at) for name, at in db.execute(
        "SELECT filename, received_at FROM qa.delivery_file WHERE delivery = ? "
        "AND dataset_id = ? ORDER BY received_instant, receipt_sequence, filename",
        [delivery, dataset_id]).fetchall()}
    rows = {name: (supply_id, outcome, to_slot) for name, supply_id, outcome, to_slot in
            db.execute("SELECT filename, supply_id, outcome, to_slot FROM qa.decision_file "
                       "WHERE decision_id = ?", [decided["id"]]).fetchall()}
    files = [{"filename": name, "receivedAt": receipts.get(name),
              "outcome": rows[name][1], "toPeriod": rows[name][2],
              "supplyId": rows[name][0],
              "runId": supply_files.run_id_of(dataset_id, rows[name][0])}
             for name in list(receipts) + sorted(set(rows) - set(receipts)) if name in rows]
    from qa_tools.common import people

    # A NAME, NOT AN EMAIL (#171 E; REQ-PIPE-147 criterion 7's rule): the
    # page is published, and every other decision on it shows a name.
    return {"actor": people.display_name(decided["actor"]), "at": decided["at"],
            "reason": decided["reason"],
            "arrivalRunId": supply_files.arrival_run_id_of(dataset_id, pair),
            "files": files}, None


def _contested(db) -> list[Blocker]:
    from qa_tools.common import asset_time, display_time, load_log, supply_db

    decided = _deciding(db)
    # EVERY LOAD THAT FAILED, NOT THE QUEUE OF ONES STILL WAITING: a
    # rejection drains load_log.failures(), and this record is the pair's
    # history - once settled it must still say which file never loaded
    # (post-build-review #172).
    failures = [r for r in load_log.latest_by_table(None, db).values() if not r.loaded]
    out = []
    for delivery, dataset_id, files, received_at in db.execute(
            "SELECT c.delivery, c.dataset_id, c.files, "
            "       (SELECT df.received_at FROM qa.delivery_file df "
            "         WHERE df.delivery = c.delivery AND df.dataset_id = c.dataset_id "
            "         ORDER BY df.received_instant, df.receipt_sequence LIMIT 1) "
            "FROM qa.delivery_contested c ORDER BY c.dataset_id, c.delivery").fetchall():
        # PYTHON'S BYTE ORDER, the order staging numbers the files in
        # (supply_files.files_in_order) - never the database collation's,
        # which on a non-C locale would name the wrong file as refused
        # (REQ-PIPE-193's file-order NFR, post-build-review #170).
        files = tuple(sorted(files or ()))
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
        # EACH FILE WITH ITS RECEIPT, AND WHERE (REQ-PIPE-194 criterion 1,
        # #171): the page reads this reason on every date, the queue item
        # only on the build's.
        received = dict(db.execute(
            "SELECT filename, received_instant FROM qa.delivery_file WHERE delivery = ? "
            "AND dataset_id = ? ORDER BY received_instant, receipt_sequence, filename",
            [delivery, dataset_id]).fetchall())
        listed = " and ".join(
            f"{name} (received {display_time.format_instant(received[name])})"
            if received.get(name) else name
            for name in (list(received) or list(files)))
        reason = (f"Two files claim this dataset's table in delivery {delivery!r}: "
                  f"{listed}. Nothing is checked until a person says what each file is, "
                  f"at '{_settle_at(dataset_id)}'.")
        if refused:
            reason += " " + " ".join(f"{name} could not be loaded ({why})."
                                     for name, why in refused)
        pair = f"{dataset_id}@{key}#1"
        ended = decided.get((dataset_id, key))
        settlement, superseded_by = _how_it_ended(db, dataset_id, pair, delivery, ended)
        out.append(Blocker(
            kind=CONTESTED, dataset_id=dataset_id, supply=pair,
            opened_at=received_at, resolved_at=ended["at"] if ended else None,
            reason=reason, files=files, load_failures=tuple(refused), delivery=delivery,
            settlement=settlement, superseded_by=superseded_by))
    return out


def _rejections(db) -> dict[tuple[str, str], dict]:
    """(dataset, arrival key) -> the first PERSON'S rejection of that
    arrival's supply: when it took effect, who, and why (REQ-PIPE-153)."""
    from qa_tools.common import people
    from qa_tools.common import decision_log

    out: dict[tuple[str, str], dict] = {}
    for dataset_id, supply, actor, actor_kind, reason, effective_at in db.execute(
            "SELECT dataset_id, supply, actor, actor_kind, reason, effective_at "
            "FROM qa.decision WHERE action = ? ORDER BY effective_at, id",
            [decision_log.REJECT]).fetchall():
        if actor_kind != decision_log.PERSON:
            continue
        out.setdefault((dataset_id, _arrival_of(supply)),
                       {"actor": people.display_name(actor), "at": _iso(effective_at),
                        "reason": reason})
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


def contests(conn=None) -> list[Blocker]:
    """Every contested pair, open or resolved - the one judgement of
    whether a contest is open, for a reader that needs only contests
    (REQ-DASH-197 criterion 4's 'two files for one table')."""
    from qa_tools.common import delivery_log

    with delivery_log._db(conn) as db:
        return _contested(db)


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
