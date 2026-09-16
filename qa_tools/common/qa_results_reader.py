"""
Reads Phase 1's committed `qa_results/` tree back - the read side of
plans/publishing-and-history.md Thread B/Phase 2. Lets the dashboard
pipeline rebuild `reports/*.json` purely from committed history, with
no real tool re-run and no live per-run DuckDB/CSV access needed.

Deliberately dumb: each committed file's own `verified` field (written
by every `qa_tools/*/run_*.py` module via `qa_results_writer.py` - see
that module's own docstring for why `verified` exists, not `raw_output`
alone) already holds the fully-resolved, dashboard-ready check-result
records for that tool+run, built once at run time when a live DB
connection to that run's own per-run warehouse naturally exists. This
module's only job is finding and concatenating those already-resolved
records back into one flat list - not reshaping anything itself.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
QA_RESULTS_DIR = ROOT / "qa_results"

# Matches orchestrate_bdm.py's/orchestrate_cp.py's own _run_one()
# construction order - keeps a history-rebuilt results list in the same
# run-then-tool order a live orchestrator run always produced, so a diff
# against a live run's own reports/*.json output is a real equivalence
# check, not noise from an incidental reordering.
TOOL_ORDER = ["dbt", "soda", "datacontract", "evidently"]


def read_one(agency: str, dataset: str, run_id: str, tool: str,
             qa_results_dir: Path | str = QA_RESULTS_DIR) -> list[dict]:
    """The `verified` list from one committed `<tool>.json` file, or
    `[]` if that run/tool combination has no committed file at all
    (e.g. a dataset segment a given tool never writes to - see
    read_qa_results()'s own docstring for the Child Protection Evidently
    case)."""
    path = Path(qa_results_dir) / agency / dataset / run_id / f"{tool}.json"
    if not path.exists():
        return []
    with open(path) as f:
        committed = json.load(f)
    return committed.get("verified") or []


def read_qa_results(agency: str, dataset: str, qa_results_dir: Path | str = QA_RESULTS_DIR) -> list[dict]:
    """Every committed run's every tool's `verified` records for one
    `agency`/`dataset` pair, concatenated in run-id then tool order.
    Only covers the tools that actually write under this exact dataset
    segment - Child Protection's Evidently check writes under its own
    table-scoped dataset id instead of the collection id the other 3
    tools use (see qa_results_writer.py callers' own AGENCY_ID/
    DATASET_ID/COLLECTION_ID constants), so a caller building CP's full
    result set calls this once per dataset segment and concatenates -
    same pattern qa_tools/cp/build_results_from_history.py uses."""
    dataset_dir = Path(qa_results_dir) / agency / dataset
    if not dataset_dir.is_dir():
        return []
    all_results: list[dict] = []
    for run_dir in sorted(p for p in dataset_dir.iterdir() if p.is_dir()):
        for tool in TOOL_ORDER:
            all_results.extend(read_one(agency, dataset, run_dir.name, tool, qa_results_dir))
    return all_results
