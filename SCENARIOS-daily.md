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
only in a passing test run.

The dashboard does not label them. A supply that is failing reads as
failing, the same as a real one would, because that is the point. **This
is the list that says which problems were on purpose, and where to look
at it.**

Each entry gives coordinates - the dataset, the supplies, the period,
and the date to set the In the warehouse on picker to - and never a link. The
generator knows where a scenario landed; it does not know how the
dashboard addresses its pages, and a URL written here would break
silently the next time a route changed.

A scenario marked **not injected** has no generated data behind it.
Either it is a pure unit test with nothing to look at, or it is meant
for injection and has not been placed yet.

**23 of 23 scenarios marked for injection have data behind them today.** 23 scenarios are registered in all.

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
| Set "in the warehouse on" to | 2026-09-15 |

### TS-2 - Backward cascade

**What it demonstrates.** Files as **Thursday**, the period open when it arrived (REQ-PIPE-131). Tuesday and Wednesday closed unfilled when the next day's window opened, read as overdue, and a human marks them not supplied with a reason (REQ-PIPE-132).

**What it would look like if the rule were wrong.** Files as Tuesday, two days late; the next as Wednesday; the feed sits permanently two days behind for ever. *Used to expect* the missed days marked missed under monotonic filling - REQ-PIPE-131 closes a slot by time and REQ-PIPE-132 has a person mark it not supplied.

*Config: daily, due ~22:00.*

| Where to look | |
|---|---|
| Dataset | birth-registrations |
| Supplies | `birth_registrations__202609111400000800` |
| Period | 2026-09-11 |
| Set "in the warehouse on" to | 2026-09-11 |

### TS-3c - Daily, prior slot FILLED

**What it demonstrates.** Tuesday's window has not opened, so Monday is the open period, and it is filled -> **resupply of Monday**, no auto-promotion, holds and warns.

*Config: daily evening-before - the supply for day D is due 22:00 on D-1 - early window 4 hours, so Tuesday's window opens 18:00 Monday. Monday's slot filled. Arrival 17:00 Monday, one hour outside.*

| Where to look | |
|---|---|
| Dataset | birth-registrations |
| Supplies | `birth_registrations__202606212100000800`, `birth_registrations__202606221700000800` |
| Period | 2026-06-22 |
| Set "in the warehouse on" to | 2026-06-22 |

### TS-3d - Daily, prior slot UNFILLED

**What it demonstrates.** Monday is still the open period -> fills **Monday, 19 hours late**.

| Where to look | |
|---|---|
| Dataset | birth-registrations |
| Supplies | `birth_registrations__202606251700000800` |
| Period | 2026-06-25 |
| Set "in the warehouse on" to | 2026-06-25 |

### TS-4 - Arrival into an already-filled slot

**What it demonstrates.** Does not auto-promote unless the replacement setting in force permits its status (REQ-PIPE-123 - `never` as shipped, so it waits); where it permits, it replaces the promoted supply, which is superseded, never rejected. Warns; the message names the context ("a supply arrived for Monday, which was already accepted at 16:00", plus the boundary detail where relevant); and the three genuinely different actions are reachable - **accept** as a correction (promoting it supersedes the one in place in the warehouse, REQ-PIPE-128), **re-file** to another slot, **reject** as a duplicate. *Used to expect* "never auto-promotes whatever its status" - REQ-PIPE-123 made that a setting (REQ-GEN-138).

| Where to look | |
|---|---|
| Dataset | birth-registrations |
| Supplies | `birth_registrations__202609151400000800`, `birth_registrations__202609151600000800`, `birth_registrations__202609152000000800` |
| Period | 2026-09-15 |
| Set "in the warehouse on" to | 2026-09-15 |

## Arrival classification

### TS-10a - Evening-before daily arrival, Monday filled

**What it demonstrates.** The 22:00 arrival fills **Tuesday, on time**.

*Config: daily, Tuesday's supply due 22:00 MONDAY, claim window 4 hours - so Tuesday's window opens 18:00 Monday, and Monday closes then.*

| Where to look | |
|---|---|
| Dataset | birth-registrations |
| Supplies | `birth_registrations__202606192200000800` |
| Period | 2026-06-20 |
| Set "in the warehouse on" to | 2026-06-20 |

### TS-10b - Evening-before daily arrival, Monday unfilled

**What it demonstrates.** The 22:00 arrival ALSO fills **Tuesday, on time**, and Monday closes with no supply. **Changed 2026-10-04 by REQ-PIPE-131**: this variant used to file Monday, late - slot state decided between two answers. Keith's worked consequence: Monday's file arriving after Tuesday's claim window opened is filed as Tuesday's; Monday closes empty, visibly, and Tuesday's real file then supersedes it (REQ-PIPE-118), replaces it (REQ-PIPE-123), or waits for a person. The cutoff still lives in `due_at` and the claim window, not in code.

| Where to look | |
|---|---|
| Dataset | birth-registrations |
| Supplies | `birth_registrations__202606272200000800` |
| Period | 2026-06-28 |
| Set "in the warehouse on" to | 2026-06-28 |

### TS-68 - A duplicate send

**What it demonstrates.** File one D's supply, early and promoted; file two kept but superseded. **Breaks as**: the duplicate, sorting first, taken as file one - the staged ordinal and the supply ordinal disagreeing.

**What it would look like if the rule were wrong.** The duplicate, sorting first, taken as file one - the staged ordinal and the supply ordinal disagreeing.

| Where to look | |
|---|---|
| Dataset | birth-registrations |
| Supplies | `birth_registrations__202607281340000800` |
| Period | 2026-07-28 |
| Set "in the warehouse on" to | 2026-07-28 |
| Built to | Pass, the 2026-07-28 13:40 arrival |

### TS-69 - Tomorrow's file sent early with today's

**What it demonstrates.** File one D's supply; file two re-filed to D+1, checked there, and D+1's only supply. **Breaks as**: D+1 left with no supply, or the re-filed file checked against D.

**What it would look like if the rule were wrong.** D+1 left with no supply, or the re-filed file checked against D.

| Where to look | |
|---|---|
| Dataset | birth-registrations |
| Supplies | `birth_registrations__202608021330000800` |
| Period | 2026-08-02 |
| Set "in the warehouse on" to | 2026-08-02 |
| Built to | Pass, the 2026-08-02 13:30 arrival |
| Built to | Pass, the 2026-08-02 13:45 arrival |

### TS-70 - A faulty file and its corrected re-export

**What it demonstrates.** File one rejected; file two D's supply, its own receipt taken, so D reads **late**, 4:30pm; no hold; D+1 unaffected. **Breaks as**: D read early from file one's receipt.

**What it would look like if the rule were wrong.** D read early from file one's receipt.

| Where to look | |
|---|---|
| Dataset | birth-registrations |
| Supplies | `birth_registrations__202608071340000800` |
| Period | 2026-08-07 |
| Set "in the warehouse on" to | 2026-08-07 |
| Built to | Pass, the 2026-08-07 16:30 arrival |

### TS-71 - A stray test file that loads

**What it demonstrates.** The test file rejected; the real one D's supply, early. **Breaks as**: the test rows checked as D's supply.

**What it would look like if the rule were wrong.** The test rows checked as D's supply.

| Where to look | |
|---|---|
| Dataset | birth-registrations |
| Supplies | `birth_registrations__202608121320000800` |
| Period | 2026-08-12 |
| Set "in the warehouse on" to | 2026-08-12 |
| Built to | Pass, the 2026-08-12 13:40 arrival |

### TS-72 - A stray test file the load refuses

**What it demonstrates.** The test file offered only "rejected", named as never loaded; the real file D's supply, checked by the real tools, early and promoted, and the refused file marked as never loaded. **Breaks as**: the real file named as the one that never loaded.

**What it would look like if the rule were wrong.** The real file named as the one that never loaded.

| Where to look | |
|---|---|
| Dataset | birth-registrations |
| Supplies | `birth_registrations__202608171330000800` |
| Period | 2026-08-17 |
| Set "in the warehouse on" to | 2026-08-17 |
| Built to | Pass, the 2026-08-17 13:30 arrival |

### TS-73 - Reject both

**What it demonstrates.** Each file's rejection its own entry, no QA, nothing promoted, D left owed and unfilled with no mark-not-supplied and no later supply. **Breaks as**: D read as supplied, or not-supplied by a person.

**What it would look like if the rule were wrong.** D read as supplied, or not-supplied by a person.

| Where to look | |
|---|---|
| Dataset | birth-registrations |
| Supplies | `birth_registrations__202608211320000800` |
| Period | 2026-08-21 |
| Set "in the warehouse on" to | 2026-08-21 |

### TS-74 - Re-file one, reject the other

**What it demonstrates.** One QA run, for D+1; D owed and unfilled, no mark-not-supplied. **Breaks as**: the early file checked against D.

**What it would look like if the rule were wrong.** The early file checked against D.

| Where to look | |
|---|---|
| Dataset | birth-registrations |
| Supplies | `birth_registrations__202608251330000800` |
| Period | 2026-08-25 |
| Set "in the warehouse on" to | 2026-08-25 |
| Built to | Pass, the 2026-08-25 13:30 arrival |

## The option A and period-closing batch, planted (REQ-GEN-136, REQ-GEN-137)

### TS-41 - A resend supersedes the failed supply before it

**What it demonstrates.** The resend supersedes the waiting 14:00 supply, which moves to the period's superseded schema, named as superseded by the resend (REQ-PIPE-118).

**What it would look like if the rule were wrong.** Two versions of one table waiting for one day, every reader contested.

*Config: daily, due 14:00 AWST - TS-1's own placement. Settings in force where it lands (2026-09-15): warn setting promote-and-acknowledge, replacement setting never.*

| Where to look | |
|---|---|
| Dataset | birth-registrations |
| Supplies | `birth_registrations__202609151400000800`, `birth_registrations__202609151600000800`, `birth_registrations__202609152000000800` |
| Period | 2026-09-15 |
| Set "in the warehouse on" to | 2026-09-15 |

### TS-43 - A warning supply held under hold

**What it demonstrates.** The warning supply is not promoted; the rule records a promotion-withheld note naming the setting, and the slot reads Warn, waiting for a person (REQ-PIPE-122).

**What it would look like if the rule were wrong.** It promotes itself, as it would under promote.

*Config: daily; the warn setting is HOLD from 2026-08-30 (TS-78's version, REQ-GEN-199); a scripted promotion at 10:00 the next morning.*

| Where to look | |
|---|---|
| Dataset | birth-registrations |
| Supplies | `birth_registrations__202609051400000800` |
| Period | 2026-09-05 |
| Set "in the warehouse on" to | 2026-09-05 |
| Built to | Warn on place_of_birth_facility.completeness (445 of 1,933), the 2026-09-05 14:00 arrival |

### TS-44 - A warning supply promoted and awaiting acknowledgement

**What it demonstrates.** Promoted by the rule, recorded with the setting, and shown as awaiting acknowledgement (REQ-PIPE-122).

**What it would look like if the rule were wrong.** Promoted with nothing asked, or held.

*Config: daily; PROMOTE-AND-ACKNOWLEDGE from 2026-09-10.*

| Where to look | |
|---|---|
| Dataset | birth-registrations |
| Supplies | `birth_registrations__202609131400000800` |
| Period | 2026-09-13 |
| Set "in the warehouse on" to | 2026-09-13 |
| Built to | Warn on registering_parent_1_name.completeness (145 of 1,993), the 2026-09-13 14:00 arrival |

### TS-45 - The same, acknowledged by a person

**What it demonstrates.** Beside TS-44's, this one reads acknowledged, by the person, with their reason (REQ-PIPE-122, REQ-GEN-137 criterion 4).

**What it would look like if the rule were wrong.** The acknowledgement refused, or written outside the decision path.

*Config: as TS-44; a scripted acknowledgement five hours after receipt, once the rule has promoted it.*

| Where to look | |
|---|---|
| Dataset | birth-registrations |
| Supplies | `birth_registrations__202609171400000800` |
| Period | 2026-09-17 |
| Set "in the warehouse on" to | 2026-09-17 |
| Built to | Warn on registering_parent_2_name.completeness (625 of 2,119), the 2026-09-17 14:00 arrival |

### TS-46 - A passing resupply replaces the promoted supply

**What it demonstrates.** The 16:00 supply is promoted by the rule, naming the supply it replaced and the setting; the 14:00 one is superseded, not rejected, and its supply-history row says so (REQ-PIPE-123, REQ-DASH-127).

**What it would look like if the rule were wrong.** The resend waits for a person, as it would under never.

*Config: daily; the replacement setting is 'when passing' from 2026-09-18 to 2026-09-21.*

| Where to look | |
|---|---|
| Dataset | birth-registrations |
| Supplies | `birth_registrations__202609211400000800`, `birth_registrations__202609211600000800` |
| Period | 2026-09-21 |
| Set "in the warehouse on" to | 2026-09-21 |
| Built to | Pass, the 2026-09-21 14:00 arrival |
| Built to | Pass, the 2026-09-21 16:00 arrival |

### TS-47 - A daily file arriving after the next day's window opened

**What it demonstrates.** It fills the NEXT day, the period open when it arrived; its own day closes with no supply, overdue, and a scripted person marks it not supplied, so it reads "not supplied (accepted)" (REQ-PIPE-131, REQ-PIPE-132, REQ-DASH-133, REQ-GEN-137 criterion 3).

**What it would look like if the rule were wrong.** Filed backward to its own day.

*Config: daily, due 14:00, 4-hour claim window - the next day's window opens at 10:00. Settings in force where it lands (2026-09-07): warn setting hold, replacement setting never.*

| Where to look | |
|---|---|
| Dataset | birth-registrations |
| Supplies | `birth_registrations__202609081100000800` |
| Period | 2026-09-07 |
| Set "in the warehouse on" to | 2026-09-08 |

## Calendar corrections

### TS-62 - A correction merged and not yet confirmed

The correction is merged and a new supply arrives before anyone confirms it. *Config: Birth Registrations, daily, due 14:00. Correction REQ-GEN-205-WINDOW, dated 24 September 2026, widens the daily claim window from four hours to six from 25 September (a version-level change), and its scripted confirmation is pending. The 25 September supply arrives at 09:00, inside the six-hour window and outside the four-hour one.* **Expect** (bootstrap of 2026-10-19): the 09:00 supply files to 2026-09-25, its own day, early, and is promoted. Birth Registrations' page says "A calendar correction to this dataset's delivery agreement - REQ-GEN-205-WINDOW - is awaiting the data asset's manager to confirm it", and `mothman supply corrections` lists it as pending. `mothman schedule check-agreement` exits 0: REQ-PIPE-173's backstop does NOT go to Fail, because a declared but unapplied correction accounts for the difference (REQ-PIPE-170 criteria 20-21). The TUI lists it under "Calendar corrections awaiting confirmation". The page's Needs action list does not yet: REQ-DASH-263 (signed 2026-10-19, Keith) adds it there, and `mothman supply queue` stays as it is. **Breaks as**: the backstop's "configuration problem on our side" Fail; or the arrival judged against the old date.

**What it would look like if the rule were wrong.** The backstop's "configuration problem on our side" Fail; or the arrival judged against the old date.

*Config: Birth Registrations, daily, due 14:00. Correction REQ-GEN-205-WINDOW, dated 24 September 2026, widens the daily claim window from four hours to six from 25 September (a version-level change), and its scripted confirmation is pending. The 25 September supply arrives at 09:00, inside the six-hour window and outside the four-hour one.*

| Where to look | |
|---|---|
| Dataset | birth-registrations |
| Supplies | `birth_registrations__202609250900000800` |
| Period | 2026-09-25 |
| Set "in the warehouse on" to | 2026-09-25 |

### TS-78a - A supply promoted after a newer one - the day it was promoted

Birth Registrations, 30 August to 2 September 2026, inside the hold era: D's supply warning and held; D+1's passing and promoted by the rule; a person promotes D's into D at 20:00 on D+1; D+2's warning and held, promoted by the person at 10:00 on D+3, before D+3's passing supply. *Config: daily; the warn setting is HOLD from 2026-08-30 (contract/data-asset.yaml, the version added for this scenario); D to D+3 quiet.* **Expect** (REQ-DASH-197 criterion 6), on 31 August, in the as-at panel: "On Monday, 31 August 2026 the newest file was not the newest promotion", the column "Latest arrival — promoted into Monday, 31 August 2026", and the reason "a supply promoted later into Sunday, 30 August 2026 was what downstream read most recently". **Breaks as**: no panel; or the generic "did not hold the latest file". Depends on the hold era covering 30 August to 1 September; generation refuses, naming TS-78a, if it stops doing so.

**What it would look like if the rule were wrong.** No panel; or the generic "did not hold the latest file". Depends on the hold era covering 30 August to 1 September; generation refuses, naming TS-78a, if it stops doing so.

| Where to look | |
|---|---|
| Dataset | birth-registrations |
| Supplies | `birth_registrations__202608301400000800`, `birth_registrations__202608311400000800`, `birth_registrations__202609011400000800` |
| Period | 2026-08-30 |
| Set "in the warehouse on" to | 2026-08-31 |
| Built to | Warn on registering_parent_1_name.completeness (145 of 1,933), the 2026-08-30 14:00 arrival |
| Built to | Pass, the 2026-08-31 14:00 arrival |
| Built to | Warn on registering_parent_2_name.completeness (625 of 1,933), the 2026-09-01 14:00 arrival |

### TS-78b - A supply promoted after a newer one - the day after

The same placement, on 1 September. **Expect** (REQ-DASH-197 criterion 13), the verdict line above the results: "Awaiting a decision — the results below are the newest supply, received 2:00pm Tuesday, 1 September 2026, which is not in place in the warehouse yet. The supply in place in the warehouse is the one received 2:00pm Sunday, 30 August 2026, and is warning." - the warehouse's status in the legend's word since REQ-DASH-272 - naming D's supply, not D+1's, which is newer by receipt. **Breaks as**: the verdict line naming 31 August's supply as in place in the warehouse.

**What it would look like if the rule were wrong.** The verdict line naming 31 August's supply as in place in the warehouse.

| Where to look | |
|---|---|
| Dataset | birth-registrations |
| Supplies | `birth_registrations__202608301400000800`, `birth_registrations__202608311400000800`, `birth_registrations__202609011400000800` |
| Period | 2026-08-30 |
| Set "in the warehouse on" to | 2026-09-01 |
| Built to | Warn on registering_parent_1_name.completeness (145 of 1,933), the 2026-08-30 14:00 arrival |
| Built to | Pass, the 2026-08-31 14:00 arrival |
| Built to | Warn on registering_parent_2_name.completeness (625 of 1,933), the 2026-09-01 14:00 arrival |


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
   "demonstrates": "Does not auto-promote unless the replacement setting in force permits its status (REQ-PIPE-123 - `never` as shipped, so it waits); where it permits, it replaces the promoted supply, which is superseded, never rejected. Warns; the message names the context (\"a supply arrived for Monday, which was already accepted at 16:00\", plus the boundary detail where relevant); and the three genuinely different actions are reachable - **accept** as a correction (promoting it supersedes the one in place in the warehouse, REQ-PIPE-128), **re-file** to another slot, **reject** as a duplicate. *Used to expect* \"never auto-promotes whatever its status\" - REQ-PIPE-123 made that a setting (REQ-GEN-138).",
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
   "id": "TS-41",
   "mode": "INJECT",
   "title": "A resend supersedes the failed supply before it",
   "section": "The option A and period-closing batch, planted (REQ-GEN-136, REQ-GEN-137)",
   "demonstrates": "The resend supersedes the waiting 14:00 supply, which moves to the period's superseded schema, named as superseded by the resend (REQ-PIPE-118).",
   "breaksAs": "Two versions of one table waiting for one day, every reader contested.",
   "config": "Config: daily, due 14:00 AWST - TS-1's own placement. Settings in force where it lands (2026-09-15): warn setting promote-and-acknowledge, replacement setting never.",
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
   "id": "TS-43",
   "mode": "INJECT",
   "title": "A warning supply held under hold",
   "section": "The option A and period-closing batch, planted (REQ-GEN-136, REQ-GEN-137)",
   "demonstrates": "The warning supply is not promoted; the rule records a promotion-withheld note naming the setting, and the slot reads Warn, waiting for a person (REQ-PIPE-122).",
   "breaksAs": "It promotes itself, as it would under promote.",
   "config": "Config: daily; the warn setting is HOLD from 2026-08-30 (TS-78's version, REQ-GEN-199); a scripted promotion at 10:00 the next morning.",
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
   "title": "A warning supply promoted and awaiting acknowledgement",
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
   "title": "A passing resupply replaces the promoted supply",
   "section": "The option A and period-closing batch, planted (REQ-GEN-136, REQ-GEN-137)",
   "demonstrates": "The 16:00 supply is promoted by the rule, naming the supply it replaced and the setting; the 14:00 one is superseded, not rejected, and its supply-history row says so (REQ-PIPE-123, REQ-DASH-127).",
   "breaksAs": "The resend waits for a person, as it would under never.",
   "config": "Config: daily; the replacement setting is 'when passing' from 2026-09-18 to 2026-09-21.",
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
   "config": "Config: daily, due 14:00, 4-hour claim window - the next day's window opens at 10:00. Settings in force where it lands (2026-09-07): warn setting hold, replacement setting never.",
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
   "id": "TS-62",
   "mode": "INJECT",
   "title": "A correction merged and not yet confirmed",
   "section": "Calendar corrections",
   "demonstrates": "The correction is merged and a new supply arrives before anyone confirms it. *Config: Birth Registrations, daily, due 14:00. Correction REQ-GEN-205-WINDOW, dated 24 September 2026, widens the daily claim window from four hours to six from 25 September (a version-level change), and its scripted confirmation is pending. The 25 September supply arrives at 09:00, inside the six-hour window and outside the four-hour one.* **Expect** (bootstrap of 2026-10-19): the 09:00 supply files to 2026-09-25, its own day, early, and is promoted. Birth Registrations' page says \"A calendar correction to this dataset's delivery agreement - REQ-GEN-205-WINDOW - is awaiting the data asset's manager to confirm it\", and `mothman supply corrections` lists it as pending. `mothman schedule check-agreement` exits 0: REQ-PIPE-173's backstop does NOT go to Fail, because a declared but unapplied correction accounts for the difference (REQ-PIPE-170 criteria 20-21). The TUI lists it under \"Calendar corrections awaiting confirmation\". The page's Needs action list does not yet: REQ-DASH-263 (signed 2026-10-19, Keith) adds it there, and `mothman supply queue` stays as it is. **Breaks as**: the backstop's \"configuration problem on our side\" Fail; or the arrival judged against the old date.",
   "breaksAs": "The backstop's \"configuration problem on our side\" Fail; or the arrival judged against the old date.",
   "config": "Config: Birth Registrations, daily, due 14:00. Correction REQ-GEN-205-WINDOW, dated 24 September 2026, widens the daily claim window from four hours to six from 25 September (a version-level change), and its scripted confirmation is pending. The 25 September supply arrives at 09:00, inside the six-hour window and outside the four-hour one.",
   "requirements": [
    "REQ-GEN-205",
    "REQ-PIPE-173",
    "REQ-PIPE-170",
    "REQ-DASH-263"
   ],
   "coordinates": {
    "dataset": "birth-registrations",
    "supplies": [
     "birth_registrations__202609250900000800"
    ],
    "period": "2026-09-25",
    "inPlaceOn": "2026-09-25",
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
   "id": "TS-78a",
   "mode": "INJECT",
   "title": "A supply promoted after a newer one - the day it was promoted",
   "section": "Calendar corrections",
   "demonstrates": "Birth Registrations, 30 August to 2 September 2026, inside the hold era: D's supply warning and held; D+1's passing and promoted by the rule; a person promotes D's into D at 20:00 on D+1; D+2's warning and held, promoted by the person at 10:00 on D+3, before D+3's passing supply. *Config: daily; the warn setting is HOLD from 2026-08-30 (contract/data-asset.yaml, the version added for this scenario); D to D+3 quiet.* **Expect** (REQ-DASH-197 criterion 6), on 31 August, in the as-at panel: \"On Monday, 31 August 2026 the newest file was not the newest promotion\", the column \"Latest arrival \u2014 promoted into Monday, 31 August 2026\", and the reason \"a supply promoted later into Sunday, 30 August 2026 was what downstream read most recently\". **Breaks as**: no panel; or the generic \"did not hold the latest file\". Depends on the hold era covering 30 August to 1 September; generation refuses, naming TS-78a, if it stops doing so.",
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
   "demonstrates": "The same placement, on 1 September. **Expect** (REQ-DASH-197 criterion 13), the verdict line above the results: \"Awaiting a decision \u2014 the results below are the newest supply, received 2:00pm Tuesday, 1 September 2026, which is not in place in the warehouse yet. The supply in place in the warehouse is the one received 2:00pm Sunday, 30 August 2026, and is warning.\" - the warehouse's status in the legend's word since REQ-DASH-272 - naming D's supply, not D+1's, which is newer by receipt. **Breaks as**: the verdict line naming 31 August's supply as in place in the warehouse.",
   "breaksAs": "The verdict line naming 31 August's supply as in place in the warehouse.",
   "config": null,
   "requirements": [
    "REQ-DASH-197",
    "REQ-DASH-272"
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
  }
 ]
}
-->
