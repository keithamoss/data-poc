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
