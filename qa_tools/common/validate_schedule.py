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
from datetime import date, timedelta
from pathlib import Path

import yaml
from asset_model import config_yaml
from asset_model import eras as eras_mod

from asset_model import asset_time, assets, schedule
from qa_tools.common import period_schema
from qa_tools.common.diff_base import diff_base
from qa_tools.common.schemas import DataAsset
from asset_model import assets as _assets

ROOT = Path(__file__).resolve().parent.parent.parent

#: Set by `mothman check` to say "you may tell me about a warning".
#: Named here, beside the gate that emits it, and imported by the two
#: callers rather than spelled out three times.
WARNING_EXIT_VAR = "MOTHMAN_GATE_WARNING_EXIT"

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

    @property
    def asset_label(self) -> str:
        """'the <data_asset_id> asset', read from the asset file itself -
        REQ-PIPE-110 criterion 18 names the asset, and the standalone
        `mothman schedule validate` prints bare file names with no [asset]
        prefix, so a problem that must name it says it in words."""
        asset_id = None
        # The calendar's own Source (validate's cal_src) points asset_path at
        # calendar.yaml, so fall back to the data-asset.yaml beside it.
        for path in (self.asset_path, self.asset_path.parent / "data-asset.yaml"):
            try:
                asset_id = (config_yaml.load(path) or {}).get("data_asset_id")
            except (OSError, yaml.YAMLError, AttributeError):
                asset_id = None
            if asset_id:
                break
        return f"the {asset_id} asset" if asset_id else "this asset"

    @classmethod
    def default(cls) -> "Source":
        """The selected asset's own configuration, resolved now (REQ-PIPE-342
        criterion 6) - it was two import-time constants, CONTRACT_DIR and
        DATA_ASSET_YAML."""
        asset = assets.selected()
        return cls(asset.data_asset_yaml, asset.folder)

    @property
    def is_the_selected_assets(self) -> bool:
        return self.asset_path == assets.selected().data_asset_yaml


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

    # WHICH DATASETS THIS BREAKS, for the header count. A calendar-
    # scoped error used to contribute ZERO to it, however many datasets
    # named that calendar - so a renamed calendar reported "affecting 1
    # dataset(s)" with seven of seven broken, which is the
    # safe-looking direction (post-build-review #18). Structural rather
    # than parsed back out of `scope`.
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
    "name": "the asset's baseline calendar's name, like 'quarterly'",
    "effective_from": "the date this version starts applying, as YYYY-MM-DD - like 2027-01-01",
    "changelog": ("a list of entries, each a date, an author and the change - like "
                  "[{date: 2027-01-01, author: Jo Bloggs, change: authored 2027 dates}]"),
    "claim_window": "a duration with its unit, like 14d or 4h",
    "cadence_rule": "a cadence, currently only 'daily'",
    "dates": "a list of period/date pairs, like [{period: 2027-Q1, date: 2027-02-01}]",
    "period": "the period's name, like 2027-Q1",
    "date": "the date the supply is expected, as YYYY-MM-DD",
    "delivery_months": "a list of full month names, like [February, August]",
    "participates": "`all`, or a list of full month names, like [February, August] - or, on a "
                    "daily baseline, full weekday names, like [Monday, Thursday]",
    "expected_time": "a 24-hour time of day, like 09:00 or 14:00",
    "days_before": "a whole number of days, 0 or more, like 1",
    "grace": "a duration with its unit, like 1h or 8h",
    "versions": "a list of versions, each with its own effective_from and changelog",
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
    if "files_go_to_period" in loc and loc and loc[-1] == "value":
        return "a whole number of periods, 0 or more, like 1"
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
    "delivery_months": "participates, on the dataset's participation in assets/<asset>/calendar.yaml",
    "owes_from": "the effective_from of the dataset's first participation version in "
                 "assets/<asset>/calendar.yaml",
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
            if err["type"] == "extra_forbidden" and _baseline_key(loc):
                continue  # refused by name, with REQ-PIPE-345's rule, by _baseline_errors
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
                if loc in (["amber_setting"], ["replacement_setting"]) and not _enduring_asset():
                    continue  # not asked of a one-off (Keith 2026-11-22)
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
    # A COLLECTION ENTRY, and the version by its effective_from (REQ-PIPE-320
    # criterion 6, critic finding 10) - never a path of indices.
    if parts and parts[0] == "collections" and len(parts) > 1 and isinstance(parts[1], int):
        entries = raw.get("collections") or []
        if parts[1] < len(entries):
            entry = entries[parts[1]] or {}
            scope = f"collection {entry.get('id')!r}"
            if "versions" in parts:
                k = parts.index("versions")
                try:
                    version = entry[parts[k - 1]]["versions"][parts[k + 1]]
                    scope += f", the version effective {version.get('effective_from')}"
                except (KeyError, IndexError, TypeError, AttributeError):
                    pass
            return scope
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


# ---- one baseline calendar per asset (REQ-PIPE-345) ------------------

#: Criterion 3's words, which every refusal of a second cadence carries.
BASELINE_RULE = ("a dataset may not be faster than its asset's baseline; a slower one owes a "
                 "subset of the baseline's periods, stated under participates; to go faster, "
                 "change the asset's baseline")


def _baseline_key(loc: list[str]) -> bool:
    """Whether a schema location is a key _baseline_errors refuses by name:
    `calendar:` on a collection or dataset of either file, or `dates:` on a
    dataset of calendar.yaml."""
    if len(loc) == 3 and loc[0] in ("collections", "datasets") and loc[1].isdigit():
        return loc[2] == "calendar" or (loc[0] == "datasets" and loc[2] == "dates")
    if loc[:1] == ["hierarchy"] and len(loc) >= 3 and loc[-3] in ("collections", "datasets"):
        return loc[-1] == "calendar" or (loc[-3] == "datasets" and loc[-1] == "dates")
    return False


def baseline_name(cal_raw: dict) -> str | None:
    """The asset's baseline calendar's name - the first calendar declared,
    which _baseline_errors requires to be the only one - or None for an
    asset that declares none."""
    for c in (cal_raw or {}).get("calendars") or []:
        return (c or {}).get("name")
    return None


def _baseline_errors(raw: dict, cal_raw: dict, src: Source) -> list[ConfigError]:
    """REQ-PIPE-345 criterion 3: a second calendar, a collection or dataset
    naming a calendar (in either file), or a dataset stating authored dates
    of its own - each refused, naming the asset, the item and the file, with
    the rule that says what to do instead."""
    out: list[ConfigError] = []
    asset = (raw or {}).get("data_asset_id") or src.asset_path.parent.name
    cal_file = src.calendar_name
    calendars = [(c or {}) for c in (cal_raw.get("calendars") or [])]
    base = baseline_name(cal_raw)
    for extra in calendars[1:]:
        name = extra.get("name")
        out.append(ConfigError(
            cal_file, f"calendar {name!r}",
            f"asset {asset!r} declares a second calendar, {name!r}, beside its baseline "
            f"{base!r} in {cal_file}; an asset has one baseline calendar.",
            f"Remove calendar {name!r}: {BASELINE_RULE}.", field="calendars"))
    for kind, entries in (("collection", cal_raw.get("collections")),
                          ("dataset", cal_raw.get("datasets"))):
        for i, entry in enumerate(entries or []):
            entry = entry or {}
            item = f"{kind} {entry.get('id')!r}"
            if "calendar" in entry:
                out.append(ConfigError(
                    cal_file, item,
                    f"asset {asset!r}: {item} names calendar {entry.get('calendar')!r} in "
                    f"{cal_file}; every {kind} is on the asset's baseline and names none.",
                    f"Remove `calendar:`: {BASELINE_RULE}.",
                    field=f"{kind}s.{i}.calendar"))
            if kind == "dataset" and "dates" in entry:
                out.append(ConfigError(
                    cal_file, item,
                    f"asset {asset!r}: {item} states authored dates of its own (`dates:`) in "
                    f"{cal_file}; a dataset has only its asset's baseline periods.",
                    f"Remove `dates:`: {BASELINE_RULE}.", field=f"datasets.{i}.dates"))
    for agency in (((raw or {}).get("hierarchy") or {}).get("agencies") or []):
        for collection in ((agency or {}).get("collections") or []):
            collection = collection or {}
            named = [(f"collection {collection.get('id')!r}", collection)]
            named += [(f"dataset {(d or {}).get('id')!r}", d or {})
                      for d in (collection.get("datasets") or [])]
            for item, entry in named:
                if "calendar" in entry:
                    out.append(ConfigError(
                        src.name, item,
                        f"asset {asset!r}: {item} names calendar {entry.get('calendar')!r} in "
                        f"{src.name}; nothing names a calendar - every dataset is on the "
                        f"asset's baseline, declared in {cal_file}.",
                        f"Remove `calendar:`: {BASELINE_RULE}."))
                if item.startswith("dataset ") and "dates" in entry:
                    out.append(ConfigError(
                        src.name, item,
                        f"asset {asset!r}: {item} states authored dates of its own (`dates:`) "
                        f"in {src.name}; a dataset has only its asset's baseline periods.",
                        f"Remove `dates:`: {BASELINE_RULE}."))
    return out


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

def _enduring_asset() -> bool:
    """Whether the folder being gated is an enduring asset under assets/ -
    every selectable folder today. A one-off's Asset will state its kind
    (REQ-PIPE-446 criterion 12), and one stating a kind is not enduring."""
    return getattr(assets.selected(), "kind", None) is None


def _dataset_errors(raw: dict, src: Source) -> list[ConfigError]:
    out: list[ConfigError] = []

    for dataset, _collection in _walk_datasets(raw):
        dataset = dataset or {}
        dataset_id = dataset.get("id")
        scope = f"dataset {dataset_id!r}"
        named = dataset.get("calendar")
        declared_none = dataset.get(schedule.NO_CALENDAR_KEY)
        derived = dataset.get(schedule.DERIVED_KEY)

        # `never` AND `derived` LIVE ONLY UNDER one-offs/ (REQ-PIPE-438
        # criterion 8, Keith 2026-11-21 Q4.7 (a)): this gate refuses them on an
        # enduring asset, naming the dataset; the calendar loader reads what it
        # is given, so every other reader of a bad folder still works.
        if _enduring_asset():
            if declared_none == schedule.NEVER:
                out.append(ConfigError(
                    src.name, scope,
                    f"declares `{schedule.NO_CALENDAR_KEY}: {schedule.NEVER}` on "
                    f"{src.asset_label}, an enduring asset.",
                    f"`{schedule.NEVER}` is for a one-off, which lives under one-offs/, never "
                    f"under assets/. Give this dataset the asset's baseline, or declare "
                    f"`{schedule.NO_CALENDAR_KEY}: {schedule.NOT_YET_AGREED}` while its schedule "
                    f"is still being agreed."))
            if derived is not None:
                out.append(ConfigError(
                    src.name, scope,
                    f"declares `{schedule.DERIVED_KEY}:` on {src.asset_label}, an enduring asset.",
                    f"`{schedule.DERIVED_KEY}: true` marks a one-off's derived product, which "
                    f"lives under one-offs/, never under assets/. Remove it."))
        else:
            # A ONE-OFF HAS SUPPLIES AND NO CADENCE (REQ-PIPE-438 criterion 9):
            # every dataset `never`, so `not-yet-agreed` or a calendar fails.
            if declared_none == schedule.NOT_YET_AGREED or named is not None or (
                    declared_none is None):
                found = (f"`{schedule.NO_CALENDAR_KEY}: {schedule.NOT_YET_AGREED}`"
                         if declared_none == schedule.NOT_YET_AGREED else
                         f"the calendar {named!r}" if named is not None else "no `no_calendar:`")
                out.append(ConfigError(
                    src.name, scope, f"declares {found} on {src.asset_label}, a one-off.",
                    f"A one-off has supplies and no schedule: every one of its datasets "
                    f"declares `{schedule.NO_CALENDAR_KEY}: {schedule.NEVER}`, and nothing "
                    f"else."))
        if derived is not None and declared_none is None:
            out.append(ConfigError(
                src.name, scope,
                f"declares `{schedule.DERIVED_KEY}:` with no `{schedule.NO_CALENDAR_KEY}:` beside it.",
                f"`{schedule.DERIVED_KEY}: true` sits beside a dataset's `{schedule.NO_CALENDAR_KEY}:` "
                f"declaration (REQ-PIPE-438); a dataset with a calendar is never a derived "
                f"product."))

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
            elif dataset.get("delivery_months"):
                out.append(ConfigError(
                    src.name, scope,
                    f"declares `{schedule.NO_CALENDAR_KEY}: {declared_none}` and still "
                    f"subsets a calendar.",
                    "`participates:` describes which of the baseline's periods this dataset "
                    "takes part in, and a dataset with no calendar takes part in none."))
            continue

        # ON THE BASELINE (REQ-PIPE-345 criterion 2): an asset with none
        # accepts only datasets declaring no calendar (criterion 1).
        if not named:
            out.append(ConfigError(
                src.name, scope,
                f"is in {assets.selected().data_asset_yaml.name}'s hierarchy, and "
                f"{src.calendar_name} declares no baseline calendar and no deliberate "
                f"no-calendar declaration for it ({src.asset_label}).",
                f"In {src.calendar_name}, declare the asset's baseline under `calendars:`, or "
                f"declare `{schedule.NO_CALENDAR_KEY}: {schedule.NOT_YET_AGREED}` for this "
                f"dataset if no schedule has been agreed for it yet. Without either there is "
                f"nothing to judge this dataset's supplies against."))
            continue

        months = dataset.get("delivery_months")

        # Months are checked per participation version, against the calendar
        # versions each overlaps, in _participation_errors (REQ-PIPE-110
        # criterion 7) - not here on the newest version alone.

        if months is not None and not months:
            out.append(ConfigError(
                src.name, scope,
                "has a `participates:` list with nothing in it.",
                "Write `participates: all` to take every period, or name the months. As written this "
                "dataset expects nothing."))
    return out


def _month_errors(scope: str, calendar_name: str, calendar: dict, months, src: Source) -> list[ConfigError]:
    """A written participates list against the calendar versions it overlaps
    (REQ-PIPE-110 criteria 5 and 7, REQ-PIPE-346 criteria 2 and 3): one
    vocabulary, the one each version takes - months for authored dates,
    weekdays for a daily rule - and every name a real one."""
    if not months or not isinstance(months, list):
        return []
    out: list[ConfigError] = []

    versions = calendar.get("versions") or []
    vocabulary = schedule.vocabulary_of(months)
    if vocabulary == "both":
        return [ConfigError(
            src.name, scope,
            f"names both months and weekdays under `participates:` ({months!r}).",
            "Name the baseline's rounds in one vocabulary - full month names for an authored "
            "calendar, full weekday names for a daily rule.")]
    rule_driven = any((v or {}).get("cadence") for v in versions)
    authored = any((v or {}).get("dates") for v in versions)
    if vocabulary == schedule.MONTHS and rule_driven:
        out.append(ConfigError(
            src.name, scope,
            f"names delivery months ({_month_list(_months_owed(months, calendar))[1:-1]}) under "
            f"`participates:` against {calendar_name!r}, which is a cadence RULE "
            f"rather than an authored date list - a daily rule takes weekdays.",
            "Write `participates: all`, or the weekdays it supplies on in full, like [Monday]. A "
            "rule-driven calendar has no months to pick from, and a dataset that 'participates in "
            "February' of a daily feed is asking for something the model cannot honour."))
        return out
    if vocabulary == schedule.WEEKDAYS and authored:
        out.append(ConfigError(
            src.name, scope,
            f"names weekdays ({_month_list(_months_owed(months, calendar))[1:-1]}) under "
            f"`participates:` against {calendar_name!r}, which is an authored "
            f"date list rather than a daily rule - an authored calendar takes months.",
            "Write `participates: all`, or the months whose rounds it supplies in, in full, like "
            "[February, August]. An authored calendar's rounds are named by month."))
        return out

    if vocabulary == schedule.WEEKDAYS or (vocabulary is None and rule_driven):
        for value in months:
            if not isinstance(value, str) or value.strip().lower() not in (
                    n.lower() for n in schedule.WEEKDAY_NAMES):
                out.append(ConfigError(
                    src.name, scope,
                    f"names {value!r} under `participates:`, which is not a weekday.",
                    f"Write the full English weekday name - one of: "
                    f"{', '.join(schedule.WEEKDAY_NAMES)}. Abbreviations and numbers are not "
                    f"accepted."))
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

        months = dataset.get("delivery_months")
        if months and schedule.vocabulary_of(months) != schedule.MONTHS:
            continue  # weekdays against authored dates: refused already, by name
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
                "not_expected leaves nothing behind. A dataset expecting nothing passes "
                "forever - which is the exhausted-schedule state arriving by "
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
                f"Add {_assets.config_dir()}/{filename}, or correct the name."))

    # Each collection's contract sits in its agency's folder (REQ-QAC-241), so
    # every YAML under contract/ is looked at, named relative to it - which is
    # how a collection's `contract:` names its file.
    for path in sorted(src.contract_dir.rglob("*.yaml")):
        rel = path.relative_to(src.contract_dir).as_posix()
        if path.name == src.name or rel in declared:
            continue
        try:
            doc = config_yaml.load(path) or {}
        except yaml.YAMLError:
            continue  # reported by the yamllint gate, not twice here
        if not isinstance(doc, dict) or doc.get("kind") != "DataContract":
            # DETECTED BY `kind: DataContract` (REQ-PIPE-110 criterion 32): it
            # used to be the presence of slaProperties, which this change
            # deletes - and that would have switched this check off silently.
            continue  # a checks file or similar, not a dataset contract
        out.append(ConfigError(
            rel, None,
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
    for path in sorted(src.contract_dir.rglob("*.yaml")):
        try:
            doc = config_yaml.load(path) or {}
        except yaml.YAMLError:
            continue
        if isinstance(doc, dict) and "slaProperties" in doc:
            out.append(ConfigError(
                path.relative_to(src.contract_dir).as_posix(), None,
                "states slaProperties, which no longer exist.",
                "Delete the block. A dataset's cadence, expected time and grace live on its "
                f"participation in {_assets.config_dir()}/calendar.yaml, and nothing reads them from a "
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
    return _git_show(rel_path, ref)


def _repo_path(path: Path) -> str | None:
    """`path` by repository path, for a read at a git ref, or None for "no
    previous state" - a file the repository does not hold.

    REFUSED (OutsideTheRepository) ONLY WHERE A DEPLOYMENT HAS DELIBERATELY
    INJECTED ITS ASSET ROOT ELSEWHERE (assets.root_injected(); REQ-PIPE-342's
    injection) and the file is in the selected asset's configuration
    folder: read as "no previous state", the agreement freeze and the amber,
    replacement and list-setting guards would pass any edit to a past item
    unseen (post-build-review #313 M2). Any other outside path - one asset's
    folder pointed elsewhere, as the suite's fixture does, or a test's
    hand-written Source - keeps reading as "no previous state". CHANGED by
    Keith 2026-11-03 (morning report 12 Q13), against the recommendation;
    REJECTED refusing every outside folder, and never refusing."""
    if path.is_relative_to(ROOT):
        return str(path.relative_to(ROOT))
    asset = assets.selected_or_none()
    if asset is not None and assets.root_injected() and path.is_relative_to(asset.folder):
        raise assets.OutsideTheRepository(
            f"asset {asset.name!r}'s configuration folder is {asset.folder}, outside the "
            f"repository ({ROOT}), so {path.name} has no repository path - the schedule "
            f"gate cannot read its previous state at a git ref, and will not read it as "
            f"having none.")
    return None


def _git_show(rel_path: str, ref: str) -> str | None:
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

    from asset_model import amber_setting

    # THE COMMITTER INSTANT, FLOORED AT THE BASE COMMIT'S (REQ-PIPE-111
    # criteria 12 and 28): the author date (%aI) can be set to anything,
    # so a backdated commit could pass a version off as added before its
    # date (plans/post-build-review.md #139).
    from qa_tools.common import agreement_freeze

    base_at = agreement_freeze.committer_instant(ref, root=ROOT)
    # BOTH FILES (REQ-GEN-371 criterion 5): a version may be added to the
    # asset's synthetic eras as well as to data-asset.yaml itself.
    eras_rel = _eras_rel(rel_path)
    result = subprocess.run(["git", "log", "--reverse", "--format=%H %cI", f"{ref}..HEAD",
                             "--", rel_path, *([eras_rel] if eras_rel else [])],
                            cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        sha, _, stamp = line.partition(" ")
        if base_at is not None and datetime.fromisoformat(stamp) < base_at:
            stamp = base_at.isoformat()
        content = _content_at(rel_path, sha)
        try:
            doc = config_yaml.parse(content or "") or {}
            if isinstance(doc, dict) and eras_rel:
                doc = _with_eras(doc, _content_at(eras_rel, sha), eras_rel)
        except (yaml.YAMLError, eras_mod.ErasError):
            continue
        if not isinstance(doc, dict):
            continue
        # EVERY SETTING (REQ-PIPE-123 criterion 1, REQ-QAC-300 criterion 2):
        # the replacement setting and each entry list_settings declares are
        # versioned by the same mechanism, so dated the same way - the list
        # settings iterated, never named.
        if any(start in amber_setting.versions_by_date(setting)
               for key in (amber_setting.KEY, "replacement_setting",
                           *amber_setting.list_setting_keys(doc))
               for setting in amber_setting.stated_settings(doc, key).values()):
            return asset_time.local_date(datetime.fromisoformat(stamp))
    return None


def _eras_rel(asset_rel: str | None) -> str | None:
    """The repository path of the eras.yaml beside an asset's data-asset.yaml."""
    if not asset_rel:
        return None
    return str(Path(asset_rel).parent / "synthetic" / eras_mod.FILE)


def _eras_text_now(src: Source) -> str | None:
    path = eras_mod.path_for(src.asset_path)
    return config_yaml.read(path) if path.exists() else None


def _with_eras(doc: dict, eras_text: str | None, where) -> dict:
    """`doc` with the eras text merged into its setting timelines
    (REQ-GEN-371 criterion 2); `doc` alone where there is no eras text."""
    if not eras_text:
        return doc
    return eras_mod.merged(doc, config_yaml.parse(eras_text, name=str(where)) or {})


def _settings_now(raw: dict, src: Source) -> dict:
    """The asset's settings as they stand: data-asset.yaml and its synthetic
    eras, one timeline - an unreadable eras.yaml is _eras_errors' to say."""
    try:
        return _with_eras(raw, _eras_text_now(src), eras_mod.path_for(src.asset_path))
    except (yaml.YAMLError, eras_mod.ErasError):
        return raw


def _settings_at(src: Source, ref: str) -> dict | None:
    """The asset's settings as they stood at `ref`, merged as now - so a
    version moved between the two files is no change (criterion 5). None
    where data-asset.yaml did not exist there."""
    name = _repo_path(src.asset_path)
    previous = _content_at(name, ref) if name else None
    if previous is None:
        return None
    try:
        doc = config_yaml.parse(previous) or {}
        if not isinstance(doc, dict):
            return None
        eras_rel = _eras_rel(name)
        return _with_eras(doc, _content_at(eras_rel, ref) if eras_rel else None, eras_rel)
    except (yaml.YAMLError, eras_mod.ErasError):
        return None


def _eras_errors(raw: dict, src: Source) -> list[ConfigError]:
    """eras.yaml must parse and name only levels the hierarchy holds."""
    path = eras_mod.path_for(src.asset_path)
    text = _eras_text_now(src)
    if not text:
        return []
    try:
        _with_eras(raw, text, path)
    except yaml.YAMLError as exc:
        return [ConfigError(eras_mod.FILE, None, f"could not be parsed: {exc}.",
                            "Fix the YAML syntax.")]
    except eras_mod.ErasError as exc:
        return [ConfigError(eras_mod.FILE, None, str(exc), "")]
    return []


def _freeze_errors(raw: dict, cal_raw: dict, src: Source,
                   ref: str | None = None) -> list[ConfigError]:
    """REQ-PIPE-111: a frozen item of the delivery agreement changes only by
    a declared correction. Replaces REQ-PIPE-050's past-date guard, whose
    route - any added changelog line licensed moving a past date - is
    removed rather than kept beside it (criterion 6): an undeclared line is
    the quiet edit the requirement exists to stop.

    Compared against the base of the whole push (criterion 13; the
    pre-commit hook sets that base to HEAD, so it compares the staged file);
    a missing previous state passes (criterion 14)."""
    from datetime import UTC, datetime

    from qa_tools.common import agreement_freeze as freeze

    ref = ref or diff_base(root=ROOT)
    cal_path, asset_path = src.agreement_path, src.asset_path

    def rel(path: Path) -> str | None:
        return _repo_path(path)

    def previous(path: Path):
        name = rel(path)
        text = _content_at(name, ref) if name else None
        if text is None:
            return None
        try:
            doc = config_yaml.parse(text) or {}
        except yaml.YAMLError:
            return None
        return doc if isinstance(doc, dict) else None

    old_cal, old_asset = previous(cal_path), previous(asset_path)
    if old_cal is None and old_asset is None:
        return []
    people = previous(ROOT / freeze.people_rel()) or {}

    # THE CLOCK (criterion 12): where the files on disk differ from HEAD the
    # change is not committed yet - it is being made now. Otherwise each
    # change dates from the committer instant of the commit that introduced
    # it. Either way, floored at the base commit's own instant.
    base_at = freeze.committer_instant(ref, root=ROOT) or datetime.now(UTC)
    rels = tuple(r for r in (rel(cal_path), rel(asset_path)) if r)
    dirty = bool(rels) and subprocess.run(
        ["git", "diff", "--quiet", "HEAD", "--", *rels], cwd=ROOT).returncode != 0
    now = datetime.now(UTC)
    final = freeze.flatten(cal_raw, raw)
    walked: list[tuple[datetime, dict]] = []

    def states() -> list[tuple[datetime, dict]]:
        # THE WALK HAPPENS ONLY WHEN A CHANGE TO SOMETHING FROZEN NEEDS
        # DATING (NFR 5) - an ordinary push reads each file once at the base.
        if not walked:
            for sha, at in freeze.commits_since(ref, rels):
                def doc_at(r, sha=sha):
                    return config_yaml.parse(_content_at(r, sha) or "") or {}
                try:
                    cal_doc = doc_at(rel(cal_path)) if rel(cal_path) else {}
                    asset_doc = doc_at(rel(asset_path)) if rel(asset_path) else {}
                except yaml.YAMLError:
                    # A commit whose file did not parse dates nothing - its
                    # items would all read as absent (delivery-critic, L3).
                    continue
                walked.append((at, freeze.flatten(cal_doc, asset_doc)))
        return walked

    def instant_of(key: str) -> datetime:
        if dirty or not states():
            return max(now, base_at)
        want = final.get(key)
        for at, items in states():
            got = items.get(key)
            if (got is None and want is None) or (got is not None and want is not None
                                                  and got.norm == want.norm):
                return max(at, base_at)
        return max(states()[-1][0], base_at)

    # CODEOWNERS AT THE BASE (REQ-GHUB-174 criterion 2), like people.yaml:
    # a change cannot make its own approver a code owner.
    codeowners = _content_at(freeze.CODEOWNERS_REL, ref)
    findings = freeze.check(old_cal, cal_raw, old_asset, raw, people, instant_of=instant_of,
                            base_codeowners=codeowners)
    names = {"calendar.yaml": src.calendar_name, "data-asset.yaml": src.name}
    return [ConfigError(names.get(f.file, f.file), f.scope, f.problem, f.fix)
            for f in findings]


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
        "Make the replacement setting 'green' (or 'never') for those dates, or the warn "
        "setting (amber_setting) promote or promote-and-acknowledge - by a NEW version of whichever you "
        "change, since a past version is frozen.")
        for where, problem in replacement_setting.conflicts(_settings_now(raw, src))]


def _list_setting_errors(raw: dict, src: Source, today: date | None = None,
                         ref: str | None = None) -> list[ConfigError]:
    """REQ-QAC-300 criterion 8: every list setting's past is frozen by the
    amber setting's own guard, run once per entry list_settings declares -
    in the configuration as it stands or as it stood, so removing one is
    seen too."""
    from types import SimpleNamespace

    from asset_model import amber_setting

    ref = ref or diff_base(root=ROOT)
    old_doc = _settings_at(src, ref) or {}
    keys = sorted(set(amber_setting.list_setting_keys(raw))
                  | set(amber_setting.list_setting_keys(old_doc if isinstance(old_doc, dict) else {})))
    out: list[ConfigError] = []
    for key in keys:
        module = SimpleNamespace(
            KEY="/".join(key),
            standing_problems=lambda doc, today, key=key: amber_setting.standing_problems(
                doc, today, key=key),
            past_change_problems=lambda old, new, today, key=key, **kw: (
                amber_setting.past_change_problems(old, new, today, key=key, **kw)))
        out += _amber_setting_errors(raw, src, today, ref, module=module)
    return out


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
    from asset_model import amber_setting

    module = module or amber_setting
    key = module.KEY
    today = today or asset_time.local_date(asset_time.now())
    # ONE TIMELINE, MERGED AGAINST MERGED (REQ-GEN-371 criteria 2 and 5).
    raw = _settings_now(raw, src)
    standing = [ConfigError(
        src.name, f"{key} ({where})", f"{problem}.",
        "Give each version its own effective_from, and keep a data-asset-level version "
        "in effect - there is no default.")
        for where, problem in module.standing_problems(raw, today)]
    ref = ref or diff_base(root=ROOT)
    name = _repo_path(src.asset_path)
    old_doc = _settings_at(src, ref)
    if old_doc is None:
        return standing
    synthetic = bool(old_doc.get("synthetic")) and bool(raw.get("synthetic"))
    problems = module.past_change_problems(old_doc, raw, today, synthetic=synthetic)
    if any("before the day it was added" in p for _, p in problems):
        # ONLY NOW ask git when it was added (criterion 7 as amended): a
        # version dated before today is the one case the commit's date can
        # change, and every other run keeps to the single `git show`.
        rel = name
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
    its calendar - the asset's baseline, never one a collection or dataset
    names (REQ-PIPE-345 criterion 2) - its newest version's participates as
    `delivery_months`, not_expected, and its no-calendar declaration. A VIEW FOR CHECKING ONLY - nothing
    writes it back, and the two files stay the only statements."""
    import copy

    merged = copy.deepcopy(raw)
    merged["calendars"] = list(cal_raw.get("calendars") or [])
    by_dataset = {(d or {}).get("id"): (d or {}) for d in (cal_raw.get("datasets") or [])}
    base = baseline_name(cal_raw)
    for dataset, _collection in _walk_datasets(merged):
        entry = by_dataset.get((dataset or {}).get("id"), {})
        # A `calendar:` or `dates:` written in the hierarchy is not read either
        # (REQ-PIPE-345): _baseline_errors refuses both by name.
        dataset.pop("calendar", None)
        dataset.pop("dates", None)
        if entry.get(schedule.DERIVED_KEY) is not None:
            dataset[schedule.DERIVED_KEY] = entry[schedule.DERIVED_KEY]
        if entry.get(schedule.NO_CALENDAR_KEY) is not None:
            dataset[schedule.NO_CALENDAR_KEY] = entry[schedule.NO_CALENDAR_KEY]
        elif base:
            dataset["calendar"] = base
        versions = ((entry.get("participation") or {}).get("versions")) or []
        months = (versions[-1] or {}).get("participates") if versions else None
        if isinstance(months, list):
            dataset["delivery_months"] = months
        if entry.get("not_expected"):
            dataset["not_expected"] = entry["not_expected"]
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


#: The values that resolve from the level above (REQ-PIPE-181 criterion 2).
_RESOLVED = ("participates", "expected_time", "grace", "claim_window", "days_before")
_INHERIT = "inherit"


def _raw_versions(block) -> list[dict]:
    return [(v or {}) for v in (((block or {}).get("versions")) or [])]


def _gives(version: dict | None, key: str) -> bool:
    """A raw version supplies `key` itself - stated, and not `inherit`."""
    return version is not None and key in version and version[key] != _INHERIT


def _governing(versions: list[dict], start: str, end: str | None) -> list[dict] | None:
    """The raw versions in force at some point in [start, end), oldest
    first - None where none is in force at `start` itself, so some of the
    window has no version at all."""
    windows = _version_windows(versions)
    hit = [v for v, (a, b) in zip(versions, windows)
           if (end is None or a < end) and (b is None or start < b)]
    if not hit or str(hit[0].get("effective_from")) > start:
        return None
    return hit


def _months_owed(value, calendar: dict) -> set[str]:
    """The rounds a raw participates value owes, by full name - months or
    weekdays (REQ-PIPE-346 criterion 4) - and for `all` or a value nobody
    stated, every weekday on a daily rule or every month the calendar
    carries."""
    if isinstance(value, list):
        vocabulary = schedule.vocabulary_of(value)
        if vocabulary == schedule.WEEKDAYS:
            known = {n.lower(): n for n in schedule.WEEKDAY_NAMES}
            return {known[v.strip().lower()] for v in value
                    if isinstance(v, str) and v.strip().lower() in known}
        return {_MONTHS[n - 1] for n in (_month_number(m) for m in value) if n is not None}
    carried = set()
    for version in (calendar.get("versions") or []):
        if (version or {}).get("cadence"):
            return set(schedule.WEEKDAY_NAMES)
        for entry in ((version or {}).get("dates") or []):
            try:
                carried.add(date.fromisoformat(str((entry or {}).get("date"))).month)
            except (TypeError, ValueError):
                continue
    return {_MONTHS[m - 1] for m in (carried or set(range(1, 13)))}


_ROUND_ORDER = {n: i for i, n in enumerate(_MONTHS + schedule.WEEKDAY_NAMES)}


def _month_list(names) -> str:
    """'[February, August]' or '[Monday, Thursday]', in calendar order."""
    return "[" + ", ".join(sorted(names, key=lambda n: _ROUND_ORDER.get(n, 99))) + "]"


def _since(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day} {d.strftime('%b %Y')}"


def _inherit_misuse(version: dict, label: str) -> list[tuple[str, str]]:
    """(problem, fix) for `inherit` written wrongly on one raw version: in
    the wrong case (delivery-critic on 181, F9), and a `reason:` beside
    inherited months - the reason belongs to the months and comes with them
    from the level that gives them (Keith, 2026-10-11, on the critic's F2)."""
    out = []
    for key in _RESOLVED:
        value = version.get(key)
        if isinstance(value, str) and value.lower() == _INHERIT and value != _INHERIT:
            out.append((f"{label} writes {key}: {value}.",
                        "Write `inherit` in lower case - it is a keyword, and any other "
                        "spelling is read as a value."))
    if version.get("participates") == _INHERIT and "reason" in version:
        out.append((f"{label} writes participates: inherit beside its own reason.",
                    "Leave `reason:` out. Inherited months come with the reason of the level "
                    "that gives them, so a reason here would read as explaining months it does "
                    "not decide."))
    return out


def _dropped(previous: dict, version: dict) -> list[str]:
    """The restate rule's dropped keys - except `reason` beside inherited
    months, which comes with them (Keith, 2026-10-11)."""
    out = [k for k in _RESTATED if k in previous and k not in version]
    if version.get("participates") == _INHERIT and "reason" in out:
        out.remove("reason")
    return out


def _defaults_errors(cal_raw: dict, raw: dict, src: Source) -> list[ConfigError]:
    """REQ-PIPE-181's rules about a collection's participation_defaults:
    the restate rule at every level (criterion 4), inherit only where an
    earlier version stated the value (criterion 6) and never for a due time
    or grace (criterion 10), an inherit that widens what its datasets owe
    refused (criterion 8), and one date per version in order (criterion
    11)."""
    out: list[ConfigError] = []
    file_name = src.calendar_name
    cal_src = replace(src, asset_path=src.agreement_path)
    calendars = {(c or {}).get("name"): (c or {}) for c in (cal_raw.get("calendars") or [])}
    entries = {(e or {}).get("id"): (e or {}) for e in (cal_raw.get("datasets") or [])}
    members: dict = {}
    for d, c in _walk_datasets(raw):
        members.setdefault((c or {}).get("id"), []).append((d or {}).get("id"))
    for c in (cal_raw.get("collections") or []):
        c = c or {}
        cid = c.get("id")
        versions = _raw_versions(c.get("participation_defaults"))
        if not versions:
            continue
        scope = f"collection {cid!r}"
        cal_name = baseline_name(cal_raw)
        calendar = calendars.get(cal_name, {})
        windows = _version_windows(versions)
        for i, (version, (start, end)) in enumerate(zip(versions, windows), start=1):
            label = f"participation_defaults version {i} (effective {start})"
            out += [ConfigError(file_name, scope, prob, fix)
                    for prob, fix in _inherit_misuse(version, label)]
            for key in ("expected_time", "grace"):
                if version.get(key) == _INHERIT:
                    out.append(ConfigError(
                        file_name, scope,
                        f"{label} writes {key}: inherit, and a calendar states no "
                        f"{key.replace('_', ' ')}, so inherit here resolves to nothing.",
                        f"State `{key}:` on this version instead. A period owed with no "
                        f"{key.replace('_', ' ')} has no due instant to judge a supply against."))
            for key in ("participates", "claim_window", "days_before"):
                if version.get(key) == _INHERIT and not any(key in p for p in versions[:i - 1]):
                    out.append(ConfigError(
                        file_name, scope,
                        f"{label} writes {key}: inherit, and no earlier version of this "
                        f"collection's defaults stated {key}.",
                        f"Leave `{key}` out instead - a value no earlier version stated is "
                        f"already taken from the level above."))
            months = version.get("participates")
            if isinstance(months, list) and not version.get("reason"):
                out.append(ConfigError(
                    file_name, scope,
                    f"{label} owes only {', '.join(map(str, months))} and gives no reason.",
                    "Add `reason:` saying why - it travels with the months to every dataset "
                    "that takes them."))
            if isinstance(months, list) and months and calendar:
                window = {"versions": _overlapping(calendar, start, end)}
                for e in _month_errors(scope, cal_name, window, months, cal_src):
                    out.append(replace(e, problem=f"{label} " + e.problem))
            for key in ("grace", "claim_window"):
                if _gives(version, key):
                    problem = _duration_error(version.get(key), f"{scope} {key}")
                    if problem:
                        out.append(ConfigError(file_name, scope, f"{label}'s {key} {problem}",
                                               "Write a duration with its unit, like 1h or 14d."))
            if i > 1:
                previous = versions[i - 2]
                dropped = _dropped(previous, version)
                if dropped:
                    offers = []
                    for k in dropped:
                        if k == "claim_window" and calendar:
                            offers.append(f"or write `claim_window: inherit` to take the "
                                          f"{cal_name} calendar's")
                    out.append(ConfigError(
                        file_name, scope,
                        f"{label} leaves out " + ", ".join(
                            f"{k} (the previous version stated {previous[k]!r})"
                            for k in dropped) + ".",
                        "Restate each value on this version" + (
                            " (" + "; ".join(offers) + ")" if offers else "")
                        + ". Every version reads as complete on its own, so a collection-wide "
                          "value is never silently dropped from every dataset that takes it."))
                # CRITERION 8: an inherit that would widen what is owed.
                if version.get("participates") == _INHERIT and isinstance(
                        previous.get("participates"), list):
                    before = _months_owed(previous.get("participates"), calendar)
                    after = _months_owed(None, calendar)
                    # Every dataset of the collection whose version in force
                    # on any date this one governs takes participates from
                    # above - having stated months earlier (F5) included.
                    affected = []
                    for ds in members.get(cid, []):
                        mine = _raw_versions(entries.get(ds, {}).get("participation"))
                        windows_ds = _version_windows(mine)
                        if any(not _gives(v, "participates")
                               for v, (a, b) in zip(mine, windows_ds)
                               if (end is None or a < end) and (b is None or start < b)):
                            affected.append(ds)
                    if after - before and affected:
                        out.append(ConfigError(
                            file_name, scope,
                            f"{label} writes participates: inherit, which would make "
                            f"{', '.join(affected)} newly owe {_month_list(after - before)[1:-1]}.",
                            f"Write the months, or all, explicitly - widening what is owed is "
                            f"never done by a keyword. To keep them: `participates: "
                            f"{_month_list(before)}` with `reason: {previous.get('reason')}`; "
                            f"to owe every period: `participates: all`."))
        starts = [a for a, _b in windows]
        for a, b in zip(starts, starts[1:]):
            if b <= a:
                out.append(ConfigError(
                    file_name, scope,
                    f"participation_defaults versions take effect {a} then {b}, which is not "
                    f"after it.",
                    "Put the versions in effective_from order, oldest first, with no two "
                    "sharing a date - otherwise there is no single version in force."))
    return out


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
                "Keep one entry. With two, the later silently decides the collection's "
                "defaults."))
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
                f"is named in {file_name} and is not a collection in {src.name}'s hierarchy "
                f"({src.asset_label}).",
                f"Correct the id, or add the collection to {src.name}. The two files have to "
                f"agree about what exists."))
    for did in entries:
        if did not in hierarchy_ids:
            out.append(ConfigError(
                file_name, f"dataset {did!r}",
                f"is named in {file_name} and is not a dataset in {src.name}'s hierarchy "
                f"({src.asset_label}).",
                f"Correct the id, or add the dataset to {src.name}. The two files have to "
                f"agree about what exists."))

    base = baseline_name(cal_raw)
    names = {c.get("id"): c.get("name") or c.get("id") for _d, c in walked}
    # CRITERION 12: one collection-level value leaving several datasets
    # without a due time is one root cause, reported once.
    unresolved: dict = {}
    for dataset, collection in walked:
        ds = dataset.get("id")
        entry = entries.get(ds, {})
        scope = f"dataset {ds!r}"
        cid = collection.get("id")
        defaults = _raw_versions(collections.get(cid, {}).get("participation_defaults"))
        seen_periods: set = set()
        for item in (entry.get("not_expected") or []):
            period = (item or {}).get("period")
            if period in seen_periods:
                out.append(ConfigError(
                    file_name, scope, f"not_expected lists period {period!r} twice.",
                    "Keep one entry with one reason - with two, the later reason silently "
                    "replaces the first."))
            seen_periods.add(period)
            # REQ-PIPE-322 criterion 12: the reason the rise's refusal printed
            # is a placeholder, never an answer.
            if str((item or {}).get("reason") or "").strip() == NOT_EXPECTED_PLACEHOLDER:
                out.append(ConfigError(
                    file_name, scope,
                    f"declares {period} not owed with the placeholder reason the gate printed.",
                    "State the reason - why this dataset owes nothing in that period, in words "
                    "a reader of the page will see."))
        if entry.get(schedule.NO_CALENDAR_KEY) is not None:
            continue
        cal_name = base
        if not cal_name:
            continue  # reported by the dataset checks, naming both files
        versions = [(v or {}) for v in (((entry.get("participation") or {}).get("versions")) or [])]
        if not versions:
            out.append(ConfigError(
                file_name, scope,
                f"is on calendar {cal_name!r}"
                + ("" if ds in entries else f" (its asset's baseline) and has no entry in {file_name}")
                + " - it has no participation versions, so nothing says when it is due.",
                "Add it to `datasets:` with `participation: {versions: [...]}`, at least one "
                "version stating its effective_from, expected_time and grace (criterion 3)."))
            continue
        calendar = calendars.get(cal_name, {})
        windows = _version_windows(versions)
        known = cal_name in calendars
        for i, (version, (start, end)) in enumerate(zip(versions, windows), start=1):
            label = f"participation version {i} (effective {start})"
            above = _governing(defaults, start, end)
            out += [ConfigError(file_name, scope, prob, fix)
                    for prob, fix in _inherit_misuse(version, label)]
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
            # CRITERION 6 (REQ-PIPE-181): inherit only where an earlier
            # version of this dataset stated the value.
            for key in _RESOLVED:
                if version.get(key) == _INHERIT and not any(key in p for p in versions[:i - 1]):
                    out.append(ConfigError(
                        file_name, scope,
                        f"{label} writes {key}: inherit, and no earlier version of this "
                        f"dataset stated {key}.",
                        f"Leave `{key}` out instead - a value no earlier version stated is "
                        f"already taken from the level above."))
            # CRITERION 29: an expected time and grace for every period owed
            # - from this version, or from its collection on every date it
            # governs (REQ-PIPE-181 criterion 2).
            for key, what in (("expected_time", "expected time"), ("grace", "grace allowance")):
                if _gives(version, key) or not known:
                    continue
                if above is not None and all(_gives(d, key) for d in above):
                    continue
                unresolved.setdefault((cid, key, what), []).append(
                    (ds, label, start, end, calendar))
            if _gives(version, "grace"):
                problem = _duration_error(version.get("grace"), f"{scope} grace")
                if problem:
                    out.append(ConfigError(file_name, scope,
                                           f"participation version {i}'s grace {problem}",
                                           "Write a duration with its unit, like 1h or 2d."))
            if _gives(version, "claim_window"):
                problem = _duration_error(version.get("claim_window"), f"{scope} claim_window")
                if problem:
                    out.append(ConfigError(file_name, scope,
                                           f"participation version {i}'s claim_window {problem}",
                                           "Write a duration with its unit, like 14d or 4h."))
            # CRITERION 33: restate everything the previous version stated -
            # a value written as inherit counts as stated (REQ-PIPE-181
            # criterion 4), and the refusal offers inherit only where it
            # would resolve on every date this version governs (criterion 7).
            if i > 1:
                previous = versions[i - 2]
                dropped = _dropped(previous, version)
                if dropped:
                    offers = []
                    for k in dropped:
                        if k == "claim_window" and calendar:
                            # WHAT IT WOULD REALLY TAKE (F4): the collection's
                            # value where it states one, else the calendar's.
                            parts = [(f"{d[k]!r} (set for {names.get(cid)}, since "
                                      f"{_since(str(d.get('effective_from')))})")
                                     if _gives(d, k) else f"the {cal_name} calendar's"
                                     for d in (above or [None]) if d is not None] \
                                or [f"the {cal_name} calendar's"]
                            offers.append("`claim_window: inherit` would take "
                                          + " then ".join(dict.fromkeys(parts)))
                        elif k in _RESOLVED and above is not None and all(
                                _gives(d, k) for d in above):
                            if k == "participates" and isinstance(previous.get(k), list) and (
                                    set().union(*(_months_owed(d.get(k), calendar)
                                                  for d in above))
                                    - _months_owed(previous.get(k), calendar)):
                                continue  # F3: inherit here would widen, and is refused
                            values = " then ".join(
                                f"{d[k]!r} (set for {names.get(cid)}, since "
                                f"{_since(str(d.get('effective_from')))})" for d in above)
                            offers.append(f"`{k}: inherit` would take {values}")
                    out.append(ConfigError(
                        file_name, scope,
                        f"{label} "
                        f"leaves out " + ", ".join(f"{k} (the previous version stated "
                                                   f"{previous[k]!r})" for k in dropped) + ".",
                        "Restate each value on this version"
                        + (", or write it as inherit: " + "; ".join(offers) if offers else "")
                        + ". Every version reads as complete on its own, so a value is never "
                          "silently dropped to a default."))
                # CRITERION 8 (REQ-PIPE-181): an inherit that would make the
                # dataset owe a period its previous version did not.
                if version.get("participates") == _INHERIT:
                    prev_value = previous.get("participates")
                    if not _gives(previous, "participates"):
                        prev_above = _governing(
                            defaults, str(previous.get("effective_from")), start)
                        prev_value = (prev_above[-1].get("participates")
                                      if prev_above and _gives(prev_above[-1], "participates")
                                      else None)
                    before = _months_owed(prev_value, calendar)
                    after: set[int] = set()
                    for d in (above or [None]):
                        after |= _months_owed(d.get("participates") if _gives(d, "participates")
                                              else None, calendar)
                    if after - before:
                        reason = previous.get("reason")
                        out.append(ConfigError(
                            file_name, scope,
                            f"{label} writes participates: inherit, which would make it newly "
                            f"owe {_month_list(after - before)[1:-1]}.",
                            f"Write the months, or all, explicitly - widening what is owed is "
                            f"never done by a keyword. To keep them: `participates: "
                            f"{_month_list(before)}`"
                            + (f" with `reason: {reason}`" if reason else "")
                            + "; to owe every period: `participates: all`."))
        # CRITERION 34: one date per version, in order.
        starts = [a for a, _b in windows]
        for a, b in zip(starts, starts[1:]):
            if b <= a:
                out.append(ConfigError(
                    file_name, scope,
                    f"participation versions take effect {a} then {b}, which is not after it.",
                    "Put the versions in effective_from order, oldest first, with no two "
                    "sharing a date - otherwise there is no single version in force."))
    for (cid, key, what), gaps in unresolved.items():
        # ONCE ONLY WHERE THE COLLECTION COULD BE THE FIX (Keith, 2026-10-11,
        # on the critic's F6): it has defaults, and the datasets take them.
        has_defaults = bool(_raw_versions(collections.get(cid, {}).get("participation_defaults")))
        grouped = [g for g in gaps if has_defaults]
        if len({g[0] for g in grouped}) < 2:
            grouped = []
        datasets = sorted({g[0] for g in grouped})
        if grouped:
            out.append(ConfigError(
                file_name, f"collection {cid!r}",
                f"leaves {', '.join(datasets)} with no {key}: none of them states it on "
                f"every participation version, and {names.get(cid)}'s participation_defaults "
                f"do not state it on every date they govern.",
                f"State `{key}:` on {names.get(cid)}'s participation_defaults (or on each "
                f"dataset). A period owed with no {what} has no due instant to judge a supply "
                f"against."))
        for ds, label, start, end, calendar in [g for g in gaps if g not in grouped]:
            out.append(ConfigError(
                file_name, f"dataset {ds!r}",
                f"{label} states no {key}, so the periods it governs have no {what}: "
                f"{_governed_periods(calendar, start, end)}. Looked in: the dataset's "
                f"participation versions and its collection's participation_defaults in "
                f"{file_name}.",
                f"Add `{key}:` to this version, or to the collection's "
                f"participation_defaults. A period owed with no {what} has no due instant to judge a supply "
                  f"against."))
    return out


# ---- turning a dataset or collection off (REQ-PIPE-179) --------------

def _iso(value) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _calendar_dates(calendar: dict, after: date, before: date | None) -> list[tuple[str, date]]:
    """A raw calendar's periods dated strictly between `after` and `before`
    (None for no end), each version contributing only inside its own period
    of effect - with a cadence rule, one per day."""
    from datetime import timedelta

    versions = [(v or {}) for v in (calendar.get("versions") or [])]
    out: list[tuple[str, date]] = []
    for version, (start, end) in zip(versions, _version_windows(versions)):
        v_start, v_end = _iso(start), _iso(end) if end else None
        if v_start is None:
            continue
        if version.get("cadence"):
            day = max(v_start, after + timedelta(days=1))
            stop = min(d for d in (v_end, before) if d) if (v_end or before) else None
            if stop is None or day < stop:
                out.append((day.isoformat(), day))
            continue
        for entry in (version.get("dates") or []):
            when = _iso((entry or {}).get("date"))
            if (when and when > after and (before is None or when < before)
                    and when >= v_start and (v_end is None or when < v_end)):
                out.append((str((entry or {}).get("period")), when))
    return sorted(out, key=lambda pd: pd[1])


def _paste_entry(effective_to, reason) -> str:
    """A ready-to-paste changelog entry turning a version off (criterion 40)."""
    return ("\n    - date: \"YYYY-MM-DD\"\n      author: <your name>\n"
            f"      change: Turned off after {effective_to} - {reason or '<why>'}.\n"
            "      turns_off: true")


def _turn_off_errors(cal_raw: dict, raw: dict, src: Source) -> list[ConfigError]:
    """REQ-PIPE-179's refusals: the two keys together (criterion 2), a
    changelog entry saying it turns off (criterion 40), an effective_to
    that fits its versions and leaves a gap holding a period (criterion 9),
    never inherited (criterion 10), a dataset back on inside its
    collection's gap stating what the collection gave it (criterion 7), and
    no not_expected entry inside a gap (criterion 21)."""
    out: list[ConfigError] = []
    file_name = src.calendar_name
    calendars = {(c or {}).get("name"): (c or {}) for c in (cal_raw.get("calendars") or [])}
    entries = {(e or {}).get("id"): (e or {}) for e in (cal_raw.get("datasets") or [])}
    collections = {(c or {}).get("id"): (c or {}) for c in (cal_raw.get("collections") or [])}
    members: dict = {}
    for d, c in _walk_datasets(raw):
        members.setdefault((c or {}).get("id"), []).append((d or {}).get("id"))

    def inheriting(cid) -> list[str]:
        """The datasets taking cid's defaults - every one on the baseline
        (REQ-PIPE-345) with participation of its own to resolve."""
        return [ds for ds in members.get(cid, [])
                if not entries.get(ds, {}).get(schedule.NO_CALENDAR_KEY)]

    base = calendars.get(baseline_name(cal_raw), {})

    # Every changelog entry in the file: turns_off is true or absent.
    def walk(node, where):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "changelog" and isinstance(v, list):
                    for e in v:
                        if isinstance(e, dict) and "turns_off" in e and e["turns_off"] is not True:
                            # NAMING ITS VERSION, WITH THE FIX TO PASTE (post-build-
                            # review #190 D10), as criterion 40's own refusal does.
                            version = (f" on the version from {node['effective_from']}"
                                       if node.get("effective_from") else "")
                            fix = ("turns_off only ever says true - leave it out of an entry "
                                   "that does not turn a dataset or collection off.")
                            if node.get("effective_to"):
                                fix += (" To say this version turns off, replace the entry "
                                        "with:" + _paste_entry(node["effective_to"],
                                                               node.get("turned_off_reason")))
                            out.append(ConfigError(
                                file_name, where,
                                f"a changelog entry dated {e.get('date')}{version} carries "
                                f"turns_off: {e['turns_off']!r}.", fix))
                else:
                    walk(v, where)
        elif isinstance(node, list):
            for v in node:
                walk(v, where)
    for cid, c in collections.items():
        walk(c, f"collection {cid!r}")
    for did, e in entries.items():
        walk(e, f"dataset {did!r}")
    for c in calendars.values():
        walk(c, f"calendar {c.get('name')!r}")

    def check_versions(versions: list[dict], scope: str, label_kind: str,
                       calendars_for_gap: list[dict]) -> list[tuple[date, date | None, str]]:
        """The rules on one level's versions; returns its gaps as
        (effective_to, next effective_from or None, reason)."""
        gaps = []
        for i, version in enumerate(versions, start=1):
            start = str(version.get("effective_from"))
            label = f"{label_kind} version {i} (effective {start})"
            has_to, has_reason = "effective_to" in version, "turned_off_reason" in version
            if version.get("turned_off_reason") == _INHERIT:
                out.append(ConfigError(
                    file_name, scope, f"{label} writes turned_off_reason: inherit.",
                    "Write the reason itself. A turn-off belongs to the one version that states "
                    "it, so it is never taken from another level or version (criterion 10)."))
            if has_to and not has_reason:
                hint = (" `reason:` says why only some periods are owed; turned_off_reason is the "
                        "key for a turn-off." if "reason" in version else "")
                out.append(ConfigError(
                    file_name, scope,
                    f"{label} states effective_to {version.get('effective_to')} and no "
                    f"turned_off_reason.",
                    "Add `turned_off_reason:` saying why it stops owing supplies - a turn-off "
                    "with no reason is indistinguishable from a mistake." + hint))
            if has_reason and not has_to:
                out.append(ConfigError(
                    file_name, scope,
                    f"{label} states turned_off_reason and no effective_to.",
                    "Add `effective_to:` - the last day it owes, as YYYY-MM-DD - or remove the "
                    "reason. A reason with no date turns nothing off."))
            to = _iso(version.get("effective_to")) if has_to else None
            if to is None:
                continue
            if not any(isinstance(e, dict) and e.get("turns_off") is True
                       for e in (version.get("changelog") or [])):
                out.append(ConfigError(
                    file_name, scope,
                    f"{label} states effective_to {to} and none of its changelog entries says "
                    f"it turns off.",
                    "Add an entry carrying `turns_off: true`, so who turned it off, when and "
                    "why can be found by filtering rather than reading:"
                    + _paste_entry(to, version.get("turned_off_reason"))))
            begin = _iso(start)
            if begin is not None and to < begin:
                out.append(ConfigError(
                    file_name, scope,
                    f"{label}'s effective_to {to} is before its own effective_from {begin}.",
                    f"Change effective_to to {begin} or later."))
                continue
            nxt = _iso(versions[i].get("effective_from")) if i < len(versions) else None
            if nxt is not None and to >= nxt:
                out.append(ConfigError(
                    file_name, scope,
                    f"{label}'s effective_to {to} is on or after the next version's "
                    f"effective_from {nxt}, so the two would govern the same days.",
                    f"Change effective_to to before {nxt}."))
                continue
            if nxt is not None and not any(_calendar_dates(c, to, nxt) for c in calendars_for_gap):
                out.append(ConfigError(
                    file_name, scope,
                    f"{label} turns off after {to} and the next version takes effect {nxt}: "
                    f"there is no period between them, so the turn-off turns nothing off.",
                    "Change effective_to to an earlier date, or the next version's "
                    "effective_from to a later one, so a period falls between."))
            gaps.append((to, nxt, version.get("turned_off_reason") or ""))
        return gaps

    collection_gaps: dict = {}
    for cid, c in collections.items():
        versions = _raw_versions(c.get("participation_defaults"))
        gaps = check_versions(versions, f"collection {cid!r}", "participation_defaults", [base])
        collection_gaps[cid] = [(to, nxt, why, versions) for to, nxt, why in gaps]
    for d, c in _walk_datasets(raw):
        ds, cid = (d or {}).get("id"), (c or {}).get("id")
        entry = entries.get(ds, {})
        scope = f"dataset {ds!r}"
        cal = base
        versions = _raw_versions(entry.get("participation"))
        gaps = [(to, nxt, why, "set for this dataset")
                for to, nxt, why in check_versions(versions, scope, "participation", [cal])]
        if ds in inheriting(cid):
            for to, nxt, why, defaults in collection_gaps.get(cid, []):
                back = [v for v in versions if (f := _iso(v.get("effective_from")))
                        and f > to and (nxt is None or f < nxt)]
                end = min([_iso(v.get("effective_from")) for v in back] + ([nxt] if nxt else []),
                          default=None)
                gaps.append((to, end, why, f"set for {collections[cid].get('id')}"))
                # CRITERION 7: back on inside the gap, stating what the
                # collection gave it on the day before.
                last = next((v for v in defaults if _iso(v.get("effective_to")) == to), {})
                for v in back[:1]:
                    missing = [k for k in _RESOLVED if _gives(last, k) and not _gives(v, k)]
                    if missing:
                        out.append(ConfigError(
                            file_name, scope,
                            f"participation version effective {v.get('effective_from')} brings "
                            f"it back on while {cid} is turned off, and leaves unstated "
                            + ", ".join(f"{k} ({cid}'s last value {last[k]!r})" for k in missing)
                            + ".",
                            "State " + ", ".join(f"`{k}:`" for k in missing) + " on that version. "
                            "While a collection is turned off it gives no value to any dataset, "
                            "so a dataset back on states its own."))
        # CRITERION 21: no not_expected entry inside a gap.
        if not gaps:
            continue
        dated = {name: when for name, when in _calendar_dates(cal, date.min, None)}
        for item in (entry.get("not_expected") or []):
            period = (item or {}).get("period")
            when = dated.get(period)
            for to, end, why, level in gaps:
                if when and when > to and (end is None or when < end):
                    out.append(ConfigError(
                        file_name, scope,
                        f"not_expected names {period}, inside a turned-off gap - after {to}, "
                        + (f"until {end}" if end else "for good")
                        + f", {level}: {why}.",
                        "Remove the not_expected entry - a turned-off period already owes "
                        "nothing - by a declared correction (REQ-PIPE-111) where the entry is "
                        "already frozen."))
    return out


# ---- the gate -------------------------------------------------------

# ---- files_go_to_period (REQ-PIPE-320) ------------------------------

_OFFSET_KEY = "files_go_to_period"


def _first_round(cal_name: str, begins: date, agr) -> date | None:
    """The first round of a calendar dated on or after `begins` - the round
    a version effective from `begins` takes effect from (criterion 1)."""
    try:
        rounds = schedule.periods_for_calendar(cal_name, until=begins + timedelta(days=400),
                                               agreement=agr)
    except schedule.ScheduleConfigError:
        return None
    return next((p.date for p in rounds if p.date >= begins), None)


def _files_go_to_period_errors(cal_raw: dict, raw: dict, src: Source, *,
                               freeze: list[ConfigError] = (),
                               consumed: list[ConfigError] | None = None) -> list[ConfigError]:
    """REQ-PIPE-320 criteria 3, 4, 5, 7 and 13, from committed configuration
    alone (criterion 9). A value's type and sign are the schema's (criterion
    6). Nothing here defaults a missing value: the two deployments want
    opposite ones, so the gate names every collection that says nothing.

    `freeze` is the freeze gate's refusals for this change (REQ-PIPE-111):
    one about a version a RISE refusal is about is folded into that refusal
    as its step 2 and added to `consumed`, so the caller gives it once
    (REQ-PIPE-322 criterion 2)."""
    from asset_model import agreement as agreement_mod

    out: list[ConfigError] = []
    name = src.calendar_name
    collection_of = {(d or {}).get("id"): (c or {}).get("id") for d, c in _walk_datasets(raw)}

    def belongs(scope: str, dataset_id: str) -> ConfigError:
        cid = collection_of.get(dataset_id)
        return ConfigError(name, scope,
                           f"states {_OFFSET_KEY}, which belongs to the collection - a "
                           f"collection's files always go into the same period, so no dataset "
                           f"can say otherwise (REQ-PIPE-320 criterion 3).",
                           f"Remove it here and state it on the collection entry {cid!r} in "
                           f"{name}'s collections list.")

    # CRITERION 3: anywhere but a collection entry.
    for entry in cal_raw.get("datasets") or []:
        did = (entry or {}).get("id")
        if _OFFSET_KEY in (entry or {}):
            out.append(belongs(f"dataset {did!r}", did))
        for i, v in enumerate(((entry.get("participation") or {}).get("versions")) or []):
            if _OFFSET_KEY in (v or {}):
                out.append(belongs(f"dataset {did!r} participation version {i + 1}", did))
    for agency in ((raw.get("hierarchy") or {}).get("agencies") or []):
        if _OFFSET_KEY in (agency or {}):
            out.append(ConfigError(src.name, f"agency {agency.get('id')!r}",
                                   f"states {_OFFSET_KEY} in the hierarchy.",
                                   f"State it on each collection's entry in {name}."))
    for dataset, collection in _walk_datasets(raw):
        if _OFFSET_KEY in (collection or {}):
            out.append(ConfigError(src.name, f"collection {collection.get('id')!r}",
                                   f"states {_OFFSET_KEY} in the hierarchy.",
                                   f"State it on the collection's entry in {name}, beside its "
                                   f"calendar."))
        if _OFFSET_KEY in (dataset or {}):
            out.append(belongs(f"dataset {dataset.get('id')!r}", dataset.get("id")))
    if out:
        return out
    try:
        agr = agreement_mod.from_doc(cal_raw, src.agreement_path)
    except (schedule.ScheduleConfigError, ValueError, TypeError, AttributeError):
        return out  # the parse error is another check's to report
    entries = {(c or {}).get("id"): (c or {}) for c in cal_raw.get("collections") or []}
    datasets_of: dict[str, list[str]] = {}
    for did, cid in collection_of.items():
        datasets_of.setdefault(cid, []).append(did)
    for cid, dids in datasets_of.items():
        entry = entries.get(cid, {})
        scope = f"collection {cid!r}"
        # TWO VERSIONS ON ONE DATE (critic finding 10) would leave which is in
        # force to the order they happen to be written in.
        seen: set[str] = set()
        for raw_v in ((entry.get(_OFFSET_KEY) or {}).get("versions") or []):
            when = str((raw_v or {}).get("effective_from"))
            if when in seen:
                out.append(ConfigError(
                    name, scope,
                    f"states two {_OFFSET_KEY} versions effective {when}.",
                    "Keep one version per effective_from - a later value is a new version "
                    "from a later round (REQ-PIPE-320)."))
            seen.add(when)
        versions = agr.offsets.get(cid, ())
        on_calendar, unknown = [], False
        for did in dids:
            d = agr.dataset(did)
            if d is None or d.no_calendar or not d.participation:
                continue
            cal_name = agr.calendar_name_for(did)
            if cal_name and cal_name in agr.calendars:
                on_calendar.append((did, cal_name, d))
            elif cal_name:
                unknown = True  # a calendar that does not exist - another check names it
        if not on_calendar and unknown:
            continue
        if not on_calendar:
            # CRITERION 5: a collection with no calendar has no periods.
            if versions:
                out.append(ConfigError(name, scope,
                                       f"states {_OFFSET_KEY}, and none of its datasets is on a "
                                       f"calendar.",
                                       "Remove it - a collection with no calendar has no periods "
                                       "to send files to."))
            continue
        # CRITERION 4: a version in force on its first participating round.
        firsts = [r for did, cal_name, d in on_calendar
                  if (r := _first_round(cal_name, d.participation[0].effective_from, agr))]
        first = min(firsts) if firsts else None
        if first is not None and (not versions or versions[0].effective_from > first):
            have = (f"its first version takes effect from "
                    f"{versions[0].effective_from.isoformat()}" if versions
                    else f"it states no {_OFFSET_KEY}")
            out.append(ConfigError(name, scope,
                                   f"{have}, and its datasets supply from the round of "
                                   f"{first.isoformat()} - its first round has no "
                                   f"{_OFFSET_KEY}, and none is assumed.",
                                   f"State {_OFFSET_KEY} on the collection's entry with a first "
                                   f"version effective from {first.isoformat()} or earlier: "
                                   f"0 if its files go into the period they arrive in, N for "
                                   f"the period N after it."))
        ends = [v.effective_from for v in versions[1:]] + [None]
        for v, until in zip(versions, ends):
            if v.value == 0:
                continue
            for did, cal_name, d in on_calendar:
                cal = agr.calendars[cal_name]
                # CRITERION 7: a cadence-rule round in this version's span.
                starts = [cv.effective_from for cv in cal.versions]
                spans = zip(cal.versions, starts[1:] + [None])
                if any(cv.is_cadence_rule
                       and (until is None or cv.effective_from < until)
                       and (cend is None or cend > v.effective_from)
                       for cv, cend in spans):
                    out.append(ConfigError(name, scope,
                                           f"states {_OFFSET_KEY} {v.value} on the version "
                                           f"effective {v.effective_from.isoformat()}, and "
                                           f"{did!r} is on the {cal_name!r} calendar, a cadence "
                                           f"rule, in that span.",
                                           "On a cadence-rule calendar a supply due ahead is "
                                           "stated with days before, of at most 1 (REQ-PIPE-324 "
                                           "criterion 4); state 0 here."))
                    break
                # REQ-PIPE-320 criterion 13's own-dates refusal went with own
                # dates (REQ-PIPE-345): no dataset states dates of its own.
        out += _rise_errors(name, cid, scope, on_calendar, versions, agr,
                            freeze=freeze, consumed=consumed)
    return out


def _days_before_errors(cal_raw: dict, src: Source) -> list[ConfigError]:
    """REQ-PIPE-324 criteria 1, 2 and 4: days before stays inside one round.
    On an authored calendar a due date may not reach back before the round
    before it - a later period is the collection's files_go_to_period to
    say; on a cadence-rule calendar 1 is the most, and nothing else is
    pointed to, since files_go_to_period is refused there. One error per
    dataset version, at its first offending round."""
    from datetime import timedelta

    from asset_model import agreement as agreement_mod

    try:
        agr = agreement_mod.from_doc(cal_raw, src.agreement_path)
    except (schedule.ScheduleConfigError, ValueError, TypeError, AttributeError):
        return []  # the parse error is another check's to report
    name = src.calendar_name
    out: list[ConfigError] = []
    from asset_model import hierarchy

    for did in sorted(d for d in (e.dataset_id for e in agr.datasets.values()) if d):
        try:
            cal_name = agr.calendar_name_for(did)
            versions = agr.resolved_versions(did)
        except hierarchy.UnknownDatasetError:
            continue  # a dataset the hierarchy does not hold is another check's to report
        cal = agr.calendars.get(cal_name) if cal_name else None
        if cal is None or not versions:
            continue
        ends = [v.effective_from for v in versions[1:]] + [None]
        rounds = None
        for v, until in zip(versions, ends):
            days = v.days_before or 0
            if days == 0:
                continue
            on = f"the version effective {v.effective_from.isoformat()}"
            if cal.current.is_cadence_rule:
                if days > 1:
                    out.append(ConfigError(
                        name, f"dataset {did!r}",
                        f"states days before {days} on {on}, on the cadence-rule calendar "
                        f"{cal_name!r}.",
                        "1 is the most a cadence-rule calendar accepts - the evening before "
                        "(REQ-PIPE-324 criterion 4). State 0 or 1."))
                continue
            if rounds is None:
                rounds = schedule.periods_for_calendar(cal_name, agreement=agr)
            for i in range(1, len(rounds)):
                rnd = rounds[i]
                if rnd.date < v.effective_from or (until is not None and rnd.date >= until):
                    continue
                # ONLY ITS OWN ROUNDS (critic finding 4): a round it supplies
                # nothing in has no slot of its to be due. Still measured
                # against the calendar round just before (PROVISIONAL).
                version = agr.participation_on(did, rnd.date)
                if version is not None and not version.owes_round(rnd.date):
                    continue
                if rnd.date - timedelta(days=days) >= rounds[i - 1].date:
                    continue
                filled = schedule.period_filled_by(did, rnd, agr)
                largest = (rnd.date - rounds[i - 1].date).days
                out.append(ConfigError(
                    name, f"dataset {did!r}",
                    f"states days before {days} on {on}, so its slot on the "
                    f"{_day(rnd.date)} round (for {filled.name if filled else rnd.name}) "
                    f"would be due before the {_day(rounds[i - 1].date)} round - that round "
                    f"accepts at most {largest}.",
                    f"Keep days before inside one round. Where these files are for a later "
                    f"period, state the collection's {_OFFSET_KEY} instead (REQ-PIPE-320) - "
                    f"it applies to every dataset of the collection."))
                break
    return out


#: The reason a pasted not_expected entry carries until somebody states one
#: (REQ-PIPE-322 criteria 2 and 12) - refused while it is still there.
NOT_EXPECTED_PLACEHOLDER = "<state why this dataset owes nothing in this period>"


def _change_rounds(cal_name: str, versions, agr):
    """(version before, version, index of the version's first round, the
    calendar's rounds) for each change of value after a collection's first
    version - which is no change (REQ-PIPE-322 criterion 5)."""
    changes = [(old, new) for old, new in zip(versions, versions[1:]) if old.value != new.value]
    if not changes:
        return
    # BOUNDED for a cadence rule, which never ends: a value above 0 there is
    # refused by criterion 7 anyway, so two years past the last change is
    # all a fall back to 0 needs.
    until = max(new.effective_from for _o, new in changes).replace(day=1)
    until = until.replace(year=until.year + 2)
    rounds = schedule.periods_for_calendar(cal_name, until=until, agreement=agr)
    for old, new in changes:
        i0 = next((i for i, r in enumerate(rounds) if r.date >= new.effective_from), None)
        if i0 is None or i0 == 0:
            continue
        yield old, new, i0, rounds


def _participates_in(did: str, rnd, agr) -> tuple[bool, str]:
    """Whether a dataset supplies in a round, and why not where it does not -
    on the round's own date (REQ-PIPE-321 criterion 2)."""
    from asset_model import agreement as agreement_mod

    begins = schedule.owes_from(did, agr)
    if begins is not None and rnd.date < begins:
        return False, f"it owes nothing before {begins.isoformat()}"
    standing = agr.standing_on(did, rnd.date)
    if standing.state == agreement_mod.TURNED_OFF:
        return False, f"it is turned off on the {_day(rnd.date)} round"
    version = agr.participation_on(did, rnd.date)
    if version is not None and not version.owes_round(rnd.date):
        return False, f"it does not supply in the {_day(rnd.date)} round"
    return True, ""


def _day(d) -> str:
    return f"{d.day} {d.strftime('%B %Y')}"


def _rise_errors(name, cid, scope, on_calendar, versions, agr, *,
                 freeze: list[ConfigError] = (),
                 consumed: list[ConfigError] | None = None) -> list[ConfigError]:
    """REQ-PIPE-322 criteria 1 and 2: a rise by D skips D periods no round
    fills, and each is declared not owed by every dataset that would have
    supplied it at the old value - ONE refusal per version, with what to
    paste, the freeze refusal for the same version (REQ-PIPE-111 criterion
    15) combined into it as step 2 where there is one."""
    if not on_calendar:
        return []
    # EVERY CALENDAR ITS DATASETS NAME (critic finding 6): each calendar's
    # skipped periods are worked out on its own rounds, for its own datasets.
    by_calendar: dict[str, list] = {}
    for entry in on_calendar:
        by_calendar.setdefault(entry[1], []).append(entry)
    if len(by_calendar) > 1:
        return [e for cal, group in by_calendar.items()
                for e in _rise_errors(name, cid, scope, group, versions, agr,
                                      freeze=freeze, consumed=consumed)]
    cal_name = on_calendar[0][1]
    out = []
    for old, new, i0, rounds in _change_rounds(cal_name, versions, agr):
        if new.value < old.value:
            continue
        skipped = [j for j in range(i0 - 1 + old.value + 1, i0 + new.value) if j < len(rounds)]
        must: dict[str, list[str]] = {}
        need_not: list[str] = []
        for j in skipped:
            period, rnd = rounds[j], rounds[j - old.value]
            for did, _cal, _d in on_calendar:
                ok, why = _participates_in(did, rnd, agr)
                if not ok:
                    need_not.append(f"{did} ({why})")
                elif period.name not in schedule.not_expected_periods(did, agr):
                    must.setdefault(did, []).append(period.name)
        if not must:
            continue
        names = ", ".join(rounds[j].name for j in skipped)
        paste = "\n".join(
            f"     - id: {did}\n       not_expected:\n" + "".join(
                f'         - period: "{p}"\n           reason: "{NOT_EXPECTED_PLACEHOLDER}"\n'
                for p in periods)
            for did, periods in must.items())
        # ONE NUMBERED LIST FOR ONE EDIT (REQ-PIPE-322 criterion 2, built
        # 2026-11-23 at Keith's word): where the version is frozen, the freeze
        # gate's refusal for it becomes step 2, with its correction to paste,
        # and is not given again on its own.
        key = f"collection {cid} {_OFFSET_KEY} {new.effective_from.isoformat()}"
        frozen = next((f for f in freeze if f.scope and key in f.scope.split(", ")
                       and not any(f is c for c in (consumed or []))), None)
        problem = (f"rises from {_OFFSET_KEY} {old.value} to {new.value} on the version effective "
                   f"{new.effective_from.isoformat()}, from the {_day(rounds[i0].date)} round - so "
                   f"no round fills {names}. Must declare it not owed: {', '.join(must)}. Need "
                   f"not: "
                   + (", ".join(need_not) if need_not else
                      "none - every dataset supplies in that round")
                   + ".")
        fix = (f"1. Declare each skipped period not owed in {name}, stating the reason - add "
               f"not_expected to each dataset's existing entry under datasets:\n" + paste)
        if frozen is not None:
            if consumed is not None:
                consumed.append(frozen)
            problem += " And the version is frozen: " + frozen.problem
            fix += ("\n  2. The version is frozen, so declare the change as a correction too "
                    "(REQ-PIPE-111 criterion 15). " + frozen.fix)
        out.append(ConfigError(name, scope, problem, fix))
    return out


def _collection_calendars(cid: str, agr) -> tuple[str, list[str]]:
    """(collection name, the calendar its datasets are on) - the asset's
    baseline, once, where any member is on it (REQ-PIPE-345)."""
    from asset_model import hierarchy

    try:
        members = hierarchy.datasets_in_collection(cid)
    except hierarchy.UnknownDatasetError:
        return "", []
    names: list[str] = []
    for d in members:
        name = agr.calendar_name_for(d.dataset_id)
        if name in agr.calendars and name not in names:
            names.append(name)
    return (members[0].collection_name if members else ""), names


def effective_lines(agr) -> list[str]:
    """REQ-PIPE-320 criterion 1: where a files_go_to_period version's
    effective_from is not itself a round's date, the round on each calendar
    it takes effect from - information, never a refusal."""
    from datetime import timedelta

    from qa_tools.common import files_go

    out = []
    for cid, versions in sorted(agr.offsets.items()):
        label, cals = _collection_calendars(cid, agr)
        for v in versions:
            for cal_name in cals:
                try:
                    rounds = schedule.periods_for_calendar(
                        cal_name, until=v.effective_from + timedelta(days=400), agreement=agr)
                except schedule.ScheduleConfigError:
                    continue
                first = next((r for r in rounds if r.date >= v.effective_from), None)
                if first is None or first.date == v.effective_from:
                    continue
                said = files_go.value_words(v.value)
                where = f" on the {cal_name!r} calendar" if len(cals) > 1 else ""
                out.append(f"{label}: {said[0].lower()}{said[1:]} from {_day(v.effective_from)}, "
                           f"which takes effect from the {_day(first.date)} round{where}.")
    return out


def fall_lines(agr) -> list[str]:
    """REQ-PIPE-322 criterion 10: one line per collection naming each period a
    fall feeds twice and the round whose files will be held for a person -
    information, never a refusal."""
    out = []
    for cid, versions in sorted(agr.offsets.items()):
        label, cals = _collection_calendars(cid, agr)
        for cal_name in cals:   # EVERY calendar its datasets name (finding 6)
            where = f" on the {cal_name!r} calendar" if len(cals) > 1 else ""
            for old, new, i0, rounds in _change_rounds(cal_name, list(versions), agr):
                if new.value > old.value:
                    continue
                for k in range(old.value - new.value):
                    held = rounds[i0 + k] if i0 + k < len(rounds) else None
                    target = i0 + k + new.value
                    if held is None or target >= len(rounds):
                        continue
                    filler = rounds[target - old.value]
                    out.append(f"{label}: from the {_day(held.date)} round{where}, files for "
                               f"{rounds[target].name} will be held for a person - the "
                               f"{_day(filler.date)} round already fills it.")
    return out


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
        raw = config_yaml.load(src.asset_path) or {}
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
        cal_raw = config_yaml.load(cal_path) or {}
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
    errors += _baseline_errors(raw, cal_raw, src)
    errors += _calendar_errors(cal_raw, cal_src)
    if len(cal_raw.get("calendars") or []) > 1:
        # TWO CALENDARS AND NOTHING BELOW CAN BE JUDGED (REQ-PIPE-345): every
        # later check reads the datasets' periods off the one baseline, and
        # guessing which of two is meant would judge them against the wrong
        # one. The refusals above say what to do; the rest waits for it.
        return _attribute(errors, merged)
    errors += _dataset_errors(merged, cal_src)
    errors += _participation_errors(cal_raw, raw, src)
    errors += _defaults_errors(cal_raw, raw, src)
    errors += _turn_off_errors(cal_raw, raw, src)
    # THE FREEZE GATE FIRST, so a rise on a frozen version is ONE refusal
    # (REQ-PIPE-322 criterion 2): what the rise refusal folds in is not given
    # again on its own.
    freeze = _freeze_errors(raw, cal_raw, src)
    consumed: list[ConfigError] = []
    errors += _files_go_to_period_errors(cal_raw, raw, src, freeze=freeze, consumed=consumed)
    errors += _days_before_errors(cal_raw, src)
    errors += _expects_nothing_errors(merged, cal_src)
    errors += _contract_errors(raw, src)
    errors += [f for f in freeze if not any(f is c for c in consumed)]
    errors += _eras_errors(raw, src)
    # NOT ASKED OF A ONE-OFF (Keith 2026-11-22): a no-period supply is never
    # promoted (REQ-PIPE-435 criterion 7), so neither setting means anything.
    if _enduring_asset():
        errors += _amber_setting_errors(raw, src)
        errors += _replacement_setting_errors(raw, src)
    errors += _list_setting_errors(raw, src)
    if src.is_the_selected_assets and not errors:
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

    from asset_model import hierarchy, slots

    out = []
    until = asset_time.local_date(asset_time.now()) + timedelta(days=DAYLIGHT_SAVING_HORIZON_DAYS)
    for entry in hierarchy.all_datasets():
        # EVERY PERIOD THE SLOT PATH COMPUTES, owed or not: a non-owed
        # period's claim-opening closes the slot before it, so its due
        # instant is computed too, and a daylight-saving gap there was a
        # traceback in filing rather than an error here (delivery-critic on
        # REQ-PIPE-113, #2).
        try:
            agreement = schedule.agreement_to_read()
            periods = [p for p in slots.period_sequence(entry.dataset_id, until, agreement)
                       if p.date <= until]
        except Exception:  # noqa: BLE001 - no calendar, or reported by another gate
            continue
        for period in periods:
            # The participation version in force on the period's own date,
            # and the day its due instant falls on (REQ-PIPE-113).
            try:
                version = slots.participation_for(entry.dataset_id, period.date, agreement)
            except schedule.ScheduleConfigError:
                continue  # reported by the participation checks
            expected_time = version.expected_time
            due_day = period.date - timedelta(days=version.days_before)
            problem = asset_time.wall_clock_problem(due_day, expected_time)
            if problem:
                out.append(ConfigError(
                    src.name, f"dataset {entry.dataset_id!r}",
                    f"its expected time {expected_time} on period {period.name}'s due date "
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
    n_datasets = len(list(_walk_datasets(config_yaml.load(src.asset_path))))
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

    # A FALL IS INFORMATION, NOT A REFUSAL (REQ-PIPE-322 criterion 10): each
    # doubly-fed period and the round whose files will be held, said once.
    try:
        from asset_model import agreement as agreement_mod

        loaded = agreement_mod.load(src.agreement_path)
        for line in effective_lines(loaded) + fall_lines(loaded):
            print(f"  {line}")
    except (schedule.ScheduleConfigError, ValueError, OSError):
        pass  # a configuration the checks above passed always loads

    # LOW RUNWAY IS A WARNING AND RETURNS 0, permanently (REQ-PIPE-053).
    # A non-fatal warning that fails a build gets disabled, and then it
    # is not there for the one that mattered. Printed AFTER the OK line
    # rather than instead of it, so it reads as an additional thing to
    # know rather than as the gate's verdict.
    warned = _warn_about_runway() if src.is_the_selected_assets else False

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
