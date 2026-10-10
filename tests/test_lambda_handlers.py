"""The S3 handlers record each arriving object as a delivery and then run
the processing pass (REQ-PIPE-152). A real, documented S3 ObjectCreated
event shape, hand-built, and a mocked S3 client - never a real Lambda
invocation, since this sandbox has no AWS access. Recording runs against
this worker's real database; the pass itself is stubbed where a test is
about the handler, since the pass has its own tests
(tests/test_processing_pass.py).

WHAT WENT, AND WHY. The tests this module used to carry pinned the handlers
calling orchestrate_bdm.run_single/orchestrate_cp.run_single with a run id
taken from the key - the stage-and-check shortcut REQ-PIPE-152 removes - and
stubbed run_single loosely enough that the handler's `reference_csv=`
TypeError went unnoticed. Asserting that retired behaviour would only
defend it.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, "aws/lambda_handlers")
import bdm_ingest_handler  # noqa: E402
import cp_ingest_handler  # noqa: E402

from qa_tools.common import processing_pass, qa_store, s3_arrival, supply_db  # noqa: E402

LANDED = datetime(2031, 5, 6, 1, 2, 3, tzinfo=timezone.utc)


def _s3_created_event(bucket: str, *keys: str) -> dict:
    return {"Records": [{"s3": {"bucket": {"name": bucket}, "object": {"key": k}}}
                        for k in keys]}


def _client(last_modified=LANDED):
    client = MagicMock()
    client.head_object.return_value = {"LastModified": last_modified}
    client.download_file.side_effect = lambda b, k, p: Path(p).write_text("id\n1\n")
    return client


@pytest.fixture
def no_pass(monkeypatch):
    """The pass, stubbed: what the handler handed it, and when."""
    calls = []

    def _run_pass(**kwargs):
        calls.append(kwargs)
        return processing_pass.PassReport()

    monkeypatch.setattr(processing_pass, "run_pass", _run_pass)
    return calls


def _files(delivery_name: str) -> list[tuple]:
    with supply_db.connect(read_only=True, label="test-lambda") as conn:
        return conn.execute(
            f'SELECT f.filename, f.dataset_id, f.received_instant, f.received_from, '
            f'f.storage_uri, d.filed_by_kind FROM "{qa_store.SCHEMA}".delivery_file f '
            f'JOIN "{qa_store.SCHEMA}".delivery d ON d.name = f.delivery '
            f"WHERE f.delivery = ?", [delivery_name]).fetchall()


class TestAnObjectIsRecordedAsADelivery:
    """Criteria 1-4 and 10."""

    def test_the_rows_name_the_object_and_its_storage_receipt(self, supply_dsn, no_pass):
        key = "cp/2031-05/cp_clients.csv"
        bucket = f"raw-{__import__('uuid').uuid4().hex[:8]}"
        s3_arrival.handle_event(
            _s3_created_event(bucket, key), _client(), prefix="cp/")
        name = s3_arrival.delivery_name_for(bucket, key, LANDED)
        [(filename, dataset_id, instant, source, uri, kind)] = _files(name)
        assert (filename, dataset_id) == ("cp_clients.csv", "cp-clients")
        assert instant == LANDED and source == "storage"
        assert uri == f"s3://{bucket}/{key}"
        assert kind == "automated"

    def test_nothing_is_copied_anywhere(self, supply_dsn, no_pass):
        client = _client()
        s3_arrival.handle_event(_s3_created_event("raw-x", "bdm/birth_registrations_x.csv"),
                                client, prefix="bdm/")
        client.upload_file.assert_not_called()
        client.put_object.assert_not_called()
        client.copy_object.assert_not_called()
        client.download_file.assert_not_called()


class TestARetryRecordsNothingTwice:
    """Criterion 7."""

    def test_the_same_object_twice_is_one_delivery(self, supply_dsn, no_pass):
        bucket = f"raw-{__import__('uuid').uuid4().hex[:8]}"
        event = _s3_created_event(bucket, "bdm/birth_registrations_r.csv")
        first = json.loads(s3_arrival.handle_event(event, _client(), prefix="bdm/")["body"])
        second = json.loads(s3_arrival.handle_event(event, _client(), prefix="bdm/")["body"])
        assert (first["recorded"], second["recorded"], second["already_recorded"]) == (1, 0, 1)
        name = s3_arrival.delivery_name_for(bucket, "bdm/birth_registrations_r.csv", LANDED)
        assert len(_files(name)) == 1


class TestAnUnplaceableObjectIsReportedAndTheRestCarryOn:
    """Criterion 9."""

    def test_it_is_recorded_unattributed_and_the_next_object_still_is(self, supply_dsn,
                                                                       no_pass):
        bucket = f"raw-{__import__('uuid').uuid4().hex[:8]}"
        body = json.loads(s3_arrival.handle_event(
            _s3_created_event(bucket, "cp/covering_note.pdf", "cp/cp_carers.csv"),
            _client(), prefix="cp/")["body"])
        assert body["unplaceable"] == 1 and body["recorded"] == 2
        [(_, dataset_id, *_)] = _files(s3_arrival.delivery_name_for(
            bucket, "cp/covering_note.pdf", LANDED))
        assert dataset_id is None


class TestTheHandlerOnlyRecordsThenRunsThePass:
    """Criteria 5, 8, 11, 12 and 13."""

    def test_the_pass_runs_once_with_the_budget_after_recording(self, supply_dsn, no_pass):
        s3_arrival.handle_event(_s3_created_event("raw-y", "bdm/birth_registrations_y.csv"),
                                _client(), prefix="bdm/")
        [call] = no_pass
        assert call["deadline"] is not None and call["s3_client"] is not None

    def test_neither_handler_calls_the_single_run_entry_point(self):
        for module in (bdm_ingest_handler, cp_ingest_handler, s3_arrival):
            assert "run_single" not in Path(module.__file__).read_text().replace(
                "never calls run_single", "")

    def test_the_bdm_handler_does_not_raise_on_its_first_object(self, supply_dsn, no_pass,
                                                                monkeypatch):
        """Criterion 11, confirmed failing first against the handler that
        passed `reference_csv=` to run_single: it now records the object and
        runs the pass, without raising."""
        monkeypatch.setitem(sys.modules, "boto3", MagicMock(client=lambda *_: _client()))
        result = bdm_ingest_handler.handler(_s3_created_event(
            "raw-z", "bdm/birth_registrations_run_099.csv"))
        assert result["statusCode"] == 200

    def test_a_held_pass_lock_fails_the_invocation_after_recording(self, supply_dsn,
                                                                   monkeypatch):
        from contextlib import contextmanager

        @contextmanager
        def held(command):
            raise processing_pass.PassLockHeld("process", "a moment ago")
            yield

        monkeypatch.setattr(processing_pass, "pass_lock", held)
        bucket = f"raw-{__import__('uuid').uuid4().hex[:8]}"
        with pytest.raises(processing_pass.PassLockHeld):
            s3_arrival.handle_event(_s3_created_event(bucket, "cp/cp_clients.csv"),
                                    _client(), prefix="cp/")
        assert _files(s3_arrival.delivery_name_for(bucket, "cp/cp_clients.csv", LANDED)), (
            "recorded before the refusal, so the platform's retry finds it")

    def test_an_object_outside_the_prefix_is_not_this_handlers(self, supply_dsn, no_pass):
        body = json.loads(s3_arrival.handle_event(
            _s3_created_event("raw-w", "elsewhere/cp_clients.csv"), _client(),
            prefix="cp/")["body"])
        assert body["skipped"] == 1 and body["recorded"] == 0


class TestEveryObjectInAnEventIsTried:
    """post-build-review #131 D2: S3 event notifications URL-encode the key,
    and one object that cannot be read must not stop the event's others."""

    def test_an_encoded_key_is_decoded_before_it_is_read(self, supply_dsn, no_pass):
        bucket = f"raw-{__import__('uuid').uuid4().hex[:8]}"
        client = _client()
        s3_arrival.handle_event(_s3_created_event(bucket, "cp/cp_carers+%282%29.csv"),
                                client, prefix="cp/")
        assert client.head_object.call_args.kwargs["Key"] == "cp/cp_carers (2).csv"

    def test_one_unreadable_object_does_not_stop_the_rest_and_still_fails_for_retry(
            self, supply_dsn, no_pass):
        bucket = f"raw-{__import__('uuid').uuid4().hex[:8]}"
        client = _client()

        def head(**kw):
            if kw["Key"] == "cp/gone.csv":
                raise RuntimeError("NoSuchKey")
            return {"LastModified": LANDED}
        client.head_object.side_effect = head
        with pytest.raises(s3_arrival.ObjectsNotRecorded, match="gone.csv"):
            s3_arrival.handle_event(_s3_created_event(bucket, "cp/gone.csv", "cp/cp_carers.csv"),
                                    client, prefix="cp/")
        assert _files(s3_arrival.delivery_name_for(bucket, "cp/cp_carers.csv", LANDED))
        assert len(no_pass) == 1, "the pass still runs for what was recorded"
