"""Placing the register's scenarios into the generated history
(REQ-GEN-044).

WHY THE GENERATOR AND NOT A TEST. Keith's own framing when he set this
obligation: the scenarios he proposed should be "visible in the real
dashboard rather than only green in a test run". A unit test proves the
rule; an injected scenario proves the SYSTEM, end to end, in the thing a
person actually looks at - and several of these fail by ATTENTION rather
than by computation, which a passing test cannot demonstrate at all.

WHAT THIS MODULE DECIDES, AND WHAT IT REFUSES TO.

  It decides SHAPES - that a supply arrives at 20:00 rather than 14:00,
  that two consecutive days carry no supply at all, that a delivery
  holds eight files rather than six.

  It decides nothing about VERDICTS, and criterion 6 says so. TS-3b's
  stated answer - "fills May, 79 days late" - is a claim about slot
  assignment, and generating it here would have the assignment sprint's
  own tests asserting that the pipeline agrees with the GENERATOR rather
  than with the rule.

DETERMINISTIC BY CONSTRUCTION, not by seeding (criterion 3). An
injection names a fixed INDEX into the dataset's generated periods, so
the same configuration places the same scenario in the same period
without a random draw anywhere. A seed would be a second thing that has
to stay fixed for the placement to be reproducible, and the placement
does not need one.

IT FAILS LOUDLY RATHER THAN QUIETLY DROPPING ONE (criterion 4). A
history that silently lacks the scenario somebody is about to
demonstrate is the whole failure this requirement exists to prevent -
worse than no injection at all, because the dashboard looks fine.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parent.parent

#: Where the placements are recorded for the scenario map to read
#: (criterion 7). Under `data/` because it is generator bookkeeping -
#: qa_tools/common/scenario_map.py reads it from exactly here, and the
#: pipeline may read neither it nor anything else under data/.
PLACEMENTS_PATH = ROOT / "data" / "scenario_placements.json"


class CannotPlace(RuntimeError):
    """An injection could not be placed in the history as configured.

    LOUD, AND NAMING THE SCENARIO (criterion 4). The alternative - skip
    it and carry on - produces a history that is missing exactly the
    thing somebody is about to point at, and looks complete.
    """


@dataclass(frozen=True)
class ExtraArrival:
    """One arrival a scenario needs beyond the ordinary chain.

    `at` is a wall-clock time in the ASSET's own timezone, because that
    is the clock every due time and claim window in this system is
    expressed in - a UTC instant here would have to be re-derived every
    time somebody read the register entry beside it.
    """

    day_offset: int
    at: str
    severity: str | None = None
    note: str = ""


@dataclass(frozen=True)
class Injection:
    """One scenario's required shape, relative to an anchor period."""

    scenario_id: str
    dataset_id: str
    #: Index into the dataset's own generated periods, oldest first.
    #: NEGATIVE indexes from the end, which is what keeps an injection
    #: near the recent end of a ROLLING window stable as the window
    #: moves - Birth Registrations' history ends on the anchor date, so
    #: a positive index there would name a different calendar day daily.
    anchor: int
    #: The configuration that makes this scenario's stated outcome the
    #: correct one (criterion 2). Recorded alongside the placement
    #: rather than only known here, because an outcome without its
    #: config is meaningless - Keith's own finding when he reviewed the
    #: register, and it invalidated two expected results as first
    #: written.
    config: str
    arrivals: tuple[ExtraArrival, ...] = ()
    #: Period offsets from the anchor that carry NO supply at all.
    suppress: tuple[int, ...] = ()
    #: Other scenario ids this same placement demonstrates. TS-1's third
    #: file IS TS-4's already-filled-slot arrival; recording one
    #: placement under both is honest, where generating a second
    #: identical arrival would be padding.
    also_demonstrates: tuple[str, ...] = ()


@dataclass(frozen=True)
class Placement:
    """Where one injection actually landed."""

    scenario_id: str
    dataset: str
    period: str
    period_date: date
    config: str
    arrivals: tuple[dict, ...] = field(default_factory=tuple)
    suppressed: tuple[str, ...] = ()

    def as_record(self) -> dict:
        """The shape qa_tools/common/scenario_map.py reads.

        `as_of` is the LATEST day this scenario has anything to show,
        which is what a reader wants the dashboard set to - an earlier
        as-of date would hide the very arrival the scenario is about.
        """
        latest = self.period_date
        for arrival in self.arrivals:
            day = date.fromisoformat(arrival["date"])
            if day > latest:
                latest = day
        return {
            "scenario_id": self.scenario_id,
            "dataset": self.dataset,
            "period": self.period,
            "as_of": latest.isoformat(),
            "supplies": [a["run_id"] for a in self.arrivals if a.get("run_id")],
            "config": self.config,
        }


def resolve(injection: Injection, periods: Sequence) -> Placement:
    """Which real period this injection lands in.

    `periods` is the dataset's own generated periods, oldest first -
    whatever the generator is about to write, not every period the
    calendar could ever yield. Anchoring to what is GENERATED is what
    makes criterion 4 checkable: an anchor outside it means the history
    does not reach far enough, which is a real configuration problem
    rather than an off-by-one to clamp away.
    """
    if not periods:
        raise CannotPlace(
            f"{injection.scenario_id}: no periods were generated for "
            f"{injection.dataset_id}, so there is nowhere to place it")
    index = injection.anchor if injection.anchor >= 0 else len(periods) + injection.anchor
    if not 0 <= index < len(periods):
        raise CannotPlace(
            f"{injection.scenario_id}: anchor {injection.anchor} falls outside the "
            f"{len(periods)} period(s) generated for {injection.dataset_id}. Either the "
            f"history is too short for this scenario or the anchor is wrong - it is not "
            f"safe to place it somewhere else, because the period is part of what the "
            f"scenario demonstrates.")
    anchor = periods[index]

    suppressed = []
    for offset in injection.suppress:
        at = index + offset
        if not 0 <= at < len(periods):
            raise CannotPlace(
                f"{injection.scenario_id}: it needs the period {offset:+d} from "
                f"{anchor.name} to carry no supply, and that period is outside the "
                f"generated history")
        suppressed.append(periods[at].name)

    arrivals = []
    for extra in injection.arrivals:
        day = anchor.date + timedelta(days=extra.day_offset)
        arrivals.append({
            "date": day.isoformat(),
            "at": extra.at,
            "severity": extra.severity,
            "note": extra.note,
        })
    return Placement(
        scenario_id=injection.scenario_id,
        dataset=injection.dataset_id,
        period=anchor.name,
        period_date=anchor.date,
        config=injection.config,
        arrivals=tuple(arrivals),
        suppressed=tuple(suppressed))


def for_dataset(dataset_id: str, injections: Sequence[Injection] | None = None
                ) -> list[Injection]:
    return [i for i in (injections if injections is not None else INJECTIONS)
            if i.dataset_id == dataset_id]


def no_two_scenarios_share_a_period(injections: Sequence[Injection],
                                    periods_by_dataset) -> None:
    """Refuse two injections landing in the same period of one dataset.

    NOT TIDINESS. Two scenarios in one period means each one's stated
    outcome depends on the other's arrivals, so neither demonstrates
    what it claims - and whichever is read first looks correct. Criterion
    11 says the same thing about incompatible schedule configurations;
    this is the same failure one level down, where the configuration is
    identical and the arrivals collide.
    """
    seen: dict[tuple[str, str], str] = {}
    for injection in injections:
        placement = resolve(injection, periods_by_dataset[injection.dataset_id])
        for name in (placement.period, *placement.suppressed):
            key = (injection.dataset_id, name)
            if key in seen and seen[key] != injection.scenario_id:
                raise CannotPlace(
                    f"{injection.scenario_id} and {seen[key]} both need "
                    f"{name} of {injection.dataset_id}, so neither would demonstrate "
                    f"what it claims - each one's outcome would depend on the other's "
                    f"arrivals. Move one to a different anchor.")
            seen[key] = injection.scenario_id


def resolve_run_ids(placements: Sequence[Placement], recognised) -> None:
    """Fill in each injected arrival's REAL run id, from recognition.

    WHY NOT THE GENERATOR'S OWN. Run identity comes from RECEIPT ORDER
    over the deliveries recognition finds (REQ-GEN-043), not from the
    generator's manifest numbering, and the two diverge the moment a
    scenario SUPPRESSES a period: the manifest is short by however many
    slots were left empty and every later id shifts. Measured on the
    first real run of this code - the placement claimed run_036 and the
    supply was run_034, a coordinate pointing at somebody else's data.

    So the generator records the delivery NAME, which both sides agree
    on, and the run id is read back from recognition once everything is
    written. Observed rather than predicted, which is the same rule this
    project applies to every other derived identity.
    """
    by_name = {arrival.delivery_name: arrival.run_id for arrival in recognised}
    for placement in placements:
        for arrival in placement.arrivals:
            name = arrival.get("delivery")
            if name and name in by_name:
                arrival["run_id"] = by_name[name]


def check_suppressed_days_are_empty(placements: Sequence[Placement], recognised) -> None:
    """Refuse a history where a "no supply at all" day has one anyway
    (criterion 4).

    THE CASE THIS CATCHES IS REAL AND WAS HIT IMMEDIATELY. Suppressing a
    period stops the generator writing THAT period's own chain; it does
    nothing about a RESUPPLY of an earlier period that happens to land
    on the same calendar day, and resupply delays are drawn at random.
    TS-2's whole claim is that two days stay unfilled, and an unrelated
    arrival landing on one of them makes the scenario demonstrate
    something else - quietly, because the dashboard looks plausible
    either way.

    Checked against what RECOGNITION actually found rather than against
    what the generator meant to write, for the same reason
    resolve_run_ids reads it back: the question is what the pipeline will
    see.
    """
    for placement in placements:
        for day in placement.suppressed:
            landed = [a.run_id for a in recognised
                      if a.received_at is not None
                      and str(a.received_at)[:10] == day]
            if landed:
                raise CannotPlace(
                    f"{placement.scenario_id}: {day} was meant to carry no supply at "
                    f"all, and {len(landed)} arrived ({', '.join(landed)}) - a resupply "
                    f"of an earlier period landing that day. The scenario would "
                    f"demonstrate something else, so this is not a history to emit. "
                    f"Move the anchor to a stretch no resupply reaches.")


def write_placements(placements: Sequence[Placement],
                     path: Path | str | None = None) -> Path:
    """Record where every scenario landed (criterion 7).

    ONE FILE, REWRITTEN WHOLE. A placement is a fact about the history
    that exists right now, and a regeneration replaces that history
    entirely - so merging into what was there before would leave
    coordinates pointing at supplies that no longer exist.
    """
    target = Path(path or PLACEMENTS_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    records = []
    for placement in placements:
        record = placement.as_record()
        for also in _ALSO.get(placement.scenario_id, ()):
            records.append({**record, "scenario_id": also})
        records.append(record)
    records.sort(key=lambda r: r["scenario_id"])
    target.write_text(json.dumps({"placements": records}, indent=2) + "\n")
    return target


#: Scenario ids a placement demonstrates BESIDES its own, filled in from
#: INJECTIONS below so `write_placements` needs no second table.
_ALSO: dict[str, tuple[str, ...]] = {}


#: THE INJECTIONS THEMSELVES.
#:
#: Each one names the configuration that makes its outcome correct,
#: because Keith's own review of the register established that an
#: outcome without its config is meaningless - "files as a resupply of
#: Wednesday" depends entirely on the cadence, the due time and the
#: claim-window size, and a different window gives a different and
#: equally correct answer.
#:
#: THE ONES THAT NEED A DIFFERENT DUE TIME ARE NOT HERE YET. TS-3c, TS-3d
#: and TS-10 all need the supply for day D due 22:00 on D-1, which no
#: effective-dated calendar version can currently express: the claim
#: window is versioned on the calendar, and the due TIME lives unversioned
#: in each ODCS contract's `slaProperties`. Criteria 8 to 11 are that
#: work, and it is a real fork about what becomes authoritative rather
#: than an implementation detail - see this requirement's own decisions.
INJECTIONS: tuple[Injection, ...] = (
    Injection(
        scenario_id="TS-1",
        dataset_id="birth-registrations",
        anchor=-8,
        config="daily, due 14:00 AWST, 60 minutes' grace, 4-hour claim window - the "
               "configuration in force. The 20:00 arrival is outside the next day's "
               "window, which opens at 10:00 the following morning.",
        arrivals=(
            ExtraArrival(0, "14:00", "red", "the original supply, which fails QA"),
            ExtraArrival(0, "16:00", None, "the resupply, which passes"),
            ExtraArrival(0, "20:00", None,
                          "the third file - expected to file as a resupply of this same "
                          "day, because tomorrow's window has not opened and no claimable "
                          "unfilled slot exists"),
        ),
        also_demonstrates=("TS-4",),
    ),
    Injection(
        scenario_id="TS-2",
        dataset_id="birth-registrations",
        # A WEEKDAY, WITH TWO WEEKDAYS BEFORE IT. The calendar is daily
        # and so includes weekends, but a supplier outage told as
        # "Tuesday and Wednesday missed, Thursday arrives on time" is not
        # the same story if two of those days are a Saturday and a
        # Sunday - nobody was expecting a supply then anyway. Held far
        # enough from TS-1 that neither scenario's days touch the other's,
        # which no_two_scenarios_share_a_period() enforces rather than
        # trusting this comment.
        anchor=-12,
        config="daily, due 14:00 AWST, 60 minutes' grace - the configuration in force. "
               "The supplier is down for two days and the next supply arrives on time "
               "for its OWN day rather than catching up.",
        arrivals=(
            ExtraArrival(0, "14:00", None, "the on-time arrival, two days after the outage"),
        ),
        suppress=(-2, -1),
    ),
)

for _injection in INJECTIONS:
    if _injection.also_demonstrates:
        _ALSO[_injection.scenario_id] = _injection.also_demonstrates
