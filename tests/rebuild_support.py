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


def record_run(collection_id: str, run_id: str, run_index: int,
               by_tool: dict[str, list[dict]]) -> None:
    """Record one finished run: its dataset_stats (which is what puts a
    run into the rebuild's manifest) and each tool's verified records."""
    from qa_tools.common.qa_results_writer import finish_run, open_run, write_qa_result

    agency, collection = ids(collection_id)
    open_run(agency, collection, run_id, _WHEN, _BY)
    write_qa_result(agency, collection, run_id, _WHEN, "dataset_stats",
                    {"arrival_record": {"run_id": run_id, "run_index": run_index}},
                    run_by=_BY)
    for tool, verified in by_tool.items():
        write_qa_result(agency, collection, run_id, _WHEN, tool, {},
                        verified=[dict(r, run_id=run_id) for r in verified], run_by=_BY)
    finish_run(run_id)


def output_path(collection_id: str, tmp_path) -> pathlib.Path:
    """Where `rebuild(collection_id, tmp_path, ...)` writes the results file."""
    return pathlib.Path(tmp_path) / "reports" / collections.by_id(collection_id).results_file


def rebuild(collection_id: str, tmp_path, monkeypatch) -> dict:
    """Run the real rebuild, writing into tmp_path/reports/ rather than
    the repo's own reports/ (results_history.ROOT is the repo root)."""
    monkeypatch.setattr(results_history, "ROOT", str(tmp_path))
    return results_history.build_results_from_history(collection_id)
