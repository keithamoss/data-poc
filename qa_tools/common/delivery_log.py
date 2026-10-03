"""One record per delivery, written once at recognition (REQ-PIPE-069,
moved into the database by REQ-PIPE-089 criteria 16 and 22).

WHAT ARRIVED, AND WHAT WE THOUGHT IT WAS. Nothing else.

IT USED TO BE A COMMITTED FILE, and the argument for that was explicit:
"the record of an arrival has to outlive the warehouse that held it and
be readable without one". Keith gave that up deliberately on
2026-09-26, and the reasoning is worth keeping rather than rediscovering
as a regret. Permanence readable with no infrastructure is real and it
is what `dashboard/snapshots/*.html.gz` has always been for - committed,
self-contained, openable in ten years with nothing but a browser. The
delivery log was never the mechanism for that; it was a second copy
that happened to be durable, and the repository holds configuration
rather than state.

RECOGNITION HAPPENS BEFORE LOADING, and that ordering was got wrong once
already: a file written at recognition cannot carry load outcomes,
because none exist yet. So there are two files at two moments and
neither is ever rewritten - this one holds RECOGNITION facts, and
REQ-PIPE-060's processing log holds LOAD facts. Attribution ("this file
is cp_clients") is a recognition fact, decided by a pattern match before
any load is attempted. The physical table it became
("staging.cp_clients__run_003") is a load fact and belongs over there.

Two reasons attribution stays here beyond that. NOT EVERYTHING
ATTRIBUTED REACHES A LOAD - a file two datasets both claim is held and
attributed to neither, an unloadable file gets no table at all - so a
supply recognised but never loaded would otherwise have no record of
what we thought it was. And REQ-PIPE-058's collision gate wants PAIRS of
filename and dataset: keeping both here makes that one read rather than
a join across two logs.

EVERY FILE BY THE NAME IT ARRIVED UNDER, not every table (Keith,
2026-09-24). The drafted wording said "every table it carried", which
fails twice. Attribution reads a file's NAME, not a logical table name,
so the gate needs names. And a JUNK FILE - a Word document, a PDF,
somebody's test PNG - is not a table and has no dataset, so it would
never have been recorded at all. That second half is the sharper one:
REQ-PIPE-057 requires every artefact we declined to act on be recorded
"alongside the delivery it came in, so that a supplier changing their
extract is visible rather than silent", and THIS FILE is what
"alongside the delivery" means. Without it the warning fires once at
recognition and the durable record loses it, so a supplier drifting
over time is invisible unless somebody happened to be watching that
run.

PRIVACY GOT BETTER, and this is the one place to say so concretely.
This paragraph used to open "this repo is public, so a recorded
filename becomes a published string", and it went on to accept, with
eyes open, that a stray `notes_for_jenny_re_case_4471.docx` - exactly
the kind of file that lands in a delivery by accident - would be
committed to a public remote with no removal path, because git cannot
forget. Keith accepted that knowingly on 2026-09-24 and declined
redaction.

It is no longer accepted, because it is no longer true. A filename
recorded here reaches a database nobody outside the deployment can
read, and a row can be deleted. Contents are still never read and
never recorded. The real-deployment judgement should still be made on
real-deployment terms rather than inherited from this PoC - but the
half of it with no removal path is gone.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path

from qa_tools.common import holds, qa_store, supply_db

ROOT = Path(__file__).resolve().parent.parent.parent


class DeliveryLogError(Exception):
    """Something that would corrupt the record rather than merely fail
    to write it."""


@contextmanager
def _db(conn: supply_db.SupplyConnection | None):
    """Reuse the caller's connection, or open one for the call."""
    if conn is not None:
        yield conn
        return
    with supply_db.connect(label="mothman:delivery-log") as opened:
        qa_store.ensure_schema(opened)
        yield opened


def record(delivery, recognition,
           conn: supply_db.SupplyConnection | None = None) -> dict | None:
    """Commit what this delivery was, once.

    WRITTEN ONCE AND NEVER REWRITTEN (criterion 1). A delivery already
    logged is left exactly as it was: what a later run would write is
    the same recognition of the same files, and a record that can be
    rewritten is one nobody can trust to be what was seen at the time.
    A delivery spanning collections is recognised by both orchestrators,
    so the second call being a no-op is the ordinary case rather than a
    guard against a bug.

    WRITE-ONCE BY DELIVERY NAME, which the primary key now enforces
    rather than a pre-read. The file version had to glob for an
    existing record under any filename, because a re-issued receipt
    sequence produced a different filename for the same delivery and
    wrote a second record; a primary key on the name cannot.

    Returns the record written, or None where one already existed.
    """
    attributed = {name: dataset_id
                  for dataset_id, names in recognition.by_dataset.items()
                  for name in names}
    contested = {name: list(claimants)
                 for name, claimants in recognition.contested.items()}

    payload = {
        "delivery": delivery.name,
        # THE OFFSET IS PRESERVED (criterion 5). asset_time already
        # refuses a naive instant, and isoformat() carries the offset
        # it was recorded with - normalising to UTC would throw away
        # which clock the receiving side was on, which is the whole
        # point of REQ-PIPE-048. The column beside it holds the same
        # moment as an instant, for ordering.
        "received_at": delivery.received_at.isoformat(),
        # AND WHICH CLOCK GAVE IT (REQ-PIPE-105 criterion 4). Carried
        # through from the receipt rather than re-derived, because the only
        # thing that knows is whatever wrote the receipt.
        "received_from": delivery.received_from,
        "collections": list(recognition.collections),
        "files": [
            {"filename": name,
             "dataset_id": attributed.get(name),
             # A file two datasets both claim is attributed to NEITHER,
             # and saying which two is the difference between a record
             # somebody can act on and one that just says "no".
             "contested_by": contested.get(name)}
            for name in sorted(delivery.files)
        ],
        # HELD SUPPLIES (REQ-PIPE-059 criterion 4). Derivable from
        # `files` - two entries carrying one dataset_id - and stated
        # anyway, because the question a person opens this with is
        # "what was held and what could it not choose between", and
        # making them compute it from a file list is how a queue stops
        # being drained.
        "contested": [{"dataset_id": h.dataset_id, "files": list(h.files)}
                 for h in holds.holds_in(recognition)],
        # Recorded, never read. A receipt lookalike or a supplier's own
        # manifest is excluded from `files` on purpose, so this is the
        # only place their presence survives.
        "anomalies": list(delivery.anomalies),
    }

    with _db(conn) as db:
        written = db.execute(
            f'INSERT INTO "{qa_store.SCHEMA}".delivery '
            "(name, received_at, received_instant, received_from, collections, contested, "
            "anomalies) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (name) DO NOTHING RETURNING name",
            [payload["delivery"], payload["received_at"], delivery.received_at,
             payload["received_from"],
             json.dumps(payload["collections"]), json.dumps(payload["contested"]),
             json.dumps(payload["anomalies"])]).fetchall()
        if not written:
            return None
        for entry in payload["files"]:
            db.execute(
                f'INSERT INTO "{qa_store.SCHEMA}".delivery_file '
                "(delivery, filename, dataset_id, contested_by) VALUES (?, ?, ?, ?)",
                [payload["delivery"], entry["filename"], entry["dataset_id"],
                 json.dumps(entry["contested_by"]) if entry["contested_by"] else None])
    return payload


def prune(present: set[str] | frozenset[str],
          conn: supply_db.SupplyConnection | None = None) -> list[str]:
    """Remove records for deliveries that no longer exist.

    Criterion 6 asks that the log never describe a history that no
    longer exists, and says so as "regenerate from scratch, under the
    same delete-and-regenerate rule". THIS PRUNES INSTEAD OF WIPING,
    and the narrowing is deliberate rather than a shortcut.

    A wipe is destructive between the delete and the rewrite, and that
    is not theoretical: the first version cleared the whole log at the
    top of `mothman pipeline run`, and the test suite - which invokes
    that command with the real work stubbed out - deleted sixty
    records on the next gate run. Nothing rewrote them, because the
    thing that would have was the part being stubbed.

    Pruning reaches the same end state for every case that can actually
    arise. Records are write-once by criterion 1, so a record for a
    delivery still present is BY DEFINITION what a regeneration would
    write again; the only records a wipe removes and a rebuild does not
    restore are exactly the ones for deliveries that are gone, which is
    what this removes.

    THE UNREADABLE CASE IS GONE WITH THE FILES. The version this
    replaces also removed records it could not parse, because a corrupt
    JSON file is both unusable and unattributable to a delivery. A row
    is either committed or it is not.

    Returns the names removed, because a silent delete of durable
    records is the wrong shape even when it is correct.
    """
    with _db(conn) as db:
        gone = [row[0] for row in db.execute(
            f'DELETE FROM "{qa_store.SCHEMA}".delivery WHERE NOT (name = ANY(?)) '
            "RETURNING name", [list(present)]).fetchall()]
    return sorted(gone)


def records(conn: supply_db.SupplyConnection | None = None) -> list[dict]:
    """Every delivery record, oldest receipt first.

    Returns the same dicts the committed files held, so every reader of
    this corpus - REQ-PIPE-058's collision gate, the arrival history,
    the outstanding queue - is unchanged by the move.

    A malformed one used to RAISE rather than be skipped, because this
    is a gate's corpus and a gate that quietly ignores what it cannot
    parse passes for the wrong reason. There is nothing left to
    malform.
    """
    with _db(conn) as db:
        deliveries = db.execute(
            f'SELECT name, received_at, collections, contested, anomalies, received_from '
            f'FROM "{qa_store.SCHEMA}".delivery ORDER BY received_instant, name'
        ).fetchall()
        files: dict[str, list[dict]] = {}
        for delivery, filename, dataset_id, contested in db.execute(
                f'SELECT delivery, filename, dataset_id, contested_by '
                f'FROM "{qa_store.SCHEMA}".delivery_file ORDER BY delivery, filename'
        ).fetchall():
            files.setdefault(delivery, []).append(
                {"filename": filename, "dataset_id": dataset_id,
                 "contested_by": contested})
    return [{"delivery": name, "received_at": received_at,
             "received_from": received_from,
             "collections": collections, "files": files.get(name, []),
             "contested": contested, "anomalies": anomalies}
            for name, received_at, collections, contested, anomalies, received_from
            in deliveries]


def records_carrying(dataset_id: str, limit: int | None = None,
                     conn: supply_db.SupplyConnection | None = None) -> list[dict]:
    """The delivery records that carried one dataset, NEWEST FIRST.

    THE NON-FUNCTIONAL CONSTRAINT, and it changed shape with the move.
    REQ-PIPE-034 requires that "when did this dataset last arrive" cost
    deliveries since IT last supplied rather than total history. Over
    files that was a reverse-sorted glob with an early exit, measured
    by counting opens. Over rows, an early exit out of a list the
    database has already materialised saves parsing and nothing else -
    so the bound has to move into the query, which is `limit` plus the
    index on `delivery_file (dataset_id)`.

    That is strictly better than the bound it replaces: the old one was
    "deliveries since this dataset last supplied", and this one does
    not depend on how long ago that was.
    """
    sql_text = (f'SELECT d.name, d.received_at, d.collections, d.contested, d.anomalies, '
                f'd.received_from '
                f'FROM "{qa_store.SCHEMA}".delivery d '
                f'WHERE EXISTS (SELECT 1 FROM "{qa_store.SCHEMA}".delivery_file f '
                f'              WHERE f.delivery = d.name AND f.dataset_id = ?) '
                "ORDER BY d.received_instant DESC, d.name DESC")
    params: list = [dataset_id]
    if limit is not None:
        sql_text += " LIMIT ?"
        params.append(limit)
    with _db(conn) as db:
        found = db.execute(sql_text, params).fetchall()
        if not found:
            return []
        names = [row[0] for row in found]
        files: dict[str, list[dict]] = {}
        for delivery, filename, ds_id, contested in db.execute(
                f'SELECT delivery, filename, dataset_id, contested_by '
                f'FROM "{qa_store.SCHEMA}".delivery_file WHERE delivery = ANY(?) '
                "ORDER BY delivery, filename", [names]).fetchall():
            files.setdefault(delivery, []).append(
                {"filename": filename, "dataset_id": ds_id, "contested_by": contested})
    return [{"delivery": name, "received_at": received_at, "collections": collections,
             "received_from": received_from,
             "files": files.get(name, []), "contested": contested, "anomalies": anomalies}
            for name, received_at, collections, contested, anomalies, received_from in found]


def sql() -> str:
    """A SELECT over the delivery record itself (criterion 4).

    It used to hand back a DuckDB `read_json_auto` over the committed
    files, so the log could be joined against the staging and period
    schemas with nothing synced. The record is IN the warehouse now, so
    the join needs no special reader at all - which is what that
    criterion wanted and the file version could only approximate.

    Still returns SQL rather than running it, because running it would
    mean choosing a connection, and the callers that want this want to
    hand it to a tool.
    """
    return (f'SELECT d.name AS delivery, d.received_at, d.collections, '
            f'd.anomalies, f.filename, f.dataset_id, f.contested_by '
            f'FROM "{qa_store.SCHEMA}".delivery d '
            f'LEFT JOIN "{qa_store.SCHEMA}".delivery_file f ON f.delivery = d.name')


def record_all() -> None:
    """Record every delivery on disk, each with what recognition made of
    it - the one loop both orchestrators used to carry a copy of, and
    what a bootstrap runs ONCE before running both collections side by
    side (REQ-TEST-116)."""
    from qa_tools.common import arrivals, delivery

    for d in delivery.list_deliveries():
        record(d, arrivals.recognise(d))
