"""
Writes each real QA tool's NATIVE raw output (dbt's run_results.json, a
Soda scan_results dict, a datacontract-cli Run, an Evidently Report
snapshot) to `qa_results/<agency>/<dataset>/<run_id>/<tool>.json` -
committed to git, not gitignored. This is Phase 1 of plans/publishing-
and-history.md's Thread B: the real source of truth for QA history,
independent of whatever the dashboard currently renders from
`reports/*.json` (which stays exactly as it is today - gitignored,
regenerated, a reshaped VIEW of this raw data, not the source of it).

Deliberately native format, not reshaped into a common schema - each
tool's own real output, unmodified, so the dashboard pipeline (Phase 2)
does all reshaping when reading history back, and so a real audit years
from now sees exactly what the tool itself produced, not this project's
own interpretation of it.

Path layout: `qa_results/<agency>/<dataset>/<run_id>/<tool>.json` - one
directory per run, one file per tool, `run_id` (not `run_timestamp`)
as the directory name since it's already this project's own stable,
human-readable identifier for a specific run (e.g. `run_07`,
`cp_run_03`) and is unique per dataset - `run_timestamp` is captured
inside each written file instead, for the actual wall-clock provenance.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
QA_RESULTS_DIR = ROOT / "qa_results"


def write_qa_result(agency: str, dataset: str, run_id: str, run_timestamp: str,
                     tool: str, raw_output: Any, results_dir: Path = QA_RESULTS_DIR) -> Path:
    """Writes one tool's native raw output for one run to a committed
    JSON file. `raw_output` must already be JSON-serializable (a plain
    dict/list) - each run_*.py caller is responsible for converting its
    own tool's native result object first (e.g. a Pydantic model's
    `.model_dump()`, an Evidently snapshot's `.dict()`) since that
    conversion is tool-specific, not something this generic writer
    should need to know about.

    Wraps the raw output with `run_timestamp` alongside it (not inside
    it - never mutates what the tool actually produced) so the file
    carries real provenance without touching the tool's own payload.
    Returns the path written."""
    run_dir = results_dir / agency / dataset / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    out_path = run_dir / f"{tool}.json"
    payload = {"run_timestamp": run_timestamp, "raw_output": raw_output}
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    return out_path
