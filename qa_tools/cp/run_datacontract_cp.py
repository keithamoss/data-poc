"""
Runs REAL datacontract-cli against contract/child-protection-contract.yaml,
once per run - the Child Protection counterpart to
qa_tools/bdm/run_datacontract_bdm.py.

Unlike Birth Registrations (one CSV per run), this contract has 6 schema
objects, so the `local` server's `path` uses datacontract-cli's own
`{model}` template (resolved per schema object name against
data/cp_raw/<run_id>/<model>.csv) - confirmed working during Phase 2
testing, and the same mechanism that lets this contract's cross-table
type: sql rules (the 7 FK checks, the 3 business rules) actually run: every
schema object becomes a real view/table on one shared duckdb connection,
so a rule on one model can genuinely join to another by its literal name.
The "local_test" server construction and DataContract.test() call are
shared with run_datacontract_bdm.py via
qa_tools/common/datacontract_common.py - see plans/qa-pipeline.md #84.

Each check result's dataset_id comes straight from `c.model` -
datacontract-cli's own check objects already know which schema object
(i.e. which CP table) they belong to.

Also captures up to 5 example failing rows' own primary keys per check
(see run_datacontract_bdm.py's docstring and datacontract_common.py -
identical mechanism, just keyed per-table via cp_common.TABLE_PK). Same
gap as BDM: the 7 FK checks and 3 business rules (all custom_sql) aren't
covered by datacontract-cli's include_failed_samples at all.
"""
from __future__ import annotations
import os
import re

from qa_tools.common.datacontract_common import (
    ENGINE_TAG, DIMENSION_BY_METRIC, LABEL_BY_METRIC, SAMPLEABLE_METRICS,
    run_against_local_server, failing_sample_keys, check_id_from_quality_definition,
    fail_threshold_from_quality_definition,
)
from qa_tools.common.qa_results_writer import write_qa_result
from . import cp_common

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
CONTRACT_PATH = os.path.join(ROOT, "contract", "child-protection-contract.yaml")
CP_RAW_DIR = os.path.join(ROOT, "data", "cp_raw")

_QUALITY_CHECK_TYPES = {
    "field_null_values", "field_invalid_values", "field_duplicate_values",
    "field_quality_sql", "model_quality_sql", "row_count",
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


def evaluate_datacontract_cp(run_id: str, run_timestamp: str) -> list[dict]:
    run = run_against_local_server(CONTRACT_PATH, os.path.join(CP_RAW_DIR, run_id, "{model}.csv"))

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
            label = LABEL_BY_METRIC.get(metric)

        check_id = check_id_from_quality_definition(c.qualityDefinition)
        if check_id is None:
            raise ValueError(f"no check_id found in qualityDefinition for datacontract check {c.name!r} "
                              f"(type={c.type!r}) - the contract is missing customProperties.check_id for this rule")

        results.append({
            "agency_id": cp_common.AGENCY_ID,
            "collection_id": cp_common.COLLECTION_ID,
            "dataset_id": cp_common.TABLE_DATASET_ID[table],
            "check_id": check_id,
            "column_name": fk_column or c.field or "(table)",
            "check_name": check_name,
            "dimension": c.dimension or DIMENSION_BY_METRIC.get(metric, ""),
            "label": label,
            "run_id": run_id,
            "run_timestamp": run_timestamp,
            "metric_value": value,
            "unit": "%" if is_pct else "count",
            "warn_threshold": None,
            "fail_threshold": fail_threshold_from_quality_definition(c.qualityDefinition, diag.get("severity")),
            "status": {"passed": "pass", "failed": "fail", "warning": "warn"}.get(c.result.value, c.result.value),
            "on_fail_action": "quarantine" if diag.get("severity") == "error" else "flag",
            "row_count_total": row_count_total,
            "row_count_invalid": row_count_invalid,
            "failing_sample_keys": failing_sample_keys(c, cp_common.TABLE_PK[table]) if metric in SAMPLEABLE_METRICS else [],
            "engine": ENGINE_TAG,
        })

    # No live-query correction needed (row_count is already in the raw
    # output's own diagnostics) - still writes `verified` for uniformity
    # with the other 3 tools, same reasoning as run_datacontract_bdm.py.
    write_qa_result(cp_common.AGENCY_ID, cp_common.COLLECTION_ID, run_id, run_timestamp,
                     "datacontract", run.model_dump(), verified=results)
    return results


if __name__ == "__main__":
    from datetime import datetime, timezone
    for run_id in ["cp_run_01_2026-07-06", "cp_run_04_2026-07-27", "cp_run_09_2026-08-31"]:
        res = evaluate_datacontract_cp(run_id, datetime.now(timezone.utc).isoformat())
        print(f"--- {run_id} ---")
        for r in res:
            if r["status"] != "pass":
                print(" ", r["dataset_id"], r["column_name"], r["check_name"], r["status"], r["metric_value"])
