"""Tests for cli/cp.py - the mothman CLI's Child Protection commands
(plans/tooling.md #1 Phase 1's own "still open" item, finished). Reuses
the same real cp_raw_dir/cp_duckdb_dir fixtures tests/test_check_cli.py
already built (real generator output, not hand-crafted rows), and drives
the Click commands through click.testing.CliRunner, same pattern as
tests/test_cli_bdm.py."""
from __future__ import annotations
import json

from qa_tools.common import tables_read
import os
import re
from unittest.mock import MagicMock

from click.testing import CliRunner

import cli.common as common
import cli.cp as cp
import qa_tools.cp.build_cp_warehouses as build_cp_warehouses
import qa_tools.cp.orchestrate_cp as orchestrate_cp
import qa_tools.cp.run_datacontract_cp as run_datacontract_cp
import qa_tools.cp.run_evidently_cp as run_evidently_cp

from fixture_ids import CP_DIRTY_RUN_ID as _DIRTY_RUN_ID, CP_REF_RUN_ID as _REF_RUN_ID

_runner = CliRunner()


def _patch_delivery_dirs(monkeypatch, delivery_dirs):
    """Point arrival recognition at an isolated tree (REQ-GEN-043) -
    see tests/test_cli_bdm.py's identical helper for why patching the
    raw dir alone is no longer enough."""
    from qa_tools.common import delivery
    monkeypatch.setattr(delivery, "DELIVERIES_DIR", delivery_dirs[0])
    monkeypatch.setattr(delivery, "RECEIPTS_DIR", delivery_dirs[1])


def _patch_cp_dirs(monkeypatch, raw_dir, duckdb_dir, delivery_dirs=None):
    # The run picker recognises arrivals from disk now (REQ-GEN-043),
    # so pointing it at the fixture means pointing the DELIVERY
    # directories at it - patching CP_RAW_DIR alone would leave these
    # tests reading the real data/deliveries/ tree.
    if delivery_dirs is not None:
        _patch_delivery_dirs(monkeypatch, delivery_dirs)
    monkeypatch.setattr(build_cp_warehouses, "CP_RAW_DIR", raw_dir)
    monkeypatch.setattr(run_datacontract_cp, "CP_RAW_DIR", raw_dir)
    monkeypatch.setattr(run_evidently_cp, "CP_RAW_DIR", raw_dir)
    # One database, named by the environment - see the BDM
    # counterpart's own comment (REQ-PIPE-068).
    # The environment already points at this worker's database
    # (conftest's supply_dsn); duckdb_dir is what staged the data into it.


def test_raw_dir_reads_build_cp_warehouses_live_not_a_frozen_import_time_copy(monkeypatch):
    """Same regression coverage as cli/bdm.py's own raw_dir() test, for
    the CP counterpart - must re-read build_cp_warehouses.CP_RAW_DIR
    fresh on every call, not cache it at import time."""
    monkeypatch.setattr(build_cp_warehouses, "CP_RAW_DIR", "/some/other/path")
    assert cp.raw_dir() == "/some/other/path"


def test_default_reference_falls_back_to_manifest_first_entry_when_nothing_promoted(monkeypatch, tmp_path):
    monkeypatch.setattr(build_cp_warehouses, "CP_RAW_DIR", str(tmp_path))
    (tmp_path / "cp_run_01").mkdir()
    manifest = [{"run_id": "cp_run_01"}, {"run_id": "cp_run_02"}]

    monkeypatch.setattr(cp, "list_run_ids", lambda agency, dataset: [])
    assert cp.default_reference(manifest) == "cp_run_01"


def test_default_reference_uses_last_promoted_run_when_its_data_still_exists(monkeypatch, tmp_path):
    monkeypatch.setattr(build_cp_warehouses, "CP_RAW_DIR", str(tmp_path))
    (tmp_path / "cp_run_05").mkdir()
    manifest = [{"run_id": "cp_run_01"}]

    monkeypatch.setattr(cp, "list_run_ids", lambda agency, dataset: ["cp_run_02", "cp_run_05"])
    assert cp.default_reference(manifest) == "cp_run_05"


def test_default_reference_falls_back_when_last_promoted_runs_data_no_longer_exists(monkeypatch, tmp_path):
    monkeypatch.setattr(build_cp_warehouses, "CP_RAW_DIR", str(tmp_path))
    (tmp_path / "cp_run_01").mkdir()
    manifest = [{"run_id": "cp_run_01"}]

    monkeypatch.setattr(cp, "list_run_ids", lambda agency, dataset: ["cp_run_99_no_longer_generated"])
    assert cp.default_reference(manifest) == "cp_run_01"


def test_picker_choices_and_run_id_from_choice_round_trip():
    manifest = [{"run_id": "cp_run_001", "received_at": "2023-02-01T01:00:00+00:00", "delivery": "DCP_20230201"},
                {"run_id": "cp_run_002", "received_at": "2023-05-01T01:00:00+00:00", "delivery": "2023-05-final"}]
    choices = cp.picker_choices(manifest)
    # See tests/test_cli_bdm.py's identical picker assertion.
    assert "DCP_20230201" in choices[0]
    assert "2023-05-final" in choices[1]
    assert cp.run_id_from_choice(choices[0]) == "cp_run_001"
    assert cp.run_id_from_choice(choices[1]) == "cp_run_002"


def test_has_failures_true_on_fail_or_error_false_otherwise():
    assert cp.has_failures([{"status": "pass"}, {"status": "warn"}]) is False
    assert cp.has_failures([{"status": "pass"}, {"status": "fail"}]) is True
    assert cp.has_failures([{"status": "error"}]) is True


def test_qa_command_flag_mode_reports_real_results_and_never_touches_real_qa_results(
        monkeypatch, tmp_path, cp_raw_dir, cp_duckdb_dir, cp_delivery_dirs):
    _patch_cp_dirs(monkeypatch, cp_raw_dir, cp_duckdb_dir, cp_delivery_dirs)
    fake_qa_results = tmp_path / "not_the_real_qa_results"
    monkeypatch.setattr(common, "QA_RESULTS_DIR", fake_qa_results)

    result = _runner.invoke(cp.qa_command, ["--run-id", _REF_RUN_ID, "--reference-run-id", _REF_RUN_ID])

    assert result.exit_code == 0, result.output
    assert "local-only check" in result.output
    assert not fake_qa_results.exists()


def test_qa_command_flag_mode_commit_promotes_into_the_patched_qa_results_dir(
        monkeypatch, tmp_path, cp_raw_dir, cp_duckdb_dir, cp_delivery_dirs):
    _patch_cp_dirs(monkeypatch, cp_raw_dir, cp_duckdb_dir, cp_delivery_dirs)
    fake_qa_results = tmp_path / "not_the_real_qa_results"
    monkeypatch.setattr(common, "QA_RESULTS_DIR", fake_qa_results)
    monkeypatch.setattr(cp, "get_run_by", lambda: "test@example.com")

    result = _runner.invoke(cp.qa_command,
                             ["--run-id", _REF_RUN_ID, "--reference-run-id", _REF_RUN_ID, "--commit"])

    assert result.exit_code == 0, result.output
    assert "Promoted" in result.output
    dataset_stats_path = (fake_qa_results / cp.AGENCY_ID / cp.COLLECTION_ID
                           / tables_read.RAW_SCOPE / _REF_RUN_ID / "dataset_stats.json")
    assert dataset_stats_path.exists()
    with open(dataset_stats_path) as f:
        assert json.load(f)["run_by"] == "test@example.com"


def test_qa_command_reports_real_failures_and_exits_nonzero(
        monkeypatch, tmp_path, cp_raw_dir, cp_duckdb_dir, cp_delivery_dirs):
    _patch_cp_dirs(monkeypatch, cp_raw_dir, cp_duckdb_dir, cp_delivery_dirs)
    monkeypatch.setattr(common, "QA_RESULTS_DIR", tmp_path / "unused")

    result = _runner.invoke(cp.qa_command, ["--run-id", _DIRTY_RUN_ID, "--reference-run-id", _REF_RUN_ID])

    assert result.exit_code == 1, result.output
    assert "fail" in result.output.lower()


def test_qa_command_unknown_run_id_is_a_real_clean_error(monkeypatch, cp_raw_dir, cp_duckdb_dir):
    _patch_cp_dirs(monkeypatch, cp_raw_dir, cp_duckdb_dir)
    result = _runner.invoke(cp.qa_command, ["--run-id", "no-such-run"])
    assert result.exit_code != 0
    assert "no manifest entry" in result.output.lower()


def test_generate_synthetic_data_command_skips_when_declined(monkeypatch, tmp_path, cp_delivery_dirs):
    monkeypatch.setattr(build_cp_warehouses, "CP_RAW_DIR", str(tmp_path))
    # Real deliveries already on disk - so there IS something to
    # overwrite, and the command must ask before it does.
    _patch_delivery_dirs(monkeypatch, cp_delivery_dirs)
    called = []
    monkeypatch.setattr(cp, "generate_synthetic_data", lambda: called.append(True))
    monkeypatch.setattr(common, "confirm", lambda *a, **k: False)

    result = _runner.invoke(cp.generate_synthetic_data_command, [])

    assert result.exit_code == 0
    assert called == []
    assert "not regenerated" in result.output.lower()


def test_generate_synthetic_data_command_yes_flag_skips_confirmation(monkeypatch, tmp_path, cp_delivery_dirs):
    monkeypatch.setattr(build_cp_warehouses, "CP_RAW_DIR", str(tmp_path))
    _patch_delivery_dirs(monkeypatch, cp_delivery_dirs)
    called = []
    monkeypatch.setattr(cp, "generate_synthetic_data", lambda: called.append(True))

    result = _runner.invoke(cp.generate_synthetic_data_command, ["--yes"])

    assert result.exit_code == 0
    assert called == [True]


def test_generate_synthetic_data_command_no_prompt_needed_on_first_run(monkeypatch, tmp_path):
    """No deliveries on disk yet - nothing to overwrite, so this
    shouldn't even ask."""
    monkeypatch.setattr(build_cp_warehouses, "CP_RAW_DIR", str(tmp_path))
    _patch_delivery_dirs(monkeypatch, (tmp_path / "deliveries", tmp_path / "receipts"))
    called = []
    monkeypatch.setattr(cp, "generate_synthetic_data", lambda: called.append(True))

    def _fail_if_called(*a, **k):
        raise AssertionError("should not prompt when there's nothing to overwrite yet")
    monkeypatch.setattr(common, "confirm", _fail_if_called)

    result = _runner.invoke(cp.generate_synthetic_data_command, [])

    assert result.exit_code == 0
    assert called == [True]


# Local files QA source mode (plans/tooling.md #1 Phase 2) - migrated
# from the now-deleted tests/test_check_cli.py once qa_tools/cp/
# check_delivery.py's own standalone CLI logic folded into qa_command's
# --folder/--reference-folder flags (mothman is the only entry point
# now).

def test_qa_command_local_folder_reports_real_cp_failures(monkeypatch, tmp_path, cp_raw_dir, cp_duckdb_dir):
    _patch_cp_dirs(monkeypatch, cp_raw_dir, cp_duckdb_dir)
    fake_qa_results = tmp_path / "not_the_real_qa_results"
    monkeypatch.setattr(common, "QA_RESULTS_DIR", fake_qa_results)

    result = _runner.invoke(cp.qa_command, [
        "--folder", os.path.join(cp_raw_dir, _DIRTY_RUN_ID),
        "--reference-folder", os.path.join(cp_raw_dir, _REF_RUN_ID),
    ])

    assert result.exit_code == 1, result.output
    assert "fail" in result.output.lower()
    assert "local-only check" in result.output
    assert not fake_qa_results.exists()


def test_qa_command_local_folder_commit_promotes_into_the_patched_qa_results_dir(
        monkeypatch, tmp_path, cp_raw_dir, cp_duckdb_dir):
    _patch_cp_dirs(monkeypatch, cp_raw_dir, cp_duckdb_dir)
    fake_qa_results = tmp_path / "not_the_real_qa_results"
    monkeypatch.setattr(common, "QA_RESULTS_DIR", fake_qa_results)
    monkeypatch.setattr(cp, "get_run_by", lambda: "test@example.com")

    result = _runner.invoke(cp.qa_command, [
        "--folder", os.path.join(cp_raw_dir, _REF_RUN_ID),
        "--reference-folder", os.path.join(cp_raw_dir, _REF_RUN_ID),
        "--commit",
    ])

    assert result.exit_code == 0, result.output
    assert "Promoted" in result.output
    matches = list(fake_qa_results.glob(
        f"{cp.AGENCY_ID}/{cp.COLLECTION_ID}/{tables_read.RAW_SCOPE}/*/dataset_stats.json"))
    assert len(matches) == 1
    with open(matches[0]) as f:
        assert json.load(f)["run_by"] == "test@example.com"


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _flat(output: str) -> str:
    """See tests/test_cli_bdm.py's own _flat() - same rich-click panel
    line-wrapping/ANSI-colour-code issue, same fix."""
    return " ".join(_ANSI_RE.sub("", output).replace("│", " ").split()).lower()


def test_qa_command_local_folder_and_run_id_together_is_a_real_clean_error(cp_raw_dir):
    result = _runner.invoke(cp.qa_command, [
        "--run-id", "some_run",
        "--folder", os.path.join(cp_raw_dir, _REF_RUN_ID),
        "--reference-folder", os.path.join(cp_raw_dir, _REF_RUN_ID),
    ])
    assert result.exit_code != 0
    assert "not both" in _flat(result.output)


def test_qa_command_local_folder_without_reference_folder_is_a_real_clean_error(cp_raw_dir):
    result = _runner.invoke(cp.qa_command, ["--folder", os.path.join(cp_raw_dir, _REF_RUN_ID)])
    assert result.exit_code != 0
    assert "--reference-folder" in result.output


def test_qa_command_local_folder_errors_on_a_partial_delivery(tmp_path):
    partial = tmp_path / "partial_delivery"
    partial.mkdir()
    (partial / "cp_clients.csv").write_text("id\n1\n")
    # the other 5 real tables are deliberately missing

    result = _runner.invoke(cp.qa_command, ["--folder", str(partial), "--reference-folder", str(partial)])

    assert result.exit_code != 0
    assert "missing" in result.output.lower()


# ---- S3 QA source mode (plans/tooling.md #1 Phase 3) -----------------


def test_s3_config_reads_the_real_committed_contract():
    """A real, not-mocked read of the actual committed contract YAML -
    catches contract drift (a renamed property, a missing entry) that a
    fixture-only test never would."""
    config = cp.s3_config()
    assert config["prefix"] == "cp/"
    assert config["local_source"] == "data/cp_raw"
    arrival = config["arrival_pattern"]
    assert len(arrival) == 6
    assert {p["extractTo"] for p in arrival} == set(cp.TABLES)
    # Each pattern names ITS OWN dataset, not the collection - a file's
    # dataset has to be derivable from its filename (REQ-GEN-043).
    assert all(p["type"] == "nested_folder" for p in arrival)
    assert {p["dataset_id"] for p in arrival} == {
        "cp-clients", "cp-notifications", "cp-investigations",
        "cp-placements", "cp-carers", "cp-case-workers"}


def test_run_check_s3_delivery_downloads_both_prefixes_then_delegates_to_local_folder_mode(monkeypatch):
    """run_check_s3_delivery() is "download, then Local files mode", not
    a third parallel check-running code path - verified here by
    monkeypatching download_prefix()/run_check_local_folder() itself, so
    this stays a fast unit test: the real tool-chain correctness for
    whatever lands on disk is already covered by the Local files mode's
    own real integration tests."""
    download_calls = []

    def _fake_download_prefix(bucket, prefix, dest_dir, s3_client=None):
        assert bucket == "my-bucket"
        assert s3_client is _fake_client
        download_calls.append((prefix, dest_dir))
        return [os.path.join(dest_dir, f"{t}.csv") for t in cp.TABLES]

    monkeypatch.setattr(cp.s3_source, "download_prefix", _fake_download_prefix)

    captured = {}

    def _fake_run_check_local_folder(folder, reference_folder, run_by, run_id=None, run_date=None, **kwargs):
        captured["folder"] = folder
        captured["reference_folder"] = reference_folder
        captured["run_by"] = run_by
        captured["run_id"] = run_id
        return [{"status": "pass"}], "/tmp/fake-results"

    monkeypatch.setattr(cp, "run_check_local_folder", _fake_run_check_local_folder)

    _fake_client = MagicMock()
    results, tmp_dir = cp.run_check_s3_delivery(
        "my-bucket", "cp/delivery_002/", "cp/delivery_001/", "test@example.com",
        run_id="s3_delivery_002", s3_client=_fake_client)

    assert [c[0] for c in download_calls] == ["cp/delivery_002/", "cp/delivery_001/"]
    assert captured["folder"] == download_calls[0][1]
    assert captured["reference_folder"] == download_calls[1][1]
    assert captured["run_by"] == "test@example.com"
    assert captured["run_id"] == "s3_delivery_002"
    assert results == [{"status": "pass"}]
    assert tmp_dir == "/tmp/fake-results"


def test_qa_command_s3_delivery_and_run_id_together_is_a_real_clean_error(monkeypatch):
    monkeypatch.setenv(common.S3_BUCKET_ENV_VAR, "my-bucket")
    result = _runner.invoke(cp.qa_command, [
        "--run-id", "some_run",
        "--s3-delivery", "cp/delivery_002/",
        "--s3-reference-delivery", "cp/delivery_001/",
    ])
    assert result.exit_code != 0
    assert "exactly one" in _flat(result.output)


def test_qa_command_s3_delivery_without_reference_is_a_real_clean_error(monkeypatch):
    monkeypatch.setenv(common.S3_BUCKET_ENV_VAR, "my-bucket")
    result = _runner.invoke(cp.qa_command, ["--s3-delivery", "cp/delivery_002/"])
    assert result.exit_code != 0
    assert "--s3-reference-delivery" in result.output


def test_qa_command_s3_delivery_requires_the_real_bucket_env_var(monkeypatch):
    monkeypatch.delenv(common.S3_BUCKET_ENV_VAR, raising=False)
    result = _runner.invoke(cp.qa_command, [
        "--s3-delivery", "cp/delivery_002/",
        "--s3-reference-delivery", "cp/delivery_001/",
    ])
    assert result.exit_code != 0
    assert common.S3_BUCKET_ENV_VAR.lower() in _flat(result.output)


def test_qa_command_s3_delivery_flag_mode_downloads_and_runs_real_checks(monkeypatch):
    """The full flag-invocable S3 path, end to end, with a mocked boto3
    client (no real AWS access in this sandbox) - proves qa_command's
    own S3 branch wires bucket/delivery/run_id through to
    run_check_s3_delivery() correctly, not just that
    run_check_s3_delivery() itself works in isolation."""
    monkeypatch.setenv(common.S3_BUCKET_ENV_VAR, "my-bucket")

    captured = {}

    def _fake_run_check_s3_delivery(bucket, delivery_prefix, reference_delivery_prefix, run_by,
                                     run_id=None, run_date=None, s3_client=None, **kwargs):
        captured.update(bucket=bucket, delivery_prefix=delivery_prefix,
                         reference_delivery_prefix=reference_delivery_prefix, run_by=run_by, run_id=run_id)
        return [{"status": "pass"}], "/tmp/fake-results"

    monkeypatch.setattr(cp, "run_check_s3_delivery", _fake_run_check_s3_delivery)

    result = _runner.invoke(cp.qa_command, [
        "--s3-delivery", "cp/delivery_002/",
        "--s3-reference-delivery", "cp/delivery_001/",
    ])

    assert result.exit_code == 0, result.output
    assert captured["bucket"] == "my-bucket"
    assert captured["delivery_prefix"] == "cp/delivery_002/"
    assert captured["reference_delivery_prefix"] == "cp/delivery_001/"
    assert captured["run_by"] == "local-check:not-persisted"
    assert captured["run_id"].startswith("s3_delivery_002_")


# ---- Single-table Child Protection QA (plans/tooling.md #1 Phase 3.5) --


def test_run_check_single_table_errors_when_the_other_tables_run_has_no_local_data(monkeypatch, tmp_path):
    monkeypatch.setattr(build_cp_warehouses, "CP_RAW_DIR", str(tmp_path))
    monkeypatch.setattr(cp, "load_manifest", lambda: [{"run_id": "cp_run_01"}])
    monkeypatch.setattr(cp, "default_reference", lambda manifest: "cp_run_missing")

    result_exc = None
    try:
        cp.run_check_single_table("cp_clients", "/some/cp_clients.csv", "test@example.com")
    except Exception as e:  # noqa: BLE001 - asserting the real ClickException below
        result_exc = e

    import rich_click as click
    assert isinstance(result_exc, click.ClickException)
    assert "no local data" in str(result_exc).lower()


def test_run_check_single_table_loads_other_5_tables_from_the_last_promoted_run(monkeypatch, tmp_path):
    """The core Phase 3.5 mechanic - verified here at the unit level
    (monkeypatched _load_delivery/add_table_to_run/orchestrate_cp.
    run_single), since the real per-tool correctness for whatever lands
    in the warehouse is already covered by the existing full-delivery
    integration tests; this test is about proving the RIGHT 6 tables
    from the RIGHT 2 sources (5 from the last Promoted run, 1 fresh)
    actually get loaded."""
    monkeypatch.setattr(build_cp_warehouses, "CP_RAW_DIR", str(tmp_path))
    (tmp_path / "cp_run_promoted").mkdir()
    monkeypatch.setattr(cp, "load_manifest", lambda: [{"run_id": "cp_run_01"}])
    monkeypatch.setattr(cp, "default_reference", lambda manifest: "cp_run_promoted")

    delivery_loads = []
    monkeypatch.setattr(cp, "_load_delivery", lambda run_id: delivery_loads.append(run_id))

    add_table_calls = []

    def _fake_add_table_to_run(run_id, table, csv_path, db_path=None, raw_dir=None):
        add_table_calls.append((run_id, table, csv_path))

    monkeypatch.setattr(build_cp_warehouses, "add_table_to_run", _fake_add_table_to_run)

    captured = {}

    def _fake_run_single(entry, reference_run_id=None, run_by=None, **kwargs):
        # **kwargs so this double doesn't have to mirror run_single()'s
        # full signature - it only asserts on the three arguments this
        # test is actually about. Caught for real when run_single() grew
        # an optional on_step callback (plans/tooling.md #13) and this
        # fake rejected it, failing a test that has nothing to do with
        # progress reporting.
        captured.update(entry=entry, reference_run_id=reference_run_id, run_by=run_by)
        return [{"status": "pass"}]

    monkeypatch.setattr(orchestrate_cp, "run_single", _fake_run_single)

    results, tmp_dir = cp.run_check_single_table(
        "cp_clients", "/tmp/fresh_cp_clients.csv", "test@example.com", run_id="table_cp_clients_001")

    assert delivery_loads == ["cp_run_promoted"]

    target_calls = [c for c in add_table_calls if c[1] == "cp_clients"]
    assert target_calls == [("table_cp_clients_001", "cp_clients", "/tmp/fresh_cp_clients.csv")]

    other_calls = {c[1]: c[2] for c in add_table_calls if c[0] == "table_cp_clients_001" and c[1] != "cp_clients"}
    assert set(other_calls) == {t for t in cp.TABLES if t != "cp_clients"}
    for table, csv_path in other_calls.items():
        assert csv_path == os.path.join(str(tmp_path), "cp_run_promoted", f"{table}.csv")

    assert captured["reference_run_id"] == "cp_run_promoted"
    assert captured["run_by"] == "test@example.com"
    assert results == [{"status": "pass"}]
    assert tmp_dir


def test_run_check_s3_single_table_downloads_then_delegates_to_single_table_mode(monkeypatch):
    download_calls = []

    def _fake_download_key(bucket, key, dest_dir, s3_client=None):
        assert bucket == "my-bucket"
        local_path = os.path.join(dest_dir, os.path.basename(key))
        with open(local_path, "w") as f:
            f.write("id\n1\n")
        download_calls.append(key)
        return local_path

    monkeypatch.setattr(cp.s3_source, "download_key", _fake_download_key)

    captured = {}

    def _fake_run_check_single_table(table, file_path, run_by, run_id=None, run_date=None, **kwargs):
        captured.update(table=table, file_path=file_path, run_by=run_by, run_id=run_id)
        return [{"status": "pass"}], "/tmp/fake-results"

    monkeypatch.setattr(cp, "run_check_single_table", _fake_run_check_single_table)

    results, tmp_dir = cp.run_check_s3_single_table(
        "my-bucket", "cp_clients", "cp/delivery_005/cp_clients.csv", "test@example.com", run_id="table_run")

    assert download_calls == ["cp/delivery_005/cp_clients.csv"]
    assert captured["table"] == "cp_clients"
    assert captured["file_path"].endswith("cp_clients.csv")
    assert captured["run_by"] == "test@example.com"
    assert captured["run_id"] == "table_run"
    assert results == [{"status": "pass"}]
    assert tmp_dir == "/tmp/fake-results"


def test_qa_command_table_and_run_id_together_is_a_real_clean_error(tmp_path):
    csv = tmp_path / "cp_clients.csv"
    csv.write_text("id\n1\n")
    result = _runner.invoke(cp.qa_command, [
        "--run-id", "some_run", "--table", "cp_clients", "--file", str(csv),
    ])
    assert result.exit_code != 0
    assert "single-table mode" in _flat(result.output)


def test_qa_command_table_requires_exactly_one_of_file_or_s3_key(tmp_path):
    result_neither = _runner.invoke(cp.qa_command, ["--table", "cp_clients"])
    assert result_neither.exit_code != 0
    assert "exactly one" in _flat(result_neither.output)

    csv = tmp_path / "cp_clients.csv"
    csv.write_text("id\n1\n")
    result_both = _runner.invoke(cp.qa_command, [
        "--table", "cp_clients", "--file", str(csv), "--s3-key", "cp/delivery_001/cp_clients.csv",
    ])
    assert result_both.exit_code != 0
    assert "exactly one" in _flat(result_both.output)


def test_qa_command_file_without_table_is_a_real_clean_error(tmp_path):
    csv = tmp_path / "cp_clients.csv"
    csv.write_text("id\n1\n")
    result = _runner.invoke(cp.qa_command, ["--file", str(csv)])
    assert result.exit_code != 0
    assert "--table" in result.output


def test_qa_command_table_file_flag_mode_calls_run_check_single_table(monkeypatch, tmp_path):
    csv = tmp_path / "cp_clients.csv"
    csv.write_text("id\n1\n")

    captured = {}

    def _fake_run_check_single_table(table, file_path, run_by, run_id=None, run_date=None, **kwargs):
        captured.update(table=table, file_path=file_path, run_by=run_by, run_id=run_id)
        return [{"status": "pass"}], "/tmp/fake-results"

    monkeypatch.setattr(cp, "run_check_single_table", _fake_run_check_single_table)

    result = _runner.invoke(cp.qa_command, ["--table", "cp_clients", "--file", str(csv)])

    assert result.exit_code == 0, result.output
    assert captured["table"] == "cp_clients"
    assert captured["file_path"] == str(csv)
    assert captured["run_by"] == "local-check:not-persisted"
    assert captured["run_id"].startswith("table_cp_clients_")


def test_qa_command_table_s3_key_flag_mode_calls_run_check_s3_single_table(monkeypatch):
    monkeypatch.setenv(common.S3_BUCKET_ENV_VAR, "my-bucket")

    captured = {}

    def _fake_run_check_s3_single_table(bucket, table, key, run_by, run_id=None, run_date=None, s3_client=None, **kwargs):
        captured.update(bucket=bucket, table=table, key=key, run_by=run_by, run_id=run_id)
        return [{"status": "pass"}], "/tmp/fake-results"

    monkeypatch.setattr(cp, "run_check_s3_single_table", _fake_run_check_s3_single_table)

    result = _runner.invoke(cp.qa_command, [
        "--table", "cp_clients", "--s3-key", "cp/delivery_005/cp_clients.csv",
    ])

    assert result.exit_code == 0, result.output
    assert captured["bucket"] == "my-bucket"
    assert captured["table"] == "cp_clients"
    assert captured["key"] == "cp/delivery_005/cp_clients.csv"
    assert captured["run_by"] == "local-check:not-persisted"
    assert captured["run_id"].startswith("table_")
