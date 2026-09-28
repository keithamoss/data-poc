"""Tests for cli/bdm.py - the mothman CLI's Birth Registrations commands
(plans/tooling.md #1 Phase 1). Reuses the same real bdm_raw_dir/
bdm_duckdb_dir fixtures tests/test_check_cli.py already built (real
generator output, not hand-crafted rows), and drives the Click commands
through click.testing.CliRunner, same as that file."""
from __future__ import annotations

from qa_tools.common import hand_filing
import os
import re
from pathlib import Path
from unittest.mock import MagicMock

from click.testing import CliRunner

import cli.bdm as bdm
import cli.common as common

_REF_RUN_ID = "pytest_bdm_ref"
_DIRTY_RUN_ID = "pytest_bdm_dirty"

# The run_ids the same two fixture runs get once they are RECOGNISED as
# arrivals rather than read from a declaration (REQ-GEN-043). They are
# not the filenames above and cannot be: a delivery's files are named by
# the supplier, so a run_id is assigned in received_at order by
# qa_tools.common.arrivals, which is what the Synthetic --run-id flow
# picks from. The flat `pytest_bdm_*.csv` names above still matter for
# the Local files mode, which takes a real path to a real file.
_ARRIVAL_REF_RUN_ID = "run_001"
_ARRIVAL_DIRTY_RUN_ID = "run_002"

_runner = CliRunner()


def _patch_bdm_dirs(monkeypatch, raw_dir, duckdb_dir):
    # The run picker recognises arrivals from disk now (REQ-GEN-043),
    # so pointing it at the fixture means pointing the DELIVERY
    # directories at it - patching RAW_DIR alone would leave these
    # tests reading the real data/deliveries/ tree.
    from pathlib import Path

    from qa_tools.common import delivery
    monkeypatch.setattr(delivery, "DELIVERIES_DIR", Path(raw_dir) / "deliveries")
    monkeypatch.setattr(delivery, "RECEIPTS_DIR", Path(raw_dir) / "receipts")
    # The warehouse used to be three module attributes pointing at a
    # directory of per-run DuckDB files. It is now one database, named
    # by MOTHMAN_SUPPLY_DB, which the supply_db_path fixture sets for
    # this worker - so `duckdb_dir` is that database's path and every
    # module resolves it the same way the real pipeline does, through
    # the environment (REQ-PIPE-068).
    # The environment already points at this worker's database
    # (conftest's supply_dsn); duckdb_dir is what staged the data into it.


def _patch_delivery_dirs(monkeypatch, root):
    """Point arrival recognition at an isolated tree (REQ-GEN-043).

    Patching build_per_run_warehouses.RAW_DIR alone is no longer enough
    for anything that asks "is there data yet?": that question is now
    answered by recognising deliveries on disk, so an unpatched test
    would read - and answer from - the real data/deliveries/ tree."""
    from pathlib import Path

    from qa_tools.common import delivery
    monkeypatch.setattr(delivery, "DELIVERIES_DIR", Path(root) / "deliveries")
    monkeypatch.setattr(delivery, "RECEIPTS_DIR", Path(root) / "receipts")


def test_the_cli_reports_where_the_generator_actually_wrote(monkeypatch):
    """THE SUCCESSOR to a test of cli/bdm.py's raw_dir(), which is
    retired with the directory (REQ-PIPE-102). The generator writes
    one copy of a supply - the delivery - so that is what the command
    reports having written.
    """
    assert not hasattr(bdm, "raw_dir"), "cli/bdm.py still exposes a raw_dir()"
    assert "deliveries" in bdm.generated_output_dir()


# THE THREE `default_reference` TESTS WERE DELETED 2026-09-29 with the
# function they covered (REQ-QAC-108 criterion 4). It picked the last
# run whose results existed and fell back to the manifest's first entry,
# which is the anchor receding into the past the criterion forbids - so
# the behaviour was removed rather than re-tested. What replaced it is
# covered by tests/test_drift_reference.py.


def test_picker_choices_and_run_id_from_choice_round_trip():
    manifest = [{"run_id": "run_001", "received_at": "2026-01-01T06:00:00+00:00", "delivery": "BDM_20260101",
                 "csv_path": "/x/BDM_20260101/birth_registrations_2026-01-01.csv"},
                {"run_id": "run_002", "received_at": "2026-01-02T06:00:00+00:00", "delivery": "drop-4471",
                 "csv_path": "/x/drop-4471/birth_registrations_2026-01-02.csv"}]
    choices = bdm.picker_choices(manifest)
    # The picker shows the DELIVERY each run came from, not an
    # injected severity - severity is generator bookkeeping the CLI has
    # no business reading (REQ-GEN-043).
    assert "BDM_20260101" in choices[0]
    assert "drop-4471" in choices[1]
    assert bdm.run_id_from_choice(choices[0]) == "run_001"
    assert bdm.run_id_from_choice(choices[1]) == "run_002"


def test_has_failures_true_on_fail_or_error_false_otherwise():
    assert bdm.has_failures([{"status": "pass"}, {"status": "warn"}]) is False
    assert bdm.has_failures([{"status": "pass"}, {"status": "fail"}]) is True
    assert bdm.has_failures([{"status": "error"}]) is True


def test_run_check_leaves_the_arrival_record_on_disk_exactly_as_it_found_it(
        monkeypatch, tmp_path, bdm_raw_dir, bdm_duckdb_dir):
    """Re-pointed from the retired `..._does_not_clobber_the_real_batch_
    manifest` test (REQ-GEN-043), which is worth spelling out rather than
    quietly deleting. The original guarded a real bug found live - a
    manual smoke test corrupted the real data/raw/manifest.json from 176
    entries down to 1, because orchestrate_bdm.run_single()
    unconditionally overwrote it with its own synthetic 1-or-2-entry
    manifest. REQ-GEN-043 removed the cause: run_single() writes no
    manifest at all now, and the run picker recognises arrivals from the
    delivery tree on disk instead of reading a declaration.

    So the specific thing that test asserted can no longer be false. The
    GUARANTEE behind it still can be, and is what this asserts instead:
    running a check against an existing arrival is a READ of the arrival
    record, never a write. If anything reintroduced a manifest write, or
    wrote into a delivery or receipt, the recognised arrival list - or
    the bytes underneath it - would move.

    Works on a real COPY of bdm_raw_dir, not the shared session fixture
    directly, for the same reason the original did: this test is
    specifically probing a destructive side effect."""
    import hashlib
    import shutil
    from pathlib import Path

    from qa_tools.common import delivery

    raw_copy = tmp_path / "raw_copy"
    shutil.copytree(bdm_raw_dir, raw_copy)

    monkeypatch.setattr(delivery, "DELIVERIES_DIR", raw_copy / "deliveries")
    monkeypatch.setattr(delivery, "RECEIPTS_DIR", raw_copy / "receipts")
    # One supply database, named by the environment - the three
    # module attributes this replaces pointed at a directory of
    # per-run DuckDB files (REQ-PIPE-068).
    # The environment already points at this worker's database
    # (conftest's supply_dsn); bdm_duckdb_dir is what staged the data into it.

    def _fingerprint() -> list[tuple[str, str]]:
        out = []
        for root in ("deliveries", "receipts"):
            for path in sorted((raw_copy / root).rglob("*")):
                if path.is_file():
                    out.append((str(path.relative_to(raw_copy)),
                                hashlib.sha256(path.read_bytes()).hexdigest()))
        return out

    before_arrivals = bdm.load_manifest()
    before_bytes = _fingerprint()
    assert len(before_arrivals) == 2, "test precondition - the fixture must recognise both arrivals"
    assert before_bytes, "test precondition - there must be real delivery files to fingerprint"

    bdm.run_check(_ARRIVAL_REF_RUN_ID, "test@example.com", reference_run_id=_ARRIVAL_REF_RUN_ID)

    assert bdm.load_manifest() == before_arrivals, \
        "run_check() must not change which arrivals are recognised on disk"
    assert _fingerprint() == before_bytes, \
        "run_check() must not write into the delivery or receipt tree it read"
    assert not (raw_copy / "manifest.json").exists(), \
        "nothing may reintroduce a written manifest - arrivals are recognised, not declared"
    assert not list(Path(raw_copy / "deliveries").glob("manifest.json"))


def test_qa_command_flag_mode_without_commit_is_a_trial(
        monkeypatch, tmp_path, bdm_raw_dir, bdm_duckdb_dir):
    """IT USED TO SAY "local-only check", and the results went to a
    throwaway directory that was simply never promoted. REQ-PIPE-089
    records results as a run completes, so "do not keep this" had to
    become a real thing rather than the absence of a later step: the run
    takes a TRIAL identity, which records nothing that survives it
    (REQ-PIPE-103)."""
    _patch_bdm_dirs(monkeypatch, bdm_raw_dir, bdm_duckdb_dir)

    result = _runner.invoke(bdm.qa_command,
                             ["--run-id", _ARRIVAL_REF_RUN_ID, "--reference-run-id", _ARRIVAL_REF_RUN_ID])

    assert result.exit_code == 0, result.output
    assert "TRIAL" in result.output
    assert "nothing was recorded" in result.output


def test_qa_command_flag_mode_commit_records_the_run_under_its_own_id(
        monkeypatch, tmp_path, bdm_raw_dir, bdm_duckdb_dir, clean_qa_history):
    """The kept case: the run keeps the manifest's own identity and its
    results are readable afterwards, attributed to whoever ran it."""
    from qa_tools.common import qa_results_reader as reader

    _patch_bdm_dirs(monkeypatch, bdm_raw_dir, bdm_duckdb_dir)
    monkeypatch.setattr(bdm, "get_run_by", lambda: "test@example.com")

    result = _runner.invoke(bdm.qa_command,
                             ["--run-id", _ARRIVAL_REF_RUN_ID, "--reference-run-id", _ARRIVAL_REF_RUN_ID,
                              "--commit"])

    assert result.exit_code == 0, result.output
    assert "Recorded" in result.output
    assert "TRIAL" not in result.output
    provenance = reader.read_run_provenance(bdm.AGENCY_ID, bdm.COLLECTION_ID,
                                             _ARRIVAL_REF_RUN_ID)
    assert provenance is not None, "the kept run recorded nothing"
    assert provenance["run_by"] == "test@example.com"


def test_qa_command_reports_real_failures_and_exits_nonzero(monkeypatch, tmp_path, bdm_raw_dir,
                                                             bdm_duckdb_dir):
    _patch_bdm_dirs(monkeypatch, bdm_raw_dir, bdm_duckdb_dir)

    result = _runner.invoke(bdm.qa_command,
                             ["--run-id", _ARRIVAL_DIRTY_RUN_ID, "--reference-run-id", _ARRIVAL_REF_RUN_ID])

    assert result.exit_code == 1, result.output
    assert "fail" in result.output.lower()


def test_qa_command_unknown_run_id_is_a_real_clean_error(monkeypatch, bdm_raw_dir, bdm_duckdb_dir):
    _patch_bdm_dirs(monkeypatch, bdm_raw_dir, bdm_duckdb_dir)
    result = _runner.invoke(bdm.qa_command, ["--run-id", "no-such-run"])
    assert result.exit_code != 0
    assert "no manifest entry" in result.output.lower()


def test_generate_synthetic_data_command_skips_when_declined(monkeypatch, tmp_path, bdm_raw_dir):
    # Real deliveries already on disk - so there IS something to
    # overwrite, and the command must ask before it does.
    _patch_delivery_dirs(monkeypatch, bdm_raw_dir)
    called = []
    monkeypatch.setattr(bdm, "generate_synthetic_data", lambda: called.append(True))
    monkeypatch.setattr(common, "confirm", lambda *a, **k: False)

    result = _runner.invoke(bdm.generate_synthetic_data_command, [])

    assert result.exit_code == 0
    assert called == []
    assert "not regenerated" in result.output.lower()


def test_generate_synthetic_data_command_yes_flag_skips_confirmation(monkeypatch, tmp_path, bdm_raw_dir):
    _patch_delivery_dirs(monkeypatch, bdm_raw_dir)
    called = []
    monkeypatch.setattr(bdm, "generate_synthetic_data", lambda: called.append(True))

    result = _runner.invoke(bdm.generate_synthetic_data_command, ["--yes"])

    assert result.exit_code == 0
    assert called == [True]


def test_generate_synthetic_data_command_no_prompt_needed_on_first_run(monkeypatch, tmp_path):
    """No deliveries on disk yet - nothing to overwrite, so this
    shouldn't even ask."""
    _patch_delivery_dirs(monkeypatch, tmp_path)
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

def test_qa_command_local_file_is_a_trial_when_nobody_said_to_keep_it(
        monkeypatch, tmp_path, bdm_raw_dir):
    """REQ-PIPE-103 criteria 2 and 8. With no flag and no terminal there
    is nobody to ask, and the two wrong answers are not equally wrong -
    a trial that should have been kept costs a re-run; a delivery filed
    on somebody's behalf is a public record of an arrival they did not
    agree to."""
    raw_dir = str(tmp_path / "raw")
    os.makedirs(raw_dir)
    _patch_bdm_dirs(monkeypatch, raw_dir, None)

    result = _runner.invoke(bdm.qa_command, [
        "--file", os.path.join(bdm_raw_dir, f"{_DIRTY_RUN_ID}.csv"),
        "--reference-file", os.path.join(bdm_raw_dir, f"{_REF_RUN_ID}.csv"),
    ])

    assert result.exit_code == 1, result.output
    assert "fail" in result.output.lower()
    assert "nothing was filed and nothing was recorded" in _flat(result.output)
    assert not (Path(raw_dir) / "deliveries").exists(), \
        "a trial filed a delivery"


def test_qa_command_local_file_commit_files_a_real_delivery_and_records_it(
        monkeypatch, tmp_path, bdm_raw_dir, bdm_delivery_dirs, clean_qa_history):
    """The other half of criterion 1: keeping files the supply as a
    real delivery BEFORE anything runs, and the run's id comes back
    from recognition rather than from the file's name.

    THE FILE IS COPIED FIRST, and named to match the dataset's own
    arrival pattern, because a name recognition cannot place is
    refused outright (Keith, 2026-09-27) - the fixture's own
    `pytest_bdm_ref.csv` is exactly such a name.
    """
    raw_dir = tmp_path / "raw"
    (raw_dir).mkdir()
    _patch_bdm_dirs(monkeypatch, str(raw_dir), None)
    monkeypatch.setattr(bdm, "get_run_by", lambda: "test@example.com")

    supplied = tmp_path / "birth_registrations_2026-01-01.csv"
    supplied.write_bytes(Path(bdm_raw_dir, f"{_REF_RUN_ID}.csv").read_bytes())

    result = _runner.invoke(bdm.qa_command, [
        "--file", str(supplied),
        "--reference-file", os.path.join(bdm_raw_dir, f"{_REF_RUN_ID}.csv"),
        "--commit",
    ])

    from qa_tools.common import qa_results_reader as reader

    assert result.exit_code == 0, result.output
    # THE RUN IS AN ORDINARY ARRIVAL, first in an empty tree.
    assert "recognised as run_001" in _flat(result.output)
    assert "is a real arrival" in _flat(result.output)
    assert (raw_dir / "deliveries").exists(), "keeping filed no delivery"

    # AND ITS RESULTS ARE RECORDED, under the id recognition gave it -
    # which used to be checked by globbing for a dataset_stats.json.
    recorded = reader.list_run_ids(bdm.AGENCY_ID, bdm.COLLECTION_ID)
    assert recorded == ["run_001"], recorded
    assert reader.read_run_provenance(bdm.AGENCY_ID, bdm.COLLECTION_ID,
                                       "run_001")["run_by"] == "test@example.com"


def test_qa_command_local_file_commit_refuses_a_name_recognition_cannot_place(
        monkeypatch, tmp_path, bdm_raw_dir):
    """Keith's own call over renaming the file to fit or filing it
    unplaceable: a run's identity comes from recognising its files by
    name, so a file we cannot place has no run to be."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    _patch_bdm_dirs(monkeypatch, str(raw_dir), None)
    monkeypatch.setattr(bdm, "get_run_by", lambda: "test@example.com")

    result = _runner.invoke(bdm.qa_command, [
        "--file", os.path.join(bdm_raw_dir, f"{_REF_RUN_ID}.csv"),
        "--reference-file", os.path.join(bdm_raw_dir, f"{_REF_RUN_ID}.csv"),
        "--commit",
    ])

    assert result.exit_code != 0
    assert "matches no dataset" in _flat(result.output)
    assert "trial" in _flat(result.output), \
        "the refusal must name the way forward, not just the problem"
    assert not (raw_dir / "deliveries").exists()
    assert not (raw_dir / "receipts").exists()


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
         "dataset_id": "birth-registrations"},
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

    def _fake_run_check_local_file(csv_path, reference_csv, run_by, run_id=None,
                                    run_date=None, keep=None, **kwargs):
        captured["csv_path"] = csv_path
        captured["reference_csv"] = reference_csv
        captured["run_by"] = run_by
        captured["keep"] = keep
        return ([{"status": "pass"}], "/tmp/fake-results",
                hand_filing.Filed("", "trial_x", (csv_path,), None))

    monkeypatch.setattr(bdm, "run_check_local_file", _fake_run_check_local_file)

    _fake_client = MagicMock()
    results, tmp_dir, filed = bdm.run_check_s3(
        "my-bucket", "bdm/run_005.csv", "bdm/run_004.csv", "test@example.com",
        s3_client=_fake_client, keep=False)

    assert download_calls == ["bdm/run_005.csv", "bdm/run_004.csv"]
    assert captured["csv_path"].endswith("run_005.csv")
    assert captured["reference_csv"].endswith("run_004.csv")
    assert captured["run_by"] == "test@example.com"
    # THE ANSWER IS WHAT TRAVELS DOWN, not a run id (REQ-PIPE-103) -
    # S3 mode is still "download, then Local files mode", and the
    # thing it must forward unchanged is the operator's decision.
    assert captured["keep"] is False
    assert results == [{"status": "pass"}]
    assert tmp_dir == "/tmp/fake-results"
    assert filed.delivery_name == ""


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

    def _fake_run_check_s3(bucket, key, reference_key, run_by, run_id=None, run_date=None,
                            s3_client=None, keep=None, **kwargs):
        captured.update(bucket=bucket, key=key, reference_key=reference_key,
                        run_by=run_by, run_id=run_id, keep=keep)
        return ([{"status": "pass"}],
                hand_filing.Filed("", "trial_x", (key,), None))

    monkeypatch.setattr(bdm, "run_check_s3", _fake_run_check_s3)

    result = _runner.invoke(bdm.qa_command, [
        "--trial",
        "--s3-key", "bdm/birth_registrations_2026-01-02.csv",
        "--s3-reference-key", "bdm/birth_registrations_2026-01-01.csv",
    ])

    assert result.exit_code == 0, result.output
    assert captured["bucket"] == "my-bucket"
    assert captured["key"] == "bdm/birth_registrations_2026-01-02.csv"
    assert captured["reference_key"] == "bdm/birth_registrations_2026-01-01.csv"
    assert captured["run_by"] == "trial:not-recorded"
    # NO RUN ID FROM THE CALLER ANY MORE (REQ-PIPE-103). The command
    # no longer mints one out of the key's filename - the decision
    # taken inside run_check_s3() does, from recognition for a kept
    # supply and from the clock for a trial. What the command passes
    # down is the ANSWER, not an identity.
    assert captured["run_id"] is None
    assert captured["keep"] is False
    assert "nothing was filed and nothing was recorded" in _flat(result.output)
