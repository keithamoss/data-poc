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
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
QA_RESULTS_DIR = ROOT / "qa_results"


def _with_tables_read(verified: list[dict], run_id: str) -> list[dict]:
    """Record, on each cross-table check's own result, the physical
    table name of every OTHER table it read (REQ-PIPE-036 criterion 10).

    HERE RATHER THAN IN EACH TOOL, because this is the one place all
    eight run_*.py callers already funnel through - and doing it in
    four tool modules twice over is four chances for one of them to be
    missed, which produces a result that looks complete and names none
    of what it read.

    THE RESOLUTION IS READ ONLY WHERE SOMETHING DECLARES A DEPENDENCY.
    Birth Registrations has no cross-table check at all, so its four
    writes never open a connection; Child Protection's do. A run with
    no recorded resolution - a fixture, an ad hoc call - gets no
    tables_read rather than an error, and that is safe to be quiet
    about for one specific reason: the run-level tables_read.json
    (REQ-PIPE-068 criterion 5) records the same resolution for the
    whole run, so an absence here is visible against a file that is
    always written.
    """
    from qa_tools.common import tables_read as tables_read_mod

    declared = _declared_reads_tables()
    if not any(record.get("check_id") in declared for record in verified):
        return verified
    try:
        from qa_tools.common import supply_db

        conn = supply_db.connect(read_only=True)
        try:
            resolved = supply_db.resolution_for(conn, run_id).resolved
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 - see the docstring on why this is quiet
        return verified
    return tables_read_mod.attach(verified, resolved, declared)


@lru_cache(maxsize=1)
def _declared_reads_tables() -> dict[str, list[str]]:
    """`check_id` -> the tables that check declares it reads.

    Cached because it parses every check source and the answer cannot
    change within one process - a check definition is a file on disk,
    and a run that edited one mid-flight would have bigger problems.
    """
    from qa_tools.common import tables_read as tables_read_mod
    from qa_tools.common.validate_check_lifecycle import collect_checks

    try:
        return tables_read_mod.declared_by_check_id(collect_checks(None))
    except Exception:  # noqa: BLE001 - a malformed source is the lifecycle gate's to report
        return {}


def write_qa_result(agency: str, dataset: str, run_id: str, run_timestamp: str,
                     tool: str, raw_output: Any, verified: list[dict] | None = None,
                     run_by: str | None = None,
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

    `run_by` (qa_tools/common/git_identity.py's get_run_by(), the local
    git user.email) is the changelog feature's attribution field
    (plans/publishing-and-history.md Phase 3, 2026-09-16) - only
    orchestrate_bdm.py's/orchestrate_cp.py's own `dataset_stats` write
    passes it, since one value per run is all the changelog needs
    (qa_tools/common/changelog.py reads it from there); the other 8
    run_*.py callers leave it None, same "always present as a key,
    defaulted" shape `verified` already uses.

    Wraps the raw output with `run_timestamp` (and `run_by`) alongside
    it (not inside it - never mutates what the tool actually produced)
    so the file carries real provenance without touching the tool's own
    payload. Returns the path written - the DATASET-SCOPED one, which
    is the file every existing caller means by "the file this wrote".
    A cross-table sibling, where there is one, is written beside it."""
    from qa_tools.common import tables_read as tables_read_mod

    records = _with_tables_read(verified or [], run_id)
    # THE CALLER'S OWN RECORDS ARE BROUGHT UP TO DATE, and that is not
    # tidiness. The orchestrator keeps the list it passed here and
    # writes it to reports/results_*.json, which is what a LOCAL
    # dashboard build reads - while CI rebuilds from the committed
    # files instead. Enriching only the copy written to disk left the
    # two build paths producing different dashboards from the same run:
    # measured at 432 results carrying tables_read from committed
    # history and none from the live run. Nothing rendered it yet, so
    # nothing failed; the next thing to read it would have seen one
    # answer locally and another in CI.
    for original, enriched in zip(verified or [], records):
        original.update(enriched)
    # CRITERION 1: a check spanning more than one dataset is recorded
    # against a scope of its own, never against one of the datasets it
    # touches - which one it got filed under was arbitrary, and the
    # arbitrariness is the whole defect. CRITERION 2: it moves, it is
    # not copied; a record kept in two places is two records to keep in
    # step.
    declared = _declared_reads_tables()
    spanning = [r for r in records if r.get("check_id") in declared]
    own = [r for r in records if r.get("check_id") not in declared]

    run_dir = results_dir / agency / dataset / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    out_path = run_dir / f"{tool}.json"
    payload = {"run_timestamp": run_timestamp, "run_by": run_by,
               "raw_output": raw_output, "verified": own}
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2, default=str)

    if spanning:
        # THE RAW OUTPUT STAYS WITH THE DATASET FILE and is not copied
        # here. It is one tool invocation's native output covering the
        # whole collection, so duplicating it would double the bulk of
        # committed history - raw_output is already 61% of it - to say
        # the same thing twice. The cross-table file carries the
        # verified records, which is what a reader of this scope wants.
        cross_dir = results_dir / agency / dataset / tables_read_mod.CROSS_TABLE_SCOPE / run_id
        cross_dir.mkdir(parents=True, exist_ok=True)
        with open(cross_dir / f"{tool}.json", "w") as f:
            json.dump({"run_timestamp": run_timestamp, "run_by": run_by,
                        "raw_output": None, "verified": spanning},
                       f, indent=2, default=str)
    return out_path
