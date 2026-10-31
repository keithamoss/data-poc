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


def stated_supply(entry: dict, dataset_id: str) -> str | None:
    """The supply a run's manifest entry says it is about, where it says
    one for THIS dataset - a re-check's purpose does (REQ-PIPE-140)."""
    purpose = entry.get("purpose") or {}
    return purpose.get("supply_id") if purpose.get("dataset_id") == dataset_id else None


def for_run(dataset_id: str, received_at, supply: str | None = None) -> dict:
    """The arrival block for one run, as the dashboard renders it.

    `arrivedAt` IS OUR RECEIPT INSTANT (criterion 4), not the
    `earliest_extract` this used to carry. That value is `MIN()` over a
    timestamp inside the supplier's own file, so letting it decide
    punctuality lets the supplier decide whether they were late.

    `filledAt` AND `arrivedAt` ARE SEPARATE FIELDS (criterion 11), and
    neither is ever rendered in the other's place: one says when the
    supplier delivered, the other when we acted on it.

    `waitedSeconds` IS OPEN WHERE NOTHING HAS PROMOTED THE SUPPLY
    (criterion 10), with `awaiting` saying so. Absent or zero would both
    read as "dealt with instantly", which is the opposite of what is true
    of a supply nobody has decided on.

    AN OPEN WAIT CARRIES NO FIGURE HERE (Keith, 2026-10-25,
    post-build-review #268 (a)): the page measures it from the arrival to
    BUILT_AT, the build's own instant, never the reader's clock. Measured
    here, to this step's own now, it changed on every build from unchanged
    results, so every collection's data file got a new name each time
    (REQ-DASH-291 criterion 16, REQ-PIPE-255 criterion 23). `awaiting` and
    `arrivedAt` are all the page needs, and BUILT_AT is blanked by the
    fingerprint already.
    """
    # THE SUPPLY THE RUN SAYS IT IS ABOUT, where it says one (REQ-PIPE-193
    # criterion 13; post-build-review #171 B): a settled pair's two files
    # can share one receipt instant, and then the instant names the
    # arrival's supply, never the re-filed one.
    record = (filing.recorded_arrival(dataset_id, supply) if supply
              else filing.recorded_arrival_at(dataset_id, received_at))
    if record is None:
        return {"arrivedAt": None, "arrivalStatus": UNKNOWN,
                "filledAt": None, "waitedSeconds": None, "awaiting": False,
                "statedOriginal": None, "filedBy": None, "slot": None}
    waited = record.waited
    return {
        "arrivedAt": record.received_at.isoformat() if record.received_at else None,
        # The classifier's own vocabulary, unmapped. The template's
        # ARRIVAL_STATUS_LABEL already carries `on_time` and `unfiled`
        # alongside the retired `onTime`, so a translation layer here
        # would be a second naming scheme for no gain.
        "arrivalStatus": record.classification or UNKNOWN,
        "filledAt": record.filled_at.isoformat() if record.filled_at else None,
        "waitedSeconds": (waited.total_seconds() if waited is not None and not record.awaiting
                          else None),
        "awaiting": record.awaiting,
        # REQ-PIPE-103 criterion 19 and REQ-PIPE-147 criterion 7: shown
        # BESIDE the receipt, labelled as the filer's statement, and who
        # filed it with the person resolved through contract/people.yaml.
        "statedOriginal": record.stated_original,
        "filedBy": _filed_by(record.filed_by),
        # THE PERIOD IT IS FILED TO (post-build-review #123 B1): the supply
        # history chains resupplies within a period, never across one.
        "slot": record.slot,
    }


def _filed_by(filed_by: dict | None) -> dict | None:
    from qa_tools.common import people

    if not filed_by:
        return None
    if filed_by.get("kind") != "person":
        return {"kind": "automated"}
    return {"kind": "person", "route": filed_by.get("route"),
            "who": people.display_name(filed_by.get("who"))}
