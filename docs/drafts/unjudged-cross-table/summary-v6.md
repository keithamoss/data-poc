# Cross-table checks that could not run, or were judged against the wrong partner (#95): draft v6, for sign-off

Re-folded by delivery-scoper on 2026-10-23 (Perth). It folds in:
- Keith's **V5-Q1 = A** and **V5-Q2 = A** (`summary.md`, end);
- the three v5 reviews, all in `docs/drafts/`: `review-architect-279v3-95v5.md`
  (its #95 section), `review-dashboard-ux-279v3-95v5.md` and
  `review-cli-ux-279v3-95v5.md`.

It stands on **REQ-PIPE-279 v4**, which is being finalised in parallel. Its
answers are fixed: K1-K7, plus N1 = B and N2 = A with a run lock for every
attempt. This is a **proposal**. Nothing is in `requirements.yaml`, and
nothing is signed.

The YAML is `requirements-draft-v6.yaml`. v4 and v5 are left as history.
**Anything this file does not restate still holds as summary-v5.md has it,
and through it as summary-v4.md has it.** In particular:
- the plain-prose sign-off brief;
- the "How #95 stands on REQ-PIPE-279" table, which is updated below for one
  change;
- every amendment not listed here.

**For Keith's final check-in:**
- **No decision of his moved.**
- **One piece of NEW WORDING to approve:** the terminal's form of the
  carry-forward warning (CLI v5 item 11). See "New wording for Keith" below.
- **Two things to know, not to decide:**
  1. V5-Q2's amendment lands on **REQ-PIPE-129 c16**, not REQ-GHUB-082. c16 is
     the signed criterion that owns the lock-timeout refusal; GHUB-082 c22
     names no exit code.
  2. **A defect of mine in v5** is fixed. v5 wrote 204's re-cast test over the
     criterion "render every name in the line as text, never as markup". That
     dropped the criterion and kept the stale test (dashboard v5 B2). v6
     restores the criterion and deletes the stale test.

## The shape, in one paragraph (what v6 adds to v5's)

A gate application holds **one lock per (collection, period)**. It is not
just for rule entries now (V5-Q1): **every person's decision that moves a
table** try-locks it too. While a gate is running, that decision is refused
with exit 75: "A gate is running for <period>. Nothing was changed. Try
again in a moment."

The lock is released after the application's one outer transaction commits,
so its own knock-on can take it.

**Every run inside an application is one point, keyed on the application**,
so a cascade shows only its last round. An application ends SETTLED or
ABANDONED, and nothing is ever reused from an abandoned one.

A failed move, or a contended re-confirmation, owes the gate again from
recorded results, never a re-run of the tools.

Counting is per check everywhere, 269 c4 included.

The dashboard's waiting state has four forms. An awaiting page captions its
grid. History and trend keep every evaluation, while status uses counted
results only.

In the terminal:
- every printed command carries real values and prints outside tables;
- `mothman supply queue` gets the same surfaces;
- every "try later" on `supply decide` exits 75, the lock timeout included
  (V5-Q2).

## How #95 stands on REQ-PIPE-279: what changed in v6

- **#95 now amends 279's point key** (V5-Q1's technical answer, architect v5
  S2). A run inside a gate application has the APPLICATION as its cause, so
  every round of one application is one point. The wording is under
  "Amendments to REQ-PIPE-279" below. It is for 279's v4 pass to fold in, or
  for #95 to apply when it lands.
- **REQ-DASH-264 c1 is amended twice** (V5-Q1's technical answer, architect
  v5 B2 option (a)). 279 ships first with its own wording. 269 amends it
  again, quoting 279's as OLD.
- **279's N1 = B conditions are 279's, not #95's.** They are:
  - one function for the compare default and the `?cmp=` rule (dashboard v5
    S7, an existing defect, to be fixed test-first);
  - every compare or history entry names its cause, including the sparkline
    tooltip (dashboard v5 section 4).

  #95 adds only the third condition: compare within one grid bucket
  (272 c17).
- **279's N2 = A** (a run lock for every attempt) does not change #95. The
  period lock and the attempt lock are separate names, and the period lock is
  always taken first.

## The requirements (changed in v6)

| Id | Changed in v6 |
|---|---|
| REQ-PIPE-266 | **New c16**: every person's table-moving decision try-locks the period (V5-Q1, exit 75). **c17**: the compare-and-swap reuses the consequences-changed refusal (CLI 4). c5: the kept report's wording (CLI 12). The owed kind is renamed `gate` (architect S4). A package is not a point (architect note). Tests. |
| REQ-PIPE-267 | c3: JOINABLE clause 3 made precise (note). c8: a fixed round order, and no reuse from an ABANDONED application (S3). **c11: keyed on the gate application** (S2). c12: SETTLED or ABANDONED, in one module. **c17: one helper; released before the knock-on (S1); a failed move owes a `gate`, never a `recheck`; contention is not a failure (S4)**. Tests. |
| REQ-PIPE-269 | **c4 per check (B1)**, and its test asserts Placements is untouched. c10: 264 c1 amended twice. |
| REQ-PIPE-271 | c7: real values, printed outside tables, in `supply queue`, and **the terminal's own lead-in (NEW wording)**. |
| REQ-DASH-272 | c6: the awaiting page's caption (S1). c7: staged only on a waiting page (S6). c9: "why it is held back" wherever the counted result is the warehouse one (S3). c12: third-bucket sentences (S2). c17: one point per application; compare within a bucket. c18: status from counted results, history and trend from every evaluation (S4). **c21: four waiting forms (B1, architect S5)**. c22: one supply-naming helper (P1). P2-P6 recorded as decisions. Tests. |
| REQ-DASH-275 | c4: the date-compression rule for the joined card line (note). |
| REQ-PIPE-276 | Real values in commands (2). `_show` convention (3). Shared renderer and `supply queue` (7). The gating line is never in `select()`, with the only-a-gating-group case (6). `_say_owed` wording (5). The door offers nothing while checking (8). Order B red links the rows, with the widened trigger (10). **Lock timeout exits 75 (V5-Q2)**, with 75's three causes documented. The joined header. One phrase. Amends REQ-PIPE-129 c16. Tests. |
| REQ-DASH-277 | NFR LENGTH no longer stale (note). Coordinated with period-clarity's button suffix (P4). |
| REQ-PIPE-278 | A test for Order B red's two tickets. |
| REQ-PIPE-280 | **"Nothing newer" is a no-op, exit 0; refusals keep exit 1 with wordings (CLI 1).** It takes the period lock (V5-Q1). Undo line, follow-up, inherit's hint, un-inherit's consequence, `--help` (CLI 9). The name is confirmed. |
| REQ-DASH-204 | **The stale c13 test is deleted and the lost "render as text" criterion restored (B2, my v5 defect).** c2: the superseded form (S5), periods through `fmtPeriodOrDay` (P3). c17: the partner's own window (P5). |
| REQ-PIPE-210 | c3: the command uses real values, printed outside tables. |
| 270, 273, 274 | Source line only. |

## Amendments: new or changed in v6

Every amendment in summary-v4.md and summary-v5.md not listed here stands as
worded there.

**REQ-DASH-264 c1** (signed 2026-10-19), by REQ-PIPE-269. **Amended a second
time, after REQ-PIPE-279.** This replaces v5's combined wording.
- OLD (REQ-PIPE-279's NEW): "... the newest result, by evaluation order
  (REQ-PIPE-279), about a supply of that dataset and recorded on or before the
  in-place-on date, whichever table's run recorded it ..."
- NEW: "THE SYSTEM SHALL show on a dataset page, for each check, the newest
  result, by evaluation order (REQ-PIPE-279), COUNTED toward the supply the
  page is about (REQ-PIPE-269) and recorded on or before the in-place-on date,
  whichever table's run recorded it, so a re-check of one table that re-runs
  another's cross-table checks changes the other table's page from the day it
  was recorded, and a result that read a supply not in place in the warehouse
  never changes an in-place supply's page. AMENDED `<date>` by REQ-PIPE-269
  (Keith, 2026-10-22, V5-Q1's technical answer: 279 first, 269 again)."

**REQ-PIPE-129 c16** (signed 2026-10-04), by REQ-PIPE-276. **New in v6**
(V5-Q2 = A).
- OLD: "THE SYSTEM SHALL give every decision transaction a lock timeout, and
  IF a move waits on a running QA tool past it, THEN THE SYSTEM SHALL refuse
  the decision with a message saying a run is in progress and to retry, and
  SHALL NOT hang."
- NEW: append: "On the flag route (mothman supply decide) that refusal exits
  75 (EXIT_LOCKED), as every 'nothing was changed, try later' refusal on that
  command does. AMENDED `<date>` by REQ-PIPE-276 (Keith, 2026-10-22, V5-Q2 =
  A)."
- REQ-GHUB-082 c22 ("tell the person ... why, on the route they raised it
  on") is unchanged and still met.

**Amendments to REQ-PIPE-279** (an unsigned draft), by REQ-PIPE-267. **New
in v6.** For 279's finalising pass to fold in, conditionally on #95, or for
#95 to apply when it lands.
- **Point key (c8 in its v3 draft).**
  - OLD: "... where an arrival run's cause is its ARRIVAL, the group of
    REQ-PIPE-265 siblings it belongs to (criterion 19; a lone arrival is a
    group of one), and a re-check, readers-only or knock-on run's cause is
    the decision id or load id it records; ..."
  - NEW: "... where an arrival run's cause is its ARRIVAL, ..., a run made
    inside a REQ-PIPE-267 gate application has that GATE APPLICATION as its
    cause (qa.run's gate-application id), and any other re-check, readers-only
    or knock-on run's cause is the decision id or load id it records; ..."
  - The rest is unchanged.
- **Sequencing NFR.** "run_seq is drawn under #95's per-(collection, period)
  lock" now means: drawn while the application holds the period lock. A
  person's decision cannot land in between, because it try-locks the same
  lock (266 c16).

**REQ-PIPE-099 (by 280)** is unchanged from v5. The no-op split needs no
099 wording.

## New wording for Keith (the only item that needs his eye)

**REQ-PIPE-271 c7, the carry-forward warning as the terminal shows it** (CLI
v5 item 11: the terminal's own voice, the same as `_recheck_panel`'s "To take
it out of {where}, demote it:"):

```
A newer cp-case-workers could be carried forward into 2024-Q4. 2024-Q4 carries
forward the supply received 1 Jul 09:00; the one received 3 Oct 09:00 has been
promoted into 2024-Q3 since.
To carry that one forward instead, in one step:
mothman supply decide --operation carry-forward --dataset cp-case-workers --period 2024-Q4 --reason '<why>'
or from the 2024-Q4 door.
```

For a refused inheritance, the lead-in is "To carry it forward, in one step:".
The dashboard keeps "A person can carry that one forward instead, in one
step:".

Other new terminal sentences in v6 are mechanical, in wording Keith has
already approved the shape of:
- the gate-running refusal (his own words in V5-Q1);
- 280's no-op and refusal lines;
- the Order B "promoting that one re-checks this one" line;
- the `supply queue` gate line.

Keith does not sign wording, per his terms, so these are listed rather than
asked.

## Walk-through 1 (v6 + 279 v4): S1, a zip

**The starting point.** 2024-Q3 holds v1 of all six tables in the warehouse,
all green. Clients v1 and Notifications v1 were received at 9:00am on Monday,
1 July 2024. At 9:00am on Monday, 21 October 2024, a zip arrives holding
Clients v2 and Notifications v2. Notifications v2 has 2 blank-value failures
of its own.

**1. Filed.** The two files are one package (266 c1) and are staged into
2024-Q3.

**2. Clients v2 is checked first.** Its own checks pass. The checks that read
Clients are evaluated, each with its reads recorded (279):
- Notifications' Client reference, against the staged Notifications v2: Pass;
- Investigations' and Placements' checks, against v1 in the warehouse: Pass.

A `gate` item is owed. Clients v2's run takes its own attempt lock (279 N2).
- *Warehouse*: all v1.
- *Dashboard*:
  - **Clients' page**: "Checked, waiting for the rest of its delivery
    (received 9:00am Monday, 21 October 2024): 1 of 2 files checked. Nothing
    needs deciding yet."
  - **Notifications' page**: "Being checked with its delivery (received
    9:00am Monday, 21 October 2024): 1 of 2 files checked. Nothing needs
    deciding yet." It shows no pill and no results, even though Clients' run
    has recorded a Pass about it (272 c21, dashboard v5 B1).
- *Terminal*:
  - Both queues show one dim, unpickable line: "Checking a delivery received
    21 Oct 09:00 (1 of 2 files checked)". With nothing else waiting, the queue
    says "Nothing is waiting on a person in Child Protection." with that line
    beneath it.
  - `mothman supply queue`'s owed list shows "gate of the delivery received
    21 Oct 09:00 (1 of 2 files checked)".
  - `mothman cp qa --commit` on the Clients file prints and reports "checked,
    waiting for the rest of its delivery (1 of 2 files checked)" and exits 0.
  - The 2024-Q3 door shows cp-clients and cp-notifications as "checking with
    its delivery (1 of 2 files checked)" and offers no decision.
  - `supply decide` on either is refused: "The delivery received ... is still
    being checked (1 of 2 files checked); decide once it is gated." It exits
    75.

**3. Notifications v2 is checked.** 2 of its own checks fail. Client reference
is carried from Clients v2's run (265), so that pair has one evaluation and
one point. Its other checks are evaluated against v1 in the warehouse.

**4. The gate application.**
- The rule try-locks (Child Protection, 2024-Q3) and records a
  `qa.gate_application` row.
- Notifications v2 is not promoting. Its `promotion-withheld` entry is
  committed now.
- Clients v2's Client reference is re-run against Notifications v1. The run's
  cause is the gate application, and it is that application's one point on
  Clients v2 (267 c11, V5-Q1). Its `caused_by_decision` is Notifications v2's
  hold-back. Nothing it records is counted until the application settles.
- *Dashboard, if built now*: both pages read "Checked, being gated (received
  ...). Nothing needs deciding yet." (architect v5 S5).
- *Terminal, if a person now tries any table-moving decision in 2024-Q3*:
  "A gate is running for 2024-Q3. Nothing was changed. Try again in a moment."
  It exits 75 (266 c16). This holds for promoting Notifications v2, demoting
  Investigations v1, carrying something forward, or any other move. The
  half-and-half race the architect found (B3) cannot happen.

**5a. Green branch.**
- The re-check passes. Clients v2 is promoted in one outer transaction, and
  the owed knock-on row is inserted inside it. The application is marked
  SETTLED, and **the period lock is released**.
- The knock-on takes the lock afresh in the same pass and re-runs **nothing**.
  Clients v2 never reads "recheck-owed" (architect v5 S1).
- *Warehouse*: Clients v2, Notifications v1, the rest v1.
- *Dashboard, Notifications' page*:
  - "Awaiting a decision — ... The supply in place in the warehouse is the one
    received 9:00am Monday, 1 July 2024, and is Green."
  - The grid is captioned "Results for the supply received 9:00am Monday, 21
    October 2024, awaiting a decision" (272 c6, dashboard S1).
  - Client reference reads "Pass ✓ ✓ ✓, Client Register received 21 Oct" under
    "Against what's in the warehouse".
- *Dashboard, Clients' page*: Green. The history row says "Promoted 9:0x by
  the rule, re-checked against the Notifications in place in the warehouse
  (received ...) because the Notifications received with it was held back."
  Its trend has its arrival point and one re-check point (the application).
- *Terminal*: one counted row, cp-notifications, red. The kept report says
  "promoted by the rule - Client reference re-checked against the
  cp-notifications in place ... green, because the cp-notifications received
  with it was held back". `pipeline process` exits 1.
- *Tickets*: one, for Notifications.

**5b. Red branch.**
- The re-check fails, and Clients v2 is held back. The entry reads "Held back:
  Client reference, re-checked against the Notifications in place in the
  warehouse (received 1 Jul) because the Notifications received with it was
  held back. This supply's checks of its own data passed."
- The application is SETTLED, and the lock is released.
- *Warehouse*: all v1.
- *Dashboard, Clients' page*:
  - the 275 notice, `data-held-back`, sits above any 204 notice;
  - the grid is captioned;
  - Client reference shows Staged "Pass, Notifications received 21 Oct" and
    In the warehouse "Fail, Notifications received 1 Jul — why it is held
    back", with a Red pill.
- *Dashboard, Notifications' page*: "Holding back with it: Client Register"
  and "If this file is turned down, the Client Register supply needs its own
  decision."
- *Card*: "[Red] Held back together: Notifications, Client Register (one
  delivery, received 9:00am Monday, 21 October 2024)".
- *Terminal*. The command is printed below the table through `_show`. The
  supply id shown here is illustrative; the terminal prints the real one.
  ```
  1 supply waiting on a decision in Child Protection (1 more held back with it, listed beneath)

  cp-notifications  2024-Q3  received 21 Oct 09:00  red - 2 of its own checks fail
    held back with it (same delivery):
    - cp-clients  nothing needs deciding on this supply - Client reference failed against
      the cp-notifications in place in the warehouse (received 1 Jul).
      Deciding cp-notifications settles it. To override:
  mothman supply decide --operation promote --dataset cp-clients --period 2024-Q3 --supply cp-clients@202410210900000000 --reason '<why>'
  or from the 2024-Q3 door.
  ```
- *Tickets*: one, Notifications', naming Clients v2.

**6. Later.**
- **A person promotes Notifications v2.** No gate holds 2024-Q3, so the
  period lock is free. The consequences say it "re-checks cp-clients' waiting
  supply received 21 Oct 09:00; if it is green, the rule promotes it".
  - If, while the person is confirming, something else changed what they saw,
    they are re-asked once with the new consequences. With `--yes`, the
    command refuses naming the new key and exits 1.
  - The knock-on re-gates Clients v2 on its arrival result against
    Notifications v2, which is now in the warehouse, and promotes it.
- **A person turns Notifications v2 down.**
  - Red branch: nothing re-runs. Clients v2's notice reads "... was turned
    down; this supply now needs its own decision". It becomes its own counted
    row and gets its own ticket.
  - Green branch: Notifications' page returns to v1's verdict.

## Walk-through 2 (v6 + 279 v4): the same files, staggered

The starting point is the same. Each file now arrives on its own, as a
package of one. Notifications v2 also points at clients that are new in
Clients v2.

### Order A: Notifications v2 at 9:00am, Clients v2 at 9:05am

**9:00, Notifications v2's arrival.** It is checked against Clients v1 in the
warehouse:
- Client reference fails, because of the new clients;
- 2 of its own checks fail.

Its gate application has nothing to join, so it is held back. The lock is
released.
- *Dashboard*:
  - Notifications' page is awaiting, with the warehouse Green.
  - The grid is captioned "Results for the supply received 9:00am ...,
    awaiting a decision", so the Fail under "Against what's in the warehouse"
    is not read as the warehouse's own result.
  - Clients' page stays Green: the result read Notifications v2, which is not
    in the warehouse.
- *Terminal*: one counted row.
- *Tickets*: Notifications'.

**9:05, Clients v2's arrival.**
- Its run checks Notifications' Client reference against the staged
  Notifications v2: Pass. That is a second point on Notifications v2, whose
  cause is **Clients v2's ARRIVAL** (279 K3 = C).
- The application joins Notifications v2. Notifications v2 is joinable: its
  current run's period is its filing's slot. It is not promoting.
- Clients v2's Client reference is re-run against Notifications v1 inside the
  application.

**Green branch.** The re-run passes, and Clients v2 promotes alone at 9:05.
The knock-on re-runs nothing. Notifications v2's hold-back is unchanged, and
no new entry is written.
- *Warehouse*: Clients v2 and Notifications v1.
- *Dashboard, Notifications' page*:
  - The 9:00 result read Clients v1, which has since been replaced, so it
    sits in neither cell. Its panel says "Read against the Client Register
    received 9:00am Monday, 1 July 2024, since replaced in the warehouse by
    the one received 9:05am Monday, 21 October 2024" (dashboard S2).
  - The 9:05 result is in the warehouse cell.
  - Its trend shows both points (272 c18, dashboard S4).
- *Flicker*: none.

**Red branch.** Clients v2 is held back by the waiting Notifications.
- *Dashboard*: the joined notice form. The card reads "Held back together:
  Notifications, Client Register (received 9:00am and 9:05am, Monday 21
  October 2024)", with the shared date written once.
- *Terminal*: "1 supply waiting on a decision in Child Protection (1 more held
  back by it, listed beneath)". cp-clients is beneath, with the full override
  command below the table and the dim supplier hint.
- *Tickets*: one, Notifications', naming Clients.

### Order B: Clients v2 at 9:00am, Notifications v2 at 9:05am

**9:00, Clients v2's arrival.** It is checked against Notifications v1.

**Green branch.** Clients v2 promotes at 9:00. At 9:05 Notifications v2 is
checked against Clients v2 in the warehouse and held back on its own reds.
The end state is the same as the zip's green branch.

**Red branch.**
- **9:00**: Clients v2 fails Client reference against Notifications v1, a real
  failure. It is held back and gets its own ticket.
- **9:05**: Notifications v2 is checked against the staged Clients v2: Pass.
  Clients v2 is joined and decided from its recorded results, with nothing
  re-run. Its counted verdict falls back to 9:00's Fail, and it stays held
  back with no new entry. Notifications v2 is held back on its own reds.
- *Dashboard, Clients' page*:
  - Client reference shows Staged "Pass, Notifications received 21 Oct 9:05"
    and In the warehouse "Fail, Notifications received 1 Jul — why it is held
    back", with a Red pill. The suffix now appears although the Fail came from
    its own 9:00 arrival (272 c9, dashboard S3).
  - Its trend keeps the 9:00 point.
- *Terminal*: two counted rows. Clients v2's row, and its door, add:

  ```
  Client reference passes against the cp-notifications waiting for a decision
  (received 21 Oct 09:05); promoting that one re-checks this one.
  ```

  Promoting Notifications v2 lists, among its consequences, that it re-checks
  Clients v2 (276 c9's widened trigger). Turning down a good Clients v2 is no
  longer the obvious mistake (CLI v5 item 10).
- *Tickets*: two, each its own root. The architect agrees this is correct
  (278 test).

### The flicker Keith accepted (Order B, with a clean Notifications v2)

1. **9:00**: Clients v2 fails against Notifications v1. It is red, held back
   and ticketed.
2. **9:05**: the clean Notifications v2 passes against the staged Clients v2.
   - The application joins Clients v2. Each check is judged by its newest
     qualifying verdict, and both read the other, which is promoting, so both
     promote together at 9:05 in one transaction.
   - The lock is released, and the knock-on re-runs nothing.
   - Clients' history reads "Promoted 9:05am with the Notifications supply
     received 9:05am, by the rule".
   - The ticket closes when the slot is reconciled.

That is five minutes of red that clears by itself: the accepted flicker. A zip
avoids it.

In the reverse order (a clean Notifications v2 at 9:00, then Clients v2), the
same flicker falls on Notifications, and its 9:00 result ends in neither
cell, with the "since replaced" sentence in its panel.

## Carry-over check

### summary.md, Keith's V5 answers

| Decision | Where in v6 |
|---|---|
| V5-Q1 = A: every person's table-moving decision (promote, reject, demote, un-inherit, de-substitute, re-file, carry-forward) try-locks the per-(collection, period) lock; refusal exit 75 with Keith's wording; B rejected | 266 c16, d, test (each operation); 267 c17 (one helper); 280 c2; 276 c20 (75's documented causes); walk-through 1 step 4 |
| ...slot locks order person against person only | 266 c16 |
| ...REQ-DASH-264 c1 amended by 279, then by 269 quoting 279's as OLD | 269 c10, d; amendment above |
| ...runs inside a gate application keyed on the application as their point, amending 279 c8 | 267 c11, d; 272 c17; 279 amendment above |
| V5-Q2 = A: `RUN_IN_PROGRESS` exits 75 too; an amendment with old/new wording; one test; B rejected | 276 c20, c22, d, test `test_a_lock_timeout_refusal_exits_75`; REQ-PIPE-129 c16 amendment (the criterion that owns the refusal; see the note at the top) |

### Architect v5 (#95 section)

| Item | Where |
|---|---|
| B1, 269 c4 per check | 269 c4, d; TestCountedPerCheck asserts no Placements/Carers |
| B2, two c1 wordings | V5-Q1 technical answer (a); 269 c10; amendment |
| B3, the CAS race | V5-Q1; 266 c16-c17 |
| S1, an application blocks its own knock-on | 267 c17 (released before the knock-on), d, test |
| S2, cascade points; two causes | 267 c11 (keyed on the application; `caused_by_decision` = lowest id), d; 272 c17; 279 amendment; test |
| S3, ABANDONED; no reuse | 267 c8, c12, c17, d |
| S4, a gate-only retry; contention is not a failure | 267 c17, d; 266 c3 (`gate` kind), d |
| S5, visible mid-application | 272 c21 ("Checked, being gated" for an unsettled application) |
| Note: package vs point | 266 d "A PACKAGE IS NOT A POINT" |
| Note: "arrival" not "delivery" in walk-through 2 | Walk-through 2 |
| Note: a fixed round order | 267 c8, d |
| Note: JOINABLE clause 3 made precise; held is never joinable | 267 c3, d |
| Notes under the lock (no transaction while tools run; hold-backs commit before citing runs; AccessExclusive on moved tables only; the knock-on row inside the outer transaction) | 267 c11, c17 |
| Builder notes (one lock helper; the lifecycle in one module) | 267 c17, c12 |
| Readings 1-3: agree (2 conditional on S3 and S4) | 266 d; 267 d (updated); 278 d and test |

### Dashboard UX v5

| Item | Where |
|---|---|
| B1, c21's four cases; Notifications' page at step 2 | 272 c21, d, tests; walk-through 1 step 2 |
| B2, delete 204 c13 | Done, and the lost criterion restored (204 c12, d) |
| S1, caption an awaiting page | 272 c6, d, test |
| S2, third-bucket sentences, compare list included | 272 c12, d, test |
| S3, the suffix wherever the counted result is the warehouse one | 272 c9, d, test |
| S4, history/trend vs counted | 272 c18, d, test |
| S5, 204's superseded form | 204 c2, c13, d |
| S6, staged bucket only on a waiting page | 272 c7, d |
| S7, the `?cmp=` / default defect | 279's N1 condition (272 d; not repeated); the road-testing sighting is noted |
| Section 4: 279 consequences (tooltip names its cause; K7 overtaken) | Routed to 279 (272 d); period-clarity's Q3 row wording goes through 272's helper (272 d) |
| P1, one supply-naming helper | 272 c22 |
| P2, no third rewording of 081 c1; the period line above the notices | 272 d |
| P3, `<period>` through `fmtPeriodOrDay` | 204 c2; 272 d |
| P4, the shared control | 277 d |
| P5, the partner's own window | 204 c17, d |
| P6, no period bucketing of sparklines | 272 d |
| Notes: 277 NFR stale; 275 c4 date rule | 277 NFR; 275 c4 |

### CLI UX v5 (#95)

| Item | Where |
|---|---|
| 1, a no-op exits 0; refusals exit 1 with wordings | 280 c6, d, tests |
| 2, real values in commands | 276 c4, c6; 210 c3; 271 c7; test |
| 3, outside tables via `_show` | 276 c21; 271 c7; 210 c3 |
| 4, the CAS through the consequences-changed machinery | 266 c17, d, test |
| 5, the `gate` kind in `_say_owed` | 276 c13, test |
| 6, never in `select()`; only-a-gating-group | 276 c12, test |
| 7, `supply queue` surfaces | 276 c6, c12; 271 c7; test |
| 8, the door offers nothing while checking | 276 c11, test |
| 9, 280's terminal surface (undo, follow-up, inherit hint, un-inherit consequence, `--help`) | 280 c8, d, tests |
| 10, link the Order B rows; widen the trigger | 276 c9, c16, d, test |
| 11, the terminal's lead-in | 271 c7 (NEW wording, above) |
| 12, the kept report | 266 c5 |
| Notes: one phrase; the joined header; exit 3 not widened | 276 c6, d |
| Q1 = V5-Q2 | As above |

The 279 items in the reviews (architect S1-S6, CLI Ctrl-C, N1 and N2) belong
to 279's v4 pass. Nothing of #95 depends on them beyond what is stated above.

**Nothing is left only in prose.**

## Non-functional angles (added in v6)

- Concurrency: one lock per period serves rules and people alike. No waits,
  and no nested self-deadlock.
- Reliability: ABANDONED applications; gate-only retries; contention reported
  as contention, never as a failure.
- Determinism: a fixed round order.
- Scriptability: 75 means "nothing was changed, try later" in all three of its
  cases on `supply decide`, and every printed command is copyable with real
  values.

Nothing new was put to Keith. Security, privacy, compliance and cost are as
in v5.

## Readings to confirm at the walk-through (no new forks)

The ones from v5 still stand:
- N1's single "A";
- Q5's "no notification";
- the staging view made precise;
- case 3a.

The architect has agreed v5's readings 1-3. C, D and E are still Keith's
(summary-v5.md), and every reviewer agrees with each recommendation.

## Draft entry for plans/running-thoughts.md #95 (for a human to apply)

> Append to #95: "**v6, 2026-10-23**: Keith's V5-Q1 = A and V5-Q2 = A and the three v5 reviews are folded into `docs/drafts/unjudged-cross-table/summary-v6.md` and `requirements-draft-v6.yaml` (unsigned). The changes:
> - a person's table-moving decision try-locks the period's gate lock (exit 75);
> - a gate application is one point, settled or abandoned, and releases its lock before its knock-on;
> - counting per check in 269 c4 as well;
> - four dashboard waiting forms, plus the reviewers' S1-S7;
> - real-valued, copyable commands and `supply queue` parity;
> - the lock-timeout refusal exits 75 (REQ-PIPE-129 c16).
>
> One piece of new terminal wording is for Keith's walk-through. Next: Keith's S1 and staggered walk-throughs."

## Validation

- `uv run mothman dashboard validate-requirements --draft
  docs/drafts/unjudged-cross-table/requirements-draft-v6.yaml`, run alone,
  reports 78 errors. All 78 are `dependencies entry ... does not match any
  real requirement id in this file`. There are no others.
- I merged `requirements.yaml` with:
  - the close-out draft's REQ-GEN-206 and REQ-PIPE-211;
  - REQ-PIPE-279's current draft on disk;
  - all fifteen v6 requirements.

  The result is at
  `/tmp/claude-0/-home-user-data-poc/5735d9c2-23bf-590b-afe1-e67b136c7e21/scratchpad/v5/merged95v6.yaml`.
  The validator reports **"requirements validation OK - 266 requirements, zero
  errors."**
- I read the file back. All fifteen requirements parse. Every item is a
  string, every requirement carries `decisions:`, and none carries
  `signed_off`.

## Signed, 2026-10-23 (Perth) - C, D and E applied to the YAML

Keith walked v6 and REQ-PIPE-279 v4 through end to end and signed off
(`summary.md`, "Keith's sign-off walk-through, 2026-10-23"). delivery-scoper
applied his last answers to `requirements-draft-v6.yaml` the same day:

- **C = A.** A new REQ-PIPE-270 c9: a check whose table is not part of the
  agreement for the period and was never supplied is out of the run's scope,
  recorded in `left_out` with its reason, and is neither red nor a result. A
  new test, c13. REQ-PIPE-271's open question is closed into a decision.
- **D = A.** REQ-DOCS-274 c1 names a new `docs/supplier-guidance.md`, linked
  from `docs/delivery-format.md` and `docs/aws-event-driven-mvp-design.md`. Its
  open question is closed into a decision.
- **E = B**, against the recommendation.
  - In REQ-PIPE-210, c1 gains an exception. The new c9 says that a supply red
    only because its partner is overdue, with nothing to sit beneath, is an
    ordinary counted, pickable row that is never told "nothing needs
    deciding".
  - The new c10 has the dashboard's cards count the same way, through the
    same function.
  - c8 counts it, and c11's tests cover both.
  - Both open questions are closed.
  - **A reading to confirm with Keith if wrong**: REQ-DASH-204 c16 now also
    stops saying "nothing needs deciding" for that case, so that the page
    agrees with the queue.
  - Ticketing (REQ-PIPE-278) is unchanged: the overdue slot's own ticket still
    names the supplies it holds back.
- **CLI item 11's wording** is approved as drafted. REQ-PIPE-271 c7 is
  unchanged.
- Every requirement is now `status: not_started` with `signed_off: {by: Keith,
  date: '2026-10-23'}`. REQ-DASH-204 keeps its build-time check (open question
  1), which is not a question for Keith.

Not in the signed batch: the close-out drafts' REQ-GEN-206 and REQ-PIPE-211
(their edits are in summary-v4.md). REQ-DASH-204 depends on REQ-PIPE-211.
