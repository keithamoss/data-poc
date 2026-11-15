"""The player half of scripted person decisions (REQ-GEN-135; moved out of
qa_tools/common/scripted_decisions.py by REQ-GEN-381 criterion 1): plays a
collection's scripts into its replay, between arrivals, through the one
decision path a person uses.

THE BOOTSTRAP BUILDS EACH PLAYER AND PASSES IT IN (REQ-PIPE-383 criterion 2):
the replay takes a player argument, runs it before each arrival and after the
last, and runs none where none is passed - the real pipeline builds none and
imports nothing of this module, so `mothman pipeline run` and the processing
pass play no scripted decision (criterion 5). StreamPlayer, a stream's combined
player, moved here from qa_tools/tools/orchestrate.py with it.

The scripts themselves, their constants and their due-instant helpers are the
reader's, qa_tools/common/scripted_decisions.py (to scenarios/ with REQ-GEN-386).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from bootstrap import replay_clock
from qa_tools.common.scripted_decisions import (
    CHAIN_MARK,
    CHOOSE_FILE,
    PERIOD,
    Script,
    ScriptRefused,
    _due_at,
    _wall_clock_after,
    answers_for,
    label,
    load,
)


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
        from asset_model import hierarchy
        from qa_tools.common import scenario_map

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
    from asset_model import schedule, slots

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
    from asset_model import slots

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
    """Criterion 8: never on an asset that has not declared itself synthetic -
    read through the one reader (REQ-PIPE-382 criterion 7)."""
    from asset_model import asset_time

    if not asset_time.declared_synthetic():
        raise ScriptRefused(
            "scripted decisions are played back only into a synthetic history, and this "
            "data asset does not declare `synthetic: true`")


def _apply(t: Timed) -> None:
    """Raise one scripted decision through the one decision path every route
    uses (criterion 4), as the synthetic person (criterion 5)."""
    from qa_tools.common import filing_decisions as fd, people

    s = t.script
    # RECORDED WHEN IT TOOK EFFECT (REQ-PIPE-081 criterion 28; post-build-
    # review #156): the replay has already anchored its clock at the NEXT
    # arrival, so a person's evening decision was recorded as made the next
    # day, and the page said so. The player is the replay's, so it moves the
    # replay's clock itself - a no-op where none is installed.
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
                    from qa_tools.common import settlement
                    from asset_model import slots

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
    # AND THE KNOCK-ON IT OWES, at the same instant, as a person's decision is
    # followed (cli/filing_tui._follow_up; post-build-review #251): TS-80's
    # readers otherwise waited for Child Protection's next arrival.
    from asset_model import collections
    from qa_tools.common import knock_on

    knock_on.follow_up_stream(collections.collection_of(s.dataset_id).id)


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


class StreamPlayer:
    """Every collection's scripted decisions, played across one stream
    (REQ-PIPE-262 criterion 4): before ANY arrival of the stream received
    after a decision's instant, not only that collection's own next one."""

    def __init__(self, players):
        self.players = list(players)

    def before(self, arrival) -> int:
        return sum(p.before(arrival) or 0 for p in self.players)

    def finish(self) -> int:
        return sum(p.finish() or 0 for p in self.players)
