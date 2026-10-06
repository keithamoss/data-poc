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

# dbt-postgres since REQ-PIPE-087 (post-build-review #124: the tag still
# named the retired DuckDB adapter). The builders map both spellings, so a
# result recorded under the old one still reads as dbt-core.
ENGINE_TAG = "dbt-core 1.12 + dbt-postgres"

# Matches datacontract-cli's own hardcoded sample cap - see
# datacontract_common.py and plans/qa-pipeline.md #15.
FAILING_SAMPLE_LIMIT = 5

_NUM_RE = re.compile(r"([\d.]+)")


class DbtRunFailed(RuntimeError):
    """A `dbt` invocation did not produce a result worth reading.

    NOT RAISED FOR A FAILING TEST, which is the distinction the whole
    class exists to draw - see run_dbt()'s own docstring.
    """


def parse_threshold(spec: str | None) -> float | None:
    if spec is None or spec.strip() == "!= 0":
        return None
    m = _NUM_RE.search(spec)
    return float(m.group(1)) if m else None


def run_dbt(command: str, select: list[str], target_path: str,
            profiles_dir: str, project_dir: str, root: str,
            run_schema: str | None = None, run_id: str | None = None,
            exclude: list[str] | None = None) -> None:
    """Run dbt against the one PostgreSQL database.

    `db_path` IS GONE from this signature (REQ-PIPE-087). It used to name
    dbt's own scratch DuckDB file, which existed because dbt writes and
    DuckDB gives a writer an exclusive lock over the whole file while
    these calls fan out over a process pool.

    `run_id` REPLACED IT, and the correction is worth stating because
    the first version of this docstring got it wrong. It said
    PostgreSQL "has no such contention, so dbt writes into its own
    schema in the same database" - true about the FILE LOCK, wrong about
    what the per-run file was really buying. Two runs writing one
    schema race on the TABLES: `dbt build` drops and recreates its
    models, so one run reads `stg_birth_registrations` while another
    rebuilds it and gets "relation does not exist". So the schema is
    per-run now, exactly as target_path already was.

    `run_schema` is unchanged and still load-bearing: it is the view
    schema this run's sources resolve through, so a bare table name in a
    model or a checks file means exactly one arrival's rows.

    `exclude` IS DBT'S OWN GRAPH SELECTOR, and it has to be, which is
    the one place this module departs from its explicit-node-list rule
    (REQ-PIPE-078 criterion 9). Dropping an unreadable model from
    `--select` is not enough: `dbt build` runs every test that DEPENDS
    on a selected node, so a relationships test declared on a readable
    model still runs and still errors on the table it references. Only
    `stg_x+` - the node and everything downstream of it - takes the
    dependents with it, and dbt is the only thing that knows what they
    are. Excluding by hand would mean this project maintaining its own
    copy of the DAG.
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
    # PER RUN. Without a run_id there is no isolation to give, so this
    # refuses rather than silently sharing one schema again - which is
    # the bug this parameter exists to prevent.
    if not run_id:
        raise ValueError(
            "run_dbt needs a run_id: dbt's schema is per-run, and sharing one "
            "lets concurrent runs drop each other's models mid-read")
    env["DBT_PG_SCHEMA"] = supply_db.dbt_schema(run_id)
    if run_schema:
        env["DBT_RUN_SCHEMA"] = run_schema
    env["DBT_SEND_ANONYMOUS_USAGE_STATS"] = "False"
    # STALE OUTPUT IS REMOVED BEFORE THE RUN, not trusted after it.
    # target_path is per-run and persists, so a build that fails early
    # leaves the PREVIOUS build's run_results.json in place and the
    # caller reads that run's results as this run's - a false green
    # produced by a build that never happened.
    for artefact in ("run_results.json", "manifest.json"):
        try:
            os.remove(os.path.join(target_path, artefact))
        except FileNotFoundError:
            pass
    completed = subprocess.run(
        # --target-path gives each run its OWN target/ subdirectory rather
        # than dbt's shared default - required for cross-run
        # parallelization (plans/performance.md #4): without this,
        # concurrent `dbt build` calls for different runs clobber each
        # other's manifest.json/run_results.json mid-write. Always applied
        # (not just under parallel execution) since it's strictly safer
        # and free even sequentially - one run's target/ never lingers to
        # confuse the next.
        # --store-failures writes each failing test's own offending rows
        # into a <target>_audit.<test> table (dbt_project.yml) in the same per-run
        # warehouse - the source failing_sample_keys_* below query for
        # per-row samples (see plans/qa-pipeline.md #15).
        ["dbt", command, "--profiles-dir", profiles_dir, "--project-dir", project_dir, "--quiet",
         "--target-path", target_path, "--select", *select,
         *(("--exclude", *exclude) if exclude else ()), "--store-failures"],
        env=env, cwd=root, check=False, capture_output=True, text=True,
    )
    _refuse_a_build_that_did_not_run(completed, target_path)


def _refuse_a_build_that_did_not_run(completed, target_path: str) -> None:
    """Raise unless dbt produced results this caller can honestly read.

    `check=True` WOULD BE WRONG, and that is the whole difficulty: dbt
    exits non-zero when a TEST FAILS, which is the ordinary outcome
    this pipeline exists to record. The exit code cannot tell a failing
    test from a model that could not run - `dbt build` returns 1 for
    both - so the decision comes from run_results.json instead, where a
    failing test carries status `fail` and a node that could not run
    carries status `error`.

    NO run_results.json AT ALL is the unambiguous case: dbt did not get
    far enough to have an opinion, so there is nothing to parse and the
    caller must not pretend otherwise.
    """
    import json

    said = "\n".join(part.strip() for part in (completed.stdout, completed.stderr) if part and part.strip())
    results_path = os.path.join(target_path, "run_results.json")
    if not os.path.exists(results_path):
        raise DbtRunFailed(
            f"dbt exited {completed.returncode} without writing run_results.json, so "
            f"this build produced nothing to read. dbt said:\n{said or '(nothing at all)'}")
    try:
        with open(results_path) as f:
            results = json.load(f)["results"]
    except (ValueError, KeyError, OSError) as exc:
        raise DbtRunFailed(
            f"dbt wrote a run_results.json this cannot read ({type(exc).__name__}: {exc}). "
            f"dbt said:\n{said or '(nothing at all)'}") from exc
    errored = [r for r in results if r.get("status") == "error"]
    if errored:
        names = ", ".join(sorted(r.get("unique_id", "?") for r in errored))
        first = next((r.get("message") for r in errored if r.get("message")), "")
        raise DbtRunFailed(
            f"dbt could not run {len(errored)} node(s): {names}. "
            f"A failing TEST is an ordinary result and does not come through here; an "
            f"errored node means the build itself did not happen. "
            f"{first}\ndbt said:\n{said or '(nothing at all)'}")


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


#: The prefix every staging model's name carries over its table's.
MODEL_PREFIX = "stg_"


class NothingLeftToBuild(Exception):
    """Every model this run would build reads a table it cannot read.

    ITS OWN EXCEPTION RATHER THAN AN EMPTY SELECT LIST, because `dbt
    build` with no `--select` builds the WHOLE PROJECT - so the failure
    mode of getting this wrong is not "nothing runs", it is "every
    other collection's models run against this run's schema". A caller
    catches this and records no dbt results for the run.
    """


def exclude_unreadable(*, models, unreadable):
    """`--exclude` arguments for the tables this run cannot read, or
    raise where that would leave nothing.

    WHY THIS EXISTS, and it is a real defect rather than a refinement
    (found 2026-09-30 building REQ-PIPE-078 criteria 9 and 10). A held
    supply gets no view, which is how "a held supply is not checked"
    has been enforced by construction since REQ-PIPE-059. But dbt was
    asked to build a FIXED list of models, so the model over the
    missing view ERRORED - and an errored node is not a failing test,
    it takes the whole run down through the orchestrator's `_run_step`.
    One dataset nobody could place cost the other five their QA, which
    is the exact opposite of what REQ-PIPE-059 criterion 7 promises.

    It had never been caught because no hold had ever occurred in the
    corpus, so the path had never run.

    `stg_x+` RATHER THAN A FILTERED SELECT LIST, and the first attempt
    at this got it wrong in a way worth recording: dropping the model
    from `--select` left four nodes still erroring, because `dbt build`
    runs every test DEPENDING on a selected node. Three were
    relationships tests declared on readable models that reference the
    unreadable one, and the fourth was a cross-table singular test. The
    `+` suffix is what takes the dependents with it, and dbt is the
    only thing that knows what they are.
    """
    withheld = frozenset(unreadable)
    if not withheld:
        return []
    remaining = [m for m in models if _table_of_model(m) not in withheld]
    if not remaining:
        raise NothingLeftToBuild(
            f"every model this run would build reads a table it cannot read "
            f"({', '.join(sorted(withheld))}), so there is nothing for dbt to "
            f"do. Recording no dbt results rather than letting an empty "
            f"--select build the whole project.")
    return [f"{MODEL_PREFIX}{table}+" for table in sorted(withheld)]


def _table_of_model(model: str) -> str:
    return model[len(MODEL_PREFIX):] if model.startswith(MODEL_PREFIX) else model
