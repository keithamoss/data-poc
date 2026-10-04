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


def resolve(dataset_id: str, at: datetime | str, *, doc: dict | None = None) -> Resolved:
    """The amber setting for `dataset_id` as at the instant `at` - the
    instant the decision about a supply takes effect (criterion 4)."""
    from qa_tools.common import asset_time

    instant = at if isinstance(at, datetime) else asset_time.parse_instant(at, "at")
    on = asset_time.local_date(instant)
    doc = doc if doc is not None else _doc()
    collection, dataset = _nodes_for(doc, dataset_id)
    for level, node in ((DATASET, dataset), (COLLECTION, collection), (ASSET, doc)):
        version = _in_effect((node or {}).get("amber_setting"), on)
        if version:
            return Resolved(value=str(version["value"]), level=level,
                            version=str(version["effective_from"]))
    raise AmberSettingError(
        f"no amber setting is in effect for {dataset_id} on {on.isoformat()} - the data "
        f"asset level must state one (one of {', '.join(AMBER_SETTINGS)}), and there is no "
        f"default.")


# ---- the configuration's guards (criteria 6 to 9 and 20) --------------

def standing_problems(doc: dict, today: date) -> list[tuple[str, str]]:
    """[(where, problem)] in the configuration as it stands - no history
    needed (delivery-critic on REQ-PIPE-122, F4 and F5).

    Criterion 9 refuses an asset that states no value; an asset whose
    every version starts in the FUTURE states none today either, and was
    accepted until the rule met its first amber supply. And two versions
    of one level sharing a date are ambiguous - the later list entry won,
    silently.
    """
    problems: list[tuple[str, str]] = []
    for where, setting in _settings(doc).items():
        starts = [str(v.get("effective_from")) for v in (setting.get("versions") or [])
                  if isinstance(v, dict)]
        for start in sorted({s for s in starts if starts.count(s) > 1}):
            problems.append((where, f"two versions share the date {start}, so which "
                                    f"applies is ambiguous"))
    if isinstance(doc.get("amber_setting"), dict) and not _in_effect(doc["amber_setting"], today):
        problems.append((ASSET, f"no version is in effect today ({today.isoformat()}) - the "
                                f"data asset level must always state one"))
    return problems

def _settings(doc: dict) -> dict[str, dict]:
    """{where: setting} for every level that states one."""
    out: dict[str, dict] = {}
    if isinstance(doc.get("amber_setting"), dict):
        out[ASSET] = doc["amber_setting"]
    for agency in ((doc.get("hierarchy") or {}).get("agencies") or []):
        for collection in (agency.get("collections") or []):
            if isinstance(collection.get("amber_setting"), dict):
                out[f"collection {collection.get('id')}"] = collection["amber_setting"]
            for dataset in (collection.get("datasets") or []):
                if isinstance(dataset.get("amber_setting"), dict):
                    out[f"dataset {dataset.get('id')}"] = dataset["amber_setting"]
    return out


def _versions(setting: dict) -> dict[str, dict]:
    return {str(v.get("effective_from")): v for v in (setting.get("versions") or [])
            if isinstance(v, dict)}


def past_change_problems(old: dict, new: dict, today: date, *,
                         synthetic: bool) -> list[tuple[str, str]]:
    """[(where, problem)] for every change that rewrites a setting's past.

    `today` is on the asset's clock. A version is PAST once its date is
    before today; a version dated today may still be corrected the day it
    is added, which is what makes "not earlier than the day it is added"
    and "the past is frozen" agree.
    """
    problems: list[tuple[str, str]] = []
    was, now = _settings(old), _settings(new)
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
            if started < today and not synthetic:
                problems.append((where, f"a new version is dated {start}, before today "
                                        f"({today.isoformat()})"))
    return problems

