"""One processing pass: handle what has arrived, finish what is owed, and
reconcile tickets - never generate anything (REQ-PIPE-151).

WHAT "PROCESSED" MEANS, AND WHY IT IS DERIVED (criteria 2, 4 and 8). An
arrival is processed once its QA run has COMPLETED and the promotion gate has
RUN on it - which the decision log records as a promote, promotion-withheld or
promotion-refused entry for its supply - or, for a supply filed to no slot, an
open assignment hold stands for it. All of that is read back from the database
in one statement whatever the length of history, and nothing keeps a separate
marker of how far processing has got: a stored marker is a second account of
the same fact, and a crash between the two leaves them disagreeing
(backlog.py's own account of why its marker was removed, 2026-09-27).

ONE GLOBAL RECEIPT ORDER (criterion 9). Every collection's arrivals are put in
one order - receipt instant, then the receipt's own sequence, which is global
across deliveries - and each is dispatched to its own collection's per-arrival
lifecycle (REQ-PIPE-086's arrival_lifecycle.process), the same function the
batches call.

TWO LOCKS (criteria 6 and 16), both PostgreSQL advisory locks, so both are
per database and both vanish with the connection that holds them:
  - the PASS lock, held for the whole of a `process`, `run` or `bootstrap`; a
    second one refuses at once, naming the holder and since when, which are
    read from the holder's own connection (application_name and its start) -
    so there is no table of who holds what to fall out of date;
  - an ARRIVAL lock, taken before an arrival is filed and released once its
    gate outcome is recorded, so another process (a Lambda retry, later) can
    never process the same arrival at the same time. Taken with try-lock: an
    arrival another process holds is left for the next pass, never waited on.

NEVER GENERATES OR DELETES (criteria 10 and 17): it reads the delivery tree and
the database, and `mothman pipeline run`/`bootstrap` stay the full rebuild.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field

from qa_tools.common import supply_db

#: Advisory-lock namespaces - the first of the two-int form, so this
#: project's locks are recognisable in pg_locks (classid) and cannot collide
#: with the single-bigint locks elsewhere in the code.
PASS_LOCK_SPACE = 51510
ARRIVAL_LOCK_SPACE = 51511
PASS_LOCK_LABEL = "mothman-pass:"

#: Exit statuses (criterion 20), stated in the command's help.
EXIT_OK, EXIT_RED, EXIT_FAILED, EXIT_LOCKED = 0, 1, 2, 75

#: The decision-log actions that mean "the gate ran on this supply".
GATED_ACTIONS = ("promote", "promotion-withheld", "promotion-refused")

#: Which collection's lifecycle handles an arrival, and how it is named.
COLLECTIONS = {
    "civil-registration": ("qa_tools.bdm.orchestrate_bdm",
                           "qa_tools.bdm.build_per_run_warehouses", "run_"),
    "child-protection": ("qa_tools.cp.orchestrate_cp",
                         "qa_tools.cp.build_cp_warehouses", "cp_run_"),
}

UNCHECKED, UNGATED, PROCESSED = "unchecked", "ungated", "processed"


class PassLockHeld(RuntimeError):
    """Another pass holds this database's pass lock (criterion 16)."""

    def __init__(self, holder: str, since):
        super().__init__(f"another pass is running against this database - `mothman "
                         f"pipeline {holder}`, since {since}. Nothing was changed.")
        self.holder, self.since = holder, since


class _Held:
    """A held pass lock - and the one way to let go of it for a moment."""

    def __init__(self, command: str):
        self.command = command
        self.conn = None

    def take(self) -> None:
        # NEVER A REUSED CONNECTION (REQ-PIPE-158): the refusal below says
        # "since" the holder's backend started, which is when the lock was
        # taken only if the connection was opened to take it.
        conn = supply_db.connect(label=f"{PASS_LOCK_LABEL}{self.command}", reuse=False)
        try:
            got = conn.execute("SELECT pg_try_advisory_lock(?, 1)",
                               [PASS_LOCK_SPACE]).fetchone()[0]
            if not got:
                rows = conn.execute(
                    "SELECT a.application_name, a.backend_start FROM pg_locks l "
                    "JOIN pg_stat_activity a ON a.pid = l.pid "
                    "WHERE l.locktype = 'advisory' AND l.classid = ? AND l.objid = 1 "
                    "AND l.objsubid = 2 AND l.granted "
                    # THIS DATABASE'S HOLDER: the lock is per database, pg_locks
                    # is not - a bootstrap running against another database on
                    # the same server was named as the holder (found by the lock
                    # test while a rebuild ran beside it).
                    "AND l.database = (SELECT oid FROM pg_database "
                    "WHERE datname = current_database())", [PASS_LOCK_SPACE]).fetchall()
                name, since = rows[0] if rows else ("", None)
                raise PassLockHeld(
                    (name or "").removeprefix(PASS_LOCK_LABEL) or "(unknown)",
                    since.isoformat(timespec="seconds") if since else "an unknown time")
        except BaseException:
            conn.close()
            raise
        self.conn = conn

    def release(self) -> None:
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    @contextmanager
    def paused(self):
        """Let go of the lock and its connection for the block, then take it
        back - for copying this database, which PostgreSQL refuses while
        anything is connected to it (REQ-TEST-159). Taking it back raises
        PassLockHeld if another pass got in between, rather than carry on
        beside it."""
        self.release()
        try:
            yield
        finally:
            self.take()


@contextmanager
def pass_lock(command: str):
    """Hold this database's pass lock for the length of the block, or raise
    PassLockHeld naming who has it - before anything is changed. Yields the
    held lock, whose `paused()` lets a checkpoint copy the database."""
    held = _Held(command)
    held.take()
    try:
        yield held
    finally:
        held.release()


@contextmanager
def arrival_lock(conn, run_id: str):
    """Yield True while this connection holds the arrival's lock, False where
    another process holds it (criterion 6)."""
    got = conn.execute("SELECT pg_try_advisory_lock(?, hashtext(?))",
                       [ARRIVAL_LOCK_SPACE, run_id]).fetchone()[0]
    try:
        yield bool(got)
    finally:
        if got:
            conn.execute("SELECT pg_advisory_unlock(?, hashtext(?))",
                         [ARRIVAL_LOCK_SPACE, run_id])


@dataclass
class Recorded:
    """What the database says has been done - criterion 8's one read."""

    completed_runs: set[str] = field(default_factory=set)
    gated: set[tuple[str, str]] = field(default_factory=set)
    held: set[tuple[str, str]] = field(default_factory=set)


def _base(supply: str) -> str:
    """`cp-clients@2025...#1` -> `cp-clients@2025...`: a contested pair's
    supplies share their arrival."""
    return (supply or "").split("#", 1)[0]


def recorded(conn) -> Recorded:
    """Everything criterion 2 asks about, in ONE statement."""
    from qa_tools.common import qa_store

    out = Recorded()
    s = qa_store.SCHEMA
    for kind, a, b in conn.execute(
            f"SELECT 'run', run_key, NULL FROM \"{s}\".run "
            "WHERE completed_at IS NOT NULL AND scope = 'arrival' "
            f"UNION ALL SELECT 'gate', dataset_id, supply FROM \"{s}\".decision "
            f"WHERE action IN ({', '.join('?' for _ in GATED_ACTIONS)}) "
            f"UNION ALL SELECT 'hold', dataset_id, supply_id FROM \"{s}\".hold "
            "WHERE resolved_by IS NULL", list(GATED_ACTIONS)).fetchall():
        if kind == "run":
            out.completed_runs.add(a)
        elif kind == "gate":
            out.gated.add((a, _base(b)))
        else:
            out.held.add((a, _base(b)))
    return out


def supply_of(arrival) -> tuple[str, str]:
    """(dataset, base supply id) - filing._supply_id_for's own rule, without
    the contested suffix."""
    from qa_tools.common import asset_time

    (dataset_id,) = arrival.files_by_dataset
    return dataset_id, f"{dataset_id}@{asset_time.arrival_key(arrival.received_at)}"


def state_of(arrival, rec: Recorded) -> str:
    """Criterion 2: checked AND gated (or held) is processed; checked but not
    gated is owed its gate; anything else is owed the whole lifecycle."""
    if arrival.run_id not in rec.completed_runs:
        return UNCHECKED
    key = supply_of(arrival)
    return PROCESSED if key in rec.gated or key in rec.held else UNGATED


def all_arrivals(deliveries_dir=None, receipts_dir=None) -> list:
    """Every collection's arrivals in ONE receipt order (criterion 9).

    FROM THE DELIVERY RECORDS, NOT THE TREE (REQ-PIPE-152 criterion 6; Keith,
    2026-10-06). The pass records every delivery on disk before it asks, so
    building every arrival from qa.delivery_file gives one source and one
    arrival type - and an object a Lambda recorded straight from S3, with no
    directory anywhere, is an arrival like any other. `receipts_dir` is
    unused now and kept so a caller passing it still works.
    """
    from qa_tools.common import arrivals

    found = []
    for collection_id in COLLECTIONS:
        found.extend(arrivals.arrivals_from_records(collection_id, deliveries_dir))
    found.sort(key=lambda a: (a.received_at, a.sequence, a.run_id))
    return found


def unprocessed(found: list, conn=None) -> list:
    """The arrivals not yet processed, in the order given."""
    if conn is None:
        with supply_db.connect(read_only=True, label="mothman:process") as opened:
            rec = recorded(opened)
    else:
        rec = recorded(conn)
    return [a for a in found if state_of(a, rec) != PROCESSED]


@dataclass
class PassReport:
    processed: list[str] = field(default_factory=list)
    gated_only: list[str] = field(default_factory=list)
    left_locked: list[str] = field(default_factory=list)
    left_behind_failure: list[str] = field(default_factory=list)
    left_behind_locked: list[str] = field(default_factory=list)
    #: Not taken because the pass's budget ran out (REQ-PIPE-152 criterion
    #: 12) - owed to the next pass, and not a failure.
    left_for_budget: list[str] = field(default_factory=list)
    failures: list[tuple[str, str]] = field(default_factory=list)
    owed: list = field(default_factory=list)
    tickets: list[str] = field(default_factory=list)
    red: bool = False
    #: (datasets, supplies) this pass held because a schedule ended
    #: (REQ-PIPE-154 criterion 6), and what it re-filed once dates covered
    #: one (criterion 7).
    schedule_ended: tuple[int, int] = (0, 0)
    refiled: list = field(default_factory=list)

    @property
    def nothing_to_do(self) -> bool:
        return not (self.processed or self.gated_only or self.left_locked or self.refiled
                    or self.left_behind_failure or self.left_behind_locked
                    or self.left_for_budget or self.failures or self.owed)

    @property
    def exit_status(self) -> int:
        """Criterion 20: a failure outranks a red result."""
        if self.failures:
            return EXIT_FAILED
        return EXIT_RED if self.red else EXIT_OK


def _red(results) -> bool:
    return any((r or {}).get("status") in ("fail", "error") for r in results or ())


def _modules(collection_id):
    import importlib

    orchestrator, builder, _ = COLLECTIONS[collection_id]
    return importlib.import_module(orchestrator), importlib.import_module(builder)


def run_pass(*, run_by: str | None = None, say=print, deadline: float | None = None,
             s3_client=None) -> PassReport:
    """Criterion 1's one pass. The caller holds the pass lock.

    `deadline` (a time.monotonic() instant) is a Lambda handler's budget
    (REQ-PIPE-152 criterion 12): once it has passed, no NEW arrival is taken -
    the one in progress finishes - and the rest stay owed to the next pass.
    None, as from the terminal or a scheduler, is no budget at all.
    `s3_client` fetches an arrival recorded from S3 (criterion 6).
    """
    import time

    from qa_tools.common import s3_arrival

    def out_of_time() -> bool:
        return deadline is not None and time.monotonic() >= deadline
    from qa_tools.common import (asset_time, delivery_log, qa_store, recheck,
                                 ticket_reconciler)
    from qa_tools.common.git_identity import get_run_by

    report = PassReport()
    run_by = run_by or get_run_by()

    def failed(what: str, exc: Exception) -> None:
        # CRITERION 20: any stage that fails is 2, whichever stage it is -
        # never an uncaught traceback, which a scheduler reads as 1, "red"
        # (post-build-review #120 D2).
        report.failures.append((what, f"{type(exc).__name__}: {exc}"))
        say(f"{what}: FAILED - {type(exc).__name__}: {exc}")

    try:
        with supply_db.connect(label="mothman:process") as conn:
            qa_store.ensure_schema(conn)
        # The deliveries on disk, recorded with what recognition made of
        # them - write-once, so recording an old one again changes nothing.
        delivery_log.record_all()
        found = all_arrivals()
        todo = unprocessed(found)
        with supply_db.connect(read_only=True, label="mothman:process") as conn:
            rec = recorded(conn)
    except Exception as exc:  # noqa: BLE001 - nothing can be processed without these
        failed("the pass's setup", exc)
        return report
    by_collection: dict[str, list] = {}
    for arrival in found:
        by_collection.setdefault(arrival.collection_id, []).append(arrival)
    blocked: set[str] = set()
    locked_out: set[str] = set()

    def fail_arrival(arrival, exc: Exception) -> None:
        # CRITERION 14: a failed arrival holds back every later one of its
        # own collection, which depend on what it would have filed - and no
        # other collection's.
        blocked.add(arrival.collection_id)
        report.failures.append((arrival.run_id, f"{type(exc).__name__}: {exc}"))
        say(f"{arrival.run_id}: FAILED - {type(exc).__name__}: {exc}; it and every "
            f"later {arrival.collection_id} arrival are left for the next pass")

    # HELD UNTIL DATES EXISTED (REQ-PIPE-154 criterion 7): re-filed by the
    # rule BEFORE this pass's new arrivals, which were all received later -
    # after them, a newer supply of the same dataset was filed first and
    # receipt order broke across the two (post-build-review #131 D7). Still
    # before the owed work, so the re-check each is owed runs - and applies
    # the gate - in this same pass.
    try:
        from qa_tools.common import schedule_ended
        report.refiled.extend(schedule_ended.refile_covered(say=say))
    except Exception as exc:  # noqa: BLE001 - the holds are durable; the next pass retries
        failed("schedule-ended holds", exc)

    # STAGED FIRST, as the batch stages first: a delivery's later files are
    # candidates the overlay sees when its first is checked. Only what is
    # still owed its checks - a gated arrival's table has moved on. A
    # staging failure is that arrival's failure, not the pass's (D2).
    # AN S3 OBJECT IS FETCHED HERE, through its recorded URI (REQ-PIPE-152
    # criterion 6), so everything after reads a local file as it always has.
    fetched = []
    for arrival in todo:
        try:
            fetched.append(s3_arrival.materialise(arrival, s3_client=s3_client))
        except Exception as exc:  # noqa: BLE001 - criterion 14: reported, left owed
            fail_arrival(arrival, exc)
            fetched.append(arrival)
    todo = fetched
    staged: set[str] = set()
    for arrival in todo:
        if arrival.collection_id in blocked or state_of(arrival, rec) != UNCHECKED:
            continue
        if out_of_time():
            break
        try:
            _, builder = _modules(arrival.collection_id)
            builder.stage_arrival(arrival)
            staged.add(arrival.run_id)
        except Exception as exc:  # noqa: BLE001 - criterion 14: reported, left owed
            fail_arrival(arrival, exc)
    staged_failures = {run_id for run_id, _ in report.failures}
    run_timestamp = asset_time.now().isoformat()
    with supply_db.connect(label="mothman:process-arrival-locks") as lock_conn:
        for arrival in todo:
            if arrival.run_id in staged_failures:
                continue
            if arrival.collection_id in blocked:
                report.left_behind_failure.append(arrival.run_id)
                continue
            if arrival.collection_id in locked_out:
                report.left_behind_locked.append(arrival.run_id)
                continue
            # THE BUDGET (REQ-PIPE-152 criterion 12): no new arrival once it
            # has run out, and none the staging above did not reach.
            if out_of_time() or (state_of(arrival, rec) == UNCHECKED
                                 and arrival.run_id not in staged):
                report.left_for_budget.append(arrival.run_id)
                continue
            with arrival_lock(lock_conn, arrival.run_id) as mine:
                if not mine:
                    # RECEIPT ORDER HOLDS (Keith, 2026-10-06, #120 Q3): a
                    # locked arrival holds back the later arrivals of its own
                    # collection, as a failure does - each filing depends on
                    # what the one before it promoted.
                    report.left_locked.append(arrival.run_id)
                    locked_out.add(arrival.collection_id)
                    continue
                try:
                    _one(arrival, by_collection[arrival.collection_id], run_timestamp,
                         run_by, report, say)
                except Exception as exc:  # noqa: BLE001 - criterion 14: reported, left owed
                    fail_arrival(arrival, exc)
    # What this pass's own runs held because a schedule ended, counted apart
    # (REQ-PIPE-154 criterion 6).
    try:
        from qa_tools.common import schedule_ended
        with supply_db.connect(read_only=True, label="mothman:process") as conn:
            report.schedule_ended = schedule_ended.raised_by_runs(conn, report.processed)
    except Exception as exc:  # noqa: BLE001 - the holds are durable; the next pass retries
        failed("schedule-ended holds", exc)
    # OWED WORK (criterion 11): re-evaluations and re-checks alike, each
    # cleared only when its work completes; a failure stays owed.
    try:
        for outcome in recheck.run_all_owed(kinds=(recheck.REEVALUATE, recheck.RECHECK),
                                            run_by=run_by):
            report.owed.append(outcome)
            if not outcome.completed:
                report.failures.append((f"owed #{outcome.owed_id}", outcome.message))
            elif outcome.status == "red":
                report.red = True
    except Exception as exc:  # noqa: BLE001 - it stays owed for the next pass
        failed("owed work", exc)
    # TICKETS LAST (criterion 12), and one line where none are configured.
    try:
        service = ticket_reconciler.service_from_env()
        if service is None:
            report.tickets.append("No ticketing is configured for this environment, so no "
                                  "ticket was reconciled.")
        else:
            for collection_id in COLLECTIONS:
                outcome = ticket_reconciler.after_runs(collection_id)
                ticket_reconciler.report(outcome)
                # A TICKET THAT COULD NOT BE RECONCILED IS A FAILED STAGE
                # (criterion 20; Keith, 2026-10-06, #120 Q1), so a scheduler
                # sees it. The slot state is durable and the next pass
                # retries; the exit status is how anyone learns it is stuck.
                for key, message in (outcome.failed or {}).items():
                    report.failures.append((f"ticket for {key}", message))
    except Exception as exc:  # noqa: BLE001 - the slot state is durable; the next pass retries
        failed("ticket reconciliation", exc)
    return report


def _one(arrival, among, run_timestamp, run_by, report: PassReport, say) -> None:
    """One arrival, under its lock: nothing if it is already processed
    (criterion 7), only the gate if it is checked, otherwise the lifecycle."""
    from qa_tools.common import arrival_lifecycle, qa_store

    with supply_db.connect(read_only=True, label="mothman:process") as conn:
        state = state_of(arrival, recorded(conn))
    if state == PROCESSED:
        return
    orchestrator, _ = _modules(arrival.collection_id)
    if state == UNGATED:
        # CHECKED BUT NOT GATED: its recorded results, the gate, nothing
        # re-run - a second set of results under the same run id is what
        # REQ-PIPE-086 criterion 8 forbids.
        # EVERY SCOPE AND STATE the run recorded, as the batch hands the
        # gate everything its run produced - the gate itself decides which
        # contribute (promotion.status_of), and a cross-table check filed
        # under a sibling is one that does.
        with supply_db.connect(read_only=True, label="mothman:process") as conn:
            results = qa_store._dicts(conn.execute(
                f'SELECT r.* FROM "{qa_store.SCHEMA}".check_result_visible r '
                "WHERE r.run_key = ? ORDER BY r.id", [arrival.run_id]))
        # A RECORDED ROW CALLS IT run_key; the gate gives each arrival only
        # the results carrying its run_id (promotion.after_runs), so without
        # this every result was dropped and a red supply read "no active
        # checks" - found on the first real pass, 2026-10-06.
        for record in results:
            record.setdefault("run_id", record.get("run_key"))
        say(f"{arrival.run_id}: checked earlier - applying the gate")
        orchestrator.STEPS.promote_after(arrival, results, run_by)
        report.gated_only.append(arrival.run_id)
        if _red(results):
            report.red = True
    else:
        # The run step prints its own "--- <run> ---" header (#120 D13).
        got = arrival_lifecycle.process(arrival, steps=orchestrator.STEPS, among=among,
                                        run_timestamp=run_timestamp, run_by=run_by)
        report.processed.append(arrival.run_id)
        if _red(got):
            report.red = True
    with supply_db.connect(read_only=True, label="mothman:process") as conn:
        after = state_of(arrival, recorded(conn))
    if after != PROCESSED:
        raise RuntimeError(f"its gate outcome was not recorded (it is {after}), so it is "
                           f"still owed - see the promotion step's report above")
