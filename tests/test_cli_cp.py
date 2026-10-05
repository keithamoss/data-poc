"""Tests for cli/cp.py - the mothman CLI's Child Protection commands
(plans/tooling.md #1 Phase 1's own "still open" item, finished). Reuses
the same real cp_raw_dir/cp_duckdb_dir fixtures tests/test_check_cli.py
already built (real generator output, not hand-crafted rows), and drives
the Click commands through click.testing.CliRunner, same pattern as
tests/test_cli_bdm.py."""
from __future__ import annotations

from qa_tools.common import hand_filing
import os
import re
from unittest.mock import MagicMock

from click.testing import CliRunner

import cli.common as common
import cli.cp as cp
import qa_tools.cp.build_cp_warehouses as build_cp_warehouses
import qa_tools.cp.orchestrate_cp as orchestrate_cp

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
    # NOTHING LEFT TO POINT AT A RAW DIRECTORY (REQ-PIPE-102). CP
    # staging kept a second copy of every delivered file under
    # data/cp_raw/ and two of the tools read it back; all three are
    # gone, so the delivery tree above is the only thing to redirect.
    del raw_dir
    # One database, named by the environment - see the BDM
    # counterpart's own comment (REQ-PIPE-068).
    # The environment already points at this worker's database
    # (conftest's supply_dsn); duckdb_dir is what staged the data into it.


def test_arrival_path_is_resolved_live_not_frozen_at_import(monkeypatch, tmp_path):
    """The successor to the raw_dir() test this replaced (REQ-PIPE-102).

    Same property, different source: where a run's files are used to
    be a module constant, and is now whichever delivery recognition
    matches - so it has to be read at call time, not bound once.
    """
    from qa_tools.common import arrivals

    class _Arrival:
        run_id = "cp_run_001"
        path = tmp_path / "SOME_DELIVERY"

    monkeypatch.setattr(arrivals, "arrivals_for", lambda *a, **k: [_Arrival()])
    assert cp.arrival_path("cp_run_001") == str(tmp_path / "SOME_DELIVERY")
    assert cp.has_arrival("cp_run_001") is True
    assert cp.has_arrival("cp_run_999") is False


def test_default_reference_falls_back_to_manifest_first_entry_when_nothing_promoted(monkeypatch):
    monkeypatch.setattr(cp, "has_arrival", lambda run_id: run_id == "cp_run_01")
    manifest = [{"run_id": "cp_run_01"}, {"run_id": "cp_run_02"}]

    monkeypatch.setattr(cp, "list_run_ids", lambda agency, dataset: [])
    assert cp.default_reference(manifest) == "cp_run_01"


def test_default_reference_uses_last_promoted_run_when_its_data_still_exists(monkeypatch):
    monkeypatch.setattr(cp, "has_arrival", lambda run_id: run_id == "cp_run_05")
    manifest = [{"run_id": "cp_run_01"}]

    monkeypatch.setattr(cp, "list_run_ids", lambda agency, dataset: ["cp_run_02", "cp_run_05"])
    assert cp.default_reference(manifest) == "cp_run_05"


def test_default_reference_falls_back_when_last_promoted_runs_data_no_longer_exists(monkeypatch):
    monkeypatch.setattr(cp, "has_arrival", lambda run_id: run_id == "cp_run_01")
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


def test_qa_command_flag_mode_without_commit_is_a_trial(
        monkeypatch, tmp_path, cp_raw_dir, cp_duckdb_dir, cp_delivery_dirs):
    """See cli/bdm.py's counterpart: "local-only check" described the
    absence of a later promote step, and REQ-PIPE-089 made that absence
    impossible - results are recorded as a run completes. Not keeping one
    is a real thing now, a TRIAL identity that records nothing."""
    _patch_cp_dirs(monkeypatch, cp_raw_dir, cp_duckdb_dir, cp_delivery_dirs)

    result = _runner.invoke(cp.qa_command, ["--run-id", _REF_RUN_ID, "--reference-run-id", _REF_RUN_ID])

    assert result.exit_code == 0, result.output
    assert "TRIAL" in result.output
    assert "nothing was recorded" in result.output


def test_qa_command_flag_mode_commit_records_the_run_under_its_own_id(
        monkeypatch, tmp_path, cp_raw_dir, cp_duckdb_dir, cp_delivery_dirs, private_supply_dsn):
    """The kept case: the run keeps the manifest's own identity and its
    results are readable afterwards, attributed to whoever ran it."""
    from qa_tools.common import qa_results_reader as reader

    _patch_cp_dirs(monkeypatch, cp_raw_dir, cp_duckdb_dir, cp_delivery_dirs)
    monkeypatch.setattr(cp, "get_run_by", lambda: "test@example.com")

    result = _runner.invoke(cp.qa_command,
                             ["--run-id", _REF_RUN_ID, "--commit"])

    # THROUGH THE LIFECYCLE NOW (REQ-PIPE-086 criterion 9), so this one
    # table is checked against its FILED period rather than five tables
    # staged beside it - and with no siblings filed in this test's database
    # a cross-table check is red. The exit code reports the verdict; what
    # this test is about is that the run is recorded, and by whom.
    assert result.exit_code in (0, 1), result.output
    assert "Recorded" in result.output
    assert "TRIAL" not in result.output
    provenance = reader.read_run_provenance(cp.AGENCY_ID, cp.COLLECTION_ID, _REF_RUN_ID)
    assert provenance is not None, "the kept run recorded nothing"
    assert provenance["run_by"] == "test@example.com"


def test_qa_command_reports_real_failures_and_exits_nonzero(
        monkeypatch, tmp_path, cp_raw_dir, cp_duckdb_dir, cp_delivery_dirs):
    _patch_cp_dirs(monkeypatch, cp_raw_dir, cp_duckdb_dir, cp_delivery_dirs)

    result = _runner.invoke(cp.qa_command, ["--run-id", _DIRTY_RUN_ID, "--reference-run-id", _REF_RUN_ID])

    assert result.exit_code == 1, result.output
    assert "fail" in result.output.lower()


def test_qa_command_unknown_run_id_is_a_real_clean_error(monkeypatch, cp_raw_dir, cp_duckdb_dir):
    _patch_cp_dirs(monkeypatch, cp_raw_dir, cp_duckdb_dir)
    result = _runner.invoke(cp.qa_command, ["--run-id", "no-such-run"])
    assert result.exit_code != 0
    assert "no manifest entry" in result.output.lower()


def test_generate_synthetic_data_command_skips_when_declined(monkeypatch, cp_delivery_dirs):
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


def test_generate_synthetic_data_command_yes_flag_skips_confirmation(monkeypatch, cp_delivery_dirs):
    _patch_delivery_dirs(monkeypatch, cp_delivery_dirs)
    called = []
    monkeypatch.setattr(cp, "generate_synthetic_data", lambda: called.append(True))

    result = _runner.invoke(cp.generate_synthetic_data_command, ["--yes"])

    assert result.exit_code == 0
    assert called == [True]


def test_generate_synthetic_data_command_no_prompt_needed_on_first_run(monkeypatch, tmp_path):
    """No deliveries on disk yet - nothing to overwrite, so this
    shouldn't even ask."""
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

def test_qa_command_local_folder_commit_files_ONE_delivery_of_six_files(
        monkeypatch, tmp_path, cp_raw_dir, private_supply_dsn):
    """REQ-PIPE-103 criteria 1, 7 and 8 for the folder route.

    ONE DELIVERY, SIX FILES - AND SIX RUNS. They arrived together and
    a delivery is the transport unit, so ONE delivery is filed; but
    every file is its own arrival (REQ-PIPE-105 criterion 1), so it is
    checked as six, exactly as the batch would (Keith, 2026-10-02). Each
    run id comes back from recognition - the staged table's spelling at
    our receipt instant - and not from the folder's name.

    A DATABASE OF ITS OWN, because a kept supply is now FILED and
    PROMOTED like any arrival: in the shared fixture database it would
    file into the period the fixture's dirty delivery is still staged
    for, and come out contested (criterion 6) - the model working, and
    not what this test is about.
    """
    # ABOUT FILING, NOT DRIFT: in this test's empty history every earlier
    # owed period is a gap, so REQ-QAC-108's gap rule would (rightly) make
    # Evidently red and the command exit 1. That rule has its own tests.
    from qa_tools.common import drift_reference
    monkeypatch.setattr(drift_reference, "assess_arrival", lambda *a, **k: None)
    _patch_cp_dirs(monkeypatch, cp_raw_dir, private_supply_dsn,
                    (tmp_path / "deliveries", tmp_path / "receipts"))
    monkeypatch.setattr(cp, "get_run_by", lambda: "test@example.com")

    result = _runner.invoke(cp.qa_command, [
        "--commit", "--originally-received", "not-known",
        "--folder", os.path.join(cp_raw_dir, _REF_RUN_ID),
    ])

    assert result.exit_code == 0, result.output
    # SIX ARRIVALS, EACH NAMED (post-build-review #120 D8), not the first.
    assert f"was filed as {len(cp.TABLES)} arrivals" in _flat(result.output)
    filed = list((tmp_path / "deliveries").iterdir())
    assert len(filed) == 1, f"expected ONE delivery, got {[d.name for d in filed]}"
    assert len(list(filed[0].iterdir())) == len(cp.TABLES)
    # ONE RECEIPT PER FILE, in one directory for the one delivery
    # (REQ-GEN-044 criterion 12).
    assert [p.name for p in (tmp_path / "receipts").iterdir()] == [filed[0].name]
    assert len(list((tmp_path / "receipts" / filed[0].name).glob("*.json"))) == len(cp.TABLES)

    # SIX RUNS RECORDED, one per table, all at the filed delivery's one
    # receipt instant - the newest key among this worker's runs.
    from qa_tools.common import qa_results_reader as reader
    recorded = [r.split("__", 1) for r in reader.list_run_ids(
        cp.cp_common.AGENCY_ID, cp.cp_common.COLLECTION_ID) if "__" in r]
    newest = max(key for _table, key in recorded)
    six = [f"{table}__{key}" for table, key in recorded if key == newest]
    assert sorted(r.split("__", 1)[0] for r in six) == sorted(cp.TABLES), recorded


def test_qa_command_local_folder_reports_real_cp_failures(monkeypatch, tmp_path, cp_raw_dir, cp_duckdb_dir):
    _patch_cp_dirs(monkeypatch, cp_raw_dir, cp_duckdb_dir)

    result = _runner.invoke(cp.qa_command, [
        "--folder", os.path.join(cp_raw_dir, _DIRTY_RUN_ID),
        "--reference-folder", os.path.join(cp_raw_dir, _REF_RUN_ID),
    ])

    assert result.exit_code == 1, result.output
    assert "fail" in result.output.lower()
    # A TRIAL, because nobody said to keep it and there is no terminal
    # to ask (REQ-PIPE-103 criteria 2 and 8). It used to say
    # "local-only check", which described the RESULTS and said nothing
    # about whether the supply had been filed.
    assert "nothing was filed and nothing was recorded" in _flat(result.output)


def test_qa_command_local_folder_commit_records_the_run(
        monkeypatch, tmp_path, cp_raw_dir, private_supply_dsn):
    # ABOUT FILING, NOT DRIFT: in this test's empty history every earlier
    # owed period is a gap, so REQ-QAC-108's gap rule would (rightly) make
    # Evidently red and the command exit 1. That rule has its own tests.
    from qa_tools.common import drift_reference
    monkeypatch.setattr(drift_reference, "assess_arrival", lambda *a, **k: None)
    from qa_tools.common import qa_results_reader as reader

    # THE DELIVERY DIRECTORIES ARE REDIRECTED, and this test is why the
    # guard in conftest exists: `--commit` FILES a real delivery, and
    # without these two lines it filed one into this repo's own
    # data/deliveries/ on every single run. Twenty-three of them had
    # accumulated by the time CI found it - by which route is the part
    # worth knowing, because nothing looked wrong locally: they pushed a
    # bootstrap from 151 staged tables to 275, and they got themselves
    # PINNED into tests/fixtures/arrival_semantics_golden.json as two extra
    # Child Protection runs that no clean checkout has.
    _patch_cp_dirs(monkeypatch, cp_raw_dir, private_supply_dsn,
                    (tmp_path / "deliveries", tmp_path / "receipts"))
    monkeypatch.setattr(cp, "get_run_by", lambda: "test@example.com")

    result = _runner.invoke(cp.qa_command, [
        "--folder", os.path.join(cp_raw_dir, _REF_RUN_ID),
        "--commit", "--originally-received", "not-known",
    ])

    assert result.exit_code == 0, result.output
    # ONE RUN PER FILE (REQ-PIPE-105 criterion 1), each attributed.
    recorded = reader.list_run_ids(cp.AGENCY_ID, cp.COLLECTION_ID)
    assert len(recorded) == len(cp.TABLES), recorded
    for run_id in recorded:
        assert reader.read_run_provenance(cp.AGENCY_ID, cp.COLLECTION_ID,
                                           run_id)["run_by"] == "test@example.com"


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

    def _fake_run_check_local_folder(folder, reference_folder, run_by, run_id=None,
                                      run_date=None, keep=None, **kwargs):
        captured["folder"] = folder
        captured["reference_folder"] = reference_folder
        captured["run_by"] = run_by
        captured["keep"] = keep
        return ([{"status": "pass"}],
                hand_filing.Filed("", "trial_x", (folder,), None))

    monkeypatch.setattr(cp, "run_check_local_folder", _fake_run_check_local_folder)

    _fake_client = MagicMock()
    results, _filed = cp.run_check_s3_delivery(
        "my-bucket", "cp/delivery_002/", "cp/delivery_001/", "test@example.com",
        s3_client=_fake_client, keep=False)

    assert [c[0] for c in download_calls] == ["cp/delivery_002/", "cp/delivery_001/"]
    assert captured["folder"] == download_calls[0][1]
    assert captured["reference_folder"] == download_calls[1][1]
    assert captured["run_by"] == "test@example.com"
    # THE ANSWER IS WHAT TRAVELS DOWN, not a run id (REQ-PIPE-103) -
    # this mode is still "download, then Local files mode", and what
    # it must forward unchanged is the operator's decision.
    assert captured["keep"] is False
    assert results == [{"status": "pass"}]


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
                                     run_id=None, run_date=None, s3_client=None, keep=None, **kwargs):
        captured.update(bucket=bucket, delivery_prefix=delivery_prefix,
                         reference_delivery_prefix=reference_delivery_prefix, run_by=run_by,
                         run_id=run_id, keep=keep)
        return ([{"status": "pass"}],
                hand_filing.Filed("", "trial_x", (delivery_prefix,), None))

    monkeypatch.setattr(cp, "run_check_s3_delivery", _fake_run_check_s3_delivery)

    result = _runner.invoke(cp.qa_command, [
        "--trial",
        "--s3-delivery", "cp/delivery_002/",
        "--s3-reference-delivery", "cp/delivery_001/",
    ])

    assert result.exit_code == 0, result.output
    assert captured["bucket"] == "my-bucket"
    assert captured["delivery_prefix"] == "cp/delivery_002/"
    assert captured["reference_delivery_prefix"] == "cp/delivery_001/"
    assert captured["run_by"] == "trial:not-recorded"
    assert captured["run_id"] is None
    assert captured["keep"] is False
    assert "nothing was filed and nothing was recorded" in _flat(result.output)


# ---- Single-table Child Protection QA (plans/tooling.md #1 Phase 3.5) --


def test_run_check_single_table_errors_when_the_other_tables_run_has_no_arrival(monkeypatch):
    monkeypatch.setattr(cp, "has_arrival", lambda run_id: False)
    monkeypatch.setattr(cp, "load_manifest", lambda: [{"run_id": "cp_run_01"}])
    monkeypatch.setattr(cp, "default_reference", lambda manifest: "cp_run_missing")

    result_exc = None
    try:
        cp.run_check_single_table("cp_clients", "/some/cp_clients.csv", "test@example.com")
    except Exception as e:  # noqa: BLE001 - asserting the real ClickException below
        result_exc = e

    import rich_click as click
    assert isinstance(result_exc, click.ClickException)
    assert "no delivery on disk" in str(result_exc).lower()


class _FakeConn:
    """Enough of a connection for the borrow step, which is itself
    monkeypatched here - this test is about WHICH tables come from
    WHERE, not about what the database does with them."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_run_check_single_table_loads_other_5_tables_from_the_last_promoted_run(monkeypatch, tmp_path):
    """The core Phase 3.5 mechanic - verified here at the unit level
    (monkeypatched _load_delivery/add_table_to_run/orchestrate_cp.
    run_single), since the real per-tool correctness for whatever lands
    in the warehouse is already covered by the existing full-delivery
    integration tests; this test is about proving the RIGHT 6 tables
    from the RIGHT 2 sources (5 from the last Promoted run, 1 fresh)
    actually get loaded."""
    # THE REFERENCE RUN'S OWN DELIVERY is where the other five come
    # from now (REQ-PIPE-102) - it holds all six tables exactly as the
    # supplier sent them, so the second copy under data/cp_raw/ this
    # used to read had nothing the delivery did not.
    promoted_delivery = tmp_path / "CP_PROMOTED_DELIVERY"
    promoted_delivery.mkdir()
    monkeypatch.setattr(cp, "has_arrival", lambda run_id: run_id == "cp_run_promoted")
    monkeypatch.setattr(cp, "arrival_path", lambda run_id: str(promoted_delivery))
    monkeypatch.setattr(cp, "load_manifest", lambda: [{"run_id": "cp_run_01"}])
    monkeypatch.setattr(cp, "default_reference", lambda manifest: "cp_run_promoted")

    delivery_loads = []
    monkeypatch.setattr(cp, "_load_delivery", lambda run_id: delivery_loads.append(run_id))

    add_table_calls = []

    def _fake_add_table_to_run(run_id, table, csv_path, **kwargs):
        add_table_calls.append((run_id, table, csv_path))

    monkeypatch.setattr(build_cp_warehouses, "add_table_to_run", _fake_add_table_to_run)

    borrowed = {}

    def _fake_borrow_views(conn, run_id, from_run_id, tables):
        borrowed.update(run_id=run_id, from_run_id=from_run_id, tables=sorted(tables))
        return list(tables)

    monkeypatch.setattr(cp.supply_db, "borrow_views", _fake_borrow_views)
    monkeypatch.setattr(cp.supply_db, "connect", lambda **kw: _FakeConn())

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

    results, filed = cp.run_check_single_table(
        "cp_clients", "/tmp/fresh_cp_clients.csv", "test@example.com",
        run_id="table_cp_clients_001", keep=False)

    assert delivery_loads == ["cp_run_promoted"]

    # ONLY THE SUPPLIED TABLE IS STAGED (REQ-PIPE-103). The other five
    # used to be re-staged under THIS run, which recorded five tables
    # as having arrived in a delivery that carried one. They are
    # borrowed as views now - see supply_db.borrow_views().
    assert add_table_calls == [
        ("table_cp_clients_001", "cp_clients", "/tmp/fresh_cp_clients.csv")]
    assert borrowed["run_id"] == "table_cp_clients_001"
    assert borrowed["from_run_id"] == "cp_run_promoted"
    assert borrowed["tables"] == sorted(t for t in cp.TABLES if t != "cp_clients")

    # THE BORROWED TABLES ARE NOT THE DRIFT REFERENCE, and they used to
    # share an answer (REQ-QAC-108 criterion 4). Which run's other five
    # tables this check stands beside is a question about the warehouse;
    # which period's supply it is measured against is a question about
    # the records, and the orchestrator resolves it.
    assert captured["reference_run_id"] is None
    assert captured["run_by"] == "test@example.com"
    assert results == [{"status": "pass"}]
    assert filed.delivery_name == "", "a trial filed a delivery"


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

    def _fake_run_check_single_table(table, file_path, run_by, run_id=None, run_date=None,
                                      keep=None, **kwargs):
        captured.update(table=table, file_path=file_path, run_by=run_by,
                        run_id=run_id, keep=keep)
        return ([{"status": "pass"}],
                hand_filing.Filed("", "trial_x", (file_path,), None))

    monkeypatch.setattr(cp, "run_check_single_table", _fake_run_check_single_table)
    monkeypatch.setattr(cp.s3_source, "last_modified", lambda bucket, keys, s3_client=None: {})

    results, _filed = cp.run_check_s3_single_table(
        "my-bucket", "cp_clients", "cp/delivery_005/cp_clients.csv", "test@example.com",
        keep=False)

    assert download_calls == ["cp/delivery_005/cp_clients.csv"]
    assert captured["table"] == "cp_clients"
    assert captured["file_path"].endswith("cp_clients.csv")
    assert captured["run_by"] == "test@example.com"
    assert captured["keep"] is False
    assert results == [{"status": "pass"}]


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

    def _fake_run_check_single_table(table, file_path, run_by, run_id=None, run_date=None,
                                      keep=None, **kwargs):
        captured.update(table=table, file_path=file_path, run_by=run_by,
                        run_id=run_id, keep=keep)
        return ([{"status": "pass"}],
                hand_filing.Filed("", "trial_x", (file_path,), None))

    monkeypatch.setattr(cp, "run_check_single_table", _fake_run_check_single_table)

    result = _runner.invoke(cp.qa_command, ["--trial", "--table", "cp_clients", "--file", str(csv)])

    assert result.exit_code == 0, result.output
    assert captured["table"] == "cp_clients"
    assert captured["file_path"] == str(csv)
    assert captured["run_by"] == "trial:not-recorded"
    assert captured["run_id"] is None
    assert captured["keep"] is False


def test_qa_command_table_s3_key_flag_mode_calls_run_check_s3_single_table(monkeypatch):
    monkeypatch.setenv(common.S3_BUCKET_ENV_VAR, "my-bucket")

    captured = {}

    def _fake_run_check_s3_single_table(bucket, table, key, run_by, run_id=None, run_date=None,
                                         s3_client=None, keep=None, **kwargs):
        captured.update(bucket=bucket, table=table, key=key, run_by=run_by,
                        run_id=run_id, keep=keep)
        return ([{"status": "pass"}],
                hand_filing.Filed("", "trial_x", (key,), None))

    monkeypatch.setattr(cp, "run_check_s3_single_table", _fake_run_check_s3_single_table)

    result = _runner.invoke(cp.qa_command, [
        "--trial", "--table", "cp_clients", "--s3-key", "cp/delivery_005/cp_clients.csv",
    ])

    assert result.exit_code == 0, result.output
    assert captured["bucket"] == "my-bucket"
    assert captured["table"] == "cp_clients"
    assert captured["key"] == "cp/delivery_005/cp_clients.csv"
    assert captured["run_by"] == "trial:not-recorded"
    assert captured["run_id"] is None
    assert captured["keep"] is False
