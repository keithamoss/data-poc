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


@dataclass(frozen=True)
class Outcome:
    owed_id: int
    run_key: str
    completed: bool
    message: str


_OWED_COLUMNS = ("id", "kind", "dataset_id", "supply_id", "period", "caused_by_decision",
                 "caused_by_load", "run_key", "attempts", "last_failure")


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
        "caused_by_load) VALUES (?, ?, ?, ?, ?) RETURNING id",
        [RECHECK, dataset_id, supply_id, decision_id, load_id]).fetchall()[0][0])


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


def run(owed_id: int, *, run_by: str | None = None, on_step=None) -> Outcome:
    """Run one owed re-check: its own run id, the supply's filed period's
    overlay, the collection's tools, then the gate - and clear it."""
    from qa_tools.common import asset_time, decision_log, filing, hierarchy
    from qa_tools.common import period_overlay, promotion
    from qa_tools.common.git_identity import get_run_by

    with supply_db.connect(label="mothman:recheck") as conn:
        rows = conn.execute(
            f"SELECT {', '.join(_OWED_COLUMNS)}, cleared_at FROM {TABLE} WHERE id = ?",
            [owed_id]).fetchall()
        if not rows:
            raise RecheckRefused(f"nothing is owed under id {owed_id}")
        *fields, cleared_at = rows[0]
        item = Owed(*fields)
        if cleared_at is not None:
            return Outcome(item.id, item.run_key or "", True, "already run")
        if item.kind != RECHECK:
            # Criterion 2's readers-only run has no caller until REQ-PIPE-121.
            raise RecheckRefused(f"a {item.kind!r} run is not built yet (REQ-PIPE-121)")
        filed = conn.execute(
            f"SELECT slot, delivery FROM {filing.CURRENT} WHERE dataset_id = ? "
            "AND supply_id = ?", [item.dataset_id, item.supply_id]).fetchall()
        if not filed or not filed[0][0]:
            raise RecheckRefused(
                f"{item.supply_id} is filed to no period, so there is no period to check "
                f"it against")
        period, delivery = filed[0]
        first = first_run_id(item.dataset_id, item.supply_id)
        with conn.raw.transaction():
            # MINTED UNDER A LOCK, so two runs of one supply at once cannot
            # both take the same next number (post-build-review #114, D2).
            conn.execute("SELECT pg_advisory_xact_lock(hashtext(?))", [f"rerun/{first}"])
            run_key = item.run_key or _next_run_id(conn, first)
            conn.execute(f"UPDATE {TABLE} SET run_key = ?, attempts = attempts + 1 "
                         "WHERE id = ?", [run_key, item.id])
    received_at = filing.received_at_of(item.dataset_id, item.supply_id)
    entry_ds = hierarchy.dataset(item.dataset_id)
    module_name, tables_module, tables_name = _ORCHESTRATORS[entry_ds.collection_id]
    module = importlib.import_module(module_name)
    tables = getattr(importlib.import_module(tables_module), tables_name)
    tables = [tables] if isinstance(tables, str) else list(tables)
    arrival = SimpleNamespace(
        run_id=run_key, received_at=received_at, sequence=0, delivery_name=delivery,
        files_by_dataset={item.dataset_id: (item.supply_id,)})
    entry = {
        "run_id": run_key, "received_at": received_at.isoformat(), "delivery": delivery,
        "csv_path": "", "data_run_id": first,
        # WHAT THIS RUN IS FOR, AND WHY (criteria 3 and 4).
        "purpose": {"dataset_id": item.dataset_id, "supply_id": item.supply_id,
                    "scope": "full", "period": period,
                    "caused_by_decision": item.caused_by_decision,
                    "caused_by_load": item.caused_by_load},
    }
    try:
        try:
            period_overlay.rebuild_for_arrival(arrival, tables=tables)
        except Exception:
            # The run's own clean-up is in _run_one's `finally`, which an
            # overlay that broke half-built never reaches (#114, minor).
            module._discard_this_runs_schemas(run_key)
            raise
        results = module._run_one(entry, asset_time.now().isoformat(),
                                  run_by or get_run_by(), on_step=on_step)
    except Exception as exc:  # noqa: BLE001 - criterion 8: reported, left owed
        message = f"{type(exc).__name__}: {exc}"
        with supply_db.connect(label="mothman:recheck") as conn:
            conn.execute(f"UPDATE {TABLE} SET last_failure = ? WHERE id = ?",
                         [message, item.id])
        return Outcome(item.id, run_key, False,
                       f"the re-check of {item.supply_id} did not complete ({message}); its "
                       f"earlier verdict stands and the re-check is still owed")
    # THE GATE, AS FOR AN ARRIVAL (REQ-PIPE-141 criterion 7) - under the
    # settings in force now, which after_runs reads at this instant.
    promotion.report(promotion.after_runs(
        [arrival], results, agency_id=entry_ds.agency_id,
        collection_id=entry_ds.collection_id, actor=promotion.RULE_ACTOR,
        actor_kind=decision_log.RULE, effective_at=asset_time.now().isoformat()))
    with supply_db.connect(label="mothman:recheck") as conn:
        conn.execute(f"UPDATE {TABLE} SET cleared_at = now(), cleared_by_run = ?, "
                     "last_failure = NULL WHERE id = ?", [run_key, item.id])
    return Outcome(item.id, run_key, True, f"{item.supply_id} re-checked as {run_key}")
