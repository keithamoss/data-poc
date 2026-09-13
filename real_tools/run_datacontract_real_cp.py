"""
Runs REAL datacontract-cli against contract/child-protection-contract.yaml,
once per run - the Child Protection counterpart to run_datacontract_real.py.

Unlike Birth Registrations (one CSV per run), this contract has 6 schema
objects, so the `local` server's `path` uses datacontract-cli's own
`{model}` template (resolved per schema object name against
data/cp_raw/<run_id>/<model>.csv) - confirmed working during Phase 2
testing, and the same mechanism that lets this contract's cross-table
type: sql rules (the 7 FK checks, the 3 business rules) actually run: every
schema object becomes a real view/table on one shared duckdb connection,
so a rule on one model can genuinely join to another by its literal name.

Each check result's dataset_id comes straight from `c.model` -
datacontract-cli's own check objects already know which schema object
(i.e. which CP table) they belong to.
"""
from __future__ import annotations
import copy
import os
import re
import sys

import yaml

sys.path.insert(0, os.path.dirname(__file__))
import cp_common

ROOT = os.path.join(os.path.dirname(__file__), "..")
CONTRACT_PATH = os.path.join(ROOT, "contract", "child-protection-contract.yaml")
CP_RAW_DIR = os.path.join(ROOT, "data", "cp_raw")

ENGINE_TAG = "datacontract-cli 1.2.0 (real)"

_QUALITY_CHECK_TYPES = {
    "field_null_values", "field_invalid_values", "field_duplicate_values",
    "field_quality_sql", "model_quality_sql", "row_count",
}

_DIMENSION_BY_METRIC = {
    "missing_count": "completeness",
    "invalid_count": "validity",
    "duplicate_count": "uniqueness",
    "custom_sql": "consistency",
    "row_count": "completeness",
}

# A short, human-readable phrase for what each metric actually measures -
# written here, where each check result is constructed, not guessed later
# from check_name by the dashboard-building code.
_LABEL_BY_METRIC = {
    "missing_count": "Null rate",
    "invalid_count": "Invalid values",
    "duplicate_count": "Duplicate rate",
    "row_count": "Row count",
}


_FK_DESCRIPTION_RE = re.compile(r"^Every \w+'s (\w+) must reference an existing \w+ row\.")


def _fk_column_for(description: str) -> str | None:
    """The 7 FK checks' descriptions (this contract's own text, written by
    hand, not a guess) all follow the exact same
    "Every <table>'s <column> must reference an existing <table> row."
    shape - so the column they're actually about is parsed straight out
    of the rule's own words. Returns None for the 3 business rules, whose
    descriptions don't match this shape at all.

    Without this, every FK check lands under column_name="(table)" (since
    ODCS has no per-property home for a table-level type: sql rule) and
    gets grouped into the dashboard's "(table-level checks)" pseudo-
    column - inconsistent with dbt's `relationships` tests and Soda's
    `values in ... must exist in ...` checks for the exact same FK, which
    the dashboard *does* attribute to the FK column itself. Keith asked
    for this to be consistent across all three tools."""
    m = _FK_DESCRIPTION_RE.match(description)
    return m.group(1) if m else None


def _custom_sql_label(description: str) -> str | None:
    """custom_sql covers both the 7 FK checks and the 3 business rules -
    distinguished here by whether the rule's own description (this
    contract's own text, not a guess) opens with one of the 3 known
    business-rule names. FK checks get "Referential integrity" (they
    otherwise read as 7 unrelated one-off sentences); business rules get
    None, since their own name already matches dbt's and Soda's names for
    the same rule closely enough to read as the same thing without a
    further prefix."""
    for name in cp_common.BUSINESS_RULE_DISPLAY_NAME.values():
        if description.startswith(name + ":"):
            return None
    return "Referential integrity"


def evaluate_datacontract_real_cp(run_id: str, run_timestamp: str) -> list[dict]:
    from datacontract.data_contract import DataContract

    with open(CONTRACT_PATH) as f:
        contract_dict = yaml.safe_load(f)

    d = copy.deepcopy(contract_dict)
    d["servers"].append({
        "server": "local_test",
        "type": "local",
        "path": os.path.join(CP_RAW_DIR, run_id, "{model}.csv"),
        "format": "csv",
        "delimiter": "comma",
    })

    dc = DataContract(data_contract_str=yaml.dump(d), server="local_test")
    run = dc.test()

    results = []
    for c in run.checks:
        if c.type not in _QUALITY_CHECK_TYPES:
            continue
        table = c.model
        if table not in cp_common.TABLE_DATASET_ID:
            continue

        diag = c.diagnostics or {}
        metric = diag.get("metric", c.type)
        is_pct = "percent" in diag
        value = diag.get("percent") if is_pct else diag.get("value")
        row_count_total = diag.get("row_count")
        row_count_invalid = None if metric == "row_count" else diag.get("value")

        # "custom_sql" alone doesn't distinguish the 7 FK checks and 3
        # business rules from each other (they're all type: sql) - c.name
        # carries this rule's own `description:` text from the contract
        # verbatim, which is genuinely distinct per rule but, for the 3
        # business rules, several paragraphs long (see contract's
        # comments) - only the first sentence is short and descriptive
        # enough for a check_name label, so that's all that's kept here.
        fk_column = None
        if metric == "custom_sql":
            first_sentence = c.name.split(". ", 1)[0].rstrip(".") + "."
            check_name = f"datacontract:sql: {first_sentence}"
            label = _custom_sql_label(c.name)
            fk_column = _fk_column_for(c.name)
        else:
            check_name = f"datacontract:{metric}"
            label = _LABEL_BY_METRIC.get(metric)

        results.append({
            "agency_id": cp_common.AGENCY_ID,
            "collection_id": cp_common.COLLECTION_ID,
            "dataset_id": cp_common.TABLE_DATASET_ID[table],
            "column_name": fk_column or c.field or "(table)",
            "check_name": check_name,
            "dimension": c.dimension or _DIMENSION_BY_METRIC.get(metric, ""),
            "label": label,
            "run_id": run_id,
            "run_timestamp": run_timestamp,
            "metric_value": value,
            "unit": "%" if is_pct else "count",
            "warn_threshold": None,
            "fail_threshold": 0 if diag.get("severity") == "error" else None,
            "status": {"passed": "pass", "failed": "fail", "warning": "warn"}.get(c.result.value, c.result.value),
            "on_fail_action": "quarantine" if diag.get("severity") == "error" else "flag",
            "row_count_total": row_count_total,
            "row_count_invalid": row_count_invalid,
            "engine": ENGINE_TAG,
        })

    return results


if __name__ == "__main__":
    from datetime import datetime, timezone
    for run_id in ["cp_run_01_2026-07-06", "cp_run_04_2026-07-27", "cp_run_09_2026-08-31"]:
        res = evaluate_datacontract_real_cp(run_id, datetime.now(timezone.utc).isoformat())
        print(f"--- {run_id} ---")
        for r in res:
            if r["status"] != "pass":
                print(" ", r["dataset_id"], r["column_name"], r["check_name"], r["status"], r["metric_value"])
