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
#: A dataset the agreement backstop refused - configuration drift, not red
#: data (Keith, 2026-10-11, morning-report (h)): its own status, so a
#: scheduler can send it to whoever owns the agreement.
EXIT_REFUSED = 3

#: The decision-log actions that mean "the gate ran on this supply".
GATED_ACTIONS = ("promote", "promotion-withheld", "promotion-refused")

#: Which collection's lifecycle handles an arrival comes from the registry
#: (REQ-PIPE-240) - every collection the hierarchy declares, through its
#: adapter. It was a two-entry map here until then.

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
    from qa_tools.common import supply_files

    return supply_files.arrival_of(supply)


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


def _waiting_for_package(conn, arrival, gate_mod) -> str | None:
    """The waiting line where this checked arrival's package gate is owed.
    An arrival with no receipt instant has no package to look up.

    ITS SUPPLIES AS RECORDED - every receipt of its dataset from its arrival,
    a contested pair's '#1' and '#2' too (post-build-review #274 D5). The id
    was rebuilt from the receipt instant alone, which no pair's supply is, so
    a pair waiting for its package was reported as a failure."""
    from qa_tools.common import asset_time, qa_store

    received = getattr(arrival, "received_at", None)
    if received is None:
        return None
    for dataset_id in sorted(getattr(arrival, "files_by_dataset", {}) or {}):
        base = f"{dataset_id}@{asset_time.arrival_key(received)}"
        supplies = sorted(sup for (sup,) in conn.execute(
            f'SELECT supply_id FROM "{qa_store.SCHEMA}".supply_receipt '
            "WHERE dataset_id = ? AND (supply_id = ? OR supply_id LIKE ?)",
            [dataset_id, base, base.replace("_", r"\_") + "#%"]).fetchall()
            if _base(sup) == base) or [base]
        for supply in supplies:
            package = gate_mod.package_of(conn, dataset_id, supply)
            if package is not None and gate_mod.owed_gate(conn, package) is not None:
                return gate_mod.waiting_words(package)
    return None


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
    from qa_tools import collections

    for collection in collections.all_collections():
        found.extend(arrivals.arrivals_from_records(collection.id, deliveries_dir))
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
    #: (datasets, supplies) this pass held while turned off (REQ-PIPE-179
    #: criterion 26), counted apart as schedule-ended holds are.
    turned_off: tuple[int, int] = (0, 0)
    refiled: list = field(default_factory=list)
    #: Datasets the agreement backstop refused this pass (REQ-PIPE-173
    #: criterion 4), each held rather than processed.
    refused: list = field(default_factory=list)
    #: What it re-filed once a dataset was no longer refused.
    refiled_cleared: list = field(default_factory=list)
    #: Arrivals left ungated because their dataset is refused (Keith,
    #: 2026-10-11, (f); delivery-critic finding 4) - waiting, not failed, and
    #: holding back nothing else in their collection.
    left_frozen: list = field(default_factory=list)
    #: Arrivals CHECKED, WAITING FOR THEIR PACKAGE (REQ-PIPE-266 criterion
    #: 3) - not a failure, and holding back nothing else; the last file of
    #: the package gates it whole.
    left_waiting: list = field(default_factory=list)
    #: Declared calendar corrections awaiting the asset manager (REQ-PIPE-170
    #: criterion 20) - noted, never computed: their moves are worked out when
    #: one is opened.
    pending_corrections: list = field(default_factory=list)
    #: Parked correction moves this pass carried out once their blocker
    #: cleared (Keith, 2026-10-11, (p)) - (dataset, supply, from, to).
    parked_moved: list = field(default_factory=list)

    @property
    def nothing_to_do(self) -> bool:
        return not (self.processed or self.gated_only or self.left_locked or self.refiled
                    or self.refiled_cleared or self.refused or self.parked_moved
                    or self.left_behind_failure or self.left_behind_locked
                    or self.left_for_budget or self.failures or self.owed
                    or self.left_waiting)

    @property
    def exit_status(self) -> int:
        """Criterion 20: a failure outranks a red result - and a refusal sits
        between them (PROVISIONAL, 2026-10-11): something must be retried
        before anything else, but an agreement that no longer matches what
        was judged is a bigger problem than one red verdict."""
        if self.failures:
            return EXIT_FAILED
        if self.refused:
            return EXIT_REFUSED
        return EXIT_RED if self.red else EXIT_OK


def _owed_failure(outcome) -> bool:
    """An owed item that did not complete is a failure of the pass - unless
    it waited on a refused dataset, which is the backstop working; another
    gate held its period, which is contention (REQ-PIPE-267 criterion 17);
    or it is a package gate still waiting for a file (REQ-PIPE-266); or a
    re-evaluation left a supply not judged, which is a red that stays owed
    (Keith, 2026-10-25, post-build-review #274 D2)."""
    return (not outcome.completed and not getattr(outcome, "frozen", False)
            and not getattr(outcome, "contended", False)
            and not getattr(outcome, "waiting", False)
            and not getattr(outcome, "not_judged", False))


def _red(results) -> bool:
    return any((r or {}).get("status") in ("fail", "error") for r in results or ())


def _steps(collection_id):
    from qa_tools.tools import orchestrate

    return orchestrate.steps(collection_id)


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
    # THE AGREEMENT BACKSTOP (REQ-PIPE-173): a dataset whose recorded
    # judgements no longer match the agreement, with nothing declared to
    # account for it, is refused - said here, held at filing - and one
    # cleared since the last pass has its held supplies filed by the rule.
    # WHAT THE BACKSTOP COULD NOT CHECK (delivery-critic #152, 8): the parked
    # correction drain must not treat "not checked" as "not refused".
    unchecked: set[str] = set()
    backstop_read = False
    try:
        from qa_tools.common import agreement_drift
        report.refiled_cleared.extend(agreement_drift.refile_cleared(say=say))
        errors: list = []
        found = agreement_drift.refusals(errors=errors)
        report.refused = sorted(found)
        # A DATASET THAT COULD NOT BE EVALUATED is a failure of this pass,
        # never a silent pass (delivery-critic on 173, #9).
        for ds, exc in errors:
            failed(f"agreement backstop for {ds}", exc)
            unchecked.add(ds)
        backstop_read = True
        # RED on the dashboard (criterion 4), and its own exit status, 3
        # (Keith, 2026-10-11, (h)) - through exit_status, never `red`, which
        # says a recorded RESULT is red (#10).
        line = agreement_drift.pass_line(found)
        if line:
            say(line)
            for refusal in found.values():
                say(refusal.message())
    except Exception as exc:  # noqa: BLE001 - the next pass evaluates it again
        failed("agreement backstop", exc)
    # A MERGED CORRECTION IS ONLY NOTED (REQ-PIPE-170 criterion 20): which
    # are pending, from configuration and the applied record. Nothing about
    # its moves is computed or stored here.
    try:
        from qa_tools.common import correction_apply, supply_db as _db

        with _db.connect(read_only=True, label="mothman:pending-corrections") as conn:
            report.pending_corrections = [p.reference for p in correction_apply.pending(conn)]
        if report.pending_corrections:
            say(f"{len(report.pending_corrections)} calendar correction(s) await the data "
                f"asset's manager: {', '.join(report.pending_corrections)}.")
    except Exception as exc:  # noqa: BLE001 - noting is not processing; say it and go on
        say(f"note: could not read pending corrections ({type(exc).__name__}: {exc}).")
    # AFTER THE BACKSTOP, AND NEVER FOR A REFUSED DATASET (delivery-critic
    # on 173, #2): a rule re-file of a schedule-ended hold files a supply
    # against the changed terms exactly as a new arrival would.
    try:
        from qa_tools.common import schedule_ended
        report.refiled.extend(schedule_ended.refile_covered(
            say=say, skip=frozenset(report.refused)))
    except Exception as exc:  # noqa: BLE001 - the holds are durable; the next pass retries
        failed("schedule-ended holds", exc)
    # A PARKED CORRECTION MOVE WHOSE BLOCKER HAS CLEARED (Keith, 2026-10-11,
    # (p)) moves now, to the period confirmed - never for a refused dataset,
    # and before arrivals, so a re-check it owes is run this pass.
    try:
        from qa_tools.common import correction_apply, supply_db as _db

        if backstop_read:
            with _db.connect(label="mothman:parked-corrections") as conn:
                report.parked_moved.extend(correction_apply.drain_parked(
                    conn, skip=frozenset(report.refused) | unchecked, say=say))
        else:
            say("Parked correction moves wait for a pass that can read the agreement "
                "backstop.")
    except Exception as exc:  # noqa: BLE001 - parked moves are durable; the next pass retries
        failed("parked correction moves", exc)

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
            from qa_tools.tools import stage

            stage.stage_arrival(arrival.collection_id, arrival)
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
            report.turned_off = schedule_ended.turned_off_by_runs(conn, report.processed)
    except Exception as exc:  # noqa: BLE001 - the holds are durable; the next pass retries
        failed("schedule-ended holds", exc)
    # OWED WORK (criterion 11): re-evaluations and re-checks alike, each
    # cleared only when its work completes; a failure stays owed.
    try:
        for outcome in recheck.run_all_owed(kinds=(recheck.REEVALUATE, recheck.RECHECK,
                                                   recheck.GATE),
                                            run_by=run_by):
            report.owed.append(outcome)
            if _owed_failure(outcome):
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
            from qa_tools import collections

            for collection in collections.all_collections():
                outcome = ticket_reconciler.after_runs(collection.id)
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
    steps = _steps(arrival.collection_id)
    from qa_tools.common import gate as gate_mod

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
        # THE UNGATED PATH IS A GATE ENTRY (REQ-PIPE-267 criterion 2) and goes
        # through the one package gate (REQ-PIPE-266 criterion 2).
        steps.promote_after(arrival, results, run_by)
        report.gated_only.append(arrival.run_id)
        if _red(results):
            report.red = True
    else:
        # The run step prints its own "--- <run> ---" header (#120 D13).
        got = arrival_lifecycle.process(arrival, steps=steps, among=among,
                                        run_timestamp=run_timestamp, run_by=run_by)
        report.processed.append(arrival.run_id)
        if _red(got):
            report.red = True
    with supply_db.connect(read_only=True, label="mothman:process") as conn:
        after = state_of(arrival, recorded(conn))
        waiting = _waiting_for_package(conn, arrival, gate_mod) if after != PROCESSED else None
    if waiting:
        # CHECKED, WAITING FOR ITS PACKAGE (REQ-PIPE-266 criterion 3): not a
        # failure, and nothing later is held back for it.
        report.left_waiting.append(arrival.run_id)
        say(f"{arrival.run_id}: {waiting}")
        return
    if after != PROCESSED:
        # LEFT UNGATED BY THE FREEZE is waiting, not failing (delivery-critic
        # on (f)-(i), finding 4): the first pass after the refusal clears
        # gates it, and nothing else in its collection is held back for it.
        from qa_tools.common import agreement_drift

        try:
            refused = agreement_drift.refusals(
                dataset_ids=sorted(getattr(arrival, "files_by_dataset", {}) or {}))
        except Exception:  # noqa: BLE001 - an unevaluable backstop refuses nothing
            refused = {}
        if refused:
            report.left_frozen.append(arrival.run_id)
            say(f"{arrival.run_id}: not gated - {', '.join(sorted(refused))} "
                f"{'is' if len(refused) == 1 else 'are'} refused by the agreement backstop; "
                f"it is gated once that is cleared")
            return
        raise RuntimeError(f"its gate outcome was not recorded (it is {after}), so it is "
                           f"still owed - see the promotion step's report above")
