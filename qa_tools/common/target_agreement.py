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


def after_replay(conn, built: Sequence) -> list[Disagreement]:
    """Every targeted supply's recorded verdict against its target
    (criterion 3). `built` is generator/targets.py's list - anything with
    label, dataset_id, delivery, target and rules."""
    from qa_tools.common import delivery_log, promotion, qa_store

    reads = promotion._declared_reads()
    supplies = delivery_log.supply_ids(sorted({b.delivery for b in built}), conn)
    out: list[Disagreement] = []
    for b in built:
        supply = supplies.get((b.delivery, b.dataset_id))
        run = qa_store.current_run(conn, b.dataset_id, supply) if supply else None
        if run is None:
            out.append(Disagreement(b.label, b.dataset_id, b.target, None,
                                    (f"nothing recorded for delivery {b.delivery}",)))
            continue
        found = compare(b.dataset_id, recorded_results(conn, run), b.target, b.label,
                        b.rules, reads)
        if found:
            out.append(found)
    return out
