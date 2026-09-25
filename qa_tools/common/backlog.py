"""Where processing got to, and what is still owed (REQ-PIPE-061).

ONE MARKER FOR EVERYTHING, not one per collection. It follows from
REQ-PIPE-057 allowing a delivery to span collections: a per-collection
marker would have to place such a delivery twice and could place it
differently each time, which is the non-determinism this whole
requirement exists to remove. What stays per-collection is the RUN -
one arrival spanning two collections produces two runs, because a run
is the per-collection QA unit. Only the ORDER, and the marker with it,
is global.

A POSITION IS (RECEIPT INSTANT, SEQUENCE), which is the same pair the
ordering itself sorts on. Anything else would be a second ordering
concept to keep in step with the first.

WHY A MARKER AT ALL, rather than deriving what is outstanding from the
load records. Deriving is correct and does not survive the scale this
is a PoC for: it asks "is this processed" of every arrival ever
received, on every run, and a daily feed over years is exactly the
shape that breaks. The requirement's own non-functional constraint
says replay cost must be bounded by the arrivals not yet processed
rather than by total history, and a marker is what bounds it.

IT ADVANCES ONLY PAST WHAT IS FULLY PROCESSED (criterion 7), and that
is the half that makes an interruption safe. A marker advanced
optimistically - past an arrival that was reached but not finished -
turns a crash into a silently skipped supply, which is the same
failure REQ-PIPE-060's load records exist to prevent one layer down.
Advancing late costs a re-process, and re-processing is idempotent.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from qa_tools.common import asset_time

ROOT = Path(__file__).resolve().parent.parent.parent

#: Inside the processing log's tree but in a SUBDIRECTORY of it, so
#: load_log.records()'s own non-recursive glob("*.json") cannot pick
#: the marker up and read it as a load outcome. It belongs near the
#: load records - it is a fact about processing, committed for the same
#: reason - without being one of them.
MARKER_PATH = ROOT / "processing_log" / "marker" / "position.json"


@dataclass(frozen=True, order=True)
class Position:
    """How far processing has got, as a sortable pair.

    `received_at` is kept as the ISO string it was recorded as rather
    than a datetime, because this is written to and read from committed
    JSON and a round-trip through a parser is a chance to change it.
    Comparison is still correct: every instant this project records is
    written by asset_time.isoformat(), so the strings sort the way the
    instants do.
    """

    received_at: str
    sequence: int

    @classmethod
    def of(cls, arrival) -> "Position":
        """The position of one arrival or delivery - anything carrying
        a receipt instant and a sequence.

        A MISSING SEQUENCE RAISES. The first version of this defaulted
        it to zero, and the bug that hid behind that default is the
        reason the rule is worth stating: `Arrival` did not carry a
        sequence at all, so EVERY arrival's position had sequence 0 and
        the tiebreak was silently absent at the one layer that uses it.
        Nothing failed. A permissive default turned a missing field
        into a wrong answer, which is the trade this repo refuses
        everywhere else.
        """
        if not hasattr(arrival, "sequence"):
            raise AttributeError(
                f"{type(arrival).__name__} carries no `sequence`, so it cannot be placed in "
                f"the processing order. Ordering needs the receipt's own write order, not just "
                f"its instant - see REQ-PIPE-061 criterion 3.")
        instant = arrival.received_at
        return cls(received_at=instant if isinstance(instant, str)
                    else asset_time.isoformat(instant),
                    sequence=int(arrival.sequence))


def read_marker(path: Path | None = None) -> Position | None:
    """How far a previous run got, or None where none ever has.

    None means START FROM THE BEGINNING, which is the correct reading
    for a first run and for a checkout that has never processed
    anything. An unreadable marker means the same thing: it is better
    to re-process an arrival that was already done - idempotent by
    REQ-PIPE-060's design - than to skip one because a file would not
    parse.
    """
    marker = Path(path or MARKER_PATH)
    if not marker.is_file():
        return None
    try:
        record = json.loads(marker.read_text())
        return Position(received_at=str(record["received_at"]),
                         sequence=int(record["sequence"]))
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def advance(position: Position, path: Path | None = None) -> Path:
    """Record that everything up to and including `position` is done.

    NEVER MOVES BACKWARDS. A run draining a backlog advances as it
    goes, and a later run processing an OLDER arrival - a late receipt,
    a re-process - must not undo that. Called with an earlier position
    this is a no-op rather than an error, because processing an arrival
    twice is legitimate and only the high-water mark is a claim.
    """
    marker = Path(path or MARKER_PATH)
    current = read_marker(marker)
    if current is not None and position <= current:
        return marker
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps(
        {"received_at": position.received_at, "sequence": position.sequence}, indent=2) + "\n")
    return marker


def pending(arrivals, marker: Position | None) -> list:
    """The arrivals still owed, in the order they must be processed.

    EVERYTHING AFTER THE MARKER, not just the one that triggered the
    run (criterion 6). The reason is worth stating because the obvious
    implementation is the wrong one: a run that handles only its
    trigger loses whatever arrived while it was busy, and GitHub holds
    only ONE pending run per concurrency group, so three rapid triggers
    silently lose the middle one. Draining needs no queueing guarantee
    from any platform.

    `arrivals` is assumed already in receipt order - survey() puts it
    there, and re-sorting here would be a second copy of the ordering
    rule to keep correct.
    """
    if marker is None:
        return list(arrivals)
    return [a for a in arrivals if Position.of(a) > marker]


def advance_through(arrivals, is_processed, path: Path | None = None) -> Position | None:
    """Advance the marker over the arrivals that are genuinely done.

    CONTIGUOUS FROM THE FRONT, and stopping at the first one that is
    not (criterion 7). A marker is a claim that EVERYTHING up to it is
    finished, so it cannot skip a gap: if the second of four arrivals
    failed and the other three succeeded, the marker stays before the
    second and the next run is owed all three again. Re-processing is
    idempotent and costs a little work; jumping the gap loses a supply
    and costs it silently.

    `is_processed` is supplied by the caller rather than computed here,
    because what "processed" means is the caller's business - for the
    orchestrators it is REQ-PIPE-060's rule, every file attributed to a
    dataset having a load record - and this module has no business
    knowing about staging.

    Returns the position the marker now sits at, or None where nothing
    was processed and it did not move.
    """
    furthest = None
    for arrival in arrivals:
        if not is_processed(arrival):
            break
        furthest = Position.of(arrival)
    if furthest is None:
        return read_marker(path)
    advance(furthest, path)
    return read_marker(path)


def advance_past_staged(path: Path | None = None) -> Position | None:
    """Move the marker over every delivery that is genuinely staged.

    WALKS THE GLOBAL DELIVERY LIST, not one collection's arrivals, and
    that is the whole correctness of it. The first version took a
    collection's own arrivals and advanced contiguously over those -
    which skips straight past any delivery belonging only to the OTHER
    collection and sitting between them. Measured on the real data:
    Birth Registrations' newest arrival is seven weeks past Child
    Protection's, so whichever orchestrator ran first would push the
    shared marker past all eighteen Child Protection arrivals. The
    marker would then be a committed record making a claim that was
    not true, which is worse than a slow one.

    Both orchestrators call this and both reach the same answer,
    because the input is the same global list either way. advance()
    never moves backwards, so the second call is a no-op rather than a
    correction.

    PROCESSED MEANS REQ-PIPE-060'S RULE, applied to the WHOLE delivery:
    every file it attributed to any dataset has a load record. A
    delivery spanning collections is therefore not processed until both
    collections have staged their half, which is exactly right - the
    marker claims everything before it is done, and half a delivery is
    not done.
    """
    from qa_tools.common import arrivals as arrivals_mod
    from qa_tools.common import delivery as delivery_mod
    from qa_tools.common import load_log, supply_db

    def is_processed(d) -> bool:
        recognition = arrivals_mod.recognise(d)
        expected = set(supply_db.expected_tables(recognition, d.received_at).values())
        if not expected:
            # Nothing was attributed to any dataset, so there is nothing
            # to stage and nothing to wait for. Treated as processed:
            # leaving it unprocessed would block the marker for ever on
            # a delivery that will never produce a load record.
            return True
        return load_log.delivery_is_processed(d.name, expected)

    # Already in receipt order, and globally - survey() puts it there.
    return advance_through(delivery_mod.survey().received, is_processed, path)
