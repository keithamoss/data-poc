# Supply lifecycle and delivery

How a data supply is modelled end to end - how it arrives, where it is
filed, when it is checked, what makes it into the warehouse, and what
the dashboard says about all of it - plus the delivery plan for building
that.

Created 2026-09-21 (Keith's own ask, at the end of a long day of design
and stress-testing) by moving the whole of that day's work out of
`plans/publishing-and-history.md` item 6 and into a standalone file.
Item 6 keeps its original subject - the copy-paste file-per-dataset
problem and the agency/collection/dataset hierarchy - and points here
for the supply model the eight requirements it spawned now sit on.

**Why this is a separate file rather than more of item 6.** Item 6 is
about CODE ARCHITECTURE: how many near-identical modules this repo needs
per dataset. What grew inside it is about a DOMAIN MODEL: what a supply
is, what a slot is, who decides what. They interact, but they are
different subjects with different lifespans - the file-architecture
question will be answered once and closed, whereas this model is the
thing the system is built around from here on.

**Where the real decisions live, and what is still conversational.**
Every Thread below is settled design, agreed with Keith on 2026-09-21,
and NOT yet built - status `todo` throughout. None of it has requirements
written against it yet beyond the eight that predate it
(`REQ-PIPE-034`..`REQ-DASH-041`, all `not_started` and all UNSIGNED), and
`CLAUDE.md`'s sign-off gate applies before any of it gets built. Per that
same file's standing rule, this prose is working material: it gets
deleted as requirements land, with anything it knows that a requirement
does not moved into that requirement's own `decisions:` first.

**One requirement is already known to be wrong.** `REQ-PIPE-035` ("QA
runs against a warehouse composed of every table's current version") was
written before cross-period composition was dropped - see Thread J. It
needs rewriting rather than building.

Status values: `todo` / `investigate` / `in-progress` / `parked` /
`done` / `superseded`. Every item also carries a Component tag - see
`plans/running-thoughts.md` item #10 for the shared taxonomy this,
`plans/*.md` and `CHANGELOG.yaml` all use. Sprint IDs (`supply-model-N`)
are permanent once assigned - never renumbered or reused, same rule as
every other plans file.

## Next steps

**Priority: work through in THIS ORDER (Keith, 2026-09-21 night, his own
words setting the queue): "let's work through the still open items that
you've got logged... and then we'll do one last stress test using chaos
engineering. And then we'll work up a delivery plan and then start
feeding them to the delivery scoper after that."**

1. **Close the open items** listed below.
2. **One last chaos-engineering stress test** of the settled model.
3. **Work up a delivery plan** - first pass is the sprints below, written
   2026-09-21 night; it wants reviewing with Keith rather than treating
   as agreed.
4. **Then** feed requirements to `delivery-scoper` - batch one (storage
   and supply model) first, the readers batch after, per the two-batch
   split agreed 2026-09-21.

Step 4 comes LAST. Batch one was described as "ready to fire" earlier
that same evening, before this sequence was set - do not act on that.

**The still-open items, as at end of 2026-09-21:**

- **Does re-filing exist as its own operation?** It may be forced anyway,
  since promote + demote compose into it. See Thread G.

  *Prepared 2026-09-21 night, for the morning.* Two options: **(A) no
  re-file operation** - demote, then promote to a chosen slot, two
  existing operations composing; **(B) an atomic re-file**, moving a
  supply from period A to period B without passing through staging.

  The argument that actually separates them is the DECISION LOG, which
  is the reason the log exists rather than a detail of it. Under (A) a
  re-file appears as two entries - a demote and a promote - and a reader
  a year later has to infer they were one act. Under (B) it is one
  entry with a from-slot, a to-slot and one reason. "Why is this supply
  in Q3?" has a single answer instead of a correlation exercise. That
  points at (B).

  **But the two open questions here are entangled and should be answered
  together.** Thread G's own unresolved question is whether "un-decide"
  (demote back to staging for re-review) is an operation worth having at
  all. If NO, demote only ever goes to rejected, nothing passes back
  through staging, and re-file MUST be atomic - (B) is forced. If YES,
  demotion needs its stickiness rule regardless, and (A) becomes viable
  again. So answer "do we want un-decide?" first; the re-file answer
  largely falls out of it.
- **What happens to a `nodata` supply** under the amber-or-green
  auto-promotion rule. `nodata` is neither, and a supply where no check
  ran is not evidence of good data. See Thread B.

  *Prepared 2026-09-21 night, for the morning - and the question has
  probably changed under us.* This was logged BEFORE the red-for-unrun
  decision (Thread I). Since a check that could not run is now RED, a
  supply whose checks all failed to run is RED too, and red never
  auto-promotes. **That case is already resolved**; it wants confirming
  rather than deciding, the same way "what a `run` means" does.

  What is left is a different and arguably sharper question: **a table
  with NO CHECKS DEFINED AT ALL.** Nothing failed to run, because there
  was nothing to run. `worstOf()` over an empty list is seeded `"green"`
  (verified in the template), so such a supply is green by vacuum and
  auto-promotes with no quality signal whatsoever behind it.

  That is a false green of a kind none of the day's work addressed -
  every other case we found was a real signal being swallowed, whereas
  this is the absence of any signal reading as a good one. Worth
  deciding deliberately: does a table with no checks auto-promote, and
  is "this table has no checks defined" itself a finding the dashboard
  should surface as a coverage gap? At 30 datasets, a table quietly
  carrying zero checks is very easy to never notice.
- **Cross-cadence check period ownership** - which table's period is a
  check's period when it spans tables on different cadences. Moot within
  Child Protection; a cross-COLLECTION problem, possibly deferrable. See
  Thread I.
- **Operator identity** in a deployed environment - already marked
  deliberately deferred to build time, listed here so it is not mistaken
  for an oversight. See Thread G.
- **Whether to build an as-published RECONSTRUCTION path at all**, given
  snapshots already provide that view. Both are computable from the
  append-only decision log; the question is whether the reconstruction
  earns its place alongside the archive. See Thread K.
- **"Current version" vs "good version"** - inherited from
  `plans/publishing-and-history.md` item 6, still open, adjacent to
  `plans/conceptual-design.md` Thread A's amber accept/reject governance
  and to be settled with it rather than separately.
- **What a "run" means for supply history** - also inherited from item 6,
  and needs RE-CHECKING rather than answering fresh: the per-table slot
  decision (Thread F) and dropping the date from `run_id` (Thread A) may
  already have resolved it.

## Delivery sprints

First pass, 2026-09-21 night, at Keith's request - and deliberately cut
SMALL (his own instruction: "I don't want any large chunks of text and
overly large sprints"). Each is one coherent deliverable that can be
built and verified on its own. Ordered by real dependency, not size.

Two things drove the order. **Some work is a precondition that gets
expensive if deferred** - a check's identity, and status parity between
the two status implementations. And **the slot is the spine**: overdue,
staleness, assignment, classification and promotion are all defined as
comparisons against the expected-supply sequence.

1. **[todo, 2026-09-21]** **[QA checks & contract]** **Check identity.**
   `REQ-QAC-039` - one hierarchy, stated once, including in a check's own
   `check_id`.

   First because it is baked into all 257 hand-authored checks; changing
   it later is a corpus-wide edit.

2. **[todo, 2026-09-21]** **[Pipeline & publishing]** **Status parity
   between the two implementations.** `qa_tools/common/dataset_status.py`
   has no `nodata` at all, so a recorded `nodata` falls through to
   threshold math and returns green (Thread I).

   Must land BEFORE per-check `nodata` exists, or the new status meets a
   silent misgrade on arrival - `plans/qa-pipeline.md` item 74's exact
   failure mode, which that module's own docstring says it already
   suffered once.

3. **[todo, 2026-09-21]** **[Pipeline & publishing]** **Timezone
   parameter.** One repo-wide config value replacing
   `pipeline/cadence.py`'s hardcoded `AWST_OFFSET`; stored timestamps
   carry their offset (Thread H).

   Small, independent, and every later sprint compares instants.

4. **[todo, 2026-09-21]** **[Pipeline & publishing]** **Schedule config
   and its validation gate.** Authored dates (quarterly) or cadence rule
   (daily), `delivery_months` participation, `effective_from` plus
   changelog, `not_expected` (Thread C); `mothman check`'s
   `validate-config` (Thread K).

   The gate ships WITH the config, not after: a typo silently yields zero
   slots, which is the exhausted-schedule state arriving by accident.

5. **[todo, 2026-09-21]** **[Pipeline & publishing]** **Slots.** The
   `(period, due_at)` sequence derived from the schedule, the low-runway
   warning measured in slots, and the hard failure on an exhausted
   schedule (Thread C).

   The spine. Nothing downstream can be built before it.

6. **[todo, 2026-09-21]** **[Data generation]** **Generator delivers one
   table at a time.** `REQ-GEN-040`.

   Sits here because it is what makes the next three sprints testable at
   all - every rule in them is about awkward arrival sequences, and none
   can be exercised while the generator only emits whole deliveries.

7. **[todo, 2026-09-21]** **[Pipeline & publishing]** **Arrival and
   staging.** Our own receipt timestamp, never the supplier's; staging
   asserting only arrival facts; replay in arrival-timestamp order
   (Threads B and H).

   Arrival order is load-bearing, not tidiness: assignment reads slot
   state, so discovery order changes the answer.

8. **[todo, 2026-09-21]** **[Pipeline & publishing]** **Slot
   assignment.** Claim windows, on-time-wins-for-the-current-slot,
   monotonic filling, and hold-for-a-human when nothing is confidently
   claimable (Threads E and H).

   The highest-risk sprint in the plan - two cascades were found here by
   stress-testing, one created by the fix for the other.

9. **[todo, 2026-09-21]** **[Pipeline & publishing]** **Arrival
   classification.** Early / on-time / late against the ASSIGNED slot,
   never a slot re-derived from the arrival date (Thread D).

   Separate from sprint 8 so the assignment rules can be verified before
   anything reports on them.

10. **[todo, 2026-09-21]** **[Pipeline & publishing]** **Promotion and
    rejection.** Auto on green/amber into an EMPTY slot; red never;
    landing in a filled slot never (Thread B).

11. **[todo, 2026-09-21]** **[Pipeline & publishing]** **The decision
    log.** Append-only; who, when, what, which, why; automated decisions
    recorded the same way with the rule as actor; demotion stickiness
    (Thread G).

    Pairs with sprint 10 and could merge with it, but kept separate
    because it is what makes mutable filing safe and deserves its own
    verification.

12. **[todo, 2026-09-21]** **[Pipeline & publishing]** **One database,
    many schemas.** Retire the per-run warehouses; one database per test
    worker (Thread J).

    Test isolation is deliberate here, not incidental - the per-run
    databases were providing it by accident and `pytest-xdist` is the
    default.

13. **[todo, 2026-09-21]** **[Pipeline & publishing]** **`qa_results/`
    keyed per dataset.** `REQ-PIPE-038`, including regenerating today's
    history under Keith's one-off exception.

14. **[todo, 2026-09-21]** **[Pipeline & publishing]** **Per-dataset QA
    trigger.** `REQ-PIPE-036` - a dataset's own arrival triggers its own
    QA run.

15. **[todo, 2026-09-21]** **[QA checks & contract]** **Check
    dependencies.** `depends_on` on multi-table checks plus its
    validation, and `REQ-QAC-037` lifting cross-table checks to the
    collection scope (Thread I).

    The `nodata` rule is not computable without `depends_on` - "any table
    it spans" is not knowable from a tool's check syntax.

16. **[todo, 2026-09-21]** **[QA checks & contract]** **Red-for-unrun.**
    The status, its qualifying chip, and the pointer indicator on a
    healthy table blocked by a neighbour (Thread I).

17. **[todo, 2026-09-21]** **[QA checks & contract]** **Drift and trend
    dependencies.** A declared temporal reference; missing-but-expected
    is red, no-prior-period is `nodata`. Includes REWRITING
    `REQ-PIPE-035`, which specifies the composition Thread J dropped.

18. **[todo, 2026-09-21]** **[Dashboard UI]** **Supply history and
    as-of under per-dataset arrivals.** `REQ-DASH-041`.

19. **[todo, 2026-09-21]** **[Dashboard UI]** **Freshness axis and
    banners.** Freshness capping the headline status; the
    exhausted-schedule banner (computed from config, so it renders even
    when the pipeline that would have produced results did not run);
    arrival-into-a-filled-slot; the blocked-check pointer (Threads C and I).

20. **[todo, 2026-09-21]** **[Dashboard UI]** **Decision-log display and
    the as-corrected default** (Thread K).

21. **[todo, 2026-09-21]** **[Dashboard UI]** **Automatic snapshots**, on
    every publish, deduplicated by content hash (Thread K).

**Why the dashboard sprints come last**: they render everything above.
Building them earlier means building against a data shape still moving -
which is how `clipDatasetToAsOf()` ended up filtering on arrival rather
than promotion (Thread H), correct only because promotion did not yet
exist.

**Not in these sprints, deliberately.** Adding two more datasets and
making the data-asset level concrete (`plans/running-thoughts.md` #23)
is sequenced AFTER this work - it is what makes the file-architecture
question in `plans/publishing-and-history.md` item 6 answerable, and it
needs the model here to be real first.

## Thread A - Storage and the physical model
**Status:** todo (2026-09-21) · **Category:** Pipeline & publishing

### Composition and the physical storage model - SETTLED 2026-09-21

Worked through with Keith over a long back-and-forth. Recorded here
because the requirements in this file's batch (point-in-time
composition, backfill, the three-state supply model, multi-table
checks) all depend on it, and because several of the answers came
from how his real operational database already works rather than
from anything derivable here.

**How composition works TODAY: it doesn't.** Established by reading
the code, not assumed. There are three DuckDB shapes and none is a
point-in-time assembly - `data/duckdb_runs/<run_id>.duckdb` (BDM, one
table, only that run's rows), `data/cp_duckdb_runs/<run_id>.duckdb`
(CP, six tables all `CREATE OR REPLACE`d from that run's CSVs), and
`data/warehouse.duckdb` (BDM only, every run's rows with a `run_id`
column, built for the dashboard's own queries). The per-run
warehouses are what dbt and Soda point at, and each is a sealed silo -
`build_per_run_warehouses.py`'s own docstring says why (the tools have
no `run_id`-scoped `WHERE`, so a per-run verdict needs a database
holding exactly one run).

Two consequences worth being explicit about, because they are not
bugs, they are things that were never built:
- **CP's cross-table checks only work by accident of the generator.**
  Every CP run delivers all six tables, so replacing all six wholesale
  leaves a coherent set. If one table failed to load, that run's
  warehouse would hold five fresh tables and one MISSING one, not five
  fresh and one carried forward. There is no carry-forward mechanism
  because nothing ever needed one.
- **"The warehouse as at time T" has never existed.** Either option
  below is new construction, not a repair.

**The storage model, settled:**
- **One schema per period, on both assets** - quarterly gets a schema
  per quarter, daily a schema per day. Keyed on the period the supply
  is INTENDED for, not the day it arrived.
- **One table per supply per dataset** inside it. A resupply is a new
  table in the same schema, not an overwrite, so a schema can hold
  several versions of the same logical table.
- **Table contents are immutable** once written - never touched again.
  But **tables CAN move between schemas** (Keith, explicitly). Only
  the contents are frozen, not the filing.
- **Physical table names carry the arrival timestamp**, matching
  Keith's real operational database.
- **`run_id` is a deterministic sequence** - no date, no `_resupply`
  suffix, just a unique id for the run. Deterministic rather than
  random is load-bearing: it is what makes regeneration overwrite in
  place instead of doubling the history (`plans/running-thoughts.md`
  #26). The delivery/attempt/supersedes relationships already live in
  the manifest, so dropping the suffix loses nothing.

**Composing "as at T"**: for each logical table, take the latest
version whose ARRIVAL is <= T. Transaction time filters, valid time
files. Cleanly bitemporal, and it means the existing as-of picker was
already correct - verified against a real resupply
(`run_010_2026-05-31_resupply1`: `delivery_date` 2026-05-31,
`arrived_date` and `run_date` both 2026-06-01), and both generators
set `run_date` from `arrived_date` explicitly. Nothing in the
dashboard says which axis it is on, though, which is worth fixing.

Consequence accepted rather than solved: "show me Q3" and "show me as
at 30 June" become different questions once early arrivals exist. The
dashboard has one picker. Keith's call - stick with "as at 30 June",
the as-at question is the one that matters.

## Thread B - Staging and promotion
**Status:** todo (2026-09-21) · **Category:** Pipeline & publishing

### How a supply gets filed - staging and promotion

The hard part, and it took three wrong answers to get here. Worth
recording the rejected ones, since each was rejected for a specific
reason that will recur.

- **Rejected: the supply declares its period.** Keith's objection, and
  it is decisive: it cannot be enforced across a wide and varied
  supplier base, and the suppliers who would get it wrong are exactly
  the ones whose data most needs QA. A rule depending on every
  supplier doing something new and doing it consistently is a wish,
  not a design.
- **Rejected: derive the period from the data's own content.**
  Circular - it would infer the filing decision from the very data
  whose correctness is about to be tested. A resupply exists precisely
  because the first attempt was wrong, possibly wrong in its dates, so
  a bad extract would file itself in the wrong place and then be QA'd
  against the wrong period. Fails silently, which is the worst
  direction.
- **Weakened, then dropped: "file by arrival, period as correctable
  metadata".** The argument for it was "do not freeze a derived
  judgment into an immutable structure". It lost its force the moment
  Keith said tables can move between schemas - re-filing is cheap, so
  there is nothing expensive being frozen.

**The answer, from Keith's real system: staging, then promotion.**
Everything lands in staging on arrival. Staging is arrival-ordered and
needs no decision - it asserts only the thing actually known (this
landed at this time), so it can never be wrong. An early supply just
sits there. Promotion then moves it into a period schema, and is
reversible because tables move.

This is already how the quarterly asset works today (a human promotes
out of staging into a quarter). The daily asset is genuinely unbuilt
and unsolved - Keith's own words - and he wants both on the same
structure. Which they can be, because the daily/quarterly difference
is not structural, it is only **who pulls the trigger**:

| Asset | Decision rule | Trigger |
|---|---|---|
| Quarterly | which quarter this fills | a human, as today |
| Daily | oldest unfilled slot, unless inside a later slot's early window | automatic |

One policy flag per asset, same machinery. The automatic rule is safe
to be imperfect precisely because tables move - a wrong promotion is a
correction, not a rebuild.

Note what this dissolves: the "arrives 10pm, belongs to tomorrow"
cutoff and the "arrives a week early" case stop being two mechanisms.
A cutoff time is just a one-day early window - same rule, different
config per asset. Resupply detection also falls out for free: if the
slot an arrival maps to is already filled, it supersedes what is
there, with nothing parsing a filename.

**The content check survives, but as a DETECTOR, not a decider.**
"This supply does not look like the period it is filed under" is a
legitimate QA finding, non-circular because it is not making the call,
and it is what turns a wrong default into something a human sees
rather than something that sits there quietly.

### QA runs on staging, and that is arguably the point

QA runs BEFORE promotion, and its results are what the promotion
decision is made on. For the quarterly asset the human's question at
promotion time is literally "is this good enough to go into Q3?" -
which makes this tool an input to a decision someone already makes,
rather than a report they read afterwards.

It also resolves the cross-table problem: QA does not run against
staging alone, it **composes the current promoted state and overlays
the staged candidate**. A newly-arrived `placements` is checked
against the promoted `clients`. The same composition machinery serves
backfill - compose the promoted state as at a past point, run the new
check against it (`plans/running-thoughts.md` #24).

Converges with the three-state supply model already in this batch:
staged / promoted / failed are the same three states seen from the
storage side rather than the QA side. One concept, not two.

**QA gates promotion, on status - settled 2026-09-21 (Keith).**
**A red supply is NEVER auto-promoted** - that is always a human
decision. Amber and green auto-promote. Since a supply that cannot be
loaded at all is red (settled earlier in this same conversation), the
failed-to-load case is covered by the same rule with nothing extra.

Recorded as a correction, because the recommendation here was the
opposite and the reasoning behind it was wrong: it argued that
holding red in staging "recreates the manual bottleneck the
automation exists to avoid". It does not. **A queue of red supplies
is a work queue, not an obstruction** - a red supply genuinely does
need a person, so a human waiting on it is the correct output of the
gate rather than a defect in it. The error was treating "something is
waiting for a human" as a failure mode when it is the purpose.

**Operators also drive promotion directly, through the TUI** (Keith,
same conversation) - explicitly promote AND demote, not just a manual
promote for the quarterly asset. That is its own requirement in this
batch, and it has two consequences worth settling rather than
discovering:

1. **Demotion makes "as at T" unstable over time**, which cuts
   against this whole file's durable-history purpose. If a table
   promoted in June is demoted in August, the same "as at 30 June"
   query gives one answer in July and a different one in September -
   the DATA is immutable, but the FILING is not, and the composed
   view depends on both. So reproducing a past view exactly needs
   transaction time on the promotion decisions themselves, not only
   on the arrivals. Suggested shape: record promotion/demotion as
   timestamped events, default "as at T" to today's filing (simplest
   and what an operator usually means), and keep the event log so
   "the view as it was published then" stays answerable. Unresolved -
   for the scoper to stress-test.
2. **What happens to a `nodata` supply.** "Amber or green
   auto-promotes" does not name it, and `nodata` ranks below green in
   `STATUS_ORDER`. A supply where no check ran at all is not evidence
   of good data, so it should presumably hold rather than promote -
   but it is an edge case the rule as stated leaves open.

## Thread C - The schedule
**Status:** todo (2026-09-21) · **Category:** Pipeline & publishing

### The schedule - what exists, what changes

Most of this already exists and was nearly reinvented. `pipeline/
cadence.py` plus each contract's `slaProperties:` already carries
`cadenceType`/`cadenceAnchorMonths`/`cadenceDayOfMonth`/
`expectedTime`/`latency`, and already provides `cycle_start()`
("as at this date, what is the most recent day a delivery was
expected") and `classify_arrival()` (early/onTime/late). Check there
before designing anything schedule-shaped.

**Quarterly uses authored DATES; daily uses a cadence rule.**
Settled 2026-09-21 (Keith). Not a compromise - they are different
shapes. 365 daily dates would be absurd to enumerate and the rule
genuinely is "every day"; four quarterly dates a year are known well
in advance, and the real agreed day is "the closest business day to
the 1st", which a `day_of_month: 1` rule does not express.

Both authoring styles produce the same thing - a sequence of
`(period, due_at)`. Everything downstream consumes that sequence and
never knows which produced it.

Two alternatives were worked through and rejected, both worth not
re-deriving:
- **Runtime derivation from a holiday library** (nearest/earliest/
  latest business day + an AU-WA holiday package, Keith's own
  counter-proposal). Technically fine - and note his correction to
  an overstated objection here: holiday packages are year-keyed, so
  a later gazette amendment does NOT silently rewrite a settled past
  date. The reason it still loses does not depend on library quality
  at all: **the dates ARE the supplier agreement, and QA judges
  against the agreement.** A calendar predicts it; it does not
  constitute it.
- **Derive at runtime, freeze the computed `due_at` onto the result
  when a slot is evaluated.** Elegant, no annual maintenance, history
  immutable because the judgement is recorded rather than its inputs
  pre-written. Rejected for the same agreement-is-the-authority
  reason, and because it leaves nowhere to record a date that
  differs from what the rule would generate.

Generation stays available as a CONVENIENCE (a `mothman` subcommand
printing a year's dates for a human to review, edit and commit) -
never as the evaluation path.

**A date list runs out, and that is the dangerous part.** Raised
against my own proposal rather than discovered later: if nobody adds
next year's dates, the schedule has no slots, so nothing is ever
expected, so nothing is ever overdue - the dashboard goes QUIET
rather than red. Same false-green shape as the staleness problem
above. Two requirements follow:
- **Warn on low runway, measured in SLOTS not months** (months
  mislead - three months of quarterly runway is one slot). "Fewer
  than N expected supplies remain", N=2 giving ~6 months on the
  quarterly asset. Applies only to date-list schedules; a
  cadence-generated one is infinite and cannot run out.
- **An exhausted schedule reads UNKNOWN, never green.** No slot
  covering the viewed date means staleness and overdue have nothing
  to compare against, so the honest answer is "cannot tell".
Surface in both the dashboard and as a non-fatal CI warning - the
person who must act maintains config, not necessarily the one
reading the dashboard.

**Schedule versions are effective-dated, with a changelog** (Keith
approved 2026-09-21), same shape and same reason as check lifecycle:
a period is evaluated against the schedule version in force at that
period's due date, so changing a supplier's cadence does not
retroactively turn met periods into breaches.

**Exceptions collapse to one kind.** Authored dates make a changed
quarterly date an ordinary edit (`effective_from` + changelog), not a
second mechanism. What survives is only a daily feed paused for a day
or two by a source-system upgrade - `not_expected: [dates]` plus a
reason. Excepted periods must be SHOWN rather than silently omitted,
so a late-added exception cannot quietly erase red history.

### The asset owns the calendar; the dataset owns participation

Settled 2026-09-21, prompted by real scale Keith supplied mid-thread:
the quarterly asset will carry **~30 datasets**, of which roughly 70%
arrive every quarter and the rest once or twice a year - still landing
on one of the same four dates, just not all of them. "The quarterly
asset" is therefore slightly the wrong name: the ASSET has a quarterly
rhythm, and DATASETS participate in it at different rates.

So there is one authored calendar per asset per year (the once-a-year
human task settled above), and each dataset names which of those dates
it is in. Inheritance is the default - say nothing, get all of them.

```yaml
# asset
calendar:
  - effective_from: 2026-01-01
    dates: [2026-02-02, 2026-05-01, 2026-08-03, 2026-11-02]

# dataset: silent -> all four
# dataset: annual
delivery_months: [February]
# dataset: twice yearly
delivery_months: [February, August]
```

Why one calendar rather than a date list per dataset, and it is a
scale argument rather than a tidiness one: **30 independent date lists
can drift.** Dataset A saying 2 February and dataset B saying 3
February for the same delivery window is a class of bug nothing would
ever flag. One calendar makes it impossible by construction.

Detail decisions:
- **Month NAMES, not numbers or positional indices.** Indices break
  silently if the calendar is edited or reordered; names stay
  meaningful and match how people talk about it. Full names only,
  case-insensitive - not `Feb` as well, since two accepted forms
  means config reading differently across 30 datasets for no gain.
- **`delivery_months`, never shortened to `months`.** It names when a
  supply ARRIVES, not the period it covers - a 2 February delivery is
  often for the November-January period, so the short form invites
  exactly the wrong reading. (Confirmed with Keith after a dictation
  ambiguity pointed the other way.)
- **CI-gated in `mothman check`, and it is load-bearing rather than
  tidiness**: a typo like `Febuary` matches no delivery date, so the
  dataset silently has ZERO slots - which is the exhausted-schedule
  state, reached by accident, on a dataset nobody is watching. A
  config typo must not be able to produce the condition the hard
  failure below exists to catch.
- **A dataset may fully override with its own dates** rather than
  subsetting the calendar. No such dataset exists today (Keith:
  everything is aligned to one of the four days), but it is cheap now
  and awkward to retrofit once 30 datasets assume subsetting. Same
  effective-dating, changelog and runway check as the asset calendar.

### Exhausted schedule - hard failure, scoped per dataset

Keith's call, 2026-09-21, stronger than the "read UNKNOWN" option
proposed above and for a good reason: it cannot be ignored. Once the
runway warning has fired and nobody has filled in the dates, the
pipeline refuses to process that dataset. Supplies pile up in
staging, which is safe - staging only ever asserts arrival facts, so
the backlog drains CORRECTLY once dates are added, filed to the right
slots and classified against the right `due_at`, not approximated.

Four constraints that make hard failure safe rather than a quieter
way to go silent:
1. **The dashboard computes "exhausted" itself, from config.** If the
   pipeline fails, no new `qa_results/` are written, so the dashboard
   rebuilds to exactly what it showed yesterday - and a dashboard
   that stopped updating looks identical to one where nothing
   changed. The schedule is CONFIG, not data, so the build can derive
   the banner with no data access and no dependency on the run that
   did not happen (CLAUDE.md's CI-never-touches-data rule is
   satisfied).
2. **Scope the failure to the dataset whose schedule ran out**, never
   the whole run. At 30 datasets, one neglected annual dataset
   halting the other 29 is how a check gets disabled wholesale.
3. **Fail at FILING, before QA runs.** A supply with no slot cannot be
   classified (no `due_at`) or promoted (no target schema), so QA
   would produce results that cannot be filed anywhere. Keith's own
   preference too: a clear signal beats half-processing.
4. **The banner counts SUPPLIES WAITING, not days elapsed.** "14
   supplies in staging, unprocessed since 2 November" scales its own
   urgency - daily and quarterly feeds pile up at very different
   rates.

At 30 datasets the runway warning must **aggregate** ("3 datasets
have fewer than 2 supplies remaining"); 30 individual banners is
noise. Same for staleness - the top-level view summarises rather than
enumerates.

## Thread D - Arrival classification
**Status:** todo (2026-09-21) · **Category:** Pipeline & publishing

### Early/onTime/late - a real gap in the current classifier

NOT yet settled with Keith - recorded because the finding itself is
real and independent of how it gets fixed.

`classify_arrival()` derives the cycle from the arrival date
(`cycle_start(cadence, run_date)`), and `cycle_start` is defined as
the most recent expected day AT OR BEFORE its input - it can only
look backwards. So "early" today can only mean early WITHIN a cycle
(expected 09:00, arrived 07:00). A genuinely early supply resolves to
the PREVIOUS cycle and is reported late against it - worked example:
a quarterly supply arriving 2026-07-25 for the 2026-08-01 anchor
resolves to the 2026-05-01 anchor and reads ~12 weeks late. The daily
case is the same: a 10pm arrival intended for the next day reads late
against the current one.

Not a bug against today's behaviour - no early supplies exist in the
generated data at all (`plans/running-thoughts.md` #27 measured 0
early / 240 on time / 112 late), so nothing currently mis-classifies.
It is a gap against the model settled above, which has early supplies
as a first-class case.

**Fix, settled 2026-09-21: classify against the period the supply was
FILED to, rather than one inferred from its arrival date** - a signature change (`classify_arrival(cadence,
assigned_period, arrival)`), not a new cadence property. Promotion
already decides the period, using information `cycle_start` does not
have (which slots are already filled); deriving it a second time here
creates two implementations of one concept that can disagree, the
`plans/qa-pipeline.md` item 74 failure mode, with "filed to Q3,
reported late for Q2" as the visible symptom. A side effect worth
keeping: it REMOVES a property rather than adding one - once the slot
is known, "early" is just `arrival < due_at`, so the earliness window
is a promotion/filing parameter, not a cadence one.

**Two corrections to that fix as first stated, both found while
explaining it rather than while writing it - it was sold as "just a
signature change" and that undersold it.**

1. **Slot ASSIGNMENT and PROMOTION are two steps, not one.** As first
   proposed, the period was assigned at promotion - but QA runs
   BEFORE promotion, so at QA time there would be no slot to classify
   against. Split them:

   ```
   arrival -> slot ASSIGNED   (derived: oldest unfilled slot, or a
                               later one if inside its early window;
                               no human, no judgment, just the rule)
           -> QA runs          (classifies against that slot's due_at)
           -> PROMOTION        (the act of moving the table into the
                               period schema - auto on green/amber,
                               human otherwise)
   ```

   Assignment is a derivation; promotion is a decision. The original
   point survives intact - there is still exactly one place the slot
   is decided, and classification still consumes it rather than
   re-deriving it - it just happens earlier. It also means a REJECTED
   supply still gets classified, which matters: "arrived three weeks
   late AND was bad" is exactly what belongs on the record for a
   supply that never got promoted.

2. **The verdict stops being a frozen historical fact.** Filing is
   mutable, so if a supply is re-filed the classification must
   follow - a supply reported "late" purely because it was misfiled
   was never actually late, and leaving a known-wrong verdict in
   place for the sake of immutability is the one place this design
   would knowingly say something untrue. This contradicts
   `pipeline/cadence.py`'s own current docstring, which states the
   verdict is computed once, committed, and "never needs porting to
   JS: a past run's own real arrival time never changes no matter
   what as-of date someone later picks". The arrival TIME still never
   changes; the VERDICT becomes a function of the current filing.

   Keith settled this CONDITIONALLY, 2026-09-21: if re-filing
   exists - and he has not yet decided whether it does - the verdict
   follows the new filing and is recomputed.

   One upside either way: since the verdict travels with the supply,
   the dashboard's JS never recomputes classification.
   `cycleStartDate()` still earns its place for the as-of picker's
   period math, so the duplicated-logic surface shrinks rather than
   grows.

**Re-filing may not be a free decision, and demotion has a trap.**
Raised 2026-09-21, unresolved:
- Promote and demote are both already asked for in the TUI. Demote
  out of Q2, promote into Q3, and a supply has been re-filed without
  anyone designing re-filing. So the real question is whether the
  composition of two agreed operations gets recognised and handled,
  not whether to build a third one.
- **Demotion needs stickiness, but only in one direction** - Keith's
  own refinement, 2026-09-21, sharper than the original framing. With
  auto-promotion on green/amber, a human demotes a green supply and
  the rule promotes it straight back, in the same run. But that only
  applies to demote-to-STAGING: auto-promotion looks at supplies
  AWAITING a decision, and a rejected supply is not awaiting one, so
  demote-to-rejected is inherently sticky. **The destination state
  carries the stickiness.**

  Proposed rule that covers it with no flag and no extra state:
  **auto-promotion only ever acts on a supply no human has touched.**
  Once any operator decision is recorded - promote, demote, reject -
  automation defers to people permanently. It generalises past this
  case: an operator's deliberate promotion into an unusual period
  should not be second-guessed on the next run either.

  **The real question it exposes, still open: is "un-decide" an
  operation we want?** Demote-to-staging means "put this back in the
  queue for someone to look at again", which is genuinely different
  from rejecting it. If not wanted, demote goes to rejected only,
  re-filing is an ATOMIC move between periods, nothing ever passes
  back through staging, and the trap disappears entirely rather than
  being managed.
- That also gives re-filing a natural shape if wanted: a demoted
  supply sits in staging with auto-promotion suppressed, and a human
  promotes it where they choose. No third operation, and the verdict
  recomputes because the slot assignment genuinely changed.

## Thread E - Slot assignment and the two cascades
**Status:** todo (2026-09-21) · **Category:** Pipeline & publishing

### Slot assignment - the claim-window rule

Settled 2026-09-21, after Keith's stress-test found a CASCADING bug
in the rule as first stated ("assign to the oldest unfilled slot").
Recorded in full because the broken rule reads perfectly reasonable
and would be re-proposed otherwise.

**The scenario.** Daily feed, due 12:00 Monday:

| Time | Rule said | Result |
|---|---|---|
| Mon 14:00 | Mon unfilled -> Mon | red, rejected - Mon still unfilled |
| Mon 16:00 | Mon unfilled -> Mon | green, promoted - Mon now filled |
| Mon 20:00 | Mon filled, oldest unfilled is Tue | WRONG - a Monday resupply filed as Tuesday's delivery |
| Mon 22:00 | Tue now filled -> Wed | WRONG |
| Tue | Wed filled -> Thu | WRONG |

Every later supply is off by one permanently, nothing self-corrects,
and each day looks locally plausible. The cause: "oldest unfilled
slot" assumes every arrival fills a NEW obligation. A resupply does
not - it supersedes an existing filing - and the rule had no way to
say so, so it invented a future obligation instead.

**The rule:**

> Assign to the oldest slot whose CLAIM WINDOW is open and which is
> unfilled. If there is no such slot, it is a RESUPPLY of the most
> recently filled slot.

A slot's claim window opens a configured interval before its due date
and never closes (late is always allowed). A slot whose window has
not opened cannot be claimed, so nothing can reach forward into the
future and the cascade is structurally impossible rather than avoided
by luck.

**This reinstates the earliness window, which the entry above had
just dropped.** That call was wrong: it was argued redundant in the
normal case and false precision in the ambiguous one, but the window
is what defines when a slot becomes CLAIMABLE, which is the thing
preventing the cascade. Keith's quarterly three-weeks-early case uses
the same mechanism - a ~21-day window on that asset makes a 13 July
arrival eligible for the August slot.

**It also deletes the daily cutoff rule.** "Arrives 10pm, so it is
for tomorrow" needs no special handling: if a feed's supply genuinely
lands the evening before, its `due_at` IS the evening before, and the
window opens accordingly. The schedule expresses it directly instead
of a separate rule reinterpreting arrivals afterwards.

**The principle worth keeping: NEVER CLAIM FORWARD.** Mis-attributing
an arrival backwards (calling a new delivery a resupply) is one
contained error on one supply. Mis-attributing it forwards cascades
through every future delivery. The risk is asymmetric, so the default
must be the one that cannot propagate - and the claim window is what
makes "cannot" literal rather than likely.

Note this depends on a rule settled earlier in this file: **a
rejected supply does not fill its slot** (only a promotion fills
one). Without that, the Mon 16:00 resupply above would itself have
been pushed to Tuesday.

Still genuinely ambiguous, and unchanged by this: an arrival when a
PRIOR slot is unfilled (a missed delivery not yet resolved) cannot be
told apart from a late one by any rule. Default to the oldest
claimable unfilled slot since late is commoner than early, mark it as
assigned under ambiguity, and surface it for review - cheap to
correct, because filing is mutable and the verdict recomputes.

**Window size is a genuine TRADE, not a tuning knob.** Worth
recording so nobody "fixes" it later. The obvious cure for a boundary
misfile is a generous window - make consecutive windows contiguous so
there is no dead zone. That reintroduces the cascade exactly: with
Tuesday's window open from Monday 12:00, the Mon 20:00 resupply finds
Monday filled, Tuesday open and unfilled, and claims Tuesday again.
**Tight windows buy cascade-immunity at the price of boundary
misfiling; wide windows do the reverse. No sizing gets both.**
The trade is accepted in favour of never-claiming-forward: a boundary
misfile is two wrong labels on one day, a cascade is wrong forever.

**What a boundary misfile actually costs**, since "the data is still
there so downstream can cope" covers only half of it (Keith's own
framing, and the data half is right - it sits in the previous slot,
present and QA'd). The REPORTING is wrong twice, and reporting is
this system's product: a punctual supplier is recorded as delivering
a very late resupply, AND the next slot is left unfilled so it goes
overdue - a phantom missing delivery for data that arrived on time
one slot over. The second is the "says something untrue" category.

**Scope boundary that falls out of this** (Keith): we do NOT build
staleness-tolerance policy for consumers. This system attributes
supplies to slots and reports what is where and how fresh. Whether a
downstream consumer takes only the latest slot, composes several, or
refuses anything older than a week is theirs. Otherwise the tool
grows a config surface for every downstream system's preferences,
unmanageable at 30 datasets.

### Arrival into an already-filled slot - warn, and never auto-promote

Keith's own proposal, 2026-09-21, and better than the
near-a-window-boundary trigger it replaced **because it needs no
magic number**. That one required "within X of the window opening",
and X is arbitrary - pick 5 minutes and a 6-minute case slips through
silently. This is a structural condition: the slot had been PROMOTED
into, and something arrived anyway. Nothing to tune. Same
structural-over-configured preference this project applies elsewhere.

It also draws a distinction the boundary rule could not:
- **Resupply after REJECTION** - the slot was never filled, so this
  is the expected repair path. Routine, no warning.
- **Resupply after ACCEPTANCE** - we had already accepted something
  for this period. Odd. Warn.

On a healthy feed the second is rare, so the banner stays meaningful
rather than becoming wallpaper at 30 datasets.

**Warning, not error**, because one legitimate case remains: a
supplier realises the extract they sent was wrong - wrong period,
wrong filter - even though it passed every check. Data can be clean
and still be wrong; that is the limit of any check suite.

**Boundary proximity becomes the EXPLANATION rather than the
trigger** - still computed, used in the message:

> A supply arrived for Monday, which was already accepted at 16:00.
> It landed 3 minutes before Tuesday's window opened - it may belong
> to Tuesday.

versus, with no boundary proximity, the same banner without that
second sentence. Same trigger, different diagnosis.

**The hole this exposed in auto-promotion, and it is a gap rather
than a refinement:** the rule as settled says amber-or-green
auto-promotes, so a green supply landing in an already-filled slot
would **silently supersede data already accepted**. Without a carve-
out, a supplier's accidental duplicate send quietly replaces good
accepted data and the only trace is a superseded table nobody looked
at. So: **a supply landing in a filled slot never auto-promotes,
whatever its status.** It holds, warns, and waits. Filling an empty
slot is routine; replacing accepted data is a decision.

Three actions the banner must lead to, genuinely different from each
other: **accept** it as a correction (promote, superseding),
**re-file** it to the next slot (it was a boundary misfile), or
**reject** it (duplicate or erroneous send).

**Standing principle Keith endorsed here, and it has now produced
three separate requirements in this file alone: where a rule
genuinely cannot know, SAY SO rather than commit silently.**

### The BACKWARD cascade - a missed slot absorbing later arrivals

Keith's second stress test, 2026-09-21, and it broke the fix for the
first one. Recorded in full for the same reason: the rule reads
sensible and the failure is invisible day to day.

**The scenario.** Daily feed, supply due ~22:00. Monday received and
filled. Supplier's system goes down for an upgrade - found out 9pm
Tuesday, too late to be a planned schedule change. Wednesday missed
too. The next supply arrives on time at 22:00 Thursday.

Under "oldest claimable unfilled slot, window never closes":

| Arrival | Oldest claimable unfilled | Filed as |
|---|---|---|
| Thu 22:00 | Tue | Tuesday, 2 days late |
| Fri 22:00 | Wed | Wednesday |
| Sat 22:00 | Thu | Thursday |

**A permanent two-day lag, cascading BACKWARDS.** Every supply reads
"late", every day looks locally plausible, it never self-corrects.
Same catastrophic shape as the forward cascade, introduced by the fix
for it.

**Cause**: the rule cannot know that a MISSED slot is never going to
be filled. The supplier was down; there is no Tuesday extract and
never will be. But an unfilled slot waits indefinitely to absorb
whatever arrives next.

Two obvious fixes that do NOT work, worth recording so they are not
re-proposed:
- **Close a slot's window when the next one opens.** Kills the
  cascade but breaks lateness - Monday's supply landing Tuesday
  morning would file as Tuesday.
- **A finite lateness tolerance.** Only shifts the lag: a one-day
  tolerance turns a two-day cascade into a one-day cascade. Any fixed
  tolerance has an outage longer than it.

**The fix: punctuality is evidence of which slot a supply is for.**

> If an arrival falls within the ON-TIME WINDOW of the current slot,
> and that slot is unfilled, file it there - even if earlier slots
> are unfilled. Otherwise, oldest claimable unfilled slot.

- Thu 22:00, Thursday due 22:00 -> on time for Thursday -> Thursday's
  slot. Tue and Wed stay unfilled and read as MISSED, which is true.
- Monday's supply arriving Tue 03:00 -> not on time for Tuesday ->
  oldest unfilled is Monday -> Monday's slot, late.

Lateness still works and an outage no longer eats the future.

**The rule only needs to be sensible, not clairvoyant, because an
outage is LOUD.** Tuesday's slot goes overdue Tuesday evening; by
Thursday two overdue slots are red. A human is engaged well before
the ambiguous arrival lands. So the definitive answer lives in the
decision log: **a human marks Tue and Wed as missed**, reason
"supplier system upgrade", closing those slots explicitly rather than
by rule.

**Two mechanisms that must not blur.** The distinction is not really
WHEN it was agreed - it is what the record ends up saying:
- **`not_expected:` in config** changes what was OWED. The slot never
  existed. No overdue, nothing red, nothing missing - the record says
  "nothing was due."
- **A slot marked missed in the decision log** records an obligation
  that was NOT MET. The slot existed, it was owed, it did not arrive,
  and it stays in the record as a failure, permanently, with a reason
  attached.

So marking a slot missed is not agreeing the supply was not owed - it
is **closing the slot while recording that it WAS owed and did not
come**. The acknowledgement is "it is not coming", never "it was not
due".

**Why the distinction protects the numbers**: otherwise supplier
reliability becomes whatever people were willing to excuse after the
fact. A two-day outage is a real service failure even when entirely
understandable, and the record should still carry it.

Timing then falls out as a CONSEQUENCE rather than being the rule -
you can only legitimately say "nothing is owed" before the fact,
because afterwards you are describing what happened rather than what
was agreed. So the same physical event splits by how it reached you:
a supplier saying next week "we are upgrading Tue-Wed, no files" is
`not_expected` (the obligation was renegotiated); finding out at 9pm
Tuesday that it is already not coming is marked-missed (the
obligation stood and was missed).

Keith's scenario is the second. Editing config retrospectively to
make red history disappear is exactly what the exceptions rule above
says must not happen.

## Thread F - Per-table slots
**Status:** todo (2026-09-21) · **Category:** Pipeline & publishing

### A supply is ONE TABLE - each table claims its own slot

Keith, 2026-09-21. Everything above was worked through assuming one
table per supply, which holds for Birth Registrations but not for
Child Protection's six. Settled: **each table claims a slot
independently**, rather than a collection filling one slot as a unit.

Vocabulary that follows, and the earlier text was loose about it: a
SUPPLY is one table version. CP's normal arrival is six supplies in
one DELIVERY. The delivery is a grouping for presentation ("these six
landed together"), never the unit of filing.

**This makes an earlier decision implementable.** Keith had already
settled that a multi-table check should read `nodata` when a table it
spans is missing - but there was no fact to test that against until
slots became per-table. It is now a crisp condition:

> A multi-table check is `nodata` for a period if ANY table it spans
> has an unfilled slot for that period.

Same for the five-tables-land-one-fails case Keith raised early on:
five slots filled, one unfilled and going overdue, rather than a
single partial fill with no vocabulary to describe it.

Two consequences:
- **Per-table classification is more honest than per-delivery.** If
  `cp_clients` lands 09:00 and `cp_placements` 14:00, each gets its
  own early/onTime/late verdict instead of the whole delivery taking
  the worst one. A single late table stops dragging five punctual
  ones down.
- **Slot count multiplies** - ~30 datasets on the quarterly asset,
  several of them multi-table collections, times four periods a year.
  This is what turns the aggregation requirement above from likely to
  certain.

The claim-window and never-claim-forward rules apply per table
unchanged - each table has its own independently-tracked slot
sequence.

## Thread G - The decision log
**Status:** todo (2026-09-21) · **Category:** Pipeline & publishing

### Filing decisions are recorded - an append-only decision log

Keith, 2026-09-21: a human promoting, rejecting, demoting or
re-filing a supply must be recorded, with the decision and a
timestamp.

**This closes an open question raised earlier in this file.**
Demotion makes "as at T" unstable - a table promoted in June and
demoted in August means the same "as at 30 June" query answers
differently in July than in September, because the data is immutable
but the FILING is not and a composed view depends on both. A
timestamped decision log is the missing piece: it puts transaction
time on the filing decisions themselves, so "the view as it was
published then" stays answerable instead of being quietly
overwritten.

Per decision: **who** (the operator), **when** (timestamp), **what**
(promote/reject/demote/re-file), **which** (the supply, and for a
re-file the from- and to- slots), **why** (free text).

**A reason is mandatory for the consequential decisions** - rejecting,
accepting something red, or superseding already-accepted data - and
optional for a routine promote. The question that arrives a year
later in a government agency is "why did we accept this into Q3", and
an audit trail recording the what but not the why answers the easy
half.

Two shape decisions:
- **Automated decisions go in the same log, with the RULE as the
  actor.** Auto-promotion is a decision too. One log means "why is
  this supply promoted" has a single answer location rather than two
  mechanisms to reconcile, and it makes the "auto-promotion only acts
  on a supply no human has touched" rule checkable directly from the
  log.
- **Append-only.** A decision record that can be edited is not an
  audit trail. Same immutability as table contents, same reason.

Likely feeds the existing activity feed - `qa_tools/common/
changelog.py` already builds "who QA'd what, when" events, and filing
decisions are the same shape.

**Open, and flagged rather than assumed: OPERATOR IDENTITY.**
`qa_tools/common/git_identity.py`'s `get_run_by()` reads the local
`git config user.email`, which is fine for a developer running the
pipeline and means nothing for an operator in a deployed environment.
Who an operator IS needs a real answer in the target architecture.
Worth naming now because it is exactly the thing that gets stubbed
with a placeholder otherwise - which `get_run_by()` itself
deliberately refuses to do, hard-erroring when unset. **Deliberately DEFERRED by
Keith to when this requirement is actually built** - named now so it
is not discovered late, not left open because nobody noticed it.

## Thread H - Chaos-engineering findings
**Status:** todo (2026-09-21) · **Category:** Pipeline & publishing

### Chaos-engineering pass - five more wrinkles

Keith's ask, 2026-09-21, after two of his own stress tests had each
found a cascade: run the settled model against deliberately awkward
sequences. All five below agreed with him the same session.

**1. Composition filters on the WRONG timestamp - a bug in a rule
already settled here.** Thread A says "as at T: the latest version
whose ARRIVAL is <= T", described as transaction time. It is not -
two different timestamps were conflated.

```
Mon 22:00  supply arrives, QA red, rejected -> NOT promoted
Wed        nothing; warehouse still holds last period's table
Fri        human decides it is the best available -> promotes it
```

Ask "as at Wednesday": its arrival was Monday and it is promoted, so
the rule includes it - but on Wednesday it was sitting rejected in
staging. **The view shows data that was not there.**

> Corrected rule: **as at T = the latest version PROMOTED on or
> before T.**

For auto-promoted supplies arrival and promotion are minutes apart
and nothing changes. The gap only opens on human-decided ones, which
are exactly the cases someone later asks about. Promotion timestamps
exist because of the decision log above.

**2. Slot assignment is ORDER-DEPENDENT.** Assignment reads the
current state of the slots, so processing order changes the answer.
Tuesday's late file and Thursday's on-time file both land in one
batch around Thu 22:00:
- Thursday's processed first -> on-time for Thursday -> Thursday;
  then Tuesday's -> oldest claimable unfilled -> Tuesday. Correct.
- Tuesday's processed first -> it falls inside Thursday's on-time
  window -> files as THURSDAY; then Thursday's real file hits a
  filled slot and is held. Wrong.

Same two files, opposite outcome, decided by loop order. **Fix:
always assign in ARRIVAL-TIMESTAMP order, never discovery order**,
with a defined tiebreak for identical timestamps. Note this is
load-bearing for a claim made earlier in this file - that a staging
backlog "drains correctly" after a hard failure because staging
preserved arrival times. That only holds if draining replays in
arrival order; the conclusion was stated without its dependency.

**3. An outstanding MISSED slot vacuums up later resupplies.**
Survives the backward-cascade fix and is worse in kind:

```
Tue        missed entirely (outage)
Wed 22:00  arrives on time, green, promoted -> Wednesday filled
Wed 23:00  a resupply of Wednesday arrives
```

Wednesday is filled so the on-time rule does not apply; the oldest
claimable unfilled slot is TUESDAY, so the Wednesday resupply files
as Tuesday, one day late. The "resupply of the most recently filled
slot" branch never fires, because an outstanding missed slot means a
claimable unfilled one exists. **So a missed delivery is recorded as
MET** - a service failure erased, using another day's data. Worse
than a cascade: it manufactures a delivery that never happened.

> Fix - **monotonic filling: a slot stops being claimable once a
> LATER slot has been filled.**

Re-traced: Tuesday is non-claimable, nothing else is claimable, so
the 23:00 arrival is correctly a Wednesday resupply. Genuine lateness
survives - Monday's supply landing Tue 03:00 finds Tuesday unfilled.

**Its limit, named rather than papered over** (Keith: "I think we
can't design around that"): once a delivery is skipped AND a later
one has landed, a genuine backfill of the older slot cannot be placed
by any rule - it is not claimable, and defaulting it into a future
slot is the forward cascade again. **When nothing is confidently
claimable, hold it for a human** and let them decide where it is
filed.

**4. Arrival timestamps: whose clock.** Every rule compares an
arrival instant against a due instant, and only the due side was
specified. Settled:
- **Never use supplier-provided timestamps** - a file's own metadata
  reflects their clock, timezone and bugs. Staging's whole
  justification is that it asserts only facts we can vouch for, so
  arrival means **when WE received it**, recorded on our side of the
  boundary.
- **Never store a naive timestamp.** `pipeline/cadence.py` already
  treats naive values as UTC; a naive AWST value is eight hours out,
  enough on a daily feed to flip on-time to late or move a supply
  into the wrong slot. The requirement is that the value **carries
  its offset** - AWST works precisely because it is a fixed UTC+8
  with no daylight saving, while a bare `2026-09-21 22:00` is
  ambiguous whatever was intended.

**5. Authored quarterly dates carry no time of day.** `2026-08-03` is
a date, but due-ness, on-time windows and claim windows all need an
instant. Settled: **the schedule carries a time alongside the
dates**, rather than relying on an implicit default.

**6. One repo-wide timezone config parameter** (Keith, 2026-09-21) -
timestamps should be easy for humans to read, this is only ever
operated in Perth, so one parameter in `contract/data-asset.yaml`
(asset-level config IS repo-level here, since assets are separate
deployments) is what every datetime derives from. It replaces
`pipeline/cadence.py`'s hardcoded `AWST_OFFSET = timedelta(hours=8)`.

One completion rather than a disagreement: **stored values still
carry their offset** (`2026-09-21T22:00:00+08:00`) - costs nothing,
stays human-readable, and is self-describing to anyone opening a
`qa_results/` file years later. Without it, changing that config
parameter retroactively reinterprets every timestamp ever written -
the same retroactivity problem `effective_from` exists to prevent,
arriving by a different door.

**7. `clipDatasetToAsOf()` filters on `run_date`, which is ARRIVAL.**
Correct today only because no promotion concept exists, so arrival is
the sole timestamp there is. It becomes wrong the moment promotion
lands (see wrinkle 1 above). Keith, 2026-09-21: flagged, to be
addressed in the build - on the list of things that must change,
never something that keeps working by default.

## Thread I - The multi-table nodata seam
**Status:** todo (2026-09-21) · **Category:** QA checks & contract

### The multi-table `nodata` seam

Keith asked this be picked at, 2026-09-21. Two of the findings are
verified against real code rather than reasoned.

**The existing `nodata` is a DIFFERENT KIND from the new one.** Today
it means "this dataset has nothing in the selected as-of window" - a
VIEWING condition, uniform across a whole dataset (`ds.noDataAsOf`).
The new one means "this particular check cannot be evaluated" -
PER-CHECK and PARTIAL.

The template's `rollup()` was built for the first kind:

```js
const withData = datasets.filter(d=>!d.noDataAsOf);
if(!withData.length) return datasets.length ? "nodata" : "green";
return worstOf(withData.map(...));
```

All-or-nothing, at dataset granularity. Its own comment states the
intent exactly - "'no data' is a different KIND of signal... must
never silently vote 'green'". But five green checks plus one nodata
cross-table check returns **green**, because the nodata never reaches
a filter that only looks at whole datasets. **The mechanism written
to prevent a false green produces one, once nodata becomes partial.**
Not wrong today; built for a shape that is about to change.

**`qa_tools/common/dataset_status.py` has no `nodata` AT ALL** -
`STATUS_ORDER = {"green": 0, "amber": 1, "red": 2}`, and
`dashboard_status_of()` does `if recorded in STATUS_ORDER: return
recorded`, so a recorded `"nodata"` falls through to threshold math
and comes back GREEN. No crash, no warning, just a silently different
answer from the JS. That is `plans/qa-pipeline.md` item 74
pre-loaded, and worth fixing BEFORE per-check nodata exists - the
file's own docstring says it was written because this module "drifted
from its own JS counterpart" once already.

**Cross-cadence checks have no period to share.** The rule "nodata if
any table it spans has an unfilled slot for period P" assumes every
participating table HAS a slot for P. A check spanning a daily table
and a quarterly reference table does not: for P = Wednesday the
quarterly table has no Wednesday slot at all, and comparing against
its latest promoted version is the only thing the check could ever
mean. So narrow the rule to "a table that PARTICIPATES IN period P",
and note that cross-cadence checks need an answer to "which table's
period is the check's period" that does not yet exist. Moot within CP
(all six tables quarterly) - this is a cross-COLLECTION problem, so
possibly deferrable, but not to be assumed away.

**This resolves two things listed as open elsewhere in this file:**
- "A check result stops being a pure function of one run" - now
  well-defined: a multi-table check is a function of PERIOD P's
  composed state, and changes when any participating table's P
  version changes.
- "Which dataset's history records it" - the COLLECTION's, which
  follows from lifting multi-table checks to collection level.

**The trap that started this, to be written down as INTENDED
behaviour**: a multi-table check reads `nodata` even though the
composed warehouse holds data for every table it spans. Carried-
forward data from another period makes a cross-table result
meaningless, so this is correct and deliberate - but it reads like a
bug to anyone encountering it cold ("we have the data, why is it not
checking?"), and would be helpfully "fixed" by a later session
without the reasoning attached.

#### Worked example, and what it must display

Real check, from `contract/child-protection-soda-checks.yml`:
`values in (cp_client_id) must exist in cp_clients (cp_client_id)`,
name "Client reference", **defined on `cp_notifications` but
depending on `cp_clients`**. A second of the same shape sits on
`cp_investigations`.

August 2026: `cp_clients` arrives as an invalid CSV, red, rejected,
so its August slot stays unfilled. The other five land clean.

Traced through the real code - `worstOf()` is
`list.reduce((w,s)=> STATUS_ORDER[s]>STATUS_ORDER[w]?s:w, "green")`,
seeded with green, and `STATUS_ORDER.nodata` is -1, so nodata can
never win:
- `cp_clients` column -> `worstOf(["nodata",...])` -> **green**
- `cp_notifications` column -> `worstOf(["green","green","nodata"])`
  -> **green**
- Collection -> **green**, and `rollup()`'s `noDataAsOf` filter never
  fires because CP as a dataset does have August data - five sixths
  of it.

**Child Protection reads green for August with one of six tables
missing and two referential checks never evaluated.** Note where the
nodata surfaces: under `cp_notifications`, a table that arrived
perfectly. Nothing on the healthy table's own row hints the problem
is next door.

**The fix is mostly already decided here and was simply not
connected**: staleness is an independent axis that caps the headline,
and an unfilled August `cp_clients` slot MEANS composition carries
May's forward, which IS stale. One condition, two symptoms. So the
headline is worst-of (quality, freshness) and cannot read clean
green.

#### A check that could not run is RED, with a qualifying chip

**Keith's proposal, 2026-09-21, and it SUPERSEDES the exclude-from-
worst-of-plus-a-count approach first drafted here** (that version:
nodata leaves the quality worst-of, and an "18 of 24 checks
evaluated" count carries the signal instead). Recorded as a
replacement rather than an alternative so the file does not hold two
contradictory designs.

The check lights up **red**, with a secondary qualifying chip noting
the cause is missing data. Status says how bad; the chip says why.

Why it is better:
- **It cannot be silently swallowed.** Red wins every `worstOf` by
  construction. No exclusion filter, no count side-channel, no
  special case in the rollup - the bug traced above becomes
  impossible rather than guarded against.
- **It is honest about consequence.** A check that could not run
  means there is no assurance here, which for someone deciding
  whether to promote or use the data is the same practical position
  as a check that ran and failed. "Unknown" is not a softer "bad".
- **Less machinery.** The superseded version needed three things
  (exclude from worst-of, carry a count, lean on the freshness axis
  to cap the headline); this needs a status and a chip. It also
  sidesteps the `dataset_status.py` drift problem entirely, since
  there is no new status value for the Python mirror to be missing.
- **It satisfies Keith's own earlier requirement BETTER** - a failed
  table should not drag the other five down "unless they have a
  multi-table check that impacts the failed table". Cross-table
  checks are lifted to the collection, so the red lands at
  COLLECTION level where the check lives; `cp_notifications` keeps
  its own green status and carries only an informational pointer.

**The boundary it must not cross - two "no data" conditions, only one
of them red:**
- **Owed but absent** - a supply was expected, did not arrive or
  failed, so the check could not run. **RED.**
- **Nothing was owed** - the period predates the dataset, or
  `not_expected` says no supply was coming. **Still `nodata`.**

The existing `noDataAsOf` is the second kind: viewing as at a date
before Child Protection existed must not turn the page red, because
nothing was missing - there was simply nothing yet.

That is the same distinction settled earlier in this file between
`not_expected` and marking a slot missed - did we change what was
OWED, or did an obligation go UNMET? Same question one layer up,
which is a decent sign it is a real seam rather than an arbitrary
one.

What each level shows (Keith's own instinct that `cp_notifications`
should "light up" with an obvious warning):

| | August |
|---|---|
| `cp_clients` | red - its own checks could not run, chip: no August data |
| `cp_notifications` | own checks green; informational pointer that a relationship check involving it is red, **blocked by `cp_clients`** |
| Collection | red, from the lifted cross-table checks |

An evaluated-count ("18 of 24") survives only as an optional nicety,
no longer load-bearing.

**The warning must NAME THE BLOCKER**, not just report absence. "Not
all checks could be run" leaves someone staring at a table where
nothing is wrong; "Client reference could not run - `cp_clients` has
no August data" makes the next click obvious.

**And it is a POINTER, not a duplicated result.** Multi-table checks
are lifted to the collection level (settled earlier), so the check
itself is not under notifications any more. The honest statement for
that row is a real distinction worth saying out loud: **fully
verified against its own data, unverified against its
relationships** - which is not the same as "this table has a
problem".

#### Checks must DECLARE their participating tables

Required, and not previously specified. To say "Client reference
could not run because `cp_clients` has no August data", the system
must know the check spans notifications -> clients. Today that is
only expressible in the check's SYNTAX - SodaCL grammar here, and
dbt/ODCS bury it differently in theirs. Parsing four tools' syntaxes
to recover dependencies is exactly the fragile thing this project
avoids elsewhere.

So a multi-table check declares them in its lifecycle metadata,
hand-authored alongside `check_id`/`name`/`introduced_date`:

```yaml
      depends_on: [cp_clients]
```

**This is not only for the message.** The nodata rule itself -
"nodata if any table it spans has an unfilled slot" - is NOT
COMPUTABLE without it. That phrase had been written throughout as
though "any table it spans" were a known quantity; it is not.

CI-gatable the same way everything else here is: `mothman check`
validates every declared table exists in the collection, and that a
check declaring nothing genuinely is single-table.

## Thread J - Composition dropped, and the warehouse
**Status:** todo (2026-09-21) · **Category:** Pipeline & publishing

### Composition drops out; drift declares what it needs

Settled 2026-09-21. **Cross-period composition is not needed and
should not be built.** What killed it was the red-for-unrun decision
above: a cross-table check only runs when every participating table
has a filled slot for period P, so the query reads ONE schema.
Carry-forward was the only reason cross-period assembly existed.

Walking the consumers: QA of a staged candidate - one schema, or it
is red. Backfilling a new check - period P's schema. Dashboard "as at
T" - reads `qa_results/`, never the warehouse, so it filters RESULTS
by time rather than composing data (two operations that had been
conflated throughout this entry; the dashboard could not do the
latter anyway under the CI-never-touches-data rule). Downstream
consumers - explicitly out of scope, they own their own staleness
tolerance.

**Tension resolved**: Keith's early "we run against the latest
version available of each table" referred to the OPERATIONAL
warehouse, which is downstream and out of scope, and the promotion
concept now covers it. It was never a statement about this tool.

What survives: **picking the newest version of a table WITHIN one
period's schema** (a schema can hold a supply plus its resupplies) -
trivial, and a different thing from assembly across time.

**Drift and trend declare a temporal dependency**, the same shape as
`depends_on` for cross-table checks:

```yaml
      depends_on: [cp_clients]        # another table, same period
      reference: previous_period      # or baseline: <date>, or window: N
```

The reference choice is a real design decision, not a tuning knob -
**previous period** catches sudden shifts, **a fixed baseline**
catches slow drift over years, **a rolling window** smooths noise.
Different checks, not different settings.

Two cases fall out of rules already set:
- **Reference period was expected but is missing** -> cannot run ->
  **red**. Identical to a missing table dependency; the dependency is
  temporal rather than lateral.
- **No reference because the dataset is brand new** -> no prior
  period was ever owed -> **`nodata`, not red**. The owed-versus-not-
  owed boundary again. Without it every new dataset starts life red
  on all its drift checks, which is how people learn to ignore a
  signal.

### One database, many schemas - replacing the per-run warehouses

Keith, 2026-09-21, and it is a strictly better answer to the problem
the per-run databases were solving. Their justification (see
`qa_tools/bdm/build_per_run_warehouses.py`'s own docstring) is that
dbt and Soda have no `run_id`-scoped `WHERE`, so a per-run verdict
needs a database holding exactly one run. **Schema-per-period gives
the same isolation AND matches the real operational system**, instead
of being a test-only construct that exists nowhere in production.

It also removes a build consequence flagged a moment earlier: a drift
check's reference period is another schema in the same database, so
it is an ordinary cross-schema query rather than something that must
be copied into a sealed database first. Mechanically it is the same
lever, different field - dbt resolves sources through database/schema
in its profile, and Soda's configuration carries a schema too.

**Test isolation needs doing deliberately.** The per-run databases
were also providing incidental isolation for parallel tests -
`pytest-xdist` is the default now, and `DUCKDB_RUNS_DIR` being unique
per run is what fixed the dbt target-path collision (`plans/running-
thoughts.md` #12). One shared database puts several workers in one
file. Fix: **one database per test worker** via `tmp_path_factory`,
the same pattern the other tools' fixtures already use. Agreed with
Keith rather than discovered as flaky tests later.

## Thread K - "As at T", the published record, and config validation
**Status:** todo (2026-09-21) · **Category:** Dashboard UI

### "As at T" defaults to AS-CORRECTED; snapshots are as-published

Settled 2026-09-21. A supply filed to Monday reads late; on 12 August
someone re-files it to Tuesday where it was on time. The 5 August
view can show either.

- **As-published** - shows it late, forever. What the dashboard said
  that day.
- **As-corrected** - shows it on time, because we now know it was.

Both legitimate, different questions: "what did the dashboard say
when I approved that promotion?" wants the first; "was this supplier
actually late in August?" wants the second, since a performance
number built from known-wrong verdicts is simply wrong.

**The live dashboard defaults to AS-CORRECTED.** The deciding
argument: this design spent a whole session eliminating cases where
the system says something untrue, and as-published deliberately
preserves a falsehood already identified and fixed. A correction
nobody sees by default is not doing much work.

**The as-published view is the SNAPSHOT archive, not a toggle** -
`dashboard/snapshots/*.html.gz` is already a frozen, self-contained
copy openable years later, immutable in a way a recomputed view can
never be. Good split, and it needs no new mechanism.

**Snapshots become automatic on every publish - opt-out, not opt-in**
(Keith). Today they are opt-in via `SNAPSHOT_DASHBOARD=1`, which
makes the as-published record SPARSE: it exists for moments someone
chose, not continuously.

**Decision-log visibility**: where decisions have been made, the
dashboard shows them clearly - the live view shows truth, snapshots
show what was published, and the decision log explains every
difference between them. Also note both views are computable
regardless, because the log is append-only and timestamped, so the
filing state at any T is fully recoverable.

**Deduplicated by CONTENT HASH** (Keith agreed, 2026-09-21) - an
identical rebuild does not accumulate a snapshot, since
`deploy-pages.yml` redeploys on plenty of pushes that change nothing
about the rendered page. Chosen because it needs no judgement about
which changes "count": if the published page differs from the last
snapshot, archive it; otherwise do not.

The reason this needed deciding rather than discovering: snapshots
are committed and meant to accumulate forever. Today there are 6
totalling 1.1MB, newest ~460KB gzipped - and the page has grown a lot
since that one (Plans, Demo and Requirements tabs all landed after
it). Automatic-on-every-publish without deduplication is real repo
growth in the one directory nothing is ever cleaned out of.

### `mothman check` validates the new config

Keith, 2026-09-21: the new asset and schedule YAML gets validated
like everything else, as a `validate-config` gate alongside
`validate-requirements`/`validate-changelog` in `cli/check.py`'s own
list. `qa_tools/common/schemas.py`'s `_Strict` base (`extra="forbid"`)
is the existing pattern to build on - no new machinery needed.

The organising idea, rather than a checklist: **every check here
exists to stop a config error silently producing ZERO SLOTS** - the
exhausted-schedule state, arriving by accident, on a dataset nobody
is watching. Most of the validations are variations on that one
failure.

Errors:
- **Shape** - required fields, types, and `extra="forbid"` so a
  mistyped KEY is caught rather than ignored (a silently-dropped
  `delivery_months` key gives a dataset all four dates when it should
  have one).
- **Values** - month names real and full, dates parseable,
  `effective_from` a real date, `latency_minutes` non-negative.
- **Cross-reference against the asset calendar** - a dataset naming a
  month the calendar has no date for has zero slots. This is the
  drift check that justified one calendar over 30 date lists, so it
  has to actually run.
- **Internal consistency** - schedule versions ordered and
  non-overlapping on `effective_from`, no duplicate calendar dates, a
  dataset not both subsetting and overriding.
- **Referential** - every dataset named in asset config has a
  contract and vice versa. At 30 datasets this is where a typo hides
  indefinitely.

Warning only:
- **Runway** - "fewer than N supplies remain" is "act soon", not
  "this is broken". Failing an otherwise-fine build on it is how a
  gate gets disabled.

All config-only, no `data/` access, so it is safe in CI under the
standing rule.

