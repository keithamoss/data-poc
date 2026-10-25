"""The promotion gate as one APPLICATION over every supply that has to be
decided together (REQ-PIPE-266, REQ-PIPE-267).

A PACKAGE IS GATED TOGETHER, ONCE ALL OF IT IS CHECKED (REQ-PIPE-266). The
arrivals of one collection that share a receipt instant and are filed to one
period - a zip - are one package, read from the filing and delivery-file
records (qa.supply_receipt over qa.filing_current), never from run ids. An
arrival checked before the rest of its package is CHECKED, WAITING FOR ITS
PACKAGE: not a failure, and its package's gate is owed as a 'gate' item until
the last file is checked. Then the package is gated as one application.

AN APPLICATION DECIDES ON WHAT THE WAREHOUSE WILL HOLD (REQ-PIPE-267). A
cross-table verdict counts toward a supply's gate only where every supply that
check read (qa.check_read) is the one the period will hold once this
application's promotions are made - the warehouse's, or a supply still
promoting with it - newest per check by run_seq. The application is the
supplies its entry just checked plus every JOINABLE supply waiting in the
period connected to them through recorded cross-table verdicts, transitively,
settled by a fixed point over the whole set at once:

  1. every supply that would not promote on checks reading no other member -
     its own, and verdicts against the warehouse - or that the rule refuses
     for its own reasons (red, amber under hold, contested, held, not loaded,
     superseded, the backstop, a resupply its setting may not replace) is
     NOT PROMOTING;
  2. a check of a supply the entry just checked that no longer has a
     qualifying verdict - it read a supply that is not promoting - is
     RE-EVALUATED against the period as it will stand, as a readers-only run
     inside the application; except a check declared on a table the period
     will hold nothing of, whose result could count toward nothing;
  3. a joined supply is never re-checked: one that loses a verdict that way
     is simply not promoting, its results and decisions unchanged;
  4. whatever is then failing is not promoting, and so on, until the set of
     supplies not promoting stops growing; the rest promote together, in ONE
     outer decision transaction, or not at all.

One advisory lock per (collection, period), try-lock, held for the whole
application: a second application or a person's decision in the period finds
it held, and the entry is left owed rather than waiting (criterion 17). Its
re-evaluations' results count toward nothing until it SETTLES; a rolled-back
one is ABANDONED and never counts (criterion 12) - qa.run_visible filters on
it. This module is that lifecycle's one home.

Everything here is decided at run time from recorded results and the decision
log, where a connection is legitimately open; the dashboard build reads only
what was recorded.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime

from qa_tools.common import qa_store, supply_db

TABLE = f'"{qa_store.SCHEMA}".gate_application'

#: The gate entries (REQ-PIPE-267 criterion 2), as recorded.
PACKAGE, RECHECK, KNOCK_ON, UNGATED = "package", "recheck", "knock-on", "ungated"
SETTLED, ABANDONED = "settled", "abandoned"

#: The advisory-lock space of the per-(collection, period) lock - beside the
#: processing pass's (51510, 51511), an owed item's claim (51512) and a run
#: attempt's (51513, qa_store.ATTEMPT_LOCK_SPACE).
PERIOD_LOCK_SPACE = 51514

#: A person's decision refused while a gate holds its period (REQ-PIPE-266
#: criterion 16).
GATE_RUNNING = "A gate is running for {period}. Nothing was changed. Try again in a moment."


# ---------------------------------------------------------------------------
# The period lock (REQ-PIPE-267 criterion 17)
# ---------------------------------------------------------------------------

def _lock_key(collection_id: str, period: str) -> str:
    return f"gate/{collection_id}/{period}"


@contextmanager
def period_lock(collection_id: str, period: str):
    """THE ONE PER-(COLLECTION, PERIOD) LOCK, and its rule, in one place.

    TRY-LOCK, NEVER A WAIT. A gate application holds it for the whole of its
    work on a connection of its own; another application finding it held
    leaves its entry OWED (its 'gate', 'reevaluate' or 'recheck' item) for the
    next pass, and a person's decision finding it held is refused with exit 75
    (try_for_decision). Waiting would self-deadlock a nested call on a second
    connection. RELEASED once the application's outer transaction commits and
    BEFORE the knock-on (knock_on.complete), which takes it afresh.

    Yields True while held by this caller, False where another holds it."""
    conn = supply_db.connect(reuse=False, label="mothman:gate-period-lock")
    try:
        got = bool(conn.execute("SELECT pg_try_advisory_lock(?, hashtext(?))",
                                [PERIOD_LOCK_SPACE, _lock_key(collection_id, period)]
                                ).fetchone()[0])
        try:
            yield got
        finally:
            if got:
                conn.execute("SELECT pg_advisory_unlock(?, hashtext(?))",
                             [PERIOD_LOCK_SPACE, _lock_key(collection_id, period)])
    finally:
        conn.close()


def try_for_decision(conn, collection_id: str, period: str) -> bool:
    """A PERSON'S table-moving decision takes the same lock for its own
    transaction (REQ-PIPE-266 criterion 16): False where a gate application
    holds it - the caller refuses, records nothing, exits 75. Released when
    the decision's transaction ends."""
    return bool(conn.execute("SELECT pg_try_advisory_xact_lock(?, hashtext(?))",
                             [PERIOD_LOCK_SPACE, _lock_key(collection_id, period)]
                             ).fetchone()[0])


class GateRunning(Exception):
    """A person's decision refused because a gate holds its period."""

    def __init__(self, period: str):
        super().__init__(GATE_RUNNING.format(period=period))
        self.period = period


# ---------------------------------------------------------------------------
# The application's lifecycle (REQ-PIPE-267 criterion 12)
# ---------------------------------------------------------------------------

def start(conn, *, collection_id: str, period: str, entry: str, delivery: str | None = None,
          package_instant=None, retries: int | None = None) -> int:
    """Record that an application has begun; its results count for nothing
    until settle()."""
    from qa_tools.common import replay_clock

    qa_store.ensure_schema(conn)
    return int(conn.execute(
        f"INSERT INTO {TABLE} (collection_id, period, entry, started_at, delivery, "
        "package_instant, retries) VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING id",
        [collection_id, period, entry, replay_clock.now(), delivery, package_instant,
         retries]).fetchone()[0])


def _end(conn, application: int, how: str) -> None:
    from qa_tools.common import replay_clock

    conn.execute(f"UPDATE {TABLE} SET ended = ?, ended_at = ? WHERE id = ? AND ended IS NULL",
                 [how, replay_clock.now(), application])


def settle(conn, application: int) -> None:
    """Its last promotion or hold-back is written: its results now count."""
    _end(conn, application, SETTLED)


def abandon(conn, application: int) -> None:
    """Its outer transaction was rolled back: its results never count, and
    nothing reuses them (criterion 8)."""
    _end(conn, application, ABANDONED)


def ended(conn, application: int) -> str | None:
    rows = conn.execute(f"SELECT ended FROM {TABLE} WHERE id = ?", [application]).fetchall()
    return rows[0][0] if rows else None


def counted(conn, application: int | None) -> bool:
    """Whether a run inside `application` counts toward anything - the rule
    qa.run_visible applies, for a reader holding a run's application id."""
    return application is None or ended(conn, application) == SETTLED


# ---------------------------------------------------------------------------
# Packages (REQ-PIPE-266 criteria 1, 3 and 7)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Package:
    collection_id: str
    period: str
    delivery: str
    received: datetime
    #: [(dataset id, supply id)] of every file of it, in dataset order.
    supplies: tuple[tuple[str, str], ...]
    #: The subset whose run is recorded.
    checked: frozenset[tuple[str, str]]

    @property
    def complete(self) -> bool:
        return len(self.checked) == len(self.supplies)

    @property
    def counts(self) -> tuple[int, int]:
        return len(self.checked), len(self.supplies)

    @property
    def instant_text(self) -> str:
        return self.received.isoformat()


def package_of(conn, dataset_id: str, supply: str) -> Package | None:
    """The package this supply belongs to, from the record: every supply of
    its collection filed from its delivery at its receipt instant to the same
    period (criterion 1). None for a supply filed to no period."""
    from qa_tools.common import filing, hierarchy

    s = qa_store.SCHEMA
    rows = conn.execute(
        f'SELECT rc.delivery, rc.received_instant, f.slot FROM "{s}".supply_receipt rc '
        f"JOIN {filing.CURRENT} f ON f.dataset_id = rc.dataset_id "
        "AND f.supply_id = rc.supply_id WHERE rc.dataset_id = ? AND rc.supply_id = ?",
        [dataset_id, supply]).fetchall()
    if not rows or not rows[0][2]:
        return None
    delivery, received, period = rows[0]
    collection_id = hierarchy.dataset(dataset_id).collection_id
    return package_at(conn, collection_id, period, delivery, received)


def package_at(conn, collection_id: str, period: str, delivery: str, received) -> Package:
    """The package at (period, delivery, receipt instant)."""
    from qa_tools.common import filing, hierarchy

    s = qa_store.SCHEMA
    members = []
    for ds, sup in conn.execute(
            f'SELECT rc.dataset_id, rc.supply_id FROM "{s}".supply_receipt rc '
            f"JOIN {filing.CURRENT} f ON f.dataset_id = rc.dataset_id "
            "AND f.supply_id = rc.supply_id "
            "WHERE rc.delivery = ? AND rc.received_instant = ? AND f.slot = ? "
            "ORDER BY rc.dataset_id, rc.supply_id", [delivery, received, period]).fetchall():
        try:
            if hierarchy.dataset(ds).collection_id != collection_id:
                continue
        except hierarchy.UnknownDatasetError:
            continue
        members.append((ds, sup))
    checked = frozenset((ds, sup) for ds, sup in members if _checked(conn, ds, sup))
    return Package(collection_id, period, delivery, received, tuple(members), checked)


def _checked(conn, dataset_id: str, supply: str) -> bool:
    """CHECKED once its run is recorded (REQ-PIPE-266 criterion 7) - a run of
    a supply that could not be loaded, is held or contested completes with
    what it could record, so that counts too."""
    return bool(conn.execute(
        f'SELECT 1 FROM "{qa_store.SCHEMA}".run WHERE dataset_id = ? AND supply_id = ? '
        "AND completed_at IS NOT NULL AND scope <> 'readers' LIMIT 1",
        [dataset_id, supply]).fetchall())


def owed_gate(conn, package: Package):
    """The uncleared 'gate' item owed for this package, or None."""
    from qa_tools.common import recheck

    for o in recheck.owed(conn):
        if (o.kind == recheck.GATE and o.period == package.period
                and o.delivery == package.delivery and o.package_instant is not None
                and _same_instant(o.package_instant, package.received)):
            return o
    return None


def _same_instant(a, b) -> bool:
    from qa_tools.common import supply_status

    return supply_status.instant(a) == supply_status.instant(b)


def owe_gate(conn, package: Package, *, dataset_id: str, retries: int | None = None) -> int:
    """Owe this package's gate (criterion 3), once: caused by the load of
    its last arrival, or by the application it retries."""
    from qa_tools.common import recheck, replay_clock

    found = owed_gate(conn, package)
    if found is not None:
        if retries is not None and found.caused_by_application != retries:
            # A RETRIED APPLICATION IS THE CAUSE NOW (criterion 3).
            conn.execute(f"UPDATE {recheck.TABLE} SET caused_by_application = ?, "
                         "caused_by_load = NULL, caused_by_decision = NULL WHERE id = ?",
                         [retries, found.id])
        return found.id
    load = None
    if retries is None:
        rows = conn.execute(
            f'SELECT max(id) FROM "{qa_store.SCHEMA}".load_outcome WHERE delivery = ? '
            "AND dataset_id = ?", [package.delivery, dataset_id]).fetchall()
        load = rows[0][0] if rows and rows[0][0] is not None else None
    return int(conn.execute(
        f"INSERT INTO {recheck.TABLE} (kind, dataset_id, period, caused_by_load, "
        "caused_by_application, delivery, package_instant, owed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?) RETURNING id",
        [recheck.GATE, dataset_id, package.period, load, retries, package.delivery,
         package.received, replay_clock.now()]).fetchone()[0])


def waiting_words(package: Package) -> str:
    """REQ-PIPE-266 criterion 5's wording."""
    n, m = package.counts
    return f"checked, waiting for the rest of its delivery ({n} of {m} files checked)"


def still_being_gated(conn, dataset_id: str, supply: str) -> str | None:
    """REQ-PIPE-266 criterion 15: the refusal for a person's decision on a
    supply whose package is still being checked or gated - its 'gate' item
    owed and not cleared - or None."""
    from qa_tools.common import display_time

    package = package_of(conn, dataset_id, supply)
    if package is None or len(package.supplies) < 2:
        return None
    if owed_gate(conn, package) is None:
        return None
    n, m = package.counts
    when = display_time.format_instant(package.received)
    if package.complete:
        text = (f"The delivery received {when} is being gated ({m} of {m} files checked); "
                f"decide once it is gated.")
    else:
        text = (f"The delivery received {when} is still being checked ({n} of {m} files "
                f"checked); decide once it is gated.")
    if not _held_by_a_run(conn, package):
        text += "\nIt is finished by the next processing pass:\n  mothman pipeline process"
    return text


def _held_by_a_run(conn, package: Package) -> bool:
    """Whether a live process holds this package now - its period lock, or
    an arrival lock on one of its files."""
    from qa_tools.common import processing_pass

    key = _lock_key(package.collection_id, package.period)
    rows = conn.execute(
        "SELECT 1 FROM pg_locks WHERE locktype = 'advisory' AND granted AND classid = ? "
        "AND objsubid = 2 AND objid = hashtext(?)::oid "
        "AND database = (SELECT oid FROM pg_database WHERE datname = current_database()) "
        "LIMIT 1",
        [PERIOD_LOCK_SPACE, key]).fetchall()
    if rows:
        return True
    for ds, sup in package.supplies:
        from qa_tools.common import supply_files

        run_id = supply_files.run_id_of(ds, sup)
        if conn.execute(
                "SELECT 1 FROM pg_locks WHERE locktype = 'advisory' AND granted "
                "AND classid = ? AND objsubid = 2 AND objid = hashtext(?)::oid "
                "AND database = (SELECT oid FROM pg_database WHERE datname = current_database()) "
                "LIMIT 1",
                [processing_pass.ARRIVAL_LOCK_SPACE, run_id]).fetchall():
            return True
    return False


# ---------------------------------------------------------------------------
# One gate application (REQ-PIPE-267 criteria 1-17)
# ---------------------------------------------------------------------------

@dataclass
class Member:
    """One supply of an application."""
    item: dict
    #: Checked by the gate entry (criterion 2), or joined, waiting already.
    checked_now: bool
    delivery: str | None = None
    received: datetime | None = None
    #: Why it is not promoting, where it is not: ('own', why) or
    #: ('held-back', Cause).
    out: tuple | None = None
    shown: list = field(default_factory=list)

    @property
    def dataset_id(self) -> str:
        return self.item["dataset_id"]

    @property
    def supply(self) -> str:
        return self.item["supply"]

    @property
    def key(self) -> tuple[str, str]:
        return self.dataset_id, self.supply

    @property
    def table(self) -> str:
        from qa_tools.common import hierarchy

        return hierarchy.dataset(self.dataset_id).table


@dataclass(frozen=True)
class Cause:
    """Why a supply was held back by a re-evaluation (criterion 13)."""
    checks: tuple[str, ...]
    #: {check: the supply in the warehouse it was checked against, or None}
    against: dict
    by: str                    # the supply not promoting
    by_dataset: str
    by_received: str | None
    #: 'package-mate' (came with this supply) or 'joined' (waiting already)
    came: str
    #: NOT JUDGED (Keith, 2026-10-25, post-build-review #274 D2): the checks
    #: whose re-evaluation recorded no result that counts, so the supply is
    #: held back until they do - never promoted without them. Empty for a
    #: hold-back on a result that did count.
    not_counted: tuple[str, ...] = ()
    #: Whether a responsible check's re-check RAN against the warehouse and
    #: failed - its own failure, so it is its own root (Keith, 2026-10-25,
    #: answer 3a) - rather than could not be checked.
    failed: bool = False


@dataclass
class Applied:
    """What one application did, in promotion.AfterRun's terms plus its own."""
    application: int | None = None
    promoted: tuple[str, ...] = ()
    refused: dict = field(default_factory=dict)
    failed: dict = field(default_factory=dict)
    frozen: dict = field(default_factory=dict)
    #: The lock was held elsewhere, or the re-confirmation found the period
    #: changed: nothing was decided, and the entry stays owed.
    contended: bool = False
    #: Waiting for the rest of its package (REQ-PIPE-266 criterion 3).
    waiting: str | None = None
    #: Supplies held back by another (criterion 13), {dataset: Cause}.
    held_back: dict = field(default_factory=dict)
    #: How many readers-only runs it made (criterion 10).
    reevaluations: int = 0
    #: Supplies held back NOT JUDGED (Keith, 2026-10-25, D2), {dataset: the
    #: tables the 'reevaluate' item retrying them is owed for}.
    not_judged: dict = field(default_factory=dict)

    def as_after_run(self):
        from qa_tools.common import promotion

        return promotion.AfterRun(promoted=self.promoted, refused=dict(self.refused),
                                  failed=dict(self.failed), frozen=dict(self.frozen))


class _Contention(Exception):
    """The re-confirmation under the slot locks found the period changed."""


def apply(collection_id: str, period: str, *, entry: str, checked: list[dict],
          effective_at: str, run_by: str | None = None, delivery: str | None = None,
          package_instant=None, retries: int | None = None) -> Applied:
    """Form and settle ONE gate application in `period` from the supplies
    `checked` (filing.supplies_of's shape), under the period lock. Where the
    lock is held elsewhere nothing is decided and `contended` is set - the
    caller leaves its entry owed."""
    if entry != PACKAGE:
        # A SUPPLY WHOSE PACKAGE IS STILL BEING CHECKED is gated by its
        # package, never alone by another entry (REQ-PIPE-266 criteria 2 and
        # 7; REQ-PIPE-267 criterion 3): a knock-on or a re-check that reaches
        # it leaves it to the package's own gate.
        with supply_db.connect(read_only=True, label="mothman:gate") as conn:
            checked = [i for i in checked if not _package_waiting(conn, i)]
        if not checked:
            return Applied()
    with period_lock(collection_id, period) as mine:
        if not mine:
            return Applied(contended=True)
        return _apply_locked(collection_id, period, entry=entry, checked=checked,
                             effective_at=effective_at, run_by=run_by, delivery=delivery,
                             package_instant=package_instant, retries=retries)


def _apply_locked(collection_id, period, *, entry, checked, effective_at, run_by,
                  delivery, package_instant, retries) -> Applied:
    from qa_tools.common import agreement_drift, promotion

    reads = promotion._declared_reads()
    with supply_db.connect(label="mothman:gate") as conn:
        application = start(conn, collection_id=collection_id, period=period, entry=entry,
                            delivery=delivery, package_instant=package_instant,
                            retries=retries)
        members: dict[tuple[str, str], Member] = {}
        for item in checked:
            m = Member(item=dict(item), checked_now=True)
            members[m.key] = m
        _join(conn, members, period)
        for m in members.values():
            m.delivery, m.received = _receipt(conn, m.dataset_id, m.supply)
        try:
            barred = agreement_drift.refusals(conn, sorted({m.dataset_id
                                                            for m in members.values()}))
        except Exception:  # noqa: BLE001 - an unevaluable backstop refuses nothing
            barred = {}
        warehouse = _warehouse(conn, period, members)
    out = Applied(application=application)
    try:
        _settle_fixed_point(collection_id, period, application, members, reads, barred,
                            warehouse, effective_at, run_by, out)
        _decide(collection_id, period, application, members, reads, barred, warehouse,
                effective_at, package_instant, out)
    except _Contention as exc:
        with supply_db.connect(label="mothman:gate") as conn:
            abandon(conn, application)
        out.contended = True
        out.promoted = ()
        out.failed = {}
        print(f"gate: {period} changed while it was being gated ({exc}) - nothing was "
              f"promoted; it is gated again by the next pass.")
        _owe_retry(collection_id, period, application, members, package_instant)
        return out
    except Exception as exc:  # noqa: BLE001 - criterion 17: the whole application is owed
        with supply_db.connect(label="mothman:gate") as conn:
            abandon(conn, application)
        out.failed = {m.dataset_id: f"{type(exc).__name__}: {exc}"
                      for m in members.values() if m.checked_now}
        out.promoted = ()
        _owe_retry(collection_id, period, application, members, package_instant)
        from qa_tools.common import asked_for

        if isinstance(exc, asked_for.MissingCheck):
            raise
        return out
    with supply_db.connect(label="mothman:gate") as conn:
        settle(conn, application)
    return out


def _package_waiting(conn, item: dict) -> bool:
    """Whether this supply's package gate is owed - its package not yet
    gated."""
    package = package_of(conn, item["dataset_id"], item["supply"])
    return package is not None and owed_gate(conn, package) is not None


def _owe_retry(collection_id, period, application, members, package_instant) -> None:
    """A failed or contended application is owed again as a 'gate' item -
    never a 'recheck', which would re-run that supply's full QA (criterion
    17) - over the package of EVERY supply its entry checked, once each. A
    knock-on or re-check entry gates readers from several deliveries, and
    owing only the first one's package left the rest decided by nothing
    (post-build-review #274 D6)."""
    seen = set()
    with supply_db.connect(label="mothman:gate") as conn:
        for m in sorted(members.values(), key=lambda m: m.key):
            if not m.checked_now:
                continue
            package = package_of(conn, m.dataset_id, m.supply)
            if package is None:
                continue
            ident = (package.period, package.delivery, _iso(package.received))
            if ident in seen:
                continue
            seen.add(ident)
            owe_gate(conn, package, dataset_id=m.dataset_id, retries=application)


def _receipt(conn, dataset_id: str, supply: str):
    rows = conn.execute(
        f'SELECT delivery, received_instant FROM "{qa_store.SCHEMA}".supply_receipt '
        "WHERE dataset_id = ? AND supply_id = ?", [dataset_id, supply]).fetchall()
    return (rows[0][0], rows[0][1]) if rows else (None, None)


def _warehouse(conn, period: str, members) -> dict[str, str | None]:
    """{logical table: the supply the warehouse holds for it in `period`}
    for every table of the members' collections, as the application saw it
    - what the re-confirmation compares against."""
    from qa_tools import collections
    from qa_tools.common import decision_log, hierarchy

    tables: dict[str, str | None] = {}
    seen = set()
    for m in members.values():
        coll = hierarchy.dataset(m.dataset_id).collection_id
        if coll in seen:
            continue
        seen.add(coll)
        for d in collections.by_id(coll).datasets:
            h = decision_log.held(conn, d.dataset_id, period)
            tables[d.table] = (h.holder if h and h.held_as in (
                decision_log.PROMOTED, decision_log.SUBSTITUTED, decision_log.INHERITED)
                else None)
    return tables


# ---- joining (criteria 2 and 3) ------------------------------------------------

def _join(conn, members: dict, period: str) -> None:
    """Every JOINABLE supply waiting in `period` connected to a member
    through recorded cross-table verdicts, transitively (criterion 2)."""
    from qa_tools.common import supply_status

    frontier = list(members.values())
    seen = set(members)
    while frontier:
        m = frontier.pop()
        for r in supply_status._shown(conn, m.dataset_id, m.supply):
            for table, read in (r.get("reads") or {}).items():
                if read.get("state") != qa_store.READ or not read.get("supply_id"):
                    continue
                ds = supply_status.dataset_of(table)
                key = (ds, read["supply_id"])
                if ds is None or key in seen:
                    continue
                seen.add(key)
                item = joinable(conn, ds, read["supply_id"], period)
                if item is None:
                    continue
                joined = Member(item=item, checked_now=False)
                members[key] = joined
                frontier.append(joined)


def joinable(conn, dataset_id: str, supply: str, period: str) -> dict | None:
    """The supply as a member item where it is JOINABLE (criterion 3) - else
    None: waiting in `period`, with no uncleared owed 'recheck' or 'gate'
    item, in no package not yet gated, and its current run recorded for its
    current filing's slot. A held supply has no slot and never joins."""
    from qa_tools.common import recheck, supersession, supply_files

    if supply not in supersession.waiting_in(conn, dataset_id, period):
        return None
    for o in recheck.owed(conn, dataset_id):
        if o.kind == recheck.RECHECK and o.supply_id == supply:
            return None
    package = package_of(conn, dataset_id, supply)
    if package is not None and owed_gate(conn, package) is not None:
        return None
    current = qa_store.current_run(conn, dataset_id, supply)
    if current is None:
        return None
    rows = conn.execute(f'SELECT period FROM "{qa_store.SCHEMA}".run WHERE run_key = ?',
                        [current]).fetchall()
    if not rows or rows[0][0] != period:
        return None
    return {"dataset_id": dataset_id, "supply": supply, "period": period,
            "physical_tables": supply_files.tables_in(conn, dataset_id, supply,
                                                      supply_db.STAGING_SCHEMA),
            "contested": supply_files.open_contest(conn, dataset_id, supply) is not None}


# ---- reading verdicts (criterion 1) ------------------------------------------------

def _promoting(members) -> dict[str, Member]:
    """{table: the member still promoting for it}."""
    out = {}
    for m in sorted(members.values(), key=lambda m: m.key):
        if m.out is None:
            out.setdefault(m.table, m)
    return out


def _will_stand(table: str, members, warehouse) -> str | None:
    """The supply the period will hold for `table` once this application's
    promotions are made: a member still promoting, else the warehouse's."""
    promoting = _promoting(members)
    if table in promoting:
        return promoting[table].supply
    return warehouse.get(table)


def will_stand(members, warehouse, period: str):
    """THE WAREHOUSE AS IT WILL STAND once this application's promotions are
    made (criterion 1): every table's supply in the warehouse, the members
    still promoting in place of theirs - as supply_status.Holdings, the view
    REQ-PIPE-279's one selection rule (supply_status.count) is given."""
    from qa_tools.common import supply_status

    held = {}
    for table, supply in warehouse.items():
        ds = supply_status.dataset_of(table)
        if ds and supply:
            held[(ds, period)] = supply
    for table, m in _promoting(members).items():
        held[(m.dataset_id, period)] = m.supply
    return supply_status.Holdings(held)


def _verdicts(m: Member, members, warehouse) -> dict[str, dict]:
    """{check: its newest QUALIFYING result} for one member: the results
    REQ-PIPE-269's one counting rule (supply_status.count) counts toward it
    in the warehouse as it will stand, newest per check by run_seq - never a
    second rule (REQ-PIPE-269 criterion 7). A check with no counted result
    is left out rather than read red: criterion 6 re-evaluates it."""
    from qa_tools.common import supply_status

    period = m.item.get("period")
    counted = supply_status.count(m.dataset_id, m.supply, m.shown,
                                  holdings=will_stand(members, warehouse, period),
                                  owed=None, period=period, stand_ins=False)
    return {r["check_id"]: r for r in supply_status.newest_per_check(counted)}


def _newest(m: Member) -> dict[str, dict]:
    """{check: the newest result counted toward it as a waiting supply}
    (REQ-PIPE-269 criteria 3 and 4)."""
    from qa_tools.common import supply_status

    out: dict[str, dict] = {}
    empty = supply_status.Holdings({})
    for r in m.shown:
        if supply_status.counts_toward(r, m.dataset_id, [], empty):
            out[r["check_id"]] = r
    return out


def _reads_another(record: dict, m: Member, members) -> bool:
    """Whether a result read a supply of another member."""
    others = {k[1] for k in members if k != m.key}
    return any(read.get("state") == qa_store.READ and read.get("supply_id") in others
               for read in (record.get("reads") or {}).values())


def _status(m: Member, verdicts, reads):
    from qa_tools.common import promotion

    try:
        return promotion.status_of(m.dataset_id, list(verdicts), reads=reads)
    except promotion.UnreadableVerdictError as exc:
        return exc


def _judge(conn, m: Member, status, reads, barred, effective_at, *, record: bool):
    from qa_tools.common import hierarchy, promotion

    ds = hierarchy.dataset(m.dataset_id)
    return promotion.judge(conn, m.item, status, results=m.shown, reads=reads,
                           effective_at=effective_at, barred=barred,
                           agency_id=ds.agency_id, collection_id=ds.collection_id,
                           record=record)


def _refresh(conn, members, application) -> None:
    from qa_tools.common import supply_status

    for m in members.values():
        m.shown = supply_status._shown(conn, m.dataset_id, m.supply, application=application)


# ---- the fixed point (criteria 5 to 9) ------------------------------------------------

def _settle_fixed_point(collection_id, period, application, members, reads, barred,
                        warehouse, effective_at, run_by, out: Applied) -> None:
    with supply_db.connect(label="mothman:gate") as conn:
        _refresh(conn, members, application)
        # CRITERION 5: whatever would not promote on checks reading no other
        # member, or that the rule refuses for its own reasons.
        for m in sorted(members.values(), key=lambda m: m.key):
            own = [r for r in _verdicts(m, members, warehouse).values()
                   if not _reads_another(r, m, members)]
            status = _status(m, own, reads)
            judged = _judge(conn, m, status if status is not None else "green", reads,
                            barred, effective_at, record=False)
            if judged.work is None:
                m.out = ("own", judged)
    # EACH CHECK IS RE-EVALUATED AT MOST ONCE PER STATE OF THE PERIOD (the
    # fixed point's bound): a re-run whose result still does not count - a
    # check its run could not evaluate at all - is decided without, never
    # run again against the same warehouse.
    attempted: set = set()
    while True:
        # CRITERIA 6 AND 9: re-evaluate, for each member the entry just
        # checked and still promoting, the checks that lost their verdict.
        while True:
            newly = False
            with supply_db.connect(label="mothman:gate") as conn:
                _refresh(conn, members, application)
                todo = _reevaluations_owed(members, warehouse)
                state = tuple(sorted(k for k, m in members.items() if m.out is None))
                for key in sorted(todo):
                    checks, causes = todo[key]
                    fresh = {c for c in checks if (key, c, state) not in attempted}
                    spent = set(checks) - fresh
                    if spent:
                        # NOT JUDGED (Keith, 2026-10-25, post-build-review
                        # #274 D2): a check re-evaluated in this very state
                        # whose result still does not count is never decided
                        # without. The supply is held back until it counts -
                        # owed a re-evaluation the next pass retries - which
                        # changes the state, so the fixed point goes on.
                        m = members[key]
                        m.out = ("held-back", _cause(
                            m, (spent, {c: causes[c] for c in spent}), members, warehouse,
                            None, not_counted=True))
                        del todo[key]
                        newly = True
                        continue
                    attempted.update((key, c, state) for c in fresh)
                    todo[key] = (fresh, {c: causes[c] for c in fresh})
                _joined_lose_verdicts(members, warehouse)
                if todo or newly:
                    _record_final_holdbacks(conn, application, members, effective_at)
            if not todo:
                if newly:
                    continue
                break
            # A FIXED ORDER, sorted by dataset id (criterion 7, REQ-PIPE-262
            # criterion 13), so run_seq is the same in every bootstrap.
            for key in sorted(todo, key=lambda k: k):
                checks, causes = todo[key]
                _reevaluate(members[key], checks, causes, members, warehouse, application,
                            period, run_by)
                out.reevaluations += 1
            with supply_db.connect(label="mothman:gate") as conn:
                _refresh(conn, members, application)
                for key in sorted(todo):
                    y = members[key]
                    if y.out is not None:
                        continue
                    verdicts = list(_verdicts(y, members, warehouse).values())
                    judged = _judge(conn, y, _status(y, verdicts, reads), reads, barred,
                                    effective_at, record=False)
                    if judged.work is None:
                        y.out = ("held-back", _cause(y, todo[key], members, warehouse,
                                                     judged))
        # CRITERION 7: whatever still fails against another still-promoting
        # supply is not promoting, together; then again from criterion 6.
        grew = False
        with supply_db.connect(label="mothman:gate") as conn:
            _refresh(conn, members, application)
            failing = []
            for m in sorted(members.values(), key=lambda m: m.key):
                if m.out is not None:
                    continue
                verdicts = list(_verdicts(m, members, warehouse).values())
                judged = _judge(conn, m, _status(m, verdicts, reads), reads, barred,
                                effective_at, record=False)
                if judged.work is None:
                    failing.append((m, judged))
            for m, judged in failing:
                m.out = ("own", judged)
                grew = True
        if not grew:
            return


def _reevaluations_owed(members, warehouse) -> dict:
    """{member key: (checks to re-evaluate, {check: the not-promoting supply
    it read})} for every member the entry just checked and still promoting
    whose check lost its qualifying verdict (criterion 6) - except a check
    declared on a table the period will hold nothing of."""
    from qa_tools.common import supply_status

    todo: dict = {}
    for m in members.values():
        if m.out is not None or not m.checked_now:
            continue
        have = _verdicts(m, members, warehouse)
        for check, newest in _newest(m).items():
            if check in have or not newest.get("reads"):
                continue
            declared = supply_status.declared_on(newest)
            if declared != m.dataset_id:
                from qa_tools.common import hierarchy

                try:
                    home = hierarchy.dataset(declared).table
                except hierarchy.UnknownDatasetError:
                    continue
                if _will_stand(home, members, warehouse) is None:
                    continue  # its result could count toward nothing
            cause = _cause_supply(newest, m, members, warehouse)
            entry = todo.setdefault(m.key, (set(), {}))
            entry[0].add(check)
            entry[1][check] = cause
    return todo


def _cause_supply(record: dict, m: Member, members, warehouse) -> str | None:
    """The supply a result read that the period will not hold - the
    not-promoting member, or another not in the warehouse."""
    for table, read in sorted((record.get("reads") or {}).items()):
        if read.get("state") != qa_store.READ or read.get("supply_id") == m.supply:
            continue
        if read.get("supply_id") != _will_stand(table, members, warehouse):
            return read.get("supply_id")
    return None


def _joined_lose_verdicts(members, warehouse) -> None:
    """Criterion 4: a joined supply is never re-checked - one whose counted
    verdict read a supply neither in the warehouse nor still promoting is
    not promoting, with no new entry."""
    for m in members.values():
        if m.out is not None or m.checked_now:
            continue
        have = _verdicts(m, members, warehouse)
        lost = [c for c, r in _newest(m).items() if c not in have and r.get("reads")]
        if lost:
            m.out = ("joined", None)


def _from_the_warehouse(y: Member, members, warehouse) -> list[str]:
    """The tables a re-evaluation of `y` reads from the warehouse: every
    table with no supply still promoting with it - the period as it will
    stand."""
    from qa_tools import collections
    from qa_tools.common import hierarchy

    promoting = _promoting(members)
    coll = collections.by_id(hierarchy.dataset(y.dataset_id).collection_id)
    return sorted(d.table for d in coll.datasets
                  if d.table != y.table and d.table not in promoting)


def _held_back_tables(y: Member, members, warehouse) -> list[str]:
    """Of those, the tables whose supply in the application is NOT promoting
    - where the warehouse holds none, the reason a check could not read them
    is 'held back with its package' (REQ-PIPE-270 criterion 4)."""
    promoting = _promoting(members)
    return sorted({m.table for m in members.values()
                   if m.out is not None and m.table != y.table and m.table not in promoting})


def _reevaluate(y: Member, checks: set, causes: dict, members, warehouse, application: int,
                period: str, run_by) -> None:
    """ONE readers-only run of `y` per round (criterion 10), inside the
    application, caused by the hold-back it re-checks for - the lowest
    decision id where several - reading the period as it will stand, and
    never re-running `y`'s own table and column checks."""
    from qa_tools.common import hierarchy, recheck

    reads = _check_reads(checks)
    moved = sorted({t for c in checks for t in reads.get(c, ())} - {y.table}
                   | {_home(c) for c in checks if _home(c) and _home(c) != y.table})
    cause_ids = []
    with supply_db.connect(label="mothman:gate") as conn:
        for supply in {s for s in causes.values() if s}:
            found = _latest_gate_entry(conn, supply)
            if found is not None:
                cause_ids.append(found)
        load = None
        if not cause_ids:
            # A SUPPLY HELD BACK WITH NO ENTRY OF ITS OWN - left ungated by the
            # agreement backstop (REQ-PIPE-266 criterion 14), which writes
            # none - is no decision to name: the re-check is caused by the
            # load that brought `y`, the gate entry's own cause.
            rows = conn.execute(
                f'SELECT max(id) FROM "{qa_store.SCHEMA}".load_outcome WHERE delivery = ? '
                "AND dataset_id = ?", [y.delivery, y.dataset_id]).fetchall()
            load = rows[0][0] if rows and rows[0][0] is not None else None
        run_key = recheck.mint_run_id(conn, y.dataset_id, y.supply)
    if not cause_ids and load is None:
        raise RuntimeError(f"no decision or load to name as the cause of {y.supply}'s re-check")
    del hierarchy
    recheck.execute(
        dataset_id=y.dataset_id, supply_id=y.supply, run_key=run_key,
        purpose={"scope": "readers", "reads_table": ",".join(moved or [y.table]),
                 "caused_by_decision": min(cause_ids) if cause_ids else None,
                 "caused_by_load": None if cause_ids else load,
                 "gate_application": application,
                 "readers_checks": sorted(checks),
                 "held_back_tables": _held_back_tables(y, members, warehouse)},
        run_by=run_by, warehouse_for=_from_the_warehouse(y, members, warehouse))


def _home(check: str) -> str | None:
    from qa_tools.common import check_id as cid, hierarchy

    parsed = cid.try_parse(check)
    try:
        return hierarchy.dataset(parsed.dataset).table if parsed else None
    except hierarchy.UnknownDatasetError:
        return None


def _check_reads(checks) -> dict[str, list[str]]:
    from qa_tools.common import promotion

    declared = promotion._declared_reads()
    return {c: list(declared.get(c) or ()) for c in checks}


def _latest_gate_entry(conn, supply: str) -> int | None:
    from qa_tools.common import decision_log

    rows = conn.execute(
        f"SELECT max(id) FROM {decision_log.TABLE} WHERE supply = ? AND action IN (?, ?)",
        [supply, decision_log.PROMOTION_WITHHELD, decision_log.PROMOTION_REFUSED]).fetchall()
    return rows[0][0] if rows and rows[0][0] is not None else None


def _cause(y: Member, todo_entry, members, warehouse, judged, *,
           not_counted: bool = False) -> Cause:
    """The structured fields of a hold-back by re-evaluation (criterion 13);
    `not_counted` where the re-evaluation of `todo_entry`'s checks recorded
    nothing that counts (D2's not judged)."""
    from qa_tools.common import supply_status

    checks, causes = todo_entry
    verdicts = _verdicts(y, members, warehouse)
    failing = sorted(c for c in checks if c in verdicts
                     and verdicts[c].get("status") not in ("pass", "warn"))
    responsible = tuple(failing or sorted(checks))
    from qa_tools.common import carried

    ran_and_failed = any(not carried.not_evaluated_reason(verdicts[c]) for c in failing)
    against = {}
    for c in responsible:
        r = verdicts.get(c) or {}
        found = None
        for table, read in (r.get("reads") or {}).items():
            if table == y.table:
                continue
            if read.get("state") == qa_store.READ:
                found = read.get("supply_id")
        against[c] = found
    by = next((causes[c] for c in responsible if causes.get(c)), None) or ""
    by_dataset = by.split("@", 1)[0] if by else ""
    other = members.get((by_dataset, by))
    came = "package-mate"
    if other is not None and not other.checked_now:
        came = "joined"
    elif other is None or (other.received and y.received and other.received != y.received):
        came = "joined"
    received = None
    if other is not None and other.received is not None:
        received = supply_status.instant(other.received).isoformat()
    return Cause(checks=responsible, against=against, by=by, by_dataset=by_dataset,
                 by_received=received, came=came,
                 not_counted=tuple(sorted(checks)) if not_counted else (),
                 failed=ran_and_failed and not not_counted)


# ---- recording and promoting (criteria 13 and 17; REQ-PIPE-266 9 and 10) ----------------

def _record_final_holdbacks(conn, application: int, members, effective_at: str) -> None:
    """Write each hold-back the moment it is final (REQ-PIPE-266 criterion
    9) - before a re-check cites it - for supplies the entry checked; a
    joined supply's outcome is unchanged and gets no entry."""
    for m in sorted(members.values(), key=lambda m: m.key):
        if m.out is None or not m.checked_now or m.item.get("_recorded"):
            continue
        _record_holdback(conn, application, m, members, effective_at)
        m.item["_recorded"] = True


def _record_holdback(conn, application: int, m: Member, members, effective_at: str) -> None:
    from qa_tools.common import decision_log, hierarchy, promotion

    kind, detail = m.out
    ds = hierarchy.dataset(m.dataset_id)
    gate_fields = {"gate_application": application,
                   "package_instant": (_iso(m.received) if m.received else None)}
    if kind == "own":
        why = detail.why if detail is not None else "refused"
        if detail is not None and detail.frozen:
            return  # left ungated, as the backstop leaves it (no record)
        if detail is not None and detail.withheld:
            # HELD BACK BY ANOTHER PERIOD, NOT ITS OWN CHECKS (Keith,
            # 2026-10-25, answer 2a; post-build-review #274 D3): a later
            # period stands on the supply it would replace (REQ-PIPE-123
            # criterion 8) - 'promotion-withheld', as after_run records it.
            promotion._record_withheld(conn, agency_id=ds.agency_id,
                                       collection_id=ds.collection_id,
                                       dataset_id=m.dataset_id, supply=m.supply,
                                       period=m.item.get("period"), reason=why,
                                       effective_at=effective_at, gate=gate_fields)
            return
        wanted = _red_only_for_want_of(m)
        if wanted:
            # RED ONLY BECAUSE ANOTHER TABLE IS ABSENT - could not run is red
            # (REQ-PIPE-270), but it is another table's doing, not a check of
            # its own failing, so it is 'promotion-withheld' (Keith,
            # 2026-10-25, answer 2a): 'promotion-refused' is only for a
            # supply's own checks failing.
            promotion._record_withheld(conn, agency_id=ds.agency_id,
                                       collection_id=ds.collection_id,
                                       dataset_id=m.dataset_id, supply=m.supply,
                                       period=m.item.get("period"),
                                       reason=_absent_words(wanted),
                                       effective_at=effective_at, gate=gate_fields)
            return
        if why == promotion.AMBER_WAITING_REASON:
            amber = _amber(m.dataset_id, effective_at)
            promotion._record_amber_waiting(
                conn, agency_id=ds.agency_id, collection_id=ds.collection_id,
                dataset_id=m.dataset_id, supply=m.supply, period=m.item.get("period"),
                amber=amber, effective_at=effective_at, gate=gate_fields)
            return
        promotion._record_refused(conn, agency_id=ds.agency_id, collection_id=ds.collection_id,
                                  dataset_id=m.dataset_id, supply=m.supply,
                                  period=m.item.get("period"), reason=why,
                                  effective_at=effective_at, gate=gate_fields)
        return
    if kind != "held-back":
        return
    cause: Cause = detail
    structured = {"checks": list(cause.checks), "against": cause.against,
                  "by": cause.by, "by_dataset": cause.by_dataset,
                  "by_received": cause.by_received, "came": cause.came}
    if cause.not_counted:
        structured["not_counted"] = list(cause.not_counted)
    structured["failed"] = cause.failed
    entry_id = _same_holdback(conn, m, cause)
    if entry_id is None:
        with decision_log.apply_decision(conn, decision_log.Decision(
                agency_id=ds.agency_id, collection_id=ds.collection_id,
                dataset_id=m.dataset_id, action=decision_log.PROMOTION_WITHHELD,
                supply=m.supply, actor=promotion.RULE_ACTOR, actor_kind=decision_log.RULE,
                effective_at=effective_at, to_slot=m.item.get("period"),
                reason=held_back_words(conn, m, cause), held_back_by=cause.by,
                held_back_detail=structured, **gate_fields)) as written:
            entry_id = written
    if cause.not_counted:
        _owe_not_judged(conn, m, cause, entry_id)


def _red_only_for_want_of(m: Member) -> list[str]:
    """The tables whose absence is the WHOLE of this supply's red - every
    failing check counted toward it could not run for want of one
    (REQ-PIPE-270), and none is an own failure or an owed stand-in - else
    []."""
    from qa_tools.common import carried, promotion

    reads = promotion._declared_reads()
    failing = [r for r in promotion._contributing_records(
                   m.dataset_id, list(_newest(m).values()), reads)
               if (r.get("status") or "") in ("fail", "error")]
    tables: set[str] = set()
    for r in failing:
        if not carried.not_evaluated_reason(r) or r.get("warehouse_reason"):
            return []
        named = r.get("unrunnable_tables") or ([r["unrunnable_table"]]
                                              if r.get("unrunnable_table") else [])
        named = named or r.get("held_tables") or []
        if not named:
            return []
        tables.update(named)
    return sorted(tables)


def _absent_words(tables: list[str]) -> str:
    """The withheld note for a supply red only for want of other tables."""
    from qa_tools.common import hierarchy

    def name(table: str) -> str:
        try:
            return hierarchy.dataset_for_table(table).dataset_name
        except hierarchy.UnknownDatasetError:
            return table
    names = ", ".join(name(t) for t in tables)
    return (f"Held back: its cross-table checks of the {names} could not be checked - no "
            f"{names} is in place for this period - and a check that could not run is red. "
            f"None of its checks of its own data failed; it is re-checked when the "
            f"{names} arrives.")


def retry_tables(m: Member, cause: Cause) -> list[str]:
    """The tables a NOT JUDGED supply's retry is owed for: every table its
    uncounted checks read - the one each is declared on included - but its
    own (D2)."""
    from qa_tools.common import hierarchy

    reads = _check_reads(cause.not_counted)
    tables = set()
    for c in cause.not_counted:
        tables.update(reads.get(c) or ())
        if _home(c):
            tables.add(_home(c))
    out = []
    for t in sorted(tables - {m.table}):
        try:
            hierarchy.dataset_for_table(t)
        except hierarchy.UnknownDatasetError:
            continue
        out.append(t)
    return out


def _owe_not_judged(conn, m: Member, cause: Cause, entry_id: int) -> None:
    """NOT JUDGED STAYS OWED (Keith, 2026-10-25, answer 1a): a 'reevaluate'
    item for the period and the tables its uncounted checks read, caused by
    the hold-back - REQ-PIPE-121's knock-on, which re-runs a stale reader's
    reading checks against the period as it stands and re-gates it. Once:
    an uncleared item already covering those tables (the knock-on now
    retrying it) is the retry, and that item stays owed while the supply is
    still not judged (knock_on.complete)."""
    from qa_tools.common import hierarchy, knock_on, recheck

    period = m.item.get("period")
    tables = retry_tables(m, cause)
    if not period or not tables:
        return
    for o in recheck.owed(conn):
        if (o.kind == recheck.REEVALUATE and o.period == period
                and set(tables) <= set(o.tables or ())):
            return
    knock_on.owe(conn, [(entry_id, hierarchy.dataset_for_table(t).dataset_id, period)
                        for t in tables])


def _same_holdback(conn, m: Member, cause: Cause) -> int | None:
    """A repeat is judged on the entry's structured fields, never its
    reason text (REQ-PIPE-266 criterion 9): the id of the latest gate
    outcome of this supply where it already says this, else None."""
    from qa_tools.common import decision_log

    rows = conn.execute(
        f"SELECT id, action, held_back_by, held_back_detail FROM {decision_log.TABLE} "
        "WHERE dataset_id = ? AND supply = ? AND action IN (?, ?, ?) ORDER BY id DESC LIMIT 1",
        [m.dataset_id, m.supply, decision_log.PROMOTE, decision_log.PROMOTION_WITHHELD,
         decision_log.PROMOTION_REFUSED]).fetchall()
    if not rows:
        return None
    entry_id, action, by, detail = rows[0]
    detail = detail or {}
    # WHAT IT WAS CHECKED AGAINST TOO (post-build-review #274): the same cause
    # against a different supply in the warehouse is a new hold-back, whose
    # entry - and wording - names the supply it was re-checked against. And
    # whether it was judged at all (D2).
    same = (action == decision_log.PROMOTION_WITHHELD and by == cause.by
            and sorted(detail.get("checks") or []) == sorted(cause.checks)
            and (detail.get("against") or {}) == (cause.against or {})
            and sorted(detail.get("not_counted") or []) == sorted(cause.not_counted))
    return int(entry_id) if same else None


def held_back_words(conn, m: Member, cause: Cause) -> str:
    """REQ-PIPE-267 criterion 13's wording, from the structured fields."""
    from qa_tools.common import display_time, hierarchy, promotion

    def name(dataset_id: str) -> str:
        try:
            return hierarchy.dataset(dataset_id).dataset_name
        except hierarchy.UnknownDatasetError:
            return dataset_id

    checks = ", ".join(dict.fromkeys(_check_words(c) for c in cause.checks)) \
        or "a cross-table check"
    by_name = name(cause.by_dataset) if cause.by_dataset else "file"
    when = (display_time.format_instant(cause.by_received) if cause.by_received else None)
    if cause.came == "package-mate":
        tail = f"the {by_name} received with it was held back."
    else:
        tail = f"the {by_name} waiting for a decision (received {when}) is held back."
    against = [s for s in cause.against.values() if s]
    if cause.not_counted:
        # NOT JUDGED (Keith, 2026-10-25, answer 1a): could not run is red
        # (REQ-PIPE-270), so it is never promoted without the check - and the
        # retry is owed, which the words say.
        return (f"Held back, not judged: {checks} was re-checked against the warehouse as "
                f"it will stand, but the re-check recorded no result that counts, because "
                f"{tail} It is not promoted without that check, and it is re-checked by "
                f"the next processing pass.")
    if against:
        held = against[0]
        held_ds = held.split("@", 1)[0]
        from qa_tools.common import filing

        got = filing.received_at_of(held_ds, held, conn=conn)
        on = display_time.format_instant(got) if got else held
        text = (f"Held back: {checks}, re-checked against the {name(held_ds)} in place in the "
                f"warehouse (received {on}) because {tail}")
    else:
        what = name(cause.by_dataset) if cause.by_dataset else "table"
        text = (f"Held back: {checks} could not be checked - no {what} is in place in the "
                f"warehouse, and {tail}")
    own = [r for r in _newest(m).values() if not r.get("reads")]
    if own and promotion.status_of(m.dataset_id, own, reads={}) in ("green", "amber"):
        text += " This supply's checks of its own data passed."
    return text


def _check_words(check: str) -> str:
    """'the Notifications -> Client Register check on cp_client_id': one
    check, whichever tools ran it (REQ-DASH-264 criterion 2's naming)."""
    from qa_tools.common import check_id as cid, hierarchy, promotion, supply_status

    parsed = cid.try_parse(check)
    if parsed is None:
        return check

    def name(dataset_id):
        try:
            return hierarchy.dataset(dataset_id).dataset_name
        except hierarchy.UnknownDatasetError:
            return dataset_id

    reads = [name(d) for d in (supply_status.dataset_of(t)
                               for t in promotion._declared_reads().get(check) or ()) if d]
    on = f" on {parsed.column}" if parsed.column else ""
    return f"the {name(parsed.dataset)} \u2192 {', '.join(reads) or 'cross-table'} check{on}"


def _amber(dataset_id: str, effective_at: str):
    from qa_tools.common import amber_setting

    try:
        return amber_setting.resolve(dataset_id, effective_at)
    except amber_setting.AmberSettingError:
        return None


def _iso(value) -> str:
    from qa_tools.common import supply_status

    return supply_status.instant(value).isoformat()


def _decide(collection_id, period, application, members, reads, barred, warehouse,
            effective_at, package_instant, out: Applied) -> None:
    """Write every remaining hold-back, then promote the rest together in
    ONE outer decision transaction, one savepoint per move, re-confirming
    under the slot locks first (criterion 17)."""
    from qa_tools.common import census, decision_log, promotion

    with supply_db.connect(label="mothman:gate") as conn:
        _refresh(conn, members, application)
        _record_final_holdbacks(conn, application, members, effective_at)
        work = []
        for m in sorted(members.values(), key=lambda m: m.key):
            if m.out is None:
                verdicts = list(_verdicts(m, members, warehouse).values())
                judged = _judge(conn, m, _status(m, verdicts, reads), reads, barred,
                                effective_at, record=False)
                if judged.work is None:  # cannot happen at the fixed point
                    m.out = ("own", judged)
                    _record_holdback(conn, application, m, members, effective_at)
                    continue
                work.append((m, judged.work, verdicts))
                continue
            if not m.checked_now:
                continue
            kind, detail = m.out
            if kind == "own" and detail is not None and detail.frozen:
                out.frozen[m.dataset_id] = detail.why
            elif kind == "own":
                out.refused[m.dataset_id] = detail.why if detail is not None else "refused"
            elif kind == "held-back":
                out.refused[m.dataset_id] = held_back_words(conn, m, detail)
                out.held_back[m.dataset_id] = detail
                if detail.not_counted:
                    out.not_judged[m.dataset_id] = retry_tables(m, detail)
        if not work:
            return
        promoted_supplies = [m.supply for m, _w, _v in work]
        moved_periods = set()
        with decision_log.decision_transaction(conn):
            for m, item, verdicts in work:
                decision_log.lock_slot(conn, m.dataset_id, item.get("period") or period)
            _reconfirm(conn, period, members, work, warehouse)
            for m, item, _v in work:
                with_ = tuple(s for s in promoted_supplies if s != m.supply)
                promotion.promote(
                    conn, agency_id=_agency(m), collection_id=collection_id,
                    dataset_id=m.dataset_id, supply=m.supply,
                    period=item.get("period") or period,
                    physical_tables=item["physical_tables"], actor=promotion.RULE_ACTOR,
                    actor_kind=decision_log.RULE, effective_at=effective_at,
                    reason=item.get("reason"), amber=item.get("amber"),
                    status=item.get("status"), replacing=item.get("replacing"),
                    census_after=False,
                    gate={"gate_application": application,
                          "package_instant": (_iso(m.received) if m.received else
                                              (_iso(package_instant) if package_instant
                                               else None)),
                          "promoted_with": with_})
                moved_periods.add(item.get("period") or period)
        out.promoted = tuple(m.dataset_id for m, _w, _v in work)
        for p in sorted(moved_periods):
            census.after_move(conn, trigger="promote", period=p)


def _agency(m: Member) -> str:
    from qa_tools.common import hierarchy

    return hierarchy.dataset(m.dataset_id).agency_id


def _reconfirm(conn, period: str, members, work, warehouse) -> None:
    """Under the slot locks: every supply it promotes is still waiting, and
    every table its counted verdicts read that it does not promote holds
    what it held when the application saw it (criterion 17). Anything
    changed is contention."""
    from qa_tools.common import decision_log, supersession

    promoting_tables = {m.table for m, _w, _v in work}
    for m, item, _v in work:
        if m.supply not in supersession.waiting_in(conn, m.dataset_id,
                                                   item.get("period") or period):
            raise _Contention(f"{m.supply} is no longer waiting")
    for table, held in warehouse.items():
        if table in promoting_tables:
            continue
        from qa_tools.common import hierarchy

        ds = hierarchy.dataset_for_table(table).dataset_id
        h = decision_log.held(conn, ds, period)
        now = h.holder if h and h.held_as in (decision_log.PROMOTED, decision_log.SUBSTITUTED,
                                              decision_log.INHERITED) else None
        if now != held:
            raise _Contention(f"{table} now holds {now or 'nothing'}, not {held or 'nothing'}")


# ---------------------------------------------------------------------------
# The entries
# ---------------------------------------------------------------------------

def after_arrival(collection_id: str, arrival, *, effective_at: str, run_by: str | None = None,
                  entry: str = PACKAGE) -> Applied:
    """THE PACKAGE GATE (REQ-PIPE-266 criteria 2, 3, 7 and 8): reached from
    the per-arrival lifecycle and the processing pass's ungated path. A
    supply filed to no period goes through the rule's own refusal, as
    before; one whose package is not all checked waits, its gate owed."""
    from qa_tools.common import decision_log, filing, promotion

    with supply_db.connect(label="mothman:gate") as conn:
        items = filing.supplies_of(conn, arrival)
    filed = [i for i in items if i.get("period")]
    unfiled = [i for i in items if not i.get("period")]
    out = Applied()
    if unfiled:
        got = promotion.after_runs(
            _only(arrival, unfiled), [], agency_id=_agency_of(collection_id),
            collection_id=collection_id, actor=promotion.RULE_ACTOR,
            actor_kind=decision_log.RULE, effective_at=effective_at)
        out.refused.update(got.refused)
        out.failed.update(got.failed)
        out.frozen.update(got.frozen)
    for item in filed:
        with supply_db.connect(label="mothman:gate") as conn:
            package = package_of(conn, item["dataset_id"], item["supply"])
            if package is None:
                # FILED, BUT NO RECEIPT RECORDED: its package cannot be read,
                # so it cannot be gated - said, never skipped in silence
                # (post-build-review #274).
                out.failed[item["dataset_id"]] = (
                    f"{item['supply']} is filed to {item['period']} but no receipt is "
                    f"recorded for it, so its delivery's package cannot be read and it "
                    f"is not gated")
                continue
            if not package.complete:
                owe_gate(conn, package, dataset_id=item["dataset_id"])
                out.waiting = waiting_words(package)
                print(f"{item['supply']}: {out.waiting}")
                continue
            owed = owed_gate(conn, package)
            members = []
            for ds, sup in package.supplies:
                if ds == item["dataset_id"] and sup == item["supply"]:
                    members.append(item)
                    continue
                got = _member_item(conn, ds, sup)
                if got is not None:
                    members.append(got)
        applied = apply(collection_id, package.period, entry=entry, checked=members,
                        effective_at=effective_at, run_by=run_by, delivery=package.delivery,
                        package_instant=package.received,
                        retries=owed.caused_by_application if owed else None)
        if applied.contended:
            with supply_db.connect(label="mothman:gate") as conn:
                owe_gate(conn, package, dataset_id=item["dataset_id"])
        elif owed is not None and not applied.failed:
            from qa_tools.common import recheck

            recheck.clear(owed.id, f"gate/{applied.application}")
        _merge(out, applied)
    return out


def run_owed(item) -> "Applied":
    """An owed 'gate' item (REQ-PIPE-266 criterion 3): its package, gated
    once every file of it is checked - from recorded results, never by
    re-running tools. Still waiting leaves it owed."""
    from qa_tools.common import decision_log, hierarchy, recheck

    with supply_db.connect(label="mothman:gate") as conn:
        collection_id = hierarchy.dataset(item.dataset_id).collection_id
        package = package_at(conn, collection_id, item.period, item.delivery,
                             item.package_instant)
        if not package.supplies:
            recheck.clear(item.id, "gate/nothing-filed")
            return Applied()
        if not package.complete:
            return Applied(waiting=waiting_words(package))
        members = [x for x in (_member_item(conn, ds, sup) for ds, sup in package.supplies)
                   if x is not None]
        effective = decision_log.follows(conn, item.caused_by_decision) \
            if item.caused_by_decision else _completing_instant(conn, package)
    applied = apply(collection_id, package.period, entry=PACKAGE, checked=members,
                    effective_at=effective, delivery=package.delivery,
                    package_instant=package.received, retries=item.caused_by_application)
    if not applied.contended and not applied.failed:
        recheck.clear(item.id, f"gate/{applied.application}")
    return applied


def _completing_instant(conn, package: Package) -> str:
    """WHEN A RETRIED OR RESUMED PACKAGE GATE TAKES EFFECT - one caused by a
    load or by the application it retries (post-build-review #274 D1): when
    its first attempt did, the effective instant of the arrival whose run
    completed the package (orchestrate.effective_at_of, the rule that
    attempt used), so a replay stamps the same instant however many attempts
    it took. It used to be the wall clock, which put a replayed history's
    promotion today. The replay clock where no arrival can be named.

    NEVER BEFORE A DECISION ALREADY IN EFFECT IN ITS PERIOD: a retried
    knock-on's readers are gated against the promotion that caused it, so
    they take effect after it (decision_log.follows), not at their own
    arrival's earlier instant."""
    from qa_tools.common import arrivals, asset_time, decision_log, replay_clock
    from qa_tools.tools import orchestrate

    rows = conn.execute(
        f"SELECT id FROM {decision_log.TABLE} WHERE collection_id = ? "
        "AND (to_slot = ? OR from_slot = ?) ORDER BY effective_at DESC, id DESC LIMIT 1",
        [package.collection_id, package.period, package.period]).fetchall()
    floor = decision_log.follows(conn, rows[0][0]) if rows else None

    def at_least_floor(text: str) -> str:
        if floor is None:
            return text
        return max(text, floor, key=lambda t: asset_time.parse_instant(t, "gate retry"))

    keys = [r[0] for r in conn.execute(
        f'SELECT run_key FROM "{qa_store.SCHEMA}".run WHERE completed_at IS NOT NULL '
        "AND scope = 'arrival' AND (dataset_id, supply_id) IN "
        "(SELECT * FROM unnest(?::text[], ?::text[])) "
        "ORDER BY run_seq NULLS FIRST, completed_at",
        [[ds for ds, _s in package.supplies], [s for _ds, s in package.supplies]]
    ).fetchall()]
    if keys:
        found = {a.run_id: a for a in arrivals.arrivals_from_records(
            package.collection_id, conn=conn)}
        if keys[-1] in found:
            return at_least_floor(orchestrate.effective_at_of(package.collection_id,
                                                              found[keys[-1]]))
    return replay_clock.now().isoformat()


def _member_item(conn, dataset_id: str, supply: str) -> dict | None:
    """A package member, in filing.supplies_of's shape, where it is still
    waiting to be decided - None where it is already promoted or decided."""
    from qa_tools.common import filing, supersession, supply_files

    rows = conn.execute(f"SELECT slot FROM {filing.CURRENT} WHERE dataset_id = ? "
                        "AND supply_id = ?", [dataset_id, supply]).fetchall()
    if not rows or not rows[0][0]:
        return None
    period = rows[0][0]
    if supply not in supersession.waiting_in(conn, dataset_id, period):
        return None
    staged = supply_files.tables_in(conn, dataset_id, supply, supply_db.STAGING_SCHEMA)
    found = supply_files.resolve(conn, dataset_id, supply)
    return {"dataset_id": dataset_id, "supply": supply, "period": period,
            "physical_tables": sorted(staged),
            "contested": len(staged) > 1 or bool(found and found.is_pair)}


def _only(arrival, items):
    """The arrival, for the unfiled half - promotion.after_runs reads its
    supplies itself, which for an unfiled supply is the same one."""
    return [arrival]


def _agency_of(collection_id: str) -> str:
    from qa_tools import collections

    return collections.by_id(collection_id).agency_id


def _merge(out: Applied, more: Applied) -> None:
    out.application = more.application or out.application
    out.promoted = tuple(out.promoted) + tuple(more.promoted)
    out.refused.update(more.refused)
    out.failed.update(more.failed)
    out.frozen.update(more.frozen)
    out.held_back.update(more.held_back)
    out.not_judged.update(more.not_judged)
    out.contended = out.contended or more.contended
    out.reevaluations += more.reevaluations
    out.waiting = out.waiting or more.waiting


def report(applied: Applied) -> None:
    """The terminal's line for what one application did - promotion.report's,
    plus the waiting and contended cases."""
    from qa_tools.common import promotion

    promotion.report(applied.as_after_run())
    if applied.contended:
        print("gate: another gate holds this period - the gate is owed to the next pass")
