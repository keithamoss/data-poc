"""A dbt build that did not run must not be read as if it had.

THE DEFECT, found 2026-09-27 while chasing the residual suite flakiness
the Soda dotenv fix left behind. `run_dbt()` invoked dbt with
`check=False, capture_output=True` and then returned, discarding both
the exit code and everything dbt had said. `check=False` is correct on
its own terms - `dbt build` exits non-zero when a TEST FAILS, which is
an ordinary outcome this pipeline exists to record - but discarding the
outcome entirely is not: a build that failed to compile, could not
reach the database, or errored on a model returned exactly like a build
that worked.

WHY THAT IS WORSE THAN A CRASH. `target_path` is per-run and PERSISTS,
so a failed build leaves the PREVIOUS build's `manifest.json` and
`run_results.json` sitting there. The caller reads them and reports
that run's results as this run's - a false green, produced by a build
that never happened. The flaky symptom that led here ("relation
stg_birth_registrations does not exist", and a dirty run reporting no
failures at all) is the same fault showing its other face: sometimes
there is no previous output to read, so it surfaces as a confusing
error several frames away from the build that actually failed.

THE LINE THIS DRAWS, and it is the part that takes care: a FAILED TEST
is not an error, an ERRORED NODE is. dbt's exit code cannot separate
them - `dbt build` returns 1 for both - so the decision is made from
`run_results.json`, where a test that failed carries status `fail` and
a node that could not run carries status `error`. Anything that stops
dbt producing `run_results.json` at all is an error by definition.
"""
from __future__ import annotations

import json
import os

import pytest

from qa_tools.common import dbt_common, supply_db

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILES_DIR = os.path.join(ROOT, "qa_tools", "dbt_profiles")
DBT_PROJECT_DIR = os.path.join(ROOT, "dbt_project")


def _target(tmp_path):
    return str(tmp_path / "target")


#: A run with no view schema in the database, which is precisely the
#: state the flake this came from produced: dbt's source resolves to a
#: schema that is not there, the model errors, and every later read of
#: `stg_birth_registrations` fails several frames away from the cause.
#: Deliberately NOT a bad selector - dbt treats "nothing matched" as a
#: warning and exits 0, which is a different thing and correctly not an
#: error here.
_NO_SUCH_RUN = "run_that_was_never_staged"


def _build_against_a_missing_schema(target):
    dbt_common.run_dbt("build", ["stg_birth_registrations"], target,
                        PROFILES_DIR, DBT_PROJECT_DIR, ROOT,
                        run_schema=supply_db.run_schema(_NO_SUCH_RUN),
                        run_id=_NO_SUCH_RUN)


def test_a_build_that_cannot_run_raises_rather_than_returning(tmp_path, supply_dsn):
    with pytest.raises(dbt_common.DbtRunFailed):
        _build_against_a_missing_schema(_target(tmp_path))


def test_the_error_carries_what_dbt_said(tmp_path, supply_dsn):
    """A traceback that does not include dbt's own message sends the
    reader to the wrong place - which is exactly what made the flake
    this came from take three full suite runs to pin down."""
    with pytest.raises(dbt_common.DbtRunFailed) as exc:
        _build_against_a_missing_schema(_target(tmp_path))
    message = str(exc.value)
    assert "dbt" in message.lower()
    assert len(message) > 40, f"the error says almost nothing: {message!r}"


def test_a_stale_run_results_from_an_earlier_build_is_not_read_as_this_one(tmp_path, supply_dsn):
    """The false-green shape, pinned. A previous build's output sitting
    in the per-run target_path must not survive a failed build as if it
    were this build's."""
    target = _target(tmp_path)
    os.makedirs(target, exist_ok=True)
    stale = {"results": [{"unique_id": "test.stale", "status": "pass"}]}
    with open(os.path.join(target, "run_results.json"), "w") as f:
        json.dump(stale, f)

    with pytest.raises(dbt_common.DbtRunFailed):
        _build_against_a_missing_schema(target)

    with open(os.path.join(target, "run_results.json")) as f:
        after = json.load(f)["results"]
    assert not any(r.get("unique_id") == "test.stale" for r in after), \
        "the previous build's results survived a failed build"


def test_a_real_test_failure_is_not_an_error(tmp_path, supply_dsn, bdm_duckdb_dir):
    """The other side of the line, and the reason `check=True` is wrong
    here. A dbt build whose TESTS fail is the ordinary case this whole
    pipeline exists to record, and it must come back normally so the
    caller can parse the failures.
    """
    from fixture_ids import BDM_DIRTY_RUN_ID

    target = str(supply_db.dbt_target_path(BDM_DIRTY_RUN_ID))
    dbt_common.run_dbt("build", ["stg_birth_registrations"], target,
                        PROFILES_DIR, DBT_PROJECT_DIR, ROOT,
                        run_schema=supply_db.run_schema(BDM_DIRTY_RUN_ID),
                        run_id=BDM_DIRTY_RUN_ID)

    with open(os.path.join(target, "run_results.json")) as f:
        results = json.load(f)["results"]
    assert results, "the build produced no results at all"
    assert not [r for r in results if r["status"] == "error"], \
        "this fixture is meant to produce test failures, not errored nodes"
