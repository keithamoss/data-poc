"""Everything that needs a person, gathered into one queue
(REQ-DASH-070).

ONE ELEMENT, NOT ONE PER PRODUCING RULE, and at ~30 datasets that is
the whole requirement rather than a refinement of it. Six requirements
- REQ-PIPE-057, 059, 060, 064, 065 and 063's closed-but-unfilled slot -
each carry their own "report it as needing action / at WARNING / as
informational" criterion, and the rule governing how those COMBINE sat
in two NFRs on two of the six. Built independently, each honours its
own criterion and the aggregate obligation is met by nobody. So this
module owns the aggregate: every producer contributes ITEMS, and
nothing downstream gets to render a banner of its own.

A QUEUE, NOT A FEED, and the requirements themselves force the split.
REQ-PIPE-064's own NFR asks for both "re-presented on every run until
resolved" and "must not become thirty banners at 30 datasets", which
one time-ordered feed cannot do at once: a feed is scanned and
discarded, a queue is drained. Put a persistent state in a feed and you
get either wallpaper or a hold that scrolls away. The activity feed
stays a feed.

SEVERITY IS NOT A DATA VERDICT (criterion 5). An unrecognised artefact
at WARNING must not make a reader think the dataset is amber -
REQ-PIPE-057 criterion 9 says explicitly it does not fail the delivery.
Event severity and data-quality status are different claims about
different things, so they get different vocabularies here and different
appearances on the page, and neither is ever distinguished by colour
alone.

BLOCKING IS A SECOND AXIS, not a third severity (criterion 3).
REQ-PIPE-065's uncertain assignment is genuinely NON-BLOCKING - the
supply was filed, just uncertainly - and mixing a non-blocking item
into a work queue with a weak distinction is how people learn to
ignore the queue. Keith's call, 2026-09-24, was that it nonetheless
SHARES the one element: the total is what a person acts on, "six
things waiting for me" is the number, and two surfaces means nobody
knows it. The distinction carries what kind; the count carries the
urgency.

RESPONSES ARE NAMED, NEVER OFFERED (criterion 8). The resolution path
does not exist until delivery sprint 12, so for a period this shows
work nobody can clear - accepted for build order, and exactly why an
item carries `actionable`. REQ-PIPE-064's own NFR warns that "a hold
nobody can clear is indistinguishable from a bug", so the item says
which it is rather than presenting a control that would do nothing.

COMMITTED HISTORY ONLY. This feeds a dashboard build and may never
open data/ or any warehouse - every fact it renders was already
committed by the producing requirement, which is what makes it
readable in CI. Four trees, and nothing else:

    delivery_log/           held supplies, contested and unrecognised
                            files, receipt-time anomalies
    processing_log/         failed loads
    observations/in_flight/ a delivery still being written when we
                            looked
    filings/                an assignment made under ambiguity

FILINGS ARE NOT RECORDED YET (Keith, 2026-09-25, on REQ-PIPE-062), so
that last source contributes nothing today. It is read anyway, for the
same reason REQ-PIPE-065's rule was built before anything could
exercise it: a reader written when the writer turns on is a reader
written by somebody who has forgotten why the shape is what it is.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from qa_tools.common import filing, hierarchy, in_flight_log, load_log

ROOT = Path(__file__).resolve().parent.parent.parent

DELIVERY_LOG_DIR = ROOT / "delivery_log"

#: Event severity. DELIBERATELY NOT the status vocabulary - there is no
#: "green", no "amber" and no "red" here, because none of these is a
#: verdict on anybody's data (criterion 5).
INFORMATIONAL = "informational"
WARNING = "warning"
NEEDS_ACTION = "needs-action"

SEVERITY_ORDER = (NEEDS_ACTION, WARNING, INFORMATIONAL)

#: What kind of thing this is. The kind is what a person recognises;
#: the severity is how loudly it asks.
HELD_SUPPLY = "held-supply"
FAILED_LOAD = "failed-load"
CONTESTED_FILE = "contested-file"
UNRECOGNISED_FILE = "unrecognised-file"
IN_FLIGHT_DELIVERY = "in-flight-delivery"
UNCERTAIN_ASSIGNMENT = "uncertain-assignment"
CLOSED_UNFILLED_SLOT = "closed-unfilled-slot"


@dataclass(frozen=True)
class Item:
    """One thing waiting for a person.

    `blocking` and `severity` are separate on purpose (criterion 3): a
    held supply and an uncertain assignment are both worth a person's
    attention and only one of them stops a supply.

    `actionable` is FALSE for everything today and is a field rather
    than a constant because it is the thing that changes at delivery
    sprint 12. Criterion 8 forbids presenting a response that cannot
    yet be taken AS A CONTROL - naming it in words is required, and is
    what `responses` is for.
    """

    kind: str
    severity: str
    blocking: bool
    headline: str
    detail: str
    agency_id: str | None = None
    collection_id: str | None = None
    dataset_id: str | None = None
    observed_at: str | None = None
    responses: tuple[str, ...] = ()
    actionable: bool = False
    #: REQ-PIPE-065 criterion 1's qualifier, carried so criterion 9 can
    #: render it everywhere the assignment is rendered rather than only
    #: here.
    ambiguity: str | None = None

    def as_record(self) -> dict:
        return {"kind": self.kind, "severity": self.severity, "blocking": self.blocking,
                "headline": self.headline, "detail": self.detail,
                "agencyId": self.agency_id, "collectionId": self.collection_id,
                "datasetId": self.dataset_id, "observedAt": self.observed_at,
                "responses": list(self.responses), "actionable": self.actionable,
                "ambiguity": self.ambiguity}


@dataclass(frozen=True)
class Outstanding:
    """The whole queue, as ONE thing carrying ONE total."""

    items: tuple[Item, ...] = field(default_factory=tuple)

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def blocking(self) -> tuple[Item, ...]:
        return tuple(i for i in self.items if i.blocking)

    @property
    def needs_review(self) -> tuple[Item, ...]:
        return tuple(i for i in self.items if not i.blocking)

    def _counts(self, attribute: str) -> dict[str, int]:
        out: dict[str, int] = {}
        for item in self.items:
            key = getattr(item, attribute)
            if key:
                out[key] = out.get(key, 0) + 1
        return out

    @property
    def by_agency(self) -> dict[str, int]:
        """Criterion 2: a per-scope count on each affected agency, so a
        status rollup cannot absorb it."""
        return self._counts("agency_id")

    @property
    def by_collection(self) -> dict[str, int]:
        return self._counts("collection_id")

    @property
    def by_dataset(self) -> dict[str, int]:
        return self._counts("dataset_id")

    def summary(self) -> str:
        """One line for the whole queue, never one per item.

        Criterion 13: where nothing requires a person, SAY SO. An empty
        queue is a real state worth reporting, and rendering nothing at
        all leaves a reader unable to tell "nothing outstanding" from
        "this panel is broken".
        """
        if not self.items:
            return "Nothing is waiting for a person."
        blocking = len(self.blocking)
        review = self.total - blocking
        parts = []
        if blocking:
            parts.append(f"{blocking} blocking a supply")
        if review:
            parts.append(f"{review} needing review")
        return (f"{self.total} thing(s) waiting for a person - "
                f"{', '.join(parts)}.")

    def as_record(self) -> dict:
        return {"items": [i.as_record() for i in self.items],
                "total": self.total,
                "blockingCount": len(self.blocking),
                "byAgency": self.by_agency,
                "byCollection": self.by_collection,
                "byDataset": self.by_dataset,
                "summary": self.summary()}


def _scope_of(dataset_id: str | None) -> tuple[str | None, str | None]:
    """The agency and collection a dataset sits under, or (None, None).

    An id the tree does not know is NOT an error here: this reads
    committed history that may name a dataset since renamed or
    retired, and a queue that raises on one stale record shows a reader
    nothing at all.
    """
    if not dataset_id:
        return (None, None)
    try:
        entry = hierarchy.dataset(dataset_id)
    except Exception:
        return (None, None)
    return (entry.agency_id, entry.collection_id)


def _collection_agency(collection_id: str) -> str | None:
    for entry in hierarchy.all_datasets():
        if entry.collection_id == collection_id:
            return entry.agency_id
    return None


def _delivery_records(log_dir: Path | None = None) -> list[dict]:
    directory = Path(log_dir or DELIVERY_LOG_DIR)
    if not directory.is_dir():
        return []
    out = []
    for path in sorted(directory.glob("*.json")):
        try:
            out.append(json.loads(path.read_text()))
        except (OSError, json.JSONDecodeError):
            # Unreadable is skipped rather than fatal, the same reading
            # in_flight_log.observations() takes: this is a report
            # ABOUT something odd, and it should not take the page down.
            continue
    return out


def _from_deliveries(log_dir: Path | None = None) -> list[Item]:
    items: list[Item] = []
    for record in _delivery_records(log_dir):
        delivery = record.get("delivery", "")
        received = record.get("received_at")
        # HELD SUPPLIES (REQ-PIPE-059). Blocking, and the most
        # expensive kind here: the supply is staged and deliberately
        # NOT checked, so its period has no verdict at all until
        # somebody chooses.
        for held in record.get("held") or []:
            dataset_id = held.get("dataset_id")
            agency, collection = _scope_of(dataset_id)
            files = list(held.get("files") or [])
            items.append(Item(
                kind=HELD_SUPPLY, severity=NEEDS_ACTION, blocking=True,
                headline=f"{dataset_id or 'a dataset'} has a held supply in {delivery!r}",
                detail=(f"{len(files)} files in this delivery are all {dataset_id} "
                         f"({', '.join(files)}), so nothing will choose between them. "
                         f"The supply is staged and is not checked until somebody does. "
                         f"Every other dataset in the delivery was processed as usual."),
                agency_id=agency, collection_id=collection, dataset_id=dataset_id,
                observed_at=received,
                responses=("assign one of the files to the slot",
                            "reject the supply")))
        for entry in record.get("files") or []:
            name = entry.get("filename", "")
            contested = entry.get("contested_by") or []
            if contested:
                # CONTESTED (REQ-PIPE-058/057). Attributed to NEITHER
                # dataset, so it is blocking: the supply did not land.
                collection = (record.get("collections") or [None])[0]
                items.append(Item(
                    kind=CONTESTED_FILE, severity=NEEDS_ACTION, blocking=True,
                    headline=f"{name} in {delivery!r} matches more than one dataset",
                    detail=(f"{name} matches the arrival patterns of "
                             f"{', '.join(contested)}, so it was attributed to neither "
                             f"and nothing was staged from it."),
                    agency_id=_collection_agency(collection) if collection else None,
                    collection_id=collection, observed_at=received,
                    responses=("narrow one of the arrival patterns so only one matches",)))
            elif not entry.get("dataset_id"):
                # UNRECOGNISED (REQ-PIPE-057 criterion 9). A WARNING
                # and explicitly NOT a failure of the delivery: a
                # covering note is ordinary, and a renamed extract is a
                # supply on the floor. The dashboard must not make the
                # first look like the second.
                collection = (record.get("collections") or [None])[0]
                items.append(Item(
                    kind=UNRECOGNISED_FILE, severity=WARNING, blocking=False,
                    headline=f"{name} in {delivery!r} matched no dataset",
                    detail=(f"{name} matched no dataset's arrival pattern, so nothing "
                             f"was staged from it. This did not fail the delivery. A "
                             f"covering note is ordinary; a renamed extract is a supply "
                             f"on the floor."),
                    agency_id=_collection_agency(collection) if collection else None,
                    collection_id=collection, observed_at=received,
                    responses=("confirm it is not a supply",
                                "add or widen an arrival pattern so it is attributed")))
    return items


def _from_loads(log_dir: Path | None = None) -> list[Item]:
    """REQ-PIPE-060's failed loads - the queue a person drains.

    Never retried automatically: the call is theirs, and it is one of
    two things - reject that supply, or fix a genuine bug and
    reprocess.
    """
    items = []
    for record in load_log.failures(log_dir):
        agency, collection = _scope_of(record.dataset_id)
        items.append(Item(
            kind=FAILED_LOAD, severity=NEEDS_ACTION, blocking=True,
            headline=f"{record.physical} could not be loaded",
            detail=(f"The load of {record.physical} from delivery "
                     f"{record.delivery!r} failed"
                     + (f": {record.reason}" if record.reason else ".")
                     + " Nothing can read the table, so this supply has no verdict."),
            agency_id=agency, collection_id=collection, dataset_id=record.dataset_id,
            observed_at=record.recorded_at,
            responses=("reject the supply",
                        "fix the fault and reprocess the delivery")))
    return items


def _from_in_flight(observations_dir: Path | None = None) -> list[Item]:
    """REQ-PIPE-057's in-flight delivery - INFORMATIONAL, and framed as
    at the last regeneration.

    A delivery still being written when we looked is an observation
    about a moment, not a state that persists: by the time a reader
    sees it, it has almost certainly finished. Saying when we looked is
    what keeps it from reading as a current problem.
    """
    items = []
    for record in in_flight_log.observations(observations_dir):
        observed_at = record.get("observed_at")
        collection = record.get("observed_by")
        for entry in record.get("in_flight") or []:
            items.append(Item(
                kind=IN_FLIGHT_DELIVERY, severity=INFORMATIONAL, blocking=False,
                headline=f"{entry.get('delivery', '')!r} was still arriving when we looked",
                detail=("At the last regeneration this delivery was still being "
                         "written, so it was left alone rather than processed part-way. "
                         "It is picked up on the next run."),
                agency_id=_collection_agency(collection) if collection else None,
                collection_id=collection, observed_at=observed_at,
                responses=("nothing - the next run picks it up",)))
    return items


def _from_filings(filings_dir: Path | None = None) -> list[Item]:
    """REQ-PIPE-065's uncertain assignment - NON-BLOCKING, and the one
    item here that is not a failure of anything.

    The supply WAS filed. The rule took the oldest claimable unfilled
    slot while an earlier slot for the same dataset was also unfilled,
    so the supply might have been for that one. It defaults backward
    because late is commoner than early, and says so rather than
    presenting the guess as certain.
    """
    items = []
    for entry in hierarchy.all_datasets():
        for record in filing.filings_of(entry.dataset_id, filings_dir):
            if not record.get("ambiguous"):
                continue
            items.append(Item(
                kind=UNCERTAIN_ASSIGNMENT, severity=WARNING, blocking=False,
                headline=(f"{entry.dataset_name}'s supply "
                           f"{record.get('supply_id', '')} was filed under uncertainty"),
                detail=(f"It was filed to {record.get('slot')}, but an earlier slot "
                         f"was also unfilled, so it may have been for that one instead. "
                         f"The supply is filed and checked - this is a qualifier on "
                         f"which period it counts for, not a fault in the data."),
                agency_id=entry.agency_id, collection_id=entry.collection_id,
                dataset_id=entry.dataset_id,
                responses=("confirm the slot", "re-file it to the earlier slot"),
                ambiguity=record.get("ambiguity")))
    return items


def _from_closed_slots(filings_dir: Path | None = None) -> list[Item]:
    """REQ-PIPE-063's slot closed by monotonic filling and left unfilled
    (criterion 7).

    AN OBLIGATION AWAITING A DECISION, NEVER A RED DATA VERDICT. A slot
    that closed unfilled means a supply we expected never arrived and
    can no longer be claimed - which is a fact about a supplier and a
    schedule, not a finding about anybody's data. Rendering it red
    would put a permanent failure on a dataset whose data is fine.

    NOTHING CLOSES A SLOT UNTIL A LATER ONE IS FILLED, and only a
    PROMOTION fills one - which does not exist until delivery sprint 11.
    So this is structurally empty today, and deliberately derived from
    the same filled-slot question rather than from filings, because
    reading filings here is the single easiest way to reintroduce the
    forward cascade.
    """
    from qa_tools.common import assignment as assignment_mod
    from qa_tools.common import slots as slots_mod

    items = []
    for entry in hierarchy.all_datasets():
        filled = filing.filled_slots(entry.dataset_id, filings_dir)
        if not filled:
            continue
        dataset_slots = slots_mod.slots_for_dataset(entry.dataset_id)
        for slot in assignment_mod.closed_by_monotonic_filling(dataset_slots, filled):
            items.append(Item(
                kind=CLOSED_UNFILLED_SLOT, severity=NEEDS_ACTION, blocking=False,
                headline=f"{entry.dataset_name} has no supply for {slot.name}",
                detail=(f"A later slot has been filled, so {slot.name} can no longer "
                         f"be claimed by an arriving supply. This is a missing delivery "
                         f"awaiting a decision, not a finding about the data that did "
                         f"arrive."),
                agency_id=entry.agency_id, collection_id=entry.collection_id,
                dataset_id=entry.dataset_id,
                responses=("record the period as not supplied",
                            "re-file a supply to this slot")))
    return items


def _sort_key(item: Item) -> tuple:
    return (0 if item.blocking else 1,
            SEVERITY_ORDER.index(item.severity) if item.severity in SEVERITY_ORDER else 9,
            item.kind, item.dataset_id or "", item.headline)


def survey(delivery_log_dir: Path | None = None,
            processing_log_dir: Path | None = None,
            observations_dir: Path | None = None,
            filings_dir: Path | None = None) -> Outstanding:
    """Everything currently waiting for a person, from committed history.

    BLOCKING FIRST, then by severity, then stably by kind and dataset.
    A queue ordered by when things happened puts the thing somebody has
    to do today below six things they have already seen.
    """
    items = (_from_deliveries(delivery_log_dir)
              + _from_loads(processing_log_dir)
              + _from_filings(filings_dir)
              + _from_closed_slots(filings_dir)
              + _from_in_flight(observations_dir))
    return Outstanding(items=tuple(sorted(items, key=_sort_key)))
