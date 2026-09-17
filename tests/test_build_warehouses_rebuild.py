"""Covers the "a previous .duckdb file already exists at this path"
rebuild branch in qa_tools/{bdm,cp}/build_*_warehouses.py's build_all() -
every other test that uses the shared bdm_duckdb_dir/cp_duckdb_dir
fixtures (tests/conftest.py) only ever builds into a fresh tmp dir, so
that branch is otherwise never exercised: calling build_all() twice into
the SAME out_dir is the only way to hit it."""
from __future__ import annotations

import os

from qa_tools.bdm.build_per_run_warehouses import build_all as build_all_bdm
from qa_tools.cp.build_cp_warehouses import build_all as build_all_cp


def test_bdm_build_all_rebuilds_an_existing_duckdb_file(tmp_path, bdm_raw_dir):
    out_dir = str(tmp_path / "bdm_duckdb_runs")

    first_paths = build_all_bdm(raw_dir=bdm_raw_dir, out_dir=out_dir)
    assert all(os.path.exists(p) for p in first_paths)

    second_paths = build_all_bdm(raw_dir=bdm_raw_dir, out_dir=out_dir)

    assert second_paths == first_paths
    assert all(os.path.exists(p) for p in second_paths)


def test_cp_build_all_rebuilds_an_existing_duckdb_file(tmp_path, cp_raw_dir):
    out_dir = str(tmp_path / "cp_duckdb_runs")

    first_paths = build_all_cp(raw_dir=cp_raw_dir, out_dir=out_dir)
    assert all(os.path.exists(p) for p in first_paths)

    second_paths = build_all_cp(raw_dir=cp_raw_dir, out_dir=out_dir)

    assert second_paths == first_paths
    assert all(os.path.exists(p) for p in second_paths)
