"""Lambda handler for Birth Registrations objects arriving under the raw
bucket's `bdm/` prefix (see aws/cdk/data_pipeline_stack.py for the wiring).

IT RECORDS, THEN RUNS THE PROCESSING PASS (REQ-PIPE-152). Each arriving
object is recorded as a delivery - REQ-PIPE-144's rows, its receipt from
storage, its dataset from the declared pattern - and REQ-PIPE-151's pass
then does what the terminal and the batch do: file, check and gate, in
global receipt order. It used to call the single-run entry point, which
files nothing and promotes nothing, took its run id from the key and its
date from the Lambda's clock - and passed a `reference_csv=` that
entry point no longer accepts, so it raised on its first object.

**Never invoked by a real Lambda runtime in this sandbox** (no AWS access
here); exercised by tests/test_lambda_handlers.py with a mocked S3 client.
"""
from __future__ import annotations

from qa_tools.common import s3_arrival

#: The prefix this handler's objects arrive under.
PREFIX = "bdm/"


def handler(event: dict, context=None) -> dict:
    import boto3

    return s3_arrival.handle_event(event, boto3.client("s3"), prefix=PREFIX)
