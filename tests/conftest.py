"""Shared pytest fixtures for real-tool integration tests (Phase 6,
plans/publishing-and-history.md): qa_tools/{bdm,cp}/run_{dbt,soda,
datacontract,evidently}_*.py's actual output-PARSING logic had zero
test coverage before this - the one test that touches orchestrate_
bdm.py/orchestrate_cp.py (tests/test_orchestrate_reference_run.py)
deliberately monkeypatches every one of these functions out, correctly
for that test's own narrow purpose (checking reference-run forwarding),
but with the side effect that the real "turn this tool's actual output
into our check-result shape" logic was never exercised under pytest at
all - only a full, slow `./run_pipeline.sh` run ever called it.

These fixtures build small, REAL, session-scoped BDM/CP data (real
generator output, real per-run DuckDB warehouses, via this project's
own real loading code) once per test session, so every real-tool test
that uses them doesn't pay the cost of rebuilding from scratch - the
real per-tool invocations (dbt build/soda scan/datacontract-cli/
Evidently) still each pay their own real, unavoidable startup cost,
since genuinely testing "does this correctly parse the real tool's
real output" requires actually running the real tool."""
from __future__ import annotations

import json
import os
from datetime import date

import pytest

from generator.daily_batch import generate_daily_batch
from generator.dirty import apply_birth_registrations_presets


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    """pytest-playwright's own launch-args fixture, extended with the
    same PLAYWRIGHT_CHROMIUM_PATH escape hatch dashboard/
    check_dashboard_renders.py already uses - some sandboxed dev
    environments pre-install a version-pinned Chromium at a fixed path
    that Playwright's own default channel/download lookup won't find.
    Unset everywhere else (a real contributor machine or CI runner,
    both of which run `uv run playwright install chromium` per
    pyproject.toml's dev dependency group), so this is a no-op there."""
    chromium_path = os.environ.get("PLAYWRIGHT_CHROMIUM_PATH")
    if not chromium_path:
        return browser_type_launch_args
    return {**browser_type_launch_args, "executable_path": chromium_path}

# Real, calibrated defect injection (generator/dirty.py's own "severity:
# 'amber' or 'red' - matches the warn/fail bands ... exactly" contract)
# plus a deliberately much smaller row count than the reference run -
# both real, deterministic ways to force at least one genuine fail/warn
# status out of each of the 4 real tools without hand-crafting fixture
# rows that don't reflect what the real generator actually produces.
_REF_RUN_ID = "pytest_bdm_ref"
_DIRTY_RUN_ID = "pytest_bdm_dirty"


@pytest.fixture(scope="session")
def bdm_raw_dir(tmp_path_factory):
    """A tiny (relative to real production volume), real data/raw/-
    shaped directory: two runs, a clean reference (600 rows - comfortably
    clear of the real Soda row_count check's own 500-row warn floor,
    contract/bdm-birth-registrations-soda-checks.yml - a fixture much
    smaller than that would trip a real check for being implausibly
    small, exactly the kind of thing that check exists to catch) and a
    red-severity dirty run with a real defect injection AND a much
    smaller row count (20 rows, a ~97% drop off the reference - well
    past both that same row_count floor AND evidently's own 25%
    row-count-growth fail threshold) - real generator output, not
    hand-crafted rows."""
    raw_dir = tmp_path_factory.mktemp("bdm_raw")

    ref_df = generate_daily_batch(date(2026, 1, 1), seed=90001, n_rows=600)
    ref_df.to_csv(raw_dir / f"{_REF_RUN_ID}.csv", index=False)

    dirty_df = generate_daily_batch(date(2026, 1, 2), seed=90002, n_rows=20)
    dirty_df = apply_birth_registrations_presets(dirty_df, severity="red", seed=90003, previous_row_count=600)
    dirty_df.to_csv(raw_dir / f"{_DIRTY_RUN_ID}.csv", index=False)

    manifest = [
        {"run_id": _REF_RUN_ID, "file": f"{_REF_RUN_ID}.csv", "run_date": "2026-01-01", "dirty_severity": None},
        {"run_id": _DIRTY_RUN_ID, "file": f"{_DIRTY_RUN_ID}.csv", "run_date": "2026-01-02", "dirty_severity": "red"},
    ]
    with open(raw_dir / "manifest.json", "w") as f:
        json.dump(manifest, f)

    return str(raw_dir)


@pytest.fixture(scope="session")
def bdm_duckdb_dir(tmp_path_factory, bdm_raw_dir):
    """Per-run DuckDB warehouses for bdm_raw_dir's same two runs, built
    via the real qa_tools.bdm.build_per_run_warehouses.build_all() -
    the exact loading code path the real pipeline uses, not a
    hand-rolled copy of it."""
    from qa_tools.bdm.build_per_run_warehouses import build_all

    out_dir = tmp_path_factory.mktemp("bdm_duckdb_runs")
    build_all(raw_dir=bdm_raw_dir, out_dir=str(out_dir))
    return str(out_dir)


_CP_REF_RUN_ID = "pytest_cp_ref"
_CP_DIRTY_RUN_ID = "pytest_cp_dirty"


@pytest.fixture(scope="session")
def cp_raw_dir(tmp_path_factory):
    """A tiny, real data/cp_raw/-shaped directory: two collection
    snapshots (a clean reference and a red-severity dirty one), built
    from a small (not real 70k-row production scale, kept fast for a
    test fixture - real generation confirmed <1s at this size) but
    genuinely real population via the actual synthetic_data_generator.
    population/child_protection generators and generator.dirty's real
    apply_cp_*_presets() injectors - the exact same generation
    functions generator/generate_cp_runs.py's own main() calls, at a
    smaller scale, not a hand-rolled copy of CP's real cross-table
    structure."""
    from generator import dirty as dirty_mod
    from generator.generate_cp_runs import _add_extract_timestamp
    from synthetic_data_generator.child_protection import generate_child_protection_collection
    from synthetic_data_generator.population import generate_population

    raw_dir = tmp_path_factory.mktemp("cp_raw")
    tables_list = ["cp_clients", "cp_notifications", "cp_investigations", "cp_placements", "cp_carers", "cp_case_workers"]

    # 45000 (not the real 70k production scale) is the smallest population
    # that clears every real Soda row_count warn floor for cp_clients (300),
    # cp_notifications (600) and cp_carers (150) - contract/child-protection-
    # soda-checks.yml - so the "clean" reference run really is clean, not
    # just short of the fail threshold.
    pop = generate_population(45000, seed=91001)
    base_tables = generate_child_protection_collection(pop, seed=91002, n_case_workers=15)

    def _write_run(run_id: str, run_date: str, tables: dict, dirty_severity: str | None):
        run_dir = raw_dir / run_id
        run_dir.mkdir()
        row_counts = {}
        for name in tables_list:
            df = _add_extract_timestamp(tables[name], date.fromisoformat(run_date), None, seed=91003)
            cols = [c for c in df.columns if not c.startswith("_")]
            df[cols].to_csv(run_dir / f"{name}.csv", index=False)
            row_counts[name] = int(len(df))
        return {"run_id": run_id, "run_index": 1, "run_date": run_date,
                "dirty_severity": dirty_severity, "seed": 91000, "row_counts": row_counts}

    ref_entry = _write_run(_CP_REF_RUN_ID, "2026-01-01", base_tables, None)

    dirty_tables = {name: base_tables[name].copy() for name in tables_list}
    dirty_tables["cp_notifications"] = dirty_mod.apply_cp_notifications_presets(
        dirty_tables["cp_notifications"], base_tables["cp_clients"], base_tables["cp_case_workers"],
        "red", seed=91101)
    dirty_tables["cp_placements"] = dirty_mod.apply_cp_placements_presets(
        dirty_tables["cp_placements"], dirty_tables["cp_carers"], base_tables["cp_clients"],
        "red", seed=91102)
    dirty_tables["cp_investigations"] = dirty_mod.apply_cp_investigations_presets(
        dirty_tables["cp_investigations"], dirty_tables["cp_clients"], base_tables["cp_notifications"],
        base_tables["cp_case_workers"], "red", seed=91103)
    dirty_tables["cp_clients"] = dirty_mod.apply_cp_clients_presets(dirty_tables["cp_clients"], "red", seed=91104)
    dirty_tables["cp_carers"] = dirty_mod.apply_cp_carers_presets(dirty_tables["cp_carers"], "red", seed=91105)
    dirty_tables["cp_case_workers"] = dirty_mod.apply_cp_case_workers_presets(dirty_tables["cp_case_workers"], "red", seed=91106)
    dirty_entry = _write_run(_CP_DIRTY_RUN_ID, "2026-04-01", dirty_tables, "red")

    with open(raw_dir / "manifest.json", "w") as f:
        json.dump([ref_entry, dirty_entry], f)

    return str(raw_dir)


@pytest.fixture(scope="session")
def cp_duckdb_dir(tmp_path_factory, cp_raw_dir):
    """Per-run DuckDB warehouses for cp_raw_dir's same two runs, built
    via the real qa_tools.cp.build_cp_warehouses.build_all() - the
    exact loading code path the real pipeline uses."""
    from qa_tools.cp.build_cp_warehouses import build_all

    out_dir = tmp_path_factory.mktemp("cp_duckdb_runs")
    build_all(raw_dir=cp_raw_dir, out_dir=str(out_dir))
    return str(out_dir)
