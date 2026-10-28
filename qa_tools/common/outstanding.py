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
An inheritance that could not complete is genuinely NON-BLOCKING - no
supply is stopped by it - and mixing a non-blocking item
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

RECORDED OBSERVATIONS ONLY. This feeds a dashboard build and may
never read SUPPLY ROWS - every fact it renders is a recorded
observation made by the producing requirement, never the
extract itself. Keith's own line, 2026-09-27: a build may read
recorded QA results, never actual data, and never anything else.

IT USED TO SAY "four trees, and nothing else", and two of them are
now tables (REQ-PIPE-089 criteria 14, 16 and 22). That changes where
the facts live and not which facts they are, which is why this module
reaches them through `delivery_log` and `load_log` rather than
opening a connection of its own: those two can only answer questions
about records, and `supply_db.connect` can answer any question at all.

    the delivery record     held supplies, contested and unrecognised
                            files, receipt-time anomalies
    the load record         failed loads
    the decision log        inheritances that could not complete, and
                            newer supplies a period could carry forward
    observations/in_flight/ a delivery still being written when we
                            looked

THREE SOURCES THIS USED TO READ ARE GONE WITH THE RULES THAT FED THEM
(REQ-PIPE-131, 2026-10-04): an assignment "made under ambiguity"
(REQ-PIPE-065 criteria 1-2 - a file can no longer fit two open periods),
a slot closed by monotonic filling (REQ-PIPE-063, retired - periods
close by time now) and a supply the off-cycle gate withheld
(REQ-PIPE-077, retired - an arrival with no open period is held instead,
and holds are already here). A slot that CLOSES unfilled comes back as
REQ-PIPE-132's item, grouped per dataset rather than one per day.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from qa_tools.common import (delivery_log, display_time, hierarchy,
                             in_flight_log)

ROOT = Path(__file__).resolve().parent.parent.parent

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
#: TWO FILES FOR ONE DATASET in one delivery (REQ-PIPE-115 criterion 8,
#: REQ-PIPE-105 criterion 6) - the OPPOSITE of CONTESTED_FILE, which is
#: one file matching several datasets. Dataset-scoped and blocking: the
#: table cannot be read until a person chooses a file.
CONTESTED_TABLE = "contested-table"
UNRECOGNISED_FILE = "unrecognised-file"
IN_FLIGHT_DELIVERY = "in-flight-delivery"
#: A slot that closed with nothing in it (REQ-PIPE-132): consecutive
#: ones of a dataset are ONE item naming the count and the range.
CLOSED_UNFILLED_SLOT = "closed-unfilled-slot"
#: An inheritance that could not complete (REQ-PIPE-098 criterion 10).
#: WARNING rather than needs-action: there is nothing for a person to
#: DO about it directly - the period genuinely has no earlier supply to
#: stand on - but it is the reason a table is absent, and the reason is
#: ours rather than the supplier's, which is exactly what somebody
#: looking at an empty period needs told.
INHERITANCE_REFUSED = "inheritance-refused"
#: A newer supply a later period could carry forward (REQ-PIPE-271 criteria 6
#: and 7) - at the prominence of a refused inheritance (WARNING), one item per
#: period and dataset, standing until a clearing decision (criterion 8).
CARRY_FORWARD_POSSIBLE = "carry-forward-possible"
#: Supplies waiting on a person's decision - the terminal queue's list
#: (filing_queue.awaiting), ONE ITEM PER DATASET counting them (Keith,
#: 2026-10-06, post-build-review #123 B2). The dashboard used to leave
#: them out while `mothman supply queue` listed about twenty.
AWAITING_DECISION = "awaiting-decision"
#: A promoted supply whose re-check came back worse than the verdict it was
#: promoted on (REQ-DASH-221 criterion 12): one item per supply, under the
#: terminal's own heading, 'Promoted, then re-checked <verdict>', until it is
#: demoted or acknowledged - turned off or not (REQ-DASH-180 criterion 6).
RECHECKED_WORSE = "promoted-then-rechecked"
#: A declared calendar correction no one has confirmed yet (REQ-PIPE-170
#: criteria 3 and 19): ASSET-WIDE, one item per correction, and needs-action
#: until the asset manager confirms it - its affected supplies keep their
#: filing and verdict meanwhile. From configuration and the applied record
#: alone; its moves are worked out when it is opened, never here.
PENDING_CORRECTION = "pending-correction"
#: A confirmed correction's move another decision blocks (Keith, 2026-10-11,
#: (p)): parked, one item per supply, needs-action until the blocker clears
#: and the pass moves it, or the asset manager keeps it where it is.
PARKED_CORRECTION_MOVE = "parked-correction-move"


@dataclass(frozen=True)
class Item:
    """One thing waiting for a person.

    `blocking` and `severity` are separate on purpose (criterion 3): a
    held supply and a refused inheritance are both worth a person's
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
    #: The datasets an ASSET-WIDE item affects, each (agency, collection,
    #: dataset), so the page links each (REQ-DASH-172 criterion 11).
    affects: tuple[tuple[str, str, str], ...] = ()
    #: The date an item stands from, where it has one - a pending
    #: correction's own date, before which the page leaves it out
    #: (REQ-DASH-263 criterion 3).
    dated: str | None = None
    #: A re-checked-worse item's new verdict, which its kind's heading names
    #: ('Promoted, then re-checked <verdict>', REQ-DASH-221 criterion 12).
    verdict: str | None = None

    def as_record(self) -> dict:
        return {"kind": self.kind, "severity": self.severity, "blocking": self.blocking,
                "headline": self.headline, "detail": self.detail,
                "agencyId": self.agency_id, "collectionId": self.collection_id,
                "datasetId": self.dataset_id, "observedAt": self.observed_at,
                "responses": list(self.responses), "actionable": self.actionable,
                "dated": self.dated,
                **({"verdict": self.verdict} if self.verdict else {}),
                "affects": [{"agencyId": a, "collectionId": c, "datasetId": d,
                             "name": _name_of(d)} for a, c, d in self.affects]}


@dataclass(frozen=True)
class Outstanding:
    """The whole queue, as ONE thing carrying ONE total."""

    items: tuple[Item, ...] = field(default_factory=tuple)
    #: Every held supply and contested pair OVER ITS WHOLE LIFE
    #: (REQ-PIPE-115 criterion 12), as dataset_blockers.Blocker records.
    #: Not items: an item is what is waiting NOW, and the dashboard's
    #: as-of view has to know what was waiting THEN.
    blockers: tuple[dict, ...] = field(default_factory=tuple)

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
                "summary": self.summary(),
                "blockers": list(self.blockers)}


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


def _delivery_records(conn=None) -> list[dict]:
    """Every delivery record.

    The file version skipped one it could not parse rather than
    failing, "the same reading in_flight_log.observations() takes: this
    is a report ABOUT something odd, and it should not take the page
    down". There is nothing left to be unparseable, so the tolerance
    goes with the files rather than being kept as a comment about a
    hazard that cannot occur.
    """
    return delivery_log.records(conn)

def _from_deliveries(conn=None) -> list[Item]:
    items: list[Item] = []
    for record in _delivery_records(conn):
        delivery = record.get("delivery", "")
        received = record.get("received_at")
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


def _from_holds(conn=None) -> list[Item]:
    """Supplies nothing could place, from the hold store (REQ-PIPE-078).

    IT USED TO READ `qa.delivery.held`, and that was the defect this
    requirement exists to fix rather than a tidier source. A delivery
    record is written once and never rewritten, so a hold read from one
    could never stop being outstanding: resolving it changed nothing a
    reader could see, and the queue went on asking for work already
    done. The store has a resolution, so this reads only what is still
    open (criterion 2).

    BOTH KINDS ARRIVE HERE ON THE SAME TERMS (criterion 3). The
    assignment-rule hold had no source at all before - it was a
    `continue` in the filing pass - so the queue could show one kind of
    hold and was structurally blind to the other.

    RECORDED OBSERVATIONS ONLY (criterion 4): `qa.hold` is a record
    somebody's rule made, and nothing here reaches a schema holding
    supply rows.
    """
    from qa_tools.common import supply_holds

    items = []
    with delivery_log._db(conn) as db:
        held_supplies = supply_holds.outstanding(db)
        # OBSERVED AT ITS RECEIPT (post-build-review #123 A2), as
        # dataset_blockers already does: `raised_at` is the wall clock of
        # whichever pass raised it - a replay's today - so on any past as-of
        # date the page dropped every held supply from the queue.
        received = {(r[0], r[1]): r[2] for r in db.execute(
            "SELECT DISTINCT ON (dataset_id, delivery) dataset_id, delivery, received_at "
            "FROM qa.delivery_file WHERE dataset_id IS NOT NULL "
            "ORDER BY dataset_id, delivery, received_instant, receipt_sequence").fetchall()}
    for held in held_supplies:
        agency, collection = _scope_of(held.dataset_id)
        # RECEIVED WHILE TURNED OFF (REQ-PIPE-179 criterion 24, amending
        # REQ-PIPE-064 criterion 5): listed, quietly, and NOT counted among
        # the states needing a person.
        quiet = held.turned_off
        items.append(Item(
            kind=HELD_SUPPLY, severity=INFORMATIONAL if quiet else NEEDS_ACTION,
            blocking=not quiet,
            headline=(f"{held.dataset_id} sent a supply while turned off" if quiet else
                      f"{held.dataset_id} has a supply nothing could place"),
            detail=(f"{held.describe()} Every other dataset in the same delivery "
                     f"was processed as usual."),
            agency_id=agency, collection_id=collection, dataset_id=held.dataset_id,
            observed_at=(received.get((held.dataset_id, held.delivery))
                         or held.raised_at.isoformat()),
            responses=held.responses))
    return items


def _from_contested_tables(blockers, conn=None) -> list[Item]:
    """REQ-PIPE-115 criterion 8: a table two files claim, one item per
    open pair, naming both files - and, criterion 27, carrying any load
    the pair's files failed rather than raising a second item for it.

    WORDED AS REQ-PIPE-194 criteria 1 and 15: 'Two files for one table',
    each file with its receipt, settled by saying what each file is, and
    WHERE - the terminal drives it, so the item names the place and hands
    over no command. Actionable: the step exists now (REQ-PIPE-193)."""
    from qa_tools.common import dataset_blockers, display_time, supply_files

    items = []
    open_ones = [b for b in blockers
                 if b.kind == dataset_blockers.CONTESTED and b.is_open]
    receipts: dict[tuple[str, str], dict[str, object]] = {}
    if open_ones:
        with delivery_log._db(conn) as db:
            for b in open_ones:
                receipts[(b.dataset_id, b.delivery)] = dict(db.execute(
                    "SELECT filename, received_instant FROM qa.delivery_file "
                    "WHERE delivery = ? AND dataset_id = ? "
                    "ORDER BY received_instant, receipt_sequence, filename",
                    [b.delivery, b.dataset_id]).fetchall())
    for blocker in open_ones:
        agency, collection = _scope_of(blocker.dataset_id)
        got = receipts.get((blocker.dataset_id, blocker.delivery)) or {}
        files = "; ".join(
            f"{name}, received {display_time.format_instant(got[name])}" if got.get(name)
            else name for name in (list(got) or list(blocker.files)))
        refused = " ".join(f"{name} could not be loaded ({why})."
                           for name, why in blocker.load_failures)
        items.append(Item(
            kind=CONTESTED_TABLE, severity=NEEDS_ACTION, blocking=True,
            headline=f"{_name_of(blocker.dataset_id)}: Two files for one table",
            detail=(f"Two files arrived for its table: {files}. Nothing is checked until "
                    f"a person says what each file is." + (f" {refused}" if refused else "")),
            agency_id=agency, collection_id=collection, dataset_id=blocker.dataset_id,
            observed_at=blocker.opened_at,
            responses=(f"say what each file is, at "
                       f"'{supply_files.where_to_settle(blocker.dataset_id)}'",),
            actionable=True))
    return items


def _from_unfilled_periods(conn=None) -> list[Item]:
    """REQ-PIPE-132 criteria 10 and 11: every closed, unfilled period
    nobody has marked, grouped into consecutive runs per dataset - one
    item each, at thirty datasets as at two."""
    from qa_tools.common import filing_queue, slot_state

    items: list[Item] = []
    with delivery_log._db(conn) as db:
        collections = sorted({e.collection_id for e in hierarchy.all_datasets()})
        for collection_id in collections:
            try:
                gaps = filing_queue.closed_gaps(db, collection_id)
            except Exception as exc:  # noqa: BLE001 - the queue never fails on one producer
                print(f"note: could not read closed periods for {collection_id} "
                      f"({type(exc).__name__}: {exc}).")
                continue
            for gap in gaps:
                agency, collection = _scope_of(gap.dataset_id)
                items.append(Item(
                    kind=CLOSED_UNFILLED_SLOT, severity=NEEDS_ACTION, blocking=False,
                    headline=f"{gap.dataset_id}: {gap.describe()}",
                    detail=(f"{gap.describe()} - closed with nothing in it, and "
                            f"{slot_state.CLOSED_NOTE}."),
                    agency_id=agency, collection_id=collection, dataset_id=gap.dataset_id,
                    responses=slot_state.CLOSED_RESPONSES))
    return items


def _from_loads(skip: frozenset = frozenset()) -> list[Item]:
    """REQ-PIPE-060's failed loads - the queue a person drains.

    Never retried automatically: the call is theirs, and it is one of
    two things - reject that supply, or fix a genuine bug and
    reprocess.

    `skip` is the (dataset, physical) of each refused load belonging to
    a contested pair, which that pair's own item reports (REQ-PIPE-115
    criterion 27) - one dataset's one problem is one item.
    """
    from qa_tools.common import dataset_blockers

    items = []
    # A PERSON'S REJECTION SETTLES IT (REQ-PIPE-153 criterion 4), derived
    # from the decision log at read time - never by editing the load
    # record (criterion 3).
    for record, opened_at in dataset_blockers.unsettled_failures_opened():
        if (record.dataset_id, record.physical) in skip:
            continue
        agency, collection = _scope_of(record.dataset_id)
        reason = (record.reason or "").rstrip()
        items.append(Item(
            kind=FAILED_LOAD, severity=NEEDS_ACTION, blocking=True,
            headline=f"{record.physical} could not be loaded",
            detail=(f"The load of {record.physical} from delivery "
                     f"{record.delivery!r} failed"
                     + (f": {reason}" + ("" if reason.endswith(".") else ".")
                        if reason else ".")
                     + " Nothing can read the table, so this supply has no verdict."),
            agency_id=agency, collection_id=collection, dataset_id=record.dataset_id,
            # FROM THE RECEIPT, as its blocker is (#118 D-B).
            observed_at=opened_at,
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


def _name_of(dataset_id: str) -> str:
    try:
        return hierarchy.dataset(dataset_id).dataset_name
    except hierarchy.UnknownDatasetError:
        return dataset_id


def _from_awaiting_decisions(conn=None) -> list[Item]:
    """The supplies `mothman supply queue` lists, grouped per dataset.

    THE TERMINAL'S OWN DEFINITION, never a second one - filing_queue.
    awaiting(), less the states another producer here already raises: a
    hold (_from_holds) and a file that could not be loaded (_from_loads).
    Observed at the earliest receipt among them, so a past date shows only
    what had arrived by then.
    """
    from qa_tools.common import filing_queue, slot_state

    skip = {slot_state.TWO_FILES, slot_state.REJECTED, filing_queue.COULD_NOT_LOAD}
    by_dataset: dict[str, list] = {}
    worse: list = []
    found_worse: list = []
    ran_at: dict = {}
    try:
        with delivery_log._db(conn) as db:
            # NOTHING FILED, NOTHING AWAITING - and the slot walk below is the
            # dearest thing the survey does, so it is not paid for nothing.
            if not db.execute("SELECT 1 FROM qa.filing LIMIT 1").fetchall():
                return []
            from qa_tools.common import root_cause

            for collection in sorted({d.collection_id for d in hierarchy.all_datasets()}):
                # COUNTED AS THE TERMINAL COUNTS (REQ-PIPE-210 criterion 10),
                # through the same one function: a supply listed beneath its
                # cause is not counted, one with nothing to sit beneath is, and
                # a delivery still being gated is not (REQ-PIPE-276 criterion 12).
                waiting = filing_queue.awaiting(db, collection)
                try:
                    counted = root_cause.group_queue(
                        db, waiting, held=[h for h in filing_queue.held_in(db, collection)
                                           if not h.turned_off]).rows
                except Exception as exc:  # noqa: BLE001 - as the terminal's queue_groups
                    # UNGROUPED RATHER THAN NOTHING (post-build critic): every
                    # supply its own counted item, as before REQ-PIPE-210.
                    print(f"note: the supplies awaiting a decision could not be grouped by "
                          f"cause ({type(exc).__name__}: {exc}) - each is counted on its own.")
                    counted = waiting
                for state in counted:
                    if state.state in skip or not state.supply:
                        continue
                    if state.state == filing_queue.RECHECKED_WORSE:
                        worse.append(state)
                        continue
                    by_dataset.setdefault(state.dataset_id, []).append(state)
            from qa_tools.common import rechecking

            found_worse = [w for w in (rechecking.worse_for(db, s.dataset_id, s.supply, s.period)
                                       for s in worse) if w is not None]
            # FROM WHEN ITS RE-CHECK RAN, the instant its verdict exists from.
            ran_at = dict(db.execute(
                "SELECT caused_by_decision, min(run_instant) FROM qa.run "
                "WHERE caused_by_decision = ANY(?) AND completed_at IS NOT NULL "
                "GROUP BY caused_by_decision", [[w.recheck_id for w in found_worse]]).fetchall()) \
                if found_worse else {}
            received = {(r[0], r[1]): r[2] for r in db.execute(
                "SELECT dataset_id, supply_id, received_at FROM qa.supply_receipt").fetchall()}
    except Exception as exc:  # noqa: BLE001 - the queue never fails on one producer
        print(f"note: could not read the supplies awaiting a decision "
              f"({type(exc).__name__}: {exc}) - the rest of the queue is unaffected.")
        return []
    items = [_rechecked_worse_item(w, received.get((w.dataset_id, w.supply)),
                                   ran_at.get(w.recheck_id))
             for w in sorted(found_worse, key=lambda w: (w.dataset_id, w.period, w.supply))]
    for dataset_id, states in sorted(by_dataset.items()):
        agency, collection = _scope_of(dataset_id)
        n = len(states)
        when = sorted(str(received[(dataset_id, s.supply)]) for s in states
                      if received.get((dataset_id, s.supply)))
        periods = ", ".join(sorted({display_time.format_period(s.period) for s in states}))
        items.append(Item(
            kind=AWAITING_DECISION, severity=NEEDS_ACTION, blocking=False,
            headline=(f"{_name_of(dataset_id)}: {n} {'supply' if n == 1 else 'supplies'} "
                      f"waiting for a decision"),
            detail=(f"The rule left these for a person to decide - for {periods}. "
                    f"`mothman supply queue --collection {collection}` lists each one."),
            agency_id=agency, collection_id=collection, dataset_id=dataset_id,
            observed_at=when[0] if when else None,
            # THE SLOT STATE'S OWN RESPONSES, as the terminal offers them.
            responses=states[0].responses))
    return items


def _rechecked_worse_item(w, received, ran_at=None) -> Item:
    """REQ-DASH-221 criterion 12: one supply promoted and then re-checked
    worse, under the terminal's own heading - observed from the re-check, so
    an earlier date does not list it."""
    agency, collection = _scope_of(w.dataset_id)
    when = display_time.format_instant(received) if received else "on an unrecorded date"
    return Item(
        kind=RECHECKED_WORSE, severity=NEEDS_ACTION, blocking=False,
        headline=f"{_name_of(w.dataset_id)}, {display_time.format_period(w.period)}",
        verdict=w.now,
        detail=(f"The supply received {when} was promoted into "
                f"{display_time.format_period(w.period)} {w.promoted_on}; a re-check "
                f"{display_time.format_instant(ran_at or w.recheck_at)} came back {w.now}. It stays "
                f"promoted until a person demotes it, or acknowledges its new verdict."),
        agency_id=agency, collection_id=collection, dataset_id=w.dataset_id,
        observed_at=_iso_text(ran_at or w.recheck_at),
        responses=("demote it", "acknowledge its new verdict"))


def _iso_text(value) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else (str(value) if value else None)


def _from_inheritance_refusals() -> list[Item]:
    """REQ-PIPE-098 criterion 10 - an inheritance that could not
    complete, surfaced rather than silent.

    THE ATTEMPT IS THE POINT. A period a dataset owes nothing for is
    normally filled by the rule with whatever is still current; where
    there is nothing earlier to stand on the rule correctly does
    nothing, and the result is a genuinely absent table with an
    explanation nobody can see unless it is put here.
    """
    from qa_tools.common import inheritance

    items = []
    try:
        # THROUGH THE NARROW READER, never a connection of this module's
        # own - see this file's own docstring on why that distinction is
        # load-bearing rather than stylistic.
        refused = inheritance.refusals()
    except Exception as exc:  # noqa: BLE001 - the queue never fails on one producer
        print(f"note: could not read inheritance refusals "
              f"({type(exc).__name__}: {exc}) - the rest of the queue is unaffected.")
        return items

    for entry in refused:
        try:
            dataset = hierarchy.dataset(entry.dataset_id)
        except hierarchy.UnknownDatasetError:
            continue
        shown = display_time.format_period(entry.period)
        items.append(Item(
            kind=INHERITANCE_REFUSED, severity=WARNING, blocking=False,
            headline=f"{dataset.dataset_name} has no table at all for {shown}",
            detail=(f"Nothing is owed for {shown}, so the period would normally "
                     f"stand on this dataset's most recent supply - and no "
                     f"earlier period holds one to stand on. The table is "
                     f"genuinely absent, for a reason of ours rather than the "
                     f"supplier's."),
            agency_id=dataset.agency_id, collection_id=dataset.collection_id,
            dataset_id=dataset.dataset_id,
            responses=("file a supply into an earlier period",
                        "accept that this dataset has no history yet")))
    return items


def _from_carry_forward_warnings() -> list[Item]:
    """REQ-PIPE-271 criterion 6: each standing warning that a newer supply
    could be carried forward, at a refused inheritance's prominence."""
    from qa_tools.common import carry_forward

    items = []
    try:
        # THROUGH THE NARROW READER, as inheritance.refusals() is read - it
        # opens its own read-only connection and answers about records only.
        standing = carry_forward.standing()
        words = {(w.dataset_id, w.period): carry_forward.lines(w, voice="page")
                 for w in standing}
    except Exception as exc:  # noqa: BLE001 - the queue never fails on one producer
        print(f"note: could not read carry-forward warnings "
              f"({type(exc).__name__}: {exc}) - the rest of the queue is unaffected.")
        return items
    for w in standing:
        try:
            dataset = hierarchy.dataset(w.dataset_id)
        except hierarchy.UnknownDatasetError:
            continue
        said = words[(w.dataset_id, w.period)]
        items.append(Item(
            kind=CARRY_FORWARD_POSSIBLE, severity=WARNING, blocking=False,
            headline=carry_forward.headline(w),
            detail=" ".join(said),
            agency_id=dataset.agency_id, collection_id=dataset.collection_id,
            dataset_id=dataset.dataset_id,
            responses=(f"carry it forward: {carry_forward.command(w)}",)))
    return items


def _from_pending_corrections(conn=None) -> list[Item]:
    """REQ-PIPE-170 criterion 3 - each pending correction, needing action."""
    from qa_tools.common import correction_apply

    try:
        with delivery_log._db(conn) as db:
            found = correction_apply.pending(db)
            from qa_tools.common import correction_trial

            cal = correction_trial.working()[0]
            affected = {p.reference: correction_apply.affected_datasets(p, cal) for p in found}
    except Exception as exc:  # noqa: BLE001 - the queue never fails on one producer
        print(f"note: could not read pending corrections ({type(exc).__name__}: {exc}) - "
              f"the rest of the queue is unaffected.")
        return []
    return [Item(
        kind=PENDING_CORRECTION, severity=NEEDS_ACTION, blocking=False,
        headline=f"Calendar correction {p.reference} awaits the data asset's manager",
        # NO DATE OR REASON IN THE WORDS (REQ-DASH-263): the page writes `dated`
        # in its own style, and the reason, free text that may hold an ISO
        # date, is what `mothman supply corrections` shows.
        detail=(f"On {p.label}. Until it is confirmed, the "
                f"supplies it affects keep their period and verdict, and the moves it makes "
                f"are worked out when it is opened."),
        affects=tuple((*_scope_of(ds), ds) for ds in affected[p.reference]),
        dated=str(p.date),
        responses=(f"see its moves: mothman supply corrections --reference {p.reference}",
                   "the data asset's manager confirms it, keeping any supply where it is"))
        for p in found]


def _from_parked_corrections(conn=None) -> list[Item]:
    """Each parked correction move, needing action (Keith, 2026-10-11)."""
    from qa_tools.common import correction_apply

    try:
        with delivery_log._db(conn) as db:
            found = correction_apply.parked(db)
    except Exception as exc:  # noqa: BLE001 - the queue never fails on one producer
        print(f"note: could not read parked correction moves ({type(exc).__name__}: {exc}) "
              f"- the rest of the queue is unaffected.")
        return []
    from qa_tools.common import filing

    items = []
    for m in found:
        agency, collection = _scope_of(m.dataset_id)
        # NEVER OFFER A KEEP THAT WOULD BE REFUSED (post-build-review #190
        # D5): the item says why instead.
        refused = correction_apply.keep_refusal(m)
        keep = None if refused else (
            f"the data asset's manager keeps it where it is: mothman supply "
            f"confirm-correction --reference {m.reference} --keep {m.supply_id} "
            f"--keep-reason '<why>'")
        cannot = f" {refused} It cannot be kept there." if refused else ""
        now = (filing.filing_for(m.dataset_id, m.supply_id) or {}).get("slot")
        gap = correction_apply.gap_ahead(m) if now == m.from_period else None
        if now != m.from_period:
            # MOVED BY A PERSON SINCE IT WAS PARKED (delivery-critic #152, 4):
            # the pass will not move it from somewhere nobody confirmed.
            headline = (f"Correction {m.reference} was to move {m.supply_id} from "
                        f"{m.from_period or 'a hold'} to {m.to_period or 'a hold'}, but it "
                        f"has since been filed to {now or 'no period'}")
            detail = (f"Confirmed by {m.confirmed_by} and parked; someone moved it while "
                      f"it waited, so the pass leaves it alone. "
                      + ("Keep it where it is now, or move it by hand." if keep else
                         f"Move it by hand.{cannot}"))
            responses = (keep,) if keep else ("move it by hand to a period still owed",)
        elif gap:
            # INTO A TURNED-OFF GAP (post-build-review #190 D6): the pass
            # leaves it parked, so the item names the gap, not a move.
            headline = (f"Correction {m.reference} was to move {m.supply_id} from "
                        f"{m.from_period or 'a hold'} to {m.to_period}, which now owes nothing")
            detail = (f"Confirmed by {m.confirmed_by}. {gap} It stays parked until "
                      f"{m.to_period} is owed again.{cannot}")
            responses = tuple(r for r in (
                f"change effective_to or effective_from so {m.to_period} is owed", keep and
                f"or {keep}") if r)
        else:
            headline = (f"Correction {m.reference} moves {m.supply_id} from "
                        f"{m.from_period or 'a hold'} to {m.to_period or 'a hold'}, once what "
                        f"blocks it is cleared")
            detail = (f"Confirmed by {m.confirmed_by}; parked because another decision "
                      f"blocks it. It stays where it is, with its verdict there, until then - "
                      f"and the next processing pass moves it.{cannot}")
            responses = tuple(r for r in (f"clear what blocks it: {m.blocked.splitlines()[0]}",
                                          keep and f"or {keep}") if r)
        items.append(Item(
            kind=PARKED_CORRECTION_MOVE, severity=NEEDS_ACTION, blocking=False,
            headline=headline, detail=detail,
            agency_id=agency, collection_id=collection, dataset_id=m.dataset_id,
            observed_at=m.parked_at, responses=responses))
    return items


def _sort_key(item: Item) -> tuple:
    return (0 if item.blocking else 1,
            SEVERITY_ORDER.index(item.severity) if item.severity in SEVERITY_ORDER else 9,
            item.kind, item.dataset_id or "", item.headline)


def survey(conn=None, observations_dir: Path | None = None) -> Outstanding:
    """Everything currently waiting for a person, from committed history.

    BLOCKING FIRST, then by severity, then stably by kind and dataset.
    A queue ordered by when things happened puts the thing somebody has
    to do today below six things they have already seen.
    """
    from qa_tools.common import dataset_blockers

    blockers = dataset_blockers.all_blockers(conn)
    items = (_from_deliveries(conn)
              + _from_holds(conn)
              + _from_contested_tables(blockers, conn)
              + _from_loads(dataset_blockers.refused_in_a_contest(conn))
              + _from_inheritance_refusals()
              + _from_carry_forward_warnings()
              + _from_awaiting_decisions(conn)
              + _from_pending_corrections(conn)
              + _from_parked_corrections(conn)
              + _from_unfilled_periods(conn)
              + _from_in_flight(observations_dir))
    return Outstanding(items=tuple(sorted(items, key=_sort_key)),
                       blockers=tuple(b.as_record() for b in blockers))
