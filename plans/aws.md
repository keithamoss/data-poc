# AWS - what waits for a real deployment

Opened 2026-10-07 at Keith's own ask: "wait for real AWS and include this
and other AWS stuff in an aws.md file". The event-driven path exists in
code - `aws/lambda_handlers/`, `aws/cdk/`, and REQ-PIPE-152's handlers
that record each S3 object as a delivery and run the processing pass - but
it has only ever run locally, against fakes. This file collects what is
deliberately left until it is deployed for real, so none of it is decided
by accident in the meantime or lost in a review entry.

**What does NOT belong here**: a defect in the handler code that is wrong
today whatever the deployment looks like - those are fixed as they are
found (post-build-review #131 D2's URL-decoding and per-object guard are
being fixed that way, in the #131-#133 fix batch).
This file is for the questions only a real account, real limits and a real
network can answer, and for infrastructure nothing builds yet.

Background: `plans/running-thoughts.md` Thread B (the AWS MVP idea, CDK in
Python) and `docs/aws-event-driven-mvp-*.md` (its design write-up).

1. **[todo, 2026-10-07]** **[Pipeline & publishing]** **The scheduled pass
   REQ-PIPE-152 counts on does not exist.** Criterion 13 says a failed
   invocation fails so the platform retries, with "the scheduled pass"
   as the backstop - and `aws/` has no schedule, no EventBridge rule, no
   retry configuration and no dead-letter queue (post-build-review #131
   D3). Proposed when picked up: a scheduled rule, roughly hourly, running
   the same processing pass, plus a dead-letter queue for events that
   still fail. Keith, 2026-10-07: wait for a real deployment.

2. **[todo, 2026-10-07]** **[Pipeline & publishing]** **What a Lambda does
   when its pass is refused as busy.** Several Child Protection files
   landing together start parallel invocations; all but one meet
   `PassLockHeld`, and the platform's default async retries (two) can run
   out while one pass holds the lock for up to ~10 minutes. The objects
   are recorded, so nothing is lost, but they wait for the next event or
   the backstop in item 1. Keith deferred this on REQ-PIPE-152's own open
   question ("decide when we focus on building the aws side later").

3. **[todo, 2026-10-07]** **[Pipeline & publishing]** **The fifteen-minute
   ceiling.** REQ-PIPE-152 criterion 12's time budget is checked only in
   the staging and arrival loops (`processing_pass.py`); downloading every
   owed object (`materialise`), `refile_covered` and the owed re-checks -
   each a full four-tool run - happen outside it (post-build-review #131
   D3). Whether that matters depends on real object sizes and real
   invocation memory, which only a deployment shows.

4. **[todo, 2026-10-07]** **[Pipeline & publishing]** **Where the database
   connection string lives.** Today it reaches the Lambda through CDK
   context into the function's environment variables, so it is readable
   in the synthesized template and the function configuration. The code
   flags this rather than solving it. A real deployment wants Secrets
   Manager or an IAM-authenticated connection, and the choice depends on
   where the database is hosted.

5. **[todo, 2026-10-07]** **[Pipeline & publishing]** **Schema names unique
   across machines.** The dbt worker's schemas were named by process id,
   which repeats across containers and Lambda sandboxes (post-build-review
   #131 D4) - to be made unique per process regardless of host in the
   #131-#133 fix batch. Worth confirming against a real concurrent load, where a handler's
   pass and a person's `mothman cp qa --commit` can meet on one database.
