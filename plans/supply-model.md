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

**One requirement was known to be wrong, and has been fixed.**
`REQ-PIPE-035` was written as "QA runs against a warehouse composed of
every table's current version", before cross-period composition was
dropped (Thread J). Rewritten 2026-09-22 as "QA runs against one
period's schema, with the staged delivery overlaid", with the dropped
composition recorded in its own `decisions:` so the rejection survives
the rewrite rather than looking like it was never considered.

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

1. ~~**Close the open items**~~ - **DONE 2026-09-22.**
2. ~~**One last chaos-engineering stress test**~~ - **DONE 2026-09-22**,
   see Thread H's second pass.
3. ~~**Work up a delivery plan**~~ - **DONE 2026-09-22**: 24 sprints
   below, reviewed with Keith.
4. **Feed requirements to `delivery-scoper`, in the batches below.**

**Where this actually stands, 2026-09-23.** Batches 1 and 2 are BUILT -
sprints 1 through 6, every requirement `built` and signed off. That is
the whole spine: check identity, the generator and delivery format,
status parity, the timezone parameter, schedule config and its gate,
and periods/slots with runway.

**Six requirements were SIGNED OFF on 2026-09-23 - but they are NOT
batch 3, and building cannot start.** They were walked through with
Keith one at a time and signed: `REQ-PIPE-034` (per-dataset
arrival history), `REQ-PIPE-035` (one period's schema, staged delivery
overlaid), `REQ-PIPE-036` (a delivery triggers one QA run), `REQ-QAC-037`
(cross-table checks in their own scope), `REQ-PIPE-038` (committed
history keyed per dataset, delivery log beside it), `REQ-DASH-041`
(supply history and as-of viewing under per-dataset arrivals).

**They are sprints 13, 14, 15, 16 and 19** - not sprints 7-10 as the
batch label claimed - and a `delivery-scoper` sense-check run the same
evening found four defects in them plus a long carry-over list. See
"Batch 3's scoper sense-check" above for all of it. **Keith's sequencing
decision, 2026-09-23: scope sprints 7-10 FIRST**, then bring these six
back where they actually fit the sprint order, fixing the four defects
as and when each is reached.

**The walkthrough changed them substantially - read the requirements,
not this summary.** Three of the six turned out to carry a SUPERSEDED
MODEL, all drafted 2026-09-21 before staging, promotion and the period
schemas were settled: `034`'s "current version" (split into most
recently ARRIVED and most recently PROMOTED), `037`'s "composed
warehouse" (the cross-period composition Thread J had killed), and
`041`'s unqualified "arrival" (now explicitly the arrival, never the
promoted supply). That is a pattern rather than three coincidences, and
it is the reason to re-read a batch against the current model before
building rather than trusting it was current when drafted.

Substantive additions the walkthrough produced, each recorded on its own
requirement: staged data lives IN the warehouse in one global staging
schema with a separate global rejected schema (both departing
deliberately from Keith's operational system); the overlay is an
ephemeral per-run view schema, needed for logical-to-physical name
resolution rather than for cross-schema reads - dbt and Soda were
verified by real experiment to read across schemas perfectly well; a
mixed-period delivery fans out into one QA run per period and never
auto-promotes; a late table re-evaluates its own checks plus those that
depend on it, within the same period only; cross-table checks record the
physical table names they read; and the delivery log is one immutable
file per delivery, queried in place by DuckDB with no second copy.

**One new requirement fell out**: `REQ-DASH-056`, showing what arrived
alongside what is actually promoted - Keith's own ask once `041` settled
that the as-of view shows the arrival. Unsigned, and deliberately scoped
as information rather than a status. Its one open question - tile,
detail panel, or both - is for the dashboard UX agents; Keith's own
words, he has ideas but wants their thoughts first.

**Placement stays with the architect**: where the delivery log and the
cross-table scope physically live. Agreed as non-blocking, but not to
stay parked.

**Batches 4, 5 and 6 are not scoped yet** - sprints 11-24 have no
requirements beyond the handful of dashboard ones already drafted. Batch
4 is the next `delivery-scoper` pass, and it chains off batch 3's
answers, so it waits on the sign-off above rather than running beside
it.

### Scoper batches

Settled with Keith, 2026-09-22, replacing the two-batch split agreed
2026-09-21 - at 24 sprints that split would have put 18 in one batch,
which he judged too many. **Cut at the seams where the CONCEPTS change
rather than evenly**, so a batch's questions can be answered without
reaching into the next one.

| Batch | Sprints | What it is |
|---|---|---|
| **1 · Preconditions** | 1-4 | check identity, generator + delivery format, status parity, timezone |
| **2 · Schedule and slots** | 5-6 | schedule config + validation, slot derivation |
| **3 · Arrival and filing** | 7-10 | delivery recognition, arrival/staging, assignment, classification - **STILL UNSCOPED as at 2026-09-23, see below** |
| **4 · Decisions and storage** | 11-14 | promotion, decision log, warehouse, `qa_results/` |
| **5 · QA under the new model** | 15-18 | delivery-triggered QA, check deps, red-for-unrun, drift |
| **6 · Dashboard** | 19-24 | supply history, freshness, decision-log display, activity feed, snapshots, time-granular as-of, plus the embedded period sequences moved here 2026-09-23 |

Batch 2 is only two sprints, deliberately: they are the SPINE -
everything downstream is defined as a comparison against the slot
sequence - so it gets its own pass rather than being buried in a batch
of six.

**The batch table above describes the PLAN, and on 2026-09-23 the plan
and the register disagreed.** Six requirements were signed off believing
they were batch 3; they are actually sprints 13-16 plus 19, and sprints
7-10 have no requirement at all. See "Batch 3's scoper sense-check"
below for the full account. Keith's call: scope 7-10 first, then place
those six where they really belong. **Check a batch's contents against
this table before trusting either one.**

Batch 6 is the biggest at six. Homogeneous enough to hold together, but
**split it at 19-21 / 22-24 if it comes back sprawling** - the seam is
"showing current state" versus "showing history and activity".

**Sequencing - five passes, not six.** The 2026-09-21 reasoning still
holds (a later batch depends on an earlier one's answers, and
conflating them produces tangled questions), but not every batch
chains:
- **Batches 1 and 2 run TOGETHER** - batch 1 is genuinely independent of
  everything.
- **Batches 2 -> 3 -> 4 -> 5 chain**, each needing the previous one's
  answers.
- **Batch 6 depends on 2-5**, and nothing depends on it.

The one parallel pair is parallel because the dependency genuinely
permits it, not to save time.

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

  **Both halves now settled, and they came apart rather than resolving
  together.** They were written up as entangled: whether re-file is
  atomic looked like it depended on whether "un-decide" (demote back to
  staging for re-review) exists at all. The answers, 2026-09-22, are
  **(B) atomic re-file** and **YES to un-decide** - which the original
  framing said could not both hold, because it assumed un-decide
  existing would make demote-then-promote the natural way to re-file.
  It does not. They are different acts with different reasons: un-decide
  says "this needs another look", re-file says "this belongs in a
  different period", and a system that can do the first is not thereby
  obliged to express the second as two of them. So re-file stays one
  log entry with a from-slot, a to-slot and one reason, AND staging can
  hold a supply a human has already looked at once. What un-decide
  existing does make unconditional is the STICKINESS rule (Thread G) -
  without it the next run re-promotes what a human just demoted.
- ~~**What happens to a `nodata` supply**~~ - **CLOSED 2026-09-22.** It
  was the same question as TS-21 (a check-less table's supply IS a
  nodata supply), and the CI gate settled there makes the state
  unreachable. Every remaining `nodata` case is "nothing was owed",
  which never reaches a promotion decision.

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
- ~~**Cross-cadence check period ownership**~~ - **CLOSED BY SCOPE
  2026-09-22.** Keith: "we won't have cross cadence checks, so there
  won't be a case where we have a check spanning the day table and the
  quarterly one. That just doesn't happen." Recorded as closed by SCOPE
  rather than ANSWERED, so a future session reading this does not
  reopen it as unresolved - if a cross-cadence check ever does appear,
  the question is live again and unanswered.
- ~~**Operator identity**~~ - **SETTLED 2026-09-22**, see Thread G.

**Swept in full on 2026-09-22, and again after that day's decisions** -
five items were genuinely open that morning; two are now settled, one is
deliberately deferred to its own batch, and the two that remain are
parked by design. A SIXTH was then found later the same day, while
reading the real code for the concept inventory below, and it is the
one item here a batch actually needs an answer to - everything else can
go to the scoper as it stands. Settled items are kept in place rather
than pruned, so they read as settled rather than vanishing, which is
how a closed question gets silently reopened:

1. ~~**Is "un-decide" an operation we want?**~~ - **SETTLED 2026-09-22.
   YES.** Keith: "I think undecide is an operation. Undecide, that is."
   Demote-to-staging is a real operation, distinct from rejecting: it
   means "put this back in the queue for someone to look at again".
   Consequences, all of which were already written up conditionally in
   Threads B and G and are now unconditional: the stickiness rule is
   REQUIRED (auto-promotion only ever acts on a supply no human has
   touched, or the next run re-promotes what a human just demoted), and
   staging holds supplies in two distinguishable situations - never
   decided, and decided-then-undecided. Re-filing stays ATOMIC anyway
   (TS-11, settled separately): un-decide existing does not make
   demote-then-promote the way to move a supply between periods, it
   just means a supply CAN sit in staging having been looked at once.
   Builds in batch 4 (sprints 11-12).
2. **Whether to build an as-published RECONSTRUCTION path at all**,
   given snapshots already answer that question. **Deliberately
   deferred to batch 6** - Keith, 2026-09-22: "let's settle that when
   we get to batch six." Not an input to batches 1-5, so it does not
   gate the scoper.
3. **"Current version" vs "good version"** - inherited from
   `plans/publishing-and-history.md` item 6, deliberately parked to be
   settled alongside `plans/conceptual-design.md` Thread A's amber
   accept/reject governance rather than separately.

   *What the question actually is*, since the two-word label does not
   carry it: when `cp-placements` arrives RED, what does the warehouse
   serve - the version the agency actually sent, or the last one that
   passed QA? "Good version" means a QA tool quietly substitutes older
   data for bad data, which is not reporting reality; a consumer would
   read a clean table and never learn the latest supply was rejected.
   The likely answer is **current version, full stop** - status is
   REPORTED, not ACTED ON - which makes "good" the wrong word for the
   alternative and is why the question is phrased this way. It is
   parked rather than settled because it is really the same governance
   question as amber accept/reject: both ask what the pipeline is
   allowed to do on a human's behalf about data quality, and answering
   one without the other invites two inconsistent answers.
4. **What a "run" means for supply history** - a RE-CHECK task rather
   than an open question: per-table slots and the dateless `run_id` may
   already have resolved it.

   *What needs re-checking*: today a `run_id` is ONE DELIVERY across
   six tables, and Phase 7's resupply-chain redesign derives chain
   membership from a per-run AGGREGATE status. Per-table arrivals break
   both halves of that - six independent timelines rather than one, and
   no single status to aggregate. The existing supply-history UI is
   built on the old shape, so the task is to open it against the new
   model and find out whether it survives, degrades, or needs
   rebuilding. Note the delivery concept (Thread B) partially rescues
   it: a delivery IS still one observed arrival of several tables, so
   there may be a real grouping to keep - just not one that owns a
   single verdict.
5. ~~**Verify GitHub's concurrency queueing behaviour**~~ - **DONE
   2026-09-22**, see Thread H. Confirmed: GitHub holds only ONE pending
   run per group, so three rapid decisions silently lose the middle one.
   An opt-in queueing mode exists but is edition-gated; Keith's call the
   same day was not to rely on it, so drain-the-backlog is the whole
   mechanism, not a fallback behind a belt.

6. ~~**What the word "delivery" refers to, given the generator already
   uses it for something else**~~ - **SETTLED 2026-09-22.** Found the
   same day by reading the real code for the concept inventory below
   rather than by design work: today's `delivery_id` means the logical
   obligation across attempts, which is what this model calls a SLOT,
   while this model's "delivery" is one physical arrival. Same word,
   swapped referent, old sense live in all three generator modules.

   **The generator adopts the agreed vocabulary** - Keith: "the
   generator should be using the new names around slot and delivery and
   so forth. We shouldn't be changing the concepts we've agreed on."
   The design does not bend to the code. So `delivery_id` becomes
   `slot_id`, `delivery_date` becomes the period/due date (exact naming
   is batch 1's to settle), and "delivery" takes its new sense in the
   generator too.

   **`is_resupply`, `supersedes_run_id` and `attempt_number` GO, rather
   than being renamed** (Keith, same conversation). They are already on
   the retire-as-authority list below, so sweeping them into the rename
   as `slot_`-prefixed fields would preserve exactly the bookkeeping
   this model stops trusting. A resupply becomes an arrival landing in
   a filled slot - observed, not recorded.

   **The cost of rewriting committed history is explicitly a non-issue**
   - Keith: "I don't care. This is all just fake data. We can nuke it
   from orbit and rerun all the fake data, rerun all the QA." And he
   would do that BEFORE the build rather than as part of it, so no
   requirement needs to plan a migration over the ~352 committed runs.

   **Lands in batch 1**, which already owns the generator and the
   delivery format; left later, the scoper writes requirements whose
   vocabulary contradicts the code it is reading.

~~**Two requirements need work before their sprint**~~ - **DONE
2026-09-22.** `REQ-PIPE-035` was REWRITTEN (it specified the
cross-period composition Thread J dropped; it now specifies one
period's schema with the staged delivery overlaid, and records the
composition decision as rejected rather than losing it) and
`REQ-PIPE-036` was REVISED (its trigger is now a DELIVERY, not a
table - the per-dataset independence survived, the per-table trigger
did not). Both remain `not_started` and UNSIGNED.

**And the standing gate**: all eight existing requirements
(`REQ-PIPE-034`..`REQ-DASH-041`) are `not_started` and UNSIGNED, and
anything `delivery-scoper` produces is a PROPOSAL. `CLAUDE.md`'s
sign-off rule applies before any of it is built - scoping is not
sign-off. See Thread G.
## Batch 3's scoper sense-check - findings, 2026-09-23

**Status:** todo (2026-09-23) · **Category:** Pipeline & publishing

Keith's call to run the six signed batch-3 requirements through
`delivery-scoper` as a sense-check, after this session found they had
never been through it. His words: "even if it won't come back with much,
it'll be a good sense check." It came back with a great deal. Recorded
here in full because the agent transcript does not survive, and because
the carry-over list below is the thing that has never been done for this
batch.

### The finding that reframes the rest: these six are not sprints 7-10

**Verified against the sprint list, not taken on trust.** The six map to:

| Requirement | Actual sprint |
|---|---|
| `REQ-PIPE-034` arrival history | ~8, and only the RECORD, not staging |
| `REQ-PIPE-035` period schema + overlay | **13** - one database, many schemas |
| `REQ-PIPE-038` `qa_results/` keying | **14** |
| `REQ-PIPE-036` delivery-triggered QA | **15** |
| `REQ-QAC-037` cross-table scope | **16** |
| `REQ-DASH-041` supply history / as-of | **19** |

So they are sprints 13-16 plus 19 - batches 4, 5 and 6 - and **sprints
7, 8, 9 and 10 have NO requirement at all**: delivery recognition and
file-to-dataset mapping (`REQ-GEN-043` built only the FORMAT, nothing
consumes it), staging load, slot assignment, and arrival classification.

They were hand-drafted 2026-09-21 from `plans/publishing-and-history.md`
item 6, before the batching scheme existed, then labelled "batch 3"
because the batch table said batch 3 was sprints 7-10. Nobody checked
the label against the contents.

**Two BUILT, SIGNED requirements already wrote IOUs against a batch 3
that does not contain them:**
- `REQ-PIPE-052` defers "oldest claimable unfilled slot,
  on-time-wins-for-the-current-slot, monotonic filling, hold for a
  human" to batch 3. Those phrases appear exactly once in the whole
  register - in that deferral. "hold for a human" appears zero times.
- `REQ-PIPE-053` depends by name on "replaying the backlog in
  arrival-timestamp order, which is batch 3's rule", and on a filing
  layer for three of its own criteria.

**Consequence**: building these six requires inventing slot assignment -
which this file itself calls "the highest-risk sprint in the plan - two
cascades were found here by stress-testing, one created by the fix for
the other" - with no requirement, no acceptance criteria and therefore
no sign-off, which CLAUDE.md's gate forbids. The obvious implementation
("oldest unfilled slot") is precisely the one Thread E proves
catastrophic.

**Keith's decision, 2026-09-23**: scope sprints 7-10 FIRST. These six
come back afterwards, placed where they actually fit the sprint order,
and the four defects below get fixed as and when they are reached.

### Four defects in the signed six

**D1. `REQ-QAC-037` criterion 6 is factually wrong.** It says cross-table
checks keep "the section of their own that `REQ-DASH-033` gives them".
`033` gives them no such section - it created SUPPLY-LEVEL and
TABLE-LEVEL sections, which are about same-table rules. Verified against
the real built data: the canonical cross-table check, "Client reference",
renders as an ordinary COLUMN check on `cp_client_id` with `scope: None`
in all three of notifications, investigations and placements. Worse,
`033`'s own criterion folds those checks into the dataset's own status -
exactly what Thread I settled against. The real requirement is Thread
I's table: blocked table red with a chip, healthy neighbour green with a
pointer NAMING the blocker, the red landing at COLLECTION level. That is
new dashboard behaviour, not a "continue to". The error originates in
item 6's answer 2 and propagated unchecked into a signed criterion.

**D2. `REQ-DASH-041` c3 contradicts TS-28 and Thread H.** 041 says the
as-of view shows the most recent ARRIVAL, never the promoted supply
(Keith, 2026-09-23). Thread H wrinkle 1 says "as at T = the latest
version PROMOTED on or before T"; wrinkle 7 names `clipDatasetToAsOf()`
directly and says filtering on arrival "becomes wrong the moment
promotion lands"; and TS-28, approved by Keith 2026-09-22, expects a
supply promoted on Friday to be ABSENT from the as-at-Wednesday view.
The 2026-09-23 decision is newer and wins, but TS-28 carries the
standing obligation that every scenario gets a unit test, and its
expected result is now the opposite of a signed criterion. Someone will
write that test. A clean resolution probably exists - the WAREHOUSE's
"as at T" is promotion-filtered, the DASHBOARD's as-of is
arrival-filtered, because the dashboard reports QA rather than warehouse
contents - but nothing says so and TS-28 needs rewording.

**D3. A three-way contradiction about where a cross-table result lives.**
`REQ-PIPE-036` c4 scopes each tool invocation to one dataset "so that
the tool's raw output describes that dataset alone and needs neither
duplicating nor filtering". `REQ-QAC-037` c1/c2 require a cross-table
result filed against its own scope, not duplicated. `REQ-PIPE-038`'s own
decision says splitting a raw output per dataset means either copying it
or filtering it, which "breaks the genuinely-unmodified guarantee".
A cross-table check is DECLARED inside one dataset's block
(`contract/child-protection-soda-checks.yml`, under `cp_notifications`),
so under per-dataset invocations its result lands in that dataset's raw
output, and filing it elsewhere needs exactly the copying-or-filtering
038 forbids. Sharper still: `REQ-QAC-039` (built) bakes the dataset into
every `check_id` - the real id reads
`...child-protection.cp-notifications.cp_client_id.relationships_soda` -
so a result whose identity permanently names `cp-notifications` is to be
filed under a scope that is explicitly not `cp-notifications`. This is
not the placement question 037 parked for the architect; it is whether
identity and filing may disagree.

**D4. `REQ-PIPE-034`'s "most recently PROMOTED" cannot be answered by
anything forbidden to touch `data/`.** Its decision derives it as the
newest table in the newest period schema holding one - a WAREHOUSE
CATALOGUE read. The neighbouring decision, written in the same session,
forbids exactly that reasoning for the ARRIVED side because "the
dashboard build may never touch data/, so it cannot read the catalogue
at all". The identical argument applies to the promoted side and was not
applied. Concretely, `REQ-DASH-056` wants the dashboard to show "latest
supply is red and staged, promoted version is Monday's" - and under 034's
derivation the dashboard build cannot compute that at all. The right
source is Thread G's committed append-only decision log, which does not
exist until batch 4. A build-order fact to record, not a design to ship.

### Carry-over: decisions in the threads that NO requirement holds

The mechanical check CLAUDE.md requires per batch, never done for these
six. Only the NOT-CARRIED items are listed - carried ones need no
action. Rejected alternatives are marked X, because those are what get
re-proposed once prose is deleted.

**Thread A - storage.** A resupply is a NEW TABLE in the same schema,
not an overwrite (`build_cp_warehouses.py` does `CREATE OR REPLACE`
today, so the cheapest implementation satisfies 035's read-the-newest
criterion by keeping exactly one version and destroys the history that
criterion exists for). Table contents immutable once written BUT tables
CAN move between schemas - the movability half is what makes
promotion/demotion/re-file cheap. Physical table names carry the arrival
timestamp, stated once as a rule rather than inferred from two
requirements that depend on it. "Show me Q3" and "show me as at 30 June"
become different questions once early arrivals exist - Keith's call was
to stick with as-at. And a live item: nothing in the dashboard says
which axis it is on.

**Thread B - staging and promotion.** X "file by arrival, period as
correctable metadata". Staging asserts only what is known, so it can
never be wrong. The quarterly/daily difference is ONLY who pulls the
trigger. **The content check survives as a DETECTOR, not a decider** -
"this supply does not look like the period it is filed under" is a
legitimate non-circular QA finding, and it is the only thing that turns
a wrong default filing into something a human sees; no requirement owns
it. WHY global staging rather than per-slot (034 records the departure
from Keith's operational system WITHOUT the reason, which is the worst
combination - a later session sees the difference and no argument, and
corrects it back). Why a rejected schema at all. "Rejected" is a
DECISION state, not a QA verdict. X rejected-as-a-LABEL in the promoted
schema, because "a filter every query must remember to apply is a
false-green generator". Why the rejected schema is global. Retention
explicitly out of scope. The four-version scenario and there being NO
superseded state. X promoting the loser as a non-current version.
Red never auto-promotes. An unexpected table is INFORMATIONAL.

**Thread D - arrival classification (sprint 10, no requirement).** Every
substantive decision is uncarried. Classify against the period the
supply was FILED to, never one re-derived from the arrival date -
symptom of getting it wrong: "filed to Q3, reported late for Q2".
Classification REMOVES a property rather than adding one. **Slot
ASSIGNMENT and PROMOTION are two steps, not one** - assignment is a
derivation with no human in it, promotion is a decision - and a REJECTED
supply still gets classified, because "arrived three weeks late AND was
bad" is what belongs on the record. The verdict stops being a frozen
historical fact once re-filing exists, which contradicts
`pipeline/cadence.py`'s current docstring. The dashboard's JS never
recomputes classification.

**Thread E - slot assignment (sprint 9, no requirement).** The rule
itself: assign to the oldest slot whose claim window is open and which
is unfilled; if none, it is a RESUPPLY of the most recently filled slot.
NEVER CLAIM FORWARD, and why the risk is asymmetric - backwards is one
contained error, forwards cascades through every future delivery. The
ambiguous case defaults but is MARKED as assigned under ambiguity and
surfaced. What a boundary misfile actually costs: the reporting is wrong
TWICE - a punctual supplier recorded as a very late resupply, and the
next slot left unfilled so it goes overdue as a phantom. Arrival into a
filled slot never auto-promotes whatever its status. X a "within X of
the window opening" trigger, because X is a magic number. Resupply after
REJECTION is routine, after ACCEPTANCE is odd. **Punctuality is evidence
of which slot a supply is for** - the backward-cascade fix. X closing a
slot's window when the next opens, and X a finite lateness tolerance.
`not_expected` versus MARKED MISSED, and why the distinction stops
supplier reliability becoming whatever people were willing to excuse.

**Thread H - chaos findings.** Assign in ARRIVAL-TIMESTAMP order, never
discovery order, with a defined tiebreak - `REQ-PIPE-053` already
depends on this by name. **Monotonic filling** - a slot stops being
claimable once a later slot is filled - plus its named limit, hold for a
human when nothing is confidently claimable; without it a missed
delivery is recorded as MET, which the thread rates worse than a cascade
because it manufactures a delivery that never happened. Two files in one
delivery matching one dataset's pattern - hold for a human (sprint 7).
Conflicting decisions record both, last wins, serialised, each run
drains the backlog. Re-filing into an occupied slot supersedes and
warns.

**Thread I - the multi-table nodata seam.** The existing `nodata` is a
different KIND from the new per-check one. Cross-cadence checks: closed
by SCOPE rather than answered (Keith: "we won't have cross cadence
checks"), and that closure exists only in prose. ARRIVAL triggers QA,
never promotion, because promotion-as-trigger LOOPS. A supply's
promotion decision considers every check its arrival caused to run, not
only checks defined on that table. **I6, which the thread itself labels
LOAD-BEARING and no requirement holds: check results are CONDITIONAL on
that supply being promoted, a period's status is computed from promoted
supplies only, and a rejected candidate leaves its period's dependent
checks back at cannot-run.** The load-bearing case is TS-18 - the
cross-table check evaluates GREEN and the candidate is then rejected for
a different reason; keep the verdict and a check reads green for a
period whose data never entered the warehouse. Promotion does not re-run
anything, it promotes the VERDICT alongside the data - which rests on
tables being immutable. That identity holds only if QA and promotion are
SERIALISED per period. The trap to be written down as INTENDED
behaviour: a multi-table check refusing to run reads red even though
data exists for every table it spans, and "would be helpfully 'fixed' by
a later session without the reasoning attached". X exclude-from-worst-of
plus an "18 of 24 checks evaluated" count. What each level shows - the
healthy neighbour green with an informational POINTER naming the
blocker, the red landing at COLLECTION level, and it is a pointer, NOT a
duplicated result. **Checks must DECLARE their participating tables
(`depends_on`), and the cannot-run rule is NOT COMPUTABLE without it** -
`grep depends_on requirements.yaml` returns zero, while three signed
criteria depend on it. The three temporal reference kinds
(`previous_period` / `baseline` / rolling `window`) as real design
choices per check, not settings.

**Test scenario register.** TS-3's "what this family is FOR" note - the
four sub-tests assert that a KNOWN IMPERFECTION STAYS CONTAINED rather
than that the system gets the right answer, and the register says
explicitly to label them so a later session does not "fix" them.

### Further points worth keeping

- A crash between staging load and QA has no defined behaviour. 038
  writes a delivery's file ONCE at recognition and never rewrites it, so
  after a crash mid-load the delivery is on record, some tables are
  staged, possibly partially written, and nothing says whether the next
  run skips it or re-processes it. A truncated table in a global staging
  schema is indistinguishable from a real short supply and would be QA'd
  as real data. 035 names orphaned VIEW schemas; nothing names orphaned
  STAGED TABLES.
- `read_json_auto` over immutable multi-year delivery files needs an
  explicit column spec, so the first added field breaks the view or is
  silently dropped. A `format_version` per delivery file is cheap
  insurance.
- A CROSS-AGENCY check has no collection to be lifted to. 035
  deliberately spans the whole asset per period so cross-agency checks
  are ordinary same-schema queries; Thread I resolves cross-table filing
  as "the COLLECTION's". At 30 datasets across agencies this stops being
  hypothetical.
- `REQ-PIPE-035` does not carry the mothman-only constraint, although it
  introduces new entry points (schema creation, staging load). 034, 036
  and 038 do.
- PRIVACY, judged rather than asked: 035 names the period schema as the
  most sensitive artefact this design creates, correctly, but does not
  name the GLOBAL STAGING and GLOBAL REJECTED schemas - new, never
  emptied, spanning every agency, holding every supply ever received
  INCLUDING ones rejected because they were wrong. An extract with
  columns nobody should have sent sits there forever. Retention being
  out of PoC scope is the right PoC call; what is missing is that the
  deferral is recorded only in prose due for deletion.
- `REQ-PIPE-038`'s regeneration is sequenced before promotion exists
  (sprint 11), so a regeneration run now produces a history where
  nothing is ever promoted, every period schema is empty and every
  cross-table and drift check is red-for-unrun - the whole of Child
  Protection permanently red in committed history. And once the
  warehouse's contents are a function of human promotion decisions it is
  no longer regenerable from `data/` alone; rebuilding needs the
  decision log replayed.
- `REQ-PIPE-035`'s one-database rule is a VERIFIED HARD BLOCKER against
  parallel runs. Tested with genuinely separate processes: while one
  holds a read-write connection, a second writer fails AND a read-only
  reader fails - `IO Error: Could not set lock on file`. It is one
  PROCESS, not one writer. `mothman pipeline run` is parallel by
  default, and dbt runs as its own writing process
  (`dbt build --store-failures` materialises a model plus an audit table
  per failing test into the same file). The per-run databases that
  currently provide this isolation for free are removed by the same
  requirement. A workable shape exists - a private scratch database per
  run for dbt's materialisation and audit tables, with the shared
  warehouse ATTACHed read-only and all shared writes serialised through
  one load/promotion step - but it needs deciding.

### Four questions the scoper prepared, still open

1. **One DuckDB database and concurrent QA runs** - private scratch per
   run with the warehouse attached read-only; or one writer with
   everything serialised; or per-run databases for dbt only.
2. **Where a cross-table result is filed, given its identity permanently
   names one dataset** - let identity and filing disagree; give
   cross-table checks their own identity segment (a second rename,
   needing its own exception); or file under the defining dataset and
   lift at render time.
3. **As-of: arrival or promotion, and what TS-28 now asserts** - two
   different views both correct, with TS-28 retagged as a warehouse
   scenario; invert TS-28 to match 041; or carry both axes explicitly
   in the dashboard.
4. **When committed history is regenerated** - twice; or build 038's
   shape now and regenerate once after batch 4; or regenerate now and
   accept a wall-to-wall red Child Protection for however long batch 4
   takes.

## Batch 3 proper - sprints 7-10 scoped, 2026-09-23

**Status:** todo (2026-09-23) · **Category:** Pipeline & publishing

Keith's sequencing call after the sense-check found sprints 7-10 had no
requirement at all. One pass over all four, going deepest on sprint 9.
Eleven requirements, `REQ-PIPE-057`..`REQ-PIPE-067`, **all unsigned** -
scoping is not sign-off, and several carry open questions that would
change what gets built.

**The carry-over check was done and came back empty.** Every decision in
Threads A, B, D, E, F, H and I bearing on sprints 7-10 is now either
carried on a requirement's own `decisions:` or has an explicit
not-needed-because. Threads D and E, which the sense-check found almost
entirely uncarried, are carried in full - both cascades with their
worked tables, every rejected alternative, and the `not_expected`
versus marked-missed distinction.

**One decision is carried but UNOWNED**: the content check as a
DETECTOR rather than a decider ("this supply does not look like the
period it is filed under"). It is a check, so it belongs with batch 5.
Recorded on `REQ-PIPE-065` so it survives Thread B's eventual deletion,
but it still needs a `QAC` requirement of its own.

**Two build-order facts, neither a design problem:**
- `REQ-PIPE-060` needs the one-database-many-schemas model that
  `REQ-PIPE-035` specifies and **sprint 13** builds. Staging has nowhere
  to stage into before then. Either sprint 13 moves forward to sit with
  sprint 8, or staging gets built twice.
- A slot closed by monotonic filling can only be resolved by a human
  marking it missed, which is **sprint 12**. Until then such a slot is
  permanently red and unclearable - correct, and visibly unfinished.

**A live trap found by running the real code rather than reading it.**
`qa_tools/common/slots.py`'s `next_unfilled_claimable()` implements
"oldest claimable unfilled slot" with **no on-time-wins branch and no
monotonic filling** - which is exactly the rule Thread E proves
catastrophic. Nothing calls it yet, so it is a trap rather than a bug.
Its own docstring made it worse: it said the missing half was the
RESUPPLY case, never mentioning the other two absences, so a reader
trusting that account would reach for it as "the assignment rule". A
warning has been added to the docstring itself, where the reader
actually is; `REQ-PIPE-062` is what extends it.

**Threads A, B, D, E, F and H are NOT yet safe to delete** - their last
dependent batch is not built, and CLAUDE.md's rule 4 says delete a
thread whole once it is. What rule 3 has now established is that
nothing in them lives only in the prose.

### The on-disk delivery structure, for Keith's review

His own ask (`plans/running-thoughts.md` #36). This is the real layout
under `data/` today - gitignored, 60 deliveries, 42 Birth Registrations
and 18 Child Protection. **Sprint 7 changes none of it; sprint 7 is the
consumer.**

```
data/
  deliveries/                        <- the supplier's side of the boundary
    EXTRACT_20260824/                <- ONE delivery. The DIRECTORY is the boundary.
      birth_registrations_2026-08-24.csv
    Data Extract 01 Feb 2023/        <- another. Six files, ONE arrival.
      cp_clients.csv
      cp_notifications.csv
      ... four more
    01bcad0f3bee/                    <- names follow NO pattern, on purpose
    monthly_extract_may2025/
    drop-9023/
  receipts/                          <- OURS. Outside every delivery.
    EXTRACT_20260824.json            <- {"delivery": ..., "received_at": ...} and nothing else
  generator_bookkeeping.json         <- the generator's own notes.
                                        NO pipeline module may read it.
```

What recognition reads out of that, and nothing else:

| Question | Answered from | Never from |
|---|---|---|
| What arrived together? | the directory | any file's contents |
| When did it arrive? | our own receipt record | a file mtime, a column, anything a supplier wrote |
| Which dataset is this file? | that dataset's own `arrivalPattern`, against the FILENAME alone | the directory name, file order, position |
| Which collection? | the datasets its files matched | the delivery's name |
| What order did arrivals happen in? | the receipt instants | directory order, the names |
| Which slot or period? | **nothing here answers that** | any declaration inside the delivery |

**Two facts about the current tree that bear on sign-off**, both found
by running the real matcher rather than reading it:
1. **All 60 deliveries are clean** - zero unmatched files, zero
   anomalies, zero duplicate matches. The awkward shapes
   `docs/delivery-format.md` says the generator CAN emit are capability
   held by `REQ-GEN-044`, not present in the history. So sprint 7's
   interesting paths have no real data behind them yet.
2. **The duplicate-match hold cannot fire for Child Protection at all**
   under today's patterns. CP's six match exactly one filename each
   (`^cp_clients\.csv$`), so the split-extract shape the normative doc
   calls legitimate - `cp_clients.csv` plus `cp_clients_part2.csv` -
   matches nothing, and the second file falls out as unrecognised
   instead. Reachable for Birth Registrations only because its pattern
   carries a `{date}` placeholder. This is `REQ-PIPE-058`'s open
   question.

### Open questions waiting on Keith

**ALL EIGHT SETTLED 2026-09-24** with Keith, and each answer now lives
on the requirement it belongs to rather than here - the lists below are
kept only as the record of what was asked and what the scoper itself
picked. Where an answer went AGAINST the pick it is marked inline, since
that is the case a later reader is most likely to get backwards.

**Non-functional**, each with the scoper's own pick:
1. **A crash between staging load and QA** - a truncated table in a
   global staging schema is indistinguishable from a real short supply.
   Derive completeness from the warehouse catalogue and re-stage
   (*pick*); a committed processing marker; or re-process everything
   every run.
2. **One DuckDB database versus parallel runs** - verified: while one
   process holds a read-write connection, a second writer AND a
   read-only reader both fail. Private scratch database per run with the
   warehouse attached read-only (*pick*); one writer serialised; or
   per-run databases for dbt only.
3. **What recognition may report in public** - an unrecognised
   artefact's filename is what an operator needs, would be committed and
   rendered, and this repo is public. Full filenames (*pick, for the
   PoC, with file CONTENTS never read or recorded*); extension plus a
   hash; or recorded but never rendered.
4. **How much replay per run** - incremental with a marker; full
   deterministic replay; or incremental with a `mothman` command to
   force a full one (*pick*). Note full replay would silently undo human
   re-filings.

**Design forks**, each with the scoper's own pick:
1. **A delivery directory with no receipt record** - today a hard error,
   and one such directory currently fails recognition for EVERY
   delivery. A real transport produces this state for seconds during an
   upload. Keep the error; treat as in-flight and report if it persists
   (*pick*); or skip silently.
2. **What form the per-dataset filename pattern takes** - today an S3
   `keyPattern` whose last segment is reused as a filename matcher, one
   config value doing two jobs. Keep it; an explicit filename pattern
   with placeholders (*pick*); or a real regex per dataset, which means
   regex over untrusted supplier filenames.
3. **Does a held supply get checked while held?** No checks until filed
   (*pick*); only its own single-table checks; or against the most
   recent period. Applies to both hold cases and should be answered once.
4. **A delivery holding files for two collections** - today
   `arrivals.py` raises, stopping the whole run including the other 29
   healthy datasets. Hold it and keep processing (*pick*); or keep the
   hard error because the transport boundary itself is wrong.
   **SETTLED 2026-09-24, AGAINST THE PICK: neither.** A delivery MAY
   span collections and is processed normally - spanning is legitimate,
   not malformed, so a hold would stop healthy supply. The consequence
   Keith accepted with it is that a run stops being one-to-one with a
   delivery: one such arrival produces two runs, one per collection, and
   receipt order becomes global rather than per-collection. See
   `REQ-PIPE-057`, `REQ-PIPE-061`, TS-36/TS-36b. Unchanged by it: the
   mixed-PERIOD delivery, which runs QA and never auto-promotes
   (TS-33a, sprint 11).

### Also flagged, not this batch's to fix

- **`REQ-PIPE-038` should gain a `format_version` criterion** for the
  delivery file. `read_json_auto` over years of immutable files needs an
  explicit column spec, so the first added field breaks the view or is
  silently dropped. 038 is signed, so this is Keith's call.
- **`REQ-PIPE-066` invalidates the usual correctness check**, and it is
  worth saying before the work starts: today's history measures 0 early
  / 240 on time / 112 late, and the new derivation will legitimately
  change those numbers. The seeded regenerate-and-diff proves nothing
  here.

## Concept inventory

**Status:** todo (2026-09-22) · **Category:** Pipeline & publishing

Written 2026-09-22, at Keith's request, immediately before the first
scoper batches. It answers three questions in one place - what this
model INTRODUCES, what it CHANGES about something that already exists,
and what it RETIRES - because the sprints and threads above describe
the destination without ever saying which parts of today's vocabulary
survive the trip.

Grounded in the real code rather than in this file's own prose. That
mattered: reading the generators turned up a name collision nothing in
the design work had noticed, recorded first below because it is the
one item here that is actively hazardous rather than merely useful.

### The collision: "delivery" already means something else

`delivery_id` exists today, in both generators' manifests and in every
committed `dataset_stats.json`. It means **the logical obligation** -
`delivery_120` spans attempt 1, resupply 1 and resupply 2, each its own
`run_id` and its own CSV, chained by `supersedes_run_id`.

Under this model **a delivery is one physical arrival** - the observed
transport unit, one folder drop, one prefix, one session (Thread B).
And the thing today's `delivery_id` actually describes is what this
model calls a **slot**.

So this is not a new word arriving into empty space. It is the same
word with its referent swapped, while the old sense stays live in
`generator/generate_runs.py`, `generator/generate_cp_runs.py`,
`generator/resupply.py` and all committed history. Somebody reading the
generator while building arrival recognition will read "delivery" and
get precisely the wrong concept.

**Decide it in batch 1, not batch 3.** Batch 1 already owns the
generator and the delivery format, so the naming call lands there
naturally; left to batch 3, the scoper writes requirements whose
vocabulary contradicts the code it is reading. The options are to
rename the generator's own field to `slot_id`, or to give the new
concept a different word. Not settled here - it needs Keith.

### 1. New concepts

**The spine** (batch 2). Everything downstream is defined as a
comparison against these, which is why they get their own pass:
- **Period** - a named bucket on the ASSET's calendar (`2026-Q3`, or
  `2026-09-22`), carrying a date. What a schema is named after. Added
  to this list 2026-09-22: Keith noticed the inventory described a
  "period schema" while never naming period itself, and the gap turned
  out to be hiding a real modelling error (Thread C).
- **Slot** - one `(table, period)` pair that is actually expected,
  carrying its own `due_at`, grace and claim window. One period, many
  slots.
- **Schedule** - authored quarterly dates plus daily cadence,
  effective-dated; the asset owns the calendar, a dataset owns its
  participation in it.
- **Claim window** - the interval before a slot's due time in which it
  can be claimed. What makes forward mis-attribution structurally
  impossible rather than merely unlikely (Thread E).

**Filing** (batches 3 and 4):
- **Staging** - arrival-ordered, asserting only the thing actually
  known (this landed at this time), so it can never be wrong.
- **Promotion**, and with it **demotion**, **un-decide** and
  **re-file** as four distinct operations rather than one with modes.
- **Period schema** - one schema per period, all within one database.
- **Delivery**, in its new sense above.
- **Decision log** - append-only: who, when, what, which, why.
- **Operator identity** - `actor: {kind: human|rule, id}`, and a log
  that refuses to record a decision carrying no identity.
- **GitHub Issues as the write channel** - the dashboard stays
  read-only, and issues are the channel, never the system of record.

**Derived rather than stored:**
- **Overdue as a computed property** - a query over schedule plus slot
  state, not an event anything has to fire. Same shape as the
  exhausted-schedule banner.

**Checks** (batch 5):
- **`depends_on`** - a check's lateral dependency, declared, because
  "any table this spans" is not knowable from a tool's check syntax.
- **Temporal `reference`** - `previous_period`, a fixed `baseline`, or
  a rolling `window`. A real design choice per check, not a knob.
- **Red-for-unrun, with a qualifying chip**, plus the pointer
  indicator on a healthy table blocked by a neighbour.

### 2. Existing concepts this model CHANGES

| Concept | Today | Under this model |
|---|---|---|
| `run_id` | `run_120_2026-09-19`, carrying a date | Dateless; a run is no longer one delivery across six tables |
| Supply granularity | One arrival is one collection, six CP tables | One supply is one table version; six independent timelines |
| Resupply | DERIVED - chain membership inferred from per-arrival aggregate status, red opening a chain and green/amber closing it | OBSERVED - an arrival landing in an already-filled slot, with nothing to infer |
| Cadence | The only schedule mechanism; quarterly computed from anchor months | One of two; quarterly becomes authored dates, with a run-out banner |
| `nodata` | "Nothing landed in the current expected cycle", which also swallows cannot-run | Narrows to "nothing was owed"; cannot-run becomes red |
| As-of | Filters runs by `run_date <= asOfDate` | Latest version PROMOTED on or before T, end of day, later time-granular |
| Warehouse | One DuckDB file per run | One database, one schema per period |
| `qa_results/` keying | Per collection | Per dataset, with today's history regenerated |
| Check identity | Hierarchy implied in several places | One hierarchy stated once, including inside `check_id` |
| Staleness | Collapses a whole column to `nodata` | Freshness is its own axis, CAPPING the headline |
| `CHANGELOG_FEED` | A QA-publish changelog | An activity feed carrying arrival anomalies, with severity |
| Data asset | A placeholder string in `data-asset.yaml` | A real level owning the calendar and a default supply cadence |

### 3. What this model RETIRES, in two kinds

Worth keeping apart, because they need opposite handling: one kind
needs acceptance criteria to remove it, the other needs a `decisions:`
entry so nobody proposes it again.

**Retired from real code** - these exist today and come out:
- `qa_tools/bdm/build_per_run_warehouses.py` and its CP sibling. Their
  whole justification was that dbt and Soda have no run-scoped
  `WHERE`; schema-per-period gives the same isolation and matches the
  real operational system (Thread J).
- `is_resupply`, `supersedes_run_id`, `attempt_number` and
  `delivery_id` AS AUTHORITY. Phase 7 already stopped deriving chains
  from them; this finishes the job. They may survive as generator
  bookkeeping, but nothing downstream reads them.
- The date inside `run_id`.
- Per-collection QA triggering, in favour of per-delivery.

**Rejected on paper, never built** - record, do not delete:
- **Cross-period composition.** The specified design in `REQ-PIPE-035`
  until 2026-09-22. Killed by red-for-unrun: carry-forward was the only
  reason cross-period assembly existed.
- **The clock-driven trigger**, and the timeout sweep for a table that
  never showed. Delivery-triggering removes the clock entirely.
- **Supplier-declared period**, and **deriving a period from the data's
  own content**. Both rejected in Thread B, each for a reason that will
  recur.
- **`nodata` as a supply state.** Closed as unreachable.
- **`queue: max`.** Rejected 2026-09-22 as edition-gated.

### Not a retirement, checked

`AS_OF_OFFSET_DAYS` is already fully gone - `contract/data-asset.yaml`
no longer declares it and nothing reads it. Every remaining mention in
the repo is a comment explaining what replaced it. It belongs on no
list here.

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

1. **[done, 2026-09-23]** **[QA checks & contract]** **Check identity.**
   `REQ-QAC-039` - one hierarchy, stated once, including in a check's own
   `check_id`. BUILT 2026-09-23; that requirement now owns the decisions,
   including two the build itself turned up.

   First because it is baked into all 257 hand-authored checks; changing
   it later is a corpus-wide edit.

2. **[done, 2026-09-23]** **[Data generation]** **Generator delivers one
   table at a time, and injects the scenario shapes.** All three parts
   BUILT, 2026-09-23. `REQ-GEN-042` did the VOCABULARY - slot vs
   delivery, period vs receipt instant, dateless deterministic run ids,
   a pinned anchor, and the schedule read from the shared calendar
   config. `REQ-GEN-043` did the ON-DISK DELIVERY FORMAT, specified in
   `docs/delivery-format.md`, and took the pipeline off the generator's
   manifest onto recognised arrivals. `REQ-GEN-040` did ONE TABLE AT A
   TIME and arrival timing - a resupply carrying some of a collection
   and not the rest, down to a single dataset, plus supplies landing
   before they were due or arbitrarily after. Each requirement owns its
   own decisions now, including the dozen the builds themselves turned
   up.

   **One deliberate hold, Keith's own call 2026-09-23**: those shapes
   are CAPABILITY, not committed history. A partial Child Protection
   delivery cannot be loaded by today's warehouse builder, so emitting
   one would take CP's pipeline down until the staging overlay exists.
   `REQ-GEN-044` carries putting them into the real history, and
   depends on sprint 7's `REQ-PIPE-035`/`036` being able to read them.

   What is LEFT in this sprint's own area is `REQ-GEN-044`/`REQ-GEN-045`:
   the `[INJECT]` set from the test scenario register below, actually
   present in the generated history, plus the scenario map that says
   where each one landed.

   **Moved here from sprint 6** (Keith, 2026-09-22). It gates roughly
   two-thirds of the test scenario register: the generator today emits
   whole deliveries only and never partial, produces ZERO early supplies
   (measured 0 early / 240 on time / 112 late), and `run_id` still
   carries dates. Until this lands, most of the model cannot be
   exercised against real data at all - and the injected shapes are how
   Keith sees any of it working.

3. **[done, 2026-09-23]** **[Pipeline & publishing]** **Status parity
   between the two implementations.** BUILT as `REQ-QAC-047`, which now
   owns the decisions - including three the build itself turned up. The
   defect was worse than this entry said and present on BOTH sides: an
   unrecognised status read green in each, by two different routes. A
   second, unpredicted gap had the two disagreeing about whether a check
   with an EMPTY retirement date was retired. And a test written for
   `REQ-PIPE-053` earlier the same day had asserted the defect as
   intended behaviour, which is the argument for a shared table in one
   incident.

   Landed BEFORE per-check `nodata` exists, which was the point.

4. **[done, 2026-09-23]** **[Pipeline & publishing]** **Timezone
   parameter.** One repo-wide config value replacing
   `pipeline/cadence.py`'s hardcoded `AWST_OFFSET`; stored timestamps
   carry their offset (Thread H). BUILT as `REQ-PIPE-048`, which now
   owns the decisions - including one the build turned up: the
   dashboard had been showing YESTERDAY's date every Perth morning.

   Small, independent, and every later sprint compares instants. Built
   out of sprint order for exactly that reason, once building
   `REQ-GEN-042` showed it was a dependency rather than a sibling.

5. **[done, 2026-09-23]** **[Pipeline & publishing]** **Schedule config
   and its validation gate.** Both halves BUILT, 2026-09-23.
   `REQ-PIPE-049` did the CONFIG - authored dates (quarterly) or
   cadence rule (daily), `delivery_months` participation,
   `effective_from` plus changelog, `not_expected`. `REQ-PIPE-050` did
   the GATE, as `mothman schedule validate`, registered in `mothman
   check` and in the deploy workflow. Built ahead of sprints 2 and 3
   because `REQ-GEN-042` turned out to depend on it rather than sit
   beside it. Each requirement owns its own decisions.

   **The retrospective-edit guard was built after all** - the open
   question `REQ-PIPE-050` carried, settled by Keith 2026-09-23 once
   the cost was confirmed as one `git show` of one file rather than the
   deep clone the rejected version needed. Moving a delivery date that
   has already passed now fails the build unless the version's
   changelog says what changed.

   Runway is the one thing Thread K listed here that is NOT in the
   gate: it is measured in slots, and slots do not exist until sprint
   6, so it belongs to `REQ-PIPE-053`.

6. **[done, 2026-09-23]** **[Pipeline & publishing]** **Periods and
   slots.** All three parts BUILT, 2026-09-23. `REQ-PIPE-051`
   derives the period sequence version by version - which turned out to
   fix a real latent bug, not just add a function: authoring a second
   calendar version would have DELETED every earlier period rather than
   leaving it alone. `REQ-PIPE-052` derives slots as periods crossed
   with each dataset's own participation, each carrying its own due
   instant, grace allowance and claim window. `REQ-PIPE-053` did the
   low-runway warning measured in slots, and the exhausted-schedule
   state (Thread C). Each owns its own decisions.

   **One deliberate hold on `REQ-PIPE-053`, and it is why that
   requirement's `built` overclaims.** Its criteria about failing at
   FILING, accepting supplies while exhausted, and a run summary naming
   what it skipped all need a filing layer that does not exist until
   sprint 8. Their tests land there. The requirement carries this in
   its own `[BUILD]` decision, including why `in_progress` was not
   available: the register's gate forbids evidence on anything not
   built, so the alternative was to drop the record of what WAS
   verified.

   The spine. Nothing downstream can be built before it.

   *Scope grew 2026-09-22*: period and slot are now separately defined,
   and `due_at` belongs to the SLOT, not the period - so this sprint
   builds two derivations rather than one sequence.

   *Scope shrank again 2026-09-23*: **embedding the period list into
   the built dashboard MOVED TO BATCH 6** (`REQ-DASH-054`, Keith's
   call). `cycleStartDate()` reimplements `cycle_start()` in JS for the
   as-of picker, and JS can compute a cadence rule but cannot compute
   an authored date list, so the embed is still needed - just not here.
   `delivery-architect` found the requirement labelled this sprint
   while depending on the unsigned `REQ-DASH-041`, and the same
   reasoning that puts every dashboard sprint last decided it: the
   coordinates that picker reasons about are still moving while slot
   assignment and promotion are unbuilt. **Accepted cost: the as-of
   picker silently returns nothing on a quarterly asset until batch
   6.**

7. **[todo, 2026-09-22]** **[Pipeline & publishing]** **Delivery
   recognition and file mapping.** What constitutes a delivery for a
   given source (folder, prefix, session); the per-dataset filename
   pattern that maps a file to a table; the **hold for a human** when
   two files in one delivery match one dataset's pattern (Thread H,
   second chaos pass #3/#4).

   **New sprint, added 2026-09-22.** The delivery boundary is
   load-bearing - it is what replaced the clock-driven trigger - and
   nothing owned it.

   **Scoped 2026-09-23**: `REQ-PIPE-057` (the boundary, and what
   recognition reports), `REQ-PIPE-058` (file-to-dataset patterns and
   their gate), `REQ-PIPE-059` (two files, one dataset - hold). All
   three unsigned. Before this, arrival and staging assumed a delivery
   had already been recognised and its files already attributed.

8. **[todo, 2026-09-21]** **[Pipeline & publishing]** **Arrival and
   staging.** Our own receipt timestamp, never the supplier's; staging
   asserting only arrival facts; replay in arrival-timestamp order
   (Threads B and H).

   Arrival order is load-bearing, not tidiness: assignment reads slot
   state, so discovery order changes the answer.

   **Scoped 2026-09-23**: `REQ-PIPE-060` (staging asserts only arrival
   facts) and `REQ-PIPE-061` (receipt-order processing and backlog
   drain - the rule `REQ-PIPE-053` already depends on by name). Both
   unsigned.

   **SPRINT 13 SPLIT, and its single-database half moves HERE** (Keith,
   2026-09-24). Staging has nowhere to stage into otherwise: it needs
   one durable database holding a staging schema, which is the part of
   sprint 13 that retires the per-run warehouses and gives each test
   worker its own database. The SCHEMA-PER-PERIOD half stays at 13,
   where it belongs - building period schemas here would mean shelves
   years before anything decides what goes on them.

   **Why the split is safe, stated precisely because it stops being
   safe if the order changes.** Thread J's argument for retiring per-run
   databases is that schema-per-period gives the same ISOLATION. Move
   the single-database half forward without it and there is a window
   with one database and no per-run isolation - which is fine ONLY
   because nothing runs QA between here and sprint 15. Two consequences
   travel with that: dbt, the concurrent writer behind the verified
   one-process-per-database blocker, does not run until QA does, so that
   blocker does not bite here either. If QA ever moves earlier than 15,
   this split stops holding and both halves have to move together.

9. **[todo, 2026-09-21]** **[Pipeline & publishing]** **Slot
   assignment.** Claim windows, on-time-wins-for-the-current-slot,
   monotonic filling, and hold-for-a-human when nothing is confidently
   claimable (Threads E and H).

   The highest-risk sprint in the plan - two cascades were found here by
   stress-testing, one created by the fix for the other.

   **Scoped 2026-09-23**: `REQ-PIPE-062` (the rule, both cascades,
   never claim forward), `REQ-PIPE-063` (monotonic filling),
   `REQ-PIPE-064` (hold for a human), `REQ-PIPE-065` (ambiguity and
   filled-slot arrivals). Four requirements rather than one,
   deliberately - the sprint's own risk note is the argument for each
   rule having its own criteria and its own tests. All unsigned.

10. **[todo, 2026-09-21]** **[Pipeline & publishing]** **Arrival
   classification.** Early / on-time / late against the ASSIGNED slot,
   never a slot re-derived from the arrival date (Thread D).

   Separate from sprint 9 so the assignment rules can be verified before
   anything reports on them.

   **Scoped 2026-09-23**: `REQ-PIPE-066` (classify against the assigned
   slot, and retire the arrival-date derivation) and `REQ-PIPE-067`
   (the verdict follows the filing). Both unsigned.

11. **[todo, 2026-09-21]** **[Pipeline & publishing]** **Promotion and
    rejection.** Auto on green/amber into an EMPTY slot; red never;
    landing in a filled slot never (Thread B). Plus the **mixed-period
    delivery gate** - a delivery whose tables land in different PERIODS
    runs QA but never auto-promotes (Thread H, TS-33).

    *Scope grew 2026-09-22*: the mixed-period gate is a promotion rule
    rather than an assignment one, so it lives here. Note its condition
    is different PERIODS, not different SLOTS - per-table slots mean an
    ordinary six-table delivery already spans six slots.

    **A third disposition exists and is NOT here**: sprint 25's
    carry-forward, where no supply arrives at all and a human accepts
    it never will. Promotion and rejection both act on a supply that
    exists; that one acts on the absence of one. Noted here because
    "promotion and rejection" reads like a complete set of outcomes and
    is not.

12. **[todo, 2026-09-21]** **[Pipeline & publishing]** **The decision
    log, and the GitHub Issues write path.** Append-only; who, when,
    what, which, why; automated decisions recorded the same way with the
    rule as actor; demotion stickiness; **re-filing** (confirmed in
    scope); and the log **refusing to record a decision with no
    identity** (Thread G).

    *Scope grew 2026-09-22*: the write path is GitHub Issues, from the
    standing principle that the dashboard is read-only. It extends
    `ticket_sync.py`'s existing `/accept` mechanism rather than being
    new architecture. **Issues are the write CHANNEL, not the system of
    record** - the pipeline reads the issue and writes an immutable
    entry to the committed log.

    Pairs with sprint 11 and could merge with it, but kept separate
    because it is what makes mutable filing safe and deserves its own
    verification.

    **Conflicting decisions on one supply**: record both, LAST WINS,
    both operators notified by the ticket being updated with the
    outcome. Decisions are applied **serialised per supply, in
    comment-timestamp order**, and **each run DRAINS THE BACKLOG** -
    reading all unprocessed decisions since a marker rather than only
    the triggering event, so a cancelled run costs nothing. Settled
    2026-09-22, see Thread H.

13. **[todo, 2026-09-21]** **[Pipeline & publishing]** **SPLIT
    2026-09-24 (Keith). What remains here is SCHEMA-PER-PERIOD**; the
    single-database half - retiring the per-run warehouses, one database
    per test worker (Thread J) - **moved to sprint 8**, because staging
    has nowhere to stage into without it.

    Test isolation is deliberate rather than incidental - the per-run
    databases were providing it by accident and `pytest-xdist` is the
    default - and it travels with the single-database half, since tests
    run from sprint 8 onward.

    See sprint 8 for why the split is safe and the one condition that
    would break it: Thread J's argument for retiring per-run databases
    is that schema-per-period supplies the same isolation, so the gap
    between the two halves is only survivable while nothing runs QA in
    it.

14. **[todo, 2026-09-21]** **[Pipeline & publishing]** **`qa_results/`
    keyed per dataset.** `REQ-PIPE-038`, including regenerating today's
    history under Keith's one-off exception.

15. **[todo, 2026-09-21]** **[Pipeline & publishing]** **Delivery-
    triggered QA.** `REQ-PIPE-036` - QA runs once per DELIVERY, per
    period touched, rather than per table arrival.

    *Reworded 2026-09-22*: the requirement's intent survives - Child
    Protection's QA stays independent of Birth Registrations' - but the
    trigger is a delivery, not a table. Per-table triggering makes
    cross-table checks flicker red on every healthy delivery (TS-13).
    `REQ-PIPE-036` was revised against this the same day, so the sprint
    can be built from the requirement as it now stands.

16. **[todo, 2026-09-21]** **[QA checks & contract]** **Check
    dependencies, and the zero-active-checks gate.** `depends_on` on
    multi-table checks plus its validation, and `REQ-QAC-037` lifting
    cross-table checks to the collection scope (Thread I). Plus the CI
    gate failing a table with **zero ACTIVE checks** (TS-21).

    The cannot-run rule is not computable without `depends_on` - "any
    table it spans" is not knowable from a tool's check syntax.

    *Scope grew 2026-09-22*: the zero-checks gate lives here rather than
    with check identity, because it is a `mothman check` gate over check
    configuration like the `depends_on` validation beside it. ACTIVE,
    not defined - a table whose checks have all been RETIRED hits the
    same green-by-vacuum path, and retirement is gradual so nothing
    prompts a look.

17. **[todo, 2026-09-21]** **[QA checks & contract]** **Red-for-unrun.**
    The status, its qualifying chip, and the pointer indicator on a
    healthy table blocked by a neighbour (Thread I).

18. **[todo, 2026-09-21]** **[QA checks & contract]** **Drift and trend
    dependencies.** A declared temporal reference; missing-but-expected
    is red, no-prior-period is `nodata`. `REQ-PIPE-035` was rewritten
    2026-09-22 and now carries both cases as acceptance criteria, so
    this sprint no longer has to fix the requirement before building
    it.

19. **[todo, 2026-09-21]** **[Dashboard UI]** **Supply history and
    as-of under per-dataset arrivals.** `REQ-DASH-041`.

20. **[todo, 2026-09-21]** **[Dashboard UI]** **Freshness axis and
    banners.** Freshness capping the headline status; the
    exhausted-schedule banner (computed from config, so it renders even
    when the pipeline that would have produced results did not run);
    arrival-into-a-filled-slot; the blocked-check pointer (Threads C and I).

21. **[todo, 2026-09-21]** **[Dashboard UI]** **Decision-log display and
    the as-corrected default** (Thread K).

22. **[todo, 2026-09-22]** **[Dashboard UI]** **The activity feed.**
    `CHANGELOG_FEED` (built by `qa_tools/common/changelog.py`) stops
    being a changelog and becomes an **activity feed**, carrying arrival
    anomalies alongside QA activity: early and late arrivals, supplies
    held for a human, arrivals into a filled slot, unexpected tables and
    unrecognised artefacts. Basic filtering, and **design and colour
    distinguishing severity** - informational versus warning versus
    significant - so a routine early arrival reads differently from
    something needing action (Threads B and H).

    **New sprint, added 2026-09-22.** It came out of TS-10 and TS-15 and
    had no home. Not `RELEASE_NOTES` (the repo-root `CHANGELOG.yaml`
    tracking the PoC's own development), which is a different feed and
    unaffected.

23. **[todo, 2026-09-21]** **[Dashboard UI]** **Automatic snapshots**, on
    every publish, deduplicated by content hash (Thread K).

24. **[todo, 2026-09-22]** **[Dashboard UI]** **Time-granular "as at".**
    The as-of control accepts an optional TIME alongside the date, so an
    intra-day sequence - promoted 14:00, demoted 22:00 - can be viewed
    at any point rather than only at its end state (Thread H, second
    chaos pass #6).

    Scoped in at Keith's request, 2026-09-22, having first been recorded
    as an unscoped later refinement.

    - **A refinement, not a reversal**: a date-only input still means
      END OF DAY. Time is an optional drill-down; the common case stays
      one click.
    - **It kills a real dependency.** The snapshot-based answer to
      intra-day granularity holds only while each decision triggers its
      own publish. With time-granular as-of the intermediate state comes
      from the decision log itself, so batching decisions into one
      publish stops mattering.
    - **Snapshots still earn their place** - they answer "what the
      dashboard SAID at that moment", where this answers "what was TRUE
      at that moment, as we now understand it".
    - The scenario map's links (see the register) can then target an
      instant rather than a date, which matters for the injected
      scenarios whose whole point is an intra-day sequence.

    **Last, and deliberately**: it depends on both the decision log
    (sprint 12) and the as-of work (sprint 19), and nothing depends on
    it.

25. **[todo, 2026-09-24]** **[Pipeline & publishing]** **CARRY-FORWARD:
    a period whose supply never arrives, and a human decides to point it
    at the previous period.** Keith, 2026-09-24. A genuinely new
    concept, adjacent to promotion and rejection (sprint 11) rather than
    part of either, and it has no requirement anywhere yet.

    **NAME COLLISION, FLAGGED FIRST because this file has been bitten
    by exactly this before** (see "The collision: delivery already means
    something else" in the concept inventory). Keith, 2026-09-24, uses
    "carry forward" for TWO DIFFERENT THINGS. This sprint is one of
    them. The other - a regularly scheduled dataset whose supplies are
    FOR THE FOLLOWING PERIOD, so data arriving in January fills Q2 and
    not Q1 - is a scheduling property, is not in these sprints, and
    lives at `plans/road-testing.md` item 3. They share a phrase and
    nothing else. His own alternative names for THIS one are
    **backfill** or **patch**; the real name is still his to pick, and
    picking one that the other concept cannot also claim is part of the
    job.

    **Who it is for: DOWNSTREAM CONSUMERS, not reporting** (Keith,
    2026-09-24, correcting an earlier reading here that had it the other
    way round). This is not primarily about making the dashboard say
    something sensible about an empty period. It is about the people and
    systems querying the warehouse, who need SOMETHING to resolve for
    the current period rather than an empty table or a broken query.

    **The situation, in his own framing.** A dataset's slot for a period
    goes unfilled, the period passes, and a human decides the data is
    not coming - "a data set's been red and no data supplied all
    throughout the cycle". We still need something, and **the best
    something we have is the last GREEN supply**. So a human makes the
    call and takes the action.

    **The write path is a human decision through GitHub or the TUI** -
    both, in his own words, rather than one settled channel. The trigger
    is lateness, which opens a ticket (see below).

    **The trigger is LATENESS, and it goes through GitHub Issues like
    every other decision** (Keith, 2026-09-24, correcting an earlier
    reading recorded here that had this deliberately bypassing the
    Issues channel - see the correction note at the end). When a supply
    ticks over to LATE, that opens a ticket. The ticket is the thing a
    human acts on, and carry-forward is one of the actions available
    from it. So there is no special write path: the same
    read-only-dashboard principle and the same sprint-12 Issues
    mechanism apply, and this is not an exception to either.

    **The action is a DATABASE action, not a QA one** - Keith's own
    framing, "less about QA and more about database stuff". Create a
    view in that period's schema, for that table, pointing at the
    previous period's table. Anything querying the period by its
    logical name resolves to last period's data. That is exactly the
    logical-name-to-physical-table indirection `REQ-PIPE-035` already
    establishes, aimed one schema further back.

    **It DOES trigger a re-QA of that table** (Keith, 2026-09-24,
    reasoning it through in the moment and worth recording with his
    reason rather than just the outcome): the carried-forward table has
    dependents, and cross-table checks that read it need to be
    re-evaluated against what the period now actually resolves to. Not
    re-QAing would leave every dependent check holding a verdict about
    an empty period.

    **A carried-forward slot COUNTS AS FILLED** (Keith, 2026-09-24,
    settling this directly) - **but it must read as carried forward in
    the dashboard, never as an ordinary green.** His own words: "no one
    could look at it and go, oh, it's green and it's good. No, it's
    green. And then next to it, it should say carry forward or
    something." That is the **status-plus-qualifier chip** vocabulary
    this model already uses elsewhere - the "no data" qualifier on an
    overdue dataset, and a check that could not run. Same pattern, new
    qualifier, rather than a new visual language.

    **A late arrival AFTER a carry-forward is HELD for a human** (Keith,
    2026-09-24). It does not silently replace the view, and it does not
    get discarded - a human decides, which keeps the carry-forward a
    real decision rather than a default that any later event can undo.

    **Naming is unsettled** - he offered "rollback" and "patch" as
    candidates and neither convinced him. Both are misleading: nothing
    is being reverted and nothing is being repaired. "Carry-forward" is
    used above as a working label only, chosen because it says what
    actually happens, and the real name is his to pick.

    **Still open:**

    - **How it appears in the dashboard, mechanically** - Keith's own
      open question: does the carried-forward period appear as a table
      in its own right that we re-QA (which it is, physically - a view
      with real check results against it), or as a period that CALLS
      OUT that it is pointing elsewhere? The qualifier chip settles the
      LABELLING; this is about whether the period has its own row of
      check results or borrows the previous period's.
    - **WHAT DETECTS LATENESS, and what acts on it** (Keith,
      2026-09-24, explicitly flagged as an open decision for when this
      is scoped). Two candidates: lateness is checked as part of the
      natural running of QA, so any run sweeps every dataset for
      overdue slots; or it is a scheduled job of its own, a cron.

      **Worth separating detection from action before choosing**, since
      the two are not the same problem. Lateness is ALREADY derived,
      client-side, as a pure function of schedule, as-of date and fill
      state - that is what produces the red-with-"no data"-qualifier
      reading in the freshness scenario above. So nothing needs to be
      computed that is not computed today; what is missing is the ACTOR
      that turns a derived state into a durable event, namely the
      ticket.

      **The case against QA-run-triggered is specific**: a dataset that
      never arrives produces no QA run of its own, so detection would
      ride on some OTHER dataset's run happening. At 30 datasets on a
      quarterly asset there are quiet stretches where nothing arrives
      at all - which is precisely the situation this whole concept
      exists for. The mechanism would be weakest exactly when it
      matters most.

      **The case against a cron has a real, verified gotcha**: GitHub's
      own documentation states that in a PUBLIC repository, scheduled
      workflows are automatically disabled after 60 days with no
      repository activity. This repo is public, and a quiet quarterly
      asset is exactly a repo with little activity - so the scheduled
      job would switch itself off during the stretch it is meant to
      cover, silently. Checked against docs.github.com 2026-09-24
      rather than recalled.

      **Note lateness detection needs NO data access** - only the
      schedule and promotion state - so unlike most computations in
      this pipeline it is not excluded from CI by the never-touch-
      `data/` rule. That widens the options rather than settling them.

      **And whichever is chosen, it must be idempotent**: a daily sweep
      must not open a new ticket every day for the same late supply.
      That is the same marker-and-drain discipline sprint 12 already
      establishes for decisions, not a new mechanism.

    - **Does the carry-forward chain?** Two consecutive missed periods:
      does period 3 point at period 2's view, or straight through to
      period 1's real table? A chain of views is fragile and a resolved
      pointer is a second thing to keep correct.
    - **Which sprint.** It needs schema-per-period (sprint 13) to have a
      period schema to create the view in, the decision log (sprint 12)
      to record the decision and carry the Issues write path, and
      arrival classification (sprint 10) to know a supply is late in
      the first place.

    **Correction recorded rather than silently overwritten**, because
    the wrong version was written into this file first and a later
    reader may have seen it. The original entry said this was the first
    decision in the model whose write path was deliberately NOT GitHub
    Issues, reasoning that a dataset which never arrived produces no
    arrival, no QA run and therefore no trigger. That reasoning looks
    sound and is wrong: **lateness is itself the trigger**, and the
    model already detects it. Worth keeping visible because the same
    mistake - concluding that an absence cannot raise an event - would
    be easy to make again.

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

## Test scenario register
**Status:** todo (2026-09-22) · **Category:** Testing & dev tooling

Every scenario worked through while shaping this model, with the
narrative behind it and the expected result under the model as settled,
so requirements and tests cite one list rather than re-deriving it from
the threads. Keith's ask, 2026-09-22, before any of this goes to
`delivery-scoper`. Reviewed by him the same day - feedback by exception,
so anything without a "Keith:" note below was approved as written.

**Two standing obligations, both his:**

1. **Every scenario here gets a unit test.** Not a subset, not the
   interesting ones - all of them.
2. **The scenarios KEITH PROPOSED get INJECTED into generated
   deliveries**, so they are visible in the real dashboard rather than
   only green in a test run. Flagged `[INJECT]`. The rest are `[unit]`
   (pure logic) or `[both]` (needs a shape to drive a rendered
   assertion).

**Every scenario must state its CONFIG.** Found during Keith's review,
and it invalidated two expected results as first written (TS-3, TS-5):
an outcome like "files as a resupply of Wednesday" is meaningless
without the cadence, the due time and the claim-window size, because a
different window gives a different - and equally correct - answer. Any
scenario whose result depends on the window says so explicitly below.

**No scenario label on the injected runs** - Keith, 2026-09-22: "this is
still just a proof of concept remember". A first draft argued for one,
to stop the dashboard growing permanent red that looks like a defect.
For a PoC that is over-building: the red IS the point and the audience
knows the data is synthetic.

**Instead: a SCENARIO MAP** - "which scenario, and where do I go to look
at it". Generated by the generator (the only thing that reliably knows
where each shape landed - a hand-written map drifts the first time the
seeded data is regenerated), committed as markdown (the dashboard build
reads committed files only and may never touch `data/`), rendered in the
dashboard, regenerated by a `mothman` subcommand. Same pattern
`plans/INDEX.md` already uses. Entries read like
`TS-1 · Birth Registrations · run_047-run_049 · 2026-07-14`.

**Each entry is CLICKABLE, and lands you on the thing itself** - Keith,
2026-09-22: "if I click on a test, it takes me to the relevant as-of
date and then the relevant page for the check, the dataset or the data
collection." Two design points so this does not get built the wrong way
round:

- **The map carries COORDINATES; the dashboard constructs the LINK.**
  The generator knows the dataset, the run ids, the as-of date and the
  check - it does not, and should not, know the dashboard's routing
  scheme. Emitting URLs from the generator would couple the two and
  break silently the next time a route changes.
- **The target is an AS-OF DATE, not a snapshot.** Keith floated both.
  As-of is right: the live dashboard defaults to as-corrected, so an
  as-of link shows the scenario as we now understand it, whereas a
  snapshot shows what was published at the time - a different question,
  and the wrong one for "show me this scenario working".

Only the `[INJECT]` set can carry a link. A `[unit]` scenario has no
data behind it and nothing to navigate to, so those entries say so
rather than rendering a dead link.

### Slot assignment

**TS-1 `[INJECT]` Forward cascade.**
*Config: daily, due 12:00.*
Monday's supply arrives 14:00 and fails QA - red, rejected, so Monday's
slot stays unfilled. A resupply lands 16:00, passes, and is promoted, so
Monday is now filled. Then a THIRD file arrives at 20:00 the same day.
**Expect**: the 20:00 arrival files as a **resupply of Monday**, because
Tuesday's claim window has not opened and no claimable unfilled slot
exists. Being a filled slot, it does NOT auto-promote - it holds and
warns (TS-4).
**Breaks as**: files as Tuesday's supply; the next file takes Wednesday;
every later supply is permanently off by one, each day looking locally
plausible.

**TS-2 `[INJECT]` Backward cascade.**
*Config: daily, due ~22:00.*
Monday received and filled. The supplier's system goes down for an
upgrade - found out 9pm Tuesday, too late to renegotiate. Wednesday
missed too. The next supply arrives on time at 22:00 Thursday.
**Expect**: files as **Thursday** (on-time-wins-for-the-current-slot).
Tuesday and Wednesday stay unfilled, go overdue, and a human marks them
missed with a reason.
**Breaks as**: files as Tuesday, two days late; the next as Wednesday;
the feed sits permanently two days behind for ever.

**TS-3 `[INJECT]` Arrival just OUTSIDE the claim window - four
sub-tests.**
Reframed from daily during Keith's review: the original example (22:00
due, 21:57 arrival) does not work at all, because the claim window opens
BEFORE due_at, so 21:57 sits comfortably inside it and files to Tuesday
correctly. The scenario only bites where the gap genuinely exceeds the
window.

Split into four at Keith's request - both slot states, at both cadences.
**The symmetry is the point**: the same four outcomes at quarterly and
daily scale prove the rule is cadence-INDEPENDENT and that the window is
the only thing that varies.

**TS-3a `[INJECT]` Quarterly, prior slot FILLED.**
*Config: quarterly, calendar Feb 2 / May 1 / Aug 3 / Nov 2, early window
14 days. Feb and May filled. Supply arrives 19 July - one day outside
August's window, which opens 20 July.*
**Expect**: August is not claimable, May and Feb are filled, so no
claimable unfilled slot exists -> **resupply of May**. Being a filled
slot it does **not auto-promote**; it holds and warns (TS-4).

**TS-3b `[INJECT]` Quarterly, prior slot UNFILLED.**
*Same config, but May's slot was never filled.*
**Expect**: May is claimable -> fills **May, ~79 days late**.

**TS-3c `[INJECT]` Daily, prior slot FILLED.**
*Config: daily evening-before - the supply for day D is due 22:00 on
D-1 - early window 4 hours, so Tuesday's window opens 18:00 Monday.
Monday's slot filled. Arrival 17:00 Monday, one hour outside.*
**Expect**: Tuesday not claimable, Monday filled -> **resupply of
Monday**, no auto-promotion, holds and warns.

**TS-3d `[INJECT]` Daily, prior slot UNFILLED.**
*Same config, but Monday's slot was never filled (Monday's supply was
due 22:00 Sunday).*
**Expect**: Monday is claimable -> fills **Monday, 19 hours late**.

**What this family is FOR, and it is a different kind from the rest.**
Most scenarios here assert the system gets the right answer. These
assert that **a known imperfection stays contained**:
1. The claim window gates exactly where config says - an arrival just
   outside does not reach forward. Never-claim-forward under test at its
   own boundary, which is the property both cascades rest on.
2. The FILLED branches prove the rules COMPOSE - a misfiling cannot
   silently promote, because a human is shown it.
3. The UNFILLED branches are not imperfections at all: if the prior slot
   never filled and something turns up, reading it as that slot's very
   late supply is entirely reasonable.
Label them as such, so a later session does not "fix" them.

**TS-4 `[INJECT]` Arrival into an already-filled slot.**
A supply arrives for a period that has already been accepted.
**Expect**: never auto-promotes whatever its status; warns; the message
names the context ("a supply arrived for Monday, which was already
accepted at 16:00", plus the boundary detail where relevant); and the
three genuinely different actions are reachable - **accept** as a
correction, **re-file** to another slot, **reject** as a duplicate.

**TS-5 `[unit]` Monotonic filling - a missed slot must not absorb a
later resupply.**
*Config: MUST be stated per variant - Keith's correction.*
Tuesday missed entirely. Wednesday arrives on time at 22:00, green,
promoted. A further supply arrives 23:00 Wednesday.
**Expect**: Tuesday is **non-claimable**, because a later slot
(Wednesday) is filled. That is the whole point of the test.
**What the 23:00 arrival then does DEPENDS ON CONFIG**, and the first
draft asserted one answer unconditionally:
- Thursday's window shut at 23:00 -> no claimable unfilled slot ->
  **resupply of Wednesday**.
- Thursday due Wednesday evening (an evening-before feed), so its window
  is open and past due -> **fills Thursday**, correctly, and is not a
  resupply at all.
**Breaks as**: files as Tuesday - recording a missed delivery as MET,
using another day's data. Worse than a cascade, because it manufactures
a delivery that never happened.

**TS-6a `[unit]` Genuine lateness still fills its own slot.**
*Config: daily.* Monday's slot unfilled; Monday's supply arrives Tuesday
03:00 with Tuesday not yet filled.
**Expect**: fills **Monday, late**. Monotonic filling does not block it,
because no later slot is filled.

**TS-6b `[unit]` A rolling lag stays correctly recorded.**
Continuing 6a: Tuesday's supply arrives Wednesday 03:00, Wednesday's
arrives Thursday 03:00.
**Expect**: each fills its own slot, each classified one day late.
Nothing is left permanently unfilled - the feed is simply running a day
behind, and says so.

**TS-6c `[unit]` A skipped day becomes missed, and a later backfill
cannot be placed.**
Continuing 6a: Tuesday's supply never comes, and Wednesday's arrives on
time at 22:00.
**Expect**: Wednesday's fills **Wednesday** (on-time-wins). Tuesday now
has a filled successor, so it is **non-claimable** -> missed, overdue,
red, and a human marks it missed. If Tuesday's supply then turns up
afterwards, **nothing is claimable** and it is **held for a human**
(TS-7) rather than defaulted forward.

Split into three at Keith's request: as one test it hid exactly the
ambiguity he asked about ("would it file to Tuesday or Wednesday?").

**TS-7 `[unit]` Nothing confidently claimable - hold, do not guess.**
An arrival that no rule can place: earlier slots non-claimable, current
slot filled or outside its window.
**Expect**: **held for a human**, never defaulted into a future slot.
Defaulting forward is the forward cascade again.

**TS-8 `[unit]` Assignment must be order-independent.**
Two files land in one batch with close arrival timestamps - a late
supply for an old slot, and an on-time supply for the current one.
Present them to the assigner in both orders.
**Expect**: **identical assignments both ways**, because replay is in
arrival-timestamp order rather than discovery order. Identical
timestamps resolve by a defined tiebreak.
**Breaks as**: the answer depends on whichever file the loop happened to
pick up first - non-determinism nothing would ever flag.

### Arrival classification

**TS-9 `[INJECT]` A genuinely early quarterly supply.**
*Config: quarterly, Feb 2 / May 1 / Aug 3 / Nov 2, early window 14 days.
Feb and May filled. Supply arrives 13 July - 21 days early, inside
August's window.*
**Expect**: assigned **August** by elimination (Feb and May are filled,
August is the next thing owed and its window is open), classified
**early by 21 days**. Note nothing measures how early it is in order to
assign it - earliness is a reported consequence of the assignment.
**Breaks as**: `cycle_start()` only looks backwards, so it resolves to
the 1 May anchor and reports the supply ~12 weeks LATE for a quarter
that was filled months ago.

**TS-10 `[INJECT]` Evening-before daily arrival - two variants.**
*Config: daily, Tuesday's supply due 22:00 MONDAY.*
- **Monday's slot filled** -> the 22:00 arrival fills **Tuesday, on
  time**.
- **Monday's slot unfilled** -> it fills **Monday, late**.
Same arrival instant, two different correct answers, decided by slot
state rather than by a cutoff rule. This is what lets the cutoff live in
`due_at` instead of in code.
**Keith, 2026-09-22**: early and late arrivals must be **flagged in the
activity feed** for humans to check - see "The activity feed" below.

**TS-11 `[unit]` A re-filed supply reclassifies.**
A supply filed to Monday reads late; a human re-files it to Tuesday,
where it was on time.
**Expect**: the verdict **recomputes** - it now reads on time. A supply
reported late only because it was misfiled was never actually late.
**Keith confirmed 2026-09-22 that he means RE-FILING** (moving a supply
between slots), not just resupplies, and that it is in scope for these
sprints - which **closes the open question** in Thread G about whether
re-filing exists as its own operation.

### Delivery and multi-table

**TS-12 `[INJECT]` Five tables load, one is an invalid CSV.**
**Keith, 2026-09-22: "this is a really important one."** The canonical
case, and the one he raised from real operational experience.
Child Protection's August delivery arrives - all six tables. Five load
cleanly. `cp_clients` is an invalid CSV and cannot be loaded at all. The
agency would be asked for a separate resupply of just that one table.
**Expect**:
- The five are staged, QA'd, green, and auto-promoted. Their August
  slots are **filled**, and their own checks are unaffected - they are
  not dragged down.
- `cp_clients` is **red** (a supply that cannot be loaded is a red QA
  finding), rejected, and its August slot stays **unfilled**.
- Every check declaring `depends_on: [cp_clients]` - including "Client
  reference", which is DEFINED on `cp_notifications` - **cannot run**,
  and reads **red with a qualifying chip naming `cp_clients` as the
  blocker**.
- That red lands at **collection** level, since cross-table checks are
  lifted there. `cp_notifications` keeps its own green status and
  carries only an informational pointer: fully verified against its own
  data, unverified against its relationships.

**TS-13 `[INJECT]` Six tables landing seconds apart.**
`cp_clients` 09:00:00, `cp_notifications` 09:00:04, and so on.
**Expect**: **one QA run over the delivery**, with no intermediate state
in which cross-table checks read red. The test asserts the ABSENCE of
flicker.
**Breaks as**: per-table triggering evaluates "Client reference" at
09:00:00 when notifications has not arrived, so it reads red, then green
four seconds later. Transiently true and practically useless - and at 30
datasets, a red appearing on every healthy delivery is how people learn
to ignore red.

**TS-14 `[INJECT]` A later single-table resupply.**
The corrected `cp_clients` arrives on its own, weeks later.
**Expect**: it arrives as **its own delivery** and triggers QA. Its slot
is clients' own August slot - per-table slot sequences mean there is no
"resupply of table X within delivery Y" concept to implement; it is just
clients' August supply, arriving late. The previously blocked
cross-table check now runs. If green, clients promotes and August's slot
fills. `qa_results/` keeps **both** runs - the period's current state is
the latest, its history is all of them.

**TS-15a `[unit]` An UNEXPECTED TABLE - recognised, but not owed.**
A file that MATCHES a dataset's arrival pattern, for a dataset with no
slot in that period.
**Expect**: it does **not** break the delivery or block readiness, which
are defined over EXPECTED tables. Not QA'd, not promoted (no slot).
**Informational** in the activity feed - Keith settled the earlier
red-or-informational question this way, 2026-09-22: it is not a data
quality failure, it is a supplier telling us something changed without
saying so. Unchanged by the 2026-09-24 severity decision below, because
we know exactly what this file is; it is merely surplus.

**TS-15b `[unit]` An UNRECOGNISED ARTEFACT - matches nothing.**
A file matching no dataset's pattern at all. Keith's own broadening,
2026-09-22, "wildly crazy shit": a `test.png`, a garbage filename.
**Expect**: still does not break the delivery, still not QA'd, still not
promoted. **WARNING, not informational** (Keith, 2026-09-24) - because
this is indistinguishable at runtime from a supply we FAILED TO CLAIM,
which is the TS-38 shape below, and a near-miss that reports quietly
produces a false-complete.

**Open, and it is a real tension between two of Keith's own calls.** On
2026-09-22 he settled `test.png` as informational; on 2026-09-24 he
settled unrecognised-matches-nothing as a warning. Both apply to the
same input, because nothing at runtime tells a junk file from a renamed
resupply. A **non-heuristic discriminator does exist** and is worth
deciding before this is built: the contract already declares each
dataset's `format` (`format: csv`), so an unrecognised file whose
extension matches no declared format could stay informational
(`test.png`), while one whose extension DOES match becomes a warning
(`cp_clients_v2.csv`). That separates the two cases on a fact from
config rather than a guess about intent. Not yet decided.

**TS-16 `[unit]` Per-table classification.**
`cp_clients` lands 09:00, `cp_placements` 14:00, one of them late.
**Expect**: each table gets its **own** early/on-time/late verdict. One
late table does not make five punctual ones late - more honest than a
single per-delivery verdict taking the worst.

**TS-17 `[unit]` The transport cannot express a delivery boundary.**
A source that drops six unrelated objects with no common prefix, folder
or session.
**Expect**: an **explicit configuration failure**, never a silent guess
at grouping. The delivery boundary is load-bearing and comes from the
transport, so a feed that cannot express one needs a boundary arranged
as a plumbing step.

### Status and rollup - the false-green family

**TS-18 `[both]` Cross-table check green, candidate rejected for a
different reason.**
The resupplied `cp_clients` arrives. "Client reference" evaluates
**green** against staged clients plus promoted notifications. But
clients is rejected because one of its OWN checks is red.
**Expect**: "Client reference" does **not** keep its green verdict for
August. It reverts to **cannot-run, red**, because clients never entered
the warehouse. The green result stays attached to the rejected SUPPLY as
evidence of what was evaluated.
**Why this one matters most**: it is the case that makes
period-state-from-promoted-supplies-only load-bearing rather than tidy.
Keep the verdict and a check reads green for a period whose data is not
there.

**TS-19 `[unit]` Partial nodata must not roll up green.**
A collection with several green checks and one that could not run.
**Expect**: the collection reads **red**.
**Breaks as**: `worstOf()` is seeded `"green"` and `STATUS_ORDER.nodata`
is -1, so a nodata can never win a reduce - five green plus one nodata
returns green. Red-for-unrun makes this structurally impossible; the
test guards the old path.

**TS-20 `[unit]` The two status implementations must agree.**
`qa_tools/common/dataset_status.py` has no `nodata` in its
`STATUS_ORDER` at all, so a recorded `nodata` falls through
`dashboard_status_of()` to threshold math and returns **green** - no
crash, no warning, silently different from the JS.
**Expect**: Python and JS return the same status for every input,
including ones the Python side does not currently know.
Item 74's exact failure mode, in the module whose own docstring says it
drifted from its JS counterpart once already.

**TS-21 `[unit]` A table with no checks defined.**
Nothing failed to run, because there was nothing to run. `worstOf()`
over an empty list is seeded green, so such a table reads green by
vacuum and would auto-promote with no quality signal behind it at all.
Every other false green found was a real signal being swallowed; this is
the ABSENCE of any signal reading as a good one.

**SETTLED 2026-09-22: CI gate, hard fail, no opt-out.** Keith's call,
and deliberately simpler than the draft it replaced (which proposed an
explicit opt-out declaration, a `nodata`-with-an-"unchecked"-qualifier
render, and the opt-out doubling as a standing promotion decision).
A table in the schedule with zero checks defined **fails
`mothman check`**. The state cannot reach production, so there is no
dashboard question to answer.
**Expect**: `mothman check` fails; the green-by-vacuum path is
unreachable.

**The gate counts ACTIVE checks, not DEFINED ones** - settled
2026-09-22 after the second chaos pass found the same failure reached by
a different door (Thread H). A retired check is still defined, so a
table whose checks have ALL been retired has zero ACTIVE checks and
renders green by vacuum, while a naive gate counting definitions sees
nothing wrong. Keith: "a table with no checks is the same as a table
with no active checks." Worth getting right now because retirement is
gradual - the day a table crosses to zero active checks is nobody's
commit, so nothing prompts a look.

**This also closes the "what happens to a `nodata` supply" open
question**, which was the same question wearing different clothes - a
check-less table's supply IS a nodata supply. With the CI gate, a supply
with no checks at all cannot exist, and every other `nodata` case is
"nothing was owed" (a brand-new dataset with no prior period, a period
before the dataset existed), which never reaches a promotion decision.

**TS-22 `[both]` Freshness caps the headline.**
Child Protection's August delivery: all six tables promoted, every check
green. It is now November and Q4's supply, due 2 November, has not
arrived. Every check is still green - they ran against August data and
passed, and nothing has re-run since - so the quality rollup says green.
But the newest CP data is a full quarter old, and a consumer reading
"green" would conclude CP is current and healthy.
**Expect**: the headline is **worst of (quality, freshness)**. All-green
checks on a dataset whose expected period is unfilled must not read
green. **Keith, 2026-09-22**: the tables read **red, with a "no data"
qualifier** - the same status-plus-chip vocabulary as a check that could
not run.

**Three assertions, keyed to the due date** (Q4 due 2 November):
- as at **1 November** - Q4 not yet due, August is still the latest
  EXPECTED data -> **green**. Nothing is late.
- as at **3 November** - Q4 overdue and unfilled -> **red, "no data"**.
- as at **15 September** - a historical view, Q4 nowhere near due ->
  **green**.

Keith initially said "1st of November, or even the 3rd", then corrected
himself: he had the due date as 1 November, so he meant the day after
and two days after. No disagreement - the boundary is the due date
either way.

**The subtle part, and the real reason it needs a test**: freshness is
measured against **the as-at date being viewed**, never against today.
Implement it against "today" and every historical view goes falsely
stale, which trains people to ignore the indicator. The 15 September
assertion above is the one that catches that.

**"As at <date>" means END OF DAY** - settled with Keith, 2026-09-22,
after noticing the as-of picker is DATE-granular while `due_at` is
INSTANT-granular. So "as at 2 November" against a Q4 due at 2 November
09:00 means the due moment HAS passed -> red. A supply arriving 2
November 14:00 is likewise included in that view. Both read naturally:
"what did we know by the end of that day".

Two things that hang off it:

- **End of day IN THE ASSET'S TIMEZONE**, per the repo-wide timezone
  parameter. "End of day" is meaningless without saying whose day, and
  an end-of-day computed in UTC would be eight hours out - including or
  excluding a whole evening's arrivals. The naive-timestamp hazard
  (TS-31) wearing a different hat.
- **Today's code already behaves this way, but for an accidental
  reason.** `clipDatasetToAsOf()` filters
  `r.run_date <= asOfDateStr` - a STRING date comparison, so a
  same-day arrival is included, which is end-of-day semantics by
  coincidence rather than by design. That comparison has to become a
  real instant comparison once `due_at` carries a time, and the
  behaviour must not change when it does. Worth a test that pins the
  current semantics before the refactor, not after.

### Schedule and config

**TS-23 `[unit]` Exhausted schedule.** A dataset whose authored date
list has run out. **Expect**: the pipeline **hard-fails for that dataset
only**; sibling datasets are unaffected; supplies pile up in staging
(safe, because staging preserves arrival facts and the backlog drains
correctly once dates are added); and the dashboard **still shows the
banner**, computed from config, even though no new results were
produced. A dashboard that stopped updating otherwise looks identical to
one where nothing changed.

**TS-24 `[unit]` Low runway.** **Expect**: a warning when fewer than N
expected supplies remain, measured in **slots** not months - three
months of quarterly runway is one slot, which is already too late. Non-
fatal, so it cannot fail an otherwise-fine build, which is how gates get
disabled.

**TS-25 `[unit]` Config typo yielding zero slots.** `delivery_months:
[Febuary]`. **Expect**: `mothman check` **fails**. A dataset must never
silently reach zero slots - that is the exhausted-schedule state,
reached by accident, on a dataset nobody is watching.

**TS-26 `[unit]` Schedule version change.** A supplier moves from
quarterly to monthly, recorded as a new `effective_from` block.
**Expect**: each period is evaluated against the version **in force at
its own due date**. Periods that were met stay met; history does not
move when a supplier changes.

**TS-27 `[unit]` `not_expected` versus marked-missed.** **Expect**:
`not_expected` yields **no slot** - nothing owed, nothing overdue,
nothing red. A slot marked missed **keeps its slot**, unfilled, counted
as an obligation NOT MET, with a reason. The distinction protects
supplier reliability from becoming whatever people were willing to
excuse after the fact.

### Composition and as-at

**TS-28 `[both]` Rejected Monday, promoted Friday.**
```
Mon 22:00   supply arrives, QA red, rejected. NOT promoted.
Tue-Thu     nothing. Warehouse still holds the previous period's table.
Fri         a human decides it is the best available and promotes it.
```
Ask: as at **Wednesday**, what did the warehouse hold?
**Expect**: the supply is **absent** from the as-at-Wednesday view.
Keith, 2026-09-22: "it hadn't arrived and the human had not yet made the
decision." Filtering is on **promotion**, not arrival.
**Why it needs a test rather than being obvious**: for auto-promoted
supplies, arrival and promotion are minutes apart and the two filters
are indistinguishable. The gap only opens on **human-decided** supplies -
exactly the ones someone asks about a year later. It is also the rule
first written WRONG in this file, where arrival-filtering was described
as "transaction time" when the warehouse's transaction time is
promotion.

**TS-29 `[unit]` Drift with a missing reference period.** The reference
period was expected and is not there. **Expect**: **red** - identical to
a missing table dependency, the dependency simply being temporal rather
than lateral.

**TS-30 `[unit]` Drift on a brand-new dataset.** No prior period exists
because none was ever owed. **Expect**: **`nodata`, not red.** The
owed-versus-not-owed boundary. Without it, every new dataset starts life
red on all its drift checks, which is how people learn to ignore a
signal.

### Timestamps

**TS-31 `[unit]` Naive timestamp.** **Expect**: never silently
interpreted. `pipeline/cadence.py` treats naive values as UTC, so a
naive AWST value is eight hours out - enough on a daily feed to flip
on-time to late or move a supply into the wrong slot. Stored values
carry their offset.

**TS-32 `[unit]` Supplier-provided timestamp.** **Expect**: **ignored**
in favour of our own receipt time. A file's metadata reflects the
supplier's clock, timezone and bugs; staging's whole justification is
that it asserts only facts we can vouch for.

**TS-34 `[INJECT]` One delivery, two files for each of two datasets.**
Keith's own scenario, 2026-09-24. A Child Protection delivery carrying
EIGHT files: the usual six, plus a second `cp_clients` and a second
`cp_placements` - a catch-up drop where two tables arrive for an earlier
period alongside the current six. Nothing in the files says which period
any of them is for, and nothing may read that from them.
**Expect**: `cp_clients` and `cp_placements` are HELD, each reported as
needing action naming every file that matched. No view is built for
either, so they are unqueryable for that run. The other four datasets
are staged, assigned, classified and QA'd normally. Every cross-table
check reading a held table reads RED naming it - which is three real
checks against `cp_clients` alone (`cp_notifications`,
`cp_investigations`, `cp_placements` each carry a referential check on
`cp_client_id`). Neither held dataset's slot is filled, so both go
overdue in the ordinary way.
**Why it is worth injecting rather than unit-testing**: the interesting
part is not the hold, it is that the blast radius is neither zero nor
the whole delivery. Only a rendered dashboard shows whether a reader can
tell "two tables need a human" apart from "three datasets are red", and
those are the same event seen from two ends.

**TS-35 `[unit]` A held supply is never chosen between, even when one
file is obviously newer.**
The same delivery, but one `cp_clients` file is larger and has a later
filesystem mtime than the other.
**Expect**: still held. No rule consults size, mtime, lexical order or
directory position. This asserts that a KNOWN-TEMPTING heuristic stays
unimplemented rather than that the system computes something - label it
as such, the same family as TS-3, so a later session does not "fix" it
by adding the obvious tie-break. `REQ-PIPE-059` records why each such
rule was rejected: every one is a guess dressed as a policy, and the
dropped file is exactly the one a supplier will later say they sent.

**TS-36 `[unit]` One delivery, two collections.**
A drop containing Birth Registrations' file alongside two Child
Protection tables - one folder, two collections.
**Expect**: the delivery is processed NORMALLY. Each file is attributed
to its own dataset and handled on that dataset's terms; nothing is held,
rejected or failed for spanning collections (Keith, 2026-09-24). This
CHANGES BUILT BEHAVIOUR twice - `qa_tools/common/arrivals.py`'s
`classify()` raises today (and because recognition walks the whole tree,
one such drop takes the run down for all 60 deliveries, reproduced
before deciding), and it also returns a SINGLE `collection_id` that
`arrivals_for()` filters on, so single-collection is structural rather
than just a guard.

**Assert the run consequence too, because it is the part that will be
got wrong**: this delivery produces **two runs**, one per collection.
Run ids come from receipt order, which is now global rather than
per-collection (`REQ-PIPE-061`) - so the assertion is that both runs
exist, that each carries only its own collection's files, and that
neither collection's ordering was computed by walking the tree a second
time.

**TS-36b `[unit]` A mixed-collection delivery must not be held.**
The negative case, and it exists for the same reason TS-33b does: the
rejected design (hold it for a human) is the one already written down in
git history, so an implementation that reinstates it looks defensible in
review. Assert explicitly that no hold, no anomaly and no warning is
raised for the spanning itself - an unrecognised artefact inside such a
delivery still warns on its own terms, which is a different thing.

**TS-36c `[unit]` One file, two datasets' patterns - the runtime hold.**
Two arrival patterns configured so that one filename matches both. The
worked example, which is the one to build the fixture from:
`^cp_clients(_part\d+)?\.csv$` and `^cp_.*_part\d+\.csv$` overlap on
exactly `cp_clients_part2.csv` and on nothing else.
**Expect**: that file is HELD, attributed to NEITHER dataset, reported
at no lower than WARNING, and the delivery and run both continue
(Keith, 2026-09-24, `REQ-PIPE-058` criterion 9).

**TS-36d `[unit]` The same collision, caught by the configuration gate.**
The same two patterns, with `cp_clients_part2.csv` present in committed
delivery history.
**Expect**: `mothman check` FAILS, naming both datasets and the example
filename. **And the negative half matters as much**: with that filename
ABSENT from history the gate PASSES, which is the known, accepted limit
of the corpus approach - real regex intersection was rejected on cost
(`REQ-PIPE-058`). A test asserting the gate catches an unwitnessed
collision is asserting the rejected design.

**Do not confuse either with TS-15's split extract.** One dataset
matching two files is legitimate (`REQ-PIPE-058` criterion 11); two
datasets matching one file is always a configuration error. Same code
path, opposite correct behaviour.

**TS-37 `[unit]` A delivery directory with no receipt record.**
Files present under `data/deliveries/<name>/`, nothing at
`data/receipts/<name>.json`.
**Expect**: skipped as in-flight, reported **on every run** as an
informational observation, and every other delivery processed normally.
NOT a hard error - reproduced 2026-09-24 that one such directory makes
`list_deliveries()` raise, taking all 60 with it. NO configured
interval, NO file modification time, NO state counting runs: persistence
shows through repetition. The reason this is the normal case rather than
an edge - under a real transport a delivery has no receipt until our own
BOUNDARY RULE says it is complete, and in S3 events fire per object with
no delivery-is-finished signal, so "files present, no receipt" is the
state of every delivery until the boundary closes.

**TS-38 `[INJECT]` A resupply whose filename no longer matches.**
**Keith's own case, 2026-09-24, and the most dangerous shape in this
register.** A catch-up Child Protection delivery: the current
`cp_clients` and `cp_placements` arrive with filenames that match their
patterns, and the RESUPPLIES of those same two tables arrive with
filenames that do not - a renamed extract, a split part, a different
convention from the upstream system.
**Expect**: the matched files are attributed and processed; the
unmatched ones are reported as unrecognised artefacts at **warning**
level. Critically, the supply is **NOT** silently treated as complete -
the warning is the only thing standing between this and a promoted,
green, HALF supply. Had the resupplies matched, this would instead be
the duplicate-match hold of TS-34, which is louder still.
**Why `[INJECT]`**: the failure is one of ATTENTION, not computation. A
unit test asserts the warning is emitted; only a rendered dashboard
shows whether a person scanning the activity feed would actually notice
it among that run's other events. That is the whole question here.

**TS-39 `[unit]` A split extract, once patterns are regexes.**
`cp_clients.csv` and `cp_clients_part2.csv` in one delivery, with
`cp-clients`' pattern written to match both.
**Expect**: a duplicate match, so the dataset is HELD (TS-34's
machinery), not a silent choice between them. Verified 2026-09-24 that
under today's `keyPattern` reuse this is NOT reachable for Child
Protection - `cp/{delivery_id}/cp_clients.csv` reduces to
`^cp_clients\.csv$`, so `part2` matches nothing and falls out as
unrecognised instead, which is the TS-38 shape. Reachable for Birth
Registrations only because its pattern carries a `{date}` placeholder.
This scenario is what proves the regex change (`REQ-PIPE-058`,
2026-09-24) actually closed the gap.

**TS-40 `[unit]` A run dies mid-load, and the next run must not trust
what it finds.**
Six CP tables staging; the process is killed after three have loaded, or
during the fourth, or during the SIXTH.
**Expect**: every table without a committed load record is treated as
unloaded and replaced, whatever is sitting in the staging schema. The
delivery is not considered processed until every attributed file has a
record.
**The case that decides this one is the LAST table**, and it is why
deriving completeness from the warehouse catalogue was rejected: a crash
during the sixth load leaves six of six tables present with one
truncated, which a catalogue check reads as complete and skips forever.
A truncated table is indistinguishable from a genuinely short supply and
would be QA'd as real data.
**Also assert the ordering**, because it is the thing most likely to be
got backwards and both orders look correct in review: the record is
written only AFTER the load is durable. Kill the process between load
and record, and the table is re-loaded - wasteful and safe. The opposite
order would skip a table that never loaded.

### The mixed-period delivery gate

**TS-33a `[unit]` A delivery whose tables land in DIFFERENT PERIODS.**
A catch-up drop carrying August's `cp_clients` alongside November's
`cp_notifications`. Different tables, so the two-files-match-one-dataset
hold never fires, and each is assigned independently with no ambiguity.
**Expect**: QA **runs**, and **nothing auto-promotes** - a human review
gate. Rare, and most real instances would trip the duplicate-file hold
first, but cheap protection against a shape nobody expects.

**TS-33b `[unit]` A normal delivery must NOT trip that gate.**
Child Protection's ordinary six-table August delivery. All six land in
the SAME period, but in six DIFFERENT slots, because slots are
per-table.
**Expect**: normal auto-promotion on green/amber. The gate does not
fire.

**TS-33b is the important half.** The gate's condition is tables landing
in different **PERIODS**, not different **SLOTS** - and an
implementation keyed on slots passes 33a while failing 33b, blocking
auto-promotion on every healthy multi-table delivery. Without the
negative case the bug ships, because the positive case alone looks like
it works.

### The activity feed

Keith, 2026-09-22, arising from TS-10 and TS-15: the existing
`CHANGELOG_FEED` (built by `qa_tools/common/changelog.py`, currently a
"who QA'd what, when" changelog) **becomes an ACTIVITY FEED** rather
than a changelog. It carries arrival anomalies alongside QA activity:
early and late arrivals, supplies held for a human, arrivals into a
filled slot, unexpected tables and unrecognised artefacts.

- **Basic filtering** on it.
- **Design and colour distinguishing severity** - informational versus
  warning versus more significant events - so a reader can tell a
  routine early arrival from something that needs action.

Note this is the QA-activity feed, NOT `RELEASE_NOTES` (the repo-root
`CHANGELOG.yaml` tracking the PoC's own development), which is a
genuinely different feed and unaffected.

### What this implies for sprint order

**Most of the `[INJECT]` set cannot be generated at all today.** The
generator emits whole deliveries only and never partial; produces ZERO
early supplies (measured 0 early / 240 on time / 112 late,
`plans/running-thoughts.md` #27); and `run_id` still carries dates. So
`REQ-GEN-040` ("the generator can deliver one table at a time") is not
one requirement among many - it gates whether roughly two-thirds of this
register can be exercised against real data at all.

**Moved to sprint 2** (Keith agreed, 2026-09-22) from sprint 6 - it
blocks the injected shapes, and the injected shapes are how he sees any
of this working. Safe to renumber at the time: nothing outside this file
cited a sprint id, and the two internal references point at sprints 8
and 10, which did not move.

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

### Staged data lives IN the warehouse - SETTLED 2026-09-23

**Keith, 2026-09-23, at REQ-PIPE-034's sign-off.** Thread B above says
"everything lands in staging on arrival" without saying where staging
physically IS, and the natural reading of "promotion moves it into a
period schema" is that staging sits somewhere else. It does not.

**Staging is a schema in the warehouse.** His words: data is loaded as
soon as it can be, QA runs on it there, and the only thing not loaded
is a file that cannot be read at all. Consistent with everything
already settled - QA runs before promotion, an unloadable supply is red
- but it had been implicit.

**Three schemas, and two of them DEPART from Keith's operational
system.** Recorded with the departures called out, because "it matches
the real operational database" was a genuine argument for
schema-per-period elsewhere in this design, and a later session could
"correct" these back without knowing they were deliberate.

| Schema | Holds | vs. the operational system |
|---|---|---|
| period schemas, one per period | promoted supplies | unchanged |
| **ONE GLOBAL staging schema** | everything on arrival | **DEPARTS** - today he runs one staging schema PER QUARTER |
| **ONE GLOBAL rejected schema** | supplies a human decided against | **DEPARTS** - today rejected tables just stay in staging |

**Why global staging rather than per-slot.** A supply's slot is not
known when it lands, and that is the whole point of staging - Thread B:
it "asserts only the thing actually known (this landed at this time),
so it can never be wrong". A slot-mirrored staging schema forces the
slot to be named at LOAD time, which is exactly the filing decision
staging exists to defer. Three cases have no slot to name: an early
supply not yet inside its claim window, a supply held for a human
because nothing is confidently claimable, and a mixed-period delivery
whose tables belong to different periods. A mirror would need an
"unassigned" schema alongside it, ending up with global AND mirrors -
worse than either. Keith's own summary on agreeing: "we don't know
where it should go, or indeed we need a human to make a decision."

**Why a rejected schema at all**, given a red supply that was never
promoted already has a home - it stays in staging. The argument is not
correctness, it is that staging otherwise becomes a work queue and a
graveyard at once, and "awaiting a decision" stops being
distinguishable from "decided against six months ago". Keith confirmed
this is a real problem in his own system: once a quarter's supplies are
done, his staging schema holds only rejected things plus some
green-but-superseded ones. His words: "a decision has been made, in
essence" - so it should not be sitting in the queue.

**Rejected is a DECISION state, not a QA verdict.** Red and nobody has
looked at it yet is still STAGED. Rejected means a human decided against
promoting it - which covers both "this was bad" and "a better one came
along", see the four-version scenario below. Reversible, via the
un-decide operation already settled in Thread G.

**Rejected is NOT a label in the promoted schema** - rejected on the
day this was settled, and for a reason already load-bearing elsewhere:
schema-per-period beat the per-run databases precisely because dbt and
Soda have no `run_id`-scoped `WHERE`. They equally have no "and not
rejected". Isolation by schema, not by label. A filter every query must
remember to apply is a false-green generator.

**Why the rejected schema is global rather than mirroring periods.**
Nothing queries rejected data - layout follows what reads it.
Schema-per-period exists so a cross-table check reads one schema;
rejected data is never in such a query by definition. Its intended slot
is a fact in the decision log, and a supply rejected before assignment
may have no slot to name at all.

**The delivery log: the COMMITTED record is the source of truth, and
the warehouse table is written from it** (Keith, 2026-09-23, agreeing).
He had assumed a log of deliveries in the warehouse, which is right -
QA and SQL need to query it there. It cannot be the only copy, for two
independent reasons: the warehouse is gitignored and regenerated, while
arrival history has to survive for years; and the dashboard build may
never touch `data/`, so it could never read that table at all. Same
pattern `qa_tools/*/dataset_stats.py` already uses - anything needing a
live connection is computed once by whoever legitimately has one, and
committed alongside.

**An unloadable file gets NO table.** Keith, directly: there is no
point creating an empty one when the delivery log already records that
something arrived and could not be read. The arrival is a fact; the
table is not.

**Retention is explicitly OUT of scope for the PoC** (Keith,
2026-09-23). Staging and rejected only grow, and that is accepted -
"we'll need that eventually but it's not a priority right now". The
future question he named is not just dropping data but whether QA
history is kept alongside it, kept after it, or dropped with it.
Recorded as a deliberate no rather than an unasked question.

**Keith's real four-version scenario**, worth keeping because it is
what the states have to survive: a supplier sends a broken version,
rejected; a second broken one, rejected; a third that is "not perfect,
but we do need to get data through" - deliberately NOT rejected, kept
while they are asked for one more; then a fourth that is green. Two
versions are in staging at once until the fourth is promoted. Note what
the third one is: a human HAS looked and HAS decided, and the decision
was neither promote nor reject. That is not the same state as "nobody
has looked".

**There is no SUPERSEDED state, and the reason is worth keeping**
(Keith, 2026-09-23, correcting this session). Reading the scenario
above, it looks as though the third version is orphaned once the fourth
is promoted: not rejected, since nothing was decided against it, but
left in staging, which is the dumping-ground problem returning by the
back door. A fourth terminal state was proposed to close it.

It is not needed, because the premise is wrong. **A human always makes
the call on the third version.** Keith's own account: once the fourth
arrives, either it is green and auto-promotes, at which point someone
goes and rejects the third - or the fourth is rejected and the third is
promoted instead. Staging drains because people drain it, not because
of an automatic rule, and the queue is small enough for that to work.

So **REJECTED means "a human decided against promoting this", not "this
was bad"**. That is broader than it first reads, and deliberately: a
perfectly good supply that simply lost to a better one is rejected, and
nothing is being mislabelled. The decision log carries the actual
reason.

Also rejected, and recorded so it is not re-proposed: **promoting the
loser into the period schema as a non-current version.** It is tempting
because a period schema already holds a supply plus its resupplies, so
it needs no new concept. It is wrong because promotion is a DECISION -
for the quarterly asset a human's decision - and this would put data
into the promoted schema that nobody approved, to avoid modelling a
state that does not exist.

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
   on the arrivals. **SETTLED 2026-09-22** (Thread K): promotion and
   demotion are recorded as timestamped events in the decision log;
   the live dashboard defaults to AS-CORRECTED; and "the view as it was
   published then" is the SNAPSHOT archive rather than a reconstruction.
   Only one residual remains - whether to build a reconstruction path at
   all, given snapshots already answer that question.
2. ~~**What happens to a `nodata` supply.**~~ **CLOSED 2026-09-22.**
   It was the same question as TS-21 - a check-less table's supply IS a
   nodata supply - and the zero-ACTIVE-checks CI gate makes the state
   unreachable. Every remaining `nodata` case is "nothing was owed",
   which never reaches a promotion decision.

### The DELIVERY is the arrival unit, and QA triggers on it

Keith, 2026-09-22. A delivery arrives, is loaded into staging as one
package, and QA triggers on that delivery. Replaces a first attempt the
same day that defined readiness over EXPECTED tables and needed a
clock-driven sweep to resolve ones that never showed - Keith's own call
("would rather not add a clock driven trigger"), and it turns out to
remove the clock from the model entirely.

**What breaks without a delivery concept.** Six CP tables land seconds
apart - `cp_clients` 09:00:00, `cp_notifications` 09:00:04. Under
per-table triggering, clients arrives, QA runs, "Client reference"
depends on notifications whose slot is still unfilled, so it reads RED.
Four seconds later notifications arrives and it reads green. The check
flickers red on every healthy delivery. The model is not LYING at
09:00:00 - notifications genuinely had not arrived - it is transiently
true and practically useless, and at 30 datasets a red appearing on
every normal delivery is how people learn to ignore red.

> **A delivery is loaded into staging as one package, and QA runs once
> over it.** A table that failed to load simply is not in it - its slot
> stays unfilled and dependent checks are red DURABLY and correctly,
> rather than transiently.

Not atomic in the roll-back sense: the five-tables-land-one-fails case
requires the five to be staged and QA'd, so a failed sixth does not
refuse the delivery.

**Why this is not the supplier-declared manifest already rejected.** The
distinction is sharp and worth keeping sharp. What was rejected is a
supplier DECLARING which period their data is for - a judgment we would
have to trust and cannot enforce across a varied supplier base. A
delivery is an OBSERVED TRANSPORT UNIT: one folder drop, one S3 prefix,
one SFTP session. A physical fact about how the data landed, which we
can see for ourselves. Nobody is asserting anything; we are noticing
what arrived together.

#### What this removes

1. **No clock-driven trigger anywhere.** The earlier attempt needed a
   periodic "have any due times passed?" sweep, to resolve an expected
   table that never showed. Under delivery-triggering there is nothing
   to resolve: the delivery arrived with five tables, QA ran on it, and
   the sixth table's slot is simply unfilled. If it turns up later it
   arrives as its own delivery and triggers its own QA.

2. **No timeout on the "table never shows" path.** That whole mechanism
   existed only because readiness had been defined over EXPECTED tables
   rather than over what actually arrived together.

3. **Overdue needs no trigger either** - a correction to the earlier
   claim that it did. **Overdue is a computed property, not an event**:
   "which slots are past due and unfilled" is a query over the schedule
   plus slot state, evaluated whenever the dashboard is built or read.
   The same pattern already settled for the exhausted-schedule banner,
   which the dashboard computes from config rather than being told
   about.

#### What it costs, and what is still open

**The delivery boundary becomes load-bearing, and it comes from the
transport.** A source whose transport cannot express one - six unrelated
S3 PUTs with no common prefix - puts us back to guessing. So the design
must state what constitutes a delivery PER SOURCE, and a source that
cannot express a boundary needs one arranged: a folder convention, a
trigger file, a batch endpoint. That is an operational transport
arrangement rather than asking a supplier to classify their data - still
a different thing from the rejected manifest - but it is a real
requirement on how each feed is plumbed, and should be explicit rather
than assumed.

Also carried over from working this through, and unchanged by the
delivery model:

- **"Failed to load" is a check result, not a separate concept.** An
  invalid CSV, a missing file, zero bytes, a bad encoding, a schema that
  does not match - all are red QA findings on that table (settled
  earlier: a supply that cannot be loaded is red). No separate taxonomy
  of failure is needed.
- **An UNEXPECTED table is a finding, not a delivery problem.** A table
  the schedule does not list for that period must not break the
  delivery, but receiving something nobody asked for usually means a
  supplier changed their extract without telling anyone - exactly what
  this tool should catch. **Settled 2026-09-22: INFORMATIONAL**, in
  the activity feed - it is not a data quality failure.
- **Re-QA is ordinary, and history keeps both runs.** August QA'd with
  five tables; November's resupply arrives as its own delivery and QA
  runs afresh. Each run's results attach to the supplies it evaluated,
  the period's CURRENT state is the latest, and `qa_results/` keeps
  every run - the whole point of it being permanent.

**Re-read against this, 2026-09-22, rather than assumed** - both items
that were flagged here are now done. `REQ-PIPE-036` was REVISED: its
intent did survive (CP's QA stays independent of BDM's) but its title
and every criterion that named a table as the trigger now name a
delivery, and the rejected clock trigger is recorded as a decision
rather than simply deleted. The arrival-triggers-QA text in Thread I
was re-read and already carries the refinement explicitly - it states
that the trigger is a DELIVERY rather than a single table's arrival and
points here for why, so the file holds one version of the rule, not
two. Checked deliberately rather than assumed, because carrying two
versions of a rule in one file is exactly the mistake made with
`nodata` earlier the same day.

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

Both authoring styles produce the same thing - a sequence of PERIODS,
each carrying a date. Everything downstream consumes that sequence and
never knows which produced it.

**Corrected 2026-09-22**: this originally said the sequence was
`(period, due_at)` pairs, putting the deadline on the period. It
cannot live there - see "PERIOD and SLOT, defined" below, where the
deadline moves to the slot. Fixed here rather than left to contradict
that section, since carrying two versions of one rule in this file is
the mistake already made once with `nodata`.

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

### PERIOD and SLOT, named - and one sentence corrected

Settled 2026-09-22. **This NAMES what the calendar/`delivery_months`
design above already produced; it does not replace or re-model it.**
Read it that way, because a first draft of this section read as though
a modelling error had been discovered, and that overstates it -
everything in the section above stands untouched.

"Period" was used throughout this file - schemas are keyed on it, the
cannot-run rule is "an unfilled slot FOR THAT PERIOD", effective-dating
says "the schedule version in force at that period's due date" - and it
was never defined anywhere. Keith caught it reading the concept
inventory: we say one schema per period without ever naming period as
a concept.

**This section's own lesson was itself wrong, and is corrected here
rather than deleted, because the correction is the more useful part.**

It used to say the error was only THIS THREAD disagreeing with ITSELF -
its own "what exists" paragraph recording that `expectedTime` is
already per-dataset, four paragraphs above its own sentence putting the
deadline on the period - and that the fix was therefore a phrasing
change to something already true.

**It is not already true.** Found 2026-09-22 by `delivery-architect`,
reading the parser rather than the config: `pipeline/cadence.py`'s
`_sla_properties_to_dict()` is `{i["property"]: i for i in items}`. It
keys on `property` ALONE and DISCARDS `element:` - so Child
Protection's single `expectedTime` block, tagged `element: cp_clients`,
is the expected time for all six of its datasets, and the `element`
discriminator already sitting in the contract is thrown away. CP has
exactly one `expectedTime` block, verified.

So `expectedTime` is per-CONTRACT, which is the same thing as
per-dataset only for Birth Registrations, where a contract holds one
dataset. Moving the deadline to the SLOT is therefore building a
capability that does not exist rather than preserving one that does -
which makes the decision MORE justified, not less, and means the fork
put to Keith was more real than it was presented as.

**Two lessons, and the second is the one that keeps costing.** A
document can contradict itself, so check that first - that part
stands. But *reading config and inferring what the code does with it*
is not verification. The shape of `slaProperties` looks per-dataset
because `element:` is right there on every property. Only the parser
says whether anything reads it, and nothing here had opened the
parser.

**The definitions:**

> A **PERIOD** is a named bucket on the ASSET's calendar - `2026-Q3`,
> or `2026-09-22`. It carries a DATE and nothing else. It is what a
> schema is named after.
>
> A **SLOT** is one `(table, period)` pair that is actually expected -
> created only where that table participates in that period. It carries
> its own `due_at`, its own grace allowance and its own claim window.

One period, many slots. Thread F already said this without naming it:
"the SAME period, but in six DIFFERENT slots".

#### The correction: `(period, due_at)` cannot express what we need

The schedule was specified above as producing a sequence of
`(period, due_at)` pairs, which makes the deadline a property of the
period - one deadline per date. **It cannot be.** `expected_time` lives
in each dataset's own ODCS contract today (`pipeline/cadence.py`'s
`parse_cadence_from_contract` reads `expectedTime` per dataset), so two
datasets landing on the same quarterly date can be due at different
times, and at ~30 datasets across different teams and source systems
they plainly will be.

**Keith's call, 2026-09-22: per-dataset expected times are "a definite
need"**, so the deadline moves to the SLOT. Recorded with a caveat
about how it was put to him: the alternative - one deadline per period,
every participant sharing it - was offered as a genuine fork, and it
was not one. Choosing it would have meant deleting working config and
removing a capability that already ships. He should have been shown the
contradiction and told which side loses, rather than asked to pick.
Same outcome, but the fork was far more lopsided than it was presented
as, and a future session should not read this as a close call that
could have gone the other way.

**The case that decides it.** Three slots in `2026-Q3` (date 1 July):
`births` due 09:00, `cp_clients` due 09:00, `cp_placements` due 17:00.
Births arrives 1 July at 16:00. With the deadline on the PERIOD - one
value for the day, say 17:00 - Births reads ON TIME. With the deadline
on the SLOT, it is due 09:00 plus 120 minutes of grace, so it reads
LATE by five hours. Same arrival, opposite verdict, and the wrong one
is a FALSE GREEN, which is the direction that matters.

#### Config sketch

**This EXTENDS the calendar/`delivery_months` config settled above - it
does not replace it.** A first draft of this section invented a
parallel `periods:`/`participatesIn:` shape and had to be corrected the
same day: `delivery_months` already exists, already does exactly this
job, and already carries its own reasoned naming decision ("it names
when a supply ARRIVES, not the period it covers"). Two config sketches
disagreeing inside one thread is precisely the failure this file keeps
having, so only the genuinely new parts are shown here.

What is new is that each authored date now carries a PERIOD NAME, so
the thing a schema is named after is config rather than derived:

```yaml
# asset - as settled above, plus a period name per date
calendar:
  - effective_from: 2026-01-01
    dates:
      - { period: 2026-Q1, date: 2026-02-02 }
      - { period: 2026-Q2, date: 2026-05-01 }
      - { period: 2026-Q3, date: 2026-08-03 }
      - { period: 2026-Q4, date: 2026-11-02 }
```

And that the per-dataset SLOT properties sit alongside
`delivery_months` in that dataset's own contract, where
`expectedTime`/`latency` already live today:

```yaml
delivery_months: [February, August]   # unchanged, as settled above
slaProperties:
  - property: expectedTime
    value: "09:00"            # exists today, but see the correction
                              # above: cadence.py discards `element:`,
                              # so CP's six datasets share one value.
                              # Honouring `element:` is real work in
                              # this sprint, not a given.
  - property: latency
    value: 120                # minutes of grace before "late"
  - property: claimWindow
    value: 3                  # days before due_at that this slot opens
```

Slots are then DERIVED - the calendar crossed with each dataset's
`delivery_months` - never authored.

#### Which concept each consumer actually needs

Both are load-bearing; neither is a wrapper for the other:
- **Schema naming** - period only.
- **Overdue** - slot. "Which slots have `due_at` in the past and are
  unfilled."
- **Claim window and slot assignment** - slot.
- **Early/onTime/late** - slot. This is what gives Thread F's
  per-table classification something to compare against.
- **The cannot-run rule** - BOTH. "Any table this check spans has an
  unfilled slot for that period" needs the period to group by and the
  slot to hold the state.

#### Consequence for the dashboard, found while sketching this

`pipeline/cadence.py`'s `cycle_start()` is deliberately reimplemented
in the dashboard's own JS (`cycleStartDate()`) because the as-of picker
lets a viewer pick any date in the browser and a static site has no
backend to ask. That reimplementation COMPUTES a cycle from a cadence
rule, and it cannot compute an authored date list.

So **the period list has to be embedded into the built dashboard**
alongside the other consts. This does not touch the
CI-never-reads-data rule - a schedule is config, not data - but it is a
real new embed that batch 2 must specify. Easy to discover late, and
the symptom would be an as-of picker silently returning nothing on a
quarterly asset.

#### Deliberately left to the scoper

The exact name of `claimWindow`, and whether the claim window is
genuinely per-dataset or one value per asset. It is drawn per-dataset
above for symmetry, but nothing in the design so far actually requires
that. Also whether the period NAME is authored per date, as sketched,
or derived from the date - authored is drawn here because a delivery
date of 2 February is often for the previous November-January period,
so deriving the name from the date would get it wrong in exactly the
way `delivery_months`' own naming note warns about.

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

**SETTLED 2026-09-21** - the fix below was agreed, along with two
corrections found while explaining it. The "not yet settled" note that
stood here was stale.

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

**Re-filing, and demotion's trap.** Raised 2026-09-21; **re-filing
was confirmed IN SCOPE as its own atomic operation 2026-09-22** (see
TS-11), so the question below is settled except where noted:
- Promote and demote are both already asked for in the TUI. Demote
  out of Q2, promote into Q3, and a supply has been re-filed without
  anyone designing re-filing. Settled: re-filing is atomic, not that
  composition - one decision-log entry with a from-slot, a to-slot and
  a reason, rather than two a later reader must correlate.
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

  **The question it exposed - is "un-decide" an operation we want? -
  is SETTLED 2026-09-22: YES.** Keith's own words: "I think undecide is
  an operation. Undecide, that is." Demote-to-staging means "put this
  back in the queue for someone to look at again", which is genuinely
  different from rejecting it, and it is worth having.

  **So the stickiness rule above is REQUIRED, not optional.** That is
  the direct consequence: the trap it guards against (a human demotes
  a green supply, the next run auto-promotes it straight back) is only
  reachable because demote-to-staging exists. Had the answer been NO,
  demote would have gone to rejected only, rejected is inherently
  sticky, and no rule would have been needed at all. It is not, so the
  rule is load-bearing.

  **Staging therefore holds supplies in two distinguishable
  situations**: never decided, and decided-then-undecided. They look
  the same in the table and are not the same to an operator - the
  second has a decision-log history saying who looked and why they put
  it back. The queue view needs to show that, or un-decide silently
  loses the very information it exists to capture.
- **Re-filing does NOT go through un-decide.** It would be natural to
  assume it does - demote to staging, then promote into the other
  period, no third operation needed - and that was the shape proposed
  here before either question was settled. It was rejected (Thread B):
  re-file is an ATOMIC move between periods, one log entry with a
  from-slot, a to-slot and one reason, so that "why is this supply in
  Q3?" has a single answer rather than two entries a later reader must
  correlate. Un-decide and re-file are different acts for different
  reasons; sharing a mechanism would cost the log its legibility for
  no saving worth having.

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
settled that a multi-table check should signal when a table it spans is
missing - but there was no fact to test that against until slots became
per-table. It is now a crisp condition:

> A multi-table check CANNOT RUN for a period if ANY table it spans has
> an unfilled slot for that period.

**What that renders as is RED with a qualifying chip, not `nodata`** -
see Thread I, which supersedes the `nodata` wording this section
originally carried. Corrected 2026-09-22 when Keith asked how the
five-tables-land-one-fails case works and quoted the old wording back,
which is how the contradiction surfaced: Thread I already said red, and
recorded that it was written as a replacement "so the file does not hold
two contradictory designs" - while this section still said `nodata`.

The distinction matters most in exactly this scenario. Five green tables
plus one `nodata` check rolls up GREEN, because `worstOf()` is seeded
`"green"` and `STATUS_ORDER.nodata` is -1, so a `nodata` can never win.
Red wins by construction. The case that prompted the rule is the case
the old wording would have failed.

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
re-file the from-slot and the to-slot), **why** (free text).

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

### Operator identity, and the write path - SETTLED 2026-09-22

`qa_tools/common/git_identity.py`'s `get_run_by()` reads the local
`git config user.email`, which is fine for a developer running the
pipeline and means nothing for an operator in a deployed environment.

- **The decision log MUST REFUSE to record a decision with no
  identity.** Never "unknown", never a default. `get_run_by()` already
  hard-errors rather than falling back to a placeholder; that discipline
  extends here. An audit trail with anonymous entries is worse than
  none, because it looks complete.
- **The actor distinguishes person from automation**, since
  auto-promotions go in the same log:
  `actor: { kind: human | rule, id: <email | principal | rule name> }`.

**The write path is GITHUB ISSUES** (Keith, 2026-09-22), from a
principle he stated as standing: **the dashboard is READ-ONLY, so
anything requiring a write goes through GitHub Issues** and is fed back
in.

**This is not new architecture - it already exists, built for this exact
reason.** `qa_tools/common/ticket_sync.py`'s own docstring records it:
one real `qa-ticket` issue per real dataset, and it was "extended to
amber too (2026-09-18, `plans/running-thoughts.md` #6, 'read-only
tension: accepting/rejecting amber supplies') once a real accept
mechanism needed somewhere to write a decision - a dataset that's only
ever been amber, never red, had no real ticket to comment `/accept` on
until this." Promote, reject, demote and re-file are the same shape of
write, landing on machinery that exists.

Two things this settles for free:
- **Identity.** GitHub authenticates the comment author, so the actor is
  known without inventing an SSO story for the separated environments.
- **Structure.** Issue forms give structured input, so a decision
  carries its supply id, action and reason rather than being free prose
  a workflow has to parse hopefully.

**Issues are the write CHANNEL, not the SYSTEM OF RECORD.** Issues can
be edited and deleted. So the pipeline reads the issue and writes an
immutable entry into the committed decision log - the issue is the
INPUT, the committed log is the RECORD. Treat issues as the store and
someone editing one silently rewrites history, which is the thing
append-only exists to prevent.

**Not PoC-only** - Keith confirmed 2026-09-22 that GitHub will exist in
the real separated environments too. A draft here speculated the
mechanism might be PoC-only with production using whatever the platform
provides; that speculation was wrong and is corrected rather than left
to mislead. Both the principle and the mechanism carry through.

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

### Second chaos pass - six more, 2026-09-22

Run against the model as it stood after the delivery, decision-log,
GitHub-issues, end-of-day-as-of and CI-gate decisions. All six reviewed
with Keith the same day.

**1. Retiring the last check on a table reaches TS-21 by a different
door - VERIFIED against real code, not reasoned.** Both implementations
filter retired checks BEFORE the rollup - the template's
`worstOf(c.checks.filter(ck=>!ck.retired).map(checkStatus))` and
`dataset_status.py`'s `if ck.get("retired_as_of"): continue`. So a table
whose checks have all been retired yields an empty filtered list,
`worstOf([])` seeded `"green"`, and renders **green by vacuum**.
**Settled**: the CI gate counts ACTIVE checks, not DEFINED ones (Keith:
"a table with no checks is the same as a table with no active checks").
A retired check is still defined, so a gate counting definitions sees
nothing wrong. Retirement is gradual, so the day a table crosses zero is
nobody's commit and nothing prompts a look.

**2. Two conflicting decisions on the same supply - DEFERRED BY
DECISION.** An operator comments `/promote`; a colleague comments
`/reject` ninety seconds later. The append-only log records BOTH, which
is correct - that is the audit trail working - but the STATE can only be
one, and nothing says which wins. The asynchronous write path makes it
likelier rather than rarer: comment -> workflow -> pipeline -> rebuild
takes minutes, during which the dashboard still shows the old state, so
**an operator who thinks their comment did not land will comment again**.
Duplicate and conflicting decisions are the expected case, not the
exotic one.
**SETTLED 2026-09-22** (Keith, after first deferring it): **record
both, LAST WINS, and both operators get feedback via the GitHub ticket
being updated with the outcome of the action.**

**On the race condition he raised** - "I'm also not sure how you would
solve like a race condition." The ordering half is free: GitHub
serialises comment creation and stamps each with a `created_at`, so
"last" is well defined without us doing anything. The real race is in
PROCESSING - two workflow runs firing concurrently, both reading the
pre-decision state, both writing.

So the fix is not ordering the comments, it is **serialising their
APPLICATION**: process decisions in comment-timestamp order, one at a
time per supply. Which is the same serialisation constraint already
named for QA and promotion in Thread I - one discipline, not two.

**Two concrete details that would silently drop decisions.**

**(a) `cancel-in-progress: false` - necessary, not sufficient.** GitHub
Actions concurrency groups are the obvious mechanism, and this repo
already uses them - we watched `test.yml` runs get CANCELLED by
concurrency on 2026-09-22 when pushes landed in quick succession.
Cancelling is exactly wrong here: a cancelled run is a LOST DECISION.
So the decision workflow queues rather than cancels, the opposite of
what the test workflow wants.

**But that only holds for TWO.** Keith asked directly whether GitHub
queues runs for us - "the first one will run and the second one will not
start running until the first one is done, is that right?" Yes for two.
**GitHub holds only ONE pending run per concurrency group**, so with A
running, B pending and C arriving, B is cancelled and replaced by C -
three rapid decisions silently lose the middle one, which is the exact
failure this was meant to prevent.

**FACT-CHECKED 2026-09-22** at Keith's request, against GitHub's own
docs source (`github/docs`, `content/actions/concepts/workflows-and-
actions/concurrency.md` - `docs.github.com` was blocked by this
session's egress proxy at the time, and has since been allow-listed;
see `CLAUDE.md`). Exact wording:

> "When you limit concurrency, by default only one run can be pending in
> a concurrency group - any additional pending runs cancel the previous
> one. If you need runs to execute sequentially without being canceled,
> you can opt in to queuing, which allows multiple runs to wait in line
> and execute in order."

So the claim holds: one pending run, and a third arrival evicts the
second.

**The opt-in queueing mode is DELIBERATELY NOT USED** - Keith's own
call, 2026-09-22, on being shown it: "I'd rather not rely upon things
that are gated behind different licenses. Let's just go for the simple
solution that you had before." It is gated behind a feature flag whose
own version data lists github.com and Enterprise Cloud but not
Enterprise Server, so whether it exists at all depends on which edition
the real separated environments run - exactly the kind of dependency
this design should not acquire for a guarantee it can get unconditionally.
It is also capped, with runs beyond the cap rejected outright, which is
a lost decision again at a higher threshold.

So the answer is not "queue harder". It is (b) below: draining the
backlog works on any edition, at any volume, and survives a run failing
for reasons that have nothing to do with concurrency.

**(b) The real fix, which makes (a) moot either way: EACH RUN DRAINS
THE BACKLOG.** The workflow reads ALL unprocessed decisions since a
recorded marker, applies them in comment-timestamp order, and advances
the marker - rather than handling only the event that triggered it.
Idempotent and drop-safe: a cancelled run costs nothing, because the
next run picks up everything outstanding including whatever the
cancelled one would have done. The design then does not depend on the
platform queueing one, ten, or none.

**3. The same dataset twice in one delivery.** A supplier drops
`cp_clients.csv` and `cp_clients_v2.csv` in the same folder. A supply is
one table VERSION, so a delivery containing two versions of one table is
ill-formed, and "whichever the loop saw last" is what you get by
default.
**Settled**: **hold for a human.** Keith ties this to the
not-yet-designed filename-to-dataset mapping - his instinct is a
**regular expression per dataset**, which both files would match. So the
rule is: **two files in one delivery matching one dataset's pattern ->
hold for a human**, with a TUI affordance to run QA and decide which
slot each belongs to.

**4. A delivery spanning two periods - MOSTLY COLLAPSES INTO #3, plus a
backstop.** A catch-up drop containing both August's and November's
`cp_clients` is NOT a separate mechanism: nothing ever reads a declared
period, assignment is purely arrival plus slot state, so two
`cp_clients` files in one delivery is exactly #3's "two files match one
dataset" hold.

The residual case is a delivery carrying August's `cp_clients` alongside
November's `cp_notifications` - different tables, so #3 never fires, and
each is assigned independently with no ambiguity. Keith, 2026-09-22:
"that's a bit of a weird shape, and it would be weird to get only August
clients, not also August and November, but just in case it happens."
**Settled**: a **human review gate** - such a delivery **runs QA but
never auto-promotes**. A cheap extra layer for a rare shape, and most
real instances would trip #3 first anyway.

**Wording matters here and would break everything if taken literally**:
the condition is tables landing in **different PERIODS**, not different
SLOTS. Per-table slots mean a normal six-table CP delivery already lands
in six different slots, so a rule phrased on slots trips on every
healthy delivery.

**5. Re-filing into an already-occupied slot.** Re-filing is a human act
that BYPASSES assignment - that is its purpose - so nothing stops a
human re-filing into a slot that already holds a promoted supply.
**Settled** (Keith, 2026-09-22): the filled-slot rule does **not** apply
to a human's deliberate act, since applying it would stop re-filing
doing what it is for. But the TUI **warns and requires explicit
confirmation** when the target slot is filled, and **a re-file into an
occupied slot SUPERSEDES what is there** - stated rather than left to
produce two supplies claiming one slot and an ambiguous "version for
period P" lookup downstream.

**6. Same-day decisions are invisible to the as-of picker.** With as-of
meaning end of day, a supply promoted 14:00 and demoted 22:00 the same
day shows only the final state.
**Settled** (Keith, 2026-09-22): acceptable, because **the snapshots
already cover it** - multiple snapshots exist for that day, so anyone
needing the granular sequence opens the snapshot for a given time. The
decision log is driven by the as-of date at end-of-day granularity like
everything else.
**One dependency worth naming**: that answer holds only because each
decision triggers a publish, and snapshots are automatic per publish
(deduplicated by content hash). If several decisions were ever batched
into one publish, the intermediate states would not be snapshotted and
this answer quietly stops working.

**Adding a TIME element to as-of resolves it, and specifically kills
that dependency** - Keith asked directly, 2026-09-22. With a
time-granular as-of the intermediate state is derivable from the
decision log itself, regardless of publish cadence, so batching stops
mattering. The data already supports it: arrivals carry our own receipt
instant and promotions carry a decision-log timestamp.

Two things it does NOT change:
- **A refinement, not a reversal.** A date-only input still means END OF
  DAY (settled above); time is an optional drill-down, not a new
  default. The common case stays one click.
- **Snapshots still earn their place**, because they answer a DIFFERENT
  question. Time-granular as-of gives "what was true at that moment, as
  we now understand it"; a snapshot gives "what the dashboard actually
  SAID at that moment". As-corrected versus as-published, one layer
  down from the same distinction settled in Thread K.

Not scoped to a sprint - a later refinement rather than sprint-1 work,
since the common case does not need it.

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

  **ARRIVAL triggers QA, never promotion** (Keith's correction,
  2026-09-22, against a claim that promoting the missing table
  "re-triggers" the checks blocked on it). **Refined the same day** - the
  trigger is a DELIVERY, not a single table's arrival; see Thread B's
  "The DELIVERY is the arrival unit" for why per-table QA makes
  cross-table checks flicker red on every healthy delivery. Promotion is an OUTCOME of
  QA, so it cannot also be its input - promotion-as-trigger loops:
  arrival -> QA -> promote -> QA -> promote. `depends_on` determines
  SCOPE, not timing: a resupplied `cp_clients` arriving means QA runs
  every check involving `cp_clients`, including ones defined on other
  tables that merely depend on it.

  Two consequences of QA running BEFORE promotion, worth settling
  rather than discovering:
  - **A supply's promotion decision considers every check its arrival
    caused to run**, not only checks defined on that table. Otherwise a
    resupply that breaks a referential constraint with an already-
    promoted sibling would promote anyway.
  - **Check results are CONDITIONAL on that supply being promoted.**
    A cross-table check only ran because the candidate was staged; if
    the candidate is then rejected, the warehouse never receives it, so
    the verdict describes data that is not there. Results attach to the
    SUPPLY (they are the evidence for its acceptance or rejection);
    the PERIOD's status is computed from promoted supplies only. So a
    rejected candidate leaves its period's dependent checks back at
    cannot-run.

    **This rule is LOAD-BEARING, and was first justified here with
    reasoning that did not reach the case it exists for.** That
    justification said the failure mode is benign because
    "evaluated-and-failed and cannot-run are both red" - true, but it
    only covers the case where the cross-table check itself failed.
    The case it misses, found 2026-09-22 when Keith asked whether this
    broke the model: **the cross-table check evaluates GREEN, and the
    candidate is rejected for a DIFFERENT reason** - one of its own
    checks is red. Keep the evaluated verdict and the check reads green
    for a period whose data never entered the warehouse. A false green,
    in the direction this whole design exists to eliminate. So the
    period-state-from-promoted-supplies-only rule is not tidiness; it
    is what closes that path.

    **The model is not broken by this** - it holds because two similar-
    looking things are genuinely different. A SUPPLY's QA results are
    evidence about that supply, the record of why it was accepted or
    rejected, and a rejected supply keeps them (the reason rejected
    supplies are kept at all). A PERIOD's state is a function of
    promoted supplies only. The staged evaluation is a PRE-FLIGHT: it
    informs the promotion decision and attaches to the supply. Nothing
    needed patching; this falls out of "promotion is what puts data in
    the warehouse".

    **And it does not mean evaluating twice.** Promotion does not re-run
    anything - it promotes the VERDICT alongside the data, in the same
    act. The verdict computed against a staged table is identical to one
    computed against the promoted table, because promotion moves a table
    without changing its contents. The check runs once; promotion makes
    its verdict authoritative for the period. That closes the loop
    Keith flagged when rejecting promotion-as-trigger.

    **Dependency worth naming**: that identity holds only if QA and
    promotion are SERIALISED per period, the way slot assignment
    already is. If another table's arrival could interleave between a
    candidate's QA and its promotion, the staged verdict might no
    longer describe the state being promoted into. The arrival-order
    replay rule covers assignment - this extends the same discipline
    through QA and promotion.
- "Which dataset's history records it" - the COLLECTION's, which
  follows from lifting multi-table checks to collection level.

**The trap that started this, to be written down as INTENDED
behaviour**: a multi-table check REFUSES TO RUN - and so reads red -
even though the composed warehouse holds data for every table it spans.
Carried-forward data from another period makes a cross-table result
meaningless, so this is correct and deliberate - but it reads like a
bug to anyone encountering it cold ("we have the data, why is it not
checking?"), and would be helpfully "fixed" by a later session without
the reasoning attached. (Wording corrected 2026-09-22 - this sentence
predated the red-with-a-chip decision below and still said `nodata`.)

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

**This is not only for the message.** The cannot-run rule itself -
"a check cannot run if any table it spans has an unfilled slot" - is NOT
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

