"""Whether a resupply may replace an already-promoted supply automatically
(REQ-PIPE-123): never, when green, or when green or amber.

THE SAME MECHANISM AS THE AMBER SETTING (criterion 1): stated at data
asset, collection and dataset level, nearest wins, versioned by effective
date, the asset level required, and a version whose date has passed is
frozen. amber_setting.py is that mechanism, read here under this key - a
second implementation of "which version is in force" is how two settings
come to disagree about the same date.

THE ONLY RULE THAT LETS AUTOMATION DISPLACE ACCEPTED DATA (NFR 1), so it is
reviewed configuration, CI-gated, and every replacement records the setting
that authorised it (criterion 5).

ONE CONFLICT IS REFUSED IN CI (criterion 11): green-or-amber replacement
where the amber setting is hold, on ANY date where versions of the two
overlap - replacing accepted data with an amber supply where amber may not
even fill an empty slot unattended makes no sense. Checked at every date
either setting changes on, at every level, for every dataset, because both
resolve piecewise-constantly between those dates.
"""
from __future__ import annotations

from datetime import date, datetime

from qa_tools.common import amber_setting
from qa_tools.common.schemas import REPLACEMENT_SETTINGS

NEVER, GREEN, GREEN_OR_AMBER = REPLACEMENT_SETTINGS
KEY = "replacement_setting"
LABEL = "replacement setting"

#: The statuses each value lets the rule replace a promoted supply with.
PERMITS = {NEVER: frozenset(), GREEN: frozenset({"green"}),
           GREEN_OR_AMBER: frozenset({"green", "amber"})}


def resolve(dataset_id: str, at: datetime | str, *, doc: dict | None = None):
    """The replacement setting for `dataset_id` as at `at` - value, level and
    version (criterion 5). Raises amber_setting.AmberSettingError where none
    is in force: there is no default."""
    return amber_setting.resolve(dataset_id, at, doc=doc, key=KEY,
                                 values=REPLACEMENT_SETTINGS, label=LABEL)


def permits(resolved, status: str | None) -> bool:
    """Whether this setting lets the rule replace a promoted supply with one
    whose status is `status` (criteria 2 and 3)."""
    return bool(resolved) and status in PERMITS.get(resolved.value, frozenset())


def standing_problems(doc: dict, today: date) -> list[tuple[str, str]]:
    return amber_setting.standing_problems(doc, today, key=KEY)


def past_change_problems(old: dict, new: dict, today: date, *, synthetic: bool,
                         added=None) -> list[tuple[str, str]]:
    return amber_setting.past_change_problems(old, new, today, synthetic=synthetic,
                                              added=added, key=KEY)


def conflicts(doc: dict) -> list[tuple[str, str]]:
    """[(where, problem)] for every dataset and date on which the resolved
    replacement setting is green-or-amber while the resolved amber setting
    is hold (criterion 11) - including in the past and the future, not only
    as set today."""
    changes = sorted({date.fromisoformat(str(v["effective_from"]))
                      for key in (KEY, amber_setting.KEY)
                      for setting in amber_setting._settings(doc, key).values()
                      for v in (setting.get("versions") or [])
                      if isinstance(v, dict) and v.get("effective_from")})
    out: list[tuple[str, str]] = []
    for agency in ((doc.get("hierarchy") or {}).get("agencies") or []):
        for collection in (agency.get("collections") or []):
            for dataset in (collection.get("datasets") or []):
                dataset_id = dataset.get("id")
                for on in changes:
                    replace = amber_setting._resolve_on(doc, dataset_id, on, KEY)
                    amber = amber_setting._resolve_on(doc, dataset_id, on, amber_setting.KEY)
                    if (replace and amber and replace.value == GREEN_OR_AMBER
                            and amber.value == amber_setting.HOLD):
                        out.append((f"dataset {dataset_id}",
                                    f"from {on.isoformat()} the replacement setting is "
                                    f"green-or-amber ({replace.level}) while the amber setting "
                                    f"is hold ({amber.level}) - an amber supply could replace "
                                    f"accepted data where it may not even fill an empty slot"))
                        break
    return out
