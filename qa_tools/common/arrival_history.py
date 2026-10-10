"""Each dataset's own arrival history (REQ-PIPE-034).

A DATASET'S TIMELINE IS ITS OWN. A file one agency resent on Tuesday
belongs on that table's timeline, not folded into a delivery of five
other tables that did not change - and the other five must not gain a
phantom arrival because they happened to share a directory with it.

DERIVED, NEVER STORED. Both questions this answers come from the
committed append-only records: the delivery log for what arrived, the
processing log for whether it loaded. Nothing here keeps a pointer to
"the latest", because a pointer is state that can drift from what is
actually true, whereas a maximum over an append-only log cannot.

WHY IT DOES NOT READ THE WAREHOUSE, which is forced rather than
preferable. A supply that could not be loaded at all has no table
anywhere - deliberately, since there is no point creating an empty one
when the arrival is already recorded. Derive arrival from the catalogue
and a supplier sending garbage on Tuesday becomes invisible: the
timeline would show Monday. And the dashboard build may never touch
data/, so it could not read the catalogue even if that were safe.

WHAT IS NOT HERE, and why it is absent rather than approximated:
MOST RECENTLY PROMOTED. The requirement asks for it, and the
derivation signed off with it - "the newest table for the dataset in
the newest period schema holding one" - is a WAREHOUSE CATALOGUE read,
which the paragraph above forbids for the arrived side and forbids
here for exactly the same reason. That defect was found after sign-off
and recorded on the requirement itself. Its real source is the
committed append-only decision log, which does not exist until batch
4, so this module answers the arrived question honestly and leaves the
promoted one to the sprint that can answer it.

COST. Answering "when did this dataset last arrive" must not walk
every arrival ever received. It does not: delivery-log filenames carry
the receipt instant and sequence, so a directory listing IS receipt
order, and the search runs newest-first and stops at the first
delivery that carried the dataset - bounded by deliveries since that
dataset last supplied rather than by total history.
"""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from qa_tools.common import delivery_log, load_log


@dataclass(frozen=True)
class Arrival:
    """One arrival of ONE dataset.

    `supply_id` is this dataset's own identifier for it (criterion 1)
    and `delivery` is the transport it came in (criterion 8). Both are
    carried because neither answers the other's question: without the
    supply id a dataset has no timeline of its own, and without the
    delivery "the agency sent all six on Tuesday" cannot be
    reconstructed later, so a real whole-collection delivery becomes
    indistinguishable from six coincidental arrivals.
    """

    dataset_id: str
    supply_id: str
    received_at: str
    sequence: int
    delivery: str
    filename: str

    @property
    def sort_key(self) -> tuple[str, int]:
        return (self.received_at, self.sequence)


def _supply_id(dataset_id: str, record: dict, ordinal: int) -> str:
    """This dataset's own name for one arrival.

    OURS, from our own receipt - never the supplier's filename, which
    is theirs and may repeat, and never the delivery name, which is
    shared by every dataset in it and so cannot identify one.
    """
    base = f"{dataset_id}@{Path(_stem(record)).name}"
    return base if ordinal <= 1 else f"{base}#{ordinal}"


def _stem(record: dict) -> str:
    return "".join(ch for ch in record.get("received_at", "") if ch.isdigit())[:20] or "0"


def _arrivals_in(record: dict, dataset_id: str | None,
                 filed: dict[tuple[str, str], str] | None = None) -> list[Arrival]:
    """This record's arrivals, each labelled with ITS OWN FILE's receipt
    and the supply id ITS FILING carries (REQ-PIPE-144 criterion 37,
    fixing post-build-review #76).

    It used to label every arrival with the DELIVERY's receipt and build
    a supply id from that - so for the ~20% of multi-file deliveries
    whose files land up to ten minutes apart, `mothman supply history`
    showed the wrong time and a supply id matching no filing. The id now
    comes from the filing (through qa.supply_receipt); only an arrival
    nothing filed falls back to deriving one, from its own file's receipt.
    """
    out: list[Arrival] = []
    counts: dict[str, int] = {}
    filed = filed or {}
    for entry in record.get("files") or []:
        found = entry.get("dataset_id")
        # A file two datasets both claim is attributed to NEITHER, so it
        # is nobody's arrival - which is the same refusal recognition
        # already makes, not a second rule.
        if not found or (dataset_id is not None and found != dataset_id):
            continue
        counts[found] = counts.get(found, 0) + 1
        own = {"received_at": entry.get("received_at") or record.get("received_at", "")}
        out.append(Arrival(
            dataset_id=found,
            supply_id=(filed.get((record.get("delivery", ""), found))
                       or _supply_id(found, own, counts[found])),
            received_at=own["received_at"],
            sequence=int(entry.get("receipt_sequence") or 0),
            delivery=record.get("delivery", ""),
            filename=entry.get("filename", "")))
    return out


def _load(conn=None) -> Iterator[dict]:
    """Every delivery record, NEWEST FIRST.

    A GENERATOR, and that is a non-functional constraint rather than a
    style choice. Built as a list first, and it read every record
    before returning one - so last_arrived() "stopped at the first hit"
    over a list that had already cost the full walk. Measured: 60 of 60
    records opened to answer a question that needs one.

    IT USED TO BE A REVERSE-SORTED GLOB, and the early exit was real
    because opening a file is what cost something. Rows come back from
    one query now, so the exit saves parsing rather than I/O - the
    property the test asserts still holds, and the honest way to make
    this cheap at thirty datasets over years is a WHERE clause, which
    is what `last_arrived` below should grow when the walk starts to
    show. Recorded rather than done, because nothing measures as slow
    yet and a guess is how an index that serves nothing gets added.

    The `_sequence` this used to parse out of each filename is gone: it
    was assigned here and read nowhere, and there are no filenames.
    """
    yield from reversed(delivery_log.records(conn))

def arrivals_of(dataset_id: str, conn=None) -> list[Arrival]:
    """One dataset's whole arrival history, oldest first.

    Presented WITHOUT reference to any other dataset (criterion 9):
    nothing in the returned records names another dataset, and a
    delivery that carried six tables contributes exactly one arrival
    here.
    """
    found: list[Arrival] = []
    records = delivery_log.records_carrying(dataset_id, conn=conn)
    filed = delivery_log.supply_ids([r["delivery"] for r in records], conn=conn)
    for record in records:
        found.extend(_arrivals_in(record, dataset_id, filed))
    return sorted(found, key=lambda a: a.sort_key)


def last_arrived(dataset_id: str, conn=None) -> Arrival | None:
    """This dataset's most recent arrival, INCLUDING one that could not
    be loaded (criterion 2).

    ONE DELIVERY IS READ, not the history up to it. The constraint
    used to be met by walking backwards and stopping at the first hit;
    it is now a WHERE on this dataset with a LIMIT, which does not
    depend on how long ago the dataset last supplied. See
    delivery_log.records_carrying() for why the early exit stopped
    being worth anything once the records were rows.
    """
    for record in delivery_log.records_carrying(dataset_id, limit=1, conn=conn):
        found = _arrivals_in(record, dataset_id,
                             delivery_log.supply_ids([record["delivery"]], conn=conn))
        if found:
            return max(found, key=lambda a: a.sort_key)
    return None


def last_promoted(dataset_id: str, conn=None) -> None:
    """Always None, and deliberately so - see this module's docstring.

    A function that returns None is here rather than nothing at all
    because the question is real and will be asked; answering it with
    the most recent ARRIVAL would be the exact conflation the
    requirement splits apart, and would read fine right up until a
    supplier sends a broken file.
    """
    return None


def load_outcome(supply_id: str, dataset_id: str, delivery: str) -> str | None:
    """Whether this dataset's supply from this delivery loaded.

    None where nothing was recorded - which is what an interrupted load
    leaves, and is not the same as a failure.
    """
    for record in load_log.records():
        if record.delivery == delivery and record.dataset_id == dataset_id:
            return record.outcome
    return None


def delivery_companions(delivery: str, conn=None) -> tuple[str, ...]:
    """Every dataset that arrived in one delivery (criterion 8).

    The counterpart to the per-dataset view: it is what makes "the
    agency sent all six on Tuesday" answerable at all, and it is a
    question about the DELIVERY rather than about any one dataset, so
    it does not belong on a dataset's own timeline.
    """
    for record in _load(conn):
        if record.get("delivery") == delivery:
            return tuple(sorted({a.dataset_id for a in _arrivals_in(record, None)}))
    return ()
