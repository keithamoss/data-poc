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

import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

from qa_tools.common import schedule
from qa_tools.common.schemas import DataAsset

ROOT = Path(__file__).resolve().parent.parent.parent
CONTRACT_DIR = ROOT / "contract"
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

    @property
    def name(self) -> str:
        return self.asset_path.name

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

    def __str__(self) -> str:
        return f"{self.problem} {self.fix}"


def _month_number(value) -> int | None:
    """A full English month name, or None. Deliberately strict - see
    schedule.parse_month_name(), whose reading this mirrors."""
    if not isinstance(value, str):
        return None
    try:
        return _MONTHS.index(value.strip()) + 1
    except ValueError:
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

def _schema_errors(raw: dict, src: Source) -> list[ConfigError]:
    """Shape, via the declared model. Every pydantic error is rewritten
    with somewhere to file it and something to do about it - the raw
    location path is accurate and unreadable."""
    from pydantic import ValidationError

    try:
        DataAsset.model_validate(raw)
    except ValidationError as exc:
        out = []
        for err in exc.errors():
            loc = [str(p) for p in err["loc"]]
            scope = _scope_from_loc(raw, err["loc"])
            where = " -> ".join(loc) or "(top level)"
            if err["type"] == "extra_forbidden":
                out.append(ConfigError(
                    src.name, scope,
                    f"{where} is not a key this configuration has.",
                    "Remove it, or correct the spelling - an unknown key is accepted "
                    "nowhere here precisely because a dropped one is invisible."))
            elif err["type"] == "missing":
                out.append(ConfigError(
                    src.name, scope,
                    f"{where} is required and is not there.",
                    "Add it."))
            else:
                out.append(ConfigError(
                    src.name, scope,
                    f"{where}: {err['msg']}.",
                    "Correct the value."))
        return out
    return []


def _scope_from_loc(raw: dict, loc: tuple) -> str | None:
    """The calendar or dataset a pydantic location sits inside.

    Resolved from the raw document rather than the model, because the
    model did not validate - that is why there is an error.
    """
    parts = list(loc)
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

    for entry in entries:
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
                    "Write it as YYYY-MM-DD."))

            window = version.get("claim_window")
            if window is not None:
                problem = _duration_error(window, f"{scope} version {i} claim_window")
                if problem:
                    out.append(ConfigError(
                        src.name, scope,
                        f"version {i}'s claim_window {problem}",
                        "Write a duration with its unit, like 14d or 4h. This is never "
                        "guessed at - a bare number could mean either."))

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
    return out


# ---- datasets -------------------------------------------------------

def _dataset_errors(raw: dict, src: Source) -> list[ConfigError]:
    out: list[ConfigError] = []
    calendars = {(c or {}).get("name"): (c or {}) for c in (raw.get("calendars") or [])}

    for dataset, _collection in _walk_datasets(raw):
        dataset = dataset or {}
        dataset_id = dataset.get("id")
        scope = f"dataset {dataset_id!r}"
        named = dataset.get("calendar")

        if not named:
            out.append(ConfigError(
                src.name, scope,
                "names no `calendar:`.",
                f"Add one of: {', '.join(sorted(n for n in calendars if n))}. Without it "
                f"there is nothing to judge this dataset's supplies against."))
            continue
        if named not in calendars:
            out.append(ConfigError(
                src.name, scope,
                f"names calendar {named!r}, which this asset does not define.",
                f"Use one of: {', '.join(sorted(n for n in calendars if n))}, or add that "
                f"calendar. A dataset on a calendar that does not exist expects nothing."))
            continue

        months = dataset.get("delivery_months")
        overrides = dataset.get("dates")

        if months and overrides:
            out.append(ConfigError(
                src.name, scope,
                "carries BOTH `delivery_months:` and its own `dates:`.",
                "Keep one. Subsetting a calendar and replacing it are different acts, and "
                "carrying both leaves no way to tell which was meant."))

        out.extend(_month_errors(scope, named, calendars[named], months, src))

        if overrides is not None and not overrides:
            out.append(ConfigError(
                src.name, scope,
                "has a `dates:` key with nothing in it.",
                "Remove the key to use the calendar's own dates, or author real ones. As "
                "written this dataset expects nothing."))
        if months is not None and not months:
            out.append(ConfigError(
                src.name, scope,
                "has a `delivery_months:` key with nothing in it.",
                "Remove the key to take every period, or name the months. As written this "
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
            f"names delivery_months against {calendar_name!r}, which is a cadence RULE "
            f"rather than an authored date list.",
            "Remove delivery_months. A rule-driven calendar has no months to pick from, and "
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
                f"names delivery month {value!r}, which is not a month.",
                f"Write the full English month name - one of: {', '.join(_MONTHS)}."))
        elif available and number not in available:
            out.append(ConfigError(
                src.name, scope,
                f"names delivery month {value!r}, which calendar {calendar_name!r} has no "
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
                "Something in this dataset's calendar, delivery_months, dates or "
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
        if not isinstance(doc, dict) or "slaProperties" not in doc:
            continue  # a checks file or similar, not a dataset contract
        out.append(ConfigError(
            path.name, None,
            "is a data contract that no collection in the hierarchy names.",
            "Add a `contract:` line to the collection it describes, or delete it. A "
            "contract nothing points at is checked by nothing."))

    out.extend(_grace_errors(declared, src))
    return out


def _grace_errors(declared: dict[str, str], src: Source) -> list[ConfigError]:
    """A negative grace allowance is a deadline before the deadline."""
    out: list[ConfigError] = []
    for filename in sorted(declared):
        path = src.contract_dir / filename
        if not path.exists():
            continue
        try:
            doc = yaml.safe_load(path.read_text()) or {}
        except yaml.YAMLError:
            continue
        for item in (doc.get("slaProperties") or []):
            if (item or {}).get("property") != "latency":
                continue
            element = item.get("element")
            scope = f"element {element!r}" if element else None
            try:
                minutes = int(item.get("value"))
            except (TypeError, ValueError):
                out.append(ConfigError(
                    filename, scope,
                    f"latency is {item.get('value')!r}, which is not a number of minutes.",
                    "Write a whole number of minutes."))
                continue
            if minutes < 0:
                out.append(ConfigError(
                    filename, scope,
                    f"latency is {minutes}, which is negative.",
                    "Write zero or more. A negative grace allowance makes a supply late "
                    "before it is due."))
    return out


# ---- a past date cannot move quietly --------------------------------

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


def _changelog_at(doc: dict, calendar_name: str, effective: str) -> list[str]:
    for calendar in (doc.get("calendars") or []):
        if (calendar or {}).get("name") != calendar_name:
            continue
        for version in ((calendar or {}).get("versions") or []):
            if str((version or {}).get("effective_from")) == effective:
                return [str(x) for x in ((version or {}).get("changelog") or [])]
    return []


def _retrospective_edit_errors(raw: dict, src: Source, today: date | None = None,
                                ref: str = "HEAD~1") -> list[ConfigError]:
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
      - A changelog entry on that version clears it. This is a "say
        what you did" gate, not a freeze - Thread E allows a correction,
        it just will not have one happen quietly.
      - Silent when there is no previous commit to compare against,
        rather than failing. A shallow checkout or a first commit is
        not a finding.
    """
    today = today or date.today()
    previous = _content_at(str(src.asset_path.relative_to(ROOT)), ref) \
        if src.asset_path.is_relative_to(ROOT) else None
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
        if _changelog_at(raw, calendar_name, effective) != old_changelog:
            continue  # the version says what changed, which is all this asks

        what = f"is now {new_value}" if new_value else "has been removed"
        out.append(ConfigError(
            src.name, f"calendar {calendar_name!r}",
            f"period {period!r} was {old_value}, a date already in the past, and {what} - "
            f"with no new changelog entry on the version effective {effective}.",
            "Add a changelog entry saying what changed and why, or author a NEW "
            "effective-dated version instead. Moving a past date rewrites whether "
            "supplies already judged against it were on time."))
    return out


# ---- the gate -------------------------------------------------------

def validate(src: Source | None = None) -> list[ConfigError]:
    src = src or Source.default()
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

    errors = _schema_errors(raw, src)
    errors += _calendar_errors(raw, src)
    errors += _dataset_errors(raw, src)
    errors += _expects_nothing_errors(raw, src)
    errors += _contract_errors(raw, src)
    errors += _retrospective_edit_errors(raw, src)
    return errors


def _report(errors: list[ConfigError]) -> None:
    """Grouped by file, then by the calendar or dataset to open.

    Every offending item appears, individually - Keith's own call,
    2026-09-23, against a recommendation to suppress errors caused by
    an earlier one. Nothing is hidden, and the count in the header is
    the true count. The grouping is what carries the scale problem
    instead.
    """
    datasets = {e.scope for e in errors if e.scope and e.scope.startswith("dataset ")}
    subject = f"{len(datasets)} dataset(s)" if datasets else "the asset's own configuration"
    print(f"schedule validation FAILED - {len(errors)} error(s) affecting {subject}:",
          file=sys.stderr)

    by_file: dict[str, dict[str | None, list[ConfigError]]] = defaultdict(lambda: defaultdict(list))
    for error in errors:
        by_file[error.file][error.scope].append(error)

    for filename in sorted(by_file):
        print(f"\n  {filename}", file=sys.stderr)
        scopes = by_file[filename]
        for scope in sorted(scopes, key=lambda s: (s is not None, s or "")):
            if scope:
                print(f"    {scope}", file=sys.stderr)
            for error in scopes[scope]:
                indent = "      " if scope else "    "
                print(f"{indent}- {error.problem}\n{indent}  {error.fix}", file=sys.stderr)


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
    print(f"schedule validation OK - {n_calendars} calendar(s), {n_datasets} dataset(s), "
          f"every one of them expecting something.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
