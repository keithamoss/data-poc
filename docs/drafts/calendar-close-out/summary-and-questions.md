# Calendar close-out batch: final proposed draft for your morning review

Keith - this is the whole batch, with the three overnight reviews (architect, CLI UX and dashboard UX) folded in. **None of it is signed, and requirements.yaml has not changed.** The full text is in `requirements-draft.yaml`, next to this file, with the three reviews it folds in (`review-*.md`). It passes `mothman dashboard validate-requirements` when merged with the live register (203 requirements, zero errors).

I applied every review finding that was a plain wording or correctness fix with no real choice in it, and each one is recorded in its requirement's `decisions:` with the finding it came from. Everything that is a real choice is a question below, recommended option first. Your decisions from 2026-10-13 have not been reopened.

**Scoper passes.** These have not been through a scoper pass of their own:
- REQ-PIPE-179 and REQ-DASH-182 only had the joint 2026-10-13 pass (with REQ-PIPE-163).
- REQ-DASH-180 had neither that pass nor one of its own.
- The two new requirements, REQ-GEN-207 and REQ-DASH-208, have not been reviewed at all.

**Build order** (architect's suggestion; recorded on REQ-GEN-207):
1. REQ-GEN-207
2. REQ-PIPE-202
3. REQ-GEN-203
4. REQ-DASH-204
5. REQ-DASH-182
6. REQ-PIPE-163
7. REQ-PIPE-179
8. REQ-DASH-180
9. REQ-DASH-208 (before the first REQ-GEN-205/206 bootstrap)
10. REQ-GEN-205
11. REQ-GEN-206

## The requirements

**REQ-GEN-207 (NEW, must): grow the Child Protection history earlier, once.**
- **What it says:** add quarters before 2023 to the calendar and the participation and setting versions. The number comes from a dry run of the collision check over every scenario this batch plans, and the existing fifteen quarters stay byte-identical. It lands in a change of its own, before any correction.
- **Why it exists:** the architect found that the quarter budget is about seventeen quarters, not eight. 2023-Q1 is also not free, because TS-77a stands on it.
- **Two blockers it fixes:**
  - The amber and replacement settings have no version before 2023, and no default, so grown supplies would have no setting in force.
  - Adding quarters re-draws every existing one. That would move TS-79b, the arrival-semantics golden file and every quoted Child Protection text.
- **Cost:** a bootstrap of roughly nine to ten minutes.

**REQ-PIPE-202 (should): widen cp_clients' file pattern.**
- **What changed:** the CLI review found that every Child Protection load route, not just the trial, loaded files by exact name. That includes the Synthetic-mode check and the reference folder, so after the widening one of them would have silently checked one file of a pair. Criterion 8 now covers every route.

**REQ-GEN-203 (should): TS-42 and TS-80.**
- **What changed:** it now depends on REQ-GEN-207 for its quarters.
- **Open:** "built green" is a real fork, because the Child Protection generator refuses a targeted green supply without lead-ins (question 3).

**REQ-DASH-204 (should): a reader dataset turned red by another table's two files says so at the top of its page.**
- **What changed:**
  - It is now one red notice, placed among the existing banners, with a real link to the contested dataset.
  - It is judged on "the run the status is computed from".
  - Once a pair has been settled, it names what will run the checks again.
- **It also touches the pipeline.** The recorder keeps only one reason code per record, so it gains a code per table.
- **A premise of mine was wrong.** Held tables are recorded elsewhere, and overdue tables cause the same red, so "which causes" is re-asked (question 17).

**REQ-DASH-182 (must): owed-nothing rows and the delivery time in force.**
- **What changed:** your three answers from 2026-10-13 had not reached the criteria; they are now in as decided:
  - a recurring row reads "Not owed - outside its agreed months (Feb, Aug)", with the authored reason shown once on the agreement tile;
  - the current cycle shows its owed-nothing row instead of "No deliveries in the current cycle yet.";
  - the label reads "by 22:00 the day before" for one day, or "by 22:00, N days before each date" for more.
- The standing-in heading now names the row's kind.

**REQ-PIPE-163 (must): placing a held supply.**
- **Kept as you decided:** a placement is recorded as a person's re-file from no period.
- **What changed:**
  - The architect showed that the decision log refuses exactly that from a person, so criterion 39 amends the log for placement only.
  - Criterion 40 makes one shared placer for the three code paths that place a held supply.
  - Criterion 41 says "placed into <period>" on every route; some currently show "None -> P" or say re-file.
  - The promote refusal now gives the hold's own options.
  - A held pair is one row; moving its second file is shown as a consequence, and --wait is refused.
  - A schedule-ended hold is no longer a dead end in the menu, and the period chooser collapses owed-nothing runs.
  - A stale decision was corrected: the re-file refusal for an open pair is now built.

**REQ-PIPE-179 (must): turning a dataset off.**
- **What changed:**
  - TS-63 now takes quarters from REQ-GEN-207.
  - The turned-off dataset's settings must first be split from the shared Child Protection block (`*cp_participation`). Otherwise turning one off turns all six off.
  - The gap's ordinary deliveries still carry the dataset's file, which is held as turned off and counted on the quiet line.
  - A held pair is re-filed whole.
  - The gap refusal is one wording, not two.

**REQ-DASH-180 (must): the turned-off dataset on the page.**
- **What changed:** the marker goes after the red-promoted badge as well, and the quiet line sits where the accepted-gaps note sits.

**REQ-DASH-208 (NEW, should): a scenario link scrolls to what it is about.**
- **What it says:** the subject is named in the scenario's placement record and collapsed history is opened; the subject gets a static accent border with no animation, and a reload goes back to the top.
- **What it fixes:** six chips currently open with their quoted text below the fold. It also rewords REQ-GEN-199 criterion 36 (post-build-review #174 called it 34, which is out of date).

**REQ-GEN-205 (must): TS-57 to TS-62, the correction scenarios.**
- **What changed:**
  - A scripted confirmation names the scenario, dataset and index for each supply to keep, and a defined list of mistakes is refused.
  - The bootstrap now runs the re-checks a confirmation leaves behind.
  - A correction's quarters are counted once and checked against every placement.
  - Dates fixed in configuration are refused if they fall outside the history.
  - Each scenario gets before-and-after lettered links.
  - Resume confirms corrections too.
- **A defect in built code (post-build-review #177):** today's bootstrap stamps confirmations with the real clock, not the end of the replay. The architect's fix (stamp at the replay's end) would confirm REQ-PIPE-181 before its own date, because the history ends on 22 September and the correction is dated 11 October. Criterion 19 now says the later of the two, written test-first (question 28).

**REQ-GEN-206 (should): the rest of REQ-GEN-136 and REQ-GEN-137, plus #175.**
- **What changed:**
  - TS-52 is chosen from configuration and deliveries only, never a supply a correction touches.
  - TS-47's following day is claimed by TS-47 and refused rather than shifted.
  - The #174 page fix is now REQ-DASH-208.
  - TS-55 has no page that shows the _manifest, so its surface is a question.

**Proposed amendment to REQ-DASH-175 (unsigned; not redrafted here).** Add: "a re-file with an empty from-period reads 'Placed in <period>'". REQ-DASH-175 forbids raw operation names, and after REQ-PIPE-163 the raw name for a placement is re-file. Best presented together with REQ-PIPE-163.

## Questions (7 sets of 4 or fewer; recommended option first)

### Set 1: foundations
1. **Who grows the Child Protection history, and do existing quarters stay byte-identical?** (REQ-GEN-207)
   - A) It is its own requirement, built first, and nothing that exists changes. Why: every quote, the golden file and the scenarios stay put.
   - B) REQ-GEN-205 owns it and the existing quarters are re-drawn.
   - C) Its own requirement, but re-drawn.
2. **Who approves the fictional corrections?** (REQ-GEN-205, REQ-PIPE-179)
   - A) Your real identity, with each reason saying it is fictional. Why: the demo goes through the same gate a real correction does.
   - B) Extend the synthetic-asset exception so they need no real approver.
3. **Child Protection "built green" for TS-42, TS-80 and TS-50.** (REQ-GEN-203, REQ-GEN-206)
   - A) Build the Child Protection lead-ins and targeting in REQ-GEN-203. Why: otherwise the scenarios' verdicts are left to chance.
   - B) Use an ordinary clean delivery and record whatever verdict it gets.
4. **When is TS-63's turn-off correction dated?** (REQ-PIPE-179)
   - A) Before the gap. Why: the turn-off is seen as it happens. Cost: the dataset reads "awaiting confirmation" for years on past dates.
   - B) Late in the history. The gap then appears only as the correction's moves at the end.

### Set 2: the correction scenarios (REQ-GEN-205)
5. **Where does a scripted confirmation live?**
   - A) A top-level `corrections:` list in contract/scripted_decisions.yaml. Why: only the bootstrap's confirmation step reads it, and the playback code and its checks stay unchanged.
   - B) A confirm-correction operation in `decisions:`.
   - C) Keys on the correction itself in contract/calendar.yaml.
6. **One correction or several?**
   - A) Two: one confirmed correction carrying TS-57 to TS-61, and one left pending. Why: one applied summary shows all five shapes.
   - B) Six, one per scenario.
7. **TS-62's collection, and when the corrections are dated.**
   - A) TS-62 on Birth Registrations, and every correction dated late in the history. Why: "awaiting confirmation" lasts weeks, not years.
   - B) TS-62 on Child Protection.
8. **Which calendar items do the corrections edit?**
   - A) One grown quarter's date per shape. Why: the narrowest frozen item.
   - B) Claim-window changes, which need extra versions either side or re-judge every quarter.

### Set 3: scenario shapes
9. **TS-61 after its move is parked.**
   - A) It stays parked to the end, as a standing item. Why: that is honestly what happens.
   - B) A later scripted keep.
10. **TS-48, TS-49 and TS-51: still wanted?** You left them out on 2026-10-11.
    - A) TS-48 counts as demonstrated by TS-75; TS-49 and TS-51 are not planted, with your reason. Why: TS-75 already shows readers rescued by their partner.
    - B) Plant all three.
    - C) Drop all three.
11. **TS-53's shape (your un-supersede case).**
    - A) Plant it across a replacement-setting boundary, so the gate promotes the good file. Why: it meets criterion 2 as written.
    - B) Add a person's promote and amend the criterion.
    - C) Drop it.
12. **TS-50's replacement half.**
    - A) Plant it in a grown quarter under a short Child Protection green-replacement era. Why: it is the one re-check route no page shows.
    - B) Keep only the supersession half, which rides TS-42.

### Set 4: findings and surfaces
13. **TS-54's carrier.**
    - A) TS-76. Why: its substitution stands for eleven weeks.
    - B) TS-77a.
    - C) TS-55's own substitution.
14. **#175 (two extra supplies held on 8 September).**
    - A) Build TS-47's following day green and state why its late file is held. Why: that hold is a true effect of the era.
    - B) Move TS-47 out of the hold era.
    - C) Build every day in a hold era green.
15. **REQ-GEN-199 criterion 9's wording** (a signed claim; it says TS-76 leaves readers red).
    - A) Reword it to what was observed (clients amber, carers green). Why: the register already says so.
    - B) Treat the missing red as a pipeline defect.
16. **TS-55's surface** (no page shows a period's _manifest).
    - A) Its Expect quotes the terminal or a query, and its chip opens the substituted dataset's page. Why: no new page needed.
    - B) Draft a period-composition view.

### Set 5: the red reader line (REQ-DASH-204)
17. **Which causes get the line?**
    - A) Every red that comes from another table: two files for one table, could not be loaded, held, overdue, awaiting a decision. Why: at thirty datasets, "another table is overdue" is the commonest one.
    - B) Two files for one table, and could not be loaded.
    - C) Two files for one table only.
18. **What shows at collection level?**
    - A) A note under each reader's row, "Affects ..." on the contested dataset's banner, and one line on the collection card. Why: at thirty datasets one cause should read once.
    - B) The row note and "Affects" only.
    - C) Nothing.
19. **What a red reader's waiting item says, on the page and in the terminal.**
    - A) Both: the page says nothing needs deciding here, and a small pipeline requirement is drafted now for the terminal queue. Why: both currently invite the wrong decision.
    - B) The page only.
    - C) Neither.
20. **MoSCoW.**
    - A) Must. Why: REQ-GEN-203 puts three red readers on the real page.
    - B) Should.

### Set 6: smaller forks
21. **After "reject both", should the readers be re-checked?** Today nothing re-checks them, so they stay red for good.
    - A) Yes, via a small pipeline follow-up. Why: otherwise they stay red forever.
    - B) No; the line says what would re-run them.
22. **The Child Protection Synthetic-mode picker, for an arrival with two files.**
    - A) List it marked, and refuse when it is picked. Why: visible and safe.
    - B) Leave it out of the picker.
    - C) List it unmarked.
23. **Should the period chooser also replace the typed period in the settle flow's re-file?** (amends REQ-PIPE-193)
    - A) Yes. Why: periods are never typed.
    - B) No.
24. **Should a scenario jump survive a reload?** (REQ-DASH-208)
    - A) No; a reload goes to the top. Why: same as every reload.
    - B) Yes, carried in the URL.

### Set 7: sign-off confirmations
25. **REQ-PIPE-163 criteria 35 (refuse while the agreement backstop refuses the dataset) and 36 (the GitHub reply)**, which I added for consistency.
    - A) Keep both.
    - B) Drop them.
26. **REQ-DASH-180's "Turning off after <date>" foreshadow marker.**
    - A) Leave it out. Why: the dashboard reviewer leans no, and criterion 25 already covers the stretch after the last owed slot closes.
    - B) Add it.
27. **The REQ-DASH-175 amendment, "Placed in <period>".**
    - A) Add it, presented with REQ-PIPE-163. Why: otherwise the page shows a placement as a re-file.
    - B) Leave REQ-DASH-175 as it is.

### Set 8: a built defect
28. **What time should a replayed correction's confirmation carry?** (REQ-GEN-205 criterion 19, post-build-review #177)
    - A) The later of the history's end and the correction's own date. Why: the same on every bootstrap, and never earlier than the correction.
    - B) The real time the bootstrap ran (today's behaviour). True to when it happened, but it differs on every run.
    - C) The end of the replay only (the architect's fix). Wrong whenever the correction is dated after the history, as REQ-PIPE-181 is.

## Not questions, but worth knowing
- **REQ-GEN-203's quarter suggestions.** Its -13 collides with TS-67's early filing, and 2023-Q1 is not free either (TS-77a stands on it). REQ-GEN-207's dry run replaces guessing here.
- **REQ-PIPE-179's open item.** It still has a check to do at build time: whether the agreement backstop already notices a slot that vanished.
- **REQ-PIPE-163 criterion 26.** It names re-check, which does nothing until REQ-PIPE-164 is built.

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
