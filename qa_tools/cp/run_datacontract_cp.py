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

from qa_tools.common.datacontract_common import (
    ENGINE_TAG, DIMENSION_BY_METRIC, LABEL_BY_METRIC, SAMPLEABLE_METRICS,
    run_against_local_server, failing_sample_keys, check_id_from_quality_definition,
    fail_threshold_from_quality_definition,
)
from qa_tools.common.check_lifecycle import (
    name_by_check_id, parse_contract_check_metadata,
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

# REQ-QAC-023, 2026-09-20. Two description-parsing helpers used to live
# here and are gone:
#
#   _fk_column_for()   regex-matched a rule's own `description:` prose
#                      ("Every <table>'s <column> must reference an
#                      existing <table> row.") to recover which column
#                      the rule was about, because an ODCS table-level
#                      `type: sql` rule had no per-property home. The
#                      rules now sit UNDER their column, so the column
#                      comes from the contract's schema structure and
#                      arrives as `c.field` like every other check.
#   _custom_sql_label() matched the description's opening words against
#                      the three business-rule display names to decide
#                      whether a rule was an FK check or a business rule.
#
# Both worked. Both meant rewording an explanation could silently move a
# check to a different column, or rename it - and the check name is what
# a dashboard URL keys on. Real damage that had already shipped: one CP
# check's name had been mangled by the first-sentence split into a bare
# trailing full stop.
_FK_TOOLS_LABEL = "Referential integrity"
_FK_TAIL = "relationships_datacontract"

# Authored display names, read once at import from the contract itself -
# the same already-authoritative parse `category_by_check_id()` uses, not
# a second copy maintained here.
CHECK_NAME_BY_ID = name_by_check_id(parse_contract_check_metadata(CONTRACT_PATH))


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

        check_id = check_id_from_quality_definition(c.qualityDefinition)
        if check_id is None:
            raise ValueError(f"no check_id found in qualityDefinition for datacontract check {c.name!r} "
                              f"(type={c.type!r}) - the contract is missing customProperties.check_id for this rule")

        if metric == "custom_sql":
            # The AUTHORED name, never the rule's own prose. A rule with
            # no authored name is a real authoring gap, and failing
            # loudly beats falling back to the description - silently
            # doing that is the behaviour this requirement removed.
            authored = CHECK_NAME_BY_ID.get(check_id)
            if not authored:
                raise ValueError(
                    f"datacontract SQL rule {check_id!r} has no authored "
                    f"customProperties `name` - add one rather than letting its "
                    f"display name come from its description")
            check_name = f"datacontract:sql: {authored}"
            # Only a `relationships_*` rule is an FK check. Decided from
            # the check_id's own tail - structure - not by matching words
            # in the description.
            #
            # The predecessor asked the question the other way round
            # ("is this NOT one of the 3 business rules? then it is an
            # FK check"), which was a real bug: cp_clients' date-of-birth
            # range check is neither, and was labelled - and so grouped
            # across tools - as referential integrity. `label` is what
            # ties equivalent checks together, so that put a date-range
            # rule in a group it has nothing to do with.
            label = _FK_TOOLS_LABEL if check_id.endswith(_FK_TAIL) else None
        else:
            check_name = f"datacontract:{metric}"
            label = LABEL_BY_METRIC.get(metric)

        results.append({
            "agency_id": cp_common.AGENCY_ID,
            "collection_id": cp_common.COLLECTION_ID,
            "dataset_id": cp_common.TABLE_DATASET_ID[table],
            "check_id": check_id,
            "column_name": c.field or "(table)",
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
