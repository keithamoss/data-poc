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

**55 of 66 scenarios marked for injection have data behind them today.** 103 scenarios are registered in all; the rest are unit tests with nothing to look at.

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

*Config: Emergency Department, the quarterly calendar - the 1st of February, May, August and November, due 09:00, a 14-day claim window, so May 2025's window opens 09:00 on 17 April. February 2025's supply arrived as usual; this one arrives 10:00 on 16 April 2025, a day before May's window opens (REQ-GEN-236).* **Expect** (the first bootstrapped build, 2026-10-18): filed to **2025-Q1** by the branch `resupply-of-open-slot`, classified `late` - May's window has not opened, so February is still the open period, and it is filled. Being a resupply of a filled slot it is **not promoted**: 2025-Q2 is left with no supply, and the next quarter's drift checks fail by the gap rule (REQ-QAC-108), measured against February's supply. **Breaks as**: files to May because it is "nearly" May's - the window would then mean nothing. Keeps the family's note: the filled branch is a contained imperfection - a supplier one day early leaves a quarter to be put right by a person - not a defect.

**What it would look like if the rule were wrong.** Files to May because it is "nearly" May's - the window would then mean nothing. Keeps the family's note: the filled branch is a contained imperfection - a supplier one day early leaves a quarter to be put right by a person - not a defect.

*Config: Emergency Department, the quarterly calendar - the 1st of February, May, August and November, due 09:00, a 14-day claim window, so May 2025's window opens 09:00 on 17 April. February 2025's supply arrived as usual; this one arrives 10:00 on 16 April 2025, a day before May's window opens (REQ-GEN-236).*

| Where to look | |
|---|---|
| Dataset | ed-presentations |
| Supplies | `ed_presentations__202504161000000800` |
| Period | 2025-Q2 |
| Set the in-place-on date to | 2025-05-01 |

### TS-3b - Quarterly, prior slot UNFILLED

*Same config, on Emergency Department, a year later: February 2026's supply never came (suppressed), and May's arrives 10:00 on 16 April 2026, a day before its window opens.* **Expect** (the first bootstrapped build, 2026-10-18): filed to **2026-Q1** by the branch `open-slot-unfilled`, classified `late` - about 74 days - because February is still the open period and nothing filled it. 2026-Q2 is left with no supply. **Breaks as**: files to May and leaves February owed for ever.

**What it would look like if the rule were wrong.** Files to May and leaves February owed for ever.

| Where to look | |
|---|---|
| Dataset | ed-presentations |
| Supplies | `ed_presentations__202604161000000800` |
| Period | 2026-Q2 |
| Set the in-place-on date to | 2026-05-01 |

### TS-3c - Daily, prior slot FILLED

**What it demonstrates.** Tuesday's window has not opened, so Monday is the open period, and it is filled -> **resupply of Monday**, no auto-promotion, holds and warns.

*Config: daily evening-before - the supply for day D is due 22:00 on D-1 - early window 4 hours, so Tuesday's window opens 18:00 Monday. Monday's slot filled. Arrival 17:00 Monday, one hour outside.*

| Where to look | |
|---|---|
| Dataset | birth-registrations |
| Supplies | `birth_registrations__202606212100000800`, `birth_registrations__202606221700000800` |
| Period | 2026-06-22 |
| Set the in-place-on date to | 2026-06-22 |

### TS-3d - Daily, prior slot UNFILLED

**What it demonstrates.** Monday is still the open period -> fills **Monday, 19 hours late**.

| Where to look | |
|---|---|
| Dataset | birth-registrations |
| Supplies | `birth_registrations__202606251700000800` |
| Period | 2026-06-25 |
| Set the in-place-on date to | 2026-06-25 |

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

| Where to look | |
|---|---|
| Dataset | cp-clients |
| Supplies | `cp_clients__202404221000000800` |
| Period | 2024-Q2 |
| Set the in-place-on date to | 2024-05-01 |

### TS-10a - Evening-before daily arrival, Monday filled

**What it demonstrates.** The 22:00 arrival fills **Tuesday, on time**.

*Config: daily, Tuesday's supply due 22:00 MONDAY, claim window 4 hours - so Tuesday's window opens 18:00 Monday, and Monday closes then.*

| Where to look | |
|---|---|
| Dataset | birth-registrations |
| Supplies | `birth_registrations__202606192200000800` |
| Period | 2026-06-20 |
| Set the in-place-on date to | 2026-06-20 |

### TS-10b - Evening-before daily arrival, Monday unfilled

**What it demonstrates.** The 22:00 arrival ALSO fills **Tuesday, on time**, and Monday closes with no supply. **Changed 2026-10-04 by REQ-PIPE-131**: this variant used to file Monday, late - slot state decided between two answers. Keith's worked consequence: Monday's file arriving after Tuesday's claim window opened is filed as Tuesday's; Monday closes empty, visibly, and Tuesday's real file then supersedes it (REQ-PIPE-118), replaces it (REQ-PIPE-123), or waits for a person. The cutoff still lives in `due_at` and the claim window, not in code.

| Where to look | |
|---|---|
| Dataset | birth-registrations |
| Supplies | `birth_registrations__202606272200000800` |
| Period | 2026-06-28 |
| Set the in-place-on date to | 2026-06-28 |

### TS-11 - A re-filed supply reclassifies

**What it demonstrates.** The verdict **recomputes** - it now reads on time. A supply reported late only because it was misfiled was never actually late. The re-filed supply returns to staging under a NEW filing (the old one kept), is checked again as a run of its own, and the gate decides (REQ-PIPE-140, REQ-PIPE-141). *Used to expect* the supply to move between slots and stay promoted - REQ-PIPE-141 made a re-file never fill its target directly.

*unit test - no generated data, nothing to navigate to*

### TS-65 - Early, at the edge of the window

**What it demonstrates.** Assigned **2025-Q3** and classified **early by 13 days**, exactly as TS-9 - the window is a boundary, and a supply inside it by a day is as early-and-fine as one inside it by a week (REQ-PIPE-131).

**What it would look like if the rule were wrong.** Treated as a resupply of 2025-Q2, as if the window counted from somewhere else.

*Config: as TS-9 - Child Protection, quarterly, due 09:00 on the 1st, claim window 14 days. 2025-Q3 (1 August) arrives 19 July at 10:00, thirteen days early, a day after its window opened at 09:00 on 18 July.*

| Where to look | |
|---|---|
| Dataset | cp-clients |
| Supplies | `cp_clients__202507191000000800` |
| Period | 2025-Q3 |
| Set the in-place-on date to | 2025-08-01 |

### TS-66 - A couple of days early - the everyday case

**What it demonstrates.** Assigned **2025-Q4**, classified **early by 2 days**, and otherwise unremarkable - it fills and promotes like an on-time supply.

**What it would look like if the rule were wrong.** Shown as anything more alarming than early.

*Config: as TS-9. 2025-Q4 (1 November) arrives 30 October at 10:00.*

| Where to look | |
|---|---|
| Dataset | cp-clients |
| Supplies | `cp_clients__202510301000000800` |
| Period | 2025-Q4 |
| Set the in-place-on date to | 2025-11-01 |

### TS-67 - A quarterly supply sent too early

**What it demonstrates.** It cannot claim 2023-Q4, whose window has not opened - nothing claims forward (REQ-PIPE-062 criterion 5). The open period when it arrives is 2023-Q3, so it files there as a **resupply of 2023-Q3** (REQ-PIPE-131), and the rule refuses to promote it over 2023-Q3's accepted supply. Then a PERSON re-files it to 2023-Q4 (a scripted decision, REQ-GEN-135, at 10:00 on 21 October, once Q4's window is open), so 2023-Q4 is not left with no supply. Keith, 2026-10-12: "plus one too early" - the case people will ask about - and "have it refiled to Q4 by a synthetic human making a decision".

**What it would look like if the rule were wrong.** Assigned 2023-Q4 by the RULE because it was obviously meant for it; or 2023-Q4 left empty once the person has re-filed it.

*Config: as TS-9. 2023-Q4 (1 November) is due 09:00 that day and its window opens 09:00 on 18 October; the supply arrives 12 October at 10:00, twenty days early and six days before the window. 2023-Q3, before it, is an ordinary quarter whose own supply has arrived.*

| Where to look | |
|---|---|
| Dataset | cp-clients |
| Supplies | `cp_clients__202310121000000800` |
| Period | 2023-Q4 |
| Set the in-place-on date to | 2023-11-01 |

### TS-68 - A duplicate send

**What it demonstrates.** File one D's supply, early and promoted; file two kept but superseded. **Breaks as**: the duplicate, sorting first, taken as file one - the staged ordinal and the supply ordinal disagreeing.

**What it would look like if the rule were wrong.** The duplicate, sorting first, taken as file one - the staged ordinal and the supply ordinal disagreeing.

| Where to look | |
|---|---|
| Dataset | birth-registrations |
| Supplies | `birth_registrations__202607281340000800` |
| Period | 2026-07-28 |
| Set the in-place-on date to | 2026-07-28 |
| Built to | green, the 2026-07-28 13:40 arrival |

### TS-69 - Tomorrow's file sent early with today's

**What it demonstrates.** File one D's supply; file two re-filed to D+1, checked there, and D+1's only supply. **Breaks as**: D+1 left with no supply, or the re-filed file checked against D.

**What it would look like if the rule were wrong.** D+1 left with no supply, or the re-filed file checked against D.

| Where to look | |
|---|---|
| Dataset | birth-registrations |
| Supplies | `birth_registrations__202608021330000800` |
| Period | 2026-08-02 |
| Set the in-place-on date to | 2026-08-02 |
| Built to | green, the 2026-08-02 13:30 arrival |
| Built to | green, the 2026-08-02 13:45 arrival |

### TS-70 - A faulty file and its corrected re-export

**What it demonstrates.** File one rejected; file two D's supply, its own receipt taken, so D reads **late**, 4:30pm; no hold; D+1 unaffected. **Breaks as**: D read early from file one's receipt.

**What it would look like if the rule were wrong.** D read early from file one's receipt.

| Where to look | |
|---|---|
| Dataset | birth-registrations |
| Supplies | `birth_registrations__202608071340000800` |
| Period | 2026-08-07 |
| Set the in-place-on date to | 2026-08-07 |
| Built to | green, the 2026-08-07 16:30 arrival |

### TS-71 - A stray test file that loads

**What it demonstrates.** The test file rejected; the real one D's supply, early. **Breaks as**: the test rows checked as D's supply.

**What it would look like if the rule were wrong.** The test rows checked as D's supply.

| Where to look | |
|---|---|
| Dataset | birth-registrations |
| Supplies | `birth_registrations__202608121320000800` |
| Period | 2026-08-12 |
| Set the in-place-on date to | 2026-08-12 |
| Built to | green, the 2026-08-12 13:40 arrival |

### TS-72 - A stray test file the load refuses

**What it demonstrates.** The test file offered only "rejected", named as never loaded; the real file D's supply, checked by the real tools, early and promoted, and the refused file marked as never loaded. **Breaks as**: the real file named as the one that never loaded.

**What it would look like if the rule were wrong.** The real file named as the one that never loaded.

| Where to look | |
|---|---|
| Dataset | birth-registrations |
| Supplies | `birth_registrations__202608171330000800` |
| Period | 2026-08-17 |
| Set the in-place-on date to | 2026-08-17 |
| Built to | green, the 2026-08-17 13:30 arrival |

### TS-73 - Reject both

**What it demonstrates.** Each file's rejection its own entry, no QA, nothing promoted, D left owed and unfilled with no mark-not-supplied and no later supply. **Breaks as**: D read as supplied, or not-supplied by a person.

**What it would look like if the rule were wrong.** D read as supplied, or not-supplied by a person.

| Where to look | |
|---|---|
| Dataset | birth-registrations |
| Supplies | `birth_registrations__202608211320000800` |
| Period | 2026-08-21 |
| Set the in-place-on date to | 2026-08-21 |

### TS-74 - Re-file one, reject the other

**What it demonstrates.** One QA run, for D+1; D owed and unfilled, no mark-not-supplied. **Breaks as**: the early file checked against D.

**What it would look like if the rule were wrong.** The early file checked against D.

| Where to look | |
|---|---|
| Dataset | birth-registrations |
| Supplies | `birth_registrations__202608251330000800` |
| Period | 2026-08-25 |
| Set the in-place-on date to | 2026-08-25 |
| Built to | green, the 2026-08-25 13:30 arrival |

## Delivery and multi-table

### TS-12 - Five tables load, one is an invalid CSV

**What it demonstrates.** - The five are staged, QA'd, green, and auto-promoted. Their August slots are **filled**, and their own checks are unaffected - they are not dragged down. - `cp_clients` is **red** (a supply that cannot be loaded is a red QA finding), rejected, and its August slot stays **unfilled**. - Every check declaring `depends_on: [cp_clients]` - including "Client reference", which is DEFINED on `cp_notifications` - **cannot run**, and reads **red with a qualifying chip naming `cp_clients` as the blocker**. - That red lands at **collection** level, since cross-table checks are lifted there. `cp_notifications` keeps its own green status and carries only an informational pointer: fully verified against its own data, unverified against its relationships.

| Where to look | |
|---|---|
| Dataset | cp-clients |
| Supplies | `cp_clients__202505010900000800`, `cp_clients__202505291000000800` |
| Period | 2025-Q2 |
| Set the in-place-on date to | 2025-05-02 |

### TS-13 - Six tables landing seconds apart

**What it demonstrates.** **one QA run over the delivery**, with no intermediate state in which cross-table checks read red. The test asserts the ABSENCE of flicker.

**What it would look like if the rule were wrong.** Per-table triggering evaluates "Client reference" at 09:00:00 when notifications has not arrived, so it reads red, then green four seconds later. Transiently true and practically useless - and at 30 datasets, a red appearing on every healthy delivery is how people learn to ignore red.

**not injected - nothing to look at yet**

### TS-14 - A later single-table resupply

**What it demonstrates.** It arrives as **its own delivery** and triggers QA. Its slot is clients' own August slot - per-table slot sequences mean there is no "resupply of table X within delivery Y" concept to implement; it is just clients' August supply, arriving late. The previously blocked cross-table check now runs. If green, clients promotes and August's slot fills. The recorded QA history keeps **both** runs - the period's current state is the latest, its history is all of them. Clients arriving also re-evaluates the waiting placements' reading checks and re-gates them (REQ-PIPE-121). *Used to say* `qa_results/` kept both runs - REQ-PIPE-089 moved the history into the database. *In the data since 2026-10-15 (REQ-GEN-044 criterion 1)*, riding TS-12's placement: TS-12's cp_clients is refused in 2025-Q2, and the corrected cp_clients arrives alone 28 days later, 10:00 on 2025-05-29, filed to 2025-Q2's still-empty slot. TS-12's link sits between the two; TS-14's lands on the correction's day.

| Where to look | |
|---|---|
| Dataset | cp-clients |
| Supplies | `cp_clients__202505010900000800`, `cp_clients__202505291000000800` |
| Period | 2025-Q2 |
| Set the in-place-on date to | 2025-05-29 |

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

**What it demonstrates.** A duplicate match, so the dataset is HELD (TS-34's machinery), not a silent choice between them. Verified 2026-09-24 that under today's `keyPattern` reuse this is NOT reachable for Child Protection - `cp/{delivery_id}/cp_clients.csv` reduces to `^cp_clients\.csv$`, so `part2` matches nothing and falls out as unrecognised instead, which is the TS-38 shape. Reachable for Birth Registrations only because its pattern carries a `{date}` placeholder. This scenario is what proves the regex change (`REQ-PIPE-058`, 2026-09-24) actually closed the gap. NOW REACHABLE for `cp_clients` (REQ-PIPE-202, 2026-10-15): its pattern is `cp_clients(_[^/]+)?\.csv`, so `cp_clients_part2.csv` matches and the pair is held as contested - `tests/test_holds.py::test_ts39_a_second_part_beside_the_extract_is_contested`. Every other Child Protection pattern is still an exact filename.

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

### TS-42a - A contested pair of one Child Protection table, while it is contested

PLANTED by REQ-GEN-203 (2026-10-18) in a grown quarter (REQ-GEN-207), after REQ-PIPE-202 widened `cp_clients`' pattern so two of its files in one delivery contest the table; `tests/test_cp_pair.py` drives the shape through the real orchestrator. Two lettered siblings share the one placement (REQ-GEN-201): this one's link opens on the pair's arrival day. *Config: quarterly, Feb/May/Aug/Nov, due 09:00 on the 1st, claim window 14 days. 2019-Q4's delivery carries the usual files and two Client Registers - cp_clients.csv at 08:30 and a re-export, cp_clients_v2.csv, at 08:40 whose rows differ (each re-pulled an hour later) - both before due; a clean cp_clients.csv follows alone on 29 November at 10:00, after due and before 2020-Q1's window opens, built green (REQ-GEN-184) after one green lead-in quarter (2019-Q3) and before a green one (2020-Q1).* **Breaks as**: one of the two files taken as the quarter's supply, or the three readers' cross-table checks evaluated against either.

**What it would look like if the rule were wrong.** One of the two files taken as the quarter's supply, or the three readers' cross-table checks evaluated against either.

*Config: quarterly, Feb/May/Aug/Nov, due 09:00 on the 1st, claim window 14 days. 2019-Q4's delivery carries the usual files and two Client Registers - cp_clients.csv at 08:30 and a re-export, cp_clients_v2.csv, at 08:40 whose rows differ (each re-pulled an hour later) - both before due; a clean cp_clients.csv follows alone on 29 November at 10:00, after due and before 2020-Q1's window opens, built green (REQ-GEN-184) after one green lead-in quarter (2019-Q3) and before a green one (2020-Q1).*

| Where to look | |
|---|---|
| Dataset | cp-clients |
| Supplies | `cp_clients__201911010830000800`, `cp_clients__201911291000000800` |
| Period | 2019-Q4 |
| Set the in-place-on date to | 2019-11-01 |
| Built to | green, the 2019-11-29 10:00 arrival |

### TS-42b - A contested pair of one Child Protection table, resolved by a later file

TS-42a's placement; this link opens on the later file's asset day. *Config: as TS-42a.* **Breaks as**: the pair still contested after the later file, or the later file filed as a resupply rather than ending the contest.

**What it would look like if the rule were wrong.** The pair still contested after the later file, or the later file filed as a resupply rather than ending the contest.

*Config: as TS-42a.*

| Where to look | |
|---|---|
| Dataset | cp-clients |
| Supplies | `cp_clients__201911010830000800`, `cp_clients__201911291000000800` |
| Period | 2019-Q4 |
| Set the in-place-on date to | 2019-11-29 |
| Built to | green, the 2019-11-29 10:00 arrival |

### TS-43 - An amber supply held under hold

**What it demonstrates.** The amber supply is not promoted; the rule records a promotion-withheld note naming the setting, and the slot reads amber, waiting for a person (REQ-PIPE-122).

**What it would look like if the rule were wrong.** It promotes itself, as it would under promote.

*Config: daily; the amber setting is HOLD from 2026-08-30 (TS-78's version, REQ-GEN-199); a scripted promotion at 10:00 the next morning.*

| Where to look | |
|---|---|
| Dataset | birth-registrations |
| Supplies | `birth_registrations__202609051400000800` |
| Period | 2026-09-05 |
| Set the in-place-on date to | 2026-09-05 |
| Built to | amber on place_of_birth_facility.completeness (445 of 1,933), the 2026-09-05 14:00 arrival |

### TS-44 - An amber supply promoted and awaiting acknowledgement

**What it demonstrates.** Promoted by the rule, recorded with the setting, and shown as awaiting acknowledgement (REQ-PIPE-122).

**What it would look like if the rule were wrong.** Promoted with nothing asked, or held.

*Config: daily; PROMOTE-AND-ACKNOWLEDGE from 2026-09-10.*

| Where to look | |
|---|---|
| Dataset | birth-registrations |
| Supplies | `birth_registrations__202609131400000800` |
| Period | 2026-09-13 |
| Set the in-place-on date to | 2026-09-13 |
| Built to | amber on registering_parent_1_name.completeness (145 of 1,993), the 2026-09-13 14:00 arrival |

### TS-45 - The same, acknowledged by a person

**What it demonstrates.** Beside TS-44's, this one reads acknowledged, by the person, with their reason (REQ-PIPE-122, REQ-GEN-137 criterion 4).

**What it would look like if the rule were wrong.** The acknowledgement refused, or written outside the decision path.

*Config: as TS-44; a scripted acknowledgement five hours after receipt, once the rule has promoted it.*

| Where to look | |
|---|---|
| Dataset | birth-registrations |
| Supplies | `birth_registrations__202609171400000800` |
| Period | 2026-09-17 |
| Set the in-place-on date to | 2026-09-17 |
| Built to | amber on registering_parent_2_name.completeness (625 of 2,119), the 2026-09-17 14:00 arrival |

### TS-46 - A green resupply replaces the promoted supply

**What it demonstrates.** The 16:00 supply is promoted by the rule, naming the supply it replaced and the setting; the 14:00 one is superseded, not rejected, and its supply-history row says so (REQ-PIPE-123, REQ-DASH-127).

**What it would look like if the rule were wrong.** The resend waits for a person, as it would under never.

*Config: daily; the replacement setting is GREEN from 2026-09-18 to 2026-09-21.*

| Where to look | |
|---|---|
| Dataset | birth-registrations |
| Supplies | `birth_registrations__202609211400000800`, `birth_registrations__202609211600000800` |
| Period | 2026-09-21 |
| Set the in-place-on date to | 2026-09-21 |
| Built to | green, the 2026-09-21 14:00 arrival |
| Built to | green, the 2026-09-21 16:00 arrival |

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

In the data since 2026-10-15 (REQ-GEN-044 criterion 1; Keith, 2026-10-14, Q13): demonstrated by TS-76's placement - cp-placements' 2025-Q1 substituted by a scripted person onto 2024-Q4, whose cp-placements supply was promoted green - with its own link while the substitution stands. CORRECTED 2026-10-16 (post-build-review #207 D1): REQ-GEN-207 moved the ordinary amber drawn for 2026-Q3 to 2024-Q4 and this entry then said "promoted amber", but that amber dirties only cp_carers and cp_clients, so cp-placements' 2024-Q4 supply is still green and promoted. Whether it should be amber is with Keith. The script's `stands_on` field (REQ-GEN-200) answered the old blocker.

| Where to look | |
|---|---|
| Dataset | cp-placements |
| Supplies | — |
| Period | 2025-Q1 |
| Set the in-place-on date to | 2025-02-17 |

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
| Supplies | `cp_carers__202608010900000800` |
| Period | 2026-Q3 |
| Set the in-place-on date to | 2026-08-01 |

### TS-80 - A contested pair of one Child Protection table, settled by a person

PLANTED by REQ-GEN-203 (2026-10-18) in a grown quarter (REQ-GEN-207): a stray test file (TS-71's shape) beside the real Client Register, so a settlement can be seen clearing the cross-table readers the contest held, which only Child Protection has. Its link opens on the pair's arrival day. *Config: quarterly, Feb/May/Aug/Nov, due 09:00 on the 1st, claim window 14 days. 2020-Q4's delivery carries the usual files and two Client Registers - a stray test file, cp_clients_TEST.csv, every client named TEST, at 08:20 on the due day and the real cp_clients.csv at 08:30, both before 09:00 - after one green lead-in quarter (2020-Q3) and before a green one (2021-Q1), the real extract built green. A scripted person settles the pair at 11:00 the next day (contract/scripted_decisions.yaml, "TS-80 settle"): file one by receipt, the test file, rejected; file two, the real extract, the quarter's supply.* **Breaks as**: the test rows checked as the quarter's supply, the readers left contested after the settlement, or the file named by sorted name rather than by receipt position.

**What it would look like if the rule were wrong.** The test rows checked as the quarter's supply, the readers left contested after the settlement, or the file named by sorted name rather than by receipt position.

*Config: quarterly, Feb/May/Aug/Nov, due 09:00 on the 1st, claim window 14 days. 2020-Q4's delivery carries the usual files and two Client Registers - a stray test file, cp_clients_TEST.csv, every client named TEST, at 08:20 on the due day and the real cp_clients.csv at 08:30, both before 09:00 - after one green lead-in quarter (2020-Q3) and before a green one (2021-Q1), the real extract built green. A scripted person settles the pair at 11:00 the next day (contract/scripted_decisions.yaml, "TS-80 settle"): file one by receipt, the test file, rejected; file two, the real extract, the quarter's supply.*

| Where to look | |
|---|---|
| Dataset | cp-clients |
| Supplies | `cp_clients__202011010820000800` |
| Period | 2020-Q4 |
| Set the in-place-on date to | 2020-11-01 |
| Built to | green, the 2020-11-01 08:30 arrival |

## Calendar corrections

### TS-57a - A correction that only re-judges, before it is confirmed

**What it demonstrates.** The quarter reads late, and the correction awaits confirmation with one verdict change (late -> on time) and no moves (REQ-PIPE-168 criteria 3-6).

**What it would look like if the rule were wrong.** Applied on merge with nobody confirming because there were no moves.

*Config: 2015-Q1's date is corrected from 1 to 2 February 2015; its one supply arrives at 12:00 on 2 February - late against the old date, on time against the corrected one.*

| Where to look | |
|---|---|
| Dataset | ed-presentations |
| Supplies | `ed_presentations__201502021200000800` |
| Period | 2015-Q1 |
| Set the in-place-on date to | 2026-09-08 |

### TS-57b - A correction that only re-judges, once confirmed

**What it demonstrates.** A new verdict naming the change reference, on time; the late verdict still readable as history.

**What it would look like if the rule were wrong.** The late verdict overwritten, or no verdict naming the correction.

*Config: as TS-57a.*

| Where to look | |
|---|---|
| Dataset | ed-presentations |
| Supplies | `ed_presentations__201502021200000800` |
| Period | 2015-Q1 |
| Set the in-place-on date to | 2026-09-22 |

### TS-58a - A correction that moves a supply, before it is confirmed

**What it demonstrates.** The correction proposes moving it 2013-Q3 -> 2013-Q4 with its re-judged verdict, and awaits confirmation.

**What it would look like if the rule were wrong.** Moved on merge, or proposed with the verdict computed against 2013-Q3.

*Config: 2013-Q4's date is corrected from 1 November to 20 October 2013. Its supply arrives on 10 October, before the old window opened, so it is filed as a resupply of 2013-Q3; the corrected window covers it.*

| Where to look | |
|---|---|
| Dataset | ed-presentations |
| Supplies | `ed_presentations__201310101000000800` |
| Period | 2013-Q4 |
| Set the in-place-on date to | 2026-09-08 |

### TS-58b - A correction that moves a supply, once confirmed

**What it demonstrates.** Re-filed to 2013-Q4 as a re-file naming the correction, re-QA'd and re-gated, judged against 2013-Q4 (REQ-PIPE-170 criteria 2, 7).

**What it would look like if the rule were wrong.** Left in 2013-Q3, or moved and not re-QA'd.

*Config: as TS-58a.*

| Where to look | |
|---|---|
| Dataset | ed-presentations |
| Supplies | `ed_presentations__201310101000000800` |
| Period | 2013-Q4 |
| Set the in-place-on date to | 2026-09-22 |

### TS-59a - A supply the asset manager will keep, before the correction is confirmed

**What it demonstrates.** The move is proposed like TS-58a's.

**What it would look like if the rule were wrong.** Kept or moved before anyone confirmed.

*Config: as TS-58 for 2014-Q3, corrected from 1 August to 20 July 2014; its supply arrives on 10 July, filed as a resupply of 2014-Q2, which the corrected agreement would move. A scripted confirmation keeps it (contract/scripted_decisions.yaml).*

| Where to look | |
|---|---|
| Dataset | ed-presentations |
| Supplies | `ed_presentations__201407101000000800` |
| Period | 2014-Q3 |
| Set the in-place-on date to | 2026-09-08 |

### TS-59b - A supply the asset manager kept

**What it demonstrates.** The supply stays filed where it is, with a KEPT decision-log entry naming it, its period, the change reference, the actor and the reason, and its verdict judged against the period it stays in (REQ-PIPE-170 criteria 5, 6, 22).

**What it would look like if the rule were wrong.** Moved anyway, kept silently with no reason, or re-judged against the period it did not go to.

*Config: as TS-59a.*

| Where to look | |
|---|---|
| Dataset | ed-presentations |
| Supplies | `ed_presentations__201407101000000800` |
| Period | 2014-Q3 |
| Set the in-place-on date to | 2026-09-22 |

### TS-60a - A correction that leaves a supply with no period, before it is confirmed

**What it demonstrates.** Proposed as "would be held".

**What it would look like if the rule were wrong.** Held, or dropped, before confirmation.

*Config: Emergency Department's first quarter, 2013-Q1, has its date corrected from 1 to 11 February 2013. Its supply arrived on 22 January, inside the old window, before the corrected one opens and with no quarter before it.*

| Where to look | |
|---|---|
| Dataset | ed-presentations |
| Supplies | `ed_presentations__201301221000000800` |
| Period | 2013-Q1 |
| Set the in-place-on date to | 2026-09-08 |

### TS-60b - A supply left with no period, once confirmed

**What it demonstrates.** Held (REQ-PIPE-064), the hold's reason naming the correction.

**What it would look like if the rule were wrong.** Left filed in a period the corrected agreement does not give it, or dropped.

*Config: as TS-60a.*

| Where to look | |
|---|---|
| Dataset | ed-presentations |
| Supplies | `ed_presentations__201301221000000800` |
| Period | 2013-Q1 |
| Set the in-place-on date to | 2026-09-22 |

### TS-61a - A move that will be blocked, before the correction is confirmed

**What it demonstrates.** The move is proposed, naming the period that stands on it.

**What it would look like if the rule were wrong.** Moved out from under the inheriting period.

*Config: 2015-Q3's date is corrected from 1 to 11 August 2015. Its supply arrived on 22 July, which the corrected agreement files to 2015-Q2 - a move blocked because 2015-Q4, the participation gap (REQ-GEN-251), stands on it.*

| Where to look | |
|---|---|
| Dataset | ed-presentations |
| Supplies | `ed_presentations__201507221000000800` |
| Period | 2015-Q3 |
| Set the in-place-on date to | 2026-09-08 |

### TS-61b - A move that is blocked, once confirmed

**What it demonstrates.** Parked as blocked, naming the decision that would unblock it - not moved, not dropped; the correction stays among the states needing action (REQ-PIPE-170 criteria 9, 19).

**What it would look like if the rule were wrong.** Moved, or the correction marked done with the supply silently left.

*Config: as TS-61a.*

| Where to look | |
|---|---|
| Dataset | ed-presentations |
| Supplies | `ed_presentations__201507221000000800` |
| Period | 2015-Q3 |
| Set the in-place-on date to | 2026-09-22 |

### TS-62 - A correction merged and not yet confirmed

**What it demonstrates.** Affected datasets read awaiting confirmation and the correction is listed as needing action; the new arrival is judged against the corrected configuration; REQ-PIPE-173's backstop does NOT go red, because a declared but unapplied correction accounts for the difference (REQ-PIPE-170 criteria 20-21).

**What it would look like if the rule were wrong.** The backstop's "configuration problem on our side" red; or the arrival judged against the old date.

**not injected - nothing to look at yet**

### TS-63a - A dataset turned off for a while: the turn-off

**What it demonstrates.** The late cp_carers files to 2021-Q4, late; 2021-Q4 stays owed until its slot closes (REQ-PIPE-179, REQ-DASH-180).

**What it would look like if the rule were wrong.** The 5 January supply held instead of filed late, or 2021-Q4 going quiet before its slot closes.

*Config: Child Protection, quarterly Feb/May/Aug/Nov, due 09:00 on the 1st, 14-day claim window. cp-carers is turned off after 31 December 2021 by correction REQ-GEN-218 dated 15 December 2021, and owed again from 2022-Q3. 2021-Q4's delivery leaves cp_carers out; cp_carers follows on 5 January 2022, after the turn-off but while 2021-Q4's slot is open.*

| Where to look | |
|---|---|
| Dataset | cp-carers |
| Supplies | `cp_carers__202201051000000800`, `cp_carers__202203151000000800` |
| Period | 2021-Q4 |
| Set the in-place-on date to | 2021-12-20 |

### TS-63b - A dataset turned off for a while: the gap

**What it demonstrates.** The 15 March supply, and each ordinary gap delivery's cp_carers, finds no open owed slot and is held as turned off; 2022-Q1 and 2022-Q2 read owed-nothing and inherit the last promoted supply; from 2022-Q3 it reads as any dataset between deliveries.

**What it would look like if the rule were wrong.** The gap read as missed supplies, or a gap arrival filed into a gap period.

*Config: as TS-63a, with a further cp_carers arriving on 15 March 2022, in the gap. The ordinary deliveries inside the gap still carry the dataset's file, as a supplier still sending files would (REQ-GEN-218 criterion 5).*

| Where to look | |
|---|---|
| Dataset | cp-carers |
| Supplies | `cp_carers__202201051000000800`, `cp_carers__202203151000000800` |
| Period | 2021-Q4 |
| Set the in-place-on date to | 2022-03-20 |

### TS-64 - An undeclared change to a frozen date

**What it demonstrates.** The draft-correction command prints a correction entry for it; committing without one is refused by the pre-commit hook with the same entry, and CI refuses it if the hook was skipped (REQ-PIPE-111, REQ-PIPE-169).

**What it would look like if the rule were wrong.** Committed; or the hook's entry and the command's entry differ.

*unit test - no generated data, nothing to navigate to*

### TS-75a - A supply rejected after it waited - while it waited

Cp-clients, 2024-Q1: the whole delivery on time at 09:00 on 1 February with cp_clients alone built red by its own preset; the other five clean. *Config: quarterly, due 09:00 on the 1st; a person rejects it at 09:00 on 22 February; a corrected cp_clients alone arrives at 10:00 on 29 February.* **Expect** (REQ-DASH-197), on 8 February, in the as-at panel under the results' verdict line: the heading "On Thursday, 8 February 2024 the warehouse did not hold the latest file", the column "Latest arrival by Thursday, 8 February 2024 — not promoted" naming cp-clients@202402010900000800, and the reason "this supply was staged and nobody had decided about it yet". **What the other tables show**: the red clients turned notifications', investigations' and placements' own cross-table checks red, so all three wait for a person on 8 and 25 February; carers waited until 11 February and then promoted green; case workers promoted green on 7 February. When the corrected cp_clients arrives the re-evaluation promotes clients, notifications, investigations and placements green (11 March). **Breaks as**: no panel; or the reason "superseded" (post-build-review #164's reading, which this quarter is placed to avoid).

**What it would look like if the rule were wrong.** No panel; or the reason "superseded" (post-build-review #164's reading, which this quarter is placed to avoid).

*Config: quarterly, due 09:00 on the 1st; a person rejects it at 09:00 on 22 February; a corrected cp_clients alone arrives at 10:00 on 29 February.*

| Where to look | |
|---|---|
| Dataset | cp-clients |
| Supplies | `cp_clients__202402010900000800`, `cp_clients__202402291000000800` |
| Period | 2024-Q1 |
| Set the in-place-on date to | 2024-02-08 |

### TS-75b - A supply rejected after it waited - after it was rejected

The same placement, on 25 February. **Expect** (REQ-DASH-197), in the same panel: "On Sunday, 25 February 2024 the warehouse did not hold the latest file", the same supply, and the reason "a person had rejected this supply, so it was not promoted". The other tables as TS-75a's, carers now promoted. From 29 February the corrected supply fills the quarter and cp-clients ends healthy. **Breaks as**: the panel naming the corrected supply, or still "nobody had decided".

**What it would look like if the rule were wrong.** The panel naming the corrected supply, or still "nobody had decided".

| Where to look | |
|---|---|
| Dataset | cp-clients |
| Supplies | `cp_clients__202402010900000800`, `cp_clients__202402291000000800` |
| Period | 2024-Q1 |
| Set the in-place-on date to | 2024-02-25 |

### TS-76 - A substitution later removed

Cp-placements, 2025-Q1: the delivery leaves cp_placements out; a person substitutes the quarter onto 2024-Q4 at 09:00 on 3 February, and at 09:00 on 20 April - once the next quarter's window has opened - removes the substitution and marks the quarter not supplied, in that order, at one instant. *Config: quarterly, as TS-75a.* **Expect** (REQ-DASH-198), on 17 February: the pill "Substituted from 2024-Q4" beside the dataset's title, and in its drill-down, below the results' heading, "Since removed, as from Sunday, 20 April 2025". The quarter closes "not supplied (accepted)". **What cp-clients and cp-carers read for 2025-Q1** (H1): clients promoted AMBER on arrival and stays amber before, during and after the substitution - the amber is the ordinary one drawn for this quarter, which the delivery keeps (REQ-GEN-199's PROVISIONAL choice); carers waited until 9 February, then promoted GREEN and stays green. Neither is red after the substitution ends: the cross-table checks reading cp_placements are filed under cp-placements, so in a quarter with no placements supply nothing runs them for clients or carers (the architect's H1 expected red; post-build-review #174). **Breaks as**: no pill on 17 February; or "Since replaced".

**What it would look like if the rule were wrong.** No pill on 17 February; or "Since replaced".

| Where to look | |
|---|---|
| Dataset | cp-placements |
| Supplies | — |
| Period | 2025-Q1 |
| Set the in-place-on date to | 2025-02-17 |

### TS-77a - A substitution later replaced - while it stood

Cp-placements, 2023-Q2: the delivery leaves cp_placements out; a person substitutes onto 2023-Q1 at 09:00 on 3 May; cp_placements alone arrives at 10:00 on 8 June and the person promotes it at 10:00 on 9 June, which removes the substitution. *Config: quarterly, as TS-75a.* **Expect** (REQ-DASH-198), on 17 May: the pill "Substituted from 2023-Q1", and in its drill-down "Since replaced, as from Friday, 9 June 2023". **What cp-clients and cp-carers read for 2023-Q2**: both waited on 2 May; clients promoted AMBER (its quarter's drawn amber, kept) on 7 May and carers GREEN on 3 May, and both stay so while the substitution stands, on 8 June and after the promotion. **Breaks as**: no pill; or "Since removed".

**What it would look like if the rule were wrong.** No pill; or "Since removed".

| Where to look | |
|---|---|
| Dataset | cp-placements |
| Supplies | `cp_placements__202306081000000800` |
| Period | 2023-Q2 |
| Set the in-place-on date to | 2023-05-17 |

### TS-77b - Known wrong today (post-build-review #164): A substitution later replaced - the day the late file waited

**What it demonstrates.** Today the as-at panel ("On Thursday, 8 June 2023 the warehouse did not hold the latest file") gives the late supply the reason "this one had been superseded - a newer version had arrived for the same period, a person had set it aside, or a later supply had been promoted into the period - so it was no longer what the period held" - against a period whose holder is a SUBSTITUTED supply, a variant of #164 - while the pill's drill-down reads "Since replaced, as from Friday, 9 June 2023" and "2023-Q2 holds 2023-Q1's supply; the results below are a newer supply awaiting a decision." Once #164 is decided the panel's reason line should say the supply was waiting for a decision. **Breaks as**: a different reason line in the panel means #164 was decided, not a regression; any other change on that date - the drill-down's sentences included - is a regression.

**What it would look like if the rule were wrong.** A different reason line in the panel means #164 was decided, not a regression; any other change on that date - the drill-down's sentences included - is a regression.

| Where to look | |
|---|---|
| Dataset | cp-placements |
| Supplies | `cp_placements__202306081000000800` |
| Period | 2023-Q2 |
| Set the in-place-on date to | 2023-06-08 |

### TS-78a - A supply promoted after a newer one - the day it was promoted

Birth Registrations, 30 August to 2 September 2026, inside the hold era: D's supply amber and held; D+1's green and promoted by the rule; a person promotes D's into D at 20:00 on D+1; D+2's amber and held, promoted by the person at 10:00 on D+3, before D+3's green supply. *Config: daily; the amber setting is HOLD from 2026-08-30 (contract/data-asset.yaml, the version added for this scenario); D to D+3 quiet.* **Expect** (REQ-DASH-197 criterion 6), on 31 August, in the as-at panel: "On Monday, 31 August 2026 the newest file was not the newest promotion", the column "Latest arrival — promoted into Monday, 31 August 2026", and the reason "a supply promoted later into Sunday, 30 August 2026 was what downstream read most recently". **Breaks as**: no panel; or the generic "did not hold the latest file". Depends on the hold era covering 30 August to 1 September; generation refuses, naming TS-78a, if it stops doing so.

**What it would look like if the rule were wrong.** No panel; or the generic "did not hold the latest file". Depends on the hold era covering 30 August to 1 September; generation refuses, naming TS-78a, if it stops doing so.

| Where to look | |
|---|---|
| Dataset | birth-registrations |
| Supplies | `birth_registrations__202608301400000800`, `birth_registrations__202608311400000800`, `birth_registrations__202609011400000800` |
| Period | 2026-08-30 |
| Set the in-place-on date to | 2026-08-31 |
| Built to | amber on registering_parent_1_name.completeness (145 of 1,933), the 2026-08-30 14:00 arrival |
| Built to | green, the 2026-08-31 14:00 arrival |
| Built to | amber on registering_parent_2_name.completeness (625 of 1,933), the 2026-09-01 14:00 arrival |

### TS-78b - A supply promoted after a newer one - the day after

The same placement, on 1 September. **Expect** (REQ-DASH-197 criterion 13), the verdict line above the results: "Awaiting a decision — the results below are the newest supply, received 2:00pm Tuesday, 1 September 2026, which is not in place yet. The supply in place is the one received 2:00pm Sunday, 30 August 2026." - naming D's supply, not D+1's, which is newer by receipt. **Breaks as**: the verdict line naming 31 August's supply as in place.

**What it would look like if the rule were wrong.** The verdict line naming 31 August's supply as in place.

| Where to look | |
|---|---|
| Dataset | birth-registrations |
| Supplies | `birth_registrations__202608301400000800`, `birth_registrations__202608311400000800`, `birth_registrations__202609011400000800` |
| Period | 2026-08-30 |
| Set the in-place-on date to | 2026-09-01 |
| Built to | amber on registering_parent_1_name.completeness (145 of 1,933), the 2026-08-30 14:00 arrival |
| Built to | green, the 2026-08-31 14:00 arrival |
| Built to | amber on registering_parent_2_name.completeness (625 of 1,933), the 2026-09-01 14:00 arrival |

### TS-79a - An inherited quarter - the newest

Cp-case-workers, the newest quarter before the build's own in which it is not delivered (2026-Q2 today), so it inherits the quarter before. Nothing generated; the placement is written after generation from the calendar's participation, in place on the middle of the quarter. *Config: quarterly; cp-case-workers participates only in Q1 and Q3.* **Expect** (REQ-DASH-198): the pill "Inherited from 2026-Q1" beside the dataset's title. The same page also shows an as-at panel and an "Awaiting a decision" verdict line about a May supply that is "not filed to any period": ordinary deliveries carry cp_case_workers in months it does not take part in, and each is held (TS-52's shape) - the pill, not the panel, is what this scenario points at. **Breaks as**: no pill; or a stale date after ANCHOR_DATE moves.

**What it would look like if the rule were wrong.** No pill; or a stale date after ANCHOR_DATE moves.

| Where to look | |
|---|---|
| Dataset | cp-case-workers |
| Supplies | — |
| Period | 2026-Q2 |
| Set the in-place-on date to | 2026-06-16 |

### TS-79b - An inherited quarter - the oldest of the original fifteen

**What it demonstrates.** Its page looks identical to TS-79a's - the pill "Inherited from 2023-Q1". **Breaks as**: no pill.

**What it would look like if the rule were wrong.** No pill.

| Where to look | |
|---|---|
| Dataset | cp-case-workers |
| Supplies | — |
| Period | 2023-Q2 |
| Set the in-place-on date to | 2023-06-16 |


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
    "inPlaceOn": "2026-09-15",
    "subject": "supply-history-row"
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
    "inPlaceOn": "2026-09-11",
    "subject": "supply-history-row"
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
   "demonstrates": "*Config: Emergency Department, the quarterly calendar - the 1st of February, May, August and November, due 09:00, a 14-day claim window, so May 2025's window opens 09:00 on 17 April. February 2025's supply arrived as usual; this one arrives 10:00 on 16 April 2025, a day before May's window opens (REQ-GEN-236).* **Expect** (the first bootstrapped build, 2026-10-18): filed to **2025-Q1** by the branch `resupply-of-open-slot`, classified `late` - May's window has not opened, so February is still the open period, and it is filled. Being a resupply of a filled slot it is **not promoted**: 2025-Q2 is left with no supply, and the next quarter's drift checks fail by the gap rule (REQ-QAC-108), measured against February's supply. **Breaks as**: files to May because it is \"nearly\" May's - the window would then mean nothing. Keeps the family's note: the filled branch is a contained imperfection - a supplier one day early leaves a quarter to be put right by a person - not a defect.",
   "breaksAs": "Files to May because it is \"nearly\" May's - the window would then mean nothing. Keeps the family's note: the filled branch is a contained imperfection - a supplier one day early leaves a quarter to be put right by a person - not a defect.",
   "config": "Config: Emergency Department, the quarterly calendar - the 1st of February, May, August and November, due 09:00, a 14-day claim window, so May 2025's window opens 09:00 on 17 April. February 2025's supply arrived as usual; this one arrives 10:00 on 16 April 2025, a day before May's window opens (REQ-GEN-236).",
   "requirements": [
    "REQ-GEN-236",
    "REQ-QAC-108"
   ],
   "coordinates": {
    "dataset": "ed-presentations",
    "supplies": [
     "ed_presentations__202504161000000800"
    ],
    "period": "2025-Q2",
    "inPlaceOn": "2025-05-01",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-3b",
   "mode": "INJECT",
   "title": "Quarterly, prior slot UNFILLED",
   "section": "Slot assignment",
   "demonstrates": "*Same config, on Emergency Department, a year later: February 2026's supply never came (suppressed), and May's arrives 10:00 on 16 April 2026, a day before its window opens.* **Expect** (the first bootstrapped build, 2026-10-18): filed to **2026-Q1** by the branch `open-slot-unfilled`, classified `late` - about 74 days - because February is still the open period and nothing filled it. 2026-Q2 is left with no supply. **Breaks as**: files to May and leaves February owed for ever.",
   "breaksAs": "Files to May and leaves February owed for ever.",
   "config": null,
   "requirements": [],
   "coordinates": {
    "dataset": "ed-presentations",
    "supplies": [
     "ed_presentations__202604161000000800"
    ],
    "period": "2026-Q2",
    "inPlaceOn": "2026-05-01",
    "subject": "supply-history-row"
   }
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
   "coordinates": {
    "dataset": "birth-registrations",
    "supplies": [
     "birth_registrations__202606212100000800",
     "birth_registrations__202606221700000800"
    ],
    "period": "2026-06-22",
    "inPlaceOn": "2026-06-22",
    "subject": "supply-history-row"
   }
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
   "coordinates": {
    "dataset": "birth-registrations",
    "supplies": [
     "birth_registrations__202606251700000800"
    ],
    "period": "2026-06-25",
    "inPlaceOn": "2026-06-25",
    "subject": "supply-history-row"
   }
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
    "inPlaceOn": "2026-09-15",
    "subject": "supply-history-row"
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
    "REQ-PIPE-131",
    "REQ-GEN-195"
   ],
   "coordinates": {
    "dataset": "cp-clients",
    "supplies": [
     "cp_clients__202404221000000800"
    ],
    "period": "2024-Q2",
    "inPlaceOn": "2024-05-01",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-10a",
   "mode": "INJECT",
   "title": "Evening-before daily arrival, Monday filled",
   "section": "Arrival classification",
   "demonstrates": "The 22:00 arrival fills **Tuesday, on time**.",
   "breaksAs": null,
   "config": "Config: daily, Tuesday's supply due 22:00 MONDAY, claim window 4 hours - so Tuesday's window opens 18:00 Monday, and Monday closes then.",
   "requirements": [],
   "coordinates": {
    "dataset": "birth-registrations",
    "supplies": [
     "birth_registrations__202606192200000800"
    ],
    "period": "2026-06-20",
    "inPlaceOn": "2026-06-20",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-10b",
   "mode": "INJECT",
   "title": "Evening-before daily arrival, Monday unfilled",
   "section": "Arrival classification",
   "demonstrates": "The 22:00 arrival ALSO fills **Tuesday, on time**, and Monday closes with no supply. **Changed 2026-10-04 by REQ-PIPE-131**: this variant used to file Monday, late - slot state decided between two answers. Keith's worked consequence: Monday's file arriving after Tuesday's claim window opened is filed as Tuesday's; Monday closes empty, visibly, and Tuesday's real file then supersedes it (REQ-PIPE-118), replaces it (REQ-PIPE-123), or waits for a person. The cutoff still lives in `due_at` and the claim window, not in code.",
   "breaksAs": null,
   "config": null,
   "requirements": [
    "REQ-PIPE-131",
    "REQ-PIPE-118",
    "REQ-PIPE-123"
   ],
   "coordinates": {
    "dataset": "birth-registrations",
    "supplies": [
     "birth_registrations__202606272200000800"
    ],
    "period": "2026-06-28",
    "inPlaceOn": "2026-06-28",
    "subject": "supply-history-row"
   }
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
     "cp_clients__202505010900000800",
     "cp_clients__202505291000000800"
    ],
    "period": "2025-Q2",
    "inPlaceOn": "2025-05-02",
    "subject": "supply-history-row"
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
   "demonstrates": "It arrives as **its own delivery** and triggers QA. Its slot is clients' own August slot - per-table slot sequences mean there is no \"resupply of table X within delivery Y\" concept to implement; it is just clients' August supply, arriving late. The previously blocked cross-table check now runs. If green, clients promotes and August's slot fills. The recorded QA history keeps **both** runs - the period's current state is the latest, its history is all of them. Clients arriving also re-evaluates the waiting placements' reading checks and re-gates them (REQ-PIPE-121). *Used to say* `qa_results/` kept both runs - REQ-PIPE-089 moved the history into the database. *In the data since 2026-10-15 (REQ-GEN-044 criterion 1)*, riding TS-12's placement: TS-12's cp_clients is refused in 2025-Q2, and the corrected cp_clients arrives alone 28 days later, 10:00 on 2025-05-29, filed to 2025-Q2's still-empty slot. TS-12's link sits between the two; TS-14's lands on the correction's day.",
   "breaksAs": null,
   "config": null,
   "requirements": [
    "REQ-PIPE-121",
    "REQ-PIPE-089",
    "REQ-GEN-044"
   ],
   "coordinates": {
    "dataset": "cp-clients",
    "supplies": [
     "cp_clients__202505010900000800",
     "cp_clients__202505291000000800"
    ],
    "period": "2025-Q2",
    "inPlaceOn": "2025-05-29",
    "subject": "supply-history-row"
   }
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
   "requirements": [
    "REQ-PIPE-202"
   ],
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
    "inPlaceOn": "2026-02-01",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-39",
   "mode": "unit",
   "title": "A split extract, once patterns are regexes",
   "section": "Timestamps",
   "demonstrates": "A duplicate match, so the dataset is HELD (TS-34's machinery), not a silent choice between them. Verified 2026-09-24 that under today's `keyPattern` reuse this is NOT reachable for Child Protection - `cp/{delivery_id}/cp_clients.csv` reduces to `^cp_clients\\.csv$`, so `part2` matches nothing and falls out as unrecognised instead, which is the TS-38 shape. Reachable for Birth Registrations only because its pattern carries a `{date}` placeholder. This scenario is what proves the regex change (`REQ-PIPE-058`, 2026-09-24) actually closed the gap. NOW REACHABLE for `cp_clients` (REQ-PIPE-202, 2026-10-15): its pattern is `cp_clients(_[^/]+)?\\.csv`, so `cp_clients_part2.csv` matches and the pair is held as contested - `tests/test_holds.py::test_ts39_a_second_part_beside_the_extract_is_contested`. Every other Child Protection pattern is still an exact filename.",
   "breaksAs": null,
   "config": null,
   "requirements": [
    "REQ-PIPE-058",
    "REQ-PIPE-202"
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
    "inPlaceOn": "2026-09-15",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-42a",
   "mode": "INJECT",
   "title": "A contested pair of one Child Protection table, while it is contested",
   "section": "The option A and period-closing batch, planted (REQ-GEN-136, REQ-GEN-137)",
   "demonstrates": "PLANTED by REQ-GEN-203 (2026-10-18) in a grown quarter (REQ-GEN-207), after REQ-PIPE-202 widened `cp_clients`' pattern so two of its files in one delivery contest the table; `tests/test_cp_pair.py` drives the shape through the real orchestrator. Two lettered siblings share the one placement (REQ-GEN-201): this one's link opens on the pair's arrival day. *Config: quarterly, Feb/May/Aug/Nov, due 09:00 on the 1st, claim window 14 days. 2019-Q4's delivery carries the usual files and two Client Registers - cp_clients.csv at 08:30 and a re-export, cp_clients_v2.csv, at 08:40 whose rows differ (each re-pulled an hour later) - both before due; a clean cp_clients.csv follows alone on 29 November at 10:00, after due and before 2020-Q1's window opens, built green (REQ-GEN-184) after one green lead-in quarter (2019-Q3) and before a green one (2020-Q1).* **Breaks as**: one of the two files taken as the quarter's supply, or the three readers' cross-table checks evaluated against either.",
   "breaksAs": "One of the two files taken as the quarter's supply, or the three readers' cross-table checks evaluated against either.",
   "config": "Config: quarterly, Feb/May/Aug/Nov, due 09:00 on the 1st, claim window 14 days. 2019-Q4's delivery carries the usual files and two Client Registers - cp_clients.csv at 08:30 and a re-export, cp_clients_v2.csv, at 08:40 whose rows differ (each re-pulled an hour later) - both before due; a clean cp_clients.csv follows alone on 29 November at 10:00, after due and before 2020-Q1's window opens, built green (REQ-GEN-184) after one green lead-in quarter (2019-Q3) and before a green one (2020-Q1).",
   "requirements": [
    "REQ-GEN-184",
    "REQ-GEN-203",
    "REQ-GEN-207",
    "REQ-PIPE-202",
    "REQ-GEN-201"
   ],
   "coordinates": {
    "dataset": "cp-clients",
    "supplies": [
     "cp_clients__201911010830000800",
     "cp_clients__201911291000000800"
    ],
    "period": "2019-Q4",
    "inPlaceOn": "2019-11-01",
    "targets": [
     {
      "date": "2019-11-29",
      "at": "10:00",
      "built_to": "green",
      "rules": [],
      "moved": []
     }
    ],
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-42b",
   "mode": "INJECT",
   "title": "A contested pair of one Child Protection table, resolved by a later file",
   "section": "The option A and period-closing batch, planted (REQ-GEN-136, REQ-GEN-137)",
   "demonstrates": "TS-42a's placement; this link opens on the later file's asset day. *Config: as TS-42a.* **Breaks as**: the pair still contested after the later file, or the later file filed as a resupply rather than ending the contest.",
   "breaksAs": "The pair still contested after the later file, or the later file filed as a resupply rather than ending the contest.",
   "config": "Config: as TS-42a.",
   "requirements": [],
   "coordinates": {
    "dataset": "cp-clients",
    "supplies": [
     "cp_clients__201911010830000800",
     "cp_clients__201911291000000800"
    ],
    "period": "2019-Q4",
    "inPlaceOn": "2019-11-29",
    "targets": [
     {
      "date": "2019-11-29",
      "at": "10:00",
      "built_to": "green",
      "rules": [],
      "moved": []
     }
    ],
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-43",
   "mode": "INJECT",
   "title": "An amber supply held under hold",
   "section": "The option A and period-closing batch, planted (REQ-GEN-136, REQ-GEN-137)",
   "demonstrates": "The amber supply is not promoted; the rule records a promotion-withheld note naming the setting, and the slot reads amber, waiting for a person (REQ-PIPE-122).",
   "breaksAs": "It promotes itself, as it would under promote.",
   "config": "Config: daily; the amber setting is HOLD from 2026-08-30 (TS-78's version, REQ-GEN-199); a scripted promotion at 10:00 the next morning.",
   "requirements": [
    "REQ-GEN-199",
    "REQ-PIPE-122",
    "REQ-GEN-184",
    "REQ-GEN-185"
   ],
   "coordinates": {
    "dataset": "birth-registrations",
    "supplies": [
     "birth_registrations__202609051400000800"
    ],
    "period": "2026-09-05",
    "inPlaceOn": "2026-09-05",
    "targets": [
     {
      "date": "2026-09-05",
      "at": "14:00",
      "built_to": "amber",
      "rules": [
       "place_of_birth_facility.completeness"
      ],
      "moved": [
       {
        "rule": "registering_parent_2_name.completeness",
        "to": "green",
        "nulls": 495,
        "of_rows": 1933
       },
       {
        "rule": "place_of_birth_facility.completeness",
        "to": "amber",
        "nulls": 445,
        "of_rows": 1933,
        "was": 46
       }
      ]
     }
    ],
    "subject": "supply-history-row"
   }
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
    "REQ-PIPE-122",
    "REQ-GEN-184"
   ],
   "coordinates": {
    "dataset": "birth-registrations",
    "supplies": [
     "birth_registrations__202609131400000800"
    ],
    "period": "2026-09-13",
    "inPlaceOn": "2026-09-13",
    "targets": [
     {
      "date": "2026-09-13",
      "at": "14:00",
      "built_to": "amber",
      "rules": [
       "registering_parent_1_name.completeness"
      ],
      "moved": [
       {
        "rule": "registering_parent_2_name.completeness",
        "to": "green",
        "nulls": 495,
        "of_rows": 1993
       },
       {
        "rule": "registering_parent_1_name.completeness",
        "to": "amber",
        "nulls": 145,
        "of_rows": 1993,
        "was": 49
       }
      ]
     }
    ],
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-45",
   "mode": "INJECT",
   "title": "The same, acknowledged by a person",
   "section": "The option A and period-closing batch, planted (REQ-GEN-136, REQ-GEN-137)",
   "demonstrates": "Beside TS-44's, this one reads acknowledged, by the person, with their reason (REQ-PIPE-122, REQ-GEN-137 criterion 4).",
   "breaksAs": "The acknowledgement refused, or written outside the decision path.",
   "config": "Config: as TS-44; a scripted acknowledgement five hours after receipt, once the rule has promoted it.",
   "requirements": [
    "REQ-PIPE-122",
    "REQ-GEN-137",
    "REQ-GEN-184"
   ],
   "coordinates": {
    "dataset": "birth-registrations",
    "supplies": [
     "birth_registrations__202609171400000800"
    ],
    "period": "2026-09-17",
    "inPlaceOn": "2026-09-17",
    "targets": [
     {
      "date": "2026-09-17",
      "at": "14:00",
      "built_to": "amber",
      "rules": [
       "registering_parent_2_name.completeness"
      ],
      "moved": [
       {
        "rule": "registering_parent_2_name.completeness",
        "to": "amber",
        "nulls": 625,
        "of_rows": 2119,
        "was": 576
       }
      ]
     }
    ],
    "subject": "supply-history-row"
   }
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
    "REQ-DASH-127",
    "REQ-GEN-184",
    "REQ-GEN-185"
   ],
   "coordinates": {
    "dataset": "birth-registrations",
    "supplies": [
     "birth_registrations__202609211400000800",
     "birth_registrations__202609211600000800"
    ],
    "period": "2026-09-21",
    "inPlaceOn": "2026-09-21",
    "targets": [
     {
      "date": "2026-09-21",
      "at": "14:00",
      "built_to": "green",
      "rules": [],
      "moved": [
       {
        "rule": "registering_parent_2_name.completeness",
        "to": "green",
        "nulls": 495,
        "of_rows": 2119
       }
      ]
     },
     {
      "date": "2026-09-21",
      "at": "16:00",
      "built_to": "green",
      "rules": [],
      "moved": [
       {
        "rule": "registering_parent_2_name.completeness",
        "to": "green",
        "nulls": 495,
        "of_rows": 2119
       }
      ]
     }
    ],
    "subject": "supply-history-row"
   }
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
    "inPlaceOn": "2026-09-08",
    "subject": "supply-history-row"
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
   "demonstrates": "In the data since 2026-10-15 (REQ-GEN-044 criterion 1; Keith, 2026-10-14, Q13): demonstrated by TS-76's placement - cp-placements' 2025-Q1 substituted by a scripted person onto 2024-Q4, whose cp-placements supply was promoted green - with its own link while the substitution stands. CORRECTED 2026-10-16 (post-build-review #207 D1): REQ-GEN-207 moved the ordinary amber drawn for 2026-Q3 to 2024-Q4 and this entry then said \"promoted amber\", but that amber dirties only cp_carers and cp_clients, so cp-placements' 2024-Q4 supply is still green and promoted. Whether it should be amber is with Keith. The script's `stands_on` field (REQ-GEN-200) answered the old blocker.",
   "breaksAs": null,
   "config": null,
   "requirements": [
    "REQ-GEN-044",
    "REQ-GEN-207",
    "REQ-GEN-200"
   ],
   "coordinates": {
    "dataset": "cp-placements",
    "supplies": [],
    "period": "2025-Q1",
    "inPlaceOn": "2025-02-17",
    "subject": "substitution-drill-down"
   }
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
    "REQ-GEN-044",
    "REQ-GEN-207"
   ],
   "coordinates": {
    "dataset": "cp-carers",
    "supplies": [
     "cp_carers__202608010900000800"
    ],
    "period": "2026-Q3",
    "inPlaceOn": "2026-08-01",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-57a",
   "mode": "INJECT",
   "title": "A correction that only re-judges, before it is confirmed",
   "section": "Calendar corrections",
   "demonstrates": "The quarter reads late, and the correction awaits confirmation with one verdict change (late -> on time) and no moves (REQ-PIPE-168 criteria 3-6).",
   "breaksAs": "Applied on merge with nobody confirming because there were no moves.",
   "config": "Config: 2015-Q1's date is corrected from 1 to 2 February 2015; its one supply arrives at 12:00 on 2 February - late against the old date, on time against the corrected one.",
   "requirements": [
    "REQ-PIPE-168"
   ],
   "coordinates": {
    "dataset": "ed-presentations",
    "supplies": [
     "ed_presentations__201502021200000800"
    ],
    "period": "2015-Q1",
    "inPlaceOn": "2026-09-08",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-57b",
   "mode": "INJECT",
   "title": "A correction that only re-judges, once confirmed",
   "section": "Calendar corrections",
   "demonstrates": "A new verdict naming the change reference, on time; the late verdict still readable as history.",
   "breaksAs": "The late verdict overwritten, or no verdict naming the correction.",
   "config": "Config: as TS-57a.",
   "requirements": [],
   "coordinates": {
    "dataset": "ed-presentations",
    "supplies": [
     "ed_presentations__201502021200000800"
    ],
    "period": "2015-Q1",
    "inPlaceOn": "2026-09-22",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-58a",
   "mode": "INJECT",
   "title": "A correction that moves a supply, before it is confirmed",
   "section": "Calendar corrections",
   "demonstrates": "The correction proposes moving it 2013-Q3 -> 2013-Q4 with its re-judged verdict, and awaits confirmation.",
   "breaksAs": "Moved on merge, or proposed with the verdict computed against 2013-Q3.",
   "config": "Config: 2013-Q4's date is corrected from 1 November to 20 October 2013. Its supply arrives on 10 October, before the old window opened, so it is filed as a resupply of 2013-Q3; the corrected window covers it.",
   "requirements": [],
   "coordinates": {
    "dataset": "ed-presentations",
    "supplies": [
     "ed_presentations__201310101000000800"
    ],
    "period": "2013-Q4",
    "inPlaceOn": "2026-09-08",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-58b",
   "mode": "INJECT",
   "title": "A correction that moves a supply, once confirmed",
   "section": "Calendar corrections",
   "demonstrates": "Re-filed to 2013-Q4 as a re-file naming the correction, re-QA'd and re-gated, judged against 2013-Q4 (REQ-PIPE-170 criteria 2, 7).",
   "breaksAs": "Left in 2013-Q3, or moved and not re-QA'd.",
   "config": "Config: as TS-58a.",
   "requirements": [
    "REQ-PIPE-170"
   ],
   "coordinates": {
    "dataset": "ed-presentations",
    "supplies": [
     "ed_presentations__201310101000000800"
    ],
    "period": "2013-Q4",
    "inPlaceOn": "2026-09-22",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-59a",
   "mode": "INJECT",
   "title": "A supply the asset manager will keep, before the correction is confirmed",
   "section": "Calendar corrections",
   "demonstrates": "The move is proposed like TS-58a's.",
   "breaksAs": "Kept or moved before anyone confirmed.",
   "config": "Config: as TS-58 for 2014-Q3, corrected from 1 August to 20 July 2014; its supply arrives on 10 July, filed as a resupply of 2014-Q2, which the corrected agreement would move. A scripted confirmation keeps it (contract/scripted_decisions.yaml).",
   "requirements": [],
   "coordinates": {
    "dataset": "ed-presentations",
    "supplies": [
     "ed_presentations__201407101000000800"
    ],
    "period": "2014-Q3",
    "inPlaceOn": "2026-09-08",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-59b",
   "mode": "INJECT",
   "title": "A supply the asset manager kept",
   "section": "Calendar corrections",
   "demonstrates": "The supply stays filed where it is, with a KEPT decision-log entry naming it, its period, the change reference, the actor and the reason, and its verdict judged against the period it stays in (REQ-PIPE-170 criteria 5, 6, 22).",
   "breaksAs": "Moved anyway, kept silently with no reason, or re-judged against the period it did not go to.",
   "config": "Config: as TS-59a.",
   "requirements": [
    "REQ-PIPE-170"
   ],
   "coordinates": {
    "dataset": "ed-presentations",
    "supplies": [
     "ed_presentations__201407101000000800"
    ],
    "period": "2014-Q3",
    "inPlaceOn": "2026-09-22",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-60a",
   "mode": "INJECT",
   "title": "A correction that leaves a supply with no period, before it is confirmed",
   "section": "Calendar corrections",
   "demonstrates": "Proposed as \"would be held\".",
   "breaksAs": "Held, or dropped, before confirmation.",
   "config": "Config: Emergency Department's first quarter, 2013-Q1, has its date corrected from 1 to 11 February 2013. Its supply arrived on 22 January, inside the old window, before the corrected one opens and with no quarter before it.",
   "requirements": [],
   "coordinates": {
    "dataset": "ed-presentations",
    "supplies": [
     "ed_presentations__201301221000000800"
    ],
    "period": "2013-Q1",
    "inPlaceOn": "2026-09-08",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-60b",
   "mode": "INJECT",
   "title": "A supply left with no period, once confirmed",
   "section": "Calendar corrections",
   "demonstrates": "Held (REQ-PIPE-064), the hold's reason naming the correction.",
   "breaksAs": "Left filed in a period the corrected agreement does not give it, or dropped.",
   "config": "Config: as TS-60a.",
   "requirements": [
    "REQ-PIPE-064"
   ],
   "coordinates": {
    "dataset": "ed-presentations",
    "supplies": [
     "ed_presentations__201301221000000800"
    ],
    "period": "2013-Q1",
    "inPlaceOn": "2026-09-22",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-61a",
   "mode": "INJECT",
   "title": "A move that will be blocked, before the correction is confirmed",
   "section": "Calendar corrections",
   "demonstrates": "The move is proposed, naming the period that stands on it.",
   "breaksAs": "Moved out from under the inheriting period.",
   "config": "Config: 2015-Q3's date is corrected from 1 to 11 August 2015. Its supply arrived on 22 July, which the corrected agreement files to 2015-Q2 - a move blocked because 2015-Q4, the participation gap (REQ-GEN-251), stands on it.",
   "requirements": [
    "REQ-GEN-251"
   ],
   "coordinates": {
    "dataset": "ed-presentations",
    "supplies": [
     "ed_presentations__201507221000000800"
    ],
    "period": "2015-Q3",
    "inPlaceOn": "2026-09-08",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-61b",
   "mode": "INJECT",
   "title": "A move that is blocked, once confirmed",
   "section": "Calendar corrections",
   "demonstrates": "Parked as blocked, naming the decision that would unblock it - not moved, not dropped; the correction stays among the states needing action (REQ-PIPE-170 criteria 9, 19).",
   "breaksAs": "Moved, or the correction marked done with the supply silently left.",
   "config": "Config: as TS-61a.",
   "requirements": [
    "REQ-PIPE-170"
   ],
   "coordinates": {
    "dataset": "ed-presentations",
    "supplies": [
     "ed_presentations__201507221000000800"
    ],
    "period": "2015-Q3",
    "inPlaceOn": "2026-09-22",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-62",
   "mode": "INJECT",
   "title": "A correction merged and not yet confirmed",
   "section": "Calendar corrections",
   "demonstrates": "Affected datasets read awaiting confirmation and the correction is listed as needing action; the new arrival is judged against the corrected configuration; REQ-PIPE-173's backstop does NOT go red, because a declared but unapplied correction accounts for the difference (REQ-PIPE-170 criteria 20-21).",
   "breaksAs": "The backstop's \"configuration problem on our side\" red; or the arrival judged against the old date.",
   "config": null,
   "requirements": [
    "REQ-PIPE-173",
    "REQ-PIPE-170"
   ],
   "coordinates": null
  },
  {
   "id": "TS-63a",
   "mode": "INJECT",
   "title": "A dataset turned off for a while: the turn-off",
   "section": "Calendar corrections",
   "demonstrates": "The late cp_carers files to 2021-Q4, late; 2021-Q4 stays owed until its slot closes (REQ-PIPE-179, REQ-DASH-180).",
   "breaksAs": "The 5 January supply held instead of filed late, or 2021-Q4 going quiet before its slot closes.",
   "config": "Config: Child Protection, quarterly Feb/May/Aug/Nov, due 09:00 on the 1st, 14-day claim window. cp-carers is turned off after 31 December 2021 by correction REQ-GEN-218 dated 15 December 2021, and owed again from 2022-Q3. 2021-Q4's delivery leaves cp_carers out; cp_carers follows on 5 January 2022, after the turn-off but while 2021-Q4's slot is open.",
   "requirements": [
    "REQ-GEN-218",
    "REQ-PIPE-179",
    "REQ-DASH-180"
   ],
   "coordinates": {
    "dataset": "cp-carers",
    "supplies": [
     "cp_carers__202201051000000800",
     "cp_carers__202203151000000800"
    ],
    "period": "2021-Q4",
    "inPlaceOn": "2021-12-20",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-63b",
   "mode": "INJECT",
   "title": "A dataset turned off for a while: the gap",
   "section": "Calendar corrections",
   "demonstrates": "The 15 March supply, and each ordinary gap delivery's cp_carers, finds no open owed slot and is held as turned off; 2022-Q1 and 2022-Q2 read owed-nothing and inherit the last promoted supply; from 2022-Q3 it reads as any dataset between deliveries.",
   "breaksAs": "The gap read as missed supplies, or a gap arrival filed into a gap period.",
   "config": "Config: as TS-63a, with a further cp_carers arriving on 15 March 2022, in the gap. The ordinary deliveries inside the gap still carry the dataset's file, as a supplier still sending files would (REQ-GEN-218 criterion 5).",
   "requirements": [
    "REQ-GEN-218"
   ],
   "coordinates": {
    "dataset": "cp-carers",
    "supplies": [
     "cp_carers__202201051000000800",
     "cp_carers__202203151000000800"
    ],
    "period": "2021-Q4",
    "inPlaceOn": "2022-03-20",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-64",
   "mode": "unit",
   "title": "An undeclared change to a frozen date",
   "section": "Calendar corrections",
   "demonstrates": "The draft-correction command prints a correction entry for it; committing without one is refused by the pre-commit hook with the same entry, and CI refuses it if the hook was skipped (REQ-PIPE-111, REQ-PIPE-169).",
   "breaksAs": "Committed; or the hook's entry and the command's entry differ.",
   "config": null,
   "requirements": [
    "REQ-PIPE-111",
    "REQ-PIPE-169"
   ],
   "coordinates": null
  },
  {
   "id": "TS-65",
   "mode": "INJECT",
   "title": "Early, at the edge of the window",
   "section": "Arrival classification",
   "demonstrates": "Assigned **2025-Q3** and classified **early by 13 days**, exactly as TS-9 - the window is a boundary, and a supply inside it by a day is as early-and-fine as one inside it by a week (REQ-PIPE-131).",
   "breaksAs": "Treated as a resupply of 2025-Q2, as if the window counted from somewhere else.",
   "config": "Config: as TS-9 - Child Protection, quarterly, due 09:00 on the 1st, claim window 14 days. 2025-Q3 (1 August) arrives 19 July at 10:00, thirteen days early, a day after its window opened at 09:00 on 18 July.",
   "requirements": [
    "REQ-PIPE-131"
   ],
   "coordinates": {
    "dataset": "cp-clients",
    "supplies": [
     "cp_clients__202507191000000800"
    ],
    "period": "2025-Q3",
    "inPlaceOn": "2025-08-01",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-66",
   "mode": "INJECT",
   "title": "A couple of days early - the everyday case",
   "section": "Arrival classification",
   "demonstrates": "Assigned **2025-Q4**, classified **early by 2 days**, and otherwise unremarkable - it fills and promotes like an on-time supply.",
   "breaksAs": "Shown as anything more alarming than early.",
   "config": "Config: as TS-9. 2025-Q4 (1 November) arrives 30 October at 10:00.",
   "requirements": [],
   "coordinates": {
    "dataset": "cp-clients",
    "supplies": [
     "cp_clients__202510301000000800"
    ],
    "period": "2025-Q4",
    "inPlaceOn": "2025-11-01",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-67",
   "mode": "INJECT",
   "title": "A quarterly supply sent too early",
   "section": "Arrival classification",
   "demonstrates": "It cannot claim 2023-Q4, whose window has not opened - nothing claims forward (REQ-PIPE-062 criterion 5). The open period when it arrives is 2023-Q3, so it files there as a **resupply of 2023-Q3** (REQ-PIPE-131), and the rule refuses to promote it over 2023-Q3's accepted supply. Then a PERSON re-files it to 2023-Q4 (a scripted decision, REQ-GEN-135, at 10:00 on 21 October, once Q4's window is open), so 2023-Q4 is not left with no supply. Keith, 2026-10-12: \"plus one too early\" - the case people will ask about - and \"have it refiled to Q4 by a synthetic human making a decision\".",
   "breaksAs": "Assigned 2023-Q4 by the RULE because it was obviously meant for it; or 2023-Q4 left empty once the person has re-filed it.",
   "config": "Config: as TS-9. 2023-Q4 (1 November) is due 09:00 that day and its window opens 09:00 on 18 October; the supply arrives 12 October at 10:00, twenty days early and six days before the window. 2023-Q3, before it, is an ordinary quarter whose own supply has arrived.",
   "requirements": [
    "REQ-PIPE-062",
    "REQ-PIPE-131",
    "REQ-GEN-135"
   ],
   "coordinates": {
    "dataset": "cp-clients",
    "supplies": [
     "cp_clients__202310121000000800"
    ],
    "period": "2023-Q4",
    "inPlaceOn": "2023-11-01",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-68",
   "mode": "INJECT",
   "title": "A duplicate send",
   "section": "Arrival classification",
   "demonstrates": "File one D's supply, early and promoted; file two kept but superseded. **Breaks as**: the duplicate, sorting first, taken as file one - the staged ordinal and the supply ordinal disagreeing.",
   "breaksAs": "The duplicate, sorting first, taken as file one - the staged ordinal and the supply ordinal disagreeing.",
   "config": null,
   "requirements": [],
   "coordinates": {
    "dataset": "birth-registrations",
    "supplies": [
     "birth_registrations__202607281340000800"
    ],
    "period": "2026-07-28",
    "inPlaceOn": "2026-07-28",
    "targets": [
     {
      "date": "2026-07-28",
      "at": "13:40",
      "delivery": "BDM_20260728",
      "filename": "birth_registrations_2026-07-28.csv",
      "day": "2026-07-28",
      "built_to": "green",
      "rules": [],
      "moved": []
     }
    ],
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-69",
   "mode": "INJECT",
   "title": "Tomorrow's file sent early with today's",
   "section": "Arrival classification",
   "demonstrates": "File one D's supply; file two re-filed to D+1, checked there, and D+1's only supply. **Breaks as**: D+1 left with no supply, or the re-filed file checked against D.",
   "breaksAs": "D+1 left with no supply, or the re-filed file checked against D.",
   "config": null,
   "requirements": [],
   "coordinates": {
    "dataset": "birth-registrations",
    "supplies": [
     "birth_registrations__202608021330000800"
    ],
    "period": "2026-08-02",
    "inPlaceOn": "2026-08-02",
    "targets": [
     {
      "date": "2026-08-02",
      "at": "13:30",
      "delivery": "DCP_20260802",
      "filename": "birth_registrations_2026-08-02.csv",
      "day": "2026-08-02",
      "built_to": "green",
      "rules": [],
      "moved": []
     },
     {
      "date": "2026-08-02",
      "at": "13:45",
      "delivery": "DCP_20260802",
      "filename": "birth_registrations_2026-08-03.csv",
      "day": "2026-08-03",
      "built_to": "green",
      "rules": [],
      "moved": [
       {
        "rule": "registering_parent_2_name.completeness",
        "to": "green",
        "nulls": 476,
        "of_rows": 1764
       }
      ]
     }
    ],
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-70",
   "mode": "INJECT",
   "title": "A faulty file and its corrected re-export",
   "section": "Arrival classification",
   "demonstrates": "File one rejected; file two D's supply, its own receipt taken, so D reads **late**, 4:30pm; no hold; D+1 unaffected. **Breaks as**: D read early from file one's receipt.",
   "breaksAs": "D read early from file one's receipt.",
   "config": null,
   "requirements": [],
   "coordinates": {
    "dataset": "birth-registrations",
    "supplies": [
     "birth_registrations__202608071340000800"
    ],
    "period": "2026-08-07",
    "inPlaceOn": "2026-08-07",
    "targets": [
     {
      "date": "2026-08-07",
      "at": "16:30",
      "delivery": "REG_20260807",
      "filename": "birth_registrations_2026-08-07-resend.csv",
      "day": "2026-08-07",
      "built_to": "green",
      "rules": [],
      "moved": [
       {
        "rule": "registering_parent_2_name.completeness",
        "to": "green",
        "nulls": 495,
        "of_rows": 2053
       }
      ]
     }
    ],
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-71",
   "mode": "INJECT",
   "title": "A stray test file that loads",
   "section": "Arrival classification",
   "demonstrates": "The test file rejected; the real one D's supply, early. **Breaks as**: the test rows checked as D's supply.",
   "breaksAs": "The test rows checked as D's supply.",
   "config": null,
   "requirements": [],
   "coordinates": {
    "dataset": "birth-registrations",
    "supplies": [
     "birth_registrations__202608121320000800"
    ],
    "period": "2026-08-12",
    "inPlaceOn": "2026-08-12",
    "targets": [
     {
      "date": "2026-08-12",
      "at": "13:40",
      "delivery": "daily_extract_aug2026",
      "filename": "birth_registrations_2026-08-12.csv",
      "day": "2026-08-12",
      "built_to": "green",
      "rules": [],
      "moved": [
       {
        "rule": "registering_parent_2_name.completeness",
        "to": "green",
        "nulls": 495,
        "of_rows": 2053
       }
      ]
     }
    ],
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-72",
   "mode": "INJECT",
   "title": "A stray test file the load refuses",
   "section": "Arrival classification",
   "demonstrates": "The test file offered only \"rejected\", named as never loaded; the real file D's supply, checked by the real tools, early and promoted, and the refused file marked as never loaded. **Breaks as**: the real file named as the one that never loaded.",
   "breaksAs": "The real file named as the one that never loaded.",
   "config": null,
   "requirements": [],
   "coordinates": {
    "dataset": "birth-registrations",
    "supplies": [
     "birth_registrations__202608171330000800"
    ],
    "period": "2026-08-17",
    "inPlaceOn": "2026-08-17",
    "targets": [
     {
      "date": "2026-08-17",
      "at": "13:30",
      "delivery": "send-4449",
      "filename": "birth_registrations_2026-08-17.csv",
      "day": "2026-08-17",
      "built_to": "green",
      "rules": [],
      "moved": [
       {
        "rule": "registering_parent_2_name.completeness",
        "to": "green",
        "nulls": 495,
        "of_rows": 2073
       }
      ]
     }
    ],
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-73",
   "mode": "INJECT",
   "title": "Reject both",
   "section": "Arrival classification",
   "demonstrates": "Each file's rejection its own entry, no QA, nothing promoted, D left owed and unfilled with no mark-not-supplied and no later supply. **Breaks as**: D read as supplied, or not-supplied by a person.",
   "breaksAs": "D read as supplied, or not-supplied by a person.",
   "config": null,
   "requirements": [],
   "coordinates": {
    "dataset": "birth-registrations",
    "supplies": [
     "birth_registrations__202608211320000800"
    ],
    "period": "2026-08-21",
    "inPlaceOn": "2026-08-21",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-74",
   "mode": "INJECT",
   "title": "Re-file one, reject the other",
   "section": "Arrival classification",
   "demonstrates": "One QA run, for D+1; D owed and unfilled, no mark-not-supplied. **Breaks as**: the early file checked against D.",
   "breaksAs": "The early file checked against D.",
   "config": null,
   "requirements": [],
   "coordinates": {
    "dataset": "birth-registrations",
    "supplies": [
     "birth_registrations__202608251330000800"
    ],
    "period": "2026-08-25",
    "inPlaceOn": "2026-08-25",
    "targets": [
     {
      "date": "2026-08-25",
      "at": "13:30",
      "delivery": "Data Extract 25 Aug 2026",
      "filename": "birth_registrations_2026-08-26.csv",
      "day": "2026-08-26",
      "built_to": "green",
      "rules": [],
      "moved": [
       {
        "rule": "registering_parent_2_name.completeness",
        "to": "green",
        "nulls": 495,
        "of_rows": 1933
       }
      ]
     }
    ],
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-75a",
   "mode": "INJECT",
   "title": "A supply rejected after it waited - while it waited",
   "section": "Calendar corrections",
   "demonstrates": "Cp-clients, 2024-Q1: the whole delivery on time at 09:00 on 1 February with cp_clients alone built red by its own preset; the other five clean. *Config: quarterly, due 09:00 on the 1st; a person rejects it at 09:00 on 22 February; a corrected cp_clients alone arrives at 10:00 on 29 February.* **Expect** (REQ-DASH-197), on 8 February, in the as-at panel under the results' verdict line: the heading \"On Thursday, 8 February 2024 the warehouse did not hold the latest file\", the column \"Latest arrival by Thursday, 8 February 2024 \u2014 not promoted\" naming cp-clients@202402010900000800, and the reason \"this supply was staged and nobody had decided about it yet\". **What the other tables show**: the red clients turned notifications', investigations' and placements' own cross-table checks red, so all three wait for a person on 8 and 25 February; carers waited until 11 February and then promoted green; case workers promoted green on 7 February. When the corrected cp_clients arrives the re-evaluation promotes clients, notifications, investigations and placements green (11 March). **Breaks as**: no panel; or the reason \"superseded\" (post-build-review #164's reading, which this quarter is placed to avoid).",
   "breaksAs": "No panel; or the reason \"superseded\" (post-build-review #164's reading, which this quarter is placed to avoid).",
   "config": "Config: quarterly, due 09:00 on the 1st; a person rejects it at 09:00 on 22 February; a corrected cp_clients alone arrives at 10:00 on 29 February.",
   "requirements": [
    "REQ-DASH-197"
   ],
   "coordinates": {
    "dataset": "cp-clients",
    "supplies": [
     "cp_clients__202402010900000800",
     "cp_clients__202402291000000800"
    ],
    "period": "2024-Q1",
    "inPlaceOn": "2024-02-08",
    "subject": "as-at-panel"
   }
  },
  {
   "id": "TS-75b",
   "mode": "INJECT",
   "title": "A supply rejected after it waited - after it was rejected",
   "section": "Calendar corrections",
   "demonstrates": "The same placement, on 25 February. **Expect** (REQ-DASH-197), in the same panel: \"On Sunday, 25 February 2024 the warehouse did not hold the latest file\", the same supply, and the reason \"a person had rejected this supply, so it was not promoted\". The other tables as TS-75a's, carers now promoted. From 29 February the corrected supply fills the quarter and cp-clients ends healthy. **Breaks as**: the panel naming the corrected supply, or still \"nobody had decided\".",
   "breaksAs": "The panel naming the corrected supply, or still \"nobody had decided\".",
   "config": null,
   "requirements": [
    "REQ-DASH-197"
   ],
   "coordinates": {
    "dataset": "cp-clients",
    "supplies": [
     "cp_clients__202402010900000800",
     "cp_clients__202402291000000800"
    ],
    "period": "2024-Q1",
    "inPlaceOn": "2024-02-25",
    "subject": "as-at-panel"
   }
  },
  {
   "id": "TS-76",
   "mode": "INJECT",
   "title": "A substitution later removed",
   "section": "Calendar corrections",
   "demonstrates": "Cp-placements, 2025-Q1: the delivery leaves cp_placements out; a person substitutes the quarter onto 2024-Q4 at 09:00 on 3 February, and at 09:00 on 20 April - once the next quarter's window has opened - removes the substitution and marks the quarter not supplied, in that order, at one instant. *Config: quarterly, as TS-75a.* **Expect** (REQ-DASH-198), on 17 February: the pill \"Substituted from 2024-Q4\" beside the dataset's title, and in its drill-down, below the results' heading, \"Since removed, as from Sunday, 20 April 2025\". The quarter closes \"not supplied (accepted)\". **What cp-clients and cp-carers read for 2025-Q1** (H1): clients promoted AMBER on arrival and stays amber before, during and after the substitution - the amber is the ordinary one drawn for this quarter, which the delivery keeps (REQ-GEN-199's PROVISIONAL choice); carers waited until 9 February, then promoted GREEN and stays green. Neither is red after the substitution ends: the cross-table checks reading cp_placements are filed under cp-placements, so in a quarter with no placements supply nothing runs them for clients or carers (the architect's H1 expected red; post-build-review #174). **Breaks as**: no pill on 17 February; or \"Since replaced\".",
   "breaksAs": "No pill on 17 February; or \"Since replaced\".",
   "config": null,
   "requirements": [
    "REQ-DASH-198",
    "REQ-GEN-199"
   ],
   "coordinates": {
    "dataset": "cp-placements",
    "supplies": [],
    "period": "2025-Q1",
    "inPlaceOn": "2025-02-17",
    "subject": "substitution-drill-down"
   }
  },
  {
   "id": "TS-77a",
   "mode": "INJECT",
   "title": "A substitution later replaced - while it stood",
   "section": "Calendar corrections",
   "demonstrates": "Cp-placements, 2023-Q2: the delivery leaves cp_placements out; a person substitutes onto 2023-Q1 at 09:00 on 3 May; cp_placements alone arrives at 10:00 on 8 June and the person promotes it at 10:00 on 9 June, which removes the substitution. *Config: quarterly, as TS-75a.* **Expect** (REQ-DASH-198), on 17 May: the pill \"Substituted from 2023-Q1\", and in its drill-down \"Since replaced, as from Friday, 9 June 2023\". **What cp-clients and cp-carers read for 2023-Q2**: both waited on 2 May; clients promoted AMBER (its quarter's drawn amber, kept) on 7 May and carers GREEN on 3 May, and both stay so while the substitution stands, on 8 June and after the promotion. **Breaks as**: no pill; or \"Since removed\".",
   "breaksAs": "No pill; or \"Since removed\".",
   "config": null,
   "requirements": [
    "REQ-DASH-198"
   ],
   "coordinates": {
    "dataset": "cp-placements",
    "supplies": [
     "cp_placements__202306081000000800"
    ],
    "period": "2023-Q2",
    "inPlaceOn": "2023-05-17",
    "subject": "substitution-drill-down"
   }
  },
  {
   "id": "TS-77b",
   "mode": "INJECT",
   "title": "Known wrong today (post-build-review #164): A substitution later replaced - the day the late file waited",
   "section": "Calendar corrections",
   "demonstrates": "Today the as-at panel (\"On Thursday, 8 June 2023 the warehouse did not hold the latest file\") gives the late supply the reason \"this one had been superseded - a newer version had arrived for the same period, a person had set it aside, or a later supply had been promoted into the period - so it was no longer what the period held\" - against a period whose holder is a SUBSTITUTED supply, a variant of #164 - while the pill's drill-down reads \"Since replaced, as from Friday, 9 June 2023\" and \"2023-Q2 holds 2023-Q1's supply; the results below are a newer supply awaiting a decision.\" Once #164 is decided the panel's reason line should say the supply was waiting for a decision. **Breaks as**: a different reason line in the panel means #164 was decided, not a regression; any other change on that date - the drill-down's sentences included - is a regression.",
   "breaksAs": "A different reason line in the panel means #164 was decided, not a regression; any other change on that date - the drill-down's sentences included - is a regression.",
   "config": null,
   "requirements": [],
   "coordinates": {
    "dataset": "cp-placements",
    "supplies": [
     "cp_placements__202306081000000800"
    ],
    "period": "2023-Q2",
    "inPlaceOn": "2023-06-08",
    "subject": "as-at-panel"
   }
  },
  {
   "id": "TS-78a",
   "mode": "INJECT",
   "title": "A supply promoted after a newer one - the day it was promoted",
   "section": "Calendar corrections",
   "demonstrates": "Birth Registrations, 30 August to 2 September 2026, inside the hold era: D's supply amber and held; D+1's green and promoted by the rule; a person promotes D's into D at 20:00 on D+1; D+2's amber and held, promoted by the person at 10:00 on D+3, before D+3's green supply. *Config: daily; the amber setting is HOLD from 2026-08-30 (contract/data-asset.yaml, the version added for this scenario); D to D+3 quiet.* **Expect** (REQ-DASH-197 criterion 6), on 31 August, in the as-at panel: \"On Monday, 31 August 2026 the newest file was not the newest promotion\", the column \"Latest arrival \u2014 promoted into Monday, 31 August 2026\", and the reason \"a supply promoted later into Sunday, 30 August 2026 was what downstream read most recently\". **Breaks as**: no panel; or the generic \"did not hold the latest file\". Depends on the hold era covering 30 August to 1 September; generation refuses, naming TS-78a, if it stops doing so.",
   "breaksAs": "No panel; or the generic \"did not hold the latest file\". Depends on the hold era covering 30 August to 1 September; generation refuses, naming TS-78a, if it stops doing so.",
   "config": null,
   "requirements": [
    "REQ-DASH-197"
   ],
   "coordinates": {
    "dataset": "birth-registrations",
    "supplies": [
     "birth_registrations__202608301400000800",
     "birth_registrations__202608311400000800",
     "birth_registrations__202609011400000800"
    ],
    "period": "2026-08-30",
    "inPlaceOn": "2026-08-31",
    "targets": [
     {
      "date": "2026-08-30",
      "at": "14:00",
      "built_to": "amber",
      "rules": [
       "registering_parent_1_name.completeness"
      ],
      "moved": [
       {
        "rule": "registering_parent_2_name.completeness",
        "to": "green",
        "nulls": 495,
        "of_rows": 1933
       },
       {
        "rule": "registering_parent_1_name.completeness",
        "to": "amber",
        "nulls": 145,
        "of_rows": 1933,
        "was": 38
       }
      ]
     },
     {
      "date": "2026-08-31",
      "at": "14:00",
      "built_to": "green",
      "rules": [],
      "moved": [
       {
        "rule": "registering_parent_2_name.completeness",
        "to": "green",
        "nulls": 495,
        "of_rows": 1933
       }
      ]
     },
     {
      "date": "2026-09-01",
      "at": "14:00",
      "built_to": "amber",
      "rules": [
       "registering_parent_2_name.completeness"
      ],
      "moved": [
       {
        "rule": "registering_parent_2_name.completeness",
        "to": "amber",
        "nulls": 625,
        "of_rows": 1933,
        "was": 526
       }
      ]
     }
    ],
    "subject": "as-at-panel"
   }
  },
  {
   "id": "TS-78b",
   "mode": "INJECT",
   "title": "A supply promoted after a newer one - the day after",
   "section": "Calendar corrections",
   "demonstrates": "The same placement, on 1 September. **Expect** (REQ-DASH-197 criterion 13), the verdict line above the results: \"Awaiting a decision \u2014 the results below are the newest supply, received 2:00pm Tuesday, 1 September 2026, which is not in place yet. The supply in place is the one received 2:00pm Sunday, 30 August 2026.\" - naming D's supply, not D+1's, which is newer by receipt. **Breaks as**: the verdict line naming 31 August's supply as in place.",
   "breaksAs": "The verdict line naming 31 August's supply as in place.",
   "config": null,
   "requirements": [
    "REQ-DASH-197"
   ],
   "coordinates": {
    "dataset": "birth-registrations",
    "supplies": [
     "birth_registrations__202608301400000800",
     "birth_registrations__202608311400000800",
     "birth_registrations__202609011400000800"
    ],
    "period": "2026-08-30",
    "inPlaceOn": "2026-09-01",
    "targets": [
     {
      "date": "2026-08-30",
      "at": "14:00",
      "built_to": "amber",
      "rules": [
       "registering_parent_1_name.completeness"
      ],
      "moved": [
       {
        "rule": "registering_parent_2_name.completeness",
        "to": "green",
        "nulls": 495,
        "of_rows": 1933
       },
       {
        "rule": "registering_parent_1_name.completeness",
        "to": "amber",
        "nulls": 145,
        "of_rows": 1933,
        "was": 38
       }
      ]
     },
     {
      "date": "2026-08-31",
      "at": "14:00",
      "built_to": "green",
      "rules": [],
      "moved": [
       {
        "rule": "registering_parent_2_name.completeness",
        "to": "green",
        "nulls": 495,
        "of_rows": 1933
       }
      ]
     },
     {
      "date": "2026-09-01",
      "at": "14:00",
      "built_to": "amber",
      "rules": [
       "registering_parent_2_name.completeness"
      ],
      "moved": [
       {
        "rule": "registering_parent_2_name.completeness",
        "to": "amber",
        "nulls": 625,
        "of_rows": 1933,
        "was": 526
       }
      ]
     }
    ],
    "subject": "verdict-line"
   }
  },
  {
   "id": "TS-79a",
   "mode": "INJECT",
   "title": "An inherited quarter - the newest",
   "section": "Calendar corrections",
   "demonstrates": "Cp-case-workers, the newest quarter before the build's own in which it is not delivered (2026-Q2 today), so it inherits the quarter before. Nothing generated; the placement is written after generation from the calendar's participation, in place on the middle of the quarter. *Config: quarterly; cp-case-workers participates only in Q1 and Q3.* **Expect** (REQ-DASH-198): the pill \"Inherited from 2026-Q1\" beside the dataset's title. The same page also shows an as-at panel and an \"Awaiting a decision\" verdict line about a May supply that is \"not filed to any period\": ordinary deliveries carry cp_case_workers in months it does not take part in, and each is held (TS-52's shape) - the pill, not the panel, is what this scenario points at. **Breaks as**: no pill; or a stale date after ANCHOR_DATE moves.",
   "breaksAs": "No pill; or a stale date after ANCHOR_DATE moves.",
   "config": null,
   "requirements": [
    "REQ-DASH-198"
   ],
   "coordinates": {
    "dataset": "cp-case-workers",
    "supplies": [],
    "period": "2026-Q2",
    "inPlaceOn": "2026-06-16",
    "subject": "standing-in-pill"
   }
  },
  {
   "id": "TS-79b",
   "mode": "INJECT",
   "title": "An inherited quarter - the oldest of the original fifteen",
   "section": "Calendar corrections",
   "demonstrates": "Its page looks identical to TS-79a's - the pill \"Inherited from 2023-Q1\". **Breaks as**: no pill.",
   "breaksAs": "No pill.",
   "config": null,
   "requirements": [
    "REQ-GEN-207"
   ],
   "coordinates": {
    "dataset": "cp-case-workers",
    "supplies": [],
    "period": "2023-Q2",
    "inPlaceOn": "2023-06-16",
    "subject": "standing-in-pill"
   }
  },
  {
   "id": "TS-80",
   "mode": "INJECT",
   "title": "A contested pair of one Child Protection table, settled by a person",
   "section": "The option A and period-closing batch, planted (REQ-GEN-136, REQ-GEN-137)",
   "demonstrates": "PLANTED by REQ-GEN-203 (2026-10-18) in a grown quarter (REQ-GEN-207): a stray test file (TS-71's shape) beside the real Client Register, so a settlement can be seen clearing the cross-table readers the contest held, which only Child Protection has. Its link opens on the pair's arrival day. *Config: quarterly, Feb/May/Aug/Nov, due 09:00 on the 1st, claim window 14 days. 2020-Q4's delivery carries the usual files and two Client Registers - a stray test file, cp_clients_TEST.csv, every client named TEST, at 08:20 on the due day and the real cp_clients.csv at 08:30, both before 09:00 - after one green lead-in quarter (2020-Q3) and before a green one (2021-Q1), the real extract built green. A scripted person settles the pair at 11:00 the next day (contract/scripted_decisions.yaml, \"TS-80 settle\"): file one by receipt, the test file, rejected; file two, the real extract, the quarter's supply.* **Breaks as**: the test rows checked as the quarter's supply, the readers left contested after the settlement, or the file named by sorted name rather than by receipt position.",
   "breaksAs": "The test rows checked as the quarter's supply, the readers left contested after the settlement, or the file named by sorted name rather than by receipt position.",
   "config": "Config: quarterly, Feb/May/Aug/Nov, due 09:00 on the 1st, claim window 14 days. 2020-Q4's delivery carries the usual files and two Client Registers - a stray test file, cp_clients_TEST.csv, every client named TEST, at 08:20 on the due day and the real cp_clients.csv at 08:30, both before 09:00 - after one green lead-in quarter (2020-Q3) and before a green one (2021-Q1), the real extract built green. A scripted person settles the pair at 11:00 the next day (contract/scripted_decisions.yaml, \"TS-80 settle\"): file one by receipt, the test file, rejected; file two, the real extract, the quarter's supply.",
   "requirements": [
    "REQ-GEN-203",
    "REQ-GEN-207"
   ],
   "coordinates": {
    "dataset": "cp-clients",
    "supplies": [
     "cp_clients__202011010820000800"
    ],
    "period": "2020-Q4",
    "inPlaceOn": "2020-11-01",
    "targets": [
     {
      "date": "2020-11-01",
      "at": "08:30",
      "delivery": "Data Extract 01 Nov 2020",
      "filename": "cp_clients.csv",
      "day": "2020-11-01",
      "built_to": "green",
      "rules": [],
      "moved": []
     }
    ],
    "subject": "supply-history-row"
   }
  }
 ]
}
-->
