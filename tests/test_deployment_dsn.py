"""Where the deployment half finds each asset's deployment database
(post-build-review #334, the critic's H1).

A session started by the session hook exports MOTHMAN_PG and no
MOTHMAN_SUPPLY_DSN (Keith, 2026-11-15), so the deployment database of an
asset is supply_<asset> on MOTHMAN_PG's server - the lookup every command
makes. Recording only MOTHMAN_SUPPLY_DSN made every deployment test SKIP
there, which is a green that proves nothing.
"""
from __future__ import annotations

import os

import psycopg
import pytest

import conftest
from qa_tools.common import supply_db


@pytest.fixture
def scratch_asset_database(supply_dsn, worker_id, monkeypatch):
    """supply_<a scratch asset name> on the test server - never a real one -
    and the session's recorded deployment details cleared for the test."""
    admin = os.environ["MOTHMAN_TEST_DSN"]
    asset = f"fu_probe_{worker_id}"
    name = f"supply_{asset}"
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{name}"')
    info = psycopg.conninfo.conninfo_to_dict(admin)
    server = (f"postgresql://{info['user']}:{info.get('password', '')}@"
              f"{info.get('host', 'localhost')}:{info.get('port', 5432)}")
    monkeypatch.setattr(conftest, "_DEPLOYMENT_BY_ASSET", {})
    monkeypatch.setitem(vars(conftest), "DEPLOYMENT_SUPPLY_DSN", None)
    yield asset, name, server
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def test_with_only_a_server_it_is_the_assets_database_there(scratch_asset_database,
                                                             monkeypatch):
    asset, name, server = scratch_asset_database
    monkeypatch.setitem(vars(conftest), "DEPLOYMENT_SERVER", server)
    found = conftest.deployment_dsn_for(asset)
    assert found == supply_db.on_server(server, name)
    assert psycopg.conninfo.conninfo_to_dict(found)["dbname"] == name


def test_with_neither_there_is_none(scratch_asset_database, monkeypatch):
    asset, _name, _server = scratch_asset_database
    monkeypatch.setitem(vars(conftest), "DEPLOYMENT_SERVER", None)
    assert conftest.deployment_dsn_for(asset) is None


def test_a_server_without_the_assets_database_is_none(scratch_asset_database, monkeypatch):
    _asset, _name, server = scratch_asset_database
    monkeypatch.setitem(vars(conftest), "DEPLOYMENT_SERVER", server)
    assert conftest.deployment_dsn_for("no_such_asset_here") is None


#: The data asset this module's tests act for (C11).
pytestmark = pytest.mark.asset("quarterly")
