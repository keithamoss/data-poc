"""Which anchor a bootstrap or a generation uses (REQ-GEN-404, REQ-GEN-405;
signed by Keith 2026-11-14 as speed-anchor v2).

ONLY A DEMO REGENERATION ROLLS (R1, SA Q2). The test suite, CI and every
bootstrap without `--roll-anchor` generate at the FIXED TEST ANCHOR, so the
arrival pin, CI's cache key and the pins built on it stay byte-stable.
`--roll-anchor` generates up to today on the asset's own clock - or the latest
day before it whose every planned receipt has already passed (SA Q5), since a
receipt still to come today is in the real future, which the replay clock may
never reach (REQ-PIPE-382, 'never after the real present'). `--anchor` names a
date, to rebuild a history given that date back (R2).

THE ROLL IS WORKED OUT FROM A DRY BUILD, one candidate day at a time: every
collection generated into a throwaway folder of its own - never data/ - and the
latest receipt instant its receipts record read off it. Normally the first
candidate (today) or the one before it.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import warnings
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from asset_model import history_anchor
from generator import public as anchor_date

#: The environments that always use the fixed test anchor (REQ-GEN-405
#: criteria 2 and 9).
FIXED_ONLY = frozenset({"test", "ci"})

#: How many days back a roll looks for a day whose receipts have all passed
#: before refusing (PROVISIONAL (2026-11-16): SA Q5 says 'normally at most one
#: day back'; a week is room for a provider whose receipts trail by days).
MOST_DAYS_BACK = 7


class AnchorRefused(anchor_date.AnchorRefused):
    """A bootstrap's or generation's anchor refused before anything is
    written."""


@dataclass(frozen=True)
class Chosen:
    """The anchor a run uses and how it was chosen: 'fixed', 'given' (--anchor)
    or 'rolled' (--roll-anchor); `said` is what the run says before generating,
    or None."""
    anchor: date
    how: str
    said: str | None = None
    #: For a roll, how many days back from today it stepped (SA Q5) - so the
    #: closing line never says 'today' of a day that was not.
    days_back: int = 0


def environment() -> str | None:
    return os.environ.get("MOTHMAN_ENVIRONMENT")


def requested(anchor: str | date | None, roll: bool) -> None:
    """Refusals that need nothing generated or read (REQ-GEN-404 criteria 5, 7
    and 9; REQ-GEN-405 criterion 9) - the retired variable, both flags, an
    anchor that is not a date, in the future or before the fixed one, and a
    rolled or other anchor where tests and CI always use the fixed one."""
    try:
        anchor_date.refuse_the_retired_variable()
    except anchor_date.AnchorRefused as exc:
        raise AnchorRefused(str(exc)) from None
    if roll and anchor is not None:
        raise AnchorRefused("--anchor and --roll-anchor were both given - give one: --anchor "
                            "names the date, --roll-anchor rolls to today. Nothing was written.")
    given = None
    if anchor is not None:
        try:
            given = anchor_date.validate_anchor(anchor)
        except anchor_date.AnchorRefused as exc:
            raise AnchorRefused(str(exc)) from None
    if environment() in FIXED_ONLY and (roll or (given is not None
                                                  and given != history_anchor.FIXED_TEST_ANCHOR)):
        what = "--roll-anchor" if roll else f"--anchor {given.isoformat()}"
        raise AnchorRefused(
            f"{what} was given where MOTHMAN_ENVIRONMENT is {environment()}: tests and CI "
            f"always use the fixed test anchor, {history_anchor.FIXED_TEST_ANCHOR.isoformat()}, "
            f"so the pins and CI's cache key never move with the calendar (R1). Nothing was "
            f"written.")


def chosen_without_roll(anchor: str | date | None) -> Chosen:
    """The anchor of a run not rolling: the one --anchor named, else the fixed
    test anchor (REQ-GEN-405 criterion 4)."""
    if anchor is None:
        return Chosen(history_anchor.FIXED_TEST_ANCHOR, "fixed")
    given = anchor_date.validate_anchor(anchor)
    refuse_past_the_last_round(given)
    return Chosen(given, "fixed" if given == history_anchor.FIXED_TEST_ANCHOR else "given")


def refuse_past_the_last_round(anchor: date) -> None:
    """REQ-GEN-406 criterion 6: an anchor after a calendar's last AUTHORED round
    is refused before anything is written, naming the calendar, the file to
    extend, a pasteable `mothman schedule candidate-dates` and the fallback. A
    cadence-rule calendar has no last round."""
    from asset_model import assets, schedule

    for cal in schedule.calendars():
        if not cal.versions or cal.versions[-1].is_cadence_rule:
            continue
        periods = schedule.periods_for_calendar(cal.name)
        if not periods:
            continue
        last = max(p.date for p in periods)
        if anchor > last:
            raise AnchorRefused(
                f"{anchor.isoformat()} is after the {cal.name!r} calendar's last authored "
                f"round, {last.isoformat()}, so the history cannot be generated up to it. "
                f"Nothing was written. Extend the calendar in "
                f"{assets.config_dir()}/calendar.yaml - `mothman schedule candidate-dates "
                f"--calendar {cal.name} --year {anchor.year}` lists the dates to add - or run "
                f"`mothman pipeline bootstrap` without --roll-anchor, which still works.")


def latest_receipt(root: Path) -> datetime | None:
    """The latest receipt instant any file under `root`/receipts records."""
    from asset_model import asset_time

    latest = None
    for receipt in (Path(root) / "receipts").rglob("*.json"):
        try:
            value = json.loads(receipt.read_text(encoding="utf-8")).get("received_at")
        except (OSError, ValueError):
            continue
        if not value:
            continue
        at = asset_time.parse_instant(value, str(receipt))
        latest = at if latest is None or at > latest else latest
    return latest


def dry_build_latest_receipt(candidate: date) -> datetime | None:
    """Every collection generated at `candidate` somewhere of its own - never
    data/ - quietly, and the latest receipt it planned."""
    from generator.public import generated_into

    with history_anchor.anchored(candidate), \
            tempfile.TemporaryDirectory(prefix="mothman-roll-") as tmp, \
            contextlib.redirect_stdout(io.StringIO()), warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with generated_into(Path(tmp)) as root:
            return latest_receipt(root)


def roll(*, now: datetime | None = None, latest_receipt_at=dry_build_latest_receipt) -> Chosen:
    """REQ-GEN-405 criteria 3 and 5: today on the asset's clock, unless a
    receipt planned for that day is still to come, in which case the latest
    day whose every planned receipt has already passed - with the sentence
    the bootstrap says before generating."""
    from asset_model import asset_time

    instant = now or asset_time.now()
    today = asset_time.local_date(instant)
    zone = anchor_date.zone_name()
    late = None
    for back in range(MOST_DAYS_BACK + 1):
        candidate = today - timedelta(days=back)
        if candidate < history_anchor.FIXED_TEST_ANCHOR:
            break
        refuse_past_the_last_round(candidate)
        latest = latest_receipt_at(candidate)
        if latest is None or latest <= instant:
            if back == 0:
                said = (f"Generating up to today, {candidate.isoformat()} on {zone}'s clock "
                        f"(--roll-anchor).")
            else:
                local = asset_time.localise(late)
                when = (f"{local:%H:%M} today" if local.date() == today
                        else f"{local:%H:%M} on {local.date().isoformat()}")
                said = (f"Rolling to {candidate.isoformat()}: a receipt is still planned for "
                        f"{when}, {zone} time.")
            return Chosen(candidate, "rolled", said, back)
        late = latest if late is None else late
    raise AnchorRefused(
        f"no day from {today.isoformat()} back to "
        f"{max(today - timedelta(days=MOST_DAYS_BACK), history_anchor.FIXED_TEST_ANCHOR).isoformat()} "
        f"has every planned receipt already passed on {zone}'s clock, so there is no day to "
        f"roll to. Nothing was written. `mothman pipeline bootstrap` without --roll-anchor "
        f"still works.")


def mismatch(requested_anchor: date, recorded: date | None) -> str | None:
    """REQ-GEN-404 criterion 8 (SR3): a bare generation asked for an anchor
    other than the one recorded for the asset's current history refuses."""
    if recorded is None or recorded == requested_anchor:
        return None
    return (f"this asset's history was generated up to {recorded.isoformat()} (its anchor "
            f"file, {history_anchor.path()}), and this generation would write one up to "
            f"{requested_anchor.isoformat()} underneath it. Nothing was written. To replace "
            f"the history, run `mothman env reset-synthetic` then `mothman pipeline "
            f"bootstrap` (with --anchor or --roll-anchor for a date other than the fixed "
            f"test anchor).")
