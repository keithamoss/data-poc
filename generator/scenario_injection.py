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

import dataclasses
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Sequence

from generator.targeting import Target
from qa_tools.common import scenario_map

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
class PairFile:
    """One file of a delivery that carries two for one table (REQ-GEN-196).

    `name` is a template - `{D}` is the placement day, `{D+1}` the day after
    - so nothing here moves when ANCHOR_DATE is bumped. `content` says what
    the rows are: `extract` (the day's), `next_day` (the next day's extract,
    sent early), `duplicate` (byte-identical to the file before it),
    or `corrected` (the first file's extract without its planted fault).
    `shape` names a per-file transform from FILE_SHAPES - a stray test file
    is `stray_test_rows`, a file the load refuses `unreadable_file`. A SHAPE, NEVER A VERDICT:
    what the file IS, never what the pipeline will make of it.

    `table` names the table the file carries, for a collection whose delivery
    carries several (REQ-GEN-203: Child Protection's Client Register pairs):
    the pair's files replace that table's usual one and every other table
    comes as usual, at the delivery's one shared instant. None for a
    one-table collection. `re_export` is the table re-pulled from the source
    system - the same rows, each extracted an hour later - so its rows
    differ from the extract's without either being wrong (TS-42)."""

    at: str
    name: str
    content: str = "extract"
    severity: str | None = None
    target: object | None = None
    #: Named per-file transforms, applied in order (a stray test file that
    #: also goes ragged is both).
    shapes: tuple[str, ...] = ()
    note: str = ""
    table: str | None = None

    def filename(self, day: date) -> str:
        return self.name.replace("{D+1}", (day + timedelta(days=1)).isoformat()) \
            .replace("{D}", day.isoformat())

    @property
    def built_for(self) -> int:
        """Days after the placement day its extract is FOR."""
        return 1 if self.content == "next_day" else 0


PAIR_CONTENTS = ("extract", "next_day", "duplicate", "corrected", "re_export")


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
    #: What this arrival's rows are BUILT TO (REQ-GEN-184 criteria 1-2): a
    #: generator/targeting.Target, in place of `severity` - a target
    #: replaces the preset outright, so naming both is refused. Still a
    #: shape, not a verdict: the real tools decide (criterion 6 above).
    target: object | None = None
    #: TWO FILES IN ONE DELIVERY for one table (REQ-GEN-196), each with its
    #: own receipt; `at` is then the earlier file's.
    files: tuple[PairFile, ...] = ()
    #: THE TABLES `severity` DIRTIES, for a collection whose delivery carries
    #: several (REQ-GEN-199 criterion 1: TS-75's cp_clients alone, the other
    #: five clean). Empty is the preset's own pick, as before.
    severity_tables: tuple[str, ...] = ()
    #: EACH FILE ITS OWN RECEIPT within one delivery, as (table, "HH:MM") on
    #: the arrival's day (REQ-GEN-273 criterion 4: S10's staggered chain,
    #: Notifications 08:40, Investigations 09:00, Clients 09:20). A table not
    #: named takes `at`, which is the delivery's own (earliest) instant.
    file_times: tuple[tuple[str, str], ...] = ()

    @property
    def targets(self) -> tuple:
        return tuple(x for x in (self.target, *(f.target for f in self.files))
                     if x is not None)

    def __post_init__(self):
        for f in self.files:
            if f.content not in PAIR_CONTENTS:
                raise CannotPlace(f"a pair file's content is one of "
                                  f"{', '.join(PAIR_CONTENTS)}, not {f.content!r}")
            if f.target is not None and f.severity is not None:
                raise CannotPlace(f"a pair file at {f.at} names both a severity and a "
                                  f"target - it is one or the other")
            if f.content == "re_export" and f.table is None:
                raise CannotPlace(f"a pair file at {f.at} is a re-export of no table - a "
                                  f"re-export names the table it re-pulls")
        if self.severity_tables and self.severity is None:
            raise CannotPlace(f"an arrival at {self.at} names the tables a severity "
                              f"dirties ({', '.join(self.severity_tables)}) and no severity")
        for table, at in self.file_times:
            if at < self.at:
                raise CannotPlace(f"an arrival at {self.at} names {table} received at {at}, "
                                  f"before the delivery's own instant - `at` is the earliest")
        if self.target is not None and self.severity is not None:
            raise CannotPlace(f"an arrival at {self.at} names both a severity "
                              f"({self.severity}) and a target - a target replaces the "
                              f"preset, so it is one or the other")


@dataclass(frozen=True)
class Link:
    """One scenario id's own in-place-on date, between two of its
    placement's events (REQ-GEN-201).

    LETTERED SIBLINGS SHARE ONE PLACEMENT (TS-75a, TS-75b, ...), and each
    shows a different moment of it - so each carries its own date, and the
    two events it must fall between, rather than the placement's one
    default. A bounding event is an ARRIVAL, by the same index a scripted
    decision uses for the placement's supplies, or a SCRIPTED DECISION, by
    its `name:` - the only events whose instants configuration fixes
    (criterion 2). `days` counts whole asset days from the FIRST event's
    own day, 0 being that day (criterion 4).
    """

    scenario_id: str
    #: Or LAST_DAY: the day before the second event.
    days: int | str
    #: An int is an arrival index; a str is a scripted decision's name.
    first: int | str
    second: int | str
    #: WHAT THE LINK LANDS ON (REQ-DASH-208 criterion 2), by name from
    #: scenario_map.SUBJECTS - never a selector.
    subject: str = scenario_map.SUPPLY_HISTORY_ROW


#: THE HISTORY'S END as a link's bounding event (REQ-GEN-205 criterion 12):
#: the first instant after its last day, so a link on that day stands.
HISTORY_END = "end of the history"
#: A LINK ON THE DAY BEFORE ITS SECOND EVENT, in place of a count of days
#: (post-build-review #252): with HISTORY_END that is the history's last day,
#: wherever the anchor has moved it - TS-57b to TS-61b show what the replay's
#: confirmation recorded there.
LAST_DAY = "last day"
_CORRECTION = "correction "


def correction_event(change_reference: str) -> str:
    """A declared correction's date as a link's bounding event, named by its
    change_reference (REQ-GEN-205 criterion 12)."""
    return f"{_CORRECTION}{change_reference}"


def _correction_date(change_reference: str) -> date | None:
    """The date a declared correction counts from, or None if undeclared."""
    from qa_tools.common import correction_apply, correction_trial

    for p in correction_apply._declared(*correction_trial.working()):
        if p.reference == change_reference:
            return date.fromisoformat(p.date[:10])
    return None


def _history_last_day() -> date:
    from generator.anchor_date import get_anchor_date

    return get_anchor_date()


@dataclass(frozen=True)
class LinkDate:
    """A link resolved: its date, its two events' instants, and why it
    cannot stand if it cannot (criteria 7-9)."""

    scenario_id: str
    on: date | None
    first: tuple[str, datetime | None]
    second: tuple[str, datetime | None]
    problem: str | None = None


@dataclass(frozen=True)
class GateOutcome:
    """What a scenario DECLARES the package gate does with one supply of one
    of its arrivals (REQ-GEN-273 criterion 3) - promoted, or held back, and
    where held back, because of which other supply's dataset and whether
    after a re-check against the warehouse. A declaration of the GATE's
    decision, never a predicted verdict (REQ-GEN-186 criterion 4); the
    bootstrap compares it with the recorded promotions and hold-backs."""

    dataset_id: str
    #: The arrival, by its index in the injection's `arrivals`.
    arrival: int
    outcome: str
    because: str | None = None
    rechecked: bool = False

    def __post_init__(self):
        if self.outcome not in ("promoted", "held back"):
            raise CannotPlace(f"a declared gate outcome is 'promoted' or 'held back', not "
                              f"{self.outcome!r}")
        if self.outcome == "promoted" and (self.because or self.rechecked):
            raise CannotPlace(f"{self.dataset_id} is declared promoted, so nothing held it "
                              f"back and it names no cause")


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
    #: For a scenario with a TARGETED arrival (REQ-GEN-185): how many
    #: periods before the anchor are generated as green, on-time, single
    #: supplies nobody else's arrival lands on - so the targeted supply is
    #: measured against something the generator knew when it built it.
    #: Per injection because a quarterly lead-in is quarters, not days, and
    #: because the era a scenario must sit in can be too short for two.
    #: The period AFTER the anchor is generated green too, so the targeted
    #: perturbation does not carry into it (criterion 3).
    lead_in: int = 2
    #: Per scenario id, the date its own placement record is in place on
    #: (REQ-GEN-201). An id with no link keeps the default - the latest
    #: day the placement has anything to show (criterion 6).
    links: tuple[Link, ...] = ()
    #: The declared correction this scenario rides, by change_reference
    #: (REQ-GEN-205 criterion 10): it may sit inside that correction's claim.
    correction: str | None = None

    #: A green day after the anchor, though nothing in it is targeted
    #: (REQ-GEN-196): a pair settled at 11:00 the next day needs that day's
    #: own supply to come after the settlement - a green one, on time.
    green_follow: bool = False

    #: HOW MANY PERIODS AFTER THE ANCHOR ARE THIS INJECTION'S OWN (REQ-GEN-199,
    #: TS-78): their own supplies are this injection's arrivals on those days,
    #: so no ordinary chain is written for them, they are claimed like the
    #: anchor, and the green following period is the one after the last.
    #: ONE PLACEMENT for several days, because D+1 is both D's following day
    #: and D+2's lead-in - two injections claiming it would collide.
    covers: int = 0

    #: WHETHER THE DELIVERY KEEPS THE ORDINARY SEVERITY DRAWN FOR ITS PERIOD
    #: (REQ-GEN-199, PROVISIONAL - Keith to confirm). A scenario that shapes
    #: only one table's PRESENCE (TS-76, TS-77) leaves the rest of the
    #: delivery as the draw made it, so an ordinary amber drawn there is
    #: generated there rather than moved: Child Protection has no clean
    #: quarter left to move it to, and REQ-GEN-184 criterion 9 says every
    #: drawn amber is generated.
    keeps_drawn_severity: bool = False

    #: Offsets from the anchor that must fall inside a `hold` amber-setting
    #: era (REQ-GEN-199 criterion 15). Generation REFUSES, naming the
    #: scenario, when one does not - never shifting it outside the era.
    hold_days: tuple[int, ...] = ()

    #: THE PERIOD A SCRIPTED SUBSTITUTION STANDS ON, as an offset from the
    #: anchor (-1, the previous one), or None (REQ-GEN-207 criterion 3). It is
    #: claimed like the anchor: the scenario's outcome depends on that
    #: period's own supply, so another scenario there would change it.
    stands_on: int | None = None

    #: THE GATE OUTCOMES IT DECLARES (REQ-GEN-273 criteria 3 and 4), checked
    #: by the bootstrap against what the gate recorded.
    gate_outcomes: tuple[GateOutcome, ...] = ()

    @property
    def is_targeted(self) -> bool:
        return any(a.targets for a in self.arrivals)


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
    #: The green lead-in periods before a targeted anchor, oldest first,
    #: and the green period after it (REQ-GEN-185 criteria 1 and 3).
    lead_in: tuple[str, ...] = ()
    follow: tuple[str, ...] = ()
    #: The periods after the anchor whose own supplies are this injection's
    #: arrivals (Injection.covers).
    covered: tuple[str, ...] = ()
    #: Scenario id -> its link's resolved in-place-on date (REQ-GEN-201
    #: criterion 5). Absent ids keep the default.
    in_place_on: tuple[tuple[str, str], ...] = ()
    #: Scenario id -> what its link lands on (REQ-DASH-208 criterion 2).
    #: Absent ids land on their first supply's row.
    subjects: tuple[tuple[str, str], ...] = ()
    #: What it declares the gate does (Injection.gate_outcomes).
    gate_outcomes: tuple = ()

    @property
    def built_green(self) -> tuple[str, ...]:
        return (*self.lead_in, *self.follow)

    def in_place_on_for(self, scenario_id: str) -> str:
        """A linked id's own date (REQ-GEN-201 criterion 5); otherwise the
        latest day the placement has anything to show (criterion 6)."""
        linked = dict(self.in_place_on).get(scenario_id)
        if linked:
            return linked
        latest = self.period_date
        for arrival in self.arrivals:
            day = date.fromisoformat(arrival["date"])
            if day > latest:
                latest = day
        return latest.isoformat()

    def subject_for(self, scenario_id: str) -> str:
        """What this id's link lands on (REQ-DASH-208 criterion 2); its first
        supply's row where no link names one."""
        return dict(self.subjects).get(scenario_id, scenario_map.SUPPLY_HISTORY_ROW)

    def as_record(self) -> dict:
        """The shape qa_tools/common/scenario_map.py reads.

        `in_place_on` is the LATEST day this scenario has anything to show,
        which is what a reader wants the dashboard set to - an earlier
        in-place-on date would hide the very arrival the scenario is about.
        """
        return {
            "scenario_id": self.scenario_id,
            "dataset": self.dataset,
            "period": self.period,
            "in_place_on": self.in_place_on_for(self.scenario_id),
            "subject": self.subject_for(self.scenario_id),
            # THE SAME LIST A LINK'S `arrival N` INDEXES (supply_arrivals): a
            # delivery that leaves this dataset's file out takes no index, so
            # a script's `supply N` names the same file (the critic's G1).
            "supplies": [a["run_id"] for a in supply_arrivals(self) if a.get("run_id")],
            "config": self.config,
            "lead_in": list(self.lead_in),
            "follow": list(self.follow),
            "targets": [{"date": a["date"], "at": a["at"], **a["target"]}
                        for a in self.arrivals if a.get("target")]
            # A PAIR FILE'S TARGET, keyed by its delivery AND filename
            # (REQ-GEN-196 criterion 19), on the day its extract is for.
            + [{"date": a["date"], "at": f["at"], "delivery": a.get("delivery"),
                "filename": f["filename"], "day": f["built_for"], **f["target"]}
               for a in self.arrivals for f in (a.get("files") or []) if f.get("target")],
            # EACH DECLARED GATE OUTCOME BY ITS ARRIVAL'S DELIVERY NAME (REQ-GEN-273
            # criterion 3) - what both sides agree on, as for run ids.
            "gate_outcomes": [
                {"dataset_id": g.dataset_id, "delivery": self.arrivals[g.arrival].get("delivery"),
                 "outcome": g.outcome, "because": g.because, "rechecked": g.rechecked}
                for g in self.gate_outcomes],
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
    # REQ-GEN-199 criterion 6. cp_placements BECAUSE NO CHECK READS IT AS A
    # PARENT: its absence breaks no other table's referential check, so the
    # other five promote normally and the substitution is what shows.
    "one_table_missing":
        "the six-file delivery with cp_placements.csv absent - the supplier's "
        "extract left one table out - and the other five unchanged.",
    "missing_table_late":
        "cp_placements.csv arriving on its own, later in the quarter - the table "
        "the delivery left out, sent once the supplier noticed.",
    # REQ-GEN-218 (TS-63): Carer Register's last owed quarter, delivered
    # without it, and its file sent on its own.
    "carers_missing":
        "the six-file delivery with cp_carers.csv absent - the supplier held the "
        "Carer Register back - and the other five unchanged.",
    "carers_alone":
        "cp_carers.csv arriving on its own - the Carer Register sent separately "
        "from the quarter's delivery.",
    # REQ-GEN-273 criterion 4 (S1 green and S1 red): a zip of two tables.
    "clients_and_notifications":
        "a zip of cp_clients.csv and cp_notifications.csv alone - a resupply of two "
        "tables that arrive together.",
    "clients_and_readers":
        "a zip of cp_clients.csv and the three tables that read it - cp_notifications, "
        "cp_investigations and cp_placements - a corrected resend of a quarter whose "
        "Client Register failed.",
    "clients_short_with_notifications":
        "a zip of cp_clients.csv and cp_notifications.csv, the Client Register missing "
        "the five clients only the Notifications point at (none of Investigations or "
        "Placements does) - its own data whole, but short of what the warehouse's "
        "Notifications need.",
    # PER FILE (REQ-GEN-196's named-shapes NFR): applied to whichever file a
    # pair names, never hardwired to one filename.
    "unreadable_file":
        "the file goes ragged partway - a row with more fields than its header - so "
        "the load refuses it (TS-12's shape, for any one file).",
    "stray_test_rows":
        "a well-formed file with the dataset's real columns whose rows are plainly "
        "test data - every registrant and parent named TEST - a test file that "
        "should never have been sent.",
}

#: The shapes a single file of a pair may take (REQ-GEN-196).
FILE_SHAPES_PER_FILE = ("unreadable_file", "stray_test_rows")
#: The name columns a stray test file fills with TEST - Birth Registrations'
#: registrant and parents, and Child Protection's client (REQ-GEN-203, TS-80).
_TEST_NAME_COLUMNS = ("child_given_names", "child_family_name",
                      "registering_parent_1_name", "registering_parent_2_name",
                      "given_name", "family_name")


def shape_file(shape: str | None, content: str) -> str:
    """One file's bytes, as the named per-file shape wants them. An unknown
    name raises, as apply_file_shape's does."""
    if shape is None:
        return content
    if shape not in FILE_SHAPES_PER_FILE:
        raise CannotPlace(f"unknown per-file shape {shape!r} - known shapes are "
                          f"{', '.join(FILE_SHAPES_PER_FILE)}")
    if shape == "unreadable_file":
        return unreadable(content)
    import io

    import pandas as pd

    df = pd.read_csv(io.StringIO(content), dtype=str, keep_default_na=False)
    for column in _TEST_NAME_COLUMNS:
        if column in df.columns:
            df[column] = df[column].where(df[column] == "", "TEST")
    return df.to_csv(index=False)

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


def carries(shape: str | None, table: str) -> bool:
    """Whether a delivery of this shape carries `table`'s file at all
    (REQ-GEN-199). A delivery that leaves the table out BY DESIGN is not one
    of that dataset's supplies, so it takes no supply index - which is how a
    link's `arrival N` and a script's `supply N` keep naming the same file
    when one delivery deliberately has none (TS-76, TS-77)."""
    if shape == "one_table_only":
        return table == "cp_clients"
    if shape == "missing_table_late":
        return table == "cp_placements"
    if shape == "one_table_missing":
        return table != "cp_placements"
    if shape == "carers_missing":
        return table != "cp_carers"
    if shape == "carers_alone":
        return table == "cp_carers"
    if shape in ("clients_and_notifications", "clients_short_with_notifications"):
        return table in ("cp_clients", "cp_notifications")
    if shape == "clients_and_readers":
        return table in _CLIENTS_AND_READERS
    return True


def supply_arrivals(placement) -> list[dict]:
    """The placement's arrivals that carry its own dataset's file, in order -
    what a script's `supply N` and a link's `arrival N` index."""
    from qa_tools.common import hierarchy

    try:
        table = hierarchy.dataset(placement.dataset).table
    except Exception:  # noqa: BLE001 - an unknown dataset carries everything
        return list(placement.arrivals)
    return [a for a in placement.arrivals if carries(a.get("file_shape"), table)]


def apply_file_shape(shape: str | None, files: dict[str, str]) -> dict[str, str]:
    """One delivery's file set, as the named shape wants it.

    UNKNOWN NAMES RAISE. A shape somebody mistyped would otherwise leave
    the delivery exactly as it was, and the scenario would quietly not be
    in the history - which is the failure criterion 4 exists to prevent,
    arriving by a different route.
    """
    if shape is None:
        return files
    if shape not in FILE_SHAPES or shape in FILE_SHAPES_PER_FILE:
        raise CannotPlace(
            f"unknown file shape {shape!r} - known shapes are "
            f"{', '.join(sorted(set(FILE_SHAPES) - set(FILE_SHAPES_PER_FILE)))}")
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
    elif shape == "one_table_missing":
        out.pop("cp_placements.csv")
    elif shape == "missing_table_late":
        out = {"cp_placements.csv": files["cp_placements.csv"]}
    elif shape == "carers_missing":
        out.pop("cp_carers.csv")
    elif shape == "carers_alone":
        out = {"cp_carers.csv": files["cp_carers.csv"]}
    elif shape == "clients_and_notifications":
        out = {t: files[t] for t in ("cp_clients.csv", "cp_notifications.csv")}
    elif shape == "clients_and_readers":
        out = {f"{t}.csv": files[f"{t}.csv"] for t in _CLIENTS_AND_READERS}
    elif shape == "clients_short_with_notifications":
        out = {"cp_clients.csv": _without_notified_only(files),
               "cp_notifications.csv": files["cp_notifications.csv"]}
    return out


#: The Client Register and the tables whose cross-table checks read it.
_CLIENTS_AND_READERS = ("cp_clients", "cp_notifications", "cp_investigations", "cp_placements")

#: How many clients S1 red's Client Register leaves out (REQ-GEN-273).
NOTIFIED_ONLY_DROPPED = 5


def _without_notified_only(files: dict[str, str]) -> str:
    """cp_clients.csv without the first few clients (by id) that a
    Notification points at and no Investigation or Placement does - so the
    Notifications -> Client Register check fails against it while every
    other check reading it passes (S1 red)."""
    import io

    import pandas as pd

    def frame(name):
        return pd.read_csv(io.StringIO(files[name]), dtype=str, keep_default_na=False)
    clients = frame("cp_clients.csv")
    notified = set(frame("cp_notifications.csv")["cp_client_id"])
    others = set(frame("cp_investigations.csv").get("cp_client_id", [])) | set(
        frame("cp_placements.csv").get("cp_client_id", []))
    drop = sorted(c for c in set(clients["cp_client_id"]) if c in notified and c not in others)
    drop = drop[:NOTIFIED_ONLY_DROPPED]
    if len(drop) < NOTIFIED_ONLY_DROPPED:
        raise CannotPlace(f"only {len(drop)} client(s) are pointed at by Notifications alone, "
                          f"not the {NOTIFIED_ONLY_DROPPED} S1 red leaves out")
    return clients[~clients["cp_client_id"].isin(drop)].to_csv(index=False)


def resolve(injection: Injection, periods: Sequence,
            scripts: Sequence | None = None) -> Placement:
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

    covered = []
    for k in range(1, injection.covers + 1):
        if index + k >= len(periods):
            raise CannotPlace(
                f"{injection.scenario_id}: it needs the {injection.covers} period(s) after "
                f"{anchor.name} as its own, and the generated history ends before them")
        covered.append(periods[index + k].name)
    _refuse_outside_hold(injection, anchor.date)

    # A TARGETED SCENARIO'S LEAD-IN AND THE PERIOD AFTER IT (REQ-GEN-185):
    # both must exist in the generated history - placing them anywhere else
    # would measure the target against something it was not built for.
    lead_in, follow = [], []
    if injection.is_targeted:
        for k in range(injection.lead_in, 0, -1):
            if index - k < 0:
                raise CannotPlace(
                    f"{injection.scenario_id}: its targeted supply needs {injection.lead_in} "
                    f"lead-in period(s) before {anchor.name}, and the generated history "
                    f"starts too late for them")
            lead_in.append(periods[index - k].name)
    # NO GREEN FOLLOW WHERE THE NEXT DAY IS SUPPRESSED (REQ-GEN-196
    # criterion 19): it is filled only by a re-filed file.
    after = index + injection.covers + 1
    if (injection.is_targeted or injection.green_follow) and 1 not in injection.suppress:
        if after >= len(periods):
            raise CannotPlace(
                f"{injection.scenario_id}: it needs the period after "
                f"{periods[after - 1].name} generated green, and the history ends there")
        follow.append(periods[after].name)

    arrivals = []
    for extra in injection.arrivals:
        day = anchor.date + timedelta(days=extra.day_offset)
        arrivals.append({
            "date": day.isoformat(),
            "at": extra.at,
            "severity": extra.severity,
            "note": extra.note,
            "file_shape": extra.file_shape,
            "file_times": [list(x) for x in extra.file_times],
            # WHAT IT WAS BUILT TO, AND WHAT WAS MOVED (REQ-GEN-184
            # criterion 12): the target as asked here, the rules and their
            # intended counts filled in once the rows are built. Never a
            # verdict, never a value from a row.
            "target": extra.target.as_record() if extra.target is not None else None,
            # A PAIR'S FILES, each by its real name and receipt (REQ-GEN-196).
            "files": [{"filename": f.filename(anchor.date + timedelta(days=extra.day_offset)),
                       "at": f.at, "content": f.content, "severity": f.severity,
                       "table": f.table,
                       "shapes": list(f.shapes), "note": f.note,
                       "built_for": (anchor.date + timedelta(
                           days=extra.day_offset + f.built_for)).isoformat(),
                       "target": f.target.as_record() if f.target is not None else None}
                      for f in extra.files],
        })
    placement = Placement(
        scenario_id=injection.scenario_id,
        dataset=injection.dataset_id,
        period=anchor.name,
        period_date=anchor.date,
        config=injection.config,
        arrivals=tuple(arrivals),
        suppressed=tuple(suppressed),
        quiet=tuple(quiet),
        lead_in=tuple(lead_in),
        follow=tuple(follow),
        covered=tuple(covered),
        gate_outcomes=tuple(injection.gate_outcomes))
    for g in injection.gate_outcomes:
        if not 0 <= g.arrival < len(arrivals):
            raise CannotPlace(f"{injection.scenario_id}: a gate outcome names arrival "
                              f"{g.arrival}, and it has {len(arrivals)}")
    if not injection.links:
        return placement
    # THE DATE WRITTEN IS THE DATE VALIDATED (REQ-GEN-201 criterion 9):
    # `mothman scenarios validate` asks link_dates() too.
    dates = link_dates(injection, placement, scripts)
    refused = [d.problem for d in dates if d.problem]
    if refused:
        raise CannotPlace("; ".join(refused))
    return dataclasses.replace(placement, in_place_on=tuple(
        (d.scenario_id, d.on.isoformat()) for d in dates),
        subjects=tuple((link.scenario_id, link.subject) for link in injection.links))


def _refuse_outside_hold(injection: Injection, anchor_day: date) -> None:
    """REQ-GEN-199 criterion 15: each of `hold_days` falls inside a `hold`
    amber-setting era, or generation is refused naming the scenario - never
    shifted outside the era, which would make its held supplies promote
    themselves."""
    if not injection.hold_days:
        return
    from qa_tools.common import amber_setting, asset_time

    outside = [anchor_day + timedelta(days=k) for k in injection.hold_days
               if amber_setting.resolve(injection.dataset_id, asset_time.start_of_day(
                   anchor_day + timedelta(days=k))).value != amber_setting.HOLD]
    if outside:
        raise CannotPlace(
            f"{injection.scenario_id}: {', '.join(d.isoformat() for d in outside)} "
            f"fall(s) outside a hold amber-setting era, and the scenario's held supplies "
            f"need it - move the anchor back inside the era (contract/data-asset.yaml's "
            f"amber_setting), or add a version; it is not shifted for you")


def link_dates(injection: Injection, placement: Placement,
               scripts: Sequence | None = None) -> list[LinkDate]:
    """THE ONE LINK RESOLVER (REQ-GEN-201 criterion 9): each link's date and
    its two events' instants, from configuration and the calendar alone -
    no generated history, no database (criterion 7) - with why it cannot
    stand where it cannot (criteria 7 and 8).

    An arrival's instant is the one the generator writes - its placed day
    at its `at`, on the asset's clock. A scripted decision's is the one the
    replay plays it at: its supply's receipt, or its period's due instant
    for a period-scoped one, plus `after_hours` - or, for one timed at a wall
    clock, its `at` on the day `day_offset` after the placement's.
    """
    from qa_tools.common import asset_time, scripted_decisions

    if scripts is None:
        scripts = scripted_decisions.load()
    ours = (injection.scenario_id, *injection.also_demonstrates)
    mine = [s for s in scripts if s.scenario in ours]

    supplies = supply_arrivals(placement)

    def arrival_at(index: int) -> datetime | None:
        if not 0 <= index < len(supplies):
            return None
        a = supplies[index]
        return asset_time.wall_clock(date.fromisoformat(a["date"]), a["at"])

    def event(ref) -> tuple[str, datetime | None, str | None]:
        if isinstance(ref, bool) or not isinstance(ref, (int, str)):
            return repr(ref), None, (f"{ref!r} is not an arrival index or a decision "
                                     f"name - give an int arrival index or a decision's "
                                     f"`name:`")
        if isinstance(ref, int):
            label = f"arrival {ref}"
            at = arrival_at(ref)
            return label, at, (None if at is not None else
                               f"{label} does not exist - the injection has "
                               f"{len(supplies)} carrying {placement.dataset}'s file; "
                               f"name one of 0 to {len(supplies) - 1}")
        if ref == HISTORY_END:
            return ref, asset_time.start_of_day(_history_last_day() + timedelta(days=1)), None
        if ref.startswith(_CORRECTION):
            reference = ref[len(_CORRECTION):]
            on = _correction_date(reference)
            return ref, (None if on is None else asset_time.start_of_day(on)), (
                None if on is not None else
                f"{reference!r} is not a declared correction - declare it in "
                f"contract/calendar.yaml, or fix the link")
        label = f"decision {ref!r}"
        named = [s for s in mine if s.name == ref]
        if not named:
            return label, None, (f"no scripted decision of {', '.join(ours)} is named "
                                 f"{ref!r} - give that decision `name: {ref}` in "
                                 f"contract/scripted_decisions.yaml, or fix the link")
        if len(named) > 1:
            return label, None, (f"{len(named)} scripted decisions of {', '.join(ours)} "
                                 f"are named {ref!r}, so it names none of them - rename one")
        s = named[0]
        if s.at is not None and s.scope != scripted_decisions.PERIOD and s.period is None:
            # AT A WALL CLOCK, as the replay times it (Player._timed): `at` on
            # the day `day_offset` after the placement period's date.
            at = scripted_decisions._wall_clock_after(s, placement.period)
            return label, at, (None if at is not None else
                               f"{label} cannot be timed: {s.dataset_id} has no date for "
                               f"{placement.period}")
        if s.scope == scripted_decisions.PERIOD:
            base = scripted_decisions._due_at(s.dataset_id, placement.period)
            why = f"{s.dataset_id} has no slot for {placement.period}"
        else:
            base = arrival_at(s.supply_index if s.supply_index is not None else -1)
            why = f"its supply {s.supply_index} is not one of the injection's arrivals"
        if base is None:
            return label, None, f"{label} cannot be timed: {why}"
        return label, base + timedelta(hours=s.after_hours), None

    out = []
    for link in injection.links:
        where = f"{injection.scenario_id}'s link for {link.scenario_id}"
        first, second = event(link.first), event(link.second)
        if link.days != LAST_DAY and (isinstance(link.days, bool)
                                      or not isinstance(link.days, int)):
            out.append(LinkDate(link.scenario_id, None, first[:2], second[:2],
                                f"{where}: days {link.days!r} is not a whole number of "
                                f"asset days - give an int, 0 being the first event's day"))
            continue
        if link.scenario_id not in ours:
            out.append(LinkDate(link.scenario_id, None, first[:2], second[:2],
                                f"{where}: {link.scenario_id} is not a scenario this "
                                f"placement demonstrates ({', '.join(ours)}) - link one of "
                                f"those, or add it to also_demonstrates"))
            continue
        broken = next((e[2] for e in (first, second) if e[2]), None)
        if broken:
            out.append(LinkDate(link.scenario_id, None, first[:2], second[:2],
                                f"{where}: {broken}"))
            continue
        on = (asset_time.local_date(second[1]) - timedelta(days=1) if link.days == LAST_DAY
              else asset_time.local_date(first[1]) + timedelta(days=link.days))
        end = asset_time.end_of_day(on)
        problem = None
        if second[0] == HISTORY_END and not end < second[1]:
            problem = (f"{where}: {on.isoformat()} is after the end of the history "
                       f"({_history_last_day().isoformat()}) - move the link's date")
        elif not first[1] < end < second[1]:
            problem = (f"{where}: the end of {on.isoformat()} ({end.isoformat()}) does not "
                       f"fall strictly between {first[0]} at {first[1].isoformat()} and "
                       f"{second[0]} at {second[1].isoformat()} - move the link's date, "
                       f"or the event that bounds it")
        out.append(LinkDate(link.scenario_id, on, first[:2], second[:2], problem))
    return out


def generated_periods(dataset_id: str) -> list:
    """The periods the generator writes for this dataset, oldest first -
    from configuration and the anchor date alone, as its provider's own plan
    asks it.

    THROUGH THE REGISTRY (REQ-GEN-246 criterion 8): the provider of the
    dataset's collection says, so a new collection's periods come with its
    provider rather than with a branch here. REFUSED, NOT DEFAULTED
    (post-build-review #169): a third collection once silently got Birth
    Registrations' periods."""
    from generator import collections

    try:
        provider = collections.for_dataset(dataset_id)
    except collections.NoProviderError as exc:
        raise CannotPlace(f"no generator writes {dataset_id}, so it has no generated periods "
                          f"to place a scenario in: {exc}") from None
    return provider.generated_periods()


def unprovided_scenarios() -> list[str]:
    """Every injected scenario naming a dataset no generator provider makes,
    with why - checked before anything is written (REQ-GEN-246 criterion 8)."""
    from generator import collections

    out = []
    for injection in INJECTIONS:
        try:
            collections.for_dataset(injection.dataset_id)
        except collections.NoProviderError as exc:
            out.append(f"{injection.scenario_id} names {injection.dataset_id}: {exc}")
    return out


def placement_of() -> dict[str, str]:
    """Each scenario id -> the id of the placement it shares (its own, or
    the injection whose also_demonstrates lists it) - the scope a decision's
    name is unique within (post-build-review #169, Keith 2026-10-13)."""
    out = {}
    for injection in INJECTIONS:
        out[injection.scenario_id] = injection.scenario_id
        for also in injection.also_demonstrates:
            out[also] = injection.scenario_id
    return out


def check_every_index_has_its_supply(placements: Sequence[Placement],
                                     injections: Sequence[Injection] | None = None,
                                     scripts: Sequence | None = None) -> None:
    """Refuse a history where a script's `supply N` or a link's `arrival N`
    would name a different file than configured (post-build-review #169,
    Keith 2026-10-13: refuse at generation).

    A placement records the supplies RECOGNITION found, and an arrival not
    recognised for the placement's dataset is left out - so every index
    from that arrival on names a later file in the replay than it does in
    link_dates(). Checked once run ids are read back, because recognition
    is not configuration and validate cannot see it.
    """
    from qa_tools.common import scripted_decisions

    if scripts is None:
        scripts = scripted_decisions.load()
    by_id = {i.scenario_id: i for i in (injections if injections is not None else INJECTIONS)}
    for placement in placements:
        gap = next((n for n, a in enumerate(supply_arrivals(placement))
                    if not a.get("run_id")), None)
        if gap is None:
            continue
        injection = by_id.get(placement.scenario_id)
        ours = (placement.scenario_id, *(injection.also_demonstrates if injection else ()))
        used = [(f"scripted decision {s.operation} ({s.scenario})", s.supply_index)
                for s in scripts if s.scenario in ours and s.supply_index is not None]
        for link in (injection.links if injection else ()):
            for ref in (link.first, link.second):
                if isinstance(ref, int) and not isinstance(ref, bool):
                    used.append((f"the link for {link.scenario_id}", ref))
        past = [what for what, index in used if index >= gap]
        if past:
            raise CannotPlace(
                f"{placement.scenario_id}: arrival {gap} was not recognised as a "
                f"{placement.dataset} supply, so {', '.join(past)} would index a different "
                f"file than configured. Make that arrival recognisable, or index only "
                f"arrivals before it.")


def link_problems(injections: Sequence[Injection] | None = None,
                  scripts: Sequence | None = None) -> list[str]:
    """Every declared link that cannot stand (REQ-GEN-201 criteria 7 and 8),
    for `mothman scenarios validate` - through link_dates(), the resolver
    the generator writes with (criterion 9)."""
    out = []
    for injection in (injections if injections is not None else INJECTIONS):
        if not injection.links:
            continue
        try:
            placement = resolve(dataclasses.replace(injection, links=()),
                                generated_periods(injection.dataset_id))
        except CannotPlace as exc:
            out.append(str(exc))
            continue
        out += [d.problem for d in link_dates(injection, placement, scripts) if d.problem]
    return out


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
        periods = periods_by_dataset[injection.dataset_id]
        # PERIODS ONLY: its links are resolved by the caller's own resolve(),
        # against its own dataset - the Child Protection check re-keys every
        # injection to one dataset, whose files a link must not be read in.
        placement = resolve(dataclasses.replace(injection, links=()), periods)
        # A LEAD-IN OR FOLLOWING PERIOD IS CLAIMED like the anchor itself
        # (REQ-GEN-185 criterion 5): another scenario's anchor, emptied or
        # quiet day landing on one fails here naming both.
        # A SCENARIO MAY NOT EMPTY ITS OWN LEAD-IN OR FOLLOWING PERIOD
        # (post-build-review #156): the check below skips a scenario's own
        # keys, and the period would silently go missing.
        own = set(placement.suppressed) & set(placement.built_green)
        if own:
            raise CannotPlace(
                f"{injection.scenario_id} suppresses {', '.join(sorted(own))}, which is "
                f"its own lead-in or following period - a targeted supply needs that "
                f"day generated green")
        for name in claimed_periods(injection, periods, placement):
            key = (injection.dataset_id, name)
            if key in seen and seen[key] != injection.scenario_id:
                raise CannotPlace(
                    f"{injection.scenario_id} and {seen[key]} both need "
                    f"{name} of {injection.dataset_id}, so neither would demonstrate "
                    f"what it claims - each one's outcome would depend on the other's "
                    f"arrivals. Move one to a different anchor.")
            seen[key] = injection.scenario_id


def claimed_periods(injection: Injection, periods: Sequence,
                    placement: Placement | None = None) -> list[str]:
    """Every period an injection needs to itself: its anchor, the periods it
    covers, stands on, suppresses or quiets, its green lead-in and following
    periods, and any it files early into."""
    if placement is None:
        placement = resolve(dataclasses.replace(injection, links=()), periods)
    stood = stood_on(injection, periods)
    return list(dict.fromkeys((placement.period, *placement.covered,
                               *((stood,) if stood else ()),
                               *placement.suppressed, *placement.quiet,
                               *placement.built_green,
                               *filed_early_into(injection, placement, periods))))


def stood_on(injection: Injection, periods: Sequence) -> str | None:
    """The period this injection's substitution stands on (REQ-GEN-207
    criterion 3), or None. Refused, never clamped, outside the history."""
    if injection.stands_on is None:
        return None
    anchor = injection.anchor if injection.anchor >= 0 else len(periods) + injection.anchor
    index = anchor + injection.stands_on
    if not 0 <= index < len(periods):
        raise CannotPlace(
            f"{injection.scenario_id}: the period it stands on ({injection.stands_on} from its "
            f"anchor) falls outside the generated history - nothing there to stand on")
    return periods[index].name


def filed_early_into(injection: Injection, placement: Placement,
                     periods: Sequence) -> tuple[str, ...]:
    """The period before the anchor, where an arrival is received before the
    anchor's own claim window opens (REQ-GEN-199 criterion 28): the open slot
    then is the previous period's, so the filing rule files it there, and the
    scenario claims that period as surely as its anchor. TS-67 arrives twenty
    days early and files into the quarter before its own; a scenario placed
    there would have TS-67's whole delivery land in it, and keying the check
    on TS-67's anchor alone did not catch it."""
    from qa_tools.common import asset_time, slots

    names = [p.name for p in periods]
    index = names.index(placement.period)
    # ONLY AN ARRIVAL BEFORE ITS ANCHOR'S OWN DAY can be early for it.
    if index == 0 or not any(date.fromisoformat(a["date"]) < placement.period_date
                             for a in placement.arrivals):
        return ()
    opens = slots.slot_instants(injection.dataset_id, placement.period_date).claim_opens_at
    early = any(asset_time.wall_clock(date.fromisoformat(a["date"]), a["at"]) < opens
                for a in placement.arrivals)
    return (names[index - 1],) if early else ()


#: TS-79's dataset: the one Child Protection table delivered only in some
#: quarters, so it inherits in the rest (REQ-GEN-199 criteria 19-21).
INHERITING_DATASET = "cp-case-workers"


def inheritance_placements(periods: Sequence) -> list[Placement]:
    """TS-79a and TS-79b, written AFTER generation rather than injected
    (REQ-GEN-199 criterion 20; delivery-architect B4): they add nothing to the
    data and claim no period - each is a quarter cp-case-workers already
    inherits in, because its participation leaves it out. Resolved from the
    calendar's participation and the generated periods, never written into
    configuration, so an ANCHOR_DATE bump moves them with the history.

    TS-79a is the newest inherited quarter before the build's own (the last
    generated one), TS-79b the oldest - whose source is the oldest of the
    original fifteen quarters; the caller passes those fifteen (REQ-GEN-207). Each is in place on the MIDDLE of its quarter: the inheritance is
    recorded when the period is first processed after it falls due, which on
    this history is within two weeks of the quarter's date."""
    from qa_tools.common import schedule

    if len(periods) < 2:
        raise CannotPlace("TS-79: the generated history is too short to hold an "
                          "inherited quarter - lengthen the Child Protection history")
    delivered = {p.name for p in schedule.periods_for_dataset(
        INHERITING_DATASET, until=periods[-1].date)}
    inherited = [i for i, p in enumerate(periods[:-1]) if p.name not in delivered and i > 0]
    if not inherited:
        raise CannotPlace(f"TS-79: {INHERITING_DATASET} inherits in no generated quarter - "
                          f"its participation in contract/calendar.yaml now covers every "
                          f"one, so there is no inheritance to link")
    out = []
    for sid, i, why in (("TS-79a", inherited[-1], "the newest quarter it inherits in "
                                                  "before the build's own"),
                        ("TS-79b", inherited[0], "the oldest of the original fifteen, "
                                                 "whose source is the oldest of the "
                                                 "original fifteen quarters")):
        p, nxt = periods[i], periods[i + 1]
        middle = p.date + (nxt.date - p.date) / 2
        # THE QUARTER IT INHERITS FROM is the latest one it was delivered in,
        # not simply the one before (the critic's G6).
        source = next(periods[j].name for j in range(i - 1, -1, -1)
                      if periods[j].name in delivered)
        out.append(Placement(
            scenario_id=sid, dataset=INHERITING_DATASET, period=p.name,
            period_date=p.date,
            config=(f"quarterly; {INHERITING_DATASET} is delivered only in the quarters "
                    f"contract/calendar.yaml's participation names, so {p.name} - {why} - "
                    f"inherits {source}'s supply. Nothing generated for it."),
            in_place_on=((sid, middle.isoformat()),),
            subjects=((sid, scenario_map.STANDING_IN_PILL),)))
    return out


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
                      and _lands_in(placement.dataset, day, a.received_at)]
            if landed:
                raise CannotPlace(
                    f"{placement.scenario_id}: {day} was meant to carry no supply at "
                    f"all, and {len(landed)} arrived ({', '.join(landed)}) - a resupply "
                    f"of an earlier period landing that day. The scenario would "
                    f"demonstrate something else, so this is not a history to emit. "
                    f"Move the anchor to a stretch no resupply reaches.")


def _lands_in(dataset_id: str, day: str, received_at) -> bool:
    """Whether an arrival received at `received_at` belongs to the suppressed
    period `day`. For a DAILY dataset that is the period's own claim window,
    from its opening to the next day's (REQ-GEN-044): in the evening-before
    era a day's supply arrives the evening before, so the calendar day of
    receipt names the wrong period. For any other cadence, the calendar day,
    as before."""
    from qa_tools.common import hierarchy, schedule, slots

    received = (received_at if isinstance(received_at, datetime)
                else datetime.fromisoformat(str(received_at)))
    try:
        daily = schedule.calendar_for_dataset(dataset_id).name == "daily"
    except hierarchy.UnknownDatasetError:
        daily = False  # a dataset the asset does not declare has no window
    if not daily:
        return str(received_at)[:10] == day
    period = date.fromisoformat(day)
    opens = slots.slot_instants(dataset_id, period).claim_opens_at
    closes = slots.slot_instants(dataset_id, period + timedelta(days=1)).claim_opens_at
    return opens <= received < closes


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
            records.append({**record, "scenario_id": also,
                            "in_place_on": placement.in_place_on_for(also),
                            # ITS OWN SUBJECT (REQ-DASH-208 criterion 2): a
                            # sibling shows a different moment of the same
                            # placement, often on a different part of the page.
                            "subject": placement.subject_for(also)})
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
#: TS-14 IS HERE SINCE 2026-10-15, riding TS-12's placement: the corrected
#: cp_clients arrives alone weeks later. It waited because a delivery not
#: carrying all six tables could not be QA'd - a run resolved its views from
#: the tables its own arrival carried. That gap closed when every file became
#: its own arrival (REQ-PIPE-105 criterion 5): a run now reads its own table
#: and takes its siblings from the period (qa_tools/common/period_overlay.py),
#: as TS-75a's and TS-77a's lone files already showed.
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
#: be placed. cp_placements' arrival pattern is an EXACT filename, so two
#: of its files in one directory can never both match it: half the
#: duplicate-match hold the scenario is about cannot arise as configured.
#: (cp_clients' pattern WAS widened, by REQ-PIPE-202 on 2026-10-15, for
#: TS-42's one-table pair; every other pattern stays exact.) Attempted on
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
#: The configuration every two-file pair (REQ-GEN-196) is placed under.
_PAIR_CONFIG = ("daily, due 14:00 AWST, 60 minutes' grace, 4-hour claim window - the "
                "configuration in force from 2026-07-05. One delivery carries two files "
                "for one table, each with its own receipt; a person settles the pair at "
                "11:00 the next day.")

INJECTIONS: tuple[Injection, ...] = (
    Injection(
        scenario_id="TS-1",
        dataset_id="birth-registrations",
        anchor=-11,
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
        anchor=-15,
        config="daily, due 14:00 AWST, 60 minutes' grace - the configuration in force. "
               "The supplier is down for two days and the next supply arrives on time "
               "for its OWN day rather than catching up.",
        arrivals=(
            ExtraArrival(0, "14:00", None, "the on-time arrival, two days after the outage"),
        ),
        suppress=(-2, -1),
    ),
    # THE EVENING-BEFORE ERA (REQ-GEN-044; Keith, 2026-10-15): Birth
    # Registrations' oldest twelve days, 2026-06-18 to 2026-06-29, in which a
    # day's supply is due at 22:00 the evening before and its claim window
    # opens at 18:00 that evening (contract/calendar.yaml). The register tells
    # these as Monday and Tuesday; here they are a day and the day after it,
    # wherever the era has room. Ordinary days between them keep each
    # scenario's neighbours on time.
    Injection(
        scenario_id="TS-3c",
        dataset_id="birth-registrations",
        # MONDAY 2026-06-22, so its 17:00 resupply lands on a weekday.
        anchor=-96,
        config="daily evening-before: the supply for a day is due 22:00 the evening "
               "before, claim window 4 hours. The day's own supply is filled; an arrival "
               "at 17:00 that day is one hour before the NEXT day's window opens at 18:00.",
        arrivals=(
            ExtraArrival(-1, "21:00", None, "the day's own supply, on time the evening before"),
            ExtraArrival(0, "17:00", None,
                         "an hour outside the next day's window - expected to file as a "
                         "resupply of this day, held and warned, never auto-promoted"),
        ),
        # The next day keeps its own supply (at 21:00 this evening) and no
        # other period's arrival lands on it.
        quiet=(1,),
    ),
    Injection(
        scenario_id="TS-3d",
        dataset_id="birth-registrations",
        anchor=-93,
        config="daily evening-before: due 22:00 the evening before, claim window 4 "
               "hours. The day's own supply never came; an arrival at 17:00 that day "
               "is an hour before the next day's window opens.",
        arrivals=(
            ExtraArrival(0, "17:00", None,
                         "the day's only supply - expected to fill this day, 19 hours late"),
        ),
        quiet=(1,),
    ),
    Injection(
        scenario_id="TS-10a",
        dataset_id="birth-registrations",
        anchor=-98,
        config="daily evening-before: this day's supply is due 22:00 the evening "
               "before, claim window 4 hours, so its window opens at 18:00 and the day "
               "before closes then. The day before is filled.",
        arrivals=(
            ExtraArrival(-1, "22:00", None,
                         "arrives at 22:00 the evening before - expected to fill this "
                         "day, on time"),
        ),
        # The day before keeps its own supply and nothing else lands on it.
        quiet=(-1,),
    ),
    Injection(
        scenario_id="TS-10b",
        dataset_id="birth-registrations",
        anchor=-90,
        config="daily evening-before, as TS-10a, but the day before never got a "
               "supply. Since REQ-PIPE-131 the 22:00 arrival still fills this day, on "
               "time, and the day before closes with nothing.",
        arrivals=(
            ExtraArrival(-1, "22:00", None,
                         "arrives at 22:00 the evening before - expected to fill this "
                         "day on time; the day before closes empty"),
        ),
        suppress=(-1,),
    ),
    # REQ-GEN-136 and 137 (sprint 11). Each is placed inside the setting era
    # it needs (contract/data-asset.yaml's synthetic versions; criterion 15),
    # and none shares a period with another. Shapes only: the severity is
    # what the generator puts into the rows, and the QA tools decide.
    #
    # TS-43 TO TS-46, PLANTED 2026-10-11 (REQ-GEN-184, REQ-GEN-185). Parked
    # on 2026-10-05 because nothing could make an amber supply - warnings
    # and no failure - or a resend that stayed green. Each is now BUILT TO A
    # TARGET from the checks' own bands, after green lead-ins and before a
    # green day, so its row count and drift are measured against what the
    # generator built. Each sits inside the setting era it needs
    # (contract/data-asset.yaml); TS-44 and TS-45 take one lead-in, because
    # the promote-and-acknowledge era is eight days with TS-2 and TS-1 in it.
    # The real tools still decide - REQ-GEN-186 checks they agreed.
    Injection(
        scenario_id="TS-43",
        dataset_id="birth-registrations",
        anchor=-21,
        config="daily; the amber setting is HOLD from 2026-08-30 (REQ-GEN-199). A scripted person "
               "promotes the held supply the next morning, twenty hours after it arrives "
               "and before that day's supply (REQ-GEN-185 criterion 7).",
        arrivals=(
            ExtraArrival(0, "14:00", None, "built to amber on facility nulls",
                         target=Target("amber", ("place_of_birth_facility.completeness",))),
        ),
    ),
    Injection(
        scenario_id="TS-44",
        dataset_id="birth-registrations",
        anchor=-13,
        lead_in=1,
        config="daily; PROMOTE-AND-ACKNOWLEDGE from 2026-09-10.",
        arrivals=(
            ExtraArrival(0, "14:00", None, "built to amber on parent 1 nulls",
                         target=Target("amber", ("registering_parent_1_name.completeness",))),
        ),
    ),
    Injection(
        scenario_id="TS-45",
        dataset_id="birth-registrations",
        anchor=-9,
        lead_in=1,
        config="as TS-44; a scripted acknowledgement five hours after receipt, once the "
               "rule has promoted it.",
        arrivals=(
            ExtraArrival(0, "14:00", None, "built to amber on parent 2 nulls",
                         target=Target("amber", ("registering_parent_2_name.completeness",))),
        ),
    ),
    Injection(
        scenario_id="TS-46",
        dataset_id="birth-registrations",
        # A WEEKDAY: its 16:00 resend is a resupply, and every resupply
        # arrives on a weekday (tests/test_generate_runs.py). 2026-09-21 is the
        # replacement era's Monday; its lead-in is the Sunday, and the day
        # after is the history's last.
        anchor=-5,
        lead_in=1,
        config="daily; the replacement setting is GREEN from 2026-09-18 to 2026-09-21. "
               "Two green supplies for one day, at 14:00 and 16:00.",
        arrivals=(
            ExtraArrival(0, "14:00", None, "the first supply, promoted",
                         target=Target("green")),
            ExtraArrival(0, "16:00", None, "the green resend that replaces it",
                         target=Target("green")),
        ),
    ),
    Injection(
        scenario_id="TS-47",
        dataset_id="birth-registrations",
        anchor=-19,
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
            # TS-14 (REQ-GEN-044 criterion 1, 2026-10-15): the corrected
            # Client Register, alone and weeks later - its own delivery, filed
            # to this quarter's still-empty slot, checked against the five
            # siblings already in place. 28 days: a Thursday, before the next
            # quarter's claim window opens.
            ExtraArrival(28, "10:00", None,
                          "the corrected cp_clients alone, weeks later - TS-14",
                          file_shape="one_table_only"),
        ),
        also_demonstrates=("TS-14",),
        # TS-12 is the refusal, so its link sits before the correction; TS-14
        # takes the placement's latest day, the correction's own.
        links=(Link("TS-12", 1, 0, 1),),
    ),
    Injection(
        scenario_id="TS-56",
        dataset_id="cp-carers",
        # -1, THE NEWEST QUARTER, MOVED FROM -8 on 2026-10-15 (Keith, REQ-GEN-207
        # criterion 3): -8 is the quarter TS-76 stands on, which the widened
        # collision rule now claims. Not back to -9: -9 is a red chain, and
        # replacing it removed the only knock-on re-evaluation (REQ-PIPE-121)
        # the generated history had - why it moved off -9 on 2026-10-05.
        anchor=-1,
        config="quarterly, Feb/May/Aug/Nov. cp_carers arrives with its columns in "
               "another order than the contract's; everything else as usual.",
        arrivals=(
            ExtraArrival(0, "09:00", None,
                          "all six tables, cp_carers' first two columns swapped - it "
                          "loads with a column-order warning",
                          file_shape="columns_reordered"),
        ),
    ),
    # EARLY ARRIVALS, AND ONE TOO EARLY (REQ-GEN-195, Keith 2026-10-12: "3 or
    # 4 plus one too early"). The quarterly calendar lets a supply arrive up
    # to 14 days before it is due (claim_window: 14d), and until then no
    # generated delivery ever did, so the window could not be seen working on
    # a real page. ON EMERGENCY DEPARTMENT SINCE REQ-GEN-235 (Keith,
    # 2026-10-15: they need nothing Child Protection has): each is one file,
    # in the same quarter at the same instant as when it was a whole Child
    # Protection delivery, and the too-early one after an ordinary quarter so
    # what it lands in is not another scenario. Shapes only; the assignment
    # rule decides.
    Injection(
        scenario_id="TS-9",
        dataset_id="ed-presentations",
        anchor=-10,
        config="quarterly, Feb/May/Aug/Nov, due 09:00 on the 1st, claim window 14 days. "
               "The supply arrives 9 days before the quarter's date, inside its window.",
        arrivals=(
            ExtraArrival(-9, "10:00", None,
                          "the supply, nine days early - inside the window"),
        ),
    ),
    Injection(
        scenario_id="TS-65",
        dataset_id="ed-presentations",
        anchor=-5,
        config="as TS-9. The window opens 14 days before 09:00 on the 1st; this supply "
               "arrives 13 days before, a day after it opened.",
        arrivals=(
            ExtraArrival(-13, "10:00", None,
                          "the supply, thirteen days early - just inside the window"),
        ),
    ),
    Injection(
        scenario_id="TS-66",
        dataset_id="ed-presentations",
        anchor=-4,
        config="as TS-9. The everyday case: a supplier who sends a couple of days ahead.",
        arrivals=(
            ExtraArrival(-2, "10:00", None, "the supply, two days early"),
        ),
    ),
    Injection(
        scenario_id="TS-67",
        dataset_id="ed-presentations",
        anchor=-12,
        config="as TS-9. The supply arrives 20 days before the quarter's date - six days "
               "before its window opens - so the quarter it was meant for is not yet "
               "open, and the previous quarter (an ordinary one) still is.",
        arrivals=(
            ExtraArrival(-20, "10:00", None,
                          "the supply, twenty days early - before its window"),
        ),
    ),
    # ONE DAY OUTSIDE A QUARTERLY CLAIM WINDOW (REQ-GEN-236, Keith 2026-10-15:
    # TS-3a and TS-3b move to Emergency Department). The quarterly window opens
    # 14 days before 09:00 on the quarter's 1st, so a supply 15 days before, at
    # 10:00, is a day short of it - the previous quarter is still the open one.
    # TS-3a leaves that quarter filled by its own supply; TS-3b suppresses it.
    # Shapes only: no resupply, late filing or verdict (REQ-GEN-044 criterion 6).
    Injection(
        scenario_id="TS-3a",
        dataset_id="ed-presentations",
        anchor=-6,
        config="quarterly, Feb/May/Aug/Nov, due 09:00 on the 1st, claim window 14 days. "
               "The previous quarter's supply arrived as usual; this one arrives 15 days "
               "before the quarter's date, a day before its window opens.",
        arrivals=(
            ExtraArrival(-15, "10:00", None,
                          "the supply, fifteen days early - a day before its window"),
        ),
    ),
    Injection(
        scenario_id="TS-3b",
        dataset_id="ed-presentations",
        anchor=-2,
        config="as TS-3a, but the previous quarter's supply never came.",
        arrivals=(
            ExtraArrival(-15, "10:00", None,
                          "the supply, fifteen days early - a day before its window"),
        ),
        suppress=(-1,),
    ),
    # WHAT A CONFIRMED CORRECTION DOES TO SUPPLIES ALREADY FILED (REQ-GEN-205,
    # REQ-GEN-237): five Emergency Department quarters of 2013-2015, each
    # riding the one correction REQ-GEN-205 declares on the quarterly calendar
    # (dated 2026-09-01, confirmed at the history's end as scripted). Offsets
    # count from each quarter's CORRECTED date, which is what the generator
    # reads; each arrival was filed against the agreement as it stood at its
    # receipt, before the correction. Shapes and instants only - the pipeline
    # files, judges, moves, holds and parks.
    Injection(
        scenario_id="TS-57a",
        dataset_id="ed-presentations",
        anchor=8,
        config="quarterly, due 09:00 with 8 hours' grace. 2015-Q1's date is corrected from 1 to 2 February 2015; its one supply arrives at 12:00 on 2 February - late against the old date, on time against the corrected one.",
        arrivals=(
            ExtraArrival(0, "12:00", None,
                         "the quarter's supply, at noon the day after the old date"),
        ),
        also_demonstrates=("TS-57b",),
        correction="REQ-GEN-205",
        # 'a' while the correction awaits confirmation, 'b' on the history's
        # last day, after the replay has confirmed it (REQ-GEN-205 criterion 12;
        # LAST_DAY follows the anchor, post-build-review #252).
        links=(Link("TS-57a", 7, correction_event("REQ-GEN-205"), HISTORY_END),
               Link("TS-57b", LAST_DAY, correction_event("REQ-GEN-205"), HISTORY_END)),
    ),
    Injection(
        scenario_id="TS-58a",
        dataset_id="ed-presentations",
        anchor=3,
        config="quarterly, 14-day claim window. 2013-Q4's date is corrected from 1 November to 20 October 2013; its supply arrives on 10 October, before the old window opened, so it was filed as a resupply of 2013-Q3 - and the corrected window covers it.",
        arrivals=(
            ExtraArrival(-10, "10:00", None,
                         "2013-Q4's supply, ten days before the corrected date"),
        ),
        also_demonstrates=("TS-58b",),
        correction="REQ-GEN-205",
        # 'a' while the correction awaits confirmation, 'b' on the history's
        # last day, after the replay has confirmed it (REQ-GEN-205 criterion 12;
        # LAST_DAY follows the anchor, post-build-review #252).
        links=(Link("TS-58a", 7, correction_event("REQ-GEN-205"), HISTORY_END),
               Link("TS-58b", LAST_DAY, correction_event("REQ-GEN-205"), HISTORY_END)),
    ),
    Injection(
        scenario_id="TS-59a",
        dataset_id="ed-presentations",
        anchor=6,
        config="quarterly, as TS-58: 2014-Q3's date is corrected from 1 August to 20 July 2014, its supply arriving on 10 July - filed as a resupply of 2014-Q2, which the corrected agreement would move, and which the asset manager keeps.",
        arrivals=(
            ExtraArrival(-10, "10:00", None,
                         "2014-Q3's supply, ten days before the corrected date"),
        ),
        also_demonstrates=("TS-59b",),
        correction="REQ-GEN-205",
        # 'a' while the correction awaits confirmation, 'b' on the history's
        # last day, after the replay has confirmed it (REQ-GEN-205 criterion 12;
        # LAST_DAY follows the anchor, post-build-review #252).
        links=(Link("TS-59a", 7, correction_event("REQ-GEN-205"), HISTORY_END),
               Link("TS-59b", LAST_DAY, correction_event("REQ-GEN-205"), HISTORY_END)),
    ),
    Injection(
        scenario_id="TS-60a",
        dataset_id="ed-presentations",
        anchor=0,
        config="quarterly, 14-day claim window. Emergency Department's first quarter, 2013-Q1, has its date corrected from 1 to 11 February 2013; its supply arrived on 22 January, inside the old window, before the corrected one opens and with no quarter before it - held, naming the correction.",
        arrivals=(
            ExtraArrival(-20, "10:00", None,
                         "the first quarter's supply, inside the old window only"),
        ),
        also_demonstrates=("TS-60b",),
        correction="REQ-GEN-205",
        # 'a' while the correction awaits confirmation, 'b' on the history's
        # last day, after the replay has confirmed it (REQ-GEN-205 criterion 12;
        # LAST_DAY follows the anchor, post-build-review #252).
        links=(Link("TS-60a", 7, correction_event("REQ-GEN-205"), HISTORY_END),
               Link("TS-60b", LAST_DAY, correction_event("REQ-GEN-205"), HISTORY_END)),
    ),
    Injection(
        scenario_id="TS-61a",
        dataset_id="ed-presentations",
        anchor=10,
        config="quarterly, 14-day claim window. 2015-Q3's date is corrected from 1 to 11 August 2015; its supply arrived on 22 July, which the corrected agreement files to 2015-Q2 - a move blocked because 2015-Q4, the participation gap (REQ-GEN-251), stands on it, so it is parked.",
        arrivals=(
            ExtraArrival(-20, "10:00", None,
                         "2015-Q3's supply, inside the old window only"),
        ),
        # 2015-Q4 owes nothing (REQ-GEN-251's gap) and is not one of the
        # generated periods, so nothing is suppressed here.
        also_demonstrates=("TS-61b",),
        correction="REQ-GEN-205",
        # 'a' while the correction awaits confirmation, 'b' on the history's
        # last day, after the replay has confirmed it (REQ-GEN-205 criterion 12;
        # LAST_DAY follows the anchor, post-build-review #252).
        links=(Link("TS-61a", 7, correction_event("REQ-GEN-205"), HISTORY_END),
               Link("TS-61b", LAST_DAY, correction_event("REQ-GEN-205"), HISTORY_END)),
    ),
    # A CORRECTION MERGED AND NOT YET CONFIRMED (REQ-GEN-205, TS-62): Birth
    # Registrations' claim window widens to six hours from 2026-09-25 - a new
    # version on the history's last day, after 2026-09-08 (criteria 24 and
    # 25) - by a correction dated 2026-09-24 that the scripted manager leaves
    # pending. 2026-09-25's own supply arrives at 09:00, which only the
    # corrected window lets claim it: judged against the merged configuration
    # while the correction waits (REQ-PIPE-170 criteria 20-21). Room for it
    # came from three days grown at the history's end (Keith, 2026-10-19).
    Injection(
        scenario_id="TS-62",
        dataset_id="birth-registrations",
        anchor=-1,
        config="daily, due 14:00 with 1 hour's grace; the claim window widens from 4 "
               "to 6 hours from 2026-09-25 by correction REQ-GEN-205-WINDOW, dated "
               "2026-09-24 and left awaiting confirmation. That day's supply arrives "
               "at 09:00 - inside the corrected window, which opens at 08:00, and "
               "outside the old one, which opened at 10:00.",
        arrivals=(
            ExtraArrival(0, "09:00", None,
                         "2026-09-25's supply, inside the six-hour window only"),
        ),
        correction="REQ-GEN-205-WINDOW",
        links=(Link("TS-62", 1, correction_event("REQ-GEN-205-WINDOW"), HISTORY_END),),
    ),
    # TWO FILES FOR ONE TABLE (REQ-GEN-196), one pair per way a person can
    # settle it (REQ-PIPE-193's choose-file). Each is ONE delivery whose two
    # files carry their own receipts, settled by a scripted person at 11:00
    # the next day (contract/scripted_decisions.yaml), so the arrival day
    # reads contested and the day after reads settled. Placed 28 July to 25
    # August WITH ORDINARY DAYS BETWEEN THEM (post-build-review #172, Keith):
    # packed into one block they left a late-July red's resends nowhere to
    # land for three weeks, and one turned TS-73's green following day red.
    # After the early-July days the ordinary reds move to
    # (_reds_clear_of_scenarios) and before TS-78's late-August days. Only a
    # file the script makes a supply is targeted (criterion 19).
    Injection(
        scenario_id="TS-68",
        dataset_id="birth-registrations",
        anchor=-60,
        config=_PAIR_CONFIG + " A duplicate send: the same extract twice, ten minutes "
               "apart, the duplicate's name sorting before the original's.",
        arrivals=(
            ExtraArrival(0, "13:40", note="one delivery, the day's extract sent twice",
                          files=(
                PairFile("13:40", "birth_registrations_{D}.csv",
                         target=Target("green"), note="the day's extract"),
                PairFile("13:50", "birth_registrations_{D}-1.csv", content="duplicate",
                         note="the same bytes again - kept, superseded"),
            )),
        ),
        lead_in=1,
    ),
    Injection(
        scenario_id="TS-69",
        dataset_id="birth-registrations",
        anchor=-55,
        config=_PAIR_CONFIG + " The next day's extract is sent early, in the same "
               "delivery as today's; the next day has no supply of its own.",
        arrivals=(
            ExtraArrival(0, "13:30", note="one delivery, today's extract and tomorrow's",
                          files=(
                PairFile("13:30", "birth_registrations_{D}.csv",
                         target=Target("green"), note="the day's extract"),
                PairFile("13:45", "birth_registrations_{D+1}.csv", content="next_day",
                         target=Target("green"),
                         note="the next day's extract, sent early - re-filed to it"),
            )),
        ),
        suppress=(1,),
        lead_in=1,
    ),
    Injection(
        scenario_id="TS-70",
        dataset_id="birth-registrations",
        anchor=-50,
        config=_PAIR_CONFIG + " The day's extract arrives on time with a fault, and a "
               "corrected re-export follows at 16:30 - after the grace, before the next "
               "day's window - named to sort first.",
        arrivals=(
            ExtraArrival(0, "13:40", note="one delivery, an extract and its correction",
                          files=(
                PairFile("13:40", "birth_registrations_{D}.csv", severity="red",
                         note="the day's extract, with a planted fault - rejected"),
                PairFile("16:30", "birth_registrations_{D}-resend.csv", content="corrected",
                         target=Target("green"),
                         note="the same extract with the fault fixed - the supply, late"),
            )),
        ),
        lead_in=1,
    ),
    Injection(
        scenario_id="TS-71",
        dataset_id="birth-registrations",
        anchor=-45,
        config=_PAIR_CONFIG + " A stray test file that loads arrives before the day's "
               "real extract.",
        arrivals=(
            ExtraArrival(0, "13:20", note="one delivery, a test file and the real extract",
                          files=(
                PairFile("13:20", "birth_registrations_{D}_TEST.csv",
                         shapes=("stray_test_rows",),
                         note="test rows that should never have been sent - rejected"),
                PairFile("13:40", "birth_registrations_{D}.csv",
                         target=Target("green"), note="the day's extract"),
            )),
        ),
        lead_in=1,
    ),
    Injection(
        scenario_id="TS-72",
        dataset_id="birth-registrations",
        anchor=-40,
        config=_PAIR_CONFIG + " The day's extract, then a stray test file the load "
               "refuses - named to sort first by bytes, second by the database's "
               "collation.",
        arrivals=(
            ExtraArrival(0, "13:30", note="one delivery, the real extract and a broken test file",
                          files=(
                PairFile("13:30", "birth_registrations_{D}.csv",
                         target=Target("green"), note="the day's extract"),
                PairFile("13:35", "birth_registrations_{D}-test.csv",
                         shapes=("stray_test_rows", "unreadable_file"),
                         note="test rows, ragged partway - never loads, rejected"),
            )),
        ),
        lead_in=1,
    ),
    Injection(
        scenario_id="TS-73",
        dataset_id="birth-registrations",
        anchor=-36,
        config=_PAIR_CONFIG + " A faulty extract and a stray test file; a person "
               "rejects both, and the day stays owed.",
        arrivals=(
            ExtraArrival(0, "13:20", note="one delivery, neither file usable",
                          files=(
                PairFile("13:20", "birth_registrations_{D}.csv", severity="red",
                         note="the day's extract, with a planted fault - rejected"),
                PairFile("13:40", "birth_registrations_{D}_TEST.csv",
                         shapes=("stray_test_rows",),
                         note="test rows - rejected"),
            )),
        ),
        green_follow=True,
    ),
    Injection(
        scenario_id="TS-74",
        dataset_id="birth-registrations",
        anchor=-32,
        config=_PAIR_CONFIG + " Tomorrow's extract sent early beside a stray test file, "
               "and nothing for today: the early file is re-filed, the test file "
               "rejected, and today stays owed.",
        arrivals=(
            ExtraArrival(0, "13:30", note="one delivery, tomorrow's extract and a test file",
                          files=(
                PairFile("13:30", "birth_registrations_{D+1}.csv", content="next_day",
                         target=Target("green"),
                         note="the next day's extract, sent early - re-filed to it"),
                PairFile("13:45", "birth_registrations_{D}_TEST.csv",
                         shapes=("stray_test_rows",),
                         note="test rows - rejected"),
            )),
        ),
        suppress=(1,),
        lead_in=1,
    ),
    # WHAT THE AS-AT PANEL AND QUALIFIER SAY ON A PAST DATE (REQ-GEN-199;
    # Keith, 2026-10-13): a real case of each thing REQ-DASH-197 and
    # REQ-DASH-198 word differently, each scenario with several moments as
    # LETTERED SIBLINGS sharing one placement, each sibling's link dated
    # between two of its events (REQ-GEN-201). Shapes and instants only - the
    # scripted person makes the decisions, the pipeline everything else.
    Injection(
        scenario_id="TS-75a",
        dataset_id="cp-clients",
        # A QUARTER WHOSE CLIENTS PERIOD HOLDS NOTHING ELSE when the held
        # supply arrives (criterion 3), so its reason is "awaiting a decision"
        # and not post-build-review #164's "superseded".
        anchor=-11,
        config="quarterly, Feb/May/Aug/Nov, due 09:00 on the 1st. The whole delivery "
               "arrives on time with cp_clients alone built to fail; a person rejects "
               "it three weeks later, and a corrected cp_clients follows a week after "
               "that, filling the quarter.",
        arrivals=(
            ExtraArrival(0, "09:00", "red",
                         "all six tables on time, cp_clients dirtied by its own red "
                         "preset and the other five clean",
                         severity_tables=("cp_clients",)),
            ExtraArrival(28, "10:00", None,
                         "the corrected cp_clients alone, a week after the rejection and "
                         "well before the next quarter's window",
                         file_shape="one_table_only"),
        ),
        also_demonstrates=("TS-75b",),
        links=(Link("TS-75a", 7, 0, "TS-75 reject", scenario_map.AS_AT_PANEL),
               Link("TS-75b", 3, "TS-75 reject", 1, scenario_map.AS_AT_PANEL)),
    ),
    # A DATASET TURNED OFF FOR A WHILE (REQ-GEN-218; TS-63): Carer Register
    # is turned off after 31 December 2021 by correction REQ-GEN-218, dated
    # 15 December, and back on for 2022-Q3 - a grown quarter (REQ-GEN-207),
    # so no planted scenario moves. Shapes and instants only: the filing rule
    # files the late one into 2021-Q4 and holds the gap's as turned off.
    Injection(
        scenario_id="TS-63a",
        dataset_id="cp-carers",
        anchor=-20,
        config="quarterly, Feb/May/Aug/Nov, due 09:00 on the 1st, 14-day claim window. "
               "cp-carers is turned off after 31 December 2021 by a correction dated 15 "
               "December 2021, and owed again from 2022-Q3. 2021-Q4's delivery leaves "
               "cp_carers out; cp_carers follows on 5 January 2022, after the turn-off but "
               "while 2021-Q4's slot is open; another arrives on 15 March 2022, in the gap.",
        arrivals=(
            ExtraArrival(0, "09:00", None,
                         "five of the six tables, on time - cp_carers.csv absent",
                         file_shape="carers_missing"),
            ExtraArrival(65, "10:00", None,
                         "cp_carers alone, after the effective_to, while 2021-Q4's slot is "
                         "still open - filed to 2021-Q4",
                         file_shape="carers_alone"),
            ExtraArrival(134, "10:00", None,
                         "cp_carers alone, inside the gap with no owed slot open - held "
                         "as turned off",
                         file_shape="carers_alone"),
        ),
        also_demonstrates=("TS-63b",),
        correction="REQ-GEN-218",
        # Indexed among the arrivals carrying cp_carers (carries()): 0 is the
        # January one, 1 the gap's.
        links=(Link("TS-63a", 5, correction_event("REQ-GEN-218"), 0),
               Link("TS-63b", 5, 1, HISTORY_END)),
    ),
    Injection(
        scenario_id="TS-76",
        dataset_id="cp-placements",
        # STANDS ON -8, TS-56's quarter, whose cp_placements is clean and
        # promoted (only cp_carers' columns are reordered there).
        anchor=-7,
        stands_on=-1,
        config="quarterly, as TS-75a. The delivery leaves cp_placements out; a person "
               "substitutes the quarter onto the previous one, and when the next "
               "quarter's window has opened removes the substitution and marks the "
               "quarter not supplied, at the same instant.",
        arrivals=(
            ExtraArrival(0, "09:00", None,
                         "five of the six tables, on time - cp_placements.csv absent",
                         file_shape="one_table_missing"),
        ),
        links=(Link("TS-76", 14, "TS-76 substitute", "TS-76 de-substitute",
                    scenario_map.SUBSTITUTION_DRILL_DOWN),
               # TS-54 (Keith, 2026-10-14, Q13): a period substituted onto an
               # earlier PROMOTED supply - TS-76's own, while it stands.
               Link("TS-54", 14, "TS-76 substitute", "TS-76 de-substitute",
                    scenario_map.SUBSTITUTION_DRILL_DOWN)),
        also_demonstrates=("TS-54",),
        keeps_drawn_severity=True,
    ),
    Injection(
        scenario_id="TS-77a",
        dataset_id="cp-placements",
        # STANDS ON -15, THE HISTORY'S FIRST QUARTER, which holds a clean
        # promoted cp_placements. Not -13, where TS-67's early delivery files
        # (criterion 28; Keith, 2026-10-13).
        anchor=-14,
        stands_on=-1,
        config="quarterly, as TS-75a. The delivery leaves cp_placements out and a "
               "person substitutes the quarter onto the previous one; cp_placements "
               "arrives on its own thirty-eight days later, waits a day, and the same person "
               "promotes it - which removes the substitution.",
        arrivals=(
            ExtraArrival(0, "09:00", None,
                         "five of the six tables, on time - cp_placements.csv absent",
                         file_shape="one_table_missing"),
            # 38 DAYS: a Thursday - every resupply arrives on a weekday.
            ExtraArrival(38, "10:00", None,
                         "cp_placements alone, late, before the next quarter's window",
                         file_shape="missing_table_late"),
        ),
        also_demonstrates=("TS-77b",),
        # `0` IS THE LATE FILE: the first delivery carries no cp_placements,
        # so it takes no supply index (carries()).
        links=(Link("TS-77a", 14, "TS-77 substitute", 0,
                    scenario_map.SUBSTITUTION_DRILL_DOWN),
               Link("TS-77b", 0, 0, "TS-77 promote", scenario_map.AS_AT_PANEL)),
        keeps_drawn_severity=True,
    ),
    # A CONTESTED CLIENT REGISTER IN CHILD PROTECTION (REQ-GEN-203): two
    # cp_clients files in one delivery contest the table (REQ-PIPE-202), and its
    # three readers' cross-table checks with it. TS-42's contest is ended by a
    # later file and TS-80's by a person - the two ways it can end, on the one
    # collection with cross-table readers. IN THE GROWN QUARTERS (REQ-GEN-207,
    # criterion 5), each drawn clean with clean neighbours, so no planted
    # scenario and no ordinary amber moves; 2021-Q4 to 2022-Q3 are TS-63's.
    # Each pair file carries its own receipt and the other tables share the
    # delivery's (criterion 2). Shapes and instants only (criterion 6).
    Injection(
        scenario_id="TS-42a",
        dataset_id="cp-clients",
        # 2019-Q4, its lead-in 2019-Q3 and following quarter 2020-Q1.
        anchor=-28,
        config="quarterly, Feb/May/Aug/Nov, due 09:00 on the 1st, claim window 14 days. "
               "2019-Q4's delivery carries the usual files and two Client Registers - "
               "cp_clients.csv at 08:30 and a re-export, cp_clients_v2.csv, at 08:40 whose "
               "rows differ - both before due; a clean cp_clients.csv follows alone on 29 "
               "November at 10:00, after due and before 2020-Q1's window opens.",
        arrivals=(
            ExtraArrival(0, "08:30", note="the quarter's delivery, its Client Register sent "
                                          "twice", files=(
                PairFile("08:30", "cp_clients.csv", table="cp_clients",
                         note="the quarter's Client Register"),
                PairFile("08:40", "cp_clients_v2.csv", content="re_export", table="cp_clients",
                         note="a re-export of it, its rows re-pulled - nobody can tell which "
                              "is right"),
            )),
            # 28 DAYS: a Friday, weeks before 2020-Q1's window opens on 18 January.
            ExtraArrival(28, "10:00", None,
                         "a clean cp_clients alone - it supersedes the pair",
                         file_shape="one_table_only", target=Target("green")),
        ),
        also_demonstrates=("TS-42b",),
        lead_in=1,
        # TS-42a ON THE PAIR'S ARRIVAL DAY, contested; TS-42b on the later
        # file's, the pair superseded by it (criterion 7).
        links=(Link("TS-42a", 0, 0, 1), Link("TS-42b", 0, 1, HISTORY_END)),
    ),
    Injection(
        scenario_id="TS-80",
        dataset_id="cp-clients",
        # 2020-Q4, its lead-in 2020-Q3 and following quarter 2021-Q1.
        anchor=-24,
        config="quarterly, Feb/May/Aug/Nov, due 09:00 on the 1st, claim window 14 days. "
               "2020-Q4's delivery carries the usual files and two Client Registers - a "
               "stray test file, cp_clients_TEST.csv, at 08:20 on the due day and the real "
               "cp_clients.csv at 08:30, both before 09:00; a person settles the pair at "
               "11:00 the next day, the test file rejected and the real extract the "
               "quarter's supply.",
        arrivals=(
            ExtraArrival(0, "08:20", note="the quarter's delivery, a test Client Register "
                                          "and the real one", files=(
                PairFile("08:20", "cp_clients_TEST.csv", table="cp_clients",
                         shapes=("stray_test_rows",),
                         note="test rows that should never have been sent - rejected"),
                PairFile("08:30", "cp_clients.csv", table="cp_clients",
                         target=Target("green"), note="the quarter's real Client Register"),
            )),
        ),
        lead_in=1,
        # ON THE PAIR'S ARRIVAL DAY, where it reads contested (REQ-GEN-196
        # criterion 5's rule for a settled pair); settled from the next.
        links=(Link("TS-80", 0, 0, "TS-80 settle"),),
    ),
    # WHAT THE PACKAGE GATE DECIDES, DECLARED (REQ-GEN-273 criterion 4; Keith,
    # 2026-10-22 and 2026-10-25): S1 green and S1 red, S2 strict as re-cast, the
    # S10 chain re-ordered and S14, each in a grown quarter drawn clean
    # (REQ-GEN-207), each stating every table of its period, and each declaring
    # its gate outcomes for the bootstrap to compare (criterion 3). S1's two sit
    # inside Child Protection's own 'green' replacement-setting era
    # (contract/data-asset.yaml, 2017-04-17 to 2017-10-18): a green resupply may
    # replace a promoted one only there.
    Injection(
        scenario_id="TS-81",
        dataset_id="cp-clients",
        anchor=-38,
        config="quarterly, Feb/May/Aug/Nov, due 09:00 on the 1st; Child Protection's "
               "replacement setting is green for 2017-Q2 and 2017-Q3. The quarter's five "
               "tables arrive on time, clean, and are promoted; two weeks later a zip of a "
               "clean Client Register and a Notifications red on its own data arrives, and "
               "a person rejects that Notifications three weeks after it.",
        arrivals=(
            ExtraArrival(0, "09:00", None,
                         "the quarter's five tables on time, clean - each promoted"),
            ExtraArrival(14, "10:00", "red",
                         "a zip of cp_clients, clean, and cp_notifications, red on its "
                         "own data", file_shape="clients_and_notifications",
                         severity_tables=("cp_notifications",)),
        ),
        gate_outcomes=(GateOutcome("cp-clients", 1, "promoted"),
                       GateOutcome("cp-notifications", 1, "held back")),
    ),
    Injection(
        scenario_id="TS-82",
        dataset_id="cp-clients",
        anchor=-37,
        config="as TS-81, the Client Register of the zip missing the five clients only "
               "the quarter's Notifications point at; a person rejects both files of the "
               "zip three weeks after it.",
        arrivals=(
            ExtraArrival(0, "09:00", None,
                         "the quarter's six tables on time, clean - each promoted"),
            ExtraArrival(14, "10:00", "red",
                         "a zip of cp_clients, short of five clients only Notifications "
                         "point at, and cp_notifications, red on its own data",
                         file_shape="clients_short_with_notifications",
                         severity_tables=("cp_notifications",)),
        ),
        gate_outcomes=(GateOutcome("cp-clients", 1, "held back", because="cp-notifications",
                                   rechecked=True),
                       GateOutcome("cp-notifications", 1, "held back")),
    ),
    Injection(
        scenario_id="TS-83",
        dataset_id="cp-clients",
        anchor=-41,
        config="quarterly, Feb/May/Aug/Nov, due 09:00 on the 1st. The quarter's six "
               "tables arrive together on time, the first supply of the quarter, the "
               "Client Register red on its own data and the other five clean; four weeks "
               "later a corrected Client Register and its three readers are resent.",
        arrivals=(
            ExtraArrival(0, "09:00", "red",
                         "the quarter's six tables on time, cp_clients red on its own "
                         "data and the other five clean", severity_tables=("cp_clients",)),
            # RESOLVED, so nothing it held back waits on later pages: the
            # supplier resends the Client Register and its three readers.
            ExtraArrival(28, "10:00", None,
                         "a corrected cp_clients and its three readers, resent together",
                         file_shape="clients_and_readers"),
        ),
        gate_outcomes=(GateOutcome("cp-clients", 1, "promoted"),
                       GateOutcome("cp-notifications", 1, "promoted"),
                       GateOutcome("cp-investigations", 1, "promoted"),
                       GateOutcome("cp-placements", 1, "promoted"),
                       GateOutcome("cp-clients", 0, "held back"),
                       GateOutcome("cp-notifications", 0, "held back", because="cp-clients",
                                   rechecked=True),
                       GateOutcome("cp-investigations", 0, "held back", rechecked=True),
                       GateOutcome("cp-placements", 0, "held back", rechecked=True),
                       GateOutcome("cp-carers", 0, "promoted"),
                       GateOutcome("cp-case-workers", 0, "promoted")),
    ),
    Injection(
        scenario_id="TS-84",
        dataset_id="cp-clients",
        anchor=-44,
        config="quarterly, Feb/May/Aug/Nov, due 09:00 on the 1st, 8 hours' grace. One "
               "delivery, the first of the quarter, each file its own receipt: Carer "
               "Register 08:30, Notifications 08:40, Placements 08:50, Investigations "
               "09:00, Client Register 09:20 - all clean.",
        arrivals=(
            ExtraArrival(0, "08:30", None,
                         "five tables, staggered: Carer Register 08:30, Notifications "
                         "08:40, Placements 08:50, Investigations 09:00, Client Register "
                         "09:20",
                         file_times=(("cp_notifications", "08:40"),
                                     ("cp_placements", "08:50"),
                                     ("cp_investigations", "09:00"),
                                     ("cp_clients", "09:20"))),
        ),
        gate_outcomes=(GateOutcome("cp-notifications", 0, "promoted"),
                       GateOutcome("cp-investigations", 0, "promoted"),
                       GateOutcome("cp-placements", 0, "promoted"),
                       GateOutcome("cp-clients", 0, "promoted"),
                       GateOutcome("cp-carers", 0, "promoted")),
    ),
    Injection(
        scenario_id="TS-85",
        dataset_id="cp-placements",
        # 2016-Q1: 2015-Q2, its first quarter, is emptied by Emergency
        # Department's correction, so nothing was written there.
        anchor=-43,
        config="quarterly, Feb/May/Aug/Nov, due 09:00 on the 1st. The quarter's six "
               "tables arrive together on time, the first supply of the quarter, "
               "Placements red on its own data and the other five clean; four weeks later "
               "a corrected Placements is resent alone.",
        arrivals=(
            ExtraArrival(0, "09:00", "red",
                         "the quarter's six tables on time, cp_placements red on its own "
                         "data and the other five clean", severity_tables=("cp_placements",)),
            # RESOLVED: a corrected Placements alone, which the rule promotes.
            ExtraArrival(28, "10:00", None, "a corrected cp_placements alone",
                         file_shape="missing_table_late"),
        ),
        gate_outcomes=(GateOutcome("cp-placements", 1, "promoted"),
                       GateOutcome("cp-placements", 0, "held back"),
                       GateOutcome("cp-clients", 0, "promoted"),
                       GateOutcome("cp-notifications", 0, "promoted"),
                       GateOutcome("cp-investigations", 0, "promoted"),
                       GateOutcome("cp-carers", 0, "promoted"),
                       GateOutcome("cp-case-workers", 0, "promoted")),
    ),
    Injection(
        scenario_id="TS-78a",
        dataset_id="birth-registrations",
        # D = 30 AUGUST, inside the hold era that now starts that day
        # (contract/data-asset.yaml; Keith, 2026-10-13). Refused, never
        # shifted, if the era stops covering D to D+2 (criterion 15).
        anchor=-27,
        covers=2,
        hold_days=(0, 1, 2),
        quiet=(0, 1, 2, 3),
        config="daily; the amber setting is HOLD from 2026-08-30. D's supply is amber "
               "and held; D+1's is green and promoted by the rule; a person promotes "
               "D's into D at 20:00 on D+1. D+2's is amber and held, and the person "
               "promotes it at 10:00 on D+3, before D+3's own supply.",
        arrivals=(
            ExtraArrival(0, "14:00", None, "D's supply, built to amber on parent 1 nulls",
                         target=Target("amber", ("registering_parent_1_name.completeness",))),
            ExtraArrival(1, "14:00", None, "D+1's supply, built green",
                         target=Target("green")),
            ExtraArrival(2, "14:00", None, "D+2's supply, built to amber on parent 2 nulls",
                         target=Target("amber", ("registering_parent_2_name.completeness",))),
        ),
        also_demonstrates=("TS-78b",),
        links=(Link("TS-78a", 0, "TS-78 promote D", 2, scenario_map.AS_AT_PANEL),
               Link("TS-78b", 0, 2, "TS-78 promote D+2", scenario_map.VERDICT_LINE)),
    ),
)

for _injection in INJECTIONS:
    if _injection.also_demonstrates:
        _ALSO[_injection.scenario_id] = _injection.also_demonstrates
