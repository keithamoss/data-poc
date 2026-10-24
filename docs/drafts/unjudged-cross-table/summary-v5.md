# Cross-table checks that could not run, or were judged against the wrong partner (#95): draft v5, for sign-off

Re-folded by delivery-scoper on 2026-10-23 (Perth). It uses Keith's answers on
the v4 reviews (`summary.md`, "Keith's answers on the v4 reviews, 2026-10-22
(Perth)": V4-Q1 = A, V4-Q2 = A, V4-Q3 = A) and the three v4 reviews
(`review-architect-v4.md`, `review-dashboard-ux-v4.md`, `review-cli-ux-v4.md`).
It now **stands on REQ-PIPE-279** (`docs/drafts/deterministic-matching/`).

This is a **proposal**. Nothing in it is in `requirements.yaml`, and nothing is
signed. The requirements are in `requirements-draft-v5.yaml`, next to this
file. v4 (`summary-v4.md`, `requirements-draft-v4.yaml`) is left as it is, as
history. **Where this file does not restate something, summary-v4.md still
holds**, in particular the amendment wordings marked "unchanged" below and the
plain-prose sign-off brief per requirement.

**How sign-off works** (Keith, `summary.md`, "How Keith will sign v4 off"):
- the architect and both UX reviewers see v5;
- then Keith gets one last check-in: the S1 walk-through and the staggered
  walk-through, both below;
- sign-off is recorded only after that, and only if no decision moved.

What this summary marks plainly for that check-in:
- **One of Keith's decisions moved, and he moved it himself.** V4-Q1 = A
  supersedes his 2026-10-21 "Clients is held too" for the case where the only
  failing table is one that reads Clients. Everything that depended on the old
  reading is re-cast (S2 strict, S10, five tests, the walk-through).
- **No new question for Keith.** There are five readings to confirm at the
  walk-through, two presentation calls to mention, and three questions carried
  over from v4 (C, D, E) that are still his. The reviewers agree with all three
  recommendations.

## The shape, in one paragraph

The design is red only, and strict. A cross-table check that cannot read a
partner is red, but only for the table that asks the question (Q13 = B).

Files that arrive together (one zip, one receipt instant) are gated together
once every one of them has been checked.

Every gate is a **gate application**. It takes the newly checked supplies,
plus every **joinable** supply waiting in the same period that is connected to
them through recorded cross-table verdicts, transitively. A supply is
promoted only on verdicts about what the warehouse will hold, **counted per
check**. When one supply in the set is held back, the others' cross-table
checks are re-run against what is in the warehouse, until nothing changes. A
check that could count toward nothing is not re-run, so **a clean table
promotes alone when the only failing table is one that reads it** (V4-Q1).
Supplies that depend on each other promote together or not at all, in one
transaction, under one lock per period.

A promoted supply counts a verdict only when every supply that check read is
still the one in the warehouse.

A quarter opens, and makes its inheritances, at its first filing, and it
inherits once. When a newer supply could be carried forward, a warning names
**one step** that does it (REQ-PIPE-280, V4-Q2).

On the dashboard, each cross-table check is one row in a grid. Its columns are
"Against what's staged" and "Against what's in the warehouse", and a column
with nothing in it is not shown. In the terminal, "held back" means every
gate hold-back. A decision refused because the delivery is still being
checked exits 75 (V4-Q3).

## How #95 stands on REQ-PIPE-279

Keith, 2026-10-22: "I don't want ties and guessing, I want deterministic
matching". REQ-PIPE-279 is scoped for that and is being finalised in
parallel. Its answers are fixed: K1 = A, K2 = A, K3 = C, K4 = A, K5 = A,
K6 = C, K7 = A, and kept as one requirement. Its criterion numbers are
provisional, so v5 cites it by id and by what it records.

**What #95 takes from 279, rather than defining it again:**

| Fact or rule | 279 provides | #95 uses it in |
|---|---|---|
| Which supply of EVERY table a check read, and its state (read, held, absent, no-supply), per result | `qa.check_read` | 267 c1 (gate counting per check, architect v4 B2); 269 c1-c2 (warehouse view per check); 272 c7 (which grid cell) |
| Whether each table was read from staging or from the period | its own recorded field | 267 c11 and 272 c7. **v4's `from_warehouse` column on `qa.run` is dropped** |
| One selection function for "which results are about this supply" | `supply_status.results_about` | 269 c7 extends it with the view argument and a shown/counted split. #95 keeps no rule of its own |
| One order for "newest" | `run_seq` (K1 = A) | 266 c4; 267 c1, c8; 269 c3, c7; 272 c7 (by its emitted rank) |
| Every evaluation its own point; one point per supply and cause | K3 = C, K4 = A | 272 c17. A package re-check is a re-check point keyed on its `promotion-withheld` cause, never merged into the delivery. In the staggered case, Clients' run re-checking Notifications' Client reference is a second point on Notifications |
| Siblings read from `qa.filing` / `qa.delivery_file`, never run ids | its REQ-PIPE-265 c1 amendment | 266 c1 (what a package is) |
| A result that read no supply of a table shows only on the declaring table's page | K2 = A | Consistent with Q13 = B; 269 c6; the held-table page (open question B) uses 279's "held" state |

**Build order consequence.** 279 is built before 269 and 267. Both schema
bumps are separate, rebuilt from empty and never migrated: 279's (45 to 46),
then #95's (`package-gate` owed kind, hold-back fields, `qa.gate_application`).
279's own NFR already says `run_seq` is drawn under #95's per-period lock once
that lands (267 c17).

**Two of 279's amendments touch the same signed text as #95's.** REQ-DASH-264
c1 is amended by both (wording combined below). REQ-DASH-264 c11 and c12 are
retired or re-keyed by 279. v5's 272 c17 follows 279 rather than
`sameDelivery`.

## The requirements

| Id | MoSCoW | What it covers | Changed in v5 |
|---|---|---|---|
| REQ-PIPE-266 | must | Package = shared receipt instant, from the record. Gated together once every file is checked. A crash waits; a backstop refusal = held back. Hold-backs written when final, never repeated. A decision during a gate is refused (exit 75); a person's promotion is compare-and-swap. | `package-gate` kind mandatory; c4 per application + `run_seq`; c5 exit; c9 no repeat; c15 two forms + next-pass line + 75; c16 CAS, not restart |
| REQ-PIPE-267 | must | The gate's view, counted per check, made transitive over JOINABLE waiting supplies, settled by the fixed point, one lock per period, one outer transaction. | B2 per check; B3 JOINABLE; named entries; V4-Q1 (c6 exception, c15); S2 strict re-cast; S10 re-ordered; S1 lock/txn; S4; S6 fixtures; S9 marker; replacement setting pinned; joined-supply wording |
| ~~REQ-PIPE-268~~ | - | Withdrawn (v4). Id spent. | - |
| REQ-PIPE-269 | must | The warehouse view, per check. A could-not-run counts only toward the declaring table. An owed re-check reads red and raises nothing. | B2 per check; S5 widened to every decision that moves a table; c6 "not owed counts nothing"; 279's function; OQ1 resolved (B) |
| REQ-PIPE-270 | must | Strict: could-not-run is red for every reason. | Reason keys kept |
| REQ-PIPE-271 | must | Open at filing. Inherit once. A stale or refused carry-forward is warned, naming one step. | V4-Q2: the warning names REQ-PIPE-280; queue period-items group; door test |
| REQ-DASH-272 | must | The awaiting line's warehouse clause, the cross-table grid (Option C), and the history rows. | B1 third bucket; S1 worst-of; S2 positional marks; S3 row stays one button; S4 phone labels; S5 waiting state; hide empty column; re-check its own point (K3 = C) |
| REQ-GEN-273 | must | The target compares the file's own checks. Five scenarios pin the gate. | S2 pinned as the mirror; S10 re-ordered |
| REQ-DOCS-274 | should | Supplier guidance: send one zip. | Unchanged |
| REQ-DASH-275 | must | Held back with its delivery: the top notice, the chain and root, one card line. | `data-held-back`; before 204's notice; superseded as well as rejected; joined form; root page's forewarning |
| REQ-PIPE-276 | must | What the terminal says about a package gate. | CLI v4 S1-S13, notes |
| REQ-DASH-277 | should | "In place" becomes "in place in the warehouse". The control reads "In the warehouse on". | Open question A taken; both label places; test scoped; 80 columns |
| REQ-PIPE-278 | must | One ticket and one still-failing record per root cause. | A root turned down or replaced stops being the root (S8); joined supplies; S2 re-cast |
| **REQ-PIPE-280** | must | **New.** Carry a newer supply forward in one decision: one log entry, one re-evaluation, never a gap. Widens REQ-PIPE-099 by one operation. | V4-Q2 = A |
| REQ-DASH-204 | must | Re-folded (replaces the close-out version). A check that could not run because another table is absent. | `data-no-promoted`; after 275's notice; package form now on Notifications' page; joined form; "was turned down" |
| REQ-PIPE-210 | should | Re-folded (replaces the close-out version). The queue: beneath the root, not counted, not pickable. | Complete override command; package reason beats "another version waiting"; S2 re-cast |

REQ-PIPE-211's edits are unchanged from summary-v4.md. Its c3 reference to
"REQ-PIPE-267 criterion 2" is still the right criterion.

**Build order** (architect, extended for 279 and 280):
1. **REQ-PIPE-279**, which is outside this batch and comes first.
2. 269.
3. 271 and 280 together. The warning names the operation.
4. 270, 266, 267, 273 and 278, **in one push behind one bootstrap**, with
   #95's schema bump.
5. 276.
6. 204, 210, 272, 275 and 277.
7. 274.

## What changed from v4, requirement by requirement

- **266.**
  - c1: siblings come from the record, via 279.
  - c2 names `processing_pass._one`.
  - c3: the owed item is a NEW kind, `package-gate`. It is also owed for a
    package of one whose period lock is contended (architect S2).
  - c4: one instant per gate application, whatever the entry. "Newer" is
    `run_seq`.
  - c5: the file exits as its own results say (architect S7, CLI S2).
  - c9: no new entry for an unchanged outcome, de-duplicated on the
    structured fields (architect S4).
  - c15: the "being gated" form, the next-pass line and exit 75 (V4-Q3;
    CLI S3a-c).
  - c16: compare-and-swap. On change it refuses and exits 1, and it never
    restarts the gate (architect S3).
  - Tests: the owed kind between runs; the fixtures named; exit 75; S16
    refused.
  - New decisions record each change.
- **267.**
  - c1: counted per check from `qa.check_read` (architect B2).
  - c2: the entries named (`recheck._run_claimed`, `knock_on.complete`, the
    package gate, `processing_pass._one`). A re-evaluation is never an entry.
  - **New c3: JOINABLE** (architect B3).
  - c4: re-applied every round. A joined supply that ends not promoting keeps
    its results and decisions (S4, restoring v3 268 c3).
  - c5: each check is judged by its newest qualifying verdict. Without this,
    the staggered flicker case (below) became a wait for a person; found
    while walking it.
  - c6: an exception. A check declared on the not-promoting table is not
    re-run where the warehouse holds no supply of that table, because it
    would count toward nothing.
  - c11 uses 279's staging-or-period field instead of a column.
  - c12: the settled marker, `qa.gate_application` (architect S9).
  - c13: the joined-supply wording and "checks of its own data" (CLI S12).
  - **New c15**: V4-Q1, stated.
  - New c16: the replacement setting is pinned in fixtures (v4 open
    question 1, closed).
  - **New c17**: one try-lock per (collection, period), no tools inside a
    decision transaction, one outer transaction, all or nothing (architect
    S1).
  - **c18: S2 strict re-cast as the mirror.**
  - New c19: three named fixture contents (architect S6).
  - Tests:
    - S1 green asserts the knock-on re-runs nothing;
    - the new V4-Q1 test;
    - S3/S2b re-cast;
    - **S10 re-ordered, with the original order as a second test**;
    - T14 re-titled for B3, plus a package member not joined;
    - concurrency tests.
- **269.**
  - c1-c3: per check (B2) and newest by `run_seq`.
  - c5 widened to every decision that moves a table. "Owed at T" comes from
    the cause decision's effective instant (architect S5). A counted check
    with nothing owed reads red, `no-current-result`.
  - **New c6**: a check not owed to the supply counts nothing, so a clean
    Clients promoted alone is not red.
  - c7 is 279's function, plus shown and counted.
  - v4 c6 removed: it duplicated 278 c5.
  - Tests: the widened Q5, and per check.
  - OQ1 resolved: the held table's rows show No data (dashboard B).
- **270.** c2 keeps `unrunnable_reason`/`held_reason` (architect note).
- **271.** c7: the warning names REQ-PIPE-280's command, on a line of its
  own, in the queue's period-items group and the door. c8 clears on it. The
  test covers the door. The T18 open question gains the architect's
  mechanism.
- **272.**
  - c6: row order kept (`crossTableRowOrder`); a column with no result is
    hidden.
  - c7: three buckets (B1), from 279's per-check record.
  - c8: worst-of word (S1) and positional marks with "·" (S2).
  - c11: the key explains "·".
  - c12: the whole row is one button, notes are plain text, links only in
    the panel (S3).
  - c13: the joined forms.
  - c15: no link in a row.
  - c16: phone labels (S4).
  - c17: the re-check is its own point (K3 = C).
  - c19: superseded too.
  - c20: joined supplies and the rule-made promotion's "why".
  - **New c21: "Checked, waiting for the rest of its delivery"** (S5 and the
    architect's transient-green note).
  - Tests extended, plus a JS test.
  - OQ1 resolved.
- **273.** c4: S2 pinned as the mirror and S10 re-ordered. c8 re-cast.
- **275.**
  - c1: `data-held-back`, placed before 204's notice, with the joined form.
  - c3: the root page's "If this file is turned down ..." (a dropped v3
    item).
  - c4: the card line for a joined set.
  - c6: superseded as well as rejected.
  - The exec-view sentence (v3 shape 4) is dropped knowingly; see its
    decisions.
- **276.** Rewritten around the CLI v4 review:
  - one word for every `promotion-withheld`;
  - "turned down" kept clear of `_gate_words`;
  - the full exit order, with `qa`'s exit fed by the gate;
  - complete commands;
  - grouping up to eight;
  - the three consequence lines;
  - the quiet "being gated" group;
  - owed-re-check words;
  - the rule-made promotion's words;
  - the crashed-sibling next-pass line;
  - the supplier hint;
  - 80 columns;
  - the proposed layout.
- **277.**
  - c3-c4 are no longer provisional: "In the warehouse on", with ids and the
    parameter kept.
  - Both label places.
  - 80 columns.
  - The text walk is scoped to the dataset and collection views.
- **278.** c1: joined supplies count; a turned-down or replaced root stops
  being the root (architect S8). Tests re-cast and added.
- **280 (new).** One carry-forward decision, one re-evaluation, no committed
  gap, consequences keyed. It amends REQ-PIPE-099 c1, c2 and c10.
- **204.**
  - c1: `data-no-promoted`, placed after 275's notice.
  - c2: the joined form and "was turned down".
  - c12: the test is now on Notifications' page.
- **210.**
  - c1: joined supplies count.
  - c3: the complete command, and the package reason beats
    `ANOTHER_VERSION_WAITING`.
  - c9: tests re-cast.

## Amendments to SIGNED requirements: only what is new or changed since summary-v4.md

Every amendment in summary-v4.md that is not listed here **stands as worded
there**. Those are: REQ-PIPE-081 c1, REQ-PIPE-105 c1, REQ-PIPE-121 c9, c12 and
NFR 4, REQ-PIPE-121 decision 11, REQ-PIPE-083 c21, REQ-PIPE-075 c2,
REQ-PIPE-079 c14 and decision 23, REQ-PIPE-115 c20, REQ-PIPE-098 c4,
REQ-DASH-264 c2, c7 and NFR 2, REQ-GEN-186 c3, REQ-TEST-159 c1, REQ-DASH-182
c3, REQ-GEN-199 c18 and REQ-GHUB-229 c5.

**REQ-QAC-037 c7** (signed 2026-09-23), by REQ-PIPE-269. **Changed: per
check.**
- NEW: "THE SYSTEM SHALL fold a cross-table check's EVALUATED verdict into the
  status of every supply THAT CHECK read (REQ-PIPE-279) - for a supply in
  place in the warehouse, only a verdict whose every read supply is the one in
  place (REQ-PIPE-269) - and a check that COULD NOT RUN only into the status of
  the supply the check is declared on, and into nothing where the declaring
  table is the one that could not be read; and SHALL NOT leave a supply
  reading green while a check counted toward it reads red. AMENDED `<date>` by
  REQ-PIPE-269 (Keith, 2026-10-21: judged by supply; 2026-10-22, Q13 = B)."

**REQ-DASH-264 c1** (signed 2026-10-19), by REQ-PIPE-269 **and REQ-PIPE-279**.
**Changed: one wording for both.** This is to be agreed with 279's
finalising pass, so that the criterion is amended once.
- NEW: "THE SYSTEM SHALL show on a dataset page, for each check, the newest
  result by evaluation order (REQ-PIPE-279) that is counted toward the supply
  the page is about on or before the in-place-on date (REQ-PIPE-269),
  whichever table's run recorded it, so a re-check of one table that re-runs
  another's cross-table checks changes the other table's page from the day it
  was recorded, and a result that read a supply not in place in the warehouse
  never changes an in-place supply's page. AMENDED `<date>` by REQ-PIPE-269
  and REQ-PIPE-279."

**REQ-DASH-264 c5** (signed 2026-10-19), by REQ-PIPE-269. **Now taken**
(open question B, as both reviewers recommend).
- OLD: "THE SYSTEM SHALL leave the held dataset's own status red by
  REQ-PIPE-115 criterion 10, the cross-table results changing only the
  cross-table section's own pill."
- NEW: append: "A result that could not run counts toward the table the check
  is declared on only (REQ-PIPE-269 criterion 4), so on the held table's page
  it is shown, its row's pill reads No data, and it does not colour the
  section's pill. AMENDED `<date>` by REQ-PIPE-269."

**REQ-PIPE-081 c20 and c23** (signed 2026-09-26), by REQ-DASH-277. **No
longer provisional.** The wording is as summary-v4.md gives it, with
`<picker label>` = "In the warehouse on". c23's amendment keeps the ids and
the `in-place-on` parameter.

**REQ-DASH-208 c4**, by REQ-DASH-277:
- NEW: "'`<scenario id>` · in the warehouse on `<date>`'".

**REQ-PIPE-099** (signed), by **REQ-PIPE-280**. **New in v5.**
- **c1** OLD: "THE SYSTEM SHALL offer inherit and un-inherit as operator
  actions, for one dataset and one period at a time."
  - NEW: "THE SYSTEM SHALL offer inherit, un-inherit and carry-forward
    (REQ-PIPE-280) as operator actions, for one dataset and one period at a
    time. AMENDED `<date>` by REQ-PIPE-280 (Keith, 2026-10-22, V4-Q2 = A)."
- **c2**: "each of them" now covers carry-forward. Append: "A carry-forward
  records what the period stood on before and after, as one entry. AMENDED
  `<date>` by REQ-PIPE-280."
- **c10**, "explicit confirmation before un-inheriting": append "and before
  carrying forward. AMENDED `<date>` by REQ-PIPE-280."
- c6, c7, c8, c9, c11 and c12 are unchanged. 280 meets each of them as
  written.

**REQ-PIPE-083 c21**, by REQ-PIPE-278. A one-phrase change to v4's wording:
"held back with a package-mate" becomes "held back because another supply
of its gate application was not promoting".

**No amendment needed**, newly checked:
- REQ-GHUB-082 names no exit code for a refusal (checked 2026-10-23, to
  re-check at build). 75 is added to `supply decide`'s documented exit codes
  by 266 c15.
- No signed requirement quotes lifecycle_report's "withheld by the rule".

## Every case under v5

Every fixture states each of the six tables (267 c19):
- ESTABLISHED: 2024-Q3 with v1 of all six tables;
- FIRST-TIME: 2024-Q4 with Case Workers, Carers, Investigations and
  Placements, and no Clients or Notifications;
- EMPTY-BUT-WORKERS: 2024-Q4 with Case Workers and Carers only.

| # | Scenario | Under v5 | Where |
|---|---|---|---|
| S1 green | Zip of Clients v2 + Notifications v2 over ESTABLISHED. Notifications v2 is red on its own data. | Notifications v2 is held back. Clients v2 is re-checked against Notifications v1, passes, and is promoted. The knock-on re-runs nothing. | 266, 267 |
| S1 red | The same, but Clients v2 drops clients that Notifications v1 points at. | Clients v2 is held back with the Notifications. Notice, grid row, card line, one ticket. | 267 c13, 272, 275, 276, 278 |
| S1 step 4 | A person promotes, or turns down, Notifications v2. | Promote: the knock-on re-gates Clients v2 and it promotes. Turn down: nothing re-runs; Clients v2 now needs its own decision and its own ticket. | 267, 275 c6, 278 c1 |
| S2 | First-time zip, both green. | Promoted together, one verdict, one knock-on. | 266, 269 |
| **V4-Q1** | First-time zip, Notifications v2 red on its own data. | **Clients v2 promotes alone**, with no re-run. Notifications v2 is held back on its own reds. | 267 c6, c15; 269 c6 |
| **S2 strict (mirror)** | First-time zip, Clients v2 red on its own data, Notifications v2 green. | Clients v2 is held back. Notifications' Client reference is re-run against no Clients: could not run, red for Notifications, which is held back. 204's package form is on Notifications' page. One ticket (Clients'), naming Notifications. | 267 c18, 204, 210, 278 |
| S3, S2b | Staggered first-time pair; then a correction. | The waiting partner joins the later file's application, and both promote. | 267 c2-c3 |
| S3b | The earlier file is waiting on its own red. | It joins and is not promoting. The arrival is re-checked against the warehouse. | 267 |
| S4 | A held-back partner's run. | Never counted toward the promoted supply, judged per check. | 269 |
| S5 | A cascade. | A fixed point, the same in any order, grouped by root in the terminal. | 267, 276 c6 |
| S6 | The Investigations-then-Notifications chain; the owe-nothing quarter. | As v4. | 272, 275, 271 |
| S7, S9 | A stale or refused carry-forward. | Warned, naming **one step**. The person carries it forward in one decision, so no reader goes red in between. | 271, **280** |
| **S10** | **Re-ordered**: Notifications 08:40, Investigations 09:00, Clients 09:20. | All three promote at Clients' arrival. **Original order**: Clients alone at 09:00; the other two together at 09:20. | 267 tests |
| S11 | Two files waiting on each other. | Both join a third arrival. | 267 |
| S14, S14b | One red Placements in a six-table zip. | Only Placements is held back, **counted per check** (B2). | 269 |
| S15 | The early file is red for days. | Explained; "Not due until ..."; no ticket. | 204, 278 |
| S16 | A person promotes while what they saw has moved. | **Refused, compare-and-swap, exit 1.** During a gate: refused, exit 75. | 266 c15-c16 |
| T14 | Re-filed partners. | Each is gated on results recorded for its new period, never joined while its re-check is owed (B3). | 267 c3 |
| Q5 widened | An un-inherit or carry-forward whose knock-on is owed. | `recheck-owed`, raising nothing. | 269 c5, 278 |
| Concurrency | Two applications in one period; a failed move. | The second is left owed and never waits. A failed move promotes nothing. | 267 c17 |
| Staggered | The same v2 files, minutes apart. | Walked through below. | 267, 272, 275 |
| Cloud | Separate S3 uploads. | Each is a package of one (known limitation). | 266 c6, 274 |

## Walk-through 1: S1, a zip (for Keith's final check-in)

**The starting point.** 2024-Q3 holds v1 of all six Child Protection tables
in the warehouse, all green. Clients v1 and Notifications v1 were received at
9:00am on Monday, 1 July 2024.

At 9:00am on Monday, 21 October 2024, a zip arrives holding Clients v2 and
Notifications v2. Notifications v2 has blank values, so 2 of its own checks
fail.

**1. Both files are filed.** They share one receipt instant, so they are one
package (266 c1). Both are staged into 2024-Q3. The quarter is already open.

**2. Clients v2 is checked first (receipt order).** Its own checks pass.
Its run evaluates every check that reads Clients:
- Notifications' Client reference, against the staged Notifications v2:
  Pass;
- Investigations' Client reference and Closed-case hygiene, against
  Investigations v1 in the warehouse: Pass;
- Placements' Client reference, against Placements v1: Pass.

Each result records which supply of each table it read (279). Nothing is
gated, and a `package-gate` item is owed.

- *Warehouse*: unchanged, all v1.
- *Staging*: Clients v2 checked; Notifications v2 not yet checked.
- *Dashboard*: Clients' page reads "Checked, waiting for the rest of its
  delivery (received 9:00am Monday, 21 October 2024): 1 of 2 files checked.
  Nothing needs deciding yet." (272 c21). It does not read green, and it does
  not read "Awaiting a decision".
- *Terminal*: the queue shows a dim, uncounted line, "Checking a delivery
  received 21 Oct 09:00 (1 of 2 files checked)". `mothman cp qa --commit`
  on the Clients file exits 0, as its own results say. A person who tries to
  decide is refused: "The delivery received ... is still being checked (1 of
  2 files checked); decide once it is gated." The command exits 75.

**3. Notifications v2 is checked.**
- Its own checks: 2 fail.
- Client reference is CARRIED from Clients v2's run (REQ-PIPE-265: the same
  supplies), so that pair has one evaluation and one point.
- Its other checks are evaluated: Assigned worker reference against Case
  Workers v1 and Escalation completeness against Investigations v1, both
  Pass.

**4. The package is gated as one application.** The rule takes the
(Child Protection, 2024-Q3) lock.
- Notifications v2 is not promoting, because of its own reds. Its
  `promotion-withheld` entry is written now, which is final.
- Clients v2's counted Client reference read Notifications v2, so it is
  re-run against Notifications v1, the one in the warehouse. That is a
  readers-only run whose cause is Notifications v2's hold-back. It is a
  re-check point of its own on Clients v2 (279 K3 = C), and it is not counted
  anywhere until the application settles.

**5a. Green branch.** The re-check passes. Clients v2 is promoted by the
rule, in one transaction. Its record names the package's instant. The
application settles. One re-evaluation is owed for `cp_clients`, and it
re-runs **nothing**: every reader's counted result already read Clients v2.
- *Warehouse*: Clients v2, Notifications v1, and the rest v1. This pair has
  been checked.
- *Staging*: Notifications v2, awaiting a decision.
- *Dashboard, Notifications' page*: "Awaiting a decision — the results below
  are the newest supply, received 9:00am Monday, 21 October 2024, which is not
  in place in the warehouse yet. The supply in place in the warehouse is the
  one received 9:00am Monday, 1 July 2024, and is Green."
  - Its grid has one column, "Against what's in the warehouse". The staged
    column is hidden because it is empty, since Clients v2 is now in the
    warehouse.
  - Client reference reads "Pass ✓ ✓ ✓, Client Register received 21 Oct".
- *Dashboard, Clients' page*: Green. Client reference reads "Pass,
  Notifications received 1 Jul", which is the re-check. Its supply history
  says "Promoted 9:0x by the rule, re-checked against the Notifications in
  place in the warehouse (received 9:00am Monday, 1 July 2024) because the
  Notifications received with it was held back."
- *Card*: red, because Notifications' newest supply waits. There is no "held
  back together" line, because nothing is held back with Notifications.
- *Terminal*: one counted row, "cp-notifications 2024-Q3 received 21 Oct 09:00
  red - 2 of its own checks fail". The kept report for Clients v2 says
  "promoted by the rule - Client reference re-checked against the
  cp-notifications in place in the warehouse (received 1 Jul), green, because
  the cp-notifications received with it was held back".
  `mothman pipeline process` exits 1.
- *Tickets*: one, for Notifications 2024-Q3. No still-failing record is
  written, because nothing the gate did changed Notifications' failure.

**5b. Red branch.** The re-check fails. Clients v2 is held back. Its entry
reads: "Held back: Client reference, re-checked against the Notifications in
place in the warehouse (received 1 Jul) because the Notifications received
with it was held back. This supply's checks of its own data passed."
Nothing is promoted, and nothing is owed.
- *Warehouse*: all v1, unchanged.
- *Staging*: Clients v2 and Notifications v2, both awaiting a decision.
- *Dashboard, Clients' page*:
  - Its awaiting line ends "The supply in place in the warehouse is the one
    received 9:00am Monday, 1 July 2024, and is Green."
  - Above that, the notice: "**Held back with the Notifications received with
    it.** That file (received 9:00am Monday, 21 October 2024) was held back, so
    this supply was re-checked against the Notifications in place in the
    warehouse, and 1 cross-table check fails against it. It is checked again
    by itself once a Notifications supply is promoted."
  - Client reference shows both cells: Staged "Pass ✓ ✓ ✓, Notifications
    received 21 Oct"; In the warehouse "Fail ✗ ✗ ✗, Notifications received 1
    Jul — why it is held back". The pill is Red.
- *Dashboard, Notifications' page*: awaiting, with the warehouse Green. It
  says "Holding back with it: Client Register" and "If this file is turned
  down, the Client Register supply needs its own decision."
- *Card*: "[Red] Held back together: Notifications, Client Register (one
  delivery, received 9:00am Monday, 21 October 2024)".
- *Terminal*:
  ```
  1 supply waiting on a decision in Child Protection (1 more held back with it, listed beneath)

  cp-notifications  2024-Q3  received 21 Oct 09:00  red - 2 of its own checks fail
    held back with it (same delivery):
    - cp-clients  nothing to decide here - Client reference failed against the
      cp-notifications in place in the warehouse (received 1 Jul).
      Deciding cp-notifications settles it. To override:
      mothman supply decide --operation promote --dataset cp-clients --period 2024-Q3 --supply <id> --reason '<why>'
  ```
- *Tickets*: one, Notifications', with "Also held back by this: Client
  Register 2024-Q3".

**6. Later.**
- **A person promotes Notifications v2.** The consequences say that it
  "re-checks cp-clients' waiting supply received 21 Oct 09:00; if it is
  green, the rule promotes it". Notifications v2 goes in red-promoted. Its
  knock-on re-gates Clients v2, whose arrival result against Notifications v2
  is now about the warehouse and passes, so the rule promotes it. The
  warehouse holds v2 and v2.
- **A person turns Notifications v2 down.** Nothing re-runs (Q10). In the red
  branch, Clients v2's notice becomes "The Notifications file received with
  it was turned down; this supply now needs its own decision." It becomes its
  own counted row and gets its own ticket (278 c1). In the green branch,
  Notifications' page returns to v1's verdict.

## Walk-through 2: the same files, staggered (Keith's alternate)

The starting point is the same: 2024-Q3 holds v1 of everything, all green.
The same two files now arrive separately, five minutes apart. Each is a
package of one. Notifications v2 still has 2 blank-value failures. Its new
notifications also point at clients that are new in Clients v2.

### Order A: Notifications v2 at 9:00am, Clients v2 at 9:05am

**9:00, Notifications v2 alone.** Its run reads Clients v1 from the
warehouse, because no Clients is staged. Client reference fails against
Clients v1 because of the new clients, and its own 2 checks fail. Its gate
application has nothing to join, so it is held back.
- *Warehouse*: all v1.
- *Staging*: Notifications v2, waiting.
- *Dashboard*: Notifications' page is awaiting, with the warehouse Green.
  Client reference reads "Fail, Client Register received 1 Jul" under
  "Against what's in the warehouse". Clients' page stays Green: Notifications
  v2's result read a supply not in the warehouse, so it is not counted toward
  Clients v1 (S4).
- *Terminal*: one counted row, cp-notifications, red.
- *Tickets*: Notifications'.

**9:05, Clients v2 alone.** Its run evaluates Notifications' Client reference
against the staged Notifications v2: Pass. That is a SECOND point on
Notifications v2, whose cause is Clients v2's delivery (279 K3 = C). The gate
application is Clients v2 plus Notifications v2, which is joined because it
is waiting, connected by that verdict and joinable. Notifications v2 is not
promoting, because of its own reds. Clients v2's Client reference read it, so
the check is re-run against Notifications v1.
- **Green branch.** The re-run passes, and Clients v2 promotes alone at 9:05.
  The knock-on re-runs nothing. Notifications v2's hold-back is unchanged and
  no new entry is written (266 c9).
  - *Warehouse*: Clients v2 and Notifications v1. This is the same end state
    as the zip's green branch.
  - *Dashboard, Notifications' page*:
    - Its 9:00 result read Clients v1, which has left the warehouse, so it
      sits in **neither** cell and stays only in the check's history (272
      c7, dashboard B1).
    - Its 9:05 result read Clients v2, now in the warehouse: "Pass, Client
      Register received 21 Oct".
    - Its trend shows two points, 9:00 and 9:05.
  - *Flicker*: none. Clients never read red. Notifications was red throughout
    for its own reasons.
- **Red branch.** The re-run fails, and Clients v2 is held back by the
  waiting Notifications: "Held back: Client reference, re-checked against the
  Notifications in place in the warehouse (received 1 Jul) because the
  Notifications waiting for a decision (received 9:00am Monday, 21 October
  2024) is held back. This supply's checks of its own data passed."
  - *Dashboard*: Clients' page shows the joined form of the notice, "**Held
    back by the Notifications waiting for a decision.** ...". The card reads
    "[Red] Held back together: Notifications, Client Register (received 9:00am
    and 9:05am, Monday 21 October 2024)".
  - *Terminal*: cp-clients is beneath cp-notifications, as "held back by it",
    with the override command and a dim line: "Files sent separately are
    gated as each arrives; sent as one zip they are gated together."
  - *Tickets*: one, Notifications', naming Clients.

### Order B: Clients v2 at 9:00am, Notifications v2 at 9:05am

**9:00, Clients v2 alone.** Its run reads Notifications v1 from the
warehouse, because nothing is staged.
- **Green branch.** Client reference passes against Notifications v1, and
  Clients v2 promotes at 9:00. The knock-on re-runs nothing.
  - At 9:05, Notifications v2 arrives. It is checked against Clients v2 in the
    warehouse: Client reference passes, and 2 of its own checks fail. It is
    held back.
  - The end state is the same as the zip's green branch: Clients v2 and
    Notifications v1 in the warehouse, and one ticket, Notifications'.
- **Red branch.** Client reference fails against Notifications v1, a real
  failing verdict. Clients v2 is held back on its own red and gets a ticket of
  its own.
  - At 9:05, Notifications v2 arrives. Its run checks Client reference
    against the staged Clients v2: Pass. Clients v2 joins the application, and
    Notifications v2 is not promoting (its own reds).
  - Clients v2 is a joined supply, so nothing is re-run for it (267 c4). Its
    counted verdict falls back to 9:00's Fail against Notifications v1, it
    stays held back, and its decision is unchanged.
  - *End state*: both are waiting, as in the zip's red branch. The
    difference: **two tickets, each its own root**, rather than one. Clients'
    failure against Notifications v1 was found before Notifications v2
    existed, so it is not "another table's doing". This is the staggered
    cost, not a defect, and the supplier guidance (274) is the remedy.

### The flicker Keith accepted, shown end to end

This is the same as Order B, but this time Notifications v2 is clean: no
blank values, and it is consistent with Clients v2.
1. 9:00: Clients v2 fails Client reference against Notifications v1. It is
   **red and held back**, and it is ticketed.
2. 9:05: Notifications v2 is checked against the staged Clients v2 and
   passes. The application joins Clients v2. Each is judged on its other
   verdicts, and its counted Client reference now reads the other, which is
   promoting. No re-check is needed, and the fixed point promotes **both
   together** at 9:05, in one transaction with one knock-on. The knock-on
   re-runs nothing.
3. *Warehouse*: Clients v2 and Notifications v2.
4. *Dashboard*: Clients' history reads "Promoted 9:05am with the
   Notifications supply received 9:05am, by the rule". The 9:00 hold-back
   stays in the log.
5. *Ticket*: Clients', opened at 9:00 and closed when the slot is
   reconciled.

That is five minutes of red that clears by itself: the accepted flicker.
Sending the two as one zip avoids it entirely.

In the reverse order (Notifications v2 clean at 9:00, Clients v2 at 9:05),
Notifications reads red for five minutes against Clients v1, then both
promote together. Its 9:00 result against Clients v1 then sits in neither
grid cell.

## Carry-over check

### summary.md, "Keith's answers on the v4 reviews, 2026-10-22 (Perth)"

| Decision | Where in v5 |
|---|---|
| V4-Q1 = A: a clean table promotes alone when the only failing table depends on it; it supersedes "Clients is held too" for that case; B rejected | 267 c6 (exception), c15, d "A CLEAN TABLE PROMOTES ALONE"; 269 c6; V4-Q1 test |
| ...the mirror is unchanged; S2 strict is re-cast as the mirror | 267 c18; 204 c2/c12, d; 210 c9; 273 c4, c8; 278 c8; walk-through |
| ...S10 is re-ordered, with the original order kept as a second test asserting Clients promotes at 09:00 | 267 S10 tests; 273 c4 |
| Deterministic matching is its own requirement (279), built before 265 is flipped; v5 references it rather than defining its own | Header; "How #95 stands on REQ-PIPE-279"; 266 c1, 267 c1/c11, 269 c1-c3/c7, 272 c7/c17 |
| V4-Q2 = A: one "carry the newer one forward" step, from the door and by flags, one decision, one re-check of readers, nothing red in between; widens 099 by one operation; B rejected; 271's warning names the one step and its command on a line of its own | **REQ-PIPE-280** (whole); 271 c7-c8, c11, d; 099 amendment |
| V4-Q3 = A: a decision refused because its delivery is still being checked exits 75, documented; B rejected; applies to 266 c15 and 276 c2 | 266 c15, d; 276 c11 (the refusal; v4's c2 and c10 were renumbered), NFR scriptability |

### review-architect-v4.md

| Item | Where in v5 |
|---|---|
| B1, S2 strict and S10 contradict Q13 = B | Put to Keith as V4-Q1, answered A; carried as above |
| B2, count per check, not per run | 267 c1, d; 269 c1-c2, test, d; via 279's `qa.check_read` |
| B3, JOINABLE | 267 c3, d; T14 tests |
| Section 1: "decisions unchanged" dropped by the fold | 267 c4; 266 c9 |
| Section 2: name the gate entries; a re-evaluation is never an entry | 267 c2, d |
| S1, per-(collection, period) try-lock; no tools inside a decision transaction; one outer transaction with savepoints; census after commit | 267 c17, d, tests, NFRs. **One deviation, for the architect:** a failed move owes the whole application, rather than returning that supply as not promoting (267 d "A FAILED MOVE OWES THE WHOLE APPLICATION") |
| S2, the `package-gate` owed kind is mandatory | 266 c3, d |
| S3, compare-and-swap on a person's override | 266 c16, d (exit 1, not 75, with the reason) |
| S4, no repeated `promotion-withheld`; de-duplicate on structured fields | 266 c9, d; 267 c4 |
| S5, owed by any decision that moved a table; nothing owed reads red; "owed at T" from effective_at | 269 c5, d, test |
| S6, fixture period content incl. Case Workers | 267 c19, d; every test names its fixture |
| S7, the "SHALL exit 0" | 266 c5, d |
| S8, a root rejected or superseded becomes its own root | 278 c1, d, test |
| S9, a settled marker | 267 c12 (`qa.gate_application`) |
| Note: carried verdicts read per check | 269 d "COUNTED PER CHECK" |
| Note: keep `unrunnable_reason`/`held_reason` | 270 c2, d |
| Note: the same instant for every application; a decision-caused run outranks an arrival | 266 c4, d (`run_seq`, 279 K1) |
| Note: 267 c3 re-evaluated every round | 267 c4 |
| Note: 269 c6 duplicates 278 c5 | 269 c6 removed; 278 d |
| Note: 277's text walk scoped | 277 c7, d |
| Note: no surface shows "checked, waiting for its package" | 272 c21; 276 c12 |
| OQ A-E readings | A, B taken (277, 269/264 c5); C's mechanism in 271 OQ1; D, E stay Keith's |
| Reading: pin the mirrored S2 | 273 c4 |
| Reading: case 3a, only the declaring table stays red | Confirmed below |
| Reading: 267 OQ1, pin a replacement setting | 267 c16 |

### review-dashboard-ux-v4.md

| Item | Where in v5 |
|---|---|
| "M4" was #258 M4, `crossTableRowOrder` | 272 c6, d |
| 204 c1's modifier class should be a data- attribute; 275 gets its own | 204 c1 (`data-no-promoted`); 275 c1 (`data-held-back`) |
| Notice order: 275 before 204 | 275 c1; 204 c1 |
| S15: superseded as well as rejected; 204's package form "was turned down" | 275 c6; 204 c2 |
| Dropped v3 items: the root page's "If this file is turned down ..."; the exec sentence | 275 c3 (folded); the exec sentence dropped knowingly (275 d) |
| **B1, the third bucket** | 272 c7, d, staggered e2e test |
| S1, worst-of word | 272 c8, d, JS test |
| S2, positional marks with a placeholder | 272 c8, c11, d, JS test |
| S3, the row stays one button; links only in the panel | 272 c12, c15, d |
| S4, phone labels; omit an all-dash result | 272 c16, d, test |
| S5, "Checked, waiting for the rest of its delivery" | 272 c21, d, test |
| Hide an empty column | 272 c6, d, test (to mention at the walk-through) |
| OQ A, "In the warehouse on", ids kept, both label places | 277 c3-c4, c6, d |
| OQ B, show the rows, row pills No data, section pill agrees | 269 d; REQ-DASH-264 c5 amendment; 272 test |
| Note: a could-not-run clause in the panel, not the blurb | 272 c12, d |
| Note: 272 c20 fires for an earlier hold-back too | 272 c20 |
| Note: S2's "not a fault" stays correct | 204 d |

### review-cli-ux-v4.md

| Item | Where in v5 |
|---|---|
| B1 | V4-Q1, as above |
| B2 | V4-Q2, REQ-PIPE-280 |
| S1, the full exit order; `cp qa`'s exit fed by the gate | 276 c3, d, test |
| S2, a waiting file's exit | 266 c5 |
| S3a gating form; S3b next-pass line; S3c 75 (V4-Q3); S3d quiet uncounted group | 266 c15; 276 c11, c12, d |
| S4, one word for `promotion-withheld`, `lifecycle_report.outcome_of` included | 276 c1, d, test |
| S5, "turned down" never through `_gate_words` | 276 c2, d, test |
| S6, owed re-check terminal wording | 276 c13, d, test |
| S7, rule-made promotion wording | 276 c14, d, test; the page's half in 272 c20 |
| S8, up to eight, one line per outcome, root first | 276 c6, d |
| S9 a/b/c, override consequences | 276 c8, c9, d, tests |
| S10, complete copyable commands and the door route | 276 c4; 210 c3 |
| S11, the terminal layout; no `[Red]` | 276 c6 (the layout quoted), d |
| S12, "checks of its own data" | 267 c13; 276 c5 |
| S13, 271's warning: period-items group, door, commands on their own lines | 271 c7, c11, d |
| Note: v3-shape S9 supplier hint | 276 c17 |
| Note: v3-shape point 7, the package reason beats `ANOTHER_VERSION_WAITING` | 210 c3 |
| Note: hide-until-settled and the quiet group | 267 c12; 276 c12 |
| Note: support 210 OQ2 = A | 210 d (still Keith's, E) |
| Note: 277's 80 columns | 277 c5, d; 276 c18 |
| Note: crashed sibling "mothman pipeline process" | 276 c15 |

### REQ-PIPE-279 summary, "#95 v4 knock-ons"

| Knock-on | Where |
|---|---|
| 267 c1 and 269 c1-2 cite 279's record, not `qa.tables_read` | 267 c1; 269 c1-c2 |
| 269 c7's function is 279's | 269 c7 |
| 279 K3 = C: a later file's re-check of a shared check is a second point | 272 c17; walk-through 2 |

**Nothing is left only in prose.** The deviations and readings are listed in
the next section.

## Non-functional angles

**Answered in the requirements:**
- Performance: the cascade is bounded, and joining costs no run. A check that
  could count toward nothing is not re-run.
- Scalability (~30 collections):
  - one lock and one connected set per collection and period;
  - one card line per root's set;
  - one ticket per root;
  - one grid row per relationship;
  - up to eight names in the terminal.
- Reliability:
  - a crash waits;
  - a contended lock waits one pass and never blocks;
  - a failed move promotes nothing;
  - the owed `package-gate` item resumes.
- Concurrency: one application per period at a time; compare-and-swap on a
  person's override; the delivery-still-checked refusal (75).
- Determinism: order is `run_seq`; reads come from 279's record; the fixed
  point is order-independent.
- Auditability: structured hold-back fields; `qa.gate_application`; a
  carry-forward is one entry naming before and after.
- Observability and noise: nothing is raised for `recheck-owed` or for a
  partner not yet due; a carry-forward never opens a gap.
- Accessibility: words and icons, positional marks with a key, whole-row
  buttons with full accessible names, phone labels.
- Compatibility: the ids and `in-place-on` are kept; the cloud limitation is
  recorded; the terminal is 80 columns, NO_COLOR and piped.
- Maintainability: one selection function (279's), one root-cause function,
  and one operation for re-pointing.

**Ruled out:**
- Security: nothing is widened, and every override keeps its allowlist,
  actor and reason.
- Privacy: only ids, periods and table names.
- Compliance and retention: no new data class.
- Cost: there is one more schema bump, after 279's, and it costs one
  bootstrap from empty, shipped in the same push as the rest.

**Put to Keith:** nothing new. V4-Q2 was itself an NFR fork (#113, no
self-clearing red) and is answered.

## Questions and readings

**New questions for Keith: none.**

**Readings to confirm at the walk-through.** Each one follows from an answer
of his and is not a new fork:
1. **A person's override that is refused because something moved exits 1,
   not 75** (266 c16). V4-Q3's 75 is for a refusal that the same command gets
   past later. Here the consequences, and so the confirmation key, have
   changed, so the person must look again.
2. **A failed move during the promotion step owes the whole application**
   (267 c17). This extends Q3 = A, "a crash waits". The architect proposed
   returning that supply to the fixed point as not promoting; this is put
   back to him in his v5 review.
3. **Staggered Order B, red branch, gives two tickets rather than one.**
   Clients' failure against Notifications v1 was found before Notifications
   v2 existed, so it is its own root.
4. From v4, still to confirm:
   - N1's single "A";
   - Q5's "no notification" read as no ticket and no still-failing record;
   - "the staging view made precise" (267 d12);
   - case 3a: only the declaring table stays red (the architect agrees).
5. **REQ-PIPE-280's operation name, "carry-forward"**, is for the CLI UX
   reviewer.

**Presentation calls to mention, not ask** (within Keith's decisions):
- A grid column with no result in any row is hidden (272 c6).
- The date control reads "In the warehouse on" (277; v4 open question A).
- A held table's could-not-run rows show "No data" (v4 open question B).
- The card line for a joined set reads "(received 9:00am and 9:05am ...)"
  (275 c4), for the dashboard UX reviewer.

**Still Keith's, carried from v4 unanswered.** Every reviewer agrees with
each recommendation:
- **C. T18**, a period before a partner's participation starts (271 OQ1).
  Recommended: out of the run's scope, recorded in `left_out` with a reason,
  which is the architect's mechanism.
- **D. Where the supplier guidance lives** (274 OQ1). Recommended: a new
  `docs/supplier-guidance.md`.
- **E. REQ-PIPE-210's two follow-ups to F6.** Recommended: A for both. The
  CLI review notes that the page's and the terminal's counts disagree unless
  E2 is A.

**For the v5 reviewers:**
- Architect: reading 2 above; 267 c6's exception; JOINABLE's third clause
  (results "from a run filed to the period it is now filed to") against
  re-file and un-supersede paths.
- Dashboard UX: the joined forms (275 c1, c4; 204 c2; 272 c13), and 272 c21's
  waiting-state wording.
- CLI UX: 280's name and consequences, 276 c12's group wording, and 276 c17's
  hint.

## Draft entry for plans/running-thoughts.md #95 (for a human to apply)

> Append to #95: "**v5, 2026-10-23**: Keith's answers on the v4 reviews (V4-Q1 = A, V4-Q2 = A, V4-Q3 = A) and the three v4 reviews are folded into `docs/drafts/unjudged-cross-table/summary-v5.md` and `requirements-draft-v5.yaml` (unsigned). #95 now stands on REQ-PIPE-279 for what each check read, the one selection function, `run_seq` and points. The changes:
> - a clean table promotes alone when only its reader fails (S2 strict re-cast as its mirror, S10 re-ordered);
> - the gate counts per check, joins only joinable supplies, takes one lock per period and promotes in one transaction;
> - one new requirement, REQ-PIPE-280, carries a newer supply forward in one decision;
> - a refusal while a delivery is being checked exits 75;
> - the dashboard grid gains a third bucket, worst-of marks, phone labels, a 'waiting for the rest of its delivery' state and hides an empty column;
> - the terminal gets the CLI review's S1 to S13.
>
> Next: the architect and both UX reviewers on v5, then Keith's S1 and staggered walk-throughs. There is no new question. C, D and E are still open from v4."

## Validation

- `uv run mothman dashboard validate-requirements --draft
  docs/drafts/unjudged-cross-table/requirements-draft-v5.yaml`, run alone,
  reports 77 errors. All 77 are `dependencies entry ... does not match any
  real requirement id in this file`, which is expected for a draft. There are
  no others.
- I merged `requirements.yaml` with:
  - the close-out draft's REQ-GEN-206 and REQ-PIPE-211;
  - REQ-PIPE-279's current draft;
  - all fifteen v5 requirements. v5's REQ-DASH-204 and REQ-PIPE-210 replace
    the close-out versions.

  The result is in the scratchpad at
  `/tmp/claude-0/-home-user-data-poc/5735d9c2-23bf-590b-afe1-e67b136c7e21/scratchpad/v5/merged95v5.yaml`.
  The validator reports **"requirements validation OK - 266 requirements, zero
  errors."**
- `yaml.safe_load` reads the v5 file back with all fifteen requirements.
  Every acceptance criterion, NFR, decision and open question is a string,
  none carries `signed_off`, and every requirement carries `decisions:`.
