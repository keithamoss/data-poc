"""Slots - one expected supply, for one dataset, in one period
(REQ-PIPE-052).

THE DISTINCTION THIS MODULE EXISTS FOR, because everything downstream
is defined against it: a PERIOD is shared by every dataset on a
calendar, and a SLOT belongs to exactly one dataset. Child Protection's
six datasets share 2026-Q1; they have six different slots in it, with
six due instants, six grace allowances and six claim windows, because
all three of those are per-dataset facts.

Flattening that is the failure the requirement's own story names: one
late table dragging five punctual ones down with it. A collection-level
deadline can only ever be one table's answer imposed on the rest.

SLOTS ARE DERIVED, NEVER AUTHORED. Nobody writes a slot down; it falls
out of a dataset's participation in its calendar's periods. At ~30
datasets across years of history that is the only tractable shape - and
it means a slot cannot drift from the schedule, because there is
nothing to drift.

NOTHING HERE RECORDS ANYTHING. Whether a slot is overdue is a QUESTION
asked of the schedule and the slot's current state, not a flag some
sweep sets - see is_overdue() for why that matters. Same for
claimability.

WHY THIS IMPORTS pipeline.cadence, which is worth naming rather than
leaving as an oddity: a dataset's expected time of day, grace allowance
and claim window all live in its own ODCS contract's slaProperties, and
that array is parsed in exactly one place. Reading it a second time
here would be two parsers for one file, which is the shape this repo
keeps removing. The layering is untidy - qa_tools/common/ reaching into
pipeline/ - and the tidier fix, moving contract parsing out of
pipeline/, is a refactor this requirement does not need.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from qa_tools.common import asset_time, hierarchy, schedule
from qa_tools.common.schedule import Period


@dataclass(frozen=True)
class Slot:
    """ONE expected supply: this dataset, this period.

    `due_at` and `claim_opens_at` are real instants carrying their own
    offset (REQ-PIPE-048), never wall-clock times somebody has to
    interpret.

    There is no `closes_at`, and its absence is a decision rather than
    an omission: a claim window OPENS a configured interval before the
    due instant and NEVER CLOSES, because late is always allowed
    (plans/supply-model.md Thread E). What the window prevents is
    claiming FORWARD - a slot whose window has not opened yet cannot be
    claimed at all, which makes the forward cascade structurally
    impossible rather than merely unlikely.
    """

    dataset_id: str
    period: Period
    due_at: datetime
    grace: timedelta
    claim_opens_at: datetime

    @property
    def name(self) -> str:
        return self.period.name

    @property
    def date(self) -> date:
        return self.period.date

    @property
    def late_after(self) -> datetime:
        """The instant a supply stops counting as on time.

        A separate property rather than a stored field, so `due_at` and
        `grace` cannot disagree with it.
        """
        return self.due_at + self.grace


def _contract_timing(dataset_id: str) -> tuple[str, int, str | None]:
    """(expected time of day, grace minutes, claim-window override) for
    one dataset, from its own contract.

    Read per ELEMENT, which is the whole reason Child Protection's six
    datasets can differ: a slaProperty naming an element overrides the
    contract-wide default for that one dataset. That discriminator was
    being parsed and discarded until REQ-PIPE-049 fixed it.
    """
    from pipeline.cadence import parse_cadence_from_contract, parse_claim_window_from_contract

    dataset = hierarchy.dataset(dataset_id)
    contract_path = hierarchy.contract_path(dataset.collection_id)
    cadence = parse_cadence_from_contract(contract_path, element=dataset.table)
    override = parse_claim_window_from_contract(contract_path, element=dataset.table)
    return cadence["expected_time"], int(cadence["latency_minutes"]), override


def slots_for_dataset(dataset_id: str, until: date | None = None) -> list[Slot]:
    """Every slot this dataset has, oldest first.

    One per period it PARTICIPATES in. A period the dataset declares
    not-expected produces NO slot - there is no supply owed, so there
    is nothing to be overdue, and creating one would invent an
    obligation the agency explicitly agreed did not exist. Note this is
    different from how periods themselves behave: a not-expected period
    is still RETURNED by the schedule, flagged, so the dashboard can
    show "no November file, agreed" rather than a silent gap.
    """
    expected_time, grace_minutes, window_override = _contract_timing(dataset_id)
    grace = timedelta(minutes=grace_minutes)
    window = schedule.claim_window(dataset_id, window_override)

    out = []
    for dataset_period in schedule.periods_for_dataset(dataset_id, until=until):
        if not dataset_period.expected:
            continue
        due_at = asset_time.wall_clock(dataset_period.date, expected_time)
        out.append(Slot(dataset_id=dataset_id, period=dataset_period.period,
                         due_at=due_at, grace=grace, claim_opens_at=due_at - window))
    return out


def is_claimable(slot: Slot, at: datetime) -> bool:
    """Could a supply arriving at `at` be filed against this slot?

    Open-ended on purpose - see Slot's own docstring. The only thing
    this refuses is claiming FORWARD, into a slot whose window has not
    opened.
    """
    asset_time.parse_instant(at, "is_claimable(at)")
    return at >= slot.claim_opens_at


def is_overdue(slot: Slot, now: datetime, filled: bool) -> bool:
    """Is this slot overdue, as at `now`?

    ASKED, NEVER RECORDED, which is criterion 7 and a real design
    choice rather than a convenience. An overdue flag written by a
    nightly sweep is wrong between the moment a slot lapses and the
    moment the sweep runs, is wrong forever if the sweep does not run,
    and quietly makes "nothing is overdue" indistinguishable from
    "nothing checked". Deriving it means the answer is correct the
    instant it is asked, including for a dashboard built from
    configuration alone.

    `filled` is the caller's - only a promotion fills a slot
    (plans/supply-model.md), and this module has no access to promotion
    state by design: it would need data.
    """
    asset_time.parse_instant(now, "is_overdue(now)")
    return not filled and now > slot.late_after


def next_unfilled_claimable(slots: list[Slot], at: datetime,
                             filled: set[str]) -> Slot | None:
    """The OLDEST slot whose window is open and which is unfilled.

    The assignment rule itself, stated once (plans/supply-model.md
    Thread E): "assign to the oldest slot whose claim window is open
    and which is unfilled. If there is no such slot, it is a resupply
    of the most recently filled slot."

    Only the first half lives here - this returns None for the resupply
    case rather than deciding it, because deciding it needs promotion
    state and therefore data. Filing is REQ-PIPE-034's; this is the
    schedule's own half of the answer, which is the half that has to be
    derivable from config alone.

    DO NOT USE THIS AS THE ASSIGNMENT RULE. It is not one, and the
    paragraph above understates what is missing: as well as the resupply
    case, this has NO on-time-wins-for-the-current-slot branch and NO
    monotonic filling. "Oldest claimable unfilled slot" on its own is
    precisely the rule plans/supply-model.md Thread E proves
    catastrophic - it produces the backward cascade, where a punctual
    supplier is recorded as a very late resupply AND the slot they
    actually filled is left to go overdue as a phantom missing delivery.

    Nothing calls this yet, which is why it is a trap rather than a bug
    (found 2026-09-23 while scoping sprints 7-10). REQ-PIPE-062 is the
    requirement that carries the whole rule; extend this there rather
    than reaching for it as-is.
    """
    for slot in slots:
        if slot.name in filled:
            continue
        if is_claimable(slot, at):
            return slot
    return None
