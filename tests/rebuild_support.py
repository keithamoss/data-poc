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

import importlib

#: The two rebuild paths, one per collection.
REBUILDS = ("qa_tools.cp.build_results_from_history",
            "qa_tools.bdm.build_results_from_history")

_WHEN = "2026-09-26T10:00:00+08:00"
_BY = "tests@example.gov.au"


def ids(module_name: str) -> tuple[str, str]:
    """(agency, collection) the given rebuild reads."""
    if ".cp." in module_name:
        from qa_tools.cp import cp_common as common
    else:
        from qa_tools.bdm import bdm_common as common
    return common.AGENCY_ID, common.COLLECTION_ID


def dataset_of(module_name: str) -> str:
    """A real dataset of that collection, for check ids and records."""
    return "cp-placements" if ".cp." in module_name else "birth-registrations"


def check(module_name: str, name: str, tool: str, dataset: str | None = None) -> dict:
    """One verified record, in the shape a tool's evaluation returns."""
    agency, collection = ids(module_name)
    dataset = dataset or dataset_of(module_name)
    return {"check_id": f"data-asset-1.{agency}.{collection}.{dataset}.col.{name}_{tool}",
            "dataset_id": dataset, "status": "pass", "engine": tool}


def record_run(module_name: str, run_id: str, run_index: int,
               by_tool: dict[str, list[dict]]) -> None:
    """Record one finished run: its dataset_stats (which is what puts a
    run into the rebuild's manifest) and each tool's verified records."""
    from qa_tools.common.qa_results_writer import finish_run, open_run, write_qa_result

    agency, collection = ids(module_name)
    open_run(agency, collection, run_id, _WHEN, _BY)
    write_qa_result(agency, collection, run_id, _WHEN, "dataset_stats",
                    {"arrival_record": {"run_id": run_id, "run_index": run_index}},
                    run_by=_BY)
    for tool, verified in by_tool.items():
        write_qa_result(agency, collection, run_id, _WHEN, tool, {},
                        verified=[dict(r, run_id=run_id) for r in verified], run_by=_BY)
    finish_run(run_id)


def rebuild(module_name: str, tmp_path, monkeypatch) -> dict:
    """Run the real rebuild, writing into tmp_path rather than reports/."""
    module = importlib.import_module(module_name)
    monkeypatch.setattr(module, "RESULTS_PATH", str(tmp_path / "results.json"))
    return module.build_results_from_history()
