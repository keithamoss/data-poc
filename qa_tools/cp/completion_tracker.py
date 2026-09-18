"""
Completion tracking for Child Protection's 6-table deliveries in the AWS
event-driven MVP (plans/running-thoughts.md #5 Thread B / docs/aws-event-
driven-mvp-design.md): Keith's own explicit call when this was scoped -
CP's cross-table referential-integrity checks must only run once ALL 6
real tables for one delivery have landed, via an "explicit completion
signal", not a timeout or a "6 files counted" heuristic inferred purely
from S3 listing.

Two real strategies behind one shared interface, so a CP ingest Lambda
handler's own logic doesn't need to know which is in use - see the design
doc's own "Child Protection: waiting for all 6 tables" section for the
full tradeoff writeup and which one is recommended as the real default.
"""
from __future__ import annotations
from abc import ABC, abstractmethod


class CompletionTracker(ABC):
    @abstractmethod
    def record_arrival(self, delivery_id: str, table: str) -> None:
        """Records that `table` has landed for `delivery_id`. Idempotent -
        recording the same (delivery_id, table) more than once (a real
        risk under S3's own at-least-once event delivery) must never
        double-count."""

    @abstractmethod
    def arrived_tables(self, delivery_id: str) -> set[str]:
        """Every distinct table recorded so far for `delivery_id`."""

    @abstractmethod
    def is_complete(self, delivery_id: str, expected_tables: set[str]) -> bool:
        """True once every one of `expected_tables` has been recorded for
        `delivery_id`."""


class InMemoryCompletionTracker(CompletionTracker):
    """For local tests and any single-process batch context - NOT safe as
    a real production Lambda tracker, since a fresh Lambda invocation
    typically gets a fresh process with no memory of a previous
    invocation's state (execution-environment reuse is real but not
    guaranteed) - see DynamoDBCompletionTracker for the real production
    alternative to ManifestMarkerCompletionTracker below."""

    def __init__(self):
        self._arrived: dict[str, set[str]] = {}

    def record_arrival(self, delivery_id: str, table: str) -> None:
        self._arrived.setdefault(delivery_id, set()).add(table)

    def arrived_tables(self, delivery_id: str) -> set[str]:
        return set(self._arrived.get(delivery_id, set()))

    def is_complete(self, delivery_id: str, expected_tables: set[str]) -> bool:
        return expected_tables.issubset(self.arrived_tables(delivery_id))


class DynamoDBCompletionTracker(CompletionTracker):
    """The real alternative to ManifestMarkerCompletionTracker (the
    recommended default - see this module's own docstring and the design
    doc) for a source system that can't guarantee a completion-marker
    file lands last: every table arrival is recorded into one DynamoDB
    item per delivery_id, using a String Set attribute (`ADD` update
    semantics - genuinely idempotent against S3's at-least-once delivery,
    adding the same table name to a set twice is a no-op, not a double-
    count) rather than a counter (which would NOT be idempotent - a
    retried S3 event would double-increment a plain number).

    Real, accepted race condition, documented rather than solved with a
    distributed lock this MVP doesn't need: two of the 6 tables' S3
    events landing on concurrent Lambda invocations at the exact moment
    the 6th, completing table arrives could both see is_complete() return
    True and both trigger orchestrate_cp.run_single() - harmless (same
    run_id, same real results, write_qa_result() just overwrites with
    identical content) but wasteful. Not exercised against a real
    DynamoDB table in this sandbox (no real AWS access) - tested against
    a mocked boto3 client instead (tests/test_completion_tracker.py)."""

    def __init__(self, table_name: str, dynamodb_client=None):
        import boto3
        self._table_name = table_name
        self._client = dynamodb_client or boto3.client("dynamodb")

    def record_arrival(self, delivery_id: str, table: str) -> None:
        self._client.update_item(
            TableName=self._table_name,
            Key={"delivery_id": {"S": delivery_id}},
            UpdateExpression="ADD arrived_tables :t",
            ExpressionAttributeValues={":t": {"SS": [table]}},
        )

    def arrived_tables(self, delivery_id: str) -> set[str]:
        response = self._client.get_item(
            TableName=self._table_name,
            Key={"delivery_id": {"S": delivery_id}},
        )
        item = response.get("Item")
        if not item:
            return set()
        return set(item.get("arrived_tables", {}).get("SS", []))

    def is_complete(self, delivery_id: str, expected_tables: set[str]) -> bool:
        return expected_tables.issubset(self.arrived_tables(delivery_id))


class ManifestMarkerCompletionTracker(CompletionTracker):
    """The recommended real default for this MVP (see the design doc's own
    "Child Protection: waiting for all 6 tables" section) - the source
    system itself writes one extra marker file once all 6 real tables for
    a delivery have landed, listing the 6 keys it just finished writing.
    No state store needed at all: record_arrival() is a real no-op here
    (every OTHER table arrival is just observability, never itself a
    completion signal), and is_complete() trusts the marker's own listed
    keys, cross-checked against `head_object_exists` (a real S3
    `head_object` call, injected rather than importing boto3 directly, so
    this stays testable with a plain fake) - protects against a source-
    system bug that writes the marker before actually finishing a slow
    upload of one of the 6 files it names."""

    def __init__(self, head_object_exists):
        # head_object_exists(bucket: str, key: str) -> bool - a thin,
        # injectable wrapper around a real `s3_client.head_object()` call
        # (see aws/lambda_handlers/cp_ingest_handler.py), not called here
        # directly so tests never need a real or mocked S3 client at all.
        self._head_object_exists = head_object_exists

    def record_arrival(self, delivery_id: str, table: str) -> None:
        pass

    def arrived_tables(self, delivery_id: str) -> set[str]:
        raise NotImplementedError(
            "ManifestMarkerCompletionTracker has no per-table state - completeness is decided directly from the "
            "marker file's own listed keys via is_complete_from_manifest(), not by counting individual arrivals")

    def is_complete(self, delivery_id: str, expected_tables: set[str]) -> bool:
        raise NotImplementedError("use is_complete_from_manifest() - this tracker has no delivery_id-keyed state")

    def is_complete_from_manifest(self, bucket: str, manifest_keys: dict[str, str]) -> bool:
        """`manifest_keys` is {table: s3_key}, as read from the real
        marker file's own JSON content. True only if every listed key
        genuinely exists in S3 right now."""
        return all(self._head_object_exists(bucket, key) for key in manifest_keys.values())
