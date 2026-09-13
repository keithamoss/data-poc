"""
Runs REAL datacontract-cli against this project's actual
contract/bdm-birth-registrations-contract.yaml (its Python DataContract API,
not a reimplementation), once per run against that run's own raw CSV file -
this dataset's real production shape (BDM drops one CSV file per day), so no
per-run DuckDB file is needed here the way dbt/Soda needed one.

A "local_test" server (type: local, pointed at that run's CSV) is added to
an in-memory copy of the contract for each call - the file on disk is never
touched, and its own "production" S3 server is untouched too.

Getting this contract to lint/test at all - not just wiring engines/
contract_engine.py to a duckdb path - required fixing real, structural
mismatches between the original contract and actual ODCS v3, only visible
once `datacontract-cli` genuinely parsed it (see the contract file's own
comments and README.md's known-disagreements section for the full list:
description/support/team shape, the real dimension/severity enums, `rule`
being deprecated in favour of `metric` with a completely different rule
vocabulary, and datacontract-cli always linting against its bundled
odcs-3.2.0 schema regardless of a contract's own declared apiVersion).
"""
from __future__ import annotations
import copy
import os

import yaml

ROOT = os.path.join(os.path.dirname(__file__), "..")
CONTRACT_PATH = os.path.join(ROOT, "contract", "bdm-birth-registrations-contract.yaml")
RAW_DIR = os.path.join(ROOT, "data", "raw")

AGENCY_ID = "registry-services"
COLLECTION_ID = "civil-registration"
DATASET_ID = "birth-registrations"
ENGINE_TAG = "datacontract-cli 1.2.0 (real)"

# the real quality-rule-driven check types this project's contract produces
# (see contract yaml's metric: nullValues/invalidValues/duplicateValues/
# rowCount and type: sql rules) - excludes the schema-derived field_present/
# field_required/field_unique checks datacontract-cli generates for free
# from `required`/`unique` property flags, which duplicate these.
_QUALITY_CHECK_TYPES = {
    "field_null_values", "field_invalid_values", "field_duplicate_values",
    "field_quality_sql", "row_count",
}

_DIMENSION_BY_METRIC = {
    "missing_count": "completeness",
    "invalid_count": "validity",
    "duplicate_count": "uniqueness",
    "custom_sql": "consistency",
    "row_count": "completeness",
}


def evaluate_datacontract_real(run_id: str, csv_filename: str, run_timestamp: str) -> list[dict]:
    from datacontract.data_contract import DataContract

    with open(CONTRACT_PATH) as f:
        contract_dict = yaml.safe_load(f)

    d = copy.deepcopy(contract_dict)
    d["servers"].append({
        "server": "local_test",
        "type": "local",
        "path": os.path.join(RAW_DIR, csv_filename),
        "format": "csv",
        "delimiter": "comma",
    })

    dc = DataContract(data_contract_str=yaml.dump(d), server="local_test")
    run = dc.test()

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

        results.append({
            "agency_id": AGENCY_ID,
            "collection_id": COLLECTION_ID,
            "dataset_id": DATASET_ID,
            "column_name": c.field or "(table)",
            "check_name": f"datacontract:{metric}",
            "dimension": c.dimension or _DIMENSION_BY_METRIC.get(metric, ""),
            "run_id": run_id,
            "run_timestamp": run_timestamp,
            "metric_value": value,
            "unit": "%" if is_pct else "count",
            "warn_threshold": None,  # ODCS severity is single-tier - see contract_engine.py's own note
            "fail_threshold": 0 if diag.get("severity") == "error" else None,
            "status": {"passed": "pass", "failed": "fail", "warning": "warn"}.get(c.result.value, c.result.value),
            "on_fail_action": "quarantine" if diag.get("severity") == "error" else "flag",
            "row_count_total": row_count_total,
            "row_count_invalid": row_count_invalid,
            "engine": ENGINE_TAG,
        })

    return results


if __name__ == "__main__":
    import json
    from datetime import datetime, timezone

    with open(os.path.join(RAW_DIR, "manifest.json")) as f:
        manifest = json.load(f)
    for entry in manifest[:1] + [e for e in manifest if e["dirty_severity"]]:
        res = evaluate_datacontract_real(entry["run_id"], entry["file"], datetime.now(timezone.utc).isoformat())
        print(f"--- {entry['run_id']} ({entry['dirty_severity']}) ---")
        for r in res:
            if r["status"] != "pass":
                print(" ", r["column_name"], r["check_name"], r["status"], r["metric_value"], r["unit"])
