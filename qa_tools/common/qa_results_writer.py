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
real gap was found: `raw_output` alone isn't trustworthy or sufficient
for two dbt-side bugs plus one Soda-side gap, all already investigated
in full in `plans/qa-pipeline.md` and `qa_tools/bdm/run_dbt_bdm.py`'s
own docstring - not re-derived here, just cited:

1. **dbt-core's `failures=0` accounting bug**, root-caused
   (`plans/qa-pipeline.md` item 34): `dbt/task/test.py`'s
   `build_test_run_result()` (confirmed in our installed dbt-core
   1.12.4's own source) never reassigns `failures` off its `0` default
   when a test's final status lands on "Pass" - so any test whose real
   failure count is nonzero but under every configured threshold (a
   genuine pass) silently reports `failures=0` in `run_results.json`.
   Filed and triaged upstream as a real bug, fix unmerged as of our
   installed version: [dbt-labs/dbt-core#11312](
   https://github.com/dbt-labs/dbt-core/issues/11312).
2. **A second, separate, still-NOT-root-caused nondeterminism**
   (`plans/qa-pipeline.md` items 34 and 38): a test's reported status/
   failures flipping between correct and wrong across separate
   `dbt build` invocations of the identical warehouse file, no code
   change in between. Item 38's own deep, controlled repro (40+
   invocations, isolated and under real parallel load) found and fixed
   a related-but-distinct, fully-explained bug along the way (a missing
   `fail_calc:` override in this project's own `schema.yml`, nothing to
   do with dbt-core itself) but never reproduced the original flip - it
   remains open, unexplained, and has no upstream issue filed (points at
   dbt-duckdb's query execution path, not dbt-core's result-reporting
   logic, so there's nothing to link beyond this repo's own account).
3. **Soda's `row_count_total` isn't in `scan_results` at all** - not a
   Soda bug, just a genuine gap in what that structure exposes (no
   issue to cite, upstream or otherwise).

Both dbt problems are exactly what `run_dbt_bdm.py`'s/`run_dbt_cp.py`'s
`_AUDIT_AGGREGATE_SQL` audit-table re-query protects against "at once"
(their own docstrings' wording) - it doesn't care which of the two
produced a wrong number, it re-derives the truth from dbt's own
`--store-failures` audit table regardless. That query, and Soda's
`row_count_total` query, both need a live connection to that run's own
per-run DuckDB warehouse - which only exists while the tool is actually
running, not when this history is read back later. Rather than have
Phase 2's dashboard-pipeline read step depend on that ephemeral
warehouse too (or silently trust numbers known to sometimes be wrong),
each `run_*.py` caller now writes `verified` once, at the point that
live connection already exists - so reading committed history back
later needs nothing beyond this file. Every tool writes `verified` the
same way, even the 2 (datacontract-cli, Evidently) whose `raw_output`
never needed correcting - uniform shape, so the reader
(`qa_results_reader.py`) never has to special-case which tools happen
to need it.

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
