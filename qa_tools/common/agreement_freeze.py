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
participation or timezone version (criterion 9).

THE CLOCK (criterion 12) is the committer instant of the commit that
introduced the change, floored at the base commit's - never the author
date, which can be backdated. Where the change is not committed yet (the
pre-commit hook, comparing the staged file against HEAD), it is now.

CONFIGURATION ONLY (criterion 16): two versions of two files, git, and the
slot arithmetic - no database and nothing under data/.
"""
from __future__ import annotations

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
                             if k not in _SKIPPED + ("effective_from",)}),
                     {"dataset": ds, "eff": eff, "end": windows.get(eff)}))
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
        opens = [_claim_open(ds, day, agr) for ds in _datasets_on(c["calendar"], agr)]
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


def _is_approver(name: str, allowed: list[dict]) -> bool:
    name = str(name).strip().lower()
    return any(name in {str(p.get("email", "")).lower(), str(p.get("github", "")).lower()}
               for p in allowed)


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
    return yaml.safe_dump(_plain(value), default_flow_style=True, sort_keys=False).strip()


def _paste_ready(owner: tuple, changes: list[tuple[str, object, object]], allowed: list[dict],
                 today: date) -> str:
    who = ", ".join(p.get("email") for p in allowed) or "nobody - people.yaml names no approver"
    lines = [f"Add to the corrections list of {_owner_label(owner)}:",
             "  corrections:",
             "    - change_reference: <CHANGE-REF>",
             f"      date: '{today.isoformat()}'",
             "      author: <you>",
             "      approver: <one of the people below>",
             "      reason: <why the agreement was wrong>",
             "      changes:"]
    for key, old, new in changes:
        # null, not the "(nothing)" a reader is shown: this block is pasted
        # and parsed, and a string would never match (delivery-critic, M1).
        lines += [f"        - item: {key}",
                  f"          old: {'null' if old is None else _value_text(old)}",
                  f"          new: {'null' if new is None else _value_text(new)}"]
    lines.append(f"May approve: {who}.")
    lines.append("Preview what this would re-judge before asking for approval - the impact "
                 "preview is REQ-PIPE-169, not built yet.")
    return "\n".join(lines)


def old_asset_like(new_asset: dict) -> dict:
    """The asset file with no previous state, standing in as its own
    previous state for every item it holds."""
    return dict(new_asset or {})


def check(old_cal: dict | None, new_cal: dict, old_asset: dict | None, new_asset: dict,
          base_people: dict | None, instant_of=None, today: date | None = None) -> list[Finding]:
    """Every refusal for one change from (old_cal, old_asset) to (new_cal,
    new_asset). `instant_of(item_key) -> datetime` is when that change was
    introduced (criterion 12); a missing previous state passes (criterion
    14)."""
    from qa_tools.common import agreement

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
        new_agr = agreement.from_doc(new_cal)
    except Exception:  # noqa: BLE001 - an unreadable NEW file is the schema gate's to report
        return []
    try:
        old_agr = agreement.from_doc(old_cal) if old_cal else None
    except Exception:  # noqa: BLE001
        # An OLD state today's loader cannot read still has its changes
        # checked, against freeze instants from the new state, rather than
        # the whole check being skipped (delivery-critic, L2).
        old_agr = new_agr
    synthetic = bool(old_asset.get("synthetic")) and bool(new_asset.get("synthetic"))
    allowed = approvers(base_people or {})

    # WHAT ACTUALLY CHANGED, by item: (item, old value, new value, frozen at).
    changes: dict[str, tuple[Item, object, object, datetime | None]] = {}
    for key in set(old_items) | set(new_items):
        before, after = old_items.get(key), new_items.get(key)
        if before is not None and after is not None and before.norm == after.norm:
            continue
        if before is not None and old_agr is not None:
            frozen_at = freeze_instant(before, old_agr)   # a change or a removal
        else:
            frozen_at = freeze_instant(after, new_agr)    # an addition
        changes[key] = (before or after, before.value if before else None,
                        after.value if after else None, frozen_at)

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
    for owner, entries in new_corr.items():
        before = old_corr.get(owner, [])
        file = "data-asset.yaml" if owner[0] == "timezone" else "calendar.yaml"
        where = owner[0] if owner[0] == "timezone" else f"{owner[0]} {owner[1]!r}"
        if [_norm(e) for e in entries[:len(before)]] != [_norm(e) for e in before]:
            out.append(Finding(file, where,
                               "an existing declared correction was changed or removed - a "
                               "corrections list is append-only. Nothing was committed.",
                               "Restore the corrections already committed, exactly as they were, "
                               "and append a new one if something more needs correcting."))
            continue
        for corr in entries[len(before):]:
            corr = corr or {}
            approver = corr.get("approver")
            if approver and not _is_approver(approver, allowed):
                out.append(Finding(
                    file, where,
                    f"a correction names approver {approver!r}, who is not a person allowed to "
                    f"approve in contract/people.yaml as it stood before this change. Nothing "
                    f"was committed.",
                    "Name one of: " + (", ".join(p.get("email") for p in allowed) or "nobody") +
                    ". An approver added in the same change does not count."))
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
    needs: dict[tuple, list] = {}
    for key, (item, old, new, frozen_at) in sorted(changes.items()):
        if key in declared or key in appended_ok or frozen_at is None:
            continue
        when = instant_of(key)
        if when < frozen_at:
            continue  # not frozen yet when introduced (criterion 10)
        added = old is None
        if added and synthetic and item.kind in ("cal_version", "participation", "tz_version"):
            continue  # criterion 9
        if added and synthetic and item.kind == "cal_date" and \
                f"calendar {item.ctx['calendar']} version {item.ctx['version']}" not in old_items:
            continue  # a date inside a version criterion 9 lets a synthetic asset add
        needs.setdefault(item.owner, []).append((item, old, new, frozen_at))

    for owner, rows in needs.items():
        file = "data-asset.yaml" if owner[0] == "timezone" else "calendar.yaml"
        for item, old, new, frozen_at in rows:
            verb = "added" if old is None else ("removed" if new is None else "changed")
            fix = _paste_ready(owner, [(item.key, old, new)], allowed, today)
            if item.kind == "not_expected":
                fix += ("\nIf the period simply was not supplied, record that after the fact "
                        f"instead: `{MARK_NOT_SUPPLIED}`.")
            out.append(Finding(
                file, item.key,
                f"{item.key} was {verb} ({_value_text(old)} -> {_value_text(new)}) after it froze "
                f"at {asset_time.localise(frozen_at).isoformat(timespec='minutes')}, the first "
                f"instant it could govern a filing. Only a declared correction may change it. "
                f"Nothing was committed.",
                fix))
    return out


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
