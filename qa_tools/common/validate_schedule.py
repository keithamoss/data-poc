"""Gate: the asset and schedule configuration cannot silently produce
zero slots (REQ-PIPE-050).

ONE SENTENCE HOLDS THIS WHOLE MODULE TOGETHER, and a new check here
should be justified against it rather than added because it is
checkable: every rule below exists to stop a configuration error
SILENTLY PRODUCING ZERO SLOTS. That is the exhausted-schedule state
arriving by accident, on a dataset nobody is watching, and it looks
exactly like a dataset with nothing wrong - green, quiet, and expecting
nothing for a year because somebody wrote Febuary.

WHY A MISTYPED KEY IS AS SERIOUS AS A MISTYPED VALUE, and the reason
`extra="forbid"` is load-bearing rather than tidy: a silently-dropped
`delivery_months` key gives a dataset all four quarterly dates when its
author meant two. Nothing fails, the dashboard shows twice the expected
supplies, and every one of the extra ones is overdue forever. A wrong
value at least has a chance of looking wrong.

SCHEMA FIRST, THEN CROSS-REFERENCES, the same split
validate_requirements.py already uses: pydantic says what SHAPE the
file has (required keys, closed vocabularies, no unknown keys), and
this module answers the questions no schema can - does this dataset's
calendar exist, does the month it names have a date, does it agree with
the contract that describes it.

WHAT THIS DELIBERATELY DOES NOT DO:

  - Runway. Thread K listed "this schedule runs out in two periods" as
    this gate's one warning, and it is not here. Runway is measured in
    SLOTS, slots do not exist until REQ-PIPE-052, and it belongs to
    REQ-PIPE-053. Failing an otherwise-fine build on runway is also
    how a gate gets turned off.
  - Anything under data/. Config only, which is what makes it safe in
    CI under the standing rule, and what keeps it in the fast group of
    `mothman check` rather than joining the slow tail.
  - Coercion. A claim window is `14d` or it is an error; it is never
    silently read as 14 days. Four ways to write one duration is four
    ways for thirty datasets' config to read differently for no gain.
"""
from __future__ import annotations

import functools
import os
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

import yaml

from qa_tools.common import asset_time, period_schema, schedule
from qa_tools.common.diff_base import diff_base
from qa_tools.common.schemas import DataAsset

ROOT = Path(__file__).resolve().parent.parent.parent
CONTRACT_DIR = ROOT / "contract"

#: Set by `mothman check` to say "you may tell me about a warning".
#: Named here, beside the gate that emits it, and imported by the two
#: callers rather than spelled out three times.
WARNING_EXIT_VAR = "MOTHMAN_GATE_WARNING_EXIT"
DATA_ASSET_YAML = CONTRACT_DIR / "data-asset.yaml"

_MONTHS = ("January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December")


@dataclass(frozen=True)
class Source:
    """Where the configuration being validated lives.

    Passed explicitly rather than read off module globals a test
    monkeypatches. This gate reads two things - the asset file and the
    contracts beside it - and a test that redirected one and not the
    other would validate a temporary hierarchy against the real
    contracts and report nonsense.
    """

    asset_path: Path
    contract_dir: Path
    #: contract/calendar.yaml beside the asset file unless given (REQ-PIPE-110).
    calendar_path: Path | None = None

    @property
    def name(self) -> str:
        return self.asset_path.name

    @property
    def agreement_path(self) -> Path:
        return self.calendar_path or self.asset_path.parent / "calendar.yaml"

    @property
    def calendar_name(self) -> str:
        return self.agreement_path.name

    @classmethod
    def default(cls) -> "Source":
        return cls(DATA_ASSET_YAML, CONTRACT_DIR)


@dataclass(frozen=True)
class ConfigError:
    """One offending item, with somewhere to file it.

    `scope` is what the reader has to go and open - a calendar or a
    dataset - because at thirty datasets "there is an error in
    data-asset.yaml" is not a location. `fix` is separate from
    `problem` on purpose: naming the rule that was broken leaves the
    reader to work out what to type, and a gate that interrupts a build
    owes them better than that.
    """

    file: str
    scope: str | None
    problem: str
    fix: str

    # ONE MISTAKE, REPORTED N TIMES, IS STILL ONE MISTAKE
    # (plans/post-build-review.md #19). `cause` groups errors that share
    # a single root - a calendar renamed by one character produces one
    # error per dataset on it - so _report() can say what the root is
    # ABOVE the detail. It suppresses nothing: every offending item is
    # still printed individually and the header count is unchanged,
    # which is Keith's own rule from 2026-09-23. `cause_hint` carries
    # the one extra sentence that names a likely fix, resolved where the
    # configuration is in scope rather than at print time.
    cause: str | None = None
    cause_hint: str | None = None

    # WHICH DATASETS THIS BREAKS, for the header count. A calendar-
    # scoped error used to contribute ZERO to it, however many datasets
    # named that calendar - so a renamed calendar reported "affecting 1
    # dataset(s)" with seven of seven broken, which is the
    # safe-looking direction (post-build-review #18). Structural rather
    # than parsed back out of `scope`, same reasoning as `cause`.
    #
    # Empty is meaningful: an error about the asset's own top-level
    # configuration affects no NAMED dataset, and _report says so in
    # words instead of inventing a number.
    affects: tuple[str, ...] = ()

    # THE EXACT VALUE THIS IS ABOUT, as a dotted path, so the schema
    # layer and the semantic layer can be seen to be talking about the
    # same thing. `claim_window: 14` used to produce one error from
    # each, two lines apart, the same version 0-indexed and 1-indexed
    # (post-build-review #20). None means "not about one value".
    field: str | None = None

    #: Which check produced this - "schema" for the declared model,
    #: "semantic" for everything a shape cannot express. Only used to
    #: decide which of two reports about ONE value survives, and the
    #: semantic one always does.
    layer: str = "semantic"

    def __str__(self) -> str:
        return f"{self.problem} {self.fix}"


def _month_number(value) -> int | None:
    """A full English month name, or None.

    DELEGATES to `schedule.parse_month_name()` rather than mirroring
    it. It used to mirror it, and the two drifted in the way a mirror
    always eventually does: the runtime lowercased and this did
    `_MONTHS.index()` against title case, so `delivery_months:
    [february]` - honoured perfectly at runtime - was refused here with
    "which is not a month", plus a cascaded second error saying the
    dataset expected no supply at all (post-build-review #34).

    The gate's job is to refuse what the runtime cannot read. That is
    only true if it asks the runtime, so it asks.
    """
    if not isinstance(value, str):
        return None
    try:
        return schedule.parse_month_name(value, "month")
    except schedule.ScheduleConfigError:
        return None


#: What each key is meant to look like, for the fix line on a missing
#: or wrongly-typed value. The generated fixes used to read "Add it."
#: and "Correct the value.", naming no shape, no example and nowhere to
#: look - against this gate's own NFR that every error be one a human
#: can act on immediately (post-build-review #20). The hand-written
#: fixes in the same report were already the standard; this brings the
#: generated ones up to it.
_SHAPES: dict[str, str] = {
    "data_asset_id": "a short identifier for this data asset, like 'wa-health-quarterly'",
    "name": "the calendar's name, as datasets refer to it - like 'quarterly'",
    "effective_from": "the date this version starts applying, as YYYY-MM-DD - like 2027-01-01",
    "changelog": ("a list of entries, each a date, an author and the change - like "
                  "[{date: 2027-01-01, author: Jo Bloggs, change: authored 2027 dates}]"),
    "claim_window": "a duration with its unit, like 14d or 4h",
    "cadence_rule": "a cadence, currently only 'daily'",
    "dates": "a list of period/date pairs, like [{period: 2027-Q1, date: 2027-02-01}]",
    "period": "the period's name, like 2027-Q1",
    "date": "the date the supply is expected, as YYYY-MM-DD",
    "delivery_months": "a list of full month names, like [February, August]",
    "participates": "`all`, or a list of full month names, like [February, August]",
    "expected_time": "a 24-hour time of day, like 09:00 or 14:00",
    "days_before": "a whole number of days, 0 or more, like 1",
    "grace": "a duration with its unit, like 1h or 8h",
    "versions": "a list of versions, each with its own effective_from and changelog",
    "calendar": "the name of a calendar defined in this file",
    "arrival_pattern": ("a regular expression matching this dataset's own "
                         "delivered filenames, like 'cp_clients\\.csv' - single-quoted, "
                         "because YAML rejects a backslash escape in double quotes"),
    "table": "the physical table this dataset lands in",
    "contract": "the ODCS contract file covering this collection",
    "id": "a stable identifier, lowercase with hyphens",
}


def _shape_of(loc: list[str]) -> str | None:
    """The expected shape for a pydantic location, by its last named
    segment - the indices in between say where, not what."""
    for part in reversed(loc):
        if not part.isdigit() and part in _SHAPES:
            return _SHAPES[part]
    return None


def _duration_error(value, what: str) -> str | None:
    """Why this is not a usable duration, or None if it is."""
    try:
        parsed = schedule.parse_duration(value, what)
    except schedule.ScheduleConfigError:
        return (f"is {value!r}, which is not a duration with a unit.")
    if parsed.total_seconds() < 0:
        return f"is {value!r}, which is negative."
    return None


# ---- schema ---------------------------------------------------------

#: Keys the delivery agreement used to carry, and what replaced each
#: (REQ-PIPE-110 criteria 14, 16 and 28). Named rather than left to the
#: schema's generic "not a key", so the refusal says where the fact lives now.
RETIRED_KEYS = {
    "delivery_months": "participates, on the dataset's participation in contract/calendar.yaml",
    "owes_from": "the effective_from of the dataset's first participation version in "
                 "contract/calendar.yaml",
}


def _retired_key_errors(docs: list[tuple[dict, str]]) -> list[ConfigError]:
    """delivery_months or owes_from stated ANYWHERE, in either file, refused
    by name with what replaced it."""
    out: list[ConfigError] = []

    def walk(node, file_name, path):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in RETIRED_KEYS:
                    out.append(ConfigError(
                        file_name, None,
                        f"{'.'.join(path + [key])} states `{key}`, which no longer exists.",
                        f"Write it as {RETIRED_KEYS[key]}.", field=".".join(path + [key]),
                        layer="semantic"))
                walk(value, file_name, path + [str(key)])
        elif isinstance(node, list):
            for i, value in enumerate(node):
                walk(value, file_name, path + [str(i)])
    for doc, file_name in docs:
        walk(doc, file_name, [])
    return out


def _schema_errors(raw: dict, src: Source, model=None, file_name: str | None = None) -> list[ConfigError]:
    """Shape, via the declared model. Every pydantic error is rewritten
    with somewhere to file it and something to do about it - the raw
    location path is accurate and unreadable."""
    from pydantic import ValidationError

    model = model or DataAsset
    file_name = file_name or src.name
    try:
        model.model_validate(raw)
    except ValidationError as exc:
        out = []
        for err in exc.errors():
            loc = [str(p) for p in err["loc"]]
            if err["type"] == "extra_forbidden" and loc and loc[-1] in RETIRED_KEYS:
                continue  # refused by name, with its replacement, by _retired_key_errors
            scope = _scope_from_loc(raw, err["loc"])
            where = " -> ".join(loc) or "(top level)"
            field = ".".join(loc) or None
            shape = _shape_of(loc)
            if err["type"] == "extra_forbidden":
                out.append(ConfigError(
                    file_name, scope,
                    f"{where} is not a key this configuration has.",
                    "Remove it, or correct the spelling - an unknown key is accepted "
                    "nowhere here precisely because a dropped one is invisible.",
                    field=field, layer="schema"))
            elif err["type"] == "missing":
                out.append(ConfigError(
                    file_name, scope,
                    f"{where} is required and is not there.",
                    f"Add it: {shape}." if shape
                    else "Add it - see the other entries at this level for the form.",
                    field=field, layer="schema"))
            else:
                out.append(ConfigError(
                    file_name, scope,
                    f"{where}: {err['msg']}.",
                    f"Write {shape}." if shape
                    else "Correct the value - see the other entries at this level "
                         "for the form.",
                    field=field, layer="schema"))
        return out
    return []


def _scope_from_loc(raw: dict, loc: tuple) -> str | None:
    """The calendar or dataset a pydantic location sits inside.

    Resolved from the raw document rather than the model, because the
    model did not validate - that is why there is an error.
    """
    parts = list(loc)
    if parts and parts[0] == "datasets" and len(parts) > 1 and isinstance(parts[1], int):
        entries = raw.get("datasets") or []
        if parts[1] < len(entries):
            return f"dataset {(entries[parts[1]] or {}).get('id')!r}"
    if parts and parts[0] == "calendars" and len(parts) > 1 and isinstance(parts[1], int):
        entries = raw.get("calendars") or []
        if parts[1] < len(entries):
            name = (entries[parts[1]] or {}).get("name")
            return f"calendar {name!r}" if name else f"calendar #{parts[1] + 1}"
    if parts and parts[0] == "hierarchy":
        for dataset, _ in _walk_datasets(raw):
            pass
        # The dataset index path is agencies -> N -> collections -> M ->
        # datasets -> K; resolved positionally rather than by guessing.
        try:
            agency = (raw["hierarchy"]["agencies"])[parts[2]]
            collection = agency["collections"][parts[4]]
            dataset = collection["datasets"][parts[6]]
            return f"dataset {dataset.get('id')!r}"
        except (KeyError, IndexError, TypeError):
            return None
    return None


def _walk_datasets(raw: dict):
    """(dataset dict, collection dict) for every dataset in the raw
    document - used before the model has validated, so it cannot lean
    on hierarchy.py."""
    for agency in ((raw.get("hierarchy") or {}).get("agencies") or []):
        for collection in (agency.get("collections") or []):
            for dataset in (collection.get("datasets") or []):
                yield dataset, collection


# ---- calendars ------------------------------------------------------

def _calendar_errors(raw: dict, src: Source) -> list[ConfigError]:
    out: list[ConfigError] = []
    entries = raw.get("calendars") or []

    seen = Counter((c or {}).get("name") for c in entries)
    for name, count in seen.items():
        if name and count > 1:
            out.append(ConfigError(
                src.name, f"calendar {name!r}",
                f"is defined {count} times.",
                "Give each calendar one definition - a dataset naming this one "
                "cannot say which it meant."))

    for ci, entry in enumerate(entries):
        entry = entry or {}
        name = entry.get("name")
        scope = f"calendar {name!r}" if name else "calendar (unnamed)"
        versions = entry.get("versions") or []

        effective = []
        for i, version in enumerate(versions, start=1):
            version = version or {}
            when = version.get("effective_from")
            try:
                effective.append((date.fromisoformat(str(when)), i))
            except (TypeError, ValueError):
                out.append(ConfigError(
                    src.name, scope,
                    f"version {i}'s effective_from is {when!r}, which is not a date.",
                    "Write it as YYYY-MM-DD.",
                    field=f"calendars.{ci}.versions.{i - 1}.effective_from"))

            window = version.get("claim_window")
            if window is not None:
                problem = _duration_error(window, f"{scope} version {i} claim_window")
                if problem:
                    out.append(ConfigError(
                        src.name, scope,
                        f"version {i}'s claim_window {problem}",
                        "Write a duration with its unit, like 14d or 4h. This is never "
                        "guessed at - a bare number could mean either.",
                        field=f"calendars.{ci}.versions.{i - 1}.claim_window"))

            out.extend(_version_date_errors(scope, i, version, src))

        for (earlier, i), (later, j) in zip(effective, effective[1:]):
            if later <= earlier:
                out.append(ConfigError(
                    src.name, scope,
                    f"version {j} takes effect {later}, which is not after version {i}'s {earlier}.",
                    "Put the versions in effective_from order, oldest first, with no two "
                    "sharing a date - otherwise there is no single calendar in force."))
    return out


def _version_date_errors(scope: str, index: int, version: dict, src: Source) -> list[ConfigError]:
    out: list[ConfigError] = []
    dates = version.get("dates") or []
    cadence = version.get("cadence")

    if not dates and not cadence:
        out.append(ConfigError(
            src.name, scope,
            f"version {index} has neither authored `dates:` nor a `cadence:` rule.",
            "Give it one or the other. A version that generates no periods means every "
            "dataset on this calendar expects nothing."))
    if dates and cadence:
        out.append(ConfigError(
            src.name, scope,
            f"version {index} has BOTH authored `dates:` and a `cadence:` rule.",
            "Keep one. Two sources for the same period list is two answers that can "
            "disagree."))

    periods = Counter()
    days = Counter()
    for entry in dates:
        entry = entry or {}
        name, when = entry.get("period"), entry.get("date")
        if name:
            periods[name] += 1
        try:
            days[date.fromisoformat(str(when))] += 1
        except (TypeError, ValueError):
            out.append(ConfigError(
                src.name, scope,
                f"version {index} period {name!r} has date {when!r}, which is not a date.",
                "Write it as YYYY-MM-DD."))

    for name, count in periods.items():
        if count > 1:
            out.append(ConfigError(
                src.name, scope,
                f"version {index} names period {name!r} {count} times.",
                "Give each period one date - a supply filed against this one could "
                "answer for either."))
    for day, count in days.items():
        if count > 1:
            out.append(ConfigError(
                src.name, scope,
                f"version {index} carries the date {day} {count} times.",
                "Remove the duplicate - two periods due the same day cannot be told apart "
                "by an arrival."))

    # TWO NAMES, ONE SCHEMA. A period's schema is its name normalised
    # (period_schema.py), which is not injective: "2026-Q3", "2026 q3"
    # and "2026_Q3" all become period_2026_q3. That used to be
    # impossible because the name was hex-encoded, and the encoding was
    # dropped on 2026-09-27 for legibility - this check is what replaced
    # it, and it is the reason dropping it was safe. Caught here, in the
    # calendar somebody just edited; missed here, it merges two periods'
    # promoted data with nothing to notice.
    for schema, names in period_schema.collisions_in(periods).items():
        out.append(ConfigError(
            src.name, scope,
            f"version {index} names {' and '.join(repr(n) for n in names)}, "
            f"which would share one schema ({schema}).",
            "Rename one so they differ by more than case or punctuation - two "
            "periods in one schema means promoted data merged with nothing to "
            "notice."))
    return out


# ---- datasets -------------------------------------------------------

def _dataset_errors(raw: dict, src: Source) -> list[ConfigError]:
    out: list[ConfigError] = []
    calendars = {(c or {}).get("name"): (c or {}) for c in (raw.get("calendars") or [])}

    # ONLY SUGGEST A CALENDAR SOMETHING ALREADY USES (#19). The fix line
    # used to list every defined calendar, which meant that after a
    # one-character rename it offered the TYPO as a valid option:
    # follow it literally, point six datasets at `quarterley`, and the
    # gate goes green with the misspelling committed. A calendar no
    # dataset references is either brand new or a typo, and neither is
    # something to steer a broken dataset at.
    #
    # Falls back to listing everything when nothing is referenced at
    # all - a first dataset being added to a fresh asset - because there
    # is then no usage signal to prefer one by, and an empty list helps
    # nobody.
    in_use = {(d or {}).get("calendar") for d, _c in _walk_datasets(raw)
              if (d or {}).get("calendar") in calendars}
    options = ", ".join(sorted(n for n in (in_use or set(calendars)) if n))

    # The one defined calendar nothing references, when there is exactly
    # one, is the likely other half of a rename. More than one and there
    # is nothing to point at, so nothing is claimed.
    unreferenced = sorted(n for n in calendars if n and n not in in_use)
    typo_hint = (f" The calendar {unreferenced[0]!r} is defined and no dataset names it - "
                 f"if that is the typo, one edit there fixes them all."
                 if len(unreferenced) == 1 else "")

    for dataset, _collection in _walk_datasets(raw):
        dataset = dataset or {}
        dataset_id = dataset.get("id")
        scope = f"dataset {dataset_id!r}"
        named = dataset.get("calendar")
        declared_none = dataset.get(schedule.NO_CALENDAR_KEY)

        # A DATASET MAY SAY IT HAS NO CALENDAR, DELIBERATELY (REQ-PIPE-106
        # criterion 2) - and only deliberately. This branch is what lets
        # the gate below keep failing on a mere omission, which is the
        # requirement's own second NFR: without that, a typo'd calendar
        # name leaves a dataset silently expecting nothing, and a dataset
        # expecting nothing never reports a missing supply.
        if declared_none is not None:
            if declared_none not in schedule.NO_CALENDAR_VALUES:
                out.append(ConfigError(
                    src.name, scope,
                    f"declares `{schedule.NO_CALENDAR_KEY}: {declared_none!r}`, which is not "
                    f"one of {', '.join(schedule.NO_CALENDAR_VALUES)}.",
                    f"`{schedule.NOT_YET_AGREED}` is sample data before a schedule is agreed, "
                    f"and it will graduate. `{schedule.NEVER}` is a one-off extraction that "
                    f"has supplies and no cadence at all."))
            elif named:
                out.append(ConfigError(
                    src.name, scope,
                    f"declares BOTH `calendar: {named}` and "
                    f"`{schedule.NO_CALENDAR_KEY}: {declared_none}`.",
                    "Keep one. A dataset either has an agreed schedule or says it has none, "
                    "and carrying both leaves no way to tell which was meant."))
            elif dataset.get("delivery_months") or dataset.get("dates"):
                out.append(ConfigError(
                    src.name, scope,
                    f"declares `{schedule.NO_CALENDAR_KEY}: {declared_none}` and still "
                    f"subsets or overrides a calendar.",
                    "`participates:` and `dates:` both describe which of a calendar's "
                    "periods this dataset takes part in, and there is no calendar here to "
                    "take part in."))
            continue

        if not named:
            out.append(ConfigError(
                src.name, scope,
                f"is in {DATA_ASSET_YAML.name}'s hierarchy and names no `calendar:` in "
                f"{src.calendar_name} - "
                f"neither on the dataset nor on its collection - and no deliberate no-calendar "
                f"declaration.",
                f"In {src.calendar_name}, name one of: {options} on the dataset or its "
                f"collection, or declare "
                f"`{schedule.NO_CALENDAR_KEY}: {schedule.NOT_YET_AGREED}` if no schedule has "
                f"been agreed for it yet (or `{schedule.NEVER}` for a one-off extraction). "
                f"Without either there is nothing to judge this dataset's supplies against, "
                f"and a typo'd calendar name would leave it silently expecting nothing."))
            continue
        if named not in calendars:
            out.append(ConfigError(
                src.name, scope,
                f"names calendar {named!r}, which this asset does not define.",
                f"Use one of: {options}, or add that "
                f"calendar. A dataset on a calendar that does not exist expects nothing.",
                cause=f"unknown-calendar:{named}",
                cause_hint=typo_hint))
            continue

        months = dataset.get("delivery_months")
        overrides = dataset.get("dates")

        if months and overrides:
            out.append(ConfigError(
                src.name, scope,
                "carries BOTH a `participates:` list and its own `dates:`.",
                "Keep one. Subsetting a calendar and replacing it are different acts, and "
                "carrying both leaves no way to tell which was meant."))

        # Months are checked per participation version, against the calendar
        # versions each overlaps, in _participation_errors (REQ-PIPE-110
        # criterion 7) - not here on the newest version alone.

        if overrides is not None and not overrides:
            out.append(ConfigError(
                src.name, scope,
                "has a `dates:` key with nothing in it.",
                "Remove the key to use the calendar's own dates, or author real ones. As "
                "written this dataset expects nothing."))
        if months is not None and not months:
            out.append(ConfigError(
                src.name, scope,
                "has a `participates:` list with nothing in it.",
                "Write `participates: all` to take every period, or name the months. As written this "
                "dataset expects nothing."))
    return out


def _month_errors(scope: str, calendar_name: str, calendar: dict, months, src: Source) -> list[ConfigError]:
    if not months or not isinstance(months, list):
        return []
    out: list[ConfigError] = []

    versions = calendar.get("versions") or []
    rule_driven = any((v or {}).get("cadence") for v in versions)
    if rule_driven:
        out.append(ConfigError(
            src.name, scope,
            f"names delivery months under `participates:` against {calendar_name!r}, which is a cadence RULE "
            f"rather than an authored date list.",
            "Write `participates: all`. A rule-driven calendar has no months to pick from, and "
            "a dataset that 'participates in February' of a daily feed is asking for "
            "something the model cannot honour."))
        return out

    available = set()
    for version in versions:
        for entry in ((version or {}).get("dates") or []):
            try:
                available.add(date.fromisoformat(str((entry or {}).get("date"))).month)
            except (TypeError, ValueError):
                continue

    for value in months:
        number = _month_number(value)
        if number is None:
            out.append(ConfigError(
                src.name, scope,
                f"names {value!r} under `participates:`, which is not a month.",
                f"Write the full English month name - one of: {', '.join(_MONTHS)}."))
        elif available and number not in available:
            out.append(ConfigError(
                src.name, scope,
                f"names month {value!r} under `participates:`, which calendar {calendar_name!r} has no "
                f"date in.",
                f"Use a month the calendar actually carries "
                f"({', '.join(_MONTHS[m - 1] for m in sorted(available))}), or author a date "
                f"for this one. As written this dataset expects nothing in {value}."))
    return out


def _expects_nothing_errors(raw: dict, src: Source) -> list[ConfigError]:
    """The organising sentence, asked DIRECTLY rather than inferred from
    the specific rules above.

    Every other check here catches one way a dataset ends up expecting
    nothing. This one derives what it actually expects and says so if
    the answer is nothing at all - which catches the combinations no
    single rule does: months that are all real and all on the calendar
    but all excluded by `not_expected`, a calendar version whose dates
    were emptied, a subset that survives every individual check and
    intersects with nothing.

    Deliberately the LAST check, and deliberately silent when an
    earlier one already fired for the same dataset: a dataset naming a
    calendar that does not exist expects nothing, and saying so twice
    is two errors for one mistake.
    """
    out: list[ConfigError] = []
    calendars = {(c or {}).get("name"): (c or {}) for c in (raw.get("calendars") or [])}

    for dataset, _collection in _walk_datasets(raw):
        dataset = dataset or {}
        dataset_id = dataset.get("id")
        calendar = calendars.get(dataset.get("calendar"))
        if not dataset_id or calendar is None:
            continue  # already reported, with a better message than this one

        versions = calendar.get("versions") or []
        if any((v or {}).get("cadence") for v in versions):
            continue  # a rule generates a period every day; it cannot be empty

        own = dataset.get("dates")
        if own:
            periods = {(e or {}).get("period") for e in own}
        else:
            months = dataset.get("delivery_months")
            wanted = {n for n in (_month_number(m) for m in (months or [])) if n}
            periods = set()
            for version in versions:
                for entry in ((version or {}).get("dates") or []):
                    entry = entry or {}
                    try:
                        when = date.fromisoformat(str(entry.get("date")))
                    except (TypeError, ValueError):
                        continue
                    if not months or when.month in wanted:
                        periods.add(entry.get("period"))

        excluded = {(e or {}).get("period") for e in (dataset.get("not_expected") or [])}
        remaining = {p for p in periods if p and p not in excluded}
        if not remaining:
            out.append(ConfigError(
                src.name, f"dataset {dataset_id!r}",
                "expects no supply in any period at all.",
                "Something in this dataset's calendar, participation, dates or "
                "not_expected leaves nothing behind. A dataset expecting nothing sits "
                "green forever - which is the exhausted-schedule state arriving by "
                "accident."))
    return out


# ---- the contracts on the other side --------------------------------

def _contract_errors(raw: dict, src: Source) -> list[ConfigError]:
    """Criterion 9 - a dataset with no contract, and a contract with no
    dataset. At thirty datasets this is the check that justifies one
    calendar over thirty date lists, because it is the one a typo hides
    behind indefinitely."""
    out: list[ConfigError] = []
    declared: dict[str, str] = {}

    for dataset, collection in _walk_datasets(raw):
        filename = (collection or {}).get("contract")
        collection_id = (collection or {}).get("id")
        scope = f"dataset {(dataset or {}).get('id')!r}"
        if not filename:
            out.append(ConfigError(
                src.name, scope,
                f"sits in collection {collection_id!r}, which names no `contract:`.",
                "Add the contract filename to the collection. Without it nothing can "
                "resolve which file describes this dataset's checks or its arrivals."))
            continue
        declared[filename] = collection_id
        if not (src.contract_dir / filename).exists():
            out.append(ConfigError(
                src.name, scope,
                f"sits in collection {collection_id!r}, whose contract {filename!r} does "
                f"not exist.",
                f"Add contract/{filename}, or correct the name."))

    for path in sorted(src.contract_dir.glob("*.yaml")):
        if path.name == src.name or path.name in declared:
            continue
        try:
            doc = yaml.safe_load(path.read_text()) or {}
        except yaml.YAMLError:
            continue  # reported by the yamllint gate, not twice here
        if not isinstance(doc, dict) or doc.get("kind") != "DataContract":
            # DETECTED BY `kind: DataContract` (REQ-PIPE-110 criterion 32): it
            # used to be the presence of slaProperties, which this change
            # deletes - and that would have switched this check off silently.
            continue  # a checks file or similar, not a dataset contract
        out.append(ConfigError(
            path.name, None,
            "is a data contract that no collection in the hierarchy names.",
            "Add a `contract:` line to the collection it describes, or delete it. A "
            "contract nothing points at is checked by nothing."))

    out.extend(_sla_properties_errors(src))
    return out


def _sla_properties_errors(src: Source) -> list[ConfigError]:
    """An ODCS contract stating slaProperties is refused (REQ-PIPE-110
    criterion 16), and nothing is ever read from it: a dataset's cadence,
    expected time and grace live in contract/calendar.yaml, and a second
    copy nobody reads is a second copy somebody edits."""
    out: list[ConfigError] = []
    for path in sorted(src.contract_dir.glob("*.yaml")):
        try:
            doc = yaml.safe_load(path.read_text()) or {}
        except yaml.YAMLError:
            continue
        if isinstance(doc, dict) and "slaProperties" in doc:
            out.append(ConfigError(
                path.name, None,
                "states slaProperties, which no longer exist.",
                "Delete the block. A dataset's cadence, expected time and grace live on its "
                "participation in contract/calendar.yaml, and nothing reads them from a "
                "contract any more."))
    return out


# ---- a past date cannot move quietly --------------------------------

@functools.lru_cache(maxsize=8)
def _content_at(rel_path: str, ref: str) -> str | None:
    """The file's content at `ref`, or None if it was not there.

    The same one-file `git show` validate_check_lifecycle.py already
    runs, at the same `fetch-depth: 2` CI is already configured for -
    measured at about 3ms per read. That cost is the whole reason this
    guard exists at all: it was rejected on 2026-09-22 against an
    estimate based on a DEEP CLONE and a full history walk, which this
    is not, and reopened on 2026-09-23 once the cheap version was found
    to be already running in this repo.
    """
    result = subprocess.run(["git", "show", f"{ref}:{rel_path}"], cwd=ROOT,
                             capture_output=True, text=True)
    return result.stdout if result.returncode == 0 else None


def _version_added_on(rel_path: str, ref: str, start: str) -> date | None:
    """The day, on the asset's clock, the commit after `ref` that FIRST
    held an amber-setting version starting `start` was authored - the
    commit that introduced it, never an earlier commit in the same push
    that only touched the file (delivery critic on 8a942e7, M1). None where
    no commit holds it yet: the version is being added now, today."""
    from datetime import datetime

    from qa_tools.common import amber_setting

    result = subprocess.run(["git", "log", "--reverse", "--format=%H %aI", f"{ref}..HEAD",
                             "--", rel_path], cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        sha, _, stamp = line.partition(" ")
        content = _content_at(rel_path, sha)
        try:
            doc = yaml.safe_load(content or "") or {}
        except yaml.YAMLError:
            continue
        if not isinstance(doc, dict):
            continue
        # EITHER SETTING (REQ-PIPE-123 criterion 1): the replacement setting
        # is versioned by the same mechanism, so dated the same way.
        if any(start in amber_setting._versions(setting)
               for key in (amber_setting.KEY, "replacement_setting")
               for setting in amber_setting._settings(doc, key).values()):
            return asset_time.local_date(datetime.fromisoformat(stamp))
    return None


def _authored_dates(doc: dict) -> dict[tuple[str, str, str], str]:
    """{(calendar, effective_from, period): date} across every version.

    Keyed by the version too, because moving a date from one version to
    another is a legitimate act - authoring a new version is exactly how
    a schedule is meant to change - and only an edit WITHIN a version
    rewrites history.
    """
    out: dict[tuple[str, str, str], str] = {}
    for calendar in (doc.get("calendars") or []):
        calendar = calendar or {}
        name = calendar.get("name")
        for version in (calendar.get("versions") or []):
            version = version or {}
            effective = str(version.get("effective_from"))
            for entry in (version.get("dates") or []):
                entry = entry or {}
                period = entry.get("period")
                if name and period:
                    out[(str(name), effective, str(period))] = str(entry.get("date"))
    return out


def _changelog_at(doc: dict, calendar_name: str, effective: str) -> list:
    for calendar in (doc.get("calendars") or []):
        if (calendar or {}).get("name") != calendar_name:
            continue
        for version in ((calendar or {}).get("versions") or []):
            if str((version or {}).get("effective_from")) == effective:
                return list((version or {}).get("changelog") or [])
    return []


def _retrospective_edit_errors(raw: dict, src: Source, today: date | None = None,
                                ref: str | None = None) -> list[ConfigError]:
    """A date in the PAST that changed, without its version saying so.

    Thread E's rule is that config must never be edited to make red
    history disappear - move last February's agreed date forward and
    every supply that was late for it becomes on time, silently and
    retroactively. That rule was going to be enforced by review alone
    (Keith, 2026-09-22); he took the other option on 2026-09-23 once
    the cost turned out to be one `git show` rather than a deep clone.

    DELIBERATELY NARROW, because a gate that fires on legitimate work
    gets turned off:
      - Only dates already in the past. Next year's dates are meant to
        be edited; that is what `mothman schedule candidate-dates` is
        for.
      - Only within one version. Authoring a NEW effective-dated
        version is the sanctioned way to change a schedule, so a date
        that differs between versions is the mechanism working.
      - A NEW changelog entry on that version clears it. This is a
        "say what you did" gate, not a freeze - Thread E allows a
        correction, it just will not have one happen quietly. It has to
        be an ADDED line, not merely a different one: the guard used to
        accept any change to the list, so rewording an existing entry -
        or deleting one - licensed moving a past date, which is the
        opposite of what it is for. Same rule as the sibling gate's
        `find_undocumented_changes()`, which has always required the
        changelog to have grown (plans/post-build-review.md #44).
      - Silent when there is no previous commit to compare against,
        rather than failing. A shallow checkout or a first commit is
        not a finding.

    WHICH COMMIT "PREVIOUS" MEANS is `diff_base()`'s call, not this
    module's - see that module for the multi-commit hole both gates
    shared.
    """
    # The ASSET's clock, never the runner's. They are different
    # calendar dates for ~8 hours of every day (Perth is UTC+8), and
    # this function's whole job is deciding whether a date is in the
    # past - so a UTC runner would let through an edit to yesterday's
    # date for a third of the day, and only for pushes landing in that
    # window. Same class as plans/post-build-review.md #59.
    today = today or asset_time.local_date(asset_time.now())
    ref = ref or diff_base()
    # contract/calendar.yaml since REQ-PIPE-110. The commit that creates it
    # has no previous state to compare - the one commit this guard cannot
    # see, which is why the move is pinned instead (its NFRs 3 and 4).
    path = src.agreement_path
    previous = _content_at(str(path.relative_to(ROOT)), ref) \
        if path.is_relative_to(ROOT) else None
    if previous is None:
        return []
    try:
        old_doc = yaml.safe_load(previous) or {}
    except yaml.YAMLError:
        return []
    if not isinstance(old_doc, dict):
        return []

    was = _authored_dates(old_doc)
    now = _authored_dates(raw)
    out: list[ConfigError] = []

    for key, old_value in was.items():
        calendar_name, effective, period = key
        new_value = now.get(key)
        if new_value == old_value:
            continue
        try:
            when = date.fromisoformat(old_value)
        except ValueError:
            continue
        if when >= today:
            continue  # a future date is meant to be editable

        old_changelog = _changelog_at(old_doc, calendar_name, effective)
        new_changelog = _changelog_at(raw, calendar_name, effective)
        if len(new_changelog) > len(old_changelog):
            continue  # the version says what changed, which is all this asks

        what = f"is now {new_value}" if new_value else "has been removed"
        out.append(ConfigError(
            src.calendar_name, f"calendar {calendar_name!r}",
            f"period {period!r} was {old_value}, a date already in the past, and {what} - "
            f"with no new changelog entry on the version effective {effective}.",
            "Add a changelog entry saying what changed and why, or author a NEW "
            "effective-dated version instead. Moving a past date rewrites whether "
            "supplies already judged against it were on time."))
    return out


# ---- the amber setting's past is frozen (REQ-PIPE-122) --------------

def _replacement_setting_errors(raw: dict, src: Source, today: date | None = None,
                                ref: str | None = None) -> list[ConfigError]:
    """REQ-PIPE-123: the replacement setting's past is frozen by the amber
    setting's own guard, read under its key (criterion 1), and green-or-amber
    replacement is refused wherever the amber setting is hold, on any date
    the two overlap (criterion 11)."""
    from qa_tools.common import replacement_setting

    out = _amber_setting_errors(raw, src, today, ref, module=replacement_setting)
    return out + [ConfigError(
        src.name, f"replacement_setting ({where})", f"{problem}.",
        "Make the replacement setting green (or never) for those dates, or the amber "
        "setting promote or promote-and-acknowledge - by a NEW version of whichever you "
        "change, since a past version is frozen.")
        for where, problem in replacement_setting.conflicts(raw)]


def _amber_setting_errors(raw: dict, src: Source, today: date | None = None,
                          ref: str | None = None, module=None) -> list[ConfigError]:
    """Criteria 6 to 8: a version of the amber setting whose date has
    passed may not be altered or removed, WHATEVER CHANGELOG ACCOMPANIES
    IT - unlike a calendar date, there is no correction route, because a
    past setting re-judges nothing (every automatic promotion recorded the
    setting it acted under). A new version may not be dated before the
    day it is added, unless the asset declares itself synthetic - before
    AND after the change, so the declaration cannot be added in the same
    edit that uses it.

    Compared against `diff_base()`, the same previous commit the calendar
    guard above reads, and silent where there is none.
    """
    from qa_tools.common import amber_setting

    module = module or amber_setting
    key = module.KEY
    today = today or asset_time.local_date(asset_time.now())
    standing = [ConfigError(
        src.name, f"{key} ({where})", f"{problem}.",
        "Give each version its own effective_from, and keep a data-asset-level version "
        "in effect - there is no default.")
        for where, problem in module.standing_problems(raw, today)]
    ref = ref or diff_base()
    previous = _content_at(str(src.asset_path.relative_to(ROOT)), ref) \
        if src.asset_path.is_relative_to(ROOT) else None
    if previous is None:
        return standing
    try:
        old_doc = yaml.safe_load(previous) or {}
    except yaml.YAMLError:
        return standing
    if not isinstance(old_doc, dict):
        return standing
    synthetic = bool(old_doc.get("synthetic")) and bool(raw.get("synthetic"))
    problems = module.past_change_problems(old_doc, raw, today, synthetic=synthetic)
    if any("before the day it was added" in p for _, p in problems):
        # ONLY NOW ask git when it was added (criterion 7 as amended): a
        # version dated before today is the one case the commit's date can
        # change, and every other run keeps to the single `git show`.
        rel = str(src.asset_path.relative_to(ROOT))
        problems = module.past_change_problems(
            old_doc, raw, today, synthetic=synthetic,
            added=lambda start: _version_added_on(rel, ref, start))
    return standing + [ConfigError(
        src.name, f"{key} ({where})", f"{problem}.",
        "A setting's past is frozen - add a NEW version, dated today or later, with the "
        "value you want from then on. Nothing judged under the old version changes, "
        "because each promotion recorded the setting it acted under.")
        for where, problem in problems]


# ---- the delivery agreement, contract/calendar.yaml (REQ-PIPE-110) ----

def _merged_view(raw: dict, cal_raw: dict) -> dict:
    """The asset file with each dataset's agreement filled in from
    calendar.yaml, in the shape the calendar and dataset checks above read:
    its calendar (its own, else its collection's), its newest version's
    participates as `delivery_months`, not_expected, its own dates flattened,
    and its no-calendar declaration. A VIEW FOR CHECKING ONLY - nothing
    writes it back, and the two files stay the only statements."""
    import copy

    merged = copy.deepcopy(raw)
    merged["calendars"] = list(cal_raw.get("calendars") or [])
    by_dataset = {(d or {}).get("id"): (d or {}) for d in (cal_raw.get("datasets") or [])}
    by_collection = {(c or {}).get("id"): (c or {}) for c in (cal_raw.get("collections") or [])}
    for dataset, collection in _walk_datasets(merged):
        entry = by_dataset.get((dataset or {}).get("id"), {})
        own = entry.get("calendar")
        if entry.get(schedule.NO_CALENDAR_KEY) is not None:
            dataset[schedule.NO_CALENDAR_KEY] = entry[schedule.NO_CALENDAR_KEY]
            if own:
                dataset["calendar"] = own
        else:
            named = own or by_collection.get((collection or {}).get("id"), {}).get("calendar")
            if named:
                dataset["calendar"] = named
        versions = ((entry.get("participation") or {}).get("versions")) or []
        months = (versions[-1] or {}).get("participates") if versions else None
        if isinstance(months, list):
            dataset["delivery_months"] = months
        if entry.get("not_expected"):
            dataset["not_expected"] = entry["not_expected"]
        own_dates = [d for v in (((entry.get("dates") or {}).get("versions")) or [])
                     for d in ((v or {}).get("dates") or [])]
        if own_dates:
            dataset["dates"] = own_dates
    return merged


#: What a participation version may state, for the restate rule (criterion 33).
_RESTATED = ("participates", "reason", "expected_time", "grace", "claim_window", "days_before")


def _version_windows(versions: list[dict]) -> list[tuple[str, str | None]]:
    """(from, until-exclusive) as ISO strings for effective-dated versions
    in file order - the last open-ended."""
    starts = [str((v or {}).get("effective_from")) for v in versions]
    return [(a, starts[i + 1] if i + 1 < len(starts) else None) for i, a in enumerate(starts)]


def _overlapping(calendar: dict, start: str, end: str | None) -> list[dict]:
    """The versions of a raw calendar whose period of effect overlaps
    [start, end) - ISO date strings compare as dates."""
    versions = [(v or {}) for v in (calendar.get("versions") or [])]
    return [v for v, (c_start, c_end) in zip(versions, _version_windows(versions))
            if (end is None or c_start < end) and (c_end is None or start < c_end)]


def _governed_periods(calendar: dict, start: str, end: str | None, limit: int = 4) -> str:
    """A short, readable list of the periods a participation version
    governs - its calendar's authored periods inside [start, end), by name
    and date, or the date range a cadence rule covers."""
    named = []
    rule = False
    for version in _overlapping(calendar, start, end):
        if version.get("cadence"):
            rule = True
            continue
        for entry in (version.get("dates") or []):
            when = str((entry or {}).get("date"))
            if when >= start and (end is None or when < end):
                named.append(f"{(entry or {}).get('period')} ({when})")
    if rule and not named:
        return f"every day from {start}" + (f" to before {end}" if end else "")
    if not named:
        return f"none authored yet from {start}"
    more = f" and {len(named) - limit} more" if len(named) > limit else ""
    return ", ".join(named[:limit]) + more


def _participation_errors(cal_raw: dict, raw: dict, src: Source) -> list[ConfigError]:
    """REQ-PIPE-110's rules about each dataset's participation, checked on
    contract/calendar.yaml as written - every version, not the newest
    alone (delivery-critic, 2026-10-11)."""
    out: list[ConfigError] = []
    file_name = src.calendar_name
    cal_src = replace(src, asset_path=src.agreement_path)
    walked = [(d or {}, c or {}) for d, c in _walk_datasets(raw)]
    hierarchy_ids = {d.get("id") for d, _c in walked}
    collection_ids = {c.get("id") for _d, c in walked}
    calendars = {(c or {}).get("name"): (c or {}) for c in (cal_raw.get("calendars") or [])}

    # ONE ENTRY EACH: a second block is never "the last one wins", because
    # nobody reviewing the first would know it was overruled.
    collections: dict = {}
    for c in (cal_raw.get("collections") or []):
        cid = (c or {}).get("id")
        if cid in collections:
            out.append(ConfigError(
                file_name, f"collection {cid!r}", f"is listed twice in {file_name}.",
                "Keep one entry. With two, the later silently decides which calendar the "
                "collection is on."))
        collections[cid] = c or {}
    entries: dict = {}
    for e in (cal_raw.get("datasets") or []):
        did = (e or {}).get("id")
        if did in entries:
            out.append(ConfigError(
                file_name, f"dataset {did!r}", f"is listed twice in {file_name}.",
                "Keep one entry and put every version in its one participation list. With two, "
                "the later silently decides the dataset's due time."))
        entries[did] = e or {}

    # CRITERION 18 - both files agree about what exists.
    for c in collections:
        if c not in collection_ids:
            out.append(ConfigError(
                file_name, f"collection {c!r}",
                f"is named in {file_name} and is not a collection in {src.name}'s hierarchy.",
                f"Correct the id, or add the collection to {src.name}. The two files have to "
                f"agree about what exists."))
    for did in entries:
        if did not in hierarchy_ids:
            out.append(ConfigError(
                file_name, f"dataset {did!r}",
                f"is named in {file_name} and is not a dataset in {src.name}'s hierarchy.",
                f"Correct the id, or add the dataset to {src.name}. The two files have to "
                f"agree about what exists."))

    own_names: set[str] = set()
    for dataset, collection in walked:
        ds = dataset.get("id")
        entry = entries.get(ds, {})
        scope = f"dataset {ds!r}"
        for v in (((entry.get("dates") or {}).get("versions")) or []):
            own_names |= {str((d or {}).get("period")) for d in ((v or {}).get("dates") or [])}
        seen_periods: set = set()
        for item in (entry.get("not_expected") or []):
            period = (item or {}).get("period")
            if period in seen_periods:
                out.append(ConfigError(
                    file_name, scope, f"not_expected lists period {period!r} twice.",
                    "Keep one entry with one reason - with two, the later reason silently "
                    "replaces the first."))
            seen_periods.add(period)
        if entry.get(schedule.NO_CALENDAR_KEY) is not None:
            continue
        cal_name = entry.get("calendar") or collections.get(collection.get("id"), {}).get("calendar")
        if not cal_name:
            continue  # reported by the dataset checks, naming both files
        versions = [(v or {}) for v in (((entry.get("participation") or {}).get("versions")) or [])]
        if not versions:
            out.append(ConfigError(
                file_name, scope,
                f"is on calendar {cal_name!r}"
                + ("" if ds in entries else f" (through its collection) and has no entry in {file_name}")
                + " - it has no participation versions, so nothing says when it is due.",
                "Add it to `datasets:` with `participation: {versions: [...]}`, at least one "
                "version stating its effective_from, expected_time and grace (criterion 3)."))
            continue
        calendar = calendars.get(cal_name, {})
        windows = _version_windows(versions)
        for i, (version, (start, end)) in enumerate(zip(versions, windows), start=1):
            months = version.get("participates")
            # CRITERION 8: a list of some months needs a reason.
            if isinstance(months, list) and not version.get("reason"):
                out.append(ConfigError(
                    file_name, scope,
                    f"participation version {i} owes only {', '.join(map(str, months))} and gives "
                    f"no reason.",
                    "Add `reason:` saying why. A month owed nothing with nothing beside it is "
                    "indistinguishable, six months later, from somebody forgetting it."))
            # CRITERIA 5 AND 7, PER VERSION: every month a real one the
            # calendar carries, and no months at all against any cadence-rule
            # calendar version this participation version overlaps.
            if isinstance(months, list) and months and calendar:
                window = {"versions": _overlapping(calendar, start, end)}
                for e in _month_errors(scope, cal_name, window, months, cal_src):
                    out.append(replace(e, problem=f"participation version {i} (effective "
                                                  f"{start}) " + e.problem))
            # CRITERION 29: an expected time and grace for every period owed.
            for key, what in (("expected_time", "expected time"), ("grace", "grace allowance")):
                if version.get(key) is None:
                    out.append(ConfigError(
                        file_name, scope,
                        f"participation version {i} (effective {start}) states no {key}, so "
                        f"the periods it governs have no {what}: "
                        f"{_governed_periods(calendar, start, end)}. Looked in: the dataset's "
                        f"participation versions in {file_name} (a collection's defaults "
                        f"arrive with REQ-PIPE-181).",
                        f"Add `{key}:` to this version. A period owed with no {what} has no due "
                        f"instant to judge a supply against."))
            if version.get("grace") is not None:
                problem = _duration_error(version.get("grace"), f"{scope} grace")
                if problem:
                    out.append(ConfigError(file_name, scope,
                                           f"participation version {i}'s grace {problem}",
                                           "Write a duration with its unit, like 1h or 2d."))
            if version.get("claim_window") is not None:
                problem = _duration_error(version.get("claim_window"), f"{scope} claim_window")
                if problem:
                    out.append(ConfigError(file_name, scope,
                                           f"participation version {i}'s claim_window {problem}",
                                           "Write a duration with its unit, like 14d or 4h."))
            # CRITERION 33: restate everything the previous version stated.
            if i > 1:
                previous = versions[i - 2]
                dropped = [k for k in _RESTATED if k in previous and k not in version]
                if dropped:
                    out.append(ConfigError(
                        file_name, scope,
                        f"participation version {i} (effective {start}) "
                        f"leaves out " + ", ".join(f"{k} (the previous version stated "
                                                   f"{previous[k]!r})" for k in dropped) + ".",
                        "Restate each value on this version. Every version reads as complete "
                        "on its own, so a value is never silently dropped to a default."))
        # CRITERION 34: one date per version, in order.
        starts = [a for a, _b in windows]
        for a, b in zip(starts, starts[1:]):
            if b <= a:
                out.append(ConfigError(
                    file_name, scope,
                    f"participation versions take effect {a} then {b}, which is not after it.",
                    "Put the versions in effective_from order, oldest first, with no two "
                    "sharing a date - otherwise there is no single version in force."))
    # CRITERION 35: a dataset's own period names are not a calendar's.
    calendar_names = {str((d or {}).get("period")) for c in calendars.values()
                      for v in (c.get("versions") or []) for d in ((v or {}).get("dates") or [])}
    for clash in sorted(own_names & calendar_names):
        out.append(ConfigError(
            file_name, None,
            f"period name {clash!r} is used by a dataset's own dates and by a calendar.",
            "Name the dataset's own period differently - one name, one period, one schema."))
    return out


# ---- the gate -------------------------------------------------------

def validate(src: Source | None = None) -> list[ConfigError]:
    src = src or Source.default()
    # ONE READ OF THE PREVIOUS FILE PER RUN, shared by the calendar guard
    # and the amber setting's (REQ-PIPE-122) - cleared here so a later run
    # in the same process never sees an earlier run's answer.
    _content_at.cache_clear()
    if not src.asset_path.exists():
        return [ConfigError(src.name, None,
                             "does not exist.",
                             "This file is the asset's own configuration; nothing works without it.")]

    try:
        raw = yaml.safe_load(src.asset_path.read_text()) or {}
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark else ""
        # ONE error and then stop. A file that did not parse has no
        # values to be missing, and reporting every one of them as
        # absent buries the single thing that is actually wrong.
        return [ConfigError(src.name, None,
                             f"could not be parsed{where}: {getattr(exc, 'problem', exc)}.",
                             "Fix the YAML syntax; nothing below it can be checked until then.")]
    if not isinstance(raw, dict):
        return [ConfigError(src.name, None,
                             "does not contain a mapping.",
                             "The file's top level is keys like data_asset_id, calendars and "
                             "hierarchy.")]

    # THE DELIVERY AGREEMENT IS ITS OWN FILE (REQ-PIPE-110).
    cal_path = src.agreement_path
    if not cal_path.exists():
        return [ConfigError(cal_path.name, None, "does not exist.",
                            "This file holds the delivery agreement - the calendars and each "
                            "dataset's participation; nothing is owed without it.")]
    try:
        cal_raw = yaml.safe_load(cal_path.read_text()) or {}
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark else ""
        return [ConfigError(cal_path.name, None,
                             f"could not be parsed{where}: {getattr(exc, 'problem', exc)}.",
                             "Fix the YAML syntax; nothing below it can be checked until then.")]
    from qa_tools.common.schemas import CalendarFile

    merged = _merged_view(raw, cal_raw)
    cal_src = replace(src, asset_path=cal_path, calendar_path=cal_path)
    errors = _retired_key_errors([(raw, src.name), (cal_raw, cal_path.name)])
    errors += _schema_errors(raw, src)
    errors += _schema_errors(cal_raw, src, CalendarFile, cal_path.name)
    errors += _calendar_errors(cal_raw, cal_src)
    errors += _dataset_errors(merged, cal_src)
    errors += _participation_errors(cal_raw, raw, src)
    errors += _expects_nothing_errors(merged, cal_src)
    errors += _contract_errors(raw, src)
    errors += _retrospective_edit_errors(cal_raw, src)
    errors += _amber_setting_errors(raw, src)
    errors += _replacement_setting_errors(raw, src)
    if src.asset_path == DATA_ASSET_YAML and not errors:
        errors += _overlap_errors(src)
        errors += _daylight_saving_errors(src)
    return _attribute(errors, merged)


def _overlap_errors(src: Source) -> list[ConfigError]:
    """A dataset's periods never overlap (REQ-PIPE-134), every overlap
    reported rather than the first (criterion 5).

    ONLY FOR THE REAL CONFIGURATION, and only once everything above has
    passed: it reads the schedule and contracts through the modules
    filing uses (criterion 2), which load the committed files, so on a
    configuration that is already broken it would report the breakage a
    second time in a worse form.
    """
    from qa_tools.common import period_overlap

    out = []
    for o in period_overlap.overlaps():
        out.append(ConfigError(
            src.name, o.dataset_id,
            f"{o.later}'s claim window opens at {o.later_claim_opens.isoformat()}, but "
            f"{o.earlier} is still on time until {o.on_time_until.isoformat()} - they "
            f"overlap by {o.by}, so a file arriving in between would belong to both.",
            f"Shorten this dataset's claim window or grace, or move its expected time, "
            f"until {o.later}'s window opens strictly after {o.earlier} stops being on time."))
    return out


#: How far ahead a CADENCE-RULE calendar's periods are checked for a due
#: time that daylight saving makes no instant or two (REQ-PIPE-112
#: criterion 8). An authored calendar is checked to its last date; a rule
#: generates periods for ever, so the gate looks this far ahead of today -
#: further than any configuration change is planned, and re-checked on
#: every run as today moves.
DAYLIGHT_SAVING_HORIZON_DAYS = 3 * 366


def _daylight_saving_errors(src: Source) -> list[ConfigError]:
    """REQ-PIPE-112 criterion 8: a dataset's expected time that does not
    exist, or occurs twice, on a period's due date in the zone in force
    then is refused, naming the dataset, the period and the time - choosing
    one of two instants, or inventing one, would be a guess presented as a
    due instant (decision 6).

    Real configuration only, after everything above has passed, for the
    reason `_overlap_errors` gives: it reads through the modules filing
    uses."""
    from datetime import timedelta

    from qa_tools.common import hierarchy, slots

    out = []
    until = asset_time.local_date(asset_time.now()) + timedelta(days=DAYLIGHT_SAVING_HORIZON_DAYS)
    for entry in hierarchy.all_datasets():
        try:
            periods = schedule.periods_for_dataset(entry.dataset_id, until=until)
            agreement = schedule._agreement()
        except Exception:  # noqa: BLE001 - no calendar, or reported by another gate
            continue
        for period in periods:
            # The participation version in force on the period's own date,
            # and the day its due instant falls on (REQ-PIPE-113).
            try:
                version = slots._participation_for(entry.dataset_id, period.date, agreement)
            except schedule.ScheduleConfigError:
                continue  # reported by the participation checks
            expected_time = version.expected_time
            due_day = period.date - timedelta(days=version.days_before)
            problem = asset_time.wall_clock_problem(due_day, expected_time)
            if problem:
                out.append(ConfigError(
                    src.name, f"dataset {entry.dataset_id!r}",
                    f"its expected time {expected_time} on period {period.period.name}'s due date "
                    f"{due_day.isoformat()} {problem} in "
                    f"{asset_time.zone_on(due_day).key}, so that period has no single "
                    f"due instant.",
                    "Move the dataset's expected time out of the daylight-saving change - an "
                    "hour either side - so it names exactly one moment on every due date."))
    return out


def _attribute(errors: list[ConfigError], raw: dict) -> list[ConfigError]:
    """Fill in each error's `affects` - the datasets it actually breaks.

    ONE PLACE READS A SCOPE BACK, deliberately. `scope` is a display
    string this module builds in exactly two shapes, and the thing to
    avoid is twenty call sites each re-deriving what it means; a single
    resolver that owns both readings is a different proposition, and it
    beats threading a dataset list through every construction site,
    where the one that got missed would silently under-count.

    A calendar-scoped error fans out to every dataset naming that
    calendar - which is the whole of post-build-review #18: those
    contributed zero before, so one renamed calendar reported
    "affecting 1 dataset(s)" with seven of seven broken.

    An error scoped to nothing affects no NAMED dataset and keeps an
    empty tuple. _report says "the asset's own configuration" for that
    case, which is truer than fanning a missing top-level key out to
    all thirty.
    """
    on_calendar: dict[str, list[str]] = defaultdict(list)
    known: set[str] = set()
    for dataset, _collection in _walk_datasets(raw):
        dataset_id = dataset.get("id")
        if not dataset_id:
            continue
        known.add(str(dataset_id))
        if dataset.get("calendar"):
            on_calendar[str(dataset["calendar"])].append(str(dataset_id))

    # ONE MISTAKE, ONE ERROR, across the schema/semantic seam. Both
    # layers legitimately check `claim_window: 14`, and both used to
    # report it - the same version, 0-indexed by pydantic and 1-indexed
    # by the semantic check, two lines apart (post-build-review #20).
    # The semantic message survives because it names the unit, gives
    # two examples and says why it is never guessed at; the schema
    # layer's generic one names nothing.
    semantic_fields = {e.field for e in errors if e.field and e.layer == "semantic"}
    errors = [e for e in errors
              if not (e.layer == "schema" and e.field in semantic_fields)]

    out = []
    for error in errors:
        if error.affects or not error.scope:
            out.append(error)
            continue
        affects: tuple[str, ...] = ()
        if error.scope.startswith("dataset "):
            name = error.scope[len("dataset "):].strip().strip("'\"")
            if name in known:
                affects = (name,)
        elif error.scope.startswith("calendar "):
            name = error.scope[len("calendar "):].strip().strip("'\"")
            affects = tuple(on_calendar.get(name, ()))
        out.append(replace(error, affects=affects))
    return out


def _colour(text: str, code: str) -> str:
    """ANSI, and only when a person is looking.

    The whole report printed uncoloured, so on a failing gate the only
    coloured thing on screen was the closing panel - which carried no
    information (post-build-review #25). Rich is not used here because
    this module is also run bare as a CI step, and a gate that imports
    a rendering library to print eight lines has bought a dependency
    for the case where colour is stripped anyway.

    `isatty` rather than a flag: CI logs stay clean without anyone
    remembering to ask, and NO_COLOR is honoured because it costs one
    condition.
    """
    if os.environ.get("NO_COLOR") or not sys.stderr.isatty():
        return text
    return f"\033[{code}m{text}\033[0m"


def _report(errors: list[ConfigError]) -> None:
    """Grouped by file, then by the calendar or dataset to open.

    Every offending item appears, individually - Keith's own call,
    2026-09-23, against a recommendation to suppress errors caused by
    an earlier one. Nothing is hidden, and the count in the header is
    the true count. The grouping is what carries the scale problem
    instead.
    """
    datasets = {d for e in errors for d in e.affects}
    subject = f"{len(datasets)} dataset(s)" if datasets else "the asset's own configuration"
    headline = f"schedule validation FAILED - {len(errors)} error(s) affecting {subject}:"
    print(_colour(headline, "1;31"), file=sys.stderr)

    # THE SHARED CAUSE, ONCE, ABOVE THE DETAIL (#19). One calendar
    # renamed by a character produces one error per dataset on it, and
    # the detail below correctly describes N broken datasets - while the
    # repair is one edit in the calendar they all name. Printed here so
    # a reader meets the root before the symptoms, and only when there
    # is genuinely something to aggregate: a single error is not a
    # shared cause, and a line restating it would be noise.
    #
    # NOTHING IS SUPPRESSED. Every offending item is still printed
    # individually below and the count in the header is unchanged -
    # Keith's own rule, 2026-09-23, against the reviewer's
    # cause-suppression recommendation. This adds a line; it removes
    # none.
    by_cause: dict[str, list[ConfigError]] = defaultdict(list)
    for error in errors:
        if error.cause:
            by_cause[error.cause].append(error)
    for cause, shared in sorted(by_cause.items()):
        if len(shared) < 2:
            continue
        _kind, _, value = cause.partition(":")
        print(_colour(f"\n  {len(shared)} datasets name calendar {value!r}, which this "
                       f"asset does not define.{shared[0].cause_hint or ''}", "1;33"),
              file=sys.stderr)

    by_file: dict[str, dict[str | None, list[ConfigError]]] = defaultdict(lambda: defaultdict(list))
    for error in errors:
        by_file[error.file][error.scope].append(error)

    for filename in sorted(by_file):
        print(f"\n  {_colour(filename, '1')}", file=sys.stderr)
        scopes = by_file[filename]
        for scope in sorted(scopes, key=lambda s: (s is not None, s or "")):
            if scope:
                print(f"    {_colour(scope, '36')}", file=sys.stderr)
            for error in scopes[scope]:
                indent = "      " if scope else "    "
                print(f"{indent}{_colour('-', '31')} {error.problem}\n"
                      f"{indent}  {error.fix}", file=sys.stderr)

    # THE HEADLINE AGAIN, AT THE FOOT. Thirty datasets is sixty lines,
    # and the closing panel used to say "see output above" - pointing a
    # reader back past all of it to a line they had already scrolled off
    # (post-build-review #25). Repeating the count where the eye already
    # is costs one line and removes the scroll.
    if len(errors) > 3:
        print(f"\n{_colour(headline.rstrip(':') + '.', '1;31')}", file=sys.stderr)


def main(src: Source | None = None) -> int:
    """Exit code, not sys.exit - matching the other validate_* gates, so
    cli/ can wrap it in a ClickException the same way."""
    src = src or Source.default()
    errors = validate(src)
    if errors:
        _report(errors)
        return 1

    n_calendars = len(schedule.calendars())
    n_datasets = len(list(_walk_datasets(yaml.safe_load(src.asset_path.read_text()))))
    # A STATEMENT ABOUT THE CONFIGURATION, NOT ABOUT TODAY
    # (plans/post-build-review.md #17, Keith's call 2026-09-24).
    #
    # This line used to end "every one of them expecting something",
    # and that was a claim the gate had not checked.
    # _expects_nothing_errors asks whether a dataset derives zero
    # periods EVER; the clause generalised it into a claim about NOW,
    # and the two part company the moment a calendar runs out - at
    # which point the first line of this gate's output asserted the
    # opposite of the warning printed three lines below it, which is
    # the false-green shape runway.py's own docstring opens with.
    #
    # Rejected: making the headline runway-aware. Config validity and
    # remaining runway are deliberately separate concerns here - one
    # fails the build and the other must never do - and a headline that
    # spoke for both would be the place they got confused.
    print(f"schedule validation OK - {n_calendars} calendar(s), {n_datasets} dataset(s), "
          f"no configuration errors.")

    # LOW RUNWAY IS A WARNING AND RETURNS 0, permanently (REQ-PIPE-053).
    # A non-fatal warning that fails a build gets disabled, and then it
    # is not there for the one that mattered. Printed AFTER the OK line
    # rather than instead of it, so it reads as an additional thing to
    # know rather than as the gate's verdict.
    warned = _warn_about_runway() if src.asset_path == DATA_ASSET_YAML else False

    # PASSED, WITH SOMETHING TO KNOW - and only when something asked to
    # be told. `mothman check` sets MOTHMAN_GATE_WARNING_EXIT so it can
    # render a fourth outcome instead of a green `passed` row followed
    # by "Every gate passed" (post-build-review #23). CI runs this same
    # command as its own workflow step, where any non-zero exit is a
    # failed step, so it does not set the variable and this stays 0 -
    # which is REQ-PIPE-053's own rule that a runway warning must never
    # fail a build.
    if warned:
        configured = (os.environ.get(WARNING_EXIT_VAR) or "").strip()
        if configured.isdigit():
            return int(configured)
    return 0


def _warn_about_runway() -> bool:
    """The low-runway warning, on stderr, never fatal. True if one was
    printed.

    Only for the REAL configuration - a test pointing this gate at a
    synthetic one is asking whether that config is VALID, and answering
    with a warning about its runway would be noise about a calendar
    nobody maintains.
    """
    from qa_tools.common import runway

    lines = runway.warning_lines(asset_time.local_date(asset_time.now()))
    if not lines:
        return False
    # THE VERDICT HAS TO LAND FIRST, and until this flush it did not.
    # The OK line goes to stdout and this goes to stderr, so with
    # stdout block-buffered - which is CI, and any plain shell - the
    # warning arrived ABOVE the verdict it is written to follow, and
    # the first thing under this gate in an Actions log was an
    # unqualified WARNING. Invisible in this sandbox, which sets
    # PYTHONUNBUFFERED (post-build-review #26).
    sys.stdout.flush()
    print("", file=sys.stderr)
    for line in lines:
        print(f"  {line}", file=sys.stderr)
    note = runway.summary(asset_time.local_date(asset_time.now()))
    if note:
        print(f"\n  {note} The gate itself PASSED.", file=sys.stderr)
    return True


if __name__ == "__main__":
    raise SystemExit(main())
