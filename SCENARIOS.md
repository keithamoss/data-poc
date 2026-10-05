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
and the date to set the In place on picker to - and never a link. The
generator knows where a scenario landed; it does not know how the
dashboard addresses its pages, and a URL written here would break
silently the next time a route changed.

A scenario marked **not injected** has no generated data behind it.
Either it is a pure unit test with nothing to look at, or it is meant
for injection and has not been placed yet.

**8 of 31 scenarios marked for injection have data behind them today.** 67 scenarios are registered in all; the rest are unit tests with nothing to look at.

## Slot assignment

### TS-1 - Forward cascade

**What it demonstrates.** The 20:00 arrival files as a **resupply of Monday**, because Monday is still the OPEN period - Tuesday's claim window has not opened (REQ-PIPE-131). Being a filled slot, it does NOT auto-promote - it holds and warns (TS-4).

**What it would look like if the rule were wrong.** Files as Tuesday's supply; the next file takes Wednesday; every later supply is permanently off by one, each day looking locally plausible.

*Config: daily, due 12:00.*

| Where to look | |
|---|---|
| Dataset | birth-registrations |
| Supplies | `birth_registrations__202609151400000800`, `birth_registrations__202609151600000800`, `birth_registrations__202609152000000800` |
| Period | 2026-09-15 |
| Set the in-place-on date to | 2026-09-15 |

### TS-2 - Backward cascade

**What it demonstrates.** Files as **Thursday**, the period open when it arrived (REQ-PIPE-131). Tuesday and Wednesday closed unfilled when the next day's window opened, read as overdue, and a human marks them not supplied with a reason (REQ-PIPE-132).

**What it would look like if the rule were wrong.** Files as Tuesday, two days late; the next as Wednesday; the feed sits permanently two days behind for ever. *Used to expect* the missed days marked missed under monotonic filling - REQ-PIPE-131 closes a slot by time and REQ-PIPE-132 has a person mark it not supplied.

*Config: daily, due ~22:00.*

| Where to look | |
|---|---|
| Dataset | birth-registrations |
| Supplies | `birth_registrations__202609111400000800` |
| Period | 2026-09-11 |
| Set the in-place-on date to | 2026-09-11 |

### TS-3 - Arrival just OUTSIDE the claim window - four sub-tests

Reframed from daily during Keith's review: the original example (22:00 due, 21:57 arrival) does not work at all, because the claim window opens BEFORE due_at, so 21:57 sits comfortably inside it and files to Tuesday correctly. The scenario only bites where the gap genuinely exceeds the window.

**not injected - nothing to look at yet**

### TS-3a - Quarterly, prior slot FILLED

**What it demonstrates.** August's window has not opened, so May is still the OPEN period (REQ-PIPE-131), and it is filled -> **resupply of May**. Being a filled slot it does **not auto-promote**; it holds and warns (TS-4).

*Config: quarterly, calendar Feb 2 / May 1 / Aug 3 / Nov 2, early window 14 days. Feb and May filled. Supply arrives 19 July - one day outside August's window, which opens 20 July.*

**not injected - nothing to look at yet**

### TS-3b - Quarterly, prior slot UNFILLED

**What it demonstrates.** May is still the open period -> fills **May, ~79 days late**.

**not injected - nothing to look at yet**

### TS-3c - Daily, prior slot FILLED

**What it demonstrates.** Tuesday's window has not opened, so Monday is the open period, and it is filled -> **resupply of Monday**, no auto-promotion, holds and warns.

*Config: daily evening-before - the supply for day D is due 22:00 on D-1 - early window 4 hours, so Tuesday's window opens 18:00 Monday. Monday's slot filled. Arrival 17:00 Monday, one hour outside.*

**not injected - nothing to look at yet**

### TS-3d - Daily, prior slot UNFILLED

**What it demonstrates.** Monday is still the open period -> fills **Monday, 19 hours late**.

**not injected - nothing to look at yet**

### TS-4 - Arrival into an already-filled slot

**What it demonstrates.** Does not auto-promote unless the replacement setting in force permits its status (REQ-PIPE-123 - `never` as shipped, so it waits); where it permits, it replaces the promoted supply, which is superseded, never rejected. Warns; the message names the context ("a supply arrived for Monday, which was already accepted at 16:00", plus the boundary detail where relevant); and the three genuinely different actions are reachable - **accept** as a correction (promoting it supersedes the one in place, REQ-PIPE-128), **re-file** to another slot, **reject** as a duplicate. *Used to expect* "never auto-promotes whatever its status" - REQ-PIPE-123 made that a setting (REQ-GEN-138).

| Where to look | |
|---|---|
| Dataset | birth-registrations |
| Supplies | `birth_registrations__202609151400000800`, `birth_registrations__202609151600000800`, `birth_registrations__202609152000000800` |
| Period | 2026-09-15 |
| Set the in-place-on date to | 2026-09-15 |

### TS-5 - A missed slot must not absorb a later resupply

**What it demonstrates.** Tuesday is **closed** - it closed when Wednesday's claim window opened (REQ-PIPE-131, which replaced REQ-PIPE-063's monotonic filling: closing by time, not by a later slot filling). That is the whole point of the test.

**What it would look like if the rule were wrong.** Files as Tuesday - recording a missed delivery as MET, using another day's data. Worse than a cascade, because it manufactures a delivery that never happened.

*Config: MUST be stated per variant - Keith's correction.*

*unit test - no generated data, nothing to navigate to*

### TS-6a - Genuine lateness still fills its own slot

**What it demonstrates.** Fills **Monday, late**. Monday is still the open period: lateness is allowed WITHIN a period's open interval (REQ-PIPE-131).

*unit test - no generated data, nothing to navigate to*

### TS-6b - A rolling lag stays correctly recorded

**What it demonstrates.** Each fills its own slot, each classified late - each arrives before the next day's window opens, so its own day is still open. Nothing is left permanently unfilled - the feed is running behind, and says so. **A feed running MORE than one window behind** is the deliberate reversal (REQ-PIPE-131, reversing REQ-PIPE-063 criterion 3): it fills the open period, and the days it skipped close unfilled.

*unit test - no generated data, nothing to navigate to*

### TS-6c - A skipped day becomes missed, and a later backfill cannot be placed

**What it demonstrates.** Wednesday's fills **Wednesday**, the open period. Tuesday closed unfilled when Wednesday's window opened -> overdue, and a human marks it not supplied (REQ-PIPE-132). If Tuesday's supply then turns up afterwards it is filed to whichever period is OPEN when it arrives - as a resupply where that period is filled - and a person re-files it into Tuesday (REQ-PIPE-131). It is never filed backward automatically, and never held merely for being late.

*unit test - no generated data, nothing to navigate to*

### TS-7 - No period open - hold, do not guess

**What it demonstrates.** **held for a human**, never defaulted forward or backward. Defaulting forward is the forward cascade again. *Used to expect* a hold whenever the oldest claimable slot was ambiguous - REQ-PIPE-131 holds only when no period is open.

*unit test - no generated data, nothing to navigate to*

### TS-8 - Assignment must be order-independent

**What it demonstrates.** **identical assignments both ways**, because replay is in arrival-timestamp order rather than discovery order. Identical timestamps resolve by a defined tiebreak.

**What it would look like if the rule were wrong.** The answer depends on whichever file the loop happened to pick up first - non-determinism nothing would ever flag.

*unit test - no generated data, nothing to navigate to*

## Arrival classification

### TS-9 - A genuinely early quarterly supply

**What it demonstrates.** Assigned **August**, the period open when it arrived (REQ-PIPE-131), classified **early by 9 days**. Note nothing measures how early it is in order to assign it - earliness is a reported consequence of the assignment.

**What it would look like if the rule were wrong.** `cycle_start()` only looks backwards, so it resolves to the 1 May anchor and reports the supply ~12 weeks LATE for a quarter that was filled months ago.

**not injected - nothing to look at yet**

### TS-10 - Evening-before daily arrival - two variants

*Config: daily, Tuesday's supply due 22:00 MONDAY, claim window 4 hours - so Tuesday's window opens 18:00 Monday, and Monday closes then.* - **Monday's slot filled** -> the 22:00 arrival fills **Tuesday, on time**. - **Monday's slot unfilled** -> it ALSO fills **Tuesday, on time**, and Monday closes with no supply. **Changed 2026-10-04 by REQ-PIPE-131**: this variant used to file Monday, late - slot state decided between two answers. Keith's worked consequence: Monday's file arriving after Tuesday's claim window opened is filed as Tuesday's; Monday closes empty, visibly, and Tuesday's real file then supersedes it (REQ-PIPE-118), replaces it (REQ-PIPE-123), or waits for a person. The cutoff still lives in `due_at` and the claim window, not in code. **Keith, 2026-09-22**: early and late arrivals must be **flagged in the activity feed** for humans to check - see "The activity feed" below.

*Config: daily, Tuesday's supply due 22:00 MONDAY, claim window 4 hours - so Tuesday's window opens 18:00 Monday, and Monday closes then.*

**not injected - nothing to look at yet**

### TS-11 - A re-filed supply reclassifies

**What it demonstrates.** The verdict **recomputes** - it now reads on time. A supply reported late only because it was misfiled was never actually late. The re-filed supply returns to staging under a NEW filing (the old one kept), is checked again as a run of its own, and the gate decides (REQ-PIPE-140, REQ-PIPE-141). *Used to expect* the supply to move between slots and stay promoted - REQ-PIPE-141 made a re-file never fill its target directly.

*unit test - no generated data, nothing to navigate to*

## Delivery and multi-table

### TS-12 - Five tables load, one is an invalid CSV

**What it demonstrates.** - The five are staged, QA'd, green, and auto-promoted. Their August slots are **filled**, and their own checks are unaffected - they are not dragged down. - `cp_clients` is **red** (a supply that cannot be loaded is a red QA finding), rejected, and its August slot stays **unfilled**. - Every check declaring `depends_on: [cp_clients]` - including "Client reference", which is DEFINED on `cp_notifications` - **cannot run**, and reads **red with a qualifying chip naming `cp_clients` as the blocker**. - That red lands at **collection** level, since cross-table checks are lifted there. `cp_notifications` keeps its own green status and carries only an informational pointer: fully verified against its own data, unverified against its relationships.

| Where to look | |
|---|---|
| Dataset | cp-clients |
| Supplies | `cp_clients__202505010900000800` |
| Period | 2025-Q2 |
| Set the in-place-on date to | 2025-05-01 |

### TS-13 - Six tables landing seconds apart

**What it demonstrates.** **one QA run over the delivery**, with no intermediate state in which cross-table checks read red. The test asserts the ABSENCE of flicker.

**What it would look like if the rule were wrong.** Per-table triggering evaluates "Client reference" at 09:00:00 when notifications has not arrived, so it reads red, then green four seconds later. Transiently true and practically useless - and at 30 datasets, a red appearing on every healthy delivery is how people learn to ignore red.

**not injected - nothing to look at yet**

### TS-14 - A later single-table resupply

**What it demonstrates.** It arrives as **its own delivery** and triggers QA. Its slot is clients' own August slot - per-table slot sequences mean there is no "resupply of table X within delivery Y" concept to implement; it is just clients' August supply, arriving late. The previously blocked cross-table check now runs. If green, clients promotes and August's slot fills. The recorded QA history keeps **both** runs - the period's current state is the latest, its history is all of them. Clients arriving also re-evaluates the waiting placements' reading checks and re-gates them (REQ-PIPE-121). *Used to say* `qa_results/` kept both runs - REQ-PIPE-089 moved the history into the database.

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

### TS-27 - `not_expected` versus marked not supplied

**What it demonstrates.** `not_expected` yields **no slot** - nothing owed, nothing overdue, nothing red. A closed slot a person marks **not supplied** (REQ-PIPE-132) **keeps its slot**, unfilled, reading "not supplied (accepted)", counted as an obligation NOT MET, with a reason. The distinction protects supplier reliability from becoming whatever people were willing to excuse after the fact. *Used to say* "marked missed" - REQ-PIPE-132 introduced mark as not supplied, which records the decision.

*unit test - no generated data, nothing to navigate to*

## Composition and as-at

### TS-28 - Rejected Monday, promoted Friday

**What it demonstrates.** The supply is **absent** from the in-place-on-Wednesday view: it was rejected on Monday, so it was withdrawn on every day before Friday (REQ-PIPE-081 criteria 1, 2 and 8 as amended 2026-10-05). *Used to expect* it absent because "filtering is on **promotion**, not arrival" (Keith, 2026-09-22) - the amended criteria show the newest supply promoted OR awaiting, and a supply leaves the view only when withdrawn, so the answer stands for a different reason.

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

| Where to look | |
|---|---|
| Dataset | cp-clients |
| Supplies | `cp_clients__202602010900000800` |
| Period | 2026-Q1 |
| Set the in-place-on date to | 2026-02-01 |

### TS-39 - A split extract, once patterns are regexes

**What it demonstrates.** A duplicate match, so the dataset is HELD (TS-34's machinery), not a silent choice between them. Verified 2026-09-24 that under today's `keyPattern` reuse this is NOT reachable for Child Protection - `cp/{delivery_id}/cp_clients.csv` reduces to `^cp_clients\.csv$`, so `part2` matches nothing and falls out as unrecognised instead, which is the TS-38 shape. Reachable for Birth Registrations only because its pattern carries a `{date}` placeholder. This scenario is what proves the regex change (`REQ-PIPE-058`, 2026-09-24) actually closed the gap.

*unit test - no generated data, nothing to navigate to*

### TS-40 - A run dies mid-load, and the next run must not trust what it finds

**What it demonstrates.** Every table without a committed load record is treated as unloaded and replaced, whatever is sitting in the staging schema. The delivery is not considered processed until every attributed file has a record.

*unit test - no generated data, nothing to navigate to*

## An arrival with no open period

### TS-33a - A supply arriving in a period its dataset does not deliver in

**What it demonstrates.** A June arrival of it is **held for a person** (REQ-PIPE-064) - filed neither backward into February nor forward into August.

*unit test - no generated data, nothing to navigate to*

### TS-33b - Its siblings must NOT be held with it

**What it demonstrates.** Each is filed to its own open period and promoted on the ordinary green-or-amber rule. The hold is on one supply only.

*unit test - no generated data, nothing to navigate to*

## The option A and period-closing batch, planted (REQ-GEN-136, REQ-GEN-137)

### TS-41 - A resend supersedes the failed supply before it

**What it demonstrates.** The resend supersedes the waiting 14:00 supply, which moves to the period's superseded schema, named as superseded by the resend (REQ-PIPE-118).

**What it would look like if the rule were wrong.** Two versions of one table waiting for one day, every reader contested.

*Config: daily, due 14:00 AWST - TS-1's own placement. Settings in force where it lands (2026-09-15): amber setting promote-and-acknowledge, replacement setting never.*

| Where to look | |
|---|---|
| Dataset | birth-registrations |
| Supplies | `birth_registrations__202609151400000800`, `birth_registrations__202609151600000800`, `birth_registrations__202609152000000800` |
| Period | 2026-09-15 |
| Set the in-place-on date to | 2026-09-15 |

### TS-42 - A contested pair of one Child Protection table, resolved by a later file

NOT IN THE DATA, and not for want of a build: Child Protection's arrival patterns are exact filenames, so two files in one directory can never both match one table - the same finding TS-34 records. Planting it means widening a pattern, which is Keith's call (REQ-PIPE-118, REQ-PIPE-105 criterion 6).

**not injected - nothing to look at yet**

### TS-43 - An amber supply held under hold

**What it demonstrates.** The amber supply is not promoted; the rule records a promotion-withheld note naming the setting, and the slot reads amber, waiting for a person (REQ-PIPE-122).

**What it would look like if the rule were wrong.** It promotes itself, as it would under promote.

*Config: daily; the amber setting is HOLD from 2026-09-01.*

**not injected - nothing to look at yet**

### TS-44 - An amber supply promoted and awaiting acknowledgement

**What it demonstrates.** Promoted by the rule, recorded with the setting, and shown as awaiting acknowledgement (REQ-PIPE-122).

**What it would look like if the rule were wrong.** Promoted with nothing asked, or held.

*Config: daily; PROMOTE-AND-ACKNOWLEDGE from 2026-09-10.*

**not injected - nothing to look at yet**

### TS-45 - The same, acknowledged by a person

**What it demonstrates.** Beside TS-44's, this one reads acknowledged, by the person, with their reason (REQ-PIPE-122, REQ-GEN-137 criterion 4).

**What it would look like if the rule were wrong.** The acknowledgement refused, or written outside the decision path.

*Config: as TS-44; a scripted acknowledgement three hours after receipt.*

**not injected - nothing to look at yet**

### TS-46 - A green resupply replaces the promoted supply

**What it demonstrates.** The 16:00 supply is promoted by the rule, naming the supply it replaced and the setting; the 14:00 one is superseded, not rejected, and its supply-history row says so (REQ-PIPE-123, REQ-DASH-127).

**What it would look like if the rule were wrong.** The resend waits for a person, as it would under never.

*Config: daily; the replacement setting is GREEN from 2026-09-18 to 2026-09-21.*

**not injected - nothing to look at yet**

### TS-47 - A daily file arriving after the next day's window opened

**What it demonstrates.** It fills the NEXT day, the period open when it arrived; its own day closes with no supply, overdue, and a scripted person marks it not supplied, so it reads "not supplied (accepted)" (REQ-PIPE-131, REQ-PIPE-132, REQ-DASH-133, REQ-GEN-137 criterion 3).

**What it would look like if the rule were wrong.** Filed backward to its own day.

*Config: daily, due 14:00, 4-hour claim window - the next day's window opens at 10:00. Settings in force where it lands (2026-09-07): amber setting hold, replacement setting never.*

| Where to look | |
|---|---|
| Dataset | birth-registrations |
| Supplies | `birth_registrations__202609081100000800` |
| Period | 2026-09-07 |
| Set the in-place-on date to | 2026-09-08 |

### TS-48 - A correction arriving before its partner is promoted

NOT IN THE DATA YET. A single-table correction that goes red on a cross-table check and is promoted when its partner's promotion re-checks it (REQ-PIPE-121) needs the Child Protection generator to place a partner's promotion between two arrivals of one quarter, which its delivery shapes do not yet express.

**not injected - nothing to look at yet**

### TS-49 - A correction still failing after its partner's promotion

NOT IN THE DATA YET, for TS-48's reason. Would produce the decision log's still-failing record (REQ-PIPE-121 criterion 12).

**not injected - nothing to look at yet**

### TS-50 - A reader re-checked against the newer version

NOT IN THE DATA YET, for TS-48's reason (REQ-PIPE-118, REQ-PIPE-123 with a cross-table reader).

**not injected - nothing to look at yet**

### TS-51 - A promoted supply turned red by a later sibling

NOT IN THE DATA YET. Needs a Child Protection file shape that breaks a promoted sibling's referential check (REQ-DASH-126).

**not injected - nothing to look at yet**

### TS-52 - Case Workers arriving in a period it does not deliver in

NOT INJECTED: the ordinary history already produces it - Case Workers files arrive in every delivery and are held in the quarters it does not take part in (TS-33a, REQ-PIPE-131). An injection would record a placement for what is already there; it waits on the Child Protection injection supporting a placement with no extra arrival.

**not injected - nothing to look at yet**

### TS-53 - Keith's worked un-supersede case

NOT IN THE DATA - FOR KEITH. A good file superseded by a bad later one, the bad one rejected and the good one un-superseded, re-checked and promoted by the gate (REQ-PIPE-120). Under the rules as built a good file is superseded only while WAITING, and a green one waits only behind a filled slot or a hold - in either case the gate does not promote it after the un-supersede without a further decision. What should the planted shape be?

**not injected - nothing to look at yet**

### TS-54 - A period substituted onto an earlier promoted supply

NOT IN THE DATA YET: the script has no field for the period stood on (REQ-PIPE-084, REQ-GEN-137 criterion 5).

**not injected - nothing to look at yet**

### TS-55 - A period whose _manifest lists all three kinds

NOT IN THE DATA YET: needs TS-54's substitution beside an inheritance in one period (REQ-PIPE-130, REQ-GEN-137 criterion 6).

**not injected - nothing to look at yet**

### TS-56 - A supply whose columns arrive in another order

**What it demonstrates.** It loads as usual, because columns are matched by name; its column-order file check WARNS, shown in the dataset's file section, and the dataset's status is unchanged by it (REQ-QAC-096 criteria 12 and 18, REQ-DASH-097 criterion 7, REQ-GEN-044 criterion 16).

**What it would look like if the rule were wrong.** Refused, or the dataset turned amber or red by a warning.

*Config: quarterly, Feb/May/Aug/Nov.*

| Where to look | |
|---|---|
| Dataset | cp-carers |
| Supplies | `cp_carers__202411010900000800` |
| Period | 2024-Q4 |
| Set the in-place-on date to | 2024-11-01 |


<!-- scenario-map-data
{
 "scenarios": [
  {
   "id": "TS-1",
   "mode": "INJECT",
   "title": "Forward cascade",
   "section": "Slot assignment",
   "demonstrates": "The 20:00 arrival files as a **resupply of Monday**, because Monday is still the OPEN period - Tuesday's claim window has not opened (REQ-PIPE-131). Being a filled slot, it does NOT auto-promote - it holds and warns (TS-4).",
   "breaksAs": "Files as Tuesday's supply; the next file takes Wednesday; every later supply is permanently off by one, each day looking locally plausible.",
   "config": "Config: daily, due 12:00.",
   "requirements": [
    "REQ-PIPE-131"
   ],
   "coordinates": {
    "dataset": "birth-registrations",
    "supplies": [
     "birth_registrations__202609151400000800",
     "birth_registrations__202609151600000800",
     "birth_registrations__202609152000000800"
    ],
    "period": "2026-09-15",
    "inPlaceOn": "2026-09-15"
   }
  },
  {
   "id": "TS-2",
   "mode": "INJECT",
   "title": "Backward cascade",
   "section": "Slot assignment",
   "demonstrates": "Files as **Thursday**, the period open when it arrived (REQ-PIPE-131). Tuesday and Wednesday closed unfilled when the next day's window opened, read as overdue, and a human marks them not supplied with a reason (REQ-PIPE-132).",
   "breaksAs": "Files as Tuesday, two days late; the next as Wednesday; the feed sits permanently two days behind for ever. *Used to expect* the missed days marked missed under monotonic filling - REQ-PIPE-131 closes a slot by time and REQ-PIPE-132 has a person mark it not supplied.",
   "config": "Config: daily, due ~22:00.",
   "requirements": [
    "REQ-PIPE-131",
    "REQ-PIPE-132"
   ],
   "coordinates": {
    "dataset": "birth-registrations",
    "supplies": [
     "birth_registrations__202609111400000800"
    ],
    "period": "2026-09-11",
    "inPlaceOn": "2026-09-11"
   }
  },
  {
   "id": "TS-3",
   "mode": "INJECT",
   "title": "Arrival just OUTSIDE the claim window - four sub-tests",
   "section": "Slot assignment",
   "demonstrates": "Reframed from daily during Keith's review: the original example (22:00 due, 21:57 arrival) does not work at all, because the claim window opens BEFORE due_at, so 21:57 sits comfortably inside it and files to Tuesday correctly. The scenario only bites where the gap genuinely exceeds the window.",
   "breaksAs": null,
   "config": null,
   "requirements": [],
   "coordinates": null
  },
  {
   "id": "TS-3a",
   "mode": "INJECT",
   "title": "Quarterly, prior slot FILLED",
   "section": "Slot assignment",
   "demonstrates": "August's window has not opened, so May is still the OPEN period (REQ-PIPE-131), and it is filled -> **resupply of May**. Being a filled slot it does **not auto-promote**; it holds and warns (TS-4).",
   "breaksAs": null,
   "config": "Config: quarterly, calendar Feb 2 / May 1 / Aug 3 / Nov 2, early window 14 days. Feb and May filled. Supply arrives 19 July - one day outside August's window, which opens 20 July.",
   "requirements": [
    "REQ-PIPE-131"
   ],
   "coordinates": null
  },
  {
   "id": "TS-3b",
   "mode": "INJECT",
   "title": "Quarterly, prior slot UNFILLED",
   "section": "Slot assignment",
   "demonstrates": "May is still the open period -> fills **May, ~79 days late**.",
   "breaksAs": null,
   "config": null,
   "requirements": [],
   "coordinates": null
  },
  {
   "id": "TS-3c",
   "mode": "INJECT",
   "title": "Daily, prior slot FILLED",
   "section": "Slot assignment",
   "demonstrates": "Tuesday's window has not opened, so Monday is the open period, and it is filled -> **resupply of Monday**, no auto-promotion, holds and warns.",
   "breaksAs": null,
   "config": "Config: daily evening-before - the supply for day D is due 22:00 on D-1 - early window 4 hours, so Tuesday's window opens 18:00 Monday. Monday's slot filled. Arrival 17:00 Monday, one hour outside.",
   "requirements": [],
   "coordinates": null
  },
  {
   "id": "TS-3d",
   "mode": "INJECT",
   "title": "Daily, prior slot UNFILLED",
   "section": "Slot assignment",
   "demonstrates": "Monday is still the open period -> fills **Monday, 19 hours late**.",
   "breaksAs": null,
   "config": null,
   "requirements": [],
   "coordinates": null
  },
  {
   "id": "TS-4",
   "mode": "INJECT",
   "title": "Arrival into an already-filled slot",
   "section": "Slot assignment",
   "demonstrates": "Does not auto-promote unless the replacement setting in force permits its status (REQ-PIPE-123 - `never` as shipped, so it waits); where it permits, it replaces the promoted supply, which is superseded, never rejected. Warns; the message names the context (\"a supply arrived for Monday, which was already accepted at 16:00\", plus the boundary detail where relevant); and the three genuinely different actions are reachable - **accept** as a correction (promoting it supersedes the one in place, REQ-PIPE-128), **re-file** to another slot, **reject** as a duplicate. *Used to expect* \"never auto-promotes whatever its status\" - REQ-PIPE-123 made that a setting (REQ-GEN-138).",
   "breaksAs": null,
   "config": null,
   "requirements": [
    "REQ-PIPE-123",
    "REQ-PIPE-128",
    "REQ-GEN-138"
   ],
   "coordinates": {
    "dataset": "birth-registrations",
    "supplies": [
     "birth_registrations__202609151400000800",
     "birth_registrations__202609151600000800",
     "birth_registrations__202609152000000800"
    ],
    "period": "2026-09-15",
    "inPlaceOn": "2026-09-15"
   }
  },
  {
   "id": "TS-5",
   "mode": "unit",
   "title": "A missed slot must not absorb a later resupply",
   "section": "Slot assignment",
   "demonstrates": "Tuesday is **closed** - it closed when Wednesday's claim window opened (REQ-PIPE-131, which replaced REQ-PIPE-063's monotonic filling: closing by time, not by a later slot filling). That is the whole point of the test.",
   "breaksAs": "Files as Tuesday - recording a missed delivery as MET, using another day's data. Worse than a cascade, because it manufactures a delivery that never happened.",
   "config": "Config: MUST be stated per variant - Keith's correction.",
   "requirements": [
    "REQ-PIPE-131",
    "REQ-PIPE-063"
   ],
   "coordinates": null
  },
  {
   "id": "TS-6a",
   "mode": "unit",
   "title": "Genuine lateness still fills its own slot",
   "section": "Slot assignment",
   "demonstrates": "Fills **Monday, late**. Monday is still the open period: lateness is allowed WITHIN a period's open interval (REQ-PIPE-131).",
   "breaksAs": null,
   "config": null,
   "requirements": [
    "REQ-PIPE-131"
   ],
   "coordinates": null
  },
  {
   "id": "TS-6b",
   "mode": "unit",
   "title": "A rolling lag stays correctly recorded",
   "section": "Slot assignment",
   "demonstrates": "Each fills its own slot, each classified late - each arrives before the next day's window opens, so its own day is still open. Nothing is left permanently unfilled - the feed is running behind, and says so. **A feed running MORE than one window behind** is the deliberate reversal (REQ-PIPE-131, reversing REQ-PIPE-063 criterion 3): it fills the open period, and the days it skipped close unfilled.",
   "breaksAs": null,
   "config": null,
   "requirements": [
    "REQ-PIPE-131",
    "REQ-PIPE-063"
   ],
   "coordinates": null
  },
  {
   "id": "TS-6c",
   "mode": "unit",
   "title": "A skipped day becomes missed, and a later backfill cannot be placed",
   "section": "Slot assignment",
   "demonstrates": "Wednesday's fills **Wednesday**, the open period. Tuesday closed unfilled when Wednesday's window opened -> overdue, and a human marks it not supplied (REQ-PIPE-132). If Tuesday's supply then turns up afterwards it is filed to whichever period is OPEN when it arrives - as a resupply where that period is filled - and a person re-files it into Tuesday (REQ-PIPE-131). It is never filed backward automatically, and never held merely for being late.",
   "breaksAs": null,
   "config": null,
   "requirements": [
    "REQ-PIPE-132",
    "REQ-PIPE-131"
   ],
   "coordinates": null
  },
  {
   "id": "TS-7",
   "mode": "unit",
   "title": "No period open - hold, do not guess",
   "section": "Slot assignment",
   "demonstrates": "**held for a human**, never defaulted forward or backward. Defaulting forward is the forward cascade again. *Used to expect* a hold whenever the oldest claimable slot was ambiguous - REQ-PIPE-131 holds only when no period is open.",
   "breaksAs": null,
   "config": null,
   "requirements": [
    "REQ-PIPE-131"
   ],
   "coordinates": null
  },
  {
   "id": "TS-8",
   "mode": "unit",
   "title": "Assignment must be order-independent",
   "section": "Slot assignment",
   "demonstrates": "**identical assignments both ways**, because replay is in arrival-timestamp order rather than discovery order. Identical timestamps resolve by a defined tiebreak.",
   "breaksAs": "The answer depends on whichever file the loop happened to pick up first - non-determinism nothing would ever flag.",
   "config": null,
   "requirements": [],
   "coordinates": null
  },
  {
   "id": "TS-9",
   "mode": "INJECT",
   "title": "A genuinely early quarterly supply",
   "section": "Arrival classification",
   "demonstrates": "Assigned **August**, the period open when it arrived (REQ-PIPE-131), classified **early by 9 days**. Note nothing measures how early it is in order to assign it - earliness is a reported consequence of the assignment.",
   "breaksAs": "`cycle_start()` only looks backwards, so it resolves to the 1 May anchor and reports the supply ~12 weeks LATE for a quarter that was filled months ago.",
   "config": null,
   "requirements": [
    "REQ-PIPE-131"
   ],
   "coordinates": null
  },
  {
   "id": "TS-10",
   "mode": "INJECT",
   "title": "Evening-before daily arrival - two variants",
   "section": "Arrival classification",
   "demonstrates": "*Config: daily, Tuesday's supply due 22:00 MONDAY, claim window 4 hours - so Tuesday's window opens 18:00 Monday, and Monday closes then.* - **Monday's slot filled** -> the 22:00 arrival fills **Tuesday, on time**. - **Monday's slot unfilled** -> it ALSO fills **Tuesday, on time**, and Monday closes with no supply. **Changed 2026-10-04 by REQ-PIPE-131**: this variant used to file Monday, late - slot state decided between two answers. Keith's worked consequence: Monday's file arriving after Tuesday's claim window opened is filed as Tuesday's; Monday closes empty, visibly, and Tuesday's real file then supersedes it (REQ-PIPE-118), replaces it (REQ-PIPE-123), or waits for a person. The cutoff still lives in `due_at` and the claim window, not in code. **Keith, 2026-09-22**: early and late arrivals must be **flagged in the activity feed** for humans to check - see \"The activity feed\" below.",
   "breaksAs": null,
   "config": "Config: daily, Tuesday's supply due 22:00 MONDAY, claim window 4 hours - so Tuesday's window opens 18:00 Monday, and Monday closes then.",
   "requirements": [
    "REQ-PIPE-131",
    "REQ-PIPE-118",
    "REQ-PIPE-123"
   ],
   "coordinates": null
  },
  {
   "id": "TS-11",
   "mode": "unit",
   "title": "A re-filed supply reclassifies",
   "section": "Arrival classification",
   "demonstrates": "The verdict **recomputes** - it now reads on time. A supply reported late only because it was misfiled was never actually late. The re-filed supply returns to staging under a NEW filing (the old one kept), is checked again as a run of its own, and the gate decides (REQ-PIPE-140, REQ-PIPE-141). *Used to expect* the supply to move between slots and stay promoted - REQ-PIPE-141 made a re-file never fill its target directly.",
   "breaksAs": null,
   "config": null,
   "requirements": [
    "REQ-PIPE-140",
    "REQ-PIPE-141"
   ],
   "coordinates": null
  },
  {
   "id": "TS-12",
   "mode": "INJECT",
   "title": "Five tables load, one is an invalid CSV",
   "section": "Delivery and multi-table",
   "demonstrates": "- The five are staged, QA'd, green, and auto-promoted. Their August slots are **filled**, and their own checks are unaffected - they are not dragged down. - `cp_clients` is **red** (a supply that cannot be loaded is a red QA finding), rejected, and its August slot stays **unfilled**. - Every check declaring `depends_on: [cp_clients]` - including \"Client reference\", which is DEFINED on `cp_notifications` - **cannot run**, and reads **red with a qualifying chip naming `cp_clients` as the blocker**. - That red lands at **collection** level, since cross-table checks are lifted there. `cp_notifications` keeps its own green status and carries only an informational pointer: fully verified against its own data, unverified against its relationships.",
   "breaksAs": null,
   "config": null,
   "requirements": [
    "REQ-GEN-044",
    "REQ-QAC-096",
    "REQ-DASH-148",
    "REQ-DASH-097"
   ],
   "coordinates": {
    "dataset": "cp-clients",
    "supplies": [
     "cp_clients__202505010900000800"
    ],
    "period": "2025-Q2",
    "inPlaceOn": "2025-05-01"
   }
  },
  {
   "id": "TS-13",
   "mode": "INJECT",
   "title": "Six tables landing seconds apart",
   "section": "Delivery and multi-table",
   "demonstrates": "**one QA run over the delivery**, with no intermediate state in which cross-table checks read red. The test asserts the ABSENCE of flicker.",
   "breaksAs": "Per-table triggering evaluates \"Client reference\" at 09:00:00 when notifications has not arrived, so it reads red, then green four seconds later. Transiently true and practically useless - and at 30 datasets, a red appearing on every healthy delivery is how people learn to ignore red.",
   "config": null,
   "requirements": [],
   "coordinates": null
  },
  {
   "id": "TS-14",
   "mode": "INJECT",
   "title": "A later single-table resupply",
   "section": "Delivery and multi-table",
   "demonstrates": "It arrives as **its own delivery** and triggers QA. Its slot is clients' own August slot - per-table slot sequences mean there is no \"resupply of table X within delivery Y\" concept to implement; it is just clients' August supply, arriving late. The previously blocked cross-table check now runs. If green, clients promotes and August's slot fills. The recorded QA history keeps **both** runs - the period's current state is the latest, its history is all of them. Clients arriving also re-evaluates the waiting placements' reading checks and re-gates them (REQ-PIPE-121). *Used to say* `qa_results/` kept both runs - REQ-PIPE-089 moved the history into the database.",
   "breaksAs": null,
   "config": null,
   "requirements": [
    "REQ-PIPE-121",
    "REQ-PIPE-089"
   ],
   "coordinates": null
  },
  {
   "id": "TS-15a",
   "mode": "unit",
   "title": "An UNEXPECTED TABLE - recognised, but not owed",
   "section": "Delivery and multi-table",
   "demonstrates": "It does **not** break the delivery or block readiness, which are defined over EXPECTED tables. Not QA'd, not promoted (no slot).",
   "breaksAs": null,
   "config": null,
   "requirements": [],
   "coordinates": null
  },
  {
   "id": "TS-15b",
   "mode": "unit",
   "title": "An UNRECOGNISED ARTEFACT - matches nothing",
   "section": "Delivery and multi-table",
   "demonstrates": "Still does not break the delivery, still not QA'd, still not promoted. **WARNING, not informational** (Keith, 2026-09-24) - because this is indistinguishable at runtime from a supply we FAILED TO CLAIM, which is the TS-38 shape below, and a near-miss that reports quietly produces a false-complete.",
   "breaksAs": null,
   "config": null,
   "requirements": [],
   "coordinates": null
  },
  {
   "id": "TS-16",
   "mode": "unit",
   "title": "Per-table classification",
   "section": "Delivery and multi-table",
   "demonstrates": "Each table gets its **own** early/on-time/late verdict. One late table does not make five punctual ones late - more honest than a single per-delivery verdict taking the worst.",
   "breaksAs": null,
   "config": null,
   "requirements": [],
   "coordinates": null
  },
  {
   "id": "TS-17",
   "mode": "unit",
   "title": "The transport cannot express a delivery boundary",
   "section": "Delivery and multi-table",
   "demonstrates": "An **explicit configuration failure**, never a silent guess at grouping. The delivery boundary is load-bearing and comes from the transport, so a feed that cannot express one needs a boundary arranged as a plumbing step.",
   "breaksAs": null,
   "config": null,
   "requirements": [],
   "coordinates": null
  },
  {
   "id": "TS-18",
   "mode": "both",
   "title": "Cross-table check green, candidate rejected for a different reason",
   "section": "Status and rollup - the false-green family",
   "demonstrates": "\"Client reference\" does **not** keep its green verdict for August. It reverts to **cannot-run, red**, because clients never entered the warehouse. The green result stays attached to the rejected SUPPLY as evidence of what was evaluated.",
   "breaksAs": null,
   "config": null,
   "requirements": [],
   "coordinates": null
  },
  {
   "id": "TS-19",
   "mode": "unit",
   "title": "Partial nodata must not roll up green",
   "section": "Status and rollup - the false-green family",
   "demonstrates": "The collection reads **red**.",
   "breaksAs": "`worstOf()` is seeded `\"green\"` and `STATUS_ORDER.nodata` is -1, so a nodata can never win a reduce - five green plus one nodata returns green. Red-for-unrun makes this structurally impossible; the test guards the old path.",
   "config": null,
   "requirements": [],
   "coordinates": null
  },
  {
   "id": "TS-20",
   "mode": "unit",
   "title": "The two status implementations must agree",
   "section": "Status and rollup - the false-green family",
   "demonstrates": "Python and JS return the same status for every input, including ones the Python side does not currently know. Item 74's exact failure mode, in the module whose own docstring says it drifted from its JS counterpart once already.",
   "breaksAs": null,
   "config": null,
   "requirements": [],
   "coordinates": null
  },
  {
   "id": "TS-21",
   "mode": "unit",
   "title": "A table with no checks defined",
   "section": "Status and rollup - the false-green family",
   "demonstrates": "Nothing failed to run, because there was nothing to run. `worstOf()` over an empty list is seeded green, so such a table reads green by vacuum and would auto-promote with no quality signal behind it at all. Every other false green found was a real signal being swallowed; this is the ABSENCE of any signal reading as a good one.",
   "breaksAs": null,
   "config": null,
   "requirements": [],
   "coordinates": null
  },
  {
   "id": "TS-22",
   "mode": "both",
   "title": "Freshness caps the headline",
   "section": "Status and rollup - the false-green family",
   "demonstrates": "The headline is **worst of (quality, freshness)**. All-green checks on a dataset whose expected period is unfilled must not read green. **Keith, 2026-09-22**: the tables read **red, with a \"no data\" qualifier** - the same status-plus-chip vocabulary as a check that could not run.",
   "breaksAs": null,
   "config": null,
   "requirements": [],
   "coordinates": null
  },
  {
   "id": "TS-23",
   "mode": "unit",
   "title": "Exhausted schedule",
   "section": "Schedule and config",
   "demonstrates": "The pipeline **hard-fails for that dataset only**; sibling datasets are unaffected; supplies pile up in staging (safe, because staging preserves arrival facts and the backlog drains correctly once dates are added); and the dashboard **still shows the banner**, computed from config, even though no new results were produced. A dashboard that stopped updating otherwise looks identical to one where nothing changed.",
   "breaksAs": null,
   "config": null,
   "requirements": [],
   "coordinates": null
  },
  {
   "id": "TS-24",
   "mode": "unit",
   "title": "Low runway",
   "section": "Schedule and config",
   "demonstrates": "A warning when fewer than N expected supplies remain, measured in **slots** not months - three months of quarterly runway is one slot, which is already too late. Non- fatal, so it cannot fail an otherwise-fine build, which is how gates get disabled.",
   "breaksAs": null,
   "config": null,
   "requirements": [],
   "coordinates": null
  },
  {
   "id": "TS-25",
   "mode": "unit",
   "title": "Config typo yielding zero slots",
   "section": "Schedule and config",
   "demonstrates": "`mothman check` **fails**. A dataset must never silently reach zero slots - that is the exhausted-schedule state, reached by accident, on a dataset nobody is watching.",
   "breaksAs": null,
   "config": null,
   "requirements": [],
   "coordinates": null
  },
  {
   "id": "TS-26",
   "mode": "unit",
   "title": "Schedule version change",
   "section": "Schedule and config",
   "demonstrates": "Each period is evaluated against the version **in force at its own due date**. Periods that were met stay met; history does not move when a supplier changes.",
   "breaksAs": null,
   "config": null,
   "requirements": [],
   "coordinates": null
  },
  {
   "id": "TS-27",
   "mode": "unit",
   "title": "`not_expected` versus marked not supplied",
   "section": "Schedule and config",
   "demonstrates": "`not_expected` yields **no slot** - nothing owed, nothing overdue, nothing red. A closed slot a person marks **not supplied** (REQ-PIPE-132) **keeps its slot**, unfilled, reading \"not supplied (accepted)\", counted as an obligation NOT MET, with a reason. The distinction protects supplier reliability from becoming whatever people were willing to excuse after the fact. *Used to say* \"marked missed\" - REQ-PIPE-132 introduced mark as not supplied, which records the decision.",
   "breaksAs": null,
   "config": null,
   "requirements": [
    "REQ-PIPE-132"
   ],
   "coordinates": null
  },
  {
   "id": "TS-28",
   "mode": "both",
   "title": "Rejected Monday, promoted Friday",
   "section": "Composition and as-at",
   "demonstrates": "The supply is **absent** from the in-place-on-Wednesday view: it was rejected on Monday, so it was withdrawn on every day before Friday (REQ-PIPE-081 criteria 1, 2 and 8 as amended 2026-10-05). *Used to expect* it absent because \"filtering is on **promotion**, not arrival\" (Keith, 2026-09-22) - the amended criteria show the newest supply promoted OR awaiting, and a supply leaves the view only when withdrawn, so the answer stands for a different reason.",
   "breaksAs": null,
   "config": null,
   "requirements": [
    "REQ-PIPE-081"
   ],
   "coordinates": null
  },
  {
   "id": "TS-29",
   "mode": "unit",
   "title": "Drift with a missing reference period",
   "section": "Composition and as-at",
   "demonstrates": "**red** - identical to a missing table dependency, the dependency simply being temporal rather than lateral.",
   "breaksAs": null,
   "config": null,
   "requirements": [],
   "coordinates": null
  },
  {
   "id": "TS-30",
   "mode": "unit",
   "title": "Drift on a brand-new dataset",
   "section": "Composition and as-at",
   "demonstrates": "**`nodata`, not red.** The owed-versus-not-owed boundary. Without it, every new dataset starts life red on all its drift checks, which is how people learn to ignore a signal.",
   "breaksAs": null,
   "config": null,
   "requirements": [],
   "coordinates": null
  },
  {
   "id": "TS-31",
   "mode": "unit",
   "title": "Naive timestamp",
   "section": "Timestamps",
   "demonstrates": "Never silently interpreted. `pipeline/cadence.py` treats naive values as UTC, so a naive AWST value is eight hours out - enough on a daily feed to flip on-time to late or move a supply into the wrong slot. Stored values carry their offset.",
   "breaksAs": null,
   "config": null,
   "requirements": [],
   "coordinates": null
  },
  {
   "id": "TS-32",
   "mode": "unit",
   "title": "Supplier-provided timestamp",
   "section": "Timestamps",
   "demonstrates": "**ignored** in favour of our own receipt time. A file's metadata reflects the supplier's clock, timezone and bugs; staging's whole justification is that it asserts only facts we can vouch for.",
   "breaksAs": null,
   "config": null,
   "requirements": [],
   "coordinates": null
  },
  {
   "id": "TS-33a",
   "mode": "unit",
   "title": "A supply arriving in a period its dataset does not deliver in",
   "section": "An arrival with no open period",
   "demonstrates": "A June arrival of it is **held for a person** (REQ-PIPE-064) - filed neither backward into February nor forward into August.",
   "breaksAs": null,
   "config": null,
   "requirements": [
    "REQ-PIPE-064"
   ],
   "coordinates": null
  },
  {
   "id": "TS-33b",
   "mode": "unit",
   "title": "Its siblings must NOT be held with it",
   "section": "An arrival with no open period",
   "demonstrates": "Each is filed to its own open period and promoted on the ordinary green-or-amber rule. The hold is on one supply only.",
   "breaksAs": null,
   "config": null,
   "requirements": [],
   "coordinates": null
  },
  {
   "id": "TS-34",
   "mode": "INJECT",
   "title": "One delivery, two files for each of two datasets",
   "section": "Timestamps",
   "demonstrates": "`cp_clients` and `cp_placements` are HELD, each reported as needing action naming every file that matched. No view is built for either, so they are unqueryable for that run. The other four datasets are staged, assigned, classified and QA'd normally. Every cross-table check reading a held table reads RED naming it - which is three real checks against `cp_clients` alone (`cp_notifications`, `cp_investigations`, `cp_placements` each carry a referential check on `cp_client_id`). Neither held dataset's slot is filled, so both go overdue in the ordinary way.",
   "breaksAs": null,
   "config": null,
   "requirements": [],
   "coordinates": null
  },
  {
   "id": "TS-35",
   "mode": "unit",
   "title": "A held supply is never chosen between, even when one file is obviously newer",
   "section": "Timestamps",
   "demonstrates": "Still held. No rule consults size, mtime, lexical order or directory position. This asserts that a KNOWN-TEMPTING heuristic stays unimplemented rather than that the system computes something - label it as such, the same family as TS-3, so a later session does not \"fix\" it by adding the obvious tie-break. `REQ-PIPE-059` records why each such rule was rejected: every one is a guess dressed as a policy, and the dropped file is exactly the one a supplier will later say they sent.",
   "breaksAs": null,
   "config": null,
   "requirements": [
    "REQ-PIPE-059"
   ],
   "coordinates": null
  },
  {
   "id": "TS-36",
   "mode": "unit",
   "title": "One delivery, two collections",
   "section": "Timestamps",
   "demonstrates": "The delivery is processed NORMALLY. Each file is attributed to its own dataset and handled on that dataset's terms; nothing is held, rejected or failed for spanning collections (Keith, 2026-09-24). This CHANGES BUILT BEHAVIOUR twice - `qa_tools/common/arrivals.py`'s `classify()` raises today (and because recognition walks the whole tree, one such drop takes the run down for all 60 deliveries, reproduced before deciding), and it also returns a SINGLE `collection_id` that `arrivals_for()` filters on, so single-collection is structural rather than just a guard.",
   "breaksAs": null,
   "config": null,
   "requirements": [],
   "coordinates": null
  },
  {
   "id": "TS-36b",
   "mode": "unit",
   "title": "A mixed-collection delivery must not be held",
   "section": "Timestamps",
   "demonstrates": "The negative case, and it exists for the same reason TS-33b does: the rejected design (hold it for a human) is the one already written down in git history, so an implementation that reinstates it looks defensible in review. Assert explicitly that no hold, no anomaly and no warning is raised for the spanning itself - an unrecognised artefact inside such a delivery still warns on its own terms, which is a different thing.",
   "breaksAs": null,
   "config": null,
   "requirements": [],
   "coordinates": null
  },
  {
   "id": "TS-36c",
   "mode": "unit",
   "title": "One file, two datasets' patterns - the runtime hold",
   "section": "Timestamps",
   "demonstrates": "That file is HELD, attributed to NEITHER dataset, reported at no lower than WARNING, and the delivery and run both continue (Keith, 2026-09-24, `REQ-PIPE-058` criterion 9).",
   "breaksAs": null,
   "config": null,
   "requirements": [
    "REQ-PIPE-058"
   ],
   "coordinates": null
  },
  {
   "id": "TS-36d",
   "mode": "unit",
   "title": "The same collision, caught by the configuration gate",
   "section": "Timestamps",
   "demonstrates": "`mothman check` FAILS, naming both datasets and the example filename. **And the negative half matters as much**: with that filename ABSENT from history the gate PASSES, which is the known, accepted limit of the corpus approach - real regex intersection was rejected on cost (`REQ-PIPE-058`). A test asserting the gate catches an unwitnessed collision is asserting the rejected design.",
   "breaksAs": null,
   "config": null,
   "requirements": [
    "REQ-PIPE-058"
   ],
   "coordinates": null
  },
  {
   "id": "TS-37",
   "mode": "unit",
   "title": "A delivery directory with no receipt record",
   "section": "Timestamps",
   "demonstrates": "Skipped as in-flight, reported **on every run** as an informational observation, and every other delivery processed normally. NOT a hard error - reproduced 2026-09-24 that one such directory makes `list_deliveries()` raise, taking all 60 with it. NO configured interval, NO file modification time, NO state counting runs: persistence shows through repetition. The reason this is the normal case rather than an edge - under a real transport a delivery has no receipt until our own BOUNDARY RULE says it is complete, and in S3 events fire per object with no delivery-is-finished signal, so \"files present, no receipt\" is the state of every delivery until the boundary closes.",
   "breaksAs": null,
   "config": null,
   "requirements": [],
   "coordinates": null
  },
  {
   "id": "TS-38",
   "mode": "INJECT",
   "title": "A resupply whose filename no longer matches",
   "section": "Timestamps",
   "demonstrates": "The matched files are attributed and processed; the unmatched ones are reported as unrecognised artefacts at **warning** level. Critically, the supply is **NOT** silently treated as complete - the warning is the only thing standing between this and a promoted, green, HALF supply. Had the resupplies matched, this would instead be the duplicate-match hold of TS-34, which is louder still.",
   "breaksAs": null,
   "config": null,
   "requirements": [],
   "coordinates": {
    "dataset": "cp-clients",
    "supplies": [
     "cp_clients__202602010900000800"
    ],
    "period": "2026-Q1",
    "inPlaceOn": "2026-02-01"
   }
  },
  {
   "id": "TS-39",
   "mode": "unit",
   "title": "A split extract, once patterns are regexes",
   "section": "Timestamps",
   "demonstrates": "A duplicate match, so the dataset is HELD (TS-34's machinery), not a silent choice between them. Verified 2026-09-24 that under today's `keyPattern` reuse this is NOT reachable for Child Protection - `cp/{delivery_id}/cp_clients.csv` reduces to `^cp_clients\\.csv$`, so `part2` matches nothing and falls out as unrecognised instead, which is the TS-38 shape. Reachable for Birth Registrations only because its pattern carries a `{date}` placeholder. This scenario is what proves the regex change (`REQ-PIPE-058`, 2026-09-24) actually closed the gap.",
   "breaksAs": null,
   "config": null,
   "requirements": [
    "REQ-PIPE-058"
   ],
   "coordinates": null
  },
  {
   "id": "TS-40",
   "mode": "unit",
   "title": "A run dies mid-load, and the next run must not trust what it finds",
   "section": "Timestamps",
   "demonstrates": "Every table without a committed load record is treated as unloaded and replaced, whatever is sitting in the staging schema. The delivery is not considered processed until every attributed file has a record.",
   "breaksAs": null,
   "config": null,
   "requirements": [],
   "coordinates": null
  },
  {
   "id": "TS-41",
   "mode": "INJECT",
   "title": "A resend supersedes the failed supply before it",
   "section": "The option A and period-closing batch, planted (REQ-GEN-136, REQ-GEN-137)",
   "demonstrates": "The resend supersedes the waiting 14:00 supply, which moves to the period's superseded schema, named as superseded by the resend (REQ-PIPE-118).",
   "breaksAs": "Two versions of one table waiting for one day, every reader contested.",
   "config": "Config: daily, due 14:00 AWST - TS-1's own placement. Settings in force where it lands (2026-09-15): amber setting promote-and-acknowledge, replacement setting never.",
   "requirements": [
    "REQ-PIPE-118"
   ],
   "coordinates": {
    "dataset": "birth-registrations",
    "supplies": [
     "birth_registrations__202609151400000800",
     "birth_registrations__202609151600000800",
     "birth_registrations__202609152000000800"
    ],
    "period": "2026-09-15",
    "inPlaceOn": "2026-09-15"
   }
  },
  {
   "id": "TS-42",
   "mode": "INJECT",
   "title": "A contested pair of one Child Protection table, resolved by a later file",
   "section": "The option A and period-closing batch, planted (REQ-GEN-136, REQ-GEN-137)",
   "demonstrates": "NOT IN THE DATA, and not for want of a build: Child Protection's arrival patterns are exact filenames, so two files in one directory can never both match one table - the same finding TS-34 records. Planting it means widening a pattern, which is Keith's call (REQ-PIPE-118, REQ-PIPE-105 criterion 6).",
   "breaksAs": null,
   "config": null,
   "requirements": [
    "REQ-PIPE-118",
    "REQ-PIPE-105"
   ],
   "coordinates": null
  },
  {
   "id": "TS-43",
   "mode": "INJECT",
   "title": "An amber supply held under hold",
   "section": "The option A and period-closing batch, planted (REQ-GEN-136, REQ-GEN-137)",
   "demonstrates": "The amber supply is not promoted; the rule records a promotion-withheld note naming the setting, and the slot reads amber, waiting for a person (REQ-PIPE-122).",
   "breaksAs": "It promotes itself, as it would under promote.",
   "config": "Config: daily; the amber setting is HOLD from 2026-09-01.",
   "requirements": [
    "REQ-PIPE-122"
   ],
   "coordinates": null
  },
  {
   "id": "TS-44",
   "mode": "INJECT",
   "title": "An amber supply promoted and awaiting acknowledgement",
   "section": "The option A and period-closing batch, planted (REQ-GEN-136, REQ-GEN-137)",
   "demonstrates": "Promoted by the rule, recorded with the setting, and shown as awaiting acknowledgement (REQ-PIPE-122).",
   "breaksAs": "Promoted with nothing asked, or held.",
   "config": "Config: daily; PROMOTE-AND-ACKNOWLEDGE from 2026-09-10.",
   "requirements": [
    "REQ-PIPE-122"
   ],
   "coordinates": null
  },
  {
   "id": "TS-45",
   "mode": "INJECT",
   "title": "The same, acknowledged by a person",
   "section": "The option A and period-closing batch, planted (REQ-GEN-136, REQ-GEN-137)",
   "demonstrates": "Beside TS-44's, this one reads acknowledged, by the person, with their reason (REQ-PIPE-122, REQ-GEN-137 criterion 4).",
   "breaksAs": "The acknowledgement refused, or written outside the decision path.",
   "config": "Config: as TS-44; a scripted acknowledgement three hours after receipt.",
   "requirements": [
    "REQ-PIPE-122",
    "REQ-GEN-137"
   ],
   "coordinates": null
  },
  {
   "id": "TS-46",
   "mode": "INJECT",
   "title": "A green resupply replaces the promoted supply",
   "section": "The option A and period-closing batch, planted (REQ-GEN-136, REQ-GEN-137)",
   "demonstrates": "The 16:00 supply is promoted by the rule, naming the supply it replaced and the setting; the 14:00 one is superseded, not rejected, and its supply-history row says so (REQ-PIPE-123, REQ-DASH-127).",
   "breaksAs": "The resend waits for a person, as it would under never.",
   "config": "Config: daily; the replacement setting is GREEN from 2026-09-18 to 2026-09-21.",
   "requirements": [
    "REQ-PIPE-123",
    "REQ-DASH-127"
   ],
   "coordinates": null
  },
  {
   "id": "TS-47",
   "mode": "INJECT",
   "title": "A daily file arriving after the next day's window opened",
   "section": "The option A and period-closing batch, planted (REQ-GEN-136, REQ-GEN-137)",
   "demonstrates": "It fills the NEXT day, the period open when it arrived; its own day closes with no supply, overdue, and a scripted person marks it not supplied, so it reads \"not supplied (accepted)\" (REQ-PIPE-131, REQ-PIPE-132, REQ-DASH-133, REQ-GEN-137 criterion 3).",
   "breaksAs": "Filed backward to its own day.",
   "config": "Config: daily, due 14:00, 4-hour claim window - the next day's window opens at 10:00. Settings in force where it lands (2026-09-07): amber setting hold, replacement setting never.",
   "requirements": [
    "REQ-PIPE-131",
    "REQ-PIPE-132",
    "REQ-DASH-133",
    "REQ-GEN-137"
   ],
   "coordinates": {
    "dataset": "birth-registrations",
    "supplies": [
     "birth_registrations__202609081100000800"
    ],
    "period": "2026-09-07",
    "inPlaceOn": "2026-09-08"
   }
  },
  {
   "id": "TS-48",
   "mode": "INJECT",
   "title": "A correction arriving before its partner is promoted",
   "section": "The option A and period-closing batch, planted (REQ-GEN-136, REQ-GEN-137)",
   "demonstrates": "NOT IN THE DATA YET. A single-table correction that goes red on a cross-table check and is promoted when its partner's promotion re-checks it (REQ-PIPE-121) needs the Child Protection generator to place a partner's promotion between two arrivals of one quarter, which its delivery shapes do not yet express.",
   "breaksAs": null,
   "config": null,
   "requirements": [
    "REQ-PIPE-121"
   ],
   "coordinates": null
  },
  {
   "id": "TS-49",
   "mode": "INJECT",
   "title": "A correction still failing after its partner's promotion",
   "section": "The option A and period-closing batch, planted (REQ-GEN-136, REQ-GEN-137)",
   "demonstrates": "NOT IN THE DATA YET, for TS-48's reason. Would produce the decision log's still-failing record (REQ-PIPE-121 criterion 12).",
   "breaksAs": null,
   "config": null,
   "requirements": [
    "REQ-PIPE-121"
   ],
   "coordinates": null
  },
  {
   "id": "TS-50",
   "mode": "INJECT",
   "title": "A reader re-checked against the newer version",
   "section": "The option A and period-closing batch, planted (REQ-GEN-136, REQ-GEN-137)",
   "demonstrates": "NOT IN THE DATA YET, for TS-48's reason (REQ-PIPE-118, REQ-PIPE-123 with a cross-table reader).",
   "breaksAs": null,
   "config": null,
   "requirements": [
    "REQ-PIPE-118",
    "REQ-PIPE-123"
   ],
   "coordinates": null
  },
  {
   "id": "TS-51",
   "mode": "INJECT",
   "title": "A promoted supply turned red by a later sibling",
   "section": "The option A and period-closing batch, planted (REQ-GEN-136, REQ-GEN-137)",
   "demonstrates": "NOT IN THE DATA YET. Needs a Child Protection file shape that breaks a promoted sibling's referential check (REQ-DASH-126).",
   "breaksAs": null,
   "config": null,
   "requirements": [
    "REQ-DASH-126"
   ],
   "coordinates": null
  },
  {
   "id": "TS-52",
   "mode": "INJECT",
   "title": "Case Workers arriving in a period it does not deliver in",
   "section": "The option A and period-closing batch, planted (REQ-GEN-136, REQ-GEN-137)",
   "demonstrates": "NOT INJECTED: the ordinary history already produces it - Case Workers files arrive in every delivery and are held in the quarters it does not take part in (TS-33a, REQ-PIPE-131). An injection would record a placement for what is already there; it waits on the Child Protection injection supporting a placement with no extra arrival.",
   "breaksAs": null,
   "config": null,
   "requirements": [
    "REQ-PIPE-131"
   ],
   "coordinates": null
  },
  {
   "id": "TS-53",
   "mode": "INJECT",
   "title": "Keith's worked un-supersede case",
   "section": "The option A and period-closing batch, planted (REQ-GEN-136, REQ-GEN-137)",
   "demonstrates": "NOT IN THE DATA - FOR KEITH. A good file superseded by a bad later one, the bad one rejected and the good one un-superseded, re-checked and promoted by the gate (REQ-PIPE-120). Under the rules as built a good file is superseded only while WAITING, and a green one waits only behind a filled slot or a hold - in either case the gate does not promote it after the un-supersede without a further decision. What should the planted shape be?",
   "breaksAs": null,
   "config": null,
   "requirements": [
    "REQ-PIPE-120"
   ],
   "coordinates": null
  },
  {
   "id": "TS-54",
   "mode": "INJECT",
   "title": "A period substituted onto an earlier promoted supply",
   "section": "The option A and period-closing batch, planted (REQ-GEN-136, REQ-GEN-137)",
   "demonstrates": "NOT IN THE DATA YET: the script has no field for the period stood on (REQ-PIPE-084, REQ-GEN-137 criterion 5).",
   "breaksAs": null,
   "config": null,
   "requirements": [
    "REQ-PIPE-084",
    "REQ-GEN-137"
   ],
   "coordinates": null
  },
  {
   "id": "TS-55",
   "mode": "INJECT",
   "title": "A period whose _manifest lists all three kinds",
   "section": "The option A and period-closing batch, planted (REQ-GEN-136, REQ-GEN-137)",
   "demonstrates": "NOT IN THE DATA YET: needs TS-54's substitution beside an inheritance in one period (REQ-PIPE-130, REQ-GEN-137 criterion 6).",
   "breaksAs": null,
   "config": null,
   "requirements": [
    "REQ-PIPE-130",
    "REQ-GEN-137"
   ],
   "coordinates": null
  },
  {
   "id": "TS-56",
   "mode": "INJECT",
   "title": "A supply whose columns arrive in another order",
   "section": "The option A and period-closing batch, planted (REQ-GEN-136, REQ-GEN-137)",
   "demonstrates": "It loads as usual, because columns are matched by name; its column-order file check WARNS, shown in the dataset's file section, and the dataset's status is unchanged by it (REQ-QAC-096 criteria 12 and 18, REQ-DASH-097 criterion 7, REQ-GEN-044 criterion 16).",
   "breaksAs": "Refused, or the dataset turned amber or red by a warning.",
   "config": "Config: quarterly, Feb/May/Aug/Nov.",
   "requirements": [
    "REQ-QAC-096",
    "REQ-DASH-097",
    "REQ-GEN-044"
   ],
   "coordinates": {
    "dataset": "cp-carers",
    "supplies": [
     "cp_carers__202411010900000800"
    ],
    "period": "2024-Q4",
    "inPlaceOn": "2024-11-01"
   }
  }
 ]
}
-->
