"""Recording a small QA history and rebuilding results from it, for tests
that drive the real `build_results_from_history()` of either collection.

The rebuild is the path the dashboard is built from, so a rule about what
it publishes - every cross-table result, one agreed ordering - is proven by
running it over a history the test wrote, not by reading its source.

Both helpers expect `clean_qa_history` to have emptied this worker's
history first. The rebuild's output file is always redirected into
`tmp_path`: its default is the real `reports/results_*.json`.
"""
from __future__ import annotations

import pathlib

from qa_tools import collections
from qa_tools.tools import results_history

#: The one rebuild, run for each collection (REQ-PIPE-243): a test
#: parametrised over these drives `results_history.build_results_from_history`
#: with each collection id in turn.
REBUILDS = ("child-protection", "civil-registration")

_WHEN = "2026-09-26T10:00:00+08:00"
_BY = "tests@example.gov.au"


def ids(collection_id: str) -> tuple[str, str]:
    """(agency, collection) the rebuild of the given collection reads."""
    coll = collections.by_id(collection_id)
    return coll.agency_id, coll.id


def dataset_of(collection_id: str) -> str:
    """A real dataset of that collection, for check ids and records."""
    return "cp-placements" if collection_id == "child-protection" else "birth-registrations"


def check(collection_id: str, name: str, tool: str, dataset: str | None = None) -> dict:
    """One verified record, in the shape a tool's evaluation returns."""
    agency, collection = ids(collection_id)
    dataset = dataset or dataset_of(collection_id)
    return {"check_id": f"data-asset-1.{agency}.{collection}.{dataset}.col.{name}_{tool}",
            "dataset_id": dataset, "status": "pass", "engine": tool}


def record_reads(run_id: str, check_ids) -> None:
    """Record `run_id`'s resolution as having read, as a supply of its own,
    every table the given cross-table checks read - their own included - so a
    cross-table result can be recorded with what it read, as the overlay
    records it before any tool runs (REQ-PIPE-279 criteria 1 and 4)."""
    from qa_tools.common import carried, hierarchy, promotion, supply_db

    declared = promotion._declared_reads()
    tables = set()
    for check in check_ids:
        tables |= carried._reads_of(check, declared) or set()
    with supply_db.connect(label="test-rebuild-support") as conn:
        supply_db.ensure_schemas(conn)
        supply_db.record_resolution(conn, supply_db.Resolution(
            run_id=run_id, schema=supply_db.run_schema(run_id),
            resolved={t: f"{t}__1" for t in tables},
            supply_of={t: f"{hierarchy.dataset_for_table(t).dataset_id}@1" for t in tables},
            source={t: "staging" for t in tables}))


def record_run(collection_id: str, run_id: str, run_index: int,
               by_tool: dict[str, list[dict]]) -> None:
    """Record one finished run: its dataset_stats (which is what puts a
    run into the rebuild's manifest) and each tool's verified records -
    with what its cross-table ones read (record_reads)."""
    from qa_tools.common import promotion
    from qa_tools.common.qa_results_writer import (close_attempt, finish_run, open_run,
                                                   write_qa_result)

    agency, collection = ids(collection_id)
    declared = promotion._declared_reads()
    spanning = [r["check_id"] for v in by_tool.values() for r in v if r["check_id"] in declared]
    if spanning:
        record_reads(run_id, spanning)
    open_run(agency, collection, run_id, _WHEN, _BY)
    try:
        write_qa_result(agency, collection, run_id, _WHEN, "dataset_stats",
                        {"arrival_record": {"run_id": run_id, "run_index": run_index}},
                        run_by=_BY)
        for tool, verified in by_tool.items():
            write_qa_result(agency, collection, run_id, _WHEN, tool, {},
                            verified=[dict(r, run_id=run_id) for r in verified], run_by=_BY)
        finish_run(run_id)
    except BaseException as exc:
        # ITS ATTEMPT ENDS HOWEVER THE WRITE ENDED, as orchestrate.run_one's
        # finally ends a real one: left open, its lock refuses the next test
        # opening the same run key in this process (REQ-PIPE-279 criterion 7).
        close_attempt(run_id, exc)
        raise


def output_path(collection_id: str, tmp_path) -> pathlib.Path:
    """Where `rebuild(collection_id, tmp_path, ...)` writes the results file."""
    return pathlib.Path(tmp_path) / "reports" / collections.by_id(collection_id).results_file


def rebuild(collection_id: str, tmp_path, monkeypatch) -> dict:
    """Run the real rebuild, writing into tmp_path/reports/ rather than
    the repo's own reports/ (results_history.ROOT is the repo root)."""
    monkeypatch.setattr(results_history, "ROOT", str(tmp_path))
    return results_history.build_results_from_history(collection_id)
