<!--
GENERATED FILE - do not edit by hand.

Rebuilt by `mothman scenarios map`, and in the same act as the
synthetic history itself, so the two cannot disagree (REQ-GEN-045
criterion 3). Two sources, neither hand-maintained: the test scenario
register in plans/supply-model.md says what each scenario is, and the
generator's own record says where it landed.
-->

# Scenario map

The synthetic history this proof of concept runs on has deliberately
awkward supplies in it - a delivery that arrives in the wrong order, a
file nothing can place, a table that will not load. They are there on
purpose, so the model can be seen working on real pages rather than
only in a green test run.

The dashboard does not label them. A supply that reads red reads red,
the same as a real one would, because that is the point. **This is the
list that says which red was on purpose, and where to look at it.**

Each entry gives coordinates - the dataset, the supplies, the period,
and the date to set the as-of picker to - and never a link. The
generator knows where a scenario landed; it does not know how the
dashboard addresses its pages, and a URL written here would break
silently the next time a route changed.

A scenario marked **not injected** has no generated data behind it.
Either it is a pure unit test with nothing to look at, or it is meant
for injection and has not been placed yet.

**0 of 15 scenarios marked for injection have data behind them today.** 51 scenarios are registered in all; the rest are unit tests with nothing to look at.

## Slot assignment

### TS-1 - Forward cascade

**What it demonstrates.** The 20:00 arrival files as a **resupply of Monday**, because Tuesday's claim window has not opened and no claimable unfilled slot exists. Being a filled slot, it does NOT auto-promote - it holds and warns (TS-4).

**What it would look like if the rule were wrong.** Files as Tuesday's supply; the next file takes Wednesday; every later supply is permanently off by one, each day looking locally plausible.

*Config: daily, due 12:00.*

**not injected - nothing to look at yet**

### TS-2 - Backward cascade

**What it demonstrates.** Files as **Thursday** (on-time-wins-for-the-current-slot). Tuesday and Wednesday stay unfilled, go overdue, and a human marks them missed with a reason.

**What it would look like if the rule were wrong.** Files as Tuesday, two days late; the next as Wednesday; the feed sits permanently two days behind for ever.

*Config: daily, due ~22:00.*

**not injected - nothing to look at yet**

### TS-3 - Arrival just OUTSIDE the claim window - four sub-tests

Reframed from daily during Keith's review: the original example (22:00 due, 21:57 arrival) does not work at all, because the claim window opens BEFORE due_at, so 21:57 sits comfortably inside it and files to Tuesday correctly. The scenario only bites where the gap genuinely exceeds the window.

**not injected - nothing to look at yet**

### TS-3a - Quarterly, prior slot FILLED

**What it demonstrates.** August is not claimable, May and Feb are filled, so no claimable unfilled slot exists -> **resupply of May**. Being a filled slot it does **not auto-promote**; it holds and warns (TS-4).

*Config: quarterly, calendar Feb 2 / May 1 / Aug 3 / Nov 2, early window 14 days. Feb and May filled. Supply arrives 19 July - one day outside August's window, which opens 20 July.*

**not injected - nothing to look at yet**

### TS-3b - Quarterly, prior slot UNFILLED

**What it demonstrates.** May is claimable -> fills **May, ~79 days late**.

**not injected - nothing to look at yet**

### TS-3c - Daily, prior slot FILLED

**What it demonstrates.** Tuesday not claimable, Monday filled -> **resupply of Monday**, no auto-promotion, holds and warns.

*Config: daily evening-before - the supply for day D is due 22:00 on D-1 - early window 4 hours, so Tuesday's window opens 18:00 Monday. Monday's slot filled. Arrival 17:00 Monday, one hour outside.*

**not injected - nothing to look at yet**

### TS-3d - Daily, prior slot UNFILLED

**What it demonstrates.** Monday is claimable -> fills **Monday, 19 hours late**.

**not injected - nothing to look at yet**

### TS-4 - Arrival into an already-filled slot

**What it demonstrates.** Never auto-promotes whatever its status; warns; the message names the context ("a supply arrived for Monday, which was already accepted at 16:00", plus the boundary detail where relevant); and the three genuinely different actions are reachable - **accept** as a correction, **re-file** to another slot, **reject** as a duplicate.

**not injected - nothing to look at yet**

### TS-5 - Monotonic filling - a missed slot must not absorb a later resupply

**What it demonstrates.** Tuesday is **non-claimable**, because a later slot (Wednesday) is filled. That is the whole point of the test.

**What it would look like if the rule were wrong.** Files as Tuesday - recording a missed delivery as MET, using another day's data. Worse than a cascade, because it manufactures a delivery that never happened.

*Config: MUST be stated per variant - Keith's correction.*

*unit test - no generated data, nothing to navigate to*

### TS-6a - Genuine lateness still fills its own slot

**What it demonstrates.** Fills **Monday, late**. Monotonic filling does not block it, because no later slot is filled.

*unit test - no generated data, nothing to navigate to*

### TS-6b - A rolling lag stays correctly recorded

**What it demonstrates.** Each fills its own slot, each classified one day late. Nothing is left permanently unfilled - the feed is simply running a day behind, and says so.

*unit test - no generated data, nothing to navigate to*

### TS-6c - A skipped day becomes missed, and a later backfill cannot be placed

**What it demonstrates.** Wednesday's fills **Wednesday** (on-time-wins). Tuesday now has a filled successor, so it is **non-claimable** -> missed, overdue, red, and a human marks it missed. If Tuesday's supply then turns up afterwards, **nothing is claimable** and it is **held for a human** (TS-7) rather than defaulted forward.

*unit test - no generated data, nothing to navigate to*

### TS-7 - Nothing confidently claimable - hold, do not guess

**What it demonstrates.** **held for a human**, never defaulted into a future slot. Defaulting forward is the forward cascade again.

*unit test - no generated data, nothing to navigate to*

### TS-8 - Assignment must be order-independent

**What it demonstrates.** **identical assignments both ways**, because replay is in arrival-timestamp order rather than discovery order. Identical timestamps resolve by a defined tiebreak.

**What it would look like if the rule were wrong.** The answer depends on whichever file the loop happened to pick up first - non-determinism nothing would ever flag.

*unit test - no generated data, nothing to navigate to*

## Arrival classification

### TS-9 - A genuinely early quarterly supply

**What it demonstrates.** Assigned **August** by elimination (Feb and May are filled, August is the next thing owed and its window is open), classified **early by 21 days**. Note nothing measures how early it is in order to assign it - earliness is a reported consequence of the assignment.

**What it would look like if the rule were wrong.** `cycle_start()` only looks backwards, so it resolves to the 1 May anchor and reports the supply ~12 weeks LATE for a quarter that was filled months ago.

*Config: quarterly, Feb 2 / May 1 / Aug 3 / Nov 2, early window 14 days. Feb and May filled. Supply arrives 13 July - 21 days early, inside August's window.*

**not injected - nothing to look at yet**

### TS-10 - Evening-before daily arrival - two variants

*Config: daily, Tuesday's supply due 22:00 MONDAY.* - **Monday's slot filled** -> the 22:00 arrival fills **Tuesday, on time**. - **Monday's slot unfilled** -> it fills **Monday, late**. Same arrival instant, two different correct answers, decided by slot state rather than by a cutoff rule. This is what lets the cutoff live in `due_at` instead of in code. **Keith, 2026-09-22**: early and late arrivals must be **flagged in the activity feed** for humans to check - see "The activity feed" below.

*Config: daily, Tuesday's supply due 22:00 MONDAY.*

**not injected - nothing to look at yet**

### TS-11 - A re-filed supply reclassifies

**What it demonstrates.** The verdict **recomputes** - it now reads on time. A supply reported late only because it was misfiled was never actually late.

*unit test - no generated data, nothing to navigate to*

## Delivery and multi-table

### TS-12 - Five tables load, one is an invalid CSV

**What it demonstrates.** - The five are staged, QA'd, green, and auto-promoted. Their August slots are **filled**, and their own checks are unaffected - they are not dragged down. - `cp_clients` is **red** (a supply that cannot be loaded is a red QA finding), rejected, and its August slot stays **unfilled**. - Every check declaring `depends_on: [cp_clients]` - including "Client reference", which is DEFINED on `cp_notifications` - **cannot run**, and reads **red with a qualifying chip naming `cp_clients` as the blocker**. - That red lands at **collection** level, since cross-table checks are lifted there. `cp_notifications` keeps its own green status and carries only an informational pointer: fully verified against its own data, unverified against its relationships.

**not injected - nothing to look at yet**

### TS-13 - Six tables landing seconds apart

**What it demonstrates.** **one QA run over the delivery**, with no intermediate state in which cross-table checks read red. The test asserts the ABSENCE of flicker.

**What it would look like if the rule were wrong.** Per-table triggering evaluates "Client reference" at 09:00:00 when notifications has not arrived, so it reads red, then green four seconds later. Transiently true and practically useless - and at 30 datasets, a red appearing on every healthy delivery is how people learn to ignore red.

**not injected - nothing to look at yet**

### TS-14 - A later single-table resupply

**What it demonstrates.** It arrives as **its own delivery** and triggers QA. Its slot is clients' own August slot - per-table slot sequences mean there is no "resupply of table X within delivery Y" concept to implement; it is just clients' August supply, arriving late. The previously blocked cross-table check now runs. If green, clients promotes and August's slot fills. `qa_results/` keeps **both** runs - the period's current state is the latest, its history is all of them.

**not injected - nothing to look at yet**

### TS-15a - An UNEXPECTED TABLE - recognised, but not owed

**What it demonstrates.** It does **not** break the delivery or block readiness, which are defined over EXPECTED tables. Not QA'd, not promoted (no slot).

*unit test - no generated data, nothing to navigate to*

### TS-15b - An UNRECOGNISED ARTEFACT - matches nothing

**What it demonstrates.** Still does not break the delivery, still not QA'd, still not promoted. **WARNING, not informational** (Keith, 2026-09-24) - because this is indistinguishable at runtime from a supply we FAILED TO CLAIM, which is the TS-38 shape below, and a near-miss that reports quietly produces a false-complete.

*unit test - no generated data, nothing to navigate to*

### TS-16 - Per-table classification

**What it demonstrates.** Each table gets its **own** early/on-time/late verdict. One late table does not make five punctual ones late - more honest than a single per-delivery verdict taking the worst.

*unit test - no generated data, nothing to navigate to*

### TS-17 - The transport cannot express a delivery boundary

**What it demonstrates.** An **explicit configuration failure**, never a silent guess at grouping. The delivery boundary is load-bearing and comes from the transport, so a feed that cannot express one needs a boundary arranged as a plumbing step.

*unit test - no generated data, nothing to navigate to*

## Status and rollup - the false-green family

### TS-18 - Cross-table check green, candidate rejected for a different reason

**What it demonstrates.** "Client reference" does **not** keep its green verdict for August. It reverts to **cannot-run, red**, because clients never entered the warehouse. The green result stays attached to the rejected SUPPLY as evidence of what was evaluated.

*unit test - no generated data, nothing to navigate to*

### TS-19 - Partial nodata must not roll up green

**What it demonstrates.** The collection reads **red**.

**What it would look like if the rule were wrong.** `worstOf()` is seeded `"green"` and `STATUS_ORDER.nodata` is -1, so a nodata can never win a reduce - five green plus one nodata returns green. Red-for-unrun makes this structurally impossible; the test guards the old path.

*unit test - no generated data, nothing to navigate to*

### TS-20 - The two status implementations must agree

**What it demonstrates.** Python and JS return the same status for every input, including ones the Python side does not currently know. Item 74's exact failure mode, in the module whose own docstring says it drifted from its JS counterpart once already.

*unit test - no generated data, nothing to navigate to*

### TS-21 - A table with no checks defined

Nothing failed to run, because there was nothing to run. `worstOf()` over an empty list is seeded green, so such a table reads green by vacuum and would auto-promote with no quality signal behind it at all. Every other false green found was a real signal being swallowed; this is the ABSENCE of any signal reading as a good one.

*unit test - no generated data, nothing to navigate to*

### TS-22 - Freshness caps the headline

**What it demonstrates.** The headline is **worst of (quality, freshness)**. All-green checks on a dataset whose expected period is unfilled must not read green. **Keith, 2026-09-22**: the tables read **red, with a "no data" qualifier** - the same status-plus-chip vocabulary as a check that could not run.

*unit test - no generated data, nothing to navigate to*

## Schedule and config

### TS-23 - Exhausted schedule

**What it demonstrates.** The pipeline **hard-fails for that dataset only**; sibling datasets are unaffected; supplies pile up in staging (safe, because staging preserves arrival facts and the backlog drains correctly once dates are added); and the dashboard **still shows the banner**, computed from config, even though no new results were produced. A dashboard that stopped updating otherwise looks identical to one where nothing changed.

*unit test - no generated data, nothing to navigate to*

### TS-24 - Low runway

**What it demonstrates.** A warning when fewer than N expected supplies remain, measured in **slots** not months - three months of quarterly runway is one slot, which is already too late. Non- fatal, so it cannot fail an otherwise-fine build, which is how gates get disabled.

*unit test - no generated data, nothing to navigate to*

### TS-25 - Config typo yielding zero slots

**What it demonstrates.** `mothman check` **fails**. A dataset must never silently reach zero slots - that is the exhausted-schedule state, reached by accident, on a dataset nobody is watching.

*unit test - no generated data, nothing to navigate to*

### TS-26 - Schedule version change

**What it demonstrates.** Each period is evaluated against the version **in force at its own due date**. Periods that were met stay met; history does not move when a supplier changes.

*unit test - no generated data, nothing to navigate to*

### TS-27 - `not_expected` versus marked-missed

**What it demonstrates.** `not_expected` yields **no slot** - nothing owed, nothing overdue, nothing red. A slot marked missed **keeps its slot**, unfilled, counted as an obligation NOT MET, with a reason. The distinction protects supplier reliability from becoming whatever people were willing to excuse after the fact.

*unit test - no generated data, nothing to navigate to*

## Composition and as-at

### TS-28 - Rejected Monday, promoted Friday

**What it demonstrates.** The supply is **absent** from the as-at-Wednesday view. Keith, 2026-09-22: "it hadn't arrived and the human had not yet made the decision." Filtering is on **promotion**, not arrival.

*unit test - no generated data, nothing to navigate to*

### TS-29 - Drift with a missing reference period

**What it demonstrates.** **red** - identical to a missing table dependency, the dependency simply being temporal rather than lateral.

*unit test - no generated data, nothing to navigate to*

### TS-30 - Drift on a brand-new dataset

**What it demonstrates.** **`nodata`, not red.** The owed-versus-not-owed boundary. Without it, every new dataset starts life red on all its drift checks, which is how people learn to ignore a signal.

*unit test - no generated data, nothing to navigate to*

## Timestamps

### TS-31 - Naive timestamp

**What it demonstrates.** Never silently interpreted. `pipeline/cadence.py` treats naive values as UTC, so a naive AWST value is eight hours out - enough on a daily feed to flip on-time to late or move a supply into the wrong slot. Stored values carry their offset.

*unit test - no generated data, nothing to navigate to*

### TS-32 - Supplier-provided timestamp

**What it demonstrates.** **ignored** in favour of our own receipt time. A file's metadata reflects the supplier's clock, timezone and bugs; staging's whole justification is that it asserts only facts we can vouch for.

*unit test - no generated data, nothing to navigate to*

### TS-34 - One delivery, two files for each of two datasets

**What it demonstrates.** `cp_clients` and `cp_placements` are HELD, each reported as needing action naming every file that matched. No view is built for either, so they are unqueryable for that run. The other four datasets are staged, assigned, classified and QA'd normally. Every cross-table check reading a held table reads RED naming it - which is three real checks against `cp_clients` alone (`cp_notifications`, `cp_investigations`, `cp_placements` each carry a referential check on `cp_client_id`). Neither held dataset's slot is filled, so both go overdue in the ordinary way.

**not injected - nothing to look at yet**

### TS-35 - A held supply is never chosen between, even when one file is obviously newer

**What it demonstrates.** Still held. No rule consults size, mtime, lexical order or directory position. This asserts that a KNOWN-TEMPTING heuristic stays unimplemented rather than that the system computes something - label it as such, the same family as TS-3, so a later session does not "fix" it by adding the obvious tie-break. `REQ-PIPE-059` records why each such rule was rejected: every one is a guess dressed as a policy, and the dropped file is exactly the one a supplier will later say they sent.

*unit test - no generated data, nothing to navigate to*

### TS-36 - One delivery, two collections

**What it demonstrates.** The delivery is processed NORMALLY. Each file is attributed to its own dataset and handled on that dataset's terms; nothing is held, rejected or failed for spanning collections (Keith, 2026-09-24). This CHANGES BUILT BEHAVIOUR twice - `qa_tools/common/arrivals.py`'s `classify()` raises today (and because recognition walks the whole tree, one such drop takes the run down for all 60 deliveries, reproduced before deciding), and it also returns a SINGLE `collection_id` that `arrivals_for()` filters on, so single-collection is structural rather than just a guard.

*unit test - no generated data, nothing to navigate to*

### TS-36b - A mixed-collection delivery must not be held

The negative case, and it exists for the same reason TS-33b does: the rejected design (hold it for a human) is the one already written down in git history, so an implementation that reinstates it looks defensible in review. Assert explicitly that no hold, no anomaly and no warning is raised for the spanning itself - an unrecognised artefact inside such a delivery still warns on its own terms, which is a different thing.

*unit test - no generated data, nothing to navigate to*

### TS-36c - One file, two datasets' patterns - the runtime hold

**What it demonstrates.** That file is HELD, attributed to NEITHER dataset, reported at no lower than WARNING, and the delivery and run both continue (Keith, 2026-09-24, `REQ-PIPE-058` criterion 9).

*unit test - no generated data, nothing to navigate to*

### TS-36d - The same collision, caught by the configuration gate

**What it demonstrates.** `mothman check` FAILS, naming both datasets and the example filename. **And the negative half matters as much**: with that filename ABSENT from history the gate PASSES, which is the known, accepted limit of the corpus approach - real regex intersection was rejected on cost (`REQ-PIPE-058`). A test asserting the gate catches an unwitnessed collision is asserting the rejected design.

*unit test - no generated data, nothing to navigate to*

### TS-37 - A delivery directory with no receipt record

**What it demonstrates.** Skipped as in-flight, reported **on every run** as an informational observation, and every other delivery processed normally. NOT a hard error - reproduced 2026-09-24 that one such directory makes `list_deliveries()` raise, taking all 60 with it. NO configured interval, NO file modification time, NO state counting runs: persistence shows through repetition. The reason this is the normal case rather than an edge - under a real transport a delivery has no receipt until our own BOUNDARY RULE says it is complete, and in S3 events fire per object with no delivery-is-finished signal, so "files present, no receipt" is the state of every delivery until the boundary closes.

*unit test - no generated data, nothing to navigate to*

### TS-38 - A resupply whose filename no longer matches

**What it demonstrates.** The matched files are attributed and processed; the unmatched ones are reported as unrecognised artefacts at **warning** level. Critically, the supply is **NOT** silently treated as complete - the warning is the only thing standing between this and a promoted, green, HALF supply. Had the resupplies matched, this would instead be the duplicate-match hold of TS-34, which is louder still.

**not injected - nothing to look at yet**

### TS-39 - A split extract, once patterns are regexes

**What it demonstrates.** A duplicate match, so the dataset is HELD (TS-34's machinery), not a silent choice between them. Verified 2026-09-24 that under today's `keyPattern` reuse this is NOT reachable for Child Protection - `cp/{delivery_id}/cp_clients.csv` reduces to `^cp_clients\.csv$`, so `part2` matches nothing and falls out as unrecognised instead, which is the TS-38 shape. Reachable for Birth Registrations only because its pattern carries a `{date}` placeholder. This scenario is what proves the regex change (`REQ-PIPE-058`, 2026-09-24) actually closed the gap.

*unit test - no generated data, nothing to navigate to*

### TS-40 - A run dies mid-load, and the next run must not trust what it finds

**What it demonstrates.** Every table without a committed load record is treated as unloaded and replaced, whatever is sitting in the staging schema. The delivery is not considered processed until every attributed file has a record.

*unit test - no generated data, nothing to navigate to*

## The mixed-period delivery gate

### TS-33a - A delivery whose tables land in DIFFERENT PERIODS

**What it demonstrates.** QA **runs**, and **nothing auto-promotes** - a human review gate. Rare, and most real instances would trip the duplicate-file hold first, but cheap protection against a shape nobody expects.

*unit test - no generated data, nothing to navigate to*

### TS-33b - A normal delivery must NOT trip that gate

**What it demonstrates.** Normal auto-promotion on green/amber. The gate does not fire.

*unit test - no generated data, nothing to navigate to*
