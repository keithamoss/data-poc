# Running thoughts

A different kind of file from the other `plans/*.md` ones: this is where
Keith's own forward-looking ideas get captured as they come (often
during a run, voice-dictated, several at once) - unscoped, not yet
questioned or forked, often well beyond this PoC's current build. Not
"decided and built" (that's `qa-pipeline.md`/`publishing-and-history.md`)
and not "a real conceptual tension in how the PoC models something"
(that's `conceptual-design.md`) - just a durable place to land a batch of
raw ideas before the next session so nothing gets lost, and a queue to
work through: scope each one with Keith via clarifying questions before
building, same working pattern as everywhere else in this project.
Created 2026-09-18, after Phase 7 wrapped, at Keith's own explicit
request.

## Batch 1 (2026-09-18, post-Phase-7 run)

Keith's own framing throughout: work through these once the current
loop (Phase 7 / whatever's active) is done, not immediately.

1. **[done, 2026-09-18]** **[GitHub workflow & people]** Ticketing system: GitHub Issues, MVP after this loop.

**Decided** (a real decision, not just an idea - previously an open
question about Jira vs. something else): use GitHub Issues as the
ticketing/case-management system for QA follow-up work, rather than a
separate tool - "that's a really good solution, it's an easy
integration." An MVP of this is next up once the current loop (Phase 6
test coverage / Phase 7 follow-ups) wraps. A subagent was sent off in
parallel (2026-09-18) to research this as a business analyst would -
scoping real GitHub Issues access from this session, and coming back
with clarifying questions for Keith as product owner, before any
scoping conversation happens for real. See that subagent's own findings
once it reports back, rather than re-deriving them here.

Directly related to `docs/remediation-workflow-design.md` (the bad-
data ticketing/case-management design that was deliberately scoped OUT
of this PoC's build - a seam only) - this may be the point that design
actually gets built against, not just designed around. Worth rereading
that doc before scoping the MVP.

**Subagent research findings, 2026-09-18 (business-analyst pass, no
code/issues created)**: Issues ARE enabled on `keithamoss/data-poc`
(confirmed via a real, live `list_issues` call), and this session's own
credentials can read them - `get_me` resolved to Keith's own personal
account, not a scoped service/bot identity, so automation currently
would act with his own full permissions, not a narrower one. The org
already has GitHub's newer Issue Types configured (Task/Bug/Feature) -
a real, empty slot for a 4th type rather than needing to overload
labels. No custom issue fields exist yet (severity/SLA/accept-reject
state would need labels, new custom fields, or body encoding - nothing
pre-built). `docs/remediation-workflow-design.md`'s mechanical parts
(universal creation, one queue, recurrence-as-cross-referenced-issue,
joint ownership, automated status comments, human-required closing) map
cleanly; dedup/escalation/suppression are real application logic GitHub
Issues has no native concept of; and genuine fit gaps were flagged: the
repo's public status (synthetic data was the reason that was fine - a
ticket holding real QA-failure detail is a different calculus), no
per-viewer content redaction (so the doc's provider-facing PK-only
convention becomes the ONLY real mitigation, not one option), external
providers needing real GitHub identities to be first-class actors, and
ticket state living only in GitHub's own live API - a real
discontinuity from this repo's everywhere-else "reconstructable from
committed git history, no live dependency" pattern. Full clarifying-
questions list (9, grouped: MVP scope, ticket lifecycle, roles/access,
platform/technical) was relayed to Keith directly rather than
duplicated here - see chat history for the complete text if needed
again.

**Built, 2026-09-18 (plans/qa-pipeline.md item 76).** Real write access
verified with a real test issue (created, commented, closed). MVP
scope resolved via a second AskUserQuestion round: dataset-level
tickets (not column-level), creation + live status-update comments (no
escalation/suppression yet), a new separate write-permitted GitHub
Action (never deploy-pages.yml), internal-only, red-only. See item 76's
own full writeup - including a real, load-bearing finding surfaced
while building: all 7 real datasets currently read red due to item
74's own already-known threshold-encoding bug, so the workflow ships
WITHOUT its automatic push trigger yet (`workflow_dispatch` only) -
Keith's own call needed on fixing item 74 first vs. accepting the
noise before flipping it on for real.

2. **[done, 2026-09-18]** **[GitHub workflow & people]** Data-asset-level people/roles config.

A new config file (alongside `contract/data-asset.yaml`'s existing
data-asset-level, not per-dataset, scope) listing the people who work on
a data asset: name, email, nickname, and optionally which
datasets/agencies they're assigned to. People carry one or more roles
(QA, peer review, manager mentioned so far - likely not an exhaustive
list). Purpose: drives the GitHub Issues ticketing system above - who a
ticket gets assigned to, and probably who's allowed to do what (e.g.
peer review vs. the original QA-er). Explicitly tied to idea #1, not a
standalone piece - scope together.

**Built, 2026-09-18 evening.** Scoped via one `AskUserQuestion` round:
drives real GitHub ticket assignment (not gating who may `/accept` -
explicitly left for a later pass); per-dataset/agency assignment, not
one flat data-asset-wide list; and shown in the dashboard too, not
backend-only.

New `contract/people.yaml` (real schema documented in its own header
comment) + `qa_tools/common/people.py` (pure parse/resolve, mirroring
`ticket_status.py`'s own real-parse/real-write split). Dataset-level
assignments win OUTRIGHT over agency-level ones - never merged, so
"who's assigned to this dataset" always has exactly one real source.
Wired into `ticket_sync.py`'s `open_ticket()` (`--assignee`, omitted
entirely when nobody's configured) and into the dashboard as a new
`ASSIGNMENTS` const with a real "Owned by" badge on the agency/dataset
headers - verified end to end with fake fixture people (agency-level,
a dataset-level override, and the agency-level fallback for a sibling
dataset with no override of its own, each behaving exactly as
designed).

**Deliberately shipped with `contract/people.yaml` still empty** - this
session doesn't know Keith's real email or full name and won't guess at
personal details, even small ones; every consumer already degrades
gracefully to "nobody assigned" (no real committed entries yet, same
treatment every other optional embedded feed here gets). Real people
are Keith's to add.

Real GitHub emails are never embedded into the publicly-deployed
dashboard (this repo is public) - only name/nickname/github/role ever
reach the built page; `embed_dashboard_data.py` strips `email` at embed
time.

**Keith's own offer, 2026-09-19 evening, not yet acted on**: he offered
to explain more about who the real users are and what each real role
(QA, peer review, manager) actually looks like day to day - raised
during the HCI/behavioral-psychology grounding work (`plans/wider.md`
#10), as something that would sharpen both that work's personas AND
this item's own roles (today just labels driving ticket assignment/the
"Owned by" badge, with no real description of what each role actually
does). Captured here so it survives compaction - ask him for this
directly next time it's relevant, don't let it quietly drop.

**PART-ANSWERED 2026-09-20 (Keith, in passing, while settling the
changelog rewrite's audience).** The real user tiers, in his own words
and roughly in seniority order:

1. **Executive** - the tier the dashboard's own top level is already
   named after.
2. **Director** - Keith himself.
3. **Manager**.
4. **Senior staff** - "so like senior data engineers".
5. **Operators** - "the actual operators of the tools, so the data
   engineers".
6. **Client services / customer service** - flagged as a *maybe*
   ("there's maybe another audience"). Genuinely different from the
   other five, and **not in the way first guessed here.** The initial
   note said they field questions from whoever consumes the data;
   Keith corrected that the same day: *"the intent for client services
   is not to field questions. It's for them to just be aware of and
   across what is happening during a refresh cycle."* So their need is
   **situational awareness on a cadence**, not lookup - closer to a
   subscriber than a user. Worth holding on to, because "awareness of
   a refresh cycle" is a genuinely different UI from anything this
   dashboard does today, which is all drill-down from a current state.

Still a list of labels, not personas - what is missing is what each
actually DOES day to day, which is the part Keith's original offer
above covers and this does not. But it settles the shape: **six tiers,
not the three role labels `contract/people.yaml` carries today.**

**The name clash is resolved (Keith, 2026-09-20).** The dashboard's own
view hierarchy had a "Tier 1 / Executive", which collided with tier 1
of this user model while meaning something entirely different - a view
level, not an audience. His call on that being flagged: **rename the
dashboard's Tier 1 to "Home"**, and leave Agency, Dataset and Column
as they are. That frees "Executive" to mean only the user tier.

Scoped before logging: the rename is **label-only**, which is better
than it first looked. Four user-visible occurrences in the template's
rail and heading, plus comments; the internal state key stays `exec`
and tier 1's URL is already `/` rather than `/executive`, so no route,
bookmark or state shape changes. One `tests-js/navigation.test.js` test
name mentions "executive tier" and should follow for clarity.

Landed here rather than in a new item because it is the direct answer
to this item's own open offer.

3. **[done, 2026-09-18]** **[Dashboard UI]** Gamification MVP on the reporting dashboard.

A small MVP that celebrates staff turning QA around fast, or
consistently getting green datasets - "some kind of gamified thing."
Genuinely vague still ("we can talk about that") - no shape decided
yet (leaderboard? badges? a streak counter? per-agency vs. per-person?).
Needs a real scoping conversation before building anything, not just an
implementation guess.

**Built, 2026-09-18 evening.** Scoped via two real `AskUserQuestion`
rounds: consistency (green streaks), not turnaround speed; a
leaderboard, not badges/a bare counter; per-person, not per-agency -
each a real fork, not a guess. Two more forks fell out of turning
"consistency" into an actual computation: amber does NOT break a
streak (only a real red run does - Keith's own call, given how common
amber legitimately is, 77 real BDM runs alone), and a streak is scored
per (person, dataset), not blended across everything a person's
touched - keeps BDM and CP's genuinely different check batteries from
being compared as if they were the same thing.

A streak belongs to a PERSON's own chronological sequence of runs on
one dataset - `qa_tools/common/leaderboard.py`'s `compute_streaks()`
skips over any other person's interleaved runs entirely (they neither
extend nor break this person's own streak), then counts backward from
their own most recent run until hitting a red one. New `status_by_run()`
in `dataset_status.py` is the Python port of the dashboard's own
client-side `datasetStatusByRun()` (real per-run status, not just
"current") - found and documented a genuine quirk of that already-
shipped JS function while porting it (an all-green run is never
explicitly recorded, only implied by absence - callers must default a
missing run_id to green), mirrored faithfully rather than "fixed",
since the real behavior is already correct end-to-end via that
convention.

Same privacy rule as item #2's ASSIGNMENTS (this repo is public): only
people with a real `contract/people.yaml` entry ever appear, by name/
nickname - `run_by` is a real email, never shown bare. A 5th header
panel ("🏆 Leaderboard") reuses the existing `openPanel()`/`closePanel()`
mechanism from items #6-#9's own work, not a new pattern.

Verified against this repo's own real committed history (not just
fixtures): a real run_by identity already exists in real `qa_results/`
(a private-relay email, the same real git identity this whole project's
history was generated under) - with a fake `contract/people.yaml` entry
for it, the leaderboard correctly produced 5 real rows across BDM and
4 real CP tables, sorted by streak descending (18/4/2/2/2), with a real
browser confirming the panel renders, opens as a real history entry,
and Back closes it, zero console errors. Deliberately left the REAL
`contract/people.yaml` empty rather than seeding it with that real
identity myself - same reasoning as item #2 (not this session's call to
make unilaterally); Keith can add himself to see this fill in for real.

**Redesigned, 2026-09-18 later the same evening - the automation-tension
follow-up.** Right after shipping the above, Keith raised a real problem
with it unprompted: "how will automating running factor in" - item #5
Thread B's own future AWS/S3-event-triggered vision has QA running
happen with no human "clicking run" at all, so the original design's
whole foundation (`run_by`, a real git identity captured at RUN time)
has nothing left to attach to once running itself is automated. Scoped
via two more real `AskUserQuestion` rounds (four total across this
item's life): the human role SHIFTS rather than the leaderboard just
going away ("I think it shifts"); what's worth celebrating once running
is automated is "resolving red to green"; this is a redesign to make
NOW, not a known future change to just document and defer (Keith
explicitly overrode this session's own "recommended: defer" default);
and the metric shape is "streak of clean resolutions" - a person's own
last N real GitHub tickets closed in a row that were never reopened,
picked after the first attempt at asking that question used jargon
("continuous per-run state") Keith flagged directly ("explain the
question again") - re-asked with a plain, worked example instead.

The mapping from "resolving red to green" to "whoever closes the real
GitHub ticket" is this session's own reasoning, not something Keith was
separately asked to confirm in as many words: `qa_tools/common/
ticket_sync.py`'s own repeated, load-bearing design principle -
"closing it is always a human decision, never automatic" - makes
ticket-closing the one real action in this whole system already
guaranteed to require a person, regardless of whether the QA run that
opened the ticket was ever triggered by one. Worth Keith double-checking
that inference specifically, not just the four scoped forks above.

Fully replaced the original run-based design (not kept alongside) -
`qa_tools/common/leaderboard.py`'s own module docstring says so, and
git history (`git log -p` on that file) has the full original
implementation if it's ever needed again. New real-fetch/pure-parse
split, same convention as `ticket_status.py`/`acceptance_sync.py`:
`fetch_ticket_resolution()`/`fetch_all_ticket_resolutions()` are the one
real `gh` boundary, now including a call to GitHub's classic Issue
Events API (`gh api repos/{owner}/{repo}/issues/{n}/events`) - the only
way to learn WHO closed/reopened a ticket, since `gh issue view --json`
exposes `closedAt` but never an actor. **Partially unverified against
real GitHub behavior**: no `gh` CLI is available in this sandbox, so the
endpoint itself was verified for real via a direct authenticated REST
call using this session's own `GITHUB_TOKEN` (confirmed reachable,
confirmed the real `event`/`actor.login`/`created_at` shape - but only
against a real `labeled` event on this repo's own issue #2, since none
of the 7 real tickets this project has ever opened has actually been
closed yet). The `closed`/`reopened` event shape itself is GitHub's own
long-documented, stable behavior, not something this session invented -
but genuinely worth Keith watching the first time a real ticket gets
closed, to confirm it resolves exactly as designed.

This also changes the leaderboard from fully CI-safe-with-no-token (the
original design needed nothing beyond committed `qa_results/` +
already-built dashboard JSON) to needing a real `gh` fetch step in
`.github/workflows/deploy-pages.yml`, same treatment TICKET_STATUS/
ACCEPTANCES already have - a real, deliberate architectural cost of this
redesign, not an oversight. Identity also shifted from a real git email
(`run_by`, resolved against `contract/people.yaml`'s `email:` field) to
a real GitHub login (`ticket_sync.py`'s own `--assignee` field,
resolved against that same file's `github:` field instead) - a
ticket-close event has no email attached at all.

**Real CI bug, caught and fixed the same evening, before this ever
reached Pages.** This redesign's own first live CI run (commit
`48b89a7`) failed on its own new step: `gh api .../events -f
per_page=100` returned a real 415 - `gh api` silently switches an
otherwise-GET request to POST the moment ANY `-f`/`-F` param is given
(unless `-X GET` is also passed explicitly), and this read-only
endpoint doesn't accept POST. Confirmed directly against this repo's
own real issue #8 while diagnosing (the same call via `-f` returns 415;
a plain GET with `?per_page=100` in the URL returns 200). Fixed by
moving `per_page` into the URL's own query string; added a regression
test (`tests/test_leaderboard.py`) that locks in the `gh` invocation
shape without needing a real `gh`/network call. Nothing broken ever
reached Pages - the gate caught it before the deploy step ran. Fixed in
`6fa8039`, confirmed green on the next real CI run.

4. **[investigate, 2026-09-18]** **[GitHub workflow & people]** GitHub Issues -> Microsoft Teams integration (research first).

Idea: live notifications into a Microsoft Teams chat as datasets arrive
and get QA'd - possibly with a small piece of the gamification idea
(#3) folded in, celebrating individual staff members' wins in the Teams
feed itself. **Architecturally important, clarified 2026-09-18 (Keith's
own follow-up, in case it wasn't clear the first time round): this
tool/pipeline never talks to Teams directly, and never gets its own
Teams webhook/bot credentials.** GitHub Issues (#1) is the ONLY
integration point - Teams is notified purely via GitHub's own
Teams<->GitHub bridge (an existing Microsoft/GitHub connector, not
something this project builds), subscribed to this repo's Issues
activity. So the pipeline's own job stops at "open/update/comment on a
real GitHub Issue accurately" - everything from there to a Teams
channel is GitHub's and Teams' own integration, not this codebase's
concern or code. Keith's own framing: "do some research online" first -
this is a research task (what's actually possible/idiomatic for that
GitHub<->Teams connector - what it can/can't surface, whether it
supports enough granularity for the gamification angle - not yet a
build task, and specifically not a "build a Teams webhook integration"
task).

**Research done, 2026-09-18 evening.** Confirmed for real (official
GitHub docs snippets, GitHub's own open-source `integrations/microsoft-
teams` repo, the app's own Marketplace listing - `docs.github.com`
itself was unreachable from this sandbox, egress-blocked, so verified
via search-engine-crawled snippets of that same official content plus
whatever of the source repo `github.com` itself would serve directly):

- It's the official, actively-maintained "GitHub for Microsoft Teams"
  Bot Framework app - not a legacy Office 365 Connector (those are being
  retired across Microsoft 365 generally; unrelated tech, no
  deprecation risk here).
- `@GitHub subscribe org/repo` in a channel, scopable to specific event
  "features" (issues, pull requests, reviews, comments, workflow runs at
  minimum).
- **Label filtering is real and works for issues**: `@GitHub subscribe
  org/repo+label:"qa-ticket"` - every real ticket this pipeline opens
  already carries that label (plus a per-dataset `dataset:<id>` one), so
  a channel could subscribe to just this pipeline's own tickets.
- **Hard constraint**: no custom message content. The app's card layout
  is fixed - there's no way to inject our own text into what Teams
  renders. The only lever this pipeline has at all is what `ticket_
  sync.py` already writes into the real GitHub issue/comment, which
  Teams then mirrors verbatim.
- **Keith's call on that constraint**: try to carry the gamification
  angle over anyway, via the existing real comment body (not a separate
  custom card) - low-effort, no guarantee it reads well in the resulting
  Teams thread, not yet attempted.

**Parked as a known unknown, 2026-09-18 evening (Keith's own call):**
whether the Teams close-event card actually NAMES who closed the
ticket, or just shows the new status - every source describes the
card's shape (threaded reply, parent card carries title/status/
assignees/labels/checks) without confirming an actor field on a close
event specifically. Pushed hard on this from multiple angles (official
docs, the source repo, the Marketplace listing, `teams.github.com`,
Wayback Machine, a text-proxy fetcher, ~8 different search phrasings)
and hit a genuine wall: this sandbox's egress proxy blocks every domain
except `github.com` itself, and no search-engine snippet quotes the
actual close-event card content either way. Not resolvable by more
searching from THIS environment - settling it for real needs either (a)
someone installing the app in a real Teams channel and watching an
actual close event, or (b) research from an environment with
unrestricted web access. One relevant data point either way: GitHub's
own Issue Events API (verified live against this repo's own ticket #8
while building item #3's redesign above) DOES carry a real actor on
every event, so the underlying data GitHub has to work with is there
even if the Teams card doesn't surface it.

**Priority: work through today/tomorrow (2026-09-19, Keith's own
explicit ask).** Worth checking first whether CLAUDE.md's own new
blocked-domain-reporting convention (added the same day, after this
item's own egress-block discovery) has since gotten Keith to widen
network access for this environment - if so, the "research from an
environment with unrestricted web access" option above might now
actually be available, rather than still needing a real Teams
installation to settle the actor-field question.

5. **[done, 2026-09-19]** **[Pipeline & publishing]** Staff adoption - two threads.

Motivation: Keith wants staff to actually start using this tool/
pipeline for real, not just as a PoC demo. Two genuinely separate
threads:

**Thread A - fit into today's actual workflow.** Staff currently pull
data down from S3 buckets or local storage themselves. Whatever this
tool becomes needs to fit that existing motion, not replace it outright
on day one.

**Built, 2026-09-19 morning - Keith's own "Let's go" once Thread B's
overnight build was reviewed.** Scoped first via two real
`AskUserQuestion` rounds, since this thread was explicitly blocked on
real specifics only Keith had: staff are **data engineers/analysts**
(comfortable with a CLI, not needing a GUI-first experience); today's
real pull is **manual download + local processing** (no existing
scheduled/scripted sync to hook into); and the right trigger point is
**on demand, after the manual pull** - someone runs a check themselves
once they already have the file, not something that fires automatically.
A second round resolved a real fork this surfaced while designing the
CLI: should an ad hoc check write into the real, permanent `qa_results/`
git history? **Throwaway by default, `--commit` to keep it** - Keith's
own explicit call, recommended option.

This maps directly onto the single-arrival entry points Thread B had
already built the same night (`orchestrate_bdm.run_single()`/
`orchestrate_cp.run_single()`) - reused as-is, invoked locally instead of
from an S3 event, rather than building a second QA-running code path.

- `qa_tools/common/local_check.py` - shared helpers: `run_id_from_path()`
  (a real, sortable, collision-resistant id from the source file/folder's
  own name + a real UTC timestamp - no manifest to draw one from),
  `copy_into()` (mirrors `run_single()`'s own arrived-file normalization,
  reused here for the user-supplied reference file/folder too), and
  `format_report()` (a short, human-readable pass/warn/fail/error summary
  with every real failing/warning check's own label and metric - this
  CLI's audience is someone deciding whether to trust a file, not
  something re-parsing JSON).
- `qa_tools/bdm/check_file.py` / `qa_tools/cp/check_delivery.py` - the
  two real CLIs (`uv run python3 -m qa_tools.bdm.check_file <csv>
  --reference-csv <known-good.csv>` / `...cp.check_delivery <folder>
  --reference-folder <known-good-folder>`), documented in `README.md`'s
  own new "On-demand checks against a file you already have" section.
  `check_delivery.py` loads all 6 real CP tables up front (a person
  running this by hand already has the whole delivery in one folder -
  no "wait for the rest to arrive" case the way Thread B's Lambda-
  triggered per-file arrivals have) and errors clearly on a partial
  delivery rather than attempting a partial run. `--commit` reuses
  `git_identity.get_run_by()` for the same real attribution every other
  committed run gets; the default (no `--commit`) path redirects every
  tool's own `write_qa_result()` to a throwaway tmp dir via `qa_tools/
  common/lambda_results_dir.py`'s `patch_write_qa_result_for_lambda()` -
  the exact same Lambda-writability fix Thread B built, reused here for
  a different reason (never touching the real committed history) rather
  than duplicated.

**Two real bugs found and fixed while writing this session's own
integration tests, not assumed correct on the first pass**: (1)
`orchestrate_bdm.run_single()`'s call to `build_one()` (and, mirrored
here, `check_delivery.py`'s calls to `add_table_to_run()`) omitted
`out_dir`/`raw_dir` as explicit keyword arguments - Python binds a
default parameter value once, at the function's own definition/import
time, so a caller monkeypatching the module's `OUT_DIR`/`CP_RAW_DIR`
constant afterwards was silently ignored, and the real code went ahead
and wrote into this repo's own actual `data/duckdb_runs/`/`data/
cp_duckdb_runs/`/`data/raw/`/`data/cp_raw/` directories instead of the
test's own tmp dir - reproduced for real (stray files genuinely
appeared there) before being caught and fixed, cleaned up immediately,
confirmed gitignored so nothing reached git either time. Fixed by
passing `out_dir=`/`raw_dir=` explicitly, read off the module attribute
at call time, the same fix `run_single()`'s own code comment already
documents for the identical class of bug found the night before.

Verified: `tests/test_local_check.py` (7 tests, pure), `tests/
test_check_cli.py` (4 real integration tests against the real local dbt/
Soda/datacontract-cli/Evidently chain - real failures reported, real
exit codes, and a real assertion that a non-`--commit` run never creates
anything under the real, permanent `qa_results/` path), `uv run ruff
check .` clean.

**Rebuilt with Click, 2026-09-19 (Keith's own explicit ask), same
morning.** Both CLIs rewritten from argparse to real `@click.command()`s
- `click.Path(exists=True, ...)` now rejects a typo'd path before any
real tool ever runs (previously a plain string that would only fail
later, inside `orchestrate_bdm.run_single()`/`_load_delivery()`), and
the partial-delivery error in `check_delivery.py` is now a real
`click.ClickException` rather than a bare `SystemExit(message)`. `click`
added as a real, direct `pyproject.toml` dependency (it was already
present transitively, via dbt-core/datacontract-cli, but this project's
own convention is to declare what it directly imports, not rely on
someone else's transitive pin). Tests rewritten to drive both commands
through `click.testing.CliRunner` - Click's own standard test harness -
instead of calling `main()` directly; two new tests added for the
path-validation behavior Click now provides for free. Verified: 12
tests in `tests/test_check_cli.py` (up from 4, the 8 new ones covering
the same ground as before plus the two new Click-validation cases),
`uv run ruff check .` clean, and the real `--help` output for both
commands checked by hand against an actual invocation.

**Thread B - an AWS MVP that reacts to real S3 events.** Deploy this
pipeline (or some version of it) to AWS, triggered by real S3 events as
files land, running the QA pipeline automatically rather than as a
manually-kicked-off local script. Real complications flagged already,
not yet solved:

- Files can arrive in different shapes: individually, in nested
  folders, or as zip files - and file names themselves can vary. The
  ODCS contract's own metadata needs to be able to express enough to
  correctly match an arriving file (whatever shape it's in) to the
  right dataset - not yet designed.
- Real dependency ordering, using Child Protection as the concrete
  example: Keith wants to QA all of a collection's tables at once (all
  6 CP tables together), and only THEN run the cross-table referential-
  integrity checks (the ones that depend on more than one table already
  being loaded) - not interleaved with per-table QA runs. This is a real
  orchestration/sequencing design question for the AWS-event-driven
  version, not something the current local, manually-sequenced pipeline
  had to solve.
- **Already caused one real redesign, 2026-09-18**: item #3's own
  leaderboard originally credited whoever's local `git config user.email`
  ran the QA tooling (`run_by`) - which has nothing to attach to once
  running itself is automated under this thread's own vision. Redesigned
  the same day to credit ticket-CLOSING instead (a real human decision
  that survives automation regardless of what triggered the run) - see
  item #3's own "Redesigned" write-up for the full account. Worth
  re-checking every other `run_by`-based feature (the changelog/activity
  feed, anything else built on `git_identity.py`) against this same
  question before this thread's AWS MVP is ever actually built, not just
  the leaderboard.

**Thread B built overnight, 2026-09-18/19 - Keith's own explicit
instruction** ("Crack on with Thread B overnight and we'll pick this all
up again in the morning"), scoped just beforehand via one more real
`AskUserQuestion` round (IaC tooling: **AWS CDK, Python**, over SAM/
Terraform; MVP scope: **both BDM and CP together**, including CP's
completion-signal wiring, not BDM-only). Thread A stayed blocked on real
specifics about Keith's actual staff workflow that this session doesn't
have - not picked up. Full design write-up: `docs/aws-event-driven-mvp-
design.md` - this entry is a summary, not a duplicate; read that file for
the real architecture, the flagged trust-boundary recommendation, and the
full "what's verified vs. not" account.

**No real AWS access exists in this sandbox** (checked directly before
starting: no `aws` CLI; `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` hold
the literal string "proxy-injected") - real design + real code, written
correctly, for Keith's morning review, but genuinely undeployed and
untested against real AWS. What IS real and tested here: the file-arrival
pattern matching, the CP completion-tracking logic, the single-run
orchestration entry points (run against the real local dbt/Soda/
datacontract-cli/Evidently chain, not stubbed), and the Lambda handlers'
own event-routing logic (fixture events, mocked boto3).

Built: `qa_tools/common/file_arrival.py` (single_file/nested_folder/
zip_archive pattern matching for the proposed `arrivalPattern` contract
extension - a design-doc-only proposal, deliberately NOT applied to the
real production contract YAML files, since there was no way to verify
overnight that it wouldn't break real Soda/dbt/datacontract-cli parsing -
see `CLAUDE.md`'s own YAML-quoting incident for exactly the kind of
mistake that would be); `qa_tools/cp/completion_tracker.py` (three real
strategies - `ManifestMarkerCompletionTracker`, the recommended MVP
default, no state store at all; `DynamoDBCompletionTracker`, the real
alternative if a source system can't guarantee a marker lands last;
`InMemoryCompletionTracker` for tests); single-run entry points
(`orchestrate_bdm.run_single()`/`orchestrate_cp.run_single()`, reusing
`_run_one()` unchanged, plus `build_per_run_warehouses.build_one()`/
`build_cp_warehouses.add_table_to_run()` factored out of the existing
per-manifest-entry loops); `qa_tools/common/results_s3_sink.py` and
`qa_tools/common/lambda_results_dir.py` (the S3-write half of the
trust-boundary design, and a real fix for `write_qa_result()`'s default
output path being unwritable inside a real Lambda); `aws/lambda_handlers/
bdm_ingest_handler.py`/`cp_ingest_handler.py`; `aws/cdk/app.py`/
`data_pipeline_stack.py` (built by a background agent, reviewed before
integrating).

**The `run_by` Lambda-context fix flagged above as a real prerequisite
got done first**, exactly as flagged: `qa_tools/common/git_identity.py`'s
`get_run_by()` now checks `AWS_LAMBDA_FUNCTION_NAME` (set only by the
real Lambda service) before ever shelling out to `git config`, returning
a real `aws-lambda:<function-name>` service identity - not a placeholder.
One other real `run_by` consumer audited (the changelog/"Recent activity"
panel): it'll render an unresolved raw string for a Lambda-attributed run
(no `contract/people.yaml` match), which is honest, not broken - flagged
in the design doc as a possible future nicety, not built.

**Two real architectural gaps found live while writing the single-run
integration tests** (not anticipated when this was first sketched, both
now fixed, both documented in the design doc's own "Two more real gaps"
section): the row-count-growth Evidently check needs a manifest to find
"the previous run," which doesn't exist per-arrival - `run_single()` now
writes a small synthetic one (optionally two-entry, if a caller ever
supplies `previous_run_id`/`previous_csv` - nothing does yet, so this
check is silently skipped for every Lambda-triggered run in this MVP,
flagged as a real follow-up); and `dataset_stats` computation needs the
COMBINED warehouse, not a per-run one - fixed by having `build_one()`
also create a `main.birth_registrations` VIEW over its own per-run table,
and having `run_single()` point `WAREHOUSE_DB_PATH` at that file for the
call's duration (a real module-global rebind, safe since one Lambda
invocation is single-threaded).

**The biggest open decision, clearly flagged for Keith's morning review,
not silently resolved**: how a Lambda-produced result ever reaches the
committed `qa_results/` git history without Lambda holding git-write
credentials. Recommended: Lambda writes to S3 only; a separate, not-yet-
built GitHub Actions workflow (needs real AWS credentials as a GitHub
secret - can't create or verify that from this sandbox) pulls from S3 and
commits, reusing the exact "CI is the only publish path" trust model
`plans/publishing-and-history.md` Thread A already established for the
dashboard. Two other options considered and rejected/deferred - see the
design doc's own "Getting results back into git" section for the full
tradeoff writeup.

Verified: `uv run pytest` (all new tests pass - `test_file_arrival.py`,
`test_completion_tracker.py`, `test_results_s3_sink.py`,
`test_orchestrate_single_run.py`, `test_lambda_handlers.py`,
`test_lambda_results_dir.py`, plus the existing BDM/CP/orchestrate suite
re-run for regressions, all green), `uv run ruff check .` clean. Full
suite + coverage check still to run before this is considered fully
verified for the morning.

6. **[done, 2026-09-18]** **[GitHub workflow & people]** Read-only tension: accepting/rejecting Amber supplies.

A genuine, not-yet-resolved tension Keith flagged himself, directly
building on the amber-governance question already parked in
`plans/conceptual-design.md` Thread A (option 3 there: "a human taking
a decision, accept/reject"). Keith's own instinct is to keep this whole
tool READ-ONLY, but he can see a real need for a human to accept/reject
an amber supply - which is inherently a WRITE. Two possible directions,
neither chosen yet:

1. Drive that write back through GitHub Issues (idea #1) - i.e. the
   ticketing system becomes the write path, and this tool stays read-
   only in the sense of never being written to directly, only ever
   reflecting ticket state.
2. A separate data store just for QA reporting - S3 + Parquet was his
   own example - kept deliberately separate from the real production
   Postgres database, "at least until we have a good mature data model
   and this is stable," with a possible later migration once it's
   proven out.

Explicitly undecided - "I don't know how to handle it" - needs a real
scoping conversation, not a guess. Directly gates idea #1's ticketing
MVP scope (does accept/reject live IN the ticket, or does the ticket
just point at a separate acceptance record?) so probably needs
resolving alongside it, not after.

**Built, 2026-09-18 evening (mechanism only - the amber-GOVERNANCE
question above stays parked, deliberately not resolved by this).**
Scoped across three real rounds of `AskUserQuestion` plus a follow-up
"how do we make this near-real-time" question, each resolved before
building:

- **Write path**: a human comments `/accept` on the dataset's own real
  GitHub Issue - never a button in the dashboard (this tool has no
  backend, so there's nowhere for one to write to). The dashboard stays
  genuinely read-only; the write happens on GitHub itself, the same
  place a data steward already works.
- **No run_id needed**: every real run already has a real arrival
  window (its own `arrived_date` up to the next run's, sourced from
  committed `qa_results/` history, no live data) - a bare `/accept`
  comment is matched to whichever run's window contains the comment's
  own real timestamp. Nobody types or copies an identifier.
- **Ticketing scope widened to amber**: `qa_tools/common/ticket_sync.py`
  was red-only - an amber-only dataset had no real ticket to comment on
  at all. Now opens (and keeps commenting on) a real ticket for amber
  too.
- **Effect of accept**: the pill stays amber - accepting never silently
  reads as green. A small "✓ Accepted by `<user>`" badge appears next
  to it, linking to the real comment, gated on the SAME client-side
  amber computation the row's own pill already uses (never trusts a
  stray `/accept` timestamp that happens to fall inside a run that
  wasn't actually amber).
- **Per-run, not standing**: a new amber arrival gets its own fresh
  window and needs its own fresh `/accept` - an old acceptance never
  silently carries forward.
- **Near-real-time**: `deploy-pages.yml` gained an `issue_comment`
  trigger (re-running the SAME build/validate/publish job, not a
  duplicate workflow - explicitly not following `ticket_sync.py`'s own
  separate-workflow precedent here, since this trigger is still a pure
  read, never a write back to GitHub), gated by a job-level `if:` so
  only a real `/accept` on a real `qa-ticket` issue pays for a rebuild.
  Realistic latency: roughly 1-2 minutes from comment to live page.
- **Reject deliberately out of scope** for this pass - it implies
  actually changing displayed status, which is the amber-governance
  question this build explicitly left parked.

New `qa_tools/common/acceptance_sync.py` (real-fetch/pure-match split,
mirroring `ticket_status.py`/`ticket_sync.py`'s own precedent exactly),
wired into `embed_dashboard_data.py` as a new `ACCEPTANCES` const.
Verified: 9 tests for the widened `ticket_sync.py`, 15 pure tests for
`acceptance_sync.py` (including against this repo's own real committed
`qa_results/` history - confirmed all 6 real Child Protection tables
correctly share the same real collection-level run windows, not 6
separate per-table histories), 2 real-browser e2e tests confirming a
fake-but-realistic `/accept` comment resolves to the exact right real
amber run and renders its badge while a different amber run with no
comment shows none, full JS suite (71 passed), ruff clean.

**`/reject` built, 2026-09-19 (Keith's own explicit ask, "let's tackle
item six") - the amber-GOVERNANCE question this item's own original
build deliberately parked is now resolved.** See
`plans/conceptual-design.md` Thread A's own "Resolved" write-up for the
full account (the three-option governance question, the scoping round,
and the real bug found/fixed along the way - a same-day `arrived_date`
collision that made most of today's real committed history structurally
unmatchable). Summary: option 3 (explicit per-run human decision), a
real `/reject` comment mirroring `/accept` exactly, a rejected run's
pill still stays amber (same non-invasive treatment as accept, just a
different badge), most-recent-comment-wins if a run's window somehow
carries both. `ACCEPTANCES` generalized to `AMBER_DECISIONS`
(`acceptance_sync.py`'s `build_acceptances()`/`match_acceptances()`
renamed `build_decisions()`/`match_decisions()`, now returning a
`decision: "accept"|"reject"` field); the dashboard's own
`acceptanceBadge()` renamed `amberDecisionBadge()`. 9 new/updated Python
tests, 3 new e2e tests, verified with a real Playwright screenshot of
both badge kinds rendering correctly side by side against real
committed amber runs.

7. **[done, 2026-09-18]** **[Dashboard UI]** Business requirements page on the dashboard.

A new dashboard page/view showing live-maintained user stories,
requirements, and acceptance criteria for what's actually being built -
generated from and kept in sync with real work, not a one-off document.
Wants to track MoSCoW priority (Must/Should/Could/Won't) per
requirement, implementation status (built yet or not), and a real tie-
back to the actual tests/integration tests that verify each one. Framed
as wanting to start "today" as a small MVP, but this is a substantial
new feature (a real live data model for requirements, not just static
text) - needs scoping like anything else, "today" is Keith's own
enthusiasm, not a commitment already made.

**Scoped and built, 2026-09-18 (plans/qa-pipeline.md item 75)** -
Keith's own explicit "go do a bit of work" pickup. Scoped via a real
round of `AskUserQuestion` first, per this project's own standing
convention, rather than guessed: structured YAML with typed fields
(his own choice - a deliberate departure from the hand-prose
`CHANGELOG.md` pattern this session recommended), high-level user-story
granularity (~10-30, not a 1:1 mirror of this file's own numbered
items), and real CI-ENFORCED test linkage (his choice again, stronger
than the "soft manual reference" MVP default recommended) - a
requirement claiming `built` status with no real, AST-verified test
behind it now fails CI. See item 75's own writeup for the full build
(schema, validator, panel UI, tests) - this entry stays as the
original ask for context, not duplicated there.

8. **[done, 2026-09-18]** **[Dashboard UI]** Deep links from the dashboard back into GitHub.

Two related, smaller asks:

- Clicking a CHECK in the dashboard should link back to the actual code
  in GitHub that implements it (the real dbt test/Soda check/
  datacontract rule/Evidently preset - each check already carries a
  real `check_id` and lifecycle metadata, `qa_tools/common/
  check_lifecycle.py`, so the underlying identity to link from likely
  already exists; where each `check_id` maps to a real file/line in
  GitHub doesn't yet).
- Clicking a DATASET (or an AGENCY) should link to its real subfolder
  in GitHub.

Smaller, more mechanical than the other ideas here - plausibly a quick
win once scoped, but still needs a real "how" pass (a generated mapping
from check_id/dataset/agency to a real GitHub URL, kept in sync as
things move) before building.

**Built, 2026-09-18 evening.** Scoped via one `AskUserQuestion` round
first (three real forks, all resolved to the recommended option): links
pin to the exact commit the dashboard was built from, not a moving
branch (`GITHUB_SHA` in CI, `git rev-parse HEAD` locally - matches this
project's existing reproducibility stance, qa_results/ and snapshots);
a dataset/agency link points at its real `qa_tools/<bdm|cp>/` folder
(this repo's already-established one-folder-per-dataset convention),
doubling as the agency link too since each real agency maps to exactly
one dataset/collection today; and a check link gets a real `#L<line>`
anchor, not just the file.

New module `qa_tools/common/github_links.py` - `build_check_source_
links()` reuses `validate_check_lifecycle.collect_checks(None)` (the
same source-file list check-lifecycle CI validation already walks, so
never drifts out of sync with it) and finds each check's real line via
a plain text scan for its own check_id's literal value - deliberately
not a per-tool YAML/AST parse, since check_id is already guaranteed
globally unique and appears as a distinctive literal string in all 3
real formats checks are authored in (dbt/soda's `check_id: <value>`,
the ODCS contract's `value: <value>` under a `- property: check_id`
customProperty, Evidently's `SOME_CHECK_ID = "<value>"` constant) -
verified against real file content for all 3 before writing it, not
assumed. `build_folder_links()` maps the small, real, currently-1:1
agency/dataset -> qa_tools folder table.

Wired into `dashboard/embed_dashboard_data.py` as a new `GITHUB_LINKS`
const (`{checks, agencies, datasets}`), same embed-at-build-time pattern
as every other real feed on the page - CI-safe, no live data touched.
UI: a small "View source" link in the check-detail panel header
(`check.check_id` was already threaded all the way through to the
frontend, so this needed no new data plumbing beyond the link map
itself), and a "View on GitHub" link on the agency (Tier 2) and dataset
(Tier 3) page headers, reusing `ticketBadge()`'s own real-link-or-
nothing pattern.

Verified: `tests/test_github_links.py` (7 tests, against this repo's
own real committed check-definition files, not a fixture - a fixture-
based test would only prove the line-finding algorithm works on data
written to match it), full JS suite (71 passed), `tests/test_dashboard_
e2e.py`/`test_check_dashboard_renders.py` (22 passed), ruff clean, plus
a manual real-browser walkthrough confirming all 3 link types resolve
to the exact right file/line/folder with zero console errors.

## Also flagged, queued separately (not part of the "running thoughts"
batch above, but landed in the same conversation)

- **Child Protection resupplies** - **[built, 2026-09-18]** CP's
  generator had zero resupply-chain concept (confirmed while building
  item 73's redesign, `generator/generate_cp_runs.py` - pure periodic
  full-collection snapshots, no resupply simulation at all - see
  `plans/conceptual-design.md` Thread A). Picked up once the loop this
  was sequenced after actually wrapped. See `plans/qa-pipeline.md` item
  81 for the full build (CP-specific delay curve, an extra earlier red
  delivery, `generator/resupply.py` genericized to a multi-table
  payload, a real churn bug found and fixed the same day) - real CP
  resupply chains now visible in the live dashboard's supply-history UI.
- **CI monitoring shouldn't block the loop**: amended in CLAUDE.md's own
  standing convention (the "check real CI" bullet) rather than logged
  here - a process fix, not a project idea.

9. **[done, 2026-09-18]** **[Dashboard UI]** Human-friendlier URLs.

**Built, 2026-09-18 evening.** Keith's own words: "improve the human
friendliness of the URLs, so we don't have to rely on hash URLs so
much." Scoped via two real `AskUserQuestion` rounds before building
(collection segment explicit vs. re-derived; column/check as path
segments vs. query params; compareIdx kept vs. dropped; panel/theme
scope in vs. out; panel history-entry behavior; theme URL-forcing
question) - real forks, not guessed.

Stayed hash-based (confirmed viable on GitHub Pages - the hash fragment
never reaches the server either way, so no deploy-side change needed
either way), but replaced the opaque `#` + `encodeURIComponent(JSON.
stringify(state))` blob with a real, readable path:
`#/agency/<id>/collection/<id>/dataset/<id>[/column/<name>[/check/
<key>]]` - agency+collection+dataset all kept explicit (not re-derived
from a shorter path) so a link never needs a lookup to resolve, and
column/check drill-down became further path segments rather than query
params, per Keith's own choices.

Two other real forks landed alongside the path itself: the check-panel's
run-comparison index (`STATE.compareIdx`) moved out of the old JSON
blob into a real `?cmp=` query param (kept, not dropped - Keith's call),
and the 4 header side panels (Recent activity/Release notes/
Requirements/Past snapshots), previously independent DOM-only open/
close pairs entirely outside STATE/URL, are now unified under
`STATE.panel`/`?panel=` with a real history entry per open (Back closes
it, same as the column/check drawers already did) - both explicitly
brought into scope by Keith's own answer, not assumed. Dark mode also
now mirrors into `?theme=` for display/bookmark purposes, but
deliberately never overrides localStorage on load (Keith's own choice -
a shared link never forces the recipient's theme).

Implementation: `dashboard/qa-reporting-dashboard.template.html`'s
`stateToPath()`/`pathToState()` (per-segment `encodeURIComponent`/
`decodeURIComponent`, verified against real check names containing
spaces/colons/parens via a real browser walkthrough), `openPanel()`/
`closePanel()` (replacing the 4 independent pairs), `setThemeInUrl()`.
Test coverage: `tests-js/navigation.test.js` (path round-trip including
column+check, panel push/close-one-at-a-time, navigate() clearing an
open panel), `tests/test_dashboard_e2e.py` (`_goto()`'s own Python
mirror of `stateToPath()`, a real back-button-closes-a-panel assertion,
a real theme-never-forced-by-URL assertion) - npm test (71 passed),
`uv run pytest tests/test_dashboard_e2e.py` (11 passed, real Chromium),
`uv run ruff check .` all clean, plus a manual real-browser walkthrough
confirming zero console errors end to end.

10. **[done, 2026-09-18]** **[Dashboard UI]** Expose the planning markdown files in the dashboard (MVP).

Keith's own words: he'd like the `plans/*.md` files themselves
browsable inside the dashboard, not just on GitHub/locally. His own
framing already anticipates this isn't a simple "embed the raw
markdown" job: "that'll probably involve a bit more work to like break
them up and give them statuses and yeah, a bit more rich information so
I can kind of like look at them." Real, current shape of the source
material, worth having in mind before scoping: these files are long,
prose-heavy, chronological narrative logs of numbered items (`wider.md`
action N, `qa-pipeline.md` item N, etc.), each hand-tagged inline with a
free-text status marker (`[done]`/`[todo]`/`[parked]`/`[investigate]`/
`[fixed, <date>]`/`[decided + built, <date>]` and more - never a closed,
consistent enum) - not a structured, queryable data model today. A real
MVP would likely need either (a) a lightweight parser that extracts
each numbered item plus its bracketed status tag as structured data
(similar in spirit to `dashboard/changelog_md.py`'s narrow line-based
`CHANGELOG.md` parser), which only works if those bracketed tags get
made consistent enough to parse reliably (they're currently free text,
written for a human reader in the moment, not a fixed vocabulary), or
(b) a real restructuring of how these files are authored going forward
(a stricter, more consistent status vocabulary, maybe even one
item/decision per file or a lightweight front-matter block) - a much
bigger, more consequential change to how this project's own memory gets
written, not just how it gets displayed. Worth scoping which of those
two directions (parse-what-exists vs. change-how-it's-written) before
building anything, since they have very different costs and very
different effects on every future session's own workflow, not just the
dashboard's.

Related to, but distinct from, item #7 (a live business-requirements/
MoSCoW page): #7 is about a NEW structured data model for requirements/
acceptance criteria that doesn't exist yet; this item is about surfacing
the EXISTING planning memory (`plans/*.md`) that already drives every
session's own work. They could plausibly share UI/rendering
infrastructure once both exist, but are two separate asks with two
separate scoping conversations - don't conflate them when either comes
up for real.

**Scoped, 2026-09-18 evening, via several real `AskUserQuestion` rounds
(Keith consistently picked the non-recommended, bigger-scope option each
time - full retrofit, not forward-only; a real component taxonomy on top
of status).** Real forks resolved, in order:

1. **Direction**: restructure how these files get authored going
   forward (not just parse today's free text as-is) - a stricter,
   closed status vocabulary. Concretely: `todo` / `investigate` /
   `in-progress` / `parked` / `done` / `superseded`, collapsing today's
   loose variants (`done`/`DONE`/`built`/`complete`/`decided`/`fixed`/
   `resolved` all become `done`, with the specific nuance staying in the
   prose that already follows - not lost, just not a separate status
   keyword).
2. **File scope**: all 5 `plans/*.md` files - but `running-thoughts.md`
   keeps its own simpler shape (no forced status field; it's explicitly
   Keith's raw, not-yet-scoped capture buffer, "not yet scoped" isn't
   really a status), just a looser feed the dashboard shows as-is.
3. **Migration scope**: a FULL retrofit, not forward-only - all ~200+
   existing items across `wider.md`/`qa-pipeline.md`/`publishing-and-
   history.md`/`conceptual-design.md` get rewritten into the new format,
   not just new items from here on. Real cost/risk, explicitly accepted:
   a large, careful rewrite of real project memory, not a small change.
4. **A real category/component field, added mid-scoping (Keith's own
   follow-up, not originally asked)**: every item ALSO gets a component
   tag, and - his own explicit ask - the SAME taxonomy should apply to
   `CHANGELOG.md`'s release notes too, not just this new surface, so
   both history feeds share one consistent "what part of the system did
   this touch" vocabulary. Draft taxonomy, confirmed as-is: **Data
   generation** (`generator/`, `synthetic_data_generator/`) · **QA
   checks & contract** (`qa_tools/bdm`, `qa_tools/cp`, `contract/`) ·
   **Pipeline & publishing** (`pipeline/`, `qa_results/` history shape,
   `.github/workflows/`) · **Dashboard UI** (`dashboard/`) · **GitHub
   workflow & people** (ticketing, acceptance, people/roles, leaderboard,
   deep links - the human-process layer on top of QA results, real
   enough to be its own bucket even though it renders inside
   `dashboard/` too) · **Testing & dev tooling** (`tests/`, `tests-js/`,
   coverage, ruff/uv/playwright setup) · **Docs & process** (`plans/
   *.md`, `CLAUDE.md`, `README.md`, `docs/`).
5. **Format**: stays markdown - explicitly NOT switching to YAML/JSON
   (Keith invited the case to be made either way: "I'm happy to make
   these not markdown files if it's genuinely easier... you would need
   to not complicate other things"). The case made and accepted: the
   real problem motivating "restructure" was disambiguation (today's
   inline `[...]` status tags collide with unrelated code/issue
   references elsewhere in the same prose - confirmed for real via a
   `grep` across all 4 files turning up `[tool.uv]`, `[str,
   pd.DataFrame]`, `[dbt-labs/dbt-core#11312]` alongside genuine status
   tags), and a disciplined tag PLACEMENT convention (below) already
   fixes that completely - a format switch buys no extra reliability on
   top of it, while costing real prose-readability for the audience
   these files actually serve (a human and every future Claude session
   reading top-to-bottom as "the actual persistent memory of the
   project," not a database client) and would introduce a THIRD
   authoring convention in the repo alongside CHANGELOG.md's own working
   narrative-markdown pattern and `requirements.yaml`'s genuinely
   tabular one.
6. **Structural placement - real finding mid-scoping, not assumed**:
   checked the actual heading structure of all 4 files (`grep -nE
   '^#{2,4} '` plus a numbered-item-count check) before committing to a
   placement, rather than assuming one shape fits all. Found a real
   split: `wider.md`/`qa-pipeline.md` (32 + 81 items) already use plain
   numbered markdown list items with a bracket tag as the item's own
   FIRST token (`N. **[status]** Title. Body...`) - no heading per item
   at all; `publishing-and-history.md`/`conceptual-design.md` have ZERO
   such items (confirmed via the same grep, 0 and 0) - they're organized
   as long-form Thread/Phase essays with bold sub-headers instead, no
   per-item status tags anywhere. Forcing the second pair into fake
   discrete items was explicitly rejected (Keith's own call, below) -
   they already carry status at the THREAD/PHASE level in their existing
   prose ("Phases 1-4 are BUILT... Phase 5/6 still open"), so the new
   schema applies at that coarser granularity for those two files only,
   not per-item.

   Resulting placement: for `wider.md`/`qa-pipeline.md`, two bracket
   groups right after each item's own number (before any body prose,
   so never ambiguous with an inline code/issue reference later in the
   same item) - `N. **[status, YYYY-MM-DD]** **[Component]** Title...`.
   For `publishing-and-history.md`/`conceptual-design.md`, a bold
   `**Status:** value (date) · **Category:** Component` line at the top
   of each `## Thread X`/`## Phase N` section, before its own prose
   begins.
7. **Link key**: `(file, item-number)` - e.g. `wider-42`,
   `qa-pipeline-17` - is already a stable, unique key; no new global ID
   scheme needed, no renumbering required.

**In progress, 2026-09-18 night.** Two more real forks resolved since
the scoping above:

8. **Data readiness before building the parser**: proposed a permissive
   parser (handle the new schema where present, fall back to plain-
   prose rendering for anything still untagged) so the UI could ship
   without waiting for the full retrofit. **Rejected outright** - Keith's
   own words: "Um, no, because I want to handle the untagged things by
   tagging. I want everything in the same structure." Full retrofit is a
   hard prerequisite, not an optional nice-to-have alongside a fallback
   path. Real scale, measured before starting: `qa-pipeline.md` - 85
   items, 81 still in the old `**[status]**`-only format (no date, no
   component), 40,730 words total; `publishing-and-history.md` - 4
   Thread sections with zero Thread-level tags, 24,184 words;
   `conceptual-design.md` - 1 Thread section untagged, 1,159 words. Two
   background agents dispatched to do this retrofit in parallel (purely
   additive tag-insertion, no renumbering, so genuinely independent of
   each other and of the earlier wider.md split's file-move risk) -
   qa-pipeline.md's 81 items in one, the 5 Thread/Phase sections across
   the other two files in the other. Verification and a real diff review
   still to happen once both land.
9. **UI shape**: a dedicated tab/view alongside the existing BDM/CP
   dashboard views (not a side panel/drawer off existing nav) - Keith's
   own call, given the real volume here (~113 items + 5 Threads, tens of
   thousands of words) doesn't fit a cramped panel.

**Built, same night.** The 17-item date-normalization gap the parser's
own real output surfaced (7 `wider.md`/4 `dashboard.md`/5 `data-
generation.md`/1 `qa-pipeline.md` item never got a real date - or, for
one item, carried an invalid `decided` status word - during the earlier
retrofit passes, because those files were split before the "always
attach a date" convention had fully solidified) got fixed at the source
first, not worked around in the parser, matching the same "no permissive
fallback" stance fork 8 above already established.

- `dashboard/plans_md.py` - the parser (mirrors `dashboard/
  changelog_md.py`'s narrow line-based style): `_parse_numbered_items()`
  for `wider.md`/`qa-pipeline.md`/`dashboard.md`/`data-generation.md`,
  `_parse_threads()` for `publishing-and-history.md`/`conceptual-
  design.md`'s Thread/Phase tag lines, `_parse_notes()` for running-
  thoughts.md's own untagged `### N. Title` shape. 15 tests
  (`tests/test_plans_md.py`), all passing against both fixtures and the
  real committed files (106 items, 6 threads, 12 notes - matches every
  real file's own item count exactly, confirmed by hand before trusting
  the parser).
- The "Plans" tab itself: a genuine new top-level page
  (`STATE.tier==="plans"`, a real `/plans` URL, not a side panel) with
  search, status/component/file filter chips, and an accordion per
  entry (click to expand the full body, rendered through a small new
  markdown-lite-to-HTML pass - paragraphs, bold, inline code, and real
  bullet lists this time, richer than changelog_md's inline-only
  version since plans/*.md bodies are genuine multi-paragraph prose).
  `dashboard/embed_dashboard_data.py` wires `parse_plans()`'s output
  into a new `const PLANS`.
- 26 new JS tests (`tests-js/plans.test.js`) plus a real fix mid-build:
  the status-filter chip's click handler read `PLANS_FILTER[kind + "s"]`
  - "status" + "s" = "statuss", not the real "statuses" key - caught by
  the tests themselves (not by staring at the code), fixed with an
  explicit `{status:"statuses", component:"components", file:"files"}`
  lookup instead of string concatenation.
- Verified: full local `uv run pytest` (411 passed, only the pre-
  existing, unrelated Playwright browser-binary gap already documented
  elsewhere), `npm test` (97 passed), ruff clean, and a real Playwright
  check of the actual built dashboard's Plans tab (search, chip filters,
  and expand/collapse all behave correctly, zero console errors).

Not yet built - real, deliberately deferred follow-ups, not oversights:
deep-linking to one specific expanded entry (today's URL is just
`/plans`, the same as every other tier's own list view before a
drill-down); the `changelog_md.py`-adjacent CHANGELOG.md component
retrofit was actually done SEPARATELY the same night (see `plans/
dashboard.md` #6) once Keith's own release-notes redesign ask
converged with this taxonomy.

11. **[parked, 2026-09-18]** **[Testing & dev tooling]** Switch pytest-cov from line/statement coverage to branch coverage.

Keith's own follow-up question after the requirements-register work
(2026-09-18): confirmed the current `pytest-cov` setup (`pyproject.toml`
`[tool.coverage.run]`) measures line/statement coverage only - no
`branch = true` set - so a line can read "covered" even when only one
side of an `if`/`else` was ever actually exercised. Switching to real
branch coverage is a small config change, but re-baselining
`fail_under` needs a full `uv run pytest --cov=...` run to measure the
new (likely lower) real number first - the full suite takes ~2 minutes
(302 tests, after item #12's own speedup below), which is exactly why
this got deferred rather than done on the spot: **explicitly parked,
not declined** - Keith's own call (2026-09-18): park this specific
question, along with anything else testing-related that comes up in the
meantime, for a dedicated planning loop on the weekend rather than
picking pieces of it off one at a time mid-session.

**Re-parked 2026-09-20** - Keith's own call, when this came back up
alongside item #12's DRY examples: the weekend the original note named
has now arrived without the testing loop happening, so rather than let
the parking note quietly go stale, park it explicitly again until **a
bit later next week**. Same grouping as before (this plus anything else
testing-related that accumulates in the meantime, taken as one planning
loop rather than picked off piecemeal) - only the date moves.

12. **[done, 2026-09-18]** **[Testing & dev tooling]** Local pytest/Playwright runtime - real profiling done, more possible.

Keith's own follow-up question (2026-09-18): "it's taking a while to
run pytest and Playwright locally, is there anything we can do to speed
that up." Real `pytest --durations=25` profile found `tests/
test_generate_runs.py` alone cost ~52s (32% of the then-163s suite) -
all 6 of its tests independently called the real generator fresh for
identical, deterministic output. Fixed (2026-09-18): a single
`scope="module"` fixture generates once, all 6 tests read it - real
~43s saved, full suite now 163s -> a measured 120s, zero coverage lost.

**`pytest-xdist` built and verified, 2026-09-18 night** - Keith's own
explicit call to pick this back up despite the "weekend loop" grouping
above (item #11 stays parked). Investigated the real open question
first, not assumed: does a real dbt subprocess call collide with
another one on dbt's shared `dbt_project/target/` default when run in
PARALLEL workers - confirmed genuinely real, not hypothetical, by
reading `qa_tools/bdm/run_dbt_bdm.py`'s own `evaluate_dbt_bdm()`:
`target_path = os.path.join(DBT_PROJECT_DIR, "target", run_id)` is a
fixed, repo-relative path (NOT inside any per-worker tmp dir the way
`DUCKDB_RUNS_DIR`/`RAW_DIR` already are for Soda/datacontract-cli/
Evidently's own tests), and `tests/test_run_dbt_bdm.py`/
`test_run_dbt_cp.py` each have 2 tests that deliberately share the same
literal `run_id` (matching `conftest.py`'s own fixture-built file
names) - safe today only because pytest runs them sequentially with a
cleanup step between. Reproduced the real failure first (two tests
landing on different xdist workers, same target dir, genuine
`FileNotFoundError`/`CatalogException` from a real dbt race), confirmed
Soda/datacontract-cli/Evidently's own tests were NOT at risk (their
directories are already monkeypatched to worker-unique
`tmp_path_factory` dirs - the "hasn't been checked" note above is now
checked and confirmed safe for those three).

A first fix attempt (suffixing the test files' own `run_id` constants
by `PYTEST_XDIST_WORKER`) was wrong and caught by re-running the tests,
not assumed correct: it broke the coupling between `conftest.py`'s
fixture-built DuckDB file names (keyed by the UNSUFFIXED literal
`run_id`) and what the test then asked `evaluate_dbt_bdm()`/
`evaluate_dbt_cp()` to look up, producing a real, different failure
(`CatalogException: schema "raw" does not exist"` - the suffixed run_id
pointed at a DuckDB file that was never built). **Real fix**: left
`run_id` alone everywhere (test files reverted to match `conftest.py`
exactly), and instead changed `evaluate_dbt_bdm()`/`evaluate_dbt_cp()`
themselves to build `target_path` from `DUCKDB_RUNS_DIR`/
`CP_DUCKDB_RUNS_DIR` (wherever `db_path` already lives - genuinely
unique per production run, and already monkeypatched to a per-worker
tmp dir in tests, same as the other three tools) instead of the fixed,
repo-relative `DBT_PROJECT_DIR/target/`. A real, small production
improvement in its own right (co-locates a run's dbt scratch output
with its own db file), not just a test-only hack - and it also meant
the two dbt test fixtures' manual `shutil.rmtree` cleanup (there
specifically to avoid `dbt_project/target/` clutter in the real repo)
was no longer needed at all, since the new location is already a tmp
dir pytest cleans up itself.

Verified: sequential run still passes (6/6, unchanged), `-n 4` passes
(6/6) across 3 repeated runs with no flakiness, and the FULL suite
under `-n 4` - `411 passed, 13 errors` (same pre-existing, unrelated
Playwright browser-binary gap documented elsewhere in this file/
CLAUDE.md, not a regression) - **in a real, measured 59s, down from the
~120s serial baseline** (item #12's own earlier fixture-consolidation
number) - close to the theoretical ~2x ceiling on this 4-core sandbox.
`pytest-xdist`/`execnet` added as real dev dependencies
(`pyproject.toml`). Deliberately NOT made the default for a bare
`uv run pytest` (Keith's own established preference, `qa_tools/common/
parallel_orchestrate.py`'s own docstring: parallel workers make stack
traces/print-debugging messier) - `-n auto` is documented as the
recommended flag for a fast FULL local run, plain `uv run pytest`
stays serial for easy single-test debugging. Whether to also enable
`-n auto` in CI's own `test.yml` (lower risk there - no interactive
debugging happening) is a real, deliberately unactioned follow-up, not
decided here.

13. **[todo, 2026-09-20]** **[Docs & process]** Make `plans/*.md` ephemeral and tie everything to requirements; make `CHANGELOG.md` shorter and human-first.

Keith, in passing while deciding whether `requirements.yaml`'s
`evidence` field survives (`plans/tooling.md` #20): *"I feel like I'm
going to start making the plan files ephemeral and have everything tied
to requirements... and also changelog will get a lot more shorter, a lot
more for humans first."*

Not scoped, and deliberately captured rather than acted on. But it is
already load-bearing for a decision in flight, so it is not a
someday-idea: **the main argument against keeping `evidence` was that
its content is already recorded in `CLAUDE.md`, `plans/*.md` and
`CHANGELOG.md`, so the field would be a second copy that drifts. If
those three stop being the durable record, that argument collapses** -
`requirements.yaml` becomes the permanent home and measured facts have
nowhere else to live. See #20 for the version of that decision that
accounts for this.

Worth noting what this direction is consistent with, because it is not a
whim: the third `plans/INDEX.md` proof (`plans/tooling.md` #17) found
that an index over the plans files is a faithful index of *stale* text -
`touches:` pointed at the wrong files for item 25 because that item's
own prose was stale, and the pointers inherited the staleness while
looking authoritative. Keith's own read at the time: requirements "point
to the files involved... that's a better source than the plan files,
which are going to be high level, kind of almost like ephemeral
artifacts." `implemented_by` (#18) is the first real piece of that
shift, not a standalone feature.

**The concrete sequence, Keith's own words later the same
conversation** - this is no longer just a direction, it is an order of
operations: *"we will rewrite changelog from ground up later, and we
will do some work to write requirements for everything, and then get
rid of all of the done items from tooling and other plan files."*

So: requirements first, deletion second, changelog rewrite its own
piece. That ordering matters and is worth not losing - the `done`
write-ups can only go once whatever is worth keeping in them has been
captured as real requirements, which is the opposite of trimming for
size. It also already has teeth: `plans/tooling.md` #19 (splitting the
1,711-line `Build order` section into real index entries) was
superseded rather than parked on exactly this basis - careful work on
text that is scheduled for deletion. The same test applies to the ~53
`CHANGELOG.md` entries currently filed under the wrong date, which
Keith explicitly said to leave alone for the same reason.

**Confirmed as a standing rule, 2026-09-20**, later the same
conversation: *"as we go forward, let's apply this rule of requirements
are the permanent artifact... and then the plan file entries get
deleted as we go."* Now written into `CLAUDE.md`'s own conventions, and
the mechanism that makes it safe exists - `requirements.yaml`'s
`decisions:` field (`plans/tooling.md` #20's sibling work), required on
every `built` requirement and CI-gated, holds the reasoning that used
to only live in a plans write-up.

**Also confirmed the same day: the changelog half is on hold pending a
conversation.** Keith asked for a pause before the next `CHANGELOG.md`
entry so he can give the context behind "human readable" before any
more get written in today's style. That hold is recorded in `CLAUDE.md`
as a bullet that explicitly overrides the same-push changelog rule, and
is to be deleted once the conversation has happened.

Real questions this raises, none answered here: what happens to the ~80
`done` write-ups that exist precisely so a session does not re-derive a
settled decision (`CLAUDE.md`'s own stated reason for the
read-everything rule); whether a requirement can carry that kind of
narrative at all or needs a new field for it; whether the Plans tab and
`plans/INDEX.md` survive the change or are replaced by the Requirements
panel; and what "human-first" means concretely for `CHANGELOG.md`, which
is currently long *because* it doubles as the project's own design
record. Scope with Keith before building any of it.

14. **[todo, 2026-09-20]** **[Docs & process]** A way to tie a set of requirements together into one piece of work - a "sprint" - and record which requirements a change actually delivered.

Keith, 2026-09-20, in the same conversation as #13's ephemeral-plans
shift and dependent on it: *"I'm also thinking we need something that
ties requirements together into a, like a, a sprint we work on
together. I guess they can live in the plan files while we're doing the
work and then can then be captured, I don't know, maybe in the revised
changelog potentially. So kind of have a field there which lists the
requirements that were implemented as part of that change."*

Two distinct halves, worth keeping apart because they have different
lifespans:

- **In flight** - a grouping of requirements being worked on together.
  Lives in a plans file while the work is happening. This is the one
  genuinely new thing; nothing in the register expresses "these five go
  together as one piece of work". `dependencies` expresses ordering
  between requirements, which is related but not the same: 023 blocks
  024, but that is a constraint, not a decision to do them together.
- **After the fact** - a `CHANGELOG.md` entry naming the requirement ids
  it delivered. That half is cheap and mostly mechanical, and it is the
  missing return leg of the traceability loop the register already has
  going forwards: a requirement points at its tests (`linked_tests`),
  its code (`implemented_by`) and its measured result (`evidence`), but
  nothing points from a shipped change back to the requirements it
  satisfied.

Real questions, none answered: whether the in-flight grouping is a
field on each requirement (a `sprint:`/`milestone:` name) or a separate
document listing ids - the first survives the plans files going
ephemeral, the second does not; whether a requirement can belong to more
than one; whether the changelog field is authored by hand or derived
from which requirements changed `status` in that push; and how any of
this interacts with #13's "rewrite CHANGELOG.md from the ground up,
shorter and human-first", since a machine-readable id list is exactly
the kind of thing a human-first document does not want prominent. Scope
with Keith before building - this depends on #13's rewrite landing
first, and its shape should probably be decided as part of it rather
than bolted onto today's changelog.

15. **[done, 2026-09-20]** **[Docs & process]** Rewrite `CHANGELOG.md` from the ground up - human-first, structured, modelled on Mapa's "What's New".

**BUILT 2026-09-20 as `REQ-DOCS-028`**, and this item's own scoping
prose has been deleted in the same change, per `CLAUDE.md`'s rule that
build work removes the plans text its requirements now cover. The
format comparison against Mapa, the reasoning for YAML over JSON, the
declined release names, the emoji scoping and the decision to scrap the
existing entries all live as `decisions:` on that requirement, which is
the permanent record.

Kept here, because it is about this file rather than about the feature:
the standing `CLAUDE.md` hold that told every session to pause before
writing a changelog entry is now **lifted**, and the same-push rule has
resumed in rewritten form. `plans/running-thoughts.md` #13's wider
"plans files become ephemeral" shift is still open - this was one piece
of it, not the whole thing.

16. **[todo, 2026-09-20]** **[Dashboard UI]** Show an accepted-values check's real value distribution in the dashboard.

Keith, 2026-09-20, raised while reviewing the first batch of
`REQ-QAC-024` plain-English drafts. He did not want the allowed values
spelled out as prose inside a check's own description ("I'm not crazy
about the what also having to encode the really allowed values as
text"), and the reason that wording existed at all is that there was
nowhere else for a reader to see them.

The idea: for an accepted-values check, expose a small histogram in the
reporting dashboard showing what the accepted values are and how many
of each arrived. That answers the question the prose was trying to
answer, and answers it better - it shows the real distribution rather
than restating the contract, so a reader can see that a value is
technically allowed but has collapsed to almost nothing.

Not scoped. Two things to settle with Keith before building. The
counts would need to come from committed `qa_results/` history rather
than a live query - `dataset_stats.json` already carries value-count
distributions for exactly this kind of presentation data, so the data
may already be there. And it is unclear whether this belongs in the
check drawer, next to that check's own definition, or in the column
view where a reader is already looking at that column.

17. **[todo, 2026-09-20]** **[QA checks & contract]** QA the schema itself - check the columns we receive are exactly the ones we expect.

Keith, 2026-09-20, raised while reviewing `REQ-QAC-024` drafts.
**His own timeframe: "let's try and do that in the next day or two."**

Where it came from, which is the useful part. A Soda completeness check
on `date_of_birth` carried a trailing clause explaining that a silently
renamed column would show up here as 100% missing rather than as a
schema failure. That was offered as the first `technical_note`, and
Keith's response was that the note is really describing a GAP: the
reason a rename surfaces as a weird completeness reading is that
nothing checks the column set itself. Fix the gap and the note stops
needing to exist. So the clause was dropped rather than preserved, and
this item is what replaces it.

Not scoped - to settle with Keith before building: whether "exactly"
means a new column is a failure as well as a missing one (a supplier
adding a field is common and not obviously an error); whether this is
one check per dataset or one per column; and which tool owns it, since
the ODCS contract already declares the schema and datacontract-cli may
already be able to assert it without a new check being written at all.

18. **[todo, 2026-09-20]** **[Docs & process]** The check-metadata authoring guidance in `plans/publishing-and-history.md` Thread D is scheduled for deletion and ~95 things point at it.

Surfaced while deciding where `REQ-QAC-024`'s plain-English authoring
rules should live (Keith's own question: "whether they're actually
encoded as part of rules anywhere, or whether they're just decisions
attached to a requirement"). That question got answered - the rules now
live in the new `docs/check-authoring-rules.md`. This is the adjacent
problem it uncovered, which is not answered.

Thread D's **"Authoring: no CLI - structured metadata lives directly in
each check's own definition"** section is the only written account of
how check-lifecycle metadata gets authored: the per-tool mechanics
(dbt's `meta:`, Soda's `attributes:`, the contract's
`customProperties:`, Evidently's plain dict), each one verified against
the real installed package rather than assumed, plus the confirmed field
set and the `check_id` format. That section is marked
`**Status:** done (2026-09-16)`.

Under the standing rule confirmed 2026-09-20 (`CLAUDE.md`: requirements
are the permanent artifact, plans prose comes out as its requirements
land), `done` prose is what gets deleted. But **a real grep counts 95
references to `publishing-and-history.md` from outside `plans/`** -
three GitHub Actions workflows, all four active `contract/*.yml` check
files' own header comments, `pipeline/build_dashboard_data.py`,
`generator/generate_runs.py`, `requirements.yaml` itself, and a long
tail of tests. Those are not decorative: a contract file's header says
"see Thread D" as the explanation for why an `attributes:` block is
there at all.

So the open question is narrow and worth settling before the
back-catalogue deletion pass reaches this file, not during it: does the
Thread D authoring content move somewhere durable (the obvious
candidate is `docs/check-authoring-rules.md`, which now exists and
already owns the prose half of the same subject), or does deleting it
mean 95 pointers resolve to nothing? `REQ-QAC-006` is the requirement
that covers check lifecycle, so its `decisions:` is the other
candidate - but the per-tool mechanics are authoring instructions, not
decisions about that requirement, which is exactly the distinction that
sent the plain-English rules to `docs/` rather than to `decisions:`.

Not scoped. Flagged rather than acted on because it is a judgement about
the deletion pass as a whole, not about this one file.

19. **[todo, 2026-09-20]** **[Dashboard UI]** The check drawer's own heading is jargon, and the prose rules forbid exactly what it says.

Found 2026-09-20 while grounding `REQ-QAC-024`'s rule 4 in what the
page actually shows. The drawer title is `check.name`, built by
`pipeline/build_dashboard_data.py`'s `display_name()`, and the real
values look like this:

- `Invalid values — dbt:accepted_values (dbt-core)`
- `Null rate — missing_count[all] (Soda Core)`
- `Row count vs. previous run — evidently:row_count_growth (Evidently AI)`

Only 16 of 257 active checks carry a hand-authored `name` in their own
metadata (`Registered on or after birth`, `Closed-case hygiene`, and
14 others). The other 241 get the generated label above.

The tension is real and slightly funny: `docs/check-authoring-rules.md`
rules 10 and 11 forbid naming a tool, macro or statistical method
anywhere in a check's prose, because a data steward does not know which
tool ran the check and should not need to. The heading sitting directly
above that prose names the tool AND the macro. So the one line on the
page that is guaranteed to be read is the one line held to no standard
at all.

Not scoped, and deliberately not fixed alongside the authoring pass -
it is a different piece of work (a rendering change, not prose) and it
interacts with real decisions already made. Things to settle with
Keith first: whether the tool name belongs in the heading at all given
this repo's whole purpose is a four-tool shootout, where a reader
otherwise learns which tool found something; whether the answer is to
hand-author a `name` for all 257 rather than change `display_name()`;
and whether the heading should instead derive from the newly-authored
`description`, which would make the authoring pass the input to it.

20. **[todo, 2026-09-20]** **[Dashboard UI]** 13 active checks never reach the dashboard at all, and they are all table-level.

Found 2026-09-20 by verifying that `REQ-QAC-024`'s first authored batch
actually rendered, rather than assuming the builders carried it. Five
of the twelve checks written in that batch do not appear on the page.

Measured against the real built JSON: **244 of 257 active checks reach
the page, 13 do not.** Every one of the 13 is table-level rather than
column-level - 7 `rowCount_datacontract`, 5 `row_count_soda`, 1
`freshness_datacontract`.

This is pre-existing, not caused by the authoring work. Birth
Registrations' own `rowCount_datacontract` has carried a hand-written
description since long before today and has never once been displayed.
The cause is structural: `pipeline/build_dashboard_data.py` and its CP
sibling assemble `checks_out` inside a per-COLUMN loop, and a
table-level check has no column to be assembled under. The one
exception proves it - `row_count_growth_evidently` does render, because
it is attached to `registration_number` rather than to the table.

Why it matters beyond tidiness: the dashboard's whole drill-down model
is Agency -> Collection -> Dataset -> Column, so "is this supply the
right size" - arguably the first question a steward asks about an
arriving supply - has nowhere to live in it. That is the same
shape-of-data-asset question `plans/wider.md` #9 raises, just hit from
a different direction.

Not scoped. Real forks to settle with Keith: whether table-level checks
get a dataset-level section of their own above the column list, or get
attached to a synthetic "whole table" pseudo-column that reuses the
existing drawer; whether the 13 should be authored in the
`REQ-QAC-024` pass at all while nothing displays them (they were, for
the five in batch 1 - the prose is correct and simply invisible); and
whether the `failure_indicates` CI gate should exempt them until they
render, which would be the wrong way round if the fix is coming anyway.
