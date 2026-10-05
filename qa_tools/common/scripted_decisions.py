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
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_PATH = ROOT / "contract" / "scripted_decisions.yaml"


class ScriptRefused(RuntimeError):
    """A scripted decision could not be played back. Loud by design."""


@dataclass(frozen=True)
class Script:
    scenario: str
    operation: str
    dataset_id: str
    reason: str
    #: Which of the scenario's recorded supplies the decision is about (or is
    #: timed from), by index - never a generated id (criterion 2).
    supply_index: int
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


def load(path: Path | str | None = None) -> list[Script]:
    """The committed script, in file order. Absent is empty."""
    p = Path(path or SCRIPT_PATH)
    if not p.exists():
        return []
    doc = yaml.safe_load(p.read_text()) or {}
    out = []
    for raw in doc.get("decisions") or []:
        out.append(Script(
            scenario=str(raw.get("scenario") or ""), operation=str(raw.get("operation") or ""),
            dataset_id=str(raw.get("dataset") or ""), reason=str(raw.get("reason") or ""),
            supply_index=int(raw.get("supply", 0)), after_hours=float(raw.get("after_hours", 1)),
            names_supply=bool(raw.get("names_supply", True)),
            to_period=raw.get("to_period"),
            period_from=str(raw.get("period_from") or "filed")))
    return out


def problems(scripts: list[Script], *, registered: set[str]) -> list[str]:
    """Criterion 13, against configuration alone: every scenario registered,
    every decision a filing decision, every reason present."""
    from qa_tools.common import filing_decisions, hierarchy

    out = []
    for i, s in enumerate(scripts, 1):
        where = f"contract/scripted_decisions.yaml decision {i} ({s.scenario or '?'})"
        if s.scenario not in registered:
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
    return out


@dataclass(frozen=True)
class Timed:
    script: Script
    at: datetime
    supply: str | None
    period: str


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
            placement = self.placements.get(s.scenario)
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
            ready.append(Timed(s, received + timedelta(hours=s.after_hours),
                               supply if s.names_supply else None,
                               placement.period if s.period_from == "placement" else filed_to))
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
                f"scripted decision for {s.scenario} - {s.operation} {s.dataset_id} - could "
                f"not be played by the end of the replay: {why}. The replay stops here rather "
                f"than finish with a history missing it.")
        # "At or after" (criterion 3): one timed exactly at the arrival plays
        # before it.
        due = [t for t in ready if until is None or t.at <= until]
        for t in due:
            _apply(t)
            self.pending.remove(t.script)
        return len(due)


def _supply_of(dataset_id: str, run_id: str) -> str:
    from qa_tools.common import supply_db

    parts = supply_db.split_staged(run_id)
    if not parts:
        raise ScriptRefused(f"{run_id} is not a run id an arrival gives")
    return f"{dataset_id}@{parts[1]}" + (f"#{parts[2]}" if parts[2] else "")


def _connect():
    from qa_tools.common import supply_db

    return supply_db.connect(label="mothman:scripted-decisions")


def _refuse_unless_synthetic() -> None:
    """Criterion 8: never on an asset that has not declared itself synthetic."""
    from qa_tools.common.hierarchy import DATA_ASSET_YAML

    doc = yaml.safe_load(Path(DATA_ASSET_YAML).read_text()) or {}
    if not doc.get("synthetic"):
        raise ScriptRefused(
            "scripted decisions are played back only into a synthetic history, and this "
            "data asset does not declare `synthetic: true`")


def _apply(t: Timed) -> None:
    """Raise one scripted decision through the one decision path every route
    uses (criterion 4), as the synthetic person (criterion 5)."""
    from qa_tools.common import filing_decisions as fd, people

    s = t.script
    with people.playback():
        actor = people.synthetic_actor()

        def ask(key=None):
            return fd.Request(operation=s.operation, dataset_id=s.dataset_id, actor=actor,
                              reason=s.reason, period=t.period, supply=t.supply,
                              to_period=s.to_period, confirmed=True, acknowledged=key)
        try:
            with _connect() as conn:
                key = fd.consequences(conn, ask()).key
                fd.apply(ask(key or None), effective_at=t.at.isoformat(), conn=conn)
        except Exception as exc:  # noqa: BLE001 - criterion 6: ANY failure stops the replay
            raise ScriptRefused(
                f"scripted decision for {s.scenario} - {s.operation} {s.dataset_id} "
                f"{t.period} {t.supply or ''} at {t.at.isoformat()} - was refused: {exc}. "
                f"The replay stops here rather than continue with a history missing it."
            ) from exc
    print(f"scripted: {s.operation} {s.dataset_id} {t.period} ({s.scenario})")
