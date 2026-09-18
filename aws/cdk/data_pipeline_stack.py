"""
CDK (Python) infra for the event-driven MVP - plans/running-thoughts.md #5
Thread B, full design at docs/aws-event-driven-mvp-design.md (read that
first; this module doesn't repeat the architecture, trust-boundary
decision, or completion-tracker discussion, only encodes the "Infra (AWS
CDK, Python)" section of it).

**Never `cdk synth`'d or deployed.** This sandbox has no AWS CLI, no CDK
CLI (Node-based), and no real AWS credentials (`AWS_ACCESS_KEY_ID`/
`AWS_SECRET_ACCESS_KEY` hold the literal string "proxy-injected", checked
directly, not assumed). Written correctly per CDK's documented Python
construct API, but genuinely unverified - the design doc's own "What's
verified vs. not" section lists this file under "not possible from this
sandbox." Treat it as a real first draft for Keith to review and deploy
from a real AWS account, not as working infrastructure.
"""
from __future__ import annotations

from aws_cdk import (
    CfnOutput,
    Duration,
    Stack,
)
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_notifications as s3n
from constructs import Construct

# Matches this repo's own pinned .python-version - the Lambda runtime has
# to match what the handler code (and whatever real dependencies eventually
# ship alongside it) was actually written/tested against locally.
LAMBDA_RUNTIME = lambda_.Runtime.PYTHON_3_11

# aws/lambda_handlers/ doesn't exist as a directory in this checkout yet
# (this task was scoped to the CDK infra only - see the design doc's
# "Lambda handlers" section for what belongs there). Code.from_asset just
# needs the directory to exist at `cdk synth` time; nothing here depends on
# its contents beyond the two entry-point module names below.
LAMBDA_HANDLERS_DIR = "aws/lambda_handlers"


class DataPipelineStack(Stack):
    """Two S3 buckets, two Lambdas, one DynamoDB table, and the IAM/event
    wiring between them - the whole of docs/aws-event-driven-mvp-design.md's
    "Infra (AWS CDK, Python)" section, nothing else. No git/GitHub
    credentials anywhere in this stack, by design (the "Getting results
    back into git" trust-boundary decision in the design doc - Lambda only
    ever gets an S3 write grant, a separate GitHub Actions workflow, not
    part of this stack, does the actual commit)."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # No bucket_name= passed on either bucket - S3 bucket names are
        # globally unique across ALL AWS accounts, so a hardcoded name
        # ("data-poc-raw", say) would only ever deploy successfully once,
        # for exactly one account. CDK auto-generates a unique name from
        # the construct/stack id; the real name is only known post-deploy,
        # which is exactly what the CfnOutputs below are for.
        raw_bucket = s3.Bucket(
            self,
            "RawDataBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
        )

        results_bucket = s3.Bucket(
            self,
            "ResultsBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
        )

        # Provisioned per the design doc even though ManifestMarkerCompletion
        # Tracker (a marker file + a live S3 HeadObject check, no state store
        # at all) is the recommended MVP default, not this table - so that
        # switching to DynamoDBCompletionTracker later (if Keith's real CP
        # source systems can't guarantee a marker lands last) is a config
        # change, not an infra change.
        completion_table = dynamodb.Table(
            self,
            "CpDeliveryCompletionTable",
            table_name="cp-delivery-completion",
            partition_key=dynamodb.Attribute(name="delivery_id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
        )

        # Real dependency bundling (this repo's own qa_tools/generator/
        # pipeline packages, plus dbt-core, Soda Core, datacontract-cli,
        # Evidently, duckdb - the actual 4-real-tool stack orchestrate_bdm.
        # py/orchestrate_cp.py's run_single() needs to import) is NOT solved
        # by Code.from_asset(LAMBDA_HANDLERS_DIR) below - that call only ever
        # bundles the two handler modules themselves. Those real
        # dependencies (several with compiled/native components - duckdb,
        # dbt-core's own deps) need either a Lambda layer built from a real
        # `pip install --platform manylinux... -t` against the Lambda
        # runtime's own architecture, or a container-image Lambda instead of
        # a zip package - neither attempted here. Flagged, not solved.
        bdm_lambda = lambda_.Function(
            self,
            "BdmIngestHandler",
            function_name="bdm-ingest-handler",
            runtime=LAMBDA_RUNTIME,
            handler="bdm_ingest_handler.handler",
            code=lambda_.Code.from_asset(LAMBDA_HANDLERS_DIR),
            timeout=Duration.minutes(15),  # Lambda's own ceiling - a full 4-tool run's real cost against
            # this limit is one of the design doc's own open questions, never checked against a real
            # invocation.
            memory_size=1024,
            environment={
                "RESULTS_BUCKET_NAME": results_bucket.bucket_name,
            },
        )

        cp_lambda = lambda_.Function(
            self,
            "CpIngestHandler",
            function_name="cp-ingest-handler",
            runtime=LAMBDA_RUNTIME,
            handler="cp_ingest_handler.handler",
            code=lambda_.Code.from_asset(LAMBDA_HANDLERS_DIR),
            timeout=Duration.minutes(15),
            memory_size=1024,
            environment={
                "RESULTS_BUCKET_NAME": results_bucket.bucket_name,
                "COMPLETION_TABLE_NAME": completion_table.table_name,
            },
        )

        # S3 ObjectCreated -> Lambda wiring, filtered by prefix so each
        # Lambda only ever sees the arrivals it actually knows how to
        # handle - matches the raw bucket's own bdm/ and cp/ layout.
        raw_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(bdm_lambda),
            s3.NotificationKeyFilter(prefix="bdm/"),
        )
        raw_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(cp_lambda),
            s3.NotificationKeyFilter(prefix="cp/"),
        )

        # IAM - narrowly scoped per the design doc's own "narrowly scoped"
        # claim, not the AWS-managed, bucket/account-wide policies CDK
        # examples often default to. grant_read()/grant_write() both accept
        # an objects_key_pattern argument that gets folded into the granted
        # policy's resource ARN (bucket-arn/<pattern>) rather than granting
        # the whole bucket - exactly the prefix-level scoping this needs, no
        # hand-written iam.PolicyStatement required for these two calls. If
        # a future aws-cdk-lib version's grant_read()/grant_write() ever
        # drops that parameter (unverified against a real install in this
        # sandbox - no `aws-cdk-lib` package available to check against),
        # the fallback is an explicit iam.PolicyStatement with a resource
        # ARN pattern like f"{raw_bucket.bucket_arn}/bdm/*" instead of the
        # grant call.
        raw_bucket.grant_read(bdm_lambda, "bdm/*")
        raw_bucket.grant_read(cp_lambda, "cp/*")

        # Both Lambdas write results bucket-wide, not prefix-scoped - the
        # design doc's trust-boundary section only requires "S3 write on the
        # results bucket," and each Lambda's own qa_results/<agency>/... key
        # layout already keeps their outputs from colliding without needing
        # IAM to enforce it too.
        results_bucket.grant_write(bdm_lambda)
        results_bucket.grant_write(cp_lambda)

        # Completion-tracking table: CP only. record_arrival()/is_complete()
        # (qa_tools/cp/completion_tracker.py's DynamoDBCompletionTracker)
        # both read and write, so this needs full read/write, not read-only.
        completion_table.grant_read_write_data(cp_lambda)

        CfnOutput(self, "RawBucketName", value=raw_bucket.bucket_name)
        CfnOutput(self, "ResultsBucketName", value=results_bucket.bucket_name)
        CfnOutput(self, "BdmIngestHandlerFunctionName", value=bdm_lambda.function_name)
        CfnOutput(self, "CpIngestHandlerFunctionName", value=cp_lambda.function_name)
