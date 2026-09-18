"""Tests for qa_tools/cp/completion_tracker.py - CP's explicit-completion-
signal design for the AWS event-driven MVP (plans/running-thoughts.md #5
Thread B / docs/aws-event-driven-mvp-design.md). DynamoDBCompletionTracker
is tested against a mocked boto3 client (no `moto` dependency, no real
AWS) - real proof of the exact calls it makes, not just its return value."""
from __future__ import annotations
from unittest.mock import MagicMock

from qa_tools.cp.completion_tracker import (
    DynamoDBCompletionTracker,
    InMemoryCompletionTracker,
    ManifestMarkerCompletionTracker,
)

_EXPECTED_TABLES = {"cp_clients", "cp_notifications", "cp_investigations", "cp_placements", "cp_carers",
                     "cp_case_workers"}


def test_in_memory_tracker_is_not_complete_until_all_tables_recorded():
    tracker = InMemoryCompletionTracker()
    for table in ["cp_clients", "cp_notifications", "cp_investigations", "cp_placements", "cp_carers"]:
        tracker.record_arrival("cp_run_09", table)
        assert not tracker.is_complete("cp_run_09", _EXPECTED_TABLES)

    tracker.record_arrival("cp_run_09", "cp_case_workers")
    assert tracker.is_complete("cp_run_09", _EXPECTED_TABLES)


def test_in_memory_tracker_keeps_separate_deliveries_independent():
    tracker = InMemoryCompletionTracker()
    for table in _EXPECTED_TABLES:
        tracker.record_arrival("cp_run_09", table)
    assert tracker.is_complete("cp_run_09", _EXPECTED_TABLES)
    assert not tracker.is_complete("cp_run_10", _EXPECTED_TABLES)


def test_in_memory_tracker_recording_the_same_table_twice_is_idempotent():
    tracker = InMemoryCompletionTracker()
    tracker.record_arrival("cp_run_09", "cp_clients")
    tracker.record_arrival("cp_run_09", "cp_clients")
    assert tracker.arrived_tables("cp_run_09") == {"cp_clients"}


def test_dynamodb_tracker_record_arrival_uses_a_string_set_add_not_a_counter():
    """The idempotency-under-retried-S3-events guarantee (module docstring)
    depends on real DynamoDB ADD-to-String-Set semantics, not a plain
    counter increment - proven by asserting the real call shape, not just
    trusting the docstring's claim."""
    client = MagicMock()
    tracker = DynamoDBCompletionTracker("cp-delivery-completion", dynamodb_client=client)

    tracker.record_arrival("cp_run_09", "cp_clients")

    client.update_item.assert_called_once_with(
        TableName="cp-delivery-completion",
        Key={"delivery_id": {"S": "cp_run_09"}},
        UpdateExpression="ADD arrived_tables :t",
        ExpressionAttributeValues={":t": {"SS": ["cp_clients"]}},
    )


def test_dynamodb_tracker_arrived_tables_reads_back_the_string_set():
    client = MagicMock()
    client.get_item.return_value = {"Item": {"arrived_tables": {"SS": ["cp_clients", "cp_carers"]}}}
    tracker = DynamoDBCompletionTracker("cp-delivery-completion", dynamodb_client=client)

    assert tracker.arrived_tables("cp_run_09") == {"cp_clients", "cp_carers"}
    client.get_item.assert_called_once_with(
        TableName="cp-delivery-completion", Key={"delivery_id": {"S": "cp_run_09"}})


def test_dynamodb_tracker_arrived_tables_handles_a_delivery_with_no_item_yet():
    client = MagicMock()
    client.get_item.return_value = {}
    tracker = DynamoDBCompletionTracker("cp-delivery-completion", dynamodb_client=client)

    assert tracker.arrived_tables("cp_run_09") == set()


def test_dynamodb_tracker_is_complete_true_only_once_all_6_present():
    client = MagicMock()
    client.get_item.return_value = {"Item": {"arrived_tables": {"SS": list(_EXPECTED_TABLES - {"cp_carers"})}}}
    tracker = DynamoDBCompletionTracker("cp-delivery-completion", dynamodb_client=client)
    assert not tracker.is_complete("cp_run_09", _EXPECTED_TABLES)

    client.get_item.return_value = {"Item": {"arrived_tables": {"SS": list(_EXPECTED_TABLES)}}}
    assert tracker.is_complete("cp_run_09", _EXPECTED_TABLES)


def test_manifest_marker_tracker_complete_only_when_every_listed_key_exists():
    seen = set()

    def fake_head_object_exists(bucket, key):
        return key in seen

    tracker = ManifestMarkerCompletionTracker(fake_head_object_exists)
    manifest_keys = {"cp_clients": "raw/cp/cp_run_09/cp_clients.csv", "cp_carers": "raw/cp/cp_run_09/cp_carers.csv"}

    assert not tracker.is_complete_from_manifest("my-bucket", manifest_keys)

    seen.add("raw/cp/cp_run_09/cp_clients.csv")
    assert not tracker.is_complete_from_manifest("my-bucket", manifest_keys)

    seen.add("raw/cp/cp_run_09/cp_carers.csv")
    assert tracker.is_complete_from_manifest("my-bucket", manifest_keys)


def test_manifest_marker_tracker_record_arrival_is_a_real_no_op():
    tracker = ManifestMarkerCompletionTracker(lambda bucket, key: True)
    tracker.record_arrival("cp_run_09", "cp_clients")  # must not raise - no state to update
