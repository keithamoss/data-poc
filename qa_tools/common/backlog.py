"""What is still owed (REQ-PIPE-061, and REQ-PIPE-089 criteria 18-20).

THE STORED MARKER IS GONE (Keith, 2026-09-27: "let's ditch it and just
derive from load records - that's much easier now it's all going to be
in a database"), and the argument it used to win is worth keeping
because it was a good one right up until the storage changed.

It read: deriving what is outstanding is correct and does not survive
the scale this is a PoC for, because it asks "is this processed" of
every arrival ever received, on every run. Over a FILE TREE that was
true - answering per arrival meant opening the records - and
REQ-PIPE-061's own constraint says replay cost must be bounded by the
arrivals not yet processed rather than by total history.

What changed is that one indexed read of the load outcomes now answers
it for every arrival at once, so the marker buys nothing it did not
buy by being a file. AND DERIVING IS STRICTLY SAFER, which is the part
that decided it: a stored marker can disagree with the load records,
and it fails in the dangerous direction - advanced past an arrival
that was reached but not finished, it turns a crash into a silently
skipped supply. Derived, there is nothing to advance and nothing to
disagree. Same reasoning that made "record the load AFTER it is
durable" the right order one layer down.

IT ALSO BEATS THE MARKER ON ONE CASE. A high-water mark had to stop at
the first unfinished arrival (criterion 7), so one stuck supply made
every later one look owed again. Asking each arrival its own question
has no gap to stop at.

Worth recording because it was found only while removing it: the
marker was WRITE-ONLY. Both orchestrators advanced it after their
fan-out and nothing in the pipeline ever read it back.

A POSITION IS (RECEIPT INSTANT, SEQUENCE), which is the same pair the
ordering itself sorts on. Anything else would be a second ordering
concept to keep in step with the first. That survives the marker's
removal, because ordering is still real: arrivals are processed
oldest receipt first.
"""
from __future__ import annotations

from dataclasses import dataclass

from qa_tools.common import asset_time

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


def unprocessed(arrivals, conn=None) -> list:
    """The arrivals still owed, in the order they must be processed.

    EVERYTHING NOT YET PROCESSED, not just the one that triggered the
    run (criterion 6, and REQ-PIPE-089 criterion 19). The reason is
    worth stating because the obvious implementation is the wrong one:
    a run that handles only its trigger loses whatever arrived while
    it was busy, and GitHub holds only ONE pending run per concurrency
    group, so three rapid triggers silently lose the middle one.
    Draining needs no queueing guarantee from any platform.

    PROCESSED MEANS CHECKED AND GATED (REQ-PIPE-151 criterion 18,
    amending REQ-PIPE-061 criterion 6's rule here). It used to mean
    LOADED - every attributed file had a loaded record - which counted an
    arrival done the moment its rows were in staging, before any check
    had run or the gate had looked at it. A file's staged name is its
    arrival's run id, so each file is processed once that run COMPLETED
    and the gate RAN on its supply (or an open hold stands for it), read
    from processing_pass.recorded() - the pass's own definition, so there
    is one answer, not two.

    ONE READ, whatever the number of arrivals - the bound the retired
    marker used to provide (REQ-PIPE-089 criterion 19).

    `arrivals` is assumed already in receipt order - survey() puts it
    there, and re-sorting here would be a second copy of the ordering
    rule to keep correct.
    """
    from qa_tools.common import processing_pass, supply_db

    if conn is None:
        with supply_db.connect(read_only=True, label="mothman:backlog") as opened:
            rec = processing_pass.recorded(opened)
    else:
        rec = processing_pass.recorded(conn)

    owed = []
    for arrival in arrivals:
        expected = set(getattr(arrival, "files", ()) or ())
        if not expected:
            # Nothing was attributed to any dataset - a covering note
            # and nothing else. Nothing will ever be checked, so treating
            # it as owed would block the queue permanently on a delivery
            # that can never satisfy it.
            continue
        if not all(_file_processed(physical, rec) for physical in expected):
            owed.append(arrival)
    return owed


def _file_processed(physical: str, rec) -> bool:
    """One staged file's arrival: run completed, and its supply gated or held."""
    from qa_tools.common import hierarchy, supply_db

    parts = supply_db.split_staged(physical)
    if not parts:
        return False
    table, key, _ = parts
    try:
        dataset_id = hierarchy.dataset_for_table(table).dataset_id
    except hierarchy.UnknownDatasetError:
        return False
    supply = (dataset_id, f"{dataset_id}@{key}")
    return (f"{table}__{key}" in rec.completed_runs
            and (supply in rec.gated or supply in rec.held))
