"""Lambda handler for Child Protection objects arriving under the raw
bucket's `cp/` prefix (see aws/cdk/data_pipeline_stack.py for the wiring).

IT RECORDS, THEN RUNS THE PROCESSING PASS (REQ-PIPE-152) - the same body as
the Birth Registrations handler; see that module.

EVERY FILE IS ITS OWN ARRIVAL, AND NOTHING WAITS (REQ-PIPE-105). This handler
once staged five of six tables and waited for a `_MANIFEST_COMPLETE.json`
marker before checking anything. A completion signal works only if something
upstream reliably sends it, and six independent systems each landing their
own table is exactly the case where nothing does - so a supply waited,
silently, for ever. A run reads the newest supply staged for its period for
every table its arrival did not carry, so one file is enough to check.

**Never invoked by a real Lambda runtime in this sandbox** (no AWS access
here); exercised by tests/test_lambda_handlers.py with a mocked S3 client.
"""
from __future__ import annotations

from qa_tools.common import s3_arrival

#: The prefix this handler's objects arrive under.
PREFIX = "cp/"


def handler(event: dict, context=None) -> dict:
    import boto3

    return s3_arrival.handle_event(event, boto3.client("s3"), prefix=PREFIX)
