"""Tests for cli/bdm.py - the mothman CLI's Birth Registrations commands
(plans/tooling.md #1 Phase 1). Reuses the same real bdm_raw_dir/
bdm_duckdb_dir fixtures tests/test_check_cli.py already built (real
generator output, not hand-crafted rows), and drives the Click commands
through click.testing.CliRunner, same as that file."""
from __future__ import annotations
import json
import os

from click.testing import CliRunner

import cli.bdm as bdm
import cli.common as common
import qa_tools.bdm.build_per_run_warehouses as build_per_run_warehouses
import qa_tools.bdm.run_datacontract_bdm as run_datacontract_bdm
import qa_tools.bdm.run_dbt_bdm as run_dbt_bdm
import qa_tools.bdm.run_evidently_bdm as run_evidently_bdm
import qa_tools.bdm.run_soda_bdm as run_soda_bdm

_REF_RUN_ID = "pytest_bdm_ref"
_DIRTY_RUN_ID = "pytest_bdm_dirty"

_runner = CliRunner()


def _patch_bdm_dirs(monkeypatch, raw_dir, duckdb_dir):
    monkeypatch.setattr(build_per_run_warehouses, "RAW_DIR", raw_dir)
    monkeypatch.setattr(build_per_run_warehouses, "OUT_DIR", duckdb_dir)
    monkeypatch.setattr(run_datacontract_bdm, "RAW_DIR", raw_dir)
    monkeypatch.setattr(run_evidently_bdm, "RAW_DIR", raw_dir)
    monkeypatch.setattr(run_dbt_bdm, "DUCKDB_RUNS_DIR", duckdb_dir)
    monkeypatch.setattr(run_soda_bdm, "DUCKDB_RUNS_DIR", duckdb_dir)


def test_raw_dir_reads_build_per_run_warehouses_live_not_a_frozen_import_time_copy(monkeypatch):
    """Real regression coverage for the exact bug class orchestrate_bdm.
    run_single()'s own docstring warns about (a module-level constant
    bound once at import time silently ignoring a later monkeypatch) -
    cli/bdm.py's own raw_dir()/manifest_path() must re-read
    build_per_run_warehouses.RAW_DIR fresh on every call, not cache it."""
    monkeypatch.setattr(build_per_run_warehouses, "RAW_DIR", "/some/other/path")
    assert bdm.raw_dir() == "/some/other/path"
    assert bdm.manifest_path() == os.path.join("/some/other/path", "manifest.json")


def test_default_reference_falls_back_to_manifest_first_entry_when_nothing_promoted(monkeypatch, tmp_path):
    monkeypatch.setattr(build_per_run_warehouses, "RAW_DIR", str(tmp_path))
    (tmp_path / "run_001.csv").write_text("id\n1\n")
    manifest = [{"run_id": "run_001", "file": "run_001.csv"}, {"run_id": "run_002", "file": "run_002.csv"}]

    monkeypatch.setattr(bdm, "list_run_ids", lambda agency, dataset: [])
    assert bdm.default_reference(manifest) == ("run_001", "run_001.csv")


def test_default_reference_uses_last_promoted_run_when_its_csv_still_exists(monkeypatch, tmp_path):
    monkeypatch.setattr(build_per_run_warehouses, "RAW_DIR", str(tmp_path))
    (tmp_path / "run_050.csv").write_text("id\n1\n")
    manifest = [{"run_id": "run_001", "file": "run_001.csv"}]

    monkeypatch.setattr(bdm, "list_run_ids", lambda agency, dataset: ["run_010", "run_050"])
    assert bdm.default_reference(manifest) == ("run_050", "run_050.csv")


def test_default_reference_falls_back_when_last_promoted_runs_csv_no_longer_exists(monkeypatch, tmp_path):
    """RUN_PLAN's size has changed across versions of this repo before -
    a Promoted run_id from an older, larger RUN_PLAN might not regenerate
    under today's code at all."""
    monkeypatch.setattr(build_per_run_warehouses, "RAW_DIR", str(tmp_path))
    (tmp_path / "run_001.csv").write_text("id\n1\n")
    manifest = [{"run_id": "run_001", "file": "run_001.csv"}]

    monkeypatch.setattr(bdm, "list_run_ids", lambda agency, dataset: ["run_999_no_longer_generated"])
    assert bdm.default_reference(manifest) == ("run_001", "run_001.csv")


def test_picker_choices_and_run_id_from_choice_round_trip():
    manifest = [{"run_id": "run_001_2026-01-01", "run_date": "2026-01-01", "dirty_severity": None},
                {"run_id": "run_002_2026-01-02", "run_date": "2026-01-02", "dirty_severity": "red"}]
    choices = bdm.picker_choices(manifest)
    assert "clean" in choices[0]
    assert "red" in choices[1]
    assert bdm.run_id_from_choice(choices[0]) == "run_001_2026-01-01"
    assert bdm.run_id_from_choice(choices[1]) == "run_002_2026-01-02"


def test_has_failures_true_on_fail_or_error_false_otherwise():
    assert bdm.has_failures([{"status": "pass"}, {"status": "warn"}]) is False
    assert bdm.has_failures([{"status": "pass"}, {"status": "fail"}]) is True
    assert bdm.has_failures([{"status": "error"}]) is True


def test_run_check_does_not_clobber_the_real_batch_manifest(monkeypatch, tmp_path, bdm_raw_dir, bdm_duckdb_dir):
    """Real bug, found live while building this (a manual smoke test
    actually corrupted the real data/raw/manifest.json from 176 entries
    down to 1): orchestrate_bdm.run_single() unconditionally overwrites
    RAW_DIR/manifest.json with its own synthetic 1-or-2-entry manifest -
    correct and intentional for its real Lambda use case (no pre-existing
    manifest there at all), but a real collision when called against a
    RAW_DIR that already holds the real, full generate_runs.py batch
    manifest this CLI's own run picker reads from. run_check() must
    leave the real manifest exactly as it found it.

    Works on a real COPY of bdm_raw_dir, not the shared session fixture
    directly - this test is specifically probing a destructive side
    effect, and bdm_raw_dir is reused by every other test in this file."""
    import shutil
    raw_copy = tmp_path / "raw_copy"
    shutil.copytree(bdm_raw_dir, raw_copy)

    monkeypatch.setattr(build_per_run_warehouses, "RAW_DIR", str(raw_copy))
    monkeypatch.setattr(build_per_run_warehouses, "OUT_DIR", bdm_duckdb_dir)
    monkeypatch.setattr(run_datacontract_bdm, "RAW_DIR", str(raw_copy))
    monkeypatch.setattr(run_evidently_bdm, "RAW_DIR", str(raw_copy))
    monkeypatch.setattr(run_dbt_bdm, "DUCKDB_RUNS_DIR", bdm_duckdb_dir)
    monkeypatch.setattr(run_soda_bdm, "DUCKDB_RUNS_DIR", bdm_duckdb_dir)

    before = bdm.load_manifest()
    assert len(before) == 2, "test precondition - the real fixture manifest must have both entries"

    bdm.run_check(_REF_RUN_ID, "test@example.com", reference_run_id=_REF_RUN_ID)

    after = bdm.load_manifest()
    assert after == before, "run_check() must not mutate the real batch manifest.json as a side effect"


def test_qa_command_flag_mode_reports_real_results_and_never_touches_real_qa_results(
        monkeypatch, tmp_path, bdm_raw_dir, bdm_duckdb_dir):
    _patch_bdm_dirs(monkeypatch, bdm_raw_dir, bdm_duckdb_dir)
    fake_qa_results = tmp_path / "not_the_real_qa_results"
    monkeypatch.setattr(common, "QA_RESULTS_DIR", fake_qa_results)

    result = _runner.invoke(bdm.qa_command, ["--run-id", _REF_RUN_ID, "--reference-run-id", _REF_RUN_ID])

    assert result.exit_code == 0, result.output
    assert "local-only check" in result.output
    assert not fake_qa_results.exists()


def test_qa_command_flag_mode_commit_promotes_into_the_patched_qa_results_dir(
        monkeypatch, tmp_path, bdm_raw_dir, bdm_duckdb_dir):
    _patch_bdm_dirs(monkeypatch, bdm_raw_dir, bdm_duckdb_dir)
    fake_qa_results = tmp_path / "not_the_real_qa_results"
    monkeypatch.setattr(common, "QA_RESULTS_DIR", fake_qa_results)
    monkeypatch.setattr(bdm, "get_run_by", lambda: "test@example.com")

    result = _runner.invoke(bdm.qa_command,
                             ["--run-id", _REF_RUN_ID, "--reference-run-id", _REF_RUN_ID, "--commit"])

    assert result.exit_code == 0, result.output
    assert "Promoted" in result.output
    dataset_stats_path = fake_qa_results / bdm.AGENCY_ID / bdm.DATASET_ID / _REF_RUN_ID / "dataset_stats.json"
    assert dataset_stats_path.exists()
    with open(dataset_stats_path) as f:
        assert json.load(f)["run_by"] == "test@example.com"


def test_qa_command_reports_real_failures_and_exits_nonzero(monkeypatch, tmp_path, bdm_raw_dir, bdm_duckdb_dir):
    _patch_bdm_dirs(monkeypatch, bdm_raw_dir, bdm_duckdb_dir)
    monkeypatch.setattr(common, "QA_RESULTS_DIR", tmp_path / "unused")

    result = _runner.invoke(bdm.qa_command, ["--run-id", _DIRTY_RUN_ID, "--reference-run-id", _REF_RUN_ID])

    assert result.exit_code == 1, result.output
    assert "fail" in result.output.lower()


def test_qa_command_unknown_run_id_is_a_real_clean_error(monkeypatch, bdm_raw_dir, bdm_duckdb_dir):
    _patch_bdm_dirs(monkeypatch, bdm_raw_dir, bdm_duckdb_dir)
    result = _runner.invoke(bdm.qa_command, ["--run-id", "no-such-run"])
    assert result.exit_code != 0
    assert "no manifest entry" in result.output.lower()


def test_generate_synthetic_data_command_skips_when_declined(monkeypatch, tmp_path):
    monkeypatch.setattr(build_per_run_warehouses, "RAW_DIR", str(tmp_path))
    (tmp_path / "manifest.json").write_text("[]")
    called = []
    monkeypatch.setattr(bdm, "generate_synthetic_data", lambda: called.append(True))
    monkeypatch.setattr(common, "confirm", lambda *a, **k: False)

    result = _runner.invoke(bdm.generate_synthetic_data_command, [])

    assert result.exit_code == 0
    assert called == []
    assert "not regenerated" in result.output.lower()


def test_generate_synthetic_data_command_yes_flag_skips_confirmation(monkeypatch, tmp_path):
    monkeypatch.setattr(build_per_run_warehouses, "RAW_DIR", str(tmp_path))
    (tmp_path / "manifest.json").write_text("[]")
    called = []
    monkeypatch.setattr(bdm, "generate_synthetic_data", lambda: called.append(True))

    result = _runner.invoke(bdm.generate_synthetic_data_command, ["--yes"])

    assert result.exit_code == 0
    assert called == [True]


def test_generate_synthetic_data_command_no_prompt_needed_on_first_run(monkeypatch, tmp_path):
    """No manifest.json yet - nothing to overwrite, so this shouldn't even
    ask."""
    monkeypatch.setattr(build_per_run_warehouses, "RAW_DIR", str(tmp_path))
    called = []
    monkeypatch.setattr(bdm, "generate_synthetic_data", lambda: called.append(True))

    def _fail_if_called(*a, **k):
        raise AssertionError("should not prompt when there's nothing to overwrite yet")
    monkeypatch.setattr(common, "confirm", _fail_if_called)

    result = _runner.invoke(bdm.generate_synthetic_data_command, [])

    assert result.exit_code == 0
    assert called == [True]
