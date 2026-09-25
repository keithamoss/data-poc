"""Where each supply was filed, recorded once (REQ-PIPE-062).

AN ASSIGNMENT IS WRITTEN ONCE AND NEVER RE-DERIVED (criterion 10).
Re-deriving on every run would silently undo a human's re-file and make
history move under a reader - the same instability the stickiness rule
exists to prevent on the promotion side. So a supply already filed is
left exactly as it was, and this is a write-once record rather than a
computed view.

WHY THE BRANCH IS STORED RATHER THAN RECOMPUTED, which is the part that
looks redundant and is not: "why is this supply here" has to be
answerable a year later without re-running anything, and recomputing it
then gives a DIFFERENT answer, because the slot state it was decided
against has moved on. The rule branch is a fact about the moment of
filing, not a property of the supply.

FILED IS NOT FILLED, and keeping them apart is load-bearing. A supply
is FILED against a slot by this rule, with no human in it. A slot is
FILLED only when a supply has been PROMOTED into it - a decision, and
one this PoC does not make yet. Treating a filing as a fill would
reintroduce the forward cascade through the back door: the rejected
14:00 supply in that worked example is filed against Monday, and if
that counted as filling Monday, the 16:00 resupply would be pushed to
Tuesday and every later supply after it.

So filled_slots() returns nothing today, deliberately, and says why
rather than being absent - the promotion side arrives with the decision
log in batch 4.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from qa_tools.common.assignment import Assignment

ROOT = Path(__file__).resolve().parent.parent.parent

#: Its own committed tree, beside the delivery and processing logs and
#: outside qa_results/. A filing is not a QA result - it is decided
#: BEFORE any check runs, and it survives a supply that never produces
#: one.
FILINGS_DIR = ROOT / "filings"

_UNSAFE = re.compile(r"[^0-9A-Za-z._-]+")


def path_for(dataset_id: str, supply_id: str, filings_dir: Path | None = None) -> Path:
    directory = Path(filings_dir or FILINGS_DIR) / _UNSAFE.sub("_", dataset_id)
    return directory / f"{_UNSAFE.sub('_', supply_id)}.json"


def record(assignment: Assignment, filings_dir: Path | None = None) -> Path | None:
    """Commit where one supply was filed, once.

    Returns the path written, or None where this supply was already
    filed - which is the ordinary case on every run after the first,
    not a guard against a bug.
    """
    path = path_for(assignment.dataset_id, assignment.supply_id, filings_dir)
    if path.exists():
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(assignment.as_record(), indent=2) + "\n")
    return path


def filing_for(dataset_id: str, supply_id: str,
                filings_dir: Path | None = None) -> dict | None:
    """This supply's filing, or None where it has not been filed."""
    path = path_for(dataset_id, supply_id, filings_dir)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def filings_of(dataset_id: str, filings_dir: Path | None = None) -> list[dict]:
    """Every filing for one dataset.

    Read from that dataset's OWN directory, so answering it costs
    nothing in the size of any other dataset's history - the same
    per-dataset shape REQ-PIPE-034 established for arrivals.
    """
    directory = Path(filings_dir or FILINGS_DIR) / _UNSAFE.sub("_", dataset_id)
    if not directory.is_dir():
        return []
    out = []
    for path in sorted(directory.glob("*.json")):
        try:
            out.append(json.loads(path.read_text()))
        except (OSError, json.JSONDecodeError):
            continue
    return out


def filled_slots(dataset_id: str, filings_dir: Path | None = None) -> frozenset[str]:
    """Slots a supply has been PROMOTED into - so, nothing yet.

    NOT the slots supplies have been FILED against, and the difference
    is the whole reason this function exists rather than callers
    reading filings_of() and taking the slot names. Only a promotion
    fills a slot; an arrival does not, a staged supply does not, and a
    rejected one certainly does not.

    Returning filings here would be the single easiest way to
    reintroduce the forward cascade, because the rejected supply in
    that worked example IS filed against Monday.
    """
    return frozenset()


def file_arrivals(found_arrivals, filings_dir: Path | None = None) -> list[Assignment]:
    """Assign and record every dataset's supply in these arrivals.

    BEFORE ANY CHECK RUNS (criterion 1), which is why this is called
    from the orchestrators rather than from whatever consumes the
    result: as first proposed the period was assigned at PROMOTION, but
    checks run before promotion, so at check time there would have been
    no slot to classify against. Assignment is a derivation with no
    human in it; promotion is a decision. There is still exactly one
    place the slot is decided - it just happens earlier.

    A supply whose checks will report red is filed on the same terms as
    any other, so a supply never promoted still carries where it was
    filed: "arrived three weeks late AND was bad" is what belongs on
    the record.

    Returns only the assignments this call actually wrote. A supply
    already filed is left alone.
    """
    from qa_tools.common import assignment as assign_mod
    from qa_tools.common import slots as slots_mod

    slots_by_dataset: dict[str, list] = {}
    written: list[Assignment] = []

    for arrival in found_arrivals:
        for dataset_id in sorted(arrival.files_by_dataset):
            # A HELD supply is not filed: REQ-PIPE-059 refuses to choose
            # between two files for one dataset, and filing one of them
            # would be making that choice by another route.
            if dataset_id in arrival.held:
                continue
            if dataset_id not in slots_by_dataset:
                try:
                    slots_by_dataset[dataset_id] = slots_mod.slots_for_dataset(
                        dataset_id, until=arrival.received_at.date())
                except (ValueError, KeyError, FileNotFoundError) as exc:
                    # A dataset whose schedule cannot be built yet gets
                    # no slots rather than taking the run down - the
                    # blast-radius rule this batch applies everywhere:
                    # one exhausted or misconfigured schedule must not
                    # fail the other 29 datasets.
                    print(f"note: {dataset_id} has no slots to file against ({exc}) - "
                          f"its supplies are still recorded as arrived.")
                    slots_by_dataset[dataset_id] = []
            supply_id = _supply_id_for(arrival, dataset_id)
            if filing_for(dataset_id, supply_id, filings_dir) is not None:
                continue
            decided = assign_mod.assign(
                dataset_id=dataset_id, supply_id=supply_id,
                at=arrival.received_at, slots=slots_by_dataset[dataset_id],
                filled=filled_slots(dataset_id, filings_dir))
            record(decided, filings_dir)
            written.append(decided)
    return written


def _supply_id_for(arrival, dataset_id: str) -> str:
    """This dataset's own name for the supply in this arrival.

    The same identifier REQ-PIPE-034 builds, so a filing and an arrival
    can be joined without a second naming scheme to keep in step.
    """
    from qa_tools.common import asset_time

    names = arrival.files_by_dataset.get(dataset_id) or ()
    base = f"{dataset_id}@{asset_time.arrival_key(arrival.received_at)}"
    return base if len(names) <= 1 else f"{base}#1"
