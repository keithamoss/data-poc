"""What each tool left out of a run, and the check that it all agrees
with what the run recorded as not evaluated (REQ-PIPE-115 criterion 17).

THE PROBE FOUND THE TWO IN AGREEMENT ONLY BY COINCIDENCE. Every tool
leaves a check over an unreadable table OUT before it runs - dbt by
`--exclude stg_<table>+`, Soda by `readable_checks_yaml`,
datacontract-cli by skipping on the shared reads declaration, Evidently
by not evaluating - and the `unrunnable` and `held` pseudo-tools record
each such check as not evaluated, from the DECLARATION of what it
reads. dbt's exclusion follows its DAG, not the declaration, so a dbt
test downstream of an unreadable model with no declaration would be
left out by dbt and reddened by nobody: a check that silently does not
appear, which reads exactly like a pass.

So each tool says what it left out, and the run compares, per tool, the
left-out checks IN THE RUN'S SCOPE against the not-evaluated records.
A disagreement refuses the run and stops the batch (Keith, 2026-10-04,
option A): it is a configuration defect, not a data condition.

IN MEMORY, PER PROCESS. A run's four tools are evaluated in one process
(two threads, parallel_orchestrate.beside), so a locked dict keyed by
run id is all this needs - and nothing here survives the run except
what the orchestrator records beside tables_read (the auditable NFR).
"""
from __future__ import annotations

import threading
from collections.abc import Iterable

#: The pseudo-tool a run's compared left-out sets are recorded under.
TOOL = "left_out"

#: The tool names the check ids' own tool segment uses, by the name a
#: run step is recorded under.
TOOL_SEGMENT = {"dbt-core": "dbt", "Soda Core": "soda",
                "datacontract-cli": "datacontract", "Evidently": "evidently"}

_lock = threading.Lock()
_by_run: dict[str, dict[str, set[str]]] = {}


class LeftOutMismatch(RuntimeError):
    """A tool left a check out that nothing recorded, or the other way
    round."""


def note(run_id: str, tool: str, check_ids: Iterable[str]) -> None:
    """Record that `tool` left these checks out of `run_id`. `tool` is
    the check id's own tool segment ("dbt", "soda", ...)."""
    with _lock:
        _by_run.setdefault(run_id, {}).setdefault(tool, set()).update(
            c for c in check_ids if c)


def peek(run_id: str) -> dict[str, set[str]]:
    """What the tools have left out of this run so far, without taking it -
    for a trial's not-evaluated records, which have to exist before the
    reconciliation takes the set (delivery critic on 8a942e7, H2)."""
    with _lock:
        return {tool: set(ids) for tool, ids in _by_run.get(run_id, {}).items()}


def take(run_id: str) -> dict[str, set[str]]:
    """Everything noted for this run, forgetting it."""
    with _lock:
        return _by_run.pop(run_id, {})


def reconcile(run_id: str, left_out: dict[str, set[str]], not_evaluated: list[dict],
              in_scope) -> dict[str, list[str]]:
    """Compare, per tool, the in-scope checks left out against the
    not-evaluated records. Returns the in-scope left-out sets (for the
    record); raises LeftOutMismatch naming every disagreement.

    `in_scope(check_id) -> bool` is the run's scope, the same one the
    results writer applies: a tool leaves checks out across the whole
    collection, and those belonging to other runs are theirs to account
    for.
    """
    from qa_tools.common import check_id as check_id_mod

    recorded: dict[str, set[str]] = {}
    for r in not_evaluated:
        parsed = check_id_mod.try_parse(r.get("check_id") or "")
        if parsed is not None and in_scope(r["check_id"]):
            recorded.setdefault(parsed.tool, set()).add(r["check_id"])
    scoped = {tool: {c for c in ids if in_scope(c)} for tool, ids in left_out.items()}
    problems = []
    for tool in sorted(set(scoped) | set(recorded)):
        missing = sorted(scoped.get(tool, set()) - recorded.get(tool, set()))
        extra = sorted(recorded.get(tool, set()) - scoped.get(tool, set()))
        if missing:
            problems.append(f"{tool} left out but nothing recorded: {', '.join(missing)}")
        if extra:
            problems.append(f"{tool} recorded as not evaluated but not left out: "
                            f"{', '.join(extra)}")
    if problems:
        raise LeftOutMismatch(
            f"{run_id}: the checks the tools left out disagree with the not-evaluated "
            "records - " + "; ".join(problems) + ". A check left out and recorded by "
            "nobody reads as a pass, so the run is refused.")
    return {tool: sorted(ids) for tool, ids in scoped.items() if ids}
