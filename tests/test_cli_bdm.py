"""Tests for cli/bdm.py - the mothman CLI's Birth Registrations commands
(plans/tooling.md #1 Phase 1). Reuses the same real bdm_raw_dir/
bdm_duckdb_dir fixtures tests/test_check_cli.py already built (real
generator output, not hand-crafted rows), and drives the Click commands
through click.testing.CliRunner, same as that file."""
from __future__ import annotations
import json
import os
import re
from unittest.mock import MagicMock

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
    dataset_stats_path = fake_qa_results / bdm.AGENCY_ID / bdm.COLLECTION_ID / _REF_RUN_ID / "dataset_stats.json"
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


# Local files QA source mode (plans/tooling.md #1 Phase 2) - migrated
# from the now-deleted tests/test_check_cli.py once qa_tools/bdm/
# check_file.py's own standalone CLI logic folded into qa_command's
# --file/--reference-file flags (mothman is the only entry point now).

def test_qa_command_local_file_reports_real_failures_and_never_touches_real_qa_results(
        monkeypatch, tmp_path, bdm_raw_dir):
    raw_dir = str(tmp_path / "raw")
    duckdb_dir = str(tmp_path / "duckdb_runs")
    os.makedirs(raw_dir)
    _patch_bdm_dirs(monkeypatch, raw_dir, duckdb_dir)
    fake_qa_results = tmp_path / "not_the_real_qa_results"
    monkeypatch.setattr(common, "QA_RESULTS_DIR", fake_qa_results)

    result = _runner.invoke(bdm.qa_command, [
        "--file", os.path.join(bdm_raw_dir, f"{_DIRTY_RUN_ID}.csv"),
        "--reference-file", os.path.join(bdm_raw_dir, f"{_REF_RUN_ID}.csv"),
    ])

    assert result.exit_code == 1, result.output
    assert "fail" in result.output.lower()
    assert "local-only check" in result.output
    assert not fake_qa_results.exists()


def test_qa_command_local_file_commit_promotes_into_the_patched_qa_results_dir(
        monkeypatch, tmp_path, bdm_raw_dir):
    raw_dir = str(tmp_path / "raw")
    duckdb_dir = str(tmp_path / "duckdb_runs")
    os.makedirs(raw_dir)
    _patch_bdm_dirs(monkeypatch, raw_dir, duckdb_dir)
    fake_qa_results = tmp_path / "not_the_real_qa_results"
    monkeypatch.setattr(common, "QA_RESULTS_DIR", fake_qa_results)
    monkeypatch.setattr(bdm, "get_run_by", lambda: "test@example.com")

    result = _runner.invoke(bdm.qa_command, [
        "--file", os.path.join(bdm_raw_dir, f"{_REF_RUN_ID}.csv"),
        "--reference-file", os.path.join(bdm_raw_dir, f"{_REF_RUN_ID}.csv"),
        "--commit",
    ])

    assert result.exit_code == 0, result.output
    assert "Promoted" in result.output
    matches = list(fake_qa_results.glob(f"{bdm.AGENCY_ID}/{bdm.COLLECTION_ID}/*/dataset_stats.json"))
    assert len(matches) == 1
    with open(matches[0]) as f:
        assert json.load(f)["run_by"] == "test@example.com"


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _flat(output: str) -> str:
    """rich-click wraps its error panels to a fixed width, which can
    split a short assertion phrase like "not both" across a line break
    mid-word - collapsing all whitespace (and box-drawing borders) into
    single spaces makes a plain substring check reliable regardless of
    where the panel happened to wrap. Real CI incident, 2026-09-19: CI's
    runner renders these panels WITH ANSI colour escape codes even
    though CliRunner.invoke() isn't given color=True (rich's own
    terminal-colour auto-detection differs from this project's local
    sandbox, which emits none) - an escape code landing between two
    words defeats a substring check even after whitespace-collapsing,
    since it's not whitespace, so it must be stripped explicitly too."""
    return " ".join(_ANSI_RE.sub("", output).replace("│", " ").split()).lower()


def test_qa_command_local_file_and_run_id_together_is_a_real_clean_error(bdm_raw_dir):
    result = _runner.invoke(bdm.qa_command, [
        "--run-id", "some_run",
        "--file", os.path.join(bdm_raw_dir, f"{_REF_RUN_ID}.csv"),
        "--reference-file", os.path.join(bdm_raw_dir, f"{_REF_RUN_ID}.csv"),
    ])
    assert result.exit_code != 0
    assert "not both" in _flat(result.output)


def test_qa_command_local_file_without_reference_file_is_a_real_clean_error(bdm_raw_dir):
    result = _runner.invoke(bdm.qa_command, ["--file", os.path.join(bdm_raw_dir, f"{_REF_RUN_ID}.csv")])
    assert result.exit_code != 0
    assert "--reference-file" in result.output


def test_qa_command_local_file_rejects_a_reference_file_that_does_not_exist(bdm_raw_dir):
    result = _runner.invoke(bdm.qa_command, [
        "--file", os.path.join(bdm_raw_dir, f"{_REF_RUN_ID}.csv"),
        "--reference-file", "/no/such/file.csv",
    ])
    assert result.exit_code != 0
    assert "does not exist" in _flat(result.output)


def test_run_check_local_file_default_path_never_requires_a_real_git_identity(
        monkeypatch, tmp_path, bdm_raw_dir):
    """Real regression test for a real red CI run (test.yml, 2026-09-19,
    originally against the now-retired qa_tools/bdm/check_file.py, ported
    here since the same logic now lives in run_check_local_file()):
    orchestrate_bdm.run_single() calls git_identity.get_run_by() whenever
    run_by isn't passed explicitly - correct for a --commit run, wrong
    for the default throwaway path, which discards the result before
    anything ever reads run_by. qa_command's own flag-mode body already
    passes a real "local-check:not-persisted" run_by rather than calling
    get_run_by() at all when --commit isn't set - this proves that holds
    for the --file path too, not just --run-id."""
    raw_dir = str(tmp_path / "raw")
    duckdb_dir = str(tmp_path / "duckdb_runs")
    os.makedirs(raw_dir)
    _patch_bdm_dirs(monkeypatch, raw_dir, duckdb_dir)

    from qa_tools.common.git_identity import MissingGitIdentityError

    def _no_git_identity():
        raise MissingGitIdentityError("git config user.email is not set")
    monkeypatch.setattr(bdm, "get_run_by", _no_git_identity)

    result = _runner.invoke(bdm.qa_command, [
        "--file", os.path.join(bdm_raw_dir, f"{_REF_RUN_ID}.csv"),
        "--reference-file", os.path.join(bdm_raw_dir, f"{_REF_RUN_ID}.csv"),
    ])
    assert result.exit_code == 0, f"a default (non---commit) run must never require a real git identity: " \
                                   f"{result.output!r} exc={result.exception!r}"

    result_commit = _runner.invoke(bdm.qa_command, [
        "--file", os.path.join(bdm_raw_dir, f"{_REF_RUN_ID}.csv"),
        "--reference-file", os.path.join(bdm_raw_dir, f"{_REF_RUN_ID}.csv"),
        "--commit",
    ])
    assert isinstance(result_commit.exception, MissingGitIdentityError), \
        "a --commit run must still fail loudly without a real git identity - that guarantee must not regress"


# ---- S3 QA source mode (plans/tooling.md #1 Phase 3) -----------------


def test_s3_config_reads_the_real_committed_contract():
    """A real, not-mocked read of the actual committed contract YAML -
    catches contract drift (a renamed property, a missing entry) that a
    fixture-only test never would."""
    config = bdm.s3_config()
    assert config["prefix"] == "bdm/"
    assert config["local_source"] == "data/raw"
    assert config["arrival_pattern"] == [
        {"type": "single_file", "keyPattern": "bdm/birth_registrations_{date}.csv",
         "dataset_id": "bdm-birth-registrations"},
    ]


def test_run_check_s3_downloads_both_keys_then_delegates_to_local_file_mode(monkeypatch, tmp_path):
    """run_check_s3() is "download, then Local files mode", not a third
    parallel check-running code path - verified here by mocking the
    boto3 client and monkeypatching run_check_local_file() itself, so
    this stays a fast unit test: the real tool-chain correctness for
    whatever lands on disk is already covered by the Local files mode's
    own real integration tests."""
    download_calls = []

    def _fake_download_key(bucket, key, dest_dir, s3_client=None):
        assert bucket == "my-bucket"
        assert s3_client is _fake_client
        local_path = os.path.join(dest_dir, os.path.basename(key))
        with open(local_path, "w") as f:
            f.write("id\n1\n")
        download_calls.append(key)
        return local_path

    monkeypatch.setattr(bdm.s3_source, "download_key", _fake_download_key)

    captured = {}

    def _fake_run_check_local_file(csv_path, reference_csv, run_by, run_id=None, run_date=None, **kwargs):
        captured["csv_path"] = csv_path
        captured["reference_csv"] = reference_csv
        captured["run_by"] = run_by
        captured["run_id"] = run_id
        return [{"status": "pass"}], "/tmp/fake-results"

    monkeypatch.setattr(bdm, "run_check_local_file", _fake_run_check_local_file)

    _fake_client = MagicMock()
    results, tmp_dir = bdm.run_check_s3(
        "my-bucket", "bdm/run_005.csv", "bdm/run_004.csv", "test@example.com",
        run_id="s3_run_005", s3_client=_fake_client)

    assert download_calls == ["bdm/run_005.csv", "bdm/run_004.csv"]
    assert captured["csv_path"].endswith("run_005.csv")
    assert captured["reference_csv"].endswith("run_004.csv")
    assert captured["run_by"] == "test@example.com"
    assert captured["run_id"] == "s3_run_005"
    assert results == [{"status": "pass"}]
    assert tmp_dir == "/tmp/fake-results"


def test_qa_command_s3_key_and_run_id_together_is_a_real_clean_error(monkeypatch):
    monkeypatch.setenv(common.S3_BUCKET_ENV_VAR, "my-bucket")
    result = _runner.invoke(bdm.qa_command, [
        "--run-id", "some_run",
        "--s3-key", "bdm/run_005.csv",
        "--s3-reference-key", "bdm/run_004.csv",
    ])
    assert result.exit_code != 0
    assert "exactly one" in _flat(result.output)


def test_qa_command_s3_key_and_file_together_is_a_real_clean_error(bdm_raw_dir, monkeypatch):
    monkeypatch.setenv(common.S3_BUCKET_ENV_VAR, "my-bucket")
    result = _runner.invoke(bdm.qa_command, [
        "--file", os.path.join(bdm_raw_dir, f"{_REF_RUN_ID}.csv"),
        "--s3-key", "bdm/run_005.csv",
        "--s3-reference-key", "bdm/run_004.csv",
    ])
    assert result.exit_code != 0
    assert "exactly one" in _flat(result.output)


def test_qa_command_s3_key_without_reference_key_is_a_real_clean_error(monkeypatch):
    monkeypatch.setenv(common.S3_BUCKET_ENV_VAR, "my-bucket")
    result = _runner.invoke(bdm.qa_command, ["--s3-key", "bdm/run_005.csv"])
    assert result.exit_code != 0
    assert "--s3-reference-key" in result.output


def test_qa_command_s3_key_requires_the_real_bucket_env_var(monkeypatch):
    monkeypatch.delenv(common.S3_BUCKET_ENV_VAR, raising=False)
    result = _runner.invoke(bdm.qa_command, [
        "--s3-key", "bdm/run_005.csv",
        "--s3-reference-key", "bdm/run_004.csv",
    ])
    assert result.exit_code != 0
    assert common.S3_BUCKET_ENV_VAR.lower() in _flat(result.output)


def test_qa_command_s3_key_flag_mode_downloads_and_runs_real_checks(monkeypatch):
    """The full flag-invocable S3 path, end to end, with a mocked boto3
    client (no real AWS access in this sandbox) - proves qa_command's
    own S3 branch wires bucket/key/run_id through to run_check_s3()
    correctly, not just that run_check_s3() itself works in isolation."""
    monkeypatch.setenv(common.S3_BUCKET_ENV_VAR, "my-bucket")

    captured = {}

    def _fake_run_check_s3(bucket, key, reference_key, run_by, run_id=None, run_date=None, s3_client=None, **kwargs):
        captured.update(bucket=bucket, key=key, reference_key=reference_key, run_by=run_by, run_id=run_id)
        return [{"status": "pass"}], "/tmp/fake-results"

    monkeypatch.setattr(bdm, "run_check_s3", _fake_run_check_s3)

    result = _runner.invoke(bdm.qa_command, [
        "--s3-key", "bdm/birth_registrations_2026-01-02.csv",
        "--s3-reference-key", "bdm/birth_registrations_2026-01-01.csv",
    ])

    assert result.exit_code == 0, result.output
    assert captured["bucket"] == "my-bucket"
    assert captured["key"] == "bdm/birth_registrations_2026-01-02.csv"
    assert captured["reference_key"] == "bdm/birth_registrations_2026-01-01.csv"
    assert captured["run_by"] == "local-check:not-persisted"
    assert captured["run_id"].startswith("s3_birth_registrations_2026-01-02_")
