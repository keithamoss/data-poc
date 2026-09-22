"""
Uploads a locally-written qa_results/ file to S3, for the AWS event-driven
MVP's Lambda handlers (plans/running-thoughts.md #5 Thread B / docs/aws-
event-driven-mvp-design.md).

Deliberately does NOT teach qa_tools/common/qa_results_writer.py itself
about S3 - every existing caller (both orchestrate_*.py modules, every
test) depends on write_qa_result()'s local-filesystem contract exactly as
it is today. Instead, a Lambda handler calls write_qa_result() completely
normally (writing to Lambda's own /tmp - the one writable path in that
runtime), then this module uploads the resulting file to S3 with the same
relative qa_results/<agency>/<dataset>/<run_id>/<tool>.json path structure
- see the design doc's own "Getting results back into git" section for
why results land in S3 rather than being committed directly (no git-write
credentials anywhere in Lambda).
"""
from __future__ import annotations
import os


def upload_qa_result(local_path: str, qa_results_root: str, bucket: str, s3_client=None) -> str:
    """local_path is an absolute path somewhere under qa_results_root
    (e.g. "/tmp/qa_results/registry-services/civil-registration/run_042/
    dbt.json"); qa_results_root is that same local qa_results/ root
    (e.g. "/tmp/qa_results"). Uploads to the results bucket at the exact
    same path relative to qa_results_root (e.g. "registry-services/
    birth-registrations/run_042/dbt.json"), so the (b) sync workflow
    described in the design doc can lay it straight into the repo's own
    committed qa_results/ with no path translation. Returns the S3 key
    uploaded to."""
    if s3_client is None:
        import boto3
        s3_client = boto3.client("s3")

    relative_path = os.path.relpath(local_path, qa_results_root)
    key = relative_path.replace(os.sep, "/")
    s3_client.upload_file(local_path, bucket, key)
    return key
