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

import importlib
from dataclasses import dataclass
from types import SimpleNamespace

from qa_tools.common import replay_clock as _replay_clock
from qa_tools.common import qa_store, supply_db

RECHECK = "recheck"
REEVALUATE = "reevaluate"
TABLE = f'"{qa_store.SCHEMA}".owed_run'

#: The orchestrator module per collection - imported lazily, so importing
#: this does not import every collection's tools.
_ORCHESTRATORS = {
    "civil-registration": ("qa_tools.bdm.orchestrate_bdm",
                           "qa_tools.bdm.build_per_run_warehouses", "TABLE"),
    "child-protection": ("qa_tools.cp.orchestrate_cp",
                         "qa_tools.cp.build_cp_warehouses", "TABLES"),
}


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


@dataclass(frozen=True)
class Outcome:
    owed_id: int
    run_key: str
    completed: bool
    message: str
    #: The supply's status after the run - green, amber, red - or None.
    status: str | None = None


_OWED_COLUMNS = ("id", "kind", "dataset_id", "supply_id", "period", "caused_by_decision",
                 "caused_by_load", "run_key", "attempts", "last_failure", "tables")


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
    """The run id an arrival gave this supply - its staged table's name."""
    from qa_tools.common import hierarchy

    logical = hierarchy.dataset(dataset_id).table
    key = supply_id.rsplit("@", 1)[1]
    head, _, ordinal = key.partition("#")
    return f"{logical}__{head}" + (f"__{ordinal}" if ordinal else "")


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
            run_by: str | None = None, on_step=None):
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
    module_name, tables_module, tables_name = _ORCHESTRATORS[entry_ds.collection_id]
    module = importlib.import_module(module_name)
    tables = getattr(importlib.import_module(tables_module), tables_name)
    tables = [tables] if isinstance(tables, str) else list(tables)
    arrival = SimpleNamespace(
        run_id=run_key, received_at=received_at, sequence=0, delivery_name=delivery,
        files_by_dataset={dataset_id: (supply_id,)})
    entry = {
        "run_id": run_key, "received_at": received_at.isoformat(), "delivery": delivery,
        "csv_path": "", "data_run_id": first_run_id(dataset_id, supply_id),
        # WHAT THIS RUN IS FOR, AND WHY (criteria 3 and 4).
        "purpose": {"dataset_id": dataset_id, "supply_id": supply_id, "period": period,
                    **purpose},
    }
    try:
        period_overlay.rebuild_for_arrival(arrival, tables=tables)
    except Exception:
        # The run's own clean-up is in _run_one's `finally`, which an overlay
        # that broke half-built never reaches (#114, minor).
        module._discard_this_runs_schemas(run_key)
        raise
    results = module._run_one(entry, _replay_clock.now().isoformat(),
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
    from qa_tools.common import decision_log, hierarchy, promotion

    with supply_db.connect(label="mothman:recheck") as conn:
        item, cleared_at = _owed_item(conn, owed_id)
        if cleared_at is not None:
            return Outcome(item.id, item.run_key or "", True, "already run")
        if item.kind == REEVALUATE:
            from qa_tools.common import knock_on

            return knock_on.complete(item, run_by=run_by, on_step=on_step)
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
        return Outcome(item.id, run_key, False,
                       f"the re-check of {item.supply_id} did not complete ({message}); its "
                       f"earlier verdict stands and the re-check is still owed")
    # THE GATE, AS FOR AN ARRIVAL (REQ-PIPE-141 criterion 7) - under the
    # settings in force now, which after_runs reads at this instant.
    gated = promotion.after_runs(
        [arrival], results, agency_id=entry_ds.agency_id,
        collection_id=entry_ds.collection_id, actor=promotion.RULE_ACTOR,
        actor_kind=decision_log.RULE, effective_at=_cause_instant(item))
    promotion.report(gated)
    from qa_tools.common import supply_status

    clear(item.id, run_key)
    with supply_db.connect(label="mothman:recheck") as conn:
        try:
            verdict = supply_status.status(conn, item.dataset_id, item.supply_id)
        except Exception:  # noqa: BLE001 - the message, never the run, depends on it
            verdict = None
    # THE OUTCOME, NOT TWO IDS (post-build-review #115, D5): what it came out
    # as against which period, and whether the gate promoted it.
    if item.dataset_id in gated.promoted:
        then = f"Promoted into {period}."
    else:
        then = (f"Not promoted - {gated.refused.get(item.dataset_id) or 'it waits for a person'}.")
    return Outcome(item.id, run_key, True,
                   f"Checked against {period}: {verdict or 'no verdict'}. {then}",
                   status=verdict)


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


def clear(owed_id: int, run_key: str) -> None:
    """Cleared only once its work - run AND gate - is done (criterion 7)."""
    with supply_db.connect(label="mothman:recheck") as conn:
        conn.execute(f"UPDATE {TABLE} SET cleared_at = ?, cleared_by_run = ?, "
                     "last_failure = NULL WHERE id = ?", [_replay_clock.now(), run_key, owed_id])


def run_all_owed(*, collection_id: str | None = None, kinds=(REEVALUATE,),
                 run_by: str | None = None, on_step=None, limit: int = 1000) -> list[Outcome]:
    """Run what is owed, oldest first, until nothing of these kinds is left -
    a promotion a re-evaluation makes owes its own, which this picks up too
    (REQ-PIPE-121 criterion 11). Bounded: a supply promotes at most once, so
    a cascade ends; `limit` is a backstop, never the expected stop. An item
    that fails stays owed and is not retried in the same call."""
    from qa_tools.common import hierarchy

    out: list[Outcome] = []
    tried: set[int] = set()
    while len(out) < limit:
        with supply_db.connect(label="mothman:recheck") as conn:
            # Its own connection, so its own schema check: every
            # promote_after ends here, and on a database nothing else has
            # prepared, owed_run does not exist yet.
            qa_store.ensure_schema(conn)
            pending = [o for o in owed(conn) if o.kind in kinds and o.id not in tried
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
