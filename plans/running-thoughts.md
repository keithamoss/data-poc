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

Idea: have the GitHub Issues ticketing system (#1) post live updates
into a Microsoft Teams chat as datasets arrive and get QA'd - possibly
with a small piece of the gamification idea (#3) folded in, celebrating
individual staff members' wins in the Teams feed itself. Keith's own
framing: "do some research online" first - this is a research task
(what's actually possible/idiomatic for a GitHub Issues -> Teams
webhook/bot integration, not yet a build task).

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

## Also flagged, queued separately (not part of the "running thoughts"
batch above, but landed in the same conversation)

- **Child Protection resupplies**: CP's generator has zero resupply-
  chain concept today (confirmed while building item 73's redesign,
  `generator/generate_cp_runs.py` - pure periodic full-collection
  snapshots, no resupply simulation at all - see
  `plans/conceptual-design.md` Thread A). Keith wants to add realistic
  CP resupplies too. Explicitly sequenced: "once you're done with this
  loop" - not urgent, but real, queued work, not just an idea.
- **CI monitoring shouldn't block the loop**: amended in CLAUDE.md's own
  standing convention (the "check real CI" bullet) rather than logged
  here - a process fix, not a project idea.
