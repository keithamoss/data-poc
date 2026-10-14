# Calendar close-out batch: for sign-off

Keith - this is the batch with your close-out answers and your 15 follow-up answers (both 2026-10-14) folded in. **None of it is signed, and requirements.yaml has not changed.** The full text is in `requirements-draft.yaml` next to this file, with the three overnight reviews (`review-*.md`). Merged with the live register it passes `mothman dashboard validate-requirements` (206 requirements, zero errors).

Every answer that took the recommendation now uses the wording already drafted for it, and each is recorded in its requirement's `decisions:` as "Keith, 2026-10-14, close-out QN" or "Keith, 2026-10-14, follow-up FN". **Answers are not sign-off**, so each requirement below still needs your yes.

**New wording you have not seen yet** (each marked "NEW WORDING - for Keith's approval" in the YAML):
- Q11: TS-53 with a person's promote (REQ-GEN-206 criterion 5), and the REQ-GEN-137 criterion 2 amendment.
- Q16: the whole of REQ-DASH-209, the period-composition view.
- Q24: REQ-DASH-208 criteria 5, 8 and 9, the scenario jump carried in the URL.
- Q26: REQ-DASH-180 criterion 27, the "Turning off after <date>" marker.
- Q17 also needed new words: REQ-DASH-204 criterion 15 gives each cause its own line and next step. You chose the option, not the wording.
- Q19 and Q21: the two new pipeline requirements, REQ-PIPE-210 and REQ-PIPE-211.

**New wording from the 15 follow-ups.** Only REQ-DASH-180's carries the YAML marker; the rest are listed here:
- F3 and F15: REQ-DASH-209 criteria 3 and 10 (the person's name), and new criterion 11 (page size).
- F5 and F7: REQ-PIPE-211 criteria 1, 2 and 4 to 7, new criteria 8 and 9, and amendment 27's NEW text.
- F6: REQ-PIPE-210 criterion 7.
- F8: REQ-GEN-206 criteria 16 to 18 (TS-81).
- F9: REQ-DASH-180 criterion 27 reworded, and new criterion 28.
- F10: REQ-DASH-208 criterion 10.
- F11: REQ-GEN-205 criteria 24 and 25.

## Scoper passes, honestly

- **No review at all:** REQ-DASH-209, REQ-PIPE-210 and REQ-PIPE-211 were drafted by delivery-scoper this morning from your answers. No architect or UX reviewer has seen them.
- **Proposed by the round 3 reviews but never reviewed as requirements of their own:** REQ-GEN-207 and REQ-DASH-208.
- **Only the joint 2026-10-13 pass:** REQ-PIPE-179 and REQ-DASH-182 (scoped jointly with REQ-PIPE-163).
- **Neither that pass nor one of its own:** REQ-DASH-180.
- The rest had a scoper pass and the round 3 reviews.

## Build order

The architect's order, with the three new requirements placed by the scoper (proposed, recorded on REQ-GEN-207):

1. REQ-GEN-207
2. REQ-PIPE-202
3. REQ-GEN-203
4. REQ-DASH-204
5. REQ-PIPE-210
6. REQ-PIPE-211
7. REQ-DASH-182
8. REQ-PIPE-163
9. REQ-PIPE-179
10. REQ-DASH-180
11. REQ-DASH-208
12. REQ-DASH-209
13. REQ-GEN-205
14. REQ-GEN-206

REQ-DASH-208 and REQ-DASH-209 must come before the first REQ-GEN-205 or 206 bootstrap, because TS-55's chip opens 209's view. REQ-GEN-206 also comes after REQ-PIPE-211 because of TS-81 (F8): planted there, TS-81 is observed with the fix in place.

## The requirements, in build order

**REQ-GEN-207 (must): grow the Child Protection history earlier, once.**
- **Story:** add quarters before 2023, sized by a dry run of the collision check, so each new scenario has a quarter of its own and no planted scenario moves.
- **What changed:** you chose option A (Q1). It is its own requirement, built first, and today's quarters stay byte-identical.
- The dry run now counts what your other answers added: Child Protection lead-in quarters (Q3), TS-50's era and lead-ins (Q12), and every period the confirmed correction claims.
- TS-62 is left out of the dry run because it is on Birth Registrations (Q7).
- **Follow-ups:** the dry run now counts TS-81, the Child Protection pair with both files rejected (F8). TS-53 is on Birth Registrations (F12), so it is not counted. TS-62's effective date is checked by REQ-GEN-205 on every generation, not by this dry run (F11).
- The build-order decision now places the three new requirements.
- **Open:** nothing.

**REQ-PIPE-202 (should): widen cp_clients' file pattern.**
- **Story:** two Client Register files in one delivery are recognised as a contested pair.
- **What changed:** criterion 13 is new (Q22). The Synthetic-mode picker lists a two-file arrival marked "two files for one table", and refuses when it is picked, naming both files.
- **Open:** nothing.

**REQ-GEN-203 (should): TS-42 and TS-80.**
- **Story:** one contested Client Register pair that a later file supersedes, and one that a scripted person settles, both on the real page.
- **What changed:**
  - Criterion 4 (Q3): the Child Protection generator gains green targeting with lead-in quarters, as REQ-GEN-185 did for Birth Registrations.
  - Criterion 5 (Q1): both scenarios and their lead-ins go in grown quarters.
  - The old criteria 4 to 11 are now 6 to 13.
- **Open, but not a question to you before:** TS-80's outcome (the stray test file rejected, the real extract kept) is still the scoper's proposal. Say if you want it otherwise.

**REQ-DASH-204 (must, Q20): a reader turned red by another table says so at the top of its page.**
- **Story:** a data team leader is sent to the one decision or arrival that clears the red.
- **What changed:**
  - **All causes (Q17):** the line now covers every cause rooted in another table: two files for one table, could not be loaded, held with no period, overdue, and waiting on a decision. It never covers not-yet-due.
  - **Wording (new):** criterion 15 gives each cause its own wording and next step, for example "Red because <dataset>'s supply for <period> is overdue".
  - **The reader's own item (Q19, page half):** criterion 16 makes it say that nothing needs deciding on this supply, and what re-checks it.
  - **Collection level (Q18):**
    - criterion 17: the causing dataset's notice ends "Affects <reader links>";
    - criterion 18: a quiet note under each reader's row, and one line per cause on the collection card.
  - **After settlement (Q21):** criterion 7 names REQ-PIPE-211's re-check as what runs the checks again.
- **Open, a build-time check:** whether every cause already has a notice on the causing dataset's page to end with "Affects". The contested banner does; the others are to be confirmed, and any cause with no notice comes back to you rather than getting a new banner.

**REQ-PIPE-210 (NEW, should, unreviewed): the terminal queue says the same as the page.**
- **Story:** a reader whose red is wholly another table's says nothing needs deciding on it, and is listed beneath that table's own item in the queue. One function decides this for both the page and the terminal.
- A reader with a failing check of its own is never told this.
- Its own decisions stay available.
- **Follow-up F6:** criterion 7. A reader listed beneath its cause is not counted, in the queue or in `mothman supply queue`, so the count is the number of things to decide. A reader with a failing check of its own is still counted.
- **MoSCoW (F14):** should.
- **Open:** two questions F6 raised (questions 3 and 4 below).

**REQ-PIPE-211 (NEW, must, unreviewed): ending a contest re-checks its readers, whatever the outcome.**
- **Story:** after "reject both" (and any other settlement), the readers' contested results are re-evaluated through the one knock-on handler. Otherwise they stay red for good.
- **Follow-ups:**
  - F5: a pair ended by a later file that is not promoted re-checks the readers too (criteria 1, 2, 4, 5, 7 and 9). This makes amendment 27 (REQ-PIPE-121 criterion 1) needed rather than contingent, and changes its NEW text.
  - F7: in the terminal, the readers' re-check runs while you wait. It runs after the settlement's own runs and before the outcome panel, and the warning panel names it beforehand (criterion 8).
  - F8: the "reject both" scenario, TS-81, is planted by REQ-GEN-206, not here. The reasons are under REQ-GEN-206 below.
  - F14: must.
- It amends REQ-PIPE-193 criterion 23 (amendment 43, unchanged by F5) and REQ-PIPE-121 criterion 1 (amendment 27, revised).
- **Open:** an architect check only. Do REQ-PIPE-121 criteria 9 and 15, worded for a decision and a promotion, need amending for a contest ended by an arrival?

**REQ-DASH-182 (must): owed-nothing rows and the delivery time in force.**
- **No answer touched it.** It is as presented overnight, with your three 2026-10-13 answers already in.
- **Open:** nothing.

**REQ-PIPE-163 (must): placing a held supply.**
- **What changed:**
  - Q25: criteria 35 and 36 are kept.
  - Q23: criterion 16's period chooser now also picks a settlement's re-file target, and criterion 42 amends REQ-PIPE-193 criterion 19 (amendment 42 below).
  - Q27: the REQ-DASH-175 amendment, "Placed in <period>", is presented with this requirement (amendment 2 below; REQ-DASH-175 is unsigned).
- **Open, a note rather than a question:** criterion 26 names re-check, which does nothing until REQ-PIPE-164 is built.

**REQ-PIPE-179 (must): turning a dataset off.**
- **What changed:**
  - Q4: criterion 39 dates TS-63's correction before the gap. Its register entry must say that cp-carers reads "awaiting confirmation" from that date to the end of the history (the accepted cost).
  - Q2: your real identity approves it, and its reason says it is fictional.
- **Open, a build-time check:** whether the agreement backstop already notices a slot that vanished (criterion 38).

**REQ-DASH-180 (must): the turned-off dataset on the page.**
- **What changed (Q26, new wording):** criterion 27 adds the "Turning off after <effective_to>" marker. The dataset stays counted in its rollups while it shows. The marker gives way to criterion 4's or 25's wording once either applies.
- **Follow-up F9 (new wording):** criterion 27 now starts the marker on the date the turn-off was authored (its changelog entry's date) and runs it until effective_to. New criterion 28: a turn-off authored after its effective_to shows no marker at all.
- **Open:** two questions F9 raised (questions 1 and 2 below): which changelog entry dates a turn-off, and what dates a turn-off declared as a correction. Read literally, TS-63 never shows the marker.

**REQ-DASH-208 (should): a scenario link lands on what it is about.**
- **What changed (Q24, new wording):**
  - The jump now survives a reload. The scenario id rides in a lowercase `scenario` query parameter, and loading that URL repeats the jump.
  - It is dropped when you navigate away, and cleared quietly if it names nothing on the page (criteria 5, 8 and 9).
  - The REQ-GEN-199 amendment now asserts the text is in view again after a cold reload, and criterion 37 is amended too (amendments 9 and 10 below).
- **Follow-up F10:** criterion 10 makes each chip a real `<a href>` link carrying the as-of date and the scenario parameter. A plain click still jumps without a reload. No signed criterion calls the chip a button, so nothing is amended.
- **Open:** nothing.

**REQ-DASH-209 (NEW, should, unreviewed; Q16): the period-composition view.**
- **Story:** one view per period of a collection, with one row per dataset saying Promoted, Inherited from <period>, Substituted from <period> or Nothing held. Each row shows receipt, when it was decided, who decided (the person's name, or "the rule"), reason, and the status it was promoted on.
- **At thirty datasets:** it opens with a counting line ("30 datasets: 26 promoted, 2 inherited, 1 substituted, 1 nothing held"), with the unusual kinds first.
- **Where its data comes from:** `qa.slot_holds`, the metadata view `_manifest` itself takes its answers from. It never reads `_manifest`, because `_manifest` lists what is present by reading the period schema, which holds supply rows. A test proves the two agree.
- **TS-55's chip** opens it.
- **Follow-ups:**
  - F1: it has its own address per collection and period, linked from supply history and from the standing-in drill-down (criterion 6, as drafted).
  - F2: every collection has it, daily ones too, with one view per day (criterion 1).
  - F3 (new wording): who decided is the person's name, or "the rule" (criterion 3). The test maps each to `_manifest`'s "person" or "rule" (criterion 10).
  - F4: datasets holding nothing are listed as "Nothing held" (criterion 1, as drafted).
  - F15: the page's size is measured before and after and reported, with no budget (new criterion 11).
  - F14: should.
- **Open:** only the architect's check on REQ-GEN-045 (amendment 3, still contingent).

**REQ-GEN-205 (must): TS-57 to TS-62.**
- **What changed:**
  - Q2: you approve the fictional corrections.
  - Q5: the scripted confirmation lives in a top-level `corrections:` list (criterion 4).
  - Q6: exactly two corrections (criterion 20).
  - Q7: TS-62 is on Birth Registrations, and every correction is dated late (criteria 11 and 21).
  - Q8: one grown quarter's date per shape (criterion 22).
  - Q9: TS-61 stays parked to the end (criterion 23).
  - Q28: criterion 19 is gone. It is built (post-build-review #177, `correction_replay.history_end` and `confirm_due(history_end=)`), and a decision records that. The old criterion 20 (resume) is now 19.
- **Follow-up F11 (new wording):** TS-62's correction adds a new Birth Registrations daily version near the end of the history. It has a different claim window and stays pending (criteria 9 and 24). Criterion 25 makes it take effect after 2026-09-01, the last Birth Registrations day REQ-GEN-199 quotes, so those quotes do not move.
- **Open, and it needs you (question 5 below):** F11 conflicts with criterion 10 and five planted scenarios. TS-43 to TS-47 sit on Birth Registrations days after 2026-09-01, the last on 2026-09-21, and the history's final day, 2026-09-22, is TS-46's following day. A new version alters every slot from the day it takes effect, so criterion 10 makes generation refuse. As drafted, criteria 24 and 25 cannot be met together with criterion 10.
- **Open, a build-time check:** REQ-PIPE-111's synthetic exemption lets a past-dated version be added with no correction. Check that a correction declared for that version is still staged as a correction.
- **Not put to you:** cp-case-workers as TS-61's blocker is still the main session's provisional choice.

**REQ-GEN-206 (should): the rest of REQ-GEN-136 and 137, plus #175.**
- **What changed:**
  - Q10 (criterion 8): TS-48 is recorded as demonstrated by TS-75; TS-49 and TS-51 are not planted, with your reason. This amends REQ-GEN-136 criteria 5 and 9.
  - Q11, new wording (criterion 5): TS-53 is reject, then un-supersede, then a scripted person's promote, amending REQ-GEN-137 criterion 2.
  - Q12 (criterion 6): TS-50 is planted in full.
  - Q13: TS-54 rides TS-76.
  - Q14 (criterion 11): TS-47 gets a green following day.
  - Q15 (criterion 15): REQ-GEN-199 criterion 9 is reworded.
  - Q16 (criterion 4): TS-55's chip opens REQ-DASH-209.
- **Follow-ups:**
  - F8 (new wording): TS-81 is a Child Protection pair whose two files a scripted person rejects, planted in one grown quarter (criteria 16 to 18). It belongs here rather than on REQ-PIPE-211 for three reasons:
    - planting a scenario is generator work;
    - this requirement is built last, after REQ-PIPE-211, so TS-81's Expect is written against the fix rather than the defect;
    - on REQ-PIPE-211 it would make a must requirement wait for grown quarters and a full bootstrap.
    REQ-GEN-203 was also considered and rejected, because it is built before REQ-PIPE-211.
  - TS-81's shape is the scoper's provisional reading of "another grown quarter": no green targeting, no lead-ins, and the settlement the day after arrival. Say if you want it otherwise.
  - F12: TS-53 is on Birth Registrations (criterion 5).
  - F13: REQ-GEN-136 criterion 4 keeps its wording. Its unmet entry is cleared, with evidence naming TS-75, as a register change when this is built rather than as an amendment (criterion 8).
- **Open:** only the build-time check on #175's 8 September supply.

## Proposed amendments to signed requirements (complete)

**43 amendments to 24 requirements**, every one with exact wording: the 9 drafted on the morning of 2026-10-14, plus 34 drafted since. One target, REQ-DASH-175, is unsigned. Each is also recorded on the requirement that carries it, as a "PROPOSED AMENDMENT WORDING" decision. Every OLD text is copied from the live requirements.yaml. `<date built>` is the one placeholder: it is the date the amendment lands, written the way the register already dates its amendments.

Four kinds of entry need you more than the rest:

- **Not promised by the draft.** Found by reading the targets: REQ-PIPE-141 criterion 12 (amendment 33) and REQ-PIPE-170 criterion 26 (amendment 39). Without them, each contradicts REQ-PIPE-179. REQ-PIPE-170 criterion 28 (amendment 40) stretches REQ-PIPE-179 criterion 36 to the second place keep is offered.

- **Contingent.** REQ-GEN-045 criterion 1 (amendment 3) is a "check at build" item for the architect, drafted so you can approve exact words if it turns out to be needed. REQ-PIPE-121 criterion 1 (amendment 27) was contingent too. Since your follow-up F5 it is needed, and its NEW text changed.

- **Changed by the 15 follow-ups:** only amendment 27 (F5). F8 and F11 needed no amendment: TS-81 is a new scenario that no signed criterion promises, and criterion 25 keeps REQ-GEN-199's quotes where they are. Amendment 43 is unchanged: a later file superseding a pair is not a settlement, so amendment 27 carries that case.

- **Removes a guarantee on purpose.** Each is marked below and follows an answer you already gave.

- **No change needed.** Seven promises turned out to need nothing once the target was read. They are listed at the end.

### REQ-DASH-155 (signed 2026-10-06, built): The exhausted-schedule notice says how many supplies are waiting and since when

**1. REQ-DASH-155 criterion 1**. Carried by REQ-DASH-180 criterion 22.

- Old: "WHERE the dashboard shows the exhausted-schedule notice, THE SYSTEM SHALL state how many supplies are held because a schedule ended and the receipt date of the earliest of them."
- New: "WHERE the dashboard shows the exhausted-schedule notice, THE SYSTEM SHALL state how many supplies are held because a schedule ended - each hold's label worked out from the configuration in force on the in-place-on date (REQ-PIPE-179 criterion 18), so that a supply held as turned off is not counted - and the receipt date of the earliest of them. AMENDED <date built> by REQ-DASH-180 criterion 22."
- Why: the backlog counts only holds that adding dates would file.
- Built behaviour: BUILT CODE CHANGES (the notice's backlog count reads the recorded flag today); NOT STATED ELSEWHERE IN REQ-DASH-180, so its build needs a test of its own.

### REQ-DASH-175 (UNSIGNED, not_started): The dashboard says when a supply was placed by hand, or re-checked after we fixed a check

**2. REQ-DASH-175 criterion 12** (drafted this morning). Carried by REQ-PIPE-163 presented with it (decision, close-out Q27).

- Old: "THE SYSTEM SHALL describe a placement and a re-check in words wherever a past decision is described - 'placed in <period>', 're-checked' - and SHALL NOT show the raw operation name."
- New: "THE SYSTEM SHALL describe a placement and a re-check in words wherever a past decision is described - 'placed in <period>', 're-checked' - recognising a placement as a person's re-file whose from-period is empty (REQ-PIPE-163 criterion 2), and SHALL NOT show the raw operation name or describe a placement as a re-file."
- Why: Keith, close-out Q27: a placement is a re-file underneath, so the page must recognise it.
- Built behaviour: UNSIGNED and not_started - no built behaviour; it is a redraft rather than an amendment.

### REQ-GEN-045 (signed 2026-09-22, built): A generated scenario map says where each scenario can be seen

**3. REQ-GEN-045 criterion 1**. Carried by REQ-DASH-209 criterion 7.

- Old: "THE SYSTEM SHALL generate a map naming, for each injected scenario, the dataset, the supplies it produced, the period and the in-place-on date at which that scenario can be seen.
"
- New: "THE SYSTEM SHALL generate a map naming, for each injected scenario, the dataset - or, for a scenario about a whole period of a collection (REQ-DASH-209 criterion 7), the collection - the supplies it produced, the period and the in-place-on date at which that scenario can be seen.
 AMENDED <date built> by REQ-DASH-209 criterion 7."
- Why: criterion 1 requires every coordinate to name a dataset; a coordinate naming only a collection and a period would break it.
- Built behaviour: BUILT CODE CHANGES if needed (the scenario map's coordinate); built and tested by REQ-DASH-209 criterion 7.
- **Note:** CONTINGENT: needed only if TS-55's coordinate names no dataset. If it keeps naming the substituted dataset and adds the collection-and-period view as its target, no change is needed. REQ-DASH-209 leaves this to the architect.

### REQ-GEN-136 (signed 2026-10-04, built): Every arrival-driven shape of the option A and period-closing batch is planted in the synthetic history

**4. REQ-GEN-136 criterion 5** (drafted this morning). Carried by REQ-GEN-206 criterion 8.

- Old: "THE SYSTEM SHALL plant a correction whose re-check after its partner's promotion still fails, producing the decision log's large shout (REQ-PIPE-121)."
- New: "THE SYSTEM SHALL register, and SHALL NOT plant, TS-49 - a correction whose re-check after its partner's promotion still fails, producing the decision log's large shout (REQ-PIPE-121) - which Keith left unplanted (2026-10-11, confirmed 2026-10-14) because it needs named red cross-table targets and referential closure across six tables."
- Why: Keith, close-out Q10.
- Built behaviour: NO BUILT BEHAVIOUR CHANGES: criterion 5 is unmet.
- **Note:** REMOVES A GUARANTEE, deliberately: TS-49 will not be planted (Keith, Q10).

**5. REQ-GEN-136 criterion 9** (drafted this morning). Carried by REQ-GEN-206 criterion 8.

- Old: "THE SYSTEM SHALL plant a promoted supply whose cross-table result goes red when a sibling arrives later (REQ-DASH-126)."
- New: "THE SYSTEM SHALL register, and SHALL NOT plant, TS-51 - a promoted supply whose cross-table result goes red when a sibling arrives later (REQ-DASH-126) - which Keith left unplanted (2026-10-11, confirmed 2026-10-14) because it needs named red cross-table targets and referential closure across six tables."
- Why: Keith, close-out Q10.
- Built behaviour: NO BUILT BEHAVIOUR CHANGES: criterion 9 is unmet.
- **Note:** REMOVES A GUARANTEE, deliberately: TS-51 will not be planted (Keith, Q10).

### REQ-GEN-137 (signed 2026-10-04, built): The batch's person decisions, and the _manifest's three kinds of table, are planted in the synthetic history

**6. REQ-GEN-137 criterion 2** (drafted this morning). Carried by REQ-GEN-206 criterion 14.

- Old: "THE SYSTEM SHALL plant Keith's worked un-supersede case: a good file superseded by a bad later one; a person rejects the bad one and un-supersedes the good one, which is re-checked and promoted by the gate (REQ-PIPE-120)."
- New: "THE SYSTEM SHALL plant Keith's worked un-supersede case: a good file superseded by a bad later one; a person rejects the bad one and un-supersedes the good one, which is re-checked (REQ-PIPE-120), left waiting by the gate, and then promoted by a person."
- Why: Keith, close-out Q11 (option B): as built, the gate does not promote the un-superseded file without a further decision.
- Built behaviour: NO BUILT BEHAVIOUR CHANGES: criterion 2 is in REQ-GEN-137's unmet list; REQ-GEN-206 criterion 5 plants it.

### REQ-GEN-196 (signed 2026-10-13, built): Birth Registrations' generated history has a contested pair for every way a settlement can go, each settled by a scripted person - a duplicate send, a next day's file sent early, a later file chosen, a stray test file (one that loads and one that does not), both files rejected, and one file re-filed while the other is rejected

**7. REQ-GEN-196 a new decision**. Carried by REQ-PIPE-202 criterion 12.

- Old: "(none - decision 1 stays as history; this appends a decision. Decision 1 reads: "BIRTH REGISTRATIONS, NOT CHILD PROTECTION (2026-10-13, carried from REQ-PIPE-193): Child Protection's arrival patterns are exact filenames and cannot admit two files for one table (TS-34 and TS-42 record why), while birth_registrations_[^/]+\.csv admits two today. No pattern is widened; TS-42 stays not injectable.")"
- New: "SUPERSEDED IN PART BY REQ-PIPE-202 (Keith, 2026-10-13; recorded <date built> by REQ-PIPE-202 criterion 12): decision 1's "No pattern is widened; TS-42 stays not injectable" no longer holds - cp-clients' arrival pattern is `cp_clients(_[^/]+)?\.csv`, so TS-42 is planted by REQ-GEN-203. Every other Child Protection pattern stays exact, so TS-34 stays not injectable, and this requirement's own pairs stay on Birth Registrations."
- Why: a reader of REQ-GEN-196 must not take "no pattern is widened" as current.
- Built behaviour: TEXT ONLY - a decision, no criterion and no code.

### REQ-GEN-199 (signed 2026-10-13, built): The generated history has a scenario for each way the as-at panel and qualifier can read - awaiting then rejected, a substitution later removed, one later replaced, a supply promoted out of order, and cp-case-workers' inheritance named - each linked from the test-scenarios panel

**8. REQ-GEN-199 criterion 9** (drafted this morning). Carried by REQ-GEN-206 criterion 15.

- Old: "THE SYSTEM SHALL record in TS-76's register entry, as part of what TS-76 shows, the state cp-clients and cp-carers are left in for TS-76's quarter once the substitution is removed - promoted and red, permanently, as the delivery-architect found (H1) - and what cp-clients' and cp-carers' pages read before the substitution, while it stands and after it ends."
- New: "THE SYSTEM SHALL record in TS-76's register entry, as part of what TS-76 shows, the state cp-clients and cp-carers are left in for TS-76's quarter once the substitution is removed - cp-clients promoted amber and cp-carers green, as the first bootstrapped build showed (post-build-review #174), the cross-table checks reading cp_placements being filed under cp-placements and run for neither in a quarter with no placements supply - and what cp-clients' and cp-carers' pages read before the substitution, while it stands and after it ends."
- Why: Keith, close-out Q15: record what was observed, not what the architect predicted.
- Built behaviour: TEXT ONLY: a register entry's wording.

**9. REQ-GEN-199 criterion 36** (drafted this morning). Carried by REQ-DASH-208 criterion 6.

- Old: "THE SYSTEM SHALL have a needs_deployment real-browser test that, at a 1280x800 viewport, clicks each of this requirement's chips in the test-scenarios panel and asserts that the element holding the text its register Expect quotes is inside the initial viewport without scrolling, then cold-reloads that URL and asserts the same text with zero console errors."
- New: "THE SYSTEM SHALL have a needs_deployment real-browser test that, at a 1280x800 viewport, clicks each of this requirement's chips in the test-scenarios panel and asserts that the element holding the text its register Expect quotes is inside the viewport once the scenario jump (REQ-DASH-208) has brought it there, then cold-reloads that URL and asserts the same text inside the viewport again, with zero console errors."
- Why: Keith, close-out Q24: the jump is carried in the URL, so a reload lands on the subject too.
- Built behaviour: BUILT TEST CHANGES (the strict expected failures naming post-build-review #174 come out as each text comes into view); REQ-DASH-208 criterion 6.
- **Note:** RELAXES "without scrolling" to "once the jump has brought it there" - Keith chose a page fix that scrolls (Q24); the cold-reload assertion is STRENGTHENED to the viewport.

**10. REQ-GEN-199 criterion 37** (drafted this morning). Carried by REQ-DASH-208 criterion 6.

- Old: "IF the Expect's element is outside the initial 1280x800 viewport, THEN that SHALL be recorded as a finding against the page, and SHALL NOT be resolved by loosening the assertion or the Expect."
- New: "IF the Expect's element is outside the 1280x800 viewport once the scenario jump (REQ-DASH-208) has run, THEN that SHALL be recorded as a finding against the page, and SHALL NOT be resolved by loosening the assertion or the Expect."
- Why: follows criterion 36.
- Built behaviour: TEXT ONLY beyond criterion 36's test change.

### REQ-GHUB-082 (signed 2026-09-28, built): An operator records a filing decision from GitHub or from the terminal, and both write the same entry

**11. REQ-GHUB-082 criterion 1**. Carried by REQ-PIPE-163 criterion 13.

- Old: "THE SYSTEM SHALL accept promote, reject, demote, re-file, substitute, de-substitute, inherit, un-inherit, mark as not supplied, acknowledge, supersede, un-supersede, excuse lateness and withdraw excuse as structured filing decisions raised on the GitHub ticket for the SLOT they concern - one dataset in one period, per REQ-PIPE-083 - so that the period a decision applies to comes from the ticket's own identity rather than from anything stated in the body. Every criterion below that says "a filing decision" SHALL mean any one of those fourteen. AMENDED 2026-10-05 by REQ-PIPE-132 criterion 13 (mark as not supplied), REQ-PIPE-122 criterion 22 (acknowledge) and REQ-PIPE-120 criterion 9 (supersede, un-supersede), and 2026-10-11 by REQ-PIPE-161 criterion 13 (excuse lateness, withdraw excuse). Keep, and the confirmation of a calendar correction's moves, are filing decisions too, offered on the terminal route only (criterion 3) - AMENDED 2026-10-11 by REQ-PIPE-170 criterion 11. Settling a contested pair (choose-file) is a filing decision too, offered on the terminal route only (criterion 3) - AMENDED 2026-10-13 by REQ-PIPE-193 criterion 29."
- New: "THE SYSTEM SHALL accept promote, reject, demote, re-file, substitute, de-substitute, inherit, un-inherit, mark as not supplied, acknowledge, supersede, un-supersede, excuse lateness and withdraw excuse as structured filing decisions raised on the GitHub ticket for the SLOT they concern - one dataset in one period, per REQ-PIPE-083 - so that the period a decision applies to comes from the ticket's own identity rather than from anything stated in the body. Every criterion below that says "a filing decision" SHALL mean any one of those fourteen. AMENDED 2026-10-05 by REQ-PIPE-132 criterion 13 (mark as not supplied), REQ-PIPE-122 criterion 22 (acknowledge) and REQ-PIPE-120 criterion 9 (supersede, un-supersede), and 2026-10-11 by REQ-PIPE-161 criterion 13 (excuse lateness, withdraw excuse). Keep, and the confirmation of a calendar correction's moves, are filing decisions too, offered on the terminal route only (criterion 3) - AMENDED 2026-10-11 by REQ-PIPE-170 criterion 11. Settling a contested pair (choose-file) is a filing decision too, offered on the terminal route only (criterion 3) - AMENDED 2026-10-13 by REQ-PIPE-193 criterion 29. Placing a held supply (place) is a filing decision too, offered on the terminal route only (criterion 3) - AMENDED <date built> by REQ-PIPE-163 criterion 13."
- Why: place is a new filing decision, terminal only, and the list is meant to be complete.
- Built behaviour: BUILT CODE CHANGES (filing_decisions.OPERATIONS gains place); built and tested by REQ-PIPE-163 criteria 1, 13 and 36.

**12. REQ-GHUB-082 criterion 3**. Carried by REQ-PIPE-163 criterion 14.

- Old: "THE SYSTEM SHALL write an identical decision-log entry whichever route raised the decision, and SHALL NOT give either route an operation the other lacks, except the confirmation of a calendar correction's moves and the keeps it records, which is offered on the terminal route only (REQ-PIPE-170 criterion 10), and settling a contested pair (choose-file), which is offered on the terminal route only (REQ-PIPE-193 criteria 1 and 16). AMENDED 2026-10-11 by REQ-PIPE-170 criterion 11, and 2026-10-13 by REQ-PIPE-193 criterion 29.
"
- New: "THE SYSTEM SHALL write an identical decision-log entry whichever route raised the decision, and SHALL NOT give either route an operation the other lacks, except the confirmation of a calendar correction's moves and the keeps it records, which is offered on the terminal route only (REQ-PIPE-170 criterion 10), settling a contested pair (choose-file), which is offered on the terminal route only (REQ-PIPE-193 criteria 1 and 16), and placing a held supply (place), which is offered on the terminal route only (REQ-PIPE-163 criteria 14 and 36). AMENDED 2026-10-11 by REQ-PIPE-170 criterion 11, 2026-10-13 by REQ-PIPE-193 criterion 29, and <date built> by REQ-PIPE-163 criterion 14.
"
- Why: place is offered on the terminal route only, so it is a third exception to "neither route lacks an operation".
- Built behaviour: BUILT CODE CHANGES (the GitHub route replies and records nothing for place); built and tested by REQ-PIPE-163 criterion 36.

### REQ-PIPE-053 (signed 2026-09-22, built): A schedule that runs out is loud, and only for its own dataset

**13. REQ-PIPE-053 criterion 10**. Carried by REQ-PIPE-179 criterion 32.

- Old: "WHERE a calendar is an authored date list, THE SYSTEM SHALL warn when fewer than a configured number of future slots remain for a dataset naming it."
- New: "WHERE a calendar is an authored date list, THE SYSTEM SHALL warn when fewer than a configured number of future slots remain for a dataset naming it - counting, for a dataset in a temporary turned-off gap, only the periods it owes once turned back on - and SHALL NOT warn for a dataset turned off for good (REQ-PIPE-179 criterion 25). AMENDED <date built> by REQ-PIPE-179 criterion 32."
- Why: Keith's T6: a supplier turned off for good must not keep the runway warning firing.
- Built behaviour: BUILT CODE CHANGES (runway.calendar_runway); built and tested by REQ-PIPE-179 criterion 25.

**14. REQ-PIPE-053 criterion 15**. Carried by REQ-PIPE-179 criterion 32.

- Old: "WHEN a calendar is low on runway, THE SYSTEM SHALL warn once for that calendar, naming it, its last authored period and how many datasets name it, and SHALL NOT enumerate those datasets."
- New: "WHEN a calendar is low on runway, THE SYSTEM SHALL warn once for that calendar, naming it, its last authored period and how many datasets name it, not counting a dataset turned off for good (REQ-PIPE-179 criterion 25), and SHALL NOT enumerate those datasets. AMENDED <date built> by REQ-PIPE-179 criterion 32."
- Why: the per-calendar count must agree with criterion 10.
- Built behaviour: BUILT CODE CHANGES (the warning's count); built and tested by REQ-PIPE-179 criterion 25.

**15. REQ-PIPE-053 criterion 19**. Carried by REQ-DASH-180 criterion 22.

- Old: "THE SYSTEM SHALL evaluate the exhausted-schedule condition against the in-place-on date currently selected, and SHALL NOT report a schedule as exhausted while viewing a date its calendar covers."
- New: "THE SYSTEM SHALL evaluate the exhausted-schedule condition against the in-place-on date currently selected, and SHALL NOT report a schedule as exhausted while viewing a date its calendar covers, nor report a dataset as exhausted on a date it is turned off (REQ-PIPE-179). AMENDED <date built> by REQ-DASH-180 criterion 22."
- Why: a turned-off dataset owes nothing, so a run-out schedule is not its problem; criteria 16 to 18 render and count the condition this criterion evaluates, so they need no change of their own.
- Built behaviour: BUILT CODE CHANGES (the template's exhausted condition and dataset_status.py); built and tested by REQ-DASH-180 criterion 17.

### REQ-PIPE-064 (signed 2026-09-24, built): When nothing is confidently claimable, hold it for a human

**16. REQ-PIPE-064 criterion 5**. Carried by REQ-PIPE-179 criterion 24.

- Old: "THE SYSTEM SHALL report a held supply as an event needing action, distinguished from an informational one."
- New: "THE SYSTEM SHALL report a held supply as an event needing action, distinguished from an informational one - except a supply held as turned off (REQ-PIPE-179 criterion 24), which SHALL be reported as a quiet count and not as needing action. AMENDED <date built> by REQ-PIPE-179 criterion 24."
- Why: Keith's T3: a supplier still sending files after being asked to stop must not raise a needs-action item each time.
- Built behaviour: BUILT CODE CHANGES (every held supply counts as needing action today); built and tested by REQ-PIPE-179 criteria 24 and 34.
- **Note:** REMOVES A GUARANTEE, deliberately: a turned-off hold is no longer reported as needing action (Keith, T3, 2026-10-10).

**17. REQ-PIPE-064 criterion 8**. Carried by REQ-PIPE-179 criterion 32.

- Old: "THE SYSTEM SHALL count and report outstanding holds together, and SHALL NOT present one element per held supply."
- New: "THE SYSTEM SHALL count and report outstanding holds together, by label - turned off, schedule ended or the plain assignment-rule hold, each worked out from the configuration in force when the count is made (REQ-PIPE-179 criterion 18) - and SHALL NOT present one element per held supply. AMENDED <date built> by REQ-PIPE-179 criterion 32."
- Why: Keith's T4: a hold's label is worked out from current configuration everywhere, counts included.
- Built behaviour: BUILT CODE CHANGES (supply_holds.Tally reads the recorded flag today); built and tested by REQ-PIPE-179 criteria 18 and 26.

### REQ-PIPE-074 (signed 2026-09-26, built): Every filing decision is recorded once, in one append-only log that refuses an anonymous entry

**18. REQ-PIPE-074 criterion 1**. Carried by REQ-PIPE-163 criterion 13.

- Old: "THE SYSTEM SHALL record every filing decision - promote, reject, demote, re-file, mark as not supplied, acknowledge, supersede, un-supersede, excuse lateness, withdraw excuse, keep and choose-file - as an entry in one append-only log, and SHALL NOT keep a second record of any of them anywhere else. AMENDED 2026-10-05 by REQ-PIPE-132 criterion 13, REQ-PIPE-122 criterion 22 and REQ-PIPE-120 criterion 9, and 2026-10-11 by REQ-PIPE-161 criterion 13 and REQ-PIPE-170 criterion 11 (keep; confirming a calendar correction records each re-file, hold and keep it makes as its own entry here), and 2026-10-13 by REQ-PIPE-193 criterion 29 (choose-file - one entry for a settlement, with each file's rejection, supersession or re-file its own entry naming it as the cause)."
- New: "THE SYSTEM SHALL record every filing decision - promote, reject, demote, re-file, mark as not supplied, acknowledge, supersede, un-supersede, excuse lateness, withdraw excuse, keep, choose-file and place - as an entry in one append-only log, and SHALL NOT keep a second record of any of them anywhere else. AMENDED 2026-10-05 by REQ-PIPE-132 criterion 13, REQ-PIPE-122 criterion 22 and REQ-PIPE-120 criterion 9, and 2026-10-11 by REQ-PIPE-161 criterion 13 and REQ-PIPE-170 criterion 11 (keep; confirming a calendar correction records each re-file, hold and keep it makes as its own entry here), and 2026-10-13 by REQ-PIPE-193 criterion 29 (choose-file - one entry for a settlement, with each file's rejection, supersession or re-file its own entry naming it as the cause). And <date built> by REQ-PIPE-163 criterion 13 (place - recorded as a person's re-file from no period, REQ-PIPE-163 criterion 2, so it adds no decision-log action of its own)."
- Why: place is a filing decision and must be in the one log; the note says it is recorded as a re-file so nobody looks for a PLACE action.
- Built behaviour: BUILT CODE CHANGES only through REQ-PIPE-163 criterion 2 (no new action); tested there.

**19. REQ-PIPE-074 criterion 9**. Carried by REQ-PIPE-163 criterion 39.

- Old: "THE SYSTEM SHALL record a re-file as ONE entry carrying a from-slot, a to-slot and one reason, and SHALL NOT express it as a demotion followed by a promotion.
"
- New: "THE SYSTEM SHALL record a re-file as ONE entry carrying a from-slot, a to-slot and one reason, and SHALL NOT express it as a demotion followed by a promotion; WHERE a re-file places a held supply - by the rule (REQ-PIPE-154 criterion 7, REQ-PIPE-179 criterion 19) or by a person placing a supply with an open assignment-rule hold (REQ-PIPE-163 criterion 2) - it SHALL carry no from-slot, and IF a person's re-file names no from-slot for any other supply, THEN THE SYSTEM SHALL refuse it, naming place; and WHERE a confirmed correction holds a supply (REQ-PIPE-170 criterion 8), its re-file SHALL carry no to-slot. AMENDED <date built> by REQ-PIPE-163 criterion 39; the rule's and the correction's one-slot forms were built 2026-10-06 and 2026-10-11 and are stated here for the first time."
- Why: this is the criterion that states the decision log's re-file rule (qa_tools/common/decision_log.py), which REQ-PIPE-163 criterion 39 relaxes for a person's placement; it already omitted two one-slot forms the code accepts.
- Built behaviour: BUILT CODE CHANGES for the person's placement only (decision_log.py's REFILE check); built and tested by REQ-PIPE-163 criterion 39. The rule and correction halves are TEXT CATCH-UP of built behaviour.
- **Note:** Widens what the text says is accepted, but no guarantee is lost: the code already accepted the two one-slot forms, and a person's re-file with no from-slot stays refused except for placing.

### REQ-PIPE-076 (signed 2026-09-26, built): Rejection and un-decide are a person's decisions, and automation defers to a person permanently

**20. REQ-PIPE-076 criterion 7**. Carried by REQ-PIPE-163 criterion 24.

- Old: "WHERE any decision has been recorded against a supply by a person, THE SYSTEM SHALL NOT promote that supply automatically thereafter - EXCEPT un-supersede, re-file and an excuse of lateness or its withdrawal, the person-decisions after which the gate may still promote automatically, and the supersede un-supersede undoes (REQ-PIPE-120 criterion 4, REQ-PIPE-141 criterion 8, REQ-PIPE-161 criterion 19). AMENDED 2026-10-05 by REQ-PIPE-120 criterion 9 and REQ-PIPE-141 criterion 19, and 2026-10-11 by REQ-PIPE-161 criterion 19."
- New: "WHERE any decision has been recorded against a supply by a person, THE SYSTEM SHALL NOT promote that supply automatically thereafter - EXCEPT un-supersede, re-file (a person's placement of a held supply included, being recorded as a re-file - REQ-PIPE-163 criteria 2 and 24) and an excuse of lateness or its withdrawal, the person-decisions after which the gate may still promote automatically, and the supersede un-supersede undoes (REQ-PIPE-120 criterion 4, REQ-PIPE-141 criterion 8, REQ-PIPE-161 criterion 19). AMENDED 2026-10-05 by REQ-PIPE-120 criterion 9 and REQ-PIPE-141 criterion 19, 2026-10-11 by REQ-PIPE-161 criterion 19, and <date built> by REQ-PIPE-163 criterion 24."
- Why: a placement must not bar the gate, and it is recorded as a re-file, which this criterion already exempts.
- Built behaviour: PROBABLY NO CODE CHANGE: rejection.decided_by_a_person already leaves REFILE out (read 2026-10-14), so a placement recorded as a re-file is exempt; REQ-PIPE-163 criterion 24 still needs a test proving it.

### REQ-PIPE-098 (signed 2026-09-28, built): A dataset that does not participate in a period stands on its most recent supply, by a view created when the period is born

**21. REQ-PIPE-098 criterion 1**. Carried by REQ-PIPE-179 criterion 32.

- Old: "WHEN a period's schema is first created, THE SYSTEM SHALL INHERIT, for each dataset the schedule says does not participate in that period, that dataset's most recent promoted supply - creating in the new period's schema a view that resolves the dataset's logical name to it.
"
- New: "WHEN a period's schema is first created, THE SYSTEM SHALL INHERIT, for each dataset the schedule says does not participate in that period or is turned off in it (REQ-PIPE-179 criterion 22), that dataset's most recent promoted supply - creating in the new period's schema a view that resolves the dataset's logical name to it.
 AMENDED <date built> by REQ-PIPE-179 criterion 32."
- Why: Keith's Q-G: a turned-off period inherits the last promoted supply, so cross-table checks do not read the table as missing.
- Built behaviour: BUILT CODE CHANGES (inheritance._does_not_participate via the one helper); built and tested by REQ-PIPE-179 criterion 22.

### REQ-PIPE-111 (signed 2026-10-07, built): A delivery agreement's past changes only by a declared, approved correction

**22. REQ-PIPE-111 criterion 2**. Carried by REQ-PIPE-179 criterion 30.

- Old: "THE SYSTEM SHALL treat each dated calendar entry, each dated entry of a dataset's own authored dates, calendar version, participation version (including a collection's default participation), not_expected entry and timezone version as FROZEN from the first instant it can govern a filing - for a dated entry, the earliest claim-opening instant that EVERY dataset on its calendar would have for that period, participating or not, since that instant also closes each one's previous period; for a not_expected entry, that dataset's claim-opening instant for the period; for a version, the earlier of the start of its effective-from date and the earliest claim-opening instant of any period it governs."
- New: "THE SYSTEM SHALL treat each dated calendar entry, each dated entry of a dataset's own authored dates, calendar version, participation version (including a collection's default participation), not_expected entry and timezone version as FROZEN from the first instant it can govern a filing - for a dated entry, the earliest claim-opening instant that EVERY dataset on its calendar would have for that period, participating or not - a dataset turned off in that period (REQ-PIPE-179) counted only where it is the first period of its gap, whose claim-opening instant closes the last owed slot before it (REQ-PIPE-179 criterion 14) - since that instant also closes each one's previous period; for a not_expected entry, that dataset's claim-opening instant for the period; for a version, the earlier of the start of its effective-from date and the earliest claim-opening instant of any period it governs; except that a participation version's effective_to and turned_off_reason are not frozen with their version but on their own, as REQ-PIPE-179 criteria 11 and 12 state. AMENDED <date built> by REQ-PIPE-179 criterion 30."
- Why: effective_to has its own freeze point (Keith, Q-K), and only the first period of a gap closes a slot, so only it can freeze a dated entry for a turned-off dataset.
- Built behaviour: BUILT CODE CHANGES (agreement_freeze); built and tested by REQ-PIPE-179 criteria 11 and 12.

**23. REQ-PIPE-111 criterion 4**. Carried by REQ-PIPE-179 criterion 30.

- Old: "THE SYSTEM SHALL carry declared corrections in a `corrections:` list on each OWNING ITEM, beside its versions - a calendar's on that calendar; a dataset's (its participation, due time, participates, not_expected and own authored dates) on that dataset's entry; a collection's participation_defaults on that collection's entry (amended by REQ-PIPE-181); the zone's on the timezone - each correction stating change_reference, date, author, approver, reason, and a list of changes each naming the item, its old value and its new value; and SHALL refuse a correction missing any of them."
- New: "THE SYSTEM SHALL carry declared corrections in a `corrections:` list on each OWNING ITEM, beside its versions - a calendar's on that calendar; a dataset's (its participation, due time, participates, not_expected, own authored dates, effective_to and turned_off_reason) on that dataset's entry; a collection's participation_defaults, their effective_to and turned_off_reason included, on that collection's entry (amended by REQ-PIPE-181); the zone's on the timezone - each correction stating change_reference, date, author, approver, reason, and a list of changes each naming the item, its old value and its new value; and SHALL refuse a correction missing any of them. AMENDED <date built> by REQ-PIPE-179 criterion 30."
- Why: a correction must be able to carry the two new frozen items.
- Built behaviour: BUILT CODE CHANGES (agreement_freeze's correction matching); built and tested by REQ-PIPE-179 criteria 11, 12 and 39 (TS-63's correction).

**24. REQ-PIPE-111 criterion 15**. Carried by REQ-PIPE-179 criterion 30.

- Old: "WHEN a change is refused, THE SYSTEM SHALL report it as the existing configuration errors do (file, where, problem, fix), grouped by item, saying that nothing was committed, naming the item in exactly the syntax a correction uses, printing a ready-to-paste correction entry with the item, old and new values filled in and reason, approver and change_reference as placeholders, listing who may approve, naming the impact preview command (REQ-PIPE-169), and - for a not_expected entry - naming mark as not supplied (REQ-PIPE-132) as the after-the-fact route."
- New: "WHEN a change is refused, THE SYSTEM SHALL report it as the existing configuration errors do (file, where, problem, fix), grouped by item, saying that nothing was committed, naming the item in exactly the syntax a correction uses, printing a ready-to-paste correction entry with the item, old and new values filled in and reason, approver and change_reference as placeholders, listing who may approve, naming the impact preview command (REQ-PIPE-169), and - for a not_expected entry or an effective_to - naming mark as not supplied (REQ-PIPE-132) as the after-the-fact route. AMENDED <date built> by REQ-PIPE-179 criterion 30."
- Why: a missed period before a turn-off is recorded after the fact the same way as one before a not_expected entry.
- Built behaviour: BUILT CODE CHANGES (refusal text); NO OTHER CRITERION STATES IT, so REQ-PIPE-179's build needs its own test for this wording.

### REQ-PIPE-113 (signed 2026-10-07, built): A slot's due instant comes from the participation in force on its period's date, and a later change never moves an earlier slot

**25. REQ-PIPE-113 criterion 2**. Carried by REQ-PIPE-179 criterion 31.

- Old: "THE SYSTEM SHALL take a slot's expected time, days before, grace allowance and claim-window override each as the value REQ-PIPE-181 resolves for that period's own date, from the dataset or its collection, and its default claim window from the calendar version in force on that date (amended by REQ-PIPE-181)."
- New: "THE SYSTEM SHALL take a slot's expected time, days before, grace allowance and claim-window override each as the value REQ-PIPE-181 resolves for that period's own date, from the dataset or its collection - through the one participation resolution of REQ-PIPE-179 criterion 27, so that a collection inside its own turned-off gap supplies no value (REQ-PIPE-179 criterion 7) - and its default claim window from the calendar version in force on that date (amended by REQ-PIPE-181, and <date built> by REQ-PIPE-179 criterion 31)."
- Why: inside a collection's gap the collection supplies no values (Keith, T1), so a back-on dataset's slot takes only its own.
- Built behaviour: BUILT CODE CHANGES (slots via the one helper); built and tested by REQ-PIPE-179 criteria 7 and 27.

**26. REQ-PIPE-113 criterion 4**. Carried by REQ-PIPE-179 criterion 31.

- Old: "THE SYSTEM SHALL compute each slot's closing instant (REQ-PIPE-131) from the next calendar period's claim-opening instant as that next period's own inputs give it, so that a version change takes effect at its own boundary and nowhere before it."
- New: "THE SYSTEM SHALL compute each slot's closing instant (REQ-PIPE-131) from the next calendar period's claim-opening instant as that next period's own inputs give it, so that a version change takes effect at its own boundary and nowhere before it; WHERE the dataset is turned off in that next period, from the claim-opening instant it would have had, each value resolved as if every effective_to on or before its date were absent (REQ-PIPE-179 criterion 14). AMENDED <date built> by REQ-PIPE-179 criterion 31."
- Why: a period inside a gap has no slot, so without this the last owed slot before a gap would have no closing instant.
- Built behaviour: BUILT CODE CHANGES (slots.py closing instant); built and tested by REQ-PIPE-179 criterion 14.

### REQ-PIPE-121 (signed 2026-10-04, built): A table arriving in or leaving a period re-checks the waiting supplies in that period that read it, and re-applies the gate - through one mechanism

**27. REQ-PIPE-121 criterion 1**. Carried by REQ-PIPE-211 criterion 1.

- Old: "WHEN a table arrives in or leaves a period schema - promoted by a rule or a person, re-filed in or out, superseded, demoted or rejected - THE SYSTEM SHALL re-evaluate, within that period only, every cross-table check that declares it reads the moved table, whether it belongs to a supply WAITING in that period or one PROMOTED there, and SHALL NOT re-evaluate any check that does not read a moved table."
- New (REVISED 2026-10-14 for follow-up F5): "WHEN a table arrives in or leaves a period schema - promoted by a rule or a person, re-filed in or out, superseded, demoted or rejected - or the contest of a table in that period ends, by a person's settlement of the pair whatever its outcome or by a later arrival superseding the pair whether or not that arrival is promoted (REQ-PIPE-211), THE SYSTEM SHALL re-evaluate, within that period only, every cross-table check that declares it reads the moved table or the table whose contest ended, whether it belongs to a supply WAITING in that period or one PROMOTED there, and SHALL NOT re-evaluate any check that reads neither. AMENDED <date built> by REQ-PIPE-211 criterion 1."
- Why: a contested pair's files are staged, never in the period schema. A settlement that leaves nothing promoted, or a later file superseding the pair and left waiting, moves no table into or out of it. So as worded, criterion 1 does not trigger, and its last clause forbids re-evaluating a check that reads no moved table.
- Built behaviour: BUILT CODE CHANGES with REQ-PIPE-193 criterion 23 (knock_on gains a trigger); built and tested by REQ-PIPE-211.
- **Note:** NO LONGER CONTINGENT, since F5. REQ-PIPE-193 criterion 23 can carry a settlement's knock-on, but a later arrival's supersession is not a settlement, and this criterion is the list of the one handler's triggers. The text changed from the morning draft: "a contested pair ... is settled" became "the contest ... ends", naming both ways it ends, and "the moved or settled table" became "the moved table or the table whose contest ended". The architect may still place the supersession trigger elsewhere (REQ-PIPE-118).

### REQ-PIPE-131 (signed 2026-10-04, built): A period closes once its calendar's next period's claim window opens, so a file is only ever filed to the one open period

**28. REQ-PIPE-131 criterion 1**. Carried by REQ-PIPE-179 criterion 31.

- Old: "THE SYSTEM SHALL treat a dataset's slot as OPEN from its claim-opening instant until the claim-opening instant that dataset would have for the NEXT PERIOD OF ITS CALENDAR - whether or not the dataset participates in that next period - and as CLOSED from then on."
- New: "THE SYSTEM SHALL treat a dataset's slot as OPEN from its claim-opening instant until the claim-opening instant that dataset would have for the NEXT PERIOD OF ITS CALENDAR - whether or not the dataset participates in that next period or is turned off in it (REQ-PIPE-179) - and as CLOSED from then on. AMENDED <date built> by REQ-PIPE-179 criterion 31."
- Why: the same closing rule applies across a turned-off gap as across a period not participated in.
- Built behaviour: BUILT CODE CHANGES with criterion 2 below; built and tested by REQ-PIPE-179 criterion 14.

**29. REQ-PIPE-131 criterion 2**. Carried by REQ-PIPE-179 criterion 31.

- Old: "THE SYSTEM SHALL compute that next claim-opening instant from the next calendar period's date with each value as REQ-PIPE-181 resolves it on that next period's date (amended by REQ-PIPE-181)."
- New: "THE SYSTEM SHALL compute that next claim-opening instant from the next calendar period's date with each value as REQ-PIPE-181 resolves it on that next period's date (amended by REQ-PIPE-181) - or, WHERE the dataset is turned off in that next period, as if every effective_to on or before that date were absent (REQ-PIPE-179 criterion 14; AMENDED <date built> by REQ-PIPE-179 criterion 31)."
- Why: inside a gap nothing resolves (the collection supplies no values), so the closing instant is computed as if the turn-off were absent.
- Built behaviour: BUILT CODE CHANGES (slots.py); built and tested by REQ-PIPE-179 criterion 14.

### REQ-PIPE-134 (signed 2026-10-04, built): A dataset's periods never overlap - enforced in CI from configuration

**30. REQ-PIPE-134 criterion 1**. Carried by REQ-PIPE-179 criterion 31.

- Old: "THE SYSTEM SHALL require, for every dataset and every pair of consecutive periods of that dataset's calendar - whether or not the dataset participates in either - that the claim-opening instant the dataset would have for the later period is strictly after the late-after instant (due instant plus grace) the dataset would have for the earlier one."
- New: "THE SYSTEM SHALL require, for every dataset and every pair of consecutive periods of that dataset's calendar - whether or not the dataset participates in either - that the claim-opening instant the dataset would have for the later period is strictly after the late-after instant (due instant plus grace) the dataset would have for the earlier one; WHERE either period of a pair lies inside a turned-off gap (REQ-PIPE-179), THE SYSTEM SHALL instead check the last owed period before the gap against the closing instant REQ-PIPE-179 criterion 14 gives it and, WHERE the gap is temporary, require the first owed slot after it to open strictly after the last owed slot before it closes, and SHALL NOT check any pair both of whose periods lie inside the gap. AMENDED <date built> by REQ-PIPE-179 criterion 31."
- Why: inside a gap a period has no resolved values to check, and the overlap that matters is between the owed slots either side of it.
- Built behaviour: BUILT CODE CHANGES (period_overlap / validate_schedule); NO OTHER CRITERION STATES IT, so REQ-PIPE-179's build needs its own tests for all three clauses.

### REQ-PIPE-140 (signed 2026-10-04, built): A decision can run a supply's QA again, on demand, as a run of its own that never overwrites the first

**31. REQ-PIPE-140 new criterion 9**. Carried by REQ-PIPE-163 criterion 31.

- Old: "(none - criteria 1 to 8 are unchanged; this is a new criterion 9)"
- New: "THE SYSTEM SHALL have every runner of an owed run - the terminal's filing-decisions door, `mothman supply decide --wait` (REQ-PIPE-163 criterion 25) and the processing pass - claim the run before running it, SHALL release a claim when the process holding it ends, and SHALL have a runner that finds the run claimed skip it and leave it owed, saying that it is being run elsewhere (REQ-PIPE-163 criterion 30). ADDED <date built> by REQ-PIPE-163 criterion 31: the claim was built 2026-10-11 (post-build-review #136, recheck.run's advisory lock) and is stated here for the first time."
- Why: the claim is built and no criterion states it.
- Built behaviour: TEXT CATCH-UP for the door and the processing pass (built 2026-10-11); the decide --wait runner is new and is REQ-PIPE-163 criterion 25's to build.

### REQ-PIPE-141 (signed 2026-10-04, built): Re-filing a supply returns it to staging under a new filing for its new period, where it is checked and the normal gate decides

**32. REQ-PIPE-141 criterion 7**. Carried by REQ-PIPE-163 criterion 25.

- Old: "THE SYSTEM SHALL then run the re-filed supply's QA against the target period through REQ-PIPE-140, and SHALL apply the promotion gate to it exactly as for a first arrival, with the amber and replacement settings in force at that instant (REQ-PIPE-122, REQ-PIPE-123), not those in force when it first arrived or was first checked."
- New: "THE SYSTEM SHALL then run the re-filed supply's QA against the target period through REQ-PIPE-140, and SHALL apply the promotion gate to it exactly as for a first arrival, with the amber and replacement settings in force at that instant (REQ-PIPE-122, REQ-PIPE-123), not those in force when it first arrived or was first checked; WHERE the re-file is recorded through `mothman supply decide --wait`, that run SHALL happen in the foreground straight after the decision commits, ending with REQ-PIPE-163 criterion 26's shared outcome panel, and WHERE it is recorded through decide without --wait, the run SHALL be left owed (REQ-PIPE-140 criterion 7). AMENDED <date built> by REQ-PIPE-163 criterion 25."
- Why: decide --wait now covers re-file as well as place and re-check (Keith, round 3 Q1).
- Built behaviour: BUILT CODE CHANGES (decide gains --wait); built and tested by REQ-PIPE-163 criteria 25 to 30.

**33. REQ-PIPE-141 criterion 12**. Carried by REQ-PIPE-179 criterion 20.

- Old: "IF a person re-files a supply into a period where its dataset's slot is resolved by INHERITANCE, THEN THE SYSTEM SHALL refuse it, say that nothing was expected for that period, and name un-inherit as the step that must come first."
- New: "IF a person re-files a supply into a period where its dataset's slot is resolved by INHERITANCE, THEN THE SYSTEM SHALL refuse it, say that nothing was expected for that period, and name un-inherit as the step that must come first - except WHERE that period lies inside a turned-off gap (REQ-PIPE-179), when REQ-PIPE-179 criterion 20's refusal SHALL be given in its place. AMENDED <date built> by REQ-PIPE-179 criterion 20."
- Why: a gap period inherits (REQ-PIPE-179 criterion 22), so this criterion would advise un-inherit, which does not make a gap period owed - the same narrowing REQ-PIPE-163 criterion 8 makes for a placement.
- Built behaviour: BUILT CODE CHANGES (refiling.plan's refusal); built and tested by REQ-PIPE-179 criterion 20.
- **Note:** NOT PROMISED BY THE DRAFT - found by reading criterion 12 against REQ-PIPE-179 criteria 20 and 22.

### REQ-PIPE-154 (signed 2026-10-06, built): A supply arriving after its dataset's schedule has ended is held as schedule-ended, and says what to edit

**34. REQ-PIPE-154 criterion 1**. Carried by REQ-PIPE-179 criterion 32.

- Old: "IF a supply arrives after the last slot of its dataset's authored calendar has closed, THEN THE SYSTEM SHALL hold it for a person under REQ-PIPE-064 with a reason stating that the dataset's delivery schedule has ended and naming that dataset's own last authored period."
- New: "IF a supply arrives after the last slot of its dataset's authored calendar has closed, THEN THE SYSTEM SHALL hold it for a person under REQ-PIPE-064 with a reason stating that the dataset's delivery schedule has ended and naming that dataset's own last authored period - unless the dataset is turned off for the period whose slot would then be current, when the hold is labelled turned off instead (REQ-PIPE-179 criterion 17). AMENDED <date built> by REQ-PIPE-179 criterion 32."
- Why: turned off outranks schedule ended (Keith confirmed, 2026-10-13, set 2 Q7(a)): "add the next dates" would not make a turned-off dataset owe anything.
- Built behaviour: BUILT CODE CHANGES (assignment / supply_holds labelling); built and tested by REQ-PIPE-179 criterion 17.

**35. REQ-PIPE-154 criterion 2**. Carried by REQ-PIPE-179 criterion 32.

- Old: "THE SYSTEM SHALL record whether a hold was raised because the schedule ended as a structured field of the hold, and SHALL NOT require any reader to parse the hold's prose to tell."
- New: "THE SYSTEM SHALL record whether a hold was raised because the schedule ended as a structured field of the hold, kept as history, and SHALL NOT require any reader to parse the hold's prose to tell; every reader that labels, re-files or counts a hold SHALL take its label from the configuration in force when it reads (REQ-PIPE-179 criterion 18), not from that field. AMENDED <date built> by REQ-PIPE-179 criterion 32."
- Why: Keith's T4: the recorded flag is history; the label shown, re-filed on and counted is worked out from current configuration.
- Built behaviour: BUILT CODE CHANGES (readers of the recorded flag); built and tested by REQ-PIPE-179 criterion 18.

**36. REQ-PIPE-154 criterion 6**. Carried by REQ-PIPE-179 criterion 32.

- Old: "WHEN a processing pass holds one or more supplies because their dataset's schedule has ended, THE SYSTEM SHALL state in that pass's own summary how many datasets and how many supplies were held for that reason, separately from any other holds."
- New: "WHEN a processing pass holds one or more supplies because their dataset's schedule has ended, THE SYSTEM SHALL state in that pass's own summary how many datasets and how many supplies were held for that reason - the label worked out as REQ-PIPE-179 criterion 18 says - separately from any other holds, turned-off holds included (REQ-PIPE-179 criterion 26). AMENDED <date built> by REQ-PIPE-179 criterion 32."
- Why: the pass counts by the worked-out label, and turned-off holds are their own count.
- Built behaviour: BUILT CODE CHANGES (the pass summary); built and tested by REQ-PIPE-179 criteria 18 and 26.

**37. REQ-PIPE-154 criterion 7**. Carried by REQ-PIPE-179 criterion 32.

- Old: "WHEN dates are added to a dataset's calendar that cover the receipt instant of a supply held because its schedule ended, THE SYSTEM SHALL re-file that supply by the filing rule on the next processing pass, in receipt order with every other supply so held, and SHALL resolve its hold naming the filing that replaced it."
- New: "WHEN configuration later gives an outstanding assignment-rule hold's receipt instant an open owed slot - dates added to a dataset's calendar covering a supply held because its schedule ended, or any other change, whatever the hold's label (REQ-PIPE-179 criterion 19) - THE SYSTEM SHALL re-file that supply by the filing rule on the next processing pass, in receipt order with every other supply so held, and SHALL resolve its hold naming the filing that replaced it. AMENDED <date built> by REQ-PIPE-179 criterion 32."
- Why: Keith, round 3 Q8 and set 2 Q6: one re-filer for every hold configuration later covers, not a second one for turned-off holds.
- Built behaviour: BUILT CODE CHANGES (schedule_ended.refile_covered widens to every label, including the eight Case Workers holds); built and tested by REQ-PIPE-179 criterion 19.
- **Note:** WIDENS a built behaviour: plain assignment-rule holds, including holds a correction or a settlement raised, will start being filed by the rule when configuration covers them.

### REQ-PIPE-170 (signed 2026-10-07, built): After a correction, the data asset's manager confirms the proposed filing moves all at once, and may keep any supply where it is

**38. REQ-PIPE-170 criterion 5**. Carried by REQ-PIPE-179 criterion 36.

- Old: "THE SYSTEM SHALL let the asset manager exclude individual supplies and then confirm every remaining move, across every dataset and agency the correction touches, in one action."
- New: "THE SYSTEM SHALL let the asset manager exclude individual supplies and then confirm every remaining move, across every dataset and agency the correction touches, in one action; IF the corrected configuration makes a supply's current period one its dataset owes nothing in - by participation, not_expected or a turn-off - THEN THE SYSTEM SHALL NOT offer to exclude (keep) that supply, and SHALL propose moving it to the owed slot the filing rule gives it, or holding it, saying that the period no longer owes a supply. AMENDED <date built> by REQ-PIPE-179 criterion 36."
- Why: Keith, round 3 Q9: a supply kept in a period with no slot, which inherits and accepts no placement, would have three rules disagreeing about one period.
- Built behaviour: BUILT CODE CHANGES (correction_trial / confirm-correction); REQ-PIPE-179 criterion 36 is the only statement, so its build needs a test of its own.
- **Note:** REMOVES A GUARANTEE, deliberately: the asset manager can no longer keep such a supply where it is (Keith, round 3 Q9).

**39. REQ-PIPE-170 criterion 26**. Carried by REQ-PIPE-179 criterion 37.

- Old: "WHEN a processing pass finds a parked move whose blocker has cleared, THE SYSTEM SHALL carry it out to the period confirmed, as the rule naming who confirmed it, before any arrival in that pass, and SHALL NOT do so for a dataset the agreement backstop refuses (REQ-PIPE-173)."
- New: "WHEN a processing pass finds a parked move whose blocker has cleared, THE SYSTEM SHALL carry it out to the period confirmed, as the rule naming who confirmed it, before any arrival in that pass, and SHALL NOT do so for a dataset the agreement backstop refuses (REQ-PIPE-173), nor WHERE the confirmed period now lies inside a turned-off gap, when the move stays parked and says so (REQ-PIPE-179 criterion 37). AMENDED <date built> by REQ-PIPE-179 criterion 37."
- Why: criterion 26 says a cleared parked move SHALL be carried out; REQ-PIPE-179 criterion 37 says one into a turned-off gap stays parked - the two contradict unless 26 is amended.
- Built behaviour: BUILT CODE CHANGES (the processing pass's parked-move step); built and tested by REQ-PIPE-179 criteria 20 and 37.
- **Note:** NOT PROMISED BY THE DRAFT - found by reading criterion 26 against REQ-PIPE-179 criterion 37.

**40. REQ-PIPE-170 criterion 28**. Carried by REQ-PIPE-179 criterion 36.

- Old: "WHILE a move is parked, THE SYSTEM SHALL let the data asset's manager keep the supply where it is instead, with a reason, recorded as a keep against that correction, through mothman supply confirm-correction --keep on the confirmed reference and from the filing menu."
- New: "WHILE a move is parked, THE SYSTEM SHALL let the data asset's manager keep the supply where it is instead, with a reason, recorded as a keep against that correction, through mothman supply confirm-correction --keep on the confirmed reference and from the filing menu - except WHERE the supply's current period is one its dataset now owes nothing in, when keep SHALL NOT be offered (criterion 5). AMENDED <date built> by REQ-PIPE-179 criterion 36."
- Why: the scoper's reading: keep on a parked move is the same act as keep at confirmation, so the same exception applies.
- Built behaviour: BUILT CODE CHANGES (confirm-correction --keep on a parked move); NOT IN REQ-PIPE-179 criterion 36 AS WORDED, which says only "keep is not offered for that supply" - needs a test.
- **Note:** PROPOSED BY THE SCOPER, not promised by the draft in words - an extension of criterion 36 to the second place keep is offered.

### REQ-PIPE-173 (signed 2026-10-07, built): The pipeline refuses a dataset whose judged past changed without a declared correction

**41. REQ-PIPE-173 criterion 12**. Carried by REQ-PIPE-179 criterion 38.

- Old: "THE SYSTEM SHALL treat a judged period that a not_expected entry now declares owed nothing as changed, so it refuses the dataset unless a declared correction of that entry accounts for it (added 2026-10-11, Keith's answer (i))."
- New: "THE SYSTEM SHALL treat a judged period that a not_expected entry, or an effective_to added or moved (REQ-PIPE-179), now declares owed nothing as changed, so it refuses the dataset unless a declared correction of that entry or that effective_to accounts for it (added 2026-10-11, Keith's answer (i); AMENDED <date built> by REQ-PIPE-179 criterion 38)."
- Why: a turn-off removes a judged slot exactly as a not_expected entry does, and the backstop must see either.
- Built behaviour: POSSIBLY BUILT CODE CHANGE: whether agreement_drift already flags a vanished slot is REQ-PIPE-179's open question; test first either way.

### REQ-PIPE-193 (signed 2026-10-13, built): A person settles a contested pair in the terminal - saying, for EACH of its two files, whether it is this period's supply, is re-filed to another period, is rejected, or is kept but superseded - and each file that becomes a supply is filed, checked and gated on its own receipt

**42. REQ-PIPE-193 criterion 19** (drafted this morning). Carried by REQ-PIPE-163 criterion 42.

- Old: "IF a re-file target is refused, THEN THE SYSTEM SHALL say why and ask for the period again, before the reason is asked and keeping both files' answers; the target prompt SHALL offer the next period as its default."
- New: "WHEN a file's outcome is a re-file, THE SYSTEM SHALL ask for its target period through REQ-PIPE-163 criterion 16's period chooser, with the next period as its first choice, and SHALL NOT ask for a typed period; IF a re-file target is refused, THEN THE SYSTEM SHALL say why and offer the chooser again, before the reason is asked and keeping both files' answers."
- Why: Keith, close-out Q23: periods are never typed in the terminal.
- Built behaviour: BUILT CODE CHANGES (settle_tui's typed prompt becomes the chooser); built and tested by REQ-PIPE-163 criterion 16.

**43. REQ-PIPE-193 criterion 23** (drafted this morning). Carried by REQ-PIPE-211 criterion 6.

- Old: "WHEN a settlement moves a file into or out of a period, and WHEN a settled supply is promoted, THE SYSTEM SHALL owe the knock-on through REQ-PIPE-121's one handler (knock_on), which selects the checks by reevaluation.reading_checks() and the datasets by reevaluation.counts_toward(), and SHALL NOT add a settlement-specific path or restate either rule."
- New: "WHEN a pair is settled, whatever its outcome (REQ-PIPE-211), WHEN a settlement moves a file into or out of a period, and WHEN a settled supply is promoted, THE SYSTEM SHALL owe the knock-on through REQ-PIPE-121's one handler (knock_on), which selects the checks by reevaluation.reading_checks() and the datasets by reevaluation.counts_toward(), and SHALL NOT add a settlement-specific path or restate either rule."
- Why: Keith, close-out Q21: after "reject both" the readers would otherwise stay red for good.
- Built behaviour: BUILT CODE CHANGES (settlement.apply owes a knock-on it does not today); built and tested by REQ-PIPE-211 criteria 1 to 8.
- **Note:** unchanged by follow-up F5: a later file superseding the pair is not a settlement, and amendment 27 carries that case.

### No change needed

- **REQ-PIPE-083 criterion 21** (named by REQ-PIPE-179 criterion 24): its needs-action ticket policy is per SLOT, and a held supply has no slot and so no ticket (REQ-PIPE-083's own decision, "A HELD SUPPLY HAS NO SLOT AND SO HAS NO TICKET") - so a turned-off hold never raises one. Criterion 24's "and REQ-PIPE-083 criterion 21" can be dropped.
- **REQ-PIPE-053 criterion 4** (named by REQ-PIPE-179 criterion 32): it says only that such a supply is held, and already gives its labelling to REQ-PIPE-154, whose criterion 1 is amended. A turned-off supply is still held. Criterion 32's "criteria 4, 10 and 15" can read "criteria 10 and 15".
- **REQ-PIPE-053 criteria 16, 17 and 18** (named by REQ-DASH-180 criterion 22): they render, keep out of the rollup and count the exhausted condition, which criterion 19 evaluates; amending 19 alone carries all three.
- **REQ-DASH-155 criterion 3** (named by REQ-DASH-180 criterion 22): it is worded on the same test as criterion 1 ("no supply is held because a schedule ended"), so amending 1's count carries it. One corner is left for the architect: a temporary gap running past the calendar's last date could leave turned-off holds received after the schedule ended, making "nothing has arrived since the schedule ended" untrue.
- **REQ-PIPE-154 criterion 7** (named by REQ-PIPE-163 (folded decision, 2026-10-10)): REQ-PIPE-163's own decision records that amendment as SUPERSEDED by round 3 Q7: schedule-ended holds are never placed or rejected, which REQ-PIPE-163 criterion 22 states. Only REQ-PIPE-179's amendment to criterion 7 remains.
- **REQ-PIPE-170 its unmet entry for criterion 23** (named by REQ-PIPE-179 criterion 40): the live register already reads "TS-57 to TS-62 ... TS-63 moved to REQ-PIPE-179 criterion 39 (Keith, 2026-10-13)" in both criterion 23 and its unmet entry. Criterion 40 is already met in the register and can be dropped.
- **REQ-PIPE-163 criterion 17** (named by REQ-PIPE-179 (round 3 decision)): REQ-PIPE-179's decision "163 NO LONGER AMENDED HERE" records that 163 is written turn-off-aware (Keith, set 1 Q1). REQ-PIPE-163 is unsigned in any case.

### Register bookkeeping, not amendments

Clearing an unmet entry once its scenario is planted is done when the scenario is built and needs no wording from you: REQ-GEN-136 criterion 3 (REQ-GEN-203 criterion 9), REQ-GEN-136 criteria 4, 5, 8, 9 and 11 and REQ-GEN-137 criteria 2, 5 and 6 (REQ-GEN-206; criterion 4's entry is cleared with evidence naming TS-75 and its wording stays, follow-up F13), and REQ-PIPE-170 criterion 23 (REQ-GEN-205). REQ-PIPE-202 criterion 9 changes tests, not a requirement.

## Still open: questions for you (recommended option first)

All 15 follow-up questions are answered and folded in. Four answers raised new questions, below. Question 5 needs answering before REQ-GEN-205 can be built the way you chose. For relaying: questions 1 to 4 fit one AskUserQuestion call, and question 5 a second.

### Set A: when the "Turning off after" marker starts (raised by F9; REQ-DASH-180)
1. **Which changelog entry dates the turn-off?** A version's changelog is a list of free-text entries, and effective_to is often added to a version that already exists. "The version's changelog date" could then be the day the version was first written, years before anyone decided the turn-off. That is the failure you rejected option C for.
   - A) The entry that adds effective_to says so in a structured field (for example `turns_off: true`). REQ-PIPE-179's configuration check refuses a version that states effective_to with no such entry.
   - B) The newest changelog entry on that version. No new key, but any later edit to the version moves the marker's start.
   - C) The earliest entry. Simplest, and wrong whenever effective_to was added later.
2. **A turn-off declared as a correction.** Every synthetic changelog entry is dated the real day it was written (2026-10-11 to 14 in contract/calendar.yaml today), after the synthetic history ends on 2026-09-22. TS-63's turn-off, though, is a correction dated inside the history (close-out Q4). Read literally, F9 means TS-63 never shows the marker, and no scenario shows criterion 27.
   - A) Where a declared correction set or moved effective_to, the marker starts from that correction's date. Otherwise it starts from the changelog entry. TS-63's register entry then quotes the marker.
   - B) The changelog entry only, as answered. Criterion 27 is shown by fixture tests alone.
   - C) Date the changelog entry on TS-63's version inside the history, fictionally, as its correction is dated.

### Set B: the terminal's count (raised by F6; REQ-PIPE-210)
3. **A reader with nothing to sit beneath.** A reader is listed beneath its cause only where the cause has an item of its own in the queue. An overdue cp_clients supply has none, so its readers are rows of their own, each saying nothing needs deciding on it. PROVISIONAL in criterion 7: they are counted as today.
   - A) Don't count them either, for F6's reason (the count is the number of things to decide). A line under the count says how many readers are waiting on another table.
   - B) Count them, as drafted. Every row in the queue is counted, and nothing needs explaining.
4. **The page's own counts.** Each agency and collection card counts supplies waiting for a person. NFR 3 says the page and the terminal decide through one function.
   - A) The same rule on the page: a reader whose red comes wholly from another table is not counted as waiting for a person, and its cause's line carries it. This would add a criterion to REQ-DASH-204.
   - B) The terminal only, as F6 was asked. The page keeps counting every waiting supply.

### Set C: TS-62 (raised by F11; REQ-GEN-205)
5. **The version you chose conflicts with five planted scenarios.** Checked 2026-10-14 in generator/scenario_injection.py and the register:
   - TS-43 to TS-47 sit on Birth Registrations days after 2026-09-01. TS-47 lands on 2026-09-07, and its whole point is the 4-hour claim window. TS-44 and TS-45 are in an era from 2026-09-10. TS-46 is on 2026-09-21, and the history's last day, 2026-09-22, is its green following day.
   - A new version alters every slot from the day it takes effect. REQ-GEN-205's criterion 10 counts all those periods as claimed, so generation refuses.
   - The 2026-09-01 bound protects REQ-GEN-199's quotes, but not those five scenarios'.

   The options:
   - A) Keep the new version, and:
     - make it take effect after 2026-09-08, TS-47's following day;
     - narrow criterion 10, for a version-level correction only, to the periods its impact preview says it would MOVE (plus one either side);
     - before the rebuild, show you the preview proving TS-43 to TS-46's filings do not move.
   - B) Go back to a not_expected entry for one past day, in a free stretch before TS-43 (F11's option A). Three days claimed, no exception.
   - C) Keep the version as answered, waive criterion 10 for TS-62, and re-observe TS-43 to TS-47's Expects after the first bootstrap. Those scenarios belong to requirements that are signed and built.

### Not questions, but provisional, so say if you want them otherwise
- TS-81's shape (REQ-GEN-206): one grown quarter, no green targeting or lead-ins, and the settlement the day after arrival. This reads F8's "another grown quarter" as one.
- TS-80's outcome (REQ-GEN-203): the stray test file rejected and the real extract kept.
- cp-case-workers as TS-61's blocker (REQ-GEN-205).

### Build-time checks (for the architect, not for you)
- REQ-DASH-209 / REQ-GEN-045: whether amendment 3 is needed.
- REQ-PIPE-211: whether REQ-PIPE-121 criteria 9 and 15 need amending for a contest ended by an arrival.
- REQ-GEN-205: whether a correction declared for a version added to a synthetic asset is staged as a correction.
- REQ-DASH-204: which notice each cause has, to end with "Affects".
- REQ-PIPE-179: whether the agreement backstop already notices a vanished slot.
- REQ-GEN-206: #175's 8 September supply.

## Non-functional angles on the three new requirements

**Answered by the scoper:**
- **Scale (thirty datasets):** one row per cause or per dataset, with counting lines.
- **Build rule:** the view reads `qa.slot_holds`, never the period schema.
- **Reliability:** 211's re-check is owed in the settlement's transaction and finished by the processing pass if interrupted.
- **No false quiet or false green:** 210's criterion 4 and 211's re-evaluation never drop a check.
- **Accessibility and portability:** no new asset; the file:// path is unaffected.
- **Auditability:** 211's results name the settlement as their cause.
- **Multi-agency:** the view is per collection.

**Ruled out:** compliance and retention, and cost (no new compute beyond cross-table checks).

**Answered by you:** REQ-DASH-209's page size is measured before and after and reported, with no budget (F15).

**New from F7:** someone settling a pair in the terminal now also waits for the readers' re-check. REQ-PIPE-211 names the re-check in the warning panel beforehand, so the wait is expected.

## Plans files, to apply alongside (drafts only, not written)
- **plans/running-thoughts.md #93:** delete it in the change that adds REQ-DASH-209 to requirements.yaml (it is now scoped), and repoint any reference to REQ-DASH-209.
- **plans/post-build-review.md #174:** append "Keith's answers 2026-10-14 (close-out Q15, Q24): the page fix is REQ-DASH-208, with the jump carried in the URL; criterion 9's wording is amended by REQ-GEN-206 criterion 15." It stays todo until those are built.
- **plans/post-build-review.md #175:** append "Keith's answer 2026-10-14 (close-out Q14): option 1, carried by REQ-GEN-206 criterion 11."
- **plans/post-build-review.md #177:** already done. REQ-GEN-205's draft criterion 19 is now removed, as its last line said it would be.

## Keith's answers (2026-10-14 morning, via AskUserQuestion)

- Q1: A - REQ-GEN-207 is its own requirement, built first; today's quarters stay byte-identical.
- Q2: A - Keith's real identity approves the fictional corrections; each reason says it is fictional.
- Q3: A - REQ-GEN-203 builds Child Protection lead-ins and targeting.
- Q4: A - TS-63's turn-off correction is dated before the gap.
- Q5: A - a top-level `corrections:` list in contract/scripted_decisions.yaml.
- Q6: A - two corrections: one confirmed carrying TS-57 to TS-61, one left pending.
- Q7: A - TS-62 on Birth Registrations; every correction dated late in the history.
- Q8: A - each correction edits one grown quarter's date per shape.
- Q9: A - TS-61 stays parked to the end, a standing item.
- Q10: A - TS-48 counts as demonstrated by TS-75; TS-49 and TS-51 not planted, Keith's reason recorded.
- Q11: B (NOT the recommendation) - TS-53 gets a person's promote, and REQ-GEN-137 criterion 2 is amended to match.
- Q12: A - TS-50 planted in full, in a grown quarter under a short Child Protection green-replacement era.
- Q13: A - TS-54 rides TS-76.
- Q14: A - build TS-47's following day green and record why its late file is held.
- Q15: A - reword REQ-GEN-199 criterion 9 to what was observed (clients amber, carers green).
- Q16: B (NOT the recommendation) - draft a period-composition view on the dashboard for TS-55; a new requirement to scope.
- Q17: A - every cross-table cause gets the line.
- Q18: A - row note, "Affects ..." on the contested banner, and one line on the collection card.
- Q19: A - page and terminal; a small pipeline requirement drafted now for the terminal queue.
- Q20: A - REQ-DASH-204 is Must.
- Q21: A - after "reject both", readers are re-checked via a small pipeline follow-up.
- Q22: A - the Child Protection Synthetic-mode picker lists a two-file arrival marked, and refuses when picked.
- Q23: A - the period chooser also replaces the typed period in the settle flow's re-file (amends REQ-PIPE-193).
- Q24: B (NOT the recommendation) - a scenario jump survives a reload, carried in the URL (REQ-DASH-208).
- Q25: A - keep REQ-PIPE-163 criteria 35 and 36.
- Q26: B (NOT the recommendation) - add the "Turning off after <date>" foreshadow marker to REQ-DASH-180.
- Q27: A - amend REQ-DASH-175 ("Placed in <period>"), presented with REQ-PIPE-163.
- Q28: A - a replayed correction's confirmation is stamped at the later of the history's end and the correction's own date (post-build-review #177).

Answers are not sign-off: the draft is re-folded with these, the five
non-recommended answers (Q11, Q16, Q24, Q26, and Q16's new view) get
criteria drafted, and each requirement then goes to Keith for sign-off.

## Keith's answers to the 15 follow-up questions (2026-10-14, via AskUserQuestion)

- F1: A - REQ-DASH-209 has its own address per collection and period, linked from each period row of a dataset's supply history and from the standing-in drill-down.
- F2: A - every collection, daily ones too.
- F3: the person's name, as the rest of the page shows ("the rule" where no person decided). Note: the main session presented this as the recommendation, reversing the scoper's order (it recommended "rule"/"person" as _manifest says), for consistency with REQ-DASH-198's stand-in fix.
- F4: A - datasets holding nothing are listed as "Nothing held" with the slot's state.
- F5: A - a pair ended by a later file that is not promoted also re-checks the readers.
- F6: A - a reader listed beneath its cause does NOT count in "Supplies waiting on a decision (N)".
- F7: A - in the terminal the readers' re-check runs while you wait, with the settlement's own runs.
- F8: B (NOT the recommendation) - plant a "reject both" Child Protection scenario, at the cost of another grown quarter (REQ-GEN-207's dry run must include it).
- F9: B (NOT the recommendation) - the "Turning off after <date>" marker shows from the date the turn-off version was authored (its changelog entry date), on any date on show from then.
- F10: A - a scenario chip becomes a real <a href> link.
- F11: B (NOT the recommendation) - TS-62's Birth Registrations correction is a new daily version near the end of the history with a different claim window. Consequence to carry: once confirmed it would re-judge every later day, but TS-62 is the correction LEFT PENDING, so its moves show as awaiting confirmation; its effective date must fall after every quoted Birth Registrations scenario day (TS-78 ends 2026-09-01) or REQ-GEN-199's quotes move - REQ-GEN-207's dry run / REQ-GEN-205 should check that.
- F12: A - TS-53 is on Birth Registrations.
- F13: A - REQ-GEN-136 criterion 4 keeps its wording; its unmet entry is cleared with evidence naming TS-75.
- F14: B - REQ-PIPE-211 is must; REQ-DASH-209 and REQ-PIPE-210 are should.
- F15: A - REQ-DASH-209's page weight is measured before and after and reported, with no budget yet.

Folded 2026-10-14. Each answer is a decision citing "Keith, 2026-10-14, follow-up FN", and each answered question is gone from its requirement. F5 revised amendment 27. F6, F9 and F11 raised the new questions under "Still open" above. Answers are still not sign-off.

## Keith's answers to the round 4 questions (2026-10-14, via AskUserQuestion)

- R1 (TS-62, scoper's new question 5 + architect D): A - TS-62's new daily version takes effect after 2026-09-08, clear of TS-47's window; REQ-GEN-205's "nothing else moves" rule (criterion 10) is narrowed, for a version-level correction, to the periods the correction's impact preview would move; TS-46's last day checked at build; the new claim window is wider (e.g. 6h) so the default view stays quiet.
- R2 (the still-failing shout, architect C / CLI UX 3): Keith - "Shout, but don't say it's waiting on a person. Wouldn't this be the same shout you'd get if the tables it depends on just never turned up?" So: the still-failing record stays, worded to name what the readers wait on (REQ-DASH-204 criterion 15's cause wording) and never "A person decides", where every red is another table's; a reader with its own fault keeps today's wording. Checked in knock_on.py for his question: NO - today a table that never turns up raises no shout at all, because the shout is only raised by a re-evaluation, and only a move or (after REQ-PIPE-211) the end of a contest causes one. A never-arrived dependency leaves the readers red, explained on the page and in the queue (REQ-PIPE-115's reason), with nothing in the decision log. The asymmetry is that the shout records a decision's consequence; put back to Keith.
- R3 (TS-79b's text, architect A): A - reword to "the oldest of the original fifteen quarters".
- R4 (exit code, CLI UX A2): A - REQ-PIPE-163's distinct "recorded, still owed" code when a settlement is recorded but a run or the readers' re-check is left owed. Amends built REQ-PIPE-193.
- R2 follow-up (should "reject both" still shout, given a never-arrived table raises none?): Keith asked first what the page shows today when a dependency never arrives. Checked (unrunnable.py, qa.check_result): it depends on the dependency's state AT THE READER'S ARRIVAL, recorded once and never revisited. Not yet due -> the cross-table check records `nodata` ("not evaluated - not yet supplied, not yet overdue"), the reader can read GREEN and be promoted, and nothing re-checks it when the dependency later goes overdue or never comes (a false green). Already overdue, contested or awaiting a decision -> the check records `fail` ("could not be evaluated"), which rolls up, so the reader reads RED with no failure of its own (real example: a cp-investigations run, zero own failures, red for a missing cp_carers). Keith's instinct: that is neither a true green nor a true red.
- R5 (a distinct "waiting on another table" state, and re-checking 'not yet due' readers when the dependency goes overdue): SCOPE IT FIRST (Keith) - a design question for the scoper and architect, decided as part of that scoping, alongside this batch. REQ-DASH-204, REQ-PIPE-210, REQ-PIPE-211 and the shout question all hang on it. Logged as plans/running-thoughts.md #95.
- R6 (REQ-DASH-209 at 30 datasets, dashboard UX D1): B (NOT the recommendation) - every row open; no collapsing of rule-promoted-on-green rows.
- R7 (REQ-DASH-209 "Nothing held", D2): A - split: "Not supplied" (owed: red or waiting) at the top, "Not owed" (turned off, not expected, outside agreed months) at the bottom, each counted.
- R8 (REQ-DASH-180 marker date, scoper new Q1 + D3): A - the changelog entry setting the turn-off carries `turns_off: true`, checked by validation; where a correction sets it, the correction's own date; validation refuses a turn-off with no such entry.

## Sign-off walk (2026-10-14)

- REQ-GEN-207: SIGNED by Keith, 2026-10-14, with the round 4 architect's changes folded in (a new earlier calendar version; today's plan passes the widened clash rule; the seven oldest-quarter indexes drawn separately with a byte proof; a before/after results comparison reported as findings; TS-79b reworded). Moved out of this draft into requirements.yaml.
- REQ-PIPE-202: SIGNED by Keith, 2026-10-14, criterion 4's reader status deferred to running-thoughts #95; amendment 7 approved with it. Moved into requirements.yaml.
- REQ-GEN-203: SIGNED by Keith, 2026-10-14, readers' status deferred to running-thoughts #95, REQ-PIPE-211 added as a dependency. Moved into requirements.yaml.
