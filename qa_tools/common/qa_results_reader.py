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
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
QA_RESULTS_DIR = ROOT / "qa_results"

_DIGIT_RUN = re.compile(r"(\d+)")


def _natural_sort_key(name: str) -> tuple:
    """Sorts run_id-shaped strings ("run_5_2026-01-01", "cp_run_005_...",
    "run_120_2026-09-18_resupply2") in real numeric/chronological order
    regardless of how many digits any of their numbers happen to have -
    a plain string sort of these (what both this module's own callers
    used to do) silently breaks the moment a run number crosses a fixed
    zero-padding width (2026-09-17: generator/generate_runs.py's
    delivery/run numbering went 60->120 deliveries and immediately hit
    exactly this - "delivery_100" < "delivery_11" as plain strings - a
    real bug a test caught; see that module's own comment). Keith's own
    call once that surfaced: this dataset's real run count will keep
    growing into the thousands over the life of the project, so a wider
    FIXED width (":03d" instead of ":02d") is not a real fix, just a
    bigger version of the same bug waiting to reoccur - this splits the
    string into alternating text/number runs and compares numbers as
    ints instead, so it's correct at any width, forever, with no digit
    count to eventually outgrow."""
    return tuple(int(part) if part.isdigit() else part for part in _DIGIT_RUN.split(name))

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


def list_run_ids(agency: str, dataset: str, qa_results_dir: Path | str = QA_RESULTS_DIR) -> list[str]:
    """Every run_id committed under this agency/dataset, sorted - the
    committed tree's own directory listing is the source of truth for
    "which runs exist" (Phase 3, plans/publishing-and-history.md),
    replacing a dependency on local, regenerated manifest.json files."""
    dataset_dir = Path(qa_results_dir) / agency / dataset
    if not dataset_dir.is_dir():
        return []
    return sorted((p.name for p in dataset_dir.iterdir() if p.is_dir()), key=_natural_sort_key)


def read_dataset_stats(agency: str, dataset: str, run_id: str,
                        qa_results_dir: Path | str = QA_RESULTS_DIR) -> dict | None:
    """The precomputed value-counts/arrival/check-aggregate/manifest-entry
    data for one run (qa_tools/<bdm|cp>/dataset_stats.py's output),
    committed under the pseudo-tool name "dataset_stats" - not a real
    QA tool, just reusing qa_results_writer.write_qa_result()'s same
    file shape/writer for consistency. Returns None if this run has no
    committed dataset_stats.json (shouldn't happen for any run written
    since Phase 3 - see plans/publishing-and-history.md)."""
    path = Path(qa_results_dir) / agency / dataset / run_id / "dataset_stats.json"
    if not path.exists():
        return None
    with open(path) as f:
        committed = json.load(f)
    return committed.get("raw_output")


def read_run_provenance(agency: str, dataset: str, run_id: str,
                         qa_results_dir: Path | str = QA_RESULTS_DIR) -> dict | None:
    """The `run_timestamp`/`run_by` envelope fields for one run - unlike
    read_dataset_stats() above (which returns only the `raw_output`
    payload, the shape every existing caller already expects), this
    reads the two provenance fields write_qa_result() stamps ALONGSIDE
    raw_output, not inside it. Added for qa_tools/common/changelog.py
    (plans/publishing-and-history.md Phase 3's changelog feature,
    2026-09-16) - a separate function rather than reshaping
    read_dataset_stats() itself, since that would break every existing
    caller's assumption that its return value IS the raw_output dict.
    Reads dataset_stats.json specifically since it's the one file
    guaranteed to exist for every run (orchestrate_bdm.py's/
    orchestrate_cp.py's own dataset_stats write is where run_by gets
    stamped - see write_qa_result()'s own docstring). Returns None if
    this run has no committed dataset_stats.json."""
    path = Path(qa_results_dir) / agency / dataset / run_id / "dataset_stats.json"
    if not path.exists():
        return None
    with open(path) as f:
        committed = json.load(f)
    return {"run_timestamp": committed.get("run_timestamp"), "run_by": committed.get("run_by")}


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
    for run_dir in sorted((p for p in dataset_dir.iterdir() if p.is_dir()), key=lambda p: _natural_sort_key(p.name)):
        for tool in TOOL_ORDER:
            all_results.extend(read_one(agency, dataset, run_dir.name, tool, qa_results_dir))
    return all_results
