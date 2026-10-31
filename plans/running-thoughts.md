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

**Former priority, cleared by Keith 2026-10-04 - work through today/tomorrow (2026-09-19, Keith's own
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
section): the row-count-growth Evidently check needs to find "the
previous run," which does not exist per-arrival - originally solved by
having `run_single()` write a small synthetic manifest, since
SUPERSEDED by `REQ-GEN-043`, which has the check resolve the preceding
run from the deliveries recognised on disk instead and removed the
`previous_run_id`/`previous_csv` parameters nobody ever passed (an
arrival landing outside the delivery tree still skips the check, which
is the same real follow-up in a different place); and `dataset_stats`
computation needs the
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
  place a data engineer already works.
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

53. **[todo, 2026-09-27]** **[Pipeline & publishing]** Something in the AWS build has to poll GitHub for QA-ticket comments, because GitHub Actions no longer builds the dashboard.

    Keith's own observation, 2026-09-27, while REQ-PIPE-092 was being
    drafted: "now that GitHub Pages isn't doing any building of the
    dashboard, we'll need a lambda in the AWS infra to poll GitHub
    looking for comments - flag that as part of running thoughts for
    the AWS build."

    **The dependency being broken, stated plainly.** An accept/reject
    decision is a real `/accept` or `/reject` comment on a dataset's own
    QA ticket (REQ-QAC-017, built). `acceptance_sync.py` splits into a
    real `gh` boundary - `fetch_all_ticket_comments()` - and pure
    matching functions over already-fetched data. The `gh` call is made
    by `deploy-pages.yml`, because that workflow already had a GitHub
    token and was already building the dashboard, so fetching comments
    there cost nothing extra.

    REQ-PIPE-092 moves the build inside the environment and stops
    GitHub Actions building anything. The environment has a database and
    no GitHub token; the workflow has a token and no database. So the
    one place that used to have both has stopped existing, and nothing
    currently fetches those comments at all.

    **Not urgent for the PoC, and worth saying why so it does not get
    scoped as a crisis.** `embed_dashboard_data.py` already degrades:
    with no `reports/qa_comments.json` it embeds an empty
    `AMBER_DECISIONS` and the badges simply do not render. A local
    build has always behaved that way. What breaks is the PUBLISHED
    dashboard losing its decision badges, which matters as soon as
    anybody relies on them.

    **Three shapes, none of them decided here.** A Lambda on a schedule
    that polls and writes into the metadata schema, which is Keith's own
    suggestion and the one that fits the AWS MVP. A GitHub webhook
    into something in the environment, which needs an inbound endpoint
    the environment may not want. Or the environment polls GitHub
    itself during a publish, which needs a token where we have just
    finished removing credentials from one side and would be adding one
    to the other.

    **It bears on the unification question below** (see the decision-log
    entry filed alongside this one): if an accept/reject is an entry in
    the one decision log, then whatever polls GitHub is a WRITER to that
    log rather than a producer of a side file the dashboard build reads.
    That changes which of the three shapes is natural - a Lambda writing
    to the database is very different from a Lambda writing a JSON file
    into a build.


54. **[done, 2026-09-27]** **[Pipeline & publishing]** An amber accept/reject and a filing decision are both decisions, and there are two logs.

    **OUTCOME, so nobody reads the analysis below as live: an amber
    `/accept` is NOT a decision and is NOT logged.** Keith withdrew his
    own comment the same evening, once told that REQ-PIPE-075 criterion
    1 already auto-promotes a green OR AMBER supply - so by the time
    anybody comments on a ticket the supply is already the period's
    answer and an accept moves nothing. An amber `/reject` IS a filing
    decision and is logged, unchanged. The reasoning is carried by
    REQ-PIPE-091's own `decisions:`; what follows is the working that
    got there, kept until 091 is built.

    Keith, 2026-09-27, when asked whether REQ-PIPE-091 really blocks
    REQ-PIPE-092: "both of those things feel like decisions to me -
    they just happen in different places, but should be show in the one
    log."

    **He is right, and this entry exists partly because I argued the
    other way twice.** I checked whether the dashboard renders filing
    decisions, found it does not - the only decision rendering is
    `AMBER_DECISIONS`, from GitHub tickets - and reported the
    dependency as resting on a false premise. The premise was not
    false. It was that these are the same KIND of thing, which is a
    product statement rather than a fact about today's code, and
    checking today's code could not have tested it.

    **WHAT EXISTS, so the overlap is visible rather than asserted.**

    - **REQ-QAC-017, BUILT.** Amber requires an explicit human
      decision per run, accept or reject (Keith's own call,
      2026-09-19, option 3 of three). A real `/accept` or `/reject`
      comment on the dataset's QA ticket; `acceptance_sync.py` matches
      it to a run by arrival window so nobody types a run id; the
      dashboard renders a badge. Deliberately read-only - no backend,
      so no button.
    - **REQ-PIPE-074, signed, not started.** Every FILING decision -
      promote, reject, demote, re-file - as one append-only log that
      refuses an anonymous entry.
    - **REQ-GHUB-082, unsigned.** Already "from GitHub or from the
      terminal, and both write the same entry": one implementation,
      each route an adapter (C11), an identical entry whichever route
      raised it (C3), the actor taken from the authenticated GitHub
      author (C4). **The two-places-one-log shape is already the
      design** - it just does not include the amber accept/reject,
      whose operation list (C1) is promote, reject, demote, re-file,
      substitute, inherit and un-inherit.

    **THE REAL QUESTION THIS OPENS, and it is not a merge of two
    mechanisms.** Is "accept this amber supply" the SAME ACT as
    "promote this supply", or a different act that happens to be about
    the same supply?

    Two things say they may be the same. REQ-PIPE-075 C1 promotes a
    green OR AMBER supply into an empty slot automatically, so amber is
    already a promotion case. And a human accepting an amber supply is,
    in plain terms, deciding it may stand as the period's answer.

    One thing says they are not. REQ-QAC-017 has an ACCEPTED run's pill
    stay amber, and a REJECTED run's pill stay amber too (Keith's own
    call, 2026-09-19, "the smaller, safer option"). Neither repaints
    anything. That reads as an ACKNOWLEDGEMENT of a quality verdict
    rather than a filing action - "somebody has looked at this" - which
    is a different fact from "this is what Q3 resolves to".

    **~~RESOLVED, 2026-09-27, Keith: "'accept this amber supply' is a
    decision worth logging too."~~ WITHDRAWN by him the same evening -
    see the outcome above.** It was going to go in the one log. The
    mapping worked out below is what showed why it should not: the two
    operations are not symmetric, and once that was on the page the
    accept half had nothing left to record.

    **A HUMAN'S ACCEPT OR REJECT ALWAYS COMES AFTER AUTOMATIC
    PROMOTION.** REQ-PIPE-075 C1 promotes a green OR AMBER supply into
    an unfilled slot when QA completes, before anybody has looked. So
    by the time a person comments `/accept` or `/reject`, the supply is
    already the period's answer.

    Which makes them different acts:

    - **`/reject` IS an existing filing decision.** REQ-PIPE-076 C1 and
      C4: move the supply to the rejected schema, leave its slot
      unfilled, record the decision. No new entry type needed.
    - **`/accept` IS NOT.** Nothing needs to move - the supply is
      already promoted. What the entry records is that a person looked
      at an amber verdict and is content for it to stand. That is an
      ACKNOWLEDGEMENT, and it is a new entry type.

    **AND IT EXPLAINS THE PILL BEHAVIOUR that looked like an
    inconsistency.** REQ-QAC-017 keeps the pill amber after an accept
    AND after a reject, while REQ-PIPE-076 C4 says a reject empties the
    slot. Those do not conflict, and the reason is worth stating so
    nobody "fixes" it: the pill is the QUALITY VERDICT, and a person
    rejecting a supply does not make its data better or worse. The
    filing state is a separate fact with a separate display. Two
    different questions, two different answers, one supply.

    **ONE CONSEQUENCE HE MAY NOT HAVE INTENDED, worth putting to him
    before it is built.** REQ-PIPE-076 C7: "WHERE any decision has been
    recorded against a supply by a person, THE SYSTEM SHALL NOT promote
    that supply automatically thereafter", and C12 keeps that bar for
    the life of the supply. If an accept is a recorded person-decision
    - and it is - then accepting an amber supply permanently bars it
    from automatic promotion. For a supply already promoted that only
    bites on a re-run or a resupply, so it may be exactly right: a
    human has spoken about this supply and automation should defer. But
    it follows from C7 rather than from anything anybody decided about
    accept, which is the kind of thing worth noticing before rather
    than after.

    **This evaporated with the withdrawal.** No accept entry means no
    recorded person-decision, so C7's permanent bar never attaches and
    nobody has to live with it. Kept because the bar itself is real and
    the next thing to propose a benign-looking entry type will meet it
    again.

    **WHAT IT CHANGES IMMEDIATELY, whichever way it goes.** If an
    accept/reject becomes an entry in the one log, then REQ-PIPE-091 IS
    a real dependency of REQ-PIPE-092 - because the dashboard renders
    accept/reject badges today, and their source would be that log. So
    the dependency Keith kept stands, for this reason rather than the
    one he first gave, and REQ-PIPE-092's own open question should be
    closed by THIS entry rather than by dropping it.

    It also changes item 53 above: whatever polls GitHub for comments
    becomes a WRITER to the decision log rather than a producer of a
    side file the dashboard build reads.

    **And a separate, unconditional finding.** REQ-PIPE-074 C11 says
    the log "SHALL commit the log to the repository, and SHALL NOT hold
    it only in the warehouse". That is false twice over now -
    REQ-PIPE-091 C1 makes the metadata schema the single system of
    record, and the repository holds configuration rather than state.
    074 is SIGNED, so that criterion needs the same treatment
    REQ-PIPE-061's marker clauses got: restate what it protected - the
    log is durable, readable, and not lost with one database - and drop
    the mechanism. True whether or not the two decision kinds converge.


56. **[done, 2026-09-28]** **[Pipeline & publishing]** **[Docs & process]** How much state is left on disk - measured, because Keith asked.

    His own question, 2026-09-27: "get back to me on how much state is
    actually left on disk now, or whether we've actually cleared out all
    the state and put it in the database." Measured in this container on
    2026-09-28, after REQ-PIPE-089 (QA results), REQ-PIPE-104 (filings)
    and REQ-PIPE-091 (the decision log) had all landed.

    **THE SHORT ANSWER: the repository holds no state at all any more,
    and `data/` holds 44MB that is not state either.** Nothing that
    accumulates is committed, with one deliberate exception.

    **WHAT THE REPOSITORY TRACKS** - 442 files, and every one of them is
    configuration, code, tests or prose:

    | path | files | what |
    |---|---|---|
    | `tests/` + `tests-js/` | 166 | tests |
    | `qa_tools/` `cli/` `pipeline/` `generator/` `dashboard/` etc | ~170 | code |
    | `contract/` | 11 | the contracts, calendars, hierarchy, environments |
    | `plans/` `docs/` | 27 | prose |
    | `dashboard/snapshots/*.html.gz` | 7 (16MB) | **the deliberate exception** |

    The snapshots stay, and the reason is unchanged: a snapshot's whole
    purpose is to be openable years later with nothing but a browser,
    which a row in a database it cannot reach is not.

    **WHAT IS ON DISK AND GITIGNORED** - 44MB under `data/`, none of it
    state in the sense Keith's rule is about:

    - **`data/deliveries/` (19MB)** - the supplier's own files. This is
      not our state, it is the INPUT. In production it is an object
      store; here it stands in for one.
    - **`data/receipts/` (332KB)** - our record of when each delivery
      arrived, written outside the delivery so a supplier has no path to
      our clock. **This one is arguably state and is staying on disk on
      purpose**: it is written by the receiving side at the moment of
      receipt, before anything has a database connection or knows which
      collection the delivery is for. It is also now duplicated INTO
      `qa.delivery` by `delivery_log.record()`, so the durable copy is
      already in the database and the file is the receiving side's own
      note. Worth a decision at some point rather than left implicit.
    - **`data/dbt_scratch/` (25MB)** - dbt's own working directory,
      per run. Not ours and not durable; `_discard_this_runs_schemas()`
      removes each run's after its results are recorded (2026-09-27).
    - **`data/generator_bookkeeping.json` (24KB)** - which scenario each
      generated delivery came from. The generator's own note to itself,
      and nothing in the pipeline may read it (REQ-GEN-043 criterion 7).

    Plus the ordinary build outputs, all gitignored and all regenerated:
    `reports/` 9.2MB, `_site/` 20MB, the built dashboard 4.8MB, and
    `.venv`/`node_modules` at 1.4GB and 94MB.

    **WHAT THE DATABASE HOLDS** - 49MB: `staging` 163 tables / 20MB, and
    the `qa` metadata schema 11 tables / 9.9MB (results, tool output,
    runs, tables_read, dataset_stats, deliveries, delivery files,
    filings, decisions, and the visible views).

    **ONE REAL FINDING, and it is small**: two orphaned per-run schemas,
    `qa_ref_birth_registrat_20260927t045754z` and
    `qa_ref_birth_registrations_2026_09_01_20260927t041512z`. Both are
    EMPTY - zero tables - so they cost nothing today, and both are
    exactly what `drop_orphan_run_schemas()`'s own docstring warns about:
    "a per-run thing that nothing deletes is just a leak with a tidier
    name - at ~30 datasets on a quarterly cadence that would be thousands
    of abandoned schemas in a year." They are reference-run schemas, and
    something on that path is not calling the tidy-up. Not chased
    tonight; logged rather than fixed in passing, because the fix is a
    question about which path owns the cleanup rather than a one-liner.


55. **[investigate, 2026-09-27]** **[Pipeline & publishing]** **[Docs & process]** How is CONFIGURATION organised once there are two data assets, sample datasets, project extractions and ad hoc QA?

    Keith raised this himself at the end of 2026-09-27, in his own
    words, and explicitly said it needs a conversation rather than a
    decision: "how we manage this repository and the data assets and
    data sets and checks configuration when there's two separate data
    assets, the quarterly one and the daily one, plus this notion of
    sample data we can QA, plus the project extractions we can QA, plus
    other ad hoc things we QA - whether we manage the configuration all
    in the one repository, which I guess is doable, whether we somehow
    inject the configuration."

    **WHY THIS IS NOW THE OPEN QUESTION ABOUT THE REPOSITORY, rather
    than one question among several.** His own standing rule of the same
    day - the repository holds CONFIGURATION, NOT STATE - answers what
    the repository is *for*. REQ-PIPE-089 is taking the last big body of
    committed state out of it. What that rule deliberately does not
    answer is how the remaining configuration is ORGANISED once there is
    more than one of everything, and that is all this is.

    **THE FIVE SHAPES IT HAS TO HOLD**, which is what makes it harder
    than "one repo or many":

    1. **Two data assets**, quarterly and daily, each managed by a
       different team in a strictly separated cloud environment, each
       with its own deployment, database and dashboard. CLAUDE.md
       already records the settled part: the asset is a DEPLOYMENT'S
       IDENTITY, not a row in the data. Roughly 30 datasets on the
       quarterly asset alone.
    2. **Sample datasets** (REQ-PIPE-106, signed 2026-09-27) - no
       calendar, real checks, and structurally ordinary in every other
       way: same hierarchy, several at once, cross-table checks among
       them.
    3. **Project extractions** (delivery sprint 29) - supplies and no
       cadence, ever, one dashboard per extraction.
    4. **Ad hoc QA**, which he named here and which nothing has scoped
       at all yet.
    5. **The check definitions themselves**, which are the largest
       hand-authored body in the tree and the thing most likely to be
       shared between assets rather than duplicated per asset.

    **WHAT THE TREE LOOKS LIKE TODAY, so the starting point is a fact
    rather than an impression.** `contract/data-asset.yaml` is ONE file
    describing ONE asset: a single `data_asset_id`, one `timezone`, the
    named `calendars`, and one `hierarchy` of agencies -> collections ->
    datasets. Beside it sit per-collection contract and Soda files, plus
    `environments.yaml` and `people.yaml`. So the current answer is
    "one repository, one asset, singular by construction" - the file
    would have to change shape or multiply either way, and that is the
    concrete thing any option has to say something about.

    **TWO PRECEDENTS ALREADY IN THE TREE, worth knowing before the
    conversation rather than discovering during it.**

    - **Configuration does not have to be hand-authored.** REQ-PIPE-106
      settled that a project extraction's dataset configuration is
      GENERATED from the recipe file arriving beside the package, and
      criterion 2 already permits it - it requires that a missing
      calendar be DECLARED, not that a human type it. So "inject the
      configuration" is not a new idea needing a new mechanism; one
      corner of the system already works that way.
    - **REQ-PIPE-107** (drafted 2026-09-27, unsigned) is the guard that
      refuses to act against a database belonging to another asset or
      environment. It is directly load-bearing here: the more
      configuration is shared between assets, the more the guard is what
      stops a shared checkout writing to the wrong one. Worth deciding
      that requirement's own open question - whether "environment" is a
      chosen name or something derived - with this conversation rather
      than before it.

    **THE ADJACENT QUESTION THIS IS NOT.**
    `plans/publishing-and-history.md` item 6 is about CODE architecture -
    how many near-identical modules per dataset. This is about
    CONFIGURATION architecture. They will inform each other and they are
    not the same question, and conflating them is how one of them gets
    answered by accident.

    **Not scoped, not started, and deliberately not decided here.** The
    options he named are worth writing down as the starting set rather
    than treated as exhaustive: everything in one repository; a
    repository per asset; one repository of shared checks with per-asset
    configuration injected at deploy time. Nobody has argued any of them
    yet.

    **DECIDED FOR THE PoC (Keith, 2026-10-31): (a), one repository with a
    configuration folder per asset**, scoped together with the period control
    (see #131). **(b) a repository per asset and (c) configuration injected at
    deploy time are a FUTURE DECISION POINT**, to be taken "once this needs to
    migrate out of PoC stage". Sample datasets, project extractions and ad hoc
    QA (shapes 2 to 4 above) are not part of this decision.


88. **[todo, 2026-10-12]** **[Testing]** **Run tests more selectively,
    so failures turn up earlier - and the full gate is too long.** Keith,
    2026-10-12, after REQ-GEN-195 went through two full `mothman check`
    runs: "You need to get better at running the test suite more
    selectively so we don't have to go through the full [gate] all the
    time. And so we can pick up tests earlier. I'm also concerned that
    full gate takes 10 minutes now, it's a long time to run tests for."
    Two separate asks. (1) PRACTICE: run the affected modules as each edit
    lands, and anything that reads the generated corpus (the asset-time
    golden, the scenario tests, the e2e module's data-dependent classes)
    straight after a bootstrap - in REQ-GEN-195's case the golden and two
    e2e failures were all predictable from "the corpus changed" and turned
    up only in the full gate. CLAUDE.md's commit-cadence rule C already
    says this; it was not followed.

    **Scoped 2026-10-23 as REQ-TEST-281 (the e2e module across workers,
    per-worker build) and REQ-TEST-282 (one page per class), with the
    2026-10-21/22 gate profile as their evidence.**

    Priority: this week, after the line of work already queued (Keith,
    2026-10-13: "we'll make a note to come back to that this week. Maybe
    after this next line of things we've got lined up").

89. **[parked, 2026-10-13]** **[Pipeline & publishing]** **SIGNIFICANT: a
    schema change has no production path - "wipe and rebuild" only works on
    a synthetic asset.** Priority: address in the next few days (Keith,
    2026-10-14 night, setting up overnight #5: "let's address number 89 and
    number 95 if we can in the next few days, given that they block some other
    requirements" - it held REQ-QAC-176, so REQ-PIPE-177, REQ-PIPE-178 and
    REQ-DASH-221, until Keith lifted that hold on 2026-10-24 by answering
    REQ-QAC-176's question 2 with C, a plain schema bump using the existing
    refusal; it blocks none of the four now). Earlier priority: deal with it this week (Keith,
    2026-10-13: "I'm quite concerned about that database schema thing.
    There's no way that approach of rewriting is viable. So that is a
    significant issue ... and we should deal with that this week.") Found answering Keith's question on REQ-PIPE-193 ("is that
    just for now, or ... in production, this would cause a rewipe and
    rebuild?"). The standing rule (Keith, 2026-10-05, recorded on
    REQ-PIPE-144) is that any SCHEMA_VERSION bump refuses an older database
    and the remedy is `mothman env reset-synthetic` then `bootstrap` - and
    reset-synthetic deliberately REFUSES an asset that does not declare
    `synthetic: true`. So against a real asset a schema change leaves the
    database refused with no way forward. Fine for the PoC; before any real
    deployment, schema changes need real migrations (or an equivalent
    route). Nothing records that today. Not scoped. Worth knowing when it
    is: the rule reaches beyond the schema - it is also why a corrected
    synthetic history is regenerated rather than repaired, so scoping should
    say which of those a real asset needs instead, and every requirement
    whose decisions say "regenerate, never migrate" (REQ-PIPE-144 and
    others) is touched by the answer.
    **SCOPING, ROUND 1 (Keith, 2026-10-14 morning, via AskUserQuestion).**
    Facts first, from the code: qa_store.SCHEMA_VERSION is 40 after 38
    bumps, about three a day lately; `_refuse_another_version` refuses ANY
    older database and names reset-synthetic as the only remedy; 21
    requirements mention the rule (20 built), but REQ-PIPE-144's "ALWAYS
    WIPE AND REBUILD ON A SCHEMA CHANGE" (Keith, 2026-10-05, over my
    recommendation to allow additive changes) is the one that decides it.
    What a real asset cannot regenerate: the append-only decision log,
    verdicts (recorded facts, REQ-PIPE-168), write-once filings and
    receipts, and the supply rows themselves - replaying deliveries would
    re-judge history today. His answers:
    - MECHANISM: versioned, forward-only migrations - each version bump
      ships a migration applied in order in a transaction. Rejected:
      replaying deliveries (re-judges verdicts); additive-only in place
      (boxes in reshapes).
    - WHEN: FROM NOW - every bump from version 41 ships a migration and its
      test. Rejected: waiting for a schema freeze; recording only. This
      reverses REQ-PIPE-144's 2026-10-05 decision, so that requirement is
      amended by whatever gets signed.
    - PROOF: both - each migration tested in CI against a database built
      at the previous version, AND dry-run on a copy of the real database
      before production.
    - SCOPE: the QA metadata schema only. A contract changing a dataset's
      own columns is a separate item (#94).
    **ROUND 2, same morning.** BASELINE: version 40 is migration zero; a
    database older than 40 is still refused with the rebuild message.
    APPLYING: an explicit `mothman db migrate` that shows what it will apply;
    everything else refuses an older database and names that command.
    Rejected: automatic on connect. RESET: reset-synthetic is kept for
    regenerating a synthetic history, but is no longer the remedy for a
    schema gap. TOOL: OPEN, between Alembic and Django, TIED (Keith,
    2026-10-14, correcting my earlier record that he leaned towards our own
    runner - he did not). OWN RUNNER REJECTED: "we just end up reinventing
    models and migrations that Alembic and Django already do really well".
    He is happy to pay for rewriting the hand-written schema SQL as real
    models. More thought and analysis on Alembic vs Django later. Researched on his ask: Alembic with alembic_utils (0.8.8)
    DOES autogenerate views, functions, triggers and policies (my first
    comparison wrongly said it could not); Django manages triggers through
    django-pgtrigger and views through django-pgviews-redux, but only by
    modelling every table. Before choosing, he wants to see what
    maintaining it looks like in a team and how often it happens in
    production:
    docs/drafts/schema-migrations/what-maintaining-it-looks-like.md.
    **WHAT THE 38 REAL BUMPS SAY (Keith's question, same morning: could each
    have been upgraded in place, and would it have needed QA re-run?)** -
    docs/drafts/schema-migrations/schema-bumps-analysis.md. All 38 could
    have been migrated in place and NONE needed the check tools re-run; the
    real risk is re-judging history, not re-running tools. 19 additive, 5
    SQL backfills from other qa rows, 6 hand-written reshapes (four also
    needing a one-off import of committed files), 1 recompute from outside
    qa (v4: the run's original UTC offset was already lost), 1 tool-only
    value (v29's file checks - fill with NULL, never today's verdict), 1
    constraint tightening, and 5 SEMANTIC changes (v11, v13, v19, v26, v27)
    that are honest only with a marker or cut-over. Worst: v26, where old
    re-file rows would silently read as leaving their target slot empty;
    v19's DEFAULT 'automated' would have claimed every hand-filing was
    automated (spot-checked in e01c1fd). The tool choice changes none of
    it. Five design rules proposed there (NULL means "not recorded at the
    time"; never recompute verdict-like values for history; record raw
    evidence; version the meaning of append-only facts; expand-verify-
    contract reshapes) - for Keith.
    **RULE 3 AUDIT (Keith, same morning: "do we have gaps around rule three,
    recording raw evidence when it happens?")** -
    docs/drafts/schema-migrations/raw-evidence-audit.md. Yes: three HIGH,
    six MED, four LOW. HIGH, each checked against the code or database:
    (H1) recorded evidence can be overwritten - a run's results are
    deleted and re-inserted and tool output is upserted under an arrival's
    fixed run key; (H2) no bytes-level identity for a delivered file -
    qa.delivery_file has no checksum, size or header; (H3) no code or tool
    versions - run.tool_versions is empty on all 229 runs and no git SHA is
    recorded anywhere. Also found the OTHER way: the qa schema already
    holds supply-row values (datacontract failed_samples in 23 tool
    outputs, failing sample keys, invalid values in dataset_stats), and the
    publisher role can read all of qa. Two calls for Keith: where delivered
    files live in production and for how long; whether sample values stay
    readable by the publisher. Not scoped.
    **PARKED, same morning (Keith): "This is a bigger change that we need to
    think about ... write this all up ... and we'll make a call later on
    this much wider set of changes."** The whole thread is written up in
    docs/drafts/schema-migrations/README.md. Two answers given before
    parking: supply-row samples move supply-side (out of the publisher's
    reach, qa keeps counts and salted key hashes); delivered files live in a
    versioned bucket per asset, retention scoped later. Wider distributions
    may be accepted as a gap and filled by a targeted regenerate later.

90. **[todo, 2026-10-13]** **[Pipeline & publishing]** **Protect the
    processing loop from a decision made while it is working on the same
    supply.** Keith, 2026-10-13, alongside #71's "QA runs only in the
    processing loop": "what if it picks up a file and it's running on it,
    or it's in its little queue, and someone changes the decision locally?
    I kind of think that shouldn't be able to happen if it's actually
    actively running in the queue." His shape, not settled:
    - WHILE THE LOOP IS ACTIVELY PROCESSING a supply, a person's decision
      about it is refused (or waits) - it must not change underneath a run;
    - WHILE MERELY WAITING, probably allowed - "but then there isn't really
      a queue. It's just a case of picking up the next thing that can be
      processed" - so the loop chooses the next processable thing at the
      moment it picks it up, rather than holding a queue that can go stale.
    Worth carrying into it, checked in the code 2026-10-13: the pass
    already takes a PostgreSQL advisory lock PER ARRIVAL, from before it is
    filed until its gate outcome is recorded (processing_pass.py, REQ-PIPE-151
    criteria 6 and 16) - but nothing in the decision path checks that lock
    today. And a decision already refuses when its consequences changed
    since confirmation (REQ-PIPE-128 criterion 9). So the first question is
    whether a decision should take or test the same arrival lock. Related: #61 (a concurrency pass once the supply model
    settles), #71 (where QA runs). Priority: this week, worked together
    with Keith.

91. **[parked, 2026-10-13]** **[Testing & dev tooling]** **[Data generation]**
    **An agent that walks every test scenario like a user and checks it
    really shows.** Keith, 2026-10-13: "have an agent run through each
    scenario and make sure what's being done actually shows up on the
    dashboard and actually is kind of represented in the database. Maybe
    they kind of like drive it all like a user using the TUI and driving a
    browser to look at the things linked from the scenarios just to make
    sure they all make sense." For each registered scenario (the scenario
    map / plans/supply-model.md register): open the dashboard link the
    Scenarios tab gives, in a real browser; drive the TUI where the
    scenario involves a person's decision; query the database for the
    filing, verdict, decisions and runs the register's "Expect" says should
    be there; and report anything that does not match or does not make
    sense to a reader. Why it is worth having, from today alone: TS-67's
    history looked right by filing and verdict, while its re-checks had
    never run and two of its supplies stayed red (post-build-review #161) -
    exactly what walking the scenario as a reader would have caught. Close
    in spirit to the delivery-*-critic agents, but driven by the scenario
    register rather than by one requirement. Parked; not scoped.

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

21. **[todo, 2026-09-20]** **[QA checks & contract]** Let `technical_note` accumulate the real causes a check has actually turned out to have.

Keith, 2026-09-20, in passing while approving `self-evident` for the
completeness family: *"over time, we might, as humans, update the
technical note field to record the kind of issues that we found
potentially."*

Worth keeping because it is a genuine widening of that field, not a
restatement of it. `technical_note` is currently narrowed to STANDING
facts - cross-references between checks, and why a check behaves as it
does by construction (`docs/check-authoring-rules.md`, rules 8 and 9).
What this describes is different in kind: an accumulating record of
what has actually gone wrong, written after the fact, growing each time
someone investigates a real failure.

Why it is interesting rather than just another field use: it is the
natural counterpart to `self-evident`. That sentinel exists because the
cause of a failure is often genuinely unknown at authoring time, and
rule 5 forbids guessing. But "unknown now" is not "unknowable" - a
data engineer who investigates three red runs on the same check learns
something real, and today there is nowhere for it to go. This would
turn the sentinel from a permanent admission into a starting state.

Not scoped, and it needs care on at least four things. It reopens the
standing/dated boundary that `technical_note` was narrowed to protect -
"we saw this in March" has a date, which is what `changelog` is for.
It is contributor-facing and never published, so a data engineer would
be writing into a field they cannot see on the page, which is either the
point or a fatal flaw depending on who is meant to write it. It overlaps
the ticketing system, which already records what a real failure turned
out to be and has an owner and a state. And it would want a real
authoring rule of its own, since "record the kinds of issues found" is
exactly the loose invitation that produced the prose this whole
requirement is rewriting.

22. **[done, 2026-10-12]** **[QA checks & contract]** `dataset` and `table` are the same thing in every check_id, and only one of them should exist.

Keith's question while reviewing the new `/check/` URL shape: "where is
dataset different to table?" Checked against the real ids rather than
the prose, and the answer is nowhere. Seven datasets, seven tables,
strictly 1:1 - the table segment is the dataset segment with `stg_`
prefixed and hyphens swapped for underscores:

| dataset | table |
|---|---|
| `birth-registrations` | `stg_birth_registrations` |
| `cp-carers` | `stg_cp_carers` |
| `cp-clients` | `stg_cp_clients` |

**His call: they are always going to be the same thing, it should be
called `dataset`, and the data-asset segment does not belong in the URL
either.** Parked rather than done, and revisited alongside the wider
question of how to model a dataset that is the only thing in its
collection.

**Why it is parked rather than a quick edit.** Removing `table` from
`check_id.py`'s `_SEGMENTS` is genuinely one line - the grammar is
built from that list precisely so a change is one edit. The cost is
everywhere else: it renames all 258 check_ids, and that collides head
on with Keith's own standing rule from 2026-09-16, that a `check_id`
once introduced is PERMANENTLY unique and must never be changed or
deleted even once retired. That rule came from his own question at the
time - "if that was real data, we wouldn't want to have to backfill it
in" - and there are 1,480 committed history files, 129MB, carrying
those ids. Doing it now would be breaking the rule precisely because
the data is synthetic and we CAN, which is the lesson the rule exists
to prevent.

**A real documentation drift found alongside it, worth fixing whenever
this is picked up.** `CLAUDE.md` describes Child Protection as "one
collection/dataset, six distinct tables", and gives that as the reason
`dataset` and `table` are separate segments. The ids say otherwise:
each CP table is its own DATASET, and the six are grouped by
COLLECTION - which does not appear in the check_id grammar at all.
So the two identity schemes overlap on agency + dataset + column, and
each carries one thing the other does not: the URL adds collection, the
check_id adds data-asset and table.

That asymmetry is the actual question to settle here, and it is the
same one `plans/wider.md` #9 raises from the other direction - what a
data asset looks like when it is not one table per dataset.

One consequence worth knowing: `validate_tail_uniqueness()` currently
guards a collision that is structurally impossible, and its own
docstring says so ("it cannot happen today only because every dataset
maps to exactly one table, and nothing enforces that"). It is not dead
weight - the `/check/` URL now really does key on the tail, so the
guarantee is load-bearing the moment a dataset ever gains a second
table.
    **DONE 2026-10-12 (open-items audit):** the `table` segment was removed from check_id's `_SEGMENTS` (qa_tools/common/check_id.py says so), under REQ-QAC-039.

23. **[todo, 2026-09-20]** **[Pipeline & publishing]** Adding two more datasets is the trigger for resolving the file-per-dataset shape.

**Scope this together with #29** (Keith, 2026-09-23). #29 is the
concrete version of "adding two more datasets" - a few small ones
across several agencies, at the end of the sprint sequence - so the
trigger this item describes and the act that pulls it are one piece of
work, not two. Cross-referenced from both directions deliberately:
finding one and not the other is how the copy-paste cost gets
multiplied instead of paid.

Keith, 2026-09-20 night, immediately after authorising the
`delivery-scoper` run on `plans/publishing-and-history.md` item 6: once
that item's restructure is done, add another couple of datasets, and
**that** is what triggers looking at the copy-paste problem properly.

Worth being precise about which half of item 6 this sequences, because
the item contains two things. Its FIRST piece of work - the
agency/collection/dataset/table hierarchy and the per-dataset-runs
model - is what `delivery-scoper` is scoping now. Its SECOND, still
genuinely unscoped, is which file-architecture shape is right:
data-driven off each dataset's own config, a per-tool plugin/registry,
or collapsing only the mechanical Phase 1/2 additions. That second
question was deliberately excluded from the scoper's brief and handed to
`delivery-architect`. This note says WHEN it gets answered.

Why the ordering is good rather than just a deferral: you cannot tell
which abstraction is right from two datasets. The shape that looks
obviously correct at two is routinely wrong at four, and item 6 already
carries `plans/qa-pipeline.md` #84's finding that the per-dataset LOGIC
is genuinely different rather than boilerplate - so guessing the
abstraction before there is enough variation to see it is how this gets
built twice. Adding real datasets first makes the copy-paste cost
concrete and shows which parts actually repeat.

Open, and for Keith: WHICH two datasets. The dashboard's own tree
already carries illustrative agencies with no real data behind them
(immunisation, hospital discharge, driver licensing, vehicle
registration, school enrolment, assessment results, business
registrations), so there are candidates, but picking ones that stress
the model differently - a single-table collection, a multi-table one, a
different cadence - would tell us more than picking two that look like
what exists.

**Answered in part, and widened, 2026-09-21** (Keith, while settling the
composition rules for item 6): it is **one new dataset per data asset**,
not two onto one. That choice is doing real work - it forces the
daily asset and the quarterly asset each to hold more than one dataset,
which is the configuration none of the current code has ever seen.

And it carries a second piece of work he named at the same time: **add a
more concrete concept of the DATA ASSET level**. Today the asset is
barely modelled - `contract/data-asset.yaml` holds an id and one global
`as_of_offset_days`, and everything else in the system is keyed on
agency/dataset. Two assets each holding two datasets is the point where
that stops being sufficient.

Specifically flagged as possibly needing rework: **how the dashboard
separates one data asset from another**. Keith's own words - "maybe it's
actually two versions of the dashboard." Deliberately left open rather
than decided here; it is a real fork (one dashboard with an asset
selector, versus a separate published site per asset, versus asset as
another level of the existing tree) and it wants scoping with him, not a
guess. Worth noting the published-site question is not purely cosmetic -
`.github/workflows/deploy-pages.yml` publishes one site today, so "two
versions" is a deploy-shape change, not just a UI one.

Where this came from, since it reads as a non-sequitur otherwise: the
argument that killed it was mine and it was wrong. I had argued a
per-day schema on the daily asset would be overhead, because BDM
delivers one table a day so the schema would group one thing. That
premise dies as soon as a second dataset lands on the daily asset - and
Keith had said two sentences earlier that both assets will eventually
carry both datasets. The schema-per-period pattern therefore holds for
both assets (settled, see item 6), and the reason the argument failed is
the same reason this item exists: the current single-dataset-per-asset
shape is not the target state, and reasoning from it produces wrong
answers.

24. **[todo, 2026-09-21]** **[QA checks & contract]** Backfill a newly-added check across every historical supply.

Keith, 2026-09-21, while working through `REQ-PIPE-038`, and it is the
reason retention has a purpose rather than just a cost. His own framing:
every version of every supply is already kept for operational reasons,
but once a QA tool exists there is real value in the history - "we might
want to add a new check to a table to pick up an issue that we identify
downstream, and to do that we would also like to be able to rerun it
against all of the historical supplies."

So a new check is not only a forward-looking thing. Adding one should be
able to answer "how long has this been wrong", which needs the check
evaluated against supplies that arrived before it existed.

**It is a TUI operation, not a one-off script** (Keith, 2026-09-21,
adding to the above). Exposed through `mothman` like everything else,
and runnable at **either dataset or collection level** - so "backfill
this new check across every supply of cp-placements" and "backfill it
across the whole Child Protection collection" are both real choices a
person makes at the point of running it.

Collection level is not just a convenience wrapper over six dataset
runs, and that is worth noticing early: a collection-scoped backfill is
the only shape that can re-evaluate a CROSS-TABLE check across history,
because those checks do not belong to any one dataset (`REQ-QAC-037`).
A dataset-scoped backfill can only reach that dataset's own checks.

**Tension to resolve before this is built**, flagged rather than
resolved: `REQ-PIPE-035` records his own answer that a check is
evaluated once against the composition current at the time and never
recomputed. That was about an EXISTING check's result, which should
stand as recorded. This is a NEW check evaluated against historical
state, which is a different act - but it does require composing a
warehouse as it was, which is the point-in-time composition that answer
declined. The two are compatible only if the distinction is written
down explicitly, and right now it is not.

25. **[todo, 2026-09-21]** **[Pipeline & publishing]** A TUI entry point for loading a supply from S3 or the filesystem into Postgres, then running QA against it.

Keith, 2026-09-21, thinking about where this tool sits operationally -
"a world where this tool is also doing the loading into the database, so
the user is choosing it from S3, it's loading into the database and then
running QA, or indeed the automated version of that." A new `mothman`
entry point alongside the existing ones.

**His own words: not needed right now.** Logged so it is not
rediscovered, not scoped.

It matters to the item 6 work for one reason only, and that reason is
already resolved: if the tool does the loading, a cross-table check can
be reached before the table on its other side has been loaded. His
resolution - all relevant data is loaded before QA runs, whether a human
or an automation triggers it, and QA then runs against the latest
version available of each table, whether that came from this supply or
an earlier one.

26. **[done, 2026-10-12]** **[Data generation]** Regenerating on a different day DOUBLES the committed history instead of replacing it.

Found 2026-09-21 while answering Keith's question about how far Birth
Registrations' history goes back. The answer turned out not to be a
configuration matter at all.

`qa_results/registry-services/birth-registrations/` holds **352 run
directories, and they are two complete generations of the same history**.
Measured, not inferred: there are exactly 176 distinct
`(delivery_id, attempt_number)` pairs, and every single one appears
under two `delivery_date` values one day apart.

    delivery_099 attempt 3  ->  2026-08-28  AND  2026-08-29
    delivery_094 attempt 1  ->  2026-08-23  AND  2026-08-24

The cause is `generator/generate_runs.py` line 118:

    START_DATE = get_anchor_date() - timedelta(days=N_DELIVERIES - 1)

The schedule is anchored to **today**, and a `run_id` embeds its own
date (`run_007_2026-05-28`). So regenerating on a different day shifts
every delivery date, every run_id changes, and the new set lands
ALONGSIDE the old rather than replacing it. Somebody regenerated on two
consecutive days and the committed history silently doubled.

**This is a going-forward bug, not a one-off mess to tidy.** It fires
again on the next regeneration, it is silent - nothing errors, the
history just grows another copy - and `qa_results/` is the permanent
source of truth, so the growth is committed. It also means every
measurement taken off that directory has been inflated: the "352 runs"
this project has been quoting is really 176.

Worth fixing in the same change as `REQ-PIPE-038`'s regeneration, or the
very first run of the new pipeline reintroduces it.

Shapes a fix could take, none chosen: pin the anchor date so a
regeneration is reproducible rather than relative to today; have
regeneration clear the dataset's directory first, which the
delete-and-regenerate decision already permits; or stop encoding a date
in the directory name so a re-run overwrites rather than accumulates.
The third is the only one that also fixes it for a partial regeneration.
    **DONE 2026-10-12 (open-items audit):** the anchor date is pinned and run ids are dateless (REQ-GEN-042), and qa_results/ - the committed history it doubled - is gone (REQ-PIPE-089).

27. **[done, 2026-10-12]** **[Data generation]** A small number of supplies should arrive EARLY.

Keith, 2026-09-21, while describing how the real operational database
organises supplies - "if data arrived 10 days before the designated
refresh day, it would go into the quarter it belongs to, not the quarter
it arrived in per the calendar."

Measured against the real generated history: **zero supplies arrive
early**. 240 arrive exactly on their delivery date and 112 arrive late,
and every one of those 112 is a resupply. So the generator models
on-time and late, and has never produced the case Keith has just said
is real.

The concept is already half-built and needs no new fields. Every
manifest entry already carries BOTH `delivery_date` (the period the
supply belongs to) and `arrived_date` (when it actually landed), and
they are already allowed to differ - that is exactly how a late resupply
is represented. An early arrival is the same two fields with the
inequality the other way round, which the generator never emits.

Why it matters beyond realism, and this is the part to carry into the
design: it is the cleanest demonstration that **the period a supply
belongs to is not the same axis as when it turned up.** Every "as at"
question has to pick one. A supply that belongs to Q1 but landed in
March, and a correction to Q1 that landed in April, both belong to Q1 -
so a resolution rule keyed only on arrival time gets them wrong.
    **DONE 2026-10-12 (open-items audit):** REQ-GEN-040 (built): the generator can deliver early.

29. **[todo, 2026-09-23]** **[Data generation]** Build a few small, genuinely-real datasets across several agencies, once all the sprints are done.

The other half of the same 2026-09-23 conversation, and the reason
deleting the illustrative data was safe to do. That deletion is BUILT -
`REQ-DASH-055`, 2026-09-23, which now owns its decisions; this item is
what makes it a replacement rather than a loss. Keith's own words: *"when we finish all these
sprints, we'll just build a few small data sets across multiple
agencies that have a sort of a few columns in a different shape, so we
get back to the point of having a semi-realistic set of agencies and
data sets."*

Three things his phrasing actually specifies, worth keeping because
they are easy to lose:
- **SMALL.** Not another Child Protection. A few columns each.
- **A DIFFERENT SHAPE.** The point is variety in the column shapes, not
  more rows of the same thing - which is what would actually exercise
  the generalisation this PoC claims.
- **MULTIPLE AGENCIES.** Breadth across the tree, not depth in one
  collection - so the agency and collection tiers have something real
  to roll up.

**Timing is explicitly the end of the sprint sequence**, not
opportunistically along the way. Worth honouring: `plans/supply-model.md`'s
own sprints are all specified against today's two datasets, and adding
datasets mid-sequence would change what each sprint has to satisfy
while it is being built.

**This is the item that pays down `plans/running-thoughts.md` #23 and
`plans/publishing-and-history.md` item 6**, which both say the same
thing from the other direction: adding datasets is the trigger for
resolving the file-per-dataset shape, because "add a dataset" currently
means "copy-paste a file." Doing 29 without having resolved that is how
the copy-paste cost gets multiplied rather than paid. Scope them
together.

30. **[todo, 2026-09-23]** **[QA checks & contract]** Go back and populate the new per-dataset config, once the sprints are done.

Keith's own ask, 2026-09-23, during the sprint: *"remind me to go back
and add some of the new config, like the expected time and claim
window."* Timing is explicitly after the sprint sequence.

**Why there is anything to go back FOR, which is the part worth
recording.** `REQ-PIPE-049` built the CAPABILITY for both and
deliberately did not populate either with real values:

- **`expectedTime` / `latency` per dataset.** The parser now honours
  `element:`, so a property naming a dataset overrides the
  contract-wide default. Child Protection's six datasets currently all
  take one contract-wide `expectedTime: "09:00"` and `latency: 480`,
  which is honest - they genuinely do share one cadence today - but the
  whole point of fixing the `element:` bug was that they need not.
- **`claimWindow` per dataset.** The calendar carries the default (14d
  quarterly, 4h daily) and a dataset may override it in its own
  contract. No dataset does.

Both were left empty on purpose rather than by omission: inventing a
business fact Keith has not stated would ALSO have moved real arrival
verdicts in committed history, and `REQ-PIPE-048`'s 150-arrival pin
exists precisely to catch that. So this is a decision to revisit with
him, not a gap to quietly fill - what are the real agreed times and
windows, per dataset?

**Sequence it with #29.** That item adds a few small datasets across
several agencies with genuinely different shapes - which is exactly
when differing expected times and claim windows stop being
hypothetical and start being the thing the config is for. Populating
them against today's two datasets would mean inventing differences;
populating them alongside #29's new datasets means describing real
ones.

31. **[todo, 2026-09-23]** **[Dashboard UI]** Live documentation of the configuration files, in the dashboard.

Keith's own ask, 2026-09-23, same conversation, and explicitly parked
for after the sprints: *"park an item for after the sprints to do some
live documentation in the dashboard of the configuration files."*

**The mechanism already exists three times over**, which is most of why
this is cheap and why it is worth doing rather than writing another
Markdown file nobody opens. The dashboard already renders committed
repo files as live tabs: `PLANS` from `plans/*.md`
(`dashboard/plans_md.py`), `REQUIREMENTS` from `requirements.yaml`
(`dashboard/requirements_yaml.py`), and `RELEASE_NOTES` from
`CHANGELOG.yaml` (`dashboard/changelog_yaml.py`). A config tab is the
same shape: a parser module, a const embedded by
`dashboard/embed_dashboard_data.py`, a top-level tier.

**What it would cover**, and the list grew a lot this sprint - which is
the real reason Keith asked:
- `contract/data-asset.yaml` - now the single statement of the
  agency/collection/dataset hierarchy (`REQ-QAC-039`), the asset
  timezone (`REQ-PIPE-048`), and the named, versioned delivery
  calendars with their periods and claim windows (`REQ-PIPE-049`).
- The two dataset contracts' `slaProperties` - cadence, expected time,
  latency, and now per-dataset overrides via `element:`.
- Whatever `REQ-PIPE-050`'s schedule gate ends up validating, since a
  page explaining the rules and a gate enforcing them should not be
  two independent accounts of the same thing.

**The question to scope with him first**: is this a reference page
(here is what the config says, rendered readably) or an explainer (here
is what each setting MEANS and what breaks if it is wrong)? Those are
different pages. `mothman schedule show` already does the first for
calendars on the CLI, which argues the dashboard's version should be
the second - but that is his call, not an assumption to build on.

32. **[done, 2026-10-12]** **[QA pipeline]** Child Protection's
    two real-tool modules still resolve their CSVs from
    `data/cp_raw/<run_id>/`, which couples them to a run_id the
    GENERATOR wrote down.

Found while fixing test fixtures for `REQ-GEN-043`, not looked for -
worth writing down because it is the last place the pipeline still
depends on the generator having named something, and it works today
only by coincidence.

**What it is.** `qa_tools/cp/run_datacontract_cp.py:82` and
`qa_tools/cp/run_evidently_cp.py:45,47` both build a path as
`CP_RAW_DIR/<run_id>/<table>.csv`. Nothing hands them the delivery they
are checking; they reconstruct a path from the run_id. Meanwhile
`generator/generate_cp_runs.py:494` writes exactly that directory,
naming it `cp_run_{run_index:03d}` - a run_id it assigns itself.

**Why it currently works, and why that is not reassuring.** Arrival
recognition assigns `cp_run_001`, `cp_run_002`... in receipt order, and
the generator numbers its runs in the same order, so the two agree. They
agree by construction of one synthetic generator, not by anything the
pipeline can check. The moment a real supply arrives out of order - which
is the entire subject of the supply model, and the exact thing that
permuted 23 Birth Registrations run_ids this same sprint - CP would
silently read the wrong delivery's CSVs. Silently, because a
`cp_run_007` directory would exist and parse fine.

**BDM does not have this.** Its equivalents take a `csv_path` that came
off the recognised arrival (`Arrival.path_for()`), so the file they read
is the file that arrived.

**Why it was not just fixed.** `REQ-GEN-043`'s criteria are about what a
delivery may declare and what may be read back out of one; the three
readers its NFRs actually name have all been retired. `data/cp_raw/` is
staged data, not bookkeeping, so nothing in that requirement forbids
this. Fixing it properly means threading the arrival's own path through
`evaluate_datacontract_cp()`/`evaluate_evidently_cp()`, which is filing
work and belongs with `REQ-PIPE-034`/`035`/`036` rather than bolted onto
a generator sprint.

**The tell, if this is ever picked up**: `tests/conftest.py`'s CP
fixture has to name its `data/cp_raw/<run_id>/` directories after the
run_ids RECOGNITION will assign, because those two modules read them
back by that name. A fixture that has to predict an id it does not
control is the coupling showing through.
    **DONE 2026-10-12 (open-items audit):** REQ-PIPE-102 (built) retired data/cp_raw/; only comments still mention it.

33. **[superseded, 2026-10-12]** **[Pipeline & publishing]** Does the
warehouse stay ephemeral, or become a permanent thing?

Keith, 2026-09-23, raised in passing while settling the delivery log's
structure during `REQ-PIPE-038`'s walkthrough, and explicitly deferred -
"we'll tackle that later, let's get the structures set up and get this
thing working first". Logged rather than carried in conversation because
it is exactly the kind of aside this project has lost before.

His words, in substance: **as we work out how we roll this out for other
people to test, we are going to have to tackle whether the warehouse
remains ephemeral or becomes a permanent thing.** He is not sure yet.
And the thing that makes it a real question rather than a tidy-up: **the
operational database is an actual database running in Amazon**, not a
DuckDB file that gets regenerated.

**Why it matters more than it sounds.** Several decisions settled the
same day assume the warehouse is disposable and the committed files are
the durable record - the delivery log lives in git and the warehouse
reads it through a view; arrival history must survive for years, so it
cannot live only in a warehouse that is regenerated. None of that breaks
if the warehouse becomes permanent, but the REASONING changes: today
"committed is the source of truth" is forced by the warehouse being
gitignored and rebuildable, and if that stops being true, someone will
reasonably ask why there are two places. The answer would then have to
be about the dashboard's no-live-data rule alone, which is a weaker
argument on its own.

**Related, not the same question**: `plans/wider.md`'s warehouse-choice
item, and `REQ-PIPE-018`'s AWS MVP, which is unsigned. This one is
narrower - not which engine, but whether the thing persists between
runs, and what that does to the committed-versus-queryable split.
    **SUPERSEDED 2026-10-12 (open-items audit):** REQ-PIPE-087/089 made PostgreSQL the system of record, so the ephemeral-or-permanent question went with DuckDB.

34. **[done, 2026-10-12]** **[Testing & dev tooling]** Run the
POST-BUILD subagents over the supply-model build work - the batch-3
build when it happens, AND the twelve requirements already built in
sprints 1-6, which never had a critic pass at all.

Keith's own ask, 2026-09-23, at the end of batch 3's sign-off: "let's
also remember once we've done this bit of build work to turn the
post-build sub agents back at this work and the previous build work
from the other sprints."

**The gap is real and it is not small.** `docs/agent-orchestration.md`
prescribes `delivery-critic` after EVERY build, plus the surface-specific
critics. Twelve requirements were built across 2026-09-21..23 and not one
went through any of them - the sprints ran build, gate, commit, next.
Nothing was skipped deliberately; the post-build half of the pipeline
simply never got invoked while the sprints were moving fast.

Built, and owed a pass:

| Requirement | Surfaces |
|---|---|
| `REQ-QAC-039` | functional |
| `REQ-GEN-040` | functional |
| `REQ-GEN-042` | functional |
| `REQ-GEN-043` | functional |
| `REQ-QAC-047` | functional + dashboard (the status vocabulary renders) |
| `REQ-PIPE-048` | functional + dashboard (the as-of default date) |
| `REQ-PIPE-049` | functional |
| `REQ-PIPE-050` | functional + CLI (`mothman schedule validate`) |
| `REQ-PIPE-051` | functional |
| `REQ-PIPE-052` | functional + CLI (`mothman schedule show`) |
| `REQ-PIPE-053` | functional + dashboard (the exhausted notice) + CLI (the runway warning) |
| `REQ-DASH-055` | functional + dashboard |

Which critics: `delivery-critic` on all of them (acceptance criteria,
real test coverage); `delivery-dashboard-ux-critic` then
`delivery-dashboard-visual-critic` - in that order, not parallel, per
the orchestration doc - on the dashboard-facing ones; and
`delivery-cli-ux-critic` on the CLI-facing ones, which drives the real
running command via `scripts/dev/tui_drive.py`.

**ONE pass rather than twelve - Keith confirmed, 2026-09-23** ("happy
to do one pass with that, that's fine, rather than twelve"), so this is
his call rather than a session's judgement. Several of these touch
the same surfaces (`REQ-PIPE-053`'s exhausted notice and `REQ-QAC-047`'s
status vocabulary are the same pills on the same tiles), so a critic
looking at them together will catch interaction problems that a
per-requirement pass would not - and twelve separate runs of a
real-browser critic is a lot of wall-clock for a lot of repetition.

**One thing to watch when it happens**: `delivery-critic` checks work
against its requirement's own acceptance criteria, and `REQ-PIPE-053` is
marked `built` while three of its criteria are explicitly deferred to
sprint 8's filing layer. It will flag them as unmet, correctly. That is
expected rather than a finding - the requirement's own `[BUILD]`
decision says so - but a session reading the report cold will not know
that.
    **DONE 2026-10-12 (open-items audit):** the first post-build critic pass covered sprints 1-6 (plans/post-build-review.md, its opening entries).

35. **[superseded, 2026-10-12]** **[Testing & dev tooling]** Batch 3 goes to
`delivery-architect` and the UX agents next - CONDITIONALLY
pre-authorised by Keith.

Keith, 2026-09-23, immediately after batch 3's sign-off: "if the scoper
comes back with no significant findings, I'm happy for you to send what
we've got on to the architect and the UX agents as well. Um, before we
build."

**The condition is load-bearing, so state it plainly.** The
authorisation is to proceed WITHOUT checking back only if the
`delivery-scoper` sense-check returns nothing significant. If it returns
real findings - a decision carried in no requirement, a further
superseded model, a genuine gap - those go to Keith FIRST. He has not
pre-approved acting on findings, only proceeding in their absence.

**Why the scoper pass is running at all** (Keith's own call, over a
session's suggestion that the carry-over check alone would do): these
six were never run through `delivery-scoper` as a batch. All six were
hand-drafted 2026-09-21 from `plans/publishing-and-history.md` item 6,
before the batching scheme existed, and were later labelled batch 3.
Three of the six turned out at sign-off to carry a superseded model,
where the requirements the scoper DID produce needed no such
corrections. His words: "even if it won't come back with much, it'll be
a good sense check."

**What goes next, per `docs/agent-orchestration.md`**: `delivery-architect`
always, and `delivery-dashboard-ux` for `REQ-DASH-041` (worth including
the unsigned `REQ-DASH-056` in the same pass - same surface, same
viewer, and its open question about tile-versus-detail-panel is exactly
what that agent is for; Keith has ideas but wants their thoughts first).
`delivery-cli-ux` is arguable for `REQ-PIPE-038`'s regeneration
subcommand, which is a thin CLI surface.

The architect has two questions waiting for it BY NAME, and they are one
decision rather than two: where the delivery log lives, and where the
cross-table scope lives in `qa_results/`. Both are "committed history
that is not one dataset's QA results".

Then Keith reviews both notes and confirms the approach, and the build
happens in the main session - no agent does the building. Build order is
near-linear on the dependencies: `034` -> `035` -> `036` -> `037` ->
`038` -> `041`. `034` is unblocked now and does NOT need the architect's
placement answer, so it could start while the architect works.
    **SUPERSEDED 2026-10-12 (open-items audit):** batch 3 (REQ-PIPE-034..038, QAC-037, DASH-041) is all built.

36. **[todo, 2026-09-23]** **[Data generation]** Keith wants one last
review of the ON-DISK STRUCTURE for storing deliveries, once sprints
7-10 come back from the scoper.

His words, 2026-09-23: "when this all comes back, I do want to do one
last review of what the delivery, like what the structure on disk looks
like for storing the deliveries. Keen to see how that's settled. It's
not super important, because it's only going to be the synth data in
the PoC, but it'd be good to get eyes on that."

**What already exists to review.** `docs/delivery-format.md` is marked
NORMATIVE and is what `REQ-GEN-043` built - one directory per physical
arrival, the directory itself being the boundary, with 42 real
deliveries under `data/deliveries/` today. Sprint 7 (delivery
recognition and file-to-dataset mapping) is the CONSUMER of that
format, so scoping 7-10 is the point at which the format gets its first
real test from the other side.

**Why he is right that it is worth a look even though it is low stakes
here.** The format is what a real supplier's transport has to be plumbed
into - Thread B's "the delivery boundary is load-bearing and it comes
from the transport", and a source that cannot express one needs one
arranged operationally. In the PoC every delivery is a tidy directory
the generator wrote. The review is about whether the format survives
contact with a transport nobody controls, which is exactly what the
synthetic case cannot tell us.

Present it to him as the actual directory layout plus what recognition
reads out of it, not as a requirement diff.

37. **[todo, 2026-09-24]** **[Pipeline & publishing]** The delivery
receipt is thin - it carries a name and an instant, and nothing about
provenance.

Keith's own ask to log it, 2026-09-24, arising from asking what a
receipt actually IS in production. Today the whole of it is:

```json
{"delivery": "EXTRACT_20260824", "received_at": "2026-08-24T14:36:03+08:00"}
```

**Why the thinness matters more than it looks.** The receipt is now the
one trustworthy arrival fact in the whole model - `REQ-PIPE-057` makes a
delivery count as received only where our own receipt exists,
`REQ-PIPE-061` processes in receipt order, and `REQ-PIPE-066` classifies
early/on-time/late against it. Everything downstream leans on it, and it
records almost nothing about where the supply came from.

In production you would plausibly want: which TRANSPORT it arrived on,
which PRINCIPAL or credential delivered it, the source bucket and key or
SFTP account, and possibly a checksum. That is what makes "who sent us
this, and how" answerable a year later - the question that gets asked
when a supply turns out to be wrong and nobody remembers which of three
feeds it came down.

**The reason to decide it early rather than when it hurts**: receipts
are immutable and accumulate, so a field added later cannot be
backfilled. Every arrival before the change is permanently thinner than
every arrival after it, and the gap never closes.

Not needed for the PoC, where one generator writes everything. Logged
because the cost of adding it later is paid by the records that already
exist.

38. **[superseded, 2026-10-12]** **[Pipeline & publishing]** Design WHEN a
delivery receipt gets written, as part of moving to AWS.

Keith's own ask, 2026-09-24. Not designed anywhere today:
`docs/aws-event-driven-mvp-design.md` parses the real S3 `ObjectCreated`
event shape but says nothing about receipts at all - it predates the
supply model by weeks - and `REQ-PIPE-018` (the AWS MVP) is unsigned and
not started.

**What is settled** is only who writes it: **we do, never the supplier.**
That is enforced structurally rather than by convention -
`write_delivery()` refuses outright if the receipts directory sits inside
the deliveries directory, because "the receipt record is ours and must
live where a supplier has no path to write it" - and Thread H settled
"our own receipt timestamp, never the supplier's".

**What is not settled is the moment.** The PoC's `data/receipts/` is a
stand-in for an ingest observation log; in production it is not a file
at all but whatever the receiving component records - an S3
`ObjectCreated` event, an SFTP watcher noticing a file, a batch
endpoint's request completion.

**The hard part, and it is the same problem as the delivery boundary.**
In S3 a supplier PUTs objects and events fire PER OBJECT. There is no
delivery-is-finished signal. So "when do we write the receipt" is
exactly "when does our boundary rule say this delivery is complete",
which Thread B already requires to be arranged per source - a folder
convention, a trigger file, a batch endpoint. The two questions are one
question, and answering the receipt half without the boundary half is
not possible.

Consequence already relied upon (`REQ-PIPE-057`, settled 2026-09-24): a
delivery with files and no receipt means the boundary has not closed
yet, so it is the NORMAL state of every delivery until it does - which
is why that requirement skips it as in-flight and reports it
informationally rather than treating it as an anomaly.
    **SUPERSEDED 2026-10-12 (open-items audit):** REQ-PIPE-105 (each file its own arrival, stamped by storage) and REQ-PIPE-152 are built; REQ-PIPE-018's open question on it is stale.

39. **[todo, 2026-09-24]** **[Pipeline & publishing]** A supplier splits
one table across several files, and we stitch them back together on
load.

Keith's own ask, 2026-09-24, raised while signing off `REQ-PIPE-059`.
His words: "the supplier splits it into three parts to assemble it and
we need to stitch it back together as part of loading it into staging."

**Explicitly OUT of scope for this PoC.** `REQ-PIPE-059` holds every
such delivery for a human, every time, which Keith chose knowing the
cost - a supplier who routinely splits an extract generates a hold per
period, per dataset, indefinitely. A proper splitting mechanism is the
answer; a hold is the honest placeholder until one exists.

**The tension this leaves in the repo, worth knowing before it is read
as a defect.** `docs/delivery-format.md` lists "two files matching one
dataset's pattern - suppliers split large extracts" as one of three
shapes a delivery may LEGITIMATELY contain. That stays true of what we
may RECEIVE. What `REQ-PIPE-059` settles is that we will not process one
unattended, which is a different claim.

**What a real requirement here would have to answer**, none of which is
settled: how a dataset DECLARES that it arrives in parts (a config flag,
or a resolution a human records once); whether the parts are concatenated
on load, which is the merging `REQ-PIPE-059` explicitly rejected as
"manufacturing a supply that never arrived" and would need a stated
reason to be acceptable here; whether a MISSING part is detectable at all
(three of three versus two of three is invisible without the supplier
saying so, which is the declared-manifest shape Thread B rejected); and
what ORDER means when the parts carry no sequence beyond their filenames.

40. **[todo, 2026-09-24]** **[Pipeline & publishing]** Delta supplies -
a delivery carrying adds, updates and deletes rather than a full table.

Keith's own ask, 2026-09-24, in the same breath as #39 and the same
shape of problem: "files with add/update/delete or maybe add+update/
delete." So one dataset may arrive as two or three files in one
delivery, split by OPERATION rather than by size.

**Explicitly OUT of scope for this PoC**, same as #39, and it falls into
the same `REQ-PIPE-059` hold today - several files matching one
dataset's pattern, held for a human.

**Why it is a bigger change than #39 rather than a variant of it.** A
split extract is still one table version cut into pieces, so stitching
restores the thing that arrived. A delta is NOT a table version at all -
it is a change SET against a previous state, which breaks the model's
own central assertion that "a supply is one table VERSION". Everything
downstream leans on that: promotion replaces a table, drift compares
this period's table to last period's, and a QA verdict is about the
table as supplied. None of those mean the same thing when what arrived
is 400 deletes.

**Questions a real requirement would have to answer:** whether a delta
is applied to the promoted table before QA or QA'd as the delta itself;
what a green verdict on a delta even asserts; what happens when a delta
arrives for a period whose base was never promoted; and whether the
apply is reversible, since demotion currently means swapping a table
back rather than un-applying changes to one.

41. **[todo, 2026-09-24]** **[Docs & process]** **[Dashboard UI]** A
CONCEPTS page - the supply vocabulary explained, with diagrams.

Keith asked on 2026-09-24 whether we had made "that concepts page that
kind of was going to have descriptions and then some diagrams, all the
concepts we're coming up with around like deliveries and supplies and
slots and periods". **We had not**, and a real search found no trace of
it ever being scoped: no `docs/concepts.md`, no dashboard tab, no
requirement, nothing in this file's other 40 items, and nothing added or
deleted in git history. The word "diagram" appears twice in the whole
planning corpus, neither time about this.

**That it left no trace is the point of logging it now.** He remembered
it as something we had agreed to do, which means it was raised at least
once and evaporated - exactly the failure `CLAUDE.md`'s "log any aside
immediately" convention exists to prevent.

**Three things already exist that keep making this look done**, and each
is a different job:
- `plans/supply-model.md`'s **Concept inventory** (2026-09-22) is the
  closest, and it answers what the model INTRODUCES, CHANGES and
  RETIRES. It is written for a builder navigating vocabulary change
  mid-flight, who already knows the concepts and needs to know which
  words survive. Not an explanation, and no diagrams.
- `docs/components.md` is the 7-part COMPONENT taxonomy - a different
  axis entirely.
- `docs/delivery-format.md` is normative on one concept, and only its
  physical shape on disk.

So the vocabulary built across the supply-model work - delivery, supply,
slot, period, run, staging, promotion, rejection, and now carry-forward
(sprint 25) - is defined across threads and `requirements.yaml`'s
`decisions:` fields, and **nowhere that explains it to a person**. That
matters more the moment anyone else uses this.

**Where it lives is a real fork, not a detail:**
- `docs/concepts.md`, versioned beside the code, read by contributors
  and by the `delivery-*` agents. Cheapest, and it is where
  `docs/components.md` already sits.
- A dashboard **Concepts tab** - a real `/concepts` URL alongside Plans
  and Demo - so someone reading the dashboard can look up "what is a
  slot" without a repo checkout.
- Both, with the tab rendering the doc. The Plans tab already parses
  committed markdown at build time (`dashboard/plans_md.py`), so the
  second is nearly free once the first exists.

**Diagrams need their own small decision**: this repo has no diagramming
toolchain at all today. Hand-authored inline SVG (consistent with how
the dashboard draws everything else, and works from a `file://` open),
or a text source rendered at build time, which adds a dependency the
"no live external dependency at render time" rule would have to be
squared with.

**Do it AFTER the supply-model sprints, not during.** Writing definitive
descriptions of concepts whose requirements are still being signed off
would produce a page that is wrong before it is finished - and a wrong
glossary is worse than none, because people quote it.

42. **[todo, 2026-09-24]** **[QA checks & contract]** A CONTENT CHECK
that asks "does this supply look like the period it is filed under" -
the only thing that turns a wrong default filing into something a human
sees.

Surfaced 2026-09-24 at `REQ-PIPE-065`'s sign-off, where a decision says
plainly: **"NO REQUIREMENT OWNS IT; it is a check and belongs with batch
5's check work."** Logged here because a decision buried inside one
requirement is a record, not a task list - nothing would have brought it
back up when batch 5 was scoped.

**Why it exists.** `REQ-PIPE-065` settles that an ambiguous assignment
DEFAULTS BACKWARD - an arrival that cannot be told apart from a late one
takes the oldest claimable unfilled slot, because late is commoner than
early - and is marked as uncertain. That default is right on average and
wrong sometimes, and nothing in the assignment rule can tell which.

**What this check adds, and the line it must not cross.** It is a
DETECTOR, never a decider. "This supply does not look like the period it
is filed under" is a legitimate, non-circular QA finding - it reports,
it does not make the filing call. That distinction is load-bearing:
`REQ-PIPE-062` rejects DERIVING the period from the supply's own content
as circular, because it would infer the filing decision from the very
data whose correctness is about to be tested. Reporting on the mismatch
is a different act from deciding with it, and only the second is
forbidden.

**Not scoped.** What "looks like the period" means is undefined and is
the whole design problem - a date column's range, a row-count profile,
a comparison against the previous supply, or something per-dataset and
declared. Belongs with batch 5's check work.

43. **[todo, 2026-09-24]** **[QA checks & contract]** EXTRACT-TO-RECEIPT
LAG as a real check - how long between a supplier extracting their data
and us receiving it.

Keith's call, 2026-09-24, settling pre-build question 11: the arrival
block in `dataset_stats.json` goes (`REQ-PIPE-066` criterion 12), and
what was worth keeping in it becomes a check instead. His own words:
"that should not be in the JSON, that should be like a check that we
craft."

**What is being deleted, and why the useful part is not simply
renamed.** That block held `earliest_extract`, a `MIN(extract_timestamp)`
over the SUPPLIER's own column - which `REQ-PIPE-060` criterion 11
forbids as an arrival time - and `max_lag_hours`, which despite sitting
in a block called "arrival" measures `MAX(extract_timestamp -
date_registered)`, a within-supply staleness figure that is computed,
committed, carried through both dashboard build paths and **rendered
nowhere**.

**The genuine finding underneath them** is different from both: the gap
between when a supplier EXTRACTED their data and when WE RECEIVED it.
That is real signal about supplier behaviour - a supplier whose extracts
are consistently three days stale by the time they arrive is telling you
something - and it is a different question from whether the supply was
on time, which `REQ-PIPE-066` now answers from the assigned slot.

**Why it has to be a check rather than a stat**, which is the part of
Keith's framing worth keeping: a lag figure with no threshold is a
number nobody acts on. As a check it gets a tolerance, a verdict, and a
place in the same amber/red vocabulary as everything else - and it
inherits the tiering discussion from `plans/road-testing.md` item 6.

**Not scoped.** It needs `REQ-PIPE-066`'s receipt instant to compute, so
it cannot be built before that lands. Open: whether the measure is the
earliest extract in the supply, the latest, or a distribution; whether
the tolerance is per-dataset like the grace allowance; and whether a
deliberately-disordered row should be excluded (the deleted code
filtered them out to protect the classification - a check arguably wants
to SEE them, and there is already a separate ordering check that does).

**Merged 2026-10-12** with a second #43 (2026-09-25) that said the same
thing; its two points not already here: the measure needs OUR receipt
instant, which exists only from REQ-PIPE-060 onward (the deleted field
could never have computed it), and it belongs with batch 5's check work.

44. **[investigate, 2026-09-25]** **[Pipeline & publishing]** A MORE
    ELEGANT MECHANISM FOR THE IMMUTABLE HISTORY OF CHECKS - Keith's own
    ask, raised while approving the check-seal fix
    (`plans/post-build-review.md` #44): "I'd like to think about a more
    elegant mechanism for recording this immutable history of checks
    and so forth, because the daily data asset is going to have like 20
    datasets appearing daily, so that starts to get big and expensive."

    **What happens today**, measured rather than estimated:
    every real run commits four tool files plus `dataset_stats.json`
    under `qa_results/<agency>/<collection>/<run_id>/`, and each tool
    file carries `raw_output` (that tool's native JSON) beside
    `verified` (the fully-resolved check records). One Birth
    Registrations run is ~300KB; the whole committed tree is **26MB
    across 60 runs**, averaging ~444KB per run. Of a 685-byte
    `verified` record only ~254 bytes is CONFIGURATION - the rest is
    the run's own result, plus the agency/collection/dataset triple
    repeated on every record. `raw_output` is **77%** of the volume.

    **Why it stops being academic at the real target.** Keith's own
    figure, 2026-09-25: the daily asset will have roughly **20 datasets
    arriving daily**. At today's measured rate that is:

    | | |
    |---|---|
    | 1 year | 7,300 runs, **~3.1 GB** |
    | 3 years | 21,900 runs, **~9.3 GB** |
    | 5 years | 36,500 runs, **~15.4 GB** |

    In a git repository that everyone clones. And ~2.4GB/year of it is
    `raw_output` alone.

    **What this is NOT.** It is not a consequence of the check-seal
    change approved the same day - that only READS what is already
    committed and adds nothing. And it is not an argument against
    Thread B: a permanent, committed QA history is the point of this
    design, and the 26MB bought something real. The question is whether
    the SHAPE is right, not whether the history should exist.

    **Threads worth pulling when this is picked up:**
    - **Does anything read `raw_output` back?** It is 77% of the
      volume and it exists so a tool's native output is never lost.
      Nobody has checked what actually consumes it. If the answer is
      "nothing, outside forensics", keeping it only for runs where
      something failed is most of the saving for none of the loss.
    - **Configuration is repeated, not versioned.** A check's
      thresholds are written into every run although they change
      perhaps twice a year. A separate, append-only record of "this
      check had these thresholds from this date" would hold the same
      immutable history in a few KB rather than a few GB - and it is
      exactly what the seal gate wants to read anyway.
    - **The per-record triple.** `agency_id`/`collection_id`/
      `dataset_id` are on every one of 257 records per run and are
      already in the file's own path.
    - **Compression.** `dashboard/snapshots/*.html.gz` already
      establishes that this repo will commit gzipped artefacts where
      the content is archival rather than diffable. JSON of this shape
      compresses hard, and nothing reads these files in a hot path.
    - **Whether git is the right store at all** past a certain size,
      and what that would cost in the "works from a plain clone"
      property the whole project leans on.

    **Not urgent at 2 datasets and 60 runs.** Worth designing before
    the daily asset exists rather than after, because migrating a
    committed history is far harder than choosing its shape.

    **THIS ITEM NOW OWNS THE SEAL ITSELF**, decided 2026-09-25 ("yep,
    do the cheap hardening now and leave the seal for 44"). The cheap
    half shipped the same day - both immutability gates now read the
    whole push rather than its last commit, the changelog escape needs
    a NEW entry rather than any edit, and the past/future boundary is
    on the asset's clock (`plans/post-build-review.md` #44, which
    records what was and was not closed). The part deliberately left
    here is the SEAL: a committed record of what a check was when it
    was last used to judge data, so the gate needs no git history at
    all.

    It is left here rather than built because the two are the same
    artefact. The obvious build - writing each check's `config_hash`
    into every verified record - costs ~8.8KB a run, **~63MB a year**
    at the 20-datasets-daily figure above, and lands squarely in the
    problem this item exists to solve. The second thread above
    ("configuration is repeated, not versioned") IS the seal, at ~30KB
    a year in total. Building the per-run hash first would be building
    the throwaway version of the thing this item is meant to design.

    One correction worth carrying, because it was got wrong out loud
    before it was got right: the committed history does NOT already
    contain what the check gate compares. `find_undocumented_changes()`
    compares `config_hash`, a SHA-256 of a check's whole config dict;
    the `verified` records carry the RESOLVED thresholds and nothing
    else, and `config_hash` appears nowhere in `qa_results/`. Changing
    a dbt `accepted_values` list from `[M, F, X]` to `[M, F, X, U]`
    changes the hash and changes no threshold - so comparing on what
    history already holds would miss exactly the class of change that
    matters most.


45. **[done, 2026-10-12]** **[Pipeline & publishing]** Add PostgreSQL to this PoC, so the warehouse can be tested like for like with production.

    **Keith's own ask, 2026-09-26**, raised while settling how demotion
    moves a table out of a period schema (`REQ-PIPE-081`). The design
    question turned on an engine difference, and neither the design nor
    the tests can currently see it.

    **The concrete thing that prompted it, measured the same hour:**

    - PostgreSQL's `ALTER TABLE ... SET SCHEMA` is a CATALOGUE-ONLY
      operation. The table's data files never move; indexes,
      constraints and owned sequences come with it. A demotion is
      instant whatever the table's size.
    - DuckDB does not implement it AT ALL. Verified against the
      installed 1.5.5: `ALTER TABLE a.t SET SCHEMA b` raises
      `Not implemented Error: T_AlterObjectSchemaStmt`, and
      `ALTER TABLE a.t RENAME TO b.t` is a parser error. So on DuckDB
      the same move is `CREATE TABLE AS SELECT` plus `DROP` - O(rows),
      under DuckDB's single-writer lock (`REQ-PIPE-068`).

    Both are safe - DuckDB's DDL is transactional, verified by rolling
    a copy-and-drop back and finding the source table intact - but they
    are an order of magnitude apart in cost, and `REQ-PIPE-081` now
    carries criteria requiring the catalogue operation where it exists
    and the copy where it does not, chosen from a DECLARED capability
    rather than by trying and catching.

    **Which is the point: that branch has no test on the fast side.**
    Everything here runs on DuckDB, so the PostgreSQL path would be
    written from documentation and never executed. This project's own
    standing lesson is that a green data layer says nothing about an
    untested transform downstream; an untested ENGINE path is the same
    shape, one layer lower.

    **What it would cost, roughly, and worth scoping properly rather
    than assuming:** a second warehouse adapter behind whatever
    interface `supply_db` settles on; a Postgres service in
    `test.yml` (GitHub Actions offers one as a service container);
    the dbt and Soda profiles gaining a second target; and a decision
    about whether the whole suite runs twice or only the
    warehouse-touching part does, which is the runtime question -
    `plans/tooling.md` #24 already records the suite at ~200s with
    the e2e module as 85% of the gate.

    **Not just about this one branch.** `plans/wider.md` still has
    warehouse choice open, and the real deployment is two cloud
    environments that will not be running DuckDB. Every place the
    design leans on DuckDB behaviour - the single-writer lock, the
    view-over-physical-tables resolution, schema-per-period itself -
    is currently unverified against the engine it will actually meet.

    **THE SCOPE GREW THE SAME EVENING, and this item is now a
    PREREQUISITE rather than a nice-to-have (Keith, 2026-09-26).** It
    was raised over one engine difference in a demotion. Hours later,
    working through how a filing decision taken in a terminal reaches
    a shared log, he stepped back and asked the bigger question: in
    production the changes land in a real PostgreSQL database, so
    **should the decision log live in the database rather than in the
    repository?**

    Why that question is not idle. `REQ-GHUB-082` had reached an
    ambiguity nothing could close: its criterion 18 judges a decision
    permissible "at the instant its entry is appended", which is exact
    for a server-side write and undefined for a terminal appending to
    a possibly-stale clone that is pushed later. Four workarounds were
    drafted - pending-until-it-lands, judge-and-void-on-arrival,
    refuse-on-a-stale-clone, accept-and-detect - and every one of them
    is a way of coping with the absence of a serialisation point. A
    database has one, plus a transaction, so the ambiguity does not
    arise there. It would also collapse `REQ-PIPE-075` criterion 9's
    ordering rule into a single transaction, since the log and the
    tables would share a database.

    **Three things Keith settled about it straight away**, recorded so
    they are not re-asked:

    - **The never-touch-data rule is UNCHANGED.** The dashboard build
      still reads committed files alone. A database log would have to
      be exported to committed files by whatever writes it - the
      `dataset_stats.json` pattern, compute where the connection
      legitimately is and commit the conclusion.
    - **No inbound connection from GitHub to the database, ever - but
      the environment DOES have outbound access.** So the GitHub route
      inverts: something inside the secure environment polls the
      ticket and applies the decision, rather than a workflow reaching
      in. Posting the outcome comment back is outbound too, so it is
      the same channel.
    - **Sequencing: this item FIRST, then the design change.** His own
      call, over changing the requirements now. Every property the
      choice rests on is one DuckDB - a single-writer file - cannot
      exercise, so deciding now would be reasoning where experiment is
      available. Nothing in the supply sprints is built, so changing
      later costs requirement edits rather than code.

    **What that costs on the schedule, stated plainly rather than
    discovered:** sprint 11 is what seven other sprints are blocked
    on, and sprint 11 now waits on this. `REQ-PIPE-074`'s own open
    question carries the same account from the register's side, and
    `REQ-GHUB-082` should not be built until it is settled, because
    the answer changes what its criterion 18 means.

    **DECIDED THE SAME EVENING (Keith, 2026-09-26): ONE ENGINE, AND IT
    IS POSTGRESQL.** Staging, rejected and the period schemas all live
    there - splitting them across two engines is worse than either end
    state, since cross-engine views do not exist and `REQ-PIPE-068`
    criterion 7 already requires one database. DuckDB KEEPS A ROLE, but
    not as a warehouse: reading arriving deliveries in CSV, Parquet and
    whatever else turns up. Where the PoC runs: a GitHub Dev Container
    for development, a locally installed PostgreSQL for non-production,
    and AWS Aurora PostgreSQL in production.

    **MEASURED AGAINST A REAL POSTGRESQL 16.13 STOOD UP IN THE SESSION
    SANDBOX, 2026-09-26**, rather than read from documentation - the
    same preference this project already applies to dbt and Soda
    questions. Every property the supply model leans on holds:

    - `ALTER TABLE ... SET SCHEMA` is CATALOGUE-ONLY, now proven rather
      than cited: relfilenode `16404` and `pg_relation_size`
      `1,818,624` identical before and after moving a 50,000-row table,
      and its index moved with it.
    - DDL is TRANSACTIONAL: a `SET SCHEMA` inside `BEGIN`/`ROLLBACK`
      left the table in the schema it started in.
    - A PER-RUN SCHEMA OF VIEWS over physical tables in other schemas
      works, and `DROP SCHEMA ... CASCADE` discards the views while the
      physical rows survive - `REQ-PIPE-068` criteria 1, 2 and 5.
    - CROSS-SCHEMA JOINS work, so Child Protection's cross-table checks
      are fine.
    - CONCURRENT WRITERS: two sessions wrote at once with no lock wait
      and both rows landed. **DuckDB's single-writer lock is gone**,
      which is the constraint `REQ-PIPE-068` was shaped around and the
      reason tests pin one database per worker.

    **PACKAGING, resolved for real with `uv lock` rather than
    estimated.** All four tools have a Postgres path and NOTHING NEEDS
    UPDATING - `dbt-core 1.12.5`, `dbt-postgres 1.11.0`,
    `soda-core-postgres 3.5.6`, `datacontract-cli[postgres] 1.2.2`,
    `evidently 0.7.23`. Two things worth knowing:

    - **The resolution is SMALLER and cleaner: 160 packages against the
      current lock's 190, and `pyproject.toml`'s
      `override-dependencies = ["duckdb>=1.5"]` is NOT needed.** Both
      follow from the same cause - that override exists only because
      `soda-core-duckdb` declares `duckdb<1.1.0` while
      `datacontract-cli[duckdb]` needs newer. Dropping both DuckDB
      extras removes the conflict; plain `duckdb`, kept for file
      reading, carries no such pin.
    - **TWO DRIVERS, not one.** `dbt-postgres` and `soda-core-postgres`
      use `psycopg2-binary`; `datacontract-cli[postgres]` uses
      `psycopg` 3. They coexist - different package and import names -
      but that is two connection-string dialects to keep straight.

    **DuckDB's new role works, verified both ways.** `read_csv_auto`
    inferred `BIGINT`/`VARCHAR`/`DATE` correctly, and the load path is
    DuckDB to a typed frame to Postgres `COPY`, which needs no
    extension. The `ATTACH`-to-Postgres route also works and writes a
    CSV straight into a Postgres table with types preserved, but it
    needs DuckDB's `postgres` extension. **That extension can be
    installed from a LOCAL FILE** (`INSTALL '/path/to/
    postgres_scanner.duckdb_extension'`, after `httpfs`), which is the
    finding that matters beyond this sandbox: a government network
    that cannot reach `extensions.duckdb.org` can still use it if the
    extension is vendored, the same treatment `dashboard/vendor/`
    already gives the asciinema player.

    **A proxy gotcha worth recording so nobody re-diagnoses it.**
    DuckDB downloads extensions over PLAIN HTTP by default, and this
    session's proxy allows the host over https only - `http://
    extensions.duckdb.org/...` returns 403 while the identical https
    URL returns 200. Setting `custom_extension_repository` to the https
    host does not fix it either: DuckDB then requests the UN-GZIPPED
    filename, which 404s, where the default path requests `.gz`, which
    exists. Hence the local-file install above.

    **ALL FOUR TOOLS WERE THEN RUN FOR REAL AGAINST THAT POSTGRES,
    2026-09-26**, in an isolated scratch environment so the repo's own
    `pyproject.toml`/`uv.lock` were untouched. The fixture mirrored the
    supply model's real shape: a period schema, a physical versioned
    table inside it, a per-run schema of views over it, and two planted
    defects.

    - **dbt-postgres: works.** A real `dbt build` read through the
      per-run view schema, passed `unique` and `not_null`, and
      correctly FAILED the planted `accepted_values` violation. `dbt
      run` then materialised its model.
    - **Soda Core: works.** A real scan found both planted defects (a
      NULL birth weight, an invalid `sex`) and passed the other two
      checks.
    - **datacontract-cli: works.** Every schema and physical-type check
      passed against the live Postgres, and the required-field check
      caught the NULL.
    - **Evidently: nothing to prove.** It reads CSVs directly and never
      touches a warehouse.

    **THREE CONCRETE CHANGES THE TOOLS THEMSELVES FORCE**, each found
    by running rather than by reading:

    - **Soda has no `add_postgres_connection`.** DuckDB is a SPECIAL
      CASE in Soda's own API (`add_duckdb_connection` takes a live
      connection object); Postgres goes through
      `add_configuration_yaml_str`/`_file` with host, port, database
      and schema. So `run_soda_bdm.py`/`run_soda_cp.py` change shape
      rather than swapping a string.
    - **The dbt profile gets SIMPLER, and its whole current
      arrangement was a DuckDB workaround.** Today it points dbt at a
      scratch DuckDB FILE and `ATTACH`es the supply database read-only,
      purely because DuckDB gives a writer an exclusive lock over the
      file. On Postgres there is no lock: dbt writes its models into
      its own schema in the SAME database, and the attach disappears.
    - **An empty password is treated as UNSET by datacontract-cli**
      (`missing_env_DATACONTRACT_POSTGRES_PASSWORD`), and it takes
      credentials from environment variables rather than from the
      contract. Fine, and worth knowing before someone spends an hour
      on it.

    **THE MIGRATION SURFACE IS MUCH SMALLER THAN THE GREP SUGGESTS.**
    59 files MENTION duckdb, but only NINE non-test modules actually
    open it: `qa_tools/common/supply_db.py`,
    `qa_tools/common/asset_time.py`, `qa_tools/{bdm,cp}/dataset_stats.py`,
    `qa_tools/{bdm,cp}/run_soda_*.py`, `qa_tools/cp/run_datacontract_cp.py`,
    `pipeline/load.py` and `pipeline/aggregate_values.py`, plus the dbt
    profile and 12 test modules. **Two of the four QA tools -
    datacontract-cli and Evidently - read the arriving CSV directly and
    never touch the warehouse at all**, so they are not part of the
    migration unless we decide to point them at what landed, which is a
    design choice rather than a forced change.

    **ALL FOUR TOOLS WILL RUN AGAINST POSTGRES, WHICH ENLARGES THE
    MIGRATION RATHER THAN SHRINKING IT (Keith, 2026-09-26).** His own
    model: the pipeline loads the CSV, Parquet or whatever arrived into
    PostgreSQL FIRST, and then every QA tool checks what is in the
    database. That is NOT how it works today, and the difference was
    found while scoping this:

    - dbt and Soda read the WAREHOUSE, through the per-run view schema.
    - datacontract-cli and Evidently read the ARRIVING CSV straight off
      disk (`type: local`, `format: csv`, and
      `read_csv_explicit_nulls`). datacontract-cli's own internal
      DuckDB, which `run_datacontract_cp.py` mentions, is its engine
      for reading that file - nothing to do with this project's
      warehouse.

    So two tools check the file as delivered and two check the rows as
    loaded, they are different subjects, and nothing reconciles them.
    A load coerces types, turns sentinels into NULLs - this repo has
    had exactly that bug, `"N/A"` becoming NULL - or rejects rows.

    **A BUILT REQUIREMENT ALREADY IMPLIED KEITH'S MODEL**, which is the
    strongest argument for it: `REQ-PIPE-068` criterion 2 says route
    every read of supply data through the per-run schema and "SHALL NOT
    query a physical table directly from any check, tool invocation or
    downstream reader". Two of the four tools bypass that by reading a
    file, so this is an existing inconsistency with something marked
    `built` rather than a new question.

    **THE AGREED SHAPE (Keith, 2026-09-26, agreeing with this
    session's proposal): LOAD FIRST, ALL FOUR TOOLS CHECK THE
    WAREHOUSE, PLUS A SMALL EXPLICIT SET OF FILE-SHAPE CHECKS AT LOAD
    TIME THAT NEVER PRETEND TO BE DATA CHECKS.**

    The boundary is what makes it work, and it is not a hedge. A class
    of checks can only be made on the FILE and is destroyed by loading
    - encoding, delimiter, header row, column order, ragged or
    malformed rows, duplicate headers. Once the rows are in Postgres
    those questions are either already answered or gone, so "check
    everything in the warehouse" on its own would silently drop them.
    They stay, at load time, and they are labelled as what they are:
    statements about the FILE, not about the data. A reader must never
    have to work out which subject a check was about.

    A genuinely bad file fails the load outright, which is itself a QA
    signal and one already modelled - `REQ-PIPE-060` and `mothman
    supply failures` carry it, so this needs no new mechanism.

    **CORRECTION TO THE SURFACE ESTIMATE ABOVE**, recorded rather than
    quietly edited: this entry first said datacontract-cli and
    Evidently were not part of the migration because they never touch
    the warehouse. Keith's decision puts them back in. It is four tools
    to repoint, not two.

    **HOW POSTGRES ACTUALLY GETS THERE, read 2026-09-26 from the Dev
    Container spec and GitHub's own docs rather than recalled.** Three
    environments, and they use three different mechanisms - worth
    knowing before anyone tries to make one config serve all of them.

    **DEVELOPMENT - a Dev Container, and the route is DOCKER COMPOSE,
    not a Feature.** A community Feature exists
    (`ghcr.io/itsmechlark/features/postgresql:1`) but it is
    third-party; every template the spec maintainers publish uses
    compose with two services, `app` and `db`. Note there is NO plain
    `python-postgres` template - `ghcr.io/devcontainers/templates/
    postgres` IS the Python one, titled "Python 3 & PostgreSQL". Four
    details in that template worth carrying over deliberately:

    - It sets `network_mode: service:db` on the app service, so the
      app shares the database's network namespace and **Postgres is at
      `localhost:5432`, not `db:5432`**. Non-obvious, and the first
      thing to get wrong.
    - Port forwarding belongs in `devcontainer.json`'s `forwardPorts`,
      NOT compose's `ports` - the template says in as many words that
      adding `ports` there will not forward from a Codespace.
    - It uses `image: postgres:latest`, which we should PIN. The whole
      point of this exercise is testing against the engine production
      runs, and production is a specific Aurora PostgreSQL version.
    - It mounts the volume at `/var/lib/postgresql` where the
      conventional path is `/var/lib/postgresql/data`. A known wart in
      that template; do not copy it without thinking.

    **This repo has NO `.devcontainer/` at all today**, so that is a
    new file set rather than an edit.

    **CI - a GitHub Actions SERVICE CONTAINER, a different mechanism
    entirely**, and the choice between its two forms is decided by
    something `test.yml` already does. A job running INSIDE a
    container reaches the service by its label (`postgres:5432`); a
    job running DIRECTLY ON THE RUNNER must map the port (`ports: -
    5432:5432`) and connect via `localhost`. **`test.yml` runs
    directly on the runner**, so it is the second form. Either way the
    service needs `POSTGRES_PASSWORD` and a health check - `--health-cmd
    pg_isready --health-interval 10s --health-timeout 5s
    --health-retries 5` - or the suite starts before the database is
    accepting connections.

    **NON-PRODUCTION is a locally installed PostgreSQL running as the
    developer's own user, and PRODUCTION is AWS Aurora PostgreSQL**
    (Keith, 2026-09-26). Three environments, three ways of getting a
    connection, which is the argument for the connection details being
    configuration read at runtime rather than anything committed.

    **WHICH BREAKS SOMETHING CURRENTLY TRUE, and it should be said
    plainly:** `qa_tools/dbt_profiles/profiles.yml` is COMMITTED today,
    and its own header explains why - "no secrets, just a local file
    path, so this is committed rather than gitignored like a normal
    profiles.yml with credentials would be". With Postgres there are
    credentials, so that reasoning expires. Something has to own how
    they reach dbt, Soda and datacontract-cli in each of the three
    environments, and datacontract-cli has already shown its hand: it
    reads `DATACONTRACT_POSTGRES_USERNAME`/`_PASSWORD` from the
    environment rather than from the contract, and treats an empty
    password as unset.

    **A DEV CONTAINER CANNOT BE THE ONLY SUPPORTED PATH, and the
    reason is this project's own development environment.** Keith
    asked whether a Claude Code session could use one. Dev Containers
    are NOT VS Code only - the spec at containers.dev has a reference
    CLI (`@devcontainers/cli`, `devcontainer up`/`exec`) and Codespaces
    and JetBrains implement it.

    **A CLAUDE CODE CLOUD SESSION CANNOT RUN ONE BY DEFAULT, and the
    reason is a POLICY boundary rather than a missing capability -
    corrected 2026-09-26 the same evening, at Keith's own ask to verify
    it rather than assert it.** This entry first said flatly that there
    is no daemon and no socket, so there are no containers at all. The
    observation was right and the inference was not.

    - `docker info` fails - nothing is running.
    - Attempting to start a daemon is refused by Claude Code's own
      safety classifier. That is a deliberate sandbox policy, and its
      own message says a user can permit it if they choose to.
    - Anthropic's published docs settle it neither way. The
      "Limitations" section of the Claude Code on the web page names
      rate limits, time limits, repository authentication, platform
      restrictions and IP allowlisting, and says nothing about Docker
      or containers at all; it describes a session only as running in
      "an isolated, Anthropic-managed VM".

    So the accurate statement is: **no Docker in a default cloud
    session, by policy**.

    **AND THE PUBLIC RECORD SETTLES IT FURTHER (searched 2026-09-26 at
    Keith's own ask, after the docs turned out to be silent).** Two
    issues on `anthropics/claude-code` are exactly this, and BOTH ARE
    CLOSED:

    - **#53430, "[BUG] Docker daemon not started on web environment"**
      (opened 26 April 2026) - **closed as NOT PLANNED**. The reporter
      hit the same thing: the CLI is installed, the socket does not
      exist, and the daemon cannot be started. Closing it as not
      planned is the part that matters - it is a stated property of
      the platform rather than a defect awaiting a fix.
    - **#29515, "[FEATURE] Docker support in Claude Code web
      environment"** (opened 28 February 2026, labelled
      `area:claude-code-web`, `area:sandbox`, `platform:web`,
      `enhancement`) - also closed. It asked for exactly what would
      help here: `docker compose` to bring up Postgres and friends for
      integration tests inside one session.

    **A CONCRETE WARNING WORTH HAVING BEFORE SOMEBODY TRIES IT:**
    #53430 reports that attempting to start the daemon FROM A SETUP
    SCRIPT crashes the environment. The cloud environment's setup
    script is the obvious place to reach for, and it is the wrong
    lever.

    The workarounds people land on are the ones this entry already
    arrived at independently: run the service natively in the session,
    or run Claude Code locally where it has the host's daemon.

    **WHICH PARTLY RESTORES THE ORIGINAL INSTINCT, ON BETTER
    EVIDENCE.** This entry first asserted Docker was impossible, then
    corrected that to "withheld by default, and permittable" once the
    refusal turned out to be a policy decision. The public record
    lands between the two: Anthropic has been asked for this twice and
    declined both times, so treating it as a stable property of the
    platform IS justified - just for a documented reason rather than
    an assumed one.

    **THE CONCLUSION SURVIVES THE CORRECTION, and it is worth being
    clear WHY, because the reasoning changed underneath it.**
    Testcontainers needs a Docker daemon, so it would work in a Dev
    Container and on a GitHub runner and not in a default session
    here. "Impossible" became "withheld by default", which is a weaker
    claim, and a recommendation resting on it would have been weaker
    too. It rests on better ground instead: a test strategy that uses
    whatever Postgres is already reachable works in every one of the
    four environments, where one that insists on starting its own
    works in two and turns on a permission decision in the third.

    **The alternative is already proven here**: a natively installed
    PostgreSQL 16, started with `initdb` plus `pg_ctl` on a spare
    port, needing no container and no privileges. Everything measured
    in this entry was run against exactly that. So the test strategy
    should take a CONNECTION STRING for a Postgres that already
    exists, rather than assuming it can start one - the Dev Container
    supplies it in one environment, a service container in CI, a local
    install in another, and a session like this one starts its own.
    Same shape as `PLAYWRIGHT_CHROMIUM_PATH`, which this repo already
    uses for exactly this reason.

    **CAN GITHUB ACTIONS RUN DOCKER, OR IS IT RAW POSTGRES THERE TOO?
    BOTH - AND THAT DISSOLVES THE TENSION** (Keith's own question,
    2026-09-26; answered from the runner image's own manifest rather
    than from prose). All four of this repo's workflows use
    `ubuntu-latest`, which resolves to Ubuntu 24.04, and that image
    ships:

    - **Docker Server 28.0.4**, plus Compose 2.38.2 and Buildx - a
      REAL daemon. So Actions can absolutely run containers; a
      `services:` block IS a Docker container, and Testcontainers
      would work there too.
    - **PostgreSQL 16.15**, user `postgres`, and in the image's own
      words "PostgreSQL service is disabled by default. Use the
      following command as a part of your job to start the service:
      `sudo systemctl start postgresql.service`".

    So CI is unlike a Claude Code session in having Docker, and LIKE
    it in already having a PostgreSQL that only needs starting. Note
    how close the versions are: 16.15 on the runner against the 16.13
    this session's experiments ran on.

    **WHICH MAKES ONE STRATEGY WORK IN EVERY ENVIRONMENT.** The test
    suite takes a CONNECTION STRING and never starts anything: the Dev
    Container's compose `db` service supplies it, CI supplies it, a
    developer's local install supplies it, and a cloud session starts
    its own with `initdb`/`pg_ctl` as this one did. No Docker anywhere
    in the test path, and no environment-specific branch in the suite.

    **THE ONE REAL TRADE-OFF, named rather than glossed: PINNING.** A
    service container pins the exact image (`postgres:16.6`), where
    the runner's preinstalled PostgreSQL is whatever GitHub ships and
    moves when they refresh runner images. Since the entire point of
    this exercise is testing against the engine production runs, that
    matters. **Recommended shape: a pinned service container in CI,
    and a connection string everywhere including CI** - pinning where
    it counts, zero dependencies everywhere else, and a suite that
    cannot tell the difference. Worth knowing for the CI half: a job
    running directly on the runner, which `test.yml` does, reaches a
    service container through a mapped port on `localhost` rather than
    by its label.

    **AN OPEN GAP THIS SESSION CREATED, named rather than left as an
    IOU: DO THE LOAD-TIME FILE CHECKS REACH THE DASHBOARD?** The agreed
    shape above adds a small set of file-shape checks at load time, and
    NOTHING SAYS WHERE THEIR RESULTS GO. Keith spotted it. Today a
    failed load surfaces only in `mothman supply failures` - terminal
    only - so the dashboard shows a dataset quietly holding no data for
    that period with no explanation of why, which is the confusing
    quiet state this project has already spent real effort on.

    **Agreed answer (Keith, 2026-09-26): yes, they reach the dashboard,
    as THEIR OWN SCOPE, never folded into the data checks' status.** A
    red saying "the file had ragged rows" is a different KIND of claim
    from "14 records violate the contract", and merging them recreates
    the two-subjects confusion the load-first decision exists to
    resolve. The model already has both shapes to copy: `_cross-table`
    is a distinct scope under a collection (`REQ-QAC-037`), and
    `REQ-PIPE-079`'s `awaiting-supply`/`overdue-supply`/
    `awaiting-decision` reason codes are already about the SUPPLY
    rather than the data. The cost is that this becomes a FIFTH tool in
    `qa_results/`, so its checks need `check_id`s, lifecycle metadata
    and prose held to `docs/check-authoring-rules.md`. **To be scoped
    after the Aurora work** (Keith's own ordering).

    **THE SCOPER BATCH IS THEREFORE THREE THINGS, in this order**
    (agreed 2026-09-26). All three touch what a period resolves to and
    what the dashboard says about it, so they go to `delivery-scoper`
    together and through one sign-off session rather than three:

    1. **The PostgreSQL switch itself** - the prerequisite, since sprint
       11 waits on it and seven sprints wait on sprint 11. Its brief is
       this whole entry.
    2. **Load-time file checks reaching the dashboard** - the item
       above, as its own scope in `qa_results/` rather than folded into
       the data checks' status.
    3. **"INHERITED": a dataset that does not participate in a period at
       all, whose most recent supply is simply still current.** Found
       2026-09-26 while naming `REQ-PIPE-084`, from Keith's own
       question about datasets on the quarterly asset that deliver only
       once a year. **It is a real gap with real evidence.**
       `schedule.py`'s `delivery_months:` already SUBSETS a calendar -
       `cp-case-workers` is `[February, August]` today - and
       `not_expected_periods()` already carries a mandatory reason per
       such period. **But nothing downstream consumes either.**
       `period_schema.py`'s reason codes are only `missing-table`,
       `missing-reference-period` and `no-prior-period`, so an annual
       dataset's absence from Q3 currently surfaces as
       **`missing-table`** - indistinguishable from a real fault, when
       February's data is current and correct. `REQ-PIPE-079`'s
       unbuilt codes do not cover it either: `awaiting-supply`,
       `overdue-supply` and `awaiting-decision` are all about a supply
       that WAS expected. The word `inherited` is reserved for this and
       deliberately not spent on `REQ-PIPE-084` - see that
       requirement's own naming decision. Rejected folding it into 084,
       which would merge an automatic structural state with a
       deliberate human decision, the very distinction `REQ-DASH-085`
       exists to keep visible.

       **ITS SHAPE CHANGED THE SAME EVENING, and it is now SMALLER
       than when it was found.** Keith settled that a standing-in
       table is a REAL VIEW in the period schema rather than a
       resolution performed at read time (`REQ-PIPE-084`'s own
       decision), so every period schema holds a complete set, one
       object per dataset. **That means `missing-table` recovers its
       real meaning and this needs NO NEW REASON CODE** - an annual
       dataset standing on February HAS an object in Q3. What is left
       to specify is when the view is created and what it points at,
       not how to report its absence - **and that got
       settled too, 2026-09-26, from three questions Keith asked about
       how an operator actually works this.**

       - **INHERIT AND UN-INHERIT ARE REAL OPERATOR ACTIONS.** He was
         never describing derived state - "a TUI command to create one
         of these inherited VIEWS in a schema, and then an equivalent
         to, like, un-inherit". That is what dissolves the deadlock the
         hard-refuse rule would otherwise have: an automatic view is
         nothing you can "deal with first", where an un-inherit is.
       - **CREATION IS AUTOMATIC ONLY AT THE MOMENT A PERIOD SCHEMA IS
         BORN, and only where the schedule says the dataset does not
         participate** (his own qualifier, "ONLY when valid according to
         the cadence and periods we've set up", NARROWED further the
         same evening: "it feels like the automatic inheritance should
         only happen when the schema is first created... any other
         inheritance would be per-dataset and by operator command").
         **The narrowing is the better rule and it is worth saying why:
         "automatic where valid" applied CONTINUOUSLY has no trigger** -
         something would have to keep re-scanning for newly-valid
         inheritances, which is a background sweep with the same
         no-cron problem `REQ-PIPE-083` is stuck on. Pinned to schema
         birth it is one well-defined moment with complete information,
         and after that the schema changes only by deliberate act.
         That is the line that makes automation safe, because it means
         inheritance is never a judgement: a dataset that does not
         participate INHERITS, while one that participates and has not
         delivered is `awaiting-supply`, then overdue, then possibly
         SUBSTITUTED by a person. Different states, no overlap.
       - **TWO TRIGGERS, and his own instinct supplies the one that
         matters.** Automatic creation falls out naturally when a
         period schema is materialised, which is the first promotion
         into it. But a quarter where only annual datasets are due may
         see NO arrivals, so the schema would never exist and a
         consumer querying that period gets nothing. Hence his second
         idea, an explicit command to OPEN a period - which is not a
         convenience but the only thing covering that case.
       - **UN-INHERIT NEEDS NO SUPPRESSION FLAG - and the FIRST
         REASONING THIS ENTRY GAVE FOR THAT WAS WRONG, corrected here
         within the hour.** It first said the next automatic pass would
         re-inherit the periods against the previous real supply. Under
         the narrowed rule above THERE IS NO NEXT PASS: automatic
         creation happens once, at schema birth, and these schemas
         already exist. The conclusion survives on better ground -
         nothing re-creates the view, so there is nothing to suppress -
         but the consequence is different and is real WORK rather than
         self-healing. Un-inherit the dependent periods, the withdrawal
         succeeds, and then the operator RE-INHERITS each one by hand,
         pointing at the previous real supply. The period that actually
         owned the withdrawn supply correctly becomes overdue on its
         own. More toil than the self-healing story, and more honest:
         they chose to un-inherit, so they choose what replaces it.
       - **WHAT LOOKED LIKE A THIRD STATE AT SCHEMA BIRTH IS ACTUALLY A
         MISSING LIFECYCLE STAGE OF A DATASET** (Keith, 2026-09-26, and
         his reframing is much better than the edge case this entry was
         about to name). The case raised was a non-participating dataset
         with NO earlier real supply to inherit from - a newly-added
         annual dataset whose first February has not happened. His first
         answer was the practical one and stands as the rule: **you
         would not add it to config until you knew a supply was about to
         arrive**, because config is the statement of what is OWED.
         Asked what should happen if you did anyway, he considered "red
         and no data" and then landed somewhere better: **the
         `placeholder:` route, "or something like it, that maps to
         operational reality where we'd have sample data to start
         building and testing QA against before we'd agreed a supply".**

         **That is a PRE-AGREEMENT STAGE, and nothing in this model has
         one.** You get sample data from a prospective supplier, you
         author checks against it, you run QA to develop those checks -
         and there is no agreed cadence, so there are no slots, no
         lateness, no overdue, no substitution and no inheritance,
         because nothing is owed yet. None of that machinery applies. It
         is a property of the DATASET's lifecycle rather than a state of
         a period, which is why trying to express it as a period-level
         reason code kept feeling wrong.

         **IT IS NOT THE SAME AS ONE-OFF EXTRACTIONS - this session
         collapsed the two and Keith corrected it.** The claim was that
         a pre-agreement dataset and `CLAUDE.md`'s coming fourth asset
         shape ("QA of one-off data extractions for individual projects,
         which has supplies but no cadence at all") were one concept in
         two guises. **"Supplies but no cadence" is true of both and is
         a SURFACE feature; it is not what distinguishes them.** Keith's
         own distinction:

         | | Sample / pre-agreement | One-off extraction |
         |---|---|---|
         | Where the data lives | a `sample` schema IN THE WAREHOUSE | pointed at ON DISK |
         | Has a future | graduates into a real dataset | done once, never graduates |
         | What the QA is for | developing the checks | a verdict on the artifact |

         **AND THE `sample` SCHEMA EARNS ITS PLACE FOR A REASON BEYOND
         STORAGE: it makes "do not factor this into anything"
         STRUCTURAL rather than a flag.** Nothing in the period
         machinery looks at `sample`, so no rollup, status calculation
         or lateness check has to remember to skip it - exclusion holds
         by construction. Same reasoning as `qa_results/`'s reserved
         `_raw`/`_cross-table` scopes and as `delivery_boundary`
         refusing to default: build the guarantee into the shape rather
         than leaving a rule to hold in mind. It also means the
         warehouse has FOUR kinds of schema, not three - `staging`,
         `rejected`, the period schemas, and `sample`.

         **SETTLED (Keith, 2026-09-26): SAMPLE QA IS COMMITTED TO THE
         REPO, IN ITS OWN TOP-LEVEL TREE, AND NEVER IN `qa_results/`.**
         Not in `qa_results/` for his own reason - "that pollutes the
         results of actual data we expected to get through the refresh
         process". In the repo because CHECK DEVELOPMENT IS REAL WORK:
         when a dataset graduates you want evidence of what those checks
         did before any real supply arrived, and more than one person
         may work on them.

         **A SEPARATE TOP-LEVEL TREE rather than a reserved scope inside
         `qa_results/`**, mirroring that tree's own
         agency/collection/dataset layout. The argument is the one Keith
         had just applied to the `sample` SCHEMA, and it holds
         identically here: a separate tree makes pollution
         STRUCTURALLY IMPOSSIBLE, where a reserved scope would put
         sample results inside the very tree the dashboard builds from
         and leave every reader having to remember to skip them - the
         flag-not-structure problem. Nothing that reads `qa_results/`
         changes at all. It also gives the warehouse and the repo the
         same shape: a `sample` schema over there, a sample tree over
         here. Rejected the reserved-scope route even though its
         machinery already exists and is proven (`_raw`,
         `_cross-table`, and a hierarchy gate that already refuses a
         leading underscore as a dataset id) - those are genuinely part
         of a RUN's results, and sample QA is not. **The tree's NAME is
         not fixed** - `qa_sample/` is this session's suggestion only,
         and this project has been bitten by names before.

         **SAMPLE RESULTS SURVIVE GRADUATION** (Keith, same
         conversation): they stay as the record of what the checks did
         before any real supply existed, which is what an auditor or a
         new team member would want. Costs only space, and neither tree
         shrinks anyway.

         **THE PRECEDENT KEITH NAMED IS REAL AND WORTH COPYING.**
         `contract/people.yaml` already carries `placeholder: true` for
         a row that has to exist before the real thing does - marked
         explicitly rather than left ambiguous, and barred from acting
         or being assigned. Exactly the same problem, already solved
         once in this repo.

         **NOT YET SCOPED, and deliberately not designed further
         tonight.** What it needs at minimum: a dataset may exist
         without a calendar; its supplies may be QA'd without being
         filed to a period; the dashboard says plainly that it is in
         development rather than green-and-good or red; and there is a
         graduation - the moment it gains a calendar and starts owing
         supplies. Whether it joins the three-item scoper batch or goes
         with the project-extraction asset shape is Keith's call.
       - **AND THE OPERATION COUNT IS NOW SEVEN, not four.** Promote,
         reject, demote, re-file, substitute, inherit, un-inherit.
         `REQ-GHUB-082` enumerates the first four by name across five
         criteria and knows nothing of the rest; recorded there as a
         decision rather than edited, so the widening happens once,
         alongside the decision-log rewrite it is already unsigned
         pending.

       **THE DEMOTION QUESTION IS ANSWERED, and the answer reversed
       Keith's own earlier position once the real behaviour was
       tested.** A PostgreSQL view binds to the OBJECT, not the name,
       so a demotion that moves the physical table out of its period
       schema takes the dependent view WITH it - verified on 16.13:
       `pg_get_viewdef` afterwards reads `FROM
       staging.cp_case_workers_v1` and the view still returns rows.
       A later period would therefore go on silently serving data
       somebody had just decided was not in effect. So "do nothing"
       was never neutral, and that is what changed the answer.
       **Demotion of a supply any later period stands on is REFUSED
       OUTRIGHT, naming the periods that block it**, and the operator
       deals with those first. Same shape as the engine's own
       behaviour, which already refuses to `DROP` a table a view
       depends on. Recorded on `REQ-PIPE-084` with the rejected
       alternatives and the general rule it rests on - a decision
       about one period must not change what another resolves to.

    **LOCKING THE ENGINE VERSION - what is actually achievable, checked
    rather than assumed (2026-09-26).**

    | Environment | Pinnable |
    |---|---|
    | Aurora (production) | the engine version you choose - THE ANCHOR |
    | CI service container | exactly, by image tag |
    | Dev Container | exactly, same image |
    | local non-prod install | no - whatever their package manager gives |
    | Claude Code cloud session | no - whatever the image shipped |

    Two of five pin exactly. **The major is ALREADY aligned** between
    the two that cannot be: this session has `postgresql-16` at
    **16.13**, the GitHub runner has **16.15**, both from Ubuntu
    24.04's own repository - same major, different point-in-time
    package snapshot. **The minor cannot be pinned in a cloud
    session**: Ubuntu's repo offers exactly one candidate at a time,
    and `apt.postgresql.org` - the PGDG repository that carries several
    minors - is BLOCKED by this session's egress policy. Even
    allow-listed it would decay, because PGDG drops old minors
    eventually.

    **So the approach is: declare a MAJOR, assert it, accept minor
    drift, and anchor on Aurora.**

    - Declare it in a committed file and GATE it - a check reading
      `current_setting('server_version_num')` that fails when the
      major disagrees. That turns "same version" from hope into an
      assertion. The precedent is this repo's own `.python-version`,
      added after a silent runner-versus-local divergence burned eight
      commits of red CI; identical failure mode.
    - Minor drift within a major is safe for what this design leans
      on. Catalogue-only `SET SCHEMA`, transactional DDL, schema
      resolution and concurrent writers are all major-version
      properties; minors are bug and security fixes.
    - **Anchor on Aurora, not on community PostgreSQL.** Aurora's
      available engine versions lag upstream, so the number is whatever
      Aurora offers and everything else follows it. Choosing 17 locally
      and finding Aurora on 16 is the avoidable mistake.
    - **Worth doing anyway: give CI a PINNED SERVICE CONTAINER rather
      than the runner's preinstalled PostgreSQL.** Then CI and the Dev
      Container are byte-identical and the cloud session is the only
      outlier, aligned on major and asserted.

    **AND THE ONE THAT IS NOT JUST ANOTHER ROW IN THAT TABLE: AURORA
    IS NOT VANILLA POSTGRESQL.** Different storage layer, its own
    divergences. Pinning "16.x" everywhere does NOT establish that
    Aurora 16 behaves identically, so it is a separate compatibility
    question rather than a version number to match.

    **AURORA, read 2026-09-26 from AWS's own docs.** Tip for whoever
    reads them next: every page serves a MARKDOWN version at the same
    URL with `.md` instead of `.html`, which parses cleanly where the
    rendered HTML does not. Also note `WebFetch` reported
    `docs.aws.amazon.com` as EGRESS_BLOCKED after Keith had
    allow-listed it - the stale-tool-check trap CLAUDE.md already
    warns about. A raw `curl` worked.

    **THE VERSION ANCHOR: AURORA POSTGRESQL 16.8 LTS, and one fact
    decides it.** Aurora designates long-term-support releases, and the
    current two are **PostgreSQL 17.7** (released 18 December 2025) and
    **PostgreSQL 16.8** (7 April 2025). LTS is built for exactly this
    agency's profile - AWS's own stated criteria are that you cannot
    afford downtime for upgrades, that your testing cycle per upgrade
    is long, and that current features suffice - and an LTS minor takes
    only critical stability and security fixes, patched about once a
    year. **Staying on one requires auto minor version upgrade to be
    DISABLED**, which is a setting, not a default.

    **Why 16.8 rather than 17.7**: Ubuntu 24.04 ships ONLY
    `postgresql-16` - verified, there is no `postgresql-17` package at
    all - and `apt.postgresql.org`, which carries other majors, is
    blocked by this session's egress policy. So anchoring on 17 would
    make the cloud session permanently a major behind, which destroys
    the alignment agreed above. Anchoring on 16.8 matches what the
    cloud session (16.13) and the GitHub runner (16.15) already have,
    and the Dev Container and CI pin `postgres:16.8` exactly. The
    counter-argument, recorded rather than waved off: 17 buys roughly
    another year of runway before end of life. If it is ever taken, the
    cloud-session mismatch becomes a testing inconvenience rather than
    a production problem - but it does end the all-aligned property.

    **DO NOT HARDCODE A VERSION FROM THE DOCS.** Availability is
    REGION-SPECIFIC, and AWS's own instruction is to query it:
    `aws rds describe-db-engine-versions --engine aurora-postgresql
    --query '*[].[EngineVersion]' --output text --region <region>`.
    Confirm 16.8 exists in the target region before committing to it.

    **AURORA HAS TWO VERSION NUMBERS**, which matters for the
    assertion agreed above: the PostgreSQL engine version, and an
    Aurora version from `aurora_version()`. They align closely from
    13.3 onward. Gate on `current_setting('server_version_num')`,
    which exists everywhere; **`aurora_version()` does NOT exist on
    vanilla PostgreSQL**, so a check must not call it unguarded.

    **THE MOST CONSEQUENTIAL DIVERGENCE IS NOT A FEATURE, IT IS THE
    TOPOLOGY: THE PRIMARY INSTANCE HANDLES ALL DDL AND DML, AND UP TO
    15 REPLICAS SERVE READ-ONLY TRAFFIC.** Map that onto this design
    and every write is on the writer - loading a supply, creating a
    per-run view schema, `ALTER TABLE ... SET SCHEMA` for promotion and
    demotion. The reader endpoint looks like free capacity for the
    CHECKS, and taking it would be a real hazard: the agreed shape is
    load THEN check, so a check served by a lagging replica can miss
    rows that were just loaded, or find the per-run view schema not yet
    there. **That is a FALSE GREEN, the direction this project has
    already been burned in.** So: everything goes to the cluster
    (writer) endpoint, and the reader endpoint is explicitly rejected
    as an optimisation rather than left as an obvious idea for somebody
    to try. Worth knowing alongside it: the cluster and reader
    endpoints survive failover where instance endpoints do not, and
    during a failover the reader endpoint may briefly point at the new
    primary.

    **NO QUOTA ON SCHEMAS OR TABLES.** Aurora's quotas are all
    account-level or cluster-level (clusters, instances, endpoints,
    parameter groups), and nothing limits schema or table COUNT. The
    size limit is a 32 TiB maximum table for Aurora PostgreSQL.

    **AND THE SCALE WORRY IS MEASURED AND DISMISSED - see the next
    section.** Correcting this entry's own first draft while I am here:
    it said a schema per period PER DATASET. It is not. `period_schema.py`'s
    own docstring says "in a real deployment one period schema holds
    Birth Registrations and Child Protection", so it is ONE SCHEMA PER
    PERIOD, shared across datasets. The pressure therefore comes from
    CADENCE rather than from dataset count: a quarterly asset needs 4
    period schemas a year whatever it holds, and a DAILY dataset needs
    365.

    **THOUSANDS OF PERIOD SCHEMAS COST NOTHING WORTH WORRYING ABOUT -
    MEASURED, not reasoned (2026-09-26, real PostgreSQL 16.13).** Built
    a decade of daily periods - **3,650 schemas, each with a table and
    its primary key**, 15,013 relations in total - and then measured
    what actually degrades:

    | | |
    |---|---|
    | creating all 3,650 schemas and tables | **11.4 s** |
    | counting them in `pg_namespace` | 2 ms |
    | `SELECT count(*) FROM information_schema.tables` | 18 ms |
    | `pg_tables` filtered to period schemas | 4 ms |
    | querying one period's own table | 0.5 ms |
    | `pg_dump` of the whole database | **3.5 s**, a 3 MB dump |
    | database size with ZERO rows in it | **94 MB, of which ~50 MB is catalogue** |

    So there is no cliff anywhere near this design's scale, and the only
    real cost is catalogue weight - roughly 14 KB per schema-plus-table
    before a single row exists. Worth re-measuring if a dataset ever
    needs a period per HOUR, but a decade of daily is fine.

    **A GENUINELY USEFUL ACCIDENT ALONG THE WAY: `max_locks_per_transaction`.**
    The first attempt created the schemas inside one `DO` block, which
    is ONE TRANSACTION, and it died after about 380 of them with `out
    of shared memory / You might need to increase
    max_locks_per_transaction`. Nothing to do with schema counts - it
    is a bound on how many objects a SINGLE TRANSACTION may touch. That
    matters here because promotion is transactional by design: six
    tables is nowhere near it, but any future "do the whole delivery in
    one transaction" idea at 30 datasets with several versions each
    should know the ceiling exists.

    **THE PREVIOUSLY-UNREAD AURORA TOPICS, now read.**

    - **THERE IS NO TRUE SUPERUSER.** `rds_superuser` is the most
      privileged role, created automatically and granted to the master
      user (`postgres` by default). Everything this design does -
      `CREATE SCHEMA`, `ALTER TABLE ... SET SCHEMA`, `CREATE VIEW`,
      `GRANT` - is within that. What is NOT is anything needing real
      superuser, and one of those is on our load path.
    - **THE LOADER MUST USE CLIENT-SIDE `COPY`, NOT A SERVER PATH.**
      Verified by experiment rather than cited: as a plain role,
      `COPY staging.t FROM '/path/file.csv'` fails with "permission
      denied to COPY from a file ... Only roles with privileges of the
      pg_read_server_files role may COPY from a file", while `\copy` /
      `COPY ... FROM STDIN` succeeds. On Aurora it is moot anyway,
      because there is no server filesystem to put a file on. So the
      DuckDB-reads-then-`COPY` path has to stream over the connection,
      which it does naturally.
    - **IAM DATABASE AUTHENTICATION IS A ROTATING PASSWORD, and that
      shapes the credential question this entry already raised.** The
      token IS the password, is at least ~1 KB and can be larger, and
      **has a lifetime of 15 minutes**. It is only used at connection
      time - "doesn't affect the session after it is established" - so
      long runs are fine, but every NEW connection needs a freshly
      minted token. dbt, Soda and datacontract-cli each open their own,
      so a static environment variable cannot serve them; something has
      to mint per connection. Also flagged by AWS: a driver or tool
      that truncates a ~1 KB password breaks authentication.
    - **`max_connections` VARIES BY DB INSTANCE CLASS** rather than
      being a fixed Aurora number, so it is a sizing decision. Relevant
      because 30 datasets checked in parallel, each tool opening its
      own connection, is a real concurrency figure to size against.
    - **SERVERLESS V2 FITS THIS WORKLOAD'S SHAPE.** It scales in
      half-ACU steps and can **pause to zero**, and AWS names
      development and testing explicitly as a use case with a low
      minimum capacity. A quarterly asset is idle for most of every
      quarter, so a provisioned instance sitting at idle between
      deliveries is the wrong shape and this is the right one.
    - **EXTENSIONS** are an allowlist published per Aurora version in
      the Release Notes guide rather than "install anything". Nothing
      in this design needs one today; worth a check before anything
      starts depending on one.

    **STILL GENUINELY UNREAD:** the specific extension list for 16.8,
    and Aurora's major-version support timeline (how long 16 remains
    available), which bears on the 16-versus-17 choice above.

    **AND AN OPEN QUESTION UPSTREAM OF ALL OF IT, raised 2026-09-26 at
    22:00 and DELIBERATELY NOT ANSWERED: WHY DOES THE REPOSITORY HOLD
    RESULTS OR DATA AT ALL?** Keith's own words, and he killed a running
    `delivery-scoper` mid-batch rather than let it draft twelve
    requirements on a premise this may overturn. That was the right
    call; the reading is not wasted, because #45 is unchanged as the
    brief.

    **WHAT SURFACED IT: a database is PER-ENVIRONMENT and git is
    SHARED.** Local dev has its own PostgreSQL, dev/UAT another, prod
    Aurora. So there is no single decision log - there is one per
    environment - while the committed export lives in a repository,
    which has no environment. Three hazards follow. Whose export gets
    committed, when a developer running locally would otherwise commit
    toy decisions over the real ones? Which environment's dashboard
    does one export path describe, when each asset is its own
    deployment with its own dashboard? And criterion 17 of
    `REQ-GHUB-082` gets a real job back, because an export genuinely
    can lag - the question becomes which database it lagged behind.

    **THE FOUR REASONS THE REPOSITORY HOLDS `qa_results/` TODAY, and
    they do not all survive PostgreSQL:**

    1. **The CI rule** - the dashboard is built by GitHub Actions, CI
       must not touch the warehouse, so whatever it renders must
       already be in files. **This is the load-bearing one.**
    2. **Permanence** - git on a public remote, readable in ten years
       with no infrastructure and no restore procedure.
    3. **Auditability with NO CREDENTIALS** - anyone can read the whole
       history with `git log`. A database needs access granted.
    4. **Zero infrastructure** - this PoC gets evaluated on other
       people's machines and today publishes a dashboard with no server
       at all.

    **REASON 1 IS REALLY A CHAIN, and seeing it as one is what opens
    the question:** the dashboard is a static site, so it is built by
    CI, so it must not touch the warehouse, so what it renders must be
    in files, so the files are committed. Which means the honest answer
    to "why does the repo hold data" is **because the publisher is
    GitHub Actions, and GitHub Actions is the wrong place to hold
    warehouse credentials.**

    **A THIRD OPTION NEITHER OF US HAD ON THE TABLE.** The rule Keith
    actually wrote is not "committed files are required" - it is that a
    pipeline must not be one accident away from being pointed at
    something real. **If the dashboard build ran INSIDE the environment
    rather than in GitHub Actions**, it could query PostgreSQL
    legitimately, produce the same static artifact, and NOTHING would
    need committing. The publisher moves to where the data already is.
    It would cost Thread A's "CI is the only publish path" as currently
    written, and the Pages deploy as currently wired. It would keep the
    static output, the snapshot archive, and no credentials in CI. And
    **it would make the per-environment problem vanish**, because each
    environment would build and publish its own dashboard from its own
    database - which is what "entirely separate instances, each with
    its own dashboard" already describes.

    **THE STRONGEST COUNTERWEIGHT IS REASON 3.** `git log` over a
    decision history is a genuinely good audit story that a database
    does not replicate - no credentials, no restore, no tooling.
    Reasons 2 and 4 matter too, and 4 matters specifically for the PoC
    being evaluated rather than for production.

    **WHAT IS AGREED BUT HELD PENDING THIS.** Six rewrites to
    `REQ-GHUB-082` were put to Keith and five approved: stop
    enumerating the operations (define the set once in criterion 1 so
    the next addition touches one criterion rather than five - the
    four-becomes-seven drift happened precisely because five criteria
    each carried a count); criterion 7 reports when the entry is
    COMMITTED rather than "on the push that carries it"; criterion 18's
    open question closes because one serialisation point makes it
    exact; criterion 27 records to the decision log rather than to the
    committed log; and NFR 2 loses its OFFLINE claim while keeping its
    real point, that the TUI needs no GitHub even though it now needs
    the database, so it stays the MORE AVAILABLE route on a network
    where a third-party domain may not be reachable. He also settled
    that `inherit` and `un-inherit` live elsewhere in the TUI rather
    than in criterion 14's queue, which is shaped for supplies awaiting
    a decision and has no entry for "Q3 has no view for
    cp-case-workers". **Criterion 17 is the one held**, because its
    correct wording depends entirely on the question above.

    **KEITH'S FIRST RESPONSE, 2026-09-26 22:15 - NOT A DECISION, and
    recorded as his position rather than as settled.** He is "happy to
    give up reason 3, and probably 2 too", and "open to having the
    dashboard build run inside the environment and NEVER in GitHub".
    What follows is the analysis he asked for in reply, not an agreed
    design.

    - **GIVING UP REASON 2 IS CHEAPER THAN IT LOOKS, because
      `dashboard/snapshots/*.html.gz` ALREADY DOES THAT JOB.** They are
      committed, self-contained and openable in ten years with nothing
      but a browser. So the durable-readable property survives even if
      `qa_results/` stops being committed - snapshots were always the
      mechanism for it, not `qa_results/`.
    - **THE MOVE IS PROBABLY REQUIRED ANYWAY RATHER THAN A COST.** In
      production this dashboard describes real data quality for two
      government agencies. Public GitHub Pages is almost certainly the
      wrong place for it, and it only works today because the data is
      synthetic. So the current Pages wiring is a PoC-only arrangement
      that was always going to need replacing.
    - **IT CASCADES FURTHER THAN THE DECISION LOG.** If the dashboard
      can query the database then `qa_results/` ITSELF stops needing to
      be committed. That touches `build_results_from_history.py` (which
      becomes "rebuild from the database"); **`changelog.py`'s
      git-history walk, which disappears ENTIRELY** - a straight win,
      since CLAUDE.md records it as a real performance bug and a
      database has actual timestamps rather than inferring them from
      commits; **`REQ-PIPE-074` criterion 13**, "readable by the
      dashboard build with no access to anything under `data/`", which
      becomes WRONG and is SIGNED; and the never-touch-data rule's own
      wording, which would become "the publisher runs where the data
      is, and GitHub never does" - same intent, different mechanism.
      **Retention also becomes possible**, where today `qa_results/`
      only grows and retention is explicitly out of scope because git
      cannot forget.
    - **WHAT GETS GENUINELY HARDER.** Hosting: Pages is free, zero-ops
      and HTTPS-included, where inside the environment you need S3 plus
      CloudFront or an internal server, which is infrastructure and
      possibly procurement. The real-browser render gate has to move
      with the build, so the environment needs Chromium. Build
      availability couples to the database - committed files always
      build, and Aurora Serverless v2's scale-to-zero is exactly what a
      quarterly asset would want. And evaluating the PoC on someone
      else's machine gets further away, though PostgreSQL already did
      that to the pipeline.
    - **WHAT GETS EASIER.** No committed-results tree to keep
      consistent, no git walking, **the per-environment versus shared-git
      mismatch vanishes completely** - each environment builds and
      publishes its own dashboard from its own database, which is what
      "entirely separate instances, each with its own dashboard" already
      described - and "CI is the only publish path" stops needing to be
      a RULE, because publishing becomes a pipeline step where the data
      lives.
    - **WHAT IS ACTUALLY LOST:** `git log` and `git diff` over QA
      history, which he has said he will give up, and the public
      dashboard, which production probably does not want.

    **ALL FOUR "HARDER" ITEMS ANSWERED (Keith, 2026-09-26 22:20), so
    none of them blocks this.** Hosting: in production it is private
    GitHub Pages on GitHub Enterprise, or an S3 static site behind a
    security/auth layer, or dumped into SharePoint - and for the PoC he
    is happy with public Pages as it stands. Chromium for the render
    gate: built into the requirements and `pyproject.toml`. Build
    availability coupling to a paused database: fine. Evaluation on
    someone else's machine: they run their own local or dockerised
    PostgreSQL.

    **YES, `qa_results/` NEEDS AN EQUIVALENT IN THE DATABASE (Keith's
    own question).** What it holds today is deliberately two things side
    by side - `raw_output`, each tool's native payload, and `verified`,
    the resolved dashboard-ready check records - plus the `dataset_stats`
    and `tables_read` pseudo-tools and `run_by`/`run_timestamp`. That
    split maps cleanly onto columns for `verified` and JSONB for
    `raw_output`, and normalising `verified` buys what a file tree
    cannot do: "every failure of this check over two years" becomes a
    `WHERE` clause instead of the tree walk `qa_results_reader.py` does
    today. **The exact schema is deliberately NOT settled** - Keith's
    call was to let the scoper put the options properly rather than
    decide it cold.

    **WHAT STAYS IN THE REPOSITORY EITHER WAY:** code,
    `contract/*.yaml`, the hand-authored check definitions (dbt `meta:`,
    Soda `attributes:`, the ODCS `customProperties:`), `plans/*.md`,
    `CHANGELOG.yaml`, and `dashboard/snapshots/*.html.gz`. The build
    still needs a checkout. What leaves is `qa_results/` and the
    decision-log export, and nothing else. One incidental win:
    `build_results_from_history.py` exists as a SECOND code path
    reproducing the live run's output, verified byte-identical - with a
    database the run writes and the reader reads, so the duplication
    that needed verifying largely stops existing.

    **ONE DATABASE WITH ROLES FOR ISOLATION, NOT A SEPARATE METADATA
    DATABASE (Keith, 2026-09-26, and he got there by pushing back on an
    argument this session had overstated).** The claim made first was
    that a separate metadata database means the dashboard build's
    credentials "literally cannot" read supply data. **That was
    overstated - it is a GRANT, not a wall.** Keith's push: "is there
    really much protection when an automated pipeline will need a lambda
    that triggers when a file arrives and writes that to the database?"
    Correct, and the honest reframing is that what separation buys is
    LEAST PRIVILEGE PER COMPONENT rather than isolation of the data -
    the loader must have supply-write credentials, and that does not
    weaken the publisher's lack of them. **But the same least-privilege
    outcome is available from a ROLE in one database**, so a second
    database adds only that a coarse boundary is harder to misconfigure
    than a fine one, which is real (Postgres grants are fiddly - default
    privileges, the `PUBLIC` schema, role inheritance) and modest.
    **Against it is something concrete gained hours earlier:**
    `REQ-PIPE-075` criterion 9's ordering rule collapsed into a single
    transaction precisely because the log and the tables share a
    database, and a separate metadata database hands that rule back.
    Load-bearing cost against a modest benefit, so: one database, its
    own schema for metadata, a role scoped to it.

    **AND A REQUIREMENT-SHAPED GAP NOTHING OWNS: ENVIRONMENT
    AWARENESS** (Keith's own question, 2026-09-26: an operator doing
    local dev against their own PostgreSQL versus being hooked into
    dev, non-prod or prod Aurora). It is more than a connection string,
    and FOUR things need it. The connection details, trivially. SAFETY,
    because an operator promoting or demoting must know whether they are
    touching prod, which deserves different friction from local. THE
    DASHBOARD MUST SAY WHICH ENVIRONMENT IT SHOWS, or a screenshot of
    dev QA is indistinguishable from prod QA - the kind of thing that
    ends up in a briefing. And the version assertion agreed above
    (`current_setting('server_version_num')`) is per-environment by
    definition.

    **THE SHARP PART IS THE DEFAULT, and this project already has the
    answer to that shape.** Defaulting to prod invites a fat-fingered
    real change; defaulting to local is WORSE, because an operator runs
    what they believe is a real operation and nothing tells them it went
    nowhere. `delivery_boundary.py` treats a source stating nothing as a
    FAILURE rather than a default, and `git_identity.py` hard-errors on
    an unset identity rather than substituting a placeholder. Same
    reasoning: **no default environment, and an unstated one is an
    error.** `mothman` is the single entry point, so that is where it
    belongs, with prod requiring something more deliberate than the
    others. Worth considering alongside it: the decision log carrying
    the environment on each entry - belt-and-braces where each
    environment has its own database, but it makes a misrouted decision
    visible rather than silent.

    **SETTLED 2026-09-26, and earlier than planned: THE DECISION LOG
    LIVES IN THE DATABASE, WITH A COMMITTED EXPORT.** Keith's original
    sequencing was Postgres first and this question second, on the
    grounds that DuckDB could not exercise the properties it turns on.
    An evening of real measurement removed that reason, and the
    question turned out to need answering BEFORE the scoper rather than
    before the build: the switch's requirements will describe "the
    warehouse", and whether the log is inside that is a scope boundary
    a scoper cannot draw for itself.

    **WHAT DECIDED IT: the log has two consumers with different needs,
    and one artifact was never going to serve both.** The SYSTEM,
    deciding what is promoted, needs atomicity and currency - a
    database wins outright, because judging permissibility and
    appending become one act. The AUDIT TRAIL - "why is this supply in
    Q3", asked a year later, possibly by somebody external - needs
    permanence and readability WITHOUT CREDENTIALS, and survival of the
    database being restored from backup; files win outright. So
    Postgres is the operational system of record and whatever writes it
    also exports the full history to committed files, which the
    dashboard reads and which stand as the audit record. Same shape as
    `dataset_stats.json`: compute where the connection legitimately is,
    commit the conclusion.

    Rejected keeping committed files as the system of record, which is
    simpler and offline-capable but leaves `REQ-GHUB-082` criterion
    18's ambiguity needing one of four unsatisfying workarounds.
    Rejected a database-only log with the dashboard reading it, which
    reverses the never-touch-data rule Keith had reaffirmed hours
    earlier and makes history die with the database.

    **THE OFFLINE PROMISE IS DROPPED, DELIBERATELY** (Keith, same
    conversation): no database, no decision. His reasoning is sound -
    a filing decision acts on the warehouse, and in production the
    engineer is inside the network where Aurora lives, so Aurora is
    plausibly MORE reachable than GitHub. Rejected queueing a decision
    locally and applying it on reconnect, which is the
    pending-until-it-lands workaround under another name and carries
    the same "not final until it lands" property.

    **WHAT THIS BREAKS OR CHANGES, enumerated now rather than
    discovered one at a time.** The three `REQ-PIPE-074` items are
    SETTLED as of 2026-09-28; everything about `REQ-GHUB-082` below is
    still live, and 082 is still unsigned.

    **THE THREE 074 ITEMS, settled by `REQ-PIPE-091` being built
    (2026-09-28), and the resolution is not the one this block
    predicted.** All three turned on the repository holding a DERIVED
    EXPORT of the log beside the database. There is no export. Keith's
    own line on 2026-09-27 - "a build may read recorded QA results,
    never actual data, and never anything else" - moved the rule
    instead, so the dashboard build reads the database over a
    least-privilege grant and the repository holds nothing. That makes
    all three questions disappear rather than get answered: criterion 11
    is superseded outright and says so in the register, criterion 1's
    "second record" worry cannot arise because there is no second
    record, and one-file-per-decision is superseded as criterion 14. The
    scale property it was protecting survives as `REQ-PIPE-091`
    criterion 11, met by an index on `(dataset_id, effective_at, id)`.

    Keith approved the amendment on 2026-09-27, which is what this block
    asked for ("074 is SIGNED, so this needs Keith's eyes") - note that
    074 was in fact NEVER signed, which its own open questions now
    record along with what status it should carry.

    **AND THE IMPLIED NEW REQUIREMENT AT THE END OF THIS LIST IS NOT
    NEEDED.** It was for the export. There is none.
    - **`REQ-GHUB-082` criterion 18's open question RESOLVES.** A
      database has one serialisation point, so "the instant its entry
      is appended" is unambiguous and the four workarounds are moot.
      This was one of the two things holding 082 unsigned.
    - **`REQ-GHUB-082` criterion 26 BREAKS.** It says the TUI writes to
      the committed log alone and never calls GitHub, "so that a
      decision can be taken with no network". The first half survives
      in spirit - the TUI still must not call GitHub - but it now
      writes to the DATABASE, and the offline justification is gone.
      Needs rewriting.
    - **`REQ-GHUB-082` NFR 2** claimed the TUI is the route that works
      with no network. Half true now: it still needs no GitHub, but it
      does need the database.
    - **`REQ-GHUB-082` criterion 7** gets SIMPLER and more immediate.
      It currently reports the outcome on the ticket "on the push that
      carries it"; the entry now reaches the shared log the moment the
      transaction commits, so the outbound comment can follow directly
      rather than waiting for a push.
    - **`REQ-GHUB-082` criterion 17** (say so when reading a
      non-current copy of the log) is moot OUTRIGHT as of 2026-09-28,
      not just for the database path: there is one copy and no export,
      so there is no non-current copy for anything to read.
    - **`REQ-PIPE-075` criterion 9** stays true and its mechanism
      collapses: "write the entry only after the tables are durably
      present" is automatic inside one transaction rather than an
      ordering rule to implement.
    - ~~**A NEW REQUIREMENT IS IMPLIED** and nothing owns it: the
      export itself.~~ **Struck 2026-09-28: there is no export** - see
      the note above the list. `REQ-PIPE-081`'s "as at T" is answered
      from the table directly, by `decision_log.promoted_into(...,
      as_at=...)`, which reads the instant a decision TOOK EFFECT rather
      than when it was recorded.
    **DONE 2026-10-12 (open-items audit):** REQ-PIPE-087 (built): PostgreSQL is the one warehouse engine; REQ-PIPE-146 and REQ-TEST-095 too.

46. **[done, 2026-09-27]** **[Pipeline & publishing]** Keith: stop encoding schema names - normalise them instead, and refuse a collision where the names are defined.

    Built the same night it was raised. `qa_run_run_5f_001` is now
    `qa_run_run_001` and `period_2026_2d_51_33` is `period_2026_q3`.

    **The reasoning lives on `REQ-PIPE-087`'s own `decisions:`** - four
    entries covering why the encoding existed, why it was the wrong
    trade, why a run id and a period name get DIFFERENT answers, and
    what dropping exact reversibility cost. Not repeated here, because
    the register is the permanent artifact and two copies can disagree.

    The one thing worth keeping in a plans file rather than a
    requirement, because it is about this repo's own tooling: the
    collision guard is `period_schema.collisions_in()`, wired into
    `mothman check`'s `schedule` gate, and it is what made deleting the
    encoding safe rather than merely tidier. Verified by removing the
    guard and confirming both new tests fail.

47. **[done, 2026-09-27]** **[Pipeline & publishing]** The idle-in-transaction lock, root-caused: every Soda scan leaked a backend, because Soda's own teardown closes an empty dict.

    Keith: "make sure that stuff that addresses the lock issue is
    robust. Like I don't want a hacky patch. I want something that
    resolves the root cause of the transaction being idle forever."

    **It is a real bug in Soda Core, and it is one line to see once you
    look in the right place.** `Scan.execute()` ends by calling
    `self._close()`, which calls
    `DataSourceManager.close_all_connections()`, which iterates
    `manager.connections` - and on this code path that dict is EMPTY.
    The live connection is held at
    `manager.data_sources[<name>].connection`. So the loop closes
    nothing, and every scan leaves one PostgreSQL backend open. Proven
    directly rather than inferred: a single scan takes the count of
    unlabelled backends from 0 to 1, and it survives `del scan` and
    `gc.collect()`.

    **Why a spare connection was not harmless.** Soda's connection is
    not autocommit, so the leaked backend sits `idle in transaction`
    holding ACCESS SHARE on every table the scan read. The
    orchestrator's own `DROP SCHEMA ... CASCADE` needs ACCESS EXCLUSIVE,
    queued behind it, and failed after thirty seconds. A pipeline over
    ~40 arrivals accumulated ~40 such backends.

    **How it was actually found, because the method transfers.** Four
    reproductions, each narrowing:
    1. `mothman pipeline run --collection bdm --sequential` failed the
       same way every time - so it was deterministic, not a flake.
    2. Sampling `pg_stat_activity` showed a sawtooth of unlabelled
       `idle in transaction` backends, which said "accumulating" but not
       who.
    3. `log_lock_waits = on` with `deadlock_timeout = '1s'` made
       PostgreSQL name the blocking PID itself, with no sampling race -
       this is the step that should come FIRST next time.
    4. The blocker had no `application_name`, so it could not be told
       from any other tool. Giving every connection this project opens
       one (`supply_db.connect(label=...)`) turned the next log line
       into an answer. That labelling is kept: it cost nothing and it is
       the difference between a four-reproduction hunt and reading one
       line.

    Matching the blocker's last query against the repo identified Soda
    exactly - it was `contract/bdm-birth-registrations-soda-checks.yml`
    line 520, verbatim.

    **The fix** is `qa_tools/common/soda_common.py`'s
    `close_scan_connections()`, called in a `finally` by both
    `run_soda_bdm.py` and `run_soda_cp.py`. It closes the connection
    through the object that actually owns it. That reaches into a
    private attribute, which is justified here because the connection
    exists only because we asked Soda to open it and the public API for
    closing it demonstrably does not work - but the guard against Soda
    changing its internals is not defensive code, it is
    `tests/test_soda_leaves_no_connection.py`, which asserts the
    OUTCOME. One of its tests pins the leak itself, so if a future Soda
    release fixes this the test fails and tells us the workaround can
    go, rather than it being carried forever unexamined.

    **Verified end to end**: the pipeline that had failed four times in
    a row completed with exit 0 and not one lock wait in PostgreSQL's
    log.

    **The timeouts stay, as a net rather than the fix** - `lock_timeout`
    turns an indefinite hang into a bounded, named error, which is worth
    having whatever else is true. Worth knowing separately, and NOT
    fixed here: `idle_in_transaction_session_timeout` is set on the test
    databases but is `0` on a real supply database, so that net has a
    hole in it in production. A server setting rather than repo state,
    so it belongs in deployment config.

    **One real gap left open, deliberately.** All four of our own
    long-lived `supply_db.connect()` call sites DO close (I briefly
    thought otherwise from too short a grep window), but they close on
    the happy path rather than in a `finally`, so an exception between
    open and close leaks the same way. Fixing it properly means
    re-indenting four long function bodies under `with`, which is not a
    4am change - it is small, real, and should be its own commit.

49. **[in-progress, 2026-09-27]** **[Pipeline & publishing]** Keith settled how the dashboard reaches Pages - and it moves the build, the issues sync and CI's own database all at once.

    His answer, 2026-09-27, to the one fork left over from the
    PostgreSQL switch: "a TUI and a CLI command here that rebuilds the
    dashboard based on what's in the current environment. That would go
    in, read results from the Postgres database and output the HTML
    file. That HTML file will know it came from this environment
    because we will have a list of environments and this will be
    provided to it... and it would then be pushed up into the GitHub
    Pages environment from here. And I guess as part of that, we'd also
    do the writing to GitHub issues as well. So I guess we're dropping
    that out of GitHub Actions. CI still runs, obviously. It would run
    on its own database. But it's spun up just for CI purposes,
    populated just for that CI run."

    **The chain, in dependency order**, because only the first two are
    safe on their own:
    1. Environments: a declared list, and each deployment saying which
       it is. **BUILT** - see below.
    2. QA results into the database (`REQ-PIPE-089`). Nothing else can
       start: the build reads committed `qa_results/` files today, so
       "read results from the Postgres database" has nothing to read.
    3. The dashboard build reads the database instead of the files.
    4. `mothman dashboard publish` - build, then push to Pages from
       here.
    5. The GitHub issues sync moves out of Actions alongside it.
    6. `deploy-pages.yml` stops building, and `qa_results/` comes out of
       the repository.

    **Step 6 removes the only working publish path**, so it goes last
    and in the same change that proves its replacement, rather than
    leaving a window where a push updates nothing.

    **Step 1 landed 2026-09-27.** `contract/environments.yaml` declares
    the list; `MOTHMAN_ENVIRONMENT` says which one this is;
    `qa_tools/common/environments.py` reads both and `mothman env
    list`/`current` show them.

    The split is the decision worth recording, and it follows this
    repo's own configuration-not-state rule rather than being invented:
    the LIST is configuration (same for everyone, reviewed, committed);
    WHICH ONE YOU ARE is a property of one deployment, so it sits in an
    environment variable beside the DSN. Keith offered either "a file or
    a gitignored config file". Both alternatives lose something -
    committing the answer commits one deployment's identity for
    everybody, and gitignoring the list stops the set of valid
    environments being reviewed, so a typo becomes a new environment
    rather than an error.

    Refusals rather than defaults, and this is the part that matters
    once something irreversible hangs off it: unset is an error, not
    "local" - a production build silently labelled as somebody's laptop
    is exactly the artifact this exists to prevent. A name not on the
    list is refused. Two environments claiming `publishes: true` is
    refused, because they would race to overwrite one dashboard.

48. **[done, 2026-09-27]** **[Testing & dev tooling]** A real command that takes a fresh checkout to a populated, QA'd warehouse - plus the SessionStart hook that was `plans/tooling.md` #11.

    Keith: "we have a way to generate the synth data and run a command
    to populate the warehouse with something with QA checks - the stuff
    we're doing now through tests, but doing it at startup or when a
    human chooses to run a command, via the TUI." Both entry points,
    one implementation, and he chose that shape explicitly.

    `qa_tools/common/bootstrap.py` is the implementation;
    `mothman pipeline bootstrap` and the TUI's own main-menu entry both
    call it. It lives in `qa_tools/common/` rather than `cli/` so the
    startup path and the human path cannot drift.

    **Idempotent by asking the DATABASE, not a marker file.** A marker
    survives a database that was dropped, and then the one command whose
    job is to guarantee data is the one confidently doing nothing. A
    second run takes 1.7 seconds and says how many staged tables it
    found, with `--force` named in the message so the next person does
    not work it out by hand. Verified against a genuinely empty
    database: populated 43 staged tables and 3,359 real check results
    from nothing.

    **The hook does NOT populate, and that is the judgement call.**
    Bootstrap takes minutes over both collections; a session start that
    blocks that long is one people disable, and then none of the rest of
    the setup runs either. So `.claude/hooks/session-start.sh` makes the
    environment ready in a few seconds and REPORTS whether there is data,
    naming the command. It covers dbt_utils, node modules, Chromium, and
    the two DSNs via `$CLAUDE_ENV_FILE`.

    **It also fixes the thing that actually kept biting.** PostgreSQL is
    the one item on that list that is a SERVER rather than a build
    artifact, and it does not survive the container - this session
    restarted it three times, and the first time the ROLE was gone too,
    which PostgreSQL reports as "password authentication failed". The
    hook starts the cluster and creates the role and database if they
    are missing.

    Still open, and deliberately not done here: whether CI should call
    bootstrap. Under Keith's 2026-09-27 rule GitHub Actions never reaches
    a database, and once the dashboard build moves out of Actions the
    only database CI needs is the per-worker one `conftest.py` already
    creates - so there may be nothing for bootstrap to do there. Worth
    confirming when the publishing move lands rather than wiring it
    speculatively.

50. **[todo, 2026-09-27]** **[Pipeline & publishing]** Now that an environment decides which database a run writes to, nothing stops locally-messed-with synthetic data reaching a real one.

    Keith's own ask, 2026-09-27, in his words: "I wouldn't want synth
    data that people were messing around with locally to get to
    production or, you know, maybe even non-production. So I think
    there should be some extra gate checks somewhere. I don't know if
    they're like extra confirmation prompts in the TUI and CLI or if
    it's a hard gate we can set." Explicitly put on the agenda for
    after the current loop (REQ-PIPE-089 and the publish chain),
    rather than started now.

    **Why it is newly real rather than newly noticed.** Until
    REQ-PIPE-087 the warehouse was a file in the working tree, so
    "which database am I writing to" had exactly one answer and
    getting it wrong was not possible. It is now an environment
    variable, `contract/environments.yaml` names three environments,
    and `mothman pipeline bootstrap` will happily generate synthetic
    supplies into whichever one the shell happens to point at. The
    generator does not know, and nothing downstream asks.

    **The shape of the question, not an answer - this needs scoping
    with Keith before anything is built.** He named two mechanisms and
    was open about not knowing which fits:
    - A CONFIRMATION, which catches the careless case and not the
      automated one, and which people learn to click through.
    - A HARD GATE, which is the one that actually holds: an
      environment declares whether synthetic data may be written to
      it at all, and the generator refuses rather than asks. That
      makes it configuration rather than vigilance, which is this
      project's own stated preference everywhere else.

    Worth carrying into the scoping: `contract/environments.yaml`
    already has a `publishes` flag, so a `synthetic_data_allowed`
    sibling is the obvious shape, and `environments.current()`
    already refuses when unset rather than defaulting - the same
    stance this would extend. Also worth deciding whether the gate
    belongs at GENERATION (refuse to generate), at STAGING (refuse to
    load a supply nothing received), or at both; and whether a run
    should record which environment produced it, so a wrong one is
    findable afterwards rather than only preventable beforehand.

    **SAY WHERE YOU ARE, everywhere, in colour** - Keith's own
    addition, 2026-09-27: "maybe having clear banners in the
    dashboard, CLI and TUI, showing what environment you're in, e.g.
    light blue for local dev, green for dev, orange for non-prod, red
    for prod."

    This is the other half of the same problem and arguably the half
    that does more work. A gate stops the action somebody was about
    to take; a banner stops them forming the intention. All three
    surfaces need it, and none has anything today - `mothman` reads
    `MOTHMAN_ENVIRONMENT` and says nothing about it, and a built
    dashboard looks identical whichever database it came from, which
    is exactly how a screenshot of sandbox data gets mistaken for
    production.

    Two things to settle when this is scoped, neither of them
    decided here:
    - **The colours name FOUR tiers and the config has THREE.**
      `contract/environments.yaml` today is `local`, `sandbox`,
      `production`; Keith's list is local dev / dev / non-prod /
      prod. So either the environment list grows to match a real
      deployment ladder, or the colour becomes a property each
      environment declares (a `tier:` or a literal `colour:`) rather
      than a mapping hard-coded per surface. The second is almost
      certainly right - it is the same reasoning that put `publishes`
      in the file rather than in code - but it is his call.
    - **Red has to survive being ordinary.** A banner that is always
      there stops being read, which is the same failure this project
      already names for per-dataset banners at thirty datasets. Worth
      asking whether prod should be the LOUD one and the rest quiet,
      rather than four equally-weighted stripes.

    Accessibility is a real constraint rather than a nicety here:
    colour alone cannot carry it, so each banner needs the
    environment's own label in text as well - which the config
    already has.

51. **[todo, 2026-09-27]** **[QA checks & contract]** Author and manage checks from the TUI, including scaffolding a new dataset's checks from default policies for its data types.

    Keith's own idea, 2026-09-27: "Allow the user to use the TUI to
    edit checks for whatever tools we end up keeping. Could include an
    initial 'scaffold up checks based on our default policies for data
    types [on] a new dataset' (or new columns on an existing
    dataset?) and then allow adding and editing and otherwise managing
    them from the TUI."

    **Why it is a bigger idea than it looks.** Adding a dataset today
    means hand-editing an ODCS contract, a SodaCL file, a dbt
    `schema.yml` and an Evidently dict - four files in three
    languages, each with its own way of saying "this column must not
    be null" - plus the hand-authored lifecycle metadata every check
    carries (`check_id`, `introduced_date`, `description`,
    `failure_indicates`) and the authoring rules in
    `docs/check-authoring-rules.md`. At two datasets that is a
    morning's work somebody does carefully. At thirty on the quarterly
    asset it is the thing that decides whether the asset gets
    onboarded at all.

    **The scaffolding half is the valuable half, and it is really a
    question about POLICY rather than about a UI.** "Default policies
    for data types" means the project can state, once, what it always
    wants: an identifier column gets uniqueness and not-null, a date
    gets a plausible range, a categorical gets an allowed-value set
    and drift, a free-text field gets length bounds and nothing else.
    That is a real artefact - a policy file - and it is worth having
    whether or not a TUI ever edits it, because it also answers "why
    does this dataset have no check on that column" with something
    better than nobody thought of it.

    **Three things to settle before building, none decided here:**
    - **What is authored and what is derived.** If the TUI writes
      SodaCL and dbt YAML, those files stop being hand-authored and
      become generated - which collides with them being the source of
      truth today, and with the lifecycle metadata living inside them.
      A policy file plus a generator, with the four tool files as
      OUTPUT, is a coherent answer; so is a TUI that edits the four
      files in place and never generates. Mixing them is the one
      option that will hurt.
    - **`check_id` is forever.** It keys committed history, so a
      scaffolder minting ids has to mint them the way a person would
      and never renumber. Related: `introduced_date` and `changelog`
      are a check's own lifecycle record, which a generator would have
      to preserve across regeneration rather than rewrite.
    - **"Whatever tools we end up keeping"** is Keith's own phrasing
      and worth taking literally - this is easier with fewer tools,
      and it may be a reason to decide that question first rather
      than scaffolding for four.

    Sits naturally alongside #50's environment work and after
    REQ-PIPE-089; not started.

57. **[done, 2026-10-12]** **[QA checks & contract]** The drift
    reference is the FIRST arrival ever, not the previous period - so
    the check measures distance from the beginning of history rather
    than change.

    Found while answering Keith's challenge on whether a relative
    volume check would be safer than the absolute band we have
    (`row_count` on `cp_clients`: warn < 300, fail < 100 or > 2000).
    Not part of that answer - a separate observation about the check
    itself, logged here rather than folded into a promotion argument
    it does not belong to.

    Both orchestrators pass `manifest[0]` as the Evidently reference -
    the first arrival in the recognised history - and deliberately
    NOT `run_evidently_cp.REFERENCE_RUN_ID`, the hardcoded literal
    that went stale every time the anchor date rolled forward. That
    fix was right for the bug it fixed. What it did not ask is
    whether the first arrival is the right reference at all.

    Over a PoC's twenty-odd runs it is fine. Over years it is a fixed
    anchor receding into the past, so a slowly-changing population
    drifts from it permanently: the check either sits red for ever,
    or its threshold gets widened until it says nothing. Neither is a
    drift check. And the thing it cannot see is the one drift
    actually exists to catch - a supply unlike the one BEFORE it,
    where the population has moved gradually and legitimately for
    three years.

    Worth scoping alongside `REQ-PIPE-079` (QA runs against the
    period a supply is filed to), which is what makes
    previous-period comparison possible at all. Not urgent, and
    explicitly NOT a promotion-safety measure - see the reasoning in
    this item's own opening paragraph for why I stopped claiming it
    was one.
    **DONE 2026-10-12 (open-items audit):** REQ-QAC-108 (built): drift and volume measure against the last PROMOTED supply.

60. **[todo, 2026-10-04]** **[Pipeline & publishing]** **Retention for
    superseded supplies (and probably the original delivery files).**
    Deferred from option A (REQ-PIPE-123's decisions, which name this
    entry; REQ-PIPE-118 made superseded per period). Superseded is now
    per period, so a retention decision applies to whole periods. Keith's
    shape: the data asset defines a period-level retention, overridable at
    collection or dataset level - "two years is fine for a quarterly
    supply, but isn't good enough for a dataset that only comes in once a
    year on the quarterly asset." Worth deciding then whether retention is
    expressed in TIME or in a NUMBER OF PERIODS (the latter adapts to each
    dataset's cadence by itself). Purge the data, keep the record - the
    receipt, QA results and decision entries - so history still reads; an
    archived copy rather than deletion ties into plans/supply-thoughts.md.
    Personal data kept indefinitely is the reason it matters.

61. **[todo, 2026-10-04]** **[Pipeline & publishing]** **A concurrency
    pass once the supply model settles: what happens when runs overlap.**
    Keith's ask, 2026-10-04, timed for "once we settle how all this works
    over the next week or two" - after the option A and period-closing
    batch is built, not before. Today the pipeline processes arrivals ONE
    AT A TIME (filing depends on what the previous arrival promoted), and
    the design so far quietly leans on that. Once arrivals are automated
    there may be several QA runs at once - across datasets, collections
    and agencies - plus people deciding things on the terminal and GitHub
    while runs are in flight. The pass should first decide WHETHER
    simultaneous runs are allowed at all (and at what grain: per dataset,
    per collection, per period), then walk the race conditions and
    oddities that follow. Already known to look at: two decisions'
    re-checks overlapping (REQ-PIPE-121 settles "newest cause wins, not
    last to finish", but nothing else has been checked that way); a file
    landing between a warning and its confirmation (REQ-PIPE-128 refuses
    and re-shows); a decision waiting on a running QA tool's lock
    (REQ-PIPE-129's lock timeout); the substitute-versus-displace race
    (129's stands_on lock); two arrivals for the same table and period
    being filed at once (REQ-PIPE-118's supersession by receipt instant
    assumes receipt order); cross-table checks reading a sibling that
    another run is mid-way through promoting; and owed re-checks
    (REQ-PIPE-120/121/140) being picked up by two runs at once. Worth a
    delivery-architect pass of its own when it comes up.

62. **[done, 2026-10-12]** **[Pipeline & publishing]** **A wider
    "did anything slip through" check after every run - maybe later.**
    Keith, 2026-10-04, choosing the NARROW reconciliation for the
    rewritten REQ-PIPE-115 ("let's do A and flag B in running thoughts
    as maybe something we do later"). 115's check compares each tool's
    SKIPPED checks against the "not evaluated" records it wrote - e.g.
    dbt left out 6 checks, so there must be exactly 6. The wider version
    would compare EVERY check the configuration says a run should
    produce (say 43) against everything recorded, verdict or not
    evaluated - catching a check that vanished for ANY reason (a tool
    quietly producing fewer results, a misconfigured check), not just
    the skip mechanism. Deferred because it has never been measured
    against real runs and could refuse good runs on day one for reasons
    nobody has met yet; worth doing once a clean run's real output has
    been measured.
    **DONE 2026-10-12 (open-items audit):** REQ-PIPE-188 (built): a run whose in-scope check has neither a result nor a not-evaluated record is refused.

64. **[todo, 2026-10-05]** **[Data generation]** **Walk through scenario injection
    with Keith - no scenario-only code paths.** Keith, after the TS-47
    explanation: once the file-check work (sprint 12) is finished, he
    wants to go through how scenario injection is designed, to check it
    works how he thinks it works, and to understand how it replicates
    what a human can do through the mothman TUI and CLI and what the
    rules do. His standing constraint, in his words: "I don't want any
    scenarios running through special code that only runs for
    scenarios. It should be running through the actual pipelines that
    the humans and the automated machines use."

    For the walkthrough, what exists today, stated plainly so it can be
    checked against that constraint rather than assumed to meet it:
    - ARRIVALS: an injection only changes what the generator WRITES - the
      files, their names and receipt instants. Recognition, filing, QA,
      promotion and the dashboard then treat them exactly as any other
      delivery; nothing downstream knows a scenario exists (REQ-GEN-044
      criteria 5 and 6).
    - PERSON DECISIONS (REQ-GEN-135): each scripted decision is raised
      through filing_decisions.apply(), the same function `mothman supply
      decide`, the TUI and the GitHub route call, with the same
      consequences check and the same refusals.
    - THE PARTS THAT ARE SCENARIO-ONLY, and the ones to look at hardest:
      (a) the Player hook in arrival_lifecycle.process_all(), which runs
      only when the batch replay passes a player - it decides WHEN a
      scripted decision is raised, between arrivals; (b)
      people.playback() and the synthetic actor, which exist only so a
      decision can be raised with no person behind it, refused on every
      other route; (c) generator-only placement rules (anchors,
      suppressed and quiet days). None of these computes a verdict,
      filing or promotion, but (a) and (b) are code the real pipeline
      carries only for scenarios, which is exactly what he wants
      examined.

    Pairs with REQ-GEN-183 to 186 (generating to the check rules, built
    2026-10-11, which was #63 here).

66. **[todo, 2026-10-05]** **[Testing & dev tooling]** **Bring a development
    database's schema forward in place.** Keith, 2026-10-05 evening: "happy
    for you to upgrade the database schema in place during development."
    Scoped that night to an agent's own dev and scratch databases, done by
    hand, with no code change - qa_store still refuses any older schema,
    per his "regenerate, never migrate" of the same morning (REQ-PIPE-144).
    The option he did not take that night, to scope later: a dev-only
    `mothman` command, or a synthetic-asset exception in qa_store, that
    applies the newer additive DDL and sets the version. It would save a
    ~27-minute rebuild per schema bump while a feature is developed. It
    stays refused for a reshape (anything below RESHAPED_AT) and for any
    non-synthetic asset. Pairs with the bootstrap speed work (REQ-PIPE-156 to 160, 188 to 192).

67. **[done, 2026-10-12]** **[Testing & dev tooling]** **Review every test:
    is it still needed, and is our testing guidance any good?** Keith,
    2026-10-06 morning, while a gate ran: "do a review of all of our tests
    and identify if they're still all required, because the gate is taking
    a long time." The full gate is about 15 minutes - 3,500 tests needing no
    deployment ~6.5 min, 292 deployment tests ~5.5 min (mostly real-browser),
    JS tests and validators ~1.5 min.

    HIS SHARPER POINT, the same conversation, and it is the first cut rather
    than the slow tests: "a lot of tests that don't actually test any code
    that is used in the real - it's just code that exists for running tests,
    and then tests that are actual code that is only ever being used by
    tests." And: "you're writing tests that are very defensive, and you have
    tests running against behaviour we haven't had in weeks because we
    replaced it. Which is pointless." Two examples written that very morning
    prove him right: one test asserts the old database-setting identity is
    no longer read, another that backlog.unprocessed no longer exists.

    SCOPED: aim FEWER, STRONGER tests (over gate time alone, or a hard
    target) - weak source-grep tests replaced by behaviour tests even where
    that costs time. Order of work:
    1. A call-graph pass: every function in qa_tools/, pipeline/, cli/,
       dashboard/ and generator/ whose ONLY callers are in tests/ - dead
       code kept alive by its tests; both go.
    2. A retired-behaviour pass: tests asserting something is absent,
       removed or no longer read, and tests that only grep the source.
    3. The testing GUIDANCE: CLAUDE.md's rules all lean towards adding a
       test (one per defect, a guard per incident) and say nothing about
       when a test should go. Draft wording - when to add one, what it must
       exercise (real entry points, not test-only code), when one is deleted
       (its behaviour is gone), and no "proving absence" tests - for Keith's
       approval word for word, as authoring standards are.
    4. Then the timing profile, taken from a gate run that happens anyway.
    Nothing is deleted without Keith's yes per item; a change that only
    makes a test cheaper while it proves the same thing can just be made.
    QUEUED with the bootstrap speed work (REQ-PIPE-188 to 192).

    A FOURTH CATEGORY, Keith the same morning, after a docs-only gate
    reported "190 passed": "how the hell do we have 190 tests just for our
    documentation?" They are tests of the PROCESS TOOLING that checks this
    project's own plans and requirements - the requirements validator 97
    (for 343 lines: nearly one test per field rule, three per field in
    places - required, empty string rejected, whitespace rejected), sprint
    state 49, the plans parser 19, the plans index 11, requirements.yaml's
    shape 10, `mothman plans` 4. None of it is the product. The review looks
    at internal process tooling as a category of its own: table-driven tests
    where one rule is tested many ways, and whether every rule earns its keep.

    **PASS 1 DONE, 2026-10-06 - product code whose only callers are tests.**
    A scan of every top-level function and class in qa_tools/, pipeline/,
    cli/, dashboard/, generator/, synthetic_data_generator/ and aws/ (1,632)
    for references outside tests/ - counting identifiers, so a name used by
    another module, the template or a workflow counts. 40 had none; 26 are
    click `*_command` functions, registered by decorator - false positives.
    THE 14 REAL ONES, each waiting on Keith's yes per item (nothing deleted):
    - NO REFERENCE AT ALL (dead outright): `qa_results_reader._datasets_in`,
      `supersession.is_superseded_schema`, `s3_arrival.local_uri` (written
      2026-10-06 for REQ-PIPE-152 and never used - delivery_log builds the
      `local:` URI inline).
    - ONLY TESTS CALL THEM (dead code kept alive by its tests):
      `asset_time.as_of_instant` (test_asset_time), `filing_queue.
      periods_needing_a_person` (test_filing_queue), `period_overlay.
      own_table_contested` (test_period_overlay), `period_tables.
      guard_disabled` (test_plain_base_names), `qa_store.cross_table_results`
      (3 test modules), `qa_store.history_for_check` (2), `qa_store.
      table_history` (1), `supply_db.run_id_of` (2), `supply_db.
      drop_run_schema` (2), `tables_read.undeclared_in_this_repo` (1).
    - TEST INFRASTRUCTURE LIVING IN PRODUCT CODE: `db_identity.mark_by_admin`,
      called only by tests/conftest.py to mark test databases - a candidate to
      MOVE to tests/ rather than delete.
    Not covered by this pass: methods inside classes, and functions reached
    only through other test-only functions (a second round once these go).
    **KEITH'S YES TO ALL THREE GROUPS, 2026-10-06; DONE THE SAME DAY.** The 13
    functions are deleted. Tests that existed only for one went with it; tests
    of real behaviour that merely used one as a convenience were kept and
    rewritten - `qa_store.results_for_run(..., scope=CROSS_TABLE_SCOPE)` for
    cross_table_results, the real `supply_db.drop_run_schemas` for cleanup,
    inline SQL for history_for_check, a test-local `_guard_disabled` for the
    guard helper, and the repo-configuration check that every mechanical
    cross-table check declares what it reads kept with its one-liner inlined.
    `mark_by_admin` moved into tests/conftest.py's `mark_test_database`.

    **PASS 2 CENSUS, 2026-10-11 evening** (a read-only agent read every
    candidate test; nothing edited). The full list, file::test by
    file::test with a recommendation each, is docs/test-review-pass2.md -
    working material for walking it with Keith, to be deleted once its
    items are decided. Totals if every recommendation were taken: about
    63 test functions deleted (of 4,641 collected), 40 weak tests replaced
    by behaviour tests, 13 data-boundary greps folded into one behaviour
    test (the dashboard-build readers run over the publisher role, which is
    already refused staging), about 75 process-tooling tests collapsed into
    about 12 tables keeping every case. Mostly strength, not gate time.
    CHECKED BY THE MAIN SESSION, and the reason to do this first: tests that
    PASS WHILE PROVING NOTHING. `test_staging_loads.py`'s
    `test_staging_happens_before_the_tools_fan_out` finds `build_all()` only
    in two stale docstrings (orchestrate_bdm.py line 25, orchestrate_cp.py
    line 17); `test_arrivals.py`'s
    `test_every_committed_dataset_stats_file_is_clean` walks `qa_results/`,
    which no longer exists, so it compares nothing. The agent names two more
    of the same kind (the e2e "compared nothing" floor counting qa_results/
    runs; a trial test satisfied by the word "transaction" in a docstring),
    both of Keith's named examples (backlog.unprocessed, the old
    database-settings identity) among about 20 absence tests, and tests that
    go red when work SUCCEEDS (the retired-check registries asserted
    empty). Nothing is deleted without Keith's yes per item.

    **WALKED WITH KEITH, 2026-10-12 morning - the false greens, DONE:** the
    three staging-order tests deleted, the other three rewritten as real
    checks (qa.dataset_stats in the deployment; the e2e floor from qa.run;
    the trial tidy-up by making its last delete fail), and the stale
    orchestrator docstrings rewritten. **THE REST WALKED THE SAME MORNING,
    every recommendation taken (Keith):** group A - delete the ~35
    memorials and trim 4, replace the 7 live-rule greps with behaviour
    tests, keep the ~11 that guard live rules; group B - replace the 31
    source greps with behaviour tests, delete 2, trim 1, keep the ~25
    architecture guards; the 13 data-boundary greps become ONE test running
    the dashboard build and its readers over the publisher role; groups C
    and D - delete the 12 duplicates and tautologies (including the sprint
    test that needs the real plan to hold a blocked and a todo sprint, and
    the two 'retired-check registry is empty' tests), collapse ~75
    validator tests into ~12 tables keeping every case, delete the 11
    proven-twice tests. Being done in three passes (deletions, replacements,
    the role test). Step 3 of this item - the testing GUIDANCE - APPROVED
    word for word by Keith the same morning and added to CLAUDE.md beside
    the bug-test rule.
    **DONE 2026-10-12 (open-items audit):** test review passes 1-3 (59860de, 45ca8cb, 03b62ef) and CLAUDE.md's 'A test earns its place' rules; a further pruning pass is parked as #86.

68. **[todo, 2026-10-06]** **[Pipeline & publishing, QA checks & contract]**
    **No custom code per dataset - everything in configuration, if we can.**
    Keith, 2026-10-06 13:47, prompted by the REQ-QAC-039 survey (hierarchy
    ids restated in ~70 places, a per-collection registry stated in five):
    his question back was why per-collection code can't read what it needs
    from `contract/data-asset.yaml`, and the aim behind it is that a dataset
    or collection is added by configuration alone, with no `qa_tools/<x>/`
    package, CLI module or dashboard builder written for it. Not scoped.
    **To talk through with him alongside the calendar group**
    (`plans/wider.md` #11, item 9) - his own placement, so do not raise it
    sooner and do not build towards it before then. Relevant prior art:
    `plans/publishing-and-history.md` item 6 (how many near-identical
    modules per dataset) and `plans/post-build-review.md` #36 (the survey,
    his answers so far). At the scale this PoC is for - ~30 datasets on one
    asset, a project-extraction shape with no cadence - this is likely the
    larger question REQ-QAC-039 is a symptom of.


69. **[done, 2026-10-12]** **[Pipeline & publishing, Data generation]**
    **Revisit REQ-PIPE-170 once the calendar groups are signed off, and slot
    its scenarios into the build.** Keith, 2026-10-08: "look at requirement
    170 once we've done with these groups, and have that slotted in as part
    of the experience to build this set of requirements." The gap it
    carries: TS-57..TS-63 (plans/supply-model.md, "Calendar corrections")
    need the generator to make a correction part way through the synthetic
    history and confirm it later, which it cannot do today, and REQ-PIPE-170
    leaves how to the builder. **When**: straight after group 3 (the undo
    tools, REQ-PIPE-161..166) is signed off, before the calendar batch's
    sprints are planned - so the scenario generation is a planned sprint
    step, not an afterthought at the end.
    **DONE 2026-10-12 (open-items audit):** REQ-PIPE-170 (built) with its scenarios, and the replay stages corrections (03cea18).

70. **[done, 2026-10-12]** **[Pipeline & publishing, Calendar]**
    **Three ways a period can be judged, and which one to reach for.**
    Keith, 2026-10-08, asking how REQ-PIPE-161 (excuse a late supply)
    differs from `not_expected` in the calendar - and whether an excuse
    should be written into the calendar YAML instead. Answer: no, it should
    not. Recorded here as the rule of thumb to apply when someone asks
    which route a case belongs on.

    - **Calendar wrong** (a date or period was mistyped, or the agreement
      itself is not what was meant): a declared correction (REQ-PIPE-111),
      through the calendar file, approved in review, confirmed by the asset
      manager (REQ-PIPE-170). The verdicts and filings it changes are
      re-judged. This is the only route that changes a past verdict.
    - **Calendar right, nothing owed** (a period nobody supplies by design,
      e.g. Christmas): `not_expected` in the calendar, written in advance as
      part of the agreement. The period reads quiet grey and is never late.
      It is configuration, so it is locked once it can govern a filing like
      any other frozen item.
    - **Calendar right, supply late, and we forgive it** (an outage, an
      agreed delay): an excuse (REQ-PIPE-161), a decision-log entry in the
      database with a reason. The verdict stays "late" and reads "late,
      excused". Nothing is re-judged.

    Why an excuse does not go in the YAML: it is a person's judgement about
    one supply, which is state, not configuration. Writing it into the
    calendar would make a supplier's outage a change to the agreement, need
    a correction and an approver for something that is not an error, and
    re-judge a verdict that was right. It would also mix two concerns the
    freeze rule keeps apart - what was agreed, and what happened.

    The cost, stated plainly: every entry point that judges a supply reads
    BOTH sources - the calendar for what was agreed and the decision log for
    what a person has since recorded (excuses, kept supplies, holds). That
    is two inputs to remember, and it is the reason REQ-PIPE-168 records the
    resolved inputs and the agreement that judged each verdict, so a reader
    can see which one a verdict leaned on. Worth checking against the
    scenarios when the calendar build is planned (plans/supply-model.md's
    "Calendar corrections").
    **DONE 2026-10-12 (open-items audit):** a reference rule, now carried by REQ-PIPE-111, 161 and 170 (all built).

71. **[todo, 2026-10-08]** **[Pipeline & publishing, Security]**
    **Letting someone use a GUI client locally when their code can differ from
    what is running live.** Keith, 2026-10-08, while signing off the decision
    to run filing placements inline (REQ-PIPE-163): a person may point a GUI
    client on their own machine at the live supply database, but their local
    checkout of the code - the checks, the filing rule, the calendar - may not
    match what the pipeline is running. A decision recorded from a stale
    checkout would be judged by rules nobody is running. Not scoped. Questions
    to settle with him first: is a local GUI client a read path only, or can
    it write decisions; should a decision carry the code version it was made
    under and refuse when the live version differs; and what a read through a
    client may see, given the staging schemas are supply rows and not for any
    route but the orchestrator (CLAUDE.md, the "build may read recorded QA
    results, never actual data" rule). Related: plans/aws.md #4 (where the
    connection string lives).

    **WIDENED 2026-10-13 - where does QA RUN at all?** Priority: this week,
    worked together (Keith, 2026-10-13). REQ-PIPE-193 exposed it: a
    terminal decision runs QA "while the person waits", on that person's
    machine, with that person's code. Keith: "people can make code changes
    locally that would not have been accepted but could change production."
    Options he named:
    - the TUI cannot be run from a checkout at all - only from somewhere
      tied to production code;
    - or, run locally, protections make sure the code is unchanged - the
      latest production code checked out, nothing modified;
    - his lean for HOW people get it: "letting them run it ... as a
      standalone executable, so they can't change the code. So I guess that
      means sort of packaging it in Python."
    And for WHERE QA runs, his lean right now: "only in the processing
    loop" - a person's decision is recorded from the terminal, and the QA
    run and the gate that follow it happen in the processing pass, never on
    the person's machine. Not for REQ-PIPE-193, which keeps going as signed
    (its criterion 15 runs QA while the person waits); if this lands as he
    leans, that criterion moves to the pass. See #90 for the other half -
    protecting the loop while it runs.

73. **[todo, 2026-10-08]** **[Pipeline & publishing, QA checks & contract]**
    **Recalling a broad class of checks, and re-running everything it touches.**
    Keith, 2026-10-08, after rejecting an automatic fingerprint of tool and
    code versions in each check's hash (it would make every dbt, Soda or
    Python upgrade a mass re-run with no change to any result). His view:
    whether a tool or code change alters a check's outcome is a PROCESS
    question, not a technical one, and the system cannot decide it. What he
    wants is a way to recall a whole class at once - e.g. a dbt or server
    bug that affects every allowed-values and required-values check - and
    a TUI path to re-run that class across everything it touches.

    Shape, as he described it: a changelog entry that can name a CHECK TYPE
    (a label such as "allowed values" or "required values") as well as, or
    instead of, individual checks; the bulk re-check (REQ-PIPE-177) selects
    every check carrying that label across every dataset, and the TUI offers
    it from the changelog entry itself. Also to settle: who labels a check
    (a controlled vocabulary, not free text, or the label is useless); whether
    a bug recall and a configuration change share one changelog; and how a
    label applies to checks in a dataset that adds one later.

    NOT for REQ-PIPE-177 as it stands (the bulk re-check, split out of
    REQ-PIPE-164 on 2026-10-10). Keith, 2026-10-08: "a much bigger
    issue than the requirements we're looking at here". Revisit as its own
    item once the current re-check work is signed off.

75. **[todo, 2026-10-10]** **[Pipeline & publishing, QA checks & contract]**
    **Pydantic for the config files, once the toolset is settled.** Keith,
    2026-10-10, asking whether Pydantic would help. Answer given: the biggest
    gains are load-time validation that names the file and field, typed
    access in place of `dict.get` string keys, defaults declared in one
    place (where the frozen-defaults table for the fingerprint would
    otherwise be kept by hand), and a JSON Schema export for editors and
    config authors. For the fingerprint alone the standard library and a
    frozen table are enough; the wider value is validation across all the
    config. Costs: one model per config format (dbt, Soda, the ODCS
    contract, the calendar), and models only for the current shape, since
    old config is never re-read under the fingerprint scheme. Not scoped.
    **Waits until the toolset is chosen** (see #76): Pydantic models for a
    format we later replace would be wasted work.

76. **[todo, 2026-10-10]** **[Pipeline & publishing, QA checks & contract]**
    **Build our own QA checks in Python instead of relying on third-party
    tools - "how hard can it be?"** Keith, 2026-10-10. Raised as a genuine
    alternative, not a decision. What the current tools do for us, so the
    comparison has something to measure against: dbt runs the SQL model
    tests, Soda runs the SodaCL checks and their thresholds, datacontract-cli
    checks the ODCS contract, and Evidently computes drift. Each has its own
    configuration format, its own result shape and its own failure modes,
    and the fingerprint, check lifecycle and changelog gates were all built
    on top of their outputs. Questions to answer before a comparison means
    anything: how much of each tool's behaviour we actually use (the
    `samples limit`, the failing-sample capture, the drift statistics), what
    the replacement would have to reproduce exactly (the calendar and verdict
    semantics are ours already, so the question is only the check
    execution), and what each in-house check costs to maintain against a
    third-party upgrade. The honest starting point is that the verdict
    logic (status, thresholds, amber and red) is already ours; what the
    tools supply is the evaluation of each check against the data, which is
    where the hard parts sit (missing and distinct-value counts across
    dialects, failing-row samples, drift). Worth a spike on one check type
    before any decision. Pairs with #75: the toolset choice decides which
    config formats Pydantic needs to model.

77. **[todo, 2026-10-10]** **[Pipeline & publishing]** **A dataset being
    removed altogether, not just turned off.** Keith, 2026-10-10, while
    deciding that turned-off periods inherit the last promoted supply
    (REQ-PIPE-110, open question Q-G): "if we weren't ever going to receive a
    dataset again, why would we want to inherit it? Why would we even want to
    keep it? Maybe there'd be a reason." Turning off (effective_to with no
    later version) keeps the dataset, its configuration, its history and -
    under Q-G - its last supply inherited into every later period for ever.
    That is right for a temporary turn-off and questionable for a dataset
    that is gone for good. Not scoped. Questions for when it is: is removal a
    distinct act from a permanent turn-off; should inheritance stop, perhaps
    configurably; what happens to the dataset's history, its tables in past
    periods and its checks; how cross-table checks that read it are retired
    (check lifecycle's retirement already exists for checks); and whether a
    removed dataset can ever come back.
    **ADDED 2026-10-14 (Keith, answering REQ-PIPE-179's own scoper pass):
    supplies held as TURNED OFF accumulate, because nobody is asked to act on
    them, and they may be real personal data the agency asked the supplier to
    stop sending.** REQ-PIPE-179 keeps them quiet and kept; how long they are
    kept, and whether anything purges them, is this item's question.


78. **[done, 2026-10-12]** **[Pipeline & publishing]** **Does excusing a late
    supply stop the gate promoting it?** Found by delivery-architect in review
    round 3, outside that round's remit. `rejection.decided_by_a_person()`
    bars the gate from promoting any supply a person has decided, exempting
    only supersede, un-supersede and re-file (`qa_tools/common/rejection.py`).
    REQ-PIPE-161's excuse is a person's decision, so excusing a WAITING late
    supply would, as built today, stop it ever promoting itself - the same
    shape as the placement and re-check findings, which were fixed by naming
    them beside re-file in REQ-PIPE-076 criterion 7. REQ-PIPE-161 is signed
    and not built, so this needs Keith before it is built: should an excuse
    also be exempt?
    **DONE 2026-10-12 (open-items audit):** REQ-PIPE-161 criterion 19: an excuse does not bar the gate (rejection.py exempts EXCUSE_LATENESS).

79. **[todo, 2026-10-10]** **[Pipeline & publishing]** **Which calendar a dataset
    or collection is on, and which collection a dataset belongs to, are not
    versioned.** Raised by delivery-scoper in the REQ-PIPE-110 reviews; Keith,
    2026-10-10, at REQ-PIPE-110's sign-off: not in REQ-PIPE-110 - settle it with
    REQ-PIPE-111. Moving a dataset to another calendar or collection would
    re-judge its whole history against the new one, with nothing to stop it.
    The three answers on the table: refuse such a move once the dataset has a
    slot; allow it only as a declared correction (REQ-PIPE-111); or version
    membership like participation.
    **ANSWERED 2026-10-13 (Keith): BOTH, FOR DIFFERENT CASES.** A real change
    of arrangement from a date - cp-carers going annual from 2027 - is
    VERSIONED MEMBERSHIP: dated entries like participation, history before
    the date stays as it was judged, nothing is re-judged, and past entries
    freeze like every other dated entry. Fixing a MISTAKE in membership is
    a DECLARED CORRECTION (REQ-PIPE-111, built), which re-judges all of
    history as if it had always been so. Applies to calendar membership and
    collection membership alike. Versioning is new work: scope it as its
    own requirement.

80. **[done, 2026-10-11]** **[Testing & dev tooling]** **A timing assertion in
    tests/test_dbt_worker.py fails under full-suite load.**
    `TestOneWorkerPerProcess::test_later_runs_reuse_the_parse` asserts that
    every later dbt run is faster than the first (`max(times[1:]) <
    times[0]`). In a full parallel `mothman check` on 2026-10-11 it saw
    7.23s, 4.26s, 7.39s and failed; the module alone passed 11/11, and the
    same tree minus one unused import had passed the whole suite minutes
    earlier. The thing it proves - the partial parse is reused - is better
    asserted directly (the msgpack is read, not rewritten; dbt's own
    "Unable to do partial parsing" line is absent) than through wall-clock
    time on a shared four-core sandbox. Not fixed here: noticed during
    REQ-GEN-183's gate, outside its scope.
    **DONE 2026-10-12, and it was a real defect, not load:** the dbt worker
    kept a stale partial parse an earlier process had left in a run's
    target, so a later run parsed in full. Fixed and the test now observes
    the kept parse rather than timing (post-build-review #158, REQ-PIPE-157's
    decisions).

81. **[done, 2026-10-12]** **[Testing & dev tooling]** **`mothman check
    --no-pytest` passes with a stale `plans/INDEX.md`.** Seen writing
    post-build-review #153: the index check lives only in
    tests/test_plans_index.py, so the cheap gate CLAUDE.md's commit rule B
    prescribes after a plans edit cannot catch the one thing a plans edit
    most often breaks - the 2026-09-23 incident's own failure. Caught here
    only because the plans test was run by hand. Probably a `plans-index
    --check` gate in `mothman check`'s list.
    **DONE 2026-10-12:** exactly that - a `plans` gate running `mothman
    dashboard plans-index --check`, so `--no-pytest` now catches it
    (tests/test_cli_check.py test_the_cheap_gate_checks_the_plans_index,
    failing first).

82. **[done, 2026-10-11]** **[Data generation]** **A resend drawn clean
    fails the three sibling checks.** Found re-measuring REQ-GEN-184:
    Birth Registrations' run_015 (slot_010, the 2026-09-02 period's third
    arrival, dirty_severity None, received 2026-09-14) fails
    sibling_match in Soda, the contract and dbt and nothing else. It is
    byte-identical at 3115cdd, before any #63 work, so it is not that
    work - almost certainly `churn()` changing a column the sibling check
    matches twins on, in one twin and not the other. It matters beyond
    the one supply: a "clean" resupply that reads red leaves its period
    unfilled, and it is the same mechanism the parked TS-46 note blames
    (a resend churned from the first supply). REQ-GEN-184 criterion 5 is
    about TARGETED supplies; churn is the ordinary chain's, so this wants
    its own fix or a line in REQ-GEN-185, which plants TS-46.

    **Fixed the same day (Keith: void singles only).** `churn()` voided 1%
    of rows at random; voiding one twin left its sibling unmatched. Real
    tools on ten churn seeds: 4 failed the sibling checks; the regression
    test failed on 5 of 12 seeds before the fix, none after. `churn()` now
    voids single-birth rows only, same draw. Measured on a regenerate from
    empty: Birth Registrations gate verdicts amber 13 / green 9 / red 20
    became 14 / 13 / 15, page 10 / 4 / 28 became 10 / 7 / 25, gap reds 30
    became 28, promotions 19 became 21; Child Protection unchanged (its
    churn only modifies). It also cleared the critic's finding 1 on
    REQ-GEN-184 part B (post-build-review #155): a targeted resend went
    through the same churn.

83. **[parked, 2026-10-11]** **[Pipeline & publishing]** **For Keith: a
    late live pass stamps its promotion before its own gate ran.** Raised by
    the critic on REQ-GEN-185 (post-build-review #156 finding 4) and not
    settled. `promotion.effective_at_for` invents a lag after receipt - one
    hour to the claim window, spread, since #156 - and takes the earlier of
    that and now. On every route, not only a replay: the terminal and Lambda
    routes do the same for a past-dated receipt, and REQ-PIPE-086 criterion
    11 needs the three to record the same decision (a "replay only" version
    of the window was built, broke tests/test_kept_routes_agree.py, and was
    taken back the same evening). So a LIVE pass that reaches a supply more
    than the claim window after receipt - a backlog, the ungated retry -
    records a decision effective before the gate ran. That was true before
    the window too, for any lag past three days. When Keith picked "Spread
    1h-4h" the option said "only in a replay; a live pass keeps its real
    instant" - the second half described the code wrongly, which is why it
    is back with him. The question: should a live pass's decision take
    effect when it is made (and the routes agree some other way), or is the
    invented instant right for a synthetic past-dated keep and wrong only
    for a real late pass?

    **Keith, 2026-10-11 evening: leave it for now.** Only synthetic,
    past-dated deliveries meet it today; no real live pass exists yet.
    Scope it with the live (AWS) work rather than on its own.

84. **[todo, 2026-10-12]** **[Dashboard]** **A dashboard build with no git
    still fails, despite the provenance stamp tolerating it.** Found by the
    test review's pass 2 while rewriting the provenance tests:
    `dashboard/embed_dashboard_data.py` stamps the build with the commit and
    tolerates its absence (`except Exception: commit = None`), but `embed()`
    asks for the commit again later, for the GitHub links, with no
    tolerance - so a build from a tarball or any checkout without git fails
    there. The tolerance test now breaks only the first ask, and would fail
    rather than pass quietly if the order changed. Small; whether a build
    without git is a supported case at all is the question to settle first.
    **ANSWERED 2026-10-13 (Keith): THE COMMIT COMES FROM AN ENVIRONMENT
    VARIABLE FIRST.** Why it matters: the build moved out of GitHub Actions
    (REQ-PIPE-092) to wherever the database is reachable - in a real
    deployment, a container image that usually has no .git. So the image is
    stamped with its commit at build time (as GITHUB_SHA already is in
    Actions), that is preferred over git, and with neither the page omits
    the commit stamp and the pinned GitHub links rather than failing - both
    asks of the commit, not only the first. Not built yet.

85. **[investigate, 2026-10-12]** **[Pipeline & publishing]** **For Keith: a
    delivery file's receipt_sequence differs between two bootstraps of the
    same history.** Found proving REQ-PIPE-192 identical: two bootstraps
    from empty into fresh databases, same deliveries, recorded the same
    161 delivery files with every column equal EXCEPT `receipt_sequence`
    (one run numbered Child Protection's first file 5, the other 1).
    Birth Registrations and Child Protection record their deliveries side
    by side (REQ-TEST-116), so the order the sequence is handed out in
    depends on which process reaches the database first. Everything else -
    filings, decisions, verdicts, supply tables - was identical. The
    question: is receipt_sequence used to ORDER anything (a tie-break
    between two files received at the same instant), in which case it
    should come from something deterministic; or is it a surrogate,
    in which case tests/equiv_support.py should exclude it like the other
    surrogate ids. REQ-PIPE-188's equivalence criterion will meet the same
    thing.
    **ANSWERED 2026-10-13 (Keith): DETERMINISTIC PER DELIVERY.** Checked in
    the code first: it IS an ordering tie-break, not a surrogate - REQ-PIPE-061,
    qa_store.py's own comment, and three ORDER BYs in dataset_blockers.py and
    outstanding.py - and it is numbered across the whole database
    (s3_arrival.py takes MAX+1), which is why the two bootstraps disagreed.
    So: number files within their own delivery in a stable order (filename),
    so the same history always gets the same numbers. Not built yet.

86. **[parked, 2026-10-12]** **[Testing & dev tooling]** **A pruning pass on
    the test suite, criterion by criterion - in the pocket for later.**
    Keith asked why there are ~4,600 Python tests ("that seems insane").
    Measured: 4,269 distinct test functions (800 parametrized cases) in 351
    modules; ~69k lines of test code against ~68k of product Python, about
    1:1; ~2.3 tests per acceptance criterion across the 167 built
    requirements (1,833 criteria). The three review passes that day only
    removed tests that were worthless on their face (memorials, duplicates,
    tautologies, source greps); none asked "what is the fewest tests that
    would catch this criterion breaking". The pass offered: go criterion by
    criterion, keep the fewest tests that would catch each breaking, fold
    near-duplicates into parametrized cases, report every cut and why. The
    honest cost: most of the day's real bugs (the stale dbt parse, the
    leftover filings) were caught by exactly the tests that look
    excessive. Keith: "leave it in the pocket for later" - and happy for it
    to be proposed again, so raise it when the suite's time or weight next
    gets in the way. Alternatives offered and not chosen: a numeric target
    (cut to N, weakest first), and a speed-only pass on the browser tests,
    which are ~85% of the suite's wall clock.

    **RAISED AGAIN, 2026-10-18, harder - and still deferred.** Keith, watching
    the REQ-GEN-246 gate take 18 minutes: "I don't understand how we have so
    many goddamn tests ... You've done something seriously wrong in how
    you've been doing testing. We need to, honestly, I think we need to rip
    it out and start again at some point. Challenge me on this." Measured
    that afternoon: about 5,000 Python test functions in 294 modules, 830
    JavaScript tests, 84k lines of test code against 77k lines of product
    Python (about 39k of them code, the rest comments, docstrings and
    blank lines). The full `mothman check` 18m02s, pytest 15m47s of it.

    THE CHALLENGE GIVEN, which he accepted for now: the COUNT is a real
    problem - one test per acceptance criterion and per critic finding,
    exact-wording pins, and the same behaviour tested once directly and
    again through the browser - but the TIME is per-test cost, not count:
    a few hundred tests drive real dbt/Soda/datacontract/Evidently runs, a
    real PostgreSQL bootstrapped from the grown Child Protection history,
    the real generators, and 239 real-browser tests in one module pinned to
    one worker. Ripping everything out would discard the ~3,000 cheap tests
    that cost seconds and rebuild the expensive ones, which are the ones
    that catch real breakage. Proposed instead, as its own requirement: (1)
    profile one full run (`--durations=0`) for each test's real cost; (2)
    budgets - a default local gate under ~5 minutes, the real-tool and
    browser tests a separate tier run before a push; (3) cut by category -
    browser tests to real user journeys, wording pins deleted (REQ-TEST-239's
    S7 capture already covers help and menus), duplicate coverage merged,
    real-tool runs shared through fixtures; (4) change the habit: a test per
    behaviour worth protecting, not per criterion or finding.

    Keith, 2026-10-18: "Don't worry about culling tests now." So this stays
    in the pocket until item 6's chain (#106) is done. What changed today
    is the GATING, recorded in #106.


92. **[todo, 2026-10-13]** **[Docs & process, Dashboard UI]** **What comes
    after the contested-pair batch, and a "we heard / we built" view of
    the road-testing feedback.** Priority: Keith's own order, 2026-10-13
    evening - (1) once this batch is done, a high-level summary from
    CHANGELOG.yaml of what was built or changed in the past two or three
    days; (2) confirm the calendar requirements worked on over the past
    week are all actually built; (3) pick up small items and open
    questions that unblock things; (4) the next big priority for the
    following few days: review plans/road-testing.md, turn it into
    decisions and requirements, and build them.
    **The road-testing feedback came from someone else** Keith showed the
    PoC to. For each item he wants to go back to them with a short, super
    high-level summary of how their feedback was addressed - enough to
    talk them through it. So road-testing entries are NOT simply deleted
    as they are built (a change to that file's own "the entry comes out
    when it lands" rule): each keeps a post-build record - "you told us
    this; this is what we heard; this is what we built; here is the
    evidence". Better still, it is an artifact IN THE DASHBOARD that
    Keith can click through with them: we heard / you described / we
    built / evidence. Same document or a separate one beside
    road-testing.md - he is easy either way. Expected to be ephemeral
    (a few months at most).
    **Answered the same evening (Keith, 2026-10-13):** "this batch" runs to
    the end of the chain he set - REQ-GEN-196 and REQ-GEN-199 included -
    before the summary and the rest. And the feedback view is ITS OWN
    top-level dashboard tab, fed by road-testing.md itself: each entry
    gains a short "You told us / What we heard / What we built /
    Evidence" block (links into the dashboard, requirement ids), one card
    per item, nothing deleted as items are built. Needs scoping into a
    requirement before it is built.
    **Steps (1) and (2) DONE the same evening**, reported to Keith in
    conversation. Step (2) found the calendar group built except two open
    pieces of built requirements (REQ-PIPE-170 criterion 23's TS-57..63 in
    the history; REQ-GEN-136's criteria 3, 4/5, 8, 9 and 11) and three
    unsigned drafts (REQ-PIPE-163, REQ-PIPE-179, REQ-DASH-182).
    **Keith's call, 2026-10-13 evening: close out the calendar group
    BEFORE the road-testing review** - REQ-PIPE-170's and REQ-GEN-136's
    leftovers, and REQ-PIPE-179 and REQ-DASH-182 built. His answers:
    REQ-GEN-199 first while those are scoped in parallel; REQ-PIPE-163
    scoped WITH REQ-PIPE-179 (179 amends 163); REQ-PIPE-170's fictional
    past corrections are declared in contract/calendar.yaml itself ("this
    asset is a synthetic data asset for demo purposes, so that is fine"),
    not a synthetic-only overlay file; and REQ-GEN-136 criterion 3 (TS-42)
    by WIDENING ONE Child Protection arrival pattern, a behaviour change
    with its own requirement - superseding REQ-GEN-196's "no pattern is
    widened" decision. Scoper pass on 163/179/182 plus the pattern
    requirement started the same evening.
    **Scoper pass the same evening** (163, 179, 182, plus new REQ-PIPE-202
    widen cp_clients' pattern and REQ-GEN-203 plant TS-42; draft in the
    session scratchpad, not yet in requirements.yaml). **Keith's answers,
    2026-10-13 ~20:30 Perth:** 163 - written in its final turn-off-aware
    form now so 179 amends nothing in it; a typed --period owing nothing
    (not participating, not_expected, turned off) is refused like the menu;
    placing into a period with an OPEN PAIR is refused ("settle first");
    placing over a WAITING VERSION is REFUSED UNTIL IT IS DECIDED (not the
    scoper's "supersede it" - no REQ-PIPE-118 amendment). 179 - every route
    into a turned-off period refused (place, re-file, correction move,
    parked move stays parked); the rule re-files ANY hold configuration
    later covers, whoever caused it; "turned off" outranks "schedule
    ended"; but a not_expected entry INSIDE a turned-off gap is REJECTED as
    configuration ("you shouldn't be able to have a not expected period
    while the dataset is turned off - that doesn't make sense"), reversing
    the drafted reading; 179 TAKES TS-63 OVER from REQ-PIPE-170 c23. He
    asked to see the config: shown as a participation version with
    effective_to + turned_off_reason, back on = a later version. 182 -
    buildable now, "Turned off" as a WHERE clause; one row for an
    owed-nothing period that inherits. 202 - cp_clients(_[^/]+)?\.csv, a
    demo choice said so in a comment; the trial route attributes by pattern
    too. 203 - its own requirement; TS-42's files cp_clients.csv plus a
    differing cp_clients_v2.csv re-export, later superseded by a clean
    file; AND (not the scoper's recommendation) ONE scripted Child
    Protection pair settled by a person in the demo history.
    **Round 2 the same evening:** the scoper folded all sixteen answers in
    (Q15 B gives REQ-GEN-203 a second scenario, TS-80: a stray
    cp_clients_TEST.csv beside the real extract, settled by a scripted
    person - reject the test file, supply the real one, PROPOSED). One new
    fork, answered by Keith: TS-63's turn-off is DECLARED AS A CORRECTION
    in calendar.yaml, like TS-57..62 - not slipped in under the synthetic
    exception for a newly added version. Still to confirm at sign-off:
    163 criteria 35 (refuse where the agreement backstop refuses the
    dataset) and 36 (GitHub reply). Architect + CLI UX + dashboard UX
    reviews started next.
    **The quarterly runway warning stays (Keith, 2026-10-13):** offered
    2028's dates (1 Feb/May/Aug/Nov) to clear `mothman check`'s "calendar
    'quarterly' is low on runway" warning; his answer - "the point of the
    warning is to demonstrate the proof of concept of what it does". Do not
    extend the calendar to silence it, and do not propose it again.
    **CLI and dashboard UX reviews, answered the same evening (Keith):**
    `mothman supply decide` leaves EVERY decision's checks owed unless
    --wait, re-file included (an amendment to built REQ-PIPE-141); Ctrl-C
    while a placement's checks run in the menus returns to the collection's
    menu, the placement standing and its checks owed; a CP trial's
    REFERENCE folder is recognised through arrival_pattern too (he asked how
    the widening works - shown: one arrival_pattern line in
    contract/data-asset.yaml, cp_clients\.csv -> cp_clients(_[^/]+)?\.csv);
    owed-nothing rows that recur (cp-case-workers' May/Nov) read a SHORT
    generated label ("Not owed - outside its agreed months (Feb, Aug)"),
    the authored reason once on the agreement tile; the current cycle shows
    its owed-nothing row in place of "No deliveries in the current cycle
    yet."; the due-before label reads "by 22:00 the day before" (one day) /
    "by 22:00, N days before each date"; and a reader dataset turned red by
    ANOTHER table's contest gets a NEW DASHBOARD REQUIREMENT NOW (a top-of-
    page line naming the contested table), not a later sighting.
    **Architect review answers, 2026-10-13 ~21:00 (Keith):** PROMOTING A
    HELD SUPPLY STRAIGHT INTO A PERIOD (skipping filing, its QA run and the
    gate - found by the architect reading promotion.promote) must be
    refused, pointing at place: "there should be no way to move things into
    a period and then skip doing checks" - and he asked for EVERY such route
    to be audited for the same loophole (audit started), plus a plain
    account of today's rules for manual promotion within a period; he is
    open to a combined "move and promote" if it keeps the checks. TS-63's
    room: GROW the Child Protection history earlier (pre-2023 calendar and
    participation versions, as Birth Registrations was grown). Still
    answering: how a placement is recorded (he asked how different place
    and re-file really are, and what a new log action costs), and held
    pairs (he asked whether there is really no route for them today).
    And the last two (Keith, same evening): a placement is RECORDED as a
    re-file from no period by a person - place and re-file are one act
    underneath, so no new log action - while the terminal and the page
    still say "placed"; and placing a HELD PAIR moves both files into the
    period, still contested, to be settled there.

    **Round 3, overnight 2026-10-13 to 14 (Keith: "draft up some requirements and chuck them to the scoper, the architect, and the UX reviewers, and then come back to me with a final proposed draft for questions"):** the scoper drafted REQ-DASH-204 (a reader dataset red from another table's contest), REQ-GEN-205 (TS-57..62 planted, a scripted confirm-correction with keeps) and REQ-GEN-206 (REQ-GEN-136/137 leftovers, #175); the three answers still outstanding on 163/179 were folded in; the whole batch with REQ-DASH-180 went to the architect, CLI UX and dashboard UX reviewers. Drafts in the session scratchpad, unsigned; the final draft and its questions are in plans/morning-reports.md #4.
    **STEPS 1 AND 2 DONE, 2026-10-14 (main session).** (1) The recap from
    CHANGELOG.yaml, 11 to 14 October: the delivery agreement moved into one
    file and its past became changeable only by a declared, approved,
    previewable correction (11th); runs ask their tools only for what they
    record, halving a rebuild (12th); two files for one table can be settled
    in the terminal and are shown on the page and ticket, with seven demo
    pairs and the as-at scenario cases (13th); an early supply no longer
    reads "No data", and rebuilt corrections date by the history (14th).
    (2) The calendar audit - every requirement written or signed from 7
    October: all SIGNED ones are built except the four signed today
    (REQ-PIPE-163/202, REQ-GEN-203/207, not started by design). Two built
    ones carry unmet criteria, both known: REQ-GEN-199 (c9, c16, c33 -
    post-build-review #174/#175, folded into the close-out draft) and
    REQ-PIPE-170 (c23, TS-57 to TS-62 - REQ-GEN-205). Not yet signed: the
    close-out batch (REQ-PIPE-179, REQ-DASH-175/180/182) and five older
    drafts outside it - REQ-PIPE-164 (re-check one supply), REQ-GHUB-165,
    REQ-PIPE-166 (withdraw a mark/acknowledgement), REQ-PIPE-177/178 (bulk
    re-check), and REQ-QAC-176 (a fingerprint of each check's definition
    on every result - the rule 3 audit's M4 gap, already drafted).
    **STEP 3 DONE AND STEP 4 SCOPED, 2026-10-14 afternoon.** The seven older
    drafts were triaged (none overtaken; docs/drafts/unsigned-triage/), re-scoped
    and reviewed; the "we heard / we built" Feedback tab was scoped as REQ-DOCS-219
    (cards in road-testing.md + a gate), REQ-DASH-220 (the tab) and REQ-DASH-222
    (a requirement's own address). Keith signed eleven: 219, 220, 222, QAC-223,
    DASH-175, PIPE-164, PIPE-166, GHUB-165, and PIPE-177/178 + DASH-221 (build
    waiting on REQ-QAC-176, which stays unsigned behind #89). Found and fixed on
    the way: post-build-review #180 (closing a side panel opened from a link left
    the dashboard). Still to do in step 4: build the Feedback tab, then scope
    road-testing sprints 1, 3 and 4.


93. **[todo, 2026-10-14]** **[Dashboard UI]** **A period-composition view
    - Keith's answer to the close-out batch's question 16.** No page
    shows a period's `_manifest` (which tables are promoted, inherited or
    substituted for that period). Keith chose to draft a dashboard view
    for it over quoting the terminal, so TS-55 (REQ-GEN-137 criterion 6)
    has a page to point at. Not scoped yet - goes to the scoper as its own
    requirement, and must work at ~30 datasets per period.

94. **[todo, 2026-10-14]** **[QA checks & contract]** **[Pipeline &
    publishing]** **When a contract changes a dataset's columns, what
    happens to supplies already recorded under the old shape?** Split out of
    #89 by Keith, 2026-10-14 ("separate"): #89 is the QA metadata schema;
    this is schema evolution of the data itself - old supplies keep their
    shape, and promotion, period views and cross-table checks all read
    across supplies that may differ. Not scoped.

95. **[todo, 2026-10-14]** **[Pipeline & publishing]** **[QA checks &
    contract]** **[Dashboard UI]** **A dataset whose cross-table check could
    not be judged is neither green nor red.** Priority: address in the next
    few days (Keith, 2026-10-14 night, with #89: "given that they block some
    other requirements" - its shape holds REQ-DASH-204, REQ-PIPE-210,
    REQ-PIPE-211 and REQ-GEN-206). Both need Keith in the conversation, so
    they are scoped with him by day, not built overnight. Keith, 2026-10-14, reviewing
    the close-out batch: "that cross-table check isn't judging on
    notifications, so you can't really rule it green - but it's also not a
    true red." What happens today (checked in unrunnable.py and
    qa.check_result): the dependency's state is read ONCE, at the reader's
    arrival, and never revisited. Not yet due -> the check records `nodata`,
    the reader can read green and be promoted, and nothing re-checks it if
    the dependency then goes overdue or never comes (a FALSE GREEN).
    Already overdue, contested or awaiting a decision -> the check records
    `fail`, which rolls up, so the reader reads RED with no failure of its
    own (e.g. a cp-investigations run, zero own failures, red for a missing
    cp_carers). Proposed: a distinct "waiting on <table>" status the gate
    does not promote on, re-checked when the dependency arrives or goes
    overdue. His call: SCOPE IT FIRST with the scoper and architect, and
    decide the re-check question as part of that. REQ-DASH-204, REQ-PIPE-210,
    REQ-PIPE-211 and the still-failing shout (close-out R2) all hang on it.
    **KEITH'S INPUT FOR THE SCOPER, same morning (in his words, condensed):**
    "If the cross-table checks can't run against everything, then
    notifications should shout." Concretely: if clients did not arrive
    alongside notifications, notifications shouts - "we can't assert that
    it's complete and actually green"; if clients is then overdue,
    notifications shouts; if clients is red and not promoted, notifications
    shouts. He is AGNOSTIC about whether those shouts differ and how detailed
    the message is: "the fact is that there is no promoted clients", and the
    reader can go to clients to see whether it is late, overdue, held or
    anything else. So the shout's trigger is one rule (a cross-table check
    could not run against everything it reads), and the detail lives on the
    dependency's own page.
    AND (Keith, same morning): whatever shape is chosen must demonstrably
    fix BOTH the false green and the false red above, and any similar
    mis-reading found on the way (a held dependency, one red and never
    promoted, one promoted later, re-filed or superseded) - each with a
    criterion and a test that reproduces today's wrong reading first.
    **SCOPED 2026-10-14** into `docs/drafts/unjudged-cross-table/` as
    REQ-QAC-212 to REQ-PIPE-217 (unsigned). **SHAPE SETTLED 2026-10-20**
    (Keith: "Go with 1, its own Incomplete status") - with Q2 (promotes itself
    as "Incomplete promoted") and Q4 (a staged dependency counts as checked)
    from 2026-10-14. The rest of the draft's questions are being walked with
    him; answers in that folder's summary.md. Related, built the same day:
    REQ-PIPE-265's 312 staggered pairs are this item's false-green case.


96. **[todo, 2026-10-14]** **[Dashboard UI]** **[QA checks & contract]**
    **File-check verdicts should show through every level of the
    dashboard - but how is not yet known.** Keith, 2026-10-14, answering
    road-testing sprint 1's question on whether file checks count as a
    "column" in the new "N of M columns not green" counts: "Let's separate
    this and scope it separately - I do think they need to display through
    all levels of the dashboard, but just not sure how yet." Today REQ-DASH-097
    criterion 2 (signed, built) keeps every file-check verdict out of "any
    status, count or trend", and criterion 7 says a file warning never changes
    the dataset's status; a refused file is already its own reason row. File
    checks are recorded per load attempt, not per QA run, so a trend of them
    is a different shape from the check trends. Sprint 1 leaves them out of
    every count and trend meanwhile. Needs scoping with Keith - starting from
    what a reader at the agency card, the dataset list and the dataset page
    should learn about a file that warned or was refused.

97. **[todo, 2026-10-15]** **[Data generation]** **[Pipeline & publishing]**
    **A calendar with a second version, to stress-test what follows a
    calendar's history.** Keith, 2026-10-15, answering morning report 5
    Q20 (the SLA tile follows participation versions but not calendar
    versions, and no calendar has a second version today): "Wait and let's
    discuss building a calendar with a second version to stress test this
    and other things." So nothing reads a calendar change in anger yet - the
    SLA tile, slot instants, claim windows, runway and the as-of picker all
    have only ever seen one calendar version. Needs a conversation first:
    which calendar, what changes in its second version (anchor months, claim
    window, day of month), when it takes effect inside the synthetic
    history, and which scenarios it should exercise.
    Keith, 2026-10-15: keep this SEPARATE from REQ-GEN-205, whose
    correction adds a past-dated calendar version - 205 is about
    corrections; a deliberate second calendar version is its own
    conversation.

98. **[todo, 2026-10-15]** **[QA checks & contract]** **[Dashboard UI]**
    **A check is judged against supplies that arrived before it existed.**
    Seen building REQ-GEN-207: every Child Protection check carries
    `introduced_date: 2023-01-15`, and the forty grown quarters (2013-2022)
    are run and shown against all of them - 111 fails and 24 warns on supplies
    no such check was ever agreed for - with nothing on the page saying the
    check came later. Question for Keith before anything is scoped: should a
    check skip, or be marked on, a supply received before its introduced
    date? Not built; recorded in the register under TS-79b.

99. **[todo, 2026-10-15]** **[Data generation]** **[Testing & dev tooling]**
    **A simple, cheap dataset to test with, so not everything rides on Child
    Protection.** Keith, 2026-10-15 evening, as the first full suite after
    REQ-GEN-207 ran past 25 minutes: "Let's prioritize adding another simple
    data set that we can use that's not going to be as intensive as child
    protection." Context: since the ten-year growth, Child Protection is 55
    quarters of five tables and costs ~32s a bootstrap quarter (CLAUDE.md's
    bootstrap log, 8m08s -> 31m52s), and much of the suite and the scenario
    register leans on it. Priority: tackle tomorrow or over the weekend
    (Keith, 2026-10-15 evening). Needs scoping with him first: one table or a few, which cadence,
    how much history, which tests and scenarios move onto it, and whether it
    joins an existing agency/collection or gets its own.

    **Scoped with Keith the same evening (22:40-ish Perth), answers in his
    own choices:** the purpose is to SHRINK Child Protection, so adding a
    scenario stops costing a Child Protection quarter. A Department of
    Health Emergency Department dataset:
    - **Quarterly, on the existing quarterly calendar**, so quarterly
      scenarios move across unchanged.
    - **One table, about eight columns, one CSV per supply** (presentation
      id, arrival date/time, triage category 1-5, age group, sex, postcode,
      departure status, length of stay - my proposal, he chose it).
    - **A new agency**: Department of Health > Emergency Department > one
      dataset, so the executive view shows a third agency.
    - **All four QA tools, a few checks each** (roughly 10-15 in total), so a
      scenario that moves still exercises the tools it did before.
    - **History: as many quarters as its scenarios need**, worked out by a
      dry run, the same rule as REQ-GEN-207's growth.
    - **What stays on Child Protection:** only a scenario that needs a supply
      of several files (TS-12, TS-38, TS-56, TS-75a, TS-76, TS-77a today), a
      cross-table check, or several datasets in one collection (collection
      participation defaults, a dataset that supplies only some quarters
      like Case Workers, knock-ons between datasets). Everything else moves
      and keeps its TS number - TS-9, TS-65, TS-66, TS-67 today, and the
      unbuilt TS-3a/3b, TS-63, TS-57 to TS-62 get planted on Emergency
      Department instead.
    - **Child Protection then shrinks to whatever its remaining scenarios
      need** (not straight back to 15 quarters, not kept at ten years) -
      an amendment to the built, signed REQ-GEN-207.
    - **Sequence:** draft the requirements now, before finishing REQ-GEN-207's
      failing tests; delivery-scoper then delivery-architect, and Keith
      signs off before anything is built.
    Drafted the same night: `plans/data-generation.md` #12.

100. **[todo, 2026-10-15]** **[Data generation]** **[Dashboard UI]**
    **Mix up the names of some of the datasets.** Keith, 2026-10-15 evening,
    in the same breath as #99: "Let's also maybe mix up the names of some of
    the data sets." Not scoped. Questions for him: which datasets, why
    (names too alike, too obviously synthetic, or exercising display of
    longer and odder names), and whether the dataset IDs change or only
    their display names. IDs are used in the decision log, contracts and
    tests, so changing them costs far more than changing names.

101. **[todo, 2026-10-16]** **[Testing & dev tooling]** **The CLI and TUI at
    ~30 collections.** Raised by the CLI UX review of item 6's drafts
    (`docs/drafts/item6/position.md` call 22): with one `mothman <short>`
    group per collection, `mothman --help` buries the tool groups among ~30
    collection groups (rich-click `COMMAND_GROUPS` could split a Collections
    panel from a Tools panel), the TUI's "Which dataset?" picker hits Hick's
    Law at 30 rows (group by agency, or questionary's search filter above a
    threshold), and flag hints listing every collection stop being readable.
    Deliberately NOT in item 6's series, which holds `--help` byte-identical.
    ANSWERED (Keith, 2026-10-16 ~06:50 Perth): "~30 collections" - thirty
    collections, each with its own command group, so this is real work, not
    a hypothetical. IN ITEM 6'S SCOPE (Keith, 2026-10-16 ~07:10 Perth: "their
    code is in scope for what we're doing here"), reversing the proposal's
    significant call 9 (position.md call 22) - the CLI and TUI at ~30
    collections is part of item 6, not later work. SCOPED the same morning as
    REQ-TEST-252 (requirements.yaml), with Keith's
    answers: N_LIST 9, the Collections/Tools help split at every size, and a
    new `mothman collections` command for the full list. Not yet signed.

102. **[in-progress, 2026-10-16]** **[Pipeline & publishing]** **Key the
     configuration caches on file content.** Drafted by delivery-scoper as
     REQ-PIPE-254, signed off by Keith 2026-10-24 with every open question
     answered. Built 2026-10-28 except criteria 13, 14 and 19, which need two
     bootstraps from empty that nobody has approved yet (see the requirement's
     unmet_criteria). Remove this entry once REQ-PIPE-254 is built.

103. **[todo, 2026-10-16]** **[Testing & dev tooling]** **Three copies of
     the asset file's path.** Found by delivery-scoper drafting REQ-PIPE-254:
     `hierarchy`, `asset_time` and `validate_schedule` each hold their own
     `DATA_ASSET_YAML` constant, so a test that patches one still reads the
     real file through the other two. Separate from REQ-PIPE-254, which it
     does not change - Keith, 2026-10-24, answering 254's open question 5:
     its own small item rather than folded in. Not yet scoped.

104. **[in-progress, 2026-10-18]** **[Dashboard UI]** **[Pipeline & publishing]**
    **Private hosting for the dashboard, then a private repository -
    Keith's answers, 2026-10-18.** Answering the weekend reminder about
    plans/dashboard.md #2 and #4, over four rounds of questions. His
    words and choices: no paid GitHub plan and he does not want one
    (Copilot does not give private Pages); he already uses Cloudflare
    and is open to Cloudflare Access; access is for a handful of named
    people in his team at work, ideally against corporate identity
    (GitHub or Microsoft), worst case one shared credential. Settled:
    Cloudflare Access with a ONE-TIME CODE to allow-listed work email
    addresses (over Entra ID, which needs his agency's tenant admin, and
    GitHub identity, which needs everyone to have an account, and a
    shared credential); CLOUDFLARE PAGES BY DIRECT UPLOAD from the
    environment that builds the dashboard (nothing on GitHub Actions
    can, it needs the database); the repository goes private only AFTER
    the private host is live and a teammate has signed in; publishing is
    BOTH the existing `mothman dashboard publish` (its transport swapped
    from gh-pages to wrangler) AND automatic at the end of `mothman
    pipeline run` and `pipeline process`, never a bootstrap, with an
    opt-out - which knowingly reverses REQ-PIPE-092 criterion 16's
    opt-in rule of 2026-09-27; the Cloudflare token is an environment
    variable alongside the DSNs, refused plainly when missing; the
    SANDBOX environment is the one publisher until production exists;
    the private site carries the current dashboard AND every snapshot;
    ONE SNAPSHOT PER PUBLISH, but a publish (and so a snapshot) only
    happens when the built site has CHANGED - his own suggestion, compare
    the current and new file hashes; Access is configured by hand in
    the Cloudflare console from a committed runbook and its outcome
    checked by the publisher; CI minutes (a private free repo gets 2,000
    Actions minutes a month against roughly 5,000-15,000 a week used
    now) are CUT FIRST, as a precondition of the flip; the dashboard's
    GitHub links 404ing for non-collaborators is accepted. delivery-scoper
    drafted REQ-PIPE-255 to REQ-DOCS-259 the same day (draft in the
    session scratchpad, to be amended with the last two rounds and put
    to him for sign-off); nothing built. Hosts a session cannot reach,
    for CLAUDE.md's blocked list: api.cloudflare.com, *.pages.dev,
    cloudflareaccess.com, dash.cloudflare.com, developers.cloudflare.com.
    Final round the same afternoon, after the scoper measured CI (about
    320 pushes and 10,900 billable minutes last week): AUTOMATIC
    PUBLISHING IS OFF after all - Keith kept REQ-PIPE-092's opt-in rule
    ("No, keep publishing opt-in"), so the proposed REQ-PIPE-256 is
    dropped and only `mothman dashboard publish` (and `pipeline run
    --publish`) publishes; no `--force` to publish an unchanged site;
    the failed-upload order (results recorded first, then the failure)
    is confirmed; and for CI minutes he chose "push far less, using the
    local checkpoint commits, and keep validate-config on every push" -
    test.yml keeps its push trigger, the lever is fewer pushes, and the
    flip still waits on a measured week fitting 2,000 minutes a month.

105. **[todo, 2026-10-18]** **[Dashboard UI]** **A thin, designed environment
    banner, instead of words in the build stamp.** Keith, 2026-10-18,
    while signing REQ-PIPE-255 ("make sure the notice that shows about
    the environment in the UI is like a nicely designed thin banner of
    some sort"). Today REQ-DASH-094's marker is the words "not production"
    appended to the masthead's build stamp plus a dimmed live dot; once
    the sandbox is the publishing environment (REQ-PIPE-255) those words
    leave the published page and a reader has nothing but the stamp.
    Wanted: a thin banner naming the environment on every page, designed
    rather than bolted on, words not colour alone (REQ-DASH-094's rule).
    Not scoped; send to delivery-scoper and delivery-dashboard-ux before
    building. Same conversation: watch the built page's size during
    development and flag it at 20 MiB (REQ-PIPE-255 now does, every
    build), and talk about optimising or splitting the file when it fires.

106. **[in-progress, 2026-10-18]** **[Testing & dev tooling]** **Item 6's
    chain: REQ-TEST-245 straight after REQ-GEN-246, and no push until the
    whole chain is done.** Keith, 2026-10-18, after asking whether
    cli/bdm.py and cli/cp.py are still needed ("Yes, do 245 straight after
    246. But don't worry about pushing until we've done this whole chain of
    stuff here. And then check with me before you push."). So the order is
    now REQ-GEN-246, REQ-TEST-245, REQ-DASH-244, then REQ-TEST-252,
    REQ-TEST-249, REQ-QAC-247 and REQ-PIPE-248 - swapped because nothing
    ties 244 before 245; they touch different files. Every piece is still
    checkpointed locally (rule D), the chain is pushed once at the end, and
    ONLY AFTER ASKING KEITH. GATING, the same day (Keith: "I agree with your
    approach of only running the test modules the piece touches and the
    cheap gates. That's good. Let's do that more."): each piece runs the
    test modules it touches, `mothman check --no-pytest`, and its
    equivalence capture where its requirement asks for one; ONE full
    `mothman check` runs after REQ-PIPE-248, before the push is put to
    him. The cost, accepted: a failure an early piece causes surfaces only
    at the end, and is harder to pin on its cause. This overrides the
    one-push-per-finished-piece default for this chain alone. Record the
    swap in REQ-TEST-245's decisions when it is built.

    A TEST ACCOUNT AT THE END OF THE CHAIN (Keith, 2026-10-18 evening, his
    words: "please report at the end of this chain how many tests you've
    deleted and how many you've migrated that were pointing at very
    particular BDM and CP behavior. And check for duplication amongst tests
    that point to the new registry stuff."). So the report put to him with
    the push question carries: tests deleted, tests migrated off
    collection-specific modules, both counted from the commit before
    REQ-GEN-246 (86fdc05) to the chain's last commit; and a duplication
    check across the tests of the registry, the generator providers, the
    CLI factory and the one dashboard builder - which tests assert the same
    behaviour twice, and which could go.

    A SIGNED CRITERION THAT CANNOT HOLD, FOR KEITH (found 2026-10-18 evening
    building REQ-TEST-249): criterion 3 says the copy may differ from the
    tracked tree in contract/data-asset.yaml only (plus new files), but a
    dataset with no entry in contract/calendar.yaml is refused outright
    ("names no `calendar:` and does not declare `no_calendar:` either").
    So a fake collection cannot be added without editing calendar.yaml,
    exactly as criterion 10 already allows for Emergency Department.
    BUILT UNDER THE ASSUMPTION that criterion 3 also allows calendar.yaml to
    differ by the fake collection's entries inserted whole, every
    pre-existing line unchanged and in order - the same rule as for
    data-asset.yaml. The criterion's text is NOT changed until he agrees.
    THE SAME FOR contract/presentation.yaml: REQ-DASH-244 put every
    collection's words in that one asset-wide file and `mothman check` fails a
    collection with no entry, so a new collection edits it too. Built under the
    same assumption; the alternative is a presentation file per agency folder,
    which would be a change to REQ-DASH-244's criterion 10.

    KEITH'S ANSWERS, 2026-10-18 evening (through the question tool, after
    the post-build critics on 246, 245, 244 and 252 reported):
    1. PUSH: hold everything until REQ-PIPE-248 is done - not the finished
       pieces first. The chain still pushes once, after asking him.
    2. REQ-TEST-249 c3: ALLOW calendar.yaml and presentation.yaml to differ
       too, only by the new collection's entries inserted whole. Amend the
       criterion's text to say so.
    3. MISSING RESULTS FILE: the dashboard build REFUSES, naming the collection
       and `mothman dashboard rebuild-results` - reverses REQ-DASH-244's
       recorded "no file reads as no runs" decision.
    4. SODA FAILED-ROWS COUNT (post-build-review #226): FOLD INTO REQ-QAC-247,
       alongside the flag retirements.
    5. AGENCY SHORTS: rs (registry-services) and cpfs
       (child-protection-family-support), as proposed.
    6. REQ-DASH-244 WORDING: correct the title (the agency pill is KEPT) and
       criterion 14's citation (criteria 12 and 13, not 11 and 12).
    7. FILING MENU ORDER: hierarchy order at EVERY size, Birth Registrations
       first - one visible change at two collections.
    8. CONTRACT TEXT: the contract's RICHER text wins; the four descriptions
       the dashboard's thinner words replaced are restored, and the page
       changes with them (a changelog line).
    9. SEEDS (REQ-GEN-246 c2): keep the declared-schedule check and ADD a test
       recording the seeds actually drawn in the existing generation tests.
    10. THIRD-COLLECTION HARDENING: FIX NOW as gate checks and clean refusals,
        test-first - multi-table target trial, unknown lever set, provider
        identity and orphan modules, adapter-less or provider-less collection
        tracebacks, duplicate labels colliding in the TUI.
    11. 252 POLISH: ONLY "filter on short and names" - the picker filter
        matches short, id, label, dataset names and agency. Not the Closest
        ranking, the <short> placeholder or the picker height cap.
    12. FILING MENU LABELS: use the QA menu's label rule (Birth Registrations,
        Child Protection), so the same word finds a collection in every menu.

    REQ-QAC-247's FLAG CALLS, the same evening (~20:20): every brief went
    with its recommendation - the twelve no-change flags unified on Child
    Protection's behaviour with one capture pair for the batch, the Soda
    '[all]' suffix dropped, zero counts kept everywhere (REQ-PIPE-248
    criterion 1 amended), Table-level always and Cross-table only above one
    table, earliest_extract no longer recorded, Soda dimensions read from
    each check's category, the Evidently volume check moved in from 248 and
    unified on Child Protection's, and the Soda count fixed test-first.
    Recorded in full in REQ-QAC-247's decisions.

107. **[todo, 2026-10-18]** **[Docs & process]** **Why is there 77,000 lines
    of product code?** Keith, 2026-10-18: "how the fuck do we have 77,000
    lines of product code? That's ridiculous." Measured the same day: 76,720
    lines of product Python, of which 38,605 are code and the rest
    comments, docstrings and blank lines - roughly half the files are
    prose. By area: qa_tools/common 51,880 (141 modules - the supply
    lifecycle of filing, slots, promotion, decisions, corrections and holds
    alone ~18,600; storage ~5,900; schedule and time ~5,500; checks and
    statuses ~4,100; the `mothman check` validators ~3,000), cli 9,981,
    generator 6,452, pipeline 3,449, dashboard Python 2,225, qa_tools/tools
    2,114; plus the dashboard template's 10,246 lines of HTML/CSS/JS.
    Not scoped: whether the docstrings should shrink (they carry decisions
    and incident history that arguably belongs in requirements.yaml's
    decisions, not in code), and whether the lifecycle's ~40 modules have
    grown more surface than the model needs. Ask Keith which he wants
    looked at, and when, after item 6's chain.

109. **[todo, 2026-10-19]** **[Pipeline & publishing]** **What a period
     schema IS: a release of the asset, or a supply's cadence? Two new
     datasets to stress-test it, and maybe two asset configurations.**
     Keith, 2026-10-19 morning, prompted by the Emergency Department work
     and the parallel-bootstrap race REQ-PIPE-262 fixed. His words: "I've kind of been designing this so at the
     data asset level, there is one schema for each quote unquote release
     of the asset. Rather than multiple schemas that depend exactly on the
     cadence of particular data sets and data collections." He suspects it
     is not built that way: a monthly dataset on a quarterly asset would
     land in its own monthly schemas. "Maybe that's the best way. Maybe we
     don't monkey with that and we put a layer on top, which is about the
     release of the data asset." Two shapes to work through:
     - **A quarterly asset with a monthly dataset.** Today this means
       separate monthly schemas. The alternatives: keep that and add a
       release layer on top that shows the latest of everything, or land
       the monthly supplies in the asset's quarter.
     - **A daily asset with a weekly dataset.** Keith thinks automatic
       inheritance already covers this (the weekly dataset is owed on its
       delivery days and inherits on the rest).
     He wants to talk it through conceptually first, then build **two new
     datasets** to test it in practice:
     - a monthly dataset in a quarterly asset;
     - a weekly dataset in a daily asset.
     Also raised: "This is possibly also the point that we want to split
     this repository into two separate data asset configurations, one for
     the daily asset and one for the quarterly asset" (see CLAUDE.md's
     two-assets target). Not scoped. Talk it through first.

110. **[done, 2026-10-19]** **[Pipeline & publishing]** **Which datasets the
     inheritance rule fills automatically - Keith's own rule, 2026-10-19.**
     "A data set not expected would be automatically inherited. One not
     participating would be automatically inherited, but one turned off
     would not be automatically inherited. The one that is participating
     and hasn't arrived yet should not be automatically inherited." The
     turned-off part differs from signed REQ-PIPE-179 criterion 22 and
     REQ-PIPE-098 criterion 1 (amended), which inherit for a turned-off
     dataset. RECONCILED THE SAME MORNING: shown REQ-PIPE-179 criterion 22
     and his own 2026-10-10 decision behind it (Q-G option A, "for a
     temporary turn-off we probably do want to inherit it"), Keith kept it
     as signed - a turned-off period inherits. Nothing changes; #77 still
     holds the larger question of a dataset removed for good.

111. **[todo, 2026-10-19]** **[Testing & dev tooling]** **A one-collection
     bootstrap, checkpoint or resume of a collection that shares a calendar
     is not its slice of a full bootstrap.** REQ-PIPE-262 replays the
     collections sharing a calendar (Child Protection and Emergency
     Department, quarterly) as one receipt-ordered stream. A `--collection
     cp` bootstrap, and REQ-TEST-159's checkpoints and resume, still replay
     one collection alone, so ED's arrivals do not interleave. The result can
     differ from that collection's part of a full bootstrap: who opened each
     quarter first, and so what each owe-nothing dataset inherits. Keith,
     2026-10-19, answering REQ-PIPE-262's Q1: "Leave as is, follow-up". The
     alternative was widening them to the whole stream (`--collection cp`
     replays ED too, and checkpoint numbers count the merged stream). Not
     scoped.

112. **[todo, 2026-10-20]** **[Docs & process]** **The scale is about 30
     datasets and 10-15 teams, not 30 teams.** Keith, 2026-10-20, while
     talking through #95: "They won't be 30 different teams... It's more like
     15 or so. Some teams own the same data set... realistically it could be
     10 to 15 teams. Like 30 data set asset." CLAUDE.md's scale paragraph
     says "roughly 30 collections on the quarterly asset" and doesn't mention
     teams, so advice phrased as "30 teams" (as in this conversation) has been
     overstating how many groups of people learn and act on each status.
     Ask Keith whether CLAUDE.md should say so.

113. **[todo, 2026-10-20]** **[Pipeline & publishing]** **No flickering
     reds: a red has to be worth notifying someone about.** Keith,
     2026-10-20, while settling #95's shape: "I don't want red flickering. So
     I don't want false positives on reds, because ultimately I think I want
     to automate send notifications on red... I don't want a boy who cried
     wolf scenario." A standing design test for anything that can turn
     something red. Would a person notified on this red have needed to act,
     or would it have cleared by itself minutes later? The early-arrival red
     in #95 (a table held until its partner's file arrives) is the case that
     prompted it. Automated notification on red is not scoped. It relates to
     the ticketing work (#53) and to REQ-GHUB tickets.

114. **[todo, 2026-10-20]** **[Pipeline & publishing]** **"Zip" is a
     stand-in for "a package of files".** Keith, 2026-10-20: "zip is just a
     stand-in for like a package of files. We might find other ways to say
     mark the start and end of a batch of files that aren't a zip container,
     but let's just go with the zip container as the current concept... and we
     can extend that later." Today "arrived together" means the same receipt
     instant (REQ-PIPE-105 c5, REQ-PIPE-265). Other ways to mark a batch's
     start and end belong with the transport layer (plans/supply-thoughts.md).
     Not scoped.
     **Keith, 2026-10-22 (#95's Q9): "A, B later"** - zip-only for now; a
     cloud (S3) package boundary, such as a manifest or an end marker, is to come.

115. **[todo, 2026-10-21]** **[Docs & process]** **Semantic search over the
     project's own memory, alongside the agents.** Keith, 2026-10-21, after
     asking how RAG differs from this project's scoper/architect/reviewer/
     critic workflow: retrieval "as the input to or alongside this set of
     agents functioning as kind of a team". The motivating failure is the
     recurring one where a decision exists but nobody knew to look for it.
     Grep finds only what you already know to ask; semantic search over
     `requirements.yaml` `decisions:`/`open_questions:` and `plans/*.md`
     would answer "have we decided anything like this before?". What the
     environment allows, checked 2026-10-21:
     - PyPI is reachable.
     - huggingface.co (local embedding models), api.openai.com and
       api.voyageai.com are refused by the egress proxy.
     - pgvector is not installed; pg_trgm is.
     So lexical ranking (PostgreSQL full-text search, or BM25) is buildable
     now. Semantic embeddings need an allow-listed model host, or Bedrock in
     an AWS deployment. Not scoped.

118. **[investigate, 2026-10-22]** **[Dashboard UI]** **Is it obvious which
     period a page is talking about?** Keith, 2026-10-22, answering REQ-PIPE-279
     K2 (a result that read no Clients supply shows only on Notifications'
     page, and Clients' page keeps showing its Q2 supply): "this opens up an
     interesting question around how we show [the] period that a page is
     talking about, whether that is clear enough in the UI ... is it obvious,
     or is it clear enough to the user when they're looking at a page?
     Particularly for the quarterly asset, but also for the daily, which
     period is being discussed, which period we are showing information for."
     Sent to the dashboard UX critic against the built dashboard the same day.
     **The critic's answer, same day: no.** Full report:
     docs/drafts/period-clarity/review-ux-critic.md. No tier names the period
     (only the picker and an ED-only block do; pages name the supply by its
     receipt instant); a cross-table red caused by the OTHER table's missing
     period gives no sign of it on the reading table's row or collection row;
     "2026-Q3" is the 1 Aug-31 Oct delivery slot, which readers will take as
     Jul-Sep or the financial-year Q3; an empty current period hides how old
     the shown results are. Also a REAL DEFECT found on the way: the
     "outside the dates" notice's "View <today> instead" and the picker's
     "Reset to default" do nothing when the default date is itself past the
     data (every morning after a build) - needs a failing test first. Three
     questions for Keith in the report.

119. **[todo, 2026-10-22]** **[Dashboard UI]** **Show a check's start time or its
     end time?** Keith, 2026-10-22, answering REQ-PIPE-279 K3 (every
     evaluation its own point, ordered by when it began): "there's also a
     running thought here around whether you show the start time of the
     checks or the end time of the checks". Today pages show receipt and
     recording instants; 279 orders by evaluation start (`run_seq`). Not
     scoped.

120. **[todo, 2026-10-22]** **[QA Pipeline]** **[Dashboard UI]** **How long
     the checks took - and noticing when that grows.** Keith, 2026-10-22,
     same conversation: "showing how long the checks took, and maybe
     alerting, monitoring, something around that. So the check starts at 5
     minutes, 10 minutes, 3 minutes, 3 hours. At some point that becomes
     visually obvious, so you can go and look into it and try and address
     it." `qa.run` already records `created_at` and `completed_at`. Related
     to the pipeline-observability item in plans/wider.md. Not scoped.

121. **[todo, 2026-10-22]** **[Dashboard UI]** **[QA Pipeline]** **Make it
     obvious when a run timed out or crashed before it succeeded.** Keith,
     2026-10-22, answering REQ-PIPE-279 K5 (a retried run takes a fresh place
     in the order): "it should also be obvious somewhere that it did time out
     or crash. Maybe that one for the UX review." Today a retry leaves no
     trace of the failed attempt (`reopen_run` clears `completed_at`;
     results are replaced), so recording attempts would have to come first.
     Display for the UX review alongside #118-#120.

123. **[todo, 2026-10-22]** **[Dashboard UI]** **[Pipeline & publishing]** **Make
     publishing the dashboard part of a routine, so the site cannot silently
     fall weeks behind.** Keith, 2026-10-22, on finding the published site
     still showed 28 September: since REQ-PIPE-092 publishing is one
     deliberate command (`mothman dashboard publish`, from an environment that
     holds the database), no push runs it, and nobody had run it in 24 days.
     His words: "making publishing part of each push's routine, or at least
     something we do at an agreed point where I give you an instruction,
     maybe." Republished from the sandbox the same day (his option A). Not
     scoped: when (every finished, pushed piece of work; or on his word),
     from which environment, and how a stale site would say so.

124. **[todo, 2026-10-23]** **[Pipeline & publishing]** **[Dashboard UI]**
     **Pipeline observability alongside the AWS build - what is running, now.**
     Keith, 2026-10-23, during the #95 sign-off walk-through (step 1, a zip
     filed as one package): "this go[es] alongside the AWS stuff, how we get
     observability of pipelines. I think that will just happen as part of how
     we build the AWS bit, but I'd like some AWS infrastructure side
     visibility of ... what pipelines are running. ... some sort of
     observability UI. It can be basic, and maybe also that is just a pointer
     to ... more observability into something that we're building here,
     whether it's the TUI, whether it's a different view in the dashboard.
     Maybe it becomes the dashboard integrates with AWS APIs and pulls
     real-time information." Belongs with this file's Thread B (the AWS MVP,
     AWS CDK in Python) and plans/wider.md's pipeline-observability item;
     related to #120 (check durations) and #121 (showing a timed-out or
     crashed run), which REQ-PIPE-279's run-attempt record and per-attempt
     lock will feed. Not scoped.
     **Added 2026-10-24 (Keith: "leave until AWS")**: the run lock's own
     weakness belongs here too (post-build-review #262 R3). The lock rides
     one idle connection with no TCP keepalive, so a dead host holds it
     ~2h (every retry refused meanwhile), and a dropped lock connection -
     an AWS NAT gateway cuts idle TCP after ~350s - lets a second attempt
     close the live one and both write, the first's end updating no row
     silently. Options weighed: keepalives on the lock connection plus a
     refusal when an attempt's end updates no row (small); a heartbeat
     column the next attempt checks (bigger, also covers a hung process).
     Decide when the AWS build is scoped.

125. **[todo, 2026-10-25]** **[Docs & process]** **[Testing & dev tooling]**
     **A real builder agent, if delegated building stays.** Over the week of
     2026-10-18 the main session drifted into handing coding work to
     general-purpose agents ("builders") and keeping orchestration - gates,
     pushes, CI, morning reports - for itself. It was never agreed or
     written down (nothing in CLAUDE.md or docs/agent-orchestration.md), and
     Keith noticed it on 2026-10-25. His call: "if we were to keep this
     practice, we'd want to actually build a builder agent". Until then:
     small things the main session builds itself, larger things go to a
     builder.
     What the main session told him it buys: its own context stays clear of
     diffs and test logs across a long or overnight run; two builders can
     run in separate worktrees (A3 beside the morning answers, 2026-10-25);
     the main session stays free to answer, check CI and gate. What it
     costs: detail lost both ways in the hand-off (a false "f861ee4 passed a
     full gate" was carried through one on 2026-10-24); a builder's report
     is a claim to re-verify, not proof; more tokens; and it sits outside
     the `delivery-*` pipeline the project actually designed.
     A builder agent would make that explicit: a `.claude/agents/` file
     whose brief carries the standing rules (failing test first, register
     fields at `built`, commit claims only from runs of that tree, never the
     real `supply` database, a scratch DSN and MOTHMAN_TEST_DB_TAG, no push,
     no full gate), what it must report, and where it sits in
     docs/agent-orchestration.md relative to the scoper, architect and
     critics. Not scoped - goes to the scoper first.

     **KEITH, 2026-10-26 morning, after the overnight run: discontinue
     working builder agents in parallel.** That night ran five builders and up
     to four critics at once; the load reached ~28 on 4 cores, the account hit
     its session limit twice (about three hours lost, every background run
     killed when PostgreSQL restarted), and the lanes collided - a builder's
     pattern `pkill` able to kill other lanes' tests, an `npm ci` through
     symlinked worktrees emptying the main checkout's node_modules, and
     hand-resolved merges of the same terminal-queue code three times. From
     here on: one builder at a time. Also his call the same morning: hold the
     next push until all the queued work is done.

126. **[todo, 2026-10-25]** **[Data generation]** **The next synthetic
     dataset uses more than one identifier.** Keith, 2026-10-25, while
     scoping the linkage product: Linkage Keys carries `id_1` .. `id_n`,
     one per identifier column of the source dataset, because some real
     datasets are keyed by more than one. Both synthetic linked datasets
     (Client Register, ED Presentations) have a single key, and he chose not
     to invent a second one for ED. So the several-id case is proven only by
     fake datasets and a planted scenario until the next real synthetic
     dataset is added - which should be keyed by two or more columns on
     purpose, so a real page shows it.

127. **[todo, 2026-10-26]** **[Pipeline & publishing]** **[QA checks &
     contract]** **Re-run FILE checks after a file check's bug is fixed,
     without asking the supplier to resend.** Keith, 2026-10-26, on the L3
     critic's provisional call that a bulk re-check of a fixed FILE check
     refuses and says file checks run again only when the supply is resent:
     "if we fix the bug in how we parse ... I'm not going to ask the guys to
     resend it. You already have the file or files. We can just re-trigger it
     ourselves." Probably the same shape as REQ-PIPE-177's bulk re-check for
     table checks, possibly its own interface, terminal first. Re-running the
     pipeline does NOT do it today: re-staging an unchanged delivery writes no
     new load record (`load_log.record_load` is silent on a repeat, by design)
     and `file_checks.record` writes nothing without a load attempt, and
     `mothman pipeline run` refuses over recorded history anyway. The files are
     kept (data/deliveries, the S3 bucket in the cloud design), so the inputs
     exist. Needs scoping before building.

128. **[done, 2026-10-28]** **[Docs & process]** **A 10-minute repeating
     wake-up while any agent is running.** Keith, 2026-10-28, after the
     container went to sleep twice in one day and stopped a running builder
     and its test run each time: "Set a policy of having a 10 minute wake up
     on scheduled repeat while an agent is running, so we don't lose work."
     Written into CLAUDE.md's working-style conventions the same day. A
     wake-up does not stop the container sleeping; what it buys is that the
     session comes back within ten minutes and resumes the stopped agent
     (SendMessage to its id) instead of the work sitting dead until Keith
     next looks. Agents also commit local checkpoints as they go, so a stop
     loses minutes rather than hours.

129. **[todo, 2026-10-30]** **[Pipeline & publishing]** **Revisit the
     one-off project extraction shape next week.** Keith, 2026-10-30, while
     deferring the geocoding questions: a dataset with no calendar is refused
     by REQ-PIPE-331 criterion 2 today, so how a cadence-less project
     extraction reads or is read by an asset-level product is undecided.
     Needs scoping with him before anything is built.

130. **[todo, 2026-10-30]** **[QA checks & contract]** **Small-count
     suppression as a generic binned rule.** Keith, 2026-10-30: REQ-QAC-333
     criterion 9 shows the large-key-group histogram exactly, with no
     suppression, but a later need to suppress small counts (privacy, for a
     real linkage unit's release) should be one generic rule on the binned
     distribution field (qa_tools/common/distribution.py), declared with the
     check, not a linkage special case. Not scoped.

131. **[todo, 2026-10-30]** **[Dashboard UI]** **Seeing everything recorded
     about a period, including results that arrived late.** Keith,
     2026-10-30 ~23:50, prompted by the REQ-DASH-337 critic's J1 (post-build
     review #289). He asked: "How can we view the results for a whole
     period?"

     Today he can't. Every dataset page is as-at a date, and shows the supply
     in place then with the results known by then. Child Protection's next
     supply lands at 9am on a round day, and the linkage release that reads
     the previous one lands at about 5:30pm the same day. So a linkage
     verdict about a Client Register supply arrives after that supply has
     been replaced, and no current page shows it on Client Register.

     The period page (REQ-DASH-209) is one table per collection per period:
     what each dataset holds there, how it got there, who decided, and the
     status when promoted. It shows no check results.

     Options put to Keith, not yet chosen:
     - (a) put results on the period page, each dataset's own checks plus
       cross-collection results recorded about that period, as known now;
     - (b) let the dataset page open by period as well as by date;
     - (c) both, the period page linking to each dataset's period view.

     He asked to see the current period page first, and was shown CP 2019-Q1
     as at 15 March 2019. Not scoped; not part of the Linkage Products push.

     **GLOBAL, NOT ONE DATASET (Keith, 2026-10-30, ~23:55)**: "I'd also want
     this fix to apply globally, not just to one dataset." Whatever is built
     applies to every dataset and every collection, through one generic rule:
     any result recorded about a period's supply, whenever it arrived and
     whichever collection's check recorded it. Linkage Products and Client
     Register are the first case to show the gap, not the scope of the fix.

     **A PERIOD VIEW, ALONGSIDE AS-AT (Keith, 2026-10-31 morning, answering
     the geocoding batch's J1/G1 surfacing question - he rejected all three
     options put: accept, a quiet notice, or move the timing)**: "what we need
     here is a new way to view the dashboard ... almost by period."
     - Mostly for the quarterly asset, but applied to every cadence; it does no
       harm on a daily asset, where you would just choose the day, and is
       valuable for weekly or monthly ones.
     - For a quarterly refresh and release he needs TWO DISTINCT VIEWS:
       - what we know about the source data arriving now, for the period it
         is coming in for (the next period);
       - what we know about the linkage products and geocoding arriving for
         the current period. Those are distinct, separate releases, almost
         separate work streams.
     - "Show me what we know about this period", most likely ALONGSIDE the
       as-at control rather than instead of it: for this period, what do we
       know as at this time.
     - THIS REOPENS A RECORDED DECISION, said so to Keith: REQ-DASH-054's
       decisions (2026-09-23) kept the picker a plain date and REJECTED a
       period picker beside it. The reason given was that a period name is
       ambiguous at asset level once several calendars exist, so it "could only
       ever sit beside the date, not replace it". Beside the date is what
       Keith is now proposing.
     - Not scoped. It supersedes the geocoding batch's J1 question.
     - SEQUENCING (Keith, same morning): geocoding does NOT wait for this; scope,
       discuss and review the period view alongside the geocoding build.
     - KEYED BY PERIOD, NOT BY ROUND (Keith, same morning, (a)): a view of
       2026-Q2 shows everything known about Q2. That is the source supplies
       filed to Q2, which arrived in an earlier round, and the linkage and
       geocoding releases for Q2, which arrive in a later round, in two
       sections, one per workstream. The as-at time is picked within it.
       REJECTED (b), a view by round or refresh (sources for Q3 beside linkage
       for Q2), and (c), both views.
     - A GLOBAL PERIOD CONTROL, BESIDE THE GLOBAL AS-AT CONTROL (Keith, same
       morning): "something like another global 'as at' control ... that's what
       I want". It sits in the header, is carried in the URL and kept across
       navigation like as-at, and every page reads it: agency, collection and
       dataset pages show that period's supply and results as at the date on
       show, including linkage and geocoding verdicts that arrived later. With
       no period chosen, every page behaves as today.
       REJECTED growing only the existing period page (REQ-DASH-209) into the
       view. How the period page relates to the new control is still open.
     - ONE BASELINE CALENDAR PER ASSET, SO SPLIT THE PoC INTO TWO FAKE ASSETS
       (Keith, same morning, answering how the period control handles an
       asset with several calendars): "the thing we've been putting off for a
       while ... splitting this to have two different fake data assets. One's
       the quarterly one, one is the daily one ... each data asset needs to have
       a single baseline calendar". This makes the period control unambiguous,
       since a period means one thing within an asset. It is the split already
       raised in #55 (how configuration is organised with two assets) and #109
       (a monthly dataset in a quarterly asset, a weekly one in a daily asset,
       "possibly ... the point that we want to split this repository into two
       separate data asset configurations"). "Baseline" leaves room for a
       dataset on another cadence inside an asset, which is #109's question.
       This makes the period control depend on the split, or on a rule for the
       one combined asset in the meantime.
     - SEQUENCING (Keith, same morning, (c)): scope the split and the period
       control TOGETHER now, the period control written against the post-split
       shape (one baseline calendar per asset), then build the split first and
       the period control after. REJECTED (b), a period control on today's
       combined asset with an interim rule for Birth Registrations.
       Geocoding builds in parallel and waits on neither.
     - REPOSITORY SHAPE FOR THE SPLIT (Keith, same morning, #55's options):
       (a) ONE REPOSITORY, A CONFIGURATION FOLDER PER ASSET, for the PoC now.
       FLAGGED AS A FUTURE DECISION POINT, in his words, "once this needs to
       migrate out of PoC stage": (b) a repository per asset, or (c) shared code
       and checks with each asset's configuration injected at deploy time.
     - THE SPLIT INCLUDES #109's TWO DATASETS (Keith, same morning, (b)): a
       monthly dataset in the quarterly asset and a weekly one in the daily
       asset, so the period control is designed against off-baseline cadences
       from the start. #109's conceptual question comes first: is a period
       schema a RELEASE of the asset, or a supply's own cadence?
       REJECTED (a), splitting with today's datasets only.
     - WHAT A PERIOD SCHEMA IS, SETTLED (Keith, same morning, answering
       #109). None of the three options put: "a data asset has to nominate a
       baseline calendar, whether that's quarterly or monthly or daily. And then
       everything else has to fit around that."
       - NOTHING FASTER THAN THE BASELINE. A quarterly asset cannot hold a
         monthly dataset.
       - SLOWER IS PARTICIPATION IN A SUBSET OF BASELINE PERIODS. A dataset on
         a quarterly asset may be owed in two quarters a year, or annually,
         meaning one quarter a year.
       - TO GO FASTER, CHANGE THE ASSET. A monthly dataset on a quarterly asset
         means changing the asset's baseline to monthly, then re-expressing
         every quarterly dataset as owed only in certain months.
       So a period schema is one baseline period, which is one release, and
       there is never a second cadence of schemas inside an asset. REJECTED
       per-cadence schemas, with or without a release layer.
       #109's own question is answered by this. Its two test datasets need
       re-thinking, since a monthly dataset in a quarterly asset is now
       refused by design.
     - #109's TEST DATASETS, REPLACED (Keith, same morning, (a)): an annual or
       twice-yearly dataset in the quarterly asset, using `participates:` as
       built (named delivery months plus a reason, contract/calendar.yaml), and
       a weekly dataset in the daily asset, which needs NEW participation by
       weekday because `participates:` names months only. The refusal of a
       dataset faster than its asset's baseline is proven by a gate test, not
       by a dataset.
     - SUPERSEDED (Keith, 2026-10-31, after the architect review): ONE CLOUDFLARE PROJECT PER ASSET, each with its own Access allow-list, because REQ-PIPE-255 uploads a whole tree. See docs/drafts/asset-split-answers.md.
     - TWO DASHBOARDS ON ONE SITE (Keith, same morning, (a)): two separately
       built dashboards, e.g. /quarterly/ and /daily/, each built only from its
       own asset's database, with a plain landing page linking them. REJECTED
       (b), one dashboard with an asset switcher, which mixes both assets into
       one build, and (c), two entirely separate sites.
     - DRAFTED 2026-10-31: docs/drafts/asset-split-v1.yaml (REQ-PIPE-342 to
       REQ-DOCS-358, 17 requirements), with five questions for Keith: Q1 the
       period page, Q2 asset ids, Q3 the test datasets, Q4 how amendments are
       signed, Q5 a cost budget. Next: architect and UX review, then sign-off.

     **THEN (~midnight)**: Keith floated a period mode on the "as at"
     switcher as the place for it. Before any requirement was drafted he
     said "Hmm maybe it's OK as it is". So nothing is scoped or built. Left
     here as a possible idea to come back to, not a commitment.

132. **[todo, 2026-10-31]** **[Dashboard UI]** **[Pipeline & publishing]** **Pass / Warn / Fail everywhere, replacing Green / Amber / Red.**
     Keith's decision, 2026-10-31 late morning. It came up when he asked "when
     the hell did we decide to change the language?", because the
     cross-table grid's cells read Pass / Warn / Fail while every other place
     reads Green / Amber / Red. He was shown that the grid's words were a
     builder's PROVISIONAL choice for REQ-DASH-272 (2026-10-25), never put to
     him, and offered three options: (a) Green / Amber / Red everywhere, (b)
     Pass / Warn / Fail in the grid only, (c) Pass / Warn / Fail everywhere.
     He chose **(c)**, confirmed when asked which direction. That means status
     pills, dataset rows, agency cards, group headings, the terminal's words
     and the Python status mirror all change.
     NOT SCOPED YET. Needs an inventory of every occurrence, including
     compound labels ("Red promoted", "Amber promoted", the amber tag), prose
     ("went amber", "the amber band"), CSS and data values versus displayed
     words, the CLI, the changelog and docs. Then a requirement, sign-off and
     the post-build-review note of how the provisional word slipped through
     (post-build-review #292). Interacts with the geocoding batch's heading-count
     question (REQ-DASH-299 Q1), which now follows this decision.

133. **[parked, 2026-10-31]** **[Pipeline & publishing]** **[QA checks & contract]** **Rename the configuration and the stored values to Pass / Warn / Fail too.**
     Keith, 2026-10-31, answering the relabel's depth question: displayed
     words only for now (running-thoughts #132), and "b/c parked for later".
     (b) is the configuration people type: `amber_setting`,
     `replacement_setting`'s values, `--dirty amber|red`, `green-or-amber`.
     (c) is everything, stored database values and the status constraint
     included, which means a migration. Not scoped. Pick it up once the
     displayed relabel has landed.

134. **[investigate, 2026-10-31]** **[Data generation]** **[Pipeline & publishing]** **The synthetic data generator and the bootstrap as separate components, strictly separated from each other and from the real pipeline and asset configuration.**
     Keith, 2026-10-31: "I would like the synthetic data generator and the
     bootstrap to be separate components with a strict separation between
     themselves and with the actual pipelines and asset configuration ...
     They will still be in the same repo." He asked for a high-level scan of
     how close the code is to that today. The scan's findings are added below
     once reported. Not scoped.
     **SCAN, 2026-10-31 (high level, grep only)**:
     - The pipeline never imports the generator (qa_tools, pipeline and
       dashboard have no `import generator`). Only cli/ wires the two.
     - The generator imports the pipeline heavily: 63 imports from qa_tools,
       mostly asset_time, hierarchy, schedule and slots, the shared domain
       model. Also correction_trial, correction_apply, promotion,
       scripted_decisions, scenario_map and the collection registry.
     - The bootstrap and replay machinery lives INSIDE the pipeline package:
       qa_tools/common/bootstrap, checkpoints, replay_clock, replay_inputs,
       scripted_decisions, scripted_corrections, correction_replay, scenarios,
       scenario_map and target_agreement, about 4,800 lines. replay_clock is
       woven into about 20 real pipeline modules (stage, orchestrate, gate,
       filing, decision_log, ...), and orchestrate plays scripted decisions.
     - Synthetic-only configuration is mixed into asset configuration:
       `synthetic: true` and the "synthetic eras" in contract/data-asset.yaml's
       amber setting; contract/scripted_decisions.yaml. The planned
       contract/synthetic_inputs.yaml would add another.
     - **DECIDED (Keith, 2026-10-31, (a))**: the CONFIGURATION half is folded
       into the asset split now. Synthetic-only configuration gets a home of
       its own beside each asset's folder, e.g. synthetic/<asset>/: scripted
       decisions, synthetic inputs, synthetic eras, the `synthetic` flag's
       consequences. The CODE half (the bootstrap and replay machinery out of
       qa_tools, the replay clock untangled from the real pipeline, the
       generator's imports narrowed to the shared domain model) is scoped
       afterwards as its own batch. REJECTED (b), the whole separation after
       the split, which moves the configuration twice, and (c), the whole
       separation before the split.
