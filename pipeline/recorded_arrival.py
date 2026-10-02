"""What the dashboard says about a supply's arrival, READ rather than
recomputed (REQ-PIPE-080 criteria 1, 4, 9, 10 and 11).

THREE DERIVATIONS OF ONE FACT is what this replaces. Both builders used
to call `cadence.classify_arrival()`, which resolved a cycle by looking
BACKWARDS from the arrival date and so could never land on a slot that
had not started; the template separately BLANKED a resupply's verdict,
which was a workaround for that derivation being wrong on exactly those
supplies rather than a rule of its own. The answer is now recorded once,
against the filing, and this module is the single place the build reads
it.

SHARED BETWEEN THE TWO BUILDERS ON PURPOSE. Birth Registrations and
Child Protection differ only in where `dataset_stats` keeps the arrival
block, and two near-identical copies of this logic is precisely the
shape that lets one be fixed and the other forgotten.

RECORDED METADATA, NEVER SUPPLY ROWS. It reads `qa.filing` and
`qa.decision` through `filing.recorded_arrival_at()` and nothing else -
the same access `promotion_state.state_for()` already has from this
path, and well inside the rule that a build may read recorded results
and never the extract itself.
"""
from __future__ import annotations

from qa_tools.common import filing

#: What a reader is told where no filing was recorded for a supply.
#: NOT "on time" and not blank: the first invents a verdict and the
#: second is the blanking this requirement removes.
UNKNOWN = "unknown"


def for_run(dataset_id: str, received_at) -> dict:
    """The arrival block for one run, as the dashboard renders it.

    `arrivedAt` IS OUR RECEIPT INSTANT (criterion 4), not the
    `earliest_extract` this used to carry. That value is `MIN()` over a
    timestamp inside the supplier's own file, so letting it decide
    punctuality lets the supplier decide whether they were late.

    `filledAt` AND `arrivedAt` ARE SEPARATE FIELDS (criterion 11), and
    neither is ever rendered in the other's place: one says when the
    supplier delivered, the other when we acted on it.

    `waitedSeconds` IS OPEN WHERE NOTHING HAS PROMOTED THE SUPPLY
    (criterion 10) - measured to now, with `awaiting` saying so. Absent
    or zero would both read as "dealt with instantly", which is the
    opposite of what is true of a supply nobody has decided on.
    """
    record = filing.recorded_arrival_at(dataset_id, received_at)
    if record is None:
        return {"arrivedAt": None, "arrivalStatus": UNKNOWN,
                "filledAt": None, "waitedSeconds": None, "awaiting": False}
    waited = record.waited
    return {
        "arrivedAt": record.received_at.isoformat() if record.received_at else None,
        # The classifier's own vocabulary, unmapped. The template's
        # ARRIVAL_STATUS_LABEL already carries `on_time` and `unfiled`
        # alongside the retired `onTime`, so a translation layer here
        # would be a second naming scheme for no gain.
        "arrivalStatus": record.classification or UNKNOWN,
        "filledAt": record.filled_at.isoformat() if record.filled_at else None,
        "waitedSeconds": waited.total_seconds() if waited is not None else None,
        "awaiting": record.awaiting,
    }
