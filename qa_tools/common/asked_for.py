"""What each QA tool is asked to evaluate on a run, the record of it, and
the refusal when a check in the run's scope goes missing (REQ-PIPE-188).

A run records only its own dataset's checks plus the cross-table checks
that read its table (qa_results_writer._scope_to_run). Every tool used to
be asked for the whole collection all the same, so a Child Protection run
evaluated five sibling tables' checks only for the writer to throw them
away - about four-fifths of each run's tool time.

ONE RULE. Which checks a scoped tool is asked for is `scope_of_run`, the
predicate the writer's own filter and the left-out reconciliation already
share (criterion 1). Nothing here knows which checks a table needs; it
filters the collection's declared checks by that predicate.

A TOOL IS SCOPED WHEN ITS RUNNER USES THE SUBSET, and only then - which is
what `SCOPED` says. Until a runner selects by it, what that tool is asked
for, and so what is recorded, is the whole collection, because that is
the truth. Evidently is never scoped (about 0.2s a run), and its asked-for
set is recorded all the same (criterion 8).

THE WRITER'S FILTER STAYS (criterion 7): a tool asked for more than the
scope does extra work and records the same thing.

A MISSING CHECK REFUSES THE RUN (criterion 6, Keith 2026-10-12). Asking
for a computed subset is a new way to lose a check - dbt simply produces
no result for a test it was not selected for - and a check that silently
does not appear reads as a pass. So once the tools have finished, every
in-scope check must have a verdict or a not-evaluated record; otherwise
the run is refused and the batch stops, as the left-out reconciliation
does for a disagreement.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable

#: The tools a run invokes, by the tool segment of their check ids. File
#: checks are evaluated at receipt, not by a run.
TOOLS = ("dbt", "soda", "datacontract", "evidently")

#: The tools whose runner asks for the run's scope rather than the whole
#: collection: dbt since REQ-PIPE-189; datacontract-cli (190) and Soda
#: (191) join as they are built. Evidently stays out by decision.
SCOPED: frozenset[str] = frozenset({"dbt", "datacontract", "soda"})


class MissingCheck(RuntimeError):
    """A check in the run's scope came back with neither a verdict nor a
    not-evaluated record."""


def collection_checks(collection_id: str, tool: str) -> list[str]:
    """Every active check of `tool` in `collection_id`, sorted."""
    from qa_tools.common import tables_read

    return tables_read.active_checks(collection_id, tool)


def for_run(run_id: str, collection_id: str, tool: str,
            in_scope: Callable[[str], bool] | None = None) -> list[str]:
    """The check ids `tool` is asked to evaluate on `run_id`: the run's
    scope for a scoped tool, the whole collection otherwise. A run id that
    names no table - a trial, a fixture's run - has the whole collection as
    its scope (criterion 4)."""
    everything = collection_checks(collection_id, tool)
    if tool not in SCOPED:
        return everything
    if in_scope is None:
        from qa_tools.common import qa_results_writer

        in_scope = qa_results_writer.scope_of_run(run_id)
    return [c for c in everything if in_scope(c)]


def ask(run_id: str, run_timestamp: str, agency_id: str, collection_id: str,
        tool: str) -> list[str]:
    """What a tool runner calls before it invokes its tool: the check ids
    to ask for, recorded against the run as they are returned - so the
    list the tool was handed and the list on record are one list."""
    asked = for_run(run_id, collection_id, tool)
    record(run_id, run_timestamp, agency_id, collection_id, tool, asked)
    return asked


def record(run_id: str, run_timestamp: str, agency_id: str, collection_id: str,
           tool: str, check_ids: Iterable[str]) -> None:
    """Record what `tool` was asked for on `run_id` (criteria 8 and 9),
    registering the run defensively as every other tool write does - with
    the run's own timestamp, which registering overwrites."""
    from qa_tools.common import environments, qa_store, supply_db

    environment = environments.current_or_none()
    with supply_db.connect(label="mothman:asked-for") as conn:
        qa_store.ensure_schema(conn)
        qa_store.record_run(conn, run_key=run_id, agency_id=agency_id,
                            collection_id=collection_id, run_timestamp=run_timestamp,
                            run_by=None,
                            environment=environment.id if environment else None)
        qa_store.record_asked(conn, run_id, tool, check_ids)


def check_nothing_missing(run_id: str, collection_id: str, records: Iterable[dict],
                          in_scope: Callable[[str], bool],
                          tools: Iterable[str] = TOOLS) -> None:
    """Raise MissingCheck where an in-scope check of any of `tools` has no
    record at all - neither a verdict nor a not-evaluated record, both of
    which carry the real tool's check id."""
    seen = {r.get("check_id") for r in records}
    problems = []
    for tool in tools:
        lost = [c for c in collection_checks(collection_id, tool)
                if in_scope(c) and c not in seen]
        if lost:
            problems.append(f"{tool}: {', '.join(lost)}")
    if problems:
        raise MissingCheck(
            f"{run_id}: checks in this run's scope came back with neither a verdict "
            "nor a not-evaluated record - " + "; ".join(problems) + ". A check that "
            "silently does not appear reads as a pass, so the run is refused. This is "
            "a defect in what the tool was asked for or how it was selected, not a "
            "data condition.")
