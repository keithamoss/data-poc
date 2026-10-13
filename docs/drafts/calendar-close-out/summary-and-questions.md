# Calendar close-out batch: for sign-off

Keith - this is the batch with your answers of 2026-10-14 morning folded in. **None of it is signed, and requirements.yaml has not changed.** The full text is in `requirements-draft.yaml` next to this file, with the three overnight reviews (`review-*.md`). Merged with the live register it passes `mothman dashboard validate-requirements` (206 requirements, zero errors).

Every answer that took the recommendation now uses the wording already drafted for it, and each is recorded in its requirement's `decisions:` as "Keith, 2026-10-14, close-out QN". **Answers are not sign-off**, so each requirement below still needs your yes.

**New wording you have not seen yet** (each marked "NEW WORDING - for Keith's approval" in the YAML):
- Q11: TS-53 with a person's promote (REQ-GEN-206 criterion 5), and the REQ-GEN-137 criterion 2 amendment.
- Q16: the whole of REQ-DASH-209, the period-composition view.
- Q24: REQ-DASH-208 criteria 5, 8 and 9, the scenario jump carried in the URL.
- Q26: REQ-DASH-180 criterion 27, the "Turning off after <date>" marker.
- Q17 also needed new words: REQ-DASH-204 criterion 15 gives each cause its own line and next step. You chose the option, not the wording.
- Q19 and Q21: the two new pipeline requirements, REQ-PIPE-210 and REQ-PIPE-211.

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

REQ-DASH-208 and REQ-DASH-209 must come before the first REQ-GEN-205 or 206 bootstrap, because TS-55's chip opens 209's view.

## The requirements, in build order

**REQ-GEN-207 (must): grow the Child Protection history earlier, once.**
- **Story:** add quarters before 2023, sized by a dry run of the collision check, so each new scenario has a quarter of its own and no planted scenario moves.
- **What changed:** you chose option A (Q1). It is its own requirement, built first, and today's quarters stay byte-identical.
- The dry run now counts what your other answers added: Child Protection lead-in quarters (Q3), TS-50's era and lead-ins (Q12), and every period the confirmed correction claims.
- TS-62 is left out of the dry run because it is on Birth Registrations (Q7).
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
- **Open:** whether such a reader still counts in "Supplies waiting on a decision (N)" (question 6 below).

**REQ-PIPE-211 (NEW, should, unreviewed): settling a pair re-checks its readers, whatever the outcome.**
- **Story:** after "reject both" (and any other settlement), the readers' contested results are re-evaluated through the one knock-on handler. Otherwise they stay red for good.
- It amends REQ-PIPE-193 criterion 23 (amendment 8 below).
- **Open:**
  - whether a pair ended by a later, unpromoted file counts too;
  - whether the terminal runs the re-check while you wait;
  - whether to plant a reject-both scenario;
  - an architect check on REQ-PIPE-121 criterion 1.

**REQ-DASH-182 (must): owed-nothing rows and the delivery time in force.**
- **No answer touched it.** It is as presented overnight, with your three 2026-10-13 answers already in.
- **Open:** nothing.

**REQ-PIPE-163 (must): placing a held supply.**
- **What changed:**
  - Q25: criteria 35 and 36 are kept.
  - Q23: criterion 16's period chooser now also picks a settlement's re-file target, and criterion 42 amends REQ-PIPE-193 criterion 19 (amendment 7 below).
  - Q27: the REQ-DASH-175 amendment, "Placed in <period>", is presented with this requirement (amendment 9 below; REQ-DASH-175 is unsigned).
- **Open, a note rather than a question:** criterion 26 names re-check, which does nothing until REQ-PIPE-164 is built.

**REQ-PIPE-179 (must): turning a dataset off.**
- **What changed:**
  - Q4: criterion 39 dates TS-63's correction before the gap. Its register entry must say that cp-carers reads "awaiting confirmation" from that date to the end of the history (the accepted cost).
  - Q2: your real identity approves it, and its reason says it is fictional.
- **Open, a build-time check:** whether the agreement backstop already notices a slot that vanished (criterion 38).

**REQ-DASH-180 (must): the turned-off dataset on the page.**
- **What changed (Q26, new wording):** criterion 27 adds the "Turning off after <effective_to>" marker. The dataset stays counted in its rollups while it shows. The marker gives way to criterion 4's or 25's wording once either applies.
- **Open:** when the marker starts (question 9 below). I proposed the last owed period's claim opening, so it cannot appear years early on a past date.

**REQ-DASH-208 (should): a scenario link lands on what it is about.**
- **What changed (Q24, new wording):**
  - The jump now survives a reload. The scenario id rides in a lowercase `scenario` query parameter, and loading that URL repeats the jump.
  - It is dropped when you navigate away, and cleared quietly if it names nothing on the page (criteria 5, 8 and 9).
  - The REQ-GEN-199 amendment now asserts the text is in view again after a cold reload, and criterion 37 is amended too (amendments 5 and 6 below).
- **Open:** whether the chips become real links (question 10 below).

**REQ-DASH-209 (NEW, should, unreviewed; Q16): the period-composition view.**
- **Story:** one view per period of a collection, with one row per dataset saying Promoted, Inherited from <period>, Substituted from <period> or Nothing held. Each row shows receipt, when it was decided, rule or person, reason, and the status it was promoted on.
- **At thirty datasets:** it opens with a counting line ("30 datasets: 26 promoted, 2 inherited, 1 substituted, 1 nothing held"), with the unusual kinds first.
- **Where its data comes from:** `qa.slot_holds`, the metadata view `_manifest` itself takes its answers from. It never reads `_manifest`, because `_manifest` lists what is present by reading the period schema, which holds supply rows. A test proves the two agree.
- **TS-55's chip** opens it.
- **Open:** four design questions (set 1 below), and an architect check on whether REQ-GEN-045's coordinate shape (signed) needs amending.

**REQ-GEN-205 (must): TS-57 to TS-62.**
- **What changed:**
  - Q2: you approve the fictional corrections.
  - Q5: the scripted confirmation lives in a top-level `corrections:` list (criterion 4).
  - Q6: exactly two corrections (criterion 20).
  - Q7: TS-62 is on Birth Registrations, and every correction is dated late (criteria 11 and 21).
  - Q8: one grown quarter's date per shape (criterion 22).
  - Q9: TS-61 stays parked to the end (criterion 23).
  - Q28: criterion 19 is gone. It is built (post-build-review #177, `correction_replay.history_end` and `confirm_due(history_end=)`), and a decision records that. The old criterion 20 (resume) is now 19.
- **Open:** what TS-62's correction edits on Birth Registrations, whose calendar is a daily rule with no dates list (question 11 below).
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
- **Open:**
  - TS-53's collection (question 12 below);
  - whether REQ-GEN-136 criterion 4 needs rewording for TS-75's shape (question 13 below);
  - a build-time check on #175's 8 September supply.

## Proposed amendments to other requirements, exact wording

Each is also recorded on the requirement that carries it as a "PROPOSED AMENDMENT WORDING" decision. The old text is copied from the live requirements.yaml.

**1. REQ-GEN-137 criterion 2** (signed 2026-10-04; close-out Q11 (option B, not the recommendation); carried by REQ-GEN-206 criterion 14)

- Old: "THE SYSTEM SHALL plant Keith's worked un-supersede case: a good file superseded by a bad later one; a person rejects the bad one and un-supersedes the good one, which is re-checked and promoted by the gate (REQ-PIPE-120)."
- New: "THE SYSTEM SHALL plant Keith's worked un-supersede case: a good file superseded by a bad later one; a person rejects the bad one and un-supersedes the good one, which is re-checked (REQ-PIPE-120), left waiting by the gate, and then promoted by a person."

**2. REQ-GEN-199 criterion 9** (signed 2026-10-13; close-out Q15; carried by REQ-GEN-206 criterion 15)

- Old: "THE SYSTEM SHALL record in TS-76's register entry, as part of what TS-76 shows, the state cp-clients and cp-carers are left in for TS-76's quarter once the substitution is removed - promoted and red, permanently, as the delivery-architect found (H1) - and what cp-clients' and cp-carers' pages read before the substitution, while it stands and after it ends."
- New: "THE SYSTEM SHALL record in TS-76's register entry, as part of what TS-76 shows, the state cp-clients and cp-carers are left in for TS-76's quarter once the substitution is removed - cp-clients promoted amber and cp-carers green, as the first bootstrapped build showed (post-build-review #174), the cross-table checks reading cp_placements being filed under cp-placements and run for neither in a quarter with no placements supply - and what cp-clients' and cp-carers' pages read before the substitution, while it stands and after it ends."

**3. REQ-GEN-136 criterion 5** (signed 2026-10-04; close-out Q10; carried by REQ-GEN-206 criterion 8)

- Old: "THE SYSTEM SHALL plant a correction whose re-check after its partner's promotion still fails, producing the decision log's large shout (REQ-PIPE-121)."
- New: "THE SYSTEM SHALL register, and SHALL NOT plant, TS-49 - a correction whose re-check after its partner's promotion still fails, producing the decision log's large shout (REQ-PIPE-121) - which Keith left unplanted (2026-10-11, confirmed 2026-10-14) because it needs named red cross-table targets and referential closure across six tables."

**4. REQ-GEN-136 criterion 9** (signed 2026-10-04; close-out Q10; carried by REQ-GEN-206 criterion 8)

- Old: "THE SYSTEM SHALL plant a promoted supply whose cross-table result goes red when a sibling arrives later (REQ-DASH-126)."
- New: "THE SYSTEM SHALL register, and SHALL NOT plant, TS-51 - a promoted supply whose cross-table result goes red when a sibling arrives later (REQ-DASH-126) - which Keith left unplanted (2026-10-11, confirmed 2026-10-14) because it needs named red cross-table targets and referential closure across six tables."

**5. REQ-GEN-199 criterion 36** (signed 2026-10-13; close-out Q24 (option B, not the recommendation); carried by REQ-DASH-208 criterion 6)

- Old: "THE SYSTEM SHALL have a needs_deployment real-browser test that, at a 1280x800 viewport, clicks each of this requirement's chips in the test-scenarios panel and asserts that the element holding the text its register Expect quotes is inside the initial viewport without scrolling, then cold-reloads that URL and asserts the same text with zero console errors."
- New: "THE SYSTEM SHALL have a needs_deployment real-browser test that, at a 1280x800 viewport, clicks each of this requirement's chips in the test-scenarios panel and asserts that the element holding the text its register Expect quotes is inside the viewport once the scenario jump (REQ-DASH-208) has brought it there, then cold-reloads that URL and asserts the same text inside the viewport again, with zero console errors."

**6. REQ-GEN-199 criterion 37** (signed 2026-10-13; close-out Q24; carried by REQ-DASH-208 criterion 6)

- Old: "IF the Expect's element is outside the initial 1280x800 viewport, THEN that SHALL be recorded as a finding against the page, and SHALL NOT be resolved by loosening the assertion or the Expect."
- New: "IF the Expect's element is outside the 1280x800 viewport once the scenario jump (REQ-DASH-208) has run, THEN that SHALL be recorded as a finding against the page, and SHALL NOT be resolved by loosening the assertion or the Expect."

**7. REQ-PIPE-193 criterion 19** (signed 2026-10-13; close-out Q23; carried by REQ-PIPE-163 criterion 42)

- Old: "IF a re-file target is refused, THEN THE SYSTEM SHALL say why and ask for the period again, before the reason is asked and keeping both files' answers; the target prompt SHALL offer the next period as its default."
- New: "WHEN a file's outcome is a re-file, THE SYSTEM SHALL ask for its target period through REQ-PIPE-163 criterion 16's period chooser, with the next period as its first choice, and SHALL NOT ask for a typed period; IF a re-file target is refused, THEN THE SYSTEM SHALL say why and offer the chooser again, before the reason is asked and keeping both files' answers."

**8. REQ-PIPE-193 criterion 23** (signed 2026-10-13; close-out Q21; carried by REQ-PIPE-211 criterion 6)

- Old: "WHEN a settlement moves a file into or out of a period, and WHEN a settled supply is promoted, THE SYSTEM SHALL owe the knock-on through REQ-PIPE-121's one handler (knock_on), which selects the checks by reevaluation.reading_checks() and the datasets by reevaluation.counts_toward(), and SHALL NOT add a settlement-specific path or restate either rule."
- New: "WHEN a pair is settled, whatever its outcome (REQ-PIPE-211), WHEN a settlement moves a file into or out of a period, and WHEN a settled supply is promoted, THE SYSTEM SHALL owe the knock-on through REQ-PIPE-121's one handler (knock_on), which selects the checks by reevaluation.reading_checks() and the datasets by reevaluation.counts_toward(), and SHALL NOT add a settlement-specific path or restate either rule."

**9. REQ-DASH-175 criterion 12** (UNSIGNED; close-out Q27; carried by presented with REQ-PIPE-163)

- Old: "THE SYSTEM SHALL describe a placement and a re-check in words wherever a past decision is described - 'placed in <period>', 're-checked' - and SHALL NOT show the raw operation name."
- New: "THE SYSTEM SHALL describe a placement and a re-check in words wherever a past decision is described - 'placed in <period>', 're-checked' - recognising a placement as a person's re-file whose from-period is empty (REQ-PIPE-163 criterion 2), and SHALL NOT show the raw operation name or describe a placement as a re-file."

**Amendments carried from earlier rounds, wording NOT yet drafted.** REQ-PIPE-163 and REQ-PIPE-179 still say "amend, in the same change" for several signed requirements without exact text:
- REQ-GHUB-082 criteria 1 and 3, REQ-PIPE-074 criterion 1, REQ-PIPE-076 criterion 7, REQ-PIPE-140 and REQ-PIPE-141 (from 163);
- REQ-PIPE-111 criteria 2, 4 and 15; REQ-PIPE-113 criteria 2 and 4; REQ-PIPE-131 criteria 1 and 2; REQ-PIPE-134 criterion 1; REQ-PIPE-154 criteria 1, 2, 6 and 7; REQ-PIPE-064 criteria 5 and 8; REQ-PIPE-083 criterion 21; REQ-PIPE-098 criterion 1; REQ-PIPE-053 criteria 4, 10 and 15; REQ-PIPE-170 and REQ-PIPE-173 (from 179);
- REQ-PIPE-053 criteria 16 to 19 and REQ-DASH-155 criteria 1 and 3 (from 180).

Their decisions say "that wording comes to Keith at sign-off", and this fold did not draft it. It is still owed, and it is the biggest thing left open in this batch.

## Still open: questions for you (recommended option first)

### Set 1: REQ-DASH-209, the period-composition view
1. **Where is it reached from?**
   - A) Its own address per collection and period, linked from each period row of a dataset's supply history and from the standing-in drill-down.
   - B) A panel on the collection page with a period picker.
   - C) Only from the scenario chip and the standing-in drill-down.
2. **Which collections?**
   - A) Every collection, daily ones too.
   - B) Quarterly collections only.
3. **Who decided?**
   - A) "rule" or "person", as `_manifest` says (REQ-PIPE-130 criterion 5).
   - B) The person's name, as the rest of the page shows.
4. **Datasets holding nothing in the period?**
   - A) Listed, as "Nothing held" with the slot's state. Why: at thirty datasets, the missing one is what matters.
   - B) Left out, matching `_manifest` exactly.

### Set 2: the two pipeline follow-ups
5. **REQ-PIPE-211: a pair ended by a later file that is not promoted?**
   - A) It also re-checks the readers.
   - B) Settlements only, as your answer was worded.
6. **REQ-PIPE-210: does a reader listed beneath its cause count in "Supplies waiting on a decision (N)"?**
   - A) No; N counts things to decide.
   - B) Yes, as today.
7. **REQ-PIPE-211: in the terminal, does the re-check run while you wait?**
   - A) Yes, with the settlement's own runs.
   - B) No, left owed for the processing pass.
8. **REQ-PIPE-211: plant a "reject both" Child Protection scenario?**
   - A) No; fixture tests only.
   - B) Yes, at the cost of another grown quarter.

### Set 3: smaller forks
9. **REQ-DASH-180: when does "Turning off after <date>" start?**
   - A) From the claim opening of the last period owed before the gap.
   - B) From the date the version was authored (its changelog entry).
   - C) Whenever effective_to lies after the date on show. This would announce a turn-off years early on past dates.
10. **REQ-DASH-208: should a scenario chip become a real `<a href>` link?** It is a button today.
    - A) Yes. Why: middle-click and "copy link" would work.
    - B) No.
11. **REQ-GEN-205: what does TS-62's Birth Registrations correction edit?**
    - A) A not_expected entry for one past day, added after the fact.
    - B) A new daily version near the end with a different claim window, which re-judges every later day.
12. **REQ-GEN-206: TS-53's collection?**
    - A) Birth Registrations. Why: no era is needed now, and it takes no Child Protection quarter.
    - B) Child Protection.

### Set 4: sign-off details
13. **REQ-GEN-136 criterion 4 (TS-48 by TS-75).**
    - A) Leave its wording and clear the unmet entry, naming TS-75.
    - B) Reword it to TS-75's shape.
14. **MoSCoW for the three new requirements.**
    - A) All should.
    - B) REQ-PIPE-211 must. Why: without it, a "reject both" leaves readers red for good on the real page.
15. **REQ-DASH-209's page weight.**
    - A) Measure before and after and report it, with no budget.
    - B) Set a budget now.

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

**Put to you:** performance and page weight for REQ-DASH-209 (question 15).

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
