"""A finished Soda scan must leave no PostgreSQL backend behind.

THE BUG THIS GUARDS, found 2026-09-27 by reproducing a real hang rather
than by reading code. `Scan.execute()` ends by calling `self._close()`,
which calls `DataSourceManager.close_all_connections()`, which iterates
`manager.connections` - and that dict is EMPTY on this code path. The
live connection is held on `manager.data_sources[name].connection`, so
Soda's own teardown closes nothing and every scan leaks one backend.

WHY IT MATTERED. Soda's connection is not autocommit, so the leaked
backend sits `idle in transaction` holding ACCESS SHARE on everything
the scan read. The orchestrator's `DROP SCHEMA ... CASCADE` needs
ACCESS EXCLUSIVE, so it queued behind that lock and failed with a lock
timeout after thirty seconds. PostgreSQL's own lock-wait log named the
pair; the fix is qa_tools.common.soda_common.close_scan_connections().

THESE TESTS ASSERT THE OUTCOME, NOT THE MECHANISM, deliberately. The fix
reaches into a private attribute because the public API does not work,
so the thing worth pinning is "a completed scan leaves no open backend"
- which stays true and stays checkable if a future Soda release fixes
this, moves it, or renames it.
"""
from __future__ import annotations

import psycopg
import pytest
from soda.scan import Scan

from qa_tools.common import supply_db
from qa_tools.common.soda_common import close_scan_connections


def _unlabelled_backends(dsn: str) -> int:
    """Backends with no application_name - which every connection this
    project opens now sets (supply_db.connect), and dbt sets for itself.
    So an unlabelled one is a tool's, and after a scan there should be
    none of them."""
    with psycopg.connect(dsn, autocommit=True, application_name="test-probe") as conn:
        return conn.execute(
            "SELECT count(*) FROM pg_stat_activity "
            "WHERE datname = current_database() "
            "AND coalesce(application_name, '') = ''").fetchone()[0]


def _scan(schema: str) -> Scan:
    scan = Scan()
    scan.set_data_source_name("probe")
    scan.add_configuration_yaml_str(supply_db.soda_config_yaml("probe", schema))
    scan.disable_telemetry()
    # A check that runs and resolves against any schema, since what is
    # under test is the CONNECTION rather than the check's own verdict.
    scan.add_sodacl_yaml_str("checks for not_a_real_table:\n  - row_count > -1\n")
    return scan


@pytest.fixture
def dsn(supply_dsn):
    return supply_dsn


def test_a_scan_on_its_own_leaks_exactly_one_backend(dsn):
    """The bug itself, pinned. If a future Soda release fixes this, this
    test fails and close_scan_connections() can be deleted - which is a
    better outcome than carrying a workaround nobody re-examines."""
    before = _unlabelled_backends(dsn)
    scan = _scan(supply_db.STAGING_SCHEMA)
    scan.execute()
    assert _unlabelled_backends(dsn) == before + 1, (
        "Soda no longer leaks its connection - close_scan_connections() "
        "may now be unnecessary; check before deleting it")
    close_scan_connections(scan)


def test_closing_the_scan_releases_it(dsn):
    before = _unlabelled_backends(dsn)
    scan = _scan(supply_db.STAGING_SCHEMA)
    scan.execute()
    assert close_scan_connections(scan) == 1
    assert _unlabelled_backends(dsn) == before, \
        "a completed and closed scan must leave no backend behind"


def test_closing_twice_is_harmless(dsn):
    """The orchestrator closes in a finally; a caller that also closes
    explicitly must not be punished for it."""
    scan = _scan(supply_db.STAGING_SCHEMA)
    scan.execute()
    assert close_scan_connections(scan) == 1
    assert close_scan_connections(scan) == 0


def test_closing_a_scan_that_never_ran_is_harmless(dsn):
    """An exception before execute() still reaches the finally."""
    assert close_scan_connections(_scan(supply_db.STAGING_SCHEMA)) == 0
