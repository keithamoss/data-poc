"""`mothman env tidy-test-databases` drops only the suite's own leftover
databases (Keith, 2026-10-20: "setup something to automatically tidy up old
leftover test databases"). Runs against the real test server."""
from __future__ import annotations

import os
import uuid

import psycopg
import pytest
from click.testing import CliRunner

from cli.app import cli
from cli.env import leftover_test_databases


@pytest.fixture
def admin():
    return os.environ["MOTHMAN_TEST_DSN"]


@pytest.fixture
def made(admin):
    """Databases this test creates, dropped afterwards whatever happened."""
    names = []

    def make(name):
        with psycopg.connect(admin, autocommit=True) as conn:
            conn.execute(f'CREATE DATABASE "{name}"')
        names.append(name)
        return name
    yield make
    with psycopg.connect(admin, autocommit=True) as conn:
        for name in names:
            conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def _exists(admin, name):
    with psycopg.connect(admin, autocommit=True) as conn:
        return conn.execute("SELECT 1 FROM pg_database WHERE datname = %s",
                            [name]).fetchone() is not None


def _tag():
    return uuid.uuid4().hex[:8]


# EVERY CALL THAT DROPS IS NARROWED TO THIS TEST'S OWN NAMES with --prefix:
# with a zero threshold the command would otherwise drop any idle suite
# database on the server, including a concurrent session's.


def test_an_old_unused_test_database_is_dropped(admin, made):
    prefix = f"mothman_test_tidy{_tag()}"
    name = made(f"{prefix}_gw0")
    result = CliRunner().invoke(cli, ["env", "tidy-test-databases", "--older-than-hours", "0",
                                      "--prefix", prefix])
    assert result.exit_code == 0, result.output
    assert not _exists(admin, name)


def test_a_young_test_database_is_kept(admin, made):
    name = made(f"mothman_solo_tidy{_tag()}")
    assert name not in leftover_test_databases(admin, older_than_hours=12)
    CliRunner().invoke(cli, ["env", "tidy-test-databases", "--prefix", name])
    assert _exists(admin, name)


def test_a_database_somebody_is_connected_to_is_kept(admin, made):
    name = made(f"mothman_test_tidy{_tag()}_gw1")
    info = psycopg.conninfo.conninfo_to_dict(admin)
    info["dbname"] = name
    with psycopg.connect(psycopg.conninfo.make_conninfo(**info)):
        assert name not in leftover_test_databases(admin, older_than_hours=0)


def test_a_database_not_named_by_the_suite_is_never_touched(admin, made):
    name = made(f"tidyprobe_{_tag()}")
    old_suite_one = made(f"mothman_test_tidy{_tag()}_gw2")
    got = leftover_test_databases(admin, older_than_hours=0)
    assert old_suite_one in got, "precondition: the listing finds the suite's own"
    assert name not in got
    assert not any(n in ("supply", "postgres") for n in got)


def test_dry_run_drops_nothing(admin, made):
    name = made(f"mothman_test_tidy{_tag()}_gw3")
    result = CliRunner().invoke(cli, ["env", "tidy-test-databases", "--older-than-hours",
                                      "0", "--dry-run", "--prefix", name])
    assert result.exit_code == 0, result.output
    assert name in result.output
    assert _exists(admin, name)


def test_with_no_test_server_it_refuses_and_drops_nothing(admin, made, monkeypatch):
    """REQ-TEST-283 criterion 2: no MOTHMAN_TEST_DSN, nothing to tidy."""
    name = made(f"mothman_test_tidy{_tag()}_gw4")
    monkeypatch.delenv("MOTHMAN_TEST_DSN")
    result = CliRunner().invoke(cli, ["env", "tidy-test-databases", "--older-than-hours", "0",
                                      "--prefix", name])
    assert result.exit_code != 0
    assert "MOTHMAN_TEST_DSN is not set" in result.output
    assert _exists(admin, name)


def test_a_database_somebody_connects_to_after_the_listing_is_kept(admin, made, monkeypatch):
    """REQ-TEST-283 criterion 7: a plain DROP fails on a database somebody
    connected to since the listing, and the command keeps it, names it and
    carries on with the rest. The listing is replaced by one that returns the
    connected database first, which is the state a late connection leaves."""
    prefix = f"mothman_test_tidy{_tag()}"
    busy = made(f"{prefix}_gw5")
    idle = made(f"{prefix}_gw6")
    monkeypatch.setattr("cli.env.leftover_test_databases",
                        lambda *_a, **_k: [busy, idle])
    info = psycopg.conninfo.conninfo_to_dict(admin)
    info["dbname"] = busy
    with psycopg.connect(psycopg.conninfo.make_conninfo(**info)):
        result = CliRunner().invoke(cli, ["env", "tidy-test-databases", "--older-than-hours",
                                          "0", "--prefix", prefix])
        assert result.exit_code == 0, result.output
        assert f"Kept {busy}" in result.output
        assert "Dropped 1 " in result.output
        assert _exists(admin, busy)
    assert not _exists(admin, idle)


def test_a_test_server_that_cannot_be_listed_is_an_error(monkeypatch):
    """REQ-TEST-283 criterion 8: the listing fails, the command exits non-zero
    naming the database error."""
    info = psycopg.conninfo.conninfo_to_dict(os.environ["MOTHMAN_TEST_DSN"])
    info["dbname"] = f"tidy_no_such_db_{_tag()}"
    monkeypatch.setenv("MOTHMAN_TEST_DSN", psycopg.conninfo.make_conninfo(**info))
    result = CliRunner().invoke(cli, ["env", "tidy-test-databases", "--dry-run"])
    assert result.exit_code != 0
    assert "could not list the test databases" in result.output
    assert "does not exist" in result.output
