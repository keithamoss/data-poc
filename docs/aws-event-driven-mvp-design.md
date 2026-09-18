# AWS event-driven MVP design — Thread B (`plans/running-thoughts.md` #5)

Real design doc plus real, reviewable code for Thread B: deploying this
pipeline (or a version of it) to AWS, triggered by real S3 events as
files land, running QA automatically instead of via a manually-kicked-
off local script (`./run_pipeline.sh` / `uv run python3 -m
qa_tools.bdm.orchestrate_bdm`).

**Built overnight, 2026-09-18/19, per Keith's own explicit instruction
("Crack on with Thread B overnight and we'll pick this all up again in
the morning") — for morning review, not yet deployed or end-to-end
tested.** This sandbox has no real AWS access at all: no `aws` CLI, and
`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` hold the literal string
`"proxy-injected"`, not real credentials (checked directly before
starting, not assumed). Everything below is written to be correct and
is unit-tested wherever the logic is pure/mockable, but **nothing here
has run against a real S3 bucket, a real Lambda invocation, or a real
`cdk deploy`.** Treat this doc as a design for Keith to confirm or
redirect, and the code as a real first draft to deploy from a real AWS
account, not as verified-working infrastructure.

This is Thread B specifically — Thread A ("fit into today's actual
S3/local-storage staff workflow") is still blocked on real specifics
from Keith about how staff actually pull data today, asked separately
and not answered yet as of this write-up. The two threads share no code
here; Thread A needs a real scoping conversation before anything gets
built for it.

## What this doc asks Keith to confirm in the morning

Four real, consequential forks got resolved by this session's own
judgement rather than deferred to a design-doc-only proposal, because
building something concrete was the whole point of "crack on overnight."
Each is flagged again in its own section below, but the short version,
gathered here so it's not missed:

1. **The `qa_results/` git-publish trust boundary** (how a Lambda-
   produced result ever becomes a committed, git-history entry without
   Lambda holding git-write credentials) — **recommended: S3-only from
   Lambda, a scheduled GitHub Actions workflow does the actual commit.**
   See "Getting results back into git" below. This is the single
   biggest architectural fork in this whole design — confirm or
   redirect it before any of the rest gets built for real.
2. **CP's completion signal is a marker file, not a DynamoDB
   arrival-counter** — recommended for MVP simplicity (no state store,
   no race window), with the counter-based `DynamoDBCompletionTracker`
   built too as a real, tested alternative if Keith's actual source
   systems can't guarantee "marker file lands last." See "Child
   Protection: waiting for all 6 tables" below.
3. **File-arrival contract matching (`arrivalPattern`) is a
   design-doc-only proposal, not applied to the real production
   contract YAML files.** Kept out of `contract/bdm-birth-registrations-
   contract.yaml` / `contract/child-protection-contract.yaml` because
   there was no way to verify overnight, with no real AWS and no time
   to safely test against real Soda/dbt/datacontract-cli parsing, that
   adding it wouldn't break real tool parsing the way the YAML-quoting
   incident in `CLAUDE.md`'s own conventions section already did once
   this project. The matching logic itself is real and tested
   (`qa_tools/common/file_arrival.py`), just driven by a standalone
   pattern-spec dict in this MVP rather than the contract file.
4. **AWS CDK (Python)** — Keith's own explicit choice, already decided,
   not re-litigated here; noted for completeness since it shapes every
   file under `aws/cdk/`.

## Architecture / event flow

```
S3 (raw-data bucket)
  │  ObjectCreated events, filtered by prefix
  ▼
┌─────────────────────────┐     ┌─────────────────────────┐
│  bdm-ingest Lambda       │     │  cp-ingest Lambda        │
│  (single BDM file)       │     │  (single CP table file,  │
│                          │     │   or the completion       │
│                          │     │   marker file)            │
└──────────┬───────────────┘     └──────────┬────────────────┘
           │                                 │ (only once complete)
           ▼                                 ▼
   qa_tools.bdm.orchestrate_bdm      qa_tools.cp.orchestrate_cp
     .run_single()                     .run_single()
           │                                 │
           ▼                                 ▼
   real dbt/Soda/datacontract-cli/Evidently runs, one delivery's worth
           │
           ▼
   qa_results/... shaped result dicts (same shape orchestrate_*.py
   already produces locally) written to S3, NOT to git directly
           │
           ▼
   scheduled GitHub Actions workflow pulls new S3 results, commits them
   into qa_results/ (the real, permanent history), same trust model
   deploy-pages.yml already uses for the dashboard
           │
           ▼
   deploy-pages.yml's existing trigger (push to qa_results/) rebuilds
   and republishes the dashboard, unchanged
```

Nothing about the CI-safe rebuild path changes: `deploy-pages.yml`,
`build_results_from_history.py`, and the dashboard build still only
ever read committed `qa_results/` history, never live data — this
design adds a new way for that history to get *written* (Lambda → S3 →
a scheduled commit workflow), not a new way for anything to *read* it.

## Single-run orchestration entry points

`orchestrate_bdm.py`/`orchestrate_cp.py`'s existing `run_pipeline()`/
`run_pipeline_cp()` are full-manifest batch loops — they read the whole
`manifest.json` and iterate every entry, which is exactly right for a
local/CI batch run but wrong for a Lambda invoked once per arriving
file. Both got a new single-run entry point that reuses the *existing*
`_run_one()` internal function unchanged (same 4-real-tool evaluation,
same `dataset_stats` computation, same `write_qa_result()` call, same
`run_by` attribution) — the only new code is what feeds `_run_one()` a
one-entry "manifest" instead of a loop over the whole file, plus a
matching single-file warehouse loader so a Lambda doesn't need
`data/raw/manifest.json`/`data/cp_raw/manifest.json` to exist at all.

`qa_tools/bdm/build_per_run_warehouses.py` gained `build_one()`:
processes exactly one CSV into exactly one
`data/duckdb_runs/<run_id>.duckdb` file, same schema/logic as the
existing per-manifest-entry loop body in `build_all()`, factored out so
both share it (`build_all()` now just calls `build_one()` per manifest
entry — verified byte-identical output via the existing pipeline run).

`qa_tools/bdm/orchestrate_bdm.py` gained `run_single(run_id, csv_path,
run_date, dirty_severity, reference_run_id, reference_csv, run_by=None)`
— builds that one warehouse, resolves `run_by` via `get_run_by()`
(picking up the Lambda-context fallback below) if not passed explicitly,
calls `_run_one()` with a synthetic one-entry manifest dict, and returns
the same `list[dict]` of check results `_run_one()` always has, without
ever touching `reports/results_bdm.json` (that file is the *full-batch*
rollup — a single Lambda invocation writes only that one run's
`qa_results/` entry, same underlying writer, no batch aggregation step).
The `reference_run_id`/`reference_csv` Evidently needs (drift comparison
against a fixed clean baseline) has to be passed in explicitly here,
since there's no manifest to read `manifest[0]` from — see "Open
question: where does the Evidently reference run come from in
production" below, genuinely unresolved.

`qa_tools/cp/build_cp_warehouses.py` gained `add_table_to_run(run_id,
table, csv_path, out_dir=OUT_DIR)` — loads exactly one table's CSV into
that run's (possibly already-partially-populated) DuckDB file, reusing
`build_all()`'s existing per-table load logic. Called once per arriving
CP table file, so a delivery's warehouse fills in incrementally as each
of the 6 tables lands, in whatever order they actually arrive.

`qa_tools/cp/orchestrate_cp.py` gained `run_single(run_id,
reference_run_id, run_by=None)` — same shape as BDM's, called only once
`completion_tracker`/the manifest-marker logic below says all 6 tables
are actually present in that run's warehouse; runs the full 4-tool
evaluation (including the cross-table referential-integrity checks,
which need every table loaded — this is exactly why CP can't run
per-table the way BDM runs per-file).

## File-arrival contract matching

The real complication flagged in `plans/running-thoughts.md` #5 before
any of this was built: files can arrive individually, in nested
folders, or as zip archives, with varying names — something has to
decide, from a raw S3 key, which dataset/table an arriving file is and
where its data actually is.

`qa_tools/common/file_arrival.py` (new, pure logic, no AWS import at
all — testable with zero mocking) implements matching against a
pattern spec shaped like this proposed `arrivalPattern` contract
extension:

```yaml
customProperties:
  - property: arrivalPattern
    value:
      type: single_file          # single_file | nested_folder | zip_archive
      keyPattern: "raw/bdm/birth_registrations_{date}.csv"
      # {date}/{run_id}/{table} become named capture groups; anything
      # else in keyPattern is matched literally.
      extractTo: null            # nested_folder/zip_archive only - see below
```

- `single_file`: the whole arriving object IS the dataset's data (BDM's
  real case today — one CSV per run).
- `nested_folder`: the arriving object is one file inside a folder that
  eventually holds several — `extractTo` names which table/file role
  this specific `keyPattern` match represents (CP's real case — 6
  separate table files land under one `cp/<run_id>/` prefix over time).
- `zip_archive`: the arriving object is a zip that needs extracting
  first; `extractTo` is a `{filename-inside-zip: table}` map. **Written
  but not exercised by either real dataset** — neither BDM nor CP
  actually arrives zipped today, so this branch has real, deliberate
  unit-test coverage (a fixture zip) but no real-dataset-shaped
  end-to-end path exercising it. Included because Keith's own original
  framing of the problem named zip archives explicitly as a real shape
  to expect, not because either current source system needs it yet.

`match_arrival(key: str, patterns: list[dict]) -> ArrivalMatch | None`
tries each pattern in order, returns the first match (dataset/table
identity, extracted named groups, and — for zip — the member->table
map) or `None` if nothing matches (the Lambda handler logs and exits
cleanly on a `None` match rather than raising, since an unmatched key
landing in the bucket is a real, expected occurrence — a stray file, a
different team's object in a shared bucket — not a pipeline failure).

**This module is real and tested against fixture patterns
(`tests/test_file_arrival.py`), but the pattern spec itself is NOT
wired into the real `contract/*-contract.yaml` files** — see the flagged
decision at the top of this doc for why. `aws/lambda_handlers/*.py`
below take their patterns from a small hardcoded list in the handler
module itself for this MVP, with a comment pointing at this section.
Moving that list into the real contract files (as genuine
`customProperties`) is a good, small follow-up once someone can verify
it against real Soda/dbt/datacontract-cli parsing — flagged, not done.

## Child Protection: waiting for all 6 tables

Keith's own answer when this was scoped: **explicit completion
signal**, not a timeout or a "6 files landed" heuristic inferred purely
from S3 listing. Two real implementations exist, behind one shared
`qa_tools/cp/completion_tracker.py` interface —
`CompletionTracker.record_arrival(delivery_id, table)` / `.is_complete
(delivery_id, expected_tables)` / `.arrived_tables(delivery_id)` — so
the Lambda handler's own logic doesn't need to know which strategy is
in use:

1. **`ManifestMarkerCompletionTracker` (recommended default for this
   MVP).** The source system itself writes one extra file once all 6
   real CP tables for a delivery have landed — e.g.
   `cp/<run_id>/_MANIFEST_COMPLETE.json`, listing the 6 real table keys
   it just finished writing. The CP Lambda's S3 event filter includes
   this marker key pattern; every *other* CP file arrival is recorded
   via `record_arrival()` for bookkeeping/observability but never
   itself triggers a pipeline run. Only the marker's own arrival calls
   `is_complete()` (which, with this tracker, also double-checks via a
   real `HeadObject` that all 6 listed keys genuinely exist in S3
   before trusting the marker — protects against a source-system bug
   writing the marker before finishing a slow upload). **No state
   store needed at all** — the marker file itself, plus a live S3
   check, is the complete signal; nothing has to persist across Lambda
   invocations. Simplest to reason about, and matches Keith's own
   framing of "explicit completion signal" most literally (a real
   signal file, not a count).
2. **`DynamoDBCompletionTracker` (built as a real alternative, not the
   default).** Every one of the 6 table files increments a DynamoDB
   item keyed by `delivery_id` (a table-name string set, using DynamoDB
   `ADD`/`String Set` semantics — idempotent against S3's own at-
   least-once delivery, a real risk this design has to account for,
   not a hypothetical one), and `is_complete()` compares the recorded
   set against the 6 expected table names, true the moment the 6th
   distinct table has ever landed. Doesn't require the source system to
   write anything extra, and copes with any arrival order — the real
   tradeoff against option 1 is it needs a real DynamoDB table
   (infra + IAM to provision and pay for) and has a genuine, if narrow,
   race condition if two of the 6 files' S3 events get processed by
   concurrent Lambda invocations at the exact same moment (mitigated by
   DynamoDB's own atomic `ADD`, but the *read-after-write* completion
   check right after is not itself atomic with the write — two
   invocations landing on the true 6th and final file at once could
   both see "complete" and both trigger `run_single()`; harmless
   (idempotent — same `run_id`, same results, `write_qa_result()`
   would just overwrite with the same content) but wasteful, a real,
   accepted cost documented here rather than solved with a distributed
   lock this MVP doesn't need yet).

**Recommendation: ship with `ManifestMarkerCompletionTracker` as the
real default**, since it needs zero new AWS infrastructure and matches
"explicit completion signal" most directly — but this assumes Keith's
real source systems for CP's 6 tables can reliably write a marker file
last. If that's not true of the real delivery mechanism (e.g. 6
independent upstream systems each land their own table with no
shared orchestration to coordinate a marker), `DynamoDBCompletionTracker`
is the real fallback, already built and tested
(`tests/test_completion_tracker.py`, with `boto3`'s DynamoDB calls
mocked via `unittest.mock` rather than a new test dependency like
`moto`).

## Lambda-context `run_by` attribution

Already built and verified this session, ahead of the rest of this
design (`qa_tools/common/git_identity.py`): `get_run_by()` checks
`AWS_LAMBDA_FUNCTION_NAME` (set only by the real Lambda service) first,
returning `"aws-lambda:<function-name>"` — a real, truthful service
identity — before ever attempting `git config user.email`, which
wouldn't exist in a Lambda runtime at all (no `.git` checkout). This is
exactly the fix `plans/running-thoughts.md` #5's own note said was
needed: "worth re-checking every other `run_by`-based feature... before
this thread's AWS MVP is ever actually built."

**One other real consumer audited, not yet a problem**: the "Recent
activity" changelog panel (`qa_tools/common/changelog.py`) reads
`run_by` straight out of committed `qa_results/` and displays it
verbatim/resolves it against `contract/people.yaml`'s `email:` field for
a friendly name — an `aws-lambda:bdm-ingest-handler` value will just
render as unresolved raw text (no `people.yaml` entry matches it),
falling back to whatever `changelog.py`'s existing "no match" behavior
already is for an unrecognized email. Not a crash, not silently wrong,
just an honest "this ran automatically" signal — acceptable for this
MVP, flagged here in case Keith wants a nicer label for it later (e.g.
a special-cased "🤖 Automated (bdm-ingest)" rendering) rather than raw
text.

The leaderboard (`qa_tools/common/leaderboard.py`) is unaffected — it
was already redesigned the same day (`plans/running-thoughts.md` #3's
"automation-tension follow-up") to credit ticket-*closing* via a real
GitHub login, not `run_by`, specifically because of this exact future
thread.

## Getting results back into git — the real trust-boundary decision

This is the fork that most needs Keith's own confirmation, not a silent
build. Three options considered:

**(a) Lambda commits directly to git via the GitHub API.** Rejected.
Means embedding real git-write credentials (a PAT or a GitHub App
private key) into Lambda's own environment/Secrets Manager — a real,
permanent expansion of the credential surface for an automated, publicly
triggerable (well, S3-triggered, but still machine-triggered with no
human in the loop) piece of infrastructure. Every other write path in
this whole project (ticket_sync.py, acceptance_sync.py, the dashboard's
own CI publish) already goes out of its way to keep git-write
credentials inside GitHub Actions' own ambient `GITHUB_TOKEN`, never
handed to anything else — this option breaks that pattern for no real
benefit over option (b).

**(b) Lambda writes to S3; a separate GitHub Actions workflow polls/is
triggered and does the actual commit.** **Recommended.** Lambda's own
IAM role only ever needs `s3:PutObject` on a results bucket/prefix — zero
GitHub credentials anywhere in the AWS account. A new, scheduled (e.g.
every 15 minutes — real latency tradeoff, tunable) GitHub Actions
workflow (`.github/workflows/sync-lambda-results.yml`, not built yet —
this doc proposes it, doesn't ship it, since it needs real AWS
credentials configured as GitHub Actions secrets, which can't happen
from this sandbox) lists new objects under the results prefix, downloads
them, and commits them into `qa_results/` using the exact same
`qa_results_writer.py`-shaped file layout local/CI runs already produce
— reusing the *existing* "CI is the only publish path" trust model
`plans/publishing-and-history.md` Thread A already established for the
dashboard, rather than inventing a second one. The workflow needs
read-only AWS credentials (list+get on one S3 prefix) as a GitHub
Actions secret — a real, but much narrower and more conventional,
credential to manage than a git-write credential living in Lambda.

**(c) Lambda writes to S3 only, nothing else, and Keith reviews/commits
results by hand periodically.** Rejected as the *default* — defeats
the point of "automatic" — but worth naming as the trivial fallback if
Keith would rather not stand up the scheduled workflow in (b)
immediately: (b)'s scheduled workflow can always be added later without
changing anything about how Lambda itself writes results, since Lambda
only ever produces S3 objects in both (b) and (c) — the only difference
is what reads them next.

**What got built for this**: the Lambda handlers below write results as
S3 objects shaped exactly like a `qa_results/<agency>/<dataset>/<run_id>
/<tool>.json` file (same content `write_qa_result()` already produces
locally — `run_single()` calls the exact same writer, just pointed at
an S3-backed path via a small `results_sink` abstraction rather than a
local file, see `qa_tools/common/qa_results_writer.py`'s own note below).
The (b) GitHub Actions workflow itself is **not built** — it needs real
AWS credentials as GitHub secrets, which this sandbox can't create or
verify, so building it here would be unverifiable infrastructure-as-
guesswork. Its real shape is fully specified above; building it for
real is the natural next step once Keith confirms option (b) and can
provide/create the narrow read-only AWS credential it needs.

`qa_results_writer.py` itself was **not modified** — rather than teach
the existing local-filesystem writer about S3, the Lambda handlers call
it normally (writing to Lambda's own `/tmp`, the only writable path in
that runtime) and then a small new `qa_tools/common/results_s3_sink.py`
(new, real, boto3-based, unit-tested with a mocked S3 client) uploads
the resulting file to S3 with the same relative path structure. Keeps
the existing writer's local-file contract, which every non-Lambda
caller and every existing test already depends on, completely
unchanged.

## Lambda handlers

`aws/lambda_handlers/bdm_ingest_handler.py` — `handler(event, context)`:
parses the real S3 `ObjectCreated` event shape (`event["Records"][0]
["s3"]["bucket"]["name"]`/`["object"]["key"]`), matches the key against
`file_arrival.match_arrival()`, downloads the object to `/tmp` via a
plain `boto3.client("s3").download_file()` call, calls
`orchestrate_bdm.run_single()`, uploads the resulting `qa_results/`
file(s) to the results bucket via `results_s3_sink.py`. Returns a small
JSON summary (counts by status) as the Lambda's own return value, useful
for CloudWatch Logs / a Lambda destination on failure.

`aws/lambda_handlers/cp_ingest_handler.py` — same shape, but: matches
against CP's own arrival patterns (6 table patterns + the marker
pattern), calls `add_table_to_run()` for a table file, or — only for a
marker-file match — checks `ManifestMarkerCompletionTracker.is_complete()`
and calls `orchestrate_cp.run_single()` only then.

Both are real, importable Python (verified this sandbox can `import
boto3` — v1.43.93, already a transitive dependency, no new install
needed for that half; nothing AWS-specific about the handler logic
itself has been exercised against a real Lambda runtime or a real S3
event, only against hand-built fixture event dicts in
`tests/test_lambda_handlers.py`).

## Infra (AWS CDK, Python)

`aws/cdk/` — Keith's own explicit choice of IaC tool. **Entirely
unverified** — `cdk synth`/`cdk deploy` need a real AWS account and the
CDK CLI (Node-based), neither available here; this was written
correctly per CDK's documented Python API shape but has never been
synthesized, let alone deployed.

- `aws/cdk/app.py` — the CDK app entry point.
- `aws/cdk/data_pipeline_stack.py` — one stack:
  - Two S3 buckets: raw-data landing bucket (BDM + CP prefixes) and a
    results bucket (Lambda's `qa_results/`-shaped output, per the
    trust-boundary decision above).
  - Two Lambda functions (`bdm-ingest-handler`, `cp-ingest-handler`),
    Python 3.11 runtime (matching this repo's own pinned
    `.python-version`), `boto3` layer/bundled dependency.
  - S3 event notifications wiring each bucket prefix to its Lambda.
  - One DynamoDB table (`cp-delivery-completion`), on-demand billing,
    used only if `DynamoDBCompletionTracker` is the chosen strategy —
    provisioned either way in this MVP so switching strategies later
    doesn't need an infra change, just a config flag.
  - IAM roles scoped narrowly per the trust-boundary decision: each
    Lambda's role gets S3 read on the raw bucket's own prefix, S3 write
    on the results bucket's own prefix, and (CP only) DynamoDB
    read/write on the completion table — no git/GitHub credentials
    anywhere in this stack, by design.

Real dependencies added under a new optional group (not the core
install — this PoC's core dependency set stays exactly as narrow as it
already is for everyone not touching this thread):
`pyproject.toml`'s `[project.optional-dependencies] aws = ["boto3>=1.34",
"aws-cdk-lib>=2.150", "constructs>=10.0"]` — `uv sync --extra aws` to
install. `boto3` alone (already transitively present) is enough for the
Lambda handlers and their tests; `aws-cdk-lib`/`constructs` are only
needed to actually `cdk synth`/`deploy`, not to read or review the CDK
source.

## What's verified vs. not

**Verified, real, tested in this sandbox:**
- `get_run_by()`'s Lambda fallback (5 tests, `tests/
  test_git_identity.py`).
- `file_arrival.match_arrival()` against all three pattern types,
  including a real fixture zip for the archive case (`tests/
  test_file_arrival.py`).
- Both `CompletionTracker` implementations, including the DynamoDB
  one's idempotent-`ADD` and race-condition behavior, against a mocked
  boto3 DynamoDB client (`tests/test_completion_tracker.py`).
- `build_one()`/`add_table_to_run()`/`run_single()` (both datasets)
  produce real, non-empty check results — including real failures on
  the same red-severity dirty fixture data the batch-path tests already
  use — run through the real local tool chain (dbt/Soda/datacontract-
  cli/Evidently) exactly as `./run_pipeline.sh` already does, with no
  manifest.json read from anywhere but the small synthetic one
  `run_single()` itself writes — this sandbox DOES have real access to
  those four tools, just not to AWS (`tests/
  test_orchestrate_single_run.py`). Two real gaps surfaced and got fixed
  while writing this test — see "Two more real gaps found while
  actually building this" above.
- `results_s3_sink.py`'s upload logic against a mocked S3 client.
- Lambda handler event-parsing/routing logic against hand-built fixture
  event dicts (not a real S3 event, but the real, documented S3 event
  JSON shape).

**Not verified, not possible from this sandbox:**
- Any real `cdk synth`/`cdk deploy`.
- Any real S3 event actually invoking a real Lambda.
- Any real DynamoDB read/write (mocked only).
- The proposed `sync-lambda-results.yml` GitHub Actions workflow (not
  built at all — needs real AWS credentials as GitHub secrets).
- Whether the real Lambda Python 3.11 runtime's cold-start time is
  acceptable for this pipeline's real per-run cost (a full 4-tool
  dbt/Soda/datacontract-cli/Evidently run took real, measured time
  locally — see `plans/performance.md` — but Lambda's own 15-minute
  execution limit and memory ceiling have never been checked against
  that real cost).

## Two more real gaps found while actually building this

Both surfaced from real test failures against the real local tool chain
while writing `tests/test_orchestrate_single_run.py` (this sandbox does
have real dbt/Soda/datacontract-cli/Evidently access, just not AWS) -
not hypothetical, and both now have a real, working fix, but worth
naming explicitly since neither was anticipated when this design was
first sketched:

1. **The row-count-growth Evidently check reads `RAW_DIR/manifest.json`
   directly** to find "the immediately preceding run" - there's no
   manifest at all once a Lambda is invoked per arriving file.
   `run_single()` now writes a small, synthetic manifest (just this
   run's own entry, or `[previous_entry, this_entry]` if the new,
   optional `previous_run_id`/`previous_csv` parameters are supplied) so
   the existing check logic keeps working unmodified. **Nobody passes
   `previous_run_id`/`previous_csv` yet** - the Lambda handlers below
   don't track "what was the last delivery for this dataset", so this
   check is silently skipped for every Lambda-triggered run in this MVP
   (the same behavior a genuinely-first-ever run already gets locally -
   not a new failure mode, just a wider one). A real fix needs something
   to track recent-delivery history across invocations (DynamoDB again,
   most likely) - flagged as a real follow-up, not built tonight.
2. **`dataset_stats.compute_dataset_stats()` needs a connection to the
   COMBINED, all-runs warehouse** (`pipeline/load.py`'s `data/
   warehouse.duckdb`, `main.birth_registrations` with a `run_id`
   column), not a per-run one - it doesn't exist at all in a single-
   arrival world. Fixed by having `build_one()` also create a
   `main.birth_registrations` VIEW over its own per-run
   `raw.birth_registrations` table (harmless/unused by dbt/Soda, which
   only ever look at the `raw` schema) and having `run_single()` point
   `orchestrate_bdm.WAREHOUSE_DB_PATH` at that same per-run file for the
   duration of the call (a real module-global rebind, safe because a
   single Lambda invocation is single-threaded) - so the exact same
   `_check_aggregates()`/`_sex_value_counts()`/`_arrival()` queries that
   already work against the combined warehouse also work, unmodified,
   against a per-run file whose `run_id` filter now just matches every
   row in it.

## Open questions for Keith, beyond the four flagged at the top

- **Where does the Evidently reference run come from in production?**
  Locally, `manifest[0]` (always the first, clean run) is the drift
  baseline for every other run. In a real event-driven world, what IS
  the reference run once there's no manifest to read `[0]` from — the
  first run ever ingested for this dataset? A rolling N-days-ago run?
  Pinned explicitly per dataset in a new config value? Not decided here
  — `run_single()` takes it as a required parameter for now, deferring
  the decision to whatever calls it (the Lambda handler currently
  hardcodes the same real `run_01`/`cp_run_01` IDs this repo's synthetic
  data already uses, which is a placeholder, not a real answer).
- **What triggers the (b) sync workflow if not a fixed schedule?** A
  15-minute poll is simple but not truly event-driven end-to-end; S3
  could instead publish to SNS/EventBridge and dispatch a `repository_
  dispatch` GitHub event immediately. Not built either way — flagged as
  a real tuning knob once (b) itself is confirmed.
- **Does this replace or sit alongside the local/manual pipeline?**
  Nothing here removes `./run_pipeline.sh` or the manifest-driven batch
  path — both `orchestrate_*.py` modules keep their existing
  `run_pipeline()`/`run_pipeline_cp()` entry points exactly as they
  were, unchanged, for local dev and any batch/backfill use. This MVP
  is additive.
