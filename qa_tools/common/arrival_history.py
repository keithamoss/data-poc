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

import json
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


def _arrivals_in(record: dict, dataset_id: str | None) -> list[Arrival]:
    out: list[Arrival] = []
    counts: dict[str, int] = {}
    for entry in record.get("files") or []:
        found = entry.get("dataset_id")
        # A file two datasets both claim is attributed to NEITHER, so it
        # is nobody's arrival - which is the same refusal recognition
        # already makes, not a second rule.
        if not found or (dataset_id is not None and found != dataset_id):
            continue
        counts[found] = counts.get(found, 0) + 1
        out.append(Arrival(
            dataset_id=found,
            supply_id=_supply_id(found, record, counts[found]),
            received_at=record.get("received_at", ""),
            sequence=_sequence_of(record),
            delivery=record.get("delivery", ""),
            filename=entry.get("filename", "")))
    return out


def _sequence_of(record: dict) -> int:
    """The receipt's write order, recovered from the record's own path.

    The delivery log does not carry the sequence in its BODY - it was
    written before REQ-PIPE-061 existed and those files are write-once
    - so it is read from the filename, which does carry it and is
    generated from the same receipt.
    """
    return int(record.get("_sequence", 0))


def _load(log_dir: Path | None = None) -> Iterator[dict]:
    """Every committed delivery record, NEWEST FIRST, with its own
    sequence attached from its filename.

    A GENERATOR, and that is the non-functional constraint rather than
    a style choice. Built as a list first, and it read every record
    before returning one - so last_arrived() "stopped at the first hit"
    over a list that had already cost the full walk. Measured: 60 of 60
    records opened to answer a question that needs one. Yielding makes
    the early exit real, which the test asserts by counting reads
    rather than by trusting this paragraph.
    """
    directory = Path(log_dir or delivery_log.DELIVERY_LOG_DIR)
    if not directory.is_dir():
        return
    for path in sorted(directory.glob("*.json"), reverse=True):
        try:
            record = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise delivery_log.DeliveryLogError(
                f"{path} is in the delivery log and cannot be read ({exc}). A dataset's "
                f"arrival history is built from these, so one that cannot be parsed is not "
                f"something to pass over.") from exc
        parts = path.stem.split("--")
        record["_sequence"] = int(parts[1]) if len(parts) > 2 and parts[1].isdigit() else 0
        yield record


def arrivals_of(dataset_id: str, log_dir: Path | None = None) -> list[Arrival]:
    """One dataset's whole arrival history, oldest first.

    Presented WITHOUT reference to any other dataset (criterion 9):
    nothing in the returned records names another dataset, and a
    delivery that carried six tables contributes exactly one arrival
    here.
    """
    found: list[Arrival] = []
    for record in _load(log_dir):
        found.extend(_arrivals_in(record, dataset_id))
    return sorted(found, key=lambda a: a.sort_key)


def last_arrived(dataset_id: str, log_dir: Path | None = None) -> Arrival | None:
    """This dataset's most recent arrival, INCLUDING one that could not
    be loaded (criterion 2).

    Stops at the first delivery carrying the dataset rather than
    reading them all, which is the non-functional constraint made
    mechanical: the listing is already in receipt order, so the first
    hit walking backwards IS the newest.
    """
    for record in _load(log_dir):
        found = _arrivals_in(record, dataset_id)
        if found:
            return max(found, key=lambda a: a.sort_key)
    return None


def last_promoted(dataset_id: str, log_dir: Path | None = None) -> None:
    """Always None, and deliberately so - see this module's docstring.

    A function that returns None is here rather than nothing at all
    because the question is real and will be asked; answering it with
    the most recent ARRIVAL would be the exact conflation the
    requirement splits apart, and would read fine right up until a
    supplier sends a broken file.
    """
    return None


def load_outcome(supply_id: str, dataset_id: str, delivery: str,
                  processing_dir: Path | None = None) -> str | None:
    """Whether this dataset's supply from this delivery loaded.

    None where nothing was recorded - which is what an interrupted load
    leaves, and is not the same as a failure.
    """
    for record in load_log.records(processing_dir):
        if record.delivery == delivery and record.dataset_id == dataset_id:
            return record.outcome
    return None


def delivery_companions(delivery: str, log_dir: Path | None = None) -> tuple[str, ...]:
    """Every dataset that arrived in one delivery (criterion 8).

    The counterpart to the per-dataset view: it is what makes "the
    agency sent all six on Tuesday" answerable at all, and it is a
    question about the DELIVERY rather than about any one dataset, so
    it does not belong on a dataset's own timeline.
    """
    for record in _load(log_dir):
        if record.get("delivery") == delivery:
            return tuple(sorted({a.dataset_id for a in _arrivals_in(record, None)}))
    return ()
