"""Tests for cli/population.py - `mothman population`, Tier 4/exploratory
(plans/tooling.md #1 Phase 5). synthetic_data_generator/ had zero test
coverage before this (plans/data-generation.md's own noted real gap) -
these are real, seeded, small-population runs (this project's convention
throughout: verify by actually running things, not mocking), kept fast
via a small --population rather than any synthetic_data_generator/-
internal mocking."""
from __future__ import annotations

from click.testing import CliRunner

import cli.population as population_cli

_runner = CliRunner()


def test_help_does_not_error():
    result = _runner.invoke(population_cli.population_command, ["--help"])
    assert result.exit_code == 0, result.output
    assert "Tier 4" in result.output


def test_real_small_population_writes_public_and_internal_outputs(tmp_path):
    outdir = tmp_path / "demo"

    result = _runner.invoke(population_cli.population_command, [
        "--population", "300", "--outdir", str(outdir), "--demo-examples", "0",
    ])

    assert result.exit_code == 0, result.output
    assert (outdir / "public" / "birth_registrations.csv").exists()
    assert (outdir / "public" / "cp_clients.csv").exists()
    assert (outdir / "public" / "school_enrollment.csv").exists()
    assert (outdir / "internal" / "population_master.csv").exists()
    assert (outdir / "internal" / "linkage_answer_key.csv").exists()


def test_real_small_population_prints_cross_agency_demo_examples(tmp_path):
    outdir = tmp_path / "demo"

    result = _runner.invoke(population_cli.population_command, [
        "--population", "2000", "--outdir", str(outdir), "--demo-examples", "1",
    ])

    assert result.exit_code == 0, result.output
    assert "Registry Services / BDM" in result.output
    assert "Child & Family Safety" in result.output
    assert "Education" in result.output


def test_dirty_amber_does_not_raise_a_real_regression_coverage(tmp_path):
    """Real regression coverage for a genuine bug found while building
    this command: synthetic_data_generator/generate.py's build() called
    dirty_mod.apply_cp_notifications_presets() with its OLD 3-arg
    signature (df, severity, seed) - the real function had since grown
    clients_df/workers_df params (dangling-FK injection, generator/
    dirty.py) that generator/generate_cp_runs.py's own call site was
    updated for, but this sibling call site never was, since synthetic_
    data_generator/ isn't wired into the real pipeline's own test/CI
    coverage. Reproduced live: `mothman population --dirty amber` raised
    a real TypeError ("missing 2 required positional arguments:
    'workers_df' and 'severity'") before the fix in generate.py's own
    build() (passing cp_tables["cp_clients"]/cp_tables["cp_case_workers"]
    through, matching generate_cp_runs.py's own real calling convention)."""
    outdir = tmp_path / "demo"

    result = _runner.invoke(population_cli.population_command, [
        "--population", "2000", "--dirty", "amber", "--outdir", str(outdir), "--demo-examples", "0",
    ])

    assert result.exit_code == 0, result.output
    assert "applied 'amber' failure-injection presets" in result.output


def test_dirty_red_does_not_raise(tmp_path):
    outdir = tmp_path / "demo"

    result = _runner.invoke(population_cli.population_command, [
        "--population", "2000", "--dirty", "red", "--outdir", str(outdir), "--demo-examples", "0",
    ])

    assert result.exit_code == 0, result.output
    assert "applied 'red' failure-injection presets" in result.output


def test_default_outdir_matches_the_real_synthetic_data_generator_output_demo_path():
    import os
    assert population_cli._DEFAULT_OUTDIR.endswith(os.path.join("synthetic_data_generator", "output", "demo"))
