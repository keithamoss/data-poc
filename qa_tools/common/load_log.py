"""One committed record per staged table, written only after that
table's load is durable (REQ-PIPE-060, criteria 13-20).

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

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

#: Beside the delivery log and outside the per-dataset QA results
#: (criterion 20). A load outcome is not a QA result and a delivery
#: spans datasets, so qa_results/ - keyed by agency and collection - is
#: the wrong tree for both.
PROCESSING_LOG_DIR = ROOT / "processing_log"

#: Redirects the whole log, the same way MOTHMAN_SUPPLY_DB redirects
#: the database - for a real run against a checkout that is not this
#: one. Most callers several frames down pass no `log_dir`, so without
#: something like this the only way to move the log is to edit code.
PROCESSING_LOG_ENV = "MOTHMAN_PROCESSING_LOG"


def log_directory(log_dir: Path | None = None) -> Path:
    """Where records are read and written: the explicit argument, then
    the environment, then the committed tree."""
    if log_dir is not None:
        return Path(log_dir)
    configured = os.environ.get(PROCESSING_LOG_ENV)
    return Path(configured) if configured else PROCESSING_LOG_DIR

LOADED = "loaded"
FAILED = "failed"

_UNSAFE = re.compile(r"[^0-9A-Za-z._-]+")


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


def _path(physical: str, recorded_at: str, log_dir: Path | None = None) -> Path:
    directory = log_directory(log_dir)
    stamp = _UNSAFE.sub("", recorded_at)
    return directory / f"{_UNSAFE.sub('_', physical)}--{stamp}.json"


def record(delivery: str, dataset_id: str, physical: str, outcome: str,
            recorded_at: str, reason: str | None = None,
            row_count: int | None = None,
            log_dir: Path | None = None) -> Path:
    """Write one load outcome.

    CALL THIS ONLY ONCE THE LOAD IS DURABLE. Nothing here can check
    that for you - the ordering is the caller's to get right, which is
    why it has a criterion of its own rather than being left as an
    implementation note.
    """
    if outcome not in (LOADED, FAILED):
        raise ValueError(f"a load outcome is {LOADED!r} or {FAILED!r}, not {outcome!r}")
    path = _path(physical, recorded_at, log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "delivery": delivery,
        "dataset_id": dataset_id,
        "physical": physical,
        "outcome": outcome,
        "recorded_at": recorded_at,
        "reason": reason,
        "row_count": row_count,
    }, indent=2) + "\n")
    return path


def record_load(delivery: str, dataset_id: str, physical: str, outcome: str,
                 recorded_at: str, reason: str | None = None,
                 row_count: int | None = None,
                 log_dir: Path | None = None) -> Path | None:
    """`record()`, but silent where the latest record already says
    exactly this.

    WHY THIS EXISTS, found by running it rather than by reading it: a
    re-run stages every delivery again, and without this each one wrote
    a fresh record for an unchanged table - 42 new committed files for
    a run in which nothing whatsoever changed. Over a PoC that is
    clutter; over the years of history this tree is FOR, at ~30
    datasets, it is a committed directory growing without bound and
    carrying no signal at all.

    IT DOES NOT WEAKEN CRITERION 19, which is the thing to check before
    reaching for a deduplicate anywhere near an append-only log. That
    criterion is about a CHANGE of outcome - a failed load reprocessed
    into a loaded one - and a change is exactly what this still writes.
    What it stops is a repetition, and the failed record it was meant
    to preserve is preserved by being the latest one until something
    different happens to that table.

    Returns the path written, or None where nothing needed writing.
    """
    latest = latest_by_table(log_dir).get(physical)
    if (latest is not None and latest.outcome == outcome
            and latest.reason == reason and latest.row_count == row_count
            and latest.delivery == delivery and latest.dataset_id == dataset_id):
        return None
    return record(delivery, dataset_id, physical, outcome, recorded_at,
                   reason=reason, row_count=row_count, log_dir=log_dir)


def records(log_dir: Path | None = None) -> list[LoadRecord]:
    """Every load record ever written, oldest first."""
    directory = log_directory(log_dir)
    if not directory.is_dir():
        return []
    out = []
    for path in sorted(directory.glob("*.json")):
        try:
            raw = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            # Unreadable means UNTRUSTED, which is the safe reading
            # everywhere here: a table whose record cannot be read is a
            # table with no record, so it is not visible to a check.
            continue
        out.append(LoadRecord(
            delivery=raw.get("delivery", ""), dataset_id=raw.get("dataset_id", ""),
            physical=raw.get("physical", ""), outcome=raw.get("outcome", ""),
            recorded_at=raw.get("recorded_at", ""), reason=raw.get("reason"),
            row_count=raw.get("row_count")))
    return sorted(out, key=lambda r: r.recorded_at)


def latest_by_table(log_dir: Path | None = None) -> dict[str, LoadRecord]:
    """The current outcome for each staged table.

    LATEST WINS, which is what makes a reprocess work without editing
    history: the failed record stays, and the record written after it
    is the one that counts.
    """
    current: dict[str, LoadRecord] = {}
    for entry in records(log_dir):
        current[entry.physical] = entry
    return current


def loaded_tables(log_dir: Path | None = None) -> frozenset[str]:
    """Physical tables a check may read.

    A table absent from this set is UNLOADED as far as anything
    downstream is concerned, whether it is physically there or not.
    """
    return frozenset(name for name, entry in latest_by_table(log_dir).items()
                      if entry.loaded)


def failures(log_dir: Path | None = None) -> list[LoadRecord]:
    """Loads currently recorded as failed - the queue a person drains.

    Never retried automatically (Keith, 2026-09-24): the call is theirs,
    and it is one of two things - reject that supply, or fix a genuine
    bug and reprocess. The second is worth naming because it works
    without any special handling: the FILE is unchanged and OUR ability
    to read it changed, and deliveries are immutable on disk, so a
    reprocess re-reads the same bytes.
    """
    return sorted((e for e in latest_by_table(log_dir).values() if not e.loaded),
                   key=lambda e: (e.delivery, e.dataset_id))


def delivery_is_processed(delivery: str, expected: set[str] | frozenset[str],
                           log_dir: Path | None = None) -> bool:
    """Criterion 16: processed only where EVERY file attributed to a
    dataset has a load record.

    `expected` is the set of physical tables that delivery should have
    produced. A delivery missing one is partial, however many it has -
    which is the case deriving completeness from the catalogue gets
    wrong.
    """
    have = {name for name, entry in latest_by_table(log_dir).items()
            if entry.delivery == delivery}
    return bool(expected) and set(expected) <= have
