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

**69 of 69 scenarios marked for injection have data behind them today.** 69 scenarios are registered in all.

## Slot assignment

### TS-3a - Quarterly, prior slot FILLED

*Config: Emergency Department, the quarterly calendar - the 1st of February, May, August and November, due 09:00, a 14-day claim window, so May 2025's window opens 09:00 on 17 April. February 2025's supply arrived as usual; this one arrives 10:00 on 16 April 2025, a day before May's window opens (REQ-GEN-236).* **Expect** (the first bootstrapped build, 2026-10-18): filed to **2025-Q1** by the branch `resupply-of-open-slot`, classified `late` - May's window has not opened, so February is still the open period, and it is filled. Being a resupply of a filled slot it is **not promoted**: 2025-Q2 is left with no supply, and the next quarter's drift checks fail by the gap rule (REQ-QAC-108), measured against February's supply. **Breaks as**: files to May because it is "nearly" May's - the window would then mean nothing. Keeps the family's note: the filled branch is a contained imperfection - a supplier one day early leaves a quarter to be put right by a person - not a defect.

**What it would look like if the rule were wrong.** Files to May because it is "nearly" May's - the window would then mean nothing. Keeps the family's note: the filled branch is a contained imperfection - a supplier one day early leaves a quarter to be put right by a person - not a defect.

*Config: Emergency Department, the quarterly calendar - the 1st of February, May, August and November, due 09:00, a 14-day claim window, so May 2025's window opens 09:00 on 17 April. February 2025's supply arrived as usual; this one arrives 10:00 on 16 April 2025, a day before May's window opens (REQ-GEN-236).*

| Where to look | |
|---|---|
| Dataset | ed-presentations |
| Supplies | `ed_presentations__202504161000000800` |
| Period | 2025-Q2 |
| Set "in the warehouse on" to | 2025-05-01 |

### TS-3b - Quarterly, prior slot UNFILLED

*Same config, on Emergency Department, a year later: February 2026's supply never came (suppressed), and May's arrives 10:00 on 16 April 2026, a day before its window opens.* **Expect** (the first bootstrapped build, 2026-10-18): filed to **2026-Q1** by the branch `open-slot-unfilled`, classified `late` - about 74 days - because February is still the open period and nothing filled it. 2026-Q2 is left with no supply. **Breaks as**: files to May and leaves February owed for ever.

**What it would look like if the rule were wrong.** Files to May and leaves February owed for ever.

| Where to look | |
|---|---|
| Dataset | ed-presentations |
| Supplies | `ed_presentations__202604161000000800` |
| Period | 2026-Q2 |
| Set "in the warehouse on" to | 2026-05-01 |

## Arrival classification

### TS-9 - A genuinely early quarterly supply

**What it demonstrates.** Assigned **2024-Q2** (due 09:00 1 May), the period open when it arrived (REQ-PIPE-131), classified **early**, and filled by the rule. Re-quoted 2026-10-28 from the bootstrapped build (REQ-GEN-235 criterion 4; post-build-review #284): Emergency Department's supply received 10:00 22 April 2024 is filed to slot 2024-Q2, arrival status early, filled at 04:06 2 May, filed automatically. Until then this said "assigned August" and "the 1 May anchor" - the dates of the original config above, never of the planted case. Note nothing measures how early it is in order to assign it - earliness is a reported consequence of the assignment.

**What it would look like if the rule were wrong.** `cycle_start()` only looks backwards, so it resolves to the 1 February anchor and reports the supply ~12 weeks LATE for 2024-Q1, a quarter that was filled months ago.

| Where to look | |
|---|---|
| Dataset | ed-presentations |
| Supplies | `ed_presentations__202404221000000800` |
| Period | 2024-Q2 |
| Set "in the warehouse on" to | 2024-05-01 |

### TS-65 - Early, at the edge of the window

**What it demonstrates.** Assigned **2025-Q3** and classified **early by 13 days**, exactly as TS-9 - the window is a boundary, and a supply inside it by a day is as early-and-fine as one inside it by a week (REQ-PIPE-131).

**What it would look like if the rule were wrong.** Treated as a resupply of 2025-Q2, as if the window counted from somewhere else.

*Config: as TS-9 - Emergency Department, one file, quarterly, due 09:00 on the 1st, claim window 14 days. 2025-Q3 (1 August) arrives 19 July at 10:00, thirteen days early, a day after its window opened at 09:00 on 18 July.*

| Where to look | |
|---|---|
| Dataset | ed-presentations |
| Supplies | `ed_presentations__202507191000000800` |
| Period | 2025-Q3 |
| Set "in the warehouse on" to | 2025-08-01 |

### TS-66 - A couple of days early - the everyday case

**What it demonstrates.** Assigned **2025-Q4**, classified **early by 2 days**, and otherwise unremarkable - it fills and promotes like an on-time supply.

**What it would look like if the rule were wrong.** Shown as anything more alarming than early.

*Config: as TS-9 - Emergency Department, one file. 2025-Q4 (1 November) arrives 30 October at 10:00.*

| Where to look | |
|---|---|
| Dataset | ed-presentations |
| Supplies | `ed_presentations__202510301000000800` |
| Period | 2025-Q4 |
| Set "in the warehouse on" to | 2025-11-01 |

### TS-67 - A quarterly supply sent too early

**What it demonstrates.** It cannot claim 2023-Q4, whose window has not opened - nothing claims forward (REQ-PIPE-062 criterion 5). The open period when it arrives is 2023-Q3, so it files there as a **resupply of 2023-Q3** (REQ-PIPE-131), and the rule refuses to promote it over 2023-Q3's accepted supply. Then a PERSON re-files it to 2023-Q4 (a scripted decision, REQ-GEN-135, at 10:00 on 21 October, once Q4's window is open), so 2023-Q4 is not left with no supply. Keith, 2026-10-12: "plus one too early" - the case people will ask about - and "have it refiled to Q4 by a synthetic human making a decision".

**What it would look like if the rule were wrong.** Assigned 2023-Q4 by the RULE because it was obviously meant for it; or 2023-Q4 left empty once the person has re-filed it.

*Config: as TS-9 - Emergency Department, one file. 2023-Q4 (1 November) is due 09:00 that day and its window opens 09:00 on 18 October; the supply arrives 12 October at 10:00, twenty days early and six days before the window. 2023-Q3, before it, is an ordinary quarter whose own supply has arrived.*

| Where to look | |
|---|---|
| Dataset | ed-presentations |
| Supplies | `ed_presentations__202310121000000800` |
| Period | 2023-Q4 |
| Set "in the warehouse on" to | 2023-11-01 |

## Delivery and multi-table

### TS-12 - Five tables load, one is an invalid CSV

**What it demonstrates.** - The five are staged, QA'd, passing, and auto-promoted. Their August slots are **filled**, and their own checks are unaffected - they are not dragged down. - `cp_clients` is a **Fail** (a supply that cannot be loaded is a failing QA finding), rejected, and its August slot stays **unfilled**. - Every check declaring `depends_on: [cp_clients]` - including "Client reference", which is DEFINED on `cp_notifications` - **cannot run**, and reads **Fail with a qualifying chip naming `cp_clients` as the blocker**. - That Fail lands at **collection** level, since cross-table checks are lifted there. `cp_notifications` keeps its own passing status and carries only an informational pointer: fully verified against its own data, unverified against its relationships.

| Where to look | |
|---|---|
| Dataset | cp-clients |
| Supplies | `cp_clients__202505010900000800`, `cp_clients__202505291000000800` |
| Period | 2025-Q3 |
| Set "in the warehouse on" to | 2025-05-02 |

### TS-14 - A later single-table resupply

**What it demonstrates.** It arrives as **its own delivery** and triggers QA. Its slot is clients' own August slot - per-table slot sequences mean there is no "resupply of table X within delivery Y" concept to implement; it is just clients' August supply, arriving late. The previously blocked cross-table check now runs. If it passes, clients promotes and August's slot fills. The recorded QA history keeps **both** runs - the period's current state is the latest, its history is all of them. Clients arriving also re-evaluates the waiting placements' reading checks and re-gates them (REQ-PIPE-121). *Used to say* `qa_results/` kept both runs - REQ-PIPE-089 moved the history into the database. *In the data since 2026-10-15 (REQ-GEN-044 criterion 1)*, riding TS-12's placement: TS-12's cp_clients is refused in 2025-Q2, and the corrected cp_clients arrives alone 28 days later, 10:00 on 2025-05-29, filed to 2025-Q2's still-empty slot. TS-12's link sits between the two; TS-14's lands on the correction's day.

| Where to look | |
|---|---|
| Dataset | cp-clients |
| Supplies | `cp_clients__202505010900000800`, `cp_clients__202505291000000800` |
| Period | 2025-Q3 |
| Set "in the warehouse on" to | 2025-05-29 |

## Timestamps

### TS-38 - A resupply whose filename no longer matches

**What it demonstrates.** The matched files are attributed and processed; the unmatched ones are reported as unrecognised artefacts at **warning** level. Critically, the supply is **NOT** silently treated as complete - the warning is the only thing standing between this and a promoted, passing, HALF supply. Had the resupplies matched, this would instead be the duplicate-match hold of TS-34, which is louder still.

| Where to look | |
|---|---|
| Dataset | cp-clients |
| Supplies | `cp_clients__202602010900000800` |
| Period | 2026-Q2 |
| Set "in the warehouse on" to | 2026-02-01 |

## The option A and period-closing batch, planted (REQ-GEN-136, REQ-GEN-137)

### TS-42a - A contested pair of one Child Protection table, while it is contested

PLANTED by REQ-GEN-203 (2026-10-18) in a grown quarter (REQ-GEN-207), after REQ-PIPE-202 widened `cp_clients`' pattern so two of its files in one delivery contest the table; `tests/test_cp_pair.py` drives the shape through the real orchestrator. Two lettered siblings share the one placement (REQ-GEN-201): this one's link opens on the pair's arrival day. *Config: quarterly, Feb/May/Aug/Nov, due 09:00 on the 1st, claim window 14 days. 2019-Q4's delivery carries the usual files and two Client Registers - cp_clients.csv at 08:30 and a re-export, cp_clients_v2.csv, at 08:40 whose rows differ (each re-pulled an hour later) - both before due; a clean cp_clients.csv follows alone on 29 November at 10:00, after due and before 2020-Q1's window opens, built passing (REQ-GEN-184) after one passing lead-in quarter (2019-Q3) and before a passing one (2020-Q1).* **Expect** (bootstrap of 2026-10-19): on 1 November 2019 cp-clients reads "Two files for one table — this dataset's own supply is not checked until a person resolves it" (REQ-DASH-264), naming cp_clients.csv (received 8:30am) and cp_clients_v2.csv, and the gate refuses its promotion. The three readers each say so at the top of their page (REQ-DASH-204 criterion 13, as the page words it on 1 November 2019, on the bootstrap of 2026-10-25): Notifications "No promoted Client Register for 2019-Q4. One of this supply's checks needs it, so it could not run. That is not a fault in this supply's own data." (when it runs again is said once, on the verdict line above it: "Nothing needs deciding on this supply"); Investigations the same with "2 of this supply's checks need it, so they could not run"; Placements the same as Notifications. Checks are counted as the grid's rows, one per check however many tools ran it (UX critic on 7093c20, B2). The Client Register's own banner ends "Affects Notifications, Investigations and Placements.". **Breaks as**: one of the two files taken as the quarter's supply, or the three readers' cross-table checks evaluated against either.

**What it would look like if the rule were wrong.** One of the two files taken as the quarter's supply, or the three readers' cross-table checks evaluated against either.

*Config: quarterly, Feb/May/Aug/Nov, due 09:00 on the 1st, claim window 14 days. 2019-Q4's delivery carries the usual files and two Client Registers - cp_clients.csv at 08:30 and a re-export, cp_clients_v2.csv, at 08:40 whose rows differ (each re-pulled an hour later) - both before due; a clean cp_clients.csv follows alone on 29 November at 10:00, after due and before 2020-Q1's window opens, built passing (REQ-GEN-184) after one passing lead-in quarter (2019-Q3) and before a passing one (2020-Q1).*

| Where to look | |
|---|---|
| Dataset | cp-clients |
| Supplies | `cp_clients__201911010830000800`, `cp_clients__201911291000000800` |
| Period | 2020-Q1 |
| Set "in the warehouse on" to | 2019-11-01 |
| Built to | Pass, the 2019-11-29 10:00 arrival |

### TS-42b - A contested pair of one Child Protection table, resolved by a later file

TS-42a's placement; this link opens on the later file's asset day. *Config: as TS-42a.* **Expect** (bootstrap of 2026-10-19): the 29 November cp_clients.csv files to 2019-Q4, late, and supersedes the pair: "Two files for one table — superseded by the supply received 10:00am Friday, 29 November 2019". It is promoted on 5 December, and the three readers are re-evaluated by the knock-on at the same instant. **Breaks as**: the pair still contested after the later file, or the later file filed as a resupply rather than ending the contest.

**What it would look like if the rule were wrong.** The pair still contested after the later file, or the later file filed as a resupply rather than ending the contest.

*Config: as TS-42a.*

| Where to look | |
|---|---|
| Dataset | cp-clients |
| Supplies | `cp_clients__201911010830000800`, `cp_clients__201911291000000800` |
| Period | 2020-Q1 |
| Set "in the warehouse on" to | 2019-11-29 |
| Built to | Pass, the 2019-11-29 10:00 arrival |

### TS-54 - A period substituted onto an earlier promoted supply

In the data since 2026-10-15 (REQ-GEN-044 criterion 1; Keith, 2026-10-14, Q13): demonstrated by TS-76's placement - cp-placements' 2025-Q1 substituted by a scripted person onto 2024-Q4, whose cp-placements supply was promoted passing - with its own link while the substitution stands. CORRECTED 2026-10-16 (post-build-review #207 D1): REQ-GEN-207 moved the ordinary Warn drawn for 2026-Q3 to 2024-Q4 and this entry then said "promoted warning", but that Warn dirties only cp_carers and cp_clients, so cp-placements' 2024-Q4 supply is still passing and promoted. Whether it should be a Warn is with Keith. The script's `stands_on` field (REQ-GEN-200) answered the old blocker.

| Where to look | |
|---|---|
| Dataset | cp-placements |
| Supplies | — |
| Period | 2025-Q2 |
| Set "in the warehouse on" to | 2025-02-17 |

### TS-56 - A supply whose columns arrive in another order

**What it demonstrates.** It loads as usual, because columns are matched by name; its column-order file check WARNS, shown in the dataset's file section, and the dataset's status is unchanged by it (REQ-QAC-096 criteria 12 and 18, REQ-DASH-097 criterion 7, REQ-GEN-044 criterion 16).

**What it would look like if the rule were wrong.** Refused, or the dataset turned to Warn or Fail by a warning.

*Config: quarterly, Feb/May/Aug/Nov.*

| Where to look | |
|---|---|
| Dataset | cp-carers |
| Supplies | `cp_carers__202608010900000800` |
| Period | 2026-Q4 |
| Set "in the warehouse on" to | 2026-08-01 |

### TS-80 - A contested pair of one Child Protection table, settled by a person

PLANTED by REQ-GEN-203 (2026-10-18) in a grown quarter (REQ-GEN-207): a stray test file (TS-71's shape) beside the real Client Register, so a settlement can be seen clearing the cross-table readers the contest held, which only Child Protection has. Its link opens on the pair's arrival day. *Config: quarterly, Feb/May/Aug/Nov, due 09:00 on the 1st, claim window 14 days. 2020-Q4's delivery carries the usual files and two Client Registers - a stray test file, cp_clients_TEST.csv, every client named TEST, at 08:20 on the due day and the real cp_clients.csv at 08:30, both before 09:00 - after one passing lead-in quarter (2020-Q3) and before a passing one (2021-Q1), the real extract built passing. A scripted person settles the pair at 11:00 the next day (contract/scripted_decisions.yaml, "TS-80 settle"): file one by receipt, the test file, rejected; file two, the real extract, the quarter's supply.* **Expect** (re-quoted from the bootstrap of 2026-10-30, post-build-review #284 (B)): the settlement is one act over both files, so it takes effect at one instant, the later of its own and file one's lagged refusal - 7:35am Sunday, 8 November 2020, not the scripted 11:00 on 2 November. On 1 to 7 November 2020 cp-clients reads "Two files for one table"; from 8 November, "Settled · Two files for one table — settled by Robin Hale, 7:35am Sunday, 8 November 2020", cp_clients_TEST.csv rejected and cp_clients.csv the quarter's supply. The re-check it owed runs at 7:35am and the gate promotes it; the knock-on re-evaluates the three readers and promotes them at the same instant (post-build-review #251). On 1 November 2020 each reader says so at the top of its page (REQ-DASH-204 criterion 13, as the page words it on the bootstrap of 2026-10-25): Notifications "No promoted Client Register for 2020-Q4. One of this supply's checks needs it, so it could not run. That is not a fault in this supply's own data." (when it runs again is said once, on the verdict line above it: "Nothing needs deciding on this supply"); Investigations the same with "2 of this supply's checks need it, so they could not run"; Placements the same as Notifications. Checks are counted as the grid's rows, one per check however many tools ran it (UX critic on 7093c20, B2). From 8 November, once re-evaluated, none of the three shows the line. On the page (REQ-DASH-264): on 1 November cp-clients' own checks read "No data" and its cross-table rows at Fail, each named "<reader> → Client Register", with the banner saying the cross-table checks did run; from 8 November the readers' Client reference reads Pass ("Re-checked 7:35am Sunday, 8 November 2020, when the Client Register was re-checked"), the re-check's result shown though it was recorded under cp-clients' run. **Breaks as**: the test rows checked as the quarter's supply, the readers left contested after the settlement, or the file named by sorted name rather than by receipt position.

**What it would look like if the rule were wrong.** The test rows checked as the quarter's supply, the readers left contested after the settlement, or the file named by sorted name rather than by receipt position.

*Config: quarterly, Feb/May/Aug/Nov, due 09:00 on the 1st, claim window 14 days. 2020-Q4's delivery carries the usual files and two Client Registers - a stray test file, cp_clients_TEST.csv, every client named TEST, at 08:20 on the due day and the real cp_clients.csv at 08:30, both before 09:00 - after one passing lead-in quarter (2020-Q3) and before a passing one (2021-Q1), the real extract built passing. A scripted person settles the pair at 11:00 the next day (contract/scripted_decisions.yaml, "TS-80 settle"): file one by receipt, the test file, rejected; file two, the real extract, the quarter's supply.*

| Where to look | |
|---|---|
| Dataset | cp-clients |
| Supplies | `cp_clients__202011010820000800` |
| Period | 2021-Q1 |
| Set "in the warehouse on" to | 2020-11-01 |
| Built to | Pass, the 2020-11-01 08:30 arrival |

### TS-81 - S1 pass - a clean Client Register promoted beside the warehouse's Notifications, its package-mate held back

**What it demonstrates.** Notifications v2 is held back (refused on its own data); Clients v2's Notifications -> Client Register check is re-run against Notifications v1 in the warehouse, passes, and Clients v2 replaces Clients v1 under the 'when passing' setting (REQ-PIPE-267 criterion 6, REQ-PIPE-123).

**What it would look like if the rule were wrong.** Clients v2 held back with its package-mate, or promoted on a verdict that read the held-back Notifications v2.

*Config: quarterly, Feb/May/Aug/Nov, due 09:00 on the 1st; Child Protection's replacement setting is 'when passing' for 2017-Q2 and 2017-Q3 (contract/data-asset.yaml, Keith 2026-10-25). 2017-Q2's five tables arrive on time, clean, and are promoted; on 15 May 2017 at 10:00 a zip of a clean cp_clients and a cp_notifications failing on its own data arrives. A scripted person rejects that Notifications three weeks later (contract/ scripted_decisions.yaml, "TS-81 reject"), so it waits on no later page.*

| Where to look | |
|---|---|
| Dataset | cp-clients |
| Supplies | `cp_clients__201705010900000800`, `cp_clients__201705151000000800` |
| Period | 2017-Q3 |
| Set "in the warehouse on" to | 2017-05-15 |

### TS-82 - S1 fail - a Client Register re-checked against the warehouse's Notifications and held back

**What it demonstrates.** Notifications v2 is held back on its own data; Clients v2's re-check against Notifications v1 fails, so Clients v2 is held back ('promotion-withheld' naming Notifications v2, re-checked against Notifications v1) and Clients v1 stays. Its root is Clients v2 itself - its own check failed (Keith, 2026-10-25, answer 3a).

**What it would look like if the rule were wrong.** Clients v2 promoted, or refused without the re-check.

*Config: as TS-81, in 2017-Q3, the zip's cp_clients missing the five clients only the quarter's Notifications point at (no Investigation or Placement does). A scripted person rejects both files of the zip three weeks later.*

| Where to look | |
|---|---|
| Dataset | cp-clients |
| Supplies | `cp_clients__201708010900000800`, `cp_clients__201708151000000800` |
| Period | 2017-Q4 |
| Set "in the warehouse on" to | 2017-08-15 |

### TS-83 - S2 strict as re-cast - a failing Client Register holds its whole first-time package back

**What it demonstrates.** Clients is held back on its own data; Notifications, Investigations and Placements are re-checked against no Client Register in the warehouse and held back with it ('promotion-withheld', could not be checked); Carer Register and Case Workers are promoted. The resend is gated as one package and all four are promoted, superseding the first four.

**What it would look like if the rule were wrong.** Notifications judged alone and promoted, or held back without the re-check.

*Config: quarterly, Feb/May/Aug/Nov, due 09:00 on the 1st. 2016-Q3's six tables arrive together on time, the quarter's first supply, cp_clients failing on its own data and the other five clean. On 29 August a corrected cp_clients and its three readers are resent together.*

| Where to look | |
|---|---|
| Dataset | cp-clients |
| Supplies | `cp_clients__201608010900000800`, `cp_clients__201608291000000800` |
| Period | 2016-Q4 |
| Set "in the warehouse on" to | 2016-08-29 |

### TS-84 - The S10 chain re-ordered - three staggered files promoted together at the last one's arrival

**What it demonstrates.** Carer Register is promoted at 08:30; Notifications, Placements and Investigations each wait failing for want of a Client Register ('promotion-withheld'); at 09:20 the Client Register's arrival gates them with it and all four are promoted together (REQ-PIPE-267 criterion 2).

**What it would look like if the rule were wrong.** Any of the three left waiting after the Client Register, or Clients promoted alone.

*Config: quarterly, Feb/May/Aug/Nov, due 09:00 on the 1st, 8 hours' grace. 2015-Q4's one delivery, the quarter's first, each file its own receipt: Carer Register 08:30, Notifications 08:40, Placements 08:50, Investigations 09:00, Client Register 09:20, all clean.*

| Where to look | |
|---|---|
| Dataset | cp-clients |
| Supplies | `cp_clients__201511010920000800` |
| Period | 2016-Q1 |
| Set "in the warehouse on" to | 2015-11-01 |

### TS-85 - S14 - a failing Placements held back alone in a first-time package

**What it demonstrates.** Placements is held back on its own data; Client Register, Notifications, Investigations, Carer Register and Case Workers are promoted - no check they count reads a Placements the period will hold. The corrected Placements is promoted, superseding the first.

**What it would look like if the rule were wrong.** A reader of Placements held back with it.

*Config: quarterly, Feb/May/Aug/Nov, due 09:00 on the 1st. 2016-Q1's six tables arrive together on time, the quarter's first supply, cp_placements failing on its own data and the other five clean. On 29 February a corrected cp_placements arrives alone.*

| Where to look | |
|---|---|
| Dataset | cp-placements |
| Supplies | `cp_placements__201602010900000800`, `cp_placements__201602291000000800` |
| Period | 2016-Q2 |
| Set "in the warehouse on" to | 2016-02-29 |

## Calendar corrections

### TS-57a - A correction that only re-judges, before it is confirmed

**What it demonstrates.** The quarter reads late. Nothing on the page names the correction on this date: the replay confirms it only at the end of the history, and the page never shows a past correction as awaiting (Keith, 2026-10-19). Before confirmation, `mothman supply corrections --reference REQ-GEN-205` previews one verdict change (late -> on time) and no moves (REQ-PIPE-168 criteria 3-6).

**What it would look like if the rule were wrong.** Applied on merge with nobody confirming because there were no moves.

*Config: 2015-Q1's date is corrected from 1 to 2 February 2015; its one supply arrives at 12:00 on 2 February - late against the old date, on time against the corrected one.*

| Where to look | |
|---|---|
| Dataset | ed-presentations |
| Supplies | `ed_presentations__201502021200000800` |
| Period | 2015-Q1 |
| Set "in the warehouse on" to | 2026-09-08 |

### TS-57b - A correction that only re-judges, once confirmed

**What it demonstrates.** A new verdict naming the change reference, on time; the late verdict still readable as history.

**What it would look like if the rule were wrong.** The late verdict overwritten, or no verdict naming the correction.

*Config: as TS-57a.*

| Where to look | |
|---|---|
| Dataset | ed-presentations |
| Supplies | `ed_presentations__201502021200000800` |
| Period | 2015-Q1 |
| Set "in the warehouse on" to | 2026-09-25 |

### TS-58a - A correction that moves a supply, before it is confirmed

**What it demonstrates.** The supply reads filed to 2013-Q3, as a resupply. Nothing on the page names the correction on this date: the replay confirms it only at the end of the history, and the page never shows a past correction as awaiting (Keith, 2026-10-19). Before confirmation, `mothman supply corrections --reference REQ-GEN-205` previews the move 2013-Q3 -> 2013-Q4 with its re-judged verdict.

**What it would look like if the rule were wrong.** Moved on merge, or proposed with the verdict computed against 2013-Q3.

*Config: 2013-Q4's date is corrected from 1 November to 20 October 2013. Its supply arrives on 10 October, before the old window opened, so it is filed as a resupply of 2013-Q3; the corrected window covers it.*

| Where to look | |
|---|---|
| Dataset | ed-presentations |
| Supplies | `ed_presentations__201310101000000800` |
| Period | 2013-Q4 |
| Set "in the warehouse on" to | 2026-09-08 |

### TS-58b - A correction that moves a supply, once confirmed

**What it demonstrates.** Re-filed to 2013-Q4 as a re-file naming the correction, re-QA'd and re-gated, judged against 2013-Q4 (REQ-PIPE-170 criteria 2, 7).

**What it would look like if the rule were wrong.** Left in 2013-Q3, or moved and not re-QA'd.

*Config: as TS-58a.*

| Where to look | |
|---|---|
| Dataset | ed-presentations |
| Supplies | `ed_presentations__201310101000000800` |
| Period | 2013-Q4 |
| Set "in the warehouse on" to | 2026-09-25 |

### TS-59a - A supply the asset manager will keep, before the correction is confirmed

**What it demonstrates.** The supply reads filed to 2014-Q2, as a resupply. Nothing on the page names the correction on this date: the replay confirms it only at the end of the history, and the page never shows a past correction as awaiting (Keith, 2026-10-19). Before confirmation, `mothman supply corrections --reference REQ-GEN-205` previews the move like TS-58a's.

**What it would look like if the rule were wrong.** Kept or moved before anyone confirmed.

*Config: as TS-58 for 2014-Q3, corrected from 1 August to 20 July 2014; its supply arrives on 10 July, filed as a resupply of 2014-Q2, which the corrected agreement would move. A scripted confirmation keeps it (contract/scripted_decisions.yaml).*

| Where to look | |
|---|---|
| Dataset | ed-presentations |
| Supplies | `ed_presentations__201407101000000800` |
| Period | 2014-Q3 |
| Set "in the warehouse on" to | 2026-09-08 |

### TS-59b - A supply the asset manager kept

**What it demonstrates.** The supply stays filed where it is, with a KEPT decision-log entry naming it, its period, the change reference, the actor and the reason, and its verdict judged against the period it stays in (REQ-PIPE-170 criteria 5, 6, 22). 2014-Q3, which the kept supply leaves empty, reads Fail "No supply" for good - the scenario's own consequence, left at Fail (Keith, 2026-10-19).

**What it would look like if the rule were wrong.** Moved anyway, kept silently with no reason, or re-judged against the period it did not go to.

*Config: as TS-59a.*

| Where to look | |
|---|---|
| Dataset | ed-presentations |
| Supplies | `ed_presentations__201407101000000800` |
| Period | 2014-Q3 |
| Set "in the warehouse on" to | 2026-09-25 |

### TS-60a - A correction that leaves a supply with no period, before it is confirmed

**What it demonstrates.** The supply reads filed to 2013-Q1. Nothing on the page names the correction on this date: the replay confirms it only at the end of the history, and the page never shows a past correction as awaiting (Keith, 2026-10-19). Before confirmation, `mothman supply corrections --reference REQ-GEN-205` previews it as "would be held".

**What it would look like if the rule were wrong.** Held, or dropped, before confirmation.

*Config: Emergency Department's first quarter, 2013-Q1, has its date corrected from 1 to 11 February 2013. Its supply arrived on 22 January, inside the old window, before the corrected one opens and with no quarter before it.*

| Where to look | |
|---|---|
| Dataset | ed-presentations |
| Supplies | `ed_presentations__201301221000000800` |
| Period | 2013-Q1 |
| Set "in the warehouse on" to | 2026-09-08 |

### TS-60b - A supply left with no period, once confirmed

**What it demonstrates.** Held (REQ-PIPE-064), the hold's reason naming the correction: "Held when correction REQ-GEN-205 was confirmed: the corrected calendar offers it no period". 2013-Q1 reads Fail "No supply" for good - the scenario's own consequence, left at Fail (Keith, 2026-10-19).

**What it would look like if the rule were wrong.** Left filed in a period the corrected agreement does not give it, or dropped.

*Config: as TS-60a.*

| Where to look | |
|---|---|
| Dataset | ed-presentations |
| Supplies | `ed_presentations__201301221000000800` |
| Period | 2013-Q1 |
| Set "in the warehouse on" to | 2026-09-25 |

### TS-61a - A move that will be blocked, before the correction is confirmed

**What it demonstrates.** The supply reads filed to 2015-Q3. Nothing on the page names the correction on this date: the replay confirms it only at the end of the history, and the page never shows a past correction as awaiting (Keith, 2026-10-19). Before confirmation, `mothman supply corrections --reference REQ-GEN-205` previews the move, naming the period that stands on it.

**What it would look like if the rule were wrong.** Moved out from under the inheriting period.

*Config: 2015-Q3's date is corrected from 1 to 11 August 2015. Its supply arrived on 22 July, which the corrected agreement files to 2015-Q2 - a move blocked because 2015-Q4, the participation gap (REQ-GEN-251), stands on it.*

| Where to look | |
|---|---|
| Dataset | ed-presentations |
| Supplies | `ed_presentations__201507221000000800` |
| Period | 2015-Q3 |
| Set "in the warehouse on" to | 2026-09-08 |

### TS-61b - A move that is blocked, once confirmed

**What it demonstrates.** Parked as blocked, naming the decision that would unblock it - not moved, not dropped; the correction stays among the states needing action (REQ-PIPE-170 criteria 9, 19).

**What it would look like if the rule were wrong.** Moved, or the correction marked done with the supply silently left.

*Config: as TS-61a.*

| Where to look | |
|---|---|
| Dataset | ed-presentations |
| Supplies | `ed_presentations__201507221000000800` |
| Period | 2015-Q3 |
| Set "in the warehouse on" to | 2026-09-25 |

### TS-63a - A dataset turned off for a while: the turn-off

PLANTED by REQ-GEN-218 (2026-10-18) in Child Protection's grown history. *Config: Child Protection, quarterly Feb/May/Aug/Nov, due 09:00 on the 1st, 14-day claim window. cp-carers is turned off after 31 December 2021 by correction REQ-GEN-218 dated 15 December 2021, and owed again from 2022-Q3. 2021-Q4's delivery leaves cp_carers out; cp_carers follows on 5 January 2022, after the turn-off but while 2021-Q4's slot is open.* **Expect** (bootstrap of 2026-10-19): from the correction's date the page reads "Turning off after Friday, 31 December 2021" (REQ-DASH-180 criterion 27). The 5 January cp_carers files to 2021-Q4, late, and is promoted; 2021-Q4 stays owed until its slot closes (REQ-PIPE-179, REQ-DASH-180). The correction itself shows on the page only once confirmed, at the end of the history - an earlier in-place-on date shows the turn-off as configured, with no correction awaiting (REQ-GEN-218 criterion 5, as amended 2026-10-19). **Breaks as**: the 5 January supply held instead of filed late, or 2021-Q4 going quiet before its slot closes.

**What it would look like if the rule were wrong.** The 5 January supply held instead of filed late, or 2021-Q4 going quiet before its slot closes.

*Config: Child Protection, quarterly Feb/May/Aug/Nov, due 09:00 on the 1st, 14-day claim window. cp-carers is turned off after 31 December 2021 by correction REQ-GEN-218 dated 15 December 2021, and owed again from 2022-Q3. 2021-Q4's delivery leaves cp_carers out; cp_carers follows on 5 January 2022, after the turn-off but while 2021-Q4's slot is open.*

| Where to look | |
|---|---|
| Dataset | cp-carers |
| Supplies | `cp_carers__202201051000000800`, `cp_carers__202203151000000800` |
| Period | 2022-Q1 |
| Set "in the warehouse on" to | 2021-12-20 |

### TS-63b - A dataset turned off for a while: the gap

TS-63a's placement; this link opens on 2021-Q4's delivery and runs to the end of the history. *Config: as TS-63a, with a further cp_carers arriving on 15 March 2022, in the gap. The ordinary deliveries inside the gap still carry the dataset's file, as a supplier still sending files would (REQ-GEN-218 criterion 5).* **Expect** (bootstrap of 2026-10-19): the 15 March supply, and each ordinary gap delivery's cp_carers (1 February and 1 May 2022), finds no open owed slot and is held as turned off. 2022-Q1 and 2022-Q2 read owed-nothing and inherit the 5 January supply: "Turned off since Saturday, 1 January 2022 · Inherited from 2021-Q4", with "2 received while turned off, earliest Tuesday, 1 February 2022 · 2 still held" on 20 March 2022 and 3 by the end of the history. From 2022-Q3 it reads as any dataset between deliveries. **Breaks as**: the gap read as missed supplies, or a gap arrival filed into a gap period.

**What it would look like if the rule were wrong.** The gap read as missed supplies, or a gap arrival filed into a gap period.

*Config: as TS-63a, with a further cp_carers arriving on 15 March 2022, in the gap. The ordinary deliveries inside the gap still carry the dataset's file, as a supplier still sending files would (REQ-GEN-218 criterion 5).*

| Where to look | |
|---|---|
| Dataset | cp-carers |
| Supplies | `cp_carers__202201051000000800`, `cp_carers__202203151000000800` |
| Period | 2022-Q1 |
| Set "in the warehouse on" to | 2022-03-20 |

### TS-75a - A supply rejected after it waited - while it waited

Cp-clients, 2024-Q1: the whole delivery on time at 09:00 on 1 February with cp_clients alone built failing by its own preset; the other five clean. *Config: quarterly, due 09:00 on the 1st; a person rejects it at 09:00 on 22 February; a corrected cp_clients alone arrives at 10:00 on 29 February.* **Expect** (REQ-DASH-197), on 8 February, in the as-at panel under the results' verdict line: the heading "On Thursday, 8 February 2024 the warehouse did not hold the latest file", the column "Latest arrival by Thursday, 8 February 2024 — not promoted" naming cp-clients@202402010900000800, and the reason "this supply was staged and nobody had decided about it yet". **What the other tables show**: the Fail clients turned notifications', investigations' and placements' own cross-table checks failing, so all three wait for a person on 8 and 25 February; carers waited until 11 February and then promoted passing; case workers promoted passing on 7 February. When the corrected cp_clients arrives the re-evaluation promotes clients, notifications, investigations and placements passing (11 March). **Breaks as**: no panel; or the reason "superseded" (post-build-review #164's reading, which this quarter is placed to avoid).

**What it would look like if the rule were wrong.** No panel; or the reason "superseded" (post-build-review #164's reading, which this quarter is placed to avoid).

*Config: quarterly, due 09:00 on the 1st; a person rejects it at 09:00 on 22 February; a corrected cp_clients alone arrives at 10:00 on 29 February.*

| Where to look | |
|---|---|
| Dataset | cp-clients |
| Supplies | `cp_clients__202402010900000800`, `cp_clients__202402291000000800` |
| Period | 2024-Q2 |
| Set "in the warehouse on" to | 2024-02-08 |

### TS-75b - A supply rejected after it waited - after it was rejected

The same placement, on 25 February. **Expect** (REQ-DASH-197), in the same panel: "On Sunday, 25 February 2024 the warehouse did not hold the latest file", the same supply, and the reason "a person had rejected this supply, so it was not promoted". The other tables as TS-75a's, carers now promoted. From 29 February the corrected supply fills the quarter and cp-clients ends healthy. **Breaks as**: the panel naming the corrected supply, or still "nobody had decided".

**What it would look like if the rule were wrong.** The panel naming the corrected supply, or still "nobody had decided".

| Where to look | |
|---|---|
| Dataset | cp-clients |
| Supplies | `cp_clients__202402010900000800`, `cp_clients__202402291000000800` |
| Period | 2024-Q2 |
| Set "in the warehouse on" to | 2024-02-25 |

### TS-76 - A substitution later removed

Cp-placements, 2025-Q1: the delivery leaves cp_placements out; a person substitutes the quarter onto 2024-Q4 at 09:00 on 3 February, and at 09:00 on 20 April - once the next quarter's window has opened - removes the substitution and marks the quarter not supplied, in that order, at one instant. *Config: quarterly, as TS-75a.* **Expect** (REQ-DASH-198), on 17 February: the pill "Substituted from 2024-Q4" beside the dataset's title, and in its drill-down, below the results' heading, "Since removed, as from Sunday, 20 April 2025". The quarter closes "not supplied (accepted)". **What cp-clients and cp-carers read for 2025-Q1** (H1): clients promoted WARNING on arrival and stays at Warn before, during and after the substitution - the Warn is the ordinary one drawn for this quarter, which the delivery keeps (REQ-GEN-199's PROVISIONAL choice); carers waited until 9 February, then promoted PASSING and stays at Pass. Neither is a Fail after the substitution ends: the cross-table checks reading cp_placements are filed under cp-placements, so in a quarter with no placements supply nothing runs them for clients or carers (the architect's H1 expected a Fail; post-build-review #174). **Breaks as**: no pill on 17 February; or "Since replaced".

**What it would look like if the rule were wrong.** No pill on 17 February; or "Since replaced".

| Where to look | |
|---|---|
| Dataset | cp-placements |
| Supplies | — |
| Period | 2025-Q2 |
| Set "in the warehouse on" to | 2025-02-17 |

### TS-77a - A substitution later replaced - while it stood

Cp-placements, 2023-Q2: the delivery leaves cp_placements out; a person substitutes onto 2023-Q1 at 09:00 on 3 May; cp_placements alone arrives at 10:00 on 8 June and the person promotes it at 10:00 on 9 June, which removes the substitution - one act, taking effect at one instant: 10:48pm Wednesday, 14 June 2023, the new supply's lagged refusal (post-build-review #284 (B); re-quoted from the bootstrap of 2026-10-30). *Config: quarterly, as TS-75a.* **Expect** (REQ-DASH-198), on 17 May: the pill "Substituted from 2023-Q1", and in its drill-down "Since replaced, as from Wednesday, 14 June 2023". **What cp-clients and cp-carers read for 2023-Q2**: both waited on 2 May; clients promoted WARNING (its quarter's drawn Warn, kept) on 7 May and carers PASSING on 3 May, and both stay so while the substitution stands, on 8 June and after the promotion. **Breaks as**: no pill; or "Since removed".

**What it would look like if the rule were wrong.** No pill; or "Since removed".

| Where to look | |
|---|---|
| Dataset | cp-placements |
| Supplies | `cp_placements__202306081000000800` |
| Period | 2023-Q3 |
| Set "in the warehouse on" to | 2023-05-17 |

### TS-77b - Known wrong today (post-build-review #164): A substitution later replaced - the day the late file waited

**What it demonstrates.** Today the as-at panel ("On Thursday, 8 June 2023 the warehouse did not hold the latest file") gives the late supply the reason "this one had been superseded - a newer version had arrived for the same period, a person had set it aside, or a later supply had been promoted into the period - so it was no longer what the period held" - against a period whose holder is a SUBSTITUTED supply, a variant of #164 - while the pill's drill-down reads "Since replaced, as from Wednesday, 14 June 2023" and "2023-Q2 holds 2023-Q1's supply; the results below are a newer supply awaiting a decision." Once #164 is decided the panel's reason line should say the supply was waiting for a decision. **Breaks as**: a different reason line in the panel means #164 was decided, not a regression; any other change on that date - the drill-down's sentences included - is a regression.

**What it would look like if the rule were wrong.** A different reason line in the panel means #164 was decided, not a regression; any other change on that date - the drill-down's sentences included - is a regression.

| Where to look | |
|---|---|
| Dataset | cp-placements |
| Supplies | `cp_placements__202306081000000800` |
| Period | 2023-Q3 |
| Set "in the warehouse on" to | 2023-06-08 |

### TS-79a - An inherited quarter - the newest

Cp-case-workers, the newest quarter before the build's own in which it is not delivered (2026-Q2 today), so it inherits the quarter before. Nothing generated; the placement is written after generation from the calendar's participation, in place on the middle of the quarter. *Config: quarterly; cp-case-workers participates only in Q1 and Q3.* **Expect** (REQ-DASH-198): the pill "Inherited from 2026-Q1" beside the dataset's title. The same page also shows an as-at panel and an "Awaiting a decision" verdict line about a May supply that is "not filed to any period": ordinary deliveries carry cp_case_workers in months it does not take part in, and each is held (TS-52's shape) - the pill, not the panel, is what this scenario points at. **Breaks as**: no pill; or a stale date after ANCHOR_DATE moves.

**What it would look like if the rule were wrong.** No pill; or a stale date after ANCHOR_DATE moves.

| Where to look | |
|---|---|
| Dataset | cp-case-workers |
| Supplies | — |
| Period | 2026-Q3 |
| Set "in the warehouse on" to | 2026-06-16 |

### TS-79b - An inherited quarter - the oldest of the original fifteen

**What it demonstrates.** Its page looks identical to TS-79a's - the pill "Inherited from 2023-Q1". **Breaks as**: no pill.

**What it would look like if the rule were wrong.** No pill.

| Where to look | |
|---|---|
| Dataset | cp-case-workers |
| Supplies | — |
| Period | 2023-Q3 |
| Set "in the warehouse on" to | 2023-06-16 |

## The linkage history, planted (REQ-GEN-335)

### TS-86 - A linkage release with an empty key

**What it demonstrates.** Linkage key recorded reads Fail on one row, and the release is held back (REQ-PIPE-332 criterion 3).

**What it would look like if the rule were wrong.** The empty key passed, or the whole release refused unloaded.

*Config: quarterly, due 18:00 with 8 hours' grace; 2016-Q3's release, one row's linkage_key empty.*

| Where to look | |
|---|---|
| Dataset | linkage-keys |
| Supplies | `linkage_keys__201608011730000800` |
| Period | 2016-Q3 |
| Set "in the warehouse on" to | 2016-08-01 |

### TS-87 - A dataset code nobody declared - a linked dataset as good as missing

**What it demonstrates.** Known dataset code reads Fail; ED Presentations' coverage reads 0 percent, Fail; its referential check finds no EDDC_PRESENTATION row to fail.

**What it would look like if the rule were wrong.** The renamed code matched by similarity, or coverage passing.

*Config: as TS-86; 2017-Q1's release codes every ED Presentations row EDDC_PRESENTATION_V2.*

| Where to look | |
|---|---|
| Dataset | linkage-keys |
| Supplies | `linkage_keys__201702011730000800` |
| Period | 2017-Q1 |
| Set "in the warehouse on" to | 2017-02-01 |

### TS-88 - A surplus identifier

**What it demonstrates.** No surplus identifiers reads Fail on that row; every other check passes.

**What it would look like if the rule were wrong.** The surplus id ignored, or read as a missing one.

*Config: as TS-86; 2018-Q1's release, one DOC_CLIENTS row carrying an id_2, the contract's id_2 column being blank in every ordinary release (PROVISIONAL).*

| Where to look | |
|---|---|
| Dataset | linkage-keys |
| Supplies | `linkage_keys__201802011730000800` |
| Period | 2018-Q1 |
| Set "in the warehouse on" to | 2018-02-01 |

### TS-89 - One record linked twice

**What it demonstrates.** Each record linked once reads Fail; coverage is unchanged.

**What it would look like if the rule were wrong.** The duplicate counted as two linked presentations.

*Config: as TS-86; 2018-Q2's release, one EDDC_PRESENTATION record under two keys.*

| Where to look | |
|---|---|
| Dataset | linkage-keys |
| Supplies | `linkage_keys__201805011730000800` |
| Period | 2018-Q2 |
| Set "in the warehouse on" to | 2018-05-01 |

### TS-90 - A link to a record the quarter does not hold

**What it demonstrates.** ED Presentations links match a presentation reads Fail, its failing row the code and identifier; the result counts toward ED Presentations as well (REQ-PIPE-332 criterion 1).

**What it would look like if the rule were wrong.** The dangling row passed, or the Fail kept off ED's page.

*Config: as TS-86; 2018-Q3's release, one EDDC_PRESENTATION row naming a presentation not in ED's 2018-Q3 supply.*

| Where to look | |
|---|---|
| Dataset | linkage-keys |
| Supplies | `linkage_keys__201808011730000800` |
| Period | 2018-Q3 |
| Set "in the warehouse on" to | 2018-08-01 |

### TS-91 - Coverage in the warn band

**What it demonstrates.** Client Register coverage reads Warn, worded below its band; the release promotes as a Warn does (REQ-DASH-337).

**What it would look like if the rule were wrong.** Worded "above 90 percent", or read Pass.

*Config: as TS-86; 2018-Q4's release links 85.5 to 89.5 percent of the Client Register's rows.*

| Where to look | |
|---|---|
| Dataset | linkage-keys |
| Supplies | `linkage_keys__201811011730000800` |
| Period | 2018-Q4 |
| Set "in the warehouse on" to | 2018-11-01 |

### TS-92 - Coverage in the fail band

**What it demonstrates.** ED Presentations coverage reads Fail, a percentage only, no failing rows; the release is held back.

**What it would look like if the rule were wrong.** Failing rows recorded for coverage, or Warn.

*Config: as TS-86; 2019-Q2's release links 78 to 84 percent of ED Presentations' rows.*

| Where to look | |
|---|---|
| Dataset | linkage-keys |
| Supplies | `linkage_keys__201905011730000800` |
| Period | 2019-Q2 |
| Set "in the warehouse on" to | 2019-05-01 |

### TS-93a - A Client Register held failing and rejected - its side of TS-93b

**What it demonstrates.** Cp_clients held back on its own data, then rejected; its readers held for want of a Client Register until a person promotes them, so none waits on a later page.

**What it would look like if the rule were wrong.** The failing Client Register promoted.

*Config: quarterly, Feb/May/Aug/Nov, due 09:00 on the 1st; 2019-Q1's six tables arrive on the 1 November 2018 round, cp_clients alone built failing; a scripted person rejects it three weeks later ("TS-93 reject") and nothing replaces it; an hour later the same person promotes its three readers ("TS-93 promote notifications", "... investigations", "... placements").*

| Where to look | |
|---|---|
| Dataset | cp-clients |
| Supplies | `cp_clients__201811010900000800` |
| Period | 2019-Q1 |
| Set "in the warehouse on" to | 2018-11-01 |

### TS-93b - A linkage release whose Client Register is not in the warehouse

**What it demonstrates.** The release's two cp-clients checks read Fail, could not run, naming the rejected Client Register; ED Presentations' checks are evaluated.

**What it would look like if the rule were wrong.** The cp-clients checks evaluated against another quarter's Client Register, or left out of scope as if marked not supplied.

*Config: as TS-86; 2019-Q1's release, built from the Client Register as received, checked with TS-93a's supply rejected.*

| Where to look | |
|---|---|
| Dataset | linkage-keys |
| Supplies | `linkage_keys__201902011730000800` |
| Period | 2019-Q1 |
| Set "in the warehouse on" to | 2019-02-01 |

### TS-94 - A failing linkage release promoted by a person

**What it demonstrates.** Held back failing; from the promotion, the Client Register promoted passing on the 1 February 2022 round reads 'Promoted, failing' (REQ-PIPE-332 criterion 4), and earlier dates still show it passing.

**What it would look like if the rule were wrong.** The Client Register demoted, or coloured before the promotion.

*Config: as TS-86; 2022-Q2's release, one DOC_CLIENTS row naming a client the quarter does not hold; a scripted person promotes it two days later ("TS-94 promote", REQ-PIPE-332 criterion 8).*

| Where to look | |
|---|---|
| Dataset | linkage-keys |
| Supplies | `linkage_keys__202205011730000800` |
| Period | 2022-Q2 |
| Set "in the warehouse on" to | 2022-05-01 |

### TS-95 - A linked dataset marked not supplied - named, not planted

**What it demonstrates.** The release's cp-clients checks are left out of scope with reason code not_supplied_by_decision, while ED Presentations' are evaluated (REQ-PIPE-332 criterion 7).

**What it would look like if the rule were wrong.** Cp-clients' checks read Fail, could not run.

*Config: quarterly; Child Protection has no supply for 2015-Q2 and its existing scripted entry marks cp-clients not supplied; the 2015-Q2 release is an ordinary one.*

| Where to look | |
|---|---|
| Dataset | linkage-keys |
| Supplies | `linkage_keys__201505011725000800` |
| Period | 2015-Q2 |
| Set "in the warehouse on" to | 2015-05-01 |

### TS-96 - A quarter with no linkage release

**What it demonstrates.** The slot closes unfilled and reads not supplied (accepted) (REQ-PIPE-132, REQ-DASH-133).

**What it would look like if the rule were wrong.** A Fail "No supply" gap left needing action.

*Config: quarterly, due 18:00; no release comes for 2020-Q3, and a scripted person marks it not supplied the day after its slot closed, 19 October 2020 ("TS-96 not supplied").*

| Where to look | |
|---|---|
| Dataset | linkage-keys |
| Supplies | — |
| Period | 2020-Q3 |
| Set "in the warehouse on" to | 2020-10-19 |

### TS-97 - Large key groups in the warn band

**What it demonstrates.** Large key groups reads Warn, with the count of keys, the count of large groups and their histogram across several bins, and no key value.

**What it would look like if the rule were wrong.** A key value recorded, or the histogram drawn over every key.

*Config: as TS-86; 2021-Q3's release, records re-keyed into groups of 51 to 230 records until just over 2 percent of distinct keys are large groups.*

| Where to look | |
|---|---|
| Dataset | linkage-keys |
| Supplies | `linkage_keys__202108011730000800` |
| Period | 2021-Q3 |
| Set "in the warehouse on" to | 2021-08-01 |

### TS-98 - Large key groups in the fail band

**What it demonstrates.** Large key groups reads Fail and the release is held back.

**What it would look like if the rule were wrong.** Warn, or every key counted as a group.

*Config: as TS-97; 2022-Q3's release, groups of 51 to 70 records until just over 4 percent of distinct keys are large groups.*

| Where to look | |
|---|---|
| Dataset | linkage-keys |
| Supplies | `linkage_keys__202208011730000800` |
| Period | 2022-Q3 |
| Set "in the warehouse on" to | 2022-08-01 |

### TS-99 - A blank expected identifier

**What it demonstrates.** Expected identifiers present reads Fail; the Client Register's referential check also fails on that row, which matches no client.

**What it would look like if the rule were wrong.** The blank read as a value.

*Config: as TS-86; 2022-Q4's release, one DOC_CLIENTS row's id_1 blank.*

| Where to look | |
|---|---|
| Dataset | linkage-keys |
| Supplies | `linkage_keys__202211011730000800` |
| Period | 2022-Q4 |
| Set "in the warehouse on" to | 2022-11-01 |

### TS-100a - A Client Register held failing, then promoted by a person - its side of TS-100b

**What it demonstrates.** Held back on its own data until the person promotes it; its readers re-checked and promoted with it.

**What it would look like if the rule were wrong.** Promoted by the rule.

*Config: quarterly, Feb/May/Aug/Nov, due 09:00 on the 1st; 2019-Q3's six tables arrive on the 1 May 2019 round, cp_clients alone built failing and held; a scripted person promotes it at 10:00 on 2 August 2019 ("TS-100 promote"), the day after the quarter's linkage release.*

| Where to look | |
|---|---|
| Dataset | cp-clients |
| Supplies | `cp_clients__201905010900000800` |
| Period | 2019-Q3 |
| Set "in the warehouse on" to | 2019-05-01 |

### TS-100b - A linkage release cleared by a person's promotion

**What it demonstrates.** Its cp-clients checks read Fail, could not run, until 10:00 on 2 August 2019, when the promotion's knock-on re-checks them and they pass (REQ-PIPE-331 criterion 5).

**What it would look like if the rule were wrong.** Still failing after the promotion, or evaluated against the held supply before it.

*Config: as TS-86; 2019-Q3's release, ordinary rows, received while TS-100a's Client Register is held.*

| Where to look | |
|---|---|
| Dataset | linkage-keys |
| Supplies | `linkage_keys__201908011730000800` |
| Period | 2019-Q3 |
| Set "in the warehouse on" to | 2019-08-01 |

### TS-101 - Emergency Department's same-round Fail, clearing

**What it demonstrates.** The release's ED Presentations checks read Fail, could not run, and clear through the knock-on once the resupply is promoted (REQ-GEN-334 criteria 9 and 12); ED's own page is not coloured by them.

**What it would look like if the rule were wrong.** ED's page coloured by a not-evaluated result, or the release re-timed to avoid the Fail.

*Config: as TS-86; 2021-Q4's release, received while ED Presentations' Fail supply of the morning is held, its resupply arriving days later; no ED arrival moved, no release re-timed.*

| Where to look | |
|---|---|
| Dataset | linkage-keys |
| Supplies | `linkage_keys__202111011730000800` |
| Period | 2021-Q4 |
| Set "in the warehouse on" to | 2021-11-01 |

## The geocoding history, planted (REQ-GEN-298)

### TS-93c - A Client Register geocode whose source was rejected - named, not planted

**What it demonstrates.** Its two cp-clients checks read Fail, could not run, and the file is held back for the rest of the history, as TS-93b's linkage release is.

**What it would look like if the rule were wrong.** The checks evaluated against another quarter's Client Register.

*Config: quarterly, due 19:00; 2019-Q1's ordinary Client Register Geocodes, received while TS-93a's Client Register is held and then rejected, nothing replacing it.*

| Where to look | |
|---|---|
| Dataset | geo-cp-clients |
| Supplies | `geo_cp_clients__201902011843000800` |
| Period | 2019-Q1 |
| Set "in the warehouse on" to | 2019-02-01 |

### TS-100c - A Client Register geocode cleared by a person's promotion - named, not planted

**What it demonstrates.** Its cp-clients checks read Fail, could not run, until 10:00 on 2 August 2019, when the promotion's knock-on re-checks them and they pass.

**What it would look like if the rule were wrong.** Still failing after the promotion.

*Config: as TS-93c; 2019-Q3's ordinary Client Register Geocodes, received while TS-100a's Client Register is held.*

| Where to look | |
|---|---|
| Dataset | geo-cp-clients |
| Supplies | `geo_cp_clients__201908011817000800` |
| Period | 2019-Q3 |
| Set "in the warehouse on" to | 2019-08-01 |

### TS-101b - An ED geocode while ED's same-round Fail is held - named, not planted

**What it demonstrates.** Its ed-presentations checks read Fail, could not run, and clear through the knock-on once the resupply is promoted.

**What it would look like if the rule were wrong.** ED's page coloured by a not-evaluated result.

*Config: as TS-93c; 2021-Q4's ordinary ED Presentations Geocodes, built from ED's Fail supply of the morning, its share not geocoded in the warn band, received while that supply is held.*

| Where to look | |
|---|---|
| Dataset | geo-ed-presentations |
| Supplies | `geo_ed_presentations__202111011850000800` |
| Period | 2021-Q4 |
| Set "in the warehouse on" to | 2021-11-01 |

### TS-102 - A missing census year

**What it demonstrates.** Missing census years reads Fail, each sample the record and the missing year; every other check passes.

**What it would look like if the rule were wrong.** The record read as left out, or the year check passing.

*Config: quarterly, due 19:00 with 8 hours' grace; 2023-Q2's Client Register Geocodes, one census year's rows dropped for one to three records, the record's other years present - two or more years in force since 2017-Q3.*

| Where to look | |
|---|---|
| Dataset | geo-cp-clients |
| Supplies | `geo_cp_clients__202305011830000800` |
| Period | 2023-Q2 |
| Set "in the warehouse on" to | 2023-05-01 |

### TS-103 - A duplicated census year

**What it demonstrates.** Duplicated census years reads Fail; every other check passes.

**What it would look like if the rule were wrong.** The repeat read as a second record.

*Config: as TS-102; 2022-Q1's ED Presentations Geocodes, one census year's row repeated, identical in every column, for one to three presentations.*

| Where to look | |
|---|---|
| Dataset | geo-ed-presentations |
| Supplies | `geo_ed_presentations__202202011830000800` |
| Period | 2022-Q1 |
| Set "in the warehouse on" to | 2022-02-01 |

### TS-104 - An unexpected census year

**What it demonstrates.** Unexpected census years reads Fail on the 2026 rows; every other check passes.

**What it would look like if the rule were wrong.** 2026 read as in the set, or caught by a type check.

*Config: as TS-102; 2016-Q2's Client Register Geocodes, a row for census year 2026 for one to three records - 2026 joins the set only from 2027-Q3.*

| Where to look | |
|---|---|
| Dataset | geo-cp-clients |
| Supplies | `geo_cp_clients__201605011830000800` |
| Period | 2016-Q2 |
| Set "in the warehouse on" to | 2016-05-01 |

### TS-105 - The share not geocoded in the warn band

**What it demonstrates.** Share not geocoded reads Warn; the drift check over placed rows passes; the file promotes as a Warn does.

**What it would look like if the rule were wrong.** Fail, or the drift check warning too.

*Config: as TS-102; 2023-Q1's ED Presentations Geocodes, whole presentations turned not geocoded in every year, codes empty, until the share lies between 6 and 9 percent.*

| Where to look | |
|---|---|
| Dataset | geo-ed-presentations |
| Supplies | `geo_ed_presentations__202302011830000800` |
| Period | 2023-Q1 |
| Set "in the warehouse on" to | 2023-02-01 |

### TS-106 - The share not geocoded in the fail band

**What it demonstrates.** Share not geocoded reads Fail and the file is held back.

**What it would look like if the rule were wrong.** Warn, or the format checks failing the empty codes.

*Config: as TS-105; 2024-Q1's Client Register Geocodes, until the share lies between 12 and 18 percent.*

| Where to look | |
|---|---|
| Dataset | geo-cp-clients |
| Supplies | `geo_cp_clients__202402011830000800` |
| Period | 2024-Q1 |
| Set "in the warehouse on" to | 2024-02-01 |

### TS-107 - Coverage in the warn band

**What it demonstrates.** Source records matched reads Warn; the missing-year check, which counts only records present, passes.

**What it would look like if the rule were wrong.** Missing census years failing, or coverage Pass.

*Config: as TS-102; 2021-Q2's ED Presentations Geocodes, 0.5 to 1.5 percent of the quarter's presentations left out in every year. (Moved from 2014-Q1 on 2026-11-14, post-build-review #322: the quarter before it had no accepted ED geocodes, so drift read Fail across the gap beside the planted Warn.)*

| Where to look | |
|---|---|
| Dataset | geo-ed-presentations |
| Supplies | `geo_ed_presentations__201402011830000800` |
| Period | 2014-Q1 |
| Set "in the warehouse on" to | 2014-02-01 |

### TS-108 - Coverage in the fail band

**What it demonstrates.** Source records matched reads Fail, a percentage only; the file is held back, so its Fail does not colour the Client Register.

**What it would look like if the rule were wrong.** Failing rows recorded for coverage, or the Client Register coloured before the file is promoted.

*Config: as TS-107; 2025-Q1's Client Register Geocodes, 3 to 6 percent of the quarter's clients left out.*

| Where to look | |
|---|---|
| Dataset | geo-cp-clients |
| Supplies | `geo_cp_clients__202502011830000800` |
| Period | 2025-Q1 |
| Set "in the warehouse on" to | 2025-02-01 |

### TS-109 - A geocode for a record the quarter does not hold

**What it demonstrates.** Rows matching no source record reads Fail, each sample the record and year; coverage passes.

**What it would look like if the rule were wrong.** The orphan passed, or coverage falling.

*Config: as TS-102; 2017-Q4's ED Presentations Geocodes, one record's rows in every year naming a presentation not in ED's 2017-Q4 supply - added, so every presentation still has its geocodes.*

| Where to look | |
|---|---|
| Dataset | geo-ed-presentations |
| Supplies | `geo_ed_presentations__201711011830000800` |
| Period | 2017-Q4 |
| Set "in the warehouse on" to | 2017-11-01 |

### TS-110 - An empty geocoding file

**What it demonstrates.** Source records matched reads Fail at 0 percent (REQ-QAC-340 criterion 4); the year checks find nothing to fail.

**What it would look like if the rule were wrong.** Every check passing over nothing.

*Config: as TS-102; 2025-Q4's geo_cp_clients.csv holds no rows while the quarter's Client Register holds its clients.*

| Where to look | |
|---|---|
| Dataset | geo-cp-clients |
| Supplies | `geo_cp_clients__202511011830000800` |
| Period | 2025-Q4 |
| Set "in the warehouse on" to | 2025-11-01 |

### TS-111 - A Client Register coloured by its geocodes' promotion

**What it demonstrates.** The file reads Warn on coverage and is promoted; from that instant the 2024-Q4 Client Register, promoted passing on the round before, reads with the Warn tag naming Linkage Products' 2024-Q4 Client Register Geocodes as the cause (REQ-PIPE-332 criterion 4), and earlier dates still show it passing.

**What it would look like if the rule were wrong.** The Client Register demoted, or tagged before the promotion.

*Config: as TS-107; 2024-Q4's Client Register Geocodes, 0.5 to 1.5 percent of clients left out, in a quarter whose amber setting promotes. (Moved from 2026-Q1 on 2026-11-14, post-build-review #322: it sat straight after TS-110's refused 2025-Q4, so drift read Fail across the gap.)*

| Where to look | |
|---|---|
| Dataset | geo-cp-clients |
| Supplies | `geo_cp_clients__202602011830000800` |
| Period | 2026-Q1 |
| Set "in the warehouse on" to | 2026-02-01 |


<!-- scenario-map-data
{
 "scenarios": [
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
   "id": "TS-9",
   "mode": "INJECT",
   "title": "A genuinely early quarterly supply",
   "section": "Arrival classification",
   "demonstrates": "Assigned **2024-Q2** (due 09:00 1 May), the period open when it arrived (REQ-PIPE-131), classified **early**, and filled by the rule. Re-quoted 2026-10-28 from the bootstrapped build (REQ-GEN-235 criterion 4; post-build-review #284): Emergency Department's supply received 10:00 22 April 2024 is filed to slot 2024-Q2, arrival status early, filled at 04:06 2 May, filed automatically. Until then this said \"assigned August\" and \"the 1 May anchor\" - the dates of the original config above, never of the planted case. Note nothing measures how early it is in order to assign it - earliness is a reported consequence of the assignment.",
   "breaksAs": "`cycle_start()` only looks backwards, so it resolves to the 1 February anchor and reports the supply ~12 weeks LATE for 2024-Q1, a quarter that was filled months ago.",
   "config": null,
   "requirements": [
    "REQ-PIPE-131",
    "REQ-GEN-235",
    "REQ-GEN-195"
   ],
   "coordinates": {
    "dataset": "ed-presentations",
    "supplies": [
     "ed_presentations__202404221000000800"
    ],
    "period": "2024-Q2",
    "inPlaceOn": "2024-05-01",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-12",
   "mode": "INJECT",
   "title": "Five tables load, one is an invalid CSV",
   "section": "Delivery and multi-table",
   "demonstrates": "- The five are staged, QA'd, passing, and auto-promoted. Their August slots are **filled**, and their own checks are unaffected - they are not dragged down. - `cp_clients` is a **Fail** (a supply that cannot be loaded is a failing QA finding), rejected, and its August slot stays **unfilled**. - Every check declaring `depends_on: [cp_clients]` - including \"Client reference\", which is DEFINED on `cp_notifications` - **cannot run**, and reads **Fail with a qualifying chip naming `cp_clients` as the blocker**. - That Fail lands at **collection** level, since cross-table checks are lifted there. `cp_notifications` keeps its own passing status and carries only an informational pointer: fully verified against its own data, unverified against its relationships.",
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
    "period": "2025-Q3",
    "inPlaceOn": "2025-05-02",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-14",
   "mode": "INJECT",
   "title": "A later single-table resupply",
   "section": "Delivery and multi-table",
   "demonstrates": "It arrives as **its own delivery** and triggers QA. Its slot is clients' own August slot - per-table slot sequences mean there is no \"resupply of table X within delivery Y\" concept to implement; it is just clients' August supply, arriving late. The previously blocked cross-table check now runs. If it passes, clients promotes and August's slot fills. The recorded QA history keeps **both** runs - the period's current state is the latest, its history is all of them. Clients arriving also re-evaluates the waiting placements' reading checks and re-gates them (REQ-PIPE-121). *Used to say* `qa_results/` kept both runs - REQ-PIPE-089 moved the history into the database. *In the data since 2026-10-15 (REQ-GEN-044 criterion 1)*, riding TS-12's placement: TS-12's cp_clients is refused in 2025-Q2, and the corrected cp_clients arrives alone 28 days later, 10:00 on 2025-05-29, filed to 2025-Q2's still-empty slot. TS-12's link sits between the two; TS-14's lands on the correction's day.",
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
    "period": "2025-Q3",
    "inPlaceOn": "2025-05-29",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-38",
   "mode": "INJECT",
   "title": "A resupply whose filename no longer matches",
   "section": "Timestamps",
   "demonstrates": "The matched files are attributed and processed; the unmatched ones are reported as unrecognised artefacts at **warning** level. Critically, the supply is **NOT** silently treated as complete - the warning is the only thing standing between this and a promoted, passing, HALF supply. Had the resupplies matched, this would instead be the duplicate-match hold of TS-34, which is louder still.",
   "breaksAs": null,
   "config": null,
   "requirements": [],
   "coordinates": {
    "dataset": "cp-clients",
    "supplies": [
     "cp_clients__202602010900000800"
    ],
    "period": "2026-Q2",
    "inPlaceOn": "2026-02-01",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-42a",
   "mode": "INJECT",
   "title": "A contested pair of one Child Protection table, while it is contested",
   "section": "The option A and period-closing batch, planted (REQ-GEN-136, REQ-GEN-137)",
   "demonstrates": "PLANTED by REQ-GEN-203 (2026-10-18) in a grown quarter (REQ-GEN-207), after REQ-PIPE-202 widened `cp_clients`' pattern so two of its files in one delivery contest the table; `tests/test_cp_pair.py` drives the shape through the real orchestrator. Two lettered siblings share the one placement (REQ-GEN-201): this one's link opens on the pair's arrival day. *Config: quarterly, Feb/May/Aug/Nov, due 09:00 on the 1st, claim window 14 days. 2019-Q4's delivery carries the usual files and two Client Registers - cp_clients.csv at 08:30 and a re-export, cp_clients_v2.csv, at 08:40 whose rows differ (each re-pulled an hour later) - both before due; a clean cp_clients.csv follows alone on 29 November at 10:00, after due and before 2020-Q1's window opens, built passing (REQ-GEN-184) after one passing lead-in quarter (2019-Q3) and before a passing one (2020-Q1).* **Expect** (bootstrap of 2026-10-19): on 1 November 2019 cp-clients reads \"Two files for one table \u2014 this dataset's own supply is not checked until a person resolves it\" (REQ-DASH-264), naming cp_clients.csv (received 8:30am) and cp_clients_v2.csv, and the gate refuses its promotion. The three readers each say so at the top of their page (REQ-DASH-204 criterion 13, as the page words it on 1 November 2019, on the bootstrap of 2026-10-25): Notifications \"No promoted Client Register for 2019-Q4. One of this supply's checks needs it, so it could not run. That is not a fault in this supply's own data.\" (when it runs again is said once, on the verdict line above it: \"Nothing needs deciding on this supply\"); Investigations the same with \"2 of this supply's checks need it, so they could not run\"; Placements the same as Notifications. Checks are counted as the grid's rows, one per check however many tools ran it (UX critic on 7093c20, B2). The Client Register's own banner ends \"Affects Notifications, Investigations and Placements.\". **Breaks as**: one of the two files taken as the quarter's supply, or the three readers' cross-table checks evaluated against either.",
   "breaksAs": "One of the two files taken as the quarter's supply, or the three readers' cross-table checks evaluated against either.",
   "config": "Config: quarterly, Feb/May/Aug/Nov, due 09:00 on the 1st, claim window 14 days. 2019-Q4's delivery carries the usual files and two Client Registers - cp_clients.csv at 08:30 and a re-export, cp_clients_v2.csv, at 08:40 whose rows differ (each re-pulled an hour later) - both before due; a clean cp_clients.csv follows alone on 29 November at 10:00, after due and before 2020-Q1's window opens, built passing (REQ-GEN-184) after one passing lead-in quarter (2019-Q3) and before a passing one (2020-Q1).",
   "requirements": [
    "REQ-GEN-184",
    "REQ-GEN-203",
    "REQ-GEN-207",
    "REQ-PIPE-202",
    "REQ-GEN-201",
    "REQ-DASH-264",
    "REQ-DASH-204"
   ],
   "coordinates": {
    "dataset": "cp-clients",
    "supplies": [
     "cp_clients__201911010830000800",
     "cp_clients__201911291000000800"
    ],
    "period": "2020-Q1",
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
   "demonstrates": "TS-42a's placement; this link opens on the later file's asset day. *Config: as TS-42a.* **Expect** (bootstrap of 2026-10-19): the 29 November cp_clients.csv files to 2019-Q4, late, and supersedes the pair: \"Two files for one table \u2014 superseded by the supply received 10:00am Friday, 29 November 2019\". It is promoted on 5 December, and the three readers are re-evaluated by the knock-on at the same instant. **Breaks as**: the pair still contested after the later file, or the later file filed as a resupply rather than ending the contest.",
   "breaksAs": "The pair still contested after the later file, or the later file filed as a resupply rather than ending the contest.",
   "config": "Config: as TS-42a.",
   "requirements": [],
   "coordinates": {
    "dataset": "cp-clients",
    "supplies": [
     "cp_clients__201911010830000800",
     "cp_clients__201911291000000800"
    ],
    "period": "2020-Q1",
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
   "id": "TS-54",
   "mode": "INJECT",
   "title": "A period substituted onto an earlier promoted supply",
   "section": "The option A and period-closing batch, planted (REQ-GEN-136, REQ-GEN-137)",
   "demonstrates": "In the data since 2026-10-15 (REQ-GEN-044 criterion 1; Keith, 2026-10-14, Q13): demonstrated by TS-76's placement - cp-placements' 2025-Q1 substituted by a scripted person onto 2024-Q4, whose cp-placements supply was promoted passing - with its own link while the substitution stands. CORRECTED 2026-10-16 (post-build-review #207 D1): REQ-GEN-207 moved the ordinary Warn drawn for 2026-Q3 to 2024-Q4 and this entry then said \"promoted warning\", but that Warn dirties only cp_carers and cp_clients, so cp-placements' 2024-Q4 supply is still passing and promoted. Whether it should be a Warn is with Keith. The script's `stands_on` field (REQ-GEN-200) answered the old blocker.",
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
    "period": "2025-Q2",
    "inPlaceOn": "2025-02-17",
    "subject": "substitution-drill-down"
   }
  },
  {
   "id": "TS-56",
   "mode": "INJECT",
   "title": "A supply whose columns arrive in another order",
   "section": "The option A and period-closing batch, planted (REQ-GEN-136, REQ-GEN-137)",
   "demonstrates": "It loads as usual, because columns are matched by name; its column-order file check WARNS, shown in the dataset's file section, and the dataset's status is unchanged by it (REQ-QAC-096 criteria 12 and 18, REQ-DASH-097 criterion 7, REQ-GEN-044 criterion 16).",
   "breaksAs": "Refused, or the dataset turned to Warn or Fail by a warning.",
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
    "period": "2026-Q4",
    "inPlaceOn": "2026-08-01",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-57a",
   "mode": "INJECT",
   "title": "A correction that only re-judges, before it is confirmed",
   "section": "Calendar corrections",
   "demonstrates": "The quarter reads late. Nothing on the page names the correction on this date: the replay confirms it only at the end of the history, and the page never shows a past correction as awaiting (Keith, 2026-10-19). Before confirmation, `mothman supply corrections --reference REQ-GEN-205` previews one verdict change (late -> on time) and no moves (REQ-PIPE-168 criteria 3-6).",
   "breaksAs": "Applied on merge with nobody confirming because there were no moves.",
   "config": "Config: 2015-Q1's date is corrected from 1 to 2 February 2015; its one supply arrives at 12:00 on 2 February - late against the old date, on time against the corrected one.",
   "requirements": [
    "REQ-GEN-205",
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
    "inPlaceOn": "2026-09-25",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-58a",
   "mode": "INJECT",
   "title": "A correction that moves a supply, before it is confirmed",
   "section": "Calendar corrections",
   "demonstrates": "The supply reads filed to 2013-Q3, as a resupply. Nothing on the page names the correction on this date: the replay confirms it only at the end of the history, and the page never shows a past correction as awaiting (Keith, 2026-10-19). Before confirmation, `mothman supply corrections --reference REQ-GEN-205` previews the move 2013-Q3 -> 2013-Q4 with its re-judged verdict.",
   "breaksAs": "Moved on merge, or proposed with the verdict computed against 2013-Q3.",
   "config": "Config: 2013-Q4's date is corrected from 1 November to 20 October 2013. Its supply arrives on 10 October, before the old window opened, so it is filed as a resupply of 2013-Q3; the corrected window covers it.",
   "requirements": [
    "REQ-GEN-205"
   ],
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
    "inPlaceOn": "2026-09-25",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-59a",
   "mode": "INJECT",
   "title": "A supply the asset manager will keep, before the correction is confirmed",
   "section": "Calendar corrections",
   "demonstrates": "The supply reads filed to 2014-Q2, as a resupply. Nothing on the page names the correction on this date: the replay confirms it only at the end of the history, and the page never shows a past correction as awaiting (Keith, 2026-10-19). Before confirmation, `mothman supply corrections --reference REQ-GEN-205` previews the move like TS-58a's.",
   "breaksAs": "Kept or moved before anyone confirmed.",
   "config": "Config: as TS-58 for 2014-Q3, corrected from 1 August to 20 July 2014; its supply arrives on 10 July, filed as a resupply of 2014-Q2, which the corrected agreement would move. A scripted confirmation keeps it (contract/scripted_decisions.yaml).",
   "requirements": [
    "REQ-GEN-205"
   ],
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
   "demonstrates": "The supply stays filed where it is, with a KEPT decision-log entry naming it, its period, the change reference, the actor and the reason, and its verdict judged against the period it stays in (REQ-PIPE-170 criteria 5, 6, 22). 2014-Q3, which the kept supply leaves empty, reads Fail \"No supply\" for good - the scenario's own consequence, left at Fail (Keith, 2026-10-19).",
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
    "inPlaceOn": "2026-09-25",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-60a",
   "mode": "INJECT",
   "title": "A correction that leaves a supply with no period, before it is confirmed",
   "section": "Calendar corrections",
   "demonstrates": "The supply reads filed to 2013-Q1. Nothing on the page names the correction on this date: the replay confirms it only at the end of the history, and the page never shows a past correction as awaiting (Keith, 2026-10-19). Before confirmation, `mothman supply corrections --reference REQ-GEN-205` previews it as \"would be held\".",
   "breaksAs": "Held, or dropped, before confirmation.",
   "config": "Config: Emergency Department's first quarter, 2013-Q1, has its date corrected from 1 to 11 February 2013. Its supply arrived on 22 January, inside the old window, before the corrected one opens and with no quarter before it.",
   "requirements": [
    "REQ-GEN-205"
   ],
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
   "demonstrates": "Held (REQ-PIPE-064), the hold's reason naming the correction: \"Held when correction REQ-GEN-205 was confirmed: the corrected calendar offers it no period\". 2013-Q1 reads Fail \"No supply\" for good - the scenario's own consequence, left at Fail (Keith, 2026-10-19).",
   "breaksAs": "Left filed in a period the corrected agreement does not give it, or dropped.",
   "config": "Config: as TS-60a.",
   "requirements": [
    "REQ-PIPE-064",
    "REQ-GEN-205"
   ],
   "coordinates": {
    "dataset": "ed-presentations",
    "supplies": [
     "ed_presentations__201301221000000800"
    ],
    "period": "2013-Q1",
    "inPlaceOn": "2026-09-25",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-61a",
   "mode": "INJECT",
   "title": "A move that will be blocked, before the correction is confirmed",
   "section": "Calendar corrections",
   "demonstrates": "The supply reads filed to 2015-Q3. Nothing on the page names the correction on this date: the replay confirms it only at the end of the history, and the page never shows a past correction as awaiting (Keith, 2026-10-19). Before confirmation, `mothman supply corrections --reference REQ-GEN-205` previews the move, naming the period that stands on it.",
   "breaksAs": "Moved out from under the inheriting period.",
   "config": "Config: 2015-Q3's date is corrected from 1 to 11 August 2015. Its supply arrived on 22 July, which the corrected agreement files to 2015-Q2 - a move blocked because 2015-Q4, the participation gap (REQ-GEN-251), stands on it.",
   "requirements": [
    "REQ-GEN-251",
    "REQ-GEN-205"
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
    "inPlaceOn": "2026-09-25",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-63a",
   "mode": "INJECT",
   "title": "A dataset turned off for a while: the turn-off",
   "section": "Calendar corrections",
   "demonstrates": "PLANTED by REQ-GEN-218 (2026-10-18) in Child Protection's grown history. *Config: Child Protection, quarterly Feb/May/Aug/Nov, due 09:00 on the 1st, 14-day claim window. cp-carers is turned off after 31 December 2021 by correction REQ-GEN-218 dated 15 December 2021, and owed again from 2022-Q3. 2021-Q4's delivery leaves cp_carers out; cp_carers follows on 5 January 2022, after the turn-off but while 2021-Q4's slot is open.* **Expect** (bootstrap of 2026-10-19): from the correction's date the page reads \"Turning off after Friday, 31 December 2021\" (REQ-DASH-180 criterion 27). The 5 January cp_carers files to 2021-Q4, late, and is promoted; 2021-Q4 stays owed until its slot closes (REQ-PIPE-179, REQ-DASH-180). The correction itself shows on the page only once confirmed, at the end of the history - an earlier in-place-on date shows the turn-off as configured, with no correction awaiting (REQ-GEN-218 criterion 5, as amended 2026-10-19). **Breaks as**: the 5 January supply held instead of filed late, or 2021-Q4 going quiet before its slot closes.",
   "breaksAs": "The 5 January supply held instead of filed late, or 2021-Q4 going quiet before its slot closes.",
   "config": "Config: Child Protection, quarterly Feb/May/Aug/Nov, due 09:00 on the 1st, 14-day claim window. cp-carers is turned off after 31 December 2021 by correction REQ-GEN-218 dated 15 December 2021, and owed again from 2022-Q3. 2021-Q4's delivery leaves cp_carers out; cp_carers follows on 5 January 2022, after the turn-off but while 2021-Q4's slot is open.",
   "requirements": [
    "REQ-GEN-218",
    "REQ-DASH-180",
    "REQ-PIPE-179"
   ],
   "coordinates": {
    "dataset": "cp-carers",
    "supplies": [
     "cp_carers__202201051000000800",
     "cp_carers__202203151000000800"
    ],
    "period": "2022-Q1",
    "inPlaceOn": "2021-12-20",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-63b",
   "mode": "INJECT",
   "title": "A dataset turned off for a while: the gap",
   "section": "Calendar corrections",
   "demonstrates": "TS-63a's placement; this link opens on 2021-Q4's delivery and runs to the end of the history. *Config: as TS-63a, with a further cp_carers arriving on 15 March 2022, in the gap. The ordinary deliveries inside the gap still carry the dataset's file, as a supplier still sending files would (REQ-GEN-218 criterion 5).* **Expect** (bootstrap of 2026-10-19): the 15 March supply, and each ordinary gap delivery's cp_carers (1 February and 1 May 2022), finds no open owed slot and is held as turned off. 2022-Q1 and 2022-Q2 read owed-nothing and inherit the 5 January supply: \"Turned off since Saturday, 1 January 2022 \u00b7 Inherited from 2021-Q4\", with \"2 received while turned off, earliest Tuesday, 1 February 2022 \u00b7 2 still held\" on 20 March 2022 and 3 by the end of the history. From 2022-Q3 it reads as any dataset between deliveries. **Breaks as**: the gap read as missed supplies, or a gap arrival filed into a gap period.",
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
    "period": "2022-Q1",
    "inPlaceOn": "2022-03-20",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-65",
   "mode": "INJECT",
   "title": "Early, at the edge of the window",
   "section": "Arrival classification",
   "demonstrates": "Assigned **2025-Q3** and classified **early by 13 days**, exactly as TS-9 - the window is a boundary, and a supply inside it by a day is as early-and-fine as one inside it by a week (REQ-PIPE-131).",
   "breaksAs": "Treated as a resupply of 2025-Q2, as if the window counted from somewhere else.",
   "config": "Config: as TS-9 - Emergency Department, one file, quarterly, due 09:00 on the 1st, claim window 14 days. 2025-Q3 (1 August) arrives 19 July at 10:00, thirteen days early, a day after its window opened at 09:00 on 18 July.",
   "requirements": [
    "REQ-PIPE-131"
   ],
   "coordinates": {
    "dataset": "ed-presentations",
    "supplies": [
     "ed_presentations__202507191000000800"
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
   "config": "Config: as TS-9 - Emergency Department, one file. 2025-Q4 (1 November) arrives 30 October at 10:00.",
   "requirements": [],
   "coordinates": {
    "dataset": "ed-presentations",
    "supplies": [
     "ed_presentations__202510301000000800"
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
   "config": "Config: as TS-9 - Emergency Department, one file. 2023-Q4 (1 November) is due 09:00 that day and its window opens 09:00 on 18 October; the supply arrives 12 October at 10:00, twenty days early and six days before the window. 2023-Q3, before it, is an ordinary quarter whose own supply has arrived.",
   "requirements": [
    "REQ-PIPE-062",
    "REQ-PIPE-131",
    "REQ-GEN-135"
   ],
   "coordinates": {
    "dataset": "ed-presentations",
    "supplies": [
     "ed_presentations__202310121000000800"
    ],
    "period": "2023-Q4",
    "inPlaceOn": "2023-11-01",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-75a",
   "mode": "INJECT",
   "title": "A supply rejected after it waited - while it waited",
   "section": "Calendar corrections",
   "demonstrates": "Cp-clients, 2024-Q1: the whole delivery on time at 09:00 on 1 February with cp_clients alone built failing by its own preset; the other five clean. *Config: quarterly, due 09:00 on the 1st; a person rejects it at 09:00 on 22 February; a corrected cp_clients alone arrives at 10:00 on 29 February.* **Expect** (REQ-DASH-197), on 8 February, in the as-at panel under the results' verdict line: the heading \"On Thursday, 8 February 2024 the warehouse did not hold the latest file\", the column \"Latest arrival by Thursday, 8 February 2024 \u2014 not promoted\" naming cp-clients@202402010900000800, and the reason \"this supply was staged and nobody had decided about it yet\". **What the other tables show**: the Fail clients turned notifications', investigations' and placements' own cross-table checks failing, so all three wait for a person on 8 and 25 February; carers waited until 11 February and then promoted passing; case workers promoted passing on 7 February. When the corrected cp_clients arrives the re-evaluation promotes clients, notifications, investigations and placements passing (11 March). **Breaks as**: no panel; or the reason \"superseded\" (post-build-review #164's reading, which this quarter is placed to avoid).",
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
    "period": "2024-Q2",
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
    "period": "2024-Q2",
    "inPlaceOn": "2024-02-25",
    "subject": "as-at-panel"
   }
  },
  {
   "id": "TS-76",
   "mode": "INJECT",
   "title": "A substitution later removed",
   "section": "Calendar corrections",
   "demonstrates": "Cp-placements, 2025-Q1: the delivery leaves cp_placements out; a person substitutes the quarter onto 2024-Q4 at 09:00 on 3 February, and at 09:00 on 20 April - once the next quarter's window has opened - removes the substitution and marks the quarter not supplied, in that order, at one instant. *Config: quarterly, as TS-75a.* **Expect** (REQ-DASH-198), on 17 February: the pill \"Substituted from 2024-Q4\" beside the dataset's title, and in its drill-down, below the results' heading, \"Since removed, as from Sunday, 20 April 2025\". The quarter closes \"not supplied (accepted)\". **What cp-clients and cp-carers read for 2025-Q1** (H1): clients promoted WARNING on arrival and stays at Warn before, during and after the substitution - the Warn is the ordinary one drawn for this quarter, which the delivery keeps (REQ-GEN-199's PROVISIONAL choice); carers waited until 9 February, then promoted PASSING and stays at Pass. Neither is a Fail after the substitution ends: the cross-table checks reading cp_placements are filed under cp-placements, so in a quarter with no placements supply nothing runs them for clients or carers (the architect's H1 expected a Fail; post-build-review #174). **Breaks as**: no pill on 17 February; or \"Since replaced\".",
   "breaksAs": "No pill on 17 February; or \"Since replaced\".",
   "config": null,
   "requirements": [
    "REQ-DASH-198",
    "REQ-GEN-199"
   ],
   "coordinates": {
    "dataset": "cp-placements",
    "supplies": [],
    "period": "2025-Q2",
    "inPlaceOn": "2025-02-17",
    "subject": "substitution-drill-down"
   }
  },
  {
   "id": "TS-77a",
   "mode": "INJECT",
   "title": "A substitution later replaced - while it stood",
   "section": "Calendar corrections",
   "demonstrates": "Cp-placements, 2023-Q2: the delivery leaves cp_placements out; a person substitutes onto 2023-Q1 at 09:00 on 3 May; cp_placements alone arrives at 10:00 on 8 June and the person promotes it at 10:00 on 9 June, which removes the substitution - one act, taking effect at one instant: 10:48pm Wednesday, 14 June 2023, the new supply's lagged refusal (post-build-review #284 (B); re-quoted from the bootstrap of 2026-10-30). *Config: quarterly, as TS-75a.* **Expect** (REQ-DASH-198), on 17 May: the pill \"Substituted from 2023-Q1\", and in its drill-down \"Since replaced, as from Wednesday, 14 June 2023\". **What cp-clients and cp-carers read for 2023-Q2**: both waited on 2 May; clients promoted WARNING (its quarter's drawn Warn, kept) on 7 May and carers PASSING on 3 May, and both stay so while the substitution stands, on 8 June and after the promotion. **Breaks as**: no pill; or \"Since removed\".",
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
    "period": "2023-Q3",
    "inPlaceOn": "2023-05-17",
    "subject": "substitution-drill-down"
   }
  },
  {
   "id": "TS-77b",
   "mode": "INJECT",
   "title": "Known wrong today (post-build-review #164): A substitution later replaced - the day the late file waited",
   "section": "Calendar corrections",
   "demonstrates": "Today the as-at panel (\"On Thursday, 8 June 2023 the warehouse did not hold the latest file\") gives the late supply the reason \"this one had been superseded - a newer version had arrived for the same period, a person had set it aside, or a later supply had been promoted into the period - so it was no longer what the period held\" - against a period whose holder is a SUBSTITUTED supply, a variant of #164 - while the pill's drill-down reads \"Since replaced, as from Wednesday, 14 June 2023\" and \"2023-Q2 holds 2023-Q1's supply; the results below are a newer supply awaiting a decision.\" Once #164 is decided the panel's reason line should say the supply was waiting for a decision. **Breaks as**: a different reason line in the panel means #164 was decided, not a regression; any other change on that date - the drill-down's sentences included - is a regression.",
   "breaksAs": "A different reason line in the panel means #164 was decided, not a regression; any other change on that date - the drill-down's sentences included - is a regression.",
   "config": null,
   "requirements": [],
   "coordinates": {
    "dataset": "cp-placements",
    "supplies": [
     "cp_placements__202306081000000800"
    ],
    "period": "2023-Q3",
    "inPlaceOn": "2023-06-08",
    "subject": "as-at-panel"
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
    "period": "2026-Q3",
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
    "period": "2023-Q3",
    "inPlaceOn": "2023-06-16",
    "subject": "standing-in-pill"
   }
  },
  {
   "id": "TS-80",
   "mode": "INJECT",
   "title": "A contested pair of one Child Protection table, settled by a person",
   "section": "The option A and period-closing batch, planted (REQ-GEN-136, REQ-GEN-137)",
   "demonstrates": "PLANTED by REQ-GEN-203 (2026-10-18) in a grown quarter (REQ-GEN-207): a stray test file (TS-71's shape) beside the real Client Register, so a settlement can be seen clearing the cross-table readers the contest held, which only Child Protection has. Its link opens on the pair's arrival day. *Config: quarterly, Feb/May/Aug/Nov, due 09:00 on the 1st, claim window 14 days. 2020-Q4's delivery carries the usual files and two Client Registers - a stray test file, cp_clients_TEST.csv, every client named TEST, at 08:20 on the due day and the real cp_clients.csv at 08:30, both before 09:00 - after one passing lead-in quarter (2020-Q3) and before a passing one (2021-Q1), the real extract built passing. A scripted person settles the pair at 11:00 the next day (contract/scripted_decisions.yaml, \"TS-80 settle\"): file one by receipt, the test file, rejected; file two, the real extract, the quarter's supply.* **Expect** (re-quoted from the bootstrap of 2026-10-30, post-build-review #284 (B)): the settlement is one act over both files, so it takes effect at one instant, the later of its own and file one's lagged refusal - 7:35am Sunday, 8 November 2020, not the scripted 11:00 on 2 November. On 1 to 7 November 2020 cp-clients reads \"Two files for one table\"; from 8 November, \"Settled \u00b7 Two files for one table \u2014 settled by Robin Hale, 7:35am Sunday, 8 November 2020\", cp_clients_TEST.csv rejected and cp_clients.csv the quarter's supply. The re-check it owed runs at 7:35am and the gate promotes it; the knock-on re-evaluates the three readers and promotes them at the same instant (post-build-review #251). On 1 November 2020 each reader says so at the top of its page (REQ-DASH-204 criterion 13, as the page words it on the bootstrap of 2026-10-25): Notifications \"No promoted Client Register for 2020-Q4. One of this supply's checks needs it, so it could not run. That is not a fault in this supply's own data.\" (when it runs again is said once, on the verdict line above it: \"Nothing needs deciding on this supply\"); Investigations the same with \"2 of this supply's checks need it, so they could not run\"; Placements the same as Notifications. Checks are counted as the grid's rows, one per check however many tools ran it (UX critic on 7093c20, B2). From 8 November, once re-evaluated, none of the three shows the line. On the page (REQ-DASH-264): on 1 November cp-clients' own checks read \"No data\" and its cross-table rows at Fail, each named \"<reader> \u2192 Client Register\", with the banner saying the cross-table checks did run; from 8 November the readers' Client reference reads Pass (\"Re-checked 7:35am Sunday, 8 November 2020, when the Client Register was re-checked\"), the re-check's result shown though it was recorded under cp-clients' run. **Breaks as**: the test rows checked as the quarter's supply, the readers left contested after the settlement, or the file named by sorted name rather than by receipt position.",
   "breaksAs": "The test rows checked as the quarter's supply, the readers left contested after the settlement, or the file named by sorted name rather than by receipt position.",
   "config": "Config: quarterly, Feb/May/Aug/Nov, due 09:00 on the 1st, claim window 14 days. 2020-Q4's delivery carries the usual files and two Client Registers - a stray test file, cp_clients_TEST.csv, every client named TEST, at 08:20 on the due day and the real cp_clients.csv at 08:30, both before 09:00 - after one passing lead-in quarter (2020-Q3) and before a passing one (2021-Q1), the real extract built passing. A scripted person settles the pair at 11:00 the next day (contract/scripted_decisions.yaml, \"TS-80 settle\"): file one by receipt, the test file, rejected; file two, the real extract, the quarter's supply.",
   "requirements": [
    "REQ-GEN-203",
    "REQ-GEN-207",
    "REQ-DASH-204",
    "REQ-DASH-264"
   ],
   "coordinates": {
    "dataset": "cp-clients",
    "supplies": [
     "cp_clients__202011010820000800"
    ],
    "period": "2021-Q1",
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
  },
  {
   "id": "TS-81",
   "mode": "INJECT",
   "title": "S1 pass - a clean Client Register promoted beside the warehouse's Notifications, its package-mate held back",
   "section": "The option A and period-closing batch, planted (REQ-GEN-136, REQ-GEN-137)",
   "demonstrates": "Notifications v2 is held back (refused on its own data); Clients v2's Notifications -> Client Register check is re-run against Notifications v1 in the warehouse, passes, and Clients v2 replaces Clients v1 under the 'when passing' setting (REQ-PIPE-267 criterion 6, REQ-PIPE-123).",
   "breaksAs": "Clients v2 held back with its package-mate, or promoted on a verdict that read the held-back Notifications v2.",
   "config": "Config: quarterly, Feb/May/Aug/Nov, due 09:00 on the 1st; Child Protection's replacement setting is 'when passing' for 2017-Q2 and 2017-Q3 (contract/data-asset.yaml, Keith 2026-10-25). 2017-Q2's five tables arrive on time, clean, and are promoted; on 15 May 2017 at 10:00 a zip of a clean cp_clients and a cp_notifications failing on its own data arrives. A scripted person rejects that Notifications three weeks later (contract/ scripted_decisions.yaml, \"TS-81 reject\"), so it waits on no later page.",
   "requirements": [
    "REQ-PIPE-267",
    "REQ-PIPE-123",
    "REQ-GEN-273"
   ],
   "coordinates": {
    "dataset": "cp-clients",
    "supplies": [
     "cp_clients__201705010900000800",
     "cp_clients__201705151000000800"
    ],
    "period": "2017-Q3",
    "inPlaceOn": "2017-05-15",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-82",
   "mode": "INJECT",
   "title": "S1 fail - a Client Register re-checked against the warehouse's Notifications and held back",
   "section": "The option A and period-closing batch, planted (REQ-GEN-136, REQ-GEN-137)",
   "demonstrates": "Notifications v2 is held back on its own data; Clients v2's re-check against Notifications v1 fails, so Clients v2 is held back ('promotion-withheld' naming Notifications v2, re-checked against Notifications v1) and Clients v1 stays. Its root is Clients v2 itself - its own check failed (Keith, 2026-10-25, answer 3a).",
   "breaksAs": "Clients v2 promoted, or refused without the re-check.",
   "config": "Config: as TS-81, in 2017-Q3, the zip's cp_clients missing the five clients only the quarter's Notifications point at (no Investigation or Placement does). A scripted person rejects both files of the zip three weeks later.",
   "requirements": [
    "REQ-GEN-273"
   ],
   "coordinates": {
    "dataset": "cp-clients",
    "supplies": [
     "cp_clients__201708010900000800",
     "cp_clients__201708151000000800"
    ],
    "period": "2017-Q4",
    "inPlaceOn": "2017-08-15",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-83",
   "mode": "INJECT",
   "title": "S2 strict as re-cast - a failing Client Register holds its whole first-time package back",
   "section": "The option A and period-closing batch, planted (REQ-GEN-136, REQ-GEN-137)",
   "demonstrates": "Clients is held back on its own data; Notifications, Investigations and Placements are re-checked against no Client Register in the warehouse and held back with it ('promotion-withheld', could not be checked); Carer Register and Case Workers are promoted. The resend is gated as one package and all four are promoted, superseding the first four.",
   "breaksAs": "Notifications judged alone and promoted, or held back without the re-check.",
   "config": "Config: quarterly, Feb/May/Aug/Nov, due 09:00 on the 1st. 2016-Q3's six tables arrive together on time, the quarter's first supply, cp_clients failing on its own data and the other five clean. On 29 August a corrected cp_clients and its three readers are resent together.",
   "requirements": [
    "REQ-GEN-273"
   ],
   "coordinates": {
    "dataset": "cp-clients",
    "supplies": [
     "cp_clients__201608010900000800",
     "cp_clients__201608291000000800"
    ],
    "period": "2016-Q4",
    "inPlaceOn": "2016-08-29",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-84",
   "mode": "INJECT",
   "title": "The S10 chain re-ordered - three staggered files promoted together at the last one's arrival",
   "section": "The option A and period-closing batch, planted (REQ-GEN-136, REQ-GEN-137)",
   "demonstrates": "Carer Register is promoted at 08:30; Notifications, Placements and Investigations each wait failing for want of a Client Register ('promotion-withheld'); at 09:20 the Client Register's arrival gates them with it and all four are promoted together (REQ-PIPE-267 criterion 2).",
   "breaksAs": "Any of the three left waiting after the Client Register, or Clients promoted alone.",
   "config": "Config: quarterly, Feb/May/Aug/Nov, due 09:00 on the 1st, 8 hours' grace. 2015-Q4's one delivery, the quarter's first, each file its own receipt: Carer Register 08:30, Notifications 08:40, Placements 08:50, Investigations 09:00, Client Register 09:20, all clean.",
   "requirements": [
    "REQ-PIPE-267",
    "REQ-GEN-273"
   ],
   "coordinates": {
    "dataset": "cp-clients",
    "supplies": [
     "cp_clients__201511010920000800"
    ],
    "period": "2016-Q1",
    "inPlaceOn": "2015-11-01",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-85",
   "mode": "INJECT",
   "title": "S14 - a failing Placements held back alone in a first-time package",
   "section": "The option A and period-closing batch, planted (REQ-GEN-136, REQ-GEN-137)",
   "demonstrates": "Placements is held back on its own data; Client Register, Notifications, Investigations, Carer Register and Case Workers are promoted - no check they count reads a Placements the period will hold. The corrected Placements is promoted, superseding the first.",
   "breaksAs": "A reader of Placements held back with it.",
   "config": "Config: quarterly, Feb/May/Aug/Nov, due 09:00 on the 1st. 2016-Q1's six tables arrive together on time, the quarter's first supply, cp_placements failing on its own data and the other five clean. On 29 February a corrected cp_placements arrives alone.",
   "requirements": [
    "REQ-GEN-273"
   ],
   "coordinates": {
    "dataset": "cp-placements",
    "supplies": [
     "cp_placements__201602010900000800",
     "cp_placements__201602291000000800"
    ],
    "period": "2016-Q2",
    "inPlaceOn": "2016-02-29",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-86",
   "mode": "INJECT",
   "title": "A linkage release with an empty key",
   "section": "The linkage history, planted (REQ-GEN-335)",
   "demonstrates": "Linkage key recorded reads Fail on one row, and the release is held back (REQ-PIPE-332 criterion 3).",
   "breaksAs": "The empty key passed, or the whole release refused unloaded.",
   "config": "Config: quarterly, due 18:00 with 8 hours' grace; 2016-Q3's release, one row's linkage_key empty.",
   "requirements": [
    "REQ-PIPE-332",
    "REQ-GEN-335"
   ],
   "coordinates": {
    "dataset": "linkage-keys",
    "supplies": [
     "linkage_keys__201608011730000800"
    ],
    "period": "2016-Q3",
    "inPlaceOn": "2016-08-01",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-87",
   "mode": "INJECT",
   "title": "A dataset code nobody declared - a linked dataset as good as missing",
   "section": "The linkage history, planted (REQ-GEN-335)",
   "demonstrates": "Known dataset code reads Fail; ED Presentations' coverage reads 0 percent, Fail; its referential check finds no EDDC_PRESENTATION row to fail.",
   "breaksAs": "The renamed code matched by similarity, or coverage passing.",
   "config": "Config: as TS-86; 2017-Q1's release codes every ED Presentations row EDDC_PRESENTATION_V2.",
   "requirements": [
    "REQ-GEN-335"
   ],
   "coordinates": {
    "dataset": "linkage-keys",
    "supplies": [
     "linkage_keys__201702011730000800"
    ],
    "period": "2017-Q1",
    "inPlaceOn": "2017-02-01",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-88",
   "mode": "INJECT",
   "title": "A surplus identifier",
   "section": "The linkage history, planted (REQ-GEN-335)",
   "demonstrates": "No surplus identifiers reads Fail on that row; every other check passes.",
   "breaksAs": "The surplus id ignored, or read as a missing one.",
   "config": "Config: as TS-86; 2018-Q1's release, one DOC_CLIENTS row carrying an id_2, the contract's id_2 column being blank in every ordinary release (PROVISIONAL).",
   "requirements": [
    "REQ-GEN-335"
   ],
   "coordinates": {
    "dataset": "linkage-keys",
    "supplies": [
     "linkage_keys__201802011730000800"
    ],
    "period": "2018-Q1",
    "inPlaceOn": "2018-02-01",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-89",
   "mode": "INJECT",
   "title": "One record linked twice",
   "section": "The linkage history, planted (REQ-GEN-335)",
   "demonstrates": "Each record linked once reads Fail; coverage is unchanged.",
   "breaksAs": "The duplicate counted as two linked presentations.",
   "config": "Config: as TS-86; 2018-Q2's release, one EDDC_PRESENTATION record under two keys.",
   "requirements": [
    "REQ-GEN-335"
   ],
   "coordinates": {
    "dataset": "linkage-keys",
    "supplies": [
     "linkage_keys__201805011730000800"
    ],
    "period": "2018-Q2",
    "inPlaceOn": "2018-05-01",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-90",
   "mode": "INJECT",
   "title": "A link to a record the quarter does not hold",
   "section": "The linkage history, planted (REQ-GEN-335)",
   "demonstrates": "ED Presentations links match a presentation reads Fail, its failing row the code and identifier; the result counts toward ED Presentations as well (REQ-PIPE-332 criterion 1).",
   "breaksAs": "The dangling row passed, or the Fail kept off ED's page.",
   "config": "Config: as TS-86; 2018-Q3's release, one EDDC_PRESENTATION row naming a presentation not in ED's 2018-Q3 supply.",
   "requirements": [
    "REQ-PIPE-332",
    "REQ-GEN-335"
   ],
   "coordinates": {
    "dataset": "linkage-keys",
    "supplies": [
     "linkage_keys__201808011730000800"
    ],
    "period": "2018-Q3",
    "inPlaceOn": "2018-08-01",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-91",
   "mode": "INJECT",
   "title": "Coverage in the warn band",
   "section": "The linkage history, planted (REQ-GEN-335)",
   "demonstrates": "Client Register coverage reads Warn, worded below its band; the release promotes as a Warn does (REQ-DASH-337).",
   "breaksAs": "Worded \"above 90 percent\", or read Pass.",
   "config": "Config: as TS-86; 2018-Q4's release links 85.5 to 89.5 percent of the Client Register's rows.",
   "requirements": [
    "REQ-DASH-337",
    "REQ-GEN-335"
   ],
   "coordinates": {
    "dataset": "linkage-keys",
    "supplies": [
     "linkage_keys__201811011730000800"
    ],
    "period": "2018-Q4",
    "inPlaceOn": "2018-11-01",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-92",
   "mode": "INJECT",
   "title": "Coverage in the fail band",
   "section": "The linkage history, planted (REQ-GEN-335)",
   "demonstrates": "ED Presentations coverage reads Fail, a percentage only, no failing rows; the release is held back.",
   "breaksAs": "Failing rows recorded for coverage, or Warn.",
   "config": "Config: as TS-86; 2019-Q2's release links 78 to 84 percent of ED Presentations' rows.",
   "requirements": [
    "REQ-GEN-335"
   ],
   "coordinates": {
    "dataset": "linkage-keys",
    "supplies": [
     "linkage_keys__201905011730000800"
    ],
    "period": "2019-Q2",
    "inPlaceOn": "2019-05-01",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-93a",
   "mode": "INJECT",
   "title": "A Client Register held failing and rejected - its side of TS-93b",
   "section": "The linkage history, planted (REQ-GEN-335)",
   "demonstrates": "Cp_clients held back on its own data, then rejected; its readers held for want of a Client Register until a person promotes them, so none waits on a later page.",
   "breaksAs": "The failing Client Register promoted.",
   "config": "Config: quarterly, Feb/May/Aug/Nov, due 09:00 on the 1st; 2019-Q1's six tables arrive on the 1 November 2018 round, cp_clients alone built failing; a scripted person rejects it three weeks later (\"TS-93 reject\") and nothing replaces it; an hour later the same person promotes its three readers (\"TS-93 promote notifications\", \"... investigations\", \"... placements\").",
   "requirements": [
    "REQ-GEN-335"
   ],
   "coordinates": {
    "dataset": "cp-clients",
    "supplies": [
     "cp_clients__201811010900000800"
    ],
    "period": "2019-Q1",
    "inPlaceOn": "2018-11-01",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-93b",
   "mode": "INJECT",
   "title": "A linkage release whose Client Register is not in the warehouse",
   "section": "The linkage history, planted (REQ-GEN-335)",
   "demonstrates": "The release's two cp-clients checks read Fail, could not run, naming the rejected Client Register; ED Presentations' checks are evaluated.",
   "breaksAs": "The cp-clients checks evaluated against another quarter's Client Register, or left out of scope as if marked not supplied.",
   "config": "Config: as TS-86; 2019-Q1's release, built from the Client Register as received, checked with TS-93a's supply rejected.",
   "requirements": [
    "REQ-GEN-335"
   ],
   "coordinates": {
    "dataset": "linkage-keys",
    "supplies": [
     "linkage_keys__201902011730000800"
    ],
    "period": "2019-Q1",
    "inPlaceOn": "2019-02-01",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-93c",
   "mode": "INJECT",
   "title": "A Client Register geocode whose source was rejected - named, not planted",
   "section": "The geocoding history, planted (REQ-GEN-298)",
   "demonstrates": "Its two cp-clients checks read Fail, could not run, and the file is held back for the rest of the history, as TS-93b's linkage release is.",
   "breaksAs": "The checks evaluated against another quarter's Client Register.",
   "config": "Config: quarterly, due 19:00; 2019-Q1's ordinary Client Register Geocodes, received while TS-93a's Client Register is held and then rejected, nothing replacing it.",
   "requirements": [
    "REQ-GEN-298"
   ],
   "coordinates": {
    "dataset": "geo-cp-clients",
    "supplies": [
     "geo_cp_clients__201902011843000800"
    ],
    "period": "2019-Q1",
    "inPlaceOn": "2019-02-01",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-94",
   "mode": "INJECT",
   "title": "A failing linkage release promoted by a person",
   "section": "The linkage history, planted (REQ-GEN-335)",
   "demonstrates": "Held back failing; from the promotion, the Client Register promoted passing on the 1 February 2022 round reads 'Promoted, failing' (REQ-PIPE-332 criterion 4), and earlier dates still show it passing.",
   "breaksAs": "The Client Register demoted, or coloured before the promotion.",
   "config": "Config: as TS-86; 2022-Q2's release, one DOC_CLIENTS row naming a client the quarter does not hold; a scripted person promotes it two days later (\"TS-94 promote\", REQ-PIPE-332 criterion 8).",
   "requirements": [
    "REQ-PIPE-332",
    "REQ-GEN-335"
   ],
   "coordinates": {
    "dataset": "linkage-keys",
    "supplies": [
     "linkage_keys__202205011730000800"
    ],
    "period": "2022-Q2",
    "inPlaceOn": "2022-05-01",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-95",
   "mode": "INJECT",
   "title": "A linked dataset marked not supplied - named, not planted",
   "section": "The linkage history, planted (REQ-GEN-335)",
   "demonstrates": "The release's cp-clients checks are left out of scope with reason code not_supplied_by_decision, while ED Presentations' are evaluated (REQ-PIPE-332 criterion 7).",
   "breaksAs": "Cp-clients' checks read Fail, could not run.",
   "config": "Config: quarterly; Child Protection has no supply for 2015-Q2 and its existing scripted entry marks cp-clients not supplied; the 2015-Q2 release is an ordinary one.",
   "requirements": [
    "REQ-PIPE-332",
    "REQ-GEN-335",
    "REQ-GEN-205"
   ],
   "coordinates": {
    "dataset": "linkage-keys",
    "supplies": [
     "linkage_keys__201505011725000800"
    ],
    "period": "2015-Q2",
    "inPlaceOn": "2015-05-01",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-96",
   "mode": "INJECT",
   "title": "A quarter with no linkage release",
   "section": "The linkage history, planted (REQ-GEN-335)",
   "demonstrates": "The slot closes unfilled and reads not supplied (accepted) (REQ-PIPE-132, REQ-DASH-133).",
   "breaksAs": "A Fail \"No supply\" gap left needing action.",
   "config": "Config: quarterly, due 18:00; no release comes for 2020-Q3, and a scripted person marks it not supplied the day after its slot closed, 19 October 2020 (\"TS-96 not supplied\").",
   "requirements": [
    "REQ-PIPE-132",
    "REQ-DASH-133",
    "REQ-GEN-335"
   ],
   "coordinates": {
    "dataset": "linkage-keys",
    "supplies": [],
    "period": "2020-Q3",
    "inPlaceOn": "2020-10-19",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-97",
   "mode": "INJECT",
   "title": "Large key groups in the warn band",
   "section": "The linkage history, planted (REQ-GEN-335)",
   "demonstrates": "Large key groups reads Warn, with the count of keys, the count of large groups and their histogram across several bins, and no key value.",
   "breaksAs": "A key value recorded, or the histogram drawn over every key.",
   "config": "Config: as TS-86; 2021-Q3's release, records re-keyed into groups of 51 to 230 records until just over 2 percent of distinct keys are large groups.",
   "requirements": [
    "REQ-GEN-335"
   ],
   "coordinates": {
    "dataset": "linkage-keys",
    "supplies": [
     "linkage_keys__202108011730000800"
    ],
    "period": "2021-Q3",
    "inPlaceOn": "2021-08-01",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-98",
   "mode": "INJECT",
   "title": "Large key groups in the fail band",
   "section": "The linkage history, planted (REQ-GEN-335)",
   "demonstrates": "Large key groups reads Fail and the release is held back.",
   "breaksAs": "Warn, or every key counted as a group.",
   "config": "Config: as TS-97; 2022-Q3's release, groups of 51 to 70 records until just over 4 percent of distinct keys are large groups.",
   "requirements": [
    "REQ-GEN-335"
   ],
   "coordinates": {
    "dataset": "linkage-keys",
    "supplies": [
     "linkage_keys__202208011730000800"
    ],
    "period": "2022-Q3",
    "inPlaceOn": "2022-08-01",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-99",
   "mode": "INJECT",
   "title": "A blank expected identifier",
   "section": "The linkage history, planted (REQ-GEN-335)",
   "demonstrates": "Expected identifiers present reads Fail; the Client Register's referential check also fails on that row, which matches no client.",
   "breaksAs": "The blank read as a value.",
   "config": "Config: as TS-86; 2022-Q4's release, one DOC_CLIENTS row's id_1 blank.",
   "requirements": [
    "REQ-GEN-335"
   ],
   "coordinates": {
    "dataset": "linkage-keys",
    "supplies": [
     "linkage_keys__202211011730000800"
    ],
    "period": "2022-Q4",
    "inPlaceOn": "2022-11-01",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-100a",
   "mode": "INJECT",
   "title": "A Client Register held failing, then promoted by a person - its side of TS-100b",
   "section": "The linkage history, planted (REQ-GEN-335)",
   "demonstrates": "Held back on its own data until the person promotes it; its readers re-checked and promoted with it.",
   "breaksAs": "Promoted by the rule.",
   "config": "Config: quarterly, Feb/May/Aug/Nov, due 09:00 on the 1st; 2019-Q3's six tables arrive on the 1 May 2019 round, cp_clients alone built failing and held; a scripted person promotes it at 10:00 on 2 August 2019 (\"TS-100 promote\"), the day after the quarter's linkage release.",
   "requirements": [
    "REQ-GEN-335"
   ],
   "coordinates": {
    "dataset": "cp-clients",
    "supplies": [
     "cp_clients__201905010900000800"
    ],
    "period": "2019-Q3",
    "inPlaceOn": "2019-05-01",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-100b",
   "mode": "INJECT",
   "title": "A linkage release cleared by a person's promotion",
   "section": "The linkage history, planted (REQ-GEN-335)",
   "demonstrates": "Its cp-clients checks read Fail, could not run, until 10:00 on 2 August 2019, when the promotion's knock-on re-checks them and they pass (REQ-PIPE-331 criterion 5).",
   "breaksAs": "Still failing after the promotion, or evaluated against the held supply before it.",
   "config": "Config: as TS-86; 2019-Q3's release, ordinary rows, received while TS-100a's Client Register is held.",
   "requirements": [
    "REQ-PIPE-331",
    "REQ-GEN-335"
   ],
   "coordinates": {
    "dataset": "linkage-keys",
    "supplies": [
     "linkage_keys__201908011730000800"
    ],
    "period": "2019-Q3",
    "inPlaceOn": "2019-08-01",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-100c",
   "mode": "INJECT",
   "title": "A Client Register geocode cleared by a person's promotion - named, not planted",
   "section": "The geocoding history, planted (REQ-GEN-298)",
   "demonstrates": "Its cp-clients checks read Fail, could not run, until 10:00 on 2 August 2019, when the promotion's knock-on re-checks them and they pass.",
   "breaksAs": "Still failing after the promotion.",
   "config": "Config: as TS-93c; 2019-Q3's ordinary Client Register Geocodes, received while TS-100a's Client Register is held.",
   "requirements": [
    "REQ-GEN-298"
   ],
   "coordinates": {
    "dataset": "geo-cp-clients",
    "supplies": [
     "geo_cp_clients__201908011817000800"
    ],
    "period": "2019-Q3",
    "inPlaceOn": "2019-08-01",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-101",
   "mode": "INJECT",
   "title": "Emergency Department's same-round Fail, clearing",
   "section": "The linkage history, planted (REQ-GEN-335)",
   "demonstrates": "The release's ED Presentations checks read Fail, could not run, and clear through the knock-on once the resupply is promoted (REQ-GEN-334 criteria 9 and 12); ED's own page is not coloured by them.",
   "breaksAs": "ED's page coloured by a not-evaluated result, or the release re-timed to avoid the Fail.",
   "config": "Config: as TS-86; 2021-Q4's release, received while ED Presentations' Fail supply of the morning is held, its resupply arriving days later; no ED arrival moved, no release re-timed.",
   "requirements": [
    "REQ-GEN-334",
    "REQ-GEN-335"
   ],
   "coordinates": {
    "dataset": "linkage-keys",
    "supplies": [
     "linkage_keys__202111011730000800"
    ],
    "period": "2021-Q4",
    "inPlaceOn": "2021-11-01",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-101b",
   "mode": "INJECT",
   "title": "An ED geocode while ED's same-round Fail is held - named, not planted",
   "section": "The geocoding history, planted (REQ-GEN-298)",
   "demonstrates": "Its ed-presentations checks read Fail, could not run, and clear through the knock-on once the resupply is promoted.",
   "breaksAs": "ED's page coloured by a not-evaluated result.",
   "config": "Config: as TS-93c; 2021-Q4's ordinary ED Presentations Geocodes, built from ED's Fail supply of the morning, its share not geocoded in the warn band, received while that supply is held.",
   "requirements": [
    "REQ-GEN-298"
   ],
   "coordinates": {
    "dataset": "geo-ed-presentations",
    "supplies": [
     "geo_ed_presentations__202111011850000800"
    ],
    "period": "2021-Q4",
    "inPlaceOn": "2021-11-01",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-102",
   "mode": "INJECT",
   "title": "A missing census year",
   "section": "The geocoding history, planted (REQ-GEN-298)",
   "demonstrates": "Missing census years reads Fail, each sample the record and the missing year; every other check passes.",
   "breaksAs": "The record read as left out, or the year check passing.",
   "config": "Config: quarterly, due 19:00 with 8 hours' grace; 2023-Q2's Client Register Geocodes, one census year's rows dropped for one to three records, the record's other years present - two or more years in force since 2017-Q3.",
   "requirements": [
    "REQ-GEN-298"
   ],
   "coordinates": {
    "dataset": "geo-cp-clients",
    "supplies": [
     "geo_cp_clients__202305011830000800"
    ],
    "period": "2023-Q2",
    "inPlaceOn": "2023-05-01",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-103",
   "mode": "INJECT",
   "title": "A duplicated census year",
   "section": "The geocoding history, planted (REQ-GEN-298)",
   "demonstrates": "Duplicated census years reads Fail; every other check passes.",
   "breaksAs": "The repeat read as a second record.",
   "config": "Config: as TS-102; 2022-Q1's ED Presentations Geocodes, one census year's row repeated, identical in every column, for one to three presentations.",
   "requirements": [
    "REQ-GEN-298"
   ],
   "coordinates": {
    "dataset": "geo-ed-presentations",
    "supplies": [
     "geo_ed_presentations__202202011830000800"
    ],
    "period": "2022-Q1",
    "inPlaceOn": "2022-02-01",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-104",
   "mode": "INJECT",
   "title": "An unexpected census year",
   "section": "The geocoding history, planted (REQ-GEN-298)",
   "demonstrates": "Unexpected census years reads Fail on the 2026 rows; every other check passes.",
   "breaksAs": "2026 read as in the set, or caught by a type check.",
   "config": "Config: as TS-102; 2016-Q2's Client Register Geocodes, a row for census year 2026 for one to three records - 2026 joins the set only from 2027-Q3.",
   "requirements": [
    "REQ-GEN-298"
   ],
   "coordinates": {
    "dataset": "geo-cp-clients",
    "supplies": [
     "geo_cp_clients__201605011830000800"
    ],
    "period": "2016-Q2",
    "inPlaceOn": "2016-05-01",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-105",
   "mode": "INJECT",
   "title": "The share not geocoded in the warn band",
   "section": "The geocoding history, planted (REQ-GEN-298)",
   "demonstrates": "Share not geocoded reads Warn; the drift check over placed rows passes; the file promotes as a Warn does.",
   "breaksAs": "Fail, or the drift check warning too.",
   "config": "Config: as TS-102; 2023-Q1's ED Presentations Geocodes, whole presentations turned not geocoded in every year, codes empty, until the share lies between 6 and 9 percent.",
   "requirements": [
    "REQ-GEN-298"
   ],
   "coordinates": {
    "dataset": "geo-ed-presentations",
    "supplies": [
     "geo_ed_presentations__202302011830000800"
    ],
    "period": "2023-Q1",
    "inPlaceOn": "2023-02-01",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-106",
   "mode": "INJECT",
   "title": "The share not geocoded in the fail band",
   "section": "The geocoding history, planted (REQ-GEN-298)",
   "demonstrates": "Share not geocoded reads Fail and the file is held back.",
   "breaksAs": "Warn, or the format checks failing the empty codes.",
   "config": "Config: as TS-105; 2024-Q1's Client Register Geocodes, until the share lies between 12 and 18 percent.",
   "requirements": [
    "REQ-GEN-298"
   ],
   "coordinates": {
    "dataset": "geo-cp-clients",
    "supplies": [
     "geo_cp_clients__202402011830000800"
    ],
    "period": "2024-Q1",
    "inPlaceOn": "2024-02-01",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-107",
   "mode": "INJECT",
   "title": "Coverage in the warn band",
   "section": "The geocoding history, planted (REQ-GEN-298)",
   "demonstrates": "Source records matched reads Warn; the missing-year check, which counts only records present, passes.",
   "breaksAs": "Missing census years failing, or coverage Pass.",
   "config": "Config: as TS-102; 2021-Q2's ED Presentations Geocodes, 0.5 to 1.5 percent of the quarter's presentations left out in every year. (Moved from 2014-Q1 on 2026-11-14, post-build-review #322: the quarter before it had no accepted ED geocodes, so drift read Fail across the gap beside the planted Warn.)",
   "requirements": [
    "REQ-GEN-298",
    "REQ-QAC-340"
   ],
   "coordinates": {
    "dataset": "geo-ed-presentations",
    "supplies": [
     "geo_ed_presentations__201402011830000800"
    ],
    "period": "2014-Q1",
    "inPlaceOn": "2014-02-01",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-108",
   "mode": "INJECT",
   "title": "Coverage in the fail band",
   "section": "The geocoding history, planted (REQ-GEN-298)",
   "demonstrates": "Source records matched reads Fail, a percentage only; the file is held back, so its Fail does not colour the Client Register.",
   "breaksAs": "Failing rows recorded for coverage, or the Client Register coloured before the file is promoted.",
   "config": "Config: as TS-107; 2025-Q1's Client Register Geocodes, 3 to 6 percent of the quarter's clients left out.",
   "requirements": [
    "REQ-GEN-298"
   ],
   "coordinates": {
    "dataset": "geo-cp-clients",
    "supplies": [
     "geo_cp_clients__202502011830000800"
    ],
    "period": "2025-Q1",
    "inPlaceOn": "2025-02-01",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-109",
   "mode": "INJECT",
   "title": "A geocode for a record the quarter does not hold",
   "section": "The geocoding history, planted (REQ-GEN-298)",
   "demonstrates": "Rows matching no source record reads Fail, each sample the record and year; coverage passes.",
   "breaksAs": "The orphan passed, or coverage falling.",
   "config": "Config: as TS-102; 2017-Q4's ED Presentations Geocodes, one record's rows in every year naming a presentation not in ED's 2017-Q4 supply - added, so every presentation still has its geocodes.",
   "requirements": [
    "REQ-GEN-298"
   ],
   "coordinates": {
    "dataset": "geo-ed-presentations",
    "supplies": [
     "geo_ed_presentations__201711011830000800"
    ],
    "period": "2017-Q4",
    "inPlaceOn": "2017-11-01",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-110",
   "mode": "INJECT",
   "title": "An empty geocoding file",
   "section": "The geocoding history, planted (REQ-GEN-298)",
   "demonstrates": "Source records matched reads Fail at 0 percent (REQ-QAC-340 criterion 4); the year checks find nothing to fail.",
   "breaksAs": "Every check passing over nothing.",
   "config": "Config: as TS-102; 2025-Q4's geo_cp_clients.csv holds no rows while the quarter's Client Register holds its clients.",
   "requirements": [
    "REQ-QAC-340",
    "REQ-GEN-298"
   ],
   "coordinates": {
    "dataset": "geo-cp-clients",
    "supplies": [
     "geo_cp_clients__202511011830000800"
    ],
    "period": "2025-Q4",
    "inPlaceOn": "2025-11-01",
    "subject": "supply-history-row"
   }
  },
  {
   "id": "TS-111",
   "mode": "INJECT",
   "title": "A Client Register coloured by its geocodes' promotion",
   "section": "The geocoding history, planted (REQ-GEN-298)",
   "demonstrates": "The file reads Warn on coverage and is promoted; from that instant the 2024-Q4 Client Register, promoted passing on the round before, reads with the Warn tag naming Linkage Products' 2024-Q4 Client Register Geocodes as the cause (REQ-PIPE-332 criterion 4), and earlier dates still show it passing.",
   "breaksAs": "The Client Register demoted, or tagged before the promotion.",
   "config": "Config: as TS-107; 2024-Q4's Client Register Geocodes, 0.5 to 1.5 percent of clients left out, in a quarter whose amber setting promotes. (Moved from 2026-Q1 on 2026-11-14, post-build-review #322: it sat straight after TS-110's refused 2025-Q4, so drift read Fail across the gap.)",
   "requirements": [
    "REQ-PIPE-332",
    "REQ-GEN-298"
   ],
   "coordinates": {
    "dataset": "geo-cp-clients",
    "supplies": [
     "geo_cp_clients__202602011830000800"
    ],
    "period": "2026-Q1",
    "inPlaceOn": "2026-02-01",
    "subject": "supply-history-row"
   }
  }
 ]
}
-->
