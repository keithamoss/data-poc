"""
Writes each real QA tool's NATIVE raw output (dbt's run_results.json, a
Soda scan_results dict, a datacontract-cli Run, an Evidently Report
snapshot) to `qa_results/<agency>/<dataset>/<run_id>/<tool>.json` -
committed to git, not gitignored. This is Phase 1 of plans/publishing-
and-history.md's Thread B: the real source of truth for QA history,
independent of whatever the dashboard currently renders from
`reports/*.json` (which stays exactly as it is today - gitignored,
regenerated, a reshaped VIEW of this raw data, not the source of it).

Deliberately native format, not reshaped into a common schema -
`raw_output` is each tool's own real output, genuinely unmodified, so a
real audit years from now sees exactly what the tool itself produced,
not this project's own interpretation of it.

A second top-level field, `verified`, sits alongside it (never inside
it - `raw_output` stays pristine either way): the same fully-resolved,
dashboard-ready check-result records `evaluate_*()` already builds in
memory every run, captured here too. Added 2026-09-16
(plans/publishing-and-history.md Phase 2, Keith's explicit call) once a
real gap was found: dbt's `raw_output` alone isn't trustworthy (a
documented dbt-core bug hardcodes `failures=0` on some passing-but-
actually-nonzero results - dbt-labs/dbt-core#11312) and Soda's
`row_count_total` isn't in `scan_results` at all - both only get
resolved via a live query against that run's own per-run DuckDB
warehouse, which only exists while the tool is actually running, not
when this history is read back later. Rather than have Phase 2's
dashboard-pipeline read step depend on that ephemeral warehouse too (or
silently trust a known-sometimes-wrong number), each `run_*.py` caller
now writes `verified` once, at the point that live connection already
exists - so reading committed history back later needs nothing beyond
this file. Every tool writes `verified` the same way, even the 2 (data-
contract-cli, Evidently) whose `raw_output` never needed correcting -
uniform shape, so the reader (`qa_results_reader.py`) never has to
special-case which tools happen to need it.

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
                     tool: str, raw_output: Any, verified: list[dict] | None = None,
                     results_dir: Path = QA_RESULTS_DIR) -> Path:
    """Writes one tool's native raw output for one run to a committed
    JSON file. `raw_output` must already be JSON-serializable (a plain
    dict/list) - each run_*.py caller is responsible for converting its
    own tool's native result object first (e.g. a Pydantic model's
    `.model_dump()`, an Evidently snapshot's `.dict()`) since that
    conversion is tool-specific, not something this generic writer
    should need to know about.

    `verified` is the caller's already-built list of fully-resolved
    check-result dicts for this tool+run (see this module's own
    docstring for why it exists alongside `raw_output`, not instead of
    it) - optional only so tests/ad-hoc calls that don't care about it
    can omit it; every real `run_*.py` caller passes it.

    Wraps the raw output with `run_timestamp` alongside it (not inside
    it - never mutates what the tool actually produced) so the file
    carries real provenance without touching the tool's own payload.
    Returns the path written."""
    run_dir = results_dir / agency / dataset / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    out_path = run_dir / f"{tool}.json"
    payload = {"run_timestamp": run_timestamp, "raw_output": raw_output, "verified": verified or []}
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    return out_path
