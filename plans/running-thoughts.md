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

### 1. Ticketing system: GitHub Issues, MVP after this loop

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

### 2. Data-asset-level people/roles config

A new config file (alongside `contract/data-asset.yaml`'s existing
data-asset-level, not per-dataset, scope) listing the people who work on
a data asset: name, email, nickname, and optionally which
datasets/agencies they're assigned to. People carry one or more roles
(QA, peer review, manager mentioned so far - likely not an exhaustive
list). Purpose: drives the GitHub Issues ticketing system above - who a
ticket gets assigned to, and probably who's allowed to do what (e.g.
peer review vs. the original QA-er). Explicitly tied to idea #1, not a
standalone piece - scope together.

### 3. Gamification MVP on the reporting dashboard

A small MVP that celebrates staff turning QA around fast, or
consistently getting green datasets - "some kind of gamified thing."
Genuinely vague still ("we can talk about that") - no shape decided
yet (leaderboard? badges? a streak counter? per-agency vs. per-person?).
Needs a real scoping conversation before building anything, not just an
implementation guess.

### 4. GitHub Issues -> Microsoft Teams integration (research first)

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

### 5. Staff adoption - two threads

Motivation: Keith wants staff to actually start using this tool/
pipeline for real, not just as a PoC demo. Two genuinely separate
threads:

**Thread A - fit into today's actual workflow.** Staff currently pull
data down from S3 buckets or local storage themselves. Whatever this
tool becomes needs to fit that existing motion, not replace it outright
on day one.

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

### 6. Read-only tension: accepting/rejecting Amber supplies

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

### 7. Business requirements page on the dashboard

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

### 8. Deep links from the dashboard back into GitHub

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

### 9. Human-friendlier URLs

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

### 10. Expose the planning markdown files in the dashboard (MVP)

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

### 11. Switch pytest-cov from line/statement coverage to branch coverage

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

### 12. Local pytest/Playwright runtime - real profiling done, more possible

Keith's own follow-up question (2026-09-18): "it's taking a while to
run pytest and Playwright locally, is there anything we can do to speed
that up." Real `pytest --durations=25` profile found `tests/
test_generate_runs.py` alone cost ~52s (32% of the then-163s suite) -
all 6 of its tests independently called the real generator fresh for
identical, deterministic output. Fixed (2026-09-18): a single
`scope="module"` fixture generates once, all 6 tests read it - real
~43s saved, full suite now 163s -> a measured 120s, zero coverage lost.

Still open, not yet done - explicitly grouped with item #11 above for
the same weekend planning loop, not picked off individually:
- `pytest-xdist` (parallel test workers) - flagged as worth revisiting
  once the real-tool integration tests actually landed (CLAUDE.md's own
  note); not yet installed. Real open question before adopting it: do
  the real dbt subprocess calls different test FILES make collide on
  dbt's shared `dbt_project/target/` default when run in PARALLEL
  workers, the same class of problem `qa_tools/common/
  parallel_orchestrate.py` had to fix with a `--target-path` per run for
  the real orchestration scripts - not yet checked for the test suite's
  own dbt-based tests.
- The remaining ~70s of real dbt-core/datacontract-cli integration test
  cost is closer to the genuine floor (actually invoking real tools,
  not mocked) - xdist parallelism is the more promising lever here than
  further fixture restructuring, once the collision question above is
  answered.
