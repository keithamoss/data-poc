"""
CDK (Python) infra for the event-driven MVP - plans/running-thoughts.md #5
Thread B, full design at docs/aws-event-driven-mvp-design.md (read that
first; this module doesn't repeat the architecture, trust-boundary
decision, or (since REQ-PIPE-105, retired) completion-tracker
discussion, only encodes the "Infra (AWS
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
    """Two S3 buckets, two Lambdas, and the IAM/event wiring between them.

    THE DYNAMODB TABLE IS GONE (REQ-PIPE-105, 2026-09-28). It existed to
    count which of Child Protection's six tables had landed, so the
    cross-table checks could wait for all of them. Nothing waits now -
    every arriving file is checked against the newest supply staged for
    its period - so there is no completion state to keep, and a table
    provisioned "so switching strategies later is a config change" is
    infrastructure for a strategy that no longer exists - the whole of docs/aws-event-driven-mvp-design.md's
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
        # A STATED ENVIRONMENT AND A DATABASE, OR NO STACK (REQ-PIPE-152).
        # Every connection refuses without MOTHMAN_ENVIRONMENT and a matching
        # qa.identity row (REQ-PIPE-093, REQ-PIPE-107), so a handler deployed
        # without either fails on its first object. Both come from CDK
        # context and neither has a default: `cdk synth -c
        # mothman_environment=production -c supply_dsn=...`. The database
        # must already be marked with the same environment by a person
        # (`mothman env mark`) - the stack cannot do that for them.
        #
        # FLAGGED, NOT SOLVED: a DSN carries a password, and a Lambda
        # environment variable is readable by anyone who can read the
        # function's configuration. A real deployment should hold it in
        # Secrets Manager and have supply_db read it from there; that is a
        # security decision for whoever deploys this, not one to make in a
        # sketch nobody has synthesised.
        handler_environment = {
            "MOTHMAN_ENVIRONMENT": self._required_context("mothman_environment"),
            "MOTHMAN_SUPPLY_DSN": self._required_context("supply_dsn"),
        }

        raw_bucket = s3.Bucket(
            self,
            "RawDataBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
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
            environment=dict(handler_environment),
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
            # The completion table it used to name is gone with the
            # completion tracking (REQ-PIPE-105); what it needs now is the
            # same stated environment and database as the other handler.
            environment=dict(handler_environment),
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

        # THERE IS NO RESULTS BUCKET (REQ-PIPE-089), and the grant that went
        # with it is the part worth noting rather than the bucket. Both
        # Lambdas used to hold bucket-wide S3 write so they could upload
        # qa_results/ JSON files for a sync workflow to lay back into git.
        # Results are recorded in the database now, so the bucket, the two
        # write grants and the RESULTS_BUCKET_NAME environment variable are
        # all gone - a write permission nothing needs is worth removing on
        # its own terms, not only for tidiness.

        # No DynamoDB grant either. The CP Lambda used to need read/write on
        # a completion table; it has nothing to count (REQ-PIPE-105), and a
        # permission nothing needs is worth removing on its own terms.

        CfnOutput(self, "RawBucketName", value=raw_bucket.bucket_name)
        CfnOutput(self, "BdmIngestHandlerFunctionName", value=bdm_lambda.function_name)
        CfnOutput(self, "CpIngestHandlerFunctionName", value=cp_lambda.function_name)

    def _required_context(self, key: str) -> str:
        """A CDK context value this stack cannot be built without - refused
        by name rather than defaulted, as MOTHMAN_ENVIRONMENT itself is."""
        value = self.node.try_get_context(key)
        if not value:
            raise ValueError(f"cdk context '{key}' is required (-c {key}=...) - the handlers "
                             f"refuse to connect without it, so the stack is not built "
                             f"without it either.")
        return str(value)
