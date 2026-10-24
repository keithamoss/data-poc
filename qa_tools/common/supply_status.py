"""A supply's status from the newest COUNTED result of every check about it
- one function (REQ-PIPE-121 NFR 4, shared with REQ-DASH-126 and the status
REQ-PIPE-130 criterion 11 records at promotion).

WHICH RESULTS ARE ABOUT A SUPPLY is results_about's answer, the one
function the promotion gate, the knock-on, the dashboard build
(pipeline.red_promoted, pipeline.warehouse_counts) and carried.decide all
read (REQ-PIPE-279 criterion 21) - from what each RESULT recorded reading,
never from whose run it was nor from a run's record of physical names.

WHICH OF THOSE COUNT (REQ-PIPE-269 criterion 7) is the same function's
second answer, given the VIEW - the warehouse as at an instant, judged from
the decision log alone (criterion 9). A result is SHOWN about every supply
it read; it COUNTS toward a supply in the warehouse only where every supply
of every table THAT CHECK read is the one in the warehouse for its table in
a period that supply is in (criteria 1 and 2), toward a waiting supply
whatever else it read (criterion 3), and - recorded not evaluated for want
of a table - only toward the table the check is declared on (criterion 4).
Counting first and then taking the newest per check is what lets a check
fall back to its newest counted result.

WHERE NOTHING COUNTS for an in-warehouse supply, a check OWED to it - declared
on its table, or reading only tables that each have a supply in the
warehouse - reads red with a structured reason: 'recheck-owed' while a
decision that moved a table owes a re-evaluation not yet run, naming that
decision, and otherwise 'no-current-result' (criterion 5). A check NOT owed
counts nothing (criterion 6). Neither falls back to a result about a supply
no longer in the warehouse.

NEWEST IS THE LATER-OPENED RUN (REQ-PIPE-279 criterion 9; Keith, K1 = A):
qa.run.run_seq, the order runs were opened for evaluation.

READ-ONLY, and only recorded QA results and the decision log - never a
supply row. So it is safe on the dashboard build's path as well as the gate's.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from qa_tools.common import qa_store, supply_db

#: The structured reasons an owed check with no counted result reads red
#: under (criterion 5) - a reader can tell an owed re-check, which clears by
#: itself and raises nothing (#113), from a result that will not come.
RECHECK_OWED, NO_CURRENT_RESULT = "recheck-owed", "no-current-result"

#: How a period holds a supply IN THE WAREHOUSE - promoted, inherited or
#: substituted (criterion 1), as qa.slot_holds names them.
IN_THE_WAREHOUSE = ("promoted", "substituted", "inherited")


@dataclass(frozen=True)
class View:
    """The warehouse a status is judged against: as at `as_at` (an instant,
    ISO text or datetime), or as the decision log stands now where None. The
    effective time of each decision, never when it was recorded - the same
    answer the dashboard's date on show and the terminal give (criterion 9)."""
    as_at: object = None


@dataclass
class About:
    """results_about's two answers: every result SHOWN about the supply,
    oldest first by run_seq, and those that COUNT toward it in the view -
    with a red record standing in for each owed check that has none."""
    shown: list[dict]
    counted: list[dict]


# ---- the warehouse at an instant ---------------------------------------------

class Holdings:
    """What each (dataset, period) holds in the warehouse at one instant."""

    def __init__(self, held: dict[tuple[str, str], str]):
        self._held = held
        self._periods: dict[tuple[str, str], list[str]] = {}
        for (ds, period), supply in held.items():
            self._periods.setdefault((ds, supply), []).append(period)

    def holder(self, dataset_id: str, period: str) -> str | None:
        return self._held.get((dataset_id, period))

    def periods_of(self, dataset_id: str, supply: str) -> list[str]:
        return sorted(self._periods.get((dataset_id, supply), ()))


def holdings_at(conn, dataset_ids, as_at=None) -> Holdings:
    """The warehouse at `as_at` for these datasets, from qa.slot_holds - the
    one definition of what a slot holds (REQ-PIPE-130 criterion 9)."""
    held: dict[tuple[str, str], str] = {}
    for ds in sorted(set(dataset_ids)):
        for slot, held_as, holder in conn.execute(
                f'SELECT slot, held_as, holder FROM "{qa_store.SCHEMA}".slot_holds(?, ?)',
                [ds, _iso(as_at)]).fetchall():
            if held_as in IN_THE_WAREHOUSE and holder:
                held[(ds, slot)] = holder
    return Holdings(held)


class HoldingsTimeline:
    """The same answers at every instant, for a reader that asks many - the
    dashboard build. Made from the slot timeline the build already reads
    (pipeline.slot_timeline.for_dataset), which is qa.slot_holds asked at
    each instant a decision took effect, so it answers exactly as
    holdings_at does; tests/test_warehouse_view.py holds the two together."""

    def __init__(self, entries_by_dataset: dict[str, list[dict]]):
        self._changes: list[tuple[datetime, str, str, str | None]] = []
        for ds, entries in entries_by_dataset.items():
            for e in entries:
                holder = e.get("holder") if e.get("held_as") in IN_THE_WAREHOUSE else None
                self._changes.append((_instant(e["at"]), ds, e["slot"], holder))
        self._changes.sort(key=lambda c: c[0])

    def at(self, instant) -> Holdings:
        when = _instant(instant)
        held: dict[tuple[str, str], str | None] = {}
        for at, ds, slot, holder in self._changes:
            if at > when:
                break
            held[(ds, slot)] = holder
        return Holdings({k: v for k, v in held.items() if v})

    def instants(self, dataset_ids) -> list[datetime]:
        wanted = set(dataset_ids)
        return sorted({at for at, ds, _s, _h in self._changes if ds in wanted})


# ---- what is owed --------------------------------------------------------------

@dataclass
class Owing:
    """The re-evaluations decisions owe (REQ-PIPE-121), for 'owed at T':
    from each cause's effective instant and whether it has cleared - never
    the wall clock (criterion 5)."""
    items: list[tuple[str, frozenset, int, datetime, object]] = field(default_factory=list)

    def owing(self, periods, tables, at) -> tuple[int, datetime] | None:
        """The newest decision owing a re-evaluation of one of `tables` in
        one of `periods` that is still owed at `at`, as (id, effective)."""
        when = _instant(at) if at is not None else None
        found = None
        for period, owed_tables, decision_id, effective, cleared_at in self.items:
            if period not in periods or not owed_tables & set(tables):
                continue
            if when is not None and effective > when:
                continue
            # CLEARED BY THE RUN IT CAUSED, which follows its cause on the
            # asset's timeline (decision_log.follows): cleared, it is owed at
            # no instant from its cause on.
            if cleared_at is not None:
                continue
            if found is None or (effective, decision_id) > (found[1], found[0]):
                found = (decision_id, effective)
        return found


def owing(conn) -> Owing:
    """Every re-evaluation a decision owes, from qa.owed_run and the log."""
    from qa_tools.common import recheck

    rows = conn.execute(
        f"SELECT o.period, o.tables, o.caused_by_decision, d.effective_at, o.cleared_at "
        f'FROM {recheck.TABLE} o JOIN "{qa_store.SCHEMA}".decision d '
        "ON d.id = o.caused_by_decision WHERE o.kind = ? ORDER BY o.id",
        [recheck.REEVALUATE]).fetchall()
    return Owing([(p, frozenset(t or ()), int(d), _instant(e), c) for p, t, d, e, c in rows])


# ---- the rule ------------------------------------------------------------------

def declared_on(record: dict) -> str | None:
    """The dataset a check is declared on, from its id (asset.agency.
    collection.dataset...), else the dataset it was recorded for."""
    from qa_tools.common import check_id as cid

    parsed = cid.try_parse(record.get("check_id") or "")
    return parsed.dataset if parsed else record.get("dataset_id")


def _dataset_of(table: str) -> str | None:
    from qa_tools.common import hierarchy

    try:
        return hierarchy.dataset_for_table(table).dataset_id
    except hierarchy.UnknownDatasetError:
        return None


def _matches(holdings: Holdings, reads: dict, period: str) -> bool:
    """Whether the warehouse in `period` is what this result read: each
    supply READ is the one the period holds, and a table it read nothing of
    (HELD, ABSENT) has nothing there - by supply id, never physical name."""
    for table, read in reads.items():
        state = read.get("state")
        if state == qa_store.NO_SUPPLY:
            continue
        ds = _dataset_of(table)
        if ds is None:
            continue
        held = holdings.holder(ds, period)
        if state == qa_store.READ:
            if held != read.get("supply_id"):
                return False
        elif held is not None:
            return False
    return True


def counts_toward(record: dict, dataset_id: str, periods: list[str],
                  holdings: Holdings) -> bool:
    """THE RULE (criteria 1 to 4) for one result already about the supply:
    `periods` are those its supply is in the warehouse in at the view's
    instant - none for a waiting supply."""
    from qa_tools.common import carried

    reads = record.get("reads")
    if not reads:
        return True  # a single-table or file result is about its own supply
    if carried.not_evaluated_reason(record) and declared_on(record) != dataset_id:
        return False  # criterion 4: only toward the table that asks
    if not periods:
        return True  # criterion 3: a waiting supply counts what read it
    return any(_matches(holdings, reads, p) for p in periods)


def _owed(record: dict, dataset_id: str, periods: list[str], holdings: Holdings) -> bool:
    """Criteria 5 and 6: declared on this table, or reading only tables that
    each have a supply in the warehouse in one of its periods."""
    if declared_on(record) == dataset_id:
        return True
    tables = [t for t, r in (record.get("reads") or {}).items()
              if r.get("state") != qa_store.NO_SUPPLY and _dataset_of(t)]
    return any(all(holdings.holder(_dataset_of(t), p) for t in tables) for p in periods)


def count(dataset_id: str, supply: str, shown: list[dict], *, holdings: Holdings,
          owed: Owing | None, at=None) -> list[dict]:
    """The results that COUNT toward `supply` in the warehouse `holdings`
    describe, oldest first, then one red stand-in per owed check with none.
    Pure: the gate (results_about) and the dashboard build
    (pipeline.warehouse_counts) both call it, so neither keeps a rule of its
    own (criterion 7)."""
    periods = holdings.periods_of(dataset_id, supply)
    counted = [r for r in shown if counts_toward(r, dataset_id, periods, holdings)]
    if not periods:
        return counted
    have = {r["check_id"] for r in counted}
    newest: dict[str, dict] = {}
    for r in shown:
        if r.get("reads"):
            newest[r["check_id"]] = r
    for check, r in newest.items():
        if check in have or not _owed(r, dataset_id, periods, holdings):
            continue
        cause = owed.owing(periods, list(r.get("reads") or {}), at) if owed is not None else None
        counted.append(stand_in(r, cause))
    return counted


def stand_in(record: dict, cause) -> dict:
    """The red an owed check reads with no counted result (criterion 5)."""
    from qa_tools.common import carried

    red = {k: v for k, v in record.items() if k not in carried.NOT_EVALUATED_KEYS}
    red.update({"status": "fail", "metric_value": None,
                "warehouse_reason": RECHECK_OWED if cause else NO_CURRENT_RESULT,
                "owed_by_decision": cause[0] if cause else None,
                "owed_since": cause[1].isoformat() if cause else None})
    return red


# ---- the one function -------------------------------------------------------------

def _shown(conn, dataset_id: str, supply: str) -> list[dict]:
    """Every completed, agreed result about `supply` of `dataset_id`, oldest
    first by run_seq and then as each run recorded them, each cross-table
    one carrying what it recorded reading (`reads`).

    A RESULT IS ABOUT A SUPPLY BY WHAT IT RECORDED, in one of five states:

      its run's own   a single-table result recorded under a run whose
                      qa.run.supply_id is this supply - such a result reads
                      only its run's own supply (criterion 3), so the run's
                      supply is its supply
      its file        a file check's, whose recorded delivery and file are
                      one of this supply's files (supply_files.resolve): a
                      pair's arrival run is shared by both its supplies, and
                      which file each one IS is settled later
                      (post-build-review #262 D2). A supply never filed has
                      no recorded file, so its run's own rule applies
      READ            a cross-table result whose qa.check_read for this
                      dataset's table names this supply - a contested
                      table's included, read as the supply it fell through to
      HELD            the supply was deliberately not read: NOT about it
      ABSENT          nothing of the table was read: about no supply of it
                      (K2 = A - it shows only where its check is declared)
      NO-SUPPLY       a sample's or a trial's table: about no supply at all

    Only the first two are about the supply, and that is the whole rule.
    The run-level qa.tables_read is not consulted: it says what a RUN read,
    and matching it by physical name was a guess about each result.

    TIE-BREAK: none is needed. run_seq is unique per run; within a run, the
    order the run recorded its results (qa.check_result.id), exactly as one
    run's own reader reads them.
    """
    from qa_tools.common import hierarchy
    from qa_tools.common import qa_results_reader as reader
    from qa_tools.common import supply_files

    table = hierarchy.dataset(dataset_id).table
    s = qa_store.SCHEMA
    own = "(r.dataset_id = ? AND r.supply_id = ?)"
    found = supply_files.resolve(conn, dataset_id, supply)
    if found is not None and found.delivery is not None:
        files = ([found.filename] if found.filename
                 else supply_files.files_in_order(conn, dataset_id, found.delivery)
                 if len(found.own) > 1 else [])
        by_file = "(c.dataset_id = ? AND c.delivery = ? AND c.filename = ANY(?))"
        by_file_params = [dataset_id, found.delivery, files]
    else:
        by_file, by_file_params = own, [dataset_id, supply]
    cursor = conn.execute(
        f'SELECT c.*, c.id AS result_row FROM "{s}".check_result_visible c '
        f'JOIN "{s}".run_visible r ON r.run_key = c.run_key '
        "WHERE c.supply_state = ? AND ("
        f"(c.scope NOT IN (?, ?) AND {own}) "
        f"OR (c.scope = ? AND {by_file}) "
        f'OR EXISTS (SELECT 1 FROM "{s}".check_read k WHERE k.check_result_id = c.id '
        "AND k.logical_table = ? AND k.state = ? AND k.supply_id = ?)) "
        "ORDER BY r.run_seq, c.id",
        [qa_store.AGREED, qa_store.CROSS_TABLE_SCOPE, qa_store.FILE_SCOPE, dataset_id, supply,
         qa_store.FILE_SCOPE, *by_file_params, table, qa_store.READ, supply])
    records = reader.records_from(cursor.description, cursor.fetchall())
    ids = [r["result_row"] for r in records]
    reads: dict[int, dict] = {}
    if ids:
        for rid, t, state, sup, contested, files in conn.execute(
                f'SELECT check_result_id, logical_table, state, supply_id, contested, '
                f'contested_files FROM "{s}".check_read WHERE check_result_id = ANY(?) '
                "ORDER BY check_result_id, logical_table", [ids]).fetchall():
            reads.setdefault(rid, {})[t] = {"state": state, "supply_id": sup,
                                            "contested": bool(contested),
                                            "contested_files": sorted(files or ())}
    for r in records:
        got = reads.get(r.pop("result_row"))
        if got:
            r["reads"] = got
    return records


def results_about(conn, dataset_id: str, supply: str, *, view: View) -> About:
    """The results SHOWN about `supply` of `dataset_id` and those COUNTED
    toward it in `view` (REQ-PIPE-279 criterion 21; REQ-PIPE-269 criterion
    7), both oldest first - so the last result per check is the newest."""
    shown = _shown(conn, dataset_id, supply)
    tables = {t for r in shown for t in (r.get("reads") or {})}
    datasets = {dataset_id, *(d for d in map(_dataset_of, tables) if d)}
    holdings = holdings_at(conn, datasets, view.as_at)
    owed = owing(conn) if holdings.periods_of(dataset_id, supply) and tables else None
    return About(shown, count(dataset_id, supply, shown, holdings=holdings, owed=owed,
                              at=view.as_at))


def newest_per_check(records: list[dict]) -> list[dict]:
    """The last record per check, in the order each check first appears."""
    latest: dict[str, dict] = {}
    for record in records:
        latest[record["check_id"]] = record
    return list(latest.values())


def latest_results(conn, dataset_id: str, supply: str, *, view: View = View()) -> list[dict]:
    """The newest COUNTED result per check about this supply in `view`
    (results_about), the later-opened run's where two recorded one.
    Includes other datasets' results; status() keeps only what contributes
    to this dataset."""
    return newest_per_check(results_about(conn, dataset_id, supply, view=view).counted)


def status(conn: supply_db.SupplyConnection, dataset_id: str, supply: str, *,
           reads: dict[str, list[str]] | None = None, view: View = View()) -> str | None:
    """green/amber/red (or a quiet status) from the newest counted result of
    every check contributing to this dataset; None where nothing did."""
    from qa_tools.common import promotion

    reads = reads if reads is not None else promotion._declared_reads()
    return promotion.status_of(dataset_id, latest_results(conn, dataset_id, supply, view=view),
                               reads=reads)


# ---- small helpers ---------------------------------------------------------------

def _instant(value) -> datetime:
    from qa_tools.common import asset_time

    return value if isinstance(value, datetime) else asset_time.parse_instant(
        value, "warehouse view")


def _iso(value):
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)
