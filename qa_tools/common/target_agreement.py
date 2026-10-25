"""Did the real tools agree with what a supply was built to (REQ-GEN-186)?

Two callers. The generator's TRIAL runs the four tools on one written file
and hands the results here (criteria 1-2); the bootstrap, once a replay has
finished, hands each targeted supply's RECORDED results here (criterion 3).
Either way the verdict is the promotion gate's own reading -
promotion.status_of(for_gate=True), so a gap red reads as its measurement
and an ordinary amber after an unresolved red is not blamed for a gap it
did not cause (Keith, 2026-10-11).

NOTHING HERE PREDICTS A VERDICT (criterion 4). It compares a verdict the
tools produced with a target, and names the checks responsible. And it
CHANGES NOTHING (criterion 6): the replay comparison only reads.

It knows nothing of the generator's bookkeeping, which no QA module may
read (REQ-GEN-043 criterion 7): the expectations arrive as plain values
from generator/targets.py, by way of cli/.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

#: How bad each gate verdict is, for "what does this target allow".
_RANK = {"green": 0, "amber": 1, "red": 2}


@dataclass(frozen=True)
class Disagreement:
    label: str
    dataset_id: str
    target: str
    verdict: str | None
    checks: tuple[str, ...]

    def __str__(self) -> str:
        said = self.verdict or "no verdict"
        why = (f" - {', '.join(self.checks)}" if self.checks else "")
        return (f"{self.label} ({self.dataset_id}) was built to {self.target} and the real "
                f"tools read {said}{why}")


def verdict_of(dataset_id: str, results: Sequence[dict], reads: dict | None = None) -> str | None:
    """The promotion gate's reading of one supply's results."""
    from qa_tools.common import promotion

    if reads is None:
        reads = promotion._declared_reads()
    return promotion.status_of(dataset_id, results, reads=reads, for_gate=True)


def responsible(dataset_id: str, results: Sequence[dict], target: str,
                rules: Iterable[str] = (), reads: dict | None = None) -> tuple[str, ...]:
    """The checks whose gate reading the target does not allow - worse than
    it, by name. Where the supply read BETTER than its target, nothing
    misbehaved, so the answer is the checks implementing the rules that were
    meant to warn, or fail, and did not."""
    from qa_tools.common import dataset_status, promotion

    if reads is None:
        reads = promotion._declared_reads()
    allowed = _RANK.get(target, 0)
    worse, quiet, named = [], [], []
    rules = tuple(rules)
    for record in promotion._contributing_records(dataset_id, results, reads):
        status = dataset_status.dashboard_status(promotion._gating_status(record))
        check = record.get("check_id") or ""
        if status not in _RANK:
            # A QUIET STATUS - no reference, nothing measured - is a verdict
            # of its own, never green (post-build-review #157 finding 6).
            quiet.append(f"{_short(check)} {status}")
        elif _RANK[status] > allowed:
            worse.append(f"{_short(check)} {status}")
        elif rules and any(f".{rule.split('.')[0]}." in check for rule in rules):
            named.append(f"{_short(check)} {status}")
    found = sorted(worse) or sorted(quiet) or sorted(named)
    if not found and _RANK.get(target, 0) > 0:
        # BETTER THAN BUILT, WITH NO RULE NAMED: an ordinary amber carries
        # none, so say what happened rather than nothing (finding 6).
        found = [f"no check {'warned' if target == 'amber' else 'failed'}"]
    return tuple(found)


def _short(check_id: str) -> str:
    """A check id without its asset, agency and collection - the part a
    reader recognises."""
    parts = check_id.split(".")
    return ".".join(parts[4:]) if len(parts) > 4 else check_id


def compare(dataset_id: str, results: Sequence[dict], target: str, label: str,
            rules: Iterable[str] = (), reads: dict | None = None) -> Disagreement | None:
    """None where the tools agreed with the target."""
    verdict = verdict_of(dataset_id, results, reads)
    if verdict == target:
        return None
    return Disagreement(label, dataset_id, target, verdict,
                        responsible(dataset_id, results, target, rules, reads) if results else ())


def recorded_results(conn, run_key: str) -> list[dict]:
    """One run's recorded results as the gate read them when it ran: the
    run's own and its cross-table ones, each record's extras merged back
    (a gap red's measured status lives there)."""
    from qa_tools.common import qa_results_reader, qa_store

    cursor = conn.execute(
        f'SELECT * FROM "{qa_store.SCHEMA}".check_result_visible '
        "WHERE run_key = ? AND scope IN (?, ?) AND supply_state = ? ORDER BY id",
        [run_key, qa_store.DATASET_SCOPE, qa_store.CROSS_TABLE_SCOPE, qa_store.AGREED])
    return qa_results_reader._records(cursor, run_key)


@dataclass(frozen=True)
class Reported:
    """A targeted supply whose FULL gate reading differs from its target only
    because of checks the comparison leaves out (REQ-GEN-273 criterion 2) -
    reported, never a failure."""
    label: str
    dataset_id: str
    target: str
    verdict: str | None
    #: The package-mate held back, or the table it could not read.
    because: str

    def __str__(self) -> str:
        return (f"{self.label} ({self.dataset_id}) was built to {self.target} and its own "
                f"checks agreed; the gate read {self.verdict or 'no verdict'} because of "
                f"{self.because}")


def own_results(results: Sequence[dict], reads: dict | None = None) -> list[dict]:
    """A supply's results as THE FILE'S OWN CHECKS read them (REQ-GEN-273
    criterion 1): leaving out the cross-table checks recorded not evaluated
    for want of a table (REQ-PIPE-270). The re-evaluations a gate
    application made because another supply was held back (REQ-PIPE-267
    criterion 6) are readers-only runs of their own, never the supply's
    current run, so they are not here to leave out."""
    from qa_tools.common import carried, promotion

    if reads is None:
        reads = promotion._declared_reads()
    return [r for r in results
            if not (carried.not_evaluated_reason(r)
                    and (r.get("check_id") in reads or r.get("unrunnable_table")
                         or r.get("held_table")))]


def _because(conn, dataset_id: str, supply: str, results: Sequence[dict]) -> str:
    """What made the full reading differ: the package-mate or waiting supply
    held back (the hold-back's structured cause), else the table it could
    not read."""
    from qa_tools.common import carried, decision_log

    rows = conn.execute(
        f"SELECT held_back_by FROM {decision_log.TABLE} WHERE dataset_id = ? AND supply = ? "
        "AND action = ? AND held_back_by IS NOT NULL ORDER BY id DESC LIMIT 1",
        [dataset_id, supply, decision_log.PROMOTION_WITHHELD]).fetchall()
    if rows:
        by = rows[0][0]
        return f"the {by.split('@', 1)[0]} supply {by}, held back"
    tables = sorted({t for r in results if carried.not_evaluated_reason(r)
                     for t in (r.get("unrunnable_tables") or r.get("held_tables") or
                               ([r["unrunnable_table"]] if r.get("unrunnable_table") else []))})
    return (f"no {', '.join(tables)} it could read" if tables
            else "checks it could not evaluate for want of another table")


def after_replay(conn, built: Sequence) -> list[Disagreement]:
    """Every targeted supply's own checks against its target (criterion 3,
    as REQ-GEN-273 criterion 1 amends it) - the failures. replay_report()
    has the reported differences too."""
    return replay_report(conn, built)[0]


def replay_report(conn, built: Sequence) -> tuple[list[Disagreement], list[Reported]]:
    """(disagreements that fail the bootstrap, differences reported without
    failing it) for every targeted supply (REQ-GEN-273 criteria 1 and 2).
    `built` is generator/targets.py's list - anything with label, dataset_id,
    delivery, target and rules, and a pair's file its filename."""
    from qa_tools.common import delivery_log, promotion, qa_store, supply_status

    reads = promotion._declared_reads()
    deliveries = sorted({b.delivery for b in built})
    supplies = delivery_log.supply_ids(deliveries, conn)
    # ONE FILE OF A PAIR is keyed by its filename too (REQ-GEN-196 criterion
    # 19): the pair's two supplies share a delivery.
    by_file = delivery_log.supply_ids_by_file(deliveries, conn)
    out: list[Disagreement] = []
    reported: list[Reported] = []
    for b in built:
        filename = getattr(b, "filename", None)
        supply = (by_file.get((b.delivery, b.dataset_id, filename)) if filename
                  else supplies.get((b.delivery, b.dataset_id)))
        run = qa_store.current_run(conn, b.dataset_id, supply) if supply else None
        if run is None:
            out.append(Disagreement(b.label, b.dataset_id, b.target, None,
                                    (f"nothing recorded for delivery {b.delivery}",)))
            continue
        recorded = recorded_results(conn, run)
        found = compare(b.dataset_id, own_results(recorded, reads), b.target, b.label,
                        b.rules, reads)
        if found:
            out.append(found)
            continue
        # THE FULL GATE READING (criterion 2): every result counted toward the
        # supply, re-evaluations and could-not-run reds included.
        full = supply_status.latest_results(conn, b.dataset_id, supply)
        verdict = verdict_of(b.dataset_id, full, reads)
        if verdict != b.target:
            reported.append(Reported(b.label, b.dataset_id, b.target, verdict,
                                     _because(conn, b.dataset_id, supply, full)))
    return out, reported


# ---------------------------------------------------------------------------
# Declared gate outcomes (REQ-GEN-273 criteria 3 and 4)
# ---------------------------------------------------------------------------

#: What a scripted scenario can declare the gate does with one supply.
PROMOTED, HELD_BACK = "promoted", "held back"


@dataclass(frozen=True)
class GateOutcomeDifference:
    scenario: str
    dataset_id: str
    supply: str | None
    declared: str
    recorded: str

    def __str__(self) -> str:
        return (f"{self.scenario}: {self.dataset_id} supply {self.supply or '(none recorded)'} "
                f"was declared {self.declared}, and the gate recorded {self.recorded}")


def gate_outcome_differences(conn, declared: Sequence) -> list[GateOutcomeDifference]:
    """Each DECLARED gate outcome against the recorded promotions and
    'promotion-withheld' entries (criterion 3) - a difference fails the
    bootstrap, naming the scenario and the supply. `declared` is anything
    with scenario, dataset_id, delivery, outcome ('promoted' or 'held
    back'), because (the dataset of the other supply that held it back, or
    None for its own data) and rechecked (whether held back after a re-check
    against the warehouse). Reads the decision log; changes nothing."""
    from qa_tools.common import decision_log, delivery_log, qa_store

    deliveries = sorted({d.delivery for d in declared})
    supplies = delivery_log.supply_ids(deliveries, conn) if deliveries else {}
    out: list[GateOutcomeDifference] = []
    for d in declared:
        supply = supplies.get((d.delivery, d.dataset_id))
        if supply is None:
            out.append(GateOutcomeDifference(d.scenario, d.dataset_id, None,
                                             _declared_words(d), "no supply"))
            continue
        rows = conn.execute(
            f"SELECT action, held_back_by FROM {decision_log.TABLE} WHERE dataset_id = ? "
            "AND supply = ? AND actor_kind = ? AND action IN (?, ?, ?) ORDER BY id",
            [d.dataset_id, supply, decision_log.RULE, decision_log.PROMOTE,
             decision_log.PROMOTION_WITHHELD, decision_log.PROMOTION_REFUSED]).fetchall()
        actions = [a for a, _b in rows]
        if d.outcome == PROMOTED:
            ok = decision_log.PROMOTE in actions
        else:
            ok = bool(actions) and decision_log.PROMOTE not in actions
            if ok and d.because:
                ok = any(a == decision_log.PROMOTION_WITHHELD and b
                         and b.split("@", 1)[0] == d.because for a, b in rows)
            if ok and d.rechecked:
                ok = bool(conn.execute(
                    f'SELECT 1 FROM "{qa_store.SCHEMA}".run_visible WHERE dataset_id = ? '
                    "AND supply_id = ? AND scope = 'readers' AND gate_application IS NOT NULL "
                    "LIMIT 1", [d.dataset_id, supply]).fetchall())
        if not ok:
            out.append(GateOutcomeDifference(d.scenario, d.dataset_id, supply,
                                             _declared_words(d), _recorded_words(rows)))
    return out


def _declared_words(d) -> str:
    if d.outcome == PROMOTED:
        return PROMOTED
    words = HELD_BACK
    if d.because:
        words += f" because of {d.because}"
    if d.rechecked:
        words += ", after a re-check against the warehouse"
    return words


def _recorded_words(rows) -> str:
    if not rows:
        return "no gate outcome"
    return ", then ".join(a + (f" (by {b})" if b else "") for a, b in rows)
