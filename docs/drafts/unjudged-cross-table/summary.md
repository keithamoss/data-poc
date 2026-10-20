# Unjudged cross-table checks (#95): draft for sign-off

Drafted by delivery-scoper on 2026-10-14 from `plans/running-thoughts.md` #95,
including Keith's input for the scoper. This is a **proposal**. Nothing in it
is in `requirements.yaml`, and anything marked PROVISIONAL depends on one of
the questions at the end. The requirements are in `requirements-draft.yaml`
next to this file, numbered REQ-QAC-212 to REQ-PIPE-217 (after the close-out
draft's REQ-PIPE-211).

## What is wrong today

I checked this in the code and in the bootstrapped database on 2026-10-14.

A cross-table check that cannot read one of its tables is recorded once, in
the reader's run. The dependency's state is read once, at that run, and never
looked at again:

- **Not yet due.** The check is recorded `nodata`. `nodata` sits below green
  and loses every rollup, so a reader whose other checks pass reads **green**
  and promotes itself. A real example: `cp-investigations@202408010100000000`
  was promoted by rule on 2024-08-01 (decision 103) with 15 results recorded
  `nodata` for cp_clients, cp_case_workers and cp_notifications. It was only
  checked again because those three tables happened to be promoted later. If
  any of them had never arrived, it would have stayed green and promoted.
- **Overdue, awaiting a decision, contested, could not be loaded, held, or
  the catch-all.** The check is recorded `fail`, which rolls up, so a reader
  with nothing failing in its own data reads **red**. A real example: the
  2023-Q4 re-file re-checks recorded 30 catch-all fails across four datasets,
  and the knock-on wrote a "still failing, a person decides" record for
  cp-notifications (decision 70).

## The central fork, and what I recommend

**How the shout should look.** I recommend **a new status, INCOMPLETE**
(working name). It is neither green nor red. It ranks above amber and below
red: a reader with a red check of its own still reads red, and one that would
otherwise read green or amber reads INCOMPLETE. It has one trigger: a
cross-table check could not run against every table it reads. The cause is
never part of the status. The reader's page says the period has no readable
`<table>` and links to it, and that table's own page says whether it is late,
overdue, held or anything else. That is Keith's own framing.

**What follows from that:**

- **Gate.** An INCOMPLETE supply does not promote itself, but a person can
  promote it.
- **Re-check.** A reader is checked again when something moves:
  - the missing table is promoted, substituted or inherited into the period
    (the knock-on already does this, once round 4's blocker B1 is fixed in
    general rather than only for contests);
  - a staged table the reader had read is rejected or superseded (new).

  Nothing is re-checked on the clock. Once "not yet due" already shouts,
  "now overdue" only changes the reason, and the reason belongs on the
  dependency's page. The dashboard never shows the recorded reason as the
  table's current state.
- **The R2 shout.** No "still failing" record is written for a reader that
  is only INCOMPLETE. So a dependency that never arrived and a pair where
  both files were rejected give exactly the same shout, which answers Keith's
  R2 question directly.

Why not the alternatives:

- **The verdict plus an "Incomplete" label** (the red-promoted pattern): a
  green pill is still read as green at a glance.
- **Red for everything:** this is the red-for-nothing-wrong that REQ-PIPE-079
  criterion 14 forbids. On Child Protection, every early arrival in a quarter
  would read red.
- **A status shown beside the rollup rather than in it:** it cannot express
  both "red beats it" and "it beats green".

**Deadlock: checked, there isn't one.** Every arrival is checked against
every other table staged for its period, so the last of a period's tables to
arrive is checked against all of them. When it promotes, the knock-on
re-checks the earlier readers and promotes them in turn.

## Requirements drafted

| Id | MoSCoW | What it covers |
|---|---|---|
| REQ-QAC-212 | must | The INCOMPLETE status: what it means, its place in the ordering, Python/JS parity through status-cases.json, and that drift checks and trials do not use it. |
| REQ-PIPE-213 | must | Every not-evaluated cross-table record reads INCOMPLETE, whatever the reason. It counts toward the participants that could be read, never toward the missing table's own dataset. Amends six signed requirements. |
| REQ-PIPE-214 | must | The gate does not promote an INCOMPLETE supply; a person can. Amends REQ-PIPE-075 criterion 3. |
| REQ-PIPE-215 | must | When a reader is checked again: something moves, never the clock. Includes the general fix for B1. Amends REQ-PIPE-121 criterion 1 and NFR 4. |
| REQ-DASH-216 | must | INCOMPLETE on every status surface, the missing table described only as "no readable supply" for the date on show, an "Incomplete promoted" label, and real-browser tests. |
| REQ-PIPE-217 | should | No "still failing" record for an INCOMPLETE-only reader, and how tickets handle it. Amends REQ-PIPE-121 criterion 12. |

## Every case, today and under the draft

Keith asked for this table (2026-10-14, binding on the draft). Every test
named below goes in `tests/test_incomplete_cross_table.py` unless another
file is given. Each is written first, seen to fail by reproducing today's
reading, and then made to pass.

| # | Case | Reads today | Reads under the draft | Fixed by |
|---|---|---|---|---|
| 1 | Dependency not yet due when the reader runs | **Green**, promoted by rule (decision 103) | INCOMPLETE, not promoted | 213 c7; 214 c6; 216 c7 (in the browser) |
| 2 | ...and the dependency then goes overdue | Still green and promoted, never checked again | Still INCOMPLETE, with no re-run needed | 215 c3, c5 |
| 3 | ...and the dependency never arrives (period closes) | Green and promoted for good | INCOMPLETE and staged until the table arrives or a person acts | 214 c7, c8 |
| 4 | Dependency overdue when the reader runs, no failure of its own | **Red**, plus a "still failing, a person decides" record after a knock-on | INCOMPLETE, with no such record | 213 c8; 217 c5; 216 c7 |
| 5 | Dependency staged but unreadable, awaiting a decision | Red | INCOMPLETE | 213 c9 |
| 6 | Dependency contested | Red | INCOMPLETE | 213 c10 |
| 7 | Dependency could not be loaded (live: cp_investigations__202505010900000800) | Red | INCOMPLETE | 213 c11 |
| 8 | Dependency held with no period | Red (held_blast_radius) | INCOMPLETE | 213 c12 |
| 9 | Dependency arrives after the reader, is red, never promoted | Whatever the reader's first run recorded, never checked again | INCOMPLETE | 215 c6 |
| 10 | Reader checked against the dependency's **staged** supply, which is then rejected | The verdict on rejected data stands; nothing re-checks it | Re-checked, reads INCOMPLETE ("Incomplete promoted" if already promoted) | 215 c2, c7; 216 c5 |
| 11 | Dependency promoted later, including after a pair where both files were rejected | Re-run in most cases, but only re-gated where the period held nothing before or after (round 4 B1) | Re-run against the promoted table, then re-gated | 215 c1, c8 |
| 12 | Siblings re-filed into one period at the same instant (2023-Q4 `__r1` runs) | Red (catch-all), plus a "still failing" record | INCOMPLETE, with no such record | 213 c13; 217 c5 |
| 13 | The staged dependency the reader read is superseded by a later file | Not re-checked | Re-checked against the later file | 215 c2, c9 |
| 14 | The other side: a check filed under the missing table, recorded in the arriving table's run (cp_carers__202305010900000800) | Green (nodata is dropped) | INCOMPLETE (PROVISIONAL, Q8) | 213 c14 |
| 15 | The missing table's own dataset | The reader's not-evaluated record is shared onto its page by the build | Not counted there; it shows its own state | 213 c15; 216 c8 |
| - | Pair where both files were rejected, compared with a dependency that never arrived (R2) | Different: one gets a log record, the other gets nothing | The same status, and no record in either case | 217 c6 |

## Effect on REQ-DASH-204, REQ-PIPE-210 and REQ-PIPE-211

If the recommendation is accepted, the close-out batch needs these changes:

**REQ-DASH-204** (the line at the top of the reader's page). It stays the
owner of the line, and the line explains INCOMPLETE rather than red.

- Title and story become "Incomplete because another table...".
- c1: drop "SHALL NOT show a line for a table that is merely not yet due".
  Keith wants a shout even when the table simply hasn't arrived with the
  reader. The red notice style becomes the INCOMPLETE style.
- c3: "explains the red" becomes "explains the INCOMPLETE status".
- c15: I recommend replacing the five per-cause wordings with one: **"No
  promoted `<dataset>` for `<period>`"**, linked, with the cause read on
  that dataset's page. Keith is agnostic about the detail, and the recorded
  cause can be out of date. If the per-cause wordings are kept, they must
  come from the dependency's state on the date shown, never from the
  recorded code.
- c7 gets simpler: where the period now holds the table but the reader has
  not been re-run, say "`<dataset>` was promoted on `<date>`; these checks
  have not run against it yet".
- c10 (codes per table) is only needed if the per-cause wording is kept.
  `held_tables` and `unrunnable_tables` are still needed either way.
- c16 stays: nothing needs deciding on this supply.
- c18 stays: one line per missing table on the card.
- c13 and c14 tests: reword them for INCOMPLETE.

**REQ-PIPE-210** (the terminal queue).

- c1: "every red check is another table's" becomes "its status is
  INCOMPLETE". c4 (a reader with a red of its own) is unchanged.
- The F6 counting rule stands. Its open question 1 (a reader with nothing
  to sit beneath) is answered "not counted", for F6's own reason.
- If Keith picks Q2 option B (INCOMPLETE promotes), these readers leave the
  queue altogether and 210 shrinks to its c4.

**REQ-PIPE-211** (re-checking after a pair is settled). Under the draft,
most of its reason goes away:

- After "reject both", the readers read INCOMPLETE. That is correct, not
  "red for good", and they are re-run when cp_clients is promoted
  (REQ-PIPE-215 c1).
- Re-running them right after the settlement re-records the same
  INCOMPLETE status with a fresher reason.
- What is still worth keeping:
  - c8: the terminal shows the readers' state after settling;
  - possibly the trigger, so the stored reason stops saying "contested".
- B1 moves into REQ-PIPE-215 c1. If 211 is kept, it depends on 215.

I recommend demoting 211 to **should**, reduced to c1, c5 and c8. That is
question Q9, since Keith made it a must.

## Signed requirements this amends (wording for Keith's approval)

- **REQ-PIPE-079 c4, c15, c16:** "report it red" becomes "record it not
  evaluated, reading INCOMPLETE (REQ-PIPE-213)", still naming the table and
  the reason. **c14:** "SHALL NOT report the check red" becomes "SHALL
  record it not evaluated, reading INCOMPLETE, and say the table has not
  been supplied for this period yet".
- **REQ-PIPE-105 c13:** "...make plain that the check reads INCOMPLETE for
  want of a readable table rather than because of anything in the data".
- **REQ-PIPE-115 c14:** "not evaluated, red" becomes "not evaluated,
  INCOMPLETE". **c20:** the expected codes stay, but every case reads
  INCOMPLETE.
- **REQ-PIPE-078 c10:** "report that check as red" becomes "record it not
  evaluated, reading INCOMPLETE".
- **REQ-QAC-037 c7:** "...whether that check failed or could not run - a
  check that could not run reads INCOMPLETE for the participants it could
  read and is not counted toward the participant it could not read
  (REQ-PIPE-213) - and SHALL NOT leave a participating dataset reading green
  while a check that reads it reads red or INCOMPLETE."
- **REQ-PIPE-075 c3:** "red or INCOMPLETE" (REQ-PIPE-214 c5).
- **REQ-PIPE-121:**
  - c1 gains the staged-rejected or superseded trigger. Amend it once,
    together with REQ-PIPE-211's contest-end trigger, if 211 survives.
  - c12 excludes an INCOMPLETE-only supply.
  - NFR 4 says a not-evaluated reading result always means a re-run.
- **REQ-PIPE-083:** no amendment if Q7 option A is chosen. c6 already
  covers "every state".
- **REQ-DASH-126:** no amendment. REQ-DASH-216 c5 extends its pattern.
- **REQ-QAC-108:** unchanged. Gaps in the drift reference period keep their
  own rules.

## Non-functional angles

- **Answered from the codebase:**
  - Scale: aggregate, one line per table.
  - Reliability: owed in the same transaction, finished by the processing
    pass.
  - Performance: computed at build time.
  - The build rule.
  - Auditability: re-runs name their cause.
  - Maintainability: one status value in two vocabularies held equal by a
    parity test.
  - Compatibility: no new assets.
- **Put to Keith:**
  - Throughput: early arrivals now wait for their partners (Q2).
  - Ticket noise (Q7).
- **Ruled out as not applying:**
  - Security: no new capability, and a person's promotion keeps its
    allowlist.
  - Privacy: only table names and periods are recorded, never rows.
  - Cost: there is no clock-driven sweep. Re-checks are cross-table only,
    one per decision.
  - Compliance and retention: no new stored data class.

## Questions for Keith (recommended option first)

### Set 1: the shape

- **Q1. What does the reader read when a cross-table check couldn't run?**
  - **A.** A new status, INCOMPLETE, ranked above amber and below red.
    (Recommended.) Own red still wins; otherwise it shouts.
  - **B.** The verdict of the checks that did run, plus a loud "Incomplete"
    label beside the pill (the red-promoted pattern). Keeps more detail, but
    still shows a green pill.
  - **C.** Red for every case, including not yet due. Simplest, but red for
    nothing wrong.
  - **D.** A distinct status shown beside the rollup rather than in it. It
    can't be ordered against red or green.
- **Q2. Does an INCOMPLETE supply promote itself?**
  - **A.** No. It waits for the table or for a person. (Recommended; this is
    what #95 proposed.) Early Child Protection arrivals wait for their
    partners.
  - **B.** Yes, shown as "Incomplete promoted" and re-checked when the table
    arrives. Data keeps flowing, but a reader that later turns red can't be
    demoted.
- **Q3. When is an INCOMPLETE reader checked again?**
  - **A.** Only when something moves: the table is promoted, substituted or
    inherited, or a staged table it read is rejected or superseded. Never on
    the clock. (Recommended.)
  - **B.** Also on the clock, when the table goes overdue or the period
    closes. This refreshes the stored reason, at the cost of a scheduled
    sweep that grows with history.
- **Q4. A reader checked against a dependency's *staged*, not-yet-promoted
  supply: does that count as checked?**
  - **A.** Yes, as today. If that staged supply is later rejected or
    superseded, the reader is re-checked. (Recommended.)
  - **B.** No. It stays INCOMPLETE until the dependency is promoted (your
    literal "red and not promoted, notifications shouts"). The gate would
    then have to promote a period's waiting supplies together, which is a
    much bigger change.

### Set 2: the edges

- **Q5. The dependency's slot is accepted as "not supplied". What happens to
  its readers?**
  - **A.** They stay INCOMPLETE, and a person promotes them if wanted.
    (Recommended.)
  - **B.** The acceptance releases them to their own verdict and they are
    re-gated automatically.
- **Q6. The "still failing, a person decides" record, for a reader that is
  only INCOMPLETE:**
  - **A.** Not written. The status is the shout, the same whether the table
    never came or both files were rejected. (Recommended; this answers R2.)
  - **B.** Written at normal prominence, naming what it waits on.
- **Q7. Tickets under the needs-action policy:**
  - **A.** No ticket for INCOMPLETE alone. The missing table's own ticket
    carries it, and the reader's existing ticket shows the state.
    (Recommended.)
  - **B.** Each INCOMPLETE reader gets a ticket.
- **Q8. The other side of a check: the first table to arrive in a quarter,
  whose partner's check couldn't run.**
  - **A.** It reads INCOMPLETE too, under one rule, per REQ-QAC-037 c7.
    (Recommended.)
  - **B.** Only the dataset the check is filed under reads INCOMPLETE.

### Set 3: the close-out batch

- **Q9. REQ-PIPE-211, given that "reject both" would read INCOMPLETE rather
  than red for good:**
  - **A.** Demote it to should, keeping only the trigger, the "owed if
    interrupted" rule and the terminal's after-settlement display.
    (Recommended.)
  - **B.** Keep it as a must, as drafted.
  - **C.** Drop it.
- **Q10. REQ-DASH-204's line:**
  - **A.** One wording, "No promoted `<dataset>` for `<period>`", linked,
    with the cause read on that page. (Recommended.)
  - **B.** Keep the five per-cause wordings, taken from the dependency's
    state on the date shown.

### Not relay questions

- The word on the pill (QAC-212, open question 1) is for the dashboard UX
  review to propose and Keith to approve.
- Whether pre-change records must also read INCOMPLETE (PIPE-213, open
  question 1) is for the architect.

## A sighting for the architect, outside this scope

The 2023-Q4 re-file batch's re-check runs saw siblings re-filed at the same
instant as *missing* (the catch-all), rather than reading each other as
staged. REQ-PIPE-105 c5's same-instant rule is worded for arrivals. Is the
same thing true of re-files?

## Draft entry for plans/running-thoughts.md (replaces #95's status line; for a human to apply)

> 95. **[in-progress, 2026-10-14]** **[Pipeline & publishing]** **[QA checks & contract]** **[Dashboard UI]** ...(existing text kept)... **SCOPED 2026-10-14** into `docs/drafts/unjudged-cross-table/` as REQ-QAC-212 to REQ-PIPE-217 (unsigned): a new INCOMPLETE status that the gate does not promote on, re-checked only when something moves, with no "still failing" record. Ten questions are with Keith. REQ-DASH-204, REQ-PIPE-210 and REQ-PIPE-211 are re-folded once he has answered.

## Validation

- I merged `requirements.yaml`, the close-out draft's nine new requirements
  and these six into `scratchpad/merged95.yaml`. `uv run mothman dashboard
  validate-requirements --draft` reported: **"requirements validation OK -
  212 requirements, zero errors."**
- Run on its own, this draft reports only the expected errors for
  requirements it depends on but does not contain.
- I read the file back. All six requirements parse, and every prose item is
  a string.

## Keith's answers so far (2026-10-14, ~midday)

- Shape (Q1): "Red with nuance and pills?" - not yet settled. Followed up:
  a red-looking status with an "Incomplete: no promoted <table>" pill that
  still promotes itself, vs a truly red one the gate holds, vs red in the data
  with a flag. PARKED by Keith: "Let's come back to this later today."
- Promote itself (Q2): YES - option B, "because a person can unpromote": an
  incomplete supply promotes itself as "Incomplete promoted" and is re-checked
  when the missing table arrives. NOTE: with self-promotion the architect's B1
  deadlock largely disappears (early arrivals promote, the period opens,
  inheritance runs, and the existing knock-on re-checks them when the table is
  promoted) - but it conflicts with a TRULY red status, which never promotes
  itself; that is the parked shape question.
- A staged dependency counts as checked (Q4 / architect A2): YES (A).
- Re-gate on a staged arrival - amend REQ-PIPE-121's "a file landing in
  staging stays outside this mechanism" (architect A1): reminded of the
  decision's wording; PARKED with the shape question ("see previous").

## Shape question re-asked, 2026-10-14 13:06 - PARKED again ("Come back to this"; REQ-PIPE-121: "See previous")

Reframed for next time. Q2 = B (an incomplete supply promotes itself) rules out
a TRULY red status, which never promotes itself, and largely dissolves the
architect's B1 (the deadlock: early arrivals promote, the period opens, the
existing knock-on re-checks them when the missing table is promoted) and B2
(nothing sits in AWAITING_DECISION). Three shapes remain:

1. **Its own "Incomplete" status** (recommended): between amber and red in
   every rollup - own red wins, it beats green and amber - pill "Incomplete:
   no promoted <table>" linking to the table, whose page gives the cause;
   promotes as "Incomplete promoted"; re-checked when the table is promoted,
   substituted or inherited.
2. **Red-looking with a pill**, but promoting itself unlike every other red:
   loudest, but red would mean two things and early Child Protection arrivals
   read red every quarter.
3. **The real verdict plus a flag** (the red-promoted pattern): least change,
   but a green pill still reads green at a glance.

REQ-PIPE-121: with self-promotion the case for amending "a file landing in
staging stays outside this mechanism" (architect A1) mostly falls away.
Recommended: keep it, and have the architect confirm no deadlock remains once
self-promotion is in.

## Keith's answer on the shape, 2026-10-20

- **Q1: shape 1, its own Incomplete status** ("Go with 1, its own Incomplete
  status"). Between amber and red in every rollup - its own red wins, it beats
  green and amber; the pill reads "Incomplete: no promoted <table>" and links to
  the table, whose page gives the cause; it promotes itself as "Incomplete
  promoted" (Q2 = B, 2026-10-14); re-checked when the table is promoted,
  substituted or inherited. Settles REQ-QAC-212 criterion 2 (PROVISIONAL until
  now). Put to him in the context of REQ-DASH-264's Q1 answer the same morning:
  a could-not-run cross-table row now reads red with "Could not be checked ...";
  once this lands its pill reads Incomplete and the sentence stays.
- **The remaining questions, 2026-10-20** ("A on all but Q9, which is B"),
  put to him reworded for self-promotion:
  - **Q3 = A**: re-checked only when something moves (the missing table is
    promoted, substituted or inherited, or a staged table it read is rejected
    or superseded), never on the clock.
  - **Q5 = A**: when the missing table's slot is accepted as "not supplied",
    the reader stays Incomplete for that period; a person can still act.
  - **Q6 = A**: no "still failing, a person decides" record for a reader that
    is only Incomplete - the status is the shout (answers close-out R2).
  - **Q7 = A**: no ticket for Incomplete alone; the missing table's own ticket
    carries it.
  - **Q8 = A**: the other side of a check reads Incomplete too, one rule
    (REQ-QAC-037 criterion 7).
  - **Q9 = B**: REQ-PIPE-211 stays a must, as drafted.
  - **Q10 = A**: REQ-DASH-204's line has one wording, "No promoted <dataset>
    for <period>", linked, the cause read on that dataset's page.
  Every question in this draft is now answered; next is folding the answers
  into the six requirements (and REQ-DASH-204, REQ-PIPE-210, REQ-PIPE-211)
  and the architect confirming no deadlock remains with self-promotion.
