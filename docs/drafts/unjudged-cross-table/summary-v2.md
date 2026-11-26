# Unjudged cross-table checks (#95): draft v2, for sign-off

Re-drafted by delivery-scoper on 2026-10-20, with all ten of Keith's answers
(summary.md, end) folded in. This is still a **proposal**. Nothing in it is in
`requirements.yaml` and nothing is signed. The requirements are in
`requirements-draft.yaml` next to this file, which has been overwritten; v1 is
in git history. `summary.md` and `review-architect.md` are left as they were,
as history.

The draft now also carries the close-out batch's **REQ-DASH-204, REQ-PIPE-210
and REQ-PIPE-211**, re-folded for the new status. They supersede the versions
in `docs/drafts/calendar-close-out/requirements-draft.yaml`.

## What changed since 2026-10-14

1. **Incomplete promotes itself (Q2 = B).** v1 had an Incomplete supply wait
   for its partner. Now it promotes, recorded as "Incomplete promoted", and is
   checked again when the missing table arrives or is promoted. Two things
   follow:
   - The false green is fixed by the **label**, not by holding the supply
     back. Case 1 still promotes, but it reads Incomplete, not green.
   - The false red is fixed by the **status**. Readers with no fault of their
     own were held as red; now they promote as Incomplete.
2. **Most of the architect's two blockers go away.**
   - **B1 (deadlock):** nothing waits on a partner any more.
   - **B2 (every early arrival "awaiting a decision"):** nothing that is only
     Incomplete is waiting.
   - So there is no new slot state, no withheld record, and no amendment to
     REQ-PIPE-121's rule that "a file landing in staging stays outside this
     mechanism". The architect still has to confirm this (see below).
3. **One new fork came out of self-promotion (Q11).** Incomplete ranks above
   amber. If the gate went on that ranking alone, an amber supply whose
   dataset says "hold" would promote whenever a partner table was missing. I
   recommend the gate decides on the status of the checks that actually ran.
4. **Case 9 is rewritten for Q4 = A.** A dependency arrives after the reader
   and is red. Its own arrival run checks the reader against it. If that
   cross-table check passes, the reader takes that verdict, not Incomplete. v1
   contradicted Keith's answer here (architect H1).
5. **REQ-PIPE-265 fits, and adds a case.** Its 312 staggered same-day pairs are
   #95's false green. This is new **case 16**: the earlier table promotes as
   Incomplete, and the later table's arrival run supplies the verdict. On the
   page, that day reads as the verdict (REQ-DASH-264 criterion 11). The
   Incomplete moment stays in the decision log.
6. **REQ-DASH-264 is amended (new today).**
   - On the missing table's page, a reader's could-not-run row keeps "Could
     not be checked ...", and its pill reads Incomplete.
   - The row counts toward the cross-table section's pill, but never toward
     that table's own status.
7. **REQ-DASH-126 criterion 5 does need amending after all.** v1 said it
   didn't. That was wrong: criterion 5 says nothing extra is shown beside a
   promoted supply that is not red.
8. **The close-out batch is re-folded.**
   - **REQ-DASH-204:** one wording, "No promoted `<dataset>` for `<period>`".
     The line now also shows for a table that is not yet due. The per-table
     reason codes and the old criterion 16 are dropped.
   - **REQ-PIPE-210:** shrinks to "a reader red in its own right also names
     the other table". Whether to keep it at all is Q12.
   - **REQ-PIPE-211:** stays a must, as drafted (Q9 = B). Only words that said
     "red" changed, and the B1 fix now comes from REQ-PIPE-215.

## The requirements

| Id | MoSCoW | What it covers |
|---|---|---|
| REQ-QAC-212 | must | The Incomplete status. It sits between amber and red; the Python and JS versions must agree, and both orderings are renumbered the same way. Drift checks and trials don't use it. |
| REQ-PIPE-213 | must | Every not-evaluated cross-table record reads Incomplete. It counts toward the tables it could read, never the one it couldn't. There is one shared function for "which tables couldn't it read". Covers cases 1, 4-8, 12, 14 and 15. Amends six signed requirements. |
| REQ-PIPE-214 | must | An Incomplete supply promotes itself, recorded as "Incomplete promoted". The gate decides on the checks that ran (Q11), and a person can still demote it. Covers cases 1, 3, 3a, 4 and 17. Amends REQ-PIPE-075. |
| REQ-PIPE-215 | must | When a reader is checked again: something moves, never the clock. Includes the general B1 fix. Covers cases 2, 9, 10, 11, 13 and 16. Amends REQ-PIPE-121 c1 and NFR 4, folded with 211 so c1 changes once. |
| REQ-DASH-216 | must | The pill "Incomplete: no promoted `<table>`", the "Incomplete promoted" label and the counts, with real-browser tests. Amends REQ-DASH-126 c5 and REQ-DASH-264 c5-7. |
| REQ-PIPE-217 | should | No "still failing" record and no ticket for something that is only Incomplete (R2). No amendments are needed. |
| REQ-DASH-204 | must | The line at the top of the reader's page, "No promoted `<dataset>` for `<period>`", linked, plus "Affects" and one line on the collection card. Re-folded. |
| REQ-PIPE-210 | should | The terminal queue names the other table beside a supply that waits for its own reasons. Reduced; Q12. |
| REQ-PIPE-211 | must | Settling a contested pair re-checks its readers. As drafted, with wording updates. |

Suggested build order, as one sprint (the architect's "fixed order"; the
architect should confirm it): 212, 213, 214, 215, 217, 211, 216, 204, 210. The
close-out batch's REQ-GEN-206 (TS-81, "reject both") then writes its expected
result as "Incomplete promoted".

## Every case, today and under v2

All tests are in `tests/test_incomplete_cross_table.py` unless another file is
named. Each is written first and seen to fail the way today's code reads.

| # | Case | Reads today | Under v2 | Where |
|---|---|---|---|---|
| 1 | Dependency not yet due when the reader runs | **Green**, promoted (decision 103) | Incomplete, promoted as "Incomplete promoted" | 213 c11; 214 c10; 216 c9 |
| 2 | ...then the dependency goes overdue | Green, never checked again | Still Incomplete, not re-run | 215 c6 |
| 3 | ...the dependency never arrives | Green for good | Incomplete until the table is promoted, substituted or inherited | 214 c12 |
| 3a | ...the slot is accepted as not supplied | Green | Stays Incomplete (Q5 = A) | 214 c13 |
| 4 | Dependency overdue, no fault of the reader's own | **Red**, withheld, and a "still failing" record | Incomplete promoted; no record | 213 c12; 214 c11; 217 c4; 216 c9 |
| 5 | Dependency staged and awaiting a decision | Red | Incomplete | 213 c13 |
| 6 | Dependency contested | Red | Incomplete | 213 c14 |
| 7 | Dependency could not be loaded | Red | Incomplete | 213 c15 |
| 8 | Dependency held with no period | Red | Incomplete | 213 c16 |
| 9 | Dependency arrives later and is red | Whatever its first run recorded | The verdict the dependency's own run reached against it (Q4 = A) | 215 c7 |
| 10 | The staged dependency the reader read is rejected | The verdict on rejected data stands | Re-checked; reads Incomplete (or "Incomplete promoted") | 215 c8; 216 c10 |
| 11 | A knock-on that leaves the period holding nothing | Only re-gated (B1) | Re-run | 215 c9 (H5 rewrite) |
| 12 | Siblings re-filed together | Red, and a "still failing" record | Incomplete; no record | 213 c17; 217 c4 |
| 13 | The staged dependency is superseded by a file that can't be read | Not re-checked | Re-checked; reads Incomplete | 215 c10 (H5 rewrite) |
| 14 | The other side of the check (Q8 = A) | Green | Incomplete | 213 c18 |
| 15 | The missing table's own status | Coloured by its readers | Not counted; its readers' rows show Incomplete | 213 c19; 216 c11 |
| 16 | A staggered pair (REQ-PIPE-265's 312) | Earlier table promoted on a nodata read as green | Incomplete promoted, then the verdict once the later table arrives | 215 c11 |
| 17 | Amber under "hold", plus a missing table | (new) | Waits as amber, reads Incomplete (Q11) | 214 c14 |
| R2 | A table that never arrived vs. a "reject both" pair | Different: one gets a log record, the other nothing | The same: Incomplete promoted, no record | 217 c5 |

## Amendments to signed requirements: exact wording for Keith's approval

`<date>` is filled in by whoever builds it. I've given only the changed
criterion. Every one is a proposal.

**REQ-PIPE-079** (signed 2026-09-26)
- **c4 OLD:** "WHERE a check cannot run because a table it depends on has no promoted supply for the period, and none of the more specific cases in this requirement applies, THE SYSTEM SHALL report it red, SHALL name the table responsible, and SHALL say that table has no filled slot in this period and is not in the delivery under test."
  **NEW:** "WHERE a check cannot run because a table it depends on has no supply for the period that the run can read - none promoted, and none staged that it can read (REQ-PIPE-105 criterion 5) - and none of the more specific cases in this requirement applies, THE SYSTEM SHALL record it not evaluated, reading INCOMPLETE (REQ-PIPE-213), SHALL name the table responsible, and SHALL say that table has no filled slot in this period and is not in the delivery under test. AMENDED `<date>` by REQ-PIPE-213."
- **c14 OLD:** "...THE SYSTEM SHALL NOT report the check red, and SHALL say the table has not been supplied for this period yet and is not yet overdue."
  **NEW:** "WHERE a table a check reads has no promoted supply for the period and that period's slot for it is neither past due nor closed, THE SYSTEM SHALL record the check not evaluated, reading INCOMPLETE (REQ-PIPE-213) - neither red nor no data - and SHALL say the table has not been supplied for this period yet and is not yet overdue. AMENDED `<date>` by REQ-PIPE-213."
- **c15 NEW:** "IF a table a check reads has no promoted supply and its slot for that period is PAST DUE, THEN THE SYSTEM SHALL record the check not evaluated, reading INCOMPLETE (REQ-PIPE-213), and SHALL say the table is overdue for the period. AMENDED `<date>` by REQ-PIPE-213." (Was: "report the check red".)
- **c16 NEW:** "IF a table a check reads has no promoted supply WHILE a supply for it is staged awaiting a decision, THEN THE SYSTEM SHALL record the check not evaluated, reading INCOMPLETE (REQ-PIPE-213), and SHALL say a supply is staged awaiting a decision, distinctly from the case where no supply exists at all. AMENDED `<date>` by REQ-PIPE-213." (Was: "report the check red". The architect's open question on REQ-PIPE-215 may lead to a further change here.)

**REQ-PIPE-105 c13** (signed 2026-09-28). **NEW:** "WHERE a cross-table check cannot read a table because no supply has been promoted into that period, THE SYSTEM SHALL make plain that the check reads INCOMPLETE for want of a promoted table (REQ-PIPE-213) rather than because of anything in the data. AMENDED `<date>` by REQ-PIPE-213." (Was: "is red for want of".)

**REQ-PIPE-115** (signed 2026-10-04)
- **c14 NEW:** "...THE SYSTEM SHALL record that check as not evaluated, reading INCOMPLETE (REQ-PIPE-213), in the run of the dataset the check belongs to, giving held or contested as the reason and naming the supply. AMENDED `<date>` by REQ-PIPE-213." (Was: "not evaluated, red".) Everything before "THE SYSTEM SHALL" is unchanged.
- **c20 NEW:** "THE SYSTEM SHALL have a test that drives the real Child Protection orchestrator with an unreadable sibling whose slot for the run's period is, in turn, not yet due, overdue, and holding a supply awaiting a decision, and asserts at qa.check_result that each records its own reason code rather than the catch-all, and that each reads INCOMPLETE (REQ-PIPE-213). AMENDED `<date>` by REQ-PIPE-213: these read nodata for not yet due and red for the other two."
- **Decision "NOT-EVALUATED STAYS DISTINGUISHABLE IN THE RECORD":** append "SUPERSEDED `<date>` IN ITS STATUS CLAUSE by REQ-PIPE-213 (Keith, 2026-10-20, #95 Q1): a not-evaluated cross-table record reads INCOMPLETE, a status of its own; the pseudo-tool, label, reason code and reason text stand."

**REQ-PIPE-078 c10** (signed 2026-09-26). **NEW:** "WHERE a cross-table check reads a held table, THE SYSTEM SHALL record that check as not evaluated, reading INCOMPLETE (REQ-PIPE-213), and SHALL name the held table as the reason. AMENDED `<date>` by REQ-PIPE-213." (Was: "report that check as red".)

**REQ-QAC-037 c7** (signed 2026-09-23). **NEW:** "THE SYSTEM SHALL fold a cross-table check's verdict into the status of every dataset it reads, whether that check failed or could not run - a check that could not run reads INCOMPLETE for the datasets whose tables it could read and is not counted toward a dataset whose table it could not read (REQ-PIPE-213) - and SHALL NOT leave a participating dataset reading green while a check counted toward it reads red or INCOMPLETE. AMENDED `<date>` by REQ-PIPE-213."

**REQ-PIPE-075** (signed 2026-09-26). These are new in v2. They replace v1's change to c3, which now stays as it is. c1 and c2 depend on Q11 = A.
- **Title NEW:** "A slot is filled only by a recorded promotion, and green, amber or Incomplete promotes itself into an empty one"
- **c1 NEW:** "WHEN a delivery's QA has completed and a supply's status is green, or amber where its amber setting resolves to promote-and-acknowledge or promote (REQ-PIPE-122), or INCOMPLETE where its evaluated status would be promoted on those terms (REQ-PIPE-214), and its assigned slot is unfilled, THE SYSTEM SHALL promote that supply into its period's schema. AMENDED 2026-10-05 by REQ-PIPE-122 criterion 22: under hold an amber supply waits for a person. AMENDED `<date>` by REQ-PIPE-214: an INCOMPLETE supply promotes itself, recorded as Incomplete promoted."
- **c2 NEW:** append "...and SHALL NOT gate on a subset of them - except that an INCOMPLETE supply's not-evaluated cross-table records decide only that it is recorded as Incomplete, never whether it promotes (REQ-PIPE-214). AMENDED `<date>` by REQ-PIPE-214."

**REQ-PIPE-121** (signed 2026-10-04). One combined text, with REQ-PIPE-211, so c1 is amended once.
- **c1 OLD:** "WHEN a table arrives in or leaves a period schema - promoted by a rule or a person, re-filed in or out, superseded, demoted or rejected - THE SYSTEM SHALL re-evaluate, within that period only, every cross-table check that declares it reads the moved table, whether it belongs to a supply WAITING in that period or one PROMOTED there, and SHALL NOT re-evaluate any check that does not read a moved table."
  **NEW:** "WHEN a table arrives in or leaves a period schema - promoted by a rule or a person, re-filed in or out, superseded, demoted or rejected - WHEN the contest of a table in that period ends, by a person's settlement of the pair whatever its outcome or by a later arrival superseding the pair whether or not that arrival is promoted (REQ-PIPE-211), or WHEN a staged supply of a table that a cross-table check read is rejected or superseded (REQ-PIPE-215), THE SYSTEM SHALL re-evaluate, within that period only, every cross-table check that declares it reads that table, whether it belongs to a supply WAITING in that period or one PROMOTED there, and SHALL NOT re-evaluate any check that reads none of those tables. AMENDED `<date>` by REQ-PIPE-211 criterion 1 and REQ-PIPE-215 criterion 2."
- **NFR 4 NEW:** "Cheapest correct path first: a waiting supply's status is recomputed from its latest result per check, and a check's tools re-run only where its latest recorded result read a different supply than the one the period now holds, or was not evaluated (REQ-PIPE-215 criterion 1). Recomputing a status from latest results is one function, shared with REQ-DASH-126. AMENDED `<date>` by REQ-PIPE-215."
- **Not amended:** c12 (only red, or amber under hold, ever reaches it), and the decision "A FILE LANDING IN STAGING STAYS OUTSIDE THIS MECHANISM" (kept, if the architect agrees).

**REQ-PIPE-193 c23** (signed 2026-10-13). Wording from the close-out batch, unchanged by #95. **NEW:** "WHEN a pair is settled, whatever its outcome (REQ-PIPE-211), WHEN a settlement moves a file into or out of a period, and WHEN a settled supply is promoted, THE SYSTEM SHALL owe the knock-on through REQ-PIPE-121's one handler (knock_on), which selects the checks by reevaluation.reading_checks() and the datasets by reevaluation.counts_toward(), and SHALL NOT add a settlement-specific path or restate either rule."

**REQ-DASH-126 c5** (signed 2026-10-04; this corrects v1). **NEW:** "THE SYSTEM SHALL show red promoted as a label beside the existing status pill rather than as a new status, and SHALL show nothing extra beside a promoted supply that is neither red nor INCOMPLETE - an INCOMPLETE one carries REQ-DASH-216's 'Incomplete promoted' label on the same terms. AMENDED `<date>` by REQ-DASH-216."

**REQ-DASH-264** (signed 2026-10-19, amended 2026-10-20)
- **c5 NEW:** "THE SYSTEM SHALL leave the held dataset's own status red by REQ-PIPE-115 criterion 10, the cross-table results changing only the cross-table section's own pill - in which a result that could not be evaluated reads INCOMPLETE - and SHALL NOT count a result that could not be evaluated toward the held dataset's own status (REQ-PIPE-213). AMENDED `<date>` by REQ-DASH-216."
- **c6 NEW:** "...cp-notifications' Client reference reading green on 3 November 2020, and cp-clients' cross-table rows reading INCOMPLETE, each with criterion 7's could-not-run sentence, and its own column checks 'No data' on 1 November 2020. AMENDED `<date>` by REQ-DASH-216." (Was "reading red". The 2026-10-20 evidence shows those rows are all could-not-run; confirm this on the first bootstrap.)
- **c7:** keep the whole text, and after "...(or \"..., when the <table> was re-checked.\")" insert: ", and its pill reads INCOMPLETE (REQ-QAC-212) rather than red". Append "AMENDED `<date>` by REQ-DASH-216 (#95 Q1, Keith 2026-10-20): the could-not-run row's pill reads Incomplete; the sentence stays."
- **c4:** unchanged. The banner sentence "The cross-table checks could not run either ..." stays.
- **Decision on Keith's #258 answers:** append "Q1's 'shows red' SUPERSEDED `<date>` by #95 Q1: a result that could not be evaluated reads INCOMPLETE; the 'Could not be checked ...' sentence and the reasoning (a real outcome, not an absence) stand."

**REQ-GEN-199 c9** (signed 2026-10-13). **NEW:** "THE SYSTEM SHALL record in TS-76's register entry, as part of what TS-76 shows, the state cp-clients and cp-carers are left in for TS-76's quarter once the substitution is removed - promoted and INCOMPLETE (REQ-QAC-212), permanently, for want of a promoted cp-placements, where before REQ-PIPE-213 they were promoted and red, as the delivery-architect found (H1) - and what cp-clients' and cp-carers' pages read before the substitution, while it stands and after it ends. AMENDED `<date>` by REQ-PIPE-213." This is PROVISIONAL until the first bootstrap shows it. The register quotes for TS-75, TS-76 and TS-77 are re-captured under REQ-PIPE-213 c10, which has no criterion wording to amend.

**No amendment needed** (the reason is in each requirement's decisions):
- REQ-PIPE-075 c3, REQ-PIPE-121 c12, and every REQ-PIPE-083 criterion.
- The B2 list: REQ-PIPE-064 c5, REQ-PIPE-132 c10, REQ-GHUB-082 c16, REQ-DASH-056 and REQ-DASH-197.
- REQ-PIPE-098 c2, REQ-QAC-108, and REQ-PIPE-265.

Three the architect listed I could not settle myself: **REQ-PIPE-074, REQ-PIPE-130 and REQ-GEN-186**. They are architect question 4 below.

## Carry-over check: every decision and where it went

**v1 draft (2026-10-14)**

| Decision | Where in v2 |
|---|---|
| 212 a distinct status, and the rejected options | 212 d1, now Keith's Q1 with all three shapes recorded |
| 212 above amber | 212 d2 (Q1); the hold question is 214 c1 / Q11 |
| 212 one trigger | 212 d3 |
| 212 working name, and its open question 1 | 212 d4: closed by Q1 ("Incomplete"). The multi-table pill wording goes to the UX review (216 OQ1) |
| 212 solves both cases | 212 d6 |
| 213 the defect (verified) | 213 d1 |
| 213 the false green is real | 213 d2, plus REQ-PIPE-265's 312 pairs |
| 213 the false red is real, plus the re-file sighting | 213 d3; the sighting is architect question 7 |
| 213 counted toward readable participants | 213 d5 (Q8 = A) |
| 213 the recorded reason stays | 213 d6 |
| 213 trials unchanged | 212 c8 and d7; Q13 |
| 213 rejected time-triggered rewrite | 213 d9 |
| 213 open question 1 (old records) | Closed by architect H3: 213 c2 and d4 |
| 214 "Incomplete waits" (Q2 = A) | Reversed by Q2 = B: 214 d1, with A recorded as rejected |
| 214 "not a deadlock, checked" | Deleted as the architect asked (it was wrong). 214 d2 replaces it, and architect question 1 asks them to confirm |
| 214 a person can still promote | 214 d5 (now demote / any filing decision) |
| 214 c5, amending REQ-PIPE-075 c3 | Not needed: under Q2 = B, c3 stays red-only. Replaced by changes to the title, c1 and c2 |
| 214 throughput NFR ("usually minutes") | Replaced: nothing waits any more (214 NFR 2) |
| 215 re-check question | 215 d1 (Q3 = A) |
| 215 B1 is general | 215 d4, c1 |
| 215 a staged dependency counts | 215 d2 (Q4 = A, with H1's consequence) |
| 216 the cause is not on the reader | 216 d1 and c4 |
| 216 the line stays with 204 | 216 d3 |
| 216 "Incomplete promoted" as a label | 216 d4, plus the correction on REQ-DASH-126 |
| 217 R2 | 217 d1 (Q6 = A) |
| 217 no ticket | 217 d2 (Q7 = A) |
| 217 c3, amending REQ-PIPE-121 c12 | Not needed: 217 d3 |

**summary.md (2026-10-14)**

| Item | Where in v2 |
|---|---|
| The central fork and its recommendation | Settled by Q1 and Q2 (above) |
| "Deadlock: checked, there isn't one" | Deleted; 214 d2 replaces it, and architect question 1 confirms |
| Case table | Updated above: cases 3a, 16 and 17 added; 9, 11 and 13 rewritten |
| 204 title and story | Done |
| 204 c1: drop the not-yet-due exclusion | Done (204 c1 and decision "every reason") |
| 204 c3 | Done |
| 204 c15: one wording | Done (Q10 = A) |
| 204 c7 simpler | Done |
| 204 c10: codes only if per-cause | Codes dropped; the structured table fields are kept through one function |
| 204 c16 "stays" | **Removed instead.** Under Q2 = B there is no waiting supply for it to apply to (204 decision) |
| 204 c18 stays | Card line kept; the row note is folded into the pill (UX to confirm) |
| 204 c13 and c14 tests | Re-worded (c13, c14) |
| 210 c1 → Incomplete | Removed (Q2 = B) |
| 210 c4 unchanged | Kept as c1 |
| 210 F6 and its open question 1 | Not needed now, rather than overturned (210 d3) |
| 210 "under B, shrinks to c4" | Done; Q12 |
| 211: demote it (Q9 A) | Keith chose B: kept a must as drafted (211 d9) |
| 211: B1 moves to 215 | 211 d10; 211 now depends on 215 |
| Amendment list | Section above, updated: 075 changes moved from c3 to the title, c1 and c2; 121 c1 folded; 121 c12 dropped; 126 c5 added |
| NFR angles | In each requirement's NFRs |
| "Not relay questions" | The word on the pill is settled by Q1; old records are settled by H3 |
| Re-file sighting | Architect question 7 |
| Keith's 2026-10-14 position: keep REQ-PIPE-121's staging rule | 215 d3 and c3 |

**review-architect.md (2026-10-14)**

| Finding | Where in v2 |
|---|---|
| Verdict: the shape is right | Adopted |
| B1 deadlock, and its fix (A1: re-gate on a staged arrival) | Dissolved by Q2 = B (214 d2); the fix is rejected (215 d3); architect question 1 |
| B2 AWAITING_DECISION, A4 slot state | Dissolved (214 d2); not needed |
| H1: Q4 A contradicts case 9 | Case 9 rewritten (215 c7, d6). What's left over is 215 OQ1 / architect question 2 |
| H2: inherited and substituted count as readable | 213 c6 and d7 |
| H2/A3: retry a refused inheritance | Not needed for this batch: self-promotion removes the delayed promotions that made it likely. The leftover is architect question 5 |
| H3: record at the writers | 213 c2 and d4 |
| H4: one predicate | 213 c4; 204 c10; 210 c2 |
| H5: three test-first claims | 215 c9 and c10 rewritten, d5; c2's test (case 10) kept; architect question 3 |
| H6: after_replay reads the gate | 214 c8 and d6 |
| M1: handled structurally | 212 NFR 4; 214 c6 |
| M2: REQ-GEN-199 quotes and the pin | 213 c10, plus the GEN-199 c9 amendment |
| M3: one withheld record | Not needed: nothing Incomplete-only is withheld |
| M4: REQ-GEN-203's dependency on 211 | It stands, because 211 stays a must (211 d10) |
| M5: 210's "not counted" | Met by the readers leaving the queue (210 d3) |
| M6: superseded decisions | 213 d8; the REQ-PIPE-115 decision amendment; 204's superseded decision; held_blast_radius's comment is build work |
| L1: renumber both orderings | 212 c5 |
| The amendment list beyond v1 | Section above; 074, 130 and GEN-186 are architect question 4 |
| "One sprint, fixed order" | Build order above |
| Keith A1-A4, B1 | A1: kept (Keith); A2 = Q4 A; A3 and A4: dissolved; B1: 203's dependency stands |

**Close-out REQ-DASH-204, 210 and 211 decisions.** Every one is carried in the
re-folded requirement. Where #95 overturned one, it is marked SUPERSEDED:
204's "explains the red", its per-cause wordings and its per-table codes. The
long amendment-27 decision in 211 is condensed to a pointer; its full wording
is in the REQ-PIPE-121 section above.

Nothing is left only in prose.

## Non-functional angles

- **Answered from the codebase:**
  - Scale: one pill, one line per table, one card line.
  - Reliability: owed in the same transaction.
  - Performance: worked out at build time.
  - The build rule.
  - Auditability: re-runs and promotions name their cause.
  - Maintainability: parity between Python and JS.
  - Compatibility: no new assets.
  - Throughput: unchanged now that Incomplete self-promotes.
- **Put to Keith:** Q11, which is the reliability / false-quiet angle (amber "hold").
- **Ruled out as not applying:**
  - Security: no new capability.
  - Privacy: only table names and periods.
  - Cost: no clock-driven sweep.
  - Compliance and retention: no new kind of stored data.

## Questions for Keith (one set, recommended option first)

- **Q11. Incomplete and an amber "hold".** Incomplete ranks above amber.
  Should a missing partner table let an amber supply past its dataset's
  "hold"?
  - **A (recommended):** No. The gate decides on the status of the checks
    that ran. An amber supply under hold still waits, and it reads
    Incomplete. The same rule applies to promote-and-acknowledge and to
    replacing a promoted supply.
  - **B:** Yes. Incomplete always promotes. Simpler, but a missing table
    becomes a way round "hold".
- **Q12. What's left of REQ-PIPE-210.** Its readers now promote themselves.
  What remains is "a supply waiting for its own reasons also names the other
  table in the terminal queue".
  - **A (recommended):** Keep it, reduced, as a should.
  - **B:** Drop it, and add that one criterion to REQ-PIPE-214 instead.
- **Q13. Trial runs.** A trial is filed to no period and decides nothing.
  - **A (recommended):** A trial's could-not-run cross-table check stays
    "No data".
  - **B:** It reads Incomplete too, for consistency.

## For the delivery-architect (2026-10-14 reviewer)

1. Confirm that no deadlock remains under self-promotion. This includes
   non-participation quarters, where a period starts at its first promotion.
   Also confirm REQ-PIPE-121's "a file landing in staging stays outside this
   mechanism" can be kept unchanged.
2. Case 9 / REQ-PIPE-215 OQ1. Under Q4 = A, the dependency's own arrival run
   checks the reader against it. A later, unrelated re-run of the reader finds
   that dependency "staged awaiting a decision" (REQ-PIPE-079 c16) and turns
   it Incomplete. Accept that, or amend c16? If c16 should change, that goes
   back to Keith.
3. Do the rewritten failing-first tests now actually fail first on today's
   code: case 11, case 13, and case 10 (REQ-PIPE-215 c2)?
4. Under Q2 = B, do REQ-PIPE-074 (decision-log vocabulary for "Incomplete
   promoted"), REQ-PIPE-130 (the _manifest view) or REQ-GEN-186 (target
   agreement) need amending? Or is REQ-PIPE-214 c2 and c8 enough?
5. Is H2/A3 (retrying a refused inheritance) still needed now that promotions
   are no longer delayed?
6. Is the staged-superseded trigger (215 c2) needed when the superseding file
   can be loaded? That file's own run already refreshes the readers, so the
   trigger may only matter for a file that can't be loaded or is held.
7. The sighting: siblings re-filed at the same instant read each other as
   missing. REQ-PIPE-265 c1 excludes re-check runs from being siblings. Is
   REQ-PIPE-105 c5's same-instant rule meant to cover re-files?
8. The build order above, and the B2 list being unneeded except for the
   amber-hold case, which uses existing states.

## For the UX reviewers

- **Dashboard:**
  - The colour for Incomplete.
  - The pill's wording when there are two or more missing tables.
  - Whether the pill "Incomplete: no promoted `<table>`" and REQ-DASH-204's
    top-of-page line say the same thing twice on one page.
  - Folding 204's collection-table row note into the pill.
  - At thirty datasets: readers' Incomplete rows on a missing table's page
    every quarter.
  - Whether each reason's page actually says why there is no promoted supply.
    Not yet due is the most likely to have no notice (204 OQ).
  - 204's new sentence (c2) and its "promoted on `<date>`" line (c7).
- **CLI:**
  - How the terminal labels Incomplete (214 c7): the QA run's outcome, the
    queue, and the settlement outcome panel in 211 c8.
  - 210's line, if it is kept.

## Draft entry for plans/running-thoughts.md #95 (for a human to apply)

> Replace "The rest of the draft's questions are being walked with him; answers in that folder's summary.md." with: "**ALL TEN ANSWERED 2026-10-20** and folded into a v2 draft (`summary-v2.md`, `requirements-draft.yaml`): REQ-QAC-212 to REQ-PIPE-217 plus the close-out REQ-DASH-204, REQ-PIPE-210 and REQ-PIPE-211 re-folded. An Incomplete supply promotes itself as 'Incomplete promoted'; re-checked only when something moves. Three new questions with Keith (Q11 amber hold, Q12 REQ-PIPE-210, Q13 trials); the architect to confirm no deadlock remains. Unsigned."

## Validation

- `uv run mothman dashboard validate-requirements --draft requirements-draft.yaml`
  reports 38 errors. All of them are the expected cross-references to
  requirements outside the draft.
- Merged with `requirements.yaml` and the close-out draft's REQ-GEN-206 (in
  the scratchpad as `merged95v2.yaml`), it reports: "requirements validation
  OK - 258 requirements, zero errors."
- I read the file back. All nine requirements parse, every prose item is a
  string, and none carries `signed_off`.
