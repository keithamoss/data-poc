"""
A Soda Core EQUIVALENT: parses the real
contract/bdm-birth-registrations-soda-checks.yml (unmodified SodaCL YAML)
and evaluates its specific checks against one run's rows - row_count,
missing_count, invalid_percent (with a `valid values` list), missing_percent,
and the `filter ... [recent]` + scoped `checks for ... [recent]` construct
for the last-24h sex-validity check.

This is NOT Soda Core. The `soda` binary isn't pip-installable in this
sandbox. This module hand-parses just the SodaCL shapes this one checks
file actually uses, reading thresholds straight from the YAML (not hardcoded
in Python), which is what gives this - unlike the contract engine's flat
error/warning/info severities - genuine two-tier warn/fail traffic-light
behaviour per check.
"""
from __future__ import annotations
import re
from datetime import datetime, timedelta

import duckdb
import yaml

AGENCY_ID = "registry-services"
COLLECTION_ID = "civil-registration"
DATASET_ID = "birth-registrations"
TABLE = "birth_registrations"

# matches "when < 500", "when > 20000", "when > 2%", "when > 0%"
_COND_RE = re.compile(r"when\s*([<>]=?)\s*([\d.]+)\s*(%?)")


def _parse_conditions(spec) -> list[tuple[str, float, bool]]:
    """spec is either a single 'when < 500' string, or a list of such
    strings (row_count's fail: has two `when` lines - a range). Returns
    (operator, value, is_percent) tuples."""
    if spec is None:
        return []
    if isinstance(spec, str):
        spec = [spec]
    out = []
    for s in spec:
        m = _COND_RE.search(s)
        if m:
            op, val, pct = m.groups()
            out.append((op, float(val), bool(pct)))
    return out


def _condition_met(metric: float, conditions: list[tuple[str, float, bool]], as_percent: bool) -> bool:
    m = metric * 100 if as_percent else metric
    for op, val, is_pct in conditions:
        v = val  # threshold is already expressed in the same units the check line used
        if op == "<" and m < v:
            return True
        if op == "<=" and m <= v:
            return True
        if op == ">" and m > v:
            return True
        if op == ">=" and m >= v:
            return True
    return False


def _status_for(metric: float, warn_spec, fail_spec, as_percent: bool) -> str:
    if _condition_met(metric, _parse_conditions(fail_spec), as_percent):
        return "fail"
    if _condition_met(metric, _parse_conditions(warn_spec), as_percent):
        return "warn"
    return "pass"


def _numeric_threshold(spec) -> float | None:
    """Reduces a warn:/fail: spec to one representative number, in the same
    units the check line used (already *100 for a '%' line, so this is a
    plain percentage-point figure, not a fraction) - what the check-result
    record schema's warn_threshold/fail_threshold fields expect.

    row_count's fail: line is a genuine two-sided range ('when < 100' AND
    'when > 20000') that doesn't reduce to one scalar without losing
    information; this takes the upper (">"/">=") bound, since "too much of
    a bad thing" is the dominant shape everywhere else in this project, and
    documents the lower bound is dropped here rather than silently guessing
    which one a reader would expect - see README.md's known-simplifications
    note."""
    conds = _parse_conditions(spec)
    if not conds:
        return None
    for op, val, _is_pct in conds:
        if op in (">", ">="):
            return val
    return conds[0][1]


def _result(run_id, run_ts, column, check_name, metric_value, unit,
            warn_threshold, fail_threshold, status, row_count_total, row_count_invalid):
    return {
        "agency_id": AGENCY_ID,
        "collection_id": COLLECTION_ID,
        "dataset_id": DATASET_ID,
        "column_name": column,
        "check_name": check_name,
        "dimension": "validity" if "invalid" in check_name else "completeness",
        "run_id": run_id,
        "run_timestamp": run_ts,
        "metric_value": metric_value,
        "unit": unit,
        "warn_threshold": warn_threshold,
        "fail_threshold": fail_threshold,
        "status": status,
        "on_fail_action": "flag",
        "row_count_total": row_count_total,
        "row_count_invalid": row_count_invalid,
        "engine": "soda_engine (Soda Core equivalent)",
    }


def evaluate_soda(checks_path: str, db_path: str, run_id: str, run_timestamp: str) -> list[dict]:
    with open(checks_path) as f:
        doc = yaml.safe_load_all(f)
        docs = list(doc)

    conn = duckdb.connect(db_path)
    df = conn.execute(f"SELECT * FROM {TABLE} WHERE run_id = ?", [run_id]).df()
    df = df.astype(object).where(df.notna(), None)
    rows = df.to_dict("records")
    n_total = len(rows)
    results: list[dict] = []

    # this checks file is a single YAML document containing several
    # top-level "checks for X[...]" and "filter X[...]" keys (not separate
    # --- documents), so PyYAML's safe_load (not safe_load_all) is what
    # actually parses it - reload accordingly.
    with open(checks_path) as f:
        doc = yaml.safe_load(f)

    for key, checks in doc.items():
        if not key.startswith("checks for"):
            continue
        scope = "recent" if "[recent]" in key else "all"
        scoped_rows = rows
        if scope == "recent":
            # filter block: extract_timestamp >= CURRENT_DATE - 1 -> last 24h
            # of extracts, evaluated relative to this run's own extract
            # timestamps (the latest extract_timestamp in the run stands in
            # for "now", since these are historical synthetic runs rather
            # than a live feed with a real wall-clock "today").
            extract_dates = [str(r["extract_timestamp"]) for r in rows if r.get("extract_timestamp")]
            as_of = max(extract_dates) if extract_dates else str(run_timestamp)
            as_of_date = datetime.strptime(as_of[:10], "%Y-%m-%d")
            cutoff = as_of_date - timedelta(days=1)
            scoped_rows = [
                r for r in rows
                if r.get("extract_timestamp") and datetime.strptime(str(r["extract_timestamp"])[:10], "%Y-%m-%d") >= cutoff
            ]
            # extract_timestamp is same-day as run_date for every synthetic
            # row in this dataset, so "recent" == "all" here in practice -
            # this is a faithful implementation of the filter semantics, it's
            # just that the fixture has no multi-day-stale rows to exclude.
        n_scope = len(scoped_rows)

        for check in checks:
            ((check_name, spec),) = check.items()

            if check_name == "row_count":
                status = _status_for(n_scope, spec.get("warn"), spec.get("fail"), as_percent=False)
                results.append(_result(run_id, run_timestamp, "(table)", f"row_count[{scope}]",
                                        n_scope, "count",
                                        _numeric_threshold(spec.get("warn")), _numeric_threshold(spec.get("fail")),
                                        status, n_total, 0))

            elif check_name.startswith("missing_count("):
                col = check_name[len("missing_count("):-1]
                n_missing = sum(1 for r in scoped_rows if r.get(col) is None or r.get(col) == "")
                status = _status_for(n_missing, spec.get("warn"), spec.get("fail"), as_percent=False)
                results.append(_result(run_id, run_timestamp, col, f"missing_count[{scope}]",
                                        n_missing, "count",
                                        _numeric_threshold(spec.get("warn")), _numeric_threshold(spec.get("fail")),
                                        status, n_scope, n_missing))

            elif check_name.startswith("invalid_percent("):
                col = check_name[len("invalid_percent("):-1]
                valid_set = set(spec.get("valid values", []))
                vals = [r.get(col) for r in scoped_rows if r.get(col) is not None and r.get(col) != ""]
                n_invalid = sum(1 for v in vals if v not in valid_set)
                rate = n_invalid / n_scope if n_scope else 0.0
                status = _status_for(rate, spec.get("warn"), spec.get("fail"), as_percent=True)
                name = spec.get("name", f"invalid_percent[{scope}]")
                results.append(_result(run_id, run_timestamp, col, name,
                                        round(rate * 100, 4), "%",
                                        _numeric_threshold(spec.get("warn")), _numeric_threshold(spec.get("fail")),
                                        status, n_scope, n_invalid))

            elif check_name.startswith("missing_percent("):
                col = check_name[len("missing_percent("):-1]
                n_missing = sum(1 for r in scoped_rows if r.get(col) is None or r.get(col) == "")
                rate = n_missing / n_scope if n_scope else 0.0
                status = _status_for(rate, spec.get("warn"), spec.get("fail"), as_percent=True)
                results.append(_result(run_id, run_timestamp, col, f"missing_percent[{scope}]",
                                        round(rate * 100, 4), "%",
                                        _numeric_threshold(spec.get("warn")), _numeric_threshold(spec.get("fail")),
                                        status, n_scope, n_missing))

    conn.close()
    return results


if __name__ == "__main__":
    import json
    import os
    checks_path = os.path.join(os.path.dirname(__file__), "..", "contract", "bdm-birth-registrations-soda-checks.yml")
    db_path = os.path.join(os.path.dirname(__file__), "..", "data", "warehouse.duckdb")
    res = evaluate_soda(checks_path, db_path, "run_04_2026-09-04", datetime.utcnow().isoformat())
    print(json.dumps(res, indent=2))
