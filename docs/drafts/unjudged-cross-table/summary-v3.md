# Cross-table checks that could not run, or are judged against the wrong partner (#95): draft v3, for sign-off

Re-scoped by delivery-scoper on 2026-10-21 (Perth) on the shape Keith settled
2026-10-20/21 (`summary.md`, from "Shape REOPENED" to the end). This is a
**proposal**. Nothing in it is in `requirements.yaml` and nothing is signed.
The requirements are in `requirements-draft-v3.yaml` next to this file.
`summary.md`, `summary-v2.md`, `requirements-draft.yaml` (v2) and the three v2
reviews are left as they are, as history.

## The shape, in one paragraph

Red only. A cross-table check that cannot read a partner is red, whatever the
reason, and holds like any red; an absent partner is never "empty". Files that
arrive together (one receipt instant) are gated together once every one of
them is checked. A file is promoted only on cross-table verdicts about what
the warehouse will hold once the gate's promotions are made; when a
package-mate is not promoted, the others' cross-table checks are re-run
against what is in place, cascading until nothing changes. Other tables are
re-checked only on promotion. A promoted supply's status counts a cross-table
verdict only when every supply it read is the one now in place. A quarter is
opened, and its inheritances made, at its first filing. The dashboard's
"Awaiting a decision" line adds the in-place supply's status.

**Terminology.** Keith says "held" for a file the gate does not promote.
The register already uses "held" for something narrower: a supply that no
slot could be claimed for (REQ-PIPE-078, `held_blast_radius`, and the
queue's "Held - no period yet"). The CLI review of the shape found that the
gate's own word in the terminal is already **held back** (`decision_words`,
`_gate_words`). So the requirements say **not promoting** inside the
gate's algorithm and **held back** for the outcome a person sees, and keep
"held" for REQ-PIPE-078's meaning. Worth Keith's nod at sign-off.

**Three reviews of the shape existed before this draft** (2026-10-21, in
this folder: `review-architect-v3-shape.md`, `review-dashboard-ux-v3-shape.md`
and `review-cli-ux-v3-shape.md`). They were not named in my brief. I found
them, read them, and folded them in; the carry-over check below lists every
finding. Two of them changed the draft materially:
- The architect's B3 algorithm replaces my first cascade, which held a
  package-mate back at once even when it was red only against another
  package-mate's v2.
- The architect's B1 (the cloud ingest path has no packages at all) is new
  question Q9.

## The requirements

Ids continue the register (highest today is REQ-PIPE-265; 256 and 261 are
spent on withdrawn drafts).

| Id | MoSCoW | What it covers | Provisional on |
|---|---|---|---|
| REQ-PIPE-266 | must | A package (shared receipt instant) is gated together, after every file is checked. One knock-on per package. A part-checked package is finished on the next pass, never gated in part. No checkpoint between two siblings. | Q3 (c12, c13); Q9 (c6) |
| REQ-PIPE-267 | must | The gate's view: a verdict counts only if everything it read is in place or promoting in the same gate. A not-promoting package-mate triggers re-checks against what is in place, cascading to a fixed point. Carried verdicts stop counting. Refusal wording names the cause. | Q2 (c11) |
| REQ-PIPE-268 | must | A file waiting only for its partner is promoted together with the partner's later file. It is re-gated, never re-checked. Without this, Keith's S3 deadlocks (T1). | Q1 (all) |
| REQ-PIPE-269 | must | Warehouse view by supply: an in-place supply counts only verdicts about the supplies in place. Fixes the live `runs_about` flaw in both directions. One function. B1 (the knock-on re-runs a reader that could not read a table). | Q5 (c5) |
| REQ-PIPE-270 | must | Strict: could-not-run is red for every reason, not yet due included. Amends REQ-PIPE-079 c14. | - |
| REQ-PIPE-271 | must | A period is opened, and its inheritances made, at its first filing (S6). | Q4 (c5, c6) |
| REQ-DASH-272 | must | The awaiting line's in-place clause ("... and is green."); wording for a row re-checked against what is in place; "read against" on every row; the page shows the warehouse view by REQ-PIPE-269. | Q11 (rollups), Q12 (c6) |
| REQ-GEN-273 | must | Target agreement compares a supply with its own verdict, not a red caused by its partner's refusal. Without it, the bootstrap fails. | Q7 (all) |
| REQ-DOCS-274 | should | Supplier guidance: send a delivery as one package. | where it lives (OQ) |

Suggested build order, following the v3-shape architect review:
1. 269 (selection by supply), which fixes the live `runs_about` issue on its
   own.
2. 271 (open at filing).
3. 270 + 266 + 267 + 268 + 273 **in one push, with one bootstrap after
   them**. 270 alone makes every early staggered file red, and without 268
   that deadlocks; without 273 the first bootstrap fails target agreement.
   The bootstrap before this push is the "before" capture (REQ-TEST-239).
4. 272.
5. 274.

The architect should confirm this order against the draft.

## What happens to the v2 draft and the close-out batch

**Withdrawn, all six v2 requirements** (REQ-QAC-212, REQ-PIPE-213, 214, 215,
REQ-DASH-216, REQ-PIPE-217). The Incomplete status was rejected. What
survives from them is listed in the carry-over check below.

**REQ-DASH-204, REQ-PIPE-210 and REQ-PIPE-211 go back to their close-out
versions** (`docs/drafts/calendar-close-out/requirements-draft.yaml`). Those
were written for a red that holds, which is the v3 shape. v2's Incomplete
re-folds of all three are withdrawn. The close-out versions need these edits:

- **REQ-DASH-204** (the line at the top of a reader's page):
  - **c1:** drop "and SHALL NOT show a line for a table that is merely not yet
    due". Under REQ-PIPE-270 that case is red too. Add "not promoted with its
    package" to the list of causes.
  - **c15:** replace the five per-cause wordings with one, **"No promoted
    `<dataset>` for `<period>`"**. That was Keith's v2 Q10 answer, and its
    reason (the cause is read on that dataset's page, and the recorded cause
    can be out of date) does not depend on the shape. **c10:** drop the
    per-table reason codes, which only the per-cause wording needed. Keep the
    structured table fields and held_tables, read through one function (v1
    architect H4).
  - **c7:** add "except criterion 7's line" to c15 (v2 dashboard UX 4: c15
    contradicted c7). The wording for c7 is the v2 UX review's: "**`<dataset>`'s
    `<period>` supply was promoted on `<date>`.** `<n>` of this dataset's
    checks have not been re-run against it yet; they run by themselves, and
    this line goes once they have."
  - **c2:** use the v2 UX review's wording: "**No promoted `<dataset>` for
    `<period>`.** `<n>` of this dataset's checks need it, so they could not
    run. That is not a fault in this dataset's own data, and nothing needs
    doing here: they run again by themselves once there is a `<period>`
    `<dataset>` supply to check them against." Drop "nothing needs doing here"
    where the dataset has a red of its own.
  - **c1:** use the `.notice-exhausted` structure with a modifier class, not an
    inline style. Name its place in the blocked branch (v2 UX 4).
  - **The open question carries over**, now sharper: not yet due and overdue
    have no notice on the missing table's own page for c17's "Affects" to end
    (v2 UX 6). This is a check at build, brought back to Keith if it is true.
  - **After a package-mate is turned down (Q10, recommended A):** word the
    line from the decision log as it stands - "The `<dataset>` file received
    with it was turned down; this supply now needs its own decision" - and
    never name an action that can no longer happen (dashboard UX review of
    the shape, S8).
  - **Does not apply to S1's red branch.** That red is a real failing verdict
    against Notifications v1, not a check that could not run. Its explanation
    is REQ-DASH-272 c4's row sentence.
- **REQ-PIPE-210** (the terminal queue): keep the close-out version. Its
  readers (red only because of another table) wait again under the strict
  rule, so "nothing needs deciding on this supply, listed beneath its cause"
  is needed once more. Add "not promoted with its package" as a cause, so that
  S2's Clients v2 is listed beneath Notifications v2. **Whether to keep it at
  all is Q8.** Its F6 open question 1 (a reader with nothing to sit beneath)
  is still open. Recommended: answer it A, "not counted", for F6's reason.
- **REQ-PIPE-211** (re-check after a contested pair is settled): keep the
  close-out version, a must (Keith, Q9 = B, 2026-10-20, which is not about
  the shape). Two edits: its B1 dependency moves from v2's REQ-PIPE-215 to
  REQ-PIPE-269 c7; and c2's "for the reason that now applies" now reads red
  under REQ-PIPE-270. TS-81 ("reject both", REQ-GEN-206) then expects the
  readers **red, waiting**, until a cp_clients is promoted. That is not "red
  for good": the knock-on clears them, and REQ-PIPE-211 makes sure their
  recorded reason stops saying "contested". Carry the v2 CLI review's item 5
  (c8 at scale: one line per resulting status, up to eight readers then "and
  `<n>` more"; reuse `_run_owed`'s wait line).
- **REQ-GEN-206 c18** (TS-81 "b"): "no reader's cross-table result reads
  contested" stands. Add that each reader reads red, with REQ-DASH-204's
  line "No promoted Client Register for `<period>`".

## Every case, today and under v3

"Today" is what the code does now, as checked on 2026-10-20 and 2026-10-21:
`arrival_lifecycle.process` gates each arrival straight after its own run;
`supply_status.runs_about` counts every run that read a supply;
`unrunnable.results_for` records not yet due as `nodata`; and the period
opens at its first promotion. Tests are named in each requirement and are
written first, seen to fail.

### Keith's worked scenarios

| # | Scenario | Today | Under v3 | Where |
|---|---|---|---|---|
| S1 | 2024-Q3 holds Clients v1 and Notifications v1 (green). A zip brings Clients v2 and Notifications v2. Clients v2's run evaluates Client reference against v2+v2: green, and carried to Notifications v2. Notifications v2 is red on blank values of its own. | Clients v2 is gated straight after its own run and **promoted before Notifications v2 is checked**. The warehouse then holds Clients v2 + Notifications v1, and that pairing was never checked. | Both are checked, then gated together. Notifications v2 is not promoting. Client reference is re-run for Clients v2 against Notifications v1. **Green:** Clients v2 is promoted, and the warehouse holds v2 + v1, checked. **Red** (v2 dropped 12 clients v1 points at): Clients v2 is refused as an ordinary red, and its refusal and row say it was re-checked against the Notifications in place because the one received with it was not promoted. | 266 c7-c8; 267 c3-c5, c13; 272 c4 |
| S1 step 4 | Later, Notifications v2 is promoted by a person, or rejected. | n/a | **Promoted:** the knock-on re-checks Clients' readers against v2 (red branch: Clients v2 is re-gated and may promote). **Rejected:** nothing changes, because no verdict any gate relied on read Notifications v2. | 267 S1-step-4 tests (characterization) |
| S2 | First-time zip, nothing promoted for the quarter. Both green. | First gated promotes on its verdict; the second follows. | Both are promoted together. The one verdict counts toward both, with no re-run. One knock-on, which re-runs nothing. | 266 c10; 269 c4 and S2 test |
| S2 strict | Same, but Notifications v2 is red. | Clients v2 is promoted on its verdict against Notifications v2, which is never promoted (half-and-half). | Clients v2 is re-checked against "no Notifications": could not run, which is red. Clients v2 is refused (strict). Promoting Notifications v2 later clears it through the knock-on. | 267 c4, c7; 270 |
| S2b | After S2 strict, a clean Notifications v3 arrives alone the next day. Its run passes Client reference against the waiting Clients v2. | v3 is promoted on that verdict, then the knock-on promotes Clients v2. | **Q1.** Recommended: v3 and Clients v2 are promoted together, and Clients v2 is re-gated, not re-checked. Strict 267 alone would deadlock this (T1). | 268 |
| S3 | Staggered: Notifications arrives at 08:40, Clients 20 minutes later. | Notifications records not yet due as `nodata`, reads green and is **promoted** (decision 103's false green). | Notifications is red and refused (an accepted flicker). Clients arrives, and its run passes against the waiting Notifications. **Q1**, recommended: both are promoted together at Clients' gate. Keith's own words, "Clients promotes, then knock-on", are Q1's option B. | 270; 268 |
| S3b | Staggered, but the earlier file waits for its own red. Clients v2 is red on its own checks. Notifications v2 arrives alone, and its verdict is against the staged Clients v2. | Notifications v2 is promoted on a verdict about a Clients that never got in. | **Q2.** Recommended: Notifications v2 is re-checked against the Clients in place (v1, or none) before its gate. | 267 c14 |
| S4 | Clients is promoted. A new Notifications file arrives pointing at missing clients, its Client reference red. It is refused. | `runs_about` counts that run toward the promoted Clients, so **Clients reads red**. Keith's 2026-10-20 case is the same in the other direction. | Clients stays green, because the run read a Notifications supply that is not in place. Fixed both ways. | 269 c1-c2, S4 tests; 272 |
| S5 | A package with mutual readers: Notifications ↔ Investigations (Escalation completeness; Notification reference), plus Clients. Investigations v2 is red. | Each is gated after its own run, in receipt order. | Notifications is re-run against Investigations v1. If that fails, Notifications is not promoting, so Clients is re-run against Notifications v1. The outcome is the same in any order, and the cascade stops when nothing changes. | 267 c5-c6, S5 test |
| S6 | Owe-nothing quarter: Case Workers sits out 2024-Q4. The other five arrive green. | The period opens only at a first promotion. Under the strict rule, every reader of Case Workers is red for want of it, so nothing promotes (deadlock). | Q4 opens at the package's filing. Case Workers is inherited before any run, the readers pass against it, and all five promote. | 271 |

### v2's cases that still apply

| v2 # | Case | Under v3 | Where |
|---|---|---|---|
| 1 | Dependency not yet due | Red, refused (was a false green) | 270 c1 |
| 2 | ...then it goes overdue | Still red, with no re-run; only the recorded reason is out of date, and REQ-DASH-204 never shows the reason as current | 270 c4 |
| 3 | ...it never arrives | Red, waiting, until it is promoted, inherited or substituted, or a person promotes the reader | 270 c6 |
| 3a | Its slot is accepted as "not supplied" | Stays red, and a person can promote it (v2 Q5 = A carried by analogy; **confirm at sign-off**) | 270 |
| 4 | Dependency overdue, no fault of the reader's own | Red, waiting, as today. The reason code stays | 270 |
| 5 | Dependency staged awaiting a decision | Re-checked against what is in place, if in the same package or (Q2) a staggered arrival | 267 c4, c14 |
| 6 | Dependency contested | A reader reads the promoted version (REQ-PIPE-079 c12), or none, which is red. Unchanged | - |
| 7, 8 | Could not be loaded; held | That supply is not promoting, so its package-mates are re-checked against what is in place | 267 c3 |
| 9 | Dependency arrives later and is red | Its run's verdict about the waiting reader is a staging view against a waiting partner. It is shown, labelled (272 c5), and never relied on by a gate (267 c1) | 267 c1; 272 c5 |
| 10 | A staged dependency the reader read is rejected | **Moot.** No gate relies on a verdict about a supply that is not promoting with it (267 c1, 268). Only a waiting reader's display is out of date, and that is labelled | - |
| 11 | A knock-on that leaves the period holding nothing (B1) | The reader is re-run, not only re-gated | 269 c7 |
| 12 | Siblings re-filed together | Still the sighting. A re-file batch is not a package (REQ-PIPE-265 c1). See T14 | - |
| 13 | Superseded by a file that cannot be loaded | Cannot happen (v2 architect, supersession.py:171-179) | - |
| 14, 15 | The other side of the check; the missing table's own status | By supply: a record counts toward the supplies it read and nothing else | 269 c4 |
| 16 | REQ-PIPE-265's 312 staggered pairs | S3 | 268, 270 |
| 17 | Amber under "hold" | Not promoting at the gate, so its package-mates are re-checked against what is in place | 267 c3 |
| R2 | "Reject both" vs. a table that never arrived | Both red and waiting. Whether either writes a "still failing" record or a ticket is Q6 | Q6 |

## Amendments to signed requirements: exact wording for Keith's approval

`<date>` is filled in by whoever builds it. Only the changed criterion is
given. Every one of these is a proposal.

**REQ-PIPE-081 c1** (signed 2026-09-26), by REQ-DASH-272.
- OLD: "...WHERE the newest is awaiting a decision while an older one is promoted, THE SYSTEM SHALL also name the promoted one as what is in place. THE SYSTEM SHALL NOT answer it with a supply withdrawn at T (criterion 2), however recently it arrived. AMENDED 2026-10-05 ... AMENDED 2026-10-13 ..."
- NEW: replace the second sentence with: "WHERE the newest is awaiting a decision while an older one is promoted, THE SYSTEM SHALL also name the promoted one as what is in place, and SHALL give that supply's status as in place at T, counted by REQ-PIPE-269." Then append: "AMENDED `<date>` by REQ-DASH-272 (Keith, 2026-10-21, option 2): a reader of a page whose newest supply waits must also see whether the warehouse is still green." The rest is unchanged.

**REQ-PIPE-105 c1** (signed 2026-09-28), by REQ-PIPE-266.
- OLD: "THE SYSTEM SHALL treat every arriving file as its own arrival, and SHALL process it without waiting for any other file."
- NEW: "THE SYSTEM SHALL treat every arriving file as its own arrival, and SHALL file and check it without waiting for any other file; WHERE several arrivals share one receipt instant, THE SYSTEM SHALL gate them together once all of them are checked (REQ-PIPE-266), which waits on their checks and never on another arrival. AMENDED `<date>` by REQ-PIPE-266." (c2, "SHALL NOT hold a supply pending the arrival of another", is unchanged and still true.)

**REQ-PIPE-121 c9** (signed 2026-10-04), by REQ-PIPE-266.
- OLD: "THE SYSTEM SHALL run one re-evaluation per decision, over every table that decision moved into or out of a period schema, after the decision commits, and SHALL NOT run one per table moved."
- NEW: "THE SYSTEM SHALL run one re-evaluation per decision - or, where one gate application (REQ-PIPE-267 criterion 2) makes several promotions, one for all of them - over every table moved into or out of a period schema, after the last of them commits, and SHALL NOT run one per table moved or per promotion of one gate application. AMENDED `<date>` by REQ-PIPE-266 criterion 10."

**REQ-PIPE-121 NFR 4**, by REQ-PIPE-269.
- OLD: "Cheapest correct path first: a waiting supply's status is recomputed from its latest result per check, and a check's tools re-run only where its latest recorded result read a different supply than the one the period now holds. Recomputing a status from latest results is one function, shared with REQ-DASH-126."
- NEW: "Cheapest correct path first: a supply's status is recomputed from its latest COUNTED result per check (REQ-PIPE-269), and a check's tools re-run only where that result read a different supply than the one the period now holds, read nothing for it, or could not be evaluated for want of a table (REQ-PIPE-269 criterion 7). Recomputing a status from counted results is one function, shared with REQ-DASH-126. AMENDED `<date>` by REQ-PIPE-269."

**REQ-PIPE-121 decision 11, "A FILE LANDING IN STAGING STAYS OUTSIDE THIS MECHANISM"** - only if Q1 = A (REQ-PIPE-268).
- APPEND: "REFINED `<date>` by REQ-PIPE-268 (#95 Q1): a landing file still re-checks no other table. But a waiting supply of another table, clean on its own and waiting only for the arriving table, is RE-GATED - never re-checked - with the arrival, on the arrival's own verdict, so that the two promote together."

**REQ-PIPE-075 c2** (signed 2026-09-26), by REQ-PIPE-267.
- OLD: "THE SYSTEM SHALL take the status this gate reads from EVERY check that contributes to that dataset's status - its own table-level and column-level checks, the cross-table checks it participates in whether or not it is the dataset they are filed under, and any other scope that folds into the dataset's status - and SHALL NOT gate on a subset of them."
- NEW: append: "A cross-table check is read by its result about the warehouse as it will stand once this gate's promotions are made (REQ-PIPE-267 criterion 1), re-evaluated where the result it has read a supply that will not be in place. AMENDED `<date>` by REQ-PIPE-267."

**REQ-QAC-037 c7** (signed 2026-09-23), by REQ-PIPE-269.
- OLD: "THE SYSTEM SHALL fold a cross-table check's verdict into the status of every dataset it reads, whether that check failed or could not run, and SHALL NOT leave a participating dataset reading green while a check that reads it reads red."
- NEW: "THE SYSTEM SHALL fold a cross-table check's verdict into the status of every supply its run read, whether that check failed or could not run - for a supply in place, only a verdict whose every read supply is the one in place (REQ-PIPE-269) - and SHALL NOT leave a participating supply reading green while a check counted toward it reads red. AMENDED `<date>` by REQ-PIPE-269 (Keith, 2026-10-21: judged by supply)."

**REQ-PIPE-079 c14** (signed 2026-09-26), by REQ-PIPE-270.
- OLD: "WHERE a table a check reads has no promoted supply for the period and that period's slot for it is neither past due nor closed, THE SYSTEM SHALL NOT report the check red, and SHALL say the table has not been supplied for this period yet and is not yet overdue."
- NEW: "WHERE a table a check reads has no supply the run may read for the period and that period's slot for it is neither past due nor closed, THE SYSTEM SHALL report the check red, not evaluated (REQ-PIPE-270), and SHALL say the table has not been supplied for this period yet and is not yet overdue. AMENDED `<date>` by REQ-PIPE-270 (Keith, 2026-10-21, strict): not yet due was the false green."
- **Decision 23**, append: "SUPERSEDED IN PART `<date>` by REQ-PIPE-270: `awaiting-supply` keeps its own code and wording, but is red. Its reason ('every new dataset starts life red ... which is how people learn to ignore a signal') is answered by supplier guidance (REQ-DOCS-274) and Keith's acceptance of the staggered-file flicker, 2026-10-20."

**REQ-PIPE-115 c20** (signed 2026-10-04), by REQ-PIPE-270.
- OLD: "...asserts at qa.check_result that each records its own reason code - nodata for not yet due, red for the other two - rather than the catch-all."
- NEW: "...asserts at qa.check_result that each records its own reason code, all three red, rather than the catch-all. AMENDED `<date>` by REQ-PIPE-270: not yet due read nodata."

**REQ-PIPE-098 c4** (signed 2026-09-28), by REQ-PIPE-271.
- OLD: "THE SYSTEM SHALL create a period's schema either on the first promotion into it or on an explicit instruction to open it, and SHALL NOT require an arrival before a period can exist - using the SAME creation mechanism for both, so that a period opened by instruction is indistinguishable from one created by a first promotion."
- NEW: "THE SYSTEM SHALL create a period's schema on the first FILING to it (REQ-PIPE-271), or on an explicit instruction to open it, whichever comes first, and SHALL NOT require an arrival before a period can exist - using the SAME creation mechanism for both, so that a period opened by instruction is indistinguishable from one opened by a filing. AMENDED `<date>` by REQ-PIPE-271 (Keith, 2026-10-20: 'inherit when the quarter is filed, not when it is first promoted')." The criterion's unmet entry (the explicit instruction) stays, unowned.

**REQ-PIPE-262 c12** (signed 2026-10-19), by REQ-PIPE-271. The wording is unchanged, but **its pinned supplies may move**: opening at filing can change which supply is "newest promoted before the instant its period was opened". If the bootstrap moves any, the new values come to Keith for approval. Nothing is quietly re-pinned.

**REQ-DASH-264 c1** (signed 2026-10-19), by REQ-PIPE-269.
- OLD: "THE SYSTEM SHALL show on a dataset page, for each check, the newest result recorded for that dataset on or before the in-place-on date, whichever table's run recorded it - the result the promotion gate reads - so a re-check of one table that re-runs another's cross-table checks changes the other table's page from the day it was recorded."
- NEW: "THE SYSTEM SHALL show on a dataset page, for each check, the newest result counted toward the supply the page is about on or before the in-place-on date (REQ-PIPE-269), whichever table's run recorded it, so a re-check of one table that re-runs another's cross-table checks changes the other table's page from the day it was recorded, and a run that read a supply not in place never changes an in-place supply's page. AMENDED `<date>` by REQ-PIPE-269." (c11 and c12 then count only counted results, with no wording change. **c6** still reads "cp-clients' cross-table rows reading red" and is unchanged.)

**REQ-GEN-186 c3** (signed 2026-10-11), by REQ-GEN-273, **only if Q7 = A**.
- OLD: "WHEN a replay of the synthetic history finishes, THE SYSTEM SHALL compare every targeted supply's verdict as the promotion gate reads it - injected and ordinary amber alike, in both collections - with its target, and IF they differ, THEN THE SYSTEM SHALL fail the bootstrap naming the scenario or period and the checks responsible."
- NEW: "...compare every targeted supply's verdict as the promotion gate reads it, leaving out cross-table checks that could not read a partner and re-evaluations made because a package-mate was not promoted (REQ-GEN-273), ... with its target, and IF they differ, THEN THE SYSTEM SHALL fail the bootstrap ... AMENDED `<date>` by REQ-GEN-273."

**REQ-TEST-159 c1** (signed 2026-10-06), by REQ-PIPE-266.
- OLD: "WHEN a person replays one collection asking for a checkpoint before arrival N, THE SYSTEM SHALL save a copy of the database as it stood once arrival N-1 was fully processed, recording with it the collection, N, and the inputs REQ-TEST-160 compares."
- NEW: append: "WHERE arrival N is not the first of its package (REQ-PIPE-266), THE SYSTEM SHALL refuse, naming the package's first arrival. AMENDED `<date>` by REQ-PIPE-266 criterion 14."

**No amendment needed** (the reason is recorded in the requirement):
- **REQ-PIPE-265**: it stands (Keith). A carried verdict stops counting through REQ-PIPE-267 c8, not through a change to 265.
- **REQ-PIPE-105 c2, c5, c13**: c2 is still true; c5's overlay is unchanged, and the re-check overlay is a build question (267 OQ2); c13 already says "red".
- **REQ-PIPE-078 c10**, **REQ-PIPE-079 c4, c15, c16**: already red.
- **REQ-PIPE-121 c1, c3, c6, c11, c12**: c3's re-gate becomes a gate application (267 c2), which 267's own wording carries. Whether c12's "still failing" record is written for a supply red only because of a partner is Q6.
- **REQ-DASH-126**: red promoted already covers a person's override.
- **REQ-PIPE-083**: unchanged unless Q6 says otherwise.
- **REQ-GEN-199** quotes (TS-75, TS-76, TS-77): these move with any bootstrap that changes reasons, and are re-captured under REQ-PIPE-270. Criterion 9's wording waits for the first bootstrap (it is also amended by REQ-GEN-206 c15).

## Carry-over check: every decision and where it landed

**summary.md, from "Shape REOPENED" to the end (2026-10-20/21)**

| Decision or fact | Where in v3 |
|---|---|
| Red "feels right"; no new status vocabulary, and no red that follows different rules | 267 d4, 270 d3 |
| Goal: "the promoted view reflects what's actually in the warehouse across rechecks" | 269 (source, d1) |
| Re-checks of OTHER tables come from promotion, never from an arrival | 267 d6; 268 d2 (re-gate is not re-check; Q1) |
| Fact: one cross-table check asks one one-way question, is declared on one dataset, and is evaluated in either table's run | Every scenario; 269 c4 |
| Fact: a check is evaluated in the run of either table (base_scope_of_run) and counts against every table it reads | 269 c4 (by supply now) |
| LIVE ISSUE: runs_about counts a refused partner's run toward a promoted supply | 269 c1-c2, d2, S4 tests |
| Correction: no deadlock in the simple staggered case under red that holds | **Overturned by T1.** Under the no-half-and-half rule (267 c1) the simple staggered case *does* deadlock unless 268 exists. Recorded in 268 d1 |
| (a) A waiting reader is not re-gated when its partner is staged but refused, "which Keith says is right" | 267 c1 and c11 (Q2) |
| (b) Owe-nothing quarters deadlock; inherit on filing | 271 |
| Inheriting on filing ties to REQ-PIPE-098 c4's command, which is unmet and unowned ("Leave until needed") | 271 d2; the command is not built here |
| Principle 1, no half-and-half; principle 2, no flickering reds (#113) | 266 NFR 1-2; 267 c1, d2, NFR 1-3 |
| A package is gated together after every file is checked; a zip stands in for it (#114) | 266 c1, c7-c8, d1-d2 |
| A refused file means the others are re-checked against the warehouse partner; worked example S1 | 267 c3-c4, S1 tests |
| Warehouse view by supply | 269 |
| Inherit on filing | 271 |
| Staggered files flicker, accepted; supplier guidance | 266 d4; 270 NFR 2; REQ-DOCS-274 |
| The awaiting page shows the staging verdict; how is the warehouse seen? | 272 |
| Rejecting staged reds returns the page to the warehouse verdict (already true) | 272 c11, d3 |
| Option 2, the in-place clause | 272 c1, d1 |
| Re-checks cascade until nothing changes | 267 c5-c6, d8 |
| First-time zip with a refused partner: Clients is re-checked against "no Notifications", red, refused; promoting the partner clears it | 267 c7, S2 strict test |
| A person promoting by hand shows as red promoted | 270 c6; 267 c15 (the warning first) |
| STRICT; "not supplied = empty" rejected | 267 d3; 270 d1 |
| REQ-PIPE-265 stands; a carried verdict stops counting once a file it read is refused | 267 c8, d5 |
| Keith wants tensions, gaps and deadlocks | "Tensions" below |

**Earlier summary.md answers (2026-10-14 and 2026-10-20 morning), now that the shape changed**

| Answer | Fate under v3 |
|---|---|
| Q1 shape 1 (Incomplete) | Reversed by Keith, 2026-10-20/21. Recorded as rejected in 267 d4 and 270 d3 |
| Q2 = B (Incomplete promotes itself) | Not needed, because red holds. Recorded with Q1 |
| Q3 = A (re-check only when something moves, never on the clock) | Stands. No clock trigger anywhere in v3. "Something moves" is now promotion, a gate application, or (Q1) a re-gate |
| Q4 = A (a staged dependency counts as checked) | **Refined, not reversed.** It counts for the staging view (269 c3). It does not count at a gate unless that dependency is promoting with the supply (267 c1). Keith's S1 step 3 is the evidence |
| Q5 = A (stays Incomplete when "not supplied") | Carried by analogy as "stays red" (case 3a). Confirm at sign-off |
| Q6 = A (no still-failing record for Incomplete-only) | Re-asked as Q6 for a red caused only by a partner |
| Q7 = A (no ticket for Incomplete alone) | Re-asked as Q6 (same question, red now) |
| Q8 = A (the other side of a check counts too) | Carried as "by supply" (269 c4) |
| Q9 = B (REQ-PIPE-211 a must, as drafted) | Stands. REQ-PIPE-211 returns to its close-out version |
| Q10 = A (one wording, "No promoted `<dataset>` for `<period>`") | Stands. Folded into REQ-DASH-204's edits |
| Q11-Q13 (v2: amber hold, REQ-PIPE-210, trials) | Q11: not needed, because there is no status above amber; amber under hold is "not promoting" (case 17). Q12 becomes Q8. Q13: trials unchanged (270 c7) |

**review-architect.md (v1, 2026-10-14)**

| Finding | Where in v3 |
|---|---|
| B1 deadlock, and the A1 fix (re-gate on a staged arrival) | The owe-nothing half is 271. The re-gate half comes back in narrowed form as 268 (re-gate only, never re-check; Q1). A1 as a re-check stays rejected (267 d6) |
| B2 AWAITING_DECISION for every early arrival; A4 slot state | **Returns, and accepted.** Under red that holds, an early staggered arrival does wait for a decision. Keith accepted the flicker. Its ticket and still-failing noise is Q6 |
| H1 Q4 vs case 9 | Case 9 under v3 (case table) |
| H2 inherited and substituted count as readable; A3 retry a refused inheritance | 270 c5. A3 comes back as the stale-inheritance question, Q4 |
| H3 record at the writers | 270 c2, d4 |
| H4 one predicate | REQ-DASH-204's edits (structured fields, one function); 269 c6 for "which results count" |
| H5 test-first claims | Every v3 test is new and names what it fails on. B1's injection is in 269 |
| H6, X2 (after-replay reads the gate) | 273 |
| M1 structural, not substring | Not needed, because there is no new status value |
| M2 REQ-GEN-199 quotes and the pin | "No amendment needed" list (re-capture) |
| M3 one withheld record | Not needed, because nothing new is withheld; refusals are ordinary |
| M4 REQ-GEN-203's dependency on 211 | Stands; 211 is kept |
| M5 210's "not counted" | Q8 and REQ-PIPE-210's F6 open question |
| M6 superseded "not a new status" decisions | They stand again (270 d6) |
| L1 renumber both orderings | Not needed, because there is no new status |

**review-architect-v2.md (2026-10-20)**

| Finding | Where in v3 |
|---|---|
| X1 four status rankings | Not needed, because no new status. Its lesson (one function) is 269 c6 and NFR |
| X2 target agreement reads status_of(for_gate) | 273 (Q7) |
| Answer 1: no deadlock under self-promotion; 121's staging rule can stay | Self-promotion is gone, so deadlocks return: T1 (staggered) and S6 (271). 121's staging rule stays except for 268's re-gate (Q1) |
| Answer 2: re-runs use the arrival overlay; staged wins | 267 OQ2: the re-check needs an overlay that leaves out a not-promoting supply |
| Answer 3: case 10 fails first; case 11 needs an injection; case 13 cannot be built | Case 10 moot (case table); case 11 is 269's B1 test with the injection; case 13 dropped |
| Answer 4: 074, 130 and GEN-186 | 130: 269 c6 (promoted status reads the one function). GEN-186: 273. 074: not needed, because no new promoted_status value |
| Answer 5: retrying a refused inheritance is a follow-up | Q4 |
| Answer 6: the trigger worded by effect ("a decision takes a staged supply out of what the period offers") | Not needed, because no gate relies on a staged supply that is not promoting with it (267 c1, 268), so taking one away changes no verdict that matters. Only a waiting reader's display, which is labelled (272 c5) |
| Answer 7: re-filed siblings | T14 |
| Answer 8: land in one push | Build order above (266+267+268+270+273 together) |
| Lesser: keep the unreadable-tables predicate separate from carried.not_evaluated_reason; the all-not-evaluated edge case | For REQ-DASH-204's one function, at build. The edge case is not needed, because could-not-run is red, never "no active checks" |
| For the critic: one ranking, one status function, one predicate, the trigger as a before/after change in apply_decision, docstrings naming the failing line, no "not green or amber" fallbacks | One function: 269 c6. The rest go to the critic unchanged |

**review-dashboard-ux-v2.md**

| Finding | Where in v3 |
|---|---|
| 1 pill one word; 2 colour; 3 counts that drop Incomplete; 8 where "Incomplete promoted" shows | Not needed, because there is no new status |
| 4 REQ-DASH-204 fixes (c15 vs c7, notice style, blocked branch); the --amber token sighting | REQ-DASH-204's edits. The sighting is already logged as plans/road-testing.md #20 (checkpoint 47aead7) |
| 5 wording for c2 and c7 | REQ-DASH-204's edits |
| 6 not yet due and overdue have no notice on the cause's page | REQ-DASH-204's carried open question |
| 7 readers' rows at scale | REQ-DASH-204's NFR (unchanged) |
| 9 navigation (real hrefs keep in-place-on) | REQ-DASH-204 c5 (unchanged) |
| Watch item: cards red at every quarter start | **Sharper now: T8.** Under the strict rule they read red, not Incomplete |

**review-cli-ux-v2.md**

| Finding | Where in v3 |
|---|---|
| 1 four fall-through paths for Incomplete; 2 exit code for "not fully checked" | Not needed, because red is already handled on every surface and `has_failures()` already exits non-zero for red |
| 3 fold 210 into 214 | Q8 (210 is restored or dropped) |
| 4 one vocabulary, dataset ids, state first | 267 c12, c15, d11; 267 c13's wording |
| 5 211 c8 at scale | REQ-PIPE-211's edits |
| 6 narrow terminals, colour | Carried to 267 c15's warning at build (truncate with filing_tui._short in cells) |

**review-architect-v3-shape.md (2026-10-21, before this draft)**

| Finding | Where in v3 |
|---|---|
| B1 the cloud ingest path has no packages (each object its own delivery) | 266 c6; **Q9** |
| B2 the gate runs from four places; checked-but-ungated is a failure today | 266 c2 (one package-gate function), c3 ("checked, waiting for its package", owed) |
| B3 the cascade algorithm (held0 = red on checks reading no other member; members red only against each other's v2s are held together) | 267 c3-c5, replacing my first version |
| B4 a waiting partner from an EARLIER arrival (S4a false green, S4b false red stuck); Q-A group gate | S4a is my S3b (Q2, 267 c14); S4b is fixed by the same re-check; the group gate is Q1 + Q2 together (268, 267 c14). The architect's deadlock cases (staggered first-time; settlement) are why Q1's A is recommended |
| B5 filter first, then newest; no qualifying record reads red; "in place" includes substituted and inherited; red_promoted.py and share_cross_table_results | 269 c1, c5 (Q5 = A agrees), c6 |
| T1 the re-check is a third view: define it as the gate's view | 267 d2, d9 |
| T2 inheritance "once" makes S7 permanent; S9 a period with nothing to inherit; a period before a partner's participation starts; 079 c14 needs amending | 271 c5-c6 (**Q4**); T18 and 271 OQ3; the 079 c14 amendment |
| T3 tickets for package-held members; k identical still-failing shouts | **Q6**; 266 c10 (one owed re-evaluation per package) |
| T4 what counts as held (incl. a slot filled with no replacement, superseded, frozen by the backstop) | 267 c3 |
| T5 one effective_at for the whole package gate | 266 c4 |
| T6 a package ends at its gate; partition a package by period | 266 c1; T14 |
| T7 audit the scenario map; GEN-186 after_replay | 273 c4; **Q7** |
| T8 cost: at most k x rounds, batched per round | 267 c9, NFR |
| Mechanism: from_warehouse on qa.run, overlay drops those tables | 267 c9, OQ2 |
| Lesser: a cycle test; hand-filed path; checkpoints fine once "waiting for its package" exists; awaiting clause in Python | 267 S5 test; 266 c2, c5; 266 c14 is kept anyway (simpler); 272 c9 |
| For the critic (one package-gate function, one record-selection function, B3 in one place, from_warehouse recorded, named failing lines, named held classes) | 266 c2; 269 c6; 267 c3-c5, c9; passed to the critic unchanged |
| Build order (selection first, then inherit, from_warehouse, package gate, display) | Folded into the build order above. The architect puts 269 first because it fixes the live issue alone, which I agree with. 270 must still land with 268 and 273 |

**review-dashboard-ux-v3-shape.md**

| Finding | Where in v3 |
|---|---|
| 1 one view per page; the clause as a small pill; "Read against ..." on every row; supplies named by receipt | 272 c1, c6 (**Q12**) |
| 2 the clause in every combination; `<br>` at phone width | 272 c7 |
| 3 two wordings for a supply held back by its partner (S2 could-not-run; S1 red, no "not a fault" clause); the cause's page says what it holds back | REQ-DASH-204's edits (taken as the proposed wording) and 272 c4 |
| 4 aggregates: one card line per held delivery; the rollup mixing views (Q-A); notify once per delivery | **Q11**; Q6 |
| 5 REQ-DASH-264 c1, c7 and c11 (sameDelivery would count a package re-check as a second run) | 269's 264 c1 amendment; 272 c4, c8 |
| 6 REQ-DASH-204 re-folded to red | REQ-DASH-204's edits |
| 7 navigation | Unchanged (204 c5) |
| S6 name the root and the chain; S8 a sibling turned down; S15 a partner resupplied | REQ-DASH-204's edits, proposed at sign-off; S8 is **Q10** |
| S12 cascade intermediates: hold results back until a package settles | 267 c10 |
| S5 "cleared minutes later" note on the history row, with the guidance | Proposed at sign-off (below); REQ-DOCS-274 holds the guidance |
| S10 inherited partner; S16 a stale staging label; S9 past dates | 272 c6 |
| S13 a widely read table at scale ("Held together: Client Register and 4 more") | REQ-DASH-204's edits |

**review-cli-ux-v3-shape.md**

| Finding | Where in v3 |
|---|---|
| 1 "held back", never "held", for a gate outcome | Terminology above; 267 c12 |
| 2 the cause read from the record, naming the partner supply | 267 c13 (refusal wording); the terminal reads it |
| 3 the outcome panel names the sibling's decision first | 267 c12 |
| 4 at ~30 datasets, one cause line and then outcomes; a cascade prints its final state | 267 c10 (only the settled state counts); REQ-PIPE-211's edits |
| 5 exit codes: EXIT_RED stands; the S7 fall-through (exit 0 after a package re-check's red) | 267 c11 |
| 6 an override's confirmation predicts the knock-on | 267 c15 |
| 7 the queue: own row after its cause, "Deciding cp-notifications settles this one" | **Q8** (REQ-PIPE-210 restored; the review prefers its own row to indenting) |
| S3 rejecting a package-mate leaves the other's reason stale | **Q10** |
| S6 `mothman cp qa --commit` on one file of an unchecked package | 266 c5 |
| S8 a decision landing mid-cascade: the re-confirm key | For the architect (below) |
| S9 a dim supplier-guidance line | REQ-DOCS-274 (could add a terminal line; not drafted) |

**v2 draft decisions not covered above.** 213 d1-d3 (the defect, the false green, the false red) are carried as evidence in 270's source and decisions and in 269 d2. 213 d9 (rejected a time-triggered rewrite) is Q3 = A above. 215 d4 (B1 is general) is 269 c7. 216 d1 (the cause is never shown as current) is carried by REQ-DASH-204's one wording. 217 d1-d2 become Q6.

**Nothing is left only in prose**, except the tensions below, which are put to Keith or to the architect.

## Tensions, gaps and deadlocks found

Keith asked for these explicitly. Each one is either a question below (Q1 to
Q12) or a decision or open question in a requirement, as marked.

- **T1. DEADLOCK: Keith's own S3 cannot happen under rules 1, 5 and 7 as
  stated.** In S3, Clients arrives 20 minutes after Notifications. Clients'
  run checks Client reference against the *waiting* Notifications, which is
  red only because Clients was missing. Under the no-half-and-half rule, a
  gate must not rely on a verdict about a supply that will not be in the
  warehouse, so Clients would be re-checked against "no Notifications": red.
  Both then wait for a person, and so does every staggered pair (312 on the
  bootstrapped history, REQ-PIPE-265's measurement). S2b, a correction
  arriving after a strict refusal, is the same shape. → **Q1**, REQ-PIPE-268.
- **T2. HALF-AND-HALF OUTSIDE A PACKAGE.** Rule 5 re-checks package-mates.
  But a single staggered arrival whose verdict read a partner waiting for
  its own red (S3b) is gated today on that verdict, and promoted beside a
  Clients that never gets in. The register has argued this both ways:
  REQ-PIPE-079 decision 23 (Keith, 2026-09-26) said judging against an
  unaccepted staged supply "would record a green that becomes retroactively
  meaningless", while REQ-PIPE-105 c5 (2026-09-28) made runs read the staged
  version. → **Q2**, REQ-PIPE-267 c14.
- **T3. A PACKAGE THAT NEVER COMPLETES.** One sibling's run crashes, or a
  sibling's dataset is refused by the agreement backstop (checked, never
  gated, until someone fixes the agreement). Gating "after every file is
  checked" then waits indefinitely. A sibling that cannot be loaded is fine:
  that is a recorded outcome, so it counts as not promoting. → **Q3**,
  REQ-PIPE-266 c12-c13.
- **T4. OPENING AT FILING MAKES STALE INHERITANCE LIKELIER.** Inheritance
  happens once, at birth (REQ-PIPE-098 c2, Keith's 2026-09-26 narrowing). A
  period that opens earlier can inherit an older supply when the previous
  period's supply is promoted later. Two things make this wider: periods are
  shared across collections on one calendar, so an Emergency Department
  filing can open a Child Protection quarter; and REQ-PIPE-262 c12's pinned
  inheritances may move. → **Q4**, REQ-PIPE-271 c5-c7.
- **T5. AN IN-PLACE SUPPLY WITH NO VERDICT ABOUT WHAT IS IN PLACE.** This
  happens after a person's promotion whose knock-on is owed or failed (S1
  step 4). Showing the old verdict is half-and-half; showing nothing loses the
  check (a false green). → **Q5**, REQ-PIPE-269 c5.
- **T6. ONE CAUSE, MANY SHOUTS.** Under red that holds, a refused file makes
  its package-mates red (S2 strict) and refused. Under the needs-action
  policy each is AWAITING_DECISION, so each gets a ticket: v1 architect B2
  comes back, and this time it is accepted rather than designed away.
  Separately, REQ-PIPE-121 c12 writes a "still failing, a person decides"
  record when a knock-on re-gates a waiting supply that still fails, even
  where its red is its own and the knock-on changed nothing about it. In S1's
  green branch, Clients v2's promotion would write "left 1 waiting supply
  failing: Notifications" about blank values nobody's promotion affected.
  With notifications on red planned (#113), both multiply. → **Q6**.
- **T7. THE BOOTSTRAP WOULD FAIL TARGET AGREEMENT.** REQ-GEN-186 c3 compares
  each targeted supply with the gate's reading. Under the strict rule, the
  early file of every staggered pair, and every green package-mate of a
  targeted-red file, reads red, so the bootstrap fails even though the
  supply's own data matched its target. → **Q7**, REQ-GEN-273.
- **T8. STRICT NOT-YET-DUE CAN BE DAYS, NOT MINUTES (not a question, for
  #113).** Keith accepted the flicker for files minutes apart. The same
  mechanism makes a file sent days before its partners' due time red for
  days. And at every quarter start, the cards for early files read red, not
  amber or Incomplete (the v2 UX watch item, sharper now). The notification
  design (#113, unscoped) has to decide whether a not-yet-due could-not-run
  red is notified before the partner's due time. The draft does not decide
  it, because it is not this batch's call.
- **T9. REQ-PIPE-105 c1 SAYS "WITHOUT WAITING FOR ANY OTHER FILE".** Gating
  a package together waits on its siblings' checks (not their arrival).
  Amended wording above. c2 ("SHALL NOT hold a supply pending the arrival of
  another") stays true.
- **T10. ONE RE-EVALUATION PER DECISION VS. A PACKAGE PROMOTED WHOLE.** A
  knock-on after the first promotion would re-run the second's readers
  against a half-promoted period. REQ-PIPE-121 c9 is amended (REQ-PIPE-266
  c10).
- **T11. CHECKPOINT, RESUME AND AN INTERRUPTED PASS.** REQ-TEST-159 takes a
  checkpoint after each arrival; the processing pass can stop between two
  siblings. Settled in REQ-PIPE-266 c3, c11 and c14: finish the package, never gate
  part of it, and no checkpoint inside a package. Scripted decisions cannot
  fall between siblings, because they share one instant.
- **T12. TWO STAGING VIEWS IN ONE PACKAGE AFTER A REFUSAL.** In S1's red
  branch, both v2s are waiting. Clients v2's verdict was re-run against v1;
  Notifications v2's still reads Clients v2 (staged, also waiting). Refused
  files are not re-checked, because no gate depends on them. Their pages
  label a verdict against a partner that is also awaiting a decision
  (REQ-DASH-272 c5). If a person promotes one, the knock-on judges it against
  what is in place. Recorded as REQ-PIPE-267 d7, for Keith to see.
- **T13. A PERSON'S OVERRIDE NOW VISIBLY REDDENS OTHER TABLES.** A person
  promoting S1's refused Clients v2 over its red makes the knock-on re-check
  Notifications v1 against it, and Notifications v1 can turn red promoted.
  That is correct (it is the warehouse view), and REQ-PIPE-267 c15 warns
  before the person confirms. Gap for the architect: should the terminal
  refuse a person's decision on a sibling of a package that is not yet gated
  (a live race only)? Recommended: refuse, saying the package is still being
  checked.
- **T14. RE-FILED SIBLINGS ARE NOT A PACKAGE.** REQ-PIPE-265 c1 gives
  re-check runs no siblings. So a person re-filing two supplies into one
  period at one instant has each re-checked and gated alone, each reading the
  other as staged and not promoting. That brings T1's deadlock back unless
  REQ-PIPE-268 also covers a re-check run, or a re-file batch is one gate
  application. For the architect; v2's case-12 sighting is the same family.
- **T15. S1 ASSUMES THE REPLACEMENT SETTING LETS GREEN REPLACE.** The v2s are
  resupplies over filled slots (REQ-PIPE-123). Under a "hold" replacement
  setting, both wait for a person whatever this batch decides.
  REQ-PIPE-267 OQ3.
- **T16. THE WAREHOUSE VIEW AS AT T IS BUILD WORK.** Every counted result
  needs the window in which all its read supplies were in place, from the
  decision log. REQ-DASH-264 c11 and c12 (same-day counting, sparklines)
  then count only counted results. REQ-PIPE-269 NFR (performance).
- **T17. A PERIOD OPENED BY A FILING THAT LATER LEAVES.** A supply that is
  re-filed out, or rejected, leaves a period holding only inherited views.
  This is harmless, but new: nothing has ever seen such a period.
  REQ-PIPE-271 OQ2 (does anything assume a period holds a promotion?).

- **T18. A PERIOD BEFORE A PARTNER'S PARTICIPATION STARTS.** There is
  nothing to inherit, and there never will be. Under the strict rule, every
  check reading that dataset is red until a person acts, period after
  period. Recommended at sign-off: a check is out of scope where a table it
  reads is not owed and has never been supplied, which is the agreement, not
  an absence. REQ-PIPE-271 OQ3.
- **T19. THE CLOUD INGEST PATH HAS NO PACKAGES** (architect B1). Each S3
  object is recorded as its own delivery at its own storage instant, so a
  shared instant never forms, and every file there is staggered. → **Q9**.
- **T20. REJECTING A PACKAGE-MATE LEAVES THE OTHER'S REASON STALE** (CLI
  S3, dashboard S8). In S2 strict, a person rejects Notifications v2.
  Clients v2's verdict is unchanged (still no Notifications in place), but
  its recorded reason says a Notifications supply is "staged awaiting a
  decision". The queue would send the person to decide something already
  decided. → **Q10**.
- **T21. THE COLLECTION CARD MIXES VIEWS** (dashboard UX Q-A). In S1, the
  dataset rows show the newest supply (the staging verdict), while the
  warehouse is fine. The card's rollup then says red for a warehouse that is
  green. → **Q11**.

## Non-functional angles

- **Answered from the codebase and the database, and in the requirements:**
  - Performance: the cascade is bounded at n-1 rounds per package, and
    re-runs cross-table checks only. Queried 2026-10-21: 12 of 53
    multi-file Child Protection packages had a never-promoted file. Measured
    at build.
  - Scalability: per package and per collection, never per asset;
    aggregation is REQ-DASH-204 and REQ-PIPE-210.
  - Reliability: interrupted packages are finished, never part-gated.
  - Determinism and replay: package membership comes from the record; the
    cascade is a fixed point; there is no checkpoint inside a package.
  - Auditability: each refusal names its package-mate and what it was
    checked against; each re-run names the refusal.
  - Maintainability: one "which results count" function.
  - Compatibility: no new assets.
  - The build rule and privacy: recorded results and the decision log only.
- **Put to Keith:**
  - Reliability edges: Q3 (a package that never completes) and Q5 (no
    verdict about what is in place).
  - Observability and noise: Q6 (tickets and still-failing records).
  - Throughput: Q1 (whether staggered pairs need a person).
  - Notification timing: T8, for #113.
- **Ruled out as not applying:**
  - Security: no new capability. A person's override keeps its allowlist,
    actor and reason.
  - Compliance and retention: no new kind of stored data. Re-check runs are
    ordinary recorded runs.
  - Cost: re-runs are cross-table only, a few per refused package, and there
    is no clock-driven sweep. Negligible against the AWS MVP's per-arrival
    compute.

## Questions for Keith (recommended option first, each framed in a scenario)

### Set 1: how files get in

- **Q1. S3, staggered.** Notifications v2 arrives alone at 08:40 and is
  refused red, because there is no Clients. Clients v2 arrives alone at
  09:00, and its run checks Notifications' Client reference against the
  waiting Notifications v2: green. How do they get in?
  - **A (recommended):** Promote both together at Clients v2's gate.
    Notifications v2 is re-gated on the verdict Clients v2's run recorded,
    not re-checked. The end state is the same as B, with no moment where one
    is in the warehouse without the other. Needs a small refinement to
    REQ-PIPE-121's "a file landing in staging stays outside this mechanism"
    (re-gate, never re-check).
  - **B:** Clients v2 promotes alone on that verdict, then the knock-on
    re-checks Notifications v2 and promotes it. This is your own description
    of S3. For a moment the warehouse holds Clients v2 judged against a
    Notifications that is not in it, and if Notifications v2 then fails
    something else, Clients v2 stays promoted on a verdict about a file that
    never got in.
  - **C:** Neither. Clients v2 is re-checked against the warehouse's
    Notifications (none), so it is red, and both wait for a person. This is
    the strictest. Every staggered pair (312 in the bootstrapped history)
    would wait for a person.
- **Q2. S3b, the earlier file waits for its own red.** Clients v2 is
  waiting, red on its own blank values. Notifications v2 arrives alone 20
  minutes later, and its Client reference against the staged Clients v2 is
  green.
  - **A (recommended):** Re-check Notifications v2's Client reference against
    the Clients in place (v1, or none) before its gate, and decide on that.
    This is the same rule as inside a package, and it matches your 2026-09-26
    reasoning in REQ-PIPE-079: judging against an unaccepted supply "would
    record a green that becomes retroactively meaningless".
  - **B:** Gate it on the verdict against the staged Clients v2, as today.
    Notifications v2 promotes. The knock-on then re-checks the promoted
    Clients v1 against it, which can turn it red promoted after the fact.
- **Q3. S1, a package that cannot finish.** Notifications v2's run crashes
  part-way. Or it is checked, but its dataset is refused by the agreement
  backstop, so it is never gated. What happens to Clients v2?
  - **A (recommended):** A crash keeps the whole package waiting and owed
    until the next pass checks Notifications v2. A backstop refusal counts
    as "not promoting", so Clients v2 is re-checked against Notifications v1
    and gated. A crash is usually transient; a backstop refusal can last
    until someone fixes the agreement.
  - **B:** Both keep the package waiting. This is the simplest, but a
    long-lived backstop refusal holds a clean Clients v2 indefinitely.
  - **C:** Both count as "not promoting". Clients v2 always proceeds, but
    after a crash it is judged without knowing what Notifications v2 would
    have found.
- **Q4. S6, inheritance once the quarter opens at filing.** Case Workers
  sits out 2024-Q4. The Q4 package arrives on 1 Nov and is filed, which
  opens Q4. Two cases:
  - (i) Case Workers has never been promoted, so the inheritance is
    refused, and every reader of Case Workers in Q4 is red.
  - (ii) Case Workers' Q3 supply is still waiting, so Q4 inherits Q2's. On
    3 Nov a person promotes the Q3 Case Workers.

  What happens later?
  - **A (recommended):** Retry a REFUSED inheritance when an earlier supply
    is later promoted, so that (i) clears through the knock-on. A refused
    inheritance never stood on anything, so no reader's earlier verdict
    changes. Leave a MADE inheritance as it is, and warn: in (ii), Q4 keeps
    Q2's Case Workers, the decision log names both supplies, and a person
    can substitute. This bends your 2026-09-26 "only at birth" rule for the
    refused case only. The v3-shape architect review recommends the same.
  - **B:** Keep "once" for both. (i) stays red until a person substitutes;
    (ii) is warned only.
  - **C:** Retry the refused one AND re-point the made one automatically,
    with the knock-on re-checking Q4's readers. This is always current, but
    it is an automatic inheritance after birth in both cases, which your
    2026-09-26 rule ruled out.

### Set 2: what is shown, and who is told

- **Q5. S1 step 4, the re-check is owed.** Clients v2 is promoted (green
  branch). At 4:55pm a person promotes Notifications v2 over its red. The
  knock-on that would re-check Clients v2 against it fails, and stays owed
  until the next morning's pass. What does Clients v2's page show that
  evening?
  - **A (recommended):** Red: "not yet checked against the Notifications in
    place". No recorded verdict is about Clients v2 with Notifications v2.
    This is strict and honest, and it clears when the owed re-check runs.
    Normally the knock-on runs straight after the promotion, so nobody sees
    it.
  - **B:** Its last verdict (against Notifications v1), with a note that a
    re-check is owed. This avoids a red, but it shows a verdict about a
    pairing no longer in the warehouse, which is half-and-half.
- **Q6. S2 strict, one cause and two reds.** Notifications v2 is red on its
  own data, and Clients v2 is refused only because of it. Which of them gets
  a ticket, and a "still failing, a person decides" record?
  - **A (recommended):** One per cause. Notifications v2's ticket and record
    list Clients v2 as affected. Clients v2 gets no ticket of its own, and
    no knock-on writes a still-failing record for a waiting supply whose red
    the knock-on did not change. This follows your v2 Q6 and Q7 answers ("the
    missing table's own ticket carries it"), and it is what red-driven
    notifications would need at ~30 collections.
  - **B:** Each red supply gets its own ticket and record, like any red. This
    is consistent with "red holds like any red", but one bad Client Register
    file could raise a ticket for every table that reads it.
- **Q7. S2 strict, in the synthetic history.** Clients v2 is built green and
  Notifications v2 is built red, in the same zip. Clients v2 ends red because
  of Notifications v2, and target agreement (REQ-GEN-186) fails the bootstrap
  on that.
  - **A (recommended):** Compare a supply's target with its verdict, leaving
    out could-not-run checks and the re-checks a package-mate's refusal
    caused. Report those differences without failing. Targets stay about the
    file's own data.
  - **B:** Targets declare the strict red too, so every scenario author
    encodes the gating rule.
  - **C:** Compare as today and fix each scenario that fails. That includes
    the early file of each of the 312 staggered pairs.
- **Q8. S2 strict, in the terminal.** Clients v2 waits red only because
  Notifications v2 was refused. In "Supplies waiting on a decision":
  - **A (recommended):** Restore the close-out REQ-PIPE-210. Clients v2 is
    listed once, beneath Notifications v2's item, saying nothing needs
    deciding on it, and it is not counted. The decision that clears it is
    Notifications v2's.
  - **B:** Drop REQ-PIPE-210. Clients v2 is listed and counted like any red,
    with REQ-DASH-204's line on its page. Less to build, but the queue
    invites a decision on the wrong supply.

### Set 3: edges the reviews found

- **Q9. S1, but uploaded to the cloud path.** The supplier uploads Clients
  v2 and Notifications v2 to S3 a second apart. The cloud ingest records each
  object as its own delivery at its own instant, so they are never a package
  and are gated as staggered files.
  - **A (recommended):** Packages are the zip-delivery concept for now. On
    the cloud path every file is a package of one, until a boundary marker
    is scoped with the transport layer (plans/supply-thoughts.md,
    running-thoughts #114). The AWS design doc says so. Staggered handling
    (Q1, Q2) still keeps the warehouse consistent; it just flickers.
  - **B:** Define a cloud package boundary now (for example, an upload
    prefix plus a manifest object). That is a transport-layer design you
    have deliberately not scoped yet.
- **Q10. S2 strict, a package-mate is turned down.** Notifications v2 is
  rejected. Clients v2 stays red (there is still no Notifications in
  place), but its recorded reason says a Notifications supply is "awaiting a
  decision".
  - **A (recommended):** No re-check, because the verdict cannot change.
    The page and terminal word the reason from the decision log as it
    stands: "The Notifications file received with it was turned down; this
    supply now needs its own decision." Keeps your "re-check only on
    promotion".
  - **B:** Rejecting a package-mate also re-runs the others' affected
    checks, so the recorded reason is refreshed. It mirrors REQ-PIPE-211 for
    contests, but it bends "only on promotion" for package-mates.
- **Q11. S1, the collection card.** Notifications v2 is waiting red, and
  the warehouse (Clients v2 + Notifications v1) is green. What does the
  Child Protection card's rollup say?
  - **A (recommended):** As today, it follows each dataset's headline (the
    newest supply), so the card counts Notifications red. It adds one line
    per held-back delivery: "[Red] Held together: Notifications, Client
    Register (one delivery, received ...)". The reader sees there is
    something to decide.
  - **B:** The card rolls up the warehouse view, with "2 awaiting a
    decision" beside it. Calmer, but a waiting red no longer reddens the
    card.
- **Q12. S1, every cross-table row.** Should every cross-table row say
  which supply of the other table it was read against?
  - **A (recommended):** Yes, on both views: "Read against the
    Notifications in place, received 1 Jul" or "... the Notifications supply
    received 1 Oct, not in place yet". Supplies are named by receipt. This
    makes the no-half-and-half principle visible.
  - **B:** Only where the row was re-checked against what is in place
    (REQ-DASH-272 c4) or read a waiting partner (c5). Less text per row.

### Also for Keith, at sign-off rather than as relay questions

- The terminology: "not promoting" and "waiting" rather than "held".
- The staging view made precise (REQ-PIPE-267 d9). Once a package-mate is
  not promoting, "what is staged for its dependencies" means what is staged
  *and promoting with it*. That is what your S1 step 3 says.
- Case 3a: a reader of a slot accepted as "not supplied" stays red (your v2
  Q5 = A, carried by analogy).
- REQ-DASH-272 c4's row wording and REQ-PIPE-267 c13's refusal wording.
- From the dashboard UX review of the shape, proposed as REQ-DASH-204's
  wording:
  - name the root and the chain in a cascade (its Q-E);
  - a "cleared minutes later" note on a staggered red's history row (Q-F);
  - "Held with the Notifications file it came with" for S1's red branch,
    with no "not a fault" clause (Q-B).
- T18: a period before a partner's participation starts.

### For the delivery-architect

- T13: refuse a person's decision on a sibling of a package not yet gated.
- CLI review S8: a decision landing mid-cascade, and the re-confirm key.
- Whether a dashboard build can run mid-cascade (dashboard UX Q-G);
  267 c10 assumes it can, and excludes unsettled results.
- T14: re-filed siblings.
- 267 OQ2: an overlay that leaves out a not-promoting supply, and a
  readers-only run caused by a refusal.
- 271 OQ2: anything that assumes a period holds a promotion.
- The build order and the one-push rule above.
- Confirm that the cascade's fixed point is order-independent as built.

## Draft entry for plans/running-thoughts.md #95 (for a human to apply)

> Replace the last sentence ("Related, built the same day: REQ-PIPE-265's 312 staggered pairs are this item's false-green case.") with: "**SHAPE REOPENED 2026-10-20 and re-settled 2026-10-21: red only, strict** (Keith: 'It's the strictest rule. It's probably the easiest to sort of think about and understand'). Re-scoped 2026-10-21 into `docs/drafts/unjudged-cross-table/summary-v3.md` and `requirements-draft-v3.yaml` as REQ-PIPE-266 to REQ-DOCS-274 (unsigned). A package is gated together; a not-promoted package-mate means re-checks against what is in place, cascading; a promoted supply counts only verdicts about what is in place; a period is opened at first filing. v2's REQ-QAC-212 to REQ-PIPE-217 are withdrawn. REQ-DASH-204, REQ-PIPE-210 and REQ-PIPE-211 return to their close-out versions with listed edits. Twelve questions are with Keith (Q1-Q12). The delivery-architect and both UX reviewers reviewed the shape beforehand, and their findings are folded in."

## Validation

- `uv run mothman dashboard validate-requirements --draft
  docs/drafts/unjudged-cross-table/requirements-draft-v3.yaml` reports 30
  errors. Every one is a dependency on a requirement outside the draft, which
  is expected.
- Merged with `requirements.yaml` and the close-out draft's REQ-DASH-204,
  REQ-GEN-206, REQ-PIPE-210 and REQ-PIPE-211 (in the scratchpad as
  `merged95v3.yaml`), it reports: "requirements validation OK - 261
  requirements, zero errors."
- I read the file back with `yaml.safe_load`. All nine requirements parse,
  every prose item is a string, and none carries `signed_off`.
