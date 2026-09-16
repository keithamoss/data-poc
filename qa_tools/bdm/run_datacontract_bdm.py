"""
Runs REAL datacontract-cli against this project's actual
contract/bdm-birth-registrations-contract.yaml (its Python DataContract API,
not a reimplementation), once per run against that run's own raw CSV file -
this dataset's real production shape (BDM drops one CSV file per day), so no
per-run DuckDB file is needed here the way dbt/Soda needed one.

The "local_test" server construction and DataContract.test() call are
shared with run_datacontract_cp.py via
qa_tools/common/datacontract_common.py - see plans/wider.md #20.

Getting this contract to lint/test at all required fixing real, structural
mismatches between the original contract and actual ODCS v3, only visible
once `datacontract-cli` genuinely parsed it (see the contract file's own
comments and README.md's known-disagreements section for the full list:
description/support/team shape, the real dimension/severity enums, `rule`
being deprecated in favour of `metric` with a completely different rule
vocabulary, and datacontract-cli always linting against its bundled
odcs-3.2.0 schema regardless of a contract's own declared apiVersion).

Also captures up to 5 example failing rows' registration_numbers per
check, via datacontract-cli's own include_failed_samples=True (see
datacontract_common.py) - it already restricts samples to identifier +
offending-field columns itself, never full row content, matching
plans/qa-pipeline.md #15's "flag it" scope. Only the 3 SAMPLEABLE_METRICS
(missing/invalid/duplicate_count) get samples from this tool - custom_sql
rules (the freshness/sibling/timestamp checks) aren't covered by
include_failed_samples at all, a real gap noted rather than hidden.
"""
from __future__ import annotations
import os

from qa_tools.common.datacontract_common import (
    ENGINE_TAG, DIMENSION_BY_METRIC, LABEL_BY_METRIC, SAMPLEABLE_METRICS,
    run_against_local_server, failing_sample_keys,
)
from qa_tools.common.qa_results_writer import write_qa_result

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
CONTRACT_PATH = os.path.join(ROOT, "contract", "bdm-birth-registrations-contract.yaml")
RAW_DIR = os.path.join(ROOT, "data", "raw")

AGENCY_ID = "registry-services"
COLLECTION_ID = "civil-registration"
DATASET_ID = "birth-registrations"

# the real quality-rule-driven check types this project's contract produces
# (see contract yaml's metric: nullValues/invalidValues/duplicateValues/
# rowCount and type: sql rules) - excludes the schema-derived field_present/
# field_required/field_unique checks datacontract-cli generates for free
# from `required`/`unique` property flags, which duplicate these.
_QUALITY_CHECK_TYPES = {
    "field_null_values", "field_invalid_values", "field_duplicate_values",
    "field_quality_sql", "row_count",
}

# The 2 custom_sql rules below get an explicit shared label: each is the
# same real-world check as a dbt (and, for the sibling check, Soda)
# counterpart under a different name - the label is what makes that
# overlap visible on the dashboard, same rationale as run_dbt_bdm.py's
# and run_soda_bdm.py's own versions of this dict. Matched by the
# rule's own description prefix (this contract's own text, not a guess).
_CUSTOM_SQL_LABEL = {
    "Multiple-birth sibling match:": "Sibling record match",
    "Extract timestamp ordering:": "Timestamp ordering",
    "Freshness / relative-date check:": "Freshness",
}


def _custom_sql_label(description: str) -> str | None:
    for prefix, label in _CUSTOM_SQL_LABEL.items():
        if description.startswith(prefix):
            return label
    return None


def evaluate_datacontract_bdm(run_id: str, csv_filename: str, run_timestamp: str) -> list[dict]:
    run = run_against_local_server(CONTRACT_PATH, os.path.join(RAW_DIR, csv_filename))
    write_qa_result(AGENCY_ID, DATASET_ID, run_id, run_timestamp, "datacontract", run.model_dump())

    results = []
    for c in run.checks:
        if c.type not in _QUALITY_CHECK_TYPES:
            continue
        diag = c.diagnostics or {}
        metric = diag.get("metric", c.type)
        is_pct = "percent" in diag
        value = diag.get("percent") if is_pct else diag.get("value")
        row_count_total = diag.get("row_count")
        row_count_invalid = None if metric == "row_count" else diag.get("value")

        label = _custom_sql_label(c.name) if metric == "custom_sql" else LABEL_BY_METRIC.get(metric)

        results.append({
            "agency_id": AGENCY_ID,
            "collection_id": COLLECTION_ID,
            "dataset_id": DATASET_ID,
            "column_name": c.field or "(table)",
            "check_name": f"datacontract:{metric}",
            "dimension": c.dimension or DIMENSION_BY_METRIC.get(metric, ""),
            "label": label,
            "run_id": run_id,
            "run_timestamp": run_timestamp,
            "metric_value": value,
            "unit": "%" if is_pct else "count",
            "warn_threshold": None,  # ODCS severity is single-tier - see README.md's known-disagreements section
            "fail_threshold": 0 if diag.get("severity") == "error" else None,
            "status": {"passed": "pass", "failed": "fail", "warning": "warn"}.get(c.result.value, c.result.value),
            "on_fail_action": "quarantine" if diag.get("severity") == "error" else "flag",
            "row_count_total": row_count_total,
            "row_count_invalid": row_count_invalid,
            "failing_sample_keys": failing_sample_keys(c, "registration_number") if metric in SAMPLEABLE_METRICS else [],
            "engine": ENGINE_TAG,
        })

    return results


if __name__ == "__main__":
    import json
    from datetime import datetime, timezone

    with open(os.path.join(RAW_DIR, "manifest.json")) as f:
        manifest = json.load(f)
    for entry in manifest[:1] + [e for e in manifest if e["dirty_severity"]]:
        res = evaluate_datacontract_bdm(entry["run_id"], entry["file"], datetime.now(timezone.utc).isoformat())
        print(f"--- {entry['run_id']} ({entry['dirty_severity']}) ---")
        for r in res:
            if r["status"] != "pass":
                print(" ", r["column_name"], r["check_name"], r["status"], r["metric_value"], r["unit"])
