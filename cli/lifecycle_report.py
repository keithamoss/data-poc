"""What the lifecycle decided about each arrival a person kept, and on what
grounds (REQ-TEST-150).

EVERY OUTCOME IS READ BACK, NEVER WORKED OUT (criterion 9): the filing, the
hold and the decision-log entries are what the pipeline RECORDED, so the
terminal says what happened rather than re-deriving which slot or why - a
second implementation of assignment is exactly what REQ-PIPE-086 forbids.

AGGREGATED, NOT REPEATED (criterion 8): the same outcome for six arrivals is
one line naming how many, and an arrival whose outcome differs gets a line of
its own - the rule REQ-DASH-070 applies on the dashboard, because a quarterly
round driven by hand at thirty datasets is long enough already.

WORDS, NOT COLOUR: every line reads with NO_COLOR or a pipe.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass

from rich.console import Console

console = Console()

_CLASSIFICATION = {"on_time": "on time", "early": "early", "late": "late",
                   "unfiled": "unfiled"}


@dataclass(frozen=True)
class Outcome:
    """One kept arrival, as recorded."""

    run_id: str
    dataset_id: str
    filed: str        # criteria 1 and 2
    gate: str         # criterion 5
    extra: tuple[str, ...] = ()  # criteria 3, 4 and 6

    def lines(self) -> list[str]:
        return [self.filed, self.gate, *self.extra]


def _supply_of(arrival, dataset_id) -> str:
    from qa_tools.common import asset_time

    names = arrival.files_by_dataset.get(dataset_id) or ()
    base = f"{dataset_id}@{asset_time.arrival_key(arrival.received_at)}"
    return base if len(names) <= 1 else f"{base}#1"


def outcome_of(conn, arrival, since=None) -> Outcome:
    """Criterion 9's single source: the recorded rows for one arrival."""
    from qa_tools.common import decision_log, filing, supply_holds

    (dataset_id, names), = arrival.files_by_dataset.items()
    supply = _supply_of(arrival, dataset_id)
    base = supply.split("#", 1)[0]
    rows = conn.execute(
        f"SELECT slot, classification, considered FROM {filing.CURRENT} "
        "WHERE dataset_id = ? AND split_part(supply_id, '#', 1) = ? ORDER BY id DESC LIMIT 1",
        [dataset_id, base]).fetchall()
    extra: list[str] = []
    if rows and rows[0][0]:
        slot, classification, _ = rows[0]
        filed = (f"recognised as {dataset_id}; filed to {slot}, "
                 f"{_CLASSIFICATION.get(classification, classification or 'unclassified')}")
    else:
        filed = f"recognised as {dataset_id}; filed to no period"
        hold = supply_holds.hold_on(conn, dataset_id, supply)
        reason = (getattr(hold, "reason", None) or {}) if hold else {}
        unavailable = reason.get("unavailable") or []
        why = "; ".join(f"{slot}: {text}" for slot, text in unavailable) or \
            "no slot was available"
        # CRITERION 3: held, the slots considered and why each was not
        # available, and that nothing was checked.
        extra.append(f"held - {why}. No check ran over it.")
    if len(names) > 1:
        # CRITERION 4: contested, naming the other file.
        extra.append(f"contested - {', '.join(sorted(names))} were staged for the same table "
                     f"and period; nothing chooses between them")
    gate = _gate_line(conn, dataset_id, supply)
    if since is not None:
        for slot, stands_on in conn.execute(
                f"SELECT to_slot, stands_on FROM {decision_log.TABLE} WHERE dataset_id = ? "
                "AND action = ? AND actor_kind = ? AND recorded_at >= ? ORDER BY id",
                [dataset_id, decision_log.INHERIT, decision_log.RULE, since]).fetchall():
            # CRITERION 6: an inheritance the cadence made, as the rule's.
            extra.append(f"the rule inherited {stands_on}'s supply into {slot}, which "
                         f"filing opened")
    return Outcome(arrival.run_id, dataset_id, filed, gate, tuple(extra))


def _gate_line(conn, dataset_id: str, supply: str) -> str:
    """CRITERION 5: what the gate did, with the reason it recorded - and that
    the rule decided it, not the person running the command."""
    from qa_tools.common import decision_log

    rows = conn.execute(
        f"SELECT action, reason, actor FROM {decision_log.TABLE} WHERE dataset_id = ? "
        "AND supply = ? AND actor_kind = ? AND action IN (?, ?, ?) ORDER BY id DESC LIMIT 1",
        [dataset_id, supply, decision_log.RULE, decision_log.PROMOTE,
         decision_log.PROMOTION_WITHHELD, decision_log.PROMOTION_REFUSED]).fetchall()
    if not rows:
        return "no gate outcome is recorded yet - it is owed to the next processing pass"
    action, reason, actor = rows[0]
    said = {decision_log.PROMOTE: "promoted",
            decision_log.PROMOTION_WITHHELD: "withheld",
            decision_log.PROMOTION_REFUSED: "left for a person"}[action]
    return f"{said} by the rule ({actor}), not by you - {(reason or '').strip()}"


def report(found, *, since=None, say=None) -> list[Outcome]:
    """Criteria 1 to 8 for the arrivals one kept supply became."""
    from qa_tools.common import supply_db

    say = say or (lambda line: console.print(line, markup=False, highlight=False))
    with supply_db.connect(read_only=True, label="mothman:kept-report") as conn:
        outcomes = [outcome_of(conn, a, since) for a in found]
    say("What the lifecycle decided:")
    for line, who in _grouped(outcomes):
        say(f"  {who}: {line}" if who else f"  {line}")
    return outcomes


def _grouped(outcomes: list[Outcome]):
    """One line per distinct outcome line; how many arrivals share it, or
    which arrival it is when only one does (criterion 8)."""
    groups: "OrderedDict[str, list[str]]" = OrderedDict()
    for o in outcomes:
        for line in o.lines():
            # The dataset varies by arrival in a CP delivery; the outcome is
            # what is shared, so the dataset is named where it is one arrival.
            key = line.replace(o.dataset_id, "{dataset}")
            groups.setdefault(key, []).append(o)
    for key, members in groups.items():
        if len(members) == 1 or len(outcomes) == 1:
            yield key.replace("{dataset}", members[0].dataset_id), members[0].run_id
        else:
            # EACH ARRIVAL'S DATASET STILL NAMED (criterion 1, #120 D8): the
            # line is shared, the datasets are listed beside the count - up
            # to a point, because thirty names on one line is not a summary.
            names = [m.dataset_id for m in members]
            shown = ", ".join(names[:_NAMED]) + (
                f" and {len(names) - _NAMED} more" if len(names) > _NAMED else "")
            yield (key.replace("{dataset}", "its dataset"),
                   f"{len(members)} arrivals ({shown})")


_NAMED = 8


def stage_failure(exc) -> None:
    """CRITERION 7: the arrival, the stage, what completed - and never the
    message that describes a completed kept run."""
    console.print(f"STOPPED - {exc.run_id}: the {exc.stage} stage failed "
                  f"({type(exc.cause).__name__}: {exc.cause}). "
                  + (f"Completed before it: {', '.join(exc.completed)}."
                     if exc.completed else "Nothing had completed."),
                  style="red", markup=False, highlight=False)


def trial_recognition(paths) -> None:
    """CRITERION 10: what recognition WOULD make of each file if it were kept
    - the dataset that claims it, or that none or several do. Never stops the
    trial."""
    import os

    from qa_tools.common import arrival_patterns

    for path in paths:
        found = arrival_patterns.attribute(os.path.basename(str(path)))
        if found.is_attributed:
            what = f"would be {found.dataset_ids[0]}"
        elif found.is_unrecognised:
            what = "would be claimed by no dataset - it could not be kept as it is named"
        else:
            what = f"would be claimed by several datasets ({', '.join(found.dataset_ids)})"
        console.print(f"  {os.path.basename(str(path))}: {what}", markup=False,
                      highlight=False)
