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
from asset_model import assets as _assets

ROOT = Path(__file__).resolve().parent.parent.parent


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


def answers_for(s: Script, filenames: list[str], period_at) -> list:
    """A scripted settlement's answers, each file's position resolved to its
    filename and each relative re-file to its period - THE ONE resolution
    (REQ-GEN-196 criterion 7), called by the replay with the pair's real
    files in receipt order and by validate with stand-ins. `period_at(n)`
    names the period `n` after the placement's. Raises ValueError, naming
    the fault, on a malformed outcome."""
    from qa_tools.common import settlement

    if len(s.files) != len(filenames):
        raise ValueError(f"it gives {len(s.files)} file outcome(s) and the pair has "
                         f"{len(filenames)} files - give exactly one per position, 1 and 2, "
                         f"in receipt order")
    out = []
    for position, (token, filename) in enumerate(zip(s.files, filenames), 1):
        outcome, _, rest = token.partition(":")
        if outcome not in settlement.OUTCOMES:
            raise ValueError(f"file {position}'s outcome {token!r} is not one of supply, "
                             f"reject, supersede or refile:+N")
        to = None
        if outcome == settlement.REFILE:
            try:
                offset = int(rest)
            except ValueError:
                raise ValueError(f"file {position}'s re-file {token!r} names no period - "
                                 f"write refile:+N, N periods after the placement's") from None
            if offset <= 0:
                raise ValueError(f"file {position}'s re-file {token!r} is not after the "
                                 f"placement's period - the pair's own period is 'supply'")
            to = period_at(offset)
            if to is None:
                raise ValueError(f"file {position}'s re-file {token!r} names a period the "
                                 f"dataset does not have")
        elif rest:
            raise ValueError(f"file {position}'s outcome {token!r} takes no period")
        out.append(settlement.Answer(filename, outcome, to))
    return out


def _settlement_problems(s: Script, where: str) -> list[str]:
    """REQ-GEN-196 criterion 12, from configuration alone: one outcome per
    position, each well formed, and a combination REQ-PIPE-193 criterion 4
    allows - judged by the settlement's own rule, on stand-in files."""
    from qa_tools.common import settlement

    if s.operation != CHOOSE_FILE:
        return ([f"{where}: `files:` is only for a settlement (choose-file)"]
                if s.files else [])
    try:
        answers = answers_for(s, ["file 1", "file 2"], lambda n: f"the period +{n}")
    except ValueError as exc:
        return [f"{where}: {exc}"]
    files = [settlement.PairFile(a.filename, None, "", False) for a in answers]
    broken = settlement.rule_broken(None, s.dataset_id, "the placement's period", files,
                                    answers)
    return [f"{where}: {broken}"] if broken else []


def problems(scripts: list[Script], *, registered: set[str],
             placement_of: dict[str, str] | None = None) -> list[str]:
    """Criterion 13, against configuration alone: every scenario registered,
    every decision a filing decision, every reason present."""
    from qa_tools.common import filing_decisions
    from asset_model import hierarchy

    out = []
    for i, s in enumerate(scripts, 1):
        where = f"{_assets.config_dir()}/synthetic/scripted_decisions.yaml decision {i} ({label(s) if s.scenario or s.period else '?'})"
        if s.period is not None:
            out += _chain_problems(s, where)
        elif s.scenario not in registered:
            out.append(f"{where}: scenario {s.scenario!r} is not in the register")
        if s.operation not in filing_decisions.OPERATIONS:
            out.append(f"{where}: {s.operation!r} is not a filing decision - one of "
                       f"{', '.join(filing_decisions.OPERATIONS)}")
        if s.period_from not in ("filed", "placement"):
            out.append(f"{where}: period_from must be filed or placement, not {s.period_from!r}")
        if not s.reason.strip():
            out.append(f"{where}: a scripted decision needs a reason, as a person's does")
        try:
            hierarchy.dataset(s.dataset_id)
        except hierarchy.UnknownDatasetError:
            out.append(f"{where}: no dataset {s.dataset_id!r} in {_assets.config_dir()}/data-asset.yaml")
        if s.period is None:
            out += _scope_problems(s, where)
            out += _settlement_problems(s, where)
        if s.at is not None and s.after_hours_given:
            out.append(f"{where}: give `at:` (with `day_offset:`) or `after_hours:`, not "
                       f"both - each says when it takes effect")
    # ONE NAME, ONE DECISION, PER PLACEMENT (REQ-GEN-201 criterion 3): a link
    # looks names up across every scenario sharing its placement, so one
    # name on two siblings' decisions names neither (Keith, 2026-10-13).
    # `placement_of` maps a scenario id to its placement's; absent, each
    # scenario is its own.
    group = placement_of or {}
    named: dict[tuple[str, str], int] = {}
    for i, s in enumerate(scripts, 1):
        if s.name is None:
            continue
        first = named.setdefault((group.get(s.scenario, s.scenario), s.name), i)
        if first != i:
            other = scripts[first - 1].scenario
            scope = (f"({s.scenario})" if other == s.scenario
                     else f"({other} and {s.scenario}, which share a placement)")
            out.append(f"{_assets.config_dir()}/synthetic/scripted_decisions.yaml decisions {first} and {i} "
                       f"{scope} are both named {s.name!r} - a name is unique within the "
                       f"scenarios sharing a placement; rename one")
    return out


def _chain_problems(s: Script, where: str) -> list[str]:
    """An ordinary chain's entry (REQ-GEN-207): a period, a supply in it,
    and a settlement - and nothing a scenario's entry needs."""
    out = []
    if s.scenario:
        out.append(f"{where}: names scenario {s.scenario!r} and `period:` - an entry is about "
                   f"a scenario or an ordinary chain's period, not both")
    if s.operation == CHAIN_MARK:
        if s.supply_index is not None:
            out.append(f"{where}: a mark-not-supplied entry names no supply - its period has "
                       f"none - drop `supply:`")
    elif s.supply_index is None:
        out.append(f"{where}: a chain entry needs `supply: <index>` - which of the period's "
                   f"supplies, in receipt order")
    if s.operation not in CHAIN_OPERATIONS and s.operation != CHAIN_MARK:
        out.append(f"{where}: an ordinary chain is settled by promote or reject, or an empty "
                   f"period marked not supplied, not {s.operation!r}")
    for field_name, is_set in (("scope", s.scope is not None),
                               ("to_period", s.to_period is not None),
                               ("period_from", s.period_from != "filed"),
                               ("names_supply", not s.names_supply),
                               ("at", s.at is not None), ("name", s.name is not None),
                               ("files", bool(s.files))):
        if is_set:
            out.append(f"{where}: `{field_name}:` means nothing on a chain entry - drop it")
    return out


def _scope_problems(s: Script, where: str) -> list[str]:
    """REQ-GEN-200 criterion 8, from configuration alone: what a script is
    about, and what a substitution stands on. Each names what to change."""
    out = []
    if s.scope not in (None, PERIOD):
        out.append(f"{where}: scope must be `period` or absent, not {s.scope!r}")
    period_scoped = s.scope == PERIOD
    if s.supply_index is None and not period_scoped:
        out.append(f"{where}: names neither a supply nor a period scope - give `supply: <index>` "
                   f"for a decision about one of the scenario's supplies, or `scope: period` for "
                   f"one about its period")
    if period_scoped and s.supply_index is not None:
        out.append(f"{where}: names both a supply and `scope: period` - a period-scoped decision "
                   f"is timed from the period's due instant; drop `supply:`")
    if period_scoped and s.operation not in PERIOD_SCOPED_OPERATIONS:
        out.append(f"{where}: {s.operation!r} cannot be period-scoped - only "
                   f"{', '.join(PERIOD_SCOPED_OPERATIONS)} are about a period with no supply; "
                   f"name the supply instead")
    if period_scoped and s.operation == "substitute" and s.stands_on is None:
        out.append(f"{where}: a substitution needs `stands_on:` - the period it stands on, as "
                   f"an offset (-1 the period before)")
    # A SUBSTITUTION IS ALWAYS ABOUT A PERIOD (post-build-review #168): one
    # scoped to a supply passed here and then lost its stands_on at play
    # time, so the replay asked for a substitution standing on nothing.
    if s.operation == "substitute" and not period_scoped:
        out.append(f"{where}: a substitution is about a period with no supply of its own - "
                   f"give `scope: period` and `stands_on:` (-1 the period before), not "
                   f"`supply:`")
    if s.after_hours < 0:
        out.append(f"{where}: `after_hours: {s.after_hours}` is before the instant it is timed "
                   f"from - a decision takes effect at or after it")
    if period_scoped:
        # FIELDS A PERIOD-SCOPED DECISION WOULD SILENTLY IGNORE: its period is
        # the placement's and it names no supply.
        for field_name, is_set in (("to_period", s.to_period is not None),
                                   ("period_from", s.period_from != "filed"),
                                   ("names_supply", not s.names_supply)):
            if is_set:
                out.append(f"{where}: `{field_name}:` means nothing on a period-scoped "
                           f"decision, whose period is the scenario's own - drop it")
    if s.stands_on is not None and s.operation != "substitute":
        out.append(f"{where}: `stands_on:` is only for a substitution, not {s.operation!r}")
    if s.stands_on is not None and s.stands_on >= 0:
        out.append(f"{where}: `stands_on: {s.stands_on}` is not before the period it fills - "
                   f"a substitution stands on an EARLIER period (-1 the period before)")
    return out


def _wall_clock_after(s: Script, period: str) -> datetime | None:
    """`at` on the day `day_offset` after the placement period's date, on
    the asset's clock (REQ-GEN-196 criterion 10)."""
    from asset_model import asset_time, schedule

    # FROM THE ROUND its slot is due on (REQ-GEN-325 criterion 3).
    on = schedule.round_of(period, s.dataset_id)
    return None if on is None else asset_time.wall_clock(on + timedelta(days=s.day_offset),
                                                         s.at)


def _due_at(dataset_id: str, period: str) -> datetime | None:
    """When this dataset's slot for `period` was due, as the slot schedule
    computes it from configuration (REQ-GEN-200 criterion 1)."""
    from asset_model import schedule, slots

    # THE ROUND the slot is due on (REQ-PIPE-321 criterion 2), never the
    # period's own date.
    on = schedule.round_of(period, dataset_id)
    return None if on is None else slots.slot_instants(dataset_id, on).due_at
