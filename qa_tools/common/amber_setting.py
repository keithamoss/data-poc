"""What happens to an AMBER supply, and the configuration's guards
(REQ-PIPE-122).

ONE SETTING, THREE VALUES, STRICTEST FIRST - hold, promote-and-acknowledge,
promote (criteria 1 and 2). Three values cannot contradict each other where
an on/off promotion flag plus an acknowledgement flag could.

NEAREST LEVEL WINS (criterion 3): a dataset's own `amber_setting`, then its
collection's, then the asset's. An agency is not a level - the schema refuses
the key there, so a setting on a level that does not exist fails the gate
(criterion 20) rather than being ignored.

EFFECTIVE-DATED (criterion 4). A level's versions are read like a calendar's:
the version in effect is the latest whose `effective_from` is on or before
the decision's own instant, read on the asset's clock. A level whose versions
all start later states nothing yet, so the next level up answers.

THE PAST IS RECORDED, NOT RECOMPUTED (criterion 5). The promotion rule
records the resolved value, its level and its version on the decision
(criterion 19), and everything that shows the past reads that record. This
module answers "what applies to a decision taking effect at T" - which is
the question only the rule ever asks.

FROZEN PAST (criteria 6 to 8): a version whose date has passed may not be
altered or removed, whatever changelog accompanies it - there is no
correction route, because a past setting is inert: nothing is re-judged
from it. A new version may not be dated before the day it is added, except
on an asset that declares itself synthetic, where scenario playback needs
to author the past.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import yaml

from qa_tools.common.schemas import AMBER_SETTINGS

HOLD, PROMOTE_AND_ACKNOWLEDGE, PROMOTE = AMBER_SETTINGS

#: The levels a setting can be stated at, nearest first.
DATASET, COLLECTION, ASSET = "dataset", "collection", "data asset"

#: THE CONFIGURATION KEY. This module is the one mechanism for an
#: effective-dated, nearest-wins, frozen-past setting: REQ-PIPE-123's
#: replacement setting is read by the same functions under its own key
#: ("by the same mechanism, and with the same protection of its past").
KEY = "amber_setting"


class AmberSettingError(ValueError):
    """The configuration cannot answer - no asset-level value in effect."""


@dataclass(frozen=True)
class Resolved:
    """The setting that applies, and where it came from (criterion 19)."""

    value: str
    level: str
    version: str           # the version's effective_from

    @property
    def owes_acknowledgement(self) -> bool:
        return self.value == PROMOTE_AND_ACKNOWLEDGE


def _doc(path: Path | None = None) -> dict:
    from qa_tools.common.hierarchy import DATA_ASSET_YAML

    with open(path or DATA_ASSET_YAML) as f:
        return yaml.safe_load(f) or {}


def _in_effect(setting: dict | None, on: date) -> dict | None:
    best = None
    for version in ((setting or {}).get("versions") or []):
        start = date.fromisoformat(str(version["effective_from"]))
        if start <= on and (best is None or start >= date.fromisoformat(
                str(best["effective_from"]))):
            best = version
    return best


def _nodes_for(doc: dict, dataset_id: str) -> tuple[dict | None, dict | None]:
    for agency in ((doc.get("hierarchy") or {}).get("agencies") or []):
        for collection in (agency.get("collections") or []):
            for dataset in (collection.get("datasets") or []):
                if dataset.get("id") == dataset_id:
                    return collection, dataset
    return None, None


def _resolve_on(doc: dict, dataset_id: str, on: date, key: str = KEY) -> Resolved | None:
    collection, dataset = _nodes_for(doc, dataset_id)
    for level, node in ((DATASET, dataset), (COLLECTION, collection), (ASSET, doc)):
        version = _in_effect((node or {}).get(key), on)
        if version:
            return Resolved(value=str(version["value"]), level=level,
                            version=str(version["effective_from"]))
    return None


def timeline(dataset_id: str, *, doc: dict | None = None) -> list[dict]:
    """Every change to this dataset's resolved setting, oldest first:
    {from, value, level, version} - what the dashboard embeds so the page
    can show the setting in force on the date on show (NFR 1, built
    2026-10-05). Read from configuration only."""
    doc = doc if doc is not None else _doc()
    collection, dataset = _nodes_for(doc, dataset_id)
    starts = sorted({str(v["effective_from"])
                     for node in (dataset, collection, doc)
                     for v in (((node or {}).get("amber_setting") or {}).get("versions") or [])
                     if isinstance(v, dict) and v.get("effective_from")})
    out: list[dict] = []
    for start in starts:
        r = _resolve_on(doc, dataset_id, date.fromisoformat(start))
        if r is None:
            continue
        if out and (out[-1]["value"], out[-1]["level"], out[-1]["version"]) == (
                r.value, r.level, r.version):
            continue
        out.append({"from": start, "value": r.value, "level": r.level, "version": r.version,
                    "text": describe(dataset_id, date.fromisoformat(start), doc=doc)})
    return out


def _level_words(doc: dict, dataset_id: str, level: str) -> str:
    if level == DATASET:
        return "set for this dataset"
    if level == COLLECTION:
        collection, _ = _nodes_for(doc, dataset_id)
        return f"set for {(collection or {}).get('name') or 'its collection'}"
    return "set for the whole data asset"


def describe(dataset_id: str, on: date, *, doc: dict | None = None) -> str:
    """The setting in force for `dataset_id` on `on`, in words - for
    example 'promote and acknowledge (set for Child Protection, since 5
    Oct 2026)' (NFR 1). Raises AmberSettingError where none is in force,
    as resolve() does - there is no default."""
    doc = doc if doc is not None else _doc()
    r = _resolve_on(doc, dataset_id, on)
    if r is None:
        raise AmberSettingError(f"no amber setting is in effect for {dataset_id} on "
                                f"{on.isoformat()}")
    since = date.fromisoformat(r.version)
    return (f"{r.value.replace('-', ' ')} ({_level_words(doc, dataset_id, r.level)}, "
            f"since {since.day} {since.strftime('%b %Y')})")


def resolve(dataset_id: str, at: datetime | str, *, doc: dict | None = None,
            key: str = KEY, values: tuple[str, ...] = AMBER_SETTINGS,
            label: str = "amber setting") -> Resolved:
    """The setting for `dataset_id` as at the instant `at` - the instant
    the decision about a supply takes effect (criterion 4)."""
    from qa_tools.common import asset_time

    instant = at if isinstance(at, datetime) else asset_time.parse_instant(at, "at")
    on = asset_time.local_date(instant)
    doc = doc if doc is not None else _doc()
    found = _resolve_on(doc, dataset_id, on, key)
    if found is not None:
        return found
    raise AmberSettingError(
        f"no {label} is in effect for {dataset_id} on {on.isoformat()} - the data "
        f"asset level must state one (one of {', '.join(values)}), and there is no "
        f"default.")


# ---- the configuration's guards (criteria 6 to 9 and 20) --------------

def standing_problems(doc: dict, today: date, key: str = KEY) -> list[tuple[str, str]]:
    """[(where, problem)] in the configuration as it stands - no history
    needed (delivery-critic on REQ-PIPE-122, F4 and F5).

    Criterion 9 refuses an asset that states no value; an asset whose
    every version starts in the FUTURE states none today either, and was
    accepted until the rule met its first amber supply. And two versions
    of one level sharing a date are ambiguous - the later list entry won,
    silently.
    """
    problems: list[tuple[str, str]] = []
    for where, setting in _settings(doc, key).items():
        starts = [str(v.get("effective_from")) for v in (setting.get("versions") or [])
                  if isinstance(v, dict)]
        for start in sorted({s for s in starts if starts.count(s) > 1}):
            problems.append((where, f"two versions share the date {start}, so which "
                                    f"applies is ambiguous"))
    if isinstance(doc.get(key), dict) and not _in_effect(doc[key], today):
        problems.append((ASSET, f"no version is in effect today ({today.isoformat()}) - the "
                                f"data asset level must always state one"))
    return problems

def _settings(doc: dict, key: str = KEY) -> dict[str, dict]:
    """{where: setting} for every level that states one."""
    out: dict[str, dict] = {}
    if isinstance(doc.get(key), dict):
        out[ASSET] = doc[key]
    for agency in ((doc.get("hierarchy") or {}).get("agencies") or []):
        for collection in (agency.get("collections") or []):
            if isinstance(collection.get(key), dict):
                out[f"collection {collection.get('id')}"] = collection[key]
            for dataset in (collection.get("datasets") or []):
                if isinstance(dataset.get(key), dict):
                    out[f"dataset {dataset.get('id')}"] = dataset[key]
    return out


def _versions(setting: dict) -> dict[str, dict]:
    return {str(v.get("effective_from")): v for v in (setting.get("versions") or [])
            if isinstance(v, dict)}


def past_change_problems(old: dict, new: dict, today: date, *,
                         synthetic: bool, added=None, key: str = KEY) -> list[tuple[str, str]]:
    """[(where, problem)] for every change that rewrites a setting's past.

    `today` is on the asset's clock. A version is PAST once its date is
    before today; a version dated today may still be corrected the day it
    is added, which is what makes "not earlier than the day it is added"
    and "the past is frozen" agree.

    `added` is the day the change was ADDED - the date of the commit that
    introduced it (criterion 7 as amended 2026-10-05, Keith) - so a
    version committed late and checked after midnight is not refused for
    the gate's own timing. None means today: an edit not yet committed.
    A callable is asked per version - `added(start)` - since each version
    is dated by the commit that introduced IT (delivery critic on 8a942e7,
    M1); its None likewise means today.
    """
    def added_for(start: str) -> date:
        found = added(start) if callable(added) else added
        return found or today
    problems: list[tuple[str, str]] = []
    was, now = _settings(old, key), _settings(new, key)
    for where, setting in was.items():
        before = _versions(setting)
        after = _versions(now.get(where) or {})
        for start, version in before.items():
            try:
                started = date.fromisoformat(start)
            except ValueError:
                continue
            if started >= today:
                continue
            if start not in after:
                problems.append((where, f"the version effective {start} has been removed, and "
                                        f"its date has passed"))
            elif (after[start].get("value"), after[start].get("changelog")) != (
                    version.get("value"), version.get("changelog")):
                problems.append((where, f"the version effective {start} has been altered, and "
                                        f"its date has passed"))
    for where, setting in now.items():
        before = _versions(was.get(where) or {})
        for start in _versions(setting):
            if start in before:
                continue
            try:
                started = date.fromisoformat(start)
            except ValueError:
                continue
            if started < today and not synthetic and started < added_for(start):
                problems.append((where, f"a new version is dated {start}, before the day "
                                        f"it was added ({added_for(start).isoformat()})"))
    return problems

