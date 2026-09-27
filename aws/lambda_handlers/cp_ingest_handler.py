"""
Lambda handler for Child Protection file arrivals - the AWS event-driven
MVP (plans/running-thoughts.md #5 Thread B / docs/aws-event-driven-mvp-
design.md's own "Lambda handlers" section). Triggered by a real S3
ObjectCreated event under the raw bucket's `cp/` prefix (see
aws/cdk/data_pipeline_stack.py for the event wiring).

EVERY FILE IS ITS OWN ARRIVAL, AND NOTHING WAITS (REQ-PIPE-105). This
handler used to do something quite different: an ordinary table file was
staged and the handler stopped, and the full four-tool run happened only
when a `_MANIFEST_COMPLETE.json` marker arrived and
`ManifestMarkerCompletionTracker` confirmed all six tables existed in S3.
Both trackers, the marker pattern and that branch are deleted.

WHY, because the reasoning matters more than the deletion. A completion
signal only works if something upstream can be relied on to send it, and
the case that breaks it was written into the old design's own
recommendation: six independent upstream systems each landing their own
table with no orchestration to coordinate a marker. Then a supply waits
on a signal nobody will ever send, silently. The DynamoDB counter removed
the supplier dependency and kept the shape - it still had to know what
"all six" meant, so adding a dataset to the collection would leave every
in-flight delivery permanently incomplete.

WHAT MAKES WAITING UNNECESSARY rather than merely risky: a run reads the
newest supply STAGED for that period for every table this arrival did not
itself carry, falling back to the period's promoted state. So the run
triggered by the sixth file of a six-file delivery sees all six and the
cross-table checks resolve normally - not because anything detected
completeness, but because the other five are already staged.

**Never invoked by a real Lambda runtime or a real S3 event in this
sandbox** - see bdm_ingest_handler.py's identical note.
"""
from __future__ import annotations
import json
import os
import tempfile

import qa_tools.cp.build_cp_warehouses as build_cp_warehouses
import qa_tools.cp.orchestrate_cp as orchestrate_cp
from qa_tools.common import asset_time
from qa_tools.common.file_arrival import match_arrival

# The proposed arrivalPattern extension - see bdm_ingest_handler.py's
# identical note on why this is hardcoded here rather than in the real
# contract YAML files. `extractTo` names which of the 6 real tables this
# pattern matches. THERE IS NO SEVENTH PATTERN any more: the marker file
# it used to match is not a supply and nothing waits for one.
CP_TABLE_NAMES = ["cp_clients", "cp_notifications", "cp_investigations", "cp_placements", "cp_carers",
                   "cp_case_workers"]
CP_ARRIVAL_PATTERNS = [
    {"type": "nested_folder", "keyPattern": f"cp/{{run_id}}/{table}.csv", "dataset_id": table, "extractTo": table}
    for table in CP_TABLE_NAMES
]

# Same real, placeholder answer as bdm_ingest_handler.py - see its
# identical comment and the design doc's own open question.
REFERENCE_RUN_ID = "cp_run_01"


def handler(event: dict, context=None) -> dict:
    import boto3

    s3_client = boto3.client("s3")
    summary = {"tables_loaded": 0, "arrivals_checked": 0, "skipped": 0, "pass": 0, "warn": 0, "fail": 0,
               "error": 0}

    # NOTHING TO REDIRECT ANY MORE - see the Birth Registrations handler's
    # own note for the whole account (REQ-PIPE-089).
    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]

        match = match_arrival(key, CP_ARRIVAL_PATTERNS)
        if match is None:
            print(f"no arrival pattern matched key={key!r} - skipping")
            summary["skipped"] += 1
            continue

        run_id = match.groups.get("run_id")

        with tempfile.TemporaryDirectory() as tmp_dir:
            local_csv = os.path.join(tmp_dir, os.path.basename(key))
            s3_client.download_file(bucket, key, local_csv)
            build_cp_warehouses.add_table_to_run(run_id, match.table, local_csv)
        summary["tables_loaded"] += 1

        # AND THEN CHECK IT, rather than stopping here (REQ-PIPE-105
        # criterion 1). This is the whole behaviour change: the run reads
        # this file plus the newest staged supply for every other table in
        # the period, so it needs nothing else to have happened first.
        run_date = asset_time.now().date().isoformat()
        entry = {"run_id": run_id, "run_date": run_date, "dirty_severity": None}
        results = orchestrate_cp.run_single(entry, reference_run_id=REFERENCE_RUN_ID)

        summary["arrivals_checked"] += 1
        for status in ("pass", "warn", "fail", "error"):
            summary[status] += sum(1 for r in results if r["status"] == status)

    return {"statusCode": 200, "body": json.dumps(summary)}
