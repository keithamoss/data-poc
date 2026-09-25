"""Covers the "this arrival has already been staged" branch in
qa_tools/{bdm,cp}/build_*_warehouses.py's build_all().

Every other test that uses the shared bdm_duckdb_dir/cp_duckdb_dir
fixtures (tests/conftest.py) stages into a fresh database, so that
branch is otherwise never exercised: calling build_all() twice against
the SAME supply database is the only way to hit it.

WHAT "REBUILD" MEANS NOW, and the distinction is the whole point of
REQ-PIPE-068's staging rule. A staged table's physical name carries the
arrival it holds, so staging the same arrival twice replaces that one
table and loses nothing - which is what makes a re-run idempotent. It
is NOT the overwrite the design forbids: that would be a second,
different arrival replacing the first under one shared name, which is
what the retired per-run builders' `CREATE OR REPLACE TABLE
raw.<table>` did.
"""
from __future__ import annotations

from qa_tools.bdm.build_per_run_warehouses import build_all as build_all_bdm
from qa_tools.common import supply_db
from qa_tools.cp.build_cp_warehouses import build_all as build_all_cp


def _staged(db_path, logical):
    conn = supply_db.connect(read_only=True, path=db_path)
    try:
        return sorted(supply_db.candidates_in(
            conn, supply_db.STAGING_SCHEMA, [logical])[logical])
    finally:
        conn.close()


def test_bdm_build_all_restages_an_arrival_it_has_already_seen(bdm_duckdb_dir, bdm_raw_dir):
    first = build_all_bdm(raw_dir=bdm_raw_dir)
    before = _staged(bdm_duckdb_dir, "birth_registrations")
    assert before, "the fixture staged nothing at all"

    second = build_all_bdm(raw_dir=bdm_raw_dir)

    assert second == first
    assert _staged(bdm_duckdb_dir, "birth_registrations") == before, \
        "re-staging the same arrivals must not leave a second copy of any of them"


def test_cp_build_all_restages_an_arrival_it_has_already_seen(cp_duckdb_dir, cp_raw_dir):
    first = build_all_cp(raw_dir=cp_raw_dir)
    before = _staged(cp_duckdb_dir, "cp_clients")
    assert before, "the fixture staged nothing at all"

    second = build_all_cp(raw_dir=cp_raw_dir)

    assert second == first
    assert _staged(cp_duckdb_dir, "cp_clients") == before
