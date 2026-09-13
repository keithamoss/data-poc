"""
A datacontract-cli EQUIVALENT: parses the real
contract/bdm-birth-registrations-contract.yaml (unmodified ODCS v3 YAML -
nothing about the rules below is invented for this engine, they're read
straight out of the contract file) and evaluates its actual quality rules
against one run's rows in the DuckDB warehouse.

This is NOT datacontract-cli (real_tools/run_datacontract_real.py runs the
actual tool). This module hand-implements the real ODCS v3 quality-rule
vocabulary this contract actually uses - metric: nullValues/invalidValues/
duplicateValues/rowCount, and type: sql for the two rules with no direct
metric equivalent (date-range, cross-field comparison) - reading their
thresholds and severities from the YAML at run time, not from Python
constants. This vocabulary (and the contract file itself) was rewritten
from an earlier, invented `rule: nullCheck/regexPattern/...` shape once
real datacontract-cli actually parsed it and rejected that shape outright -
see the contract file's own comments and README.md's known-disagreements
section.

Every finding is emitted in the check-result record shape used across this
project (see data-contract-engines-landscape.md's "QA reporting layers"
section): agency_id/collection_id/dataset_id/column_name/check_name/
dimension/run_id/run_timestamp/metric_value/unit/warn_threshold/
fail_threshold/status/on_fail_action/row_count_total/row_count_invalid,
plus an `engine` tag so the dashboard/report can show which tool produced
which row.
"""
from __future__ import annotations
import re
from datetime import date, datetime

import duckdb
import yaml

AGENCY_ID = "registry-services"
COLLECTION_ID = "civil-registration"
DATASET_ID = "birth-registrations"
TABLE = "birth_registrations"


def _severity_to_status(severity: str, violated: bool) -> str:
    if not violated:
        return "pass"
    return {"error": "fail", "warning": "warn", "info": "warn"}.get(severity, "warn")


# A short, human-readable phrase for what each metric actually measures -
# looked up here, at the one shared point every check result passes
# through, not guessed later from check_name by the dashboard-building
# code. "sql" has no entry: this contract's 2 sql rules (a date-range
# check, a cross-field comparison) are each a one-off with nothing else to
# pair against, so there's no grouping benefit to labeling them.
_LABEL_BY_CHECK_NAME = {
    "nullValues": "Null rate",
    "invalidValues": "Invalid values",
    "duplicateValues": "Duplicate rate",
    "rowCount": "Row count",
}


def _result(run_id, run_ts, column, check_name, dimension, metric_value, unit,
            warn_threshold, fail_threshold, status, on_fail_action, row_count_total, row_count_invalid):
    return {
        "agency_id": AGENCY_ID,
        "collection_id": COLLECTION_ID,
        "dataset_id": DATASET_ID,
        "column_name": column,
        "check_name": check_name,
        "dimension": dimension,
        "label": _LABEL_BY_CHECK_NAME.get(check_name),
        "run_id": run_id,
        "run_timestamp": run_ts,
        "metric_value": metric_value,
        "unit": unit,
        "warn_threshold": warn_threshold,
        "fail_threshold": fail_threshold,
        "status": status,
        "on_fail_action": on_fail_action,
        "row_count_total": row_count_total,
        "row_count_invalid": row_count_invalid,
        "engine": "contract_engine (datacontract-cli equivalent)",
    }


def _rows_for_run(conn: duckdb.DuckDBPyConnection, run_id: str) -> list[dict]:
    df = conn.execute(f"SELECT * FROM {TABLE} WHERE run_id = ?", [run_id]).df()
    df = df.astype(object).where(df.notna(), None)
    return df.to_dict("records")


def evaluate_contract(contract_path: str, db_path: str, run_id: str, run_timestamp: str) -> list[dict]:
    with open(contract_path) as f:
        contract = yaml.safe_load(f)

    conn = duckdb.connect(db_path)
    rows = _rows_for_run(conn, run_id)
    n = len(rows)
    results: list[dict] = []

    table_schema = contract["schema"][0]
    columns = table_schema["properties"]

    def _is_percent(rule: dict) -> bool:
        return str(rule.get("unit", "")).strip().lower() == "percent"

    for col in columns:
        name = col["name"]
        values = [r.get(name) for r in rows]

        for rule in col.get("quality", []):
            severity = rule.get("severity", "error")
            dimension = rule.get("dimension", "")
            metric = rule.get("metric")

            if metric == "nullValues":
                n_null = sum(1 for v in values if v is None or v == "")
                rate = n_null / n if n else 0.0
                if "mustBe" in rule:
                    threshold = rule["mustBe"]
                    violated = n_null != threshold
                    metric_value, unit = n_null, "count"
                    # ODCS severity is single-tier (a rule is either "error" -
                    # pass/fail with no amber band - or "warning"/"info" -
                    # pass/warn with NO red band at all). A downstream
                    # consumer with only a two-threshold warn/fail slot (like
                    # this project's dashboard) needs that encoded into
                    # warn/fail directly, not left as a bare single
                    # threshold, or it'll invent an amber band that doesn't
                    # exist in the real rule (see README's known-simplifications
                    # note): error -> warn==fail==threshold (binary
                    # green/red); warning/info -> warn==threshold,
                    # fail==an unreachable ceiling (never red).
                    if severity == "error":
                        warn_t, fail_t = threshold, threshold
                    else:
                        warn_t, fail_t = threshold, max(threshold, n) + 1
                else:
                    threshold = rule["mustBeLessThan"]
                    violated = (rate * 100 if _is_percent(rule) else n_null) >= threshold
                    metric_value, unit = (round(rate * 100, 4), "%") if _is_percent(rule) else (n_null, "count")
                    if severity == "error":
                        warn_t, fail_t = threshold, threshold
                    else:
                        warn_t, fail_t = threshold, (100.0 if _is_percent(rule) else n + 1)
                status = _severity_to_status(severity, violated)
                results.append(_result(run_id, run_timestamp, name, "nullValues", dimension,
                                        metric_value, unit, warn_t, fail_t, status,
                                        "quarantine" if severity == "error" else "flag", n, n_null))

            elif metric == "invalidValues":
                args = rule.get("arguments") or {}
                if "pattern" in args:
                    pattern = re.compile(args["pattern"])
                    n_invalid = sum(1 for v in values if v is not None and not pattern.match(str(v)))
                elif "validValues" in args:
                    valid_set = set(args["validValues"])
                    n_invalid = sum(1 for v in values if v is not None and v not in valid_set)
                else:
                    continue
                violated = n_invalid > 0
                status = _severity_to_status(severity, violated)
                results.append(_result(run_id, run_timestamp, name, "invalidValues", dimension,
                                        n_invalid, "count", None, 0, status,
                                        "quarantine" if severity == "error" else "flag", n, n_invalid))

            elif metric == "duplicateValues":
                col_values = [r.get(name) for r in rows]
                n_dupe = len(col_values) - len(set(col_values))
                threshold = rule.get("mustBe", 0)
                violated = n_dupe != threshold
                status = _severity_to_status(severity, violated)
                results.append(_result(run_id, run_timestamp, name, "duplicateValues", dimension,
                                        n_dupe, "count", None, threshold, status,
                                        "quarantine" if severity == "error" else "flag", n, n_dupe))

            elif rule.get("type") == "sql":
                query = rule["query"].format(model=TABLE, field=name)
                # emulate datacontract-cli's {model}/{field} placeholder
                # substitution (see prepare_query in its create_checks.py)
                # against this run's rows specifically, via a scoped view.
                safe_run_id = run_id.replace("'", "''")
                conn.execute(f"CREATE OR REPLACE TEMP VIEW _rule_scope AS SELECT * FROM {TABLE} WHERE run_id = '{safe_run_id}'")
                scoped_query = query.replace(TABLE, "_rule_scope")
                n_invalid = conn.execute(scoped_query).fetchone()[0]
                threshold = rule.get("mustBe", 0)
                violated = n_invalid != threshold
                status = _severity_to_status(severity, violated)
                results.append(_result(run_id, run_timestamp, name, "sql", dimension,
                                        n_invalid, "count", None, threshold, status,
                                        "quarantine" if severity == "error" else "flag", n, n_invalid))

    # table-level quality rules
    for rule in table_schema.get("quality", []):
        severity = rule.get("severity", "error")
        dimension = rule.get("dimension", "")
        metric = rule.get("metric")

        if metric == "rowCount":
            lo, hi = rule["mustBeBetween"]
            violated = not (lo <= n <= hi)
            status = _severity_to_status(severity, violated)
            results.append(_result(run_id, run_timestamp, "(table)", "rowCount", dimension,
                                    n, "count", lo, hi, status,
                                    "quarantine" if severity == "error" else "flag", n, 0 if not violated else n))

    conn.close()
    return results


if __name__ == "__main__":
    import json
    import os
    contract_path = os.path.join(os.path.dirname(__file__), "..", "contract", "bdm-birth-registrations-contract.yaml")
    db_path = os.path.join(os.path.dirname(__file__), "..", "data", "warehouse.duckdb")
    res = evaluate_contract(contract_path, db_path, "run_09_2026-09-09", datetime.utcnow().isoformat())
    print(json.dumps(res, indent=2))
