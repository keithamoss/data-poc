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

from qa_tools.common import config_yaml

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_PATH = ROOT / "contract" / "scripted_decisions.yaml"


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
    p = Path(path or SCRIPT_PATH)
    if not p.exists():
        return []
    doc = config_yaml.parse(p.read_text()) or {}
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
    from qa_tools.common import filing_decisions, hierarchy

    out = []
    for i, s in enumerate(scripts, 1):
        where = f"contract/scripted_decisions.yaml decision {i} ({label(s) if s.scenario or s.period else '?'})"
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
            out.append(f"{where}: no dataset {s.dataset_id!r} in contract/data-asset.yaml")
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
            out.append(f"contract/scripted_decisions.yaml decisions {first} and {i} "
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


@dataclass(frozen=True)
class Timed:
    script: Script
    at: datetime
    supply: str | None
    period: str
    #: The period a substitution stands on, resolved (REQ-GEN-200 criterion 3).
    stands_on: str | None = None
    #: The scenario's placement period, from which a settlement's relative
    #: re-file is counted (REQ-GEN-196 criterion 8).
    placement_period: str | None = None


class Player:
    """Plays a collection's scripted decisions into its replay, in order."""

    def __init__(self, collection_id: str, *, scripts: list[Script] | None = None,
                 placements: dict | None = None):
        from qa_tools.common import hierarchy, scenario_map

        mine = {d.dataset_id for d in hierarchy.datasets_in_collection(collection_id)}
        self.collection_id = collection_id
        self.pending = [s for s in (scripts if scripts is not None else load())
                        if s.dataset_id in mine]
        self.placements = (placements if placements is not None
                           else scenario_map.read_placements())
        if self.pending:
            _refuse_unless_synthetic()

    def _timed(self) -> tuple[list[Timed], list[tuple[Script, str]]]:
        """Each pending script with its instant, supply and period - resolved
        from the placement and the filings as they stand (criteria 2, 7) -
        and, separately, each one that cannot be resolved YET, with why.

        PER SCRIPT, and a script whose supply has not arrived waits for it:
        its receipt does not exist until it is filed, and one unresolvable
        script used to stop every other (found by the first replay - a
        TypeError on the first arrival took the whole replay down)."""
        from qa_tools.common import filing

        ready, waiting = [], []
        for s in self.pending:
            if s.period is not None:
                timed, why = _timed_chain(s)
                if timed is None:
                    waiting.append((s, why))
                else:
                    ready.append(timed)
                continue
            placement = self.placements.get(s.scenario)
            if s.scope == PERIOD:
                timed, why = _timed_by_period(s, placement)
                if timed is None:
                    waiting.append((s, why))
                else:
                    ready.append(timed)
                continue
            if s.supply_index is None:
                # Validate refuses this; the replay never calls validate, so
                # it is named here rather than reaching a TypeError below
                # (post-build-review #168).
                waiting.append((s, "it names neither a supply nor a period scope - give "
                                   "`supply: <index>` or `scope: period`"))
                continue
            if placement is None or not placement.supplies:
                waiting.append((s, "the scenario has no recorded placement with supplies - "
                                   "is it injected?"))
                continue
            if not 0 <= s.supply_index < len(placement.supplies):
                waiting.append((s, f"supply {s.supply_index} does not exist - its placement "
                                   f"recorded {len(placement.supplies)}"))
                continue
            supply = _supply_of(s.dataset_id, placement.supplies[s.supply_index])
            received = filing.received_at_of(s.dataset_id, supply)
            if received is None:
                waiting.append((s, f"{supply} has not arrived"))
                continue
            with _connect() as conn:
                period = conn.execute(
                    f"SELECT slot FROM {filing.CURRENT} WHERE dataset_id = ? AND supply_id = ?",
                    [s.dataset_id, supply]).fetchall()
            filed_to = (period[0][0] if period else None) or placement.period
            at = (_wall_clock_after(s, placement.period) if s.at is not None
                  else received + timedelta(hours=s.after_hours))
            if at is None:
                waiting.append((s, f"{s.dataset_id} has no date for {placement.period} to "
                                   f"time it from"))
                continue
            ready.append(Timed(s, at, supply if s.names_supply else None,
                               placement.period if s.period_from == "placement" else filed_to,
                               placement_period=placement.period))
        # STABLE, IN FILE ORDER AT ONE INSTANT (REQ-GEN-200 criterion 5):
        # `ready` is built in script order, and sorted() never reorders equal
        # keys - so a de-substitution listed before a mark-not-supplied on the
        # same instant is recorded first.
        return sorted(ready, key=lambda t: t.at), waiting

    def before(self, arrival) -> int:
        """Play every scripted decision that takes effect before this arrival
        was received (criterion 3). Returns how many it played."""
        return self._play(until=arrival.received_at)

    def finish(self) -> int:
        """Play what is left, after the last arrival - and refuse, loudly,
        any script still unplayable then (criterion 6)."""
        return self._play(until=None)

    def _play(self, until) -> int:
        if not self.pending:
            return 0
        ready, waiting = self._timed()
        if until is None and waiting:
            s, why = waiting[0]
            raise ScriptRefused(
                f"scripted decision for {label(s)} - {s.operation} {s.dataset_id} - could "
                f"not be played by the end of the replay: {why}. The replay stops here rather "
                f"than finish with a history missing it.")
        # "At or after" (criterion 3): one timed exactly at the arrival plays
        # before it.
        due = [t for t in ready if until is None or t.at <= until]
        for t in due:
            _apply(t)
            self.pending.remove(t.script)
        return len(due)


def _timed_chain(s: Script) -> tuple[Timed | None, str]:
    """An ordinary chain's instant (REQ-GEN-207): `after_hours` after the
    `supply`-th supply filed to its period, in receipt order - or None and
    why, while that supply has not arrived. A mark-not-supplied entry's is
    `after_hours` after its period's slot closes, from configuration alone."""
    from qa_tools.common import filing

    if s.operation == CHAIN_MARK:
        return _timed_mark(s)
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT supply_id FROM {filing.CURRENT} WHERE dataset_id = ? AND slot = ?",
            [s.dataset_id, s.period]).fetchall()
    received = sorted((r, sid) for sid, in rows
                      if (r := filing.received_at_of(s.dataset_id, sid)) is not None)
    if not 0 <= s.supply_index < len(received):
        return None, (f"supply {s.supply_index} of {s.period} has not arrived - "
                      f"{len(received)} filed so far")
    at, supply = received[s.supply_index]
    return Timed(s, at + timedelta(hours=s.after_hours), supply, s.period), ""


def _timed_mark(s: Script) -> tuple[Timed | None, str]:
    from qa_tools.common import schedule, slots

    on = schedule.date_of(s.period, s.dataset_id)
    if on is None:
        return None, f"{s.dataset_id} has no period {s.period} to mark"
    # FAR ENOUGH ON FOR THE NEXT PERIOD TO EXIST, which is what closes it.
    slot = next((x for x in slots.slots_for_dataset(s.dataset_id, until=on + timedelta(days=400))
                 if x.name == s.period), None)
    if slot is None or slot.closes_at is None:
        return None, f"{s.dataset_id}'s {s.period} slot has no closing instant yet"
    return Timed(s, slot.closes_at + timedelta(hours=s.after_hours), None, s.period), ""


def _timed_by_period(s: Script, placement) -> tuple[Timed | None, str]:
    """A period-scoped script's instant and periods (REQ-GEN-200 criteria 1
    and 3), or None and why it cannot be placed. Its period is the
    scenario's placement period; its instant is that period's due instant
    plus `after_hours`; a substitution's stood-on period is resolved here,
    its SUPPLY only when it is played - what that period holds depends on
    the decisions before it."""
    from qa_tools.common import slots

    if placement is None or not placement.period:
        return None, "the scenario has no recorded placement - is it injected?"
    due = _due_at(s.dataset_id, placement.period)
    if due is None:
        return None, (f"{s.dataset_id} has no slot for {placement.period} - a period-scoped "
                      f"decision is timed from when its period was due")
    stood = None
    if s.stands_on is not None:
        stood = slots.relative_period(s.dataset_id, placement.period, s.stands_on)
        if stood is None:
            return None, (f"{s.dataset_id} has no period {abs(s.stands_on)} before "
                          f"{placement.period} to stand on")
    return Timed(s, due + timedelta(hours=s.after_hours), None, placement.period, stood), ""


def _wall_clock_after(s: Script, period: str) -> datetime | None:
    """`at` on the day `day_offset` after the placement period's date, on
    the asset's clock (REQ-GEN-196 criterion 10)."""
    from qa_tools.common import asset_time, schedule

    on = schedule.date_of(period, s.dataset_id)
    return None if on is None else asset_time.wall_clock(on + timedelta(days=s.day_offset),
                                                         s.at)


def _due_at(dataset_id: str, period: str) -> datetime | None:
    """When this dataset's slot for `period` was due, as the slot schedule
    computes it from configuration (REQ-GEN-200 criterion 1)."""
    from qa_tools.common import schedule, slots

    on = schedule.date_of(period, dataset_id)
    return None if on is None else slots.slot_instants(dataset_id, on).due_at


def _supply_of(dataset_id: str, run_id: str) -> str:
    """The FILED supply a recorded run is about (REQ-GEN-196 criterion 9):
    an arrival that brought two files for one table is filed as
    `<dataset>@<key>#1`, never the plain id no filing carries - asked of
    the filings, by the one resolver, not rebuilt from the run id."""
    from qa_tools.common import filing, supply_db, supply_files

    parts = supply_db.split_staged(run_id)
    if not parts:
        raise ScriptRefused(f"{run_id} is not a run id an arrival gives")
    with _connect() as conn:
        filed = supply_files.supply_for_table(conn, dataset_id, run_id)
        if filed is None or not supply_files.ordinal_of(filed):
            pair = f"{dataset_id}@{parts[1]}#1"
            if conn.execute(f"SELECT 1 FROM {filing.CURRENT} WHERE dataset_id = ? "
                            "AND supply_id = ?", [dataset_id, pair]).fetchall():
                return pair
    return filed or f"{dataset_id}@{parts[1]}"


def _connect():
    from qa_tools.common import supply_db

    return supply_db.connect(label="mothman:scripted-decisions")


def _refuse_unless_synthetic() -> None:
    """Criterion 8: never on an asset that has not declared itself synthetic."""
    from qa_tools.common.hierarchy import DATA_ASSET_YAML

    doc = config_yaml.parse(Path(DATA_ASSET_YAML).read_text()) or {}
    if not doc.get("synthetic"):
        raise ScriptRefused(
            "scripted decisions are played back only into a synthetic history, and this "
            "data asset does not declare `synthetic: true`")


def _apply(t: Timed) -> None:
    """Raise one scripted decision through the one decision path every route
    uses (criterion 4), as the synthetic person (criterion 5)."""
    from qa_tools.common import filing_decisions as fd, people

    from qa_tools.common import replay_clock

    s = t.script
    # RECORDED WHEN IT TOOK EFFECT (REQ-PIPE-081 criterion 28; post-build-
    # review #156): the replay has already anchored its clock at the NEXT
    # arrival, so a person's evening decision was recorded as made the next
    # day, and the page said so.
    if replay_clock.active():
        replay_clock.anchor(t.at)
    with people.playback():
        actor = people.synthetic_actor()

        try:
            with _connect() as conn:
                # THE SUPPLY THE STOOD-ON PERIOD HOLDS AS PROMOTED, at the
                # decision's own instant (REQ-GEN-200 criterion 3). None where it
                # holds nothing, and then the filing decision's own refusal
                # stands - never a fall-back to another period (criterion 6).
                supply = t.supply
                if t.stands_on is not None:
                    from qa_tools.common import decision_log
                    supply = decision_log.promoted_into(conn, s.dataset_id, t.stands_on,
                                                        t.at.isoformat())

                # A SETTLEMENT'S FILES BY POSITION, resolved now (REQ-GEN-196
                # criteria 7 and 8): the pair's real files in receipt order,
                # and each relative re-file counted from the placement.
                outcomes = ()
                if s.operation == CHOOSE_FILE:
                    from qa_tools.common import settlement, slots

                    _delivery, _period, files = settlement.pair_files(conn, s.dataset_id,
                                                                      supply)
                    outcomes = tuple(answers_for(
                        s, [f.filename for f in files],
                        lambda n: slots.relative_period(
                            s.dataset_id, t.placement_period or t.period, n)))

                def ask(key=None):
                    return fd.Request(operation=s.operation, dataset_id=s.dataset_id,
                                      actor=actor, reason=s.reason, period=t.period,
                                      supply=supply, to_period=s.to_period,
                                      stands_on=t.stands_on, confirmed=True,
                                      acknowledged=key, file_outcomes=outcomes)
                key = fd.consequences(conn, ask()).key
                # NO TYPED ENVIRONMENT ID (REQ-PIPE-093 criterion 9): scripted
                # playback is unattended, and the published PoC is bootstrapped in
                # production from synthetic data - a prompt would make it unbootable.
                outcome = fd.apply(ask(key or None), effective_at=t.at.isoformat(), conn=conn)
                # A DECISION THAT CHANGED NOTHING STOPS THE REPLAY TOO (Keith,
                # 2026-10-13, amending criterion 6): for a person "already done"
                # is a true and useful answer, but a script exists to put a
                # decision INTO the history, and one that changed nothing leaves
                # the scenario quietly without it.
                if not outcome.changed:
                    raise RuntimeError(f"it changed nothing - {outcome.message}")
        except Exception as exc:  # noqa: BLE001 - criterion 6: ANY failure stops the replay
            raise ScriptRefused(
                f"scripted decision for {label(s)} - "
                + " ".join(x for x in (s.operation, s.dataset_id, t.period, t.supply,
                                       f"standing on {t.stands_on}" if t.stands_on else None,
                                       f"at {t.at.isoformat()}") if x)
                + f" - was refused: {str(exc).rstrip('.')}. "
                f"The replay stops here rather than continue with a history missing it."
            ) from exc
    print(f"scripted: {s.operation} {s.dataset_id} {t.period} ({label(s)})")
    # EVERY RE-CHECK IT OWED, in order (REQ-GEN-196 criterion 10): a
    # settlement owes one per file that became a supply.
    for owed_id in outcome.owed:
        _run_the_re_check_it_owed(t, owed_id)


def _run_the_re_check_it_owed(t: Timed, owed_id: int) -> None:
    """The re-check a decision owed, run at the decision's own instant, as
    the terminal runs it while a person waits (post-build-review #161;
    Keith, 2026-10-13: every scripted decision). It used to be discarded, so
    TS-67's re-filed supplies were never checked nor gated in their new
    period. The decision is committed first, so the run reads it. A re-check
    that does not complete stops the replay, as a refused decision does
    (criterion 6): a history whose decision was never checked is the same
    gap."""
    from qa_tools.common import recheck

    s = t.script
    try:
        got = recheck.run(owed_id)
    except Exception as exc:  # noqa: BLE001 - criterion 6, as above
        got = recheck.Outcome(owed_id, "", False, str(exc))
    if not got.completed:
        raise ScriptRefused(
            f"scripted decision for {label(s)} - {s.operation} {s.dataset_id} - was "
            f"recorded, but the re-check it owed did not complete: {got.message}. The "
            f"replay stops here rather than continue with a history missing it.")
    print(f"scripted: re-checked {s.dataset_id} ({label(s)}): {got.status or got.message}")
