"""A Soda scan must not repoint this process at another database.

THE BUG THIS GUARDS, found 2026-09-27 by chasing suite flakiness down to
its cause rather than re-running until it passed. Soda Core builds a
singleton `EnvHelper` on its first scan, and that constructor calls
`dotenv.load_dotenv(override=True)` - it walks up from its own file,
finds this repo's `.env`, and writes every name in it over whatever the
process already had. `MOTHMAN_SUPPLY_DSN` is one of those names.

So the first real scan in a process silently moved the warehouse. In the
test suite that meant every test AFTER a Soda test on the same xdist
worker stopped using its own isolated database and started using the
developer's real one: staging tables and run schemas from pytest
fixtures were found sitting in `supply`, and the tests that then looked
for their own data in their own database correctly found nothing. Which
test failed depended on how xdist happened to distribute the files, so
the suite failed differently on every run - eight tests, then four, then
one - and every one of them passed in isolation.

IT IS NOT A TEST-ONLY PROBLEM, which is why the fix is in the production
helper rather than in a fixture. `MOTHMAN_SUPPLY_DSN=... mothman
pipeline run` is a legitimate thing for an operator to type, and before
this fix the first Soda scan of that run discarded it in favour of
whatever `.env` said. A pipeline that quietly writes to a different
database than the one it was told to is the same class of fault as the
CI rule about never reaching real data.

THE ASSERTION IS THE OUTCOME, not Soda's internals: a scan leaves the
environment exactly as it found it. That stays checkable if a future
Soda release drops the dotenv reload, moves it, or renames the helper.
"""
from __future__ import annotations

import os

import pytest
from soda.scan import Scan

from qa_tools.common import supply_db
from qa_tools.common.soda_common import execute_scan

PROBE_TABLE = "soda_env_probe"


class _ScanThatRewritesTheEnvironment:
    """Stands in for Soda's own dotenv reload.

    A STUB RATHER THAN THE REAL LIBRARY for the one assertion that has
    to hold everywhere. The real reload only changes anything when a
    `.env` exists beside this repo, and `.env` is gitignored - so on a
    freshly-cloned CI runner the real-scan test below is trivially true
    and would not have caught this. This one reproduces the failure
    whether or not the file is there, which is what a regression test
    for it has to do (CLAUDE.md's own note about tests that assert on
    gitignored paths).
    """

    def __init__(self):
        self.executed = False

    def execute(self):
        self.executed = True
        os.environ[supply_db.SUPPLY_DSN_ENV] = "postgresql://somewhere/else"
        os.environ["MOTHMAN_SCAN_INVENTED_THIS"] = "1"
        os.environ.pop("MOTHMAN_SCAN_DELETED_THIS", None)

    def get_scan_results(self):
        return {"checks": []}


def test_a_scan_cannot_repoint_the_warehouse(monkeypatch):
    monkeypatch.setenv(supply_db.SUPPLY_DSN_ENV, "postgresql://ours/supply")
    monkeypatch.setenv("MOTHMAN_SCAN_DELETED_THIS", "kept")
    monkeypatch.delenv("MOTHMAN_SCAN_INVENTED_THIS", raising=False)

    scan = _ScanThatRewritesTheEnvironment()
    execute_scan(scan)

    assert scan.executed, "the helper must actually run the scan"
    assert os.environ[supply_db.SUPPLY_DSN_ENV] == "postgresql://ours/supply", \
        "a scan repointed the warehouse at another database"
    assert "MOTHMAN_SCAN_INVENTED_THIS" not in os.environ, \
        "a scan left a variable behind that nothing in this process set"
    assert os.environ["MOTHMAN_SCAN_DELETED_THIS"] == "kept", \
        "a scan removed a variable this process had set"


def test_the_environment_is_restored_even_when_the_scan_raises(monkeypatch):
    """The case nobody is watching, and the same reasoning that put
    close_scan_connections() in a `finally`."""
    monkeypatch.setenv(supply_db.SUPPLY_DSN_ENV, "postgresql://ours/supply")

    class _Boom(_ScanThatRewritesTheEnvironment):
        def execute(self):
            super().execute()
            raise RuntimeError("the scan blew up")

    with pytest.raises(RuntimeError):
        execute_scan(_Boom())

    assert os.environ[supply_db.SUPPLY_DSN_ENV] == "postgresql://ours/supply"


def test_the_helper_returns_the_scan_results(monkeypatch):
    monkeypatch.setenv(supply_db.SUPPLY_DSN_ENV, "postgresql://ours/supply")
    assert execute_scan(_ScanThatRewritesTheEnvironment()) == {"checks": []}


def test_a_real_scan_leaves_the_environment_alone(supply_dsn):
    """The same invariant against the real library.

    TRIVIALLY TRUE WITHOUT A `.env` - there is nothing for Soda to load
    on a freshly-cloned runner - and that is why the stub tests above
    exist as well. Here it is the end-to-end statement: whatever this
    developer's own `.env` says, a real scan does not impose it.
    """
    with supply_db.connect(label="test-setup") as conn:
        supply_db.ensure_schemas(conn)
        conn.execute(
            f'CREATE TABLE IF NOT EXISTS "{supply_db.STAGING_SCHEMA}".{PROBE_TABLE} (id integer)')

    before = dict(os.environ)

    scan = Scan()
    scan.set_data_source_name("probe")
    scan.add_configuration_yaml_str(
        supply_db.soda_config_yaml("probe", supply_db.STAGING_SCHEMA))
    scan.disable_telemetry()
    scan.add_sodacl_yaml_str(f"checks for {PROBE_TABLE}:\n  - row_count >= 0\n")
    execute_scan(scan)

    assert dict(os.environ) == before, \
        "a real Soda scan changed this process's environment"
    assert supply_db.supply_db_dsn() == supply_dsn, \
        "a real Soda scan repointed the warehouse away from this worker's database"
