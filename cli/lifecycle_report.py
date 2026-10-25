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
    #: The arrival's supply, and - where it is held back by another supply,
    #: wholly that supply's doing - the ROOT it traces to (root_cause.trace,
    #: REQ-PIPE-276 criterion 6), how it came ('package-mate' or 'joined')
    #: and the datasets it traces through on the way.
    supply: str | None = None
    root: str | None = None
    came: str | None = None
    through: tuple[str, ...] = ()

    def lines(self) -> list[str]:
        return [self.filed, self.gate, *self.extra]


def _supply_of(arrival, dataset_id) -> str:
    """The arrival's own supply - filing's one rule, never a copy of it."""
    from qa_tools.common import filing

    return filing._supply_id_for(arrival, dataset_id)


def outcome_of(conn, arrival) -> Outcome:
    """Criterion 9's single source: the recorded rows for one arrival."""
    from qa_tools.common import decision_log, filing, supply_holds

    (dataset_id, names), = arrival.files_by_dataset.items()
    supply = _supply_of(arrival, dataset_id)
    # THE ARRIVAL'S OWN SUPPLY'S FILING (REQ-PIPE-193 criterion 13): a
    # settled pair's `#2` is a supply of its own, filed on its own receipt.
    rows = conn.execute(
        f"SELECT slot, classification, considered FROM {filing.CURRENT} "
        "WHERE dataset_id = ? AND supply_id = ? ORDER BY id DESC LIMIT 1",
        [dataset_id, supply]).fetchall()
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
    root = came = None
    through: tuple[str, ...] = ()
    if rows and rows[0][0] and gate.startswith("held back by the rule"):
        from qa_tools.common import root_cause

        traced = root_cause.trace(conn, dataset_id, supply, rows[0][0])
        if traced is not None and traced.root.kind == "supply" \
                and traced.root.supply != supply:
            root, came = traced.root.supply, traced.came
            through = tuple(ds for ds, _s in traced.via)
    # CRITERION 6: the inheritances THIS arrival caused - by its filing since
    # REQ-PIPE-271, which opens the period (by its promotion before) - as the
    # rule's - read by the link each entry records (Keith, 2026-10-06, over
    # a recorded_at window, which would claim whatever a concurrent pass
    # inherited too). They are other datasets', into the period it opened.
    for inherited, slot, stands_on in conn.execute(
            f"SELECT dataset_id, to_slot, stands_on FROM {decision_log.TABLE} "
            "WHERE action = ? AND caused_by_supply = ? ORDER BY id",
            [decision_log.INHERIT, supply]).fetchall():
        extra.append(f"the rule inherited {inherited}'s {stands_on} supply into {slot}, "
                     f"which this arrival opened")
    return Outcome(arrival.run_id, dataset_id, filed, gate, tuple(extra), supply=supply,
                   root=root, came=came, through=through)


def _gate_line(conn, dataset_id: str, supply: str) -> str:
    """CRITERION 5: what the gate did, with the reason it recorded - and that
    the rule decided it, not the person running the command."""
    from qa_tools.common import decision_log

    rows = conn.execute(
        f"SELECT action, reason, actor, gate_application FROM {decision_log.TABLE} "
        "WHERE dataset_id = ? "
        "AND supply = ? AND actor_kind = ? AND action IN (?, ?, ?) ORDER BY id DESC LIMIT 1",
        [dataset_id, supply, decision_log.RULE, decision_log.PROMOTE,
         decision_log.PROMOTION_WITHHELD, decision_log.PROMOTION_REFUSED]).fetchall()
    if not rows:
        # WAITING FOR ITS PACKAGE IS NOT OWED TO THE NEXT PASS (REQ-PIPE-266
        # criterion 5): it is gated by the rest of its delivery's last check.
        from qa_tools.common import gate

        package = gate.package_of(conn, dataset_id, supply)
        if package is not None and not package.complete and len(package.supplies) > 1:
            return gate.waiting_words(package)
        return "no gate outcome is recorded yet - it is owed to the next processing pass"
    action, reason, actor = rows[0][:3]
    application = rows[0][3] if len(rows[0]) > 3 else None
    # ONE WORD FOR ONE ACTION (REQ-PIPE-276 criterion 1): every
    # 'promotion-withheld' is 'held back', as decision_words says it -
    # never 'withheld', 'held', 'refused' or 'rejected'.
    said = {decision_log.PROMOTE: "promoted",
            decision_log.PROMOTION_WITHHELD: "held back",
            decision_log.PROMOTION_REFUSED: "left for a person"}[action]
    if action == decision_log.PROMOTE and application is not None:
        # A RULE-MADE PROMOTION AFTER A RE-CHECK AGAINST THE WAREHOUSE SAYS WHY
        # (criterion 15).
        why = rechecked_promotion_words(conn, dataset_id, supply)
        if why:
            return f"promoted by the rule ({actor}), not by you - {why}"
    return f"{said} by the rule ({actor}), not by you - {(reason or '').strip()}"


def rechecked_promotion_words(conn, dataset_id: str, supply: str) -> str | None:
    """REQ-PIPE-276 criterion 14: where the rule promoted this supply after
    re-checking it against the warehouse inside its gate application -
    'Client reference re-checked against the cp-notifications in place in the
    warehouse (received <instant>), green, because the cp-notifications
    received with it was held back' (for a joined supply, 'because the
    cp-notifications waiting for a decision (received <instant>) is held
    back'). From the promotion's application, the readers-only run it made
    and that run's recorded reads; None where it made none."""
    from qa_tools.common import decision_log, display_time, filing, gate, qa_store
    from qa_tools.common import qa_results_reader as reader

    rows = conn.execute(
        f"SELECT gate_application FROM {decision_log.TABLE} WHERE dataset_id = ? "
        "AND supply = ? AND action = ? AND actor_kind = ? ORDER BY id DESC LIMIT 1",
        [dataset_id, supply, decision_log.PROMOTE, decision_log.RULE]).fetchall()
    if not rows or rows[0][0] is None:
        return None
    runs = conn.execute(
        f'SELECT run_key, caused_by_decision FROM "{qa_store.SCHEMA}".run WHERE dataset_id = ? '
        "AND supply_id = ? AND scope = 'readers' AND gate_application = ? "
        "AND completed_at IS NOT NULL ORDER BY run_seq DESC NULLS LAST LIMIT 1",
        [dataset_id, supply, rows[0][0]]).fetchall()
    if not runs:
        return None
    run_key, cause_id = runs[0]
    cause = conn.execute(
        f"SELECT dataset_id, supply, package_instant FROM {decision_log.TABLE} WHERE id = ?",
        [cause_id]).fetchall() if cause_id else []
    if not cause:
        return None
    by_ds, by_supply, _instant = cause[0]
    cursor = conn.execute(
        f'SELECT c.*, c.id AS result_row FROM "{qa_store.SCHEMA}".check_result c '
        "WHERE c.run_key = ? ORDER BY c.id", [run_key])
    records = reader.records_from(cursor.description, cursor.fetchall())
    against = None
    checks = []
    for r in records:
        reads = conn.execute(
            f'SELECT logical_table, state, supply_id FROM "{qa_store.SCHEMA}".check_read '
            "WHERE check_result_id = ?", [r["result_row"]]).fetchall()
        mine = {t: (st, sup) for t, st, sup in reads}
        other = [(t, sup) for t, (st, sup) in mine.items()
                 if st == qa_store.READ and sup and not sup.startswith(dataset_id + "@")]
        if not other:
            continue
        checks.append(gate._check_words(r["check_id"]))
        against = against or other[0][1]
    if not checks or against is None:
        return None
    against_ds = against.split("@", 1)[0]
    got = filing.received_at_of(against_ds, against, conn=conn)
    on = display_time.format_instant(got) if got else against
    names = ", ".join(dict.fromkeys(checks))
    mine_at = filing.received_at_of(dataset_id, supply, conn=conn)
    theirs_at = filing.received_at_of(by_ds, by_supply, conn=conn)
    if mine_at and theirs_at and gate._same_instant(mine_at, theirs_at):
        because = f"because the {by_ds} received with it was held back"
    else:
        when = display_time.format_instant(theirs_at) if theirs_at else by_supply
        because = f"because the {by_ds} waiting for a decision (received {when}) is held back"
    return (f"{names} re-checked against the {against_ds} in place in the warehouse "
            f"(received {on}), green, {because}")


def report(found, *, say=None) -> list[Outcome]:
    """Criteria 1 to 8 for the arrivals one kept supply became."""
    from qa_tools.common import supply_db

    say = say or (lambda line: console.print(line, markup=False, highlight=False))
    with supply_db.connect(read_only=True, label="mothman:kept-report") as conn:
        outcomes = [outcome_of(conn, a) for a in found]
    say("What the lifecycle decided:")
    for line, who in _grouped(outcomes):
        say(f"  {who}: {line}" if who else f"  {line}")
    return outcomes


#: How a supply held back by another is labelled beneath its root
#: (REQ-PIPE-276 criterion 6), mirroring REQ-DASH-275's 'Holding back with it'.
WITH_IT, BY_IT = "held back with it (same delivery)", "held back by it"


def label_for(came: str | None) -> str:
    return BY_IT if came == "joined" else WITH_IT


def header_more(n: int, came: str | None) -> str:
    """'(1 more held back with it, listed beneath)' (criterion 6)."""
    how = "by it" if came == "joined" else "with it"
    return f"({n} more held back {how}, listed beneath)"


def named(names: list[str]) -> str:
    """Up to _NAMED names, then 'and <n> more' (criterion 6; NFR SCALE)."""
    names = list(dict.fromkeys(names))
    shown = ", ".join(names[:_NAMED])
    return shown + (f" and {len(names) - _NAMED} more" if len(names) > _NAMED else "")


def beneath_lines(root_line: str, members, *, root_name: str) -> list[str]:
    """THE ONE RENDERER of a hold-back's grouping (REQ-PIPE-276 criterion 6),
    shared by the kept report, the Filing decisions queue, `mothman supply
    queue` and a settlement's outcome panel (REQ-PIPE-211 criterion 14): the
    root's own line first, then under each label ONE line per resulting
    outcome naming its datasets up to eight and then 'and <n> more', each
    naming the root and what it traces through. `members` are (label,
    dataset id, outcome words, [datasets traced through]). Final states
    only - a cascade's intermediate states are never members. Plain text,
    no Rich markup."""
    lines = [root_line] if root_line else []
    by_label: "OrderedDict[str, OrderedDict[tuple, list[str]]]" = OrderedDict()
    for label, dataset_id, outcome, through in members:
        key = (outcome, tuple(through or ()))
        by_label.setdefault(label, OrderedDict()).setdefault(key, []).append(dataset_id)
    for label, outcomes in by_label.items():
        lines.append(f"  {label}:")
        for (outcome, through), names in outcomes.items():
            via = f" (through {named(list(through))})" if through else ""
            lines.append(f"  - {named(names)}{via}  {outcome}")
    return lines


def outcome_lines(outcomes, *, more: str | None = None) -> list[str]:
    """One line per resulting outcome - (dataset id, status in words, the
    gate's result) - naming up to eight datasets and then 'and <n> more',
    red lines first (REQ-PIPE-276 criterion 10; REQ-PIPE-211 criterion 14).
    A truncated red line ends with `more`, where to see them all."""
    groups: "OrderedDict[tuple[str, str], list[str]]" = OrderedDict()
    for dataset_id, status, result in outcomes:
        groups.setdefault((status, result), []).append(dataset_id)
    order = sorted(groups.items(), key=lambda kv: (not kv[0][0].startswith("red"),))
    lines = []
    for (status, result), names in order:
        line = f"- {named(names)}: {status}, {result}"
        if more and status.startswith("red") and len(set(names)) > _NAMED:
            line += f" - {more}"
        lines.append(line)
    return lines


def _grouped(outcomes: list[Outcome]):
    """One line per distinct outcome line; how many arrivals share it, or
    which arrival it is when only one does (criterion 8).

    GROUPED BY ROOT (REQ-PIPE-276 criterion 6): an arrival held back wholly
    by another arrival of this report is not given lines of its own; it is
    listed beneath its root, after every other line, through beneath_lines -
    its final state only."""
    by_supply = {o.supply: o for o in outcomes if o.supply}
    held = [o for o in outcomes if o.root and o.root in by_supply]
    plain = [o for o in outcomes if o not in held]
    yield from _grouped_plain(plain, total=len(outcomes))
    roots: "OrderedDict[str, list[Outcome]]" = OrderedDict()
    for o in held:
        roots.setdefault(o.root, []).append(o)
    for root_supply, members in roots.items():
        root = by_supply[root_supply]
        came = "joined" if any(m.came == "joined" for m in members) else "package-mate"
        for line in beneath_lines(
                f"{root.dataset_id} {header_more(len(members), came)}",
                [(label_for(m.came), m.dataset_id,
                  f"{m.gate}; deciding {root.dataset_id} settles it", m.through)
                 for m in members],
                root_name=root.dataset_id):
            yield line, None


def _grouped_plain(outcomes: list[Outcome], *, total: int):
    groups: "OrderedDict[str, list[str]]" = OrderedDict()
    for o in outcomes:
        for line in o.lines():
            # The dataset varies by arrival in a CP delivery; the outcome is
            # what is shared, so the dataset is named where it is one arrival.
            key = line.replace(o.dataset_id, "{dataset}")
            groups.setdefault(key, []).append(o)
    for key, members in groups.items():
        if len(members) == 1 or total == 1:
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
    message that describes a completed kept run. Then, where its package has
    files already checked, what they wait for (REQ-PIPE-276 criterion 17)."""
    console.print(f"STOPPED - {exc.run_id}: the {exc.stage} stage failed "
                  f"({type(exc.cause).__name__}: {exc.cause}). "
                  + (f"Completed before it: {', '.join(exc.completed)}."
                     if exc.completed else "Nothing had completed."),
                  style="red", markup=False, highlight=False)
    from qa_tools.common import gate

    for line in gate.crashed_sibling_lines(exc):
        console.print(line, soft_wrap=line.startswith("mothman "), markup=False,
                      highlight=False)


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
