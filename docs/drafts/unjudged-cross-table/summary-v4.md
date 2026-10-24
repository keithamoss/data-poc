# Cross-table checks that could not run, or were judged against the wrong partner (#95): draft v4, for sign-off

Re-folded by delivery-scoper on 2026-10-22 (Perth), using every answer Keith gave
that day (`summary.md`, from "Keith's answers on v3, 2026-10-22 (Perth)" to
the end) and the four reviews of v3. This is a **proposal**. Nothing in it is
in `requirements.yaml`, and nothing is signed. The requirements are in
`requirements-draft-v4.yaml`, next to this file. v3 (`summary-v3.md`,
`requirements-draft-v3.yaml`) is left as it is, as history.

**How sign-off works this time** (Keith, `summary.md`, "How Keith will sign
v4 off"): the scoper writes this draft, then the architect reviews it, then
both UX reviewers. After that, Keith gets one last check-in: a walk-through
of S1 as it now works end to end. He does not need to approve exact wording,
"as long as what I've decided hasn't changed or there's been no new
questions". So this summary marks plainly:
- anything that moved one of his decisions (nothing did, as far as I can
  tell; see the carry-over check), and
- every question that is new rather than carried over.

## The shape, in one paragraph

The design is red only, and strict. A cross-table check that cannot read a
partner is red, but only for the table that asks the question (Q13 = B). An
absent partner is never treated as empty.

Files that arrive together (one zip, one receipt instant) are gated together,
once every one of them has been checked.

Every gate is a **gate application**: the newly checked supplies, plus every
supply waiting in the same period that is connected to them through recorded
cross-table verdicts, transitively (architect N1). A supply is promoted only
on verdicts about what the warehouse will hold. When one supply in the set is
held back, the others' cross-table checks are re-run against what is in the
warehouse, until nothing changes. Supplies that depend on each other promote
together or not at all. No check is ever run for a waiting supply.

A promoted supply counts a verdict only when every supply that verdict read
is still the one in the warehouse.

A quarter opens, and makes its inheritances, at its first filing. It
inherits once. A warning appears when a newer supply could be carried forward
instead (Q4 = B).

On the dashboard:
- The awaiting-a-decision line says whether the warehouse is still green.
- Each cross-table check is one row in a grid, with two columns: "Against
  what's staged" and "Against what's in the warehouse" (density Option C).

One ticket and one still-failing record are raised per root cause. "In place"
now reads "in place in the warehouse" everywhere a person sees it.

## The requirements

| Id | MoSCoW | What it covers | Changed in v4 |
|---|---|---|---|
| REQ-PIPE-266 | must | Package = shared receipt instant. Gated together once every file is checked. A crash waits; a backstop refusal counts as held back. A hold-back is written as `promotion-withheld` the moment it is final. Decisions during a gate are refused; `promote()` re-confirms under the slot locks. The joint promotion is recorded. | Q3, Q9, N3, T13/S16, the mid-gate refusal, the joint-promotion record |
| REQ-PIPE-267 | must | The gate's view, made transitive, settled by the fixed point. The hold-back reason is stored as fields, plus its wording. | N1 (absorbs 268 and v3 c14), two-table limit, evaluated "over the whole set at once"; terminal criteria moved to 276 |
| ~~REQ-PIPE-268~~ | - | **Withdrawn.** Folded into REQ-PIPE-267 c2-c3 (N1). The id is spent. | - |
| REQ-PIPE-269 | must | The warehouse view, by supply. A could-not-run counts only toward the declaring table. An owed re-check reads red and raises nothing. | Q13, Q5 |
| REQ-PIPE-270 | must | Strict: could-not-run is red for every reason. `describe()` covers every reason. | Q13, CLI describe() |
| REQ-PIPE-271 | must | Open at filing. Inherit once. A stale or refused carry-forward is warned on the dashboard, in the queue and in the door. | Q4 = B + warning, S17, pins |
| REQ-DASH-272 | must | The awaiting line's warehouse clause. The cross-table **grid** (Option C). Q12's "what it read". The dual result row. Owed re-check wording. Joint-promotion history row. | Q12, S6, Option C, D1-D4, N4, N5, Q5 |
| REQ-GEN-273 | must | The target compares the file's own checks. A few scenarios pin the gate's outcome. | Q7 = A + scenarios |
| REQ-DOCS-274 | should | Supplier guidance: send one zip, on the cloud path too. | Q9 |
| **REQ-DASH-275** | must | **New.** Held back with its delivery: the top notice for S1 red, the root and the chain, "Holding back with it", one card line per delivery. | S1-red top, S6 root, Q11, Q10 |
| **REQ-PIPE-276** | must | **New.** What the terminal says about a package gate: vocabulary, exit code, next step, grouping by root, override consequences, follow-up, crashed-sibling wording, re-file warning. | CLI review of v3, N1-N5 |
| **REQ-DASH-277** | should | **New.** "In place" becomes "in place in the warehouse" wherever a person sees it. | Keith's general wording change |
| **REQ-PIPE-278** | must | **New.** One ticket and one still-failing record per root cause. Nothing raised for an owed re-check or a partner not yet due. | Q6, Q5, N1 |
| REQ-DASH-204 | must | **Re-folded** (replaces the close-out version). A check that could not run because another table is absent: one wording, the S2 package form, the owed re-check, the not-due muted line, the rejected package-mate. | S2 wording, N1, Q5, Q10 |
| REQ-PIPE-210 | should | **Re-folded** (replaces the close-out version). Listed beneath the root, not counted, not pickable, overridden by naming it, becomes its own row once the cause is rejected. | Q8 = A, Q10 |

REQ-PIPE-211 is not re-drafted. Its four edits are listed below.

**Build order** (architect, v3 draft review, extended):
1. 269. It fixes the live `runs_about` issue on its own; Q13's counting
   goes with it.
2. 271.
3. 270, 266, 267, 273 and 278, **in one push behind one bootstrap**. N3's
   schema change (the hold-back cause, the owed package-gate item) goes with
   266. The bootstrap before this push is the "before" capture.
4. 276.
5. 204, 210, 272, 275 and 277. 277 can go with 272, since they share
   wording.
6. 274.

## What changed from v3, requirement by requirement

- **266.**
  - c3 gives the owed package gate a cause: the last arrival's load, or a
    new owed kind (architect N3).
  - c6 is no longer provisional, and the AWS doc must state the limitation
    (Q9 = A).
  - c9: a hold-back is a `promotion-withheld` entry, written the moment it
    is final (N3; CLI vocabulary).
  - c10 is new: a promotion names what it was promoted with.
  - c13 and c14 are no longer provisional (Q3 = A). c13 adds that the next
    pass re-runs the crashed file.
  - New criteria: c15, the mid-gate refusal in Keith's wording; c16,
    `promote()` re-confirms under the slot locks (T13/S16).
  - New tests: the crashed sibling, the backstop sibling, the mid-gate
    refusal and S16.
  - The no-flicker NFR is rewritten for "written when final".
- **267.**
  - c2 and c3: the transitive gate application, at every gate entry,
    including `recheck.execute` (N1, T14). A joined waiting supply is never
    re-checked: where its verdict would need it, it is simply not promoting.
  - c7 adds "evaluated over the whole set at once".
  - c12 is the hold-back wording ("Held back: ...", not "Refused:"), stored
    as fields, with the locus clause "This supply's own checks passed."
  - v3's c14 (Q2) is folded into c2.
  - v3's c11, c12 and c15 (exit code, next step, override warning) moved to
    276.
  - Tests added: S3 and S2b (from 268), S3b (no longer provisional), S10,
    S11, and T14's re-filed partners.
  - New decisions: the transitive gate, the two-table accepted limit, and
    holding a failing pair together.
  - The open questions for the architect that N3 and the v3 review answered
    are gone.
- **269.**
  - c4 is rewritten for Q13 = B.
  - c5 is no longer provisional (Q5 = A), with a structured `recheck-owed`
    reason.
  - c6 is new: nothing is raised for an owed re-check.
  - Tests added: S14, S14b, the absent-Clients direction, and Q5.
  - New open question 1 (a held table's own page under Q13; **new**).
- **270.**
  - c1 says the could-not-run is counted as 269 c4 says.
  - c4 records the not-due instant and "held back with its package" as
    structured codes.
  - c5 is new: `describe()` has a text for every reason (CLI review).
- **271.**
  - c5 and c6 are replaced by Q4 = B: carry forward once, never retry or
    re-point. A warning goes to the decision log (c6), the dashboard and
    the terminal (c7, new wording), and clears only when it stops being true
    (c8).
  - c9 says the pins may need a generator fix, not a re-pin.
  - v3's open question 2 was answered by the architect and moved into the
    decisions.
  - S17 is recorded as accepted.
- **272.**
  - c1 to c5: D2's formats, D1's double red-promoted text removed, N5's
    named person, N4's inherited supply, D4's nothing-in-the-warehouse form.
  - **c6 to c16: the Option C grid.** One row per check, the two columns,
    the cell content, the dual row, the owed re-check cell, the key line,
    the panel and accessible name holding the full sentences, the two exempt
    kinds, links, and stacking at phone width.
  - c20: the joint-promotion history row.
  - The amendment list adds REQ-DASH-264 c2, c7 and NFR 2.
  - Q11 and Q12 are no longer provisional.
- **273.**
  - It is no longer provisional in whole (Q7 = A).
  - c3 and c4 are new: scenarios declare the gate outcome they expect, for
    S1 green, S1 red, S2 strict, S10 and S14.
  - c6 audits the pins too.
- **274.** It says to upload a zip, on the cloud path too (Q9). Its open
  question gains a recommendation.
- **204 and 210.** Fully re-drafted (see each requirement's last
  "decisions" entries for what moved). 204 loses its "never a not-yet-due
  one" exclusion and its five per-cause wordings, and gains:
  - the S2 package form;
  - the owed re-check and settled-pair lines;
  - the not-due muted line on the partner's page;
  - the rejected package-mate wording.

  210 gains Q8 = A's placement and the chain, flat under its root.

## Amendments to SIGNED requirements: exact wording for approval

`<date>` is filled in by whoever builds it. Each amendment changes only the
quoted part.

**REQ-PIPE-081 c1** (signed 2026-09-26), by REQ-DASH-272. Unchanged from v3.
- OLD: "WHERE the newest is awaiting a decision while an older one is promoted, THE SYSTEM SHALL also name the promoted one as what is in place."
- NEW: "WHERE the newest is awaiting a decision while an older one is promoted, THE SYSTEM SHALL also name the promoted one as what is in place, and SHALL give that supply's status as in place at T, counted by REQ-PIPE-269." Append: "AMENDED `<date>` by REQ-DASH-272 (Keith, 2026-10-21, option 2): a reader of a page whose newest supply waits must also see whether the warehouse is still green."

**REQ-PIPE-081 c20** (signed 2026-09-26), by REQ-DASH-277. **Provisional on open question A.**
- OLD: "THE SYSTEM SHALL label the date control \"In place on\" rather than \"As of\", ..."
- NEW: "THE SYSTEM SHALL label the date control \"In the warehouse on\" rather than \"As of\", ... AMENDED `<date>` by REQ-DASH-277 (Keith, 2026-10-22: say where)."

**REQ-PIPE-081 c23** (signed 2026-09-26), by REQ-DASH-277. **Only if open question A's recommendation is taken.**
- OLD: "THE SYSTEM SHALL name the date control's own element ids and its query-string parameter after the label the control carries, and SHALL NOT keep \"asof\" as an identifier anywhere in the page."
- NEW: append: "The ids and the parameter stay `in-place-on` when the label became \"In the warehouse on\" (REQ-DASH-277), so that no saved link needs a second redirect. AMENDED `<date>` by REQ-DASH-277."

**REQ-PIPE-105 c1** (signed 2026-09-28), by REQ-PIPE-266. Unchanged from v3.
- OLD: "THE SYSTEM SHALL treat every arriving file as its own arrival, and SHALL process it without waiting for any other file."
- NEW: "THE SYSTEM SHALL treat every arriving file as its own arrival, and SHALL file and check it without waiting for any other file; WHERE several arrivals share one receipt instant, THE SYSTEM SHALL gate them together once all of them are checked (REQ-PIPE-266), which waits on their checks and never on another arrival. AMENDED `<date>` by REQ-PIPE-266."

**REQ-PIPE-121 c9** (signed 2026-10-04), by REQ-PIPE-266.
- OLD: "THE SYSTEM SHALL run one re-evaluation per decision, over every table that decision moved into or out of a period schema, after the decision commits, and SHALL NOT run one per table moved."
- NEW: "THE SYSTEM SHALL run one re-evaluation per decision - or, where one gate application (REQ-PIPE-267 criterion 2) makes several promotions, one for all of them - over every table moved into or out of a period schema, after the last of them commits, and SHALL NOT run one per table moved or per promotion of one gate application. AMENDED `<date>` by REQ-PIPE-266 criterion 11."

**REQ-PIPE-121 c12** (signed 2026-10-04), by REQ-PIPE-278. **New in v4.**
- OLD: "WHEN a re-evaluation leaves a waiting supply failing the automatic-promotion rules as resolved for its dataset - red, or amber where the resolved amber setting (REQ-PIPE-122) is 'hold' - THE SYSTEM SHALL record that, grouped as ONE record per causing decision naming every such supply (...), in the decision log at its highest prominence, with the rule as actor, naming the supply, the promotion that caused the re-check and the reason it still cannot promote, so that a person sees it and acts."
- NEW: append: "A waiting supply whose failing checks are all another table's doing (REQ-PIPE-278 criterion 1) is named in its ROOT CAUSE's record rather than given its own, and no record is written for a waiting supply whose failure the re-evaluation did not change. AMENDED `<date>` by REQ-PIPE-278 (Keith, 2026-10-22, Q6 = A: one record per root cause)."

**REQ-PIPE-121 NFR 4**, by REQ-PIPE-269.
- OLD: "Cheapest correct path first: a waiting supply's status is recomputed from its latest result per check, and a check's tools re-run only where its latest recorded result read a different supply than the one the period now holds. Recomputing a status from latest results is one function, shared with REQ-DASH-126."
- NEW: "Cheapest correct path first: a supply's status is recomputed from its latest COUNTED result per check (REQ-PIPE-269), and a check's tools re-run only where that result read a different supply than the one the period now holds, read nothing for it, or could not be evaluated for want of a table (REQ-PIPE-269 criterion 8). Recomputing a status from counted results is one function, shared with REQ-DASH-126. AMENDED `<date>` by REQ-PIPE-269."

**REQ-PIPE-121 decision 11, "A FILE LANDING IN STAGING STAYS OUTSIDE THIS MECHANISM"**, by REQ-PIPE-267. **Now unconditional** (in v3 it depended on Q1).
- APPEND: "REFINED `<date>` by REQ-PIPE-267 criterion 2 (Keith, 2026-10-22, the transitive group gate): a landing file still re-checks no other table. But every supply waiting in its period that is connected to it through recorded cross-table verdicts is RE-GATED with it, in one gate application, on recorded results alone - never re-checked - so that supplies that depend on each other promote together."

**REQ-PIPE-083 c21** (signed 2026-09-28), by REQ-PIPE-278. **New in v4.**
- OLD: "THE SYSTEM SHALL read its ticket policy from DATA-ASSET-LEVEL configuration, offering at least `all` - a ticket for every slot - and `needs-action` - a ticket for a slot that is amber, red, overdue, late, held, or awaiting a person's decision because automatic promotion did not apply - and SHALL default to `needs-action`."
- NEW: append: "Under `needs-action`, a slot whose supply is red only by another table's doing - held back with a package-mate, or a cross-table check that could not run for want of another table - and a slot whose only red is an owed re-check get no ticket of their own; the root cause's ticket names them (REQ-PIPE-278). AMENDED `<date>` by REQ-PIPE-278 (Keith, 2026-10-22, Q6 = A and Q5 = A)."

**REQ-PIPE-075 c2** (signed 2026-09-26), by REQ-PIPE-267. Unchanged from v3.
- OLD: "THE SYSTEM SHALL take the status this gate reads from EVERY check that contributes to that dataset's status - ... - and SHALL NOT gate on a subset of them."
- NEW: append: "A cross-table check is read by its result about the warehouse as it will stand once this gate's promotions are made (REQ-PIPE-267 criterion 1), re-evaluated where the result it has read a supply that will not be in place. AMENDED `<date>` by REQ-PIPE-267."

**REQ-QAC-037 c7** (signed 2026-09-23), by REQ-PIPE-269. **Rewritten for Q13 = B.**
- OLD: "THE SYSTEM SHALL fold a cross-table check's verdict into the status of every dataset it reads, whether that check failed or could not run, and SHALL NOT leave a participating dataset reading green while a check that reads it reads red."
- NEW: "THE SYSTEM SHALL fold a cross-table check's EVALUATED verdict into the status of every supply its run read - for a supply in place, only a verdict whose every read supply is the one in place (REQ-PIPE-269) - and a check that COULD NOT RUN only into the status of the supply the check is declared on, and into nothing where the declaring table is the one that could not be read; and SHALL NOT leave a supply reading green while a check counted toward it reads red. AMENDED `<date>` by REQ-PIPE-269 (Keith, 2026-10-21: judged by supply; 2026-10-22, Q13 = B: a check that could not run counts only against the table that asks)."

**REQ-PIPE-079 c14** (signed 2026-09-26), by REQ-PIPE-270.
- OLD: "WHERE a table a check reads has no promoted supply for the period and that period's slot for it is neither past due nor closed, THE SYSTEM SHALL NOT report the check red, and SHALL say the table has not been supplied for this period yet and is not yet overdue."
- NEW: "WHERE a table a check reads has no supply the run may read for the period and that period's slot for it is neither past due nor closed, THE SYSTEM SHALL report the check red, not evaluated, for the table the check is declared on (REQ-PIPE-270, REQ-PIPE-269 criterion 4), and SHALL say the table has not been supplied for this period yet and is not yet overdue, recording when it falls due. AMENDED `<date>` by REQ-PIPE-270 (Keith, 2026-10-21, strict): not yet due was the false green."
- **Decision 23**, append: "SUPERSEDED IN PART `<date>` by REQ-PIPE-270: `awaiting-supply` keeps its own code and wording, but is red. Its reason ('every new dataset starts life red ... which is how people learn to ignore a signal') is answered by supplier guidance (REQ-DOCS-274), Keith's acceptance of the staggered-file flicker (2026-10-20), and no ticket for a partner not yet due (REQ-PIPE-278)."

**REQ-PIPE-115 c20** (signed 2026-10-04), by REQ-PIPE-270. Unchanged from v3.
- OLD: "...asserts at qa.check_result that each records its own reason code - nodata for not yet due, red for the other two - rather than the catch-all."
- NEW: "...asserts at qa.check_result that each records its own reason code, all three red, rather than the catch-all. AMENDED `<date>` by REQ-PIPE-270: not yet due read nodata."

**REQ-PIPE-098 c4** (signed 2026-09-28), by REQ-PIPE-271. Unchanged from v3.
- OLD: "THE SYSTEM SHALL create a period's schema either on the first promotion into it or on an explicit instruction to open it, and SHALL NOT require an arrival before a period can exist - using the SAME creation mechanism for both, so that a period opened by instruction is indistinguishable from one created by a first promotion."
- NEW: "THE SYSTEM SHALL create a period's schema on the first FILING to it (REQ-PIPE-271), or on an explicit instruction to open it, whichever comes first, and SHALL NOT require an arrival before a period can exist - using the SAME creation mechanism for both, so that a period opened by instruction is indistinguishable from one opened by a filing. AMENDED `<date>` by REQ-PIPE-271 (Keith, 2026-10-20: 'inherit when the quarter is filed, not when it is first promoted')." The unmet entry for the explicit instruction stays, unowned.

**REQ-PIPE-262 c12** (signed 2026-10-19), by REQ-PIPE-271 c9 and REQ-GEN-273 c6. No wording change, but **its pinned supplies may move**. So may TS-63's expectations and REQ-GEN-251 c3's. The architect expects some may need a generator fix rather than a new value. Each one comes to Keith with its cause. Nothing is re-pinned quietly.

**REQ-DASH-264 c1** (signed 2026-10-19), by REQ-PIPE-269. Unchanged from v3.
- OLD: "THE SYSTEM SHALL show on a dataset page, for each check, the newest result recorded for that dataset on or before the in-place-on date, whichever table's run recorded it - the result the promotion gate reads - so a re-check of one table that re-runs another's cross-table checks changes the other table's page from the day it was recorded."
- NEW: "THE SYSTEM SHALL show on a dataset page, for each check, the newest result counted toward the supply the page is about on or before the in-place-on date (REQ-PIPE-269), whichever table's run recorded it, so a re-check of one table that re-runs another's cross-table checks changes the other table's page from the day it was recorded, and a run that read a supply not in place never changes an in-place supply's page. AMENDED `<date>` by REQ-PIPE-269."

**REQ-DASH-264 c2** (signed 2026-10-19), by REQ-DASH-272 (Option C). **New in v4.**
- OLD: "THE SYSTEM SHALL name on every cross-table row the dataset the check is declared on and the datasets it reads, as \"<declared on> → <reads>\", so a table read by several others shows each relationship as its own check."
- NEW: "THE SYSTEM SHALL show each cross-table check as ONE row, whichever tools ran it, naming under the check's name the dataset it is declared on and the datasets it reads, as \"<declared on> → <reads>\", so a table read by several others shows each relationship as its own row (REQ-DASH-272). AMENDED `<date>` by REQ-DASH-272 (Keith, 2026-10-22, Option C)."

**REQ-DASH-264 c7** (signed 2026-10-19), by REQ-DASH-272. **New in v4.**
- OLD: "WHERE the result a row shows was recorded under another table's run, THE SYSTEM SHALL say so on the row, after the tool name, every time - ..." (the rest of the criterion, with its sentences and its 2026-10-19/20 history, is unchanged).
- NEW: "WHERE a result was recorded under another table's run, THE SYSTEM SHALL say so in the check's panel under that tool's result, and in the row's accessible name, every time - ..." Append: "AMENDED `<date>` by REQ-DASH-272 (Keith, 2026-10-22, Option C): the row carries a short note of which supply was read, and the full sentence moves to the panel and the accessible name."

**REQ-DASH-264 NFR 2** (signed 2026-10-19), by REQ-DASH-272. **New in v4.**
- OLD: "At thirty collections a table read by many others lists one labelled row per relationship per tool; the label is what keeps that list readable."
- NEW: "At thirty collections a table read by many others lists one labelled row per relationship, its tools shown as marks in the row's cells; the label is what keeps that list readable. AMENDED `<date>` by REQ-DASH-272."

**REQ-DASH-264 "M4"**: the density review says "264 M4 (signed)" for the section's ordering by relationship. REQ-DASH-264 has **no item labelled M4** in the register (decisions D1-D9, NFRs 1-2). The ordering by relationship lives in c2 and NFR 2, and both are amended above. Option C keeps relationship order (one row per check), so no other text needs changing. **For the dashboard UX reviewer to confirm** what "M4" referred to.

**REQ-DASH-264 c5** (signed 2026-10-19), by REQ-PIPE-269. **Only if open question B's recommendation is taken; new in v4.**
- OLD: "THE SYSTEM SHALL leave the held dataset's own status red by REQ-PIPE-115 criterion 10, the cross-table results changing only the cross-table section's own pill."
- NEW: append: "A result that could not run counts toward the table the check is declared on only (REQ-PIPE-269 criterion 4), so on the held table's page it is shown but does not colour that pill. AMENDED `<date>` by REQ-PIPE-269."

**REQ-GEN-186 c3** (signed 2026-10-11), by REQ-GEN-273. Now unconditional (Q7 = A).
- OLD: "WHEN a replay of the synthetic history finishes, THE SYSTEM SHALL compare every targeted supply's verdict as the promotion gate reads it - injected and ordinary amber alike, in both collections - with its target, and IF they differ, THEN THE SYSTEM SHALL fail the bootstrap naming the scenario or period and the checks responsible."
- NEW: "WHEN a replay of the synthetic history finishes, THE SYSTEM SHALL compare every targeted supply's verdict on its own checks - leaving out cross-table checks that could not read a partner and re-evaluations made because another supply was held back (REQ-GEN-273) - injected and ordinary amber alike, in both collections, with its target, and IF they differ, THEN THE SYSTEM SHALL fail the bootstrap naming the scenario or period and the checks responsible. The gate's own outcome is pinned by REQ-GEN-273's declared gate outcomes. AMENDED `<date>` by REQ-GEN-273 (Keith, 2026-10-22, Q7 = A)."

**REQ-TEST-159 c1** (signed 2026-10-06), by REQ-PIPE-266. Unchanged from v3.
- OLD: "WHEN a person replays one collection asking for a checkpoint before arrival N, THE SYSTEM SHALL save a copy of the database as it stood once arrival N-1 was fully processed, recording with it the collection, N, and the inputs REQ-TEST-160 compares."
- NEW: append: "WHERE arrival N is not the first of its package (REQ-PIPE-266), THE SYSTEM SHALL refuse, naming the package's first arrival. AMENDED `<date>` by REQ-PIPE-266 criterion 17."

**REQ-DASH-277's quoted-wording amendments** (all signed and built; only the quoted fragment changes; `<picker label>` is open question A):
- **REQ-PIPE-081 c20** (above).
- **REQ-DASH-182 c3**:
  - OLD: "'Pick a later date, or reset to the default, using the 📅 In place on control above.'"
  - NEW: "'Pick a later date, or reset to the default, using the 📅 `<picker label>` control above.'"
- **REQ-DASH-208 c4**:
  - OLD: "'`<scenario id>` · in place on `<date>`'"
  - NEW: "'`<scenario id>` · `<picker label, lower case>` `<date>`'"
- **REQ-GEN-199 c18**:
  - OLD: "'Awaiting a decision — the results below are the newest supply, received `<D+2 receipt>`, which is not in place yet. The supply in place is the one received `<D's receipt>`.'"
  - NEW: "'Awaiting a decision — the results below are the newest supply, received `<D+2 receipt>`, which is not in place in the warehouse yet. The supply in place in the warehouse is the one received `<D's receipt>`, and is `<status>`.'"
  - The status clause comes from REQ-DASH-272 c1, and the wording from REQ-DASH-277.
- **REQ-GHUB-229 c5**:
  - OLD: "in place (promoted)"
  - NEW: "in place in the warehouse (promoted)"

**No amendment needed** (each reason is recorded in the requirement):
- REQ-PIPE-265: it stands.
- REQ-PIPE-105 c2, c5, c13.
- REQ-PIPE-078 c10.
- REQ-PIPE-079 c4, c15, c16.
- REQ-PIPE-121 c1, c3, c6, c11.
- REQ-DASH-126.
- REQ-PIPE-163 c20: 276 c1 complies with it.
- REQ-PIPE-099: the warning names its operations and does not change them.
- REQ-GHUB-229 c6: prose, not quoted wording.
- REQ-GEN-199's other quotes: they are re-captured with the bootstrap.
- Register prose that uses "in place" as a term: left alone (277 decision 3).

## Edits to the close-out drafts (unsigned)

- **REQ-DASH-204 and REQ-PIPE-210:** replaced whole by the v4 versions in
  `requirements-draft-v4.yaml`. Apply the v4 versions, not the close-out
  ones.
- **REQ-PIPE-211** (stays a must, Keith Q9 = B, 2026-10-20). Four edits:
  - Its B1 dependency moves from v2's REQ-PIPE-215 to REQ-PIPE-269 c8; add
    REQ-PIPE-269 to its dependencies.
  - c2's "for the reason that now applies" now reads red (REQ-PIPE-270).
  - c3's "apply the promotion gate to each waiting supply the re-evaluation
    touched" becomes "...as one gate application (REQ-PIPE-267 criterion
    2)".
  - c8 at scale: one line per resulting status, up to eight readers, then
    "and `<n>` more", reusing `_run_owed`'s wait line (v2 CLI review 5,
    carried).
- **REQ-GEN-206 c18** (TS-81 "b"): "no reader's cross-table result reads
  contested" stands. Add: "each reader reads red, with REQ-DASH-204's line
  'No promoted Client Register for `<period>`'". Under Q13 = B the readers
  are the tables declaring checks against cp_clients, so this still holds.

## Every case under v4 (Keith's scenarios, plus the reviewers')

| # | Scenario | Under v4 | Where |
|---|---|---|---|
| S1 green | A zip of Clients v2 and Notifications v2 over v1 + v1. Notifications v2 is red on its own data. | Both are checked, then gated together. Notifications v2 is held back. Clients v2 is re-checked against Notifications v1, passes, and is promoted. | 266, 267 |
| S1 red | The same, but Clients v2 drops clients that Notifications v1 points at. | Clients v2 is held back: "Held back: Client reference, re-checked against the Notifications in place in the warehouse ...". The page shows the top notice (275), and the grid row has both results (272). | 267 c12, 272, 275, 276 |
| S1 step 4 | A person later promotes or rejects Notifications v2. | Promote: the knock-on re-checks Clients v2. Reject: nothing re-runs; the wording becomes "turned down" (Q10). | 267, 275 c6, 210 c6 |
| S2 | A first-time zip, both green. | Promoted together, with one verdict counted toward both, no re-run and one knock-on. The history row says "Promoted ... with ...". | 266, 269, 272 c20 |
| S2 strict | The same, with Notifications v2 red. | Clients v2 is re-checked against "no Notifications": red, held back. 204's package form shows on its page. One ticket, Notifications v2's, names Clients v2. In the queue, Clients v2 is beneath Notifications v2 and not counted. | 267, 204 c2, 278, 210 |
| S3, S2b | Staggered pairs; a correction after a strict hold-back. | The waiting partner joins the later file's gate application, and both promote together. | 267 c2-c3 |
| S3b | The earlier file is waiting on its own red. | It joins the gate application, is not promoting, and the arrival is re-checked against the warehouse. | 267 c2-c5 |
| S4 | A held-back partner's run. | Never counted toward the promoted supply. | 269 |
| S5 | A cascade. | A fixed point, the same outcome in any order. The terminal groups the result by root. | 267, 276 c5 |
| S6 (UX) | A chain: Investigations, then Notifications. | The grid row has Pass (staged) and Fail (warehouse), ending "why it is held back". The notice names the root, and the root's page lists everything it holds back. | 272, 275 |
| S6 (owe-nothing) | Case Workers sits a quarter out. | The quarter opens at filing and inherits; all five tables promote. | 271 |
| S7, S9 | A stale or refused carry-forward. | Warned on the dashboard, in the queue and in the door. A person carries it forward. | 271 c6-c8 |
| S10, S11 | Three staggered files; two that wait on each other. | All promote together at the last arrival. | 267 c2, tests |
| S14, S14b | One red Placements in a first-time six-table zip; the same zip without Placements. | Only Placements is held back; the other five promote. | 269 c4 |
| S15 | The early file in S10 is red for days. | Explained on the reader's page (204). The partner's page shows "Not due until ...". No ticket. | 204 c17, 278 c3 |
| S16 | A person promotes during a re-check. | Refused during the gate. Otherwise `promote()` re-confirms the read supplies and restarts the gate if they changed. | 266 c15-c16 |
| S17 | Inheriting at filing blocks a green resupply more often. | Recorded and accepted, as today's behaviour. | 271 decision |
| T14 | Re-filed partners. | Gated together through `recheck.execute`. | 267 c2 |
| Q5 | A knock-on owed overnight. | Red, worded "Not yet re-checked against ...". No ticket, no record. | 269 c5-c6, 272, 204 c7 |
| Cloud | Files uploaded separately to S3. | Each is a package of one and flickers. Recorded as a limitation; suppliers are told to upload a zip. | 266 c6, 274 |

## Carry-over check

### summary.md, "Keith's answers on v3, 2026-10-22 (Perth)" to the end

Every bullet, in order.

| Decision | Where in v4 |
|---|---|
| N1, the transitive group gate, at every gate entry; folds 268 and 267 c14; Q1 = Q2 = A | 267 c2-c3, d2-d4; 268 withdrawn; amendment of 121 d11 |
| Q13 = B (could-not-run counts only toward the declaring table; reverses v2 Q8; strict red still holds for the table that asks) | 269 c4, d2, S14 tests; 270 c1, d2; QAC-037 c7 amendment; 273 c4 (S14 pinned); 269 OQ1 (new consequence) |
| Q9 = A, "B later" (zip-only; cloud flicker a known limitation; guidance says zip; boundary later via #114) | 266 c6, d3, NFR; 274 c1-c3, d2 |
| Q3 = A (a crash waits and is owed, not a failure; the next pass re-runs it and gates together; a backstop refusal = held back) | 266 c3, c13, c14, d4, tests; 276 c11 |
| Q4 = B plus the warning, covering stale AND refused (confirmed) | 271 c5-c8, d2, tests |
| Q5 = A (red, worded; no notification unless the re-check fails; B rejected as half-and-half) | 269 c5-c6, d3; 272 c10, c13; 204 c7; 278 c5 |
| Q7 = A, plus a few gate-outcome scenarios (S1 green, S1 red, S2, S10, S14) | 273 c1-c4, d1-d2 |
| Q8 = A (beneath, not counted, "nothing needs deciding", not pickable, override by naming it; its own row once the package-mate is rejected; A' not taken) | 210 c2-c6, d2; 276 c3, d4 |
| Agreed batch: Q10 = A | 275 c6; 204 c16; 210 c6; 276 c3 |
| Agreed batch: Q6 = A | 278 (whole); 121 c12 and 083 c21 amendments |
| Agreed batch: a decision during the gate is refused (Keith's wording); `promote()` re-confirms under the slot locks | 266 c15-c16, d7; 276 c10 |
| Agreed batch: the joint-promotion history row (replaces S5's "cleared" note) | 266 c10; 272 c20 |
| Q11 = A (follow the newest supply; one card line per held-back delivery, at most three names) | 275 c4-c5, d3; 272 d (rollups) |
| Q12 = A (every row says what it read; structured; as-at; two exempt kinds) | 272 c7-c8, c12-c13, d3 |
| S1-red top line = A (`.notice-exhausted role=status`, no "not a fault" clause) | 275 c1, d1 |
| S2 wording = yes (amends Keith's v2 Q10 wording for this case) | 204 c2, d7 |
| "In place" becomes "in place in the warehouse", as its own requirement; the picker label is open | REQ-DASH-277; open question A; all v4 wording uses it |
| S6 row display = A (show both; the staging result first, then the re-check "why held back"; the row's status is the gate's) | 272 c9, d4 |
| Keith's density concern | 272 d5 (quoted), NFR "Density" |
| "S6 root naming NOT yet answered", then answered A | 275 c2-c3, c7, d2 |
| Row density: first "NOT decided" (correction), then **Option C, "with stacked results on phone"** | 272 c6-c16, d5; the 264 c2, c7 and NFR 2 amendments. The "not decided" bullet is superseded by the later bullet and the coordinator's update; nothing from Option A is in v4 |
| N1 (a partner not due yet) = A, the muted line; the reader's red unchanged; should not page anyone; "A" given once to two questions, to confirm | 204 c17, d9; 270 NFR 3; 278 c3 |
| How Keith will sign v4 off | The top of this file; the walk-through draft below |

### review-architect-v3-draft.md

| Finding | Where in v4 |
|---|---|
| B2 partly: the re-check executor is a fourth gate | 267 c2 (`recheck.execute`), d4; T14 test |
| B4: single arrival only | 267 c2-c3 (one rule) |
| T2: 271 c5-c6 pending Q4; T18 open | 271 (Q4 = B); T18 is 271 OQ1 / open question C |
| T3: 266 c10 plus Q6, matters more under N2 | 266 c11; 278 |
| 268 correct for two tables | Folded (267 d3) |
| n-1 rounds and order-independence need "over the whole set at once" and two-table checks | 267 c7; d6 (accepted limit) |
| Holding a failing pair together: record it as a decision | 267 d5 |
| 271 mechanically fine; nothing assumes a period holds a promotion | 271 d4, d5 |
| Pins (262 c12, TS-63, GEN-251 c3) at risk; a generator fix, not a re-pin | 271 c9, d7; 273 c6 |
| N3: refusals written when final; keep hide-until-settled; the owed package gate's cause | 266 c3, c9, d5; 267 c10-c11 |
| T13: refuse a decision during the gate; `promote()` re-confirms under the slot locks | 266 c15-c16 |
| N1 BLOCKER (S10, S11) | 267 c2-c3, S10/S11 tests |
| N2, so Q13 | 269 c4 (B) |
| S14, S14b | 269 tests; 273 c4 |
| S15 (red for days) | 270 NFR 3; 204 c17; 278 c3 |
| S16 | 266 c16, test |
| S17 | 271 d6 |
| Recommendations: Q1 "A, transitively"; Q13 B; Q4 A with a pin warning; Q6 A | Q1 and Q13 taken. Q4: Keith chose B (the pin warning is kept, 271 c9). Q6 taken |
| Build order: N1 in the same push; N3's schema with 266 | Build order above |

### review-cli-ux-v3-draft.md

| Finding | Where in v4 |
|---|---|
| 267 c11: count toward `has_failures`/`PassReport.red`, keep the `exit_status` precedence, failing-first test | 276 c2, d2, test |
| 266 c5 landed | 266 c5 (kept) |
| 267 c12: the condition and the named surfaces | 276 c3, d3 |
| Vocabulary: "held back", action `promotion-withheld`, no "Refused:" | 266 c9, d6; 267 c12; 276 c1 |
| Never under "Held - no period yet"; a NO_COLOR/pipe test per surface | 276 c1, c13 |
| The locus clause "This supply's own checks passed." | 267 c12; 276 c4 |
| `describe()` has no text for the new reason | 270 c5, d4 |
| Terminal grouping at ~30 datasets (`_grouped`) | 276 c5 |
| The c15 override text misses T13/S5; the line when promoting the cause | 276 c7, c8, d5 |
| N1: the knock-on report lists every supply re-gated | 276 c9 |
| N2: a cascade in the queue, flat under the root | 210 c2, d4 |
| N3: refuse before the reason prompt | 266 c15; 276 c10 (Keith's wording, "still being checked") |
| N4: crashed-sibling wording | 276 c11 |
| N5: warn when re-filing one sibling | 276 c12 |
| Q8: A' recommended | Not taken: Keith chose A (210 d2, 276 d4) |
| Q10 A; "refuse" for a decision during the gate | Taken (above) |

### review-dashboard-ux-v3-draft.md

| Finding | Where in v4 |
|---|---|
| The card line had no criterion | 275 c4 |
| S6 root and chain | 275 c2-c3 |
| S5's "cleared" note | Replaced by the joint-promotion row, 272 c20 |
| Names as real links via `navHref`/`affectsLinks`, keeping in-place-on | 272 c15; 275 c7; 204 c5 |
| D1, the red-promoted text printed twice | 272 c2 (removed), d6 |
| D2, `fmtInstant` and `STATUS_LABEL` formats | 272 c1 example |
| D3, "held back", "received `<instant>`", "Held back together/with" | Throughout; 275 d5 |
| D4, a "nothing in place" form; no "Read against" where c4's sentence applies | 272 c8, c12, c13 |
| D5, the S1-red top-line contradiction | 275 c1, d1 (Keith = A) |
| Wordings: S1-red row, S2 row, S1-red top, S2 204 c2 | 272 c13; 275 c1; 204 c2 |
| N1, the partner not yet due | 204 c17 |
| N2, the owed re-check wording, no notification | 269 c5-c6; 272 c10, c13; 204 c7; 278 c5 |
| N3, the history row | 272 c20 |
| N4, an inherited supply in the clause (`promotionStateOn`) | 272 c4, d7 |
| N5, a hand promotion names who | 272 c3, d8 |
| Questions 1-8 | All answered by Keith; each is mapped above |

### review-dashboard-ux-v3-density.md

| Finding | Where in v4 |
|---|---|
| About two thirds of the section is repetition; five relationships | 272 NFR "Density" |
| A row is a `<button>` and cannot contain links | 272 c12 (the check's name is the control; nothing nested) |
| Option A, B or C | **C chosen** (Keith, "with stacked results on phone"); 272 c6-c16, d5 |
| C's caution: most rows fill one column; at 375px the columns stack | Accepted (272 d5); stacking with the pill visible is 272 c16 and its test |
| Criteria to amend: 264 M4, c7, NFR 2; 272 c4-c6 | 264 c2, c7 and NFR 2 amended; "M4" not found (see above); 272 rewritten |
| "In place in the warehouse" adds about 17 characters | 277 NFR "Length"; in C the long sentences sit in the panel |

### Items v3 left for sign-off or for the architect

- **Terminology:** settled as "held back" (Keith's own answers use it).
- **The staging view made precise** (267 d12): to confirm at the
  walk-through.
- **Case 3a** (a reader of a slot accepted as "not supplied" stays red; v2
  Q5 = A, by analogy): to confirm at the walk-through. Under Q13 = B, the
  table that stays red is the reader that declares the check.
- **v3's 267 OQ2** (the overlay; a readers-only run caused by a refusal):
  answered by N3, 267 c10.
- **v3's 271 OQ2:** answered by the architect.
- **A build during a cascade:** 267 c11 kept.
- **The fixed point's order-independence:** 267 c7.
- **T18:** still open (question C).

**Nothing is left only in prose**, apart from the open questions below.

## Non-functional angles

**Answered in the requirements:**
- Performance: the cascade is bounded, and joining a waiting supply costs
  no run. The grid is computed at build.
- Scalability at ~30 collections:
  - one connected set per collection and period;
  - one card line per delivery;
  - one ticket per root cause;
  - one grid row per relationship.
- Reliability: crash and backstop (Q3); interrupted packages; owed items
  with causes.
- Concurrency: the refusal during a gate, and the re-confirm under locks.
- Determinism and replay.
- Auditability: `promotion-withheld` fields, and the joint-promotion record.
- Observability and noise: no tickets for reds that clear by themselves.
- Accessibility: words and icons, a key for the marks, the accessible name,
  nothing nested inside a button.
- Compatibility:
  - `in-place-on` and the ids are kept;
  - snapshots keep their own day's wording;
  - the cloud path's limitation is recorded.
- Maintainability: one selection function, and one root-cause function
  shared by the page, the queue and the tickets.

**Ruled out as not applying:**
- Security: no new capability; overrides keep their allowlist, actor and
  reason.
- Privacy: only ids, periods and table names.
- Compliance and retention: no new data class.
- Cost: cross-table re-runs only, and no clock sweep. Five more scripted
  scenarios add some bootstrap time, measured at build.

**Put to Keith:** no new NFR question this round. Every NFR fork was in
Keith's 2026-10-22 answers (Q3, Q5, Q6, N1).

## Open questions

Each is framed in a scenario, with the recommendation first. **B is new this
round**, because it arises from Q13 = B. A was raised by Keith himself. C, D
and E are carried over unanswered from earlier rounds.

- **A. The date control's label (REQ-DASH-277).** A reader sees the button
  "📅 In place on: 22 October 2026". "In place in the warehouse on" is long
  for the page's narrowest control.
  - **Recommended:** "In the warehouse on". Keep the element ids and the
    `in-place-on` query parameter, which amends REQ-PIPE-081 c23 so that the
    ids need not follow the label. No link breaks.
  - **Alternatives:**
    - "In place in the warehouse on" in full.
    - Keep "In place on" for this one control.
    - Rename the ids and the parameter too, which needs a second old-link
      redirect (c24).
  - Note: summary.md named this REQ-PIPE-081 c6. It is c20.
- **B. A held table's own page after Q13 = B (REQ-PIPE-269 OQ1). NEW.**
  - Scenario: Clients is held with no period. Notifications' Client
    reference could not run in Notifications' own run. Today REQ-DASH-264
    c3-c5 show those rows on Clients' page, and they turn its cross-table
    pill red. Under Q13 = B, they count only toward Notifications.
  - **Recommended:** still show the rows on Clients' page, because they
    explain why its readers are red, but leave them out of its pill. Its
    status is red anyway (REQ-PIPE-115 c10). This adds one clause to 264
    c5.
  - **Alternative:** drop them from Clients' page, which hides the cause
    from the table that causes it.
- **C. T18: a period before a partner's participation starts
  (REQ-PIPE-271 OQ1).**
  - Scenario: a dataset joins the agreement from 2025-Q1, and a reader's
    check of it runs in 2024-Q4. There is nothing to inherit, and there
    never will be.
  - **Recommended:** the check is out of scope where the table it reads is
    not owed and has never been supplied. That is the agreement, not an
    absence, so the check records neither red nor a result.
  - **Alternative:** keep it red, and let a person promote each such period
    by hand.
- **D. Where the supplier guidance lives (REQ-DOCS-274).**
  - **Recommended:** a short new `docs/supplier-guidance.md`, linked from
    `docs/delivery-format.md` and the AWS design doc.
  - **Alternatives:** a section of `docs/delivery-format.md`, or wait for
    the transport layer.
- **E. Two follow-ups to F6 on REQ-PIPE-210.**
  - (1) Scenario: Notifications v2 is red only because Clients is overdue,
    and has nothing in the queue to sit beneath. **Recommended:** not
    counted, with a line under the count.
  - (2) **Recommended:** the dashboard's cards count the same way, through
    the same function.

**To confirm at the walk-through** (my readings of Keith's answers, not new
forks):
- N1's single "A" is recorded for both of the questions it answered.
- Q5's "no notification" is taken as no ticket and no still-failing record,
  plus a structured reason that #113 can use.
- Keith's "S2" scenario pin is taken as S2 strict, because the both-green
  zip pins nothing new.
- The staging view made precise (267 d12).
- Case 3a.

**For the reviewers, not for Keith:**
- 272 OQ1 (dashboard UX): on an in-warehouse page the staged column is all
  dashes. Keep it, or drop it?
- What the density review meant by "264 M4".
- 267 OQ1 (architect): pin the replacement setting in the tests.
- 204 OQ1 (check at build): the overdue cause's notice.

## Sign-off brief, per requirement (plain prose for reading to Keith)

**REQ-PIPE-266: files that arrive together are gated together** (must)
- **Story.** So that no file gets in on a verdict about a file that then
  doesn't, a zip's files wait until all of them have been checked, then are
  decided together.
- **What it does.**
  - A package is the files sharing one receipt instant. On the cloud path,
    every file is its own package for now.
  - Nothing in a package is promoted or held back until the last file is
    checked.
  - If one file's run crashes, the package waits and the next pass finishes
    it. If the agreement backstop refuses one file, that file counts as held
    back and the others go on.
  - Each file held back is written to the log as "promotion withheld" as
    soon as that is final.
  - Each promotion names what it was promoted with.
  - A person can't make a decision while the package is still being gated:
    "The delivery received ... is still being checked (1 of 2 files
    checked); decide once it is gated."
  - If something moves under a person's promotion, the gate starts again.
  - No checkpoint falls inside a package.
- **NFRs.** No half-and-half view. No flickering reds. A crash waits.
  Decisions come from the record, so a replay matches. One query answers
  "what was gated together".

**REQ-PIPE-267: the gate judges against what the warehouse will hold, and
connected files go in together** (must)
- **Story.** A file is promoted only on verdicts about the tables it will
  actually sit beside. Files that depend on each other go in together or
  not at all.
- **What it does.**
  - A gate considers the new files plus every waiting file in the period
    connected to them by a recorded cross-table result, however far the
    chain goes.
  - A waiting file is never re-run. Its recorded results decide whether it
    can come in.
  - When one file is held back, the others' cross-table checks are re-run
    against what is in the warehouse, until nothing changes. The result is
    the same in any order.
  - A held-back file's log entry says which check, checked against what, and
    because of which file. "This supply's own checks passed" is added where
    true.
  - So: two or three staggered files go in together when the last one
    lands; re-filed partners go in together; and S1 works as Keith
    described.
- **NFRs.** No half-and-half view. No false green. No deadlock between clean
  files. Bounded rounds. Deterministic.

**REQ-PIPE-269: what counts toward a supply's status** (must)
- **Story.** A promoted table's status is about what is actually beside it
  in the warehouse. A check that couldn't run is held against the table
  that asked the question, and only that table.
- **What it does.**
  - A result counts toward a promoted supply only if everything it read is
    still in the warehouse. So a bad file that was held back can't turn the
    promoted partner red.
  - A check that couldn't run counts only against the table that declares
    it. One bad Placements file no longer holds back the whole quarter.
  - If a re-check owed by a promotion hasn't run yet, the supply reads red
    ("not yet re-checked"), but no ticket or record is raised.
  - The same function is used everywhere.
- **NFRs.** No false green or false red. Proportionate strictness. Computed
  at build from the log and results only.

**REQ-PIPE-270: a check that cannot read a table is red** (must)
- **Story.** Nothing reads green that nobody could check.
- **What it does.**
  - A cross-table check that could not read a partner is red for the table
    asking, whatever the reason, "not yet due" included.
  - The reason is kept as a code: when the partner falls due, or "held back
    with its package".
  - Every reason has its own description in the terminal.
  - Inherited tables count as readable.
  - A person can still promote over it.
- **NFRs.** Flicker is accepted for staggered files. A partner that is
  merely not due yet pages nobody.

**REQ-PIPE-271: a quarter opens when it is first filed, and warns when its
carry-forward goes stale** (must)
- **Story.** A quarter in which a table owes nothing doesn't deadlock, and
  nothing carried forward goes quietly stale.
- **What it does.**
  - The first filing opens the quarter and makes its inheritances, before
    any check runs.
  - Inheritance happens once and is never retried or re-pointed
    automatically.
  - When a newer supply is promoted into an earlier quarter, a warning
    appears in the log, on the dataset's page and card, and in the
    terminal's queue and door. It says a newer supply could be carried
    forward, or that nothing was carried forward when one now could be, and
    how a person does it.
  - The warning clears only once that is no longer true.
- **NFRs.** No deadlock. No silent staleness. Deterministic replay.

**REQ-DASH-272: the page shows both views** (must)
- **Story.** Tell "a bad file is waiting" apart from "the warehouse is
  broken" at a glance, with the full explanation one click away for
  engineers.
- **What it does.**
  - The awaiting line ends with "The supply in place in the warehouse is the
    one received ..., and is Green." This covers inherited, red-promoted,
    turned-red (naming who) and nothing-in-the-warehouse.
  - The cross-table checks become a grid, one row per check, with columns
    "Against what's staged" and "Against what's in the warehouse". Each cell
    shows Pass or Fail, a tick or cross per tool, and which supply was read.
    A dash means no result.
  - Where the two results differ, both show, and the warehouse one says
    "why it is held back". The row's pill is the gate's.
  - A key line explains the marks. Selecting a check opens each tool's full
    result and the full "Read against ..." or "Re-checked ..." sentences,
    which the screen reader also gets.
  - On a phone, the two results stack under the check's name, with the pill
    kept visible.
  - The supply history says "Promoted ... with the Notifications supply
    received ..., by the rule".
- **NFRs.** No false green or false alarm. Accessible: words, icons and a
  key, never colour alone. Computed at build. One row per relationship at
  ~30 collections.

**REQ-GEN-273: the synthetic history checks files and gates separately**
(must)
- **Story.** The bootstrap doesn't fail because a green file was held back
  by its partner, but the gate's own decisions are still pinned.
- **What it does.**
  - Targets are compared with each file's own checks, leaving out checks
    that couldn't run and re-checks a partner caused. Those differences are
    reported, not failed on.
  - Five new scripted scenarios declare what the gate should decide: S1
    green, S1 red, S2 strict, the three-file chain, and the Placements case.
    The bootstrap fails if the gate decides otherwise.
  - Changed pins come to Keith.
- **NFRs.** No masked defect. Deterministic.

**REQ-DOCS-274: tell suppliers to send one zip** (should)
- **Story.** Suppliers avoid the flicker.
- **What it does.** The guidance says to send a delivery's files as one zip,
  on the cloud path too, and that separately sent files may read red until
  the rest arrive.
- **Open.** Where it lives (D).

**REQ-DASH-275: a supply held back with its delivery says so** (must, new)
- **Story.** The reader goes straight to the one decision that clears the
  delivery.
- **What it does.**
  - S1 red shows a notice at the top: "Held back with the Notifications
    received with it. That file ... was held back, so this supply was
    re-checked against the Notifications in place in the warehouse, and 1
    cross-table check fails against it. It is checked again by itself once a
    Notifications supply is promoted."
  - A longer chain names its root: "Held back with its delivery: the
    Investigations file was held back, and the Notifications with it." The
    root's page lists everything it holds back.
  - Cards show one line per delivery: "Held back together: Notifications,
    Client Register (one delivery, received ...)".
  - Once the root is turned down, the wording says so.
  - Every name is a link that keeps the date.
- **NFRs.** One line per delivery. No false quiet. No dead ends.

**REQ-PIPE-276: what the terminal says** (must, new)
- **Story.** Decide the one thing that matters, and never be surprised by
  what the rule does next.
- **What it does.**
  - The terminal always says "held back".
  - A re-check's red makes `qa` exit 1, as any red does.
  - The next step names the partner's decision while it is still waiting,
    and the supply's own decision once the partner is turned down.
  - Results are grouped by root, showing final states only.
  - Before an override, the terminal warns what it will re-check, and says
    when a re-check is likely to come out worse.
  - After a decision, it lists every supply the rule re-gated.
  - It explains a crashed sibling, warns when only part of a package is
    re-filed, and works under NO_COLOR and when piped.
- **NFRs.** One vocabulary. Exit codes keep their precedence. Nothing is
  widened.

**REQ-DASH-277: "in place" says where** (should, new)
- **Story.** Nobody has to guess whether a supply is actually in the
  warehouse.
- **What it does.**
  - Every shown "in place" becomes "in place in the warehouse": about
    fourteen lines of the page and five of the terminal. The raw 33 and 12
    included comments and "in place of".
  - The date control's label is open (A).
  - Ids, links and code names are unchanged.
  - Five signed criteria's quoted wording is amended.
  - A browser test confirms no shown "in place" is left bare.
- **NFRs.** Links keep working. Snapshots keep their own day's wording.

**REQ-PIPE-278: one shout per root cause** (must, new)
- **Story.** One bad file doesn't raise a ticket for every table that reads
  it.
- **What it does.**
  - A supply red only because of another table gets no ticket or
    still-failing record of its own. The root's ticket and record name it.
  - A partner that is merely not due yet raises nothing until it is overdue.
  - An owed re-check raises nothing.
  - A supply with its own fault is still ticketed.
- **NFRs.** No ticket storm. No flickering reds. The page, queue and
  tickets name the same root.

**REQ-DASH-204: a check that could not run because another table is absent
says so** (must, re-folded)
- **What it does.** One notice at the top, one line per missing table:
  - "No promoted Notifications for 2024-Q3. 3 of this supply's checks need
    it, so they could not run. That is not a fault in this supply's own
    data. They run again by themselves once a 2024-Q3 Notifications supply
    is promoted."
  - Where the cause is a package-mate held back: "The Notifications received
    with this supply (...) was held back, so 3 of this supply's checks could
    not run ...".
  - A pending re-check reads "Not yet re-checked against the Notifications
    promoted ...".
  - The partner's page says "Not due until ... — the Client Register is
    waiting on it".
  - Nothing implies the reader is otherwise fine.

**REQ-PIPE-210: the queue** (should, re-folded)
- **What it does.**
  - A supply held back only by another is listed beneath that cause (flat
    under the root of a chain). It is not counted, it says nothing needs
    deciding, and it is not pickable from the queue line. Overriding it
    means naming it in `supply decide`.
  - Once the cause is turned down, it becomes its own counted row, worded
    from the log.
- **Open.** E.

### A draft of the walk-through Keith asked for (to finalise after the reviews)

S1. 2024-Q3 holds Clients v1 and Notifications v1, both green. A zip
arrives with Clients v2 and Notifications v2.

1. Clients v2 is checked. Its result, Client reference against the staged
   Notifications v2, is green. Nothing is decided yet, and the terminal
   says "checked, waiting for its package (1 of 2)".
2. Notifications v2 is checked. It is red on blank values of its own.
3. The package is gated as one gate application. Notifications v2 is held
   back, and the log records "promotion withheld" with its own reasons.
4. Client reference is re-run for Clients v2 against Notifications v1, the
   one in the warehouse.
   - **Green:** Clients v2 is promoted. The warehouse holds Clients v2 and
     Notifications v1, and that pair has been checked.
   - **Red:** Clients v2 is held back. Its log entry, notice and grid row
     all say it was re-checked against the Notifications in the warehouse
     because the Notifications received with it was held back.
5. On the dashboard, Notifications' page reads "Awaiting a decision ... The
   supply in place in the warehouse is the one received ..., and is Green."
   The Child Protection card shows one line, "Held back together ...".
6. One ticket is raised, for Notifications v2. In the red branch it names
   Clients v2. In the terminal queue, Clients v2 sits beneath Notifications
   v2 and is not counted.
7. Later:
   - A person promotes Notifications v2, and the knock-on re-checks Clients
     v2 (which may then promote).
   - Or a person rejects Notifications v2. Nothing re-runs, and Clients v2
     "now needs its own decision".

## Draft entry for plans/running-thoughts.md #95 (for a human to apply)

> Append to #95: "**v4, 2026-10-22**: Keith's 2026-10-22 answers and the four reviews of v3 are folded into `docs/drafts/unjudged-cross-table/summary-v4.md` and `requirements-draft-v4.yaml` (unsigned). The changes:
> - a transitive group gate (REQ-PIPE-268 withdrawn into REQ-PIPE-267);
> - a could-not-run counts only against the declaring table (Q13 = B);
> - carry forward once, with a stale/refused warning (Q4 = B);
> - the cross-table grid, Option C;
> - four new requirements: REQ-DASH-275 held back with its delivery, REQ-PIPE-276 terminal, REQ-DASH-277 'in place in the warehouse' (#116), and REQ-PIPE-278 one shout per root cause;
> - REQ-DASH-204 and REQ-PIPE-210 re-folded.
>
> Next: the architect, both UX reviewers, then Keith's S1 walk-through. Five open questions are listed (A to E), and one of them (B) is new."

And for #116: "Scoped 2026-10-22 as REQ-DASH-277 (unsigned) in the #95 v4 batch. The date control's label is open."

## Validation

- `uv run mothman dashboard validate-requirements --draft docs/drafts/unjudged-cross-table/requirements-draft-v4.yaml`, run alone, reports only `dependencies entry ... does not match any real requirement id in this file` errors. Each one is a dependency on a requirement outside the draft, which is expected. No other kind of error is reported.
- `requirements.yaml` was merged with the close-out draft's REQ-GEN-206 and REQ-PIPE-211, and with all fourteen v4 requirements (v4's REQ-DASH-204 and REQ-PIPE-210 replace the close-out versions). The result is in the scratchpad as `merged95v4.yaml`. The validator reports: **"requirements validation OK - 264 requirements, zero errors."**
- `yaml.safe_load` reads the v4 file back with all fourteen requirements. Every acceptance criterion, NFR, decision and open question is a string, and none carries `signed_off`.
