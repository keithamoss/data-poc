"""A decision runs a supply's QA again, as a run of its own (REQ-PIPE-140).

ONE EXECUTOR for every decision-triggered run (NFR 1): un-supersede,
re-file, and later the re-check on promotion (REQ-PIPE-121). A second
implementation is how "which checks touch this table" comes to have two
answers.

THE SHAPE, in order - and it is an arrival's own shape, on purpose:
  1. the run is OWED, recorded in the transaction of the decision that
     causes it (criterion 7) - `owe()`;
  2. a run id of its own is minted, `<the supply's run>__r<N>`, so nothing
     an earlier run recorded is overwritten (criterion 3);
  3. its view schema is the supply's filed period's overlay, built exactly
     as an arrival's is (period_overlay.rebuild_for_arrival);
  4. the collection's own orchestrator runs the four tools, recording the
     decision as the cause on the run (criterion 4);
  5. the gate is applied to it as to an arrival (promotion.after_runs);
  6. only then is the owed record cleared - a crash between the run and
     the gate leaves it owed rather than lost.

A RUN THAT BREAKS (criterion 8) leaves the decision in place and the
supply's earlier verdict current - its run never completed, so it is not
the supply's current run - reports the failure, and stays owed. Finishing
owed runs is REQ-PIPE-151's processing pass (Keith, 2026-10-05: no
interim command).

ONLY FROM THE ORCHESTRATOR PATH (criterion 6): this reads supply rows
through the tools, so nothing on a read-committed-history path may import
it - tests/test_recheck.py asserts the import graph.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from qa_tools.common import replay_clock as _replay_clock
from qa_tools.common import qa_store, supply_db

RECHECK = "recheck"
REEVALUATE = "reevaluate"
#: A gate application owed from recorded results (REQ-PIPE-266 criterion 3):
#: never a re-run of any tool - gate.run_owed applies it.
GATE = "gate"
TABLE = f'"{qa_store.SCHEMA}".owed_run'

#: The shared orchestrator (qa_tools/tools/orchestrate.py, REQ-PIPE-243) is
#: imported lazily, so importing this does not import the QA tools.


class RecheckRefused(RuntimeError):
    """A re-run that cannot be made, with the reason."""


@dataclass(frozen=True)
class Owed:
    id: int
    kind: str
    dataset_id: str
    supply_id: str | None
    period: str | None
    caused_by_decision: int | None
    caused_by_load: int | None
    run_key: str | None
    attempts: int
    last_failure: str | None
    #: The tables a re-evaluation is for (REQ-PIPE-121) - empty for a re-check.
    tables: list | None = None
    #: A 'gate' item's package and the application it retries (REQ-PIPE-266).
    caused_by_application: int | None = None
    delivery: str | None = None
    package_instant: object = None


@dataclass(frozen=True)
class Outcome:
    owed_id: int
    run_key: str
    completed: bool
    message: str
    #: The supply's status after the run - green, amber, red - or None.
    status: str | None = None
    #: Not run because the agreement backstop refuses its dataset (Keith,
    #: 2026-10-11, morning-report (f)) - left owed, and not a failure.
    frozen: bool = False
    #: Where a completed re-check left the supply, for the one outcome panel
    #: (REQ-PIPE-163 criteria 19 and 26): the period it was checked against,
    #: whether the gate promoted it, and - where it did not - why it waits.
    period: str | None = None
    promoted: bool | None = None
    waits_because: str | None = None
    #: A PROMOTED supply re-checked (REQ-PIPE-164 criterion 8): no gate, and
    #: it stays promoted whatever came back.
    stays_promoted: bool = False
    #: Its status before the run, for the panel's before and after (criterion 17).
    before: str | None = None
    #: Left owed because another gate application holds its period, or the
    #: period changed under it (REQ-PIPE-267 criterion 17) - contention,
    #: never a failure of the pass.
    contended: bool = False
    #: A 'gate' item whose package is still being checked (REQ-PIPE-266).
    waiting: bool = False
    #: A re-evaluation that left a supply NOT JUDGED - a check whose re-run
    #: still records nothing that counts (Keith, 2026-10-25, post-build-review
    #: #274 D2): left owed for the next pass, and a red, never a failure.
    not_judged: bool = False


_OWED_COLUMNS = ("id", "kind", "dataset_id", "supply_id", "period", "caused_by_decision",
                 "caused_by_load", "run_key", "attempts", "last_failure", "tables",
                 "caused_by_application", "delivery", "package_instant")


def owe(conn: supply_db.SupplyConnection, *, dataset_id: str, supply_id: str,
        decision_id: int | None = None, load_id: int | None = None) -> int:
    """Record that this supply's QA is owed again, in the caller's
    transaction (criterion 7). Owing the same thing twice for the same
    cause is one record."""
    if (decision_id is None) == (load_id is None):
        raise RecheckRefused("a re-run is owed to exactly one cause - a decision or a load")
    rows = conn.execute(
        f"SELECT id FROM {TABLE} WHERE kind = ? AND dataset_id = ? AND supply_id = ? "
        "AND cleared_at IS NULL AND caused_by_decision IS NOT DISTINCT FROM ? "
        "AND caused_by_load IS NOT DISTINCT FROM ?",
        [RECHECK, dataset_id, supply_id, decision_id, load_id]).fetchall()
    if rows:
        return int(rows[0][0])
    return int(conn.execute(
        f"INSERT INTO {TABLE} (kind, dataset_id, supply_id, caused_by_decision, "
        "caused_by_load, owed_at) VALUES (?, ?, ?, ?, ?, ?) RETURNING id",
        [RECHECK, dataset_id, supply_id, decision_id, load_id,
         _replay_clock.now()]).fetchall()[0][0])


def owed(conn: supply_db.SupplyConnection, dataset_id: str | None = None) -> list[Owed]:
    """What is owed and not yet run, oldest first."""
    rows = conn.execute(
        f"SELECT {', '.join(_OWED_COLUMNS)} FROM {TABLE} WHERE cleared_at IS NULL "
        "AND (?::text IS NULL OR dataset_id = ?) ORDER BY owed_at, id",
        [dataset_id, dataset_id]).fetchall()
    return [Owed(*row) for row in rows]


def first_run_id(dataset_id: str, supply_id: str) -> str:
    """The run id this supply's own runs are named from - its arrival's, or
    for a settled pair's supply one of its own (REQ-PIPE-193 criterion 14).
    An identity only: the supply's TABLE is the resolver's to say."""
    from qa_tools.common import supply_files

    return supply_files.run_id_of(dataset_id, supply_id)


def _next_run_id(conn, first: str) -> str:
    """The next unused `__r<N>` - counting the ids an owed run has already
    taken as well as the runs recorded. An attempt that broke before its
    run was opened holds its id on the owed record alone, and minting
    past only `qa.run` handed the same id to the next owed re-check, whose
    results would then replace the first's (post-build-review #114, D2)."""
    like = first.replace("_", r"\_") + r"\_\_r%"
    rows = conn.execute(
        f'SELECT run_key FROM "{qa_store.SCHEMA}".run WHERE run_key LIKE ? '
        f"UNION SELECT run_key FROM {TABLE} WHERE run_key LIKE ?", [like, like]).fetchall()
    taken = [supply_db.split_run(r[0])[1] for r in rows
             if supply_db.split_run(r[0])[0] == first]
    return supply_db.rerun_id(first, max(taken, default=0) + 1)


def _owed_item(conn, owed_id: int) -> tuple[Owed, object]:
    rows = conn.execute(
        f"SELECT {', '.join(_OWED_COLUMNS)}, cleared_at FROM {TABLE} WHERE id = ?",
        [owed_id]).fetchall()
    if not rows:
        raise RecheckRefused(f"nothing is owed under id {owed_id}")
    *fields, cleared_at = rows[0]
    return Owed(*fields), cleared_at


def mint_run_id(conn, dataset_id: str, supply_id: str, *, owed_id: int | None = None,
                taken: str | None = None) -> str:
    """The supply's next `__r<N>` run id - or `taken`, an owed run's id from an
    earlier attempt, so a retry completes the same run. MINTED UNDER A LOCK,
    so two runs of one supply at once cannot take the same number
    (post-build-review #114, D2)."""
    first = first_run_id(dataset_id, supply_id)
    with conn.raw.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(?))", [f"rerun/{first}"])
        run_key = taken or _next_run_id(conn, first)
        if owed_id is not None:
            conn.execute(f"UPDATE {TABLE} SET run_key = ?, attempts = attempts + 1 "
                         "WHERE id = ?", [run_key, owed_id])
    return run_key


def execute(*, dataset_id: str, supply_id: str, run_key: str, purpose: dict,
            run_by: str | None = None, on_step=None, warehouse_for=()):
    """THE ONE EXECUTOR (NFR 1): run the collection's own tools over a staged,
    filed supply, as a run of its own, against its filed period's overlay -
    exactly as an arrival's run is built. Returns (arrival, results). Raises
    whatever the run raises; the caller decides what owing it means."""
    from qa_tools.common import filing, hierarchy, period_overlay
    from qa_tools.common.git_identity import get_run_by

    with supply_db.connect(label="mothman:recheck") as conn:
        filed = conn.execute(
            f"SELECT slot, delivery FROM {filing.CURRENT} WHERE dataset_id = ? "
            "AND supply_id = ?", [dataset_id, supply_id]).fetchall()
    if not filed or not filed[0][0]:
        raise RecheckRefused(f"{supply_id} is filed to no period, so there is no period "
                             f"to check it against")
    period, delivery = filed[0]
    received_at = filing.received_at_of(dataset_id, supply_id)
    entry_ds = hierarchy.dataset(dataset_id)
    from qa_tools import collections

    from qa_tools.tools import orchestrate

    coll = collections.by_id(entry_ds.collection_id)
    # REFUSED BY NAME BEFORE ANYTHING IS STAGED OR OVERLAID (REQ-PIPE-240
    # criterion 6): a collection with no adapter raises NoAdapterError here.
    collections.adapter(coll)
    tables = [d.table for d in coll.datasets]

    arrival = SimpleNamespace(
        run_id=run_key, received_at=received_at, sequence=0, delivery_name=delivery,
        files_by_dataset={dataset_id: (supply_id,)},
        # THE SUPPLY IT IS ABOUT, SAID RATHER THAN DERIVED (REQ-PIPE-193
        # criterion 13): a settled pair's supply has its own file's receipt,
        # whose key names no table, so nothing downstream may rebuild the
        # supply, its period or its table from `received_at`.
        supply_ids={dataset_id: supply_id},
        # A GATE APPLICATION'S RE-CHECK (REQ-PIPE-267 criterion 6) reads these
        # tables from the warehouse, as the period will stand.
        warehouse_for=tuple(warehouse_for))
    # NO run_index (REQ-PIPE-279 criterion 19): the results rebuild orders runs
    # by run_seq, and a re-check was stamped with its arrival's run_index only
    # so the old order had something to sort it by (post-build-review #161).
    entry = {
        "run_id": run_key, "received_at": received_at.isoformat(), "delivery": delivery,
        "csv_path": "",
        # WHAT THIS RUN IS FOR, AND WHY (criteria 3 and 4).
        "purpose": {"dataset_id": dataset_id, "supply_id": supply_id, "period": period,
                    **purpose},
    }
    try:
        period_overlay.rebuild_for_arrival(arrival, tables=tables)
    except Exception:
        # The run's own clean-up is in _run_one's `finally`, which an overlay
        # that broke half-built never reaches (#114, minor).
        orchestrate.discard_run_schemas(run_key)
        raise
    results = orchestrate.run_one(entry_ds.collection_id, entry, _replay_clock.now().isoformat(),
                                  run_by or get_run_by(), on_step=on_step)
    return arrival, results


#: The advisory-lock space an owed item's claim lives in - beside the
#: processing pass's own (processing_pass.PASS_LOCK_SPACE, ARRIVAL_LOCK_SPACE).
OWED_CLAIM_SPACE = 51512

#: What a runner says when another runner already has the item.
CLAIMED_ELSEWHERE = ("this is already being run elsewhere - it will finish there, and it "
                     "stays owed until it does")


def run(owed_id: int, *, run_by: str | None = None, on_step=None) -> Outcome:
    """Run one owed item - claimed first, so no two runners run it at once.

    THE CLAIM (post-build-review #136): the terminal runs an owed item
    straight after the decision that owed it, and the processing pass runs
    whatever is owed - so both can reach one item, and without a claim both
    executed it under one run key, one's schema tidy-up able to drop the
    other's views mid-run. A session advisory lock on a connection held for
    the whole run: released when the run ends, or when its process does,
    so a crash never leaves an item claimed for ever. A runner that finds
    it claimed skips it and leaves it owed - nothing broke, so nothing is
    recorded as a failure."""
    with supply_db.connect(label="mothman:recheck-claim") as claim:
        got = claim.execute("SELECT pg_try_advisory_lock(?, ?)",
                            [OWED_CLAIM_SPACE, owed_id]).fetchone()[0]
        if not got:
            return Outcome(owed_id, "", False, CLAIMED_ELSEWHERE)
        try:
            return _run_claimed(owed_id, run_by=run_by, on_step=on_step)
        finally:
            claim.execute("SELECT pg_advisory_unlock(?, ?)", [OWED_CLAIM_SPACE, owed_id])


def _run_claimed(owed_id: int, *, run_by: str | None = None, on_step=None) -> Outcome:
    """Run one owed item this process has claimed: a re-check (a supply's own
    checks again, then the gate) or a re-evaluation (REQ-PIPE-121's knock-on,
    knock_on.complete) - and clear it. Read only after the claim, so an item
    another runner finished meanwhile reads as already run."""
    from qa_tools.common import decision_log, hierarchy

    with supply_db.connect(label="mothman:recheck") as conn:
        item, cleared_at = _owed_item(conn, owed_id)
        if cleared_at is not None:
            return Outcome(item.id, item.run_key or "", True, "already run")
        # A REFUSED DATASET IS FROZEN (Keith, 2026-10-11, morning-report (f)):
        # nothing about it moves until its undeclared change is restored or
        # declared, so a re-check or re-evaluation owed to it waits - still
        # owed, never a failure.
        from qa_tools.common import agreement_drift

        try:
            refused = agreement_drift.refusals(conn, [item.dataset_id])
        except Exception:  # noqa: BLE001 - an unevaluable backstop refuses nothing
            refused = {}
        # A RE-EVALUATION IS OWED UNDER ITS WRITER but runs its readers, so
        # each reader is checked in knock_on.complete instead (delivery-critic
        # on (f)-(i), findings 2 and 3).
        if item.kind != REEVALUATE and item.dataset_id in refused:
            return Outcome(item.id, item.run_key or "", False,
                           f"{item.dataset_id} is refused by the agreement backstop, so this "
                           f"waits until the change is restored or declared - still owed.",
                           frozen=True)
        if item.kind == REEVALUATE:
            from qa_tools.common import knock_on

            return knock_on.complete(item, run_by=run_by, on_step=on_step)
        if item.kind == GATE:
            return _run_gate(item)
        filed = conn.execute(
            f"SELECT slot FROM {_filing_current()} WHERE dataset_id = ? AND supply_id = ?",
            [item.dataset_id, item.supply_id]).fetchall()
        if not filed or not filed[0][0]:
            raise RecheckRefused(
                f"{item.supply_id} is filed to no period, so there is no period to check "
                f"it against")
        period = filed[0][0]
        run_key = mint_run_id(conn, item.dataset_id, item.supply_id, owed_id=item.id,
                              taken=item.run_key)
        # PROMOTED, SO NOT RE-GATED (REQ-PIPE-164 criteria 8 and 25; Keith,
        # 2026-10-10): its new verdict is recorded and shown, and taking it out
        # stays a person's decision.
        promoted_here = decision_log.promoted_into(conn, item.dataset_id, period) == item.supply_id
        from qa_tools.common import supply_status

        try:
            before = supply_status.status(conn, item.dataset_id, item.supply_id)
        except Exception:  # noqa: BLE001 - the message, never the run, depends on it
            before = None
    entry_ds = hierarchy.dataset(item.dataset_id)
    try:
        arrival, results = execute(
            dataset_id=item.dataset_id, supply_id=item.supply_id, run_key=run_key,
            purpose={"scope": "full", "caused_by_decision": item.caused_by_decision,
                     "caused_by_load": item.caused_by_load},
            run_by=run_by, on_step=on_step)
    except Exception as exc:  # noqa: BLE001 - criterion 8: reported, left owed
        message = f"{type(exc).__name__}: {exc}"
        fail(item.id, message)
        # A MISSING CHECK STOPS EVERYTHING, as in an arrival's run (REQ-PIPE-188
        # criterion 6; Keith, 2026-10-12) - left owed AND raised.
        from qa_tools.common import asked_for

        if isinstance(exc, asked_for.MissingCheck):
            raise
        return Outcome(item.id, run_key, False,
                       f"the re-check of {item.supply_id} did not complete ({message}); its "
                       f"earlier verdict stands and the re-check is still owed")
    # READ AFTER THE RUN (post-build-review #192 F7): a person may have
    # demoted it while it ran, and then the gate applies.
    with supply_db.connect(label="mothman:recheck") as conn:
        promoted_here = (decision_log.promoted_into(conn, item.dataset_id, period)
                         == item.supply_id)
    if promoted_here:
        return _promoted_outcome(item, run_key, period, before)
    # THE GATE, AS FOR AN ARRIVAL (REQ-PIPE-141 criterion 7) - under the
    # settings in force now - AS A GATE APPLICATION (REQ-PIPE-267 criterion 2):
    # this owed-item runner is a gate entry, so a re-filed partner waiting in
    # the period is gated with it. Contended, the re-check stays owed and its
    # results stand - but the next pass runs it WHOLE again, tools and all
    # (execute() above), since a 'recheck' item has no gate-only retry.
    from qa_tools.common import filing, gate

    del arrival, results, entry_ds
    with supply_db.connect(label="mothman:recheck") as conn:
        items = [i for i in filing.supplies_of(conn, SimpleNamespace(
            received_at=filing.received_at_of(item.dataset_id, item.supply_id),
            files_by_dataset={item.dataset_id: (item.supply_id,)},
            supply_ids={item.dataset_id: item.supply_id}))]
    applied = gate.apply(hierarchy.dataset(item.dataset_id).collection_id, period,
                         entry=gate.RECHECK, checked=items, effective_at=_cause_instant(item),
                         run_by=run_by)
    gate.report(applied)
    if applied.contended:
        return Outcome(item.id, run_key, False,
                       f"Checked against {period}; another gate holds {period}, so its gate "
                       f"is applied by the next pass - still owed.", period=period,
                       contended=True)
    gated = applied.as_after_run()
    from qa_tools.common import supply_status

    clear(item.id, run_key)
    with supply_db.connect(label="mothman:recheck") as conn:
        try:
            verdict = supply_status.status(conn, item.dataset_id, item.supply_id)
        except Exception:  # noqa: BLE001 - the message, never the run, depends on it
            verdict = None
    # THE OUTCOME, NOT TWO IDS (post-build-review #115, D5): what it came out
    # as against which period, and whether the gate promoted it.
    promoted = item.dataset_id in gated.promoted
    why = None if promoted else (gated.refused.get(item.dataset_id) or "it waits for a person")
    then = f"Promoted into {period}." if promoted else f"Not promoted - {why}."
    return Outcome(item.id, run_key, True,
                   f"Checked against {period}: {verdict or 'no verdict'}. {then}",
                   status=verdict, period=period, promoted=promoted, waits_because=why,
                   before=before)


def _run_gate(item) -> Outcome:
    """An owed 'gate' item (REQ-PIPE-266 criterion 3): applied from recorded
    results by gate.run_owed - no tool runs - and left owed while its
    package is still being checked or its period is held by another gate."""
    from qa_tools.common import gate

    applied = gate.run_owed(item)
    gate.report(applied)
    if applied.waiting:
        return Outcome(item.id, "", False, f"gate owed: {applied.waiting}", waiting=True)
    if applied.contended:
        return Outcome(item.id, "", False, f"another gate holds {item.period}; the gate is "
                       f"still owed", period=item.period, contended=True)
    if applied.failed:
        message = "; ".join(f"{d}: {w}" for d, w in sorted(applied.failed.items()))
        fail(item.id, message)
        return Outcome(item.id, "", False, f"the gate of {item.period} did not complete "
                       f"({message}); it is still owed", period=item.period)
    return Outcome(item.id, f"gate/{applied.application}", True,
                   f"{item.period}: gated - promoted {', '.join(applied.promoted) or 'nothing'}",
                   period=item.period)


def _promoted_outcome(item, run_key: str, period: str, before: str | None) -> Outcome:
    """A promoted supply's re-check, cleared with no gate (criterion 8): its
    new verdict, that it is still promoted and the period keeps it, and - where
    it came back red - demote as what takes it out and acknowledge as what
    records that it stays (criterion 13)."""
    from qa_tools.common import rechecking, supply_status

    with supply_db.connect(label="mothman:recheck") as conn:
        try:
            verdict = supply_status.status(conn, item.dataset_id, item.supply_id)
        except Exception:  # noqa: BLE001 - the message, never the run, depends on it
            verdict = None
        promoted_on = rechecking.promoted_on(conn, item.dataset_id, period)
    clear(item.id, run_key, found_worse=rechecking.is_worse(promoted_on, verdict))
    message = (f"Checked against {period}: {verdict or 'no verdict'} (was "
               f"{before or 'no verdict'}). It is still promoted - {period} keeps it.")
    if verdict == "red":
        message += (
            f" To take it out of {period}, demote it:\n"
            f"  mothman supply decide --operation demote --dataset {item.dataset_id} "
            f"--period {period} --supply {item.supply_id} --reason '<why>'\n"
            f"To record that it stays, acknowledge its new verdict:\n"
            f"  mothman supply decide --operation acknowledge --dataset {item.dataset_id} "
            f"--period {period} --supply {item.supply_id} --reason '<why>'")
    return Outcome(item.id, run_key, True, message, status=verdict, period=period,
                   promoted=None, stays_promoted=True, before=before)


def _cause_instant(item) -> str:
    """When the gate's decision takes effect: as long after the decision that
    owed this re-check as it really ran (decision_log.follows - Keith,
    2026-10-06, post-build-review #117 D7). Live that is when it ran; a replay
    of four years still stamps the cause's instant, never today (#116)."""
    from qa_tools.common import decision_log

    with supply_db.connect(label="mothman:recheck") as conn:
        return decision_log.follows(conn, item.caused_by_decision)


def _filing_current() -> str:
    from qa_tools.common import filing

    return filing.CURRENT


def fail(owed_id: int, message: str) -> None:
    """An attempt that broke: the item stays owed, with why (criterion 8)."""
    with supply_db.connect(label="mothman:recheck") as conn:
        conn.execute(f"UPDATE {TABLE} SET last_failure = ? WHERE id = ?", [message, owed_id])


def clear(owed_id: int, run_key: str, found_worse: bool | None = None) -> None:
    """Cleared only once its work - run AND gate - is done (criterion 7).

    `found_worse` is recorded for a PROMOTED supply's re-check only: whether
    it came back worse than the verdict it was promoted on - the value a
    period's _manifest reads for its acknowledged column (REQ-PIPE-130
    criterion 12 as amended by Keith, 2026-10-15), recorded here rather than
    computed in the view, which cannot compute a supply's current verdict."""
    with supply_db.connect(label="mothman:recheck") as conn:
        conn.execute(f"UPDATE {TABLE} SET cleared_at = ?, cleared_by_run = ?, "
                     "last_failure = NULL, found_worse = ? WHERE id = ?",
                     [_replay_clock.now(), run_key, found_worse, owed_id])


def run_all_owed(*, collection_id: str | None = None, kinds=(REEVALUATE,),
                 run_by: str | None = None, on_step=None, limit: int = 1000,
                 ids=None, deadline: float | None = None) -> list[Outcome]:
    """Run what is owed, oldest first, until nothing of these kinds is left -
    a promotion a re-evaluation makes owes its own, which this picks up too
    (REQ-PIPE-121 criterion 11). Bounded: a supply promotes at most once, so
    a cascade ends; `limit` is a backstop, never the expected stop. An item
    that fails stays owed and is not retried in the same call.

    `ids` runs only those owed items - a bulk re-check's own (REQ-PIPE-177
    criterion 17). `deadline` (a time.monotonic() instant) is the processing
    pass's budget: once it has passed, NO NEW item is started and the rest
    stay owed for the next pass (criterion 24)."""
    import time

    from qa_tools.common import hierarchy

    wanted = None if ids is None else set(ids)
    out: list[Outcome] = []
    tried: set[int] = set()
    while len(out) < limit:
        if deadline is not None and time.monotonic() >= deadline:
            return out
        with supply_db.connect(label="mothman:recheck") as conn:
            # Its own connection, so its own schema check: every
            # promote_after ends here, and on a database nothing else has
            # prepared, owed_run does not exist yet.
            qa_store.ensure_schema(conn)
            pending = [o for o in owed(conn) if o.kind in kinds and o.id not in tried
                       and (wanted is None or o.id in wanted)
                       and (collection_id is None
                            or _collection_of(hierarchy, o.dataset_id) == collection_id)]
        if not pending:
            return out
        item = pending[0]
        tried.add(item.id)
        try:
            out.append(run(item.id, run_by=run_by, on_step=on_step))
        except RecheckRefused as exc:
            fail(item.id, str(exc))
            out.append(Outcome(item.id, item.run_key or "", False, str(exc)))
    return out


def _collection_of(hierarchy, dataset_id: str) -> str | None:
    try:
        return hierarchy.dataset(dataset_id).collection_id
    except hierarchy.UnknownDatasetError:
        return None
