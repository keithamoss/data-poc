"""
Tool-generic dbt-core invocation and manifest-parsing helpers, shared by
qa_tools/bdm/run_dbt_bdm.py and qa_tools/cp/run_dbt_cp.py.
The actual test-to-dashboard-field mapping (which tests exist, what
dimension/label each one gets, any tool-reliability workarounds a
dataset needed) is genuinely different per dataset and stays in each
dataset's own file - only the subprocess invocation and
manifest.json/run_results.json parsing plumbing that's identical across
datasets lives here. Split out once a second dataset (Child Protection)
confirmed the same ~30-40 lines really were identical, rather than
guessed in advance - see plans/qa-pipeline.md #84.
"""
from __future__ import annotations
import os
import re
import subprocess


from qa_tools.common import supply_db

ENGINE_TAG = "dbt-core 1.12 + dbt-duckdb"

# Matches datacontract-cli's own hardcoded sample cap - see
# datacontract_common.py and plans/qa-pipeline.md #15.
FAILING_SAMPLE_LIMIT = 5

_NUM_RE = re.compile(r"([\d.]+)")


def parse_threshold(spec: str | None) -> float | None:
    if spec is None or spec.strip() == "!= 0":
        return None
    m = _NUM_RE.search(spec)
    return float(m.group(1)) if m else None


def run_dbt(command: str, select: list[str], target_path: str,
            profiles_dir: str, project_dir: str, root: str,
            run_schema: str | None = None) -> None:
    """Run dbt against the one PostgreSQL database.

    `db_path` IS GONE from this signature (REQ-PIPE-087). It used to name
    dbt's own scratch DuckDB file, which existed because dbt writes and
    DuckDB gives a writer an exclusive lock over the whole file while
    these calls fan out over a process pool. PostgreSQL has no such
    contention, so dbt writes into its own schema in the same database
    and there is no second database to name.

    `run_schema` is unchanged and still load-bearing: it is the view
    schema this run's sources resolve through, so a bare table name in a
    model or a checks file means exactly one arrival's rows.
    """
    env = dict(os.environ)
    # PARSED WITH psycopg's OWN conninfo PARSER, not a regex. dbt-postgres
    # wants discrete host/port/user/dbname fields and this project holds
    # one DSN, and the three forms that DSN legitimately takes - a URL, a
    # keyword string, and a unix socket as `?host=/tmp` - are exactly
    # where a hand-rolled parser gets one wrong.
    fields = supply_db.connection_fields()
    env["DBT_PG_HOST"] = fields["host"]
    env["DBT_PG_PORT"] = fields["port"]
    env["DBT_PG_USER"] = fields["user"]
    env["DBT_PG_PASSWORD"] = fields["password"]
    env["DBT_PG_DBNAME"] = fields["dbname"]
    env["DBT_PG_SCHEMA"] = supply_db.DBT_SCHEMA
    if run_schema:
        env["DBT_RUN_SCHEMA"] = run_schema
    env["DBT_SEND_ANONYMOUS_USAGE_STATS"] = "False"
    subprocess.run(
        # --target-path gives each run its OWN target/ subdirectory rather
        # than dbt's shared default - required for cross-run
        # parallelization (plans/performance.md #4): without this,
        # concurrent `dbt build` calls for different runs clobber each
        # other's manifest.json/run_results.json mid-write. Always applied
        # (not just under parallel execution) since it's strictly safer
        # and free even sequentially - one run's target/ never lingers to
        # confuse the next.
        # --store-failures writes each failing test's own offending rows
        # into a main_dbt_test__audit.<test> table in the same per-run
        # warehouse - the source failing_sample_keys_* below query for
        # per-row samples (see plans/qa-pipeline.md #15).
        ["dbt", command, "--profiles-dir", profiles_dir, "--project-dir", project_dir, "--quiet",
         "--target-path", target_path, "--select", *select, "--store-failures"],
        env=env, cwd=root, check=False, capture_output=True, text=True,
    )


def test_nodes(manifest: dict) -> dict[str, dict]:
    return {
        uid: node for uid, node in manifest["nodes"].items()
        if node.get("resource_type") == "test"
    }


def failing_sample_keys_direct(conn, relation_name: str, pk_column: str,
                                limit: int = FAILING_SAMPLE_LIMIT) -> list[str]:
    """For test shapes whose --store-failures audit table already carries
    the model's own primary key column verbatim (not_null - the whole
    failing row; the singular tests that already select their home
    table's PK directly) - just read it straight out.
    relation_name comes from the test's own manifest node (already
    fully-qualified/quoted for this warehouse), not constructed by hand."""
    try:
        rows = conn.execute(f"SELECT {pk_column} FROM {relation_name} LIMIT {limit}").fetchall()
    except Exception:
        return []
    return [str(r[0]) for r in rows if r[0] is not None]


def failing_sample_keys_via_values(conn, relation_name: str, value_column: str,
                                    model: str, filter_column: str, pk_column: str,
                                    limit: int = FAILING_SAMPLE_LIMIT) -> list[str]:
    """For test shapes whose audit table is pre-aggregated to the
    offending VALUE, not the failing row (accepted_values' `value_field`,
    unique's `unique_field`, both grouped-by-value + a count) - resolves
    back to real failing rows' own primary keys via one follow-up query
    against the model itself, keyed on those values."""
    try:
        rows = conn.execute(
            f"SELECT {pk_column} FROM {model} WHERE {filter_column} "
            f"IN (SELECT {value_column} FROM {relation_name}) LIMIT {limit}"
        ).fetchall()
    except Exception:
        return []
    return [str(r[0]) for r in rows if r[0] is not None]
