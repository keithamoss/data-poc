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
    #: Which named transform to apply to this arrival's FILE SET, for a
    #: collection whose delivery carries several files. `None` leaves it
    #: as the generator built it.
    #:
    #: A NAME RATHER THAN A CALLABLE, so the table below stays data that
    #: can be read, diffed and reviewed - three of these scenarios are
    #: about what a delivery's file set looks like, and a lambda in a
    #: declaration is the point at which a table stops being one.
    file_shape: str | None = None


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
    #: Period offsets from the anchor where no OTHER period's arrival may
    #: land - a resend shifted off to the next weekday instead - while each
    #: of these periods keeps its own supply. TS-47 needs its day's own
    #: supply never to come, and on the first scripted replay an earlier
    #: day's resend landed on it at 10:11 and filled it, which is not the
    #: scenario. Suppressing the period would not do: the next day's own
    #: supply is part of what TS-47 shows.
    quiet: tuple[int, ...] = ()
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
    quiet: tuple[str, ...] = ()

    def as_record(self) -> dict:
        """The shape qa_tools/common/scenario_map.py reads.

        `in_place_on` is the LATEST day this scenario has anything to show,
        which is what a reader wants the dashboard set to - an earlier
        in-place-on date would hide the very arrival the scenario is about.
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
            "in_place_on": latest.isoformat(),
            "supplies": [a["run_id"] for a in self.arrivals if a.get("run_id")],
            "config": self.config,
        }


#: The named transforms an arrival's `file_shape` can ask for.
#:
#: EACH ONE IS A SHAPE, NOT AN OUTCOME (criterion 6). "cp_clients cannot
#: be parsed" is a fact about the bytes that arrived; that it is recorded
#: red, that its slot stays unfilled and that every check depending on it
#: reads red naming it are all the PIPELINE's answers, and generating any
#: of them here would have the pipeline's own tests asserting agreement
#: with this file.
FILE_SHAPES: dict[str, str] = {
    "one_file_unreadable":
        "cp_clients.csv arrives as an extract that goes ragged partway and cannot "
        "be parsed at all, while the other "
        "five load cleanly - Keith's own case from real operational experience, and "
        "the one he called 'a really important one'.",
    "one_table_only":
        "a delivery carrying a single table, which is what a corrected resupply of "
        "one table actually looks like - it is that dataset's own supply arriving "
        "late, not a resupply 'within' an earlier delivery.",
    "unmatched_resupply":
        "the six expected files plus two resupplies whose names match no pattern at "
        "all - a renamed extract from an upstream system. The danger is that the "
        "supply looks complete.",
    "columns_reordered":
        "cp_carers.csv arrives with its first two columns swapped, header and rows "
        "alike - the same data, laid out differently by an upstream export.",
}

def unreadable(content: str) -> str:
    """The same extract, gone wrong partway through - ragged rows.

    CHECKED AGAINST THE REAL READER RATHER THAN ASSUMED, and the first
    attempt failed that check. It was an unterminated quote, which reads
    like obvious rubbish and which `read_csv_explicit_nulls()` parses
    quite happily into an empty two-column table - so the scenario would
    have demonstrated an empty supply with nonsense columns, not a
    supply that cannot be loaded at all. A row carrying more fields than
    the header does raise, with `Expected N fields in line M, saw K`.

    KEEPS THE REAL HEADER AND THE REAL FIRST ROWS, because that is what
    a truncated or mis-delimited export actually looks like: a file that
    starts out fine. A file of obvious rubbish would be caught by
    anything, including a person glancing at it.
    """
    lines = content.splitlines()
    if len(lines) < 3:
        return content
    keep = lines[:max(2, len(lines) // 2)]
    widest = max(line.count(",") for line in keep) + 3
    return "\n".join([*keep, ",".join(str(i) for i in range(widest))]) + "\n"


def reordered(content: str) -> str:
    """The same extract with its first two columns swapped, in the header
    and in every row alike - which is what a changed export layout looks
    like, and which loads correctly because columns are matched by name.
    CSV-aware, so a quoted comma never moves a value between columns."""
    import csv
    import io

    rows = list(csv.reader(io.StringIO(content)))
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    for row in rows:
        writer.writerow([row[1], row[0], *row[2:]] if len(row) >= 2 else row)
    return out.getvalue()


def apply_file_shape(shape: str | None, files: dict[str, str]) -> dict[str, str]:
    """One delivery's file set, as the named shape wants it.

    UNKNOWN NAMES RAISE. A shape somebody mistyped would otherwise leave
    the delivery exactly as it was, and the scenario would quietly not be
    in the history - which is the failure criterion 4 exists to prevent,
    arriving by a different route.
    """
    if shape is None:
        return files
    if shape not in FILE_SHAPES:
        raise CannotPlace(
            f"unknown file shape {shape!r} - known shapes are "
            f"{', '.join(sorted(FILE_SHAPES))}")
    out = dict(files)
    if shape == "one_file_unreadable":
        out["cp_clients.csv"] = unreadable(files["cp_clients.csv"])
    elif shape == "one_table_only":
        out = {"cp_clients.csv": files["cp_clients.csv"]}
    elif shape == "unmatched_resupply":
        # NAMES NOTHING CLAIMS. Not a variant of a real name - a
        # different convention entirely, which is what an upstream system
        # changing its export looks like.
        out["CLIENTS_EXTRACT_FINAL.csv"] = files["cp_clients.csv"]
        out["placements (2).csv"] = files["cp_placements.csv"]
    elif shape == "columns_reordered":
        out["cp_carers.csv"] = reordered(files["cp_carers.csv"])
    return out


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

    quiet = []
    for offset in injection.quiet:
        at = index + offset
        if not 0 <= at < len(periods):
            raise CannotPlace(
                f"{injection.scenario_id}: it needs the period {offset:+d} from "
                f"{anchor.name} kept clear of other periods' arrivals, and that period "
                f"is outside the generated history")
        quiet.append(periods[at].name)

    arrivals = []
    for extra in injection.arrivals:
        day = anchor.date + timedelta(days=extra.day_offset)
        arrivals.append({
            "date": day.isoformat(),
            "at": extra.at,
            "severity": extra.severity,
            "note": extra.note,
            "file_shape": extra.file_shape,
        })
    return Placement(
        scenario_id=injection.scenario_id,
        dataset=injection.dataset_id,
        period=anchor.name,
        period_date=anchor.date,
        config=injection.config,
        arrivals=tuple(arrivals),
        suppressed=tuple(suppressed),
        quiet=tuple(quiet))


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
        for name in dict.fromkeys((placement.period, *placement.suppressed,
                                   *placement.quiet)):
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

    WHY NOT THE GENERATOR'S OWN. Run identity comes from RECOGNITION
    (REQ-GEN-043) - since REQ-PIPE-105 the staged table's spelling at
    our receipt instant, and before that a position in receipt order -
    not from the generator's manifest numbering, and the two diverged the moment a
    scenario SUPPRESSES a period: the manifest is short by however many
    slots were left empty and every later id shifts. Measured on the
    first real run of this code - the placement claimed run_036 and the
    supply was run_034, a coordinate pointing at somebody else's data.

    So the generator records the delivery NAME, which both sides agree
    on, and the run id is read back from recognition once everything is
    written. Observed rather than predicted, which is the same rule this
    project applies to every other derived identity.
    """
    # BY (DELIVERY, DATASET), NOT BY DELIVERY ALONE (2026-10-02). One
    # file is one arrival since REQ-PIPE-105, so a six-file delivery is
    # six runs sharing one name, and a name-keyed map kept whichever was
    # recognised LAST - a cp-clients scenario pointing at the
    # cp_placements run. The scenario's own dataset picks its run; a
    # delivery that did not carry that dataset falls back to its only
    # run where there is exactly one, and to nothing otherwise rather
    # than to a guess.
    by_name: dict[str, dict[str, str]] = {}
    for arrival in recognised:
        datasets = tuple(getattr(arrival, "files_by_dataset", None) or ()) or ("",)
        for dataset_id in datasets:
            by_name.setdefault(arrival.delivery_name, {})[dataset_id] = arrival.run_id
    for placement in placements:
        for arrival in placement.arrivals:
            runs = by_name.get(arrival.get("delivery") or "") or {}
            run_id = runs.get(placement.dataset) or (
                next(iter(runs.values())) if len(runs) == 1 else None)
            if run_id:
                arrival["run_id"] = run_id


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
                     path: Path | str | None = None,
                     merge: bool = False) -> Path:
    """Record where every scenario landed (criterion 7).

    ONE FILE, REWRITTEN WHOLE PER DATASET. A placement is a fact about
    the history that exists right now, and a regeneration replaces that
    history entirely - so keeping what was there before would leave
    coordinates pointing at supplies that no longer exist.

    `merge` KEEPS OTHER DATASETS' PLACEMENTS, and is what lets the two
    generators run independently: `mothman bdm generate-synthetic-data`
    rewrites Birth Registrations' scenarios and must not delete Child
    Protection's, which it knows nothing about. Records for the datasets
    being written are replaced outright either way, so a scenario that
    moved does not leave its old coordinate behind.
    """
    target = Path(path or PLACEMENTS_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    records = []
    if merge and target.is_file():
        mine = {p.dataset for p in placements}
        try:
            existing = json.loads(target.read_text()).get("placements") or []
        except (OSError, json.JSONDecodeError):
            existing = []
        records.extend(r for r in existing if r.get("dataset") not in mine)
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
#: TS-14 IS NOT HERE FOR THE SAME UNDERLYING REASON AS TS-12, which is
#: what makes the pair worth reading together. Its shape is a corrected
#: `cp_clients` arriving ALONE weeks later, and that delivery was written
#: correctly - one file, its own receipt, recognised as clients' own
#: supply arriving late. The run then died the same way TS-12's did, on
#: `cp_placements` this time: a run resolves its views from the tables
#: THIS ARRIVAL carried, so five of the six are simply absent and dbt's
#: models ref() all six.
#:
#: `supply_db.borrow_views()` exists for exactly this - "a delivery
#: carrying one re-sent table cannot be checked on its own... the run's
#: schema simply gets a VIEW onto each table the earlier run already
#: resolved" - and nothing calls it from the ordinary path. So the two
#: scenarios are one gap wearing two faces: A DELIVERY THAT DOES NOT
#: CARRY ALL SIX TABLES CANNOT BE QA'D AT ALL TODAY, whether a table is
#: missing because it never came or because it could not be read.
#:
#: TS-12 IS HERE SINCE 2026-10-05 (criterion 15), now that the file
#: checks refuse a ragged file before it is loaded (REQ-QAC-096) and a
#: refused own table reads red rather than failing its run (REQ-DASH-148).
#: What follows is why it waited, kept because the reason is the most
#: useful thing this requirement found:
#:
#: TS-12 WAS NOT HERE, AND THE REASON IS THE MOST USEFUL THING
#: THIS REQUIREMENT HAS FOUND SO FAR. It was injected on 2026-09-28 and
#: it worked exactly as written at the arrival layer - a real Child
#: Protection extract going ragged partway, `cp_clients FAILED to load
#: (ParserError: Expected 10 fields in line 265, saw 12)`, recorded for
#: human action, no table staged. Then the RUN died: dbt could not find
#: `qa_cp_run_011.cp_clients`, the whole run was recorded INCOMPLETE,
#: and the five tables that HAD loaded produced no results at all.
#:
#: The register expects the opposite - the five staged, QA'd and green,
#: `cp_clients` red, and every check depending on it red with a chip
#: naming the blocker. REQ-PIPE-035 already defers red-for-unrun to the
#: promotion sprint, saying no check's verdict is produced through it
#: yet; what it does NOT say, and what this found, is that one
#: unloadable table takes the whole delivery's QA down with it. Keith
#: called TS-12 "a really important one" from real operational
#: experience, and it is: today a supplier sending one bad file loses
#: the QA on five good ones.
#:
#: Not injected until that is built, because a history with an
#: INCOMPLETE run in it is one the dashboard cannot be built from - the
#: scenario would break the thing it exists to be visible on.
#:
#: TS-34 IS NOT HERE, AND IT IS NOT AN OVERSIGHT. It wants eight files
#: where six are expected - a second cp_clients and a second
#: cp_placements, each matching its dataset's own pattern, so neither can
#: be placed. Child Protection's arrival patterns are EXACT filenames
#: (`cp_clients\.csv`), so two files in one directory can never both
#: match one of them: the duplicate-match hold the scenario is about
#: cannot arise for this collection as configured. Attempted anyway on
#: 2026-09-28, and the files were reported as matching NO pattern, which
#: is TS-38's scenario wearing TS-34's name - a shape that demonstrates
#: the wrong thing is worse than one not yet injected. Widening a
#: pattern is a real behaviour change with a gate of its own about
#: exactly this ambiguity, so it is Keith's call rather than a
#: workaround.
#:
#: THE ONES THAT NEED A DIFFERENT DUE TIME ARE NOT HERE YET. TS-3c, TS-3d
#: and TS-10 all need the supply for day D due 22:00 on D-1. The
#: configuration can say it since REQ-PIPE-113 - a participation version in
#: contract/calendar.yaml with expected_time "22:00" and days_before 1,
#: read on each period's own date - so what remains is REQ-GEN-044's
#: criteria 8 to 11: the generated history stating its eras as such
#: versions.
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
                          "day, because tomorrow's window has not opened, so this day is "
                          "still the open period"),
        ),
        # TS-41: the 16:00 resend supersedes the 14:00 supply that failed
        # (REQ-PIPE-118) - the same placement, honestly recorded under both.
        also_demonstrates=("TS-4", "TS-41"),
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
    # REQ-GEN-136 and 137 (sprint 11). Each is placed inside the setting era
    # it needs (contract/data-asset.yaml's synthetic versions; criterion 15),
    # and none shares a period with another. Shapes only: the severity is
    # what the generator puts into the rows, and the QA tools decide.
    #
    # TS-43, TS-44, TS-45 AND TS-46 ARE PARKED (Keith, 2026-10-05). The
    # first three each need an AMBER supply - warnings and no failure - and
    # TS-46 a GREEN resend; no dial this generator
    # has produces one reliably: the 'amber' preset trips single-tier checks
    # and reads red as a whole, and a plain truncation into the row-count
    # warn band splits multiple-birth groups (three sibling checks fail) and
    # compounds across consecutive days (row count and drift fail). TS-46's
    # resend is churned from the first supply, which moves its row count and
    # its distribution enough that those two checks read it red against the
    # supply it was to replace. All were tried on real rebuilds; the
    # register says what planting needs (plans/running-thoughts.md #63).
    Injection(
        scenario_id="TS-47",
        dataset_id="birth-registrations",
        anchor=-16,
        # QUIET ON ITS OWN DAY AND THE NEXT, so no earlier day's resend
        # fills either before the late file comes (found by the first
        # scripted replay, which refused the mark-not-supplied because a
        # 10:11 resend had filled the day).
        quiet=(0, 1),
        config="daily, due 14:00 AWST, 4-hour claim window: the next day's window "
               "opens at 10:00. The day's own supply never comes; it arrives at 11:00 "
               "the NEXT day, after that window opened.",
        # NO `suppress`: the injection already replaces this period's own
        # chain with the one late arrival, and suppressing the day as well
        # shifted an unrelated resend onto the next day, where it collided
        # with another arrival's receipt instant.
        arrivals=(ExtraArrival(1, "11:00", None,
                               "the late file, which fills the next day rather than its own"),),
    ),
    Injection(
        scenario_id="TS-38",
        dataset_id="cp-clients",
        anchor=-3,
        config="quarterly, Feb/May/Aug/Nov. The current files match their patterns "
               "and the resupplies of two of them do not - a renamed extract from "
               "an upstream system.",
        arrivals=(
            ExtraArrival(0, "09:00", None,
                          "six matching files plus two whose names match no pattern "
                          "at all - the danger being that the supply looks complete",
                          file_shape="unmatched_resupply"),
        ),
    ),
    Injection(
        scenario_id="TS-12",
        dataset_id="cp-clients",
        anchor=-6,
        config="quarterly, Feb/May/Aug/Nov. One delivery of all six tables in which "
               "cp_clients goes ragged partway - a row with more fields than its header.",
        arrivals=(
            ExtraArrival(0, "09:00", None,
                          "all six tables, cp_clients ragged partway and refused by the "
                          "fields-per-row file check; the other five load",
                          file_shape="one_file_unreadable"),
        ),
    ),
    Injection(
        scenario_id="TS-56",
        dataset_id="cp-carers",
        # -8, a clean quarter (no resupply chain), MOVED FROM -9 on 2026-10-05:
        # -9 is a red chain, and replacing it removed the only knock-on
        # re-evaluation (REQ-PIPE-121) the generated history had.
        anchor=-8,
        config="quarterly, Feb/May/Aug/Nov. cp_carers arrives with its columns in "
               "another order than the contract's; everything else as usual.",
        arrivals=(
            ExtraArrival(0, "09:00", None,
                          "all six tables, cp_carers' first two columns swapped - it "
                          "loads with a column-order warning",
                          file_shape="columns_reordered"),
        ),
    ),
)

for _injection in INJECTIONS:
    if _injection.also_demonstrates:
        _ALSO[_injection.scenario_id] = _injection.also_demonstrates
