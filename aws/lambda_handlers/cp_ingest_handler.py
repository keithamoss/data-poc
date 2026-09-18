"""
Lambda handler for Child Protection file arrivals - the AWS event-driven
MVP (plans/running-thoughts.md #5 Thread B / docs/aws-event-driven-mvp-
design.md's own "Lambda handlers" section and "Child Protection: waiting
for all 6 tables" section). Triggered by a real S3 ObjectCreated event
under the raw bucket's `cp/` prefix (see aws/cdk/data_pipeline_stack.py
for the event wiring).

Unlike bdm_ingest_handler.py (one arrival = one full pipeline run), most
CP arrivals only load one of 6 tables and stop there - the full 4-tool
run (including the cross-table checks, which need all 6 tables loaded)
only happens once ManifestMarkerCompletionTracker confirms every table
for this delivery genuinely exists in S3, triggered by the delivery's own
completion-marker file arriving (see qa_tools/cp/completion_tracker.py's
own docstring for why this tracker, not the DynamoDB one, is this MVP's
real default).

**Never invoked by a real Lambda runtime or a real S3 event in this
sandbox** - see bdm_ingest_handler.py's identical note.
"""
from __future__ import annotations
import json
import os
import tempfile
from datetime import datetime, timezone

import qa_tools.cp.build_cp_warehouses as build_cp_warehouses
import qa_tools.cp.orchestrate_cp as orchestrate_cp
from qa_tools.common.file_arrival import match_arrival
from qa_tools.common.lambda_results_dir import CP_MODULES, patch_write_qa_result_for_lambda
from qa_tools.common.results_s3_sink import upload_qa_result
from qa_tools.cp.completion_tracker import ManifestMarkerCompletionTracker

# The proposed arrivalPattern extension - see bdm_ingest_handler.py's
# identical note on why this is hardcoded here rather than in the real
# contract YAML files. `extractTo` names which of the 6 real tables (or
# the completion marker) this specific pattern matches.
CP_TABLE_NAMES = ["cp_clients", "cp_notifications", "cp_investigations", "cp_placements", "cp_carers",
                   "cp_case_workers"]
CP_ARRIVAL_PATTERNS = [
    {"type": "nested_folder", "keyPattern": f"cp/{{run_id}}/{table}.csv", "dataset_id": table, "extractTo": table}
    for table in CP_TABLE_NAMES
] + [
    {"type": "nested_folder", "keyPattern": "cp/{run_id}/_MANIFEST_COMPLETE.json", "dataset_id": "cp-collection",
     "extractTo": "_manifest"},
]

# Same real, placeholder answer as bdm_ingest_handler.py - see its
# identical comment and the design doc's own open question.
REFERENCE_RUN_ID = "cp_run_01"

RESULTS_BUCKET_NAME = os.environ.get("RESULTS_BUCKET_NAME")


def _head_object_exists(s3_client, bucket: str, key: str) -> bool:
    try:
        s3_client.head_object(Bucket=bucket, Key=key)
        return True
    except Exception:
        return False


def handler(event: dict, context=None) -> dict:
    import boto3

    s3_client = boto3.client("s3")
    summary = {"tables_loaded": 0, "deliveries_completed": 0, "skipped": 0, "pass": 0, "warn": 0, "fail": 0,
               "error": 0}

    qa_results_root = os.path.join(tempfile.gettempdir(), "qa_results")
    patch_write_qa_result_for_lambda(CP_MODULES, qa_results_root)

    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]

        match = match_arrival(key, CP_ARRIVAL_PATTERNS)
        if match is None:
            print(f"no arrival pattern matched key={key!r} - skipping")
            summary["skipped"] += 1
            continue

        run_id = match.groups.get("run_id")

        if match.table != "_manifest":
            # An ordinary table arrival - load it and stop. The full
            # pipeline only ever runs once the completion marker arrives
            # (below), never eagerly per-table - CP's own explicit
            # dependency-ordering requirement (all 6 tables loaded before
            # the cross-table checks run).
            with tempfile.TemporaryDirectory() as tmp_dir:
                local_csv = os.path.join(tmp_dir, os.path.basename(key))
                s3_client.download_file(bucket, key, local_csv)
                build_cp_warehouses.add_table_to_run(run_id, match.table, local_csv)
            summary["tables_loaded"] += 1
            continue

        # The completion marker itself arrived - read its own listed
        # keys and verify each genuinely exists in S3 before trusting it
        # (ManifestMarkerCompletionTracker's own real protection against
        # a source-system bug that writes the marker before finishing a
        # slow upload - see its own docstring).
        with tempfile.TemporaryDirectory() as tmp_dir:
            local_manifest = os.path.join(tmp_dir, "manifest.json")
            s3_client.download_file(bucket, key, local_manifest)
            with open(local_manifest) as f:
                manifest_keys = json.load(f)  # {table: s3_key}

        tracker = ManifestMarkerCompletionTracker(lambda b, k: _head_object_exists(s3_client, b, k))
        if not tracker.is_complete_from_manifest(bucket, manifest_keys):
            print(f"completion marker for run_id={run_id!r} listed keys that don't all exist yet - skipping")
            summary["skipped"] += 1
            continue

        run_date = datetime.now(timezone.utc).date().isoformat()
        entry = {"run_id": run_id, "run_date": run_date, "dirty_severity": None}
        results = orchestrate_cp.run_single(entry, reference_run_id=REFERENCE_RUN_ID)

        run_dirs_root = os.path.join(qa_results_root, orchestrate_cp.cp_common.AGENCY_ID,
                                      orchestrate_cp.cp_common.COLLECTION_ID, run_id)
        if RESULTS_BUCKET_NAME and os.path.isdir(run_dirs_root):
            for filename in os.listdir(run_dirs_root):
                upload_qa_result(os.path.join(run_dirs_root, filename), qa_results_root, RESULTS_BUCKET_NAME,
                                  s3_client=s3_client)

        summary["deliveries_completed"] += 1
        for status in ("pass", "warn", "fail", "error"):
            summary[status] += sum(1 for r in results if r["status"] == status)

    return {"statusCode": 200, "body": json.dumps(summary)}
