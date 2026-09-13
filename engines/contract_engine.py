"""
A datacontract-cli EQUIVALENT: parses the real
contract/bdm-birth-registrations-contract.yaml (unmodified ODCS v3 YAML -
nothing about the rules below is invented for this engine, they're read
straight out of the contract file) and evaluates its actual quality rules
against one run's rows in the SQLite warehouse.

This is NOT datacontract-cli. That binary isn't pip-installable in this
sandbox (see README.md for the network-constraint note and the real-tool
swap-in instructions). This module hand-implements just the rule types
this one contract actually uses - nullCheck, regexPattern, validDateRange,
validValues, fieldComparison, duplicateCheck, rowCount - reading their
thresholds and severities from the YAML at run time, not from Python
constants. If the contract file changes, this engine's behaviour changes
with it, the same as a real contract engine.

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
from typing import Any

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


def _result(run_id, run_ts, column, check_name, dimension, metric_value, unit,
            warn_threshold, fail_threshold, status, on_fail_action, row_count_total, row_count_invalid):
    return {
        "agency_id": AGENCY_ID,
        "collection_id": COLLECTION_ID,
        "dataset_id": DATASET_ID,
        "column_name": column,
        "check_name": check_name,
        "dimension": dimension,
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

    for col in columns:
        name = col["name"]
        values = [r.get(name) for r in rows]

        for rule in col.get("quality", []):
            rtype = rule["rule"]
            severity = rule.get("severity", "error")
            dimension = rule.get("dimension", "")

            if rtype == "nullCheck":
                n_null = sum(1 for v in values if v is None or v == "")
                rate = n_null / n if n else 0.0
                if "mustBe" in rule:
                    threshold = rule["mustBe"]
                    violated = n_null != threshold
                    metric, unit = n_null, "count"
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
                    violated = rate >= threshold
                    # expressed in percentage-points (not a bare fraction) so
                    # this lines up with the Soda/dbt engines' own "%"-unit
                    # results for the same kind of rate check.
                    metric, unit = round(rate * 100, 4), "%"
                    threshold_pct = round(threshold * 100, 4)
                    if severity == "error":
                        warn_t, fail_t = threshold_pct, threshold_pct
                    else:
                        warn_t, fail_t = threshold_pct, 100.0  # rate can't exceed 100% - an honest "no red tier" ceiling
                status = _severity_to_status(severity, violated)
                results.append(_result(run_id, run_timestamp, name, "nullCheck", dimension,
                                        metric, unit, warn_t, fail_t, status,
                                        "quarantine" if severity == "error" else "flag", n, n_null))

            elif rtype == "regexPattern":
                pattern = re.compile(rule["mustBeRegex"])
                n_invalid = sum(1 for v in values if v is not None and not pattern.match(str(v)))
                violated = n_invalid > 0
                status = _severity_to_status(severity, violated)
                results.append(_result(run_id, run_timestamp, name, "regexPattern", dimension,
                                        n_invalid, "count", None, 0, status,
                                        "quarantine" if severity == "error" else "flag", n, n_invalid))

            elif rtype == "validDateRange":
                lo_raw, hi_raw = rule["mustBeBetween"]
                lo = datetime.strptime(lo_raw, "%Y-%m-%d").date()
                hi = date.today() if hi_raw == "$today" else datetime.strptime(hi_raw, "%Y-%m-%d").date()
                n_invalid = 0
                for v in values:
                    if v is None:
                        continue
                    try:
                        d = datetime.strptime(str(v)[:10], "%Y-%m-%d").date()
                    except ValueError:
                        n_invalid += 1
                        continue
                    if not (lo <= d <= hi):
                        n_invalid += 1
                violated = n_invalid > 0
                status = _severity_to_status(severity, violated)
                results.append(_result(run_id, run_timestamp, name, "validDateRange", dimension,
                                        n_invalid, "count", None, 0, status,
                                        "quarantine" if severity == "error" else "flag", n, n_invalid))

            elif rtype == "validValues":
                valid_set = set(rule["mustBe"])
                n_invalid = sum(1 for v in values if v is not None and v not in valid_set)
                violated = n_invalid > 0
                status = _severity_to_status(severity, violated)
                results.append(_result(run_id, run_timestamp, name, "validValues", dimension,
                                        n_invalid, "count", None, 0, status,
                                        "quarantine" if severity == "error" else "flag", n, n_invalid))

            elif rtype == "fieldComparison":
                other_col = rule["mustBeGreaterThanOrEqualTo"]
                other_values = [r.get(other_col) for r in rows]
                n_invalid = 0
                for v, ov in zip(values, other_values):
                    if v is None or ov is None:
                        continue
                    try:
                        dv = datetime.strptime(str(v)[:10], "%Y-%m-%d").date()
                        dov = datetime.strptime(str(ov)[:10], "%Y-%m-%d").date()
                    except ValueError:
                        continue
                    if dv < dov:
                        n_invalid += 1
                violated = n_invalid > 0
                status = _severity_to_status(severity, violated)
                results.append(_result(run_id, run_timestamp, name, "fieldComparison", dimension,
                                        n_invalid, "count", None, 0, status,
                                        "quarantine" if severity == "error" else "flag", n, n_invalid))

    # table-level quality rules
    for rule in table_schema.get("quality", []):
        rtype = rule["rule"]
        severity = rule.get("severity", "error")
        dimension = rule.get("dimension", "")

        if rtype == "duplicateCheck":
            reg_numbers = [r.get("registration_number") for r in rows]
            n_dupe = len(reg_numbers) - len(set(reg_numbers))
            violated = n_dupe != rule["mustBe"]
            status = _severity_to_status(severity, violated)
            results.append(_result(run_id, run_timestamp, "registration_number", "duplicateCheck", dimension,
                                    n_dupe, "count", None, rule["mustBe"], status,
                                    "quarantine" if severity == "error" else "flag", n, n_dupe))

        elif rtype == "rowCount":
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
