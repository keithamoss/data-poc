"""
Lambda handler for Birth Registrations file arrivals - the AWS event-
driven MVP (plans/running-thoughts.md #5 Thread B / docs/aws-event-
driven-mvp-design.md's own "Lambda handlers" section). Triggered by a
real S3 ObjectCreated event under the raw bucket's `bdm/` prefix (see
aws/cdk/data_pipeline_stack.py for the event wiring).

**Never invoked by a real Lambda runtime or a real S3 event in this
sandbox** (no AWS access at all here) - written against the real,
documented S3 event JSON shape and exercised in tests/
test_lambda_handlers.py against hand-built fixture event dicts and a
mocked boto3 S3 client, not a real invocation.
"""
from __future__ import annotations
import json
import os
import tempfile
from datetime import datetime, timezone

import qa_tools.bdm.orchestrate_bdm as orchestrate_bdm
from qa_tools.common.file_arrival import match_arrival
from qa_tools.common.lambda_results_dir import BDM_MODULES, patch_write_qa_result_for_lambda
from qa_tools.common.results_s3_sink import upload_qa_result

# The proposed arrivalPattern contract extension (docs/aws-event-driven-
# mvp-design.md's own "File-arrival contract matching" section) - a
# hardcoded stand-in here, NOT wired into the real production contract
# YAML files yet (that doc explains why: no way to verify it against
# real Soda/dbt/datacontract-cli parsing overnight without real AWS
# access to actually deploy and test against). Move this into contract/
# bdm-birth-registrations-contract.yaml's own customProperties once
# someone can verify that round-trip for real.
BDM_ARRIVAL_PATTERNS = [
    {"type": "single_file", "keyPattern": "bdm/birth_registrations_{run_id}.csv", "dataset_id": "birth-registrations"},
]

# A real, placeholder answer to the design doc's own open question
# ("where does the Evidently reference run come from in production") -
# reuses this repo's own synthetic run_01 convention rather than
# resolving a real one. Flagged there as a real gap, not solved here.
REFERENCE_RUN_ID = "run_001"
REFERENCE_CSV = "run_001.csv"

RESULTS_BUCKET_NAME = os.environ.get("RESULTS_BUCKET_NAME")
AGENCY_ID = orchestrate_bdm.AGENCY_ID
COLLECTION_ID = orchestrate_bdm.COLLECTION_ID


def handler(event: dict, context=None) -> dict:
    import boto3

    s3_client = boto3.client("s3")
    summary = {"processed": 0, "skipped": 0, "pass": 0, "warn": 0, "fail": 0, "error": 0}

    # A real, necessary fix (qa_tools/common/lambda_results_dir.py's own
    # docstring has the full account): every write_qa_result() call in
    # this call chain defaults to this repo's own committed qa_results/
    # path, which doesn't exist (and isn't writable) inside a real
    # Lambda's deployment package - redirected to /tmp instead, then
    # uploaded to S3 below.
    qa_results_root = os.path.join(tempfile.gettempdir(), "qa_results")
    patch_write_qa_result_for_lambda(BDM_MODULES, qa_results_root)

    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]

        match = match_arrival(key, BDM_ARRIVAL_PATTERNS)
        if match is None:
            # A real, expected occurrence (a stray file, a different
            # team's object in a shared bucket) - never a pipeline
            # failure. See qa_tools/common/file_arrival.py's own
            # docstring.
            print(f"no arrival pattern matched key={key!r} - skipping")
            summary["skipped"] += 1
            continue

        run_id = match.groups.get("run_id") or os.path.splitext(os.path.basename(key))[0]
        # A real S3 object's own LastModified would be a better arrival
        # timestamp than "now" - not threaded through record["s3"] in the
        # real S3 event notification shape, so run_date here is really
        # "when this Lambda processed it," not "when the file actually
        # arrived" - a real, small imprecision, not solved in this MVP.
        run_date = datetime.now(timezone.utc).date().isoformat()

        with tempfile.TemporaryDirectory() as tmp_dir:
            local_csv = os.path.join(tmp_dir, os.path.basename(key))
            s3_client.download_file(bucket, key, local_csv)

            # dirty_severity is a synthetic-data-generator-only concept
            # (generator/dirty.py's own calibrated defect injection,
            # never a real production signal) - a real arriving file has
            # no such label at all, so this is always None here, never
            # guessed from anything about the file itself.
            results = orchestrate_bdm.run_single(
                run_id, local_csv, run_date, None,
                reference_run_id=REFERENCE_RUN_ID, reference_csv=REFERENCE_CSV)

        run_dir = os.path.join(qa_results_root, AGENCY_ID, COLLECTION_ID, run_id)
        if RESULTS_BUCKET_NAME and os.path.isdir(run_dir):
            for filename in os.listdir(run_dir):
                upload_qa_result(os.path.join(run_dir, filename), qa_results_root, RESULTS_BUCKET_NAME,
                                  s3_client=s3_client)

        summary["processed"] += 1
        for status in ("pass", "warn", "fail", "error"):
            summary[status] += sum(1 for r in results if r["status"] == status)

    return {"statusCode": 200, "body": json.dumps(summary)}
