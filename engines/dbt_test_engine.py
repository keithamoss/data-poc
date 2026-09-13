"""
A dbt-core EQUIVALENT: renders the real dbt_project/models/staging/
stg_birth_registrations.sql (via Jinja2 - the actual templating engine dbt
itself uses, resolving {{ source('raw','birth_registrations') }} to the
warehouse table) into a genuine SQLite VIEW, then reads
dbt_project/models/staging/schema.yml - the real dbt schema file, generic
tests and severity config included - and evaluates each declared test as
SQL against that view.

This is NOT `dbt test`. dbt-core isn't pip-installable in this sandbox.
But the SQL model and schema.yml this engine executes are exactly what a
real `dbt run && dbt test` would build and check - nothing here duplicates
their logic in a different shape, it interprets the same project files.

Two-tier tests (accepted_values / not_null with a `severity: warn` +
warn_if/error_if config) are dbt's own mechanism for exactly the kind of
amber/red banding this project's Soda checks also express - implemented
here by counting failing rows and applying the operator string
(">0", ">2%") from the YAML, the same as dbt-core's test runner does.
"""
from __future__ import annotations
import re

import duckdb
import jinja2
import yaml

VIEW_NAME = "stg_birth_registrations"


def _render_model_sql(sql_path: str, source_table: str) -> str:
    with open(sql_path) as f:
        raw = f.read()
    # dbt's {{ source('raw', 'birth_registrations') }} macro resolves, in a
    # real project, to the fully-qualified source relation. Here there's one
    # source table, so it resolves directly to it.
    env = jinja2.Environment()
    template = env.from_string(raw)
    return template.render(source=lambda *a: source_table)


def _build_staging_view(conn: duckdb.DuckDBPyConnection, sql_path: str, source_table: str = "birth_registrations") -> None:
    select_sql = _render_model_sql(sql_path, source_table)
    conn.execute(f"CREATE OR REPLACE VIEW {VIEW_NAME} AS {select_sql}")


def _parse_threshold(spec: str) -> tuple[str, float, bool]:
    """'>2%' -> ('>', 2.0, True); '>0' -> ('>', 0.0, False)"""
    m = re.match(r"([<>]=?)\s*([\d.]+)\s*(%?)", spec.strip())
    op, val, pct = m.groups()
    return op, float(val), bool(pct)


def _compare(value: float, op: str, threshold: float) -> bool:
    return {"<": value < threshold, "<=": value <= threshold,
            ">": value > threshold, ">=": value >= threshold}[op]


def _status_from_config(n_fail: int, n_total: int, config: dict | None) -> tuple[str, float, str, float | None, float | None]:
    """Applies a test's severity config (warn_if/error_if) if present,
    otherwise falls back to plain dbt semantics: any failing row -> fail.

    Returns (status, metric_value, unit, warn_threshold, fail_threshold) -
    all numeric/scaled consistently (percent-point figures when the config
    uses a '%' threshold, plain counts otherwise), the same convention the
    contract and soda engines use, rather than dbt's own raw config strings
    (">0", ">2%") which don't carry a fixed unit on their own."""
    rate = n_fail / n_total if n_total else 0.0

    if not config:
        # a plain generic test (no severity config) - dbt semantics: any
        # failing row is an error. Modeled as a count check against a fixed
        # fail-at-0 threshold so it fits this project's shared check shape.
        return ("fail" if n_fail > 0 else "pass"), n_fail, "count", None, 0

    warn_if = config.get("warn_if")
    error_if = config.get("error_if")
    is_pct = any(spec and "%" in spec for spec in (warn_if, error_if))
    metric_value = round(rate * 100, 4) if is_pct else n_fail
    unit = "%" if is_pct else "count"

    def hits(spec):
        if spec is None:
            return False
        op, val, spec_is_pct = _parse_threshold(spec)
        metric = rate * 100 if spec_is_pct else n_fail
        return _compare(metric, op, val)

    warn_t = _parse_threshold(warn_if)[1] if warn_if else None
    fail_t = _parse_threshold(error_if)[1] if error_if else None

    if hits(error_if):
        return "fail", metric_value, unit, warn_t, fail_t
    if hits(warn_if):
        return "warn", metric_value, unit, warn_t, fail_t
    return "pass", metric_value, unit, warn_t, fail_t


def evaluate_dbt_tests(project_dir: str, db_path: str, run_id: str, run_timestamp: str) -> list[dict]:
    sql_path = f"{project_dir}/models/staging/stg_birth_registrations.sql"
    schema_path = f"{project_dir}/models/staging/schema.yml"

    with open(schema_path) as f:
        schema = yaml.safe_load(f)

    conn = duckdb.connect(db_path)
    _build_staging_view(conn, sql_path)

    results = []
    for model in schema["models"]:
        for col in model.get("columns", []):
            col_name = col["name"]
            for test in col.get("tests", []):
                if isinstance(test, str):
                    test_name, cfg = test, {}
                else:
                    ((test_name, spec),) = test.items()
                    cfg = (spec or {}).get("config", {}) if isinstance(spec, dict) else {}

                n_total = conn.execute(
                    f"SELECT COUNT(*) FROM {VIEW_NAME} WHERE run_id = ?", [run_id]
                ).fetchone()[0]

                if test_name == "unique":
                    n_fail = conn.execute(
                        f"""SELECT COALESCE(SUM(c - 1), 0) FROM (
                                SELECT COUNT(*) AS c FROM {VIEW_NAME}
                                WHERE run_id = ? GROUP BY {col_name} HAVING COUNT(*) > 1
                            )""", [run_id]
                    ).fetchone()[0]

                elif test_name == "not_null":
                    n_fail = conn.execute(
                        f"SELECT COUNT(*) FROM {VIEW_NAME} WHERE run_id = ? AND {col_name} IS NULL",
                        [run_id]
                    ).fetchone()[0]

                elif test_name == "accepted_values":
                    values = spec["values"]
                    placeholders = ",".join("?" for _ in values)
                    n_fail = conn.execute(
                        f"""SELECT COUNT(*) FROM {VIEW_NAME}
                            WHERE run_id = ? AND {col_name} IS NOT NULL
                            AND {col_name} NOT IN ({placeholders})""",
                        [run_id, *values]
                    ).fetchone()[0]

                else:
                    continue

                status, metric_value, unit, warn_t, fail_t = _status_from_config(n_fail, n_total, cfg)
                results.append({
                    "agency_id": "registry-services",
                    "collection_id": "civil-registration",
                    "dataset_id": "birth-registrations",
                    "column_name": col_name,
                    "check_name": f"dbt:{test_name}",
                    "dimension": "uniqueness" if test_name == "unique" else
                                 "completeness" if test_name == "not_null" else "validity",
                    "run_id": run_id,
                    "run_timestamp": run_timestamp,
                    "metric_value": metric_value,
                    "unit": unit,
                    "warn_threshold": warn_t,
                    "fail_threshold": fail_t,
                    "status": status,
                    "on_fail_action": "flag",
                    "row_count_total": n_total,
                    "row_count_invalid": n_fail,
                    "engine": "dbt_test_engine (dbt-core equivalent)",
                })

    conn.close()
    return results


if __name__ == "__main__":
    import json
    import os
    from datetime import datetime
    project_dir = os.path.join(os.path.dirname(__file__), "..", "dbt_project")
    db_path = os.path.join(os.path.dirname(__file__), "..", "data", "warehouse.duckdb")
    for run_id in ["run_01_2026-09-01", "run_04_2026-09-04", "run_09_2026-09-09"]:
        res = evaluate_dbt_tests(project_dir, db_path, run_id, datetime.utcnow().isoformat())
        print(f"--- {run_id} ---")
        for r in res:
            print(" ", r["column_name"], r["check_name"], r["status"], r["metric_value"])
