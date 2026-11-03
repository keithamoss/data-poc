"""A module's own fixtures survive its first test's asset switch (#307).

The worker's database is emptied when a test acts for another asset than the
last one (tests/conftest.py, _mark_worker_db_for). That switch ran per TEST,
after a module-scoped fixture had already built what the module reads - so a
module of the daily asset, first on a worker that started quarterly, lost its
fixture's work before its first test: tests/test_run_dbt_bdm.py, run alone,
failed with qa.carried_check missing, and passed only beside a module that had
switched the worker first. The module's asset is now selected before its
module-scoped fixtures run."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.asset("daily")


@pytest.fixture(scope="module")
def built_by_the_module(supply_dsn):
    from qa_tools.common import qa_store, supply_db

    with supply_db.connect(label="pytest:module-fixture") as conn:
        qa_store.ensure_schema(conn)
        conn.execute('CREATE SCHEMA IF NOT EXISTS "module_fixture_probe"')
    return True


def test_what_the_module_fixture_built_is_still_there(built_by_the_module):
    from qa_tools.common import supply_db

    with supply_db.connect(read_only=True, label="pytest:probe") as conn:
        found = {r[0] for r in conn.execute(
            "SELECT nspname FROM pg_namespace WHERE nspname IN ('module_fixture_probe', 'qa')").fetchall()}
    assert found == {"module_fixture_probe", "qa"}
