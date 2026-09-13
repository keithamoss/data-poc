"""
An Evidently AI EQUIVALENT: computes real Population Stability Index (PSI)
for the `sex` column, comparing each run's distribution against a fixed
reference run - the actual statistic Evidently's data-drift preset reports
for a categorical column, computed from scratch here rather than via the
`evidently` library (not pip-installable in this sandbox).

PSI formula (standard, per-category):
    PSI = sum( (actual_pct - reference_pct) * ln(actual_pct / reference_pct) )
over every category seen in either distribution (Laplace-smoothed so a
zero-count category doesn't produce ln(0)).

Conventional interpretation bands (used across the industry, not invented
for this project): PSI < 0.1 no significant shift, 0.1-0.25 moderate shift
(watch), > 0.25 major shift (investigate) - mapped here to pass/warn/fail
so drift results share the same status vocabulary as the other three
engines.

Reference run: the first CLEAN run in the manifest (run_01) - the
"known-good" baseline a real Evidently reference dataset would be, rather
than an arbitrary or most-recent run.
"""
from __future__ import annotations
import json
import math
import os

import duckdb

REFERENCE_RUN_ID = "run_01_2026-09-01"
CATEGORIES = ["M", "F", "X"]  # closed set per the contract; anything else is out-of-set
EPS = 1e-4


def _distribution(conn: duckdb.DuckDBPyConnection, run_id: str, column: str = "sex") -> dict[str, float]:
    rows = conn.execute(
        f"SELECT {column}, COUNT(*) FROM birth_registrations WHERE run_id = ? GROUP BY {column}",
        [run_id]
    ).fetchall()
    total = sum(c for _, c in rows)
    counts = {cat: 0 for cat in CATEGORIES}
    counts["_other"] = 0
    for val, c in rows:
        if val in counts:
            counts[val] += c
        else:
            counts["_other"] += c
    return {k: v / total for k, v in counts.items()} if total else {k: 0.0 for k in counts}


def _psi(reference: dict[str, float], actual: dict[str, float]) -> float:
    psi = 0.0
    for cat in set(reference) | set(actual):
        r = max(reference.get(cat, 0.0), EPS)
        a = max(actual.get(cat, 0.0), EPS)
        psi += (a - r) * math.log(a / r)
    return psi


def _status_for_psi(psi: float) -> str:
    if psi > 0.25:
        return "fail"
    if psi > 0.10:
        return "warn"
    return "pass"


def evaluate_drift(db_path: str, run_id: str, run_timestamp: str, reference_run_id: str = REFERENCE_RUN_ID) -> list[dict]:
    conn = duckdb.connect(db_path)
    reference = _distribution(conn, reference_run_id)
    actual = _distribution(conn, run_id)
    n_total = conn.execute(
        "SELECT COUNT(*) FROM birth_registrations WHERE run_id = ?", [run_id]
    ).fetchone()[0]
    conn.close()

    psi = _psi(reference, actual)
    status = _status_for_psi(psi)

    return [{
        "agency_id": "registry-services",
        "collection_id": "civil-registration",
        "dataset_id": "birth-registrations",
        "column_name": "sex",
        "check_name": "drift:PSI",
        "dimension": "consistency",
        "label": "Distribution drift",
        "run_id": run_id,
        "run_timestamp": run_timestamp,
        "metric_value": round(psi, 4),
        "unit": "PSI",
        "warn_threshold": 0.10,
        "fail_threshold": 0.25,
        "status": status if run_id != reference_run_id else "pass",
        "on_fail_action": "flag",
        "row_count_total": n_total,
        "row_count_invalid": None,
        "engine": "drift_engine (Evidently AI equivalent)",
        "reference_run_id": reference_run_id,
        "reference_distribution": reference,
        "actual_distribution": actual,
    }]


if __name__ == "__main__":
    from datetime import datetime
    db_path = os.path.join(os.path.dirname(__file__), "..", "data", "warehouse.duckdb")
    with open(os.path.join(os.path.dirname(__file__), "..", "data", "raw", "manifest.json")) as f:
        manifest = json.load(f)
    for entry in manifest:
        res = evaluate_drift(db_path, entry["run_id"], datetime.utcnow().isoformat())
        r = res[0]
        print(f"{entry['run_id']:25s} PSI={r['metric_value']:.4f}  status={r['status']:5s}  "
              f"actual={r['actual_distribution']}")
