"""One record per staged table, written only after that table's load
is durable (REQ-PIPE-060 criteria 13-20, moved into the database by
REQ-PIPE-089 criteria 14 and 22).

IT USED TO BE A COMMITTED FILE TREE, `processing_log/`, and everything
below about ORDERING, PHYSICAL PRESENCE and APPEND-ONLY is unchanged by
the move - those are properties of the record, not of where it lives.
What changed is that the repository stops holding it, and that "latest"
is now the highest id on an append-only table rather than the largest
`recorded_at` string. The second is a real improvement rather than a
consequence: string ordering is only correct while every writer uses
one UTC offset, and a second deployment in another one would have
silently reordered history.

THE ORDERING IS THE LOAD-BEARING PART, and it deserves saying twice
because the two orders look identical in review and fail in opposite
directions.

  Record AFTER the load is durable - a crash between them re-loads a
  table that was already fine. Wasteful, and safe.

  Record BEFORE - a crash between them skips a table that never
  loaded. A silently missing supply.

That asymmetry is also why a re-load must be safe against whatever is
already there: no record means untrusted, so it is REPLACED rather than
appended to.

PHYSICAL PRESENCE IS NOT READABILITY, and that distinction is the whole
mechanism. Criterion 7 used to say a staged table must be readable only
once loaded completely, which cannot be built alongside the rejection of
a whole-delivery transaction: without one, a truncated table is
physically present and physically readable. What delivers the guarantee
instead is this record PLUS the per-run view schema - a check reads
through a view, and the view resolves only tables that have a record
here. An interrupted load leaves a table nothing can see.

WHY NOT ASK THE DATABASE. Deriving completeness from the warehouse
catalogue was the obvious answer and is wrong at exactly the boundary
that matters. The catalogue says a table EXISTS, not that it is
COMPLETE. Crash after three of six tables and three are present,
correctly read as partial; crash during the LAST table and six of six
are present with one truncated, read as complete and skipped for ever.
A truncated table in staging is indistinguishable from a genuinely
short supply and would be QA'd as real data.

APPEND-ONLY, LATEST WINS. A failed load is never retried automatically
- it is for a person, who either rejects that supply or fixes a genuine
bug and reprocesses. A reprocess writes a NEW record rather than editing
the failed one, so the history of what went wrong survives the fix. That
is the same shape REQ-PIPE-034 settled for arrivals, and it makes the
failed-load path structurally identical to REQ-PIPE-059's held supply:
a state needing human action, resolved by an operation or a rejection.

A FAILED LOAD IS A CHECK RESULT, not a separate taxonomy. An invalid
CSV, a missing file, zero bytes, a bad encoding, a schema that does not
match are all red findings on that table.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass

from qa_tools.common import qa_store, supply_db

LOADED = "loaded"
FAILED = "failed"

_TABLE = f'"{qa_store.SCHEMA}".load_outcome'
_FIELDS = ("delivery", "dataset_id", "physical", "outcome", "recorded_at",
           "reason", "row_count")

#: A run that is not a trial sees only real records; a trial sees those
#: PLUS its own. Both halves matter: a trial borrowing an earlier run's
#: tables needs their real records to resolve them, and a trial's own
#: staged tables need records nobody else can see.
_VISIBLE = "(trial_run_id IS NULL OR trial_run_id = ?)"
_REAL_ONLY = "trial_run_id IS NULL"


def _scope(trial: str | None) -> tuple[str, list]:
    return (_VISIBLE, [trial]) if trial else (_REAL_ONLY, [])


@dataclass(frozen=True)
class LoadRecord:
    delivery: str
    dataset_id: str
    physical: str
    outcome: str
    recorded_at: str
    reason: str | None = None
    row_count: int | None = None

    @property
    def loaded(self) -> bool:
        return self.outcome == LOADED


@contextmanager
def _db(conn: supply_db.SupplyConnection | None):
    """Reuse the caller's connection, or open one for the call.

    Every read here sits on a hot path - resolving a run's views asks
    `loaded_tables()` - so a caller already holding a connection passes
    it rather than paying for another. Callers that do not are the CLI
    and one-off tooling, where one connection per call is nothing.
    """
    if conn is not None:
        yield conn
        return
    with supply_db.connect(label="mothman:load-log") as opened:
        qa_store.ensure_schema(opened)
        yield opened


def _rows(cursor) -> list[LoadRecord]:
    return [LoadRecord(**dict(zip(_FIELDS, row))) for row in cursor.fetchall()]


def record(delivery: str, dataset_id: str, physical: str, outcome: str,
           recorded_at: str, reason: str | None = None,
           row_count: int | None = None, trial: str | None = None,
           conn: supply_db.SupplyConnection | None = None) -> LoadRecord:
    """Write one load outcome.

    CALL THIS ONLY ONCE THE LOAD IS DURABLE. Nothing here can check
    that for you - the ordering is the caller's to get right, which is
    why it has a criterion of its own rather than being left as an
    implementation note.

    Returns the record written. It used to return the path of the file
    it wrote, and no caller used that for anything but a truth test.
    """
    if outcome not in (LOADED, FAILED):
        raise ValueError(f"a load outcome is {LOADED!r} or {FAILED!r}, not {outcome!r}")
    entry = LoadRecord(delivery, dataset_id, physical, outcome, recorded_at,
                       reason, row_count)
    with _db(conn) as db:
        db.execute(
            f"INSERT INTO {_TABLE} ({', '.join(_FIELDS)}, trial_run_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [delivery, dataset_id, physical, outcome, recorded_at, reason,
             row_count, trial])
    return entry


def record_load(delivery: str, dataset_id: str, physical: str, outcome: str,
                recorded_at: str, reason: str | None = None,
                row_count: int | None = None, trial: str | None = None,
                conn: supply_db.SupplyConnection | None = None) -> LoadRecord | None:
    """`record()`, but silent where the latest record already says
    exactly this.

    WHY THIS EXISTS, found by running it rather than by reading it: a
    re-run stages every delivery again, and without this each one wrote
    a fresh record for an unchanged table - 42 new records for a run in
    which nothing whatsoever changed. Over a PoC that is clutter; over
    the years of history this is FOR, at ~30 datasets, it is a table
    growing without bound and carrying no signal at all.

    IT DOES NOT WEAKEN CRITERION 19, which is the thing to check before
    reaching for a deduplicate anywhere near an append-only log. That
    criterion is about a CHANGE of outcome - a failed load reprocessed
    into a loaded one - and a change is exactly what this still writes.
    What it stops is a repetition, and the failed record it was meant
    to preserve is preserved by being the latest one until something
    different happens to that table.

    Returns the record written, or None where nothing needed writing.
    """
    with _db(conn) as db:
        latest = latest_for(physical, trial=trial, conn=db)
        if (latest is not None and latest.outcome == outcome
                and latest.reason == reason and latest.row_count == row_count
                and latest.delivery == delivery and latest.dataset_id == dataset_id):
            return None
        return record(delivery, dataset_id, physical, outcome, recorded_at,
                      reason=reason, row_count=row_count, trial=trial, conn=db)


def records(trial: str | None = None,
            conn: supply_db.SupplyConnection | None = None) -> list[LoadRecord]:
    """Every load record ever written, oldest first."""
    where, params = _scope(trial)
    with _db(conn) as db:
        return _rows(db.execute(
            f"SELECT {', '.join(_FIELDS)} FROM {_TABLE} WHERE {where} ORDER BY id",
            params))


def latest_for(physical: str, trial: str | None = None,
               conn: supply_db.SupplyConnection | None = None) -> LoadRecord | None:
    """The current outcome for ONE staged table.

    Its own query rather than a lookup in `latest_by_table()`, because
    `record_load` asks about a single table on every staged table of
    every delivery - which over a re-run of the whole history is the
    difference between one indexed row and the entire log each time.
    """
    with _db(conn) as db:
        where, params = _scope(trial)
        found = _rows(db.execute(
            f"SELECT {', '.join(_FIELDS)} FROM {_TABLE} "
            f"WHERE physical = ? AND {where} ORDER BY id DESC LIMIT 1",
            [physical, *params]))
    return found[0] if found else None


def latest_by_table(trial: str | None = None,
                    conn: supply_db.SupplyConnection | None = None) -> dict[str, LoadRecord]:
    """The current outcome for each staged table.

    LATEST WINS, which is what makes a reprocess work without editing
    history: the failed record stays, and the record written after it
    is the one that counts.
    """
    with _db(conn) as db:
        where, params = _scope(trial)
        found = _rows(db.execute(
            f"SELECT DISTINCT ON (physical) {', '.join(_FIELDS)} FROM {_TABLE} "
            f"WHERE {where} ORDER BY physical, id DESC", params))
    return {entry.physical: entry for entry in found}


def loaded_tables(trial: str | None = None,
                  conn: supply_db.SupplyConnection | None = None) -> frozenset[str]:
    """Physical tables a check may read.

    A table absent from this set is UNLOADED as far as anything
    downstream is concerned, whether it is physically there or not.
    """
    return frozenset(name for name, entry in latest_by_table(trial, conn).items()
                     if entry.loaded)


def failures(trial: str | None = None,
             conn: supply_db.SupplyConnection | None = None) -> list[LoadRecord]:
    """Loads currently recorded as failed - the queue a person drains.

    Never retried automatically (Keith, 2026-09-24): the call is theirs,
    and it is one of two things - reject that supply, or fix a genuine
    bug and reprocess. The second is worth naming because it works
    without any special handling: the FILE is unchanged and OUR ability
    to read it changed, and deliveries are immutable on disk, so a
    reprocess re-reads the same bytes.
    """
    return sorted((e for e in latest_by_table(trial, conn).values() if not e.loaded),
                  key=lambda e: (e.delivery, e.dataset_id))


def delivery_is_processed(delivery: str, expected: set[str] | frozenset[str],
                          conn: supply_db.SupplyConnection | None = None) -> bool:
    """Criterion 16: processed only where EVERY file attributed to a
    dataset has a load record.

    `expected` is the set of physical tables that delivery should have
    produced. A delivery missing one is partial, however many it has -
    which is the case deriving completeness from the catalogue gets
    wrong.

    BOUNDED BY THIS DELIVERY rather than by the whole log, which the
    file-tree version could not be: it read every record to find the
    few belonging here. That is REQ-PIPE-089 criterion 19's cost bound
    falling out of the move rather than needing its own mechanism.
    """
    with _db(conn) as db:
        have = {row[0] for row in db.execute(
            f"SELECT DISTINCT ON (physical) physical FROM {_TABLE} "
            f"WHERE delivery = ? AND {_REAL_ONLY} ORDER BY physical, id DESC",
            [delivery]).fetchall()}
    return bool(expected) and set(expected) <= have
