"""Scripted person decisions, played back into a synthetic history
(REQ-GEN-135).

WHY. Several scenarios are about what a PERSON decides - un-superseding a
good file after rejecting a bad one, marking a closed period not supplied,
acknowledging an amber promotion. A generator can plant an arrival; it
cannot plant a decision without writing the decision log itself, which is
the one thing nothing but the decision path may do. So the decisions are
scripted, as committed configuration (`contract/scripted_decisions.yaml`),
and the replay raises each one through filing_decisions.apply() - the same
judgement a person's decision gets, against the filing state at that point
(criterion 4).

THREE LOCKS, ALL OF WHICH MUST HOLD (NFR 2), because this is the one path
that writes a person's decision with no person behind it:
  1. the data asset declares itself synthetic (criterion 8);
  2. the actor is the synthetic entry in contract/people.yaml, which
     people.person_by_email refuses outside playback() and which has no
     GitHub username, so the GitHub route cannot reach it (criteria 9, 10);
  3. playback happens only inside the batch replay, before each arrival
     (criterion 3), never from a route a person drives.

WHERE AND WHEN, FROM THE SCENARIO'S PLACEMENT (criteria 2 and 7): a script
names its scenario and an index into that scenario's recorded supplies,
never a generated supply id; the decision takes effect a stated number of
hours after that supply was received. Same configuration, same history,
same decisions at the same instants.

THE READER AND THE PLAYER ARE TWO MODULES (REQ-GEN-381 criterion 1): this one
reads the selected asset's scripted_decisions.yaml - what the generator, the
gates and the player all read (it goes to scenarios/ with REQ-GEN-386
criterion 4) - and bootstrap/decision_player.py plays them, the half only a
replay of a synthetic history has. The real pipeline imports neither
(REQ-PIPE-383 criterion 2).

A REFUSAL STOPS THE REPLAY (criterion 6), naming the scenario, the decision
and the refusal - a history silently missing the decision a scenario is
about is the failure REQ-GEN-044 exists to prevent.

A DECISION ABOUT A PERIOD THAT RECEIVED NOTHING (REQ-GEN-200). Timing from a
supply cannot place a substitution: the period it is about never received
one. So a script may be scoped to the scenario's PERIOD instead (`scope:
period`), timed a stated number of hours after that period was due, and a
substitution names the period it stands on as an offset (`stands_on: -1`),
resolved at play time through slots.relative_period() - the one resolver -
with the supply that period then holds as promoted. Nothing in the script
moves when ANCHOR_DATE is bumped.

AN ORDINARY CHAIN, NOT A SCENARIO (REQ-GEN-207, Keith, 2026-10-16). A red in
Child Protection's grown years leaves its resend waiting under replacement
`never`, a permanent queue item no scenario is about. Such an entry names no
scenario: it names the dataset's PERIOD, an index into the supplies filed to
that period in receipt order, and only promote or reject.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from asset_model import config_yaml

ROOT = Path(__file__).resolve().parent.parent


def script_path() -> Path:
    """The selected asset's scripted_decisions.yaml, resolved now (REQ-PIPE-342 criterion
    6; it was the import-time constant SCRIPT_PATH)."""
    from asset_model import assets

    return assets.selected().synthetic / "scripted_decisions.yaml"


class ScriptRefused(RuntimeError):
    """A scripted decision could not be played back. Loud by design."""


#: The scope a script names when it is about its scenario's PERIOD rather
#: than one of its supplies (REQ-GEN-200 criterion 1).
PERIOD = "period"
#: The decisions that may be period-scoped (criterion 2): the ones about a
#: period that received no supply of its own.
PERIOD_SCOPED_OPERATIONS = ("substitute", "de-substitute", "mark-not-supplied")
#: What an ordinary chain's entry may decide (REQ-GEN-207): settle it.
CHAIN_OPERATIONS = ("promote", "reject")
#: A chain entry about a period with NOTHING filed to it (Keith, 2026-10-19):
#: Child Protection's quarters emptied by REQ-GEN-237 criterion 3, accepted
#: as not supplied. It names no supply and is timed from the slot's close.
CHAIN_MARK = "mark-not-supplied"


def label(s) -> str:
    """What a refusal calls a script: its scenario, or an ordinary chain's
    dataset and period."""
    return s.scenario or f"{s.dataset_id} {s.period}"


@dataclass(frozen=True)
class Script:
    scenario: str
    operation: str
    dataset_id: str
    reason: str
    #: Which of the scenario's recorded supplies the decision is about (or is
    #: timed from), by index - never a generated id (criterion 2). None for a
    #: period-scoped script, which names no supply (REQ-GEN-200).
    supply_index: int | None
    #: Hours after that supply was received that the decision takes effect.
    after_hours: float
    #: Whether the decision names the supply (promote, reject, ...) or only
    #: the period (mark-not-supplied).
    names_supply: bool = True
    to_period: str | None = None
    #: Whose period the decision is about: `filed` - the period the supply is
    #: filed to - or `placement` - the scenario's own anchor period, for a
    #: decision about a period the supply did NOT fill (marking it not
    #: supplied).
    period_from: str = "filed"
    #: `period` scopes the decision to the scenario's placement period,
    #: timed from that period's due instant (REQ-GEN-200 criterion 1).
    scope: str | None = None
    #: For a substitution: the period it stands on, as an offset from the
    #: placement period in the dataset's own sequence (-1 the period before).
    stands_on: int | None = None
    #: What a scenario link calls this decision when it bounds a date
    #: (REQ-GEN-201 criterion 3) - unique within its scenario. A name, not
    #: its position in the file, which an inserted decision would move.
    name: str | None = None
    #: A settlement's outcome for each file of the pair, BY ITS POSITION IN
    #: RECEIPT ORDER (REQ-GEN-196 criterion 7): `supply`, `reject`,
    #: `supersede` or `refile:+N` - a period counted from the placement's
    #: (criterion 8). Never a filename, whose date moves with ANCHOR_DATE.
    files: tuple[str, ...] = ()
    #: Timed at a WALL CLOCK on a day counted from the placement period
    #: (REQ-GEN-196 criterion 10: 11:00 on D+1) rather than hours after a
    #: receipt - `day_offset` days after it, at `at` on the asset's clock.
    at: str | None = None
    day_offset: int = 0
    #: Whether `after_hours:` was written, so `at:` beside it is refused.
    after_hours_given: bool = False
    #: For an ordinary chain rather than a scenario (REQ-GEN-207): the
    #: dataset's period whose supplies `supply:` indexes, in receipt order.
    period: str | None = None


def load(path: Path | str | None = None) -> list[Script]:
    """The committed script, in file order. Absent is empty."""
    p = Path(path or script_path())
    if not p.exists():
        return []
    doc = config_yaml.load(p) or {}
    out = []
    for raw in _expanded(doc.get("decisions") or []):
        out.append(Script(
            scenario=str(raw.get("scenario") or ""), operation=str(raw.get("operation") or ""),
            dataset_id=str(raw.get("dataset") or ""), reason=str(raw.get("reason") or ""),
            # NO DEFAULT SUPPLY (REQ-GEN-200 criterion 9): an absent index used
            # to read as supply 0, so a script naming neither a supply nor a
            # period was silently about the scenario's first supply.
            supply_index=(int(raw["supply"]) if raw.get("supply") is not None else None),
            after_hours=float(raw.get("after_hours", 1)),
            names_supply=bool(raw.get("names_supply", True)),
            to_period=raw.get("to_period"),
            period_from=str(raw.get("period_from") or "filed"),
            scope=(str(raw["scope"]) if raw.get("scope") is not None else None),
            stands_on=(int(raw["stands_on"]) if raw.get("stands_on") is not None else None),
            name=(str(raw["name"]) if raw.get("name") is not None else None),
            files=tuple(str(f) for f in (raw.get("files") or ())),
            at=(str(raw["at"]) if raw.get("at") is not None else None),
            day_offset=int(raw.get("day_offset", 0)),
            after_hours_given="after_hours" in raw,
            period=(str(raw["period"]) if raw.get("period") is not None else None)))
    return out


def _expanded(entries: list[dict]) -> list[dict]:
    """A chain entry may list `periods:` - one entry per period, in order -
    rather than repeating itself for each (Keith, 2026-10-19)."""
    out = []
    for raw in entries:
        periods = raw.get("periods")
        if periods is None:
            out.append(raw)
            continue
        rest = {k: v for k, v in raw.items() if k != "periods"}
        out += [{**rest, "period": p} for p in periods]
    return out


CHOOSE_FILE = "choose-file"


def wall_clock_after(s: Script, period: str) -> datetime | None:
    """`at` on the day `day_offset` after the placement period's date, on
    the asset's clock (REQ-GEN-196 criterion 10)."""
    from asset_model import asset_time, schedule

    # FROM THE ROUND its slot is due on (REQ-GEN-325 criterion 3).
    on = schedule.round_of(period, s.dataset_id)
    return None if on is None else asset_time.wall_clock(on + timedelta(days=s.day_offset),
                                                         s.at)


def due_at(dataset_id: str, period: str) -> datetime | None:
    """When this dataset's slot for `period` was due, as the slot schedule
    computes it from configuration (REQ-GEN-200 criterion 1)."""
    from asset_model import schedule, slots

    # THE ROUND the slot is due on (REQ-PIPE-321 criterion 2), never the
    # period's own date.
    on = schedule.round_of(period, dataset_id)
    return None if on is None else slots.slot_instants(dataset_id, on).due_at
