"""A delivery agreement's past changes only by a declared correction
(REQ-PIPE-111).

WHAT IS FROZEN, AND FROM WHEN (criterion 2). Every item of the agreement
that can govern a filing - a calendar's dated entry, a calendar version, a
participation version, a not_expected entry, a dataset's own authored
dates and their versions, a timezone version - is FROZEN from the first
instant it can govern one: for a dated entry, the earliest claim-opening
instant any dataset on its calendar has for that period (that instant also
closes each one's previous period, REQ-PIPE-131); for a not_expected entry,
that dataset's claim-opening for the period; for a version, the earlier of
the start of its effective-from date and the earliest claim-opening of any
period it governs. Every instant comes from `slots.slot_instants`, the one
slot-instants function filing uses, so this gate and filing cannot disagree
about when something started to matter.

WHAT MAY CHANGE IT (criteria 3-5, 21, 22). Only a declared correction,
appended to the `corrections:` list of the item that owns the change - a
calendar's on that calendar, a dataset's on its entry, the zone's on the
timezone - naming its change reference, date, author, approver, reason and
each changed item with its old and new value. The values must match what
the file actually did ("you declared X; the file had Y"); the list is
append-only; the approver must be a real person allowed to approve, as
people.yaml stood at the base of the change. An ordinary changelog line is
no licence at all (criterion 6): that was REQ-PIPE-050's guard, which this
replaces.

WHAT NEEDS NO CEREMONY. An item not yet frozen (criterion 10). Dates
appended after a calendar's last one, even already past, where no dataset
on it would see its last slot's closing move (criterion 8) - extending an
exhausted schedule. On a synthetic asset, ADDING a past-dated calendar,
participation or timezone version, or restating on a frozen version a value
it left out at that value's default (criterion 9).

THE CLOCK (criterion 12) is the committer instant of the commit that
introduced the change, floored at the base commit's - never the author
date, which can be backdated. Where the change is not committed yet (the
pre-commit hook, comparing the staged file against HEAD), it is now.

CONFIGURATION ONLY (criterion 16): two versions of two files, git, and the
slot arithmetic - no database and nothing under data/.
"""
from __future__ import annotations

import copy
import json
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import yaml

from qa_tools.common import asset_time

ROOT = Path(__file__).resolve().parent.parent.parent
CALENDAR_REL = "contract/calendar.yaml"
ASSET_REL = "contract/data-asset.yaml"
PEOPLE_REL = "contract/people.yaml"
CODEOWNERS_REL = ".github/CODEOWNERS"

#: PROVISIONAL (overnight #3, 2026-10-11): the role in contract/people.yaml
#: that may approve a correction. Criterion 22 says "allowed to approve"
#: without naming a role; manager is the one that already signs things off.
APPROVER_ROLE = "manager"

#: The decision a person records after the fact for a period a dataset
#: turned out to owe nothing in (REQ-PIPE-132) - named in a not_expected
#: refusal (criterion 15).
MARK_NOT_SUPPLIED = ("mothman supply decide --operation mark-not-supplied "
                     "--dataset <id> --period <p> --reason <why>")


# ---- the items ------------------------------------------------------

@dataclass(frozen=True)
class Item:
    """One freezable thing, named exactly as a correction names it."""

    key: str
    owner: tuple            # ("calendar", name) | ("dataset", id) | ("timezone",)
    kind: str
    value: object           # plain YAML-able value
    ctx: dict = field(default_factory=dict, compare=False, hash=False)

    @property
    def norm(self) -> str:
        return _norm(self.value)


def _plain(value):
    """Dates to ISO strings, recursively - so a value read by PyYAML and the
    same value read by the loader compare equal."""
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _norm(value) -> str:
    return json.dumps(_plain(value), sort_keys=True, default=str)


def _windows(versions: list[dict]) -> list[tuple[str, str | None]]:
    starts = sorted(str((v or {}).get("effective_from")) for v in versions)
    return [(a, starts[i + 1] if i + 1 < len(starts) else None) for i, a in enumerate(starts)]


_SKIPPED = ("changelog", "corrections")
#: A turn-off is ITS OWN ITEM (REQ-PIPE-179 criteria 11 and 12, amending
#: REQ-PIPE-111 criterion 2): it freezes when the periods it flips start to
#: matter, not when its version took effect.
_TURN_OFF_KEYS = ("effective_to", "turned_off_reason")


def _turn_off_item(add, key: str, owner: tuple, v: dict, ctx: dict) -> None:
    """The turn-off of one version, where it states one - its effective_to
    and its turned_off_reason, frozen together (criterion 12)."""
    if not any(k in v for k in _TURN_OFF_KEYS):
        return
    add(Item(f"{key} effective_to", owner, "turn_off",
             _plain({k: v[k] for k in _TURN_OFF_KEYS if k in v}), dict(ctx)))


def flatten(cal_doc: dict, asset_doc: dict) -> dict[str, Item]:
    """Every freezable item of one state of the two files, by key.

    Changelog lines are not items: adding one changes nothing that governs
    a filing. Corrections are not items either - they have their own rule,
    append-only (criterion 21)."""
    out: dict[str, Item] = {}

    def add(item: Item):
        out[item.key] = item

    for cal in (cal_doc or {}).get("calendars") or []:
        cal = cal or {}
        name = str(cal.get("name"))
        versions = [(v or {}) for v in (cal.get("versions") or [])]
        windows = dict(_windows(versions))
        for v in versions:
            eff = str(v.get("effective_from"))
            end = windows.get(eff)
            dates = sorted(str((d or {}).get("date")) for d in (v.get("dates") or []))
            inside = [d for d in dates if d >= eff and (end is None or d < end)]
            first = inside[0] if inside else (eff if v.get("cadence") else None)
            add(Item(f"calendar {name} version {eff}", ("calendar", name), "cal_version",
                     _plain({k: val for k, val in v.items()
                             if k not in _SKIPPED + ("dates", "effective_from")}),
                     {"calendar": name, "eff": eff, "first": first}))
            # THE DATES IN FORCE, not the entries listed (delivery-critic on
            # 111, H1): a version that starts later takes the earlier one's
            # later dates out of force without touching a line of it, and
            # that is a removal of frozen dates like any other. Keyed by
            # period, so restating a date unchanged in a new version is no
            # change at all.
            for d in (v.get("dates") or []):
                d = d or {}
                when = str(d.get("date"))
                if when < eff or (end is not None and when >= end):
                    continue
                add(Item(f"calendar {name} period {d.get('period')}",
                         ("calendar", name), "cal_date", _plain(d.get("date")),
                         {"calendar": name, "date": when, "version": eff}))
    for entry in (cal_doc or {}).get("datasets") or []:
        entry = entry or {}
        ds = str(entry.get("id"))
        owner = ("dataset", ds)
        versions = [(v or {}) for v in (((entry.get("participation") or {}).get("versions")) or [])]
        windows = dict(_windows(versions))
        for v in versions:
            eff = str(v.get("effective_from"))
            add(Item(f"dataset {ds} participation {eff}", owner, "participation",
                     _plain({k: val for k, val in v.items()
                             if k not in _SKIPPED + _TURN_OFF_KEYS + ("effective_from",)}),
                     {"dataset": ds, "eff": eff, "end": windows.get(eff)}))
            _turn_off_item(add, f"dataset {ds} participation {eff}", owner, v,
                           {"datasets": [ds]})
        for ne in entry.get("not_expected") or []:
            ne = ne or {}
            add(Item(f"dataset {ds} not_expected {ne.get('period')}", owner, "not_expected",
                     _plain(ne.get("reason")), {"dataset": ds, "period": str(ne.get("period"))}))
        own = [(v or {}) for v in (((entry.get("dates") or {}).get("versions")) or [])]
        own_windows = dict(_windows(own))
        for v in own:
            eff = str(v.get("effective_from"))
            end = own_windows.get(eff)
            dates = sorted(str((d or {}).get("date")) for d in (v.get("dates") or []))
            add(Item(f"dataset {ds} dates version {eff}", owner, "own_version",
                     _plain({k: val for k, val in v.items()
                             if k not in _SKIPPED + ("dates", "effective_from")}),
                     {"dataset": ds, "eff": eff, "first": dates[0] if dates else None}))
            for d in (v.get("dates") or []):
                d = d or {}
                when = str(d.get("date"))
                if when < eff or (end is not None and when >= end):
                    continue
                add(Item(f"dataset {ds} dates period {d.get('period')}", owner,
                         "own_date", _plain(d.get("date")), {"dataset": ds, "date": when}))
    # A COLLECTION'S DEFAULTS FREEZE LIKE A DATASET'S OWN VERSIONS
    # (REQ-PIPE-181, amending REQ-PIPE-111 criterion 4): a value its datasets
    # take governs their filings as much as one they state, and the
    # collection carries its own corrections list.
    for coll in (cal_doc or {}).get("collections") or []:
        coll = coll or {}
        cid = str(coll.get("id"))
        versions = [(v or {}) for v in
                    (((coll.get("participation_defaults") or {}).get("versions")) or [])]
        windows = dict(_windows(versions))
        for v in versions:
            eff = str(v.get("effective_from"))
            add(Item(f"collection {cid} participation_defaults {eff}", ("collection", cid),
                     "defaults",
                     _plain({k: val for k, val in v.items()
                             if k not in _SKIPPED + _TURN_OFF_KEYS + ("effective_from",)}),
                     {"collection": cid, "eff": eff, "end": windows.get(eff)}))
            _turn_off_item(add, f"collection {cid} participation_defaults {eff}",
                           ("collection", cid), v, {"collection": cid})
        # A COLLECTION'S files_go_to_period FREEZES LIKE ANY OTHER VERSION
        # (REQ-PIPE-320 criterion 8, REQ-PIPE-111 criterion 2 as amended): it
        # moves due instants, claim windows and filings.
        offsets = [(v or {}) for v in
                   (((coll.get("files_go_to_period") or {}).get("versions")) or [])]
        offset_windows = dict(_windows(offsets))
        for i, v in enumerate(offsets):
            eff = str(v.get("effective_from"))
            add(Item(f"collection {cid} files_go_to_period {eff}", ("collection", cid),
                     "offset_version", _plain(v.get("value")),
                     {"collection": cid, "eff": eff, "end": offset_windows.get(eff),
                      "first_version": i == 0}))
    # WHICH CALENDAR EACH DATASET IS ON, as resolved (delivery-critic on
    # 111, H2; PROVISIONAL, Keith's fork from REQ-PIPE-110 and
    # plans/running-thoughts.md #79): moving a dataset - or its whole
    # collection - to another calendar, or to none, re-judges its history
    # against a different schedule, so it freezes like a date. Per dataset,
    # on the dataset's own entry, because that is the owner a correction
    # names; a collection move is one change to each of its datasets.
    collections = {(c or {}).get("id"): (c or {}).get("calendar")
                   for c in (cal_doc or {}).get("collections") or []}
    entries = {(e or {}).get("id"): (e or {}) for e in (cal_doc or {}).get("datasets") or []}
    for agency in (((asset_doc or {}).get("hierarchy") or {}).get("agencies") or []):
        for coll in ((agency or {}).get("collections") or []):
            for dataset in ((coll or {}).get("datasets") or []):
                ds = str((dataset or {}).get("id"))
                entry = entries.get(ds, {})
                if entry.get("no_calendar") is not None:
                    value = f"no calendar ({entry['no_calendar']})"
                else:
                    value = entry.get("calendar") or collections.get((coll or {}).get("id"))
                if value is None:
                    continue
                add(Item(f"dataset {ds} calendar", ("dataset", ds), "membership", value,
                         {"dataset": ds}))

    tz = (asset_doc or {}).get("timezone") or {}
    for v in (tz.get("versions") or []) if isinstance(tz, dict) else []:
        v = v or {}
        eff = str(v.get("effective_from"))
        add(Item(f"timezone version {eff}", ("timezone",), "tz_version", _plain(v.get("zone")),
                 {"eff": eff, "zone": str(v.get("zone"))}))
    return out


# ---- when each one froze --------------------------------------------

def _datasets_on(calendar_name: str, agr) -> list[str]:
    from qa_tools.common import hierarchy

    out = []
    for entry in hierarchy.all_datasets():
        own = agr.dataset(entry.dataset_id)
        if own is not None and own.no_calendar is not None:
            continue
        try:
            if agr.calendar_name_for(entry.dataset_id) == calendar_name:
                out.append(entry.dataset_id)
        except Exception:  # noqa: BLE001 - not in this state's agreement
            continue
    return out


def _claim_open(dataset_id: str, day: date, agr) -> datetime | None:
    from qa_tools.common import schedule, slots

    try:
        return slots.slot_instants(dataset_id, day, agr).claim_opens_at
    except (schedule.ScheduleConfigError, KeyError, ValueError):
        return None


def _first_period_on_or_after(dataset_id: str, day: date, end: date | None, agr) -> date | None:
    from qa_tools.common import schedule, slots

    try:
        periods = slots._calendar_periods(dataset_id, day + timedelta(days=400), agr)
    except (schedule.ScheduleConfigError, KeyError, ValueError):
        return None
    dates = [p.date for p in periods if p.date >= day and (end is None or p.date < end)]
    return min(dates) if dates else None


def _counts_on(dataset_id: str, day: date, agr) -> bool:
    """Whether a dataset counts in a dated entry's freeze (REQ-PIPE-179
    criterion 30, amending REQ-PIPE-111 criterion 2): always, unless it is
    turned off on that day - then only for the first period of its gap,
    whose opening closes its last owed slot."""
    from qa_tools.common import agreement

    try:
        standing = agr.standing_on(dataset_id, day)
    except Exception:  # noqa: BLE001 - not in this state's agreement
        return True
    if standing.state != agreement.TURNED_OFF:
        return True
    try:
        first = _first_period_on_or_after(dataset_id, standing.turned_off.effective_to
                                          + timedelta(days=1), None, agr)
    except Exception:  # noqa: BLE001
        return True
    return first == day


def _min(*values):
    present = [v for v in values if v is not None]
    return min(present) if present else None


def freeze_instant(item: Item, agr) -> datetime | None:
    """The first instant `item` could govern a filing, in the state that
    holds it - or None where it can govern none (a not_expected period that
    is not one of the dataset's)."""
    c = item.ctx
    if item.kind == "cal_date":
        day = date.fromisoformat(c["date"])
        opens = [_claim_open(ds, day, agr) for ds in _datasets_on(c["calendar"], agr)
                 if _counts_on(ds, day, agr)]
        return _min(*opens) or asset_time.start_of_day(day)
    if item.kind == "cal_version":
        eff = date.fromisoformat(c["eff"])
        first = date.fromisoformat(c["first"]) if c.get("first") else None
        opens = ([_claim_open(ds, first, agr) for ds in _datasets_on(c["calendar"], agr)]
                 if first else [])
        return _min(asset_time.start_of_day(eff), *opens)
    if item.kind == "participation":
        eff = date.fromisoformat(c["eff"])
        end = date.fromisoformat(c["end"]) if c.get("end") else None
        first = _first_period_on_or_after(c["dataset"], eff, end, agr)
        return _min(asset_time.start_of_day(eff),
                    _claim_open(c["dataset"], first, agr) if first else None)
    if item.kind == "defaults":
        # The earliest instant any dataset taking it could be filed under it.
        eff = date.fromisoformat(c["eff"])
        end = date.fromisoformat(c["end"]) if c.get("end") else None
        opens = []
        for ds in agr.datasets:
            if agr.collection_of(ds) != c["collection"] or not agr.defaults_for(ds):
                continue
            first = _first_period_on_or_after(ds, eff, end, agr)
            if first:
                opens.append(_claim_open(ds, first, agr))
        return _min(asset_time.start_of_day(eff), *opens)
    if item.kind == "offset_version":
        # As a collection's defaults: the earliest instant any of its
        # datasets could be filed under it - a slot due on a round it governs.
        eff = date.fromisoformat(c["eff"])
        end = date.fromisoformat(c["end"]) if c.get("end") else None
        opens = []
        for ds in agr.datasets:
            if agr.collection_of(ds) != c["collection"]:
                continue
            first = _first_period_on_or_after(ds, eff, end, agr)
            if first:
                opens.append(_claim_open(ds, first, agr))
        return _min(asset_time.start_of_day(eff), *opens)
    if item.kind == "not_expected":
        from qa_tools.common import slots

        try:
            periods = slots._calendar_periods(c["dataset"], None, agr)
        except Exception:  # noqa: BLE001 - a cadence rule needs a bound
            periods = slots._calendar_periods(
                c["dataset"], asset_time.local_date(datetime.now(UTC)) + timedelta(days=400), agr)
        match = next((p for p in periods if p.name == c["period"]), None)
        return _claim_open(c["dataset"], match.date, agr) if match else None
    if item.kind == "own_version":
        eff = date.fromisoformat(c["eff"])
        first = date.fromisoformat(c["first"]) if c.get("first") else None
        return _min(asset_time.start_of_day(eff),
                    _claim_open(c["dataset"], first, agr) if first else None)
    if item.kind == "own_date":
        day = date.fromisoformat(c["date"])
        return _claim_open(c["dataset"], day, agr) or asset_time.start_of_day(day)
    if item.kind == "membership":
        # From the first instant the dataset's first slot could be filed:
        # its first participation version's freeze point.
        own = agr.dataset(c["dataset"])
        if own is None or not own.participation:
            return None
        first = own.participation[0]
        probe = Item("", ("dataset", c["dataset"]), "participation", None,
                     {"dataset": c["dataset"], "eff": first.effective_from.isoformat(),
                      "end": None})
        return freeze_instant(probe, agr)
    if item.kind == "tz_version":
        from zoneinfo import ZoneInfo

        from qa_tools.common import hierarchy

        eff = date.fromisoformat(c["eff"])
        try:
            starts = datetime.combine(eff, datetime.min.time(), tzinfo=ZoneInfo(c["zone"]))
        except Exception:  # noqa: BLE001 - an unknown zone is the schema's to report
            starts = asset_time.start_of_day(eff)
        opens = []
        for entry in hierarchy.all_datasets():
            first = _first_period_on_or_after(entry.dataset_id, eff, None, agr)
            if first:
                opens.append(_claim_open(entry.dataset_id, first, agr))
        return _min(starts, *opens)
    return None


# ---- the clock ------------------------------------------------------

def _git(*args: str, root: Path | None = None) -> str | None:
    result = subprocess.run(["git", *args], cwd=root or ROOT, capture_output=True, text=True)
    return result.stdout if result.returncode == 0 else None


def committer_instant(ref: str, root: Path | None = None) -> datetime | None:
    """A commit's COMMITTER instant - never its author date, which a person
    can set to anything (criterion 12; REQ-PIPE-111 decision 22)."""
    out = _git("log", "-1", "--format=%cI", ref, root=root)
    return datetime.fromisoformat(out.strip()) if out and out.strip() else None


def commits_since(ref: str, rel_paths: tuple[str, ...]) -> list[tuple[str, datetime]]:
    """(sha, committer instant) for each commit after `ref` touching any of
    `rel_paths`, oldest first."""
    out = _git("log", "--reverse", "--format=%H %cI", f"{ref}..HEAD", "--", *rel_paths)
    rows = []
    for line in (out or "").splitlines():
        sha, _, stamp = line.partition(" ")
        if sha and stamp:
            rows.append((sha, datetime.fromisoformat(stamp)))
    return rows


# ---- the corrections ------------------------------------------------

def _corrections_by_owner(cal_doc: dict, asset_doc: dict) -> dict[tuple, list]:
    out: dict[tuple, list] = {}
    for cal in (cal_doc or {}).get("calendars") or []:
        out[("calendar", str((cal or {}).get("name")))] = list((cal or {}).get("corrections") or [])
    for entry in (cal_doc or {}).get("datasets") or []:
        out[("dataset", str((entry or {}).get("id")))] = list((entry or {}).get("corrections") or [])
    for coll in (cal_doc or {}).get("collections") or []:
        out[("collection", str((coll or {}).get("id")))] = list((coll or {}).get("corrections") or [])
    tz = (asset_doc or {}).get("timezone") or {}
    if isinstance(tz, dict):
        out[("timezone",)] = list(tz.get("corrections") or [])
    return out


def _owner_label(owner: tuple) -> str:
    if owner[0] == "timezone":
        return "the timezone in contract/data-asset.yaml"
    return f"{owner[0]} {owner[1]!r} in contract/calendar.yaml"


def approvers(people_doc: dict) -> list[dict]:
    """Who may approve a correction, as people.yaml stood at the base of the
    change (criterion 22): a real person - not a placeholder, not the
    synthetic history's scripted one - ASSIGNED the manager role AT
    DATA-ASSET LEVEL for this asset (REQ-GHUB-171 criterion 4).

    PROVISIONAL (overnight #3, post-build-review #141): the first build read
    each person's own `roles:` list, so a real AGENCY manager could approve a
    correction to the whole asset's agreement, and removing `manager` from
    the asset manager's roles left the gate green and nobody able to approve.
    The level of the assignment, not the name of the role, says whose
    decision it is (REQ-GHUB-171 decision 2)."""
    from qa_tools.common import people as people_mod

    asset = people_mod.this_asset_id()
    managers = {(a or {}).get("person") for a in (people_doc or {}).get("assignments") or []
                if (a or {}).get(people_mod.DATA_ASSET) == asset
                and (a or {}).get("role") == APPROVER_ROLE}
    return [p for p in ((people_doc or {}).get("people") or [])
            if not p.get("placeholder") and not p.get("synthetic")
            and p.get("email") in managers]


def _person_named(name: str, allowed: list[dict]) -> dict | None:
    name = str(name).strip().lower()
    return next((p for p in allowed
                 if name in {str(p.get("email", "")).lower(), str(p.get("github", "")).lower()}),
                None)


def _pattern_matches(pattern: str, path: str) -> bool:
    """One CODEOWNERS pattern against a repository-relative path, in
    GitHub's terms: a leading `/` anchors it to the root, a trailing `/`
    names a directory, an unanchored pattern without a `/` matches at any
    depth, a plain path also owns everything under it, and `*` never
    crosses a `/` - only `**` does (delivery-critic on 174, M4: fnmatch's
    `*` crossed it, so `/*.yaml` owned contract/calendar.yaml, which on
    GitHub it does not).
    """
    import re

    anchored = pattern.startswith("/")
    pat = pattern.lstrip("/")
    if not pat:
        return False
    directory = pat.endswith("/")
    pat = pat.rstrip("/")
    globbed = any(c in pat for c in "*?[")

    def rx(text: str) -> str:
        out, k = "", 0
        while k < len(text):
            if text.startswith("**", k):
                out, k = out + ".*", k + 2
            elif text[k] == "*":
                out, k = out + "[^/]*", k + 1
            elif text[k] == "?":
                out, k = out + "[^/]", k + 1
            else:
                out, k = out + re.escape(text[k]), k + 1
        return out

    body = rx(pat)
    if not anchored and "/" not in pat:
        body = f"(?:.*/)?{body}"
    # A PLAIN PATH OR A DIRECTORY owns what is under it; a glob owns only
    # what it matches (GitHub: `docs/*` does not own docs/a/b.md).
    under = "(?:/.*)?" if (directory or not globbed) else ""
    return re.fullmatch(body + under, path) is not None


def code_owners(codeowners_text: str | None, path: str) -> set[str]:
    """The GitHub accounts .github/CODEOWNERS makes owners of `path`,
    lower-cased and without the `@` (REQ-GHUB-174 criterion 2). The LAST
    matching line wins, as on GitHub; a line with no owners un-owns."""
    owners: set[str] = set()
    for raw in (codeowners_text or "").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        pattern, *who = line.split()
        if _pattern_matches(pattern, path):
            owners = {w[1:].lower() for w in who
                      if w.startswith("@") and len(w) > 1 and "/" not in w}
    return owners


# ---- the gate -------------------------------------------------------

@dataclass
class Finding:
    file: str
    scope: str | None
    problem: str
    fix: str


def _value_text(value) -> str:
    if value is None:
        return "(nothing)"
    # ONE LINE, however long: wrapped at YAML's default eighty columns, a
    # long reason broke the pasted entry's indentation (REQ-PIPE-181's
    # migration, 2026-10-11).
    return yaml.safe_dump(_plain(value), default_flow_style=True, sort_keys=False,
                          width=10**6).strip()


def _quoted(value: str) -> str:
    """A free-text answer as a YAML scalar that parses back to itself."""
    return yaml.safe_dump(value, default_flow_style=True, width=10**6).strip().removesuffix(
        "\n...").strip()


def _paste_ready(owner: tuple, changes: list[tuple[str, object, object]], allowed: list[dict],
                 today: date, *, reference: str | None = None, author: str | None = None,
                 approver: str | None = None, reason: str | None = None) -> str:
    """The correction entry to paste - placeholders for whatever was not
    given (REQ-PIPE-169 criterion 14), the same text the refusal prints."""
    who = ", ".join(p.get("email") for p in allowed) or "nobody - people.yaml names no approver"
    lines = [f"Add to the corrections list of {_owner_label(owner)}:",
             "  corrections:",
             f"    - change_reference: {_quoted(reference) if reference else '<CHANGE-REF>'}",
             f"      date: '{today.isoformat()}'",
             f"      author: {_quoted(author) if author else '<you>'}",
             f"      approver: {_quoted(approver) if approver else '<one of the people below>'}",
             f"      reason: {_quoted(reason) if reason else '<why the agreement was wrong>'}",
             "      changes:"]
    for key, old, new in changes:
        # null, not the "(nothing)" a reader is shown: this block is pasted
        # and parsed, and a string would never match (delivery-critic, M1).
        lines += [f"        - item: {key}",
                  f"          old: {'null' if old is None else _value_text(old)}",
                  f"          new: {'null' if new is None else _value_text(new)}"]
    lines.append(f"May approve: {who}.")
    lines.append("Preview what this would re-judge and move before asking for approval, and "
                 "attach it to the change reference: `mothman schedule preview-correction "
                 "--output impact.md`.")
    return "\n".join(lines)


def old_asset_like(new_asset: dict) -> dict:
    """The asset file with no previous state, standing in as its own
    previous state for every item it holds."""
    return dict(new_asset or {})


def _agreements(old_cal: dict | None, new_cal: dict):
    """(new, old) agreements; raises where the NEW file cannot be read."""
    from qa_tools.common import agreement

    new_agr = agreement.from_doc(new_cal)
    try:
        old_agr = agreement.from_doc(old_cal) if old_cal else None
    except Exception:  # noqa: BLE001
        # An OLD state today's loader cannot read still has its changes
        # checked, against freeze instants from the new state, rather than
        # the whole check being skipped (delivery-critic, L2).
        old_agr = new_agr
    return new_agr, old_agr


def _turn_off_datasets(item: Item, agr) -> list[str]:
    """The datasets a turn-off item applies to - its own dataset, or every
    dataset taking its collection's defaults."""
    if item.ctx.get("datasets"):
        return list(item.ctx["datasets"])
    return [ds for ds in agr.datasets
            if agr.collection_of(ds) == item.ctx.get("collection") and agr.defaults_for(ds)]


#: How far past the earlier effective_to a flipped period is looked for - the
#: FIRST flipped period is the freeze, and it is never further than a period.
_FLIP_REACH = timedelta(days=800)


def _flipped(item: Item, before, after, old_agr, new_agr) -> list[tuple[str, str, datetime]]:
    """(dataset, period, earliest claim-opening) for every period whose
    owed-or-not status this turn-off change flips - each opening the
    earlier of its values under the configuration before and after
    (REQ-PIPE-179 criterion 11), computed with criterion 14's inputs. A
    change of the reason alone flips nothing, and freezes with the periods
    it already turned off (criterion 12)."""
    from qa_tools.common import agreement, slots

    tos = [date.fromisoformat(str(v["effective_to"])) for v in (before, after)
           if isinstance(v, dict) and v.get("effective_to")]
    if not tos:
        return []
    start = min(tos)
    out = []
    for ds in sorted(set(_turn_off_datasets(item, old_agr)) | set(_turn_off_datasets(item, new_agr))):
        try:
            periods = slots._calendar_periods(ds, start + _FLIP_REACH, new_agr)
        except Exception:  # noqa: BLE001 - a dataset with no calendar flips nothing
            continue
        reason_only = len(tos) == 2 and tos[0] == tos[1]
        for p in periods:
            if p.date <= start:
                continue
            was = old_agr.standing_on(ds, p.date).state
            now = new_agr.standing_on(ds, p.date).state
            if was == now and not (reason_only and was == agreement.TURNED_OFF):
                continue
            opens = _min(_claim_open(ds, p.date, old_agr), _claim_open(ds, p.date, new_agr))
            if opens is not None:
                # EVERY ONE, not the first (post-build-review #190 D7): the
                # first is the freeze, and the refusal names each that has
                # opened by the time the change was introduced.
                # NAMED BY THE PERIOD THE ROUND FILLS (REQ-PIPE-179 criterion 11
                # as REQ-PIPE-321 amends it), not the round's own name.
                from qa_tools.common import schedule as schedule_mod

                filled = schedule_mod.period_filled_by(ds, p, new_agr)
                out.append((ds, filled.name if filled is not None else p.name, opens))
    return out


def _changed(old_items: dict, new_items: dict, old_agr, new_agr) -> dict:
    changes: dict[str, tuple[Item, object, object, datetime | None]] = {}
    for key in set(old_items) | set(new_items):
        before, after = old_items.get(key), new_items.get(key)
        if before is not None and after is not None and before.norm == after.norm:
            continue
        item = before or after
        if item.kind == "turn_off":
            flips = _flipped(item, before.value if before else None,
                             after.value if after else None, old_agr or new_agr, new_agr)
            item.ctx["flipped"] = flips
            changes[key] = (item, before.value if before else None,
                            after.value if after else None,
                            _min(*(opens for _d, _p, opens in flips)))
            continue
        if before is not None and old_agr is not None:
            frozen_at = freeze_instant(before, old_agr)   # a change or a removal
        else:
            frozen_at = freeze_instant(after, new_agr)    # an addition
        changes[key] = (before or after, before.value if before else None,
                        after.value if after else None, frozen_at)
    return changes


def changed(old_cal: dict, new_cal: dict, old_asset: dict, new_asset: dict) -> dict:
    """Every item that differs between two states of the agreement, by key:
    (item, old value, new value, the instant it froze or None) - the gate's
    own comparison, for the impact preview (REQ-PIPE-169) to share."""
    new_agr, old_agr = _agreements(old_cal, new_cal)
    return _changed(flatten(old_cal, old_asset), flatten(new_cal, new_asset), old_agr, new_agr)


def check(old_cal: dict | None, new_cal: dict, old_asset: dict | None, new_asset: dict,
          base_people: dict | None, instant_of=None, today: date | None = None, *,
          base_codeowners: str | None, needs: dict | None = None) -> list[Finding]:
    """Every refusal for one change from (old_cal, old_asset) to (new_cal,
    new_asset). `instant_of(item_key) -> datetime` is when that change was
    introduced (criterion 12); a missing previous state passes (criterion
    14). `base_codeowners` is .github/CODEOWNERS's text at the base, or
    None where it did not exist - REQUIRED, with no default, so no caller
    can leave the code-owner check out by forgetting it (REQ-GHUB-174).

    `needs`, where given, is filled with every undeclared frozen change by
    owner - what `drafts()` turns into correction entries (REQ-PIPE-169
    criterion 14), so the draft and the refusal are one computation."""
    if old_cal is None and old_asset is None:
        return []
    # A FILE WITH NO PREVIOUS STATE IS NOT COMPARED (criterion 14), even when
    # the other file has one - a new asset's calendar.yaml can postdate its
    # data-asset.yaml (delivery-critic, M2). Its items are taken as they now
    # stand on both sides.
    if old_cal is None:
        old_cal = new_cal
    if old_asset is None:
        old_asset = {**old_asset_like(new_asset)}
    today = today or asset_time.local_date(datetime.now(UTC))
    instant_of = instant_of or (lambda key: datetime.now(UTC))
    out: list[Finding] = []

    old_items, new_items = flatten(old_cal, old_asset), flatten(new_cal, new_asset)
    try:
        new_agr, old_agr = _agreements(old_cal, new_cal)
    except Exception:  # noqa: BLE001 - an unreadable NEW file is the schema gate's to report
        return []
    synthetic = bool(old_asset.get("synthetic")) and bool(new_asset.get("synthetic"))
    allowed = approvers(base_people or {})

    # WHAT ACTUALLY CHANGED, by item: (item, old value, new value, frozen at).
    changes = _changed(old_items, new_items, old_agr, new_agr)

    # CRITERION 8: appended dates after a calendar's last one, moving nothing.
    appended_ok: set[str] = set()
    if old_agr is not None:
        appended_ok = _appended_dates_allowed(changes, old_items, old_agr, new_agr)

    # CRITERION 21: a corrections list is append-only; and criteria 4, 5, 22
    # on what was appended.
    declared: set[str] = set()
    old_corr = _corrections_by_owner(old_cal, old_asset)
    new_corr = _corrections_by_owner(new_cal, new_asset)
    for owner, before in old_corr.items():
        if before and owner not in new_corr:
            file = "data-asset.yaml" if owner[0] == "timezone" else "calendar.yaml"
            out.append(Finding(file, f"{owner[0]} {owner[1]!r}" if len(owner) > 1 else owner[0],
                               "was removed, and its declared corrections with it - a "
                               "corrections list is append-only, and removing its owner "
                               "removes the record of every governed change it holds. "
                               "Nothing was committed.",
                               "Keep the entry and its corrections."))
    # A LATER-DATED VERSION KEEPS ITS CORRECTIONS (REQ-GEN-238, PROVISIONAL): on
    # a synthetic asset criterion 9 lets a past version be later-dated, and a
    # correction already naming it by its old date names it by its new one -
    # the only edit an existing correction may take, and only for that version.
    redated = _redated_versions(changes) if synthetic else {}
    for owner, entries in new_corr.items():
        before = old_corr.get(owner, [])
        file = "data-asset.yaml" if owner[0] == "timezone" else "calendar.yaml"
        where = owner[0] if owner[0] == "timezone" else f"{owner[0]} {owner[1]!r}"
        if [_norm(e) for e in entries[:len(before)]] != \
                [_norm(_redate_items(e, redated)) for e in before]:
            out.append(Finding(file, where,
                               "an existing declared correction was changed or removed - a "
                               "corrections list is append-only. Nothing was committed.",
                               "Restore the corrections already committed, exactly as they were, "
                               "and append a new one if something more needs correcting."))
            continue
        # A CODE OWNER OF THE FILE IT IS DECLARED IN (REQ-GHUB-174
        # criterion 2), at the base - so a change cannot make its approver.
        rel_file = ASSET_REL if owner[0] == "timezone" else CALENDAR_REL
        owners = code_owners(base_codeowners, rel_file)
        eligible = [p for p in allowed if str(p.get("github", "")).lower() in owners]
        for corr in entries[len(before):]:
            corr = corr or {}
            approver = corr.get("approver")
            person = _person_named(approver, allowed) if approver else None
            if approver and person is None:
                out.append(Finding(
                    file, where,
                    f"a correction names approver {approver!r}, who is not a person allowed to "
                    f"approve in contract/people.yaml as it stood before this change. Nothing "
                    f"was committed.",
                    "Name one of: " + (", ".join(p.get("email") for p in eligible) or "nobody") +
                    ". An approver added in the same change does not count."))
            elif approver and person not in eligible:
                why = (f"there was no {CODEOWNERS_REL} before this change"
                       if base_codeowners is None else
                       f"their GitHub account ({person.get('github') or 'none in people.yaml'}) "
                       f"is not a code owner of {rel_file} in {CODEOWNERS_REL} as it stood "
                       f"before this change")
                out.append(Finding(
                    file, where,
                    f"a correction names approver {approver!r}, but {why} - the approver must "
                    f"be someone whose review GitHub can require. Nothing was committed.",
                    "Name one of: " + (", ".join(p.get("email") for p in eligible) or "nobody") +
                    ". A code owner added in the same change does not count."))
            for change in corr.get("changes") or []:
                change = change or {}
                key = str(change.get("item"))
                actual = changes.get(key)
                if actual is None:
                    out.append(Finding(file, key,
                                       f"you declared {key} changing from "
                                       f"{_value_text(change.get('old'))} to "
                                       f"{_value_text(change.get('new'))}; the file had no change "
                                       f"to it. Nothing was committed.",
                                       "Declare only what this change actually does, naming each "
                                       "item exactly as the gate names it."))
                    continue
                item, old, new, _frozen = actual
                if item.owner != owner:
                    out.append(Finding(file, key,
                                       f"the correction for {key} is declared on {where}, and the "
                                       f"item belongs to {_owner_label(item.owner)}. Nothing was "
                                       f"committed.",
                                       f"Move it to the corrections list of "
                                       f"{_owner_label(item.owner)}."))
                    continue
                if _norm(change.get("old")) != _norm(old) or _norm(change.get("new")) != _norm(new):
                    out.append(Finding(
                        file, key,
                        f"you declared {_value_text(change.get('old'))} -> "
                        f"{_value_text(change.get('new'))}; the file had {_value_text(old)} -> "
                        f"{_value_text(new)}. Nothing was committed.",
                        "Make the declared old and new values match what the change does."))
                    continue
                declared.add(key)

    # CRITERIA 3 AND 7: a frozen item changed, removed or added undeclared.
    needs = {} if needs is None else needs
    for key, (item, old, new, frozen_at) in sorted(changes.items()):
        if key in declared or key in appended_ok or frozen_at is None:
            continue
        when = instant_of(key)
        if when < frozen_at:
            continue  # not frozen yet when introduced (criterion 10)
        if item.kind == "turn_off":
            item.ctx["flipped_open"] = [f for f in item.ctx.get("flipped", ()) if f[2] <= when]
        added = old is None
        # A NEW DATASET'S MEMBERSHIP TOO (criterion 9's own words; a real
        # defect found adding Emergency Department, 2026-10-18): its versions
        # were exempt and its calendar membership was not, so the push adding a
        # collection with a past-dated history was refused.
        if added and synthetic and item.kind in ("cal_version", "participation", "tz_version",
                                                  "defaults", "membership", "offset_version"):
            continue  # criterion 9
        # THE ADOPTION ALLOWANCE (REQ-PIPE-320 criterion 11): a collection's
        # FIRST files_go_to_period version stating 0 from its first round moves
        # no instant and no filing, so it lands on frozen rounds on any asset.
        if added and item.kind == "offset_version" and new == 0 and \
                item.ctx.get("first_version") and \
                not any(k.startswith(f"collection {item.ctx['collection']} files_go_to_period ")
                        for k in old_items):
            continue
        # CHANGING THE VALUE a files_go_to_period version states, on a
        # synthetic asset (REQ-PIPE-111 criterion 9 as REQ-PIPE-320 amends it).
        if synthetic and item.kind == "offset_version" and old is not None and new is not None:
            continue
        if added and synthetic and item.kind == "cal_date" and \
                f"calendar {item.ctx['calendar']} version {item.ctx['version']}" not in old_items:
            continue  # a date inside a version criterion 9 lets a synthetic asset add
        if synthetic and _restates_at_default(item, old, new, old_cal, old_asset):
            continue  # criterion 9, amended 2026-10-16
        # REMOVING OR LATER-DATING ONE (criterion 9 as amended 2026-10-15, built
        # with REQ-GEN-238): later-dating is the old date's version removed and
        # the new date's added, which the clause above already lets through.
        if new is None and synthetic and item.kind in _VERSION_KINDS:
            continue
        # AND THE PERIOD DATES OF A CALENDAR VERSION IT REMOVES OR LATER-DATES
        # (post-build-review #284 (4); Keith, 2026-10-29, option a): they go
        # with their version, as a version's dates arrive with it when one is
        # added. A date removed from a version that stays is still refused.
        if new is None and synthetic and item.kind == "cal_date" and \
                f"calendar {item.ctx['calendar']} version {item.ctx['version']}" \
                not in new_items:
            continue
        needs.setdefault(item.owner, []).append((item, old, new, frozen_at))

    for owner, rows in needs.items():
        file = "data-asset.yaml" if owner[0] == "timezone" else "calendar.yaml"
        # WHO MAY APPROVE IS WHO THE GATE WILL ACCEPT (delivery-critic on 174,
        # L1): the asset's managers who are also code owners of this file.
        owners = code_owners(base_codeowners, ASSET_REL if owner[0] == "timezone"
                             else CALENDAR_REL)
        may = [p for p in allowed if str(p.get("github", "")).lower() in owners]
        # ONE ENTRY PER OWNER (Keith, 2026-10-11, morning-report (l)): every
        # changed item of one owner in one correction, as draft-correction
        # gives it - one approval each, and the two never disagree.
        said = []
        for item, old, new, frozen_at in rows:
            verb = "added" if old is None else ("removed" if new is None else "changed")
            if item.kind == "turn_off":
                # REQ-PIPE-179 criterion 11: each period whose status it flips,
                # and the claim-opening instant that has passed for it.
                flips = "; ".join(
                    f"{ds} {period}, whose claim window opened "
                    f"{asset_time.localise(opens).isoformat(timespec='minutes')}"
                    for ds, period, opens in item.ctx.get("flipped_open",
                                                          item.ctx.get("flipped", ())))
                said.append(f"{item.key} was {verb} ({_value_text(old)} -> {_value_text(new)}), "
                            f"which changes whether a period already open is owed: {flips}")
                continue
            said.append(f"{item.key} was {verb} ({_value_text(old)} -> {_value_text(new)}) "
                        f"after it froze at "
                        f"{asset_time.localise(frozen_at).isoformat(timespec='minutes')}, the "
                        f"first instant it could govern a filing")
        fix = _paste_ready(owner, [(item.key, old, new) for item, old, new, _f in rows],
                           may, today)
        if any(item.kind == "turn_off" for item, *_ in rows):
            fix += ("\nOr draft it:\n  mothman schedule draft-correction"
                    "\nIf a period simply was not supplied, record that after the fact "
                    f"instead: `{MARK_NOT_SUPPLIED}`.")
        if any(item.kind == "not_expected" for item, *_ in rows):
            fix += ("\nIf a period simply was not supplied, record that after the fact "
                    f"instead: `{MARK_NOT_SUPPLIED}`.")
        out.append(Finding(
            file, ", ".join(item.key for item, *_ in rows),
            "; ".join(said) + ". Only a declared correction may change "
            + ("it" if len(rows) == 1 else "them") + ". Nothing was committed.",
            fix))
    return out


#: The version-level items criterion 9 lets a synthetic asset add, remove or
#: later-date without a declared correction.
_VERSION_KINDS = ("cal_version", "participation", "tz_version", "defaults", "offset_version")


def _redated_versions(changes: dict) -> dict[str, str]:
    """Each version this change later-dated, old key to new key: a version of
    one owner and kind removed and another added with the same value - so
    only its date moved."""
    removed = [(item, old) for item, old, new, _f in changes.values()
               if new is None and item.kind in _VERSION_KINDS]
    added = [(item, new) for item, old, new, _f in changes.values()
             if old is None and item.kind in _VERSION_KINDS]
    out: dict[str, str] = {}
    for gone, value in removed:
        same = [item for item, v in added if item.owner == gone.owner
                and item.kind == gone.kind and _norm(v) == _norm(value)
                and item.key not in out.values()]
        if len(same) == 1:
            out[gone.key] = same[0].key
    return out


def _redate_items(entry, redated: dict[str, str]):
    """`entry` (one declared correction) with each change naming a later-dated
    version - the version itself, or an item of it - named by its new date."""
    if not redated or not isinstance(entry, dict):
        return entry
    def rename(key: str) -> str:
        for old, new in redated.items():
            if key == old or key.startswith(old + " "):
                return new + key[len(old):]
        return key
    changes = [{**c, "item": rename(str(c.get("item")))} if isinstance(c, dict) else c
               for c in entry.get("changes") or []]
    return {**entry, "changes": changes} if "changes" in entry else entry


#: A participation value's own default, where it has one that is not
#: "unstated" (agreement.py's fallback): the only value criterion 9 lets a
#: synthetic asset restate on a frozen version that left it out.
_DEFAULTS = {"days_before": 0}


def _collection_states(key: str, dataset_id: str, cal_doc: dict, asset_doc: dict) -> bool:
    """Whether any participation_defaults version of the dataset's
    collection states `key` - where it does, leaving the key out took the
    collection's value rather than the default."""
    for agency in (((asset_doc or {}).get("hierarchy") or {}).get("agencies") or []):
        for coll in ((agency or {}).get("collections") or []):
            if any(str((d or {}).get("id")) == dataset_id for d in (coll or {}).get("datasets") or []):
                for c in (cal_doc or {}).get("collections") or []:
                    if (c or {}).get("id") == (coll or {}).get("id"):
                        versions = ((c.get("participation_defaults") or {}).get("versions")) or []
                        return any(key in (v or {}) for v in versions)
    return False


def _restates_at_default(item: Item, old, new, old_cal: dict, old_asset: dict) -> bool:
    """REQ-PIPE-111 criterion 9, amended 2026-10-16 (Keith's wording):
    RESTATING on a frozen version a value it left out, at that value's
    default. True only where the new value is the old one plus such keys
    and nothing else, and the value left out really did resolve to the
    default - not to a collection's."""
    if item.kind not in ("participation", "defaults"):
        return False
    if not isinstance(old, dict) or not isinstance(new, dict):
        return False
    added = set(new) - set(old)
    if not added or set(old) - set(new) or any(new[k] != old[k] for k in old):
        return False
    for key in added:
        if key not in _DEFAULTS or new[key] != _DEFAULTS[key] or isinstance(new[key], bool):
            return False
        if item.kind == "participation" and _collection_states(
                key, item.ctx["dataset"], old_cal, old_asset):
            return False
    return True


def _appended_dates_allowed(changes, old_items, old_agr, new_agr) -> set[str]:
    """Criterion 8's carve-out: dated entries ADDED after a calendar's last
    previous date, where - for each dataset on the calendar - the earliest
    claim-opening of the appended entries is no earlier than the closing
    instant that dataset's previous last slot had."""
    from qa_tools.common import slots

    allowed: set[str] = set()
    by_calendar: dict[str, list[Item]] = {}
    for key, (item, old, _new, _f) in changes.items():
        if item.kind == "cal_date" and old is None:
            by_calendar.setdefault(item.ctx["calendar"], []).append(item)
    for cal, items in by_calendar.items():
        previous = [i.ctx["date"] for i in old_items.values()
                    if i.kind == "cal_date" and i.ctx["calendar"] == cal]
        if not previous:
            continue
        latest = max(previous)
        later = [i for i in items if i.ctx["date"] > latest]
        if not later:
            continue
        first = date.fromisoformat(min(i.ctx["date"] for i in later))
        ok = True
        for ds in _datasets_on(cal, new_agr):
            opens = _claim_open(ds, first, new_agr)
            try:
                own = slots.slots_for_dataset(ds, until=date.fromisoformat(latest),
                                              agreement=old_agr)
            except Exception:  # noqa: BLE001
                own = []
            closes = own[-1].closes_at if own else None
            if opens is not None and closes is not None and opens < closes:
                ok = False
                break
        if ok:
            allowed |= {i.key for i in later}
    return allowed


def drafts(old_cal: dict | None, new_cal: dict, old_asset: dict | None, new_asset: dict,
           base_people: dict | None, *, base_codeowners: str | None, today: date,
           reference: str | None = None, author: str | None = None,
           approver: str | None = None, reason: str | None = None) -> list[str]:
    """One correction entry per owning item, for every frozen change no
    declared correction covers yet (REQ-PIPE-169 criterion 14) - computed by
    the gate's own check and written by the refusal's own `_paste_ready`."""
    needs: dict[tuple, list] = {}
    check(old_cal, new_cal, old_asset, new_asset, base_people, today=today,
          base_codeowners=base_codeowners, needs=needs)
    out = []
    for owner in sorted(needs, key=_owner_label):
        rows = needs[owner]
        owners = code_owners(base_codeowners, ASSET_REL if owner[0] == "timezone"
                             else CALENDAR_REL)
        may = [p for p in approvers(base_people or {})
               if str(p.get("github", "")).lower() in owners]
        out.append(_paste_ready(owner, [(i.key, o, n) for i, o, n, _ in rows], may, today,
                                reference=reference, author=author, approver=approver,
                                reason=reason))
    return out


# ---- putting a declared correction back (REQ-PIPE-170) ---------------------

def _own(container: dict, key: str, default):
    """`container[key]`, a copy of its own - the file shares participation
    versions between datasets through YAML anchors, and deepcopy keeps that
    sharing, so an edit to one would reach every dataset sharing it."""
    container[key] = copy.deepcopy(container.get(key) if container.get(key) is not None
                                   else default)
    return container[key]


def _version(versions: list, eff: str) -> dict | None:
    return next((v for v in versions if str((v or {}).get("effective_from")) == eff), None)


def _set_settings(versions: list, eff: str, old, *, keep: tuple) -> None:
    """A versioned item's settings back to `old`: removed where `old` is
    None (it was added), restored where it was removed, else replaced -
    keeping the keys an item does not hold (its dates, changelog)."""
    found = _version(versions, eff)
    if old is None:
        if found is not None:
            versions.remove(found)
        return
    if found is None:
        versions.append({"effective_from": eff, **copy.deepcopy(old)})
        versions.sort(key=lambda v: str(v.get("effective_from")))
        return
    for k in [k for k in found if k not in keep and k != "effective_from"]:
        del found[k]
    found.update(copy.deepcopy(old))


def _set_period(versions: list, period: str, old) -> None:
    """A dated period back to `old`: removed where `old` is None, else moved
    or restored - into the version whose window holds the old date."""
    for v in versions:
        v["dates"] = [d for d in (v.get("dates") or []) if str((d or {}).get("period")) != period]
    if old is None:
        return
    when = str(old)
    holder = None
    for v in sorted(versions, key=lambda v: str(v.get("effective_from"))):
        if str(v.get("effective_from")) <= when:
            holder = v
    holder = holder or versions[0]
    holder.setdefault("dates", []).append({"period": period, "date": when})
    holder["dates"].sort(key=lambda d: str(d.get("date")))


def revert(cal_doc: dict, asset_doc: dict,
           changes: list[tuple[str, object, object]]) -> tuple[dict, dict]:
    """The two files as they stood before `changes` - each (item key, old,
    new), as a declared correction lists them - copies, never the documents
    given. Raises ValueError for an item key it does not know, rather than
    leave a change silently in place.

    Versions before their dates and periods: a removed version comes back
    first, so its restored dates have somewhere to go."""
    cal, asset = copy.deepcopy(cal_doc), copy.deepcopy(asset_doc)
    calendars = {str((c or {}).get("name")): c for c in cal.get("calendars") or []}
    entries = {str((e or {}).get("id")): e for e in cal.setdefault("datasets", [])}

    def entry(ds: str) -> dict:
        if ds not in entries:
            entries[ds] = {"id": ds}
            cal["datasets"].append(entries[ds])
        return entries[ds]

    def order(change):
        parts = change[0].split()
        return 0 if "version" in parts else 1

    for key, old, _new in sorted(changes, key=order):
        p = key.split()
        if len(p) == 4 and p[0] == "calendar" and p[2] in ("version", "period") \
                and p[1] in calendars:
            versions = _own(calendars[p[1]], "versions", [])
            if p[2] == "version":
                _set_settings(versions, p[3], old, keep=("dates",) + _SKIPPED)
            else:
                _set_period(versions, p[3], old)
        elif len(p) == 4 and p[0] == "dataset" and p[2] == "participation":
            part = _own(entry(p[1]), "participation", {})
            _set_settings(part.setdefault("versions", []), p[3], old,
                          keep=_SKIPPED + _TURN_OFF_KEYS)
        elif len(p) == 4 and p[0] == "collection" and p[2] == "participation_defaults":
            coll = next((c for c in cal.get("collections") or [] if str((c or {}).get("id")) == p[1]),
                        None)
            if coll is None:
                raise ValueError(f"{key!r} names a collection the file does not hold.")
            part = _own(coll, "participation_defaults", {})
            _set_settings(part.setdefault("versions", []), p[3], old,
                          keep=_SKIPPED + _TURN_OFF_KEYS)
        elif len(p) == 5 and p[4] == "effective_to" and (
                (p[0] == "dataset" and p[2] == "participation")
                or (p[0] == "collection" and p[2] == "participation_defaults")):
            # A TURN-OFF (REQ-PIPE-179): its two keys on the one version.
            if p[0] == "dataset":
                block = _own(entry(p[1]), "participation", {})
            else:
                coll = next((c for c in cal.get("collections") or []
                             if str((c or {}).get("id")) == p[1]), None)
                if coll is None:
                    raise ValueError(f"{key!r} names a collection the file does not hold.")
                block = _own(coll, "participation_defaults", {})
            found = _version(block.setdefault("versions", []), p[3])
            if found is None:
                raise ValueError(f"{key!r} names a version the file does not hold.")
            for k in _TURN_OFF_KEYS:
                found.pop(k, None)
            found.update(copy.deepcopy(old or {}))
        elif len(p) == 4 and p[0] == "dataset" and p[2] == "not_expected":
            listed = [n for n in _own(entry(p[1]), "not_expected", [])
                      if str((n or {}).get("period")) != p[3]]
            if old is not None:
                listed.append({"period": p[3], "reason": old})
            entry(p[1])["not_expected"] = listed
        elif len(p) == 5 and p[0] == "dataset" and p[2] == "dates" and p[3] in ("version", "period"):
            versions = _own(entry(p[1]), "dates", {}).setdefault("versions", [])
            if p[3] == "version":
                _set_settings(versions, p[4], old, keep=("dates",) + _SKIPPED)
            else:
                _set_period(versions, p[4], old)
        elif len(p) == 3 and p[0] == "dataset" and p[2] == "calendar":
            e = entry(p[1])
            e.pop("calendar", None)
            e.pop("no_calendar", None)
            text = "" if old is None else str(old)
            if text.startswith("no calendar (") and text.endswith(")"):
                e["no_calendar"] = text[len("no calendar ("):-1]
            elif old is not None:
                e["calendar"] = old
        elif len(p) == 3 and p[:2] == ["timezone", "version"]:
            tz = asset.setdefault("timezone", {})
            versions = tz.setdefault("versions", [])
            _set_settings(versions, p[2], None if old is None else {"zone": old},
                          keep=_SKIPPED)
        else:
            raise ValueError(f"{key!r} cannot be reverted - it is not an item the schedule gate "
                             f"names, so the agreement before this correction cannot be rebuilt")
    return cal, asset
