"""The date this project's generated history is built around - its ANCHOR
(REQ-GEN-042; REQ-GEN-404 and REQ-GEN-405, signed by Keith 2026-11-14).

AN INPUT, RECORDED WITH THE HISTORY - NO LONGER A CONSTANT A PERSON BUMPS. A
generation is given its anchor by its caller and records the date it used
(asset_model/history_anchor.py has the three records). The caller decides which
date (REQ-GEN-405): the FIXED TEST ANCHOR, 2026-09-25, for the test suite, CI and
every bootstrap or generation not asked for another; today on the asset's own
clock for `mothman pipeline bootstrap --roll-anchor`; or the date `--anchor`
names. The same anchor and the same inputs give the same bytes (R2).

WHY THE ANCHOR WAS PINNED IN THE FIRST PLACE, AND WHY THIS DOES NOT UNDO IT. It
used to default to `date.today()`, so the history slid forward every day it was
regenerated, and with dated run ids two regenerations on consecutive days
ACCUMULATED two histories (the "352 committed runs" that were really 176). Run
ids carry no date now (REQ-GEN-042 criterion 5), and a regeneration replaces
the whole history - the reset deletes the files with the database (REQ-GEN-408)
- so a moved anchor gives one history, never two. What stays from Keith's
2026-09-22 call ("I'm happy for demo data to visibly age"): regeneration is a
DELIBERATE act, a reset then a bootstrap (R3), never a side effect of running
the generator on another day.

GENERATOR_ANCHOR_DATE IS NO LONGER READ, AND REFUSES RATHER THAN GOING QUIET
(REQ-GEN-404 criterion 9; CLI finding 6): a developer's leftover line in .env
would otherwise stop working without a word. `--anchor` replaces it.
"""
from __future__ import annotations

import os
from datetime import date

from asset_model import history_anchor

#: THE FIXED TEST ANCHOR (REQ-GEN-405 criterion 1), the generator's name for
#: asset_model's one constant: the most recent day a supply lands in a history
#: generated for the tests, CI or a plain bootstrap. 2026-09-25 since 2026-10-19
#: (Keith, "Grow BR's end"), so TS-62 has room after 2026-09-08.
FIXED_TEST_ANCHOR = history_anchor.FIXED_TEST_ANCHOR

#: The environment variable that used to override the anchor - now refused.
RETIRED_ENV = "GENERATOR_ANCHOR_DATE"


class AnchorRefused(ValueError):
    """An anchor a generation may not use, said before anything is written."""


def refuse_the_retired_variable() -> None:
    """REQ-GEN-404 criterion 9: every generation and bootstrap refuses while
    GENERATOR_ANCHOR_DATE is set, naming `--anchor`."""
    if os.environ.get(RETIRED_ENV):
        raise AnchorRefused(
            f"{RETIRED_ENV} is set ({os.environ[RETIRED_ENV]!r}), and it is no longer read: "
            f"a generation's anchor is given with --anchor YYYY-MM-DD (or --roll-anchor on "
            f"`mothman pipeline bootstrap`). Remove it from the environment and from .env. "
            f"Nothing was written.")


def get_anchor_date() -> date:
    """The anchor of the generation running in this process: the one its caller
    installed (history_anchor.anchored, handed to every process it starts), or -
    where nothing installed one, as in a test calling a provider directly - the
    fixed test anchor, REQ-GEN-405's choice. No other default exists anywhere in
    the generator or a provider (REQ-GEN-404 criterion 1). Read at CALL TIME, so
    a provider imported before the anchor is installed generates for the one
    installed later (criterion 2)."""
    refuse_the_retired_variable()
    installed = history_anchor.installed()
    return installed if installed is not None else FIXED_TEST_ANCHOR


def asset_today() -> date:
    """Today on the selected asset's own clock (REQ-GEN-405 criterion 3), the
    clock's installed or pinned instant where there is one."""
    from asset_model import asset_time

    return asset_time.local_date(asset_time.now())


def validate(value, *, today: date | None = None) -> date:
    """`value` - a date or a YYYY-MM-DD string - as an anchor a generation may
    use, or AnchorRefused before anything is written (REQ-GEN-404 criterion 7;
    SR6): not a valid date; after today on the asset's clock; earlier than the
    fixed test anchor."""
    if isinstance(value, date):
        anchor = value
    else:
        try:
            anchor = date.fromisoformat(str(value).strip())
        except ValueError:
            raise AnchorRefused(f"{value!r} is not a date - an anchor is written YYYY-MM-DD, "
                                f"e.g. {FIXED_TEST_ANCHOR.isoformat()}. Nothing was written.") from None
    if today is None:
        today = asset_today()
    if anchor > today:
        raise AnchorRefused(
            f"{anchor.isoformat()} is after today, {today.isoformat()} on {_zone()}'s clock. "
            f"A history cannot be generated up to a day that has not happened. Nothing was "
            f"written.")
    if anchor < FIXED_TEST_ANCHOR:
        raise AnchorRefused(
            f"{anchor.isoformat()} is earlier than the fixed test anchor - the earliest anchor "
            f"a history can be generated at is {FIXED_TEST_ANCHOR.isoformat()}, the first day "
            f"its scenarios are placed for. Nothing was written.")
    return anchor


def _zone() -> str:
    """The asset's zone as a person names it - 'Perth' for Australia/Perth."""
    try:
        from asset_model import asset_time

        return str(asset_time.zone_now()).rsplit("/", 1)[-1].replace("_", " ")
    except Exception:  # noqa: BLE001 - a wording helper never fails a refusal
        return "the asset"


def zone_name() -> str:
    return _zone()
