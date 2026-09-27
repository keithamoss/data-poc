"""Tests for aws/lambda_handlers/*.py - the AWS event-driven MVP's
Lambda entry points (plans/running-thoughts.md #5 Thread B / docs/aws-
event-driven-mvp-design.md). Real, documented S3 ObjectCreated event
JSON shape, hand-built as fixtures (never a real S3 event or a real
Lambda invocation - no AWS access in this sandbox). orchestrate_bdm.
run_single()/orchestrate_cp.run_single()/build_cp_warehouses.
add_table_to_run() are stubbed out here - this file tests the handlers'
own event-parsing/routing/S3-upload logic, not the real 4-tool chain
(already covered, unstubbed, by tests/test_orchestrate_single_run.py)."""
from __future__ import annotations
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, "aws/lambda_handlers")
import bdm_ingest_handler  # noqa: E402
import cp_ingest_handler  # noqa: E402


def _s3_created_event(bucket: str, key: str) -> dict:
    return {"Records": [{"s3": {"bucket": {"name": bucket}, "object": {"key": key}}}]}


def test_bdm_handler_skips_an_unmatched_key(monkeypatch):
    fake_boto3 = MagicMock()
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)

    result = bdm_ingest_handler.handler(_s3_created_event("raw-bucket", "some-other-teams-file.csv"))

    body = json.loads(result["body"])
    assert body["skipped"] == 1
    assert body["processed"] == 0


def test_bdm_handler_downloads_matched_file_and_calls_run_single(monkeypatch, tmp_path):
    fake_client = MagicMock()

    def fake_download_file(bucket, key, local_path):
        with open(local_path, "w") as f:
            f.write("id\n1\n")

    fake_client.download_file.side_effect = fake_download_file
    fake_boto3 = MagicMock()
    fake_boto3.client.return_value = fake_client
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)

    captured = {}

    def fake_run_single(run_id, csv_path, run_date, reference_run_id, reference_csv):
        captured["run_id"] = run_id
        captured["reference_run_id"] = reference_run_id
        with open(csv_path) as f:
            captured["csv_content"] = f.read()
        return [{"status": "pass"}, {"status": "fail"}]

    monkeypatch.setattr(bdm_ingest_handler.orchestrate_bdm, "run_single", fake_run_single)

    result = bdm_ingest_handler.handler(_s3_created_event("raw-bucket", "bdm/birth_registrations_run_099.csv"))

    assert captured["run_id"] == "run_099"
    assert "dirty_severity" not in captured, \
        "a real arrival has no synthetic-data severity label, and the pipeline no longer has a place to put one"
    assert captured["reference_run_id"] == bdm_ingest_handler.REFERENCE_RUN_ID
    assert "1" in captured["csv_content"]
    body = json.loads(result["body"])
    assert body["processed"] == 1
    assert body["pass"] == 1
    assert body["fail"] == 1


def test_bdm_handler_uploads_nothing_anywhere(monkeypatch, tmp_path):
    """WHAT THIS REPLACED, because the absence is the assertion.

    The handler used to write QA results as JSON files into Lambda's
    /tmp - the one writable path in that runtime - and then upload each
    one to a results bucket, so a sync workflow could lay them into the
    repository's committed qa_results/ tree. The test here checked the
    uploaded key matched the tree's own layout.

    REQ-PIPE-089 records results in the database, so there is nothing to
    upload and no bucket to upload to: the redirection, the upload, the
    sync workflow, the bucket and both Lambdas' bucket-wide S3 write
    grants all went together. A handler that started writing files again
    would be silently accumulating them in a container that is about to
    be thrown away, which is why this asserts rather than assumes.
    """
    fake_client = MagicMock()
    fake_client.download_file.side_effect = lambda bucket, key, local_path: open(local_path, "w").close()
    fake_boto3 = MagicMock()
    fake_boto3.client.return_value = fake_client
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)
    monkeypatch.setattr(bdm_ingest_handler.orchestrate_bdm, "run_single", lambda *a, **k: [])

    bdm_ingest_handler.handler(_s3_created_event("raw-bucket", "bdm/birth_registrations_run_099.csv"))

    fake_client.upload_file.assert_not_called()
    fake_client.put_object.assert_not_called()


def test_neither_handler_can_reach_a_results_bucket_at_all(monkeypatch):
    """Asserted on the module rather than on a call, so that a handler
    reintroducing the name has to notice this test rather than a review
    having to."""
    for handler in (bdm_ingest_handler, cp_ingest_handler):
        assert not hasattr(handler, "RESULTS_BUCKET_NAME")
        assert not hasattr(handler, "upload_qa_result")
        assert not hasattr(handler, "patch_write_qa_result_for_lambda")


def test_cp_handler_checks_every_table_arrival_on_its_own(monkeypatch, tmp_path):
    """REQ-PIPE-105 criterion 1, and the assertion is INVERTED from what it
    was. It used to read "a single table arrival must never trigger the full
    pipeline on its own", which was the completion signal's whole premise:
    the cross-table checks needed all six tables, so five of six arrivals
    staged and stopped.

    Nothing waits now. A run reads the newest supply staged for that period
    for every table this arrival did not carry, so one file is enough to
    check - and a supply never waits on a signal a supplier may never send.
    """
    fake_client = MagicMock()
    fake_client.download_file.side_effect = lambda bucket, key, local_path: open(local_path, "w").close()
    fake_boto3 = MagicMock()
    fake_boto3.client.return_value = fake_client
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)

    captured = {}
    monkeypatch.setattr(cp_ingest_handler.build_cp_warehouses, "add_table_to_run",
                         lambda run_id, table, csv_path: captured.setdefault("calls", []).append((run_id, table)))
    monkeypatch.setattr(cp_ingest_handler.orchestrate_cp, "run_single",
                         lambda entry, reference_run_id: [{"status": "pass"}])

    result = cp_ingest_handler.handler(_s3_created_event("raw-bucket", "cp/cp_run_09/cp_clients.csv"))

    assert captured["calls"] == [("cp_run_09", "cp_clients")]
    body = json.loads(result["body"])
    assert body["tables_loaded"] == 1
    assert body["arrivals_checked"] == 1, "one file is one arrival, and an arrival is checked"
    assert body["pass"] == 1


def test_the_cp_handler_has_no_completion_tracking_left(monkeypatch):
    """Criterion 9, asserted on the module for the same reason the results
    bucket is above: a handler reintroducing a completion signal has to
    notice this test rather than a reviewer having to.

    The failure it guards is specific. Six independent upstream systems
    each landing their own table with no orchestration to coordinate a
    marker was in the retired design's own recommendation as the case that
    breaks it - and what breaks is a supply waiting silently forever.
    """
    import qa_tools.cp as cp_package

    assert not hasattr(cp_ingest_handler, "ManifestMarkerCompletionTracker")
    assert not hasattr(cp_ingest_handler, "_head_object_exists")
    # No seventh pattern: the marker file is not a supply.
    assert len(cp_ingest_handler.CP_ARRIVAL_PATTERNS) == len(cp_ingest_handler.CP_TABLE_NAMES)
    assert not any("MANIFEST" in p["keyPattern"]
                    for p in cp_ingest_handler.CP_ARRIVAL_PATTERNS)
    # And the module itself is gone rather than merely unused.
    assert not (Path(cp_package.__file__).parent / "completion_tracker.py").exists()
